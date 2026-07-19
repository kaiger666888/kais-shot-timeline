#!/usr/bin/env python3
"""PySceneDetect V2：双检测器组合 + 后处理（参数化版本）。

  - 主检测: AdaptiveDetector(4.0, min_scene_len=30) → 粗切
  - 长镜头(>8s)内部: ContentDetector(22) 二次扫描 → 防漏切
  - 后处理: 合并 <1.2s 碎片到相邻镜头 → 消除误切
  - 帧级精度

用法：
  python detectors/psd_shot_preview_v2.py --video input.mp4
                                          [--output shots.html]
                                          [--json shots.json]
                                          [--adaptive-threshold 4.0]
                                          [--min-scene-len 30]
                                          [--content-threshold 22]
                                          [--long-shot-thresh 8.0]
                                          [--merge-frag 1.2]
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from scenedetect import detect, ContentDetector, AdaptiveDetector


def get_fps(video_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video_path],
        capture_output=True, text=True)
    fps_str = r.stdout.strip()
    if "/" in fps_str:
        num, den = fps_str.split("/")
        return float(num) / float(den)
    return float(fps_str) if fps_str else 30.0


def detect_shots_v2(video_path: str, adaptive_threshold: float = 4.0,
                    min_scene_len: int = 30, content_threshold: float = 22.0,
                    long_shot_thresh: float = 8.0,
                    merge_frag: float = 1.2) -> list:
    fps = get_fps(video_path)

    print(f"  Stage 1: AdaptiveDetector({adaptive_threshold}, min{min_scene_len})...")
    coarse = detect(video_path, AdaptiveDetector(
        adaptive_threshold=adaptive_threshold, min_scene_len=min_scene_len))
    print(f"    {len(coarse)} coarse scenes")

    print(f"  Stage 2: Fine-grained ContentDetector({content_threshold}) "
          f"on long scenes (>{long_shot_thresh}s)...")
    refined = []
    long_count = 0
    for start, end in coarse:
        dur = end.get_seconds() - start.get_seconds()
        if dur > long_shot_thresh:
            sub = detect(
                video_path,
                ContentDetector(threshold=content_threshold, min_scene_len=15),
                start_time=start.get_seconds(),
                end_time=end.get_seconds())
            if len(sub) > 1:
                long_count += 1
                refined.extend(sub)
            else:
                refined.append((start, end))
        else:
            refined.append((start, end))
    print(f"    Refined {long_count} long scenes")
    refined.sort(key=lambda x: x[0].get_seconds())

    print(f"  Stage 3: Merging fragments <{merge_frag}s...")
    merged = list(refined)
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            start, end = merged[i]
            dur = end.get_seconds() - start.get_seconds()
            if dur < merge_frag and len(merged) > 1:
                if i == 0:
                    merged[i + 1] = (start, merged[i + 1][1])
                    del merged[i]
                elif i == len(merged) - 1:
                    merged[i - 1] = (merged[i - 1][0], end)
                    del merged[i]
                else:
                    prev_dur = merged[i - 1][1].get_seconds() - merged[i - 1][0].get_seconds()
                    next_dur = merged[i + 1][1].get_seconds() - merged[i + 1][0].get_seconds()
                    if prev_dur <= next_dur:
                        merged[i - 1] = (merged[i - 1][0], end)
                        del merged[i]
                    else:
                        merged[i + 1] = (start, merged[i + 1][1])
                        del merged[i]
                changed = True
                break

    shots = []
    for i, (start, end) in enumerate(merged):
        s, e = start.get_seconds(), end.get_seconds()
        shots.append({
            "id": i + 1,
            "start_sec": round(s, 3),
            "end_sec": round(e, 3),
            "duration": round(e - s, 3),
        })
    short = sum(1 for s in shots if s["duration"] < merge_frag)
    long_shots = sum(1 for s in shots if s["duration"] > long_shot_thresh)
    avg = sum(s["duration"] for s in shots) / len(shots) if shots else 0
    print(f"  Final: {len(shots)} shots, "
          f"<{merge_frag}s={short}, >{long_shot_thresh}s={long_shots}, "
          f"avg={avg:.1f}s")
    return shots


def extract_frame(video_path: str, timestamp: float, quality: int = 2) -> str:
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
    shot_data_js = json.dumps([
        {k: v for k, v in s.items()
         if k not in ("first_frame", "last_frame")} for s in shots])

    cards = ""
    for s in shots:
        cls = "shot-card"
        if s["duration"] < 1.5:
            cls += " short"
        elif s["duration"] > 8:
            cls += " long"
        cards += f"""    <div class="{cls}" id="shot-{s['id']}" onclick="playShot({s['id']}, {s['start_sec']}, {s['end_sec'] - 0.05})">
        <div class="shot-header">
            <span class="shot-num">#{s['id']}</span>
            <span class="shot-dur">{s['duration']:.1f}s</span>
        </div>
        <div class="frames">
            <div class="frame">
                <img src="{s['first_frame']}" alt="首帧" loading="lazy">
                <span class="frame-label">{s['start_sec']:.1f}s</span>
            </div>
            <div class="frame">
                <img src="{s['last_frame']}" alt="尾帧" loading="lazy">
                <span class="frame-label">{s['end_sec']:.1f}s</span>
            </div>
        </div>
        <div class="shot-times">
            <span>{s['start_sec']:.1f}s</span>
            <span>→</span>
            <span>{s['end_sec']:.1f}s</span>
        </div>
    </div>
"""

    n_short = sum(1 for s in shots if s['duration'] < 1.5)
    n_long = sum(1 for s in shots if s['duration'] > 8)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜预览 V2 - {ep_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 380px; }}
body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }}

.header {{ position: sticky; top: 0; z-index: 200; background: #161b22; border-bottom: 1px solid #30363d; }}
.header-top {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 10px 20px 4px; }}
.header-top h1 {{ font-size: 18px; color: #58a6ff; }}
.stats {{ color: #8b949e; font-size: 13px; }}
.badge {{ background: #1f6feb; color: white; font-size: 11px; padding: 2px 8px; border-radius: 10px; }}

.toolbar {{ display: flex; align-items: center; gap: 8px; margin-left: auto; }}
.toolbar label {{ color: #8b949e; font-size: 12px; }}
.cols-btn {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.15s; }}
.cols-btn:hover {{ background: #30363d; }}
.cols-btn.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}

.player-section {{ padding: 4px 16px 10px; }}
.player-container {{ max-width: 100%; margin: 0 auto; position: relative; }}
video {{ width: 100%; max-height: 60vh; border-radius: 8px; object-fit: contain; }}
.current-shot-info {{ text-align: center; padding: 2px; color: #58a6ff; font-size: 13px; }}

.player-size-btns {{ display: flex; gap: 6px; justify-content: center; margin-top: 4px; }}
.player-size-btns button {{ background: #21262d; color: #8b949e; border: 1px solid #30363d; padding: 2px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }}
.player-size-btns button.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}

.shots-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    padding: 16px;
    max-width: 1800px;
    margin: 0 auto;
    transition: grid-template-columns 0.2s ease;
}}
.shots-grid.cols-1 {{ grid-template-columns: 1fr; max-width: 900px; }}
.shots-grid.cols-2 {{ grid-template-columns: repeat(2, 1fr); }}
.shots-grid.cols-3 {{ grid-template-columns: repeat(3, 1fr); }}
.shots-grid.cols-4 {{ grid-template-columns: repeat(4, 1fr); }}
.shots-grid.cols-5 {{ grid-template-columns: repeat(5, 1fr); }}
.shots-grid.cols-6 {{ grid-template-columns: repeat(6, 1fr); }}
.shots-grid.cols-8 {{ grid-template-columns: repeat(8, 1fr); }}

.shot-card {{ background: #161b22; border: 2px solid #30363d; border-radius: 10px; overflow: hidden; cursor: pointer; transition: all 0.2s; position: relative; }}
.shot-card:hover {{ border-color: #58a6ff; transform: translateY(-3px); }}
.shot-card.playing {{ border-color: #f85149; box-shadow: 0 0 16px rgba(248,81,73,0.5); }}
.shot-card.short {{ border-left: 4px solid #d29922; }}
.shot-card.long {{ border-left: 4px solid #3fb950; }}

.shot-header {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: rgba(0,0,0,0.3); }}
.shot-num {{ color: #58a6ff; font-size: 13px; font-weight: 700; }}
.shot-dur {{ color: #8b949e; font-size: 11px; }}

.frames {{ display: flex; gap: 3px; padding: 0 3px; }}
.frame {{ flex: 1; position: relative; }}
.frame img {{ width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; border-radius: 4px; }}
.frame-label {{ position: absolute; bottom: 3px; left: 3px; background: rgba(0,0,0,0.75); color: #aaa; font-size: 9px; padding: 1px 5px; border-radius: 3px; }}
.shot-times {{ padding: 4px 10px 6px; font-size: 11px; color: #8b949e; display: flex; justify-content: space-between; }}

.nav {{ position: sticky; bottom: 0; background: #161b22; border-top: 1px solid #30363d; padding: 8px 20px; display: flex; justify-content: center; gap: 12px; z-index: 100; }}
.nav button {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
.nav button:hover {{ background: #30363d; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
      <h1>🎬 {ep_name}</h1>
      <span class="badge">双检测器+后处理</span>
      <div class="stats">{len(shots)} 镜 · {total_duration:.1f}s · 短={n_short} · 长={n_long}</div>
      <div class="toolbar">
          <label>每行</label>
          <button class="cols-btn" onclick="setCols(1)">1</button>
          <button class="cols-btn" onclick="setCols(2)">2</button>
          <button class="cols-btn" onclick="setCols(3)">3</button>
          <button class="cols-btn active" onclick="setCols(4)">4</button>
          <button class="cols-btn" onclick="setCols(5)">5</button>
          <button class="cols-btn" onclick="setCols(6)">6</button>
          <button class="cols-btn" onclick="setCols(8)">8</button>
      </div>
  </div>
  <div class="player-section">
      <div class="player-container">
          <video id="player" controls preload="metadata">
              <source src="{video_filename}" type="video/mp4">
          </video>
          <div class="current-shot-info" id="shotInfo">点击下方分镜卡片播放</div>
          <div class="player-size-btns">
              <button onclick="setPlayerSize('40vh')">小</button>
              <button onclick="setPlayerSize('60vh')" class="active">中</button>
              <button onclick="setPlayerSize('80vh')">大</button>
              <button onclick="setPlayerSize('95vh')">全屏</button>
          </div>
      </div>
  </div>
</div>

<div class="shots-grid cols-4" id="shotsGrid">
{cards}</div>

<div class="nav">
    <button onclick="prevShot()">⬅ 上一镜</button>
    <button onclick="togglePlay()">⏯ 播放/暂停</button>
    <button onclick="nextShot()">下一镜 ➡</button>
</div>

<script>
const video = document.getElementById('player');
const shotInfo = document.getElementById('shotInfo');
const grid = document.getElementById('shotsGrid');
const shots = {shot_data_js};
let currentShot = null;
let stopAt = null;

function setCols(n) {{
    grid.className = 'shots-grid cols-' + n;
    document.querySelectorAll('.cols-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    localStorage.setItem('shotGridCols', n);
}}

function setPlayerSize(size) {{
    document.getElementById('player').style.maxHeight = size;
    document.querySelectorAll('.player-size-btns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    localStorage.setItem('playerSize', size);
}}

const savedSize = localStorage.getItem('playerSize');
if (savedSize) {{
    document.getElementById('player').style.maxHeight = savedSize;
    document.querySelectorAll('.player-size-btns button').forEach(b => {{
        if (b.textContent === {{'40vh':'小','60vh':'中','80vh':'大','95vh':'全屏'}}[savedSize]) b.classList.add('active');
        else b.classList.remove('active');
    }});
}}

const savedCols = localStorage.getItem('shotGridCols');
if (savedCols) {{
    grid.className = 'shots-grid cols-' + savedCols;
    document.querySelectorAll('.cols-btn').forEach(b => {{
        if (b.textContent === savedCols) b.classList.add('active');
        else b.classList.remove('active');
    }});
}}

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
    if (card) {{
        const headerEl = document.querySelector('.header');
        const offset = headerEl ? headerEl.offsetHeight + 8 : 0;
        const rect = card.getBoundingClientRect();
        const scrollTop = window.pageYOffset + rect.top - offset;
        window.scrollTo({{ top: scrollTop, behavior: 'smooth' }});
    }}
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
    if (e.target.tagName === 'BUTTON') return;
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
        description="PySceneDetect V2：双检测器 + 后处理 + HTML 预览")
    ap.add_argument("--video", required=True, help="输入视频路径")
    ap.add_argument("--adaptive-threshold", type=float, default=4.0,
                    help="AdaptiveDetector 阈值（默认 4.0）")
    ap.add_argument("--min-scene-len", type=int, default=30,
                    help="AdaptiveDetector 最小场景帧数（默认 30）")
    ap.add_argument("--content-threshold", type=float, default=22.0,
                    help="长镜头二次扫描 ContentDetector 阈值（默认 22）")
    ap.add_argument("--long-shot-thresh", type=float, default=8.0,
                    help="长镜头阈值（默认 8s，超过此长度触发二次扫描）")
    ap.add_argument("--merge-frag", type=float, default=1.2,
                    help="碎片合并阈值（默认 1.2s）")
    ap.add_argument("--ep-name", default=None,
                    help="剧集名（默认 <video-basename>）")
    ap.add_argument("--json", default=None,
                    help="输出分镜 JSON 路径（默认 <video-basename>_shots_v2.json）")
    ap.add_argument("--output", default=None,
                    help="输出 HTML 路径（默认 <video-basename>_shots_v2.html）")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源（默认 --video 的 basename）")
    args = ap.parse_args()

    ep_name = args.ep_name or Path(args.video).stem
    json_path = args.json or os.path.join(
        os.path.dirname(args.video) or ".",
        f"{Path(args.video).stem}_shots_v2.json")
    html_path = args.output or os.path.join(
        os.path.dirname(args.video) or ".",
        f"{Path(args.video).stem}_shots_v2.html")
    video_src = args.video_src or os.path.basename(args.video)

    print(f"Processing {args.video}")
    shots = detect_shots_v2(
        args.video, adaptive_threshold=args.adaptive_threshold,
        min_scene_len=args.min_scene_len,
        content_threshold=args.content_threshold,
        long_shot_thresh=args.long_shot_thresh,
        merge_frag=args.merge_frag)

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
