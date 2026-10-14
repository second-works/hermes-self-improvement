"""Synthetic fixture smoke benchmark; never claims production/Codex accuracy."""

import argparse
import json
from pathlib import Path
import subprocess

from .contract import Invalid, compare, disposition, loads, observation, validate_decision, validate_input
from .evaluate import summary
from .server import Judge


def resource_sample(pid):
    if pid is None:
        return None
    try:
        values = subprocess.check_output(["ps", "-p", str(pid), "-o", "%cpu=,rss="], text=True).split()
        return {"cpu_percent": float(values[0]), "rss_kib": int(values[1])}
    except Exception:
        return None


def run(cases, judge, minimum=0.8):
    rows = []
    for case in cases:
        review = validate_input(case["review"])
        expected = validate_decision(case["expected"])
        try:
            raw = judge.triage(review)
            reason = "high_risk" if disposition(raw["decision"]) == "BLOCKING" else None
            if reason is None and any(max(p.values()) < minimum for p in raw["probabilities"].values()):
                reason = "low_confidence"
            row = observation(review["comment_id"], "local_judge", decision=raw["decision"], reason=reason,
                              probabilities=raw["probabilities"], latency_ms=raw["latency_ms"],
                              measurements={key: raw[key] for key in ("field_latency_ms", "cache_prompt", "cache_tokens", "probability_kind")})
        except Exception:
            row = observation(review["comment_id"], "local_judge", reason="unavailable")
        row["comparison"] = {"baseline": compare(row["decision"], expected), "jev": None}
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures")
    parser.add_argument("output")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--llama-pid", type=int)
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 100 or Path(args.fixtures).stat().st_size > 2 * 1024 * 1024:
            raise Invalid("invalid_input")
        fixtures = loads(Path(args.fixtures).read_text())
        if fixtures["label_source"] != "synthetic_fixture_expected":
            raise Invalid("invalid_input")
        cases = fixtures["cases"][:args.limit]
        if not cases:
            raise Invalid("invalid_input")
        report = {"label_source": "synthetic_fixture_expected", "case_count": len(cases),
                  "production_accuracy": "NOT_VERIFIED", "jev_comparison": "NOT_RUN",
                  "openclaw_rag_contention": "NOT_MEASURED", "cache_runs": {}}
        for cache in (False, True):
            before = resource_sample(args.llama_pid)
            rows = run(cases, Judge(cache=cache))
            report["cache_runs"]["on" if cache else "off"] = {
                "summary": summary(rows)["local_judge"], "observations": rows,
                "llama_process_before": before, "llama_process_after": resource_sample(args.llama_pid),
            }
        Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    except Exception:
        print("BENCHMARK_STATUS=FAILED")
        return 1
    print("BENCHMARK_STATUS=COMPLETE")
    print("BENCHMARK_CASES=" + str(len(cases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
