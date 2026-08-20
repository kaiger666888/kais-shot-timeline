---
phase: 18-contract-v1-3
plan: 02
subsystem: contract
tags: [fixture, validation, bidirectional-proof, cross-version, backward-filter, eight-shapes]
requires:
  - "18-01 — roundtrip.schema.json + asset.schema.json v1.3 deltas + export_asset.py 1.3 (the contract layer this plan proves)"
provides:
  - "spec/fixtures/v1.3/ — 13-file fixture set (11 byte-copied substrate + edited asset.json + new roundtrip.json)"
  - "spec/validate.py V13 tier — 4-tier shape gate (minimal 6 / v1.1 10 / v1.2 12 / v1.3 13), exit-code aggregated"
  - "scripts/verify_contract.py — v1.0↔v1.1↔v1.2↔v1.3 bidirectional proof + _recover_v12_schema (git-tag primary + dual strip fallback) + v1.3 fixture consistency + EIGHT_SHAPES roundtrip with object 特判"
affects:
  - "18-03 (SPEC docs) — cites the fixture/gate/proof evidence delivered here"
  - "Phase 20 (h3 regen client) — writes roundtrip.json + structured warnings; EIGHT_SHAPES/特判 pairing means producer mounts will not false-fail"
  - "Phase 21 (scorer) — fills scores/verdict against the proven schema"
  - "Phase 22 (gallery/dataset) — consumes data.roundtrip stats + sidecar"
tech-stack:
  added: []
  patterns:
    - "v1.x first non-property-delta backward-filter exemption (path-scoped type/anyOf exemption for items widening)"
    - "first recover-* fallback that RESTORES a subschema (warnings items) rather than only popping additive keys"
    - "object-valued data.* mount handling in shape harnesses (unwrap .path before string check)"
key-files:
  created:
    - spec/fixtures/v1.3/ (13 files; roundtrip.json + asset.json are the authored/edited ones)
  modified:
    - spec/validate.py
    - scripts/verify_contract.py
decisions:
  - "backward filter exempts EXACTLY two documented deltas (additionalProperties anywhere; type/anyOf only when absolute_path[:2]==(generator,warnings)) — injected asset_type const drift still FAILs (A3 negative test proves filter not blind)"
  - "ep01 producer-mode failure is pre-existing runtime-data drift (registry.draft.json method/total_clusters/total_crops from a 2026-07-30 experiment, untracked) — NOT fixed (scope boundary), logged deferred-items #2; 18-02 verification routed via the documented PHASE4_ASSET_DIR=ep02 override"
metrics:
  duration: "~8 min (13:39:17Z → 13:47:36Z)"
  completed: 2026-08-19
---

# Phase 18 Plan 02: Contract v1.3 Fixtures + Gates + Bidirectional Proof Summary

**One-liner:** v1.3 契约的实证层落地：13 文件 fixture（11 个 v1.2 substrate byte-copy + asset.json 四点编辑 + roundtrip.json 全/degrade 两态 sidecar）、validate.py 第四阶 4-tier gate、verify_contract.py v1.2↔v1.3 双向证明 —— 含两个 Phase 11 没有的新机制：backward 过滤规则扩展（首个 items 类型加宽的 type/anyOf 错误按 path 精确豁免，注入 const 漂移仍 FAIL）与 validate_eight_shapes 的首个 object 值挂载特判（与 EIGHT_SHAPES 追加同 plan 成对）。

## What Was Built

### Task 1 — spec/fixtures/v1.3/ 13-file fixture (commit a896a79)

- **11 substrate files** byte-copied from v1.2 (`cp` + `diff` clean): shots / audio_analysis / transcript / frames / prompts / characters / props / registry.draft / registry.edits / audio_semantic / speakers — byte-identical-absent 红线的 substrate 半边证明（RT-01）。
- **asset.json edited at exactly 4 points** (verified: `generated_at` 与其余字段不动): `schema_version` "1.3"; `generator.version` "0.3.0-spec-fixture-v1.3"; `warnings` 双形并存 = 1 条 legacy string（保留 "preflight route unreachable…ConnectError…"，弃第二条 string）+ 2 条结构化（`{code: comfyui_unreachable, detail: …ConnectError…(:8188)}` + `{code: vram_insufficient, detail: …18.4GB free < 22GB minimum (REGEN-03)}`）；`data.roundtrip` = `{path: "roundtrip.json", accepted_count: 1, rejected_count: 1}`（挂在 speakers 之后）—— 统计与 sidecar verdict 计数一致（18-01 挂载语义的 fixture 级体现）。
- **roundtrip.json**（新形状）: shot 1 = full/auto-accept（regen 全 8 字段含 duration_sec 4.8 + width 832 + height 480；scores 双信号 midframe_sim{0.87, clip-vit-l14-336} + judge{prompt_faithful, 0.8, 中文 reason}；verdict{accepted, auto} 无 decided_at）；shot 2 = degrade+human-reject（regen 5-tuple + 仅 duration_sec —— optional 字段缺席示例；scores 仅 midframe_sim{0.42}；verdict{rejected, human, decided_at: "2026-08-19T00:00:00Z"}）。shot_id ∈ {1,2}（substrate 硬约束，T-18-10）。
- **全字段覆盖走 direct-validator 通道**（Open Q1 adopted 方案，一 shot 一条目结果集语义）: status.failed 条目、三个 attribution enum 值逐一、verdict 缺席、duration_sec 缺席、三个 warning code 作为 solo 结构化条目 —— 全部对 18-01 schema 实例校验绿。

### Task 2 — spec/validate.py V13 第四阶 (commit 5e05fd8)

- `V13_FIXTURE_DIR` + `V13_FIXTURE_MAP`（12 个 v1.2 entries verbatim + `"roundtrip": "roundtrip.json"`）+ `V13_ORDER = V12_ORDER + ["roundtrip"]`（13 entries，introspection 断言 `set(V12_ORDER) < set(V13_ORDER)`）。
- `validate_v13()` line-for-line mirror of `validate_v12()`（docstring 记 11 byte-copied + asset 编辑 + roundtrip 新增；`[valid-v13]`/`[FAIL-v13]` 前缀；复用 load_validator + _format_errors）。
- `main()`：`[validate] v1.3 fixture = …` 行 + `v13_failures = validate_v13()`；聚合 `total_strict_failures = minimal + v11 + v12 + v13`；汇总行加 `v1.3 failures=N`。老三阶 + smoke/strict-smoke flag 零改动。

### Task 3 — scripts/verify_contract.py 五处 surgical edits (commit 301e7ae)

1. **EIGHT_SHAPES += `"roundtrip"`**（现 12 元素），Phase 18 注释明确 gated on data.roundtrip existence + 指向 object 特判；头部计数注释同步诚实化（13 shapes / 12 elements）。
2. **validate_eight_shapes object 特判**：`rel` 为 dict 时先 `rel.get("path")` 解包再走 string 检查；解包后缺失/非 string 的 failure 命名 `data.{shape}.path is not a string`。与 EIGHT_SHAPES 追加同 plan 成对（Pitfall 2 / T-18-09 —— Phase 20 producer 挂载不误报）。
3. **`_recover_v12_schema`**：primary `git show v1.2:spec/schemas/<shape>.schema.json`（subprocess timeout 5，mirror _recover_v11_schema）；strip fallback 除 pop `data.properties.roundtrip` 外**还原** `generator.properties.warnings.items = {"type": "string"}`（v1.x 首个需要 restore 而非仅 pop 的 recover —— Wrinkle 1 连锁 3 / T-18-08）。两条路径都实测：git-show primary 内容断言（无 roundtrip prop + items=={"type":"string"}）+ monkeypatch git 不可用强走 fallback（同样双还原 + 接受 v1.2 fixture 0 non-addprop errors）。
4. **pass (e) FORWARD v1.2→v1.3**（v1.2 fixture asset.json × 当前 schema → 0 errors；string warnings 对加宽 items 天然合法）+ **pass (f) BACKWARD v1.3→v1.2**（`_recover_v12_schema` + 扩展过滤）：豁免恰为两类 —— `e.validator == "additionalProperties"`（data.roundtrip 新键）OR（`e.validator in ("type","anyOf")` 且 `tuple(e.absolute_path)[:2] == ("generator","warnings")`，即文档化 items 加宽）；其余任何错误记 `backward v1.3→v1.2 asset: N non-additive error(s) (shared fields drifted)`。汇总话术诚实化：`v1.0↔v1.1↔v1.2↔v1.3 … excluding documented v1.3 deltas: data.roundtrip + warnings items widening`。
5. **`_fixture_consistency_check` v1.3 block**（gated on v1.3 dir is_dir + roundtrip.json is_file）：`roundtrip.shots[].shot_id` ⊆ v1.3 目录自己的 shots.json ids（WR-01 lesson）；成功话术扩为 `v1.1 + v1.2 + v1.3 fixture set cross-file IDs consistent (0 dangling)`。

**A3 负测试（最高风险项）**：向 v1.3 fixture asset.json 注入 `asset_type: "other"`（const violation）→ `_cross_version_check()` 必须 FAIL 且 detail 含 `backward v1.3→v1.2` + `non-additive`；finally 恢复后 `git diff` 证明 byte-exact 还原。过滤不盲。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] deque 不支持切片 —— 过滤谓词抛 TypeError**
- **Found during:** Task 3 首次跑 producer mode（pass (f) 处理 warnings items 错误时）
- **Issue:** plan 伪代码写 `tuple(e.absolute_path[:2])`，但 jsonschema 的 `e.absolute_path` 是 `deque` —— `deque[:2]` 直接抛 `TypeError: sequence index must be integer, not 'slice'`，整个 `_cross_version_check` 崩成 traceback。
- **Fix:** 改为 `tuple(e.absolute_path)[:2]`（先 tuple 再切片），附中文注释说明。语义与 plan 意图完全一致。
- **Files modified:** scripts/verify_contract.py
- **Commit:** 301e7ae

### Deliberate Non-Actions

**2. [Scope Boundary] ep01 默认目录的 pre-existing producer-mode FAIL 不修**
- **Found during:** Task 3 首次跑 `--mode=producer`（默认 `PHASE4_ASSET_DIR` = ep01）
- **Issue:** `registry at /<root>: Additional properties are not allowed ('method', 'total_clusters', 'total_crops')`。根因：ep01 `output/…/registry.draft.json`（gitignored 运行时产物，mtime 2026-07-30，post-v1.2 `local_reid_glm46v_hist` 实验所写）带 schema 外根键，且用 `method` 而非 schema 期望的 `model`。已验证 pre-existing：pre-18-02 HEAD 版 verify_contract.py 同样失败；ep02/ep03 的 registry draft schema-clean。
- **Decision:** 不修（untracked 运行时数据 + schema-vs-experiment 漂移 deserving 自己的决策：widen registry.schema.json vs 重新生成合规 draft —— Rule 4 领域）。验证改走 harness 自带文档化的 `PHASE4_ASSET_DIR` 覆盖（ep02，18-RESEARCH Environment Availability 表的本意 fallback）；发现记入 `deferred-items.md` #2 交 orchestrator 裁决。Phase 18 自身的全部检查（cross-version / fixture consistency / EIGHT_SHAPES / self-test）在两个目录都绿。
- **Files modified:** .planning/phases/18-contract-v1-3/deferred-items.md（仅记录）
- **Commit:** 301e7ae

## Auth Gates

None — no auth-required operations in this plan.

## Known Stubs

None — no stub/placeholder code was emitted. All three deliverables (fixture set, gate, proof harness) are fully functional.

## Verification Evidence

- Task 1 verify: `[fixture-ok] 13 files + 11 diff-clean + schemas green + counts consistent + full-field coverage (status.failed / 3 attributions / 3 warning codes / optional absences)`。
- Task 1 acceptance: `ls | wc -l` = 13；`diff` 11 文件 clean；`1.3 {'path': 'roundtrip.json', 'accepted_count': 1, 'rejected_count': 1}`；warnings `1 2`；`generated_at` 不变。
- Task 2 verify: 13 条 `[valid-v13]`（含 asset + roundtrip）、零 `[FAIL-v13]`、汇总 `minimal failures=0, v1.1 failures=0, v1.2 failures=0, v1.3 failures=0, smoke failures=0`、exit 0；`grep -c 'V13_…\|validate_v13'` = 8（≥5）；ast.parse OK；V13_ORDER introspection OK。
- Task 3 verify（`PHASE4_ASSET_DIR`=ep02）: producer mode exit 0，输出含 `v1.0↔v1.1↔v1.2↔v1.3 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors, excluding documented v1.3 deltas: data.roundtrip + warnings items widening)` + `v1.1 + v1.2 + v1.3 fixture set cross-file IDs consistent (0 dangling)`。
- `_recover_v12_schema('asset')`: git-show primary 无 roundtrip data prop 且 warnings items == `{'type': 'string'}`；**strip fallback 实跑验证**（monkeypatch git 不可用）同样双还原、且 recovered schema 接受 v1.2 fixture（0 non-addprop errors）—— 比 plan 要求的 source-grep 更强。
- A3 负测试: `[negative] injected asset_type drift correctly FAILS backward v1.3→v1.2 (filter not blind)`；恢复后 `git diff --stat` 空（byte-exact）。
- `PHASE4_SELF_TEST=1 … --mode=producer` exit 0（fail-loud self-test intact）；默认 ep01 目录的失败仅剩 pre-existing registry drift（与 pre-edit HEAD 逐字一致 —— 本 plan 零新增失败，EIGHT_SHAPES roundtrip 在 ep01 dormant）。
- Wave regression: `python3 -m pytest tests/ -x -q` → 36 passed。
- `grep -c '_recover_v12_schema' scripts/verify_contract.py` = 2（定义 + 调用点）。

## Self-Check: PASSED

- Files: spec/fixtures/v1.3/roundtrip.json FOUND · spec/fixtures/v1.3/asset.json FOUND · spec/validate.py FOUND (modified) · scripts/verify_contract.py FOUND (modified) · 13-file dir count confirmed
- Commits: a896a79 FOUND · 5e05fd8 FOUND · 301e7ae FOUND
- All task acceptance criteria re-run green at commit time (consolidated pass 13:47Z).
