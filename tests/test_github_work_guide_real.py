"""Expected guidance for real PUBLIC Issue/PR text (fixtures/github_work_guide/real_20261023.json).

The fixture is PUBLIC REST GET output captured on 2026-10-23. These tests fix what a person
needs to resume work on each OPEN Issue; they are not a semantic accuracy measurement.
"""
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from github_work_guide.core import (Invalid, REPO, build_plan, diff, digest, load_run, markdown, read_json, recheck, save_run,
                                   seal, source_url, validate, validate_plan)
import tempfile

FIXTURE = ROOT / 'fixtures/github_work_guide/real_20261023.json'
PR25_HEAD = '3dd1227d1f7905d04fce62c8a12393cd9336480e'


def load_rows():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['items']


def snapshot(rows):
    items = {}
    for raw in rows:
        d = raw['detail']
        kind = 'pr' if 'checks' in raw else 'issue'
        items[f'{kind}:{d["number"]}'] = {
            'kind': kind, 'number': d['number'],
            'state': 'MERGED' if kind == 'pr' and d['merged'] else d['state'].upper(),
            'title': d['title'], 'body': d['body'] or '', 'url': source_url(kind, d['number']),
            'raw': raw, 'hash': digest(raw)}
    return validate(seal(items, {'status': 'COMPLETE', 'errors': [], 'calls': 0,
                                 'limits': {'pages': 10, 'items': 5000, 'calls': 500, 'seconds': 180},
                                 'connections': [{'route': 'fixture', 'complete': True}]}))


def renumber(rows, offset):
    """Same text with every same-repo number shifted, to catch number-specific rules."""
    url = re.compile(r'(https://github\.com/' + re.escape(REPO) + r'/(?:issues|pull)/)(\d+)')
    def text(value):
        value = url.sub(lambda m: m.group(1) + str(int(m.group(2)) + offset), value)
        return re.sub(r'(?<![\w.-])#(\d+)', lambda m: '#' + str(int(m.group(1)) + offset), value)
    rows = copy.deepcopy(rows)
    for raw in rows:
        d = raw['detail']
        d['number'] += offset
        d['html_url'] = source_url('pr' if 'checks' in raw else 'issue', d['number'])
        d['body'] = text(d['body'] or '')
        d['title'] = text(d['title'])
        for comment in raw['comments']:
            comment['body'] = text(comment['body'])
        for closing in raw.get('closing', []):
            closing['number'] += offset
    return rows


def codes(candidate):
    return [h['code'] for h in candidate['holds']]


def evidence_quotes(candidate, ids):
    table = {e['id']: e['quote'] for e in candidate['evidence']}
    return [table[i] for i in ids]


class RealIssueGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_rows()
        cls.snap = snapshot(cls.rows)
        cls.plan = build_plan(cls.snap)
        cls.c = cls.plan['candidates']

    def test_issue_7_updated_goal_and_merged_related_pr(self):
        c = self.c['issue:7']
        self.assertEqual(c['kind'], 'completion')
        self.assertEqual(c['dependencies'], [])
        goal = [h for h in c['holds'] if h['code'] == 'goal_multiple']
        self.assertEqual(len(goal), 1)
        quotes = evidence_quotes(c, goal[0]['evidence'])
        self.assertTrue(any('改善候補を作成する' in q for q in quotes))
        self.assertTrue(any('事前登録済みの修正操作' in q for q in quotes))
        self.assertTrue(any('更新' in q for q in quotes))  # the enclosing heading says it updates the goal
        related = [r for r in c['related'] if r['target'] == 'pr:25']
        self.assertTrue(related)
        self.assertEqual({r['state'] for r in related}, {'MERGED'})
        self.assertIn('refs', {r['relation'] for r in related})
        self.assertNotIn('closing', {r['relation'] for r in related})
        self.assertIn({'checked': 6, 'total': 6}, [{k: d[k] for k in ('checked', 'total')} for d in c['done']])
        steps = '\n'.join(c['steps'])
        self.assertIn('pr:25', steps)
        self.assertIn(PR25_HEAD, steps)
        self.assertIn('Merge', steps)
        self.assertIn('人間が判断', steps)
        self.assertTrue(any('pr:25' in n and 'Merge' in n for n in c['notes']))
        deps = [h for h in c['holds'] if h['code'] == 'dependency_prose']
        mentioned = {m['target']: m['state'] for h in deps for m in h['mentioned']}
        self.assertEqual({k: mentioned.get(k) for k in ('pr:17', 'pr:22', 'pr:23', 'pr:24')},
                         {k: 'MERGED' for k in ('pr:17', 'pr:22', 'pr:23', 'pr:24')})
        self.assertEqual(recheck(self.snap, self.plan, 'issue:7', self.snap)['status'], 'BLOCKED')
        text = json.dumps(c, ensure_ascii=False)
        for claim in ('完了している', 'Close済み', '採用済み', '本番完了'):
            self.assertNotIn(claim, ''.join(c['steps'] + c['notes']), claim)
        self.assertIn('closing', text)

    def test_issue_8_sections_and_missing_verification(self):
        c = self.c['issue:8']
        names = {s['name'] for s in c['sections']}
        self.assertTrue({'goal', 'scope', 'done'} <= names)
        self.assertIn('verification', c['gaps'])
        self.assertNotIn('format_missing', codes(c))
        deps = [h for h in c['holds'] if h['code'] == 'dependency_prose']
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]['category'], 'semantic')
        self.assertEqual([t['term'] for t in deps[0]['terms']], ['共通テンプレート', '評価基盤', '隔離スキル作成'])
        self.assertTrue(any('ロールバック' in q for q in evidence_quotes(c, [d['evidence'] for d in c['done']])))
        self.assertTrue(any('検証' in s and '完了条件' in s for s in c['steps']))

    def test_issue_9_prose_dependencies_stay_candidates(self):
        c = self.c['issue:9']
        self.assertEqual(c['dependencies'], [])
        deps = [h for h in c['holds'] if h['code'] == 'dependency_prose']
        terms = {t['term']: t for t in deps[0]['terms']}
        self.assertEqual(list(terms), ['Memory', '自己監査', '評価基盤', 'Self-Evolution調査', '委任実装', 'GitHub承認フロー'])
        candidates = [x['target'] for x in terms['GitHub承認フロー']['candidates']]
        self.assertIn('issue:8', candidates)
        self.assertTrue(all(x['confirmed'] is False for t in terms.values() for x in t['candidates']))
        self.assertTrue(any('GitHub承認フロー' in q for q in evidence_quotes(c, deps[0]['evidence'])))
        self.assertTrue(any('依存' in s and '番号' in s for s in c['steps']))

    def test_issue_18_missing_sections_external_parent_and_boundary(self):
        c = self.c['issue:18']
        missing = {h['section'] for h in c['holds'] if h['code'] == 'format_missing'}
        self.assertEqual(missing, {'goal', 'dependencies'})
        self.assertTrue(all(h['category'] == 'format' for h in c['holds'] if h['code'] == 'format_missing'))
        self.assertIn({'checked': 0, 'total': 5}, [{k: d[k] for k in ('checked', 'total')} for d in c['done']])
        external = [x['url'] for x in c['external']]
        self.assertIn('https://github.com/second-works/ai-security-governance/issues/1', external)
        self.assertTrue(all('取得しない' in x['note'] for x in c['external']))
        self.assertTrue(any('issue:4' in s and '境界' in s for s in c['steps']))
        self.assertTrue(any('対象外repo' in s and '取得しない' in s for s in c['steps']))
        four = [r for r in c['related'] if r['target'] == 'issue:4']
        self.assertTrue(four)
        self.assertTrue(any('Do not modify existing self-audit issue #4 scope' in q
                            for q in evidence_quotes(c, [r['evidence'] for r in four])))

    def test_open_issue_guidance_is_specific(self):
        open_issues = [k for k, v in self.snap['items'].items() if v['kind'] == 'issue' and v['state'] == 'OPEN']
        self.assertEqual(len(open_issues), 10)
        steps = [tuple(self.c[k]['steps']) for k in open_issues]
        self.assertEqual(len(set(steps)), len(open_issues))
        self.assertGreater(len({self.c[k]['kind'] for k in open_issues}), 1)
        for key in open_issues:
            for hold in self.c[key]['holds']:
                for field in ('reason', 'check', 'question', 'release'):
                    self.assertTrue(hold[field], (key, hold['code'], field))
                self.assertNotIn(hold['release'], ('人が確認する。', '人が確認'))

    def test_quotes_are_exact_excerpts(self):
        sources = {}
        for key, it in self.snap['items'].items():
            sources[key] = [it['body']] + [c['body'] for c in it['raw']['comments']]
        for c in self.c.values():
            for e in c['evidence']:
                owner = ':'.join(e['id'].split(':')[:2])
                if e['id'].endswith((':state', ':head')):
                    continue
                self.assertTrue(any(e['quote'] in s for s in sources[owner]), e['id'])

    def test_report_is_shorter_than_sources(self):
        report = markdown(self.snap, diff(self.snap), self.plan)
        total = sum(len(it['body']) for it in self.snap['items'].values())
        self.assertLess(len(report), total)
        self.assertIn('issue:7', report)
        self.assertNotIn('<script', report)

    def test_report_shows_done_counts(self):
        # The quoted Done excerpt may be truncated, so the count must appear on its own line.
        report = markdown(self.snap, diff(self.snap), self.plan)
        section = report.split('## issue:18 ')[1].split('\n## ')[0]
        self.assertIn('- 完了条件: L9 0/5チェック', section)
        section = report.split('## issue:7 ')[1].split('\n## ')[0]
        self.assertIn('- 完了条件: L11 チェック項目なし、L34 6/6チェック', section)

    def test_repository_metadata_only_is_not_a_work_change(self):
        moved = copy.deepcopy(self.rows)
        for raw in moved:
            if 'checks' in raw:
                for side in ('head', 'base'):
                    raw['detail'][side]['repo'].update(open_issues_count=99, pushed_at='2026-10-24T00:00:00Z',
                                                       updated_at='2026-10-24T00:00:00Z')
        fresh = snapshot(moved)
        self.assertNotEqual(fresh['items']['pr:25']['hash'], self.snap['items']['pr:25']['hash'])
        changes = diff(fresh, self.snap)
        self.assertEqual({x['status'] for x in changes}, {'UNCHANGED'})
        self.assertTrue(all(x['metadata_only'] for x in changes if x['target'].startswith('pr:')))
        result = recheck(self.snap, self.plan, 'issue:7', fresh)
        self.assertNotEqual(result['status'], 'STALE')
        for mutate in (lambda d: d['head'].update(sha='b' * 40), lambda d: d.update(state='open', merged=False),
                       lambda d: d.update(body=d['body'] + '\n追記')):
            changed = copy.deepcopy(self.rows)
            pr = next(r for r in changed if r['detail']['number'] == 25 and 'checks' in r)
            mutate(pr['detail'])
            fresh = snapshot(changed)
            self.assertIn('CHANGED', {x['status'] for x in diff(fresh, self.snap)})
            self.assertEqual(recheck(self.snap, self.plan, 'issue:7', fresh)['status'], 'STALE')

    def test_saved_plan_round_trip_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / 'runs' / 'real'
            save_run(out, {'snapshot.json': self.snap, 'plan.json': self.plan})
            snap, plan = load_run(out), read_json(out / 'plan.json')
            validate_plan(snap, plan)
            for mutate in (lambda c: c['steps'].append('Issue #7は完了した'),
                           lambda c: c['holds'].pop(),
                           lambda c: c['related'][0].update(relation='closing'),
                           lambda c: c['holds'][0]['terms'][0]['candidates'][0].update(confirmed=True)
                           if c['holds'][0].get('terms') else c['notes'].append('x')):
                altered = copy.deepcopy(plan)
                mutate(altered['candidates']['issue:7'])
                with self.assertRaises(Invalid):
                    validate_plan(snap, altered)
            old = copy.deepcopy(plan)
            old['version'] = 1
            with self.assertRaises(Invalid):
                validate_plan(snap, old)

    def test_renumbered_copy_has_same_structure(self):
        offset = 100
        other = build_plan(snapshot(renumber(self.rows, offset)))['candidates']
        def shape(c):
            return (c['kind'], sorted(codes(c)), sorted((r['relation'], r['state']) for r in c['related']),
                    len(c['steps']), len(c['external']))
        for key, c in self.c.items():
            kind, n = key.split(':')
            self.assertEqual(shape(other[f'{kind}:{int(n) + offset}']), shape(c), key)


    def edited(self, number, old, new):
        rows = copy.deepcopy(self.rows)
        raw = next(r for r in rows if 'checks' not in r and r['detail']['number'] == number)
        self.assertEqual(raw['detail']['body'].count(old), 1)
        raw['detail']['body'] = raw['detail']['body'].replace(old, new)
        return build_plan(snapshot(rows))['candidates'][f'issue:{number}']

    def test_pr_named_dependency_stays_unconfirmed(self):
        # pr:25 exists; "PR #25" must not become the unknown issue:25 or a confirmed order edge.
        c = self.edited(8, '依存: 共通テンプレート、評価基盤、隔離スキル作成。', '依存: PR #25')
        self.assertIn('dependency_prose', codes(c))
        self.assertNotEqual(c['kind'], 'dependency')
        self.assertFalse(any('issue:25' in h['reason'] for h in c['holds']))
        c = self.edited(8, '依存: 共通テンプレート、評価基盤、隔離スキル作成。', '依存: issue #5')
        self.assertEqual(c['kind'], 'dependency')
        self.assertTrue(any(h['reason'].startswith('issue:5:') for h in c['holds']))

    def test_done_counts_ignore_code_block_examples(self):
        c = self.edited(18, '- [ ] Evidence of verification and remaining limitations included in PR\n',
                        '- [ ] Evidence of verification and remaining limitations included in PR\n'
                        '```md\n- [x] Example only\n```\n')
        self.assertEqual([(d['checked'], d['total']) for d in c['done']], [(0, 5)])


    def test_done_counts_include_subheadings(self):
        old = '- [ ] Evidence of verification and remaining limitations included in PR\n'
        c = self.edited(18, old, old + '### Backend\n- [x] Sub item done\n### Tests\n- [ ] Sub item open\n')
        self.assertEqual([(d['checked'], d['total']) for d in c['done']], [(1, 7)])
        # A named section nested under Done (e.g. ### Verification) is not a completion condition.
        c = self.edited(18, old, old + '### Verification\n- [x] Ran tests\n')
        self.assertEqual([(d['checked'], d['total']) for d in c['done']], [(0, 5)])
        # A Done heading made only of subheadings counts their items instead of reporting none.
        c = self.edited(8, '## 完了条件\n評価済み候補がPRとして出され、人間の承認で採用でき、想定した問題に対してロールバックできる。\n',
                        '## 完了条件\n### Backend\n- [ ] One\n### Tests\n- [x] Two\n')
        self.assertEqual([(d['checked'], d['total']) for d in c['done']], [(1, 2)])

    def test_goal_with_only_subheadings_is_not_empty(self):
        c = self.edited(8, '## 目的\nHermesが作成した変更', '## 目的\n### 管理\nHermesが作成した変更')
        self.assertNotIn('goal_empty', codes(c))
        c = self.edited(8, '## 目的\nHermesが作成した変更をGitHub上の追跡可能なIssue/PRとして管理し、安全に適用・復旧する。\n',
                        '## 目的\n')
        self.assertIn('goal_empty', codes(c))

    def test_nested_fences_close_only_with_matching_marker(self):
        from github_work_guide.guide import Text
        body = ('## Goal\nReal goal\n\n````md\n## Goal\n```sh\nexample\n```\n## Goal\n````\n'
                '~~~\n```\n## Goal\n~~~\n```\n## Goal\n```` \n## Scope\nx')
        self.assertEqual([h[2] for h in Text('issue:1', 'body', body).headings], ['Goal', 'Scope'])
        # An unclosed fence runs to the end of the text, as in Markdown.
        self.assertEqual([h[2] for h in Text('issue:1', 'body', '## Goal\n```\n## Goal').headings], ['Goal'])
        c = self.edited(8, '## 作業\n', '````md\n## 目的\n```sh\nx\n```\n## 目的\n````\n\n## 作業\n')
        self.assertNotIn('goal_multiple', codes(c))

    def test_comment_goal_inside_code_block_is_not_a_change(self):
        def with_comment(text):
            rows = copy.deepcopy(self.rows)
            four = next(r for r in rows if 'checks' not in r and r['detail']['number'] == 4)
            raw = next(r for r in rows if 'checks' not in r and r['detail']['number'] == 8)
            comment = copy.deepcopy(four['comments'][0])
            comment['body'] = text
            raw['comments'] = [comment]
            raw['detail']['comments'] = 1
            return build_plan(snapshot(rows))['candidates']['issue:8']
        self.assertNotIn('comment_change', codes(with_comment('例:\n```md\n## Goal\n```\n')))
        self.assertIn('comment_change', codes(with_comment('Goalを変更します。')))

if __name__ == '__main__':
    unittest.main()
