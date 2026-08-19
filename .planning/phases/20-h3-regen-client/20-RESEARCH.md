# Phase 20: h3 复现客户端 - Research

**Researched:** 2026-08-20
**Domain:** ComfyUI 直连 HTTP 客户端（fl2va workflow 提交/轮询/回收）+ per-shot cache + GPU 编排
**Confidence:** HIGH（核心提交/回收链路已在真实 ComfyUI :8188 上逐端点实测；VRAM 批中行为为 MEDIUM——见 Pitfall 1）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions（照抄 20-CONTEXT.md ## Implementation Decisions）

- `analysis/roundtrip/h3_regen.py` 单模块 + `analysis/roundtrip/workflow_fl2va.json` 模板（workflow JSON 是数据分开放）
- 模板 JSON 深拷贝 + 运行时改节点 inputs（首/尾帧 LoadImage、prompt 文本、length 17k+5 对齐、分辨率）——mirror kmc 模式
- **HTTP 轮询** ComfyUI `/history/{prompt_id}` + sleep 间隔（kmc v4 已验证 crash-safe 模式）；不用 websocket
- 产物回收走 ComfyUI `/view` API 下载 → `output/<video-stem>/roundtrip/shot_XXX_regen.mp4`
- cache 元数据 `route_cache/h3_regen/shot_XXX.json`（4-tuple + prompt_id + 产物 sha）与 mp4 实体分离
- cache hit 判定：4-tuple 匹配 + mp4 存在 + size >1KB；**不做** ffprobe 深检
- prompt_version = per-shot prompt hash：sha256(该镜 prompt_text)[:8]
- `--force` 清理清单扩展：+ `route_cache/h3_regen/` + `roundtrip/` 产物目录
- TTS **自动 kill**（VoiceDesign :5111 / IndexTTS :5110 监听进程）+ kill 前后各记一条 `[roundtrip]` warning
- nvidia-smi 直读 h3 所在 GPU（3090）free memory：**<22GB 拒提交** + warning + exit 0（graceful-degrade）；批开始前 + 每镜提交前复查
- eye 串行检测：**显存探测即编排信号**——提交前 GPU 已用 ≥13GB 视为 eye lease 在跑 → 不提交轮询等待（可配超时）；不做 KAP lease 主动查询/进程发现
- `POST /free`：kill TTS 后 + 批开始前各一次；批中每镜之间不调
- `--sample-shots N`：均匀间隔抽样；`--max-shot-sec`（默认 10）>10s 跳过 + warning + skipped 清单；`--regen-resolution` 降档 1344×768 → **896×512**（严格 7:4）
- length 对齐：duration×24fps → 17k+5 最近合法值（训练区间 124-362、步进 17；短镜保底 124）

### Claude's Discretion

- 轮询间隔/超时具体值、warning 文案、日志格式（mirror repo [stage] 前缀惯例）
- ComfyUI URL / GPU index 的 flag 默认值与探测顺序
- 首尾帧来源细节（frames 提取 or prompts.json 引用的帧路径——研究期确认）

### Deferred Ideas (OUT OF SCOPE)

None — ep01 全量 overnight 渲染执行、scorer、pipeline 挂载均属后续 phase。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REGEN-01 | ComfyUI API 客户端：fl2va workflow 模板 + 提交/轮询/产物回收，不经 subagent | 提交/轮询/回收三端点已在真实 ComfyUI 实测（/upload/image→/prompt→/history→/view byte-identical 往返）；完整 fl2va 节点图已从 KAP i2va native builder + live history 双源核对（§Code Examples） |
| REGEN-02 | per-shot 4-tuple cache + 断点续跑 + --force 清单扩展 | repo 4-tuple cache 惯例（WR-04）先例齐备；run_pipeline --force 现有清单已核实（route_cache/ 整目录 rmtree 已天然覆盖 h3_regen/ 子目录，只需文档列明 + 客户端自身 --force） |
| REGEN-03 | VRAM guard（TTS 检测 + /free + <22GB 拒提交）+ eye 串行编排 | TTS 进程名/显存占用有 p11b validated 数据（4.4+6.6=11GB）；/free payload 实测 200；nvidia-smi 解析先例在本 repo qwen_eye_client.py；**批中复查的 ComfyUI 自身 cache 假阳性是已识别 Pitfall 1，须按 §Pitfall 1 方案实现** |
| REGEN-04 | --sample-shots / --regen-resolution / >10s 跳过 | ep01 实测数据：93 镜、3 镜 >10s、uniform-20 预演清单已算出（§ep01 数据盘点）；896×512 已验证 on-grid（%32==0、7:4 比例、面积远低于 MAX_PIXELS） |
</phase_requirements>

## Summary

本 phase 的核心链路（kst 直连 ComfyUI，不经 KAP/kmc/subagent）**已在真实运行的 ComfyUI :8188 上逐端点实测验证**：`POST /upload/image` 上传帧图 → 返回 `{name, subfolder, type}`；`POST /prompt` 提交 workflow JSON；`GET /history/{prompt_id}` 轮询（`status.status_str ∈ {success, error}` + `status.completed`）；`GET /view?filename=&type=output` 下载——155 字节探针文件上传/下载 **byte-identical**。fl2va 的确切节点拓扑有两个独立权威来源交叉验证：KAP `buildH3I2vaWorkflowNative`（源码精读）与 live history 里 3 个近期成功渲染的 prompt JSON（含 `MiniMaxH3ImageToVideo` 的 `first_frame`/`last_frame` optional 输入，object_info 现场确认）。

三个改变实现的实证发现：(1) **kmc v4 不是可照抄的提交协议**——它经 KAP HTTP API 提交、`docker cp` 下载（docstring 说 /view 但代码没有），且 `h3_frame_count` 算出的帧数**从未发给服务端**（multipart data 无 length 字段，全部按 defaultLength=124 渲染）；seed 用 `hash(sid)` 跨进程不确定。kst 客户端必须走 ComfyUI 原生 API 并真正下发 per-shot length。(2) **history 里视频产物在 `images` 键下**（本 0.30.0 build 的 SaveVideo 序列化为 `{filename: '...mp4', subfolder, type:'output'}` + `animated:[True]`），不在 `videos`/`gifs` 键。(3) **批中每镜 22GB 绝对值复查会自锁**——ComfyUI 渲完第一镜后自身 cache 驻留，free 会长期低于 22GB；必须按「nvidia-smi compute-apps PID 归因排除 ComfyUI 自身」实现复查（仍是显存物理真相，见 Pitfall 1）。

**Primary recommendation:** 模板用 §Code Examples 的 9 节点 native 链（KSampler 形态，euler+simple+cfg=1.0+shift_video=12.0），模型选 live 验证过的 `minimax_h3_fl2va_int8_convrot.safetensors`；上传用 subprocess curl（p11b validated，避免 requests 大文件 ConnectionResetError）；首尾帧**从 h264.mp4 全分辨率重新提取**（现有 shot_frames/ 是 480×270 缩略图，不可用）；全 stdlib 零新依赖。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| fl2va workflow 构造（per-shot 参数注入） | kst 客户端（analysis/roundtrip/） | — | 深拷贝模板+改 inputs 是纯本地数据变换 |
| 帧图上传到 ComfyUI input dir | ComfyUI HTTP API | curl 子进程 | `/upload/image` 是官方入口（实测 200 + byte-identical） |
| 渲染执行 + 模型加载 | ComfyUI 容器（comfyui-primary, GPU1 3090） | — | h3 int8 模型 ~20GB 只在容器侧存在 |
| 渲染状态/产物元数据 | ComfyUI `/history` | — | 唯一权威完成信号（KAP status 也只是转发它） |
| 产物下载落盘 | kst 客户端（`/view`） | — | CONTEXT 锁定 /view（实测可用；output dir 宿主路径 /mnt/agents/output/gpu1 亦可见但不必走文件系统） |
| GPU 仲裁（TTS kill / VRAM gate / eye 串行） | kst 客户端（批开始） | ComfyUI /free（驱逐自身 cache） | KAP 的 withGpuQueue 只管 KAP 自己的提交；kst 直连必须自带 guard |
| cache/断点续跑/warnings/roundtrip.json 写入 | kst 客户端 + route_cache/ sidecar | — | repo 既定文件系统状态模式（无 runtime 内存态） |
| 打分/verdict | Phase 21（**不建**） | — | schema 已留 degrade 中间态（regen 有、scores 无） |

## Standard Stack

### Core（全部已在本机存在，零新安装）

| 组件 | 版本 | 用途 | 为何标准 |
|---------|------|------|---------|
| Python stdlib（urllib.request / subprocess / json / hashlib / argparse） | 3.12 | 全部 HTTP/进程/序列化 | repo 惯例：qwen_eye_client.py 全 stdlib；无 lockfile 项目不引第三方 [VERIFIED: 代码库 grep] |
| curl（subprocess 调用，仅 /upload/image） | 8.5.0 | 帧图 multipart 上传 | p11b Pitfall 7 validated：Python requests 传大 PNG 会 ConnectionResetError，curl 不会 [CITED: p11b-h3-vram-and-longshot-pitfalls/SKILL.md L91-98] |
| ComfyUI HTTP API（/upload/image /prompt /history /view /free /system_stats /object_info） | 0.30.0 | 提交/轮询/回收/驱逐 | 实测全部可用（§Environment Availability）[VERIFIED: 本机 curl 实测] |
| nvidia-smi（query-gpu + query-compute-apps） | 驱动自带 | VRAM gate + eye/TTS 识别 | repo 先例 qwen_eye_client.py:_vram_free_mib；KAP gpuVramManager 同款 [VERIFIED: 代码库 grep] |
| pytest | 9.0.3 | 单测 | tests/ 目录 9 个测试文件既有 [VERIFIED: 本机 pytest --version] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| HTTP 轮询 /history | websocket /ws | CONTEXT 已锁不用 websocket；kmc/KAP/p11b 三方均轮询，crash-safe 已验证 |
| curl 子进程上传 | requests 2.34（本机已装） | requests 在大文件上有 ConnectionResetError 实锤（p11b）；且 repo 无 lockfile，引第三方依赖是方向性变化 |
| /view 下载 | docker cp（kmc v4 实际做法） | CONTEXT 锁 /view；/view 不依赖 docker 权限、路径稳定；docker cp 需猜容器内文件名 pattern（kmc 的 triple-pattern fallback 就是代价） |
| 经 KAP :10588 API 提交 | — | **明确排除**：STATE 决策 5 锁定「不经 kmc/hermes runtime」；且 p11b 警告 KAP T8 profile 依赖的节点组合与直连模板不同构 |

**Installation:** 无（零新包）。

## Package Legitimacy Audit

本 phase **不安装任何外部包**——全部功能由 Python stdlib + 系统已装的 curl/nvidia-smi/pytest 实现。slopcheck gate 不适用（无可审计包）。requests 2.34.0 虽在本机存在，但研究推荐**不使用**（见 Alternatives），无需 gate。

## Architecture Patterns

### System Architecture Diagram

```
                    kst h3_regen.py (analysis/roundtrip/)
                    ┌─────────────────────────────────────────────┐
                    │ 1. 载入 shots.json + prompts.json (ep01)     │
                    │ 2. --sample-shots 均匀抽样 / >10s 过滤        │
                    │ 3. cache 预判 (4-tuple: vch+engine+ver+pvh)  │──hit──> skip 该镜
                    │ 4. VRAM guard (批开始):                       │
                    │    a. TTS 端口探测 :5110/:5111               │
                    │       └─占用─> pkill voicedesign/indextts    │
                    │          + [roundtrip] warning ×2            │
                    │    b. POST /free (unload_models+free_memory) │
                    │    c. nvidia-smi -i 1 free <22GB? ──否──> warning + exit 0
                    │    d. used ≥13GB ⇒ eye lease ──> 轮询等待    │
                    │ 5. per-shot:                                  │
                    │    ffmpeg 提取首/尾帧 (全分辨率, from h264.mp4)│
                    │    curl POST /upload/image ──> input filename │
                    │    深拷贝 workflow_fl2va.json + 改 inputs      │
                    │    (14/15 LoadImage, 20 prompt/w/h/length,    │
                    │     21 shift, 30 seed/steps, 50 prefix)       │
                    │    POST /prompt ──> prompt_id                 │
                    │    loop: GET /history/{prompt_id} (sleep 15s) │
                    │      ├─ status_str=success ──> outputs 找     │
                    │      │   'images' 键 {filename,type=output}   │
                    │      │   GET /view ──> roundtrip/shot_XXX_regen.mp4 │
                    │      │   写 route_cache/h3_regen/shot_XXX.json │
                    │      ├─ status_str=error ──> 记 status{failed} │
                    │      └─ 超时 ──> 记 failed, 继续下一镜          │
                    │    per-shot VRAM 复查 (PID 归因, 见 Pitfall 1) │
                    │ 6. 收尾: roundtrip.json (regen 半边, READ-merge)│
                    │    + route_cache/warnings.json merge          │
                    └─────────────────────────────────────────────┘
     │                                    │
     ▼ (HTTP 127.0.0.1:8188)              ▼ (subprocess)
┌──────────────────┐              ┌───────────────┐
│ ComfyUI 0.30.0   │              │ nvidia-smi    │
│ comfyui-primary  │              │ GPU1=3090     │
│ NVIDIA_VISIBLE_  │              │ GPU0=3060Ti   │
│ DEVICES=1 (3090) │              └───────────────┘
│ --lowvram        │
└──────────────────┘
   外部邻居: TTS :5110/:5111 (VoiceDesign 4.4GB + IndexTTS 6.6GB, P10 后驻留)
            qwen-eye lease (llama-server, 13.4GB)
            music3 常驻 676MiB (cpu-offloaded, 当前实况)
```

### Recommended Project Structure

```
analysis/roundtrip/
├── h3_regen.py               # 单模块客户端（argparse + main()，mirror repo 惯例）
├── workflow_fl2va.json       # 模板数据（9 节点 native 链，与代码分离）
└── __init__.py               # 不需要——repo 无包结构，脚本按路径调用
output/<video-stem>/
├── roundtrip/                # 产物目录（regen.path 相对 asset root = roundtrip/shot_XXX_regen.mp4）
├── roundtrip.json            # Phase 18 契约 sidecar（本 phase 写 regen 半边）
└── route_cache/
    ├── h3_regen/shot_XXX.json  # 4-tuple + prompt_id + 产物 sha + seed/length/分辨率
    └── warnings.json           # [roundtrip] {code, detail} 条目 READ-merge-write
tests/
└── test_h3_regen.py          # FakeComfyUI monkeypatch（mirror test_qwen_eye_client.py）
```

### Pattern 1: 模板深拷贝 + 节点 inputs 注入（CONTEXT 锁定的 kmc 模式，但按 KAP native 拓扑修正）

**What:** workflow JSON 是纯数据文件；运行时 `json.load` → `copy.deepcopy` → 按 node id 改 `inputs` → `{"prompt": wf}` POST。
**When to use:** 每镜提交前。
**Example:** 见 §Code Examples 完整模板。

### Pattern 2: cache 元数据与产物分离 + 4-tuple 判定

**What:** `route_cache/h3_regen/shot_XXX.json` 存 `{video_content_hash, engine_name, engine_version, prompt_version, prompt_id, seed, length, width, height, mp4_sha256}`；hit = 4-tuple 全匹配 + `../roundtrip/shot_XXX_regen.mp4` 存在且 >1KB。
**When to use:** 每镜提交前预判（mirror vision_seq 的「全 cache 命中时引擎从未实例化」）。
**Note:** `video_content_hash` 复用 `analysis/call_shot_analysis.py:video_content_hash` 同款算法（sha256(首1MB+尾1MB+str(filesize))[:16]）——schema `pattern ^[0-9a-f]{16}$` 与 ep01 实测值 `ece64d62bcbc534a` 已核对。[VERIFIED: 代码库 grep + 实算]

### Pattern 3: warnings READ-merge-write（双形保留）

**What:** 读 `route_cache/warnings.json` 现有 list → 追加本 step 新条目 → 原子写回。**本 step 的条目是结构化 `{code, detail}`**（RT-04 v1.3 加宽形），code ∈ closed enum {comfyui_unreachable, vram_insufficient, scorer_model_missing}（scorer_model_missing 是 Phase 21 的码，本 phase 不产生）。merge helper 必须同时保留 str（legacy）与 dict（新）两种元素——**不可照抄 vision_seq 的 `_read_existing_warnings`**（它 `isinstance(w, str)` 过滤会把 dict 条目丢掉，见 Pitfall 6）。strip 逻辑按「code+detail 前缀标记」识别本 step 上一轮条目防重复。[VERIFIED: vision_seq_facets.py:214-224 + export_asset.py:70-81 双向核对]

### Anti-Patterns to Avoid

- **照抄 kmc v4 的提交协议**：它 POST KAP multipart API、`docker cp` 下载、不发 length、seed 不确定——四个偏差都会在 kst 语境下变成 bug（见 Pitfall 2）。
- **猜产物文件名 pattern**（`{prefix}_00001_.mp4` triple-try）：history 的 outputs 条目里有**确切 filename**，直接用。
- **用 `hash()` 派生 seed**：Python 字符串 hash 每进程随机化（PYTHONHASHSEED），跨跑不可复现。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 帧数对齐 | 自创 rounding | `while n % 17 != 5: n += 1` + floor 124 + cap 362 | object_info tooltip + KAP alignH3FrameCount 双源一致；「最近合法值」即 ceil-on-grid [VERIFIED] |
| 分辨率合法性 | 手算 aspect | %32==0 校验 + MAX_PIXELS 预算 | CANVAS_MULTIPLE=32, MAX_PIXELS=1032192（1344×768）；token 预算 width×height×length ≤300M 安全线（>340M 实测双后端崩溃）[CITED: KAP config.ts H3_CONSTANTS/H3_TOKEN_FRONTIER] |
| 渲染完成判定 | 解析 ComfyUI 日志 | `/history/{pid}` 的 `status.status_str/completed` | kmc/KAP/p11b 三方一致 + live history 实测 [VERIFIED] |
| 引擎可达性 | ping 端口 | `GET /system_stats`（200 = 活） | 实测返回完整设备信息 [VERIFIED] |
| 显存读数 | 解析 `nvidia-smi` 全文 | `--query-gpu=memory.free --format=csv,noheader,nounits -i 1` | repo qwen_eye_client.py 同款先例 [VERIFIED] |

**Key insight:** 本 phase 的「复杂度预算」应全部花在 VRAM 编排与 cache 语义上；提交/轮询/回收是已被三方（kmc/KAP/p11b）验证过的简单 HTTP 模式，不要发明新协议。

## Common Pitfalls

### Pitfall 1（本 phase 最大实现风险）: 批中每镜 22GB 绝对值复查会自锁
**What goes wrong:** CONTEXT 锁定「批开始前 + 每镜提交前复查 <22GB 拒提交」「批中每镜之间不调 /free」。但 ComfyUI 渲完第一镜后**自身模型 cache 驻留显存**（int8 模型 ~20GB，--lowvram 下权重部分 offload 但不 eager 清空；只有 /free 或新模型挤占才释放）。第 2 镜提交前 nvidia-smi free 很可能 <22GB → 客户端把自己渲染的 cache 误判为「显存不足」，批在第 2 镜就 graceful-exit。同理「GPU 已用 ≥13GB ⇒ eye 在跑」会把 h3 自身 cache 误判为 eye lease。
**Why it happens:** 绝对值 free 分不清「可驱逐（ComfyUI cache，下一镜本来就要复用）」与「常驻不可驱逐（TTS/eye）」。KAP gpuVramManager 源码对此有整段注释：「ensureVram 只看 nvidia-smi free，分不清『可驱逐』与『常驻不可驱逐』」并引入 effectiveFree = free + Σ evictable-resident。[VERIFIED: gpuVramManager.ts L173-178]
**How to avoid（推荐实现，仍满足「显存探测即编排信号」锁定决策）:**
- **批开始 gate（严格）**：kill TTS + /free 之后复查，free <22528 MiB ⇒ 拒绝整批（此刻没有自身 cache 干扰，22GB 语义成立——今天实测 kill 后 ~22.5GB，刚好过线）。
- **每镜 gate（PID 归因）**：`nvidia-smi --query-compute-apps=pid,used_memory -i 1`，**排除 ComfyUI 容器进程 PID**（提交前 `GET /system_stats` 不可得 PID；用 docker inspect 或首次渲染后记录基线），foreign-used（TTS/eye/music3 等）>阈值 ⇒ 等待/记 warning。这是「更物理的真相」——仍是 nvidia-smi 直读，只是归因到进程。
- 备选（更简单）：每镜 gate 改为「free 相对上一镜完成后基线的**下降量** >2GB ⇒ 有新占用者」。缺点是首镜无基线。
- eye-串行（≥13GB）判定**只在批开始**做绝对值检查（此刻无自身 cache）；批中 eye 检测走 PID 归因。
**Warning signs:** smoke 时第 2 镜被 vram_insufficient 拒绝、或批中日志出现「等待 eye 释放」但 nvidia-smi compute-apps 里只有 ComfyUI 自己。

### Pitfall 2: kmc v4 参考代码的四个不可照抄点
**What goes wrong:** 把 `h3_batch_render_v4.py` 当提交协议模板。
**Why:** (a) 它 POST 的是 `KAP /api/production/minimax-h3/i2va`（multipart + docker cp 进容器），**不是** ComfyUI 原生 /prompt——kst 必须不经 KAP；(b) docstring 说 "fixed download (ComfyUI /view API)" 但代码实际 `docker cp` 三 pattern 猜文件名——/view 路径 kst 要自己实现（已实测可行）；(c) `h3_frame_count()` 算出的帧数只进了日志，multipart data **没有 length 字段**，全部按 KAP defaultLength=124 渲染；(d) seed = `50000 + abs(hash(sid)) % 9999`，`hash()` 跨进程随机。[VERIFIED: 逐行精读 L111-169, L215-268 + KAP i2va.ts L490-491]
**How to avoid:** 可照抄的只有：轮询 crash-safe 骨架（poll 异常 continue、data=None 兜底直查 ComfyUI history、60s 节流日志）、`size>1000` 产物有效性下限、批循环 sleep 节奏。提交/下载/参数下发按本研究的 Code Examples。
**Warning signs:** 客户端代码里出现 KAP URL、docker 命令、或 hash() 派生 seed。

### Pitfall 3: 视频产物在 history 的 `images` 键下（不是 `videos`/`gifs`）
**What goes wrong:** 轮询完成后在 outputs 里找 `gifs`（旧 ComfyUI SaveAnimatedWEBP 惯例）或 `videos`（直觉命名）→ 找不到 → 误判失败。
**Why:** 本 0.30.0 build 的 SaveVideo 把 SavedResult 序列化进 `images` 键（live history 实测：`'images': [{filename: 'S01_B02_h3_00004_.mp4', subfolder: '', type: 'output'}]` + `animated: [True]`）。[VERIFIED: live /history 实测 67 条目枚举]
**How to avoid:** 解析时遍历 outputs 所有 node 的 `images`（兼容 `gifs`/`videos`）列表，取 `type=='output'` 且 filename 以 `.mp4` 结尾的条目，用其**确切 filename** 调 /view。
**Warning signs:** 下载 404 / 空 outputs。

### Pitfall 4: 首尾帧分辨率不足（480×270 缩略图不可用）
**What goes wrong:** 复用现成 `output/<ep01>/shot_frames/shot_XXX_first.jpg`（480×270）做 1344×768 渲染的条件帧 → 上采样糊 + 比对信号失真。
**Why:** shot_frames 是 HTML 时间轴缩略图（repo ffmpeg 模式带 `scale=480:-1`）。源是 1920×1080。[VERIFIED: PIL 实测尺寸 + ffprobe]
**How to avoid:** 客户端自己从 `h264.mp4` 提取：`ffmpeg -ss <start_sec> -i h264.mp4 -frames:v 1 -q:v 2`（**不带 scale**），首帧= start_sec、尾帧= end_sec−(1/24 or 0.04s) 前移防越界。1920×1080 16:9 → adaptH3Canvas → 恰为 1344×768（已实算验证）。上传文件名用确定性前缀（如 `kst_<vch8>_shot042_ff.jpg`）+ `overwrite=true`，防 input 目录无限膨胀（现已 349 个 KAP uuid 文件）。
**Warning signs:** regen 视频首尾帧糊/构图偏。

### Pitfall 5: 上传用 requests 会 ConnectionResetError；GET /upload/image 是 404
**What goes wrong:** (a) Python requests 传大图偶发 ConnectionResetError（p11b 实锤）；(b) 探测端点时 GET /upload/image 返回 404，误以为端点不存在。
**Why:** (a) p11b Pitfall 7 修复方案明确要求 curl；(b) 该路由只注册 POST。[VERIFIED: 实测 GET 404 / POST 200]
**How to avoid:** 上传走 `subprocess.run(["curl", "-s", "-X", "POST", url, "-F", f"image=@{path}", "-F", "type=input", "-F", "overwrite=true"])`；JSON 类请求用 stdlib urllib（mirror qwen_eye_client._http_json）。

### Pitfall 6: vision_seq 的 warnings strip 会丢 {code, detail} dict 条目
**What goes wrong:** h3_regen 写入结构化 warning 后，若 vision_seq 重跑（--force 或单独重烧），其 `_read_existing_warnings` 只保留 str 元素 → roundtrip dict 条目被静默清除。
**Why:** `vision_seq_facets.py:223`：`[w for w in data["warnings"] if isinstance(w, str)]`。[VERIFIED: 代码 grep]
**How to avoid:** h3_regen 自己的 merge helper 保留双形（str+dict）；本 phase 不改 vision_seq（scope 外），但在 h3_regen docstring 记录该交互。若 planner 想加一行修复（vision_seq 过滤改为「str 或 dict 都保留」）属低风险加分项，非必须。
**Warning signs:** warnings.json 里 [roundtrip] 条目在重跑其它 step 后消失。

### Pitfall 7: 调度器参数名歧义——euler+simple 是 KAP native 默认，但 live 渲染用的是 res_multistep+normal
**What goes wrong:** 从 live history「抄作业」会抄到 res_multistep/normal/36steps（KAP 某 profile 配置）；从 ref2va SKILL.md 抄会抄到 euler/**normal**；三处不一致。
**Why:** KAP config `H3_NATIVE = {t2vSamplerName: "euler", t2vScheduler: "simple"}`（L79-80）是 CONTEXT SC1 锁定的组合；SKILL.md 例程 scheduler 写 normal；live history 三条近期渲染是 res_multistep+normal+36steps。[VERIFIED: 三源交叉]
**How to avoid:** 按 CONTEXT 锁定值 euler+simple（KAP native 默认，配置在案可运行）；steps=15（kmc/T8 默认，8-13h/集预算的前提）。把 sampler/scheduler/steps 全部冻结进 `engine_version` 字符串与 cache，改任一参数即 cache 失效。
**Warning signs:** 渲染时长显著偏离预估（36steps 约慢 2.4 倍）。

### Pitfall 8: 单镜超时 900s 不够长镜
**What goes wrong:** kmc max_wait=900s；p11b 实测 15s/362f 要 15-20 分钟 → 长镜必超时误判。
**How to avoid:** 超时按帧数缩放（如 `900 + length*3` 秒，或直接 2400s 默认 + `--shot-timeout` flag）。默认 >10s 跳过后最长 243f（10s 镜）≈ 13-15 分钟 @15steps，900s 边缘。[CITED: p11b Pitfall 7 实测时长]

### Pitfall 9: music3 常驻 676MiB 与 22GB 阈值的余量极小
**What goes wrong:** 批开始 gate 期望 ~23.6GB free，但当前 GPU1 实况：ComfyUI idle 692MiB + music3 常驻 676MiB（cpu-offloaded，不可驱逐——KAP 表里标注 evictable=false）+ 桌面开销 → 实测 free **22539MiB，距 22528 阈值仅 11MiB**。任何小占用都可能让整批拒提交（行为上合法——graceful-degrade——但会造成「为什么今天跑不了」的困惑）。[VERIFIED: nvidia-smi 实测]
**How to avoid:** 阈值 22GB 保持 CONTEXT 锁定，但 warning detail 里写明当前 free 与 top 占用者 PID/进程名，让 operator 一眼看出是谁占了；文档记 music3 常驻属正常态（676MiB 不至于挡门——22.5GB 仍过线）。

## Code Examples

### 完整 fl2va workflow 模板（kst 版——9 节点 native KSampler 链）

来源合成：KAP `buildH3I2vaWorkflowNative`（i2va.ts L244-388，节点 10-50 拓扑）+ p11b 直接提交模板（templates/h3_ref2va_workflow.py 的 KSampler 形态）+ object_info 实测输入名。**比 KAP native 少 3 个节点**：不用 Advanced 链（KSamplerSelect/BasicScheduler/RandomNoise/BasicGuider/SamplerCustomAdvanced 五件套 ≡ KSampler，KAP 源码注释明证数学等价）；不用 TESpeed/ExtendIntermediateSigmas（kmc 调参基线没有它们）；不建 node 16 负面 conditioning（cfg=1.0 下 negative=positive 即可，SKILL.md 方案 A）。

```json
{
  "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax"}},
  "11": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
  "12": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_int8_convrot.safetensors", "weight_dtype": "default"}},
  "13": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
  "14": {"class_type": "LoadImage", "inputs": {"image": "<FF_FILENAME>"}},
  "15": {"class_type": "LoadImage", "inputs": {"image": "<LF_FILENAME>"}},
  "20": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
      "clip": ["10", 0], "vae": ["11", 0],
      "prompt": "<PROMPT_TEXT>",
      "width": 1344, "height": 768, "length": 124,
      "first_frame": ["14", 0], "last_frame": ["15", 0]}},
  "21": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["12", 0], "shift_video": 12.0, "shift_audio": 3.0}},
  "30": {"class_type": "KSampler", "inputs": {
      "model": ["21", 0], "positive": ["20", 0], "negative": ["20", 0], "latent_image": ["20", 1],
      "seed": 42, "steps": 15, "cfg": 1.0,
      "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
  "40": {"class_type": "VAEDecode", "inputs": {"samples": ["30", 0], "vae": ["11", 0]}},
  "41": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["30", 0], "vae": ["13", 0]}},
  "42": {"class_type": "CreateVideo", "inputs": {"images": ["40", 0], "fps": 24, "audio": ["41", 0]}},
  "50": {"class_type": "SaveVideo", "inputs": {"video": ["42", 0], "filename_prefix": "<PREFIX>", "format": "mp4", "codec": "auto"}}
}
```

运行时注入点（deepcopy 后改）：
| 节点 | 字段 | 来源 |
|------|------|------|
| 14/15 | `inputs.image` | /upload/image 返回的 name（确定性名 `kst_<vch8>_shot<NNN>_ff/lf.jpg`） |
| 20 | `inputs.prompt` | prompts.json 该镜 `prompt_text`（ep01 覆盖率 93/93）[VERIFIED] |
| 20 | `inputs.width/height` | 默认 1344×768；`--regen-resolution 896x512`（两值均 %32==0、7:4、458752 px² ≪ MAX_PIXELS）[VERIFIED] |
| 20 | `inputs.length` | `max(124, min(ceil17k5(duration×24), 362))` |
| 30 | `inputs.seed` | **确定性派生**：`int(sha256(f"{vch}:{shot_id}")[:8], 16) % 2**31`（可复现，进 cache 元数据） |
| 50 | `inputs.filename_prefix` | `kst_<vch8>_shot<NNN>`（产物名从 history 拿，prefix 只需可识别） |

[VERIFIED: KAP i2va.ts 源码 + live history 三条成功渲染 + object_info MiniMaxH3ImageToVideo/SigmaShift/SaveVideo 输入实测。模型文件名 `minimax_h3_fl2va_int8_convrot.safetensors` 在容器 diffusion_models/ 实际存在且为 live 渲染所用；SKILL.md 写的 `_pruned_` 变体也在盘但为 ref2va 语境。]

### 提交 + 轮询 + 下载骨架（kmc crash-safe 模式 × ComfyUI 原生 API）

```python
# Source: kmc h3_batch_render_v4.py poll 骨架 + p11b Pitfall 7 直连模式（均本地验证）
def submit(wf: dict) -> str:
    payload = json.dumps({"prompt": wf}).encode()
    req = urllib.request.Request(f"{COMFY}/prompt", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    if "prompt_id" in result:
        return result["prompt_id"]
    # validation error: result["node_errors"] 按 node 展开（h3_ref2va_workflow.py:submit_workflow 同款）

def poll_and_fetch(prompt_id: str, timeout_s: int) -> dict | None:
    start = time.time()
    while time.time() - start < timeout_s:
        time.sleep(15)
        try:
            with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}", timeout=10) as r:
                hist = json.loads(r.read())
        except Exception:
            continue                       # 瞬态错误继续轮（kmc crash-safe）
        entry = hist.get(prompt_id)
        if not entry:
            continue
        st = entry.get("status", {})
        if st.get("status_str") == "error":
            return {"ok": False, "error": str(st.get("messages"))[:2000]}
        if st.get("completed"):
            for nid, out in (entry.get("outputs") or {}).items():
                for key in ("images", "gifs", "videos"):        # Pitfall 3: 本build在 images
                    for item in out.get(key) or []:
                        if item.get("type") == "output" and item.get("filename", "").endswith(".mp4"):
                            return {"ok": True, **item}          # filename/subfolder 确切值
    return None                                                  # 超时

def download(item: dict, dest: str):
    q = urllib.parse.urlencode({"filename": item["filename"],
                                "subfolder": item.get("subfolder", ""),
                                "type": "output"})
    with urllib.request.urlopen(f"{COMFY}/view?{q}", timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())       # 实测 byte-identical（155B 探针）；~10-50MB mp4 同路径
```

### VRAM guard（批开始严格 + 每镜 PID 归因——Pitfall 1 方案）

```python
# Source: qwen_eye_client.py:_vram_free_mib 同款 nvidia-smi 调用 + gpuVramManager /free payload
VRAM_GPU_INDEX = 1          # RTX 3090（comfyui-primary NVIDIA_VISIBLE_DEVICES=1 实证）
BATCH_MIN_FREE_MIB = 22528  # 22GB（CONTEXT 锁定）
EYE_LEASE_MIB = 13721       # 13.4GB（qwen_eye_client 注释实证）

def free_mib() -> int | None:        # fail-open：None 不阻塞（qwen 先例）
    p = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits", "-i", str(VRAM_GPU_INDEX)],
                       capture_output=True, text=True, timeout=10)
    return int(p.stdout.strip().splitlines()[0])

def compute_apps() -> list[tuple[int, int]]:   # [(pid, used_mib)]，GPU1
    p = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                        "--format=csv,noheader,nounits", "-i", str(VRAM_GPU_INDEX)],
                       capture_output=True, text=True, timeout=10)
    out = []
    for line in p.stdout.strip().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) >= 2 and cols[0].isdigit():
            out.append((int(cols[0]), int(cols[1].replace("MiB", "") or 0)))
    return out

def kill_tts() -> list[str]:        # p11b validated 进程名；kai 自己的进程无需 sudo
    killed = []
    for pat in ("voicedesign_server.py", "indextts25-server.py"):
        r = subprocess.run(["pkill", "-f", pat], capture_output=True)
        if r.returncode == 0:
            killed.append(pat)
    return killed

def comfy_free():                   # KAP gpuVramManager 同款 payload（实测 200）
    req = urllib.request.Request(f"{COMFY}/free",
        data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=5)
```

### warnings 追加（双形保留 merge）

```python
# Source: vision_seq_facets.py:214 改造——保留 str+dict 双形（Pitfall 6）
def append_roundtrip_warnings(sidecar: str, new_entries: list[dict]):
    try:
        data = json.load(open(sidecar, encoding="utf-8"))
        existing = data.get("warnings", [])
    except (OSError, json.JSONDecodeError):
        existing = []
    existing = [w for w in existing
                if not (isinstance(w, dict) and w.get("code") in _ROUNDTRIP_CODES)]  # strip 上一轮
    merged = existing + new_entries          # [roundtrip] 条目 = {"code": ..., "detail": ...}
    atomic_write(sidecar, {"warnings": merged})   # indent=2 ensure_ascii=False（repo 惯例）
```

## ep01 数据盘点（实测）

| 指标 | 值 | 来源 |
|------|-----|------|
| 总镜数 | 93 | shots.json [VERIFIED] |
| >10s 长镜 | 3（max 19.7s） | 实算 |
| duration 分布 | min 0.5 / median 2.3 / max 19.7 | 实算 |
| prompt_text 覆盖率 | 93/93（字段存在即 regen prompt 源） | 实算 |
| video_content_hash | `ece64d62bcbc534a`（h264.mp4, 172686591B） | 实算（call_shot_analysis 同款算法） |
| 源视频 | 1920×1080 @30fps → adaptH3Canvas → 1344×768 | ffprobe + 实算 |
| uniform-20 抽样预演 | ids [1,5,10,14,19,24,28,33,38,42,47,52,56,61,66,70,75,80,84,89]；其中 **shot 70 (19.7s) 会被 >10s 规则跳过 → 实渲 19 镜**；frame counts: 175/175/124×12/158/175/124/124（总 2543f） | 实算 |
| 19 镜 smoke 时长估算 | ~2.5-3h @15steps/1344×768（SKILL.md: 15步 95f≈8min, 141f≈13min） | [ASSUMED]（外推） |
| 全量（90 可渲镜）估算 | ~12-14h —— 与 goal 的 8-13h/集 一致量级 | [ASSUMED]（外推） |

设计注意：抽样在 >10s 过滤**之前**做（对全镜列表等距抽样），shot 70 落样后跳过并记 warning + skipped 清单——这保证抽样代表性不被过滤顺序扭曲，且 SC1 的「--sample-shots 20」语义直观。若 planner 想要「实渲恰好 20」，可等距抽 21 个容忍 1 个跳过——推荐前者（简单、可解释）。

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| kmc v4 经 KAP API 提交 + docker cp 下载 | kst 直连 ComfyUI /prompt + /view | 本 phase（STATE 决策 5） | 摆脱 kmc/hermes runtime 与 KAP 队列耦合 |
| subagent 逐镜提交（p11b Pitfall 7 崩溃源） | 客户端进程内 HTTP 轮询 | p11b 2026-08-13 validated | 长镜不再因 subagent 超时崩批 |
| ComfyUI legacy `gifs` 输出键 | 0.30.0 SaveVideo → `images` 键 + `animated` 标志 | 本 build 实测 | 下载解析按 filename 精确取 |
| KSampler 逐节点链 | KAP native Advanced 链（数学等价） | 2026-08-16 KAP | kst 二选一皆可；推荐 KSampler 形态（少 4 节点） |

**Deprecated/outdated:** kmc v4 的「/view 下载」docstring（代码实际 docker cp）；`hash(sid)` seed 派生；`minimax_h3_fl2va_pruned_*` 在 ref2va SKILL.md 的引用（fl2va live 证据是 int8_convrot 非 pruned 变体）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 渲完一镜后 ComfyUI cache 驻留会使 free <22GB（Pitfall 1 根因） | Pitfalls | 若 --lowvram 实际 eager offload，每镜绝对复查也可行——但 PID 归因方案两头都安全，风险仅剩「多实现了归因逻辑」 |
| A2 | steps=15 在 euler+simple 下质量可用于 round-trip 校准 | Code Examples | 质量/时长权衡错→校准数据噪音大；p11b/kmc 均用 15，风险低 |
| A3 | smoke/全量时长估算（8min/124f 线性外推） | ep01 盘点 | 预算偏差；sample-shots 模式本就为控制预算设计 |
| A4 | euler+simple 组合未在本 server 逐字面提交过（KAP native 默认值在案、live 用的是 res_multistep） | Pitfall 7 | 极低——参数是 object_info 合法值且 KAP 默认；smoke 首镜即验证 |
| A5 | TTS 进程名 voicedesign_server.py / indextts25-server.py 仍准确 | VRAM guard | pkill 落空 → 端口探测兜底（ss/lsof :5110/:5111 → PID）；guard 是 best-effort 语义 |
| A6 | shot 70 跳过后 19 镜是 SC1 的正确解读 | ep01 盘点 | 若 Kai 要「恰好 20」需抽 21——plan 阶段一句话决策 |

**其余关键断言均 [VERIFIED]（本机实测/源码精读）或 [CITED]（p11b/KAP/SKILL 文档）——不需要用户确认。**

## Open Questions（3/3 RESOLVED —— plan 期已裁决，指针见各条）

1. **每镜 VRAM 复查的实现口径**（Pitfall 1 的三个方案：PID 归因 / 基线 delta / 维持绝对值）——(RESOLVED → 20-02 Task 1)
   - What we know: 绝对值复查在自身 cache 驻留下大概率自锁；PID 归因最稳。
   - What's unclear: --lowvram 下渲后驻留的真实水位（需首镜实测）。
   - Recommendation: 按 PID 归因实现 + smoke（--sample-shots 2）时顺带记录渲后 free 水位进 cache 元数据，为后续调参留数据。
   - **Resolution: 20-02 Task 1 按 PID 归因实现（compute-apps 差集 + 基线 ∪ comfyui-primary 容器主 PID，foreign Σused ≥4096MiB 才等待/终止）；渲后水位以 post_render_free_mib 字段留档进 cache 元数据。**
2. **roundtrip.json 的写入归属**：schema 描述 producer 为 "Phase 20/21"。——(RESOLVED → 20-03 Task 1)
   - Recommendation: 本 phase 客户端批末写 regen 半边（shots[]{shot_id, regen} ∪ status{failed}，scores/verdict 缺席——schema 明文合法 degrade 中间态），READ-merge 已有条目（Phase 21 增量补 scores/verdict 时同模式）。这满足 SC1「Phase 18 契约是客户端的写入目标」且不给 Phase 21 留全量重写负担。
   - **Resolution: 20-03 Task 1 write_roundtrip_sidecar——客户端批末写 regen 半边，READ-merge 保留 Phase 21 scores/verdict 字段，Draft202012Validator 写前自校验。**
3. **engine_version 字符串构成**（4-tuple 之一，影响 cache 失效粒度）——(RESOLVED → 20-01 Task 1)
   - Recommendation: `"comfyui-0.30.0_fl2va-int8-convrot_euler-simple-15"`（把影响产物的参数冻进版本串：模型+sampler+scheduler+steps；分辨率/length/seed 不进——它们已按镜存 cache 元数据，且 --regen-resolution 切换时应整体重渲，可把分辨率并入 engine_version 或作为 cache 第 5 维，planner 定；推荐并入 engine_version，简单且语义即「换了渲染配置」）。
   - **Resolution: 20-01 Task 1 冻结 ENGINE_VERSION_TEMPLATE="fl2va-int8/euler+simple/15/{width}x{height}"——model+sampler+scheduler+steps+resolution 全进版本串，cache 保持 4-tuple 不设第 5 维（--regen-resolution 切换即整体失效，20-02 Task 2 接入）。**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| ComfyUI :8188 | REGEN-01 提交/轮询/回收 | ✓ | 0.30.0（pytorch 2.11.0+cu130） | comfyui_unreachable warning + exit 0 |
| comfyui-primary 容器 | 模型/执行宿主 | ✓ | Up 2 days, GPU1（NVIDIA_VISIBLE_DEVICES=1） | — |
| fl2va 模型 | REGEN-01 | ✓ | `minimax_h3_fl2va_int8_convrot.safetensors` + `_pruned_` 变体均在 diffusion_models/ | — |
| CLIP/VAE 模型 | REGEN-01 | ✓ | qwen3vl_32b_nvfp4_awq / video_vae_fp16 / audio_vae_fp32 均在 | — |
| GPU1 3090 | REGEN-03 | ✓ | 24576 MiB，当前 free 22539（music3 常驻 676 + ComfyUI idle 692） | vram_insufficient warning + exit 0 |
| nvidia-smi | REGEN-03 | ✓ | query-gpu + query-compute-apps 实测可用 | fail-open（qwen 先例） |
| TTS :5110/:5111 | REGEN-03 kill 对象 | ✗ 当前未监听（无 kill 对象，guard 空转合法） | — | 端口探测→pkill；落空则记 warning 继续 |
| ffmpeg/ffprobe | 首尾帧提取 + regen duration_sec | ✓ | 系统 PATH（repo 既有依赖） | — |
| curl | /upload/image multipart | ✓ | 8.5.0 | urllib 手写 multipart（不推荐） |
| pytest | Validation | ✓ | 9.0.3 | — |
| KAP :10588 | （不需要） | ✓ 在跑 | — | 明确不用（STATE 决策 5） |

**Missing dependencies with no fallback:** 无。
**Missing dependencies with fallback:** TTS 服务未运行——kill 步骤设计为 no-op 安全（探测不到监听即跳过，仍记 warning 说明检查已执行）。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3（无配置文件——repo 惯例裸 pytest） |
| Config file | none（tests/ 平铺，mirror 既有 9 个 test_*.py） |
| Quick run command | `python3 -m pytest tests/test_h3_regen.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REGEN-01 | workflow 注入：deepcopy 模板后 14/15 image 名、20 prompt/w/h/length、30 seed/steps、50 prefix 全部落位；length ∈ {n: n%17==5} ∪ floor124 ∪ cap362 | unit | `python3 -m pytest tests/test_h3_regen.py -k workflow -x -q` | ❌ Wave 0 |
| REGEN-01 | 提交/轮询/下载：FakeComfyUI（monkeypatch urllib/curl 子进程）返回 canned /prompt id → /history success+images mp4 条目 → /view bytes；断言落盘 + cache 写入；error/超时分支 → status{failed} | unit | `python3 -m pytest tests/test_h3_regen.py -k "submit or poll" -x -q` | ❌ Wave 0 |
| REGEN-02 | 4-tuple cache hit/miss：同 tuple+mp4>1KB → skip；prompt_version 变（prompt_text 改一字）→ 重渲；mp4 删 → 重下/重渲 | unit | `python3 -m pytest tests/test_h3_regen.py -k cache -x -q`（tmp_path） | ❌ Wave 0 |
| REGEN-02 | 断点续跑：FakeComfyUI 计数器 + 预置 3/5 镜 cache → 重跑只提交缺失 2 镜 | unit | `python3 -m pytest tests/test_h3_regen.py -k resume -x -q` | ❌ Wave 0 |
| REGEN-03 | VRAM guard 离线：monkeypatch subprocess.run 喂假 nvidia-smi 输出（free=21000 → 拒；free=23000 + 自身 PID 占 18GB → PID 归因放行；foreign PID 13.7GB → 等待）；kill_tts 的 pkill 调用参数断言 | unit | `python3 -m pytest tests/test_h3_regen.py -k vram -x -q` | ❌ Wave 0 |
| REGEN-03 | warnings：{code, detail} 条目 merge 保留双形 + strip 上一轮不误伤 [vision-seq] 字符串条目 | unit | `python3 -m pytest tests/test_h3_regen.py -k warnings -x -q` | ❌ Wave 0 |
| REGEN-04 | uniform 抽样确定性 + >10s 过滤 + skipped 清单 + 896×512 合法性 | unit | `python3 -m pytest tests/test_h3_regen.py -k "sample or resolution" -x -q` | ❌ Wave 0 |
| REGEN-01..04 | 真 ComfyUI smoke：`--sample-shots 2 --regen-resolution 896x512`（2 短镜，~4-8min）；完成后**重跑同命令** → 2 镜全 cache-hit 零提交（断点续跑实证）；中途 Ctrl-C 再重跑 → 只补缺失（SC1 验收形态） | smoke（manual/overnight 可自动） | `python3 analysis/roundtrip/h3_regen.py --work-dir "<ep01 dir>" --sample-shots 2 --regen-resolution 896x512` 后重跑比对 stdout cache-hit 行 | ❌ 执行期 |
| 契约 | 产物 roundtrip.json 过 `spec/schemas/roundtrip.schema.json` 校验（regen.path pattern、16-hex vch、互斥 status） | unit（jsonschema 已是 spec/ 依赖） | `python3 spec/validate.py`（若已挂 fixture）或测试内 jsonschema.validate | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_h3_regen.py -x -q`（<10s，全 monkeypatch 零真引擎）
- **Per wave merge:** `python3 -m pytest tests/ -q`
- **Phase gate:** 全 suite 绿 + 真 ComfyUI smoke（--sample-shots 2 级）+ 断点续跑实证，才进 `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_h3_regen.py` — 上述全部 unit 用例（FakeComfyUI mirror `tests/test_qwen_eye_client.py` 的 FakeHTTP/monkeypatch 模式）
- [ ] `analysis/roundtrip/workflow_fl2va.json` — 模板数据文件（§Code Examples 的 9 节点 JSON）
- [ ] 共享 fixture：假 nvidia-smi 输出样本、假 history entry（success/error/timeout 三形）——测试内联即可，无需 conftest

## Security Domain

`security_enforcement` 未在 config.json 出现（= enabled），但本 phase 攻击面极小（localhost HTTP 客户端 + 本机进程管理）。逐项核查：

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | ComfyUI :8188 无鉴权（本机环回）——不改不补，风险限于本机 |
| V3 Session Management | no | 无会话（每请求独立 urllib） |
| V4 Access Control | no | 只读 ComfyUI + 写自家 work_dir |
| V5 Input Validation | yes | workflow 参数来自 shots.json/prompts.json（自家产物）；CLI 值做 %32/帧格校验；/view 下载校验 filename 后缀 + size>1KB |
| V6 Cryptography | no | sha256 仅作 cache key（非安全用途，schema 明文声明） |

### Known Threat Patterns for 本地 GPU 编排客户端

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| pkill 误杀（pattern 过宽） | Tampering/Elevation of Info | pattern 精确到脚本名（voicedesign_server.py / indextts25-server.py），p11b validated；绝不用宽 pattern；kill 前后 warning 审计 |
| warnings/日志泄凭据 | Information Disclosure | detail 只记 exception class + 状态码（schema no-PII/no-tokens 条款）；urllib 不走代理 URL（qwen 先例 `trust_env` 语义） |
| 路径穿越（regen.path） | Tampering | schema pattern 已拒 `..`/绝对路径；客户端只写 work_dir 内相对路径 |
| ffmpeg 注入（-ss 值） | Tampering | duration/start_sec 来自自家 shots.json 数值字段，argparse float/int 强类型，非 shell 拼接（subprocess list 形式，repo 惯例） |

## Sources

### Primary (HIGH confidence — 本机实测)
- ComfyUI :8188 live 探测：`/system_stats`（v0.30.0, GPU cuda:0=3090 23.6GB）、`/object_info`（MiniMaxH3ImageToVideo required/optional 输入名 + length step 17 + trained 124-362）、`POST /upload/image` + `GET /view` 155B 探针 byte-identical、`POST /free` 200、`GET /history?max_entries=67`（SaveVideo→`images` 键、status_str success/error、3 条 h3 成功渲染的完整 workflow JSON）
- `docker inspect comfyui-primary`：NVIDIA_VISIBLE_DEVICES=1、--lowvram、模型挂载 /data/models/comfyui、输出 /mnt/agents/output/gpu1
- 容器文件系统：diffusion_models/ 两 fl2va 变体 + VAE×2 + CLIP 实存；input/ 349 文件
- nvidia-smi：GPU0=3060Ti / GPU1=3090 24576MiB free 22539；compute-apps（music3 676MiB 常驻）

### Primary (HIGH confidence — 源码精读)
- `/data/workspace/kais-aigc-platform/src/routes/production/minimax-h3/i2va.ts`（buildH3I2vaWorkflowNative 完整节点拓扑 + withGpuQueue gpuIndex:1）
- `/data/workspace/kais-aigc-platform/src/routes/production/minimax-h3/config.ts`（H3_CONSTANTS：CANVAS_MULTIPLE=32/MAX_PIXELS/FPS=24/CFG=1.0/17k+5 网格/124-362；alignH3FrameCount；adaptH3Canvas；H3_NATIVE euler+simple；token 预算 300M/340M；defaultLength=124）
- `/data/workspace/kais-aigc-platform/src/lib/gpuVramManager.ts`（nvidia-smi 查询式、/free payload、evictable 常驻注释）
- kst 侧：`analysis/call_shot_analysis.py:video_content_hash`、`analysis/vision_seq_facets.py`（cache key/warnings merge/strip）、`analysis/engine_clients/qwen_eye_client.py`（_vram_free_mib/_VRAM_GPU_INDEX=1/14000MiB/13.4GB）、`run_pipeline.py` --force 清单、`scripts/export_asset.py:_valid_warnings_list`（双形校验）、`spec/schemas/roundtrip.schema.json` + `asset.schema.json`（regen 5 字段 + warnings code enum + data.roundtrip 挂载）
- `/data/workspace/kais-hermes-skills/skills/kais-movie-pipeline/episodes/.../h3_batch_render_v4.py` 335 行逐行（kmc 四偏差）
- ep01 数据：shots.json 93 镜 / prompts.json prompt_text 93/93 / shot_frames 480×270 / h264.mp4 1920×1080@30 / vch=ece64d62bcbc534a / uniform-20 实算

### Secondary (MEDIUM confidence — 文档引用)
- [CITED: p11b-h3-vram-and-longshot-pitfalls/SKILL.md] — TTS VRAM（VoiceDesign 4.4GB/IndexTTS 6.6GB）、pkill 进程名、/free payload、直连提交模式、curl 上传、res_multistep 时长实测（15s/362f ≈ 15-20min）
- [CITED: skills/kais-video/minimax-h3-ref2va-comfyui/SKILL.md] — ref2va 节点族输入细节、cfg=1.0 负面无效、性能基线（15步 95f≈8min）、dotted autogrow key
- [CITED: skills/kais-movie-pipeline/templates/h3_ref2va_workflow.py] — KSampler 形态模板 + /prompt node_errors 解析 + BGM/audio-mode 语义（fl2va 不需要 audio ref，但 audio VAE 解码链保留）

### Tertiary (LOW confidence)
- 无未验证断言进入推荐路径；A1-A6 已列 Assumptions Log。

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 提交/轮询/回收链路端点级实测；零新依赖
- Architecture: HIGH — 双源（KAP 源码 + live history）交叉的节点拓扑；cache/warnings 有 repo 内先例
- Pitfalls: HIGH（P2/P3/P4/P5/P6/P7/P9 实证）/ MEDIUM（P1 批中 VRAM 行为——机制有 KAP 源码注释佐证，渲后水位未实测；P8 时长外推）
- VRAM guard 设计: MEDIUM — 每镜复查口径已于 plan 期裁决（Open Question 1 RESOLVED → 20-02 Task 1 PID 归因）

**Research date:** 2026-08-20
**Valid until:** 2026-09-19（ComfyUI 容器/TTS 状态是运行时实况，执行期应复核 :8188 存活与 GPU1 占用）
