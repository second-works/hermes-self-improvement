"""Exercise the mock controller with a packet emitted by the #63 producer."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_github_work_guide import ROOT, change, save_run

sys.path.insert(0, str(ROOT / 'scripts'))
from build_improvement_packet import build_packet
from run_mock_improvement import EvaluationError, canonical, run


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

    def test_proposal_and_durable_duplicate(self):
        response = canonical({**self.base, 'decision': 'PROPOSE', 'edit': self.edit})
        outcome = json.loads(run(self.packet, lambda: response, self.state))
        self.assertEqual(outcome['edit'], self.edit)
        self.assertEqual(outcome['baseline_sha'], self.packet['baseline_sha'])
        self.assertNotIn(self.edit['after'], (self.receipt / 'finished.json').read_text())
        with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
            run(self.packet, lambda: self.fail('mock must not be read again'), self.state)

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
