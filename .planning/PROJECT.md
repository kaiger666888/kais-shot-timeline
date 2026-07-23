# kais-shot-timeline

## What This Is

视频分镜解构工具：把一支成片拆解成可导航、多轨道的分镜资产——分镜边界（首尾帧）+ Demucs 4-stem 分离音轨 + Whisper 对白转录 + 分镜 prompt 反推，并以交互式 HTML 时间轴呈现（点击 stem 波形即静音视频、单独试听该轨，与画面同步）。服务于想把成片逆向成结构化分镜资产的内容创作者与 AI 影视管线。

## Core Value

把成片解构成可导航、多轨道的分镜资产（分镜 + 分离音轨 + 对白 + prompt），且这套形态可移植——能作为无限画布等下游消费者的「最终资产集合形态」被直接消费。

## Current Milestone: v1.0 ShotTimelineAsset Contract

**Goal:** 定义一个仓库无关的 ShotTimelineAsset 格式，把成片的分镜时间轴（分镜 + stems + 转录 + prompts）变成一种可移植的「资产集合形态」——由 kais-shot-timeline 导出，被 @kais/infinite-canvas 作为一等集合（first-class collection）消费。

**Target features:**
- ShotTimelineAsset 规范——canonical「资产集合形态」：通用化的 5-JSON 形状（shots / audio_analysis / transcript / frames / prompts）+ 媒体引用约定（视频 + 3 个 stem wav，Range 服务）
- shot-timeline 导出器——pipeline 输出 → ShotTimelineAsset 产物（JSON + 媒体引用），带版本号、自描述
- 画布消费（@kais/infinite-canvas，跨仓库）——现有 import-from-dir 路径消费 ShotTimelineAsset，在画布上表示为一个 collection（结构化父节点聚合 storyboard/audio/video 子节点，复用现有 5 个渲染器，无需 contract bump）

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

<!-- 当前 milestone 范围。v1.0 ShotTimelineAsset Contract。 -->

*All v1.0 requirements validated — milestone complete. See lifecycle (audit → complete → cleanup).*



### Out of Scope

<!-- 明确边界，含理由，防止回头再加。 -->

- 画布内原生时间轴渲染器（stem 播放引擎、波形 canvas、Range 媒体服务）— v1.0 只做格式契约 + 结构化集合表示；完整原生交互是后续 milestone，建立在契约之上
- 把 shot-timeline 的检测/转录/分离拆成画布编排 skill（紧耦合方案）— 用户已选「外部生产者」松耦合；画布编排留待未来评估
- 新增画布 custom renderer（contract bump）— v1.0 用结构化父节点复用现有 5 渲染器的低摩擦路径
- shot-timeline 现有检测/转录/分离算法本身的优化或替换— 已是 validated 基线，本 milestone 不动核心算法

## Context

**跨仓库关系。** 本仓库（kais-shot-timeline）是新建立的 GSD 工程，作为 ShotTimelineAsset 格式的**生产者/权威定义方**。消费方是 `/data/workspace/kais-aigc-platform/packages/infinite-canvas`（`@kais/infinite-canvas`，React Flow + Zustand + Vite/TS）。两个仓库松耦合：shot-timeline 导出产物，画布通过其现有 `import-from-dir` 路径吃进来。画布的 GSD 工程独立（已到 v2.0），不在本仓库追踪。

**画布侧关键事实（决定本 milestone 形态）。** 画布当前**没有「相关资产集合」概念**——`storyboard` 节点 = 单个镜头，镜头序列只靠 `sequence` 边表达。shot-timeline 的格式本质是一个同步多镜头集合（分镜 + stems + 转录 + prompts），因此本 milestone 实际上是给画布引入一个目前不存在的实体类型。低摩擦落地路径：用一个结构化父节点（沿用 `zone`/`phase` 模式，持有子节点 ID）聚合现有 `storyboard`/`audio`/`video` 子节点——画布的 receiver schema (`canvasAssetSchema.ts`) 已经把 `structuralTypes = {zone, phase, suggestion, reference}` 透传不校验，复用现有 5 个渲染器，无需 `default_renderer` 新选项（contract bump）。

**shot-timeline 当前数据形状（导出契约的来源）。** 5 个 JSON 喂给 HTML 生成器：`shots.json`（`{id, start_sec, end_sec, duration}`，canonical 镜头列表）、`audio_analysis.json`（Demucs 分析 + 每镜能量/谱/`dominant_type`）、`transcript.json`（Whisper segments）、`frames.json`（首尾帧 base64）、`prompts.json`（结构化 prompt）。运行时还需 video mp4 + 3 个 stem wav（`_vocals/_drums/_other`）经 Range-aware server 提供。timeline.html 自包含（内联 CSS/JS、帧内联 base64），唯独这 3 个媒体文件外置。

## Constraints

- **跨仓库**：格式 + 导出器在 shot-timeline（本 GSD 工程）；画布消费节点在 kais-aigc-platform（每 phase 独立分支/PR）—— on branch `feat/canvas-asset-collection`
- **松耦合**：shot-timeline = 外部生产者，画布 = 消费者；产物必须自描述、带版本号，两个仓库可独立演进
- **不碰核心算法**：分镜检测/转录/分离是 validated 基线，v1.0 不改算法，只在其输出之上加导出层
- **画布侧低摩擦**：复用现有渲染器 + 结构化父节点，不引入 custom renderer / contract bump
- **媒体服务**：导出约定需覆盖 Range-aware HTTP 服务（画布消费 stem/视频 seek 依赖 206 响应）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1.0 交付 = 格式契约（非原生组件移植、非 iframe 嵌入） | 格式是骨架，原生渲染/嵌入都建立在它之上；v1.0 先落契约 + 画布最小消费 | — Pending |
| shot-timeline 作为「外部生产者」（非画布编排 skill） | 与「shot-timeline 独立 GSD 工程」决策一致；两仓库松耦合、独立演进 | ✓ Validated Phase 2（export_asset.py + step_export 落地导出层，additive-only） |
| 画布用结构化父节点表示 collection（非新 node type / custom renderer） | receiver schema 已透传 structural types，复用现有 5 渲染器，零 contract bump | — Pending |
| GSD 工程建在 shot-timeline（非 aigc-platform） | 格式权威定义方 = 生产者；aigc-platform 已有独立 GSD（v2.0） | — Pending |
| 在 `feat/canvas-asset-collection` 分支开发（非 main / 非 worktree） | main 保留可交付、隔离多 phase 工作；worktree 无法跨仓库组合且拆分 .planning/ 状态 | — Pending |

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
*Last updated: 2026-07-21 after Phase 4 complete — v1.0 ShotTimelineAsset Contract milestone COMPLETE (all 4 phases verified: spec / exporter / consumer / cross-repo verification)*
