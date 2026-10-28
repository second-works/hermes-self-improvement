"""PUBLIC development fixtures and injected observations; actual model calls are zero."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from worklog_candidates.core import ContractError, canonical, load_snapshot
from worklog_candidates.report import packets, make_report, validate_response

BASE = ROOT/'fixtures/gemma_comparison'
spec = importlib.util.spec_from_file_location('gemma_mock_receiver', BASE/'mock_receiver.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


class Comparison(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((BASE/'manifest.json').read_text())
        self.rubric = json.loads((BASE/'rubric.json').read_text())['cases']

    def response(self, case):
        return {'schema_version': 1, 'coverage_complete': True, 'input_truncated': False,
                'output_truncated': False, 'facts': [
                    {'source_id': case['id'], 'line': f['line'], 'quote': f['quote']}
                    for f in case['required']]}

    def observe(self, value=None, **kwargs):
        case = self.rubric[0]
        source = (BASE/self.manifest['files'][0]['path']).read_text()
        return receiver.receive(source, case, canonical(value or self.response(case)),
                                elapsed=kwargs.pop('elapsed', 1),
                                outcome=kwargs.pop('outcome', 'ok'), **kwargs)

    def test_three_long_public_sources_and_frozen_source_spans(self):
        self.assertEqual(self.manifest['classification'], 'PUBLIC')
        self.assertEqual(len(self.manifest['files']), 3)
        self.assertEqual({f['id'] for f in self.manifest['files']}, {c['id'] for c in self.rubric})
        for f, case in zip(self.manifest['files'], self.rubric):
            raw = (BASE/f['path']).read_bytes()
            text = raw.decode()
            self.assertGreater(len(text), 12000)
            self.assertEqual((len(raw), len(text)), (f['bytes'], f['characters']))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), f['sha256'])
            reused = (ROOT/f['reused_source']).read_bytes()
            self.assertEqual(hashlib.sha256(reused).hexdigest(), f['reused_sha256'])
            self.assertIn(reused.decode(), text)
            for anchor in case['required']:
                self.assertEqual(text.splitlines()[anchor['line']-1], anchor['quote'])
            self.assertEqual(receiver.receive(text, case, canonical(self.response(case)),
                                             elapsed=1, outcome='ok'), 'REVIEW_REQUIRED')

    def test_receiver_never_connects_or_executes(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('process')):
            self.assertEqual(self.observe(), 'REVIEW_REQUIRED')

    def test_unavailable_timeout_and_duplicate_fall_back_without_retry(self):
        for outcome in ('unavailable', 'timeout', 'cancelled'):
            self.assertEqual(self.observe(outcome=outcome), 'DIRECT_UNAVAILABLE')
        for elapsed in (30, 31, -1, float('inf'), float('nan'), True):
            self.assertEqual(self.observe(elapsed=elapsed), 'DIRECT_DEADLINE')
        self.assertEqual(self.observe(elapsed=29.999), 'REVIEW_REQUIRED')
        self.assertEqual(self.observe(already_attempted=True), 'DIRECT_DUPLICATE')

    def test_missing_number_negation_or_fact_is_not_a_usable_digest(self):
        for n in range(3):
            bad = self.response(self.rubric[0]); bad['facts'].pop(n)
            self.assertEqual(self.observe(bad), 'DIRECT_REJECTED')

    def test_wrong_reference_fabrication_and_truncation_rejected(self):
        for field, val in [('line', 0), ('line', True), ('source_id', 'other'),
                           ('quote', '本番への適用は許可されている。')]:
            bad = self.response(self.rubric[0]); bad['facts'][0][field] = val
            self.assertEqual(self.observe(bad), 'DIRECT_REJECTED')
        for key, val in [('coverage_complete', False), ('input_truncated', True),
                         ('output_truncated', True), ('extra', 1)]:
            bad = self.response(self.rubric[0]); bad[key] = val
            self.assertEqual(self.observe(bad), 'DIRECT_REJECTED')

    def test_malformed_json_not_repaired(self):
        source = (BASE/self.manifest['files'][0]['path']).read_text()
        for raw in (b'```json\n{}\n```', b'{"facts":[],"facts":[]}', b'{"x":NaN}', b'\xff'):
            self.assertEqual(receiver.receive(source, self.rubric[0], raw,
                                             elapsed=1, outcome='ok'), 'DIRECT_REJECTED')

    def test_existing_worklog_membership_missing_response_and_hold_preserved(self):
        snapshot = load_snapshot(ROOT/'fixtures/worklog_candidates', 'manifest.json')
        model_packet = packets(snapshot)
        self.assertNotIn('gold', canonical(model_packet).decode())
        self.assertNotIn('path', model_packet['packets'][0]['records'][0])
        case = snapshot['candidates'][0]
        selected = {'schema_version': 1, 'decisions': [{'candidate_id': case['candidate_id'],
            'state': 'hold', 'reason': 'insufficient_context',
            'evidence_ids': [case['records'][0].record_id]}]}
        validate_response(snapshot, canonical(selected))
        report = make_report(snapshot, canonical(selected))
        self.assertEqual(report['status'], 'PARTIAL')
        self.assertEqual(len(report['candidates']), len(snapshot['candidates']))
        self.assertTrue(all(r['state'] == 'hold' for r in report['candidates']))
        bad = deepcopy(selected); bad['decisions'][0]['evidence_ids'] = ['r-unknown']
        with self.assertRaises(ContractError): validate_response(snapshot, canonical(bad))

    def test_measurement_rows_are_empty_and_not_mock_performance(self):
        template = json.loads((BASE/'measurement-template.json').read_text())
        self.assertEqual(template['status'], 'NOT_MEASURED')
        self.assertEqual(template['model_calls'], 0)
        self.assertEqual(len(template['rows']), 6)
        for row in template['rows']:
            self.assertTrue(all(v is None for k,v in row.items() if k not in ('id', 'arm')))


if __name__ == '__main__':
    unittest.main()
