"""Actual script results stay separate from the model and the test oracle."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from delegation.execution import execute_case, execute_batch, execution_cases
from evaluation.core import EvaluationError, canonical


class Unit:
    def __init__(self, stdout):
        self.stdout, self.calls = stdout, []
        self.error, self.exit, self.stderr = None, 0, b''

    def run(self, program, value):
        self.calls.append((program, value))
        return {'stdout': self.stdout, 'error': self.error, 'exit': self.exit,
                'stderr': self.stderr, 'container_exit': 0}


class ExecutionTests(unittest.TestCase):
    def test_serializes_actual_output_without_injecting_expected_answer(self):
        case = execution_cases()[0]
        actual = {'findings': [{'path': case['input']['path'], 'line': 99, 'rule': 'dynamic-eval'}],
                  'cpu_seconds': 0}
        unit = Unit(canonical(actual))
        self.assertEqual(execute_case(unit, 'program', case['input']), actual)
        self.assertEqual(json.loads(unit.calls[0][1]), case['input'])
        self.assertNotIn('expected', unit.calls[0][1].decode())
        self.assertNotEqual(actual['findings'][0]['line'], case['expected'][0][1])

    def test_invalid_input_is_rejected_before_execution(self):
        unit = Unit(b'{}')
        for value in ({'path': '../secret', 'patch': 'x'}, {'path': 'case_valid000.py', 'patch': ''},
                      {'path': 'case_valid000.py', 'patch': 'x', 'expected': []}):
            with self.assertRaises(EvaluationError):
                execute_case(unit, 'program', value)
        self.assertEqual(unit.calls, [])

    def test_fences_wrong_rules_other_paths_and_cpu_are_rejected(self):
        value = execution_cases()[0]['input']
        rows = [{'path': value['path'], 'line': 23, 'rule': 'dynamic-eval'}]
        for data in (b'```json\n{}\n```', canonical({'findings': rows, 'cpu_seconds': 1}),
                     canonical({'findings': [{**rows[0], 'path': 'case_other000.py'}], 'cpu_seconds': 0}),
                     canonical({'findings': [{**rows[0], 'rule': 'prose'}], 'cpu_seconds': 0})):
            with self.assertRaises(EvaluationError):
                execute_case(Unit(data), 'program', value)

    def test_new_profile_extends_only_calls_and_keeps_token_limits(self):
        from delegation.core import specification
        before = specification('cycle100')['budget']
        after = specification('controlled102')['budget']
        self.assertEqual(after['calls'], 102)
        self.assertEqual({k: v for k, v in after.items() if k != 'calls'},
                         {k: v for k, v in before.items() if k != 'calls'})

    def test_runtime_failures_and_unbounded_batches_fail_closed(self):
        value = execution_cases()[0]['input']
        for field, bad in (('error', 'TIMEOUT'), ('exit', 1), ('stderr', b'error')):
            unit = Unit(b'{"findings":[],"cpu_seconds":0}')
            setattr(unit, field, bad)
            with self.assertRaisesRegex(EvaluationError, 'EXECUTION_FAILED'):
                execute_case(unit, 'program', value)
        for values in ([], [value] * 17):
            with self.assertRaisesRegex(EvaluationError, 'EXECUTION_BATCH_SIZE'):
                execute_batch(Unit(b'{}'), 'program', values)


if __name__ == '__main__':
    unittest.main()
