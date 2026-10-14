#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'CHECK'
import ast
from pathlib import PurePosixPath
import subprocess

entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'])
for entry in entries.split(b'\0'):
    if not entry:
        continue
    metadata, name = entry.split(b'\t', 1)
    mode, object_id, stage = metadata.split()
    if stage != b'0':
        raise SystemExit('lint cannot inspect an unmerged index')
    if mode not in (b'100644', b'100755'):
        continue
    path = PurePosixPath(name.decode('utf-8', errors='surrogateescape'))
    if path.suffix not in ('.sh', '.py'):
        continue
    source = subprocess.check_output(['git', 'cat-file', 'blob', object_id.decode('ascii')])
    if path.suffix == '.sh':
        subprocess.run(['bash', '-n'], input=source, check=True)
    else:
        ast.parse(source, filename=str(path))
CHECK
git diff --check
git diff --cached --check
