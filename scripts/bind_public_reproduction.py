#!/usr/bin/env python3
"""Bind a supervisor's local reproduction record to a current public CI failure.

The JSON record requires schema_version 1, the repo, pr_number, head_sha,
check_id and event_id from intake, a lowercase reproduction_sha256, and the
observed FAIL and expected PASS verdicts. The digest identifies evidence
retained by the supervisor. This command checks the binding only.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake_public_failure import intake
from evaluation.core import EvaluationError, load_json, regular
from github_work_guide.collector import GhReadOnly
from github_work_guide.core import Invalid, require

BINDING = ('repo', 'pr_number', 'head_sha', 'check_id', 'event_id')
EVIDENCE_FIELDS = {'schema_version', 'reproduction_sha256', 'observed', 'expected', *BINDING}


def bind(run, pr_number, evidence_path, transport):
    entry = intake(run, pr_number, transport)
    if entry['status'] == 'SKIP':
        return entry
    if evidence_path is None:
        return {'status': 'SKIP', 'reason': 'REPRODUCTION_EVIDENCE_REQUIRED'}
    evidence = load_json(regular(evidence_path, evidence_path.absolute().parent, 2048))
    require(type(evidence) is dict and set(evidence) == EVIDENCE_FIELDS, 'invalid evidence fields')
    require(type(evidence['schema_version']) is int and evidence['schema_version'] == 1,
            'invalid evidence version')
    require(all(type(evidence[key]) is type(entry[key]) and evidence[key] == entry[key]
                for key in BINDING), 'evidence does not match current failure')
    require(evidence['observed'] == 'FAIL' and evidence['expected'] == 'PASS', 'no reproduced discrepancy')
    artifact = evidence['reproduction_sha256']
    require(type(artifact) is str and re.fullmatch(r'[0-9a-f]{64}', artifact) is not None,
            'invalid reproduction digest')
    return {**entry, 'status': 'AWAITING_HUMAN_REVIEW', 'reproduction_sha256': artifact}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    try:
        result = bind(args.run, args.pr, args.evidence, GhReadOnly())
    except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Public reproduction binding failed.', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
