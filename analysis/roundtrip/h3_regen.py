#!/usr/bin/env python3
"""h3 复现客户端（Phase 20 / REGEN-01/03/04）—— kst 直连 ComfyUI 原生 API，不经 subagent/KAP/kmc。

背景
----
闭环数据集的复现半边：对每镜 (首帧, 尾帧, prompt_text) 用 MiniMax H3 fl2va
重新生成一段 mp4（roundtrip/shot_XXX_regen.mp4），供 Phase 21 scorer 与原片段
比对打分。提交协议是 ComfyUI 原生 HTTP（/upload/image → /prompt → /history →
/view），HTTP 轮询 crash-safe（kmc v4 骨架；只走短连接轮询，不建长连接通道）。

算法步骤
--------
1. 载入 shots.json（分割权威镜列表）+ prompts.json（按 shot_id join prompt_text）；
2. ComfyUI 可达性 gate（GET /system_stats 非 200 → 结构化 warning + exit 0，
   graceful-degrade）——标准序第一位（ComfyUI down 时先降级退出，不白杀 TTS、
   不空轮 eye lease，**更不执行 --force 破坏性清除**——CR-02：引擎确认可用
   之前 cache/产物/sidecar 一个字节都不动）；
3. --force 时显式清单清除本 step 的 cache 与产物（gate 之后才执行）；
4. 批开始 VRAM guard 五步固定序（kill TTS → /free → eye 等待 → /free → 严格
   gate，见下「VRAM guard 语义」）；
5. 批循环逐镜：每镜提交前 PID 归因复查 → 4-tuple cache 预判 → miss 则 ffmpeg
   全分辨率提取首/尾帧 → curl POST /upload/image ×2 → deepcopy
   workflow_fl2va.json 模板并注入节点参数（14/15 帧名、20 prompt/width/height/
   length、30 seed、50 prefix）→ POST /prompt → 轮询 /history/{prompt_id} →
   /view 下载 mp4 → cache 写入（含渲后水位 post_render_free_mib）；
6. 收尾：roundtrip.json regen 半边写入（Open Q2 裁决——READ-merge 保留
   Phase 21 未来 scores/verdict 字段 + Draft202012Validator 写前自校验，
   cache-hit 镜从 cache meta 重建条目保证断点续跑后 sidecar 完整）→
   flush 本轮 warnings（跳镜 str / 失败摘要）+ summary print。

graceful-degrade 语义
---------------------
ComfyUI 不可达 / 单镜渲染失败 / 单镜超时都不阻塞：引擎级降级 exit 0（资产照常，
[warnings] 记 {code: "comfyui_unreachable"}）；单镜级失败进 failed 清单后 continue。

VRAM guard 语义（REGEN-03，20-02）
---------------------------------
批开始五步固定序（CONTEXT 字面，顺序不可换）：
  ① ss -tlnp 端口→PID 归因找 TTS 监听（:5110 IndexTTS / :5111 VoiceDesign），
     有则 os.kill(SIGTERM) 定向 kill（绝不宽 pattern pkill；ss 探测失败才回退
     pkill -f 两个精确脚本名），kill 前后各一条审计 warning
     （code=vram_insufficient——三码 closed enum 约束下的事件记因，detail 含
     pid/端口/进程名）；确认无监听则不 kill、仍记 after 审计 warning（no-op 安全）；
  ② POST /free（kill 后第一次）；
  ③ eye 串行等待：used=total-free ≥13721MiB 视为 qwen-eye lease 在跑 → 15s
     轮询至 --vram-wait-timeout（超时 → vram_insufficient + exit 0）；
  ④ POST /free（批开始前第二次——「kill 后与批开始前各一次」）；
  ⑤ 严格 gate：free < 22528MiB（22GB）→ vram_insufficient warning（detail 含
     当前 free + compute-apps top 占用者 pid/进程名/MiB）+ exit 0。
music3 常驻 676MiB 属正常态——kill 后实测 free≈22539，22.5GB 仍过线（Pitfall 9）。

每镜提交前复查走 PID 归因（Pitfall 1 反自锁）：基线 = guard 完成后
compute-apps 全部 PID ∪ comfyui-primary 容器主 PID（docker inspect，
best-effort 失败忽略）；当前 compute-apps 中不在基线的 foreign PID Σused
≥4096MiB 才等待/终止——ComfyUI 自身渲后 cache 驻留（可达 ~18GB）在基线内，
永不自锁；渲后水位以 post_render_free_mib 留档进 cache 元数据（Open Q1 数据）。
全部读数 fail-open（qwen 先例）：nvidia-smi/ss 不可得时不阻塞，但 gate 判定
本身保守——有读数即严判。

cache 惯例
----------
- 元数据 work_dir/route_cache/h3_regen/shot_{NNN}.json（4-tuple：video_content_hash
  + engine_name + engine_version + prompt_version；另存 prompt_id/seed/length/
  width/height/mp4_sha256/rendered_at），与 mp4 实体分离；
- hit = 4-tuple 全等 + mp4 存在且 size>1KB +（meta 存档时）mp4_sha256 一致
  + length 与当前 duration 网格值一致（CR-01：半截/外改产物拒绝命中；
  WR-02：重分割边界漂移即重渲。不做 ffprobe 深检——编码级损坏由
  Phase 21 scorer 自然暴露）；下载走 .part + os.replace 原子落位；
- prompt_version = sha256(该镜 prompt_text)[:8]（per-shot，改一字即重渲该镜）；
- engine_version 冻结 model+sampler+scheduler+steps+resolution
  （"fl2va-int8/euler+simple/15/{W}x{H}"），cache 不设第 5 维。

warnings 双形交互（Pitfall 6）
-----------------------------
route_cache/warnings.json 合法元素是 str（legacy）或 {code, detail}（v1.3 加宽，
code ∈ comfyui_unreachable/vram_insufficient/scorer_model_missing）。本模块自带
的双形 merge 两种都保留；但 vision_seq 的读法只保留 str 元素——若其后重跑，
本模块写入的 dict 条目会被 strip。这不是数据丢失边界（[roundtrip] 条目本就按
「上一轮」语义每次 strip 重写），但 operator 应知道该交互存在。

roundtrip.json sidecar（20-03 / Open Q2 裁决）
----------------------------------------------
批末写 regen 半边（Phase 18 契约的运行时兑现）：rendered 镜 → {shot_id,
regen{path, video_content_hash, engine_name, engine_version, prompt_version,
duration_sec, width, height}}；failed 镜 → {shot_id, status{state:"failed",
error}}；未尝试（抽样外/跳过）→ 条目缺席（schema 是结果集不是任务队列）。
scores/verdict 本 phase 不写——schema 明文合法 degrade 中间态，Phase 21
增量补齐。READ-merge 按 shot_id 只替换 regen/status 半边，既有条目的其它
键原样保留（不给 Phase 21 留全量重写负担）；写前 Draft202012Validator
全量自校验，有错 sys.exit 不落盘。schema_version 从 scripts/export_asset.py
importlib 加载单源（绝不复制字面量）。

argv 用法
---------
    python3 analysis/roundtrip/h3_regen.py --work-dir output/<video-stem>/ \
        [--comfy-url http://127.0.0.1:8188] [--gpu-index 1] \
        [--vram-wait-timeout 1800] [--sample-shots 20] [--max-shot-sec 10] \
        [--regen-resolution 896x512] [--force] [--shot-timeout 0]

抽样与降载语义（REGEN-04，20-02）
---------------------------------
- --sample-shots N：均匀间隔抽样（确定性，无随机）：pos = {int(i*N/n)} 0-based
  去重保序映射回升序全镜 ids；n≥N → 全镜。**抽样在 >10s 过滤之前做**（对全镜
  列表等距——代表性不被过滤顺序扭曲；ep01 锚点：93 镜 N=20 → shot 70 落样后
  被 max-shot-sec 跳过 → 实渲 19）。
- --max-shot-sec（默认 10）：duration 超限镜跳过 + str warning + skipped.json
  条目 {shot_id, reason, duration_sec}（route_cache/h3_regen/ 下，READ-merge
  重跑替换同 shot_id；--force 清 cache 目录时一并清掉）。
- --regen-resolution（默认 1344x768，降档 896x512 严格 7:4）：parse +
  validate（%32 / 7:4 / ≤MAX_PIXELS）失败中文报错退出；分辨率冻进
  engine_version —— 切分辨率 = 旧 cache 整体失效换渲染配置全集重渲（Q3 裁决）。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ─── 模块级常量 ─────────────────────────────────────────────────────────────

# ComfyUI 原生 API 基址（comfyui-primary 容器，本机环回，无鉴权）。
COMFY_URL_DEFAULT = "http://127.0.0.1:8188"

# cache 4-tuple 之二：引擎身份。model+sampler+scheduler+steps+resolution 全部
# 冻进版本串（Q3 裁决）——改任一渲染参数即整体 cache 失效，无需第 5 维。
ENGINE_NAME = "comfyui-fl2va"
ENGINE_VERSION_TEMPLATE = "fl2va-int8/euler+simple/15/{width}x{height}"

# 本 plan 固定默认渲染分辨率（1920x1080 源 → adaptH3Canvas → 1344x768）。
DEFAULT_WIDTH = 1344
DEFAULT_HEIGHT = 768

STEP_TAG = "[roundtrip]"

# RT-04：[roundtrip] degrade 记因的结构化 warnings code closed enum（与
# scripts/export_asset.py:_ROUNDTRIP_WARNING_CODES / asset.schema 逐字对齐）。
_ROUNDTRIP_WARNING_CODES = (
    "comfyui_unreachable",
    "vram_insufficient",
    "scorer_model_missing",
)

# fl2va 帧率与 length 网格（object_info + KAP H3_CONSTANTS 双源一致）：
# 合法帧数 n 满足 n%17==5 且 124<=n<=362（训练区间，短镜保底 124、长镜 cap 362）。
FPS = 24
LENGTH_MIN = 124
LENGTH_MAX = 362
LENGTH_STEP = 17
LENGTH_MOD = 5

# 尾帧时间戳前移量（秒）——防 end_sec 恰在片尾时 -ss 越界取不到帧。
LAST_FRAME_GUARD_SEC = 0.04

# 产物有效性下限（kmc v4 同款 >1000 量级；拒绝空/截断 mp4 进 cache）。
MIN_MP4_BYTES = 1024

# KAP H3_CONSTANTS.MAX_PIXELS（1344x768）——分辨率合法性预算上界。
MAX_PIXELS = 1032192

# workflow 模板注入点节点 id（与 workflow_fl2va.json 键一一对应）。
NODE_FIRST = "14"      # LoadImage 首帧
NODE_LAST = "15"       # LoadImage 尾帧
NODE_I2V = "20"        # MiniMaxH3ImageToVideo（prompt/width/height/length）
NODE_SAMPLER = "30"    # KSampler（seed；steps/cfg/sampler/scheduler 模板已锁定）
NODE_SAVE = "50"       # SaveVideo（filename_prefix）

# 模板数据文件（与本模块同目录；数据与代码分离）。
TEMPLATE_PATH = Path(__file__).resolve().parent / "workflow_fl2va.json"

# roundtrip.json 写前自校验目标 schema（Phase 18 契约）。**三层 parent**：本模块
# 在 analysis/roundtrip/ 下，比 analysis/vision_seq_facets.py 深一层——repo root
# 必须 parent.parent.parent（off-by-one 陷阱，PATTERNS §F 已标）。
SCHEMA_PATH = (Path(__file__).resolve().parent.parent.parent
               / "spec" / "schemas" / "roundtrip.schema.json")

# SCHEMA_VERSION 单源位置（scripts/export_asset.py:SCHEMA_VERSION）——importlib
# 加载取属性，绝不在本模块复制字面量（STATE 载明单源纪律）。
_SCHEMA_VERSION_SOURCE = (Path(__file__).resolve().parent.parent.parent
                          / "scripts" / "export_asset.py")

# 轮询节奏（kmc v4 crash-safe 骨架：sleep 15s + 瞬态异常 continue）。
POLL_INTERVAL_SEC = 15
POLL_LOG_EVERY_SEC = 60

# ─── VRAM guard / GPU 编排常量（20-02 / REGEN-03）──────────────────────────
# GPU index 可配（默认 1 = comfyui-primary 所在 3090；NVIDIA_VISIBLE_DEVICES=1 实证）。
VRAM_GPU_INDEX_DEFAULT = 1
# 批开始严格 gate：kill TTS + 双 /free 之后 free < 22528MiB（22GB）拒整批。
# 实测锚点：kill 后 free≈22539——music3 常驻 676MiB 属正常态，22.5GB 仍过线（Pitfall 9）。
BATCH_MIN_FREE_MIB = 22528
# qwen-eye lease 显存水位（13.4GB，qwen_eye_client 注释实证）：批开始 used ≥ 此值
# 视为 eye lease 在跑 → 轮询等待而非提交（「显存探测即编排信号」，CONTEXT 锁定）。
EYE_LEASE_MIB = 13721
# 每镜复查 foreign 阻塞阈值：不在基线的 PID 合计占用 ≥ 4GB 才等待/终止。
FOREIGN_BLOCK_MIB = 4096
# guard 轮询节奏（秒）。
GUARD_POLL_SEC = 15
# TTS 监听端口（IndexTTS :5110 / VoiceDesign :5111，p11b validated）。
TTS_PORTS = (5110, 5111)
# ss 探测失败时的 pkill 回退 pattern——精确到两个脚本名，绝不宽 pattern（T-20-05）。
TTS_FALLBACK_PATTERNS = ("voicedesign_server.py", "indextts25-server.py")
# ComfyUI 容器名（docker inspect 取主 PID 并进每镜复查基线）。
COMFY_CONTAINER = "comfyui-primary"


# ─── 基础 hash / 模板 ───────────────────────────────────────────────────────

def video_content_hash(video_path: str) -> str:
    """sha256(first_1MB + last_1MB + str(filesize))[:16] —— mirror
    analysis/call_shot_analysis.py:91-108（repo 权威实现；multi-GB 视频毫秒级、
    确定性 cache key）。"""
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))                    # head 1MB
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)             # 跳到尾部前 1MB
            h.update(f.read(1024 * 1024))                # tail 1MB
    h.update(str(size).encode())                         # 文件大小参与 hash
    return h.hexdigest()[:16]


def load_template() -> dict:
    """载入 fl2va workflow 模板（纯数据；调用方 deepcopy 后注入，绝不改磁盘文件）。"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_engine_version(width: int, height: int) -> str:
    """engine_version 串（cache 4-tuple 之一）：分辨率并入（Pitfall 7——
    sampler/scheduler/steps/model 全冻结，切分辨率即整体失效）。"""
    return ENGINE_VERSION_TEMPLATE.format(width=width, height=height)


# ─── 帧数网格 / seed / 分辨率 ───────────────────────────────────────────────

def h3_frame_count(duration_sec: float, fps: int = FPS) -> int:
    """duration×fps → 17k+5 网格上的最近合法值（ceil-on-grid），再 clamp 到
    训练区间 [124, 362]。124 与 362 本就在网格上（17*7+5 / 17*21+5），
    clamp 不破网格。短镜保底 124。"""
    n = round(duration_sec * fps)
    while n % LENGTH_STEP != LENGTH_MOD:
        n += 1
    return max(LENGTH_MIN, min(n, LENGTH_MAX))


def derive_seed(vch: str, shot_id: int) -> int:
    """确定性 seed：int(sha256(f"{vch}:{shot_id}")[:8], 16) % 2**31。
    跨进程确定（绝不用 hash()——PYTHONHASHSEED 随机化，kmc Pitfall）、
    异镜异 seed；值进 cache 元数据可追溯。"""
    digest = hashlib.sha256(f"{vch}:{shot_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2 ** 31)


def parse_resolution(s: str) -> tuple[int, int]:
    """'WxH' → (w, h)。非法输入（缺 x / 非整数 / 非正）直接 sys.exit 中文报错。"""
    try:
        w_s, h_s = str(s).lower().split("x", 1)
        w, h = int(w_s), int(h_s)
        if w <= 0 or h <= 0:
            raise ValueError
    except ValueError:
        sys.exit(f"{STEP_TAG} 非法分辨率 {s!r}：应为 WxH 形式（如 1344x768 / 896x512）")
    return w, h


def validate_resolution(width: int, height: int) -> bool:
    """分辨率合法性：两轴 %32==0（CANVAS_MULTIPLE）+ 严格 7:4（w*4==h*7，
    保 CLIP 比对信号）+ 面积 <= MAX_PIXELS（token 预算安全线）。"""
    return (width % 32 == 0 and height % 32 == 0
            and width * 4 == height * 7
            and width * height <= MAX_PIXELS)


# ─── 输入装配 ───────────────────────────────────────────────────────────────

def load_shot_prompts(work_dir: str) -> tuple[list[dict], list[str]]:
    """读 shots.json（分割权威镜列表）+ prompts.json（顶层是 list，按 shot_id
    join 出 prompt_text）。缺 prompt_text（或 prompts.json 无该镜条目）的镜
    跳过并产 str warning（事件性说明走 legacy str 形，永远合法）。"""
    with open(os.path.join(work_dir, "shots.json"), encoding="utf-8") as f:
        shots = json.load(f)
    with open(os.path.join(work_dir, "prompts.json"), encoding="utf-8") as f:
        prompts = json.load(f)
    text_by_sid: dict[int, str] = {}
    if isinstance(prompts, list):
        for p in prompts:
            if isinstance(p, dict) and isinstance(p.get("shot_id"), int):
                text_by_sid[p["shot_id"]] = str(p.get("prompt_text") or "")
    out: list[dict] = []
    warnings: list[str] = []
    for s in shots:
        sid = int(s["id"])
        text = text_by_sid.get(sid)
        if text is None or not text.strip():
            warnings.append(f"{STEP_TAG} shot {sid}: prompts.json 缺 prompt_text，跳过该镜")
            continue
        out.append({
            "id": sid,
            "start_sec": float(s.get("start_sec", 0.0)),
            "end_sec": float(s.get("end_sec", 0.0)),
            "duration": float(s.get("duration", 0.0)),
            "prompt_text": text,
        })
    return out, warnings


def resolve_source_video(work_dir: str) -> str:
    """源视频解析：h264.mp4 优先（AV1 转码稳定版），缺席回退 video.mp4；
    都没有 sys.exit（没有源视频本 step 无法工作——非 degrade 语境）。"""
    for name in ("h264.mp4", "video.mp4"):
        cand = os.path.join(work_dir, name)
        if os.path.isfile(cand):
            return cand
    sys.exit(f"{STEP_TAG} 找不到源视频：{work_dir}/h264.mp4 与 video.mp4 均不存在")


# ─── 抽样 / 跳镜 / 降载（REGEN-04，20-02）──────────────────────────────────

def uniform_sample(shot_ids: list[int], n: int) -> list[int]:
    """均匀间隔抽样（确定性、无随机）：pos = {int(i*N/n) for i in range(n)}
    （0-based 去重保序）→ 映射回升序 ids。n ≥ N 或 n ≤ 0 → 全镜。
    ep01 锚点（RESEARCH 实算复现）：93 镜 n=20 →
    [1,5,10,14,19,24,28,33,38,42,47,52,56,61,66,70,75,80,84,89]。"""
    ids = sorted(shot_ids)
    if n <= 0 or n >= len(ids):
        return ids
    pos = sorted({int(i * len(ids) / n) for i in range(n)})
    return [ids[p] for p in pos]


def _skipped_path(work_dir: str) -> str:
    """>10s 跳镜清单路径（route_cache/h3_regen/skipped.json）。"""
    return os.path.join(work_dir, "route_cache", "h3_regen", "skipped.json")


def write_skipped_entry(work_dir: str, shot_id: int, reason: str,
                        duration_sec: float) -> None:
    """skipped 清单 READ-merge 写入：重跑替换同 shot_id 条目（幂等），
    按 shot_id 排序原子写。--force 清 route_cache/h3_regen/ 时一并清掉。"""
    try:
        with open(_skipped_path(work_dir), encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            entries = []
    except (OSError, json.JSONDecodeError):
        entries = []
    entries = [e for e in entries
               if not (isinstance(e, dict) and e.get("shot_id") == shot_id)]
    entries.append({"shot_id": shot_id, "reason": reason,
                    "duration_sec": duration_sec})
    entries.sort(key=lambda e: e.get("shot_id", 0) if isinstance(e, dict) else 0)
    _atomic_write_json(_skipped_path(work_dir), entries)


# ─── 帧提取 / 上传 ──────────────────────────────────────────────────────────

def extract_endpoint_frames(src_video: str, shot: dict, vch: str,
                            frames_dir: str) -> tuple[str, str]:
    """ffmpeg 提取该镜首/尾帧（全分辨率，绝不带 -vf/scale——Pitfall 4：现有
    shot_frames/ 是 480x270 缩略图不可用）。首帧 ts=start_sec；尾帧
    ts=max(start_sec, end_sec-LAST_FRAME_GUARD_SEC)（前移防越界）。
    落盘确定性名 frames_dir/kst_{vch}_shot{NNN:03d}_ff.jpg 与 _lf.jpg
    （+ overwrite 语义由 ffmpeg -y 承担，防帧目录无限膨胀）。
    subprocess 全 list-form（security：-ss 数值来自自家 shots.json，无 shell 拼接）。"""
    os.makedirs(frames_dir, exist_ok=True)
    sid = int(shot["id"])
    start_sec = float(shot.get("start_sec", 0.0))
    end_sec = float(shot.get("end_sec", start_sec))
    lf_ts = max(start_sec, end_sec - LAST_FRAME_GUARD_SEC)
    dests = []
    for ts, suffix in ((start_sec, "ff"), (lf_ts, "lf")):
        dest = os.path.join(frames_dir, f"kst_{vch}_shot{sid:03d}_{suffix}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", src_video,
             "-frames:v", "1", "-q:v", "2", dest, "-loglevel", "error"],
            capture_output=True, timeout=60)
        dests.append(dest)
    return dests[0], dests[1]


def upload_image(path: str, comfy_url: str) -> str:
    """curl multipart 上传帧图 → 返回 ComfyUI input 目录内的确切文件名。
    Pitfall 5：(a) requests 传大图偶发 ConnectionResetError（p11b 实锤），
    用系统 curl；(b) GET /upload/image 返回 404 属正常（该路由只注册 POST）。"""
    proc = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{comfy_url}/upload/image",
         "-F", f"image=@{path}", "-F", "type=input", "-F", "overwrite=true"],
        capture_output=True, text=True, timeout=120)
    info = json.loads(proc.stdout)
    return info["name"]


# ─── HTTP plumbing（module-level —— 测试单一 monkeypatch 点）────────────────

def _http_json(url: str, payload: dict | None = None,
               timeout: float = 30.0) -> tuple[int, object]:
    """极简 JSON POST/GET（stdlib）。返回 (status, parsed-body-or-None)：
    HTTPError → (exc.code, body[:300])；URLError/OSError → (0, str(exc)[:300])。
    逐字 mirror analysis/engine_clients/qwen_eye_client.py:_http_json 语义。"""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300] if exc.fp else ""
        return exc.code, body
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, str(exc)[:300]


# ─── 提交 / 轮询 / 下载 ─────────────────────────────────────────────────────

def build_workflow(template: dict, ff_name: str, lf_name: str, prompt_text: str,
                   width: int, height: int, length: int, seed: int,
                   prefix: str) -> dict:
    """deepcopy 模板 → 注入五组节点 inputs，返回新 dict（模板对象与磁盘文件
    均不被改动）。prompt_text 只经 json.dumps 进 /prompt POST body
    （submit_prompt），绝不进任何 subprocess argv/字符串拼接（T-20-01）。"""
    wf = copy.deepcopy(template)
    wf[NODE_FIRST]["inputs"]["image"] = ff_name
    wf[NODE_LAST]["inputs"]["image"] = lf_name
    i2v = wf[NODE_I2V]["inputs"]
    i2v["prompt"] = prompt_text
    i2v["width"] = width
    i2v["height"] = height
    i2v["length"] = length
    sampler = wf[NODE_SAMPLER]["inputs"]
    sampler["seed"] = seed
    sampler["steps"] = 15      # CONTEXT SC1 锁定（模板同值，显式重申防漂移）
    sampler["cfg"] = 1.0
    wf[NODE_SAVE]["inputs"]["filename_prefix"] = prefix
    return wf


def submit_prompt(wf: dict, comfy_url: str) -> str:
    """POST {comfy}/prompt body {"prompt": wf} → prompt_id。
    校验失败（node_errors）raise RuntimeError 附前若干条（h3_ref2va_workflow
    同款解析；detail 只记 node id/字段名，T-20-03）。"""
    status, body = _http_json(f"{comfy_url}/prompt", payload={"prompt": wf})
    if status == 200 and isinstance(body, dict) and body.get("prompt_id"):
        return str(body["prompt_id"])
    detail = ""
    if isinstance(body, dict) and isinstance(body.get("node_errors"), dict):
        parts = []
        for nid, ne in list(body["node_errors"].items())[:5]:
            parts.append(f"{nid}:{sorted((ne or {}).keys())[:6]}")
        detail = "; ".join(parts)
    raise RuntimeError(f"ComfyUI /prompt 提交失败 status={status} {detail[:500]}")


def poll_and_fetch(prompt_id: str, comfy_url: str, timeout_s: int,
                   shot_label: str = "") -> dict | None:
    """轮询 /history/{prompt_id} 直至完成/出错/超时（kmc v4 crash-safe 骨架）。
    返回 {"ok": True, "filename", "subfolder"} / {"ok": False, "error"} / None(超时)。
    Pitfall 3：本 0.30.0 build 的 SaveVideo 把 mp4 产物序列化在 outputs 的
    **images** 键下（兼容遍历 gifs/videos），取 type=='output' 且 .mp4 结尾的
    确切条目——绝不猜文件名 pattern。瞬态 urlopen 异常 continue；每 ~60s 一条
    渲染中日志（含 elapsed 秒）。"""
    start = time.time()
    last_log = -POLL_LOG_EVERY_SEC
    while time.time() - start < timeout_s:
        time.sleep(POLL_INTERVAL_SEC)
        try:
            status, body = _http_json(f"{comfy_url}/history/{prompt_id}")
        except Exception:                                   # noqa: BLE001 — crash-safe
            continue
        if status != 200 or not isinstance(body, dict):
            continue
        entry = body.get(prompt_id)
        if not isinstance(entry, dict):
            continue
        st = entry.get("status") or {}
        if st.get("status_str") == "error":
            return {"ok": False, "error": str(st.get("messages"))[:2000]}
        if st.get("completed"):
            outputs = entry.get("outputs") or {}
            for out in outputs.values():
                if not isinstance(out, dict):
                    continue
                for key in ("images", "gifs", "videos"):
                    for item in (out.get(key) or []):
                        if (isinstance(item, dict)
                                and item.get("type") == "output"
                                and str(item.get("filename", "")).endswith(".mp4")):
                            return {"ok": True,
                                    "filename": str(item.get("filename", "")),
                                    "subfolder": str(item.get("subfolder", ""))}
        elapsed = int(time.time() - start)
        if elapsed - last_log >= POLL_LOG_EVERY_SEC:
            last_log = elapsed
            print(f"{STEP_TAG} {shot_label} 渲染中 elapsed={elapsed}s")
    return None


def sanitize_view_filename(filename: str) -> bool:
    """/view 下载文件名净化（T-20-02）：拒路径分隔符与 ".."、强制 .mp4 后缀。
    本地落盘路径由客户端自构造（shot_{NNN}_regen.mp4），不采用服务端文件名。"""
    if not isinstance(filename, str) or not filename.endswith(".mp4"):
        return False
    return not any(sep in filename for sep in ("/", "\\", ".."))


def _view_download(item: dict, comfy_url: str, dest: str) -> None:
    """GET /view?filename=&subfolder=&type=output → 二进制写 .part 临时文件，
    全量读完才 os.replace 落位 dest（CR-01：半截文件**永不占住最终路径**——
    中途 IncompleteRead/timeout/连接重置只留下可清理的 .part，上一轮完整产物
    与 cache meta 不受污染）。实测 byte-identical 路径；timeout 300s 覆盖
    ~10-50MB mp4。"""
    q = urllib.parse.urlencode({
        "filename": item.get("filename", ""),
        "subfolder": item.get("subfolder", ""),
        "type": "output",
    })
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(f"{comfy_url}/view?{q}", timeout=300) as resp, \
                open(tmp, "wb") as f:
            f.write(resp.read())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)          # 半截 .part 不残留（dest 从未被触碰）
        except OSError:
            pass
        raise


# ─── 4-tuple cache（REGEN-02）───────────────────────────────────────────────

def prompt_version_for(prompt_text: str) -> str:
    """per-shot prompt hash：sha256(prompt_text)[:8]。该镜 prompt_text 改一字
    即变 → 只重渲该镜（CONTEXT 锁定；与 vision_seq 的全局版本串不同）。"""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:8]


def _cache_meta_path(shot_id: int, work_dir: str) -> str:
    """cache 元数据路径（与 mp4 实体分离——cache 清了产物可独立校验）。"""
    return os.path.join(work_dir, "route_cache", "h3_regen", f"shot_{shot_id:03d}.json")


def _mp4_path(shot_id: int, work_dir: str) -> str:
    """产物路径（Phase 18 契约：regen.path 相对 asset root = roundtrip/shot_XXX_regen.mp4）。"""
    return os.path.join(work_dir, "roundtrip", f"shot_{shot_id:03d}_regen.mp4")


# cache 4-tuple 字段名（mirror WR-04 / vision_seq _cache_key 形状）。
_CACHE_KEY_FIELDS = ("video_content_hash", "engine_name", "engine_version", "prompt_version")


def cache_read(shot_id: int, work_dir: str, key4: dict) -> dict | None:
    """读 cache 元数据：4-tuple 全等才返回 meta，否则 None（miss 即全新，
    绝不部分复用）。文件缺席/损坏同样 miss。"""
    try:
        with open(_cache_meta_path(shot_id, work_dir), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    for field in _CACHE_KEY_FIELDS:
        if meta.get(field) != key4.get(field):
            return None
    return meta


def cache_is_hit(meta: dict | None, mp4_path: str,
                 expected_length: int | None = None) -> bool:
    """hit = meta 非 None 且 mp4 实体存在且 size>MIN_MP4_BYTES 且（meta 存档
    mp4_sha256 时）哈希一致（CR-01：下载截断/外改产物在 hit 口即拦截——深检
    成本 ~一次 50MB 顺序读，远低于重渲；旧版 meta 无此字段时退化为 size-only）
    且（给 expected_length 时）存档 length 与当前帧数网格值一致（WR-02：
    video_content_hash 只钉视频不钉分割——重分割后边界漂移的镜必须重渲，
    绝不复用旧 start/end_sec 首/尾帧渲染）。ffprobe 级编码损坏仍不检
    （CONTEXT 锁定——由 Phase 21 scorer 自然暴露）。"""
    if not isinstance(meta, dict):
        return False
    if not os.path.isfile(mp4_path):
        return False
    if os.path.getsize(mp4_path) <= MIN_MP4_BYTES:
        return False
    if expected_length is not None and meta.get("length") != expected_length:
        return False                        # 镜边界变了 → 该镜重渲
    expected = meta.get("mp4_sha256")
    return not expected or _file_sha256(mp4_path) == expected


def _file_sha256(path: str, chunk: int = 1024 * 1024) -> str:
    """分块读产物算 sha256（cache 元数据留档，供产物/cache 分离后独立校验）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _atomic_write_json(path: str, data: object) -> None:
    """tmp + os.replace 原子写（mirror vision_seq L333-338；indent=2
    ensure_ascii=False repo 惯例）。data 为 dict（cache/warnings/sidecar）
    或 list（skipped 清单）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cache_write(shot_id: int, work_dir: str, meta: dict) -> None:
    """写 cache 元数据（含 4-tuple + prompt_id/seed/length/width/height/
    mp4_sha256 + rendered_at 写入时刻 ISO）。原子写。"""
    payload = dict(meta)
    payload["rendered_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _atomic_write_json(_cache_meta_path(shot_id, work_dir), payload)


# ─── warnings 双形 merge（Pitfall 6）────────────────────────────────────────

def _is_roundtrip_warning(w: object) -> bool:
    """识别「本 step 上一轮」的条目：dict 且 code ∈ 三码 enum（[roundtrip]
    degrade 记因专用码——其它 step 不产 dict 形），或 str 以 [roundtrip] 开头
    （事件性说明）。[vision-seq] 等陌生 str 条目不匹配 → 原样保留。"""
    if isinstance(w, dict) and w.get("code") in _ROUNDTRIP_WARNING_CODES:
        return True
    return isinstance(w, str) and w.startswith(STEP_TAG)


def append_roundtrip_warnings(work_dir: str, new_entries: list) -> None:
    """READ route_cache/warnings.json → strip 本 step 上一轮条目 → 追加
    new_entries（str 与 dict 双形都收）→ 原子写回 {"warnings": merged}。
    绝不照抄 vision_seq 的 isinstance(w, str) 过滤（Pitfall 6 会丢 dict 条目）。"""
    sidecar = os.path.join(work_dir, "route_cache", "warnings.json")
    existing: list = []
    try:
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("warnings"), list):
            existing = list(data["warnings"])
    except (OSError, json.JSONDecodeError):
        existing = []
    kept = [w for w in existing if not _is_roundtrip_warning(w)]
    _atomic_write_json(sidecar, {"warnings": kept + list(new_entries)})


# ─── roundtrip.json sidecar（20-03 / Open Q2：regen 半边 + READ-merge）───────

def _load_schema_version() -> str:
    """importlib 加载 scripts/export_asset.py 取 SCHEMA_VERSION 属性（单源——
    版本号只活在 export_asset.py 一处，勿复制字面量）。加载失败/属性缺席
    sys.exit 中文报错：版本不明绝不落盘 sidecar。"""
    spec = importlib.util.spec_from_file_location(
        "export_asset_version", _SCHEMA_VERSION_SOURCE)
    if spec is None or spec.loader is None:
        sys.exit(f"{STEP_TAG} 无法定位 SCHEMA_VERSION 单源：{_SCHEMA_VERSION_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:                            # noqa: BLE001 — 任何加载失败都不静默兜版本
        sys.exit(f"{STEP_TAG} 加载 SCHEMA_VERSION 单源失败"
                 f"（{type(exc).__name__}: {str(exc)[:200]}）")
    version = getattr(module, "SCHEMA_VERSION", None)
    if not isinstance(version, str) or not version:
        sys.exit(f"{STEP_TAG} {_SCHEMA_VERSION_SOURCE} 缺 SCHEMA_VERSION 属性")
    return version


def probe_duration_sec(path: str) -> float:
    """ffprobe 探 mp4 时长（秒）。失败返回 0.0（repo probe_duration 吞错先例：
    duration 是 sidecar 观测字段，不构成批成败判据——损坏由 Phase 21 scorer
    自然暴露）。"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        return float(proc.stdout.strip())
    except (ValueError, AttributeError, subprocess.SubprocessError, OSError):
        return 0.0


def build_sidecar_entries(results: list, vch: str, width: int,
                          height: int) -> list[dict]:
    """results → roundtrip.json 条目半边。results 元素两种形态：
    rendered/cache-hit 镜 = cache meta + shot_id + mp4 绝对路径（cache-hit 镜
    从 cache meta 重建——断点续跑后 sidecar 完整性的关键）；failed 用例 =
    {shot_id, error}（error 截 2000，schema T-18-02 长度上界）。
    regen.path 由 shot_id 确定性构造（roundtrip/shot_{NNN:03d}_regen.mp4，
    相对 asset root——Phase 18 契约约定）。"""
    entries: list[dict] = []
    for r in results:
        if not isinstance(r, dict) or not isinstance(r.get("shot_id"), int):
            continue
        sid = int(r["shot_id"])
        if "error" in r:
            entries.append({"shot_id": sid,
                            "status": {"state": "failed",
                                       "error": str(r["error"])[:2000]}})
            continue
        entries.append({"shot_id": sid, "regen": {
            "path": f"roundtrip/shot_{sid:03d}_regen.mp4",
            "video_content_hash": str(r.get("video_content_hash") or vch),
            "engine_name": str(r.get("engine_name") or ENGINE_NAME),
            "engine_version": str(r.get("engine_version")
                                  or build_engine_version(width, height)),
            "prompt_version": str(r.get("prompt_version") or ""),
            "duration_sec": probe_duration_sec(str(r.get("mp4") or "")),
            "width": int(r.get("width") or width),
            "height": int(r.get("height") or height),
        }})
    return entries


def write_roundtrip_sidecar(work_dir: str, entries: list[dict]) -> None:
    """roundtrip.json 写入（Open Q2：客户端批末写 regen 半边）。
    READ-merge：既有同 shot_id 条目只替换 regen/status 半边，scores/verdict
    等 Phase 21 未来字段**原样保留**；JSON 损坏/缺席视为空重建（Phase 18
    决策：挂载前仅 JSON-parse）。写前 Draft202012Validator 全量 iter_errors
    （错误前 3 条 sys.exit 不落盘——vision_seq L705-713 先例）→ tmp +
    os.replace 原子写。schema_version 从 export_asset 单源加载。"""
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            existing = json.load(f)
    except (OSError, json.JSONDecodeError):
        existing = None
    if not isinstance(existing, dict) or not isinstance(existing.get("shots"), list):
        existing = {"shots": []}
    merged: dict[int, dict] = {}
    for s in existing["shots"]:
        if isinstance(s, dict) and isinstance(s.get("shot_id"), int):
            merged[int(s["shot_id"])] = s
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("shot_id"), int):
            continue
        sid = int(e["shot_id"])
        kept = {k: v for k, v in merged.get(sid, {}).items()
                if k not in ("regen", "status")}
        kept.update(e)                          # 新 regen/status 半边落位
        merged[sid] = kept
    payload = {"schema_version": _load_schema_version(),
               "shots": [merged[k] for k in sorted(merged)]}
    from jsonschema import Draft202012Validator
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                           for e in errors[:3])
        sys.exit(f"{STEP_TAG} roundtrip.json schema 校验失败"
                 f"（{len(errors)} 错误，拒绝落盘）: {detail}")
    _atomic_write_json(sidecar_path, payload)
    print(f"{STEP_TAG} roundtrip.json 已写入（{len(payload['shots'])} shots，"
          f"schema {payload['schema_version']} 校验通过）")


def strip_sidecar_regen_half(work_dir: str) -> int:
    """--force 时 roundtrip.json 的处理（WR-01 红线：verdict rejected 永不删除）：
    **绝不整体 unlink**——逐镜剥掉 regen/status 半边（本 run 将重渲重建），
    scores/verdict 等 Phase 21 人工/下游字段原样保留，等批末 READ-merge 回填。
    剥空（只剩 shot_id、无任何人工字段）的条目移除；全部剥空或文件缺席/损坏
    → 文件移除（等价旧的「全新重建」语义，但只在确认无人工数据可保留时发生）。
    返回保留条目数。"""
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
        return 0
    kept: list[dict] = []
    for s in data["shots"]:
        if not isinstance(s, dict) or not isinstance(s.get("shot_id"), int):
            continue
        stripped = {k: v for k, v in s.items() if k not in ("regen", "status")}
        if len(stripped) >= 2:               # shot_id 之外仍有 scores/verdict 等
            kept.append(stripped)
    if not kept:
        if os.path.isfile(sidecar_path):
            os.unlink(sidecar_path)
        return 0
    payload = {"schema_version": data.get("schema_version")
               or _load_schema_version(),
               "shots": sorted(kept, key=lambda e: int(e["shot_id"]))}
    _atomic_write_json(sidecar_path, payload)
    return len(kept)


# ─── VRAM guard / GPU 编排（REGEN-03，20-02）────────────────────────────────
# 全部读数 fail-open（qwen _vram_free_mib 先例）：nvidia-smi/ss/docker 异常返回
# None/[] 不阻塞调用方——guard 判定本身保守（有读数即严判，T-20-06）。

def proc_name(pid: int) -> str:
    """/proc/{pid}/cmdline 读进程名（\\0 → 空格，截 120 字符）——warning detail
    的 top 占用者审计用。不可读返回 ''（best-effort，不抛）。"""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read().replace(b"\x00", b" ").decode(errors="replace").strip()
        return raw[:120]
    except OSError:
        return ""


def gpu_mem_mib(gpu_index: int) -> tuple[int, int] | None:
    """一次查询 GPU total/free（MiB）→ (total, free)；不可得返回 None
    （fail-open）。--query-gpu 查询式（qwen _vram_free_mib 同款调用形状）。"""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits", "-i", str(gpu_index)],
            capture_output=True, text=True, timeout=10)
        cols = [c.strip() for c in proc.stdout.strip().splitlines()[0].split(",")]
        return int(cols[0]), int(cols[1])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return None


def compute_apps(gpu_index: int) -> list[tuple[int, int]]:
    """--query-compute-apps=pid,used_memory → [(pid, used_mib)]（Pitfall 1 每镜
    PID 归因复查的数据源）。"[Not Found]" 行（进程退出瞬间占位）被 isdigit
    数字校验自然跳过（T-20-07）；异常整体返回 []（fail-open）。"""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits", "-i", str(gpu_index)],
            capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        return []
    out: list[tuple[int, int]] = []
    for line in proc.stdout.strip().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) >= 2 and cols[0].isdigit():
            used = cols[1].replace("MiB", "").strip()
            out.append((int(cols[0]), int(used) if used.isdigit() else 0))
    return out


def find_tts_listeners() -> list[tuple[int, int, str]] | None:
    """ss -tlnp 解析 TTS_PORTS 监听 → [(pid, port, name)]。
    返回 None = 探测失败（ss 不可用/非零退出——哨兵区分「探测失败」与「无监听」，
    前者触发 pkill 回退）；[] = 确认无监听（no-op 安全路径）。"""
    try:
        proc = subprocess.run(["ss", "-tlnp"],
                              capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    listeners: list[tuple[int, int, str]] = []
    for line in proc.stdout.splitlines():
        for port in TTS_PORTS:
            if f":{port} " in line:
                m = re.search(r"pid=(\d+)", line)
                if m:
                    pid = int(m.group(1))
                    listeners.append((pid, port, proc_name(pid)))
                break
    return listeners


def kill_tts(listeners: list[tuple[int, int, str]] | None) -> list[dict]:
    """定向 kill TTS 监听进程：每个 (pid, port, name) os.kill(pid, SIGTERM)
    （ProcessLookupError 容忍——进程已退出不算错），返回审计记录。
    listeners is None（ss 探测失败）→ 回退 pkill -f 两个精确脚本名（A5 兜底，
    pattern 限于 TTS_FALLBACK_PATTERNS——绝不宽 pattern，T-20-05）；
    listeners == []（确认无监听）→ 空列表（无 kill 动作）。"""
    if listeners is None:
        killed: list[dict] = []
        for pat in TTS_FALLBACK_PATTERNS:
            try:
                r = subprocess.run(["pkill", "-f", pat],
                                   capture_output=True, timeout=10)
                if r.returncode == 0:
                    killed.append({"pattern": pat, "method": "pkill-fallback"})
            except (subprocess.SubprocessError, OSError):
                pass
        return killed
    killed = []
    for pid, port, name in listeners:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append({"pid": pid, "port": port, "name": name,
                           "method": "os.kill-SIGTERM"})
        except ProcessLookupError:
            pass                      # 进程已退出——视为已 kill
        except OSError:
            pass                      # 其余信号失败 best-effort 忽略
    return killed


def comfy_free(comfy_url: str) -> bool:
    """POST {comfy}/free body {"unload_models": True, "free_memory": True}
    （KAP gpuVramManager 同款 payload，实测 200）——驱逐 ComfyUI 自身模型
    cache。best-effort：结果只在返回值体现，调用方不据此阻塞。"""
    status, _ = _http_json(f"{comfy_url}/free",
                           payload={"unload_models": True, "free_memory": True})
    return status == 200


def _listeners_desc(listeners: list[tuple[int, int, str]]) -> str:
    """审计 warning detail 的监听者描述（pid/端口/进程名——CONTEXT 锁定要素）。"""
    return "; ".join(
        f"pid={p} port={port}({name[:60] or 'name-unreadable'})"
        for p, port, name in listeners)


def _apps_top_desc(gpu_index: int, limit: int = 3) -> str:
    """compute-apps top 占用者描述（pid+进程名+MiB——Pitfall 9：gate 拒绝时
    operator 一眼看出是谁占了）。"""
    apps = sorted(compute_apps(gpu_index), key=lambda x: -x[1])
    if not apps:
        return "n/a（compute-apps 无读数）"
    return "; ".join(f"pid={p}({proc_name(p)})={u}MiB" for p, u in apps[:limit])


def batch_start_guard(comfy_url: str, gpu_index: int,
                      wait_timeout: int) -> dict:
    """批开始 VRAM guard（五步固定序，见模块 docstring「VRAM guard 语义」）。
    返回 {blocked: bool, reason: str|None, killed: list[dict], warnings: list}——
    warnings 由 main 统一收集 flush（审计 + 拒绝记因都走 vram_insufficient）。"""
    result: dict = {"blocked": False, "reason": None, "killed": [], "warnings": []}

    # ① TTS 端口→PID 归因 kill（前后审计 warning；无监听 no-op 安全）
    listeners = find_tts_listeners()
    if listeners is None:
        result["killed"] = kill_tts(None)
        hit = [k.get("pattern") for k in result["killed"]]
        result["warnings"].append({
            "code": "vram_insufficient",
            "detail": f"TTS 端口探测失败（ss 不可用）→ pkill 回退："
                      f"{hit if hit else '无命中'}（pattern 限 "
                      f"{list(TTS_FALLBACK_PATTERNS)}）"})
    elif listeners:
        result["warnings"].append({
            "code": "vram_insufficient",
            "detail": f"TTS kill 前: {_listeners_desc(listeners)}"})
        result["killed"] = kill_tts(listeners)
        result["warnings"].append({
            "code": "vram_insufficient",
            "detail": f"TTS kill 后（SIGTERM 定向）: {_listeners_desc(listeners)}"})
    else:
        result["warnings"].append({
            "code": "vram_insufficient",
            "detail": f"TTS 端口 {list(TTS_PORTS)} 无监听 —— 无需 kill"
                      f"（guard 检查已执行的审计记录）"})

    # ② kill 后第一次 POST /free
    comfy_free(comfy_url)

    # ③ eye 串行等待（批开始绝对值检查——此刻无自身 cache 干扰，13GB 语义成立）
    start = time.time()
    while True:
        mem = gpu_mem_mib(gpu_index)
        if mem is None:
            break                                # fail-open：读数不可得不阻塞
        used = mem[0] - mem[1]
        if used < EYE_LEASE_MIB:
            break                                # eye lease 不在（或已释放）
        if time.time() - start >= wait_timeout:
            print(f"{STEP_TAG} eye lease 等待超时（{wait_timeout}s，"
                  f"used={used}MiB）—— 拒绝整批")
            result["blocked"] = True
            result["reason"] = "eye-wait-timeout"
            result["warnings"].append({
                "code": "vram_insufficient",
                "detail": f"eye lease 等待超时：used={used}MiB ≥ {EYE_LEASE_MIB}MiB"
                          f"（等待 {wait_timeout}s 后仍占用）—— qwen-eye 在跑，"
                          f"批不提交（--vram-wait-timeout 可配）"})
            return result
        print(f"{STEP_TAG} eye lease 在跑（used={used}MiB ≥ {EYE_LEASE_MIB}MiB）"
              f"—— 等待释放…")
        time.sleep(GUARD_POLL_SEC)

    # ④ 批开始前第二次 POST /free（「kill 后与批开始前各一次」——CONTEXT 字面）
    comfy_free(comfy_url)

    # ⑤ 严格 gate：free < 22528MiB 拒整批（detail 含 free + top 占用者——Pitfall 9）
    mem = gpu_mem_mib(gpu_index)
    if mem is not None and mem[1] < BATCH_MIN_FREE_MIB:
        print(f"{STEP_TAG} 批开始 free={mem[1]}MiB < {BATCH_MIN_FREE_MIB}MiB"
              f"（22GB）—— 拒绝整批")
        result["blocked"] = True
        result["reason"] = "batch-free-below-min"
        result["warnings"].append({
            "code": "vram_insufficient",
            "detail": f"批开始 free={mem[1]}MiB < {BATCH_MIN_FREE_MIB}MiB（22GB）—— "
                      f"top 占用: {_apps_top_desc(gpu_index)}（music3 常驻 676MiB "
                      f"属正常态，kill 后实测 ≈22539 仍过线）"})
    return result


def baseline_pid_snapshot(gpu_index: int) -> set[int]:
    """每镜复查基线：guard 完成后 compute-apps 全部 PID ∪ docker inspect
    comfyui-primary 主 PID（best-effort，docker 不可用静默忽略）。"""
    pids = {p for p, _ in compute_apps(gpu_index)}
    try:
        proc = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", COMFY_CONTAINER],
            capture_output=True, text=True, timeout=10)
        pids.add(int(proc.stdout.strip()))
    except (subprocess.SubprocessError, OSError, ValueError):
        pass
    return pids


def per_shot_vram_ok(gpu_index: int, baseline: set[int],
                     wait_timeout: int) -> bool:
    """每镜提交前 PID 归因复查（Pitfall 1 反自锁）：foreign = 当前 compute-apps
    中不在基线的 PID；Σforeign_used < FOREIGN_BLOCK_MIB → True；否则 15s 等待
    循环（log 一次 top foreign）至超时 → False（main 收到 False → warning +
    优雅终止批）。基线内 PID（ComfyUI 自身 cache 驻留）永不触发。"""
    start = time.time()
    logged = False
    while True:
        foreign = [(p, u) for p, u in compute_apps(gpu_index) if p not in baseline]
        total_used = sum(u for _, u in foreign)
        if total_used < FOREIGN_BLOCK_MIB:
            return True
        if not logged:
            top = max(foreign, key=lambda x: x[1])
            print(f"{STEP_TAG} foreign GPU 占用 {total_used}MiB ≥ "
                  f"{FOREIGN_BLOCK_MIB}MiB（top pid={top[0]} {top[1]}MiB）"
                  f"—— 等待释放…")
            logged = True
        if time.time() - start >= wait_timeout:
            return False
        time.sleep(GUARD_POLL_SEC)


# ─── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="h3 fl2va 复现客户端 —— ComfyUI 直连提交/轮询/回收 + per-shot cache")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— cache 与产物写在其下")
    ap.add_argument("--comfy-url", default=COMFY_URL_DEFAULT,
                    help=f"ComfyUI API 基址（默认 {COMFY_URL_DEFAULT}）")
    ap.add_argument("--force", action="store_true",
                    help="清掉本 step 的 cache（route_cache/h3_regen/）与产物"
                         "（roundtrip/）后重渲；roundtrip.json 只剥 regen/status"
                         " 半边——scores/verdict（含 rejected）永不删除")
    ap.add_argument("--shot-timeout", type=int, default=0,
                    help="单镜渲染超时秒数（0=自动 900+3*length，按帧数缩放防长镜误判）")
    ap.add_argument("--gpu-index", type=int, default=VRAM_GPU_INDEX_DEFAULT,
                    help=f"nvidia-smi GPU index（默认 {VRAM_GPU_INDEX_DEFAULT} = "
                         f"comfyui-primary 所在 3090）")
    ap.add_argument("--vram-wait-timeout", type=int, default=1800,
                    help="批开始 eye 等待 / 每镜 foreign 等待的超时秒数（默认 1800）")
    ap.add_argument("--sample-shots", type=int, default=0,
                    help="均匀间隔抽样 N 镜（0=不抽样全量；抽样在 >10s 过滤之前做）")
    ap.add_argument("--max-shot-sec", type=float, default=10.0,
                    help="超限镜跳过阈值秒数（duration 超过则跳镜 + skipped.json；0=不过滤）")
    ap.add_argument("--regen-resolution",
                    default=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}",
                    help="渲染分辨率 WxH（默认 1344x768；降档 896x512 严格 7:4——"
                         "分辨率冻进 engine_version，切换即整体 cache 失效重渲）")
    args = ap.parse_args()
    signal.signal(signal.SIGINT, signal.default_int_handler)  # Ctrl-C 可中断批（断点续跑承接）

    work_dir = args.work_dir
    src_video = resolve_source_video(work_dir)
    vch = video_content_hash(src_video)
    shots, join_warnings = load_shot_prompts(work_dir)
    print(f"{STEP_TAG} 源={os.path.basename(src_video)} vch={vch} "
          f"待处理镜数={len(shots)}（缺 prompt_text 跳过 {len(join_warnings)} 镜）")
    pending_warnings: list = list(join_warnings)

    # 分辨率解析 + 校验（CLI fail-fast：非法值在任何 guard 动作/HTTP 之前退出）。
    width, height = parse_resolution(args.regen_resolution)
    if not validate_resolution(width, height):
        sys.exit(f"{STEP_TAG} --regen-resolution {args.regen_resolution} 非法"
                 f"（需 %32==0 + 严格 7:4 + 面积≤{MAX_PIXELS}；"
                 f"如 {DEFAULT_WIDTH}x{DEFAULT_HEIGHT} / 896x512）")
    engine_version = build_engine_version(width, height)

    # ComfyUI 可达性 gate（标准序第一位：ComfyUI down 时先降级退出，不白杀 TTS、
    # 不空轮 eye lease，**更不执行 --force 破坏性清除**——CR-02：引擎确认可用
    # 之前 cache/产物/sidecar 一个字节都不动）→ --force 清单清除 → 抽样/过滤
    # → batch_start_guard → 批循环（20-01 标准序 + CR-02 重排）。
    status, _body = _http_json(f"{args.comfy_url}/system_stats")
    if status != 200:
        pending_warnings.append({"code": "comfyui_unreachable",
                                 "detail": f"system_stats status={status}"})
        append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} ComfyUI 不可达（status={status}）—— graceful-degrade 退出")
        return 0

    if args.force:
        import shutil
        force_cache_dir = os.path.join(work_dir, "route_cache", "h3_regen")
        force_out_dir = os.path.join(work_dir, "roundtrip")
        for p in (force_cache_dir, force_out_dir):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)      # 显式清单，绝不 glob 父级（T-14-01/T-20-04）
        # roundtrip.json 不整体删除（WR-01 红线：verdict rejected 永不删除）——
        # 只剥 regen/status 半边，scores/verdict 保留给批末 READ-merge 回填。
        kept_sidecar = strip_sidecar_regen_half(work_dir)
        print(f"{STEP_TAG} [force] 已清除 {force_cache_dir} / {force_out_dir}"
              f"；roundtrip.json 剥除 regen/status 半边"
              f"（保留 {kept_sidecar} 条 scores/verdict 条目）")

    # 抽样 → 时长过滤（顺序锁定：先抽样后过滤——A6 语义：抽样代表性不被过滤
    # 顺序扭曲；ep01 锚点 shot 70 落样后被 max-shot-sec 跳过 → 实渲 19。
    # 放在 --force 之后：force 清掉旧 skipped.json 后由本轮回写，清单始终
    # 反映最新一轮的过滤决定）。
    sampled_count = 0
    if args.sample_shots > 0:
        all_count = len(shots)
        keep_ids = set(uniform_sample([s["id"] for s in shots],
                                       args.sample_shots))
        shots = [s for s in shots if s["id"] in keep_ids]
        sampled_count = len(keep_ids)
        print(f"{STEP_TAG} --sample-shots {args.sample_shots}: "
              f"{sampled_count}/{all_count} 镜入样（均匀间隔，全镜列表上做）")
    skipped_count = 0
    if args.max_shot_sec > 0:
        kept_shots: list[dict] = []
        for s in shots:
            if s.get("duration", 0.0) > args.max_shot_sec:
                msg = (f"{STEP_TAG} shot {s['id']} skipped: "
                       f"{s['duration']:.1f}s > max {args.max_shot_sec:.1f}s")
                print(msg)
                pending_warnings.append(msg)
                write_skipped_entry(work_dir, s["id"], "duration_over_max",
                                    s["duration"])
                skipped_count += 1
            else:
                kept_shots.append(s)
        shots = kept_shots

    # 批开始 VRAM guard（五步固定序，见模块 docstring）。blocked → 优雅退出
    # exit 0（graceful-degrade：vram_insufficient warning，cache 保留续跑语义）。
    guard = batch_start_guard(args.comfy_url, args.gpu_index,
                              args.vram_wait_timeout)
    pending_warnings.extend(guard["warnings"])
    if guard["blocked"]:
        append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} 批开始 guard 拒绝（reason={guard['reason']}）"
              f"—— graceful-degrade 退出")
        return 0
    # 每镜复查基线（guard 之后快照——此刻 GPU 上的 PID 全部属「已过 gate」态）。
    baseline_pids = baseline_pid_snapshot(args.gpu_index)

    # 分辨率已在 gate 前解析校验；engine_version 随 (w,h) 变化 → 切分辨率
    # 即旧 cache 整体失效（Q3 裁决：换渲染配置全集重渲）。
    template = load_template()

    frames_dir = os.path.join(work_dir, "route_cache", "h3_regen", "frames")
    out_dir = os.path.join(work_dir, "roundtrip")
    os.makedirs(out_dir, exist_ok=True)

    rendered = 0
    cache_hits = 0
    failed: list[int] = []
    failed_detail: dict[int, str] = {}
    results: list[dict] = []          # sidecar results（rendered + cache-hit meta）
    done = 0
    for shot in shots:
        done += 1
        sid = shot["id"]
        label = f"shot {sid}"
        key4 = {
            "video_content_hash": vch,
            "engine_name": ENGINE_NAME,
            "engine_version": engine_version,
            "prompt_version": prompt_version_for(shot["prompt_text"]),
        }
        mp4 = _mp4_path(sid, work_dir)
        # length 在 cache 预判**之前**算（WR-02：4-tuple 只钉视频不钉分割——
        # 同源视频重分割后，存档 length 与当前 duration 网格值不一致即 miss
        # 重渲，绝不复用旧边界首/尾帧的渲染）。
        length = h3_frame_count(shot["duration"])
        hit_meta = cache_read(sid, work_dir, key4)
        if cache_is_hit(hit_meta, mp4, expected_length=length):
            cache_hits += 1
            # cache-hit 镜也进 sidecar results（从 cache meta 重建条目——
            # 断点续跑后 roundtrip.json 完整性的关键）。
            results.append(dict(hit_meta or {}, shot_id=sid, mp4=mp4))
            print(f"{STEP_TAG} shot {sid}: cache hit, skipping")
            continue
        # 每镜提交前 PID 归因复查（Pitfall 1：基线内自身 cache 驻留不触发；
        # foreign ≥4GB 且超时 → 优雅终止批，break 落到收尾 flush 后 return 0）。
        if not per_shot_vram_ok(args.gpu_index, baseline_pids,
                                args.vram_wait_timeout):
            foreign = sorted(((p, u) for p, u in compute_apps(args.gpu_index)
                              if p not in baseline_pids), key=lambda x: -x[1])
            top = "; ".join(f"pid={p}({proc_name(p)})={u}MiB"
                            for p, u in foreign[:3]) or "n/a"
            mem = gpu_mem_mib(args.gpu_index)
            free_s = f"{mem[1]}MiB" if mem else "n/a"
            pending_warnings.append({
                "code": "vram_insufficient",
                "detail": f"镜 {sid} 提交前 foreign GPU 占用 ≥{FOREIGN_BLOCK_MIB}MiB"
                          f"（top: {top}; free={free_s}）—— 优雅终止批，cache 保留续跑"})
            print(f"{STEP_TAG} shot {sid}: foreign 占用超限 —— 优雅终止批"
                  f"（cache 保留续跑）")
            break
        try:
            seed = derive_seed(vch, sid)
            ff_path, lf_path = extract_endpoint_frames(src_video, shot, vch, frames_dir)
            ff_name = upload_image(ff_path, args.comfy_url)
            lf_name = upload_image(lf_path, args.comfy_url)
            prefix = f"kst_{vch}_shot{sid:03d}"
            wf = build_workflow(template, ff_name, lf_name, shot["prompt_text"],
                                width, height, length, seed, prefix)
            prompt_id = submit_prompt(wf, args.comfy_url)
            timeout_s = args.shot_timeout if args.shot_timeout > 0 else 900 + 3 * length
            result = poll_and_fetch(prompt_id, args.comfy_url, timeout_s, label)
            if not result or not result.get("ok"):
                error = (result or {}).get("error") or "timeout"
                print(f"{STEP_TAG} shot {sid}: 渲染失败（{str(error)[:300]}）")
                failed.append(sid)
                failed_detail[sid] = str(error)[:2000]
                continue
            filename = result.get("filename", "")
            if not sanitize_view_filename(filename):
                print(f"{STEP_TAG} shot {sid}: 产物文件名非法（{filename!r}），拒绝下载")
                failed.append(sid)
                failed_detail[sid] = f"产物文件名非法: {filename!r}"
                continue
            _view_download(result, args.comfy_url, mp4)
            if os.path.getsize(mp4) <= MIN_MP4_BYTES:
                print(f"{STEP_TAG} shot {sid}: 产物 <= {MIN_MP4_BYTES}B，判失败")
                failed.append(sid)
                failed_detail[sid] = f"下载产物 <= {MIN_MP4_BYTES}B"
                continue
            meta = dict(key4)
            meta.update({
                "prompt_id": prompt_id,
                "seed": seed,
                "length": length,
                "width": width,
                "height": height,
                "mp4_sha256": _file_sha256(mp4),
            })
            # 渲后水位留档（Open Q1 数据：--lowvram 下渲后自身 cache 驻留的实测
            # 水位，为后续 guard 调参留证据；nvidia-smi 不可得记 None）。
            mem_after = gpu_mem_mib(args.gpu_index)
            meta["post_render_free_mib"] = mem_after[1] if mem_after else None
            cache_write(sid, work_dir, meta)
            results.append(dict(meta, shot_id=sid, mp4=mp4))
            rendered += 1
            print(f"{STEP_TAG} shot {sid}: rendered {os.path.basename(mp4)}")
        except Exception as exc:                            # 单镜失败不阻塞批（vision_seq L660 形态）
            print(f"{STEP_TAG} shot {sid}: 异常失败（{type(exc).__name__}: {str(exc)[:300]}）")
            failed.append(sid)
            failed_detail[sid] = f"{type(exc).__name__}: {str(exc)[:300]}"
            continue
        if (done % 10) == 0:
            print(f"{STEP_TAG} {done}/{len(shots)} shots processed")

    # 收尾：roundtrip.json regen 半边（Open Q2）—— failed 镜转 status 条目后
    # 与 rendered/cache-hit results 合并写入（schema 写前自校验 + READ-merge）。
    # 早退路径（ComfyUI 不可达 / guard 拒绝）不写：本轮无新增产物，既有
    # sidecar 原样保留（READ-merge 空集本就是恒等变换）。
    results.extend({"shot_id": sid,
                    "error": failed_detail.get(sid, "render failed")}
                   for sid in failed)
    write_roundtrip_sidecar(work_dir, build_sidecar_entries(
        results, vch, width, height))

    # 收尾 flush：本轮 str/dict warnings（join 缺失 / 跳镜 str / 失败摘要 /
    # guard 审计与拒绝记因）→ summary print。
    if failed:
        pending_warnings.append(f"{STEP_TAG} failed shots: {failed}")
    if pending_warnings:
        append_roundtrip_warnings(work_dir, pending_warnings)
    print(f"{STEP_TAG} 完成：rendered={rendered} cache-hit={cache_hits} "
          f"failed={len(failed)} sampled={sampled_count} skipped={skipped_count}")
    print(f"{STEP_TAG} 产物目录：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
