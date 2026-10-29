"""#50: parent Issues whose children are all done are routed to acceptance. PUBLIC synthetic data only."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_work_guide.core import build_plan, diff, digest, markdown, recheck, validate_plan
from test_github_work_guide import item, snapshot

DONE_ROWS = '- [x] 子の作業が終わる\n- [ ] 全体を照合し、人が親完了を確認する\n'
PARENT = ('# Goal\n親の目的\n# Done\n' + DONE_ROWS + '# Children / Dependencies\n'
          '- [x] 子 #2 の作業\n- [x] 子 #3 の作業\n- [ ] 親のDone、残課題と人間の最終検収を照合する。\n')


def issue(n, text=None, state='open'):
    value = item(n, state=state)
    if text is not None:
        value['body'] = text
        value['raw']['detail']['body'] = text
    value['hash'] = digest(value['raw'])
    return value


def parent_snapshot(text=PARENT, child_states=('closed', 'closed'), children=(2, 3)):
    values = [issue(1, text)] + [issue(n, state=s) for n, s in zip(children, child_states)]
    return snapshot(*values)


def candidate(value):
    return build_plan(value)['candidates']['issue:1']


def hold_codes(c):
    return {h['code'] for h in c['holds']}


class AcceptanceTests(unittest.TestCase):
    def test_all_children_done_routes_to_acceptance(self):
        value = parent_snapshot()
        c = candidate(value)
        self.assertEqual(c['kind'], 'acceptance')
        self.assertEqual(c['label'], '親の検収待ち')
        self.assertNotIn('parent_plan', hold_codes(c))
        steps = '\n'.join(c['steps'])
        self.assertIn('docs/parent-issue-completion.md', steps)
        self.assertIn('番号付き2項目', steps)
        self.assertIn('証明ではない', steps)  # CLOSED/checked is not treated as acceptance
        self.assertIn('人間が判断する', steps)
        self.assertNotIn('実装Issue', steps)
        self.assertNotIn('着手する子', steps)

    def test_recheck_is_confirmed_when_unchanged_and_stale_when_a_child_reopens(self):
        value = parent_snapshot()
        plan = build_plan(value)
        self.assertEqual(recheck(value, plan, 'issue:1', value)['status'], 'CONFIRMED')
        reopened = parent_snapshot(child_states=('closed', 'open'))
        self.assertEqual(recheck(value, plan, 'issue:1', reopened)['status'], 'STALE')

    def test_report_shows_acceptance_label(self):
        value = parent_snapshot()
        text = markdown(value, diff(value), build_plan(value))
        self.assertIn('## issue:1 — 親の検収待ち', text)

    def test_plan_is_regenerated_and_checked(self):
        value = parent_snapshot()
        plan = build_plan(value)
        validate_plan(value, plan)
        altered = copy.deepcopy(plan)
        altered['candidates']['issue:1']['kind'] = 'scope'
        with self.assertRaises(Exception):
            validate_plan(value, altered)


    def test_open_explicit_dependency_still_blocks_acceptance(self):
        text = PARENT.replace('# Done\n', '依存: #4\n# Done\n')
        value = snapshot(issue(1, text), issue(2, state='closed'), issue(3, state='closed'), issue(4))
        c = candidate(value)
        self.assertIn('dependency_state', hold_codes(c))
        self.assertIn('検収の完了として扱わない', '\n'.join(c['steps']))
        self.assertEqual(recheck(value, build_plan(value), 'issue:1', value)['status'], 'BLOCKED')


class StaysParentPlanTests(unittest.TestCase):
    def assert_parent_plan(self, value):
        c = candidate(value)
        self.assertNotEqual(c['kind'], 'acceptance')
        self.assertIn('parent_plan', hold_codes(c))
        self.assertIn('親計画を直接実装せず', '\n'.join(c['steps']))
        recheck_status = recheck(value, build_plan(value), 'issue:1', value)['status']
        self.assertEqual(recheck_status, 'BLOCKED')

    def test_open_child(self):
        self.assert_parent_plan(parent_snapshot(child_states=('closed', 'open')))

    def test_unfetched_child(self):
        self.assert_parent_plan(parent_snapshot(child_states=('closed',), children=(2,)))

    def test_numbered_row_unchecked_even_if_closed(self):
        text = PARENT.replace('- [x] 子 #3 の作業', '- [ ] 子 #3 の作業')
        self.assert_parent_plan(parent_snapshot(text))

    def test_numbered_row_unchecked_is_not_hidden_by_other_checked_rows(self):
        text = PARENT.replace('- [ ] 親のDone', '- [ ] 子 #2 の追加確認 #3\n- [ ] 親のDone')
        self.assert_parent_plan(parent_snapshot(text))

    def test_no_numbered_children(self):
        text = PARENT.replace('子 #2 の作業', '子Aの作業').replace('子 #3 の作業', '子Bの作業')
        self.assert_parent_plan(parent_snapshot(text))


class NotParentTests(unittest.TestCase):
    def test_issue_without_children_is_unchanged(self):
        text = '# Goal\n合成課題\n# Dependencies\nnone'
        c = candidate(snapshot(issue(1, text)))
        self.assertNotEqual(c['kind'], 'acceptance')
        self.assertNotIn('parent_plan', hold_codes(c))


if __name__ == '__main__':
    unittest.main()
