#!/usr/bin/env python3
"""Apply a supplied selection, or explicitly opt in to the bounded OpenAI provider."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.catalog import catalog
from delegation.registered import run
from delegation.openai_run import run_openai
from evaluation.core import EvaluationError, canonical, require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--openai-config', type=Path,
                        help='Explicit model, prices, and limits; no defaults or API key in this file.')
    parser.add_argument('--allow-api', action='store_true',
                        help='Explicit opt-in to one paid OpenAI selection; requires separate live-run approval.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true',
                        help='Run the fixed public checks and jobs in an existing isolated Docker environment.')
    args = parser.parse_args(argv)
    try:
        if args.catalog:
            require(not any((args.source, args.selection, args.output, args.execute,
                             args.openai_config, args.allow_api)), 'ARGUMENTS')
            result = catalog()
        else:
            require(args.source and args.output and bool(args.selection) != bool(args.openai_config),
                    'ARGUMENTS')
            if args.openai_config:
                result = run_openai(ROOT, args.source.absolute(), args.openai_config.absolute(),
                                    args.output.absolute(), allow_api=args.allow_api,
                                    execute=args.execute)
            else:
                require(not args.allow_api, 'ARGUMENTS')
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
