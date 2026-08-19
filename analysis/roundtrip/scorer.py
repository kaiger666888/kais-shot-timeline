#!/usr/bin/env python3
"""SigLIP 中段帧轨迹相似度打分（Phase 21 / SCORE-01）—— 原片段 vs h3 regen 的
机器可证半边（21-01 离线交付；GPU 真跑在 21-02/21-03 复用同 requirement IDs）。

背景
----
Phase 20 h3_regen 产出 roundtrip/shot_XXX_regen.mp4 后，本模块给出双信号中
便宜的那一路：两侧各 resample 到固定 N=8 帧 @25%-75% 时窗（t=0/t=end 被
condition 帧结构性排除——SC1 字面；实测 t=0 余弦 0.983 vs 中段 0.91-0.93，
端点混入会让分数虚高），SigLIP so400m embedding 后 per-position cosine，
mean 即 midframe_sim 主分数（DTW 轨迹对齐留升级位，CONTEXT 裁决）。

算法步骤
--------
1. 读 work_dir/roundtrip.json 取有 regen.path 的条目（status/failed 条目
   str warning 跳过——它们没有可比对产物）；--shots 可选 int 子集过滤；
2. 逐镜 cache 预判（key 五字段：video_content_hash + regen_mp4_sha256_16 +
   model + n_frames + window——regen mp4 身份进 key，896×512 smoke 与
   1344×768 批产物天然分离，Pitfall 7）；全 hit 零模型加载；
3. miss 镜：ffmpeg 逐帧提取 16 帧（orig 侧 ts = shot.start_sec + 时窗偏移；
   regen 侧 ts = 时窗偏移按 regen 时长归一；两端 clamp min(ts, dur-0.2)——
   175f/24fps 流末帧起点 7.25s，-ss 7.252 实测越界，Pitfall 3）；
   SigLIP fp16 一次前向（batch=16）→ L2 归一 → 逐位 dot → mean；
4. cache 写 route_cache/scorer/shot_XXX.json（含 frames.orig/regen 各 8 条
   {j, t_pct, t_sec, path} 时间戳清单——SC2 审计可回放的硬要求）；
5. roundtrip.json scores.midframe_sim 半边 READ-merge 写入：scores 子对象
   **浅合并**（只 update midframe_sim，绝不整体替换——不丢 judge 半边），
   verdict/regen/status 原样保留；写前两层自校验 mirror h3_regen WR-04
   （本批坏 sys.exit fail-loud；预存坏条目剔除 + .bak-<ts> 备份 + str warning）。

graceful-degrade 语义
---------------------
SigLIP 加载抛任何异常（权重 .incomplete / transformers 5.x API 漂移 / OOM 后
cpu 重试也失败）→ append_roundtrip_warnings 写 {code: "scorer_model_missing",
detail: 异常类型+消息}（三码 closed enum 已预留此码）+ rc=0 + sidecar 原样
——绝不 sys.exit 炸批（RT-04）。cuda 加载失败/OOM 自动降 cpu 重试一次（日志
可见），不碰 GPU1（ComfyUI 批后 cache 驻留 ~21GB，Pitfall 4——默认 --device
cuda:0 即 GPU0 3060Ti 零竞争）。

cache 惯例
----------
- 元数据 work_dir/route_cache/scorer/shot_{NNN}.json；hit = key 五字段与
  payload 内字段全等（缺席/损坏/字段不等一律 miss，绝不部分复用——mirror
  h3_regen cache_read）；
- payload 另存 frames.orig/regen 清单（j / t_pct / t_sec / path）、
  per_position_cos（SC2 审计面）、score、model、device、scored_at；
- 帧实体落 route_cache/scorer/frames/shot_{NNN}_{side}_{JJ}.jpg（side ∈
  orig|regen，先删后提防失败残留，WR-05）。

argv 用法
---------
    python3 analysis/roundtrip/scorer.py --work-dir output/<video-stem>/ \
        [--device cuda:0] [--shots 1,5,47]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# ─── 模块级常量 ─────────────────────────────────────────────────────────────

STEP_TAG = "[roundtrip]"          # 与 h3_regen 同 tag（同 step 家族，warnings strip 语义共用）

# SigLIP so400m（CONTEXT 锁定；权重已在盘 HF cache 离线加载零下载）。
# MODEL_LABEL 是 sidecar scores.midframe_sim.model 与 cache key 的取值——
# 跨模型分数不可比（schema 强制 model 字段）。
MODEL_ID = "google/siglip-so400m-patch14-384"
MODEL_LABEL = "siglip-so400m-patch14-384"

# 时窗：N=8 帧，t_j = dur·(25% + 50%·j/7)，j=0..7（t=0/t=end 结构性不可达）。
N_FRAMES = 8
WINDOW_PCT = (25.0, 75.0)         # 百分比形（cache key 留档同形）

# 端点防越界前移量（秒）。h3_regen 的 0.04s guard 是对 h264.mp4 调的值，
# 对 24fps regen mp4 不够（末帧起点 7.25s，-ss 7.252 实测失败）——Pitfall 3。
ENDPOINT_GUARD_SEC = 0.2

SCORER_CACHE_SUBDIR = "route_cache/scorer"
FRAMES_SUBDIR = "route_cache/scorer/frames"

# roundtrip.json 写前自校验目标 schema 经 h3s（其 SCHEMA_PATH 与本模块同层同路径）。
# 本模块在 analysis/roundtrip/ 下——repo root 必须 parent.parent.parent
# （三层 parent off-by-one 陷阱，mirror h3_regen L190-199 注释）。
SCHEMA_PATH = (Path(__file__).resolve().parent.parent.parent
               / "spec" / "schemas" / "roundtrip.schema.json")

# h3_regen 共享件经 importlib 文件加载（单源不漂移；h3_regen 模块级无副作用、
# main 有 guard，加载安全——mirror h3_regen.py L708-712 加载 export_asset 的方式）。
# 用 h3s.append_roundtrip_warnings / _atomic_write_json / probe_duration_sec /
# _iter_sidecar_errors / _load_schema_version / resolve_source_video /
# video_content_hash，绝不复制字面量实现。
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)

# cache key 五字段（Pitfall 7：分辨率/引擎身份经 regen mp4 sha256 联动）。
_SCORER_KEY_FIELDS = ("video_content_hash", "regen_mp4_sha256_16",
                      "model", "n_frames", "window")


# ─── 帧窗数学（SCORE-01 核心，探针实测公式）────────────────────────────────

def frame_ts(duration_sec: float, j: int, n: int = N_FRAMES,
             guard: float = ENDPOINT_GUARD_SEC) -> float:
    """时窗内第 j 帧的时间戳（秒）：ts = dur·(0.25 + 0.5·j/(n-1))，再 clamp
    min(ts, max(dur-guard, 0.0))。不变式：n=8 时 t_pct 序列 25.0..75.0
    （步长 50/7），t=0 / t=end 结构性不可达（窗口定义本身排除被 condition
    的首尾帧）；短镜端点 clamp 生效（dur=0.5 时 j=7 → 0.3）。"""
    ts = float(duration_sec) * (0.25 + 0.5 * j / (n - 1))
    return min(ts, max(float(duration_sec) - guard, 0.0))


def plan_frames(duration_sec: float, n: int = N_FRAMES) -> list[dict]:
    """整窗帧清单：[{j, t_pct, t_sec}]。t_pct 是名义窗位百分数（25.0→75.0，
    不随 clamp 变化——审计留档的是「打算取哪一窗位」）；t_sec 是 clamp 后
    实际提取时间戳。"""
    out: list[dict] = []
    for j in range(n):
        out.append({
            "j": j,
            "t_pct": round((0.25 + 0.5 * j / (n - 1)) * 100.0, 4),
            "t_sec": round(frame_ts(duration_sec, j, n), 6),
        })
    return out


# ─── 帧提取（ffmpeg list-form + 三重 fail-loud，WR-05 形状）─────────────────

def _stderr_snip(proc, limit: int = 200) -> str:
    """subprocess 结果的 stderr 片段（bytes/str/属性缺席通吃，截 limit）。
    mirror h3_regen L378-384（经 h3s 同名件语义一致，此处 judge/scorer 各自
    保留一份私有副本以便单测独立替换）。"""
    raw = getattr(proc, "stderr", None) or ""
    if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
    return raw[:limit]


def extract_frame(video: str, ts_sec: float, dest: str) -> None:
    """ffmpeg 提取单帧到 dest（list-form；-ss 数值只来自自家 shots.json /
    ffprobe，无 shell 拼接）。提取前先删旧 dest（isfile 守卫——失败绝不残留
    上一轮字节被当新帧，WR-05）；rc 非零 / dest 未产出 / 空文件三重检查
    fail-loud → RuntimeError 附 stderr 摘录。"""
    if os.path.isfile(dest):
        os.unlink(dest)
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{ts_sec:.3f}", "-i", video,
         "-frames:v", "1", "-q:v", "2", dest, "-loglevel", "error"],
        capture_output=True, timeout=60)
    if (proc.returncode != 0 or not os.path.isfile(dest)
            or os.path.getsize(dest) == 0):
        raise RuntimeError(
            f"ffmpeg 帧提取失败 rc={proc.returncode} dest={dest} "
            f"stderr={_stderr_snip(proc)}")


def regen_sha16(path: str, chunk: int = 1024 * 1024) -> str:
    """regen mp4 的 sha256 前 16 hex（分块读）。cache key 身份维——896×512
    smoke 与 1344×768 批产物字节级不同，天然分离（Pitfall 7）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()[:16]


# ─── SigLIP 加载 / embedding（transformers 5.6.2 API，探针实测）────────────

def load_siglip(device: str):
    """离线加载 SigLIP so400m → (model, processor, 实际 device)。

    - HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 先设 env 再 import transformers
      （只读盘 cache，无网络取包面，T-21-04）；
    - transformers 5.x：AutoModel.from_pretrained(..., dtype=...)（参数名
      dtype=）；cuda 路径 fp16，cpu 路径 float32；
    - cuda 加载/OOM 失败 → 打印降级日志后 cpu 重试一次；重试仍失败异常上抛
      （main 捕获走 scorer_model_missing degrade）；
    - 延迟 import（函数内 import torch/transformers）使单测可 monkeypatch
      本函数整体而不触碰重依赖。
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch                                             # 延迟重依赖
    from transformers import AutoModel, AutoProcessor
    if not str(device).startswith("cuda"):
        model = (AutoModel.from_pretrained(MODEL_ID, dtype=torch.float32)
                 .to("cpu").eval())
        return model, AutoProcessor.from_pretrained(MODEL_ID), "cpu"
    try:
        model = (AutoModel.from_pretrained(MODEL_ID, dtype=torch.float16)
                 .to(device).eval())
        return model, AutoProcessor.from_pretrained(MODEL_ID), device
    except Exception as exc:                                 # cuda 不可用 / OOM → 降 cpu
        print(f"{STEP_TAG} SigLIP 在 {device} 加载失败"
              f"（{type(exc).__name__}: {str(exc)[:200]}）—— 自动降级 cpu 重试")
        model = (AutoModel.from_pretrained(MODEL_ID, dtype=torch.float32)
                 .to("cpu").eval())
        return model, AutoProcessor.from_pretrained(MODEL_ID), "cpu"


def embed_frames(model, processor, device: str,
                 frames: list) -> np.ndarray:
    """PIL 帧列表 → L2 归一后的 (B, 1152) numpy。transformers 5.x 返回
    BaseModelOutputWithPooling——必须取 .pooler_output（探针实证；直接当
    tensor 用会 AttributeError）。cuda 时 pixel_values 转 half 匹配 fp16 权重。"""
    import torch                                             # 延迟重依赖（torch.no_grad）
    pv = processor(images=frames, return_tensors="pt")["pixel_values"].to(device)
    if str(device).startswith("cuda"):
        pv = pv.half()
    with torch.no_grad():
        out = model.get_image_features(pixel_values=pv).pooler_output
    emb = out.float().cpu().numpy()
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0                                # 零向量除零守卫
    return emb / norms


# ─── 打分主计算 ─────────────────────────────────────────────────────────────

def score_shot(model, processor, device: str, work_dir: str, src_video: str,
               shot: dict, regen_path: str, regen_dur: float, key: dict) -> dict:
    """单镜打分：16 帧提取（orig 8 + regen 8）→ 一次前向 → 前 8/后 8 切分 →
    per-position cosine（L2 归一后逐位 dot）→ mean 即 score（clamp [0,1] 后
    round 4 位）。返回 cache 完整 payload（key 五字段 + frames 清单带 path +
    per_position_cos + score + model + device + scored_at）。"""
    sid = int(shot["id"])
    dur = float(shot.get("duration")
                or (float(shot.get("end_sec", 0.0)) - float(shot.get("start_sec", 0.0))))
    start = float(shot.get("start_sec", 0.0))
    frames_dir = os.path.join(work_dir, FRAMES_SUBDIR)
    os.makedirs(frames_dir, exist_ok=True)

    orig_plan = plan_frames(dur)
    regen_plan = plan_frames(regen_dur)
    orig_paths: list[str] = []
    regen_paths: list[str] = []
    frames_meta: dict = {"orig": [], "regen": []}
    for side, plan, video, base_ts, paths in (
            ("orig", orig_plan, src_video, start, orig_paths),
            ("regen", regen_plan, regen_path, 0.0, regen_paths)):
        for e in plan:
            dest = os.path.join(frames_dir,
                                f"shot_{sid:03d}_{side}_{e['j']:02d}.jpg")
            extract_frame(video, base_ts + e["t_sec"], dest)
            paths.append(dest)
            frames_meta[side].append({"j": e["j"], "t_pct": e["t_pct"],
                                      "t_sec": e["t_sec"], "path": dest})

    images = [Image.open(p).convert("RGB") for p in orig_paths + regen_paths]
    emb = embed_frames(model, processor, device, images)     # (16, 1152) L2 归一
    per_pos = [float(np.dot(emb[j], emb[N_FRAMES + j]))
               for j in range(N_FRAMES)]
    mean = sum(per_pos) / N_FRAMES
    score = round(min(1.0, max(0.0, mean)), 4)               # schema [0,1] + 浮点毛刺钳制

    payload = dict(key)
    payload.update({
        "frames": frames_meta,
        "per_position_cos": [round(c, 6) for c in per_pos],
        "score": score,
        "model": MODEL_LABEL,
        "device": str(device),
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    })
    return payload


# ─── cache（mirror h3_regen cache_read/cache_write 形状）────────────────────

def _scorer_cache_path(shot_id: int, work_dir: str) -> str:
    """cache 元数据路径（SCORER_CACHE_SUBDIR/shot_%03d.json）。"""
    return os.path.join(work_dir, SCORER_CACHE_SUBDIR, f"shot_{shot_id:03d}.json")


def cache_read(shot_id: int, work_dir: str, key: dict) -> dict | None:
    """读 cache：key 五字段与 payload 内字段全等才返回 payload，否则 None
    （缺席/损坏/字段不等一律 miss，绝不部分复用）。"""
    try:
        with open(_scorer_cache_path(shot_id, work_dir), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    for field in _SCORER_KEY_FIELDS:
        if meta.get(field) != key.get(field):
            return None
    return meta


def cache_write(shot_id: int, work_dir: str, payload: dict) -> None:
    """写 cache 元数据（score_shot 已含 scored_at；原子写经 h3s 单源）。"""
    h3s._atomic_write_json(_scorer_cache_path(shot_id, work_dir), payload)


# ─── roundtrip.json scores 半边写入（READ-merge + 浅合并 + 两层自校验）──────

def write_scores_sidecar(work_dir: str, entries: list[dict]) -> list[str]:
    """roundtrip.json scores.midframe_sim 半边写入（mirror h3_regen
    write_roundtrip_sidecar L805-863 逐行形状，差异仅在 merge 粒度）。

    - READ-merge：既有同 shot_id 条目 kept-keys 除 "scores" 全保留（verdict/
      regen/status 原样——Pitfall 8 对偶半边）；
    - scores 子对象**浅合并**：merged_scores = dict(prev.get("scores") or {})
      后 update 新 midframe_sim 子对象——绝不整体替换 scores（不丢 judge 半边）；
    - 写前两层自校验（WR-04）：① 本批 entries 单独校验有错 sys.exit 不落盘；
      ② 合并 payload 校验有错按 absolute_path 归因 shot_id → per-shot str
      warning + 剔除 + 原文件备份 .bak-<ts> → 复验仍错则 sys.exit；
    - schema_version 经 h3s._load_schema_version()（export_asset 单源）。
    返回追加的 per-shot warnings（调用方统一 flush）。"""
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            existing = json.load(f)
    except (OSError, json.JSONDecodeError):
        existing = None
    if not isinstance(existing, dict) or not isinstance(existing.get("shots"), list):
        existing = {"shots": []}
    schema_version = h3s._load_schema_version()
    # ① 本批条目独立校验（fail-loud）
    own_errors = h3s._iter_sidecar_errors({"schema_version": schema_version,
                                           "shots": entries})
    if own_errors:
        detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                           for e in own_errors[:3])
        sys.exit(f"{STEP_TAG} roundtrip.json 本批条目 schema 校验失败"
                 f"（{len(own_errors)} 错误，拒绝落盘）: {detail}")
    merged: dict[int, dict] = {}
    for s in existing["shots"]:
        if isinstance(s, dict) and isinstance(s.get("shot_id"), int):
            merged[int(s["shot_id"])] = s
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("shot_id"), int):
            continue
        sid = int(e["shot_id"])
        prev = merged.get(sid, {})
        kept = {k: v for k, v in prev.items() if k != "scores"}
        merged_scores = dict(prev.get("scores") or {})
        merged_scores.update(e.get("scores") or {})   # 浅合并——只覆盖 midframe_sim
        if merged_scores or isinstance(prev.get("scores"), dict):
            kept["scores"] = merged_scores
        kept.update({k: v for k, v in e.items() if k != "scores"})
        merged[sid] = kept
    payload = {"schema_version": schema_version,
               "shots": [merged[k] for k in sorted(merged)]}
    # ② 合并校验：预存坏条目归因 → warning + 剔除 + 备份
    warnings: list[str] = []
    errors = h3s._iter_sidecar_errors(payload)
    if errors:
        bad_ids: set[int] = set()
        for err in errors:
            parts = list(err.absolute_path)
            if (len(parts) >= 2 and parts[0] == "shots"
                    and isinstance(parts[1], int)
                    and 0 <= parts[1] < len(payload["shots"])):
                shot = payload["shots"][parts[1]]
                if isinstance(shot, dict) and isinstance(shot.get("shot_id"), int):
                    bad_ids.add(int(shot["shot_id"]))
        if not bad_ids:
            detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                               for e in errors[:3])
            sys.exit(f"{STEP_TAG} roundtrip.json schema 校验失败"
                     f"（{len(errors)} 错误，且无法归因到预存条目，拒绝落盘）: {detail}")
        import shutil
        bak = f"{sidecar_path}.bak-{int(time.time())}"
        if os.path.isfile(sidecar_path):
            shutil.copy2(sidecar_path, bak)           # 被剔除条目的人工数据可找回
        for sid in sorted(bad_ids):
            warnings.append(
                f"{STEP_TAG} roundtrip.json 预存条目 shot {sid} 违反当前 schema"
                f"——本次写入已剔除该条目（原文件备份 {os.path.basename(bak)}，"
                f"人工数据未销毁）")
            merged.pop(sid, None)
        payload = {"schema_version": schema_version,
                   "shots": [merged[k] for k in sorted(merged)]}
        errors = h3s._iter_sidecar_errors(payload)
        if errors:
            detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                               for e in errors[:3])
            sys.exit(f"{STEP_TAG} roundtrip.json 剔除预存坏条目后仍校验失败"
                     f"（{len(errors)} 错误，拒绝落盘）: {detail}")
    h3s._atomic_write_json(sidecar_path, payload)
    print(f"{STEP_TAG} roundtrip.json scores 半边已写入（本批 {len(entries)} 镜，"
          f"合计 {len(payload['shots'])} shots，schema 校验通过）")
    return warnings


# ─── 输入装配 ───────────────────────────────────────────────────────────────

def _read_sidecar_shots(work_dir: str) -> list:
    """读 roundtrip.json shots 列表；损坏/缺席/形状不对一律空列表
    （mirror write 侧「视为空重建」语义——挂载前仅 JSON-parse，Phase 18 决策）。"""
    try:
        with open(os.path.join(work_dir, "roundtrip.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("shots"), list):
        return data["shots"]
    return []


def _load_shots_index(work_dir: str) -> dict[int, dict]:
    """shots.json → {id: shot dict}（orig 侧时窗的 start/end/duration 来源）。"""
    with open(os.path.join(work_dir, "shots.json"), encoding="utf-8") as f:
        shots = json.load(f)
    out: dict[int, dict] = {}
    for s in shots:
        if isinstance(s, dict) and isinstance(s.get("id"), int):
            out[int(s["id"])] = s
    return out


def parse_shots_subset(spec: str) -> set[int]:
    """--shots "1,5,47" → {1,5,47}；空串 → 空集（=不过滤）。非法 token
    （非正整数）sys.exit 中文报错。"""
    text = (spec or "").strip()
    if not text:
        return set()
    ids: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            val = int(token)
        except ValueError:
            sys.exit(f"{STEP_TAG} 非法 --shots token {token!r}（应为逗号分隔的正整数）")
        if val < 1:
            sys.exit(f"{STEP_TAG} 非法 --shots token {token!r}（应为 ≥1 的镜 id）")
        ids.add(val)
    return ids


# ─── main ───────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SigLIP 中段帧轨迹相似度打分（SCORE-01）—— 25%-75% 时窗 "
                    "N=8 帧 per-position cosine + mean")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— 读 roundtrip.json/"
                         "shots.json，写 route_cache/scorer/ 与 scores 半边")
    ap.add_argument("--device", default="cuda:0",
                    help="推理设备（默认 cuda:0 = GPU0 3060Ti 零竞争；cuda 加载"
                         "失败自动降 cpu，绝不碰 GPU1——Pitfall 4）")
    ap.add_argument("--shots", default="",
                    help="逗号分隔 shot id 子集（空=全部有 regen 产物的镜）")
    args = ap.parse_args(argv)

    work_dir = args.work_dir
    src_video = h3s.resolve_source_video(work_dir)
    vch = h3s.video_content_hash(src_video)
    shots_index = _load_shots_index(work_dir)
    keep_ids = parse_shots_subset(args.shots)

    pending_warnings: list = []
    candidates: list[tuple[int, dict, str]] = []
    for s in _read_sidecar_shots(work_dir):
        if not isinstance(s, dict) or not isinstance(s.get("shot_id"), int):
            continue
        sid = int(s["shot_id"])
        if keep_ids and sid not in keep_ids:
            continue
        regen = s.get("regen")
        if isinstance(regen, dict) and regen.get("path"):
            regen_path = os.path.join(work_dir, str(regen["path"]))
            if os.path.isfile(regen_path):
                candidates.append((sid, regen, regen_path))
                continue
            pending_warnings.append(
                f"{STEP_TAG} shot {sid}: regen 产物缺席（{regen['path']}），跳过")
            continue
        if isinstance(s.get("status"), dict):
            pending_warnings.append(
                f"{STEP_TAG} shot {sid}: status=failed 条目无产物，跳过打分")
    print(f"{STEP_TAG} vch={vch} 候选镜数={len(candidates)}（device={args.device}）")

    # cache 预判：全 hit 零模型加载（SigLIP 只在存在 miss 时才进内存）。
    keys: dict[int, dict] = {}
    misses: list[tuple[int, dict, str]] = []
    hits = 0
    for sid, regen, regen_path in candidates:
        key = {
            "video_content_hash": vch,
            "regen_mp4_sha256_16": regen_sha16(regen_path),
            "model": MODEL_LABEL,
            "n_frames": N_FRAMES,
            "window": list(WINDOW_PCT),
        }
        keys[sid] = key
        if cache_read(sid, work_dir, key) is not None:
            hits += 1
        else:
            misses.append((sid, regen, regen_path))

    if not misses:
        if pending_warnings:
            h3s.append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} 全部 cache 命中（hit={hits} miss=0）—— 零模型加载，无新分数")
        return 0

    try:
        model, processor, device = load_siglip(args.device)
    except Exception as exc:                          # noqa: BLE001 — degrade 记因不炸批
        pending_warnings.append({
            "code": "scorer_model_missing",
            "detail": f"{type(exc).__name__}: {str(exc)[:300]}"})
        h3s.append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} SigLIP 加载失败（{type(exc).__name__}）—— "
              f"scorer_model_missing degrade，sidecar 原样退出")
        return 0

    new_entries: list[dict] = []
    failed: list[int] = []
    for sid, regen, regen_path in misses:
        shot = shots_index.get(sid)
        if shot is None:
            pending_warnings.append(
                f"{STEP_TAG} shot {sid}: shots.json 无该镜条目，跳过打分")
            continue
        regen_dur = float(regen.get("duration_sec") or 0.0)
        if regen_dur <= 0.0:
            regen_dur = h3s.probe_duration_sec(regen_path)
        try:
            payload = score_shot(model, processor, device, work_dir,
                                 src_video, shot, regen_path, regen_dur, keys[sid])
        except Exception as exc:                      # 单镜失败不阻塞批（h3_regen 先例）
            print(f"{STEP_TAG} shot {sid}: 打分异常失败"
                  f"（{type(exc).__name__}: {str(exc)[:300]}）")
            failed.append(sid)
            continue
        cache_write(sid, work_dir, payload)
        new_entries.append({"shot_id": sid, "scores": {"midframe_sim": {
            "score": payload["score"], "model": MODEL_LABEL}}})
        print(f"{STEP_TAG} shot {sid}: scored sim={payload['score']:.4f}")

    if new_entries:
        sidecar_warnings = write_scores_sidecar(work_dir, new_entries)
        pending_warnings.extend(sidecar_warnings)
    if failed:
        pending_warnings.append(f"{STEP_TAG} failed shots: {failed}")
    if pending_warnings:
        h3s.append_roundtrip_warnings(work_dir, pending_warnings)
    print(f"{STEP_TAG} 完成：hit={hits} miss-scored={len(new_entries)} "
          f"failed={len(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
