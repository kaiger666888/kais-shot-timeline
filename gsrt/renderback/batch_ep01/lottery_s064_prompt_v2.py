#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 prompt v2 seed 彩票: 判定 20f 网格内「张嘴吞镜」终点可达性。
冻结集 = v2 臂逐字克隆(FL2VA+T8AudioLock/lx9/20f floor4/网格锚/v2 prompt), 唯一变量=seed。
990202 已有(v2主臂), 彩票 8 seeds。全部量化双锚 + 末帧落盘供 vision 甄别。
"""
import sys, json, subprocess, time
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R
import numpy as np
from PIL import Image

PROMPT_V2 = open("/tmp/s064_prompt_v2.txt").read().strip()
SEEDS = [990203, 31337, 424242, 777, 20260903, 990204, 990205, 990206]
GT_LAST = "/data/workspace/kais-gold-remount/episodes/ep-xiaojianghu-ep01/S4_closures/p11b_batch/renders/conds/s064_p1_last.jpg"
GT_FIRST = "/data/workspace/kais-gold-remount/episodes/ep-xiaojianghu-ep01/S4_closures/p11b_batch/renders/conds/s064_p1_first.jpg"

_orig_load_unit = R.load_unit
def load_unit_v2(uid):
    u = _orig_load_unit(uid)
    u["h3_prompt"] = PROMPT_V2
    return u
R.load_unit = load_unit_v2

def gray(p, size=(480,274)):
    return np.asarray(Image.open(p).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
def mad(a,b): return float(np.abs(a-b).mean())

def tail_frames(mp4, outdir, n=3):
    """末3帧落盘(渲染末帧≠锚时刻, 甄别用)"""
    subprocess.run(["mkdir","-p",outdir], check=True)
    for i, ss in enumerate(["-0.05","-0.10","-0.15"]):
        subprocess.run(["ffmpeg","-y","-loglevel","error","-sseof",ss,"-i",mp4,
                        "-vframes","1","-q:v","3",f"{outdir}/tail_{i}.jpg"], check=True)

results = []
for seed in SEEDS:
    rec = R.render_unit("s064_p1", seed)
    if rec.get("status") != "success":
        print(json.dumps({"seed":seed,"status":rec.get("status")}), flush=True)
        continue
    mp4 = rec["video"]
    f0, l0 = f"/tmp/s064_lot/f_{seed}.jpg", f"/tmp/s064_lot/l_{seed}.jpg"
    subprocess.run(["mkdir","-p","/tmp/s064_lot"], check=True)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",mp4,"-vframes","1","-q:v","3",f0], check=True)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-sseof","-0.05","-i",mp4,"-vframes","1","-q:v","3",l0], check=True)
    tail_frames(mp4, f"/tmp/s064_lot/tails_{seed}")
    ml, mf = mad(gray(l0), gray(GT_LAST)), mad(gray(f0), gray(GT_FIRST))
    entry = dict(seed=seed, mad_last=round(ml,2), mad_first=round(mf,2), video=mp4)
    results.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)

results.sort(key=lambda r: r["mad_last"])
json.dump(results, open("/tmp/s064_lot/lottery_v2_results.json","w"), indent=1)
print("RANKING:", json.dumps(results, ensure_ascii=False, indent=1), flush=True)
