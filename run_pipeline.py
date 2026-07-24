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
  6. 跨镜 re-id 聚类（analysis/call_reid.py + html/gen_registry_review.py ——
     第二个网络依赖步骤；调用 DEFERRED kais-aigc-platform
     POST /api/v1/production/character-reid 路由 → registry.draft.json +
     HITL 审阅 HTML；graceful-degrade 写空 clusters + warnings sidecar。
     非阻塞：产 draft + HTML 后退出，不等待人审；registry/apply_edits.py 是
     独立 standalone CLI，由操作员在审阅完 HTML 后手动运行）
  7. 生成时间轴双面板 HTML（html/gen_timeline_html.py）
  8. ShotTimelineAsset 导出（scripts/export_asset.py —— asset.json + canonical symlinks）

用法：
  python run_pipeline.py --video input.mp4
                         [--output-dir ./output]
                         [--skip-detect] [--skip-separate] [--skip-transcribe]
                         [--skip-semantic] [--skip-reid] [--skip-export]
                         [--offline]   # 全局：仅读 route_cache 不联网
                         [--analysis-url URL] [--analysis-timeout 960]
                         [--reid-url URL] [--reid-timeout 960]
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
    ├── registry.draft.json    （step 6 产出 —— re-id 聚类草稿；空 clusters 也 schema 合法）
    ├── registry_review.html   （step 6 产出 —— HITL 审阅 HTML；offline 可审）
    ├── route_cache/shot_analysis/shot_XXX.json （每镜路由响应缓存，含 _cache_key）
    ├── route_cache/character_reid/video_<vch>.json （跨镜 re-id per-video 缓存，含 _cache_key）
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
        print(f"[1/8] codec={codec}, no transcode needed")
        return video_path
    out = os.path.join(work_dir, "h264.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        print(f"[1/8] cached H264: {out}")
        return out
    print(f"[1/8] transcoding AV1 → H264: {video_path} → {out}")
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
        print("[2/8] --skip-detect: skipping scene detection")
        return shots_json if os.path.exists(shots_json) else None
    if os.path.exists(shots_json):
        print(f"[2/8] cached shots: {shots_json}")
        return shots_json
    run_step(
        [sys.executable, str(HERE / "detectors" / "detect_v3b.py"),
         "--video", video, "--frames-dir", frames_dir,
         "--sample-fps", str(sample_fps),
         "--output", shots_json],
        "[2/8] V3b scene detection")
    return shots_json


def step_separate(video: str, stems_root: str, shots_json: str,
                  audio_json: str, skip: bool, demucs_model: str,
                  device: str) -> str:
    if skip:
        print("[3/8] --skip-separate: skipping Demucs + audio analysis")
        return audio_json if os.path.exists(audio_json) else None
    if os.path.exists(audio_json):
        print(f"[3/8] cached audio analysis: {audio_json}")
        return audio_json
    cmd = [sys.executable, str(HERE / "audio" / "separate_stems.py"),
           "--input", video, "--shots", shots_json,
           "--output-dir", stems_root, "--output", audio_json,
           "--model", demucs_model]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[3/8] Demucs stem separation + per-shot analysis")
    return audio_json


def step_transcribe(video: str, transcript: str, skip: bool,
                    model: str, language: str, device: str,
                    backend: str) -> str:
    if skip:
        print("[4/8] --skip-transcribe: skipping Whisper")
        return transcript if os.path.exists(transcript) else None
    if os.path.exists(transcript):
        print(f"[4/8] cached transcript: {transcript}")
        return transcript
    cmd = [sys.executable, str(HERE / "audio" / "transcribe.py"),
           "--input", video, "--output", transcript,
           "--model", model, "--language", language,
           "--backend", backend]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[4/8] Whisper transcription")
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
        print("[5/8] --skip-semantic: skipping cinematography analysis")
        return prompts_json if os.path.exists(prompts_json) else None
    # TOCTOU-safe mtime cache（mirror step_export 02-REVIEW WR-07）；offline 模式不
    # 跳过（仍需跑子进程读 cache + 写 prompts.json），只在 skip 时短路。
    # WR-01：mtime 单比不够 —— video 文件被换（同/更老 mtime，如 backup 恢复 /
    # cp --preserve=timestamps / 版本控制 checkout）会让外层 mtime cache 命中但
    # 内层 per-shot cache 全 stale（video_content_hash 变了）→ 陈旧 prompts.json
    # 静默发货。镜像 step_export 的 video 身份 sidecar（path|size|mtime_ns），不同
    # video 强制 miss 重跑（call_shot_analysis 内层 cache 也会同步失效）。
    video_stamp = prompts_json + ".video-stamp"
    cached_video_id = None
    if os.path.exists(video_stamp):
        try:
            with open(video_stamp, encoding="utf-8") as f:
                cached_video_id = f.read().strip()
        except OSError:
            cached_video_id = None
    current_video_id = _video_identity(video)
    if (os.path.exists(prompts_json)
            and _safe_mtime(prompts_json) > _safe_mtime(shots_json)
            and cached_video_id is not None
            and cached_video_id == current_video_id):
        print(f"[5/8] cached prompts: {prompts_json}")
        return prompts_json
    cmd = [sys.executable, str(HERE / "analysis" / "call_shot_analysis.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", prompts_json,
           "--analysis-url", analysis_url,
           "--analysis-timeout", str(analysis_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[5/8] cinematography analysis (shot-analysis route)")
    # 写 video 身份 sidecar —— best-effort（WR-01）；失败仅意味着下次 cache check
    # 多一次重跑（cached_video_id=None → 强制 miss）。
    if current_video_id is not None:
        try:
            with open(video_stamp, "w", encoding="utf-8") as f:
                f.write(current_video_id)
        except OSError:
            pass
    return prompts_json if os.path.exists(prompts_json) else None


def step_reid(video: str, work_dir: str, shots_json: str,
              registry_draft: str, review_html: str,
              skip: bool, offline: bool,
              reid_url: str, reid_timeout: float) -> str:
    """跨镜 re-id 聚类（step 6 of 8）—— 第二个网络依赖步骤。

    子进程调 analysis/call_reid.py（httpx POST → registry.draft.json），再
    自动调 html/gen_registry_review.py 产 HITL 审阅 HTML。两个子进程都不
    阻塞待人审：step_reid 产完 draft + HTML 就退出；apply_edits.py 是独立
    standalone CLI，由操作员在浏览器审阅完 HTML 后手动运行（CONTEXT Q2 lock）。

    Pipeline 第二个网络依赖步骤。Graceful-degrade：路由不可达 / --offline +
    cache miss / preflight 失败时 call_reid.py 写空 clusters:[] + warnings
    sidecar；apply_edits 缺席 → characters.json/props.json 缺席 → export_asset
    条件性 emit（CONTRACT-06 closure，Plan 04 Task 2）。

    Args:
        video: 原始视频绝对路径（含 audio 流）。
        work_dir: 资产根目录；route_cache/character_reid/ 写在其下。
        shots_json: shots.json 路径（call_reid 读它定 per-shot 元数据）。
        registry_draft: registry.draft.json 输出路径（call_reid 产物；
            gen_registry_review 读它；apply_edits 读它）。
        review_html: HITL 审阅 HTML 输出路径（gen_registry_review 产物）。
        skip: --skip-reid → True，整步跳过。
        offline: --offline → True，仅读 route_cache 不联网。
        reid_url: character-reid 路由 URL（含 /api/v1/production/character-reid path）。
        reid_timeout: 单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）。

    Returns:
        registry_draft 路径（若产出 / 已存在）；None 若 skip 且文件不存在。
    """
    if skip:
        print("[6/8] --skip-reid: skipping cross-shot re-id")
        return registry_draft if os.path.exists(registry_draft) else None
    # TOCTOU-safe mtime cache（mirror step_semantic）；offline 模式不跳过，
    # 只在 skip 时短路。WR-01：mtime 单比不够 —— video 换会让外层 mtime cache
    # 命中但内层 per-video cache 全 stale。镜像 step_semantic 的 video 身份 sidecar。
    video_stamp = registry_draft + ".video-stamp"
    cached_video_id = None
    if os.path.exists(video_stamp):
        try:
            with open(video_stamp, encoding="utf-8") as f:
                cached_video_id = f.read().strip()
        except OSError:
            cached_video_id = None
    current_video_id = _video_identity(video)
    if (os.path.exists(registry_draft)
            and _safe_mtime(registry_draft) > _safe_mtime(shots_json)
            and cached_video_id is not None
            and cached_video_id == current_video_id):
        print(f"[6/8] cached registry draft: {registry_draft}")
        return registry_draft
    # 子进程 1：call_reid.py（POST character-reid route → registry.draft.json）
    cmd = [sys.executable, str(HERE / "analysis" / "call_reid.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", registry_draft,
           "--reid-url", reid_url,
           "--reid-timeout", str(reid_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[6/8] cross-shot re-id (character-reid route)")
    # 写 video 身份 sidecar —— best-effort（WR-01）。
    if current_video_id is not None:
        try:
            with open(video_stamp, "w", encoding="utf-8") as f:
                f.write(current_video_id)
        except OSError:
            pass
    # 子进程 2：gen_registry_review.py（产 HITL HTML —— 非阻塞，apply_edits 是
    # 独立 CLI）。仅在 draft 实际写出后才调；route-down degrade 时 draft 仍写出
    # （空 clusters），HTML 也仍生成（空态 placeholder —— gen_registry_review 支持）。
    if os.path.exists(registry_draft):
        cmd2 = [sys.executable, str(HERE / "html" / "gen_registry_review.py"),
                "--draft", registry_draft,
                "--video", video,
                "--shots", shots_json,
                "--output", review_html]
        run_step(cmd2, "[6/8] HITL review HTML generation")
    return registry_draft if os.path.exists(registry_draft) else None


def step_timeline(video: str, work_dir: str, shots_json: str,
                  audio_json: str, transcript: str, frames_json: str,
                  stems_dir: str, out_html: str, video_src: str,
                  stem_basename: str,
                  prompts_json: str = None) -> str:
    r"""Phase 8 wiring: step_timeline 现含 attach_refs 预处理 + 扩展 mtime cache。

    NO new numbered step / NO counter bump (CONTEXT Q3 lock —— ROADMAP Phase 8
    success criteria 不需要新 step；attach_refs 是 step_timeline 内的 pre-step，
    banner 用 plain label 不带 N/M 前缀，保持 step-counter grep count 24 不变)。
    Pitfall 9 prevention：prompts_json 现入 cache inputs —— attach_refs 重写
    prompts.json 后新 mtime → cache miss → timeline 重生成（带新 refs/chips）。
    """
    # Phase 8: attach_refs pre-step —— 在 mtime cache check 之前跑，保证 attach_refs
    # 重写 prompts.json 后 cache 立即 miss（Pitfall 9 prevention, part 1）。
    # GRACEFUL: prompts.json 不存在（step_semantic 被跳过）→ 整段跳过；characters.json/
    # props.json 不存在（route-down / 未审阅）→ attach_refs 自己 graceful-degrade 写空 refs。
    if prompts_json and os.path.exists(prompts_json):
        cmd_refs = [sys.executable, str(HERE / "prompts" / "attach_refs.py"),
                    "--prompts", prompts_json,
                    "--work-dir", work_dir]
        # Banner label 故意不带 numeric 前缀 —— Phase 8 lock 要求 step-banner grep count
        # 不变（24），因此 attach_refs 用 plain label（避免 Pitfall 5 phantom bump）。
        run_step(cmd_refs, "prompt-ref attachment (attach_refs pre-step)")
    # Phase 8: mtime cache 扩展 —— prompts_json 现入输入集（Pitfall 9 prevention,
    # part 2）。原 inputs = shots/audio/transcript；现 + prompts。attach_refs 在
    # cache check 之前跑，新 mtime → cache miss → timeline 重生成（含新 refs/chips）。
    # Phase 8 REVIEW WR-01 fix：TOCTOU-safe（mirror step_export:442-444）。原实现
    # 是 `os.path.exists(p)` + `os.path.getmtime(p)` 两步，之间存在 race window
    # （另一进程删文件 → getmtime raise FileNotFoundError 变 uncaught traceback）。
    # 统一经 _safe_mtime 单点 stat：缺失视为 +inf → 强制 cache miss（不再 traceback）。
    inputs = [shots_json]
    if audio_json:
        inputs.append(audio_json)
    if transcript:
        inputs.append(transcript)
    if prompts_json and os.path.exists(prompts_json):
        inputs.append(prompts_json)
    input_mtimes = [_safe_mtime(p) for p in inputs]
    max_input_mtime = max(input_mtimes) if input_mtimes else 0
    if os.path.exists(out_html) and _safe_mtime(out_html) > max_input_mtime:
        print(f"[7/8] cached timeline: {out_html}")
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
    # Phase 8: pass --prompts + --characters/--props/--asset-json so the HTML
    # reflects attached refs + gallery data. attach_refs 在上面已跑过；prompts.json
    # 现含 character_refs/prop_refs + recomposed prompt_text。
    if prompts_json and os.path.exists(prompts_json):
        cmd += ["--prompts", prompts_json]
    chars_path = os.path.join(work_dir, "characters.json")
    if os.path.exists(chars_path):
        cmd += ["--characters", chars_path]
    props_path = os.path.join(work_dir, "props.json")
    if os.path.exists(props_path):
        cmd += ["--props", props_path]
    asset_json_path = os.path.join(work_dir, "asset.json")
    # asset.json preferred source for gallery (registry_snapshot 是 export-time
    # truth —— RESEARCH Open Question 2 lock)。gen_timeline_html 内部会优先读
    # registry_snapshot，回退到 --characters/--props。
    if os.path.exists(asset_json_path):
        cmd += ["--asset-json", asset_json_path]
    run_step(cmd, "[7/8] timeline HTML generation")
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
        print("[8/8] --skip-export: skipping asset export")
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
        print(f"[8/8] cached asset: {asset_json}")
        return asset_json
    cmd = [sys.executable, str(HERE / "scripts" / "export_asset.py"),
           "--work-dir", work_dir,
           "--video", video,
           "--stems-source-dir", stems_source_dir,
           "--output", asset_json]
    if force:
        cmd += ["--force"]
    run_step(cmd, "[8/8] ShotTimelineAsset export")

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
    ap.add_argument("--skip-reid", action="store_true",
                    help="跳过跨镜 re-id（character-reid 路由调用）")
    # --offline 已在 Phase 6 加（全局，reid 复用）
    ap.add_argument("--reid-url",
                    default="http://127.0.0.1:8000/api/v1/production/character-reid",
                    help="character-reid 路由 URL（含 /api/v1/production/character-reid path；"
                         "默认端口 8000 —— 路由 DEFERRED 未上线，首跑需 verify 实际端口）")
    ap.add_argument("--reid-timeout", type=float, default=960.0,
                    help="单次 re-id 路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
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
    # Phase 7：registry.draft.json（call_reid 产物）+ registry_review.html（gen_registry_review 产物）
    registry_draft = os.path.join(work_dir, "registry.draft.json")
    review_html = os.path.join(work_dir, "registry_review.html")

    os.makedirs(work_dir, exist_ok=True)

    if args.force:
        # 含 asset.json 的 video 身份 sidecar（02-REVIEW WR-07）—— force 时一并清。
        # Phase 6：prompts.json（step_semantic 产物）+ route_cache/ 目录（per-shot
        # 路由响应缓存）也一并清，避免 ROUTE_VERSION bump 后旧 cache 残留（Pitfall 5）。
        # Phase 7：registry.draft.json（step_reid 产物）+ registry_review.html +
        # registry_draft.video-stamp（WR-01 sidecar）一并清；route_cache rmtree
        # 已含 route_cache/character_reid/ 子目录。
        # route_cache 是目录 → shutil.rmtree(ignore_errors=True)（partial corrupt
        # cache 不应阻塞 forced rerun）。
        import shutil
        route_cache_dir = os.path.join(work_dir, "route_cache")
        for p in (shots_json, frames_json, audio_json, transcript, out_html,
                  asset_json, asset_json + ".video-stamp",
                  prompts_json,                                      # Phase 6
                  prompts_json + ".video-stamp",                     # Phase 6 WR-01
                  registry_draft,                                    # Phase 7
                  registry_draft + ".video-stamp",                   # Phase 7 WR-01
                  review_html,                                       # Phase 7
                  route_cache_dir):                                  # Phase 6+7
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

    # 6. 跨镜 re-id（character-reid 路由 —— DEFERRED；graceful-degrade）
    # 非阻塞：产 registry.draft.json + 自动调 gen_registry_review 产 HITL HTML；
    # apply_edits 是独立 standalone CLI，由操作员 offline 跑。
    step_reid(video, work_dir, shots, registry_draft, review_html,
              args.skip_reid, args.offline,
              args.reid_url, args.reid_timeout)

    # 7. 时间轴 HTML
    stem_basename = args.stem_basename or stem
    video_src = args.video_src or os.path.basename(video)
    html = step_timeline(video, work_dir, shots, audio, tr, frames_json,
                         stems_dir, out_html, video_src, stem_basename,
                         prompts_json=prompts_json)

    # 8. ShotTimelineAsset 导出（asset.json + canonical symlinks）
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
