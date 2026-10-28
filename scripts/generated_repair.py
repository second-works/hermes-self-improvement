#!/usr/bin/env python3
"""Separate generated-repair CLI; never invokes a model or pulls an image."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from delegation.generated import Controller
from evaluation.core import EvaluationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'freeze', 'evaluate', 'audit'])
    parser.add_argument('--run')
    parser.add_argument('--candidate-sha')
    args = parser.parse_args()
    try:
        c = Controller(ROOT)
        if args.operation == 'prepare':
            value = {'run_id': c.prepare(), 'status': 'ISOLATION_VERIFIED'}
        elif args.operation == 'freeze':
            value = c.freeze(args.run)
        elif args.operation == 'evaluate':
            value = c.evaluate(args.run, args.candidate_sha)
        else:
            value = c.audit(args.run)
        print(json.dumps(value))
    except (EvaluationError, OSError, ValueError) as error:
        print(json.dumps({'status': 'STOPPED', 'reason': str(error) if isinstance(error, EvaluationError) else type(error).__name__}))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
