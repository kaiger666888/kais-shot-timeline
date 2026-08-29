#!/usr/bin/env python3
"""3 CONFIRMED 镜定性触表 v2 — 兼容 frames.json 的 16 字节垃圾前缀 (SOI 扫描剥离).
顺手把 frames_full 缓存全部清洗为标准 JPEG (PIL 可读), 消除后续消费地雷.
"""
import json, subprocess, os, sys
from PIL import Image

BASE = "/data/workspace/kais-shot-timeline"
EP = f"{BASE}/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
OUT = f"{BASE}/gsrt/renderback/p1a_anchor_scan"
FF = f"{OUT}/frames_full"
FILM = f"{EP}/h264.mp4"

def clean_jpeg(path):
    data = open(path, "rb").read()
    i = data.find(b"\xff\xd8\xff")
    if i > 0:
        open(path, "wb").write(data[i:])
        return True
    return i == 0

n = sum(1 for f in os.listdir(FF) if f.endswith(".jpg") and clean_jpeg(f"{FF}/{f}"))
print(f"frames_full cleaned (prefix stripped): {n}")

sl = json.load(open(f"{EP}/p09_shot-list.json"))["shot_list"]
smap = {s["kst_shot_id"]: s for s in sl}

def frame_at(t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", FILM,
                    "-frames:v", "1", "-q:v", "3", out], capture_output=True)

rows_img, labels = [], []
for sid in (34, 52, 55):
    s = smap[sid]
    t0, t1 = s["start_sec"], s["end_sec"]
    cells = [f"{FF}/{sid:03d}_first.jpg"]
    for t in (t0 + 0.02, t0 + 0.6):
        p = f"{OUT}/tmp_{sid}_{t}.jpg"
        frame_at(t, p)
        cells.append(p)
    cells.append(f"{FF}/{sid-1:03d}_last.jpg")
    labels.append(f"row{sid}: S1_{sid:02d} win=[{t0},{t1}] dur={round(t1-t0,2)}s  cols: claimed_first | film@start | film@+0.6s | prev(S1_{sid-1:02d})_claimed_last")
    rows_img.append([Image.open(c).convert("RGB").resize((320, 180)) for c in cells])

cv = Image.new("RGB", (320 * 4, 190 * 3), (20, 20, 20))
for ri, row in enumerate(rows_img):
    for ci, im in enumerate(row):
        cv.paste(im, (ci * 320, ri * 190))
gp = f"{OUT}/confirmed_contact_sheet.jpg"
cv.save(gp, quality=82)
print("grid:", gp)
for l in labels:
    print(" ", l)
