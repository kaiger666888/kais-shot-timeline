#!/usr/bin/env python3
"""从分镜 JSON 生成 V3 风格 HTML 预览（参数化版本）。

读取 detect_v3b.py 的输出（或任意分镜 JSON），抽取首尾帧，生成与 V2 同款
CSS/JS 的卡片网格 HTML。

用法：
  python html/gen_shots_preview.py --video input.mp4 --shots shots.json
                                   [--output shots.html]
                                   [--video-src video.mp4]
                                   [--ep-name ep01]
                                   [--v2-html existing_v2.html]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def extract_frame_b64(video_path: str, ts: float, q: int = 2) -> str:
    """抽单帧 → base64 data URI。"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path, "-frames:v", "1",
         "-q:v", str(q), "-vf", "scale=480:-1", tmp, "-loglevel", "error"],
        capture_output=True, timeout=10)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 100:
        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp)
        return "data:image/jpeg;base64," + b64
    if os.path.exists(tmp):
        os.unlink(tmp)
    return ""


def extract_first_last_frames(video_path: str, shots: list):
    """为每个 shot 添加 first_frame / last_frame（base64 data URI）。"""
    print(f"Extracting first/last frames from {video_path}...", flush=True)
    for i, s in enumerate(shots):
        s["first_frame"] = extract_frame_b64(video_path, s["start_sec"])
        s["last_frame"] = extract_frame_b64(
            video_path, max(s["end_sec"] - 0.05, s["start_sec"]))
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(shots)}", flush=True)


def build_default_css() -> str:
    """若无 V2 HTML 可复用，使用内置 CSS（与 V2 一致）。"""
    return """<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 380px; }
body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }

.header { position: sticky; top: 0; z-index: 200; background: #161b22; border-bottom: 1px solid #30363d; }
.header-top { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 10px 20px 4px; }
.header-top h1 { font-size: 18px; color: #58a6ff; }
.stats { color: #8b949e; font-size: 13px; }
.badge { background: #1f6feb; color: white; font-size: 11px; padding: 2px 8px; border-radius: 10px; }

.toolbar { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.cols-btn { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.cols-btn.active { background: #1f6feb; border-color: #1f6feb; color: white; }

.player-section { padding: 4px 16px 10px; }
video { width: 100%; max-height: 60vh; border-radius: 8px; object-fit: contain; }
.current-shot-info { text-align: center; padding: 2px; color: #58a6ff; font-size: 13px; }

.shots-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 16px; max-width: 1800px; margin: 0 auto; }
.shots-grid.cols-1 { grid-template-columns: 1fr; max-width: 900px; }
.shots-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }
.shots-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
.shots-grid.cols-4 { grid-template-columns: repeat(4, 1fr); }
.shots-grid.cols-5 { grid-template-columns: repeat(5, 1fr); }
.shots-grid.cols-6 { grid-template-columns: repeat(6, 1fr); }
.shots-grid.cols-8 { grid-template-columns: repeat(8, 1fr); }

.shot-card { background: #161b22; border: 2px solid #30363d; border-radius: 10px; overflow: hidden; cursor: pointer; transition: all 0.2s; position: relative; }
.shot-card:hover { border-color: #58a6ff; transform: translateY(-3px); }
.shot-card.playing { border-color: #f85149; box-shadow: 0 0 16px rgba(248,81,73,0.5); }
.shot-card.short { border-left: 4px solid #d29922; }
.shot-card.long { border-left: 4px solid #3fb950; }

.shot-header { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: rgba(0,0,0,0.3); }
.shot-num { color: #58a6ff; font-size: 13px; font-weight: 700; }
.shot-dur { color: #8b949e; font-size: 11px; }

.frames { display: flex; gap: 3px; padding: 0 3px; }
.frame { flex: 1; position: relative; }
.frame img { width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; border-radius: 4px; }
.frame-label { position: absolute; bottom: 3px; left: 3px; background: rgba(0,0,0,0.75); color: #aaa; font-size: 9px; padding: 1px 5px; border-radius: 3px; }
.shot-times { padding: 4px 10px 6px; font-size: 11px; color: #8b949e; display: flex; justify-content: space-between; }

.nav { position: sticky; bottom: 0; background: #161b22; border-top: 1px solid #30363d; padding: 8px 20px; display: flex; justify-content: center; gap: 12px; z-index: 100; }
.nav button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
</style>"""


def main():
    ap = argparse.ArgumentParser(
        description="V3 风格分镜预览 HTML 生成器（从分镜 JSON）")
    ap.add_argument("--video", required=True, help="原视频路径（用于抽帧）")
    ap.add_argument("--shots", required=True, help="分镜 JSON")
    ap.add_argument("--output", default=None,
                    help="输出 HTML 路径（默认 <shots>_shots.html）")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源（默认 --video 的 basename）")
    ap.add_argument("--ep-name", default=None,
                    help="剧集名（默认 <video-basename>）")
    ap.add_argument("--v2-html", default=None,
                    help="可选：已有 V2 HTML 文件，从中复用 CSS/JS 块")
    args = ap.parse_args()

    with open(args.shots) as f:
        shots = json.load(f)

    ep_name = args.ep_name or Path(args.video).stem
    out_html = args.output or os.path.join(
        os.path.dirname(args.shots) or ".",
        f"{Path(args.shots).stem}_shots.html")
    video_src = args.video_src or os.path.basename(args.video)

    extract_first_last_frames(args.video, shots)

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
        <div class="shot-header"><span class="shot-num">#{s['id']}</span><span class="shot-dur">{s['duration']:.1f}s</span></div>
        <div class="frames"><div class="frame"><img src="{s['first_frame']}" loading="lazy"><span class="frame-label">{s['start_sec']:.1f}s</span></div><div class="frame"><img src="{s['last_frame']}" loading="lazy"><span class="frame-label">{s['end_sec']:.1f}s</span></div></div>
        <div class="shot-times"><span>{s['start_sec']:.1f}s</span><span>→</span><span>{s['end_sec']:.1f}s</span></div>
    </div>
"""

    # 复用 V2 HTML 的 CSS / JS（可选）
    if args.v2_html and os.path.exists(args.v2_html):
        with open(args.v2_html) as f:
            v2html = f.read()
        css_start = v2html.index("<style>")
        css_end = v2html.index("</style>") + 8
        css_block = v2html[css_start:css_end]
        js_start = v2html.index("<script>")
        js_end = v2html.index("</script>") + 9
        js_block = v2html[js_start:js_end]
        js_block = re.sub(r"const shots = \[.*?\];",
                          f"const shots = {shot_data_js};", js_block, flags=re.DOTALL)
    else:
        css_block = build_default_css()
        js_block = f"""<script>
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
    if (card) card.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
}}

video.addEventListener('timeupdate', () => {{
    if (stopAt !== null && video.currentTime >= stopAt) {{
        video.pause();
        stopAt = null;
    }}
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
</script>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜预览 - {ep_name}</title>
{css_block}
</head>
<body>

<div class="header">
  <div class="header-top">
      <h1>🎬 {ep_name}</h1>
      <span class="badge" style="background:#238636">V3 融合检测</span>
      <div class="stats">{len(shots)} 镜 · {total_duration:.1f}s · 短={sum(1 for s in shots if s['duration'] < 1.5)} · 长={sum(1 for s in shots if s['duration'] > 8)}</div>
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
              <source src="{video_src}" type="video/mp4">
          </video>
          <div class="current-shot-info" id="shotInfo">点击下方分镜卡片播放</div>
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

{js_block}
</body>
</html>"""

    with open(out_html, "w") as f:
        f.write(html)
    size_mb = os.path.getsize(out_html) / 1024 / 1024
    print(f"HTML: {out_html} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
