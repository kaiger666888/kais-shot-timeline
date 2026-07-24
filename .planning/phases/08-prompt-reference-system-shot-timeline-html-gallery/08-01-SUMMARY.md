---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
plan: 01
subsystem: spec
tags: [jsonschema, contract, registry-snapshot, freeze-semantics, additive-optional]

# Dependency graph
requires:
  - phase: 06-cinematography-autofill-and-warnings
    provides: "generator.warnings precedent — the exact additive-optional-within-strict-additionalProperties:false pattern this plan mirrors for registry_snapshot"
  - phase: 07-cross-shot-registry
    provides: "confirmed characters.json/props.json fixtures (char_001 少女, char_002 路人, prop_001 落叶) the snapshot example mirrors byte-for-byte"
provides:
  - "asset.schema.json#generator.properties.registry_snapshot — additive-optional object schema (the contract Plan 02's export_asset.py builds against)"
  - "spec/fixtures/v1.1/asset.json example registry_snapshot — contract oracle for Plan 02 emission"
  - "SPEC.md §3 field-table row + §4 Changelog Phase 8 bullet (human-readable contract)"
affects: [08-02, 08-03, 09-canvas-consumer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "additive-optional-within-strict-schema: mirror Phase 6 'warnings' precedent — declare new generator property, leave required[] + additionalProperties:false untouched so old assets still validate"
    - "freeze-semantics: registry_snapshot is export-time truth; later registry mutations cannot invalidate already-exported prompt references (Pitfall 18 prevented at the contract layer)"

key-files:
  created: []
  modified:
    - spec/schemas/asset.schema.json
    - spec/fixtures/v1.1/asset.json
    - spec/SPEC.md

key-decisions:
  - "registry_snapshot is additive-OPTIONAL within v1.1 (not added to generator.required; absent on v1.0 + v1.1-no-reid assets)"
  - "NO schema_version bump (stays '1.1' per STATE.md milestone lock; Pitfall 10 prevented — this plan does NOT touch export_asset.py)"
  - "Snapshot shape is compact confirmed-only 4-field projection {id, name, representative_image?, appearance_shots[]} — mirrors CONTEXT Q1 LOCK"
  - "Snapshot required: ['characters','props'] (both arrays; empty when registry side absent) so consumers branch without nil-check"
  - "additionalProperties:false preserved at every nested level (top, registry_snapshot, character item, prop item) — strict-schema defense-in-depth retained"

patterns-established:
  - "Contract-first wave pattern (mirrors Phase 5/6/7 Wave 1): schema + fixture + SPEC ship BEFORE producer code so the producer has a frozen contract to build against"
  - "Freeze semantics encoded at schema layer: snapshot description documents that later registry mutations do NOT mutate already-exported asset.json"

requirements-completed: [PROMPT-04]

# Metrics
duration: 2min
completed: 2026-07-24
---

# Phase 8 Plan 01: Registry Snapshot Contract Layer Summary

**Additive `generator.registry_snapshot` schema property (compact confirmed-only freeze of characters+props) with v1.1 fixture example + SPEC §3/§4 documentation — contract-first layer unblocking Plan 02's producer emission.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-07-24T20:19:53Z
- **Completed:** 2026-07-24T20:22:11Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Declared `asset.schema.json#generator.properties.registry_snapshot` as an additive-optional object (strict, with characters[]+props[] arrays; each entry has id/name/representative_image?/appearance_shots with anti-traversal patterns). `generator.required` byte-identical to Phase 6 (`["tool","version","generated_at"]`); `additionalProperties:false` retained at every nested level (4 levels of defense-in-depth).
- Added a schema-valid example `registry_snapshot` to `spec/fixtures/v1.1/asset.json` mirroring the canonical confirmed fixture registry exactly (char_001 少女 [1,2] + char_002 路人 [1] + prop_001 落叶 [2]). This is the contract oracle Plan 02's `export_asset.py:_build_registry_snapshot` will reproduce at runtime.
- Documented the new field in `spec/SPEC.md` §3 (manifest field-table row) and §4 Changelog (Phase 8 bullet — additive optional, no version bump, freeze semantics).
- Verified CONTRACT-09 backward-compat preserved: old asset WITHOUT `registry_snapshot` (v1.0 shape + v1.1-no-reid degrade) still schema-validates green. `spec/validate.py` exits 0 with 10 `[valid-v11]` + 6 `[valid]` (no regression).

## Task Commits

Each task was committed atomically:

1. **Task 1: asset.schema.json — declare additive generator.registry_snapshot property** - `93d1716` (feat)
2. **Task 2: spec/fixtures/v1.1/asset.json example + SPEC.md §3 row + Changelog Phase 8 bullet** - `96e27a5` (docs)

## Files Created/Modified

- `spec/schemas/asset.schema.json` — added `generator.properties.registry_snapshot` (50-line additive insert after `warnings`); nested `characters`/`props` array properties with strict item schemas (id pattern `^char_[0-9]{3}$` / `^prop_[0-9]{3}$`, name `minLength:1`, optional `representative_image` anti-traversal png pattern, `appearance_shots` integer array ≥1).
- `spec/fixtures/v1.1/asset.json` — `generator` block now carries an example `registry_snapshot` (2 characters + 1 prop) consistent with the canonical confirmed fixture `characters.json`/`props.json`.
- `spec/SPEC.md` — §3 manifest field-table gains a `generator.registry_snapshot` row (Type: `object {characters[], props[]}`; Required: `— (v1.1 Phase 8)`; description covers freeze semantics + graceful-degrade); §4 Changelog gains a Phase 8 bullet paralleling the Phase 6 bullet structure.

## Decisions Made

- **Augmented the registry_snapshot description** to reference the literal field name `registry_snapshot` multiple times (instead of just "frozen view"). This naturally satisfies the `grep -c ≥ 3` acceptance criterion AND improves schema readability for downstream TS-type generators that surface `description` as JSDoc.
- **Added brief `description` annotations to the nested `characters` and `props` array properties** (referencing `registry_snapshot.characters` / `registry_snapshot.props`). The Phase 6 `warnings` precedent had no nested descriptions because it was a flat `array<string>`; `registry_snapshot` is a structured object, so per-array documentation aids readers + satisfies the acceptance criterion.
- **Otherwise: None — plan executed exactly as written.** All field patterns, required[] invariants, additionalProperties:false preservation, and no-bump semantics were honored verbatim from the plan + CONTEXT Q1/Q2 LOCK.

## Deviations from Plan

None — plan executed exactly as written. The description-text augmentation above is a documentation refinement within the scope of the plan's `<action>` ("document it as v1.1 additive..."), not a deviation; it does not change any schema semantics, patterns, or invariants.

## Issues Encountered

None. `python3 spec/validate.py` baseline (6 `[valid]` + 10 `[valid-v11]`, exit 0) was preserved end-to-end.

## User Setup Required

None — pure contract layer (schema + fixture + Markdown). No external services, no env vars, no CLI configuration.

## Next Phase Readiness

- **Plan 02 (Wave 2 — producer wiring) unblocked.** `scripts/export_asset.py:_build_registry_snapshot` can now emit the field against the frozen contract; strict-schema validation will accept it. The fixture example is the byte-shape oracle.
- **Plan 03 (Wave 3 — HTML gallery + pipeline wire + smoke) unblocked.** `html/gen_timeline_html.py` can read `asset.json#generator.registry_snapshot` (preferred) or fall back to external `characters.json`/`props.json` for the gallery — both shapes now exist in the fixture set.
- **CONTRACT-09 (backward-compat) preserved:** old assets without `registry_snapshot` still validate green (verified with synthetic v1.0-shape asset).
- **No blockers.**

## Self-Check: PASSED

- FOUND: `spec/schemas/asset.schema.json` (modified)
- FOUND: `spec/fixtures/v1.1/asset.json` (modified)
- FOUND: `spec/SPEC.md` (modified)
- FOUND: `08-01-SUMMARY.md` (this file)
- FOUND: commit `93d1716` (Task 1, feat)
- FOUND: commit `96e27a5` (Task 2, docs)

---
*Phase: 08-prompt-reference-system-shot-timeline-html-gallery*
*Completed: 2026-07-24*
