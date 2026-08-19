# ShotTimelineAsset — Contract Specification

**Version:** 1.3 (active; `schema_version: "1.3"`) — v1.2 (`"1.2"`) / v1.1 (`"1.1"`) / v1.0 (`"1"`) archived
**Owner:** `kais-shot-timeline` (本仓库,authoritative spec owner)
**Consumers:** `@kais/infinite-canvas` (`kais-aigc-platform`,跨仓库,branch `feat/canvas-asset-collection`)
**Status:** Active — Phase 18 v1.3 additive extension (2026-08-19); Phase 11 v1.2 additive extension (2026-07-25); Phase 5 v1.1 additive extension (2026-07-24); v1.0 contract published 2026-07-20。v1.1 是首个 minor bump;v1.3 是第三个 minor bump(additive 为主,含两处诚实记录的非纯 property-delta,见 §4 Changelog)。

> 这份文档是 **ShotTimelineAsset** 的人读权威契约:它把「一支成片如何被解构为可移植的多轨道分镜资产集合」用 15 分钟可读完的形式写下来,让生产端(本仓库 Phase 2 导出器)和消费端(画布 Phase 3 集合节点)对着同一份描述实现,无需口口相传字段名、类型、媒体路径或版本规则。Tribal knowledge is the failure mode this milestone exists to kill.

---

## 1. Authority & Schema Layout (D-01)

**权威源分层(严格但可读):**

| 层级 | 角色 | 文件 |
|------|------|------|
| **机器可校验的权威源** | JSON Schema (draft 2020-12) — 生产端导出时被 `spec/validate.py` 校验,消费端可据此生成 TS 类型 | `spec/schemas/*.schema.json` (14 份) |
| **人读概览(本文档)** | prose spec — 给新贡献者一份 15 分钟可读完的导览,串起 5 数据形状 + 版本规则 + 媒体约定 + 自描述 manifest | `spec/SPEC.md` (本文档) |

两层必须保持一致(schema drift = silent interop bug,见 §5 graceful-degrade 规则不放松 schema 本身)。当文档与 schema 冲突时,**以 schema 为准**;同时本文档的任何与 schema 不一致都视为 Phase 1 缺陷,必须修复。

### 14 个 schema 文件(按 filename 索引)

| 文件 | 一句话概述 |
|------|-----------|
| `spec/schemas/shots.schema.json` | 顶层 JSON 数组 — canonical 分镜边界 `{id, start_sec, end_sec, duration}`,contiguous 覆盖 `[0, duration]` |
| `spec/schemas/audio_analysis.schema.json` | 顶层对象 — 每镜 Demucs 4-stem RMS 能量 / 能量比 / 频谱质心 / `dominant_type` 分类 |
| `spec/schemas/transcript.schema.json` | 顶层对象 — Whisper 时间戳对白段 `{start, end, text}` + backend 元信息 |
| `spec/schemas/frames.schema.json` | 顶层 JSON 数组 — 每镜首尾帧的 base64 JPEG data URI(内联,非外部文件) |
| `spec/schemas/prompts.schema.json` | 顶层 JSON 数组 — 每镜结构化 prompt(7 个 facet + `prompt_text`;v1.1 新增 optional `character_refs[]`/`prop_refs[]`) |
| `spec/schemas/asset.schema.json` | 顶层对象 — 自描述 manifest(`schema_version` + 来源 + 生成器 + 数据清单 + 媒体清单;v1.1 新增 optional `data.characters`/`data.props` + `media.characters[]`/`media.props[]`;v1.2 新增 optional `data.audio_semantic`/`data.speakers`) |
| `spec/schemas/characters.schema.json` | 顶层 JSON 数组 — 跨镜角色注册表(`^char_[0-9]{3}$` ID + name + 代表图 + `appearance_shots[]` + `review_state` + `looks[]`)。**v1.1** |
| `spec/schemas/props.schema.json` | 顶层 JSON 数组 — 跨镜道具注册表(`^prop_[0-9]{3}$` ID,`states[]` 非 `looks[]` — 道具按状态变体,非造型)。**v1.1** |
| `spec/schemas/registry.schema.json` | 顶层对象 — re-id 聚类草稿(`clusters[]` refs-only members + `tier` enum + `mean_cosine`)。pipeline-internal 工作产物,**不在** `asset.json#data`。**v1.1** |
| `spec/schemas/audio_semantic.schema.json` | 顶层对象 — per-shot 三模态音频语义(dialogue/sfx)+ 分层复现 prompt(TTS/music-gen/foley);`word_level_experimental` 顶层 flag gate word-level timestamps;`emotion` nullable string + `emotion_confidence`(见 §10 fidelity_disclaimer)。**`1.2`** |
| `spec/schemas/speakers.schema.json` | 顶层对象 — 声学说话人注册表(NEW `^spk_[0-9]{3}$` acoustic ID space,与 `^char_[0-9]{3}$` 视觉 ID 刻意 disjoint);nullable `char_id` link;`review_state` 门控下游流向。**`1.2`** |
| `spec/schemas/speaker-edits.schema.json` | 顶层对象 — speaker HITL 审阅 edits round-trip shape(mirrors `registry-edits.schema.json` + 新 `link_mappings` 作 spk→char N:M 映射;Phase 13 `link_speakers.py` 消费)。pipeline-internal 工作产物,**不在** `asset.json#data`。**`1.2`** |
| `spec/schemas/roundtrip.schema.json` | 顶层对象 — per-shot h3 重生成 ref(`regen` 5-tuple)+ 双信号打分 `scores{midframe_sim, judge}` + `verdict{accepted/rejected}`;`shots[]` 是结果集(regen 失败 = `status{state:failed}`,未尝试 = 缺席);阈值不进 schema(见 §10 / Phase 21)。**`1.3`** |

**下游 TS 类型生成:** Phase 3 消费端可从这 14 个 schema 生成 TS 类型(`json-schema-to-typescript` 或等价工具);本 phase 不产生 TS 代码。

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
| `generator.warnings` | array\<string\> | — (v1.1) | 非致命警告列表(如运镜路由不可达 → prompts 空字段降级)。仅在非空时 emit;老资产及干净运行缺省仍合法(graceful-degrade)。Producer: Plan 02 `analysis/call_shot_analysis.py` 在路由失败时写 `route_cache/warnings.json` sidecar,由 `scripts/export_asset.py:main` best-effort 读入合并进 `generator.warnings`。Operator-facing failure reasons only(exception class + message, route status codes)— no PII, no auth tokens, no body payloads |
| `generator.registry_snapshot` | object `{characters[], props[]}` | — (v1.1 Phase 8) | 导出时冻结的 confirmed registry 紧凑视图(characters + props)。每条目嵌 id / name / representative_image / appearance_shots —— 消费端据此解析 `prompts.character_refs[]`/`prop_refs[]` + 渲染画廊,**无需**再读外部 `characters.json`/`props.json`。Producer(`scripts/export_asset.py` Plan 02)仅在 `characters.json` 或 `props.json` 存在时 emit 确认态 registry 的冻结快照;无 registry 时缺省(byte-identical to v1.0/v1.1-no-reid)。仍是 v1.1 纯增量(无 schema_version bump、`required[]` 不变、`additionalProperties:false` 保留)。Pitfall 18 prevented:snapshot 是 export-time truth,后续 registry 变动(re-review / re-cluster / rename)不回写已导出的 `asset.json` |
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

- **2026-07-24 — `1.1`(v1.1 additive extension,Phases 5-9)** — 首个 minor bump,纯增量(无 rename / 语义漂移 / 新增 required 字段 — Pitfall 11 prevented)。整个 v1.1 milestone(phases 5-9)共享此版本号,各 phase 仅做 optional 字段增量;无 schema_version bump 直到 v2。变更:
  - **3 个新 schema**:`characters.schema.json`(`^char_[0-9]{3}$` ID + `looks[]`)、`props.schema.json`(`^prop_[0-9]{3}$` ID,`states[]` 非 `looks[]`)、`registry.schema.json`(re-id 聚类草稿,pipeline-internal,不在 `asset.json#data`)。
  - **`prompts.schema.json` additive**:新增 optional `character_refs[]` / `prop_refs[]`(ID-pattern string 数组,Phase 8 按 `appearance_shots[]` 挂到对应 shot)。`required[]` 与 v1.0 byte-identical。
  - **`asset.schema.json` additive**:新增 optional `data.characters` / `data.props`(JSON 路径)+ `media.characters[]` / `media.props[]`(external png 路径数组,**非** base64 — 资产膨胀防护,与 `frames.json` 内联 base64 相反)。
  - **`schema_version` pattern 不变**(`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`)— 版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.1"`,**非** schema `const`(否则拒绝 v1 minimal fixture `"1"`,破坏 CONTRACT-09)。
  - **向后兼容**:`spec/fixtures/minimal/`(v1)仍 6/6 绿(CONTRACT-09);`spec/fixtures/v1.1/`(9 文件)新增;`scripts/verify_contract.py` `_cross_version_check` 实测双向兼容(forward 0 errors;backward 仅 additionalProperties errors → 0 non-additive errors)。
  - **Phase 6 (cinematography auto-fill)**: `asset.schema.json#generator` 新增 optional `warnings: array<string>`(Plan 01)。Producer(`scripts/export_asset.py`)在 step_semantic 路由失败时从 `route_cache/warnings.json` sidecar 读入失败原因列表,非空时 emit `generator.warnings`;None / 空列表时缺省。仍是 v1.1 纯增量(无 schema_version bump、`required[]` 不变、`additionalProperties:false` 保留)。
  - **Phase 8 (prompt reference system)**: `asset.schema.json#generator` 新增 optional `registry_snapshot: {characters[], props[]}`(Plan 01)。Producer(`scripts/export_asset.py` Plan 02)在 `characters.json`/`props.json` 存在时 emit 确认态 registry 的冻结快照;无 registry 时缺省(byte-identical to v1.0/v1.1-no-reid)。仍是 v1.1 纯增量(无 schema_version bump、`required[]` 不变、`additionalProperties:false` 保留)。Pitfall 18 prevented:snapshot 是 export-time truth,后续 registry 变动(re-review / re-cluster / rename)不回写已导出的 `asset.json`。

- **2026-07-25 — `1.2`(v1.2 additive extension,Phases 10-17)** — 第二个 minor bump,纯增量(无 rename / 语义漂移 / 新增 required 字段 — Pitfall 11 prevented)。v1.2 milestone 引入 route-based 三模态音频语义(dialogue/music/sfx)+ 分层复现 prompt(TTS/music-gen/foley)+ 关闭 v1.1 SPEAKER-01 deferral。整个 v1.2 milestone(phases 10-17)共享此版本号。**Phase 10 spike outcomes reshape three field shapes**(见下方 deviations,empirical basis)。变更:
  - **3 个新 schema**:`audio_semantic.schema.json`(per-shot dialogue/sfx + reproduction prompts;`word_level_experimental` flag)、`speakers.schema.json`(`^spk_[0-9]{3}$` NEW acoustic ID space,nullable `char_id` link)、`speaker-edits.schema.json`(HITL round-trip,mirror `registry-edits` + 新 `link_mappings`)。
  - **`asset.schema.json` additive**:新增 optional `data.audio_semantic` / `data.speakers`(JSON 路径)。`required[]` 与 v1.0/v1.1 byte-identical(仍 5 keys)。
  - **`schema_version` pattern 不变**(`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`)— 版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.2"`(line 55),非 schema `const`(否则拒绝 v1 minimal fixture `"1"`,破坏 CONTRACT-09)。
  - **Phase-10-informed deviations**(NON-NEGOTIABLE,empirical basis):
    - **instruments field OMITTED** — MUS-04 deferred v1.3。MERT-v1-95M 无 instrument classifier head(spike 仅产出 duration-correlated K-means clusters + 768-d embedding L2 norms);PANNs Cnn14 zenodo-blocked at spike time。Phase 12+ route host 需要真实 MIR classifier 才能解锁。schema 全文不含英文 `instruments` key(只在 SPEC prose 中文「乐器」指代)。
    - **`dialogue.emotion` = `type:["string","null"]`**(NOT enum)+ `emotion_confidence: ["number","null"]`(0..1)。SenseVoice `self_consistency_pct=100%` 是 label-stability proxy,NOT calibrated accuracy(DIA-04 ship-nullable+confidence)。Closed 7-class enum 会 over-claim 我们没有的 calibration。详见 §10。
    - **`dialogue.words[]` EXPERIMENTAL optional sub-field** — gated behind top-level `word_level_experimental: boolean` flag(DIA-05 ship-experimental)。WhisperX boundary drift median 101.5ms(<200ms ship threshold)但 aggregate per-word drift 是 metric-definition artifact(`word_start − segment_start` inflates for interior words;Phase 12 refines)。Segment-level remains SLA path;consumers SHOULD graceful-degrade 到 segment-only 当 `word_level_experimental:false`。
  - **`speakers.speakers[].spk_id` 使用 NEW `^spk_[0-9]{3}$` acoustic ID space**(NOT `^char_[0-9]{3}$` — deliberate disjoint to avoid identity-signal conflation;closes v1.1 SPEAKER-01 deferral via Phase 13 HITL linking)。
  - **向后兼容**:`spec/fixtures/minimal/`(v1)仍 6/6 绿;`spec/fixtures/v1.1/`仍 10/10 绿;`spec/fixtures/v1.2/`(12 文件)新增;`scripts/verify_contract.py` `_cross_version_check` 实测三向兼容(v1.0↔v1.1↔v1.2 forward 0 errors;backward 仅 additionalProperties errors → 0 non-additive errors);`speakers.char_id ⊆ characters.id` consistency GREEN。
  - **`fidelity_disclaimer`**:见 §10 — 复现 prompt 是 regeneration 友好的 NL 描述(非源音频精确逆向),per-modality 估算 TTS~70%/music-gen~60-75%/foley~80%(AF-01 缓解)。prose 层(two-tier authority),非 schema field。

- **2026-08-19 — `1.3`(v1.3 additive extension,Phases 18-22)** — 第三个 minor bump。与前两个 minor bump 的「纯增量」不同,**本条目诚实记录两处非纯 property-delta 的变更** — `generator.warnings.items` 类型加宽(string → `string | {code, detail}` 双形)与 `data.roundtrip` object 值挂载(v1.x 首个 object 值的 `data.*` 挂载)— 两者**对旧数据仍是 additive**(v1.0-v1.2 资产的纯文本 warnings 对加宽后的 items 天然合法;无 roundtrip 输入跑导出,v1.2 及以前 12 个数据文件 byte-identical),但不是「新增 optional property」式的纯增量,backward 证明的过滤规则因此同步扩展(见下方向后兼容 bullet)。整个 v1.3 milestone(phases 18-22)共享此版本号 — Phase 18 锁契约,Phase 19-22 实现 producer/scorer/consumer。变更:
  - **1 个新 schema**:`roundtrip.schema.json`(per-shot h3 重生成 ref + `scores{midframe_sim, judge}` 双信号打分 + `verdict{accepted/rejected}`;8 层 `additionalProperties:false`;阈值不进 schema — two-tier authority。形状文档见 §5.10 **Round-trip**)。
  - **`asset.schema.json` additive,两处 delta(诚实记录)**:
    - **`generator.warnings.items` 加宽** — 从 `{"type":"string"}` 加宽为 `anyOf: [string, {code, detail}]`,**v1.x 首个 items 类型加宽**。`code` 是 closed enum `{comfyui_unreachable, vram_insufficient, scorer_model_missing}`(RT-04 点名的三种 roundtrip 缺席因由,机器可 grep),`detail` optional(degrade 记因最小单元是 code)。"no PII, no auth tokens" 条款保留。
    - **新增 optional `data.roundtrip` object** `{path, accepted_count, rejected_count}` — **v1.x 首个 object 值的 `data.*` 挂载**(file ref + verdict 统计:消费端不开 sidecar 即可渲染 round-trip 概览;per-shot 数据留在 `roundtrip.json`,不内嵌)。`data.required` 仍为 5 keys 不变(`data.properties` 现 10 keys)。
  - **`schema_version` pattern 不变**(`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`)— 版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.3"`(line 59,本条目写作时 grep 实测;README v1.2 小节所引 "line 55" 在 v1.3 已过时),非 schema `const`(否则拒绝 v1 minimal fixture `"1"`,破坏 CONTRACT-09)。
  - **CONTEXT-locked decisions**(Phase 18 18-CONTEXT 锁定):
    - **`judge.attribution` closed enum 三分类** `{prompt_faithful, model_diverged, prompt_underspecified}` — SCORE-02 三分类是自有分类学(非未校准外部模型输出),enum 使 SCORE-03「rejected 占比可审计」机器可查;与 v1.2 `emotion` free-string 判例不矛盾(那是未校准的模型标签)。
    - **`scores.midframe_sim` 必带 `model` 标识** — clip/siglip 变体不可跨模型比较,不标 model 名的分数不可审计。
    - **`judge` 无连续分** — 分类器非回归器,连续相似度分是伪精度;只有 attribution + confidence + reason 三件套。
    - **`shots[]` 结果集语义,无 pending/rendering 任务态** — 只收「有产物」的 shot;regen 失败收录为 `status{state:failed, error}`;未尝试 = 缺席(schema 是结果集不是任务队列)。
    - **regen 元数据 minimal** — 帧率/总帧数/随机种子/完整 workflow 参数不收(h3 workflow 是 kst 外部资产,不契约化;只收 5-tuple + optional `duration_sec`/`width`/`height`)。
  - **向后兼容**:`spec/fixtures/minimal/`(v1)6/6、`v1.1/` 10/10、`v1.2/` 12/12 仍全绿(`spec/validate.py` 四阶 gate:minimal 6 / v1.1 10 / v1.2 12 / v1.3 13,全部 failures=0);`spec/fixtures/v1.3/` 13 文件新增(**11 个 v1.2 substrate 文件 byte-copied(diff-clean)+ `asset.json` 四点编辑 + `roundtrip.json` 新增**);`scripts/verify_contract.py` `_cross_version_check` 实测四向兼容(**v1.0↔v1.1↔v1.2↔v1.3** forward 0 errors;backward 0 non-additive errors — **excluding documented v1.3 deltas**:`data.roundtrip` 新键 + warnings items 加宽,过滤规则按 error path 精确豁免,注入 `asset_type` const 漂移的负测试仍 FAIL 证明过滤不盲);无 roundtrip 输入跑 `build_asset_dict`,data 块 keys 与 v1.2 时代逐键等价(byte-identical-absent 红线,data-keys smoke 证明)。
  - **`fidelity_disclaimer`**:见 §10 v1.3 三层(§10.5)— accepted = 「h3 可复现」≠「prompt 完美」;rejected 是 hard negatives + h3 能力边界测绘数据(非垃圾);judge attribution 是模型判断带 confidence(非 ground truth);accepted 双阈值由 Phase 21 校准后锁定,校准前本 SPEC 不给数值。prose 层(two-tier authority),非 schema field。

---

## 5. The 5 Canonical Data Shapes (SPEC-01)

每种形状都列出:生产端脚本、字段级类型表(名称 / 类型严格对齐 schema)、enum 值(如有)、最小 JSON 片段、参考 schema 文件。

> **v1.1 (Phase 5):** §5.1–§5.5 是 v1.0 的 5 个 required 数据形状;新增 §5.6 **Characters** + §5.7 **Props** 两个 optional 跨镜注册表形状(仅 re-id 跑过且 HITL 审阅后 emit)。registry 是 pipeline-internal 草稿,非 canonical asset 数据形状,故不在此列(见 §1 schema 索引)。

> **v1.2 (Phase 11):** 新增 §5.8 **Audio Semantic** + §5.9 **Speakers** 两个 optional 音频支路形状(仅 route-host round-trip 跑过且条件字段达标后 emit)。`speaker-edits` 是 HITL round-trip 工作产物,非 canonical asset 数据形状,故不在此列(见 §1 schema 索引)。这两个形状的字段保真度受 Phase-10 spike outcomes 限制(见 §10 **Fidelity Disclaimer**)— emotion=calibrated estimate、word-level=experimental、instruments=absent。

> **v1.3 (Phase 18):** 新增 §5.10 **Round-trip**(optional — 仅 Phase 20/21 regen+scoring 往返后 emit)。verdict 的解释边界受 §10 v1.3 三层 Fidelity Disclaimer 约束 — accepted = 「h3 可复现」≠「prompt 完美」,rejected 是 hard negatives,attribution 是模型判断带 confidence(非 ground truth)。

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

### Audio Semantic (`1.2`)

**Producer:** `audio/call_audio_analysis.py`(Phase 12 + Phase 15 pipeline producer,route-host 往返成功后写 `audio_semantic.json` per-shot 三模态 + reproduction prompts)
**Consumers:** `html/gen_*_html.py`(Phase 16 HTML gallery — modality 标签 + 复现面板)、画布集合节点(Phase 17 — 同上)
**顶层形状:** JSON 对象 — `schema_version` + `word_level_experimental` 顶层 flag + `shots[]` 数组(per-shot 三模态 dialogue/sfx + reproduction 分层 prompt)。v1.2 全新数据文件;v1.0/v1.1 资产缺省(`asset.json#data.audio_semantic` absent),仍合法(graceful-degrade)。字段保真度受 Phase-10 spike outcomes 限制(见 §10 **Fidelity Disclaimer**)。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string (`^(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$`) | ✓ | 与 `asset.json#schema_version` 同源;producer emit `"1.2"`,pattern 保持宽松以兼容 `"1"`/`"1.1"` |
| `word_level_experimental` | boolean | — | 顶层 flag:true 当且仅当任一 `shots[].dialogue.words[]` 非空。Consumers(画布/HTML)先读此字段,false 时 graceful-degrade 到 segment-level。DIA-05 ship-experimental 锁定 |
| `shots[]` | array\<object\> | ✓ | Per-shot 音频语义条目,`shot_id` 交叉引用 `shots.json#id` |
| `shots[].shot_id` | integer (≥1) | ✓ | 仅此字段 required —— 其余全部 optional 以支持 route-down graceful-degrade |
| `shots[].start_sec` / `end_sec` / `duration` | number (≥0) | — | 与 `shots.json` 对应条目一致(advisory;consumer 可重读 `shots.json`) |
| `shots[].dialogue` | object | — | Per-shot 对话模态(可缺席 — 非语音 shot 不 emit)。所有字段 optional。**`music` 子对象在 v1.2 schema 中 OMITTED**(instruments 字段缺席 → 无音乐内容可契约;future slot 仅在本文档记录,schema `additionalProperties:false` 拒绝) |
| `shots[].dialogue.text` | string | — | Segment-level 转录文本(来自 `transcript.json` 的 segment.text,此处重复以供 consumers 单文件渲染) |
| `shots[].dialogue.spk_id` | string (`^spk_[0-9]{3}$`) \| null | — | 说话人 ID(交叉引用 `speakers.json#speakers[].spk_id`)。NULLABLE — 未做 diarize 或旁白/群杂未聚类时为 null |
| `shots[].dialogue.emotion` | string \| null | — | Free-string emotion label(SenseVoice 实测:HAPPY/ANGRY/NEUTRAL/SAD/emo_unk)。**NOT enum** — Phase 10 spike 证实 SenseVoice self_consistency=100% 是 label-stability 代理,NOT calibrated accuracy(DIA-04 ship-nullable+confidence;闭枚举会 over-claim)。详见 §10 |
| `shots[].dialogue.emotion_confidence` | number (0..1) \| null | — | Emotion 置信度(`self_consistency_pct / 100`)。emotion 非 null 时通常填;emotion 为 null 时此字段也 null |
| `shots[].dialogue.events` | array\<string\> | — | SenseVoice 8-event 标签:`Speech`/`BGM`/`Applause`/`Laughter`/`Cry`/`Sneeze`/`Breath`/`Cough`。Free-string(not enum)保留 forward-compat |
| `shots[].dialogue.words[]` | array\<object\> | — | **EXPERIMENTAL** Word-level timestamps(WhisperX wav2vec2 align)。顶层 `word_level_experimental=true` 时才允许非空。Per-word drift metric 是 definition artifact(Phase 12 精化)。详见 §10 |
| `shots[].dialogue.words[].start` / `.end` | number (≥0) | ✓ (in `words[]`) | Word 起止时间(秒,相对音频起点) |
| `shots[].dialogue.words[].text` | string (≥1 char) | ✓ (in `words[]`) | Word 文本 |
| `shots[].dialogue.words[].score` | number (0..1) | — | WhisperX alignment score(缺席 = 未提供) |
| `shots[].sfx` | object | — | Per-shot 非语音音效模态。v1.2 仅携带 SenseVoice non-speech events;PANNs 527-class 折入未来 schema 扩展 |
| `shots[].sfx.events` | array\<string\> | — | Non-speech SenseVoice events(`Speech` 不在此 — 它在 `dialogue.events`)。Subset of `[BGM/Applause/Laughter/Cry/Sneeze/Breath/Cough]` |
| `shots[].sfx.description` | string | — | Free-text NL 描述(foley reproduction prompt 的素材) |
| `shots[].reproduction` | object | — | 分层复现 prompt(model-agnostic NL — 不嵌 NC 权重)。每层可缺席(null 或 omitted),各自携带 confidence + 可选 `fidelity_disclaimer` |
| `shots[].reproduction.tts` / `.music_gen` / `.foley` | `repro_prompt` \| null | — | 各模态复现 prompt(`{text, confidence, fidelity_disclaimer}`)。`text` 必填非空;模态未启用时 emit null 或 omitted |

**`repro_prompt` 子形状(defs):**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `text` | string (≥1 char) | ✓ | NL prompt for the named generator family(TTS: 「成年女性说话者,语气开心愉悦,中文普通话」;foley: 「关门声 + 脚步声」) |
| `confidence` | number (0..1) | — | Prompt 生成的置信度(producer 估算) |
| `fidelity_disclaimer` | string | — | Per-prompt 保真度声明(如 `"TTS ~70% similarity to source voice"`;AF-01 mitigation)。UI 渲染给用户以管理期望 |

**最小片段**(摘自 `spec/fixtures/v1.2/audio_semantic.json`,2-shot 简化样例):

```json
{
  "schema_version": "1.2",
  "word_level_experimental": true,
  "shots": [
    {"shot_id": 1, "start_sec": 0.0, "end_sec": 1.5, "duration": 1.5,
     "dialogue": {"text": "你好世界", "spk_id": "spk_001",
                  "emotion": "HAPPY", "emotion_confidence": 1.0,
                  "events": ["Speech"],
                  "words": [{"start": 0.0, "end": 0.5, "text": "你", "score": 0.99}]},
     "sfx": {"events": [], "description": ""},
     "reproduction": {"tts": {"text": "成年女性说话者,语气开心愉悦,中文普通话,节奏自然",
                              "confidence": 0.7,
                              "fidelity_disclaimer": "TTS ~70% similarity to source voice (AF-01 mitigation)"},
                      "music_gen": null, "foley": null}},
    {"shot_id": 2, "start_sec": 1.5, "end_sec": 3.0, "duration": 1.5,
     "dialogue": {"text": "测试一句", "spk_id": "spk_002",
                  "emotion": "emo_unk", "emotion_confidence": 1.0, "events": [], "words": []},
     "reproduction": {"tts": null, "music_gen": null, "foley": null}}
  ]
}
```

Reference schema: `spec/schemas/audio_semantic.schema.json`

### Speakers (`1.2`)

**Producer:** `registry/link_speakers.py`(Phase 13 HITL apply,镜像 v1.1 `apply_edits.py`,把 confirmed `speakers.json` 流向 canonical)
**Consumers:** `html/gen_*_html.py`(Phase 16 — speaker→character chip 渲染)、画布集合节点(Phase 17 — 同上)
**顶层形状:** JSON 对象 — `speakers[]` 数组,每条目含 acoustic `^spk_[0-9]{3}$` ID + 可选 `^char_[0-9]{3}$` link + `review_state` + `turns[]`。v1.2 全新数据文件;v1.0/v1.1 资产缺省(`asset.json#data.speakers` absent),仍合法。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `speakers[]` | array\<object\> | ✓ | Per-speaker 条目。即使在最简 route-down degrade 场景也至少 emit 空 array(与 `asset.json#data.speakers` 的 file-existence gating 解耦) |
| `speakers[].spk_id` | string (`^spk_[0-9]{3}$`) | ✓ | Immutable 说话人声学 ID(零填充 3 位)。Pattern 在 Phase 11 锁定;一旦 confirmed 永不重用或重排版(Pitfall 17 — 保证 `audio_semantic.json#dialogue.spk_id` 引用永不悬空)。**刻意 disjoint from `^char_[0-9]{3}$`** — 声学身份(pyannote/WhisperX diarize embedding)≠ 视觉身份(DINOv2 char_ embedding);SPEAKER-01 Phase 13 核心目标 |
| `speakers[].char_id` | string (`^char_[0-9]{3}$`) \| null | — | Linked character ID(NULLABLE for 旁白/群杂 speakers,DIA-03)。非 null 时 MUST 解析到 `characters.json#id` 中 `review_state='confirmed'` 的条目(`verify_contract.py` `_fixture_consistency_check` 强制)。SPEAKER-01 HITL `link_speakers.py` 写入此字段 |
| `speakers[].total_speech_sec` | number (≥0) | — | 该说话人的累计发言时长(秒)。由 producer 聚合 `turns[]` 计算(advisory;下游可重算) |
| `speakers[].review_state` | enum | ✓ | 同 characters:`proposed` / `confirmed` / `rejected`。**仅 `confirmed` 流向下游渲染**(Pitfall 7);`rejected` = 软删除(ID 保留维护引用完整性) |
| `speakers[].turns[]` | array\<object\> | — | 该说话人的发言区间列表(shot-level 定位)。可缺席 — diarize 失败但 spk_id 已分配时仍 emit spk_id(advisory speaker inventory)。空 array 合法 |
| `speakers[].turns[].shot_id` | integer (≥1) | ✓ (in `turns[]`) | Shot ID(交叉引用 `shots.json#id`) |
| `speakers[].turns[].start_sec` / `.end_sec` | number (≥0) | ✓ (in `turns[]`) | Turn 起止时间(秒,相对音频起点) |

**`review_state` enum:** 同 characters §5.6 — `proposed`(diarize 草稿默认值)/ `confirmed`(HITL 审阅确认,唯一流向下游)/ `rejected`(审阅否决,软删除 ID 永不重用)。

**最小片段**(摘自 `spec/fixtures/v1.2/speakers.json`,2 speakers — spk_001 链到 char_001,spk_002 旁白 char_id=null):

```json
{
  "speakers": [
    {"spk_id": "spk_001", "char_id": "char_001",
     "total_speech_sec": 1.5, "review_state": "confirmed",
     "turns": [{"shot_id": 1, "start_sec": 0.0, "end_sec": 1.5}]},
    {"spk_id": "spk_002", "char_id": null,
     "total_speech_sec": 1.5, "review_state": "confirmed",
     "turns": [{"shot_id": 2, "start_sec": 1.5, "end_sec": 3.0}]}
  ]
}
```

Reference schema: `spec/schemas/speakers.schema.json`

### Round-trip (`1.3`)

**Producer:** Phase 20(h3 复现客户端 — per-shot `regen` 条目 + `status` 失败记录,pending)+ Phase 21(scorer / verdict 合并 — `scores` 与 `verdict` 写入,pending)。Phase 18 仅锁契约,不写生产者。
**Consumers:** Phase 22(gallery round-trip 审阅面板 — 原片段 vs 重生成并排 + 分数 + HITL accept/reject 按钮;dataset 导出。均 pending)。

**顶层形状:** JSON 对象 — `schema_version` + `shots[]` **结果集**。`shots[]` 只收「有产物」的 shot:regen 成功的带 `regen` ref(可能已打分 / 未打分 — degrade 中间态合法,只有 score 没 verdict 也合法);regen 失败的收录为 `status{state: failed, error}`;**未尝试的 shot 不在数组里(缺席 = 未尝试)** — schema 是结果集不是任务队列,刻意无 pending/rendering 任务态。v1.0/v1.1/v1.2 资产缺省(`asset.json#data.roundtrip` absent),仍合法(graceful-degrade);无 roundtrip 输入跑导出 byte-identical-absent。阈值不进 schema(SCORE-03 的 accepted 双阈值 Phase 21 校准后才存在 — 见 §10)。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string (`^(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$`) | ✓ | 与 `asset.json#schema_version` 同源;producer emit `"1.3"`,pattern 宽松兼容 `"1"`/`"1.1"`/`"1.2"` |
| `shots[]` | array\<object\> | ✓ | Per-shot round-trip 条目,`shot_id` 交叉引用 `shots.json#id` |
| `shots[].shot_id` | integer (≥1) | ✓ | 仅此字段 required — 其余 optional 支持 degrade 中间态(regen 成功未打分 / 有 score 无 verdict) |
| `shots[].regen` | object | — (与 `status` 互斥) | 重生成视频 ref(REGEN-02 可复现可审计 tuple,mirror WR-04)。与 `status` 二选一:有产物用 `regen`,失败用 `status`(互斥由 producer 保证,schema 不做 if/then 硬约束) |
| `shots[].regen.path` | string (`^(?!.*\.\.)([^/]+/)*roundtrip/…\.mp4$`) | ✓ (in `regen`) | 重生成 mp4 相对路径,相对 asset root(建议 canonical 布局 `roundtrip/shot_XXX.mp4`;anti-traversal,拒绝 `..`/绝对路径/Windows 保留字符) |
| `shots[].regen.video_content_hash` | string (`^[0-9a-f]{16}$`) | ✓ (in `regen`) | 源视频内容 hash(sha256(首1MB+尾1MB+filesize) hex 前 16 位 — `analysis/call_shot_analysis.py` 同款;cache invalidation 级,非安全 hash) |
| `shots[].regen.engine_name` / `engine_version` / `prompt_version` | string (≥1 char) | ✓ (in `regen`) | 复现引擎名(如 `MiniMaxH3ImageToVideo` / `h3-fl2va`)、引擎版本(ComfyUI workflow/模型版本标识)、prompt 生成器版本 |
| `shots[].regen.duration_sec` / `width` / `height` | number (≥0) / integer (≥1) / integer (≥1) | — | 实际时长与实际分辨率(REGEN-04 降分辨率模式记录实际值)。帧率/总帧数/随机种子/完整 workflow 参数**不收**(h3 workflow 是 kst 外部资产,不契约化) |
| `shots[].status.state` | enum `["failed"]` | ✓ (in `status`) | 刻意单值 enum — 不加任务态(结果集语义,CONTEXT 锁) |
| `shots[].status.error` | string (1..2000) | ✓ (in `status`) | 失败原因(operator-facing;无凭据无 PII — mirror warnings 惯例。`maxLength: 2000` 是 T-18-02 长度上界:模型/引擎产出文本未来流入 Phase 22 HTML,先 bound) |
| `shots[].scores` | object | — | 双信号打分(SCORE-01/02)。`midframe_sim` 与 `judge` 两个子对象**可独立缺席**(degrade 中间态) |
| `shots[].scores.midframe_sim.score` | number (0..1) | ✓ (in `midframe_sim`) | 中段帧相似度(25%-75% 时窗 — 显式排除被 fl2va condition 的首尾帧;SCORE-01 帧 embedding 轨迹相似度) |
| `shots[].scores.midframe_sim.model` | string (≥1 char) | ✓ (in `midframe_sim`) | similarity model 标识(如 `clip-vit-l14-336`)。**必带** — clip/siglip 变体不可跨模型比较,不标 model 名的分数不可审计 |
| `shots[].scores.judge.attribution` | enum | ✓ (in `judge`) | 三分类 closed enum(逐字对齐 schema):`prompt_faithful` / `model_diverged` / `prompt_underspecified` — SCORE-02 自有分类学,enum 使 SCORE-03 rejected 占比机器可审计 |
| `shots[].scores.judge.confidence` | number (0..1) | ✓ (in `judge`) | judge 置信度(模型自报,**非校准精度** — 见 §10 第③层) |
| `shots[].scores.judge.reason` | string (1..2000) | ✓ (in `judge`) | 归因理由(模型产出 NL 文本;`maxLength: 2000` = T-18-02 长度上界) |
| `shots[].verdict.decision` | enum `accepted` / `rejected` | ✓ (in `verdict`) | accepted = 「h3 可复现」≠「prompt 完美」(§10 第①层);rejected 永不删除(DATASET-01) |
| `shots[].verdict.source` | enum `auto` / `human` | ✓ (in `verdict`) | auto = SCORE-03 校准后的自动判;**`human` = PRESENT-01 HITL 按钮覆盖**(DATASET-02 溯源可审计) |
| `shots[].verdict.decided_at` | string (ISO-8601 UTC) | — | mirror `asset.generator.generated_at` 风格(纯 string + description,不加 `format` 关键字) |

**最小片段**(摘自 `spec/fixtures/v1.3/roundtrip.json`,2-shot 简化样例 — shot 1 = full/auto-accept;shot 2 = degrade/human-reject,演示 optional 字段缺席与 `decided_at`):

```json
{
  "schema_version": "1.3",
  "shots": [
    {"shot_id": 1,
     "regen": {"path": "roundtrip/shot_001.mp4", "video_content_hash": "a1b2c3d4e5f60718",
               "engine_name": "MiniMaxH3ImageToVideo", "engine_version": "h3-fl2va-v4",
               "prompt_version": "prompts-0.3.0", "duration_sec": 4.8, "width": 832, "height": 480},
     "scores": {"midframe_sim": {"score": 0.87, "model": "clip-vit-l14-336"},
                "judge": {"attribution": "prompt_faithful", "confidence": 0.8,
                          "reason": "中段帧主体运动与运镜方向同 prompt 描述一致，场景元素齐全"}},
     "verdict": {"decision": "accepted", "source": "auto"}},
    {"shot_id": 2,
     "regen": {"path": "roundtrip/shot_002.mp4", "video_content_hash": "0f1e2d3c4b5a6978",
               "engine_name": "MiniMaxH3ImageToVideo", "engine_version": "h3-fl2va-v4",
               "prompt_version": "prompts-0.3.0", "duration_sec": 4.8},
     "scores": {"midframe_sim": {"score": 0.42, "model": "clip-vit-l14-336"}},
     "verdict": {"decision": "rejected", "source": "human", "decided_at": "2026-08-19T00:00:00Z"}}
  ]
}
```

Reference schema: `spec/schemas/roundtrip.schema.json`

**渲染安全与 manifest 挂载说明:** `judge.reason` 与 `status.error` 是模型/引擎产出的自由文本 — Phase 22 HTML 渲染 **MUST** 先经 `_esc()` HTML 转义再插入 DOM(PRESENT-01 XSS 硬化义务预告;schema 层已先做 `maxLength: 2000` 长度上界,bound 而非 forbid)。manifest 侧:`asset.json#data.roundtrip` 是 **object** 挂载(v1.x 首个 object 值的 `data.*` 挂载)`{path: "roundtrip.json", accepted_count, rejected_count}` — `path` 指向本 sidecar,两个 count 是 `shots[].verdict.decision` 的计数统计(消费端不开 sidecar 即可渲染 round-trip 概览);per-shot 数据留在 `roundtrip.json`,**不内嵌** asset.json。producer(`scripts/export_asset.py`)仅在 roundtrip.json 存在且可解析时 emit(malformed → `[warn]` + OMIT,不持久化可疑统计 — mirror WR-05;不做挂载前 schema 校验,完整 gate 在 `spec/validate.py` V13 阶与 `verify_contract.py` producer mode)。accepted 判定阈值(midframe_sim + judge 双信号)由 Phase 21 ep01 ≤20 镜抽样校准后锁定 — **校准前本 SPEC 不给数值**(见 §10;two-tier authority:阈值是散文 + 校准报告,永不进 schema)。

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

## 10. Fidelity Disclaimer (`1.2` + `1.3` — AF-01/AF-02/AF-03 mitigation)

> 本节是 v1.2 milestone 引入的 prose-layer 保真度声明。**它不是 schema field** — `fidelity_disclaimer` 在 schema 中只作为 `reproduction.{tts,music_gen,foley}.fidelity_disclaimer` 的 per-prompt machine-checkable string 字段出现(下游 UI 渲染给用户管理期望);本节是 producer/operator/consumer 必读的人读概览,属于 two-tier authority 的人读半边(schema 是机器真源,prose 与 schema 冲突时 schema 为准)。
>
> 消费端(Phase 17 画布 / Phase 16 HTML gallery)**MUST 在信任任何 v1.2 audio field 前读完本节**。emotion/word-level/instruments 三个字段的保真度边界由 Phase 10 spike outcomes 锁定(见 `.planning/research/audio-spike-report.md`),non-obvious to a reader who only reads the schemas。
>
> v1.3(Phase 18)追加 §10.5 round-trip verdict 三层声明 — 消费端(dataset 消费者 / Phase 22 gallery 审阅者)**在信任任何 `roundtrip.json` verdict 前同样必读**。

### 10.1 AF-01 — 复现 prompt 是 regeneration 友好的 NL 描述(explicit out-of-scope)

**v1.2 复现 prompt(`audio_semantic.shots[].reproduction.{tts,music_gen,foley}`)是 regeneration 友好的 NL 描述,不是源音频的精确逆向。**

任何承诺绝对化复现语义的短语(中文或英文 — 典型如「完美/精确/绝对 + 复刻/复原/重建/复现」式中文组合与 perfect/exact + reconstruct/restore 式英文组合;完整禁用清单以 AF-01 invariant grep 守门为准)— 在 `README.md` / `SPEC.md` / `html/*.html` 中 **FORBIDDEN**(AF-01 invariant)。这些短语对内容创作者构成虚假承诺 — TTS 复现的是「相似音色 + 相同情绪文本」的 regeneration 而非 source-voice 克隆;music-gen 复现的是「相似节奏 + 调性」的 regeneration 而非 source-audio 拷贝;foley 复现的是「同类音效描述」的 regeneration 而非 source-foley 还原。

> 本节用「绝对化复现措辞」作统称;具体禁用短语以 AF-01 invariant grep 守门(SPEC + README 中绝对化措辞必须 0 匹配 — 连本节列举式的「提及」也不豁免,grep 无法区分使用与提及)。

所有复现 prompt 字段在 schema 层都带 `confidence` (0..1) + 可选 `fidelity_disclaimer` (per-prompt string,UI 渲染给用户);HTML/SPEC 的展示标签 MUST 显式「estimated」前缀(Phase 16 PRESENT-01)。

### 10.2 Per-modality 估算(TTS ~70% / music-gen ~60-75% / foley ~80%)

基于 Phase 10 spike 经验 + 模型卡声明 + 业界经验,我们对 v1.2 三层复现 prompt 给出以下 calibrated 估算(producer 把这些写进 `reproduction.{layer}.fidelity_disclaimer`):

| 模态 | 相似度估算 | 含义 | 限制 |
|------|-----------|------|------|
| **TTS** | ~70% similarity to source voice | 音色相似度 + 情绪标签复现 | model-agnostic prompt 不保证具体 speaker identity;同一角色不同声优的 TTS 模型可能产出显著差异 |
| **music-gen** | ~60-75%(harmonic / rhythmic 相似) | 节奏 / 调性 / 乐器大体相似 | 音色因 model-agnostic prompt 不保证;v1.2 不带 instruments 字段 → 描述层仅靠 free-text NL |
| **foley** | ~80%(音效描述相对 well-defined) | 同类音效 + 类似时序 | 复杂环境音(混合多源)相似度下降;描述层的歧义大于 TTS/music-gen |

这些数字是 **calibrated estimate**(校准估计),不是 rigorous mAP / F1。任何把它们伪装成 rigorous 精度指标的说法都违反 AF-02/AF-03 anti-fabrication 红线。

### 10.3 Phase-10-informed 字段保真度

#### `dialogue.emotion` = calibrated estimate(NOT rigorous accuracy)

SenseVoice `self_consistency_pct=100.0`(Phase 10 SER spike, N=30 ep01 stratified)是 **label-stability proxy**(3 次 VAD-分桶运行得到相同 emotion 标签),**NOT rigorous macro-F1** against developer-annotated ground truth。Phase 10 methodology_ab 走 calibrated estimate + 对 30 段做定性 sanity review(情绪标签 vs 对白文本 coherent);rigorous macro-F1 需要 developer-annotated 30-segment ground truth(Phase 12+,~1hr 人工,deferred)。

> **Calibrated estimate statement(逐字镜像 `audio-spike-report.md` §1):** The `self_consistency_pct=100.0` is a calibrated estimate of SenseVoice's label stability across VAD-segmentation variants on these 30 Chinese animation clips. It is NOT a true macro-F1 against human ground truth. A model that deterministically predicts `NEUTRAL` on every clip would score 100% self-consistency yet unknown real accuracy. Cross-domain accuracy on other Chinese animation episodes may differ.

**Schema 形态后果:** `emotion` 是 `type:["string","null"]`(NOT 7-class enum),配对 `emotion_confidence: ["number","null"]` (0..1)。Closed enum 会 over-claim 我们没有的 calibration。

#### `dialogue.words[]` = EXPERIMENTAL(word-level timestamps)

WhisperX wav2vec2 forced alignment 在 faster-whisper/openai-whisper 既有 segments 上对齐。**Boundary drift median = 101.5ms(<200ms ship threshold ✓)**;但 **aggregate per-word drift 是 metric-definition artifact**(`word_start − segment_start` inflates for interior words — interior words 的 segment_start 是 segment 边界,与 word_start 的距离天然大于 boundary words)。Segment-level remains SLA path;Phase 12+ 会用 boundary drift(而非 per-word drift)精化 metric。

**Schema 形态后果:** `words[]` 是 optional sub-field,gated behind 顶层 `word_level_experimental: boolean` flag。Consumers SHOULD graceful-degrade 到 segment-only 当 `word_level_experimental:false` 或消费者对 word-level 边界精度敏感。

#### instruments field OMITTED(v1.2 schema 不含此字段)

**MUS-04 deferred v1.3。** Phase 10 MIR spike 证实:(1) `m-a-p/MERT-v1-95M` 是音频 encoder,**没有乐器 classifier head** — spike 仅产出 5-cluster K-means 聚类 + 768-d embedding L2 范数,这些 clusters 与 shot DURATION 强相关(模型 artifact 而非音乐内容信号);(2) `Cnn14_mAP=0.431.pth` (PANNs) 在 spike 期 zenodo-blocked(`mir_panns_ep01.json status=blocked`)。

**Schema 形态后果:** v1.2 全套 schema 不含 `instruments` 字段(也不含 `instrument_labels` / `instruments_detected` 等同义变体)。schema 全文用中文「乐器」/「MIR label」指代以避开英文 grep —— 任何在 schema JSON 中找到的英文 `instrument*` key 都是 bug。Phase 12+ route host 需要真实 MIR classifier(可达的 PANNs、fine-tuned MERT head、或专门的中文民族乐器模型)才能在 v1.3 解锁此字段。

### 10.4 Two-tier authority 重申

`fidelity_disclaimer` 是 **SPEC prose**(人读概览),**NOT** schema field。机器可校验的 nullable+confidence+per-prompt disclaimer 在 schema:

- `audio_semantic.schema.json#shots[].dialogue.emotion{,_confidence}`(nullable + confidence)
- `audio_semantic.schema.json#shots[].reproduction.{tts,music_gen,foley}.{confidence,fidelity_disclaimer}`(per-prompt machine-checkable string)
- `speakers.schema.json#speakers[].{char_id,review_state}`(nullable link + state gating)

Schema 与 SPEC 冲突时 **schema 为准**(本节 §1 Authority 已锁定)。本文档的任何与 schema 不一致都视为缺陷,必须修复。本节的存在 **不放松** schema 严格性(`additionalProperties:false` 全程开启),也不放松消费端的 graceful-degrade 运行时义务(§4)。

### 10.5 v1.3 Round-trip verdict 三层保真度声明(Phases 18-22)

v1.3 的 round-trip verdict(`roundtrip.json#shots[].verdict`)引入新的过度信任风险。消费端(dataset 消费者 / Phase 22 gallery 审阅者 / 未来贡献者)**MUST 在信任任何 verdict 前读完以下三层**:

**第①层 — accepted = 「h3 可复现」≠「prompt 完美」。** `verdict.decision = accepted` 的判定对象是「MiniMax H3 fl2va 能否在给定首尾帧条件下重生成出与原片段中段相似的动态」,**不是**「prompt 完整刻画了原片段」。fl2va 是首尾帧条件渲染 — 首尾帧已被 condition 注入,相似度信号集中在中段(25%-75% 时窗);这带来**幸存者偏差**:prompt 中未被中段渲染体现的维度(音效、部分材质细节、画外信息、prompt 各 facet 的措辞差异)不可由此 verdict 证伪。把 accepted 读作「prompt 无懈可击」会系统性高估 prompt 质量 — accepted 的正确读法是「这条 prompt 在 h3 的能力范围内可复现到中段相似」。

**第②层 — rejected 是 hard negatives + h3 能力边界测绘数据,非垃圾。** `verdict.decision = rejected` 的条目**必须保留**(DATASET-01;rejected 永不删除):它们是 rejection sampling 的 **hard negatives**(对训练「区分好 prompt 与欠约束 prompt」的判别有价值),同时是 h3 引擎**能力边界的测绘数据**(`judge.attribution = model_diverged` 的条目刻画「prompt 足够好但引擎做不到」的边界 — 这些边界样本本身是 h3 迭代的基准)。SCORE-03 的 rejected 占比审计依赖此语义;把 rejected 当垃圾丢弃会同时丢掉这两类价值,并让 accepted 占比失去解释基线。

**第③层 — judge attribution 是模型判断带 confidence,不是 ground truth。** `scores.judge.attribution` 三分类(`prompt_faithful` / `model_diverged` / `prompt_underspecified`)是 SCORE-02 的**自有分类学**,由 VLM judge 产出 — 它是模型判断;配对的 `confidence` 是模型自报置信度,**未校准**(不是校准概率,数值只可序数比较、不可当概率使用)。三分类的边界本身是我们定义的分类学而非客观真值 — 任何把 attribution 当 ground truth 的下游流程(如直接按 `model_diverged` 过滤数据集而不抽查)都在过度信任一个未校准信号。

**附 — accepted 双阈值由 Phase 21 校准后锁定(two-tier authority)。** accepted 的判定阈值(midframe_sim 相似度阈值 + judge 归因规则)**在校准前不存在**:Phase 21 将用 ep01 ≤20 镜抽样校准后锁定,校准报告是阈值的权威载体。本 SPEC 与 schema 在校准前**不给出任何阈值数值** — schema 只装结果(`score` / `attribution` / `confidence` / `decision`),阈值永远活在散文(本节)+ Phase 21 校准报告里,永不进 schema。

---

*Created: 2026-07-20 (Phase 01 Plan 02 — initial publication of the human-readable ShotTimelineAsset contract).*
* schema_version "1" — initial contract. See §4 Changelog for evolution rules.*
* 2026-07-25 (Phase 11 Plan 03 — v1.2 additive extension: §4 Changelog `1.2` + §5.8 Audio Semantic + §5.9 Speakers + §10 Fidelity Disclaimer). schema_version "1.2".*
* 2026-08-19 (Phase 18 Plan 03 — v1.3 additive extension: §4 Changelog `1.3` + §5.10 Round-trip + §10 v1.3 三层 Fidelity Disclaimer). schema_version "1.3".*
