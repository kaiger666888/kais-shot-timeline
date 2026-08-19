---
phase: 19-qwen-eye-v2
plan: "02"
subsystem: vision-seq-spike
tags: [qwen-eye, spike, blind-review, gpu-burn, sandbox]
requires:
  - "19-01: analysis/vision_seq_facets.py 模块（CLI + 双信封 cache + 三策略归约）"
provides:
  - "ep01 六镜三策略 GPU 实证产物 + 甲/乙/丙盲评材料（results/ + DRAFT 报告）"
  - "ear on/off 双跑 diff 证据（SC3）"
  - "live 不覆盖 sha256 负测试 + cache 秒级重跑实测（SC1/SC4 半边）"
  - "待 Task 3：Kai 盲评锁定 MERGE_STRATEGY_DEFAULT + 报告定稿"
affects:
  - "analysis/vision_seq_facets.py（Task 3 裁决后或改 MERGE_STRATEGY_DEFAULT）"
  - "19-03 wiring（复用 sandbox route_cache / --reset 语义）"
tech-stack:
  added: []
  patterns:
    - "sandbox 副本目录双跑（facet 置空 → 只填空缺语义可实证；live 零写入安全门 + sha256 负测试）"
    - "盲评防泄漏：固定 seed 甲/乙/丙映射只落 strategy_mapping.txt + 导出后禁词 grep 自检"
key-files:
  created:
    - spike/vision_seq/README.md
    - spike/vision_seq/build_sandbox.py
    - spike/vision_seq/run_spike.py
    - .planning/research/vision-seq-spike-report.md
    - spike/vision_seq/results/{run.log,shot_*.md,ear_diff.md,blind_review.md,strategy_mapping.txt,metrics.json}
    - spike/vision_seq/{sandbox,sandbox_ear}/route_cache/vision_seq/shot_*.json
  modified:
    - spike/vision_seq/{sandbox,sandbox_ear}/prompts.json（facets 被 v2 产物填充）
decisions:
  - "spike 实测 147 calls ≈15.5 min（含引擎拉起 ~4 min；单 call ≈4-5s）——A1 假设 1-3h 高估约一个量级"
  - "盲评主判据 + 客观指标仅辅助（反循环论证，Pitfall 4）；甲/乙/丙映射 seed=20260819 落 strategy_mapping.txt"
metrics:
  duration: "~1h20m（Task 1 脚手架 ~60m；Task 2 双跑+落档 22m，其中 GPU burn 15.5m）"
  completed: 2026-08-19T18:17Z（checkpoint 暂停，非完结）
---

# Phase 19 Plan 02: ep01 Vision-Seq Spike（三策略盲评 + ear 双跑）Summary

**One-liner:** ep01 六镜 sandbox GPU 双跑 147 calls 实证三策略（temporal/llm/longest）同镜产物 + ear on/off diff + 客观指标，盲评材料齐备落 DRAFT 报告，待 Kai 盲评锁定合并策略（Task 3 blocking checkpoint）。

**Status: CHECKPOINT PAUSED** — Task 1/2 完成并提交；Task 3（blocking human-verify）待 Kai 裁决「锁定 <甲/乙/丙 或 策略名>」。报告仍为 DRAFT（Task 3 后去 DRAFT 定稿 + 回写映射 + 可能改 `MERGE_STRATEGY_DEFAULT`）。

## Tasks

| # | Task | Commit | 结果 |
|---|------|--------|------|
| 1 | spike 脚手架（THROWAWAY README + sandbox 构建 + 四步双跑驱动） | 9a6624c | sandbox/sandbox_ear 双目录（6/3 镜置空）+ demo audio_semantic 过 schema 校验 + 离线幂等构建 + 断点续跑驱动 |
| 2 | GPU 双跑 + 三策略产物 + 指标 + 报告 DRAFT | af23da4 | 147 calls ≈15.5 min（ear_off 90 + ear_on 45 + merged_B 12），0 warnings；results/ 全套产物；报告 402 行 DRAFT；SC1 sha256 相等 + SC4 秒级重跑在案 |
| 3 | Kai 盲评 checkpoint → 锁定策略 → 定稿 | —（待人工） | **blocking，未自批**；裁决后：报告 FINAL + 回写映射 + 若 ≠temporal 改 MERGE_STRATEGY_DEFAULT + pytest 复跑 + commit |

## 实测记录（回填 Pitfall 6 / A1 假设）

- 调用量：147（预算上限 ~150，T-19-08 mitigate 生效）= step a 90（6 镜×15）+ step b 45（3 镜×15）+ step c 12（6 镜×2 ask_text）+ step d 0（纯归约）。
- 耗时：tmux 后台 01:55:48–~02:11 (+0800) ≈15.5 min，含引擎 ensure_ready 拉起+模型加载 ~4 min；单 call 均值 ≈4-5s（[ASSUMED] A1 原 估 10-60s/call、总 1-3h——高估约一个量级）。
- ep01 全量外推（参考，非本 phase SC）：93 镜 ≈1400 calls ≈2-2.5h——overnight 批量级不变。
- SC1 负测试：live ep01 prompts.json sha256 跑前=跑后 `7cc4a4841e7f53975e5cd28e6399f66a21fb996f32414f80cb55efa32afaced5`；`git status output/` 空。
- SC4：facets 已填短路 0.94s；置空+cache 全命中 temporal 重填 0.98s / llm 重填（merged_B cache）0.97s——均零引擎调用。
- SC3 ear diff 可见：#1「正闭眼倒数等待对方逗它开心」、#88「挂着泪珠/屏息聆听」、#91「焦急地呼喊爸爸」（ear_off 版则靠读内嵌字幕）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_ensure_symlink` 安全门破坏幂等**
- **Found during:** Task 1（构建脚本自测）
- **Issue:** 对已存在 symlink 本身 `resolve()` 会跟随到 live output/ 目标，触发「拒绝写 spike 外路径」误退出，二次构建必挂。
- **Fix:** 改为 `link.parent.resolve() / link.name` 判定（只 resolve 父目录）；幂等重跑验证通过。
- **Files:** spike/vision_seq/build_sandbox.py；**Commit:** 9a6624c（随 Task 1 一并提交）

**2. [Rule 1 - Bug] build_sandbox main() 残留无意义 self-check 循环**
- **Found during:** Task 1（自查）
- **Issue:** 作者期残留的 `targets[name] if False else ...` 表达式与重复 `_self_check` 调用。
- **Fix:** 删除（build_target 全量构建路径内已自带 self-check）。
- **Files:** spike/vision_seq/build_sandbox.py；**Commit:** 9a6624c

**3. [Rule 3 - Blocking] Plan Task 2 verify 命令字面量自身有 bug**
- **Found during:** Task 2 verify
- **Issue:** `test -f ...shot_00{1,88,91}.json` 经 bash brace 展开为 `shot_001/shot_0088/shot_0091`——后两者不存在（实际文件名 3 位零填充 `shot_088.json`/`shot_091.json`），`test` 报「参数太多」，verify 永假。
- **Fix:** 按语义等价改写为三个显式 `test -f`（shot_001/shot_088/shot_091）执行，全绿；ear 三镜在位早经 run_spike.py step b 断言（同一集合语义）。
- **Files:** 无代码变更（计划文档缺陷）；**Commit:** N/A

另记录（非偏差，假设修正）：GPU 双跑实际 ~15.5 min，远低于计划 [ASSUMED] 1-3h——预算按上限控的（≤150 calls 封顶）未变。

## Auth Gates

None.

## Known Stubs

None.（demo 级 audio_semantic.json 为计划明示的设计性 demo 输入，只在 sandbox、报告头部已声明，不流向任何 UI/生产路径。）

## Threat Flags

None.（T-19-06/07/08 mitigate 均已落实：安全门 + sha256 负测试；映射落档 + 禁词自检；147/150 调用封顶。无计划外新攻击面。）

## Checkpoint（Task 3 — blocking）

- **材料：** `.planning/research/vision-seq-spike-report.md` §Recommendations 盲评表（甲/乙/丙 + v1 参照；独立匿名文件 `spike/vision_seq/results/blind_review.md`）；§ear on/off diff；§Reproducibility。
- **勿看（裁决前）：** `spike/vision_seq/results/strategy_mapping.txt`。
- **Resume-signal:** 「锁定 <甲/乙/丙 或 策略名>」或描述需补跑/修正的问题。
- **续跑代理待办：** 报告去 DRAFT 改 FINAL + 回写映射与理由；若锁定 ≠ temporal 改 `analysis/vision_seq_facets.py` `MERGE_STRATEGY_DEFAULT`（llm 需确认 merged_B 全量在位）；pytest 复跑（有断言默认值则同步改）；commit；然后 state.advance-plan / roadmap / 本 SUMMARY 补定稿记录。VISION-01/02 保持未勾选（与 19-01 共享，19-03 wiring 后收口——mirror 18-01 先例）。

## Self-Check: PASSED

- 文件在位：.planning/research/vision-seq-spike-report.md（402 行 ≥120）、spike/vision_seq/results/ 7 产物、sandbox cache 6 镜、sandbox_ear cache 3 镜。
- 提交在位：9a6624c（Task 1）、af23da4（Task 2）。
- Task 2 自动 verify（修正版）全绿 + `python3 -m pytest tests/ -q` 58 passed。
- 盲评表禁词 grep（报告盲表节 + blind_review.md）零命中。
