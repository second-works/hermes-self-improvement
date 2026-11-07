"""Exercise the mock controller with a packet emitted by the #63 producer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from test_github_work_guide import ROOT, change, save_run

sys.path.insert(0, str(ROOT / 'scripts'))
from build_improvement_packet import build_packet
from handoff_improvement import HandoffAdoption, digest, evaluator
from run_mock_improvement import EvaluationError, canonical, control_intake, run
from rehearse_public_execution import rehearse


class MockImprovementTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        snapshot = json.loads((ROOT / 'fixtures/github_work_guide/synthetic.json').read_text())
        snapshot = change(snapshot, 'pr:25',
                          lambda pr: pr['raw']['checks'][0].update(conclusion='failure'))
        source = root / 'runs' / 'source'
        save_run(source, {'snapshot.json': snapshot})
        audit = json.loads((ROOT / 'fixtures/audit/sample.json').read_text())
        audit['baseline_sha'] = snapshot['items']['pr:25']['raw']['detail']['head']['sha']
        self.packet = build_packet(source, {
            'repo': snapshot['repo'], 'snapshot_hash': snapshot['hash'], 'pr_number': 25,
            'observation_id': 'procedure', 'audit_input': audit,
        })
        self.state = root / 'runs' / 'mock-improvement'
        self.receipt = self.state / self.packet['event_id']
        self.base = {'schema_version': 1, 'reason': 'Synthetic skipped step',
                     'evidence_refs': [self.packet['evidence']['audit'][0]['pointer']]}
        self.edit = {'path': self.packet['change_allowlist'][0],
                     'before': 'skip_check()', 'after': 'perform_check()'}

    def test_cli_imports_in_isolated_python(self):
        for script in ('run_mock_improvement.py', 'handoff_improvement.py'):
            with self.subTest(script=script):
                subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts' / script), '--help'],
                               check=True, capture_output=True)

    def test_regression_mounts_readable_snapshot_not_private_target(self):
        self.state.mkdir(parents=True)
        program = self.state / 'private.py'
        data = b'# private fixture artifact'
        program.write_bytes(data)
        program.chmod(0o600)
        controller = HandoffAdoption.__new__(HandoffAdoption)
        controller.repo, controller.area, controller.work = self.state.parents[1], self.state, self.state
        controller.source = lambda: ({'before_hash': digest(data), 'after_hash': digest(data)}, {}, '')
        case = {'input': {'patch': ''}, 'expected': []}
        pinned = {'environment': {}, 'image': {'id': 'fixture-image'}}
        for operation, expected_count in (('ADOPT', 12), ('ROLLBACK', 10)):
            with self.subTest(operation=operation), patch.object(evaluator, 'Sandbox') as factory, \
                    patch.object(evaluator, 'read', side_effect=[pinned, [case] * 12]):
                box = factory.return_value
                box.environment.return_value = pinned['environment']
                box.image_info.return_value = pinned['image']
                def check_snapshot(snapshot, _):
                    self.assertNotEqual(snapshot, program)
                    self.assertEqual(snapshot.read_bytes(), data)
                    self.assertEqual(snapshot.stat().st_mode & 0o777, 0o444)
                    return {'exit': 0, 'container_exit': 0, 'stderr': b'', 'error': None,
                            'oom': False, 'stdout': b'{"findings":[],"cpu_seconds":0}'}
                box.run.side_effect = check_snapshot
                self.assertTrue(controller.regression(program, operation))
                self.assertEqual(box.run.call_count, expected_count)
        self.assertEqual(program.stat().st_mode & 0o777, 0o600)

    def test_proposal_and_durable_duplicate(self):
        response = canonical({**self.base, 'decision': 'PROPOSE', 'edit': self.edit})
        outcome = json.loads(run(self.packet, lambda: response, self.state))
        self.assertEqual(outcome['edit'], self.edit)
        self.assertEqual(outcome['baseline_sha'], self.packet['baseline_sha'])
        self.assertNotIn(self.edit['after'], (self.receipt / 'finished.json').read_text())
        with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
            run(self.packet, lambda: self.fail('mock must not be read again'), self.state)

    def test_stop_persists_until_explicit_resume_without_replaying(self):
        response = canonical({**self.base, 'decision': 'HOLD'})
        run(self.packet, lambda: response, self.state)
        self.assertEqual(control_intake(self.state, 'stop'), 'INTAKE_STOPPED')
        fresh = {**self.packet, 'event_id': 'a' * 64}
        with self.assertRaisesRegex(EvaluationError, 'INTAKE_STOPPED'):
            run(fresh, lambda: self.fail('worker read while stopped'), self.state)
        self.assertFalse((self.state / fresh['event_id']).exists())
        self.assertEqual(control_intake(self.state, 'resume'), 'ACCEPTING')
        run(fresh, lambda: response, self.state)
        with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
            run(self.packet, lambda: self.fail('old event replayed'), self.state)

    def test_corrupt_stop_and_unconfirmed_cleanup_keep_intake_closed(self):
        control_intake(self.state, 'stop')
        marker = self.state / 'intake-stop.json'
        marker.write_text('{}')
        with self.assertRaisesRegex(EvaluationError, 'STOP_RECORD_INVALID'):
            control_intake(self.state, 'resume')
        marker.write_bytes(canonical({'status': 'STOP_REQUESTED'}))
        (self.state / 'isolation-pending.json').write_text('{}')
        for action in ('stop', 'resume'):
            with self.assertRaisesRegex(EvaluationError, 'ISOLATION_PENDING'):
                control_intake(self.state, action)
        with self.assertRaisesRegex(EvaluationError, 'INTAKE_STOPPED'):
            run(self.packet, lambda: self.fail('worker read while stopped'), self.state)

    def test_stop_between_claim_and_isolated_start(self):
        response = canonical({**self.base, 'decision': 'HOLD'})
        claimed, release = Event(), Event()
        errors = []

        def read_response():
            claimed.set()
            if not release.wait(5):
                raise AssertionError('test did not release the reader')
            return response

        def worker():
            try:
                run(self.packet, read_response, self.state, isolated=True)
            except EvaluationError as error:
                errors.append(str(error))

        thread = Thread(target=worker)
        with patch('run_mock_improvement.interrupt_worker',
                   side_effect=lambda *_: release.set()), patch('run_mock_improvement.isolated_response') as isolated:
            thread.start()
            try:
                self.assertTrue(claimed.wait(5))
                self.assertEqual(control_intake(self.state, 'stop'), 'INTAKE_STOPPED')
            finally:
                release.set()
                thread.join(5)
            isolated.assert_not_called()
        self.assertEqual(errors, ['INTAKE_STOPPED'])
        receipt = json.loads((self.receipt / 'finished.json').read_text())
        self.assertEqual(receipt['status'], 'STOPPED')

    def test_public_rehearsal_claims_snapshot_and_preserves_stop(self):
        selected = {'status': 'SELECTED', 'candidate': self.packet}
        with patch('rehearse_public_execution.select', return_value=selected) as select, \
                patch('run_mock_improvement.isolated_response', side_effect=lambda data, *_a, **_k: data) as worker:
            self.assertEqual(rehearse(None, None, self.state, None)['decision'], 'HOLD')
            selected['candidate'] = {**self.packet, 'event_id': 'a' * 64}
            with self.assertRaisesRegex(EvaluationError, 'SNAPSHOT_ALREADY_CLAIMED'):
                rehearse(None, None, self.state, None)
            self.assertEqual(select.call_args.args[2], {self.packet['event_id']})
            self.assertEqual(worker.call_count, 1)
            control_intake(self.state, 'stop')
            with self.assertRaisesRegex(EvaluationError, 'INTAKE_STOPPED'):
                rehearse(None, None, self.state, None)
            self.assertEqual(select.call_count, 2)

    def test_public_rehearsal_stops_before_worker_when_preconditions_fail(self):
        selected = {'status': 'SELECTED', 'candidate': self.packet}
        for reason in ('AUTH_FAILED', 'QUOTA_EXHAUSTED', 'COST_UNVERIFIED'):
            with self.subTest(reason=reason), patch('rehearse_public_execution.select', return_value=selected), \
                    patch('run_mock_improvement.isolated_response') as worker:
                state = self.state / reason
                with self.assertRaisesRegex(EvaluationError, reason):
                    rehearse(None, None, state, None, reason)
                worker.assert_not_called()
                receipt = json.loads((state / self.packet['event_id'] / 'finished.json').read_text())
                self.assertEqual((receipt['status'], receipt['reason']), ('STOPPED', reason))

    def test_non_proposal_decisions(self):
        for decision in ('REUSE', 'NO_CHANGE', 'HOLD'):
            with self.subTest(decision=decision):
                data = canonical({**self.base, 'decision': decision})
                value = json.loads(run(self.packet, lambda: data, self.state / decision))
                self.assertEqual(value['decision'], decision)
                self.assertNotIn('edit', value)

    def test_failures_stop_without_retry(self):
        for reason in ('AUTH_FAILED', 'QUOTA_EXHAUSTED', 'TIMEOUT'):
            with self.subTest(reason=reason):
                state = self.state / reason
                response = canonical({'schema_version': 1, 'decision': reason})
                with self.assertRaisesRegex(EvaluationError, reason):
                    run(self.packet, lambda: response, state)
                receipt = json.loads((state / self.packet['event_id'] / 'finished.json').read_text())
                self.assertEqual((receipt['status'], receipt['reason']), ('STOPPED', reason))
                with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
                    run(self.packet, lambda: self.fail('retry'), state)

    def test_isolated_timeout_discards_response_and_prevents_retry(self):
        with patch('run_mock_improvement.isolated_response', side_effect=EvaluationError('TIMEOUT')) as worker:
            with self.assertRaisesRegex(EvaluationError, 'TIMEOUT'):
                run(self.packet, lambda: b'partial', self.state, isolated=True)
            with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
                run(self.packet, lambda: self.fail('retry'), self.state, isolated=True)
        self.assertEqual(worker.call_count, 1)
        self.assertFalse((self.state / 'isolation-pending.json').exists())
        self.assertEqual(json.loads((self.receipt / 'finished.json').read_text())['reason'], 'TIMEOUT')

    def test_unconfirmed_isolation_blocks_other_events(self):
        error = EvaluationError('ISOLATION_CLEANUP_FAILED')
        error.pending_container = 'hermes-eval-fixture'
        with patch('run_mock_improvement.isolated_response', side_effect=error):
            with self.assertRaisesRegex(EvaluationError, 'ISOLATION_CLEANUP_FAILED'):
                run(self.packet, lambda: b'partial', self.state, isolated=True)
        pending = json.loads((self.state / 'isolation-pending.json').read_text())
        self.assertRegex(pending['container'], r'^hermes-eval-[0-9a-f]{32}$')
        other = {**self.packet, 'event_id': 'a' * 64}
        with self.assertRaisesRegex(EvaluationError, 'ISOLATION_PENDING'):
            run(other, lambda: self.fail('must not start'), self.state, isolated=True)

    def test_rejects_bad_schema_and_path(self):
        response = {**self.base, 'decision': 'PROPOSE', 'edit': self.edit}
        cases = [
            ('EDIT_PATH', canonical({**response, 'edit': {**self.edit, 'path': '../escape.py'}})),
            ('RESPONSE_EVIDENCE', canonical({**response, 'evidence_refs': ['/observations/0/logs/0']})),
            ('RESPONSE_SCHEMA', canonical({**response, 'tool': 'shell'})),
            ('JSON_INVALID', b'{'),
        ]
        for error, payload in cases:
            with self.subTest(error=error), self.assertRaisesRegex(EvaluationError, error):
                run(self.packet, lambda: payload, self.state / error)

    def test_refuses_non_public_packet_before_claim(self):
        with self.assertRaisesRegex(EvaluationError, 'PACKET_SCOPE'):
            run({**self.packet, 'classification': 'INTERNAL'},
                lambda: self.fail('mock read'), self.state)
        self.assertFalse(self.state.exists())

    def test_deadline_discards_valid_response(self):
        response = canonical({**self.base, 'decision': 'NO_CHANGE'})
        clock = iter((0, 1, 5)).__next__
        with self.assertRaisesRegex(EvaluationError, 'TIMEOUT'):
            run(self.packet, lambda: response, self.state, clock)

    def test_concurrent_event_and_interrupted_attempt(self):
        def interrupt():
            other = {**self.packet, 'event_id': 'f' * 64}
            with self.assertRaisesRegex(EvaluationError, 'CONCURRENT_RUN'):
                run(other, lambda: self.fail('concurrent mock read'), self.state)
            self.assertFalse((self.state / other['event_id']).exists())
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run(self.packet, interrupt, self.state)
        self.assertTrue((self.receipt / 'started.json').is_file())
        self.assertFalse((self.receipt / 'finished.json').exists())
        with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
            run(self.packet, lambda: self.fail('restarted mock read'), self.state)


if __name__ == '__main__':
    unittest.main()
