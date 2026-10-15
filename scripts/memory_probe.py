#!/usr/bin/env python3
"""Fetch pinned PUBLIC source separately, then run the offline storage probe.

Usage: python3 -I -B scripts/memory_probe.py fetch|run|verify-events RUN_ID
No Hermes CLI, model API, host HOME or credentials are used by the worker.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
PIN = 'f97608f178d1ffeca59860195ab7da295f7c8e5f'
RUNS = ROOT / 'runs'
SOURCE = RUNS / ('memory-source-' + PIN)
LOCK = ROOT / 'fixtures/memory/upstream-lock.json'
WORKER = ROOT / 'tests/memory_probe_worker.py'
ZERO = '0' * 64


class ProbeError(Exception):
    def __init__(self, reason, cases=None):
        super().__init__(reason)
        self.cases = cases or []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def safe_path(path):
    """Reject symlinks before reading/writing; all generated paths stay in runs."""
    if '..' in path.parts or not path.is_relative_to(RUNS):
        raise ProbeError('path_outside_runs')
    for ancestor in [path, *path.parents]:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ProbeError('symlink_rejected')
    return path


def load_lock():
    lock = json.loads(LOCK.read_bytes())
    if (lock['schema_version'] != 1 or lock['repository'] != 'NousResearch/hermes-agent'
            or lock['commit'] != PIN or not 1 <= len(lock['files']) <= 100):
        raise ProbeError('invalid_source_lock')
    total = 0
    for name, info in lock['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or not re.fullmatch(r'[A-Za-z0-9_/]+\.py', name):
            raise ProbeError('invalid_source_path')
        if not re.fullmatch('[0-9a-f]{64}', info['sha256']) or not re.fullmatch('[0-9a-f]{40}', info['git_blob']):
            raise ProbeError('invalid_source_hash')
        if type(info['bytes']) is not int or not 0 < info['bytes'] <= 2_000_000:
            raise ProbeError('invalid_source_size')
        total += info['bytes']
    if total > 8_000_000:
        raise ProbeError('source_budget_exceeded')
    return lock


def check_bytes(data, info):
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if len(data) != info['bytes'] or digest(data) != info['sha256'] or blob != info['git_blob']:
        raise ProbeError('source_hash_mismatch')


def verify_source(lock):
    safe_path(SOURCE)
    if not SOURCE.is_dir():
        raise ProbeError('source_missing_run_fetch_first')
    for path in SOURCE.rglob('*'):
        safe_path(path)
        if not path.is_dir() and (not path.is_file() or path.relative_to(SOURCE).as_posix() not in lock['files']):
            raise ProbeError('unexpected_source_file')
    for name, info in lock['files'].items():
        path = safe_path(SOURCE / name)
        if not path.is_file():
            raise ProbeError('source_file_missing')
        check_bytes(path.read_bytes(), info)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError('source_redirect_rejected')


def fetch(lock):
    safe_path(SOURCE).mkdir(parents=True, exist_ok=True)
    # Public source request has no inherited proxies, auth headers or credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for name, info in lock['files'].items():
        path = safe_path(SOURCE / name)
        if path.exists():
            check_bytes(path.read_bytes(), info)
            continue
        url = 'https://raw.githubusercontent.com/NousResearch/hermes-agent/' + PIN + '/' + name
        with opener.open(url, timeout=30) as response:
            data = response.read(info['bytes'] + 1)
        check_bytes(data, info)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    verify_source(lock)
    print(json.dumps({'status': 'VERIFIED', 'source_files': len(lock['files']), 'commit': PIN}))


def expected_cases():
    tree = ast.parse(WORKER.read_bytes())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'StorageTests')
    cases = sorted(n.name for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
    if not cases:
        raise ProbeError('no_test_cases')
    return cases


def worker(work, mode):
    env = {'HOME': str(work / 'home'), 'HERMES_HOME': str(work / 'home/hermes'),
           'PATH': '/usr/bin:/bin', 'HERMES_TIMEZONE': 'UTC', 'TMPDIR': str(work / 'tmp'),
           'LANG': 'C.UTF-8'}
    try:
        result = subprocess.run([sys.executable, '-I', '-B', str(WORKER), str(SOURCE), str(work), mode],
                                env=env, cwd=work, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise ProbeError('worker_timeout') from None
    # Do not persist or echo worker streams. Reconstruct allowlisted evidence only.
    if result.stderr:
        raise ProbeError('worker_unexpected_stderr')
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        if result.returncode:
            raise ProbeError('worker_' + mode + '_failed') from None
        raise ProbeError('worker_invalid_output') from None
    if result.returncode:
        names = expected_cases()
        failed = sorted({name for key in ('errors', 'failures') for name in payload.get(key, []) if name in names})
        raise ProbeError('worker_' + mode + '_failed', failed)
    if payload.get('status') != 'VERIFIED':
        raise ProbeError('worker_result_not_verified')
    if mode == 'check':
        if (payload.get('tests_run') != len(expected_cases()) or payload.get('failures') != []
                or payload.get('errors') != [] or payload.get('passed_cases') != expected_cases()):
            raise ProbeError('worker_incomplete_tests')
        return {'status': 'VERIFIED', 'phase': mode, 'tests_run': payload['tests_run'],
                'passed_cases': expected_cases()}
    if payload.get('phase') != mode:
        raise ProbeError('worker_phase_mismatch')
    return {'status': 'VERIFIED', 'phase': mode}


def read_manifest_hash(work):
    try:
        manifest = json.loads(safe_path(work / 'manifest.json').read_bytes())
        if not isinstance(manifest, dict) or manifest.get('run_id') != work.name:
            raise ProbeError('audit_manifest_invalid')
        return digest(canonical(manifest))
    except (OSError, ValueError, UnicodeError):
        raise ProbeError('audit_manifest_missing_or_invalid') from None


def append_event(work, run_id, state, previous, output_hash=ZERO, reason=None, manifest_sha256=None):
    event = {'run_id': run_id, 'utc': utc(), 'actor': 'storage-probe', 'state': state,
             'input_hash': digest(LOCK.read_bytes()), 'output_hash': output_hash,
             'api_cost_usd': 0, 'approval_ref': 'human-chat-2026-10-15-storage-retention',
             'previous_hash': previous, 'reason': reason,
             'manifest_sha256': manifest_sha256 or read_manifest_hash(work)}
    event['hash'] = digest(canonical(event))
    with (work / 'events.jsonl').open('ab') as stream:
        stream.write(canonical(event) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    return event['hash']


def verify_events(work):
    safe_path(work)
    manifest_sha256 = read_manifest_hash(work)
    previous = ZERO
    count = 0
    states = []
    for line in (safe_path(work / 'events.jsonl')).read_bytes().splitlines():
        event = json.loads(line)
        claimed = event.pop('hash')
        if (event['previous_hash'] != previous or digest(canonical(event)) != claimed
                or event['run_id'] != work.name or event.get('manifest_sha256') != manifest_sha256):
            raise ProbeError('audit_chain_mismatch')
        previous, count = claimed, count + 1
        states.append(event['state'])
    if not count:
        raise ProbeError('audit_chain_empty')
    report_bytes = safe_path(work / 'report.json').read_bytes()
    report = json.loads(report_bytes)
    if (states[0] != 'STARTED' or states[-1] not in ('VERIFIED', 'FAILED', 'BLOCKED')
            or report['run_id'] != work.name or report['status'] != states[-1]
            or event['output_hash'] != digest(report_bytes)):
        raise ProbeError('audit_incomplete_or_report_mismatch')
    if states[-1] == 'VERIFIED' and states != ['STARTED', 'SOURCE_VERIFIED', 'VERIFIED']:
        raise ProbeError('audit_invalid_transition')
    return {'status': 'VERIFIED', 'events': count, 'final_hash': previous}


def run(lock):
    run_id = 'memory-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    work = safe_path(RUNS / run_id)
    work.mkdir(parents=True, mode=0o700)
    for name in ['home/hermes', 'tmp']:
        (work / name).mkdir(parents=True, mode=0o700)
    manifest = {'schema_version': 1, 'run_id': run_id, 'started_at': utc(), 'source_sha': PIN,
                'source_lock_sha256': digest(LOCK.read_bytes()), 'worker_sha256': digest(WORKER.read_bytes()),
                'runner_sha256': digest(Path(__file__).read_bytes()),
                'python_version': sys.version.split()[0], 'sqlite_version': __import__('sqlite3').sqlite_version,
                'classification': 'PUBLIC_SYNTHETIC_ONLY', 'risk_tier': 'HIGH',
                'retention': {'raw_minimum_days': 30, 'audit_minimum_days': 90,
                              'automatic_deletion': False, 'deletion_requires_human_approval': True},
                'scope': 'offline_storage_modules_with_explicit_AST_helper_slices',
                'not_verified': ['full_agent_integration', 'model_API', 'production_root_cause',
                                 'OS_restart', 'automatic_prune_scheduling', 'adversarial_OS_sandbox']}
    (work / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
    manifest_sha256 = digest(canonical(manifest))
    previous = append_event(work, run_id, 'STARTED', ZERO, manifest_sha256=manifest_sha256)
    phases, reason, status, failed_cases = [], None, 'BLOCKED', []
    try:
        verify_source(lock)
        previous = append_event(work, run_id, 'SOURCE_VERIFIED', previous, manifest_sha256=manifest_sha256)
        phases.append(worker(work, 'seed'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            phases.extend(pool.map(lambda mode: worker(work, mode), ['one', 'two']))
        phases.append(worker(work, 'check'))
        verify_source(lock)
        if read_manifest_hash(work) != manifest_sha256:
            raise ProbeError('audit_manifest_mismatch')
        status = 'VERIFIED'
    except ProbeError as error:
        reason = str(error)
        failed_cases = error.cases
        status = 'FAILED' if reason.startswith('worker_') else 'BLOCKED'
    except Exception:
        reason = 'probe_unexpected_failure'
    report = {'schema_version': 1, 'run_id': run_id, 'status': status, 'reason': reason,
              'failed_cases': failed_cases,
              'scope': manifest['scope'], 'phases': phases, 'not_verified': manifest['not_verified'],
              'secret_masking': 'NOT_GUARANTEED_BY_UPSTREAM_STORAGE', 'api_cost_usd': 0}
    raw = canonical(report) + b'\n'
    (work / 'report.json').write_bytes(raw)
    append_event(work, run_id, status, previous, digest(raw), reason, manifest_sha256)
    audit_result = verify_events(work)
    print(json.dumps({'status': status, 'reason': reason, 'run_id': run_id,
                      'tests': len(expected_cases()) if status == 'VERIFIED' else None,
                      'report_sha256': digest(raw), 'final_event_hash': audit_result['final_hash']}))
    return 0 if status == 'VERIFIED' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch', 'run', 'verify-events'])
    parser.add_argument('run_id', nargs='?')
    args = parser.parse_args()
    os.umask(0o077)
    safe_path(RUNS)
    lock = load_lock()
    if args.action == 'fetch':
        fetch(lock)
    elif args.action == 'run':
        return run(lock)
    else:
        if not args.run_id or not re.fullmatch(r'memory-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', args.run_id):
            raise ProbeError('invalid_run_id')
        print(json.dumps(verify_events(RUNS / args.run_id)))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        # No source content, exception text, credentials or request headers in logs.
        print(json.dumps({'status': 'BLOCKED', 'reason': 'probe_setup_or_source_validation_failed'}))
        sys.exit(2)
