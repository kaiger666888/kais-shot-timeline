#!/usr/bin/env python3
"""qwen-eye 三分类归因 judge + verdict 冻结应用器（Phase 21 / SCORE-02 +
SCORE-03 + DATASET-01）—— 21-01 离线交付；GPU 真跑在 21-02/21-03 复用同
requirement IDs。

背景
----
双信号中贵的那一路：VLM judge 看「原片段 vs regen」的 2×4 标注 grid 图 +
prompt_text，输出三分类归因（prompt_faithful = prompt 描述了X且渲染出X /
model_diverged = 描述了X渲染成Y（prompt 好）/ prompt_underspecified =
欠约束 h3 自行脑补）——区分「prompt 好 h3 不行」与「prompt 本身欠约束」，
防数据集系统性偏向简单动作（v1.3 立项研究 Pitfall 5）。本模块另承载
--apply-verdict：SCORE-03 校准后按 τ_sim 把双信号合成 verdict 冻结写入
roundtrip.json（rejected 永不删除，DATASET-01）。

算法步骤
--------
judge 批（默认模式）：
1. 读 roundtrip.json 取有 regen.path 的条目（status/failed str warning 跳过）
   + shots.json/prompts.json（经 h3s.load_shot_prompts join prompt_text）；
2. 逐镜 cache 预判（key 四字段：video_content_hash + regen_mp4_sha256_16 +
   engine_name + engine_version；parsed 缺席同样 miss）；全命中零引擎实例化；
3. miss 镜：ffmpeg 提取 4 时位 {0, 1/3, 2/3, 1} ×2 侧 = 8 帧（t=100% 同样
   clamp min(ts, dur-0.2)，Pitfall 3）→ PIL 2×4 grid（列头 ORIGINAL 蓝 /
   REGEN (h3) 绿 + 行标签 t=0%/33%/66%/100% 竖排**进图**——judge 只收一张
   图，列语义只能靠图内文字，T-21-03）→ observe_single 一次调用；
4. 解析容错（glm-structured-output 模式零依赖）：fence 剥离 → 花括号截取 →
   json.loads → enum 三值闭集 / confidence ∈[0,1] / reason ≥10 字符；
   失败重问 ≤2 次且错误码回喂进 question（retry-with-feedback）；attempts
   全记录进 cache；
5. roundtrip.json scores.judge 半边 READ-merge（reason 先 str()[:2000]——
   schema T-18-02 上界）；三连坏 → str warning + 该镜无 judge 分（rc=0）。

--apply-verdict --tau-sim τ：读现存 sidecar（不重跑引擎）——verdict 已存在
的镜跳过（冻结：auto/human 一视同仁）；双信号齐备的镜
accepted ⇔ midframe_sim.score ≥ τ ∧ judge.attribution == prompt_faithful
（硬合取，无 confidence 第二门槛——20 镜定两阈已勉强，加了是伪精度）；
verdict = {decision, source: "auto", decided_at}；信号缺一跳过 + str warning。

--summarize：只读打印 (shot_id, sim, attribution, confidence) 表 + sim 分位
数 p10/25/50/75/90 + attribution 三桶 + τ 候选预演（含 rejected 按归因分桶
——SC4 防偏向审计素材）。

graceful-degrade 语义
---------------------
有 miss 时：comfy_free(comfy_url) best-effort（腾 GPU1，ComfyUI 批后 cache
驻留 ~21GB，Pitfall 4）→ QwenEye() → ensure_ready 返回 (False, ·) → 等 30s
显式重试一次（启动实测恰 120s 贴 LLM_START_TIMEOUT_S 上限，Pitfall 6）→
仍败 → str warning + rc=0（三码 closed enum 无 judge 码，事件性说明走
legacy str 形——h3_regen L316 先例）；try/finally stop_if_owned（13.4GB
lease 崩溃也不泄漏，WR-03）。全 cache 命中 → 零实例化零 HTTP。

cache 惯例
----------
- 元数据 work_dir/route_cache/judge/shot_{NNN}.json；hit = key 四字段全等
  **且** parsed 为 dict（解析失败产物不算命中，重跑必重问）；
- payload 另存 grid{path,w,h}（相对路径，SC3 抽检素材指针）+ attempts
  [{parse, raw_len}]（重问审计）+ parsed + judged_at；
- grid 实体落 roundtrip/_judge_grids/shot_{NNN}.jpg（mirror 20-03
  roundtrip/_compare/ 先例）。

argv 用法
---------
    python3 analysis/roundtrip/judge.py --work-dir output/<video-stem>/ \
        [--comfy-url http://127.0.0.1:8188] [--shots 1,5,47]
    python3 analysis/roundtrip/judge.py --work-dir <dir> --apply-verdict --tau-sim 0.92
    python3 analysis/roundtrip/judge.py --work-dir <dir> --summarize
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# engine_clients 是唯一被 sanction 的跨模块 import（PATTERNS §A）。本模块在
# analysis/roundtrip/ 下比 vision_seq_facets.py 深一层——repo 的 analysis/
# 必须 parent.parent（off-by-one 陷阱）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine_clients.qwen_eye_client import (  # noqa: E402
    ENGINE_NAME, ENGINE_VERSION, QwenEye,
)

# h3_regen 共享件经 importlib 文件加载（单源不漂移；模块级无副作用、main 有
# guard，加载安全）。用 h3s.append_roundtrip_warnings / _atomic_write_json /
# comfy_free / probe_duration_sec / _iter_sidecar_errors / _load_schema_version /
# COMFY_URL_DEFAULT / resolve_source_video / video_content_hash / load_shot_prompts。
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)

# ─── 模块级常量 ─────────────────────────────────────────────────────────────

STEP_TAG = "[roundtrip]"          # 与 h3_regen/scorer 同 tag（warnings strip 语义共用）

# 三分类 closed enum（schema 同款；机器可 grep——SCORE-03 rejected 占比审计）。
ATTRIBUTIONS = ("prompt_faithful", "model_diverged", "prompt_underspecified")

# grid 几何（RESEARCH Pattern 3 探针值：canvas 1370×1476 ≈2.0M px，
# token 预算锚 = vision_seq 曾以 1920×1080 单图 147 calls 无碍）。
GRID_T_PCT = (0.0, 1 / 3, 2 / 3, 1.0)
GRID_ROW_LABELS = ("t=0%", "t=33%", "t=66%", "t=100%")
CELL_W = 640                      # 16:9 等比 cell（1920×1080 降采样）
CELL_H = 360
ROWLBL_W = 90                     # 行标签列宽 → canvas W = 90 + 640*2 = 1370
HDR_H = 36                        # 列头条高 → canvas H = 36 + 360*4 = 1476
COL_ORIG = (88, 166, 255)         # ORIGINAL 列头（#58a6ff GitHub-dark 蓝）
COL_REGEN = (63, 185, 80)         # REGEN (h3) 列头（#3fb950 GitHub-dark 绿）
COL_TEXT = (230, 237, 243)        # 行标签前景
BG = (13, 17, 23)                 # canvas 底色（#0d1117）

# 端点防越界 clamp（与 scorer 同值 0.2s，本地声明——两模块不互相 import，
# PATTERNS 惯例；一手实测：175f/24fps regen 流末帧起点 7.25s，-ss 7.252 越界）。
ENDPOINT_GUARD_SEC = 0.2

JUDGE_CACHE_SUBDIR = "route_cache/judge"
JUDGE_FRAMES_SUBDIR = "route_cache/judge/frames"
GRIDS_SUBDIR = "roundtrip/_judge_grids"

# 失败重问上限（1 次主问 + 2 次重问）。
MAX_RETRIES = 2

# cache key 四字段（引擎身份 × regen 产物身份 × 源视频身份）。
_JUDGE_KEY_FIELDS = ("video_content_hash", "regen_mp4_sha256_16",
                     "engine_name", "engine_version")


# ─── grid 时窗 / 帧提取 ─────────────────────────────────────────────────────

def grid_ts(duration_sec: float) -> list[float]:
    """4 时位时间戳：ts = dur·pct（pct ∈ {0, 1/3, 2/3, 1}），各 clamp
    min(ts, max(dur-ENDPOINT_GUARD_SEC, 0.0))——t=100% 帧在 regen mp4 上
    必然贴末帧起点，不 clamp 会取空（Pitfall 3 实测：dur=7.2917 → 7.0917）。"""
    dur = float(duration_sec)
    cap = max(dur - ENDPOINT_GUARD_SEC, 0.0)
    return [min(dur * pct, cap) for pct in GRID_T_PCT]


def _stderr_snip(proc, limit: int = 200) -> str:
    """subprocess stderr 片段（WR-05 fail-loud detail 诊断信息；mirror
    h3_regen L378-384 语义，本地副本）。"""
    raw = getattr(proc, "stderr", None) or ""
    if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
    return raw[:limit]


def extract_frame(video: str, ts_sec: float, dest: str) -> None:
    """ffmpeg 提取单帧（list-form；先删旧 dest；rc/存在/大小三重 fail-loud
    ——mirror h3_regen extract_endpoint_frames 的 WR-05 形状，本地副本）。"""
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
    """regen mp4 sha256 前 16 hex（cache key 身份维，Pitfall 7）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()[:16]


def build_grid(orig_frames: list, regen_frames: list, dest: str) -> tuple[int, int]:
    """2×4 标注 grid 拼图（纯 PIL，零 GPU）：左列 ORIGINAL / 右列 REGEN (h3)，
    四行 t=0%/33%/66%/100%。**标签必须进图**（judge 只收一张图，列语义只能
    靠图内文字——CONTEXT 明示；27B 实测正确解读后 reason 能对照中段帧，
    T-21-03）。cell 统一 resize 到 640×360；存 JPEG quality 90。返回 (w, h)。"""
    from PIL import Image, ImageDraw                     # 延迟（纯本模块用）
    w = ROWLBL_W + CELL_W * 2
    h = HDR_H + CELL_H * 4
    canvas = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((ROWLBL_W + CELL_W // 2, HDR_H // 2), "ORIGINAL",
              fill=COL_ORIG, anchor="mm")
    draw.text((ROWLBL_W + CELL_W + CELL_W // 2, HDR_H // 2), "REGEN (h3)",
              fill=COL_REGEN, anchor="mm")
    for r in range(4):
        y = HDR_H + r * CELL_H
        draw.text((ROWLBL_W // 2, y + CELL_H // 2), GRID_ROW_LABELS[r],
                  fill=COL_TEXT, anchor="mm")
        cell_o = Image.open(str(orig_frames[r])).convert("RGB").resize(
            (CELL_W, CELL_H))
        cell_r = Image.open(str(regen_frames[r])).convert("RGB").resize(
            (CELL_W, CELL_H))
        canvas.paste(cell_o, (ROWLBL_W, y))
        canvas.paste(cell_r, (ROWLBL_W + CELL_W, y))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    canvas.save(dest, "JPEG", quality=90)
    return w, h


# ─── 提示词 / 解析容错（RESEARCH Pattern 2 探针 5/5 实测，逐字落地）────────

def build_question(prompt_text: str, parse_err: str | None = None) -> str:
    """三分类提示词：定义逐字 + JSON 模板 + reason 证据指令 + 本镜 prompt_text。
    parse_err 非空时（重问轮）附「上一次回答无效」回喂——retry-with-feedback。
    prompt_text 只进 HTTP JSON body（observe_single 的 question 参数），绝不
    进任何 subprocess argv（T-20-01 延续）。"""
    lines = [
        "你是视频复现质量评审（round-trip judge）。",
        "下图左列 ORIGINAL 是原片帧、右列 REGEN (h3) 是文生视频模型按 prompt 重新生成的帧，",
        "四行从上到下分别是 t=0% / t=33% / t=66% / t=100% 时位。",
        "请对 REGEN 相对 prompt 的归因做三分类判定：",
        "  - prompt_faithful：prompt 描述了X且渲染出X（REGEN 忠实呈现了 prompt 所述内容）",
        "  - model_diverged：描述了X渲染成Y（prompt 好、明确充分，是模型执行走样）",
        "  - prompt_underspecified：prompt 欠约束，h3 自行脑补（prompt 没写清的关键细节由模型自由发挥）",
        "判定以 t=33%/66% 中段行为为主要证据（t=0%/100% 端点帧仅作构图与 condition 参考）。",
        "只输出一个 JSON 对象（不要输出模板以外的任何文字）：",
        '  {"attribution": "prompt_faithful" | "model_diverged" | "prompt_underspecified", '
        '"confidence": 0.0到1.0的小数, "reason": "中文归因理由"}',
        "reason 必须引用 prompt 原文中的具体短语作为证据。",
        "",
        "本镜 prompt_text：",
        str(prompt_text),
    ]
    q = "\n".join(lines)
    if parse_err:
        q += (f"\n\n上一次回答无效：{parse_err}。"
              f"请严格只输出符合上述模板的 JSON，attribution 必须是三个枚举值之一。")
    return q


def parse_judge_answer(txt: str) -> tuple[dict | None, str]:
    """解析 judge 回答 → (obj | None, code)。六码：no-brace / json:<msg> /
    enum / conf-range / reason-short / ok。fence 剥离 → 花括号截取 → 严格
    校验（enum 三值闭集 / confidence ∈[0,1] / reason ≥10 字符——比 schema
    minLength 1 更严，短 reason 无证据价值）。"""
    t = re.sub(r"```(?:json)?", "", txt.strip()).strip("` \n")
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None, "no-brace"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, f"json:{e.msg[:40]}"
    if not isinstance(obj, dict) or obj.get("attribution") not in ATTRIBUTIONS:
        return None, "enum"
    c = obj.get("confidence")
    # bool 是 int 子类：JSON true 会伪装成 confidence=1.0 绕过数值校验、
    # 进 sidecar 后被 schema 的 number 类型拒收——显式排除（Rule 2 补漏）。
    if (not isinstance(c, (int, float)) or isinstance(c, bool)
            or not (0.0 <= c <= 1.0)):
        return None, "conf-range"
    r = str(obj.get("reason") or "")
    if len(r) < 10:
        return None, "reason-short"
    return obj, "ok"


def run_judge_shot(engine, grid_path: str,
                   prompt_text: str) -> tuple[dict | None, list[dict]]:
    """单镜 judge：最多 1+2 次 observe_single（max_tokens 2000），每次 parse
    后记 {parse: code, raw_len}；成功即停；错误码回喂进下一问。引擎调用异常
    （瞬态重试后仍失败）按 error:<类型> 记 attempts 继续重问。返回
    (parsed | None, attempts)。"""
    attempts: list[dict] = []
    parsed: dict | None = None
    parse_err: str | None = None
    for i in range(1 + MAX_RETRIES):
        question = build_question(prompt_text, parse_err if i > 0 else None)
        try:
            raw = engine.observe_single(Path(grid_path), question,
                                        max_tokens=2000)
        except Exception as exc:                          # noqa: BLE001 — 瞬态降级继续重问
            code = f"error:{type(exc).__name__}"
            attempts.append({"parse": code, "raw_len": 0})
            parse_err = code
            continue
        parsed, code = parse_judge_answer(raw)
        attempts.append({"parse": code, "raw_len": len(raw)})
        if parsed is not None:
            break
        parse_err = code
    return parsed, attempts


# ─── sidecar 写入（Pattern 4 冻结 merge + 两层自校验）───────────────────────

def _utc_now_iso() -> str:
    """UTC ISO-8601 秒精度（decided_at/judged_at 留档）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _merge_write_sidecar(work_dir: str, entries: list[dict]) -> list[str]:
    """roundtrip.json READ-merge 写入（mirror h3_regen write_roundtrip_sidecar
    L805-863 两层自校验形状；merge 核心 = RESEARCH Pattern 4 冻结骨架）：

    - kept-keys：既有条目除 "scores" 外全保留（verdict/regen/status 原样）；
    - verdict 冻结：预存 verdict（auto 或 human）的镜，新条目的 verdict 先
      pop——永不覆盖（SC5：rejected 永续 + human verdict 防意外覆盖）；
    - scores 子对象浅合并：prev.scores 与新 scores 合并保留两侧半边
      （scorer 写 midframe_sim 不丢 judge，judge 写 judge 不丢 midframe_sim）；
    - ① 本批 entries 单独校验有错 sys.exit（fail-loud）；② 合并 payload 有错
      按归因 shot_id 剔除 + .bak-<ts> 备份 + str warning（WR-04 防重试死锁）。
    """
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            existing = json.load(f)
    except (OSError, json.JSONDecodeError):
        existing = None
    if not isinstance(existing, dict) or not isinstance(existing.get("shots"), list):
        existing = {"shots": []}
    schema_version = h3s._load_schema_version()
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
        if isinstance(prev.get("verdict"), dict):
            e.pop("verdict", None)                # 冻结：已有 verdict 永不覆盖
        kept = {k: v for k, v in prev.items() if k != "scores"}
        merged_scores = dict(prev.get("scores") or {})
        merged_scores.update(e.get("scores") or {})
        if merged_scores or isinstance(prev.get("scores"), dict):
            kept["scores"] = merged_scores
        kept.update({k: v for k, v in e.items() if k != "scores"})
        merged[sid] = kept
    payload = {"schema_version": schema_version,
               "shots": [merged[k] for k in sorted(merged)]}
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
            shutil.copy2(sidecar_path, bak)
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
    return warnings


def write_judge_sidecar(work_dir: str, entries: list[dict]) -> list[str]:
    """scores.judge 半边写入（结构 mirror scorer.write_scores_sidecar；差异
    仅在子对象 key）。调用方保证 reason 已 str()[:2000] 截断。"""
    return _merge_write_sidecar(work_dir, entries)


# ─── cache（mirror h3_regen cache_read/cache_write 形状）────────────────────

def _judge_cache_path(shot_id: int, work_dir: str) -> str:
    return os.path.join(work_dir, JUDGE_CACHE_SUBDIR, f"shot_{shot_id:03d}.json")


def cache_read(shot_id: int, work_dir: str, key: dict) -> dict | None:
    """读 cache：key 四字段全等**且** parsed 是 dict 才返回 payload（解析
    失败/缺席的产物不算命中——重跑必重问）；缺席/损坏一律 miss。"""
    try:
        with open(_judge_cache_path(shot_id, work_dir), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    for field in _JUDGE_KEY_FIELDS:
        if meta.get(field) != key.get(field):
            return None
    if not isinstance(meta.get("parsed"), dict):
        return None
    return meta


def cache_write(shot_id: int, work_dir: str, payload: dict) -> None:
    h3s._atomic_write_json(_judge_cache_path(shot_id, work_dir), payload)


# ─── verdict 应用器（SCORE-03 / DATASET-01）─────────────────────────────────

def apply_verdict(work_dir: str, tau_sim: float) -> dict:
    """读现存 roundtrip.json（不重跑引擎）→ 逐条判定 → 冻结 merge 写入。

    规则：verdict 已存在的镜跳过（冻结，auto/human 一视同仁）；双信号齐备
    的镜 accepted ⇔ midframe_sim.score ≥ τ ∧ attribution == prompt_faithful
    （硬合取）；信号缺一（无 sim 或无 judge）跳过 + str warning 列 shot_id。
    verdict = {decision, source: "auto", decided_at: UTC ISO}。
    返回 {applied, frozen, skipped_missing, accepted, rejected}。"""
    try:
        with open(os.path.join(work_dir, "roundtrip.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = None
    shots: list = []
    if isinstance(data, dict) and isinstance(data.get("shots"), list):
        shots = data["shots"]

    pending_warnings: list[str] = []
    entries: list[dict] = []
    frozen: list[int] = []
    skipped_missing: list[int] = []
    accepted = 0
    rejected = 0
    for s in shots:
        if not isinstance(s, dict) or not isinstance(s.get("shot_id"), int):
            continue
        sid = int(s["shot_id"])
        if isinstance(s.get("verdict"), dict):
            frozen.append(sid)
            continue
        scores = s.get("scores") if isinstance(s.get("scores"), dict) else {}
        sim_obj = scores.get("midframe_sim") if isinstance(
            scores.get("midframe_sim"), dict) else {}
        sim = sim_obj.get("score")
        judge_obj = scores.get("judge") if isinstance(
            scores.get("judge"), dict) else {}
        attribution = judge_obj.get("attribution")
        if (not isinstance(sim, (int, float)) or isinstance(sim, bool)
                or attribution not in ATTRIBUTIONS):
            skipped_missing.append(sid)
            continue
        faithful = attribution == "prompt_faithful"
        decision = "accepted" if (float(sim) >= float(tau_sim) and faithful) \
            else "rejected"
        entries.append({"shot_id": sid, "verdict": {
            "decision": decision,
            "source": "auto",
            "decided_at": _utc_now_iso(),
        }})
        if decision == "accepted":
            accepted += 1
        else:
            rejected += 1

    if entries:
        pending_warnings.extend(_merge_write_sidecar(work_dir, entries))
    for sid in skipped_missing:
        pending_warnings.append(
            f"{STEP_TAG} shot {sid}: 双信号缺一（midframe_sim/judge 不齐），"
            f"verdict 跳过")
    if pending_warnings:
        h3s.append_roundtrip_warnings(work_dir, pending_warnings)
    return {"applied": len(entries), "frozen": len(frozen),
            "skipped_missing": skipped_missing,
            "accepted": accepted, "rejected": rejected}


# ─── 汇总（SCORE-03 校准素材汇编器）────────────────────────────────────────

def summarize_scores(pairs: list, taus: list | None = None) -> dict:
    """双信号汇总：{n, quantiles, buckets, tau_preview}。

    - pairs：[(sim | None, attribution | None), ...]（sim/attribution 缺席
      的镜也计入 n——分布的分母要如实）；
    - quantiles：sim 分位数 p10/25/50/75/90，线性插值
      （statistics.quantiles(method="inclusive")，与 numpy linear 同义；
      19 值小样本排序索引即可，此处写明方法）；
    - buckets：attribution 三桶计数（含信号缺席归 None 不进桶）；
    - tau_preview：各候选 τ 下 accepted/rejected 计数 + rejected 按归因分桶
      （faithful-but-sim<τ / model_diverged / prompt_underspecified——SC4
      防偏向审计的机器可 grep 面）。taus 缺省 = 数据内排序去重 sim 值。"""
    import statistics
    def _is_num(x) -> bool:
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    sims = [float(s) for s, _ in pairs if _is_num(s)]
    attribs = [a for _, a in pairs if a in ATTRIBUTIONS]
    buckets = {a: attribs.count(a) for a in ATTRIBUTIONS}

    quantiles: dict[str, float | None] = {"p10": None, "p25": None,
                                          "p50": None, "p75": None,
                                          "p90": None}
    if len(sims) >= 2:
        qs = statistics.quantiles(sims, n=100, method="inclusive")
        quantiles = {"p10": round(qs[9], 4), "p25": round(qs[24], 4),
                     "p50": round(qs[49], 4), "p75": round(qs[74], 4),
                     "p90": round(qs[89], 4)}

    both = [(float(s), a) for s, a in pairs if _is_num(s) and a in ATTRIBUTIONS]
    if taus is None:
        taus = sorted({s for s, _ in both})
    tau_preview: list[dict] = []
    for tau in taus:
        rej_buckets = {
            "prompt_faithful": sum(1 for s, a in both
                                   if a == "prompt_faithful" and s < tau),
            "model_diverged": sum(1 for s, a in both
                                  if a == "model_diverged"),
            "prompt_underspecified": sum(1 for s, a in both
                                         if a == "prompt_underspecified"),
        }
        tau_preview.append({
            "tau": tau,
            "accepted": sum(1 for s, a in both
                            if s >= tau and a == "prompt_faithful"),
            "rejected": sum(rej_buckets.values()),
            "rejected_by_bucket": rej_buckets,
        })
    return {"n": len(pairs), "quantiles": quantiles, "buckets": buckets,
            "tau_preview": tau_preview}


def _print_summary_block(summary: dict, rows: list) -> None:
    """--summarize 的可粘贴报告文本块（镜表 + 分位数 + 分桶 + τ 预演）。"""
    print(f"{STEP_TAG} ── 双信号汇总（n={summary['n']}）──")
    print(f"{STEP_TAG} shot_id | sim | attribution | confidence")
    for row in rows:
        sim_s = f"{row['sim']:.4f}" if isinstance(row["sim"], (int, float)) else "-"
        conf_s = f"{row['confidence']:.2f}" if isinstance(
            row["confidence"], (int, float)) else "-"
        print(f"{STEP_TAG} {row['shot_id']:>7} | {sim_s} | "
              f"{row['attribution'] or '-':<21} | {conf_s}")
    q = summary["quantiles"]
    print(f"{STEP_TAG} sim 分位数（线性插值）: "
          + " ".join(f"{k}={v}" for k, v in q.items()))
    b = summary["buckets"]
    print(f"{STEP_TAG} attribution 分桶: prompt_faithful={b['prompt_faithful']} "
          f"model_diverged={b['model_diverged']} "
          f"prompt_underspecified={b['prompt_underspecified']}")
    print(f"{STEP_TAG} τ 候选预演（accepted ⇔ sim ≥ τ ∧ prompt_faithful）:")
    for t in summary["tau_preview"]:
        rb = t["rejected_by_bucket"]
        print(f"{STEP_TAG}   τ={t['tau']:.4f} accepted={t['accepted']} "
              f"rejected={t['rejected']}"
              f"（faithful<τ={rb['prompt_faithful']} / "
              f"diverged={rb['model_diverged']} / "
              f"underspecified={rb['prompt_underspecified']}）")


# ─── 输入装配 ───────────────────────────────────────────────────────────────

def _read_sidecar_shots(work_dir: str) -> list:
    """读 roundtrip.json shots 列表（损坏/缺席 → 空列表，mirror scorer）。"""
    try:
        with open(os.path.join(work_dir, "roundtrip.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("shots"), list):
        return data["shots"]
    return []


def parse_shots_subset(spec: str) -> set[int]:
    """--shots "1,5,47" → {1,5,47}；空串 → 空集（mirror scorer 同款校验）。"""
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
        description="qwen-eye 三分类归因 judge + verdict 冻结应用器"
                    "（SCORE-02/03 + DATASET-01）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— 读 roundtrip.json/"
                         "shots.json/prompts.json，写 route_cache/judge/ 与 scores/verdict 半边")
    ap.add_argument("--comfy-url", default=h3s.COMFY_URL_DEFAULT,
                    help=f"ComfyUI API 基址（默认 {h3s.COMFY_URL_DEFAULT}；"
                         f"judge 启动前 best-effort POST /free 腾 GPU1）")
    ap.add_argument("--shots", default="",
                    help="逗号分隔 shot id 子集（空=全部有 regen 产物的镜）")
    ap.add_argument("--apply-verdict", action="store_true",
                    help="verdict 应用模式：读现存双信号按硬合取出 verdict 冻结"
                         "写入（不重跑引擎；需 --tau-sim）")
    ap.add_argument("--tau-sim", type=float, default=None,
                    help="SCORE-03 校准锁定的 τ_sim 阈值（--apply-verdict 时必填）")
    ap.add_argument("--summarize", action="store_true",
                    help="只读汇总模式：打印双信号表/分位数/分桶/τ 预演，不写盘")
    args = ap.parse_args(argv)

    work_dir = args.work_dir

    # ── verdict 应用模式（SCORE-03/DATASET-01）──
    if args.apply_verdict:
        if args.tau_sim is None:
            sys.exit(f"{STEP_TAG} --apply-verdict 需要 --tau-sim <τ>（SCORE-03 "
                     f"校准后的 midframe_sim 阈值，accepted ⇔ sim ≥ τ ∧ "
                     f"prompt_faithful）")
        result = apply_verdict(work_dir, args.tau_sim)
        print(f"{STEP_TAG} verdict 应用完成：applied={result['applied']} "
              f"frozen={result['frozen']} skipped={len(result['skipped_missing'])} "
              f"accepted={result['accepted']} rejected={result['rejected']}"
              f"（τ_sim={args.tau_sim}）")
        return 0

    sidecar_shots = _read_sidecar_shots(work_dir)

    # ── 只读汇总模式（SCORE-03 校准素材）──
    if args.summarize:
        rows = []
        pairs = []
        for s in sidecar_shots:
            if not isinstance(s, dict) or not isinstance(s.get("shot_id"), int):
                continue
            scores = s.get("scores") if isinstance(s.get("scores"), dict) else {}
            sim_obj = scores.get("midframe_sim") if isinstance(
                scores.get("midframe_sim"), dict) else {}
            judge_obj = scores.get("judge") if isinstance(
                scores.get("judge"), dict) else {}
            sim = sim_obj.get("score") if isinstance(
                sim_obj.get("score"), (int, float)) else None
            rows.append({"shot_id": int(s["shot_id"]), "sim": sim,
                         "attribution": judge_obj.get("attribution"),
                         "confidence": judge_obj.get("confidence")})
            pairs.append((sim, judge_obj.get("attribution")))
        _print_summary_block(summarize_scores(pairs), rows)
        return 0

    # ── judge 批模式（SCORE-02）──
    src_video = h3s.resolve_source_video(work_dir)
    vch = h3s.video_content_hash(src_video)
    shot_prompts, join_warnings = h3s.load_shot_prompts(work_dir)
    shots_by_id = {int(s["id"]): s for s in shot_prompts}
    keep_ids = parse_shots_subset(args.shots)

    pending_warnings: list = list(join_warnings)
    candidates: list[tuple[int, dict, str]] = []
    for s in sidecar_shots:
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
                f"{STEP_TAG} shot {sid}: status=failed 条目无产物，跳过 judge")
    print(f"{STEP_TAG} vch={vch} 候选镜数={len(candidates)}")

    # cache 预判：全命中零引擎实例化（mirror vision_seq L564-567 预判）。
    keys: dict[int, dict] = {}
    misses: list[tuple[int, dict, str]] = []
    hits = 0
    for sid, regen, regen_path in candidates:
        key = {
            "video_content_hash": vch,
            "regen_mp4_sha256_16": regen_sha16(regen_path),
            "engine_name": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
        }
        keys[sid] = key
        if cache_read(sid, work_dir, key) is not None:
            hits += 1
        else:
            misses.append((sid, regen, regen_path))

    if not misses:
        if pending_warnings:
            h3s.append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} 全部 cache 命中（hit={hits} miss=0）—— 零引擎实例化")
        return 0

    # 引擎编排：comfy_free best-effort 腾 GPU1 → QwenEye → ensure_ready 失败
    # 等 30s 重试一次 → 仍败 str warning + rc=0；finally stop_if_owned。
    h3s.comfy_free(args.comfy_url)
    engine = QwenEye()
    healthy = False
    try:
        healthy, _owned = engine.ensure_ready(timeout_s=120)
        if not healthy:
            print(f"{STEP_TAG} ensure_ready 首次失败 —— 等 30s 显式重试一次"
                  f"（启动实测贴 120s 上限，Pitfall 6）")
            time.sleep(30)
            healthy, _owned = engine.ensure_ready(timeout_s=120)
        if not healthy:
            pending_warnings.append(
                f"{STEP_TAG} qwen-eye 引擎不可用（重试 1 次后仍失败）—— "
                f"judge 批 graceful-degrade，sidecar 原样")
            h3s.append_roundtrip_warnings(work_dir, pending_warnings)
            print(f"{STEP_TAG} 引擎不可达 —— degrade 退出（rc=0）")
            return 0

        new_entries: list[dict] = []
        failed: list[int] = []
        for sid, regen, regen_path in misses:
            shot = shots_by_id.get(sid)
            if shot is None:
                pending_warnings.append(
                    f"{STEP_TAG} shot {sid}: shots.json/prompts.json 无该镜条目，跳过")
                continue
            try:
                regen_dur = float(regen.get("duration_sec") or 0.0)
                if regen_dur <= 0.0:
                    regen_dur = h3s.probe_duration_sec(regen_path)
                dur = float(shot.get("duration")
                            or (float(shot.get("end_sec", 0.0))
                                - float(shot.get("start_sec", 0.0))))
                start = float(shot.get("start_sec", 0.0))
                frames_dir = os.path.join(work_dir, JUDGE_FRAMES_SUBDIR)
                os.makedirs(frames_dir, exist_ok=True)
                orig_ts = grid_ts(dur)
                regen_ts = grid_ts(regen_dur)
                orig_paths: list[str] = []
                regen_paths: list[str] = []
                for j in range(len(GRID_T_PCT)):
                    dest_o = os.path.join(
                        frames_dir, f"shot_{sid:03d}_orig_{j}.jpg")
                    extract_frame(src_video, start + orig_ts[j], dest_o)
                    orig_paths.append(dest_o)
                    dest_r = os.path.join(
                        frames_dir, f"shot_{sid:03d}_regen_{j}.jpg")
                    extract_frame(regen_path, regen_ts[j], dest_r)
                    regen_paths.append(dest_r)
                grid_rel = f"{GRIDS_SUBDIR}/shot_{sid:03d}.jpg"
                grid_abs = os.path.join(work_dir, grid_rel)
                gw, gh = build_grid(orig_paths, regen_paths, grid_abs)
                parsed, attempts = run_judge_shot(engine, grid_abs,
                                                  shot["prompt_text"])
                if parsed is None:
                    pending_warnings.append(
                        f"{STEP_TAG} shot {sid}: judge 三连坏（attempts="
                        f"{[a['parse'] for a in attempts]}）—— 该镜无 judge 分")
                    failed.append(sid)
                    continue
                payload = dict(keys[sid])
                payload.update({
                    "grid": {"path": grid_rel, "w": gw, "h": gh},
                    "attempts": attempts,
                    "parsed": parsed,
                    "judged_at": _utc_now_iso(),
                })
                cache_write(sid, work_dir, payload)
                new_entries.append({"shot_id": sid, "scores": {"judge": {
                    "attribution": parsed["attribution"],
                    "confidence": float(parsed["confidence"]),
                    "reason": str(parsed.get("reason") or "")[:2000],
                }}})
                print(f"{STEP_TAG} shot {sid}: judged "
                      f"{parsed['attribution']} (conf={parsed['confidence']})")
            except Exception as exc:              # 单镜失败不阻塞批（h3_regen 先例）
                print(f"{STEP_TAG} shot {sid}: judge 异常失败"
                      f"（{type(exc).__name__}: {str(exc)[:300]}）")
                failed.append(sid)
                continue
    finally:
        engine.stop_if_owned()                    # 13.4GB lease 崩溃也不泄漏

    if new_entries:
        sidecar_warnings = write_judge_sidecar(work_dir, new_entries)
        pending_warnings.extend(sidecar_warnings)
    if failed:
        pending_warnings.append(f"{STEP_TAG} judge failed shots: {failed}")
    if pending_warnings:
        h3s.append_roundtrip_warnings(work_dir, pending_warnings)
    print(f"{STEP_TAG} 完成：hit={hits} miss-judged={len(new_entries)} "
          f"failed={len(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
