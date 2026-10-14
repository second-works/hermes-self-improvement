"""Provider adapters implementing observe(review) -> a common observation."""

import json
import re
import time
from urllib.parse import urlsplit

from .contract import (MODEL, Invalid, MAX_REQUEST, OPTIONS, exact, number,
                       observation, valid_reason, validate_decision, validate_input,
                       validate_local)
from .transport import request_json


class LocalJudgeProvider:
    def __init__(self, env, transport=request_json):
        self.env = env
        self.transport = transport

    def observe(self, review):
        cid = review["comment_id"]
        env = self.env
        keys = ("LOCAL_JUDGE_URL", "LOCAL_JUDGE_HOST", "LOCAL_JUDGE_TOKEN",
                "LOCAL_JUDGE_ACCESS_CLIENT_ID", "LOCAL_JUDGE_ACCESS_CLIENT_SECRET")
        if not all(env.get(key) for key in keys):
            return observation(cid, "local_judge", reason="unconfigured")
        started = time.monotonic()
        try:
            url = urlsplit(env["LOCAL_JUDGE_URL"])
            host = env["LOCAL_JUDGE_HOST"]
            if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
                    or "." not in host or re.fullmatch(r"[0-9.]+", host)
                    or url.scheme != "https" or url.hostname != host
                    or url.netloc != host or url.path != "/triage"
                    or url.query or url.fragment or url.username or url.password):
                raise Invalid("invalid_config")
            credentials = [env[key] for key in keys[2:]]
            if any(not re.fullmatch(r"[!-~]{1,512}", value) for value in credentials):
                raise Invalid("invalid_config")
            minimum = float(env.get("LOCAL_JUDGE_MIN_CONFIDENCE") or "0.8")
            if not number(minimum, 1):
                raise Invalid("invalid_config")
            payload = json.dumps(validate_input(review), ensure_ascii=False).encode()
            if len(payload) > MAX_REQUEST:
                raise Invalid("request_too_large")
            reply = self.transport(env["LOCAL_JUDGE_URL"], data=payload, headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + credentials[0],
                "CF-Access-Client-Id": credentials[1], "CF-Access-Client-Secret": credentials[2],
            }, timeout=30)
            exact(reply, ("result",))
            result = validate_local(reply["result"], cid)
            reason = None
            decision = result["decision"]
            if decision["high_risk"] or decision["category"] == "security" or decision["priority"] in ("p0", "p1"):
                reason = "high_risk"
            elif any(max(values.values()) < minimum for values in result["probabilities"].values()):
                reason = "low_confidence"
            return observation(
                cid, "local_judge", decision=decision, reason=reason,
                probabilities=result["probabilities"], latency_ms=result["latency_ms"],
                measurements={key: result[key] for key in (
                    "field_latency_ms", "cache_prompt", "cache_tokens", "probability_kind")},
            )
        except Invalid as error:
            reason = str(error)
        except (ValueError, TypeError):
            reason = "invalid_config"
        except Exception:
            reason = "unavailable"
        return observation(cid, "local_judge", reason=reason,
                           latency_ms=round((time.monotonic() - started) * 1000, 3))


class JevProvider:
    """Adapt the validated legacy JEV audit without changing its wire or CLI contract."""

    def __init__(self, records):
        self.records = records

    def observe(self, review):
        cid = review["comment_id"]
        raw = self.records.get(cid)
        if raw is None:
            return observation(cid, "jev", reason="unconfigured")
        try:
            if (raw.get("comment_id") != cid or raw.get("model") != "typesafe/jev"
                    or raw.get("authoritative") is not False
                    or raw.get("effective_disposition_source") != "baseline"):
                raise Invalid("malformed_response")
            if raw.get("mode") != "shadow":
                return observation(cid, "jev", reason="non_shadow_response")
            fallback_required = raw.get("fallback_required")
            fallback_reason = raw.get("fallback_reason")
            if (type(fallback_required) is not bool or not valid_reason(fallback_reason)
                    or fallback_required != (fallback_reason is not None)):
                raise Invalid("malformed_response")
            if raw.get("decision") not in ("action_required", "no_action"):
                return observation(cid, "jev", reason=fallback_reason or "jev_fallback")
            decision = {field: raw.get(field) for field in OPTIONS if field != "needs_action"}
            decision["needs_action"] = raw["decision"] == "action_required"
            validate_decision(decision)
            if not number(raw.get("confidence"), 1) or not number(raw.get("latency_ms")):
                raise Invalid("malformed_response")
            reason = (fallback_reason or "jev_fallback") if fallback_required else None
            return observation(cid, "jev", decision=decision, reason=reason,
                               confidence=raw["confidence"], latency_ms=raw["latency_ms"])
        except Exception:
            return observation(cid, "jev", reason="malformed_response")


class BaselineProvider:
    def __init__(self, records):
        self.records = records

    def observe(self, review):
        cid = review["comment_id"]
        decision = self.records.get(cid)
        try:
            validate_decision(decision)
        except Exception:
            return observation(cid, "baseline", reason="baseline_unavailable")
        return observation(cid, "baseline", decision=decision)
