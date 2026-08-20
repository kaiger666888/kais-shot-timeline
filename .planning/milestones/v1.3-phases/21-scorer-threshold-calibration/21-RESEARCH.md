# Phase 21: Scorer + 阈值校准 - Research

**Researched:** 2026-08-20
**Domain:** 双信号打分（SigLIP midframe 轨迹相似度 + qwen-eye VLM judge 归因）+ ep01 校准 + verdict 幂等写入
**Confidence:** HIGH（所有关键路径均在本机探针实测——SigLIP 离线加载/双卡 VRAM、judge grid JSON 5/5、端帧越界实测）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions（逐字，from 21-CONTEXT.md ## Implementation Decisions）

**打分对象与批渲染编排**
- Phase 21 内先跑 uniform-20 @1344×768（SC4 字面要求；smoke 2 镜不够校准；门槛锁定对正式分辨率——896×512 是验证模式）——h3_regen 客户端驱动 overnight 批
- 串行链：h3 批（GPU 满载）→ scorer（轻量）→ judge qwen-eye（13.4GB）——复用 Phase 20 显存探测编排约定
- 分两模块：`analysis/roundtrip/scorer.py` + `analysis/roundtrip/judge.py`（不同生命周期/依赖，mirror repo 每步一模块惯例）

**midframe 相似度实现（SCORE-01）**
- SigLIP so400m-patch14-384（盘上 HF cache 离线加载零下载）+ `model` 字段记录（schema 要求跨模型不可比）
- 两侧各 resample 到固定 N=8 帧 @25%-75% 时窗 → per-position cosine → mean 为主分数；DTW 留升级位
- 打分帧时间戳清单写进 cache 元数据（哪 8 帧、各自 t%——审计可回放，t=0/t=end 显式排除有据）
- transformers + `HF_HUB_OFFLINE=1` 盘 cache 加载（零下载）

**VLM judge 归因（SCORE-02）**
- 输入：原片段 vs regen 各 4 帧全时窗（0/33/66/100%——judge 判断符不符 prompt，condition 帧含信息）拼 2×4 grid 图 + prompt_text 一次调用
- 结构化输出：qwen-eye 直接输出 JSON（提示词含三分类定义 + JSON 模板）→ 本地严格校验（enum/confidence 范围/reason 长度）→ 失败重问 ≤2 次——复用 glm-structured-output 的「严格校验+重试」模式但零外部依赖
- 三分类定义逐字进提示词（prompt_faithful=描述了X且渲染出X / model_diverged=描述了X渲染成Y / prompt_underspecified=欠约束 h3 自行脑补）+ reason 要求引用 prompt 具体短语作证据
- 人工抽检：抽 5 镜 Kai 复核 judge 归因 vs 自己判断（一致率 ≥4/5 可接受；不一致镜进校准报告）——checkpoint

**阈值校准与 verdict 写入（SCORE-03, DATASET-01）**
- 双门槛：`accepted ⇔ midframe_sim ≥ τ_sim ∧ attribution == prompt_faithful`（硬合取；无 confidence 第二门槛——20 镜定两阈已勉强，加了是伪精度）
- 校准流程：20 镜散点（sim 分布 + attribution 分桶）→ Kai 看分布定 τ_sim + 理由 → PROJECT.md Key Decisions（SC4 明文）+ 校准报告 `.planning/research/roundtrip-threshold-calibration.md`（rejected 占比按归因分桶——SC4 防偏向审计）
- verdict 来源：本 phase 全部 `source: "auto"`（HITL Phase 22 覆盖写 human——schema 已预留）；decided_at 记录
- 幂等合并（SC5）：重跑 READ-merge——已存在 verdict 的镜永不覆盖（rejected 永续 + human verdict 防意外覆盖），只补缺 verdict 的镜；scores 可更新（新模型重打分）但 verdict 冻结

### Claude's Discretion
- grid 拼图实现（PIL/ffmpeg）、judge 提示词具体措辞、scorer cache 文件形状细节
- resample 帧提取的 ffmpeg 调用细节
- 校准报告排版与散点呈现方式

### Deferred Ideas (OUT OF SCOPE)
- DTW 轨迹对齐升级（校准期 mean 足够，时序错位容忍留后续）
- 双模型交叉打分（CLIP+SigLIP 一致性校验——后续质量增强）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCORE-01 | 中段帧相似度：原片段 vs regen 在 25%-75% 时窗的 SigLIP 帧 embedding 轨迹相似度；显式排除 t=0/t=end | 探针实测 SigLIP 离线加载/1152 维 pooler_output/双卡 VRAM（§SigLIP 实测）；端帧越界 guard 实测（Pitfall 3）；t=0 condition 膨胀一手数据（0.983 vs 中段 0.91-0.93） |
| SCORE-02 | VLM judge 归因三分类，结构化输出 | 探针实测 5/5 JSON parse-ok + 5/5 归因一致 + reason 引用 prompt 短语与中段帧（§Judge 实测）；grid 设计 + 解析容错函数已验证可直接落地 |
| SCORE-03 | 阈值校准 spike：ep01 ≤20 镜实测双信号分布 → 锁双门槛；rejected 占比可审计 | 真实分数量级实测（0.85-0.98 窄带）；校准报告结构 precedent（vision-seq-spike-report）；分位数表 + 分桶统计设计（§校准材料） |
| DATASET-01 | verdict 合并写 roundtrip.json；rejected 永不删除 | write_roundtrip_sidecar 现有 READ-merge 形状逐行核对 + scores/verdict 半边扩展点 + 冻结语义实现方案（§Sidecar 写入） |
</phase_requirements>

## Summary

Phase 21 的三大技术风险全部被本机探针消除。(1) SigLIP so400m：**CONTEXT「盘上 cache 零下载」的前提在权重层面是错的**——`~/.cache/huggingface/hub/models--google--siglip-so400m-patch14-384/blobs/` 里 model.safetensors 是 960MB 的 `.incomplete`（6 月 14 日中断），本研究期间已通过 hf-mirror 补全 3.51GB 并实测 `HF_HUB_OFFLINE=1` 离线加载 + 双卡 embedding 成功（fp16 峰值 ~2.0GB，batch16 0.3-0.8s）。(2) qwen-eye judge JSON 可靠性：真实 2×4 grid 图 + 三分类提示词 ×5 次实测 **5/5 一次 parse 成功、5/5 归因一致**，reason 质量高（引用 prompt 原文短语 + 按指令以 t=33%/66% 中段行为主要证据）。(3) 帧提取端点越界：regen mp4 上 `-ss` 取 t=100% 帧实测失败（175f/24fps 流末帧起始于 7.25s，7.252s 越界）——需要 `duration - 0.2s` clamp，h3_regen 的 0.04s guard 不够。

关键量化锚点：uniform-20 @1344×768 = 19 镜实渲（shot 70 被 >10s 跳过）、共 2594 h3 帧、按 smoke 每帧耗时 2-3× 外推 **overnight 批约 3-4.5h**；scorer 全程 <5min；judge 19 镜 ×1 次调用 ≈2-5s/镜 + 引擎拉起 ~2min。SigLIP 真实相似度落在 0.85-0.98 窄带（随机噪声基线 ~0.99，SigLIP 余弦天然压缩在高区）——**τ_sim 只能靠 19 镜实测分布定，不能拍脑袋**，这正好是 SCORE-03 的设计。Sidecar 写入侧：h3_regen 的 `write_roundtrip_sidecar` READ-merge 已为 Phase 21 预留 scores/verdict 保留语义（逐行核对过 L813-824），本 phase 只需加「scores 可更新 / verdict 冻结」的第二个 merge 函数。

**Primary recommendation:** 三步串行编排（overnight h3 批 → scorer @GPU0 → judge @GPU1 + 预 `/free`），scorer/judge 各自带 4-tuple 风格 cache + 打分帧清单元数据；judge 解析容错按本研究的已验证函数落地（markdown 剥离 + 花括号截取 + enum/conf/长度校验 + ≤2 次重问）；verdict 应用器读双信号 + `--tau-sim` 出 verdict，冻结语义 = 已有 verdict 的镜跳过。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| h3 批渲染（overnight） | 本地 ComfyUI 容器（GPU1 3090） | — | Phase 20 h3_regen 全链已验证；1344×768 是默认分辨率 |
| 帧提取（原片时窗 + regen 时窗） | 本地 ffmpeg 子进程 | — | repo 全部视频 I/O 走 ffmpeg 惯例；-ss 数值来自自家 JSON |
| midframe 相似度推理 | scorer.py @torch（GPU0 3060Ti 首选 / GPU1 / CPU 降级） | — | fp16 仅 ~2GB；GPU0 与 GPU1 引擎链零竞争 |
| judge 归因推理 | judge.py @qwen-eye :8125（GPU1 13.4GB lease） | — | engine_clients 生命周期 + KAP release 现成 |
| grid 拼图 | judge.py 内 PIL（本地产物） | — | 纯 CPU、确定性、带标注（列标签进图） |
| scores/verdict 持久化 | roundtrip.json sidecar（READ-merge + schema 预校验） | route_cache/{scorer,judge}/shot_XXX.json | 契约层 Phase 18 已锁；cache 是审计/断点续跑层 |
| 校准决策（τ_sim） | 人工（Kai 看分布裁决） | 校准报告 + PROJECT.md Key Decisions | HITL 硬门先例；20 镜定阈是统计上勉强的事，机器不代裁 |

## Standard Stack

### Core（零新包——全部在位实测）

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| transformers | 5.6.2 | SigLIP so400m 加载 + `get_image_features` | 已装（本会话 import 实测）[VERIFIED: local session] |
| torch | 2.6.0+cu124 | 推理后端（fp16） | 已装；双卡探测通过 [VERIFIED: local session] |
| Pillow | 12.2.0 | grid 拼图 + 标注文字 | repo 既有依赖 [VERIFIED: codebase] |
| jsonschema | 4.26.0 | verdict 写前自校验（Draft202012Validator） | h3_regen `_iter_sidecar_errors` 同款 [VERIFIED: codebase] |
| matplotlib | 3.11.1 | 校准散点 PNG（可选） | 已装 [VERIFIED: local session] |
| ffmpeg/ffprobe | 6.1.1 | 帧提取 / 时长探测 | repo 惯例 [VERIFIED: codebase] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| engine_clients.qwen_eye_client | （repo 内） | judge 引擎生命周期 + observe_single | judge.py 唯一新 import（sanctioned exception） |
| h3_regen.py 既有函数 | （repo 内） | `append_roundtrip_warnings`/`gpu_mem_mib`/`comfy_free` 复用参考 | 见 §Import 约定裁决 |

**Installation:** 无——本 phase 零新包（repo「零重依赖」约束延续；SigLIP 是模型下载不是包）。

## Package Legitimacy Audit

本 phase **不安装任何外部包**（全部依赖已在位并本会话实测版本）。无可审计条目。

**模型权重（非包）审计：** `google/siglip-so400m-patch14-384` 权重 3.51GB，来源 hf-mirror.com（huggingface.co 直连在本机不可达——curl 实测无响应，镜像 302 + `accept-ranges: bytes`）。本研究已代为补全下载（原 `.incomplete` 960MB → 完整 3.51GB，`model.safetensors` symlink 已落位）。[VERIFIED: local session]

## Architecture Patterns

### System Architecture Diagram

```
                    ┌────────────────────────────────────────────────┐
                    │  Step 0: overnight h3 批（Phase 20 既有资产）     │
                    │  h3_regen.py --work-dir <ep01> --sample-shots 20│
                    │  （默认 1344x768；896x512 smoke cache 全 miss）   │
                    │  GPU1 3090 满载 ~3-4.5h → 19 镜 regen mp4       │
                    └──────────────────────┬─────────────────────────┘
                                           │ 批完（ComfyUI 驻留 ~21GB cache）
                                           ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Step 1: scorer.py（SCORE-01）                                           │
 │  对每个 regen mp4 + 原片时窗：                                          │
 │   a. 帧清单计算：N=8，t_j = 25% + 50%·j/7（j=0..7），clamp duration-0.2s │
 │   b. ffmpeg 逐帧提取（16 帧/镜，-ss 前 -i，list-form）                  │
 │   c. SigLIP fp16 离线加载（HF_HUB_OFFLINE=1，GPU0 首选→CPU 降级）        │
 │   d. per-position cosine(1152d) → mean = midframe_sim                  │
 │  写：route_cache/scorer/shot_XXX.json（帧清单+逐位余弦+score，审计面）   │
 │  写：roundtrip.json scores.midframe_sim{score, model}（READ-merge）     │
 └──────────────────────┬─────────────────────────────────────────────────┘
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Step 2: judge.py（SCORE-02）                                            │
 │  POST ComfyUI /free（best-effort，腾 GPU1）→ qwen-eye ensure_ready      │
 │  对每镜：4+4 帧全时窗（0/33/66/100%）→ PIL 2×4 grid（列标签进图）        │
 │   → observe_single(grid, 三分类提示词+JSON 模板+prompt_text)            │
 │   → 解析容错（fence 剥离+花括号截取+enum/conf/reason 校验）→ 失败重问 ≤2  │
 │  写：route_cache/judge/shot_XXX.json（raw 答案+解析结果+重试次数）        │
 │  写：roundtrip.json scores.judge{attribution, confidence, reason}       │
 │  stop_if_owned（KAP lease 配对释放）                                     │
 └──────────────────────┬─────────────────────────────────────────────────┘
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Step 3: 校准 + verdict（SCORE-03 / DATASET-01）                         │
 │  汇编 19 镜双信号 → 分布表/散点/分位数 → 校准报告草稿                     │
 │  【checkpoint】Kai 看分布定 τ_sim（+抽 5 镜复核归因，SC3）               │
 │  judge.py --apply-verdict --tau-sim <τ>：                               │
 │   accepted ⇔ sim ≥ τ ∧ attribution == prompt_faithful                  │
 │   → verdict{decision, source:"auto", decided_at}，冻结语义 merge 写入    │
 │  → PROJECT.md Key Decisions + 报告终稿（rejected 按归因分桶占比）        │
 └────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
analysis/roundtrip/
├── h3_regen.py            # Phase 20 既有（不动，除可能的共享 helper 提取——不建议）
├── scorer.py              # 新：SCORE-01（SigLIP midframe 轨迹相似度 + 帧清单审计 cache）
├── judge.py               # 新：SCORE-02（grid 拼图 + qwen-eye 三分类）+ --apply-verdict（SCORE-03/DATASET-01 应用器）
└── workflow_fl2va.json    # 既有
tests/
├── test_scorer.py         # 新：FakeSigLIP + 帧窗数学 + 端点 guard + cache/merge
└── test_judge.py          # 新：解析容错矩阵 + FakeEye + verdict 冻结幂等
output/<ep01>/
├── route_cache/scorer/shot_XXX.json    # 帧清单 + 逐位余弦（SC2 审计面）
├── route_cache/judge/shot_XXX.json     # raw 答案 + 解析结果 + 重试审计
├── roundtrip/_judge_grids/shot_XXX.jpg # grid 图留档（抽检素材，SC3 复核用）
└── roundtrip.json                      # scores + verdict（schema 预校验 + 冻结 merge）
.planning/research/roundtrip-threshold-calibration.md   # 校准报告
```

### Pattern 1: scorer 帧清单与相似度（探针验证代码）

**What:** N=8 百分位帧 + per-position cosine + mean；帧清单进 cache（SC2 硬要求）。
**When to use:** scorer.py 主路径。

```python
# Source: 本会话探针 /tmp/probe_siglip3.py（实测通过，transformers 5.6.2 API）
import os
os.environ["HF_HUB_OFFLINE"] = "1"; os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from transformers import AutoModel, AutoProcessor

proc = AutoProcessor.from_pretrained("google/siglip-so400m-patch14-384")
model = AutoModel.from_pretrained(
    "google/siglip-so400m-patch14-384", dtype=torch.float16).to("cuda:0").eval()
with torch.no_grad():
    pv = proc(images=frames_a + frames_b, return_tensors="pt")["pixel_values"].to("cuda:0").half()
    emb = model.get_image_features(pixel_values=pv).pooler_output.float().cpu().numpy()
# ⚠️ transformers 5.x：get_image_features 返回 BaseModelOutputWithPooling，不是 tensor——
#    取 .pooler_output（(B, 1152)）；torch_dtype 参数已更名 dtype（deprecated warning 实证）
```

帧位公式（两侧同式、各自时长归一）：

```python
# t_j = 25% + 50% * j/(N-1)，j=0..7；首尾 (t=0/t=end) 结构性排除（窗口定义本身）
# 端点防越界 clamp（Pitfall 3 实测：175f/24fps 流末帧起点 7.25s，-ss 7.252 失败）：
def frame_ts(dur: float, j: int, n: int = 8, guard: float = 0.2) -> float:
    ts = dur * (0.25 + 0.5 * j / (n - 1))
    return min(ts, max(dur - guard, 0.0))
```

### Pattern 2: judge 解析容错（glm-structured-output 模式，零依赖）

**What:** markdown 剥离 → 花括号截取 → 严格校验 → 失败重问（温度降 0 + 错误回喂）。
**When to use:** judge.py。本会话 5/5 一次通过，重问路径是保险不是主路径。

```python
# Source: 本会话探针 /tmp/judge_probe/judge_probe.py（实测 5/5 parse-ok）
import json, re
def parse_judge_answer(txt: str):
    t = re.sub(r"```(?:json)?", "", txt.strip()).strip("` \n")
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None, "no-brace"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, f"json:{e.msg[:40]}"
    if obj.get("attribution") not in ("prompt_faithful", "model_diverged",
                                      "prompt_underspecified"):
        return None, "enum"
    c = obj.get("confidence")
    if not isinstance(c, (int, float)) or not (0.0 <= c <= 1.0):
        return None, "conf-range"
    r = str(obj.get("reason") or "")
    if len(r) < 10:                      # schema minLength 1；此处更严（10 字下限）
        return None, "reason-short"
    return obj, "ok"
```

reason 写 sidecar 前截 2000（schema T-18-02 上界）；校验失败重问 ≤2 次（错误信息进 prompt，mirror glm_extract 的 retry-with-feedback）。

### Pattern 3: 2×4 judge grid（PIL，标注进图）

**What:** 2 列（左 ORIGINAL / 右 REGEN-h3）× 4 行（t=0/33/66/100%）+ 列头标签 + 行时间标签。
**When to use:** judge.py。实测 27B 正确读懂列语义与行时间、reason 中引用「t=33%/66% 中段帧」。

```python
# Source: 本会话探针（grid_shot1.jpg 1370×1476，judge 5/5 正确解读标注）
# cell 640×360（16:9 等比）→ grid 1370×1476 ≈ 2.0M px ≈ 单张 1920×1080 的 token 预算
# ——vision_seq 曾以全幅 1920×1080 单图喂 observe_single 147 calls 无碍（token 预算实证锚）
canvas = Image.new("RGB", (ROWLBL_W + CELL_W*2, HDR_H + CELL_H*4), (13, 17, 23))
# 列头：ORIGINAL（蓝 #58a6ff）/ REGEN (h3)（绿 #3fb950）——GitHub-dark palette（repo CSS 惯例）
# 行标签：t=0% / t=33% / t=66% / t=100%（左侧竖排）
# ⚠️ 标签必须进图：judge 只收一张图，列语义只能靠图内文字（CONTEXT 明示）
```

### Pattern 4: verdict 冻结 merge（DATASET-01 / SC5）

**What:** scores 半边可更新（重打分自由），verdict 半边只在缺席时补写。
**When to use:** judge.py `--apply-verdict`。

```python
# 语义骨架（h3_regen.write_roundtrip_sidecar L813-824 的对偶扩展）：
for e in entries:                      # e = {shot_id, scores?, verdict?}
    sid = int(e["shot_id"])
    prev = merged.get(sid, {})
    kept = {k: v for k, v in prev.items() if k not in ("scores",)}   # regen/status/scores 之外全保留
    if "verdict" in prev:
        e.pop("verdict", None)          # 冻结：已有 verdict（auto 或 human）永不覆盖
    new_scores = e.get("scores") or {}
    merged_scores = dict(prev.get("scores") or {})
    merged_scores.update(new_scores)    # scores 子对象浅合并（scorer 只写 midframe_sim，judge 只写 judge）
    kept["scores"] = merged_scores
    kept.update({k: v for k, v in e.items() if k != "scores"})
    merged[sid] = kept
# 写前两层自校验复用 h3_regen 模式：本批 fail-loud / 预存坏条目剔除+备份
```

### Import 约定裁决（research focus #5 的「import 还是复制」）

[VERIFIED: codebase] 证据链：
- `analysis/local_vision_facets.py:57-61` 与 `vision_seq_facets.py:88-92` 均 `sys.path.insert(0, <analysis 目录>)` 后 `from engine_clients.qwen_eye_client import ...` —— **engine_clients 是唯一被 sanction 的跨模块 import**；
- `analysis/roundtrip/h3_regen.py:450` 对 qwen_eye_client 的 `_http_json` 选择**逐字 mirror 复制**而非 import（stage 脚本不互相 import 的惯例）；
- `h3_regen.py:704-721` 用 `importlib.util.spec_from_file_location` 加载 `scripts/export_asset.py` 取 SCHEMA_VERSION —— **importlib 文件加载脚本是被 sanction 的单源机制**；
- tests/ 全部用 importlib 文件位置加载被测模块（`test_h3_regen.py:64-68`）。

**推荐：**
1. `judge.py`：`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` 后 import engine_clients（mirror vision_seq，注意**深一层**——PATTERNS §F off-by-one）；
2. `scorer.py`/`judge.py` 需要的 h3_regen 共享件（`append_roundtrip_warnings` 双形 merge、`gpu_mem_mib`、`comfy_free`、`_atomic_write_json`、`_load_schema_version`）：用 **importlib 文件加载 h3_regen.py**（单源不漂移，与 export_asset 加载同机制；h3_regen 模块级无副作用、main 有 guard，加载安全），次选逐字 mirror 复制 + 注释指认源行号。**不要**为此把 h3_regen 改造成包结构（牵动 Phase 20 已验证代码）。

### Anti-Patterns to Avoid

- **把 t=0/t=end 帧混进 midframe 打分**——实测 shot1 t=0 余弦 0.983 vs 中段 0.91-0.93，condition 膨胀会让分数虚高（research Pitfall 4 一手复证）。
- **judge grid 不带列标签**——judge 无法分辨哪列是原片，归因会退化成猜（CONTEXT 明示；本探针标注进图后 reason 能明确对照「REGEN 在 t=33%/66% 中段帧中…」）。
- **scorer 跑在 GPU1 且批后不 /free**——ComfyUI 渲后 cache 驻留可达 ~21GB（post_render_free_mib=1321 实测），SigLIP 直接 OOM。
- **绝对 free 下限式的自查**——mirror h3_regen Pitfall 1 教训（20-02 决策）：scorer/judge 的显存自查要 PID 归因或干脆选零竞争 GPU0。
- **verdict 全量重写**——READ-merge 必须跳过已有 verdict 的镜（SC5 硬要求，rejected 永不删除）。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 结构化 LLM 输出 | 自创协议（XML/哨兵） | JSON 对象 + 本地校验 + 失败重问（glm-structured-output 模式） | 探针 5/5 一次通过；glm_extract 的 fence 剥离/重试形状已被两处生产验证 |
| 图像 embedding | 手卷积/直方图相似度 | SigLIP pooler_output + cosine | hist 相似度对运动/构图漂移盲；SigLIP 1152d 语义空间是学界标准做法 [ASSUMED]（但效果已被本探针的真实帧数据佐证） |
| sidecar schema 校验 | 手写形状断言 | Draft202012Validator.iter_errors | h3_regen `_iter_sidecar_errors` 现成，写前两层自校验模式已验证 |
| 引擎生命周期 | 裸 HTTP + sleep | engine_clients.QwenEye（ensure_ready/stop_if_owned/KAP release） | 13.4GB lease 无管理泄漏是已付学费的坑（WR-03 19-REVIEW） |
| warnings 双形 merge | 只写 str 或只写 dict | 复用 append_roundtrip_warnings（双形保留 + 上一轮 strip） | Pitfall 6（vision_seq 只保 str 会吞 dict 条目）已在 20-01 修过 |

**Key insight:** Phase 19/20 已把「引擎调用 + cache + sidecar + warnings」的骨架全部建好——Phase 21 的增量只在两个新信号的计算与合并，其余全部复用既有形状。

## Common Pitfalls

### Pitfall 1: SigLIP「零下载」前提不成立（已在本研究修复，planner 需知晓）
**What goes wrong:** `HF_HUB_OFFLINE=1` 离线加载直接失败（权重 blob `.incomplete`，960MB/3.51GB）。
**Why:** 6 月 14 日的下载中断，CONTEXT 的「盘 cache 零下载」只在 config/tokenizer 层成立。
**How to avoid:** 已补全（hf-mirror `hf download`，断点续传 `.incomplete` 续写）；scorer.py 载入失败时 degrade 走 `scorer_model_missing` warning（enum 已有此码），不要 sys.exit 炸批。
**Warning signs:** `LocalEntryNotFoundError` / `TypeError: not a string`（本探针初次失败的实际报错）。

### Pitfall 2: transformers 5.x API 变更
**What goes wrong:** 按 4.x 记忆写 `model.get_image_features(...)` 直接当 tensor 用 → `AttributeError: 'BaseModelOutputWithPooling' object has no attribute 'shape'`；`torch_dtype=` 参数 deprecated。
**Why:** transformers 5.6.2 返回类型改为 output 对象。
**How to avoid:** 取 `.pooler_output`（(B,1152)）；参数名用 `dtype=`。探针代码可直接抄（§Pattern 1）。

### Pitfall 3: 帧提取端点越界（实测）
**What goes wrong:** `-ss <duration>` 或接近末帧起点的精确时间戳取帧失败，产出空 jpg 或无产物。
**Why:** 175f/24fps 流时长 7.2917s，**末帧起点是 7.25s**——`-ss 7.252` 已越过；h3_regen 的 `LAST_FRAME_GUARD_SEC=0.04` 是对 h264.mp4 调的值，对 regen mp4 不够。
**How to avoid:** 百分位时间戳统一 clamp `min(ts, dur - 0.2)`（judge 全时窗 t=100% 帧同理）；提取后校验产物存在且非空（mirror extract_endpoint_frames 的 WR-05 fail-loud 形状）。
**Warning signs:** 帧清单里有缺文件；ffmpeg rc=0 但 dest 不存在。

### Pitfall 4: GPU 编排——批后驻留与 eye 启动预检
**What goes wrong:** h3 批刚结束就跑 scorer/judge 在 GPU1：ComfyUI cache 驻留 ~21GB → SigLIP OOM / qwen-eye Guard 1（free<14000MiB）拒启动。
**Why:** 20-03 实测 post_render_free_mib 低至 1321。
**How to avoid:** 串行链批后先 `POST /free`（mirror `comfy_free`）；scorer 默认 GPU0（3060Ti 4.9GB free，SigLIP fp16 峰值 2.0GB，零竞争），`--device` 可调 + OOM/不可用 → CPU 降级（batch16 CPU 量级可接受，19 镜 ≈ 分钟级）。
**Warning signs:** CUDA OOM；`[vision-engine] insufficient VRAM ... skip start`。

### Pitfall 5: SigLIP 余弦窄带——绝对阈值直觉失效
**What goes wrong:** 拿 CLIP 时代的「0.7 以上算相似」直觉定 τ_sim。
**Why:** SigLIP（sigmoid 损失）的余弦天然压缩在高区：本探针**随机噪声图对**余弦都有 0.99；真实 shot1 对（smoke 896×512）落在 0.85-0.98。
**How to avoid:** τ_sim 必须由 19 镜实测分布的分位数/散点定（正是 SCORE-03 流程）；报告里放全量分布而非只放均值；`model` 字段记录（schema 已强制——跨模型不可比）。
**Warning signs:** 19 镜分数挤在 <0.02 区间 → 考虑 per-position 分数 + 温度化呈现，或如实报告区分度不足（不私调窗口/帧数凑区分度）。

### Pitfall 6: qwen-eye 启动贴近 120s 超时上限
**What goes wrong:** `ensure_ready` 偶发超时返回 (False, True)。
**Why:** 本探针实测启动恰 120s（`LLM_START_TIMEOUT_S=120` 边缘）。
**How to avoid:** judge.py 对 (False, owned) 走一次显式重试（间隔 ≥30s）再 degrade；调用方 try/finally stop_if_owned 已是 client 契约。
**Warning signs:** ensure_ready 返回 False 且 server.log 有 load 迹象。

### Pitfall 7: cache 与分辨率/引擎身份联动
**What goes wrong:** 拿 896×512 smoke 的 regen（shots 1/47）混进 1344×768 校准集。
**Why:** h3_regen engine_version 冻分辨率——切 1344×768 后旧 cache 全 miss 重渲（这是对的）；但 roundtrip.json 里现存的 2 条 896×512 条目会被新批 READ-merge 覆盖 regen 半边，scores 若已写则保留。
**How to avoid:** 校准集 = h3_regen 批末写入的 19 条 @1344×768 条目；scorer/judge 的 cache key 要含 regen mp4 的身份（推荐 mp4 sha256 前 16 位）+ model_id + N + window。

### Pitfall 8: verdict 冻结与 h3_regen 重渲的交互
**What goes wrong:** Phase 22 重跑 h3_regen 后 verdict 丢失的担忧。
**Why:** 已核对——h3_regen `write_roundtrip_sidecar` 的 kept-keys 逻辑（L821-822: `k not in ("regen","status")`）原样保留 scores/verdict；`--force` 走 `strip_sidecar_regen_half` 同样只剥 regen/status。**现有代码已正确**，Phase 21 的 merge 不要破坏该对称性（Pattern 4 的 kept 逻辑是其对偶）。
**How to avoid:** judge verdict 应用器的单测必须含「预存 verdict + h3_regen 风格重写 regen 半边 → verdict 原样」双向用例。

## Code Examples

### ffmpeg 帧提取（repo 惯例 + 端点 guard）
```python
# Source: h3_regen.extract_endpoint_frames 形状（L407-416）+ 本会话 regen 端点实测修正
proc = subprocess.run(
    ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", video, "-frames:v", "1",
     "-q:v", "2", dest, "-loglevel", "error"],
    capture_output=True, timeout=60)
# ts 已 clamp dur-0.2；全 list-form（-ss 数值来自自家 shots.json/ffprobe，无 shell 拼接）
```

### scorer cache 元数据形状（SC2 审计面，Claude's discretion 区的推荐）
```json
{
  "video_content_hash": "ece64d62bcbc534a",
  "regen_mp4_sha256_16": "<hex16>",
  "model": "siglip-so400m-patch14-384",
  "model_impl": "transformers-5.6.2",
  "n_frames": 8, "window": [0.25, 0.75],
  "device": "cuda:0",
  "frames": {
    "orig":  [{"j": 0, "t_pct": 25.0, "t_sec": 1.683, "path": "..."}],
    "regen": [{"j": 0, "t_pct": 25.0, "t_sec": 1.823, "path": "..."}]
  },
  "per_position_cos": [0.947, 0.932, 0.914, 0.901, 0.893, 0.878, 0.861, 0.846],
  "score": 0.902,
  "scored_at": "2026-08-21T02:17:44"
}
```

### judge cache 元数据形状
```json
{
  "video_content_hash": "ece64d62bcbc534a",
  "regen_mp4_sha256_16": "<hex16>",
  "engine_name": "qwen-eye", "engine_version": "qwen3.8-27b-q3@c3949404",
  "grid": {"path": "roundtrip/_judge_grids/shot_001.jpg", "w": 1370, "h": 1476},
  "attempts": [{"parse": "ok", "raw_len": 312}],
  "parsed": {"attribution": "prompt_faithful", "confidence": 0.85,
             "reason": "prompt 要求'独角仙武士弯腰把一颗红浆果递给…'…"},
  "judged_at": "2026-08-21T02:31:09"
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| transformers 4.x `get_image_features` 返回 tensor | 5.x 返回 `BaseModelOutputWithPooling`（取 `.pooler_output`） | transformers 5.x（本机 5.6.2 实证） | scorer 必须用新 API；`torch_dtype`→`dtype` |
| CLIP ViT-L/14 做帧相似度 | SigLIP so400m（sigmoid 损失，更强对齐） | 2023 发表后成为主流选择 [ASSUMED] | 余弦窄带特性改变阈值语义（Pitfall 5）；CLIP ViT-L/14 本机 cache 同样无权重（不可作 fallback） |

**Deprecated/outdated:** 本机无 CLIP 可用权重（snapshot 只剩 tokenizer 件）——不要计划 CLIP 交叉验证（那是 Deferred 的双模型升级位，且需再下载）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SigLIP 是帧轨迹相似度的正确模型选择（相对 DINOv3/CLIP） | Standard Stack | 若 DINOv3 纯视觉特征更优也只影响分数分布形态，不阻塞（CONTEXT 已锁 SigLIP；DINOv3 本机同样无权重） |
| A2 | 1344×768 渲染每帧耗时 = smoke 896×512 的 2-3×（外推 3-4.5h） | Summary | 偏差只影响 overnight 时长预期，h3_regen 断点续跑兜底 |
| A3 | judge 温度 0.1 下 5/5 一致可外推到 19 镜（总有边缘镜） | Judge 实测 | 低——重问 ≤2 + 抽检 5 镜兜底；校准报告本就要记录不一致 |
| A4 | SigLIP 高窄带意味着 τ_sim 区分度可能不足 | Pitfall 5 | 若 19 镜分布无区分度，校准报告如实呈现并回 Kai 裁决（可能触发窗口/粒度调整讨论）——不是静默改参数 |
| A5 | grid cell 640×360 足够 judge 辨细节 | Pattern 3 | 若抽检发现细节盲，升 cell 到 896 宽（grid ~1836×2072 仍在 token 预算边缘，需重验） |

## Open Questions (RESOLVED)

1. **verdict 应用器放哪个模块** — [RESOLVED → 21-01-T2: judge.py --apply-verdict --tau-sim 落地]
   - What we know: CONTEXT 锁两模块（scorer.py + judge.py）；verdict 应用需要双信号齐备 + τ_sim。
   - What's unclear: 逻辑归属（judge 的 attribution 是 verdict 半边信号 → 放 judge.py `--apply-verdict --tau-sim` 最顺）。
   - Recommendation: judge.py 承载（本研究的结构图按此画）；planner 可改为 scorer.py 或独立小脚本，不破坏 SC。
2. **19 镜分数区分度不足时怎么办** — [RESOLVED → 21-03-T2 blocking checkpoint 回 Kai 裁决，禁静默调参]
   - What we know: SigLIP 窄带（Pitfall 5）+ 19 镜小样本。
   - What's unclear: 分布实测前无法预知。
   - Recommendation: 校准报告必含 per-position 分布与分位数全表；区分度不足 → checkpoint 回 Kai 裁决（选项：调 N、调窗口、换特征层），不静默自调。
3. **`_judge_grids/` 目录位置** — [RESOLVED → 校准材料含 _judge_grids/，21-03-T2 抽检用]
   - What we know: grid 图是 SC3 抽检素材，须留档；roundtrip/ 下已有 `_compare/` 先例（20-03 目视抽检）。
   - What's unclear: 无——`roundtrip/_judge_grids/` 与 `_compare/` 对齐即可，此处只是确认。
   - Recommendation: `output/<ep01>/roundtrip/_judge_grids/shot_XXX.jpg`。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| SigLIP so400m 权重 | scorer | ✓（本研究补全 3.51GB，离线加载实测过） | snapshot 9fdffc58 | degrade：`scorer_model_missing` warning + sidecar 缺 scores（RT-04） |
| transformers | scorer | ✓ | 5.6.2 | — |
| torch CUDA | scorer | ✓ 双卡 | 2.6.0+cu124 | CPU 降级（分钟级/19 镜） |
| qwen-eye :8125 | judge | ✗ down（本探针停掉；client 自管拉起，实测 120s 起） | qwen3.8-27b-q3 | ensure_ready 失败 → degrade + 重试 1 次 |
| ComfyUI :8188 | h3 批 + judge 前 /free | ✓ up（本会话 200） | 0.30.0 | h3 批 degrade 已有 |
| GPU0 3060 Ti | scorer 默认位 | ✓ 4.9GB free（SigLIP 需 ~2.0GB） | — | GPU1（批后 /free）或 CPU |
| GPU1 3090 | h3 批 + judge | ✓ 22.5GB free（此刻） | — | 串行链兜底 |
| ffmpeg/ffprobe | 帧提取 | ✓ | 6.1.1 | — |
| matplotlib | 校准散点（可选） | ✓ | 3.11.1 | markdown 表 + 文本直方图（零依赖） |
| hf-mirror.com | （权重已就位，不再需要） | ✓ 302 + ranges | — | — |

**Missing dependencies with no fallback:** 无。
**Missing dependencies with fallback:** qwen-eye down 是常态（client 生命周期自管）。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3（无配置文件——repo 惯例裸跑） |
| Config file | none（tests/ 平铺；importlib 文件位置加载被测模块） |
| Quick run command | `python3 -m pytest tests/ -q` |
| Full suite command | `python3 -m pytest tests/ -q`（当前基线 **119 passed 3.44s**，本会话实跑） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-01 | 帧窗数学：t_j 落 [25%,75%]、t=0/t=end 结构性排除、dur-0.2 clamp 生效 | unit | `python3 -m pytest tests/test_scorer.py -q` | ❌ Wave 0 |
| SCORE-01 | FakeSigLIP（固定 1152d 向量替身）→ per-position cos + mean 数值断言 | unit | 同上 | ❌ Wave 0 |
| SCORE-01 | cache：4-tuple 风格 key miss/hit；帧清单字段齐（SC2 审计） | unit | 同上 | ❌ Wave 0 |
| SCORE-01 | SigLIP 不可加载 → `scorer_model_missing` warning + rc=0（RT-04） | unit | 同上 | ❌ Wave 0 |
| SCORE-02 | 解析容错矩阵：干净 JSON / ```json fence / 前后散文 / 尾逗号坏 JSON / 非法 enum / conf 越界 / reason 过短 → 各 verdict 码 | unit | `python3 -m pytest tests/test_judge.py -q` | ❌ Wave 0 |
| SCORE-02 | FakeEye（observe_single 回放预设文本）→ 重问 ≤2 次 + 错误回喂 prompt 断言 | unit | 同上 | ❌ Wave 0 |
| SCORE-02 | grid 拼图：2×4 布局断言（尺寸、列/行标签像素存在）——纯 PIL，零 GPU | unit | 同上 | ❌ Wave 0 |
| SCORE-03 | 分位数表/分桶统计函数：已知 19 值输入 → 精确分位数与 rejected 占比 | unit | 同上（或校准报告汇编器所在模块） | ❌ Wave 0 |
| DATASET-01 | verdict 冻结幂等：预存 verdict 镜重跑 --apply-verdict → 原样；缺 verdict 镜补写 | unit | `python3 -m pytest tests/test_judge.py -q` | ❌ Wave 0 |
| DATASET-01 | scores 半边浅合并：scorer 写 midframe_sim 不丢 judge 子对象（及反向） | unit | 同上 | ❌ Wave 0 |
| DATASET-01 | 写前两层自校验：本批坏 fail-loud；预存坏剔除+备份（mirror h3_regen WR-04 用例） | unit | 同上 | ❌ Wave 0 |
| DATASET-01 | schema gate：含 scores+verdict 全字段条目过 roundtrip.schema Draft202012Validator | unit | 同上 | ❌ Wave 0 |
| SC1/SC3/SC4 | 2 镜真 GPU scorer+judge smoke（SigLIP 真 embed + 真 grid + qwen-eye 真判）→ 人工抽检 | manual+GPU | 见下 GPU smoke 步骤 | n/a |
| SC2 | 19 镜批后 roundtrip.json 全量 schema 校验 + 帧清单抽查 | integration | `python3 -c "from jsonschema import Draft202012Validator; ..."`（或复用 validate.py V13） | n/a |

**GPU smoke（唯一真 GPU 验证步，预算 ~15-25min）**：对既有 2 镜 896×512 smoke regen（shots 1/47，已在盘）直接跑 scorer + judge —— 不等 overnight 批即可先行验证全链（cache key 含 regen 身份，1344×768 批后再自然重打分）。**抽检 5 镜（SC3 checkpoint）**在 overnight 批完成后、τ_sim 裁决前做：`roundtrip/_judge_grids/` 素材 + regen/orig 并排呈现给 Kai。

**校准 checkpoint 流程（SC4）**：汇编分布 → 报告草稿（含 τ_sim 候选分位数表 + rejected 分桶预演）→ Kai 裁决 τ_sim + 抽检归因 → `--apply-verdict --tau-sim <τ>` → PROJECT.md Key Decisions + 报告终稿。

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -q`（3.4s，全跑不挑）
- **Per wave merge:** 同上（全套即快套）
- **Phase gate:** 全套绿 + 2 镜 GPU smoke 产物 schema 过 + checkpoint approved 后才 `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_scorer.py` — FakeSigLIP + 帧窗数学 + cache + degrade（SCORE-01）
- [ ] `tests/test_judge.py` — 解析容错矩阵 + FakeEye 重问 + grid 布局 + verdict 冻结/合并/schema（SCORE-02/03, DATASET-01）
- [ ] 框架已装（pytest 9.0.3，119 passed 基线）——无安装步

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | 本地无鉴权引擎（:8125/:8188 环回）——网络边界外不适用 |
| V3 Session Management | no | 无会话概念 |
| V4 Access Control | no | 单用户本地批任务 |
| V5 Input Validation | yes | jsonschema enum/range/maxLength（attribution 三值闭集、confidence [0,1]、reason ≤2000）；prompt_text 只进 HTTP JSON body 不进 argv（T-20-01 延续）；-ss 数值来自自家 shots.json（list-form subprocess） |
| V6 Cryptography | no | 无新加密需求（sha256 仅作 cache key） |
| V12 File/Resource | yes | 帧/grid 路径全部自家构造（shot_id 格式化）；ffmpeg 全 list-form；下载产物 `.part`+os.replace 原子性已在 Phase 20 建立，本 phase 无新下载面 |

### Known Threat Patterns for 本 phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| judge.reason / model 输出文本注入下游渲染 | Tampering/Spoofing | schema maxLength 2000 已 bound；写 sidecar 前 `str()[:2000]`；HTML `_esc()` 属 Phase 22 PRESENT-01（已记录契约） |
| prompt_text 经 shell 注入 ffmpeg | Injection | 全 list-form subprocess（repo 既有惯例，h3_regen 同款审计通过） |
| 假 grid 图误导 judge（标签被裁/列序错） | Spoofing | grid 布局进单测（标签像素断言）；列序固定 orig 左 regen 右 |
| 校准数据被静默偏向（Pitfall 5 of v1.3 research） | Repudiation | rejected 占比按归因分桶进校准报告（机器可 grep 的 schema enum）+ PROJECT.md 决策行 |

## Sources

### Primary (HIGH confidence)
- 本会话探针（全部一手实测）：`/tmp/probe_siglip*.py`（SigLIP 离线加载/双卡 VRAM/真实帧余弦）、`/tmp/judge_probe/judge_probe.py + grid_shot1.jpg`（judge JSON 5/5）、regen 端点 ffmpeg 越界实测
- [VERIFIED: codebase] `analysis/roundtrip/h3_regen.py`（sidecar READ-merge L779-867 / VRAM guard / cache / warnings 双形 / uniform_sample L340-349）
- [VERIFIED: codebase] `analysis/engine_clients/qwen_eye_client.py`（生命周期契约 / observe_single / enable_thinking:false / 硬约束）
- [VERIFIED: codebase] `spec/schemas/roundtrip.schema.json`（scores/verdict 全形状 + attribution enum + maxLength 上界）
- [VERIFIED: codebase] `.planning/research/SUMMARY.md` §5 Pitfalls 1-6（v1.3 立项研究）
- [VERIFIED: codebase] `.planning/research/vision-seq-spike-report.md`（qwen-eye 4-5s/call、1920×1080 单图 147 calls、报告结构 precedent）
- [VERIFIED: codebase] `.planning/phases/20-h3-regen-client/20-03-SUMMARY.md`（smoke 计时、post_render_free_mib=1321、_compare 先例）
- [VERIFIED: codebase] ep01 live 数据：shots.json 93 镜 / roundtrip.json 2 条 896×512 / h264.mp4 1920×1080 30fps / prompts.json prompt_text

### Secondary (MEDIUM confidence)
- hf-mirror.com resolve HEAD（302 + content-length 3.51GB + accept-ranges——下载通道实证）
- transformers 5.6.2 运行时行为（本机 pip 安装版本的实测，非官方文档对照）

### Tertiary (LOW confidence)
- [ASSUMED] SigLIP 相对其它 embedding 模型的优劣排序（训练知识，未检索文献）；已用真实帧数据佐证可用性

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 零新包，全部在位且本会话实测
- Architecture: HIGH — 复用形状逐行核对 + 探针端到端跑通（SigLIP embed + judge grid→JSON 全链）
- Pitfalls: HIGH — 8 条中 6 条有本会话一手实测证据，其余 2 条有 repo 文档锚点

**Research date:** 2026-08-20
**Valid until:** 2026-09-19（本地环境稳定；权重/引擎版本若变动需重验）

**环境变更披露（本研究期间做的两处环境写入，非 repo 写入）：**
1. 补全 SigLIP 权重下载（`~/.cache/huggingface/hub/models--google--siglip-so400m-patch14-384/`，`.incomplete` 960MB → 完整 3.51GB，经 hf-mirror）——正是 Phase 21 需要的资产， planners 无需重复执行；
2. `/tmp/` 下探针脚本与 grid 素材（临时产物，随 /tmp 生命周期）。
