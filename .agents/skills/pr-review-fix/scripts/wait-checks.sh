#!/usr/bin/env bash

if (( BASH_VERSINFO[0] < 5 )); then
  printf 'ERROR: Bash 5 or newer required (current %s)\n' "$BASH_VERSION" >&2
  exit 4
fi

set -Eeuo pipefail

if [[ $# -lt 2 || $# -gt 6 ]]; then
  echo "Usage: $0 <repo-identity> <expected-sha> [timeout-seconds] [no-checks-grace-seconds] [stability-seconds] [security-preflight-script]" >&2
  exit 2
fi

REPO_IDENTITY="$1"
EXPECTED_SHA="$2"
TIMEOUT="${3:-300}"
NO_CHECKS_GRACE="${4:-60}"
STABILITY_SECONDS="${5:-30}"
SECURITY_PREFLIGHT_SCRIPT="${6:-}"
INTERVAL=5
START="$(date +%s)"
STABLE_SINCE=""
LAST_SIGNATURE=""

command -v gh >/dev/null 2>&1 || { echo "ERROR: gh not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; exit 1; }

if [[ "$REPO_IDENTITY" != */*/* ]]; then
  echo "ERROR: repository identity must be HOST/owner/repo" >&2
  exit 1
fi
HOST="${REPO_IDENTITY%%/*}"
REPO_PATH="${REPO_IDENTITY#*/}"

gh auth status --hostname "$HOST" >/dev/null 2>&1 || {
  echo "ERROR: gh authentication is not available for $HOST" >&2
  exit 1
}

if [[ -z "$SECURITY_PREFLIGHT_SCRIPT" && -x "$PWD/scripts/security-preflight.sh" ]]; then
  SECURITY_PREFLIGHT_SCRIPT="$PWD/scripts/security-preflight.sh"
fi

TMPDIR_RUN="$(mktemp -d "${TMPDIR:-/tmp}/pr-review-checks.XXXXXX")"
trap 'rm -rf "$TMPDIR_RUN"' EXIT

SECURITY_PREFLIGHT_OUTPUT="$TMPDIR_RUN/security-preflight.result"
if [[ -n "$SECURITY_PREFLIGHT_SCRIPT" ]]; then
  if [[ ! -x "$SECURITY_PREFLIGHT_SCRIPT" ]]; then
    printf '%s\n' 'SECURITY_STATUS=SECURITY_UNAVAILABLE' 'SECURITY_REASON=security preflight script is not executable' >"$SECURITY_PREFLIGHT_OUTPUT"
  else
    set +e
    "$BASH" "$SECURITY_PREFLIGHT_SCRIPT" "$PWD" >"$SECURITY_PREFLIGHT_OUTPUT" 2>&1
    PREFLIGHT_EXIT=$?
    set -e
    if ! grep -qE '^SECURITY_STATUS=(SECURITY_PASSED|SECURITY_FAILED|SECURITY_NOT_APPLICABLE|SECURITY_UNAVAILABLE)$' "$SECURITY_PREFLIGHT_OUTPUT"; then
      printf '%s\n' 'SECURITY_STATUS=SECURITY_UNAVAILABLE' "SECURITY_REASON=security preflight exited without a machine-readable status (exit=$PREFLIGHT_EXIT)" >>"$SECURITY_PREFLIGHT_OUTPUT"
    fi
  fi
else
  printf '%s\n' 'SECURITY_STATUS=SECURITY_UNAVAILABLE' 'SECURITY_REASON=no security preflight script was configured' >"$SECURITY_PREFLIGHT_OUTPUT"
fi

while :; do
  NOW="$(date +%s)"
  ELAPSED=$((NOW - START))

  gh api --hostname "$HOST" --paginate --slurp \
    "repos/$REPO_PATH/commits/$EXPECTED_SHA/check-runs?per_page=100" \
    >"$TMPDIR_RUN/check-runs.json"
  gh api --hostname "$HOST" --paginate --slurp \
    "repos/$REPO_PATH/commits/$EXPECTED_SHA/status?per_page=100" \
    >"$TMPDIR_RUN/status.json"

  RESULT="$(python3 - "$TMPDIR_RUN/check-runs.json" "$TMPDIR_RUN/status.json" "$SECURITY_PREFLIGHT_OUTPUT" <<'PY'
import hashlib
import json
import re
import sys

check_path, status_path, fallback_path = sys.argv[1:]

with open(check_path, encoding="utf-8") as f:
    check_pages = json.load(f)
with open(status_path, encoding="utf-8") as f:
    status_pages = json.load(f)

def flatten_pages(pages, key):
    items = []
    for page in pages:
        if isinstance(page, dict):
            items.extend(page.get(key, []))
    return items

security_pattern = re.compile(
    r"codeql|code[ -]?scanning|security|secret|gitleaks|semgrep|trivy|osv|snyk|dependabot|dependency[ -]?scan|bandit|pip[ -]?audit|npm[ -]?audit|^analy[sz]e(?:\s*\(|$)",
    re.IGNORECASE,
)

def group_for(name):
    return "security" if security_pattern.search(name or "") else "ci"

checks = flatten_pages(check_pages, "check_runs")
statuses = flatten_pages(status_pages, "statuses")
groups = {
    "ci": {"count": 0, "pending": [], "failed": []},
    "security": {"count": 0, "pending": [], "failed": []},
}
items = []

for run in checks:
    name = run.get("name") or "<unnamed-check>"
    group = group_for(name)
    state = run.get("status")
    conclusion = run.get("conclusion")
    groups[group]["count"] += 1
    items.append((group, "check", str(run.get("id") or ""), name, state or "", conclusion or ""))
    if state != "completed":
        groups[group]["pending"].append(name)
    elif conclusion != "success":
        groups[group]["failed"].append(f"{name}:{conclusion}")

for status in statuses:
    name = status.get("context") or "<unnamed-status>"
    group = group_for(name)
    state = status.get("state")
    groups[group]["count"] += 1
    items.append((group, "status", str(status.get("id") or ""), name, state or "", ""))
    if state == "pending":
        groups[group]["pending"].append(name)
    elif state != "success":
        groups[group]["failed"].append(f"{name}:{state}")

fallback = {}
with open(fallback_path, encoding="utf-8") as f:
    for line in f:
        key, separator, value = line.rstrip("\n").partition("=")
        if separator:
            fallback[key] = value

fallback_status = fallback.get("SECURITY_STATUS", "SECURITY_UNAVAILABLE")
if fallback_status not in {"SECURITY_PASSED", "SECURITY_FAILED", "SECURITY_NOT_APPLICABLE", "SECURITY_UNAVAILABLE"}:
    fallback_status = "SECURITY_UNAVAILABLE"

ci = groups["ci"]
security = groups["security"]
observed_names = {run.get("name") for run in checks} | {status.get("context") for status in statuses}
if "ci" not in observed_names:
    ci_status = "CI_UNAVAILABLE"
elif ci["pending"]:
    ci_status = "CI_PENDING"
elif ci["failed"]:
    ci_status = "CI_FAILED"
else:
    ci_status = "CI_PASSED"

# All configured security gates are required independently.
if not {"Security Preflight", "Analyze (python)"}.issubset(observed_names):
    security_status = "SECURITY_UNAVAILABLE"
elif security["pending"]:
    security_status = "SECURITY_PENDING"
elif security["failed"]:
    security_status = "SECURITY_FAILED"
else:
    security_status = "SECURITY_PASSED"

all_pending = ci["pending"] + security["pending"]
all_failed = ci["failed"] + security["failed"]
signature = hashlib.sha256(repr(sorted(items) + [("fallback", fallback_status)]).encode()).hexdigest()
print(f"COUNT={len(checks) + len(statuses)}")
print(f"PENDING={len(all_pending)}")
print(f"FAILED={len(all_failed)}")
print(f"CI_COUNT={ci['count']}")
print(f"CI_PENDING={len(ci['pending'])}")
print(f"CI_FAILED={len(ci['failed'])}")
print(f"CI_STATUS={ci_status}")
print(f"SECURITY_COUNT={security['count']}")
print(f"SECURITY_PENDING={len(security['pending'])}")
print(f"SECURITY_FAILED={len(security['failed'])}")
print(f"SECURITY_STATUS={security_status}")
print(f"SECURITY_FALLBACK_STATUS={fallback_status}")
print(f"SIGNATURE={signature}")
if all_pending:
    print("PENDING_NAMES=" + ",".join(sorted(all_pending)))
if all_failed:
    print("FAILED_NAMES=" + ",".join(sorted(all_failed)))
PY
  )"

  COUNT="$(printf '%s\n' "$RESULT" | awk -F= '$1=="COUNT"{print $2}')"
  CI_COUNT="$(printf '%s\n' "$RESULT" | awk -F= '$1=="CI_COUNT"{print $2}')"
  CI_STATUS="$(printf '%s\n' "$RESULT" | awk -F= '$1=="CI_STATUS"{print $2}')"
  SECURITY_STATUS="$(printf '%s\n' "$RESULT" | awk -F= '$1=="SECURITY_STATUS"{print $2}')"
  PENDING="$(printf '%s\n' "$RESULT" | awk -F= '$1=="PENDING"{print $2}')"
  FAILED="$(printf '%s\n' "$RESULT" | awk -F= '$1=="FAILED"{print $2}')"
  SIGNATURE="$(printf '%s\n' "$RESULT" | awk -F= '$1=="SIGNATURE"{print $2}')"

  if [[ "$FAILED" -gt 0 ]]; then
    printf '%s\n' "$RESULT" >&2
    echo "ERROR: CI/security check did not complete successfully for $EXPECTED_SHA" >&2
    exit 1
  fi

  if [[ "$SECURITY_STATUS" == "SECURITY_FAILED" ]]; then
    printf '%s\n' "$RESULT" >&2
    echo "ERROR: security preflight/check failed for $EXPECTED_SHA" >&2
    exit 1
  fi

  if [[ "$CI_STATUS" == "CI_UNAVAILABLE" && "$ELAPSED" -ge "$NO_CHECKS_GRACE" ]]; then
    printf '%s\n' "$RESULT" >&2
    echo "EXPECTED_SHA=$EXPECTED_SHA" >&2
    echo "WAITED_SECONDS=$ELAPSED" >&2
    echo "STATUS=CI_UNAVAILABLE" >&2
    echo "ERROR: required ci context was not observed; explicit human decision is required before continuing" >&2
    exit 4
  fi

  if [[ "$SECURITY_STATUS" == "SECURITY_UNAVAILABLE" && "$ELAPSED" -ge "$NO_CHECKS_GRACE" ]]; then
    printf '%s\n' "$RESULT" >&2
    echo "EXPECTED_SHA=$EXPECTED_SHA" >&2
    echo "WAITED_SECONDS=$ELAPSED" >&2
    echo "STATUS=SECURITY_UNAVAILABLE" >&2
    echo "ERROR: required Security Preflight / Analyze (python) contexts were unavailable; explicit human decision is required before continuing" >&2
    exit 4
  fi

  if [[ "$CI_STATUS" == "CI_PASSED" && ( "$SECURITY_STATUS" == "SECURITY_PASSED" || "$SECURITY_STATUS" == "SECURITY_NOT_APPLICABLE" ) ]]; then
    if [[ "$SIGNATURE" != "$LAST_SIGNATURE" || -z "$STABLE_SINCE" ]]; then
      LAST_SIGNATURE="$SIGNATURE"
      STABLE_SINCE="$NOW"
    fi

    STABLE_FOR=$((NOW - STABLE_SINCE))
    if [[ "$STABLE_FOR" -ge "$STABILITY_SECONDS" ]]; then
      printf '%s\n' "$RESULT"
      echo "EXPECTED_SHA=$EXPECTED_SHA"
      echo "STABLE_SECONDS=$STABLE_FOR"
      echo "STATUS=CHECKS_PASSED_STABLE"
      exit 0
    fi
  else
    STABLE_SINCE=""
    LAST_SIGNATURE="$SIGNATURE"
  fi

  if [[ "$ELAPSED" -ge "$TIMEOUT" ]]; then
    printf '%s\n' "$RESULT" >&2
    echo "ERROR: timed out waiting for stable CI/security checks for $EXPECTED_SHA" >&2
    exit 1
  fi

  sleep "$INTERVAL"
done
