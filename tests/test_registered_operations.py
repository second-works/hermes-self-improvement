"""File adapter and execution boundaries; no Docker, service, or model connection."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.catalog import available_operations, catalog
from delegation.core import public_cases
from delegation.cycle import transfer_cases
from delegation.execution import execution_cases
from delegation.patch import OPERATION_IDS, apply_operations, counter_cases
from delegation.registered import run
from evaluation.core import EvaluationError, canonical, digest

SOURCE = (ROOT / 'fixtures/delegation/registered-operations/review.py').read_bytes()


class FakeSandbox:
    """Supply distinct execution observations, without executing candidate code."""
    wrong = False

    def __init__(self, root, work, image, deadline):
        self.image = image

    def environment(self):
        return {'test_double': True}

    def image_info(self, image):
        return {'id': image}

    def run(self, program, payload):
        value = json.loads(payload)
        cases = public_cases() + counter_cases() + transfer_cases() + execution_cases()
        case = next(case for case in cases if case['input'] == value)
        # Baseline observations deliberately include failures. Verification must use them.
        expected = case['expected']
        if Path(program).name == 'baseline.py' or self.wrong:
            expected = []
        return {'error': None, 'exit': 0, 'stderr': b'', 'container_exit': 0,
                'stdout': canonical({'findings': [{'path': path, 'line': line, 'rule': rule}
                                                  for path, line, rule in expected],
                                     'cpu_seconds': 0})}


class RegisteredTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'runs').mkdir()
        baseline = self.root / 'fixtures/delegation/registered-operations/review.py'
        baseline.parent.mkdir(parents=True)
        baseline.write_bytes(SOURCE)
        self.source = self.root / 'source.py'
        self.source.write_bytes(SOURCE)
        self.selection = self.root / 'selection.json'
        self.selection.write_bytes(canonical({'operations': list(OPERATION_IDS)}))
        self.output = self.root / 'runs/result'

    def test_catalog_is_fixed_and_available_operations_reflect_real_preconditions(self):
        original = copy.deepcopy(catalog())
        altered = catalog()
        altered['operations'][0]['id'] = 'arbitrary'
        self.assertEqual(catalog(), original)
        self.assertEqual(tuple(available_operations(SOURCE.decode())), OPERATION_IDS)
        repaired = apply_operations(SOURCE.decode(), {'operations': list(OPERATION_IDS)})
        self.assertEqual(available_operations(repaired), [])

    def test_default_prepares_without_constructing_a_sandbox_and_preserves_inputs(self):
        selection_before = self.selection.read_bytes()
        with patch('evaluation.sandbox.Sandbox', side_effect=AssertionError('No execution')):
            report = run(self.root, self.source, self.selection, self.output)
        self.assertEqual(report['status'], 'PREPARED_NOT_EXECUTED')
        self.assertEqual(report['model_calls'], 0)
        self.assertEqual(self.source.read_bytes(), SOURCE)
        self.assertEqual(self.selection.read_bytes(), selection_before)
        self.assertEqual(report['candidate_sha256'], digest((self.output / 'candidate.py').read_bytes()))
        self.assertFalse((self.output / 'execution-results.json').exists())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.output / 'candidate.py').stat().st_mode & 0o777, 0o444)
        with self.assertRaises(FileExistsError):
            run(self.root, self.source, self.selection, self.output)

    def test_unknown_duplicate_fenced_or_extra_fields_fail_before_output_creation(self):
        for data in (b'```json\n{}\n```', b'{"operations":[],"operations":[]}',
                     canonical({'operations': ['unknown']}),
                     canonical({'operations': [OPERATION_IDS[0]] * 2}),
                     canonical({'operations': [], 'command': 'anything'})):
            self.selection.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(EvaluationError):
                run(self.root, self.source, self.selection, self.output)
            self.assertFalse(self.output.exists())

    def test_noop_retains_source_and_repeated_operations_are_unavailable(self):
        repaired = apply_operations(SOURCE.decode(), {'operations': list(OPERATION_IDS)})
        self.source.write_text(repaired)
        self.selection.write_bytes(canonical({'operations': []}))
        report = run(self.root, self.source, self.selection, self.output)
        self.assertEqual(report['source_sha256'], report['candidate_sha256'])
        self.selection.write_bytes(canonical({'operations': list(OPERATION_IDS)}))
        with self.assertRaisesRegex(EvaluationError, 'OPERATION_NOT_AVAILABLE'):
            run(self.root, self.source, self.selection, self.root / 'runs/repeated')

    def test_unregistered_sources_and_modified_baseline_fail_before_any_output(self):
        self.selection.write_bytes(canonical({'operations': []}))
        for source in (b'print(42)\n', SOURCE + b'print(42)\n'):
            self.source.write_bytes(source)
            with self.assertRaisesRegex(EvaluationError, 'UNREGISTERED_SOURCE'):
                run(self.root, self.source, self.selection, self.output)
            self.assertFalse(self.output.exists())
        self.source.write_bytes(SOURCE)
        (self.root / 'fixtures/delegation/registered-operations/review.py').write_bytes(SOURCE + b'# changed\n')
        with self.assertRaisesRegex(EvaluationError, 'REGISTERED_BASELINE_CHANGED'):
            run(self.root, self.source, self.selection, self.output)
        self.assertFalse(self.output.exists())

    def test_execution_results_come_from_runner_and_failed_checks_never_pass(self):
        report = run(self.root, self.source, self.selection, self.output,
                     execute=True, sandbox_factory=FakeSandbox)
        self.assertEqual(report['status'], 'VERIFIED')
        self.assertEqual(report['decision'], 'ACCEPTED')
        self.assertEqual(len(report['after']), 15)
        results = json.loads((self.output / 'execution-results.json').read_text())
        self.assertEqual([row['findings'][0]['line'] for row in results], [23, 62])
        class Wrong(FakeSandbox):
            wrong = True
        failed = self.root / 'runs/failed'
        with self.assertRaisesRegex(EvaluationError, 'CANDIDATE_REJECTED'):
            run(self.root, self.source, self.selection, failed,
                execute=True, sandbox_factory=Wrong)
        failure_report = json.loads((failed / 'report.json').read_text())
        self.assertEqual(failure_report['status'], 'FAILED')
        self.assertFalse((failed / 'execution-results.json').exists())

    def test_symlinked_source_or_output_parent_is_rejected(self):
        alias = self.root / 'alias.py'
        alias.symlink_to(self.source)
        with self.assertRaisesRegex(EvaluationError, 'PATH_SYMLINK'):
            run(self.root, alias, self.selection, self.output)
        parent = self.root / 'runs/alias'
        parent.symlink_to(self.root / 'runs', target_is_directory=True)
        with self.assertRaisesRegex(EvaluationError, 'RUN_PARENT'):
            run(self.root, self.source, self.selection, parent / 'result')
        with self.assertRaisesRegex(EvaluationError, 'RUN_BOUNDARY'):
            run(self.root, self.source, self.selection, self.root / 'outside')

    def test_cli_catalog_and_argument_rejection_have_no_runtime_side_effect(self):
        spec = importlib.util.spec_from_file_location('registered_cli', ROOT / 'scripts/run_registered_operations.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch('builtins.print'), patch.object(module, 'run', side_effect=AssertionError('No run')):
            self.assertEqual(module.main(['--catalog']), 0)
            self.assertEqual(module.main(['--catalog', '--execute']), 2)
            self.assertEqual(module.main([]), 2)


if __name__ == '__main__':
    unittest.main()
