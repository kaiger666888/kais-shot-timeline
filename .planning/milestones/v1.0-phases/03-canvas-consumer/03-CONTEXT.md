# Phase 3: Canvas Consumer - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — grey areas accepted as recommended

<domain>
## Phase Boundary

让 `@kais/infinite-canvas` 的现有 `import-from-dir` 路径能消费一个 **ShotTimelineAsset 目录**（Phase 2 产物），在画布上表示为一个 **collection**：一个 `zone` 结构化父节点聚合 `storyboard`/`audio`/`video` 子节点，**复用现有 5 个渲染器**（script/asset/storyboard/video/audio + zone + Fallback），**不引入 custom renderer / 不 bump contract**（receiver schema 已透传 `structuralTypes`）。

本 phase **只加消费层**：不改 5 个渲染器本身、不动 React Flow / Zustand store 结构、不改 receiver schema 的校验严格度。交付物：backend `import-from-dir.ts` 新增 ShotTimelineAsset 分支（识别 `asset.json` → `extractShotTimelineArtifacts` → 复用 `buildPhaseTree`/`appendAndSync`）+ 一个 standalone TS verify script + 一个 golden fixture（shot-timeline ep01 真实导出资产）。

**Goal:** The canvas's existing `import-from-dir` path ingests a ShotTimelineAsset directory and renders it as a first-class collection on the canvas, using only existing renderers.
**Requirements:** CANVAS-01, CANVAS-02, CANVAS-03
**Repo:** `kais-aigc-platform`（跨仓库；本仓库 .planning/ 仅做 milestone 级追踪）
**Depends on:** Phase 1（spec）, Phase 2（一个真实导出资产作为测试对象）

</domain>

<decisions>
## Implementation Decisions

### 跨仓库执行模型 + 分支策略 (blocker)
- **执行从本仓库 GSD 驱动跨仓库**：discuss/plan 在本仓库 `.planning/`（milestone 统一追踪）；executor 进 `kais-aigc-platform` 改代码；commits 落在 `kais-aigc-platform` 的 `feat/canvas-asset-collection` 分支
- **干净 worktree**：`/data/workspace/kst-canvas-consumer`，从 `origin/master`（686d526c）创建的 git worktree，分支 `feat/canvas-asset-collection`。理由：`kais-aigc-platform` master 有并发 ltx 工作（uncommitted，与本 phase 无关），worktree 隔离保证 Phase 3 diff 干净、不扰动并发工作。沿用项目既有 worktree 模式
- executor 在该 worktree 内操作；所有 git commit 落在 `feat/canvas-asset-collection`

### 导入器位置 (CANVAS-01)
- **在 `scanWorkdirForArtifacts`（import-from-dir.ts:996）加一个 ShotTimelineAsset 分支**：检测根目录 `asset.json` → 调用新 helper `extractShotTimelineArtifacts(assetJson, workdir)` → 复用既有 `buildPhaseTree`（Zone→Summary→Artifact 模式）+ `appendAndSync`（bootstrap 事件持久化）+ `fsToOssUrl`（媒体 URL 归一化）
- 单一既有入口（`POST /api/canvas/v2/import-from-dir`），最小新增表面积；不新挂路由
- 识别判据：workdir 根存在 `asset.json` 且 `asset_type === "shottimeline"`（schema_version graceful-degrade：未知版本不 reject，warn 后渲染已知部分）

### Collection → Canvas 节点映射 + Schema 约束 (CANVAS-02, CANVAS-03 核心)
- **结构**：ONE `zone` 父节点（`data.label = source.video_filename`，`data.phase` = 选定 phase group）+ 子节点：
  - `storyboard` × N：每镜一个（来自 `shots.json` 的 `{id, start_sec, end_sec, duration}`），携带 `shot_id`、首帧缩略图（来自 `frames.json` base64 → OSS 临时文件或内联）、`duration_sec`
  - `audio` × 3：每个 stem 一个（vocals/drums/other，来自 `media.stems`），携带 `filePath`（fsToOssUrl 归一化）、`duration_sec`
  - `video` × 1：master（`media.video` → video.mp4），携带 `filePath`、`duration_sec`
  - transcript/prompts：作为 sidecar description 附挂（不单独建 script/asset 节点 —— 保持节点数克制）
- **Schema 字段合成**（关键：per-type Zod schemas 要求 asset 不直接携带的字段）：
  - `engine = "shot-timeline"`（provenance 标识，所有 audio/video 子节点）
  - `shot_type`：从 `prompts.json` 推断（如 prompt 含镜头语言关键词）或默认 `"scene"`（storyboard 子节点）
  - `resolution`：ffprobe 探 `video.mp4` 得到（如 `1920x1080`）（video 子节点）
  - `shot_id`：来自 `shots.json` 的 `id`（storyboard）；audio/video 用集合级 sentinel（如 `"collection"` 或 `0`）
  - **不放宽 per-type schemas**（CANVAS-03 不 bump contract）—— 用合成值满足，并在节点 `data` 里标注 `__synthetic_fields` 供溯源
- **Sequence edges**：在 storyboard 子节点之间（按 `shot_id` 升序）emit `data: { linkType: 'sequence' }` 边 —— 唯一让分镜顺序在画布上可见的方式（蓝色箭头，`CanvasEdge.tsx:60-75`）。import-from-dir 现有 artifact 分支不 emit sequence 边，本 phase 新增

### Phase / Lane 归属 (Claude's discretion，低风险)
- 复用既有 phase group（倾向 `"production"` 或 `"post"/"delivery"`，p11/p12 区），单一 zone 单一 lane。或引入新 phase —— plan 阶段定（低风险、可逆）

### 验证方法 (CANVAS-01..03, SC)
- **Standalone TS verify script**：仿 `scripts/verify-import-roundtrip.ts`，喂 golden fixture 进导入器的纯函数（`extractShotTimelineArtifacts` → `buildPhaseTree`），断言：(a) Zone→children 结构正确（1 zone + N storyboard + 3 audio + 1 video）；(b) 每个 media 子节点通过 `canvasAssetSchema` 对应 per-type Zod（`validateNodeData` 返回 null）；(c) sequence edges 存在且按 shot_id 有序。无需起 backend
- **Golden fixture**：**复制 shot-timeline Phase 2 的 ep01 真实导出资产目录**到 `kais-aigc-platform/scripts/fixtures/shot-timeline-ep01/`（producer 输出 → consumer 测试输入；同时也是 Phase 4 VERIFY-01 的端到端 fixture 基础）
- 媒体文件（video.mp4 + stems/*.wav）也一并复制进 fixture，保证 `fsToOssUrl`/filePath 解析可测

### Claude's Discretion
- `extractShotTimelineArtifacts` 的精确内部结构（如何把 5 个 data JSON 折叠成 RawArtifact[] 喂 buildPhaseTree）
- phase/lane 归属的具体取值（production vs post vs 新 lane）
- 缩略图处理（首帧 base64 内联 vs 落 OSS 临时文件 vs 不显示）—— 受 ZoneNode/StoryboardNode 渲染能力约束，plan 阶段定
- `__synthetic_fields` 溯源标注的精确形态

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (all in kais-aigc-platform worktree)
- `src/routes/canvas/v2/import-from-dir.ts` —— **1502 行的导入主入口**。关键可复用：
  - `scanWorkdirForArtifacts` (L996-1135)：目录枚举 + JSON/media 提取 —— 加 ShotTimelineAsset 分支的位置
  - `buildPhaseTree` (L592-835)：Zone → Summary → Artifact 三级树构建 —— 直接复用
  - `appendAndSync` (L1393-1405 replace / L1465-1477 merge)：bootstrap 事件持久化 —— 复用
  - `fsToOssUrl` (L174-192)：绝对路径 → `/oss/...` URL + 自动建 `data/oss/{basename}` symlink —— 复用（媒体归一化）
  - `flattenParamsToNodeData` (L31-43)：params.* → node.data 扁平化 —— 参考
  - `broadcastToProject(projectId, "graph:saved", ...)` (L1480)：触发前端 reload —— 复用
- `src/lib/canvasAssetSchema.ts` —— per-type Zod schemas (L51-119 `assetDataSchemas`) + `structuralTypes={zone,phase,suggestion,reference}` 透传 (L121-140) + `validateNodeData` (L138) + `EXPECTED_PARAM_FIELDS_BY_TYPE` (L194-204)。**不改严格度**，只用 `validateNodeData` 做测试断言
- `src/types/flowgraph-v2-schema.ts` —— `NodeTypeSchema` 枚举 (L15-19，含 zone/phase) + `FlowNodeV2Schema` (L32-49)。权威节点结构
- `packages/infinite-canvas/src/components/FlowCanvas.tsx:42-64` —— 5 渲染器 + zone + Fallback 的 `nodeTypes` map（**不改**）
- `scripts/verify-import-roundtrip.ts` —— verify script 模板（imports 生产模块，replay fixtures，断言 roundtrip）
- `docs/canvas-import-from-dir.md` —— 用户文档（filename→phase 映射、请求/响应形状、curl/Python 示例）

### Established Patterns
- **Backend-driven ingestion**：导入器写 backend → `appendAndSync` → broadcast `graph:saved` → 前端 `loadCanvas` → `flowGraphToCanvas` → `setNodes(whole graph)`。前端 store 无 `addNode` API（设计如此）
- **Zone 不持 childNodeIds**：父子关系靠 (a) `dataType:'output'` 显式边 + (b) 共享 `data.phase`/`phaseIndex`/`phaseName`。autoLayout 按 `data.phase` 聚合 zone 子节点
- **Media URL 归一化**：所有 filePath 经 `fsToOssUrl`；sidecar `.txt`（同 basename）自动附为 description/prompt（10K 字符上限）
- **Sequence 语义**：边 `data.linkType='sequence'` → `CanvasEdge.tsx` 蓝色箭头。survives save/load roundtrip

### Integration Points
- `import-from-dir.ts:scanWorkdirForArtifacts` —— 加 asset.json 识别分支
- `import-from-dir.ts:extractShotTimelineArtifacts` (NEW) —— asset.json → RawArtifact[]
- `canvasAssetSchema.ts:assetDataSchemas` —— 合成字段必须满足（只读约束，不改）
- Phase 4 会用同一 golden fixture 做跨仓库端到端 VERIFY-01

</code_context>

<specifics>
## Specific Ideas

- 必须复用既有 `import-from-dir` 入口（不新挂路由）—— CANVAS-01 字面要求「现有 import-from-dir 路径能消费」
- per-type Zod schemas 是硬约束：media 子节点（storyboard/video/audio）必须携带规定字段，否则 `save-v2` HTTP 400 reject。合成字段（engine/shot_type/resolution）是满足约束的手段，不是放宽约束
- sequence edges 是分镜顺序在画布上可见的唯一方式 —— import-from-dir 现有 artifact 分支不 emit，本 phase 必须新增
- golden fixture = shot-timeline ep01 真实导出（producer→consumer 跨仓库实物，不是手写 minimal）

</specifics>

<deferred>
## Deferred Ideas

- 画布内原生时间轴渲染器（stem 播放引擎、波形 canvas）—— v2 milestone（NATIVE-01/02），建立在 v1.0 契约之上
- transcript → script 节点、prompts → asset 节点的细粒度映射 —— 本 phase 保持节点数克制（storyboard/audio/video），细粒度留待后续
- ShotTimelineAsset 专属 phase lane（p14）—— 本 phase 复用既有 phase group，新 lane 留待评估
- 把 ShotTimelineAsset 导入做成画布编排 skill —— ORCH-01，紧耦合方案，用户已选松耦合，留待未来评估
- None others —— 讨论保持在 phase 范围内

</deferred>
