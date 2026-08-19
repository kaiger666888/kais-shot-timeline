# Phase 19: qwen-eye v2 看片段 - Research

**Researched:** 2026-08-19
**Domain:** 本地 VL 引擎帧序列逐帧问答（llama.cpp 单图硬约束）+ facet 升级 + pipeline 集成
**Confidence:** HIGH（核心事实全部来自本仓代码逐行验证 + 运行时探测；估算类标 ASSUMED）

## Summary

本 phase 的全部基建已在仓内：v1 先例 `analysis/local_vision_facets.py`（cache/生命周期/graceful-degrade/schema 自校验/原子写全套）、引擎客户端 `analysis/engine_clients/qwen_eye_client.py`、`run_pipeline.py` step 5.5 挂载模式、27 个离线 pytest（0.16s 跑完）。v2 = mirror 这个先例换 facet（action/camera）换帧策略（≤8 帧均匀 + 相邻帧对）。

但研究发现了 **4 个 CONTEXT.md 前提与仓内/runtime 实况的偏差**，planner 必须吸收：

1. **`observe()` 多图入口在仓内客户端不存在** —— 客户端 docstring 明文「去掉 observe() 多图入口」，只有 `observe_single`（qwen_eye_client.py:267）。上游真源 `/home/kai/workspace/kais-hermes-skills/plugins/kais_aigc/qwen_eye.py:268` 有 `observe(image_paths)` 但**不带 question 参数**。v2 的相邻帧对问 + 纯文本 LLM 合并（策略 B）都需要客户端本地扩展（加方法，不是改引擎本体）。
2. **ep01/ep02/ep03 的 action/camera 空缺率全部为 0/93、0/100、0/76** —— 锁定决策「只填空缺、已有值永不覆盖」意味着 v2 生产路径在**所有现存集上都是 no-op**。SC1 的「prompts.json diff 可见」只能在 sandbox（把抽样镜 facet 置空的副本目录）里实证，或落在 spike report 里。roadmap SC1 措辞「只填空缺/**更短**」与 CONTEXT 锁定的「不做更短就替换（deferred）」冲突——CONTEXT 是 discuss 后的最新用户裁决，以它为准。
3. **没有任何一集有 `audio_semantic.json`**（只有 spec/fixtures/v1.2 与 v1.3 两份 fixture）。kap master（:10588）挂了 shot-analysis（POST 400 = 路由在）但 **audio-analysis 404**（在未合并分支 `feat/audio-analysis-route` 上）。SC3 的 ear 生效验证需要为 spike 镜手工构建 schema 合法的 demo 级 audio_semantic.json（schema 最低要求仅 `schema_version` + `shots[].shot_id`）。
4. **pipeline 时序：pre-step 5.6（锁定位置）在 step 7（audio semantic 产出）之前** —— 全新跑时 5.6 处 audio_semantic.json 必然不存在 → ear 自动关闭；step 7 产出后重跑管线 ear 激活 → cache key 变化 → 一次全量重烧 GPU。这是锁定决策的组合后果，需文档化接受。

另：ep01 无 route_cache 目录、ep02/ep03 的 route_cache 子目录全空 → **v1 local_vision 从未在任何集上留有生产 GPU 运行痕迹**（模块 2026-08-17 才落地，d16ee6d）。本 phase spike 是本仓首次真实 qwen-eye 批量跑。

**Primary recommendation:** mirror `local_vision_facets.py` 建 `analysis/vision_seq_facets.py`；客户端加 `observe_pair(img_a, img_b, question)` + `ask_text(question)` 两个本地扩展方法（mirror 上游多 user 消息 shape）；spike 在 sandbox 副本目录跑 A/B/baseline 三策略 + ear on/off 双跑；cache 存**原始逐帧/逐对答案**（合并是纯归约，策略锁定不重烧 GPU）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- 每镜**等间隔均匀 ≤8 帧**（时窗内均匀采样）；新增 `MAX_SEQ_FRAMES_PER_SHOT = 8`，**不动** v1 的 `MAX_FRAMES_PER_SHOT = 3`
- action/camera **分开问**（两个 facet 独立）
- camera 运镜用**相邻帧对问**：frame_i + frame_{i+1} 两图一次调用问「相对前一帧镜头/主体怎么动了」（7 对/镜）
- spike 规模：ep01 抽 **≤10 镜**（含 1-2 个强运镜镜 + 1-2 个长动作链镜）
- 候选：**A=时序拼接** vs **B=LLM 二次合并**（纯文本调用）；baseline=最长回答只作参照
- 判据：**Kai 人工并排盲评** + 客观辅助指标（时序连接词密度、实体/动作动词覆盖率、长度）；结论落 `.planning/research/vision-seq-spike-report.md`
- **新模块** `analysis/vision_seq_facets.py`（v1 零改动零回归）
- **只填空缺**：action/camera 为 `""` 的镜才填，已有值**永不覆盖**——不做「更短就替换」
- cache：`route_cache/vision_seq/shot_XXX.json`，4-tuple key + `PROMPT_VERSION = "vision-seq-v1"`；**ear on/off 进 cache key**
- pipeline 挂载：step 5.5 之后**无编号 pre-step 5.6**（不 bump step counter、`--no-vision-seq` 跳过；local_vision 之后、step_reid 之前）
- ear **生成时注入**（audio 摘要拼进逐帧提问上下文）；字段白名单：`dialogue.text`（截断）+ `dialogue.emotion` + `sfx.events` + `sfx.description`；**不进**：word-level timestamps、reproduction 层、speakers
- audio_semantic.json 存在时**默认开**，`--no-ear` 跳过；无该文件自动无 ear（degrade 不加 warning）
- 生效验证：ear on/off 双跑 diff（进 spike report）+ 单元级断言（prompt 组装含/不含音频子串）

### Claude's Discretion
- 逐帧提问的具体文案措辞（mirror v1 SCENE/SUBJECT_PROMPT 风格）
- 均匀采样的具体实现（帧索引计算、边界处理）
- spike 镜选取的具体 shot_id
- 客观辅助指标的具体计算方式

### Deferred Ideas (OUT OF SCOPE)
- VISION-03 vLLM + Qwen3-VL-8B 视频原生输入
- 「更短就替换」的 facet 升级逻辑——未来需要时再加（当前只填空缺）
- scene/subject facet 的 v1 路径（零改动零回归）
- round-trip 闭环任何部分（Phase 20/21/22）
- 修改 qwen-eye 引擎本体（server / 上游 qwen_eye.py）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VISION-01 | 帧序列逐帧问答升级 action/camera facet（≤8 帧、合并策略 spike 锁定、只填空缺不覆盖） | v1 全套先例可 mirror（本文件 §Architecture Patterns）；`observe_single` 签名/硬约束已验证；ep01 数据盘点给出 spike 候选镜；「只填空缺」在现存集上 no-op 的事实与 sandbox 方案（§Pitfall 1、§Open Questions Q1） |
| VISION-02 | ear 融合（audio_semantic → 视觉 prompt，additive、`--no-ear` 可跳过） | audio_semantic schema 最低要求已验证（仅 schema_version + shots[].shot_id）；字段白名单映射到 fixture 实测结构；无真实数据的事实 + demo 构建路径（§Pitfall 3）；pipeline 时序后果（§Pitfall 5） |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **GSD workflow enforcement**：改文件走 GSD 入口（本 phase 即 `/gsd:execute-phase`），不直接裸改 repo
- **注释/docstring 全中文（简体）**；每个可执行模块必有 module docstring（用途/算法步骤/输出 schema/CLI 用法）
- **日志**：`print(f"[stage] ...")` 括号前缀 + banner 块 + cache-hit skip 行 + 长循环 10 进度计数；无 logging 模块
- **stage 脚本互相不 import**（例外：local_vision_facets 独占 engine_clients 客户端——v2 需同样处理 sys.path 注入或共用此例外）；pipeline 以 `subprocess.run([sys.executable, str(HERE/...), ...])` 按路径调 sibling 脚本
- **JSON 写出**：`indent=2` + `ensure_ascii=False`（含中文必用）+ 原子写（tmp + os.replace）
- **CLI 惯例**：kebab-case flag、每个 add_argument 带中文 help、布尔 flag `action="store_true"` 或 dest+store_false 双 flag（`--x`/`--no-x` 先例 run_pipeline.py:684-690）
- **错误处理**：subprocess `check=True` fail-loud；缺输入 `sys.exit("...")`；无自定义异常类
- **无包管理**：无 requirements.txt/pyproject——零新 pip 依赖是硬约束（本 phase 天然满足）
- **每步一模块** + 每 step 产物自描述（repo 惯例：analysis/ 下每步一个 CLI 模块）

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 帧序列均匀采样（≤8 帧/镜） | 离线分析脚本（vision_seq_facets.py） | — | 纯本地文件系统计算，复用 frames_5fps，零 IO 新增 |
| action facet 逐帧问答 | 本地 VL 引擎客户端（qwen_eye_client） | — | llama.cpp 单图 bug → 只能 observe_single 逐帧 |
| camera facet 相邻帧对问 | 本地 VL 引擎客户端（需扩展 observe_pair） | — | 运镜=帧间差异；多 user 消息多图合法（硬约束 1） |
| 合并策略 A/B/baseline | 离线分析脚本（纯归约/纯文本 LLM 调用） | qwen-eye（策略 B 的 merge 调用） | A/baseline 零 GPU；B 复用同引擎纯文本调用 |
| ear 融合 | 离线分析脚本（prompt 组装层） | — | 生成时注入：拼进提问文本，非后处理改写 |
| per-shot cache / 幂等 | 文件系统（route_cache/vision_seq/） | — | mirror WR-04 4-tuple 惯例 |
| prompts.json 写入保护 | 离线分析脚本 + schema 校验 | — | 只填空缺 + Draft202012Validator 写前自校验 |
| pipeline 编排 | run_pipeline.py（pre-step 5.6） | — | subprocess 按路径调用，无编号 banner |
| GPU/引擎生命周期 | qwen_eye_client（ensure_ready/stop_if_owned） | KAP :10588 allocate | 13.4GB lease 防泄漏 try/finally |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| qwen_eye_client（仓内） | qwen3.8-27b-q3@c3949404 | 引擎调用/生命周期 | v1 已用；本 phase 唯一引擎 |
| jsonschema（已装） | Draft202012Validator | prompts.json 写前自校验 | v1/call_shot_analysis 同款 fails-loud 惯例 |
| argparse/json/os/sys/pathlib（stdlib） | py3.12 | CLI + 原子写 | repo 零新依赖约束 |
| pytest（已装） | — | 离线单测 | 27 tests / 0.16s 现状 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| 无新增 | — | — | 零新引擎、零新模型下载、零新 pip 包（SC4 明文） |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 逐帧 observe_single | vLLM + Qwen3-VL-8B 视频原生 | VISION-03 deferred（锁定决策 2）；llama.cpp 单图 bug 是硬约束 |
| 相邻帧对问 camera | 单帧问 camera | 运镜本质是帧间差异，单帧答不出——CONTEXT 已锁定对问 |

**Installation:** 无。`pip list` 不变。

**Package Legitimacy Audit:** 本 phase **零外部包安装**（零新 pip 依赖、零新引擎、零模型下载，SC4 明文约束）→ 审计不适用（none）。

## Architecture Patterns

### System Architecture Diagram

```text
run_pipeline.py main()
  │
  ├─ step 5  step_semantic ────────────▶ prompts.json（route 产物，含富 facets）
  ├─ 5.5 pre-step local_vision（v1，零改动）
  │      └─▶ 填空缺 scene/subject（route_cache/local_vision/）
  │
  ├─ 5.6 pre-step vision_seq（v2 新增，--no-vision-seq 跳过）            ★本 phase
  │      │  触发条件：args.vision_seq ∧ ¬skip_semantic ∧ prompts.json 在 ∧ frames_5fps/ 在
  │      │
  │      ▼  subprocess: analysis/vision_seq_facets.py
  │   ┌──────────────────────────────────────────────────────────────┐
  │   │ 读 prompts.json + shots.json + frames_5fps/（5fps 等间隔 jpg）│
  │   │ 读 audio_semantic.json（在位→ear 默认开；--no-ear→关）        │
  │   │                                                              │
  │   │ per-shot：action/camera 为 ""？ ──否──▶ 跳过（永不覆盖）      │
  │   │   是 ▼                                                        │
  │   │ 均匀采样 ≤8 帧（f%06d.jpg，编号1起，≈(N-1)/5s）               │
  │   │   ├─ action：8 次 observe_single（ear=音频摘要拼进提问）      │
  │   │   └─ camera：7 次 observe_pair（frame_i + frame_{i+1} 对问）  │
  │   │ cache 命中（route_cache/vision_seq/shot_XXX.json，           │
  │   │   4-tuple + ear 标志）──▶ 直接用原始答案，零 GPU             │
  │   │                                                              │
  │   │ 合并（策略锁定后）：                                          │
  │   │   A 时序拼接（纯归约） / B LLM 二次合并（ask_text 纯文本）    │
  │   │   / baseline 最长回答（参照）                                 │
  │   └──────────────────────────────────────────────────────────────┘
  │      ├─▶ prompts.json（只改空缺 action/camera 两键；写前 schema
  │      │     自校验 + 原子写）
  │      └─▶ route_cache/warnings.json（[vision-seq] 前缀，READ-merge-write）
  │
  ├─ step 6  step_reid ──▶ registry.draft.json
  ├─ step 7  step_audio_semantic ──▶ audio_semantic.json（route 在才写）
  │            ▲ 时序注意：5.6 在 step 7 之前——首跑 ear 必然缺席（§Pitfall 5）
  └─ step 8/8/9.5 timeline/export/canvas
```

### Recommended Project Structure
```text
analysis/
├── vision_seq_facets.py          # v2 新模块（mirror local_vision_facets.py 结构）
├── local_vision_facets.py        # v1 零改动
└── engine_clients/
    └── qwen_eye_client.py        # +observe_pair/ask_text 本地扩展（头部注明偏离上游）
tests/
├── test_vision_seq_facets.py     # 新（mirror test_local_vision_facets.py 12 test 模式）
└── test_pipeline_vision_seq_wiring.py  # 新（mirror wiring 4 test 模式）
.planning/research/
└── vision-seq-spike-report.md    # spike 结论落档（mirror v1.2-research/audio-spike-report.md 先例）
```

### Pattern 1: 引擎生命周期 try/finally（防 13.4GB 泄漏）
**What:** `ensure_ready()` → `(healthy, owned)`；`finally: stop_if_owned()` 只停自己拉起的 server。 [VERIFIED: codebase qwen_eye_client.py:159-231, local_vision_facets.py:228-271]

Guard 链（v2 直接继承，勿重写）：health 探测 → Guard 1 VRAM 预检（GPU1 free < 14000MiB 不启动；**必须在 health 之后**——健康 q3 自占 13.4GB 会误杀）→ KAP allocate（:10588，`{"variantId":"q3","caller":...}`）→ fallback `bash /opt/qwen-llm/kap-llm.sh start q3` → 轮询 ≤120s + Guard 2（server.log 自 offset 起 `failed to load model|model loading error` → 立即放弃）。

### Pattern 2: 4-tuple + ear cache key
**What:** `_cache_key = {video_content_hash, engine_name, engine_version, prompt_version}`；v2 加 ear 维度（推荐显式第 5 字段 `"ear": true/false`，或 PROMPT_VERSION 后缀 `"vision-seq-v1+ear"`——两者语义等价，任一不匹配即 miss）。 [VERIFIED: codebase local_vision_facets.py:170-178]

**关键设计建议（本研究所增）：cache 存原始证据而非合并产物。** per-shot cache 的 `answers` dict 存 `action_frame_1..8` + `camera_pair_1..7` 的原始逐帧/逐对答案；合并（A/baseline 纯归约零 GPU；B 的 LLM merge 结果另存 `merged_B` 键）在写出时进行。收益：策略锁定/换策略不烧 GPU；spike 三策略共用同一份原始证据。

### Pattern 3: 相邻帧对问的消息构造（mirror 上游 observe）
**What:** 每图一条 user 消息（硬约束 1），question 作为最后一条图像消息的 text part。上游 `observe()` shape： [VERIFIED: codebase 上游 kais-hermes-skills/plugins/kais_aigc/qwen_eye.py:268-283]

```python
# Source: 上游 qwen_eye.py:268-283（repo 客户端缺此入口——见 Pitfall 2）
def observe(self, image_paths: list[Path]) -> str:
    n = len(image_paths)
    messages: list[dict] = []
    for i, path in enumerate(image_paths):
        messages.append({"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + self._b64(path)}},
            {"type": "text", "text": f"(帧{i + 1}/{n})"},
        ]})
    return self._call_llm(messages, max_tokens=2000)
```

v2 需要的形态（本地扩展，question 拼进第二条消息）：

```python
def observe_pair(self, img_a: Path, img_b: Path, question: str,
                 max_tokens: int = 2000) -> str:
    messages = [
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + self._b64(img_a)}},
            {"type": "text", "text": "(第1帧/前一帧)"}]},
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + self._b64(img_b)}},
            {"type": "text", "text": "(第2帧/当前帧)" + question}]},
    ]
    return self._call_llm(messages, max_tokens=max_tokens)

def ask_text(self, question: str, max_tokens: int = 2000) -> str:
    """纯文本调用（策略 B 合并用）——无图 = 豁免多图丢弃 bug。"""
    return self._call_llm(
        [{"role": "user", "content": [{"type": "text", "text": question}]}],
        max_tokens=max_tokens)
```

恒传 `enable_thinking:false`（`_call_llm` 已内置，qwen_eye_client.py:243）——否则 thinking 吃光 max_tokens 返回空串。

### Pattern 4: pipeline pre-step 5.6 挂载（mirror 5.5）
**What:** 无编号 plain-label banner + dest/store_false 双 flag + 存在性条件。 [VERIFIED: codebase run_pipeline.py:801-822（5.5 先例）, 684-690（flag 惯例）, 122-126（run_step banner）]

```python
# 插入点：run_pipeline.py:822（5.5 块结束）与 824（step 6 reid 注释）之间
# argparse 段（~690 行后）：
ap.add_argument("--vision-seq", dest="vision_seq", action="store_true", default=True,
                help="启用帧序列逐帧问答升级 action/camera facets（默认启用；5.6 无编号 pre-step）")
ap.add_argument("--no-vision-seq", dest="vision_seq", action="store_false",
                help="禁用帧序列 v2（action/camera 保持现有值）")
# main() 体：
if (args.vision_seq and not args.skip_semantic
        and os.path.exists(prompts_json)
        and os.path.isdir(frames_dir)):
    cmd = [sys.executable, str(HERE / "analysis" / "vision_seq_facets.py"),
           "--shots", shots, "--frames-dir", frames_dir,
           "--work-dir", work_dir, "--output", prompts_json, "--video", video]
    run_step(cmd, "vision seq facets (qwen-eye v2 pre-step)")   # plain label，无 [N/9]
```

**注意 ear 输入**：`audio_semantic_json` 变量在 run_pipeline.py:736 已定义（step 7 产物路径），可直接作 `--audio-semantic` 参数传给子进程（文件存在性由模块自判）。

### Pattern 5: warnings sidecar + graceful-degrade
**What:** 引擎不可用 → facet 保原值 + `[vision-seq]` 前缀 warning + exit 0；sidecar READ-merge-write，strip 本 step 上一轮条目防 self-accumulate，他 step 条目保留。 [VERIFIED: codebase local_vision_facets.py:155-167, 219-296]

### Pattern 6: 均匀采样实现（Claude's discretion 区，研究给参考实现）
```python
# frames_5fps: f%06d.jpg 编号从 1 起，第 N 帧 ≈ (N-1)/5s（local_vision_facets.py:113-137）
def select_uniform_frames(frames_dir, start_sec, end_sec, max_frames=8):
    window = [...]  # mirror v1 select_frames 的时窗过滤 + 忽略 *_ds1280.jpg 变体
    if len(window) <= max_frames:
        return window
    idx = {round(i * (len(window) - 1) / (max_frames - 1)) for i in range(max_frames)}
    return [window[i] for i in sorted(idx)]
```
ep01 实况：93 镜中 64 镜时窗内 ≥8 帧（duration ≥1.6s）；中位镜 2.27s ≈ 11 帧。 [VERIFIED: runtime probe]

### Anti-Patterns to Avoid
- **单条 user 消息带多图**：llama.cpp 只算 ceil(N/2) 张——相邻帧对必须拆两条 user 消息 [VERIFIED: codebase qwen_eye_client.py:29-31]
- **忘记 enable_thinking:false**：thinking 吃光预算 → 空串 PARSE_FAIL [VERIFIED: codebase qwen_eye_client.py:241-243]
- **并行调引擎**：单实例串行 thread-unsafe by design [VERIFIED: codebase qwen_eye_client.py:33]
- **stop 不属于自己的 server**：预存在 lease 绝不动（KAP 归因会断） [VERIFIED: codebase qwen_eye_client.py:216-231]
- **在 5.6 位置假设 audio_semantic.json 在位**：首跑必然缺席（step 7 在后） [VERIFIED: codebase run_pipeline.py:801-840 执行顺序]
- **banner 带 [N/9] 数字前缀**：test_step_banner_count_unchanged 的 grep 锁会破（`[5.5/9]` not in src 断言） [VERIFIED: codebase tests/test_pipeline_vision_wiring.py:99-107]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 引擎生命周期/VRAM guard | 自写 nvidia-smi 轮询+启停 | QwenEye.ensure_ready/stop_if_owned | 双 guard + 顺序陷阱 + lease 归因，v1 已验收 |
| cache 失效 | mtime 比对 | 4-tuple _cache_key + PROMPT_VERSION 旋钮 | WR-04 惯例，跨视频/引擎/prompt 三维失效 |
| facet 写入合法性 | 手写字段检查 | Draft202012Validator(prompts.schema.json) 写前自校验 | v1/call_shot_analysis 同款 fails-loud |
| 视频身份 hash | 全文件 sha256 | video_content_hash（首尾 1MB+size） | multi-GB 毫秒级，local_vision_facets.py:99-110 |
| 半写读取竞态 | 直接 open(w) | tmp + os.replace 原子写 | v1 全套先例 |

**Key insight:** v2 的全部「难」都在 v1 已解决的层（生命周期/cache/degrade/写保护）；v2 真正的新逻辑只有：均匀采样、对问、合并、ear 注入——都是纯函数，可单测覆盖。

## Runtime State Inventory

> 本 phase 非 rename/refactor/migration —— 按 protocol 略。但按 SC 精神做了等价的 runtime 盘点（见 §Environment Availability + ep01 数据盘点），关键 runtime 事实：**任何集都无 audio_semantic.json、任何集都无 local_vision/vision cache 痕迹、ep01 无 route_cache 目录**。

## ep01 数据盘点（runtime 事实，spike 输入实况）

全部 [VERIFIED: runtime probe 2026-08-19]，目录 `output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/`：

| 项 | 实况 |
|----|------|
| shots.json | 93 镜；duration min 0.53 / p25 1.50 / med 2.27 / p75 4.00 / max 19.73s；总长 308.3s；≥8 帧镜 64/93 |
| frames_5fps | 1542 张非 ds jpg（f000001-f001542.jpg）+ 11 张 `_ds1280` 变体（须忽略） |
| prompts.json | mtime **2026-07-20**（route 时代产物，早于 local_vision 08-17 落地）；action/camera/scene/subject 空缺率全为 **0/93**；action len p50=27/p90=35/max=44；camera len p50=11/p90=20/max=30 |
| route_cache | **目录不存在**（ep01 从未跑过 v1.1+ 路由缓存布局的步骤） |
| audio_semantic.json | **不存在**（全集皆无，仅 spec/fixtures/v1.2、v1.3 两份 fixture） |
| transcript.json | 155 段真实对白（ear demo 构建可用真 dialogue.text） |
| ep02/ep03 | prompts.json 全满（0 空缺）；route_cache/{shot_analysis,local_vision,audio_analysis,character_reid} 全空目录；ep02 warnings.json 记录 route 全 degrade 事故 |
| audio_semantic fixture 结构 | shot = `{shot_id, start_sec, end_sec, duration, dialogue{text,spk_id,emotion,emotion_confidence,events,words}, sfx{events,description}, reproduction{tts,music_gen,foley}}`；schema 最低要求仅 `schema_version` + `shots[].shot_id`（+ words[] 内 start/end/text） |

**spike 候选镜（Claude's discretion 区的研究建议，按「强运镜 + 长动作链」标准扫出）：**

| shot_id | dur | camera（现行值） | 特征 |
|---------|-----|------------------|------|
| #91 | 15.1s | 由面部大特写大幅拉升拉远至大远景，航拍式拉镜 | 强运镜（拉）+ 长镜（~75 帧） |
| #88 | 13.0s | 首帧中景过肩，尾帧推至面部特写，平视推镜 | 强运镜（推）+ 动作链（低头垂角闭目） |
| #66 | 6.9s | 低角度特写转大全景，拉升 | 强运镜（拉升）+ 对峙动作 |
| #46 | 5.7s | 全景动作后推至面部大特写 | 运镜 + 快速动作（蜈蚣猛扑） |
| #70 | 19.7s | （最长镜，~98 帧） | 长动作链（举刀戒备→惊骇反应） |
| #1 | 6.7s | 由面部近景拉至全景 | 递浆果动作链（v1 样例镜，对比直观） |

ear demo 镜建议从上表挑 2-3 个（audio 摘要手工构造：真实 dialogue.text + 示范性 sfx 如 雨声/脚步）。

## Common Pitfalls

### Pitfall 1: 「只填空缺」在现存集上是 no-op（SC1 表述冲突）
**What goes wrong:** ep01/02/03 的 action/camera 空缺率全为 0。v2 生产语义（锁定：只填 `""`、永不覆盖）在所有现存集上不会改写 prompts.json 任何字节。SC1 字面（「ep01 抽样镜跑 v2 后 prompts.json 的 action/camera 含跨帧合并产物」+「只填空缺/**更短**」）在锁定决策下不可同时成立——「更短就替换」已被 CONTEXT 明确 deferred。
**Why it happens:** roadmap SC1 措辞早于 discuss 锁定；ep01 的 facets 是 07-20 route 富产物。
**How to avoid:** SC1 的「diff 可见」用 **sandbox 实证**：复制最小 work_dir（shots.json + prompts.json 副本 + frames_5fps symlink），把抽样镜 action/camera 置 `""`，v2 跑 sandbox → 三策略产物 + 与 v1 现行值并排对比进 spike report；**live ep01 prompts.json 保持 byte-identical**（这本身就是「不覆盖」的最强证明——sha256 前后比对作 SC1 负测试）。
**Warning signs:** plan 里出现「升级 ep01 的 action/camera」类任务 = 违反锁定决策。

### Pitfall 2: 客户端没有多图/纯文本入口（CONTEXT 前提偏差）
**What goes wrong:** CONTEXT 写「observe() 多图入口已存在」——仓内客户端 docstring 明文裁掉了它（qwen_eye_client.py:10），只剩 `observe_single`（:267）。且上游 `observe()` 不带 question 参数，无法直接满足「对问」需求；策略 B 的纯文本合并调用也无现成入口。
**How to avoid:** v2 交付物含**客户端本地扩展**：`observe_pair(img_a, img_b, question)` + `ask_text(question)`（Pattern 3 代码），头部注释更新「相对上游的裁剪/扩展」清单。这是改 repo 副本，不是改引擎本体（NOT in scope 边界不破——上游 server/生命周期/HTTP shape 全不动）。同步加 test_qwen_eye_client.py 风格的单测（消息 shape 断言）。
**Warning signs:** vision_seq_facets.py 里直接调 `engine._call_llm`（私有 API 越界）。

### Pitfall 3: ear 没有真实输入数据（SC3 数据缺口）
**What goes wrong:** SC3 要「带 audio_semantic.json 的集上 ear 融合可见生效」，但全盘无此文件；audio-analysis 路由在 kap master 404（未合并分支 feat/audio-analysis-route），本 phase 不可能靠 route 产出。
**How to avoid:** 为 spike 构建 demo 级 audio_semantic.json：schema 最低要求仅 `schema_version` + `shots[].shot_id`，dialogue.text 用 ep01 transcript 真实对白，sfx 手工加示范事件（雨声/脚步声——正好演示「雨声→scene、脚步→动作链补走近」）。文件放 sandbox 目录（**不放 live ep01 work_dir**——避免污染真数据目录）。单测用 spec/fixtures/v1.2/audio_semantic.json。
**Warning signs:** plan 里出现「部署/合并 audio-analysis 路由」任务 = 越界（deferred 范畴）。

### Pitfall 4: Q3 27B 帧序列动作描述质量未验证（research Pitfall 3 原文）
**What goes wrong:** 合并策略若靠机器指标自动锁定 = 循环论证（指标本身假设「长/连接词多=好」）。
**How to avoid:** CONTEXT 已锁定判据结构：Kai 盲评为主 + 客观指标为辅；结论必须落 `.planning/research/vision-seq-spike-report.md`（mirror `.planning/milestones/v1.2-research/audio-spike-report.md` 先例：证据 + 锁定结论 + 样例摘录）。盲评材料：同镜三策略产物匿名编号（甲/乙/丙）+ v1 现行值参照，并排表格。
**Warning signs:** plan 里没有「Kai 盲评」人工门。

### Pitfall 5: pipeline 时序——5.6 在 step 7 之前，ear 首跑必然缺席
**What goes wrong:** 全新管线跑：5.6 处 audio_semantic.json 不存在 → ear 自动关（无 warning）；step 7 产出后**再跑**管线 → ear 开 → cache key 变 → **一次全量 GPU 重烧**（~93×15≈1400 calls）。
**Why it happens:** 锁定挂载位（step_reid 前）+锁定 ear 默认开 +锁定 ear 进 cache key 的组合后果。
**How to avoid:** 无法在锁定约束内消除——文档化接受 + 缓解：(a) spike/生产首跑用 `--no-ear` 显式定死无 ear 版本；(b) README/help 写明「ear 激活发生在 audio_semantic.json 就位后的第二次管线跑」；(c) 操作员想跳过重烧就保持 `--no-ear`。-planner 把这一条写进模块 docstring。
**Warning signs:** 有人期望「一次管线跑同时拿到 ear 版 facets」。

### Pitfall 6: 调用量预算失控（GPU 时间）
**What goes wrong:** 每镜 15 calls（8 action 帧 + 7 camera 对）；ep01 全量 93×15≈1395 calls（策略 B 再 +2/镜 merge）。串行引擎 + 单 call 未知延迟（LLM_CALL_TIMEOUT_S 上限 3600s，CPU fallback 单 call 可 ~5.5min）→ 全量可能是 overnight 级。
**How to avoid:** 本 phase 只跑 **spike ≤10 镜**（~15×10 + B 合并 2×10 + ear 双跑子集 ≈ 200-260 calls，[ASSUMED] 估计 1-3h）；全量跑不在本 phase SC 内。进度打印 mirror v1（每 10 镜一行）+ cache 断点续跑天然支持中断恢复。
**Warning signs:** plan 把「ep01 全量 93 镜 v2」列为交付物。

### Pitfall 7: 覆盖守卫语义混淆
**What goes wrong:** 把 aw2-fast 守卫（call_shot_analysis.py:418-442：route 全 degrade + 既有富 prompts.json → 跳过覆盖）误解为 facet 级守卫。它是**步骤级**守卫（防空壳整体覆盖），v1/v2 的「已有值不覆盖」是**字段级**语义——两者互补不打架。
**How to avoid:** v2 永不整体重写 prompts.json 非目标键（v1 同款：读入→只改目标键→写回）；commit 25c8ce9 本体是 canvas-import 文档 commit，守卫代码在 d166b8d/e9c8793（勿引错 commit）。

### Pitfall 8: `_ds1280.jpg` 变体帧混入采样
**What goes wrong:** dissolve 扫描旁路产物混进均匀采样序列（ep01 有 11 张）。
**How to avoid:** mirror v1 过滤 `"_ds" not in p.stem`（local_vision_facets.py:122-125）。

## Code Examples

### v1 observe_single（v2 action 逐帧直接复用）
```python
# Source: analysis/engine_clients/qwen_eye_client.py:267-279 [VERIFIED: codebase]
def observe_single(self, image_path: Path, question: str,
                   max_tokens: int = 2000) -> str:
    messages = [{"role": "user", "content": [
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + self._b64(image_path)}},
        {"type": "text", "text": question},
    ]}]
    return self._call_llm(messages, max_tokens=max_tokens)
```

### ear prompt 组装（生成时注入，白名单字段）
```python
# 推荐 shape（Claude's discretion 区的研究建议）：
def build_audio_context(shot_audio: dict, max_text: int = 200) -> str:
    parts = []
    d = shot_audio.get("dialogue") or {}
    if d.get("text"):
        text = d["text"][:max_text]                      # 截断
        emo = d.get("emotion")
        parts.append(f"对白「{text}」" + (f"（情绪:{emo}）" if emo else ""))
    sfx = shot_audio.get("sfx") or {}
    if sfx.get("events"):
        desc = sfx.get("description") or ""
        parts.append(f"音效:{'/'.join(sfx['events'])} {desc}".strip())
    return "；".join(parts)
# 逐帧提问 = f"该镜音频：{audio_ctx}。结合这一帧，{ACTION_PROMPT}"
# 单测断言：有 audio → 提问含音频子串；--no-ear / 无文件 → 不含（SC3 单元级）
# 白名单外字段（words/reproduction/spk_id）永不出现 —— grep 负测试可证
```

### cache 命中零引擎调用（SC4 单测骨架，mirror v1 test）
```python
# Source: tests/test_local_vision_facets.py:128-147 模式 [VERIFIED: codebase]
def test_cache_hit_second_run_zero_engine_calls(tmp_path, monkeypatch):
    fake = FakeEngine("答案")            # 记录 call_count
    patch_engine(monkeypatch, fake)
    run_main(work, prompts_path)         # 第一跑：N 次调用
    assert fake.call_count > 0
    fake2 = FakeEngine("不该被问到")
    patch_engine(monkeypatch, fake2)
    run_main(work, prompts_path)         # 第二跑：全 cache 命中
    assert fake2.call_count == 0         # SC4 的机器可证断言
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 3 静帧取最长回答（v1 local_vision） | ≤8 帧逐帧 + 对问 + 合并策略（v2 本 phase） | Phase 19 | action/camera 从「单帧脑补」到「时序证据链」 |
| observe() 多图入口在上游 | repo 副本裁剪掉（2026-08-17 d16ee6d 复制时） | — | v2 需本地扩展（Pitfall 2） |
| audio-analysis 路由 8000 端口 DEFERRED | shot-analysis 已上 kap master :10588（e9c8793 ROUTE_PATH 修复）；audio-analysis 仍在 feat/audio-analysis-route 未合并分支 | 2026-08-19 | ear 输入只能 demo 级构建（Pitfall 3） |

**Deprecated/outdated:**
- STATE.md 旧表述「route branches unmerged 不阻塞」中 shot-analysis 部分已过时（master 已挂，probe 400 证实路由在）；audio-analysis 部分仍准确（404）。 [VERIFIED: runtime probe]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 单 call 延迟 10-60s 量级（27B Q3 单图问答），spike 200-260 calls ≈ 1-3h | Pitfall 6 | 预算偏离——spike 可能需要切小（≤5 镜）或分批跑；cache 断点续跑兜底 |
| A2 | demo 级 audio_semantic.json（真 dialogue + 手工 sfx）足以支撑 SC3 的「生效可见」验证 | Pitfall 3 | 若 Kai 要求真实音频语义产物，SC3 需改依赖 route 分支部署（越界）——需用户确认 |
| A3 | 策略 B 纯文本合并不受单图 bug 影响（无图=无图可丢） | Pattern 3 | 若 llama.cpp 对纯文本调用另有怪癖，B 策略降级为 A——spike 本身会暴露 |
| A4 | 相邻帧对问两条 user 消息两张图都能被模型看到（上游 observe() 同 shape 已在别处使用） | Pattern 3 | 若对问失效（模型只见一图），camera 退化为逐帧单帧问——spike 盲评会暴露（camera 答案无帧间语义时 B/A 均无运镜信息） |
| A5 | 客户端本地扩展方法属「Claude's discretion/实现细节」而非违反「不修改引擎本体」 | Pitfall 2 | 若用户视为越界，改为 vision_seq_facets 内构造消息 + 引擎暴露受控入口——需确认 |

## Open Questions

1. **SC1 与「只填空缺」锁定的字面冲突如何收口？**
   - What we know: 全部现存集 action/camera 0 空缺；CONTEXT 锁定永不覆盖、更短替换 deferred；roadmap SC1 仍写「只填空缺/更短」。
   - What's unclear: Kai 是否期望 live ep01 prompts.json 在本 phase 被升级（即临时授权抽样镜覆盖）。
   - Recommendation: 默认 sandbox 实证 + live 文件 sha 不变（研究强烈建议——与守卫精神一致）；plan 里作为一个显式 checkpoint 让 Kai 确认。
2. **spike 的 GPU 执行时机与操作员在场性**
   - What we know: 引擎当前 down（:8125 无响应）；GPU1 free 22.5GB ≥ 14GB 门槛可拉起；spike 1-3h [ASSUMED]。
   - What's unclear: 交互路径内跑还是后台 tmux 跑；ComfyUI/TTS 若同卡抢占的现场处理。
   - Recommendation: plan 把「spike 双跑（A/B 原始证据 + ear on/off）」列为独立 GPU 任务，tmux 后台 + cache 断点续跑，不阻塞其他 task。
3. **盲评材料的呈现载体**
   - What we know: 结论落 markdown spike report；盲评要「并排打分」。
   - What's unclear: 纯 markdown 表格够不够（vs 小 HTML）。
   - Recommendation: markdown 表格 + 帧图相对路径引用（repo .html 被 gitignore，md 更可归档）；mirror audio-spike-report 先例。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| qwen-eye server :8125 | 全部 LLM 调用 | ✗（down，可拉起） | qwen3.8-27b-q3@c3949404 | ensure_ready 自动拉起（GPU1 free 22539MiB ≥ 14000 门槛 ✅） |
| KAP :10588 | allocate lease | ✓ | — | kap-llm.sh 直跑 fallback（客户端内置） |
| GPU1 RTX 3090 | 13.4GB lease | ✓ | free 22539 MiB | — |
| shot-analysis 路由（kap master） | 无直接依赖（背景） | ✓（POST 400=在） | — | — |
| audio-analysis 路由 | ear 真实数据 | ✗（404，未合并分支） | — | demo 级 audio_semantic.json（Pitfall 3） |
| python3 / pytest / jsonschema | 单测 | ✓ | 3.12.3 / 27 tests 0.16s / Draft202012 | — |
| /opt/qwen-llm/server.log | Guard 2 死因检测 | ✓（路径存在性由客户端运行时自判） | — | log 不可读 → best-effort False |

**Missing dependencies with no fallback:** 无（engine down 是设计内状态，ensure_ready 处理）。
**Missing dependencies with fallback:** audio-analysis 路由 → demo 构建（A2 需确认）。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest（系统 python3，无独立配置文件） |
| Config file | none（repo 根直接跑） |
| Quick run command | `python3 -m pytest tests/ -q`（现状 27 passed / 0.16s，全离线零网络） |
| Full suite command | 同上（本仓无 GPU 测试；GPU 类验证走 spike 手动档） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VISION-01 | 均匀采样 ≤8 帧、<8 帧全取、忽略 _ds 变体 | unit | `python3 -m pytest tests/test_vision_seq_facets.py -q` | ❌ Wave 0 |
| VISION-01 | 只填空缺：已有 action/camera 不被覆盖（mirror v1 test_existing_facet_not_overwritten） | unit | 同上 | ❌ Wave 0 |
| VISION-01 | cache 命中二跑零引擎调用 + stale key miss 重拉 | unit | 同上 | ❌ Wave 0 |
| VISION-01 | 合并策略 A/baseline 纯归约确定性（同输入同输出、零引擎调用） | unit | 同上 | ❌ Wave 0 |
| VISION-01 | graceful-degrade：引擎不可用 → facet 原值 + [vision-seq] warning + exit 0 | unit | 同上 | ❌ Wave 0 |
| VISION-01 | 写前 schema 校验 + 原子写 + warnings sidecar merge | unit | 同上 | ❌ Wave 0 |
| VISION-01 | 客户端扩展消息 shape（pair=两条 user 各一图、ask_text 纯文本） | unit | `python3 -m pytest tests/test_qwen_eye_client.py -q`（扩展现有文件） | ✅（扩展） |
| VISION-01/PIPE | wiring：--no-vision-seq 解析、5.6 块在 5.5 后 step_reid 前、banner 无 [N/9] | unit(静态+argparse spy) | `python3 -m pytest tests/test_pipeline_vision_seq_wiring.py -q` | ❌ Wave 0 |
| VISION-02 | prompt 组装：有 audio 含音频子串 / --no-ear 不含 / 白名单外字段不出现 | unit | `python3 -m pytest tests/test_vision_seq_facets.py -q` | ❌ Wave 0 |
| VISION-02 | 无 audio_semantic.json → 自动无 ear、零 warning、输出与显式 --no-ear byte-identical | unit | 同上 | ❌ Wave 0 |
| SC1 | live ep01 prompts.json 前后 sha256 不变（不覆盖证明） | integration（spike 手动档，命令记录进 spike report） | `sha256sum …/prompts.json`（跑 v2 sandbox 前后） | n/a（手动） |
| SC1 | sandbox 空缺镜被跨帧合并产物填充、与 v1 三静帧产物差异可见 | manual（Kai 审阅 spike report） | — | n/a |
| SC2 | 三策略产物 + 客观指标 + 盲评结论落 `.planning/research/vision-seq-spike-report.md` | manual-only（Kai 盲评是人工门——Pitfall 4 判据结构锁定） | `test -f .planning/research/vision-seq-spike-report.md` | n/a |
| SC3 | ear on/off 双跑 diff 呈现（spike report 章节） | manual（diff 材料机器生成） | — | n/a |
| SC4 | 二跑 wall-clock 秒级 + 引擎零调用（FakeEngine call_count==0） | unit + runtime | unit 见上；runtime：真跑二跑计时记录进 spike report | 部分 ❌ |
| SC4 | 零新引擎/零模型下载 | 静态 review | `git diff --stat` 范围审查（无新 engine_clients 模块、无 HF 调用） | n/a |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -q`（<1s，全离线）
- **Per wave merge:** 同上 + wiring 文件
- **Phase gate:** 全 suite 绿 + spike report 在档 + live prompts.json sha 不变证明，才进 `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_vision_seq_facets.py` —— 覆盖上表全部 unit 项（mirror test_local_vision_facets.py 的 make_workdir/FakeEngine/argv 注入骨架）
- [ ] `tests/test_pipeline_vision_seq_wiring.py` —— mirror test_pipeline_vision_wiring.py（--help 冒烟 + argparse spy + 静态顺序断言 + banner count 锁不破）
- [ ] sandbox spike 脚手架（副本 work_dir 构建 + 抽样镜 facet 置空 + demo audio_semantic.json 生成）——建议 `spike/vision_seq/` 下（repo 已有 spike/ 先例目录）

*(现有 27 test 全部保持绿 = v1 零回归的机器证明)*

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 本地 CLI 管线，无新端点 |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | LLM 产出文本写入 prompts.json 前过 Draft202012Validator（type:string 全字段）；audio_semantic 读取按白名单字段提取（V5 语义：不信任模型输出 shape，缺字段/类型错一律跳过） |
| V6 Cryptography | no | — |

### Known Threat Patterns for 本地 LLM 管线
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 模型产出注入下游渲染（prompt_text/新 facet 是模型文本） | Tampering | 写前 schema 校验（string 类型约束）；HTML 渲染侧 _esc 是 Phase 22 PRESENT-01 范畴，本 phase 不产 HTML |
| cache 投毒（shot_XXX.json 篡改） | Tampering | _cache_key 4-tuple 比对（video hash 参与 urlparse 无关的强绑定）；cache 读失败=miss 重拉 |
| 引擎端点错配 | Spoofing | 常量 URL（127.0.0.1:8125/10588），无用户可控 URL 输入 |

## Sources

### Primary (HIGH confidence)
- 仓内代码逐行：`analysis/engine_clients/qwen_eye_client.py`（279 行全文）、`analysis/local_vision_facets.py`（373 行全文）、`run_pipeline.py:122-126,650-870`、`analysis/call_shot_analysis.py:405-460`（aw2-fast 守卫）、`tests/test_{local_vision_facets,pipeline_vision_wiring,semantic_no_clobber,qwen_eye_client}.py`
- 上游真源：`/home/kai/workspace/kais-hermes-skills/plugins/kais_aigc/qwen_eye.py:268-283`（observe() shape）@ commit c3949404
- Runtime probe（2026-08-19 本机）：ep01/02/03 数据统计（python3 直读 JSON）、:8125 health（down）、:10588 两路由 POST（400/404）、nvidia-smi（GPU0 free 4502MiB / GPU1 free 22539MiB）、pytest 27 passed 0.16s
- Schema：`spec/schemas/prompts.schema.json`（action/camera = required type:string）、`spec/schemas/audio_semantic.schema.json`（required 链）、`spec/fixtures/v1.2/audio_semantic.json`（结构实况）
- Git：d16ee6d（local_vision Phase 1, 2026-08-17）、d166b8d/e9c8793（守卫+ROUTE_PATH）、25c8ce9（实为 canvas-import 文档 commit）
- `.planning/research/SUMMARY.md` + `v1.3-roundtrip-validation-proposal.md`（Pitfall 3 原文、VRAM 竞争）

### Secondary (MEDIUM confidence)
- 无（本研究无 WebSearch 类外部来源）

### Tertiary (LOW confidence)
- 无

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 全部仓内既有件，零新依赖
- Architecture: HIGH — mirror v1 全套已验收模式；仅客户端扩展点是新增（shape 来自上游逐行）
- Pitfalls: HIGH — 4 个 CONTEXT 偏差全部有 codebase/runtime 直接证据；A1/A3/A4 估算与行为假设已入 Assumptions Log
- Data facts: HIGH — ep01 统计与文件在位性全部本机实测

**Research date:** 2026-08-19
**Valid until:** 2026-09-02（仓内事实稳定；GPU/路由 probe 有效期短——执行前建议复探 :8125/:10588）
