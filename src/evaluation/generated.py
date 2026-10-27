"""Expected input rejection is distinct from infrastructure and output failures."""
from evaluation.core import EvaluationError, findings, load_json


def observe(outcome, case):
    safety_failure = bool(outcome.get('error') or outcome.get('oom'))
    failed = safety_failure or outcome.get('exit') not in (0, 2) or outcome.get('exit') != outcome.get('container_exit') or bool(outcome.get('stderr'))
    correct = False
    kind = 'EXECUTION_FAILURE' if failed else 'WRONG_ANSWER'
    if not failed:
        try:
            if case['exit'] == 2:
                correct = outcome['exit'] == 2 and load_json(outcome['stdout']) == {'error': 'INVALID_INPUT'}
                kind = 'EXPECTED_REJECTION' if correct else 'WRONG_REJECTION'
            elif outcome['exit'] == 0:
                answer, _ = findings(load_json(outcome['stdout']))
                correct = answer == sorted(map(tuple, case['expected']))
                kind = 'CORRECT' if correct else 'WRONG_ANSWER'
            else:
                failed = True
                kind = 'UNEXPECTED_EXIT'
        except (EvaluationError, TypeError, KeyError):
            failed = True
            kind = 'OUTPUT_INVALID'
    return {'correct': correct, 'failed': bool(failed), 'safety_failure': safety_failure,
            'kind': kind, 'wall_seconds': outcome['wall_seconds']}
