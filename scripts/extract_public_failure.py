#!/usr/bin/env python3
"""Extract one public PR's failure metadata from a verified saved snapshot."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from github_work_guide.collector import Collector, GhReadOnly, PREFIX
from github_work_guide.core import Invalid, REPO, complete, load_run, number, require, source_url


def latest_ci(checks, head):
    matches = [row for row in checks if row['name'] == 'ci' and row['head_sha'] == head]
    require(all(type(row['id']) is int and row['id'] > 0 for row in matches), 'invalid check ID')
    require(len({row['id'] for row in matches}) == len(matches), 'duplicate check ID')
    return max(matches, key=lambda row: row['id'], default=None)


def extract(run, pr_number, transport):
    snapshot = load_run(run)
    complete(snapshot)
    target = snapshot['items'].get(f'pr:{number(pr_number)}')
    if target is None or target['state'] != 'OPEN':
        return None
    raw = target['raw']
    head = raw['detail']['head']['sha']
    check = latest_ci(raw['checks'], head)
    if check is None or (check['status'], check.get('conclusion')) != ('completed', 'failure'):
        return None
    metadata = transport.get(PREFIX, None, 10)
    require(metadata.get('full_name') == REPO and metadata.get('private') is False
            and metadata.get('visibility') == 'public', 'PUBLIC repo required')
    live = transport.get(f'{PREFIX}/pulls/{pr_number}', None, 10)
    require(live.get('number') == pr_number and live.get('html_url') == source_url('pr', pr_number),
            'PR identity mismatch')
    if live.get('state') != 'open' or live['head']['sha'] != head:
        return None
    rows = Collector(transport=transport).pages(f'{PREFIX}/commits/{head}/check-runs', 'check_runs')
    current = latest_ci(rows, head)
    if current is None or (current['id'], current['status'], current.get('conclusion')) != (
            check['id'], 'completed', 'failure'):
        return None
    return {'pr_url': source_url('pr', pr_number), 'pr_number': pr_number,
            'head_sha': head, 'check_id': check['id'], 'conclusion': 'failure',
            'snapshot_hash': snapshot['hash']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--pr', type=int, required=True)
    args = parser.parse_args()
    try:
        result = extract(args.run, args.pr, GhReadOnly())
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Saved snapshot or GitHub verification failed.', file=sys.stderr)
        return 2
    print(json.dumps(result if result is not None else {'status': 'SKIP'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
