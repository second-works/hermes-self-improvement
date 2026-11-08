#!/usr/bin/env python3
"""Foreground PUBLIC collection timing only; no scheduler or improvement handoff."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from github_work_guide.collector import Collector, GhReadOnly, PREFIX
from github_work_guide.core import Invalid, require, save_run


class ProfiledReadOnly(GhReadOnly):
    def __init__(self):
        self.operations = {}

    def measure(self, kind, function, *args):
        started, success = time.monotonic(), False
        try:
            result = function(*args)
            success = True
            return result
        finally:
            entry = self.operations.setdefault(kind, {'requests': 0, 'seconds': 0.0, 'failures': 0})
            entry['requests'] += 1
            entry['seconds'] += time.monotonic() - started
            entry['failures'] += not success

    def get(self, path, page, timeout):
        suffix = path[len(PREFIX):]
        if not suffix:
            kind = 'metadata'
        elif suffix == '/issues':
            kind = 'inventory'
        elif suffix.endswith('/comments'):
            kind = 'review_comments' if suffix.startswith('/pulls/') else 'comments'
        elif suffix.endswith('/check-runs'):
            kind = 'checks'
        elif suffix.endswith('/statuses'):
            kind = 'statuses'
        elif suffix.endswith('/reviews'):
            kind = 'reviews'
        else:
            kind = 'pr_detail' if suffix.startswith('/pulls/') else 'issue_detail'
        return self.measure(kind, super().get, path, page, timeout)

    def connection(self, kind, n, cursor, timeout):
        return self.measure(kind, super().connection, kind, n, cursor, timeout)

    def closing_batch(self, requests, timeout):
        return self.measure('closing_batch', super().closing_batch, requests, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new repository runs/<name>')
    args = parser.parse_args(argv)
    try:
        output = args.out.absolute()
        require(output.parent == ROOT / 'runs' and not output.exists(), 'new repository run required')
        require(not any(p.is_symlink() for p in (output, *output.parents)), 'symlink output')
        transport = ProfiledReadOnly()
        started = time.monotonic()
        snapshot = Collector(transport).collect()
        metrics = {'status': snapshot['coverage']['status'], 'items': len(snapshot['items']),
                   'logical_reads': snapshot['coverage']['calls'],
                   'http_requests': sum(x['requests'] for x in transport.operations.values()),
                   'elapsed_seconds': round(time.monotonic() - started, 3),
                   'operations': transport.operations}
        for entry in metrics['operations'].values():
            entry['seconds'] = round(entry['seconds'], 4)
        # Preserve the snapshot and timing together under the existing manifest contract.
        report = json.dumps(metrics, ensure_ascii=False, indent=2) + '\n'
        save_run(output, {'snapshot.json': snapshot, 'report.md': report})
        print(report, end='')
        return 0 if metrics['status'] == 'COMPLETE' else 2
    except (Invalid, OSError, KeyError, TypeError, ValueError, AttributeError):
        print('BLOCKED: 取得/計測/保存を確認できません。', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
