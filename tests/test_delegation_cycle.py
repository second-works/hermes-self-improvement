"""Improvement adoption policy: regressions and partial repairs never pass."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from delegation.cycle import acceptance, transfer_cases
from delegation.core import specification
from evaluation.core import EvaluationError


class CycleTests(unittest.TestCase):
    def test_improvement_requires_full_success_without_regression(self):
        self.assertEqual(acceptance([True, False], [True, True]), 'ACCEPTED')
        self.assertEqual(acceptance([True, False], [False, True]), 'REJECTED_REGRESSION')
        self.assertEqual(acceptance([False, False], [True, False]), 'REJECTED_INCOMPLETE')
        self.assertEqual(acceptance([True], [True]), 'REJECTED_NO_IMPROVEMENT')
        self.assertEqual(acceptance([True], [True], True), 'UNCHANGED')

    def test_invalid_or_inconsistent_measurements_fail_closed(self):
        for before, after, unchanged in (([], [], False), ([True], [], False),
                                         ([1], [True], False), ([False], [True], True)):
            with self.assertRaises(EvaluationError):
                acceptance(before, after, unchanged)

    def test_transfer_suite_uses_different_inputs_and_budget_stays_bounded(self):
        from delegation.core import public_cases
        from delegation.patch import counter_cases
        prior = public_cases() + counter_cases()
        cases = transfer_cases()
        self.assertEqual(len(cases), 6)
        self.assertTrue(all(case['input'] not in [x['input'] for x in prior] for case in cases))
        from delegation.core import correct_output
        for case in cases:
            output = {'findings': [{'path': path, 'line': line, 'rule': rule}
                                    for path, line, rule in case['expected']], 'cpu_seconds': 0}
            self.assertTrue(correct_output(output, case))
        budget = specification('cycle100')['budget']
        self.assertEqual((budget['calls'], budget['input_tokens'], budget['output_tokens']),
                         (100, 400000, 80000))


if __name__ == '__main__':
    unittest.main()
