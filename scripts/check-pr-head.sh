#!/usr/bin/env bash
# Read-only check that a PR is ready for a merge request on its final head.
#
#   check-pr-head.sh <pr-number>
#
# Checks, all on the PR's current head SHA:
#   1. the local HEAD is the same commit as the PR head
#   2. every required check exists and succeeded. A name is looked up both as a check
#      run and as a commit status of the same context (some workflows report through
#      statuses); a failure or a pending result in either stops it. The names come from
#      PR_GATE_CHECKS (comma separated), else .github/pr-gate-checks on the PR's base
#      branch on GitHub (one per line; blank lines and lines starting with # are
#      ignored), else the default. The base branch copy is used so that neither local
#      edits nor the PR itself can drop a required check.
#   3. the formal review finished on this head with no unresolved findings. Accepted kinds
#      come from PR_GATE_REVIEW (comma separated), else .github/pr-gate-review on the base
#      branch (one per line, like pr-gate-checks), else "codex". Kinds:
#        codex        the Codex summary comment (codex-review-state:v1) by PR_GATE_REVIEWER
#        claude-code  a PR comment with <!-- claude-code-review:v1 {json} --> whose author
#                     is OWNER, MEMBER or COLLABORATOR; json has commit_sha, status and
#                     has_unresolved_findings (same meaning as the Codex state)
#      One accepted kind completed on this head with no findings passes; any accepted kind
#      reporting unresolved findings on this head stops it.
#   4. no review thread is unresolved
#   5. GitHub reports no conflict with the base branch
#   6. no reviewer has requested changes: the latest APPROVED / CHANGES_REQUESTED /
#      DISMISSED review of each reviewer, and reviewDecision when the repo fills it
# Review comments posted as plain PR comments are not read; check those by hand.
# Prints PR_GATE_STATUS=<status> and PR_GATE_REASON=<text>. Exit 0 only for READY.
# Needs gh (logged in) and jq. Anything it cannot read is reported, never passed.

set -u

default_checks='verification,Security Preflight'
default_review='codex'
reviewer="${PR_GATE_REVIEWER:-chatgpt-codex-connector}"

report() {
  printf 'PR_GATE_STATUS=%s\nPR_GATE_REASON=%s\n' "$1" "$2"
  [[ $1 == READY ]] && exit 0
  exit 1
}

[[ $# -eq 1 && $1 =~ ^[0-9]+$ ]] || { echo "usage: check-pr-head.sh <pr-number>" >&2; exit 2; }
pr="$1"
for tool in gh jq git; do
  command -v "$tool" >/dev/null 2>&1 || report UNAVAILABLE "$tool is not installed"
done

pr_json="$(gh pr view "$pr" --json headRefOid,baseRefName,url,state,mergeable,reviewDecision,reviews 2>/dev/null)" || report UNAVAILABLE "could not read PR #$pr"
head="$(jq -er '.headRefOid' <<<"$pr_json" 2>/dev/null)" || report UNAVAILABLE "PR head is missing"
url="$(jq -er '.url' <<<"$pr_json" 2>/dev/null)" || report UNAVAILABLE "PR url is missing"
state="$(jq -r '.state' <<<"$pr_json")"
repo="$(sed -E 's#^https://[^/]+/([^/]+/[^/]+)/pull/[0-9]+$#\1#' <<<"$url")"
[[ $repo == */* && $repo != "$url" ]] || report UNAVAILABLE "could not parse the repository from $url"
printf 'PR_GATE_HEAD=%s\n' "$head"

[[ $state == OPEN ]] || report NOT_OPEN "PR #$pr is $state"

local_head="$(git rev-parse HEAD 2>/dev/null)" || report UNAVAILABLE "could not read the local HEAD"
[[ $local_head == "$head" ]] || report STALE_HEAD "local HEAD $local_head differs from PR head $head"

# Reads a list file from the PR's base branch on GitHub into the named array.
# Returns 0 when read, 1 when the file does not exist; any other error stops with <status>.
read_base_list() { # <path> <status> <array-name>
  local base contents listed err line
  base="$(jq -er '.baseRefName' <<<"$pr_json" 2>/dev/null)" || report "$2" "PR base branch is missing"
  # The branch name goes through --raw-field, so a name with + or & is sent as it is.
  contents=(--method GET --raw-field "ref=$base" "repos/$repo/contents/$1")
  if listed="$(gh api -H 'Accept: application/vnd.github.raw+json' "${contents[@]}" 2>/dev/null)"; then
    while IFS= read -r line || [[ -n $line ]]; do
      line="${line%$'\r'}"
      [[ -z ${line//[[:space:]]/} || $line == '#'* ]] && continue
      eval "$3+=(\"\$line\")"
    done <<<"$listed"
    return 0
  fi
  # Only "no such file" falls back to the default; any other error is not success.
  err="$(gh api "${contents[@]}" 2>&1 >/dev/null)"
  grep -q 'HTTP 404' <<<"$err" || report "$2" "could not read $1 on $base"
  return 1
}

required=()
if [[ -n ${PR_GATE_CHECKS:-} ]]; then
  IFS=',' read -r -a required <<<"$PR_GATE_CHECKS"
else
  read_base_list .github/pr-gate-checks CHECK_UNAVAILABLE required || true
fi
[[ ${#required[@]} -gt 0 ]] || IFS=',' read -r -a required <<<"$default_checks"

# filter=latest keeps only the newest run of each check, so a re-run replaces an old failure.
runs="$(gh api "repos/$repo/commits/$head/check-runs?filter=latest&per_page=100" 2>/dev/null)" ||
  report CHECK_UNAVAILABLE "could not read checks for $head"
# The combined status keeps only the latest status of each context.
statuses="$(gh api "repos/$repo/commits/$head/status?per_page=100" 2>/dev/null)" ||
  report CHECK_UNAVAILABLE "could not read commit statuses for $head"
# Only one page (100) is read. A result left on a later page could be a failure, so
# more than one page is not success.
jq -e '(.total_count // (.check_runs | length)) <= (.check_runs | length)' <<<"$runs" >/dev/null 2>&1 ||
  report CHECK_UNAVAILABLE "more than 100 checks on $head; check them by hand"
jq -e '(.total_count // (.statuses | length)) <= (.statuses | length)' <<<"$statuses" >/dev/null 2>&1 ||
  report CHECK_UNAVAILABLE "more than 100 commit statuses on $head; check them by hand"
for name in "${required[@]}"; do
  from_run="$(jq -r --arg n "$name" '
    [.check_runs[] | select(.name == $n)] as $r
    | if ($r | length) == 0 then "missing"
      elif any($r[]; .status != "completed") then "pending"
      elif any($r[]; .conclusion != "success" and .conclusion != "skipped" and .conclusion != "neutral") then "failed"
      elif any($r[]; .conclusion == "success") then "success"
      else "skipped" end' <<<"$runs" 2>/dev/null)" || report CHECK_UNAVAILABLE "could not parse checks"
  from_status="$(jq -r --arg n "$name" '
    [.statuses[] | select(.context == $n) | .state] as $s
    | if ($s | length) == 0 then "missing"
      elif any($s[]; . == "pending") then "pending"
      elif all($s[]; . == "success") then "success"
      else "failed" end' <<<"$statuses" 2>/dev/null)" || report CHECK_UNAVAILABLE "could not parse commit statuses"
  # Either source can stop the check; success needs at least one success and nothing worse.
  if [[ $from_run == failed || $from_status == failed ]]; then summary=failed
  elif [[ $from_run == pending || $from_status == pending ]]; then summary=pending
  elif [[ $from_run == skipped ]]; then summary=skipped
  elif [[ $from_run == success || $from_status == success ]]; then summary=success
  else summary=missing
  fi
  case "$summary" in
    success) ;;
    missing) report CHECK_UNAVAILABLE "check '$name' was not found on $head" ;;
    pending) report CHECK_PENDING "check '$name' has not finished on $head" ;;
    skipped) report CHECK_UNAVAILABLE "check '$name' was skipped on $head, which is not success" ;;
    *) report CHECK_FAILED "check '$name' did not succeed on $head" ;;
  esac
done

kinds=()
if [[ -n ${PR_GATE_REVIEW:-} ]]; then
  IFS=',' read -r -a kinds <<<"$PR_GATE_REVIEW"
else
  read_base_list .github/pr-gate-review REVIEW_UNAVAILABLE kinds || true
fi
[[ ${#kinds[@]} -gt 0 ]] || kinds=("$default_review")

comments="$(gh pr view "$pr" --json comments 2>/dev/null)" || report REVIEW_UNAVAILABLE "could not read PR comments"
passed='' waiting=()
for kind in "${kinds[@]}"; do
  kind="${kind//[[:space:]]/}"
  case "$kind" in
    codex)
      review="$(jq -r --arg who "$reviewer" '
        [.comments[] | select(.author.login == $who) | .body
         | (capture("codex-review-state:v1 (?<s>\\{.*\\}) -->") | .s)?] | last // empty' <<<"$comments" 2>/dev/null)"
      sha_path='.code_review.commit_sha' status_path='.code_review.status' open_path='.code_review.has_unresolved_findings' ;;
    claude-code)
      # Anyone can comment on a public repository, so only trusted authors count.
      review="$(jq -r '
        [.comments[] | select(.authorAssociation == "OWNER" or .authorAssociation == "MEMBER" or .authorAssociation == "COLLABORATOR")
         | .body | (capture("claude-code-review:v1 (?<s>\\{[^\\n]*?\\}) -->") | .s)?] | last // empty' <<<"$comments" 2>/dev/null)"
      sha_path='.commit_sha' status_path='.status' open_path='.has_unresolved_findings' ;;
    *) report REVIEW_UNAVAILABLE "unknown review kind '$kind' in the review setting" ;;
  esac
  if [[ -z $review ]]; then waiting+=("no $kind review"); continue; fi
  r_sha="$(jq -r "$sha_path // empty" <<<"$review" 2>/dev/null)"
  r_status="$(jq -r "$status_path // empty" <<<"$review" 2>/dev/null)"
  r_open="$(jq -r "$open_path" <<<"$review" 2>/dev/null)"
  if [[ $r_sha != "$head" ]]; then waiting+=("latest $kind review is for ${r_sha:-unknown}"); continue; fi
  if [[ $r_status != completed ]]; then waiting+=("$kind review on $head is ${r_status:-unknown}"); continue; fi
  [[ $r_open == false ]] || report REVIEW_FINDINGS "$kind review on $head has unresolved findings"
  passed="$kind"
done
if [[ -z $passed ]]; then
  reason="$(IFS=';'; printf '%s' "${waiting[*]}")"
  if [[ $reason == *"review on $head is"* || $reason == *"review is for"* ]]; then report REVIEW_PENDING "$reason"; fi
  report REVIEW_UNAVAILABLE "$reason"
fi

owner="${repo%%/*}" name="${repo#*/}"
threads="$(gh api graphql -F owner="$owner" -F name="$name" -F pr="$pr" -f query='
  query($owner: String!, $name: String!, $pr: Int!) {
    repository(owner: $owner, name: $name) { pullRequest(number: $pr) {
      reviewThreads(first: 100) { pageInfo { hasNextPage } nodes { isResolved } } } } }' 2>/dev/null)" ||
  report REVIEW_UNAVAILABLE "could not read review threads"
open_threads="$(jq -er '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length' <<<"$threads" 2>/dev/null)" ||
  report REVIEW_UNAVAILABLE "could not parse review threads"
[[ $open_threads -eq 0 ]] || report UNRESOLVED_THREADS "$open_threads review thread(s) are unresolved"
[[ $(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage' <<<"$threads") == false ]] ||
  report REVIEW_UNAVAILABLE "more than 100 review threads; check the rest by hand"

# The second read at the end can see a conflict or a new review decision that
# appeared during this check, so the same checks run on both reads.
check_snapshot() { # <pr-json>
  case "$(jq -r '.mergeable // "UNKNOWN"' <<<"$1")" in
    MERGEABLE) ;;
    CONFLICTING) report CONFLICT "PR #$pr conflicts with its base branch" ;;
    *) report MERGE_STATE_PENDING "GitHub has not finished checking for conflicts" ;;
  esac
  [[ $(jq -r '.reviewDecision // ""' <<<"$1") != CHANGES_REQUESTED ]] ||
    report CHANGES_REQUESTED "a reviewer has requested changes"
  # reviewDecision stays empty unless branch protection requires reviews, so also read
  # each reviewer's latest deciding review. A later COMMENTED review does not clear it.
  local blocking
  blocking="$(jq -r '[(.reviews // [])[] | select(.state == "APPROVED" or .state == "CHANGES_REQUESTED" or .state == "DISMISSED")]
    | group_by(.author.login) | map(max_by(.submittedAt)) | map(select(.state == "CHANGES_REQUESTED") | .author.login) | join(",")' <<<"$1" 2>/dev/null)" ||
    report REVIEW_UNAVAILABLE "could not read the reviews"
  [[ -z $blocking ]] || report CHANGES_REQUESTED "changes requested by $blocking"
}
check_snapshot "$pr_json"

# A push during this check would make every result above stale, so read the head again.
again="$(gh pr view "$pr" --json headRefOid,baseRefName,url,state,mergeable,reviewDecision,reviews 2>/dev/null)" || report UNAVAILABLE "could not re-read PR #$pr"
[[ $(jq -r '.headRefOid' <<<"$again") == "$head" ]] || report STALE_HEAD "PR head changed during the check"
[[ $(jq -r '.state' <<<"$again") == OPEN ]] || report NOT_OPEN "PR #$pr is no longer open"
check_snapshot "$again"

report READY "checks, review ($passed), threads and conflicts are clear on $head"
