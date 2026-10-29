#!/usr/bin/env python3
"""Explicit steps only; no automatic generation, GitHub writes, or human approval."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from manual_cycle.core import Cycle
from evaluation.core import EvaluationError, canonical, load_json, regular


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    sub = parser.add_subparsers(dest='operation', required=True)
    init = sub.add_parser('initialize'); init.add_argument('--expires-at', required=True)
    for label in ('start','status','handoff','evaluate','reobserve','submission'):
        sub.add_parser(label)
    diagnosis = sub.add_parser('diagnose'); diagnosis.add_argument('--proposal', required=True)
    check = sub.add_parser('public-check'); check.add_argument('--candidate-sha', required=True)
    trial = sub.add_parser('prepare-trial'); trial.add_argument('--kind', choices=['degradation','crash'], required=True)
    plan = sub.add_parser('fault-plan'); plan.add_argument('--request', required=True)
    submit = sub.add_parser('submit')
    for field in ('url','head-sha','packet-hash'):
        submit.add_argument('--' + field, required=True)
    request = sub.add_parser('request')
    request.add_argument('--action', choices=['ADOPT','ROLLBACK'], required=True)
    request.add_argument('--expires-at', required=True); request.add_argument('--actor', required=True)
    execute = sub.add_parser('execute')
    execute.add_argument('--request', required=True); execute.add_argument('--confirm-request-hash', required=True)
    execute.add_argument('--confirm-fault-hash')
    args = parser.parse_args()
    c = None
    try:
        c = Cycle(ROOT, args.run)
        match args.operation:
            case 'initialize': value = c.initialize(args.expires_at)
            case 'start': value = c.start()
            case 'status': value = c.status()
            case 'diagnose': value = c.diagnose(load_json(regular(Path(args.proposal), c.area)))
            case 'handoff': value = c.handoff()
            case 'public-check': value = c.public_check(args.candidate_sha)
            case 'evaluate': value = c.evaluate()
            case 'submission': value = c.adoption().packet()
            case 'submit': value = c.submit(args.url, args.head_sha, args.packet_hash)
            case 'request': value = c.request(args.action, args.expires_at, args.actor)
            case 'prepare-trial': value = c.prepare_trial(args.kind)
            case 'fault-plan': value = c.fault_plan(load_json(regular(Path(args.request), c.area)))
            case 'execute': value = c.execute(load_json(regular(Path(args.request), c.area)), args.confirm_request_hash, args.confirm_fault_hash)
            case 'reobserve': value = c.reobserve()
            case _: raise EvaluationError('OPERATION')
        print(canonical(value if value is not None else c.status()).decode())
        return 0
    except (EvaluationError, OSError, ValueError, KeyError, TypeError):
        # No raw payloads, hidden trace, host paths or credentials in errors.
        try:
            state = c.status()['state'] if c is not None else 'UNKNOWN'
        except (EvaluationError, OSError, ValueError, KeyError, TypeError):
            state = 'UNKNOWN'
        print(canonical({'run_id': args.run, 'status': 'ERROR', 'state': state,
                         'reason': 'CYCLE_OPERATION_FAILED'}).decode())
        return 2


if __name__ == '__main__':
    sys.exit(main())
