---
phase: 18-contract-v1-3
fixed_at: 2026-08-19T14:39:27Z
review_path: .planning/phases/18-contract-v1-3/18-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 18: Code Review Fix Report

**Fixed at:** 2026-08-19T14:39:27Z
**Source review:** .planning/phases/18-contract-v1-3/18-REVIEW.md
**Iteration:** 1
**Fix scope:** Critical + Warning (Info findings IN-01..IN-03 not in scope)

**Summary:**
- Findings in scope: 6 (0 Critical, 6 Warning)
- Fixed: 6
- Skipped: 0

**Gates after all fixes (all green):**
- `python3 spec/validate.py` → exit 0 (minimal 6 / v1.1 10 / v1.2 12 / v1.3 13, failures=0)
- `PHASE4_ASSET_DIR=<ep02> python3 scripts/verify_contract.py --mode=producer` → exit 0
- `PHASE4_SELF_TEST=1 ... --mode=producer` → self-test PASS + producer OK (ep02 **and** the reviewer's WR-01 repro `--asset-dir spec/fixtures/v1.3`)
- `python3 -m pytest tests/ -x -q` → 36 passed

**Out of scope (deferred per fix contract):** ep01 `registry.draft.json` pre-existing issue (deferred-items #2 — runtime data, not code).

## Fixed Issues

### WR-01: `run_self_test` crashes with unhandled TypeError on the v1.3 object mount

**Files modified:** `scripts/verify_contract.py`
**Commit:** b08d9d5
**Applied fix:** The self-test file-copy loop now mirrors the `validate_eight_shapes` unwrap special-case: `data.*` values that are dicts (the v1.3 `data.roundtrip` object mount) are unwrapped via `.path` before the `src_dir / rel` path join; a `.path` that is not a string (malformed mount) is skipped (not copied) — the asset-shape schema validation is responsible for flagging that drift.
**Verification:** Reviewer's exact repro `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer --asset-dir spec/fixtures/v1.3` previously crashed with `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'dict'`; now exits 0 with self-test PASS + producer OK (roundtrip.json now copied into the temp fixture set).

### WR-02: Export-time roundtrip counting violates its own graceful-degrade contract

**Files modified:** `scripts/export_asset.py`, `scripts/verify_contract.py`
**Commit:** 2230076
**Applied fix:** (a) `export_asset.py` roundtrip mount block: `rt.get("shots")` is now type-guarded — any non-list value (int → old code raised uncaught TypeError; str/dict → old code silently emitted 0/0 stats) raises `ValueError`, which the existing `except (OSError, json.JSONDecodeError, ValueError)` handler turns into the documented `[warn]` + OMIT path. (b) `verify_contract.py` fixture-side v1.3 roundtrip block (`shots`) and v1.2 speakers block (`speakers`, the "ideally :742" pre-existing sibling) now record an `expected array` failure instead of crashing on non-list values. Note: the producer-side speakers block in `_producer_registry_integrity` has the same iteration shape but was not cited in the finding and was left untouched.
**Verification:** Behavioral tests: `roundtrip.json = {"schema_version": "1.3", "shots": 5}` → `[warn] ... shots is int, expected array` + `data.roundtrip` OMITTED (no crash); `shots: "abc"` → warn + OMIT (no silent 0/0); valid list → mount 1/1 emitted unchanged. Fixture-side: corrupted v1.3 `shots=5` / v1.2 `speakers="oops"` each produce a clean `expected array` failure; unmodified fixtures stay green.

### WR-03: Roundtrip cross-file integrity gate is fixture-only

**Files modified:** `scripts/verify_contract.py`
**Commit:** f0a7cfd
**Applied fix:** (a) Added a roundtrip block to `_producer_registry_integrity` (documented as check (g) in its docstring), mirroring the fixture-side v1.3 block and gated on `roundtrip.json` existence: `shots[].shot_id ⊆ shots.json IDs`, verdict counting with `export_asset.build_asset_dict` semantics, plus the count cross-check — when `asset.json#data.roundtrip` mount is present, `{accepted,rejected}_count` must equal the sidecar's actual verdict counts. (b) Added the same count cross-check to the fixture-side v1.3 block in `_fixture_consistency_check` (against `spec/fixtures/v1.3/asset.json`), closing the "drifted fixture / stale re-export passes all gates" gap on both sides.
**Verification:** Drift-injection tests on a copy of the v1.3 fixture as a fake producer dir: dangling `shot_id 99` → `roundtrip.json: shot_id 99 unknown`; mount counts 2/1 vs sidecar 1/1 → `asset.json data.roundtrip counts stale: mount=2/1 sidecar=1/1`; roundtrip.json absent → clean no-op (graceful-degrade). Fixture side: stale mount (1/0 vs 1/1) → failure. Shipped fixture (1/1 == 1/1) stays green.

### WR-04: `_recover_v1_schema` / `_recover_v11_schema` fallbacks not extended with v1.2/v1.3 deltas

**Files modified:** `scripts/verify_contract.py`
**Commit:** b9fd1c7
**Applied fix:** Strip lists made cumulative (kept the per-function structure rather than refactoring into a shared helper, to keep the change surgical): `_recover_v1_schema` fallback now strips `data.{characters,props,audio_semantic,speakers,roundtrip}` + `media.{characters,props}` + `generator.{warnings,registry_snapshot}` (neither generator key existed in v1.0); `_recover_v11_schema` fallback now strips `data.{audio_semantic,speakers,roundtrip}` and restores `generator.warnings.items = {"type": "string"}` (v1.1 has warnings, but string-only items), mirroring `_recover_v12_schema`'s Wrinkle-1 chain. Docstrings updated to state the cumulative obligation.
**Verification (fixed: requires human verification of the cumulative semantics — behavioral evidence below):** Simulated tag-less environment (git primary path forced to fail) and asserted: (1) fallback property-key sets for `data`/`media`/`generator` are **identical to the real `git show v1.0/v1.1/v1.2` schemas** on all three tiers; (2) backward passes (b) v1.1-fixture × fallback-v1.0 and (d) v1.2-fixture × fallback-v1.1 yield 0 non-additionalProperties errors (no false red); (3) contamination probe — a structured `{code, detail}` warning entry is now **rejected** by fallback v1.1 (old code fake-greened it); (4) real-tag-path `_cross_version_check()` still green.

### WR-05: SPEC §3 field table still types `generator.warnings` as `array<string>`

**Files modified:** `spec/SPEC.md`
**Commit:** ad7305c
**Applied fix:** §3 field-table type cell updated to `array<string | {code, detail}>`, Required cell now reads "— (v1.1;items 加宽 v1.3)", and the description documents the v1.3 dual-form items with the RT-04 closed enum (`comfyui_unreachable` / `vram_insufficient` / `scorer_model_missing`), pointing to `asset.schema.json#generator.warnings.items` and §4 Changelog `1.3` (mirroring the schema description as suggested).
**Verification:** Re-read of the edited row; table row structure intact (pipes escaped).

### WR-06: README "How to validate" expected output is stale

**Files modified:** `spec/README.md`
**Commit:** 87ced5c
**Applied fix:** Expected-output sentence updated to the four-tier reality: 6 行 `[valid]` + 10 行 `[valid-v11]`（…+ registry-edits）+ 12 行 `[valid-v12]`（…+ audio_semantic / speakers）+ 13 行 `[valid-v13]`（…+ roundtrip）+ 至少 5 行 `[smoke-valid|smoke-FAIL]`;四阶 fixture gate 均计入退出码,smoke 默认不计入（`--strict-smoke` 计入）。
**Verification:** Ran `python3 spec/validate.py` and counted the actual output lines: 6 / 10 / 12 / 13 — exact match with the new text; exit 0.

## Skipped Issues

None — all 6 in-scope findings fixed.

---

_Fixed: 2026-08-19T14:39:27Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
