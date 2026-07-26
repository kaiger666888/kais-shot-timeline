---
phase: 10-risk-validation-spike-route-stub
plan: 01
subsystem: spike/audio
tags: [wave0, smoke-harness, foundation, throwaway]
requires:
  - ep01 cached intermediates (output/虫虫武侠小故事…/stems/htdemucs/<ep01>/{vocals,drums,bass,other}.wav + shots.json + transcript.json)
provides:
  - spike/audio/common.py (EP01_* path constants, stratified_sample n=30 seed=10, parse_sensevoice_tags, _safe_error, write_result, git_sha)
  - spike/audio/tests/smoke_all.sh (wave-merge gate runner)
  - spike/audio/tests/route_stub_smoke.sh (ROUTE-01 envelope 3-check curl harness)
  - spike/audio/tests/results_schema_check.py (per-model JSON shape validator)
  - spike/audio/tests/staleness_check.sh (Pitfall 10 staleness gate wrapper)
  - spike/audio/aggregate_report.py (--check-staleness + --aggregate placeholder; Plan 06 fleshes out)
  - spike/audio/README.md (THROWAWAY invariant + invariants + WhisperX venv path)
affects:
  - downstream plans 10-02 (route stub uses route_stub_smoke.sh), 10-03/04/05 (spike scripts import common.py), 10-06 (aggregate_report.py)
tech-stack:
  added: []
  patterns:
  - Throwaway spike scripts NOT wired into run_pipeline.py (analysis/ = producer-code convention preserved)
  - Deterministic stratified sample (seed=10 n=30) shared across 4 spikes for Pitfall 9 head-to-head integrity
  - HF_TOKEN redaction via _safe_error regex extended from call_shot_analysis.py:122 (Pitfall 6 / T-10-01 mitigation)
  - Wave-merge gate via smoke_all.sh (VALIDATION.md Nyquist Wave 0 invariant)
key-files:
  created:
    - spike/audio/common.py (260 lines)
    - spike/audio/aggregate_report.py (95 lines)
    - spike/audio/README.md (76 lines)
    - spike/audio/tests/smoke_all.sh (46 lines)
    - spike/audio/tests/route_stub_smoke.sh (82 lines)
    - spike/audio/tests/results_schema_check.py (188 lines)
    - spike/audio/tests/staleness_check.sh (14 lines)
  modified: []
decisions:
  - Wave 0 minimal aggregate_report.py scaffold committed with Task 2 (Rule 3 — staleness_check.sh in Task 2 requires aggregate_report.py from Task 3 to exist; atomic Task 2 verify depends on it)
  - stratified_sample uses ceil(n/4) per bucket + dedupe + backfill (Rule 1 — literal "n//4 per bucket" from plan body capped at 4×7=28 < 30, could not satisfy the n=30 acceptance criterion)
metrics:
  duration: 7m20s
  completed: 2026-07-25
  tasks: 3
  files_created: 7
  files_modified: 0
---

# Phase 10 Plan 01: Wave 0 Foundation (common.py + smoke harness + aggregate scaffold) Summary

Wave 0 throwaway-spike foundation: 7 files under `spike/audio/` that all Wave 1+ spike scripts (Plans 03/04/05) import and that the ROUTE-01 stub verification (Plan 02) calls. NONE are pipeline code — README.md makes the throwaway invariant explicit.

## What Was Built

**`common.py` (260 lines)** — shared helpers imported by every spike script:
- `EP01_DIR` / `EP01_VOCALS` / `EP01_DRUMS` / `EP01_BASS` / `EP01_OTHER` / `EP01_SHOTS` / `EP01_TRANSCRIPT` / `EP01_AUDIO_ANALYSIS` — pathlib.Path constants pointing at the verified ep01 cached layout. All `.exists() == True` verified.
- `stratified_sample(segments, n=30, seed=10)` — deterministic 4-bucket (short<2s / medium 2-5s / long>5s / dense>10chars-per-sec) stratified sampler. Pitfall 9 head-to-head integrity: same `(segments, n, seed)` → same 30-element list across all 4 model spikes.
- `parse_sensevoice_tags(raw_text)` — regex-extracts `{language, emotion, events, clean_text}` from raw SenseVoice output BEFORE `rich_transcription_postprocess` (Pitfall 2). Default emotion = `emo_unk` when no emotion tag matches.
- `_safe_error(msg)` — regex redacts `hf_<token>` / `token=<val>` / `Bearer <val>` / URL userinfo. T-10-01 mitigation extending `call_shot_analysis.py:122` (Pitfall 6 HF_TOKEN leakage prevention).
- `write_result(model, fixture, payload)` — stamps `{model, fixture, git_sha, timestamp_utc, device='cpu'}`, writes `results/<model>_<fixture>.json` with `ensure_ascii=False, indent=2`, runs final `_safe_error` pass.
- `git_sha()` — `subprocess.check_output(["git","rev-parse","--short","HEAD"])`, short-circuits to `"unknown"` on failure (T-10-05 accepted; spike fault-tolerance).

**`tests/smoke_all.sh` (46 lines)** — top-level wave-merge gate runner. Calls schema/staleness/route-stub in order; exits non-zero on first failure. Wave 0 baseline: empty results/ + no route host → ALL SMOKE CHECKS PASS.

**`tests/route_stub_smoke.sh` (82 lines)** — 3 curl checks against `${AUDIO_ROUTE_URL:-http://localhost:3000}/api/production/audio-analysis` (NO `/v1/` per RESEARCH mounting-path note). Auto-skips with Wave 0 baseline message when server down or `SKIP_ROUTE_STUB=1`. Checks: (1) happy path code==200 + stub_mode==true, (2) validation code==400, (3) env-flip informational only.

**`tests/results_schema_check.py` (188 lines)** — per-model JSON shape validator. Dispatches by filename prefix: `ser_sensevoice_*` / `mir_mert_*` / `mir_panns_*` (uniform per-sample entry per Plan 10-04 Task 2) / `whisperx_align_*` (sample_size>=30 invariant) / `diarize_*`. Empty results/ → exit 0 (Wave 0 baseline).

**`tests/staleness_check.sh` (14 lines)** — single-line `exec` wrapper around `aggregate_report.py --check-staleness`.

**`aggregate_report.py` (95 lines)** — `--check-staleness` (Pitfall 10 gate: compares per-file `git_sha` to current HEAD; exit 1 on stale) + `--aggregate` (Plan 06 placeholder). Empty results/ → exit 0 (Wave 0 baseline).

**`README.md` (76 lines)** — Chinese throwaway invariant: do NOT import from `run_pipeline.py` or `analysis/*`. Documents n=30 seed=10 + device='cpu' + ep01 fixture invariants + WhisperX isolated-venv path `/tmp/whisperx-spike-venv` (Pitfall 1).

## Verification Results

All 5 plan-level verification assertions PASSED:

| Check | Result |
|-------|--------|
| `bash spike/audio/tests/smoke_all.sh` exits 0 (Wave 0 baseline) | ✓ ALL SMOKE CHECKS PASS |
| `SKIP_ROUTE_STUB=1 bash spike/audio/tests/smoke_all.sh` exits 0 | ✓ explicit skip path |
| `python3 -c "import common; common.stratified_sample([], n=30)"` no raise | ✓ returns `len=0` |
| All 7 files exist under `spike/audio/` | ✓ |
| `git diff --stat HEAD~3 HEAD` shows ONLY spike/audio additions (no pipeline files touched) | ✓ 761 insertions across 7 files |

Task 1 behavior block (paths exist + 30-deterministic-unique sample + tag parse + redaction) → `[common] all behavior checks GREEN`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] stratified_sample algorithm couldn't reach n=30**

- **Found during:** Task 1 GREEN verification (RED test asserted `len(s1) == 30`, got 28).
- **Issue:** Plan body specified `per_bucket = max(1, n // 4)` — for n=30 this is 7, and 4 buckets × 7 = 28, which can NEVER satisfy the `len(s1) == 30` acceptance criterion (also unique-element check after dedupe would shrink it further).
- **Fix:** Changed to `per_bucket = max(1, (n + 3) // 4)` (ceil division → 8 per bucket = 32 candidates pre-dedupe). Added dedupe by `idx` (since `dense` bucket overlaps the three duration buckets). Added backfill pass for the edge case where dedupe drops too many. Returns exactly `n=30` for the ep01 155-segment input.
- **Files modified:** `spike/audio/common.py` (stratified_sample body + docstring)
- **Commit:** `b5279b0`

**2. [Rule 1 - Bug] _safe_error preserved literal "Bearer " prefix**

- **Found during:** Task 1 GREEN verification (`AssertionError: leak: Auth failed: [REDACTED] token=[REDACTED] Bearer [REDACTED]` — the literal word "Bearer" was preserved).
- **Issue:** Plan verify asserts `'Bearer' not in redacted`. Original regex replacement `Bearer [REDACTED]` kept the literal `Bearer` prefix word.
- **Fix:** Changed `_BEARER_RE.sub(...)` replacement to consume the entire `Bearer <val>` match → `[REDACTED]` (without the "Bearer " prefix). hf_/token=/URL-userinfo replacements were already correct.
- **Files modified:** `spike/audio/common.py` (one-line `_safe_error` body)
- **Commit:** `b5279b0`

**3. [Rule 3 - Blocking] Task 2 staleness_check.sh depends on Task 3 aggregate_report.py**

- **Found during:** Task 2 implementation (staleness_check.sh in Task 2 wraps `aggregate_report.py` from Task 3 — hidden Task 2→Task 3 dependency that breaks atomic Task 2 verification).
- **Issue:** Per "one task per commit" convention, Task 2 commit should only contain the 4 smoke files, but `bash smoke_all.sh` (Task 2's verify command) fails with "file not found" if `aggregate_report.py` doesn't exist on disk.
- **Fix:** Wrote a minimal `aggregate_report.py` scaffold (only `--check-staleness` flag + default no-flag placeholder) as part of the Task 2 commit so atomic verification works. Task 3 then expanded it with the `--aggregate` flag.
- **Files modified:** `spike/audio/aggregate_report.py` (initial minimal version committed with Task 2, expanded in Task 3 commit `9192d7b`)
- **Commits:** Task 2 commit `f6b554e` includes the minimal scaffold; Task 3 commit `9192d7b` adds `--aggregate`.

## Authentication Gates

None — Plan 10-01 has no model loading or external auth. HF_TOKEN redaction is preemptive (T-10-01 mitigation for future Plans 03/04/05/optional diarize).

## Known Stubs

None — `aggregate_report.py:aggregate()` is a documented Plan 06 placeholder by design (not a stub that masks unfinished plan-10-01 work). It prints `"skeleton — Plan 06 fleshes this out; got N result file(s)"` and exits 0, which IS the complete Plan 10-01 Task 3 deliverable.

## Threat Flags

None new beyond the threat model in PLAN.md. `_safe_error` implements T-10-01 mitigation; `write_result` stamps `device='cpu' + git_sha` (T-10-02 mitigation); `git_sha` subprocess is T-10-05 accepted (system git on repo HEAD, no untrusted input).

## Self-Check

Files (all 7 spike/audio deliverables):

- FOUND: `spike/audio/common.py`
- FOUND: `spike/audio/aggregate_report.py`
- FOUND: `spike/audio/README.md`
- FOUND: `spike/audio/tests/smoke_all.sh`
- FOUND: `spike/audio/tests/route_stub_smoke.sh`
- FOUND: `spike/audio/tests/results_schema_check.py`
- FOUND: `spike/audio/tests/staleness_check.sh`

Commits (3 task commits):

- FOUND: `b5279b0` (feat 10-01: common.py)
- FOUND: `f6b554e` (feat 10-01: smoke harness + aggregate scaffold)
- FOUND: `9192d7b` (feat 10-01: --aggregate flag + README)

## Self-Check: PASSED
