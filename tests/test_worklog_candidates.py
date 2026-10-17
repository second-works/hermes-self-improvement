"""Evidence, source boundaries, chronology, transport refusal, and CLI integration."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worklog_candidates.core import (ContractError, canonical, decode, digest,
                                    load_snapshot, parse_records, read_relative)
from worklog_candidates.evaluation import evaluate
from worklog_candidates.report import (make_report, markdown, packets, safe_text,
                                      validate_response, write_output)
FIX = ROOT / 'fixtures/worklog_candidates'


def snapshot():
    return load_snapshot(FIX, 'manifest.json')


def response(s):
    # Transport stub only: not used to measure classifier quality.
    return {'schema_version': 1, 'decisions': [
        {'candidate_id': c['candidate_id'], 'state': 'hold', 'reason': 'insufficient_context',
         'evidence_ids': [c['records'][0].record_id]} for c in s['candidates']]}


class Contracts(unittest.TestCase):
    def test_independent_twenty_scenarios_and_baseline_errors(self):
        s = snapshot()
        gold = decode((FIX / 'gold.json').read_bytes())
        self.assertEqual(len({c['scenario_id'] for c in gold['cases']}), 20)
        self.assertEqual(len({c['scenario_id'] for c in gold['cases'] if c['split'] == 'development'}), 10)
        report = make_report(s)
        metrics = evaluate(report, gold, s['sources'])
        self.assertEqual(metrics['splits']['all']['correct_states'], 18)
        self.assertEqual(metrics['splits']['all']['active_false_negative'], 2)
        self.assertEqual(metrics['splits']['all']['resolved_false_positive'], 1)
        self.assertEqual(metrics['duplicates'], 0)
        self.assertFalse(metrics['model_accuracy_measured'])
        known = {r.record_id for c in s['candidates'] for r in c['records']}
        for case in gold['cases']:
            for ref in case['evidence']:
                self.assertTrue(set(ref['record_ids']).issubset(known))

    def test_malformed_gold_is_rejected_without_entering_classifier(self):
        good=decode((FIX/'gold.json').read_bytes())
        for key,val in [('task_id',[]),('state',[]),('evidence',[{}])]:
            bad=deepcopy(good);bad['cases'][0][key]=val
            with self.assertRaises(ContractError):evaluate(make_report(snapshot()),bad,snapshot()['sources'])

    def test_source_spans_and_ids_independently_match_physical_bytes(self):
        for candidate in snapshot()['candidates']:
            for r in candidate['records']:
                raw = (FIX / r.path).read_bytes()
                self.assertEqual(r.file_sha256, hashlib.sha256(raw).hexdigest())
                lines = raw.decode().split('\n')
                self.assertEqual(r.text, '\n'.join(lines[r.line_start-1:r.line_end]))
                source = 's-' + hashlib.sha256(canonical([r.path, r.file_sha256])).hexdigest()
                self.assertEqual(source, r.source_id)
                self.assertEqual(r.record_id, 'r-' + hashlib.sha256(canonical([source, r.line_start, r.line_end])).hexdigest())

    def test_chronology_resolution_reopen_duplicates_and_other_task(self):
        rows = {(r['scenario_id'], r['task_id']):r for r in make_report(snapshot())['candidates']}
        for scenario, state in [(8,'resolved_in_log'),(11,'resolved_in_log'),(12,'needs_check'),
                                (13,'needs_check'),(14,'awaiting_approval'),(15,'needs_check')]:
            self.assertEqual(rows[f'scenario-{scenario:02}', 'task-a']['state'],state)
        self.assertEqual(rows['scenario-16','task-b']['state'], 'resolved_in_log')
        self.assertNotEqual(rows['scenario-16','task-a']['state'], 'resolved_in_log')
        self.assertEqual(len(rows['scenario-13','task-a']['references']), 2)

    def test_no_gold_in_packets_and_no_calls_or_commands_in_classification(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('command')):
            s = snapshot()
            before = packets(s)
            make_report(s)
        self.assertEqual(before, packets(s))
        self.assertNotIn('gold', canonical(before).decode())
        self.assertNotIn('state', before['packets'][0])
        self.assertNotIn('sources', before)
        self.assertNotIn('sources', make_report(s))

    def test_bad_json_never_repaired(self):
        for raw in [b'```json\n{}\n```', b'{"x":1,"x":2}', b'{"x":NaN}', b'{', b'\xff']:
            with self.subTest(raw=raw):
                with self.assertRaises(ContractError): decode(raw)
                report = make_report(snapshot(), raw)
                self.assertEqual(report['status'], 'PARTIAL')
                self.assertTrue(all(r['state']=='hold' and r['reason']=='invalid_response' for r in report['candidates']))

    def test_response_membership_fields_pairing_and_duplicate_ids(self):
        s = snapshot()
        good = response(s)
        self.assertEqual(len(validate_response(s,canonical(good))),21)
        mutations = []
        for field,value in [('candidate_id','c-'+'0'*64),('state','done'),('reason','linked_success'),
                            ('evidence_ids',[]),('evidence_ids',['r-'+'0'*64]),('extra','text')]:
            bad=deepcopy(good);bad['decisions'][0][field]=value;mutations.append(bad)
        bad=deepcopy(good);bad['decisions'][0]['evidence_ids']=[s['candidates'][1]['records'][0].record_id];mutations.append(bad)
        bad=deepcopy(good);bad['decisions'].append(bad['decisions'][0]);mutations.append(bad)
        bad=deepcopy(good);bad['decisions'][0]['evidence_ids']*=2;mutations.append(bad)
        bad=deepcopy(good);bad['schema_version']=True;mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad):
                with self.assertRaises(ContractError): validate_response(s,canonical(bad))

    def test_missing_response_keeps_every_candidate(self):
        report=make_report(snapshot(),(FIX/'responses/partial.json').read_bytes())
        self.assertEqual(len(report['candidates']),21)
        self.assertEqual(report['coverage']['incomplete'],20)
        self.assertEqual(report['status'],'PARTIAL')

    def test_complete_mock_response_is_not_semantic_success(self):
        s=snapshot(); report=make_report(s,canonical(response(s)))
        self.assertEqual(report['status'],'COMPLETE')
        self.assertEqual(report['mode'],'mock-selection')
        metrics=evaluate(report,decode((FIX/'gold.json').read_bytes()),s['sources'])
        self.assertFalse(metrics['model_accuracy_measured'])
        self.assertGreater(metrics['splits']['all']['active_false_negative'],0)
        self.assertEqual(metrics['semantic_entailment'],'HUMAN_REVIEW_REQUIRED')

    def test_reexecution_stable_and_original_unchanged(self):
        before={p:digest(p.read_bytes()) for p in FIX.rglob('*') if p.is_file()}
        self.assertEqual(canonical(make_report(snapshot())),canonical(make_report(snapshot())))
        self.assertEqual(before,{p:digest(p.read_bytes()) for p in before})

    def test_fenced_headings_not_claims_and_unclosed_fence_partial(self):
        e=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        records,unsupported=parse_records(e,b'# title\n\n```md\n## fake heading\ntext\n```\n')
        self.assertEqual(len(records),1);self.assertEqual(records[0].kind,'code')
        self.assertFalse(unsupported)
        records,unsupported=parse_records(e,b'# title\n\n```\ntext\n')
        self.assertTrue(unsupported)
        s=snapshot();s['candidates'][0]['unsupported']=True
        self.assertEqual(make_report(s,canonical(response(s)))['status'],'PARTIAL')

    def test_quote_and_indented_code_without_blank_do_not_resolve_task(self):
        e=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        from worklog_candidates.core import baseline
        for tail in ('> 修正後の再テスト成功。','    修正後の再テスト成功。'):
            records,unsupported=parse_records(e,('テスト失敗。\n'+tail+'\n').encode())
            self.assertEqual(len(records),2)
            candidate=dict(records=records,unsupported=unsupported)
            self.assertEqual(baseline(candidate)[0],'needs_check')

    def test_heading_only_and_oversized_paragraph_not_silent(self):
        e=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        r,u=parse_records(e,b'# title\n')
        self.assertTrue(u);self.assertEqual(r[0].line_end,1)
        with self.assertRaisesRegex(ContractError,'RECORD_LIMIT'):
            parse_records(e,b'x'*8193)

    def test_path_traversal_symlink_fifo_and_file_size(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'real').write_bytes(b'x')
            (root/'alias').symlink_to(root/'real')
            (root/'diralias').symlink_to(root,target_is_directory=True)
            os.mkfifo(root/'pipe')
            for path in ['../secret','/etc/passwd','a/../real','./real','alias','diralias/real','pipe']:
                with self.subTest(path=path):
                    with self.assertRaises((ContractError,OSError)):read_relative(root,path)
            with self.assertRaisesRegex(ContractError,'FILE_BOUNDARY'):read_relative(root,'real',0)
            self.assertEqual(read_relative(root,'real'),b'x')

    def test_manifest_hash_classification_and_limits(self):
        original=decode((FIX/'manifest.json').read_bytes())
        changes=[('classification','CONFIDENTIAL'),('source_kind','real-log'),('schema_version',True),('files',[])]
        for key,val in changes:
            with tempfile.TemporaryDirectory() as name:
                root=Path(name).resolve();bad=deepcopy(original);bad[key]=val
                (root/'manifest.json').write_bytes(canonical(bad))
                with self.assertRaises(ContractError):load_snapshot(root,'manifest.json')
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'logs').mkdir();(root/'logs/a.md').write_bytes(b'new')
            e=deepcopy(original['files'][0]);e['path']='logs/a.md'
            original['files']=[e];(root/'manifest.json').write_bytes(canonical(original))
            with self.assertRaisesRegex(ContractError,'SOURCE_HASH'):load_snapshot(root,'manifest.json')

    def test_same_time_conflict_is_held_not_filename_ordered(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'logs').mkdir();files=[]
            for path,text in [('logs/a.md','結果は未確認。'),('logs/b.md','# title\n\n修正後の再テスト成功。')]:
                raw=text.encode();(root/path).write_bytes(raw)
                files.append(dict(path=path,sha256=digest(raw),session_id='session',task_id='task',scenario_id='scenario',sequence=0))
            m=dict(schema_version=1,classification='PUBLIC',source_kind='synthetic-fixture',files=files)
            (root/'manifest.json').write_bytes(canonical(m))
            row=make_report(load_snapshot(root,'manifest.json'))['candidates'][0]
            self.assertEqual(row['state'],'hold')

    def test_output_create_only_and_source_derived_escaped_markdown(self):
        report=make_report(snapshot())
        with tempfile.TemporaryDirectory() as name:
            dest=Path(name).resolve()/'report'
            write_output(dest,report)
            self.assertEqual(json.loads((dest/'report.json').read_bytes()),report)
            self.assertIn('行', (dest/'report.md').read_text())
            before=digest((dest/'report.json').read_bytes())
            with self.assertRaises(FileExistsError):write_output(dest,report)
            self.assertEqual(before,digest((dest/'report.json').read_bytes()))
            alias=dest.parent/'link';alias.symlink_to(dest,target_is_directory=True)
            with self.assertRaises(OSError):write_output(alias/'new',report)
        rendered=safe_text('[click](https://example.invalid) <script>\x1b\u202e')
        self.assertNotIn('<script>',rendered);self.assertNotIn('\x1b',rendered)
        self.assertIn('\\[click\\]',rendered)
        self.assertIn('現在のGitHub',markdown(report))

    def test_indented_and_empty_atx_headings_are_not_claims(self):
        from worklog_candidates.core import baseline
        e=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        for raw in (b'#',b'###   ', '   # 結果は未確認。\n'.encode(), '  #### 修正後の再テスト成功。\n'.encode()):
            records,unsupported=parse_records(e,raw)
            self.assertTrue(unsupported)
            self.assertEqual(baseline(dict(records=records,unsupported=unsupported)),('hold','unsupported_format'))

    def test_gold_reference_binds_text_ids_and_line_end(self):
        original=decode((FIX/'gold.json').read_bytes())
        report=make_report(snapshot())
        for field,value in [('text','架空の成功文。'),('record_ids',['r-'+'0'*64]),
                            ('record_ids',original['cases'][1]['evidence'][0]['record_ids']),
                            ('path',original['cases'][1]['evidence'][0]['path']),('line_end',4)]:
            bad=deepcopy(original);bad['cases'][0]['evidence'][0][field]=value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ContractError,'GOLD_SOURCE_MISMATCH'):
                    evaluate(report,bad,snapshot()['sources'])

    def test_crlf_and_setext_headings_do_not_become_claims(self):
        e=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        for raw in (b'#\r\n', '結果は未確認。\n---\n'.encode(), '結果は未確認。\n===\n'.encode()):
            with self.subTest(raw=raw):
                records,unsupported=parse_records(e,raw)
                self.assertTrue(unsupported)

    def test_gold_cannot_replace_discarded_heading_with_blank(self):
        from worklog_candidates.evaluation import bind_reference
        data='テスト失敗。\n# real heading\n修正後の再テスト成功。'.encode()
        e=dict(path='logs/a.md',sha256=digest(data),sequence=0)
        records,_=parse_records(e,data)
        refs=[r.__dict__ for r in records]
        gold=dict(path=e['path'],line_start=1,line_end=3,text='テスト失敗。\n\n修正後の再テスト成功。',record_ids=[r.record_id for r in records])
        with self.assertRaisesRegex(ContractError,'GOLD_SOURCE_MISMATCH'):
            bind_reference(gold,refs,{e['path']:data})
        gold['text']=data.decode()
        bind_reference(gold,refs,{e['path']:data})

    def test_nul_paths_are_fixed_contract_errors(self):
        with self.assertRaisesRegex(ContractError,'PATH_BOUNDARY'):
            read_relative(FIX,'logs/bad\x00.md')
        with self.assertRaisesRegex(ContractError,'OUTPUT_PATH'):
            write_output('/private/tmp/bad\x00',make_report(snapshot()))

    def test_source_utf8_record_count_and_total_limits(self):
        entry=dict(path='logs/a.md',sha256='0'*64,sequence=0)
        with self.assertRaisesRegex(ContractError,'SOURCE_ENCODING'):
            parse_records(entry,b'\xff')
        with patch('worklog_candidates.core.MAX_TOTAL',1):
            with self.assertRaisesRegex(ContractError,'TOTAL_LIMIT'):snapshot()
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'logs').mkdir()
            raw=('x\n\n'*129).encode();(root/'logs/a.md').write_bytes(raw)
            row=dict(path='logs/a.md',sha256=digest(raw),session_id='session',task_id='task',scenario_id='scenario',sequence=0)
            manifest=dict(schema_version=1,classification='PUBLIC',source_kind='synthetic-fixture',files=[row])
            (root/'manifest.json').write_bytes(canonical(manifest))
            with self.assertRaisesRegex(ContractError,'RECORD_COUNT'):load_snapshot(root,'manifest.json')

    def test_old_file_reoutput_after_success_does_not_reopen(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'logs').mkdir();files=[]
            for number,text in enumerate(('テスト失敗。','修正後の再テスト成功。','テスト失敗。')):
                raw=text.encode();path=f'logs/{number}.md';(root/path).write_bytes(raw)
                files.append(dict(path=path,sha256=digest(raw),session_id='session',task_id='task',scenario_id='scenario',sequence=number))
            manifest=dict(schema_version=1,classification='PUBLIC',source_kind='synthetic-fixture',files=files)
            (root/'manifest.json').write_bytes(canonical(manifest))
            row=make_report(load_snapshot(root,'manifest.json'))['candidates'][0]
            self.assertEqual(row['state'],'resolved_in_log')
            self.assertEqual(len(row['references']),3)

    def test_same_words_different_session_remain_separate(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();(root/'logs').mkdir();files=[]
            for index, session in enumerate(('session-a','session-b')):
                raw='結果は未確認。'.encode();path=f'logs/{index}.md';(root/path).write_bytes(raw)
                files.append(dict(path=path,sha256=digest(raw),session_id=session,task_id='task',scenario_id='scenario',sequence=0))
            manifest=dict(schema_version=1,classification='PUBLIC',source_kind='synthetic-fixture',files=files)
            (root/'manifest.json').write_bytes(canonical(manifest))
            self.assertEqual(len(make_report(load_snapshot(root,'manifest.json'))['candidates']),2)

    def test_cli_rules_mock_and_safe_error_diagnostics(self):
        cli=[sys.executable,'-I','-B',str(ROOT/'scripts/report_worklog_candidates.py')]
        r=subprocess.run(cli+['--evaluate'],capture_output=True,check=True)
        report=json.loads(r.stdout);self.assertEqual(report['model_calls'],0)
        self.assertEqual(report['evaluation']['splits']['all']['cases'],21)
        r=subprocess.run(cli+['--responses','responses/complete.json'],capture_output=True,check=True)
        self.assertEqual(json.loads(r.stdout)['status'],'COMPLETE')
        for args in [['--responses','responses/invalid.json'],['--responses','responses/partial.json']]:
            r=subprocess.run(cli+args,capture_output=True)
            self.assertEqual(r.returncode,2);self.assertEqual(json.loads(r.stdout)['status'],'PARTIAL')
        r=subprocess.run(cli+['--manifest','../private.json'],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertNotIn(b'private.json',r.stderr)


if __name__=='__main__':unittest.main()
