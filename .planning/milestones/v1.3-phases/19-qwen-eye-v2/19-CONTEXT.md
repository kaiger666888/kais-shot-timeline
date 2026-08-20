# Phase 19: qwen-eye v2 看片段 - Context

**Gathered:** 2026-08-19
**Status:** Ready for planning

<domain>
## Phase Boundary

把 prompts.json 的 action/camera facet 从「3 静帧脑补」升级为「≤8 帧序列逐帧实证」（llama.cpp 单图 bug 硬约束下的务实版），并把 v1.2 `audio_semantic` 作为 ear 融进视觉 prompt——独立于 round-trip 闭环就提升 prompt 质量。

Requirements: VISION-01, VISION-02。

**In scope:**
- 帧序列逐帧问答升级 action/camera facet（每镜 ≤8 帧、只填空缺 facet）
- 合并策略 A/B spike（ep01 小样本）→ 锁定 + spike report 落档
- ear 融合（audio_semantic 摘要注入逐帧提问，--no-ear 可跳过）
- per-shot cache 幂等 + pipeline pre-step 挂载 + graceful-degrade（mirror local_vision 惯例）

**NOT in scope:**
- scene/subject facet 的 v1 路径（零改动零回归）
- vLLM + Qwen3-VL-8B 视频原生（VISION-03，deferred 升级位）
- round-trip 闭环任何部分（Phase 20/21/22）
- 修改 qwen-eye 引擎本体

</domain>

<decisions>
## Implementation Decisions

### 帧序列抽取与逐帧问答设计
- 每镜**等间隔均匀 ≤8 帧**（时窗内均匀采样；动作链时序覆盖最完整；长镜天然降密度）
- action/camera **分开问**（两个 facet 独立、混问互相污染；~100 镜 ×8 帧 ×2 问 ≈1600 calls，cache 后重跑秒级）
- camera 运镜用**相邻帧对问**：frame_i + frame_{i+1} 两图一次调用问「相对前一帧镜头/主体怎么动了」（7 对/镜）——运镜本质是帧间差异，单帧答不出；qwen_eye_client.observe() 多图入口已存在
- 新增 `MAX_SEQ_FRAMES_PER_SHOT = 8` 常量，**不动** v1 的 `MAX_FRAMES_PER_SHOT = 3`（scene/subject v1 路径零回归）

### 合并策略 A/B spike（SC2）
- spike 规模：ep01 抽 **≤10 镜**（含 1-2 个强运镜镜 + 1-2 个长动作链镜）
- 候选：**A=时序拼接**（t₁答→t₂答→…保时序证据链）vs **B=LLM 二次合并**（8 帧答案纯文本再喂一次产连贯描述——单图 bug 不影响纯文本调用）；baseline=最长回答为代表只作参照
- 判据：**Kai 人工并排盲评**（3 策略同镜产物打分）+ 客观辅助指标（时序连接词密度、实体/动作动词覆盖率、长度）——Q3 27B 动作描述质量是 research Pitfall 3 明示的未验证假设，机器判据会循环论证
- 结论落点：`.planning/research/vision-seq-spike-report.md`（mirror Phase 10 audio-spike-report 先例：证据 + 锁定结论 + 样例摘录）

### 模块形态、防覆盖边界与 cache
- **新模块** `analysis/vision_seq_facets.py`（v1 local_vision_facets.py 零改动零回归；repo 惯例每步一模块）
- **只填空缺**：action/camera 为 `""` 的镜才填，已有值**永不覆盖**（route/人工产物无法从文本长度区分优劣；mirror local_vision 边界 + aw2-fast 防覆盖守卫精神）——不做「更短就替换」
- cache：`route_cache/vision_seq/shot_XXX.json`，4-tuple key + `PROMPT_VERSION = "vision-seq-v1"`（与 v1 local-vision-v1 独立目录独立版本）；**ear on/off 进 cache key**
- pipeline 挂载：run_pipeline step 5.5 之后新增**无编号 pre-step 5.6**（mirror local_vision 先例：不 bump step counter、`--no-vision-seq` 跳过；local_vision 之后、step_reid 之前）

### ear 融合（VISION-02, SC3）
- **生成时注入**：该镜 audio_semantic 摘要拼进逐帧提问上下文（「该镜音频：…结合这一帧…」），模型自己权衡视听证据——非后处理规则改写
- 字段白名单：`dialogue.text`（截断）+ `dialogue.emotion` + `sfx.events` + `sfx.description`；**不进**：word-level timestamps（实验性）、reproduction 层（复现 prompt 非感知证据）、speakers（身份归 re-id）
- audio_semantic.json 存在时**默认开**，`--no-ear` 跳过；无该文件时自动无 ear（degrade 不加 warning——v1.2 集没跑 audio 步是常态）
- 生效验证：ep01 同镜 **ear on/off 双跑 diff 展示**（进 spike report）+ 单元级断言（prompt 组装函数带 audio 输入时含音频摘要子串、--no-ear 时不含）

### Claude's Discretion
- 逐帧提问的具体文案措辞（mirror v1 SCENE/SUBJECT_PROMPT 风格）
- 均匀采样的具体实现（帧索引计算、边界处理）
- spike 镜选取的具体 shot_id（按「强运镜/长动作链」标准扫 ep01 挑）
- 客观辅助指标的具体计算方式

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analysis/local_vision_facets.py`（373 行）——v1 完整先例：4-tuple cache（`route_cache/local_vision/shot_XXX.json` + `PROMPT_VERSION="local-vision-v1"`）、engine 生命周期 try/finally（ensure_ready…stop_if_owned 防 13.4GB 泄漏）、graceful-degrade（引擎不可用 → facet 保 "" + `[vision]` warning + exit 0）、写前 Draft202012Validator 自校验 + 原子写、warnings sidecar READ-merge-write 防 self-accumulate
- `analysis/engine_clients/qwen_eye_client.py`（279 行）——`observe_single` 单图入口 + `observe()` 多图入口（多 user 消息合法，v2 相邻帧对问可用）；ENGINE_NAME/ENGINE_VERSION 已导出
- `frames_5fps/` 全帧 jpg（step 2 已产，零额外抽帧 IO）；`select_frames()` 时窗选帧逻辑可参考（`*_ds1280.jpg` 变体忽略）
- `run_pipeline.py:803-824`——step 5.5 local_vision pre-step 挂载模式（无编号、--no-local-vision 跳过、条件判断 os.path.exists）
- v1.2 `audio_semantic.json` 数据（ep01 已产）——ear 输入

### Established Patterns
- facet 边界不越权：subject 身份归 re-id、scene/action/camera 归视觉步骤，本步骤永不写 char_XXX
- 只填空缺 + 永不覆盖（route/人工产物保护）
- 引擎 warnings 用 `[vision]` 前缀（v2 可用 `[vision-seq]` 区分）
- cache 任一 4-tuple 不匹配即 miss 重拉；PROMPT_VERSION 是 prompt 变更→全量失效旋钮

### Integration Points
- `run_pipeline.py` step 5.5 之后插 pre-step 5.6（local_vision 后、step_reid 前）
- `prompts.json` action/camera 两键（写前 schema 自校验）
- `route_cache/warnings.json` sidecar（READ-merge-write）
- `.planning/research/vision-seq-spike-report.md`（spike 结论落档）

</code_context>

<specifics>
## Specific Ideas

- SC1 明文「兼容 260819-aw2-fast 防覆盖守卫」——今晨 quick session 建立的防覆盖约定，v2 只填空缺语义与其一致
- SC4 幂等：per-shot cache 命中不重复烧 GPU，重跑秒级完成
- research Pitfall 3：Q3 27B 帧序列动作描述质量未验证——spike 的存在理由

</specifics>

<deferred>
## Deferred Ideas

- VISION-03 vLLM + Qwen3-VL-8B 视频原生输入（模型已在盘 `/data/models/comfyui/LLM/Qwen-VL/`）——REQUIREMENTS Future 名单
- 「更短就替换」的 facet 升级逻辑——未来需要时再加（当前只填空缺）

</deferred>
