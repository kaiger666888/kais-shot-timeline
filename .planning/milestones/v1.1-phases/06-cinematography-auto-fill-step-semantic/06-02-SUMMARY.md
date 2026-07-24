---
phase: 06-cinematography-auto-fill-step-semantic
plan: 02
subsystem: api
tags: [httpx, cinematography, prompts, graceful-degrade, cache, shot-analysis-route]

# Dependency graph
requires:
  - phase: 06-cinematography-auto-fill-step-semantic (Plan 01)
    provides: asset.schema.json#generator.warnings (optional array<string>) + export_asset.py build_asset_dict(warnings=None) + the route_cache/warnings.json sidecar shape contract {"warnings": [...]} that this plan writes.
provides:
  - "analysis/call_shot_analysis.py — self-contained CLI stage: httpx sync client + compose_facets (LOCKED route→prompts mapping) + video_content_hash + per-shot cache + single preflight + warnings sidecar + Draft202012Validator pre-write self-check + atomic prompts.json write"
  - "examples/shot_analysis/shot_001..007.json — repo-local copy of the 7 captured route fixtures (the CINEMA-01 mapping correctness oracle; survives without /mnt/agents/)"
  - "CLI contract consumed by Plan 03's run_pipeline.step_semantic subprocess call (--video/--shots/--work-dir/--output/--analysis-url/--analysis-timeout/--offline)"
affects: [06-03 (run_pipeline step_semantic integration + verify_phase6_smoke.py), Phase 7 (step_reid mirrors the cache+preflight+degrade pattern), Phase 8 (prompt_text recomposition consumes the facets this plan fills)]

# Tech tracking
tech-stack:
  added: ["httpx 0.28.1 (already in-env; now documented in README install line — first network dep in the project)"]
  patterns:
    - "Per-shot cache with content-hash key: (video_content_hash, route_name, route_version) — head+tail 1MB sha256 avoids full-read of multi-GB videos"
    - "Graceful-degrade via httpx.HTTPError root catch-all: ConnectError/Timeout/HTTPStatusError/NetworkError all → empty-string facets + warnings sidecar"
    - "Single preflight short-circuit: one probe before the loop, failure sets route_down=True, no per-shot retry storm"
    - "Namespace-package flat directory (NO __init__.py) — analysis/ mirrors scripts/; imported via sys.path, CLAUDE.md-compliant"
    - "Pre-write schema self-validation (Draft202012Validator) — fails loud on broken mapping before prompts.json lands"

key-files:
  created:
    - "analysis/call_shot_analysis.py (httpx client + mapping + cache + preflight + main, ~330 LOC)"
    - "examples/shot_analysis/shot_001.json .. shot_007.json (7 captured fixtures, verbatim copies)"
  modified:
    - "README.md (install line += httpx)"

key-decisions:
  - "LOCKED route→prompts mapping (CONTEXT D-XX): camera=join(shot_scale, camera_primitive, camera_speed, geometry.primitive) filtering falsy; action=subject_motion; lighting=lighting; style=lens_feel; subject='' + scene='' never fabricated. Verified against all 7 captured fixtures → 0 schema errors + exact match to RESEARCH Example 3 oracle table."
  - "compose_facets(None) handles graceful-degrade internally (returns all-empty facets) — cleaner than the research skeleton's `if route_shot else {...}` guard at the call site."
  - "merge_prompts.py MERGE deferral (documented deviation in PLAN objective): step_semantic writes prompts.json from route facets only (prompt_text='', subject='') because merge_prompts.py is currently external/manual, not wired into run_pipeline — no part_*.json exists during a pipeline run. When merge_prompts.py is later wired in, extend the compose step to pre-load part_*.json as base."
  - "ROUTE_VERSION='feat-shot-analysis-route-v1' hardcoded as module-level constant (route response has no version field to auto-probe); bump invalidates all caches."
  - "--offline reads cache (network suppressed only); --skip-semantic skips the whole step (handled by Plan 03 run_pipeline, not here)."

patterns-established:
  - "Pattern: httpx.Client with httpx.Timeout(connect=5, read=960, write=5, pool=5) — read 960s deliberately > route-side 900s execFileSync ceiling so the route self-kills first and the client gets a definite 500 to degrade on."
  - "Pattern: per-shot POST body always {semantic:true, subject:false, shot_id_range:[N,N]} (CONTEXT lock — semantic:true is load-bearing for the mapping)."
  - "Pattern: cache file embeds _cache_key {video_content_hash, route_name, route_version}; mismatch (stale) → treated as miss, not poisoned (Pitfall 5)."

requirements-completed: [CINEMA-01, CINEMA-03, CINEMA-04, CINEMA-05]

# Metrics
duration: 11min
completed: 2026-07-24
---

# Phase 6 Plan 02: Cinematography Analysis Client Summary

**httpx sync client calling kais-aigc-platform `shot-analysis` route, mapping geometry+semantic into prompts.json facets with content-hash per-shot cache, single preflight short-circuit, and graceful-degrade to schema-valid empty facets when the route is down**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-07-24T14:56:45Z
- **Completed:** 2026-07-24T15:07:33Z
- **Tasks:** 2 (both auto; Task 1 tdd=true)
- **Files modified:** 9 (1 new module + 7 fixture copies + 1 README edit)

## Accomplishments
- `analysis/call_shot_analysis.py` — the project's first network dependency. Implements compose_facets (LOCKED mapping), video_content_hash (head+tail 1MB sha256), call_route (httpx.HTTPError catch-all), preflight (single short-circuit), and main() (preflight → cache lookup → per-shot POST → compose → Draft202012Validator self-check → atomic write → warnings sidecar).
- The CINEMA-01 mapping correctness oracle is now repo-local: 7 captured route fixtures copied verbatim into `examples/shot_analysis/`; compose_facets over all 7 yields 0 Draft202012Validator errors and matches the RESEARCH Example 3 oracle table exactly (incl. null/empty boundaries: shot_002 shot_scale=null, shot_005 subject_motion="", shot_007 subject_motion=null — no "None" literal, no leading ", ").
- Graceful-degrade verified end-to-end against a route-down scenario (bad --analysis-url): preflight ConnectError → route_down → all-empty facets + 3-entry warnings sidecar + schema-valid prompts.json + exit 0. Cache-hit verified: --offline + pre-seeded cache → 0 httpx post calls + cached camera value used.
- No regression: `python3 spec/validate.py` exit 0; `python3 scripts/verify_contract.py --mode=producer` exit 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: analysis/call_shot_analysis.py (httpx client + mapping + cache + preflight + main) + README httpx note** - `a1b7904` (feat)
2. **Task 2: copy 7 captured fixtures into examples/shot_analysis/** - `c9103fe` (docs)

## Files Created/Modified
- `analysis/call_shot_analysis.py` — httpx sync client stage. ROUTE_NAME/ROUTE_VERSION constants, video_content_hash, compose_facets (LOCKED mapping), call_route (HTTPError catch), preflight (single probe), main() CLI (argparse + preflight + cache loop + schema self-validate + atomic write + warnings sidecar). NO `analysis/__init__.py` (namespace package, CLAUDE.md-compliant).
- `examples/shot_analysis/shot_001.json` .. `shot_007.json` — verbatim copies of `/mnt/agents/output/gpu1/shot_analysis/`; the offline mapping oracle.
- `README.md` — install line += `httpx` (with note: Phase 6 uses 0.28.1, already in-env).

## Decisions Made
- **compose_facets(None) internal handling** — the LOCKED mapping function itself returns all-empty facets when route_shot is None, rather than guarding at the call site. Cleaner and directly satisfies the `compose_facets(None) → all 6 facets ""` behavior row.
- **Lazy httpx import inside call_route/preflight/main-client-open** — mirrors `audio/transcribe.py`'s optional-dep lazy-import convention; lets the argparse + cache-read paths work for `--offline` even if httpx were somehow absent.
- All other decisions followed CONTEXT D-XX LOCKED mapping + the PLAN action section verbatim.

## Deviations from Plan

None - plan executed exactly as written.

(The research Example 1 skeleton contained a `warnings sidecar path = ...` line that is invalid Python syntax; this was recognized as a skeleton typo and implemented correctly as `warnings_sidecar = ...`. Not a deviation from plan intent — the PLAN `<action>` step 6.2 already specified the correct `warnings_sidecar` name.)

## TDD Gate Compliance

Task 1 was `tdd="true"`. Per VALIDATION.md (status: approved, 2026-07-24) the project is **pytest-free** (CLAUDE.md + v1.0 RETROSPECTIVE: "no test framework; standalone `sys.exit(0/1)` scripts"). The PLAN `<action>` explicitly states: "Inline assertions during development (a `python3 -c "..."` one-liner per behavior row) are the test loop; the formal regression harness lives in Plan 03 Task 2 (`scripts/verify_phase6_smoke.py`)."

- **RED gate:** satisfied by the absent module — `import analysis.call_shot_analysis` raised `ModuleNotFoundError` before implementation (confirmed at execution start). All 10 behavior rows were unsatisfiable.
- **GREEN gate:** satisfied by `a1b7904` — the Task 1 `<verify><automated>` block printed `OK: Task 1 behavior contracts green`, plus the 3 extended behavior rows (call_route unreachable, route-down main, offline cache-hit 0-posts) all pass.
- **REFACTOR gate:** no refactor needed; code is clean.

Because there is no committed test artifact (inline `python3 -c` is the test loop and the project forbids test files), the RED and GREEN gates collapse into a single `feat(06-02)` commit. This honors the TDD test-first verification spirit while respecting the project's no-test-files convention. The formal regression harness (`scripts/verify_phase6_smoke.py`) is owned by Plan 03.

## Issues Encountered
None.

## User Setup Required

None for execution — httpx 0.28.1 is already in the active Python env (verified: `python3 -c "import httpx; print(httpx.__version__)"` → `0.28.1`). The PLAN frontmatter `user_setup` precondition documents the package-legitimacy audit path for a fresh environment (human MUST verify https://pypi.org/project/httpx/ before `pip install "httpx==0.28.1"`), but no install runs in this plan.

Live route round-trip is DEFERRED per STATE.md blocker (kais-aigc-platform `feat/shot-analysis-route` unmerged) — mapping + graceful-degrade + cache are all verified offline against captured fixtures + route-down. The live round-trip becomes a post-merge smoke test.

## Next Phase Readiness
- **Plan 06-03 unblocked.** This plan delivers the exact CLI contract (`--video/--shots/--work-dir/--output/--analysis-url/--analysis-timeout/--offline`) that `run_pipeline.step_semantic` will subprocess-call, plus the cache/preflight/warnings-sidecar behavior that `scripts/verify_phase6_smoke.py`'s 3-scenario regression (route-down / cache-hit / --skip-semantic) will exercise.
- **CINEMA-01/03/04/05 closed at component level.** CINEMA-02 (run_pipeline `[N/7]` step slot) + CINEMA-06 (4 flags surfaced in run_pipeline argparse) close in Plan 03.
- **Phase 7** can mirror this stage pattern for the `character-reid` route (cache + preflight + degrade).
- **Phase 8** owns `prompt_text` recomposition (this plan deliberately leaves `prompt_text=""`).

## Self-Check: PASSED

All 10 created/modified files FOUND on disk; both task commits (a1b7904, c9103fe) FOUND in git log; `analysis/__init__.py` CONFIRMED absent (namespace-package convention).

---
*Phase: 06-cinematography-auto-fill-step-semantic*
*Completed: 2026-07-24*
