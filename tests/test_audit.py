"""Independent synthetic expectations, false positives, and read-only CLI boundaries."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit.core import AuditError, CATEGORIES, audit, canonical, decode, digest

spec = importlib.util.spec_from_file_location('audit_fixture', ROOT / 'scripts/audit_fixture.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def sample():
    return json.loads((ROOT / 'fixtures/audit/sample.json').read_bytes())


class AuditContracts(unittest.TestCase):
    def assert_schema(self, value, schema):
        """Check the published schemas' small keyword set without a runtime dependency."""
        if 'anyOf' in schema:
            self.assertTrue(any((value is None and branch.get('type') == 'null') or
                                (type(value) is str and branch.get('type') == 'string' and
                                 re.fullmatch(branch.get('pattern', '.*'), value))
                                for branch in schema['anyOf']))
            return
        if 'const' in schema:
            self.assertEqual(value, schema['const'])
        if 'enum' in schema:
            self.assertIn(value, schema['enum'])
        kind = schema.get('type')
        if kind:
            self.assertIs(type(value), {'object': dict, 'array': list, 'string': str,
                                       'integer': int, 'boolean': bool}[kind])
        if kind == 'object':
            self.assertEqual(set(value), set(schema['required']))
            self.assertFalse(schema['additionalProperties'])
            for name, item in value.items():
                self.assert_schema(item, schema['properties'][name])
        if kind == 'array':
            self.assertLessEqual(len(value), schema['maxItems'])
            for item in value:
                self.assert_schema(item, schema['items'])
        if kind == 'integer':
            self.assertGreaterEqual(value, schema.get('minimum', value))
            self.assertLessEqual(value, schema.get('maximum', value))
        if kind == 'string':
            self.assertRegex(value, schema.get('pattern', '.*'))
            self.assertGreaterEqual(len(value), schema.get('minLength', 0))
            self.assertLessEqual(len(value), schema.get('maxLength', len(value)))

    def test_published_schema_shapes_and_example_match_actual_result(self):
        value = sample()
        report = audit(value)
        for name, data in [('audit-input', value), ('audit-report', report)]:
            schema = json.loads((ROOT / f'schemas/{name}.schema.json').read_bytes())
            self.assert_schema(data, schema)
        example = json.loads((ROOT / 'fixtures/audit/report.example.json').read_bytes())
        self.assertEqual(report, example)

    def test_six_causes_and_independent_expected_counts(self):
        expected = json.loads((ROOT / 'fixtures/audit/expected.json').read_bytes())
        report = audit(sample())
        self.assertEqual({d['observation_id']: d['cause'] for d in report['diagnoses']}, expected['causes'])
        self.assertEqual({d['cause'] for d in report['diagnoses']} - {None}, set(CATEGORIES))
        self.assertEqual(sum(d['status'] == 'HOLD' for d in report['diagnoses']), 2)
        self.assertEqual(sum(d['status'] == 'NO_FAILURE' for d in report['diagnoses']), 1)
        self.assertEqual(len(report['proposals']), expected['proposal_count'])
        self.assertEqual(sum(p['authoring_suggestion'] is not None for p in report['proposals']),
                         expected['skill_authoring_suggestions'])
        gap = next(p for p in report['proposals'] if p['cause'] == 'skill_gap')
        self.assertEqual(gap['observation_ids'], ['gap', 'repeat-gap'])

    def test_evidence_resolves_to_exact_input_log_and_proposal_hash(self):
        value = sample()
        report = audit(value)
        for row in report['diagnoses']:
            for ref in row['evidence']:
                target = value
                for part in ref['pointer'].split('/')[1:]:
                    target = target[int(part)] if type(target) is list else target[part]
                self.assertEqual(target, {'line': ref['line'], 'code': ref['code']})
                self.assertEqual(ref['input_hash'], digest(value))
        for proposal in report['proposals']:
            body = {k: v for k, v in proposal.items() if k != 'proposal_hash'}
            self.assertEqual(proposal['proposal_hash'], digest(body))
            self.assertEqual(proposal['approval'], 'NOT_REQUESTED')
            self.assertEqual(proposal['budget']['api_calls'], 0)

    def test_123_124_is_a_synthetic_disabled_record_difference(self):
        value = sample()
        value['skills'] = [dict(value['skills'][0], id=f'skill-{i}', name=f'skill-{i}',
                                enabled=i < 123) for i in range(124)]
        value['observations'] = []
        counts = audit(value)['inventory']
        self.assertEqual((counts['registered_records'], counts['available_unique_names']), (124, 123))
        self.assertEqual(counts['excluded']['disabled_in_profile'], 1)

    def test_profile_origin_and_duplicate_counts_do_not_double_count(self):
        value = sample()
        counts = audit(value)['inventory']
        self.assertEqual(counts['by_origin'], {'builtin': 1, 'local': 1, 'hub': 1})
        self.assertEqual((counts['registered_records'], counts['profile_filtered_records'],
                          counts['available_unique_names']), (3, 2, 1))
        self.assertEqual(counts['available_skill_ids'], ['review-builtin'])
        value['profile'] = 'research'
        self.assertEqual(audit(value)['inventory']['available_skill_ids'], ['other-local'])

    def test_existing_disabled_incompatible_shadowed_or_other_profile_never_generates_skill(self):
        for change in ({'enabled': False}, {'compatible': False}, {'profile': 'research'}):
            value = sample()
            value['observations'] = [value['observations'][0]]
            value['skills'] = [dict(value['skills'][0], capabilities=['missing'], **change)]
            self.assertEqual(audit(value)['proposals'], [])
        value['skills'] = [dict(value['skills'][0], id='shadow', priority=0, capabilities=['review']),
                           dict(value['skills'][0], id='hidden', priority=1, capabilities=['missing'])]
        self.assertEqual(audit(value)['proposals'], [])

    def test_unknown_or_incomplete_inventory_does_not_establish_a_gap(self):
        for kind in ('inventory', 'tools', 'models', 'auth', 'delegation'):
            value = sample()
            value['observations'] = [value['observations'][0]]
            if kind == 'inventory':
                value['inventory_complete'] = False
            else:
                value[kind][0]['state'] = 'unknown'
            self.assertEqual(audit(value)['proposals'], [])

    def test_errors_cannot_trigger_authoring_even_with_no_skills(self):
        for code, category in [('CONTEXT_LENGTH_EXCEEDED', 'model_limit'),
                               ('HTTP_401', 'permission_api'), ('HTTP_429', 'permission_api'),
                               ('DEPENDENCY_UNAVAILABLE', 'external_dependency')]:
            value = sample()
            value['skills'] = []
            value['observations'] = [dict(value['observations'][0], logs=[{'line': 1, 'code': code}])]
            report = audit(value)
            self.assertEqual(report['diagnoses'][0]['cause'], category)
            self.assertIsNone(report['proposals'][0]['authoring_suggestion'])
            # A simultaneous exhaustive-search signal does not justify creating a skill.
            value['observations'][0]['logs'].append({'line': 2, 'code': 'SEARCH_COMPLETE'})
            self.assertEqual(audit(value)['proposals'], [])

    def test_conflicts_empty_and_contradictory_logs_hold(self):
        for outcome, selected, codes in [('failed', None, []),
                                         ('failed', None, ['SUCCESS']),
                                         ('succeeded', None, []),
                                         ('succeeded', None, ['HTTP_403']),
                                         ('failed', 'review-builtin', ['SELECTION_SKIPPED']),
                                         ('failed', None, ['STEP_SKIPPED']),
                                         ('failed', None, ['HTTP_403', 'CONTEXT_LENGTH_EXCEEDED'])]:
            value = sample()
            value['observations'] = [dict(value['observations'][1], outcome=outcome,
                                          selected_skill=selected,
                                          logs=[{'line': i+1, 'code': code} for i, code in enumerate(codes)])]
            self.assertEqual(audit(value)['diagnoses'][0]['status'], 'HOLD')
            self.assertEqual(audit(value)['proposals'], [])

    def test_blocked_unexplained_resource_and_ineligible_selection_hold(self):
        value = sample()
        value['observations'] = [value['observations'][2]]
        value['auth'][0]['state'] = 'blocked'
        self.assertEqual(audit(value)['proposals'], [])
        value['auth'][0]['state'] = 'ready'
        value['skills'][0]['enabled'] = False
        self.assertEqual(audit(value)['diagnoses'][0]['reason'], 'INELIGIBLE_SELECTION')

    def test_input_contract_rejects_unknown_fields_secret_text_and_bad_references(self):
        mutations = [lambda v: v.update(schema_version=True),
                     lambda v: v.update(observed_at='2026-02-30T00:00:00Z'),
                     lambda v: v.update(classification='CONFIDENTIAL'),
                     lambda v: v.update(source_kind='production'),
                     lambda v: v.update(baseline_sha='main'),
                     lambda v: v['skills'].append(deepcopy(v['skills'][0])),
                     lambda v: v['observations'][0]['logs'][0].update(text='do not echo'),
                     lambda v: v['observations'][0]['logs'][0].update(code='INSTALL_NOW'),
                     lambda v: v['observations'][0].update(tool_id='absent'),
                     lambda v: v['observations'][0].update(selected_skill='absent'),
                     lambda v: v['observations'][0]['logs'][0].update(line=True)]
        for mutate in mutations:
            value = sample()
            mutate(value)
            with self.assertRaises(AuditError):
                audit(value)
        for data in (b'{"a":1,"a":2}', b'{"x":NaN}', b'\xff', b'not-json'):
            with self.assertRaises(AuditError):
                decode(data)

    def test_no_observations_no_proposals_and_input_not_mutated(self):
        value = sample()
        before = deepcopy(value)
        self.assertEqual(canonical(audit(value)), canonical(audit(value)))
        self.assertEqual(value, before)
        value['observations'] = []
        self.assertEqual(audit(value)['proposals'], [])

    def test_cli_reproducible_outside_cwd_without_environment_or_external_calls(self):
        command = [sys.executable, '-I', '-B', str(ROOT / 'scripts/audit_fixture.py'),
                   '--input', 'fixtures/audit/sample.json']
        with tempfile.TemporaryDirectory() as tmp:
            first = subprocess.run(command, cwd=tmp, capture_output=True, env={'HOME': tmp}, check=True)
            second = subprocess.run(command, cwd=tmp, capture_output=True, env={'HOME': tmp}, check=True)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.stderr, b'')
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(json.loads(first.stdout), audit(sample()))

    def test_cli_path_and_file_rejection_never_echoes_data(self):
        for name in ('../private', '/tmp/private', 'runs/hidden.json', 'fixtures/skills/secret'):
            with self.assertRaises(AuditError):
                cli.read_fixture(name)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'fixtures/audit').mkdir(parents=True)
            bad = root / 'fixtures/audit/bad.json'
            with patch.object(cli, 'ROOT', root):
                bad.symlink_to('/tmp')
                with self.assertRaises(OSError):
                    cli.read_fixture('fixtures/audit/bad.json')
                bad.unlink()
                bad.write_bytes(b'x' * 262145)
                with self.assertRaises(AuditError):
                    cli.read_fixture('fixtures/audit/bad.json')
                bad.unlink()
                (root / 'fixtures/audit').rmdir()
                (root / 'fixtures/audit').symlink_to('/tmp')
                with self.assertRaises(AuditError):
                    cli.read_fixture('fixtures/audit/bad.json')


if __name__ == '__main__':
    unittest.main()
