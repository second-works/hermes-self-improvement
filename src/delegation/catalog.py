"""Versioned controller-owned operation catalog; model text never defines code."""
from evaluation.core import EvaluationError, digest, require
from delegation.patch import OPERATION_IDS, apply_operations


CATALOG_VERSION = 1
BASELINE_SHA256 = '091055ee7066c5ea2b8d5d919a7845585793f90b7109ba9a52273ffcfc4239ea'
_DESCRIPTIONS = {
    'count_context_lines': 'Advance the new-file line counter for a context line.',
    'count_added_comments': 'Advance the new-file line counter before skipping an added comment.',
}


def selection_schema():
    return {'type': 'object', 'properties': {'operations': {
        'type': 'array', 'maxItems': len(OPERATION_IDS), 'uniqueItems': True,
        'items': {'type': 'string', 'enum': list(OPERATION_IDS)}}},
        'required': ['operations'], 'additionalProperties': False}


def catalog():
    """Return a fresh public description, without accepting runtime registrations."""
    return {'version': CATALOG_VERSION, 'baseline_sha256': BASELINE_SHA256,
            'selection_schema': selection_schema(),
            'no_change': {'operations': []}, 'operations': [
                {'id': operation, 'version': 1, 'description': _DESCRIPTIONS[operation],
                 'target': 'scripts/review.py',
                 'precondition': 'Required counter insertion is absent and its anchor is unique.',
                 'verification': 'All 15 public contract cases pass without regression.'}
                for operation in OPERATION_IDS]}


def validate_selection(value):
    require(type(value) is dict and set(value) == {'operations'} and
            type(value['operations']) is list and len(value['operations']) <= len(OPERATION_IDS) and
            all(type(op) is str and op in OPERATION_IDS for op in value['operations']),
            'OPERATION_SCHEMA')
    require(len(value['operations']) == len(set(value['operations'])), 'DUPLICATE_OPERATION')
    return tuple(value['operations'])


def registered_source_hashes(baseline):
    """Only the pinned PUBLIC baseline and its four deterministic states are allowed."""
    require(digest(baseline) == BASELINE_SHA256, 'REGISTERED_BASELINE_CHANGED')
    source = baseline.decode('utf-8')
    selections = ([], [OPERATION_IDS[0]], [OPERATION_IDS[1]], list(OPERATION_IDS))
    return {digest(apply_operations(source, {'operations': operations}).encode())
            for operations in selections}


def available_operations(source):
    """Use the actual implementation's preconditions instead of model assertions."""
    result = []
    for operation in OPERATION_IDS:
        try:
            apply_operations(source, {'operations': [operation]})
        except (EvaluationError, SyntaxError):
            continue
        result.append(operation)
    return result
