"""Bounded PUBLIC semantic trials with simulated transport and no credentials."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from evaluation.core import EvaluationError,canonical,digest
from evaluation.semantic import Budget,ROLES,TRIALS,observation,verdict
import evaluate_skill_semantics as semantic
import evaluate_skill_candidate as profiles
import run_public_hermes as generation
import run_mock_improvement as intake


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.area=Path(self.temp.name)
        self.value={'event_id':'a'*64,'trials':[{**t,'prompt_hash':digest(canonical(t))} for t in TRIALS]}
        self.budget=Budget(self.area,self.value);self.budget.begin('b'*64)

    def test_generation_plus_nine_never_exceeds_ten_or_three_per_role(self):
        for i in range(9):self.budget.reserve(i,'hermes-eval-'+f'{i:032x}')
        intents=self.budget.intents()
        self.assertEqual(1+len(intents),10)
        for role in ROLES:self.assertEqual(sum(i['role']==role for i in intents),3)
        for index in (9,0,True,-1):
            with self.assertRaises(EvaluationError):self.budget.reserve(index,'hermes-eval-'+'c'*32)
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_ALREADY_STARTED'):
            Budget(self.area,self.value).begin('c'*64)
        altered={**self.value,'event_id':'d'*64}
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_ALREADY_STARTED'):
            Budget(self.area,altered).begin('c'*64)

    def test_failed_intent_cannot_be_reused_or_skipped(self):
        self.budget.reserve(0,'hermes-eval-'+'a'*32)
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_REPLAY_OR_ORDER'):
            self.budget.reserve(0,'hermes-eval-'+'b'*32)
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_CONTAINER_REUSE'):
            self.budget.reserve(1,'hermes-eval-'+'a'*32)
        self.budget.reserve(1,'hermes-eval-'+'b'*32)
        (self.area/'intent-00.json').unlink()
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_BUDGET_GAP'):self.budget.intents()

    def test_intent_and_start_substitution_is_refused(self):
        self.budget.reserve(0,'hermes-eval-'+'a'*32)
        p=self.area/'intent-00.json';v=json.loads(p.read_text());v['prompt_hash']='f'*64;p.write_text(json.dumps(v))
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_INTENT_CHANGED'):self.budget.intents()

    def test_parser_and_verdict_do_not_accept_structure_or_self_scores(self):
        expected={'counts':{'build':{'ok':2,'failed':0}}}
        good=observation(json.dumps(expected),expected,1)
        bad=observation('{"counts":{}}',expected,1)
        control=observation('DEGRADED_CONTROL',expected,1)
        records={'baseline':[deepcopy(bad) for _ in range(3)],'candidate':[deepcopy(good) for _ in range(3)],
                 'degraded':[deepcopy(control) for _ in range(3)]}
        self.assertEqual(verdict(records)['state'],'AWAITING_HUMAN_APPROVAL')
        records['candidate']=[deepcopy(bad) for _ in range(3)]
        self.assertEqual(verdict(records)['state'],'HOLD')
        records['candidate']=[deepcopy(good) for _ in range(3)]
        records['candidate'][1]=bad
        self.assertEqual(verdict(records)['state'],'HOLD')
        records['candidate']=[deepcopy(good) for _ in range(3)]
        records['degraded']=[deepcopy(good) for _ in range(3)]
        self.assertEqual(verdict(records)['state'],'HOLD')
        self.assertFalse(observation(json.dumps({**expected,'self_score':100}),expected,1)['correct'])
        self.assertFalse(observation('{"counts":{"build":{"ok":true,"failed":0}}}',expected,1)['correct'])


class SemanticCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        for obj,name,value in [(semantic,'ROOT',self.root),(semantic,'STATE',self.root/'runs/semantic-evaluation'),
                               (profiles,'ROOT',self.root),(profiles,'STATE',self.root/'runs/profile-evaluation'),
                               (profiles.gate,'RUNS',self.root/'runs'),(generation,'ROOT',self.root)]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.event='a'*64
        self.work=self.root/'runs/evaluation-20261107T000000Z-aaaaaaaaaaaa';self.work.mkdir(parents=True)
        (self.work/'profile-manifest.json').write_text('{}')
        self.source_report={'event_id':self.event,'candidate_sha':'b'*40,'baseline_sha':'c'*40,'profile_hash':'d'*64,'machine_seconds':1}
        self.m={'entry':{'event_id':self.event,'head_sha':'c'*40}}
        self.skills={'baseline':'BASELINE_RULE','candidate':'CANDIDATE_RULE','degraded':semantic.DEGRADED}
        self.case={'stdin':'{"events":[{"category":"build","status":"ok"},{"category":"build","status":"ok"}]}',
                   'expected':{'counts':{'build':{'ok':2,'failed':0}}},'exit':0}
        self.raw=canonical({'PUBLIC':'synthetic proposal'})
        self.source=lambda *args:(self.work,self.m,self.source_report,{'report_hash':'e'*64},self.skills,self.case)
        p=patch.object(semantic,'source',side_effect=self.source);p.start();self.addCleanup(p.stop)
        p=patch.object(profiles.gate,'source_hashes',return_value={'public_source':'f'*64});p.start();self.addCleanup(p.stop)
        memory={'schema_version':1,'run_id':self.work.name,'recorded_at':'2026-11-07T00:00:00Z',
                'classification':'PUBLIC','iteration':1,'baseline':{'commit_sha':'c'*40,'artifact_sha256':'d'*64},
                'candidate':{'commit_sha':'b'*40,'artifact_sha256':'e'*64},'metrics':{},
                'approval':{'status':'NOT_REQUESTED','record_sha256':None},
                'rollback':{'status':'NOT_REQUESTED','record_sha256':None}}
        (self.work/'profile-memory.json').write_bytes(canonical(memory))
        self.plan=semantic.prepare(self.work.name,self.raw)['plan']
        self.approval=self.root/'approval.json';self.write_approval()
        self.seen=[]
        self.counter=0

    def write_approval(self,**changes):
        self.approval.write_bytes(canonical({**self.plan,'expires_at':int(time.time())+300,**changes}))
        self.approval.chmod(0o600)

    def clock(self):
        self.counter+=1
        return self.counter*0.01

    def transport(self,root,data,work,deadline,name):
        payload=json.loads(data)
        self.assertFalse(payload['offline_test'])
        self.assertEqual(payload['auth'],{'synthetic':True})
        self.seen.append((payload['prompt'],name))
        answer=json.dumps(self.case['expected']) if 'CANDIDATE_RULE' in payload['prompt'] else '{"counts":{}}'
        if semantic.DEGRADED in payload['prompt']:answer='DEGRADED_CONTROL'
        return canonical({'status':'COMPLETED','requests':1,'tools':0,'text':answer})

    def run_campaign(self,transport=None):
        with patch.object(generation,'read_auth',return_value={'synthetic':True}):
            return semantic.run(self.event,self.approval,transport=transport or self.transport,clock=self.clock)

    def test_nine_independent_trials_stop_at_audited_approval_pending(self):
        result=self.run_campaign()
        self.assertEqual(result['state'],'AWAITING_HUMAN_APPROVAL')
        self.assertEqual(len(self.seen),9)
        self.assertEqual(len({name for _,name in self.seen}),9)
        for role in ('BASELINE_RULE','CANDIDATE_RULE',semantic.DEGRADED):
            self.assertEqual(sum(role in text for text,_ in self.seen),3)
        self.assertEqual(semantic.audit(self.event)['requests_reserved'],10)
        memory=json.loads((semantic.area(self.event)/'memory.json').read_text())
        self.assertEqual(memory['approval']['status'],'PENDING')
        self.assertEqual(memory['rollback']['status'],'NOT_REQUESTED')
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_ALREADY_STARTED'):self.run_campaign()
        self.assertEqual(len(self.seen),9)

    def test_approval_mismatch_or_expiry_never_reads_auth(self):
        for changes in ({'max_total_requests':11},{'max_retries':True},{'additional_cost_yen':1},
                        {'candidate_sha':'f'*40},{'expires_at':int(time.time())-1}):
            self.write_approval(**changes)
            with patch.object(generation,'read_auth') as auth:
                with self.assertRaises(EvaluationError):semantic.run(self.event,self.approval,transport=self.transport)
                auth.assert_not_called()
        self.assertFalse((semantic.area(self.event)/'started.json').exists())

    def test_source_and_input_substitution_is_refused(self):
        path=semantic.area(self.event)/'case.private.json'
        changed=deepcopy(self.case);changed['stdin']='{}';path.write_bytes(canonical(changed))
        with patch.object(generation,'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError,'SEMANTIC_CASE_CHANGED'):
                semantic.run(self.event,self.approval,transport=self.transport)
            auth.assert_not_called()

    def test_trusted_code_change_is_refused_before_credentials(self):
        with patch.object(profiles.gate,'source_hashes',return_value={'public_source':'0'*64}), \
             patch.object(generation,'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError,'SEMANTIC_STALE'):
                semantic.run(self.event,self.approval,transport=self.transport)
            auth.assert_not_called()

    def test_event_copy_cannot_create_another_budget_for_same_generation(self):
        import shutil
        other='b'*64
        copied=semantic.STATE/other
        shutil.copytree(semantic.area(self.event),copied)
        path=copied/'manifest.json';value=json.loads(path.read_text());value['event_id']=other
        path.write_bytes(canonical(value))
        with patch.object(generation,'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError,'SEMANTIC_SOURCE_CHANGED'):
                semantic.send_plan(other)
            auth.assert_not_called()

    def test_quota_failure_consumes_intent_without_retry(self):
        calls=[]
        def quota(*args):
            calls.append(1)
            return canonical({'status':'QUOTA_EXHAUSTED'})
        result=self.run_campaign(quota)
        self.assertEqual(result['state'],'STOPPED')
        self.assertEqual(result['reason'],'QUOTA_EXHAUSTED')
        self.assertEqual(result['evaluation_attempts'],1)
        self.assertEqual(len(calls),1)
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_ALREADY_STARTED'):self.run_campaign()

    def test_auth_failure_never_refreshes_or_retries(self):
        calls=[]
        def invalid(*args):
            calls.append(1);return canonical({'status':'AUTH_FAILED'})
        result=self.run_campaign(invalid)
        self.assertEqual(result['state'],'STOPPED')
        self.assertEqual(result['reason'],'AUTH_FAILED')
        self.assertEqual(result['evaluation_attempts'],1)
        self.assertEqual(len(calls),1)

    def test_approval_substitution_after_one_trial_stops_before_second_read(self):
        def changed(*args):
            result=self.transport(*args)
            self.write_approval(expires_at=int(time.time())+600)
            return result
        with patch.object(generation,'read_auth',return_value={'synthetic':True}) as auth:
            result=semantic.run(self.event,self.approval,transport=changed,clock=self.clock)
        self.assertEqual(result['state'],'STOPPED')
        self.assertEqual(result['reason'],'APPROVAL_CHANGED')
        self.assertEqual(result['evaluation_attempts'],1)
        self.assertEqual(auth.call_count,1)

    def test_unconfirmed_cleanup_blocks_resume_and_new_generation(self):
        error=EvaluationError('ISOLATION_CLEANUP_FAILED');error.pending_container='hermes-eval-'+'f'*32
        def broken(*_):raise error
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_RECOVERY_REQUIRED'):self.run_campaign(broken)
        self.assertTrue((semantic.STATE/'pending.json').exists())
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_RECOVERY_REQUIRED'):generation.reject_profile_pending()
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_RECOVERY_REQUIRED'):self.run_campaign()

    def test_interrupt_verifies_intent_config_and_kills_inspected_id(self):
        box=Mock()
        box.container_exists.return_value=True
        box.inspect.return_value={'State':{'Running':True},'Id':'f'*64}
        def stopped(*args):
            with patch.object(semantic.hermes_cloud,'CloudSandbox',return_value=box):
                semantic.interrupt()
            (self.root/'runs/public-hermes/intake-stop.json').write_bytes(canonical({'status':'STOP_REQUESTED'}))
            return self.transport(*args)
        result=self.run_campaign(stopped)
        self.assertEqual(result['state'],'STOPPED')
        box.verify_config.assert_called_once_with(box.inspect.return_value,self.root/semantic.hermes_cloud.WORKER_PATH)
        box.checked.assert_called_once_with('kill','f'*64,timeout=5)

    def test_stop_checks_semantic_cleanup_after_controller_has_exited(self):
        error=EvaluationError('ISOLATION_CLEANUP_FAILED');error.pending_container='hermes-eval-'+'f'*32
        def broken(*_):raise error
        with self.assertRaisesRegex(EvaluationError,'SEMANTIC_RECOVERY_REQUIRED'):self.run_campaign(broken)
        pending=semantic.STATE/'pending.json'
        original=pending.read_bytes()
        state=self.root/'runs/public-hermes'
        box=Mock()
        box.container_exists.return_value=True
        box.inspect.return_value={'State':{'Running':True},'Id':'f'*64}
        with patch.object(intake,'ROOT',self.root),patch.object(semantic.hermes_cloud,'CloudSandbox',return_value=box):
            with self.assertRaisesRegex(EvaluationError,'SEMANTIC_RECOVERY_REQUIRED'):
                intake.control_intake(state,'stop')
        box.verify_config.assert_called_once_with(box.inspect.return_value,self.root/semantic.hermes_cloud.WORKER_PATH)
        box.checked.assert_called_once_with('kill','f'*64,timeout=5)
        self.assertEqual(pending.read_bytes(),original)
        self.assertEqual(json.loads((state/'intake-stop.json').read_text()),intake.STOP_RECORD)
        # Unknown identity/configuration must fail before any kill or success response.
        box.reset_mock();box.verify_config.side_effect=EvaluationError('CONTAINER_CONFIG')
        with patch.object(intake,'ROOT',self.root),patch.object(semantic.hermes_cloud,'CloudSandbox',return_value=box):
            with self.assertRaisesRegex(EvaluationError,'CONTAINER_CONFIG'):
                intake.control_intake(state,'stop')
        box.checked.assert_not_called()
        self.assertEqual(pending.read_bytes(),original)

    def test_stop_rejects_corrupt_semantic_pending_with_free_lock(self):
        (semantic.STATE/'pending.json').write_text('{}')
        state=self.root/'runs/public-hermes'
        with patch.object(intake,'ROOT',self.root),patch.object(semantic.hermes_cloud,'CloudSandbox') as box:
            with self.assertRaisesRegex(EvaluationError,'SEMANTIC_PENDING'):
                intake.control_intake(state,'stop')
        box.assert_not_called()
        self.assertTrue((state/'intake-stop.json').exists())

    def test_stop_without_semantic_pending_still_succeeds(self):
        with patch.object(intake,'ROOT',self.root):
            self.assertEqual(intake.control_intake(self.root/'runs/public-hermes','stop'),'INTAKE_STOPPED')

    def test_late_stop_never_becomes_approval_pending(self):
        def last(*args):
            answer=self.transport(*args)
            if len(self.seen)==9:
                (self.root/'runs/public-hermes/intake-stop.json').write_bytes(canonical({'status':'STOP_REQUESTED'}))
            return answer
        result=self.run_campaign(last)
        self.assertEqual(result['state'],'STOPPED')
        self.assertEqual(result['reason'],'INTAKE_STOPPED')
        self.assertEqual(result['evaluation_attempts'],9)
        memory=json.loads((semantic.area(self.event)/'memory.json').read_text())
        self.assertEqual(memory['approval']['status'],'NOT_REQUESTED')


if __name__=='__main__':unittest.main()
