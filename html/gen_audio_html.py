#!/usr/bin/env python3
"""生成音频分析 HTML：分镜缩略图 + 4-stem 能量条 + 对白文本。

参数化版本，输入：
  --video       原视频（用于抽帧）
  --audio-json  audio/separate_stems.py 输出的 per-shot 分析 JSON
  --stems-dir   Demucs stem 目录（vocals/drums/bass/other.wav）
  --output      输出 HTML 路径
  --video-src   HTML 内嵌 <video> 引用的源（默认使用 --video 的 basename）
  --title       页面标题（默认 "音轨分析 - <video basename>"）
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile

import numpy as np


def extract_frame(video_path, timestamp, quality=2):
    """用 ffmpeg 抽取单帧，返回 base64 data URI。"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
               "-frames:v", "1", "-q:v", str(quality), tmp_path]
        subprocess.run(cmd, capture_output=True, timeout=10)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return f"data:image/jpeg;base64,{b64}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return ""


def load_audio_mono(path):
    """读取 wav → 单声道 float32 numpy。"""
    import wave
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
    return audio, sr


def compute_energy_timeline(audio, sr, duration, bucket_ms=100):
    """按 bucket_ms 桶计算 RMS，作为波形条数据。"""
    bucket_size = max(1, int(sr * bucket_ms / 1000))
    n_buckets = int(len(audio) / bucket_size)
    energies = []
    for i in range(n_buckets):
        chunk = audio[i * bucket_size:(i + 1) * bucket_size]
        rms = np.sqrt(np.mean(chunk ** 2) + 1e-10)
        energies.append(float(rms))
    return energies


def type_color(t):
    return {"dialogue": "#58a6ff", "bgm": "#3fb950",
            "sfx": "#d29922", "mixed": "#8b949e"}.get(t, "#666")


def type_icon(t):
    return {"dialogue": "💬", "bgm": "🎵", "sfx": "🔊",
            "mixed": "🔀"}.get(t, "❓")


def build_html(video_path, video_src, audio_data, stems, stem_norm,
               total_dur, title):
    cards = ""
    for shot in audio_data["shots"]:
        rts = shot["ratios"]
        dt = shot["dominant_type"]
        color = type_color(dt)
        icon = type_icon(dt)

        dialogue = " ".join(d["text"] for d in shot.get("dialogue", []))
        if dialogue:
            dialogue_html = f'<div class="dialogue">💬 {dialogue}</div>'
        else:
            dialogue_html = '<div class="dialogue empty">（无对话）</div>'

        voc_h = rts["vocals"] * 100
        drm_h = rts["drums"] * 100
        bas_h = rts["bass"] * 100
        oth_h = rts["other"] * 100

        # 该分镜时间区间内的 vocals 波形条
        s_bucket = int(shot["start_sec"] * 10)
        e_bucket = int(shot["end_sec"] * 10)
        voc_wave = stem_norm.get("vocals", [])[s_bucket:e_bucket]
        wave_bars = "".join(
            f'<div class="wbar" style="height:{max(2, v * 100):.0f}%"></div>'
            for v in voc_wave)

        cls = "shot-card"
        if shot["duration"] < 1.5:
            cls += " short"
        elif shot["duration"] > 8:
            cls += " long"

        cards += f"""    <div class="{cls}" id="shot-{shot['shot_id']}" onclick="playShot({shot['shot_id']}, {shot['start_sec']}, {shot['end_sec'] - 0.05})">
        <div class="shot-header" style="border-left: 3px solid {color}">
            <span class="shot-num">#{shot['shot_id']}</span>
            <span class="shot-type" style="color:{color}">{icon} {dt}</span>
            <span class="shot-dur">{shot['duration']:.1f}s</span>
        </div>
        <div class="frames">
            <div class="frame">
                <img src="{shot.get('first_frame','')}" alt="首帧" loading="lazy">
                <span class="frame-label">{shot['start_sec']:.1f}s</span>
            </div>
        </div>
        <div class="energy-bars">
            <div class="ebar-row">
                <span class="ebar-label">人声</span>
                <div class="ebar-track"><div class="ebar-fill" style="width:{voc_h:.0f}%; background:#58a6ff"></div></div>
                <span class="ebar-val">{rts['vocals']:.0%}</span>
            </div>
            <div class="ebar-row">
                <span class="ebar-label">鼓点</span>
                <div class="ebar-track"><div class="ebar-fill" style="width:{drm_h:.0f}%; background:#3fb950"></div></div>
                <span class="ebar-val">{rts['drums']:.0%}</span>
            </div>
            <div class="ebar-row">
                <span class="ebar-label">低音</span>
                <div class="ebar-track"><div class="ebar-fill" style="width:{bas_h:.0f}%; background:#d29922"></div></div>
                <span class="ebar-val">{rts['bass']:.0%}</span>
            </div>
            <div class="ebar-row">
                <span class="ebar-label">其他</span>
                <div class="ebar-track"><div class="ebar-fill" style="width:{oth_h:.0f}%; background:#f85149"></div></div>
                <span class="ebar-val">{rts['other']:.0%}</span>
            </div>
        </div>
        <div class="waveform">{wave_bars}</div>
        {dialogue_html}
    </div>
"""

    td = audio_data.get("type_distribution", {})
    n_shots = len(audio_data["shots"])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, 'PingFang SC', sans-serif; }}

.header {{ position: sticky; top: 0; z-index: 200; background: #161b22; border-bottom: 1px solid #30363d; }}
.header-top {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 10px 20px 4px; }}
.stats {{ display: flex; gap: 12px; font-size: 13px; color: #8b949e; }}
.legend {{ display: flex; gap: 8px; font-size: 12px; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; }}
.legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

.player-section {{ padding: 4px 16px 10px; }}
video {{ width: 100%; max-height: 60vh; border-radius: 8px; object-fit: contain; }}
.player-size-btns {{ display: flex; gap: 6px; justify-content: center; margin-top: 4px; }}
.player-size-btns button {{ background: #21262d; color: #8b949e; border: 1px solid #30363d;
    padding: 2px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }}
.player-size-btns button.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}

.shots-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 16px; max-width: 1800px; margin: 0 auto; }}
.shots-grid.cols-2 {{ grid-template-columns: repeat(2, 1fr); }}
.shots-grid.cols-3 {{ grid-template-columns: repeat(3, 1fr); }}
.shots-grid.cols-4 {{ grid-template-columns: repeat(4, 1fr); }}

.shot-card {{ background: #161b22; border: 2px solid #30363d; border-radius: 10px; overflow: hidden; cursor: pointer; transition: all 0.2s; }}
.shot-card:hover {{ border-color: #58a6ff; }}
.shot-card.playing {{ border-color: #f85149; box-shadow: 0 0 16px rgba(248,81,73,0.5); }}
.shot-card.short {{ border-left: 4px solid #d29922; }}
.shot-card.long {{ border-left: 4px solid #3fb950; }}

.shot-header {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: rgba(0,0,0,0.3); font-size: 13px; }}
.shot-num {{ color: #58a6ff; font-weight: 700; }}
.shot-type {{ font-size: 11px; text-transform: uppercase; }}
.shot-dur {{ color: #8b949e; }}

.frames {{ padding: 0 3px; }}
.frame {{ position: relative; }}
.frame img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; border-radius: 4px; }}
.frame-label {{ position: absolute; bottom: 2px; left: 4px; font-size: 10px; background: rgba(0,0,0,0.7); padding: 1px 4px; border-radius: 2px; }}

.energy-bars {{ padding: 8px 10px 4px; }}
.ebar-row {{ display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }}
.ebar-label {{ font-size: 10px; width: 24px; color: #8b949e; }}
.ebar-track {{ flex: 1; height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; }}
.ebar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
.ebar-val {{ font-size: 10px; width: 30px; text-align: right; color: #8b949e; }}

.waveform {{ display: flex; align-items: flex-end; gap: 1px; height: 30px; padding: 4px 10px; }}
.wbar {{ flex: 1; background: #58a6ff; opacity: 0.6; border-radius: 1px; min-width: 1px; }}

.dialogue {{ padding: 4px 10px 8px; font-size: 12px; line-height: 1.5; color: #c9d1d9; }}
.dialogue.empty {{ color: #484f58; font-style: italic; }}

.cols-btn {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }}
.cols-btn.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}
.toolbar {{ display: flex; align-items: center; gap: 8px; margin-left: auto; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-top">
    <h1>🎵 {title} ({n_shots} shots)</h1>
    <div class="stats">
      <span>⏱ {total_dur:.1f}s</span>
      <span>💬 {td.get('dialogue',0)}对话</span>
      <span>🎵 {td.get('bgm',0)}BGM</span>
      <span>🔊 {td.get('sfx',0)}音效</span>
      <span>🔀 {td.get('mixed',0)}混合</span>
    </div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#58a6ff"></div>人声</div>
      <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div>鼓/BGM</div>
      <div class="legend-item"><div class="legend-dot" style="background:#d29922"></div>低音</div>
      <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div>环境/其他</div>
    </div>
    <div class="toolbar">
      <button class="cols-btn" onclick="setCols(2)">2</button>
      <button class="cols-btn active" onclick="setCols(3)">3</button>
      <button class="cols-btn" onclick="setCols(4)">4</button>
    </div>
  </div>
  <div class="player-section">
    <video id="player" controls preload="metadata">
      <source src="{video_src}" type="video/mp4">
    </video>
    <div class="player-size-btns">
      <button onclick="setPlayerSize('40vh')">小</button>
      <button onclick="setPlayerSize('60vh')" class="active">中</button>
      <button onclick="setPlayerSize('80vh')">大</button>
    </div>
  </div>
</div>
<div class="shots-grid cols-3" id="grid">
{cards}
</div>
<script>
const video = document.getElementById('player');
const grid = document.getElementById('grid');
let stopAt = null;

function setCols(n) {{
    grid.className = 'shots-grid cols-' + n;
    document.querySelectorAll('.cols-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    localStorage.setItem('audioGridCols', n);
}}
function setPlayerSize(s) {{
    document.getElementById('player').style.maxHeight = s;
    document.querySelectorAll('.player-size-btns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    localStorage.setItem('playerSize', s);
}}
function playShot(id, start, end) {{
    document.querySelectorAll('.shot-card').forEach(c => c.classList.remove('playing'));
    document.getElementById('shot-'+id)?.classList.add('playing');
    stopAt = end;
    video.currentTime = start;
    video.play().catch(() => {{}});
    const card = document.getElementById('shot-'+id);
    if (card) {{
        const h = document.querySelector('.header').offsetHeight + 8;
        const r = card.getBoundingClientRect();
        window.scrollTo({{ top: window.pageYOffset + r.top - h, behavior: 'smooth' }});
    }}
}}
video.addEventListener('timeupdate', () => {{
    if (stopAt !== null && video.currentTime >= stopAt) {{
        video.pause(); stopAt = null;
    }}
}});

document.addEventListener('keydown', e => {{
    const cards = [...document.querySelectorAll('.shot-card')];
    const active = document.querySelector('.shot-card.playing');
    let idx = active ? cards.indexOf(active) : -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {{
        e.preventDefault();
        idx = Math.min(idx + 1, cards.length - 1);
        cards[idx]?.click();
    }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
        e.preventDefault();
        idx = Math.max(idx - 1, 0);
        cards[idx]?.click();
    }}
}});

const sc = localStorage.getItem('audioGridCols');
if (sc) {{
    grid.className = 'shots-grid cols-' + sc;
    document.querySelectorAll('.cols-btn').forEach(b => b.classList.toggle('active', b.textContent === sc));
}}
const ss = localStorage.getItem('playerSize');
if (ss) {{
    document.getElementById('player').style.maxHeight = ss;
}}
</script>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser(description="音频分析 HTML 生成器")
    ap.add_argument("--video", required=True, help="原视频路径（用于抽帧）")
    ap.add_argument("--audio-json", required=True,
                    help="audio/separate_stems.py 输出的 JSON")
    ap.add_argument("--stems-dir", required=True,
                    help="Demucs stem 目录（含 vocals/drums/bass/other.wav）")
    ap.add_argument("--output", required=True, help="输出 HTML 路径")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源（默认 --video 的 basename）")
    ap.add_argument("--title", default=None,
                    help="页面标题（默认 '音轨分析 - <video basename>'）")
    ap.add_argument("--extract-frames", action="store_true", default=True,
                    help="从视频抽首帧并写入 audio_json（默认开启）")
    ap.add_argument("--no-extract-frames", dest="extract_frames",
                    action="store_false",
                    help="跳过抽帧（要求 audio_json 已含 first_frame）")
    args = ap.parse_args()

    video_src = args.video_src or os.path.basename(args.video)
    title = args.title or f"音轨分析 - {os.path.basename(args.video)}"

    with open(args.audio_json) as f:
        data = json.load(f)
    shots = data["shots"]

    # 加载 stem 波形
    print(f"[gen-audio-html] Loading stems from {args.stems_dir}")
    stems = {}
    for name in ("vocals", "drums", "bass", "other"):
        p = os.path.join(args.stems_dir, f"{name}.wav")
        if os.path.exists(p):
            audio, sr = load_audio_mono(p)
            stems[name] = compute_energy_timeline(audio, sr, data["duration"])
            print(f"  {name}: {len(stems[name])} buckets")

    # 抽首帧
    if args.extract_frames:
        print(f"[gen-audio-html] Extracting first-frames from {args.video}")
        for i, shot in enumerate(shots):
            shot["first_frame"] = extract_frame(args.video, shot["start_sec"])
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(shots)}")
        # 抽完帧把扩展后的 shots 写回 JSON，方便后续 timeline HTML 复用
        with open(args.audio_json, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    if stems:
        max_energy = max(max(e for e in stems[k]) for k in stems)
        stem_norm = {k: [min(1.0, e / max_energy) if max_energy > 0 else 0.0
                         for e in stems[k]] for k in stems}
    else:
        stem_norm = {}

    html = build_html(args.video, video_src, data, stems, stem_norm,
                      data["duration"], title)
    with open(args.output, "w") as f:
        f.write(html)
    print(f"[gen-audio-html] wrote {len(html):,} bytes → {args.output}")


if __name__ == "__main__":
    main()
