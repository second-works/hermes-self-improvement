#!/usr/bin/env python3
"""Inspect the fixed catalog or apply a supplied AI selection; no model connection."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.catalog import catalog
from delegation.registered import run
from evaluation.core import EvaluationError, canonical, require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true',
                        help='Run the fixed public checks and jobs in an existing isolated Docker environment.')
    args = parser.parse_args(argv)
    try:
        if args.catalog:
            require(not any((args.source, args.selection, args.output, args.execute)), 'ARGUMENTS')
            result = catalog()
        else:
            require(all((args.source, args.selection, args.output)), 'ARGUMENTS')
            result = run(ROOT, args.source.absolute(), args.selection.absolute(),
                         args.output.absolute(), execute=args.execute)
        print(canonical(result).decode())
        return 0
    except (EvaluationError, OSError) as error:
        print(canonical({'status': 'FAILED', 'reason': str(error) if isinstance(error, EvaluationError)
                         else 'FILESYSTEM_ERROR'}).decode())
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
