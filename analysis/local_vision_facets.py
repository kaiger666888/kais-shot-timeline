#!/usr/bin/env python3
"""本地 qwen-eye VL 填充 prompts.json 的 scene/subject facets（local_vision）

背景：`analysis/call_shot_analysis.py:160-161` 明文把两个 facet 留空——
    subject ← "" 永不伪造（Phase 7 re-id 处理身份）
    scene   ← "" 永不伪造（未来 Qwen-VL 扩展）
本模块就是那条「未来 Qwen-VL 扩展」：用本地 qwen-eye 引擎（Qwen3.8-27B VL，
:8125，见 analysis/engine_clients/qwen_eye_client.py）把空缺的 scene（环境/
场景描述）与 subject（主体**外观描述**）填上。输入复用 step 2 已产的
frames_5fps/ 全帧 jpg —— 零额外抽帧 IO。

facet 边界（不越权）：
  * scene   ← 该镜时窗内首/中/尾 ≤3 帧的 observe_single 观察 → 环境描述文本。
  * subject ← 同上 → **外观描述文本**（"橙黄色绒毛的毛毛虫小孩"），NOT 角色 ID。
    身份归 Phase 7 re-id（registry clusters → attach_refs 的 character_refs），
    本步骤永不写 char_XXX —— 与 call_shot_analysis.py:160 的边界注释一致。

缓存（mirror call_shot_analysis.py:327-334 WR-04 4-tuple 惯例）：
  route_cache/local_vision/shot_XXX.json，_cache_key =
  (video_content_hash, engine_name, engine_version, prompt_version)
  —— 任一不匹配即 miss 重拉。PROMPT_VERSION 是 prompt 变更 → 全量失效旋钮。

graceful-degrade（文档化契约）：引擎不可用（ensure_ready 失败：VRAM 不足 /
启动超时 / server.log 记录 load 失败）→ 所有目标 facet 保持原值（通常 ""），
warnings sidecar 追加 `[vision] engine unavailable (...)`，**exit 0**，
prompts.json 仍写出且 schema 合法（scene/subject 是 type:string 无 minLength）。
单镜 observe 失败 → 该镜该 facet 保持 ""，per-shot warning，不阻塞其余镜。

引擎生命周期（防 13.4GB 泄漏）：main() try/finally 包 ensure_ready …
stop_if_owned —— 崩溃也会停掉自己拉起的 server；预存在 lease 绝不动。

输出：
  1. prompts.json —— 读入现有文件（step 5 产物），只改 scene/subject 两键，
     其余 facets + character_refs/prop_refs/prompt_text 原样保留（additive），
     写前 Draft202012Validator(prompts.schema.json) 自校验（fails loud 惯例），
     原子写（tmp + os.replace）。
  2. route_cache/local_vision/shot_XXX.json —— 每镜引擎响应缓存（含 _cache_key）。
  3. route_cache/warnings.json —— READ-merge-write sidecar（mirror call_reid.py
     非破坏性合并；strip 本 step 上一轮的 [vision] 前缀条目防 self-accumulate）。

用法（被 run_pipeline.py step 5 之后的无编号 pre-step 以 subprocess 调用）：
  python3 analysis/local_vision_facets.py \\
      --shots /abs/path/to/shots.json \\
      --frames-dir /abs/path/to/frames_5fps \\
      --work-dir output/<video-stem>/ \\
      --output output/<video-stem>/prompts.json \\
      [--video /abs/path/to/video.mp4]        # cache key 用；缺席 → "unknown" \\
      [--facet scene,subject] [--no-subject]
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# 引擎客户端是同仓 sibling 包模块（engine_clients/ 无 __init__.py —— 直接
# sys.path 注入其目录 import，mirror 上游「stage 脚本互相不 import，例外：
# 本文件独占拥有这个复制来的客户端」约定）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_clients.qwen_eye_client import (  # noqa: E402
    ENGINE_NAME,
    ENGINE_VERSION,
    QwenEye,
)

# ─── 模块级常量 ─────────────────────────────────────────────────────────────
# cache key 组成部分。PROMPT_VERSION 是 cache-invalidation 旋钮 —— SCENE_PROMPT/
# SUBJECT_PROMPT 文案变了就 bump 此串 → 全部 cache miss（mirror ROUTE_VERSION 惯例）。
CACHE_NAME = "local_vision"
PROMPT_VERSION = "local-vision-v1"

# frames_5fps 抽帧频率（run_pipeline --sample-fps 默认 5.0；detect_v3b 同值）。
# 帧文件名 f%06d.jpg 从 1 起编号：f000001.jpg ≈ t=0s，f000N.jpg ≈ (N-1)/fps。
FRAME_SAMPLING_FPS = 5.0

# 每镜最多取的帧数（首/中/尾）。R11：q3 ctx=16K 单 slot —— 控制单镜调用量。
MAX_FRAMES_PER_SHOT = 3

# 引擎身份写进 warnings —— 便于追溯哪个引擎/版本产的 facet。
STEP_TAG = "[vision]"

SCENE_PROMPT = (
    "请用一句简洁中文描述这一帧的画面场景与环境（地点、空间、背景元素、"
    "时代/世界观线索）。只输出场景描述本身，不要描述角色，不要编号或前缀。"
)

SUBJECT_PROMPT = (
    "请用一句简洁中文描述这一帧中主要可见主体（角色/生物/关键物体）的"
    "外观：种类、体型、颜色、服饰或材质特征。只输出外观描述本身，"
    "不要给出角色名字或编号，不要描述环境。"
)

# prompts.schema.json 绝对路径（写前 Draft202012Validator 自校验用）。
# analysis/local_vision_facets.py → repo root/spec/schemas/prompts.schema.json
PROMPTS_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "prompts.schema.json"


def video_content_hash(video_path: str) -> str:
    """sha256(first_1MB + last_1MB + str(filesize))[:16] —— mirror
    call_shot_analysis.py:91-108（multi-GB 视频毫秒级、确定性 cache key）。"""
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))                    # head 1MB
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)            # 跳到尾部前 1MB
            h.update(f.read(1024 * 1024))                # tail 1MB
    h.update(str(size).encode())                         # 文件大小参与 hash
    return h.hexdigest()[:16]


def select_frames(frames_dir: str, start_sec: float, end_sec: float,
                  max_frames: int = MAX_FRAMES_PER_SHOT) -> list[Path]:
    """取该镜时窗 [start_sec, end_sec] 内的首/中/尾 ≤3 帧。

    frames_5fps 的命名是 f%06d.jpg、编号从 1 起（detect_v3b.sample_frames），
    第 N 帧的时间戳 ≈ (N-1)/FRAME_SAMPLING_FPS。时窗内全部候选先列出，再取
    首/中/尾（时窗内不足 3 帧就有多少取多少；0 帧 → 空列表，调用方 degrade）。
    忽略 `*_ds1280.jpg` 变体帧（dissolve 扫描的旁路产物，非等间隔采样序列）。
    """
    all_frames = sorted(
        p for p in Path(frames_dir).glob("f[0-9]*.jpg")
        if "_ds" not in p.stem
    )
    lo = int(start_sec * FRAME_SAMPLING_FPS) + 1     # 首个 ≥ start 的帧号
    hi = int(end_sec * FRAME_SAMPLING_FPS) + 1       # 最后一个 ≤ end 的帧号上界
    window = [p for p in all_frames
              if lo <= _frame_number(p) <= hi]
    if not window:
        return []
    if len(window) <= max_frames:
        return window
    # 首/中/尾 三点采样 —— 单镜内视觉连续，三点足够覆盖镜内变化。
    mid = (len(window) - 1) // 2
    picks = {0, mid, len(window) - 1}
    return [window[i] for i in sorted(picks)][:max_frames]


def _frame_number(path: Path) -> int:
    """f000123.jpg → 123。文件名不合式（防御）→ -1（永不落进任何时窗）。"""
    digits = path.stem.lstrip("f")
    try:
        return int(digits)
    except ValueError:
        return -1


def _clean_answer(text: str) -> str:
    """引擎回答 → facet 文本：去首尾空白 + 去包裹引号；空/纯标点 → ""。"""
    t = (text or "").strip().strip('"').strip("'").strip()
    return t.strip("。；;.,、") .strip() if t.strip("。；;.,、") else ""


def _read_existing_warnings(sidecar: str) -> list[str]:
    """读现有 warnings sidecar（call_shot_analysis/call_reid 可能已写入）。
    损坏/缺席 → []（不阻塞本步骤）。"""
    if not os.path.exists(sidecar):
        return []
    try:
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("warnings"), list):
        return [w for w in data["warnings"] if isinstance(w, str)]
    return []


def _cache_key(vch: str) -> dict:
    """4-tuple cache key（WR-04 惯例）：video_content_hash + engine_name +
    engine_version + prompt_version 全部参与比对。"""
    return {
        "video_content_hash": vch,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
    }


def main():
    ap = argparse.ArgumentParser(
        description="本地 qwen-eye VL 填充 prompts.json 的 scene/subject facets")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径（含 id/start_sec/end_sec —— 时窗选帧用）")
    ap.add_argument("--frames-dir", required=True,
                    help="frames_5fps/ 目录（step 2 产物，f%06d.jpg 等间隔采样帧）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— route_cache 写在其下")
    ap.add_argument("--output", required=True,
                    help="prompts.json 路径（读入现有 → 只改 scene/subject → 原子写回）")
    ap.add_argument("--video", default=None,
                    help="原始视频路径（cache key 的 video_content_hash 用；"
                         "缺席 → 'unknown'（cache 仍可用，仅跨视频不失效））")
    ap.add_argument("--facet", default="scene,subject",
                    help="要填充的 facet 子集（逗号分隔，默认 scene,subject）")
    ap.add_argument("--no-subject", action="store_true",
                    help="跳过 subject facet（只填 scene）—— subject 外观描述可选")
    args = ap.parse_args()

    facets = [f.strip() for f in args.facet.split(",") if f.strip()]
    facets = [f for f in facets if f in ("scene", "subject")]
    if args.no_subject and "subject" in facets:
        facets.remove("subject")
    if not facets:
        print("[vision] no facets selected (empty --facet / --no-subject) — nothing to do")
        return 0

    # 1. 载入现有 prompts.json（step 5 产物）+ shots 元数据 + cache key
    if not os.path.exists(args.output):
        sys.exit(f"[vision] input prompts.json not found: {args.output} "
                 f"(step 5 must run first — 本步骤是 additive 填充，不从零生成)")
    with open(args.output, encoding="utf-8") as f:
        prompts = json.load(f)
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    vch = video_content_hash(args.video) if args.video and os.path.exists(args.video) else "unknown"

    # 2. cache 目录 + warnings sidecar（READ-merge-write，mirror call_reid）
    cache_dir = os.path.join(args.work_dir, "route_cache", CACHE_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    warnings_sidecar = os.path.join(args.work_dir, "route_cache", "warnings.json")
    existing_warnings = _read_existing_warnings(warnings_sidecar)
    warnings: list[str] = []

    # 3. 引擎生命周期：try/finally 包 ensure_ready…stop_if_owned —— 崩溃也不
    #    泄漏 13.4GB。预存在 lease（healthy 且非我们拉起）绝不停。
    engine = QwenEye()
    filled = {"scene": 0, "subject": 0}
    # Phase 22（22-04 Rule 3）：零 facet 改动 → 完全跳过 prompts.json 原子写，
    # 保住 mtime —— 下游 step_roundtrip 外层 cache（roundtrip.json > prompts.json）
    # 与 step_export 的 mtime cache 都以 prompts 为 input；无条件重写会让两个
    # cache 每次跑都 miss（mirror vision_seq_facets 的 changed-guard 先例）。
    changed = False
    try:
        healthy, _owned = engine.ensure_ready()
        if not healthy:
            # graceful-degrade：目标 facet 保持原值，显式 warning，exit 0。
            msg = (f"{STEP_TAG} engine unavailable "
                   f"(ensure_ready failed: VRAM/startup) — "
                   f"{','.join(facets)} facets left as-is")
            warnings.append(msg)
            print(f"[vision] {msg}")
        else:
            by_id = {s["id"]: s for s in shots_meta}
            for p in prompts:
                sid = p.get("shot_id")
                meta = by_id.get(sid)
                if meta is None:
                    continue
                frames = select_frames(args.frames_dir,
                                       meta["start_sec"], meta["end_sec"])
                if not frames:
                    warnings.append(
                        f"{STEP_TAG} shot {sid}: no frames in window "
                        f"[{meta['start_sec']:.2f}, {meta['end_sec']:.2f}] — "
                        f"facets left as-is")
                    continue
                for facet in facets:
                    if p.get(facet):
                        continue   # 已有值（route/人工产物）—— 不覆盖
                    cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")
                    answer, cached = _facet_cached(cache_file, facet, vch)
                    if answer is None and not cached:
                        answer, err = _ask_facet(engine, frames, facet)
                        if err:
                            warnings.append(f"{STEP_TAG} shot {sid}: {facet}: {err}")
                            continue   # 该镜该 facet degrade，不阻塞其余
                        _write_facet_cache(cache_file, sid, facet, answer, vch)
                    if answer:
                        p[facet] = answer
                        filled[facet] += 1
                        changed = True
                if (sid % 10) == 0:
                    print(f"[vision] {sid}/{len(prompts)} shots processed")
    finally:
        engine.stop_if_owned()

    # 4. 写前 schema 自校验（fails loud —— 防畸形输出流向下游 export/HTML）
    from jsonschema import Draft202012Validator
    with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
        prompts_schema = json.load(f)
    errors = list(Draft202012Validator(prompts_schema).iter_errors(prompts))
    if errors:
        sys.exit(
            f"prompts.json schema validation failed ({len(errors)} errors): "
            + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                        for e in errors[:3]))

    # 5. 原子写 prompts.json（tmp + os.replace —— 防 partial-write 被下游读到）。
    #    零 facet 改动时跳过（保 mtime，见上方 changed 注释）。
    if changed:
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)

    # 6. warnings sidecar —— READ-merge-write。strip 本 step 上一轮的 [vision]
    #    条目再 append fresh（防 self-accumulate，mirror call_reid WR-01）；
    #    他 step 的 warnings 保留（cross-step 非破坏性合并）。
    prior = [w for w in existing_warnings if not w.startswith(STEP_TAG)]
    with open(warnings_sidecar, "w", encoding="utf-8") as f:
        json.dump({"warnings": prior + warnings}, f, ensure_ascii=False, indent=2)

    if changed:
        print(f"[vision] wrote {args.output} "
              f"(scene filled: {filled['scene']}, subject filled: {filled['subject']}, "
              f"{len(warnings)} new warnings)")
    else:
        print(f"[vision] {args.output} unchanged "
              f"(zero facets modified — output not rewritten; "
              f"{len(warnings)} new warnings)")
    return 0


def _facet_cached(cache_file: str, facet: str, vch: str) -> tuple[str | None, bool]:
    """cache lookup。返回 (answer, was_cached)：
      * (answer, True)  —— _cache_key 匹配且该 facet **键存在**于 answers。
      * (None, False)   —— 文件缺失 / key 不匹配（stale）/ 该 facet 键缺席
        （同镜另一 facet 已缓存但本 facet 未问过 —— 必须重拉，不能误判成
        "上次 degrade"）。cache 只写成功答案，故键缺席 = 从未问过。
    """
    if not os.path.exists(cache_file):
        return None, False
    try:
        with open(cache_file, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None, False
    if not isinstance(cached, dict) or cached.get("_cache_key") != _cache_key(vch):
        return None, False
    answers = cached.get("answers") if isinstance(cached.get("answers"), dict) else {}
    if facet not in answers:
        return None, False
    return answers[facet], True


def _write_facet_cache(cache_file: str, sid: int, facet: str,
                       answer: str, vch: str) -> None:
    """写/合并 per-shot cache：同镜多 facet 共享一个 shot_XXX.json（read-
    merge-write，避免 subject 后填时把 scene 的缓存抹掉）。best-effort。"""
    cached: dict = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)
            if not isinstance(cached, dict):
                cached = {}
        except (OSError, json.JSONDecodeError):
            cached = {}
    answers = cached.get("answers") if isinstance(cached.get("answers"), dict) else {}
    answers[facet] = answer
    payload = {"shot_id": sid, "answers": answers, "_cache_key": _cache_key(vch)}
    try:
        tmp = cache_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cache_file)
    except OSError:
        pass   # cache 写失败不阻塞 —— 下次重拉即可


def _ask_facet(engine: QwenEye, frames: list[Path],
               facet: str) -> tuple[str, str | None]:
    """对 ≤3 帧逐帧 observe_single → 取最长回答（信息量最大的一帧）。

    单图调用天然豁免 llama.cpp 多图丢弃 bug（engine client 硬约束 1）。
    返回 (answer, None) 或 ("", err_msg)。
    """
    prompt = SCENE_PROMPT if facet == "scene" else SUBJECT_PROMPT
    best = ""
    for frame in frames:
        try:
            raw = engine.observe_single(frame, prompt)
        except (RuntimeError, OSError) as e:
            return "", f"engine call failed: {e}"
        answer = _clean_answer(raw)
        if len(answer) > len(best):
            best = answer
    if not best:
        return "", "engine returned empty answer for all frames"
    return best, None


if __name__ == "__main__":
    sys.exit(main())
