#!/usr/bin/env bash
set -Eeuo pipefail
file_list="$(mktemp)"
trap 'rm -f "$file_list"' EXIT
git ls-files -z '*.sh' > "$file_list"
while IFS= read -r -d '' path; do
  bash -n "$path"
done < "$file_list"
python3 - <<'CHECK'
import ast
from pathlib import Path
for root in ('scripts', 'tests'):
    for path in Path(root).rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
CHECK
git diff --check
git diff --cached --check
