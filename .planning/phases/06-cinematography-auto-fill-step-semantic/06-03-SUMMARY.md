---
phase: 06-cinematography-auto-fill-step-semantic
plan: 03
subsystem: infra
tags: [pipeline-orchestration, subprocess, argparse, jsonschema, graceful-degrade, regression-harness]

# Dependency graph
requires:
  - phase: 06-01
    provides: asset.schema.json#generator.warnings + export_asset.py warnings plumbing + SPEC §3 row
  - phase: 06-02
    provides: analysis/call_shot_analysis.py (httpx client + compose_facets LOCKED mapping + per-shot cache + preflight + warnings sidecar) + examples/shot_analysis/ fixtures
provides:
  - run_pipeline.py step_semantic wiring (subprocess-invokes analysis/call_shot_analysis.py between step_transcribe and step_timeline)
  - 7-step pipeline counter [N/7] (codec/detect/separate/transcribe/semantic/timeline/export)
  - 4 CLI flags (--skip-semantic / --offline / --analysis-url / --analysis-timeout) with Chinese help
  - --force cache list extended (clears prompts.json + route_cache/ dir on forced rerun)
  - scripts/verify_phase6_smoke.py — 3-scenario regression harness (route-down / --skip-semantic / cache-hit-offline)
affects:
  - Phase 7 (Cross-Shot Re-ID): inserts step_reid at slot 6, will bump counter to [N/8] (CONTEXT D-XX lock — no phantom gap)
  - Phase 8 (Prompt Reference System): consumes prompts.json produced by step_semantic for narrative recomposition
  - Phase 9 (Canvas Consumer Integration): asset.json now carries generator.warnings when route degrades

# Tech tracking
tech-stack:
  added: []  # zero new packages — stdlib (subprocess/argparse/tempfile/contextlib/io) + existing jsonschema 4.26.0
  patterns:
    - "step_* mirror pattern extended: step_semantic slots between step_transcribe + step_timeline, subprocess-invokes analysis/call_shot_analysis.py with --offline threaded conditionally"
    - "TOCTOU-safe mtime cache (mirror _safe_mtime helper from step_export 02-REVIEW WR-07) — single-point stat, missing → +inf → forced cache miss"
    - "--force cache list: files via os.unlink, directories (route_cache/) via shutil.rmtree(ignore_errors=True) so partial-corrupt cache doesn't block forced rerun"
    - "Regression harness pattern: standalone sys.exit(0/1) script mirroring scripts/verify_contract.py (no pytest — VALIDATION.md lock); per-scenario mkdtemp + finally rmtree"

key-files:
  created:
    - scripts/verify_phase6_smoke.py
  modified:
    - run_pipeline.py

key-decisions:
  - "Counter stays [N/7] (NOT [N/8]) per CONTEXT D-XX lock — Phase 7 will bump to [N/8] when it inserts step_reid at slot 6; no phantom gap left now"
  - "step_semantic return value intentionally NOT captured in main() — step_export independently checks os.path.exists(prompts.json); subprocess failure (schema validation) raises CalledProcessError → fail loud (project convention); graceful-degrade still writes prompts.json + exits 0"
  - "Offline mode does NOT skip the step (still runs subprocess to read cache + write prompts.json); only --skip-semantic short-circuits. CONTEXT recommendation followed."
  - "TINY_VIDEO in regression harness = scripts/verify_phase6_smoke.py itself — known to exist + fixed content → video_content_hash stable across runs (scenario 3 cache-key pre-seed reproducibility)"

patterns-established:
  - "step function counter format [N/total] in stdout labels (run_step banner + cache hit + skip short-circuit)"
  - "argparse flag conventions: --skip-* (store_true) for opt-out, --offline for global mode, --*-url/--*-timeout (type=float) for configuration; Chinese help= mandatory"
  - "Standalone regression harness contract: sys.exit(0/1), bracketed [phaseN-smoke] PASS/FAIL tags, mkdtemp + finally rmtree per scenario, inline Draft202012Validator for schema checks"

requirements-completed: [CINEMA-02, CINEMA-03, CINEMA-06]

# Metrics
duration: 10min
completed: 2026-07-24
---

# Phase 6 Plan 03: run_pipeline step_semantic Integration Summary

**Wired step_semantic into run_pipeline.py as pipeline slot 5 of 7 (between transcribe + timeline), renumbered 17 [N/6]→[N/7] labels, added 4 CLI flags (--skip-semantic/--offline/--analysis-url/--analysis-timeout), extended --force to clear prompts.json + route_cache/, and built scripts/verify_phase6_smoke.py (3-scenario regression: route-down / --skip-semantic / cache-hit-offline).**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-24T15:18:03Z
- **Completed:** 2026-07-24T15:28:22Z
- **Tasks:** 2 (Task 2 TDD: RED→GREEN)
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments

- `run_pipeline.py:step_semantic` mirrors `step_transcribe` shape (skip short-circuit + TOCTOU-safe mtime cache + subprocess banner); subprocess-invokes `analysis/call_shot_analysis.py` with 6 required flags + conditional `--offline`
- All 17 existing `[N/6]` step labels renamed to `[N/7]` (codec[1]/detect[2]/separate[3]/transcribe[4]/timeline[6]/export[7]); 3 new `[5/7]` labels added in `step_semantic` (skip / cache / banner) — total 20 `[N/7]`, zero residual `[N/6]`
- 4 new argparse flags with Chinese `help=` (CLAUDE.md convention); `--analysis-url` default notes "首跑需 verify 实际端口" (STATE.md blocker documentation)
- `--force` cache list extended with `prompts.json` + `route_cache/` dir; `shutil.rmtree(ignore_errors=True)` so partial-corrupt cache doesn't block forced rerun (T-06-11 mitigation)
- Module docstring updated: step 5 inserted between transcribe (4) and timeline (now 6); output layout notes `prompts.json` is now produced by step_semantic + new `route_cache/{shot_analysis, warnings.json}` runtime artifacts
- `scripts/verify_phase6_smoke.py` 3 scenarios all green: route-down (schema-valid empty facets + warnings sidecar), --skip-semantic (no subprocess banner), cache-hit-offline (camera='中景, follow, fast, pan_right' from shot_003 fixture)

## Task Commits

Each task was committed atomically:

1. **Task 1: run_pipeline.py — step_semantic + [N/7] renumber + 4 flags + --force list** — `9d0af89` (feat)
2. **Task 2 (TDD RED): scaffold verify_phase6_smoke.py** — `306a972` (test)
3. **Task 2 (TDD GREEN): implement 3 scenarios** — `0a6498c` (feat)

## Files Created/Modified

- `run_pipeline.py` — Added `step_semantic()` function (~50 LOC); renumbered 17 `[N/6]`→`[N/7]`; added 4 argparse flags; extended `--force` cache-clear list (rmtree for route_cache dir); updated module docstring to reflect 7-step pipeline
- `scripts/verify_phase6_smoke.py` (NEW) — Standalone regression harness (335 LOC): 3 scenarios (route_down / skip_semantic / cache_hit_offline), each with own `mkdtemp` + `finally rmtree`; inline `Draft202012Validator` for prompts.json schema check; in-process imports of `run_pipeline.step_semantic` (s2) and `analysis.call_shot_analysis.video_content_hash/ROUTE_VERSION` (s3) for precise stdout capture + cache-key pre-seed

## Decisions Made

- **Counter [N/7] not [N/8]:** Followed CONTEXT D-XX lock — Phase 7 will bump to [N/8] when it inserts `step_reid` at slot 6. Avoids phantom missing-step gap in the interim. ROADMAP already carries the inline note documenting this override (verified in Phase Details → Phase 6 "Counter lock" callout).
- **step_semantic return value not captured in main():** `step_export` independently checks `os.path.exists(prompts.json)`; if `call_shot_analysis.py` sys.exits on schema-validation failure, `subprocess.run(check=True)` raises `CalledProcessError` → pipeline halts (fails loud, project convention). Graceful-degrade path still writes prompts.json + exits 0 so pipeline continues.
- **TINY_VIDEO in smoke harness = the harness file itself:** `scripts/verify_phase6_smoke.py` is known to exist + has fixed content → `video_content_hash` is stable across runs, so scenario 3's pre-seeded `_cache_key` reliably matches.
- **Smoke harness uses in-process imports (not subprocess) for s2/s3 setup:** `run_pipeline.step_semantic` (s2) called directly via Python import for precise stdout capture; `analysis.call_shot_analysis.video_content_hash/ROUTE_NAME/ROUTE_VERSION` (s3) imported to compute the correct cache key. Subprocess is still used for the actual `call_shot_analysis.py` invocation in s1/s3 (mirrors real pipeline call path).

## Deviations from Plan

### Issues with plan-internal verification expectations (not code defects)

**1. [Rule 1 - Bug] Plan's `--help` grep expected exactly 4 matches but argparse emits 7**
- **Found during:** Task 1 verification
- **Issue:** The plan's automated verify command `python3 run_pipeline.py --help 2>&1 | grep -cE '\-\-skip-semantic|\-\-offline|\-\-analysis-url|\-\-analysis-timeout' | grep -q '^4$'` and acceptance criterion "returns 4" did not account for argparse's usage banner duplicating each flag. Each of the 4 flags appears 2× in `--help` output (once in the `usage:` banner, once in the `options:` block) → 8 raw matches; grep `-c` counts matching *lines* so the result is 7 (because `--skip-semantic [--skip-export] --offline` share one usage line).
- **Fix:** No code change — the underlying functional requirement ("all 4 flags surfaced with Chinese help=") is fully met (verified by per-flag grep: each flag appears 2×; Chinese help string matches ≥8). The plan author's expected grep count was an off-by-N error in their mental model of argparse output formatting.
- **Files modified:** none
- **Verification:** `python3 run_pipeline.py --help 2>&1 | grep -c '\-\-skip-semantic' == 2` (usage + options); same for the other 3 flags. Chinese help strings: 8 matches (`跳过`/`仅读`/`超时`).
- **Committed in:** 9d0af89 (Task 1 commit — no change needed; documented here for transparency)

---

**Total deviations:** 1 documented (1 plan-internal off-by-N expectation; zero code changes required)
**Impact on plan:** None — all functional acceptance criteria satisfied. The plan's literal grep-count check is unmet, but the intent ("all 4 flags surfaced") is verifiably met.

## Issues Encountered

None beyond the plan-internal grep-count expectation noted above.

## User Setup Required

None — no external service configuration required. The default `--analysis-url http://127.0.0.1:8000/...` will need verification once `feat/shot-analysis-route` merges in kais-aigc-platform (already documented in STATE.md blocker + the flag's own help string: "首跑需 verify 实际端口").

## Next Phase Readiness

**Phase 6 is now shippable as a graceful-degrade producer.** All 3 plans complete:
- Plan 01: schema extension (`generator.warnings` optional) + exporter plumbing
- Plan 02: `analysis/call_shot_analysis.py` (httpx client + LOCKED mapping + cache + preflight)
- Plan 03: pipeline integration + 4 flags + regression harness (THIS PLAN)

**Live route round-trip remains deferred** per STATE.md blocker (`feat/shot-analysis-route` + `feat/shot-geometry-nodes` unmerged in kais-aigc-platform). Mapping correctness verified against 7 captured fixtures; graceful-degrade + cache behavior verified by `scripts/verify_phase6_smoke.py` (3 scenarios green).

**Unblocks:**
- Phase 7 (Cross-Shot Re-ID Registry + HITL Review) — prompts.json substrate now produced by step_semantic; `step_reid` will patch it
- Phase 8 (Prompt Reference System) — can begin prompt-text recomposition once Phase 7 ships confirmed registry entries

**Phase 7 counter bump reminder:** When Phase 7 inserts `step_reid` at slot 6, renumber `[N/7]` → `[N/8]` across the (now 20 + N new) labels. CONTEXT D-XX lock documented this deferment.

---
*Phase: 06-cinematography-auto-fill-step-semantic*
*Completed: 2026-07-24*

## Self-Check: PASSED

- Files: `run_pipeline.py`, `scripts/verify_phase6_smoke.py`, `06-03-SUMMARY.md` all FOUND
- Commits: `9d0af89` (Task 1 feat), `306a972` (Task 2 RED test), `0a6498c` (Task 2 GREEN feat) all FOUND in `git log`
