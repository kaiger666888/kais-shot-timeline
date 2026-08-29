#!/usr/bin/env python3
"""GSRT 迭代轮评分器 — 双锚像素差 + 中帧beat视觉判定素材.

判定口径 (与 v1 一致 + v2 增补):
- 双锚: 渲染首/尾帧 vs 目标首/尾帧 的感知哈希海明距离 (v1 用同法, pass线: 双锚均 <15)
- 中帧 beat: 抽渲染 25%/50%/75% 帧存 grid, 供 vision 判定节拍是否发生
  (64: 面部特写占满画面? 89: 横刀亮刀出现? 90: 鞠躬深度≈90度?)
"""
import json, subprocess, os, sys

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
ITER = f"{BASE}/renders_iter"
FRAMES = f"{BASE}/frames"

def phash(path):
    """64-bit dHash via ffmpeg+PIL."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vframes", "1",
                        "-f", "mjpeg", "-"], capture_output=True)
    if r.returncode != 0:
        return None
    import io
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(r.stdout)).convert("L").resize((9, 8))
    except Exception:
        return None
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row*9+col] < px[row*9+col+1] else 0)
    return bits

def hamming(a, b):
    return bin(a ^ b).count("1")

def dual_anchor(vid, sid):
    """渲染首帧=vid第一帧, 尾帧=vid最后一帧; 目标锚=frames/{sid}_first/last.jpg"""
    import tempfile
    scores = {}
    with tempfile.TemporaryDirectory() as td:
        # 渲染首帧
        subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vframes", "1",
                        f"{td}/rf.jpg"], capture_output=True)
        # 渲染尾帧
        subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-0.1", "-i", vid,
                        "-vframes", "1", f"{td}/rl.jpg"], capture_output=True)
        # 中帧 beat 抽帧 (25/50/75%)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "csv=p=0", vid],
                               capture_output=True, text=True)
        dur = float(probe.stdout.strip() or 0)
        for frac, name in [(0.25, "m25"), (0.5, "m50"), (0.75, "m75")]:
            subprocess.run(["ffmpeg", "-v", "error", "-ss", str(dur*frac), "-i", vid,
                            "-vframes", "1", f"{td}/{name}.jpg"], capture_output=True)
        # 目标首尾锚
        tf, tl = f"{FRAMES}/{sid}_first.jpg", f"{FRAMES}/{sid}_last.jpg"
        for label, a, b in [("first", f"{td}/rf.jpg", tf), ("last", f"{td}/rl.jpg", tl)]:
            ha, hb = phash(a), phash(b)
            scores[label] = hamming(ha, hb) if (ha is not None and hb is not None) else 999
        # 中帧 grid 落盘供 vision
        grid = f"{ITER}/{sid}_midbeats.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-i", vid,
                        "-vf", "select='eq(n\\,0)+1',scale=426:-1,tile=3x1", "-vframes", "1",
                        grid], capture_output=True)
        # 更稳: 直接拷三帧拼图
        mid = f"{ITER}/{sid}_midbeats_raw"
        os.makedirs(mid, exist_ok=True)
        for name in ["m25", "m50", "m75"]:
            subprocess.run(["cp", f"{td}/{name}.jpg", f"{mid}/{name}.jpg"],
                           capture_output=True)
    return scores

def main(tag="v3"):
    jobs = json.load(open(f"{ITER}/_{tag}_jobs.json"))
    out = {}
    for sid_s, info in jobs.items():
        sid = sid_s
        f = info.get("file")
        if not f or not os.path.exists(f):
            out[sid] = {"status": "missing"}
            continue
        anchors = dual_anchor(f, sid)
        out[sid] = {
            "file": f,
            "anchor_first_diff": anchors["first"],
            "anchor_last_diff": anchors["last"],
            "pass_anchors": anchors["first"] < 15 and anchors["last"] < 15,
            "midbeats": f"{ITER}/{sid}_midbeats_raw/",
        }
        print(f"shot {sid}: first={anchors['first']} last={anchors['last']} "
              f"pass={'Y' if out[sid]['pass_anchors'] else 'N'}")
    json.dump(out, open(f"{ITER}/_{tag}_scores.json", "w"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v3")
