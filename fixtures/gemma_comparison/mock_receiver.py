"""Offline specification example. No transport, timers, model invocation or tool calls."""
import math

from worklog_candidates.core import ContractError, decode, fields, require


def receive(source, rubric, raw, *, elapsed, outcome, already_attempted=False):
    """Judge an injected observation, never enforce a real inference deadline.

    Rubric is evaluator-only. It must not be included in a model prompt.
    A usable result still needs human semantic review against the whole source.
    """
    if already_attempted:
        return 'DIRECT_DUPLICATE'
    if outcome != 'ok':
        return 'DIRECT_UNAVAILABLE'
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed < 30:
        return 'DIRECT_DEADLINE'
    try:
        value = decode(raw)
        fields(value, 'schema_version coverage_complete input_truncated output_truncated facts')
        require(type(value['schema_version']) is int and value['schema_version'] == 1, 'VERSION')
        require(value['coverage_complete'] is True and value['input_truncated'] is False and
                value['output_truncated'] is False, 'COVERAGE')
        require(type(value['facts']) is list and 1 <= len(value['facts']) <= 64, 'FACTS')
        lines = source.splitlines()
        quotes = set()
        for fact in value['facts']:
            fields(fact, 'source_id line quote')
            require(fact['source_id'] == rubric['id'] and type(fact['line']) is int and
                    1 <= fact['line'] <= len(lines) and type(fact['quote']) is str and
                    fact['quote'] == lines[fact['line']-1], 'REFERENCE')
            key = (fact['line'], fact['quote'])
            require(key not in quotes, 'DUPLICATE')
            quotes.add(key)
        require(all((f['line'], f['quote']) in quotes for f in rubric['required']), 'MISSING_FACT')
    except (ContractError, TypeError, ValueError, RecursionError):
        return 'DIRECT_REJECTED'
    return 'REVIEW_REQUIRED'
