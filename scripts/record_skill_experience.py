#!/usr/bin/env python3
"""Record skill-improvement session ends, experiences and candidates in a local JSONL ledger.

No model, HTTP or other repository is used. Evidence references are stored as text only.
Output is one JSON object on stdout; a refusal prints {"error": CODE} on stderr and exits 2.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from skill_improvement.cli import QuietParser  # noqa: E402
from skill_improvement.ledger import (CAUSES, EFFORT_ACTIVITIES, EXPERIENCE_TYPES, Ledger, LedgerError, Manifest,  # noqa: E402
                                      load_contract, summary, utc_now)


def experience(text):
    try:
        value = json.loads(text)
    except ValueError:
        raise argparse.ArgumentTypeError('experience must be a JSON object') from None
    if type(value) is not dict:
        raise argparse.ArgumentTypeError('experience must be a JSON object')
    return value


def parser():
    root = QuietParser(description=__doc__)
    root.add_argument('--manifest', required=True, help='approved repository manifest (JSON)')
    root.add_argument('--ledger', required=True, help='approved ledger directory (absolute, named by the manifest)')
    commands = root.add_subparsers(dest='command', required=True)

    end = commands.add_parser('end', help='record one session end')
    end.add_argument('--repository', required=True)
    end.add_argument('--work-unit', required=True, help='ID of the work unit; one end record per unit')
    end.add_argument('--result', required=True, choices=['CANDIDATE_FOUND', 'NO_CANDIDATE', 'UNDETERMINED'])
    end.add_argument('--work-date', help='YYYY-MM-DD in the manifest timezone (default: today)')
    end.add_argument('--reason', help='required for UNDETERMINED')
    end.add_argument('--experience', action='append', type=experience, default=[],
                     help='JSON: {"type": %s, "summary": "...", "refs": ["input:..."], "cause": optional}'
                          % '|'.join(EXPERIENCE_TYPES))
    end.add_argument('--classification', choices=['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'UNKNOWN'])

    propose = commands.add_parser('propose', help='make a candidate from recorded experiences')
    propose.add_argument('--repository', required=True)
    propose.add_argument('--work-unit', required=True)
    propose.add_argument('--experience-id', action='append', required=True)
    propose.add_argument('--target-skill', required=True)
    propose.add_argument('--cause', required=True, choices=CAUSES)
    propose.add_argument('--duplicate-of')
    propose.add_argument('--shared-repositories', nargs='+', metavar='REPOSITORY',
                         help='SHARED scope based on repetition in these repositories')
    propose.add_argument('--shared-contract', help='SHARED scope based on a missing common contract (reference)')
    propose.add_argument('--decided-by', help='person who decided the SHARED scope')
    propose.add_argument('--work-date')
    propose.add_argument('--classification', choices=['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'UNKNOWN'])

    state = commands.add_parser('set-state', help='change a candidate state (OPEN/HOLD/DECLINED/DUPLICATE)')
    state.add_argument('--candidate', required=True)
    state.add_argument('--status', required=True)
    state.add_argument('--reason')
    state.add_argument('--duplicate-of')
    state.add_argument('--work-date')

    day = commands.add_parser('work-day', help='register a work day without commits (coverage denominator)')
    day.add_argument('--repository', required=True)
    day.add_argument('--work-unit', required=True)
    day.add_argument('--summary', required=True, help='one line, 120 characters or fewer')
    day.add_argument('--work-date')
    day.add_argument('--classification', choices=['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'UNKNOWN'])

    effort = commands.add_parser('effort', help='record minutes spent on one activity')
    effort.add_argument('--repository', required=True)
    effort.add_argument('--work-unit', required=True)
    effort.add_argument('--activity', required=True, choices=EFFORT_ACTIVITIES)
    effort.add_argument('--minutes', required=True, type=int)
    effort.add_argument('--subject', required=True,
                        help='end event_id (RECORD), candidate_id, evaluation_id or deployment_id')
    effort.add_argument('--work-date')
    effort.add_argument('--classification', choices=['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'UNKNOWN'])

    commands.add_parser('verify', help='re-read the whole ledger and print counts')
    return root


def scope_of(args):
    if args.shared_repositories and args.shared_contract:
        raise LedgerError('SCOPE_INVALID', 'choose one SHARED basis')
    if not (args.shared_repositories or args.shared_contract):
        if args.decided_by:
            raise LedgerError('SCOPE_INVALID', '--decided-by needs a SHARED basis')
        return None
    if not args.decided_by:
        raise LedgerError('SCOPE_INVALID', 'SHARED needs --decided-by')
    if args.shared_repositories:
        return {'type': 'SHARED', 'basis': 'REPEATED_IN_REPOSITORIES',
                'repository_ids': args.shared_repositories, 'decided_by': args.decided_by}
    return {'type': 'SHARED', 'basis': 'MISSING_COMMON_CONTRACT', 'contract_ref': args.shared_contract,
            'decided_by': args.decided_by}


def run(args):
    contract = load_contract()
    manifest = Manifest.load(args.manifest, contract, utc_now())
    ledger = Ledger(args.ledger, manifest, contract)
    if args.command == 'end':
        return ledger.record_end(args.repository, args.work_unit, args.result, args.work_date, args.reason,
                                 args.experience, args.classification)
    if args.command == 'propose':
        return ledger.propose(args.repository, args.work_unit, args.experience_id, args.target_skill, args.cause,
                              scope_of(args), args.duplicate_of, args.work_date, args.classification)
    if args.command == 'set-state':
        return ledger.set_state(args.candidate, args.status, args.reason, args.duplicate_of, args.work_date)
    if args.command == 'work-day':
        return ledger.record_work_day(args.repository, args.work_unit, args.summary, args.work_date,
                                      args.classification)
    if args.command == 'effort':
        return ledger.record_effort(args.repository, args.work_unit, args.activity, args.minutes, args.subject,
                                    args.work_date, args.classification)
    return dict(summary(ledger.read()), status='VERIFIED')


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except LedgerError as error:
        print(json.dumps({'error': error.code, 'detail': error.detail}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
