"""Pure contracts and host controller boundaries; Docker E2E is a separate mandatory gate."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import (EvaluationError, canonical, digest, findings, judge, load_json,
                             policy, regular, write_new)
from evaluation.sandbox import Sandbox, capture

spec = importlib.util.spec_from_file_location('evaluate_fixture', ROOT / 'scripts/evaluate_fixture.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def metric(correct=None, failures=0, latency=1.0, cost=0):
    return {'correct': correct or [True] * 7 + [False] * 3 + [True] * 7 + [False] * 3,
            'failures': failures, 'latency': latency, 'cost_usd': cost}


class Decisions(unittest.TestCase):
    def test_probe_requires_all_fields_and_reports_only_fixed_denial_code(self):
        value = {field: True for field in controller.PROBE_FIELDS['boundaries']}
        value['python'] = '3.12.99'
        self.assertEqual(controller.probe_result('boundaries', canonical(value)), '3.12.99')
        with self.assertRaises(EvaluationError):
            controller.probe_result('boundaries', b'{"python":"3.12.99"}')
        value['env'] = False
        with self.assertRaisesRegex(EvaluationError, '^DENIAL_ENV$'):
            controller.probe_result('boundaries', canonical(value))

    def test_new_python_sources_parse_without_running_fixture(self):
        for name in [*controller.SOURCES, controller.ARTIFACT, 'tests/test_evaluation.py']:
            if name.endswith('.py'):
                ast.parse(regular(ROOT / name, ROOT))

    def test_report_schema_local_references_resolve(self):
        schema = load_json(regular(ROOT / 'schemas/evaluation-report.schema.json', ROOT))
        def visit(value):
            if type(value) is dict:
                if '$ref' in value:
                    target = schema
                    for part in value['$ref'].split('/')[1:]:
                        target = target[part]
                for item in value.values():
                    visit(item)
            elif type(value) is list:
                for item in value:
                    visit(item)
        visit(schema)
        self.assertEqual(set(schema['required']), set(schema['properties']))

    def test_fixed_policy_matches_file(self):
        self.assertEqual(policy(), load_json(regular(ROOT / 'fixtures/evaluation/policy.json', ROOT)))

    def test_gain_without_regression_passes(self):
        self.assertEqual(judge(metric(), metric([True] * 20), safety=True)['status'], 'PASS')

    def test_baseline_and_no_improvement_hold(self):
        for same in (False, True):
            self.assertEqual(judge(metric(), metric(), safety=True, same_artifact=same)['status'], 'HOLD')

    def test_degradation_fails_even_when_another_case_improves(self):
        values = [True] * 20
        values[0] = False
        self.assertIn('REGRESSION', judge(metric(), metric(values), safety=True)['reasons'])

    def test_safety_failure_dominates_missing_metrics(self):
        self.assertEqual(judge(None, None, safety=False)['status'], 'FAIL')

    def test_missing_safety_and_contamination_hold(self):
        self.assertEqual(judge(metric(), metric([True] * 20), safety=None)['status'], 'HOLD')
        self.assertEqual(judge(metric(), metric([True] * 20), safety=True, contaminated=True)['status'], 'HOLD')

    def test_cost_failure_latency_boundary_and_failure_rate(self):
        for candidate, code in [(metric([True] * 20, cost=0.01), 'COST_LIMIT'),
                                (metric([True] * 20, latency=1.2001), 'LATENCY_LIMIT'),
                                (metric([True] * 20, failures=1), 'FAILURE_RATE_INCREASE')]:
            self.assertIn(code, judge(metric(), candidate, safety=True)['reasons'])
        self.assertEqual(judge(metric(), metric([True] * 20, latency=1.2), safety=True)['status'], 'PASS')

    def test_missing_nonfinite_and_small_samples_hold(self):
        for candidate in ({}, metric([True] * 19), metric([True] * 20, latency=float('nan'))):
            self.assertEqual(judge(metric(), candidate, safety=True)['status'], 'HOLD')

    def test_exact_findings_and_duplicate_or_extra_fields_rejected(self):
        row = {'path': 'case_0123456789abcdef.py', 'line': 5, 'rule': 'dynamic-eval'}
        self.assertEqual(findings({'findings': [row], 'cpu_seconds': 0})[0], [(row['path'], 5, 'dynamic-eval')])
        for payload in [{'findings': [row, row], 'cpu_seconds': 0},
                        {'findings': [], 'cpu_seconds': 0, 'trace': 'PRIVATE'},
                        {'findings': [{**row, 'path': '../private'}], 'cpu_seconds': 0},
                        {'findings': [{**row, 'line': True}], 'cpu_seconds': 0},
                        {'findings': [], 'cpu_seconds': float('inf')}]:
            with self.assertRaises(EvaluationError):
                findings(payload)

    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'\xff', b'not json'):
            with self.assertRaises(EvaluationError):
                load_json(raw)

    def test_repeat_instability_is_evidence_for_hold(self):
        rows = [[{'answer_hash': 'a', 'correct': True, 'failed': False, 'wall_seconds': 1},
                 {'answer_hash': 'b', 'correct': False, 'failed': False, 'wall_seconds': 1}]] * 20
        _, unstable = controller.compare_records({'baseline': rows})
        self.assertTrue(unstable)


class Boundaries(unittest.TestCase):
    def setUp(self):
        (ROOT / 'runs').mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='evaluation-unit-', dir=ROOT / 'runs'))

    def test_regular_rejects_traversal_symlink_directory_fifo_and_size(self):
        target = self.work / 'data'
        write_new(target, b'fixture')
        self.assertEqual(regular(target, self.work), b'fixture')
        link = self.work / 'link'
        link.symlink_to(target)
        os.mkfifo(self.work / 'fifo')
        for path in (self.work / '../outside', link, self.work, self.work / 'fifo'):
            with self.assertRaises(EvaluationError):
                regular(path, self.work)
        with self.assertRaises(EvaluationError):
            regular(target, self.work, 1)
        with self.assertRaises(FileExistsError):
            write_new(target, b'overwrite')

    def test_parent_symlink_is_rejected(self):
        (self.work / 'subdir').mkdir()
        (self.work / 'subdir/file').write_text('fixture')
        (self.work / 'alias').symlink_to(self.work / 'subdir', target_is_directory=True)
        with self.assertRaises(EvaluationError):
            regular(self.work / 'alias/file', self.work)

    def test_capture_drains_both_streams_and_bounds_total(self):
        env = {'PATH': '/usr/bin:/bin'}
        result = capture([sys.executable, '-I', '-c',
                          'import os; os.write(2,b"x"*60000); os.write(1,b"y"*60000)'], env=env, limit=100000)
        self.assertEqual(result['error'], 'OUTPUT_LIMIT')
        self.assertLessEqual(len(result['stdout']) + len(result['stderr']), 100000)

    def test_capture_timeout_and_input(self):
        result = capture([sys.executable, '-I', '-c', 'import time; time.sleep(3)'], env={}, timeout=0.1)
        self.assertEqual(result['error'], 'TIMEOUT')
        result = capture([sys.executable, '-I', '-c', 'import sys; print(sys.stdin.read())'], env={}, data=b'fixture')
        self.assertEqual(result['stdout'], b'fixture\n')

    def test_candidate_options_have_no_host_write_or_inherited_env(self):
        box = Sandbox(ROOT, self.work, 'sha256:' + 'a' * 64)
        options = box.options('test', ROOT / 'fixtures/evaluation/isolation_probe.py')
        for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--pull=never', '--log-driver=none'):
            self.assertIn(flag, options)
        self.assertEqual(options.count('--mount'), 1)
        self.assertNotIn('SSH_AUTH_SOCK', box.env)
        self.assertNotIn('DOCKER_HOST', box.env)
        self.assertNotIn('--privileged', options)
        self.assertNotIn(str(Path.home()), options[options.index(box.image) + 1:])

    def test_docker_configuration_mismatch_stops_before_start(self):
        box = Sandbox(ROOT, self.work, 'sha256:' + 'a' * 64)
        program = ROOT / 'fixtures/evaluation/isolation_probe.py'
        args = box.options('test', program)
        config = {'HostConfig': {
            'NetworkMode': 'none', 'IpcMode': 'none', 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
            'CapAdd': None, 'SecurityOpt': ['no-new-privileges=true'], 'NanoCpus': 1000000000,
            'Memory': 268435456, 'MemorySwap': 268435456, 'PidsLimit': 32,
            'LogConfig': {'Type': 'none'}, 'Privileged': False, 'PidMode': '', 'Devices': [], 'Binds': None,
            'Tmpfs': {'/run/work': 'rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700'}},
            'Config': {'User': '65532:65532', 'WorkingDir': '/run/work', 'Entrypoint': None,
                       'Cmd': args[args.index(box.image) + 1:]},
            'Image': box.image, 'Mounts': [{'Source': str(program), 'Destination': '/input/program.py', 'RW': False}]}
        box.verify_config(config, program)
        for key, bad in [('NetworkMode', 'host'), ('Memory', 0), ('Privileged', True), ('LogConfig', {'Type': 'json-file'})]:
            original = config['HostConfig'][key]
            config['HostConfig'][key] = bad
            with self.assertRaises(EvaluationError):
                box.verify_config(config, program)
            config['HostConfig'][key] = original

    def test_cleanup_failure_breaks_sandbox_and_blocks_more_execution(self):
        box = Sandbox(ROOT, self.work, 'sha256:' + 'a' * 64)
        program = ROOT / 'fixtures/evaluation/isolation_probe.py'
        with patch.object(box, 'checked', return_value=b''), \
             patch.object(box, 'container_exists', return_value=True), \
             patch.object(box, 'verify_config', side_effect=EvaluationError('CONFIG_MISMATCH')), \
             patch.object(box, 'inspect', side_effect=EvaluationError('UNAVAILABLE')):
            with self.assertRaises(EvaluationError):
                box.run(program)
        self.assertTrue(box.broken)
        with self.assertRaises(EvaluationError):
            box.options('test', program)

    def test_ambiguous_create_cleans_named_container_and_stops_sandbox(self):
        box = Sandbox(ROOT, self.work, 'sha256:' + 'a' * 64)
        program = ROOT / 'fixtures/evaluation/isolation_probe.py'
        seen = {'present': False, 'name': None, 'removed': False}
        def checked(*args, **kwargs):
            if args[0] == 'create':
                seen['name'] = args[args.index('--name') + 1]
                seen['present'] = True  # daemon succeeds but the client response is lost
                raise EvaluationError('DOCKER_COMMAND_FAILED')
            if args[0] == 'container':
                return (seen['name'].encode() + b'\n') if seen['present'] else b''
            if args[0] == 'rm':
                self.assertEqual(args[1], seen['name'])
                seen['removed'], seen['present'] = True, False
            return b''
        with patch.object(box, 'checked', side_effect=checked), \
             patch.object(box, 'inspect', return_value={'State': {'Running': False}}):
            with self.assertRaises(EvaluationError):
                box.run(program)
        self.assertTrue(seen['removed'])
        self.assertFalse(seen['present'])
        self.assertTrue(box.broken)

    def test_ambiguous_create_and_unreachable_daemon_break_sandbox(self):
        box = Sandbox(ROOT, self.work, 'sha256:' + 'a' * 64)
        with patch.object(box, 'checked', side_effect=EvaluationError('DOCKER_COMMAND_FAILED')):
            with self.assertRaises(EvaluationError):
                box.run(ROOT / 'fixtures/evaluation/isolation_probe.py')
        self.assertTrue(box.broken)

    def audit_fixture(self):
        save = controller.save
        save(self.work, 'environment.json', {'fixture': True})
        sources = {'fixture': 'a' * 64}
        save(self.work, 'gate.json', {'status': 'VERIFIED', 'sources': sources,
             'probes': {n: 'VERIFIED' for n in (*controller.PROBE_FIELDS, 'timeout', 'output')},
             'environment_hash': digest(regular(self.work / 'environment.json', ROOT / 'runs'))})
        for name in ('public', 'hidden'):
            save(self.work, name + '.json', [])
        manifest = {'run_id': self.work.name, 'sources': sources, 'policy': policy(),
             'dataset_hashes': {name: digest(regular(self.work / (name + '.json'), ROOT / 'runs')) for name in ('public', 'hidden')},
             'environment_hash': digest(regular(self.work / 'environment.json', ROOT / 'runs')),
             'gate_hash': digest(regular(self.work / 'gate.json', ROOT / 'runs'))}
        save(self.work, 'manifest.json', manifest)
        for state, name in [('ENVIRONMENT_PINNED', 'environment'), ('ISOLATION_VERIFIED', 'gate'),
                            ('EVALUATION_FROZEN', 'manifest')]:
            controller.event(self.work, state, digest(regular(self.work / (name + '.json'), ROOT / 'runs')))
        return sources

    def test_audit_checks_original_manifest_and_dataset(self):
        sources = self.audit_fixture()
        with patch.object(controller, 'source_hashes', return_value=sources):
            controller.verify_manifest(self.work)
            original = (self.work / 'manifest.json').read_bytes()
            (self.work / 'manifest.json').write_bytes(original.replace(b'1200', b'1201'))
            with self.assertRaises(EvaluationError):
                controller.verify_manifest(self.work)
            (self.work / 'manifest.json').write_bytes(original)
            (self.work / 'hidden.json').write_bytes(b'["tampered"]')
            with self.assertRaises(EvaluationError):
                controller.verify_manifest(self.work)

    def test_audit_rejects_chain_mutation_and_incomplete_run(self):
        sources = self.audit_fixture()
        with patch.object(controller, 'source_hashes', return_value=sources):
            with self.assertRaises(EvaluationError):
                controller.audit(self.work)
        events = self.work / 'events.jsonl'
        events.write_bytes(events.read_bytes().replace(b'ISOLATION_VERIFIED', b'ISOLATION_MODIFIED'))
        with self.assertRaises(EvaluationError):
            controller.verify_events(self.work)

    def test_bad_sha_and_unknown_run_rejected(self):
        for value in ('main', 'a' * 39, '../outside', 'a' * 40 + ':path'):
            with self.assertRaises(EvaluationError):
                controller.git_bytes(value)
        with self.assertRaises(EvaluationError):
            controller.run_path('../outside')

    def test_controller_lifecycle_public_report_controls_and_single_use(self):
        self.lifecycle()

    def test_controller_interruption_persists_reason_and_keeps_run_locked(self):
        self.lifecycle(fail=True)

    def lifecycle(self, *, fail=False):
        # Inert transport fixture; this never executes a candidate or uses real hidden data.
        sources = {'fixture': 'a' * 64}
        cases = []
        for index in range(10):
            path = f'case_{index:016x}.py'
            rule = 'dynamic-eval' if index < 3 else 'shell-execution'
            expected = [[path, 1, rule]] if index < 6 else []
            cases.append({'input': {'path': path, 'patch': 'synthetic'}, 'expected': expected})
        for name in ('public', 'hidden'):
            controller.save(self.work, name + '.json', cases)
        controller.save(self.work, 'environment.json', {'image': {'id': 'sha256:' + 'a' * 64}})
        controller.save(self.work, 'gate.json', {'status': 'VERIFIED', 'sources': sources,
            'probes': {n: 'VERIFIED' for n in (*controller.PROBE_FIELDS, 'timeout', 'output')},
            'environment_hash': digest(regular(self.work / 'environment.json', ROOT / 'runs'))})
        manifest = {'run_id': self.work.name, 'sources': sources, 'policy': policy(),
            'baseline_sha': 'a' * 40, 'baseline_artifact_hash': digest(b'baseline inert marker'),
            'dataset_hashes': {n: digest(regular(self.work / (n + '.json'), ROOT / 'runs')) for n in ('public', 'hidden')},
            'environment_hash': digest(regular(self.work / 'environment.json', ROOT / 'runs')),
            'gate_hash': digest(regular(self.work / 'gate.json', ROOT / 'runs'))}
        controller.save(self.work, 'manifest.json', manifest)
        for state, name in [('ENVIRONMENT_PINNED', 'environment'), ('ISOLATION_VERIFIED', 'gate'),
                            ('EVALUATION_FROZEN', 'manifest')]:
            controller.event(self.work, state, digest(regular(self.work / (name + '.json'), ROOT / 'runs')))
        class InertTransport:
            def run(self, path, data):
                if fail:
                    raise EvaluationError('TRANSPORT_FAILURE')
                case = load_json(data)
                index = int(case['path'][5:21], 16)
                correct = cases[index]['expected']
                if path.stem == 'degraded' or path.stem == 'baseline' and index >= 3:
                    correct = []
                rows = [{'path': p, 'line': n, 'rule': r} for p, n, r in correct]
                return {'exit': 0, 'stdout': canonical({'findings': rows, 'cpu_seconds': 0}),
                        'stderr': b'', 'error': None, 'oom': False, 'container_exit': 0, 'wall_seconds': 1}
        def artifact(sha):
            return b'baseline inert marker' if sha == 'a' * 40 else b'candidate inert marker'
        with patch.object(controller, 'source_hashes', return_value=sources), \
             patch.object(controller, 'sandbox', return_value=InertTransport()), \
             patch.object(controller, 'git_bytes', side_effect=artifact), \
             patch.object(controller, 'git_command', return_value=b''), \
             contextlib.redirect_stdout(io.StringIO()):
            if fail:
                with self.assertRaisesRegex(EvaluationError, '^TRANSPORT_FAILURE$'):
                    controller.evaluate(self.work, 'a' * 40, 'b' * 40)
                self.assertEqual(controller.read(self.work, 'stopped.json')['reason'], 'TRANSPORT_FAILURE')
                self.assertEqual(controller.verify_events(self.work)[-1]['state'], 'EVALUATION_STOPPED')
                with self.assertRaises(EvaluationError):
                    controller.evaluate(self.work, 'a' * 40, 'b' * 40)
                return
            controller.evaluate(self.work, 'a' * 40, 'b' * 40)
            report = controller.read(self.work, 'report.json')
            self.assertEqual({k: v['status'] for k, v in report['decisions'].items()},
                             {'baseline': 'HOLD', 'candidate': 'PASS', 'degraded': 'FAIL'})
            self.assertNotIn('case_', json.dumps(report))
            schema = load_json(regular(ROOT / 'schemas/evaluation-report.schema.json', ROOT))
            self.assertEqual(set(schema['required']), set(report))
            controller.audit(self.work)
            with self.assertRaises(EvaluationError):
                controller.evaluate(self.work, 'a' * 40, 'b' * 40)
            lock = self.work / 'evaluation-lock.json'
            lock.write_bytes(lock.read_bytes().replace(b'"EVALUATING"', b'"TAMPERED"'))
            with self.assertRaises(EvaluationError):
                controller.audit(self.work)


if __name__ == '__main__':
    unittest.main()
