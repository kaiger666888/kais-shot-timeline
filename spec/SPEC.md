# ShotTimelineAsset — Contract Specification

**Version:** 1.1 (active; `schema_version: "1.1"`) — v1.0 (`"1"`) archived
**Owner:** `kais-shot-timeline` (本仓库,authoritative spec owner)
**Consumers:** `@kais/infinite-canvas` (`kais-aigc-platform`,跨仓库,branch `feat/canvas-asset-collection`)
**Status:** Active — Phase 5 v1.1 additive extension (2026-07-24); v1.0 contract published 2026-07-20。v1.1 是首个 minor bump(纯增量,见 §4 Changelog)。

> 这份文档是 **ShotTimelineAsset** 的人读权威契约:它把「一支成片如何被解构为可移植的多轨道分镜资产集合」用 15 分钟可读完的形式写下来,让生产端(本仓库 Phase 2 导出器)和消费端(画布 Phase 3 集合节点)对着同一份描述实现,无需口口相传字段名、类型、媒体路径或版本规则。Tribal knowledge is the failure mode this milestone exists to kill.

---

## 1. Authority & Schema Layout (D-01)

**权威源分层(严格但可读):**

| 层级 | 角色 | 文件 |
|------|------|------|
| **机器可校验的权威源** | JSON Schema (draft 2020-12) — 生产端导出时被 `spec/validate.py` 校验,消费端可据此生成 TS 类型 | `spec/schemas/*.schema.json` (9 份) |
| **人读概览(本文档)** | prose spec — 给新贡献者一份 15 分钟可读完的导览,串起 5 数据形状 + 版本规则 + 媒体约定 + 自描述 manifest | `spec/SPEC.md` (本文档) |

两层必须保持一致(schema drift = silent interop bug,见 §5 graceful-degrade 规则不放松 schema 本身)。当文档与 schema 冲突时,**以 schema 为准**;同时本文档的任何与 schema 不一致都视为 Phase 1 缺陷,必须修复。

### 9 个 schema 文件(按 filename 索引)

| 文件 | 一句话概述 |
|------|-----------|
| `spec/schemas/shots.schema.json` | 顶层 JSON 数组 — canonical 分镜边界 `{id, start_sec, end_sec, duration}`,contiguous 覆盖 `[0, duration]` |
| `spec/schemas/audio_analysis.schema.json` | 顶层对象 — 每镜 Demucs 4-stem RMS 能量 / 能量比 / 频谱质心 / `dominant_type` 分类 |
| `spec/schemas/transcript.schema.json` | 顶层对象 — Whisper 时间戳对白段 `{start, end, text}` + backend 元信息 |
| `spec/schemas/frames.schema.json` | 顶层 JSON 数组 — 每镜首尾帧的 base64 JPEG data URI(内联,非外部文件) |
| `spec/schemas/prompts.schema.json` | 顶层 JSON 数组 — 每镜结构化 prompt(7 个 facet + `prompt_text`;v1.1 新增 optional `character_refs[]`/`prop_refs[]`) |
| `spec/schemas/asset.schema.json` | 顶层对象 — 自描述 manifest(`schema_version` + 来源 + 生成器 + 数据清单 + 媒体清单;v1.1 新增 optional `data.characters`/`data.props` + `media.characters[]`/`media.props[]`) |
| `spec/schemas/characters.schema.json` | 顶层 JSON 数组 — 跨镜角色注册表(`^char_[0-9]{3}$` ID + name + 代表图 + `appearance_shots[]` + `review_state` + `looks[]`)。**v1.1** |
| `spec/schemas/props.schema.json` | 顶层 JSON 数组 — 跨镜道具注册表(`^prop_[0-9]{3}$` ID,`states[]` 非 `looks[]` — 道具按状态变体,非造型)。**v1.1** |
| `spec/schemas/registry.schema.json` | 顶层对象 — re-id 聚类草稿(`clusters[]` refs-only members + `tier` enum + `mean_cosine`)。pipeline-internal 工作产物,**不在** `asset.json#data`。**v1.1** |

**下游 TS 类型生成:** Phase 3 消费端可从这 9 个 schema 生成 TS 类型(`json-schema-to-typescript` 或等价工具);本 phase 不产生 TS 代码。

---

## 2. Asset Directory Layout (D-03, D-04)

一份 ShotTimelineAsset **就是一个目录**。消费端通过现有 `import-from-dir` 路径把整个目录吃进来;`asset.json` 是入口,自描述到「无需任何外部文档」的程度。

### Canonical 目录结构

```
<asset-root>/
├── asset.json              # manifest(entry point — schema_version + 来源 + 生成器 + 5 JSON 清单 + 媒体清单)
├── shots.json              # 分镜边界列表(D-04)
├── audio_analysis.json     # 每镜音频分析(D-04)
├── transcript.json         # Whisper 转录段(D-04)
├── frames.json             # 首尾帧 base64 data URI(内联 — 见 §7.3,D-04)
├── prompts.json            # 结构化分镜 prompt(D-04)
├── video.mp4               # canonical 视频(D-03)
└── stems/
    ├── vocals.wav          # canonical stem(D-03)
    ├── drums.wav           # canonical stem(D-03)
    └── other.wav           # canonical stem(D-03)
```

**命名要点:**

- **`bass.wav` 不在 canonical 集合内** — 消费端画布前端只渲染 vocals / drums / other 三轨。Demucs 实际产出 4 stem(含 bass),bass 在数据层(`audio_analysis.shots[].energies.bass` 等)保留完整,但在媒体清单(`asset.json#media.stems`)中被刻意剔除。生产端导出器(Phase 2)负责从 `stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav` 重命名/复制到 canonical 布局并丢弃 bass.wav。
- **5 个数据 JSON 平铺在资产根**(本 phase 锁定,未来可允许子目录 — `asset.schema.json` 的 data.* 路径 pattern 已支持 `[^/]+/` 前缀)。
- **`frames.json` 内联 base64**(不是外部图片文件)— 见 §7.3 说明。

---

## 3. The Manifest: `asset.json` (SPEC-04, D-02, D-04)

`asset.json` 是入口,自描述到消费端无需任何外部文档即可理解整份资产。

### 字段表

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string (semver-lite) | ✓ | 资产契约版本,形如 `"1"` / `"1.1"`。Pattern: `^(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$`。详见 §4 |
| `asset_type` | const `"shottimeline"` | ✓ | 资产类型 discriminator;此契约下恒为字面量 `"shottimeline"` |
| `source.video_filename` | string | ✓ | 原始视频文件名(basename,如 `"《小江湖》第03话：….mp4"`) |
| `source.duration_sec` | number (≥0) | ✓ | 原始视频时长(秒,来自 ffprobe) |
| `generator.tool` | string | ✓ | 工具名(如 `"kais-shot-timeline"`) |
| `generator.version` | string | ✓ | 工具版本(任意字符串 — semver / git SHA / build id 均可) |
| `generator.generated_at` | string (ISO-8601) | ✓ | 导出时间戳(UTC 推荐,如 `"2026-07-20T00:00:00Z"`) |
| `data.shots` | string (relative path `*.json`) | ✓ | 指向 `shots.json`(相对资产根,不可含 `..`,不可含 Windows 保留字符) |
| `data.audio_analysis` | string (relative path `*.json`) | ✓ | 指向 `audio_analysis.json` |
| `data.transcript` | string (relative path `*.json`) | ✓ | 指向 `transcript.json` |
| `data.frames` | string (relative path `*.json`) | ✓ | 指向 `frames.json` |
| `data.prompts` | string (relative path `*.json`) | ✓ | 指向 `prompts.json` |
| `media.video` | string (pattern: `video.mp4`) | ✓ | 指向 canonical 视频(资产根或一层子目录下,必须以 `video.mp4` 结尾) |
| `media.stems.vocals` | string (pattern: `stems/vocals.wav`) | ✓ | 指向 canonical vocals stem |
| `media.stems.drums` | string (pattern: `stems/drums.wav`) | ✓ | 指向 canonical drums stem |
| `media.stems.other` | string (pattern: `stems/other.wav`) | ✓ | 指向 canonical other stem |
| `data.characters` | string (relative path `*.json`) | — (v1.1) | 指向 `characters.json`(canonical confirmed 角色注册表)。仅 re-id 跑过且 HITL 审阅确认条目后 emit;v1 资产缺省,仍合法(graceful-degrade) |
| `data.props` | string (relative path `*.json`) | — (v1.1) | 指向 `props.json`(canonical confirmed 道具注册表)。同 characters 缺省规则 |
| `media.characters` | array\<string\> (png path) | — (v1.1) | 角色代表图 inventory(external png 相对路径,**非** base64 — 防 10-50× 资产膨胀)。canonical 命名 `characters/<id>.png`,anti-traversal 强约束 |
| `media.props` | array\<string\> (png path) | — (v1.1) | 道具代表图 inventory(external png)。canonical 命名 `props/<id>.png` |

**路径 pattern 强约束(防路径穿越):** 所有 data/media 路径都用负向前瞻 `(?!.*\.\.)` 拒绝父目录穿越,并拒绝绝对路径、Windows 保留字符(`:*?"<>|`)。详见 `spec/schemas/asset.schema.json` 的 `pattern` 字段。

**最小样例:** 见 `spec/fixtures/minimal/asset.json`(2-shot 样例,所有字段齐全)。

Reference schema: `spec/schemas/asset.schema.json`

---

## 4. Schema Versioning & Graceful Degrade (SPEC-02, D-02)

`schema_version` 是 manifest 顶层单字段(不是每个数据 JSON 各自带版本)— 一个 `schema_version` 覆盖整份资产。

### Pattern

```
^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$
```

- 接受:`"1"`, `"1.1"`, `"2.0"`, `"0"`, `"10"`, `"1.0"`
- 拒绝:`"v1"`(前缀), `"1.1.1"`(三段), `""`(空), `"01"`(前导零), `"1."`, `".1"`, `"1.2.3-alpha"`

### Graceful-degrade 规则(逐字引用自 `asset.schema.json#schema_version.description`)

> Asset contract version, semver-lite (major[.minor]). Examples: "1", "1.1", "2.0". Non-examples: "v1", "1.1.1", "". Consumer MUST graceful-degrade on unknown/newer versions: ignore unknown fields, render known parts, emit a warning — do NOT reject. New field = minor bump; breaking change (rename/semantic shift/removal) = major bump (document migration in SPEC.md).

**消费端的运行时义务(三步):**

1. **忽略未知字段** — 不要因为遇到 schema 没列的字段就报错。
2. **渲染已知部分** — 把能识别的字段照常渲染。
3. **emit 一个 warning** — 不要静默,让运维侧能感知到版本错位。
4. **不要 reject / 不要 crash** — 保向前兼容,避免脆弱断裂。

### 严格 schema × 宽松消费端的「有意张力」

- **schema 严格**(`additionalProperties: false` 在每个 object 上)— 这才是强制生产端显式 bump 版本的机制。Validation-time strictness is what forces explicit version bumps.
- **消费端宽松**(runtime graceful-degrade)— 是消费端的运行时行为,**不是**放松 schema。两条规则分别住在不同层次,不要混淆。

规则全文嵌在 `asset.schema.json` 的两处:`schema_version.description`(消费端读 schema 时直接看到)+ 顶层 `$comment`(schema 作者意图)。

### 为什么是 semver-lite,不是完整 semver

- ShotTimelineAsset 是**单一生产端的产物**,不是公开发布的库 — 不存在 patch 修复版本的概念(没有消费者依赖的「bug fix」语义)。
- `major.minor` 已足够区分「破坏性变更」与「加字段」。
- 完整 semver(`1.2.3` + pre-release tags)增加心智负担,且无法在 single-producer 场景下提供额外信号。

### 演进规则

| 变更类型 | 版本动作 | 旧消费端行为 |
|---------|---------|-------------|
| 新增字段 | minor bump(`"1"` → `"1.1"`) | graceful-degrade(忽略新字段,正常渲染) |
| 重命名字段 / 改语义 / 删字段 | major bump(`"1"` → `"2"`) | graceful-degrade + warning(渲染已知部分;字段缺失时按缺省处理) |
| 加 enum 值 | minor bump | 旧消费端遇到新 enum 值应归为「未知」并 warn,不要 crash |
| 加 required 字段 | **major bump** | 旧消费端无法满足,必须显式迁移 |

任何 major bump **必须**在本节下方的 Changelog 写迁移说明。

### Changelog

- **2026-07-20 — `1`(initial contract)** — Phase 1 首次发布。定义 6 schema(shots / audio_analysis / transcript / frames / prompts / asset)、5 canonical 数据形状、自描述 manifest、canonical 媒体布局(`video.mp4` + `stems/{vocals,drums,other}.wav`,bass 剔除)、Range-aware HTTP 206 服务要求。`additionalProperties: false` 全程开启,graceful-degrade 是消费端运行时行为。

- **2026-07-24 — `1.1`(v1.1 additive extension,Phase 5)** — 首个 minor bump,纯增量(无 rename / 语义漂移 / 新增 required 字段 — Pitfall 11 prevented)。变更:
  - **3 个新 schema**:`characters.schema.json`(`^char_[0-9]{3}$` ID + `looks[]`)、`props.schema.json`(`^prop_[0-9]{3}$` ID,`states[]` 非 `looks[]`)、`registry.schema.json`(re-id 聚类草稿,pipeline-internal,不在 `asset.json#data`)。
  - **`prompts.schema.json` additive**:新增 optional `character_refs[]` / `prop_refs[]`(ID-pattern string 数组,Phase 8 按 `appearance_shots[]` 挂到对应 shot)。`required[]` 与 v1.0 byte-identical。
  - **`asset.schema.json` additive**:新增 optional `data.characters` / `data.props`(JSON 路径)+ `media.characters[]` / `media.props[]`(external png 路径数组,**非** base64 — 资产膨胀防护,与 `frames.json` 内联 base64 相反)。
  - **`schema_version` pattern 不变**(`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`)— 版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.1"`,**非** schema `const`(否则拒绝 v1 minimal fixture `"1"`,破坏 CONTRACT-09)。
  - **向后兼容**:`spec/fixtures/minimal/`(v1)仍 6/6 绿(CONTRACT-09);`spec/fixtures/v1.1/`(9 文件)新增;`scripts/verify_contract.py` `_cross_version_check` 实测双向兼容(forward 0 errors;backward 仅 additionalProperties errors → 0 non-additive errors)。

---

## 5. The 5 Canonical Data Shapes (SPEC-01)

每种形状都列出:生产端脚本、字段级类型表(名称 / 类型严格对齐 schema)、enum 值(如有)、最小 JSON 片段、参考 schema 文件。

> **v1.1 (Phase 5):** §5.1–§5.5 是 v1.0 的 5 个 required 数据形状;新增 §5.6 **Characters** + §5.7 **Props** 两个 optional 跨镜注册表形状(仅 re-id 跑过且 HITL 审阅后 emit)。registry 是 pipeline-internal 草稿,非 canonical asset 数据形状,故不在此列(见 §1 schema 索引)。

### Shots

**Producer:** `detectors/detect_v3b.py:main`(写入 `shots.json`)
**Consumers:** `audio/separate_stems.py:analyze_shots`、`html/gen_timeline_html.py:build_shots_js`

**顶层形状:** JSON 数组,contiguous 覆盖 `[0, source_duration]`,无 gap。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | integer (≥1) | ✓ | 1-based 镜头索引,数组内单调递增 |
| `start_sec` | number (≥0) | ✓ | 镜头起始秒(含);首镜必须为 `0.0` |
| `end_sec` | number (≥0) | ✓ | 镜头结束秒(不含);必须等于下一镜 `start_sec` |
| `duration` | number (>0) | ✓ | 镜头时长(秒);必须等于 `end_sec - start_sec` 且 > 0 |

**最小片段:**

```json
[
  {"id": 1, "start_sec": 0.0,  "end_sec": 1.5, "duration": 1.5},
  {"id": 2, "start_sec": 1.5,  "end_sec": 3.0, "duration": 1.5}
]
```

Reference schema: `spec/schemas/shots.schema.json`

### Audio Analysis

**Producer:** `audio/separate_stems.py:analyze_shots`
**顶层形状:** JSON 对象 — Demucs htdemucs 4-stem 分离结果 + 每镜能量/频谱分析 + 主导类型分类。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `episode` | string | ✓ | 逻辑 episode/source 标签(生产端当前恒为字面量 `"shots"`) |
| `duration` | number (≥0) | ✓ | 分析覆盖的源时长(秒) |
| `stems` | array<enum> | ✓ | 固定 4-stem:`["vocals", "drums", "bass", "other"]`;`minItems=4 maxItems=4 uniqueItems=true`;顺序由生产端决定 |
| `shots[]` | array<object> | ✓ | 每镜分析条目;必须与 `shots.json` 按 `shot_id` 1:1 对齐 |
| `shots[].shot_id` | integer (≥1) | ✓ | 对应 `shots.json` 的 `id` |
| `shots[].start_sec` | number (≥0) | ✓ | 镜头起始秒 |
| `shots[].end_sec` | number (≥0) | ✓ | 镜头结束秒 |
| `shots[].duration` | number (>0) | ✓ | 镜头时长 |
| `shots[].energies` | object `{vocals, drums, bass, other: number≥0}` | ✓ | 每轨 RMS 能量(linear amplitude²,范围大致 `[0, 1]`) |
| `shots[].ratios` | object `{vocals, drums, bass, other: number≥0}` | ✓ | 每轨能量占比(总和约为 1.0) |
| `shots[].spectral_centroid` | object `{vocals, drums, bass, other: number≥0}` | ✓ | 每轨频谱质心(Hz,亮度) |
| `shots[].dominant_type` | enum | ✓ | 见下表 |
| `type_distribution` | object `{dialogue, bgm, mixed, sfx: integer≥0}` | ✓ | `dominant_type` 在 shots 数组上的计数直方图 |

**`dominant_type` enum(逐字对齐 schema):**

| 值 | 含义 |
|----|------|
| `dialogue` | 对白主导 |
| `bgm` | 背景音乐主导 |
| `mixed` | 混合(无明显主导) |
| `sfx` | 音效主导 |

由 `audio/separate_stems.py:classify_shot`(能量 + 频谱质心启发式)给出。

**最小片段:**

```json
{
  "episode": "shots",
  "duration": 3.0,
  "stems": ["vocals", "drums", "bass", "other"],
  "shots": [
    {"shot_id": 1, "start_sec": 0.0, "end_sec": 1.5, "duration": 1.5,
     "energies": {"vocals": 0.8, "drums": 0.1, "bass": 0.05, "other": 0.05},
     "ratios":   {"vocals": 0.8, "drums": 0.1, "bass": 0.05, "other": 0.05},
     "spectral_centroid": {"vocals": 1200.0, "drums": 200.0, "bass": 80.0, "other": 1500.0},
     "dominant_type": "dialogue"}
  ],
  "type_distribution": {"dialogue": 1, "bgm": 0, "mixed": 0, "sfx": 0}
}
```

Reference schema: `spec/schemas/audio_analysis.schema.json`

### Transcript

**Producer:** `audio/transcribe.py:main`(优先 `faster-whisper`,失败回退 `openai-whisper`)
**顶层形状:** JSON 对象 — Whisper 时间戳对白段。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `backend` | enum | ✓ | 见下表 |
| `model` | string | ✓ | Whisper 模型 id(如 `"large-v3"`) |
| `language` | string | ✓ | 检测/强制语言码(ISO-639-1 小写,如 `"zh"`) |
| `segments[]` | array<object> | ✓ | 有序 Whisper 段,跨 `[0, duration)`;相邻段通常 contiguous(`end_i == start_{i+1}`),静默处可有 gap |
| `segments[].start` | number (≥0) | ✓ | 段起始秒 |
| `segments[].end` | number (≥0) | ✓ | 段结束秒(必须 > `start`) |
| `segments[].text` | string | ✓ | 该段转录文本(静默段可为空字符串) |
| `text` | string | ✓ | 全文(所有段文本拼接) |
| `duration` | number (≥0) | ✓ | 源时长(秒,来自 ffprobe) |
| `source` | string | ✓ | 原始视频文件名(basename,可追溯) |

**`backend` enum(逐字对齐 schema):**

| 值 | 含义 |
|----|------|
| `faster-whisper` | CTranslate2 后端(优先) |
| `openai-whisper` | OpenAI 官方后端(回退) |

由 `audio/transcribe.py:109-123` 的 auto-fallback 逻辑在运行时解析(`--backend auto` 默认)。

**最小片段:**

```json
{
  "backend": "faster-whisper",
  "model": "large-v3",
  "language": "zh",
  "segments": [
    {"start": 0.0, "end": 1.5, "text": "你好"},
    {"start": 1.5, "end": 3.0, "text": "世界"}
  ],
  "text": "你好世界",
  "duration": 3.0,
  "source": "sample.mp4"
}
```

Reference schema: `spec/schemas/transcript.schema.json`

### Frames

**Producer:** `html/gen_timeline_html.py:extract_frames_if_needed`(ffmpeg 抽帧 → JPEG → base64 data URI)
**顶层形状:** JSON 数组 — 每镜首尾帧的内联 base64 JPEG data URI。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | integer (≥1) | ✓ | 对应 `shots.json` 的 `id` |
| `first_frame` | string | ✓ | 首帧 data URI;pattern: `^data:image/jpeg;base64,` |
| `last_frame` | string | ✓ | 尾帧 data URI;pattern: `^data:image/jpeg;base64,` |

**为什么内联 base64(而不是外部文件):** 见 §7.3 — frames 是「让 JSON 集合自包含、可直接 browse」的唯一例外(视频/stem 因体积外置,frames 因小巧且与镜头强绑定而内联)。

**最小片段(已截断 base64 以便阅读):**

```json
[
  {"id": 1,
   "first_frame": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/2wB...",
   "last_frame":  "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/2wB..."}
]
```

Reference schema: `spec/schemas/frames.schema.json`

### Prompts

**Producer:** `html/gen_prompts_html.py`(已建立;`spec/schemas/prompts.schema.json#description` 注明 planned producer,当前生产端形状已在 `output/《小江湖》第03话…/prompts.json` 中观察并 smoke-valid)
**顶层形状:** JSON 数组 — 每镜结构化 prompt(7 个 facet + `prompt_text`)。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `shot_id` | integer (≥1) | ✓ | 对应 `shots.json` 的 `id` |
| `start_sec` | number (≥0) | ✓ | 镜头起始秒 |
| `end_sec` | number (≥0) | ✓ | 镜头结束秒 |
| `duration` | number (>0) | ✓ | 镜头时长 |
| `subject` | string | ✓ | 画面主体(角色、关键物件) |
| `action` | string | ✓ | **完整物理动作链**(谁→做什么→一步步→物理合理,如"抬头→伸手接住浆果→捧到嘴边→张嘴咬下→咀嚼,表情舒展")。不要只写一句话("缓缓抬头"不够)——下游视频模型靠这条链路演动作,写简了会瞎演/违反物理。运镜放 `camera` |
| `camera` | string | ✓ | 镜头语言(景别、运镜) |
| `scene` | string | ✓ | 场景 / 环境 |
| `lighting` | string | ✓ | 光线质量与方向 |
| `style` | string | ✓ | 视觉风格(媒介、渲染质感、参考) |
| `prompt_text` | string | ✓ | 由上述 facet 合成的即用 prompt 文本 |
| `character_refs` | array\<string\> (`^char_[0-9]{3}$`) | — (v1.1) | 该镜出现的角色 ID 列表(`characters.json#id` 子集)。Phase 8 按 `characters.json#appearance_shots[]` 挂载,实现跨镜叙事连贯。v1 资产缺省,仍合法 |
| `prop_refs` | array\<string\> (`^prop_[0-9]{3}$`) | — (v1.1) | 该镜出现的道具 ID 列表(`props.json#id` 子集)。同 `character_refs` 挂载规则 |

**最小片段:**

```json
[
  {"shot_id": 1, "start_sec": 0.0, "end_sec": 1.5, "duration": 1.5,
   "subject": "少女特写", "action": "垂眸片刻后缓缓抬起头,目光从地面移向窗外,嘴角微微上扬,几缕发丝随抬头动作轻轻晃动",
   "camera": "近景,固定机位", "scene": "室内,逆光",
   "lighting": "侧逆光,柔光", "style": "动画赛璐珞质感",
   "prompt_text": "近景固定机位,少女在室内逆光下垂眸片刻后缓缓抬起头,目光移向窗外,嘴角微扬,发丝轻晃,侧逆光柔和,动画赛璐珞质感"}
]
```

Reference schema: `spec/schemas/prompts.schema.json`

### Characters (v1.1)

**Producer:** `registry/apply_edits.py`(Phase 7/8,pending — 把 HITL 审阅后的 `confirmed` 条目流向 canonical `characters.json`)
**顶层形状:** JSON 数组 — 跨镜角色注册表。每个角色 = 不可变 ID + 展示名 + 代表图 + 出场镜头 + 审阅状态 + 造型变体。v1.1 全新数据文件;v1 资产缺省(`asset.json#data.characters` absent),仍合法。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string (`^char_[0-9]{3}$`) | ✓ | 不可变角色 ID(零填充 3 位)。一旦 confirmed,永不重用或重排版(Pitfall 17 — 保证 `prompts.json#character_refs[]` 引用永不悬空) |
| `name` | string | ✓ | 展示名(中文/英文均可);reviewer 可编辑,ID 不可编辑 |
| `representative_image` | string (png path) | — | external png 相对路径(`characters/<id>.png`),anti-traversal 强约束,**非** base64 |
| `appearance_shots` | array\<integer\> | — | 该角色出场的 shot ID 列表(`shots.json#id` 子集);Phase 8 据此挂 `character_refs[]` |
| `review_state` | enum | ✓ | `proposed` / `confirmed` / `rejected`。**仅 `confirmed` 流向下游 prompt 引用**(Pitfall 7);`rejected` = 软删除(ID 保留维护引用完整性) |
| `looks` | array\<object\> | — | 造型/服装变体。每个 look = `{label, image_ref, appearance_shots[]}`,自带出场镜头 → Phase 8 能挂 per-look prompt refs(非仅 per-character) |

**`review_state` enum:**

| 值 | 语义 |
|----|------|
| `proposed` | re-id 聚类草稿(`registry.draft.json`)默认值;尚未人工审阅 |
| `confirmed` | HITL 审阅确认;**唯一**流向 `characters.json` + prompt 引用的状态 |
| `rejected` | 审阅否决;软删除(ID 永不重用,维护引用完整性) |

**最小片段**(摘自 `spec/fixtures/v1.1/characters.json`):

```json
[
  {"id": "char_001", "name": "少女", "representative_image": "characters/char_001.png",
   "appearance_shots": [1, 2], "review_state": "confirmed",
   "looks": [{"label": "默认造型", "image_ref": "characters/char_001.png", "appearance_shots": [1, 2]}]}
]
```

Reference schema: `spec/schemas/characters.schema.json`

### Props (v1.1)

**Producer:** `registry/apply_edits.py`(Phase 7/8,pending)
**顶层形状:** JSON 数组 — 跨镜道具注册表。与 characters 同构核心 shape,但变体字段是 `states[]`(道具按状态:开/关、完好/破碎)而非 `looks[]`(服装) — **语义精度优先于 schema 统一**(CONTEXT D-XX lock)。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string (`^prop_[0-9]{3}$`) | ✓ | 不可变道具 ID(零填充 3 位);同样 Pitfall 17 ID 不可变 |
| `name` | string | ✓ | 展示名(如「落叶」「神秘信件」) |
| `representative_image` | string (png path) | — | `props/<id>.png`,anti-traversal,**非** base64 |
| `appearance_shots` | array\<integer\> | — | 出场 shot ID 列表 |
| `review_state` | enum | ✓ | 同 characters:`proposed` / `confirmed` / `rejected` |
| `states` | array\<object\> | — | 状态变体。每个 state = `{label, image_ref, appearance_shots[]}`(如「完好」/「破碎」)。刻意不与 characters 的 `looks[]` 合并 |

**最小片段**(摘自 `spec/fixtures/v1.1/props.json`):

```json
[
  {"id": "prop_001", "name": "落叶", "representative_image": "props/prop_001.png",
   "appearance_shots": [2], "review_state": "confirmed",
   "states": [{"label": "完好", "image_ref": "props/prop_001.png", "appearance_shots": [2]},
              {"label": "破碎", "image_ref": "props/prop_001_broken.png", "appearance_shots": []}]}
]
```

Reference schema: `spec/schemas/props.schema.json`

---

## 6. Media References & Range-aware Serving (SPEC-03, D-03)

媒体文件(video + 3 stem wavs)是 ShotTimelineAsset 中**唯一外置**的资源 — 它们必须经 **Range-aware HTTP 206 (Partial Content)** 服务才能被消费端正常 seek 播放。

### 6.1 路径与命名约定

| 资源 | Canonical 路径 | Pattern(asset.schema.json) |
|------|---------------|---------------------------|
| 视频 | `video.mp4`(资产根,或一层子目录下如 `subdir/video.mp4`) | `^(?!.*\.\.)([^/]+/)*video\.mp4$` |
| vocals stem | `stems/vocals.wav` | `^(?!.*\.\.)([^/]+/)*stems/(vocals)\.wav$` |
| drums stem | `stems/drums.wav` | `^(?!.*\.\.)([^/]+/)*stems/(drums)\.wav$` |
| other stem | `stems/other.wav` | `^(?!.*\.\.)([^/]+/)*stems/(other)\.wav$` |

**强制约束(schema 层):**

- **相对路径** — 不可绝对路径(`/abs/...`)、不可含驱动器盘符(`C:\...`)。
- **不可父目录穿越** — 所有 pattern 用负向前瞻 `(?!.*\.\.)` 拒绝 `../`。
- **不可 Windows 保留字符** — data 路径拒绝 `:*?"<>|`。
- **大小写敏感** — `Video.mp4` 会被拒绝(必须 `video.mp4`)。
- **必须以正确扩展名结尾** — `video.mp4` / `.wav` / `.json`。
- **`bass.wav` 显式剔除** — `media.stems` 不接受 bass(canonical 集合是 3 stem)。bass 仍在数据层 `audio_analysis.shots[].energies.bass` 保留(频谱分析需要完整 4-stem 数据)。

**生产端当前非 canonical 布局(`stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav`)被 schema 拒绝** — Phase 2 导出器负责重命名到 canonical 布局(并丢弃 bass.wav)再写 `asset.json`。

### 6.2 Range-aware HTTP 206 要求

消费端 `<video>` / `<audio>` 元素的 seek 行为依赖服务端正确响应 `Range` 请求头,返回 **HTTP 206 Partial Content**(而非 200 OK 全文重传)。若服务端只返回 200,会出现「第一个分镜能播、后面 seek 回 0」的现象(浏览器无法定位到后期字节偏移)。

**已知 Ubuntu/Debian quirk:** `python3 -m http.server` 在某些发行版上**不识别 Range 头**,只返回 200 — 这就是 `scripts/serve.py` 存在的原因。

**参考实现(SPEC-03 的 reference server):** `scripts/serve.py`

```bash
# 启动 Range-aware 静态 server,把整个资产目录暴露为可 seek 的 HTTP 资源
python3 scripts/serve.py <asset-root> 8765
# 默认 dir=. port=8765
```

`scripts/serve.py` 是 `http.server.SimpleHTTPRequestHandler` 的子类,override 了 `send_head()` 以正确解析 `Range: bytes=start-end` 请求头,返回 `206 Partial Content` + `Content-Range: bytes start-end/total` + `Accept-Ranges: bytes`。生产端 v1.0 **不修改**该脚本(SPEC-03 直接引用现有实现);若 Phase 2 发现性能或安全问题(FD leak、binds `0.0.0.0` unauth),会在 EXPORT-03 范围内做定向硬化。

### 6.3 为什么媒体外置(而 frames 内联)

| 资源 | 体积 | 处理方式 | 理由 |
|------|------|---------|------|
| `video.mp4` | 多 100-MB(单 episode 可达数百 MB) | 外置 + Range 206 服务 | 太大无法内联;消费端必须可 seek |
| `stems/*.wav` | 多 10-MB / stem | 外置 + Range 206 服务 | 同上;且分轨独立 seek(试听某轨) |
| `frames.json`(首尾帧) | 单帧 JPEG ~10-50 KB | **内联 base64** | 体积可控,且 frames 与 shot 强绑定 — 内联让 JSON 集合保持自包含,消费端 browse thumbnails 时无需再发 N 个小请求 |

**frames 是唯一例外**(CONTEXT D-04)。这条规则与生产端现有 `frames.json` 模式一致(已 smoke-valid)。

### 6.4 角色与道具代表图(v1.1 — external png,非 base64)

v1.1 新增 `media.characters[]` / `media.props[]` 媒体类别:角色与道具的代表图(cropped portrait)。**刻意外置为 png 文件,不内联 base64** — 与 `frames.json` 的内联策略相反,理由:

| 资源 | 体积 | 处理方式 | 理由 |
|------|------|---------|------|
| `characters/<id>.png` / `props/<id>.png` | 单图 ~50-200 KB,但角色/道具数量随内容增长(一部 episode 可达数十-上百) | **external png** | 总量随 registry 增长;内联会使 `characters.json`/`props.json` 膨胀 10-50×,甚于 `frames.json`。外置让 registry JSON 保持精简,图像走 `serve.py` |

**canonical 命名:** `characters/<id>.png` / `props/<id>.png`(如 `characters/char_001.png`)。`representative_image` 与 `looks[].image_ref` / `states[].image_ref` 共用同一 anti-traversal pattern。服务:经 `scripts/serve.py` 暴露(png 体积小,200 OK 足够,Range 非必需,但 serve.py 透明处理)。anti-traversal 在 schema 层强制(`asset.schema.json#media.characters[].pattern` + `characters.schema.json#representative_image.pattern`)。

---

## 7. Validation

如何把一份资产对着契约校验:

```bash
# 默认:minimal fixture 必须 6 条全 [valid]
#      + smoke 校验 output/ 下真实生产产物(仅打印,不影响退出码)
python3 spec/validate.py

# 严格模式:smoke 失败也计入退出码(Phase 2 回归 / CI 用)
python3 spec/validate.py --strict-smoke
```

- **`spec/validate.py`** 用 `jsonschema.Draft202012Validator`(4.26.0,system-installed,无 pip 安装)。
- **`spec/fixtures/minimal/`** 是 canonical 样例资产(2-shot,所有字段齐全)— 任何 schema 改动后都应跑一遍确保 6/6 `[valid]`。
- **smoke mode** 自动发现 `output/` 下第一个含 `shots.json` 的子目录,对 5 个数据 JSON 做宽容校验(只校验 5 个数据形状,不校验 asset.json — 生产端尚未输出 manifest)。Phase 1 当前结果:**5/5 smoke-valid**,意味着 Phase 2 的数据形状无需 cleanup,只需补 `asset.json` + canonical 媒体重命名。

---

## 8. Out of Scope (for v1.0)

本 phase **只交付契约文档**;以下明确不在 v1.0 范围(详见 `PROJECT.md` Out of Scope):

- **画布内原生时间轴渲染器**(stem 播放引擎、波形 canvas、Range 媒体服务)— v1.0 只做格式契约 + 结构化集合表示;完整原生交互是后续 milestone,建立在契约之上。
- **画布侧 Range 媒体服务**(消费端自带 206 server)— 消费端经 `import-from-dir` 拿到的是本地目录路径,媒体由本仓库的 `scripts/serve.py` 提供;画布自带服务是后续 milestone。
- **新增画布 custom renderer / contract bump** — v1.0 用结构化父节点(zone/phase 模式)复用现有 5 渲染器,零 contract bump。
- **shot-timeline 现有检测 / 转录 / 分离算法本身的优化或替换** — 已是 validated 基线,v1.0 不动核心算法,只在其输出之上加导出层。
- **把 shot-timeline 拆成画布编排 skill**(紧耦合方案)— 用户已选「外部生产者」松耦合;画布编排留待未来评估。
- **多用户 / web UI for the producer** — 生产端是 CLI pipeline,无 web UI 计划。
- **训练流水线集成** — 当前 milestone 只定义资产格式,不动训练侧。

---

## 9. References

- **项目级文档:**
  - `.planning/PROJECT.md` — milestone scope / constraints / key decisions
  - `.planning/ROADMAP.md` — Phase 1–4 derivation chain
  - `.planning/REQUIREMENTS.md` — SPEC-01..04 验收要求
- **6 个 schema 文件(机器可校验的权威源):**
  - `spec/schemas/shots.schema.json`
  - `spec/schemas/audio_analysis.schema.json`
  - `spec/schemas/transcript.schema.json`
  - `spec/schemas/frames.schema.json`
  - `spec/schemas/prompts.schema.json`
  - `spec/schemas/asset.schema.json`
- **校验器与样例:**
  - `spec/validate.py` — jsonschema 校验器
  - `spec/fixtures/minimal/` — canonical minimal asset
  - `spec/README.md` — spec 目录导览
- **Range-aware server(SPEC-03 reference impl):**
  - `scripts/serve.py`
- **5 个生产端脚本(数据形状的实际产出方):**
  - `detectors/detect_v3b.py` — V3b 4-pass 融合检测 → `shots.json`
  - `audio/separate_stems.py` — Demucs htdemucs 4-stem 分离 + 每镜能量/频谱分析 + `dominant_type` 分类 → `audio_analysis.json`
  - `audio/transcribe.py` — Whisper 转录(faster-whisper 优先、openai-whisper 回退)→ `transcript.json`
  - `html/gen_timeline_html.py:extract_frames_if_needed` — ffmpeg 抽首尾帧 → base64 → `frames.json`
  - `html/gen_prompts_html.py` — 结构化分镜 prompt 反推 → `prompts.json`

---

*Created: 2026-07-20 (Phase 01 Plan 02 — initial publication of the human-readable ShotTimelineAsset contract).*
* schema_version "1" — initial contract. See §4 Changelog for evolution rules.*
