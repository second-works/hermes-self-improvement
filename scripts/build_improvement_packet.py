#!/usr/bin/env python3
"""Build one offline improvement packet from a saved run and PUBLIC synthetic evidence.

The evidence JSON binds repo, snapshot_hash, pr_number and observation_id to
an audit_input (Issue #4 schema). Supply previously emitted event IDs through
--seen-event. Exit 0 with a packet or SKIP, or 2 on invalid input.
"""
import argparse
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit.core import AuditError, audit, canonical, decode
from github_work_guide.core import REPO, Invalid, complete, digest, load_run, require

MAX_EVIDENCE_BYTES = 262_144
MAX_PACKET_BYTES = 8_192
SKILL = 'review-builtin'
CHANGE_ALLOWLIST = ('fixtures/skills/github-code-review/review.py',)


def build_packet(run, evidence, seen_events=()):
    snapshot = load_run(run)
    complete(snapshot)
    require(type(evidence) is dict and set(evidence) == {
        'repo', 'snapshot_hash', 'pr_number', 'observation_id', 'audit_input',
    }, 'evidence schema')
    require(evidence['repo'] == REPO and evidence['snapshot_hash'] == snapshot['hash'],
            'observation scope')
    require(type(evidence['pr_number']) is int and evidence['pr_number'] > 0, 'PR number')
    require(all(re.fullmatch(r'[0-9a-f]{64}', event) for event in seen_events), 'event ID')
    raw = evidence['audit_input']
    report = audit(raw)
    diagnosis = next((row for row in report['diagnoses']
                      if row['observation_id'] == evidence['observation_id']), None)
    require(diagnosis is not None, 'unknown observation')
    target = snapshot['items'].get(f'pr:{evidence["pr_number"]}')
    require(target is not None and target['state'] == 'OPEN', 'open PR required')
    head = target['raw']['detail']['head']['sha']
    require(report['baseline_sha'] == head, 'audit head mismatch')
    # A stale check or a superseded failure cannot authorize a proposal.
    check = max((row for row in target['raw']['checks']
                 if row['name'] == 'ci' and row['head_sha'] == head),
                key=lambda row: row['id'], default=None)
    if check is None or (check['status'], check.get('conclusion')) != ('completed', 'failure'):
        return {'status': 'SKIP', 'reason': 'NO_CURRENT_CI_FAILURE'}
    if diagnosis['status'] == 'NO_FAILURE':
        return {'status': 'SKIP', 'reason': 'NO_AUDIT_FAILURE'}
    require(diagnosis['status'] == 'DIAGNOSED', 'unresolved diagnosis')
    observation = next(row for row in raw['observations'] if row['id'] == diagnosis['observation_id'])
    if diagnosis['cause'] != 'procedure' or observation['selected_skill'] != SKILL:
        return {'status': 'SKIP', 'reason': 'OUTSIDE_FIXTURE_SKILL_SCOPE'}
    # Exclude capture time and unrelated changes so repeated collection deduplicates.
    event_id = digest([REPO, target['number'], head, check['id']])
    if event_id in seen_events:
        return {'status': 'SKIP', 'reason': 'ALREADY_SEEN'}
    packet = {
        'schema_version': 1, 'status': 'READY', 'classification': 'PUBLIC',
        'source_kind': 'synthetic-fixture', 'repo': REPO, 'snapshot_hash': snapshot['hash'],
        'event_id': event_id, 'pr_url': target['url'], 'baseline_sha': head,
        'failure_category': diagnosis['cause'], 'target_skill': SKILL,
        'change_allowlist': list(CHANGE_ALLOWLIST),
        'evidence': {'check_id': check['id'], 'observation_id': diagnosis['observation_id'],
                     'audit': diagnosis['evidence']},
    }
    require(len(canonical(packet)) <= MAX_PACKET_BYTES, 'packet too large')
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--run', type=Path, required=True, help='saved synthetic collect run')
    parser.add_argument('--evidence', type=Path, required=True, help='PUBLIC synthetic evidence JSON')
    parser.add_argument('--seen-event', action='append', default=[])
    args = parser.parse_args()
    try:
        fd = os.open(args.evidence, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'invalid evidence file')
            data = stream.read(MAX_EVIDENCE_BYTES + 1)
        require(len(data) <= MAX_EVIDENCE_BYTES, 'evidence too large')
        result = build_packet(args.run, decode(data), args.seen_event)
    except (Invalid, AuditError, OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError):
        print('{"status":"ERROR","reason":"INVALID_IMPROVEMENT_INPUT"}', file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(result) + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
