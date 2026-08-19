---
phase: 18-contract-v1-3
reviewed: 2026-08-19T14:31:18Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - scripts/export_asset.py
  - scripts/verify_contract.py
  - spec/README.md
  - spec/schemas/asset.schema.json
  - spec/schemas/roundtrip.schema.json
  - spec/SPEC.md
  - spec/validate.py
findings:
  critical: 0
  warning: 6
  info: 3
  total: 9
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-08-19T14:31:18Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the v1.3 contract deliverables: `roundtrip.schema.json` (new), the `asset.schema.json` deltas (`data.roundtrip` object mount + `generator.warnings` items widening), `export_asset.py` (`SCHEMA_VERSION = "1.3"` + roundtrip mount + `_valid_warnings_list` widening), `verify_contract.py` (v1.2↔v1.3 bidirectional proof + EIGHT_SHAPES roundtrip + fixture consistency), `validate.py` (4-tier gate), and the SPEC/README prose.

Verified green at runtime: `spec/validate.py` exits 0 (minimal 6 / v1.1 10 / v1.2 12 / v1.3 13, all failures=0); `_cross_version_check()` returns True; the `_recover_v12_schema` **fallback strip path** (simulated in isolation, git tag bypassed) yields exactly the 3 documented exempt errors (2× items-type under `generator.warnings` + 1× additionalProperties on `data`) with 0 non-exempt; the A3 negative test claim holds (injected `asset_type: "other"` → 1 non-exempt `const` error). Schema counts check out (14 schema files, 13 v1.3 fixture files, fixture mount counts 1/1 match `roundtrip.json`). No secrets, no dangerous functions, SQL is parameterized, subprocess calls are list-args.

However, the adversarial pass found **two reproducible harness/producer crashes on the exact data shape this phase introduced** (the object-valued `data.roundtrip` mount and a structurally-malformed sidecar), one integrity-gate coverage gap that is asymmetric with the v1.2 speakers precedent, stale recover-fallbacks that weaken the backward proof in the documented tag-less scenario, and two prose-vs-schema contradictions in the contract docs (which SPEC §1 itself classifies as defects).

## Warnings

### WR-01: `run_self_test` crashes with unhandled TypeError on the v1.3 object mount

**File:** `scripts/verify_contract.py:1202`
**Issue:** The self-test file-copy loop assumes every `data.*` value is a string path:

```python
for shape, rel in manifest_copy.get("data", {}).items():
    src_data = src_dir / rel          # rel is a dict for data.roundtrip
```

`validate_eight_shapes` got the object-mount unwrap special-case this phase (lines 257-266, the "Pitfall 2: 勿只做一半" mitigation), but `run_self_test`'s copy loop did not — the exact half-done failure mode the code's own comment warns about. Reproduced:

```
$ PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer --asset-dir spec/fixtures/v1.3
TypeError: unsupported operand type(s) for /: 'PosixPath' and 'dict'
  File "scripts/verify_contract.py", line 1202, in run_self_test
    src_data = src_dir / rel
```

Latent today only because ep01 has no roundtrip.json; it fires on every self-test run once Phase 20 emits real assets (or when PHASE4_ASSET_DIR points at any v1.3 asset). Exit code is coincidentally 1, so it cannot false-green, but the harness crashes with a traceback instead of a clean self-test PASS/FAIL, and the copied fixture set silently omits `roundtrip.json`.
**Fix:** Mirror the `validate_eight_shapes` unwrap:

```python
for shape, rel in manifest_copy.get("data", {}).items():
    if isinstance(rel, dict):          # v1.3 object mount (data.roundtrip)
        rel = rel.get("path")
        if not isinstance(rel, str):
            continue                   # malformed mount; asset-shape check will flag
    src_data = src_dir / rel
```

### WR-02: Export-time roundtrip counting violates its own graceful-degrade contract (uncaught TypeError; silent 0/0 emit)

**File:** `scripts/export_asset.py:384`
**Issue:** The roundtrip mount block documents "malformed / 非 dict → [warn] + OMIT（不持久化可疑统计）" and raises `ValueError` for the non-dict top-level so the `except (OSError, json.JSONDecodeError, ValueError)` handler catches it — but the iteration over `shots` is unguarded:

```python
for s in rt.get("shots") or []:   # shots: 5 → TypeError, NOT caught
```

Reproduced with `roundtrip.json = {"schema_version": "1.3", "shots": 5}`: `TypeError: 'int' object is not iterable` — an unhandled traceback crashes `build_asset_dict`/`main()` instead of the documented `[warn]` + OMIT. Additionally, `shots` as a string or dict (iterable, non-list) silently emits `{"path": "roundtrip.json", "accepted_count": 0, "rejected_count": 0}` with no warning — persisting stats derived from a structurally-invalid sidecar, contradicting the "不持久化可疑统计" rationale in the same comment block. The identical unguarded-iteration shape exists in `scripts/verify_contract.py:785` (`for entry in rt_data.get("shots", []) or []` — new this phase) and `:742` (v1.2 speakers block, pre-existing).
**Fix:**

```python
shots = rt.get("shots")
if not isinstance(shots, list):
    raise ValueError(
        f"shots is {type(shots).__name__}, expected array")
for s in shots:
    ...
```

applied at `export_asset.py:384` and `verify_contract.py:785` (and ideally `:742`).

### WR-03: Roundtrip cross-file integrity gate is fixture-only — producer asset dirs get zero roundtrip checks

**File:** `scripts/verify_contract.py:803-1021` (gap), `766-792` (fixture-only check)
**Issue:** The v1.2 precedent (speakers, SPEAKER-03) added integrity checks to BOTH `_fixture_consistency_check` (fixture side, lines 709-758) AND `_producer_registry_integrity` (producer side, lines 901-967). Phase 18 added the roundtrip `shot_id ⊆ shots.json#id` check only to the fixture side (`spec/fixtures/v1.3`, lines 766-792). `_producer_registry_integrity` has no roundtrip block at all — a real post-Phase 20 asset dir whose `roundtrip.json` references dangling shot_ids (hand-edited drift, or a Phase 20 producer bug — the exact Pitfall-17 class the speakers/characters checks exist to catch) passes `--mode=producer` green. `validate_eight_shapes` does schema-validate the sidecar contents when the mount is present, but schema validation cannot see cross-file ID references. Additionally, nothing anywhere (fixture or producer side) cross-checks `asset.data.roundtrip.{accepted,rejected}_count` against the sidecar's actual verdict counts — the shipped fixture is consistent (1/1), but a drifted fixture or stale re-export would pass all gates.
**Fix:** Add a roundtrip block to `_producer_registry_integrity` mirroring lines 766-792 (gated on `roundtrip.json` existence; `shot_id ⊆ shot_ids`), plus a count cross-check when the `data.roundtrip` mount is present:

```python
rt_path = asset_dir / "roundtrip.json"
if rt_path.is_file():
    ...  # shot_id ⊆ shot_ids check
    mount = (manifest.get("data") or {}).get("roundtrip")
    if isinstance(mount, dict):
        if mount.get("accepted_count") != acc or mount.get("rejected_count") != rej:
            failures.append(
                f"asset.json data.roundtrip counts stale: "
                f"mount={mount.get('accepted_count')}/{mount.get('rejected_count')} "
                f"sidecar={acc}/{rej}")
```

### WR-04: `_recover_v1_schema` / `_recover_v11_schema` programmatic fallbacks not extended with v1.2/v1.3 deltas — backward proof silently weakens in tag-less environments

**File:** `scripts/verify_contract.py:295-336` (`_recover_v1_schema`), `339-378` (`_recover_v11_schema`)
**Issue:** Phase 18 correctly taught `_recover_v12_schema` the Wrinkle-1 chain (pop `data.roundtrip` AND restore `warnings.items = {"type": "string"}`, per T-18-08 "fallback 产出被污染的假 schema → backward 证明会假绿") — but did not cumulatively extend the older recover fallbacks. In the fallback's own documented rationale ("tag 缺失 / git 不可用, e.g. CI shallow clone"), `_recover_v11_schema("asset")` deep-copies the **current v1.3** schema and strips only `audio_semantic`/`speakers` — the resulting "v1.1" schema still contains `data.roundtrip` and the widened warnings items. Likewise `_recover_v1_schema` strips only `characters`/`props` (not `audio_semantic`/`speakers`/`roundtrip`, nor `generator.warnings`/`registry_snapshot` which did not exist in v1.0). Backward passes (b)/(d) then accept v1.2/v1.3-era additions that real v1.0/v1.1 schemas reject — the check proves strictly less than its output message claims. Results are coincidentally identical for the current shipped fixtures (the v1.1/v1.2 fixtures contain no `roundtrip` key and their warnings are strings, verified by reasoning over the fixture contents), so this is latent, but it is the precise contamination class the phase's own T-18-08 comment exists to prevent, one recover-tier down.
**Fix:** Make the strip lists cumulative: `_recover_v11_schema` should also `data_props.pop("roundtrip", None)` and restore `warnings_schema["items"] = {"type": "string"}`; `_recover_v1_schema` should strip `characters/props/audio_semantic/speakers/roundtrip` from `data` (+ media characters/props, `generator.warnings`, `generator.registry_snapshot`). Alternatively, single-source a `_strip_to_version(schema, target)` helper so each bump updates one table.

### WR-05: SPEC §3 field table still types `generator.warnings` as `array<string>` after the v1.3 widening

**File:** `spec/SPEC.md:89`
**Issue:** The manifest field table — the primary per-field reference for the contract — says:

```
| `generator.warnings` | array\<string\> | — (v1.1) | ... |
```

The v1.3 widening to `string | {code, detail}` is documented in §4 Changelog and the warnings schema description, but §3 was not updated. SPEC §1 states: "本文档的任何与 schema 不一致都视为 Phase 1 缺陷,必须修复" — this is a live schema-vs-prose contradiction introduced by this phase's schema change. A consumer author reading §3 (and the §3-only field table is what a TS-type generator author would scan) would type warnings as `string[]` and crash on structured entries.
**Fix:** Update the type cell to `array\<string | {code, detail}\>` and add one sentence pointing to the RT-04 closed enum (`comfyui_unreachable / vram_insufficient / scorer_model_missing`), e.g. mirroring the schema description at `spec/schemas/asset.schema.json:78`.

### WR-06: README "How to validate" expected output is stale and contradicts the Layout section of the same file

**File:** `spec/README.md:64`
**Issue:** The expected-output description claims "9 行 `[valid-v11] <shape>`(v1.1: 上述 6 + characters / props / registry)" — but `V11_ORDER` has had 10 entries since Phase 7 added `registry-edits`, and the section mentions no `[valid-v12]`/`[valid-v13]` lines at all. The Layout section 15 lines up (line 49), which this phase did update, correctly says "minimal 6/6 + v1.1 10/10 + v1.2 12/12 + v1.3 13/13 四 pass". An operator running `spec/validate.py` and comparing against this section sees 3 unexplained tiers and a wrong v1.1 count; worse, the missing v1.2/v1.3 lines mean a silently-skipped tier would look anomalous against the doc rather than expected.
**Fix:** Update the sentence to: "预期输出:6 行 `[valid]` + 10 行 `[valid-v11]` + 12 行 `[valid-v12]` + 13 行 `[valid-v13]` + 至少 5 行 `[smoke-valid|smoke-FAIL]`;四阶 fixture gate 均计入退出码,smoke 默认不计入(`--strict-smoke` 计入)。"

## Info

### IN-01: SPEC §3 field table has no `data.roundtrip` row (nor `data.audio_semantic`/`data.speakers`)

**File:** `spec/SPEC.md:91-103`
**Issue:** The manifest field table lists `data.characters`/`data.props`/`media.characters`/`media.props` (v1.1 rows) but omits the v1.2 mounts (pre-existing) and the new v1.3 `data.roundtrip` object mount. §5.10's "渲染安全与 manifest 挂载说明" paragraph covers it, but the field table is incomplete as the single-scroll manifest reference — especially worth adding since `data.roundtrip` is the first object-valued mount (type differs from every sibling row).
**Fix:** Add rows: `| data.roundtrip | object {path, accepted_count, rejected_count} | — (v1.3) | ... |` (and backfill the two v1.2 rows).

### IN-02: Backward-filter exemption is prefix-broad — any type/anyOf error under `generator.warnings` is exempted

**File:** `scripts/verify_contract.py:582-592`
**Issue:** Verified by probe: injecting `generator.warnings = "oops"` (whole-field type drift, not items widening) into the v1.3 fixture yields 0 non-exempt errors against the recovered v1.2 schema, because `tuple(e.absolute_path)[:2] == ("generator", "warnings")` matches the field itself, not just item positions. The only thing preventing this from masking real drift is that pass (e) forward-validates the fixture against the current v1.3 schema (which requires `warnings` to be an array) — defense-in-depth holds today, but the filter is looser than its comment ("items widening … error path 精确豁免") suggests.
**Fix:** Pin item-level paths: require `len(e.absolute_path) >= 3 and isinstance(e.absolute_path[2], int)` (plus optionally `e.absolute_path[3] in (None,)` to exclude nested `code`/`detail` type errors).

### IN-03: Stale docstrings/annotations around the widened warnings and the grown harness

**File:** `scripts/export_asset.py:283`; `scripts/verify_contract.py:434-437, 453, 1032`
**Issue:** (a) `build_asset_dict(..., warnings: list[str] | None = None)` and its docstring "可选非致命警告字符串列表" are now inaccurate — v1.3 admits `list[str | {code, detail}]` (the widening this phase shipped). (b) `_cross_version_check`'s docstring header still says "双向 v1↔v1.1 兼容证明" and the (a)-pass comment says "当前 v1.1 已扩展" although the function now proves the 4-way v1.0↔v1.1↔v1.2↔v1.3 chain. (c) `run_producer_check`'s docstring step 4 says "validate_six_shapes 跑 6 个 schema" — the function has been `validate_eight_shapes` covering 12 shapes since v1.2/v1.3.
**Fix:** Update the annotation to `list[str | dict] | None`, and refresh the three docstring passages to match current behavior.

---

_Reviewed: 2026-08-19T14:31:18Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
