# Requirements: kais-shot-timeline — v1.0 ShotTimelineAsset Contract

**Defined:** 2026-07-20
**Core Value:** 把成片解构成可移植的分镜资产集合（分镜 + stems + 转录 + prompts），作为下游 `@kais/infinite-canvas` 可直接消费的一等 collection 形态。

## v1 Requirements

本 milestone（v1.0）范围：定义并落地 **ShotTimelineAsset** 格式契约 —— 仓库无关、自描述、带版本号；由 kais-shot-timeline 导出，被 @kais/infinite-canvas 消费。

### SPEC — ShotTimelineAsset 规范

- [x] **SPEC-01**: 定义 5-JSON canonical 形状的字段 schema —— `shots`（边界/时长）、`audio_analysis`（Demucs + 每镜能量/谱/dominant_type）、`transcript`（Whisper segments）、`frames`（首尾帧）、`prompts`（结构化 prompt） — DONE Plan 01-01 (6 schemas under spec/schemas/)
- [x] **SPEC-02**: 定义资产版本号字段（schema versioning），使导出端与消费端可独立演进、做兼容性判断 — DONE Plan 01-01 (asset.schema.json schema_version + graceful-degrade rule)
- [x] **SPEC-03**: 定义媒体引用约定 —— video mp4 + 3 个 stem wav 的路径/命名规则，以及 Range-aware HTTP 服务要求（206 Partial Content，供消费端 seek 播放） — DONE Plan 01-01 (canonical patterns; Range 206 ref in spec/README.md → scripts/serve.py)
- [x] **SPEC-04**: 资产自描述（manifest 描述内容清单、来源视频、生成参数/工具版本），消费端无需外部文档即可理解 — DONE Plan 01-01 (asset.schema.json: source/generator/data/media inventory)

### EXPORT — shot-timeline 导出端（生产者，本仓库）

- [ ] **EXPORT-01**: 实现 shot-timeline 导出器，把 `run_pipeline.py` 产出的 `output/<stem>/` 打包成符合 SPEC 的 ShotTimelineAsset 产物
- [ ] **EXPORT-02**: 导出产物带版本号、自描述 manifest，且不改变现有检测/转录/分离算法（仅在其输出之上加导出层）
- [ ] **EXPORT-03**: 导出端通过 Range-aware server（`scripts/serve.py`）对外提供媒体文件，满足消费端 stem/视频 seek 依赖

### CANVAS — 画布消费端（@kais/infinite-canvas，跨仓库 kais-aigc-platform）

- [ ] **CANVAS-01**: 画布现有 `import-from-dir` 路径能消费 ShotTimelineAsset，在画布上表示为一个 collection（结构化父节点）
- [ ] **CANVAS-02**: 用结构化父节点（沿用 `zone`/`phase` 模式，持有子节点 ID）聚合现有 `storyboard`/`audio`/`video` 子节点
- [ ] **CANVAS-03**: 复用画布现有 5 个渲染器，不引入 custom renderer / 不 bump contract（receiver schema 已透传 structuralTypes）

### VERIFY — 跨仓库契约一致性

- [ ] **VERIFY-01**: 导出端产物能被消费端成功 import，并正确渲染出分镜/stem/字幕/prompt 集合
- [ ] **VERIFY-02**: 契约一致性验证 —— 字段 schema 与媒体引用在导出端 ↔ 消费端两端对齐，有回归保护

## v2 Requirements

Deferred to future milestone（建立在 v1.0 契约之上）：

### 原生交互

- **NATIVE-01**: 画布内原生时间轴渲染器（stem 播放引擎、波形 canvas）
- **NATIVE-02**: 画布内原生 Range 媒体服务（脱离 shot-timeline 独立 seek）

### 编排

- **ORCH-01**: 把 shot-timeline 检测/转录/分离拆成画布编排 skill（替代外部生产者松耦合方案）

## Out of Scope

| Feature | Reason |
|---------|--------|
| 检测/转录/分离算法优化或替换 | 已是 validated 基线，v1.0 不动核心算法，只在其输出上加导出层 |
| 新增画布 custom renderer（contract bump） | 用结构化父节点复用现有 5 渲染器是更低摩擦路径，v1.0 明确选这条 |
| shot-timeline 的 Web UI / 多用户 / 在线分析 | 定位单机离线 CLI；本 milestone 只产出可移植资产 |
| 把数据集训练流程放进本仓库 | 本仓库只产出资产，训练在 aigc-platform 侧 |
| kais-movie-center / kais-movie-pipeline 对接 | v1.0 消费方先只做 @kais/infinite-canvas；其余平台对接留待后续 milestone |

## Traceability

由 roadmap 创建时填充（每条 v1 requirement 映射到恰好一个 phase）。

| Requirement | Phase | Status |
|-------------|-------|--------|
| SPEC-01 | Phase 1 | Complete (Plan 01-01) |
| SPEC-02 | Phase 1 | Complete (Plan 01-01) |
| SPEC-03 | Phase 1 | Complete (Plan 01-01) |
| SPEC-04 | Phase 1 | Complete (Plan 01-01) |
| EXPORT-01 | Phase 2 | Pending |
| EXPORT-02 | Phase 2 | Pending |
| EXPORT-03 | Phase 2 | Pending |
| CANVAS-01 | Phase 3 | Pending |
| CANVAS-02 | Phase 3 | Pending |
| CANVAS-03 | Phase 3 | Pending |
| VERIFY-01 | Phase 4 | Pending |
| VERIFY-02 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 12 total
- Mapped to phases: 12 (Phase 1: 4, Phase 2: 3, Phase 3: 3, Phase 4: 2)
- Unmapped: 0

---
*Requirements defined: 2026-07-20*
*Last updated: 2026-07-20 — traceability backfilled after ROADMAP.md creation*
