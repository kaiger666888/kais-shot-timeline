# v1.3 Research Summary — Round-trip Validation

**日期:** 2026-08-19 · **来源:** Kai 提议 + Claude Code 本地实证调研（全部路径/端口/数字已验证）
**详细版:** `v1.3-roundtrip-validation-proposal.md`（同目录）

---

## 1. 要做的事（一句话）

逆推→复现→比对闭环：qwen-eye 看片段帧序列逆推 prompt → h3 fl2va（首尾帧 conditioning）复现 →
中段帧打分 + VLM judge 归因 → accepted = 经复现验证的 (首帧, 尾帧, prompt) 真值数据集。
本质是 **rejection sampling 造 SFT 真值**。

## 2. Stack（全部已在位，零新模型下载）

| 件 | 事实 | 对 v1.3 的意义 |
|----|------|----------------|
| qwen-eye 引擎 | :8125 llama.cpp，Qwen3.8-27B-VL Q3_K_XL GGUF，13.4GB VRAM lease（`analysis/engine_clients/qwen_eye_client.py`） | 已接（`local_vision_facets.py` 填 scene/subject）；**硬约束：llama.cpp 多图丢弃 bug → 只能单图 `observe_single`，ctx 16K** |
| h3 fl2va | ComfyUI `MiniMaxH3ImageToVideo`（v0.30.0+ 内置节点）；模型 `minimax_h3_fl2va_pruned_int8_convrot` (~20GB) + `qwen3vl_32b_minimax_h3_nvfp4_awq` text encoder (~15GB)；shift_video=12.0 / cfg=1.0 / euler+simple / length 17k+5 对齐 (124帧=5s) | 首尾帧→视频+**音频联合**生成；3090 上 5s 镜 5-8min，需 11-22GB VRAM |
| kmc 先例 | `kais-hermes-skills/.../h3_batch_render_v4.py` + `templates/h3_ref2va_workflow.py` + skills `minimax-h3-3090-workflow` / `p11b-h3-vram-and-longshot-pitfalls` | workflow API 提交模式可抄；VRAM 坑已文档化（TTS 服务器抢显存 → 先 kill + `/free`） |
| 升级位 | `/data/models/comfyui/LLM/Qwen-VL/Qwen3-VL-8B-Instruct` 已在盘上（原生视频输入） | v2 升级路线（vLLM serving），v1.3 不动 |
| 打分 | 无现成 —— 新增。CLIP/SigLIP 中段帧轨迹 + VLM judge（可用全局 glm-structured-output skill 做 schema 化输出） | Phase 21 spike 实测分布定阈值 |
| ear | v1.2 `audio_semantic`（dialogue/sfx/reproduction）已产出 | 不新引引擎，只融合进视觉 prompt |

**新增依赖（producer 侧）:** 仅 ComfyUI HTTP API 客户端（httpx，已有）+ 一个 CLIP/SigLIP 推理调用
（放 ComfyUI 侧或本地 torch，Phase 21 定）——延续「shot-timeline 零重 ML 依赖」约束的边界需在
Phase 18 契约讨论中明确（打分模型放哪是本 milestone 唯一的架构新决策）。

## 3. Features（table stakes vs differentiators）

**Table stakes（不做闭环就不成立）:**
- h3 fl2va 逐镜复现 + per-shot cache + 断点续跑（8-13h/集，不 cache 不可用）
- 中段帧相似度打分（首尾帧被 condition，无信息量）
- verdict + reason 写 `roundtrip.json`（schema 合法、graceful-degrade）
- VRAM guard（ComfyUI `/free` + 剩余显存检查 + TTS 共存检测）

**Differentiators（价值核心）:**
- **VLM judge 归因**（prompt 描述了X模型渲染了Y vs prompt 欠约束）——没有归因，数据集系统性偏向简单动作
- **rejected 保留**（hard negatives + h3 能力边界测绘）
- qwen-eye v2 帧序列问答升级 action/camera facet（独立于闭环就提升 prompts.json 质量）
- ear 融合（audio_semantic → 视觉 prompt 修正）
- accepted 子集独立 dataset 目录导出（可直接喂训练）

**Anti-features（明确不做）:** 全自动 accepted 无 HITL 复核；音频侧 round-trip 对比（h3 自带环境音
vs Demucs stems，白拿但 defer v1.4）；改 h3 引擎/workflow 本体；训练任何模型。

## 4. Architecture 集成点

- **新 step**：`step_roundtrip`（prompts 就绪后的验证 pass，slot 在 timeline/export 附近；精确 slot Phase 22 定）
- **新文件**：`analysis/roundtrip/`（regen 客户端 + scorer + verdict 合并）；`spec/schemas/roundtrip.schema.json`；
  `asset.json#data.roundtrip` optional；`output/<stem>/roundtrip/regen/`（重生成 mp4 per-shot）
- **cache**：mirror WR-04 4-tuple（video_content_hash + engine_name + engine_version + prompt_version）
- **graceful-degrade**：ComfyUI 不可达 / VRAM 不足 → roundtrip.json 缺省、资产照常导出、`[roundtrip]`
  warnings sidecar——mirror v1.1/v1.2 全部先例
- **消费者**：gallery HTML（本 repo）先行；canvas roundtrip 节点 defer

## 5. Pitfalls（已知的坑，phase 必须吸收）

1. **VRAM 竞争**（p11b Pitfall 6）：VoiceDesign :5111 (~4.4GB) + IndexTTS :5110 (~6.6GB) 与 ComfyUI 同卡；
   复现前必须 kill + `POST /free` + 验证 ~23GB free。qwen-eye 13.4GB lease 与 h3 同卡也互斥——**Phase 20
   必须做引擎串行编排**（eye 先跑完释放，再起 h3 批）。
2. **长镜超时**（p11b Pitfall 7）：15s/362帧 = 15-20min/镜，subagent 等待超时 → 直接 API 提交 + 轮询，
   不经 subagent；>10s 的镜可跳过或降分辨率（验证不需要全分辨率）。
3. **llama.cpp 单图 bug**：帧序列只能逐帧 `observe_single`——Phase 19 的合并策略（取信息量最大回答 vs
   时序拼接）需 spike 验证；Q3 27B 动作描述质量未验证 = Phase 19 首plan 应含 ep01 小样本校验。
4. **首尾帧必然相似**：任何包含 t=0/t=end 帧的打分都是自欺——打分器只看中段（25%-75% 时窗）。
5. **数据集偏差**：accepted 集天然偏向简单动作——归因字段 + rejected 保留是唯一缓解，验收标准必须
   含「rejected 占比被记录且可审计」。
6. **成本现实**：~100 镜/集全量轮 = 8-13h GPU 占用——首轮必须抽样（≤20 镜）校准阈值，全量跑是
   校准后的 overnight 批任务，不进交互路径。

## 6. 推荐结论

方案可行、基础设施 ~80% 就位、风险集中在三处（归因质量 / Q3 帧序列问答质量 / GPU 编排），
全部有既有 pattern 兜底。建议 5 phases（18-22）：契约先行 → eye v2 → h3 客户端 → scorer →
dataset+呈现，phase 间依赖单向，18/19 可并行规划。
