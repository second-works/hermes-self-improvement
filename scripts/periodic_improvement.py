#!/usr/bin/env python3
"""Disabled-by-default handoff from completed inspections to approved improvement jobs."""
import argparse
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_skill_candidate as profiles
import evaluate_skill_semantics as semantic
import run_public_hermes as generation
from adoption.core import save, syncdir
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require
from github_work_guide.collector import GhReadOnly
from github_work_guide.core import Invalid, complete, load_run
from run_mock_improvement import control_intake, hex_id, prepare_state, state_lock
from select_public_failure import bind, select

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'runs/periodic-improvement'
RUN_NAME = re.compile(r'periodic-\d{8}-\d{4}\Z')
SEMANTIC_REASON = ['STRUCTURE_ONLY_SEMANTIC_EVALUATION_REQUIRED']


def read(path):
    return load_json(regular(path, STATE, 65536))


def configuration():
    require(not any(path.is_symlink() for path in (STATE, *STATE.parents)), 'PATH_SYMLINK')
    path = STATE / 'config.json'
    if not os.path.lexists(path):
        return None
    raw = generation.owner_file(path, 1024)
    value = load_json(raw)
    require(type(value) is dict and set(value) == {'schema_version', 'enabled'}
            and type(value['schema_version']) is int and value['schema_version'] == 1
            and type(value['enabled']) is bool, 'PERIODIC_CONFIG')
    return digest(raw) if value['enabled'] else None


def inspection(path):
    path = Path(path).absolute()
    require(path.parent == ROOT / 'runs' and RUN_NAME.fullmatch(path.name), 'PERIODIC_RUN_PATH')
    snapshot = load_run(path)
    complete(snapshot)
    require(hex_id(snapshot['hash'], 64), 'PERIODIC_SNAPSHOT')
    return snapshot


def allowed(config_hash):
    require(configuration() == config_hash, 'PERIODIC_CONFIG_CHANGED')
    profiles.stopped()
    generation.reject_profile_pending()


def once(job, name, operation):
    """An interrupted action is never repeated, even when its lower-level receipt is missing."""
    result, started = job / (name + '.json'), job / (name + '-started.json')
    if os.path.lexists(result):
        require(read(started) == {'operation': name}, 'PERIODIC_ACTION_BINDING')
        return read(result)
    require(not os.path.lexists(started), 'PERIODIC_RECOVERY_REQUIRED')
    save(started, {'operation': name})
    value = operation()
    save(result, value)
    return value


def receipt(job, status, **values):
    return {'status': status, 'event_id': job.name, **values}


def finish(job, status, **values):
    result = receipt(job, status, **values)
    save(job / 'finished.json', result)
    return result


def jobs():
    parent = STATE / 'events'
    prepare_state(parent)
    result = []
    for path in sorted(parent.iterdir()):
        require(hex_id(path.name, 64) and path.is_dir() and not path.is_symlink(), 'PERIODIC_JOB_PATH')
        if not os.path.lexists(path / 'finished.json'):
            result.append(path)
    return result


def choose(run, snapshot, transport):
    check = STATE / 'checks' / (snapshot['hash'] + '.json')
    if os.path.lexists(check):
        value = read(check)
        require(type(value) is dict and set(value) == {'run', 'snapshot_hash', 'event_id'}
                and value['run'] == run.name and value['snapshot_hash'] == snapshot['hash']
                and (value['event_id'] is None or hex_id(value['event_id'], 64)), 'PERIODIC_CHECK_BINDING')
        return None if value['event_id'] is None else STATE / 'events' / value['event_id']
    waiting = jobs()
    if waiting:
        # One outstanding job takes this inspection's slot; never select a second event.
        job = waiting[0]
    else:
        seen = {p.name for p in (STATE / 'events').iterdir()}
        public_state = ROOT / 'runs/public-hermes'
        if public_state.exists():
            seen.update(p.name for p in public_state.iterdir() if hex_id(p.name, 64))
        selected = select(run, STATE / 'reproductions', seen, transport)
        if selected['status'] == 'SKIP':
            job = None
        else:
            require(selected['status'] == 'SELECTED', 'PERIODIC_SELECTION')
            entry = selected['candidate']
            profiles.check_entry(entry)
            require(entry['snapshot_hash'] == snapshot['hash'], 'PERIODIC_SELECTION_BINDING')
            job = STATE / 'events' / entry['event_id']
            job.mkdir(mode=0o700)
            syncdir(job.parent)
            save(job / 'entry.json', {'run': run.name, 'entry': entry})
    save(check, {'run': run.name, 'snapshot_hash': snapshot['hash'], 'event_id': job.name if job else None})
    return job


def advance(job, config_hash, transport):
    if os.path.lexists(job / 'finished.json'):
        result = read(job / 'finished.json')
        require(result.get('event_id') == job.name, 'PERIODIC_RESULT_BINDING')
        return result
    try:
        record = read(job / 'entry.json')
        require(type(record) is dict and set(record) == {'run', 'entry'}, 'PERIODIC_JOB_BINDING')
        entry = record['entry']
        profiles.check_entry(entry)
        require(entry['event_id'] == job.name, 'PERIODIC_JOB_BINDING')
        source = ROOT / 'runs' / record['run']
        require(inspection(source)['hash'] == entry['snapshot_hash'], 'PERIODIC_SOURCE_CHANGED')

        def fresh():
            allowed(config_hash)
            current = bind(source, entry['pr_number'], STATE / 'reproductions' / (job.name + '.json'), transport)
            require(current == entry, 'PERIODIC_FAILURE_CHANGED')

        fresh()
        mapping_file = job / 'mapping.json'
        if not os.path.lexists(mapping_file):
            return receipt(job, 'AWAITING_MAPPING')
        mapping = load_json(generation.owner_file(mapping_file, 16384))
        require(type(mapping) is dict and 'profile_id' in mapping, 'PERIODIC_MAPPING')
        require(mapping == profiles.mapping_plan(entry, mapping['profile_id']), 'PERIODIC_MAPPING')
        context = once(job, 'prepare', lambda: profiles.prepare(entry, mapping['profile_id'], mapping))
        context_run = context['run_id']
        require(profiles.context(context_run, entry) == context, 'PERIODIC_CONTEXT_CHANGED')
        prompt = generation.request_prompt(entry, context)
        expected = generation.plan(entry, prompt)
        if not os.path.lexists(job / 'generation-plan.json'):
            save(job / 'generation-plan.json', expected)
        require(read(job / 'generation-plan.json') == expected, 'PERIODIC_PLAN_CHANGED')
        approval = job / 'generation-approval.json'
        if not os.path.lexists(job / 'generate.json') and not os.path.lexists(approval):
            require(not os.path.lexists(job / 'generate-started.json'), 'PERIODIC_RECOVERY_REQUIRED')
            return receipt(job, 'AWAITING_GENERATION_APPROVAL', context_run=context_run)

        def generate():
            generation.approval(approval, expected)
            fresh()
            return load_json(generation.execute(entry, prompt, approval, ROOT / 'runs/public-hermes',
                                                context_run=context_run))

        response = once(job, 'generate', generate)
        raw = canonical(response)
        work = profiles.gate.run_path(context_run)
        profiles.verify_proposal(work, profiles.manifest(work), raw)
        allowed(config_hash)
        report = once(job, 'evaluate', lambda: profiles.evaluate(context_run, raw))
        audit = profiles.audit(context_run)
        require(read(job / 'evaluate.json') == profiles.gate.read(work, 'profile-report.json'), 'PERIODIC_REPORT_CHANGED')
        semantic_needed = report['state'] == 'HOLD' and report.get('decision', {}).get('reasons') == SEMANTIC_REASON
        if not semantic_needed:
            allowed(config_hash)
            return finish(job, report['state'], context_run=context_run, report_hash=audit['report_hash'])
        allowed(config_hash)
        prepared = once(job, 'semantic-prepare', lambda: semantic.prepare(context_run, raw))
        plan = semantic.send_plan(job.name)
        require(prepared == plan, 'PERIODIC_SEMANTIC_PLAN_CHANGED')
        approval = job / 'semantic-approval.json'
        if not os.path.lexists(job / 'semantic.json') and not os.path.lexists(approval):
            require(not os.path.lexists(job / 'semantic-started.json'), 'PERIODIC_RECOVERY_REQUIRED')
            return receipt(job, 'AWAITING_SEMANTIC_APPROVAL', context_run=context_run)

        def evaluate_semantics():
            generation.approval(approval, plan['plan'])
            fresh()
            return semantic.run(job.name, approval)

        measured = once(job, 'semantic', evaluate_semantics)
        audit = semantic.audit(job.name)
        require(measured == load_json(regular(semantic.area(job.name) / 'report.json', semantic.STATE)),
                'PERIODIC_SEMANTIC_REPORT_CHANGED')
        allowed(config_hash)
        return finish(job, measured['state'], context_run=context_run, report_hash=audit['report_hash'])
    except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        reason = str(error) if isinstance(error, EvaluationError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,80}', str(error)) else 'PERIODIC_JOB_FAILED'
        return finish(job, 'STOPPED', reason=reason)


def dispatch(run, *, inspection_complete=True, transport=None):
    if not inspection_complete:
        return {'status': 'SKIP', 'reason': 'POINT_CHECK_INCOMPLETE'}
    try:
        config_hash = configuration()
        if config_hash is None:
            return {'status': 'DISABLED'}
        snapshot = inspection(run)
        prepare_state(STATE)
        for name in ('checks', 'events', 'reproductions'):
            prepare_state(STATE / name)
        with state_lock(STATE, 'dispatcher.lock'):
            allowed(config_hash)
            transport = transport or GhReadOnly()
            job = choose(Path(run), snapshot, transport)
            return advance(job, config_hash, transport) if job else {'status': 'SKIP', 'reason': 'NO_ELIGIBLE_PUBLIC_FAILURE'}
    except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        reason = str(error) if isinstance(error, EvaluationError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,80}', str(error)) else 'PERIODIC_DISPATCH_FAILED'
        return {'status': 'STOPPED', 'reason': reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--run', type=Path)
    action.add_argument('--stop', action='store_true')
    action.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.run:
        result = dispatch(args.run)
    else:
        try:
            if args.resume:
                generation.reject_profile_pending()
            result = {'status': control_intake(ROOT / 'runs/public-hermes', 'stop' if args.stop else 'resume')}
        except (EvaluationError, OSError) as error:
            result = {'status': 'STOPPED', 'reason': str(error) if isinstance(error, EvaluationError) else 'PERIODIC_CONTROL_FAILED'}
    print(canonical(result).decode())
    return 2 if result['status'] == 'STOPPED' else 0


if __name__ == '__main__':
    sys.exit(main())
