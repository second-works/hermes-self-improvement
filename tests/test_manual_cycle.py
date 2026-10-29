"""Real supervisor filesystem/state tests; inert bytes and fake Docker metrics.

Synthetic approvals and fake evaluation are never human acceptance evidence.
"""
from datetime import datetime, timedelta, timezone
import fcntl
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from manual_cycle.core import Cycle, EvaluatedAdoption, DECISIONS, BudgetSandbox
from adoption.core import save, read
from delegation.generated import ARTIFACT, BASELINE_HASH, Controller as Generated, git
from evaluation.core import EvaluationError, canonical, digest
from evaluation.sandbox import Sandbox


def expiry():
    return (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()


class CycleTests(unittest.TestCase):
    def test_deadline_stops_execution_but_preserves_bounded_container_cleanup(self):
        box = object.__new__(BudgetSandbox)
        box.deadline = time.monotonic() - 1
        with patch.object(Sandbox,'command',return_value={'exit':0}) as command:
            for args in [('container','ls'),('inspect','fixture'),('kill','fixture'),('rm','fixture')]:
                self.assertEqual(box.command(*args,timeout=5),{'exit':0})
            for action in ('create','start','info','image'):
                with self.assertRaises(EvaluationError): box.command(action)
            self.assertEqual(command.call_count,4)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        dep = self.repo / 'fixtures/manual_cycle'; dep.mkdir(parents=True)
        git(self.repo, 'init', '--initial-branch=fixture')
        (self.repo / 'marker').write_text('PUBLIC test only')
        git(self.repo, 'add', 'marker')
        git(self.repo, '-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','test')
        head = git(self.repo, 'rev-parse','HEAD').decode().strip()
        save(dep / 'dependency.json', {'issue':8,'product_acceptance':'ACCEPTED','merge_sha':head})
        self.c = Cycle(self.repo, 'cycle-test')
        self.c.initialize(expiry())
        self.observation = {'source_sha': head, 'correct': False, 'kind':'WRONG_REJECTION'}
        self.c.event('OBSERVED', {'observation': self.observation})

    def proposal(self, decision='REPAIR'):
        return {'decision':decision,'reason':'PUBLIC input contract rejects malformed input; baseline does not',
            'observation_hash':digest(canonical(self.observation)), 'baseline_sha':self.observation['source_sha'],
            'classification':'PUBLIC','allowlist':[ARTIFACT] if decision == 'REPAIR' else []}

    def ready(self):
        self.c.diagnose(self.proposal())
        work = self.repo / 'runs/generated-test'; packet = work / 'packet'
        (packet / 'scripts').mkdir(parents=True)
        baseline = (ROOT / 'fixtures/generated_repair/baseline.py').read_bytes()
        (packet / ARTIFACT).write_bytes(baseline)
        (packet / 'contract.json').write_text('{}')
        self.public = [{'stdin':'{}','exit':2,'expected':None}]
        save(packet / 'public.json', self.public)
        save(work / 'public.json', self.public)
        git(packet, 'init','--initial-branch=fixture'); git(packet, 'add','.')
        git(packet, '-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','baseline')
        base = git(packet,'rev-parse','HEAD').decode().strip()
        self.manifest = {'baseline_sha':base,'baseline_hash':BASELINE_HASH,
            'git_config_hash':digest((packet / '.git/config').read_bytes()),
            'packet_files':{p:digest((packet / p).read_bytes()) for p in (ARTIFACT,'contract.json','public.json')}}
        (packet / ARTIFACT).write_bytes(baseline + b'\n# inert synthetic candidate; never executed\n')
        git(packet, 'add', ARTIFACT)
        git(packet, '-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','inert')
        sha = git(packet,'rev-parse','HEAD').decode().strip()
        report = {'baseline_sha':base,'candidate_sha':sha,'manifest_hash':'a'*64,
            'artifact_hashes':{'baseline':digest(baseline),'candidate':digest((packet / ARTIFACT).read_bytes())},
            'decision':{'status':'PASS','reasons':[]},'counts':{}}
        save(work / 'report.json', report)
        g = Mock()
        g.frozen.return_value = self.manifest
        g.intake.side_effect = lambda w,m,s: Generated.intake(Generated(ROOT),w,m,s)
        g.evaluate.return_value = report
        g.audit.side_effect = lambda *_: {'report_hash':digest((work / 'report.json').read_bytes()),'manifest_hash':'a'*64}
        self.g, self.work, self.sha = g, work, sha
        self.c.event('PROPOSED', {'frozen':{'run_id':'generated-test'}})
        patcher = patch.object(Cycle, 'generated', return_value=(g, 'generated-test',work))
        patcher.start(); self.addCleanup(patcher.stop)
        return report

    def evaluated(self):
        self.ready()
        self.c.event('CANDIDATE_READY', {'public_check':{'candidate_sha':self.sha}})
        self.c.evaluate()
        self.c.submit('https://github.com/second-works/hermes-self-improvement/pull/99',
                      'b'*40,digest(canonical(self.c.adoption().packet())))

    def request(self, action='ADOPT'):
        request = self.c.request(action,expiry(),'SYNTHETIC-NOT-HUMAN')
        return request, digest(canonical(request))

    def test_no_change_reuse_and_hold_never_generate(self):
        for decision in DECISIONS:
            if decision == 'REPAIR': continue
            with self.subTest(decision=decision):
                self.c.event('OBSERVED', {})
                self.c.diagnose(self.proposal(decision))
                self.assertEqual(self.c.status()['state'],DECISIONS[decision])
                with self.assertRaises(EvaluationError): self.c.handoff()
                self.assertFalse((self.c.area / 'adoption').exists())

    def test_proposal_cannot_expand_scope_or_use_old_observation(self):
        p = self.proposal(); p['allowlist']=['../outside']
        with self.assertRaises(EvaluationError): self.c.diagnose(p)
        self.assertEqual(self.c.status()['state'],'STOPPED')

    def test_duplicate_cycle_and_concurrent_process_rejected(self):
        with self.assertRaises(FileExistsError): Cycle(self.repo,'cycle-other').initialize(expiry())
        with (self.repo / 'runs/manual-cycle.lock').open('r+') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(EvaluationError): self.c.status()

    def test_prewrite_process_interruption_never_resumes(self):
        self.c.event('BUSY',{'operation':'generation','started_monotonic':time.monotonic(),
                            'boot_epoch':time.time()-time.monotonic()})
        self.assertEqual(Cycle(self.repo,self.c.name).status()['state'],'STOPPED')
        with self.assertRaises(EvaluationError): self.c.diagnose(self.proposal())

    def test_budget_and_expiry_stop_before_generation(self):
        self.c.event('PROPOSED',{},1200)
        with self.assertRaises(EvaluationError): self.c.handoff()
        self.assertEqual(self.c.status()['state'],'STOPPED')
        self.c.event('PROPOSED',{})
        with patch('manual_cycle.core.stamp',return_value=0):
            with self.assertRaises(EvaluationError): self.c.handoff()

    def test_config_and_journal_tamper_rejected(self):
        path = self.c.area / 'config.json'
        config=read(path); config['expires_at']='2099-01-01T00:00:00Z'
        path.write_bytes(canonical(config))
        with self.assertRaises(EvaluationError): self.c.diagnose(self.proposal())
        journal = self.c.area / 'events.jsonl'
        journal.write_bytes(journal.read_bytes().replace(b'STOPPED',b'ADOPTED'))
        with self.assertRaises(EvaluationError): self.c.status()

    def test_public_retry_limit_and_hidden_consumption(self):
        self.ready()
        # A retry packet contains candidate bytes; only the frozen support files stay fixed.
        self.c.event('PUBLIC_FAILED', {'generation_started':1})
        self.assertEqual(self.c.handoff()['attempt'],2)
        self.c.event('PUBLIC_FAILED',{})
        with self.assertRaises(EvaluationError): self.c.handoff()
        self.g.evaluate.assert_not_called()

    def test_hidden_fail_and_hold_do_not_create_adoption(self):
        report = self.ready()
        for state in ('FAIL','HOLD'):
            self.c.event('CANDIDATE_READY', {'public_check':{'candidate_sha':self.sha}})
            report['decision']['status']=state
            self.c.evaluate()
            self.assertEqual(self.c.status()['state'],state)
            self.assertFalse((self.c.area / 'adoption').exists())
            with self.assertRaises(EvaluationError): self.c.handoff()

    def test_public_invalid_output_and_infrastructure_fault_are_not_pass(self):
        self.ready()
        fake=Mock()
        fake.run.return_value={'exit':2,'container_exit':2,'stdout':b'not-json','stderr':b'',
                               'error':None,'oom':False,'wall_seconds':0.1}
        with patch.object(Cycle,'box',return_value=fake):
            self.c.event('BUILDING',{})
            self.c.public_check(self.sha)
            self.assertEqual(self.c.status()['state'],'PUBLIC_FAILED')
            fake.run.return_value['error']='TIMEOUT'
            self.c.event('BUILDING',{})
            with self.assertRaises(EvaluationError): self.c.public_check(self.sha)
            self.assertEqual(self.c.status()['state'],'STOPPED')
        self.g.evaluate.assert_not_called()

    def test_no_failure_cannot_propose_a_repair(self):
        # Each setUp supplies one observation; modify this isolated synthetic receipt.
        self.observation['correct']=True
        with patch.object(Cycle,'receipt',return_value=self.observation):
            with self.assertRaises(EvaluationError): self.c.diagnose(self.proposal())

    def test_evaluation_packet_pr_and_human_approval_are_separate(self):
        self.ready()
        self.c.event('CANDIDATE_READY',{'public_check':{'candidate_sha':self.sha}})
        self.c.evaluate()
        self.assertEqual(self.c.status()['state'],'AWAITING_PR')
        with self.assertRaises(EvaluationError): self.c.request('ADOPT',expiry(),'test')
        self.assertEqual(self.c.adoption().state('target'),'AWAITING_APPROVAL')

    def test_real_filesystem_normal_and_separate_degradation_recovery(self):
        self.evaluated()
        with patch.object(Cycle,'regression',return_value=lambda *_:True):
            request,key=self.request(); self.c.execute(request,key)
            self.c.reobserve()
            normal = self.c.adoption()
            original = normal.actual(normal.binding('target'),ARTIFACT)
            self.c.prepare_trial('degradation')
            request,key=self.request()
            plan=self.c.fault_plan(request)
            self.c.execute(request,key,digest(canonical(plan)))
            self.assertEqual(self.c.status()['state'],'RECOVERY_REQUIRED')
            request,key=self.request('ROLLBACK'); self.c.execute(request,key)
            self.assertEqual(self.c.status()['state'],'ROLLED_BACK')
            self.assertEqual(self.c.active_adoption().actual(self.c.active_adoption().binding('target'),ARTIFACT)[0],normal.packet()['before_hash'])
            self.assertEqual(normal.actual(normal.binding('target'),ARTIFACT),original)

    def test_changed_evaluation_cannot_use_old_ticket(self):
        self.evaluated(); request,key=self.request()
        report=read(self.work / 'report.json'); report['counts']={'changed':1}
        (self.work / 'report.json').write_bytes(canonical(report))
        with self.assertRaises(EvaluationError): self.c.execute(request,key)
        self.assertEqual(self.c.adoption().state('target'),'AWAITING_APPROVAL')

    def test_actual_child_process_death_and_explicit_recovery(self):
        self.evaluated()
        with patch.object(Cycle,'regression',return_value=lambda *_:True):
            request,key=self.request(); self.c.execute(request,key); self.c.reobserve()
            self.c.prepare_trial('crash')
            request,key=self.request(); confirmation=digest(canonical(self.c.fault_plan(request)))
            pid=os.fork()
            if pid == 0:
                self.c.execute(request,key,confirmation)
                os._exit(99)
            _, status=os.waitpid(pid,0)
            self.assertEqual(os.waitstatus_to_exitcode(status),71)
            self.assertEqual(self.c.status()['state'],'RECOVERY_REQUIRED')
            a=self.c.active_adoption()
            self.assertNotEqual(a.actual(a.binding('target'),ARTIFACT)[0],a.packet()['after_hash'])
            request,key=self.request('ROLLBACK'); self.c.execute(request,key)
            self.assertEqual(self.c.status()['state'],'ROLLED_BACK')
            self.assertEqual(a.actual(a.binding('target'),ARTIFACT)[0],a.packet()['before_hash'])
            self.assertEqual(self.c.adoption().state('target'),'ADOPTED')

    def test_fault_injection_needs_its_own_confirmation(self):
        self.evaluated()
        with patch.object(Cycle,'regression',return_value=lambda *_:True):
            request,key=self.request(); self.c.execute(request,key); self.c.reobserve()
            self.c.prepare_trial('crash')
            request,key=self.request()
            with self.assertRaises(EvaluationError): self.c.execute(request,key)
            self.assertEqual(self.c.active_adoption().state('target'),'AWAITING_APPROVAL')

    def test_old_approval_and_recovery_failure_never_succeed(self):
        self.evaluated(); request,key=self.request()
        request['candidate_sha']='0'*40
        with self.assertRaises(EvaluationError): self.c.execute(request,digest(canonical(request)))
        self.assertEqual(self.c.adoption().state('target'),'AWAITING_APPROVAL')

    def test_missing_dependency_prevents_new_cycle(self):
        (self.repo / 'runs/manual-cycle.lock').unlink()  # isolated test teardown, never production unlock
        (self.repo / 'fixtures/manual_cycle/dependency.json').unlink()
        with self.assertRaises(FileNotFoundError): Cycle(self.repo,'cycle-missing').initialize(expiry())
        self.assertFalse((self.repo / 'runs/cycle-missing').exists())

    def test_invalid_pr_destination_or_packet_never_adopts(self):
        self.ready(); self.c.event('CANDIDATE_READY',{'public_check':{'candidate_sha':self.sha}})
        self.c.evaluate()
        with self.assertRaises(EvaluationError): self.c.submit('https://example.invalid/pull/1','b'*40,'c'*64)
        self.assertEqual(self.c.adoption().state('target'),'AWAITING_APPROVAL')

    def test_scope_symlink_rejected(self):
        with self.assertRaises(EvaluationError): Cycle(self.repo,'../escape')
        (self.repo / 'runs/cycle-link').symlink_to(self.c.area,target_is_directory=True)
        with self.assertRaises(EvaluationError): Cycle(self.repo,'cycle-link')


if __name__ == '__main__': unittest.main()
