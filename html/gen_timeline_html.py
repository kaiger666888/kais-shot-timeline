#!/usr/bin/env python3
"""生成时间轴双面板 HTML（音轨波形 + stem 播放 + 自适应/线性双模式）。

该脚本由最终 855 行版本的 xiaojianghu_ep01_timeline.html 反向提取而来，
所有前端特性都对应保留：

  * 线性 vs 自适应双模式（toggleMode + buildShotLayout + getTimeY/getYTime）
  * 自适应模式 syncAdaptiveLayout（DOM 高度回写右面板）
  * 分段 canvas 波形（避开浏览器 ~65535px canvas 高度上限）
  * <audio> 元素 stem 播放（playStem + stopStem + playbackMode 互斥）
  * XHR blob 预加载（保证 stem 即点即播）
  * 音轨视觉分隔（border-left/right + hover/playing）
  * ontimeupdate playhead 跟踪 + 自动滚动
  * body flex 布局（无需 JS 算高度）
  * 缩略图 flex:1 + aspect-ratio:16/9
  * 双面板按比例 / 1:1 滚动同步
"""
import argparse
import json
import os
from pathlib import Path


def build_shots_js(shots, frames_by_id, audio_by_id, transcript_segments=None):
    """合并 shots + frames + audio analysis → 前端 SHOTS 数组。"""
    seg_by_shot = {}
    if transcript_segments:
        for shot in shots:
            seg_by_shot[shot["id"]] = []
        for seg in transcript_segments:
            seg_start = seg.get("start", 0)
            for shot in shots:
                if shot["start_sec"] <= seg_start < shot["end_sec"]:
                    seg_by_shot[shot["id"]].append(
                        {"start": seg_start, "end": seg.get("end", seg_start),
                         "text": seg.get("text", "").strip()})
                    break

    js_shots = []
    for shot in shots:
        fr = frames_by_id.get(shot["id"], {})
        au = audio_by_id.get(shot["id"], {})
        dlg_segs = au.get("dialogue") or seg_by_shot.get(shot["id"], [])
        js_shots.append({
            "id": shot["id"],
            "start": round(shot["start_sec"], 2),
            "end": round(shot["end_sec"], 2),
            "dur": round(shot["duration"], 2),
            "ff": fr.get("first_frame", ""),
            "lf": fr.get("last_frame", ""),
            "type": au.get("dominant_type", "mixed"),
            "dialogue": " ".join(d["text"] for d in dlg_segs) if dlg_segs else "",
        })
    return js_shots


def build_js_stems(stems_dir, duration, bucket_ms=350):
    """读取 stem wav → 计算 ~350ms 桶 RMS（0-100 整数），供 canvas 绘制。

    stems_dir 必须含 vocals.wav / drums.wav / other.wav。
    返回 {"vocals":[int,...], "drums":[...], "other":[...]}
    """
    import numpy as np
    import wave

    def load_mono(path):
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            n_ch = wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if n_ch == 2:
                a = a.reshape(-1, 2).mean(axis=1)
        return a, sr

    out = {}
    for name in ("vocals", "drums", "other"):
        p = os.path.join(stems_dir, f"{name}.wav")
        if not os.path.exists(p):
            print(f"[warn] missing stem {p}, using zero array")
            n = max(1, int(duration * 1000 / bucket_ms))
            out[name] = [0] * n
            continue
        audio, sr = load_mono(p)
        bucket = max(1, int(sr * bucket_ms / 1000))
        n = int(len(audio) / bucket)
        raw_buckets = []
        for i in range(n):
            chunk = audio[i * bucket:(i + 1) * bucket]
            raw_buckets.append(float(np.sqrt(np.mean(chunk ** 2) + 1e-10)))
        mx = max(raw_buckets) if raw_buckets else 1.0
        if mx <= 0:
            mx = 1.0
        out[name] = [int(round(v / mx * 100)) for v in raw_buckets]
        print(f"[gen-timeline-html] stem {name}: {n} buckets (~{bucket_ms}ms)")
    return out


def build_html(shots_js, stems_js, duration, video_src, title,
               stem_basename, n_dialogue=None, n_bgm=None, n_sfx=None,
               n_shots=None, transcript_segments=None):
    """生成完整 HTML。

    stem_basename: stem 文件名前缀，例如 'ep01'。HTML 内 <audio> 会引用
                   {stem_basename}_vocals.wav / {stem_basename}_drums.wav /
                   {stem_basename}_other.wav。
    transcript_segments: 可选 [{start,end,text}, ...]，用于播放器下的实时字幕条，
                         按 audio/video 的 currentTime 精确匹配。
    """
    shots_json = json.dumps(shots_js, ensure_ascii=False)
    stems_json = json.dumps(stems_js)
    transcript_json = json.dumps(transcript_segments or [], ensure_ascii=False)
    n_shots_val = n_shots if n_shots is not None else len(shots_js)

    # 类型统计行（仅在数据存在时显示对应 span）
    stat_spans = ""
    if n_dialogue is not None:
        stat_spans += f'<span>💬 {n_dialogue}对话</span>'
    if n_bgm is not None:
        stat_spans += f'<span>🎵 {n_bgm}BGM</span>'
    if n_sfx is not None:
        stat_spans += f'<span>🔊 {n_sfx}音效</span>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ background:#0d1117; color:#c9d1d9; font-family:-apple-system,'PingFang SC',sans-serif; overflow:hidden; height:100vh; display:flex; flex-direction:column; }}

/* ===== Top: sticky header + player ===== */
.header {{ flex-shrink:0; z-index:200; background:#161b22; border-bottom:1px solid #30363d; }}
.header-top {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; padding:10px 20px 4px; }}
.stats {{ display:flex; gap:12px; font-size:13px; color:#8b949e; }}
.toolbar {{ display:flex; align-items:center; gap:8px; margin-left:auto; }}
.player-section {{ padding:4px 16px 10px; }}
video {{ width:100%; max-height:35vh; border-radius:8px; object-fit:contain; }}
.player-size-btns {{ display:flex; gap:6px; justify-content:center; margin-top:4px; }}
.player-size-btns button {{ background:#21262d; color:#8b949e; border:1px solid #30363d;
    padding:2px 10px; border-radius:4px; cursor:pointer; font-size:11px; }}
.player-size-btns button.active {{ background:#1f6feb; border-color:#1f6feb; color:white; }}

/* ===== Live caption (follows actual playback time) ===== */
.live-caption {{ min-height:22px; padding:6px 14px; margin:6px auto 0; max-width:90%;
    font-size:14px; line-height:1.35; color:#d29922; background:rgba(46,38,10,0.45);
    border-left:3px solid #d29922; border-radius:4px; text-align:center;
    transition:opacity 0.15s; font-weight:500; }}
.live-caption.empty {{ opacity:0.25; color:#6e7681; font-style:italic;
    background:rgba(110,118,129,0.08); border-left-color:#6e7681; }}
.live-caption .seg-time {{ display:block; font-size:10px; color:#8b949e;
    font-family:monospace; margin-top:2px; font-weight:400; }}

/* ===== Below: two-panel layout (body flex, no JS height calc) ===== */
.app {{ display:flex; gap:0; flex:1; min-height:0; }}
.left-panel {{ width:calc(100% - 420px); min-width:300px; overflow-y:auto; border-right:1px solid #30363d; }}
.right-panel {{ width:420px; flex-shrink:0; overflow-y:auto; overflow-x:hidden; position:relative; }}

/* ===== Left: shot rows positioned to match timeline ===== */
.left-panel {{ position:relative; }}
.shot-list-inner {{ position:relative; }}
.shot-list-inner.adaptive .shot-row {{ position:relative !important; top:auto !important; height:auto !important; }}
.shot-list-inner.adaptive .shot-row .body {{ overflow:hidden; }}
.shot-row {{ position:absolute; left:0; right:0; display:flex; align-items:flex-start; gap:6px; padding:0 10px; cursor:pointer; transition:background 0.15s; background:#0d1117; z-index:1; }}
.shot-row:hover {{ background:#161b22; z-index:100; }}
.shot-row.active {{ background:#1a1f35; z-index:100; }}
.shot-row .num {{ width:28px; font-size:12px; color:#58a6ff; font-weight:700; text-align:right; flex-shrink:0; padding-top:2px; }}
.shot-row .body {{ flex:1; min-width:0; }}
.shot-row .thumbs {{ display:flex; gap:2px; align-items:center; }}
.shot-row .thumbs img {{ flex:1; min-width:0; aspect-ratio:16/9; object-fit:cover; border-radius:3px; background:#161b22; }}
.shot-row .thumbs .arrow {{ flex:0 0 auto; color:#484f58; font-size:12px; padding:0 2px; }}
.shot-row .times {{ font-size:10px; color:#8b949e; font-family:monospace; margin-top:1px; }}
.shot-row .dur {{ color:#d29922; }}
.shot-row .type-badge {{ font-size:8px; padding:0 3px; border-radius:2px; margin-left:3px; }}
.shot-row .dlg {{ font-size:11px; color:#c9d1d9; line-height:1.2; margin-top:1px; }}
.type-dialogue {{ background:#1a3a5e; color:#58a6ff; }}
.type-bgm {{ background:#1a3e1a; color:#3fb950; }}
.type-sfx {{ background:#3e351a; color:#d29922; }}
.type-mixed {{ background:#2a2a3e; color:#8b949e; }}

/* ===== Right: vertical timeline ===== */
.timeline-inner {{ position:relative; }}
.time-axis {{ position:absolute; left:0; top:0; width:36px; bottom:0; border-right:1px solid #21262d; z-index:5; }}
.time-tick {{ position:absolute; right:4px; font-size:9px; color:#484f58; font-family:monospace; transform:translateY(-50%); }}
.shot-boundary {{ position:absolute; left:36px; right:0; height:1px; background:#30363d; opacity:0.4; z-index:4; }}
.shot-boundary.major {{ background:#58a6ff; opacity:0.15; height:1px; }}
.shot-blabel {{ position:absolute; left:38px; font-size:8px; color:#484f58; z-index:6; white-space:nowrap; transform:translateY(-50%); }}
.playhead {{ position:absolute; left:36px; right:0; height:0; border-top:2px solid #f85149; z-index:50; pointer-events:none; }}
.playhead::before {{ content:''; position:absolute; left:-5px; top:-5px; width:8px; height:8px; background:#f85149; border-radius:50%; }}
.track {{ position:relative; border-left:2px solid #30363d; border-right:1px solid #21262d; background:rgba(22,27,34,0.4); }}
.track:hover {{ background:rgba(56,139,253,0.08); }}
.track.playing {{ background:rgba(56,139,253,0.12); }}
.track-label {{ position:absolute; left:4px; top:2px; font-size:11px; font-weight:700; z-index:10; text-shadow:0 0 4px #0d1117, 0 0 2px #0d1117; pointer-events:none; }}
.track-label.vocals {{ color:#58a6ff; }}
.track-label.bgm {{ color:#3fb950; }}
.track-label.sfx {{ color:#d29922; }}
.track canvas {{ display:block; }}
.track .click-zone {{ position:absolute; left:0; right:0; top:0; bottom:0; cursor:crosshair; z-index:20; }}
</style>
</head>
<body>

<!-- ===== STICKY HEADER + PLAYER ===== -->
<div class="header">
  <div class="header-top">
    <h1>🎵 {title} ({n_shots_val} shots)</h1>
    <div class="stats">
      <span>⏱ {duration:.1f}s</span>
      {stat_spans}
    </div>
    <div class="toolbar">
      <button onclick="syncScroll()" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;">🔗 同步滚动</button>
      <button id="modeBtn" onclick="toggleMode()" style="background:#21262d;color:#58a6ff;border:1px solid #30363d;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;">📐 线性模式</button>
    </div>
  </div>
  <div class="player-section">
    <video id="player" controls preload="auto">
      <source src="{video_src}" type="video/mp4">
    </video>
    <div id="liveCaption" class="live-caption empty">（待播放）</div>
    <div class="player-size-btns">
      <button onclick="setPlayerSize('25vh')">小</button>
      <button onclick="setPlayerSize('35vh')" class="active">中</button>
      <button onclick="setPlayerSize('50vh')">大</button>
    </div>
  </div>
</div>

<!-- ===== TWO-PANEL LAYOUT ===== -->
<div class="app" id="app">
  <div class="left-panel" id="leftPanel">
    <div class="shot-list-inner" id="shotListInner"></div>
  </div>
  <div class="right-panel" id="rightPanel">
    <div class="timeline-inner" id="timelineInner">
      <div class="time-axis" id="timeAxis"></div>
      <div id="markers"></div>
      <div id="tracks"></div>
      <div class="playhead" id="playhead" style="top:0;"></div>
    </div>
  </div>
</div>

<script>
const SHOTS = {shots_json};
const STEMS = {stems_json};
const TRANSCRIPT_SEGMENTS = {transcript_json};
const DURATION = {duration};
const STEM_BASENAME = {json.dumps(stem_basename)};
const N_PTS = STEMS.vocals.length;
const PX_PER_SEC_LINEAR = 396;
const TRACK_W = 120;

let MODE = 'adaptive';
const MIN_SHOT_PX = 280;

function buildShotLayout() {{
    const layout = [];
    let cumY = 0;
    SHOTS.forEach(s => {{
        const naturalH = s.dur * PX_PER_SEC_LINEAR;
        const h = Math.max(naturalH, MIN_SHOT_PX);
        layout.push({{ id: s.id, start: s.start, end: s.end, dur: s.dur, h: h, yStart: cumY, yEnd: cumY + h }});
        cumY += h;
    }});
    layout.totalH = cumY;
    return layout;
}}

let SHOT_LAYOUT = buildShotLayout();

function getTimeY(t) {{
    if (MODE === 'linear') return t * PX_PER_SEC_LINEAR;
    for (const s of SHOT_LAYOUT) {{
        if (t >= s.start && t <= s.end) {{
            return s.yStart + ((t - s.start) / s.dur) * s.h;
        }}
    }}
    if (t >= DURATION) return SHOT_LAYOUT.totalH;
    return 0;
}}

function getYTime(y) {{
    if (MODE === 'linear') return y / PX_PER_SEC_LINEAR;
    for (const s of SHOT_LAYOUT) {{
        if (y >= s.yStart && y <= s.yEnd) {{
            return s.start + ((y - s.yStart) / s.h) * s.dur;
        }}
    }}
    if (y < 0) return 0;
    return DURATION;
}}

function getTimelineHeight() {{
    if (MODE === 'linear') return DURATION * PX_PER_SEC_LINEAR;
    return SHOT_LAYOUT.totalH;
}}

let TIMELINE_H = getTimelineHeight();

const video = document.getElementById('player');
const playhead = document.getElementById('playhead');
const timelineInner = document.getElementById('timelineInner');
const rightPanel = document.getElementById('rightPanel');
const leftPanel = document.getElementById('leftPanel');
const liveCaption = document.getElementById('liveCaption');
let currentShot = null;
let syncMode = true;

// === 实时字幕：按当前播放时刻精确匹配 transcript segment ===
function updateCaption(t) {{
    if (!TRANSCRIPT_SEGMENTS.length) return;
    // 二分找第一个 end > t 的段；它若 start <= t 即命中
    let lo = 0, hi = TRANSCRIPT_SEGMENTS.length - 1, hit = -1;
    while (lo <= hi) {{
        const mid = (lo + hi) >> 1;
        if (TRANSCRIPT_SEGMENTS[mid].end > t) {{ hit = mid; hi = mid - 1; }}
        else lo = mid + 1;
    }}
    const seg = (hit >= 0 && TRANSCRIPT_SEGMENTS[hit].start <= t) ? TRANSCRIPT_SEGMENTS[hit] : null;
    if (seg) {{
        if (liveCaption.dataset.segStart !== String(seg.start)) {{
            liveCaption.classList.remove('empty');
            liveCaption.dataset.segStart = seg.start;
            liveCaption.innerHTML = seg.text
                + `<span class="seg-time">${{seg.start.toFixed(1)}} → ${{seg.end.toFixed(1)}}s</span>`;
        }}
    }} else {{
        liveCaption.classList.add('empty');
        liveCaption.dataset.segStart = '';
        liveCaption.textContent = '（静音 / 间奏）';
    }}
}}

function adjustAppHeight() {{
    const header = document.querySelector('.header');
    const h = window.innerHeight - header.offsetHeight;
    document.getElementById('app').style.height = h + 'px';
}}
adjustAppHeight();
window.addEventListener('resize', () => {{ adjustAppHeight(); if (MODE === 'adaptive') syncAdaptiveLayout(); }});
document.getElementById('player').addEventListener('loadedmetadata', () => {{
    adjustAppHeight();
    if (MODE === 'adaptive') syncAdaptiveLayout();
}});

const typeColors = {{dialogue:'#58a6ff', bgm:'#3fb950', sfx:'#d29922', mixed:'#8b949e'}};
const typeIcons = {{dialogue:'💬', bgm:'🎵', sfx:'🔊', mixed:'🔀'}};
const shotListInner = document.getElementById('shotListInner');
shotListInner.style.height = TIMELINE_H + 'px';

SHOTS.forEach(s => {{
    const row = document.createElement('div');
    row.className = 'shot-row';
    row.id = 'srow-' + s.id;
    row.style.top = getTimeY(s.start) + 'px';
    row.style.height = (getTimeY(s.end) - getTimeY(s.start)) + 'px';
    row.style.zIndex = s.id;
    row.onclick = () => playAt(s.start, s.id);
    const durCls = s.dur < 1.5 ? 'dur' : '';
    const dlg = s.dialogue ? s.dialogue.substring(0, 200) : '<span style="color:#484f58">（无对话）</span>';
    row.innerHTML = `<span class="num">${{s.id}}</span>`
        + `<div class="body">`
        + `<div class="thumbs"><img src="${{s.ff}}"><span class="arrow">→</span><img src="${{s.lf}}"></div>`
        + `<div class="times">${{s.start.toFixed(1)}}→${{s.end.toFixed(1)}} <span class="${{durCls}}">(${{s.dur}}s)</span>`
        + `<span class="type-badge type-${{s.type}}">${{typeIcons[s.type]||''}} ${{s.type}}</span></div>`
        + `<div class="dlg">${{dlg}}</div>`
        + `</div>`;
    shotListInner.appendChild(row);
}});

timelineInner.style.height = TIMELINE_H + 'px';
const timeAxis = document.getElementById('timeAxis');
timeAxis.style.height = TIMELINE_H + 'px';
for (let t = 0; t <= DURATION; t += 10) {{
    const tick = document.createElement('div');
    tick.className = 'time-tick';
    tick.style.top = getTimeY(t) + 'px';
    tick.textContent = t + 's';
    timeAxis.appendChild(tick);
}}

const markersDiv = document.getElementById('markers');
SHOTS.forEach(s => {{
    const y = getTimeY(s.start);
    const m = document.createElement('div');
    m.className = 'shot-boundary' + (s.dur > 2 ? ' major' : '');
    m.style.top = y + 'px';
    markersDiv.appendChild(m);
    if (s.dur >= 1.5) {{
        const lbl = document.createElement('div');
        lbl.className = 'shot-blabel';
        lbl.style.top = y + 'px';
        lbl.textContent = '#' + s.id;
        markersDiv.appendChild(lbl);
    }}
}});

const tracksDiv = document.getElementById('tracks');
const trackCfg = [
    {{key:'vocals', label:'💬 对话',     cls:'vocals', color:'#58a6ff', x0: 36}},
    {{key:'drums',  label:'🎵 BGM',      cls:'bgm',    color:'#3fb950', x0: 36 + TRACK_W}},
    {{key:'other',  label:'🔊 环境音效',  cls:'sfx',    color:'#d29922', x0: 36 + TRACK_W*2}}
];

const CANVAS_MAX_H = 60000; // browsers cap canvas height near 65535px

function buildTracks() {{
    const tracksDiv = document.getElementById('tracks');
    tracksDiv.innerHTML = '';
    trackCfg.forEach(cfg => {{
        const track = document.createElement('div');
        track.className = 'track';
        track.style.cssText = `position:absolute; left:${{cfg.x0}}px; top:0; width:${{TRACK_W}}px; height:${{TIMELINE_H}}px;`;

        const lbl = document.createElement('div');
        lbl.className = 'track-label ' + cfg.cls;
        lbl.style.cssText = 'position:absolute; left:2px; top:2px; font-size:10px; font-weight:600; text-shadow:0 0 4px #0d1117; z-index:10;';
        lbl.textContent = cfg.label;
        track.appendChild(lbl);

        const nSegs = Math.ceil(TIMELINE_H / CANVAS_MAX_H);
        track.dataset.segments = nSegs;
        for (let s = 0; s < nSegs; s++) {{
            const segTop = s * CANVAS_MAX_H;
            const segH = Math.min(CANVAS_MAX_H, TIMELINE_H - segTop);
            const canvas = document.createElement('canvas');
            canvas.id = `cv-${{cfg.key}}-${{s}}`;
            canvas.style.cssText = `position:absolute; left:0; top:${{segTop}}px; width:${{TRACK_W}}px; height:${{segH}}px;`;
            canvas.width = TRACK_W;
            canvas.height = Math.floor(segH);
            track.appendChild(canvas);
        }}

        const clickZone = document.createElement('div');
        clickZone.className = 'click-zone';
        clickZone.style.cssText = 'position:absolute; left:0; top:0; right:0; bottom:0; cursor:crosshair; z-index:20;';
        clickZone.onclick = (e) => {{
            const rect = clickZone.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const t = getYTime(y);
            playStem(cfg.key, t);
        }};
        track.appendChild(clickZone);

        tracksDiv.appendChild(track);
    }});
}}

function drawWaveforms() {{
    trackCfg.forEach(cfg => {{
        const data = STEMS[cfg.key];
        const w = TRACK_W;
        const mid = w / 2;
        const dt = DURATION / N_PTS;
        const nSegs = Math.ceil(TIMELINE_H / CANVAS_MAX_H);

        for (let s = 0; s < nSegs; s++) {{
            const canvas = document.getElementById(`cv-${{cfg.key}}-${{s}}`);
            if (!canvas) continue;
            const segTop = s * CANVAS_MAX_H;
            const segH = Math.min(CANVAS_MAX_H, TIMELINE_H - segTop);
            canvas.width = w;
            canvas.height = Math.floor(segH);
            canvas.style.height = segH + 'px';
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, w, segH);
            ctx.fillStyle = cfg.color;
            for (let i = 0; i < data.length; i++) {{
                const t = i * dt;
                const yGlobal = getTimeY(t);
                const yInSeg = yGlobal - segTop;
                if (yGlobal + 1 < segTop || yGlobal > segTop + segH) continue;
                const barH = Math.max(0.5, (getTimeY(t + dt) - getTimeY(t)) || 1);
                const barW = (data[i] / 100) * (w * 0.45);
                ctx.fillRect(mid - barW, yInSeg, barW * 2, barH);
            }}
        }}
    }});
}}
buildTracks();
setTimeout(drawWaveforms, 200);
window.addEventListener('resize', () => setTimeout(drawWaveforms, 100));

if (MODE === 'adaptive') {{
    const sli = document.getElementById('shotListInner');
    sli.classList.add('adaptive');
    sli.style.height = 'auto';
    document.querySelectorAll('.shot-row').forEach(row => {{
        row.style.top = '';
        row.style.height = '';
    }});
    const btn = document.getElementById('modeBtn');
    btn.textContent = '📐 自适应模式';
    btn.style.color = '#56d364';
    requestAnimationFrame(() => {{
        requestAnimationFrame(() => {{
            syncAdaptiveLayout();
        }});
    }});
}}

let stopAtTime = null;
let activeStemKey = null;
let playbackMode = 'video';

// === Stem playback via <audio> elements ===
const stemAudioElements = {{}};
let stemStopTimer = null;

trackCfg.forEach(cfg => {{
    const a = document.createElement('audio');
    a.src = `${{STEM_BASENAME}}_${{cfg.key}}.wav`;
    a.preload = 'auto';
    a.style.display = 'none';
    document.body.appendChild(a);
    stemAudioElements[cfg.key] = a;
}});

// XHR blob 预加载：preload='auto' 只是 hint，用 XHR 强制完整下载 + 缓存
const stemReady = {{}};
trackCfg.forEach(cfg => {{
    const key = cfg.key;
    stemReady[key] = false;
    const xhr = new XMLHttpRequest();
    xhr.open('GET', `${{STEM_BASENAME}}_${{key}}.wav`, true);
    xhr.responseType = 'blob';
    xhr.onload = () => {{
        if (xhr.status === 200) {{
            const objUrl = URL.createObjectURL(xhr.response);
            stemAudioElements[key].src = objUrl;
            stemReady[key] = true;
            console.log(`Stem cached: ${{key}}`);
        }}
    }};
    xhr.send();
}});

function stopStem() {{
    if (stemStopTimer) {{
        clearTimeout(stemStopTimer);
        stemStopTimer = null;
    }}
    Object.values(stemAudioElements).forEach(a => {{
        a.pause();
        a.ontimeupdate = null;
    }});
    // Stem 停止时，把同步静音播放的视频也一并暂停
    if (!video.paused) video.pause();
    activeStemKey = null;
}}

function stopAll() {{
    stopStem();
    clearTrackHighlight();
    const v = document.getElementById('player');
    if (v && !v.paused) v.pause();
    stopAtTime = null;
    playbackMode = 'idle';
}}

function playStem(key, t) {{
    t = Math.max(0, Math.min(t, DURATION - 0.1));
    const v = document.getElementById('player');

    if (stemStopTimer) {{
        clearTimeout(stemStopTimer);
        stemStopTimer = null;
    }}
    Object.entries(stemAudioElements).forEach(([k, a]) => {{
        if (k !== key) a.pause();
    }});

    playbackMode = 'stem';
    activeStemKey = key;

    // 视频静音 + 同步播放：只有目标 stem 出声，画面跟着 stem 推进。
    // 不做 drift 修正 — 修正会在视频偶发卡顿时变成 seek 循环（"反复跳"）。
    v.muted = true;
    try {{ v.currentTime = t; }} catch (e) {{}}
    v.play().catch(() => {{}});

    const audio = stemAudioElements[key];
    if (!audio) return;

    try {{ audio.currentTime = t; }} catch(e) {{ /* may not be seekable yet */ }}
    audio.volume = 1.0;

    const playPromise = audio.play();
    if (playPromise) {{
        playPromise.then(() => {{
            console.log(`Playing stem: ${{key}} from ${{t.toFixed(1)}}s`);
        }}).catch(e => {{
            console.error(`Stem play failed: ${{key}}:`, e.message);
            playbackMode = 'video';
            activeStemKey = null;
            playAt(t);
        }});
    }}

    highlightTrack(key);

    audio.ontimeupdate = () => {{
        if (playbackMode !== 'stem' || activeStemKey !== key) return;
        const ct = audio.currentTime;
        playhead.style.top = getTimeY(ct) + 'px';
        updateCaption(ct);
        const found = SHOTS.find(s => ct >= s.start && ct < s.end);
        if (found && found.id !== currentShot) selectShot(found.id);
    }};

    audio.onended = () => {{
        if (playbackMode === 'stem' && activeStemKey === key) {{
            stopStem();
            clearTrackHighlight();
            playbackMode = 'idle';
        }}
    }};

    playhead.style.top = getTimeY(t) + 'px';
    updateCaption(t);
    scrollTimelineTo(t);
    const found = SHOTS.find(s => t >= s.start && t < s.end);
    if (found) selectShot(found.id);
}}

function highlightTrack(key) {{
    const clsMap = {{vocals: 'vocals', drums: 'bgm', other: 'sfx'}};
    const targetCls = clsMap[key];
    document.querySelectorAll('.track').forEach(tr => {{
        const lbl = tr.querySelector('.track-label');
        if (lbl && lbl.classList.contains(targetCls)) {{
            tr.classList.add('playing');
            tr.style.opacity = '1';
            tr.style.filter = 'brightness(1.3) drop-shadow(0 0 6px currentColor)';
        }} else {{
            tr.classList.remove('playing');
            tr.style.opacity = '0.25';
            tr.style.filter = 'grayscale(0.5)';
        }}
    }});
}}

function clearTrackHighlight() {{
    document.querySelectorAll('.track').forEach(tr => {{
        tr.classList.remove('playing');
        tr.style.opacity = '';
        tr.style.filter = '';
    }});
}}

document.getElementById('timeAxis').style.cursor = 'crosshair';
document.getElementById('timeAxis').addEventListener('click', (e) => {{
    const rect = e.currentTarget.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const t = getYTime(y);
    stopStem();
    clearTrackHighlight();
    playbackMode = 'video';
    playAt(t);
}});

function playAt(t, shotId) {{
    t = Math.max(0, Math.min(t, DURATION - 0.1));
    stopStem();
    clearTrackHighlight();
    playbackMode = 'video';
    // 切回视频模式：解除静音，恢复视频自带音频
    video.muted = false;
    let sid = shotId;
    if (!sid) {{
        const found = SHOTS.find(s => t >= s.start && t < s.end);
        sid = found ? found.id : null;
    }}
    if (sid) {{
        const s = SHOTS.find(x => x.id === sid);
        if (s) {{
            stopAtTime = s.end - 0.05;
            video.currentTime = s.start;
        }}
    }} else {{
        stopAtTime = null;
        video.currentTime = t;
    }}
    video.play().catch(() => {{}});
    if (sid) selectShot(sid);
    scrollTimelineTo(video.currentTime);
}}

function selectShot(id) {{
    document.querySelectorAll('.shot-row').forEach(r => r.classList.remove('active'));
    const row = document.getElementById('srow-' + id);
    if (row) row.classList.add('active');
    currentShot = id;
}}

function scrollTimelineTo(t) {{
    if (!syncMode) return;
    const target = getTimeY(t) - rightPanel.offsetHeight / 2;
    rightPanel.scrollTo({{top: Math.max(0, target), behavior:'smooth'}});
}}

function setPlayerSize(s) {{
    document.getElementById('player').style.maxHeight = s;
    document.querySelectorAll('.player-size-btns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    adjustAppHeight();
}}

function syncScroll() {{
    syncMode = !syncMode;
    event.target.style.opacity = syncMode ? '1' : '0.4';
    if (syncMode && currentShot) {{
        const s = SHOTS.find(x => x.id === currentShot);
        if (s) scrollTimelineTo(s.start);
    }}
}}

// === Adaptive layout sync: measure actual left-panel row heights → update right panel ===
function syncAdaptiveLayout() {{
    if (MODE !== 'adaptive') return;
    let cumY = 0;
    SHOTS.forEach(s => {{
        const row = document.getElementById('srow-' + s.id);
        let measuredH = MIN_SHOT_PX;
        if (row) {{
            measuredH = Math.ceil(row.getBoundingClientRect().height);
            if (measuredH < 10) measuredH = MIN_SHOT_PX;
        }}
        const entry = SHOT_LAYOUT.find(x => x.id === s.id);
        if (entry) {{
            entry.h = measuredH;
            entry.yStart = cumY;
            entry.yEnd = cumY + measuredH;
        }}
        cumY += measuredH;
    }});
    SHOT_LAYOUT.totalH = cumY;
    TIMELINE_H = cumY;

    const timelineInner = document.getElementById('timelineInner');
    timelineInner.style.height = TIMELINE_H + 'px';
    document.getElementById('timeAxis').style.height = TIMELINE_H + 'px';
    document.getElementById('markers').style.height = TIMELINE_H + 'px';

    document.querySelectorAll('.time-tick').forEach(tick => {{
        const t = parseFloat(tick.textContent);
        if (!isNaN(t)) tick.style.top = getTimeY(t) + 'px';
    }});

    const allMarkers = document.querySelectorAll('.shot-boundary');
    const allLabels = document.querySelectorAll('.shot-blabel');
    SHOTS.forEach((s, i) => {{
        const y = getTimeY(s.start);
        if (allMarkers[i]) allMarkers[i].style.top = y + 'px';
        if (allLabels[i]) allLabels[i].style.top = y + 'px';
    }});

    buildTracks();
    drawWaveforms();

    if (!video.paused) {{
        playhead.style.top = getTimeY(video.currentTime) + 'px';
    }}
}}

function toggleMode() {{
    MODE = (MODE === 'linear') ? 'adaptive' : 'linear';
    TIMELINE_H = getTimelineHeight();
    const shotListInner = document.getElementById('shotListInner');
    if (MODE === 'adaptive') {{
        shotListInner.classList.add('adaptive');
    }} else {{
        shotListInner.classList.remove('adaptive');
    }}
    const btn = document.getElementById('modeBtn');
    if (MODE === 'adaptive') {{
        btn.textContent = '📐 自适应模式';
        btn.style.color = '#56d364';
    }} else {{
        btn.textContent = '📐 线性模式';
        btn.style.color = '#58a6ff';
    }}
    rebuildAll();
    if (MODE === 'adaptive') {{
        requestAnimationFrame(() => {{
            requestAnimationFrame(() => {{
                syncAdaptiveLayout();
            }});
        }});
    }}
}}

function rebuildAll() {{
    const shotListInner = document.getElementById('shotListInner');
    shotListInner.innerHTML = '';
    shotListInner.style.height = (MODE === 'adaptive') ? 'auto' : TIMELINE_H + 'px';

    SHOTS.forEach(s => {{
        const row = document.createElement('div');
        row.className = 'shot-row';
        row.id = 'srow-' + s.id;
        if (MODE === 'linear') {{
            row.style.top = getTimeY(s.start) + 'px';
            row.style.height = (getTimeY(s.end) - getTimeY(s.start)) + 'px';
        }} else {{
            row.style.top = '';
            row.style.height = '';
        }}
        row.style.zIndex = s.id;

        const dlg = s.dialogue ? s.dialogue.substring(0, 200) : '（无对话）';
        const typeIcons = {{dialogue:'💬', bgm:'🎵', sfx:'🔊', mixed:'🎛️', silence:'🔇'}};
        const durCls = s.dur < 1 ? 'dur' : '';
        row.innerHTML = `<span class="num">${{s.id}}</span>`
            + `<div class="body">`
            + `<div class="thumbs"><img src="${{s.ff}}"><span class="arrow">→</span><img src="${{s.lf}}"></div>`
            + `<div class="times">${{s.start.toFixed(1)}}→${{s.end.toFixed(1)}} <span class="${{durCls}}">(${{s.dur}}s)</span>`
            + `<span class="type-badge type-${{s.type}}">${{typeIcons[s.type]||''}} ${{s.type}}</span></div>`
            + `<div class="dlg">${{dlg}}</div>`
            + `</div>`;

        row.onclick = () => playAt(s.start, s.id);
        row.onmouseenter = () => {{ row.style.zIndex = 9999; }};
        row.onmouseleave = () => {{ row.style.zIndex = s.id; }};
        shotListInner.appendChild(row);
    }});

    const timelineInner = document.getElementById('timelineInner');
    timelineInner.style.height = TIMELINE_H + 'px';

    const timeAxis = document.getElementById('timeAxis');
    timeAxis.innerHTML = '';
    timeAxis.style.height = TIMELINE_H + 'px';
    for (let t = 0; t <= DURATION; t += 10) {{
        const tick = document.createElement('div');
        tick.className = 'time-tick';
        tick.style.top = getTimeY(t) + 'px';
        tick.textContent = t + 's';
        timeAxis.appendChild(tick);
    }}

    const markersDiv = document.getElementById('markers');
    markersDiv.innerHTML = '';
    markersDiv.style.height = TIMELINE_H + 'px';
    SHOTS.forEach(s => {{
        const y = getTimeY(s.start);
        const m = document.createElement('div');
        m.className = 'shot-boundary' + (s.dur > 2 ? ' major' : '');
        m.style.top = y + 'px';
        markersDiv.appendChild(m);
        if (s.dur >= 1.5) {{
            const lbl = document.createElement('div');
            lbl.className = 'shot-blabel';
            lbl.style.top = y + 'px';
            lbl.textContent = '#' + s.id;
            markersDiv.appendChild(lbl);
        }}
    }});

    buildTracks();
    drawWaveforms();

    if (!video.paused) {{
        playhead.style.top = getTimeY(video.currentTime) + 'px';
    }}
}}

// === timeupdate playhead tracking + auto-stop ===
video.addEventListener('timeupdate', () => {{
    if (playbackMode !== 'video') return;
    const t = video.currentTime;
    if (stopAtTime !== null && t >= stopAtTime) {{
        video.pause();
        stopAtTime = null;
    }}
    playhead.style.top = getTimeY(t) + 'px';
    updateCaption(t);
    scrollTimelineTo(t);
    const found = SHOTS.find(s => t >= s.start && t < s.end);
    if (found && found.id !== currentShot) {{
        selectShot(found.id);
    }}
}});

document.addEventListener('keydown', e => {{
    if (e.key === ' ') {{
        e.preventDefault();
        if (playbackMode === 'stem' && activeStemKey) {{
            stopStem();
            clearTrackHighlight();
            playbackMode = 'idle';
        }} else if (video.paused) {{
            playbackMode = 'video';
            video.play();
        }} else {{
            video.pause();
        }}
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

// === Dual-panel scroll sync (proportional in adaptive, 1:1 in linear) ===
let scrollTimer = null;
let syncingScroll = false;

function syncBothPanels(source) {{
    if (syncingScroll) return;
    syncingScroll = true;
    if (MODE === 'adaptive') {{
        const srcMax = source.scrollHeight - source.clientHeight;
        const dstMax = (source === leftPanel ? rightPanel : leftPanel).scrollHeight - (source === leftPanel ? rightPanel : leftPanel).clientHeight;
        if (srcMax > 0 && dstMax > 0) {{
            const ratio = source.scrollTop / srcMax;
            const target = Math.round(ratio * dstMax);
            (source === leftPanel ? rightPanel : leftPanel).scrollTop = target;
        }}
    }} else {{
        const scrollTop = source.scrollTop;
        if (source === leftPanel) {{
            rightPanel.scrollTop = scrollTop;
        }} else {{
            leftPanel.scrollTop = scrollTop;
        }}
    }}
    syncingScroll = false;
}}

leftPanel.addEventListener('scroll', () => syncBothPanels(leftPanel));
rightPanel.addEventListener('scroll', () => syncBothPanels(rightPanel));
</script>
</body>
</html>'''
    return html


def extract_frames_if_needed(shots, video_path, frames_json):
    """如果 frames_json 不存在或不含某分镜的帧，则从视频抽取首尾帧。"""
    import base64
    import subprocess
    import tempfile

    if frames_json and os.path.exists(frames_json):
        with open(frames_json) as f:
            frames_data = json.load(f)
    else:
        frames_data = []

    frames_by_id = {f["id"]: f for f in frames_data}
    if not video_path or not os.path.exists(video_path):
        return frames_by_id

    print(f"[gen-timeline-html] extracting first/last frames from {video_path}")
    changed = False
    for i, shot in enumerate(shots):
        sid = shot["id"]
        if sid in frames_by_id and frames_by_id[sid].get("first_frame"):
            continue
        ff_ts = shot["start_sec"]
        lf_ts = max(shot["end_sec"] - 0.05, shot["start_sec"])

        def grab(ts):
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                p = tmp.name
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", "-vf", "scale=480:-1",
                 p, "-loglevel", "error"],
                capture_output=True, timeout=10)
            if os.path.exists(p) and os.path.getsize(p) > 100:
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                os.unlink(p)
                return f"data:image/jpeg;base64,{b64}"
            if os.path.exists(p):
                os.unlink(p)
            return ""

        frames_by_id[sid] = {
            "id": sid,
            "first_frame": grab(ff_ts),
            "last_frame": grab(lf_ts),
        }
        changed = True
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(shots)}")

    if changed and frames_json:
        with open(frames_json, "w") as f:
            json.dump(list(frames_by_id.values()), f, indent=2)
        print(f"[gen-timeline-html] frames cached → {frames_json}")
    return frames_by_id


def main():
    ap = argparse.ArgumentParser(description="时间轴双面板 HTML 生成器（含 stem 播放）")
    ap.add_argument("--shots", required=True, help="分镜 JSON")
    ap.add_argument("--audio-json", default=None,
                    help="audio/separate_stems.py 输出的 per-shot 分析 JSON")
    ap.add_argument("--frames", default=None,
                    help="首尾帧 JSON（[{id, first_frame, last_frame}]）；"
                         "若缺省，将从 --video 抽帧")
    ap.add_argument("--transcript", default=None,
                    help="audio/transcribe.py 输出的转录 JSON（用于 dialogue 文本）")
    ap.add_argument("--stems-dir", default=None,
                    help="Demucs stem 目录（vocals/drums/other.wav）；"
                         "若缺省，--js-stems 必须提供")
    ap.add_argument("--js-stems", default=None,
                    help="预先计算好的 stem 波形 JSON（{vocals/drums/other: [...]}）")
    ap.add_argument("--output", required=True, help="输出 HTML 路径")
    ap.add_argument("--video", default=None,
                    help="原视频路径（用于抽帧 / 默认 video-src basename）")
    ap.add_argument("--video-src", default=None,
                    help="HTML 内嵌 <video> 引用源；默认 --video 的 basename")
    ap.add_argument("--stem-basename", default=None,
                    help="<audio> 元素引用的 stem 文件前缀 "
                         "(默认 <video-basename>)")
    ap.add_argument("--title", default=None,
                    help="页面标题（默认 '音轨时间轴 - <video basename>'）")
    args = ap.parse_args()

    with open(args.shots) as f:
        shots = json.load(f)
    audio_data = {"shots": []}
    if args.audio_json and os.path.exists(args.audio_json):
        with open(args.audio_json) as f:
            audio_data = json.load(f)
    audio_by_id = {s["shot_id"]: s for s in audio_data.get("shots", [])}

    transcript_segments = []
    if args.transcript and os.path.exists(args.transcript):
        with open(args.transcript) as f:
            t = json.load(f)
        transcript_segments = t.get("segments", [])

    frames_by_id = extract_frames_if_needed(shots, args.video, args.frames)
    shots_js = build_shots_js(shots, frames_by_id, audio_by_id, transcript_segments)

    duration = shots[-1]["end_sec"] if shots else 0.0

    if args.js_stems and os.path.exists(args.js_stems):
        with open(args.js_stems) as f:
            stems_js = json.load(f)
    elif args.stems_dir and os.path.isdir(args.stems_dir):
        stems_js = build_js_stems(args.stems_dir, duration)
    else:
        n = max(1, int(duration * 1000 / 350))
        stems_js = {k: [0] * n for k in ("vocals", "drums", "other")}
        print("[warn] no stems provided, timeline will show empty tracks")

    video_src = args.video_src or (os.path.basename(args.video) if args.video else "video.mp4")
    title = args.title or f"音轨时间轴 - {os.path.basename(args.video) if args.video else 'video'}"
    stem_basename = args.stem_basename or (
        Path(args.video).stem if args.video else "audio")

    type_dist = audio_data.get("type_distribution", {})

    html = build_html(
        shots_js, stems_js, duration, video_src, title,
        stem_basename,
        n_dialogue=type_dist.get("dialogue"),
        n_bgm=type_dist.get("bgm"),
        n_sfx=type_dist.get("sfx"),
        n_shots=len(shots),
        transcript_segments=transcript_segments,
    )
    with open(args.output, "w") as f:
        f.write(html)
    print(f"[gen-timeline-html] wrote {len(html):,} bytes → {args.output}")


if __name__ == "__main__":
    main()
