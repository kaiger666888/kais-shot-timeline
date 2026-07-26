# Phase 13: SPEAKER-01 Linkage HITL - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — code phase mirroring 2 proven v1.1 analogs (apply_edits.py + gen_registry_review.py); shape forced by Phase 11 schemas + the new spk_NNN space. All recommendations accepted per user momentum preference.

<domain>
## Phase Boundary

Close the v1.1 SPEAKER-01 deferral: a NEW `^spk_[0-9]{3}$` acoustic ID space (NOT reusing `^char_[0-9]{3}$` — avoids identity-signal conflation) + HITL review HTML (`html/gen_speaker_review.py`) + confirmed-only apply gate (`registry/link_speakers.py`, mirror v1.1 Phase 7 `apply_edits.py`). The route (Phase 12) produces raw `spk_NNN` IDs from diarization; this phase gives the developer a review UI to confirm/reject/merge/link speakers to characters, then applies only confirmed mappings to canonical `speakers.json`.

This phase produces the HITL loop ONLY — NO route ML, NO pipeline wiring (Phase 14 wires `link_speakers` between `step_audio_semantic` and `step_timeline`).

</domain>

<decisions>
## Implementation Decisions

### HITL review HTML (`html/gen_speaker_review.py` → mirror `gen_registry_review.py`)

- Speaker cards sorted by `shot_count` desc (most-active speakers first).
- Per-speaker character dropdown FILTERED to `characters.json#review_state=="confirmed"` (don't let the user link to an unconfirmed character — Pitfall 7 confirmed-only gate upstream).
- Export-edits button → `speaker-edits.json` (validates against the Phase 11 `speaker-edits.schema.json` — merge_groups/splits/confirm_ids/reject_ids/link_mappings).
- Chinese UI per CLAUDE.md; GitHub-dark palette reuse; XSS hardening mirror v1.1 Phase 8 PRESENT patterns.

### Confirmed-only apply gate (`registry/link_speakers.py` → mirror `apply_edits.py`)

- **Hard gate at build-entry** (mirror `apply_edits.py`): only `review_state=="confirmed"` spk→char mappings land in canonical `speakers.json`. rejected/pending → omitted (ID reserved for referential integrity, Pitfall 17).
- **Idempotent re-apply**: same `speaker-edits.json` applied N times → byte-identical `speakers.json` (fixed apply order: merge → split → confirm/reject → link_mapping; deterministic `_next_speaker_id` = `max_existing_N + 1`, Pitfall 5 idempotency).
- **Draft202012Validator pre-validate** `speaker-edits.json` before apply (T-07-02, Phase 11 schema lock).
- Writes `speakers.json` validating against Phase 11 `speakers.schema.json`: `char_id` nullable (旁白/群杂 supported); non-null `char_id` MUST resolve to a confirmed `characters.json#id`.

### Producer registry integrity (additive extension of v1.1 `_producer_registry_integrity`)

- Extend the existing assert additively: gated on file existence (no-op on v1.0/v1.1/route-down assets — Pitfall 11 byte-identical-absent). When `speakers.json` exists, catch speakers→characters dangling refs at producer time (second-line defense behind the schema/verify_contract checks).

### End-to-end HITL round-trip (SC#5)

- On fixture: `audio_semantic.json` (Phase 12, with dialogue.spk_id) + `characters.json` → review HTML → `speaker-edits.json` → `link_speakers.py` → `speakers.json` (confirmed-only). Exercises DIA-02 (diarization) + DIA-03 (speaker↔character HITL).

### Claude's Discretion

- Exact HTML structure (mirror gen_registry_review.py's card layout).
- Whether link_speakers.py imports apply_edits.py helpers or copies the idempotent-apply pattern (mirror the apply-order + deterministic-ID logic).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (v1.1 analogs)
- **`registry/apply_edits.py`** — the confirmed-only apply gate + idempotent re-apply pattern (fixed apply order, deterministic next-ID). THE analog for `link_speakers.py`.
- **`html/gen_registry_review.py`** — the HITL review HTML pattern (cards + dropdowns + export button + XSS hardening). THE analog for `gen_speaker_review.py`.
- **`spec/schemas/speakers.schema.json` + `speaker-edits.schema.json`** (Phase 11) — the contracts. `speakers` uses `^spk_[0-9]{3}$`; `speaker-edits` has link_mappings (spk→char).
- **Phase 12 `audio_semantic.json`** — supplies `dialogue.spk_id` (the raw acoustic IDs from diarization, the input to the review UI).
- **v1.1 `characters.json`** — supplies confirmed characters (the link target).

### Established Patterns
- **HITL round-trip**: review HTML → edits JSON → confirmed-only apply → canonical JSON (mirror v1.1 reid registry flow).
- **Idempotent apply**: fixed operation order + deterministic ID allocation → byte-identical re-apply (Pitfall 5).
- **Confirmed-only gate**: only confirmed flows downstream (Pitfall 7).
- **spk_NNN disjoint from char_NNN**: acoustic ID ≠ visual ID (Phase 11 lock).

### Integration Points
- Phase 14 invokes `link_speakers.py` between `step_audio_semantic` and `step_timeline` (non-blocking standalone CLI).
- Phase 16 HTML gallery renders the speaker→character chips from `speakers.json`.

</code_context>

<specifics>
## Specific Ideas

- The confirmed-only hard gate is the key correctness feature — rejected speakers never reach canonical `speakers.json`, but their IDs stay reserved (referential integrity for `audio_semantic.json#dialogue.spk_id`). Mirror apply_edits.py exactly.
- Idempotency (Pitfall 5) is non-negotiable: re-applying the same edits must produce byte-identical output. Fixed apply order (merge→split→confirm/reject→link) + deterministic `_next_speaker_id` (max+1).
- The review HTML's character dropdown MUST filter to confirmed characters only (don't permit linking to unconfirmed — Pitfall 7 upstream gate).

</specifics>

<deferred>
## Deferred Ideas

- **DIA-06 face-voice auto speaker→character** — v1.3 differentiator (v1.2 always HITL). Out of scope.
- **Live diarization through the route** — Phase 12/14; Phase 13 consumes the `spk_NNN` IDs the route produced.

</deferred>
