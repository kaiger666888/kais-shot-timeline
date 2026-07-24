---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
plan: 01
subsystem: contract
tags: [json-schema, hitl, registry, reid, edits-round-trip, fixture, draft2020-12]

# Dependency graph
requires:
  - phase: 05-contract-v1.1
    provides: registry.schema.json + characters.schema.json + props.schema.json + v1.1 fixture set (registry.draft.json + characters.json + props.json) — the frozen target shapes this plan's edits contract operates on
provides:
  - spec/schemas/registry-edits.schema.json — the HITL edits round-trip contract (review HTML exports → apply_edits.py consumes); structured + deterministic + idempotent per CONTEXT Q2 lock
  - spec/fixtures/v1.1/registry.edits.json — fixture exercising confirm_ids + renames against the existing 3-cluster registry.draft.json fixture (internally consistent with canonical characters.json/props.json names)
  - spec/validate.py wiring — registry-edits validated as the 10th v1.1 shape (V11_FIXTURE_MAP + V11_ORDER extended)
affects: [07-02, 07-03, 07-04, phase-08-prompt-reference]

# Tech tracking
tech-stack:
  added: []  # zero new deps — jsonschema 4.26.0 is v1.0 baseline
  patterns:
    - "Structured HITL edits round-trip: deterministic apply order (merge → split → rename → type_override → confirm/reject) guarantees byte-identical re-apply (Pitfall 5 idempotency)"
    - "Strict additionalProperties:false defense-in-depth at every object level (top-level + splits + renames + type_overrides) — anti-traversal cluster_id pattern ^(char|prop)_[0-9]{3}$ on all ID fields (T-07-01)"
    - "Empty-edits-valid: {} is schema-valid (operator reviewed but made no changes — the no-op case)"
    - "Fixture-consistency-with-canonical: edits fixture derives from registry.draft.json cluster_ids + characters.json/props.json display names (apply_edits test oracle for Plan 03)"

key-files:
  created:
    - spec/schemas/registry-edits.schema.json
    - spec/fixtures/v1.1/registry.edits.json
  modified:
    - spec/validate.py

key-decisions:
  - "Edits shape = structured + deterministic + idempotent (CONTEXT Q2 lock); free-form notes explicitly REJECTED — non-reproducible, unverifiable"
  - "All 7 properties optional (no top-level required); empty edits {} schema-valid for the no-changes review case"
  - "apply_edits.py apply order locked: merge → split → rename → type_override → confirm/reject — this order + deterministic ID allocation (splits use max_existing_N + 1) guarantees idempotency"
  - "registry-edits is a v1.1 fixture-regression shape (10th), NOT an asset-dir shape — verify_contract.py EIGHT_SHAPES intentionally untouched (extended separately in Plan 04)"

patterns-established:
  - "HITL edits round-trip contract pattern: schema-first freeze of the review→apply shape before either tool is built (mirrors Phase 5/6 contract-first sequencing)"
  - "Fixture derives from existing fixture set: edits fixture confirm_ids ⊆ registry.draft.json cluster_ids + renames match characters.json/props.json canonical names — makes the fixture set internally consistent as a Plan 03 apply_edits test oracle"

requirements-completed: []  # CAST-06 + CAST-07 are SPLIT across plans 01 (contract layer) + 03 (implementation). NOT marked complete until Plan 03 ships gen_registry_review.py + apply_edits.py.

# Metrics
duration: 4min
completed: 2026-07-24
---

# Phase 7 Plan 01: Registry-Edits Contract (HITL Round-Trip Schema + Fixture + Validator) Summary

**Draft 2020-12 schema freezing the HITL edits round-trip shape (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes) with strict additionalProperties:false + anti-traversal cluster_id pattern, plus a fixture consistent with the existing 3-cluster registry.draft.json, wired as the 10th v1.1 shape in spec/validate.py**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-24T18:12:45Z
- **Completed:** 2026-07-24T18:16:40Z
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- Froze the HITL edits round-trip contract (`registry-edits.schema.json`) — the shape `html/gen_registry_review.py` exports and `registry/apply_edits.py` consumes (Plans 02/03 build against this frozen target). Locks CONTEXT Q2: structured + deterministic + idempotent; free-form notes rejected.
- Created a fixture (`registry.edits.json`) that confirms all 3 draft clusters + renames them to canonical display names (少女/路人/落叶), internally consistent with the existing registry.draft.json + characters.json + props.json — serves as Plan 03's apply_edits test oracle.
- Extended `spec/validate.py` to validate 10 v1.1 shapes green (was 9; +1 registry-edits); minimal v1.0 shapes unaffected (CONTRACT-09 backward-compat); exit code 0. No regression in `verify_contract.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create registry-edits.schema.json + registry.edits.json fixture** - `1a34c7f` (feat)
2. **Task 2: Wire spec/validate.py to validate registry-edits as the 10th v1.1 shape** - `00c6368` (feat)

## Files Created/Modified
- `spec/schemas/registry-edits.schema.json` - Draft 2020-12 schema; 7 optional properties (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes); strict additionalProperties:false at every object level; cluster_id pattern `^(char|prop)_[0-9]{3}$` on all ID fields; no top-level required (empty edits {} valid). Threat mitigations: T-07-01 (path traversal via cluster_id), T-07-03 (repudiation audit via review_notes).
- `spec/fixtures/v1.1/registry.edits.json` - Fixture: confirm_ids=[char_001,char_002,prop_001] + renames to 少女/路人/落叶 + review_notes documenting the operator rationale. Exercises the happy path (confirm + rename only; merge/split/reject deferred to Plan 03 idempotency scenario).
- `spec/validate.py` - V11_FIXTURE_MAP += `"registry-edits": "registry.edits.json"`; V11_ORDER appended with `"registry-edits"`; comment block + validate_v11() docstring updated 9 → 10 shapes.

## Decisions Made
- **Empty edits {} schema-valid:** All 7 properties optional (no top-level `required`). Represents the no-changes review case (operator reviewed but accepted everything as-is). Verified by inline schema check.
- **Did NOT mark CAST-06/CAST-07 complete in REQUIREMENTS.md:** These requirements span plans 01 (this contract layer) + 03 (gen_registry_review.py + apply_edits.py implementation). Marking them complete after plan 01 would be premature — the full CAST-06 needs the HITL review HTML and full CAST-07 needs apply_edits.py, both in Plan 03. The plan frontmatter `requirements: [CAST-06, CAST-07]` reflects "requirements this plan touches," not "requirements this plan fully delivers." ROADMAP already labels 07-01 as "[CAST-06, CAST-07 contract layer]."
- **Did NOT touch verify_contract.py EIGHT_SHAPES:** registry-edits.json is an operator review artifact, not a canonical asset-dir shape. verify_contract.py is extended separately in Plan 04 for producer-side registry↔shots integrity. This matches the plan's explicit "Do NOT touch verify_contract.py" instruction.

## Deviations from Plan

### Plan-Internal Inconsistency (documentation only — no functional impact)

**1. [Rule 3 - Blocking-ish] `grep -c 'registry.edits.json' spec/validate.py` acceptance criterion conflicts with the plan's own action instruction**
- **Found during:** Task 2 (verification)
- **Issue:** The acceptance criterion states `grep -c 'registry.edits.json' spec/validate.py = 1`, but the plan's Task 2 `<action>` explicitly instructs adding a comment block containing the literal `registry.edits.json` (documenting the fixture filename mapping). Following the action produces grep count = 2 (V11_FIXTURE_MAP value + comment). The action instruction and its grep proxy contradict each other.
- **Fix:** Followed the substantive action instruction (added the comment as specified). The functional requirement (`python3 spec/validate.py` exits 0; 10 `[valid-v11]` lines; `[valid-v11] registry-edits` present) is fully met and verified. The grep count is a proxy check that the plan's own action invalidates.
- **Files modified:** spec/validate.py (the comment block the plan told me to add)
- **Verification:** `python3 spec/validate.py` exits 0; 10 v1.1 shapes green; `[valid-v11] registry-edits` present; verify_contract.py still exits 0.
- **Committed in:** 00c6368 (Task 2 commit)

---

**Total deviations:** 1 (plan-internal criterion/action inconsistency; no scope creep; functional behavior fully correct)

## Issues Encountered
None — both tasks executed cleanly on the first pass. The inline schema-validation block (Task 1) and the validate.py output check (Task 2) passed without iteration.

## User Setup Required
None - no external service configuration required. This plan adds zero new dependencies (jsonschema 4.26.0 is v1.0 baseline; no installs). Pure contract-layer artifact: 1 schema + 1 fixture + validator wiring.

## Next Phase Readiness
- **CAST-06/CAST-07 contract layer is FROZEN.** Plans 02/03 can now build against the locked `registry-edits.schema.json` shape:
  - Plan 07-02 (`analysis/call_reid.py`) produces `registry.draft.json` — unaffected by this schema, but its output feeds the review HTML.
  - Plan 07-03 (`html/gen_registry_review.py`) exports `registry.edits.json` conforming to this schema; `registry/apply_edits.py` consumes it. Both now have a frozen target.
- **Apply-order idempotency contract is documented** (merge → split → rename → type_override → confirm/reject) — Plan 03's apply_edits.py MUST implement this exact order + the `max_existing_N + 1` split-ID allocation to guarantee byte-identical re-apply (Pitfall 5).
- **No blockers.** The fixture set is internally consistent (edits ↔ draft ↔ canonical). Plan 03 can use draft+edits as a deterministic apply_edits test oracle.

---
*Phase: 07-cross-shot-re-id-registry-hitl-review-step-reid*
*Completed: 2026-07-24*

## Self-Check: PASSED

- Files: `spec/schemas/registry-edits.schema.json` FOUND, `spec/fixtures/v1.1/registry.edits.json` FOUND, `spec/validate.py` FOUND, `07-01-SUMMARY.md` FOUND
- Commits: `1a34c7f` FOUND, `00c6368` FOUND
- `python3 spec/validate.py` exits 0 (10 v1.1 + 6 minimal green)
- `python3 scripts/verify_contract.py --mode=producer` exits 0 (no regression)
