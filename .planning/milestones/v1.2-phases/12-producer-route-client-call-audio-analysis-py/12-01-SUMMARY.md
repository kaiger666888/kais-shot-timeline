---
phase: 12-producer-route-client-call-audio-analysis-py
plan: 01
subsystem: producer-client
tags: [httpx, audio-analysis, schema-validate, cache, graceful-degrade, warnings-merge, poisoned-invalidation]

# Dependency graph
requires:
  - phase: 10-02
    provides: POST /api/production/audio-analysis route stub (kais-aigc-platform:feat/audio-analysis-route) — envelope + mount-path contract
  - phase: 11
    provides: spec/schemas/audio_semantic.schema.json — Draft 2020-12 validation target
  - phase: (call_shot_analysis.py v1.1)
    provides: httpx POST + envelope unpack + _safe_error + preflight + per-shot cache analog
  - phase: (call_reid.py v1.1)
    provides: poisoned-cache invalidation + read-merge-write warnings sidecar analog
provides:
  - "analysis/call_audio_analysis.py — producer-side thin httpx client for POST /api/production/audio-analysis"
  - "Per-shot 4-tuple cache (route_cache/audio_analysis/shot_{sid:03d}.json) with poisoned-cache auto-invalidation"
  - "STEP_TAG=[audio] read-merge-write warnings sidecar (non-destructive cross-step merge)"
  - "SC#4-ready: stub envelope (stub_mode:true) round-trip proven end-to-end"
affects: [phase-14-pipeline-wiring, ROUTE-02, ROUTE-03, PIPE-02, phase-13-link-speakers, phase-15-gen-audio-prompts, phase-16-html]

# Tech tracking
tech-stack:
  added: []  # zero new deps — httpx 0.28.1 + jsonschema 4.26.0 both already in v1.1 deps
  patterns:
    - "Third sibling of the v1.1 route-pattern family: call_shot_analysis (per-shot POST+normalize), call_reid (per-video cache+invalidation+sidecar merge), call_audio_analysis (per-shot POST + per-shot cache + poisoned invalidation + [audio] sidecar merge)"
    - "Pre-write schema-validate gate (Draft202012Validator) doubles as poisoned-cache invalidation trigger — schema tightening auto-invalidates stale cache entries"
    - "byte-identical-absent graceful-degrade (CONTRACT-05): audio_semantic.json NOT written when zero shots have modality data → asset absent on v1.1 (additive v1.2)"
    - "ROUTE_PATH single-source of truth; preflight rsplit anchor /api/production (NOT /api/v1) matches audio-analysis mount-path flag (10-02-SUMMARY:113-117)"

key-files:
  created:
    - "analysis/call_audio_analysis.py (827 lines) — module docstring + constants + 5 helpers + main() CLI with 11 flags"
  modified: []

key-decisions:
  - "ROUTE_PATH hardcoded /api/production/audio-analysis (NO /v1/) — single source of truth, not configurable via --route-url"
  - "ROUTE_VERSION = phase-12-stub-v1 (bump on route logic change → cache invalidation)"
  - "Cache layout route_cache/audio_analysis/shot_{sid:03d}.json (per-shot, mirror shot_analysis NOT reid's per-video); 3-tuple _cache_key + shot_id in filename = 4-tuple per PIPE-02"
  - "SCHEMA_VERSION lazy-imported from scripts/export_asset.py via importlib (CONTRACT-03 single-source); '1.2' literal ONLY as fallback with explanatory comment"
  - "normalize_audio_semantic is healing (clamps out-of-range, drops malformed fields) — poisoned-cache invalidation fires only for unhealable schema constraint violations (e.g., shot_id < 1)"
  - "byte-identical-absent triggers on `has_any_data = any(shot has dialogue/sfx/reproduction)` — NOT on `shots_out` emptiness (always-append keeps shots[] covering full timeline)"
  - "Pre-existing audio_semantic.json NOT unlinked on full-degrade (operator may have valid prior output; we just skip writing)"

patterns-established:
  - "audio_semantic producer client: third instance of v1.1 route-client pattern, factored for per-shot POST + per-shot cache + cross-step warnings merge"
  - "STEP_TAG self-dedup (strip prior [audio] warnings) + cross-step preservation ([semantic]/[reid]/etc) — canonical read-merge-write contract for any future route-client sibling"
  - "Lazy SCHEMA_VERSION import via importlib (not module import) — keeps analysis/ → scripts/ dependency at runtime-only, no import-time side effects"

requirements-completed: [ROUTE-02, ROUTE-03, PIPE-02]

# Metrics
duration: 4min
completed: 2026-07-25
---

# Phase 12 Plan 01: Producer Route Client (call_audio_analysis.py) Summary

**827-line httpx producer client for POST /api/production/audio-analysis — third sibling of v1.1 route-pattern family, with per-shot 4-tuple cache, poisoned-cache schema-invalidated auto-cleanup, byte-identical-absent graceful-degrade, and non-destructive [audio] warnings sidecar merge; SC#4 stub round-trip proven end-to-end before any ML lands.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-07-25T15:54:53Z
- **Completed:** 2026-07-25T15:59:09Z
- **Tasks:** 2/2 complete
- **Files modified:** 1 (analysis/call_audio_analysis.py) + 1 SUMMARY

## Accomplishments

- `analysis/call_audio_analysis.py` (827 lines) parses cleanly, imports cleanly, and is schema-locked against `spec/schemas/audio_semantic.schema.json` pre-write.
- ROUTE_PATH = `/api/production/audio-analysis` (NO `/v1/`) is single-source; preflight + main client both rsplit on `/api/production` (mount-path flag honored).
- Zero occurrences of the English M-I word (case-insensitive) — 乐器/MIR-label lock respected per Phase 11 schema $comment.
- SC#4 stub round-trip proven in-process: `call_route` correctly handles `{code:200, data:{shots:[], stub_mode:true}}` → returns `(None, msg mentioning stub_mode:true)` → downstream graceful-degrade. Non-empty happy-path payload schema-validates against the Phase 11 schema.
- Cache layout + 3-tuple `_cache_key` + shot_id-in-filename = 4-tuple per PIPE-02. Poisoned-cache invalidation fires on schema-constraint violations normalize cannot heal (verified via shot_id=0 test).
- byte-identical-absent (CONTRACT-05): offline + empty cache → audio_semantic.json NOT written; [audio] warnings sidecar contains tagged entries.
- Cross-step warnings sidecar merge preserves `[semantic]`/`[reid]` tags; self-dedup strips prior `[audio]` tags to prevent self-accumulate on re-run.
- SCHEMA_VERSION lazy-imported from scripts/export_asset.py via importlib (CONTRACT-03 single-source); `1.2` literal only as fallback with explanatory comment.
- Field shapes honor Phase 11 schema: emotion nullable string + emotion_confidence [0,1] clamp (WR-03 analog); words[] EXPERIMENTAL with `word_level_experimental` top-level flag; reproduction.{tts,music_gen,foley} passthrough.
- T-12-04 mitigation: `_safe_error` regex applied on every error path before warnings sidecar write (auth/URL redaction defense-in-depth).

## Task Commits

Each task was committed atomically:

1. **Task 1: Core httpx POST + envelope normalize + schema-validate gate** — `5f8dac9` (feat) — module docstring + ROUTE_PATH constant + 5 helpers (`video_content_hash`, `_safe_error`, `normalize_audio_semantic`, `call_route`, `preflight`) + module constants. No `main()`.
2. **Task 2: Per-shot 4-tuple cache + poisoned invalidation + graceful-degrade + [audio] warnings read-merge-write + CLI main()** — `d7f4945` (feat) — appended `main()` (11-flag CLI) + cache helpers + atomic write + warnings sidecar merge.

**Plan metadata:** `TBD` (docs: complete plan — this commit)

## Files Created/Modified

- `analysis/call_audio_analysis.py` (created, 827 lines) — module docstring (Chinese) + 4 module constants (`ROUTE_NAME`, `ROUTE_VERSION`, `ROUTE_PATH`, `AUDIO_SEMANTIC_SCHEMA`) + 5 top-level helpers + `_cache_key_matches` / `_cache_key_payload` cache helpers + `main()` with argparse CLI (11 flags, Chinese help=).

## Decisions Made

- **ROUTE_PATH hardcoded (single source of truth).** Not configurable via `--route-url` (CONTEXT lock + 10-02-SUMMARY mount-path flag). `--route-url` defaults include the full path for documentation but the path component is rsplit-stripped before POST/preflight so ROUTE_PATH wins.
- **Cache dir under `route_cache/audio_analysis/`** (NOT `.cache/audio-analysis/`). CONTEXT.md suggested the latter, but v1.1 convention (`route_cache/<ROUTE_NAME>/`) wins so the warnings sidecar at `route_cache/warnings.json` merges correctly and `run_pipeline.py --force` cache-clearing stays consistent.
- **Always-append normalize strategy.** `shots_out` always contains every shot from `shots_meta` (skeletons for degraded shots). The byte-identical-absent decision is driven by `has_any_data = any(shot has dialogue/sfx/reproduction)`, NOT by `len(shots_out)`. This keeps shots[] timeline-coverage semantics stable when ≥1 shot has data while making the absent case unambiguous.
- **`SCHEMA_VERSION` import via importlib.util** (not module import). The `scripts/` directory has no `__init__.py`; importlib loads by filesystem path, keeping `analysis/ → scripts/` a runtime-only dependency with no import-time side effects (stage decoupling invariant preserved).
- **Lazy httpx import inside `call_route` + `preflight`** (not top-of-module). Mirrors `audio/transcribe.py` optional-dep pattern — cache-only `--offline` runs do not require httpx installed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed English literal from docstring (MUS-04 lock)**
- **Found during:** Task 1 verify automation
- **Issue:** First draft of the module docstring quoted the English M-I word in a comment explaining WHY it is omitted. Plan explicitly requires case-insensitive grep for that word to return 0 matches (Phase 11 schema $comment lock).
- **Fix:** Rewrote the docstring paragraph to use only the Chinese 「乐器」 and the English acronym "MIR label", removing the literal English word.
- **Files modified:** `analysis/call_audio_analysis.py` (docstring only, line 64 area)
- **Verification:** `! grep -niE 'instrument' analysis/call_audio_analysis.py` returns success (0 matches).
- **Committed in:** `5f8dac9` (Task 1 commit — fix applied before commit so verify passes on the committed file)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Cosmetic docstring reword to satisfy MUS-04 grep invariant. No scope creep, no architectural change, no behavior impact.

## Issues Encountered

None. Plan was extremely detailed (CONTEXT + interfaces + threat model + per-task action verify blocks); execution was straightforward code transcription of the v1.1 analog patterns.

The initial `--models` JSON parse failure path was added as a Rule 2 missing-critical-functionality guard: bad JSON in `--models` would otherwise crash inside the per-shot loop with an opaque error. Parse + validate early (in main, before cache lookup) — sys.exit with actionable message.

## User Setup Required

None — no external service configuration required. The client is offline-capable (`--offline`) and runs against cache alone. Live ML round-trip requires the Phase 10 stub host (kais-aigc-platform:feat/audio-analysis-route) running on `http://127.0.0.1:8000`; default `--route-url` already points there.

## Known Stubs

None. The producer client does not contain any data stubs, placeholder values, or hardcoded empty arrays that flow to consumers. The `audio_semantic.json` payload is built entirely from (a) cached route responses, (b) live route responses, or (c) absent entirely (byte-identical v1.1 asset on full degrade). The Phase 10 ROUTE-01 stub on the route host side is documented separately in `10-02-SUMMARY.md` and is NOT a stub in this client — the client correctly handles `stub_mode:true` as a graceful-degrade signal.

## Threat Flags

None beyond the plan's `<threat_model>`:

- T-12-01 (spoofing): mitigated — no auth header, internal-only route (mirror call_shot_analysis.py).
- T-12-02 (poisoned cache): mitigated — schema-validate on hit AND pre-write; auto-unlink on fail.
- T-12-03 (path traversal): mitigated — cache filename is `shot_{sid:03d}.json` with sid schema-validated int ≥1; no traversal vector.
- T-12-04 (info disclosure): mitigated — `_safe_error` regex on every error string before sidecar write; defense-in-depth.
- T-12-05 (malformed envelope): mitigated — `call_route` broadens except to `(httpx.HTTPError, ValueError, AttributeError, TypeError, KeyError)` + isinstance guards at every envelope level.
- T-12-SC (supply chain): N/A — zero new packages installed.

No new security-relevant surface introduced.

## Next Phase Readiness

- **Phase 12 Plan 02** (SC#4 stub round-trip harness) has a firm integration target: the client correctly handles the Phase 10 stub envelope (proven in-process via mock client in this plan's verify).
- **Phase 13** (`link_speakers`) can consume `audio_semantic.json#shots[].dialogue.spk_id` once the route populates it; absent spk_id is null (schema-valid).
- **Phase 14** (`step_audio_semantic`) wires this client into `run_pipeline.py` as slot 7/9; the CLI signature + work-dir/cache layout are stable.
- **Phase 15** (`gen_audio_prompts`) owns recomposition of `reproduction.{tts,music_gen,foley}`; Phase 12 only passes through whatever the route returns.

### Concerns

- `normalize_audio_semantic` is intentionally healing (clamps out-of-range values, drops malformed fields, drops unknown dialogue/sfx/reproduction keys). This means poisoned-cache invalidation effectively only fires for unhealable structural violations (e.g., shot_id < 1 from shot_meta). Future Phase 11+ schema tightenings that introduce new required fields could expose healing-vs-poisoning ambiguity; the pre-write validator catches this as a last-resort fail-loud. Trade-off is documented inline.
- `_safe_error` regex only redacts `user:pass@` basic-auth userinfo in URLs. If a future route returns token values in non-URL fields (e.g., `data.debug.auth_token`), those would NOT be redacted. Mitigation: schema `additionalProperties:false` on every envelope level drops unknown fields at the route boundary — defense-in-depth is preserved.

---

## Self-Check: PASSED

- FOUND: `analysis/call_audio_analysis.py` (827 lines, > min_lines:380)
- FOUND: commit `5f8dac9` in `git log` (feat — Task 1)
- FOUND: commit `d7f4945` in `git log` (feat — Task 2)
- PASS: `python3 -c "import ast; ast.parse(open('analysis/call_audio_analysis.py').read())"` (syntax valid)
- PASS: `python3 -c "from analysis.call_audio_analysis import main, normalize_audio_semantic, call_route, preflight, video_content_hash, _safe_error, ROUTE_PATH, ROUTE_NAME, AUDIO_SEMANTIC_SCHEMA"` (all imports)
- PASS: `grep -c 'ROUTE_PATH = "/api/production/audio-analysis"' analysis/call_audio_analysis.py` returns 1
- PASS: `! grep -niE 'instrument' analysis/call_audio_analysis.py` (0 matches — MUS-04 lock)
- PASS: `grep -c 'STEP_TAG = "\[audio\]"' analysis/call_audio_analysis.py` returns 1
- PASS: `! grep -c 'schema_version.*1\.2.*1\.2' analysis/call_audio_analysis.py` (no duplicate literal)
- PASS: offline smoke — audio_semantic.json NOT written, [audio] warning in sidecar
- PASS: cross-step [semantic]/[reid] tags preserved through read-merge-write
- PASS: [audio] self-dedup strips prior [audio] tags on re-run
- PASS: poisoned-cache invalidation fires on shot_id=0 schema violation
- PASS: SC#4 stub envelope (stub_mode:true) → call_route returns (None, msg mentioning stub_mode)
- PASS: non-empty happy-path payload schema-validates against audio_semantic.schema.json
- PASS: cache file pattern `shot_{sid:03d}.json`, 3-tuple `_cache_key`

---

*Phase: 12-producer-route-client-call-audio-analysis-py*
*Plan: 01*
*Completed: 2026-07-25*
