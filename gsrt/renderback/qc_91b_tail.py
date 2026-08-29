#!/usr/bin/env python3
"""shot91b 尾段密集采样: 渲染 90/95/99% vs 条件尾帧 + 原片对应节拍."""
import subprocess, os
from PIL import Image

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
render = f"{BASE}/renders_iter/gsrt_t4_91b_00001_.mp4"
tclip = f"{BASE}/targets/orig_091.mp4"
cond_last = f"{BASE}/frames/91_last_28110.jpg"

def frame_at(v, t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", v,
                    "-frames:v", "1", "-q:v", "3", out], capture_output=True)
    return os.path.exists(out)

# 渲染 3.75s: 90%=3.375 95%=3.56 99%=3.71; 原片 4.116s: 90%=3.70 97%=3.99
picks = [
    ("R90", render, 3.375), ("R95", render, 3.56), ("R99", render, 3.71),
    ("O90", tclip, 3.70), ("O97", tclip, 3.99), ("COND_LAST", cond_last, None),
]
ims = []
for tag, v, t in picks:
    fp = f"{BASE}/qc_tmp_91b_tail_{tag}.jpg"
    if t is None:
        fp = cond_last
    else:
        frame_at(v, t, fp)
    if os.path.exists(fp):
        ims.append(Image.open(fp).convert("RGB").resize((426, 240)))
cv = Image.new("RGB", (426 * 3, 480))
for i, im in enumerate(ims[:6]):
    cv.paste(im, ((i % 3) * 426, (i // 3) * 240))
gp = f"{BASE}/qc_91b_tailgrid.jpg"
cv.save(gp, quality=80)
print("grid:", gp, "| row1: R90 R95 R99 | row2: O90 O97 COND_LAST")
