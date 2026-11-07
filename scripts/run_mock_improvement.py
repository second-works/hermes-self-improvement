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
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from adoption.core import save, syncdir
from audit.core import CODES
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require
from github_work_guide.core import REPO
from evaluation.sandbox import Sandbox
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_improvement_packet import CHANGE_ALLOWLIST, MAX_PACKET_BYTES, SKILL

DEADLINE_SECONDS = 5
ISOLATED_DEADLINE_SECONDS = 30
MOCK_IMAGE = 'python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'
MOCK_PROGRAM = ROOT / 'fixtures/shadow-improvement/worker.py'
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


def isolated_response(data, event_dir, deadline, name, *, stall=False):
    sandbox = Sandbox(ROOT, event_dir, deadline=deadline)
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'TIMEOUT')
    image = load_json(sandbox.checked('image', 'inspect', MOCK_IMAGE, timeout=remaining))[0]
    sandbox.image = image['Id']
    require(image['Os'] == 'linux' and image['Architecture'] == 'arm64', 'IMAGE_BOUNDARY')
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'TIMEOUT')
    result = sandbox.run(MOCK_PROGRAM, (b'1' if stall else b'0') + data, timeout=remaining, name=name)
    require(result['error'] != 'TIMEOUT' and time.monotonic() < deadline, 'TIMEOUT')
    require(not result['error'] and result['exit'] == 0 and result['container_exit'] == 0
            and not result['oom'], 'MOCK_WORKER_FAILED')
    return result['stdout']


STOP_RECORD = {'status': 'STOP_REQUESTED'}


def prepare_state(state_dir):
    require(not any(path.is_symlink() for path in (state_dir, *state_dir.parents)), 'STATE_PATH')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    syncdir(state_dir.parent)
    syncdir(state_dir.parent.parent)


@contextmanager
def state_lock(state_dir, filename):
    fd = os.open(state_dir / filename,
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EvaluationError('CONCURRENT_RUN') from None
        yield
    finally:
        os.close(fd)


def reject_stopped(marker):
    require(not os.path.lexists(marker), 'INTAKE_STOPPED')


def interrupt_worker(state_dir, pending):
    if state_dir == ROOT / 'runs/public-hermes':
        from evaluate_skill_semantics import interrupt
        interrupt()
    if not os.path.lexists(pending):
        return
    try:
        record = load_json(regular(pending, state_dir, 1024))
    except FileNotFoundError:
        # The worker may have removed the receipt while completing normally.
        return
    cloud = record.get('worker_kind') == 'hermes-cloud-v1' if isinstance(record, dict) else False
    fields(record, 'event_id packet_hash container' + (' worker_kind' if cloud else ''), 'PENDING_SCHEMA')
    name = record['container']
    require(hex_id(record['event_id'], 64) and hex_id(record['packet_hash'], 64)
            and isinstance(name, str) and re.fullmatch(r'hermes-eval-[0-9a-f]{32}', name),
            'PENDING_SCHEMA')
    event_dir = state_dir / record['event_id']
    started = load_json(regular(event_dir / 'started.json', state_dir, 1024))
    require(started == {'event_id': record['event_id'], 'packet_hash': record['packet_hash'],
                        'status': 'STARTED', ('model_attempt_budget' if cloud else 'mock_attempts'): 1}, 'PENDING_BINDING')
    if cloud:
        from delegation.hermes_cloud import CloudSandbox, IMAGE, WORKER_PATH
        box = CloudSandbox(ROOT, event_dir, IMAGE)
        program = ROOT / WORKER_PATH
    else:
        box = Sandbox(ROOT, event_dir)
        program = MOCK_PROGRAM
    if not box.container_exists(name):
        return
    try:
        info = box.inspect(name, timeout=5)
        if not info['State']['Running']:
            return
        if not cloud:
            image = load_json(box.checked('image', 'inspect', MOCK_IMAGE, timeout=5))[0]
            box.image = image['Id']
        box.verify_config(info, program)
        # Use the inspected container ID, so a name being reused cannot redirect the kill.
        require(hex_id(info['Id'], 64), 'CONTAINER_IDENTITY_UNKNOWN')
        box.checked('kill', info['Id'], timeout=5)
    except EvaluationError:
        if box.container_exists(name):
            raise


def control_intake(state_dir, action):
    prepare_state(state_dir)
    marker = state_dir / 'intake-stop.json'
    pending = state_dir / 'isolation-pending.json'
    with state_lock(state_dir, 'intake.lock'):
        if action == 'resume':
            with state_lock(state_dir, 'controller.lock'):
                require(not os.path.lexists(pending), 'ISOLATION_PENDING')
                require(load_json(regular(marker, state_dir, 1024)) == STOP_RECORD, 'STOP_RECORD_INVALID')
                marker.unlink()
                syncdir(state_dir)
            return 'ACCEPTING'
        if not os.path.lexists(marker):
            save(marker, STOP_RECORD)
        require(load_json(regular(marker, state_dir, 1024)) == STOP_RECORD, 'STOP_RECORD_INVALID')
        deadline = time.monotonic() + 10
        while True:
            try:
                with state_lock(state_dir, 'controller.lock'):
                    if state_dir == ROOT / 'runs/public-hermes':
                        from evaluate_skill_semantics import STATE, interrupt
                        interrupt()
                        # A crashed controller's pending receipt still requires recovery,
                        # even if its inspected worker was killed or is already absent.
                        require(not os.path.lexists(STATE / 'pending.json'), 'SEMANTIC_RECOVERY_REQUIRED')
                    require(not os.path.lexists(pending), 'ISOLATION_PENDING')
                    return 'INTAKE_STOPPED'
            except EvaluationError as error:
                if str(error) != 'CONCURRENT_RUN':
                    raise
            require(time.monotonic() < deadline, 'STOP_UNCONFIRMED')
            interrupt_worker(state_dir, pending)
            time.sleep(0.1)


def run(packet, read_mock, state_dir, clock=time.monotonic, *, isolated=False, stall=False):
    require(len(canonical(packet)) <= MAX_PACKET_BYTES, 'PACKET_SIZE')
    refs = packet_refs(packet)

    def build_result(receipt, data):
        return {
            'schema_version': 1, **receipt, 'classification': 'PUBLIC',
            'target_skill': SKILL, 'baseline_sha': packet['baseline_sha'],
            **response_result(load_json(data), refs),
        }

    return execute_trial(packet, read_mock, state_dir, build_result, clock,
                         isolated=isolated, stall=stall)


def execute_trial(packet, read_mock, state_dir, build_result, clock=time.monotonic,
                  *, isolated=False, stall=False, one_per_snapshot=False, cloud=False):
    require(not cloud or (isolated and not stall), 'CLOUD_MODE')
    require(hex_id(packet.get('event_id'), 64), 'EVENT_ID')
    prepare_state(state_dir)
    marker = state_dir / 'intake-stop.json'
    reject_stopped(marker)
    with state_lock(state_dir, 'controller.lock'):
        reject_stopped(marker)
        pending = state_dir / 'isolation-pending.json'
        require(not os.path.lexists(pending), 'ISOLATION_PENDING')
        event_dir = state_dir / packet['event_id']
        require(not os.path.lexists(event_dir), 'EVENT_ALREADY_CLAIMED')
        if one_per_snapshot:
            snapshot = packet['snapshot_hash']
            require(hex_id(snapshot, 64), 'SNAPSHOT_HASH')
            try:
                (state_dir / ('snapshot-' + snapshot)).mkdir(mode=0o700)
            except FileExistsError:
                raise EvaluationError('SNAPSHOT_ALREADY_CLAIMED') from None
            syncdir(state_dir)
        try:
            event_dir.mkdir(mode=0o700)
        except FileExistsError:
            raise EvaluationError('EVENT_ALREADY_CLAIMED') from None
        syncdir(state_dir)
        receipt = {'event_id': packet['event_id'], 'packet_hash': digest(canonical(packet))}
        save(event_dir / 'started.json', {**receipt, 'status': 'STARTED',
                                         ('model_attempt_budget' if cloud else 'mock_attempts'): 1})
        deadline = clock() + (ISOLATED_DEADLINE_SECONDS if isolated else DEADLINE_SECONDS)
        try:
            data = read_mock()
            reject_stopped(marker)
            require(clock() < deadline, 'TIMEOUT')
            require(len(data) <= MAX_RESPONSE_BYTES, 'RESPONSE_SIZE')
            if isolated:
                name = 'hermes-eval-' + uuid.uuid4().hex
                save(pending, {**receipt, 'container': name,
                               **({'worker_kind': 'hermes-cloud-v1'} if cloud else {})})
                try:
                    if cloud:
                        from delegation.hermes_cloud import response
                        data = response(ROOT, data, event_dir, deadline, name)
                    else:
                        data = isolated_response(data, event_dir, deadline, name, stall=stall)
                except EvaluationError as error:
                    if getattr(error, 'pending_container', None) is None:
                        pending.unlink()
                        syncdir(state_dir)
                    raise
                pending.unlink()
                syncdir(state_dir)
                require(len(data) <= MAX_RESPONSE_BYTES, 'RESPONSE_SIZE')
            result = build_result(receipt, data)
            reject_stopped(marker)
            encoded = canonical(result)
            require(clock() < deadline, 'TIMEOUT')
        except (EvaluationError, OSError) as error:
            reason = str(error) if isinstance(error, EvaluationError) else 'MOCK_READ_FAILED'
            save(event_dir / 'finished.json', {**receipt, 'status': 'STOPPED', 'reason': reason})
            raise EvaluationError(reason) from None
        save(event_dir / 'finished.json', {**receipt, 'status': 'COMPLETED',
                                          'decision': result['decision'], 'result_hash': digest(encoded)})
        return encoded


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--stop', action='store_const', dest='control', const='stop')
    operation.add_argument('--resume', action='store_const', dest='control', const='resume')
    parser.add_argument('--packet', type=Path)
    parser.add_argument('--response', type=Path)
    parser.add_argument('--isolated', action='store_true', help='run a fixed offline worker in Docker')
    parser.add_argument('--simulate-stall', action='store_true', help='emit partial output then stall')
    args = parser.parse_args()
    if args.control and (args.packet or args.response or args.isolated or args.simulate_stall):
        parser.error('--stop and --resume cannot be combined with worker arguments')
    if not args.control and not (args.packet and args.response):
        parser.error('--packet and --response are required for a worker')
    if args.simulate_stall and not args.isolated:
        parser.error('--simulate-stall requires --isolated')
    state_dir = ROOT / 'runs' / 'mock-improvement'
    try:
        if args.control:
            print(canonical({'status': control_intake(state_dir, args.control)}).decode())
            return 0
        packet = load_json(regular(args.packet, args.packet.absolute().parent, MAX_PACKET_BYTES))
        encoded = run(packet, lambda: regular(args.response, args.response.absolute().parent,
                                              MAX_RESPONSE_BYTES), state_dir,
                      isolated=args.isolated, stall=args.simulate_stall)
    except (EvaluationError, OSError, RecursionError) as error:
        reason = str(error) if isinstance(error, EvaluationError) else 'INPUT_OR_STATE_ERROR'
        print(canonical({'status': 'STOPPED', 'reason': reason}).decode(), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(encoded + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
