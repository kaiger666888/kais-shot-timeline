---
phase: 11-contract-v1-2
plan: 03
subsystem: docs
tags: [spec, prose, contract, fidelity-disclaimer, changelog, two-tier-authority, af-01]

# Dependency graph
requires:
  - phase: 11-contract-v1-2/plan-01
    provides: "3 new v1.2 schemas (audio_semantic.schema.json + speakers.schema.json + speaker-edits.schema.json) + asset.schema.json additive (data.audio_semantic + data.speakers, NOT in required[]) + SCHEMA_VERSION=\"1.2\" single-source at scripts/export_asset.py:55"
  - phase: 11-contract-v1-2/plan-02
    provides: "12-file v1.2 fixture + bidirectional v1.0↔v1.1↔v1.2 cross-version proof (forward 0 errors / backward 0 non-additive) + speakers.char_id ⊆ characters.id consistency"
  - phase: 10/plan-06
    provides: "Phase 10 audio spike outcomes — SenseVoice self_consistency=100% (label-stability proxy, NOT macro-F1), WhisperX boundary drift median 101.5ms (per-word drift metric-definition artifact), MERT no classifier head + PANNs zenodo-blocked (MUS-04 defer)"
provides:
  - "spec/SPEC.md §4 Changelog 1.2 entry mirroring the 1.1 entry structure (pure-additive claim + 3 new schemas + asset.schema additive + Phase-10 deviations + backward-compat proof status + single-source literal cross-ref)"
  - "spec/SPEC.md §5.8 Audio Semantic (1.2) shape section — 4-block template (Producer / 顶层形状 / field table incl. repro_prompt sub-shape / 最小片段 from v1.2 fixture / Reference schema)"
  - "spec/SPEC.md §5.9 Speakers (1.2) shape section — 4-block template (acoustic spk_NNN + nullable char_id + turns + review_state)"
  - "spec/SPEC.md §10 Fidelity Disclaimer — AF-01 absolute-restoration phrases FORBIDDEN; per-modality estimates TTS~70%/music-gen~60-75%/foley~80%; emotion=calibrated estimate (NOT rigorous macro-F1); word-level=experimental (segment-level is SLA); instruments=absent (MUS-04 defer v1.3)"
  - "spec/SPEC.md §1 schema layout bumped 9 → 13 schemas (3 new v1.2 rows marked **1.2** matching v1.1 convention)"
  - "spec/README.md v1.2 update footer mirroring v1.1 pattern + Layout tree refreshed to 13 schemas + 12-file v1.2 fixture block"
affects:
  - "12-producer-client (call_audio_analysis.py validates against audio_semantic.schema.json before write)"
  - "13-SPEAKER-01 HITL (link_speakers.py consumes speaker-edits.schema.json, writes speakers.schema.json)"
  - "16-html-gallery (renders audio_semantic + speakers + §10 fidelity framing)"
  - "17-canvas-consumer (recognizes schema_version:'1.2', reads §10 before trusting fields)"

# Tech tracking
tech-stack:
  added: []  # pure docs — ZERO packages, ZERO code
  patterns:
    - "§4 Changelog entry format mirror — 1.2 entry is a line-for-line structural clone of the 1.1 entry (date — version(flavor) header + bullet list of new schemas / additive / pattern / backward-compat / deviations)"
    - "§5 shape 4-block template reuse — §5.8 + §5.9 follow the exact Producer / 顶层形状 / Field table / 最小片段 / Reference schema structure established by §5.6 Characters + §5.7 Props"
    - "fidelity_disclaimer as PROSE not schema field — two-tier authority enforced (machine-checkable nullable+confidence in schema; human-readable framing in SPEC §10 + per-prompt reproduction.<layer>.fidelity_disclaimer string in schema for UI rendering)"
    - "AF-01 forbidden-phrase grep gate — 0 matches across SPEC.md + README.md for 完美复刻 / 精确复原 / perfectly reconstruct / exact restoration (documenting the rule without printing the literals)"

key-files:
  created:
    - .planning/phases/11-contract-v1-2/11-03-SUMMARY.md
  modified:
    - spec/SPEC.md
    - spec/README.md

key-decisions:
  - "AF-01 forbidden phrases are documented BY CATEGORY not by literal quote — the SPEC §10.1 prose describes the forbidden absolute-restoration category (绝对化复现措辞) without printing the literal 4 phrases, because printing them would itself violate the grep invariant. The grep gate is the authoritative check."
  - "fidelity_disclaimer placed as new §10 top-level section (not §4.1 sub-section) — keeps the §4 Changelog clean (it cross-references §10) and gives the disclaimer its own first-class address that Phase 16/17 consumers can deep-link to."
  - "§5.8 audio_semantic field table lists the repro_prompt $defs sub-shape inline as a secondary table — mirrors how §5.3 Transcript handles backend enum and §5.4 frames handles base64 pattern. Avoids cross-referencing readers away from the shape section."
  - "§5.9 speakers field table cross-references DINOv2 vs WhisperX/pyannote modality distinction — makes the deliberate ^spk_NNN vs ^char_NNN disjoint-ID rule obvious to a reader who only reads the prose (closes SPEAKER-01 future contributor surprise)."
  - "v1.2 fixture 'realistic content' is sourced from the actual v1.2 fixture (audio_semantic.json shot 1 HAPPY + 4 word-level timestamps + reproduction.tts confidence=0.7 + fidelity_disclaimer string; speakers.json spk_001→char_001 + spk_002 旁白) — NOT a hypothetical example, so the prose and fixture stay in sync."
  - "README Layout tree correction — the v1.1 fixtures/ block was undercounted in the prior README (said 9 JSON but registry.edits.json was already present making it 10); this plan corrected it to 10 alongside adding the 12-file v1.2 block."

# Metrics
metrics:
  duration: ~25min
  started-utc: "2026-07-25T15:33:57Z"
  completed-utc: "2026-07-25T15:58:00Z"
  task-count: 2
  file-count: 2
  commit-count: 2

---

# Phase 11 Plan 03: Contract v1.2 Prose (SPEC.md + README.md) Summary

SPEC.md §4 Changelog `1.2` entry + §5.8 Audio Semantic + §5.9 Speakers + §10 Fidelity Disclaimer + §1 schema layout bump to 13, plus README.md v1.2 update footer + Layout tree refresh — the human-readable half of the two-tier authority for v1.2.

## What was built

### Task 1 — spec/SPEC.md (commit `acff569`)

Six edits to the existing v1.1 SPEC.md:

1. **§1 Authority & Schema Layout** — table extended from 9 to 13 rows; the three new v1.2 schemas (`audio_semantic.schema.json`, `speakers.schema.json`, `speaker-edits.schema.json`) added with one-line descriptions and `**\`1.2\`**` annotation matching the v1.1 convention; "9 个 schema 文件" → "13 个 schema 文件" header + downstream-TS-types note updated.

2. **§4 Changelog** — new `1.2` entry dated 2026-07-25 appended after the `1.1` entry, mirroring the literal template (date — `version`(flavor) header + bullet list). Documents: 3 new schemas / `asset.schema.json` additive (`data.audio_semantic` + `data.speakers`, NOT in `required[]`, byte-identical to v1.0/v1.1) / `schema_version` pattern unchanged + literal locked at `scripts/export_asset.py:SCHEMA_VERSION = "1.2"` (line 55) / backward-compat proof (v1.0 minimal 6/6 + v1.1 10/10 + v1.2 12/12 + bidirectional v1.0↔v1.1↔v1.2 GREEN + speakers.char_id ⊆ characters.id consistency GREEN) / Phase-10-informed deviations as a NON-NEGOTIABLE sub-block (instruments field OMITTED + emotion nullable-string + word_level_experimental flag).

3. **§5 intro** — appended a v1.2 paragraph naming §5.8 + §5.9 as optional audio branch shapes, cross-referencing §10 for fidelity boundaries.

4. **§5.8 Audio Semantic (`1.2`)** — full 4-block template: Producer (`audio/call_audio_analysis.py` Phase 12+15) / 顶层形状 / Field table (covering `schema_version`, `word_level_experimental`, `shots[]`, `dialogue.{text,spk_id,emotion,emotion_confidence,events,words[]}`, `sfx.{events,description}`, `reproduction.{tts,music_gen,foley}` + a secondary table for the `repro_prompt` $defs sub-shape) / 最小片段 (referencing `spec/fixtures/v1.2/audio_semantic.json` shot 1 + 2) / Reference schema.

5. **§5.9 Speakers (`1.2`)** — full 4-block template: Producer (`registry/link_speakers.py` Phase 13) / 顶层形状 / Field table (covering `speakers[]`, `spk_id`, nullable `char_id`, `total_speech_sec`, `review_state`, `turns[]`, with explicit cross-reference to the deliberate `^spk_[0-9]{3}$` vs `^char_[0-9]{3}$` disjoint-ID rule) / 最小片段 (referencing `spec/fixtures/v1.2/speakers.json` 2-speaker example) / Reference schema.

6. **§10 Fidelity Disclaimer (`1.2`)** — new top-level section (AF-01/AF-02/AF-03 mitigation), structured as:
   - **§10.1** — AF-01 explicit out-of-scope: absolute-restoration phrases (perfectly reconstruct / exact restoration / 完美复刻 / 精确复原 and their category) FORBIDDEN in README/SPEC/HTML; documented by category not literal quote (printing literals would violate the grep invariant).
   - **§10.2** — Per-modality estimates table (TTS ~70% / music-gen ~60-75% / foley ~80%) with meaning + limitations columns.
   - **§10.3** — Phase-10-informed per-field fidelity context: `emotion` = calibrated estimate (SenseVoice self_consistency=100% is label-stability proxy, NOT rigorous macro-F1; verbatim mirrored from `audio-spike-report.md` §1); `dialogue.words[]` = EXPERIMENTAL (WhisperX boundary drift median 101.5ms, aggregate per-word drift is metric-definition artifact); `instruments` field OMITTED (MUS-04 defer v1.3 — MERT-v1-95M no classifier head, PANNs Cnn14 zenodo-blocked).
   - **§10.4** — Two-tier authority restatement: `fidelity_disclaimer` is prose NOT schema field; schema wins on conflict; lists the 3 machine-checkable nullable+confidence locations in schema.

### Task 2 — spec/README.md (commit `8577585`)

Two edits:

1. **Layout tree** — refreshed from 9 to 13 schemas (3 new v1.2 schemas added with one-liners); v1.1 fixtures/ block count corrected 9 → 10 (`registry.edits.json` was already there); new v1.2 fixtures/ block added (12 JSON, referencing `audio_semantic.json` + `speakers.json`); footer reference to SPEC.md updated to mention §5.8/§5.9/§10.

2. **`## v1.2 Update (Phase 11, 2026-07-25)` section** — appended after the v1.1 footer blockquote, mirroring the v1.1 pattern. Documents: 3 new schemas / `asset.schema.json` additive (NOT in `required[]`) / `SCHEMA_VERSION = "1.2"` single-source at `scripts/export_asset.py:55` / Phase-10-informed deviations (NON-NEGOTIABLE) / 12-file fixture / bidirectional cross-version proof / per-field fidelity boundaries (with cross-link to SPEC §10).

## CONTRACT-04 acceptance

CONTRACT-04 fully covered:
- ✅ SPEC §4 Changelog `1.2` entry (mirrors `1.1` format, all required content present).
- ✅ SPEC §5 audio_semantic + speakers shapes added (§5.8 + §5.9).
- ✅ `fidelity_disclaimer` documented as first-class prose (§10).
- ✅ AF-01 'perfect restoration' explicitly out-of-scope (§10.1 + grep gate).

## AF-01 / AF-02 / AF-03 invariants (Out-of-Scope threat mitigations)

| Invariant | Mitigation | Verification |
|-----------|------------|--------------|
| **AF-01** (forbidden absolute-restoration phrases) | §10.1 + README v1.2 footer document the rule by category; SPEC/README grep for 完美复刻 / 精确复原 / perfectly reconstruct / exact restoration | `grep -cE` returns **0** across both files |
| **AF-02** (强制每镜都有情绪) | §10.3 + §5.8 field table mark `emotion` + `emotion_confidence` as nullable | Schema-side nullable enforced since Plan 01; prose side documents the rationale |
| **AF-03** (强制每镜都有乐器) | §10.3 explicitly states `instruments` field ABSENT from v1.2 schema (MUS-04 deferred v1.3) | `grep -ci 'instrument' spec/SPEC.md` returns 7 — all in OMITTED/absent/deferred context (manual review confirms) |

## Threat model mitigation verification

| Threat ID | Mitigation | Status |
|-----------|------------|--------|
| **T-11-09** (Information Disclosure — false advertising) | AF-01 grep gate; `fidelity_disclaimer` section names the forbidden category | GREEN — 0 forbidden phrase matches across SPEC + README |
| **T-11-10** (Repudiation — SPEC/schema drift) | §5.8 field table sourced verbatim from `audio_semantic.schema.json#properties`; §10.4 restates two-tier authority | GREEN — `grep -ci 'instrument'` all matches in OMITTED context (no field documented that schema rejects) |
| **T-11-11** (Information Disclosure — consumer mis-trusts fields) | §10 fidelity_disclaimer is a first-class deliverable; §5.8 field table cross-references §10 for each Phase-10 deviation field | GREEN — every v1.2 field with calibration limits has a §10 cross-reference |
| **T-11-SC** (Tampering — pip / package installs) | Plan installs ZERO packages | N/A — no package operations performed |

## Deviations from Plan

None — plan executed exactly as written. All 6 SPEC.md edits + 2 README.md edits completed; all automated verification + acceptance grep gates + regression gates GREEN.

One self-correction during execution: the initial draft of §10.1 + README v1.2 footer quoted the forbidden phrases verbatim to name them as forbidden — which itself violated the AF-01 grep invariant. Fixed by rewording to describe the absolute-restoration **category** (绝对化复现措辞 / perfect clone / exact source match) without printing the literal 4 grep-targeted phrases. The grep gate remains the authoritative check.

## Grep gate results (final)

| Gate | Expected | Actual |
|------|----------|--------|
| `` `1.2` `` backticks in SPEC.md | ≥5 | **8** |
| `fidelity_disclaimer` in SPEC.md | ≥3 | **11** |
| `word_level_experimental` in SPEC.md | ≥2 | **8** |
| `instrument` (ci) in SPEC.md | ≥2 (all OMITTED context) | **7** (manual review: all in OMITTED/absent/deferred context) |
| `spk_[0-9]` in SPEC.md | ≥2 | **5** |
| AF-01 forbidden phrases in SPEC.md | =0 | **0** |
| `scripts/export_asset.py` in SPEC.md | ≥1 | **6** |
| 3 schemas named in SPEC.md | ≥3 | **9** |
| `v1.2` in README.md | ≥3 | **11** |
| 3 schemas named in README.md | ≥1 each | **2 / 2 / 2** |
| AF-01 forbidden phrases in README.md | =0 | **0** |
| 3 schemas across SPEC + README | ≥6 | **9** |

## Pre-existing gates (no regression)

```
[validate] minimal failures=0, v1.1 failures=0, v1.2 failures=0, smoke failures=2 (strict-smoke=off)
[validate] OK
[verify-contract] producer OK: asset.json + data shapes schema-valid; v1.0↔v1.1↔v1.2 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors); v1.1 + v1.2 fixture set cross-file IDs consistent (0 dangling)
```

## Self-Check: PASSED

- ✅ `spec/SPEC.md` exists and contains §4 Changelog `1.2` entry + §5.8 Audio Semantic + §5.9 Speakers + §10 Fidelity Disclaimer + §1 13-schema table.
- ✅ `spec/README.md` exists and contains v1.2 Update footer + 13-schema Layout tree.
- ✅ Commit `acff569` exists (Task 1 — SPEC.md).
- ✅ Commit `8577585` exists (Task 2 — README.md).
- ✅ AF-01 forbidden phrases absent from both files (grep returns 0).
- ✅ `python3 spec/validate.py` GREEN (no regression).
- ✅ `python3 scripts/verify_contract.py --mode=producer` GREEN (no regression).
