# Phase 18: Contract v1.3 - Context

**Gathered:** 2026-08-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Lock the v1.3 contract BEFORE any round-trip code writes against it（契约先行，mirror v1.1 Phase 5 / v1.2 Phase 11 先例）：

- `spec/schemas/roundtrip.schema.json` sidecar（draft 2020-12、`additionalProperties:false`）—— per-shot: regen video ref + scores{midframe_sim, judge} + verdict{accepted/rejected} + attribution + reason
- `asset.schema.json` 增 optional `data.roundtrip` 挂载（不进 `required[]`）
- `SCHEMA_VERSION = "1.3"` 在 `scripts/export_asset.py` 单源锁定
- `spec/validate.py` shape gate 扩展三层门（minimal / v1.2 / v1.3 fixture 全绿）
- `scripts/verify_contract.py` v1.2↔v1.3 bidirectional cross-version proof（forward 0 errors / backward 0 non-additive errors）
- roundtrip 数据缺席时导出照常 + `[roundtrip]` warnings sidecar 记因通道（RT-04 契约级 degrade）
- SPEC.md §4 changelog 1.2→1.3 + §5 roundtrip 形状文档 + fidelity disclaimer

Requirements: RT-01, RT-02, RT-03, RT-04。

**NOT in this phase:** 任何 round-trip 生产者代码（regen 客户端 = Phase 20、scorer = Phase 21）、HTML 面板（Phase 22）、dataset 导出（Phase 22，RT-05）。

</domain>

<decisions>
## Implementation Decisions

### roundtrip.json 顶层形状与 per-shot 结构
- 顶层 `{schema_version, shots[]}` 数组 —— 100% mirror `audio_semantic.schema.json` 先例（Phase 11 同款），validate/gate 模式直接复用
- regen ref 是对象：`regen: {path, video_content_hash, engine_name, engine_version, prompt_version}` —— REGEN-02 的 4-tuple cache 直接进契约（mirror WR-04），可复现可审计；path 相对 asset root
- regen 元数据 minimal：`duration_sec` + `width`/`height` optional（REGEN-04 降分辨率模式需记录实际分辨率）；fps/frames/seed/完整 workflow 参数不收（h3 workflow 是 kst 外部资产，不契约化）
- per-shot 只有 `shot_id` required，其余 optional —— 支持 degrade 中间态（regen 成功但未打分、只有 score 没 verdict）

### scores / verdict / attribution 字段形状
- attribution 是 **closed enum** `{prompt_faithful, model_diverged, prompt_underspecified}` —— SCORE-02 三分类是我们自己的分类学（非未校准外部模型输出），enum 让 SCORE-03「rejected 占比可审计」机器可查；与 emotion free-string 先例不矛盾（那是没有校准的模型标签）
- `midframe_sim: {score: 0..1, model: string}` —— 带 similarity model 标识（clip/siglip 变体不可跨模型比较，不标 model 名的 0.87 不可审计）
- `judge: {attribution: enum, confidence: 0..1, reason: string}` 三件套 —— judge 本质是分类器不是回归器；不给连续分（伪精度）
- `verdict: {decision: accepted|rejected, source: auto|human, decided_at?}` —— PRESENT-01 HITL accept/reject 按钮覆盖后 `source=human`；DATASET-02 可审计要求溯源（attribution enum 值同 judge 三分类）

### degrade 通道与 warnings 形状（RT-04）
- `[roundtrip]` warnings 复用 `asset.json#generator.warnings[]` 现有 sidecar（`[shot]`/`[audio]` 前缀模式，consumer 已知如何读）；不建独立 warnings 文件
- warnings 条目结构化：`code` closed enum `{comfyui_unreachable, vram_insufficient, scorer_model_missing}` + free `detail` —— RT-04 点名的三种因由机器可 grep（比 v1.2 纯文本 warning 升级一级，合理：roundtrip 缺席是预期常态而非异常）
- per-shot 中间态：shots[] 只收「有产物」的 shot；regen 失败的收录为 `status: {state: failed, error: string}`；未跑的 shot 不在数组里（缺席=未尝试；schema 是结果集不是任务队列，不加 pending/rendering 任务态）
- byte-identical-absent 红线证明：mirror v1.2 Phase 11 模式 —— 无 roundtrip 输入跑 export，diff v1.2 及以前 12 个数据文件 byte-identical，写进 phase verification（契约级断言，不加常驻 CI harness）

### SPEC / fixture / gate 交付物
- v1.3 fixture set = 13 形状：v1.2 的 12 个 byte-copied substrate + `roundtrip.json` 新形状（mirror Phase 11 的 v1.1→v1.2 模式）
- `asset.schema.json#data.roundtrip` 挂载 mirror `data.audio_semantic`：optional object（file ref + accepted/rejected 统计字段），不内嵌 per-shot 数据，不进 required[]
- 阈值数值 **不进 schema** —— Phase 21 校准后才存在，schema 只装结果不装阈值；阈值放 SPEC §5 散文 + Phase 21 校准报告（two-tier authority 先例）
- SPEC fidelity disclaimer 三层：① accepted = 「h3 可复现」≠「prompt 完美」（fl2va 条件渲染幸存者偏差）② rejected 是 hard negatives + h3 能力边界测绘、非垃圾 ③ judge attribution 是模型判断带 confidence 不是 ground truth

### Claude's Discretion
- schema 字段命名细节（snake_case 与现有 schema 一致）、description 中文行文、$comment 里的决策溯源措辞
- fixture 具体样例数值（覆盖全字段但取小值）
- validate.py 的 v1.3 gate 接线细节（V13_FIXTURE_DIR 常量、退出码聚合方式 mirror 现状）

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `spec/schemas/audio_semantic.schema.json` —— 最接近的 sidecar schema 先例（draft 2020-12 + additionalProperties:false + $comment 决策溯源 + nullable 宽松 required 模式），roundtrip.schema.json 直接套此骨架
- `spec/validate.py` —— 已有 minimal / v1.1 / v1.2 三阶 gate（`V12_FIXTURE_DIR`、退出码聚合 `total_strict_failures`），v1.3 是第四阶增量
- `spec/fixtures/v1.2/` —— 12 形状 substrate，byte-copy 即得 v1.3 fixture 的前 12 个
- `scripts/verify_contract.py` —— 已有 v1.0↔v1.1↔v1.2 bidirectional cross-version proof 模式，加 v1.2↔v1.3 一档
- `scripts/export_asset.py:56` —— `SCHEMA_VERSION = "1.2"` 单源，bump 到 "1.3"
- `asset.schema.json` —— `data.audio_semantic` optional 挂载是 `data.roundtrip` 的形状模板

### Established Patterns
- 契约先行：v1.1 Phase 5 / v1.2 Phase 11 都是 schema+fixture+gate+SPEC 一 phase 锁死，生产者后续 phase 才写
- strict-schema × lenient-consumer：schema 校验 additionalProperties:false 全程，runtime consumer 容忍未知字段
- additive-only minor bump：老版本消费者 graceful-degrade，缺席 = byte-identical
- two-tier authority：SPEC 散文承载 fidelity disclaimer，schema 只装 machine-checkable 事实

### Integration Points
- `scripts/export_asset.py` —— SCHEMA_VERSION bump + data.roundtrip optional 挂载写入（roundtrip.json 存在时）
- `spec/validate.py` main() —— v1.3 fixture gate 接进退出码
- `spec/SPEC.md` §4 changelog + §5 形状文档
- `asset.json#generator.warnings[]` —— `[roundtrip]` 前缀条目（code+detail 结构）

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the ROADMAP success criteria and locked decisions above — open to standard approaches mirroring Phase 11.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.（canvas roundtrip 消费、音频 round-trip 对比等已在 REQUIREMENTS Future/Out-of-Scope 名单，非本 phase 讨论）

</deferred>
