#!/usr/bin/env python3
"""V3b 融合检测：AdaptiveDetector 粗切 + Histogram 相关性补切 + Pass3 长镜头
帧级扫描 + Pass4 溶解转场检测，全部参数化。

4 趟检测：
  Pass 1: PySceneDetect AdaptiveDetector（粗切）
  Pass 2: 5fps 帧直方图相关性 → HistCorr 补切 + 帧级精确化
  Pass 3: 长镜头（>3s）逐帧 16x16x16 直方图扫描
  Pass 4: 滑动窗口相关性 + RGB 单调性 → 溶解/淡入淡出转场

输出：分镜 JSON [{id, start_sec, end_sec, duration}, ...]

用法：
  python detectors/detect_v3b.py --video input.mp4 [--frames-dir ./frames]
                                 [--sample-fps 5] [--output shots.json]
                                 [--adaptive-threshold 4.0] [--min-scene-len 30]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scenedetect import detect, AdaptiveDetector


def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def needs_transcode(video_path: str) -> bool:
    """判断是否为 AV1（PySceneDetect 不擅长 AV1，需要先转 H264）。"""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path],
        capture_output=True, text=True)
    return "av1" in r.stdout.strip().lower()


def transcode_to_h264(video_path: str, h264_path: str) -> str:
    print(f"[transcode] {video_path} → {h264_path}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an",
         h264_path], check=True)
    return h264_path


def ensure_h264(video_path: str, work_dir: str) -> str:
    """若视频是 AV1，转码到 H264；否则原路径返回。"""
    if not needs_transcode(video_path):
        return video_path
    os.makedirs(work_dir, exist_ok=True)
    h264_path = os.path.join(work_dir, Path(video_path).stem + "_h264.mp4")
    if not os.path.exists(h264_path) or os.path.getsize(h264_path) < 100_000:
        transcode_to_h264(video_path, h264_path)
    return h264_path


def sample_frames(video_path: str, frame_dir: str, sample_fps: float = 5.0):
    """用 ffmpeg 按指定 fps 抽帧到 frame_dir（用于 Pass2 HistCorr）。"""
    os.makedirs(frame_dir, exist_ok=True)
    print(f"[sample] {sample_fps} fps → {frame_dir}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vf", f"fps={sample_fps}", "-q:v", "3",
         os.path.join(frame_dir, "f%06d.jpg"), "-loglevel", "error"],
        check=True)


def run_pass1(h264_path: str, adaptive_threshold: float, min_scene_len: int):
    """Pass 1: PySceneDetect AdaptiveDetector 粗切。"""
    scenes = detect(h264_path, AdaptiveDetector(
        adaptive_threshold=adaptive_threshold, min_scene_len=min_scene_len))
    cuts = [round(s.get_seconds(), 2) for s, _ in scenes if s.get_seconds() > 0.1]
    print(f"[pass1] PSD AdaptiveDetector: {len(cuts)} cuts")
    return cuts


def run_pass2_histcorr(h264_path: str, frame_dir: str, sample_fps: float,
                       psd_cuts: list):
    """Pass 2: 5fps 帧直方图相关性 → HistCorr 补切 + 帧级精确化。

    步骤：
      1. 在 frame_dir 中读取所有 5fps 抽样帧，计算 8x8x8 RGB 直方图
      2. 相邻帧 cosine corr < 0.90 视为候选切换点
      3. 对每个候选点，若 0.3s 内已有 PSD 切则保留原值；
         否则在 ±0.3s 范围内逐帧扫描 8x8x8 直方图，定位最低 corr 帧
    """
    import cv2
    frame_files = sorted(os.listdir(frame_dir))
    hists = []
    bins = 8
    step = 256 // bins
    for i, fname in enumerate(frame_files):
        arr = np.array(Image.open(os.path.join(frame_dir, fname)).convert("RGB"),
                       dtype=np.float32)
        r = (arr[:, :, 0] // step).astype(int).clip(0, bins - 1)
        g = (arr[:, :, 1] // step).astype(int).clip(0, bins - 1)
        b = (arr[:, :, 2] // step).astype(int).clip(0, bins - 1)
        h = np.zeros(bins ** 3, dtype=np.float32)
        np.add.at(h, (r * bins * bins + g * bins + b).ravel(), 1)
        h /= h.sum()
        hists.append((i / sample_fps, h))

    raw = []
    for i in range(1, len(hists)):
        corr = float(np.dot(hists[i][1], hists[i - 1][1]) /
                     (np.linalg.norm(hists[i][1]) *
                      np.linalg.norm(hists[i - 1][1]) + 1e-8))
        if corr < 0.90:
            raw.append(round(hists[i][0], 2))
    print(f"[pass2] HistCorr 5fps/8bins: {len(raw)} raw cuts")

    cap = cv2.VideoCapture(h264_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    refined = []
    for hc in raw:
        if any(abs(hc - pc) < 0.3 for pc in psd_cuts):
            refined.append(hc)
            continue
        sf = int(max(0, hc - 0.3) * fps)
        ef = int((hc + 0.3) * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, sf)
        prev_h = None
        best_corr, best_t = 1.0, hc
        for fno in range(sf, ef + 1):
            ret, frm = cap.read()
            if not ret:
                break
            h = cv2.calcHist([frm], [0, 1, 2], None, [8, 8, 8],
                             [0, 256, 0, 256, 0, 256])
            h = cv2.normalize(h, h).flatten()
            if prev_h is not None:
                c = cv2.compareHist(prev_h, h, cv2.HISTCMP_CORREL)
                if c < best_corr:
                    best_corr = c
                    best_t = fno / fps
            prev_h = h
        refined.append(round(best_t, 2))
    cap.release()
    print(f"[pass2] HistCorr refined: {len(refined)} cuts")
    return refined


def detect_rapid_zones(hist_cuts: list):
    """检测快剪蒙太奇区域（2s 内 ≥3 切）。"""
    zones = []
    i = 0
    while i < len(hist_cuts):
        zs = hist_cuts[i]
        nearby = [c for c in hist_cuts if zs <= c < zs + 2.0]
        if len(nearby) >= 3:
            zones.append((zs - 0.2, max(nearby) + 0.5))
            i += len(nearby) - 1
        i += 1
    return zones


def in_rapid_zone(t, zones):
    return any(s <= t <= e for s, e in zones)


def merge_cuts(psd_cuts, hist_cuts, rapid_zones):
    """合并 PSD + HistCorr，按精度优先级去重，再按区域应用 min_scene_len。"""
    psd_set = set(psd_cuts)
    all_sorted = sorted(set(psd_cuts + hist_cuts))
    merged = []
    for c in all_sorted:
        if not merged or abs(c - merged[-1]) > 0.3:
            merged.append(c)
        elif c in psd_set and merged[-1] not in psd_set:
            merged[-1] = c  # PSD 精度优先

    final = []
    for c in merged:
        min_len = 0.5 if in_rapid_zone(c, rapid_zones) else 1.0
        if not final or c - final[-1] >= min_len:
            final.append(c)
    return final


def run_pass3_long_shots(h264_path: str, boundaries: list, rapid_zones: list,
                         duration: float, corr_thresh: float = 0.88,
                         min_seg_dur: float = 3.0):
    """Pass 3: 对长镜头（>3s）逐帧 16x16x16 扫描，捕获中等差异切换。"""
    import cv2
    cap = cv2.VideoCapture(h264_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cuts = []
    temp_b = [0.0] + list(boundaries) + [duration]
    for i in range(len(temp_b) - 1):
        ss, se = temp_b[i], temp_b[i + 1]
        if se - ss < min_seg_dur or in_rapid_zone(ss, rapid_zones):
            continue
        sf = int(ss * fps) + 1
        ef = int((se - 0.1) * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, sf)
        prev_h = None
        for fno in range(sf, ef + 1):
            ret, frm = cap.read()
            if not ret:
                break
            h = cv2.calcHist([frm], [0, 1, 2], None, [16, 16, 16],
                             [0, 256, 0, 256, 0, 256])
            h = cv2.normalize(h, h).flatten()
            if prev_h is not None:
                c = cv2.compareHist(prev_h, h, cv2.HISTCMP_CORREL)
                if c < corr_thresh:
                    cuts.append(round(fno / fps, 2))
            prev_h = h
    cap.release()
    print(f"[pass3] long-shot scan 16x16x16 (thresh={corr_thresh}): "
          f"{len(cuts)} cuts")
    return cuts


def run_pass4_dissolves(video_path: str, existing_cuts: list,
                        vfps: float = 30.0, window: int = 15):
    """Pass 4: 溶解/淡入淡出转场检测（滑动窗口 corr + RGB 单调性）。"""
    import cv2
    cap = cv2.VideoCapture(video_path)
    all_h, all_rgb = [], []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        h = cv2.calcHist([frame], [0, 1, 2], None, [16, 16, 16],
                         [0, 256, 0, 256, 0, 256])
        h = cv2.normalize(h, h).flatten()
        all_h.append(h)
        mb, mg, mr = cv2.mean(frame)[:3]
        all_rgb.append((mb, mg, mr))
    cap.release()

    n = len(all_h)
    corrs = []
    for i in range(window, n):
        c = cv2.compareHist(all_h[i - window], all_h[i], cv2.HISTCMP_CORREL)
        corrs.append((i / vfps, c, i))

    existing_set = set(round(c, 1) for c in existing_cuts)
    dissolves = []
    for idx in range(len(corrs)):
        ts, c, fno = corrs[idx]
        if c >= 0.78:
            continue
        ls = max(0, idx - 9)
        re = min(len(corrs), idx + 9)
        lv = [corrs[j][1] for j in range(ls, idx)]
        rv = [corrs[j][1] for j in range(idx + 1, re)]
        if len(lv) < 3 or len(rv) < 3:
            continue
        if c > min(lv) or c > min(rv):
            continue
        lr = [corrs[j][1] for j in range(max(0, idx - 15), idx)]
        rr = [corrs[j][1] for j in range(idx + 1, min(len(corrs), idx + 15))]
        if max(lr) <= 0.93 or max(rr) <= 0.93:
            continue
        vw = 1
        j = idx - 1
        while j >= 0 and corrs[j][1] < 0.90:
            vw += 1; j -= 1
        j = idx + 1
        while j < len(corrs) and corrs[j][1] < 0.90:
            vw += 1; j += 1
        if vw / vfps >= 1.0:
            continue
        if any(abs(ts - b) < 0.8 for b in existing_set):
            continue
        vf_s = max(0, fno - vw)
        vf_e = min(n, fno + vw)
        pre_s = max(0, vf_s - 15)
        pre_rgbs = all_rgb[pre_s:vf_s]
        post_rgbs = all_rgb[vf_e:min(n, vf_e + 15)]
        if len(pre_rgbs) < 5 or len(post_rgbs) < 5:
            continue
        if np.max(np.std(pre_rgbs, axis=0)) > 3.0 or \
                np.max(np.std(post_rgbs, axis=0)) > 3.0:
            continue
        pre_mean = np.mean(pre_rgbs, axis=0)
        post_mean = np.mean(post_rgbs, axis=0)
        if np.max(np.abs(post_mean - pre_mean)) < 8.0:
            continue
        valley_rgbs = all_rgb[vf_s:vf_e]
        if len(valley_rgbs) < 3:
            continue
        mono_ok, total_ch = 0, 0
        for ch in range(3):
            vals = [v[ch] for v in valley_rgbs]
            delta = post_mean[ch] - pre_mean[ch]
            if abs(delta) < 3:
                continue
            total_ch += 1
            direction = 1 if delta > 0 else -1
            consistent = sum(1 for k in range(1, len(vals))
                             if (vals[k] - vals[k - 1]) * direction >= -1)
            if consistent / len(vals) >= 0.7:
                mono_ok += 1
        if total_ch == 0 or mono_ok < total_ch:
            continue
        dissolves.append(round(ts, 2))
    print(f"[pass4] dissolve detection: {len(dissolves)} cuts {dissolves}")
    return dissolves


def detect_shots(video_path: str, frames_dir: str = None,
                 sample_fps: float = 5.0,
                 adaptive_threshold: float = 4.0,
                 min_scene_len: int = 30) -> list:
    """完整 V3b 流程，返回分镜列表。"""
    duration = probe_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"无法读取视频时长: {video_path}")

    work_dir = os.path.dirname(os.path.abspath(video_path))
    h264 = ensure_h264(video_path, work_dir)

    if frames_dir is None:
        frames_dir = tempfile.mkdtemp(prefix="v3b_frames_")
    sample_frames(h264, frames_dir, sample_fps)

    psd_cuts = run_pass1(h264, adaptive_threshold, min_scene_len)
    hist_cuts = run_pass2_histcorr(h264, frames_dir, sample_fps, psd_cuts)
    rapid_zones = detect_rapid_zones(hist_cuts)
    print(f"[merge] rapid montage zones: "
          f"{[(round(s, 1), round(e, 1)) for s, e in rapid_zones]}")

    merged = merge_cuts(psd_cuts, hist_cuts, rapid_zones)
    pass3_cuts = run_pass3_long_shots(h264, merged, rapid_zones, duration)
    all_p3 = sorted(set(merged + pass3_cuts))
    pass4_cuts = run_pass4_dissolves(h264, all_p3)
    all_final = sorted(set(all_p3 + pass4_cuts))

    boundaries = [0.0] + all_final + [duration]
    shots = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        if e - s >= 0.3:
            shots.append({
                "id": len(shots) + 1,
                "start_sec": round(s, 2),
                "end_sec": round(e, 2),
                "duration": round(e - s, 2),
            })
    for i, s in enumerate(shots):
        s["id"] = i + 1

    short = sum(1 for s in shots if s["duration"] < 1.0)
    long_shots = sum(1 for s in shots if s["duration"] > 8)
    print(f"\n[result] V3b: {len(shots)} shots "
          f"(short<1s={short}, long>8s={long_shots})")
    return shots


def main():
    ap = argparse.ArgumentParser(description="V3b 融合分镜检测")
    ap.add_argument("--video", required=True, help="输入视频路径")
    ap.add_argument("--frames-dir", default=None,
                    help="5fps 抽帧目录（默认临时目录）")
    ap.add_argument("--sample-fps", type=float, default=5.0,
                    help="Pass2 HistCorr 抽帧频率（默认 5）")
    ap.add_argument("--adaptive-threshold", type=float, default=4.0,
                    help="AdaptiveDetector 阈值（默认 4.0）")
    ap.add_argument("--min-scene-len", type=int, default=30,
                    help="AdaptiveDetector 最小场景帧数（默认 30）")
    ap.add_argument("--output", default=None,
                    help="输出分镜 JSON 路径（默认 <video-basename>_v3b_shots.json）")
    args = ap.parse_args()

    out = args.output or os.path.join(
        os.path.dirname(args.video) or ".",
        f"{Path(args.video).stem}_v3b_shots.json")

    shots = detect_shots(
        args.video, frames_dir=args.frames_dir, sample_fps=args.sample_fps,
        adaptive_threshold=args.adaptive_threshold,
        min_scene_len=args.min_scene_len)

    with open(out, "w") as f:
        json.dump(shots, f, indent=2)
    print(f"[result] saved {len(shots)} shots → {out}")


if __name__ == "__main__":
    main()
