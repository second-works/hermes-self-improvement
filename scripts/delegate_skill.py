#!/usr/bin/env python3
"""Issue #7: one real Hermes delegation, local Gemma only, no production operations."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from evaluation.sandbox import Sandbox
from delegation.core import IMAGE, UPSTREAM, candidate_files, correct_output, handoff, public_cases, specification
from delegation.relay import LocalModel, live_context
from delegation.sandbox import DelegationSandbox

PROGRAM = ROOT / 'fixtures/delegation/worker.py'
PREPARER = ROOT / 'fixtures/delegation/prepare.py'
PROBE = ROOT / 'fixtures/self-evolution/isolation_probe.py'
PREPARATION = ROOT / ('runs/delegation-prepare-' + UPSTREAM[:12])
SOURCE_GIT = PREPARATION / 'source-git'
PACKAGES = ['openai==2.24.0', 'rich==14.3.3', 'python-dotenv==1.2.2', 'fire==0.7.1',
            'httpx[socks]==0.28.1', 'tenacity==9.1.4', 'ruamel.yaml==0.18.16',
            'requests==2.33.0', 'jinja2==3.1.6', 'pydantic==2.13.4', 'PyYAML==6.0.3',
            'prompt_toolkit==3.0.52', 'croniter==6.0.0', 'snowballstemmer==3.1.1',
            'PyJWT==2.13.0', 'psutil==7.2.2', 'websockets==15.0.1', 'pathspec==1.1.1',
            'packaging==26.0', 'Pillow==12.3.0', 'truststore==0.10.4',
            'tiktoken==0.12.0', 'jsonschema==4.26.0']
CONTROL = ['scripts/delegate_skill.py', 'src/delegation/core.py', 'src/delegation/relay.py',
           'src/delegation/patch.py',
           'src/delegation/experiment.py', 'src/delegation/cycle.py', 'src/delegation/execution.py',
           'src/delegation/context.py',
           'src/delegation/sandbox.py', 'fixtures/delegation/worker.py', 'fixtures/delegation/prepare.py',
           'src/evaluation/core.py', 'src/evaluation/sandbox.py', 'src/self_evolution/sandbox.py',
           'fixtures/self-evolution/isolation_probe.py', 'scripts/self_evolution_spike.py',
           'fixtures/audit/delegation.json', 'src/audit/core.py',
           'fixtures/self-evolution/hermes-agent/skills/github-code-review/SKILL.md']


def save(work, name, value):
    write_new(work / name, canonical(value) + b'\n')


def hashes(root):
    require(not root.is_symlink() and root.is_dir(), 'TREE_BOUNDARY')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'TREE_SYMLINK')
        if not path.is_dir():
            result[str(path.relative_to(root))] = digest(regular(path, root, 8 * 1024**2))
    return result


def source_snapshot():
    source = SOURCE_GIT
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
    def git(*args):
        r = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(source), *args],
                           env=env, capture_output=True, timeout=15)
        require(r.returncode == 0, 'SOURCE_GIT')
        return r.stdout
    require(git('rev-parse', 'HEAD').decode().strip() == UPSTREAM, 'UPSTREAM_SHA')
    destination = PREPARATION / 'source'
    destination.mkdir(exist_ok=False)
    total = 0
    for entry in git('ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, oid, stage = metadata.split()
        path = Path(name.decode())
        if not (source / path).exists() or path.suffix not in ('.py', '.json', '.yaml', '.yml', '.toml', '.txt', '.md', '.tiktoken', '.jinja', '.j2'):
            continue
        require(stage == b'0' and mode in (b'100644', b'100755'), 'SOURCE_MODE')
        data = regular(source / path, source, 2097152)
        require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest().encode() == oid,
                'SOURCE_DIRTY')
        total += len(data)
        require(total <= 64 * 1024**2, 'SOURCE_LIMIT')
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, data)
        target.chmod(0o444)  # PUBLIC source must be readable by the unprivileged container UID.
    source_hashes = hashes(destination)
    require(len(source_hashes) > 100, 'SOURCE_INCOMPLETE')
    save(PREPARATION, 'source-manifest.json', {'upstream_sha': UPSTREAM, 'files': source_hashes, 'bytes': total})


def prepare(wheels=None):
    report = {'status': 'STOPPED', 'phase': 'prepare', 'reason': 'PREPARATION_INCOMPLETE'}
    PREPARATION.mkdir(parents=True, exist_ok=True)
    require(not (PREPARATION / 'prepare-report.json').exists(), 'PREPARATION_ALREADY_ATTEMPTED')
    try:
        source_snapshot()
        (PREPARATION / 'packages/site').mkdir(parents=True)
        (PREPARATION / 'packages').chmod(0o777)
        (PREPARATION / 'packages/site').chmod(0o777)
        write_new(PREPARATION / 'requirements.lock', b'# Preparation is not yet locked.\n')
        (PREPARATION / 'requirements.lock').chmod(0o444)
        box = DelegationSandbox(ROOT, PREPARATION, IMAGE, preparation=PREPARATION,
                                deadline=time.monotonic() + 600)
        report['environment'] = box.environment()
        report['image'] = box.image_info(IMAGE)
        if wheels is None:
            box.phase = 'download'
            result = box.run(PREPARER, canonical({'mode': 'download', 'packages': PACKAGES}), timeout=550)
            require(not result['error'] and result['exit'] == 0 and result['container_exit'] == 0, 'WHEEL_DOWNLOAD')
        else:
            expected = regular(ROOT / 'fixtures/delegation/requirements.lock', ROOT).decode()
            (PREPARATION / 'packages/wheels').mkdir()
            for path in sorted(wheels.iterdir()):
                data = regular(path, ROOT / 'runs', 100 * 1024**2)
                require(path.suffix == '.whl' and digest(data) in expected, 'WHEEL_HASH_MISMATCH')
                write_new(PREPARATION / 'packages/wheels' / path.name, data)
                (PREPARATION / 'packages/wheels' / path.name).chmod(0o444)
        wheels, rows, wheel_bytes = {}, [], 0
        for path in sorted((PREPARATION / 'packages/wheels').iterdir()):
            require(path.suffix == '.whl' and not path.is_symlink(), 'WHEEL_FORMAT')
            data = regular(path, PREPARATION, 100 * 1024**2)
            wheel_bytes += len(data)
            require(wheel_bytes <= 512 * 1024**2, 'WHEEL_LIMIT')
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
                require(len(names) == 1 and archive.getinfo(names[0]).file_size <= 262144, 'WHEEL_METADATA')
                meta = BytesParser().parsebytes(archive.read(names[0]))
            name, version = meta['Name'], meta['Version']
            require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) and re.fullmatch(r'[A-Za-z0-9_.+!-]+', version), 'PACKAGE_NAME')
            sha = digest(data)
            wheels[path.name] = sha
            rows.append(f'{name}=={version} --hash=sha256:{sha}')
        require(0 < len(rows) <= 100, 'PACKAGE_COUNT')
        lock = ('\n'.join(sorted(rows)) + '\n').encode()
        (PREPARATION / 'requirements.lock').chmod(0o600)
        (PREPARATION / 'requirements.lock').write_bytes(lock)
        (PREPARATION / 'requirements.lock').chmod(0o444)
        tracked_lock = ROOT / 'fixtures/delegation/requirements.lock'
        if tracked_lock.exists():
            require(regular(tracked_lock, ROOT) == lock, 'LOCK_CHANGED')
        else:
            write_new(tracked_lock, lock)
        box.phase = 'install'
        result = box.run(PREPARER, canonical({'mode': 'install'}), timeout=120)
        require(not result['error'] and result['exit'] == 0 and result['container_exit'] == 0, 'OFFLINE_INSTALL')
        report.update(status='VERIFIED', reason=None, wheel_hashes=wheels, wheel_bytes=wheel_bytes,
                      source_manifest_hash=digest(regular(PREPARATION / 'source-manifest.json', PREPARATION, 1048576)),
                      lock_hash=digest(lock), dependency_hashes=hashes(PREPARATION / 'packages/site'))
    except Exception as error:
        report['reason'] = str(error) if isinstance(error, EvaluationError) else 'PREPARE_ERROR'
        if hasattr(error, 'pending_container'):
            report['pending_container'] = error.pending_container
        raise
    finally:
        save(PREPARATION, 'prepare-report.json', report)
        print(json.dumps({'phase': 'prepare', 'status': report['status'], 'reason': report['reason']}))


def verify_preparation():
    report = load_json(regular(PREPARATION / 'prepare-report.json', PREPARATION, 2097152))
    require(report['status'] == 'VERIFIED', 'PREPARATION_NOT_VERIFIED')
    require(digest(regular(PREPARATION / 'requirements.lock', PREPARATION)) == report['lock_hash'] and
            digest(regular(ROOT / 'fixtures/delegation/requirements.lock', ROOT)) == report['lock_hash'], 'LOCK_CHANGED')
    manifest_data = regular(PREPARATION / 'source-manifest.json', PREPARATION, 1048576)
    require(digest(manifest_data) == report['source_manifest_hash'], 'SOURCE_MANIFEST_CHANGED')
    manifest = load_json(manifest_data)
    require(manifest['upstream_sha'] == UPSTREAM and hashes(PREPARATION / 'source') == manifest['files'], 'SOURCE_CHANGED')
    require(hashes(PREPARATION / 'packages/site') == report['dependency_hashes'], 'DEPENDENCIES_CHANGED')
    return report


def gate(box):
    # Reuse the fixed Issue #6 probe/validator with this controller's exact matching limits/mounts.
    import importlib.util
    spec = importlib.util.spec_from_file_location('spike_gate', ROOT / 'scripts/self_evolution_spike.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    box.phase = 'gate'
    results = {}
    for mode in ('boundaries', 'disk', 'memory', 'pids', 'cpu', 'timeout', 'output'):
        outcome = box.run(PROBE, canonical({'mode': mode}), timeout=3 if mode == 'timeout' else 30)
        results[mode] = module.validate_gate(mode, outcome)
    return results


def invoke(box, mode, *, record_label=None, **fields):
    label = record_label or mode
    require(re.fullmatch('[a-z0-9-]{1,40}', label) is not None, 'RECORD_LABEL')
    box.phase = 'probe'
    phase_seconds = max(1, min(3540, int(box.deadline - time.monotonic())))
    try:
        outcome = box.run(PROGRAM, canonical({'mode': mode, 'runtime_context': box.runtime_context,
                          'phase_seconds': phase_seconds, 'child_seconds': box.relay.child_seconds, **fields}),
                          timeout=phase_seconds)
    except EvaluationError as failure:
        save(box.work, label + '.events.json', getattr(failure, 'protocol_events', []))
        save(box.work, label + '.failure.json', {'reason': str(failure)})
        raise
    # Only the actual fixed worker outcome, never its prose success claim, drives state.
    write_new(box.work / (label + '.stderr.txt'), outcome['stderr'])
    save(box.work, label + '.events.json', outcome.get('events', []))
    value = load_json(outcome['stdout'])
    save(box.work, label + '.json', value)
    if type(value) is dict and value.get('reason') == 'RUNTIME_CONTEXT_UNSUPPORTED':
        require(False, 'RUNTIME_CONTEXT_UNSUPPORTED')
    require(not outcome['error'] and outcome['exit'] == 0 and outcome['container_exit'] == 0 and
            type(value) is dict and value.get('status') == 'VERIFIED', 'HERMES_' + mode.upper() + '_FAILED')
    return value


def check_candidate(unit, work, value, label, cases):
    candidate_files(value)
    for name, content in value.items():
        path = work / label / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new(path, content.encode())
        path.chmod(0o444)
    results, details = [], []
    for case in cases:
        outcome = unit.run(work / label / 'scripts/review.py', canonical(case['input']))
        require(not outcome['error'] and outcome['exit'] == 0 and not outcome['stderr'] and
                outcome['container_exit'] == 0, 'CANDIDATE_TEST_FAILED')
        try:
            passed = correct_output(load_json(outcome['stdout']), case)
            protocol = 'JSON'
        except EvaluationError:
            passed, protocol = False, 'INVALID_JSON_OR_OUTPUT_SCHEMA'
        results.append(passed)
        details.append({'passed': passed, 'protocol': protocol,
                        'stdout_bytes': len(outcome['stdout']), 'stdout_hash': digest(outcome['stdout'])})
    save(work, label + '-tests.json', results)
    save(work, label + '-test-details.json', details)
    return results


def repair_existing(box, work, seed_report, deadline):
    seed = load_json(regular(seed_report, ROOT / 'runs'))
    source = seed_report.parent / 'candidate'
    files = {name: regular(source / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == seed.get('candidate_hashes'), 'REPAIR_SEED_CHANGED')
    save(work, 'repair-seed.json', {'report': str(seed_report.relative_to(ROOT)),
                                  'hashes': candidate_files(files)})
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    def check(value, label):
        return check_candidate(unit, work, value, label, public_cases())
    before = check(files, 'repair-baseline')
    require(before == [True, True, True, False, True, False], 'REPAIR_BASELINE_CHANGED')
    for attempt, target, index in ((1, 'comment', 3), (2, 'context_line', 5)):
        if before[index]:
            continue
        repaired = invoke(box, 'repair', record_label='repair-' + str(attempt), files=files, target=target)['files']
        require(repaired['SKILL.md'] == files['SKILL.md'] and
                repaired['scripts/review.py'] != files['scripts/review.py'], 'REPAIR_SCOPE')
        after = check(repaired, 'repair-candidate-' + str(attempt))
        save(work, 'repair-comparison-' + str(attempt) + '.json',
             {'target': target, 'before': before, 'after': after,
              'hashes': candidate_files(repaired)})
        require(not any(old and not new for old, new in zip(before, after)), 'REPAIR_REGRESSION')
        require(after[index] and sum(after) > sum(before), 'REPAIR_NO_IMPROVEMENT')
        files, before = repaired, after
    require(all(before), 'PUBLIC_UNIT_FAILED')
    return files, before


def bounded_patch_existing(box, work, seed_report, deadline, start_attempt=1):
    from delegation.patch import apply_counter_patch, counter_cases
    source = seed_report.parent / 'repair-candidate-1'
    expected = load_json(regular(seed_report.parent / 'repair-comparison-1.json', ROOT / 'runs'))['hashes']
    files = {name: regular(source / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == expected, 'REPAIR_SEED_CHANGED')
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    cases = public_cases() + counter_cases()
    before = check_candidate(unit, work, files, 'patch-baseline', cases)
    require(before[:6] == [True, True, True, True, True, False], 'REPAIR_BASELINE_CHANGED')
    save(work, 'patch-seed.json', {'report': str(seed_report.relative_to(ROOT)), 'hashes': expected})
    # Read-only relay rejects model-selected writes before Hermes can execute them.
    box.relay.reuse = True
    require(start_attempt in (1, 2), 'PATCH_ATTEMPT')
    for attempt in range(start_attempt, 3):
        box.relay.proposal_only = True
        try:
            proposed = invoke(box, 'propose_patch', record_label='patch-' + str(attempt), files=files,
                              patch_attempt=attempt)
        finally:
            box.relay.proposal_only = False
        require(proposed.get('source_sha256') == digest(files['scripts/review.py'].encode()), 'PATCH_SOURCE_CHANGED')
        try:
            proposal = load_json(proposed['final'].encode())
            repaired = {**files, 'scripts/review.py': apply_counter_patch(files['scripts/review.py'], proposal)}
        except (EvaluationError, SyntaxError):
            save(work, 'patch-rejected-' + str(attempt) + '.json', {'reason': 'PATCH_REJECTED'})
            raise EvaluationError('PATCH_REJECTED') from None
        after = check_candidate(unit, work, repaired, 'patch-candidate-' + str(attempt), cases)
        save(work, 'patch-comparison-' + str(attempt) + '.json',
             {'before': before, 'after': after, 'hashes': candidate_files(repaired)})
        require(not any(old and not new for old, new in zip(before, after)), 'REPAIR_REGRESSION')
        require(sum(after) > sum(before), 'REPAIR_NO_IMPROVEMENT')
        files, before = repaired, after
        if all(after):
            return files, after
    raise EvaluationError('PUBLIC_UNIT_FAILED')


def matrix_existing(box, work, seed_report, deadline):
    from delegation.experiment import CONDITIONS, patch_shape
    from delegation.patch import apply_counter_patch, counter_cases
    from delegation.context import resources
    source = seed_report.parent / 'repair-candidate-1'
    expected = load_json(regular(seed_report.parent / 'repair-comparison-1.json', ROOT / 'runs'))['hashes']
    files = {name: regular(source / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == expected, 'REPAIR_SEED_CHANGED')
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    cases = public_cases() + counter_cases()
    before = check_candidate(unit, work, files, 'matrix-baseline', cases)
    require(before[:6] == [True, True, True, True, True, False], 'REPAIR_BASELINE_CHANGED')
    experiment = {'classification': 'PUBLIC', 'trials_per_condition': 1,
                  'limitations': 'Exploratory fixed-order comparison; not a reliability estimate.',
                  'source_hashes': expected, 'baseline': before, 'rows': []}
    qualified = []
    box.relay.reuse = True
    def persist():
        (work / 'matrix-progress.json').write_bytes(canonical(experiment) + b'\n')
    for thinking, structured in CONDITIONS:
        label = 'matrix-' + ('on' if thinking else 'off') + '-' + ('schema' if structured else 'plain')
        row = {'label': label, 'thinking_requested': thinking, 'schema_requested': structured,
               'json_valid': False, 'shape_valid': False, 'scope_valid': False, 'tests': None,
               'resources_before': resources()}
        experiment['rows'].append(row)
        start = time.monotonic()
        calls_before = box.relay.calls
        box.relay.condition = (thinking, structured)
        box.relay.proposal_only = True
        try:
            proposed = invoke(box, 'propose_patch', record_label=label, files=files, patch_attempt=1)
            require(proposed.get('source_sha256') == digest(files['scripts/review.py'].encode()), 'PATCH_SOURCE_CHANGED')
            observation = box.relay.condition_observations[-1]
            row['thinking_output_observed'] = observation.get('reasoning_characters', 0) > 0
            row['thinking_verified'] = (observation.get('thinking_prompt_observed') == thinking and
                                        row['thinking_output_observed'] == thinking)
            try:
                proposal = load_json(proposed['final'].encode())
                row['json_valid'] = True
            except EvaluationError:
                proposal = None
            row['shape_valid'] = patch_shape(proposal)
            if row['shape_valid']:
                try:
                    repaired = {**files, 'scripts/review.py': apply_counter_patch(files['scripts/review.py'], proposal)}
                    row['scope_valid'] = True
                except (EvaluationError, SyntaxError):
                    repaired = None
                if repaired is not None:
                    row['tests'] = check_candidate(unit, work, repaired, label + '-candidate', cases)
                    row['candidate_hashes'] = candidate_files(repaired)
                    if all(row['tests']):
                        qualified.append((repaired, row))
        except EvaluationError as error:
            row['runtime_error'] = str(error)
            raise
        finally:
            box.relay.proposal_only = False
            box.relay.condition = None
            row['elapsed_seconds'] = round(time.monotonic() - start, 3)
            row['model_calls'] = box.relay.calls - calls_before
            row['observations'] = box.relay.condition_observations[-row['model_calls']:] if row['model_calls'] else []
            row['resources_after'] = resources()
            persist()
    save(work, 'matrix.json', experiment)
    return experiment, qualified


def operation_existing(box, work, seed_report, deadline):
    from delegation.patch import apply_operations, counter_cases, OPERATION_IDS
    from delegation.context import resources
    source = seed_report.parent / 'repair-candidate-1'
    expected = load_json(regular(seed_report.parent / 'repair-comparison-1.json', ROOT / 'runs'))['hashes']
    files = {name: regular(source / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == expected, 'REPAIR_SEED_CHANGED')
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    cases = public_cases() + counter_cases()
    experiment = {'classification': 'PUBLIC', 'source_hashes': expected, 'rows': [],
                  'limitations': 'Four controlled fixtures, one trial each. Trusted repairs are predefined; this measures selection, not code generation.'}
    variants = [('both-missing', [], list(OPERATION_IDS)),
                ('none-missing', list(OPERATION_IDS), []),
                ('comment-missing', [OPERATION_IDS[0]], [OPERATION_IDS[1]]),
                ('context-missing', [OPERATION_IDS[1]], [OPERATION_IDS[0]])]
    box.relay.reuse = True
    for label, present, needed in variants:
        fixture = {**files, 'scripts/review.py': apply_operations(files['scripts/review.py'], {'operations': present})}
        row = {'label': label, 'expected_operations': needed, 'json_valid': False,
               'scope_valid': False, 'selection_correct': False, 'tests': None,
               'fixture_hashes': candidate_files(fixture), 'resources_before': resources()}
        experiment['rows'].append(row)
        row['baseline'] = check_candidate(unit, work, fixture, 'operations-' + label + '-baseline', cases)
        start, calls_before = time.monotonic(), box.relay.calls
        box.relay.condition = (True, True)
        box.relay.output_kind = 'operations'
        box.relay.proposal_only = True
        try:
            proposed = invoke(box, 'select_operations', record_label='operations-' + label, files=fixture)
            require(proposed.get('source_sha256') == digest(fixture['scripts/review.py'].encode()), 'PATCH_SOURCE_CHANGED')
            try:
                proposal = load_json(proposed['final'].encode())
                row['json_valid'] = True
            except EvaluationError:
                proposal = None
            try:
                repaired = {**fixture, 'scripts/review.py': apply_operations(fixture['scripts/review.py'], proposal)}
                row['scope_valid'] = True
            except (EvaluationError, SyntaxError) as error:
                row['rejection'] = str(error)
                repaired = None
            if repaired is not None:
                row['selected_operations'] = proposal['operations']
                row['selection_correct'] = set(proposal['operations']) == set(needed)
                row['tests'] = check_candidate(unit, work, repaired, 'operations-' + label + '-candidate', cases)
                row['candidate_hashes'] = candidate_files(repaired)
        finally:
            box.relay.proposal_only = False
            box.relay.condition = None
            box.relay.output_kind = 'patch'
            row['elapsed_seconds'] = round(time.monotonic() - start, 3)
            row['model_calls'] = box.relay.calls - calls_before
            row['resources_after'] = resources()
            (work / 'operations-progress.json').write_bytes(canonical(experiment) + b'\n')
    save(work, 'operations.json', experiment)
    return experiment


def cycle_existing(box, work, seed_report, deadline, *, controlled=False):
    from delegation.patch import apply_operations, counter_cases
    from delegation.cycle import transfer_cases, acceptance
    source = seed_report.parent / 'repair-candidate-1'
    hashes_before = load_json(regular(seed_report.parent / 'repair-comparison-1.json', ROOT / 'runs'))['hashes']
    files = {name: regular(source / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == hashes_before, 'REPAIR_SEED_CHANGED')
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    public = public_cases() + counter_cases()
    separate = transfer_cases()
    current = check_candidate(unit, work, files, 'cycle-baseline', public + separate)
    experiment = {'classification': 'PUBLIC', 'baseline': current, 'public_case_count': len(public),
                  'transfer_case_count': len(separate), 'source_hashes': hashes_before,
                  'limitations': 'Predefined repair selection; transfer fixtures are separate from the prompt, not a sealed independent evaluation.',
                  'rounds': [], 'reuse': 'NOT_RUN', 'adoption': 'NOT_REQUESTED'}
    box.relay.reuse = True
    def persist():
        (work / 'cycle-progress.json').write_bytes(canonical(experiment) + b'\n')
    for number in (1, 2):
        row = {'round': number, 'before': current, 'before_hashes': candidate_files(files)}
        experiment['rounds'].append(row)
        box.relay.condition = (True, True)
        box.relay.output_kind = 'operations'
        box.relay.proposal_only = True
        try:
            result = invoke(box, 'select_operations', record_label='cycle-select-' + str(number), files=files)
            require(result.get('source_sha256') == digest(files['scripts/review.py'].encode()), 'PATCH_SOURCE_CHANGED')
            try:
                proposal = load_json(result['final'].encode())
                candidate = {**files, 'scripts/review.py': apply_operations(files['scripts/review.py'], proposal)}
            except (EvaluationError, SyntaxError) as error:
                row.update(decision='REJECTED_PROPOSAL', rejection=str(error))
                break
            after = check_candidate(unit, work, candidate, 'cycle-candidate-' + str(number), public + separate)
            decision = acceptance(current, after, candidate == files)
            row.update(operations=proposal['operations'], after=after, decision=decision,
                       candidate_hashes=candidate_files(candidate))
            if decision == 'ACCEPTED':
                files, current = candidate, after
            else:
                break
        finally:
            box.relay.proposal_only = False
            box.relay.condition = None
            box.relay.output_kind = 'patch'
            persist()
    experiment['final_hashes'] = candidate_files(files)
    experiment['final_results'] = current
    # Keep accepted bytes separately; no source fixture or production file is changed.
    for name, content in files.items():
        target = work / 'cycle-retained' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, content.encode())
        target.chmod(0o444)
    require(candidate_files({name: regular(source / name, ROOT / 'runs', 65536).decode()
                             for name in files}) == hashes_before, 'CYCLE_SOURCE_CHANGED')
    if controlled:
        from delegation.execution import execute_batch, execution_cases
        require(all(current) and experiment['rounds'][-1]['decision'] in ('ACCEPTED', 'UNCHANGED'),
                'CONTROLLED_CANDIDATE_UNQUALIFIED')
        jobs = execution_cases()
        results = execute_batch(unit, work / 'cycle-retained/scripts/review.py', [job['input'] for job in jobs])
        checks = [correct_output(result, job) for result, job in zip(results, jobs)]
        save(work, 'execution-results.json', results)
        experiment['execution'] = {'result_owner': 'controller_from_actual_script_stdout',
                                   'model_role': 'bounded_operation_selection_only', 'checks': checks,
                                   'results_hash': digest(canonical(results)),
                                   'limitation': 'Predefined repairs and two fixed public jobs; not autonomous skill interpretation.'}
        experiment['reuse'] = 'NOT_APPLICABLE_DIRECT_EXECUTION'
        persist()
        require(all(checks), 'CONTROLLED_EXECUTION_FAILED')
        save(work, 'cycle.json', experiment)
        return experiment
    if all(current) and experiment['rounds'][-1]['decision'] in ('ACCEPTED', 'UNCHANGED'):
        box.relay.condition = (True, False)
        experiment['reuse'] = 'RUNNING'
        persist()
        try:
            case = {'path': 'case_cyclereuse00.py', 'patch': '@@ -21,1 +21,3 @@\n context\n+# note\n+eval(value)'}
            reused = invoke(box, 'reuse', record_label='cycle-reuse', files=files, case=case)
            expected = {'input': case, 'expected': [('case_cyclereuse00.py', 23, 'dynamic-eval')]}
            experiment['reuse'] = ('VERIFIED' if correct_output(load_json(reused['final'].encode()), expected)
                                   else 'FAILED_OUTPUT')
        except EvaluationError as error:
            experiment['reuse'] = 'FAILED_' + str(error)
            raise
        finally:
            box.relay.condition = None
            persist()
    save(work, 'cycle.json', experiment)
    return experiment


def reuse_cycle_existing(box, work, seed_report, deadline):
    from delegation.patch import counter_cases
    from delegation.cycle import transfer_cases
    seed = load_json(regular(seed_report, ROOT / 'runs'))
    progress = load_json(regular(seed_report.parent / 'cycle-progress.json', ROOT / 'runs'))
    require(seed.get('status') == 'STOPPED' and seed.get('reason') == 'JSON_INVALID' and
            len(progress['final_results']) == 15 and all(progress['final_results']) and
            progress['rounds'][-1]['decision'] == 'UNCHANGED', 'REUSE_SEED_NOT_QUALIFIED')
    files = {name: regular(seed_report.parent / 'cycle-retained' / name, ROOT / 'runs', 65536).decode()
             for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == progress['final_hashes'], 'REUSE_SEED_CHANGED')
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    tests = check_candidate(unit, work, files, 'reuse-retained', public_cases() + counter_cases() + transfer_cases())
    require(all(tests), 'REUSE_RETEST_FAILED')
    result = {'classification': 'PUBLIC', 'tests': tests, 'source_hashes': candidate_files(files),
              'reuse': 'RUNNING', 'limitations': 'Actual skill reads and model interpretation; generated script runs separately in unit-test sandbox.'}
    box.relay.reuse = True
    box.relay.condition = (True, False)
    try:
        case = {'path': 'case_cyclereuse00.py', 'patch': '@@ -21,1 +21,3 @@\n context\n+# note\n+eval(value)'}
        reused = invoke(box, 'reuse', record_label='reuse-contract', files=files, case=case, strict_reuse=True)
        expected = {'input': case, 'expected': [('case_cyclereuse00.py', 23, 'dynamic-eval')]}
        require(correct_output(load_json(reused['final'].encode()), expected), 'REUSE_OUTPUT_FAILED')
        result['reuse'] = 'VERIFIED'
        return result
    except EvaluationError as error:
        result['reuse'] = 'FAILED_' + str(error)
        raise
    finally:
        box.relay.condition = None
        save(work, 'reuse-result.json', result)


def run(check_only=False, carry_report=None, deadline_epoch=None, request_timeout=90, budget_profile='standard',
        repair_report=None, patch_only=False, patch_attempt=1, matrix=False, operations=False, cycle=False, reuse_cycle=False, controlled_execution=False):
    run_id = 'delegation-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(6)
    work = ROOT / 'runs' / run_id
    work.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'run_id': run_id, 'classification': 'PUBLIC',
              'status': 'STOPPED', 'state': 'STOPPED', 'reason': 'RUN_INCOMPLETE',
              'model': 'gemma-4-e4b', 'upstream_sha': UPSTREAM, 'evaluation': 'NOT_RUN', 'adoption': 'NOT_REQUESTED'}
    relay = None
    try:
        preparation = verify_preparation()
        report['control_hashes'] = {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}
        report['preparation_hash'] = digest(canonical(preparation))
        spec = specification(budget_profile)
        report['budget_profile'] = budget_profile
        spec['budget'].update(request_seconds=request_timeout, child_seconds=max(300, request_timeout * 3),
                              seconds=min(3600, int(deadline_epoch - time.time())) if deadline_epoch else 1200)
        from audit.core import audit
        diagnosis = audit(load_json(regular(ROOT / 'fixtures/audit/delegation.json', ROOT)))
        require(len(diagnosis['proposals']) == 1 and diagnosis['proposals'][0]['cause'] == 'skill_gap', 'AUDIT_GAP')
        save(work, 'diagnostic-fixture.json', diagnosis)
        spec['diagnostic_proposal_hash'] = diagnosis['proposals'][0]['proposal_hash']
        spec['diagnostic_scope'] = 'synthetic fixture under the audit fixed revision; not the runtime inventory'
        save(work, 'specification.json', spec)
        deadline = time.monotonic() + (min(3540, deadline_epoch - time.time()) if deadline_epoch else 1200)
        require(deadline - time.monotonic() > 0, 'RUN_DEADLINE')
        carried = None
        if carry_report is not None:
            previous = load_json(regular(carry_report, ROOT / 'runs'))
            carried = {key: previous['model_usage'][key] for key in ('calls', 'input_tokens', 'output_tokens')}
            report['carried_budget'] = carried
        def journal(event):
            event = {**event, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            fd = os.open(work / 'progress.jsonl', os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'ab') as stream:
                stream.write(canonical(event) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
        def tool_trace(event):
            path = work / 'tool-calls.jsonl'
            line = canonical(event) + b'\n'
            require((path.stat().st_size if path.exists() else 0) + len(line) <= 2097152, 'TOOL_TRACE_LIMIT')
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'ab') as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
        relay = LocalModel(deadline, initial_usage=carried, request_timeout=request_timeout,
                           event_sink=journal, budget_profile=budget_profile, tool_sink=tool_trace)
        report['timeouts'] = {'request_seconds': request_timeout, 'child_seconds': relay.child_seconds,
                              'remaining_seconds': int(deadline - time.monotonic())}
        box = DelegationSandbox(ROOT, work, IMAGE, preparation=PREPARATION, deadline=deadline)
        report['environment'] = box.environment()
        report['image'] = box.image_info(IMAGE)
        report['gate'] = gate(box)
        box.runtime_context = live_context()
        report['runtime_context'] = box.runtime_context
        box.relay = relay
        invoke(box, 'boot')
        if check_only:
            report.update(status='VERIFIED', state='RUNTIME_READY', reason=None)
            return
        if reuse_cycle:
            report['reuse_cycle'] = reuse_cycle_existing(box, work, repair_report, deadline)
            require(report['control_hashes'] == {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}, 'CONTROL_CHANGED')
            verify_preparation()
            report.update(status='VERIFIED', state='SAVED_CYCLE_REUSE_VERIFIED', reason=None)
            return
        if cycle or controlled_execution:
            report['cycle'] = cycle_existing(box, work, repair_report, deadline, controlled=controlled_execution)
            require(report['control_hashes'] == {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}, 'CONTROL_CHANGED')
            verify_preparation()
            report.update(status='VERIFIED', state=('CONTROLLED_EXECUTION_VERIFIED' if controlled_execution else 'IMPROVEMENT_CYCLE_MEASURED'), reason=None)
            return
        if operations:
            experiment = operation_existing(box, work, repair_report, deadline)
            report['operation_rows'] = experiment['rows']
            require(report['control_hashes'] == {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}, 'CONTROL_CHANGED')
            verify_preparation()
            report.update(status='VERIFIED', state='OPERATION_SELECTION_MEASURED', reason=None)
            return
        preverified = None
        if matrix:
            experiment, qualified = matrix_existing(box, work, repair_report, deadline)
            report['matrix_rows'] = experiment['rows']
            if not qualified:
                require(report['control_hashes'] == {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}, 'CONTROL_CHANGED')
                verify_preparation()
                report.update(status='VERIFIED', state='MATRIX_MEASURED_NO_QUALIFIED_CANDIDATE', reason=None)
                return
            files, best = next((entry for entry in qualified if entry[1]['schema_requested']), qualified[0])
            preverified = best['tests'][:6]
            report['matrix_selected'] = best['label']
            report['reuse_controls'] = {'thinking': best['thinking_requested'], 'json_schema': False,
                                       'note': 'Saved-skill reuse is separate from patch-generation comparison.'}
            relay.condition = (best['thinking_requested'], False)
            created = {'files': files}
        elif repair_report is not None:
            files, outcomes = (bounded_patch_existing(box, work, repair_report, deadline, patch_attempt)
                               if patch_only else repair_existing(box, work, repair_report, deadline))
            created = {'files': files}
        else:
            invoke(box, 'capability')
            created = invoke(box, 'create', specification=spec)
        files = created['files']
        report['candidate_hashes'] = candidate_files(files)
        for name, content in files.items():
            path = work / 'candidate' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            write_new(path, content.encode())
            path.chmod(0o444)
        # Reuse the existing no-network runner. No generated code is imported on the host.
        unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
        outcomes = list(preverified) if preverified is not None else []
        for case in ([] if preverified is not None else public_cases()):
            outcome = unit.run(work / 'candidate/scripts/review.py', canonical(case['input']))
            require(not outcome['error'] and outcome['exit'] == 0 and not outcome['stderr'] and
                    outcome['container_exit'] == 0, 'CANDIDATE_TEST_FAILED')
            outcomes.append(correct_output(load_json(outcome['stdout']), case))
        save(work, 'public-tests.json', outcomes)
        require(all(outcomes), 'PUBLIC_UNIT_FAILED')
        reuse_case = {'path': 'case_reuse001.py', 'patch': '@@ -21,0 +21,1 @@\n+eval(value)'}
        relay.reuse = True
        reused = invoke(box, 'reuse', files=files, case=reuse_case)
        expected = {'input': reuse_case, 'expected': [('case_reuse001.py', 21, 'dynamic-eval')]}
        require(correct_output(load_json(reused['final'].encode()), expected), 'REUSE_OUTPUT_FAILED')
        baseline = regular(ROOT / 'fixtures/skills/github-code-review/review.py', ROOT).decode()
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                 env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin'}, timeout=5).decode().strip()
        patch, manifest = handoff(files, baseline, baseline_sha=sha, spec_hash=digest(canonical(spec)), results=outcomes)
        write_new(work / 'candidate.diff', patch.encode())
        save(work, 'handoff.json', manifest)
        require(report['control_hashes'] == {p: digest(regular(ROOT / p, ROOT)) for p in CONTROL}, 'CONTROL_CHANGED')
        verify_preparation()
        report.update(status='VERIFIED', state='READY_FOR_INDEPENDENT_EVALUATION', reason=None,
                      handoff_hash=digest(canonical(manifest)))
    except Exception as error:
        report['reason'] = str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR'
        if hasattr(error, 'pending_container'):
            report['pending_container'] = error.pending_container
        raise
    finally:
        if relay is not None:
            if relay.rejected_tool_calls:
                save(work, 'rejected-tool-calls.json', relay.rejected_tool_calls)
            report['model_usage'] = {'calls': relay.calls, 'input_tokens': relay.input_tokens,
                                    'output_tokens': relay.output_tokens, 'records': relay.records, 'cost_usd': 0,
                                    'accounting': 'RESERVED_ON_FAILURE' if relay.failed else 'SETTLED',
                                    'usage_observations': relay.usage_observations,
                                    'transport_failure': relay.transport_failure}
            report['condition_observations'] = relay.condition_observations
        save(work, 'report.json', report)
        print(json.dumps({'run_id': run_id, 'status': report['status'], 'reason': report['reason']}))


if __name__ == '__main__':
    def stopped(signum, frame):
        raise EvaluationError('OPERATOR_STOP')
    signal.signal(signal.SIGTERM, stopped)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'check', 'run', 'temporary-64k', 'temporary-64k-memory',
                                          'temporary-64k-compact'))
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--wheels', type=Path)
    parser.add_argument('--carry-report', type=Path)
    parser.add_argument('--repair-report', type=Path)
    parser.add_argument('--patch-only', action='store_true')
    parser.add_argument('--patch-attempt', type=int, choices=(1, 2), default=1)
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--operations', action='store_true')
    parser.add_argument('--cycle', action='store_true')
    parser.add_argument('--reuse-cycle', action='store_true')
    parser.add_argument('--controlled-execution', action='store_true')
    parser.add_argument('--deadline-epoch', type=float)
    parser.add_argument('--request-timeout', type=int, choices=(90, 180, 300, 600), default=90)
    parser.add_argument('--budget-profile', choices=('standard', 'extended', 'extended60', 'extended80', 'patch88', 'matrix94', 'cycle100', 'controlled102'), default='standard')
    args = parser.parse_args()
    try:
        require(not args.patch_only or args.repair_report is not None, 'PATCH_SEED_REQUIRED')
        require(not args.matrix or args.repair_report is not None and not args.patch_only and
                args.action in ('temporary-64k-memory', 'run'), 'MATRIX_BOUNDARY')
        require(not args.operations or args.repair_report is not None and not args.patch_only and not args.matrix and
                args.action in ('temporary-64k-memory', 'run'), 'OPERATIONS_BOUNDARY')
        require(not args.cycle or args.repair_report is not None and not any((args.patch_only, args.matrix, args.operations)) and
                args.action in ('temporary-64k-memory', 'run'), 'CYCLE_BOUNDARY')
        require(not args.reuse_cycle or args.repair_report is not None and not any((args.patch_only, args.matrix, args.operations, args.cycle)) and
                args.action in ('temporary-64k-memory', 'run'), 'REUSE_CYCLE_BOUNDARY')
        require(not args.controlled_execution or args.repair_report is not None and not any((args.patch_only, args.matrix, args.operations, args.cycle, args.reuse_cycle)) and
                args.action in ('temporary-64k-memory', 'run'), 'CONTROLLED_BOUNDARY')
        if args.repair_report is not None:
            args.repair_report = args.repair_report.absolute()
            require(args.repair_report.name == 'report.json' and
                    args.repair_report.is_relative_to(ROOT / 'runs'), 'REPAIR_REPORT_BOUNDARY')
        if args.carry_report is not None:
            args.carry_report = args.carry_report.absolute()
            require(args.carry_report.name == 'report.json' and
                    args.carry_report.is_relative_to(ROOT / 'runs'), 'CARRIED_REPORT_BOUNDARY')
        if args.deadline_epoch is not None:
            require(time.time() < args.deadline_epoch <= time.time() + 3600, 'RUN_DEADLINE')
        if args.preparation is not None:
            candidate = args.preparation.absolute()
            require(candidate.parent == ROOT / 'runs' and candidate.name.startswith('delegation-prepare-') and
                    not candidate.is_symlink(), 'PREPARATION_BOUNDARY')
            PREPARATION = candidate
        if args.wheels is not None:
            args.wheels = args.wheels.absolute()
            require(args.action == 'prepare' and args.wheels.is_relative_to(ROOT / 'runs') and
                    '..' not in args.wheels.parts and not args.wheels.is_symlink(), 'WHEEL_BOUNDARY')
        if args.action in ('temporary-64k', 'temporary-64k-memory', 'temporary-64k-compact'):
            from delegation.context import run_temporary
            verify_preparation()
            run_temporary(ROOT, PREPARATION, memory_saving=args.action in ('temporary-64k-memory', 'temporary-64k-compact'),
                          carry_report=args.carry_report, deadline_epoch=args.deadline_epoch,
                          request_timeout=args.request_timeout, budget_profile=args.budget_profile,
                          compact_memory=args.action == 'temporary-64k-compact', repair_report=args.repair_report,
                          patch_only=args.patch_only, patch_attempt=args.patch_attempt, matrix=args.matrix, operations=args.operations, cycle=args.cycle, reuse_cycle=args.reuse_cycle, controlled_execution=args.controlled_execution)
        else:
            prepare(args.wheels) if args.action == 'prepare' else run(
                check_only=args.action == 'check', carry_report=args.carry_report,
                deadline_epoch=args.deadline_epoch, request_timeout=args.request_timeout,
                budget_profile=args.budget_profile, repair_report=args.repair_report, patch_only=args.patch_only,
                patch_attempt=args.patch_attempt, matrix=args.matrix, operations=args.operations, cycle=args.cycle, reuse_cycle=args.reuse_cycle, controlled_execution=args.controlled_execution)
    except (EvaluationError, OSError, ValueError):
        raise SystemExit(1) from None
