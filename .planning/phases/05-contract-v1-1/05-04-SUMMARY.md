---
phase: 05-contract-v1-1
plan: 04
subsystem: testing
tags: [regression-harness, cross-version, json-schema, spec-docs, shot-timeline-asset]

requires:
  - phase: 05-contract-v1-1 (plan 01)
    provides: the 5 frozen v1.1 schemas the harness validates
  - phase: 05-contract-v1-1 (plan 03)
    provides: spec/fixtures/v1.1/ the harness + cross-version check consume
provides:
  - "verify_contract.py EIGHT_SHAPES + _cross_version_check + _fixture_consistency_check (v1.1 regression harness)"
  - "validate.py dual minimal+v1.1 fixture pass"
  - "SPEC.md v1.1 prose (§4 Changelog + §5.6 Characters + §5.7 Props + §1/§3/§6)"
  - "README.md v1.1 layout + dual-fixture docs"
affects: [phase-6-step_semantic, phase-7-step_reid, phase-8-prompt-refs, phase-9-canvas-consumer, all-future-v1.1-phases]

tech-stack:
  added: []
  patterns: ["schema-layer cross-version proof (filter additionalProperties → 0 non-additive errors = shared fields aligned)", "git show v1.0:<schema> primary + programmatic property-strip fallback for v1 schema recovery"]

key-files:
  created: []
  modified:
    - scripts/verify_contract.py
    - spec/validate.py
    - spec/SPEC.md
    - spec/README.md

key-decisions:
  - "Cross-version check is schema-LAYER only (no fake Python consumer stub) — CONTEXT D-XX lock; real TS consumer warn behavior verified Phase 9"
  - "_recover_v1_schema uses git show v1.0:... (tag confirmed) with programmatic property-strip fallback for portability"
  - "_cross_version_check + _fixture_consistency_check operate on spec/fixtures/ (deterministic contract invariants), not the producer asset dir"
  - "validate.py: minimal still gates exit code (CONTRACT-09); v1.1 failures also count (Plan 01 schemas must accept Plan 03 fixtures)"

patterns-established:
  - "EIGHT_SHAPES (9 elements, name kept for v1.0 historic compat) + SIX_SHAPES = EIGHT_SHAPES[:6] alias"
  - "registry shape discovered by canonical filename registry.draft.json (not in asset.json#data); characters/props validate-when-present via data_field"

requirements-completed: [CONTRACT-07, CONTRACT-08, CONTRACT-09]

duration: 35min
completed: 2026-07-24
---

# Phase 5 Plan 04: v1.1 Harness + Prose Summary

**Regression harness extended (EIGHT_SHAPES + bidirectional cross-version proof + fixture-consistency check) + SPEC/README v1.1 prose — the v1.1 contract is now locked, documented, and regression-protected.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- `scripts/verify_contract.py`: SIX_SHAPES→EIGHT_SHAPES (+alias); validate_eight_shapes (registry branch + characters/props validate-when-present); `_recover_v1_schema` (git show v1.0 primary + programmatic strip fallback); `_cross_version_check` (forward v1→v1.1 schema 0 errors; backward v1.1→v1 schema filters additionalProperties → 0 non-additive errors); `_fixture_consistency_check` (prompts↔characters/props, appearance_shots↔shots, registry↔IDs). All threaded into run_producer_check; run_self_test fail-loud path untouched.
- `spec/validate.py`: + V11 fixture pass (9 shapes); minimal still gates exit code; v1.1 failures count.
- `spec/SPEC.md`: header v1.1; §1 (9 schemas); §3 (+4 optional fields); §4 Changelog `1.1` entry; §5 intro + §5.5 (+character_refs/prop_refs); §5.6 Characters + §5.7 Props (full field tables + review_state enum + minimal snippets); §6.4 (external-png convention).
- `spec/README.md`: layout block (9 schemas + v1.1/ dir); dual-fixture validate docs; graceful-degrade v1.1 note; Phase 05 footer.

## Task Commits

1. **Task 1: harness (verify_contract.py + validate.py)** - `0753823` (feat)
2. **Task 2: SPEC.md v1.1 prose** - `8fd19df` (docs)
3. **Task 3: README.md** - `13169f1` (docs)

(Separately, the user committed `761b4c1` prompts action-chain description + I committed `9be082f` matching SPEC §5.5 action guidance — prompt-quality docs preserved per user intent, orthogonal to v1.1 contract.)

## Full Phase 5 Gate (all green)
- `python3 spec/validate.py` → minimal 6/6 [valid] + v1.1 9/9 [valid-v11] + exit 0
- `python3 scripts/verify_contract.py --mode=producer` → EIGHT_SHAPES green + "v1↔v1.1 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors)" + "fixture set cross-file IDs consistent (0 dangling)"
- `PHASE4_SELF_TEST=1 ... --mode=producer` → [self-test] PASS (schema_version='v1' drift still rejected)
- Negative test: corrupting v1.1 characters.json → validate.py exits 1 (v1.1 pass gates)

## Files Created/Modified
- `scripts/verify_contract.py` - EIGHT_SHAPES + 3 new helpers (CONTRACT-07/09)
- `spec/validate.py` - v1.1 fixture pass (CONTRACT-09 regression)
- `spec/SPEC.md` - v1.1 prose (CONTRACT-08)
- `spec/README.md` - layout + docs (CONTRACT-08)

## Decisions Made
- `_cross_version_check` backward direction filters additionalProperties errors (the empirically-proven "ignored-not-crashed" mechanic from RESEARCH Pattern 7) — NOT a fake consumer stub.
- Placed the 3 new helpers thematically between validate_eight_shapes and run_producer_check.

## Deviations from Plan
None substantive — plan executed as written (inline; the action-chain prompt-quality changes are a parallel user edit, not a plan deviation).

## Issues Encountered
- Earlier in the phase, the spawned 05-01 executor hit a 5-hour quota limit (429) mid-execution and drifted to out-of-scope action-field edits. Recovered inline (see 05-01-SUMMARY). Plans 05-02/03/04 executed inline thereafter for reliability — all green.

## User Setup Required
None.

## Next Phase Readiness
- v1.1 contract fully locked + documented + regression-protected. Phase 5 ready for /gsd:verify-work.
- Downstream: Phase 6 step_semantic fills prompts facets; Phase 7 step_reid produces registry.draft + characters/props; Phase 8 attaches prompt refs; Phase 9 canvas consumer emits character/prop nodes — all build against this frozen contract.

---
*Phase: 05-contract-v1-1*
*Completed: 2026-07-24*
