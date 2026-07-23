# Phase 2: shot-timeline Exporter (Producer) - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — grey areas accepted as recommended

<domain>
## Phase Boundary

在 `run_pipeline.py` 现有 5 步之上**加一个导出层**（additive only），把 `output/<video-stem>/` 下的产物打包成符合 Phase 1 spec 的自描述 **ShotTimelineAsset**：写 `asset.json` manifest + canonical 媒体重命名/链接 + 自校验。导出端通过现有 `scripts/serve.py`（206 Range）对外提供媒体，供下游消费端 seek 播放。

本 phase **只加导出层**：不改分镜检测/转录/分离算法（那是 validated 基线），不动 timeline.html 生成。交付物：`export_asset.py` 导出器 + `run_pipeline.py` 新增 `step_export`（step 6）+ `--skip-export` flag + `scripts/serve.py` FD-leak 修复 + Range-206 自检脚本。

**Goal:** Running the shot-timeline pipeline emits a self-describing ShotTimelineAsset artifact that conforms to the Phase 1 spec and is servable to a downstream consumer.
**Requirements:** EXPORT-01, EXPORT-02, EXPORT-03
**Repo:** kais-shot-timeline（本仓库）
**Depends on:** Phase 1（spec + schemas + validate.py 已就绪）

</domain>

<decisions>
## Implementation Decisions

### 导出触发与调用模型 (EXPORT-01, SC-1)
- 导出逻辑放在**新增 `step_export`（step 6）**里，shell out 到一个新脚本 `export_asset.py`（沿用现有「orchestrator 经 `[sys.executable, 脚本路径]` 调子进程」模式，不跨 stage import）
- **默认 always-on** —— 跑完 `run_pipeline.py` 自动产出 ShotTimelineAsset；新增 `--skip-export` flag，与现有 `--skip-detect/--skip-separate/--skip-transcribe` 风格一致
- **缓存策略**：cache on `asset.json` 存在 + mtime-vs-inputs（mirror timeline step 的 `os.path.getmtime` 模式）；`--force` 一并清掉 `asset.json`
- 理由：SC-1 字面要求「`run_pipeline.py` finishes → artifact exists」，always-on 是唯一字面满足的形态

### Canonical 媒体策略 (EXPORT-02, SC-1)
- **Symlink（符号链接）**产出 canonical 媒体，in-place 在 `output/<video-stem>/` 根：
  - `stems/vocals.wav` → `stems/htdemucs/<stem>/vocals.wav`
  - `stems/drums.wav` → `stems/htdemucs/<stem>/drums.wav`
  - `stems/other.wav` → `stems/htdemucs/<stem>/other.wav`（bass 不导出 —— 消费端只渲染 3 stems）
  - `video.mp4` → `<original-name>.mp4`（**非** `h264.mp4`，后者 `-an` 去掉了音轨；保音频保真）
- **零磁盘开销 + 不破坏 `timeline.html`** 现有的 `<basename>_vocals/_drums/_other` 引用 —— 符号链接让新旧引用共存，additive only
- 理由：copy 翻 4×wav+视频磁盘；move 会断 timeline.html；symlink 是最小侵入。Linux-first 工具，符号链接 serving 可接受（Range server 已能 `translate_path`/`os.fstat` 跟随）

### prompts.json 间隙 + 自校验 (EXPORT-01, SC-1)
- **Exporter 要求 prompts.json 存在** —— `asset.schema.json` 的 `data` 把 5 个 JSON 全部列为 `required`，不可省略；若 `prompts.json` 缺失，exporter **fails loud**（带可操作错误信息：提示 prompts 由独立步骤产出，需先就位）
- **写完 `asset.json` 后跑 `spec/validate.py` 自校验** —— invalid 则导出失败（fail export）。这样 SC-1「conforms to the Phase 1 spec」有机器可检证据，且为 Phase 4 回归 harness 打基础
- 理由：省略 prompts 会违反 schema `required`（违背 Phase 1 的 strict-additionalProperties 决策）；不校验则 SC-1 无证据。prompts 生成不在本 phase（additive only —— 不改核心算法；prompts 由既有独立步骤产出）

### serve.py 加固范围 (EXPORT-03, SC-3)
- **只修 FD-leak**（真实正确性 bug：consumer 连续 seek 时 file handle 不释放，影响 Range 服务可靠性）—— 错误路径（416、NOT_FOUND、Range 解析失败）下 `f.close()` 未保证
- **新增 tiny Range-206 自检**：curl-based check（`Range: bytes=0-1023` → assert 206 + `Content-Range: bytes 0-1023/<total>` + `Accept-Ranges: bytes`），作为 SC-3 的机器可检证据
- **defer** `0.0.0.0` unauth / bind-address / auth 加固 —— 单机离线 dev 工具，属 scope creep（SC-3 只要求 206 可观察，已满足）
- 理由：206 本已工作（满足 SC-3 字面），但 FD-leak 是影响 consumer 实际 seek 可靠性的真 bug；其余加固属运维范畴，本 phase 不背

### Claude's Discretion
- `export_asset.py` 的精确字段填充逻辑（asset.json 各字段从 ffprobe/已有 JSON 取值的具体实现）
- `generator.version` 取值来源（git SHA / hardcode / `__version__`）—— 任意字符串即可，schema 不强制
- Range-206 自检脚本的落地形式（独立 `scripts/check_range.py` 还是 export_asset 的 post-step 子命令）—— plan 阶段定

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_pipeline.py` —— orchestrator；新增 `step_export` 仿照 `step_timeline`（mtime cache + subprocess）。CLI argparse 已有 `--skip-*` 模式可复制。`--force` 块需追加 `asset.json` 清理
- `spec/validate.py` —— Phase 1 产出的 schema 校验器；exporter post-write 直接调用，无需重写
- `spec/schemas/asset.schema.json` —— manifest 的权威 schema（`required: schema_version, asset_type, source, generator, data, media`；`media.stems` 只要 vocals/drums/other）
- `scripts/serve.py` —— `RangeRequestHandler.send_head` 已实现 206；FD-leak 在 `send_head` 的 416/error 分支（`f.close()` 缺失）+ `_Partial` 包装器异常路径
- `run_pipeline.py:probe_duration` / `probe_codec` —— generator/source 字段可复用

### Established Patterns
- **Subprocess-by-path**：orchestrator 用 `[sys.executable, str(HERE / "scripts" / "export_asset.py"), ...]` 调子脚本，不跨 stage import
- **Cache-on-existence + mtime**：`step_timeline` 的 `os.path.getmtime(out_html) > max(inputs)` 模式，step_export 复用
- **JSON 一律 `ensure_ascii=False` + `indent=2`**（中文 content，见 CONVENTIONS.md）
- **`--skip-*` boolean flags**：`action="store_true"` + 中文 `help=`
- **Bracketed stage prefix**：`print(f"[6/6] ...")` 与现有 `[1/5]..[5/5]` 一致（注意 step 总数从 5 升 6）

### Integration Points
- `run_pipeline.py:main` —— 在 `step_timeline` 之后追加 `step_export`；CLI 加 `--skip-export`
- `scripts/serve.py:RangeRequestHandler.send_head` —— FD-leak 修复点（416 分支 `f.close()`、NOT_FOUND 分支已 close、`_Partial` read 异常）
- `output/<video-stem>/asset.json` —— 新产物；in-place 同 stems/htdemucs/、5 JSON 并列
- Phase 3 消费端会读 `asset.json` 找 manifest；Phase 4 会复用 validate.py + Range check 做回归

</code_context>

<specifics>
## Specific Ideas

- canonical `video.mp4` 必须 symlink 到**原始视频**（`<original-name>.mp4`），不是 `h264.mp4`（后者 `-an` 丢了音轨 —— 消费端要听 stems 对齐，视频也要有声轨作 fallback）
- timeline.html 的旧 stem 引用（`<basename>_vocals.wav` 等）**不能被导出层破坏** —— 这是「additive only」的硬约束，symlink 共存方案是为此设计
- 5 个数据 JSON 的实际形状已 smoke-valid（Phase 1 结论），exporter 不改它们，只引用

</specifics>

<deferred>
## Deferred Ideas

- prompts.json 生成步骤的 pipeline 化（接入 run_pipeline）—— 仍由独立步骤产出；本 phase 要求其存在但不生成
- serve.py 的 bind-address / auth / HTTPS 加固 —— 单机 dev 工具，属后续运维范畴
- Windows 下 symlink 兼容（需管理员权限）—— Linux-first 工具，不在 v1.0 考虑
- asset 目录打成 zip/tar 分发 —— v1.0 只定义目录形态，打包留待后续
- None others —— 讨论保持在 phase 范围内

</deferred>
