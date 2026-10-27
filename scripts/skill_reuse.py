#!/usr/bin/env python3
"""Trusted handoff CLI; never evaluates model-provided commands or code."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from delegation.skill_reuse import Controller
from evaluation.core import EvaluationError, load_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'freeze', 'accept', 'read', 'use', 'evaluate', 'audit'])
    parser.add_argument('--run')
    parser.add_argument('--candidate-sha')
    parser.add_argument('--trial', type=int)
    parser.add_argument('--scenario')
    parser.add_argument('--request')
    args = parser.parse_args()
    c = Controller(Path(__file__).resolve().parents[1])
    try:
        if args.action == 'prepare': result = c.prepare()
        elif args.action == 'freeze': result = c.freeze(args.run)
        elif args.action == 'accept': result = c.accept(args.run, args.candidate_sha)
        elif args.action == 'read': result = c.handoff(args.run, args.trial, args.scenario)
        elif args.action == 'use': result = c.use(args.run, args.trial, args.scenario, load_json(args.request))
        elif args.action == 'evaluate': result = c.evaluate(args.run)
        else: result = c.audit(args.run)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (EvaluationError, OSError, ValueError) as error:
        print(json.dumps({'status': 'STOPPED', 'reason': str(error) if isinstance(error, EvaluationError) else type(error).__name__}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
