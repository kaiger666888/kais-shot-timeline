# kais-shot-timeline

## What This Is

视频分镜解构工具：把一支成片拆解成可导航、多轨道、带语义的分镜资产——分镜边界（首尾帧）+ Demucs 4-stem 分离音轨 + Whisper 对白转录 + 镜头语言/动作/场景的结构化 prompt + 跨镜可复用的角色/道具注册表，并以交互式 HTML 时间轴呈现（点击 stem 波形即静音视频、单独试听该轨，与画面同步）。服务于想把成片逆向成结构化分镜资产、并用于真实叙事连贯的内容创作者与 AI 影视管线。

## Core Value

把成片解构成可导航、多轨道的分镜资产（分镜 + 分离音轨 + 对白 + prompt），且这套形态可移植——能作为无限画布等下游消费者的「最终资产集合形态」被直接消费。

## Current Milestone: v1.1 分镜语义深化 —— 镜头语言 + 跨镜角色/道具注册表

**Goal:** 把成片从「边界 + 音轨 + 对白 + prompt 文本」升级为带镜头语言、动作、可复用跨镜角色/道具注册表的叙事资产——prompt 引用注册表实现真实叙事连贯，并把 ShotTimelineAsset 契约升到 v2。

**Target features:**
- 镜头语言/动作/语义自动填充——shot-timeline 作 HTTP 客户端调 kais-aigc-platform 运镜分析路由（geometry/SAM3/Qwen3-VL），自动填 `prompts.json` 的 `camera/action/scene/lighting/style/subject` 结构化字段（替代当前外部手动 `part_*.json`）
- 跨镜角色/道具注册表（re-id）——从首尾帧 SAM3 切出主体/道具图，跨镜识别同一实体 → 可复用「演员表 + 道具表」，带人工 review 修正（re-id 不可能 100% 准）
- prompt 引用系统——prompt 结构化引用注册表条目（角色/道具 ID），实现真实叙事连贯
- ShotTimelineAsset 契约 minor bump——`schema_version` 1→`1.1`（纯增量：新增 optional `characters`/`props` 数据文件 + 丰富 `prompts` schema，按项目 SPEC semver-lite 规则）；graceful-degrade 兜底老消费者
- 展示（双端）——shot-timeline HTML（角色/道具画廊 + 带 reference chip 的 prompt）+ canvas 消费者新增角色/道具节点类型（跨仓库 kais-aigc-platform）

> **v1.0（已归档）** ShotTimelineAsset Contract：定义并落地了仓库无关的 5-JSON 资产集合形态 + 导出器 + 画布最小消费 + 跨仓库验证。详见 `.planning/MILESTONES.md`。本 milestone 在其契约之上做语义深化与契约 minor bump。

## Requirements

### Validated

<!-- 已发布、确认有价值。v1.0 之前的 pre-GSD 基线。 -->

- ✓ 分镜检测（V1 Adaptive / V2 双检测器+后处理 / V3b 4 趟融合推荐版）— PySceneDetect — pre-GSD 基线
- ✓ 音轨分离（Demucs htdemucs 4-stem: vocals/drums/bass/other）+ 分镜级能量/频谱分析 — pre-GSD 基线
- ✓ 语音转录（Whisper，faster-whisper 优先、openai-whisper 回退）— pre-GSD 基线
- ✓ 交互式时间轴 HTML（双面板：分镜卡片首尾帧 + 竖向 stem 波形 + 视频播放器 + 实时字幕条 + 点击播放分离 stem）— pre-GSD 基线
- ✓ 分镜卡片网格 / 音频分析卡片网格 / prompt 审阅 HTML（一键复制）— pre-GSD 基线
- ✓ 分镜 prompt 反推（首尾帧 → 结构化 prompt + 连贯 prompt 文本 → prompts.json）— pre-GSD 基线
- ✓ Range-aware HTTP server（scripts/serve.py，206 Partial Content）用于 stem/视频 seek 播放 — pre-GSD 基线
- ✓ ShotTimelineAsset 规范（6 个 JSON Schema draft 2020-12 + 版本号 graceful-degrade 规则 + 媒体引用约定 + 自描述 manifest + validate.py）— Validated in Phase 1: ShotTimelineAsset Specification
- ✓ shot-timeline 导出 ShotTimelineAsset 产物（export_asset.py 写 asset.json + canonical symlinks；run_pipeline.py step_export 第 6 步 always-on；serve.py FD-leak 修复 + check_range.py Range-206 自检；additive-only）— Validated in Phase 2: shot-timeline Exporter (Producer)
- ✓ 画布侧（@kais/infinite-canvas）消费 ShotTimelineAsset，表示为 collection（import-from-dir.ts 新增 ShotTimelineAsset 分支：asset.json 识别 → extractShotTimelineArtifacts → 复用 buildPhaseTree；1 zone 父节点 + storyboard/audio/video 子节点 + sequence edges；合成字段满足 per-type Zod，不改 renderer / 不 bump contract；跨仓库 kais-aigc-platform feat/canvas-asset-collection）— Validated in Phase 3: Canvas Consumer
- ✓ 跨仓库契约一致性验证（scripts/verify_contract.py 三模式 harness：producer inline schema 校验 + consumer shells Phase 3 verify + e2e 真 producer→backend→SQL read-back 断言 1 zone+93 storyboard+3 audio+video+92 sequence edges；self-test 证 fail-loud；WR-01/04 正式接受）— Validated in Phase 4: Cross-Repo Contract Verification

### Active

<!-- 当前 milestone 范围。v1.1 分镜语义深化。REQ-IDs 见 REQUIREMENTS.md。 -->

- [ ] 镜头语言/动作/语义：shot-timeline 调运镜分析路由，自动填 prompts.json 结构化字段
- [ ] 跨镜角色/道具注册表：首尾帧 SAM3 切图 + re-id 形成可复用演员表/道具表 + 人工 review
- [ ] prompt 引用系统：prompt 结构化引用角色/道具 ID，实现叙事连贯
- [ ] ShotTimelineAsset 契约 minor bump：schema_version 1→1.1，新增 characters/props + 丰富 prompts schema（纯增量），graceful-degrade 兜底
- [ ] 双端展示：shot-timeline HTML 角色道具画廊 + reference chip；canvas 新增角色/道具节点类型（跨仓库）



### Out of Scope

<!-- 明确边界，含理由，防止回头再加。v1.1 在 v1.0 基础上更新。 -->

- 完全自动 re-id（无人 review）— re-id 不可能 100% 准，v1.1 必须 human-in-the-loop；全自动留待 re-id 精度成熟后再评估
- 对白→角色归属（谁说了哪句台词）— 强力叙事能力但是大 lift（需说话人识别/唇形对齐），v1.1 不做
- 跨成片角色连续性（同一角色跨不同视频识别为同一实体）— v1.1 只在单支成片内 re-id；跨片留后续
- 画布内原生时间轴渲染器（stem 播放引擎、波形 canvas、Range 媒体服务）— 完整原生交互是后续 milestone
- 新增画布 custom renderer — v1.1 用「新节点类型 + 复用现有渲染器」路径，仍不引入 custom renderer（契约 bump 仅是 schema_version + 新数据文件，渲染复用）
- 修改 shot-timeline 现有检测/转录/分离算法本身 — 仍是 validated 基线；v1.1 新分析（镜头语言/角色道具）全部走外部 kais-aigc-platform 路由，不动 shot-timeline 自身算法
- 把 shot-timeline 的检测/转录/分离拆成画布编排 skill（紧耦合方案）— 仍维持「外部生产者」松耦合

## Context

**跨仓库关系。** 本仓库（kais-shot-timeline）是新建立的 GSD 工程，作为 ShotTimelineAsset 格式的**生产者/权威定义方**。消费方是 `/data/workspace/kais-aigc-platform/packages/infinite-canvas`（`@kais/infinite-canvas`，React Flow + Zustand + Vite/TS）。两个仓库松耦合：shot-timeline 导出产物，画布通过其现有 `import-from-dir` 路径吃进来。画布的 GSD 工程独立（已到 v2.0），不在本仓库追踪。

**画布侧关键事实（决定本 milestone 形态）。** 画布当前**没有「相关资产集合」概念**——`storyboard` 节点 = 单个镜头，镜头序列只靠 `sequence` 边表达。shot-timeline 的格式本质是一个同步多镜头集合（分镜 + stems + 转录 + prompts），因此本 milestone 实际上是给画布引入一个目前不存在的实体类型。低摩擦落地路径：用一个结构化父节点（沿用 `zone`/`phase` 模式，持有子节点 ID）聚合现有 `storyboard`/`audio`/`video` 子节点——画布的 receiver schema (`canvasAssetSchema.ts`) 已经把 `structuralTypes = {zone, phase, suggestion, reference}` 透传不校验，复用现有 5 个渲染器，无需 `default_renderer` 新选项（contract bump）。

**shot-timeline 当前数据形状（导出契约的来源）。** 5 个 JSON 喂给 HTML 生成器：`shots.json`（`{id, start_sec, end_sec, duration}`，canonical 镜头列表）、`audio_analysis.json`（Demucs 分析 + 每镜能量/谱/`dominant_type`）、`transcript.json`（Whisper segments）、`frames.json`（首尾帧 base64）、`prompts.json`（结构化 prompt）。运行时还需 video mp4 + 3 个 stem wav（`_vocals/_drums/_other`）经 Range-aware server 提供。timeline.html 自包含（内联 CSS/JS、帧内联 base64），唯独这 3 个媒体文件外置。

**v1.1 新增语义层（镜头语言 + 角色/道具注册表）。** 现状关键事实：① `prompts.json` schema 已含 `subject/action/camera/scene/lighting/style/prompt_text` 结构化字段，但 shot-timeline **没有 prompt 生成器**——`prompts/merge_prompts.py` 只合并外部产出的 `prompt_parts/part_*.json`，字段目前靠外部/手动填。② 运镜分析能力**已在 kais-aigc-platform 用 ComfyUI 落地**（geometry 自建节点跑稀疏光流出运镜 + SAM3.1 主体跟踪出主体运动 + Qwen3-VL-8B INT8 出景别/机位/语义；driver `scripts/shot-analysis/shot_analysis_driver.py` 读 `shots.json` 逐镜投喂，路由 `POST /api/v1/production/shot-analysis`），P0-P4 验证完成（2026-07-23），但**两特性分支未 merge**（`feat/shot-geometry-nodes` 节点 + `feat/shot-analysis-route` driver/路由）。该输出几乎一一映射到现有 prompts 字段。③ 角色/道具切图 + 跨镜 re-id 是**全新能力**，尚不存在。v1.1 决定：shot-timeline 作 HTTP 客户端调这些路由（运镜复用、角色道具新建端点），合并 JSON 进资产；re-id 走「DINOv2 embedding + Agglomerative 聚类 + 三档阈值 + 人工 review」半自动路径；契约 minor bump 到 schema_version `"1.1"`（纯增量，按项目 SPEC semver-lite 规则），靠 v1.0 graceful-degrade 规则兜底老消费者。

## Constraints

- **跨仓库**：shot-timeline（本 GSD 工程）= 生产者 + 路由客户端 + 契约权威；kais-aigc-platform = 分析路由宿主 + canvas 消费者（每 phase 独立分支/PR）
- **松耦合**：shot-timeline = 外部生产者，画布 = 消费者；产物必须自描述、带版本号，两个仓库可独立演进
- **不动 shot-timeline 核心算法**：分镜检测/转录/分离仍是 validated 基线；v1.1 新分析（镜头语言/角色道具）**全部走 kais-aigc-platform 路由**，不在 shot-timeline 内重跑 ML
- **路由依赖**：shot-timeline 的镜头语言/角色道具填充依赖 kais-aigc-platform 路由可用 + 两未 merge 运镜分支先上线；路由不可用时 shot-timeline 必须能 graceful-degrade（跳过该步、资产仍可生成）
- **re-id 精度上限**：跨镜 re-id 不可能 100% 准，必须 human-in-the-loop review；接受「够用即可」，不追求全自动
- **契约仅 minor bump**：v1.1 把 schema_version 升到 `"2"`，新增字段/数据文件，但不做破坏性变更（无 rename/语义漂移/删除）；老消费者靠 graceful-degrade 不崩。仍不引入画布 custom renderer（新节点类型复用现有渲染器）
- **媒体服务**：导出约定需覆盖 Range-aware HTTP 服务（画布消费 stem/视频 seek 依赖 206 响应）；角色/道具图作为新媒体类别纳入约定

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1.0 交付 = 格式契约（非原生组件移植、非 iframe 嵌入） | 格式是骨架，原生渲染/嵌入都建立在它之上；v1.0 先落契约 + 画布最小消费 | — Pending |
| shot-timeline 作为「外部生产者」（非画布编排 skill） | 与「shot-timeline 独立 GSD 工程」决策一致；两仓库松耦合、独立演进 | ✓ Validated Phase 2（export_asset.py + step_export 落地导出层，additive-only） |
| 画布用结构化父节点表示 collection（非新 node type / custom renderer） | receiver schema 已透传 structural types，复用现有 5 渲染器，零 contract bump | — Pending |
| GSD 工程建在 shot-timeline（非 aigc-platform） | 格式权威定义方 = 生产者；aigc-platform 已有独立 GSD（v2.0） | — Pending |
| 在 `feat/canvas-asset-collection` 分支开发（非 main / 非 worktree） | main 保留可交付、隔离多 phase 工作；worktree 无法跨仓库组合且拆分 .planning/ 状态 | ✓ Validated Phase 3/4（v1.0 已 ship） |
| **v1.1** 新分析走「shot-timeline 调 kais-aigc-platform 路由」（非本地实现） | 运镜 infra 已在 comfyui 侧建好；延续 v1.0 松耦合；shot-timeline 不增重 ML 依赖；需先 merge 两运镜分支 | — Pending |
| **v1.1** 角色道具做「跨镜 re-id 注册表」（非单镜提取） | 「真实叙事连贯」的核心 = 同一角色跨镜是同一引用；接受 re-id 不准、用人工 review 兜底 | — Pending |
| **v1.1** 升级 ShotTimelineAsset 到 schema_version `"1.1"`（minor bump，非侧车数据；刻意不用 `"2"`） | 纯增量变更按项目 SPEC semver-lite 规则 = minor；保留 `"2"` 给未来破坏性变更；资产自描述、可移植、一等公民；v1.0 graceful-degrade 规则专为这种 minor bump 设计 | — Pending |
| **v1.1** 双端展示（shot-timeline HTML + canvas 新节点类型） | 用户要端到端可见；接受跨仓库 ~30% 额外开销（v1.0 实测） | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-24 after /gsd-new-milestone — v1.1 分镜语义深化 milestone started (镜头语言 + 跨镜角色/道具注册表 + 契约 v2 + 双端展示)*
