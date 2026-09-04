#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 D臂: 22f 边界实验 — 唯一能把口腔首帧(174.4667)装进 24fps 网格末锚的选项.
   网格末锚 = 173.6+21/24 = 174.4750 (30fps seek 命中≈174.4667 口腔帧, mad34 部分重叠)
   代价: 渲染窗 0.9167s 超原片 0.87s 5.4% — 违反 0903 '≤原片' 注记, 作为 Kai 0904
   '修到至少一臂达验收项' 指令下的边界实验臂登记. prompt 用 manifest v1 (与 21f 臂同, 保持单变量链).
"""
import sys, json, time
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R

def duration_frames_22f(u, policy):
    return 22
R.duration_frames = duration_frames_22f

if __name__ == "__main__":
    t0 = time.time()
    rec = R.render_unit("s064_p1", seed=990204)
    rec["iter"] = "dur_22f_boundary"
    rec["boundary_note"] = "22f window 0.9167s exceeds source 0.87s by 5.4% — deliberate boundary probe; grid anchor 174.4750 lands on oral-cavity first frame"
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    print(f"wall={time.time()-t0:.0f}s", flush=True)
