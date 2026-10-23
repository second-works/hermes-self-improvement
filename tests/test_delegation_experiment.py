"""Experiment isolation and format-vs-meaning contracts; no live model calls."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from delegation.experiment import CONDITIONS, PATCH_SCHEMA, OPERATIONS_SCHEMA, condition_body, patch_shape
from delegation.relay import LocalModel
from evaluation.core import EvaluationError

REQUEST = {'model': 'gemma-4-e4b', 'messages': [{'role': 'user', 'content': 'PUBLIC'}],
           'max_tokens': 32, 'stream': False}


class ExperimentTests(unittest.TestCase):
    def test_four_conditions_change_only_requested_factors(self):
        original = copy.deepcopy(REQUEST)
        for thinking, schema in CONDITIONS:
            value = condition_body(REQUEST, (thinking, schema))
            self.assertEqual(value['chat_template_kwargs'], {'enable_thinking': thinking})
            self.assertEqual(value['reasoning_effort'], 'medium' if thinking else 'none')
            self.assertEqual(value['messages'], REQUEST['messages'])
            self.assertEqual('response_format' in value, schema)
            if schema:
                self.assertEqual(value['response_format']['json_schema']['schema'], PATCH_SCHEMA)
        self.assertEqual(REQUEST, original)
        for bad in ((1, False), (True,), [True, False]):
            with self.assertRaisesRegex(EvaluationError, 'MATRIX_CONDITION'):
                condition_body(REQUEST, bad)

    def test_schema_does_not_encode_correct_patch_or_line_numbers(self):
        self.assertTrue(patch_shape({'insertions': [{'after_line': -999, 'text': 'wrong'}]}))
        self.assertFalse(patch_shape({'insertions': [{'after_line': True, 'text': 'wrong'}]}))
        self.assertFalse(patch_shape({'insertions': []}))
        text = str(PATCH_SCHEMA)
        self.assertNotIn('current_line_num', text)
        self.assertNotIn('enum', text)

    def test_operations_schema_allows_noop_and_all_choices_without_fixture_answers(self):
        schema = condition_body(REQUEST, (True, True), 'operations')['response_format']['json_schema']['schema']
        self.assertEqual(schema, OPERATIONS_SCHEMA)
        choices = schema['properties']['operations']
        self.assertNotIn('minItems', choices)
        self.assertEqual(choices['maxItems'], 2)
        self.assertEqual(choices['items']['enum'], ['count_context_lines', 'count_added_comments'])
        self.assertNotIn('default', choices)
        self.assertNotIn('const', choices)
        with self.assertRaisesRegex(EvaluationError, 'EXPERIMENT_OUTPUT_KIND'):
            condition_body(REQUEST, (True, True), 'untrusted')

    def test_real_thinking_marker_is_required_before_completion(self):
        calls = []
        def exchange(path, value):
            calls.append((path, value))
            if path == '/apply-template':
                return {'prompt': 'PUBLIC without requested thinking prefix'}
            raise AssertionError('No tokenizer or completion may run after marker mismatch')
        relay = LocalModel(exchange=exchange)
        relay.condition = (True, False)
        with self.assertRaisesRegex(EvaluationError, 'THINKING_TEMPLATE_UNVERIFIED'):
            relay.complete(REQUEST)
        self.assertEqual(relay.calls, 0)
        self.assertEqual(len(calls), 1)

    def test_schema_and_thinking_reach_preflight_and_completion_identically(self):
        calls = []
        def exchange(path, value):
            calls.append((path, value))
            if path == '/apply-template':
                return {'prompt': '<|think|>PUBLIC'}
            if path == '/tokenize':
                return {'tokens': [1] * 10}
            return {'model': 'gemma-4-e4b', 'usage': {'prompt_tokens': 10, 'completion_tokens': 2},
                    'choices': [{'finish_reason': 'stop', 'message': {'content': '{}', 'reasoning_content': 'fixture'}}]}
        relay = LocalModel(exchange=exchange)
        relay.condition = (True, True)
        relay.complete(REQUEST)
        self.assertEqual(calls[0][1], calls[2][1])
        self.assertTrue(relay.condition_observations[0]['thinking_prompt_observed'])
        self.assertEqual(relay.condition_observations[0]['reasoning_characters'], 7)


if __name__ == '__main__':
    unittest.main()
