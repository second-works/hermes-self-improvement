"""Fixed two-factor experiment controls; no answer values in the output schema."""
import copy
from evaluation.core import require

PATCH_SCHEMA = {'type': 'object', 'properties': {'insertions': {
    'type': 'array', 'minItems': 1, 'maxItems': 2,
    'items': {'type': 'object', 'properties': {'after_line': {'type': 'integer'},
                                             'text': {'type': 'string'}},
              'required': ['after_line', 'text'], 'additionalProperties': False}}},
    'required': ['insertions'], 'additionalProperties': False}
CONDITIONS = ((False, False), (False, True), (True, False), (True, True))
OPERATIONS_SCHEMA = {'type': 'object', 'properties': {'operations': {
    'type': 'array', 'maxItems': 2, 'items': {'type': 'string',
    'enum': ['count_context_lines', 'count_added_comments']}}},
    'required': ['operations'], 'additionalProperties': False}


def condition_body(body, condition, output_kind='patch'):
    require(output_kind in ('patch', 'operations'), 'EXPERIMENT_OUTPUT_KIND')
    require(type(condition) is tuple and len(condition) == 2 and
            all(type(value) is bool for value in condition), 'MATRIX_CONDITION')
    thinking, structured = condition
    result = copy.deepcopy(body)
    result['reasoning_effort'] = 'medium' if thinking else 'none'
    result['chat_template_kwargs'] = {'enable_thinking': thinking}
    result['seed'] = 20261017
    result.pop('response_format', None)
    if structured:
        result['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'counter_patch' if output_kind == 'patch' else 'counter_operations',
            'schema': copy.deepcopy(PATCH_SCHEMA if output_kind == 'patch' else OPERATIONS_SCHEMA)}}
    return result


def patch_shape(value):
    if type(value) is not dict or set(value) != {'insertions'}:
        return False
    edits = value['insertions']
    return type(edits) is list and 1 <= len(edits) <= 2 and all(
        type(edit) is dict and set(edit) == {'after_line', 'text'} and
        type(edit['after_line']) is int and type(edit['text']) is str for edit in edits)
