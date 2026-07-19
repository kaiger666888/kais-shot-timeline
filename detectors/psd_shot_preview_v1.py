#!/usr/bin/env python3
"""
PySceneDetect 分镜检测 + HTML 预览生成器
- 用 AdaptiveDetector（滑窗自适应阈值，适合动画）
- 帧级精度，直接输出每个 shot 的起止时间
- 首尾帧用 ffmpeg 从原视频精确抽取
- HTML 内嵌 base64 图片 + playShot 点击播放
"""

import os, sys, json, base64, subprocess, tempfile, time
from scenedetect import detect, ContentDetector, AdaptiveDetector

VIDEO_DIR = "/home/kai/Downloads/bilibili_xiaojianghu"
TMP_DIR = "/tmp/xiaojianghu_psd"
OUTPUT_DIR = "/home/kai/range_server"

EPISODES = {
    "ep01": "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。.mp4",
    "ep02": "虫虫武侠小故事《小江湖》第02话：刀和小番茄（ 有苦有甜，才是人生.mp4",
    "ep03": "《小江湖》第03话：白头发的少女（画面只是工具，情绪是目的.mp4",
}


def detect_shots(h264_path, video_path):
    """Run PySceneDetect with AdaptiveDetector, return list of shots."""
    print(f"  Detecting scenes with AdaptiveDetector...")
    t0 = time.time()
    
    # AdaptiveDetector: sliding window + adaptive threshold
    # threshold=3.0 (default), min_scene_len=15 frames
    scenes = detect(
        h264_path,
        AdaptiveDetector(
            adaptive_threshold=3.0,
            min_scene_len=15,  # 0.5s at 30fps
        ),
    )
    
    elapsed = time.time() - t0
    print(f"  Found {len(scenes)} scenes in {elapsed:.1f}s")
    
    # Build shot list with frame-accurate times
    shots = []
    for i, (start, end) in enumerate(scenes):
        start_sec = start.get_seconds()
        end_sec = end.get_seconds()
        duration = end_sec - start_sec
        shots.append({
            "id": i + 1,
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "duration": round(duration, 3),
        })
    
    return shots


def extract_frame(video_path, timestamp, quality=2):
    """Extract a single frame at given timestamp using ffmpeg, return base64."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name
    
    cmd = [
        "ffmpeg", "-y", "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", str(quality),
        "-vf", "scale=480:-1",  # 480px wide thumbnail
        tmp_path,
        "-loglevel", "error",
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)
    
    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
        with open(tmp_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp_path)
        return f"data:image/jpeg;base64,{b64}"
    else:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return ""


def extract_all_frames(video_path, shots):
    """Extract first and last frame for each shot."""
    print(f"  Extracting frames for {len(shots)} shots...")
    for i, shot in enumerate(shots):
        # First frame: at start_sec
        shot["first_frame"] = extract_frame(video_path, shot["start_sec"])
        # Last frame: at end_sec - 0.05 (slightly before the cut)
        last_ts = max(shot["end_sec"] - 0.05, shot["start_sec"])
        shot["last_frame"] = extract_frame(video_path, last_ts)
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(shots)} frames extracted")
    print(f"  All frames extracted.")


def generate_html(ep_name, shots, video_filename, video_path):
    """Generate self-contained HTML preview."""
    
    # Get video duration for the video element
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True
    )
    video_duration = float(result.stdout.strip()) if result.stdout.strip() else 300
    
    # Copy video to range_server dir if not already there
    dest_video = os.path.join(OUTPUT_DIR, video_filename)
    if not os.path.exists(dest_video):
        # Create symlink to avoid copying large files
        try:
            os.symlink(video_path, dest_video)
        except FileExistsError:
            pass
    
    total_duration = shots[-1]["end_sec"] if shots else 0
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜预览 - 小江湖 {ep_name}</title>
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
    <h1>🎬 小江湖 {ep_name} — 分镜预览 (PySceneDetect)</h1>
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
    
    html += f"""</div>

<div class="nav">
    <button onclick="prevShot()">⬅ 上一镜</button>
    <button onclick="togglePlay()">⏯ 播放/暂停</button>
    <button onclick="nextShot()">下一镜 ➡</button>
</div>

<script>
const video = document.getElementById('player');
const shotInfo = document.getElementById('shotInfo');
const shots = {json.dumps([{k: v for k, v in s.items() if k not in ('first_frame', 'last_frame')} for s in shots])};
let currentShot = null;
let stopAt = null;

function playShot(id, start, stopAtTime) {{
    // Clear previous highlight
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
    
    // Scroll card into view
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

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight') nextShot();
    else if (e.key === 'ArrowLeft') prevShot();
    else if (e.key === ' ') {{ e.preventDefault(); togglePlay(); }}
}});
</script>
</body>
</html>"""
    
    return html


def process_episode(ep_name, video_filename):
    """Full pipeline: transcode → detect → extract frames → generate HTML."""
    video_path = os.path.join(VIDEO_DIR, video_filename)
    h264_path = os.path.join(TMP_DIR, f"{ep_name}_h264.mp4")
    
    # For ep03, use glob to find the file
    if not os.path.exists(video_path):
        import glob
        matches = glob.glob(os.path.join(VIDEO_DIR, f"*{ep_name[-2:]}话*"))
        if matches:
            video_path = matches[0]
    
    print(f"\n{'='*60}")
    print(f"Processing {ep_name}: {os.path.basename(video_path)}")
    print(f"{'='*60}")
    
    # Step 1: Transcode if needed
    if not os.path.exists(h264_path) or os.path.getsize(h264_path) < 1000000:
        print("  Transcoding AV1→H264...")
        t0 = time.time()
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an",
            h264_path
        ], capture_output=True, timeout=300)
        print(f"  Transcoded in {time.time()-t0:.0f}s")
    else:
        print(f"  H264 already exists, skipping transcode")
    
    # Step 2: Detect scenes
    shots = detect_shots(h264_path, video_path)
    
    # Save shot data as JSON
    json_path = os.path.join(OUTPUT_DIR, f"xiaojianghu_{ep_name}_shots.json")
    with open(json_path, "w") as f:
        json.dump([{k: v for k, v in s.items() if k not in ('first_frame', 'last_frame')} for s in shots], f, indent=2)
    print(f"  Shot data saved: {json_path}")
    
    # Step 3: Extract frames (from original AV1 video for best quality)
    extract_all_frames(video_path, shots)
    
    # Step 4: Generate HTML
    html_filename = f"xiaojianghu_{ep_name}_shots.html"
    video_dest_name = f"xiaojianghu_{ep_name}.mp4"
    html = generate_html(ep_name, shots, video_dest_name, video_path)
    
    html_path = os.path.join(OUTPUT_DIR, html_filename)
    with open(html_path, "w") as f:
        f.write(html)
    size_mb = os.path.getsize(html_path) / 1024 / 1024
    print(f"  HTML generated: {html_path} ({size_mb:.1f} MB)")
    
    return shots


if __name__ == "__main__":
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_results = {}
    for ep_name, fname in EPISODES.items():
        shots = process_episode(ep_name, fname)
        all_results[ep_name] = len(shots)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for ep, count in all_results.items():
        print(f"  {ep}: {count} scenes")
