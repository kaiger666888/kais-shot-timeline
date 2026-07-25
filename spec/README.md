# ShotTimelineAsset Spec Directory

`spec/` 是 **ShotTimelineAsset 契约的权威定义方**——机可校验的 JSON Schema(draft 2020-12)+ 自校验的最小样例 + 校验器。生产端(`kais-shot-timeline` Phase 2 导出器)和消费端(`@kais/infinite-canvas` Phase 3 集合节点)都对着这套 schema 实现,无需口口相传字段名/类型/媒体布局。

> Spec directory is the authoritative owner of the ShotTimelineAsset contract. JSON Schema (draft 2020-12) is the lingua franca between Python (producer) and TypeScript (consumer).

## Layout

```
spec/
├── schemas/                       # 13 个机可校验的 JSON Schema 文件(draft 2020-12)
│   ├── shots.schema.json          # 分镜边界列表
│   ├── audio_analysis.schema.json # 每镜 Demucs 4-stem 能量/谱/类型
│   ├── transcript.schema.json     # Whisper 转录段
│   ├── frames.schema.json         # 首尾帧 base64 data URI
│   ├── prompts.schema.json        # 结构化分镜 prompt(v1.1 +character_refs[]/prop_refs[])
│   ├── asset.schema.json          # 自描述 manifest(schema_version + 来源 + 生成器 + 数据清单 + 媒体清单)
│   ├── characters.schema.json     # 跨镜角色注册表(^char_[0-9]{3}$ + looks[])。v1.1
│   ├── props.schema.json          # 跨镜道具注册表(^prop_[0-9]{3}$ + states[])。v1.1
│   ├── registry.schema.json       # re-id 聚类草稿(clusters[] + tier + mean_cosine)。v1.1,pipeline-internal
│   ├── audio_semantic.schema.json # per-shot 三模态音频语义 + reproduction prompts。v1.2
│   ├── speakers.schema.json       # 声学说话人注册表(^spk_[0-9]{3}$ + nullable char_id)。v1.2
│   └── speaker-edits.schema.json  # speaker HITL edits round-trip(link_mappings + merge/split)。v1.2,pipeline-internal
├── fixtures/minimal/              # v1.0 最小样例资产(6 JSON,6 schema 全绿)
│   ├── asset.json
│   ├── shots.json
│   ├── audio_analysis.json
│   ├── transcript.json
│   ├── frames.json
│   └── prompts.json
├── fixtures/v1.1/                 # v1.1 样例资产(10 JSON — 复用 minimal 2-shot + characters/props/registry)。Phase 5
│   ├── asset.json                 # schema_version="1.1" + data/media characters+props
│   ├── shots.json / audio_analysis.json / transcript.json / frames.json  # 复用 minimal substrate(verbatim)
│   ├── prompts.json               # +character_refs[]/prop_refs[]
│   ├── characters.json            # 2 角色(char_001 少女 w/ looks[],char_002 路人 minimal)
│   ├── props.json                 # 1 道具(prop_001 落叶 w/ states[])
│   ├── registry.draft.json        # 3 clusters,one per tier,all review_state=proposed
│   └── registry.edits.json        # HITL edits sample(merge_groups/splits/confirm_ids/reject_ids/renames/type_overrides)
├── fixtures/v1.2/                 # v1.2 样例资产(12 JSON — v1.1 10 文件 byte-copied + audio_semantic + speakers)。Phase 11
│   ├── asset.json                 # schema_version="1.2" + data/media audio_semantic+speakers
│   ├── audio_semantic.json        # per-shot 三模态 + reproduction prompts(2-shot 简化)
│   ├── speakers.json              # 2 speakers(spk_001→char_001,spk_002 旁白 char_id=null)
│   └── (余 9 文件 verbatim 复用 v1.1 substrate)
├── validate.py                    # 校验器(标准库 + jsonschema;minimal 6/6 + v1.1 10/10 + v1.2 12/12 三 pass)
├── README.md                      # 本文件
└── SPEC.md                        # 人读 prose 规范(§1-§10,含 v1.1 §5.6 Characters / §5.7 Props + v1.2 §5.8 Audio Semantic / §5.9 Speakers / §10 Fidelity Disclaimer)
```

## How to validate

```bash
# 默认:minimal fixture 必须 6 条全 [valid],smoke 阶段对 output/ 真实产物宽容校验(仅打印,不影响退出码)
python3 spec/validate.py

# 严格模式:smoke 失败也计入退出码(CI / Phase 2 回归用)
python3 spec/validate.py --strict-smoke
```

预期输出:6 行 `[valid] <shape>`(minimal: asset / shots / audio_analysis / transcript / frames / prompts)+ 9 行 `[valid-v11] <shape>`(v1.1: 上述 6 + characters / props / registry)+ 至少 5 行 `[smoke-valid|smoke-FAIL] <shape>`(只要仓库 `output/` 下有真实生产产物)。minimal 仍 gate 退出码(CONTRACT-09);v1.1 失败也计入(Plan 01 schemas 必须接受 Plan 03 fixtures)。

## Canonical asset layout (CONTEXT D-03)

视频与 stem 音频在资产目录内的**规范命名**(Phase 2 导出器会按此重命名,生产端当前 `stems/htdemucs/<stem>/...` 布局是非规范的):

- 视频:`video.mp4`(资产根或一层子目录下)
- Stems:`stems/vocals.wav`、`stems/drums.wav`、`stems/other.wav`(bass 被剔除——消费端只渲染 vocals/drums/other 三轨)

`asset.schema.json` 用正则 pattern 强制该命名,并拒绝 `..` 路径穿越、绝对路径、Windows 保留字符(T-01-03 缓解)。

## Range-aware HTTP 206 (SPEC-03)

消费端 seek 视频 / stem 时,媒体必须经 **Range-aware HTTP 206 (Partial Content)** 服务访问。生产端现成服务:`scripts/serve.py`(已实现 206,默认端口 8765)。本 phase 不修改该脚本——prose 规范在 Plan 02 `SPEC.md` 中会再次引用。

## Schema 版本与 graceful-degrade 规则 (CONTEXT D-02)

`asset.json` 的 `schema_version` 字段使用 semver-lite(`"1"`、`"1.1"`,非完整 semver)。schema 严格(`additionalProperties: false`),但消费端**必须**在运行时对未知/更新版本做 graceful-degrade:忽略未知字段、渲染已知部分、emit 一个 warning,不要 reject 或 crash。新增字段=minor bump,破坏性变更=major bump(必须在 prose SPEC 中写迁移说明)。规则全文嵌在 `asset.schema.json` 的 `schema_version.description` 与顶层 `$comment` 里。

> **v1.1 (Phase 5) 是首个 minor bump** — 新增 3 个 optional schema(characters/props/registry)+ asset/prompts additive 扩展(全 optional 字段,`required[]` 与 v1.0 byte-identical,Pitfall 11 prevented)。版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.1"`(schema pattern 不变)。详见 `SPEC.md` §4 Changelog。

## v1.2 Update (Phase 11, 2026-07-25)

Contract bumped to `1.2` (pure-additive minor bump; v1.0/v1.1 fixtures remain byte-identical)。这是 v1.2 milestone(phases 10-17)共享的版本号 — Phase 10 audio spike 完成后锁契约,Phase 12-17 实现 producer/consumer。

**3 个新 schema:**

- `audio_semantic.schema.json` — per-shot dialogue/sfx + reproduction prompts(Phase 11;route-host round-trip 跑过后才 emit)。
- `speakers.schema.json` — `^spk_[0-9]{3}$` acoustic speaker registry,带 nullable `char_id` link(Phase 11;NEW acoustic ID space 与 `^char_[0-9]{3}$` 视觉 ID 刻意 disjoint,关闭 v1.1 SPEAKER-01 deferral via Phase 13 HITL linking)。
- `speaker-edits.schema.json` — HITL round-trip edits shape(mirrors `registry-edits.schema.json` + 新 `link_mappings` 作 spk→char N:M 映射;Phase 13 `link_speakers.py` 消费)。

**`asset.schema.json` additive:** 新增 optional `data.audio_semantic` + `data.speakers`(均 NOT 在 `required[]`;v1.0/v1.1 资产缺席 → byte-identical graceful-degrade)。

**`SCHEMA_VERSION = "1.2"` 单一真源** 在 `scripts/export_asset.py:55`(Pitfall 12 prevented — 不在 schema `const` 也不在 validate.py 复制)。

**Phase-10-informed deviations**(NON-NEGOTIABLE,empirical basis — 来自 `.planning/research/audio-spike-report.md`):

- `instruments` field OMITTED(MUS-04 deferred v1.3 — MERT-v1-95M 无 classifier head 仅产出 duration-correlated K-means clusters;PANNs Cnn14 zenodo-blocked at spike time)。schema 全文不含英文 `instruments` key。
- `dialogue.emotion` 是 `type:["string","null"]`(NOT enum)+ `emotion_confidence` nullable(SenseVoice self_consistency=100% 是 label-stability 代理,NOT calibrated accuracy;闭枚举会 over-claim)。
- `dialogue.words[]` 是 EXPERIMENTAL optional sub-field,gated behind 顶层 `word_level_experimental` flag(WhisperX boundary drift median 101.5ms 但 aggregate per-word drift 是 metric-definition artifact;segment-level 仍是 SLA path)。

**12-file fixture** at `spec/fixtures/v1.2/`(10 byte-copied from v1.1 + `audio_semantic.json` + `speakers.json`,使用真实 ep01 spike 数据)。

**Bidirectional cross-version proof** 扩展在 `scripts/verify_contract.py`:`v1.0↔v1.1↔v1.2` forward 0 errors + backward 仅 additionalProperties errors(0 non-additive)+ `speakers.char_id ⊆ characters.id` consistency check GREEN。

**字段保真度边界**(consumers MUST 读 `SPEC.md` §10 Fidelity Disclaimer 后再信任 v1.2 audio 字段):

- 复现 prompt ≠ 绝对化复现 — 任何承诺「绝对复现 / 完美重建 / 精确还原 / perfect clone / exact source match」之类绝对化语义的短语(中文或英文)在 README/SPEC/HTML 中 **FORBIDDEN**(AF-01 invariant,grep 守门 0 匹配)。Per-modality 估算:TTS ~70% / music-gen ~60-75% / foley ~80%。
- `emotion` = calibrated estimate(NOT rigorous macro-F1)。
- `dialogue.words[]` = experimental(segment-level is SLA)。
- `instruments` = absent(deferred v1.3)。

详见 `spec/SPEC.md` §4 Changelog `1.2` entry + §5.8 Audio Semantic + §5.9 Speakers + §10 Fidelity Disclaimer for the full prose。

## Origin / Provenance

- **生产端**:Phase 2 导出器(待实现),把 `output/<video-stem>/` 下的 5 个 JSON + 媒体重命名为 canonical 布局后写出 `asset.json`。
- **消费端**:Phase 3 `@kais/infinite-canvas` 集合节点(跨仓库,`kais-aigc-platform` 上的 `feat/canvas-asset-collection` 分支)。
- **本 phase**:Phase 1,只交付 schema + fixture + 校验器,**不写导出器代码、不写画布消费代码**。

---

*Created: 2026-07-20 (Phase 01 Plan 01)*
*Updated: 2026-07-24 (Phase 05 — v1.1 additive extension: +3 schemas, +spec/fixtures/v1.1/, validate.py dual minimal+v1.1 pass, verify_contract.py EIGHT_SHAPES + cross-version + fixture-consistency)*
