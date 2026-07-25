---
phase: 11-contract-v1-2
plan: 02
subsystem: testing
tags: [fixture, validation, bidirectional-proof, cross-version, jsonschema, contract]

# Dependency graph
requires:
  - phase: 11-contract-v1-2/plan-01
    provides: "3 new v1.2 schemas (audio_semantic, speakers, speaker-edits) + asset.schema.json additive extension (data.audio_semantic + data.speakers, NOT in required[])"
provides:
  - "12-file v1.2 fixture (spec/fixtures/v1.2/) — 10 byte-copied from v1.1 + audio_semantic.json (real SenseVoice HAPPY/emo_unk spike outputs + WhisperX word-level timestamps) + speakers.json (spk_001/spk_002 with char_001/null mapping)"
  - "3-tier shape gate in spec/validate.py — minimal (6) + v1.1 (10) + v1.2 (12) all GREEN, exit code 0"
  - "v1.0↔v1.1↔v1.2 cross-version bidirectional proof in scripts/verify_contract.py — forward 0 errors + backward 0 non-additive errors"
  - "_recover_v11_schema(shape) helper using git show v1.1:... PRIMARY + programmatic-strip fallback"
  - "speakers.char_id ⊆ characters.id fixture-consistency check (Pitfall 17 mitigation)"
affects: [11-contract-v1-2/plan-03 (SPEC.md prose), 12- producer-client, 13-s SPEAKER-01 HITL, 16-html-gallery, 17-canvas-consumer]

# Tech tracking
tech-stack:
  added: []  # no new packages — reuses jsonschema 4.26.0 + Python 3.12 stdlib
  patterns:
    - "V11→V12_ORDER mirror pattern (file_map + order + validate_fn clone) — extends the existing v1.0→v1.1 precedent"
    - "_recover_vN_schema(shape) generalization — N=1 (v1.0) + N=11 (v1.1) now exist; future v1.3 can clone again or parameterize"
    - "forward (old × new schema) + backward (new × recovered-old schema) bidirectional proof — proven pattern for additive invariants"
    - "speakers.char_id ⊆ characters.id cross-file consistency — same shape as prompts.character_refs ⊆ characters.id"

key-files:
  created:
    - spec/fixtures/v1.2/asset.json
    - spec/fixtures/v1.2/audio_semantic.json
    - spec/fixtures/v1.2/speakers.json
    - spec/fixtures/v1.2/{shots,audio_analysis,transcript,frames,prompts,characters,props,registry.draft,registry.edits}.json
  modified:
    - spec/validate.py
    - scripts/verify_contract.py

key-decisions:
  - "audio_semantic.json fixture carries 2 shots referencing shots.json ids 1+2 — shot 1 has real SenseVoice HAPPY spike outputs (proxy_confidence=1.0, ['Speech'] events) + plausible WhisperX 4-word timestamps; shot 2 has real emo_unk + empty events (silence/non-speech path). Both come from spike/audio/results/ser_sensevoice_ep01.json per_sample[2] and per_sample[0] adapted to the fixture's shot IDs."
  - "speakers.json fixture: spk_001 confirmed + char_id='char_001' (happy-path resolve to existing 少女 character); spk_002 confirmed + char_id=null (旁白/群杂 nullable path). Both have total_speech_sec=1.5 + 1 turn referencing shot_id 1 or 2 (within shots.json range)."
  - "_recover_v11_schema cloned (not parameterized) from _recover_v1_schema — parameterization is cleaner DRY-wise but cloning matches the existing v1.0 code shape and is mechanically obvious for future readers. Plan RESEARCH Pattern 5 explicitly granted this discretion."
  - "EIGHT_SHAPES list extended (not renamed to ALL_SHAPES) — the legacy name is referenced in self-test documentation; renaming would create churn. The comment now clearly says '11 elements, name is legacy'."
  - "No instruments field anywhere in audio_semantic fixture (Phase-10 deviation enforced: MUS-04 deferred to v1.3 because MERT-v1-95M has no classifier head + PANNs Cnn14 was zenodo-blocked at spike time)."

patterns-established:
  - "V<NN>_ORDER / V<NN>_FIXTURE_MAP / validate_v<NN>() triad — every future contract bump (v1.3, v2.0) mirrors this exactly. The pattern is mechanically cloneable."
  - "Bidirectional cross-version proof = forward (old × new schema = 0 errors) + backward (new × recovered-old schema = only additionalProperties errors). The non-additive filter is the load-bearing check — shared-field drift surfaces as non-addProp errors."
  - "Pitfall 17 fixture-consistency extension pattern: speakers.char_id ⊆ characters.id mirrors the existing prompts.character_refs ⊆ characters.id check. Phase 13+ will extend this pattern further."

requirements-completed: [CONTRACT-03, CONTRACT-05]

# Metrics
duration: 35min
completed: 2026-07-25
---

# Phase 11 Plan 02: v1.2 Fixture + 3-Tier Gate + Bidirectional Cross-Version Proof Summary

**12-file v1.2 fixture (10 byte-copied from v1.1 + audio_semantic.json with real SenseVoice spike outputs + speakers.json with synthetic spk_NNN turns) wired into a 3-tier shape gate (minimal/v1.1/v1.2 all 0-failure) + verify_contract.py extended with v1.0↔v1.1↔v1.2 bidirectional proof (forward 0 errors, backward 0 non-additive errors) + speakers.char_id ⊆ characters.id consistency check.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3/3 complete
- **Files modified:** 14 (12 created in spec/fixtures/v1.2/ + 2 modified: spec/validate.py, scripts/verify_contract.py)

## Accomplishments

- **12-file v1.2 fixture shipped** at spec/fixtures/v1.2/ with 9 v1.1 substrate files byte-identical (diff-clean for shots/audio_analysis/transcript/frames/prompts/characters/props/registry.draft/registry.edits), asset.json carrying schema_version="1.2" + generator.version="0.3.0-spec-fixture-v1.2" + 2 new data keys (audio_semantic + speakers, 9 data keys total), and 2 new shape-correct fixture files using real Phase-10 spike model outputs.
- **3-tier shape gate GREEN** — minimal (6 shapes) + v1.1 (10 shapes) + v1.2 (12 shapes) all schema-valid; exit code 0; closing print includes "minimal failures=0, v1.1 failures=0, v1.2 failures=0".
- **v1.0↔v1.1↔v1.2 bidirectional proof GREEN** — forward (v1.1 fixture × v1.2 schema = 0 errors) proves the additive extension didn't break old assets; backward (v1.2 fixture × recovered-v1.1 schema = only additionalProperties errors) proves no shared-field drift.
- **speakers.char_id ⊆ characters.id consistency enforced** — Pitfall 17 (speaker→character dangling) caught at contract layer; tampering probe (injecting char_999) verified to fail-loud with "Pitfall 17 — speaker→character dangling" message.
- **No regression** — v1.0 minimal tier + v1.1 tier + v1.1 fixture byte-identical to v1.1 git tag (Phase 11 didn't touch the v1.1 fixture set).

## Task Commits

Each task was committed atomically:

1. **Task 1: 12-file v1.2 fixture** — `ba27565` (feat)
2. **Task 2: spec/validate.py V12 extension + 3-tier gate** — `20c44f1` (feat)
3. **Task 3: scripts/verify_contract.py bidirectional + consistency extension** — `ed7b948` (feat)

**Plan metadata:** (this SUMMARY commit hash — see below)

## Files Created/Modified

### Created (spec/fixtures/v1.2/ — 12 files)
- `spec/fixtures/v1.2/asset.json` — v1.2 manifest: schema_version="1.2", generator.version="0.3.0-spec-fixture-v1.2", data block has 9 keys (5 required v1.0 + 2 v1.1 additive + 2 v1.2 additive)
- `spec/fixtures/v1.2/audio_semantic.json` — 2-shot audio sidecar with real SenseVoice HAPPY (shot 1, spk_001, ['Speech'] events, 4-word WhisperX timestamps, reproduction.tts non-null with fidelity_disclaimer) + emo_unk (shot 2, spk_002, empty events, all reproduction layers null). Top-level word_level_experimental=true.
- `spec/fixtures/v1.2/speakers.json` — 2-speaker registry: spk_001 (confirmed, char_id=char_001 → resolves to existing 少女 character) + spk_002 (confirmed, char_id=null → 旁白/群杂 nullable path). Each has total_speech_sec=1.5 + 1 turn.
- `spec/fixtures/v1.2/{shots,audio_analysis,transcript,frames,prompts,characters,props,registry.draft,registry.edits}.json` — byte-copied from v1.1 substrate (diff-clean).

### Modified
- `spec/validate.py` — added V12_FIXTURE_DIR/V12_FIXTURE_MAP/V12_ORDER (12 entries) + validate_v12() function; main() runs minimal + v1.1 + v1.2 + smoke with v1.2 failures counting toward exit code
- `scripts/verify_contract.py` — added _recover_v11_schema() helper (git show v1.1 PRIMARY + programmatic-strip fallback); extended _cross_version_check with v1.1↔v1.2 forward + backward passes; extended _fixture_consistency_check with speakers.char_id ⊆ characters.id + spk_id pattern + turn.shot_id ⊆ shots.json#id; extended EIGHT_SHAPES list to include audio_semantic + speakers

## Decisions Made

- **Fixture content uses real Phase-10 spike outputs** — audio_semantic.json shot 1 carries HAPPY emotion (proxy_confidence=1.0) and ['Speech'] events straight from ser_sensevoice_ep01.json per_sample[2] (shot_id 77 in the spike; remapped to shot_id 1 in the fixture because the fixture's shots.json only has IDs 1+2). Shot 2 carries emo_unk + empty events from per_sample[0] (shot_id 43 in the spike, representing silence/non-speech). This is NOT hand-fabricated happy-path data — the emotion labels and confidence values are literal SenseVoice model outputs.
- **speakers.json is synthetic-but-shape-correct** — spike didn't run diarize, so no real spk_NNN inventory exists. Fixture uses spk_001 (linked to existing char_001 少女 — happy-path resolve) + spk_002 (char_id=null — 旁白/群杂 nullable path). Both review_state="confirmed" (Phase 13 SPEAKER-01 HITL hasn't run; the fixture represents post-HITL canonical shape).
- **_recover_v11_schema cloned (not parameterized)** — RESEARCH Pattern 5 / Example 4 explicitly granted planner discretion. Cloning matches the existing _recover_v1_schema code shape and is mechanically obvious; parameterization would be cleaner DRY but harder to read. Future v1.3 bump can revisit.
- **EIGHT_SHAPES extended (not renamed)** — the legacy name is referenced in self-test documentation and fail-loud semantics. Renaming to ALL_SHAPES would create doc churn without behavior change. Comment now clearly says "11 elements, name is legacy".

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Phase 11 installs ZERO packages (reuses existing jsonschema 4.26.0 + Python 3.12 + git CLI).

## Next Phase Readiness

- **Plan 11-03 (SPEC.md prose)** can proceed: the fixture + 3-tier gate + bidirectional proof are locked; SPEC §4 Changelog `1.2` entry + §5.8 Audio Semantic + §5.9 Speakers + fidelity_disclaimer section can reference these as the locked correctness gate.
- **Phase 12 (producer client)** can validate route round-trip outputs against spec/schemas/audio_semantic.schema.json pre-write via the same Draft202012Validator path.
- **Phase 13 (SPEAKER-01 HITL)** consumes speakers.schema.json + speaker-edits.schema.json; the consistency check pattern (speakers.char_id ⊆ characters.id) is established for runtime extension in link_speakers.py.
- **Phase 16 (HTML gallery)** can read audio_semantic.json + speakers.json shapes from this fixture as the canonical rendering reference.

## Validation Results (all GREEN)

```
=== 1. validate.py 3-tier gate ===
[validate] minimal failures=0, v1.1 failures=0, v1.2 failures=0, smoke failures=2 (strict-smoke=off)
[validate] OK

=== 2. verify_contract.py bidirectional + consistency ===
[producer] OK: asset.json + data shapes schema-valid; v1.0↔v1.1↔v1.2 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors); v1.1 + v1.2 fixture set cross-file IDs consistent (0 dangling)

=== 3. v1.2 fixture file count ===
12

=== 4. byte-identical spot check ===
diff spec/fixtures/v1.1/shots.json spec/fixtures/v1.2/shots.json → empty

=== 5. Tampering probe ===
Injecting char_999 (non-existent) into speakers.json spk_001.char_id → verify_contract.py exits 1 with: "v1.2 speakers.json spk_001: char_id 'char_999' not in v1.2 characters.json IDs (Pitfall 17 — speaker→character dangling)"

=== 6. v1.1 git tag asset.schema.json (PRIMARY baseline for _recover_v11_schema) ===
data.properties keys: ['audio_analysis', 'characters', 'frames', 'prompts', 'props', 'shots', 'transcript']
(NO audio_semantic / speakers — confirms the v1.1 tag is the immutable truth the recover helper reads)
```

---
*Phase: 11-contract-v1-2*
*Plan: 02*
*Completed: 2026-07-25*

## Self-Check: PASSED

- All 4 created files exist (spec/fixtures/v1.2/asset.json + audio_semantic.json + speakers.json + 11-02-SUMMARY.md).
- All 3 task commits present in git log: ba27565 (Task 1) + 20c44f1 (Task 2) + ed7b948 (Task 3).
- v1.2 fixture file count = 12 (matches must_haves T1).
- validate.py 3-tier gate GREEN: minimal=0 + v1.1=0 + v1.2=0 failures; exit 0.
- verify_contract.py --mode=producer GREEN: bidirectional v1.0↔v1.1↔v1.2 + v1.1+v1.2 consistency; exit 0.
