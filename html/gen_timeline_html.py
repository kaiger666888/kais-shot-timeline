#!/usr/bin/env python3
"""Build the timeline audio analysis HTML."""
import json, sys

def main():
    shots_json = sys.argv[1]   # /tmp/ep01_v3b_shots.json
    audio_json = sys.argv[2]   # /tmp/ep01_audio_analysis.json
    frames_json = sys.argv[3]  # /tmp/ep01_frames_data.json
    js_stems_json = sys.argv[4] # /tmp/ep01_js_stems.json
    output_html = sys.argv[5]
    video_src = sys.argv[6] if len(sys.argv) > 6 else "xiaojianghu_ep01.mp4"

    shots = json.load(open(shots_json))
    audio_data = json.load(open(audio_json))
    frames_data = json.load(open(frames_json))
    js_stems = json.load(open(js_stems_json))

    total_duration = shots[-1]["end_sec"]

    frames_by_id = {f["id"]: f for f in frames_data}
    audio_by_id = {s["shot_id"]: s for s in audio_data["shots"]}

    js_shots = []
    for shot in shots:
        fr = frames_by_id.get(shot["id"], {})
        au = audio_by_id.get(shot["id"], {})
        js_shots.append({
            "id": shot["id"],
            "start": round(shot["start_sec"], 2),
            "end": round(shot["end_sec"], 2),
            "dur": round(shot["duration"], 2),
            "ff": fr.get("first_frame", ""),
            "lf": fr.get("last_frame", ""),
            "type": au.get("dominant_type", "mixed"),
            "dialogue": " ".join(d["text"] for d in au.get("dialogue", [])),
        })

    shots_js = json.dumps(js_shots, ensure_ascii=False)
    stems_js = json.dumps(js_stems)
    dur_js = total_duration

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>音轨时间轴 - 小江湖 01</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#c9d1d9; font-family:-apple-system,'PingFang SC',sans-serif; overflow:hidden; }}

/* ===== Layout: left shots list + right timeline ===== */
.app {{ display:flex; height:100vh; }}
.left-panel {{ width:42%; overflow-y:auto; border-right:1px solid #30363d; }}
.right-panel {{ flex:1; display:flex; flex-direction:column; overflow:hidden; }}

/* ===== Sticky video player (top of right panel) ===== */
.player-bar {{ position:sticky; top:0; z-index:200; background:#161b22; border-bottom:1px solid #30363d; padding:8px 12px; display:flex; align-items:center; gap:12px; }}
.player-bar video {{ height:80px; border-radius:6px; cursor:pointer; }}
.player-bar .time-display {{ font-size:14px; color:#58a6ff; font-family:monospace; min-width:100px; }}
.player-bar .shot-info {{ font-size:12px; color:#8b949e; }}

/* ===== Left: shot list (1 row each) ===== */
.shot-row {{ display:flex; align-items:center; gap:8px; padding:4px 8px; border-bottom:1px solid #21262d; cursor:pointer; transition:background 0.15s; }}
.shot-row:hover {{ background:#161b22; }}
.shot-row.active {{ background:#1a1f35; border-left:3px solid #58a6ff; }}
.shot-row .num {{ width:30px; font-size:12px; color:#58a6ff; font-weight:700; text-align:right; flex-shrink:0; }}
.shot-row .thumb {{ width:96px; height:54px; position:relative; flex-shrink:0; }}
.shot-row .thumb img {{ width:48px; height:100%; object-fit:cover; border-radius:3px 0 0 3px; }}
.shot-row .thumb img:last-child {{ border-radius:0 3px 3px 0; }}
.shot-row .thumb .arrow {{ position:absolute; left:46px; top:50%; transform:translateY(-50%); color:#484f58; font-size:10px; }}
.shot-row .meta {{ flex:1; min-width:0; }}
.shot-row .times {{ font-size:11px; color:#8b949e; font-family:monospace; }}
.shot-row .dur {{ color:#d29922; font-weight:600; }}
.shot-row .type-badge {{ font-size:10px; padding:1px 5px; border-radius:3px; margin-left:4px; }}
.shot-row .dialogue-text {{ font-size:11px; color:#8b949e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px; }}
.type-dialogue {{ background:#1a3a5e; color:#58a6ff; }}
.type-bgm {{ background:#1a3e1a; color:#3fb950; }}
.type-sfx {{ background:#3e351a; color:#d29922; }}
.type-mixed {{ background:#2a2a3e; color:#8b949e; }}

/* ===== Right: vertical timeline ===== */
.timeline-container {{ flex:1; overflow-y:auto; overflow-x:hidden; position:relative; padding:0; }}
.timeline-inner {{ position:relative; min-height:100%; }}

/* Time axis labels on the left edge of timeline */
.time-axis {{ position:absolute; left:0; top:0; bottom:0; width:40px; border-right:1px solid #21262d; z-index:5; }}
.time-tick {{ position:absolute; right:4px; font-size:9px; color:#484f58; font-family:monospace; transform:translateY(-50%); }}

/* Playhead line */
.playhead {{ position:absolute; left:40px; right:0; height:2px; background:#f85149; z-index:50; pointer-events:none; }}
.playhead::before {{ content:''; position:absolute; left:-5px; top:-4px; width:10px; height:10px; background:#f85149; border-radius:50%; }}

/* Track rows */
.track {{ position:relative; height:120px; border-bottom:1px solid #21262d; }}
.track-label {{ position:absolute; left:44px; top:4px; font-size:11px; z-index:10; font-weight:600; }}
.track-label.vocals {{ color:#58a6ff; }}
.track-label.bgm {{ color:#3fb950; }}
.track-label.sfx {{ color:#d29922; }}
.track-canvas {{ position:absolute; left:40px; right:0; top:0; bottom:0; }}

/* Shot boundary markers on timeline */
.shot-marker {{ position:absolute; left:40px; width:1px; background:#30363d; z-index:5; opacity:0.5; }}
.shot-marker-label {{ position:absolute; left:42px; font-size:8px; color:#484f58; background:#0d1117; padding:0 2px; z-index:6; white-space:nowrap; transform:translateY(-50%); }}

/* Click overlay for seeking */
.click-overlay {{ position:absolute; left:40px; right:0; top:0; bottom:0; cursor:crosshair; z-index:20; }}
</style>
</head>
<body>
<div class="app">
  <!-- LEFT: shot list -->
  <div class="left-panel" id="leftPanel">
    <div style="padding:8px 12px; background:#161b22; border-bottom:1px solid #30363d; position:sticky; top:0; z-index:100;">
      <span style="font-size:14px; font-weight:700;">📋 分镜 ({len(shots)} shots, {total_duration:.1f}s)</span>
    </div>
    <div id="shotList"></div>
  </div>

  <!-- RIGHT: timeline + player -->
  <div class="right-panel">
    <div class="player-bar">
      <video id="player" controls preload="metadata" onclick="togglePlay()">
        <source src="{video_src}" type="video/mp4">
      </video>
      <div>
        <div class="time-display" id="timeDisplay">0.0s / {total_duration:.1f}s</div>
        <div class="shot-info" id="shotInfo">点击任意位置播放</div>
      </div>
    </div>
    <div class="timeline-container" id="timelineContainer">
      <div class="timeline-inner" id="timelineInner">
        <div class="time-axis" id="timeAxis"></div>
        <div id="markers"></div>
        <div id="tracks"></div>
        <div class="playhead" id="playhead" style="top:0;"></div>
      </div>
    </div>
  </div>
</div>

<script>
const SHOTS = {shots_js};
const STEMS = {stems_js};
const DURATION = {dur_js};
const N_POINTS = STEMS.vocals.length; // 881
const PX_PER_SEC = 25; // timeline height: 25px per second
const TIMELINE_HEIGHT = DURATION * PX_PER_SEC;

const video = document.getElementById('player');
const timeDisplay = document.getElementById('timeDisplay');
const shotInfo = document.getElementById('shotInfo');
const playhead = document.getElementById('playhead');
const timelineInner = document.getElementById('timelineInner');
const timelineContainer = document.getElementById('timelineContainer');

let currentShot = null;

// === Build shot list (left panel) ===
const typeColors = {{dialogue:'#58a6ff', bgm:'#3fb950', sfx:'#d29922', mixed:'#8b949e'}};
const typeIcons = {{dialogue:'💬', bgm:'🎵', sfx:'🔊', mixed:'🔀'}};

const shotList = document.getElementById('shotList');
SHOTS.forEach(s => {{
    const row = document.createElement('div');
    row.className = 'shot-row';
    row.id = 'shot-row-' + s.id;
    row.onclick = () => playAt(s.start, s.id);
    
    const durClass = s.dur < 1.5 ? 'dur' : '';
    const tColor = typeColors[s.type] || '#8b949e';
    const tIcon = typeIcons[s.type] || '❓';
    const dlg = s.dialogue ? s.dialogue.substring(0, 60) : '<span style="color:#484f58">（无对话）</span>';
    
    row.innerHTML = `
        <span class="num">#${{s.id}}</span>
        <div class="thumb">
            <img src="${{s.ff}}" alt="首"><span class="arrow">›</span><img src="${{s.lf}}" alt="尾">
        </div>
        <div class="meta">
            <div class="times">${{s.start.toFixed(1)}}s → ${{s.end.toFixed(1)}}s <span class="${{durClass}}">(${{s.dur}}s)</span> <span class="type-badge type-${{s.type}}">${{tIcon}} ${{s.type}}</span></div>
            <div class="dialogue-text">${{dlg}}</div>
        </div>
    `;
    shotList.appendChild(row);
}});

// === Build timeline ===
timelineInner.style.height = TIMELINE_HEIGHT + 'px';

// Time axis ticks (every 10s)
const timeAxis = document.getElementById('timeAxis');
for (let t = 0; t <= DURATION; t += 10) {{
    const tick = document.createElement('div');
    tick.className = 'time-tick';
    tick.style.top = (t * PX_PER_SEC) + 'px';
    tick.textContent = t + 's';
    timeAxis.appendChild(tick);
}}

// Shot boundary markers
const markersDiv = document.getElementById('markers');
SHOTS.forEach(s => {{
    const m = document.createElement('div');
    m.className = 'shot-marker';
    m.style.top = (s.start * PX_PER_SEC) + 'px';
    m.style.height = ((s.end - s.start) * PX_PER_SEC) + 'px';
    markersDiv.appendChild(m);
    
    if (s.dur > 2) {{
        const label = document.createElement('div');
        label.className = 'shot-marker-label';
        label.style.top = (s.start * PX_PER_SEC) + 'px';
        label.textContent = '#' + s.id;
        markersDiv.appendChild(label);
    }}
}});

// === Draw waveforms on canvas ===
const tracksDiv = document.getElementById('tracks');
const trackConfigs = [
    {{name:'vocals', label:'💬 对话', cls:'vocals', color:'#58a6ff'}},
    {{name:'drums',  label:'🎵 BGM',  cls:'bgm',    color:'#3fb950'}},
    {{name:'other',  label:'🔊 环境音效', cls:'sfx', color:'#d29922'}}
];

trackConfigs.forEach((cfg, ti) => {{
    const track = document.createElement('div');
    track.className = 'track';
    
    const label = document.createElement('div');
    label.className = 'track-label ' + cfg.cls;
    label.textContent = cfg.label;
    track.appendChild(label);
    
    const canvas = document.createElement('canvas');
    canvas.className = 'track-canvas';
    canvas.id = 'canvas-' + cfg.name;
    track.appendChild(canvas);
    
    // Click overlay
    const overlay = document.createElement('div');
    overlay.className = 'click-overlay';
    overlay.onclick = (e) => {{
        const rect = track.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const t = y / PX_PER_SEC;
        playAt(t);
    }};
    track.appendChild(overlay);
    
    tracksDiv.appendChild(track);
}});

// Draw waveforms
function drawWaveforms() {{
    trackConfigs.forEach(cfg => {{
        const canvas = document.getElementById('canvas-' + cfg.name);
        const w = canvas.offsetWidth;
        const h = 120;
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        
        const data = STEMS[cfg.name];
        const barW = Math.max(1, w / data.length);
        const mid = h / 2;
        
        // Offset each track vertically within timeline
        ctx.fillStyle = cfg.color;
        for (let i = 0; i < data.length; i++) {{
            const x = i * barW;
            const barH = (data[i] / 100) * (h * 0.45);
            ctx.fillRect(x, mid - barH, barW - 0.5, barH * 2);
        }}
    }});
}}

// Wait for layout then draw
setTimeout(drawWaveforms, 100);
window.addEventListener('resize', () => setTimeout(drawWaveforms, 50));

// === Playback control ===
function playAt(t, shotId) {{
    video.currentTime = Math.max(0, Math.min(t, DURATION));
    video.play().catch(() => {{}});
    
    // Find and highlight shot
    let sid = shotId;
    if (!sid) {{
        const found = SHOTS.find(s => t >= s.start && t < s.end);
        sid = found ? found.id : null;
    }}
    if (sid) selectShot(sid);
    
    // Scroll left panel to shot
    if (sid) {{
        const row = document.getElementById('shot-row-' + sid);
        if (row) row.scrollIntoView({{block:'nearest', behavior:'smooth'}});
    }}
}}

function selectShot(id) {{
    document.querySelectorAll('.shot-row').forEach(r => r.classList.remove('active'));
    const row = document.getElementById('shot-row-' + id);
    if (row) row.classList.add('active');
    const s = SHOTS.find(x => x.id === id);
    if (s) {{
        shotInfo.textContent = `#${{s.id}} ${{s.start.toFixed(1)}}s→${{s.end.toFixed(1)}}s (${{s.dur}}s) ${{typeIcons[s.type]||''}} ${{s.type}}`;
    }}
    currentShot = id;
}}

function togglePlay() {{
    if (video.paused) video.play(); else video.pause();
}}

// === Update playhead + auto-stop ===
video.addEventListener('timeupdate', () => {{
    const t = video.currentTime;
    timeDisplay.textContent = `${{t.toFixed(1)}}s / ${{DURATION.toFixed(1)}}s`;
    
    // Move playhead
    playhead.style.top = (t * PX_PER_SEC) + 'px';
    
    // Auto-scroll timeline to playhead
    const containerH = timelineContainer.offsetHeight;
    const playheadPx = t * PX_PER_SEC;
    const scrollTop = timelineContainer.scrollTop;
    if (playheadPx < scrollTop + 30 || playheadPx > scrollTop + containerH - 30) {{
        timelineContainer.scrollTo({{top: playheadPx - containerH / 2, behavior:'smooth'}});
    }}
    
    // Update active shot
    const found = SHOTS.find(s => t >= s.start && t < s.end);
    if (found && found.id !== currentShot) {{
        selectShot(found.id);
        const row = document.getElementById('shot-row-' + found.id);
        if (row) row.scrollIntoView({{block:'nearest', behavior:'smooth'}});
    }}
}});

// === Keyboard nav ===
document.addEventListener('keydown', e => {{
    if (e.key === ' ') {{
        e.preventDefault();
        togglePlay();
    }} else if (e.key === 'ArrowDown') {{
        e.preventDefault();
        const idx = currentShot ? SHOTS.findIndex(s => s.id === currentShot) : -1;
        if (idx < SHOTS.length - 1) playAt(SHOTS[idx+1].start, SHOTS[idx+1].id);
    }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        const idx = currentShot ? SHOTS.findIndex(s => s.id === currentShot) : 0;
        if (idx > 0) playAt(SHOTS[idx-1].start, SHOTS[idx-1].id);
    }}
}});
</script>
</body>
</html>'''

    with open(output_html, 'w') as f:
        f.write(html)
    print(f"Written {len(html):,} bytes to {output_html}")

if __name__ == "__main__":
    main()
