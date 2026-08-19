---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Round-trip Validation（逆推→复现→比对闭环数据集）
status: executing
stopped_at: Completed 19-02-PLAN.md (Phase 19 2/3 — Kai 盲评锁定甲=temporal，spike report FINAL)
last_updated: "2026-08-19T18:25:23.209Z"
last_activity: 2026-08-20
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 6
  completed_plans: 5
  percent: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-19)

**Core value:** 把成片解构成可导航、多轨道、带语义的分镜资产（分镜 + 分离音轨 + 对白 + 镜头语言/动作/场景 prompt + 跨镜角色/道具注册表 + 三模态音频语义），且形态可移植——能作为无限画布等下游消费者的「最终资产集合形态」被直接消费。
**Current focus:** Phase 19 — qwen-eye v2 看片段

## Current Position

Phase: 19 (qwen-eye v2 看片段) — EXECUTING
Plan: 3 of 3
Status: Ready to execute
Last activity: 2026-08-20

Progress: [████████░░] 83%

## Performance Metrics

**Velocity (cumulative historical):**

- Total plans completed: 68 (v1.0: 7, v1.1: 16, v1.2: 20 — all archived)
- v1.3 plans completed: 3

**By Phase (v1.3 — populates as plans complete):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 18. Contract v1.3 | 2/3 | 13m | 7m |
| 19. qwen-eye v2 看片段 | 2/3 | ~1h48m | ~54m |
| 20. h3 复现客户端 | 0/TBD | - | - |
| 21. Scorer + 阈值校准 | 0/TBD | - | - |
| 22. Dataset Export + Integration | 0/TBD | - | - |
| 18 | 3 | - | - |

**Plan metrics (per executed plan):**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 18 P01 | 5m | 3 tasks | 3 files |
| Phase 18 P02 | 8m | 3 tasks | 15 files |
| Phase 18 P03 | ~30m | 3 tasks | 2 files |
| Phase 19 P01 | 13m | 3 tasks | 5 files |
| Phase 19 P02 | ~1h35m | 3 tasks | 12 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Locked decisions entering v1.3 (proposal + /gsd:new-milestone, 2026-08-19):

1. v1.3 = Round-trip Validation；MUS-04 乐器识别 / DIA-06 继续 defer（不捎带）
2. qwen-eye v2 务实版：每镜 ≤8 帧逐帧 `observe_single`（llama.cpp 单图 bug 硬约束）；vLLM + Qwen3-VL-8B 视频原生留升级位（VISION-03），本 milestone 不动
3. ear = 复用 v1.2 `audio_semantic` 融进视觉 prompt（不新引音频理解引擎）
4. 打分只看中段帧 25%-75% 时窗；verdict 必须归因；rejected 保留
5. h3 客户端 = kst 直连 ComfyUI API（自有客户端，不经 kmc/hermes runtime）；mirror route-client 先例 + p11b VRAM pitfalls
6. dataset 导出 = 独立目录 `dataset/<video-stem>/`（非 asset.json 内嵌 subset）
7. 音频侧 round-trip 对比 defer v1.4
8. 首轮抽样 ≤20 镜校准打分阈值；全量 = 校准后的 overnight 批任务（8-13h/集），不进交互路径

Carried (still load-bearing): contract-first minor bump（一个 milestone 一个 minor）；byte-identical-absent 红线；`SCHEMA_VERSION` 单源（export_asset.py，勿复制字面量）；conditional fields nullable+confidence；HITL 硬门先例（registry + speaker review）；v1.x fixture 前向/后向 cross-version proof 模式。

- [Phase 18]: 18-01: roundtrip.json 挂载前不做 schema 校验（仅 JSON-parse + verdict 计数；完整 gate 留在 validate.py V13 / verify_contract producer mode — Open Q3 锁定）
- [Phase 18]: 18-01: RT-01/RT-02/RT-04 保持未勾选 — 本 plan 只交付 schema/single-source/channel 半边，fixture+gate+proof 半边在 18-02（同 requirement IDs）
- [Phase 18]: 18-02: backward v1.3→v1.2 过滤豁免恰为两类（additionalProperties 任意处；type/anyOf 仅当 absolute_path 前两段==(generator,warnings)）—— 注入 asset_type const 漂移仍 FAIL（A3 负测试证过滤不盲）
- [Phase 18]: 18-02: ep01 默认目录 producer-mode 失败是 pre-existing 运行时漂移（registry.draft.json method/total_clusters/total_crops，2026-07-30 实验产物 untracked）—— 不修（scope boundary），记 deferred-items #2；验证走文档化 PHASE4_ASSET_DIR=ep02 覆盖
- [Phase 18]: 18-03: SPEC/README 单源位置引用 grep 实测行号 export_asset.py:59 — v1.2 小节 stale 'line 55' 预警命中，两处新散文均引实测值
- [Phase 18]: 18-03: AF-01 枚举句改写为 pattern-composition 描述（Rule 1）— 禁词 grep 是纯字面机器门，mention-not-use 不可区分；SPEC §10.1 + README v1.2 小节两处
- [Phase 18]: 18-03: RT-03 人类审阅 approved（Kai, 2026-08-19，无 wording issues）— Phase 18 契约层四 requirement 收口
- [Phase 19]: 19-01: merged_B 按 facet 分键存 dict（{action,camera}）；RAW 答案键存在即已问（空答案落 cache 空串防重问死循环）；facet 产出要求 RAW 证据完整
- [Phase 19]: 19-01: VISION-01/02 保持未勾选 —— 模块+单测半边已交付，spike（19-02）与 wiring（19-03）共享同 requirement IDs（mirror 18-01 先例）
- [Phase 19]: 19-02: spike 实测 147 calls ≈15.5min（A1 估 1-3h 高估一个量级）；live sha256 不变 + SC4 秒级重跑在案；盲评映射 seed=20260819 只落 strategy_mapping.txt（裁决后回写报告）
- [Phase 19]: 19-02: Kai 盲评锁定甲 = temporal（2026-08-20）→ MERGE_STRATEGY_DEFAULT 本就一致零代码变更；SC3 ear diff 同 checkpoint 复核无异议；SC2 收口

### Pending Todos

None yet.

### Blockers/Concerns (v1.3 top risks — from `.planning/research/SUMMARY.md`)

- **verdict 混淆 prompt 质量与 h3 能力**：不归因则数据集系统性偏向简单动作 → Phase 21 judge 归因三分类 + rejected 占比记录可审计（验收硬性要求）
- **h3 渲染时长 / VRAM 竞争**：8-13h/集；TTS（:5110/:5111）与 ComfyUI 同卡；qwen-eye 13.4GB lease 与 h3 互斥 → Phase 20 per-shot cache + 断点续跑 + VRAM guard（kill TTS + `POST /free` + <22GB 拒提交）+ eye→h3 串行编排
- **Q3 27B 帧序列问答动作描述质量未验证**：llama.cpp 单图 bug 只能逐帧问 → Phase 19 首个 plan 必含 ep01 小样本校验 + 合并策略 spike
- Cross-repo route branches（shot-analysis / audio-analysis）仍 unmerged — **不阻塞 v1.3**（round-trip 走 kst 本地 ComfyUI 直连，无 route 依赖），只影响 v1.1/v1.2 deferred 的 live round-trip 验证

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260725-afz | 音频 prompt 反推 spike → 晋升 v1.2 Phase 15 | 2026-07-25 | 3a85a56 | [dir](./quick/260725-afz-prompt-spike-audio-gen-nl-prompt-demucs/) |
| 260819-aw2-fast | semantic 防覆盖守卫（route degrade 不销毁富 prompts.json）+ 3 pytest | 2026-08-19 | fast | ✅ |
| 9077e55 | local_reid 直产 schema 合规 draft + GLM sidecar | 2026-08-19 | 9077e55 | ✅ |
| 260819-aw2 | 画布自动导入 scripts/canvas_import.py + step_export 后钩子 + 6 pytest | 2026-08-19 | 0e1feb9 | [dir](./quick/260819-aw2-canvas-auto-import/) |

## Deferred Items

Items acknowledged and carried forward (full history in archived milestone REQUIREMENTS.md):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v1.3 (Future) | VISION-03: vLLM + Qwen3-VL-8B 视频原生输入（模型已在盘） | Deferred — 升级位 | 2026-08-19 |
| v1.3 (Future) | AUDIO-CMP-01: 音频侧 round-trip（h3 环境音 vs Demucs stems） | Deferred — v1.4 | 2026-08-19 |
| v1.3 (Future) | CANVAS-RT-01: canvas roundtrip 消费节点 | Deferred — 后续 milestone | 2026-08-19 |
| v1.2 遗留 | MUS-04 多标签乐器识别 | Continue defer — PANNs zenodo-blocked 未解 | 2026-08-19 |
| v1.2 遗留 | DIA-06 face-voice 自动 speaker→character | Continue defer | 2026-08-19 |
| v1.1/v1.2 | Live `shot-analysis` / `character-reid` / `audio-analysis` route round-trip + e2e backend verify | Deferred — kais-aigc-platform 分支 unmerged；graceful-degrade 已证 | 2026-07-25 |
| v1.2 (spike) | DIA-04 rigorous macro-F1 / WhisperX drift metric refinement / PANNs Cnn14 head-to-head | Deferred — route host up 后 | 2026-07-25 |
| v1.1 (v2) | 跨视频角色/音频连续性、prompt dialect、display enhancements | Deferred — v2 | 2026-07-24 |

## Session Continuity

Last session: 2026-08-19T18:25:23.202Z
Stopped at: Completed 19-02-PLAN.md (Phase 19 2/3 — Kai 盲评锁定甲=temporal，spike report FINAL)
Resume file: None

## Operator Next Steps

- `/gsd:plan-phase 18` — Contract v1.3（或并行规划 Phase 19）
