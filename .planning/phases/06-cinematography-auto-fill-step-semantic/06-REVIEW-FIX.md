---
phase: 06-cinematography-auto-fill-step-semantic
fixed_at: 2026-07-25T00:00:00Z
review_path: .planning/phases/06-cinematography-auto-fill-step-semantic/06-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-07-25
**Source review:** `06-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (critical + warning): 8
- Fixed: 8
- Skipped: 0
- Info findings (4): out of scope (default fix_scope = critical_warning); IN-01 closed
  as a side effect of WR-03 (ROUTE_PATH constant DRYs the 3 hardcoded literals).

Both BLOCKERs were empirically reproduced before fixing (CR-01: stale-cache + offline →
empty facets + zero warnings; CR-02: 200-with-HTML body → uncaught JSONDecodeError →
exit 1 traceback). Both reproductions are now closed and locked behind a permanent
harness regression guard (WR-06).

## Fixed Issues

### CR-01: Stale-cache + offline silently degrades prompts to empty facets (violates Pitfall 4)

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `c5cfa12`
**Applied fix:** Tracked a `cache_stale` flag during cache lookup (file present but
`_cache_key` mismatches) and rewrote the `route_down` warning logic to distinguish
"file absent" from "stale-but-present". Both offline miss paths now emit a warning
(stale-cache → `offline/stale-cache (_cache_key mismatch)`; absent → `offline/cache-miss`).
The operator can no longer receive a schema-valid but content-degraded `prompts.json`
with zero warnings.
**Reproduction closed:** pre-fill cache with wrong hash → `--offline` → empty camera AND
warnings sidecar non-empty (`shot 1: offline/stale-cache (_cache_key mismatch) → empty facets`).

### CR-02: `call_route` / `compose_facets` raise uncaught tracebacks on malformed route responses

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `912a8d0`
**Applied fix:** In `call_route`, wrapped `resp.json()` in an inner `except ValueError`
(non-JSON 200 body), added `isinstance(payload, dict)` + `isinstance(data, dict)` guards,
and broadened the outer `except` to `(httpx.HTTPError, ValueError, AttributeError,
TypeError, KeyError)` → all malformed responses degrade to `(None, error_msg)`. In
`compose_facets`, replaced `route_shot.get("semantic") or {}` with typed `isinstance`
guards and added a top-level `isinstance(route_shot, dict)` guard so a non-dict truthy
shot also degrades cleanly. The pipeline never aborts on a malformed route response.
**Reproduction closed:** 200-with-HTML → exit 0 + empty facets + warning
(`route returned non-JSON body: JSONDecodeError: ...`), no traceback; non-dict envelope
→ exit 0 + empty facets + warning (`route envelope not a dict: list`); non-dict
`semantic` → no AttributeError (graceful tolerance, matching the REVIEW's literal fix).

### WR-01: `step_semantic` mtime cache ignores video identity and `ROUTE_VERSION`

**Files modified:** `run_pipeline.py`
**Commit:** `de0d5b4`
**Applied fix:** Mirrored `step_export`'s `asset.json.video-stamp` pattern: after a
successful `call_shot_analysis.py` run, `step_semantic` writes
`prompts.json.video-stamp` containing `_video_identity(video)` (path|size|mtime_ns);
the cache-hit check now also requires the stamp to match the current video identity.
A video swap (same/older mtime, e.g. backup restore / `cp --preserve=timestamps`)
now forces a re-run. Added `prompts.json.video-stamp` to the `--force` cleanup list.
**Verified:** matching stamp → cache hit; swapped video → cache miss → re-run.
**Residual (documented):** a pure `ROUTE_VERSION` bump without a video/shots change
still requires `--force` to re-run `step_semantic` (consistent with the documented
cache-invalidation knob; the per-shot cache auto-invalidates once the step re-runs).
Cross-module importing `ROUTE_VERSION` into `run_pipeline` was rejected to preserve
the "stages invoked by path, not imported" convention (CLAUDE.md).

### WR-02: `import httpx` is unconditional even in `--offline` mode

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `9842725`
**Applied fix:** Converted the `with httpx.Client(...) as client:` block to a
conditional client (`client = None; if not args.offline: import httpx; client = ...`)
wrapped in `try/finally` (closes only when non-None). The per-shot loop still runs in
offline mode (reads cache + writes prompts); `call_route` is only invoked on the
`not route_down` branch, so `client=None` is never touched on the network path.
**Verified:** `--offline` + valid cache → cache hit + correct camera + exit 0, with
httpx made *unimportable* via a `sitecustomize.py` shim (simulates uninstalled).

### WR-03: `--analysis-url` path component beyond `/api/v1` is silently dropped

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `fe59c53`
**Applied fix:** Introduced module constant `ROUTE_PATH = "/api/v1/production/shot-analysis"`
(CONTEXT lock). The main client now strips `base_url` to the host root
(`args.analysis_url.rsplit("/api/v1", 1)[0]`) — matching what `preflight` already did —
and both `call_route.post(ROUTE_PATH)` and `preflight.get(ROUTE_PATH)` use the constant.
This removes the silent discrepancy (main used full URL as base, preflight stripped) and
the RFC-3986 absolute-path-replace surprise. Also closes **IN-01** (the hardcoded string
is now a single source instead of 3 scattered literals).
**Verified:** exactly 1 hardcoded path literal remains (the constant); both preflight and
main strip at `/api/v1`; route-down still degrades correctly.

### WR-04: `_cache_key` comparison omits `route_name` despite documented key

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `3930fe6`
**Applied fix:** Added `and ck.get("route_name") == ROUTE_NAME` to the cache-key
comparison so the full documented 4-tuple
`(video_content_hash, route_name, route_version)` is enforced (shot_id is encoded in the
filename). Latent bug closed for any future second route cached under the same
`route_cache/` tree.
**Verified:** matching `route_name` → cache hit; mismatched `route_name` → stale miss +
warning.

### WR-05: `--analysis-url` embedded credentials may leak into `asset.json.warnings`

**Files modified:** `analysis/call_shot_analysis.py`
**Commit:** `375d647`
**Applied fix:** Added module-level `_safe_error(msg)` helper
(`re.sub(r"(https?://)([^@/]+@)", r"\1***@", msg)`) and routed all error-return strings
in `call_route` (non-JSON body, non-dict envelope, code≠200, broadened except) and
`preflight` through it. Defense-in-depth against credential leak if a URL carries
`user:pass@` (schema forbids auth tokens in `generator.warnings`).
**Verified:** `_safe_error` unit-tested (scrubs `http://user:pass@host` → `http://***@host`,
no-op when no URL); integration run with `http://alice:s3cr3t@127.0.0.1:1/...` → no
credentials, username, or password appear in the warnings sidecar.

### WR-06: `verify_phase6_smoke.py` does not cover the stale-cache + offline scenario

**Files modified:** `scripts/verify_phase6_smoke.py`
**Commit:** `0814db9`
**Applied fix:** Added a 4th scenario `scenario_stale_cache_offline` that pre-seeds the
cache with a wrong `video_content_hash` + `--offline`, then asserts: exit 0, all
route-sourced facets empty (degraded), schema-valid, and warnings ≥ 1 containing
"stale-cache". Registered in `main()` scenarios list; updated module docstring + argparse
description (3 → 4 scenarios). This is the permanent CR-01 regression guard — the exact
harness gap that let CR-01 ship under "3/3 green".
**Verified:** harness now reports `4/4 scenarios green`.

## Skipped Issues

None — all 8 in-scope findings were fixed.

## Out-of-scope (Info) Notes

- **IN-01** (hardcoded route path duplicated): closed as a side effect of WR-03
  (`ROUTE_PATH` constant — single source).
- **IN-02** (`s["id"]` KeyError guard), **IN-03** (docstring wording), **IN-04**
  (`>` vs `>=` mtime): out of scope (Info tier); left as-is. IN-04 explicitly noted by
  the reviewer as "leave as-is" (consistent with `step_export` convention).

## Gate Results (all green)

| Gate | Command | Result |
|---|---|---|
| 1 | `python3 scripts/verify_phase6_smoke.py` | `4/4 scenarios green` (exit 0) |
| 2 | `python3 spec/validate.py` | `minimal failures=0, v1.1 failures=0, smoke failures=0` (exit 0) |
| 3 | `PHASE4_ASSET_DIR=<ep01> python3 scripts/verify_contract.py --mode=producer` | `OK producer` (exit 0) |
| 4 | `PHASE4_ASSET_DIR=<ep01> PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | `OK self-test` + `OK producer` (exit 0) |

Gates 3-4 require `PHASE4_ASSET_DIR` because a fresh review-fix worktree has no
`output/` artifacts (gitignored); pointed at the existing ep01 asset they pass green.
These gates exercise the asset schema/export/contract surface, which these fixes do not
touch (only `analysis/call_shot_analysis.py`, `run_pipeline.py:step_semantic`, and the
Phase 6 harness were modified).

## Blocker Reproduction Confirmation

- **CR-01** (pre-fix: empty camera + 0 warnings): **CLOSED** — now exit 0, empty camera
  (degraded), 1 warning `shot 1: offline/stale-cache (_cache_key mismatch) → empty facets`.
- **CR-02** (pre-fix: uncaught `JSONDecodeError` traceback, exit 1): **CLOSED** — now
  exit 0, empty facets, 1 warning `route returned non-JSON body: ...`, no traceback;
  non-dict envelope and non-dict `semantic`/`geometry` also degrade cleanly.

---

_Fixed: 2026-07-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
