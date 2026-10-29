"""Current PUBLIC contracts; explicit syntax only, no semantic dependency inference."""
import copy
import json
from pathlib import Path
import sys
import unittest
from test_github_work_guide_real import renumber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from github_work_guide import guide
from github_work_guide.core import build_plan, digest, seal, source_url, recheck, validate_plan, Invalid
from test_github_work_guide_real import snapshot, load_rows, codes


def current_snapshot():
    rows = load_rows()
    template = copy.deepcopy(next(r for r in rows if r['detail']['number'] == 8))
    current = json.loads((ROOT / 'fixtures/github_work_guide/current_contracts_20261028.json').read_text())
    for item in current['items']:
        rows = [r for r in rows if r['detail']['number'] != item['number']]
        row = copy.deepcopy(template)
        row['detail'].update(number=item['number'], title=item['title'], body=item['body'],
                             html_url=item['url'], comments=0)
        row['comments'] = []
        rows.append(row)
    return snapshot(rows)


class CurrentContracts(unittest.TestCase):
    def test_current_goal_and_done_exclude_explicit_archive_tail(self):
        plan = build_plan(current_snapshot())
        for n in (8, 9):
            with self.subTest(n=n):
                c = plan['candidates'][f'issue:{n}']
                self.assertNotIn('goal_multiple', codes(c))
                self.assertNotIn('dependency_multiple', codes(c))
                self.assertEqual(len(c['done']), 1)
                self.assertTrue(any('履歴' in note for note in c['notes']))

    def test_annotated_none_is_not_an_unknown_dependency(self):
        c = build_plan(current_snapshot())['candidates']['issue:28']
        self.assertNotIn('dependency_prose', codes(c))
        self.assertEqual(c['dependencies'], [])

    def test_parent_child_references_are_not_prerequisites(self):
        c = build_plan(current_snapshot())['candidates']['issue:31']
        self.assertNotIn('format_missing', codes(c))
        self.assertEqual(c['dependencies'], [])
        self.assertTrue(c['children'])
        self.assertIn('親計画', '\n'.join(c['steps']))
        self.assertTrue(any('issue:8' in row['targets'] for row in c['children']))
        self.assertTrue(any('Gemma' in e['quote'] for e in c['evidence']))

    def test_annotation_cannot_hide_required_dependencies(self):
        for text in ('なし（ただし #8 が必要）', 'なし（#8未完了）',
                     'なし（#8はマージ済み、#9が必要）', 'なし（#8はマージ済み）\n#9'):
            with self.subTest(text=text):
                self.assertIsNone(guide.dependency_value(text)[0])

    def test_unmarked_or_ambiguous_history_still_holds(self):
        for body in ('# Goal\nnow\n## 履歴\n## 目的\nold',
                     '# Goal\nnow\n---\n## 履歴\n## 目的\nold\n# Goal\nlater'):
            text = guide.Text('issue:100', 'body', body)
            self.assertEqual(sum(s['name'] == 'goal' for s in guide.sections(text)), 2 if 'later' not in body else 3)

    def test_archive_words_in_code_do_not_hide_real_goal(self):
        text = guide.Text('issue:100', 'body', '# Goal\nnow\n```\n---\n## 履歴\n```\n## 目的\nother')
        self.assertEqual(sum(s['name'] == 'goal' for s in guide.sections(text)), 2)

    def test_open_closing_pr_routes_to_existing_work(self):
        s = current_snapshot()
        items = copy.deepcopy(s['items'])
        pr = copy.deepcopy(next(v for v in items.values() if v['kind'] == 'pr'))
        pr.update(number=129, state='OPEN', url=source_url('pr', 129))
        d = pr['raw']['detail']
        d.update(number=129, state='open', merged=False, html_url=pr['url'])
        pr['raw']['closing'] = [{'number': 28, 'repository': {'nameWithOwner': 'second-works/hermes-self-improvement'}}]
        pr['hash'] = digest(pr['raw'])
        items['pr:129'] = pr
        c = build_plan(seal(items, s['coverage']))['candidates']['issue:28']
        self.assertIn('active_pr', codes(c))
        self.assertIn('pr:129', '\n'.join(c['steps']))
        self.assertIn('重複', '\n'.join(c['steps']))

    def test_parent_children_ignore_comment_line_collisions(self):
        s = current_snapshot()
        items = copy.deepcopy(s['items'])
        item = items['issue:31']
        lines = item['body'].split('\n')
        row = next(i for i, line in enumerate(lines) if '- [ ] ⑤既存 #8' in line)
        item['raw']['comments'] = [{'body': '\n' * row + '#999'}]
        item['raw']['detail']['comments'] = 1
        item['hash'] = digest(item['raw'])
        c = build_plan(seal(items, s['coverage']))['candidates']['issue:31']
        self.assertFalse(any('#999' in child['targets'] for child in c['children']))

    def test_no_number_specific_current_contract_rules(self):
        s = current_snapshot()
        shifted = snapshot(renumber([i['raw'] for i in s['items'].values()], 100))
        plan = build_plan(shifted)
        for n in (108, 109):
            self.assertNotIn('goal_multiple', codes(plan['candidates'][f'issue:{n}']))
        self.assertTrue(plan['candidates']['issue:131']['children'])
        self.assertNotIn('dependency_prose', codes(plan['candidates']['issue:128']))

    def test_archive_separator_is_not_dependency_content(self):
        for value in ('none', 'なし', 'なし（#26 / PR #27はマージ済み）'):
            with self.subTest(value=value):
                snapshot0 = current_snapshot()
                items = copy.deepcopy(snapshot0['items'])
                item = items['issue:28']
                item['body'] = '# Goal\ncurrent\n# Dependencies\n' + value + '\n\n---\n## 履歴\n## 目的\nold'
                item['raw']['detail']['body'] = item['body']
                item['hash'] = digest(item['raw'])
                snap = seal(items, snapshot0['coverage'])
                text = guide.Text('issue:28', 'body', item['body'])
                section = next(s for s in guide.sections(text) if s['name'] == 'dependencies')
                self.assertEqual(section['content'], value)
                self.assertEqual(guide.subtree_content(text, section), value)
                plan = build_plan(snap)
                self.assertNotIn('dependency_prose', codes(plan['candidates']['issue:28']))
                self.assertEqual(recheck(snap, plan, 'issue:28', snap)['status'], 'CONFIRMED')

    def test_old_plan_version_is_not_reused(self):
        s = current_snapshot()
        plan = build_plan(s)
        self.assertEqual(plan['version'], 6)
        for old in (2, 4, 5):  # v4: before #49 fingerprints, v5: before the parent acceptance kind (#50)
            with self.assertRaises(Invalid):
                validate_plan(s, dict(plan, version=old))

    def test_archive_is_still_part_of_snapshot_fingerprint(self):
        s = current_snapshot()
        plan = build_plan(s)
        changed = copy.deepcopy(s['items'])
        item = changed['issue:8']
        item['body'] += '\n履歴への追記\n'
        item['raw']['detail']['body'] = item['body']
        item['hash'] = digest(item['raw'])
        fresh = seal(changed, s['coverage'])
        self.assertEqual(recheck(s, plan, 'issue:8', fresh)['status'], 'STALE')


if __name__ == '__main__':
    unittest.main()
