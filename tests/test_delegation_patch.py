"""Scope rejection tests for counter-only insertions; no model or generated code execution."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evaluation.core import EvaluationError
from delegation.patch import apply_counter_patch, counter_cases, apply_operations, OPERATION_IDS
from delegation.core import correct_output

SOURCE = ("def inspect(lines):\n    current_line_num = 0\n    for line in lines:\n"
          "        if line.startswith('@@'):\n            current_line_num = 7\n"
          "        elif line.startswith('+'):\n            content = line[1:]\n"
          "            if content.startswith('#'):\n                continue\n"
          "            current_line_num += 1\n    return current_line_num\n")
CONTEXT = "        elif line.startswith(' '):\n            current_line_num += 1\n"
COMMENT = '                current_line_num += 1\n'


class PatchTests(unittest.TestCase):
    def test_only_authorized_insertions_preserve_every_original_byte(self):
        edits = [{'after_line': 5, 'text': CONTEXT}, {'after_line': 8, 'text': COMMENT}]
        actual = apply_counter_patch(SOURCE, {'insertions': edits})
        self.assertEqual(actual.replace(CONTEXT, '').replace(COMMENT, ''), SOURCE)
        self.assertEqual(apply_counter_patch(SOURCE, {'insertions': edits[::-1]}), actual)

    def test_scope_and_full_replacement_are_rejected(self):
        for value in ({'script': SOURCE}, {'insertions': []},
                      {'insertions': [{'after_line': 5, 'text': CONTEXT + '        print(1)\n'}]},
                      {'insertions': [{'after_line': 1, 'text': CONTEXT}]},
                      {'insertions': [{'after_line': True, 'text': CONTEXT}]},
                      {'insertions': [{'after_line': 5, 'text': CONTEXT}] * 2},
                      {'insertions': [{'after_line': 8, 'text': '                eval(data)\n'}]}):
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                apply_counter_patch(SOURCE, value)

    def test_operation_variants_and_rejections(self):
        both = apply_operations(SOURCE, {'operations': list(OPERATION_IDS)})
        self.assertEqual(apply_operations(both, {'operations': []}), both)
        for first, second in (OPERATION_IDS, OPERATION_IDS[::-1]):
            partial = apply_operations(SOURCE, {'operations': [first]})
            self.assertEqual(apply_operations(partial, {'operations': [second]}), both)
            with self.assertRaisesRegex(EvaluationError, 'OPERATION_ALREADY_PRESENT'):
                apply_operations(partial, {'operations': [first]})
        for value in ({'operations': ['unknown']}, {'operations': [OPERATION_IDS[0]] * 2},
                      {'operations': [], 'extra': 1}, {'operations': 'count_context_lines'}):
            with self.assertRaises(EvaluationError):
                apply_operations(SOURCE, value)

    def test_unknown_baseline_is_rejected(self):
        with self.assertRaisesRegex(EvaluationError, 'PATCH_BASELINE_SCOPE'):
            apply_counter_patch('print(1)\n', {'insertions': [{'after_line': 1, 'text': COMMENT}]})

    def test_extra_cases_cover_context_deletion_and_comment_line_counts(self):
        cases = counter_cases()
        self.assertEqual([case['expected'][0][1] for case in cases], [9, 8, 8])
        self.assertTrue(all(case['expected'][0][2] == 'dynamic-eval' for case in cases))
        for case in cases:
            path, line, rule = case['expected'][0]
            self.assertTrue(correct_output({'findings': [{'path': path, 'line': line, 'rule': rule}],
                                            'cpu_seconds': 0}, case))


if __name__ == '__main__':
    unittest.main()
