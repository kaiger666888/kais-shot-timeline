---
phase: 15-layered-reproduction-prompts
plan: 01
subsystem: audio
tags: [reproduction-prompts, model-agnostic-nl, conditional-gating, af-01-grep-gate, fidelity-disclaimer, spike-promotion, mus-04-omitted, dia-04-nullable, dia-05-experimental, table-stakes-flow, differentiator-nullable, pure-composer]
requires:
  - spec/schemas/audio_semantic.schema.json
  - analysis/call_audio_analysis.py (Phase 12 normalize_audio_semantic)
  - spec/SPEC.md §10 (fidelity_disclaimer literals)
provides:
  - audio/gen_audio_prompts.py:compose_reproduction (pure library entry)
  - audio/gen_audio_prompts.py:_compose_tts_layer / _compose_music_gen_layer / _compose_foley_layer
  - analysis/call_audio_analysis.py wired with lazy-import + per-shot composer invocation
  - run_pipeline.py threads audio_analysis.json side input through step_audio_semantic
affects:
  - Phase 15-02 (--recompose CLI mode uses compose_reproduction)
  - Phase 16 HTML gallery (renders reproduction.{tts,music_gen,foley} panel)
  - Phase 17 canvas consumer (emits audio asset nodes per shot)
tech_stack:
  added: []
  patterns:
    - 纯函数 composer（无 I/O / RNG / timestamps）—— mirror v1.1 Pattern 2 deterministic recompose
    - SPEC §10 fidelity_disclaimer 字面量锁定（AF-01 mitigation）
    - lazy-import via importlib.util（mirror SCHEMA_VERSION pattern in call_audio_analysis.py:540-558）
    - CONDITIONAL gating per Phase 10 LOCKED（MUS-04 omitted; DIA-04 nullable+confidence; DIA-05 word-level composer-isolated）
key_files:
  created: []
  modified:
    - audio/gen_audio_prompts.py
    - analysis/call_audio_analysis.py
    - run_pipeline.py
decisions:
  - emit triggers for music_gen are strictly BGM-OR-tempo（mood is modifier only — prevents over-claiming for pure-dialogue shots）
  - reproduction key OMITTED when all three layers null（保 has_any_data 在 CONTRACT-05 byte-identical-absent 路径上正确；deferred to 15-02 Task 3 Rule 1 fix）
  - composer is dual-entry：library function（invoked inline by call_audio_analysis.py）+ future --recompose CLI（15-02 Task 1）
  - spike helpers（load_audio_stem/estimate_tempo_from_envelope/brightness_word/loudness_word）preserved as library functions
metrics:
  duration: ~25min
  completed: 2026-07-26
  tasks: 3/3
  verdict: approved → Plan 15-02 (recompose CLI + smoke harness) unblocked
---

# Phase 15 Plan 01: Layered Reproduction Prompts Library + Producer Wiring Summary

**One-liner:** Promoted `audio/gen_audio_prompts.py` spike to pure library composer `compose_reproduction(shot, analysis_shot) -> {tts, music_gen, foley}`; wired into `analysis/call_audio_analysis.py` per-shot loop via lazy import; threaded `--audio-analysis-json` side input through `run_pipeline.py:step_audio_semantic`; AF-01 grep gate + MUS-04 instruments audit + DIA-05 word-level isolation all CLEAN.

## What Was Built

### Task 1: Pure `compose_reproduction` library (audio/gen_audio_prompts.py)

Three private layer composers + one public entry point, all pure (no I/O, no RNG, no timestamps — same inputs produce byte-identical outputs across processes):

- **`_compose_tts_layer(dialogue)`** — DIA-01 text + DIA-04 emotion nullable+confidence + DIA-05 word-level NEVER read (T-15-04 mitigation). Confidence calibrated to ~0.65-0.85 (SPEC §10.2 TTS ~70% central estimate).
- **`_compose_music_gen_layer(shot_semantic, analysis_shot, drum_audio, drum_sr)`** — MUS-01 BGM presence (from SenseVoice events) OR MUS-02 tempo (from audio_analysis.json side input when drums ratio ≥ 0.10). MUS-03 mood (from dialogue.emotion via MOOD_MAP) is modifier-only. MUS-04 乐器 field NEVER emitted (T-15-02 mitigation; Phase 11 schema $comment lock). MUS-05/MUS-06 differentiator-populated-when-route-produces-signal is null-by-default.
- **`_compose_foley_layer(sfx)`** — SFX-01 description verbatim + SenseVoice 8-event non-speech subset (EVENT_CN_MAP). SFX-02/SFX-03 deferred v1.3 → null.

Each non-null layer carries one of three SPEC §10 LOCKED `fidelity_disclaimer` literals:
- `FIDELITY_DISCLAIMER_TTS = "TTS ~70% similarity to source voice (AF-01 mitigation)"`
- `FIDELITY_DISCLAIMER_MUSIC_GEN = "music-gen ~60-75% harmonic/rhythmic similarity; timbre not guaranteed (AF-01 mitigation)"`
- `FIDELITY_DISCLAIMER_FOLEY = "foley ~80% similarity for defined event types (AF-01 mitigation)"`

Lookup tables UPPER_CASE per CLAUDE.md: `EMOTION_TONE_MAP`, `MOOD_MAP`, `EVENT_CN_MAP`.

Spike CLI (`--episode-dir` + sidecar output) preserved in this commit; retired in Plan 15-02 Task 1.

### Task 2: Producer wiring (analysis/call_audio_analysis.py)

- Lazy-import `compose_reproduction` via `importlib.util.spec_from_file_location` (mirror SCHEMA_VERSION pattern at lines 540-558; avoids stage-decoupling violation since `audio/` is not a package).
- New `--audio-analysis-json` CLI flag (Chinese help= per CLAUDE.md).
- `analysis_by_id` dict built at main() start for per-shot side input lookup.
- Composer invoked AFTER `normalize_audio_semantic()` and BEFORE `shots_out.append()` — Phase 12 transparent reproduction passthrough RETIRED (locked decision #6).
- Defense-in-depth: composer exception → reproduction OMIT entirely (schema-valid skeleton).
- Pre-write `Draft202012Validator` (existing defense at lines 780-804) catches any composer regression.

### Task 3: Pipeline threading (run_pipeline.py)

- `step_audio_semantic` signature extended with `audio_analysis_json: str | None = None`.
- subprocess argv conditionally extended with `--audio-analysis-json` when `audio_analysis.json` exists (mirror `--offline` pattern at line 394-396).
- `main()` passes `audio_json` (work_dir/audio_analysis.json) through to `step_audio_semantic`.
- Docstring documents the new parameter (Chinese rationale).

## Verification

- **AF-01 grep gate CLEAN**: `grep -rE 'perfectly reconstruct|exact restoration|完美复刻|精确复原' audio/ spec/SPEC.md spec/README.md scripts/ analysis/` returns 0 matches (exit 1).
- **MUS-04 instruments audit CLEAN**: `grep -riE '\binstruments\b|instrument_labels|instruments_detected' audio/ analysis/ spec/schemas/audio_semantic.schema.json spec/fixtures/v1.2/audio_semantic.json` returns 0 matches.
- **DIA-05 word-level audit CLEAN**: composer source contains NO code-level `.words` access (prose mentions in docstrings describing the invariant are not code).
- **E2E synthetic smoke**: composed reproduction validates against `audio_semantic.schema.json`; sample shot (dialogue+emotion+BGM+sfx) produces well-formed `{tts, music_gen, foley}` with appropriate confidence + fidelity_disclaimer per SPEC §10.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AF-01 / MUS-04 docstring prose self-match**
- **Found during:** Task 1 verification
- **Issue:** Initial composer docstring contained literal forbidden phrases ("perfectly reconstruct / exact restoration / 完美复刻 / 精确复原") and literal English `instruments` word — describing the invariants broke the grep gate.
- **Fix:** Replaced literal phrases with paraphrases (SPEC §10.1's generic term "绝对化复现措辞"; Phase 11 schema $comment's Chinese 「乐器」 convention).
- **Files modified:** audio/gen_audio_prompts.py (docstring + comment banner)
- **Commit:** ca492d3

No other deviations — plan executed as written.

## Threat Model Disposition Verification

| Threat | Mitigation Verified |
|--------|---------------------|
| T-15-01 (AF-01 forbidden phrases) | ✓ AF-01 grep CLEAN (load-bearing Task 3 acceptance) |
| T-15-02 (MUS-04 instruments leakage) | ✓ MUS-04 audit CLEAN (load-bearing Task 3 acceptance) |
| T-15-03 (non-deterministic composer) | ✓ Pure function — same-input byte-identical output (Task 1 verify) |
| T-15-04 (DIA-05 word-level leak) | ✓ No code-level `.words` access in composer (Task 1 verify) |
| T-15-05 (composer regression breaks schema) | ✓ Pre-write Draft202012Validator catches any escape (existing defense; Task 2 wiring relies on it) |

## Self-Check: PASSED

- [x] `audio/gen_audio_prompts.py` exports `compose_reproduction` (library function)
- [x] `analysis/call_audio_analysis.py` lazy-imports + invokes composer per-shot AFTER normalize
- [x] Phase 12 transparent reproduction passthrough RETIRED (grep confirms no `raw_repro = route_shot.get` in normalize function)
- [x] `run_pipeline.py` threads `audio_analysis.json` path through `step_audio_semantic`
- [x] AF-01 grep gate CLEAN
- [x] MUS-04 instruments audit CLEAN
- [x] DIA-05 composer audit CLEAN (no `.words` code-level access)
- [x] E2E synthetic smoke schema-validates composed reproduction

**Self-Check: PASSED**

## Requirements Closed

- **PROMPT-01**: per-shot reproduction.{tts,music_gen,foley} model-agnostic NL ✓
- **PROMPT-02**: nullable + confidence + fidelity_disclaimer per SPEC §10 ✓
- **PROMPT-03**: spike promoted; --offline recompose implemented in 15-02 (library fn ready)
- **DIA-01**: segment-level dialogue text flows to TTS ✓
- **DIA-04**: emotion nullable + emotion_confidence honored ✓
- **DIA-05**: word-level gating — composer NEVER reads words[] ✓
- **MUS-01**: BGM presence from SenseVoice events ✓
- **MUS-02**: tempo BPM from audio_analysis.json side input ✓
- **MUS-03**: discrete mood from emotion lookup ✓
- **MUS-04**: instruments OMITTED (deferred v1.3) ✓
- **MUS-05/MUS-06**: differentiator nullable (no route signal in v1.2) ✓
- **SFX-01**: foley description + SenseVoice events flow through ✓
- **SFX-02/SFX-03**: differentiator nullable (deferred v1.3) ✓

## Self-Check Run

Self-check executed on 2026-07-26: all files FOUND, all commits FOUND (e545bca + ca492d3 + bf9992e + a9a08bf), all gates CLEAN (AF-01 + MUS-04 + DIA-05).

**Self-Check Status: PASSED**
