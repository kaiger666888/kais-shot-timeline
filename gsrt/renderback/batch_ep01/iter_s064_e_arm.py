#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 E臂: 21f + 口腔首帧直抽锚 + v3 prompt (合并两个已证正贡献变量 + 锚直抽).
   依据: C臂(21f+anchor174.4333+v1prompt) 57.8 已优于 A臂最优 64.9;
   22f 证伪越窗路线; ffmpeg 30fps 网格化 -ss 174.4750 无法命中口腔帧 174.4667.
   E臂: 直接 -ss 174.4667 抽口腔帧为尾锚(绕过网格数学), 21f 窗(不越原片), v3 prompt.
"""
import sys, json, time
import subprocess as sp
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R

PROMPT_V3 = open("/tmp/s064_repair/prompt_v3.txt").read().strip()
ORIG_LOAD = R.load_unit
def lu(uid):
    u = ORIG_LOAD(uid)
    u["h3_prompt"] = PROMPT_V3
    return u
R.load_unit = lu

def duration_frames_21(u, policy):
    return 21
R.duration_frames = duration_frames_21

# 覆写 extract 后的网格末锚重抽: 22f 脚本里 grid_anchor 分支用 t=start+(frames-1)/FPS
# frames=21 → 174.4333. 需要把该重抽换成直抽 174.4667. 渲染走 render_unit 内联逻辑, 
# 因此 monkeypatch extract_conds 让它返回直抽的口腔帧:
ORIG_EXTRACT = R.extract_conds
def extract_conds_e(u, outdir):
    cf, cl = ORIG_EXTRACT(u, outdir)
    # 直抽口腔首帧 (源30fps, 帧心 174.4667)
    sp.run(["ffmpeg","-y","-v","error","-ss","174.4667","-i",R.SOURCE_EP01,
            "-frames:v","1",cl], check=True)
    return cf, cl
R.extract_conds = extract_conds_e

if __name__ == "__main__":
    t0 = time.time()
    rec = R.render_unit("s064_p1", seed=990204)
    rec["iter"] = "e_21f_oral_anchor_v3prompt"
    rec["boundary_note"] = "21f (no window violation) + oral-cavity first frame (174.4667, vision-verified) direct-extract as cond_last + prompt v3"
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    print(f"wall={time.time()-t0:.0f}s", flush=True)
