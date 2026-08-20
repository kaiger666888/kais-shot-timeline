# Phase 21: Scorer + 阈值校准 - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

双信号打分——中段帧 CLIP/SigLIP 轨迹相似度（便宜信号）+ VLM judge 归因（区分 prompt 好/h3 不行 vs prompt 欠约束）——在 ep01 ≤20 镜抽样上实测分布、锁定 accepted 双门槛，verdict 写入 schema 合法的 `roundtrip.json`，rejected 永不删除。

Requirements: SCORE-01, SCORE-02, SCORE-03, DATASET-01。

**In scope:**
- uniform-20 @1344×768 overnight 批渲染（h3_regen 客户端驱动，19 镜可渲 + shot 70 跳过）
- `analysis/roundtrip/scorer.py`（SigLIP midframe 轨迹相似度）+ `analysis/roundtrip/judge.py`（qwen-eye 三分类归因）
- 20 镜双信号分布实测 → τ_sim 锁定（Kai 看分布裁决）+ PROJECT.md Key Decisions + 校准报告
- verdict 合并写 roundtrip.json（幂等、rejected 永不删除）
- judge 归因人工抽检 5 镜一致（SC3 checkpoint）

**NOT in scope:**
- HITL 审阅面板（Phase 22 PRESENT-01）
- dataset 导出（Phase 22 RT-05）
- pipeline step_roundtrip 挂载（Phase 22 PIPE-01）

</domain>

<decisions>
## Implementation Decisions

### 打分对象与批渲染编排
- **Phase 21 内先跑 uniform-20 @1344×768**（SC4 字面要求；smoke 2 镜不够校准；门槛锁定对正式分辨率——896×512 是验证模式）——h3_regen 客户端驱动 overnight 批
- **串行链**：h3 批（GPU 满载）→ scorer（轻量）→ judge qwen-eye（13.4GB）——复用 Phase 20 显存探测编排约定
- **分两模块**：`analysis/roundtrip/scorer.py` + `analysis/roundtrip/judge.py`（不同生命周期/依赖，mirror repo 每步一模块惯例）

### midframe 相似度实现（SCORE-01）
- **SigLIP so400m-patch14-384**（盘上 HF cache 离线加载零下载）+ `model` 字段记录（schema 要求跨模型不可比）
- 两侧各 resample 到**固定 N=8 帧 @25%-75% 时窗** → per-position cosine → **mean 为主分数**；DTW 留升级位
- 打分帧**时间戳清单写进 cache 元数据**（哪 8 帧、各自 t%——审计可回放，t=0/t=end 显式排除有据）
- transformers + `HF_HUB_OFFLINE=1` 盘 cache 加载（零下载）

### VLM judge 归因（SCORE-02）
- 输入：原片段 vs regen **各 4 帧全时窗**（0/33/66/100%——judge 判断符不符 prompt，condition 帧含信息）拼 **2×4 grid 图** + prompt_text 一次调用
- 结构化输出：**qwen-eye 直接输出 JSON**（提示词含三分类定义 + JSON 模板）→ 本地严格校验（enum/confidence 范围/reason 长度）→ 失败重问 ≤2 次——复用 glm-structured-output 的「严格校验+重试」模式但零外部依赖
- 三分类定义逐字进提示词（prompt_faithful=描述了X且渲染出X / model_diverged=描述了X渲染成Y / prompt_underspecified=欠约束 h3 自行脑补）+ reason 要求引用 prompt 具体短语作证据
- 人工抽检：**抽 5 镜 Kai 复核** judge 归因 vs 自己判断（一致率 ≥4/5 可接受；不一致镜进校准报告）——checkpoint

### 阈值校准与 verdict 写入（SCORE-03, DATASET-01）
- 双门槛：`accepted ⇔ midframe_sim ≥ τ_sim ∧ attribution == prompt_faithful`（硬合取；无 confidence 第二门槛——20 镜定两阈已勉强，加了是伪精度）
- 校准流程：20 镜散点（sim 分布 + attribution 分桶）→ **Kai 看分布定 τ_sim** + 理由 → PROJECT.md Key Decisions（SC4 明文）+ 校准报告 `.planning/research/roundtrip-threshold-calibration.md`（rejected 占比按归因分桶——SC4 防偏向审计）
- verdict 来源：本 phase 全部 `source: "auto"`（HITL Phase 22 覆盖写 human——schema 已预留）；decided_at 记录
- 幂等合并（SC5）：重跑 READ-merge——**已存在 verdict 的镜永不覆盖**（rejected 永续 + human verdict 防意外覆盖），只补缺 verdict 的镜；scores 可更新（新模型重打分）但 verdict 冻结

### Claude's Discretion
- grid 拼图实现（PIL/ffmpeg）、judge 提示词具体措辞、scorer cache 文件形状细节
- resample 帧提取的 ffmpeg 调用细节
- 校准报告排版与散点呈现方式

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analysis/roundtrip/h3_regen.py`（Phase 20 刚验证）——批渲染驱动 + VRAM guard 编排 + sidecar READ-merge + warnings 通道全套；uniform-20 清单锚点测试已在
- `spec/schemas/roundtrip.schema.json`——scores{midframe_sim{score,model}, judge{attribution,confidence,reason}} + verdict{decision,source,decided_at} 是本 phase 的写入目标
- `analysis/engine_clients/qwen_eye_client.py`——judge 的引擎客户端（observe_pair/ask_text + 生命周期 + KAP release）
- SigLIP so400m HF cache（`models--google--siglip-so400m-patch14-384`）+ transformers 5.6.2 已装
- `spike report` 先例（vision-seq-spike-report.md）——校准报告结构参考
- glm-structured-output 模式（全局 skill）——「严格 schema 校验 + 重试」的 driver 形状参考（零依赖借用模式）

### Established Patterns
- 4-tuple cache + per-shot 中间态 + graceful-degrade + [roundtrip] warnings
- READ-merge-write sidecar（20-03 已建 write_roundtrip_sidecar——本 phase 扩 scores/verdict 半边）
- 引擎 try/finally 生命周期

### Integration Points
- `route_cache/scorer/shot_XXX.json`（相似度元数据 + 帧清单审计）+ `route_cache/judge/shot_XXX.json`
- `output/<video-stem>/roundtrip.json`（scores + verdict 写入，schema 预校验）
- `.planning/research/roundtrip-threshold-calibration.md`（校准报告）
- PROJECT.md Key Decisions（τ_sim 决策行）

</code_context>

<specifics>
## Specific Ideas

- SC2 明文「打分帧清单可审计，research Pitfall 4」——帧时间戳进 cache 元数据是硬要求
- SC3 明文「ep01 抽样上有人工抽检一致的示例——归因不是信口开河」
- SC4 明文「rejected 占比被记录且可审计（防数据集静默偏向简单动作，research Pitfall 5）」
- judge 与 h3 批串行（复用 Phase 20 编排约定——roadmap Depends on 明文）

</specifics>

<deferred>
## Deferred Ideas

- DTW 轨迹对齐升级（校准期 mean 足够，时序错位容忍留后续）
- 双模型交叉打分（CLIP+SigLIP 一致性校验——后续质量增强）

</deferred>
