#!/usr/bin/env python3
"""ShotTimelineAsset 导出器：把 output/<video-stem>/ 打包成自描述的 asset.json。

目的：在 pipeline 末端把现有 5 个数据 JSON（shots / audio_analysis / transcript /
frames / prompts）+ 原始视频 + 3 个 canonical stems（vocals / drums / other）
打包成符合 spec/schemas/asset.schema.json 的 ShotTimelineAsset manifest，并
建立 canonical 媒体 symlink，让下游消费者（@kais/infinite-canvas）能以统一的
相对路径（`video.mp4`、`stems/{vocals,drums,other}.wav`）找到所有资产。

行为：
  * 读取 transcript.json 中的 `source` / `duration` 字段，回退到 ffprobe 兜底。
  * 写入 asset.json（schema_version="1"，asset_type="shottimeline"，generator
    含 tool / version(git SHA) / generated_at(ISO-8601 UTC)）。
  * 建立 4 个 canonical symlinks：
      - video.mp4             → 原始视频的绝对路径（含 audio 流，非 h264.mp4）
      - stems/vocals.wav      → stems/htdemucs/<video-stem>/vocals.wav
      - stems/drums.wav       → stems/htdemucs/<video-stem>/drums.wav
      - stems/other.wav       → stems/htdemucs/<video-stem>/other.wav
    bass.wav 显式剔除（schema 拒绝 + 前端只渲染 3 stems）。
  * 写完后立即用 inline Draft202012Validator(asset.schema.json) 自校验，
    不 subprocess 到 spec/validate.py（其 SMOKE_SHAPES 排除 asset）。
  * prompts.json 缺失时 sys.exit 非 0 + 中文 actionable 错误（schema required）。
  * 幂等：已存在的 symlink 若 target 一致则跳过；非 symlink 真实文件拒绝覆盖。

用法：
  python3 scripts/export_asset.py \
      --work-dir output/<video-stem>/ \
      --video /abs/path/to/original.mp4 \
      --stems-source-dir output/<video-stem>/stems/htdemucs/<video-stem>/ \
      --output output/<video-stem>/asset.json \
      [--force]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# scripts/export_asset.py → repo root（定位 spec/schemas/asset.schema.json）
REPO = Path(__file__).parent.parent.resolve()


def _probe_duration(path: str) -> float:
    """ffprobe 读取视频时长（秒）；失败回退 0.0。

    与 run_pipeline.py:probe_duration 行为一致（不跨 stage import，自带副本）。
    """
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def _git_sha() -> str:
    """取仓库短 git SHA 作为 generator.version；失败回退 "dev"。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2)
        return r.stdout.strip() or "dev"
    except (subprocess.SubprocessError, OSError):
        return "dev"


def ensure_symlink(link_path: str, target: str) -> None:
    """幂等创建 symlink link_path → target。

    分支：
      * target 必须是 regular file —— 拒绝目录/FIFO/device/special file
        （02-REVIEW WR-05）。否则 symlink-to-dir 会通过 schema pattern 校验 +
        pre-write os.path.exists assert（True for dir），把指向目录的"看似有效"
        manifest 落盘，下游打开 .wav 才崩。os.path.isfile 跟随 symlink 后 stat，
        等价于 "exists 且是 regular file"。
      * 若 link_path 已是 symlink：
          - readlink 与 target 一致 → skip（避免无谓的 unlink+recreate）
          - 不一致 → unlink + 重建
      * 若 link_path 存在但非 symlink（真实文件/目录）→ raise FileExistsError
        （拒绝静默覆盖真实文件）
      * 否则 → os.symlink(target, link_path)
    """
    # 02-REVIEW WR-05：用 isfile 而非 exists —— 显式排除 dir / FIFO / device / socket。
    if not os.path.isfile(target):
        raise FileNotFoundError(
            f"symlink target is not a regular file: {target}")
    if os.path.islink(link_path):
        try:
            current = os.readlink(link_path)
        except OSError:
            current = None
        if current == target:
            return  # idempotent skip
        os.unlink(link_path)
    elif os.path.exists(link_path):
        raise FileExistsError(
            f"refusing to overwrite non-symlink: {link_path} "
            f"(expected symlink → {target})")
    os.symlink(target, link_path)


def validate_asset_json(asset_dict: dict) -> None:
    """inline Draft202012Validator 自校验 asset_dict。

    绝不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES 显式排除 asset
    （spec/validate.py:49），subprocess 会让无效 manifest 悄悄通过。
    """
    # lazy import：沿用 CLAUDE.md 的 optional-dep lazy-import 惯例
    from jsonschema import Draft202012Validator

    schema_path = REPO / "spec" / "schemas" / "asset.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(asset_dict),
                    key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        sys.exit(
            f"asset.json failed schema validation ({len(errors)} error(s)):\n"
            + "\n".join(lines))


def build_asset_dict(work_dir: str, video_path: str) -> dict:
    """从现有 pipeline 产物组装 asset.json dict。

    字段 sourcing（全部对照 output/《小江湖》第03话…/ 实际产物验证过）：
      * schema_version: 字面量 "1"（spec/fixtures/minimal/asset.json 一致）
      * asset_type: const "shottimeline"
      * source.video_filename: basename(video_path)；与 transcript.source 交叉
        校验（不一致仅 warn，不 fail）
      * source.duration_sec: transcript.duration 优先；缺失回退 _probe_duration
      * generator.tool: 字面量 "kais-shot-timeline"
      * generator.version: _git_sha() 短 SHA（失败 "dev"）
      * generator.generated_at: UTC ISO-8601（带 Z 后缀）
      * data.*: 5 个数据 JSON 的字面量相对路径
      * media.video: 字面量 "video.mp4"
      * media.stems.*: 字面量 "stems/<name>.wav"（bass 不在内）
    """
    with open(os.path.join(work_dir, "transcript.json"), encoding="utf-8") as f:
        transcript = json.load(f)

    video_filename = os.path.basename(video_path)
    # 完整性交叉校验：transcript.source 与 video basename 应一致。
    # 不一致仅 warn（不 fail）—— 让用户看到但不阻塞导出。
    if transcript.get("source") and transcript["source"] != video_filename:
        print(f"[warn] transcript.source={transcript['source']!r} != "
              f"video basename={video_filename!r}")

    duration = transcript.get("duration")
    if not duration:
        duration = _probe_duration(video_path)

    return {
        "schema_version": "1",
        "asset_type": "shottimeline",
        "source": {
            "video_filename": video_filename,
            "duration_sec": duration,
        },
        "generator": {
            "tool": "kais-shot-timeline",
            "version": _git_sha(),
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "data": {
            "shots": "shots.json",
            "audio_analysis": "audio_analysis.json",
            "transcript": "transcript.json",
            "frames": "frames.json",
            "prompts": "prompts.json",
        },
        "media": {
            "video": "video.mp4",
            "stems": {
                "vocals": "stems/vocals.wav",
                "drums": "stems/drums.wav",
                "other": "stems/other.wav",
            },
        },
    }


def main():
    ap = argparse.ArgumentParser(
        description="ShotTimelineAsset 导出器（manifest 写入 + canonical symlinks + inline jsonschema 自校验）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/，含 5 个数据 JSON）")
    ap.add_argument("--video", required=True,
                    help="原始视频绝对路径（含 audio 流；非 h264.mp4）")
    ap.add_argument("--stems-source-dir", required=True,
                    help="Demucs 输出 stems 目录（stems/htdemucs/<video-stem>/）")
    ap.add_argument("--output", required=True,
                    help="asset.json 写入路径（通常 <work-dir>/asset.json）")
    ap.add_argument("--force", action="store_true",
                    help="若 output 已存在则先删除再写（canonical symlinks 由 ensure_symlink 幂等处理）")
    args = ap.parse_args()

    # 路径绝对化：symlink target 必须是 abs path，否则会相对「symlink 所在目录」
    # 解析（不是 cwd）—— 相对 target 会让 stems/vocals.wav 解析到
    # stems/./output/.../vocals.wav 这种不存在的路径。video 同理（RESEARCH Pitfall 1）。
    work_dir = os.path.abspath(args.work_dir)
    video = os.path.abspath(args.video)
    stems_source_dir = os.path.abspath(args.stems_source_dir)
    output = os.path.abspath(args.output)

    # (a) 5 个数据 JSON 存在性 guard —— asset.schema.json 的 data.* 全部 required
    # （schema 第 61 行：required: shots/audio_analysis/transcript/frames/prompts）。
    # 任何缺失都 fail loud —— 不静默写入引用不存在文件的 manifest（02-REVIEW WR-02：
    # 原实现只 guard 了 prompts.json，其余 4 个缺失会让 schema 通过但下游崩）。
    # prompts.json 由独立步骤产出（未接入 run_pipeline），其余 4 个由 step_* 产出。
    required_data = ("shots.json", "audio_analysis.json", "transcript.json",
                     "frames.json", "prompts.json")
    for name in required_data:
        p = os.path.join(work_dir, name)
        if not os.path.exists(p):
            field = name.removesuffix(".json")
            if name == "prompts.json":
                hint = ("  prompts.json 当前由独立步骤产出（未接入 run_pipeline）；"
                        "请先就位再运行导出。\n")
            else:
                hint = ("  若是用 --skip-* 跳过了对应步骤，请先就位再运行导出。\n")
            sys.exit(
                f"{name} 不存在: {p}\n"
                f"  asset.schema.json 的 data.{field} 是 required 字段 —— 不可省略。\n"
                + hint)

    # (b) video 存在性
    if not os.path.exists(video):
        sys.exit(f"input video not found: {video}")

    # (c) 验证 video 含 audio 流（02-RESEARCH Pitfall 1 关键修复）
    # h264.mp4 是 -an 去 audio 的转码中间产物 —— video.mp4 symlink 决不能指它。
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", video], capture_output=True, text=True)
    # 02-REVIEW WR-04：先看 returncode —— ffprobe 失败（corrupt video、权限、PATH
    # 问题）时 stdout 为空，不查 returncode 会错误触发"no audio stream"，把用户
    # 带偏到 transcode -an 调试路径。真实原因是 ffprobe 没跑起来。
    if r.returncode != 0:
        sys.exit(
            f"ffprobe failed (rc={r.returncode}): {video}\n"
            f"  stderr: {r.stderr.strip() or '(empty)'}")
    if "audio" not in r.stdout:
        sys.exit(
            f"video has no audio stream: {video}\n"
            f"  (h264.mp4 transcode was -an stripped — exporter needs original)")

    # (d) stems/ 子目录
    os.makedirs(os.path.join(work_dir, "stems"), exist_ok=True)

    # (e) 4 个 canonical symlinks
    #   video.mp4 → 原始视频 abs path（NOT work_dir 内的 <original-name>.mp4，
    #   后者链到 -an 去 audio 的 h264.mp4 —— 会让消费者听不到声音）
    #   target 必须是 abs path —— 相对 target 会按「symlink 所在目录」解析（非 cwd）。
    ensure_symlink(os.path.join(work_dir, "video.mp4"), video)
    ensure_symlink(
        os.path.join(work_dir, "stems", "vocals.wav"),
        os.path.join(stems_source_dir, "vocals.wav"))
    ensure_symlink(
        os.path.join(work_dir, "stems", "drums.wav"),
        os.path.join(stems_source_dir, "drums.wav"))
    ensure_symlink(
        os.path.join(work_dir, "stems", "other.wav"),
        os.path.join(stems_source_dir, "other.wav"))
    # 不创建 stems/bass.wav —— schema 拒绝 + 前端只渲染 3 stems。
    # htdemucs 原始 bass.wav 在 stems-source-dir 中保持不动（additive-only）。

    # (f) --force 清空已存在的 output
    if args.force and os.path.exists(output):
        os.unlink(output)

    # (g) 构建 manifest dict
    asset = build_asset_dict(work_dir, video)

    # (g0) duration_sec > 0 hard check —— asset.schema.json 仅约束 minimum:0，
    # schema 校验放过 0；但下游消费者拿到 duration_sec=0 会渲染失败。
    # 02-REVIEW WR-03：transcript.duration 缺失 + ffprobe 失败时 _probe_duration
    # 静默返回 0.0（低阶 helper 沿用项目惯例），exporter 必须把它当硬错误。
    if not asset["source"]["duration_sec"]:
        sys.exit(
            f"无法确定视频时长：duration_sec=0\n"
            f"  video={video}\n"
            f"  transcript.json 无 duration 字段，且 ffprobe 兜底失败（rc≠0 或 stdout 解析失败）。\n"
            f"  duration_sec 是 asset.schema.json 的 required 字段，不可为 0 —— "
            f"请检查 ffprobe 是否在 PATH、video 是否可读。")

    # (g') Pre-write assert：4 个 canonical paths 都 resolve 到真实文件
    # 必须在 write 之前 —— 否则 dangling-symlink 的 manifest 已经落盘，下游看到
    # schema-valid 但指向不存在媒体的文档（02-REVIEW WR-01）。
    # step (e) 已建好 symlink，这里只是兜底断言；schema 校验只看 path 字符串
    # pattern，验不出 dangling symlink。
    for rel in ("video.mp4", "stems/vocals.wav", "stems/drums.wav", "stems/other.wav"):
        p = os.path.join(work_dir, rel)
        if not os.path.exists(p):
            sys.exit(f"canonical path missing before write: {rel} (expected at {p})")

    # (i') inline schema 自校验（在写入之前 —— invalid 时 helper 内 sys.exit 非 0，
    # 避免 schema-invalid manifest 落盘被下游读到）
    validate_asset_json(asset)

    # (h) 原子写入（temp + os.replace）—— 避免 partial-write 状态被下游读到
    # （02-REVIEW WR-01）。ensure_ascii=False 强制 —— Chinese video_filename。
    tmp = output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)
    os.replace(tmp, output)

    # (k) Final-status print（CLAUDE.md bracketed-tag 惯例）
    print(f"[export-asset] wrote asset.json → {output}")
    print(f"[export-asset] canonical symlinks: video.mp4, stems/{{vocals,drums,other}}.wav")


if __name__ == "__main__":
    main()
