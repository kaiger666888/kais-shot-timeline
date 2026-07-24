---
phase: 05-contract-v1-1
plan: 03
subsystem: testing
tags: [fixtures, v1.1, json-schema, sample-data, shot-timeline-asset]

requires:
  - phase: 05-contract-v1-1 (plan 01)
    provides: the 5 frozen v1.1 schemas these fixtures exercise
provides:
  - "spec/fixtures/v1.1/ — canonical 9-file v1.1 asset sample (reference shape for Phase 9 + test data for Plan 04 harness)"
affects: [05-04-harness, phase-9-canvas-consumer]

tech-stack:
  added: []
  patterns: ["self-contained synthetic fixture set (each dir stands alone); cross-file ID consistency shipped from day 1"]

key-files:
  created:
    - spec/fixtures/v1.1/characters.json
    - spec/fixtures/v1.1/props.json
    - spec/fixtures/v1.1/registry.draft.json
    - spec/fixtures/v1.1/asset.json
    - spec/fixtures/v1.1/prompts.json
    - spec/fixtures/v1.1/shots.json
    - spec/fixtures/v1.1/audio_analysis.json
    - spec/fixtures/v1.1/transcript.json
    - spec/fixtures/v1.1/frames.json
  modified: []

key-decisions:
  - "Reused minimal's 2-shot substrate (4 byte-identical copies) so v1.1 fixture is a minimal delta, not a parallel universe"
  - "char_001 少女 carries 2 looks[] (默认造型 + 回忆杀) proving per-look appearance_shots; char_002 路人 is minimal (no looks) proving optionality"
  - "prop_001 落叶 uses states[] (完好/破碎); the 破碎 state has empty appearance_shots proving the schema accepts empty arrays"
  - "registry.draft has exactly 3 clusters, one per tier, all review_state=proposed (it's a pre-review draft)"

patterns-established:
  - "v1.1 fixture cross-file consistency: prompts.character_refs/prop_refs ⊆ characters/props IDs ⊆ shots IDs; registry.cluster_id ⊆ characters+props IDs"

requirements-completed: [CONTRACT-01, CONTRACT-02, CONTRACT-03, CONTRACT-04, CONTRACT-05, CONTRACT-09]

duration: 12min
completed: 2026-07-24
---

# Phase 5 Plan 03: v1.1 Fixture Set Summary

**9-file self-contained v1.1 fixture sample — exercises every new + extended schema with cross-file-consistent IDs; v1 minimal fixture unaffected (6/6 green).**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2
- **Files created:** 9 (5 new v1.1 content + 4 byte-identical substrate copies)

## Accomplishments
- characters.json (2 chars: rich char_001 with 2 looks + minimal char_002), props.json (1 prop with states[]), registry.draft.json (3 clusters, one per tier) — all validate 0-errors against Plan 01 schemas.
- asset.json (schema_version "1.1" + data/media characters+props inventories), prompts.json (2-shot + character_refs/prop_refs) — validate 0-errors against extended schemas.
- 4 substrate files (shots/audio_analysis/transcript/frames) copied byte-identical from minimal/.
- Cross-file ID consistency verified: prompts→characters/props, characters/props→shots, registry→characters/props/shots — zero dangling IDs (Pitfall C prevention from day 1).
- v1 minimal fixture still 6/6 green (CONTRACT-09).

## Task Commits

1. **Task 1: registry-flavor fixtures (characters/props/registry.draft)** - `18878f5` (feat)
2. **Task 2: asset+prompts + 4 reuse copies** - `81538b1` (feat)

## Files Created/Modified
- 9 files under `spec/fixtures/v1.1/` (see frontmatter key-files.created)

## Decisions Made
- Followed plan's exact fixture content spec (locked in CONTEXT grey-area 4).
- All files `indent=2`, `ensure_ascii=False` (Chinese names like 少女/落叶 render un-escaped).

## Deviations from Plan
None — plan executed as written (inline; plan specified exact JSON content).

## Issues Encountered
None.

## User Setup Required
None.

## Next Phase Readiness
- v1.1 fixture set is the canonical sample Plan 04 (harness) validates via EIGHT_SHAPES + the cross-version/consistency checks, and Phase 9 (canvas consumer) reads as the reference shape.
- CONTRACT-01..05 fixtures + CONTRACT-09 regression all green.

---
*Phase: 05-contract-v1-1*
*Completed: 2026-07-24*
