"""#51: one candidate's guidance from a verified saved run. PUBLIC synthetic data; no network/model."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_work_guide.core import (EXCERPT_LIMIT, OLD_PLAN, Invalid, build_plan, digest, excerpt, markdown,
                                    mentions, save_run, seal, diff)
from test_github_work_guide import item, snapshot

CLI = ROOT / 'scripts/report_github_work_guide.py'
CLOSED = range(2, 32)  # 30 closed related Issues, including #3 and #31 (ID prefix check)


def issue(n, text=None, state='open'):
    value = item(n, state=state)
    if text is not None:
        value['body'] = text
        value['raw']['detail']['body'] = text
    value['hash'] = digest(value['raw'])
    return value


def target_text():
    related = ' '.join(f'#{n}' for n in CLOSED)
    return ('# Goal\n対象の目的\n# Done\n- [ ] 完了条件\n# Dependencies\n#40 の結果を見てから決める\n'
            f'# Context\n参考: {related}\n境界: #41 と重ならないこと\n')


def run_snapshot():
    values = [issue(1, target_text())] + [issue(n, state='closed') for n in CLOSED]
    values += [issue(40), issue(41)]
    return snapshot(*values)


class ExcerptTests(unittest.TestCase):
    def setUp(self):
        self.value = run_snapshot()
        self.plan = build_plan(self.value)
        self.c = self.plan['candidates']['issue:1']
        self.text = excerpt(self.value, self.plan, 'issue:1', 'synthetic-run')

    def test_steps_holds_and_conditions_are_kept_in_full(self):
        for step in self.c['steps']:
            self.assertIn(step, self.text)
        self.assertTrue(self.c['holds'])
        for h in self.c['holds']:
            for field in ('reason', 'question', 'release'):
                self.assertIn(h[field], self.text)
        self.assertIn(self.c['start_condition'], self.text)
        self.assertIn(self.c['stop_condition'], self.text)

    def test_header_names_run_hash_and_target(self):
        self.assertIn('run: "synthetic-run"', self.text)
        risky = excerpt(self.value, self.plan, 'issue:1', '[x](http://example.invalid)<b>')
        self.assertNotIn('[x](', risky)
        self.assertNotIn('<b>', risky)
        self.assertIn(self.value['hash'], self.text)
        self.assertIn('対象: issue:1 / plan version:', self.text)
        self.assertIn('期待回答や人の判断は含まない', self.text)

    def test_related_keeps_open_and_hold_cited_and_counts_the_rest(self):
        self.assertIn('関連候補: issue:41（OPEN', self.text)
        self.assertIn('関連候補: issue:40（OPEN', self.text)
        for n in (3, 31):
            self.assertNotIn(f'関連候補: issue:{n}（', self.text)
        self.assertIn('関連候補のうち30件', self.text)

    def test_unfetched_related_is_kept_not_counted_as_closed(self):
        text = target_text() + '参考: See #999\n'
        value = snapshot(issue(1, text), *[issue(n, state='closed') for n in CLOSED], issue(40), issue(41))
        out = excerpt(value, build_plan(value), 'issue:1', 'run')
        self.assertIn('関連候補: #999（UNFETCHED', out)
        self.assertIn('関連候補のうち30件', out)

    def test_excerpt_is_smaller_than_the_full_section(self):
        full = markdown(self.value, diff(self.value), self.plan)
        self.assertLess(len(self.text), len(full))
        self.assertLess(len(self.text), EXCERPT_LIMIT)
        self.assertNotIn('目安の', self.text)

    def test_quotes_are_substrings_of_the_source(self):
        sources = {k: v['body'] + '\n' + '\n'.join(c['body'] for c in v['raw']['comments'])
                   for k, v in self.value['items'].items()}
        cited = [e for e in self.c['evidence'] if ':L' in e['id'] and mentions(self.text, e['id'])]
        self.assertTrue(cited)
        for e in cited:
            owner = ':'.join(e['id'].split(':')[:2])
            self.assertIn(e['quote'], sources[owner])

    def test_unused_evidence_is_dropped(self):
        unused = [e['id'] for e in self.c['evidence'] if e['id'].startswith('issue:3:')]
        for i in unused:
            self.assertNotIn(f'[{i}]', self.text)

    def test_unknown_target_and_altered_plan_are_rejected(self):
        with self.assertRaises(Invalid):
            excerpt(self.value, self.plan, 'issue:999', 'run')
        altered = json.loads(json.dumps(self.plan))
        altered['candidates']['issue:1']['steps'].append('捏造した手順')
        with self.assertRaises(Invalid):
            excerpt(self.value, altered, 'issue:1', 'run')

    def test_old_plan_version_is_reported(self):
        with self.assertRaises(Invalid) as caught:
            excerpt(self.value, dict(self.plan, version=4), 'issue:1', 'run')
        self.assertEqual(str(caught.exception), OLD_PLAN)

    def test_incomplete_snapshot_is_rejected(self):
        coverage = dict(self.value['coverage'], status='INCOMPLETE', errors=['x'])
        with self.assertRaises(Invalid):
            excerpt(seal(self.value['items'], coverage), self.plan, 'issue:1', 'run')

    def test_long_excerpt_is_flagged_not_truncated(self):
        with patch('github_work_guide.core.EXCERPT_LIMIT', 500):
            text = excerpt(self.value, self.plan, 'issue:1', 'run')
        self.assertIn('目安の500文字を超えている', text)
        for step in self.c['steps']:
            self.assertIn(step, text)

    def test_every_hold_evidence_is_kept(self):
        text = '# Goal\n目的A\n# Goal\n目的B\n# Dependencies\nnone\n'
        value = snapshot(issue(1, text))
        plan = build_plan(value)
        c = plan['candidates']['issue:1']
        out = excerpt(value, plan, 'issue:1', 'run')
        ids = [i for h in c['holds'] for i in h['evidence']]
        self.assertGreater(len(ids), 1)  # goal_multiple cites both goal sections
        for i in ids:
            self.assertIn(f'[{i}]', out)
        for h in self.c['holds']:
            for i in h['evidence']:
                self.assertIn(f'[{i}]', self.text)

    def test_mentions_matches_whole_ids_only(self):
        self.assertFalse(mentions('issue:1:L1-L2', 'issue:1:L1'))
        self.assertTrue(mentions('issue:1:L1-L2', 'issue:1:L1-L2'))
        self.assertTrue(mentions('issue:31 と issue:3。', 'issue:3'))
        self.assertFalse(mentions('issue:31 だけ', 'issue:3'))
        self.assertFalse(mentions('issue:31:L9:1', 'issue:31:L9'))
        self.assertTrue(mentions('（issue:31:L9）', 'issue:31:L9'))


class CliTests(unittest.TestCase):
    def run_cli(self, run, target, out):
        return subprocess.run([sys.executable, '-I', '-B', str(CLI), 'excerpt', '--run', str(run),
                               '--target', target, '--out', str(out)], capture_output=True, text=True, timeout=60)

    def make_run(self, tmp, **documents):
        run = Path(tmp).resolve() / 'runs' / 'saved'
        save_run(run, documents)
        return run

    def test_cli_writes_a_new_excerpt_run(self):
        value = run_snapshot()
        plan = build_plan(value)
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': value, 'plan.json': plan})
            out = run.parent / 'ex1'
            proc = self.run_cli(run, 'issue:1', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = (out / 'excerpt.md').read_text(encoding='utf-8')
            self.assertEqual(text, excerpt(value, plan, 'issue:1', 'saved'))
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(set(manifest['files']), {'excerpt.md'})

    def test_cli_rejects_without_output(self):
        value = run_snapshot()
        plan = build_plan(value)
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': value, 'plan.json': plan})
            proc = self.run_cli(run, 'issue:999', run.parent / 'ex-missing')
            self.assertEqual(proc.returncode, 2)
            self.assertFalse((run.parent / 'ex-missing').exists())
            # altered run: one byte of the saved snapshot changes after the manifest was written
            snap = run / 'snapshot.json'
            snap.write_text(snap.read_text(encoding='utf-8').replace('対象の目的', '対象の目的X', 1), encoding='utf-8')
            proc = self.run_cli(run, 'issue:1', run.parent / 'ex-altered')
            self.assertEqual(proc.returncode, 2)
            self.assertFalse((run.parent / 'ex-altered').exists())

    def test_cli_rejects_run_without_plan_or_with_old_plan(self):
        value = run_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': value})
            proc = self.run_cli(run, 'issue:1', run.parent / 'ex-noplan')
            self.assertEqual(proc.returncode, 2)
            self.assertFalse((run.parent / 'ex-noplan').exists())
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': value, 'plan.json': dict(build_plan(value), version=4)})
            proc = self.run_cli(run, 'issue:1', run.parent / 'ex-old')
            self.assertEqual(proc.returncode, 2)
            self.assertIn(OLD_PLAN, proc.stderr)
            self.assertFalse((run.parent / 'ex-old').exists())

    def test_cli_rejects_unsupported_flags(self):
        value = run_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': value, 'plan.json': build_plan(value)})
            for flags in (['--priority', 'issue:1'], ['--previous', str(run)]):
                out = run.parent / ('ex-flag' + flags[0])
                proc = subprocess.run([sys.executable, '-I', '-B', str(CLI), 'excerpt', '--run', str(run),
                                       '--target', 'issue:1', '--out', str(out)] + flags,
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 2)
                self.assertFalse(out.exists())

    def test_cli_rejects_incomplete_run(self):
        value = run_snapshot()
        coverage = dict(value['coverage'], status='INCOMPLETE', errors=['x'])
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, **{'snapshot.json': seal(value['items'], coverage)})
            proc = self.run_cli(run, 'issue:1', run.parent / 'ex-incomplete')
            self.assertEqual(proc.returncode, 2)
            self.assertFalse((run.parent / 'ex-incomplete').exists())


if __name__ == '__main__':
    unittest.main()
