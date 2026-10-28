#!/usr/bin/env python3
"""Supervisor-only fixture commands. Requests are drafts until explicit approval."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from adoption.core import Controller, EvaluationError, canonical, digest, load_json, regular
from adoption.regression import DockerRegression


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--area', required=True, help='new controller directory under repo/runs')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare')
    commands.add_parser('submission', help='print PUBLIC packet; no GitHub write')
    register = commands.add_parser('register')
    register.add_argument('--environment', required=True)
    register.add_argument('--target', required=True)
    register.add_argument('--root', required=True)
    request = commands.add_parser('request')
    request.add_argument('--target', required=True)
    request.add_argument('--operation', choices=['ADOPT','ROLLBACK'], required=True)
    request.add_argument('--actor', required=True)
    request.add_argument('--expires-at', required=True)
    approve = commands.add_parser('approve')
    approve.add_argument('--request', required=True)
    approve.add_argument('--confirm-request-hash', required=True)
    execute = commands.add_parser('execute')
    execute.add_argument('--approval-hash', required=True)
    status = commands.add_parser('status')
    status.add_argument('--target', required=True)
    observe = commands.add_parser('observe')
    observe.add_argument('--target', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    c = Controller(repo, Path(args.area))
    if args.command == 'prepare':
        result = c.initialize()
    elif args.command == 'submission':
        result = c.packet()
    elif args.command == 'register':
        result = c.register(args.environment, args.target, Path(args.root))
    elif args.command == 'request':
        draft = c.request(args.target, args.operation, args.expires_at, args.actor)
        result = {'request':draft, 'request_hash':digest(canonical(draft)), 'approval':'NOT_GRANTED'}
    elif args.command == 'approve':
        # Only supervisor-controlled request files in this area are accepted.
        file = Path(args.request).absolute()
        if not file.is_relative_to(c.area):
            raise EvaluationError('REQUEST_BOUNDARY')
        result = {'approval_hash':c.approve(load_json(regular(file, c.area)), confirmation=args.confirm_request_hash)}
    elif args.command == 'execute':
        result = c.execute(args.approval_hash, DockerRegression(c))
    elif args.command == 'observe':
        result = {'state':c.observe(args.target, DockerRegression(c))}
    else:
        with c.guard():
            state = c.state(args.target)
            events = c.events(args.target)
            if state == 'RECOVERY_REQUIRED' and events and events[-1]['state'] in ('ADOPTING','ROLLING_BACK'):
                c.event(args.target, state, {'reason':'INCOMPLETE_INTENT_AFTER_RESTART'})
            result = {'state':state, 'binding':c.binding(args.target), 'events':c.events(args.target)}
    print(canonical(result).decode())


if __name__ == '__main__':
    try:
        main()
    except (EvaluationError, OSError, KeyError, TypeError, ValueError) as error:
        code = str(error) if isinstance(error, EvaluationError) else 'INVALID_OR_UNAVAILABLE'
        print(canonical({'status':'STOPPED', 'reason':code}).decode(), file=sys.stderr)
        sys.exit(2)
