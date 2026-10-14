#!/usr/bin/env bash
if (( BASH_VERSINFO[0] < 5 )); then
  printf 'ERROR: Bash 5 or newer required (current %s)\n' "$BASH_VERSION" >&2
  exit 4
fi
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <pr-number>" >&2
  exit 2
fi

PR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v git >/dev/null 2>&1 || { echo "ERROR: git not found" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "ERROR: gh not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; exit 1; }

git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "ERROR: not inside a git repository" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean" >&2
  exit 1
fi

repo_identity_from_url() {
  local url="$1"
  local host path identity rest authority

  case "$url" in
    git@*:*/*)
      host="${url#git@}"
      host="${host%%:*}"
      path="${url#*:}"
      ;;
    ssh://git@*/*/*)
      rest="${url#ssh://git@}"
      host="${rest%%/*}"
      path="${rest#*/}"
      if [[ "$host" == *:* ]]; then
        echo "ERROR: SSH URL with explicit port is not supported safely" >&2
        return 1
      fi
      ;;
    http://*/*/*|https://*/*/*)
      rest="${url#*://}"
      authority="${rest%%/*}"
      path="${rest#*/}"
      # HTTPS remotes may embed userinfo (for example a token). Strip it
      # before deriving or ever printing the repository identity.
      host="${authority##*@}"
      ;;
    *)
      echo "ERROR: unsupported Git remote URL format" >&2
      return 1
      ;;
  esac

  path="${path%.git}"
  if [[ -z "$host" || "$path" != */* || "$path" == */*/* ]]; then
    echo "ERROR: could not resolve HOST/owner/repo from Git remote URL" >&2
    return 1
  fi

  identity="${host}/${path}"
  printf '%s\n' "$identity" | tr '[:upper:]' '[:lower:]'
}

ORIGIN_FETCH_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$ORIGIN_FETCH_URL" ]]; then
  echo "ERROR: origin fetch URL is not configured" >&2
  exit 1
fi

mapfile -t ORIGIN_PUSH_URLS < <(git remote get-url --push --all origin 2>/dev/null || true)
if [[ ${#ORIGIN_PUSH_URLS[@]} -eq 0 ]]; then
  echo "ERROR: origin push URL is not configured" >&2
  exit 1
fi

REPO="$(repo_identity_from_url "$ORIGIN_FETCH_URL")"
for push_url in "${ORIGIN_PUSH_URLS[@]}"; do
  PUSH_REPO="$(repo_identity_from_url "$push_url")"
  if [[ "$PUSH_REPO" != "$REPO" ]]; then
    echo "ERROR: origin push repository differs from fetch/GitHub repository" >&2
    echo "  fetch identity: $REPO" >&2
    echo "  push identity:  $PUSH_REPO" >&2
    echo "Do not push until every origin push URL targets the same GitHub repository." >&2
    exit 1
  fi
done

HOST="${REPO%%/*}"
gh auth status --hostname "$HOST" >/dev/null 2>&1 || {
  echo "ERROR: gh authentication is not available for $HOST" >&2
  exit 1
}

DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef --jq '.defaultBranchRef.name')"
PR_JSON="$(gh pr view "$PR" --repo "$REPO" --json number,state,headRefName,headRefOid,baseRefName,isCrossRepository,url)"

STATE="$(printf '%s' "$PR_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])')"
HEAD_BRANCH="$(printf '%s' "$PR_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["headRefName"])')"
HEAD_SHA="$(printf '%s' "$PR_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["headRefOid"])')"
CROSS_REPO="$(printf '%s' "$PR_JSON" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["isCrossRepository"]).lower())')"
URL="$(printf '%s' "$PR_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["url"])')"

if [[ "$STATE" != "OPEN" ]]; then
  echo "ERROR: PR #$PR is not open (state=$STATE)" >&2
  exit 1
fi

if [[ "$CROSS_REPO" == "true" ]]; then
  echo "ERROR: cross-repository PR is not supported by this skill" >&2
  exit 1
fi

if [[ -z "$HEAD_BRANCH" || -z "$HEAD_SHA" ]]; then
  echo "ERROR: could not resolve PR head branch/SHA" >&2
  exit 1
fi

if [[ "$HEAD_BRANCH" == "$DEFAULT_BRANCH" ]]; then
  echo "ERROR: PR head branch is the default branch ($DEFAULT_BRANCH)" >&2
  exit 1
fi

RUNTIME_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pr-review-fix.${PR}.XXXXXX")"
cp -R "$SCRIPT_DIR" "$RUNTIME_DIR/scripts"

BEFORE_SHA="$HEAD_SHA"

git fetch origin "+refs/heads/$HEAD_BRANCH:refs/remotes/origin/$HEAD_BRANCH"

if git show-ref --verify --quiet "refs/heads/$HEAD_BRANCH"; then
  git checkout "$HEAD_BRANCH"
else
  git checkout --track -b "$HEAD_BRANCH" "origin/$HEAD_BRANCH"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$HEAD_BRANCH" ]]; then
  echo "ERROR: checkout mismatch: current=$CURRENT_BRANCH expected=$HEAD_BRANCH" >&2
  exit 1
fi

LOCAL_SHA="$(git rev-parse HEAD)"
if [[ "$LOCAL_SHA" != "$HEAD_SHA" ]]; then
  echo "ERROR: local HEAD does not match GitHub PR head SHA" >&2
  echo "  local:  $LOCAL_SHA" >&2
  echo "  github: $HEAD_SHA" >&2
  echo "Synchronize the existing PR head branch first; do not create another branch." >&2
  exit 1
fi

cat <<EOF
PR_NUMBER=$PR
PR_URL=$URL
REPO=$REPO
HEAD_BRANCH=$HEAD_BRANCH
BEFORE_SHA=$BEFORE_SHA
HEAD_SHA=$HEAD_SHA
DEFAULT_BRANCH=$DEFAULT_BRANCH
ORIGIN_FETCH_IDENTITY=$REPO
ORIGIN_PUSH_URL_COUNT=${#ORIGIN_PUSH_URLS[@]}
RUNTIME_DIR=$RUNTIME_DIR
VERIFY_SCRIPT=$RUNTIME_DIR/scripts/verify-pr-head.sh
STATUS=READY
EOF
