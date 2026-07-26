---
phase: 15-layered-reproduction-prompts
plan: 02
subsystem: audio
tags: [offline-recompose, byte-identical-determinism, spike-cli-retirement, smoke-harness, schema-validation, conditional-field-defer-proof, sc6-proof]
requires:
  - audio/gen_audio_prompts.py:compose_reproduction (Plan 15-01)
  - spec/schemas/audio_semantic.schema.json
provides:
  - audio/gen_audio_prompts.py --recompose CLI mode (offline in-place recompose)
  - audio/gen_audio_prompts.py:recompose_audio_semantic (in-process API for harness)
  - scripts/verify_phase15_repro_smoke.py (4-scenario regression + AF-01/MUS-04 audits)
  - spec/fixtures/v1.2/audio_semantic.json enriched (demonstrates composed tts + foley)
affects:
  - Phase 16 HTML gallery (smoke harness is the regression guard)
  - Phase 17 canvas consumer (fixture is the contract exemplar)
tech_stack:
  added: []
  patterns:
    - Atomic write via temp + os.replace (T-15-06 mitigation; mirror call_audio_analysis.py:807-811)
    - Pre-write Draft202012Validator defense-in-depth (T-15-07 mitigation)
    - Fragment-concatenated forbidden-phrase pattern in smoke harness (avoid self-match)
    - Idempotent fixed-point (composed reproduction is its own fixed-point under re-application)
key_files:
  created:
    - scripts/verify_phase15_repro_smoke.py
  modified:
    - audio/gen_audio_prompts.py
    - spec/fixtures/v1.2/audio_semantic.json
    - analysis/call_audio_analysis.py (Rule 1 fix for CONTRACT-05 preservation)
decisions:
  - --recompose mode is OFFLINE-ONLY by design (named --recompose NOT --offline to avoid confusion with run_pipeline.py global --offline)
  - Forbidden phrases in harness source assembled via fragment-concatenation at runtime (avoid self-match)
  - When composer returns all-null reproduction, producer OMITS the reproduction key entirely (not present-with-nulls) — preserves CONTRACT-05 byte-identical-absent semantics
metrics:
  duration: ~30min
  completed: 2026-07-26
  tasks: 3/3
  verdict: approved → Phase 15 fully closes PROMPT-01/02/03 + 12 modality reqs + SC#1-6
---

# Phase 15 Plan 02: --recompose Offline Mode + SC#6 Determinism Proof Summary

**One-liner:** Retired spike CLI per locked decision #6; added `--recompose` mode for offline in-place recomposition of `audio_semantic.json#shots[].reproduction` (byte-identical re-run = SC#6 proof); built 4-scenario smoke harness covering baseline-compose / byte-identical / idempotent-fixed-point / conditional-gate-proof + AF-01 grep + MUS-04 audit; enriched v1.2 fixture with composed tts + foley exemplar; fixed CONTRACT-05 regression where composer-emitted all-null reproduction broke Phase 14 route-down/stub-only byte-identical-absent scenarios.

## What Was Built

### Task 1: --recompose CLI mode (audio/gen_audio_prompts.py)

- **Spike CLI RETIRED** (locked decision #6): `--episode-dir` + `gen_prompts()` + `derive_facets_and_prompt()` + `find_dialogue_excerpt()` + `leading_phrase()` + `compose_prompt()` DELETED. Spike-only constants `DIALOGUE_EXCERPT_MAX_CHARS / VOCAL_PRESENCE_HIGH / SC_HIGH_CENTROID_HZ` removed.
- **New `recompose_audio_semantic(input_path, output_path, audio_analysis_json, schema_path) -> dict`** function:
  - Reads existing audio_semantic.json
  - Optionally loads + indexes audio_analysis.json side input by shot_id
  - Per-shot: invokes `compose_reproduction(shot, analysis_shot)` and replaces `shots[i]["reproduction"]` (preserves all other keys — T-15-07 mitigation)
  - Schema-validates recomposed payload (Draft202012Validator; sys.exit on failure)
  - Atomic write via temp + os.replace (T-15-06 mitigation)
- **New `main()`** with `--recompose / --audio-analysis-json / --schema` CLI flags (Chinese help= per CLAUDE.md).
- **Library functions preserved** unchanged from Plan 15-01: `compose_reproduction`, `_compose_*_layer`, lifted spike helpers (`load_audio_stem`, `estimate_tempo_from_envelope`, `brightness_word`, `loudness_word`), lookup tables (`EMOTION_TONE_MAP`, `MOOD_MAP`, `EVENT_CN_MAP`), fidelity_disclaimer literals.

### Task 2: 4-scenario smoke harness (scripts/verify_phase15_repro_smoke.py)

Mirror of `scripts/verify_phase_audio_smoke.py` structure (bracketed `[phase15-smoke]` prefix tags, `sys.exit(0/1)` contract, stdlib + jsonschema only, isolated `tempfile.mkdtemp` per scenario with `shutil.rmtree(ignore_errors=True)` in finally).

| Scenario | Coverage | Assertion |
|----------|----------|-----------|
| `baseline-compose` | PROMPT-01/02 + SC#1 | skeleton input → schema-valid output + non-reproduction fields preserved verbatim + SPEC §10 fidelity_disclaimer literals on every non-null layer |
| `byte-identical-SC6` | SC#6 load-bearing | two recompose runs on same input produce byte-identical file bytes |
| `idempotent-fixed-pt` | SC#1 + idempotency | re-recompose on composed output = byte-identical fixed-point |
| `conditional-gate` | CONDITIONAL gating全集 | 4 synthetic shots: dialogue-only (tts non-null) / BGM-only (music_gen non-null) / sfx-only (foley non-null) / empty (reproduction key OMITTED) |

Two global audits at harness tail:
- **AF-01 grep gate**: fragment-concatenated pattern (`"perfectly" + " reconstruct"`, etc.) to avoid harness source self-match; greps `audio/ spec/SPEC.md spec/README.md scripts/ analysis/`.
- **MUS-04 instruments audit**: case-insensitive grep for `\binstruments\b|instrument_labels|instruments_detected` across producer code + schema + fixture.

### Task 3: v1.2 fixture enrichment + CONTRACT-05 regression fix

- **`spec/fixtures/v1.2/audio_semantic.json` enriched**: shot 1 demonstrates composed `tts` + `foley` layers (`music_gen: null` — no BGM in shot 1's events, honestly demonstrating the differentiator-null case); shot 2 `reproduction` key OMITTED entirely (matches producer output shape after Rule 1 fix).
- **Schema-validate GREEN**, **bidirectional cross-version GREEN** (`scripts/verify_contract.py` 29 passed; v1.0↔v1.1↔v1.2 forward 0 errors + backward additionalProperties-only).

## Verification (all gates GREEN end-to-end)

```
=== Phase 15 smoke ===
[phase15-smoke] Result: 4/4 scenarios + AF-01 ✓ + MUS-04 ✓ = ALL_SCENARIOS_PASS

=== Phase 14 smoke (no regression) ===
[phase14-smoke] OK: 6/6 scenarios green

=== Phase 11 bidirectional cross-version ===
29 passed, 0 failed
[verify-contract] OK producer + OK consumer
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] music_gen emit trigger over-claimed on mood-alone**
- **Found during:** Plan 15-02 Task 1 verification
- **Issue:** Initial `_compose_music_gen_layer` let `mood_word` alone (derived from `dialogue.emotion`) trigger music_gen emit. For a pure-dialogue shot with emotion but no BGM/tempo, this over-claimed music reproduction.
- **Fix:** Emit triggers are now strictly BGM-OR-tempo (mood is modifier only), matching Plan 15-01 Task 1 spec lock. Unreachable "ambient bed" branch removed.
- **Files modified:** audio/gen_audio_prompts.py (`_compose_music_gen_layer`)
- **Commit:** b469637

**2. [Rule 1 - Bug] CONTRACT-05 regression — composer always emitted reproduction key**
- **Found during:** Plan 15-02 Task 3 Phase 14 regression run
- **Issue:** Phase 15 composer unconditionally set `shot["reproduction"] = {tts: null, music_gen: null, foley: null}` for skeleton-only shots. This made `has_any_data` in `call_audio_analysis.py:805-808` return True for route-down/stub-mode scenarios (because `bool(shot.get("reproduction"))` is True for any dict, even all-null), causing `audio_semantic.json` to be written — breaking CONTRACT-05 byte-identical-absent.
- **Fix:** Only emit `reproduction` key when ≥1 layer is non-null. Applied to both `analysis/call_audio_analysis.py` (producer hot path) and `recompose_audio_semantic` (CLI --recompose mode).
- **Files modified:** analysis/call_audio_analysis.py, audio/gen_audio_prompts.py, spec/fixtures/v1.2/audio_semantic.json (shot 2 reproduction key OMITTED), scripts/verify_phase15_repro_smoke.py (conditional-gate scenario updated to assert key-omitted for empty shot)
- **Verification:** Phase 14 stub_only + route_down scenarios now GREEN (were FAIL); Phase 15 smoke ALL_SCENARIOS_PASS
- **Commit:** 40f26af

**3. [Rule 1 - Bug] AF-01 grep self-match in smoke harness**
- **Found during:** Plan 15-02 Task 2 harness run
- **Issue:** Smoke harness source contained literal forbidden phrases in docstring + grep pattern argument + assertion list — the harness's own `_af01_grep_gate()` subprocess walked `scripts/` and self-matched, always returning FAIL.
- **Fix:** Fragment-concatenate the forbidden phrases at runtime (`"perfectly" + " reconstruct"`) so the literal phrase never appears in source. SPEC §10.1's generic term "绝对化复现措辞" used in prose.
- **Files modified:** scripts/verify_phase15_repro_smoke.py
- **Commit:** 256273d

No Rule 4 (architectural) deviations — plan executed as written.

## Threat Model Disposition Verification

| Threat | Mitigation Verified |
|--------|---------------------|
| T-15-06 (non-atomic write) | ✓ `os.replace` present in recompose_audio_semantic write block |
| T-15-07 (non-reproduction field corruption) | ✓ Scenario baseline-compose asserts `schema_version / word_level_experimental / dialogue.text` preserved verbatim; pre-write validator defense-in-depth |
| T-15-08 (timestamps / abs paths in output) | ✓ byte-identical-SC6 scenario implicitly verifies (no time-dependent drift across runs) |
| T-15-09 (temp dir / stub process linger) | ✓ Every scenario has `tempfile.mkdtemp` paired with `shutil.rmtree(ignore_errors=True)` in `finally` |

## Self-Check: PASSED

- [x] `audio/gen_audio_prompts.py` CLI retired from spike (`--episode-dir` / `audio_prompts.json` sidecar absent)
- [x] `--recompose` mode + `recompose_audio_semantic` function present
- [x] Atomic write via `os.replace` present (T-15-06)
- [x] Pre-write `Draft202012Validator` present (T-15-07)
- [x] SC#6 byte-identical proof passes (Plan 15-02 Task 1 + smoke scenario_byte_identical)
- [x] Idempotent fixed-point passes (smoke scenario_idempotent)
- [x] 4-scenario smoke harness + AF-01 grep + MUS-04 audit ALL_SCENARIOS_PASS
- [x] Phase 14 smoke 6/6 GREEN (no regression)
- [x] Phase 11 bidirectional cross-version OK
- [x] `spec/fixtures/v1.2/audio_semantic.json` schema-valid + matches producer output shape

**Self-Check: PASSED**

## Phase 15 Complete — All Success Criteria Met

| SC | Description | Status |
|----|-------------|--------|
| SC#1 | per-shot reproduction.{tts,music_gen,foley} model-agnostic NL + deterministic recompose | ✓ (Plan 15-01 + 15-02) |
| SC#2 | every reproduction field nullable + confidence + SPEC §10 fidelity_disclaimer; no absolute-restoration phrasing | ✓ (AF-01 grep CLEAN) |
| SC#3 | table-stakes modality enrichment (DIA-01/MUS-01/02/03/SFX-01) flows through | ✓ (composer source confirms each) |
| SC#4 | differentiator modalities (MUS-05/06, SFX-02/03) populate nullable+confidence when route produces signal | ✓ (null-by-default; emit-on-signal) |
| SC#5 | CONDITIONAL-gated items ship-or-defer per Phase 10 spike thresholds (MUS-04 omitted; DIA-04 nullable+confidence; DIA-05 word-level gated) | ✓ (MUS-04 audit CLEAN; DIA-05 composer-isolated) |
| SC#6 | --offline recompose byte-identical | ✓ (smoke scenario_byte_identical load-bearing proof) |

## Self-Check Run

Self-check executed on 2026-07-26: all files FOUND (audio/gen_audio_prompts.py + scripts/verify_phase15_repro_smoke.py + spec/fixtures/v1.2/audio_semantic.json + both SUMMARY.md), all commits FOUND (b469637 + 256273d + 40f26af), Phase 15 smoke 4/4 + AF-01 + MUS-04 ALL_SCENARIOS_PASS, Phase 14 smoke 6/6 GREEN (no regression), Phase 11 bidirectional cross-version OK.

**Self-Check Status: PASSED**
