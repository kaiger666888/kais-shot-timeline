#!/usr/bin/env python3
"""P1a 全镜批量锚评分 (ITERATION.md §5-P1a).

预筛语义: frames.json(检测器声称锚帧) vs h264.mp4(物理真相@shot-list时间窗) 的 dHash 海明距离。
- d<10 ANCHORED / 10-15 LIGHT / >15 RED(送 vision/人工)
- 附带: 自锚距(first↔last, 运动量代理) + 时长表 → 后续渲染优先级参考
复用 score_iter.py 的 dHash 判据口径。不改机械层算法——纯数据级审计 (P0b 先例)。
"""
import json, subprocess, os, base64, sys, tempfile

BASE = "/data/workspace/kais-shot-timeline"
EP = f"{BASE}/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
RB = f"{BASE}/gsrt/renderback"
OUT = f"{RB}/p1a_anchor_scan"
FILM = f"{EP}/h264.mp4"
os.makedirs(OUT, exist_ok=True)
os.makedirs(f"{OUT}/frames_full", exist_ok=True)

sys.path.insert(0, RB)
from score_iter import phash, hamming  # 同判据口径

from PIL import Image
import io

shot_list = json.load(open(f"{EP}/p09_shot-list.json"))["shot_list"]
frames = json.load(open(f"{EP}/frames.json"))
fmap = {f["id"]: f for f in frames}

# 1) 导出 frames.json → jpg (缓存)
FF = f"{OUT}/frames_full"
exported = 0
for f in frames:
    for side in ("first", "last"):
        p = f"{FF}/{f['id']:03d}_{side}.jpg"
        if not os.path.exists(p):
            open(p, "wb").write(base64.b64decode(f[f"{side}_frame"]))
            exported += 1
print(f"frames_full exported: {exported} new / {93*2-exported} cached")

def film_frame(t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", FILM,
                    "-frames:v", "1", "-q:v", "3", out], capture_output=True)
    return os.path.exists(out)

# 2) 全量扫
rows, reds = [], []
for s in shot_list:
    sid = s["kst_shot_id"]
    t0, t1 = s["start_sec"], s["end_sec"]
    fp_first, fp_last = f"{FF}/{sid:03d}_first.jpg", f"{FF}/{sid:03d}_last.jpg"
    h_first, h_last = phash(fp_first), phash(fp_last)
    with tempfile.TemporaryDirectory() as td:
        f0, f1 = f"{td}/f0.jpg", f"{td}/f1.jpg"
        ok0 = film_frame(t0 + 0.05, f0)
        ok1 = film_frame(max(0, t1 - 0.12), f1)
        d_first = hamming(h_first, phash(f0)) if (ok0 and h_first is not None) else None
        d_last = hamming(h_last, phash(f1)) if (ok1 and h_last is not None) else None
    d_self = hamming(h_first, h_last) if (h_first is not None and h_last is not None) else None
    worst = max(x for x in (d_first, d_last) if x is not None) if (d_first is not None or d_last is not None) else None
    verdict = ("NO_HASH" if worst is None else
               "RED" if worst > 15 else
               "LIGHT" if worst >= 10 else "ANCHORED")
    row = {"shot": f"S1_{sid:02d}", "kst_id": sid, "dur": round(t1 - t0, 2),
           "d_first": d_first, "d_last": d_last, "d_self": d_self, "verdict": verdict,
           "window": [t0, t1]}
    rows.append(row)
    if verdict == "RED":
        reds.append(row)

json.dump({"protocol": "P1a: frames.json锚帧 vs h264.mp4@shot-list窗口 dHash海明距 (<10锚定/10-15轻/>15红)",
           "film": FILM, "count": len(rows), "rows": rows,
           "red_count": len(reds)}, open(f"{OUT}/scan_93.json", "w"), ensure_ascii=False, indent=1)

n_ok = sum(1 for r in rows if r["verdict"] == "ANCHORED")
n_light = sum(1 for r in rows if r["verdict"] == "LIGHT")
print(f"\n=== P1a 全镜锚评分: {n_ok} ANCHORED / {n_light} LIGHT / {len(reds)} RED (共{len(rows)}) ===")
for r in reds:
    print(f"RED {r['shot']} dur={r['dur']}s d_first={r['d_first']} d_last={r['d_last']} win={r['window']}")
print("\nLIGHT:")
for r in rows:
    if r["verdict"] == "LIGHT":
        print(f"LIGHT {r['shot']} d_first={r['d_first']} d_last={r['d_last']}")
print("\n运动量TOP10 (d_self, 渲染难度代理):")
for r in sorted(rows, key=lambda x: -(x["d_self"] or 0))[:10]:
    print(f"  {r['shot']} d_self={r['d_self']} dur={r['dur']}s")
