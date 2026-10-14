"""Join sanitized observations with explicit Codex labels, then report metrics."""

import argparse
import json
from pathlib import Path
import statistics

from .contract import (FIELDS, MODEL, Invalid, compare, disposition, exact, loads,
                       number, observation, valid_reason, validate_decision,
                       validate_local)


def summary(rows):
    report = {}
    for provider in ("jev", "local_judge"):
        selected = [row for row in rows if row["provider"] == provider]
        paired = [row for row in selected if row.get("comparison", {}).get("baseline") is not None]
        compared_jev = [row for row in selected if row.get("comparison", {}).get("jev") is not None]
        latencies = [row["latency_ms"] for row in selected if number(row.get("latency_ms"))]
        fallback = sum(row["fallback_required"] for row in selected)
        calibration = {}
        for field in FIELDS:
            bins = [{"count": 0, "correct": 0, "probability_sum": 0.0} for _ in range(5)]
            for row in paired:
                probabilities = row.get("probabilities")
                probability = max(probabilities[field].values()) if probabilities else row.get("confidence")
                if not number(probability, 1):
                    continue
                bucket = bins[min(int(probability * 5), 4)]
                bucket["count"] += 1
                bucket["correct"] += field not in row["comparison"]["baseline"]["disagreements"]
                bucket["probability_sum"] += probability
            calibration[field] = [{
                "lower_bound": index / 5, "upper_bound": (index + 1) / 5,
                "count": bucket["count"],
                "accuracy": bucket["correct"] / bucket["count"] if bucket["count"] else None,
                "mean_score": bucket["probability_sum"] / bucket["count"] if bucket["count"] else None,
            } for index, bucket in enumerate(bins)]
        report[provider] = {
            "observations": len(selected), "paired_with_baseline": len(paired),
            "fallback_count": fallback, "fallback_rate": fallback / len(selected) if selected else None,
            "field_agreement": {field: (sum(field not in row["comparison"]["baseline"]["disagreements"]
                                                for row in paired) / len(paired) if paired else None)
                                for field in FIELDS},
            "field_agreement_with_jev": {field: (sum(field not in row["comparison"]["jev"]["disagreements"]
                                                         for row in compared_jev) / len(compared_jev) if compared_jev else None)
                                         for field in FIELDS},
            "paired_with_jev": len(compared_jev),
            "error_counts": {key: sum(row["comparison"]["baseline"][key] for row in paired)
                             for key in ("false_negative", "false_positive", "blocking_false_negative", "security_false_negative")},
            "mean_latency_ms": statistics.mean(latencies) if latencies else None,
            "p95_latency_ms": sorted(latencies)[max(0, (95 * len(latencies) + 99) // 100 - 1)] if latencies else None,
            "mean_field_latency_ms": {}, "mean_cache_tokens": {},
            "calibration_score": "constrained_probability" if provider == "local_judge" else "jev_confidence",
            "calibration": calibration,
        }
        for field in FIELDS:
            for metric, source in (("mean_field_latency_ms", "field_latency_ms"), ("mean_cache_tokens", "cache_tokens")):
                values = [row["measurements"][source][field] for row in selected
                          if row.get("measurements") and number(row["measurements"][source].get(field))]
                report[provider][metric][field] = statistics.mean(values) if values else None
    return report


def join(rows, baseline):
    exact(baseline, ("repository", "pr_number", "head_sha", "decisions"))
    if not isinstance(baseline["decisions"], dict):
        raise Invalid("invalid_input")
    grouped = {}
    output = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise Invalid("invalid_input")
        cid, provider = raw.get("comment_id"), raw.get("provider")
        record = observation(cid, provider)
        exact(raw, set(record) | {"repository", "pr_number", "head_sha", "comparison"})
        if (any(raw[key] != baseline[key] for key in ("repository", "pr_number", "head_sha"))
                or type(raw["pr_number"]) is not int or raw["mode"] != "shadow"
                or raw["authoritative"] is not False or raw["effective_disposition_source"] != "baseline"
                or raw["schema_version"] != 1 or raw["model"] != record["model"]):
            raise Invalid("invalid_input")
        if raw["decision"] is not None:
            validate_decision(raw["decision"])
        if raw["confidence"] is not None and not number(raw["confidence"], 1):
            raise Invalid("invalid_input")
        if raw["latency_ms"] is not None and not number(raw["latency_ms"]):
            raise Invalid("invalid_input")
        if provider == "local_judge" and raw["decision"] is not None:
            validate_local({"comment_id": cid, "model": MODEL, "mode": "shadow", "authoritative": False,
                            "decision": raw["decision"], "probabilities": raw["probabilities"],
                            "latency_ms": raw["latency_ms"], **(raw["measurements"] or {})}, cid)
        elif raw["probabilities"] is not None or raw["measurements"] is not None:
            raise Invalid("invalid_input")
        reason = raw["fallback_reason"]
        if (type(raw["fallback_required"]) is not bool or not valid_reason(reason)
                or raw["fallback_required"] != (reason is not None)):
            raise Invalid("invalid_input")
        key = (cid, provider)
        if key in grouped:
            raise Invalid("invalid_input")
        grouped[key] = raw
    ids = {cid for cid, _provider in grouped}
    for cid in sorted(ids):
        expected = baseline["decisions"].get(cid)
        if expected is not None:
            validate_decision(expected)
        jev = grouped.get((cid, "jev"), {}).get("decision")
        for provider in ("jev", "local_judge", "baseline"):
            raw = grouped.get((cid, provider))
            if raw is None:
                continue
            record = dict(raw)
            if provider == "baseline":
                record = {**record, **observation(cid, "baseline", decision=expected,
                                                reason=None if expected else "baseline_unavailable")}
            # Never trust precomputed comparison fields from a remote artifact.
            record["comparison"] = {"baseline": compare(record["decision"], expected),
                                    "jev": compare(record["decision"], jev) if provider == "local_judge" else None}
            output.append(record)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit")
    parser.add_argument("baseline")
    parser.add_argument("output")
    args = parser.parse_args()
    try:
        if Path(args.audit).stat().st_size > 2 * 1024 * 1024 or Path(args.baseline).stat().st_size > 1024 * 1024:
            raise Invalid("invalid_input")
        rows = [loads(line) for line in Path(args.audit).read_text().splitlines()]
        baseline = loads(Path(args.baseline).read_text())
        report = summary(join(rows, baseline))
        Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    except Exception:
        print("EVALUATION_STATUS=INVALID_INPUT")
        return 1
    print("EVALUATION_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
