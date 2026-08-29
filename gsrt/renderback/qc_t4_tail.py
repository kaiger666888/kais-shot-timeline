#!/usr/bin/env python3
"""T4 尾段补测 QC — 像素锚定判据 (256×144 灰度 mean-abs-diff) + 帧计数.
判据 (gsrt 既有协议): 渲染首帧 vs 条件首帧 <10=锚定, <20=轻漂移, >25=没钉住; 同法尾帧.
条件帧 vs 原片对应时刻锚位差参考 ~2-5 (提帧协议容差内).
"""
import json, subprocess, os, sys
import numpy as np
from PIL import Image

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
manifest = json.load(open(f"{BASE}/manifest_v8.json"))
results = json.load(open(f"{BASE}/t4_tail_results.json"))

def gray(path):
    return np.asarray(Image.open(path).convert("L").resize((256, 144)), dtype=float)

def mad(a, b):
    return float(np.abs(a - b).mean())

def frame_at(video, t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video,
                    "-frames:v", "1", "-q:v", "3", out], capture_output=True)
    return os.path.exists(out)

report = []
for m in manifest:
    sid = m["shot_id"]
    render = results.get(str(sid))
    row = {"shot": sid, "render": render}
    if not render or not os.path.exists(render):
        row["verdict"] = "NO_RENDER"
        report.append(row)
        continue
    # 渲染视频时长与帧数
    p = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", render], capture_output=True, text=True)
    try:
        row["render_duration"] = round(float(p.stdout.strip()), 2)
    except Exception:
        row["render_duration"] = None
    # 抽渲染首尾帧
    tmp = f"{BASE}/qc_tmp_{sid}"
    f0, f1 = f"{tmp}_r0.jpg", f"{tmp}_r1.jpg"
    frame_at(render, 0.05, f0)
    p = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", render], capture_output=True, text=True)
    dur = float(p.stdout.strip() or 0) or 1
    frame_at(render, max(0, dur - 0.12), f1)
    # 像素锚定
    d_first = mad(gray(f0), gray(m["first_frame"]))
    d_last = mad(gray(f1), gray(m["last_frame"]))
    row["d_first"] = round(d_first, 1)
    row["d_last"] = round(d_last, 1)
    row["verdict"] = ("ANCHORED" if max(d_first, d_last) < 10 else
                      "LIGHT_DRIFT" if max(d_first, d_last) < 20 else
                      "NOT_PINNED")
    # 中帧节拍网格供 vision 判 (25/50/75%)
    grids = []
    for i, frac in enumerate([0.25, 0.5, 0.75]):
        fp = f"{tmp}_m{i}.jpg"
        frame_at(render, dur * frac, fp)
        grids.append(fp)
    # 拼渲染3中帧 + 目标3中帧
    tclip = m["target_clip"]
    t_dur_p = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                              "-of", "csv=p=0", tclip], capture_output=True, text=True)
    try:
        t_dur = float(t_dur_p.stdout.strip())
        tgrids = []
        for i, frac in enumerate([0.25, 0.5, 0.75]):
            fp = f"{tmp}_t{i}.jpg"
            frame_at(tclip, t_dur * frac, fp)
            tgrids.append(fp)
        ims = [Image.open(x).convert("RGB").resize((426, 240)) for x in grids + tgrids if os.path.exists(x)]
        cv = Image.new("RGB", (426 * 3, 480))
        for i, im in enumerate(ims[:6]):
            cv.paste(im, ((i % 3) * 426, (i // 3) * 240))
        gp = f"{BASE}/qc_{sid}_midbeats.jpg"
        cv.save(gp, quality=80)
        row["midbeat_grid"] = gp
    except Exception:
        pass
    report.append(row)

json.dump(report, open(f"{BASE}/t4_tail_qc.json", "w"), ensure_ascii=False, indent=1)
for r in report:
    print(f"shot{r['shot']}: {r['verdict']} d_first={r.get('d_first')} d_last={r.get('d_last')} dur={r.get('render_duration')} grid={r.get('midbeat_grid','-')}")
