#!/usr/bin/env python3
"""音轨分离 + 分镜级音频能量分析

流程：
  1. Demucs htdemucs 4-stem 分离（vocals / drums / bass / other）
  2. 加载分镜 JSON
  3. 计算每个分镜在 4 条 stem 上的 RMS 能量与频谱重心
  4. 按比例判定主导音频类型（dialogue / bgm / sfx / mixed）
  5. 写出 per-shot audio profile JSON

输出 JSON 结构：
{
  "episode": "<video stem>",
  "duration": <float>,
  "stems": ["vocals","drums","bass","other"],
  "shots": [
    {
      "shot_id": 1,
      "start_sec": 0.0, "end_sec": 6.7, "duration": 6.7,
      "energies": {"vocals": 0.12, "drums": 0.03, "bass": 0.02, "other": 0.05},
      "ratios":   {"vocals": 0.50, "drums": 0.12, "bass": 0.08, "other": 0.30},
      "spectral_centroid": {"vocals": 1240.0, ...},
      "dominant_type": "dialogue"
    },
    ...
  ],
  "type_distribution": {"dialogue": 36, "bgm": 16, "sfx": 18, "mixed": 22}
}
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


def separate_stems(input_video: str, output_dir: str, model: str = "htdemucs",
                   two_stem: str = None, device: str = None) -> str:
    """调用 Demucs 进行音轨分离。

    参数：
        input_video: 输入视频/音频路径
        output_dir: Demucs 输出根目录（最终 stem 写到 output_dir/<model>/<file_basename>/）
        model: Demucs 模型名（htdemucs / htdemucs_ft 等）
        two_stem: 若指定（如 'vocals'），只做两轨分离
        device: 'cuda' / 'cuda:0' / 'cpu'；None 则让 Demucs 自动选择

    返回：
        stem 目录绝对路径（包含 vocals.wav / drums.wav / bass.wav / other.wav）
    """
    os.makedirs(output_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs",
           "--name", model,
           "--two-stems", two_stem, "-o", output_dir] if two_stem else \
          [sys.executable, "-m", "demucs",
           "--name", model, "-o", output_dir]
    if device:
        cmd += ["-d", device]
    cmd.append(input_video)

    print(f"[demucs] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    base = Path(input_video).stem
    stem_dir = Path(output_dir) / model / base
    if not stem_dir.exists():
        # 兼容某些 Demucs 版本：输出直接放在 output_dir/model/input_filename.wav 形式
        candidate = Path(output_dir) / model
        if candidate.exists():
            stem_dir = candidate
    return str(stem_dir)


def load_audio_stem(path: str):
    """读取 wav 文件，返回 (mono float32 numpy, sample_rate)。"""
    import wave
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
    return audio, sr


def compute_rms_energy(audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> float:
    """计算时间段的 RMS 能量。"""
    s = max(0, min(int(start_sec * sr), len(audio)))
    e = max(s, min(int(end_sec * sr), len(audio)))
    if e == s:
        return 0.0
    seg = audio[s:e]
    return float(np.sqrt(np.mean(seg ** 2) + 1e-10))


def compute_spectral_centroid(audio: np.ndarray, sr: int,
                              start_sec: float, end_sec: float) -> float:
    """估算频谱重心（亮度），用于辅助 stem 类型判定。"""
    s = max(0, min(int(start_sec * sr), len(audio)))
    e = max(s, min(int(end_sec * sr), len(audio)))
    if e - s < 256:
        return 0.0
    seg = audio[s:e]
    n = 8192
    fft = np.fft.rfft(seg[:n])
    mag = np.abs(fft)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    if mag.sum() < 1e-10:
        return 0.0
    return float(np.sum(freqs * mag) / np.sum(mag))


def classify_shot(ratios: dict) -> str:
    """按 stem 能量比例判定主导类型。"""
    vocal = ratios["vocals"]
    bgm = ratios["drums"] + ratios["bass"]
    sfx = ratios["other"]
    if vocal > 0.5:
        return "dialogue"
    if bgm > 0.5:
        return "bgm"
    if sfx > 0.4:
        return "sfx"
    return "mixed"


def analyze_shots(stem_dir: str, shots_json: str, output_json: str,
                  sample_rate: int = 48000) -> dict:
    """计算每个分镜的 per-stem 能量 / 频谱 / 主导类型。"""
    print(f"[analyze] Loading stems from {stem_dir}")
    stems = {}
    for name in ("vocals", "drums", "bass", "other"):
        p = os.path.join(stem_dir, f"{name}.wav")
        if os.path.exists(p):
            audio, sr = load_audio_stem(p)
            stems[name] = audio
            print(f"  {name}: {len(audio) / sr:.1f}s, sr={sr}")
    if not stems:
        raise FileNotFoundError(f"No stems found under {stem_dir}")

    with open(shots_json) as f:
        shots = json.load(f)
    print(f"[analyze] {len(shots)} shots to profile")

    first_stem_name = next(iter(stems.keys()))
    first_stem_path = os.path.join(stem_dir, first_stem_name + ".wav")
    _, sr = load_audio_stem(first_stem_path)

    results = []
    for shot in shots:
        s, e = shot["start_sec"], shot["end_sec"]
        energies = {n: compute_rms_energy(a, sr, s, e) for n, a in stems.items()}
        centroids = {n: compute_spectral_centroid(a, sr, s, e) for n, a in stems.items()}
        total = sum(energies.values()) + 1e-10
        ratios = {k: v / total for k, v in energies.items()}
        results.append({
            "shot_id": shot["id"],
            "start_sec": s,
            "end_sec": e,
            "duration": shot["duration"],
            "energies": {k: round(v, 4) for k, v in energies.items()},
            "ratios": {k: round(v, 4) for k, v in ratios.items()},
            "spectral_centroid": {k: round(v, 1) for k, v in centroids.items()},
            "dominant_type": classify_shot(ratios),
        })
        if shot["id"] % 10 == 0:
            print(f"  Processed {shot['id']}/{len(shots)}")

    type_counts = {}
    for r in results:
        t = r["dominant_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print("[analyze] type distribution:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c} shots ({c / len(results) * 100:.1f}%)")

    out = {
        "episode": Path(shots_json).stem,
        "duration": shots[-1]["end_sec"] if shots else 0.0,
        "stems": list(stems.keys()),
        "shots": results,
        "type_distribution": type_counts,
    }
    with open(output_json, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[analyze] saved {output_json}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Demucs 4-stem 分离 + 分镜级音频能量分析")
    ap.add_argument("--input", required=True, help="输入视频或音频文件")
    ap.add_argument("--shots", required=True, help="分镜 JSON（detect_v3b.py 输出）")
    ap.add_argument("--output-dir", default="./stems",
                    help="Demucs 输出根目录（默认 ./stems）")
    ap.add_argument("--output", default=None,
                    help="音频分析 JSON 输出路径（默认 <output-dir>/<input-stem>_audio_analysis.json）")
    ap.add_argument("--model", default="htdemucs", help="Demucs 模型名（默认 htdemucs）")
    ap.add_argument("--two-stem", default=None,
                    help="若指定（如 vocals），只做两轨分离；否则 4-stem")
    ap.add_argument("--device", default=None, help="cuda / cuda:0 / cpu")
    ap.add_argument("--skip-separate", action="store_true",
                    help="跳过 Demucs 步骤，假设 stem 已存在于 output-dir")
    args = ap.parse_args()

    if args.skip_separate:
        base = Path(args.input).stem
        stem_dir = os.path.join(args.output_dir, args.model, base)
        if not os.path.isdir(stem_dir):
            # 兜底：尝试 output_dir 本身
            stem_dir = args.output_dir
        print(f"[skip-separate] using existing stems at {stem_dir}")
    else:
        stem_dir = separate_stems(args.input, args.output_dir,
                                  model=args.model, two_stem=args.two_stem,
                                  device=args.device)

    out_json = args.output or os.path.join(
        args.output_dir, f"{Path(args.input).stem}_audio_analysis.json")
    analyze_shots(stem_dir, args.shots, out_json)


if __name__ == "__main__":
    main()
