#!/usr/bin/env python3
"""Exercise public execution admission with a fixed offline worker."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_mock_improvement import (ROOT, EvaluationError, canonical, control_intake,
                                  execute_trial, fields, hex_id, load_json, prepare_state,
                                  reject_stopped, require, response_result)
from github_work_guide.collector import GhReadOnly
from github_work_guide.core import Invalid
from select_public_failure import select

OUTCOMES = ('HOLD', 'AUTH_FAILED', 'QUOTA_EXHAUSTED', 'COST_UNVERIFIED', 'TIMEOUT')


def rehearse(run, evidence_dir, state_dir, transport, outcome='HOLD'):
    require(outcome in OUTCOMES, 'INVALID_REHEARSAL_OUTCOME')
    prepare_state(state_dir)
    reject_stopped(state_dir / 'intake-stop.json')
    seen = {path.name for path in state_dir.iterdir() if hex_id(path.name, 64)}
    result = select(run, evidence_dir, seen, transport)
    if result['status'] == 'SKIP':
        return result
    entry = result['candidate']
    refs = {'/reproduction_sha256'}

    def response():
        if outcome in ('AUTH_FAILED', 'QUOTA_EXHAUSTED', 'COST_UNVERIFIED'):
            raise EvaluationError(outcome)
        return canonical({'schema_version': 1, 'decision': 'HOLD',
                          'reason': 'Offline rehearsal', 'evidence_refs': sorted(refs)})

    def receipt(identity, data):
        decision = response_result(load_json(data), refs)
        fields(decision, 'decision reason evidence_refs', 'REHEARSAL_SCHEMA')
        require(decision['decision'] == 'HOLD', 'REHEARSAL_DECISION')
        return {'schema_version': 1, **identity, 'classification': 'PUBLIC',
                'mode': 'offline-rehearsal', 'decision': 'HOLD'}

    encoded = execute_trial(entry, response, state_dir, receipt, isolated=True,
                            stall=outcome == 'TIMEOUT', one_per_snapshot=True)
    return load_json(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--simulate', choices=OUTCOMES)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--stop', action='store_const', const='stop', dest='action')
    actions.add_argument('--resume', action='store_const', const='resume', dest='action')
    args = parser.parse_args()
    if args.action and (args.run or args.evidence_dir or args.simulate):
        parser.error('control actions take no rehearsal arguments')
    if not args.action and not (args.run and args.evidence_dir):
        parser.error('--run and --evidence-dir are required for a rehearsal')
    state = ROOT / 'runs' / 'public-execution-rehearsal'
    try:
        result = ({'status': control_intake(state, args.action)} if args.action else
                  rehearse(args.run, args.evidence_dir, state, GhReadOnly(), args.simulate or 'HOLD'))
    except EvaluationError as error:
        print(canonical({'status': 'STOPPED', 'reason': str(error)}).decode(), file=sys.stderr)
        return 2
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Public execution rehearsal verification failed.', file=sys.stderr)
        return 2
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    sys.exit(main())
