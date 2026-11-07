"""Periodic orchestration: synthetic inspections, real one-shot receipts, mocked workers."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from threading import Event, Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts')); sys.path.insert(0, str(ROOT/'tests'))
import test_extract_public_failure as fixtures
import periodic_improvement as runner
import periodic_check as periodic
import run_mock_improvement as intake
from evaluation.core import EvaluationError, canonical, digest
from github_work_guide.core import save_run
from bind_public_reproduction import BINDING


class PeriodicImprovementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PublicFailureTest(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.run.parents[1]
        self.run = self.fixture.run.with_name('periodic-20261107-0000')
        self.fixture.run.rename(self.run); self.fixture.run = self.run
        for obj, name, value in [(runner,'ROOT',self.root),(runner,'STATE',self.root/'runs/periodic-improvement'),
                                 (runner.profiles,'ROOT',self.root),(runner.profiles,'STATE',self.root/'runs/profile-evaluation'),
                                 (runner.generation,'ROOT',self.root),(intake,'ROOT',self.root)]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.state=runner.STATE;self.state.mkdir()
        self.config=self.state/'config.json';self.enable()
        self.evidence=self.state/'reproductions';self.evidence.mkdir()
        self.entry=fixtures.intake(self.run,25,self.fixture)
        self.entry.update(status='AWAITING_HUMAN_REVIEW',reproduction_sha256='a'*64)
        evidence={'schema_version':1,'reproduction_sha256':'a'*64,'observed':'FAIL','expected':'PASS',
                  **{key:self.entry[key] for key in BINDING}}
        (self.evidence/(self.entry['event_id']+'.json')).write_bytes(canonical(evidence))
        self.job=self.state/'events'/self.entry['event_id']
        self.context={'run_id':'evaluation-20261107T000000Z-aaaaaaaaaaaa','profile_id':'event-status-counts-v1',
                      'manifest_hash':'f'*64}
        self.work=self.root/'runs'/self.context['run_id'];self.work.mkdir()
        self.mapping={'profile_id':'event-status-counts-v1','event_id':self.entry['event_id']}
        self.report={'state':'AWAITING_HUMAN_APPROVAL'}
        self.semantic_plan={'status':'AWAITING_SEND_APPROVAL','plan':{'event_id':self.entry['event_id'],
                            'max_total_requests':10},'trials':list(range(9))}
        p=patch.object(runner.profiles,'mapping_plan',return_value=self.mapping);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'prepare',return_value=self.context);self.prepare=p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'context',return_value=self.context);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles.gate,'run_path',return_value=self.work);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles.gate,'RUNS',self.root/'runs');p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'manifest',return_value={'entry':self.entry});p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'verify_proposal');p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'evaluate',side_effect=self.evaluate);self.evaluate_mock=p.start();self.addCleanup(p.stop)
        p=patch.object(runner.profiles,'audit',return_value={'report_hash':'c'*64});p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'prepare',return_value=self.semantic_plan);self.semantic_prepare=p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'send_plan',return_value=self.semantic_plan);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'run',side_effect=self.measure);self.semantic_run=p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'audit',return_value={'report_hash':'d'*64});p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'area',return_value=self.job);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.semantic,'STATE',self.state);p.start();self.addCleanup(p.stop)
        p=patch.object(runner.generation,'read_auth',return_value={'synthetic':True});self.auth=p.start();self.addCleanup(p.stop)
        response={'schema_version':1,'decision':'HOLD','reason':'Synthetic response.',
                  'evidence_refs':['/reproduction_sha256']}
        self.reply=canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps(response)})
        p=patch('delegation.hermes_cloud.response',return_value=self.reply);self.cloud=p.start();self.addCleanup(p.stop)

    def enable(self, enabled=True):
        self.config.write_bytes(canonical({'schema_version':1,'enabled':enabled}));self.config.chmod(0o600)

    def dispatch(self, run=None, **kw):
        return runner.dispatch(run or self.run,transport=self.fixture,**kw)

    def private(self,path,value):
        path.write_bytes(canonical(value));path.chmod(0o600)

    def register(self):
        self.assertEqual(self.dispatch()['status'],'AWAITING_MAPPING')
        self.private(self.job/'mapping.json',self.mapping)
        self.assertEqual(self.dispatch()['status'],'AWAITING_GENERATION_APPROVAL')
        expected=json.loads((self.job/'generation-plan.json').read_text())
        self.private(self.job/'generation-approval.json',{**expected,'expires_at':int(time.time())+600})

    def evaluate(self,*_):
        (self.work/'profile-report.json').write_bytes(canonical(self.report))
        return deepcopy(self.report)

    def measure(self,*_):
        value={'state':'AWAITING_HUMAN_APPROVAL'}
        (self.job/'report.json').write_bytes(canonical(value))
        return value

    def test_missing_disabled_invalid_config_never_selects_or_reads_auth(self):
        for value in (False,True):
            self.enable(value)
            if value:self.config.unlink()
            with patch.object(runner,'select') as selected:
                self.assertEqual(self.dispatch()['status'],'DISABLED');selected.assert_not_called()
        self.enable();self.config.chmod(0o644)
        self.assertEqual(self.dispatch()['reason'],'PRIVATE_FILE_PERMISSIONS')
        self.enable('yes');self.assertEqual(self.dispatch()['reason'],'PERIODIC_CONFIG')
        self.auth.assert_not_called();self.cloud.assert_not_called()

    def test_incomplete_or_tampered_inspection_never_starts(self):
        self.assertEqual(self.dispatch(inspection_complete=False)['reason'],'POINT_CHECK_INCOMPLETE')
        path=self.run/'snapshot.json';path.write_text('{}')
        self.assertEqual(self.dispatch()['status'],'STOPPED')
        self.prepare.assert_not_called();self.auth.assert_not_called()

    def test_symlink_ancestor_is_rejected_before_configuration_read(self):
        runs=self.root/'runs';moved=self.root/'preserved-runs'
        runs.rename(moved);runs.symlink_to(moved,target_is_directory=True)
        with patch.object(runner.generation,'owner_file') as read_config:
            self.assertEqual(self.dispatch()['reason'],'PATH_SYMLINK')
        read_config.assert_not_called();self.auth.assert_not_called()

    def test_mapping_and_each_send_approval_are_required(self):
        self.register()
        (self.job/'generation-approval.json').unlink()
        self.assertEqual(self.dispatch()['status'],'AWAITING_GENERATION_APPROVAL')
        self.auth.assert_not_called();self.cloud.assert_not_called()
        self.assertEqual(self.prepare.call_count,1)

    def test_generation_evaluation_and_restart_never_resend(self):
        self.register()
        first=self.dispatch();self.assertEqual(first['status'],'AWAITING_HUMAN_APPROVAL')
        self.assertEqual(self.dispatch(),first)
        self.assertEqual(self.cloud.call_count,1);self.assertEqual(self.auth.call_count,1)
        self.assertEqual(self.evaluate_mock.call_count,1)
        # A later completed check cannot resubmit the same original event.
        later=self.run.with_name('periodic-20261114-0000')
        def changed(item):item['body']=item['raw']['detail']['body']='A later synthetic inspection'
        snapshot=fixtures.change(self.fixture.snapshot,'pr:25',changed)
        save_run(later,{'snapshot.json':snapshot})
        self.assertEqual(self.dispatch(later)['status'],'SKIP')
        self.assertEqual(self.cloud.call_count,1)

    def test_semantic_stage_requires_separate_approval_and_does_not_regenerate(self):
        self.register();self.report={'state':'HOLD','decision':{'reasons':runner.SEMANTIC_REASON}}
        first=self.dispatch();self.assertEqual(first['status'],'AWAITING_SEMANTIC_APPROVAL')
        self.assertEqual(self.dispatch(),first)
        self.semantic_run.assert_not_called()
        self.private(self.job/'semantic-approval.json',{**self.semantic_plan['plan'],'expires_at':int(time.time())+600})
        final=self.dispatch();self.assertEqual(final['status'],'AWAITING_HUMAN_APPROVAL')
        self.assertEqual(self.dispatch(),final)
        self.assertEqual(self.cloud.call_count,1);self.assertEqual(self.semantic_run.call_count,1)

    def test_invalid_approval_stops_before_auth_and_cannot_be_retried(self):
        self.register();path=self.job/'generation-approval.json'
        value=json.loads(path.read_text());value['max_requests']=2;self.private(path,value)
        first=self.dispatch();self.assertEqual(first['reason'],'APPROVAL_MISMATCH')
        self.assertEqual(self.dispatch(),first)
        self.auth.assert_not_called();self.cloud.assert_not_called()

    def test_crash_after_started_marker_requires_recovery(self):
        self.register()
        (self.job/'generate-started.json').write_bytes(canonical({'operation':'generate'}))
        first=self.dispatch();self.assertEqual(first['reason'],'PERIODIC_RECOVERY_REQUIRED')
        self.assertEqual(self.dispatch(),first);self.auth.assert_not_called()

    def test_auth_refusal_never_retries(self):
        self.register();self.cloud.return_value=canonical({'status':'AUTH_FAILED'})
        first=self.dispatch();self.assertEqual(first['reason'],'AUTH_FAILED')
        self.assertEqual(self.dispatch(),first);self.assertEqual(self.cloud.call_count,1)

    def test_cleanup_unknown_keeps_global_pending_and_never_retries(self):
        self.register()
        error=EvaluationError('ISOLATION_CLEANUP_FAILED');error.pending_container='hermes-eval-'+'e'*32
        self.cloud.side_effect=error
        self.assertEqual(self.dispatch()['reason'],'ISOLATION_CLEANUP_FAILED')
        pending=self.root/'runs/public-hermes/isolation-pending.json'
        before=pending.read_bytes()
        self.assertEqual(self.dispatch()['reason'],'ISOLATION_PENDING')
        self.assertEqual(pending.read_bytes(),before);self.assertEqual(self.cloud.call_count,1)

    def test_later_inspection_services_only_the_outstanding_job(self):
        self.register();(self.job/'generation-approval.json').unlink()
        later=self.run.with_name('periodic-20261114-0000')
        def changed(item):item['body']=item['raw']['detail']['body']='Later synthetic check'
        save_run(later,{'snapshot.json':fixtures.change(self.fixture.snapshot,'pr:25',changed)})
        result=self.dispatch(later)
        self.assertEqual(result['status'],'AWAITING_GENERATION_APPROVAL')
        self.assertEqual(result['event_id'],self.job.name)
        self.assertEqual(len(list((self.state/'events').iterdir())),1)
        self.auth.assert_not_called()

    def test_live_failure_recovery_stops_before_credentials(self):
        self.register();self.fixture.check['conclusion']='success'
        self.assertEqual(self.dispatch()['reason'],'PERIODIC_FAILURE_CHANGED')
        self.auth.assert_not_called()

    def test_stop_preserves_inspection_and_blocks_new_jobs(self):
        before=(self.run/'manifest.json').read_bytes()
        intake.control_intake(self.root/'runs/public-hermes','stop')
        self.assertEqual(self.dispatch()['reason'],'INTAKE_STOPPED')
        self.assertEqual((self.run/'manifest.json').read_bytes(),before)
        self.auth.assert_not_called()
        intake.control_intake(self.root/'runs/public-hermes','resume')
        self.assertEqual(self.dispatch()['status'],'AWAITING_MAPPING')

    def test_stop_running_job_then_resume_does_not_resend(self):
        self.register();entered,release=Event(),Event();results=[]
        def waiting(*_):
            entered.set()
            if not release.wait(5):raise AssertionError('test worker was not released')
            return self.reply
        self.cloud.side_effect=waiting
        thread=Thread(target=lambda:results.append(self.dispatch()))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            with patch.object(intake,'interrupt_worker',side_effect=lambda *_:release.set()):
                self.assertEqual(intake.control_intake(self.root/'runs/public-hermes','stop'),'INTAKE_STOPPED')
        finally:
            release.set();thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['reason'],'INTAKE_STOPPED')
        self.assertEqual(intake.control_intake(self.root/'runs/public-hermes','resume'),'ACCEPTING')
        self.assertEqual(self.dispatch(),results[0]);self.assertEqual(self.cloud.call_count,1)
        self.assertTrue((self.run/'manifest.json').is_file())

    def test_concurrent_dispatch_does_not_start_another_worker(self):
        with intake.state_lock(self.state,'dispatcher.lock'):
            self.assertEqual(self.dispatch()['reason'],'CONCURRENT_RUN')
        self.auth.assert_not_called()

    def test_config_disabled_during_prepare_never_reaches_credentials(self):
        def disabled(*_):self.enable(False);return self.context
        self.prepare.side_effect=disabled
        self.register()
        self.assertEqual(self.dispatch()['status'],'DISABLED');self.auth.assert_not_called()

    def test_symlink_mapping_and_unknown_fields_fail_closed(self):
        self.dispatch();target=self.state/'outside.json';target.write_bytes(canonical(self.mapping))
        (self.job/'mapping.json').symlink_to(target)
        self.assertEqual(self.dispatch()['status'],'STOPPED');self.prepare.assert_not_called()


class PeriodicHandoffTests(unittest.TestCase):
    def test_summary_is_saved_before_improvement_and_survives_its_failure(self):
        fixture=fixtures.PublicFailureTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        root=fixture.run.parents[1]
        def collect(args,**_):
            out=Path(args[args.index('--out')+1])
            save_run(out,{'snapshot.json':fixture.snapshot,'diff.json':[]})
            return 0,'',''
        def handoff(path,completed):
            self.assertTrue(completed)
            summaries=list((root/'runs/periodic-summaries').glob('*.md'))
            self.assertEqual(len(summaries),1)
            self.assertIn('取得',summaries[0].read_text())
            self.assertTrue((path/'manifest.json').is_file())
            return {'status':'STOPPED','reason':'SYNTHETIC_FAILURE'}
        with patch.object(periodic,'ROOT',root),patch.object(periodic,'run',side_effect=collect), \
             patch.object(periodic,'main_ci',return_value=([],None)), \
             patch.object(periodic,'review_setting',return_value=['codex']), \
             patch.object(periodic,'improvement_handoff',side_effect=handoff):
            self.assertEqual(periodic.main([]),0)
        text=next((root/'runs/periodic-summaries').glob('*.md')).read_text()
        self.assertIn('SYNTHETIC_FAILURE',text)

    def test_handoff_failure_and_incomplete_check_preserve_monitoring(self):
        with patch.object(runner,'dispatch',side_effect=RuntimeError('synthetic failure')):
            self.assertEqual(periodic.improvement_handoff(Path('/unused'),True),
                             {'status':'STOPPED','reason':'PERIODIC_HANDOFF_FAILED'})
        with patch.object(runner,'dispatch',return_value={'status':'SKIP'}) as dispatch:
            periodic.improvement_handoff(Path('/unused'),False)
            self.assertFalse(dispatch.call_args.kwargs['inspection_complete'])


if __name__=='__main__':unittest.main()
