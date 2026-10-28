"""Real filesystem/approval/crash tests with synthetic approval and inert checks.

These are not human acceptance or evidence of candidate execution in Docker.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from adoption.core import Controller, EvaluationError, ARTIFACT, canonical, digest, read, relative


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'runs', prefix='test-adoption-')
        self.addCleanup(self.temp.cleanup)
        self.c = Controller(ROOT, Path(self.temp.name) / 'control')
        self.packet = self.c.initialize()
        self.root = self.c.area / 'fixtures' / 'first'
        (self.root / 'scripts').mkdir(parents=True)
        self.file = self.root / ARTIFACT
        self.original = (self.c.area / 'baseline.py').read_bytes()
        self.file.write_bytes(self.original)
        self.binding = self.c.register('public-test', 'first', self.root)

    def request(self, operation='ADOPT', target='first'):
        return self.c.request(target, operation, (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(), 'synthetic-test')

    def approve(self, request=None):
        request = request or self.request()
        return self.c.approve(request, confirmation=digest(canonical(request)))

    def adopt(self, regression=lambda *_: True):
        return self.c.execute(self.approve(), regression)

    def recover(self, regression=lambda *_: True):
        return self.c.execute(self.approve(self.request('ROLLBACK')), regression)

    def test_public_submission_matches_pinned_packet_and_diff(self):
        from adoption.core import source_packet
        packet,_,diff=source_packet(ROOT)
        folder=ROOT/'artifacts/fixture-adoption/issue-8'
        self.assertEqual(read(folder/'packet.json'),packet)
        self.assertEqual((folder/'diff.patch').read_bytes(),diff.encode())
        self.assertFalse(packet['merge_is_adoption'])

    def test_normal_adoption_is_exact_bytes_and_preserves_backup(self):
        self.assertEqual(self.adopt()['state'], 'ADOPTED')
        self.assertEqual(digest(self.file.read_bytes()), self.packet['after_hash'])
        self.assertEqual(self.c.backup(self.c.intent('first')), self.original)
        self.assertEqual(self.c.observe('first', lambda *_:True), 'ADOPTED')
        self.assertEqual(len(self.c.events('first')), 2)

    def test_approval_identity_fields_and_unknown_schema_are_rejected(self):
        original = self.request()
        changes = {'candidate_sha':'0'*40, 'evaluation_hash':'0'*64, 'baseline_sha':'0'*40,
            'environment_id':'other', 'root_binding_hash':'0'*64, 'root':str(self.root.parent),
            'artifact_path':'../outside.py', 'before_hash':'0'*64, 'after_hash':'0'*64,
            'schema_version':2, 'operation':'MERGE', 'extra':'value'}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises((EvaluationError, OSError)):
                self.approve(dict(original, **{key:value}))
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_expired_future_and_old_approval(self):
        for fields in [{'expires_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()},
                       {'issued_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
                       {'issued_at':(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()}]:
            with self.subTest(fields=fields), self.assertRaises(EvaluationError):
                self.approve(dict(self.request(), **fields))

    def test_confirmation_and_approval_file_tampering(self):
        with self.assertRaisesRegex(EvaluationError,'CONFIRMATION'):
            self.c.approve(self.request(), confirmation='0'*64)
        key = self.approve()
        path = self.c.area / 'approvals' / (key + '.json')
        path.write_bytes(canonical(dict(read(path), actor='other')))
        with self.assertRaisesRegex(EvaluationError, 'APPROVAL_HASH'):
            self.c.execute(key, lambda *_:True)

    def test_new_target_registration_after_completed_adoption(self):
        self.adopt()
        root=self.c.area/'fixtures/second'
        (root/'scripts').mkdir(parents=True)
        (root/ARTIFACT).write_bytes(self.original)
        self.assertEqual(self.c.register('public-test','second',root)['target_id'],'second')
        with self.assertRaisesRegex(EvaluationError,'ROOT_ALREADY_REGISTERED'):
            self.c.register('public-test','alias',self.root)

    def test_old_target_approval_not_accepted_on_other_target(self):
        root = self.c.area / 'fixtures' / 'second'
        (root/'scripts').mkdir(parents=True); (root/ARTIFACT).write_bytes(self.original)
        self.c.register('public-test','second',root)
        with self.assertRaisesRegex(EvaluationError,'APPROVAL_BINDING'):
            self.approve(dict(self.request(), target_id='second'))
        with self.assertRaisesRegex(EvaluationError,'ROOT_ALREADY_REGISTERED'):
            self.c.register('public-test','alias',self.root)

    def test_adopted_root_replacement_requires_recovery_and_refuses_approval(self):
        self.adopt()
        self.root.rename(self.root.with_name('original'))
        (self.root/'scripts').mkdir(parents=True)
        self.file.write_bytes(self.original)
        with self.assertRaisesRegex(EvaluationError,'ROOT_REPLACED'):
            self.c.observe('first',lambda *_:True)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        with self.assertRaises(EvaluationError): self.request('ROLLBACK')

    def test_root_replaced_same_string_is_rejected(self):
        key = self.approve()
        self.root.rename(self.root.with_name('original'))
        (self.root/'scripts').mkdir(parents=True); self.file.write_bytes(self.original)
        with self.assertRaisesRegex(EvaluationError,'ROOT_REPLACED'):
            self.c.execute(key, lambda *_:True)

    def test_symlink_root_parent_and_file_refused(self):
        key = self.approve()
        self.file.rename(self.file.with_suffix('.original'))
        self.file.symlink_to(self.file.with_suffix('.original'))
        with self.assertRaises(OSError): self.c.execute(key,lambda *_:True)
        self.file.unlink()
        self.file.with_suffix('.original').rename(self.file)
        scripts = self.root/'scripts'; scripts.rename(self.root/'original')
        scripts.symlink_to(self.root/'original', target_is_directory=True)
        with self.assertRaises(OSError): self.c.execute(key,lambda *_:True)
        scripts.unlink(); (self.root/'original').rename(scripts)
        self.root.rename(self.root.with_name('old')); self.root.symlink_to(self.root.with_name('old'))
        with self.assertRaises(OSError): self.c.execute(key,lambda *_:True)

    def test_hardlink_special_and_oversized_destination_refused(self):
        self.file.unlink(); os.mkfifo(self.file)
        with self.assertRaises(EvaluationError): self.request()
        self.file.unlink(); self.file.write_bytes(b'x'*65537)
        with self.assertRaises(EvaluationError): self.request()
        self.file.write_bytes(self.original); os.link(self.file,self.file.with_suffix('.alias'))
        with self.assertRaises(EvaluationError): self.request()

    def test_paths_and_unregistered_outside_root_refused(self):
        for path in ['../x','/tmp/x','scripts//review.py','scripts/./review.py','scripts/../x','', 'x\\y']:
            with self.subTest(path=path), self.assertRaises(EvaluationError): relative(path)
        with self.assertRaises(EvaluationError): self.c.register('x','x',ROOT/'fixtures')
        with self.assertRaises(EvaluationError): self.c.register('x','x',self.root/'..'/'escape')

    def test_evaluation_packet_candidate_mutation_refused(self):
        key = self.approve()
        candidate = self.c.area/'candidate.py'; source = candidate.read_bytes()
        candidate.write_bytes(b'changed')
        with self.assertRaises(EvaluationError): self.c.execute(key,lambda *_:True)
        candidate.write_bytes(source)
        packet = self.c.area/'packet.json'; packet.write_bytes(canonical(dict(self.packet,evaluation_hash='0'*64)))
        with self.assertRaises(EvaluationError): self.c.execute(key,lambda *_:True)

    def test_prewrite_drift_and_double_adoption_refused(self):
        key = self.approve(); self.file.write_bytes(b'drift')
        with self.assertRaises(EvaluationError): self.c.execute(key,lambda *_:True)
        self.file.write_bytes(self.original)
        self.c.execute(key,lambda *_:True)
        with self.assertRaises(EvaluationError): self.c.execute(key,lambda *_:True)
        with self.assertRaises(EvaluationError): self.request()

    def test_post_adoption_degradation_requires_recovery(self):
        self.adopt()
        with self.assertRaisesRegex(EvaluationError,'REGRESSION_FAILED'):
            self.c.observe('first',lambda *_:False)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        self.assertEqual(self.recover()['state'],'ROLLED_BACK')
        self.assertEqual(self.file.read_bytes(), self.original)
        with self.assertRaises(EvaluationError): self.request()

    def test_partial_write_exception_and_fresh_controller_recovery(self):
        def partial(*_):
            self.file.write_bytes(b'partial')
            raise OSError('injected')
        with patch.object(self.c,'replace',side_effect=partial), self.assertRaises(OSError): self.adopt()
        self.c = Controller(ROOT,self.c.area)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        self.assertEqual(self.recover()['state'],'ROLLED_BACK')
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_process_death_after_intent_persists_recovery_lock(self):
        key = self.approve()
        code = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/src')
from adoption.core import Controller
c=Controller(Path(sys.argv[1]),Path(sys.argv[2]))
def crash(*args):
    (Path(sys.argv[3])).write_bytes(b'crash partial')
    os._exit(71)
c.replace=crash
c.execute(sys.argv[4],lambda *_:True)
'''
        out = subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(self.c.area),str(self.file),key])
        self.assertEqual(out.returncode,71)
        self.assertEqual(self.c.events('first')[-1]['state'],'ADOPTING')
        self.assertEqual(Controller(ROOT,self.c.area).state('first'),'RECOVERY_REQUIRED')
        with self.assertRaises(EvaluationError): self.request()
        self.assertEqual(self.recover()['state'],'ROLLED_BACK')

    def test_missing_current_file_can_recover_only_with_bound_approval(self):
        self.adopt(); self.file.unlink()
        with self.assertRaises(EvaluationError): self.c.observe('first',lambda *_:True)
        request = self.request('ROLLBACK'); self.assertIsNone(request['current_hash'])
        key = self.approve(request)
        self.file.write_bytes(b'unexpected')
        with self.assertRaises(EvaluationError): self.c.execute(key,lambda *_:True)
        self.file.unlink()
        self.assertEqual(self.c.execute(key,lambda *_:True)['state'],'ROLLED_BACK')

    def recovery_required(self):
        with self.assertRaises(EvaluationError): self.adopt(lambda *_:False)

    def test_backup_missing_or_corrupt_stops_before_rollback(self):
        self.recovery_required()
        backup = self.c.area/'snapshots'/self.c.intent('first')['backup']
        original = backup.read_bytes(); backup.write_bytes(b'bad')
        with self.assertRaises(EvaluationError): self.approve(self.request('ROLLBACK'))
        backup.write_bytes(original); key = self.approve(self.request('ROLLBACK')); backup.unlink()
        with self.assertRaises(OSError): self.c.execute(key,lambda *_:True)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')

    def test_rollback_failure_and_regression_failure_do_not_resume(self):
        self.recovery_required()
        key = self.approve(self.request('ROLLBACK'))
        with patch.object(self.c,'replace',side_effect=OSError('injected')), self.assertRaises(OSError):
            self.c.execute(key,lambda *_:True)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        with self.assertRaises((EvaluationError, OSError)):
            self.c.execute(key,lambda *_:True)
        with self.assertRaises(EvaluationError): self.recover(lambda *_:False)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        self.assertEqual(self.recover()['state'],'ROLLED_BACK')

    def test_real_os_lock_conflict_refuses_command(self):
        with self.c.guard(), self.assertRaisesRegex(EvaluationError,'CONCURRENT_OPERATION'):
            self.approve()

    def test_cli_regression_uses_readonly_snapshot_and_fixed_docker_contract(self):
        from adoption.regression import DockerRegression
        from adoption.core import IMAGE, load_json
        self.adopt()
        cases=load_json((ROOT/'artifacts/generated-repair/issue-33/public.json').read_bytes())
        by_input={r['stdin'].encode():r for r in cases}
        calls=[]
        def run(program,data,**kwargs):
            self.assertEqual(program.stat().st_mode & 0o777,0o444)
            self.assertNotEqual(program,self.file)
            row=by_input[data]; calls.append(row)
            value={'error':'INVALID_INPUT'} if row['exit']==2 else {
                'findings':[dict(path=p,line=line,rule=rule) for p,line,rule in row['expected']], 'cpu_seconds':0}
            return {'exit':row['exit'],'container_exit':row['exit'],'stdout':canonical(value),
                    'stderr':b'', 'error':None,'oom':False}
        with patch('adoption.regression.Sandbox') as box:
            box.return_value.environment.return_value={}
            box.return_value.image_info.return_value={'id':IMAGE}
            box.return_value.run.side_effect=run
            self.assertTrue(DockerRegression(self.c)(self.file,'ADOPT'))
            self.assertEqual(len(calls),10)
            self.file.write_bytes(self.original); calls.clear()
            self.assertTrue(DockerRegression(self.c)(self.file,'ROLLBACK'))
            self.assertEqual(len(calls),5)
            box.return_value.image_info.return_value={'id':'wrong'}
            with self.assertRaises(EvaluationError): DockerRegression(self.c)(self.file,'ROLLBACK')

    def test_deleted_journal_does_not_release_durable_lock(self):
        self.adopt()
        (self.c.area/'targets/first.journal').unlink()
        self.file.write_bytes(self.original)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        with self.assertRaises(EvaluationError): self.request()
        with self.assertRaises(EvaluationError): self.approve(self.request('ROLLBACK'))

    def test_write_hash_changes_during_regression_require_recovery(self):
        def drift(*_):
            self.file.write_bytes(b'changed during check')
            return True
        with self.assertRaises(EvaluationError): self.adopt(drift)
        self.assertEqual(self.c.state('first'),'RECOVERY_REQUIRED')
        self.assertEqual(self.recover()['state'],'ROLLED_BACK')

    def test_rollback_process_death_and_changed_lock_refused(self):
        self.recovery_required()
        key = self.approve(self.request('ROLLBACK'))
        with patch.object(self.c,'replace',side_effect=SystemExit(71)), self.assertRaises(SystemExit):
            self.c.execute(key,lambda *_:True)
        self.assertEqual(self.c.events('first')[-1]['state'],'ROLLING_BACK')
        self.assertEqual(Controller(ROOT,self.c.area).state('first'),'RECOVERY_REQUIRED')
        lock=self.c.area/'targets/first.intent-lock.json'
        lock.write_bytes(canonical(dict(read(lock),target_id='other')))
        with self.assertRaises(EvaluationError): self.approve(self.request('ROLLBACK'))

    def test_journal_tamper_and_truncation_are_not_success(self):
        self.adopt()
        journal = self.c.area/'targets/first.journal'
        content = journal.read_bytes(); journal.write_bytes(content[:-5])
        with self.assertRaises(EvaluationError): self.c.state('first')
        journal.write_bytes(content.replace(b'ADOPTED',b'IGNORED'))
        with self.assertRaises(EvaluationError): self.c.state('first')


if __name__ == '__main__': unittest.main()
