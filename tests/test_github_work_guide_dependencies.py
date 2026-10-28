"""Literal dependency hints are evidence to inspect, never confirmed prerequisites."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from github_work_guide.core import build_plan,digest,seal,recheck,markdown,diff,validate_plan,Invalid
from test_github_work_guide_current import current_snapshot
from test_github_work_guide_real import snapshot,renumber


def dependency_snapshot():
    old=current_snapshot()
    rows=[v['raw'] for v in old['items'].values()]
    extra=json.loads((ROOT/'fixtures/github_work_guide/dependency_evidence_20261028.json').read_text())['items']
    numbers={r['detail']['number'] for r in extra}
    return snapshot([r for r in rows if r['detail']['number'] not in numbers]+extra)


def body_snapshot(body):
    old=dependency_snapshot();items=copy.deepcopy(old['items']);item=items['issue:8']
    item['body']=body;item['raw']['detail']['body']=body;item['hash']=digest(item['raw'])
    return seal(items,old['coverage'])


class DependencyGuidanceTests(unittest.TestCase):
    def test_explicit_35_routes_to_done_and_ref_pr_without_confirming(self):
        s=dependency_snapshot();p=build_plan(s);c=p['candidates']['issue:8']
        self.assertEqual(c['dependencies'],[])
        self.assertEqual([h['target'] for h in c.get('dependency_hints',[])],['issue:35'])
        h=c.get('dependency_hints',[])[0]
        self.assertFalse(h['confirmed']);self.assertEqual(h['state'],'CLOSED')
        self.assertEqual([(x['checked'],x['total']) for x in h['done']],[(5,5)])
        self.assertTrue(any(x['target']=='pr:40' and x['relation']=='refs' for x in h['related_prs']))
        steps='\n'.join(c['steps'])
        self.assertIn('issue:35',steps);self.assertIn('pr:40',steps)
        self.assertIn('11a8f2a0b511339e98b8ec1d125be908dedab59e',steps)
        self.assertIn('Done',steps)
        self.assertFalse(any('番号が確定していない' in r for r in c['hold_reasons']))
        self.assertEqual(recheck(s,p,'issue:8',s)['status'],'BLOCKED')
        report=markdown(s,diff(s),p)
        self.assertIn('未確定の依存確認先',report)
        self.assertIn('独立評価の証拠',report)

    def test_9_hints_only_8_not_parent_optional_or_transitive_numbers(self):
        c=build_plan(dependency_snapshot())['candidates']['issue:9']
        self.assertEqual([h['target'] for h in c.get('dependency_hints',[])],['issue:8'])
        self.assertEqual(c['dependencies'],[])

    def test_format_limitation_and_unspecified_number_are_distinct(self):
        with_number=build_plan(body_snapshot('# Goal\nx\n# Dependencies\n#35（完了条件の確認後）'))['candidates']['issue:8']
        without_number=build_plan(body_snapshot('# Goal\nx\n# Dependencies\n評価基盤の後'))['candidates']['issue:8']
        self.assertNotEqual(with_number['hold_reasons'],without_number['hold_reasons'])
        self.assertFalse(any('番号が確定していない' in r for r in with_number['hold_reasons']))

    def test_number_shift_preserves_structure(self):
        s=dependency_snapshot();shifted=snapshot(renumber([x['raw'] for x in s['items'].values()],100))
        c=build_plan(shifted)['candidates']['issue:108']
        self.assertEqual([h['target'] for h in c.get('dependency_hints',[])],['issue:135'])
        self.assertTrue(any(p['target']=='pr:140' for p in c.get('dependency_hints',[])[0]['related_prs']))

    def test_statement_label_grammar_preserves_only_primary_references(self):
        for value in ('Parent: #31。Depends on: #35（#32は参考）。',
                      'Parent: #31. Depends on: Issue #35（完了条件）。',
                      'Parent: #31; 依存: #35（条件）。'):
            with self.subTest(value=value):
                c=build_plan(body_snapshot('# Goal\nx\n# Dependencies\n'+value))['candidates']['issue:8']
                self.assertEqual([h['target'] for h in c['dependency_hints']],['issue:35'])
                self.assertEqual(c['dependencies'],[])
        for value in ('Parent: #35（条件）', '任意: #35', 'Not Depends on: #35',
                      'Depends on: #35abc', 'Depends on: https://github.com/other/repo/issues/35'):
            with self.subTest(value=value):
                c=build_plan(body_snapshot('# Goal\nx\n# Dependencies\n'+value))['candidates']['issue:8']
                self.assertEqual(c['dependency_hints'],[])

    def test_fences_inline_code_comments_and_history_are_not_declarations(self):
        for value in ('```\nDepends on: #35\n```', '`Depends on: #35`',
                      '説明。`Depends on: #35`', 'Depends on: `#35`'):
            with self.subTest(value=value):
                c=build_plan(body_snapshot('# Goal\nx\n# Dependencies\n'+value))['candidates']['issue:8']
                self.assertEqual(c['dependency_hints'],[])
        s=body_snapshot('# Goal\nx\n# Dependencies\n条件未定\n\n---\n## 履歴\nDepends on: #35')
        items=copy.deepcopy(s['items']);item=items['issue:8']
        item['raw']['comments']=[{'body':'Depends on: #35'}];item['raw']['detail']['comments']=1
        item['hash']=digest(item['raw'])
        self.assertEqual(build_plan(seal(items,s['coverage']))['candidates']['issue:8']['dependency_hints'],[])

    def test_missing_target_and_pr_type_stay_held(self):
        for value,target in [('Depends on: #999（条件）','#999'),('Depends on: PR #25（条件）','pr:25')]:
            with self.subTest(value=value):
                s=body_snapshot('# Goal\nx\n# Dependencies\n'+value);p=build_plan(s);c=p['candidates']['issue:8']
                self.assertEqual([h['target'] for h in c['dependency_hints']],[target])
                self.assertEqual(c['dependencies'],[])
                self.assertEqual(recheck(s,p,'issue:8',s)['status'],'BLOCKED')
                if target=='#999': self.assertEqual(c['dependency_hints'][0]['state'],'UNFETCHED')
                else: self.assertIn(c['dependency_hints'][0]['head'],'\n'.join(c['steps']))

    def test_related_pr_requires_body_relation_not_inline_or_comment_example(self):
        s=dependency_snapshot();items=copy.deepcopy(s['items']);pr=items['pr:40']
        pr['body']='Example: `Refs #35`';pr['raw']['detail']['body']=pr['body']
        pr['raw']['comments']=[{'body':'Refs #35'}];pr['raw']['detail']['comments']=1
        pr['hash']=digest(pr['raw'])
        hint=build_plan(seal(items,s['coverage']))['candidates']['issue:8']['dependency_hints'][0]
        self.assertEqual(hint['related_prs'],[])

    def test_closing_has_its_own_evidence_and_mentions_are_not_refs(self):
        for body in ('Related to #35', 'Example: Refs #35', 'Refs #35'):
            s=dependency_snapshot();items=copy.deepcopy(s['items']);pr=items['pr:40']
            pr['body']=body;pr['raw']['detail']['body']=body;pr['hash']=digest(pr['raw'])
            hint=build_plan(seal(items,s['coverage']))['candidates']['issue:8']['dependency_hints'][0]
            self.assertEqual(bool(hint['related_prs']),body=='Refs #35')
        pr['body']='Implementation';pr['raw']['detail']['body']=pr['body']
        pr['raw']['closing']=[{'number':35,'repository':{'nameWithOwner':'second-works/hermes-self-improvement'}}]
        pr['hash']=digest(pr['raw'])
        c=build_plan(seal(items,s['coverage']))['candidates']['issue:8'];related=c['dependency_hints'][0]['related_prs'][0]
        self.assertEqual(related['relation'],'closing')
        quote=next(e['quote'] for e in c['evidence'] if e['id']==related['evidence'])
        self.assertEqual(json.loads(quote),pr['raw']['closing'][0])

    def test_conflicting_and_multiple_references_are_held_without_graph_edges(self):
        s=body_snapshot('# Goal\nx\n# Dependencies\nDepends on: #35, PR #40（条件）\n# 依存\nなし')
        p=build_plan(s);c=p['candidates']['issue:8']
        self.assertEqual([h['target'] for h in c['dependency_hints']],['issue:35','pr:40'])
        self.assertEqual(c['dependencies'],[])
        self.assertTrue(any(h['code']=='dependency_multiple' for h in c['holds']))
        self.assertEqual(recheck(s,p,'issue:8',s)['status'],'BLOCKED')

    def test_new_hints_do_not_clear_holds_or_hide_changes_or_reuse_old_plan(self):
        s=dependency_snapshot();p=build_plan(s)
        self.assertEqual(recheck(s,p,'issue:8',s)['status'],'BLOCKED')
        for version in (2,3):
            old=copy.deepcopy(p);old['version']=version
            with self.assertRaises(Invalid): validate_plan(s,old)
        items=copy.deepcopy(s['items']);dep=items['issue:35']
        dep['state']='OPEN';dep['raw']['detail']['state']='open';dep['hash']=digest(dep['raw'])
        self.assertEqual(recheck(s,p,'issue:8',seal(items,s['coverage']))['status'],'STALE')


if __name__=='__main__': unittest.main()
