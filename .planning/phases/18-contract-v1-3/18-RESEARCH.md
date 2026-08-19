# Phase 18: Contract v1.3 - Research

**Researched:** 2026-08-19
**Domain:** JSON Schema contract lock (draft 2020-12) — sidecar schema + fixture + validation gates + cross-version proof + SPEC prose（mirror v1.1 Phase 5 / v1.2 Phase 11 契约先行先例）
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**roundtrip.json 顶层形状与 per-shot 结构**
- 顶层 `{schema_version, shots[]}` 数组 —— 100% mirror `audio_semantic.schema.json` 先例（Phase 11 同款），validate/gate 模式直接复用
- regen ref 是对象：`regen: {path, video_content_hash, engine_name, engine_version, prompt_version}` —— REGEN-02 的 4-tuple cache 直接进契约（mirror WR-04），可复现可审计；path 相对 asset root
- regen 元数据 minimal：`duration_sec` + `width`/`height` optional（REGEN-04 降分辨率模式需记录实际分辨率）；fps/frames/seed/完整 workflow 参数不收（h3 workflow 是 kst 外部资产，不契约化）
- per-shot 只有 `shot_id` required，其余 optional —— 支持 degrade 中间态（regen 成功但未打分、只有 score 没 verdict）

**scores / verdict / attribution 字段形状**
- attribution 是 **closed enum** `{prompt_faithful, model_diverged, prompt_underspecified}` —— SCORE-02 三分类是我们自己的分类学（非未校准外部模型输出），enum 让 SCORE-03「rejected 占比可审计」机器可查；与 emotion free-string 先例不矛盾（那是没有校准的模型标签）
- `midframe_sim: {score: 0..1, model: string}` —— 带 similarity model 标识（clip/siglip 变体不可跨模型比较，不标 model 名的 0.87 不可审计）
- `judge: {attribution: enum, confidence: 0..1, reason: string}` 三件套 —— judge 本质是分类器不是回归器；不给连续分（伪精度）
- `verdict: {decision: accepted|rejected, source: auto|human, decided_at?}` —— PRESENT-01 HITL accept/reject 按钮覆盖后 `source=human`；DATASET-02 可审计要求溯源（attribution enum 值同 judge 三分类）

**degrade 通道与 warnings 形状（RT-04）**
- `[roundtrip]` warnings 复用 `asset.json#generator.warnings[]` 现有 sidecar（`[shot]`/`[audio]` 前缀模式，consumer 已知如何读）；不建独立 warnings 文件
- warnings 条目结构化：`code` closed enum `{comfyui_unreachable, vram_insufficient, scorer_model_missing}` + free `detail` —— RT-04 点名的三种因由机器可 grep（比 v1.2 纯文本 warning 升级一级，合理：roundtrip 缺席是预期常态而非异常）
- per-shot 中间态：shots[] 只收「有产物」的 shot；regen 失败的收录为 `status: {state: failed, error: string}`；未跑的 shot 不在数组里（缺席=未尝试；schema 是结果集不是任务队列，不加 pending/rendering 任务态）
- byte-identical-absent 红线证明：mirror v1.2 Phase 11 模式 —— 无 roundtrip 输入跑 export，diff v1.2 及以前 12 个数据文件 byte-identical，写进 phase verification（契约级断言，不加常驻 CI harness）

**SPEC / fixture / gate 交付物**
- v1.3 fixture set = 13 形状：v1.2 的 12 个 byte-copied substrate + `roundtrip.json` 新形状（mirror Phase 11 的 v1.1→v1.2 模式）
- `asset.schema.json#data.roundtrip` 挂载 mirror `data.audio_semantic`：optional object（file ref + accepted/rejected 统计字段），不内嵌 per-shot 数据，不进 required[]
- 阈值数值 **不进 schema** —— Phase 21 校准后才存在，schema 只装结果不装阈值；阈值放 SPEC §5 散文 + Phase 21 校准报告（two-tier authority 先例）
- SPEC fidelity disclaimer 三层：① accepted = 「h3 可复现」≠「prompt 完美」（fl2va 条件渲染幸存者偏差）② rejected 是 hard negatives + h3 能力边界测绘、非垃圾 ③ judge attribution 是模型判断带 confidence 不是 ground truth

### Claude's Discretion
- schema 字段命名细节（snake_case 与现有 schema 一致）、description 中文行文、$comment 里的决策溯源措辞
- fixture 具体样例数值（覆盖全字段但取小值）
- validate.py 的 v1.3 gate 接线细节（V13_FIXTURE_DIR 常量、退出码聚合方式 mirror 现状）

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.（canvas roundtrip 消费、音频 round-trip 对比等已在 REQUIREMENTS Future/Out-of-Scope 名单，非本 phase 讨论）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RT-01 | `roundtrip.schema.json` sidecar — per-shot {regen video ref, scores{midframe_sim, judge}, verdict{accepted/rejected}, attribution, reason}；additive optional；byte-identical-absent 红线 | §Integration Points（audio_semantic 模板全文核对）；§Code Examples A（完整 schema 骨架）；§Wrinkle 2（byte-identical 精确证明框架 = Phase 11 VERIFICATION SC#2 原文核对） |
| RT-02 | `SCHEMA_VERSION = "1.3"` producer-locked 单源；validate.py shape gate 扩展；fixture + v1.2↔v1.3 bidirectional cross-version proof | §Integration Points（export_asset.py:56、validate.py 三阶 gate 机制、verify_contract.py 四 pass 结构 + git tag 已验证可用）；§Code Examples B/C |
| RT-03 | SPEC §4 changelog 1.2→1.3 + §5 roundtrip 形状文档 + fidelity disclaimer | §SPEC.md 交付物（§1/§4/§5/§10/README 精确结构与 Phase 11 先例条目原文） |
| RT-04 | graceful-degrade —— ComfyUI 不可达 / VRAM 不足 / 打分模型缺席 → roundtrip sidecar 缺省（byte-identical-absent）、资产照常导出、`[roundtrip]` warnings sidecar 记因 | §Wrinkle 1（warnings items 类型加宽的完整机制 + 向后证明过滤的交互 —— 本 phase 唯一真正的新问题）；§Code Examples D |
</phase_requirements>

## Summary

Phase 18 是 v1.2 Phase 11 的近克隆：同一套 schema+fixture+gate+cross-version-proof+SPEC 交付物，只是新形状从 3 个减到 1 个（roundtrip.schema.json）。所有既有机制已逐行核对：`validate.py` 的 V11/V12 阶梯（加 V13 是第四阶纯增量）、`verify_contract.py` 的四 pass 双向证明（git tag `v1.2` 已存在且 `git show v1.2:spec/schemas/asset.schema.json` 已验证可用）、Phase 11 的三 plan 拆分（schemas/producer → fixtures/gates → SPEC docs）与 VERIFICATION 证明框架（data-keys smoke + 9 个 byte-copied substrate 文件 diff-clean）都可直接镜像。仓库内 warnings 零解析消费者（html/ 与 canvas_import.py grep 为空），warnings 形状演进不破坏任何现有读者。

与 Phase 11 有 **两处真实差异**，planner 必须显式处理（详见 §The Two Novel Wrinkles）：① CONTEXT 锁定的结构化 warnings 条目 `{code, detail}` 要求把 `asset.schema.json#generator.warnings.items` 从 `{"type":"string"}` 加宽为 string|object 双形 —— 这是 v1.x 历史**第一次对既有字段的 items 类型加宽**，会与 backward cross-version proof 的「0 non-additive errors」过滤规则交互（需要精确扩展过滤规则 + `_recover_v12_schema` strip fallback 还原 items）；② `data.roundtrip` 是 v1.x 历史**第一个 object 值的 data.\* 挂载**（file ref + accepted/rejected 统计），会撞上 `verify_contract.py:validate_eight_shapes` 的 `isinstance(rel, str)` 假设（line 253-261）。两处都有精确的落地机制（见 Code Examples），但它们是本 phase 不能盲目 copy-paste Phase 11 的原因。

**Primary recommendation:** 三 plan 镜像 Phase 11（01 schemas+producer emission / 02 fixtures+gates+proof / 03 SPEC docs，wave 结构相同）；warnings 加宽与 object 挂载的机制按 §Wrinkle 1/2 的推荐方案落地，backward 证明过滤规则的扩展作为 11-02 对应 plan 的 must-have truth 显式写入。

## Architectural Responsibility Map

本项目是 CLI pipeline + 静态契约，无 web tier；能力归属按「契约权威层」划分：

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| roundtrip 数据形状权威（machine-checkable） | `spec/schemas/roundtrip.schema.json` | — | strict-schema × lenient-consumer：schema 是唯一机器权威（SPEC.md §1 two-tier authority） |
| 版本字面量单源 | `scripts/export_asset.py:SCHEMA_VERSION` | — | 单一真源防 Pitfall 12（schema 变更忘 bump）；schema pattern 刻意宽松以兼容老 fixture |
| data.roundtrip 挂载 + 统计 | `scripts/export_asset.py:build_asset_dict` | — | producer 唯一写 manifest 的地方；条件发射（file-existence gate）保 byte-identical-absent |
| 结构化 warnings 通道 | `asset.schema.json#generator.warnings`（形状）+ `route_cache/warnings.json`（传输 sidecar） | `export_asset.py` main() 装载 | 复用既有 sidecar 通道（CONTEXT 锁），不建新文件 |
| fixture 阶梯 gate | `spec/validate.py`（V13 第四阶） | — | minimal 仍 gate 退出码；每阶独立 map/order/fn，退出码聚合 `total_strict_failures` |
| 双向跨版本证明 | `scripts/verify_contract.py:_cross_version_check`（pass e/f） | `_recover_v12_schema`（git tag v1.2 primary + strip fallback） | schema-layer 兼容证明的 canonical home |
| fixture 跨文件一致性 | `verify_contract.py:_fixture_consistency_check` | — | roundtrip.shots[].shot_id ⊆ shots.json#id（mirror speakers Pitfall 17 块） |
| prose 权威（fidelity disclaimer / 阈值散文） | `spec/SPEC.md` §4/§5/§10 | `spec/README.md` footer | two-tier authority：阈值与保真度声明不进 schema |
| HTML gallery / canvas roundtrip 消费 | —（Phase 22 / 后续 milestone） | — | NOT in this phase（CONTEXT 边界） |

## Current Integration Point Map（逐点核对，全部 [VERIFIED: codebase]）

### 1. `scripts/export_asset.py`
- **`SCHEMA_VERSION = "1.2"` 在 line 56**（上方 51-55 行是版本注释块，bump 时同步更新注释为 v1.3 语义）。[VERIFIED: codebase scripts/export_asset.py:51-56]
- **条件发射模板**：Phase 11 的 audio_semantic/speakers 块在 line 320-329（`audio_semantic_path = os.path.join(work_dir, "audio_semantic.json"); if os.path.isfile(...): data_block["audio_semantic"] = "audio_semantic.json"`）。v1.3 的 roundtrip 块 mirror 此结构，但值是 **object 不是 string**（见 §Wrinkle 2）。[VERIFIED: codebase scripts/export_asset.py:320-329]
- **warnings 流**：`main()` line 488-501 best-effort 读 `route_cache/warnings.json`（`{"warnings": [...]}` 形状），**只接受 `list[str]`**（line 496-499：`all(isinstance(w, str) for w in candidate)`，否则整体回退 None）；`build_asset_dict` line 382 `**({"warnings": warnings} if warnings else {})` 非空才 emit。结构化条目要过载必须改这两处（见 §Wrinkle 1）。[VERIFIED: codebase scripts/export_asset.py:488-501,382]
- **写盘机制**：inline `Draft202012Validator` 自校验（line 530）→ 原子写 `tmp + os.replace`（line 534-537）→ `indent=2, ensure_ascii=False`。`generator.version` = git SHA、`generated_at` = UTC 时间戳 —— **asset.json 跨运行永远不 byte-identical**（这决定了红线证明的正确框架，见 §Wrinkle 2）。[VERIFIED: codebase scripts/export_asset.py:366-391,530-537]

### 2. `spec/validate.py`
- 三阶 gate 结构：`FIXTURE_DIR`(minimal, 6 shapes) / `V11_FIXTURE_DIR`(10) / `V12_FIXTURE_DIR`(12)，各配 `*_FIXTURE_MAP`（shape→文件名）+ `*_ORDER` + 独立 `validate_v11()/validate_v12()` 函数（打印前缀 `[valid-v11]`/`[FAIL-v11]` 等）。[VERIFIED: codebase spec/validate.py:32-98,146-214]
- 退出码聚合在 `main()`：`total_strict_failures = minimal_failures + v11_failures + v12_failures`（+ 可选 smoke），0 → exit 0。加 V13 = 新增 `V13_FIXTURE_DIR/MAP/ORDER` + `validate_v13()`（mirror `validate_v12()`，前缀 `-v13`）+ 聚合式加 `v13_failures` + 汇总行加一段。[VERIFIED: codebase spec/validate.py:290-310]
- **jsonschema 4.26.0 已装**（docstring line 16 也写明），`Draft202012Validator` 直接 import 使用。[VERIFIED: runtime `python3 -c "import jsonschema"` → 4.26.0]

### 3. `scripts/verify_contract.py`
- **四 pass 双向证明**（`_cross_version_check`，line 368-480）：(a) forward v1.0 minimal × 当前 schema（SIX_SHAPES，0 errors）；(b) backward v1.1 fixture × `_recover_v1_schema`（过滤 `e.validator != "additionalProperties"` 后须 0）；(c) forward v1.1→v1.2（仅 asset）；(d) backward v1.2→v1.1（仅 asset，`_recover_v11_schema`，non-addprop 过滤）。**v1.3 加 (e) forward v1.2→v1.3 + (f) backward v1.3→v1.2，各仅 asset shape**（roundtrip 是全新形状无旧实例可测，mirror Phase 11 只测被扩展的 asset）。[VERIFIED: codebase scripts/verify_contract.py:368-480]
- **`_recover_v11_schema` 模板**（line 326-365）：primary = `git show v1.1:spec/schemas/<shape>.schema.json`；fallback = deep-copy 当前 schema 后 pop 已知 additive keys。**`git show v1.2:spec/schemas/asset.schema.json` 已实测可用**（v1.2 tag → 276e698 milestone archive commit，schema 内容 = 当前盘上 v1.2 状态，data props 9 keys、warnings items = `{'type': 'string'}`）。`_recover_v12_schema` 的 strip fallback 需 pop `data.properties.roundtrip` **并还原 `generator.properties.warnings.items` 为 `{"type":"string"}`**（见 §Wrinkle 1）。[VERIFIED: runtime git show + codebase scripts/verify_contract.py:326-365]
- **`validate_eight_shapes` 的 string 假设**：line 253-261 `rel = data_field.get(shape); if not isinstance(rel, str): ... failures.append(f"{shape}: data.{shape} is not a string")` —— `data.roundtrip` 若为 object 会被误报。EIGHT_SHAPES（line 82-89）加 `"roundtrip"` 时必须同步处理 object 形（取 `rel["path"]`）。[VERIFIED: codebase scripts/verify_contract.py:82-89,253-261]
- **fixture 一致性检查模板**：`_fixture_consistency_check` 的 v1.2 speakers 块（line 578-632，gated on `v12_fix_dir.is_dir()`）做 spk_id pattern + char_id ⊆ characters ids + turn.shot_id ⊆ shots ids。v1.3 mirror 一块：roundtrip.shots[].shot_id ⊆ v1.3 fixture shots.json ids。[VERIFIED: codebase scripts/verify_contract.py:578-632]
- producer-mode 默认 ep01 asset dir（`DEFAULT_E01_ASSET_DIR`），**已验证存在于盘上**（`output/虫虫武侠小故事《小江湖》第01话…/asset.json` OK）—— producer mode 本 phase 可跑。[VERIFIED: runtime ls]

### 4. `spec/schemas/asset.schema.json`
- `required: ["schema_version","asset_type","source","generator","data","media"]`；`data.required` 仍是 5 个 v1.0 keys（line 116）。[VERIFIED: codebase spec/schemas/asset.schema.json:10,116]
- `data.audio_semantic`/`data.speakers` 挂载模板（line 154-163）：`{type:"string", pattern:"^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$", description: "v1.2 additive (OPTIONAL …)"}`。`data.roundtrip` mirror **挂载模式**（optional、不进 required）但值形状不同（object，CONTEXT 锁）。[VERIFIED: codebase spec/schemas/asset.schema.json:154-163]
- **`generator.warnings`**（line 56-59）：`{type:"array", items:{"type":"string"}, description:"v1.1 additive (OPTIONAL — Phase 6)…"}` —— 结构化条目要求加宽 items（§Wrinkle 1）。[VERIFIED: codebase spec/schemas/asset.schema.json:56-59]
- 路径 pattern 惯例：json 文件 `^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$`；媒体 `^(?!.*\\.\\.)([^/]+/)*stems/…`（anti-traversal + 无 drive letter + 扩展名锁定）。regen.path（mp4）应 mirror 媒体 pattern 风格。[VERIFIED: codebase spec/schemas/asset.schema.json:121-162,171-198]

### 5. `spec/fixtures/v1.2/`（12 文件，已 ls 核对）
`asset.json, audio_analysis.json, audio_semantic.json, characters.json, frames.json, prompts.json, props.json, registry.draft.json, registry.edits.json, shots.json, speakers.json, transcript.json`。Phase 11 VERIFICATION 原文：**9 个非 asset v1.1 substrate 文件 byte-copied（diff-clean），asset.json 被编辑**（schema_version="1.2" + 9 data keys + `generator.version="0.3.0-spec-fixture-v1.3"` 风格的版本串）。v1.3 mirror：**11 个非 asset 文件 byte-copy + asset.json 编辑（schema_version "1.3" + data.roundtrip object + warnings 增结构化条目 + generator.version "0.3.0-spec-fixture-v1.3"）+ roundtrip.json 新增 = 13 文件**。[VERIFIED: codebase spec/fixtures/v1.2/ + .planning/milestones/v1.2-phases/11-contract-v1-2/11-VERIFICATION.md:29-48]
- **v1.2 fixture shots.json 只有 shot_id {1,2}** —— roundtrip.json fixture 条目受此约束（一致性检查 shot_id ⊆ {1,2}）；「覆盖全字段」与「2 个 shot 上限」冲突的解法见 §Open Questions Q1。[VERIFIED: runtime json 解析]

### 6. `spec/SPEC.md`（728 行）
- §1（line 12 起）：「13 个 schema 文件」表 + two-tier authority 表 —— v1.3 改 14 + 加 roundtrip 行。[VERIFIED: codebase spec/SPEC.md:12-43]
- §4 Changelog（line 160 起）：三个既有条目（`1` / `1.1` / `1.2`）都是同一结构：日期—版本—「纯增量」声明—分 bullet 列 新 schema / asset.schema additive / pattern 不变+单源位置 / 向后兼容证据 / phase-informed deviations。v1.3 条目 mirror，**且必须诚实记录两处非纯新增量的增量**（items 加宽 + object 挂载——对旧数据仍是 additive，但要写明）。[VERIFIED: codebase spec/SPEC.md:160-186]
- §5 形状文档模板（§5.8 Audio Semantic line 439 起，四块结构）：Producer/Consumers 行 → 顶层形状段 → 字段表（Field/Type/Required/Notes）→ 最小片段（摘自 fixture）→ Reference schema 行。v1.3 加 §5.10 Round-trip。[VERIFIED: codebase spec/SPEC.md:439-539]
- §10 Fidelity Disclaimer（line 664 起，`1.2` 版）：AF-01 禁语 invariant（「完美复刻/精确复原/perfectly reconstruct」不得出现）+ 分层诚实声明 —— v1.3 三层 disclaimer 的直接先例（新增小节或 §10.5+）。[VERIFIED: codebase spec/SPEC.md:664-728]
- `spec/README.md` 有 v1.1/v1.2 update footer 模式（末行 `*Updated: … (Phase 05 — v1.1 additive extension: …)*`）—— v1.3 mirror。[VERIFIED: codebase spec/README.md tail]

### 7. Phase 11 先例的三 plan 拆分（.planning/milestones/v1.2-phases/11-contract-v1-2/）
- **11-01（wave 1）**：3 新 schema + asset.schema 扩展 + export_asset.py（SCHEMA_VERSION bump + 条件发射）。files_modified 含 export_asset.py —— **producer 文件在契约 phase 改是先例支持**（v1.3 的 warnings 装载加宽 + roundtrip 挂载统计放同一 plan）。[VERIFIED: codebase 11-01-PLAN.md frontmatter]
- **11-02（wave 2, depends 11-01）**：fixtures/v1.2/ 12 文件 + validate.py 三阶 gate + verify_contract.py（cross-version e/d pass + `_recover_v11_schema` + fixture 一致性）。[VERIFIED: codebase 11-02-PLAN.md frontmatter]
- **11-03（wave 2, depends 11-01）**：SPEC.md + spec/README.md。must_haves 含 AF-01 禁语 invariant（「NOWHERE … '完美复刻'/'精确复原' appear」）。[VERIFIED: codebase 11-03-PLAN.md]
- **11-VALIDATION.md**：契约 phase 的 validation = jsonschema 校验 + 双向证明 + byte-identical diff，**明确 NOT unit tests**（本 phase 同理，无需新增 pytest 文件；现有 `python3 -m pytest tests/` 仅作回归确认）。[VERIFIED: codebase 11-VALIDATION.md]

### 8. warnings 现状（生产者/消费者）
- 传输 sidecar：`route_cache/warnings.json` = `{"warnings": [str]}`，四个生产者 READ-merge-write（`analysis/call_shot_analysis.py:277`、`call_reid.py:321`、`call_audio_analysis.py:600`、`local_vision_facets.py:222`）。条目是**纯文本**（实测样例：`"preflight route unreachable: ConnectError: …"`、`"shot 3: route code=500: SHOT_ANALYSIS_DRIVER_FAILED"` —— v1.1/v1.2 fixture asset.json 同款）。CONTEXT 所述「[shot]/[audio] 前缀模式」是宽泛描述；实际无 bracket tag，结构化 `{code, detail}` 确实是升级一级。[VERIFIED: codebase analysis/call_shot_analysis.py:270-330 + spec/fixtures/v1.1/asset.json]
- **仓库内零解析消费者**：`grep -rn warnings html/*.py scripts/canvas_import.py` 为空 —— warnings 是 operator-facing，加宽 items 不破坏任何现有读者。consumer worktree `/data/workspace/kst-canvas-consumer` 不在盘上（verify_contract consumer mode 本机跑不了，但契约 phase 不需要它）。[VERIFIED: runtime grep]

## The Two Novel Wrinkles（v1.3 与 Phase 11 的真实差异 —— planner 必读）

### Wrinkle 1: warnings items 类型加宽（RT-04 的实现代价）

CONTEXT 锁定结构化条目后，`asset.schema.json#generator.warnings.items` 必须从 `{"type":"string"}` 加宽为双形。**这是 v1.x 历史上第一次修改既有字段的类型约束**（v1.1/v1.2 全是纯新增 optional property），有三处连锁：

1. **schema 变更**（加宽本身对旧数据是 additive —— 所有旧资产的 string warnings 仍校验通过；forward 证明不受影响）：
   ```json
   "warnings": {
     "type": "array",
     "items": {
       "anyOf": [
         {"type": "string"},
         {"type": "object", "additionalProperties": false,
          "required": ["code"],
          "properties": {
            "code": {"enum": ["comfyui_unreachable", "vram_insufficient", "scorer_model_missing"]},
            "detail": {"type": "string"}
          }}
       ]
     }
   }
   ```
   （required 取 `["code"]`、detail optional 是推荐值 —— degrade 记因最小单元是 code，detail 缺席合法；属 CONTEXT 的「命名细节」discretion 范围 [ASSUMED]。）
2. **backward pass (f) 的过滤规则交互**：v1.3 fixture（含结构化 warnings 条目）× recovered-v1.2 schema（items=string）会产生 `type` validator 错误 —— 不是 additionalProperties，现行 non-addprop 过滤会把它当 shared-field drift 报 FAIL。**必须**把过滤规则精确扩展为：`e.validator == "additionalProperties"`（data.roundtrip 新键）**OR**（`e.validator in ("type","anyOf")` 且 `e.absolute_path` 前两段 == `("generator","warnings")`，即文档化的 items 加宽）。汇总话术诚实化为「backward 0 non-additive errors (excluding documented v1.3 deltas: data.roundtrip + warnings items widening)」。[ASSUMED — 机制是本研究的工程设计，无先例可引；过滤的精确 scope 已核对 jsonschema 4.26 的 `e.validator`/`e.absolute_path` 语义与现行代码用法一致]
3. **`_recover_v12_schema` strip fallback**：pop `data.properties.roundtrip` 之外**还要还原 warnings items 为 `{"type":"string"}`**（git-show primary 路径无此问题，fallback 才需要）。[ASSUMED — 同上]

配套：`export_asset.py` main() 的 sidecar 装载（line 496-499 只收 list[str]）需加宽为接受 str | {code,detail}（~5 行，mirror 既有 graceful-degrade 风格：非合规形状回退忽略）。**推荐在本 phase 做**（Phase 11 的 11-01 同样在契约 phase 改 export_asset.py；通道端到端落地 = RT-04「记因通道落地」的字面要求；Phase 20 生产者只需往 sidecar 写结构化条目）。[ASSUMED — 归属 phase 的推荐，CONTEXT 未逐字指定]

### Wrinkle 2: `data.roundtrip` 是第一个 object 值的 data.* 挂载

CONTEXT 锁定：`data.roundtrip` = optional **object**（file ref + accepted/rejected 统计），不是 audio_semantic 式的纯 string path。连锁两处：

1. **`verify_contract.py:validate_eight_shapes` line 253-261** 假设 `data.<shape>` 是 string —— EIGHT_SHAPES 加 `"roundtrip"` 时必须特判 object（取 `rel.get("path")` 再走文件加载）。若本 phase 把 roundtrip 加进 EIGHT_SHAPES，此特判必须同 plan 落地（否则 Phase 20 producer 挂载即误报 "not a string"）。本 phase 不加 EIGHT_SHAPES 也可（ep01 无 roundtrip.json，dormant），但推荐加 + 特判一起做，保持 harness 与契约同步。[ASSUMED — 推荐归属]
2. **export_asset.py 挂载逻辑**比 Phase 11 复杂一档：文件存在 → 读 roundtrip.json → 数 `shots[].verdict.decision` 得 accepted_count/rejected_count → `data_block["roundtrip"] = {"path": "roundtrip.json", "accepted_count": N, "rejected_count": M}`。malformed roundtrip.json 的行为推荐 mirror `_build_registry_snapshot` 的 WR-05 模式：`[warn]` + OMIT（不持久化可能错的统计）。[ASSUMED — 字段名与 degrade 行为是 discretion 推荐值]

**byte-identical-absent 红线的正确证明框架**（照抄 Phase 11 VERIFICATION SC#2 原文语义，勿自行发明全文件 diff）：
- `grep -c 'SCHEMA_VERSION = "1.3"' scripts/export_asset.py` == 1 且 `grep -c 'SCHEMA_VERSION = '` == 1（无重复字面量）；
- **synthetic producer smoke**：仅含 5 个 required data JSON 的 work_dir（无 characters/props/audio_semantic/speakers/**roundtrip**）跑 `build_asset_dict` → `data` keys 恰为 5 个 required keys（与 v1.0/v1.1/v1.2 同集）+ `schema_version == "1.3"` + warnings 缺省 —— 证明「roundtrip 缺席 → data 块逐键等价」；
- **files-present smoke**：加 roundtrip.json → `data.roundtrip` 以 object 挂载 + 统计正确；
- fixture 侧：v1.3 目录中 **11 个非 asset 文件与 v1.2 diff-clean**（`diff -r` 排除 asset.json/roundtrip.json 为空）。
- 为什么不是全文件 byte diff：`generator.version`(git SHA) 与 `generated_at`(时间戳) 每次运行必变，asset.json 永不 byte-identical；红线语义是「**除 schema_version 字面量外零字段漂移**」。[VERIFIED: codebase .planning/milestones/v1.2-phases/11-contract-v1-2/11-VERIFICATION.md:30 + export_asset.py:373-382]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| jsonschema（`Draft202012Validator`） | 4.26.0（系统已装） | 全部 schema 校验（validate.py / verify_contract.py / export_asset.py inline） | 项目自 Phase 1 的唯一校验依赖，draft 2020-12 全程；本 phase 零新依赖 [VERIFIED: runtime + spec/validate.py:16] |
| Python stdlib（json/pathlib/subprocess/argparse） | 3.12.3 | fixture 拷贝、git-show recover、smoke harness | 项目惯例：无新包、无 lockfile [VERIFIED: codebase 全局] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3（`~/.local/bin/pytest`） | 现有 `tests/` 回归确认 | 每个 wave merge 后跑一次确认零破坏；本 phase 不新增测试文件（mirror 11-VALIDATION「NOT unit tests」） [VERIFIED: runtime] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| anyOf 加宽 warnings items | 前缀字符串 `"[roundtrip] comfyui_unreachable: …"` | 纯 additive 零加宽，但**违背 CONTEXT 锁定的结构化决策**——仅在 discuss 重开时考虑 |
| `data.roundtrip` object 挂载 | 纯 string path 挂载（audio_semantic 同款）+ 统计只在 roundtrip.json 内 | 更简单且完全 mirror 先例，但违背 CONTEXT 锁定的「file ref + accepted/rejected 统计字段」——同上，仅 discuss 重开 |

**Installation:** 无 —— 本 phase 零新包（jsonschema/pytest 均已在系统）。

## Package Legitimacy Audit

本 phase **不安装任何外部包**（纯 schema/fixture/harness/docs 改动，jsonschema 4.26.0 与 pytest 9.0.3 已在系统且为本仓既有依赖）。无 slopcheck 对象；无 [ASSUMED] 包推荐。

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌─────────────────────────────────────────────────┐
                    │  契约权威层（本 phase 交付物）                    │
                    │                                                 │
  人工 fixture ────▶│ roundtrip.schema.json (draft 2020-12, aP:false) │
  (13 文件)         │ asset.schema.json (+data.roundtrip obj,         │
                    │                     +warnings items 加宽)       │
                    │        │                        │                │
                    │        ▼                        ▼                │
                    │ spec/validate.py          scripts/verify_       │
                    │ 4 阶 gate (minimal/v1.1/   contract.py           │
                    │ v1.2/v1.3) ── exit 0/1    _recover_v12_schema   │
                    │                           (git tag v1.2 → strip) │
                    │        │                  pass (e) forward ─────┼──▶ 0 errors
                    │        │                  pass (f) backward ────┼──▶ 0 non-additive
                    │        │                  (过滤: addProp +       │   (excl. documented
                    │        │                   warnings-items 加宽)  │    v1.3 deltas)
                    └────────┼────────────────────────────────────────┘
                             │ 契约约束
                             ▼
  ┌────────────────── producer（本 phase 仅最小接线）──────────────────┐
  │ scripts/export_asset.py                                           │
  │  SCHEMA_VERSION="1.3" (单源) ──▶ asset.json#schema_version        │
  │  roundtrip.json 存在? ──是──▶ data.roundtrip={path,+counts} 挂载  │
  │        │缺席                     │ malformed → [warn]+OMIT        │
  │        ▼                                                         │
  │  data 块 = 5 required keys only（byte-identical-absent 红线）     │
  │  route_cache/warnings.json ─▶ generator.warnings[]（str|obj）     │
  └───────────────────────────────────────────────────────────────────┘
                             │
                             ▼
   Phase 20/21 生产者（NOT this phase）写 roundtrip.json + 结构化 warnings
   Phase 22 消费（HTML 面板 / dataset 导出）读 sidecar —— 全部 lenient-consumer
```

### Recommended Project Structure（增量）
```text
spec/
├── schemas/
│   ├── roundtrip.schema.json        # 新增（第 14 个 schema）
│   └── asset.schema.json            # 编辑（data.roundtrip + warnings items）
├── fixtures/v1.3/                   # 新增：11 byte-copy + asset.json 编辑 + roundtrip.json = 13
├── validate.py                      # 编辑：V13 阶
├── SPEC.md                          # 编辑：§1(14 个)/§4 changelog/§5.10/§10 disclaimer
└── README.md                        # 编辑：v1.3 footer
scripts/
├── export_asset.py                  # 编辑：SCHEMA_VERSION + roundtrip 挂载 + warnings 装载加宽
└── verify_contract.py               # 编辑：_recover_v12_schema + pass e/f + 一致性块 + EIGHT_SHAPES
```

### Pattern 1: 契约先行（contract-first minor bump）
**What:** schema + fixture + gate + 双向证明 + SPEC 一 phase 锁死，生产者后续 phase 才写。
**When to use:** 每次 minor bump 的第一个 phase（v1.1 Phase 5 / v1.2 Phase 11 / v1.3 Phase 18 三连先例）。
**Example:** 见 Code Examples A-D。

### Pattern 2: strict-schema × lenient-consumer × additive-only
**What:** `additionalProperties:false` 全程（含每个嵌套 object）；新增字段只进 properties 绝不进 required[]；老版本消费者忽略未知字段。
**When to use:** roundtrip.schema.json 每一层；asset.schema.json 的两个编辑点。
**Source:** [VERIFIED: codebase asset.schema.json $comment line 7 + SPEC.md §4 演进规则表]

### Pattern 3: nullable/enum 的校准诚实学（audio_semantic 先例的判例法）
**What:** 自己的分类学 → closed enum（可审计）；未校准的外部模型标签 → free string + confidence。v1.3 判例：`judge.attribution` 是我们的三分类 → **enum**（与 emotion free-string 先例不矛盾，CONTEXT 已明确论证）；`midframe_sim.score` 必须带 `model` 标识（跨模型不可比）。
**Source:** [VERIFIED: codebase audio_semantic.schema.json $comment + CONTEXT decisions]

### Pattern 4: 版本字面量单源
**What:** schema pattern 保持宽松（`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`），emit 的字面量锁在 `export_asset.py:SCHEMA_VERSION` 一处 —— schema 用 const 会拒绝 v1 minimal fixture 的 "1"（破坏 CONTRACT-09）。
**Source:** [VERIFIED: codebase SPEC.md §4 v1.1 changelog + export_asset.py:51-56]

### Anti-Patterns to Avoid
- **把阈值写进 schema**（SCORE-03 的 midframe_sim/judge 双门槛 Phase 21 校准后才存在；schema 只装结果 —— two-tier authority）[VERIFIED: CONTEXT]
- **全文件 byte diff 当红线证明**（generator.version/generated_at 必变；用 Phase 11 的 data-keys smoke 框架）
- **给 shots[] 加 pending/rendering 任务态**（schema 是结果集不是任务队列；失败 = `status:{state:failed}`，未跑 = 缺席）[VERIFIED: CONTEXT]
- **在 schema description/SPEC 里用英文写死阈值或「prompt 完美」类措辞**（AF-01 禁语 invariant 延续）
- **忘记 `_recover_v12_schema` fallback 还原 warnings items**（git tag 在就没问题，但 fallback 路径是 CI/shallow-clone 保险）

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 跨版本 schema 恢复 | 自维护 v1.2 schema 副本目录 | `git show v1.2:spec/schemas/<shape>.schema.json` + programmatic strip fallback | git tag 是 immutable truth；strip fallback 已有 `_recover_v1/_v11` 双先例 [VERIFIED: codebase verify_contract.py:282-365] |
| fixture 阶梯 gate | 新写独立校验脚本 | 扩展 `spec/validate.py` 第四阶 | 退出码聚合/错误格式/顺序全部复用 |
| 双向兼容证明 | 新 harness | 扩展 `_cross_version_check` pass (e)/(f) | 过滤规则（additionalProperties 豁免）是证明语义的一部分，分裂即漂移 |
| mp4/json 路径校验 | 新 pattern | 复用既有 anti-traversal pattern 惯例（`^(?!.*\.\.)…`） | 与 13 个既有 schema 一致，consumer 侧同一心智模型 |

**Key insight:** 本 phase 的全部价值在于「与既有证明机器完全同构」——任何新发明的新机制（新脚本/新证明通道/新 warnings 文件）都是漂移源。

## Common Pitfalls

### Pitfall 1: warnings 加宽弄破 backward 证明（本 phase 最高风险）
**What goes wrong:** v1.3 fixture 带结构化 warnings 条目 → pass (f) 里 recovered-v1.2 schema 报 `type` 错 → 现行 non-addprop 过滤判为 shared-field drift → verify_contract FAIL，被误当成契约破裂。
**Why it happens:** v1.1/v1.2 的 delta 全是新增 optional property（additionalProperties 错误天然豁免）；items 类型加宽是第一例非 property-delta。
**How to avoid:** 过滤规则按 §Wrinkle 1 精确扩展（path 前缀限定 `("generator","warnings")` + validator 限定 type/anyOf），汇总话术同步诚实化。
**Warning signs:** `backward v1.3→v1.2 asset: 1 non-additionalProperties error(s)` 且错误信息是 `… is not of type 'string'`。

### Pitfall 2: EIGHT_SHAPES 加 roundtrip 后 validate_eight_shapes 误报
**What goes wrong:** Phase 20 producer 挂载 `data.roundtrip` object → line 260 `"data.roundtrip is not a string"` 误报。
**How to avoid:** 同 plan 内做 object 特判（取 `rel["path"]`）；或本 phase 不加 EIGHT_SHAPES（二选一，勿只做一半）。
**Warning signs:** producer mode 在有 roundtrip.json 的真实目录上 FAIL。

### Pitfall 3: byte-identical 证明过度声明
**What goes wrong:** 声称「asset.json byte-identical」→ 验证时被 timestamp/SHA 差异打脸。
**How to avoid:** 严格用 Phase 11 框架：data-keys smoke + 11 文件 diff-clean + SCHEMA_VERSION 单源 grep。红线语义 =「除 schema_version 字面量外零字段漂移」。

### Pitfall 4: `= None` lazy-default / 误触空字段（Pitfall 11 延续）
**What goes wrong:** roundtrip 缺席时 data_block 仍出现 `"roundtrip": None` 或 `{}` → 破坏 byte-identical-absent。
**How to avoid:** mirror 现有 `if os.path.isfile(path): data_block[...] = …` 条件发射；不写 `data_block.get("roundtrip")` 类中间操作。`build_asset_dict` 的局部 dict + 组装时决定模式（line 288-291 注释）是防此坑的既有防御。
**Warning signs:** synthetic smoke 的 data keys != 5。

### Pitfall 5: fixture shot_id 越界
**What goes wrong:** roundtrip.json fixture 用了 shot_id 3+ → 一致性检查（若按推荐新增）报 dangling。
**How to avoid:** v1.2 shots.json fixture 只有 id {1,2}；roundtrip 条目 shot_id ∈ {1,2}。字段全覆盖问题见 Open Questions Q1。

### Pitfall 6: schema 改了忘 bump / bump 了忘 grep
**What goes wrong:** SCHEMA_VERSION 出现第二处字面量（复制粘贴）。
**How to avoid:** VERIFICATION 固定两条 grep（`= "1.3"` 恰 1 处；`= ` 恰 1 处）——Phase 11 SC#2 原文。

### Pitfall 7: v1.1/v1.2 老 gate 回归
**What goes wrong:** asset.schema.json 编辑误伤老 fixture（如 required 变动、pattern 收紧）。
**How to avoid:** `python3 spec/validate.py` 四阶全绿 + verify_contract pass (a)-(d) 不动且仍绿 —— 每个 wave 的固定动作。

## Code Examples

### A. roundtrip.schema.json 完整骨架（可直接 lift；命名/description 措辞属 CONTEXT discretion）
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/roundtrip.schema.json",
  "draft": "2020-12",
  "title": "Round-trip 验证（per-shot 复现 ref + 双信号打分 + verdict）",
  "description": "Canonical v1.3 round-trip sidecar —— per-shot h3 重生成视频 ref + scores{midframe_sim, judge} + verdict{accepted/rejected}。Producer (Phase 20/21) 在 regen+scoring 往返后写 roundtrip.json；consumer (Phase 22 gallery/dataset) 读它渲染并排审阅与 dataset 导出。缺席 on v1.0-v1.2 assets（byte-identical-absent；asset.schema.json#data.roundtrip 是 OPTIONAL）。阈值不进 schema（SCORE-03 Phase 21 校准后才存在；two-tier authority —— 阈值在 SPEC §5 散文）。",
  "$comment": "v1.3 决策溯源：(1) attribution 是 closed enum {prompt_faithful, model_diverged, prompt_underspecified} —— SCORE-02 三分类是自有分类学（非未校准外部模型输出），enum 使 SCORE-03 rejected 占比机器可审计；与 v1.2 emotion free-string 先例不矛盾（那是未校准的模型标签）。(2) midframe_sim 必带 model 标识 —— clip/siglip 变体不可跨模型比较。(3) judge 无连续分（分类器非回归器，伪精度）。(4) shots[] 只收「有产物」的 shot；regen 失败收录为 status{state:failed}；未尝试 = 缺席（schema 是结果集不是任务队列，不加 pending/rendering）。(5) fps/frames/seed/完整 workflow 参数不收 —— h3 workflow 是 kst 外部资产，不契约化。",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "shots"],
  "properties": {
    "schema_version": {
      "type": "string",
      "pattern": "^(0|[1-9]\\d*)(\\.(0|[1-9]\\d*))?$",
      "description": "Asset contract 版本 semver-lite，与 asset.json#schema_version 同源。Producer emit '1.3'；pattern 宽松兼容 '1'/'1.1'/'1.2'。"
    },
    "shots": {
      "type": "array",
      "description": "Per-shot round-trip 条目，shot_id 交叉引用 shots.json#id。仅此字段 required。",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["shot_id"],
        "properties": {
          "shot_id": {
            "type": "integer", "minimum": 1,
            "description": "Shot ID（交叉引用 shots.json#id）。仅此字段 required —— 其余 optional 支持 degrade 中间态（regen 成功未打分 / 有 score 无 verdict）。"
          },
          "regen": {
            "type": "object",
            "additionalProperties": false,
            "required": ["path", "video_content_hash", "engine_name", "engine_version", "prompt_version"],
            "description": "重生成视频 ref（REGEN-02 4-tuple cache 进契约，mirror WR-04 —— 可复现可审计）。与 status 互斥（一 shot 有产物或记失败，二选一；互斥由 producer 保证，schema 不做 if/then 硬约束）。path 相对 asset root。",
            "properties": {
              "path": {
                "type": "string",
                "pattern": "^(?!.*\\.\\.)([^/]+/)*roundtrip/[^:*?\"<>|]+\\.mp4$",
                "description": "重生成 mp4 相对路径（建议 canonical 布局 roundtrip/shot_XXX.mp4；anti-traversal mirror asset.schema 媒体惯例）。实际目录 Phase 20 定，pattern 只锁 mp4 + 防 traversal。"
              },
              "video_content_hash": {
                "type": "string",
                "pattern": "^[0-9a-f]{16}$",
                "description": "源视频内容 hash（sha256(首1MB+尾1MB+filesize) hex 前 16 位 —— analysis/call_shot_analysis.py:video_content_hash 同款，cache invalidation 级非安全 hash）。"
              },
              "engine_name": {"type": "string", "minLength": 1, "description": "复现引擎名（如 'MiniMaxH3ImageToVideo' / 'h3-fl2va'）。"},
              "engine_version": {"type": "string", "minLength": 1, "description": "引擎版本（ComfyUI workflow/模型版本标识）。"},
              "prompt_version": {"type": "string", "minLength": 1, "description": "prompt 生成器版本（prompts.json 产出方版本）。"},
              "duration_sec": {"type": "number", "minimum": 0, "description": "重生成视频时长（秒）。"},
              "width": {"type": "integer", "minimum": 1, "description": "实际渲染宽（REGEN-04 降分辨率模式记录实际值）。"},
              "height": {"type": "integer", "minimum": 1, "description": "实际渲染高。"}
            }
          },
          "status": {
            "type": "object",
            "additionalProperties": false,
            "required": ["state", "error"],
            "description": "regen 失败记录（regen 的互斥对位 —— 有产物用 regen，失败用 status，未尝试缺席）。",
            "properties": {
              "state": {"enum": ["failed"], "description": "失败态。刻意单值 enum —— 不加 pending/rendering 任务态（CONTEXT 锁）。"},
              "error": {"type": "string", "minLength": 1, "description": "失败原因（operator-facing；无凭据无 PII —— mirror warnings 惯例）。"}
            }
          },
          "scores": {
            "type": "object",
            "additionalProperties": false,
            "description": "双信号打分（SCORE-01/02）。各子对象可独立缺席（degrade 中间态）。",
            "properties": {
              "midframe_sim": {
                "type": "object",
                "additionalProperties": false,
                "required": ["score", "model"],
                "description": "中段帧相似度（25%-75% 时窗，显式排除被 condition 的首尾帧）。",
                "properties": {
                  "score": {"type": "number", "minimum": 0, "maximum": 1, "description": "相似度 [0,1]（帧 embedding 轨迹相似度，SCORE-01 定义）。"},
                  "model": {"type": "string", "minLength": 1, "description": "similarity model 标识（clip/siglip 变体不可跨模型比较 —— 不标 model 的分数不可审计）。"}
                }
              },
              "judge": {
                "type": "object",
                "additionalProperties": false,
                "required": ["attribution", "confidence", "reason"],
                "description": "VLM judge 归因三件套（SCORE-02）。",
                "properties": {
                  "attribution": {"enum": ["prompt_faithful", "model_diverged", "prompt_underspecified"], "description": "归因三分类（自有分类学，closed enum 可审计）。"},
                  "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "judge 置信度 [0,1]（模型自报，非校准精度 —— 见 SPEC fidelity disclaimer 第③层）。"},
                  "reason": {"type": "string", "minLength": 1, "description": "归因理由（模型产出 NL 文本）。"}
                }
              }
            }
          },
          "verdict": {
            "type": "object",
            "additionalProperties": false,
            "required": ["decision", "source"],
            "description": "终审（DATASET-01 合并写；rejected 永不删除）。",
            "properties": {
              "decision": {"enum": ["accepted", "rejected"], "description": "accepted = 「h3 可复现」≠「prompt 完美」（SPEC fidelity disclaimer 第①层）。"},
              "source": {"enum": ["auto", "human"], "description": "auto = 双门槛自动判（SCORE-03 校准后）；human = PRESENT-01 HITL 按钮覆盖。"},
              "decided_at": {"type": "string", "description": "ISO-8601 UTC（mirror asset.generator.generated_at 风格 —— 纯 string + description，不加 format 关键字）。"}
            }
          }
        }
      }
    }
  }
}
```
[VERIFIED: 骨架逐字段对照 audio_semantic.schema.json 结构 + CONTEXT 锁定决策；具体 pattern 取值（mp4 路径前缀 `roundtrip/`、16-hex hash）为推荐值 [ASSUMED]，planner 可在 discretion 内调整]

### B. validate.py V13 接线（mirror V12 三件套 + main 聚合）
```python
# 常量区（V12_ORDER 之后）
V13_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.3"
V13_FIXTURE_MAP = {
    # 12 v1.2 entries verbatim（11 byte-copied substrate + asset.json 编辑版）
    "asset": "asset.json", "shots": "shots.json",
    "audio_analysis": "audio_analysis.json", "transcript": "transcript.json",
    "frames": "frames.json", "prompts": "prompts.json",
    "characters": "characters.json", "props": "props.json",
    "registry": "registry.draft.json", "registry-edits": "registry.edits.json",
    "audio_semantic": "audio_semantic.json", "speakers": "speakers.json",
    # 1 NEW v1.3 shape:
    "roundtrip": "roundtrip.json",
}
V13_ORDER = V12_ORDER + ["roundtrip"]

def validate_v13() -> int:
    """对 spec/fixtures/v1.3/ 下的 13 个 v1.3 fixture 跑 schema 校验（mirror validate_v12）。"""
    # 循环体与 validate_v12 逐行同构，仅换常量与前缀 [valid-v13]/[FAIL-v13]

# main() 内：
v13_failures = validate_v13()
total_strict_failures = (minimal_failures + v11_failures + v12_failures
                         + v13_failures)
# 汇总打印行加 f"v1.3 failures={v13_failures}, "
```
[VERIFIED: 模式对照 spec/validate.py:73-98,181-214,290-310]

### C. verify_contract.py v1.2↔v1.3 证明（pass e/f + recover + 过滤扩展）
```python
def _recover_v12_schema(shape: str):
    """恢复 v1.2 schema 用于 backward v1.3→v1.2。Primary: git show v1.2:…
    Fallback: strip v1.3 additive keys —— data.properties.roundtrip +
    generator.properties.warnings.items 还原为 {"type":"string"}（v1.3 的
    items 加宽是首个非 property-delta，必须一并还原）。"""
    # git show v1.2:spec/schemas/{shape}.schema.json   ← 已实测可用
    # fallback: deep-copy current → pop data.roundtrip →
    #           schema["properties"]["generator"]["properties"]["warnings"]["items"] = {"type": "string"}

# _cross_version_check 内新增（mirror pass (c)/(d) 结构）：
# (e) FORWARD v1.2→v1.3: v1.2 fixture asset.json × 当前(v1.3) schema → 0 errors
#     （v1.2 fixture 的 string warnings 对加宽后 items 仍合法 —— forward 天然干净）
# (f) BACKWARD v1.3→v1.2: v1.3 fixture asset.json × _recover_v12_schema →
#     仅两类「文档化 delta」错误：
#       e.validator == "additionalProperties"                （data.roundtrip 新键）
#     e.validator in ("type", "anyOf") 且
#     tuple(e.absolute_path[:2]) == ("generator", "warnings") （items 加宽）
#     其余 → non-additive failure（shared-field drift）
```
[VERIFIED: pass (c)/(d) 原文对照 verify_contract.py:428-472；过滤扩展机制为工程设计 ASSUMED]

### D. export_asset.py 两处编辑点
```python
SCHEMA_VERSION = "1.3"   # line 56；同步更新 51-55 注释块为 v1.3 语义

# build_asset_dict 内（line 320-329 Phase 11 块之后 mirror）：
roundtrip_path = os.path.join(work_dir, "roundtrip.json")
if os.path.isfile(roundtrip_path):
    try:
        with open(roundtrip_path, encoding="utf-8") as f:
            rt = json.load(f)
        counts = {"accepted": 0, "rejected": 0}
        for s in rt.get("shots", []):
            d = (s.get("verdict") or {}).get("decision")
            if d in counts:
                counts[d] += 1
        data_block["roundtrip"] = {
            "path": "roundtrip.json",
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
        }
    except (OSError, json.JSONDecodeError) as e:
        print(f"[warn] roundtrip.json malformed → data.roundtrip will be OMITTED: {e}")
        # mirror _build_registry_snapshot WR-05：不持久化可疑统计

# main() warnings 装载加宽（line 496-499）：
#   candidate 元素接受 str 或 {"code": <三 enum 之一>, "detail": str}；
#   非合规形状 → 整体回退 None（保持既有 silent-fallback 语义）
```
[VERIFIED: 结构对照 export_asset.py:320-329,488-501,174-244；object 统计与 warn+OMIT 为推荐设计 ASSUMED]

## State of the Art（本契约域内的版本史）

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.0：6 schema、5 required data 形状 | v1.1：+3 schema（characters/props/registry）、optional 挂载 | 2026-07-24 (Phase 5) | 确立 additive-only + cross-version proof 模式 |
| v1.1 双向证明（v1↔v1.1） | v1.2 三向（v1.0↔v1.1↔v1.2）+ `_recover_v11_schema` git-tag primary | 2026-07-25 (Phase 11) | git tag 成为 schema 恢复 immutable truth |
| warnings items = string（v1.1） | v1.3 加宽 string\|{code,detail} | 本 phase | **首个 items 类型加宽** —— backward 过滤规则必须扩展（§Wrinkle 1） |
| data.* 挂载 = string path | v1.3 data.roundtrip = object{path,stats} | 本 phase | **首个 object 挂载** —— validate_eight_shapes 需特判（§Wrinkle 2） |

**Deprecated/outdated:** 无（全部旧机制仍 load-bearing；CLAUDE.md 的 STACK 段「No pytest cases present」已过时 —— tests/ 现有 7 个 pytest 文件，但本 phase 不依赖它新增）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `data.roundtrip` 统计字段名 `accepted_count`/`rejected_count`/`path`（形状「object+file ref+统计」是 CONTEXT 锁，键名是 discretion） | Wrinkle 2 / Code Ex. D | 低 —— 命名漂移只影响 Phase 20/22 对齐，SPEC 文档即契约可查 |
| A2 | 结构化 warnings 条目 required=["code"]、detail optional | Wrinkle 1 | 低 —— discretion 范围；若 detail 必填则 fixture 多一行 |
| A3 | backward pass (f) 过滤扩展机制（path 前缀 + validator 限定）| Wrinkle 1 / Code Ex. C | 中 —— 机制不当会误放真 shared-field drift 或误拦合法 delta；verifier 必须含负测试（注入 verdict 漂移必须仍 FAIL） |
| A4 | export_asset.py 本 phase 落地 warnings 装载加宽 + roundtrip 挂载统计（含 malformed → warn+OMIT） | Wrinkle 1/2 | 低 —— 归属划分问题；若 defer 到 Phase 20 需在 ROADMAP/DEPENDS 显式记录，否则 RT-04 通道悬空 |
| A5 | EIGHT_SHAPES 本 phase 加 "roundtrip" + object 特判一起做 | Wrinkle 2 | 低 —— 不加则 Phase 20 必须补；加了不特判则 Phase 20 producer 误报 |
| A6 | regen 对象内部 5 字段全 required（对象存在即完整 audit tuple） | Code Ex. A | 低 —— 若部分 required 会弱化 REGEN-02 可审计性 |
| A7 | verdict.decided_at = 纯 ISO string（无 format 关键字，mirror generated_at） | Code Ex. A | 低 —— jsonschema 默认不校验 format，加了对齐也无损 |
| A8 | status.state 单值 enum ["failed"] | Code Ex. A | 低 —— CONTEXT 明确不加任务态；未来加态 = minor bump |
| A9 | regen.path canonical 前缀 `roundtrip/`（pattern 只锁 mp4 + anti-traversal） | Code Ex. A | 低 —— 实际目录 Phase 20 定；pattern 过严会逼 Phase 20 改 schema |
| A10 | v1.3 fixture asset.json 保留 1 条 legacy string warning + 增结构化条目（双形并存证明） | Wrinkle 1 / Open Q1 | 低 —— fixture 数值属 discretion；但结构化条目必须在 fixture 中出现（SC#4「可表达」的证明载体） |

## Open Questions (RESOLVED — all three closed at plan level; adopted answers marked inline)

1. **fixture 全字段覆盖 vs 2-shot 上限**
   - What we know: v1.2 fixture shots.json 只有 id {1,2}（substrate 必须 byte-copy）；CONTEXT 要求 fixture「覆盖全字段但取小值」；roundtrip 的状态空间 = full / regen-only / scored-no-verdict / failed-status / accepted-auto / rejected-human。
   - What's unclear: 2 个 shot 条目装不下全部状态×字段组合。
   - Recommendation: fixture 内 2 条覆盖主路径（shot 1 = full: regen+双 score+verdict{accepted,auto}；shot 2 = degrade+human: regen+midframe_sim+verdict{rejected,human,decided_at}）；**其余形状**（status.failed、judge 缺席、width/height 等 optional 字段）用 VERIFICATION 里的 direct-validator 实例检查覆盖（mirror Phase 11「all 12 fixtures validated via direct Draft202012Validator」的加强版）—— 一段 python -c 构造全字段实例过 schema。planner 可改为在 fixture 中安排 3 条 shot_id ∈{1,2} —— 不推荐（一 shot 一条目的结果集语义）。
   - **[RESOLVED → 18-02 Task 1]** Adopted the recommendation as-is: 2-shot fixture (shot 1 full/auto-accept, shot 2 degrade+human-reject) + all remaining shapes via direct-validator instances inside Task 1's automated verify (status.failed entry, all 3 attribution values, optional-field absences, all 3 warning codes as solo structured entries).
2. **EIGHT_SHAPES 归属（本 phase vs Phase 20）** — 见 A5；两案皆可，勿做一半。
   - **[RESOLVED → 18-02 Task 3]** EIGHT_SHAPES gains `"roundtrip"` THIS phase, paired in the SAME task with the `validate_eight_shapes` object 特判 (`rel.get("path")` before the string check) — the 勿做一半 rule is satisfied by same-plan pairing, with an in-code Pitfall 2 pairing comment mandated.
3. **roundtrip.json 挂载前是否 schema-validate**（registry_snapshot 先例 validate；audio_semantic 挂载先例不 validate）
   - Recommendation: 本 phase 只做 JSON 可解析 + 计数（Code Ex. D）；完整 schema gate 在 validate.py V13/producer 侧已有，export 内重复校验收益低。若 verifier 想加，mirror `_validate_registry_for_snapshot` fail-soft 模式。
   - **[RESOLVED → 18-01 Task 3]** No pre-mount schema validation in export_asset.py: JSON-parse + verdict-count only, encoded as an explicit DO NOT in 18-01 Task 3's action; the full schema gate stays in validate.py V13 (18-02 Task 2) / verify_contract producer mode.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| jsonschema | 全部 schema 校验/证明 | ✓ | 4.26.0 | — |
| Python 3 | 全部 | ✓ | 3.12.3 (/usr/bin/python3) | — |
| git（含 tag v1.0/v1.1/v1.2） | `_recover_v12_schema` primary | ✓ | tag 三者均在（v1.2→276e698 已验证内容） | programmatic strip fallback |
| ep01 真实 asset dir | verify_contract producer mode | ✓ | `output/虫虫武侠小故事《小江湖》第01话…/asset.json` 在盘 | `PHASE4_ASSET_DIR` 覆盖 |
| pytest | 现有 tests/ 回归 | ✓ | 9.0.3 | — |
| ffmpeg/ffprobe | export smoke（duration 兜底） | ✓（pipeline 工作机既有） | 6.1.1 | transcript.duration 优先，几乎不触 |
| consumer worktree（kst-canvas-consumer） | verify_contract consumer/e2e mode | ✗ | — | **不需要** —— 契约 phase 只跑 producer mode；STATE.md 已记录 unmerged 不阻塞 v1.3 |

**Missing dependencies with no fallback:** 无。
**Missing dependencies with fallback:** consumer worktree（见上表，非本 phase 依赖）。

注：`/home/kai/workspace/kais-shot-timeline` 与 `/data/workspace/kais-shot-timeline` 同 inode（bind mount），路径差异无影响。[VERIFIED: runtime stat]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | jsonschema 4.26.0（`Draft202012Validator`）+ Python 3.12.3 stdlib；pytest 9.0.3 仅回归 |
| Config file | none —— 复用 `spec/validate.py` + `scripts/verify_contract.py`（mirror 11-VALIDATION「NOT unit tests」） |
| Quick run command | `python3 spec/validate.py`（四阶 gate，~1s） |
| Full suite command | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RT-01 | roundtrip.schema.json 对人工 fixture 全字段校验通过（draft 2020-12、aP:false） | schema | `python3 spec/validate.py`（v1.3 failures=0） | ❌ Wave 0（fixture 本身是交付物） |
| RT-01 | schema 自身合法 | schema | `python3 -c "from jsonschema import Draft202012Validator as D; import json; D.check_schema(json.load(open('spec/schemas/roundtrip.schema.json')))"` | ❌ Wave 0 |
| RT-01 | 负测试：未知字段被拒 | schema(负) | `python3 - <<'PY'`（构造 fixture 副本注入 `"bogus":1` → `iter_errors` ≥1，validator==additionalProperties） | ❌ Wave 0 |
| RT-01 | 负测试：score 越界 / attribution 越界 enum 被拒 | schema(负) | 同上式注入 `score=1.5` / `attribution="banana"` → ≥1 error | ❌ Wave 0 |
| RT-01 | byte-identical-absent 红线 | smoke | synthetic work_dir（仅 5 required JSON）跑 `build_asset_dict` → data keys == 5 且 warnings 缺省；11 个非 asset fixture 文件 `diff` v1.2 → clean | ❌ Wave 0（VERIFICATION 内 ad-hoc，不加常驻 harness —— CONTEXT 锁） |
| RT-02 | SCHEMA_VERSION 单源 | grep | `grep -c 'SCHEMA_VERSION = "1.3"' scripts/export_asset.py`==1 且 `grep -c 'SCHEMA_VERSION = '`==1 | ✅ 目标文件在 |
| RT-02 | validate.py 四阶 gate | cli | `python3 spec/validate.py` → exit 0，输出含 `v1.3 failures=0` | ✅（待扩展） |
| RT-02 | v1.2↔v1.3 forward 0 errors | cli | `python3 scripts/verify_contract.py --mode=producer`（pass e 在 producer mode 内跑） | ✅（待扩展） |
| RT-02 | v1.2↔v1.3 backward 0 non-additive（excl. 文档化 delta） | cli | 同上（pass f） | ✅（待扩展） |
| RT-02 | backward 过滤负测试（真 drift 仍 FAIL） | cli(负) | 临时副本注入 `asset_type:"other"` 重跑 backward 逻辑 → 必须 FAIL（证明过滤没有变盲） | ❌ Wave 0 |
| RT-02 | harness 自身 fail-loud | cli | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | ✅ |
| RT-03 | SPEC §4/§5/§10 + README | manual-only | `grep -n "1\.3" spec/SPEC.md`（changelog 条目/§5.10/§1 的 14 个计数）+ 人工审阅（三层 disclaimer 完整性、禁语不出现） | ✅（文档在，待编辑） |
| RT-04 | warnings 双形在 schema 可表达 + fixture 演示 | schema | v1.3 fixture asset.json 同时含 string 与 {code,detail} 条目且 validate 绿；负测试 `code:"banana"` 被拒 | ❌ Wave 0 |
| RT-04 | degrade 三因由 enum 齐全 | schema | `python3 -c`（三 enum 值逐一构造实例过 schema） | ❌ Wave 0 |
| RT-04 | roundtrip 缺席导出照常 | smoke | RT-01 的 synthetic smoke 同一命令（data keys==5 = 照常 + 缺席） | ❌ Wave 0 |
| 回归 | 老阶不破 | cli | validate.py 输出 minimal/v1.1/v1.2 failures 全 0；`python3 -m pytest tests/ -x` 绿 | ✅ |

### Sampling Rate
- **Per task commit:** `python3 spec/validate.py`（~1s）
- **Per wave merge:** `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 -m pytest tests/ -x`
- **Phase gate:** Full suite 绿 + VERIFICATION 记录 byte-identical smoke 证据后才进 `/gsd:verify-work`

### Wave 0 Gaps
- 全部 ❌ 项均为本 phase 交付物自身的验证（fixture/schema 尚未存在），由 11-02 对应 plan 的 verification 步骤承接 —— 无需独立测试文件（mirror Phase 11：VALIDATION.md 明确 NOT unit tests）。
- 无 framework install 需求。

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|----------------|---------|------------------|
| V2 Authentication | no | 本 phase 无网络/身份面（纯本地 schema/fixture/docs） |
| V3 Session Management | no | 同上 |
| V4 Access Control | no | 同上 |
| V5 Input Validation | yes | JSON Schema draft 2020-12 + `additionalProperties:false` 全层 + anti-traversal pattern（`^(?!.*\.\.)`）on regen.path / data.roundtrip.path —— 契约本身就是 V5 控制件 [VERIFIED: codebase asset.schema.json pattern 惯例] |
| V6 Cryptography | no | video_content_hash 是 cache key 非安全 hash（`hexdigest()[:16]`，schema description 已明示）—— 不声称密码学性质 |

### Known Threat Patterns for {JSON-contract pipeline}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 路径穿越（sidecar 内 path 字段指向 asset root 外） | Tampering/Elevation | anti-traversal pattern 拒 `..`/绝对路径/drive letter（14 个 schema 统一惯例，roundtrip mirror） |
| 凭据泄漏进 warnings（detail 是自由文本） | Information Disclosure | 既有惯例延续：producer 侧 redact（call_shot_analysis WR 注释：http://user:pass@host 不进 warning 串）；schema description 重申 no PII/no tokens（mirror asset.schema warnings description line 59） |
| 模型产出文本 = 未来 XSS 面（judge.reason / status.error） | Tampering | 本 phase 仅契约（schema minLength/类型）；HTML 渲染的 `_esc()` hardening 属 Phase 22 PRESENT-01（REQUIREMENTS 已点名）—— SPEC §5.10 行文预告该义务 |
| 恶意/畸形 fixture 内容触发校验器崩溃 | DoS | jsonschema iter_errors + try/except JSONDecodeError 的既有容错模式（validate.py/verify_contract.py 全部既有路径已如此） |

## Sources

### Primary (HIGH confidence)
- 代码库逐行阅读（本 session 全部 [VERIFIED: codebase …] 标注）：`scripts/export_asset.py`、`spec/validate.py`、`scripts/verify_contract.py`、`spec/schemas/asset.schema.json`、`spec/schemas/audio_semantic.schema.json`、`spec/SPEC.md`、`spec/README.md`、`spec/fixtures/{minimal,v1.1,v1.2}/`
- Phase 11 先例全套：`.planning/milestones/v1.2-phases/11-contract-v1-2/`（11-CONTEXT / 11-RESEARCH / 11-01..03-PLAN / 11-VALIDATION / 11-VERIFICATION / 11-REVIEW）
- runtime 验证：`git show v1.2:spec/schemas/asset.schema.json` 内容核对、jsonschema 4.26.0、pytest 9.0.3、ep01 asset 在盘、fixture shots id {1,2}、warnings 消费者 grep 为空、双路径同 inode

### Secondary (MEDIUM confidence)
- 无（未用 WebSearch/WebFetch —— 纯仓内镜像 phase，无外部生态问题）

### Tertiary (LOW confidence)
- 无

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 零新依赖，jsonschema 4.26.0 runtime 实测
- Architecture: HIGH — 全部机制逐行核对 + Phase 11 三 plan 先例原文
- Pitfalls: HIGH（Wrinkle 1/2 之外的）/ MEDIUM（Wrinkle 1 的过滤扩展机制 —— 工程设计无先例，已列 A3 + 负测试要求）

**Research date:** 2026-08-19
**Valid until:** 2026-09-18（仓内契约域，稳定；若 Phase 17 后有未 commit 的 spec 改动落盘需重对 diff）
