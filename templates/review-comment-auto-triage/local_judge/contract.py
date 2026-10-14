"""Strict, provider-neutral shadow observations. No routing or write authority."""

import json
import math
import re

FIELDS = ("needs_action", "category", "priority", "auto_fixable", "high_risk")
OPTIONS = {
    "needs_action": {"A": True, "B": False},
    "category": dict(zip("ABCDEF", ("security", "bug", "test", "style", "docs", "other"))),
    "priority": dict(zip("ABCD", ("p0", "p1", "p2", "p3"))),
    "auto_fixable": {"A": True, "B": False},
    "high_risk": {"A": True, "B": False},
}
MODEL = "gemma-4-e4b"
MAX_REQUEST = 16384
MAX_RESPONSE = 32768
REASONS = {
    None, "unconfigured", "invalid_config", "invalid_input", "unavailable", "timeout",
    "malformed_response", "response_too_large", "request_too_large", "http_error",
    "low_confidence", "high_risk", "non_shadow_response", "model_mismatch",
    "jev_fallback", "baseline_unavailable",
    "invalid_comment_id", "invalid_body", "comment_too_large", "invalid_comment",
    "invalid_existing_decision", "invalid_route_config", "unparseable_response",
    "credits_exhausted", "spend_limit", "rate_limited", "billing_unavailable",
    "api_failure", "undecided",
}


class Invalid(ValueError):
    """A sanitized error code, never an upstream message."""


def valid_reason(value):
    return (value is None or isinstance(value, str) and
            (value in REASONS or re.fullmatch(r"http_[1-5][0-9]{2}", value) is not None))


def number(value, maximum=None):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (maximum is None or value <= maximum))


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Invalid("malformed_response")
            result[key] = value
        return result

    def constant(_):
        raise Invalid("malformed_response")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("malformed_response")


def comment_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value) is not None


def validate_input(value):
    exact(value, ("comment_id", "body", "diff_hunk"))
    if not comment_id(value["comment_id"]):
        raise Invalid("invalid_input")
    for key in ("body", "diff_hunk"):
        text = value[key]
        if not isinstance(text, str) or len(text.encode("utf-8")) > 6000:
            raise Invalid("invalid_input")
    if not value["body"].strip():
        raise Invalid("invalid_input")
    return value


def validate_decision(value):
    exact(value, FIELDS)
    for field in FIELDS:
        if not any(type(value[field]) is type(v) and value[field] == v
                   for v in OPTIONS[field].values()):
            raise Invalid("malformed_response")
    return value


def validate_local(value, expected_id):
    exact(value, ("comment_id", "model", "mode", "authoritative", "decision",
                  "probabilities", "latency_ms", "field_latency_ms", "cache_prompt",
                  "cache_tokens", "probability_kind"))
    if (value["comment_id"] != expected_id or value["model"] != MODEL
            or value["mode"] != "shadow" or value["authoritative"] is not False
            or value["probability_kind"] != "constrained_distribution"
            or type(value["cache_prompt"]) is not bool):
        raise Invalid("malformed_response")
    validate_decision(value["decision"])
    exact(value["probabilities"], FIELDS)
    exact(value["field_latency_ms"], FIELDS)
    exact(value["cache_tokens"], FIELDS)
    for field in FIELDS:
        probabilities = value["probabilities"][field]
        exact(probabilities, OPTIONS[field])
        if (not all(number(p, 1) for p in probabilities.values())
                or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.001)):
            raise Invalid("malformed_response")
        selected = max(probabilities, key=probabilities.get)
        if value["decision"][field] != OPTIONS[field][selected]:
            raise Invalid("malformed_response")
        if not number(value["field_latency_ms"][field], 60000):
            raise Invalid("malformed_response")
        cached = value["cache_tokens"][field]
        if cached is not None and (type(cached) is not int or not 0 <= cached <= 32768):
            raise Invalid("malformed_response")
    if not number(value["latency_ms"], 60000):
        raise Invalid("malformed_response")
    return value


def disposition(decision):
    if decision is None:
        return None
    if (decision["high_risk"] or decision["category"] == "security"
            or decision["priority"] in ("p0", "p1")):
        return "BLOCKING"
    if not decision["needs_action"]:
        return "DISMISS"
    if decision["priority"] == "p2" and decision["auto_fixable"]:
        return "IN-SCOPE FIX"
    return "FOLLOW-UP"


def observation(cid, provider, *, decision=None, reason=None, confidence=None,
                probabilities=None, latency_ms=None, measurements=None):
    if provider not in ("jev", "local_judge", "baseline") or not comment_id(cid):
        raise Invalid("invalid_input")
    if decision is not None:
        validate_decision(decision)
    if not valid_reason(reason):
        reason = "unavailable"
    return {
        "schema_version": 1, "comment_id": cid, "provider": provider,
        "model": {"jev": "typesafe/jev", "local_judge": MODEL, "baseline": "codex"}[provider],
        "mode": "shadow", "authoritative": False,
        "effective_disposition_source": "baseline", "decision": decision,
        "disposition_candidate": disposition(decision),
        "confidence": confidence, "probabilities": probabilities,
        "latency_ms": latency_ms, "measurements": measurements,
        "fallback_required": reason is not None, "fallback_reason": reason,
    }


def compare(left, right):
    if left is None or right is None:
        return None
    return {
        "disagreements": [field for field in FIELDS if left[field] != right[field]],
        "false_negative": right["needs_action"] and not left["needs_action"],
        "false_positive": not right["needs_action"] and left["needs_action"],
        "blocking_false_negative": disposition(right) == "BLOCKING" and disposition(left) != "BLOCKING",
        "security_false_negative": right["category"] == "security" and left["category"] != "security",
    }
