#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 时域修复臂: 21f (唯一变量=帧数/时长, 冻结集逐字克隆 20f 严格臂).

依据 (0904 下午取证链):
  1. 原片吞没终点在物理窗最后 ~2 帧: 174.45s=吞没开始, 174.47s=口腔内部
  2. 20f floor4 网格末锚 = 174.3917s = 扫过过渡帧(嘴未开) → 引擎忠实抵达扫过态
     = 9 臂共同缺陷的真实根因 (推翻"引擎1s跑不完"标签)
  3. 21f 网格末锚 = 173.6+20/24 = 174.4333s = 吞没开始帧 → 锚里第一次有"吞嘴"语义
边界账: 21f 渲染窗 [173.6, 174.475) 越界 s065 起点(174.47) 5ms < 半帧 20.8ms;
  音频轴同步截断至 21/24=0.875s (越界段在窗尾外); 交付时长 0.875/0.87 = 1.006x
  vs 20f 的 0.958x → 更贴近 Kai "时长尽量严格对应" 要求, 边界越界 5ms 登记为已知锁。
用法: python3 iter_s064_21f.py [seeds,默认990202,990204]
"""
import sys, json, time
import subprocess as sp
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R

_orig_load_unit = R.load_unit
def load_unit_21f(uid):
    u = _orig_load_unit(uid)
    # 时域单变量: 覆写 grid_frames → duration_frames() 得 21 (floor(20.88)=20→ hack: 直接给 21f 窗)
    # duration_frames 用 floor(grid/4)*4, 21 不是 4 倍数 → 不能走该函数, 改为在 render_unit 外层组装
    return u
R.load_unit = load_unit_21f

_orig_duration_frames = R.duration_frames
def duration_frames_21f(u, policy):
    return 21  # 唯一变量: 20f → 21f (吞没帧进锚), 越界 5ms 已登记
R.duration_frames = duration_frames_21f

if __name__ == "__main__":
    seeds = [int(s) for s in sys.argv[1].split(",")] if len(sys.argv) > 1 else [990202, 990204]
    for seed in seeds:
        t0 = time.time()
        rec = R.render_unit("s064_p1", seed=seed)
        rec["iter"] = "dur_21f"
        rec["boundary_note"] = "21f window exceeds s065 start by 5ms (<half frame); audio axis kept at 21/24"
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        print(f"[{seed}] wall={time.time()-t0:.0f}s", flush=True)
