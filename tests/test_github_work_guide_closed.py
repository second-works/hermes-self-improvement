"""#49: closed/merged PRs skip review-gate sources. PUBLIC synthetic API only; no network/model."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_work_guide.collector import Collector, PREFIX
from github_work_guide.core import (CLOSED_PR_OMITTED, GATE_FIELDS, OLD_PLAN, Invalid, build_plan, diff, digest,
                                    markdown, recheck, save_run, seal, validate, validate_plan)
from test_github_work_guide import Fake, detail, item, snapshot

GATE_ROUTES = ('/check-runs', '/statuses', '/reviews')


class ClosedFake(Fake):
    """Fake API whose PR #25 is merged (or closed) instead of open."""

    def __init__(self, merged=True, close_during_collection=False):
        super().__init__()
        self.items = [detail(7), detail(25, True, 'closed')]
        self.items[1]['merged'] = merged
        self.close_during_collection = close_during_collection

    def get(self, path, page, timeout):
        response = super().get(path, page, timeout)
        if self.close_during_collection and path == PREFIX + '/issues' and self.inventories > 1:
            response[1]['state'] = 'open'  # state differs between the two inventories
        return response


def merged_item(n=25, with_gate=False):
    value = item(n, True, 'closed')
    value['state'] = 'MERGED'
    value['raw']['detail']['merged'] = True
    if not with_gate:
        for field in GATE_FIELDS:
            value['raw'].pop(field)
    value['hash'] = digest(value['raw'])
    return value


def rehash(value):
    value['hash'] = digest(value['raw'])
    return value


class CollectorScopeTests(unittest.TestCase):
    def test_merged_pr_reads_only_body_comments_head_and_closing(self):
        fake = ClosedFake()
        value = Collector(fake).collect()
        self.assertEqual(value['coverage']['status'], 'COMPLETE')
        routes = [r[1] for r in fake.routes]
        self.assertFalse([r for r in routes if isinstance(r, str) and r.endswith(GATE_ROUTES)])
        self.assertNotIn(f'{PREFIX}/pulls/25/comments', routes)  # review comments
        self.assertIn(f'{PREFIX}/issues/25/comments', routes)  # conversation comments stay
        self.assertEqual([r for r in fake.routes if r[0] == 'QUERY'], [('QUERY', 'closing', 25)])
        raw = value['items']['pr:25']['raw']
        self.assertEqual(value['items']['pr:25']['state'], 'MERGED')
        self.assertFalse(set(GATE_FIELDS) & set(raw))
        self.assertEqual(raw['closing'], [])
        self.assertEqual(value['coverage']['omitted'], CLOSED_PR_OMITTED)

    def test_closed_unmerged_pr_is_also_skipped(self):
        fake = ClosedFake(merged=False)
        value = Collector(fake).collect()
        self.assertEqual(value['items']['pr:25']['state'], 'CLOSED')
        self.assertFalse([r for r in fake.routes if r[0] == 'GET' and r[1].endswith(GATE_ROUTES)])

    def test_open_pr_still_reads_full_gate_and_uses_fewer_calls_when_closed(self):
        open_fake, closed_fake = Fake(), ClosedFake()
        open_value = Collector(open_fake).collect()
        closed_value = Collector(closed_fake).collect()
        self.assertEqual(open_value['coverage']['status'], 'COMPLETE')
        self.assertTrue(set(GATE_FIELDS) <= set(open_value['items']['pr:25']['raw']))
        self.assertIn(('QUERY', 'threads', 25), open_fake.routes)
        self.assertLess(closed_value['coverage']['calls'], open_value['coverage']['calls'])

    def test_state_change_during_collection_stops_as_incomplete(self):
        value = Collector(ClosedFake(close_during_collection=True)).collect()
        self.assertEqual(value['coverage']['status'], 'INCOMPLETE')
        with self.assertRaises(Invalid):
            build_plan(value)  # no guidance from an inconsistent acquisition


class ValidationTests(unittest.TestCase):
    def test_open_pr_requires_gate_fields(self):
        for field in GATE_FIELDS:
            value = item(25, True)
            value['raw'].pop(field)
            with self.assertRaises(Invalid):
                validate(snapshot(item(7), rehash(value)))

    def test_closed_pr_accepts_new_and_old_forms(self):
        validate(snapshot(item(7), merged_item()))
        validate(snapshot(item(7), merged_item(with_gate=True)))

    def test_closed_pr_still_needs_closing_and_valid_present_fields(self):
        value = merged_item()
        value['raw'].pop('closing')
        with self.assertRaises(Invalid):
            validate(snapshot(item(7), rehash(value)))
        value = merged_item(with_gate=True)
        value['raw']['checks'][0]['status'] = 'unknown'
        with self.assertRaises(Invalid):
            validate(snapshot(item(7), rehash(value)))

    def test_omitted_accepts_only_the_fixed_note(self):
        value = snapshot(item(7))
        validate(seal(value['items'], dict(value['coverage'], omitted=CLOSED_PR_OMITTED)))
        for bad in (['x'], '', '<script>任意の文</script>'):
            with self.assertRaises(Invalid):
                validate(seal(value['items'], dict(value['coverage'], omitted=bad)))


class CompareTests(unittest.TestCase):
    def test_run_before_49_compares_unchanged_for_closed_pr(self):
        old = snapshot(item(7), merged_item(with_gate=True))
        new = snapshot(item(7), merged_item())
        changes = {x['target']: x for x in diff(new, old)}
        self.assertEqual(changes['pr:25']['status'], 'UNCHANGED')

    def test_closed_pr_gate_change_is_outside_scope_but_state_change_is_not(self):
        before = merged_item(with_gate=True)
        after = copy.deepcopy(before)
        after['raw']['checks'][0]['conclusion'] = 'failure'
        old, new = snapshot(item(7), before), snapshot(item(7), rehash(after))
        self.assertEqual({x['target']: x['status'] for x in diff(new, old)}['pr:25'], 'UNCHANGED')
        plan = build_plan(old)
        self.assertEqual(recheck(old, plan, 'pr:25', new)['status'], 'CONFIRMED')
        reopened = item(25, True)  # OPEN again, with full gate data
        self.assertEqual({x['target']: x['status'] for x in diff(snapshot(item(7), reopened), old)}['pr:25'], 'CHANGED')

    def test_open_pr_gate_change_is_still_detected(self):
        before = item(25, True)
        after = copy.deepcopy(before)
        after['raw']['threads'].append({'isResolved': False})
        old, new = snapshot(item(7), before), snapshot(item(7), rehash(after))
        changes = {x['target']: x for x in diff(new, old)}
        self.assertEqual(changes['pr:25']['status'], 'CHANGED')
        self.assertIn('threads', changes['pr:25']['fields'])
        self.assertEqual(recheck(old, build_plan(old), 'pr:25', new)['status'], 'STALE')


class SavedPlanTests(unittest.TestCase):
    """Codex review on PR #52: plans saved before #49 hold old fingerprints for closed PRs."""

    def old_run(self):
        value = snapshot(item(7), merged_item(with_gate=True))
        plan = build_plan(value)
        plan['version'] = 4  # what a run saved before #49 carries
        return value, plan

    def test_old_plan_is_reported_as_old_not_altered(self):
        value, plan = self.old_run()
        with self.assertRaises(Invalid) as caught:
            validate_plan(value, plan)
        self.assertEqual(str(caught.exception), OLD_PLAN)

    def test_old_snapshot_can_be_replanned(self):
        value, _ = self.old_run()
        validate_plan(value, build_plan(value))

    def test_cli_recheck_stops_before_collecting_with_clear_message(self):
        value, plan = self.old_run()
        with tempfile.TemporaryDirectory() as tmp:
            run, out = Path(tmp).resolve() / 'runs' / 'old', Path(tmp).resolve() / 'runs' / 'pre'
            save_run(run, {'snapshot.json': value, 'plan.json': plan})
            proc = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/report_github_work_guide.py'),
                                   'recheck', '--run', str(run), '--target', 'issue:7', '--out', str(out)],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 2)
            self.assertIn(OLD_PLAN, proc.stderr)
            self.assertFalse(out.exists())  # stopped before collecting or saving


class PlanAndReportTests(unittest.TestCase):
    def test_closed_pr_plan_and_report_state_omission(self):
        value = Collector(ClosedFake()).collect()
        plan = build_plan(value)
        self.assertEqual(plan['candidates']['pr:25']['kind'], 'none')
        text = markdown(value, diff(value), plan)
        self.assertIn(f'取得対象外: {CLOSED_PR_OMITTED}。', text)
        self.assertIn('「変化なし」を意味しない', text)

    def test_report_for_run_before_49_says_no_omission(self):
        value = snapshot(item(7), merged_item(with_gate=True))
        self.assertIn('取得対象外: なし（#49より前の形式）。', markdown(value, diff(value), build_plan(value)))


if __name__ == '__main__':
    unittest.main()
