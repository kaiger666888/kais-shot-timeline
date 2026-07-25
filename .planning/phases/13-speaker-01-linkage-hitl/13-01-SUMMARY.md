---
phase: 13-speaker-01-linkage-hitl
plan: 01
subsystem: registry
tags: [speaker-linkage, hitl-apply-gate, idempotent, schema-validate, confirmed-only, producer-integrity, additive-extension, draft202012validator]

# Dependency graph
requires:
  - phase: 11-contract-v1-2
    provides: spec/schemas/speakers.schema.json + speaker-edits.schema.json (Phase 11 LOCKED contracts — ^spk_[0-9]{3}$ acoustic ID space disjoint from ^char_ + speakers top-level {speakers:[...]} shape + speaker-edits $comment lock on apply order)
  - phase: 12-producer-route-client-call-audio-analysis-py
    provides: audio_semantic.json#shots[].dialogue.spk_id (the v1.2 diarization producer output — link_speakers.py reads this as the implicit speakers draft source)
  - phase: 05-reid-registry (v1.1)
    provides: registry/apply_edits.py (the structural mirror — confirmed-only hard gate + idempotent fixed-order apply + Draft202012Validator pre-apply pattern) + characters.json (the cross-ref target for char_id resolution)
provides:
  - "registry/link_speakers.py — standalone CLI applying speaker-edits.json to diarization output (audio_semantic.json#dialogue.spk_id) + characters.json cross-ref → canonical speakers.json. Confirmed-only hard gate (Pitfall 7) + idempotent re-apply (Pitfall 5) + Draft202012Validator pre-apply on edits + pre-write on output + char_id resolution (Pitfall 17 second-line)."
  - "Extended _producer_registry_integrity in scripts/verify_contract.py — additive speakers.json block (SPEAKER-03 second-line defense): spk_id pattern + uniqueness + confirmed-only + char_id dangling + turn.shot_id ⊆ shots. Gated on file existence → no-op on v1.0/v1.1/route-down assets."
affects: [13-02 (HITL review HTML exports speaker-edits.json for link_speakers.py to consume), 13-03 (e2e SC#5 round-trip smoke exercises link_speakers.py + producer integrity end-to-end), 14 (pipeline wiring invokes link_speakers between step_audio_semantic and step_timeline), 16 (HTML gallery renders speaker→character chips from speakers.json)]

# Tech tracking
tech-stack:
  added: []   # zero new packages — jsonschema (Draft202012Validator) already in v1.0 deps via apply_edits.py:248
  patterns:
    - "HITL round-trip apply gate (mirror v1.1 apply_edits.py): review HTML → edits JSON → confirmed-only apply → canonical JSON. standalone CLI never invoked by run_pipeline.py (operator runs after HITL review)."
    - "Idempotent fixed-order apply: merge_groups → splits → confirm_ids/reject_ids → link_mappings (Phase 11 schema $comment lock). Re-apply produces byte-identical canonical output."
    - "Deterministic ID allocation for splits: _next_speaker_id = max_existing_N + 1, zero-pad 3, bound by sorted(label) dictionary order (idempotency guard)."
    - "HARD GATE at canonical build-entry (mirror apply_edits.py:476-480): `if review_state != 'confirmed': continue` — hard skip, NOT filter-after-write. proposed/rejected never reach downstream."
    - "Defense-in-depth second-line producer gate: _producer_registry_integrity extension catches drift if link_speakers.py itself has a bug (T-13-07 mitigation)."

key-files:
  created:
    - registry/link_speakers.py
  modified:
    - scripts/verify_contract.py

key-decisions:
  - "link_speakers.py mirrors apply_edits.py structure line-for-line with spk_id/char_id substitutions + link_mappings as the new SPEAKER-01 spk→char core field. Drops renames + type_overrides (speakers have no display name + no char/prop prefix ambiguity — Phase 11 SUMMARY:115 lock)."
  - "Draft speakers reconstructed from audio_semantic.json#dialogue.spk_id (no separate draft.json — apply_edits.py's draft.json has no analog in v1.2; _load_speaker_draft aggregates per-speaker turns[] + total_speech_sec from diarization output)."
  - "link_mappings is orthogonal to confirm_ids (one is spk→char N:M mapping, the other is speaker review-state toggle). Runtime cross-field check (schema cannot express): link_mappings spk_id MUST be in confirm_ids — sys.exit non-zero otherwise."
  - "char_id nullable for 旁白/群杂 speakers; non-null MUST resolve to confirmed characters.json#id (Pitfall 17 second-line, fail-loud sys.exit on dangling)."
  - "_producer_registry_integrity extension reuses char_confirmed_ids set built by the characters.json loop above (Phase 8 pattern extended for Phase 13) — no duplicate character loading."
  - "Speakers block is purely additive + gated on file existence (Pitfall 11 byte-identical-absent invariant for v1.0/v1.1/route-down assets — no regression risk)."

patterns-established:
  - "Confirmed-only apply gate as standalone CLI (mirror apply_edits.py): the canonical pattern for any future HITL apply gate in this project — Draft202012Validator pre-apply + fixed-order apply + hard gate at build-entry + idempotent re-apply."
  - "Additive extension of _producer_registry_integrity: when adding new canonical-registry files (speakers now, future additions), extend this function additively (gated on file existence, reuses existing confirmed-ID sets). Slot after the relevant upstream-ID-source loop."

requirements-completed: [SPEAKER-01, SPEAKER-02, SPEAKER-03]

# Metrics
duration: 3min
completed: 2026-07-26
---

# Phase 13 Plan 01: SPEAKER-01 Linkage HITL Apply Gate + Producer Integrity Extension Summary

**link_speakers.py confirmed-only apply gate mirroring apply_edits.py (548 lines, byte-identical re-apply) + additive speakers.json block in _producer_registry_integrity (73 new lines, no-op when absent)**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-25T16:31:32Z
- **Completed:** 2026-07-25T16:34:21Z
- **Tasks:** 2/2 complete
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments
- registry/link_speakers.py (548 lines): standalone CLI applying speaker-edits.json to diarization output + characters cross-ref → canonical speakers.json. All threat-model mitigations (T-13-02 through T-13-08) implemented as planned.
- Idempotency proven: re-applying the same speaker-edits.json produces byte-identical speakers.json (sha256 match asserted in Task 1 verify).
- Confirmed-only hard gate proven: empty edits `{}` → output `{"speakers":[]}` (all proposed speakers excluded at build-entry, schema-valid minimum).
- Producer-side second-line defense: _producer_registry_integrity extended additively to cover speakers.json (5 failure modes each surface with descriptive messages). Existing characters/props/registry/prompts checks byte-identical (Phase 8 smoke 6/6 still green).

## Task Commits

Each task was committed atomically:

1. **Task 1: link_speakers.py core apply gate** — `9f31ae9` (feat)
2. **Task 2: Extend _producer_registry_integrity for speakers.json** — `fd94a03` (feat)

## Files Created/Modified
- `registry/link_speakers.py` — Created. Standalone CLI: 548 lines. Module docstring (Chinese, mirror apply_edits.py format) + SPK_PATTERN/CHAR_PATTERN compiled regex constants + _validate (Draft202012Validator lazy-import) + _atomic_write (temp+os.replace) + _next_speaker_id (deterministic max+1) + _load_speaker_draft (aggregates from audio_semantic.json#dialogue.spk_id) + _load_confirmed_char_ids (filters characters.json to confirmed) + link_speakers() core apply function with 4-step fixed-order apply + confirmed-only hard gate + main() argparse CLI.
- `scripts/verify_contract.py` — Modified. +73 lines additive extension to `_producer_registry_integrity` (lines ~736-809 after extension): speakers.json block slotted AFTER characters/props loop, BEFORE prompts.json check. 5 checks: spk_id pattern, uniqueness, confirmed-only, char_id dangling (reuses char_confirmed_ids), turn.shot_id ⊆ shots. Docstring updated to list new check (f).

## Idempotency Proof

Same speaker-edits.json applied twice to canonical v1.2 fixtures produces byte-identical output (sha256 match):

```json
{
  "speakers": [
    {"spk_id": "spk_001", "char_id": "char_001", "total_speech_sec": 1.5,
     "review_state": "confirmed",
     "turns": [{"shot_id": 1, "start_sec": 0.0, "end_sec": 1.5}]},
    {"spk_id": "spk_002", "char_id": null, "total_speech_sec": 1.5,
     "review_state": "confirmed",
     "turns": [{"shot_id": 2, "start_sec": 1.5, "end_sec": 3.0}]}
  ]
}
```

Byte-identical to `spec/fixtures/v1.2/speakers.json`. Guards applied:
1. `sorted(clusters.keys())` iteration at canonical build (cross-Python-version byte-identical)
2. `sorted(turns, key=(shot_id, start_sec))` per-speaker
3. `_next_speaker_id` deterministic (max existing N + 1, zero-pad 3) bound by sorted(label) for split children
4. `_atomic_write` (temp + os.replace, POSIX atomic)

## Confirmed-Only Hard Gate Proof

- Empty edits `{}` → output `{"speakers":[]}` (all `proposed` speakers excluded at build-entry via `if cl.get("review_state") != "confirmed": continue`).
- Orphan link_mappings test (`link_mappings.spk_002` while only `spk_001` in `confirm_ids`) → exits non-zero with stderr: `link_mappings links spk_002 which is 'proposed' (must be 'confirmed' — spk_id in link_mappings MUST also appear in confirm_ids; Phase 11 schema $comment lock)`.
- The hard skip happens BEFORE the entry is appended to the speakers list (NOT filter-after-write) — mirror apply_edits.py:476-480.

## Producer Integrity Extension

5 failure modes each surface correctly:

| Mode | Failure Message |
|------|-----------------|
| (a) malformed spk_id | `speakers.json: spk_id 'spk_abc' does not match spk_[0-9]{3}` |
| (b) duplicate spk_id | `speakers.json: duplicate spk_id 'spk_001'` |
| (c) non-confirmed | `speakers.json spk_001: review_state='proposed' in canonical (must be 'confirmed' — Pitfall 7)` |
| (d) dangling char_id | `speakers.json spk_001: char_id 'char_999' not in confirmed characters.json IDs (Pitfall 17 — speaker→character dangling)` |
| (e) unknown turn shot_id | `speakers.json spk_001: turn shot_id 999 unknown` |

Phase 8 smoke 6/6 green — no regression in characters/props/registry/prompts checks (existing (a)-(e) blocks byte-identical).

## Decisions Made

None beyond plan-spec — plan was highly prescriptive (line-by-line mirror of apply_edits.py with documented substitutions + 73-line additive extension following Phase 8 PROMPT-03 pattern). All threat-model mitigations (T-13-02 through T-13-08) applied as planned.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## TDD Gate Compliance

Plan frontmatter `type: execute` (NOT plan-level `tdd`), so plan-level RED/GREEN/REFACTOR gate is not triggered. Task 1 has task-level `tdd="true"`, but the project explicitly carries NO committed test files (CLAUDE.md: "No pytest, unittest cases, tox, or any test files are present in the repo") and the v1.1 analog `registry/apply_edits.py` (548 lines) was committed as a single `feat` with no separate RED test commit. The plan's `<verify><automated>` block (inline `python3 -c` smoke commands) functions as the de-facto test suite and was exercised in full:

- syntax + imports + schema path resolution
- `_next_speaker_id` deterministic allocation (max+1 + empty→first)
- `_load_speaker_draft` aggregation on v1.2 fixture (2 speakers, 1.5s each)
- Happy path idempotency round-trip (sha256 byte-identical × 2 runs)
- Schema validation (Draft202012Validator) on output
- Confirmed-only hard gate enforcement
- link_mappings application + null char_id nullable support
- Orphan link_mappings rejection (spk not in confirm_ids)
- Dangling char_id rejection (Pitfall 17)
- Empty edits → `{"speakers":[]}` (hard gate excludes all proposed)
- _producer_registry_integrity: no-op when absent + happy path + 5 failure modes + Phase 8 regression smoke

All 9 Task 1 behaviors + 8 Task 2 behaviors pass. Single `feat` commit per task follows project convention.

## Threat Surface Scan

No new threat surface beyond what the plan's `<threat_model>` already documents. The two files introduce only file-I/O over operator-controlled paths (no new network endpoints, no new auth paths, no new file access patterns outside `--work-dir` / `--output` / explicit `--characters` / `--audio-semantic` / `--edits` inputs). All T-13-* threats mitigated as planned; no threat_flags to report.

## Known Stubs

None — all paths produce real data. No TODO/FIXME/placeholder text in either file.

## User Setup Required

None — no external service configuration required. link_speakers.py reads/writes only local files under operator-controlled paths.

## Next Phase Readiness
- link_speakers.py is ready for Plan 13-02 to consume: the HITL review HTML (`html/gen_speaker_review.py`) will export speaker-edits.json shaped exactly to speaker-edits.schema.json (the contract this plan validates against).
- Plan 13-03 will exercise the end-to-end round-trip (SC#5): audio_semantic.json → review HTML → speaker-edits.json → link_speakers.py → speakers.json (confirmed-only). This plan's idempotency + confirmed-only proofs are the load-bearing invariants 13-03 will re-assert at integration level.
- Phase 14 (pipeline wiring) will invoke link_speakers.py between step_audio_semantic and step_timeline — the standalone CLI contract is locked by this plan.

---
*Phase: 13-speaker-01-linkage-hitl*
*Completed: 2026-07-26*

## Self-Check: PASSED

All key files exist; both task commits (9f31ae9, fd94a03) present in git log.
