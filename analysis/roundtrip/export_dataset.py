#!/usr/bin/env python3
"""analysis/roundtrip/export_dataset.py — accepted 子集独立 dataset 目录导出
（RT-05 + DATASET-02；22-03 将作为 step_export 后 plain-label post-step 挂载，
本模块自身 standalone 可跑）。

把 roundtrip.json 冻结 verdict 的 accepted 子集导出为消费端零契约依赖的
SFT-grade 数据集目录：

    <dataset-root>/<video-stem>/
        shot_NNN/{first_frame.jpg, last_frame.jpg, prompt.json}   # accepted 镜
        manifest.json          # τ/引擎版本/计数/rejected 分桶/shots 索引
        accepted.txt           # 每行一个 shot_NNN（仅本轮实际导出成功的镜——WR-01：
                               # 降级跳过的镜不进索引，单列 manifest.exported_skipped）
        rejected.txt           # 每行 `shot_NNN sim={:.4f} {attribution} {reason 前 80 字符}`

关键设计（CONTEXT locked decisions）：
    * prompt.json **自含可独立消费**——prompt_text + 六 facet + refs（缺席空
      列表）+ scores 整块 + attribution 冗余直取 + regen 四字段（engine_name/
      engine_version/prompt_version/video_content_hash，刻意不含 path）。dataset
      目录内零 asset.json/roundtrip/ 路径引用，帧为 copy2 拷贝非 symlink
      （RT-05 消费端独立性）。
    * 首尾帧两级来源（PATTERNS §B——绝不手搓 ffmpeg 时窗提取）：优先直拷
      route_cache/h3_regen/frames/kst_{vch}_shot{NNN:03d}_{ff,lf}.jpg（字节
      即 h3 实喂帧）；缺席回落 h3s.extract_endpoint_frames（同一实现=同分辨率
      同 q:v 2 确定性，产物回填 cache 后改名落 dataset）。
    * manifest rejected 分桶从冻结 verdict+scores **直接统计不重算**（mirror
      judge.summarize_scores 分桶命名：faithful_below_tau / diverged /
      underspecified——DATASET-02 hard-negative 索引可审计）。
    * 幂等重建：重跑整目录自重建——不在当前 accepted 集的 shot_NNN 目录被清
      （**显式清单删自身目录，绝不 glob/rmtree 父级**，T-22-09/T-14-01）；
      dataset-root 下其它 video-stem 目录不碰。
    * graceful：roundtrip.json 缺席/损坏 → 打印 warning 退出 0（post-step
      语义，不炸管线）；sidecar 坏条目经 h3s._iter_sidecar_errors 过滤 +
      warning 跳过，不炸整批。
    * **禁**：为 dataset 产物建 schema（dataset 不是契约面——RESEARCH
      Pattern 6）；symlink；dataset 文件内引用 asset.json 或 roundtrip/。

用法：
    python3 analysis/roundtrip/export_dataset.py \\
        --work-dir     <abs path>   (必填 — output/<video-stem>/，roundtrip.json 所在) \\
        --dataset-root <abs path>   (可选 — 默认 work_dir.parent/"dataset" 即 output/dataset/；跨视频可累积集合根) \\
        --tau-sim      <float>      (可选 — 默认 0.9670，仅 manifest 记录用；判定已在 judge 冻结)

退出码：0（含 graceful 降级）；无数据可导出时打印原因退出 0（post-step 语义）。
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# h3_regen 共享件经 importlib 文件加载（mirror judge.py:100-103 单源不漂移；
# 模块级无副作用、main 有 guard，加载安全）。本模块用：
#   h3s.extract_endpoint_frames（首尾帧回落——同一实现同分辨率确定性）
#   h3s.video_content_hash（regen 半边缺席 vch 时的确定性回退）
#   h3s._load_schema_version（export_asset SCHEMA_VERSION 单源）
#   h3s._iter_sidecar_errors（sidecar 坏条目过滤）
#   h3s._atomic_write_json（PID-tmp + os.replace 原子写）
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)

# ─── 模块级常量 ─────────────────────────────────────────────────────────────

STEP_TAG = "[roundtrip-dataset]"

# Phase 21 Kai 裁决值（仅 manifest 记录用——accepted/rejected 判定已在 judge
# 冻结进 sidecar，本模块绝不重算）。
TAU_SIM_DEFAULT = 0.9670

# prompts.json 平键六 facet（UI-SPEC §6 / PATTERNS §C：顶层是 list、facet 是
# 平键非嵌套对象、无 prompt_version 键——版本从 sidecar regen 取）。
FACET_KEYS = ("subject", "action", "camera", "scene", "lighting", "style")

# h3_regen 帧缓存目录（相对 work_dir；h3_regen.py:1314 frames_dir 同源）。
FRAMES_CACHE_RELPATH = os.path.join("route_cache", "h3_regen", "frames")

# shot 目录名 pattern（prune 只认这个形状——绝不波及其它条目）。
_SHOT_DIR_RE = re.compile(r"^shot_\d{3,}$")

# rejected 分桶名 → attribution closed enum 映射（judge.summarize_scores 同款
# 命名：faithful 桶的 rejected 必然 sim < τ——硬合取判定的补集）。
BUCKET_BY_ATTRIBUTION = {
    "prompt_faithful": "faithful_below_tau",
    "model_diverged": "diverged",
    "prompt_underspecified": "underspecified",
}


# ─── 读取端（defensive，graceful）───────────────────────────────────────────

def _find_source_video(work_dir: str) -> str | None:
    """源视频解析：h264.mp4 优先、video.mp4 回落（mirror h3s.resolve_source_video
    的顺序；差异：缺席返回 None 而非 sys.exit——本模块是 graceful post-step，
    帧回落缺席时降级跳过该镜而不是炸整批）。"""
    for name in ("h264.mp4", "video.mp4"):
        cand = os.path.join(work_dir, name)
        if os.path.isfile(cand):
            return cand
    return None


def _read_prompts_by_id(work_dir: str) -> dict[int, dict] | None:
    """读 prompts.json（顶层平铺 list，按 shot_id join）。损坏/形状不对返回
    None（调用方 warning 降级），缺席/坏条目不炸整批。"""
    path = os.path.join(work_dir, "prompts.json")
    try:
        with open(path, encoding="utf-8") as f:
            prompts = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    by_id: dict[int, dict] = {}
    if isinstance(prompts, list):
        for p in prompts:
            if isinstance(p, dict) and isinstance(p.get("shot_id"), int):
                by_id[int(p["shot_id"])] = p
    return by_id


def _bad_sidecar_shot_ids(payload: dict) -> set[int]:
    """h3s._iter_sidecar_errors 过滤：按 absolute_path 归因到 shot_id（mirror
    scorer merge ②层归因形状）。无法归因 → 空集（调用方按整体损坏处理）。"""
    errors = h3s._iter_sidecar_errors(payload)
    bad: set[int] = set()
    for err in errors:
        parts = list(err.absolute_path)
        if (len(parts) >= 2 and parts[0] == "shots"
                and isinstance(parts[1], int)
                and isinstance(payload.get("shots"), list)
                and 0 <= parts[1] < len(payload["shots"])):
            shot = payload["shots"][parts[1]]
            if isinstance(shot, dict) and isinstance(shot.get("shot_id"), int):
                bad.add(int(shot["shot_id"]))
    return bad


# ─── 帧两级来源（PATTERNS §B）───────────────────────────────────────────────

def _frame_cache_paths(frames_dir: str, vch: str, sid: int) -> tuple[str, str]:
    """route_cache/h3_regen/frames/ 确定性缓存名（h3_regen.py:404 同款）。"""
    return (os.path.join(frames_dir, f"kst_{vch}_shot{sid:03d}_ff.jpg"),
            os.path.join(frames_dir, f"kst_{vch}_shot{sid:03d}_lf.jpg"))


def _ensure_endpoint_frames(work_dir: str, sid: int, prompt_entry: dict,
                            regen: dict, warnings: list) -> tuple[str, str] | None:
    """accepted 镜首尾帧落 dataset：直拷优先、缺席回落提取。

    返回 (first_frame.jpg 绝对路径, last_frame.jpg 绝对路径)——注意返回的是
    **源**路径（调用方 copy2 进 shot 目录改名）；失败返回 None + warning
    （单镜降级不炸整批）。"""
    frames_dir = os.path.join(work_dir, FRAMES_CACHE_RELPATH)
    vch = regen.get("video_content_hash")
    if not (isinstance(vch, str) and len(vch) == 16):
        # regen 半边缺席 vch——从源视频确定性重算（同一 hash 实现，cache 名不变）
        src = _find_source_video(work_dir)
        if src is None:
            warnings.append(f"{STEP_TAG} shot {sid}: 无 regen.vch 且无源视频，跳过该镜")
            return None
        vch = h3s.video_content_hash(src)
    ff, lf = _frame_cache_paths(frames_dir, vch, sid)
    if os.path.isfile(ff) and os.path.isfile(lf):
        return ff, lf                      # 直拷命中——字节即 h3 实喂帧
    src = _find_source_video(work_dir)
    if src is None:
        warnings.append(f"{STEP_TAG} shot {sid}: 帧缓存缺席且无源视频（h264.mp4/"
                        f"video.mp4 均不在），跳过该镜")
        return None
    shot_meta = {"id": sid,
                 "start_sec": float(prompt_entry.get("start_sec", 0.0)),
                 "end_sec": float(prompt_entry.get("end_sec", 0.0))}
    try:
        # 同一实现回落（LAST_FRAME_GUARD_SEC 前移防越界 / 删旧再提 / fail-loud
        # 全在 h3s 内）；产物落 frames_dir 即回填 cache，下轮直拷。
        ff2, lf2 = h3s.extract_endpoint_frames(src, shot_meta, vch, frames_dir)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        warnings.append(f"{STEP_TAG} shot {sid}: 帧回落提取失败，跳过该镜: {e}")
        return None
    return ff2, lf2


# ─── prompt.json / manifest / 清单 ──────────────────────────────────────────

def _build_prompt_json(sid: int, prompt_entry: dict, shot: dict) -> dict:
    """自含字段装配（mirror prompts.json 平键风格 + sidecar 合并；refs 缺席
    空列表；regen 刻意不含 path——消费端独立性）。"""
    scores = shot.get("scores") if isinstance(shot.get("scores"), dict) else {}
    judge = scores.get("judge") if isinstance(scores.get("judge"), dict) else {}
    regen = shot.get("regen") if isinstance(shot.get("regen"), dict) else {}
    pj = {
        "shot_id": sid,
        "start_sec": prompt_entry.get("start_sec"),
        "end_sec": prompt_entry.get("end_sec"),
        "duration": prompt_entry.get("duration"),
        "prompt_text": prompt_entry.get("prompt_text") or "",
    }
    for k in FACET_KEYS:
        pj[k] = prompt_entry.get(k) or ""
    pj["character_refs"] = list(prompt_entry.get("character_refs") or [])
    pj["prop_refs"] = list(prompt_entry.get("prop_refs") or [])
    pj["scores"] = scores
    pj["attribution"] = judge.get("attribution")   # 冗余直取——消费端免解包
    pj["regen"] = {
        "engine_name": regen.get("engine_name") or "",
        "engine_version": regen.get("engine_version") or "",
        "prompt_version": regen.get("prompt_version") or "",
        "video_content_hash": regen.get("video_content_hash") or "",
    }
    return pj


def _rejected_line(shot: dict) -> str:
    """rejected.txt 行：`shot_NNN sim={:.4f} {attribution} {reason 前 80 字符}`
    （可 grep 可审计；sim/attribution 缺席用占位——绝不因半边缺席丢行）。"""
    sid = int(shot["shot_id"])
    scores = shot.get("scores") if isinstance(shot.get("scores"), dict) else {}
    sim_obj = scores.get("midframe_sim") if isinstance(
        scores.get("midframe_sim"), dict) else {}
    sim = sim_obj.get("score")
    sim_str = f"{float(sim):.4f}" if isinstance(sim, (int, float)) \
        and not isinstance(sim, bool) else "-"
    judge = scores.get("judge") if isinstance(scores.get("judge"), dict) else {}
    attribution = judge.get("attribution") or "-"
    reason = str(judge.get("reason") or "")[:80]
    return f"shot_{sid:03d} sim={sim_str} {attribution} {reason}".rstrip()


# ─── 主流程 ─────────────────────────────────────────────────────────────────

def export_dataset(work_dir: str, dataset_root: str, tau_sim: float) -> int:
    """roundtrip.json 冻结 verdict → 独立 dataset 目录。返回 0（graceful）。"""
    work_dir = os.path.abspath(work_dir)
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    if not os.path.isfile(sidecar_path):
        print(f"{STEP_TAG} warning: roundtrip.json 不存在（step_roundtrip 被跳过/"
              f"降级），跳过 dataset 导出")
        return 0
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"{STEP_TAG} warning: roundtrip.json 损坏（{type(e).__name__}），"
              f"跳过 dataset 导出")
        return 0
    if not isinstance(payload, dict) or not isinstance(payload.get("shots"), list):
        print(f"{STEP_TAG} warning: roundtrip.json 形状不对，跳过 dataset 导出")
        return 0

    warnings: list[str] = []
    bad_ids = _bad_sidecar_shot_ids(payload)
    if bad_ids:
        for sid in sorted(bad_ids):
            warnings.append(f"{STEP_TAG} roundtrip.json 条目 shot {sid} 违反当前 "
                            f"schema，已跳过（不炸整批）")

    prompts_by_id = _read_prompts_by_id(work_dir)
    if prompts_by_id is None:
        print(f"{STEP_TAG} warning: prompts.json 缺席/损坏——prompt.json 无法自含，"
              f"跳过 dataset 导出")
        for w in warnings:
            print(w)
        return 0

    # ── 分桶遍历（从冻结 verdict+scores 直接统计，不重算）──────────────────
    accepted: list[dict] = []
    rejected: list[dict] = []
    no_verdict = 0
    for s in payload["shots"]:
        if not isinstance(s, dict) or not isinstance(s.get("shot_id"), int):
            continue
        sid = int(s["shot_id"])
        if sid in bad_ids:
            continue
        verdict = s.get("verdict") if isinstance(s.get("verdict"), dict) else None
        if verdict is None:
            no_verdict += 1
            continue
        if verdict.get("decision") == "accepted":
            accepted.append(s)
        elif verdict.get("decision") == "rejected":
            rejected.append(s)
    accepted.sort(key=lambda s: s["shot_id"])
    rejected.sort(key=lambda s: s["shot_id"])
    if no_verdict:
        warnings.append(f"{STEP_TAG} {no_verdict} 镜无冻结 verdict，不进任何清单")
    if not accepted:
        print(f"{STEP_TAG} warning: accepted 子集为空（verdict 尚未冻结或全 "
              f"rejected），跳过 dataset 导出")
        for w in warnings:
            print(w)
        return 0

    buckets = {"faithful_below_tau": 0, "diverged": 0, "underspecified": 0}
    engine_versions: set[str] = set()
    for s in accepted + rejected:
        regen = s.get("regen") if isinstance(s.get("regen"), dict) else {}
        if isinstance(regen.get("engine_version"), str) and regen["engine_version"]:
            engine_versions.add(regen["engine_version"])
    for s in rejected:
        scores = s.get("scores") if isinstance(s.get("scores"), dict) else {}
        judge = scores.get("judge") if isinstance(scores.get("judge"), dict) else {}
        bucket = BUCKET_BY_ATTRIBUTION.get(judge.get("attribution"))
        if bucket is not None:
            buckets[bucket] += 1
        else:
            warnings.append(f"{STEP_TAG} shot {s['shot_id']}: rejected 但归因缺席/"
                            f"未知，不计入分桶")

    # ── 目录重建（prune 陈旧 shot 目录：显式清单删自身目录，绝不碰父级/兄弟）
    stem = os.path.basename(work_dir.rstrip(os.sep))
    out_dir = os.path.join(dataset_root, stem)
    os.makedirs(out_dir, exist_ok=True)
    current_dirs = {f"shot_{int(s['shot_id']):03d}" for s in accepted}
    pruned = 0
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if os.path.isdir(path) and _SHOT_DIR_RE.match(name) and name not in current_dirs:
            shutil.rmtree(path)          # 只删自身陈旧 shot 目录（T-22-09）
            pruned += 1
            print(f"{STEP_TAG} prune 陈旧目录 {name}（不在当前 accepted 集）")

    # ── accepted 镜：帧两级来源 + prompt.json 自含落盘 ──────────────────────
    # WR-01（22-REVIEW）：索引（accepted.txt / manifest["shots"]）只列**本轮实际
    # 导出成功**的镜——降级跳过的镜绝不进索引（否则消费端迭代索引会撞上缺席/
    # 半空目录，accepted_count 与索引长度互相矛盾）。skipped 镜单列 manifest
    # "exported_skipped"（可审计），warnings 逐镜说明原因。
    exported = 0
    skipped_shots = 0
    skipped_ids: list[int] = []
    exported_names: dict[int, str] = {}   # sid → shot_NNN（本轮导出成功集）
    for s in accepted:
        sid = int(s["shot_id"])
        prompt_entry = prompts_by_id.get(sid)
        if prompt_entry is None:
            warnings.append(f"{STEP_TAG} shot {sid}: prompts.json 缺该镜条目，"
                            f"跳过（prompt.json 无法自含）")
            skipped_shots += 1
            skipped_ids.append(sid)
            continue
        shot_dir = os.path.join(out_dir, f"shot_{sid:03d}")
        os.makedirs(shot_dir, exist_ok=True)
        frames = _ensure_endpoint_frames(work_dir, sid, prompt_entry,
                                         s.get("regen") if isinstance(
                                             s.get("regen"), dict) else {},
                                         warnings)
        if frames is None:
            shutil.rmtree(shot_dir, ignore_errors=True)   # 半成品目录不残留
            skipped_shots += 1
            skipped_ids.append(sid)
            continue
        shutil.copy2(frames[0], os.path.join(shot_dir, "first_frame.jpg"))
        shutil.copy2(frames[1], os.path.join(shot_dir, "last_frame.jpg"))
        h3s._atomic_write_json(os.path.join(shot_dir, "prompt.json"),
                               _build_prompt_json(sid, prompt_entry, s))
        exported += 1
        exported_names[sid] = f"shot_{sid:03d}"

    # ── manifest + 两清单 ──────────────────────────────────────────────────
    manifest = {
        "video_stem": stem,
        "tau_sim": float(tau_sim),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "engine_versions": sorted(engine_versions),
        "accepted_count": exported,
        "rejected_count": len(rejected),
        "rejected_buckets": buckets,
        # WR-01：shots 索引从本轮实际导出成功集派生（== accepted_count ==
        # len(accepted.txt) 行数）；skipped 镜单列，绝不进索引
        "exported_skipped": sorted(skipped_ids),
        "shots": {str(sid): exported_names[sid]
                  for sid in sorted(exported_names)},
    }
    h3s._atomic_write_json(os.path.join(out_dir, "manifest.json"), manifest)
    with open(os.path.join(out_dir, "accepted.txt"), "w", encoding="utf-8") as f:
        for sid in sorted(exported_names):
            f.write(exported_names[sid] + "\n")
    with open(os.path.join(out_dir, "rejected.txt"), "w", encoding="utf-8") as f:
        for s in rejected:
            f.write(_rejected_line(s) + "\n")

    for w in warnings:
        print(w)
    print(f"{STEP_TAG} 完成：accepted={exported} rejected={len(rejected)} "
          f"skipped={skipped_shots} pruned={pruned}（buckets: "
          f"faithful_below_tau={buckets['faithful_below_tau']} "
          f"diverged={buckets['diverged']} "
          f"underspecified={buckets['underspecified']}）→ {out_dir}")
    return 0


# ─── CLI entry point ────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "roundtrip.json 冻结 verdict 的 accepted 子集导出为独立 dataset "
            "目录（消费端零契约依赖；首尾帧复用 h3_regen 全分辨率提帧）。"))
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— roundtrip.json 所在")
    ap.add_argument("--dataset-root", default="",
                    help="dataset 根目录（默认 work_dir 同级的 dataset/，即 "
                         "output/dataset/——跨视频可累积集合根）")
    ap.add_argument("--tau-sim", type=float, default=TAU_SIM_DEFAULT,
                    help=f"τ_sim 记录值（默认 {TAU_SIM_DEFAULT}，Phase 21 锁定值；"
                         f"仅写入 manifest，判定已在 judge 冻结）")
    args = ap.parse_args(argv)

    dataset_root = args.dataset_root or os.path.join(
        os.path.dirname(os.path.abspath(args.work_dir).rstrip(os.sep)), "dataset")
    return export_dataset(args.work_dir, dataset_root, args.tau_sim)


if __name__ == "__main__":
    sys.exit(main())
