---
name: event-status-counts
description: Validate bounded JSON event lists and count ok/failed events by category through the trusted adapter, or route requests for this exact capability.
---

# Event status counts

Use this skill only for `event-status-counts`: counting duplicate events separately by category and status, or selecting whether this capability should be created or reused.

## Authority and boundaries

Use the session's trusted `read` transport to obtain this skill, the supplied tasks, `allowed_operations`, and concrete transport instructions. Routing tasks supply a catalog; execution tasks supply input JSON and the actual stdin bytes and hash. Use those supplied materials and the contract stated in this skill; there is no separate contract-file or script-source retrieval step. For each supplied task, use only its allowed operations and the concrete transport instructions; do not invent a command or transport syntax. If transport or required evidence is missing, hold for evidence through a permitted routing operation when available. Missing authorization requires a permission hold; do not suggest bypassing permissions.

Do not fetch external content, install dependencies, access authentication or production, install a skill globally, or modify policies or evaluators. Never execute or import the bundled Python on the host. Python execution is permitted only through `run_aggregate` in the trusted fixed Docker adapter using Python 3.12 and its standard library.

## Route a capability request

Use the supplied catalog's completeness, capability descriptions, and explicit creation permission:

1. If the evidence is incomplete or does not establish equivalence or its absence, choose `hold_evidence`.
2. If an existing skill provides this exact capability and input/output contract, choose `select_reuse` and identify that skill from the catalog. Do not create an unnecessary replacement.
3. If the complete catalog establishes no equivalent skill and creation is authorized, choose `select_create`.
4. If no equivalent exists but creation permission is absent, choose `hold_permission`.

Invoke the chosen permitted routing operation through the supplied `use` transport to record the selection. That operation completes the routing task; do not call `respond` for routing. A routing selection never writes or installs a skill.

## Execute aggregation

Invoke the permitted `run_aggregate` operation using the session's trusted `use` transport. The trusted fixed Docker adapter executes the bundled `scripts/aggregate.py`; do not request or submit script source through another entry point. Use the execution task's supplied stdin bytes and hash as directed by its transport. Preserve the input bytes; do not repair, coerce, trim, or replace invalid input. The displayed input JSON is context, not a replacement for the actual stdin bytes.

The script accepts at most 16384 stdin bytes, strictly decoded as UTF-8 JSON. The root has exactly `events`, an array of objects with exactly `category` and `status`. Category matches `[a-z0-9]{1,16}` and status is `ok` or `failed`. Duplicate JSON keys and non-JSON numeric constants are rejected. Duplicate events count separately. Each observed category has both integer counters; empty events yields an empty counts object.

Inspect the adapter's actual exit status, stdout, and stderr:

- Exit 0 and empty stderr indicate success. Return the actual stdout unchanged through `respond`, including its trailing newline.
- Exit 2, empty stderr, and stdout `{"error":"INVALID_INPUT"}` plus a trailing newline are the expected validation result. Return that actual stdout unchanged through `respond`; do not classify it as infrastructure failure.
- Missing execution evidence, unavailable adapter, unexpected exit code, stderr, or a result inconsistent with the contract is not success. Report the execution failure or hold for evidence through the supplied transport without using `respond` to manufacture an execution result; `respond` is reserved for final return of actual `run_aggregate` stdout. Never manufacture counts, silently substitute an empty result, or claim execution without actual stdout.

Do not calculate a replacement answer mentally or reconstruct the stdout from parsed JSON. The final execution response must be the exact bytes of the adapter's actual stdout.
