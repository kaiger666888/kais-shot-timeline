---
phase: 18-contract-v1-3
reviewed: 2026-08-19T14:44:31Z
depth: standard
review_mode: re-review after fixes (iteration 2 of --auto loop)
review_range: b08d9d5..87ced5c
files_reviewed: 4
files_reviewed_list:
  - scripts/export_asset.py
  - scripts/verify_contract.py
  - spec/SPEC.md
  - spec/README.md
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
previous_findings:
  warnings_total: 6
  warnings_verified_fixed: 6
  info_carried_open: 3
fix:
  fixed_at: 2026-08-19T14:39:27Z
  iteration: 1
  in_scope: 6
  fixed: 6
  skipped: 0
  report: 18-REVIEW-FIX.md
  commits:
    - b08d9d5 (WR-01)
    - 2230076 (WR-02)
    - f0a7cfd (WR-03)
    - b9fd1c7 (WR-04)
    - ad7305c (WR-05)
    - 87ced5c (WR-06)
status: clean
---

# Phase 18: Code Review Report — Re-review (iteration 2)

**Reviewed:** 2026-08-19T14:44:31Z
**Depth:** standard
**Review mode:** re-review after fixes (`b08d9d5..87ced5c`; WR-01's fix is in `b08d9d5` itself, the range base)
**Files Re-reviewed:** 4 (`scripts/export_asset.py`, `scripts/verify_contract.py`, `spec/SPEC.md`, `spec/README.md`)
**Status:** clean — all 6 Warning findings verified fixed with runtime evidence; **no new Critical or Warning findings**. The 3 first-pass Info findings (IN-01..IN-03) remain open (explicitly out of fix scope) and are carried below unchanged.

## Summary

Re-reviewed the 4 in-scope files after the 6 warning fixes. Every fix was verified behaviorally, not just by reading the diff — each original repro was re-run, and the WR-04 fallback schemas were diffed against the real `v1.0`/`v1.1`/`v1.2` git tags (which exist in this repo), giving ground-truth confirmation of the "simulated old schema matches the tagged schema" question the fixer flagged as requiring human verification.

Verification evidence, all green:

- `python3 spec/validate.py` → exit 0; tier line counts measured at exactly **6 / 10 / 12 / 13** `[valid…]` lines + 5 smoke lines — matches the WR-06 README sentence verbatim.
- `PHASE4_SELF_TEST=1 PHASE4_ASSET_DIR=spec/fixtures/v1.3 python3 scripts/verify_contract.py --mode=producer` → exit 0, self-test PASS + producer OK (this exercises the WR-01 unwrap over a real object-mount manifest, the WR-03 producer roundtrip block over a real sidecar, `_cross_version_check`, and `_fixture_consistency_check` end-to-end).
- `_cross_version_check()` → True; `_fixture_consistency_check()` → True.
- ep01 default producer run still FAILs on `registry.draft.json` schema drift — **pre-existing, known accepted-out-of-scope (deferred #2), unchanged by these fixes**; not re-flagged.

No new bugs were found in the fix hunks. Details per finding below.

## Re-review Verification (Narrative Findings)

### WR-01: `run_self_test` unwrap of `data.roundtrip` object mount — VERIFIED FIXED

**File:** `scripts/verify_contract.py:1343-1353`
The copy loop now mirrors the `validate_eight_shapes` unwrap: dict-valued `data.*` entries resolve `.path`; a non-string `.path` skips the copy (leaving the drift for the asset-shape validator to flag, per the comment). Re-ran the original repro (`PHASE4_SELF_TEST=1 … --asset-dir spec/fixtures/v1.3`): previously `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'dict'`; now a clean `(True, "corrupt asset (schema_version='v1') correctly rejected with 1 error(s)…")` and `roundtrip.json` is copied into the temp fixture set.

### WR-02: guarded shots/speakers iteration (warn+OMIT semantics) — VERIFIED FIXED

**Files:** `scripts/export_asset.py:388-391`, `scripts/verify_contract.py:778-783` (v1.2 speakers), `:829-834` (v1.3 roundtrip fixture side)
Re-ran `build_asset_dict` against four malformed sidecar shapes — `shots: 5` (int), `"abc"` (str), `{}` (dict), and key-absent — all four now take the `[warn] roundtrip.json malformed → data.roundtrip will be OMITTED: shots is <type>, expected array` path with no crash and no mount; a valid sidecar still mounts `{'path': 'roundtrip.json', 'accepted_count': 1, 'rejected_count': 1}` (no regression). The `raise ValueError` sits inside the `try` whose handler catches `(OSError, json.JSONDecodeError, ValueError)`, so the documented warn+OMIT contract now holds for every malformed shape. The harness-side guards record a failure and degrade to `[]` instead of raising.

### WR-03: roundtrip integrity in `_producer_registry_integrity` — VERIFIED FIXED

**File:** `scripts/verify_contract.py:1104-1160` (producer side), `:838-870` (fixture-side count cross-check)
Constructed a drifted producer dir (`roundtrip.json` with dangling `shot_id: 999` + `asset.json` mount claiming 5/0 vs actual sidecar 1/1): the gate reports exactly the two expected failures (`roundtrip.json: shot_id 999 unknown`, `asset.json data.roundtrip counts stale: mount=5/0 sidecar=1/1`). A consistent dir (v1.3 fixture copied) yields `[]` — no false positive. Counting semantics match `export_asset.build_asset_dict` exactly (verdict dict + decision ∈ {accepted, rejected}; non-dict entries skipped). The manifest re-read is guarded at both levels (`isinstance(…, dict)` on the manifest and on `data`), and unreadable/missing `asset.json` degrades to skip-the-cross-check rather than crash. Asymmetry note (benign): when `shots` is non-list, the producer block skips the count check under `else:` while the fixture block runs it against `rt_shots = []` — both fail loud either way.

### WR-04: cumulative strip lists in `_recover_v1`/`_recover_v11` fallbacks — VERIFIED FIXED against git-tag ground truth

**File:** `scripts/verify_contract.py:295-353` (`_recover_v1_schema`), `:356-412` (`_recover_v11_schema`)

The fixer flagged this as "requires human verification" — verified directly, since the repo carries the `v1.0`/`v1.1`/`v1.2` tags. Each recover fallback was forced (git call patched to raise, simulating tag-less CI) and deep-diffed against the real tagged schema:

| Recovered schema | Structural differences vs real tag |
|---|---|
| `_recover_v1_schema("asset")` | **0** — exact match |
| `_recover_v1_schema("prompts")` | 1 — `items.properties.action.description` prose only |
| `_recover_v11_schema("asset")` | 1 — `generator.warnings.description` prose only |
| `_recover_v12_schema("asset")` | 1 — `generator.warnings.description` prose only |

Every difference is a `description` string (documentation text with zero validator semantics); all validation-relevant structure — properties, `required`, `additionalProperties`, `items` — matches the tags exactly. Specific cumulative-semantics questions answered:

- `_recover_v1_schema` pops `generator.warnings` **entirely**, which also removes the v1.3-widened `items` wholesale — correct for v1.0 (which had neither), confirmed by the 0-diff result. No separate items restoration is needed at this tier.
- `_recover_v11_schema` correctly **retains** `registry_snapshot` and `media.characters`/`media.props` and `data.characters`/`data.props` (all v1.1-milestone additions present in the real `v1.1` tag) while stripping v1.2/v1.3 data keys and restoring `warnings.items = {"type": "string"}`.
- Negative probe (the T-18-08 contamination class, one tier down): with the fixed fallback, a v1.2-era asset carrying a v1.3-only structured warning entry FAILS backward (d) with `at /generator/warnings/0: … is not of type 'string'` (non-additionalProperties → counted); replaying the **pre-fix** strip list against the same drifted instance false-greens. The hole WR-04 described is demonstrably closed, and clean v1.2 data still passes (no false positive).

Residual (accepted, validation-inert): because the fallback deep-copies the *current* schema, human-facing `description` prose from later phases leaks into the simulated old schemas. This cannot change any validator verdict and is inherent to the deep-copy approach; no action required.

### WR-05: SPEC §3 `generator.warnings` union type — VERIFIED FIXED

**File:** `spec/SPEC.md:89`
The type cell now reads `array\<string \| {code, detail}\>` with the RT-04 closed enum (`comfyui_unreachable / vram_insufficient / scorer_model_missing`) and `detail` optional string — checked against `spec/schemas/asset.schema.json#properties.generator.properties.warnings`: the anyOf object branch's enum and `detail` type match the new prose verbatim. The Required-column annotation "(v1.1;items 加宽 v1.3)" is accurate. **Note for IN-01:** this fix did **not** add a `data.roundtrip` row to the §3 field table (rows still end at `media.props`; `data.audio_semantic`/`data.speakers`/`data.roundtrip` all still absent) — IN-01 remains open, as expected for its Info tier.

### WR-06: README 4-tier counts — VERIFIED FIXED

**File:** `spec/README.md:64`
The rewritten expected-output sentence claims 6 `[valid]` + 10 `[valid-v11]` + 12 `[valid-v12]` + 13 `[valid-v13]` + ≥5 `[smoke-*]` lines. Measured from an actual run: 6 / 10 / 12 / 13 / 5 — exact match, and consistent with the Layout section of the same file (which lists 6/10/12/13 fixture files). The exit-code semantics sentence (four fixture tiers gate; smoke only under `--strict-smoke`) matches the observed `[validate] OK` exit-0 behavior and the final failures summary line.

## New Findings

None. No new Critical or Warning findings; no new Info findings. All fix hunks were additionally probed for introduced defects (guard placement, exception scope, nesting of the count cross-check, false-positive potential on consistent inputs) — clean.

## Carried-over Open Items (not re-flagged; documented for traceability)

### IN-01: SPEC §3 field table still lacks `data.roundtrip` (and `data.audio_semantic`/`data.speakers`) rows — OPEN

**File:** `spec/SPEC.md:91-103`
Pre-existing Info, out of fix scope; re-confirmed post-fix that WR-05 did not cover it. §5.10's manifest-mount paragraph remains the covering documentation.

### IN-02: Backward-filter exemption is prefix-broad under `generator.warnings` — OPEN

**File:** `scripts/verify_contract.py:616-626`
Pre-existing Info, unchanged by the fixes; forward pass (e) remains the compensating control.

### IN-03: Stale docstrings/annotations — OPEN

**Files:** `scripts/export_asset.py:282-283` (`warnings: list[str] | None` annotation predates the v1.3 widening), `scripts/verify_contract.py:468, 1173`
Pre-existing Info, unchanged by the fixes.

### Known deferred (accepted out of scope at iteration 1; re-confirmation only)

- **ep01 `registry.draft.json` drift (deferred #2):** default `--mode=producer` still fails with `registry at /<root>: Additional properties are not allowed ('method', 'total_clusters', 'total_crops'…)`. Identical failure to iteration 1 — the fixes neither caused nor masked it.
- **Producer-side speakers list-level guard** (`verify_contract.py:1000` — `speakers_data.get("speakers", []) or []` still iterates an int value into TypeError): noted by the fixer for future harmonization; unchanged, per-entry guards remain present.

---

_Reviewed: 2026-08-19T14:44:31Z (re-review, iteration 2)_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
