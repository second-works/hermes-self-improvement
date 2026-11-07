#!/usr/bin/env python3
"""Select at most one public CI failure from a completed point-in-time inspection.

The supervisor's evidence directory holds records named <event_id>.json.
The caller supplies previously claimed event IDs. Selection neither claims
an event nor authorizes model execution.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bind_public_reproduction import bind
from evaluation.core import EvaluationError
from extract_public_failure import latest_ci
from github_work_guide.collector import GhReadOnly
from github_work_guide.core import Invalid, complete, load_run, require
from intake_public_failure import failure_event_id


def select(run, evidence_dir, seen_events, transport):
    snapshot = load_run(run)
    complete(snapshot)
    require(evidence_dir.is_dir() and not any(
        path.is_symlink() for path in (evidence_dir, *evidence_dir.parents)), 'invalid evidence directory')
    seen = set(seen_events)
    require(all(isinstance(event, str) and re.fullmatch(r'[0-9a-f]{64}', event)
                for event in seen), 'invalid seen event')
    skipped = Counter()
    pull_requests = sorted(
        (item for item in snapshot['items'].values() if item['kind'] == 'pr' and item['state'] == 'OPEN'),
        key=lambda item: item['number'],
    )
    for item in pull_requests:
        raw = item['raw']
        head = raw['detail']['head']['sha']
        check = latest_ci(raw['checks'], head)
        if check is None or (check['status'], check.get('conclusion')) != ('completed', 'failure'):
            skipped['NO_SAVED_CI_FAILURE'] += 1
            continue
        event = failure_event_id(item['number'], head, check['id'])
        if event in seen:
            skipped['ALREADY_CLAIMED'] += 1
            continue
        evidence = evidence_dir / (event + '.json')
        if not os.path.lexists(evidence):
            skipped['REPRODUCTION_EVIDENCE_REQUIRED'] += 1
            continue
        record = bind(run, item['number'], evidence, transport)
        if record['status'] == 'SKIP':
            skipped[record['reason']] += 1
            continue
        require(record['status'] == 'AWAITING_HUMAN_REVIEW'
                and record['event_id'] == event and record['snapshot_hash'] == snapshot['hash'],
                'selection changed during verification')
        return {'status': 'SELECTED', 'candidate': record, 'skipped': dict(skipped)}
    return {'status': 'SKIP', 'reason': 'NO_ELIGIBLE_PUBLIC_FAILURE', 'skipped': dict(skipped)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--seen-event', action='append', default=[])
    args = parser.parse_args()
    try:
        result = select(args.run, args.evidence_dir, args.seen_event, GhReadOnly())
    except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Public failure selection failed.', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
