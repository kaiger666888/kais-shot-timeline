#!/usr/bin/env python3
"""V3b: Adaptive min_scene_len based on rapid montage detection."""
import json, os
import numpy as np
from PIL import Image
from scenedetect import detect, AdaptiveDetector

h264 = "/tmp/xiaojianghu_psd/ep01_h264.mp4"
frame_dir = "/tmp/ep01_frames_5fps"
sample_fps = 5.0
duration = 308.33

# === Pass 1: PySceneDetect ===
psd_scenes = detect(h264, AdaptiveDetector(adaptive_threshold=4.0, min_scene_len=30))
psd_cuts = [round(s.get_seconds(), 2) for s, e in psd_scenes if s.get_seconds() > 0.1]
print(f"PSD: {len(psd_cuts)} cuts")

# === Pass 2: Histogram correlation ===
frame_files = sorted(os.listdir(frame_dir))
hists = []
for i, fname in enumerate(frame_files):
    arr = np.array(Image.open(os.path.join(frame_dir, fname)).convert("RGB"), dtype=np.float32)
    bins = 8  # 8x8x8=512 bins, low noise for main pass
    step = 256 // bins  # 16 for bins=16
    r = (arr[:,:,0]//step).astype(int).clip(0,bins-1)
    g = (arr[:,:,1]//step).astype(int).clip(0,bins-1)
    b = (arr[:,:,2]//step).astype(int).clip(0,bins-1)
    hist = np.zeros(bins**3, dtype=np.float32)
    np.add.at(hist, (r*bins*bins+g*bins+b).ravel(), 1)
    hist /= hist.sum()
    hists.append((i / sample_fps, hist))

hist_cuts_raw = []
for i in range(1, len(hists)):
    t_curr, h_curr = hists[i]
    t_prev, h_prev = hists[i-1]
    corr = np.dot(h_curr, h_prev) / (np.linalg.norm(h_curr) * np.linalg.norm(h_prev) + 1e-8)
    if corr < 0.90:
        hist_cuts_raw.append(round(t_curr, 2))
print(f"HistCorr: {len(hist_cuts_raw)} cuts")

# === Refine HistCorr-only cuts to frame-level precision ===
# For each histcorr cut NOT near a PSD cut, scan ±0.3s frame-by-frame
# to find the exact transition frame (lowest corr).
psd_set_temp = set(psd_cuts)
hist_cuts = []
import cv2 as _cv2
_cap = _cv2.VideoCapture(h264)
_fps = _fps if (_fps := _cap.get(_cv2.CAP_PROP_FPS)) > 0 else 30.0

for hc in hist_cuts_raw:
    # Check if a PSD cut is nearby (within 0.3s) — if so, skip refinement
    if any(abs(hc - pc) < 0.3 for pc in psd_set_temp):
        hist_cuts.append(hc)
        continue
    
    # Frame-level scan ±0.3s around the histcorr sampling point
    scan_start = max(0, hc - 0.3)
    scan_end = hc + 0.3
    sf = int(scan_start * _fps)
    ef = int(scan_end * _fps)
    _cap.set(_cv2.CAP_PROP_POS_FRAMES, sf)
    
    _prev_h = None
    _best_corr = 1.0
    _best_t = hc
    
    for _fn in range(sf, ef + 1):
        _ret, _frm = _cap.read()
        if not _ret:
            break
        _h = _cv2.calcHist([_frm], [0,1,2], None, [8,8,8], [0,256,0,256,0,256])
        _h = _cv2.normalize(_h, _h).flatten()
        if _prev_h is not None:
            _c = _cv2.compareHist(_prev_h, _h, _cv2.HISTCMP_CORREL)
            if _c < _best_corr:
                _best_corr = _c
                _best_t = _fn / _fps
        _prev_h = _h
    
    refined = round(_best_t, 2)
    hist_cuts.append(refined)

_cap.release()
print(f"HistCorr refined: {len(hist_cuts)} cuts")

# === Detect rapid montage zones ===
rapid_zones = []
i = 0
while i < len(hist_cuts):
    zone_start = hist_cuts[i]
    nearby = [c for c in hist_cuts if zone_start <= c < zone_start + 2.0]
    if len(nearby) >= 3:
        zone_end = max(nearby) + 0.5
        rapid_zones.append((zone_start - 0.2, zone_end))
        i += len(nearby) - 1
    i += 1

print(f"Rapid montage zones: {[(round(s,1), round(e,1)) for s,e in rapid_zones]}")

def is_in_rapid_zone(t):
    for s, e in rapid_zones:
        if s <= t <= e:
            return True
    return False

# === Merge ===
# Tag each cut with its source for precision-aware dedup
psd_set = set(psd_cuts)
all_tagged = sorted(set(psd_cuts + hist_cuts), key=lambda c: c)

# Dedup: 0.3s window, but prefer PSD (frame-level precision) over HistCorr (5fps sampling)
merged = []
for c in all_tagged:
    if not merged or abs(c - merged[-1]) > 0.3:
        merged.append(c)
    else:
        # Collision: keep the PSD value (higher precision) if available
        if c in psd_set and merged[-1] not in psd_set:
            merged[-1] = c  # Replace lower-precision with higher-precision

# Min scene len: 0.5s in rapid zones, 1.0s elsewhere
final_cuts = []
for c in merged:
    min_len = 0.5 if is_in_rapid_zone(c) else 1.0
    if not final_cuts or c - final_cuts[-1] >= min_len:
        final_cuts.append(c)

# === Pass 3: Frame-level scan of long shots ===
# PSD misses cuts in high-motion segments; HistCorr 5fps/8x8x8 is too coarse.
# For shots > 3.0s outside rapid zones, scan frame-by-frame with 16x16x16 bins
# to catch mid-range cuts (corr 0.85-0.90 range) that both passes missed.
import cv2
pass3_cuts = []
cap3 = cv2.VideoCapture(h264)
fps3 = fps3 if (fps3 := cap3.get(cv2.CAP_PROP_FPS)) > 0 else 30.0

temp_boundaries = [0.0] + final_cuts + [duration]
for i in range(len(temp_boundaries) - 1):
    seg_start = temp_boundaries[i]
    seg_end = temp_boundaries[i + 1]
    seg_dur = seg_end - seg_start
    
    if seg_dur < 3.0 or is_in_rapid_zone(seg_start):
        continue
    
    # Frame-level scan with 16x16x16 bins
    sf = int(seg_start * fps3) + 1  # skip first frame (already boundary)
    ef = int((seg_end - 0.1) * fps3)
    cap3.set(cv2.CAP_PROP_POS_FRAMES, sf)
    
    prev_h3 = None
    for fn3 in range(sf, ef + 1):
        ret3, frm3 = cap3.read()
        if not ret3:
            break
        h3 = cv2.calcHist([frm3], [0,1,2], None, [16,16,16], [0,256,0,256,0,256])
        h3 = cv2.normalize(h3, h3).flatten()
        if prev_h3 is not None:
            c3 = cv2.compareHist(prev_h3, h3, cv2.HISTCMP_CORREL)
            if c3 < 0.88:
                t3 = round(fn3 / fps3, 2)
                pass3_cuts.append(t3)
        prev_h3 = h3

cap3.release()
print(f"Pass3 (long-shot frame scan 16x16x16, thresh=0.88): {len(pass3_cuts)} cuts")

# Merge pass3 into final_cuts
all_final_p3 = sorted(set(final_cuts + pass3_cuts))

# === Pass 4: Dissolve transition detection ===
# Dissolve/fade transitions have near-zero adjacent-frame difference,
# making them invisible to PSD, HistCorr, and Pass3.
# Uses W=15 sliding-window corr + RGB monotonicity validation.
def detect_dissolves_pass4(video_path, existing_cuts, vfps=30.0, window=15):
    """Detect dissolve transitions using sliding-window corr + RGB validation."""
    cap = cv2.VideoCapture(video_path)
    all_h = []
    all_rgb = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        h = cv2.calcHist([frame], [0,1,2], None, [16,16,16], [0,256,0,256,0,256])
        h = cv2.normalize(h, h).flatten()
        all_h.append(h)
        mb, mg, mr = cv2.mean(frame)[:3]
        all_rgb.append((mb, mg, mr))
    cap.release()

    n = len(all_h)
    corrs = []
    for i in range(window, n):
        c = cv2.compareHist(all_h[i-window], all_h[i], cv2.HISTCMP_CORREL)
        corrs.append((i / vfps, c, i))

    existing_set = set(round(c, 1) for c in existing_cuts)
    dissolves = []

    for idx in range(len(corrs)):
        ts, c, fno = corrs[idx]
        if c >= 0.78:
            continue

        # Local minimum check (±0.3s)
        ls = max(0, idx - 9)
        re = min(len(corrs), idx + 9)
        lv = [corrs[j][1] for j in range(ls, idx)]
        rv = [corrs[j][1] for j in range(idx+1, re)]
        if len(lv) < 3 or len(rv) < 3:
            continue
        if c > min(lv) or c > min(rv):
            continue

        # V-shape recovery (±0.5s)
        lr = [corrs[j][1] for j in range(max(0, idx-15), idx)]
        rr = [corrs[j][1] for j in range(idx+1, min(len(corrs), idx+15))]
        if max(lr) <= 0.93 or max(rr) <= 0.93:
            continue

        # Valley width
        vw = 1
        j = idx - 1
        while j >= 0 and corrs[j][1] < 0.90:
            vw += 1; j -= 1
        j = idx + 1
        while j < len(corrs) and corrs[j][1] < 0.90:
            vw += 1; j += 1
        if vw / vfps >= 1.0:
            continue

        # Skip near existing boundary (0.8s to avoid false positives from
        # RGB stabilization after nearby hard cuts)
        if any(abs(ts - b) < 0.8 for b in existing_set):
            continue

        # RGB validation: monotonicity + stability
        vf_s = max(0, fno - vw)
        vf_e = min(n, fno + vw)
        pre_s = max(0, vf_s - 15)
        pre_rgbs = all_rgb[pre_s:vf_s]
        post_rgbs = all_rgb[vf_e:min(n, vf_e+15)]
        if len(pre_rgbs) < 5 or len(post_rgbs) < 5:
            continue

        if np.max(np.std(pre_rgbs, axis=0)) > 3.0 or np.max(np.std(post_rgbs, axis=0)) > 3.0:
            continue

        pre_mean = np.mean(pre_rgbs, axis=0)
        post_mean = np.mean(post_rgbs, axis=0)
        if np.max(np.abs(post_mean - pre_mean)) < 8.0:
            continue

        # Monotonicity
        valley_rgbs = all_rgb[vf_s:vf_e]
        if len(valley_rgbs) < 3:
            continue
        mono_ok = 0
        total_ch = 0
        for ch in range(3):
            vals = [v[ch] for v in valley_rgbs]
            delta = post_mean[ch] - pre_mean[ch]
            if abs(delta) < 3:
                continue
            total_ch += 1
            direction = 1 if delta > 0 else -1
            consistent = sum(1 for i in range(1, len(vals)) if (vals[i]-vals[i-1]) * direction >= -1)
            if consistent / len(vals) >= 0.7:
                mono_ok += 1
        if total_ch == 0 or mono_ok < total_ch:
            continue

        dissolves.append(round(ts, 2))

    return dissolves

# Build temp shots from pass3 for boundary reference
temp_b = [0.0] + all_final_p3 + [duration]
pass4_cuts = detect_dissolves_pass4(h264, temp_b)
print(f"Pass4 (dissolve detection): {len(pass4_cuts)} cuts {pass4_cuts}")

all_final = sorted(set(all_final_p3 + pass4_cuts))

# Build shots
boundaries = [0.0] + all_final + [duration]
shots = []
for i in range(len(boundaries)-1):
    s, e = boundaries[i], boundaries[i+1]
    dur = e - s
    if dur >= 0.3:
        shots.append({"id": len(shots)+1, "start_sec": round(s,2), "end_sec": round(e,2), "duration": round(dur,2)})
for i, s in enumerate(shots):
    s["id"] = i + 1

short = sum(1 for s in shots if s["duration"] < 1.0)
long_shots = sum(1 for s in shots if s["duration"] > 8)
print(f"\nV3b result: {len(shots)} shots (short<1s={short}, long>8s={long_shots})")

# Show 95-120s
print(f"\n95-122s region:")
for s in shots:
    if 94 <= s["start_sec"] <= 122:
        rapid = " [RAPID]" if is_in_rapid_zone(s["start_sec"]) else ""
        marker = " ⚠️" if s["duration"] < 1.0 else ""
        print(f"  #{s['id']:3d}  {s['start_sec']:7.2f}s → {s['end_sec']:7.2f}s  ({s['duration']:5.2f}s){marker}{rapid}")

with open("/tmp/ep01_v3b_shots.json", "w") as f:
    json.dump(shots, f, indent=2)
print("\nSaved.")
