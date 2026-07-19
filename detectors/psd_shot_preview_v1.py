#!/usr/bin/env python3
"""PySceneDetect 基础分镜检测 + HTML 预览生成器（V1，参数化版本）。

  - AdaptiveDetector（滑窗自适应阈值，适合动画）
  - 帧级精度
  - 首尾帧用 ffmpeg 从原视频精确抽取（base64 内嵌）
  - HTML playShot 点击播放对应分镜

用法：
  python detectors/psd_shot_preview_v1.py --video input.mp4
                                         [--output shots.html]
                                         [--json shots.json]
                                         [--threshold 3.0]
                                         [--min-scene-len 15]
                                         [--video-src video.mp4]
                                         [--ep-name ep01]
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from scenedetect import detect, AdaptiveDetector


def get_video_duration(video_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 300.0


def detect_shots(video_path: str, threshold: float = 3.0,
                 min_scene_len: int = 15) -> list:
    print(f"  Detecting scenes with AdaptiveDetector(threshold={threshold}, "
          f"min_scene_len={min_scene_len})...")
    t0 = time.time()
    scenes = detect(video_path, AdaptiveDetector(
        adaptive_threshold=threshold, min_scene_len=min_scene_len))
    print(f"  Found {len(scenes)} scenes in {time.time() - t0:.1f}s")
    shots = []
    for i, (start, end) in enumerate(scenes):
        s, e = start.get_seconds(), end.get_seconds()
        shots.append({
            "id": i + 1,
            "start_sec": round(s, 3),
            "end_sec": round(e, 3),
            "duration": round(e - s, 3),
        })
    return shots


def extract_frame(video_path: str, timestamp: float, quality: int = 2) -> str:
    """抽单帧 → base64 data URI。"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
         "-frames:v", "1", "-q:v", str(quality), "-vf", "scale=480:-1",
         tmp_path, "-loglevel", "error"],
        capture_output=True, timeout=10)
    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
        with open(tmp_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp_path)
        return f"data:image/jpeg;base64,{b64}"
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    return ""


def extract_all_frames(video_path: str, shots: list):
    print(f"  Extracting frames for {len(shots)} shots...")
    for i, shot in enumerate(shots):
        shot["first_frame"] = extract_frame(video_path, shot["start_sec"])
        last_ts = max(shot["end_sec"] - 0.05, shot["start_sec"])
        shot["last_frame"] = extract_frame(video_path, last_ts)
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(shots)}")
    print("  All frames extracted.")


def generate_html(ep_name: str, shots: list, video_filename: str) -> str:
    total_duration = shots[-1]["end_sec"] if shots else 0
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜预览 - {ep_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }}
.header {{ position: sticky; top: 0; z-index: 100; background: #161b22; padding: 12px 20px; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 20px; }}
.header h1 {{ font-size: 18px; color: #58a6ff; }}
.stats {{ color: #8b949e; font-size: 13px; }}
.player-section {{ background: #161b22; padding: 16px; border-bottom: 1px solid #30363d; }}
.player-container {{ max-width: 960px; margin: 0 auto; position: relative; }}
video {{ width: 100%; border-radius: 8px; }}
.current-shot-info {{ text-align: center; padding: 8px; color: #58a6ff; font-size: 14px; }}
.shots-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; padding: 16px; max-width: 1600px; margin: 0 auto; }}
.shot-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.2s; position: relative; }}
.shot-card:hover {{ border-color: #58a6ff; transform: translateY(-2px); }}
.shot-card.playing {{ border-color: #f85149; box-shadow: 0 0 12px rgba(248,81,73,0.4); }}
.shot-num {{ position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.8); color: #58a6ff; font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
.shot-dur {{ position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,0.8); color: #8b949e; font-size: 11px; padding: 2px 6px; border-radius: 4px; }}
.frames {{ display: flex; gap: 2px; }}
.frame {{ flex: 1; position: relative; }}
.frame img {{ width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; }}
.frame-label {{ position: absolute; bottom: 2px; left: 2px; background: rgba(0,0,0,0.7); color: #8b949e; font-size: 9px; padding: 1px 4px; border-radius: 2px; }}
.shot-times {{ padding: 4px 8px; font-size: 11px; color: #8b949e; display: flex; justify-content: space-between; }}
.nav {{ position: sticky; bottom: 0; background: #161b22; border-top: 1px solid #30363d; padding: 8px 20px; display: flex; justify-content: center; gap: 12px; }}
.nav button {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
.nav button:hover {{ background: #30363d; }}
</style>
</head>
<body>

<div class="header">
    <h1>🎬 {ep_name} — 分镜预览 (PySceneDetect)</h1>
    <div class="stats">{len(shots)} 镜 · 总时长 {total_duration:.1f}s</div>
</div>

<div class="player-section">
    <div class="player-container">
        <video id="player" controls preload="metadata">
            <source src="{video_filename}" type="video/mp4">
        </video>
        <div class="current-shot-info" id="shotInfo">点击下方分镜卡片播放</div>
    </div>
</div>

<div class="shots-grid">
"""
    for shot in shots:
        html += f"""    <div class="shot-card" id="shot-{shot['id']}"
     onclick="playShot({shot['id']}, {shot['start_sec']}, {shot['end_sec'] - 0.05})">
        <span class="shot-num">#{shot['id']}</span>
        <span class="shot-dur">{shot['duration']:.1f}s</span>
        <div class="frames">
            <div class="frame">
                <img src="{shot['first_frame']}" alt="首帧" loading="lazy">
                <span class="frame-label">首帧 {shot['start_sec']:.1f}s</span>
            </div>
            <div class="frame">
                <img src="{shot['last_frame']}" alt="尾帧" loading="lazy">
                <span class="frame-label">尾帧 {shot['end_sec']:.1f}s</span>
            </div>
        </div>
        <div class="shot-times">
            <span>{shot['start_sec']:.1f}s</span>
            <span>→</span>
            <span>{shot['end_sec']:.1f}s</span>
        </div>
    </div>
"""
    meta_only = [{k: v for k, v in s.items()
                  if k not in ("first_frame", "last_frame")} for s in shots]
    html += f"""</div>

<div class="nav">
    <button onclick="prevShot()">⬅ 上一镜</button>
    <button onclick="togglePlay()">⏯ 播放/暂停</button>
    <button onclick="nextShot()">下一镜 ➡</button>
</div>

<script>
const video = document.getElementById('player');
const shotInfo = document.getElementById('shotInfo');
const shots = {json.dumps(meta_only)};
let currentShot = null;
let stopAt = null;

function playShot(id, start, stopAtTime) {{
    document.querySelectorAll('.shot-card').forEach(c => c.classList.remove('playing'));
    const card = document.getElementById('shot-' + id);
    if (card) card.classList.add('playing');
    currentShot = id;
    stopAt = stopAtTime;
    video.currentTime = start;
    video.play().catch(() => {{}});
    const s = shots.find(s => s.id === id);
    if (s) {{
        shotInfo.textContent = `镜头 #${{id}} · ${{s.start_sec.toFixed(1)}}s → ${{s.end_sec.toFixed(1)}}s · ${{s.duration.toFixed(1)}}s`;
    }}
    if (card) card.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
}}

video.addEventListener('timeupdate', () => {{
    if (stopAt !== null && video.currentTime >= stopAt) {{
        video.pause();
        stopAt = null;
    }}
}});

video.addEventListener('ended', () => {{
    document.querySelectorAll('.shot-card').forEach(c => c.classList.remove('playing'));
    shotInfo.textContent = '播放结束';
}});

function nextShot() {{
    if (currentShot === null) currentShot = 0;
    const next = currentShot + 1;
    if (next <= shots.length) {{
        const s = shots.find(s => s.id === next);
        if (s) playShot(next, s.start_sec, s.end_sec - 0.05);
    }}
}}

function prevShot() {{
    if (currentShot === null || currentShot <= 1) return;
    const prev = currentShot - 1;
    const s = shots.find(s => s.id === prev);
    if (s) playShot(prev, s.start_sec, s.end_sec - 0.05);
}}

function togglePlay() {{
    if (video.paused) video.play(); else video.pause();
}}

document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight') nextShot();
    else if (e.key === 'ArrowLeft') prevShot();
    else if (e.key === ' ') {{ e.preventDefault(); togglePlay(); }}
}});
</script>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser(
        description="PySceneDetect V1：基础分镜检测 + HTML 预览")
    ap.add_argument("--video", required=True, help="输入视频路径")
    ap.add_argument("--threshold", type=float, default=3.0,
                    help="AdaptiveDetector 阈值（默认 3.0）")
    ap.add_argument("--min-scene-len", type=int, default=15,
                    help="最小场景帧数（默认 15）")
    ap.add_argument("--ep-name", default=None,
                    help="剧集名（默认 <video-basename>）")
    ap.add_argument("--json", default=None,
                    help="输出分镜 JSON 路径（默认 <video-basename>_shots.json）")
    ap.add_argument("--output", default=None,
                    help="输出 HTML 路径（默认 <video-basename>_shots.html）")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源（默认 --video 的 basename）")
    args = ap.parse_args()

    ep_name = args.ep_name or Path(args.video).stem
    json_path = args.json or os.path.join(
        os.path.dirname(args.video) or ".",
        f"{Path(args.video).stem}_shots.json")
    html_path = args.output or os.path.join(
        os.path.dirname(args.video) or ".",
        f"{Path(args.video).stem}_shots.html")
    video_src = args.video_src or os.path.basename(args.video)

    print(f"Processing {args.video}")
    shots = detect_shots(args.video, threshold=args.threshold,
                         min_scene_len=args.min_scene_len)

    with open(json_path, "w") as f:
        json.dump([{k: v for k, v in s.items()
                    if k not in ("first_frame", "last_frame")} for s in shots],
                  f, indent=2)
    print(f"  JSON saved: {json_path}")

    extract_all_frames(args.video, shots)

    html = generate_html(ep_name, shots, video_src)
    with open(html_path, "w") as f:
        f.write(html)
    size_mb = os.path.getsize(html_path) / 1024 / 1024
    print(f"  HTML: {html_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
