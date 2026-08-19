# Phase 20: h3 复现客户端 - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

kst 侧 ComfyUI 直连客户端把每镜 (首帧, 尾帧, prompt) 用 MiniMax H3 fl2va 复现成 regen mp4——per-shot 4-tuple cache + 断点续跑 + VRAM guard + 串行编排，让 8-13h/集 的批量渲染可管理、不撞 OOM（不经 kmc/hermes runtime，不经 subagent）。

Requirements: REGEN-01, REGEN-02, REGEN-03, REGEN-04。

**In scope:**
- `analysis/roundtrip/` ComfyUI API 客户端（fl2va workflow 模板 + 提交/轮询/产物回收）
- per-shot 4-tuple cache + 断点续跑 + `--force` 清单扩展
- VRAM guard（TTS kill + /free + <22GB 拒提交）+ eye 串行编排
- `--sample-shots` / `--max-shot-sec` / `--regen-resolution` 降载
- `[roundtrip]` warnings 通道接入（Phase 18 RT-04 契约的运行时兑现）

**NOT in scope:**
- 打分/verdict（Phase 21）、pipeline step 挂载与 dataset 导出（Phase 22）
- 改 h3 引擎/ComfyUI workflow 本体（只消费模板参数）
- ep01 全量 8-13h 渲染执行（本 phase 交付客户端 + smoke 验证；全量是 Phase 21 校准的前置 overnight 任务）

</domain>

<decisions>
## Implementation Decisions

### 客户端形态与提交协议
- `analysis/roundtrip/h3_regen.py` 单模块 + `analysis/roundtrip/workflow_fl2va.json` 模板（workflow JSON 是数据分开放）
- 模板 JSON 深拷贝 + 运行时改节点 inputs（首/尾帧 LoadImage、prompt 文本、length 17k+5 对齐、分辨率）——mirror kmc 模式
- **HTTP 轮询** ComfyUI `/history/{prompt_id}` + sleep 间隔（kmc v4 已验证 crash-safe 模式）；不用 websocket
- 产物回收走 ComfyUI `/view` API 下载 → `output/<video-stem>/roundtrip/shot_XXX_regen.mp4`（Phase 18 schema `regen.path` 相对 asset root 约定）

### cache 与断点续跑（REGEN-02）
- 元数据 `route_cache/h3_regen/shot_XXX.json`（4-tuple + prompt_id + 产物 sha）与 mp4 实体分离（cache 清了产物可独立校验）
- cache hit 判定：4-tuple 匹配 + mp4 存在 + size >1KB；**不做** ffprobe 深检（损坏由 Phase 21 scorer 自然暴露）
- prompt_version = **per-shot prompt hash**：sha256(该镜 prompt_text)[:8]——facet 级变化只重渲该镜
- `--force` 清理清单扩展：+ `route_cache/h3_regen/` + `roundtrip/` 产物目录（文档列明新增项）

### VRAM guard 与串行编排（REGEN-03）
- TTS **自动 kill**（VoiceDesign :5111 / IndexTTS :5110 监听进程）+ kill 前后各记一条 `[roundtrip]` warning（审计可查）
- nvidia-smi 直读 h3 所在 GPU（3090）free memory：**<22GB 拒提交** + `[roundtrip]` warning + exit 0（graceful-degrade）；批开始前 + **每镜提交前复查**
- eye 串行检测：**显存探测即编排信号**——提交前 GPU 已用 ≥13GB 视为 eye lease 在跑 → 不提交轮询等待（可配超时）；不做 KAP lease 主动查询/进程发现（显存是物理真相）
- `POST /free`：kill TTS 后 + 批开始前各一次；批中每镜之间不调

### 抽样、降载与 CLI（REGEN-04）
- `--sample-shots N`：**均匀间隔抽样**（全镜列表等距取 N，代表性覆盖头/中/尾）
- `--max-shot-sec`（默认 10）：>10s 长镜默认跳过 + `[roundtrip]` warning + skipped 清单文件可查
- `--regen-resolution`：降档 1344×768 → **896×512**（严格保持 7:4 比例；保 CLIP 比对信号）
- length 对齐：duration×24fps → **17k+5 最近合法值**（mirror kmc `h3_frame_count`：训练区间 124-362、步进 17；短镜保底 124）

### Claude's Discretion
- 轮询间隔/超时具体值、warning 文案、日志格式（mirror repo [stage] 前缀惯例）
- ComfyUI URL / GPU index 的 flag 默认值与探测顺序
- 首尾帧来源细节（frames 提取 or prompts.json 引用的帧路径——研究期确认）

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **kmc `h3_batch_render_v4.py`**（`/data/workspace/kais-hermes-skills/skills/kais-movie-pipeline/episodes/ep-shencongshenyuan-ep01/assets/P11/h3_batch_render_v4.py`，335 行）——submit/poll/download 全链路参考：COMFY :8188 直连、`/history/{prompt_id}` 轮询 + KAP status 兜底、`/view` 下载（fixed download 注释）、crash-safe polling
- **fl2va workflow 模板**（`/data/workspace/kais-hermes-skills/skills/kais-video/minimax-h3-ref2va-comfyui/SKILL.md`）——节点图 JSON：UNETLoader `minimax_h3_fl2va_pruned_int8_convrot.safetensors`、MiniMaxH3SigmaShift shift_video=12.0/shift_audio=3.0、1344×768、length 步进 17、训练区间 124-362
- **Phase 18 契约**（本 phase 的写入目标）——`spec/schemas/roundtrip.schema.json`：regen{path, video_content_hash, engine_name, engine_version, prompt_version}、status{state:"failed", error}、`[roundtrip]` warnings {code, detail} 三码 enum（comfyui_unreachable/vram_insufficient/scorer_model_missing）
- **p11b VRAM pitfalls**（research 已录）——TTS 共存检测 + /free + 剩余显存门槛 + 串行编排
- kst 侧 cache/降级/引擎生命周期惯例全套先例：local_vision_facets.py / vision_seq_facets.py（19-01/19-02 刚验证）

### Established Patterns
- 4-tuple cache（video_content_hash + engine_name + engine_version + prompt_version）mirror WR-04
- graceful-degrade：引擎不可达 → warning + exit 0，资产照常
- `[stage]` 前缀 print + banner + cache-hit skip 行 + 长循环 10 进度计数
- JSON indent=2 ensure_ascii=False + 原子写

### Integration Points
- `output/<video-stem>/roundtrip/shot_XXX_regen.mp4`（regen.path 产物）
- `route_cache/h3_regen/shot_XXX.json`（元数据）+ `route_cache/warnings.json`（[roundtrip] 条目 READ-merge-write）
- ComfyUI :8188 API（/prompt /history /view /free）+ nvidia-smi + TTS 端口探测
- Phase 21 scorer 消费 regen mp4；Phase 22 pipeline 挂载消费本客户端

</code_context>

<specifics>
## Specific Ideas

- SC1 明文 fl2va 参数：shift_video=12.0 / cfg=1.0 / euler+simple / length 17k+5 对齐——研究期从模板 JSON 逐节点核对
- SC3 research Pitfall 1：qwen-eye 13.4GB lease 与 h3 批同卡串行
- p11b Pitfall 7：不经 subagent（客户端直接 API 提交+轮询）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.（ep01 全量 overnight 渲染执行、scorer、pipeline 挂载均属后续 phase）

</deferred>
