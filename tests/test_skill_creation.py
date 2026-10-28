"""Tests exercise real freeze/audit bindings with inert candidate and mocked containers."""
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from delegation.skill_creation import Controller,FILES,SKILL,PROGRAM,CASES,request,observe
from delegation.generated import git
from evaluation.core import EvaluationError,canonical,digest,write_new


class ContractTests(unittest.TestCase):
    def test_untrusted_requests_cannot_define_commands(self):
        for value in [{'operation':'curl'}, {'operation':'run_aggregate','command':'anything'}, [], {'operation':None}]:
            with self.subTest(value=value), self.assertRaises(EvaluationError): request(value)
        self.assertEqual(request({'operation':'run_aggregate'}),'run_aggregate')

    def test_output_schema_exit_and_faults(self):
        base={'exit':0,'container_exit':0,'stdout':b'{"counts":{}}','stderr':b'','error':None,'oom':False}
        self.assertEqual(observe(base),{'counts':{}})
        self.assertEqual(observe(dict(base,exit=2,container_exit=2,stdout=b'{"error":"INVALID_INPUT"}')),{'error':'INVALID_INPUT'})
        for changes in [{'exit':1},{'container_exit':2},{'error':'TIMEOUT'},{'oom':True},{'stderr':b'err'},
                        {'stdout':b'[]'},{'stdout':b'{"counts":{"x":{"ok":true,"failed":0}}}'},
                        {'stdout':b'{"counts":{"A":{"ok":1,"failed":0}}}'},
                        {'stdout':b'{"counts":{"x":{"ok":-1,"failed":0}}}'}]:
            with self.subTest(changes=changes), self.assertRaises(EvaluationError): observe(dict(base,**changes))


class FrozenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        original=Controller(ROOT)
        for name in original.sources():
            target=self.root/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        (self.root/'.gitignore').write_text('runs/\n')
        git(self.root,'init','--template=','--initial-branch=test'); git(self.root,'add','.')
        git(self.root,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','test evaluator')
        self.c=Controller(self.root); self.c.runs.mkdir()
        self.work=self.c.runs/('skill-'+'c'*24); self.work.mkdir()
        self.c.save(self.c.runs,'skill-reuse.lock',{'run_id':self.work.name})
        self.c.save(self.work,'environment.json',{'mock':True})
        gate=self.c.legacy()
        self.c.save(self.work,'gate.json',{'status':'VERIFIED','sources':gate.source_hashes(),
            'environment_hash':digest((self.work/'environment.json').read_bytes()),
            'probes':{n:'VERIFIED' for n in (*gate.PROBE_FIELDS,'timeout','output')}})
        self.c.save(self.work,'budget.json',{'seconds':1,'started_at':time.time()})
        gate.event(self.work,'ENVIRONMENT_PINNED',digest((self.work/'environment.json').read_bytes()))
        gate.event(self.work,'ISOLATION_VERIFIED',digest((self.work/'gate.json').read_bytes()))
        self.c.freeze(self.work.name); self.packet=self.work/'packet'
        (self.packet/'event-status-counts/scripts').mkdir(parents=True)
        (self.packet/SKILL).write_text('---\nname: event-status-counts\ndescription: inert test\n---\n')
        (self.packet/PROGRAM).write_text('import json\n')
        self.commit()

    def commit(self):
        git(self.packet,'add','.')
        git(self.packet,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','inert candidate')
        self.sha=git(self.packet,'rev-parse','HEAD').decode().strip()

    def test_two_file_scope_and_dependencies(self):
        _,data=self.c.intake(self.work,self.sha)
        self.assertEqual(set(data),set(FILES))
        (self.packet/PROGRAM).write_text('import requests\n'); self.commit()
        with self.assertRaisesRegex(EvaluationError,'DEPENDENCY_FORBIDDEN'): self.c.intake(self.work,self.sha)
        (self.packet/PROGRAM).write_text('import json\n')
        (self.packet/'contract.json').write_bytes(b'{}'); self.commit()
        with self.assertRaisesRegex(EvaluationError,'EDIT_SCOPE'): self.c.intake(self.work,self.sha)

    def test_size_symlink_and_original_guard(self):
        (self.packet/SKILL).write_bytes(b'x'*65536); self.commit()
        with self.assertRaisesRegex(EvaluationError,'ARTIFACT_SIZE'): self.c.intake(self.work,self.sha)
        (self.packet/SKILL).unlink(); (self.packet/SKILL).symlink_to('/nonexistent'); self.commit()
        with self.assertRaisesRegex(EvaluationError,'ARTIFACT_TYPE'): self.c.intake(self.work,self.sha)

    def test_freeze_detects_source_and_dataset_mutation(self):
        source=self.root/'scripts/skill_create.py'; original=source.read_bytes(); source.write_bytes(original+b'\n# tamper\n')
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.sha)
        source.write_bytes(original)
        (self.work/'trials.private.json').write_bytes(b'[]')
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.sha)

    def accept_mock_public(self):
        _,data=self.c.intake(self.work,self.sha)
        self.c.save(self.work,'public-0.json',{'candidate_sha':self.sha,
            'artifact_hashes':{p:digest(v) for p,v in data.items()},'passed':4,'total':4,
            'seconds':.1,'cases':[{'correct':True}]*4})
        self.c.accept(self.work.name,self.sha)

    def test_accept_requires_public_result_for_same_artifact(self):
        with self.assertRaisesRegex(EvaluationError,'PUBLIC_NOT_VERIFIED'):
            self.c.accept(self.work.name,self.sha)

    def batch(self,mode='correct'):
        self.accept_mock_public()
        cases=self.c.read_json(self.work,'trials.private.json')
        lookup={r['stdin'].encode():r for row in cases for r in row.values() if r['kind']=='execution'}
        def run(program,data,**kwargs):
            row=lookup[data]
            return {'exit':row['exit'],'container_exit':row['exit'],'stdout':canonical(row['expected'])+b'\n',
                    'stderr':b'','error':None,'oom':False,'wall_seconds':.1}
        self.c.save(self.work,'sessions.json',[f'/test/fresh{i}' for i in range(3)])
        with patch('delegation.skill_creation.Sandbox') as box:
            box.return_value.run.side_effect=run
            for i,row in enumerate(cases):
                handoff=self.c.handoff(self.work.name,i)
                self.assertTrue(all(set(task)=={'id','kind','task'} for task in handoff['tasks']))
                self.assertEqual(len(handoff['tasks']),len(CASES))
                for key,case in row.items():
                    op=case['operation']
                    if mode=='routing' and key=='equivalent': op='select_create'
                    out=self.c.use(self.work.name,i,key,{'operation':op})
                    if case['kind']=='execution' and mode!='missing':
                        self.c.respond(self.work.name,i,key,out['stdout'] if mode!='changed' else '{}\n')
            self.assertEqual(box.return_value.run.call_count,27)
        if mode=='missing':
            with self.assertRaisesRegex(EvaluationError,'FINAL_RESPONSE_MISSING'): self.c.evaluate(self.work.name)
            with self.assertRaisesRegex(EvaluationError,'ASSESSMENT_OR_FAILURE'):
                self.c.respond(self.work.name,0,'empty','{}')
            return
        report=self.c.evaluate(self.work.name)
        self.assertEqual(report['status'],'PASS' if mode=='correct' else 'FAIL')
        self.assertEqual(self.c.audit(self.work.name)['audit'],'VERIFIED')
        (self.work/'0-empty.response.json').write_bytes(b'{}')
        with self.assertRaises(EvaluationError): self.c.audit(self.work.name)

    def test_real_bindings_and_complete_mock_batch(self): self.batch()
    def test_missing_final_results_cannot_pass(self): self.batch('missing')
    def test_changed_final_results_cannot_pass(self): self.batch('changed')
    def test_always_create_cannot_pass(self): self.batch('routing')

    def test_public_failure_and_one_revision_are_bounded(self):
        with patch('delegation.skill_creation.Sandbox') as box:
            box.return_value.deadline=time.monotonic()+60
            box.return_value.run.return_value={'exit':0,'container_exit':0,'stdout':b'[]',
                'stderr':b'','error':None,'oom':False}
            self.assertEqual(self.c.public(self.work.name,self.sha)['passed'],0)
            public=self.c.read_json(self.packet,'public.json')
            answers={canonical(row['input']):row for row in public}
            def result(program,data,**kwargs):
                row=answers[data]
                return {'exit':row['exit'],'container_exit':row['exit'],'stdout':canonical(row['expected']),
                        'stderr':b'','error':None,'oom':False}
            box.return_value.run.side_effect=result
            self.assertEqual(self.c.public(self.work.name,self.sha)['passed'],4)
            with self.assertRaisesRegex(EvaluationError,'PUBLIC_LIMIT'):
                self.c.public(self.work.name,self.sha)

    def test_unauthorized_execution_and_external_fetch_stop_before_container(self):
        self.accept_mock_public(); self.c.handoff(self.work.name,0)
        with patch('delegation.skill_creation.Sandbox') as box:
            with self.assertRaisesRegex(EvaluationError,'EXECUTION_NOT_ALLOWED'):
                self.c.use(self.work.name,0,'denied',{'operation':'run_aggregate'})
            box.assert_not_called()
        self.assertTrue((self.work/'active.lock').exists())
