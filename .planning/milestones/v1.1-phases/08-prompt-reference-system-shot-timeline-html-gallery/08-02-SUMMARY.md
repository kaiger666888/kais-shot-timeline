---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
plan: 02
subsystem: producer
tags: [prompt-refs, pattern-2-recompose, registry-snapshot, integrity, pitfall-17, idempotent, graceful-degrade]

# Dependency graph
requires:
  - phase: 08-prompt-reference-system-shot-timeline-html-gallery
    plan: 01
    provides: "asset.schema.json#generator.registry_snapshot additive schema + fixture example (the contract oracle this plan's export_asset emission reproduces)"
  - phase: 07-cross-shot-registry
    provides: "confirmed characters.json/props.json fixtures (char_001 少女, char_002 路人, prop_001 落叶) — the substrate attach_refs inverts + snapshot projects"
  - phase: 06-cinematography-autofill-and-warnings
    provides: "generator.warnings conditional-emit precedent — Phase 8 mirrors it exactly for registry_snapshot"
  - phase: 05-contract-v11
    provides: "prompts.schema.json already permits optional character_refs[]/prop_refs[] (CONTRACT-04) — attach_refs output schema-valid by construction"
provides:
  - "prompts/attach_refs.py — standalone CLI: attaches character_refs/prop_refs via appearance_shots inversion + recomposes prompt_text via Pattern 2 (idempotent, graceful-degrade, pre-write schema-validated, atomic write)"
  - "scripts/export_asset.py:_build_registry_snapshot — confirmed-only compact registry projection; conditional generator.registry_snapshot emission"
  - "scripts/verify_contract.py:_producer_registry_integrity extended with prompts→registry direction (Pitfall 17 dangling-ref detection)"
  - "spec/fixtures/v1.1/prompts.json synced to Pattern 2 recompose output (contract oracle for attach_refs)"
affects: [08-03, 09-canvas-consumer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "appearance_shots inversion → refs: build shot_id→[ids] map by inverting registry appearance_shots[]; sorted(set(...)) for idempotency (Pitfall 2 prevention)"
    - "Pattern 2 deterministic template join: [style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting] — identity clauses skipped when refs empty; empty facets skipped; no LLM, no fabrication"
    - "confirmed-only compact projection: _build_registry_snapshot._project hard-filters review_state!=confirmed (Pitfall 7 consistent across attach_refs/snapshot/integrity); representative_image emitted only when truthy (Phase 7 WARNING-2)"
    - "additive integrity extension: extend _producer_registry_integrity in place (no fork — Pitfall 6); reuse confirmed-ID sets accumulated in existing loop for prompts→registry check"
    - "TDD-without-test-framework: RED stub (function signatures + failing bodies) → pure-function assertions confirm fail → GREEN implementation → full verify (mirrors CLAUDE.md no-pytest convention)"

key-files:
  created:
    - prompts/attach_refs.py
  modified:
    - spec/fixtures/v1.1/prompts.json
    - scripts/export_asset.py
    - scripts/verify_contract.py

key-decisions:
  - "Pattern 2 recompose template is locked (CONTEXT Q2): [style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting]; separator = ' · ' (U+00B7); identity clauses + empty facets skipped — deterministic + idempotent by construction"
  - "registry_snapshot confirmed-only hard filter (Pitfall 7): _build_registry_snapshot._project skips review_state!=confirmed — same gating as attach_refs._load_registry + apply_edits build-time gate + _producer_registry_integrity second-line assert"
  - "NO schema_version bump (stays '1.1' — Pitfall 10 prevented); registry_snapshot is additive-optional within v1.1"
  - "Additive integrity extension (no fork — Pitfall 6): prompts→registry check added inside _producer_registry_integrity; reuses char_confirmed_ids/prop_confirmed_ids accumulated in existing loop"
  - "TDD adapted to no-test-framework project: RED = module skeleton with stub bodies + pure-function assertions (no fixture mutation during RED); GREEN = full implementation + CLI fixture sync"

requirements-completed: [PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04]

# Metrics
duration: 6min
completed: 2026-07-24
---

# Phase 8 Plan 02: Producer Wiring (attach_refs + registry_snapshot + Pitfall 17 integrity) Summary

**Three independent producer-side files wiring the confirmed Phase-7 registry onto prompts (attach_refs.py — PROMPT-01/02), the asset manifest (export_asset.py registry_snapshot — PROMPT-04), and the integrity gate (verify_contract.py Pitfall 17 — PROMPT-03); all pure JSON post-processing, zero ML, zero new deps.**

## Performance

- **Duration:** ~6 min (359s)
- **Started:** 2026-07-24T20:27:13Z
- **Completed:** 2026-07-24T20:33:12Z
- **Tasks:** 3
- **Files modified:** 4 (1 new + 3 modified)

## Accomplishments

- **`prompts/attach_refs.py` (NEW, PROMPT-01/02)** — standalone CLI mirroring `prompts/merge_prompts.py`. `_load_registry()` reads characters.json/props.json filtering to `review_state=="confirmed"` only (Pitfall 7 consistent), graceful-degrades to `([],[])` when files absent. `attach()` inverts `appearance_shots[]` → `character_refs[]`/`prop_refs[]` per shot via `sorted(set(...))` (idempotent — Pitfall 2 prevented). `_recompose()` implements the locked Pattern 2 template (`[style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting]`), skipping identity clauses when refs empty and skipping empty facets. Pre-write `Draft202012Validator(prompts.schema.json)` + atomic write (temp + os.replace). Verified idempotent (byte-identical re-run), graceful-degrade (facets-only prompt_text when no registry), schema-valid.
- **`spec/fixtures/v1.1/prompts.json` synced** — fixture prompt_text now matches the Pattern 2 recompose output (contract oracle): shot 1 = `3D 动画,写实渲染,柔和色彩 · 明亮城市街道,远景有树 · 角色:[少女, 路人] · 少女,白色衣裙 · ...`; shot 2 = `... · 角色:[少女] · 道具:[落叶] · ...`. Refs unchanged (already correct from Phase 5); only prompt_text recomposed.
- **`scripts/export_asset.py` (MODIFIED, PROMPT-04)** — added `_build_registry_snapshot(work_dir)` helper: confirmed-only compact projection `{characters:[{id,name,representative_image?,appearance_shots}], props:[...]}`; returns `None` when neither registry file exists (graceful-degrade → field OMITTED, byte-identical to v1.0). `representative_image` emitted only when truthy (Phase 7 WARNING-2: apply_edits OMITS it on ffmpeg failure → no dangling path). `build_asset_dict` conditionally emits `generator.registry_snapshot` mirroring the Phase 6 `warnings` conditional pattern (snapshot called ONCE into local var). `SCHEMA_VERSION` stays `"1.1"` (Pitfall 10 prevented). Verified: no-registry → OMITTED; confirmed-only filters out proposed; representative_image optional.
- **`scripts/verify_contract.py` (MODIFIED, PROMPT-03)** — extended `_producer_registry_integrity` (additive, NOT forked — Pitfall 6 prevented; `grep -c 'def _producer_registry_integrity' == 1`). Accumulates `char_confirmed_ids`/`prop_confirmed_ids` in the existing characters/props loop (populated only when `review_state=="confirmed"`). New prompts→registry block (gated on prompts.json existence): every `character_refs[]`/`prop_refs[]` ID in prompts.json MUST exist in confirmed registry IDs; failures reference "Pitfall 17" + include the dangling ID + shot_id. Verified: clean (no prompts → no-op), dangling ref detected, valid ref passes, ref-to-proposed flagged.

## Task Commits

Each task was committed atomically (Task 1 followed TDD RED/GREEN):

1. **Task 1 (RED): attach_refs stub** - `c12137a` (test) — module skeleton with stub bodies; pure-function assertions confirmed failing
2. **Task 1 (GREEN): attach_refs + Pattern 2 + fixture sync** - `db5d198` (feat) — full implementation + fixture prompts.json synced
3. **Task 2: export_asset registry_snapshot emission** - `9db91e8` (feat)
4. **Task 3: verify_contract Pitfall 17 integrity** - `fae8a31` (feat)

## Files Created/Modified

- `prompts/attach_refs.py` (NEW) — 5 functions: `_atomic_write`, `_load_registry` (confirmed-only graceful-degrade), `attach` (appearance_shots inversion + sorted refs), `_recompose` (Pattern 2 locked template), `main` (argparse CLI + pre-write Draft202012Validator + atomic write).
- `spec/fixtures/v1.1/prompts.json` — prompt_text on both shots recomposed to Pattern 2 output (refs unchanged from Phase 5).
- `scripts/export_asset.py` — added `_build_registry_snapshot` (55-line helper before `build_asset_dict`); extended `build_asset_dict` generator block with `**({"registry_snapshot": snapshot} if snapshot is not None else {})` conditional emit.
- `scripts/verify_contract.py` — `_producer_registry_integrity` extended: confirmed-ID set accumulation in existing loop + new prompts→registry Pitfall 17 check block (gated on prompts.json existence).

## Decisions Made

- **TDD adapted to the no-test-framework project (CLAUDE.md).** The plan marked Task 1 `tdd="true"`, but CLAUDE.md forbids test files (no pytest/unittest). Resolution: RED = module skeleton with stub bodies (`attach` returns refs empty, `_recompose` returns `""`); pure-function assertions (no fixture mutation during RED) confirmed failure; GREEN = full implementation + CLI fixture sync. This honors TDD intent (test-before-full-impl) while respecting the standalone-script convention. The RED commit (`c12137a`) and GREEN commit (`db5d198`) form the gate pair.
- **`_recompose` is module-level (not a method).** The plan's Task 1 `<action>` had a `self._SEP.join(parts)` typo; `_recompose` is a module-level function (no `self`). Used `_SEP.join(parts)` per the RESEARCH Pattern 2 authoritative skeleton (lines 424-455).
- **Otherwise: None — plan executed exactly as written.** All locked decisions (Pattern 2 template, confirmed-only snapshot, no schema bump, additive integrity extension, conditional emit mirroring warnings) were honored verbatim.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan verify block's `bare` test fixture was schema-incomplete**
- **Found during:** Task 1 verify
- **Issue:** The plan's Task 1 `<verify>` inline `bare` input (`[{'shot_id':1, 'subject':'cat', ...}]`) was missing required schema fields `start_sec`/`end_sec`/`duration`. Assertion #4 (`Draft202012Validator(schema).iter_errors(out)` expects 0 errors) failed because `attach()` correctly preserves input fields via `dict(entry)` — it does not synthesize missing required fields (out of scope). The test data, not the implementation, was incomplete.
- **Fix:** Added the missing required fields to the `bare` input (`start_sec:0.0, end_sec:1.0, duration:1.0`) so assertion #4 actually tests "graceful-degrade preserves schema-validity" rather than "attach synthesizes missing required fields". Implementation unchanged.
- **Files modified:** none (test-data-only fix; the implementation is correct).
- **Commit:** n/a (verify-block test-data correction; no source change).

## Issues Encountered

None beyond the Rule 1 test-data fix above. `spec/validate.py` baseline (exit 0) and `verify_contract.py --mode=producer` baseline (exit 0) both preserved end-to-end.

## User Setup Required

None — pure producer-side JSON post-processing. No external services, no env vars, no CLI configuration beyond the existing pipeline.

## Next Phase Readiness

- **Plan 03 (Wave 3 — HTML gallery + pipeline wire + smoke) unblocked.** `html/gen_timeline_html.py` can read `asset.json#generator.registry_snapshot` (preferred, embedded truth) or fall back to external characters.json/props.json for the gallery; prompts.json now carries refs + Pattern 2 prompt_text for chip rendering. `run_pipeline.py:step_timeline` can invoke `prompts/attach_refs.py` as a pre-step (NO counter bump per CONTEXT Q3).
- **Phase 8 gate (Plans 01+02 together) internally consistent:** fixture `asset.json#generator.registry_snapshot` mirrors canonical characters.json/props.json (verified byte-shape); fixture prompts.json prompt_text matches Pattern 2; refs ⊆ confirmed registry IDs. The contract oracle is closed.
- **CONTRACT-09 (backward-compat) preserved:** old assets without registry_snapshot / without prompt refs still validate green (snapshot OMITTED when no registry; refs empty when graceful-degrade).
- **Threat model T-08-04/05/06/07/08/09 all mitigated** at the producer layer: dangling refs caught (Pitfall 17), confirmed-only snapshot (Pitfall 7), anti-traversal schema + representative_image-optional (WARNING-2), atomic writes (Pitfall 18 freeze + partial-write protection), idempotent output (Pitfall 2).
- **No blockers.**

## Self-Check: PASSED

- FOUND: `prompts/attach_refs.py` (created)
- FOUND: `spec/fixtures/v1.1/prompts.json` (modified)
- FOUND: `scripts/export_asset.py` (modified)
- FOUND: `scripts/verify_contract.py` (modified)
- FOUND: `08-02-SUMMARY.md` (this file)
- FOUND: commit `c12137a` (Task 1 RED, test)
- FOUND: commit `db5d198` (Task 1 GREEN, feat)
- FOUND: commit `9db91e8` (Task 2, feat)
- FOUND: commit `fae8a31` (Task 3, feat)

---
*Phase: 08-prompt-reference-system-shot-timeline-html-gallery*
*Completed: 2026-07-24*
