# Phase 1: ShotTimelineAsset Specification - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — grey areas accepted as recommended

<domain>
## Phase Boundary

产出一份**仓库无关的 ShotTimelineAsset 契约文档**（+ 机器可校验的 schema），让生产者（kais-shot-timeline）和消费者（@kais/infinite-canvas）都能对着实现，无需口口相传。

本 phase **只定义契约**，不写导出器代码（那是 Phase 2）、不写画布消费代码（Phase 3）。交付物：规范文档 + 5 个 JSON Schema 文件 + 一个 manifest schema。

**Goal:** A repo-agnostic ShotTimelineAsset contract document exists that both producer and consumer can implement against without tribal knowledge.
**Requirements:** SPEC-01, SPEC-02, SPEC-03, SPEC-04
**Repo:** kais-shot-timeline（authoritative spec owner）
**Depends on:** Nothing (first phase)

</domain>

<decisions>
## Implementation Decisions

### Schema 描述语言 (SPEC-01)
- 用 **JSON Schema (draft 2020-12)** 正式描述 5 个 canonical JSON 形状，每个形状一份 schema 文件
- 另写一份 prose 规范文档总览（人读），JSON Schema 是机器可校验的权威源
- 理由：producer 是 Python、consumer 是 TS，JSON Schema 是两端通用 lingua franca；TS 类型可从 schema 生成

### 版本号 + 未知版本规则 (SPEC-02)
- 版本字段：**顶层 manifest 一个 `schema_version`**，semver-lite 形态（`"1"` / `"1.1"`），不是每个 JSON 各自带版本
- 消费端遇未知/更新版本：**graceful degrade** —— 忽略未知字段、渲染已知部分 + warn。不严格 reject（保向前兼容，避免脆弱断裂）
- 版本演进规则：新增字段=minor bump（旧消费端 degrade），破坏性变更=major bump（契约里写清迁移说明）

### 媒体引用 + Range 服务 (SPEC-03)
- 媒体文件用**资产目录内相对路径** + 固定命名约定：`video.mp4`、`stems/vocals.wav` / `stems/drums.wav` / `stems/other.wav`
- 明确要求消费端经 **Range-aware HTTP 206 (Partial Content)** 访问媒体（沿用现有 `scripts/serve.py` 已实现的 206 服务），不要求消费端自起服务
- 不内联视频/stem（太大）；frames 首尾帧除外（见下）

### Manifest + 文件布局 (SPEC-04)
- 单一入口 `asset.json`（manifest）：含 `schema_version`、source（来源视频）、generator（工具名 + 版本）、5 个数据 JSON 的清单、媒体文件清单
- 数据 JSON 平铺在资产目录（或按子目录，plan 阶段定细节）
- frames 首尾帧**维持内联 base64**（现有 `frames.json` 模式，保持单文件自包含）

### Claude's Discretion
- JSON Schema 文件的具体目录布局（`schemas/` 下按形状分文件）
- prose 规范文档的结构与详略
- `asset.json` manifest 的精确字段集（在满足 SPEC-04 最小要求基础上可扩展）

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- 现有 5 个数据 JSON 的实际形状（来自 codebase map + PROJECT.md）—— 契约 schema 的来源：
  - `shots.json`: `{id, start_sec, end_sec, duration}` —— canonical 镜头列表
  - `audio_analysis.json`: Demucs 分析 + 每镜能量/谱/`dominant_type`
  - `transcript.json`: Whisper segments（{start, end, text}）
  - `frames.json`: 首尾帧 base64
  - `prompts.json`: 结构化 prompt
- `scripts/serve.py`: 已实现 Range-aware 206 服务 —— SPEC-03 的服务端已存在

### Established Patterns
- pipeline 用 `output/<video-stem>/*.json` 解耦各 stage（见 ARCHITECTURE.md）
- JSON 一律 `ensure_ascii=False` + `indent=2`（中文内容，见 CONVENTIONS.md）

### Integration Points
- Phase 2 导出器会按本 phase 产出的 schema 生成资产
- Phase 3 画布消费端会按本 schema（生成 TS 类型后）解析资产

</code_context>

<specifics>
## Specific Ideas

- frames 维持内联 base64 是用户已接受的具体形态（不是外部图片文件）
- manifest 要自描述到「消费端无需外部文档即可理解资产」

</specifics>

<deferred>
## Deferred Ideas

None — 讨论保持在 phase 范围内。导出器实现细节归 Phase 2，画布消费归 Phase 3。

</deferred>
