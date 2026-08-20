---
phase: 18-contract-v1-3
verified: 2026-08-19T23:15:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 18: Contract v1.3 Verification Report

**Phase Goal:** Lock the v1.3 contract — `roundtrip.schema.json` sidecar + `asset.json#data.roundtrip` optional 挂载 + `SCHEMA_VERSION="1.3"` 单源 + fixture/validate gate + SPEC — BEFORE any round-trip code writes against it（契约先行，mirror v1.1 Phase 5 / v1.2 Phase 11 先例）
**Verified:** 2026-08-19T23:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `roundtrip.schema.json`（draft 2020-12、`additionalProperties:false`）对人工 fixture 全字段校验通过；`asset.schema.json` 增 optional `data.roundtrip`（不进 `required[]`） | ✓ VERIFIED | `Draft202012Validator.check_schema` passes; `$schema` = draft 2020-12 URI; `additionalProperties:false` at 8 object levels (root, shots.items, regen, status, scores, midframe_sim, judge, verdict); root required exactly `["schema_version","shots"]`; shots.items required exactly `["shot_id"]`; regen required exactly the 5-tuple; `video_content_hash` pattern `^[0-9a-f]{16}$`; attribution enum `[prompt_faithful, model_diverged, prompt_underspecified]`; verdict required `["decision","source"]` + optional `decided_at` (no `format` keyword); `status.state` enum `["failed"]` single value; `maxLength:2000` on `judge.reason` + `status.error`; zero occurrences of pending/rendering/fps/"seed"/threshold/门槛/format. Full-field synthetic instance VALID; 4 negative mutations (bogus field / score 1.5 / attribution "banana" / hash "XYZ") all rejected. `spec/fixtures/v1.3/roundtrip.json` validates (full shot 1 + degrade shot 2). asset.schema.json: `data.properties.roundtrip` object mount (`aP:false`, required `["path","accepted_count","rejected_count"]`, path pattern identical to sibling `data.shots`); **`data.required` UNCHANGED at exactly `['shots','audio_analysis','transcript','frames','prompts']`**; 10 data props; forward-compat re-validated minimal/v1.1/v1.2 fixtures all VALID |
| 2 | `SCHEMA_VERSION = "1.3"` 在 export_asset.py 单源锁定；roundtrip.json 缺席时 v1.2 及以前全部数据文件 byte-identical（RT-01 红线） | ✓ VERIFIED | `SCHEMA_VERSION = "1.3"` at line 59; `grep -c 'SCHEMA_VERSION = "1.3"'` == 1 AND `grep -c 'SCHEMA_VERSION = '` == 1 (single source, no duplicate literal). Byte-identical-absent proven via Phase 11 framework (re-run in verifier's own process): (a) data-keys smoke — minimal work_dir → exactly 5 required data keys + `schema_version == "1.3"`; v1.2-superset work_dir (characters/props/audio_semantic/speakers present, roundtrip absent) → exactly the 9 v1.2-era keys, zero roundtrip trace; (b) substrate diff — all 11 non-asset v1.3 fixture files byte-identical to `spec/fixtures/v1.2/`; (c) `diff <(git show v1.2:spec/schemas/asset.schema.json)` shows ONLY the two documented hunks (warnings items widening + roundtrip mount block); audio_semantic.schema.json 0 lines changed vs v1.2 tag. Malformed roundtrip.json (invalid JSON / list / shots=int / str / dict) → `[warn]` + mount OMIT (never `None`/`{}` defaults) |
| 3 | `validate.py` shape gate 扩展三层门全绿 + `verify_contract.py` v1.2↔v1.3 bidirectional cross-version proof（forward 0 / backward 0 non-additive） | ✓ VERIFIED | `python3 spec/validate.py` → exit 0, summary `minimal failures=0, v1.1 failures=0, v1.2 failures=0, v1.3 failures=0, smoke failures=0`; exactly 13 `[valid-v13]` lines incl. `[valid-v13] roundtrip`; `--strict-smoke` also exit 0; `V13_ORDER` = 13 entries extending V12_ORDER. `PHASE4_ASSET_DIR=<ep02> python3 scripts/verify_contract.py --mode=producer` → exit 0 with the exact line `v1.0↔v1.1↔v1.2↔v1.3 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors, excluding documented v1.3 deltas: data.roundtrip + warnings items widening)` + `v1.1 + v1.2 + v1.3 fixture set cross-file IDs consistent (0 dangling)`. `_recover_v12_schema` verified on BOTH paths (git-tag primary and forced-fallback): recovered schema has no roundtrip data prop AND warnings items == `{"type":"string"}`. **A3 negative test re-run by verifier**: injecting `asset_type: "other"` into the v1.3 fixture makes `_cross_version_check()` FAIL with `backward v1.3→v1.2` + `non-additive` — the extended filter is NOT blind; fixture restored byte-exact after. `PHASE4_SELF_TEST=1` green on ep02 AND on `spec/fixtures/v1.3` (the WR-01 object-mount repro path). `python3 -m pytest tests/ -x -q` → 36 passed |
| 4 | roundtrip 数据缺席时导出照常 + `[roundtrip]` warnings sidecar 记因通道落地——三种因由在 warnings 形状中可表达 | ✓ VERIFIED | Absent → export proceeds (SC#2 data-keys smoke is the same proof). Schema: `generator.warnings.items` widened to `anyOf [string, {code enum(3), detail}]` with code enum exactly `[comfyui_unreachable, vram_insufficient, scorer_model_missing]`; each of the 3 codes validated as a solo structured entry against asset.schema; `code: "banana"` rejected. Producer: module-level `_ROUNDTRIP_WARNING_CODES` + `_valid_warnings_list()` called from `main()` sidecar loader (line 575) with silent-fallback + `[warn] route_cache/warnings.json malformed` semantics preserved — 3 valid forms accepted, 5 invalid rejected. Fixture demonstrates 双形并存: 1 legacy string + 2 structured entries (comfyui_unreachable ConnectError + vram_insufficient 18.4GB < 22GB) |
| 5 | SPEC.md §4 changelog 1.2→1.3 + §5 round-trip 形状文档 + fidelity disclaimer 一次人类审阅通过 | ✓ VERIFIED | SPEC.md header Version `1.3 (active; schema_version: "1.3")` + Status mentions Phase 18 (2026-08-19); §1 heading「14 个 schema 文件」+ authority 表「(14 份)」+ roundtrip.schema.json row; §4 Changelog `2026-08-19 — 1.3 (Phases 18-22)` entry honestly records the TWO non-pure-property deltas (warnings items 加宽 + data.roundtrip object 挂载，对旧数据 additive 但非 property-delta) with single-source citation `export_asset.py:59` — matches actual `grep -n` output (59), stale v1.2 "line 55" avoided; §5 intro v1.3 sentence + `### Round-trip (`1.3`)` section following the 4-block template (Producer/Consumers → 顶层形状 → field table with enums verbatim → 最小片段 → Reference schema); **min-fragment JSON == `spec/fixtures/v1.3/roundtrip.json` by exact `json.loads` equality**; `_esc()` PRESENT-01 obligation + data.roundtrip mount explanation present; §10.5 three-layer disclaimer (①幸存者偏差 ②hard negatives 非垃圾 ③模型判断非 ground truth) with Phase 21 threshold pointer and zero threshold numbers. README v1.3 Update section + layout 14 + `fixtures/v1.3/` line + Phase 18 footer. AF-01 forbidden phrases: 0 in SPEC.md, 0 in README.md. Human review: Kai approved 2026-08-19, recorded in 18-03-SUMMARY.md Task 3 (the plan-designated recording vessel), corroborated by orchestrator context; post-approval SPEC/README edits were the WR-05/WR-06 review-chain accuracy fixes, independently re-reviewed clean (18-REVIEW.md iteration 2) |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `spec/schemas/roundtrip.schema.json` | v1.3 sidecar schema | ✓ VERIFIED | 8816 bytes; check_schema OK; all CONTEXT-locked shapes; contains `prompt_faithful`; wired via validate.py V13 + verify_contract + SPEC Reference line |
| `spec/schemas/asset.schema.json` | Extended manifest | ✓ VERIFIED | Two deltas only vs v1.2 tag; contains `comfyui_unreachable`; data.required untouched |
| `scripts/export_asset.py` | SCHEMA_VERSION 1.3 + conditional mount + widened loader | ✓ VERIFIED | Line 59 single source; `data_block["roundtrip"]` emission + `_valid_warnings_list` both behaviorally exercised |
| `spec/fixtures/v1.3/` (13 files) | Fixture set | ✓ VERIFIED | Exactly 13 files; 11 substrate byte-identical; asset.json edited at exactly the 4 points (`generated_at` unchanged, matches v1.2); roundtrip.json full/degrade 2-shot |
| `spec/validate.py` | 4-tier gate | ✓ VERIFIED | V13_FIXTURE_DIR/MAP/ORDER + validate_v13() wired into exit-code aggregation; 13 `[valid-v13]` lines |
| `scripts/verify_contract.py` | Bidirectional proof | ✓ VERIFIED | `_recover_v12_schema` (def + call), EIGHT_SHAPES += "roundtrip" paired with object unwrap (`isinstance(rel, dict)` at validate_eight_shapes:264 AND run_self_test:1349), v1.3 fixture consistency block, WR-03 producer-side roundtrip integrity gate |
| `spec/SPEC.md` | v1.3 prose layer | ✓ VERIFIED | §1/§4/§5.10/§10.5/header/footer all present and fixture-consistent |
| `spec/README.md` | v1.3 index update | ✓ VERIFIED | v1.3 Update section, layout 14, footer; WR-06 corrected expected-output counts (6/10/12/13 — matches measured run) |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| asset.schema.json#data.roundtrip | roundtrip.schema.json | JSON file ref | ✓ WIRED (fixture `data.roundtrip.path = "roundtrip.json"` resolves; sidecar validates) |
| export_asset.py:build_asset_dict | data.roundtrip mount | `data_block["roundtrip"] = {path, counts}` | ✓ WIRED (smoke: present → `{path, accepted_count:1, rejected_count:1}`) |
| export_asset.py:main() | generator.warnings | `_valid_warnings_list(candidate)` at line 575 | ✓ WIRED (call site + silent fallback verified) |
| fixture asset.json#data.roundtrip | fixture roundtrip.json | path + counts | ✓ WIRED (mount counts 1/1 == sidecar verdict counts) |
| verify_contract pass (f) | `_recover_v12_schema` | function call | ✓ WIRED (grep count ≥2; both recovery paths content-verified) |
| validate.py:validate_v13 | roundtrip.schema.json | load_validator against fixture | ✓ WIRED (`[valid-v13] roundtrip` in output) |
| SPEC §4 Changelog | export_asset.py:59 | grep-verified line citation | ✓ WIRED (cited 59 == actual 59) |
| SPEC Round-trip section | roundtrip.schema.json | Reference schema footer | ✓ WIRED |
| SPEC 最小片段 | spec/fixtures/v1.3/roundtrip.json | excerpt | ✓ WIRED (exact JSON equality) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 4-tier shape gate | `python3 spec/validate.py` | exit 0; all tiers failures=0; 13 `[valid-v13]` | ✓ PASS |
| Strict smoke | `python3 spec/validate.py --strict-smoke` | exit 0 | ✓ PASS |
| Bidirectional proof (documented ep02 route) | `PHASE4_ASSET_DIR=<ep02> python3 scripts/verify_contract.py --mode=producer` | exit 0; exact proof line | ✓ PASS |
| Fail-loud self-test (incl. WR-01 object-mount repro) | `PHASE4_SELF_TEST=1 PHASE4_ASSET_DIR=spec/fixtures/v1.3 …` | exit 0; corrupt-asset rejection PASS | ✓ PASS |
| Backward-filter negative (A3) | inject `asset_type:"other"` → `_cross_version_check()` | FAIL as required; byte-exact restore | ✓ PASS |
| Byte-identical-absent smoke | synthetic work_dirs → `build_asset_dict` | 5-key / 9-key exact; malformed OMIT ×5 shapes | ✓ PASS |
| Test regression | `python3 -m pytest tests/ -x -q` | 36 passed | ✓ PASS |
| Producer mode, default ep01 dir | `python3 scripts/verify_contract.py --mode=producer` | exit 1 — registry drift (see below) | ✓ PRE-EXISTING (not a phase-18 regression) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RT-01 | 18-01, 18-02 | roundtrip.schema.json sidecar; additive optional; byte-identical-absent 红线 | ✓ SATISFIED | SC#1 + SC#2 evidence: schema validates fixture full-field; substrate diff-clean + data-keys smoke |
| RT-02 | 18-01, 18-02 | SCHEMA_VERSION 1.3 单源; validate gate; bidirectional proof | ✓ SATISFIED | SC#2 + SC#3 evidence |
| RT-03 | 18-03 | SPEC §4/§5 changelog + 形状文档 + fidelity disclaimer + 一次人类审阅 | ✓ SATISFIED | SC#5 evidence |
| RT-04 | 18-01, 18-02 | graceful-degrade + 三因由 warnings 记因 | ✓ SATISFIED | SC#4 evidence |

Orphaned requirements: none — REQUIREMENTS.md maps RT-01..04 to Phase 18 (all complete) and RT-05 to Phase 22 (correctly out of scope). No premature roundtrip producer/consumer code exists (`grep roundtrip html/*.py scripts/canvas_import.py` → 0).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| spec/schemas/roundtrip.schema.json | 39 | `shot_XXX.mp4` | ℹ️ Info | Filename-template glob in canonical-layout description (wording supplied by PLAN/RESEARCH skeleton), not a debt marker — fixture uses concrete `shot_001.mp4` |
| spec/SPEC.md | 570 | `shot_XXX.mp4` | ℹ️ Info | Same naming-convention reference in the field table |
| scripts/verify_contract.py | 1655, 1714 | e2e "placeholder" | ℹ️ Info | Pre-existing since Phase 4 (commit 459b9b2, present in v1.2 tag); outside phase-18 scope |

No TBD/FIXME/XXX debt markers, no stub implementations, no hardcoded-empty data paths in any phase-18 deliverable. All 15 documented commits (eae251a, ee1e5eb, ee907bd, a896a79, 5e05fd8, 301e7ae, ead9aaf, 3f9a792, 8cf3454, b08d9d5, 2230076, f0a7cfd, b9fd1c7, ad7305c, 87ced5c, 5810314, 6181265) exist in history.

### Human Verification Required

None outstanding. The phase's single human checkpoint (SC#5 SPEC prose review) was executed during the phase: Kai approved 2026-08-19 with no wording issues, recorded in 18-03-SUMMARY.md Task 3 per the plan's designated recording mechanism. The two post-approval edits (WR-05 SPEC §3 type cell, WR-06 README validate counts) were accuracy corrections from the independent code-review chain and were behaviorally re-verified by the iteration-2 re-review — no re-approval is demanded for them.

### Gaps Summary

No gaps. All five success criteria verified against the codebase with behavioral evidence re-run in the verifier's own process (not SUMMARY-narrated): schema validation, data-keys smoke, substrate diff, single-source grep, 4-tier gate, bidirectional proof on both recovery paths, the A3 filter-blindness negative test, self-test, and pytest.

**Non-blocking carry-over (pre-existing, verified NOT phase-18 scope):** default-dir producer mode (`--mode=producer` on ep01) fails on `registry.draft.json` schema drift. Verifier independently confirmed this is pre-existing: the file is gitignored untracked runtime output (mtime 2026-07-30, before Phase 18), `registry.schema.json` is unchanged since Phase 5 (commit 3e55c02), and the drifted keys (`method`/`total_clusters`/`total_crops`) come from a post-v1.2 experiment. All Phase 18 proof obligations are green via the harness's documented `PHASE4_ASSET_DIR` override (ep02). Tracked in deferred-items.md #2 awaiting an orchestrator decision (widen registry.schema.json vs regenerate the draft) — flagged here for visibility; it does not affect any Phase 18 success criterion.

**Judgment notes:**
- "shot_XXX.mp4" occurrences are documentation naming conventions per plan-supplied wording, not unreferenced debt markers — classified Info, not blockers.
- SC#5's human-approval element is evidenced by the recorded approval in the plan-designated artifact (18-03-SUMMARY) plus orchestrator corroboration; all machine-checkable substance of SC#5 was verified directly.
- The two Info-level review carry-overs (IN-01 SPEC §3 table lacks data.* mount rows; IN-02 prefix-broad backward exemption under generator/warnings, compensated by forward pass (e)) are documented open items from the review chain — cosmetic/defense-in-depth, no impact on the contract's correctness proofs.

---

_Verified: 2026-08-19T23:15:00Z_
_Verifier: Claude (gsd-verifier)_
