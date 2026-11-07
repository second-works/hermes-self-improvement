#!/usr/bin/env python3
"""Record one verified public CI failure for offline reproduction triage."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_public_failure import extract
from github_work_guide.collector import GhReadOnly
from github_work_guide.core import Invalid, REPO, digest

SOURCE_KIND = 'public-github-check'
PUBLIC_FIELDS = ('pr_url', 'pr_number', 'head_sha', 'check_id', 'conclusion', 'snapshot_hash')


def intake(run, pr_number, transport):
    failure = extract(run, pr_number, transport)
    if failure is None:
        return {'status': 'SKIP', 'reason': 'NO_CURRENT_CI_FAILURE'}
    return {
        'schema_version': 1,
        'status': 'AWAITING_REPRODUCTION',
        'classification': 'PUBLIC',
        'source_kind': SOURCE_KIND,
        'repo': REPO,
        'event_id': digest([SOURCE_KIND, REPO, failure['pr_number'], failure['head_sha'], failure['check_id']]),
        **{field: failure[field] for field in PUBLIC_FIELDS},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path, help='verified saved GitHub snapshot directory')
    parser.add_argument('--pr', required=True, type=int)
    args = parser.parse_args()
    try:
        result = intake(args.run, args.pr, GhReadOnly())
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Public failure intake verification failed.', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
