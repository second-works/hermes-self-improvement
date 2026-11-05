#!/usr/bin/env python3
"""Validate one synthetic improvement packet against a local mock response.

Run with --packet and --response. A response has schema_version 1 and a
decision of PROPOSE, REUSE, NO_CHANGE, HOLD, AUTH_FAILED, QUOTA_EXHAUSTED
or TIMEOUT. The first four require reason and evidence_refs (audit pointers
from the packet). PROPOSE also requires edit with path, before and after
text. REUSE refers to the existing target_skill in the packet.

Receipts under runs/mock-improvement retain only hashes and outcomes.
The candidate is a single replacement for downstream evaluation, emitted
on stdout. No candidate is applied or run.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from adoption.core import save, syncdir
from audit.core import CODES
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require
from github_work_guide.core import REPO
from build_improvement_packet import CHANGE_ALLOWLIST, MAX_PACKET_BYTES, SKILL

DEADLINE_SECONDS = 5
MAX_RESPONSE_BYTES = 32_768
STOP_REASONS = ('AUTH_FAILED', 'QUOTA_EXHAUSTED', 'TIMEOUT')


def fields(value, expected, code):
    require(type(value) is dict and set(value) == set(expected.split()), code)


def hex_id(value, size):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{%d}' % size, value) is not None


def packet_refs(packet):
    fields(packet, 'schema_version status classification source_kind repo snapshot_hash '
           'event_id pr_url baseline_sha failure_category target_skill change_allowlist evidence',
           'PACKET_SCHEMA')
    require(type(packet['schema_version']) is int and packet['schema_version'] == 1
            and packet['status'] == 'READY' and packet['classification'] == 'PUBLIC'
            and packet['source_kind'] == 'synthetic-fixture' and packet['repo'] == REPO
            and packet['failure_category'] == 'procedure' and packet['target_skill'] == SKILL
            and packet['change_allowlist'] == list(CHANGE_ALLOWLIST), 'PACKET_SCOPE')
    require(hex_id(packet['event_id'], 64) and hex_id(packet['snapshot_hash'], 64)
            and hex_id(packet['baseline_sha'], 40) and type(packet['pr_url']) is str
            and re.fullmatch(r'https://github\.com/' + re.escape(REPO) + r'/pull/[1-9][0-9]*',
                             packet['pr_url']), 'PACKET_IDENTITY')
    evidence = packet['evidence']
    fields(evidence, 'check_id observation_id audit', 'PACKET_EVIDENCE')
    require(type(evidence['check_id']) is int and evidence['check_id'] > 0
            and type(evidence['observation_id']) is str
            and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', evidence['observation_id'])
            and type(evidence['audit']) is list and 1 <= len(evidence['audit']) <= 32,
            'PACKET_EVIDENCE')
    refs = set()
    for row in evidence['audit']:
        fields(row, 'input_hash pointer line code', 'PACKET_EVIDENCE')
        require(hex_id(row['input_hash'], 64) and type(row['pointer']) is str
                and re.fullmatch(r'/observations/[0-9]+/logs/[0-9]+', row['pointer'])
                and type(row['line']) is int and 1 <= row['line'] <= 1_000_000
                and row['code'] in CODES and row['pointer'] not in refs, 'PACKET_EVIDENCE')
        refs.add(row['pointer'])
    require(any(row['code'] == 'STEP_SKIPPED' for row in evidence['audit']), 'PACKET_EVIDENCE')
    return refs


def response_result(response, refs):
    require(type(response) is dict and type(response.get('schema_version')) is int
            and response['schema_version'] == 1, 'RESPONSE_SCHEMA')
    decision = response.get('decision')
    if decision in STOP_REASONS:
        fields(response, 'schema_version decision', 'RESPONSE_SCHEMA')
        raise EvaluationError(decision)
    require(decision in ('PROPOSE', 'REUSE', 'NO_CHANGE', 'HOLD'), 'RESPONSE_DECISION')
    expected = 'schema_version decision reason evidence_refs'
    fields(response, expected + (' edit' if decision == 'PROPOSE' else ''), 'RESPONSE_SCHEMA')
    reason, selected = response['reason'], response['evidence_refs']
    require(type(reason) is str and 0 < len(reason) <= 1024 and bool(reason.strip())
            and type(selected) is list and 0 < len(selected) <= len(refs)
            and all(type(ref) is str and ref in refs for ref in selected)
            and len(selected) == len(set(selected)), 'RESPONSE_EVIDENCE')
    if decision == 'PROPOSE':
        edit = response['edit']
        fields(edit, 'path before after', 'EDIT_SCHEMA')
        require(edit['path'] in CHANGE_ALLOWLIST, 'EDIT_PATH')
        before, after = edit['before'], edit['after']
        require(type(before) is str and bool(before.strip()) and type(after) is str
                and before != after and len(before) <= 4096 and len(after) <= 4096
                and '\x00' not in before and '\x00' not in after, 'EDIT_TEXT')
    return {key: value for key, value in response.items() if key != 'schema_version'}


def run(packet, read_mock, state_dir, clock=time.monotonic):
    require(len(canonical(packet)) <= MAX_PACKET_BYTES, 'PACKET_SIZE')
    refs = packet_refs(packet)
    require(not any(path.is_symlink() for path in (state_dir, *state_dir.parents)), 'STATE_PATH')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    syncdir(state_dir.parent)
    syncdir(state_dir.parent.parent)
    lock = os.open(state_dir / 'controller.lock',
                   os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EvaluationError('CONCURRENT_RUN') from None
        event_dir = state_dir / packet['event_id']
        try:
            event_dir.mkdir(mode=0o700)
        except FileExistsError:
            raise EvaluationError('EVENT_ALREADY_CLAIMED') from None
        syncdir(state_dir)
        receipt = {'event_id': packet['event_id'], 'packet_hash': digest(canonical(packet))}
        save(event_dir / 'started.json', {**receipt, 'status': 'STARTED', 'mock_attempts': 1})
        deadline = clock() + DEADLINE_SECONDS
        try:
            data = read_mock()
            require(clock() < deadline, 'TIMEOUT')
            require(len(data) <= MAX_RESPONSE_BYTES, 'RESPONSE_SIZE')
            result = {
                'schema_version': 1, **receipt, 'classification': 'PUBLIC',
                'target_skill': SKILL, 'baseline_sha': packet['baseline_sha'],
                **response_result(load_json(data), refs),
            }
            encoded = canonical(result)
            require(clock() < deadline, 'TIMEOUT')
        except (EvaluationError, OSError) as error:
            reason = str(error) if isinstance(error, EvaluationError) else 'MOCK_READ_FAILED'
            save(event_dir / 'finished.json', {**receipt, 'status': 'STOPPED', 'reason': reason})
            raise EvaluationError(reason) from None
        save(event_dir / 'finished.json', {**receipt, 'status': 'COMPLETED',
                                          'decision': result['decision'], 'result_hash': digest(encoded)})
        return encoded
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--response', type=Path, required=True)
    args = parser.parse_args()
    try:
        packet = load_json(regular(args.packet, args.packet.absolute().parent, MAX_PACKET_BYTES))
        encoded = run(packet, lambda: regular(args.response, args.response.absolute().parent,
                                              MAX_RESPONSE_BYTES), ROOT / 'runs' / 'mock-improvement')
    except (EvaluationError, OSError, RecursionError) as error:
        reason = str(error) if isinstance(error, EvaluationError) else 'INPUT_OR_STATE_ERROR'
        print(canonical({'status': 'STOPPED', 'reason': reason}).decode(), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(encoded + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
