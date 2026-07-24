#!/usr/bin/env python3
"""端到端 pipeline：视频 → 分镜检测 + 音轨分离 + 转录 + 时间轴 HTML + ShotTimelineAsset 导出。

步骤（每步可单独跳过，中间结果缓存在 output/<video-name>/ 下）：

  1. AV1→H264 转码（如果输入是 AV1）
  2. PySceneDetect V3b 融合检测（detectors/detect_v3b.py）
  3. Demucs 音轨分离 + 分镜音频能量分析（audio/separate_stems.py）
  4. Whisper 转录（audio/transcribe.py）
  5. 运镜语义分析路由调用（analysis/call_shot_analysis.py —— 首个网络依赖步骤；
     调用 kais-aigc-platform POST /api/v1/production/shot-analysis 路由，
     把逐镜运镜分析填进 prompts.json 的 camera/action/lighting/style facets；
     路由不可达时 graceful-degrade 写空 facets + warnings sidecar）
  6. 生成时间轴双面板 HTML（html/gen_timeline_html.py）
  7. ShotTimelineAsset 导出（scripts/export_asset.py —— asset.json + canonical symlinks）

用法：
  python run_pipeline.py --video input.mp4
                         [--output-dir ./output]
                         [--skip-detect] [--skip-separate] [--skip-transcribe]
                         [--skip-semantic] [--skip-export]
                         [--offline]   # 全局：仅读 route_cache 不联网
                         [--analysis-url URL] [--analysis-timeout 960]
                         [--whisper-model large-v3] [--whisper-language zh]
                         [--demucs-model htdemucs]
                         [--device cuda]
                         [--video-src URL_OR_FILENAME]

输出布局：
  output/<video-stem>/
    ├── h264.mp4               （若转码过）
    ├── shots.json             （V3b 检测结果）
    ├── frames.json            （首尾帧 base64 缓存）
    ├── stems/htdemucs/<stem>/ （Demucs 分轨，4 stems 含 bass）
    ├── stems/{vocals,drums,other}.wav （canonical symlinks, bass 显式剔除）
    ├── audio_analysis.json    （per-shot stem 能量分析）
    ├── transcript.json        （Whisper 转录）
    ├── prompts.json           （step 5 产出 —— 路由 facets 填充；空 facets 也 schema 合法）
    ├── route_cache/shot_analysis/shot_XXX.json （每镜路由响应缓存，含 _cache_key）
    ├── route_cache/warnings.json （graceful-degrade 失败原因 sidecar，export_asset 读）
    ├── video.mp4              （canonical symlink → 原始视频含 audio 流）
    ├── asset.json             （ShotTimelineAsset manifest, schema_version="1"）
    └── timeline.html          （最终 HTML）
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).parent.resolve()


def probe_codec(path: str) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return r.stdout.strip().lower()


def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def ensure_h264(video_path: str, work_dir: str) -> str:
    """若视频是 AV1，转码到 H264（PySceneDetect 在 AV1 上不稳定）。"""
    codec = probe_codec(video_path)
    if codec != "av1":
        print(f"[1/7] codec={codec}, no transcode needed")
        return video_path
    out = os.path.join(work_dir, "h264.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        print(f"[1/7] cached H264: {out}")
        return out
    print(f"[1/7] transcoding AV1 → H264: {video_path} → {out}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", out],
        check=True)
    return out


def run_step(cmd: list, label: str):
    """运行子进程，失败时抛出 RuntimeError。"""
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def step_detect(video: str, work_dir: str, frames_dir: str,
                shots_json: str, skip: bool, sample_fps: float) -> str:
    if skip:
        print("[2/7] --skip-detect: skipping scene detection")
        return shots_json if os.path.exists(shots_json) else None
    if os.path.exists(shots_json):
        print(f"[2/7] cached shots: {shots_json}")
        return shots_json
    run_step(
        [sys.executable, str(HERE / "detectors" / "detect_v3b.py"),
         "--video", video, "--frames-dir", frames_dir,
         "--sample-fps", str(sample_fps),
         "--output", shots_json],
        "[2/7] V3b scene detection")
    return shots_json


def step_separate(video: str, stems_root: str, shots_json: str,
                  audio_json: str, skip: bool, demucs_model: str,
                  device: str) -> str:
    if skip:
        print("[3/7] --skip-separate: skipping Demucs + audio analysis")
        return audio_json if os.path.exists(audio_json) else None
    if os.path.exists(audio_json):
        print(f"[3/7] cached audio analysis: {audio_json}")
        return audio_json
    cmd = [sys.executable, str(HERE / "audio" / "separate_stems.py"),
           "--input", video, "--shots", shots_json,
           "--output-dir", stems_root, "--output", audio_json,
           "--model", demucs_model]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[3/7] Demucs stem separation + per-shot analysis")
    return audio_json


def step_transcribe(video: str, transcript: str, skip: bool,
                    model: str, language: str, device: str,
                    backend: str) -> str:
    if skip:
        print("[4/7] --skip-transcribe: skipping Whisper")
        return transcript if os.path.exists(transcript) else None
    if os.path.exists(transcript):
        print(f"[4/7] cached transcript: {transcript}")
        return transcript
    cmd = [sys.executable, str(HERE / "audio" / "transcribe.py"),
           "--input", video, "--output", transcript,
           "--model", model, "--language", language,
           "--backend", backend]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[4/7] Whisper transcription")
    return transcript


def step_semantic(video: str, work_dir: str, shots_json: str,
                  prompts_json: str, skip: bool, offline: bool,
                  analysis_url: str, analysis_timeout: float) -> str:
    """运镜语义分析 —— 调用 kais-aigc-platform shot-analysis 路由，填 prompts.json facets。

    Pipeline 首个网络依赖步骤。子进程调 analysis/call_shot_analysis.py，后者用
    httpx sync client per-shot POST /api/v1/production/shot-analysis（route 分支
    feat/shot-analysis-route，merge 后生效）。Graceful-degrade：路由不可达时
    call_shot_analysis.py 写空 facets + warnings sidecar，资产仍导出
    （CONTEXT D-XX lock）。

    Args:
        video: 原始视频绝对路径（含 audio 流 —— 与 step_separate/step_transcribe 同源）。
        work_dir: 资产根目录（output/<video-stem>/）；route_cache 写在其下。
        shots_json: shots.json 路径（step_detect 产物；step_semantic 读它定 per-shot 循环）。
        prompts_json: prompts.json 输出路径（step_semantic 产物；step_export 读）。
        skip: --skip-semantic → True，整步跳过（返已存在的 prompts.json 或 None）。
        offline: --offline → True，仅读 route_cache 不联网（cache 命中即用，miss 则
            空 facets + warning，仍写 prompts.json）。注意：offline 模式 *不* 跳过
            step（仍要跑子进程读 cache + 写 prompts）；skip 才跳过整步。
        analysis_url: shot-analysis 路由 URL（含 /api/v1/production/shot-analysis path）。
        analysis_timeout: 单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）。

    Returns:
        prompts_json 路径（若产出 / 已存在）；None 若 skip 且文件不存在。
        注意：step_export 自己也检查 os.path.exists(prompts.json)，因此本步返回
        值不被显式使用 —— 子进程失败（schema validation）→ CalledProcessError → fail loud。
    """
    if skip:
        print("[5/7] --skip-semantic: skipping cinematography analysis")
        return prompts_json if os.path.exists(prompts_json) else None
    # TOCTOU-safe mtime cache（mirror step_export 02-REVIEW WR-07）；offline 模式不
    # 跳过（仍需跑子进程读 cache + 写 prompts.json），只在 skip 时短路。
    if (os.path.exists(prompts_json)
            and _safe_mtime(prompts_json) > _safe_mtime(shots_json)):
        print(f"[5/7] cached prompts: {prompts_json}")
        return prompts_json
    cmd = [sys.executable, str(HERE / "analysis" / "call_shot_analysis.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", prompts_json,
           "--analysis-url", analysis_url,
           "--analysis-timeout", str(analysis_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[5/7] cinematography analysis (shot-analysis route)")
    return prompts_json if os.path.exists(prompts_json) else None


def step_timeline(video: str, work_dir: str, shots_json: str,
                  audio_json: str, transcript: str, frames_json: str,
                  stems_dir: str, out_html: str, video_src: str,
                  stem_basename: str) -> str:
    if os.path.exists(out_html) and os.path.getmtime(out_html) > max(
            os.path.getmtime(shots_json),
            os.path.getmtime(audio_json) if audio_json else 0,
            os.path.getmtime(transcript) if transcript else 0):
        print(f"[6/7] cached timeline: {out_html}")
        return out_html
    cmd = [sys.executable, str(HERE / "html" / "gen_timeline_html.py"),
           "--shots", shots_json, "--output", out_html]
    if audio_json:
        cmd += ["--audio-json", audio_json]
    if frames_json:
        cmd += ["--frames", frames_json]
    if transcript:
        cmd += ["--transcript", transcript]
    if stems_dir and os.path.isdir(stems_dir):
        cmd += ["--stems-dir", stems_dir]
    if video:
        cmd += ["--video", video]
    if video_src:
        cmd += ["--video-src", video_src]
    if stem_basename:
        cmd += ["--stem-basename", stem_basename]
    run_step(cmd, "[6/7] timeline HTML generation")
    return out_html


def _safe_mtime(path: str) -> float:
    """单点 stat 读 mtime；缺失返回 +inf 强制 cache miss（02-REVIEW WR-07 TOCTOU）。

    step_export / step_timeline 旧实现是 `os.path.exists(p)` 之后再 `os.path.getmtime(p)`，
    两步之间存在 TOCTOU 窗口：另一进程删文件会让 getmtime raise FileNotFoundError
    变 uncaught traceback。统一经此 helper 走 try/except，缺失视为 +inf → cache miss。
    """
    try:
        return os.path.getmtime(path)
    except OSError:
        return float("inf")


def _video_identity(video_path: str) -> str | None:
    """视频身份指纹（path + size + mtime_ns）；缺失返回 None（02-REVIEW WR-07）。

    step_export 的 mtime cache 仅看 mtime —— 若用户切到另一个 mtime 更老/相等
    的 --video（例如 backup 恢复保留原时间戳），cache 会命中并返回引用旧 video
    filename 的陈旧 manifest。把 path+size+mtime_ns 三件套写入 sidecar，下次
    cache check 比对，不同 video 强制 miss。
    """
    try:
        st = os.stat(video_path)
    except OSError:
        return None
    return f"{video_path}|{st.st_size}|{st.st_mtime_ns}"


def step_export(work_dir: str, video: str, stems_source_dir: str,
                asset_json: str, skip: bool, force: bool) -> str:
    """导出 ShotTimelineAsset（asset.json + canonical symlinks）。

    子进程调 scripts/export_asset.py；失败（export_asset.py sys.exit 非 0）
    时 subprocess.run(check=True) raises CalledProcessError，run_pipeline 崩
    （fails loud，项目惯例）。

    Cache 策略（mirror step_timeline + 02-REVIEW WR-07 修补）：
      * inputs = 5 个数据 JSON + 原始 video
      * TOCTOU-safe mtime：经 _safe_mtime 单点 stat，缺失 input → +inf → 强制 miss
      * video 身份 sidecar（asset.json.video-stamp）：cache key 锁定 path+size+mtime_ns，
        防止不同 --video（同 mtime/size）误命中陈旧 manifest
    """
    if skip:
        print("[7/7] --skip-export: skipping asset export")
        return asset_json if os.path.exists(asset_json) else None
    # mtime cache: mirror step_timeline；inputs = 5 数据 JSON + 原始 video
    inputs = [
        os.path.join(work_dir, "shots.json"),
        os.path.join(work_dir, "audio_analysis.json"),
        os.path.join(work_dir, "transcript.json"),
        os.path.join(work_dir, "frames.json"),
        os.path.join(work_dir, "prompts.json"),
        video,
    ]
    # TOCTOU-safe mtime：缺失 input → +inf → 强制 cache miss（不再 exists+getmtime 两步）
    input_mtimes = [_safe_mtime(p) for p in inputs]
    all_inputs_present = all(m != float("inf") for m in input_mtimes)
    max_input_mtime = max(input_mtimes)

    # video 身份 sidecar：防止不同 --video（同 mtime/size）误命中陈旧 manifest
    video_stamp = asset_json + ".video-stamp"
    cached_video_id = None
    if os.path.exists(video_stamp):
        try:
            with open(video_stamp, encoding="utf-8") as f:
                cached_video_id = f.read().strip()
        except OSError:
            cached_video_id = None
    current_video_id = _video_identity(video)

    if (not force and os.path.exists(asset_json)
            and all_inputs_present
            and _safe_mtime(asset_json) > max_input_mtime
            and cached_video_id is not None
            and cached_video_id == current_video_id):
        print(f"[7/7] cached asset: {asset_json}")
        return asset_json
    cmd = [sys.executable, str(HERE / "scripts" / "export_asset.py"),
           "--work-dir", work_dir,
           "--video", video,
           "--stems-source-dir", stems_source_dir,
           "--output", asset_json]
    if force:
        cmd += ["--force"]
    run_step(cmd, "[7/7] ShotTimelineAsset export")

    # 写 video 身份 sidecar —— best-effort；失败仅意味着下次 cache check 多一次重跑
    if current_video_id is not None:
        try:
            with open(video_stamp, "w", encoding="utf-8") as f:
                f.write(current_video_id)
        except OSError:
            pass

    return asset_json


def main():
    ap = argparse.ArgumentParser(
        description="端到端 pipeline: 视频 → 分镜 + 音轨 + 转录 + 时间轴 HTML")
    ap.add_argument("--video", required=True, help="输入视频路径")
    ap.add_argument("--output-dir", default="./output",
                    help="输出根目录（默认 ./output）")
    ap.add_argument("--skip-detect", action="store_true",
                    help="跳过分镜检测")
    ap.add_argument("--skip-separate", action="store_true",
                    help="跳过 Demucs 分轨 + 音频分析")
    ap.add_argument("--skip-transcribe", action="store_true",
                    help="跳过 Whisper 转录")
    ap.add_argument("--skip-semantic", action="store_true",
                    help="跳过运镜语义分析（shot-analysis 路由调用）")
    ap.add_argument("--skip-export", action="store_true",
                    help="跳过 ShotTimelineAsset 导出（asset.json + canonical symlinks）")
    ap.add_argument("--offline", action="store_true",
                    help="全局：仅读 route_cache 不联网（缓存命中即用，miss 则降级空 facets）")
    ap.add_argument("--analysis-url",
                    default="http://127.0.0.1:8000/api/v1/production/shot-analysis",
                    help="shot-analysis 路由 URL（含 /api/v1/production/shot-analysis path；"
                         "默认端口 8000 — 路由 unmerged，首跑需 verify 实际端口）")
    ap.add_argument("--analysis-timeout", type=float, default=960.0,
                    help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
    ap.add_argument("--sample-fps", type=float, default=5.0,
                    help="V3b Pass2 HistCorr 抽帧频率（默认 5）")
    ap.add_argument("--demucs-model", default="htdemucs",
                    help="Demucs 模型（默认 htdemucs）")
    ap.add_argument("--whisper-model", default="large-v3",
                    help="Whisper 模型（默认 large-v3）")
    ap.add_argument("--whisper-language", default="zh",
                    help="Whisper 语言代码（默认 zh）")
    ap.add_argument("--whisper-backend", default="auto",
                    choices=["auto", "faster-whisper", "openai-whisper"])
    ap.add_argument("--device", default="cuda:1",
                    help="cuda / cuda:0 / cuda:1 / cpu（默认 cuda:1 = RTX 3090；"
                         "Demucs + Whisper 共用）")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源（默认 --video 的 basename）")
    ap.add_argument("--stem-basename", default=None,
                    help="HTML <audio> stem 文件名前缀（默认 <video-basename>）")
    ap.add_argument("--force", action="store_true",
                    help="忽略缓存，强制重跑所有未跳过的步骤")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        sys.exit(f"input video not found: {video}")

    stem = Path(video).stem
    work_dir = os.path.join(args.output_dir, stem)
    frames_dir = os.path.join(work_dir, "frames_5fps")
    stems_root = os.path.join(work_dir, "stems")
    stems_dir = os.path.join(stems_root, args.demucs_model, stem)
    shots_json = os.path.join(work_dir, "shots.json")
    frames_json = os.path.join(work_dir, "frames.json")
    audio_json = os.path.join(work_dir, "audio_analysis.json")
    transcript = os.path.join(work_dir, "transcript.json")
    prompts_json = os.path.join(work_dir, "prompts.json")
    out_html = os.path.join(work_dir, "timeline.html")
    asset_json = os.path.join(work_dir, "asset.json")

    os.makedirs(work_dir, exist_ok=True)

    if args.force:
        # 含 asset.json 的 video 身份 sidecar（02-REVIEW WR-07）—— force 时一并清。
        # Phase 6：prompts.json（step_semantic 产物）+ route_cache/ 目录（per-shot
        # 路由响应缓存）也一并清，避免 ROUTE_VERSION bump 后旧 cache 残留（Pitfall 5）。
        # route_cache 是目录 → shutil.rmtree(ignore_errors=True)（partial corrupt
        # cache 不应阻塞 forced rerun）。
        import shutil
        route_cache_dir = os.path.join(work_dir, "route_cache")
        for p in (shots_json, frames_json, audio_json, transcript, out_html,
                  asset_json, asset_json + ".video-stamp",
                  prompts_json,                                      # Phase 6
                  route_cache_dir):                                  # Phase 6
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.unlink(p)
        print(f"[force] cleared cache under {work_dir}")

    # 1. 转码（如果需要）
    video_for_detect = ensure_h264(video, work_dir)

    # 2. 分镜检测
    shots = step_detect(video_for_detect, work_dir, frames_dir, shots_json,
                        args.skip_detect, args.sample_fps)
    if not shots:
        sys.exit("scene detection did not produce shots.json; aborting")

    # 3. 音轨分离 + 分析
    audio = step_separate(video, stems_root, shots, audio_json,
                          args.skip_separate, args.demucs_model, args.device)

    # 4. 转录
    tr = step_transcribe(video, transcript, args.skip_transcribe,
                         args.whisper_model, args.whisper_language,
                         args.device, args.whisper_backend)

    # 5. 运镜语义分析（shot-analysis 路由 —— 首个网络依赖步骤）
    # 返回值不捕获：step_export 自己检查 prompts.json 是否存在；子进程失败
    # （schema validation 错）→ CalledProcessError → fail loud（项目惯例）。
    # 路由不可达时 call_shot_analysis.py 仍写 prompts.json（空 facets + warnings）+ exit 0。
    step_semantic(video, work_dir, shots, prompts_json,
                  args.skip_semantic, args.offline,
                  args.analysis_url, args.analysis_timeout)

    # 6. 时间轴 HTML
    stem_basename = args.stem_basename or stem
    video_src = args.video_src or os.path.basename(video)
    html = step_timeline(video, work_dir, shots, audio, tr, frames_json,
                         stems_dir, out_html, video_src, stem_basename)

    # 7. ShotTimelineAsset 导出（asset.json + canonical symlinks）
    stems_source_dir = stems_dir  # stems/htdemucs/<stem>/
    step_export(work_dir, video, stems_source_dir, asset_json,
                args.skip_export, args.force)

    print(f"\n[done] timeline: {html}")
    print(f"       work dir: {work_dir}")
    print(f"       asset: {asset_json}")
    if not os.path.isabs(video_src) and not os.path.exists(
            os.path.join(work_dir, video_src)):
        print(f"       hint: HTML references '{video_src}' — copy/symlink "
              f"the video into {work_dir}/ to enable in-browser playback")


if __name__ == "__main__":
    main()
