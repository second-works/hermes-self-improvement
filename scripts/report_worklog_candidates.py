#!/usr/bin/env python3
"""Manual, network-free CLI restricted to this repository's synthetic fixtures."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worklog_candidates.core import ContractError, canonical, decode, load_snapshot, read_relative
from worklog_candidates.evaluation import evaluate
from worklog_candidates.report import make_report, markdown, packets, write_output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='manifest.json', help='Relative to fixtures/worklog_candidates')
    parser.add_argument('--responses', help='Pre-recorded synthetic selection JSON, relative to the same fixture root')
    parser.add_argument('--format', choices=('json', 'markdown'), default='json')
    parser.add_argument('--evaluate', action='store_true', help='Score after classification using separate synthetic gold.json')
    parser.add_argument('--packets', action='store_true', help='Emit all bounded selection packets, without labels')
    parser.add_argument('--output', help='New directory; parent must already exist; never overwrite')
    args = parser.parse_args(argv)
    try:
        fixture_root = ROOT / 'fixtures/worklog_candidates'
        snapshot = load_snapshot(fixture_root, args.manifest)
        if args.packets:
            if args.responses or args.output or args.evaluate or args.format != 'json':
                raise ContractError('ARGUMENT_CONFLICT')
            sys.stdout.buffer.write(canonical(packets(snapshot)) + b'\n')
            return 0
        raw = None
        if args.responses:
            if not args.responses.startswith('responses/') or not args.responses.endswith('.json'):
                raise ContractError('RESPONSE_PATH')
            raw = read_relative(fixture_root, args.responses)
        report = make_report(snapshot, raw)
        if args.evaluate:
            report['evaluation'] = evaluate(report, decode(read_relative(fixture_root, 'gold.json')), snapshot['sources'])
        if args.output:
            write_output(args.output, report)
        data = canonical(report) + b'\n' if args.format == 'json' else markdown(report).encode('utf-8')
        sys.stdout.buffer.write(data)
        return 0 if report['status'] == 'COMPLETE' else 2
    except ContractError as exc:
        print('worklog: ' + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print('worklog: FILESYSTEM_ERROR (input/output may be incomplete)', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
