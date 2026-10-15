#!/usr/bin/env python3
"""Read one explicit repository fixture, emit a deterministic JSON report to stdout."""
import argparse
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit.core import AuditError, audit, canonical, decode


def read_fixture(relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or path.parts[:2] != ('fixtures', 'audit'):
        raise AuditError('INPUT_PATH')
    for parent in path.parents:
        if (ROOT / parent).is_symlink():
            raise AuditError('INPUT_SYMLINK')
    fd = os.open(ROOT / path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144:
            raise AuditError('INPUT_FILE')
        data = os.read(fd, 262145)
        if len(data) > 262144:
            raise AuditError('INPUT_FILE')
        return data
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='explicit fixtures/audit/ relative JSON file')
    args = parser.parse_args()
    try:
        report = audit(decode(read_fixture(args.input)))
    except AuditError as error:
        print(canonical({'status': 'ERROR', 'reason': str(error)}).decode(), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, RecursionError):
        print('{"status":"ERROR","reason":"INPUT_INVALID"}', file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(report) + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
