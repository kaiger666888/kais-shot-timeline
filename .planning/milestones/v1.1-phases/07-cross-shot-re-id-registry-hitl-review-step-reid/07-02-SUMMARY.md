---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
plan: 02
subsystem: producer
tags: [httpx, reid, character-reid, registry-draft, graceful-degrade, per-video-cache, normalize-clusters, cast-05, cast-09]

# Dependency graph
requires:
  - phase: 05-contract-v1.1
    provides: registry.schema.json — the frozen output shape call_reid.py normalizes INTO (Draft202012Validator pre-write self-check)
  - phase: 06-shot-analysis-route-step-semantic
    provides: analysis/call_shot_analysis.py — the DIRECT template mirrored verbatim (httpx client + video_content_hash + _safe_error + preflight + graceful-degrade pattern + lazy httpx import + URL scrubbing)
provides:
  - analysis/call_reid.py — httpx sync client + normalize_clusters + _tier_for + per-video cache + preflight + graceful-degrade; produces registry.draft.json (CAST-05) and degrades gracefully on route-down (CAST-09 component-level)
affects: [07-03, 07-04, phase-08-prompt-reference]

# Tech tracking
tech-stack:
  added: []  # zero new deps — httpx 0.28.1 already verified in Phase 6
  patterns:
    - "Shape-agnostic projector: normalize_clusters projects whatever the (deferred) route emits onto registry.schema.json#clusters[] allowed fields only — drops centroid_embedding/mask_bbox/etc (additionalProperties:false defense)"
    - "Per-video cache granularity for cross-shot aggregation (route_cache/character_reid/video_<vch>.json) — distinct from Phase 6's per-shot cache (Pitfall 4 prevention)"
    - "Non-destructive warnings sidecar merge: READ existing step_semantic warnings → APPEND re-id warnings → WRITE merged list (does NOT overwrite Phase 6 warnings)"
    - "Broadened graceful-degrade except clause (httpx.HTTPError + ValueError + AttributeError + TypeError + KeyError) — never tracebacks into step_reid (CR-02 pattern from Phase 6)"
    - "Three-tier advisory classification (_tier_for ≥0.85/0.6/<0.6) — tier is authoritative label, mean_cosine is advisory number (calibration deferred per CONTEXT Q2)"

key-files:
  created:
    - analysis/call_reid.py
  modified: []

key-decisions:
  - "normalize_clusters is the explicit CAST-05 projection: every cluster gets review_state='proposed' (producer NEVER emits confirmed/rejected); extra route fields dropped pre-schema-validation"
  - "Cache is per-video (video_<vch>.json), NOT per-shot — re-id is cross-shot aggregation, per-shot cache would store incomplete intermediate state (Pitfall 4)"
  - "Warnings sidecar is READ-merge-write (non-destructive): step_semantic warnings from Phase 6 are preserved; re-id warnings appended after"
  - "call_route returns the WHOLE data dict (not shots[0] like Phase 6) — re-id returns data.clusters as a list; normalize_clusters extracts .get('clusters')"
  - "ROUTE_VERSION='deferred-character-reid-route-v1' is the cache-invalidation knob — bump post-merge to invalidate all stale caches"

patterns-established:
  - "Second httpx network-dependency sibling (call_reid.py mirrors call_shot_analysis.py) — proves the thin-client + graceful-degrade pattern generalizes across routes"
  - "Non-destructive sidecar merge pattern: multiple route-calling steps (semantic + reid) can coexist in route_cache/warnings.json without overwriting each other"

requirements-completed: []  # CAST-05 + CAST-09 are SPLIT across plans 02 (component) + 04 (step integration). NOT marked complete until Plan 04 ships step_reid + flag wiring.

# Metrics
duration: 4min
completed: 2026-07-24
---

# Phase 7 Plan 02: Cross-Shot Re-ID Route Client (call_reid.py) Summary

**httpx sync client mirroring Phase 6's call_shot_analysis.py — calls the DEFERRED character-reid route once per video (cross-shot aggregation), normalizes the response into registry.draft.json via shape-agnostic projection (CAST-05: all clusters review_state='proposed'), with per-video cache, single preflight probe, broadened graceful-degrade except, and non-destructive warnings sidecar merge**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-24T18:23:37Z
- **Completed:** 2026-07-24T18:27:41Z
- **Tasks:** 1
- **Files modified:** 1 (1 created)

## Accomplishments
- Created `analysis/call_reid.py` (~420 LOC) — the producer-side httpx client for the (DEFERRED cross-repo) `POST /api/v1/production/character-reid` route. Mirrors `analysis/call_shot_analysis.py` (Phase 6) structure verbatim with four substantive differences: (a) constants (ROUTE_NAME/ROUTE_VERSION/ROUTE_PATH); (b) per-video cache instead of per-shot loop; (c) `normalize_clusters()` replaces `compose_facets()`; (d) output is `registry.draft.json` validated against `registry.schema.json`.
- Implemented `normalize_clusters()` as the CAST-05 shape-agnostic projector: takes route `data` dict, extracts `.clusters[]`, projects each onto registry.schema.json#clusters[] allowed fields only (cluster_id/review_state="proposed"/tier/mean_cosine/members), drops extra route fields (centroid_embedding/mask_bbox — schema additionalProperties:false would reject), skips clusters with empty members (schema minItems:1), defaults mean_cosine to 0.0 when non-numeric.
- Implemented `_tier_for()` with CONTEXT Q2 locked three-tier advisory defaults: auto_merge ≥0.85 / review 0.6-0.85 / auto_distinct <0.6 (non-numeric → review). tier is authoritative label; mean_cosine is advisory number.
- Verified graceful-degrade end-to-end: unreachable route URL → registry.draft.json with clusters:[] + 2 warnings (preflight msg + offline/cache-miss msg), exit 0, asset still exports.
- Verified cache-hit offline path: pre-seeded per-video cache → `--offline` short-circuits before preflight → 0 httpx POST calls → draft uses 3 cached fixture clusters → stdout contains "cache hit".
- Verified non-destructive warnings sidecar merge: pre-seeded step_semantic warnings preserved + re-id warnings appended (2+2=4 total), read-merge-write pattern confirmed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create analysis/call_reid.py** - `270058c` (feat)

## Files Created/Modified
- `analysis/call_reid.py` - Self-contained CLI stage (sibling of call_shot_analysis.py). Module-level constants (ROUTE_NAME/ROUTE_VERSION/ROUTE_PATH/REGISTRY_SCHEMA). Functions: `video_content_hash` (reused verbatim), `_safe_error` (reused verbatim, WR-05 URL scrubbing), `_tier_for` (CONTEXT Q2 three-tier), `normalize_clusters` (CAST-05 projection with extra-field drop + empty-member skip), `call_route` (httpx POST with broadened except, returns whole data dict), `preflight` (single short-circuit probe), `main` (per-video cache + single POST + normalize + Draft202012Validator pre-write + atomic write + warnings sidecar READ-merge-write). Chinese module docstring (purpose + route contract + output schema + CLI usage + graceful-degrade). Lazy httpx import (WR-02). `if __name__ == "__main__": sys.exit(main())`.

## Decisions Made
- **normalize_clusters is defensive throughout:** isinstance checks on every level (route_data dict, clusters list, each cluster dict, each member dict, shot_id int). Non-conforming entries are silently skipped (defense-in-depth) — the pre-write Draft202012Validator catches any remaining schema violations fails-loud.
- **mask_quality is conditionally included:** only added to projected member when the route provides it (schema optional). This keeps the projection minimal while preserving signal when available.
- **call_route returns the whole `data` dict** (not `shots[0]` like Phase 6): re-id returns `data.clusters` as a list; normalize_clusters handles the extraction. This is the key structural difference from the per-shot shot-analysis client.
- **Two warnings on route-down degrade:** the preflight failure msg (containing "preflight" + "ConnectError") AND the generic "character-reid: offline/cache-miss → empty draft" msg (Pitfall 4 non-silent degrade). Both are intentional — the first explains why the route is unreachable, the second explains the consequence (empty draft).

## Deviations from Plan

None - plan executed exactly as written. All 10+ behavior rows pass via inline checks; route-down degrade verified end-to-end; cache-hit offline verified; non-destructive warnings merge verified.

## Issues Encountered
None — the module passed all three automated verify blocks (behavior contracts + route-down degrade + cache-hit offline) on the first pass, plus the additional acceptance greps, schema regression, producer contract verification, and explicit non-destructive merge test.

## User Setup Required
None - no external service configuration required. httpx 0.28.1 is already in the active Python env (verified Phase 6). The character-reid ROUTE is DEFERRED cross-repo (does not exist today); graceful-degrade is fully testable without it (route-down → empty draft + warnings sidecar, verified end-to-end).

## Known Stubs
None. `call_reid.py` is fully functional for the producer-side role. The DEFERRED character-reid route (kais-aigc-platform cross-repo) is not a stub in this repo — it is an explicitly deferred cross-repo dependency documented in CONTEXT/RESEARCH/STATE. When the route ships, `call_reid.py` will call it without modification (shape-agnostic projector handles whatever shape the route emits).

## Next Phase Readiness
- **CAST-05 (component) + CAST-09 (component) are implemented.** Plan 04 closes CAST-09 step integration (`run_pipeline.py:step_reid` slot 6 of 8 + `[N/7]`→`[N/8]` counter + 4 flags + `--force` cache list).
- **registry.draft.json producer is ready.** Plan 03 (`html/gen_registry_review.py`) can consume the draft shape immediately (frozen in Phase 5 fixture set, produced identically by call_reid.py).
- **No blockers.** The module is fully testable in graceful-degrade mode (route not running). Live round-trip deferred to post-merge smoke test (mirrors Phase 6 deferral).

## Threat Mitigations Verified
- **T-07-04 (SSRF via --reid-url):** CLI flag, not runtime user input. httpx validates URL syntax. Default localhost. ✓
- **T-07-05 (DoS / route hang):** Preflight short-circuits on first ConnectError. `--reid-timeout` 960s upper bound. Per-video failure non-fatal (degrade to empty draft). ✓
- **T-07-06 (cache poisoning):** `_cache_key` checks (video_content_hash, route_name, route_version). Mismatch → miss. ✓
- **T-07-07 (info disclosure via warnings):** `_safe_error` scrubs URL userinfo (WR-05). Verified: `user:pass@` → `***@`. ✓
- **T-07-08 (spoofing / malformed 200):** `call_route` checks code==200 + isinstance(data, dict). `normalize_clusters` isinstance throughout. Malformed → empty clusters. ✓
- **T-07-09 (overwriting step_semantic warnings):** READ-merge-write verified end-to-end (2 pre-existing + 2 re-id = 4 preserved). ✓

---
*Phase: 07-cross-shot-re-id-registry-hitl-review-step-reid*
*Completed: 2026-07-24*

## Self-Check: PASSED

- Files: `analysis/call_reid.py` FOUND
- Commits: `270058c` FOUND
- Clean import: `from analysis.call_reid import normalize_clusters, _tier_for, video_content_hash, call_route, preflight, main, ROUTE_VERSION, ROUTE_NAME, ROUTE_PATH` exits 0
- Behavior contracts: all 10+ rows green (constants + _tier_for boundaries + normalize_clusters projection + edge cases + video_content_hash determinism/content-sensitivity + _safe_error scrubbing)
- Route-down degrade: exit 0 + empty clusters + 2 warnings (verified)
- Cache-hit offline: 3 cached clusters reused + "cache hit" in stdout + 0 network calls (verified)
- Non-destructive merge: 2 step_semantic + 2 re-id warnings preserved (verified)
- `python3 spec/validate.py` exits 0 (10 v1.1 + 6 minimal green — no schema regression)
- `python3 scripts/verify_contract.py --mode=producer` exits 0 (no regression)
