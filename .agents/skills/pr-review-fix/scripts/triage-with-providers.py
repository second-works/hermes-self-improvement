#!/usr/bin/env python3
"""Observe JEV / Local Judge / Codex baseline without changing review decisions."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "templates/review-comment-auto-triage"))
from local_judge.contract import Invalid, MAX_REQUEST, comment_id, compare, loads, validate_input
from local_judge.providers import BaselineProvider, JevProvider, LocalJudgeProvider

MAX_COMMENTS = 100
MAX_INPUT = 2 * 1024 * 1024


def run_jev(command, timeout=120):
    """Run legacy JEV in its own process group so timeout stops every child."""
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


def read_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise Invalid("invalid_input")
    return loads(raw)


def current_comments(raw, sha):
    if not isinstance(raw, list):
        raise Invalid("invalid_input")
    flat = [item for page in raw for item in (page if isinstance(page, list) else [page])]
    result = []
    seen = set()
    for item in flat:
        if not isinstance(item, dict):
            continue
        actor = item.get("user")
        if (not isinstance(actor, dict) or actor.get("type") != "Bot"
                or actor.get("login") not in ("chatgpt-codex-connector", "chatgpt-codex-connector[bot]")
                or item.get("commit_id") != sha):
            continue
        cid = str(item.get("id"))
        if not comment_id(cid) or cid in seen:
            raise Invalid("invalid_input")
        seen.add(cid)
        result.append(item)
    if len(result) > MAX_COMMENTS:
        raise Invalid("invalid_input")
    return result


def write_audit(output_file, records):
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False) as handle:
        staging = Path(handle.name)
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
    staging.replace(output)


def collect(repo, pr, sha, comments_file, output_file, baseline_file=None):
    if Path(output_file).resolve() in {Path(p).resolve() for p in (comments_file, baseline_file) if p is not None}:
        raise Invalid("invalid_input")
    # Invalidate old evidence even when this invocation later falls back.
    write_audit(output_file, [])
    if (not re.fullmatch(r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            or not re.fullmatch(r"[1-9][0-9]*", pr)
            or not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise Invalid("invalid_input")
    comments = current_comments(read_json(comments_file), sha)
    baselines = {}
    if baseline_file:
        raw = read_json(baseline_file)
        # Baselines are explicit labels tied to a repository / PR / SHA, never
        # inferred from a provider's answer or stale GitHub review text.
        if (not isinstance(raw, dict) or set(raw) != {"repository", "pr_number", "head_sha", "decisions"}
                or raw["repository"] != repo or type(raw["pr_number"]) is not int
                or raw["pr_number"] != int(pr) or raw["head_sha"] != sha
                or not isinstance(raw["decisions"], dict)):
            raise Invalid("invalid_input")
        baselines = raw["decisions"]
    with tempfile.TemporaryDirectory(prefix="shadow-triage-") as temporary:
        private = Path(temporary)
        selected = private / "comments.json"
        selected.write_text(json.dumps(comments), encoding="utf-8")
        audit = private / "jev.jsonl"
        jev_records = {}
        if comments:
            try:
                returncode = run_jev(
                    ["bash", str(Path(__file__).with_name("triage-with-jev.sh")), repo, pr, sha,
                     str(selected), str(audit)], timeout=120,
                )
                if returncode == 0 and audit.exists() and audit.stat().st_size <= MAX_INPUT:
                    for line in audit.read_text().splitlines():
                        record = loads(line)
                        if isinstance(record, dict) and comment_id(record.get("comment_id")):
                            jev_records[record["comment_id"]] = record
            except Exception:
                pass  # The Local Judge and baseline still run if legacy JEV fails.
        providers = [JevProvider(jev_records), LocalJudgeProvider(os.environ), BaselineProvider(baselines)]
        records = []
        for item in comments:
            review = {"comment_id": str(item["id"]), "body": item.get("body"),
                      "diff_hunk": item.get("diff_hunk") or ""}
            observations = {}
            for provider in providers:
                record = provider.observe(review)
                observations[record["provider"]] = record
            baseline = observations["baseline"]["decision"]
            jev = observations["jev"]["decision"]
            for record in observations.values():
                record.update(repository=repo, pr_number=int(pr), head_sha=sha)
                record["comparison"] = {
                    "baseline": compare(record["decision"], baseline),
                    "jev": compare(record["decision"], jev) if record["provider"] == "local_judge" else None,
                }
                records.append(record)
        # Atomic output: an aborted inference cannot leave an apparently complete audit.
        write_audit(output_file, records)
        return records


def main():
    if len(sys.argv) not in (6, 7):
        print("Usage: triage-with-providers.py <repo> <pr> <sha> <comments.json> <audit.jsonl> [baseline.json]")
        return 2
    try:
        records = collect(*sys.argv[1:])
    except Exception:
        print("SHADOW_STATUS=FALLBACK_INVALID_INPUT")
        print("SHADOW_FALLBACK_REQUIRED=1")
        return 0
    print("SHADOW_STATUS=COMPLETE")
    print("SHADOW_OBSERVED_COUNT=" + str(len(records)))
    print("SHADOW_FALLBACK_COUNT=" + str(sum(record["fallback_required"] for record in records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
