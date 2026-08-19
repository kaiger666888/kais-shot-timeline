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
  5.5 本地 VL facet 填充（analysis/local_vision_facets.py —— 无编号 pre-step，
     mirror attach_refs 先例不 bump step counter；本地 qwen-eye 引擎 :8125 对
     frames_5fps 帧做 observe_single，填 prompts.json 的 scene/subject facets
     （call_shot_analysis.py:160-161 文档化留空的两键）；引擎不可用时
     graceful-degrade 保持空值 + [vision] warnings；--no-local-vision 关闭）
  6. 跨镜 re-id 聚类（analysis/call_reid.py + html/gen_registry_review.py ——
     第二个网络依赖步骤；调用 DEFERRED kais-aigc-platform
     POST /api/v1/production/character-reid 路由 → registry.draft.json +
     HITL 审阅 HTML；graceful-degrade 写空 clusters + warnings sidecar。
     非阻塞：产 draft + HTML 后退出，不等待人审；registry/apply_edits.py 是
     独立 standalone CLI，由操作员在审阅完 HTML 后手动运行）
  7. 音频语义深化路由调用（analysis/call_audio_analysis.py —— 第三个网络依赖
     步骤；调用 kais-aigc-platform POST /api/production/audio-analysis 路由，
     把逐镜三模态音频语义填进 audio_semantic.json 的 dialogue/sfx/reproduction；
     graceful-degrade 写 [audio] warnings sidecar 但不写 audio_semantic.json。
     非阻塞：link_speakers.py 是独立 standalone CLI，由操作员在审阅完
     speaker-review.html 后手动运行，mirror v1.1 apply_edits.py 模式；
     --skip-speaker-link 仅控制提示输出，本步永远不 subprocess 调用 link_speakers）
  8. 生成时间轴双面板 HTML（html/gen_timeline_html.py）
  9. ShotTimelineAsset 导出（scripts/export_asset.py —— asset.json + canonical symlinks）
  10. 导出后自动导入画布（可选，--canvas-auto-import 开启；失败 warning 不阻断
      —— plain label post-step，不占编号也不 bump [N/9] step counter）

用法：
  python run_pipeline.py --video input.mp4
                         [--output-dir ./output]
                         [--skip-detect] [--skip-separate] [--skip-transcribe]
                         [--skip-semantic] [--skip-reid] [--skip-export]
                         [--skip-audio-semantic] [--skip-speaker-link]
                         [--no-local-vision] [--no-subject]
                         [--canvas-auto-import] [--ep-name NAME]
                         [--canvas-project-name NAME]
                         [--offline]   # 全局：仅读 route_cache 不联网（5/6/7 共用）
                         [--analysis-url URL] [--analysis-timeout 960]
                         [--reid-url URL] [--reid-timeout 960]
                         [--audio-url URL] [--audio-timeout 900]
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
    ├── audio_semantic.json    （step 7 产出 —— 路由三模态填充；route-down 缺省 CONTRACT-05）
    ├── route_cache/shot_analysis/shot_XXX.json （每镜路由响应缓存，含 _cache_key）
    ├── route_cache/character_reid/video_<vch>.json （跨镜 re-id per-video 缓存，含 _cache_key）
    ├── route_cache/audio_analysis/shot_XXX.json （每镜 audio-analysis 路由响应缓存，含 4-tuple _cache_key）
    ├── route_cache/warnings.json （graceful-degrade 失败原因 sidecar，export_asset 读）
    ├── video.mp4              （canonical symlink → 原始视频含 audio 流）
    ├── asset.json             （ShotTimelineAsset manifest, schema_version="1.2"）
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
        print(f"[1/9] codec={codec}, no transcode needed")
        return video_path
    out = os.path.join(work_dir, "h264.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        print(f"[1/9] cached H264: {out}")
        return out
    print(f"[1/9] transcoding AV1 → H264: {video_path} → {out}")
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
        print("[2/9] --skip-detect: skipping scene detection")
        return shots_json if os.path.exists(shots_json) else None
    if os.path.exists(shots_json):
        print(f"[2/9] cached shots: {shots_json}")
        return shots_json
    run_step(
        [sys.executable, str(HERE / "detectors" / "detect_v3b.py"),
         "--video", video, "--frames-dir", frames_dir,
         "--sample-fps", str(sample_fps),
         "--output", shots_json],
        "[2/9] V3b scene detection")
    return shots_json


def step_separate(video: str, stems_root: str, shots_json: str,
                  audio_json: str, skip: bool, demucs_model: str,
                  device: str) -> str:
    if skip:
        print("[3/9] --skip-separate: skipping Demucs + audio analysis")
        return audio_json if os.path.exists(audio_json) else None
    if os.path.exists(audio_json):
        print(f"[3/9] cached audio analysis: {audio_json}")
        return audio_json
    cmd = [sys.executable, str(HERE / "audio" / "separate_stems.py"),
           "--input", video, "--shots", shots_json,
           "--output-dir", stems_root, "--output", audio_json,
           "--model", demucs_model]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[3/9] Demucs stem separation + per-shot analysis")
    return audio_json


def step_transcribe(video: str, transcript: str, skip: bool,
                    model: str, language: str, device: str,
                    backend: str) -> str:
    if skip:
        print("[4/9] --skip-transcribe: skipping Whisper")
        return transcript if os.path.exists(transcript) else None
    if os.path.exists(transcript):
        print(f"[4/9] cached transcript: {transcript}")
        return transcript
    cmd = [sys.executable, str(HERE / "audio" / "transcribe.py"),
           "--input", video, "--output", transcript,
           "--model", model, "--language", language,
           "--backend", backend]
    if device:
        cmd += ["--device", device]
    run_step(cmd, "[4/9] Whisper transcription")
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
        print("[5/9] --skip-semantic: skipping cinematography analysis")
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
        print(f"[5/9] cached prompts: {prompts_json}")
        return prompts_json
    cmd = [sys.executable, str(HERE / "analysis" / "call_shot_analysis.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", prompts_json,
           "--analysis-url", analysis_url,
           "--analysis-timeout", str(analysis_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[5/9] cinematography analysis (shot-analysis route)")
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
        print("[6/9] --skip-reid: skipping cross-shot re-id")
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
        print(f"[6/9] cached registry draft: {registry_draft}")
        return registry_draft
    # 子进程 1：call_reid.py（POST character-reid route → registry.draft.json）
    cmd = [sys.executable, str(HERE / "analysis" / "call_reid.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", registry_draft,
           "--reid-url", reid_url,
           "--reid-timeout", str(reid_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[6/9] cross-shot re-id (character-reid route)")
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
        run_step(cmd2, "[6/9] HITL review HTML generation")
    return registry_draft if os.path.exists(registry_draft) else None


def step_audio_semantic(video: str, work_dir: str, shots_json: str,
                        stems_dir: str, audio_semantic_json: str,
                        skip: bool, offline: bool,
                        audio_url: str, audio_timeout: float,
                        audio_analysis_json: str | None = None) -> str:
    """音频语义深化（step 7 of 9）—— 第三个网络依赖步骤。

    子进程调 analysis/call_audio_analysis.py（httpx POST → audio_semantic.json），
    把每镜三模态（dialogue/sfx/reproduction）填进 audio_semantic.json。
    Pipeline 第三个网络依赖步骤。Graceful-degrade：路由不可达 / --offline +
    cache miss / preflight 失败 / stub_mode:true 时 call_audio_analysis.py
    写 [audio] warning sidecar 但 NOT 写 audio_semantic.json（byte-identical
    v1.1 asset，CONTRACT-05）。link_speakers.py 是独立 standalone CLI，由操作员
    在审阅完 html/gen_speaker_review.py 产出的 HITL HTML 后手动运行（mirror
    v1.1 apply_edits.py 模式）—— 本步 NEVER subprocess 调用 link_speakers；
    --skip-speaker-link 仅控制 main() 里的提示输出（T-14-03 mitigation）。

    Args:
        video: 原始视频绝对路径（含 audio 流）。
        work_dir: 资产根目录；route_cache/audio_analysis/ 写在其下。
        shots_json: shots.json 路径（call_audio_analysis 读它定 per-shot 循环）。
        stems_dir: Demucs stems 目录（htdemucs/<video-stem>/，传给路由做 SER/MIR 输入）。
        audio_semantic_json: audio_semantic.json 输出路径（call_audio_analysis 产物；
            step_export + step_timeline 读；route-down 时不写）。
        skip: --skip-audio-semantic → True，整步跳过。
        offline: --offline → True（全局），仅读 route_cache 不联网。
        audio_url: audio-analysis 路由 URL（含 /api/production/audio-analysis path；
            NO /v1/ —— 10-02-SUMMARY mount-path flag）。
        audio_timeout: 单次路由调用 read 超时秒（默认 900，= 路由侧 execFileSync
            硬超时；mirror Phase 6 Pitfall 1）。
        audio_analysis_json: 可选 audio_analysis.json side input 路径（Phase 15
            reproduction composer 用其 drums ratio + 频谱重心估 tempo/brightness；
            缺席时 composer 降级为 BGM/mood-only music_gen，schema 仍合法）。

    Returns:
        audio_semantic_json 路径（若产出 / 已存在）；None 若 skip 且文件不存在。
        注意：step_export + step_timeline 都各自 os.path.exists 检查，因此返回值
        不被显式使用 —— 子进程失败（schema validation）→ CalledProcessError →
        fail loud。call_audio_analysis 自身 graceful-degrade 时 exit 0 + 不写文件
        → 下游 step_export 条件性 emit audio_semantic 缺席（CONTRACT-05）。
    """
    if skip:
        print("[7/9] --skip-audio-semantic: skipping audio semantic analysis")
        return audio_semantic_json if os.path.exists(audio_semantic_json) else None
    # TOCTOU-safe mtime cache（mirror step_reid:269-286）；offline 模式不跳过
    # （仍需跑子进程读 cache + 写 warnings sidecar），只在 skip 时短路。
    # WR-01：mtime 单比不够 —— video 换会让外层 mtime cache 命中但内层 per-shot
    # cache 全 stale。镜像 step_reid 的 video 身份 sidecar。
    video_stamp = audio_semantic_json + ".video-stamp"
    cached_video_id = None
    if os.path.exists(video_stamp):
        try:
            with open(video_stamp, encoding="utf-8") as f:
                cached_video_id = f.read().strip()
        except OSError:
            cached_video_id = None
    current_video_id = _video_identity(video)
    if (os.path.exists(audio_semantic_json)
            and _safe_mtime(audio_semantic_json) > _safe_mtime(shots_json)
            and cached_video_id is not None
            and cached_video_id == current_video_id):
        print(f"[7/9] cached audio_semantic: {audio_semantic_json}")
        return audio_semantic_json
    # 子进程：call_audio_analysis.py（POST audio-analysis route → audio_semantic.json
    # + route_cache/audio_analysis/shot_XXX.json + route_cache/warnings.json）。
    # list-form subprocess.run —— argv 不经 shell 解析（T-14-02 injection mitigation）。
    cmd = [sys.executable, str(HERE / "analysis" / "call_audio_analysis.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", audio_semantic_json,
           "--stems-dir", stems_dir,
           "--route-url", audio_url,
           "--route-timeout", str(audio_timeout)]
    if offline:
        cmd += ["--offline"]
    # Phase 15：audio_analysis.json side input pass-through —— reproduction
    # composer 用其 drums ratio + 频谱重心估 tempo/brightness（mirror --stems-dir
    # argv-extension pattern at line 392-394）。
    if audio_analysis_json and os.path.exists(audio_analysis_json):
        cmd += ["--audio-analysis-json", audio_analysis_json]
    run_step(cmd, "[7/9] audio semantic analysis (audio-analysis route)")
    # 写 video 身份 sidecar —— best-effort（WR-01）。
    if current_video_id is not None:
        try:
            with open(video_stamp, "w", encoding="utf-8") as f:
                f.write(current_video_id)
        except OSError:
            pass
    return audio_semantic_json if os.path.exists(audio_semantic_json) else None


def step_timeline(video: str, work_dir: str, shots_json: str,
                  audio_json: str, transcript: str, frames_json: str,
                  stems_dir: str, out_html: str, video_src: str,
                  stem_basename: str,
                  prompts_json: str = None,
                  audio_semantic_json: str = None,
                  speakers_json: str = None) -> str:
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
    # Phase 14：audio_semantic_json + speakers_json 现入 cache inputs —— Pitfall 9
    # prevention（mirror Phase 8 prompts_json addition）。link_speakers.py 重写
    # speakers.json 后新 mtime → cache miss → timeline 重生成（Phase 16 HTML gallery
    # 会读这俩文件渲染对白/音乐/音效 chips + speaker→character chip）。
    if audio_semantic_json and os.path.exists(audio_semantic_json):
        inputs.append(audio_semantic_json)
    if speakers_json and os.path.exists(speakers_json):
        inputs.append(speakers_json)
    input_mtimes = [_safe_mtime(p) for p in inputs]
    max_input_mtime = max(input_mtimes) if input_mtimes else 0
    if os.path.exists(out_html) and _safe_mtime(out_html) > max_input_mtime:
        print(f"[8/9] cached timeline: {out_html}")
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
    # Phase 16 (PRESENT-01): pass --audio-semantic + --speakers so HTML gallery
    # renders v1.2 chips + speaker→character chip + reproduction panel. Phase 14
    # mtime cache (run_pipeline.py:461-464) already includes these files as inputs
    # —— Phase 16 only adds cmd argv (mirror --prompts / --characters pattern at
    # run_pipeline.py:489-502)。graceful-omit：文件不存在 → flag 不传 → 输出 byte-
    # identical to v1.1 timeline (gen_timeline_html.py T-16-04 invariant)。
    if audio_semantic_json and os.path.exists(audio_semantic_json):
        cmd += ["--audio-semantic", audio_semantic_json]
    if speakers_json and os.path.exists(speakers_json):
        cmd += ["--speakers", speakers_json]
    run_step(cmd, "[8/9] timeline HTML generation")
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
        print("[9/9] --skip-export: skipping asset export")
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
        print(f"[9/9] cached asset: {asset_json}")
        return asset_json
    cmd = [sys.executable, str(HERE / "scripts" / "export_asset.py"),
           "--work-dir", work_dir,
           "--video", video,
           "--stems-source-dir", stems_source_dir,
           "--output", asset_json]
    if force:
        cmd += ["--force"]
    run_step(cmd, "[9/9] ShotTimelineAsset export")

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
    # Phase 14：audio-analysis 路由（step 7 of 9 —— 第三个网络依赖步骤）。
    ap.add_argument("--skip-audio-semantic", action="store_true",
                    help="跳过音频语义分析（audio-analysis 路由调用）")
    ap.add_argument("--audio-url",
                    default="http://127.0.0.1:8000/api/production/audio-analysis",
                    help="audio-analysis 路由 URL（含 /api/production/audio-analysis path；"
                         "NO /v1/ —— 10-02-SUMMARY mount-path flag；默认端口 8000 —— "
                         "路由 DEFERRED 未上线，首跑需 verify 实际端口）")
    ap.add_argument("--audio-timeout", type=float, default=900.0,
                    help="单次 audio-analysis 路由调用 read 超时秒（默认 900，"
                         "= 路由侧 execFileSync 硬超时；mirror Phase 6 Pitfall 1）")
    ap.add_argument("--skip-speaker-link", action="store_true",
                    help="跳过 link_speakers HITL 提示（link_speakers.py 本身是独立 CLI —— "
                         "操作员手动运行；本 flag 仅控制提示输出，不影响 step_audio_semantic）")
    # 画布自动导入（step_export 之后可选 post-step —— 无编号 plain label，
    # mirror attach_refs / local-vision 先例不 bump step counter）。失败仅打
    # [canvas-import] warning 不阻断管线（graceful-degrade，与 route 步骤同口径）。
    ap.add_argument("--canvas-auto-import", action="store_true",
                    help="导出成功后自动调 scripts/canvas_import.py 把资产目录导入画布"
                         "（kap 默认 http://127.0.0.1:10588；失败仅 warning 不阻断管线）")
    ap.add_argument("--ep-name", default=None,
                    help="剧集短名（画布项目命名用；缺省取 video 文件 stem）")
    ap.add_argument("--canvas-project-name", default=None,
                    help="覆盖画布项目名（缺省 小江湖·逆推资产集(<ep_label>)，"
                         "ep_label = --ep-name 或 video stem）")
    # 本地 VL facet 填充（step 5 之后的无编号 pre-step）。dest+store_false 双
    # flag 惯例（mirror gen_audio_html.py --extract-frames/--no-extract-frames）。
    ap.add_argument("--local-vision", dest="local_vision",
                    action="store_true", default=True,
                    help="启用本地 qwen-eye VL 填充 prompts.json 的 scene/subject "
                         "facets（默认启用；step 5 之后的无编号 pre-step）")
    ap.add_argument("--no-local-vision", dest="local_vision",
                    action="store_false",
                    help="禁用本地 VL facet 填充（scene/subject 保持 step 5 产出的空值）")
    ap.add_argument("--no-subject", action="store_true",
                    help="本地 VL 只填 scene、跳过 subject facet（subject 外观描述可选；"
                         "仅 --local-vision 时生效）")
    # Phase 19：帧序列逐帧问答 v2（action/camera 升级 —— 5.5 之后的无编号
    # pre-step 5.6）。dest+store_false 双 flag 惯例 mirror 上方 local-vision 组。
    ap.add_argument("--vision-seq", dest="vision_seq",
                    action="store_true", default=True,
                    help="启用帧序列逐帧问答升级 action/camera facets"
                         "（默认启用；5.5 之后的无编号 pre-step）")
    ap.add_argument("--no-vision-seq", dest="vision_seq",
                    action="store_false",
                    help="禁用帧序列 v2（action/camera 保持现有值）")
    ap.add_argument("--no-ear", action="store_true", default=False,
                    help="禁用 vision-seq 的 audio_semantic ear 融合"
                         "（audio_semantic.json 存在时默认开）")
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
    # Phase 14：audio_semantic.json（call_audio_analysis 产物）+ speakers.json
    # （link_speakers.py 产物 —— 独立 standalone CLI，不在 pipeline 内产）。
    audio_semantic_json = os.path.join(work_dir, "audio_semantic.json")
    speakers_json = os.path.join(work_dir, "speakers.json")

    os.makedirs(work_dir, exist_ok=True)

    if args.force:
        # 含 asset.json 的 video 身份 sidecar（02-REVIEW WR-07）—— force 时一并清。
        # Phase 6：prompts.json（step_semantic 产物）+ route_cache/ 目录（per-shot
        # 路由响应缓存）也一并清，避免 ROUTE_VERSION bump 后旧 cache 残留（Pitfall 5）。
        # Phase 7：registry.draft.json（step_reid 产物）+ registry_review.html +
        # registry_draft.video-stamp（WR-01 sidecar）一并清；route_cache rmtree
        # 已含 route_cache/character_reid/ 子目录。
        # Phase 14：audio_semantic.json + speakers.json + audio_semantic 的
        # video-stamp sidecar + route_cache/audio_analysis/ 子目录（NOT 父级
        # route_cache —— 那会 nuke sibling shot_analysis/character_reid 缓存）。
        # T-14-01 mitigation：EXPLICIT LIST，NEVER glob/rmtree 父级 route_cache。
        # route_cache 是目录 → shutil.rmtree(ignore_errors=True)（partial corrupt
        # cache 不应阻塞 forced rerun）；audio_analysis 子目录同理 rmtree。
        # Phase 19：下方 route_cache 整目录 rmtree 已天然覆盖 route_cache/vision_seq/
        # 子目录（5.6 pre-step 的 RAW 证据 cache）—— 无需单列进清单。
        # Phase 20：route_cache 整目录 rmtree 已天然覆盖 route_cache/h3_regen/
        # 子目录（h3 复现元数据 cache）—— 无需单列进清单。roundtrip/（h3 复现
        # 产物目录）与 roundtrip.json（RT 契约 sidecar）**不清**（20-REVIEW WR-01
        # 收紧）：管线自身不生产 roundtrip 数据（h3_regen 是独立 CLI，非
        # pipeline step），删了无法由管线找回；sidecar 内 scores/verdict 是
        # Phase 21 人工数据，红线「rejected 永不删除」。
        import shutil
        route_cache_dir = os.path.join(work_dir, "route_cache")
        audio_analysis_cache_dir = os.path.join(route_cache_dir, "audio_analysis")
        for p in (shots_json, frames_json, audio_json, transcript, out_html,
                  asset_json, asset_json + ".video-stamp",
                  prompts_json,                                      # Phase 6
                  prompts_json + ".video-stamp",                     # Phase 6 WR-01
                  registry_draft,                                    # Phase 7
                  registry_draft + ".video-stamp",                   # Phase 7 WR-01
                  review_html,                                       # Phase 7
                  audio_semantic_json,                               # Phase 14
                  audio_semantic_json + ".video-stamp",              # Phase 14 WR-01
                  speakers_json,                                     # Phase 14
                  route_cache_dir,                                   # Phase 6+7
                  audio_analysis_cache_dir):                         # Phase 14
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

    # 5.5 本地 VL facet 填充（qwen-eye pre-step —— 无编号，mirror attach_refs
    # 先例 at step_timeline；不 bump step counter，保持 grep count 不变）。
    # step 5 产 prompts.json 后：对 scene/subject 为空的镜，用本地 qwen-eye 引擎
    # （frames_5fps 首中尾 ≤3 帧 observe_single）填充 scene/subject facet。
    # graceful-degrade：引擎不可用（VRAM 不足/启动失败）→ facet 保持 "" +
    # [vision] warning，exit 0，管线继续。--no-local-vision 整段跳过。
    # 注意 attach_refs（step 8 内）在此之后跑 —— 它基于 prompts.json 重写
    # prompt_text，本步骤只改 scene/subject 两键，互不覆盖。
    if (args.local_vision and not args.skip_semantic
            and os.path.exists(prompts_json)
            and os.path.isdir(frames_dir)):
        cmd_vision = [sys.executable,
                      str(HERE / "analysis" / "local_vision_facets.py"),
                      "--shots", shots,
                      "--frames-dir", frames_dir,
                      "--work-dir", work_dir,
                      "--output", prompts_json]
        if args.no_subject:
            cmd_vision += ["--no-subject"]
        cmd_vision += ["--video", video]
        # Banner label 故意不带 numeric 前缀 —— 与 attach_refs 同款 plain label。
        run_step(cmd_vision, "local vision facets (qwen-eye pre-step)")

    # 5.6 帧序列逐帧问答（qwen-eye v2 pre-step —— 无编号，mirror 5.5 local_vision
    # 先例；不 bump step counter，保持 grep count 不变）。5.5 填完 scene/subject
    # （3 静帧）后：对 action/camera 为空的镜，用 ≤8 帧均匀采样逐帧/相邻帧对问
    # 升级两 facet（时序证据链）。graceful-degrade 由子模块自带（引擎不可用 →
    # facet 保持 "" + [vision-seq] warning + exit 0，管线继续）。
    # ear 时序后果（RESEARCH Pitfall 5）：本步在 step 7（audio_semantic 产出）
    # 之前 —— 全新跑 audio_semantic.json 必然缺席 → 模块自动关 ear 且零 warning；
    # step 7 产出后的第二次管线跑 ear 才激活（ear 进 cache key，激活即重烧一次；
    # 想跳过重烧保持 --no-ear）。--no-vision-seq 整段跳过；--audio-semantic 的
    # 文件存在性由子模块自判。
    if (args.vision_seq and not args.skip_semantic
            and os.path.exists(prompts_json)
            and os.path.isdir(frames_dir)):
        cmd_vseq = [sys.executable,
                    str(HERE / "analysis" / "vision_seq_facets.py"),
                    "--shots", shots,
                    "--frames-dir", frames_dir,
                    "--work-dir", work_dir,
                    "--output", prompts_json,
                    "--video", video,
                    "--audio-semantic", audio_semantic_json,
                    # WR-02（19-REVIEW）：抽帧率直通 —— 子模块的时窗→帧号换算
                    # 必须与 step 2 实际写 frames_5fps 的 --sample-fps 一致，
                    # 否则问的是镜头的错误半段；fps 进 window 契约参与 cache 匹配。
                    "--frame-fps", str(args.sample_fps)]
        if args.no_ear:
            cmd_vseq += ["--no-ear"]
        # Banner label 故意不带 numeric 前缀 —— 与 5.5 / attach_refs 同款 plain label。
        run_step(cmd_vseq, "vision seq facets (qwen-eye v2 pre-step)")

    # 6. 跨镜 re-id（character-reid 路由 —— DEFERRED；graceful-degrade）
    # 非阻塞：产 registry.draft.json + 自动调 gen_registry_review 产 HITL HTML；
    # apply_edits 是独立 standalone CLI，由操作员 offline 跑。
    step_reid(video, work_dir, shots, registry_draft, review_html,
              args.skip_reid, args.offline,
              args.reid_url, args.reid_timeout)

    # 7. 音频语义深化（audio-analysis 路由 —— 第三个网络依赖步骤）
    # 非阻塞：产 audio_semantic.json（路由 round-trip 成功）OR 不写（route-down
    # graceful-degrade，CONTRACT-05 byte-identical-absent）。link_speakers.py 是
    # 独立 standalone CLI，由操作员在审阅 html/gen_speaker_review.py 产出后手动
    # 运行（mirror v1.1 apply_edits.py 模式；T-14-03 mitigation: 本步永远不
    # subprocess 调用 link_speakers —— 全自动映射是 AF-05 violation）。
    step_audio_semantic(video, work_dir, shots, stems_dir, audio_semantic_json,
                        args.skip_audio_semantic, args.offline,
                        args.audio_url, args.audio_timeout,
                        audio_analysis_json=audio_json)
    # --skip-speaker-link 仅控制 HITL 提示输出（不阻塞 step_audio_semantic）。
    # 提示串拼出 operator 手动运行的完整 CLI 命令 —— mirror v1.1 apply_edits 提示。
    if (not args.skip_speaker_link
            and os.path.exists(audio_semantic_json)
            and os.path.exists(os.path.join(work_dir, "characters.json"))):
        edits_hint = os.path.join(work_dir, "speaker-edits.json")
        print(f"[hint] SPEAKER-01 HITL: after reviewing speaker-review.html + "
              f"exporting speaker-edits.json, run link_speakers:")
        print(f"         python registry/link_speakers.py \\")
        print(f"           --audio-semantic {audio_semantic_json} \\")
        print(f"           --characters     {os.path.join(work_dir, 'characters.json')} \\")
        print(f"           --edits          {edits_hint} \\")
        print(f"           --work-dir       {work_dir} \\")
        print(f"           --output         {speakers_json}")

    # 8. 时间轴 HTML
    stem_basename = args.stem_basename or stem
    video_src = args.video_src or os.path.basename(video)
    html = step_timeline(video, work_dir, shots, audio, tr, frames_json,
                         stems_dir, out_html, video_src, stem_basename,
                         prompts_json=prompts_json,
                         audio_semantic_json=audio_semantic_json,
                         speakers_json=speakers_json)

    # 8. ShotTimelineAsset 导出（asset.json + canonical symlinks）
    stems_source_dir = stems_dir  # stems/htdemucs/<stem>/
    step_export(work_dir, video, stems_source_dir, asset_json,
                args.skip_export, args.force)

    # 9.5 画布自动导入（可选 post-step —— 无编号 plain label，mirror attach_refs
    # / local-vision 先例；不 bump [N/9] step counter，保住 vision wiring 测试的
    # grep 锁）。触发条件：--canvas-auto-import 且 asset.json 存在（step_export
    # 成功或 cached 都算成功）。graceful-degrade：canvas_import 失败（kap 宕 /
    # 项目建失败 / import 400）只打 [canvas-import] warning，管线继续走到
    # [done]，绝不 re-raise（与 route 步骤同口径）。
    if args.canvas_auto_import:
        if not os.path.exists(asset_json):
            print(f"[canvas-import] warning: asset.json 不存在"
                  f"（export 被跳过或失败），跳过画布导入")
        else:
            ep_label = args.ep_name or stem
            project_name = args.canvas_project_name or \
                f"小江湖·逆推资产集({ep_label})"
            print(f"\n{'='*60}\ncanvas auto-import (canvas_import post-step)\n{'='*60}")
            # argv 只传 --asset-dir / --project-name —— episodes-id/mode 走
            # canvas_import.py 自身默认（1 / replace），不重复透传。list-form
            # argv 不经 shell（T-AW2-01 injection mitigation）。
            cmd_canvas = [sys.executable,
                          str(HERE / "scripts" / "canvas_import.py"),
                          "--asset-dir", work_dir,
                          "--project-name", project_name]
            # NOT run_step —— 那是 check=True helper，失败会 raise 阻断管线；
            # 本 post-step 要求 graceful-degrade，自写 check=False + returncode
            # 判断（T-AW2-03 mitigation）。
            try:
                r = subprocess.run(cmd_canvas, check=False)
            except OSError as e:
                print(f"[canvas-import] warning: 无法启动 canvas_import.py: "
                      f"{e}（graceful-degrade，管线继续）")
            else:
                if r.returncode != 0:
                    print(f"[canvas-import] warning: canvas_import.py 退出码 "
                          f"{r.returncode}（graceful-degrade，管线继续）")

    print(f"\n[done] timeline: {html}")
    print(f"       work dir: {work_dir}")
    print(f"       asset: {asset_json}")
    if not os.path.isabs(video_src) and not os.path.exists(
            os.path.join(work_dir, video_src)):
        print(f"       hint: HTML references '{video_src}' — copy/symlink "
              f"the video into {work_dir}/ to enable in-browser playback")


if __name__ == "__main__":
    main()
