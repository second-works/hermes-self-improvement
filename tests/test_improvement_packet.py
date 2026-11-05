"""Compose the existing PUBLIC synthetic collect and audit fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_github_work_guide import ROOT, change, save_run, seal

sys.path.insert(0, str(ROOT / 'scripts'))
from build_improvement_packet import Invalid, MAX_EVIDENCE_BYTES, build_packet


class ImprovementPacketTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        synthetic = json.loads((ROOT / 'fixtures/github_work_guide/synthetic.json').read_text())
        self.failed = change(synthetic, 'pr:25',
                             lambda pr: pr['raw']['checks'][0].update(conclusion='failure'))
        audit_input = json.loads((ROOT / 'fixtures/audit/sample.json').read_text())
        audit_input['baseline_sha'] = self.failed['items']['pr:25']['raw']['detail']['head']['sha']
        self.evidence = {'repo': synthetic['repo'], 'snapshot_hash': self.failed['hash'],
                         'pr_number': 25, 'observation_id': 'procedure', 'audit_input': audit_input}
        self.healthy = synthetic

    def save(self, name, snapshot):
        run = self.root / 'runs' / name
        save_run(run, {'snapshot.json': snapshot})
        self.evidence['snapshot_hash'] = snapshot['hash']
        return run

    def test_packet_and_repeat_collection(self):
        packet = build_packet(self.save('first', self.failed), self.evidence)
        self.assertEqual(packet['status'], 'READY')
        self.assertEqual(packet['failure_category'], 'procedure')
        self.assertEqual(packet['evidence']['audit'][0]['code'], 'STEP_SKIPPED')
        self.assertEqual(packet['change_allowlist'], ['fixtures/skills/github-code-review/review.py'])
        run = self.save('second', seal(self.failed['items'], self.failed['coverage']))
        repeated = build_packet(run, self.evidence)
        self.assertEqual(repeated['event_id'], packet['event_id'])
        self.assertEqual(build_packet(run, self.evidence, [packet['event_id']])['reason'], 'ALREADY_SEEN')

    def test_distinct_observations_of_same_failed_check(self):
        run = self.save('distinct', self.failed)
        audit_input = self.evidence['audit_input']
        first = next(row for row in audit_input['observations'] if row['id'] == 'procedure')
        audit_input['observations'].append({**first, 'id': 'other-procedure',
                                            'logs': [{'line': 2, 'code': 'STEP_SKIPPED'}]})
        packet = build_packet(run, self.evidence)
        other = {**self.evidence, 'observation_id': 'other-procedure'}
        second = build_packet(run, other, [packet['event_id']])
        self.assertEqual(second['status'], 'READY')
        self.assertNotEqual(second['event_id'], packet['event_id'])
        self.assertEqual(second['evidence']['audit'][0]['line'], 2)

    def test_healthy_and_superseded_failure(self):
        self.assertEqual(build_packet(self.save('healthy', self.healthy), self.evidence)['reason'],
                         'NO_CURRENT_CI_FAILURE')
        recovered = change(self.failed, 'pr:25', lambda pr: pr['raw']['checks'].append(
            {**pr['raw']['checks'][0], 'id': 999, 'conclusion': 'success'}))
        self.assertEqual(build_packet(self.save('recovered', recovered), self.evidence)['reason'],
                         'NO_CURRENT_CI_FAILURE')

    def test_rejects_incomplete_unbound_and_unknown(self):
        incomplete = seal({}, {**self.failed['coverage'], 'status': 'INCOMPLETE'})
        with self.assertRaises(Invalid):
            build_packet(self.save('incomplete', incomplete), self.evidence)
        run = self.save('complete', self.failed)
        for key, bad in [('repo', 'other/project'), ('snapshot_hash', 'a' * 64),
                         ('observation_id', 'unknown')]:
            with self.subTest(key=key), self.assertRaises(Invalid):
                build_packet(run, {**self.evidence, key: bad})
        unclassified = self.evidence['audit_input']
        row = next(row for row in unclassified['observations'] if row['id'] == 'procedure')
        row['logs'][0]['code'] = 'UNKNOWN'
        with self.assertRaises(Invalid):
            build_packet(run, self.evidence)

    def test_modified_run_and_wrong_head_fail_closed(self):
        run = self.save('wrong-head', self.failed)
        self.evidence['audit_input']['baseline_sha'] = 'f' * 40
        with self.assertRaises(Invalid):
            build_packet(run, self.evidence)
        run = self.save('tampered', self.failed)
        with (run / 'snapshot.json').open('a') as stream:
            stream.write(' ')
        with self.assertRaises(Invalid):
            build_packet(run, self.evidence)

    def test_cli_bounds_evidence_and_does_not_echo_it(self):
        run = self.save('cli', self.failed)
        path = self.root / 'input.json'
        command = [sys.executable, '-I', '-B', str(ROOT / 'scripts/build_improvement_packet.py'),
                   '--run', str(run), '--evidence', str(path)]
        path.write_text(json.dumps(self.evidence))
        ready = subprocess.run(command, capture_output=True, check=True)
        self.assertEqual(json.loads(ready.stdout)['status'], 'READY')
        path.write_bytes(b'x' * (MAX_EVIDENCE_BYTES + 1))
        refused = subprocess.run(command, capture_output=True)
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, b'')
        self.assertEqual(json.loads(refused.stderr)['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
