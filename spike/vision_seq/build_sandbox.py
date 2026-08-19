#!/usr/bin/env python3
"""构建 vision_seq spike 的 sandbox 副本目录（离线、幂等、只读 live 只写 spike/）

用途（Phase 19 Plan 19-02 Task 1，THROWAWAY —— 见 spike/vision_seq/README.md）：
  ep01 live 集 action/camera 空缺率 0/93，「只填空缺」语义在 live 上是
  no-op（RESEARCH Pitfall 1）。spike 用 sandbox 副本目录实证 v2 填充效果：
  复制 shots.json / prompts.json，把 6 个 spike 候选镜的 action 与 camera
  置 ""，frames_5fps 与视频用 symlink（不复制大文件），另生成 demo 级
  audio_semantic.json（ear 输入：dialogue.text 取 transcript.json 落在该镜
  时窗内的真实段落文本截断 200 字；sfx 手工示范事件——#91 雨声、#1 脚步声、
  #88 呼吸声，正好演示「雨声→场景语义、脚步→动作链补走近」）。

算法步骤：
  1. sandbox/：live shots.json + prompts.json 副本 → 置空 SPIKE_SHOTS 六镜
     两 facet → symlink frames_5fps / video.mp4 → demo audio_semantic.json
     （过 Draft202012Validator(audio_semantic.schema.json) 自检后原子写）。
  2. sandbox_ear/：同构，但只置空 EAR_SHOTS 三镜（ear 双跑子集，控 GPU 预算）。
  3. --reset：从 live 副本重新置空既有 sandbox 的 prompts.json facets
     （不动 route_cache —— 供 19-03 复用 / 三策略重跑从同一 RAW 证据出发）。

输出 schema：sandbox/prompts.json 与 live 同构（93 元素 list，仅 6 镜
action/camera 置 ""，其余 87 镜与 live 逐值相同）；audio_semantic.json 过
v1.2 schema（最低要求 schema_version + shots[].shot_id）。

CLI 用法：
  python3 spike/vision_seq/build_sandbox.py                 # 全量构建（幂等）
  python3 spike/vision_seq/build_sandbox.py --reset         # 重置两 sandbox 的 facets
  python3 spike/vision_seq/build_sandbox.py --reset --target sandbox

安全门（T-19-06 mitigate）：所有写路径 assert 落在 spike/vision_seq/ 下；
live ep01 work_dir 只以只读方式打开。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPIKE_ROOT = Path(__file__).resolve().parent

# live ep01 work_dir（目录名含全角括号与中文冒号 —— 一律 pathlib，禁 shell 拼接）。
LIVE_WORK_DIR = REPO_ROOT / "output" / (
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。")

# spike 候选镜（RESEARCH ep01 数据盘点表：强运镜 + 长动作链标准扫出）。
SPIKE_SHOTS = [1, 46, 66, 70, 88, 91]
# ear 双跑子集（控 GPU 预算：只 3 镜烧 ear=true 信封）。
EAR_SHOTS = [1, 88, 91]

# sfx 手工示范事件（demo 级，只进 sandbox 不进 live）。
SFX_DEMO = {
    91: {"events": ["雨声"], "description": "持续的中雨声，伴随远雷"},
    1: {"events": ["脚步声", "鸟鸣"], "description": "由远及近的脚步声"},
    88: {"events": ["呼吸声", "衣料摩擦"], "description": "紧张的近距离呼吸与衣料摩擦"},
}

AUDIO_SCHEMA = REPO_ROOT / "spec" / "schemas" / "audio_semantic.schema.json"
DIALOGUE_TEXT_MAX = 200
LOG_PREFIX = "[spike-build]"


def _assert_in_spike(path: Path) -> None:
    """写路径安全门：产物必须落在 spike/vision_seq/ 下（live 零写入）。"""
    resolved = path.resolve()
    root = SPIKE_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        sys.exit(f"{LOG_PREFIX} 拒绝写 spike/vision_seq/ 外路径: {resolved}")


def _atomic_write_json(path: Path, obj) -> None:
    """tmp + os.replace 原子写（mirror analysis/* 惯例；ensure_ascii=False）。"""
    _assert_in_spike(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _blank_facets(prompts: list, shot_ids: list) -> tuple:
    """把 shot_id ∈ shot_ids 的 action/camera 置 ""（浅拷贝，不动 live 结构）。"""
    ids = set(shot_ids)
    out, n = [], 0
    for p in prompts:
        q = dict(p)
        if q.get("shot_id") in ids:
            q["action"] = ""
            q["camera"] = ""
            n += 1
        out.append(q)
    return out, n


def _dialogue_text_for_window(transcript: dict, start: float, end: float) -> str:
    """拼接与 [start, end] 时窗重叠的 transcript 段落文本（截断 200 字）。"""
    segs = [s for s in transcript.get("segments", [])
            if s.get("start", 0.0) < end and s.get("end", 0.0) > start]
    texts = [s.get("text", "").strip() for s in segs if s.get("text")]
    if not texts:
        return ""
    return "，".join(texts)[:DIALOGUE_TEXT_MAX]


def _build_audio_semantic(shots_meta: list, transcript: dict) -> dict:
    """demo 级 audio_semantic.json：六镜 shots[]（shot_id/start/end/duration
    从 shots.json 取）+ 真实 dialogue.text + 手工示范 sfx。"""
    by_id = {s["id"]: s for s in shots_meta}
    shots_out = []
    for sid in SPIKE_SHOTS:
        meta = by_id[sid]
        entry = {
            "shot_id": sid,
            "start_sec": meta["start_sec"],
            "end_sec": meta["end_sec"],
            "duration": meta["duration"],
        }
        text = _dialogue_text_for_window(transcript,
                                         meta["start_sec"], meta["end_sec"])
        if text:
            entry["dialogue"] = {"text": text}
        if sid in SFX_DEMO:
            entry["sfx"] = dict(SFX_DEMO[sid])
        shots_out.append(entry)
    return {"schema_version": "1.2", "shots": shots_out}


def _validate_audio(data: dict) -> None:
    """Draft202012Validator 自检（fail-loud —— 产物进 LLM 提问上下文前必须合法）。"""
    with open(AUDIO_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        sys.exit(f"{LOG_PREFIX} audio_semantic.json schema 校验失败: "
                 + "; ".join(e.message for e in errors[:3]))


def _ensure_symlink(link: Path, target: Path, label: str) -> None:
    """建 symlink（已是指向同目标的 symlink 则跳过；非 symlink 实体存在 → 拒绝）。

    安全门按「父目录 resolve + link 名」判定 —— 不对 link 本身 resolve：
    已存在的 symlink 一旦 resolve 会跟随到 live output/ 目标，误触发拒绝
    （幂等重跑会踩这个坑）。"""
    root = SPIKE_ROOT.resolve()
    candidate = link.parent.resolve() / link.name
    if root not in candidate.parents:
        sys.exit(f"{LOG_PREFIX} 拒绝写 spike/vision_seq/ 外路径: {candidate}")
    rel = os.path.relpath(target.resolve(), link.parent.resolve())
    if link.is_symlink() and os.readlink(link) == rel:
        return
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        sys.exit(f"{LOG_PREFIX} {label} 已存在且不是 symlink: {link}")
    os.symlink(rel, link)


def _self_check(sandbox: Path, live_prompts: list, blank_ids: list) -> None:
    """写后自检：置空数恰等于预期；未置空镜与 live 逐值相同（action/camera）。"""
    with open(sandbox / "prompts.json", encoding="utf-8") as f:
        written = json.load(f)
    blank = [q["shot_id"] for q in written
             if not q.get("action") and not q.get("camera")]
    if sorted(blank) != sorted(blank_ids):
        sys.exit(f"{LOG_PREFIX} {sandbox.name} 置空镜异常: {sorted(blank)} "
                 f"(预期 {sorted(blank_ids)})")
    live_by_id = {p["shot_id"]: p for p in live_prompts}
    for q in written:
        if q["shot_id"] in set(blank_ids):
            continue
        lv = live_by_id[q["shot_id"]]
        if q["action"] != lv["action"] or q["camera"] != lv["camera"]:
            sys.exit(f"{LOG_PREFIX} {sandbox.name} shot {q['shot_id']} "
                     f"非目标镜 facet 被改动")
    print(f"{LOG_PREFIX} {sandbox.name} self-check OK "
          f"({len(blank_ids)} 镜置空，其余 {len(written) - len(blank_ids)} 镜与 live 逐值同)")


def build_target(name: str, blank_ids: list, live_shots: list,
                 live_prompts: list, audio_data: dict, reset_only: bool) -> None:
    """构建/重置一个 sandbox 目录。reset_only=True 时只重写 prompts.json。"""
    sandbox = SPIKE_ROOT / name
    _assert_in_spike(sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)
    blanked, n = _blank_facets(live_prompts, blank_ids)
    if n != len(blank_ids):
        sys.exit(f"{LOG_PREFIX} {name}: live prompts 中只匹配到 {n}/{len(blank_ids)} 个目标镜")
    _atomic_write_json(sandbox / "prompts.json", blanked)
    if reset_only:
        return
    _atomic_write_json(sandbox / "shots.json", live_shots)
    _atomic_write_json(sandbox / "audio_semantic.json", audio_data)
    _ensure_symlink(sandbox / "frames_5fps",
                    LIVE_WORK_DIR / "frames_5fps", "frames_5fps symlink")
    _ensure_symlink(sandbox / "video.mp4",
                    LIVE_WORK_DIR / "h264.mp4", "video.mp4 symlink")
    _self_check(sandbox, live_prompts, blank_ids)


def main():
    ap = argparse.ArgumentParser(
        description="构建 vision_seq spike sandbox 副本（离线幂等；只读 live 只写 spike/vision_seq/）")
    ap.add_argument("--reset", action="store_true",
                    help="只从 live 副本重新置空既有 sandbox 的 prompts.json facets"
                         "（不动 route_cache —— 断点续跑/19-03 复用）")
    ap.add_argument("--target", choices=["sandbox", "sandbox_ear", "both"],
                    default="both",
                    help="作用目标目录（默认 both）")
    args = ap.parse_args()

    # live 只读加载（三件套）。
    with open(LIVE_WORK_DIR / "shots.json", encoding="utf-8") as f:
        live_shots = json.load(f)
    with open(LIVE_WORK_DIR / "prompts.json", encoding="utf-8") as f:
        live_prompts = json.load(f)
    with open(LIVE_WORK_DIR / "transcript.json", encoding="utf-8") as f:
        transcript = json.load(f)

    audio_data = _build_audio_semantic(live_shots, transcript)
    _validate_audio(audio_data)

    targets = {"sandbox": SPIKE_SHOTS, "sandbox_ear": EAR_SHOTS}
    todo = targets if args.target == "both" else {args.target: targets[args.target]}
    mode = "reset" if args.reset else "full build"
    print(f"{LOG_PREFIX} {mode}: {sorted(todo)} "
          f"(spike shots={SPIKE_SHOTS}, ear subset={EAR_SHOTS})")
    for name, blank_ids in todo.items():
        build_target(name, blank_ids, live_shots, live_prompts,
                     audio_data, reset_only=args.reset)
    print(f"{LOG_PREFIX} done（live ep01 全程零写入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
