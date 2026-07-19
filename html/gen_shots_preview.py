#!/usr/bin/env python3
"""Generate V3 HTML preview from fusion shot data."""
import json, base64, subprocess, os, tempfile, re

shots = json.load(open("/tmp/ep01_v3b_shots.json"))
video_path = "/home/kai/Downloads/bilibili_xiaojianghu/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。.mp4"

def extract_frame_b64(vp, ts, q=2):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    subprocess.run(["ffmpeg","-y","-ss",str(ts),"-i",vp,"-frames:v","1","-q:v",str(q),"-vf","scale=480:-1",tmp,"-loglevel","error"], capture_output=True, timeout=10)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 100:
        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp)
        return "data:image/jpeg;base64," + b64
    if os.path.exists(tmp):
        os.unlink(tmp)
    return ""

print("Extracting frames...", flush=True)
for i, s in enumerate(shots):
    s["first_frame"] = extract_frame_b64(video_path, s["start_sec"])
    s["last_frame"] = extract_frame_b64(video_path, max(s["end_sec"] - 0.05, s["start_sec"]))
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(shots)}", flush=True)

# Build HTML — reuse CSS/JS from V2
ep_name = "ep01"
video_filename = "xiaojianghu_ep01.mp4"
total_duration = shots[-1]["end_sec"]
shot_data_js = json.dumps([{k: v for k, v in s.items() if k not in ("first_frame", "last_frame")} for s in shots])

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

# Read CSS/JS from V2 file
with open("/home/kai/range_server/xiaojianghu_ep01_shots_v2.html") as f:
    v2html = f.read()
css_start = v2html.index("<style>")
css_end = v2html.index("</style>") + 8
css_block = v2html[css_start:css_end]

js_start = v2html.index("<script>")
js_end = v2html.index("</script>") + 9
js_block = v2html[js_start:js_end]
js_block = re.sub(r"const shots = \[.*?\];", f"const shots = {shot_data_js};", js_block)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜预览 V3 - 小江湖 {ep_name}</title>
{css_block}
</head>
<body>

<div class="header">
  <div class="header-top">
      <h1>🎬 小江湖 {ep_name}</h1>
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
              <source src="{video_filename}" type="video/mp4">
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

html_path = "/home/kai/range_server/xiaojianghu_ep01_shots.html"
with open(html_path, "w") as f:
    f.write(html)
size_mb = os.path.getsize(html_path) / 1024 / 1024
print(f"HTML: {html_path} ({size_mb:.1f} MB)")

dst = "/home/kai/shared/xiaojianghu_ep01_shots.html"
if os.path.exists(dst) and os.path.islink(dst):
    pass  # already symlinked
elif os.path.exists(dst):
    os.unlink(dst)
    os.symlink(html_path, dst)
else:
    os.symlink(html_path, dst)
print("Synced to shared/")
