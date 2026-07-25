# Phase 11: Contract v1.2 - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — contract-locking phase; shape forced by Phase 10 outcomes + v1.1 Phase 5 patterns + ROADMAP success criteria. All recommendations accepted per user momentum preference ("按你建议先来").

<domain>
## Phase Boundary

Lock the v1.2 contract BEFORE any producer code writes against it (mirror v1.1 Phase 5 contract-first). Deliverables: 3 new schemas (`audio_semantic`, `speakers`, `speaker-edits`) + additive `asset.schema.json` extension + `SCHEMA_VERSION = "1.2"` single-source + 12-file fixture (v1.1's 10 + `audio_semantic.json` + `speakers.json`) + bidirectional cross-version proof in `verify_contract.py` + SPEC.md §4 Changelog `1.2` + §5 shapes + `fidelity_disclaimer`.

This phase produces NO producer pipeline code, NO route ML, NO HTML. It produces schemas + fixtures + contract-proof + SPEC prose. The contract is the integration target for Phase 12 (producer client) and Phase 16 (HTML gallery) and Phase 17 (canvas consumer).

**The spike-before-contract invariant (non-negotiable #1):** Phase 10's empirical outcomes directly reshape the v1.2 field shapes — the contract is NOT the v1.1-pattern mechanical copy the ROADMAP dependency note sketched. Two Phase-10-informed deviations from that note are locked below (instruments omitted; emotion is string-not-enum).

</domain>

<decisions>
## Implementation Decisions

### Schema shapes — Phase-10-informed (the core of this phase)

- **dialogue.emotion = `type: string` (NOT enum).** SenseVoice self-consistency=100% is a label-stability proxy, NOT calibrated accuracy (DIA-04 ship-nullable+confidence). A closed 7-class enum would over-claim calibration we do not have. `emotion` is **nullable** + paired with `emotion_confidence: number` (0..1). The `fidelity_disclaimer` applies. *(Phase 10 evidence: ser_sensevoice_ep01.json methodology_ab; PROJECT.md DIA-04 row.)*
- **instruments field = OMITTED from v1.2.** MUS-04 deferred to v1.3. MERT-v1-95M has NO instrument classifier head (spike only produced duration-correlated K-means clusters); PANNs Cnn14 was zenodo-blocked. There is no instrument signal to contract yet. **This deviates from the ROADMAP Phase-11 dependency note** ("instruments as `list[{label,confidence}]`") — that note predated the spike; the spike overrules it. Do NOT add an `instruments` field to `audio_semantic.schema.json` or `asset.schema.json`. *(Phase 10 evidence: mir_mert_ep01.json + mir_panns_ep01.json status=blocked; PROJECT.md MUS-04 defer row.)*
- **dialogue.words (word-level timestamps) = EXPERIMENTAL optional sub-field.** DIA-05 ship-experimental. `words: [{start, end, text, score}]` is OPTIONAL under each dialogue segment (segment-level remains the SLA path). A top-level `word_level_experimental: boolean` flag marks the whole `audio_semantic.json` when word-level is present, so consumers can graceful-degrade. *(Phase 10 evidence: whisperx_align_ep01.json — boundary drift median 101.5ms, dense bucket 93.3%; aggregate per-word metric is a definition artifact.)*
- **dialogue.events = `array<string>` (SenseVoice 8-event tags).** SenseVoice ran cleanly on ep01. Events: Speech/BGM/Applause/Laughter/Cry/Sneeze/Breath/Cough (the 8 SenseVoice classes). Free-string (not enum) for forward-compat.
- **sfx sub-object:** SenseVoice events + (future) PANNs 527-class. For v1.2, sfx is the SenseVoice `events` projection (non-speech events). Keep minimal — no PANNs multi-label yet (blocked).
- **music sub-object:** OMITTED in v1.2 (instruments deferred → no music content to contract). Reserve the key as a documented future slot in SPEC.md §5 but do NOT add to the schema (`additionalProperties:false` would reject it anyway; documenting intent in SPEC is enough).

### speakers + speaker-edits schemas (new ID space)

- **`speakers.schema.json`** — per-shot acoustic speaker turns using a NEW `^spk_[0-9]{3}$` ID space (NOT reusing `^char_[0-9]{3}$` — avoids identity-signal conflation per Phase 13 goal). Schema: `{shot_id, turns:[{start, end, spk_id}]}` per shot, or a top-level `{speakers:[{spk_id, total_speech_sec}], turns_per_shot:[...]}`. Exact shape at planner's discretion but the `spk_NNN` regex is locked.
- **`speaker-edits.schema.json`** — HITL confirmed edits (mirror `registry-edits.schema.json` pattern): confirmed `spk_id → char_id` links + status (confirmed/rejected/pending). Phase 13 consumes this; Phase 11 just defines the contract.

### Contract mechanics (mirror v1.1 Phase 5 — proven patterns)

- **`SCHEMA_VERSION = "1.2"`** single-source in `scripts/export_asset.py` (currently `"1.1"`). Schema pattern unchanged (`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`). This is a minor bump (pure-additive).
- **`asset.schema.json` additive extension:** optional `data.audio_semantic` + `data.speakers` (both NOT in `required[]`). v1.0/v1.1 fixtures remain **byte-identical** when these are absent (CONTRACT-05 graceful-degrade proof — Pitfall 11 prevented, same as v1.1's characters/props addition).
- **3 new schemas:** `audio_semantic.schema.json`, `speakers.schema.json`, `speaker-edits.schema.json` — all draft 2020-12, `additionalProperties: false` (consistency with the 10 existing schemas).
- **12-file fixture** under `spec/fixtures/v1.2/`: copy v1.1's 10 files + add `audio_semantic.json` + `speakers.json`. Use ep01 Phase-10 spike results as realistic fixture content (real emotion/event predictions, real drift-shaped word timestamps, synthetic-but-shape-correct spk_NNN turns). `V12_ORDER` list constant mirrors `V11_ORDER`.
- **`verify_contract.py` bidirectional cross-version self-test:** forward (v1.1 fixture × v1.2 schema = 0 errors — additive proof) + backward (v1.2 fixture × recovered-v1.1 schema = ONLY additionalProperties errors, nothing else — proves no breaking change) + fixture-consistency (`speakers.char_id ⊆ characters.id` where characters present).
- **SPEC.md:** §4 Changelog `1.2` entry (additive: 3 schemas + asset extension + experimental word-level + nullable emotion; instruments deferred); §5 audio_semantic/speakers shapes; `fidelity_disclaimer` documented (AF-01 "perfect restoration" explicitly out-of-scope — emotion is a calibrated estimate, word-level is experimental, instruments absent).

### Claude's Discretion

- Exact field names/casing within the locked shapes above (mirror v1.1 conventions: snake_case, draft 2020-12, `$id`/`$schema`/`title`/`description` headers matching the 10 existing schemas).
- The `speakers.schema.json` internal structure (per-shot vs top-level turns) — pick whichever composes cleanly with Phase 13's HITL flow.
- Fixture content realism (use ep01 spike JSONs as source; synthesize shape-correct spk_NNN turns).
- Whether to factor a shared `_common` snippet for the nullable+confidence pattern (if v1.1 has a precedent, follow it; else inline).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (v1.1 contract — Phase 11 extends, does NOT rewrite)
- **`spec/schemas/*.schema.json`** (10 schemas) — the draft-2020-12 + `additionalProperties:false` template to copy for the 3 new schemas. `registry-edits.schema.json` is the line-for-line template for `speaker-edits.schema.json`.
- **`scripts/export_asset.py`** — `SCHEMA_VERSION = "1.1"` single-source (line per scout). Phase 11 bumps to `"1.2"` + adds the 2 new optional `data.*` keys to the asset manifest builder (mirror how v1.1 added `data.characters`/`data.props`).
- **`scripts/verify_contract.py`** — the bidirectional cross-version prover. Phase 11 extends with the v1.2 fixture + the speakers⊆characters consistency check. `V11_ORDER` list → add `V12_ORDER`.
- **`spec/SPEC.md`** (v1.1 active) — §4 Changelog + §5 shapes sections to extend with the `1.2` entry.
- **`spec/fixtures/v1.1/`** (10 files) — copy to `spec/fixtures/v1.2/` + add 2 new.
- **Phase 10 spike results** (`spike/audio/results/*.json`) — realistic fixture data source for `audio_semantic.json` (real emotion/event predictions, real word-level drift).

### Established Patterns
- **Additive-only minor bumps:** v1.1 Phase 5 is the precedent — new optional fields, `required[]` unchanged, byte-identical-absent (Pitfall 11 prevented). Phase 11 follows identically.
- **Two-tier authority:** schemas = machine-checkable truth, SPEC.md = human overview; on conflict schema wins. Phase 11 honors this (the `fidelity_disclaimer` lives in SPEC prose; the nullable+confidence is in the schema).
- **Single-source version:** `SCHEMA_VERSION` literal in `export_asset.py`, schema `pattern` unchanged. No second source.

### Integration Points
- Phase 12 producer client (`call_audio_analysis.py`) validates against these schemas pre-write.
- Phase 13 SPEAKER-01 HITL consumes `speakers.schema.json` + `speaker-edits.schema.json`.
- Phase 16 HTML gallery renders `audio_semantic` fields.
- Phase 17 canvas consumer recognizes `schema_version:"1.2"`.

</code_context>

<specifics>
## Specific Ideas

- The single most important Phase-10-informed decision: **instruments omitted**. The ROADMAP Phase-11 dependency note assumed `list[{label,confidence}]`; the spike empirically overruled it. The plan MUST bake this in (no instruments field anywhere in v1.2) and the SPEC §4 Changelog must record WHY (MERT no classifier + PANNs blocked → MUS-04 defer).
- The `fidelity_disclaimer` is a first-class deliverable (AF-01/AF-02/AF-03): emotion=calibrated estimate, word-level=experimental, instruments=absent. Consumers (canvas) must read this before trusting fields.
- Bidirectional cross-version proof is the correctness gate — forward (v1.1×v1.2=0 errors) proves additive; backward (v1.2×recovered-v1.1=only additionalProperties) proves no breaking change. Both must be GREEN.

</specifics>

<deferred>
## Deferred Ideas

- **instruments field** — v1.3, pending a real MIR classifier (PANNs once zenodo-reachable, or a fine-tuned MERT head). Documented in SPEC §4 as deferred.
- **PANNs 527-class SFX multi-label** — folded into a future sfx expansion once PANNs is reachable.
- **word-level drift metric refinement** — Phase 12 (use boundary drift, not per-word-from-segment-start).
- **Live ML round-trip through the route** — Phase 12+ (route host loads SenseVoice/WhisperX/etc.).

</deferred>
