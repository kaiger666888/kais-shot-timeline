# Phase 3: Canvas Consumer - Research

**Researched:** 2026-07-20
**Domain:** Cross-repo TypeScript importer extension (kais-aigc-platform consumer for shot-timeline producer assets)
**Confidence:** HIGH (both repos inspected in person this session; worktree HEAD matches CONTEXT exactly)

## Summary

Phase 3 在 kais-aigc-platform worktree (`/data/workspace/kst-canvas-consumer`, branch `feat/canvas-asset-collection`, HEAD `686d526c` —— 与 CONTEXT.md 锁定一致 `[VERIFIED: worktree git rev-parse]`) 内,为 `src/routes/canvas/v2/import-from-dir.ts` 增加一个 `asset.json` 识别分支,把一份 ShotTimelineAsset 资产目录转换成画布上的一个 zone 父节点 + N storyboard + 3 audio + 1 video 子节点,且在不修改任何现有渲染器/不放宽 per-type Zod 的前提下通过 `validateGraphNodes` 严格校验。

关键约束已在前置代码中确定:per-type Zod (`src/lib/canvasAssetSchema.ts:51-119`) 是硬门槛 —— 缺 `filePath`/`shot_id`/`engine`/`duration_sec`/`shot_type`/`resolution` 任一字段的节点会被 `save-v2.ts:49` HTTP 400 拒绝。`buildPhaseTree` (L592-835) 还有一个结构性副作用:它把同一个 phase 下**所有** artifact 节点的 `type` 强制设为 `def.canvasType`,而 ShotTimelineAsset 需要 storyboard/audio/video 三种异构子节点同处一个 zone —— 这意味着我们不能字面复用 `buildPhaseTree` 三次(会产出三个 zone,违反 CONTEXT 的「ONE zone」锁定决策),而是要么扩展 `RawArtifact` 接口增加可选 `canvasType` 覆盖(additive,对既有 13 phase 调用者零影响),要么在 `extractShotTimelineArtifacts` 内部实现一个镜像 Zone→Summary→Artifact 结构的并行 tree-builder。两种方案都满足 CONTEXT 的「reuse pattern」要求,planner 取舍见 `## Architecture Patterns`。`fsToOssUrl` (L174-192)、`appendAndSync` (canvasEventStore L203)、`broadcastToProject` 三件套均可直接复用。

前端零改动:`packages/infinite-canvas/src/components/FlowCanvas.tsx:42-64` 的 `nodeTypes` map 已含 `script/asset/storyboard/video/audio/zone/reference + default fallback`,sequence 边由 `packages/infinite-canvas/src/components/edges/CanvasEdge.tsx:60-75` 渲染成蓝色箭头(识别 `data.linkType === 'sequence'`)。CANVAS-03「复用现有 5 渲染器」字面成立 —— 不需要任何 React/components 改动。

**Primary recommendation:** 在 `import-from-dir.ts` 的 `scanWorkdirForArtifacts` 顶部增加 asset.json 早期识别分支(在现有 p0X_*.json 扫描之前 short-circuit),调用新导出的 `extractShotTimelineArtifacts(assetJson, workdir)` helper,该 helper 内部用并行 tree-builder(或扩展后的 buildPhaseTree)产出 1 zone + N storyboard + 3 audio + 1 video + sequence edges 的子图,然后在 `scanAndBuildTree` 把这个子图与现有 13 phase 树合并。配套 `scripts/verify-canvas-shot-timeline.ts` 仿 `verify-import-roundtrip.ts` 模板,直接 import 生产模块的纯函数对 golden fixture 做结构 + schema 双重断言。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 跨仓库执行模型 + 分支策略 (blocker)
- 执行从本仓库 GSD 驱动跨仓库:discuss/plan 在本仓库 `.planning/`(milestone 统一追踪);executor 进 `kais-aigc-platform` 改代码;commits 落在 `kais-aigc-platform` 的 `feat/canvas-asset-collection` 分支
- 干净 worktree:`/data/workspace/kst-canvas-consumer`,从 `origin/master`(`686d526c`)创建的 git worktree,分支 `feat/canvas-asset-collection`
- executor 在该 worktree 内操作;所有 git commit 落在 `feat/canvas-asset-collection`

#### 导入器位置 (CANVAS-01)
- 在 `scanWorkdirForArtifacts`(import-from-dir.ts:996)加一个 ShotTimelineAsset 分支:检测根目录 `asset.json` → 调用新 helper `extractShotTimelineArtifacts(assetJson, workdir)` → 复用既有 `buildPhaseTree`(Zone→Summary→Artifact 模式)+ `appendAndSync`(bootstrap 事件持久化)+ `fsToOssUrl`(媒体 URL 归一化)
- 单一既有入口(`POST /api/canvas/v2/import-from-dir`),最小新增表面积;不新挂路由
- 识别判据:workdir 根存在 `asset.json` 且 `asset_type === "shottimeline"`(schema_version graceful-degrade:未知版本不 reject,warn 后渲染已知部分)

#### Collection → Canvas 节点映射 + Schema 约束 (CANVAS-02, CANVAS-03 核心)
- 结构:ONE `zone` 父节点(`data.label = source.video_filename`,`data.phase` = 选定 phase group)+ 子节点:
  - `storyboard` × N:每镜一个(来自 `shots.json` 的 `{id, start_sec, end_sec, duration}`),携带 `shot_id`、首帧缩略图、`duration_sec`
  - `audio` × 3:每个 stem 一个(vocals/drums/other,来自 `media.stems`),携带 `filePath`、`duration_sec`
  - `video` × 1:master(`media.video` → video.mp4),携带 `filePath`、`duration_sec`
  - transcript/prompts:作为 sidecar description 附挂(不单独建 script/asset 节点 —— 保持节点数克制)
- Schema 字段合成(关键:per-type Zod schemas 要求 asset 不直接携带的字段):
  - `engine = "shot-timeline"`(provenance 标识,所有 audio/video 子节点)
  - `shot_type`:从 `prompts.json` 推断 或默认 `"scene"`(storyboard 子节点)
  - `resolution`:ffprobe 探 `video.mp4` 得到(如 `1920x1080`)(video 子节点)
  - `shot_id`:来自 `shots.json` 的 `id`(storyboard);audio/video 用集合级 sentinel(如 `"collection"` 或 `0`)
  - 不放宽 per-type schemas(CANVAS-03 不 bump contract)—— 用合成值满足,并在节点 `data` 里标注 `__synthetic_fields` 供溯源
- Sequence edges:在 storyboard 子节点之间(按 `shot_id` 升序)emit `data: { linkType: 'sequence' }` 边

#### Phase / Lane 归属 (Claude's discretion,低风险)
- 复用既有 phase group(倾向 `"production"` 或 `"post"/"delivery"`,p11/p12 区),单一 zone 单一 lane。或引入新 phase —— plan 阶段定(低风险、可逆)

#### 验证方法 (CANVAS-01..03, SC)
- Standalone TS verify script:仿 `scripts/verify-import-roundtrip.ts`,喂 golden fixture 进导入器的纯函数(`extractShotTimelineArtifacts` → `buildPhaseTree`),断言:(a) Zone→children 结构正确;(b) 每个 media 子节点通过 `canvasAssetSchema` 对应 per-type Zod(`validateNodeData` 返回 null);(c) sequence edges 存在且按 shot_id 有序。无需起 backend
- Golden fixture:**复制 shot-timeline Phase 2 的 ep01 真实导出资产目录**到 `kais-aigc-platform/scripts/fixtures/shot-timeline-ep01/`
- 媒体文件(video.mp4 + stems/*.wav)也一并复制进 fixture,保证 `fsToOssUrl`/filePath 解析可测

### Claude's Discretion
- `extractShotTimelineArtifacts` 的精确内部结构(如何把 5 个 data JSON 折叠成 RawArtifact[] 喂 buildPhaseTree)
- phase/lane 归属的具体取值(production vs post vs 新 lane)
- 缩略图处理(首帧 base64 内联 vs 落 OSS 临时文件 vs 不显示)—— 受 ZoneNode/StoryboardNode 渲染能力约束,plan 阶段定
- `__synthetic_fields` 溯源标注的精确形态

### Deferred Ideas (OUT OF SCOPE)
- 画布内原生时间轴渲染器(stem 播放引擎、波形 canvas)—— v2 milestone(NATIVE-01/02)
- transcript → script 节点、prompts → asset 节点的细粒度映射 —— 本 phase 保持节点数克制(storyboard/audio/video)
- ShotTimelineAsset 专属 phase lane(p14)—— 本 phase 复用既有 phase group
- 把 ShotTimelineAsset 导入做成画布编排 skill —— ORCH-01
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CANVAS-01 | 画布现有 `import-from-dir` 路径能消费 ShotTimelineAsset,在画布上表示为一个 collection(结构化父节点) | `scanWorkdirForArtifacts` L996 增加 asset.json 早识别分支;新增 `extractShotTimelineArtifacts` 复用 `fsToOssUrl`+`appendAndSync`;不新挂路由(见 `## Architecture Patterns` Pattern 1)。识别判据:根目录有 asset.json 且 `asset_type === "shottimeline"` |
| CANVAS-02 | 用结构化父节点(沿用 `zone`/`phase` 模式,持有子节点 ID)聚合现有 `storyboard`/`audio`/`video` 子节点 | ONE zone node + N storyboard + 3 audio + 1 video children。父子关系靠 `dataType:'output'` 显式边(zone→child)+ 共享 `data.phase`/`phaseIndex`(见 `## Architecture Patterns` Pattern 2)。sequence edges 在 storyboard 子节点之间按 shot_id 升序 emit |
| CANVAS-03 | 复用画布现有 5 个渲染器,不引入 custom renderer / 不 bump contract(receiver schema 已透传 structuralTypes) | `FlowCanvas.tsx:42-64` nodeTypes 已含 storyboard/audio/video/zone;per-type Zod (`assetDataSchemas`) 严格度零改动,合成字段满足 required 列表(见 `## Field Mapping` 表);additive-only 验证:`grep` 确认 packages/infinite-canvas/ 无需任何改动 |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| asset.json 识别 + schema_version graceful-degrade | Backend route (import-from-dir.ts) | — | workdir 是 backend 的输入边界;consumer-side runtime lenience 由 SPEC §4 mandated 在消费端做 |
| 5 数据 JSON 解析 → RawArtifact[] | Backend (新 helper) | — | 纯函数,fs.readFile + JSON.parse;无 DB/IO 副作用,易测 |
| Per-type Zod field 合成 (engine/shot_type/resolution) | Backend helper | — | schema 是 receiver-side 硬约束;合成必须在 persist 之前完成 |
| Sequence edges 构造 | Backend helper | — | 边数据在生产端写死(按 shot_id 排序),消费端 CanvasEdge.tsx 只渲染 |
| ffprobe 探 resolution | Backend (subprocess) | — | 仅 video 子节点需要;ffprobe 在 worktree env 已可用 |
| Media filePath → /oss/ URL 归一化 | Backend (`fsToOssUrl`) | — | 复用既有 helper + 自动 symlink (`scanAndBuildTree` 已做) |
| Bootstrap 事件持久化 | Backend (`appendAndSync`) | — | 复用;前端通过 `graph:saved` WS 重载 |
| 前端渲染 | Frontend (`packages/infinite-canvas/`) | — | 零改动;nodeTypes map + CanvasEdge 已支持所有需要的语义 |
| Verify 断言 | Standalone script (scripts/) | — | tsx + 生产模块 import + fixture,无 DB/HTTP |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `express` | ^5.2.1 (已装) | 既有路由框架 —— Phase 3 不新增 route,只增加分支 | `[VERIFIED: package.json L62]` 唯一 HTTP 框架,零替代 |
| `zod` | ^4 (推断,已装) | asset.json runtime graceful-degrade 解析 + 复用 `assetDataSchemas` 做断言 | `[VERIFIED: canvasAssetSchema.ts:18 import, assetDataSchemas:51]` |
| `tsx` | ^4.21.0 (devDep) | verify script 跑 .ts 直接执行(`npx tsx scripts/verify-*.ts`) | `[VERIFIED: package.json scripts.verify:* + devDependencies.tsx]` 既有 6 个 verify 脚本统一模式 |
| `@xyflow/react` | v12 (推断) | 前端 React Flow —— 既有 nodeTypes/edgeTypes 注册 | `[VERIFIED: FlowCanvas.tsx:7 import @xyflow/react]` 零改动 |
| `knex` + `better-sqlite3` | ^3.2.5 / ^12.9.0 | canvasEventStore 持久化 —— Phase 3 不动 | `[VERIFIED: package.json L83, L57]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `ffprobe` (system binary) | 6.1.1-3ubuntu5 | 探 video.mp4 分辨率,合成 video 子节点 `resolution` 字段 | 仅 video 子节点一次 subprocess 调用;失败可 fallback "0x0" 字符串(Zod 只要 min(1)) |
| `fs/promises` (Node stdlib) | — | readdir/readFile/stat/scratch 写 verify 输出 | 复用 import-from-dir.ts 既有 import |
| `json-schema-to-typescript` | 可选 | 从 spec/schemas/*.json 生成 TS 类型(`Context.discretion`) | 如希望 asset.json 解析有强类型;非必须 —— 当前 fixture 已是 plain JSON |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 在 import-from-dir.ts 加分支 | 新增 `POST /canvas/v2/import-asset` 路由 | CONTEXT 已锁「单一既有入口」—— 新路由被否决 |
| 复用 buildPhaseTree + extension | 全新并行 tree-builder | buildPhaseTree 改动是 1-line additive;并行 builder 是 ~80 行重复代码。前者更小,但侵入既有 helper;后者更隔离。planner 选 |
| tsx 跑 verify | jest/vitest | worktree 无 jest/vitest 配置,6 个既有 verify 脚本都用 tsx —— 沿用一致 |
| ffprobe 子进程 | 用 frontend-zod-extensions 加可选 resolution | Zod 要求 `resolution: z.string().min(1)` —— 必须有非空值。ffprobe 是最权威来源;若省略须合成 "0x0" 占位 |

### Package Legitimacy Audit

> 本 phase **不安装任何新包** —— 全部依赖已在 worktree `package.json` 中。仅做版本与可用性确认。

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| express | npm | 多年 | 极高 | github.com/expressjs/express | (skip) | 既有依赖,无新增 |
| zod | npm | 多年 | 极高 | github.com/colinhacks/zod | (skip) | 既有依赖 |
| tsx | npm | 多年 | 高 | github.com/privatenumber/tsx | (skip) | 既有 devDep |
| @xyflow/react | npm | 多年 | 高 | github.com/xyflow/xyflow | (skip) | 既有依赖 |

**Packages removed due to slopcheck [SLOP] verdict:** none(本 phase 不引新包)
**Packages flagged as suspicious [SUS]:** none

slopcheck 未执行(本 phase 零新包安装,全部依赖已在 worktree `package.json` 验证存在)。

## Architecture Patterns

### System Architecture Diagram

```text
 Producer (本仓库,kais-shot-timeline)           Consumer (worktree,kais-aigc-platform)
 ─────────────────────────────────────           ────────────────────────────────────────
 run_pipeline.py                                                         
   ├─ detect_v3b.py    → shots.json           
   ├─ separate_stems   → audio_analysis.json  
   │                     + stems/htdemucs/…/      ┌──────────────────────────────────┐
   ├─ transcribe.py    → transcript.json         │  POST /api/canvas/v2/import-from-dir │
   ├─ gen_*_html.py    → frames.json      ─────▶ │  (import-from-dir.ts)              │
   └─ export_asset.py  → asset.json + canoni-    │                                    │
                         cal media symlinks      │   1. scanWorkdirForArtifacts()     
                                                 │      └─ NEW: detect asset.json     
                                                 │         → extractShotTimelineArtifacts()
                                                 │                                    │
                                                 │   2. extractShotTimelineArtifacts()
                                                 │      ├─ parse 5 data JSONs         
                                                 │      ├─ ffprobe video.mp4 → res.   
                                                 │      ├─ fsToOssUrl(media paths)    
                                                 │      ├─ build zone + children      
                                                 │      │   (1 zone + N story + 3 aud  
                                                 │      │    + 1 vid, synth fields)    
                                                 │      └─ emit sequence edges        
                                                 │         (storyboard[i]→[i+1])      
                                                 │                                    │
                                                 │   3. appendAndSync(bootstrap)      
                                                 │      → kv_canvasEvent + snapshot   
                                                 │                                    │
                                                 │   4. broadcastToProject('saved')   
                                                 └─────────────┬─────────────────────┬┘
                                                               │                     │
                                                               ▼ WS graph:saved      │ HTTP 200 {imported, links, ...}
                                                 ┌──────────────────────────────────┐
                                                 │ Frontend (零改动)                  │
                                                 │  FlowCanvas.tsx nodeTypes map     │
                                                 │   ├─ ZoneNodeComponent            │
                                                 │   ├─ StoryboardNodeComponent      │
                                                 │   ├─ AudioNodeComponent           │
                                                 │   ├─ VideoNodeComponent           │
                                                 │   └─ CanvasEdgeComponent          │
                                                 │       └─ linkType:'sequence'      │
                                                 │          → 蓝色实线 + 箭头         │
                                                 └──────────────────────────────────┘
```

阅读路径:producer 的 6 个产物(asset.json + 5 数据 JSON + 3 个 stems + 1 个 video)由 backend importer 一次读入 → 在 helper 内折叠成 zone+children 树 → 既有 `appendAndSync` 写入 SQLite + 广播 → 前端通过既有 `loadCanvasGraph` 拉取并用既有 5 个 renderer 渲染。

### Recommended Project Structure (worktree diff)

```text
/data/workspace/kst-canvas-consumer/    # worktree root, branch feat/canvas-asset-collection
├── src/routes/canvas/v2/
│   └── import-from-dir.ts              # MODIFY: scanWorkdirForArtifacts + extractShotTimelineArtifacts (新 export)
├── scripts/
│   ├── verify-canvas-shot-timeline.ts  # NEW: 仿 verify-import-roundtrip.ts 模板
│   └── fixtures/
│       └── shot-timeline-ep01/         # NEW: golden fixture (从本仓库 ep01 复制)
│           ├── asset.json              # manifest
│           ├── shots.json              # 93 shots
│           ├── audio_analysis.json
│           ├── transcript.json
│           ├── frames.json             # ~7MB (base64 内联)
│           ├── prompts.json
│           ├── video.mp4               # 见 Pitfall 4 — fixture size 策略
│           └── stems/{vocals,drums,other}.wav
└── docs/
    └── canvas-import-from-dir.md       # MODIFY: 增 asset.json 识别 section(可选)
```

本仓库(.planning/)侧仅产 RESEARCH/PLAN/VERIFY 文档;代码改动 100% 在 worktree。

### Pattern 1: asset.json 早识别分支(早退 short-circuit)

**What:** 在 `scanWorkdirForArtifacts` 顶部、在既有 `p0X_*.json` 循环之前,先 probe `workdir/asset.json`。命中则走 ShotTimelineAsset 分支,直接返回 single-phase `Map<string, RawArtifact[]>`(key 用选定 phase prefix,例如 `"p13"`)。
**When to use:** 当 workdir 根同时含 asset.json 与 p0X_*.json 时,asset.json 优先(避免误把 ep01 数据当成普通 phase 处理)。
**Why:** `extractShotTimelineArtifacts` 需要直接产出 tree 而非 RawArtifact[](因为异构子节点 + sequence edges,见 Pattern 2),所以最干净的 hook 是绕过 `scanAndBuildTree` 的 `buildPhaseTree` 调用,直接产 `{nodes, links}` 给 `appendAndSync`。

```typescript
// Source: 本仓库 src/routes/canvas/v2/import-from-dir.ts(L996 上下文,新分支为 Phase 3 新增)
// 在 scanWorkdirForArtifacts 开头插入(asset.json 优先于 p0X_*.json):

async function scanWorkdirForArtifacts(workdir: string): Promise<Map<string, RawArtifact[]>> {
  const phaseArtifacts = new Map<string, RawArtifact[]>();
  // ── NEW: Phase 3 — ShotTimelineAsset 早期识别 ─────────────
  const assetManifestPath = join(workdir, "asset.json");
  const manifest = await tryReadJSON(assetManifestPath);
  if (manifest && manifest.asset_type === "shottimeline") {
    // schema_version graceful-degrade:已知版本("1"/"1.x")安静通过;
    // 未知/更新版本 warn + 继续渲染已知部分(SPEC.md §4 mandated consumer runtime lenience)
    if (!["1"].includes(String(manifest.schema_version ?? ""))) {
      console.warn(
        `[v2/import] asset.json schema_version="${manifest.schema_version}" 未知,graceful-degrade 渲染已知字段`,
      );
    }
    // 标记:scanAndBuildTree 检测此 key 时走专用 extractShotTimelineArtifacts 路径,
    // 不进 buildPhaseTree(buildPhaseTree 强制同质 canvasType,见 Pattern 2)
    phaseArtifacts.set("__shot_timeline_asset__", [{
      label: manifest.source?.video_filename ?? "ShotTimelineAsset",
      output_key: "__shot_timeline_asset__",
      extra: { __manifest_path: assetManifestPath, __manifest: manifest },
    }]);
    return phaseArtifacts;
  }
  // ── 既有逻辑 ... ──────────────────────────────────────────
}
```

然后在 `scanAndBuildTree` 增加:

```typescript
// 在 buildPhaseTree 循环之后、return 之前:
const stKey = "__shot_timeline_asset__";
if (phaseArtifacts.has(stKey)) {
  const meta = phaseArtifacts.get(stKey)![0].extra!;
  const sub = await extractShotTimelineArtifacts(meta.__manifest, workdir, meta.__manifest_path);
  allNodes.push(...sub.nodes);
  allLinks.push(...sub.links);
}
```

### Pattern 2: ONE zone × 异构子节点 —— buildPhaseTree 的结构性约束与解法

**What:** `buildPhaseTree` (L592-835) 把同一 phase 下**所有 artifact 的 `type` 强制设为 `def.canvasType` (L802-804: `type: def.canvasType as any`)。ShotTimelineAsset 需要在一个 zone 下混合 storyboard(N)+ audio(3)+ video(1)三种 type,无法直接喂 buildPhaseTree(三种 type 要三个 phase → 三个 zone → 违反 ONE zone 锁定)。

**When to use:** 这是 Phase 3 的核心结构决策。两种解法:

#### 方案 A —— 扩展 RawArtifact + 一行 buildPhaseTree 改动(推荐)

在 `RawArtifact` interface (L237-254) 加可选字段 `canvasType?: string`,在 buildPhaseTree L802 改 `type: (art.canvasType ?? def.canvasType) as any`。既有的 13 phase 调用者**完全不设** `art.canvasType` → 行为零变化。新 helper 设 `canvasType: "storyboard" | "audio" | "video"`。

```typescript
// 1. RawArtifact 扩展(additive,无破坏):
interface RawArtifact {
  label: string;
  output_key: string;
  // ... 既有字段 ...
  /** Phase 3: per-artifact canvasType 覆盖;不设则用 phase 默认 */
  canvasType?: "script" | "asset" | "storyboard" | "audio" | "video";
}

// 2. buildPhaseTree L802 改一行:
const artNode: FlowNodeV2 = {
  id: nodeId,
  type: (art.canvasType ?? def.canvasType) as any,   // ← 改这一行
  // ...
};

// 3. extractShotTimelineArtifacts 直接调用 buildPhaseTree("p13", artifacts):
//    其中 artifacts[] 内每个 RawArtifact 都带 canvasType 字段
```

**优点:** 最小代码改动(1 行 buildPhaseTree + interface 加字段);最大化复用(布局、SCHEMA_ALIASES、EXPECTED_PARAM_FIELDS 检查、E-Konte derivation 全部继承);verify 脚本可以独立测 `extractShotTimelineArtifacts` 和 `buildPhaseTree` 两个 export。
**风险:** buildPhaseTree 是 production hot path —— 但改动是 additive opt-in,既有 13 phase 不设 `canvasType` → 行为不变。

#### 方案 B —— extractShotTimelineArtifacts 内部并行 tree-builder

新 helper 内部完整复制 buildPhaseTree 的 Zone→Summary→Artifact 三级结构 + 布局常量,自己 emit 节点(允许异构 type)。`buildPhaseTree` 完全不动。

**优点:** buildPhaseTree 零侵入;Phase 3 边界完全隔离。
**缺点:** ~80 行代码与 buildPhaseTree 重复(布局常量、zone 节点构造、artifact 循环、E-Konte derivation);未来 buildPhaseTree 改了,这边要手动同步。

**推荐 A。** CONTEXT 写「复用 buildPhaseTree」,方案 A 字面满足;方案 B 是「复用模式但重写实现」语义稍弱。Planner 取舍。

### Pattern 3: Sequence edges 在生产端 emit

**What:** sequence 边在 `CanvasEdge.tsx:60-75` 被识别为蓝色实线 + marker arrow。生产端的边数据形状:`{id, source, target, branchId, dataType, data: {linkType: 'sequence'}}`(`flowDataMapper.ts:170` 既有先例)。
**When to use:** 在 `extractShotTimelineArtifacts` 内,所有 storyboard 节点构造完后,按 `shot_id` 升序遍历,相邻两个 emit 一条边。
**Where to hook:** helper 内、return `{nodes, links}` 之前。
**Why:** import-from-dir 现有的 artifact 分支不 emit sequence 边(`buildPhaseTree` 不做、`buildCrossReferenceLinks` 只做 `dataType:'reference'`)。Phase 3 是首次在生产端写 sequence 边。

```typescript
// 在 extractShotTimelineArtifacts 内,storyboard 节点构造完后:
const sortedSb = storyboardNodes.sort((a, b) =>
  Number(a.data.shot_id) - Number(b.data.shot_id)
);
for (let i = 1; i < sortedSb.length; i++) {
  sequenceLinks.push({
    id: `seq-${sortedSb[i - 1].id}-${sortedSb[i].id}`,
    source: sortedSb[i - 1].id,
    target: sortedSb[i].id,
    branchId: "main",
    dataType: "data",
    data: { linkType: "sequence" },   // ← CanvasEdge.tsx:60 识别此字段
  } as FlowLinkV2);
}
```

### Pattern 4: schema_version graceful-degrade runtime 实现

**What:** SPEC §4 + asset.schema.json#schema_version.description mandate 消费端「未知版本 warn + 渲染已知 + 不 reject」。这是 runtime behavior,schema 本身保持严格(`additionalProperties:false`)。
**When to use:** helper 读 asset.json 时,检查 `schema_version` 字段。
**Why:** CONTEXT 写「schema_version graceful-degrade」是 Phase 3 的明确要求。

实现:由于本 phase 仅处理 schema_version="1",且 asset.json schema 严格(`additionalProperties:false` 在每层),unknown-field-ignore 实际上对本 phase 无操作(没有 unknown 字段)。**实际只需做 warn**:

```typescript
const KNOWN_VERSIONS = new Set(["1"]);
if (!KNOWN_VERSIONS.has(String(manifest?.schema_version ?? ""))) {
  console.warn(
    `[v2/import] ShotTimelineAsset schema_version="${manifest.schema_version}" not in known set ${[...KNOWN_VERSIONS].join("/")}; rendering known fields only (SPEC §4 graceful-degrade)`,
  );
}
// 继续:不 throw,用 manifest.source/data/media 渲染
```

未来 major bump(如 "2")时,如果字段重命名,本 helper 需在此处加版本分支处理;SPEC.md §4 已规定迁移须在 changelog 文档化。本 phase 不预设。

### Anti-Patterns to Avoid

- **在 packages/infinite-canvas/ 改任何文件** —— 违反 CANVAS-03「复用现有 5 渲染器」+ STATE.md `additive-only` 不变量。verify 脚本应断言 `git diff --name-only origin/master..HEAD -- packages/infinite-canvas/` 输出为空。
- **放宽 assetDataSchemas 任一 Zod 字段** —— CONTEXT 明确「不 bump contract」。`resolution: z.string().min(1)` 不可改 optional,只能用合成 `"0x0"` 或 ffprobe 真值满足。
- **把 transcript/prompts 建独立 script/asset 节点** —— CONTEXT 明确「保持节点数克制,作为 sidecar description 附挂」。增加节点数会让画布拥挤且无信息增益。
- **在 helper 内调用 DB / `appendAndSync`** —— helper 应是纯函数(fs + JSON + subprocess),持久化由 `scanAndBuildTree` 既有流程做,便于 verify。
- **多 zone 拆分** —— 「ONE zone 父节点」是 CONTEXT 硬锁定。即便子节点 type 异构,也要同处一个 zone(用 Pattern 2 方案 A 解决)。

## Field Mapping (R2 答案)

per-type Zod required 字段 → ShotTimelineAsset 数据源 完整对照:

| Node type | Zod required field | Data source (ShotTimelineAsset) | Synth? | Notes |
|-----------|-------------------|--------------------------------|--------|-------|
| **zone** | (无,structuralType pass-through) | — | — | `structuralTypes` set 在 canvasAssetSchema.ts:122 含 `"zone"`,`validateNodeData` 直接返回 null |
| **storyboard** | `label` | 合成 `"Shot ${shot.id}"` | ✓ | 也可附 prompts.json 的 `subject` 做 subtitle |
| storyboard | `shot_id` | `String(shot.id)` (来自 shots.json) | partial | Zod 是 `z.string().min(1)`,需 stringify 1-based int |
| storyboard | `shot_type` | 合成 `"scene"`(默认) 或 prompts.json 关键词推断 | ✓ | CONTEXT 锁默认 `"scene"`;Zod 是 `z.string().min(1)` 不限枚举;frontend `NODE_SCHEMA.storyboard` 没有 shot_type 字段(只有 framing/cameraMovement),所以任何非空字符串都能渲染 |
| storyboard | `duration_sec` | `shot.duration` (来自 shots.json) | partial | Zod `z.number().positive()`;直接 float |
| storyboard | `filePath` | (optional storyboard schema) | — | 不强制;若有可塞 frames.json 的 first_frame data URI(但 data URI 不是真路径);建议**不设**,让 StoryboardNode 走 thumbnailUrl 分支 |
| storyboard | `thumbnailUrl` (渲染用) | `frames.json[id-1].first_frame` (base64 data URI) | partial | 直接内联 data URI 进 `data.thumbnailUrl`;StoryboardNode.tsx:74-75 识别此字段渲染 `<img>`;不经 fsToOssUrl |
| **audio** | `filePath` | `fsToOssUrl(join(workdir, "stems", "<stem>.wav"))` | partial | 三个 stem 各一条;fsToOssUrl 自动 symlink 到 data/oss/ |
| audio | `shot_id` | 合成 `"collection"` | ✓ | CONTEXT 接受 sentinel;集合级 |
| audio | `engine` | 合成 `"shot-timeline"` | ✓ | provenance 标识;不在前端 AUDIO_METADATA_LABELS.engine 枚举里,但 Zod 不限枚举 |
| audio | `duration_sec` | `asset.source.duration_sec` | partial | 集合级;同一时长三个 stem |
| **video** | `filePath` | `fsToOssUrl(join(workdir, "video.mp4"))` | partial | master 视频一条 |
| video | `shot_id` | 合成 `"collection"` | ✓ | 同 audio |
| video | `engine` | 合成 `"shot-timeline"` | ✓ | 同 audio |
| video | `duration_sec` | `asset.source.duration_sec` | partial | 来自 manifest |
| video | `resolution` | `ffprobe(video.mp4)` → `"${w}x${h}"` | ✓ synth | 见 Don't Hand-Roll;失败 fallback `"0x0"` |
| video | `thumbnailUrl` (渲染用) | (可选)合成 ffmpeg 抽首帧 → fsToOssUrl;或不设让 VideoNode 走 inline 播放 | optional | 建议先不设,前端 VideoNode 会用 video 元素自带首帧 |

**`__synthetic_fields` 标注(Claude's discretion):** 在每个合成字段所在的节点 `data` 上加:
```typescript
data.__synthetic_fields = ["engine", "shot_type"];  // 或 ["engine", "resolution", "shot_id"]
```
便于后续 traceability(Phase 4 VERIFY-02 也可断言此字段存在)。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| video resolution 探测 | 自己写 mp4 header parser 或用 ffmpeg pipe | `subprocess.run(["ffprobe","-v","quiet","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x", videoPath])` | `[VERIFIED: CLAUDE.md Key Dependencies "ffprobe 6.1.1"]` + worktree env 实测可用;mp4 box parser 是出了名的易错 |
| media URL → /oss/ URL 归一化 | 自己拼字符串 + symlink | `fsToOssUrl` (import-from-dir.ts:174) + `scanAndBuildTree` 已建 `data/oss/{basename} → workdir` symlink | 复用,且 symlink 是 backend HTTP server `/oss/...` 静态服务的契约 |
| Zod schema validation | 手写 if/else 字段检查 | `validateNodeData(nodeType, data)` (canvasAssetSchema.ts:133) | 已有 6 个 phase 的 verify 脚本都用它 |
| bootstrap 事件持久化 | 自己写 SQLite UPSERT | `appendAndSync({projectId, episodesId, clientId, source, events: [{type:"bootstrap", payload:{graph}}]})` (canvasEventStore.ts:203) | 已是 production 唯一持久化路径,含 dedup + recompute |
| sequence 边形状 | 自定义 edge 字段 | `{source, target, branchId:"main", dataType:"data", data:{linkType:"sequence"}}` | CanvasEdge.tsx:60 严格识别 `data.linkType === 'sequence'`;flowDataMapper.ts:170 既有先例 |
| FlowGraphV2 schema check | 手写节点/边字段检查 | `FlowGraphV2Schema.safeParse(graph)` (flowgraph-v2-schema.ts:102) | save-v2.ts:36 已用同一 schema,提前在 helper 内测可早发现 shape 错误 |

**Key insight:** 这个 phase 的全部复杂度在「字段合成」和「reuse vs parallel-build 决策」,不在「实现新基础设施」。任何「我需要一个新的 DB 表 / 一个新 route / 一个新前端 component / 一个新 Zod schema」都是 anti-pattern 信号。

## Runtime State Inventory

> 本 phase 是 cross-repo 新增(producer 侧零代码改动,consumer 侧 helper + fixture 新增)。不存在 rename/refactor/migration 触发条件,但仍按 5 类核对:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — worktree 是干净 checkout(HEAD 686d526c,git status clean `[VERIFIED: git status in worktree]`)。无生产 DB 数据引用即将引入的 helper | None |
| Live service config | None — 无 n8n/Datadog/Tailscale 等外部服务引用 import-from-dir 的内部函数 | None |
| OS-registered state | None — 无 systemd/pm2/launchd 注册 | None |
| Secrets/env vars | None — import-from-dir.ts 不读任何 env var;verify 脚本可选读 `KAIS_HERMES_SKILLS_PATH`(已有,非新增)| None |
| Build artifacts | None — worktree `node_modules/` 缺失(worktree 是 fresh checkout);executor 须先 `yarn install` 才能跑 `npx tsx` | Wave 0 加 `yarn install` 步骤(见 Validation Architecture) |

**The canonical question** 「After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?」—— 本 phase 是纯新增,不替换任何字符串,故所有类别都是 "Nothing found"。已逐项 explicit 答复。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ffprobe` (system) | video 子节点 resolution 合成 | ✓ | 6.1.1-3ubuntu5 | 合成 `"0x0"`(Zod `min(1)` 通过,frontend VIDEO_METADATA_LABELS.resolution 没有 "0x0" 标签但 fallback 显示原值) |
| `tsx` (devDep) | verify script 执行 | ✓(主仓 `/data/workspace/kais-aigc-platform/node_modules/.bin/tsx` 存在)| ^4.21.0 | worktree 无 node_modules → `yarn install` 后可用;或临时用主仓 node_modules |
| `yarn` | 装依赖 | ✓ | 1.22.22 | — |
| Node.js | TS 编译 + 跑 tsx | ✓ | v24.13.0 (nvm) | — |
| `data/oss/` 写权限 | fsToOssUrl 自动 symlink | ✓(worktree 在 `/data/workspace/kst-canvas-consumer`,symlink target 是 `data/oss/`)| — | symlink 创建失败已被既有 import-from-dir.ts:1354 catch 为 non-fatal warn |
| `git` (worktree commits) | 落 feat/canvas-asset-collection | ✓ | user `kaiger666888@gmail.com` 已配 `[VERIFIED: git config in worktree]` | — |
| Producer ep01 真实资产(golden fixture 源) | 复制到 consumer worktree | ✓ | `/data/workspace/kais-shot-timeline/output/虫虫武侠…/` 648MB(数据 JSON + video.mp4 + stems/)| 数据 JSON 直接复制;媒体须 downsample(见 Pitfall 4) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None(全部可用)。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Node.js + `npx tsx` 直接执行 .ts(无 jest/vitest)—— 沿用 worktree 既有 6 个 verify 脚本模式 `[VERIFIED: package.json scripts.verify:*]` |
| Config file | 无(每个 verify 脚本自带 `assert` + `process.exit`) |
| Quick run command | `npx tsx scripts/verify-canvas-shot-timeline.ts`(worktree cwd) |
| Full suite command | 同上(本 phase 单一 verify 脚本;既有 `npm run verify:phase-46-contracts` 不受影响) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CANVAS-01 | asset.json 识别分支触发 + 走 extractShotTimelineArtifacts 而非 buildPhaseTree | unit | `npx tsx scripts/verify-canvas-shot-timeline.ts` (assert A: fixture 路径下识别为 ShotTimelineAsset,产出节点数 = 1 zone + 1 summary + N+4 media children) | ❌ Wave 0 新建 |
| CANVAS-02 | Zone→children 结构正确(1 zone,N storyboard,3 audio,1 video)+ sequence edges 按 shot_id 有序 | unit | 同上 (assert B: counts; assert C: sequence edges length = N-1,且 source/target shot_id 单调递增) | ❌ Wave 0 |
| CANVAS-03 | 每个子节点通过 per-type Zod (`validateNodeData` 返回 null)+ additive-only 断言 | unit | 同上 (assert D: `validateGraphNodes(allNodes).length === 0`;assert E: 仓库 diff `packages/infinite-canvas/` 为空 + canvasAssetSchema.ts 严格度未改)| ❌ Wave 0 |
| Roundtrip (Phase 4 预留) | asset.json manifest 字段 survive 进 node.data(video_filename → zone label;duration_sec → audio/video duration_sec) | unit | 同上 (assert F: spot-check 字段映射) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `npx tsx scripts/verify-canvas-shot-timeline.ts`(单次 < 5s,fixture 内联)
- **Per wave merge:** 同上 + 既有 `npm run verify:phase-46-contracts`(回归保护,确保未破坏 13 phase 既有逻辑)
- **Phase gate:** 全绿后方可 `/gsd:verify-work`;Phase 4 VERIFY-01 用同一 fixture 做端到端

### Wave 0 Gaps
- [ ] `scripts/verify-canvas-shot-timeline.ts` —— 新建 verify 脚本,覆盖 REQ CANVAS-01/02/03 + roundtrip spot-check
- [ ] `scripts/fixtures/shot-timeline-ep01/` —— 新建 fixture 目录,内容来自本仓库 ep01(媒体 downsample,见 Pitfall 4)
- [ ] `yarn install` —— Wave 0 必跑(worktree fresh checkout,node_modules 缺失)
- [ ] helper export 决策:`extractShotTimelineArtifacts` 必须 export(verify script 要 import);如选 Pattern 2 方案 A,buildPhaseTree 也需 export(目前只有 `flattenParamsToNodeData` 是 export `[VERIFIED: import-from-dir.ts:31]`)

*(无既有 test/config 文件需要改 —— 本 phase 全新增)*

## Security Domain

> `security_enforcement` 未在 .planning/config.json 显式设(false 也未设),按 absent=enabled 应纳入。但本 phase 的「attack surface」极窄:不接 user-supplied HTTP body(复用既有 validateFields),不直接读 network,只读 workdir 文件系统。仍按 ASVS 对照如下:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 复用既有 route-level auth middleware;Phase 3 不动 auth |
| V3 Session Management | no | 同上 |
| V4 Access Control | no | 同上 |
| V5 Input Validation | yes | asset.json 用 zod graceful-degrade 解析;所有外溢字段必须经 `tryReadJSON`(已 catch+null);媒体文件名直接来自 asset.json#media 路径,须防 path traversal —— **asset.json schema 已用 `^(?!.*\.\.)` pattern 拒绝父目录穿越** `[CITED: spec/schemas/asset.schema.json L99,L110,L115,L120]`,consumer 侧再次 join(workdir, ...) 时 schema 保证安全 |
| V6 Cryptography | no | 无 crypto 操作 |
| V7 Error Handling | yes | ffprobe 失败 / JSON parse 失败 / 文件缺失须 graceful —— 既有 tryReadJSON 已是 catch-null 模式,沿用 |
| V8 Data Protection | no | 不写 secrets |
| V9 Communications | no | WS broadcast 复用既有 |
| V12 Files & Resources | yes | **路径穿越防护见 V5**;媒体文件读取限于 workdir 子树 |

### Known Threat Patterns for cross-repo importer extension

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via malicious asset.json#media path | Tampering | schema `^(?!.*\.\.)` 拒绝;consumer 再 `join(workdir, rel)` 后 `fs.realpath()` 检查结果仍在 workdir 内(建议 additive check) |
| Zip-bomb / huge frames.json OOM | Denial of Service | frames.json 是 producer 自产,fixture ep01 = 7.25MB(可接受);若未来接受第三方 asset,加 `tryReadJSON` 大小上限(本 phase 不做) |
| ffprobe 注入(恶意 video.mp4 文件名) | Tampering | ffprobe 子进程 args 数组传递(无 shell);video.mp4 路径来自 schema-validated asset.json |
| Symlink attack on data/oss/ | Tampering | import-from-dir.ts:1340-1352 已检查 symlink target 一致性 + 失败 non-fatal warn;Phase 3 复用,无新增 |

## Code Examples

### 示例 1: extractShotTimelineArtifacts 骨架(方案 A:扩展 RawArtifact)

```typescript
// Source: 新增于 src/routes/canvas/v2/import-from-dir.ts(末尾),仿既有 buildPhaseTree 结构
// 完整生产实现细节由 plan/execute 阶段定,此处只示 field-mapping + sequence edges 骨架

export async function extractShotTimelineArtifacts(
  manifest: any,                       // 已 parse 的 asset.json
  workdir: string,
  manifestPath: string,
): Promise<{ nodes: FlowNodeV2[]; links: FlowLinkV2[] }> {
  const KNOWN_VERSIONS = new Set(["1"]);
  if (!KNOWN_VERSIONS.has(String(manifest?.schema_version ?? ""))) {
    console.warn(`[v2/import] ShotTimelineAsset schema_version="${manifest.schema_version}" not known — graceful-degrade`);
  }

  // 1. 读 5 个数据 JSON(并行)
  const [shots, audioAnalysis, transcript, frames, prompts] = await Promise.all([
    tryReadJSON(join(workdir, manifest.data.shots)),
    tryReadJSON(join(workdir, manifest.data.audio_analysis)),
    tryReadJSON(join(workdir, manifest.data.transcript)),
    tryReadJSON(join(workdir, manifest.data.frames)),
    tryReadJSON(join(workdir, manifest.data.prompts)),
  ]);

  // 2. ffprobe video.mp4 拿 resolution
  const videoPath = join(workdir, manifest.media.video);
  const resolution = await probeResolution(videoPath);  // "1920x1080" 或 "0x0"

  // 3. 构造 RawArtifact[] —— 异构 canvasType(方案 A 的关键)
  const phasePrefix = "p13";  // 或 "p11" —— planner 决策(见 Discretion)
  const artifacts: RawArtifact[] = [];

  // storyboard × N
  const framesById = new Map((frames ?? []).map((f: any) => [f.id, f]));
  for (const shot of shots ?? []) {
    artifacts.push({
      label: `Shot ${shot.id}`,
      output_key: "storyboard",
      canvasType: "storyboard",   // ← 方案 A 关键:覆盖 phase 默认
      thumbnailUrl: framesById.get(shot.id)?.first_frame,  // base64 data URI 直传
      extra: {
        shot_id: String(shot.id),
        shot_type: "scene",        // CONTEXT 默认;可选用 prompts 关键词覆盖
        duration_sec: shot.duration,
        __synthetic_fields: ["shot_type"],
      },
    });
  }

  // audio × 3
  const duration = manifest.source.duration_sec;
  for (const stem of ["vocals", "drums", "other"] as const) {
    const stemPath = join(workdir, manifest.media.stems[stem]);
    artifacts.push({
      label: `${stem} stem`,
      output_key: "audio",
      canvasType: "audio",
      filePath: fsToOssUrl(stemPath) ?? stemPath,
      extra: {
        shot_id: "collection",
        engine: "shot-timeline",
        duration_sec: duration,
        __synthetic_fields: ["shot_id", "engine"],
      },
    });
  }

  // video × 1
  artifacts.push({
    label: manifest.source.video_filename,
    output_key: "video",
    canvasType: "video",
    filePath: fsToOssUrl(videoPath) ?? videoPath,
    extra: {
      shot_id: "collection",
      engine: "shot-timeline",
      duration_sec: duration,
      resolution,
      __synthetic_fields: ["shot_id", "engine", "resolution"],
    },
  });

  // 4. 调用扩展后的 buildPhaseTree(产出 zone + summary + artifact 三级 + zone→child 边)
  const tree = buildPhaseTree(phasePrefix, artifacts);

  // 5. 在 storyboard 子节点之间 emit sequence edges(按 shot_id 升序)
  const sequenceLinks: FlowLinkV2[] = [];
  const sbNodes = tree.artifactNodes
    .filter((n) => n.type === "storyboard")
    .sort((a, b) => Number((a.data as any).shot_id) - Number((b.data as any).shot_id));
  for (let i = 1; i < sbNodes.length; i++) {
    sequenceLinks.push({
      id: `seq-${sbNodes[i - 1].id}-${sbNodes[i].id}`,
      source: sbNodes[i - 1].id,
      target: sbNodes[i].id,
      branchId: "main",
      dataType: "data",
      data: { linkType: "sequence" },
    } as FlowLinkV2);
  }

  return {
    nodes: [tree.zoneNode, tree.summaryNode, ...tree.artifactNodes],
    links: [...tree.links, ...sequenceLinks],
  };
}

async function probeResolution(videoPath: string): Promise<string> {
  try {
    const { execFile } = await import("child_process");
    const { promisify } = await import("util");
    const execFileP = promisify(execFile);
    const { stdout } = await execFileP("ffprobe", [
      "-v", "quiet", "-select_streams", "v:0",
      "-show_entries", "stream=width,height",
      "-of", "csv=p=0:s=x", videoPath,
    ]);
    return stdout.trim() || "0x0";
  } catch {
    return "0x0";   // Zod min(1) 仍通过;frontend 会显示原值
  }
}
```

### 示例 2: verify 脚本骨架(仿 verify-import-roundtrip.ts)

```typescript
// Source: 新增于 scripts/verify-canvas-shot-timeline.ts
// 模板源:scripts/verify-import-roundtrip.ts(L1-141 完整结构)
#!/usr/bin/env tsx
import fs from "node:fs";
import path from "node:path";
import { extractShotTimelineArtifacts } from "../src/routes/canvas/v2/import-from-dir";
import { validateGraphNodes } from "../src/lib/canvasAssetSchema";

const results: Array<{name:string; pass:boolean; detail?:string}> = [];
function assert(cond: boolean, name: string, detail?: string) {
  results.push({ name, pass: cond, detail });
  console.log(`  ${cond ? "PASS" : "FAIL"}: ${name}${detail ? " — " + detail : ""}`);
}

const FIXTURE = path.resolve(__dirname, "fixtures/shot-timeline-ep01");

async function main() {
  console.log("=== Phase 3 verify-canvas-shot-timeline ===\n");
  const manifest = JSON.parse(fs.readFileSync(path.join(FIXTURE, "asset.json"), "utf8"));
  const { nodes, links } = await extractShotTimelineArtifacts(manifest, FIXTURE, path.join(FIXTURE, "asset.json"));

  // CANVAS-01: 结构 = 1 zone + 1 summary + N+4 children
  const zones = nodes.filter((n) => n.type === "zone");
  const summaries = nodes.filter((n) => n.id.startsWith("sum-"));
  const storyboards = nodes.filter((n) => n.type === "storyboard");
  const audios = nodes.filter((n) => n.type === "audio");
  const videos = nodes.filter((n) => n.type === "video");
  assert(zones.length === 1, "CANVAS-01: exactly 1 zone node");
  assert(summaries.length === 1, "CANVAS-01: exactly 1 summary node");
  assert(audios.length === 3, "CANVAS-01: exactly 3 audio children (vocals/drums/other)");
  assert(videos.length === 1, "CANVAS-01: exactly 1 video child");
  assert(storyboards.length > 0, `CANVAS-01: ≥1 storyboard child (ep01 = 93)`);

  // CANVAS-02: sequence edges 按 shot_id 升序
  const seqEdges = links.filter((l: any) => l.data?.linkType === "sequence");
  assert(seqEdges.length === storyboards.length - 1,
    `CANVAS-02: ${storyboards.length - 1} sequence edges (got ${seqEdges.length})`);
  // (省略单调性断言细节)

  // CANVAS-03: per-type Zod 全过 + additive-only
  const validationErrors = validateGraphNodes(nodes as any);
  assert(validationErrors.length === 0,
    `CANVAS-03: all nodes pass per-type Zod (validateGraphNodes returns 0 errors)`,
    validationErrors.map((e: any) => `${e.nodeId}: ${e.errors}`).join(" | "));

  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => { console.error(err); process.exit(1); });
```

### 示例 3: additive-only 守门断言(进 verify 脚本或独立 check)

```typescript
// Source: 新增 —— 确保 CANVAS-03 字面成立(packages/infinite-canvas/ 零改动)
import { execSync } from "node:child_process";

// 在 worktree cwd 下跑:
const diff = execSync(
  `git diff --name-only origin/master..HEAD -- packages/infinite-canvas/`,
  { cwd: "/data/workspace/kst-canvas-consumer", encoding: "utf8" },
).trim();
assert(diff === "", "CANVAS-03 additive-only: packages/infinite-canvas/ diff is empty", diff || "(empty)");

const schemaDiff = execSync(
  `git diff origin/master..HEAD -- src/lib/canvasAssetSchema.ts`,
  { cwd: "/data/workspace/kst-canvas-consumer", encoding: "utf8" },
).trim();
// 允许 0 字符差异 OR 仅注释/格式改动(不允许 Zod 严格度放宽)
assert(!/\.optional\(\)/.test(schemaDiff.replace(/\/\/.*$/gm, "")),
  "CANVAS-03: no new .optional() added to canvasAssetSchema.ts (strictness preserved)");
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 旧 flat-file node approach | Zone→Summary→Artifact 三级树(canvas_sync.py) | Phase 37 | import-from-dir.ts 已用此模式;Phase 3 沿用 |
| event-sourcing(appendAndSync + reducer replay) | 直接 relational UPSERT(saveFullGraph) | Phase 41 | save-v2.ts 已迁;import-from-dir.ts **仍用 appendAndSync** 路径(bootstrap 事件)—— 不变 |
| 单画布脚本节点驱动 | 5 个 typed renderers + structural zone | Phase 32 | FlowCanvas.tsx nodeTypes map;Phase 3 直接复用 |
| 仅 dataType:'data'/'reference' 边 | 加 `linkType:'sequence'/'parallel'/'reference'` 语义边 | Phase 35 (CANVAS-02) | CanvasEdge.tsx 识别;flowDataMapper.ts:170 既有 emit 模式 |

**Deprecated/outdated:**
- `awaiting_audit` review status(已被 `pending` 替代,flowDataMapper.ts:340 临时兼容层)—— Phase 3 不用
- `flattenParamsToNodeData` 仅用于既有 p0X manifest 的 `params.*` flatten;Phase 3 ShotTimelineAsset 不走此路(直接构造 art.extra)

## Assumptions Log

> 所有 `[ASSUMED]` claims 汇总。Planner 与 discuss-phase 用此识别需用户确认的决策。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | phase prefix 选 `p13`(delivery)/`p11`(video render)/`p12`(composite)三者之一,Claude's discretion | User Constraints + Pattern 1 | 低:可逆(改 phasePrefix 即可);影响 zone label 与 lane 位置 |
| A2 | sequence edges 用 `data:{linkType:'sequence'}` 字面形状,与 flowDataMapper.ts:170 既有先例一致 | Pattern 3 | 低:既有渲染管线已识别;CanvasEdge.tsx:60 hard-coded |
| A3 | video resolution 失败时 fallback `"0x0"` 满足 Zod `z.string().min(1)` | Field Mapping | 极低:Zod 不限枚举;frontend 显示原值 |
| A4 | frames.json base64 data URI 可直接进 `data.thumbnailUrl` 不经 fsToOssUrl | Field Mapping + Code Example 1 | 低:StoryboardNode.tsx:74-75 直接 `<img src={thumbnailUrl}>` 接受 data URI;但 Node 美观度可能因 base64 长度受影响 |
| A5 | producer ep01 真实资产可被 downsample 进 fixture 而保留 verify 价值 | Pitfall 4 + Validation Architecture | 中:downsample 策略由 planner 定;若用户坚持原尺寸,fixture 648MB 进 git 不可行(LFS/submodule 须评估) |
| A6 | schema_version graceful-degrade 在 Phase 3 只做 warn(无 unknown field 需忽略,因 schema additionalProperties:false 已强制 producer 不写多余字段)| Pattern 4 | 极低:本 phase 仅处理 version="1";future major bump 时此 helper 需扩展 |
| A7 | 工作目录的 `data/oss/{basename}` symlink 在测试环境可写 | Environment Availability | 低:既有 import-from-dir.ts:1354 已 catch non-fatal;verify 脚本若 e2e 跑须确保可写,但纯函数测试不需要 |

**Overall confidence:** HIGH —— 大部分关键 claims 已 `[VERIFIED]` 或 `[CITED]`;只有 A5(fixture size 策略)有中等 risk。

## Open Questions (RESOLVED)

> All 4 questions resolved during planning — the plan implements recommendations 1–3 verbatim; recommendation 4 (sidecar attachment) is deferred with justification (see plan 03-01 Task 2 `<done>` D3 note). Resolution markers added post plan-checker (doc-format fix, no content change).

1. **Pattern 2 方案 A vs B —— planner 取舍**
   - What we know: 两种都能 work;方案 A 改 1 行 buildPhaseTree,方案 B 加 ~80 行并行 builder
   - What's unclear: 用户对「修改既有 production hot path」的容忍度
   - Recommendation: **方案 A** —— buildPhaseTree 改动是 additive opt-in(既有 13 phase 不设 canvasType → 零行为变化),且复用最大化。Planner 可在 plan 中明确「方案 A,失败回退方案 B」。
   - RESOLVED: Plan 03-01 选方案 A(RawArtifact.canvasType 可选字段 + buildPhaseTree L804 `(art.canvasType ?? def.canvasType)` 单行覆盖)。

2. **phase prefix 选 p11 vs p12 vs p13**
   - What we know: 三者都是 phaseGroup="post";canvasType 都是 "video"(zone 用 canvasType 不重要,structural pass-through)
   - What's unclear: 哪个 lane label 语义最贴近「逆向解构的成片」
   - Recommendation: **p13(delivery)** —— master video 是已交付的 artifact;lane label 「P13 · 交付」语义最贴。低风险可逆。
   - RESOLVED: Plan 03-01 选 p13。

3. **fixture 媒体 downsample 策略**
   - What we know: ep01 全量 648MB(stems 208MB + video 46MB + frames.json 7MB + 其它);进 git 不现实
   - What's unclear: 用户接受何种替代 —— (a)ffmpeg 生成 1s silent stub;(b)只复制数据 JSON + 文件名占位 stub;(c)git LFS 引入
   - Recommendation: **(a) ffmpeg 生成 1s silent stub** —— 保留 fsToOssUrl/ffprobe 可测性,fixture < 10MB。Planner 在 Wave 0 加 stub 生成步骤。或更激进:**fixture 完全不带媒体**,在 helper 内 monkey-patch fsToOssUrl 用于 verify。
   - RESOLVED: Plan 03-01 Task 1 用 ffmpeg 生成 1s silent stub + 复制真实数据 JSON。

4. **transcript/prompts 作为 sidecar description 的具体 attach 形态**
   - What we know: CONTEXT 说「不单独建 script/asset 节点」;附挂在哪个节点的 data 上未定
   - What's unclear: 挂在 zone.data.description?还是每个 storyboard 的 prompt 来自 prompts.json[shot_id-1]?还是单独 transcript.json 全文挂 video 节点?
   - Recommendation: storyboard 节点附 prompts.json 对应 shot 的 `prompt_text`(提升单镜信息密度);video 节点附 transcript.json 全文(对白与 master 视频关联);zone 节点附 asset.generator.tool/version 来源信息。Planner 细化。
   - RESOLVED (deferred): 本 phase 显式延后次要 sidecar 附挂(CANVAS-01/02/03 SC 不要求);prompts/transcript 仍保留在 fixture asset.json data 引用里。见 plan 03-01 Task 2 `<done>` D3 deferral note。

## Sources

### Primary (HIGH confidence)
- **本仓库 producer side:**
  - `spec/SPEC.md` L1-455 —— 完整 ShotTimelineAsset contract(逐字对照 graceful-degrade 规则)
  - `spec/schemas/asset.schema.json` L1-128 —— manifest 机器可校验权威源
  - `output/虫虫武侠…/asset.json` —— 真实 ep01 manifest(schema_version="1", 5 data paths, 3 stems, 1 video)
  - `.planning/phases/03-canvas-consumer/03-CONTEXT.md` —— 用户锁定决策与 discretion 范围

- **consumer worktree(HEAD 686d526c = origin/master,git status clean):**
  - `src/routes/canvas/v2/import-from-dir.ts` L1-1502 —— 完整 importer 实现(scanWorkdirForArtifacts L996, buildPhaseTree L592, fsToOssUrl L174, appendAndSync 调用 L1393/1465)
  - `src/lib/canvasAssetSchema.ts` L1-205 —— per-type Zod + structuralTypes + validateNodeData + EXPECTED_PARAM_FIELDS_BY_TYPE
  - `src/types/flowgraph-v2-schema.ts` L1-109 —— NodeTypeSchema + FlowNodeV2Schema + FlowLinkV2Schema
  - `src/lib/canvasEventStore.ts` L1-219 —— appendAndSync / ensureBootstrap / loadGraph
  - `src/routes/canvas/v2/save-v2.ts` L1-79 —— validateGraphNodes → HTTP 400 路径
  - `src/routes/canvas/v2/load-v2.ts` L1-119 —— rowToNode/rowToLink 字段映射
  - `packages/infinite-canvas/src/components/FlowCanvas.tsx` L42-64 —— nodeTypes map(5 renderer + zone + Fallback)
  - `packages/infinite-canvas/src/components/edges/CanvasEdge.tsx` L60-75 —— sequence 蓝色箭头
  - `packages/infinite-canvas/src/utils/flowDataMapper.ts` L140-180, L332-394 —— sequence edge 既有先例 + flowGraphToCanvas 映射
  - `packages/infinite-canvas/src/utils/autoLayout.ts` L92-100 —— zone wrapping by data.phase
  - `packages/infinite-canvas/src/constants.ts` L51-175 —— METADATA_LABELS 枚举(确认 shot_type 不在 NODE_SCHEMA,只有 framing)
  - `scripts/verify-import-roundtrip.ts` L1-141 —— verify 脚本模板
  - `package.json` —— scripts.verify:* 模式 + tsx/typescript versions + better-sqlite3/knex
  - `docs/canvas-import-from-dir.md` —— 既有 endpoint doc

### Secondary (MEDIUM confidence)
- worktree env 实测:`ffprobe --version` = 6.1.1-3ubuntu5,`/data/workspace/kais-aigc-platform/node_modules/.bin/tsx` 存在,worktree 自身 node_modules 缺失(须 yarn install)
- worktree git status:clean,HEAD 686d526c,与 CONTEXT.md 锁定的 origin/master 一致

### Tertiary (LOW confidence)
- 无 —— 所有 claims 均来自 Primary 源 或 worktree 实测

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH —— 全部依赖已在 worktree `package.json` `[VERIFIED]`;零新包
- Architecture: HIGH —— 两仓库代码完整读过;buildPhaseTree 的同质约束是 `grep` 验证的(L802 `type: def.canvasType as any`)
- Field mapping: HIGH —— per-type Zod required 字段逐字对照;5 数据 JSON shape 已用 ep01 真实数据验证(93 shots, 155 segments, 7MB frames.json)
- Pitfalls: HIGH —— 全部来自代码读 + 真实 ep01 数据测
- Verify infrastructure: HIGH —— 既有 6 个 verify:* 脚本模式清晰;verify-import-roundtrip.ts 是字面模板

**Research date:** 2026-07-20
**Valid until:** 2026-08-19(30 天;稳定 domain,但 worktree feat/canvas-asset-collection 分支可能被并发 ltx 工作扰动 —— 执行前 executor 须再 `git status` 确认 clean)
