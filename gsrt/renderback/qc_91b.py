#!/usr/bin/env python3
"""shot91b QC — 与 qc_t4_tail.py 同判据: 256x144 灰度 MAD 像素锚定 + 中帧节拍网格."""
import json, subprocess, os
import numpy as np
from PIL import Image

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
m = [x for x in json.load(open(f"{BASE}/manifest_v8.json")) if x["shot_id"] == 91][0]
render = f"{BASE}/renders_iter/gsrt_t4_91b_00001_.mp4"

def gray(p):
    return np.asarray(Image.open(p).convert("L").resize((256, 144)), dtype=float)

def mad(a, b):
    return float(np.abs(a - b).mean())

def frame_at(v, t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", v,
                    "-frames:v", "1", "-q:v", "3", out], capture_output=True)
    return os.path.exists(out)

p = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                    "-of", "csv=p=0", render], capture_output=True, text=True)
dur = float(p.stdout.strip())
f0, f1 = f"{BASE}/qc_tmp_91b_r0.jpg", f"{BASE}/qc_tmp_91b_r1.jpg"
frame_at(render, 0.05, f0)
frame_at(render, dur - 0.12, f1)
d_first = mad(gray(f0), gray(m["first_frame"]))
d_last = mad(gray(f1), gray(m["last_frame"]))
verdict = ("ANCHORED" if max(d_first, d_last) < 10 else
           "LIGHT_DRIFT" if max(d_first, d_last) < 20 else "NOT_PINNED")
print(f"render_dur={dur:.2f}s d_first={d_first:.1f} d_last={d_last:.1f} -> {verdict}")

grids = []
for i, frac in enumerate([0.25, 0.5, 0.75]):
    fp = f"{BASE}/qc_tmp_91b_m{i}.jpg"
    frame_at(render, dur * frac, fp)
    grids.append(fp)
tclip = m["target_clip"]
tp = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", tclip], capture_output=True, text=True)
t_dur = float(tp.stdout.strip())
tgrids = []
for i, frac in enumerate([0.5, 0.85, 0.97]):
    fp = f"{BASE}/qc_tmp_91b_t{i}.jpg"
    frame_at(tclip, t_dur * frac, fp)
    tgrids.append(fp)
ims = [Image.open(x).convert("RGB").resize((426, 240)) for x in grids + tgrids if os.path.exists(x)]
cv = Image.new("RGB", (426 * 3, 480))
for i, im in enumerate(ims[:6]):
    cv.paste(im, ((i % 3) * 426, (i // 3) * 240))
gp = f"{BASE}/qc_91b_midbeats.jpg"
cv.save(gp, quality=80)
print("grid:", gp)
