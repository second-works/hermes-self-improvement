#!/usr/bin/env python3
"""Weekly work-day coverage and burden report for the skill improvement MVP (#108).

Reads the approved manifest, the local ledger and, for repositories that register a local checkout,
local commit dates on the allowed branches. No fetch, API call or model call is made. When none of
the inputs changed since the last run, the cached report is returned without re-reading commits.
Output is one JSON object on stdout; a refusal prints {"error": CODE} on stderr and exits 2.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from skill_improvement.cli import QuietParser  # noqa: E402
from skill_improvement.ledger import Ledger, LedgerError, Manifest, load_contract, utc_now  # noqa: E402
from skill_improvement.metrics import build_report  # noqa: E402


def main(argv=None):
    parser = QuietParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='approved repository manifest (JSON)')
    parser.add_argument('--ledger', required=True, help='approved ledger directory')
    parser.add_argument('--start', help='YYYY-MM-DD (default: manifest period start)')
    parser.add_argument('--end', help='YYYY-MM-DD (default: manifest period end)')
    args = parser.parse_args(argv)
    try:
        contract = load_contract()
        manifest = Manifest.load(args.manifest, contract, utc_now())
        report = build_report(manifest, manifest.raw, Ledger(args.ledger, manifest, contract), args.start, args.end)
    except LedgerError as error:
        print(json.dumps({'error': error.code, 'detail': error.detail}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
