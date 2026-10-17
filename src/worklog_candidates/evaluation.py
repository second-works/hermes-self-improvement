"""Finite synthetic scoring. Labels enter only after classification has finished."""
import re

from .core import STATES, fields, ident, require

ACTIVE = set(STATES[:3])


def evaluate(report, gold):
    fields(gold, 'schema_version classification cases')
    require(type(gold['schema_version']) is int and gold['schema_version'] == 1 and
            gold['classification'] == 'PUBLIC' and type(gold['cases']) is list and
            1 <= len(gold['cases']) <= 64, 'GOLD_SCHEMA')
    expected = {}
    for row in gold['cases']:
        fields(row, 'scenario_id session_id task_id split state evidence')
        for name in ('scenario_id', 'session_id', 'task_id'):
            ident(row[name])
        require(type(row['state']) is str and row['state'] in STATES and
                type(row['split']) is str and row['split'] in ('development', 'evaluation') and
                type(row['evidence']) is list and 1 <= len(row['evidence']) <= 40, 'GOLD_SCHEMA')
        for ref in row['evidence']:
            fields(ref, 'path line_start line_end text record_ids')
            require(type(ref['path']) is str and type(ref['text']) is str and
                    type(ref['line_start']) is int and type(ref['line_end']) is int and
                    1 <= ref['line_start'] <= ref['line_end'] <= 262144 and
                    type(ref['record_ids']) is list and 1 <= len(ref['record_ids']) <= 128 and
                    all(type(i) is str and re.fullmatch('r-[a-f0-9]{64}', i) for i in ref['record_ids']), 'GOLD_SCHEMA')
        key = (row['session_id'], row['task_id'])
        require(key not in expected, 'GOLD_DUPLICATE')
        expected[key] = row
    actual = {(r['session_id'], r['task_id']): r for r in report['candidates']}
    groups = {}
    for split in ('all', 'development', 'evaluation'):
        cases = [v for v in expected.values() if split == 'all' or v['split'] == split]
        matrix, correct, tp, fp, fn, false_open, evidence_missing, hold = {}, 0, 0, 0, 0, 0, 0, 0
        for case in cases:
            row = actual.get((case['session_id'], case['task_id']))
            state = row['state'] if row else 'missing'
            truth = case['state']
            name = truth + ' -> ' + state
            matrix[name] = matrix.get(name, 0) + 1
            correct += state == truth
            tp += state in ACTIVE and truth in ACTIVE
            fp += state in ACTIVE and truth not in ACTIVE
            fn += truth in ACTIVE and state not in ACTIVE
            false_open += truth == 'resolved_in_log' and state in ACTIVE
            hold += state == 'hold'
            selected = [r for r in row['references'] if r['record_id'] in row['evidence_ids']] if row else []
            # Physical source coverage is checkable; it is not semantic entailment.
            for ref in case['evidence']:
                required = {ref['line_start'] + offset for offset, line in enumerate(ref['text'].split('\n')) if line.strip()}
                covered = {line for r in selected if r['path'] == ref['path']
                           for line in range(r['line_start'], r['line_end'] + 1)}
                evidence_missing += not required.issubset(covered)
        groups[split] = {'cases': len(cases), 'correct_states': correct,
                         'hold': hold, 'confusion_matrix': matrix,
                         'active_true_positive': tp, 'active_false_positive': fp,
                         'active_false_negative': fn, 'resolved_false_positive': false_open,
                         'active_precision': tp / (tp + fp) if tp + fp else None,
                         'active_recall': tp / (tp + fn) if tp + fn else None,
                         'missing_gold_evidence_spans': evidence_missing}
    return {'kind': 'finite-synthetic-only', 'model_accuracy_measured': False,
            'semantic_entailment': 'HUMAN_REVIEW_REQUIRED',
            'duplicates': len(report['candidates']) - len(actual),
            'extra_candidates': len(set(actual) - set(expected)), 'splits': groups}
