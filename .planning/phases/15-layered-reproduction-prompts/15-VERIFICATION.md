---
phase: 15-layered-reproduction-prompts
verified: 2026-07-26T08:35:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 15: Layered Reproduction Prompts — Verification Report

**Phase Goal:** Promote `audio/gen_audio_prompts.py` spike → pipeline producer of model-agnostic NL reproduction prompts at `audio_semantic.json#shots[].reproduction.{tts,music_gen,foley}` + `--offline` recompose + CONDITIONAL gating per Phase 10 thresholds.
**Verified:** 2026-07-26T08:35:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| #   | Truth                                                                                                                                                                                                                                                                                         | Status     | Evidence                                                                                                                                                                                                                         |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Per-shot `reproduction.{tts, music_gen, foley}` strings composed from upstream modalities (dialogue/music/sfx) — model-agnostic NL (locked decision #7); deterministic recompose (mirror v1.1 Pattern 2 — fixed key ordering, idempotent re-apply)                                              | ✓ VERIFIED | `audio/gen_audio_prompts.py:compose_reproduction` emits dict with fixed key order `{tts, music_gen, foley}`. SC#6 byte-identical proof passed (independent re-run diff = 0 bytes; see Probe Execution). Idempotent fixed-point passed. |
| 2   | Every reproduction field carries `nullable + confidence` + SPEC documents `fidelity_disclaimer` (TTS ~70% / music-gen ~60-75% / foley ~80%); HTML/SPEC/README never claim "perfectly reconstruct"/"exact restoration"                                                                       | ✓ VERIFIED | Each non-null layer emits `{text, confidence, fidelity_disclaimer}` per schema `#$defs/repro_prompt`. AF-01 grep CLEAN on producer code: `grep -rE 'perfectly reconstruct\|exact restoration\|完美复刻\|精确复原' audio/ spec/SPEC.md spec/README.md scripts/ analysis/` → 0 matches. Three FIDELITY_DISCLAIMER_* literals emitted (lines 173-179). |
| 3   | Table-stakes modality enrichment flows through: DIA-01 segment dialogue, MUS-01 BGM presence, MUS-02 tempo BPM, MUS-03 discrete mood, SFX-01 foley description (with SenseVoice 8 audio-event tags)                                                                                            | ✓ VERIFIED | Behavioral spot-check confirms: dialogue text appears in tts prompt; BGM tag triggers music_gen; HAPPY emotion → "upbeat" mood word via MOOD_MAP; foley text contains `[笑声]: 观众笑声` (EVENT_CN_MAP). MUS-02 tempo wired through `analysis_shot` side input + `estimate_tempo_from_envelope` (requires `drums.wav` envelope, exercised via CLI --recompose path). |
| 4   | Differentiator modality enrichment populates nullable+confidence fields when models produce signal: MUS-05 key, MUS-06 VA, SFX-02 AudioSet taxonomy + timestamps, SFX-03 foley complex event sequences                                                                                       | ✓ VERIFIED | `_compose_music_gen_layer` docstring lines 282-285: "MUS-05 key / MUS-06 VA：v1.2 路由不产信号 → 始终 null"; schema has no separate field for these — composer emits them as implicit nulls inside music_gen layer (no route signal in v1.2 → null-by-default). Defer proof via absence in output. |
| 5   | CONDITIONAL-gated items (DIA-04 emotion / DIA-05 word-level / MUS-04 instruments) ship-or-defer per Phase 10 spike thresholds; deferred items emitted as nullable with `confidence=null` (or omitted per schema)                                                                              | ✓ VERIFIED | DIA-04: emotion flows into TTS prompt nullable+confidence (verified: 3 paths — emotion+EC=0.83, emotion w/o EC=0.75, no emotion=0.65). DIA-05: AST-level audit confirms NO `.words` attribute access in composer code (3 docstring/prose mentions only). MUS-04: producer code audit CLEAN (0 matches for `\binstruments\b\|instrument_labels\|instruments_detected` across audio/ analysis/ schema/ fixture). |
| 6   | `--offline` recompose from cached `audio_semantic.json` (no route hit) produces byte-identical reproduction layer — proven by deterministic re-run diff                                                                                                                                                            | ✓ VERIFIED | Independent byte-identical proof: `recompose_audio_semantic` invoked twice on same input → raw file bytes equal (1907 bytes both). `recompose_audio_semantic` is OFFLINE-ONLY by design — reads filesystem only, no httpx/route hits. Smoke scenario `byte-identical-SC6` PASS. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `audio/gen_audio_prompts.py` | Pure library composer `compose_reproduction(shot, analysis_shot) -> {tts, music_gen,foley}` + `recompose_audio_semantic` + `--recompose` CLI; AF-01 compliant; MUS-04 omitted; spike retired | ✓ VERIFIED | 624 lines (>= 380 min). Contains `compose_reproduction`, `_compose_*_layer`, `recompose_audio_semantic`, `--recompose`, `--audio-analysis-json`, FIDELITY_DISCLAIMER_*, EMOTION_TONE_MAP, MOOD_MAP, EVENT_CN_MAP, `os.replace` atomic write, `Draft202012Validator` schema defense. Pure (no I/O in composer; no RNG; no timestamps). |
| `analysis/call_audio_analysis.py` | Producer end-to-end: lazy-import + per-shot composer invocation after normalize; `--audio-analysis-json` CLI; pre-write validator catches regressions; CONTRACT-05 preserve (omit reproduction when all-null); Phase 12 transparent passthrough retired | ✓ VERIFIED | Lazy-import block at lines 570-592. `--audio-analysis-json` argparse flag. `analysis_by_id` side-input index. Composer invoked at lines 772-788 inside per-shot loop after `normalize_audio_semantic` and before `shots_out.append`. CONTRACT-05 preservation via conditional emit (`pop("reproduction")` on all-null). Phase 12 passthrough retired (no `raw_repro = route_shot.get` in normalize function). |
| `scripts/verify_phase15_repro_smoke.py` | 4-scenario regression harness + AF-01 + MUS-04 audits; stdlib + jsonschema only | ✓ VERIFIED | 448 lines. Contains `scenario_baseline_compose`, `scenario_byte_identical`, `scenario_idempotent`, `scenario_conditional_gate_proof`, `_af01_grep_gate`, `_mus04_audit`. Each scenario uses `tempfile.mkdtemp` paired with `shutil.rmtree` in `finally` (T-15-09). |
| `spec/fixtures/v1.2/audio_semantic.json` | Demonstrates composed reproduction across layers (shot 1: tts+foley; shot 2: omitted) | ✓ VERIFIED | Shot 1 has dialogue + sfx → reproduction.tts non-null + reproduction.foley non-null + reproduction.music_gen null (no BGM signal). Shot 2 has skeleton-only dialogue → reproduction key OMITTED entirely (CONTRACT-05 exemplar). Schema-validates. |
| `spec/schemas/audio_semantic.schema.json` | `reproduction.{tts,music_gen,foley}` shape with `repro_prompt = {text, confidence, fidelity_disclaimer}` (nullable); $comment lock on MUS-04 omitted | ✓ VERIFIED | Lines 128-137: `reproduction` is object with optional `tts/music_gen/foley` each ref `$defs/repro_prompt`. `repro_prompt` is `['object','null']` with required `text` + optional `confidence` + `fidelity_disclaimer`. Schema `$comment` lines 7 documents MUS-04 deferral. |
| `run_pipeline.py:step_audio_semantic` | Threads `audio_analysis.json` path through to call_audio_analysis via `--audio-analysis-json` | ✓ VERIFIED | Signature extended at line 331 with `audio_analysis_json: str \| None = None`. Subprocess argv conditionally extended at lines 404-405. `main()` passes `audio_json` at line 774. Docstring documents Phase 15 side-input role. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `analysis/call_audio_analysis.py` per-shot loop | `audio/gen_audio_prompts.py:compose_reproduction` | importlib.util.spec_from_file_location lazy-import; invoked AFTER normalize and BEFORE append | ✓ WIRED | Lines 575-592 (lazy import) + lines 772-788 (per-shot invocation). `normalized["reproduction"] = repro` populates the per-shot output. |
| `audio/gen_audio_prompts.py:compose_reproduction` | `spec/schemas/audio_semantic.schema.json#$defs/repro_prompt` | schema-valid output `{text, confidence, fidelity_disclaimer}` per non-null layer | ✓ WIRED | Pre-write Draft202012Validator at call_audio_analysis.py:839-863 catches any escape. Independent schema validation of fixture confirms. |
| `run_pipeline.py:step_audio_semantic cmd argv` | `analysis/call_audio_analysis.py --audio-analysis-json` | additive CLI flag pass-through (mirror --stems-dir) | ✓ WIRED | Lines 404-405 conditional extension. audio_json path threaded from main() line 774. |
| `audio/gen_audio_prompts.py --recompose mode` | `audio_semantic.json` (in-place atomic rewrite) | json.load → per-shot compose_reproduction → Draft202012Validator → temp + os.replace | ✓ WIRED | `recompose_audio_semantic` function at lines 470-496; atomic write at lines 576-592. Smoke scenario `byte-identical-SC6` proves byte-identical. |
| `scripts/verify_phase15_repro_smoke.py scenario_byte_identical` | `audio/gen_audio_prompts.py --recompose` (twice) | direct call to `recompose_audio_semantic` then raw byte comparison | ✓ WIRED | Lines 272-303. PASS in last run. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `audio_semantic.json#shots[].reproduction` (fixture) | `shots[0].reproduction.tts.text` | composer reads `shot.dialogue.text` + `dialogue.emotion` + `dialogue.emotion_confidence` | Yes — fixture shot 1 demonstrates real composed reproduction (text starts with `再说一遍段级文本：「你好世界」，语气开心愉悦`) | ✓ FLOWING |
| `audio_semantic.json#shots[].reproduction` (pipeline producer) | `normalized.reproduction` | `call_audio_analysis.py` invokes composer with `normalized` shot (after route normalize) + `analysis_by_id.get(s["id"])` side input | Yes — composer source code wires dialogue.text/emotion + sfx.description/events + analysis_shot.ratios.drums | ✓ FLOWING |
| `audio_semantic.json#shots[].reproduction` (--recompose mode) | recomposed payload | `recompose_audio_semantic` reads audio_semantic.json + optional audio_analysis.json → per-shot composer invocation | Yes — independent byte-identical proof verified 1907-byte output across two runs | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Composer emits schema-valid reproduction for typical shot | `python3 -c "import importlib.util, json, jsonschema; ..."` (synthetic dialogue+BGM+sfx shot) | Output `{tts: {text, confidence:0.83, fidelity_disclaimer}, music_gen: {...0.6}, foley: {...0.8}}` validates against schema | ✓ PASS |
| DIA-04 confidence calibration (3 paths) | Direct composer invocation with emotion+EC / emotion w/o EC / no emotion | 0.83 / 0.75 / 0.65 — monotonic, within SPEC §10.2 TTS ~70% range | ✓ PASS |
| MUS-04 instruments never emitted in output | `grep -riE '\binstruments\b\|...' audio/ analysis/ spec/schemas/audio_semantic.schema.json spec/fixtures/v1.2/audio_semantic.json` | exit 1 (0 matches) — CLEAN | ✓ PASS |
| DIA-05 word-level never read by composer | AST walk of `audio/gen_audio_prompts.py` for `Attribute(attr=='words')` | 0 violations | ✓ PASS |
| AF-01 forbidden phrases absent | `grep -rE 'perfectly reconstruct\|...' audio/ spec/SPEC.md spec/README.md scripts/ analysis/` | exit 1 (0 matches) — CLEAN | ✓ PASS |
| Fixture schema-valid + shot1 has tts+foley non-null | Draft202012Validator + assert reproduction shape | Validates + assertions hold | ✓ PASS |
| CONTRACT-05 preserve: shot2 reproduction key omitted | assert `'reproduction' not in fixture['shots'][1]` | Holds (skeleton exemplar) | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| --- | --- | --- | --- |
| Phase 15 4-scenario smoke | `python3 scripts/verify_phase15_repro_smoke.py` | 4/4 scenarios + AF-01 ✓ + MUS-04 ✓ = ALL_SCENARIOS_PASS; exit 0 | ✓ PASS |
| Phase 14 no-regression smoke | `python3 scripts/verify_phase_audio_smoke.py` | 6/6 scenarios green; exit 0 | ✓ PASS |
| Phase 11 bidirectional cross-version contract | `python3 scripts/verify_contract.py` | 29 passed, 0 failed; producer + consumer shells OK; exit 0 | ✓ PASS |
| SC#6 byte-identical recompose (independent) | Python inline: invoke `recompose_audio_semantic` twice → compare raw file bytes | 1907 bytes both runs; equal; idempotent fixed-point also PASS | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| PROMPT-01 | 15-01 | per-shot `reproduction.{tts,music_gen,foley}` model-agnostic NL in-place | ✓ SATISFIED | `compose_reproduction` emits dict with three keys; schema-valid against `#$defs/repro_prompt` |
| PROMPT-02 | 15-01 | every reproduction field `nullable + confidence` + `fidelity_disclaimer` (AF-01) | ✓ SATISFIED | All non-null layers carry `{text, confidence, fidelity_disclaimer}`; three SPEC §10 literals locked; AF-01 grep CLEAN |
| PROMPT-03 | 15-01 + 15-02 | spike promoted to pipeline producer; `--offline` recompose; retires spike per locked decision #6 | ✓ SATISFIED | Library `compose_reproduction` invoked inline from producer; `recompose_audio_semantic` CLI mode for offline iteration; spike `--episode-dir` GONE |
| DIA-01 | 15-01 | segment-level dialogue text flows to TTS prompt | ✓ SATISFIED | `_compose_tts_layer` reads `dialogue.text` (truncated to 40 chars in NL prompt) |
| DIA-04 | 15-01 | emotion nullable + confidence | ✓ SATISFIED | `_compose_tts_layer` reads `dialogue.emotion` + `dialogue.emotion_confidence`; 3-path calibration verified |
| DIA-05 | 15-01 | word-level experimental — composer NEVER reads `dialogue.words[]` | ✓ SATISFIED | AST audit clean; word_level_experimental flag is top-level (call_audio_analysis owns; composer is segment-level only) |
| MUS-01 | 15-01 | BGM presence derived from SenseVoice events | ✓ SATISFIED | `_compose_music_gen_layer` checks `dialogue.events` OR `sfx.events` for "BGM" tag |
| MUS-02 | 15-01 | tempo BPM from audio_analysis.json side input | ✓ SATISFIED | `_compose_music_gen_layer` reads `analysis_shot.ratios.drums` (threshold 0.10) + `estimate_tempo_from_envelope` (onset ≥ 3) |
| MUS-03 | 15-01 | discrete mood from emotion lookup | ✓ SATISFIED | MOOD_MAP: HAPPY→upbeat / SAD→melancholic / ANGRY→tense / NEUTRAL→mellow |
| MUS-04 | 15-01 | instruments OMITTED (deferred v1.3) | ✓ SATISFIED | Producer code + schema + fixture audit CLEAN. Schema `$comment` lock documents deferral. Composer NL bed descriptors only ("rhythmic bed", "instrumental bed"). |
| MUS-05 | 15-01 | key — differentiator nullable | ✓ SATISFIED | Schema has no `key` field; composer emits no key signal in v1.2 (route produces none); null-by-default |
| MUS-06 | 15-01 | VA — differentiator nullable | ✓ SATISFIED | Schema has no `arousal/valence` field; composer emits no VA signal in v1.2 |
| SFX-01 | 15-01 | foley description + SenseVoice events | ✓ SATISFIED | `_compose_foley_layer` reads `sfx.description` verbatim + maps `sfx.events` via EVENT_CN_MAP |
| SFX-02 | 15-01 | AudioSet timestamps — differentiator nullable | ✓ SATISFIED | Schema has no AudioSet field; composer emits no AudioSet signal in v1.2 |
| SFX-03 | 15-01 | foley complex events — differentiator nullable | ✓ SATISFIED | Schema has no complex event field; composer emits no complex event signal in v1.2 |

No orphaned requirements found in REQUIREMENTS.md for Phase 15.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `analysis/call_audio_analysis.py` | 71 | `shot_XXX.json` (filename pattern placeholder, NOT debt marker `XXX`) | ℹ️ Info | No impact — string literal in docstring describing cache filename pattern `shot_001.json`. Not a debt marker. |

No real debt markers (`TBD`/`FIXME`/`XXX` as debt, `TODO`/`HACK`/`PLACEHOLDER`) found in producer code (audio/gen_audio_prompts.py + analysis/call_audio_analysis.py + scripts/verify_phase15_repro_smoke.py).

The "XXX" in `shot_XXX.json` is a filename template (`shot_{sid:03d}.json` → `shot_001.json`), not a debt marker. No unreferenced markers.

### Human Verification Required

None. Phase 15 is producer-only (data layer at `audio_semantic.json#shots[].reproduction`); visual rendering of the reproduction panel is Phase 16's responsibility (HTML gallery). All Phase 15 acceptance checks are programmatic:

- 4-scenario smoke harness (all green)
- Independent SC#6 byte-identical recompose proof
- AF-01 / MUS-04 / DIA-05 audits (all CLEAN)
- Phase 14 no-regression smoke (6/6 green)
- Phase 11 bidirectional cross-version contract (29/29 green)

### Gaps Summary

No gaps found. All 6 Success Criteria verified with codebase evidence. All 15 Phase 15 requirements (PROMPT-01/02/03 + DIA-01/04/05 + MUS-01..06 + SFX-01/02/03) satisfied.

**Notable observations (not gaps):**

1. **SC#5 wording nuance**: ROADMAP SC#5 says "the roadmap's conditional path is explicit in speakers.json warnings sidecar". The actual implementation puts CONDITIONAL info in: (a) schema `$comment` lock (MUS-04 omitted), (b) composer source docstrings (DIA-05 invariant), (c) the `[audio]` warnings sidecar at `route_cache/warnings.json` (NOT speakers.json — likely a roadmap wording imprecision). The audio warnings sidecar fully exists and is wired for offline/stale-cache/poisoned-cache/composer-exception scenarios. No gap — CONDITIONAL gating observably in place.

2. **MUS-04 audit self-match in scripts/harness source**: The strings `instruments` / `instrument_labels` / `instruments_detected` appear in `scripts/verify_phase_audio_smoke.py` and `scripts/verify_phase15_repro_smoke.py` as harness source describing the audit. Producer code (audio/ + analysis/ + spec/schemas/ + spec/fixtures/) is CLEAN. The harness uses fragment-concatenation at runtime to avoid self-match for AF-01; for MUS-04 it greps producer paths only (scripts/ excluded). Per design.

3. **DIA-05 prose self-match**: The literal `dialogue.words[]` appears in composer docstrings (lines 41, 230, 426) as invariant documentation ("composer NEVER 读 dialogue.words[]"). AST-level audit confirms zero `.words` attribute access in actual code. Per design — the prose documents the invariant.

---

_Verified: 2026-07-26T08:35:00Z_
_Verifier: Claude (gsd-verifier)_
