import { runDecisionLayer } from "./decision-layer.mjs";

const MAX_REQUEST_BYTES = 64 * 1024;
const AUTH_SCHEME = "Bearer ";
const CLIENT_INPUT_FALLBACKS = new Set([
  "invalid_comment",
  "invalid_comment_id",
  "invalid_body",
  "invalid_existing_decision",
  "comment_too_large",
]);
const encoder = new TextEncoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function resultStatus(result) {
  if (result.final_result !== "fallback") return 200;
  if (CLIENT_INPUT_FALLBACKS.has(result.fallback_reason)) {
    return 400;
  }
  return 502;
}

async function hasValidSharedSecret(request, env) {
  const expected = env.TRIAGE_SHARED_SECRET;
  if (typeof expected !== "string" || expected.length === 0) return null;

  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith(AUTH_SCHEME)) return false;

  const presented = authorization.slice(AUTH_SCHEME.length);
  const [expectedDigest, presentedDigest] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
    crypto.subtle.digest("SHA-256", encoder.encode(presented)),
  ]);
  const expectedBytes = new Uint8Array(expectedDigest);
  const presentedBytes = new Uint8Array(presentedDigest);
  let difference = expectedBytes.length ^ presentedBytes.length;
  for (let index = 0; index < expectedBytes.length; index += 1) {
    difference |= expectedBytes[index] ^ presentedBytes[index];
  }
  return difference === 0;
}

async function readBoundedJson(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error("missing_body");

  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_REQUEST_BYTES) throw new Error("request_too_large");
    chunks.push(value);
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/triage") {
      return json({ error: "not_found" }, 404);
    }

    const authorized = await hasValidSharedSecret(request, env);
    if (authorized === null) return json({ error: "auth_not_configured" }, 503);
    if (!authorized) return json({ error: "unauthorized" }, 401);

    let input;
    try {
      input = await readBoundedJson(request);
    } catch (error) {
      const reason = error instanceof SyntaxError ? "invalid_json" : error.message;
      return json({ error: reason || "invalid_request" }, 400);
    }

    const mode = env.TRIAGE_MODE === "limited_automation" ? "limited_automation" : "shadow";
    const rawMinConfidence = env.MIN_CONFIDENCE;
    const minConfidence = rawMinConfidence === undefined
      ? null
      : typeof rawMinConfidence === "string" && rawMinConfidence.trim() === ""
        ? Number.NaN
        : Number(rawMinConfidence);
    const result = await runDecisionLayer({ env, input, mode, minConfidence });
    return json({ result }, resultStatus(result));
  },
};
