"""PUBLIC fixtures for the inference-free first-observation pilot."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from test_github_work_guide import item, snapshot, change, SHA
from github_work_guide.core import save_run
from evaluation.core import EvaluationError, canonical
from adoption.core import save

spec = importlib.util.spec_from_file_location('first_failure_pilot', ROOT / 'scripts/first_failure_pilot.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def sample(failed=False):
    s = snapshot(item(7), item(25, True))
    if failed:
        s = change(s, 'pr:25', lambda v: v['raw']['checks'][0].update(conclusion='failure'))
    return s


class DetectionTests(unittest.TestCase):
    def test_required_checks_match_pinned_repository_contract(self):
        names = [x.strip() for x in (ROOT / '.github/pr-gate-checks').read_text().splitlines()
                 if x.strip() and not x.startswith('#')]
        self.assertEqual(tuple(names), p.REQUIRED)

    def test_only_current_open_head_latest_failed_check_is_observed(self):
        self.assertEqual(p.failures(sample()), [])
        s = sample(True)
        self.assertEqual(p.failures(s)[0]['id'], 1)
        for variant in ('closed', 'old-head', 'newer-success', 'running'):
            value = copy.deepcopy(s)
            def edit(v):
                if variant == 'closed':
                    v['state'] = 'CLOSED';v['raw']['detail']['state'] = 'closed'
                elif variant == 'old-head':
                    v['raw']['checks'][0]['head_sha'] = 'b' * 40
                elif variant == 'newer-success':
                    v['raw']['checks'].append({**v['raw']['checks'][0], 'id': 10, 'conclusion': 'success'})
                else:
                    v['raw']['checks'][0].update(status='in_progress', conclusion=None)
            value = change(value, 'pr:25', edit)
            self.assertEqual(p.failures(value), [], variant)

    def test_security_statuses_and_codeql_are_captured_without_external_urls(self):
        for name in p.REQUIRED:
            s = change(sample(), 'pr:25', lambda v: v['raw']['statuses'].append(
                {'id': 9, 'context': name, 'state': 'error', 'target_url': 'https://untrusted.invalid'}))
            observed = p.failures(s)[0]
            self.assertEqual(observed['kind'], 'commit-status')
            self.assertEqual(observed['name'], name)
            self.assertNotIn('untrusted', str(observed))
            s = change(s, 'pr:25', lambda v: v['raw']['statuses'].append(
                {'id': 10, 'context': name, 'state': 'success'}))
            self.assertEqual(p.failures(s), [])
        s = change(sample(), 'pr:25', lambda v: v['raw']['checks'][2].update(conclusion='timed_out'))
        self.assertEqual(p.failures(s)[0]['name'], 'Analyze (python)')

    def test_duplicate_id_and_incomplete_snapshot_are_refused(self):
        s = change(sample(True), 'pr:25', lambda v: v['raw']['checks'].append(copy.deepcopy(v['raw']['checks'][0])))
        with self.assertRaises(EvaluationError):
            p.failures(s)
        from github_work_guide.core import seal, Invalid
        s = sample()
        s = seal(s['items'], dict(s['coverage'], status='INCOMPLETE', errors=['fixed']))
        with self.assertRaises(Invalid):
            p.failures(s)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.pilot = p.Pilot(self.root)
        self.runtime = patch.object(self.pilot, 'runtime').start()
        self.addCleanup(patch.stopall)
        self.notify = patch.object(self.pilot, 'notify').start()
        self.pilot.configure(SHA)
        self.source = sample()
        self.collect = patch.object(self.pilot, 'collect', side_effect=self.fake_collect).start()

    def fake_collect(self, output, cycle):
        save_run(output, {'snapshot.json': self.source, 'report.md': 'PUBLIC saved report\n'})

    def test_clear_then_first_failure_is_durable_and_future_ticks_never_collect(self):
        self.assertEqual(self.pilot.tick()['status'], 'CLEAR')
        self.source = sample(True)
        first = self.pilot.tick()
        self.assertEqual(first['status'], 'AWAITING_REVIEW')
        self.assertEqual(first['failure']['head_sha'], SHA)
        self.assertEqual(first['failure']['pr_number'], 25)
        self.assertEqual(first['model_calls'], 0)
        report = self.pilot.state / 'first-report.md'
        before = report.read_bytes()
        restarted = p.Pilot(self.root)
        with patch.object(restarted, 'collect', side_effect=AssertionError('no network')):
            self.assertEqual(restarted.tick(), first)
            self.assertEqual(restarted.status(), first)
        self.assertEqual(report.read_bytes(), before)
        self.assertEqual(self.collect.call_count, 2)
        self.notify.assert_called_once()
        self.assertNotIn('generation-approval', str(list(self.pilot.state.rglob('*'))))

    def test_multiple_failures_fix_only_first_deterministic_observation(self):
        self.source = change(sample(True), 'pr:25', lambda v: v['raw']['checks'][1].update(conclusion='failure'))
        result = self.pilot.tick()
        self.assertEqual(result['failure']['name'], 'ci')
        self.assertEqual(len(list((self.pilot.state / 'cycles').iterdir())), 1)

    def test_stop_blocks_network_and_cannot_resume_by_reconfigure(self):
        self.pilot.stop()
        result = self.pilot.tick()
        self.assertEqual(result['status'], 'STOPPED')
        self.assertEqual(result['reason'], 'STOP_REQUESTED')
        self.collect.assert_not_called()
        with self.assertRaises(EvaluationError):
            self.pilot.configure(SHA)
        self.assertEqual(self.pilot.tick(), result)

    def test_incomplete_or_failed_collect_stays_stopped_and_is_not_retried(self):
        self.collect.side_effect = EvaluationError('COLLECT_FAILED')
        first = self.pilot.tick()
        self.assertEqual(first['reason'], 'COLLECT_FAILED')
        self.assertEqual(self.pilot.tick(), first)
        self.collect.assert_called_once()

    def test_interrupted_cycle_is_never_resubmitted(self):
        cycle = self.pilot.state / 'cycles' / ('001-' + 'a' * 32)
        cycle.mkdir()
        value = self.pilot.tick()
        self.assertEqual(value['reason'], 'RECOVERY_REQUIRED')
        self.collect.assert_not_called()

    def test_count_and_storage_limits_pause_without_collect_or_deletion(self):
        with patch.object(p, 'MAX_CHECKS', 0):
            value = self.pilot.tick()
        self.assertEqual(value['reason'], 'CHECK_LIMIT')
        self.collect.assert_not_called()
        self.assertTrue((self.pilot.state / 'config.json').exists())

    def test_storage_limit_symlink_and_config_changes_fail_closed(self):
        with patch.object(p, 'MAX_BYTES', 1):
            value = self.pilot.tick()
        self.assertEqual(value['reason'], 'STORAGE_LIMIT')
        self.collect.assert_not_called()

    def test_invalid_config_or_permissions_pause_before_network(self):
        config = self.pilot.state / 'config.json'
        config.write_bytes(canonical({'schema_version': 1, 'enabled': True, 'runtime_sha': SHA, 'infer': True}))
        value = self.pilot.tick()
        self.assertEqual(value['reason'], 'CONFIG_INVALID')
        self.collect.assert_not_called()

    def test_symlink_config_is_not_read(self):
        config = self.pilot.state / 'config.json'
        config.unlink();config.symlink_to(self.root / 'outside')
        value = self.pilot.tick()
        self.assertEqual(value['status'], 'STOPPED')
        self.collect.assert_not_called()

    def test_corrupted_report_or_snapshot_does_not_trigger_new_collection(self):
        self.source = sample(True)
        self.pilot.tick()
        report = self.pilot.state / 'first-report.md'
        report.write_text('modified')
        value = self.pilot.tick()
        self.assertEqual(value['reason'], 'REPORT_CHANGED')
        self.collect.assert_called_once()

    def test_disabled_and_not_configured_never_start_collection(self):
        config = self.pilot.state / 'config.json'
        config.write_bytes(canonical({'schema_version':1,'enabled':False,'runtime_sha':SHA}))
        self.assertEqual(self.pilot.tick()['status'], 'DISABLED')
        self.assertEqual(p.Pilot(self.root / 'other').tick()['status'], 'NOT_CONFIGURED')
        self.collect.assert_not_called()

    def test_concurrent_tick_and_status_cannot_create_second_cycle(self):
        with self.pilot.lock():
            with self.assertRaisesRegex(EvaluationError, 'CONCURRENT_RUN'):
                self.pilot.tick()
            with self.assertRaisesRegex(EvaluationError, 'CONCURRENT_RUN'):
                self.pilot.status()
        self.collect.assert_not_called()

    def test_runtime_change_and_mid_collect_stop_are_reported(self):
        self.runtime.side_effect = EvaluationError('RUNTIME_CHANGED')
        value = self.pilot.tick()
        self.assertEqual(value['reason'], 'RUNTIME_CHANGED')
        self.collect.assert_not_called()


    def test_one_completed_check_consumes_limit_and_keeps_snapshot(self):
        first=self.pilot.tick()
        with patch.object(p,'MAX_CHECKS',1):
            second=self.pilot.tick()
        self.assertEqual(second['reason'],'CHECK_LIMIT')
        self.assertTrue((self.root/'runs'/first['snapshot_run']/'snapshot.json').is_file())
        self.collect.assert_called_once()

    def test_incomplete_saved_snapshot_is_stopped_not_success(self):
        from github_work_guide.core import seal
        value=sample();self.source=seal(value['items'],dict(value['coverage'],status='INCOMPLETE',errors=['fixed']))
        result=self.pilot.tick()
        self.assertEqual(result['status'],'STOPPED')
        self.assertEqual(self.pilot.tick(),result)
        self.collect.assert_called_once()

    def test_previous_saved_snapshot_tampering_prevents_next_fetch(self):
        first=self.pilot.tick()
        path=self.root/'runs'/first['snapshot_run']/'snapshot.json'
        path.write_bytes(path.read_bytes()+b' ')
        result=self.pilot.tick()
        self.assertEqual(result['status'],'STOPPED')
        self.collect.assert_called_once()

    def test_stop_and_config_change_during_collect_fail_closed(self):
        def stopped(output,cycle):
            self.fake_collect(output,cycle);self.pilot.stop()
        self.collect.side_effect=stopped
        self.assertEqual(self.pilot.tick()['reason'],'STOP_REQUESTED')

    def test_changed_configuration_during_collect_is_not_accepted(self):
        def changed(output,cycle):
            self.fake_collect(output,cycle)
            (self.pilot.state/'config.json').write_bytes(canonical({'schema_version':1,'enabled':False,'runtime_sha':SHA}))
        self.collect.side_effect=changed
        self.assertEqual(self.pilot.tick()['reason'],'CONFIG_CHANGED')

    def test_public_config_permissions_and_state_symlink_are_rejected(self):
        (self.pilot.state/'config.json').chmod(0o644)
        self.assertEqual(self.pilot.tick()['reason'],'RECORD_PERMISSIONS')
        self.collect.assert_not_called()

    def test_changed_snapshot_after_first_pause_is_never_replaced(self):
        self.source=sample(True);first=self.pilot.tick()
        path=self.root/'runs'/first['snapshot_run']/'snapshot.json'
        path.write_bytes(path.read_bytes()+b' ')
        before=(self.pilot.state/'terminal.json').read_bytes()
        self.assertEqual(self.pilot.tick()['status'],'STOPPED')
        self.assertEqual((self.pilot.state/'terminal.json').read_bytes(),before)
        self.collect.assert_called_once()



    def test_unverified_stop_survives_permission_repair_without_network(self):
        self.pilot.state.chmod(0o755)
        with self.assertRaises(EvaluationError):self.pilot.path_check()
        self.pilot.block_unverified()
        self.pilot.state.chmod(0o700)
        self.assertEqual(self.pilot.tick()['reason'],'PILOT_UNVERIFIED')
        self.assertEqual(self.pilot.status()['reason'],'PILOT_UNVERIFIED')
        self.collect.assert_not_called()


    def test_terminal_counter_tampering_stops_without_replacing_record(self):
        self.source=sample(True);self.pilot.tick()
        path=self.pilot.state/'terminal.json';value=json.loads(path.read_text());value['model_calls']=1
        path.write_bytes(canonical(value))
        self.assertEqual(self.pilot.tick()['reason'],'TERMINAL_INVALID')
        self.assertEqual(json.loads(path.read_text())['model_calls'],1)
        self.collect.assert_called_once()

    def test_repeated_stop_preserves_original_marker(self):
        self.pilot.stop();path=self.pilot.state/'stop.requested';first=path.read_bytes()
        self.assertEqual(self.pilot.stop()['status'],'STOP_REQUESTED')
        self.assertEqual(path.read_bytes(),first)
        self.collect.assert_not_called()


    def test_stop_request_does_not_depend_on_valid_configuration(self):
        (self.pilot.state/'config.json').write_bytes(b'{')
        self.assertEqual(self.pilot.stop()['status'],'STOP_REQUESTED')
        self.assertTrue(self.pilot.stop_requested())
        self.collect.assert_not_called()
        self.assertEqual(p.Pilot(self.root/'unconfigured').stop()['status'],'NOT_CONFIGURED')


    def test_missing_configuration_is_latched_and_restoration_does_not_resume(self):
        self.pilot.tick();config=self.pilot.state/'config.json';before=config.read_bytes();config.unlink()
        failed=self.pilot.tick()
        self.assertEqual(failed['status'],'STOPPED')
        self.assertEqual(failed['reason'],'CONFIG_MISSING')
        config.write_bytes(before);config.chmod(0o600)
        self.assertEqual(self.pilot.tick(),failed)
        self.collect.assert_called_once()

    def test_real_child_collects_public_fixture_then_freezes_first_report(self):
        root=self.root/'native';(root/'scripts').mkdir(parents=True)
        program=root/'scripts/report_github_work_guide.py'
        value=json.dumps(sample(True),ensure_ascii=True)
        program.write_text('import sys,json\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,'+repr(str(ROOT/'src'))+')\n'
            + 'from github_work_guide.core import save_run\n'
            + 'save_run(Path(sys.argv[-1]),'+repr({'report.md':'PUBLIC synthetic report\n'})
            + ' | {"snapshot.json":json.loads('+repr(value)+')})\n')
        pilot=p.Pilot(root)
        with patch.object(pilot,'runtime'),patch.object(pilot,'notify'):
            pilot.configure(SHA)
            result=pilot.tick()
            self.assertEqual(result['status'],'AWAITING_REVIEW',result)
            with patch.object(p.subprocess,'Popen',side_effect=AssertionError('no second child')):
                self.assertEqual(pilot.tick(),result)
        self.assertEqual(pilot.read(pilot.state/'terminal.json'),result)


class ProcessTests(unittest.TestCase):
    def test_actual_process_arguments_and_bounded_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();pilot=p.Pilot(root);cycle=root/'cycle';cycle.mkdir()
            child=Mock(pid=123,returncode=None)
            child.poll.return_value=None
            child.wait.return_value=143
            with patch.object(p.subprocess,'Popen',return_value=child) as popen, \
                 patch.object(pilot,'stop_requested',return_value=True),patch.object(pilot,'observe',return_value=None), \
                 patch.object(p.os,'getpgid',return_value=123),patch.object(p.os,'killpg') as kill:
                with self.assertRaisesRegex(EvaluationError,'STOP_REQUESTED'):
                    pilot.collect(root/'runs/pilot-test',cycle)
            args=popen.call_args.args[0]
            self.assertEqual(args[1:3],['-I','-B'])
            self.assertEqual(args[3:5],['-c',p.COLLECTOR_SUPERVISOR])
            self.assertEqual(args[5],str(root))
            self.assertEqual(args[6],str(root/'runs/pilot-test'))
            self.assertIn("'collect', '--out'",p.COLLECTOR_SUPERVISOR)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertFalse(popen.call_args.kwargs.get('shell',False))
            self.assertEqual(kill.call_args_list[0].args,(123,signal.SIGTERM))
            self.assertEqual(kill.call_args_list[1].args,(123,signal.SIGKILL))
            child.wait.assert_called_once_with(timeout=5)


    def test_group_kill_precedes_reaping_so_pid_cannot_be_reused(self):
        pilot=p.Pilot(ROOT);child=Mock(pid=123)
        with patch.object(pilot,'observe',return_value=None),patch.object(p.os,'getpgid',return_value=123), \
             patch.object(p.os,'killpg') as kill, \
             patch.object(p.time,'sleep'):
            child.wait.side_effect=lambda **_: self.assertEqual(kill.call_args_list[-1].args,(123,signal.SIGKILL))
            pilot.terminate(child)
        self.assertEqual([c.args[1] for c in kill.call_args_list],[signal.SIGTERM,signal.SIGKILL])
        child.wait.assert_called_once_with(timeout=5)

    def test_unknown_process_group_is_never_signalled(self):
        pilot=p.Pilot(ROOT);child=Mock(pid=123)
        with patch.object(pilot,'observe',return_value=None),patch.object(p.os,'getpgid',return_value=456),patch.object(p.os,'killpg') as kill:
            with self.assertRaisesRegex(EvaluationError,'CHILD_IDENTITY_UNCONFIRMED'):
                pilot.terminate(child)
        kill.assert_not_called()


    def test_collector_timeout_terminates_owned_child_without_waiting_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();pilot=p.Pilot(root);cycle=root/'cycle';cycle.mkdir()
            child=Mock(pid=123,returncode=None);child.poll.return_value=None
            with patch.object(p.subprocess,'Popen',return_value=child), \
                 patch.object(pilot,'stop_requested',return_value=False),patch.object(pilot,'capacity'),patch.object(pilot,'observe',return_value=None), \
                 patch.object(p.time,'monotonic',side_effect=[0,211]),patch.object(pilot,'terminate') as terminate:
                with self.assertRaisesRegex(EvaluationError,'COLLECT_TIMEOUT'):
                    pilot.collect(root/'runs/pilot-test',cycle)
                terminate.assert_called_once_with(child)


    def test_exited_leader_does_not_leave_live_descendant(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'scripts').mkdir();cycle=root/'cycle';cycle.mkdir()
            ready=root/'ready';beat=root/'heartbeat';stop=root/'stop-child'
            child_code=("import signal,time\nfrom pathlib import Path\n"
                + "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                + "ready=Path("+repr(str(ready))+");beat=Path("+repr(str(beat))+");stop=Path("+repr(str(stop))+")\n"
                + "ready.write_text('ready');end=time.monotonic()+10\n"
                + "while time.monotonic()<end and not stop.exists():\n beat.write_text(str(time.monotonic()));time.sleep(.01)\n")
            program=("import subprocess,sys,time\nfrom pathlib import Path\n"
                + "subprocess.Popen([sys.executable,'-I','-c',"+repr(child_code)+"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                + "ready=Path("+repr(str(ready))+");end=time.monotonic()+5\n"
                + "while not ready.exists():\n assert time.monotonic()<end;time.sleep(.01)\n")
            (root/'scripts/report_github_work_guide.py').write_text(program)
            pilot=p.Pilot(root)
            try:
                pilot.collect(root/'runs/pilot-test',cycle)
                time.sleep(.1);before=beat.read_text();time.sleep(.2)
                self.assertEqual(beat.read_text(),before,'descendant still runs after collector exited')
            finally:
                stop.write_text('stop')
                time.sleep(.05)

    def test_fresh_isolated_cli_ignores_cwd_pythonpath_and_has_no_auth_or_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            (root/'github_work_guide.py').write_text('raise RuntimeError("poisoned")')
            env=dict(os.environ,PYTHONPATH=str(root))
            result=subprocess.run([sys.executable,'-I','-B',str(ROOT/'scripts/first_failure_pilot.py'),'status'],
                                  cwd=root,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout)
            self.assertEqual(value,{'status':'NOT_CONFIGURED','model_calls':0,'hermes_auth_reads':0})


    def test_launch_agent_has_only_fixed_hourly_read_only_entry(self):
        import plistlib
        value=plistlib.loads((ROOT/'scripts/launchd/com.secondworks.hermes.first-failure-pilot.plist').read_bytes())
        self.assertEqual(value['Label'],'com.secondworks.hermes.first-failure-pilot')
        self.assertEqual(value['StartInterval'],p.INTERVAL)
        self.assertEqual(value['ProgramArguments'],['@PYTHON@','-I','-B','@CHECKOUT@/scripts/first_failure_pilot.py','tick'])
        self.assertIs(value['RunAtLoad'],True);self.assertIs(value['KeepAlive'],False)
        self.assertFalse(set(value)&{'StartCalendarInterval','Sockets','WatchPaths','MachServices'})


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'scripts').mkdir()
        (self.root/'scripts/worker.py').write_text('print(1)\n')
        (self.root/'.gitignore').write_text('runs/\n')
        def git(*args):
            return subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True).stdout
        self.git=git
        git('init','-q');git('config','user.name','Synthetic Test');git('config','user.email','synthetic@example.invalid')
        git('add','.');git('commit','-qm','PUBLIC synthetic runtime')
        self.sha=git('rev-parse','HEAD').decode().strip();self.pilot=p.Pilot(self.root)

    def test_runtime_ignores_git_environment_and_verifies_real_tree(self):
        with patch.dict(os.environ,{'GIT_DIR':'/nonexistent','GIT_WORK_TREE':'/nonexistent'}):
            self.pilot.runtime(self.sha)

    def test_runtime_detects_hidden_assume_unchanged_source(self):
        self.git('update-index','--assume-unchanged','scripts/worker.py')
        (self.root/'scripts/worker.py').write_text('print(2)\n')
        self.assertEqual(self.git('status','--porcelain'),b'')
        with self.assertRaisesRegex(EvaluationError,'RUNTIME_CHANGED'):
            self.pilot.runtime(self.sha)


class NotificationTests(unittest.TestCase):
    def test_notification_failure_does_not_discard_report_or_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            pilot=p.Pilot(Path(tmp).resolve())
            pilot.state.mkdir(parents=True,mode=0o700)
            with patch.object(p.sys,'platform','darwin'),patch.object(p.subprocess,'run',side_effect=OSError('fixed')) as send:
                value=pilot.pause('STOPPED','FIXED')
                self.assertEqual(pilot.terminal(),value)
                self.assertEqual(pilot.read(pilot.state/'notification.json'),{'status':'FAILED'})
                self.assertEqual(send.call_count,1)
                self.assertEqual(send.call_args.args[0][0],'/usr/bin/osascript')
                self.assertNotIn(str(pilot.state),''.join(send.call_args.args[0][1:8]))


if __name__=='__main__':unittest.main()
