#!/usr/bin/env python3
"""h3 复现客户端（Phase 20 / REGEN-01）—— kst 直连 ComfyUI 原生 API，不经 subagent/KAP/kmc。

背景
----
闭环数据集的复现半边：对每镜 (首帧, 尾帧, prompt_text) 用 MiniMax H3 fl2va
重新生成一段 mp4（roundtrip/shot_XXX_regen.mp4），供 Phase 21 scorer 与原片段
比对打分。提交协议是 ComfyUI 原生 HTTP（/upload/image → /prompt → /history →
/view），HTTP 轮询 crash-safe（kmc v4 骨架；只走短连接轮询，不建长连接通道）。

算法步骤
--------
1. 载入 shots.json（分割权威镜列表）+ prompts.json（按 shot_id join prompt_text）；
2. --force 时显式清单清除本 step 的 cache 与产物；
3. ComfyUI 可达性 gate（GET /system_stats 非 200 → 结构化 warning + exit 0，
   graceful-degrade；20-02 的 VRAM guard 序列插在此 gate 之后）；
4. 批循环逐镜：4-tuple cache 预判 → miss 则 ffmpeg 全分辨率提取首/尾帧 →
   curl POST /upload/image ×2 → deepcopy workflow_fl2va.json 模板并注入
   节点参数（14/15 帧名、20 prompt/width/height/length、30 seed、50 prefix）→
   POST /prompt → 轮询 /history/{prompt_id} → /view 下载 mp4 → cache 写入；
5. 收尾 flush 本轮 warnings（跳镜 str / 失败摘要）+ summary print。

graceful-degrade 语义
---------------------
ComfyUI 不可达 / 单镜渲染失败 / 单镜超时都不阻塞：引擎级降级 exit 0（资产照常，
[warnings] 记 {code: "comfyui_unreachable"}）；单镜级失败进 failed 清单后 continue。

cache 惯例
----------
- 元数据 work_dir/route_cache/h3_regen/shot_{NNN}.json（4-tuple：video_content_hash
  + engine_name + engine_version + prompt_version；另存 prompt_id/seed/length/
  width/height/mp4_sha256/rendered_at），与 mp4 实体分离；
- hit = 4-tuple 全等 + mp4 存在且 size>1KB（不做 ffprobe 深检——损坏由
  Phase 21 scorer 自然暴露）；
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

argv 用法
---------
    python3 analysis/roundtrip/h3_regen.py --work-dir output/<video-stem>/ \
        [--comfy-url http://127.0.0.1:8188] [--force] [--shot-timeout 0]

（--sample-shots/--max-shot-sec/--regen-resolution 等 sampling/降载 flag 在
20-02 接入；本 plan 固定默认分辨率 1344x768 处理全部镜。）
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
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

# 轮询节奏（kmc v4 crash-safe 骨架：sleep 15s + 瞬态异常 continue）。
POLL_INTERVAL_SEC = 15
POLL_LOG_EVERY_SEC = 60


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
    """GET /view?filename=&subfolder=&type=output → 二进制直写 dest
    （实测 byte-identical 路径；timeout 300s 覆盖 ~10-50MB mp4）。"""
    q = urllib.parse.urlencode({
        "filename": item.get("filename", ""),
        "subfolder": item.get("subfolder", ""),
        "type": "output",
    })
    with urllib.request.urlopen(f"{comfy_url}/view?{q}", timeout=300) as resp, \
            open(dest, "wb") as f:
        f.write(resp.read())
