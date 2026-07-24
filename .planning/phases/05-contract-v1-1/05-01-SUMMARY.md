---
phase: 05-contract-v1-1
plan: 01
subsystem: infra
tags: [json-schema, draft-2020-12, contract, shot-timeline-asset, v1.1]

requires:
  - phase: 01-shot-timeline-asset-specification
    provides: v1.0 schema patterns ($defs/$ref, anti-traversal regex, additionalProperties:false)
provides:
  - "characters.schema.json — cross-shot character registry contract"
  - "props.schema.json — cross-shot prop registry contract (states[] not looks[])"
  - "registry.schema.json — pre-review re-id clustering draft contract"
  - "prompts.schema.json additive character_refs[]/prop_refs[] (CONTRACT-04)"
  - "asset.schema.json additive data/media characters+props (CONTRACT-05)"
affects: [05-03-fixtures, 05-04-harness, phase-6-step_semantic, phase-7-step_reid, phase-8-prompt-refs, phase-9-canvas-consumer]

tech-stack:
  added: []
  patterns: ["strict-schema × lenient-consumer preserved; pure-additive extension (only + in properties, required byte-identical)", "external-png-not-base64 media convention with anti-traversal pattern"]

key-files:
  created:
    - spec/schemas/characters.schema.json
    - spec/schemas/props.schema.json
    - spec/schemas/registry.schema.json
  modified:
    - spec/schemas/prompts.schema.json
    - spec/schemas/asset.schema.json

key-decisions:
  - "schema_version stays PATTERN in asset.schema.json (NOT const:\"1.1\") — value locked producer-side via SCHEMA_VERSION constant in 05-02; a const would reject v1 minimal fixture \"1\" and break CONTRACT-09"
  - "props use states[] (open/closed) not looks[] — semantic precision over schema uniformity (CONTEXT grey-area 2)"
  - "registry clusters[] members are refs-only {shot_id,frame_pos,mask_quality} — no 768-d DINOv2 embeddings inlined (bloat prevention); tier enum + mean_cosine float; thresholds in $comment not numeric fields"
  - "characters/props/registry media paths use external png (NOT base64) with ^(?!.*\\.\\.) anti-traversal — mirrors asset.schema.json:66"

patterns-established:
  - "v1.1 additive extension discipline: every new field OPTIONAL, required[] byte-identical to v1.0, additionalProperties:false preserved (Pitfall 11 prevention)"

requirements-completed: [CONTRACT-01, CONTRACT-02, CONTRACT-03, CONTRACT-04, CONTRACT-05]

duration: 25min
completed: 2026-07-24
---

# Phase 5 Plan 01: v1.1 Contract Schemas Summary

**3 new registry-flavor schemas + 2 additive schema extensions locking the v1.1 ShotTimelineAsset contract — all pure-additive, v1 minimal fixture still validates 6/6 green.**

## Performance

- **Duration:** ~25 min (including mid-execution recovery — see Issues Encountered)
- **Tasks:** 2
- **Files modified:** 5 (3 created, 2 extended)

## Accomplishments
- characters.schema.json: `^char_[0-9]{3}$` ID + name + representative_image (external png, anti-traversal) + appearance_shots[] + review_state enum + looks[] with per-look appearance_shots[] (enables Phase 8 per-look prompt refs)
- props.schema.json: same core shape but `states[]` (not looks[]) — props vary by state, not costume
- registry.schema.json: clusters[] with refs-only members + tier enum (auto_merge|review|auto_distinct) + mean_cosine float; thresholds documented in $comment (default τ calibrated Phase 7)
- prompts.schema.json: optional character_refs[]/prop_refs[] (ID-pattern string arrays); required[] byte-identical to v1.0
- asset.schema.json: optional data.characters/data.props (json paths) + media.characters[]/media.props[] (external png arrays); schema_version PATTERN unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: 3 new schemas (characters/props/registry)** - `3e55c02` (feat)
2. **Task 2: prompts + asset additive extension** - `4ff0d74` (feat)

## Files Created/Modified
- `spec/schemas/characters.schema.json` - cross-shot character registry contract (CONTRACT-01)
- `spec/schemas/props.schema.json` - cross-shot prop registry contract, states[] (CONTRACT-02)
- `spec/schemas/registry.schema.json` - pre-review re-id clustering draft contract (CONTRACT-03)
- `spec/schemas/prompts.schema.json` - +character_refs[]/prop_refs[] additive (CONTRACT-04)
- `spec/schemas/asset.schema.json` - +data/media characters+props additive (CONTRACT-05)

## Decisions Made
- All 4 CONTEXT-locked grey-area decisions honored verbatim (schema_version pattern-not-const; looks/states split; registry refs-only+tier+mean_cosine; external-png-not-base64).
- `additionalProperties:false` confirmed on every OBJECT node (items + $defs.look/state for array-rooted schemas; root + cluster item + member for registry). The plan's acceptance criterion "`grep -c 'additionalProperties: false'` ≥ 3" assumed object-root; array-rooted characters/props legitimately have 2 (semantic invariant — every object node is strict — holds; registry has 3).

## Deviations from Plan

None — plan executed as written. (Recovery details below are an execution-environment issue, not a plan deviation.)

## Issues Encountered

**Mid-execution quota termination + inline recovery.** The spawned gsd-executor agent completed Task 1 (3 new schemas, correct) and began Task 2, but terminated early on a provider 5-hour-usage-limit (429) before committing. On resume, the working tree contained: the 3 correct new schemas (uncommitted), a WRONG prompts.schema.json change (an out-of-scope rewrite of the `action` field description to "完整物理动作链" — a prompt-quality concern, NOT CONTRACT-04), premature SPEC.md/README.md edits (same out-of-scope action-chain theme, 05-04 territory), and an unextended asset.schema.json.

Recovery (inline as orchestrator, per safe_resume_gate "close out manually"):
1. Verified the 3 new schemas correct against CONTEXT decisions.
2. Reverted the out-of-scope prompts/SPEC/README changes (`git checkout`).
3. Applied the correct CONTRACT-04 extension to prompts.schema.json (character_refs[]/prop_refs[]).
4. Applied the missing CONTRACT-05 extension to asset.schema.json (data/media characters+props).
5. Validated: all 9 schemas valid Draft 2020-12; required[] byte-identical to v1.0; schema_version pattern-not-const; v1 minimal fixture 6/6 green.
6. Committed Task 1 + Task 2 atomically.

**Root cause of the out-of-scope drift:** the failed agent appears to have pursued an "action field richness" tangent unrelated to the v1.1 contract. Recovered cleanly; no out-of-scope changes landed in the commits.

## User Setup Required
None - pure schema/contract files, no external services.

## Next Phase Readiness
- 5 schemas frozen — 05-03 (fixtures) can now author a v1.1 fixture set that exercises them; 05-04 (harness) can wire EIGHT_SHAPES + cross-version self-test.
- All CONTRACT-01..05 schema work complete; CONTRACT-06 (SCHEMA_VERSION producer constant) is 05-02 (independent, Wave 1).

---
*Phase: 05-contract-v1-1*
*Completed: 2026-07-24*
