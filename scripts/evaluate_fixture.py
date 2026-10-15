#!/usr/bin/env python3
"""Issue #5: offline, separately gated fixture evaluation. See docs/independent-evaluation.md."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import (EvaluationError, canonical, digest, findings, judge, load_json,
                             policy, regular, require, write_new)
from evaluation.sandbox import Sandbox

RUNS = ROOT / 'runs'
ARTIFACT = 'fixtures/skills/github-code-review/review.py'
ZERO = '0' * 64
SOURCES = ['scripts/evaluate_fixture.py', 'src/evaluation/__init__.py',
           'src/evaluation/core.py', 'src/evaluation/sandbox.py',
           'fixtures/evaluation/isolation_probe.py', 'fixtures/evaluation/policy.json',
           'schemas/evaluation-report.schema.json']
PROBE_FIELDS = {
    'boundaries': {'non_root', 'capabilities', 'no_new_privileges', 'seccomp', 'env',
                   'root_readonly', 'fixture_readonly', 'canary_unmounted', 'hidden_unmounted',
                   'socket_unmounted', 'no_shared_memory', 'cpu_quota', 'memory_limit',
                   'swap_limit', 'pids_limit', 'tmpfs_size', 'network_denied', 'work_writable'},
    'disk': {'disk_denied'}, 'memory': {'memory_denied'}, 'pids': {'pids_denied'},
    'cpu': {'cpu_throttled'},
}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_path(run_id):
    require(re.fullmatch(r'evaluation-\d{8}T\d{6}Z-[a-f0-9]{12}', run_id), 'RUN_ID')
    require(not RUNS.is_symlink() and not (RUNS / run_id).is_symlink(), 'RUN_SYMLINK')
    work = RUNS / run_id
    require(work.is_dir(), 'RUN_MISSING')
    return work


def read(work, name):
    return load_json(regular(work / name, RUNS, 2097152))


def save(work, name, value):
    write_new(work / name, canonical(value) + b'\n')


def source_hashes():
    return {name: digest(regular(ROOT / name, ROOT)) for name in SOURCES}


def git_command(*args):
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1'}
    result = subprocess.run(['git', '-C', str(ROOT), *args], env=env, capture_output=True, timeout=10)
    require(result.returncode == 0, 'COMMIT_UNAVAILABLE')
    return result.stdout


def event(work, state, payload_hash):
    path = work / 'events.jsonl'
    previous = ZERO
    index = 0
    if path.exists():
        lines = regular(path, RUNS, 2097152).splitlines()
        previous = load_json(lines[-1])['hash']
        index = len(lines)
    row = {'index': index, 'run_id': work.name, 'utc': stamp(), 'actor': 'fixture-controller',
           'state': state, 'payload_hash': payload_hash, 'previous_hash': previous}
    row['hash'] = digest(canonical(row))
    fd = os.open(path, os.O_APPEND | os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'ab') as stream:
        stream.write(canonical(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def bootstrap():
    require(not RUNS.is_symlink(), 'RUN_SYMLINK')
    RUNS.mkdir(exist_ok=True)
    run_id = 'evaluation-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(6)
    work = RUNS / run_id
    work.mkdir(mode=0o700)
    box = Sandbox(ROOT, work)
    environment = box.environment()
    # Explicit bootstrap-only network operation; never performed by evaluate/run.
    box.checked('pull', '--platform=linux/arm64', 'docker.io/library/python:3.12-slim-bookworm', timeout=180)
    image = box.image_info('docker.io/library/python:3.12-slim-bookworm')
    save(work, 'environment.json', {'run_id': run_id, 'environment': environment, 'image': image,
                                 'approval': 'human chat approval 2026-10-15; Issue #5 proposal',
                                 'classification': 'PUBLIC', 'utc': stamp()})
    event(work, 'ENVIRONMENT_PINNED', digest(regular(work / 'environment.json', RUNS)))
    print(json.dumps({'run_id': run_id, 'image': image, 'environment': environment}))


def sandbox(work):
    env = read(work, 'environment.json')
    box = Sandbox(ROOT, work, env['image']['id'])
    require(box.image_info(box.image) == env['image'], 'IMAGE_CHANGED')
    require(box.environment() == env['environment'], 'ENVIRONMENT_CHANGED')
    return box


def probe_result(mode, data):
    payload = load_json(data)
    require(type(payload) is dict, 'PROBE_SCHEMA')
    revision = None
    if mode == 'boundaries':
        revision = payload.pop('python', None)
        require(type(revision) is str and re.fullmatch(r'3\.12\.\d+', revision), 'PYTHON_REVISION')
    require(set(payload) == PROBE_FIELDS[mode], 'PROBE_FIELDS')
    for key in sorted(PROBE_FIELDS[mode]):
        require(payload[key] is True, 'DENIAL_' + key.upper())
    return revision


def gate(work):
    require(not (work / 'gate.json').exists(), 'GATE_ALREADY_RUN')
    box = sandbox(work)
    results = {}
    python_revision = None
    try:
        for mode in ('boundaries', 'disk', 'memory', 'pids', 'cpu', 'timeout', 'output'):
            outcome = box.run(ROOT / 'fixtures/evaluation/isolation_probe.py', canonical({'mode': mode}),
                              timeout=1 if mode == 'timeout' else 30)
            if mode in ('timeout', 'output'):
                require(outcome['error'] == ('TIMEOUT' if mode == 'timeout' else 'OUTPUT_LIMIT'),
                        'DENIAL_PROBE_FAILED')
            else:
                require(outcome['exit'] == 0 and not outcome['stderr'] and not outcome['error'],
                        'DENIAL_PROBE_FAILED')
                revision = probe_result(mode, outcome['stdout'])
                if revision:
                    python_revision = revision
            results[mode] = 'VERIFIED'
        result = {'status': 'VERIFIED', 'probes': results, 'python_revision': python_revision,
                  'environment_hash': digest(regular(work / 'environment.json', RUNS)),
                  'sources': source_hashes(), 'utc': stamp()}
        save(work, 'gate.json', result)
        event(work, 'ISOLATION_VERIFIED', digest(regular(work / 'gate.json', RUNS)))
        print(json.dumps({'run_id': work.name, 'gate': 'VERIFIED', 'probes': len(results)}))
    except Exception as error:
        code = str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR'
        save(work, 'gate.json', {'status': 'FAILED', 'probes': results, 'failed_mode': mode,
                                'reason': code, 'utc': stamp()})
        event(work, 'ISOLATION_FAILED', digest(regular(work / 'gate.json', RUNS)))
        raise


def cases(hidden):
    """Fixed categories, unknown individual paths/lines/values; never print hidden bytes."""
    rows = []
    for index, kind in enumerate(['eval'] * 3 + ['shell'] * 3 + ['safe'] * 4):
        tag = secrets.token_hex(8) if hidden else f'{index:016x}'
        path = 'case_' + tag + '.py'
        line = secrets.randbelow(60) + 2 if hidden else index + 2
        expression = {'eval': 'value = eval(user_input)',
                      'shell': 'value = subprocess.run(user_input, shell=True)',
                      'safe': 'value = user_input.strip()'}[kind]
        patch = f'--- a/{path}\n+++ b/{path}\n@@ -1,0 +{line},1 @@\n+{expression}\n'
        expected = [] if kind == 'safe' else [[path, line, 'dynamic-eval' if kind == 'eval' else 'shell-execution']]
        rows.append({'input': {'path': path, 'patch': patch}, 'expected': expected})
    return rows


def verify_gate(work):
    value = read(work, 'gate.json')
    require(value.get('status') == 'VERIFIED' and value.get('sources') == source_hashes() and
            value.get('environment_hash') == digest(regular(work / 'environment.json', RUNS)), 'GATE_STALE')
    require(value.get('probes') == {name: 'VERIFIED' for name in (*PROBE_FIELDS, 'timeout', 'output')},
            'GATE_PROBES_MISSING')
    return value


def freeze(work):
    verify_gate(work)
    require(not (work / 'manifest.json').exists(), 'ALREADY_FROZEN')
    require(load_json(regular(ROOT / 'fixtures/evaluation/policy.json', ROOT)) == policy(), 'POLICY_MISMATCH')
    baseline_sha = git_command('rev-parse', 'HEAD').decode().strip()
    baseline_data = git_bytes(baseline_sha)
    require(regular(ROOT / ARTIFACT, ROOT) == baseline_data, 'BASELINE_DIRTY')
    for name, expected in source_hashes().items():
        stored = git_command('show', baseline_sha + ':' + name)
        require(digest(stored) == expected, 'EVALUATOR_NOT_COMMITTED')
    save(work, 'public.json', cases(False))
    save(work, 'hidden.json', cases(True))
    manifest = {'schema_version': 1, 'run_id': work.name, 'utc': stamp(), 'policy': policy(),
                'baseline_sha': baseline_sha, 'baseline_artifact_hash': digest(baseline_data),
                'sources': source_hashes(), 'seed_id': secrets.token_hex(16),
                'dataset_hashes': {name: digest(regular(work / (name + '.json'), RUNS))
                                   for name in ('public', 'hidden')},
                'environment_hash': digest(regular(work / 'environment.json', RUNS)),
                'gate_hash': digest(regular(work / 'gate.json', RUNS)),
                'classification': {'public': 'PUBLIC', 'hidden': 'INTERNAL'},
                'retention_days': {'synthetic': 30, 'audit': 90}, 'automatic_deletion': False}
    save(work, 'manifest.json', manifest)
    event(work, 'EVALUATION_FROZEN', digest(regular(work / 'manifest.json', RUNS)))
    print(json.dumps({'run_id': work.name, 'manifest_hash': digest(regular(work / 'manifest.json', RUNS)),
                      'public_dataset_hash': manifest['dataset_hashes']['public'],
                      'hidden_commitment': manifest['dataset_hashes']['hidden']}))


def verify_manifest(work):
    verify_gate(work)
    manifest = read(work, 'manifest.json')
    require(manifest['run_id'] == work.name and manifest['sources'] == source_hashes() and
            manifest['policy'] == policy(), 'MANIFEST_CHANGED')
    for name in ('public', 'hidden'):
        require(digest(regular(work / (name + '.json'), RUNS)) == manifest['dataset_hashes'][name],
                'DATASET_CHANGED')
    for name in ('environment', 'gate'):
        require(digest(regular(work / (name + '.json'), RUNS)) == manifest[name + '_hash'], 'MANIFEST_CHANGED')
    # Anchor the immutable manifest to the earlier event, not merely to itself.
    events = verify_events(work)
    frozen = [e for e in events if e['state'] == 'EVALUATION_FROZEN']
    require(len(frozen) == 1 and frozen[0]['payload_hash'] == digest(regular(work / 'manifest.json', RUNS)),
            'MANIFEST_ANCHOR')
    return manifest


def git_bytes(sha):
    require(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'COMMIT_SHA')
    require(git_command('cat-file', '-t', sha).strip() == b'commit', 'COMMIT_TYPE')
    tree = git_command('ls-tree', sha, '--', ARTIFACT).split()
    require(len(tree) == 4 and tree[0] in (b'100644', b'100755') and tree[1] == b'blob', 'ARTIFACT_TYPE')
    data = git_command('show', sha + ':' + ARTIFACT)
    require(0 < len(data) <= 65536, 'ARTIFACT_SIZE')
    return data


def compare_records(records):
    result = {}
    unstable = False
    for label, rows in records.items():
        correct = []
        for item in rows:
            unstable |= len(set(sample['answer_hash'] for sample in item)) != 1
            correct.append(all(sample['correct'] for sample in item))
        result[label] = {'correct': correct,
                         'failures': sum(sample['failed'] for item in rows for sample in item),
                         'latency': statistics.median(statistics.median(s['wall_seconds'] for s in item) for item in rows),
                         'cost_usd': 0}
    return result, unstable


def evaluate(work, baseline_sha, candidate_sha):
    require(not (work / 'evaluation-lock.json').exists(), 'RUN_ALREADY_USED')
    manifest = verify_manifest(work)
    box = sandbox(work)
    baseline, candidate = git_bytes(baseline_sha), git_bytes(candidate_sha)
    require(baseline_sha == manifest['baseline_sha'] and digest(baseline) == manifest['baseline_artifact_hash'],
            'BASELINE_CHANGED')
    require(baseline_sha != candidate_sha and baseline != candidate, 'CANDIDATE_NOT_DISTINCT')
    # Ancestry ensures the baseline predates the candidate; timestamps alone cannot prove ordering.
    git_command('merge-base', '--is-ancestor', baseline_sha, candidate_sha)
    save(work, 'evaluation-lock.json', {'baseline_sha': baseline_sha, 'candidate_sha': candidate_sha,
                                      'manifest_hash': digest(regular(work / 'manifest.json', RUNS)),
                                      'utc': stamp(), 'state': 'EVALUATING'})
    event(work, 'EVALUATING', digest(regular(work / 'evaluation-lock.json', RUNS)))
    programs = {'baseline': baseline, 'candidate': candidate,
                'degraded': b'import json\nprint(json.dumps({"findings":[],"cpu_seconds":0}))\n'}
    for label, data in programs.items():
        write_new(work / (label + '.py'), data)
        os.chmod(work / (label + '.py'), 0o644)
    data = read(work, 'public.json') + read(work, 'hidden.json')
    require(len(data) == 20, 'SAMPLE_COUNT')
    records = {label: [[] for _ in range(20)] for label in programs}
    safety = True
    violation_codes = []
    try:
        for index, case in enumerate(data):
            for repeat in range(3):
                order = ('baseline', 'candidate', 'degraded') if repeat % 2 == 0 else ('degraded', 'candidate', 'baseline')
                for label in order:
                    outcome = box.run(work / (label + '.py'), canonical(case['input']))
                    failed = bool(outcome['error'] or outcome['exit'] or outcome['stderr'] or outcome['oom'] or outcome['container_exit'])
                    answer, cpu = [], None
                    if not failed:
                        try:
                            require(len(outcome['stdout']) <= 262144, 'RESULT_LIMIT')
                            answer, cpu = findings(load_json(outcome['stdout']))
                        except EvaluationError:
                            failed = True
                    if outcome['error'] or outcome['oom']:
                        safety = False
                        violation_codes.append('EXECUTION_LIMIT')
                    records[label][index].append({'correct': not failed and answer == sorted(map(tuple, case['expected'])),
                        'failed': failed, 'answer_hash': digest(canonical(answer)),
                        'wall_seconds': outcome['wall_seconds'], 'reported_cpu_seconds': cpu})
        verify_manifest(work)
        for label, original in programs.items():
            require(digest(regular(work / (label + '.py'), RUNS)) == digest(original), 'ARTIFACT_CHANGED')
        metrics, unstable = compare_records(records)
        decisions = {label: judge(metrics['baseline'], metrics[label], safety=safety,
                                  same_artifact=label == 'baseline', contaminated=unstable)
                     for label in programs}
        # A run is an evaluation result, not an adoption action. A failed control can never complete it.
        control_verified = decisions['degraded']['status'] == 'FAIL' and decisions['baseline']['status'] == 'HOLD'
        status = decisions['candidate']['status']
        if status == 'PASS' and not control_verified:
            status = 'HOLD'
        report = {'schema_version': 1, 'run_id': work.name, 'classification': 'PUBLIC',
                  'status': status,
                  'baseline_sha': baseline_sha, 'candidate_sha': candidate_sha,
                  'artifact_hashes': {label: digest(value) for label, value in programs.items()},
                  'manifest_hash': digest(regular(work / 'manifest.json', RUNS)),
                  'image': read(work, 'environment.json')['image'],
                  'dataset_commitments': manifest['dataset_hashes'],
                  'metrics': {label: {'public_correct': sum(m['correct'][:10]), 'hidden_correct': sum(m['correct'][10:]),
                              'cases': 20, 'executions': 60, 'failures': m['failures'],
                              'failure_rate': m['failures'] / 60, 'median_wall_seconds': m['latency'],
                              'api_calls': 0, 'tokens': 0, 'api_cost_usd': 0, 'inference': 'not_applicable'}
                              for label, m in metrics.items()},
                  'decisions': decisions, 'control_verified': control_verified,
                  'safety': 'VERIFIED' if safety else 'FAILED', 'violation_codes': sorted(set(violation_codes)),
                  'permission_violations': 0,
                  'state': 'AWAITING_APPROVAL' if status == 'PASS'
                           else 'REJECTED' if status == 'FAIL' else 'HELD',
                  'limitations': ['finite deterministic fixture', 'no real LLM or production acceptance'],
                  'utc': stamp()}
        save(work, 'metrics.private.json', records)
        report['private_metrics_hash'] = digest(regular(work / 'metrics.private.json', RUNS, 2097152))
        save(work, 'report.json', report)
        lines = ['# 独立評価結果', '', f"全体判定: {status} / 状態: {report['state']}",
                 f'基準SHA: {baseline_sha}', f'候補SHA: {candidate_sha}', '',
                 '| 版 | 公開正答/10 | hidden正答/10 | 失敗/60 | median秒 | 判定 |',
                 '| --- | --- | --- | --- | --- | --- |']
        for label, row in report['metrics'].items():
            lines.append(f"| {label} | {row['public_correct']} | {row['hidden_correct']} | {row['failures']} | "
                         f"{row['median_wall_seconds']:.4f} | {decisions[label]['status']} |")
        lines += ['', '判定理由: ' + ', '.join(decisions['candidate']['reasons'] or ['ALL_FIXTURE_CRITERIA_MET']),
                  'API呼出・token・費用: 0。推論は未実施。実LLM品質・本番検収は未検証。',
                  'hiddenの個別入力・正解・traceは掲載しない。PASSも人間の承認待ちであり採用ではない。']
        write_new(work / 'report.md', ('\n'.join(lines) + '\n').encode())
        event(work, 'EVALUATION_COMPLETED', digest(regular(work / 'report.json', RUNS)))
        save(work, 'checkpoint.json', {'report_hash': digest(regular(work / 'report.json', RUNS)),
                                      'markdown_hash': digest(regular(work / 'report.md', RUNS)),
                                      'last_event_hash': verify_events(work)[-1]['hash']})
        print(json.dumps({'run_id': work.name, 'status': status, 'decisions': decisions, 'state': report['state']}))
    except Exception as error:
        code = str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR'
        save(work, 'stopped.json', {'status': 'STOPPED', 'reason': code,
             'completed_executions': sum(len(item) for rows in records.values() for item in rows),
             'manifest_hash': digest(regular(work / 'manifest.json', RUNS)), 'utc': stamp()})
        event(work, 'EVALUATION_STOPPED', digest(regular(work / 'stopped.json', RUNS)))
        raise


def verify_events(work):
    rows = [load_json(line) for line in regular(work / 'events.jsonl', RUNS, 2097152).splitlines()]
    previous = ZERO
    for index, row in enumerate(rows):
        unsigned = {k: v for k, v in row.items() if k != 'hash'}
        require(row['index'] == index and row['run_id'] == work.name and row['previous_hash'] == previous and
                row['hash'] == digest(canonical(unsigned)), 'AUDIT_CHAIN')
        previous = row['hash']
    require(bool(rows), 'AUDIT_EMPTY')
    require(rows[0]['state'] == 'ENVIRONMENT_PINNED', 'AUDIT_START')
    bindings = {'ENVIRONMENT_PINNED': 'environment.json', 'ISOLATION_VERIFIED': 'gate.json',
                'ISOLATION_FAILED': 'gate.json', 'EVALUATION_FROZEN': 'manifest.json',
                'EVALUATING': 'evaluation-lock.json', 'EVALUATION_STOPPED': 'stopped.json',
                'EVALUATION_COMPLETED': 'report.json'}
    for row in rows:
        require(row['state'] in bindings and
                digest(regular(work / bindings[row['state']], RUNS)) == row['payload_hash'], 'AUDIT_BINDING')
    return rows


def audit(work):
    verify_manifest(work)
    rows = verify_events(work)
    require([r['state'] for r in rows] == ['ENVIRONMENT_PINNED', 'ISOLATION_VERIFIED',
            'EVALUATION_FROZEN', 'EVALUATING', 'EVALUATION_COMPLETED'], 'AUDIT_STATES')
    require(rows[-1]['state'] == 'EVALUATION_COMPLETED', 'AUDIT_INCOMPLETE')
    report_bytes = regular(work / 'report.json', RUNS)
    checkpoint = read(work, 'checkpoint.json')
    require(digest(report_bytes) == rows[-1]['payload_hash'] == checkpoint['report_hash'] and
            rows[-1]['hash'] == checkpoint['last_event_hash'] and
            digest(regular(work / 'report.md', RUNS)) == checkpoint['markdown_hash'], 'AUDIT_REPORT')
    report = load_json(report_bytes)
    lock = read(work, 'evaluation-lock.json')
    require(lock['baseline_sha'] == report['baseline_sha'] and lock['candidate_sha'] == report['candidate_sha'] and
            lock['manifest_hash'] == report['manifest_hash'], 'AUDIT_LOCK')
    require(digest(regular(work / 'metrics.private.json', RUNS, 2097152)) == report['private_metrics_hash'],
            'AUDIT_METRICS')
    require(report['manifest_hash'] == digest(regular(work / 'manifest.json', RUNS)), 'AUDIT_MANIFEST')
    for label, expected in report['artifact_hashes'].items():
        require(digest(regular(work / (label + '.py'), RUNS)) == expected, 'AUDIT_ARTIFACT')
    require(digest(git_bytes(report['baseline_sha'])) == report['artifact_hashes']['baseline'] and
            digest(git_bytes(report['candidate_sha'])) == report['artifact_hashes']['candidate'], 'AUDIT_SHA')
    print(json.dumps({'run_id': work.name, 'audit': 'VERIFIED', **checkpoint}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('bootstrap', 'gate', 'freeze', 'evaluate', 'audit'))
    parser.add_argument('run_id', nargs='?')
    parser.add_argument('--baseline-sha')
    parser.add_argument('--candidate-sha')
    args = parser.parse_args()
    try:
        if args.operation == 'bootstrap':
            bootstrap()
        else:
            work = run_path(args.run_id or '')
            if args.operation == 'evaluate':
                evaluate(work, args.baseline_sha, args.candidate_sha)
            else:
                {'gate': gate, 'freeze': freeze, 'audit': audit}[args.operation](work)
    except (EvaluationError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        code = str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR'
        print(json.dumps({'status': 'STOPPED', 'reason': code}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
