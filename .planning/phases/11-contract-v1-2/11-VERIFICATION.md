---
phase: 11-contract-v1-2
verified: 2026-07-25T15:42:55Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 11: Contract v1.2 Lock — Verification Report

**Phase Goal:** Lock the v1.2 contract — 3 new schemas + additive asset.schema extension + `SCHEMA_VERSION="1.2"` single-source + 12-file fixture + bidirectional cross-version proof + SPEC + fidelity_disclaimer — BEFORE any producer code.

**Verified:** 2026-07-25T15:42:55Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (5 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | 3 new schemas (audio_semantic, speakers, speaker-edits) draft 2020-12 + additionalProperties:false validate; asset.schema extended with optional data.audio_semantic + data.speakers (NOT in required[]) | ✓ VERIFIED | All 4 schemas pass `Draft202012Validator.check_schema`; asset.data.properties has 9 keys (audio_semantic + speakers present with anti-traversal pattern matching shots.pattern); required[] unchanged: `['shots','audio_analysis','transcript','frames','prompts']` (5 keys byte-identical to v1.0/v1.1); 3 new schemas all have `additionalProperties: false` at root + every nested object level |
| SC#2 | SCHEMA_VERSION="1.2" single-source in export_asset.py; v1.0/v1.1 fixtures byte-identical when audio_semantic.json + speakers.json absent (CONTRACT-05 graceful-degrade proof) | ✓ VERIFIED | `grep -c 'SCHEMA_VERSION = "1.2"' scripts/export_asset.py` = exactly 1; `grep -c 'SCHEMA_VERSION = '` = exactly 1 (no duplicate literal); synthetic producer smoke with empty work_dir → data keys = `['audio_analysis','frames','prompts','shots','transcript']` (5 keys, byte-identical to v1.0/v1.1) + schema_version="1.2"; no `= None` lazy-default trap (Pitfall 11 prevented) |
| SC#3 | v1.2 12-file fixture validates 12/12 under V12_ORDER; v1.1 fixture still 10/10 green under extended schemas (additive-only) | ✓ VERIFIED | `ls spec/fixtures/v1.2/ \| wc -l` = 12; 9 non-asset v1.1 substrate files byte-identical (diff-clean for shots/audio_analysis/transcript/frames/prompts/characters/props/registry.draft/registry.edits); `python3 spec/validate.py` exits 0 with output `minimal failures=0, v1.1 failures=0, v1.2 failures=0`; all 12 v1.2 fixtures validated against their schemas via direct `Draft202012Validator` |
| SC#4 | verify_contract.py bidirectional GREEN: forward (v1.1 fixture × v1.2 schema = 0 errors) + backward (v1.2 fixture × recovered-v1.1 schema = only additionalProperties) + fixture-consistency (speakers.char_id ⊆ characters.id) | ✓ VERIFIED | `python3 scripts/verify_contract.py --mode=producer` exits 0; backward filter `non_addprop = [e for e in errs if e.validator != "additionalProperties"]` confirmed load-bearing (lines 466-472) — disconfirmation: injecting shared-field drift (`media.video = {nested:object}` instead of string) caught with exit 1 + precise error; tampering probe (`char_999` in speakers.json) caught with `"Pitfall 17 — speaker→character dangling"` message, exit 1; `_recover_v11_schema` PRIMARY via `git show v1.1:...` (verified v1.1 git tag yields asset schema WITHOUT audio_semantic/speakers) + programmatic-strip fallback |
| SC#5 | SPEC.md §4 Changelog `1.2` + §5 audio_semantic/speakers shapes + fidelity_disclaimer documented (AF-01 "perfect restoration" out-of-scope) | ✓ VERIFIED | §4 Changelog `1.2` entry at SPEC.md:173 (8 bullets: 3 new schemas, additive, version literal, 3 Phase-10 deviations, spk_NNN ID space, backward-compat proof, fidelity_disclaimer cross-ref); §5.8 Audio Semantic at SPEC.md:441-501 (4-block template: Producer/顶层形状/field table/repro_prompt sub-shape/最小片段/Reference schema); §5.9 Speakers at SPEC.md:503-537 (4-block template); §10 Fidelity Disclaimer at SPEC.md:664-722 with 4 sub-sections (§10.1 AF-01 out-of-scope, §10.2 per-modality TTS~70%/music-gen~60-75%/foley~80%, §10.3 Phase-10-informed per-field context, §10.4 two-tier authority); AF-01 grep gate: 0 matches across SPEC.md + README.md for `perfectly reconstruct` / `exact restoration` / `完美复刻` / `精确复原`; README.md v1.2 footer at line 80 |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `spec/schemas/audio_semantic.schema.json` | v1.2 audio sidecar (per-shot dialogue/sfx + reproduction); `word_level_experimental` flag; NO instruments field; emotion nullable-string + confidence | ✓ VERIFIED | 167 lines; draft 2020-12 valid; `additionalProperties: false` at 7 nesting levels (root/shots.items/dialogue/words.items/sfx/reproduction/repro_prompt); `emotion: type:['string','null']` NOT enum; `emotion_confidence: ['number','null']` 0..1; top-level `word_level_experimental: boolean`; 0 instrument matches (case-insensitive) |
| `spec/schemas/speakers.schema.json` | v1.2 speaker registry; `^spk_[0-9]{3}$` acoustic ID; nullable `^char_[0-9]{3}$` link; `review_state` enum | ✓ VERIFIED | 69 lines; draft 2020-12 valid; top-level `{speakers:[...]}` shape mirrors registry.schema.json's `{clusters:[...]}`; spk_id pattern `^spk_[0-9]{3}$` enforced at 2 locations; char_id pattern `^char_[0-9]{3}$` OR null; review_state enum `[proposed/confirmed/rejected]` |
| `spec/schemas/speaker-edits.schema.json` | HITL round-trip edits shape (mirror registry-edits + `link_mappings`); drops `renames`/`type_overrides` | ✓ VERIFIED | 73 lines; draft 2020-12 valid; properties = `['confirm_ids','link_mappings','merge_groups','reject_ids','review_notes','splits']` (renames + type_overrides correctly dropped); `link_mappings` uses `patternProperties` mapping `^spk_[0-9]{3}$` → `^char_[0-9]{3}$` string (orthogonal to confirm_ids); spk pattern enforced at 8 locations |
| `spec/schemas/asset.schema.json` | Extended manifest with optional data.audio_semantic + data.speakers (NOT in required[]) | ✓ VERIFIED | 9 data properties (5 required v1.0 + 2 v1.1 additive + 2 v1.2 additive); required[] unchanged at 5 keys; anti-traversal pattern `^(?!.*\.\.)[^:*?"<>\|]+\.json$` reused verbatim from 7 existing path fields; v1.0 minimal + v1.1 fixtures still validate (forward-compat) |
| `scripts/export_asset.py` | SCHEMA_VERSION="1.2" single-source + conditional data.* emission | ✓ VERIFIED | `SCHEMA_VERSION = "1.2"` at line 56 (only literal); Phase 11 conditional emission block at lines 320-329 mirrors Phase 7 pattern; no Pitfall 11 trap; byte-identical-absent + files-present smokes both pass |
| `spec/validate.py` | 3-tier shape gate (minimal + v1.1 + v1.2) | ✓ VERIFIED | V12_FIXTURE_DIR/MAP/ORDER (12 entries) + `validate_v12()` function; main() runs all 3 tiers + counts toward exit; `[valid-v12]` prefix; exit 0 with `minimal failures=0, v1.1 failures=0, v1.2 failures=0` |
| `scripts/verify_contract.py` | Bidirectional v1.0↔v1.1↔v1.2 cross-version proof + speakers⊆characters consistency | ✓ VERIFIED | `_recover_v11_schema(shape)` at line 326 (PRIMARY git show + fallback strip); `_cross_version_check` extended at lines 428-480 (forward + backward with non-addProperties filter); `_fixture_consistency_check` extended at line 578+ (speakers.char_id ⊆ characters.id); producer mode GREEN |
| `spec/fixtures/v1.2/*` | 12-file fixture (10 byte-copied from v1.1 + audio_semantic.json + speakers.json) | ✓ VERIFIED | 12 files; 9 non-asset v1.1 substrate files byte-identical; `asset.json` schema_version="1.2" + 9 data keys + generator.version="0.3.0-spec-fixture-v1.2"; `audio_semantic.json` uses real Phase-10 spike outputs (HAPPY emotion + Speech events + WhisperX word-level from ser_sensevoice_ep01.json per_sample[2]); `speakers.json` has spk_001 (char_id=char_001 resolves to 少女) + spk_002 (char_id=null 旁白 path); all 12 fixtures schema-valid |
| `spec/SPEC.md` | §4 Changelog + §5.8/§5.9 + §10 fidelity_disclaimer + §1 schema layout bump | ✓ VERIFIED | 728 lines; §1 "13 个 schema 文件"; §4 Changelog `1.2` entry (line 173); §5.8 Audio Semantic (line 441); §5.9 Speakers (line 503); §10 Fidelity Disclaimer with 4 sub-sections (line 664); AF-01 forbidden phrases absent |
| `spec/README.md` | v1.2 update footer + 13-schema layout refresh | ✓ VERIFIED | 122 lines; v1.2 footer at line 80; 13-schema layout tree; 3 v1.2 schemas listed (2 mentions each); AF-01 phrases absent |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `asset.schema.json#properties.data.properties.audio_semantic` | `audio_semantic.schema.json` | JSON path string (`data.audio_semantic = "audio_semantic.json"`) | ✓ WIRED | data.audio_semantic has same anti-traversal pattern as shots; producer emits literal filename `"audio_semantic.json"` |
| `asset.schema.json#properties.data.properties.speakers` | `speakers.schema.json` | JSON path string (`data.speakers = "speakers.json"`) | ✓ WIRED | data.speakers pattern matches shots.pattern; producer emits `"speakers.json"` |
| `export_asset.py:build_asset_dict` | `asset.schema.json#properties.data` | conditional `data_block["audio_semantic"]` emission when file exists | ✓ WIRED | `if os.path.isfile(audio_semantic_path): data_block["audio_semantic"] = "audio_semantic.json"` (line 326-327); both directions smoke-tested |
| `fixtures/v1.2/asset.json#data.audio_semantic` | `fixtures/v1.2/audio_semantic.json` | relative path string | ✓ WIRED | `"audio_semantic": "audio_semantic.json"` in fixture; file exists + schema-valid |
| `fixtures/v1.2/speakers.json#speakers[].char_id` | `fixtures/v1.2/characters.json#[].id` | ID reference (consistency-check enforced) | ✓ WIRED | spk_001.char_id=char_001 resolves to characters.json 少女 (char_001); tampering probe with char_999 caught |
| `verify_contract.py:_cross_version_check` | `verify_contract.py:_recover_v11_schema` | function call in v1.2→v1.1 backward pass | ✓ WIRED | called at line 454; PRIMARY path via `git show v1.1:...` verified yields true v1.1 schema |
| `SPEC.md §4 Changelog 1.2 entry` | `scripts/export_asset.py:SCHEMA_VERSION` | prose cross-reference | ✓ WIRED | 6 mentions of `scripts/export_asset.py` in SPEC.md; line 176 explicitly: "版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.2"` (line 55)" |
| `SPEC.md §5.8 Audio Semantic` | `spec/schemas/audio_semantic.schema.json` | Reference schema footer | ✓ WIRED | SPEC.md:501: `Reference schema: \`spec/schemas/audio_semantic.schema.json\`` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `spec/fixtures/v1.2/audio_semantic.json` | dialogue.emotion, events, words[] | Phase-10 spike `ser_sensevoice_ep01.json` per_sample[2] (shot_id=77 HAPPY, confidence=1.0, ['Speech']) + per_sample[0] (shot_id=43 emo_unk, empty events) | Yes — real SenseVoice model outputs adapted to fixture shot IDs | ✓ FLOWING |
| `spec/fixtures/v1.2/speakers.json` | speakers[].spk_id, char_id | synthetic-but-shape-correct (no real diarize run; spike didn't run diarize per SUMMARY) | Yes — shape-correct; spk_001→char_001 (happy-path resolve), spk_002→null (旁白/群杂 path) | ✓ FLOWING |
| `scripts/export_asset.py build_asset_dict` | data_block["audio_semantic"], data_block["speakers"] | `os.path.isfile(work_dir/audio_semantic.json)` etc. | Yes — real filesystem probe; absent → key OMITTED (not None); present → emit literal filename | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 3-tier shape gate GREEN | `python3 spec/validate.py` | exit 0; `minimal failures=0, v1.1 failures=0, v1.2 failures=0` | ✓ PASS |
| Bidirectional cross-version proof GREEN | `python3 scripts/verify_contract.py --mode=producer` | exit 0; `v1.0↔v1.1↔v1.2 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors); v1.1 + v1.2 fixture set cross-file IDs consistent (0 dangling)` | ✓ PASS |
| SCHEMA_VERSION single-source | `grep -c 'SCHEMA_VERSION = "1.2"' scripts/export_asset.py` | 1 | ✓ PASS |
| All 3 new schemas valid draft 2020-12 | `python3 -c "from jsonschema import Draft202012Validator as V; import json; [V.check_schema(json.load(open(f'spec/schemas/{n}.schema.json'))) for n in ['audio_semantic','speakers','speaker-edits']]"` | exit 0 | ✓ PASS |
| All 12 v1.2 fixtures schema-valid | direct `Draft202012Validator(schema).validate(instance)` for each of 12 fixture/schema pairs | all PASS | ✓ PASS |
| Byte-identical-absent (route-down degrade) | synthetic producer smoke with empty work_dir | data.audio_semantic + data.speakers OMITTED; schema_version="1.2" | ✓ PASS |
| Files-present emission | synthetic producer smoke with both files present | both keys emitted as `"audio_semantic.json"` + `"speakers.json"` | ✓ PASS |
| Tampering probe (Pitfall 17) | inject `char_999` into speakers.json spk_001.char_id, run verify_contract | exit 1 with `"v1.2 speakers.json spk_001: char_id 'char_999' not in v1.2 characters.json IDs (Pitfall 17 — speaker→character dangling)"` | ✓ PASS |
| Shared-field drift disconfirmation | change v1.2/asset.json media.video from string to object, run verify_contract | exit 1 with `"backward v1.2→v1.1 asset: 1 non-additionalProperties error(s) (shared fields drifted); first: {'nested': 'object'} is not of type 'string'"` | ✓ PASS (filter is load-bearing) |
| AF-01 forbidden phrases | grep across SPEC.md + README.md for `perfectly reconstruct`/`exact restoration`/`完美复刻`/`精确复原` | 0 matches across both files | ✓ PASS |
| 12-file fixture count | `ls spec/fixtures/v1.2/ \| wc -l` | 12 | ✓ PASS |
| Forward-compat (v1.0 + v1.1 fixtures) | direct validate against extended asset.schema | both PASS | ✓ PASS |
| Phase-10 deviation (a): instruments omitted | `grep -ic instrument spec/schemas/{audio_semantic,speakers,speaker-edits,asset}.schema.json` | 0 matches across all 4 schemas | ✓ PASS |
| Phase-10 deviation (b): emotion nullable-string | inspect audio_semantic.schema.json dialogue.emotion | `type: ['string','null']`, no enum | ✓ PASS |
| Phase-10 deviation (c): word_level_experimental flag | top-level property in audio_semantic.schema.json | boolean flag present | ✓ PASS |
| Phase-10 deviation (d): spk_NNN acoustic ID | grep `spk_[0-9]{3}` across speakers + speaker-edits schemas | 2 + 8 = 10 occurrences | ✓ PASS |

### Probe Execution

Phase 11 is a contract-locking phase (schemas + fixtures + docs); no `scripts/*/tests/probe-*.sh` convention declared in PLAN files. Probe-style verification is replaced by behavioral spot-checks above (validate.py + verify_contract.py + tampering probes). All spot-check commands exit within seconds. Step 7c conventional-probe discovery: SKIPPED (no probe scripts declared or conventional).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CONTRACT-01 | 11-01 | `audio_semantic.json` sidecar schema — per-shot 三模态 + reproduction prompts; additive optional; byte-identical-absent 红线 | ✓ SATISFIED | `spec/schemas/audio_semantic.schema.json` exists, draft 2020-12, additionalProperties:false, locks all 3 Phase-10 deviations; v1.0/v1.1 forward-compat proven |
| CONTRACT-02 | 11-01 | `speakers.json` sidecar schema + `speaker-edits.schema.json` (HITL round-trip mirror) | ✓ SATISFIED | Both schemas exist; `^spk_[0-9]{3}$` enforced; speaker-edits mirrors registry-edits (drops renames + type_overrides; adds link_mappings); speaker-edits fixture deferred to Phase 13 (intentional — HITL flow not yet implemented) |
| CONTRACT-03 | 11-01 + 11-02 | `SCHEMA_VERSION = "1.2"` single-source; `validate.py` 3-tier shape gate; `verify_contract.py` bidirectional cross-version + fixture-consistency | ✓ SATISFIED | Single literal at export_asset.py:56; V12_ORDER 12 entries; bidirectional GREEN (forward 0 errors + backward 0 non-additive errors); speakers.char_id ⊆ characters.id enforced |
| CONTRACT-04 | 11-03 | SPEC §4 changelog + §5 shapes + `fidelity_disclaimer` documentation | ✓ SATISFIED | SPEC.md §4 Changelog 1.2 entry; §5.8 Audio Semantic + §5.9 Speakers 4-block template; §10 Fidelity Disclaimer 4 sub-sections; AF-01 forbidden phrases absent |
| CONTRACT-05 | 11-01 + 11-02 | Graceful-degrade (route-unreachable / conditional-field-model-fails → sidecar absent byte-identical to v1.0/v1.1 / field nullable; `generator.warnings` records cause) | ✓ SATISFIED | Producer conditional emission (os.path.isfile gate; no None-default trap); byte-identical-absent smoke GREEN; v1.0 minimal + v1.1 fixtures still validate against extended asset.schema; emotion/emotion_confidence/words[] all nullable; speaker-edits deferred cleanly |

**Orphaned requirements check:** REQUIREMENTS.md maps exactly CONTRACT-01..05 to Phase 11. All 5 IDs claimed in plans (11-01: CONTRACT-01/02/03/05; 11-02: CONTRACT-03/05; 11-03: CONTRACT-04). No orphaned IDs. No REQ-ID drift between REQUIREMENTS.md and PLAN frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/verify_contract.py` | 1258, 1317 | "e2e ... placeholder, 04-02 实现" / "e2e mode —— Plan 04-02 接入（替换 04-01 placeholder）" | ℹ️ Info | PRE-EXISTING from Phase 4 (e2e verification mode defer); NOT introduced by Phase 11; references documented Plan 04-02 follow-up work — not unresolved Phase 11 debt |

**No `TBD`/`FIXME`/`XXX` debt markers in any Phase 11 file.** No `TODO`/`HACK`/`PLACEHOLDER` introduced by Phase 11 (only pre-existing e2e-mode comments carried forward). No empty implementations, no console.log stubs, no hardcoded-empty data flowing to rendering.

### Human Verification Required

None required for Phase 11. This is a contract-locking phase producing schemas + fixtures + documentation; no user-visible runtime surface (HTML gallery lands in Phase 16, canvas consumer in Phase 17). All proofs are machine-checkable and have been independently run by this verifier:

- 3-tier shape gate: machine-validated (exit 0)
- Bidirectional cross-version proof: machine-validated (exit 0) + load-bearing filter confirmed via 2 disconfirmation probes
- Schema validity: machine-validated via `Draft202012Validator.check_schema`
- Producer emission: machine-validated via 2 synthetic smokes (byte-identical-absent + files-present)
- AF-01 forbidden phrases: machine-validated via grep (0 matches)
- Phase-10 deviations: machine-validated via grep + schema property inspection

The SPEC §5.8/§5.9/§10 prose is comprehensive and follows established templates; readability is high but does not require human gate (the grep gates + structural templates verify content presence + correctness).

### Gaps Summary

No gaps found. All 5 ROADMAP Success Criteria verified VERIFIED. All 5 CONTRACT-01..05 requirements SATISFIED. All artifacts exist, are substantive, are wired, and produce real data. The bidirectional cross-version proof has real teeth (load-bearing non-addProperties filter confirmed via 2 independent disconfirmation probes — one for speaker-char_id dangling, one for shared-field drift). The 4 Phase-10-informed deviations (instruments omitted, emotion nullable-string + confidence, word_level_experimental flag, spk_NNN disjoint from char_NNN) are honored in schemas AND documented honestly in SPEC §10 fidelity_disclaimer.

The contract is locked BEFORE any producer code writes against it (mirror v1.1 Phase 5 contract-first sequencing — CONTEXT § domain). Phase 12 (producer client) has a clean integration target.

**Notable observations (informational, not gaps):**

1. **speaker-edits fixture intentionally deferred to Phase 13** — the speaker-edits.schema.json exists + validates, but no `spec/fixtures/v1.2/speaker-edits.json` instance ships. This is by design (validate.py:76 comment + SPEC.md:193 + README.md:23 all document the deferral): speaker-edits is a HITL working artifact, not a canonical asset data shape, so its fixture naturally lands when Phase 13's HITL flow exists. speaker-edits is therefore NOT in V12_ORDER (correctly excluded — same v1.1 precedent that excludes the pipeline-internal `registry-edits.json` from the canonical asset data shape list except as a fixture-side substrate). NOT a gap — DOCUMENTED DEFERRAL.

2. **2 pre-existing "placeholder" comments in scripts/verify_contract.py** at lines 1258 + 1317 — these are Phase 4's documented e2e-mode deferral (references Plan 04-02 work), not Phase 11 debt. Phase 11 extended verify_contract.py without introducing new placeholder markers. NOT a blocker.

3. **Phase 11 produces ZERO producer pipeline code** (no `step_audio_semantic`, no `call_audio_analysis.py`, no `link_speakers.py`) — correct per CONTEXT § domain ("This phase produces NO producer pipeline code, NO route ML, NO HTML. It produces schemas + fixtures + contract-proof + SPEC prose."). The producer pipeline lands in Phase 12; SPEAKER-01 HITL in Phase 13; pipeline integration in Phase 14. The conditional `data_block["audio_semantic"]` / `data_block["speakers"]` emission in `export_asset.py` is the ONLY producer code touched, and it mirrors the proven Phase 7 characters/props pattern.

4. **Smoke tier shows 2 pre-existing failures** — `python3 spec/validate.py` reports `smoke failures=2` for `transcript.json` + `frames.json` missing under `output/《小江湖》第03话.../` (a producer output directory from a prior run). This is PRE-EXISTING (carried from before Phase 11; documented in 11-01-SUMMARY.md acceptance table). `strict-smoke=off` so it does not affect exit code. NOT a Phase 11 regression.

---

_Verified: 2026-07-25T15:42:55Z_
_Verifier: Claude (gsd-verifier)_
