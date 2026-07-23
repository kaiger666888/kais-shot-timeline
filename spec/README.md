# ShotTimelineAsset Spec Directory

`spec/` 是 **ShotTimelineAsset 契约的权威定义方**——机可校验的 JSON Schema(draft 2020-12)+ 自校验的最小样例 + 校验器。生产端(`kais-shot-timeline` Phase 2 导出器)和消费端(`@kais/infinite-canvas` Phase 3 集合节点)都对着这套 schema 实现,无需口口相传字段名/类型/媒体布局。

> Spec directory is the authoritative owner of the ShotTimelineAsset contract. JSON Schema (draft 2020-12) is the lingua franca between Python (producer) and TypeScript (consumer).

## Layout

```
spec/
├── schemas/                       # 6 个机可校验的 JSON Schema 文件(draft 2020-12)
│   ├── shots.schema.json          # 分镜边界列表
│   ├── audio_analysis.schema.json # 每镜 Demucs 4-stem 能量/谱/类型
│   ├── transcript.schema.json     # Whisper 转录段
│   ├── frames.schema.json         # 首尾帧 base64 data URI
│   ├── prompts.schema.json        # 结构化分镜 prompt
│   └── asset.schema.json          # 自描述 manifest(schema_version + 来源 + 生成器 + 5 JSON 清单 + 媒体清单)
├── fixtures/minimal/              # 一份完整的最小样例资产(6 个 JSON,可被 6 个 schema 全部校验通过)
│   ├── asset.json
│   ├── shots.json
│   ├── audio_analysis.json
│   ├── transcript.json
│   ├── frames.json
│   └── prompts.json
├── validate.py                    # 校验器(标准库 + jsonschema,无外部依赖)
├── README.md                      # 本文件
└── SPEC.md                        # 人读 prose 规范 — 由 Plan 02 产出(pending Plan 02)
```

## How to validate

```bash
# 默认:minimal fixture 必须 6 条全 [valid],smoke 阶段对 output/ 真实产物宽容校验(仅打印,不影响退出码)
python3 spec/validate.py

# 严格模式:smoke 失败也计入退出码(CI / Phase 2 回归用)
python3 spec/validate.py --strict-smoke
```

预期输出:6 行 `[valid] <shape>`(asset / shots / audio_analysis / transcript / frames / prompts)+ 至少 5 行 `[smoke-valid|smoke-FAIL] <shape>`(只要仓库 `output/` 下有真实生产产物)。

## Canonical asset layout (CONTEXT D-03)

视频与 stem 音频在资产目录内的**规范命名**(Phase 2 导出器会按此重命名,生产端当前 `stems/htdemucs/<stem>/...` 布局是非规范的):

- 视频:`video.mp4`(资产根或一层子目录下)
- Stems:`stems/vocals.wav`、`stems/drums.wav`、`stems/other.wav`(bass 被剔除——消费端只渲染 vocals/drums/other 三轨)

`asset.schema.json` 用正则 pattern 强制该命名,并拒绝 `..` 路径穿越、绝对路径、Windows 保留字符(T-01-03 缓解)。

## Range-aware HTTP 206 (SPEC-03)

消费端 seek 视频 / stem 时,媒体必须经 **Range-aware HTTP 206 (Partial Content)** 服务访问。生产端现成服务:`scripts/serve.py`(已实现 206,默认端口 8765)。本 phase 不修改该脚本——prose 规范在 Plan 02 `SPEC.md` 中会再次引用。

## Schema 版本与 graceful-degrade 规则 (CONTEXT D-02)

`asset.json` 的 `schema_version` 字段使用 semver-lite(`"1"`、`"1.1"`,非完整 semver)。schema 严格(`additionalProperties: false`),但消费端**必须**在运行时对未知/更新版本做 graceful-degrade:忽略未知字段、渲染已知部分、emit 一个 warning,不要 reject 或 crash。新增字段=minor bump,破坏性变更=major bump(必须在 prose SPEC 中写迁移说明)。规则全文嵌在 `asset.schema.json` 的 `schema_version.description` 与顶层 `$comment` 里。

## Origin / Provenance

- **生产端**:Phase 2 导出器(待实现),把 `output/<video-stem>/` 下的 5 个 JSON + 媒体重命名为 canonical 布局后写出 `asset.json`。
- **消费端**:Phase 3 `@kais/infinite-canvas` 集合节点(跨仓库,`kais-aigc-platform` 上的 `feat/canvas-asset-collection` 分支)。
- **本 phase**:Phase 1,只交付 schema + fixture + 校验器,**不写导出器代码、不写画布消费代码**。

---

*Created: 2026-07-20 (Phase 01 Plan 01)*
