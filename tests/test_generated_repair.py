"""Generated intake tests use inert candidate bytes and observations, never host execution."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from delegation.generated import Controller, ARTIFACT, BASELINE_HASH, artifact, cases, git
from evaluation.core import EvaluationError, canonical, digest, judge, write_new
from evaluation.generated import observe


def outcome(code=0, stdout=b'{"findings":[],"cpu_seconds":0}', **values):
    return dict({'exit': code, 'container_exit': code, 'stdout': stdout, 'stderr': b'',
                 'error': None, 'oom': False, 'wall_seconds': .1}, **values)


class ObservationTests(unittest.TestCase):
    def test_expected_rejection_and_execution_failure_are_distinct(self):
        case = {'exit': 2, 'expected': None}
        good = observe(outcome(2,b'{"error":"INVALID_INPUT"}'),case)
        self.assertTrue(good['correct'])
        self.assertFalse(good['failed'])
        for changes in [{'exit':127,'container_exit':127}, {'error':'TIMEOUT'}, {'oom':True}, {'stderr':b'explanation'}, {'container_exit':127}]:
            bad = observe(outcome(2,b'{"error":"INVALID_INPUT"}', **changes),case)
            self.assertTrue(bad['failed'])
            self.assertFalse(bad['correct'])
        for body in [b'Good job', b'{"error":"INVALID_INPUT","extra":1}', b'{"error":"INVALID_INPUT","error":"INVALID_INPUT"}']:
            self.assertFalse(observe(outcome(2,body),case)['correct'])

    def test_success_schema_and_regression(self):
        case = {'exit':0, 'expected':[]}
        self.assertTrue(observe(outcome(),case)['correct'])
        self.assertFalse(observe(outcome(2,b'{"error":"INVALID_INPUT"}'),case)['correct'])
        self.assertTrue(observe(outcome(stdout=b'{}'),case)['failed'])
        b = {'correct':[True]*10+[False]*10,'failures':0,'latency':1,'cost_usd':0}
        c = copy.deepcopy(b); c['correct'][10] = True
        self.assertEqual(judge(b,c,safety=True)['status'],'PASS')
        c['correct'][0] = False
        self.assertEqual(judge(b,c,safety=True)['status'],'FAIL')
        self.assertEqual(judge(b,{},safety=None)['status'],'HOLD')

    def test_public_packet_data_contains_no_hidden_or_solution(self):
        public=cases()
        self.assertEqual(len(public),10)
        self.assertEqual({row['exit'] for row in public},{0,2})
        text=canonical(public).decode()
        self.assertNotIn('operations',text)
        self.assertNotIn('hidden',text)
        self.assertEqual(digest((ROOT/'fixtures/generated_repair/baseline.py').read_bytes()), BASELINE_HASH)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.work=self.root/'runs/generated-test'; self.work.mkdir(parents=True)
        self.repo=self.work/'packet'; (self.repo/'scripts').mkdir(parents=True)
        self.source=(ROOT/'fixtures/generated_repair/baseline.py').read_bytes()
        (self.repo/ARTIFACT).write_bytes(self.source)
        (self.repo/'contract.json').write_bytes(b'{}')
        (self.repo/'public.json').write_bytes(b'[]')
        git(self.repo,'init','--initial-branch=generated')
        git(self.repo,'add','.')
        self.commit()
        self.base=git(self.repo,'rev-parse','HEAD').decode().strip()
        self.manifest={'baseline_sha':self.base,'baseline_hash':BASELINE_HASH,
          'git_config_hash':digest((self.repo/'.git/config').read_bytes()),
          'packet_files':{p:digest((self.repo/p).read_bytes()) for p in [ARTIFACT,'contract.json','public.json']}}
        self.c=Controller(ROOT)

    def commit(self):
        git(self.repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-am','inert test change')

    def candidate(self):
        (self.repo/ARTIFACT).write_bytes(self.source+b'\n# inert candidate; never executed\n')
        self.commit()
        return git(self.repo,'rev-parse','HEAD').decode().strip()

    def test_valid_one_artifact_descendant(self):
        sha=self.candidate()
        b,c=self.c.intake(self.work,self.manifest,sha)
        self.assertEqual(b,self.source); self.assertNotEqual(b,c)
        self.assertEqual(artifact(self.repo,sha),c)

    def test_old_sha_and_uncommitted_changes(self):
        sha=self.candidate()
        (self.repo/ARTIFACT).write_bytes(b'changed')
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.manifest,sha)
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.manifest,self.base)
        with self.assertRaises(EvaluationError): artifact(self.repo,'HEAD')

    def test_forbidden_diff(self):
        sha=self.candidate()
        (self.repo/'contract.json').write_bytes(b'{"changed":true}')
        self.commit()
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.manifest,git(self.repo,'rev-parse','HEAD').decode().strip())

    def test_symlink_and_size(self):
        sha=self.candidate()
        (self.repo/ARTIFACT).unlink()
        (self.repo/ARTIFACT).symlink_to('/nonexistent')
        with self.assertRaises((EvaluationError,OSError)): self.c.intake(self.work,self.manifest,sha)
        (self.repo/ARTIFACT).unlink(); (self.repo/ARTIFACT).write_bytes(b'x'*65537)
        self.commit()
        with self.assertRaises(EvaluationError): artifact(self.repo,git(self.repo,'rev-parse','HEAD').decode().strip())

    def test_git_configuration_tampering_and_no_overwrite(self):
        sha=self.candidate()
        with (self.repo/'.git/config').open('ab') as f: f.write(b'\n# changed\n')
        with self.assertRaises(EvaluationError): self.c.intake(self.work,self.manifest,sha)
        p=self.work/'lock'; write_new(p,b'original')
        with self.assertRaises(FileExistsError): write_new(p,b'overwrite')
        self.assertEqual(p.read_bytes(),b'original')

    def test_no_sandbox_before_freeze_and_path_validation(self):
        with patch.object(self.c.gate,'Sandbox',side_effect=AssertionError('not allowed')):
            for name in ['../bad','generated-'+('a'*24),None]:
                with self.assertRaises(EvaluationError): self.c.evaluate(name,self.base)

class FlowTests(unittest.TestCase):
    """Mock execution observations validate orchestration, not isolation or code quality."""
    def setUp(self):
        import shutil
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.c=Controller(ROOT)
        files=set(self.c.gate.SOURCES)
        for name in files:
            target=self.root/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        git(self.root,'init','--initial-branch=test')
        git(self.root,'add','.')
        git(self.root,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','test controller fixture')
        self.c=Controller(self.root)
        gate=self.c.gate
        outer=self
        class FakeBox:
            def __init__(self,root,work,image=None,**kwargs): self.image=image
            def environment(self): return {'fake':True}
            def image_info(self,image): return {'id':image}
            def run(self,program,data,**kwargs):
                if outer.fault: raise EvaluationError('TEST_EXECUTION_FAULT')
                all_cases=gate.read(outer.work,'public.json')+gate.read(outer.work,'hidden.json')
                case=next(row for row in all_cases if row['stdin'].encode()==data)
                good=program.name=='candidate.py' and not outer.degrade or case['exit']==0
                if case['exit']==2:
                    return outcome(2,b'{"error":"INVALID_INPUT"}') if good else outcome(stdout=b'')
                expected=case['expected'] if not (program.name=='degraded.py' or outer.degrade and program.name=='candidate.py') else []
                return outcome(stdout=canonical({'findings':[{'path':p,'line':n,'rule':r} for p,n,r in expected],'cpu_seconds':0}))
        def fake_gate(work):
            gate.save(work,'gate.json',{'status':'VERIFIED','sources':gate.source_hashes(),
                'environment_hash':digest((work/'environment.json').read_bytes()),
                'probes':{key:'VERIFIED' for key in (*gate.PROBE_FIELDS,'timeout','output')}})
            gate.event(work,'ISOLATION_VERIFIED',digest((work/'gate.json').read_bytes()))
        self.fault=False; self.degrade=False
        self.boxpatch=patch.object(gate,'Sandbox',FakeBox); self.boxpatch.start(); self.addCleanup(self.boxpatch.stop)
        self.gatepatch=patch.object(gate,'gate',fake_gate); self.gatepatch.start(); self.addCleanup(self.gatepatch.stop)
        self.name=self.c.prepare(); self.work=self.c.work(self.name)

    def freeze_candidate(self):
        frozen=self.c.freeze(self.name)
        repo=self.work/'packet'
        (repo/ARTIFACT).write_bytes((repo/ARTIFACT).read_bytes()+b'\n# inert observation fixture\n')
        git(repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-am','inert test')
        return git(repo,'rev-parse','HEAD').decode().strip()

    def test_freeze_compare_audit_and_reuse_rejection(self):
        sha=self.freeze_candidate()
        self.assertEqual(git(self.work/'packet','ls-files').splitlines(),[b'contract.json',b'public.json',b'scripts/review.py'])
        report=self.c.evaluate(self.name,sha)
        self.assertEqual(report['decision']['status'],'PASS')
        self.assertEqual(self.c.audit(self.name)['audit'],'VERIFIED')
        self.assertNotIn('stdin',canonical(report).decode())
        self.assertNotIn('expected',canonical(report).decode())
        with self.assertRaises(EvaluationError): self.c.evaluate(self.name,sha)
        with self.assertRaises(EvaluationError): self.c.freeze(self.name)
        with self.assertRaises(FileExistsError): self.c.prepare()
        with (self.work/'report.json').open('ab') as f: f.write(b' ')
        with self.assertRaises(EvaluationError): self.c.audit(self.name)

    def test_degraded_observations_fail(self):
        sha=self.freeze_candidate(); self.degrade=True
        self.assertEqual(self.c.evaluate(self.name,sha)['decision']['status'],'FAIL')

    def test_missing_execution_stops_preserving_lock(self):
        sha=self.freeze_candidate(); self.fault=True
        with self.assertRaises(EvaluationError): self.c.evaluate(self.name,sha)
        self.assertTrue((self.work/'stopped.json').exists())
        self.assertTrue((self.root/'runs/generated-repair.lock').exists())
        self.assertFalse((self.work/'report.json').exists())
        with self.assertRaises(EvaluationError): self.c.audit(self.name)

    def test_changed_dataset_and_source_refuse_execution(self):
        sha=self.freeze_candidate()
        (self.work/'public.json').write_bytes(b'[]')
        with self.assertRaises(EvaluationError): self.c.evaluate(self.name,sha)
        self.assertFalse((self.work/'evaluation-lock.json').exists())

    def test_missing_freeze_and_gate_and_dirty_evaluator(self):
        with self.assertRaises((EvaluationError,OSError)): self.c.evaluate(self.name,'a'*40)
        path=self.root/'src/evaluation/generated.py'
        path.write_bytes(path.read_bytes()+b'\n# changed\n')
        with self.assertRaises(EvaluationError): self.c.freeze(self.name)
        self.assertFalse((self.work/'packet').exists())


if __name__=='__main__': unittest.main()
