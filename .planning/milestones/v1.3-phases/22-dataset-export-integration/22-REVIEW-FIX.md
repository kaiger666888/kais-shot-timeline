---
phase: 22-dataset-export-integration
fixed_at: 2026-08-20T09:24:00Z
review_path: .planning/phases/22-dataset-export-integration/22-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 22: Code Review Fix Report

**Fixed at:** 2026-08-20T09:24:00Z
**Source review:** .planning/phases/22-dataset-export-integration/22-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (fix_scope = Critical + Warning; IN-01..IN-08 not in scope)
- Fixed: 5
- Skipped: 0

**Gates:**
- `python3 -m pytest tests/ -q` — **234 passed**（223 基线零回归 + 11 新增回归锚：CR-01 ×1 / WR-01 ×2 / WR-02 ×2 / WR-03 ×6 / WR-04 ×1）
- `python3 spec/validate.py` — **exit 0**（minimal/v1.1/v1.2/v1.3 全 0 failures；roundtrip.schema.json 未动——WR-03 决策 τ 走 stamp 文件，two-tier authority lock 保持）
- ep01 正本 roundtrip_review.html 已用修复后生成器重生成复验：19/19 queue 项 topline/sim bar 完好 + 19/19 prompt 折叠尾注含 engine_version；roundtrip.json sha `63543baf…` 前后不变（runtime sidecar 零触碰）

## Fixed Issues

### CR-01: Queue sidebar wiped on page load — `textContent` set on the `<a>` instead of the `.queue-check` placeholder span

**Files modified:** `html/gen_roundtrip_review.py`, `tests/test_roundtrip_review.py`
**Commit:** 6cc0cde
**Applied fix:** `applyVisualState()` 改经 `q.querySelector('.queue-check')` 只更新专用占位 span（anchor 的 topline/微 sim bar 子节点不动）；`_queue_item_html` docstring 明确占位 span 是 anchor 首子节点。新增回归锚 `test_queue_checkmark_targets_dedicated_span`：源码断言生成 JS 不写 `q.textContent`、check span 选择器/填充形态在场、server 渲染端每 queue item 恰一个空占位 span（计数锁）。ep01 正本重生成验证 19/19 queue 项内容完好、sidecar sha 不变。修后状态：**fixed**（DOM 行为修复——源码级断言 + 真实数据重生成双重验证，无需人工复核标记）。

### WR-01: `accepted.txt` and `manifest["shots"]` list accepted shots whose directories were never created

**Files modified:** `analysis/roundtrip/export_dataset.py`, `tests/test_export_dataset.py`
**Commit:** d4d8b11
**Applied fix:** 导出循环内建 `exported_names`（sid→shot_NNN 本轮成功集）与 `skipped_ids`；`accepted.txt` 与 `manifest["shots"]` 均从实际导出集派生，`accepted_count == len(shots) == len(accepted.txt 行数)`；降级跳过镜单列 `manifest["exported_skipped"]`（可审计）绝不进索引。新增两回归锚（prompts 缺条目路径 + 帧降级路径的索引三一致断言）。

### WR-02: Degraded rerun deletes previously-good dataset shot directories

**Files modified:** `analysis/roundtrip/export_dataset.py`, `tests/test_export_dataset.py`
**Commit:** c7bcd6c
**Applied fix:** 最小改（合同指定方案）：`created = not os.path.isdir(shot_dir)` 区分本轮自建/上轮遗存——降级失败路径只 rmtree 本轮自建半成品；上轮完好导出目录保留 + warning（不进本轮索引，WR-01 口径），成功路径照常覆盖重写。新增两回归锚：降级重跑后上轮 first/last_frame.jpg + prompt.json 字节不变、保留决策 warning 在场；对照面（本轮自建半成品仍清）。

### WR-03: τ change on a cache-hit rerun displays a non-governing τ as governing (panel pill/tick/queue-sort + dataset manifest)

**Files modified:** `analysis/roundtrip/judge.py`, `analysis/roundtrip/export_dataset.py`, `run_pipeline.py`, `tests/test_judge.py`, `tests/test_export_dataset.py`, `tests/test_pipeline_roundtrip_wiring.py`
**Commit:** daf8365
**Applied fix:** 合同指定最小正确解三件套：(1) `judge.apply_verdict` 首次实际 apply 把决策 τ 写 `roundtrip.json.verdict-tau` stamp（mirror `.video-stamp` 纯文本先例；写后不覆盖——冻结语义下首次 τ 即首批 verdict 决策阈值；换 τ 重跑打不一致 warning）；(2) `step_roundtrip` 外层 cache stamp 身份追加 `|tau=<τ>` 后缀（`current_cache_id` 比对+写盘）——换 τ 强制 miss 重生成 HTML/manifest；(3) `export_dataset` manifest 的 `tau_sim` 拆成 `verdict_tau`（stamp 留档值；缺席/坏值 → null + warning）与 `export_tau`（本轮 CLI τ）双记。roundtrip.schema.json 未动（阈值不进 schema 的 two-tier authority lock 保持，spec/validate 0 failures）。新增六回归锚（judge stamp 写入/不覆盖 ×1 + no-entries 不写 ×1 + export 双记不一致/缺席/坏 stamp ×3 + wiring cache-key τ 后缀源码锁 ×1）。状态：**fixed: requires human verification**（cache-key 语义变更——旧 stamp 一次性 miss 后自愈为新格式，属预期行为但建议首跑确认）。

### WR-04: UI-SPEC data-mapping deviation — `regen.engine_version` / `engine_name` never rendered; `_esc` docstring overclaims coverage

**Files modified:** `html/gen_roundtrip_review.py`, `tests/test_roundtrip_review.py`
**Commit:** bc51e50
**Applied fix:** prompt 折叠 summary 尾注改「prompt v{prompt_version} · {engine_version}」（均过 `_esc`；半边缺席退化单段/无尾注）——UI-SPEC 映射行补齐缺半边；模块 docstring 第 1 层 XSS 清单修正为实际到达 HTML 的字段清单（engine_name 不渲染——映射表未含，进 dataset prompt.json）。新增回归锚 `test_prompt_fold_summary_includes_engine_version`（5 regen 镜尾注计数 + 降级卡无尾注路径）。ep01 正本重生成复验 19/19 尾注在场。

## Skipped Issues

None — all 5 in-scope findings fixed.

## Notes

- Runtime sidecar 数据 / ROADMAP / STATE 未触碰（ep01 roundtrip.json sha 前后一致 `63543baf9da845de930c02f13a1d3a5eb1a6b91a04ee172d9625f7482436dd73`）；ep01 `roundtrip_review.html` 为派生产物，按合同用修复后生成器重生成（queue 完好性验证载体）。
- 22-REVIEW.md 已按 finding 补 Outcome 行（commit f75dce9）；Info findings（IN-01..IN-08）不在本轮 scope，未动。
- WR-03 混合批次边界（首批 τ1 冻结后、新镜按 τ2 补判）stamp 取首次 τ 并打不一致 warning——单值留档的固有近似，warning 保证可审计。

---

_Fixed: 2026-08-20T09:24:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
