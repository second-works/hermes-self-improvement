#!/usr/bin/env bash

if (( BASH_VERSINFO[0] < 5 )); then
  printf '%s\n' 'SECURITY_STATUS=SECURITY_UNAVAILABLE' \
    "SECURITY_REASON=Bash 5 or newer required (current ${BASH_VERSION})"
  exit 4
fi

set -Eeuo pipefail

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [repository-root]" >&2
  exit 2
fi

repo_root="$(cd "${1:-.}" && pwd)"

command -v git >/dev/null 2>&1 || {
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=git is not installed'
  exit 4
}

git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=repository root is not a git worktree'
  exit 4
}

tracked_files=''
if ! tracked_files="$(mktemp "${TMPDIR:-/tmp}/security-preflight-files.XXXXXX")"; then
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=could not allocate a tracked-file list'
  exit 4
fi
scan_root=''
cleanup() {
  rm -f "$tracked_files"
  if [[ -n "$scan_root" ]]; then
    rm -rf -- "$scan_root"
  fi
}
trap cleanup EXIT
if ! git -C "$repo_root" ls-files -z >"$tracked_files"; then
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=git ls-files failed; tracked files were not fully inspected'
  exit 4
fi

# Inspect the version that would be committed, including dependency manifests.
# Materialize raw blobs only; never invoke checkout transformations or filters.
if ! scan_root="$(mktemp -d "${TMPDIR:-/tmp}/security-preflight-index.XXXXXX")"; then
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=could not allocate an index snapshot'
  exit 4
fi
if ! python3 - "$repo_root" "$scan_root" <<'PY'
import os
from pathlib import Path
import subprocess
import sys

repo = sys.argv[1]
destination = Path(sys.argv[2]).resolve()
try:
    entries = subprocess.check_output(['git', '-C', repo, 'ls-files', '--stage', '-z'])
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, object_id, stage = metadata.split()
        if stage != b'0' or mode not in (b'100644', b'100755', b'120000'):
            raise ValueError('unsupported index entry')
        relative = Path(os.fsdecode(name))
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('invalid index path')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if destination not in (target.parent.resolve(), *target.parent.resolve().parents):
            raise ValueError('index path escapes snapshot')
        content = subprocess.check_output(['git', '-C', repo, 'cat-file', 'blob', object_id.decode('ascii')])
        if mode == b'120000':
            os.symlink(os.fsdecode(content), target)
        else:
            with target.open('xb') as handle:
                handle.write(content)
except (OSError, ValueError, subprocess.SubprocessError):
    raise SystemExit(1)
PY
then
  echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
  echo 'SECURITY_REASON=index snapshot failed; staged files were not fully inspected'
  exit 4
fi

secret_pattern='ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'

escape_path() {
  local value="$1"
  value="${value//$'\r'/%0D}"
  value="${value//$'\n'/%0A}"
  printf '%s' "$value"
}

scan_file() {
  local file="$1"
  if [[ -L "$file" ]]; then
    local link_target
    if ! link_target="$(readlink "$file")"; then
      return 2
    fi
    if printf '%s' "$link_target" | grep -Eiq -- "$secret_pattern"; then
      return 0
    else
      local grep_status=$?
      [[ "$grep_status" -eq 1 ]] && return 1
      return 2
    fi
  fi
  [[ -f "$file" ]] || return 2
  if grep -Eiq -- "$secret_pattern" "$file"; then
    return 0
  else
    local grep_status=$?
    [[ "$grep_status" -eq 1 ]] && return 1
    return 2
  fi
}

# Reject secret-bearing names before any diagnostic can display file paths.
while IFS= read -r -d '' path; do
  if printf '%s' "$path" | grep -Eiq -- "$secret_pattern"; then
    printf '%s\n' 'SECURITY_STATUS=SECURITY_FAILED' \
      'SECURITY_REASON=secret-like value detected in a staged pathname (value omitted)' \
      'SECRET_STATUS=SECURITY_FAILED' 'DEPENDENCY_STATUS=SECURITY_UNAVAILABLE' 'DEPENDENCY_MANIFEST='
    exit 1
  else
    path_status=$?
    if [[ "$path_status" -ne 1 ]]; then
      echo 'SECURITY_STATUS=SECURITY_UNAVAILABLE'
      echo 'SECURITY_REASON=pathname scanner failed'
      exit 4
    fi
  fi
done < "$tracked_files"

secret_status='SECURITY_PASSED'
secret_reason='staged files and symlink targets contained no known secret patterns'
while IFS= read -r -d '' path; do
  if scan_file "$scan_root/$path"; then
    secret_status='SECURITY_FAILED'
    secret_reason="secret-like value detected in $(escape_path "$path")"
    break
  else
    scan_status=$?
    if [[ "$scan_status" -ne 1 ]]; then
      printf 'SECURITY_STATUS=SECURITY_UNAVAILABLE\n'
      printf 'SECURITY_REASON=secret scanner failed for %s\n' "$(escape_path "$path")"
      exit 4
    fi
  fi
done < "$tracked_files"

manifest_paths=()
while IFS= read -r -d '' path; do
  manifest_name="${path##*/}"
  case "$manifest_name" in
    package.json|package-lock.json|npm-shrinkwrap.json|pnpm-lock.yaml|yarn.lock|requirements.txt|requirements-*.txt|pyproject.toml|poetry.lock|Pipfile.lock|uv.lock)
      manifest_paths+=("$path")
      ;;
  esac
done < "$tracked_files"

dependency_status='SECURITY_NOT_APPLICABLE'
dependency_reason='no supported dependency manifest is present'
dependency_manifest=''
dependency_manifests=()
dependency_reasons=()
dependency_failed=0
dependency_unavailable=0

for path in "${manifest_paths[@]}"; do
  manifest_name="${path##*/}"
  if [[ -L "$scan_root/$path" ]]; then
    dependency_unavailable=1
    dependency_reasons+=("dependency manifest is a symlink: $(escape_path "$path")")
    continue
  fi
  case "$manifest_name" in
    package-lock.json|npm-shrinkwrap.json)
      dependency_manifests+=("$path")
      ;;
    pnpm-lock.yaml|yarn.lock|requirements.txt|requirements-*.txt|pyproject.toml|poetry.lock|Pipfile.lock|uv.lock)
      dependency_unavailable=1
      dependency_reasons+=("no supported dependency scanner is defined for $(escape_path "$path")")
      ;;
    package.json)
      if [[ "$path" == */* ]]; then
        package_dir="${path%/*}"
      else
        package_dir='.'
      fi
      matching_lock=0
      for lock_path in "${manifest_paths[@]}"; do
        if [[ "$package_dir" == '.' ]]; then
          if [[ "$lock_path" == 'package-lock.json' || "$lock_path" == 'npm-shrinkwrap.json' ]]; then
            matching_lock=1
            break
          fi
        elif [[ "$lock_path" == "$package_dir/package-lock.json" || "$lock_path" == "$package_dir/npm-shrinkwrap.json" ]]; then
          matching_lock=1
          break
        fi
      done
      if ((matching_lock == 0)); then
        dependency_unavailable=1
        dependency_reasons+=("package.json is present but no supported npm lockfile is available for $(escape_path "$path")")
      fi
      ;;
  esac
done

if ((${#manifest_paths[@]} > 0)); then
  dependency_display_manifests=()
  for path in "${manifest_paths[@]}"; do
    dependency_display_manifests+=("$(escape_path "$path")")
  done
  dependency_manifest="$(IFS=,; printf '%s' "${dependency_display_manifests[*]}")"

  for path in "${dependency_manifests[@]}"; do
    if [[ "$path" == */* ]]; then
      audit_dir="$scan_root/${path%/*}"
    else
      audit_dir="$scan_root"
    fi

    audit_output="$(mktemp "${TMPDIR:-/tmp}/security-preflight-audit.XXXXXX")"
    if ! command -v npm >/dev/null 2>&1; then
      dependency_unavailable=1
      dependency_reasons+=("npm is unavailable for $(escape_path "$path")")
    elif (cd "$audit_dir" && npm audit --json --audit-level=high --package-lock-only >"$audit_output" 2>&1); then
      dependency_reasons+=("npm audit reported no high or critical vulnerabilities for $(escape_path "$path")")
  else
      if python3 - "$audit_output" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, json.JSONDecodeError):
    raise SystemExit(2)

vulnerabilities = payload.get("metadata", {}).get("vulnerabilities", {})
if "auditReportVersion" not in payload or not isinstance(vulnerabilities, dict):
    raise SystemExit(2)
high = int(vulnerabilities.get("high", 0) or 0)
critical = int(vulnerabilities.get("critical", 0) or 0)
raise SystemExit(0 if high or critical else 1)
PY
      then
        dependency_failed=1
        dependency_reasons+=("npm audit reported high or critical vulnerabilities for $(escape_path "$path")")
      else
        audit_parse_status=$?
        if [[ "$audit_parse_status" -eq 1 ]]; then
          dependency_reasons+=("npm audit reported no high or critical vulnerabilities for $(escape_path "$path")")
        else
          dependency_unavailable=1
          dependency_reasons+=("npm audit could not produce a machine-readable result for $(escape_path "$path")")
        fi
      fi
    fi
    rm -f "$audit_output"
  done

  if ((dependency_failed)); then
    dependency_status='SECURITY_FAILED'
  elif ((dependency_unavailable)); then
    dependency_status='SECURITY_UNAVAILABLE'
  else
    dependency_status='SECURITY_PASSED'
  fi
  dependency_reason="${dependency_reasons[*]}"
fi

overall_status='SECURITY_PASSED'
overall_reason="$secret_reason; dependency check: $dependency_reason"
if [[ "$secret_status" == 'SECURITY_FAILED' || "$dependency_status" == 'SECURITY_FAILED' ]]; then
  overall_status='SECURITY_FAILED'
elif [[ "$dependency_status" == 'SECURITY_UNAVAILABLE' ]]; then
  overall_status='SECURITY_UNAVAILABLE'
fi

printf 'SECURITY_STATUS=%s\n' "$overall_status"
printf 'SECURITY_REASON=%s\n' "$overall_reason"
printf 'SECRET_STATUS=%s\n' "$secret_status"
printf 'DEPENDENCY_STATUS=%s\n' "$dependency_status"
printf 'DEPENDENCY_MANIFEST=%s\n' "$dependency_manifest"

case "$overall_status" in
  SECURITY_FAILED)
    exit 1
    ;;
  SECURITY_UNAVAILABLE)
    exit 4
    ;;
  SECURITY_PASSED|SECURITY_NOT_APPLICABLE)
    exit 0
    ;;
esac
