#!/usr/bin/env python3
"""P1a 二道防线: 17 RED 密集重采样甄别 (边界抖动假红 vs 真失真红).
每镜 5 采样点 (t0+0.02/0.10/0.25 | t1-0.25/0.05), 取 min dHash 距.
min<10 → DOWNGRADE(窗口内存在锚定帧,原红为采样偏移); min 仍>15 → CONFIRMED(真失真,送vision).
"""
import json, subprocess, os, sys, tempfile

BASE = "/data/workspace/kais-shot-timeline"
EP = f"{BASE}/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
RB = f"{BASE}/gsrt/renderback"
OUT = f"{RB}/p1a_anchor_scan"
FILM = f"{EP}/h264.mp4"

sys.path.insert(0, RB)
from score_iter import phash, hamming

scan = json.load(open(f"{OUT}/scan_93.json"))
reds = [r for r in scan["rows"] if r["verdict"] == "RED"]

results = []
for r in reds:
    sid, t0, t1 = r["kst_id"], r["window"][0], r["window"][1]
    fp_first, fp_last = f"{OUT}/frames_full/{sid:03d}_first.jpg", f"{OUT}/frames_full/{sid:03d}_last.jpg"
    h_first, h_last = phash(fp_first), phash(fp_last)
    probes_first, probes_last = [], []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate([t0 + 0.02, t0 + 0.10, t0 + 0.30, t0 + (t1 - t0) * 0.5]):
            f = f"{td}/f{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", FILM,
                            "-frames:v", "1", "-q:v", "3", f], capture_output=True)
            if os.path.exists(f) and h_first is not None:
                probes_first.append(hamming(h_first, phash(f)))
        for i, t in enumerate([t1 - 0.30, t1 - 0.15, t1 - 0.05]):
            f = f"{td}/l{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", FILM,
                            "-frames:v", "1", "-q:v", "3", f], capture_output=True)
            if os.path.exists(f) and h_last is not None:
                probes_last.append(hamming(h_last, phash(f)))
    m_first = min(probes_first) if probes_first else None
    m_last = min(probes_last) if probes_last else None
    worst_min = max(x for x in (m_first, m_last) if x is not None)
    verdict = ("DOWNGRADE" if worst_min < 10 else
               "BORDERLINE" if worst_min <= 15 else "CONFIRMED")
    results.append({**r, "min_d_first": m_first, "min_d_last": m_last,
                    "probes_f": probes_first, "probes_l": probes_last, "recheck": verdict})
    print(f"{verdict:10s} {r['shot']} orig=({r['d_first']},{r['d_last']}) min=({m_first},{m_last})")

json.dump(results, open(f"{OUT}/red_recheck.json", "w"), ensure_ascii=False, indent=1)
n_conf = sum(1 for x in results if x["recheck"] == "CONFIRMED")
n_down = sum(1 for x in results if x["recheck"] == "DOWNGRADE")
print(f"\n=== 甄别: {n_conf} CONFIRMED / {n_down} DOWNGRADE / {len(results)-n_conf-n_down} BORDERLINE ===")
