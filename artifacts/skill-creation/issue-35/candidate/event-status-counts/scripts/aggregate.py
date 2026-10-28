#!/usr/bin/env python3
"""Validate and count bounded public event input using only the standard library."""

import json
import re
import sys

MAX_STDIN_BYTES = 16384
CATEGORY = re.compile(r"[a-z0-9]{1,16}", re.ASCII)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-JSON constant")


def aggregate(raw):
    if len(raw) > MAX_STDIN_BYTES:
        raise ValueError("oversize input")
    data = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(data, dict) or set(data) != {"events"}:
        raise ValueError("invalid root")
    events = data["events"]
    if not isinstance(events, list):
        raise ValueError("invalid events")
    counts = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != {"category", "status"}:
            raise ValueError("invalid event")
        category = event["category"]
        status = event["status"]
        if not isinstance(category, str) or CATEGORY.fullmatch(category) is None:
            raise ValueError("invalid category")
        if not isinstance(status, str) or status not in ("ok", "failed"):
            raise ValueError("invalid status")
        if category not in counts:
            counts[category] = {"ok": 0, "failed": 0}
        counts[category][status] += 1
    return {"counts": counts}


def main():
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    try:
        result = aggregate(raw)
    except (ValueError, UnicodeError, RecursionError):
        sys.stdout.write('{"error":"INVALID_INPUT"}\n')
        return 2
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
