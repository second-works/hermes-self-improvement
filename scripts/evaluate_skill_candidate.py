#!/usr/bin/env python3
"""Freeze a registered PUBLIC skill context; evaluate one receipted proposal offline."""
import argparse
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from adoption.core import save, syncdir, utc
from delegation.core import IMAGE
from delegation.generated import git
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from evaluation.profiles import (PROFILES, apply, artifacts, cases, decision, diff, hashes, launcher,
                                 observe, profile, response)
from evaluation.sandbox import capture
from github_work_guide.core import REPO
from intake_public_failure import failure_event_id
from run_mock_improvement import hex_id, reject_stopped, state_lock, prepare_state

spec = importlib.util.spec_from_file_location('profile_evaluation_gate', ROOT / 'scripts/evaluate_fixture.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate.SOURCES += ['src/evaluation/profiles.py', 'scripts/evaluate_skill_candidate.py',
                 'scripts/run_public_hermes.py', 'scripts/run_mock_improvement.py',
                 'scripts/intake_public_failure.py', 'src/github_work_guide/core.py',
                 'src/delegation/generated.py', 'src/delegation/core.py', 'src/adoption/core.py',
                 'fixtures/generated_skills/event-counts-task/contract.json']
STATE = ROOT / 'runs/profile-evaluation'


def check_entry(entry):
    fields = ('schema_version status classification source_kind repo event_id pr_url pr_number '
              'head_sha check_id conclusion snapshot_hash reproduction_sha256').split()
    require(type(entry) is dict and set(entry) == set(fields), 'PROFILE_ENTRY')
    require(type(entry['schema_version']) is int and entry['schema_version'] == 1
            and entry['status'] == 'AWAITING_HUMAN_REVIEW' and entry['classification'] == 'PUBLIC'
            and entry['source_kind'] == 'public-github-check' and entry['repo'] == REPO
            and entry['conclusion'] == 'failure', 'PROFILE_ENTRY')
    require(type(entry['pr_number']) is int and entry['pr_number'] > 0
            and type(entry['check_id']) is int and entry['check_id'] > 0
            and hex_id(entry['head_sha'], 40) and hex_id(entry['snapshot_hash'], 64)
            and hex_id(entry['reproduction_sha256'], 64)
            and entry['pr_url'] == f'https://github.com/{REPO}/pull/{entry["pr_number"]}'
            and entry['event_id'] == failure_event_id(entry['pr_number'], entry['head_sha'], entry['check_id']),
            'PROFILE_EVENT_BINDING')


def mapping_plan(entry, name):
    check_entry(entry)
    selected = profile(name)
    files = artifacts(ROOT, entry['head_sha'], selected)
    return {'schema_version': 1, 'event_id': entry['event_id'], 'repo': REPO,
            'head_sha': entry['head_sha'], 'reproduction_sha256': entry['reproduction_sha256'],
            'profile_id': name, 'profile_hash': selected.hash, 'artifact_hashes': hashes(files),
            'public_case_id': name + ':public:' + str(selected.reproduction_index)}


def stopped():
    reject_stopped(ROOT / 'runs/public-hermes/intake-stop.json')


def events(work):
    """Same #65 hash chain, with fixed profile-specific payload bindings."""
    bindings = {'ENVIRONMENT_PINNED': 'environment.json', 'ISOLATION_VERIFIED': 'gate.json',
                'ISOLATION_FAILED': 'gate.json', 'PROFILE_FROZEN': 'profile-manifest.json',
                'PROFILE_EVALUATED': 'profile-report.json', 'PROFILE_MEMORY_RECORDED': 'profile-memory.json'}
    rows = [load_json(line) for line in regular(work / 'events.jsonl', gate.RUNS, 2097152).splitlines()]
    previous = gate.ZERO
    for index, row in enumerate(rows):
        unsigned = {k: v for k, v in row.items() if k != 'hash'}
        require(row['index'] == index and row['run_id'] == work.name and row['previous_hash'] == previous
                and row['hash'] == digest(canonical(unsigned)), 'PROFILE_AUDIT_CHAIN')
        require(row['state'] in bindings and row['payload_hash'] ==
                digest(regular(work / bindings[row['state']], gate.RUNS)), 'PROFILE_AUDIT_BINDING')
        previous = row['hash']
    require(rows and rows[0]['state'] == 'ENVIRONMENT_PINNED', 'PROFILE_AUDIT_START')
    return rows


def manifest(work):
    gate.verify_gate(work)
    m = gate.read(work, 'profile-manifest.json')
    selected = profile(m['profile_id'])
    check_entry(m['entry'])
    require(m['profile_hash'] == selected.hash and m['sources'] == gate.source_hashes(), 'PROFILE_STALE')
    require(canonical(m['mapping']) == canonical(mapping_plan(m['entry'], selected.id)), 'PROFILE_MAPPING_CHANGED')
    for label in ('public', 'hidden', 'sources', 'environment', 'gate', 'budget'):
        file = 'sources.json' if label == 'sources' else label + '.json'
        require(digest(regular(work / file, gate.RUNS)) == m['hashes'][label], 'PROFILE_FROZEN_CHANGED')
    require(hashes(gate.read(work, 'sources.json')) == m['mapping']['artifact_hashes'], 'PROFILE_SOURCE_CHANGED')
    rows = events(work)
    anchors = [row for row in rows if row['state'] == 'PROFILE_FROZEN']
    require(len(anchors) == 1 and anchors[0]['payload_hash'] == digest(regular(work / 'profile-manifest.json', gate.RUNS)),
            'PROFILE_MANIFEST_ANCHOR')
    return m


def context(run_id, entry):
    work = gate.run_path(run_id)
    m = manifest(work)
    require(m['entry'] == entry, 'PROFILE_CONTEXT_BINDING')
    selected = profile(m['profile_id'])
    contract = ('Review a PUBLIC Python unified patch. Report every added dynamic eval and subprocess '
                'shell=True call, including multiline calls; preserve the path and first added call line. '
                'Output exactly findings(path,line,rule) and cpu_seconds. No findings for safe calls.')
    if selected.id == 'event-status-counts-v1':
        contract = load_json(regular(ROOT / 'fixtures/generated_skills/event-counts-task/contract.json', ROOT))
    return {'run_id': work.name, 'manifest_hash': digest(regular(work / 'profile-manifest.json', gate.RUNS)),
            'profile_id': selected.id, 'profile_hash': selected.hash, 'skill_id': selected.skill,
            'baseline_sha': entry['head_sha'], 'artifact_hashes': m['mapping']['artifact_hashes'],
            'artifacts': gate.read(work, 'sources.json'),
            'public_case_id': m['mapping']['public_case_id'],
            'public_reproduction': gate.read(work, 'public.json')[selected.reproduction_index],
            'public_contract': contract,
            'allowlist': list(selected.artifacts)}


def prepare(entry, name, mapping):
    check_entry(entry)
    selected = profile(name)
    require(canonical(mapping) == canonical(mapping_plan(entry, name)), 'PROFILE_MAPPING')
    prepare_state(STATE)
    prepare_state(ROOT / 'runs/public-hermes')
    stopped()
    with state_lock(STATE, 'controller.lock'), state_lock(ROOT / 'runs/public-hermes', 'controller.lock'):
        stopped()
        require(not (STATE / 'pending.json').exists(), 'PROFILE_RECOVERY_REQUIRED')
        claim = STATE / entry['event_id']
        require(not os.path.lexists(claim), 'PROFILE_ALREADY_CLAIMED')
        claim.mkdir(mode=0o700)
        save(claim / 'started.json', {'event_id': entry['event_id'], 'profile_hash': selected.hash})
        save(STATE / 'pending.json', {'event_id': entry['event_id'], 'phase': 'PREPARING'})
        started = time.monotonic()
        try:
            return prepare_claimed(entry, selected, mapping, claim, started)
        except Exception as error:
            save(claim / 'stopped.json', {'state': 'RECOVERY_REQUIRED',
                'reason': str(error) if isinstance(error, EvaluationError) else 'PROFILE_PREPARATION_FAILED',
                'pending_container': getattr(error, 'pending_container', None)})
            raise


def prepare_claimed(entry, selected, mapping, claim, started):
    # Called only while both controller locks and a durable pending record are held.
    # Existing isolation probes, exact image identity and evaluator provenance are reused.
    with contextlib.redirect_stdout(io.StringIO()) as out:
        gate.bootstrap(IMAGE)
    run_id = load_json(out.getvalue())['run_id']
    work = gate.run_path(run_id)
    save(claim / 'run.json', {'run_id': run_id})
    with contextlib.redirect_stdout(io.StringIO()):
        gate.gate(work)
    for path, value in gate.source_hashes().items():
        require(digest(git(ROOT, 'show', 'HEAD:' + path)) == value, 'PROFILE_EVALUATOR_NOT_COMMITTED')
    files = artifacts(ROOT, entry['head_sha'], selected)
    public, hidden = cases(selected, gate.cases), cases(selected, gate.cases, True)
    for label, value in [('sources', files), ('public', public), ('hidden', hidden)]:
        gate.save(work, label + '.json', value)
    program = work / 'reproduction.py'
    write_new(program, launcher(files, selected))
    program.chmod(0o444)
    box = gate.sandbox(work)
    box.deadline = started + 1200
    stopped()
    case = public[selected.reproduction_index]
    outcome = box.run(program, case['stdin'].encode())
    observed = observe(selected, outcome, case)
    require(not observed['failed'] and not observed['correct'], 'PROFILE_REPRODUCTION_REQUIRED')
    gate.save(work, 'budget.json', {'machine_seconds': time.monotonic() - started})
    m = {'schema_version': 1, 'entry': entry, 'profile_id': selected.id, 'profile_hash': selected.hash,
         'mapping': mapping, 'sources': gate.source_hashes(),
         'hashes': {label: digest(regular(work / (label + '.json'), gate.RUNS))
                    for label in ('sources', 'public', 'hidden', 'environment', 'gate', 'budget')}}
    gate.save(work, 'profile-manifest.json', m)
    gate.event(work, 'PROFILE_FROZEN', digest(regular(work / 'profile-manifest.json', gate.RUNS)))
    stopped()
    (STATE / 'pending.json').unlink()
    syncdir(STATE)
    return context(run_id, entry)

def candidate_commit(work, baseline_sha, files):
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_INDEX_FILE': str(work / 'candidate.index'),
           'GIT_AUTHOR_NAME': 'Fixture Controller', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
           'GIT_COMMITTER_NAME': 'Fixture Controller', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
    def write(*args, data=b''):
        result = capture(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                          '-C', str(ROOT), *args], env=env, data=data, timeout=10)
        require(not result['error'] and result['exit'] == 0, 'PROFILE_GIT_FAILED')
        return result['stdout'].decode().strip()
    # Only a private index and unreachable objects are written; no branch/worktree is modified.
    write('read-tree', baseline_sha)
    for path, content in files.items():
        blob = write('hash-object', '-w', '--stdin', data=content.encode())
        write('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path)
    tree = write('write-tree')
    return write('commit-tree', tree, '-p', baseline_sha, data=b'PUBLIC isolated candidate\n')


def verify_proposal(work, m, raw):
    value = load_json(raw)
    require(type(value) is dict, 'PROFILE_PROPOSAL_SCHEMA')
    require(raw in (canonical(value), canonical(value) + b'\n'), 'PROFILE_PROPOSAL_ENCODING')
    expected = {'schema_version': 1, 'event_id': m['entry']['event_id'],
                'packet_hash': digest(canonical(m['entry'])), 'classification': 'PUBLIC',
                'source_kind': 'public-github-check', 'baseline_sha': m['entry']['head_sha'],
                'context_run': work.name, 'context_manifest_hash': digest(regular(work / 'profile-manifest.json', gate.RUNS))}
    require(all(type(value.get(k)) is type(v) and value[k] == v for k, v in expected.items()), 'PROFILE_PROPOSAL_BINDING')
    require(hex_id(value.get('approval_hash'), 64), 'PROFILE_APPROVAL_BINDING')
    metadata = set(expected) | {'approval_hash'}
    decision = response({k: v for k, v in value.items() if k not in metadata or k == 'schema_version'}, profile(m['profile_id']))
    receipt = load_json(regular(ROOT / 'runs/public-hermes' / expected['event_id'] / 'finished.json', ROOT / 'runs', 2048))
    require(receipt == {'event_id': expected['event_id'], 'packet_hash': expected['packet_hash'],
                       'status': 'COMPLETED', 'decision': decision['decision'],
                       'result_hash': digest(canonical(value))}, 'PROFILE_PROPOSAL_RECEIPT')
    return decision


def evaluate(run_id, raw):
    require(len(raw) <= 65536, 'PROFILE_PROPOSAL_SIZE')
    prepare_state(STATE)
    prepare_state(ROOT / 'runs/public-hermes')
    work = gate.run_path(run_id)
    with state_lock(STATE, 'controller.lock'), state_lock(ROOT / 'runs/public-hermes', 'controller.lock'):
        stopped()
        require(not (STATE / 'pending.json').exists(), 'PROFILE_RECOVERY_REQUIRED')
        m = manifest(work)
        selected = profile(m['profile_id'])
        require(not (work / 'profile-evaluation-lock.json').exists(), 'PROFILE_RUN_USED')
        # Consume the attempt before parsing any model-controlled response.
        gate.save(work, 'profile-evaluation-lock.json', {'proposal_hash': digest(raw),
                  'manifest_hash': digest(regular(work / 'profile-manifest.json', gate.RUNS))})
        save(STATE / 'pending.json', {'run_id': run_id, 'phase': 'EVALUATING'})
        try:
            proposal = verify_proposal(work, m, raw)
            if proposal['decision'] != 'PROPOSE':
                report = {'state': proposal['decision'], 'reason': 'MODEL_' + proposal['decision']}
            else:
                report = evaluate_edits(work, m, selected, proposal)
        except EvaluationError as error:
            if getattr(error, 'pending_container', None):
                gate.save(work, 'profile-stopped.json', {'state': 'RECOVERY_REQUIRED', 'reason': str(error),
                          'pending_container': error.pending_container})
                raise
            state = 'STOPPED' if str(error) in ('INTAKE_STOPPED', 'PROFILE_BUDGET', 'CASE_DEADLINE',
                                               'SANDBOX_STOPPED', 'TIMEOUT') else 'REJECTED'
            report = {'state': state, 'reason': str(error)}
        except Exception:
            gate.save(work, 'profile-stopped.json', {'state': 'RECOVERY_REQUIRED', 'reason': 'PROFILE_CONTROLLER_FAILED'})
            raise EvaluationError('PROFILE_RECOVERY_REQUIRED') from None
        report.update(schema_version=1, event_id=m['entry']['event_id'], run_id=run_id,
                      profile_hash=selected.hash, proposal_hash=digest(raw),
                      manifest_hash=digest(regular(work / 'profile-manifest.json', gate.RUNS)))
        gate.save(work, 'profile-report.json', report)
        gate.event(work, 'PROFILE_EVALUATED', digest(regular(work / 'profile-report.json', gate.RUNS)))
        memory = memory_record(work, m, report)
        gate.save(work, 'profile-memory.json', memory)
        gate.event(work, 'PROFILE_MEMORY_RECORDED', digest(regular(work / 'profile-memory.json', gate.RUNS)))
        (STATE / 'pending.json').unlink()
        syncdir(STATE)
        return report


def evaluate_edits(work, m, selected, proposal):
    before = gate.read(work, 'sources.json')
    after = apply(before, proposal['edits'])
    candidate_sha = candidate_commit(work, m['entry']['head_sha'], after)
    require(artifacts(ROOT, candidate_sha, selected) == after, 'PROFILE_CANDIDATE_CHANGED')
    patch = diff(before, after)
    gate.save(work, 'candidate-files.json', after)
    write_new(work / 'candidate.diff', patch.encode())
    # The control only returns an empty result; it cannot satisfy the improving cases.
    degraded = dict(before)
    degraded[selected.entrypoint] = ('import json\nprint(json.dumps(' +
        repr({'findings': [], 'cpu_seconds': 0} if selected.id == 'review-multiline-shell-v1' else {'counts': {}}) + '))\n')
    programs = {}
    for label, files in [('baseline', before), ('candidate', after), ('degraded', degraded)]:
        path = work / (label + '-bundle.py')
        write_new(path, launcher(files, selected)); path.chmod(0o444)
        programs[label] = path
    charged = gate.read(work, 'budget.json')['machine_seconds']
    require(type(charged) in (int, float) and 0 < charged < 1200, 'PROFILE_BUDGET')
    box = gate.sandbox(work)
    box.deadline = time.monotonic() + 1200 - charged
    public, hidden = gate.read(work, 'public.json'), gate.read(work, 'hidden.json')
    records = {label: [[] for _ in public + hidden] for label in programs}
    for index, case in enumerate(public + hidden):
        for repeat in range(3):
            labels = ('baseline', 'candidate', 'degraded')
            for label in labels[repeat:] + labels[:repeat]:
                stopped()
                outcome = box.run(programs[label], case['stdin'].encode(), timeout=min(30, max(0, box.deadline-time.monotonic())))
                records[label][index].append(observe(selected, outcome, case))
    require(time.monotonic() < box.deadline, 'PROFILE_BUDGET')
    metrics, unstable = gate.compare_records(records)
    safety = all(not sample['safety_failure'] for rows in records.values() for row in rows for sample in row)
    state, verdict, control = decision(metrics, safety=safety, unstable=unstable,
                                       public_count=len(public), hidden_count=len(hidden), edits=proposal['edits'])
    manifest(work)
    require(artifacts(ROOT, candidate_sha, selected) == after, 'PROFILE_CANDIDATE_CHANGED')
    for label, files in [('baseline', before), ('candidate', after), ('degraded', degraded)]:
        require(regular(programs[label], gate.RUNS, 65536) == launcher(files, selected), 'PROFILE_BUNDLE_CHANGED')
    gate.save(work, 'profile-metrics.private.json', records)
    report = {'state': state, 'decision': verdict, 'control': control,
              'private_metrics_hash': digest(regular(work / 'profile-metrics.private.json', gate.RUNS)),
              'counts': {label: {'public_correct': sum(metric['correct'][:len(public)]),
                                  'hidden_correct': sum(metric['correct'][len(public):]),
                                  'failures': metric['failures']} for label, metric in metrics.items()},
              'baseline_sha': m['entry']['head_sha'], 'candidate_sha': candidate_sha,
              'artifact_hashes': {'baseline': hashes(before), 'candidate': hashes(after)},
              'diff_hash': digest(patch.encode()), 'evidence_refs': proposal['evidence_refs'],
              'claim': 'finite registered PUBLIC contract; no adoption; CI causality is not established'}
    return report


def memory_record(work, m, report):
    candidate = None
    if 'candidate_sha' in report:
        candidate = {'commit_sha': report['candidate_sha'],
                     'artifact_sha256': digest(canonical(report['artifact_hashes']['candidate']))}
    measured = 'decision' in report
    return {'schema_version': 1, 'run_id': work.name, 'recorded_at': utc().replace('+00:00', 'Z'),
            'classification': 'PUBLIC', 'iteration': 1,
            'baseline': {'commit_sha': m['entry']['head_sha'],
                         'artifact_sha256': digest(canonical(m['mapping']['artifact_hashes']))},
            'candidate': candidate,
            'metrics': {'status': 'VERIFIED' if measured else 'NOT_VERIFIED',
                        'evidence_sha256': digest(regular(work / 'profile-report.json', gate.RUNS)) if measured else None,
                        'values': [{'name': 'evaluation_completed', 'value': 1, 'unit': 'count'}] if measured else []},
            'approval': {'status': 'PENDING' if report['state'] == 'AWAITING_HUMAN_APPROVAL' else 'NOT_REQUESTED',
                         'record_sha256': None},
            'rollback': {'status': 'NOT_REQUESTED', 'record_sha256': None}}


def audit(run_id):
    work = gate.run_path(run_id)
    m = manifest(work)
    report = gate.read(work, 'profile-report.json')
    rows = events(work)
    for state, filename in [('PROFILE_EVALUATED', 'profile-report.json'),
                            ('PROFILE_MEMORY_RECORDED', 'profile-memory.json')]:
        anchors = [row for row in rows if row['state'] == state]
        require(len(anchors) == 1 and anchors[0]['payload_hash'] == digest(regular(work / filename, gate.RUNS)),
                'PROFILE_AUDIT_CHANGED')
    require(report['manifest_hash'] == digest(regular(work / 'profile-manifest.json', gate.RUNS))
            and report['event_id'] == m['entry']['event_id']
            and gate.read(work, 'profile-evaluation-lock.json') == {
                'proposal_hash': report['proposal_hash'], 'manifest_hash': report['manifest_hash']},
            'PROFILE_AUDIT_BINDING')
    require(gate.read(work, 'profile-memory.json') == memory_record_for_audit(work, m, report), 'PROFILE_MEMORY_CHANGED')
    if 'candidate_sha' in report:
        selected = profile(m['profile_id'])
        before = artifacts(ROOT, m['entry']['head_sha'], selected)
        after = artifacts(ROOT, report['candidate_sha'], selected)
        require(report['artifact_hashes'] == {'baseline': hashes(before), 'candidate': hashes(after)}
                and gate.read(work, 'candidate-files.json') == after
                and regular(work / 'candidate.diff', gate.RUNS) == diff(before, after).encode()
                and report['diff_hash'] == digest(diff(before, after).encode()), 'PROFILE_AUDIT_ARTIFACT')
        require(report['private_metrics_hash'] == digest(regular(work / 'profile-metrics.private.json', gate.RUNS)),
                'PROFILE_AUDIT_METRICS')
    return {'status': 'VERIFIED', 'run_id': run_id, 'state': report['state'],
            'report_hash': digest(regular(work / 'profile-report.json', gate.RUNS))}


def memory_record_for_audit(work, m, report):
    expected = memory_record(work, m, report)
    expected['recorded_at'] = gate.read(work, 'profile-memory.json')['recorded_at']
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('mapping-plan', 'prepare'):
        p = sub.add_parser(command)
        p.add_argument('--entry', required=True, type=Path)
        p.add_argument('--profile', required=True, choices=sorted(PROFILES))
        if command == 'prepare': p.add_argument('--mapping', required=True, type=Path)
    p = sub.add_parser('evaluate'); p.add_argument('--run', required=True); p.add_argument('--proposal', required=True, type=Path)
    p = sub.add_parser('audit'); p.add_argument('--run', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'audit': result = audit(args.run)
        elif args.command == 'evaluate':
            result = evaluate(args.run, regular(args.proposal, args.proposal.absolute().parent, 65536))
        else:
            entry = load_json(regular(args.entry, args.entry.absolute().parent, 8192))
            if args.command == 'mapping-plan': result = mapping_plan(entry, args.profile)
            else:
                from run_public_hermes import owner_file
                result = prepare(entry, args.profile, load_json(owner_file(args.mapping, 8192)))
        print(canonical(result).decode()); return 0
    except (EvaluationError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('{"status":"STOPPED","reason":"PROFILE_OPERATION_FAILED"}', file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main())
