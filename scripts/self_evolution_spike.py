#!/usr/bin/env python3
"""Issue #6 approved offline spike. No provider access, push, or production discovery."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from self_evolution.sandbox import SpikeSandbox, stored_bytes

UPSTREAM = '0a929e3aa20e15cf04dc7c28492a7d41a5139125'
IMAGE = 'python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'
WORKER = ROOT / 'fixtures/self-evolution/worker.py'
PROBE = ROOT / 'fixtures/self-evolution/isolation_probe.py'
SOURCES = ['scripts/self_evolution_spike.py', 'src/self_evolution/__init__.py',
           'src/self_evolution/sandbox.py', 'src/evaluation/sandbox.py', 'src/evaluation/core.py',
           'fixtures/self-evolution/worker.py', 'fixtures/self-evolution/isolation_probe.py',
           'fixtures/self-evolution/hermes-agent/skills/github-code-review/SKILL.md',
           'fixtures/self-evolution/requirements.lock']
BOUNDARIES = {'non_root', 'capabilities', 'no_new_privileges', 'seccomp', 'env', 'root_readonly',
              'fixture_readonly', 'source_readonly', 'deps_readonly', 'skill_readonly', 'lock_readonly',
              'canary_unmounted', 'hidden_unmounted', 'socket_unmounted', 'no_shared_memory',
              'cpu_quota', 'memory_limit', 'swap_limit', 'pids_limit', 'tmpfs_size',
              'network_denied', 'work_writable'}


def save(work, name, value):
    write_new(work / name, canonical(value) + b'\n')


def tree_hashes(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'SNAPSHOT_SYMLINK')
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def git(source, *args):
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(source), *args],
                            env=env, capture_output=True, timeout=10)
    require(result.returncode == 0 and len(result.stdout) <= 1048576, 'SOURCE_UNAVAILABLE')
    return result.stdout


def snapshot(source, destination):
    require(git(source, 'rev-parse', 'HEAD').decode().strip() == UPSTREAM, 'UPSTREAM_MISMATCH')
    names = git(source, 'ls-tree', '-r', '--name-only', UPSTREAM).decode().splitlines()
    selected = [n for n in names if n.startswith('evolution/') and n.endswith('.py')]
    require(bool(selected) and len(selected) < 100, 'SOURCE_SCOPE')
    for name in selected:
        require('..' not in Path(name).parts and not Path(name).is_absolute(), 'SOURCE_PATH')
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(source, 'cat-file', 'blob', UPSTREAM + ':' + name))
    return tree_hashes(destination)


def validate_gate(mode, result):
    if mode in ('timeout', 'output'):
        require(result['error'] == ('TIMEOUT' if mode == 'timeout' else 'OUTPUT_LIMIT'), 'DENIAL_FAILED')
        require(not result['stderr'], 'PROBE_START_UNVERIFIED')
        if mode == 'timeout':
            started = load_json(result['stdout'])
            require(type(started) is dict and set(started) == {'probe', 'pid', 'parent_pid'} and
                    started['probe'] == 'timeout-child-started' and type(started['pid']) is int and
                    started['pid'] > 1 and type(started['parent_pid']) is int and
                    started['parent_pid'] == 1, 'PROBE_START_UNVERIFIED')
        else:
            require(len(result['stdout']) >= 1024 and set(result['stdout']) == {ord('x')},
                    'PROBE_START_UNVERIFIED')
        return {'status': 'VERIFIED', 'reason': result['error'], 'probe_started': True}
    require(result['exit'] == 0 and not result['error'] and not result['stderr'], 'PROBE_FAILED')
    value = load_json(result['stdout'])
    expected = BOUNDARIES if mode == 'boundaries' else {
        'disk': {'disk_denied'}, 'memory': {'memory_denied'},
        'pids': {'pids_denied'}, 'cpu': {'cpu_throttled'}}[mode]
    revision = value.pop('python', None) if mode == 'boundaries' else None
    require(set(value) == expected and all(v is True for v in value.values()), 'DENIAL_FAILED')
    require(mode != 'boundaries' or isinstance(revision, str) and revision.startswith('3.12.'), 'PYTHON_REVISION')
    return {'status': 'VERIFIED', 'checks': sorted(value), 'python': revision}


def execute(box, phase, mode):
    box.phase = phase
    program = PROBE if phase == 'gate' else WORKER
    result = box.run(program, canonical({'mode': mode}), timeout=3 if mode == 'timeout' else 60)
    prefix = phase + '-' + mode
    write_new(box.work / (prefix + '.stdout.txt'), result.pop('stdout'))
    write_new(box.work / (prefix + '.stderr.txt'), result.pop('stderr'))
    save(box.work, prefix + '.json', result)
    print(json.dumps({'phase': phase, 'mode': mode, 'exit': result['exit'], 'error': result['error']}), flush=True)
    result['stdout'] = (box.work / (prefix + '.stdout.txt')).read_bytes()
    result['stderr'] = (box.work / (prefix + '.stderr.txt')).read_bytes()
    return result


def run(source):
    # The global budget starts before snapshot, image checks, and dependency setup.
    started = time.monotonic()
    deadline = started + 1200
    runs = ROOT / 'runs'
    require(not runs.is_symlink(), 'RUN_SYMLINK')
    runs.mkdir(exist_ok=True)
    tag = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(6)
    work = runs / ('self-evolution-' + tag)
    work.mkdir(mode=0o700)
    report = {'run_id': work.name, 'classification': 'PUBLIC', 'upstream': UPSTREAM,
              'approval': 'human chat approval 2026-10-16; docs/self-evolution-spike.md stage 1',
              'model_api_calls': 0, 'cost_usd': 0, 'status': 'RUNNING', 'gate': {}, 'probes': {}}
    print(json.dumps({'run_id': work.name}), flush=True)
    try:
        for name in ('source', 'prepare', 'prepare/site'):
            (work / name).mkdir(exist_ok=True)
        # Only this new preparation directory is writable by the preparation worker.
        (work / 'prepare').chmod(0o777)
        (work / 'prepare/site').chmod(0o777)
        report['sources'] = {n: digest(regular(ROOT / n, ROOT)) for n in SOURCES}
        box = SpikeSandbox(ROOT, work, deadline=deadline)
        report['source_files'] = snapshot(source, work / 'source')
        report['environment'] = box.environment()
        # Exact official registry digest, no mutable tag resolution or model endpoint.
        box.checked('pull', '--platform=linux/arm64', IMAGE, timeout=min(60, deadline - time.monotonic()))
        report['image'] = box.image_info(IMAGE)
        box.image = report['image']['id']
        save(work, 'environment.json', report)
        for phase in ('download', 'install'):
            result = execute(box, phase, phase)
            require(result['exit'] == 0 and not result['error'], 'DEPENDENCIES_' + phase.upper())
        report['dependencies'] = tree_hashes(work / 'prepare')
        for mode in ('boundaries', 'disk', 'memory', 'pids', 'cpu', 'timeout', 'output'):
            report['gate'][mode] = validate_gate(mode, execute(box, 'gate', mode))
        save(work, 'gate.json', {'status': 'VERIFIED', 'results': report['gate'],
                                'sources': report['sources'], 'image': report['image']})
        before = tree_hashes(ROOT / 'fixtures/self-evolution/hermes-agent')
        for mode in ('help', 'dry-run', 'contracts', 'failure-path'):
            require(report['sources'] == {n: digest(regular(ROOT / n, ROOT)) for n in SOURCES},
                    'CONTROLLER_CHANGED')
            require(report['source_files'] == tree_hashes(work / 'source') and
                    report['dependencies'] == tree_hashes(work / 'prepare'), 'INPUT_CHANGED')
            result = execute(box, 'probe', mode)
            require(result['exit'] == 0 and not result['error'], 'CLI_API_' + mode.upper())
            if mode in ('contracts', 'failure-path'):
                report['probes'][mode] = load_json(result['stdout'])
            else:
                text = result['stdout'].decode()
                require(('--hermes-repo' in text) if mode == 'help' else ('DRY RUN' in text), 'CLI_OUTPUT')
                report['probes'][mode] = {'status': 'VERIFIED'}
        report['fixture_unchanged'] = before == tree_hashes(ROOT / 'fixtures/self-evolution/hermes-agent')
        require(report['fixture_unchanged'] and report['source_files'] == tree_hashes(work / 'source') and
                report['dependencies'] == tree_hashes(work / 'prepare'), 'INPUT_CHANGED')
        report['status'] = 'OBSERVATIONS_RECORDED'
        report['acceptance'] = 'NOT_VERIFIED: no real model optimization or production compatibility test'
    except Exception as error:
        report['status'] = 'BLOCKED'
        report['reason'] = str(error) if isinstance(error, EvaluationError) else type(error).__name__
        report['pending_container'] = getattr(error, 'pending_container', None)
        raise
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        try:
            report['stored_bytes'] = stored_bytes(work)
        except (OSError, EvaluationError):
            report['stored_bytes'] = None
            report['storage_status'] = 'UNCERTAIN'
            report['status'] = 'BLOCKED'
        save(work, 'report.json', report)
        print(json.dumps({'run_id': work.name, 'status': report['status'],
                          'seconds': report['elapsed_seconds'], 'stored_bytes': report['stored_bytes']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Public upstream checkout at the fixed SHA')
    arguments = parser.parse_args()
    try:
        run(arguments.source)
    except (EvaluationError, OSError, subprocess.SubprocessError):
        print('Spike stopped; see the new run report and bounded logs.', file=sys.stderr)
        raise SystemExit(1)
