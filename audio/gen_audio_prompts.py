#!/usr/bin/env python3
"""为每镜生成 audio-gen 风格的自然语言 prompt（spike）

用途：
  本脚本是 producer-only spike —— 从已算好的 Demucs 能量/频谱 + Whisper 对白
  + drum/bass onset 推导出每镜的 audio-gen NL prompt，写到 sidecar
  `audio_prompts.json`。**合约零改动、未进 pipeline、未引入新依赖**（仅
  stdlib + numpy）。输出 sidecar 不被 spec / asset.json / export_asset.py
  引用，仅供肉眼 spot-check 是否值得晋升为 v1.2 milestone。

算法：
  对每个分镜（覆盖 shots.json 全部 shot）：
    1. 读 audio_analysis.json 取该 shot 的 energies / ratios /
       spectral_centroid / dominant_type
    2. 由 dominant_type + brightness (spectral_centroid) + vocal_presence
       (ratios.vocals) 决定 leading phrase
    3. 仅当 drums ratio ≥ 0.10 且 stems 可读时，从 drums.wav envelope
       peak-pick 估 tempo (bpm)；onset < 3 视为不置信 → null
    4. 仅当 transcript.json 可读时，找首个与该 shot 时间重叠的 segment，
       截前 20 字符作 dialogue_excerpt
    5. 按 {leading}[ ~Xbpm][, "excerpt"], {loudness} {brightness} bed 顺序
       拼接成 prompt 字符串

降级路径：
  - 无 transcript.json → dialogue_excerpt=""、vocal_presence 仍由能量比推导
  - 无 stems 目录 → tempo_bpm=null、prompt 不出现 "Xbpm"
  两条降级都必须 graceful（仍产出 prompt，不崩溃）。

输出 JSON schema（sidecar，不进 spec）：
  [
    {
      "shot_id": 1,
      "start_sec": 0.0,
      "end_sec": 6.73,
      "duration": 6.73,
      "prompt": "calm male vocal narration, \"爸爸去哪儿？\", moderate warm mid-range bed",
      "facets": {
        "dominant_type": "dialogue",
        "tempo_bpm": null,
        "brightness": "warm mid-range",
        "loudness": "moderate",
        "vocal_presence": 0.9655,
        "dialogue_excerpt": "爸爸去哪儿？"
      }
    }
  ]

确定性：相同输入两次运行产出 byte-identical 的 audio_prompts.json（不写
时间戳、不写绝对路径、字典遍历按固定 key 序）。

CLI 用法：
  python3 audio/gen_audio_prompts.py --episode-dir output/<ep-name>/
  python3 audio/gen_audio_prompts.py --episode-dir output/<ep-name>/ \\
      --output /tmp/custom.json
"""
import argparse
import json
import os
import sys
import wave
from pathlib import Path

import numpy as np

# ===== 可调阈值常量（spot-check 后可改；改动只影响输出文本，不影响合约） =====
LOUDNESS_QUIET_THRESHOLD = 0.02       # overall_rms < 此值 → "quiet"
LOUDNESS_MODERATE_THRESHOLD = 0.08    # overall_rms < 此值 → "moderate"，否则 "loud"
BRIGHTNESS_DEEP_THRESHOLD = 400       # spectral_centroid_hz < 此值 → "deep low rumble"
BRIGHTNESS_WARM_THRESHOLD = 1500      # < 此值（且 ≥ deep）→ "warm mid-range"，否则 "bright airy"
DRUM_RATIO_TEMPO_THRESHOLD = 0.10     # ratios.drums ≥ 此值才估 tempo
TEMPO_MIN_ONSETS = 3                  # onset 数 < 此值视为不置信 → bpm=None
TEMPO_ONSET_HOP = 512                 # envelope hop（samples）
TEMPO_ONSET_WIN = 1024                # envelope win（samples）
TEMPO_DEBOUNCE_SEC = 0.20             # onset 防抖最小间距（秒）
TEMPO_MIN_BPM = 40                    # bpm clamp 下界
TEMPO_MAX_BPM = 200                   # bpm clamp 上界
DIALOGUE_EXCERPT_MAX_CHARS = 20       # 对白摘录最大字符数（中文按字符算）
VOCAL_PRESENCE_HIGH = 0.70            # vocal_presence ≥ 此值视为高（用于 dialogue leading）
SC_HIGH_CENTROID_HZ = 2500.0          # dialogue 降级路径（无 transcript）频谱重心高低分界


def load_audio_stem(path: str):
    """读取 wav 文件，返回 (mono float32 numpy, sample_rate)。

    镜像 audio/separate_stems.py:77-88 既有范式（stdlib wave + numpy
    int16→float32 + 双声道均值），保持项目一致性。
    """
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
    return audio, sr


def estimate_tempo_from_envelope(audio, sr, start_sec, end_sec):
    """从 drum stem envelope peak-pick 估 tempo。

    参数：
        audio: drum stem 的 mono float32 numpy 数组（全曲）
        sr: 采样率
        start_sec / end_sec: 该 shot 的时段（秒）

    返回：
        (bpm_or_None, onset_count)
        - onset_count < TEMPO_MIN_ONSETS 时 bpm 为 None
        - 否则 bpm = round(60 / median_interval)，clamp 到 [40, 200]
    """
    s = max(0, min(int(start_sec * sr), len(audio)))
    e = max(s, min(int(end_sec * sr), len(audio)))
    if e - s < TEMPO_ONSET_WIN:
        return None, 0
    seg = audio[s:e]
    # 短窗 RMS envelope
    n_hops = max(0, (len(seg) - TEMPO_ONSET_WIN) // TEMPO_ONSET_HOP + 1)
    if n_hops <= 1:
        return None, 0
    envelope = np.empty(n_hops, dtype=np.float32)
    for i in range(n_hops):
        off = i * TEMPO_ONSET_HOP
        win = seg[off:off + TEMPO_ONSET_WIN]
        envelope[i] = np.sqrt(np.mean(win ** 2) + 1e-10)
    # 自适应阈值
    thr = float(envelope.mean() + 0.5 * envelope.std())
    # peak-pick：高于阈值 + 局部极大（高于左右各 1 邻居）+ 与上一个 onset ≥ 0.20s
    min_hop_gap = max(1, int(TEMPO_DEBOUNCE_SEC * sr / TEMPO_ONSET_HOP))
    onset_indices = []
    last_onset_idx = -min_hop_gap - 1
    for i in range(1, len(envelope) - 1):
        v = envelope[i]
        if v < thr:
            continue
        if not (v > envelope[i - 1] and v >= envelope[i + 1]):
            continue
        if i - last_onset_idx < min_hop_gap:
            continue
        onset_indices.append(i)
        last_onset_idx = i
    onset_count = len(onset_indices)
    if onset_count < TEMPO_MIN_ONSETS:
        return None, onset_count
    # 相邻 onset 间隔中位数 → bpm
    intervals_sec = []
    for a, b in zip(onset_indices[:-1], onset_indices[1:]):
        intervals_sec.append((b - a) * TEMPO_ONSET_HOP / sr)
    if not intervals_sec:
        return None, onset_count
    median_interval = float(np.median(intervals_sec))
    if median_interval <= 0:
        return None, onset_count
    bpm = 60.0 / median_interval
    bpm = max(TEMPO_MIN_BPM, min(TEMPO_MAX_BPM, int(round(bpm))))
    return bpm, onset_count


def brightness_word(hz: float) -> str:
    """频谱重心 → 亮度词（D3 指导）。"""
    if hz < BRIGHTNESS_DEEP_THRESHOLD:
        return "deep low rumble"
    if hz < BRIGHTNESS_WARM_THRESHOLD:
        return "warm mid-range"
    return "bright airy"


def loudness_word(rms_energy: float) -> str:
    """整体 RMS（shot 内四 stem 能量和）→ 响度词。"""
    if rms_energy < LOUDNESS_QUIET_THRESHOLD:
        return "quiet"
    if rms_energy < LOUDNESS_MODERATE_THRESHOLD:
        return "moderate"
    return "loud"


def leading_phrase(dominant_type: str, brightness: str,
                   vocal_presence: float) -> str:
    """由 dominant_type + brightness + vocal_presence 决定 leading phrase。

    返回确定性（同输入 → 同短语）。dialogue 降级路径（无 transcript 时）由
    derive_facets_and_prompt 在调用后按频谱重心覆盖。
    """
    if dominant_type == "dialogue":
        if vocal_presence >= VOCAL_PRESENCE_HIGH:
            return "clear lead vocal, calm male vocal narration"
        return "calm male vocal narration"
    if dominant_type == "bgm":
        return f"{brightness} instrumental bed"
    if dominant_type == "sfx":
        return f"textural {brightness} effect"
    if dominant_type == "mixed":
        return f"blended {brightness} bed with vocals"
    # 兜底（理论不会走到，dominant_type 限定四值之一）
    return f"{brightness} bed"


def find_dialogue_excerpt(transcript_segments, start_sec: float,
                          end_sec: float,
                          max_chars: int = DIALOGUE_EXCERPT_MAX_CHARS) -> str:
    """找首个与 [start_sec, end_sec) 重叠的 segment，取前 max_chars 字符。

    引号转义防止破坏 JSON / 注入未预期字符到 prompt 字符串（T-afz-02 mitigate）。
    无匹配或 transcript_segments 为 None 时返回空串。
    """
    if not transcript_segments:
        return ""
    for seg in transcript_segments:
        seg_start = seg.get("start", 0.0)
        seg_end = seg.get("end", 0.0)
        if seg_start < end_sec and seg_end > start_sec:
            text = (seg.get("text") or "").strip()
            excerpt = text[:max_chars]
            return excerpt.replace('"', '\\"')
    return ""


def compose_prompt(leading: str, tempo_bpm, dialogue_excerpt: str,
                   loudness: str, brightness: str) -> str:
    """按序拼接 prompt。

    顺序：{leading}[ ~Xbpm][, "excerpt"], {loudness} {brightness} bed
    无 tempo 不出现 bpm 片段；无对白不出现引号片段。
    """
    out = leading
    if tempo_bpm is not None:
        out += f" ~{tempo_bpm}bpm"
    if dialogue_excerpt:
        out += f", \"{dialogue_excerpt}\""
    out += f", {loudness} {brightness} bed"
    return out


def derive_facets_and_prompt(shot: dict, drum_audio, drum_sr: int,
                             transcript_segments) -> dict:
    """从单个 shot 的特征 + drum stem + transcript 派生 prompt + facets。"""
    dominant_type = shot["dominant_type"]
    energies = shot["energies"]
    ratios = shot["ratios"]
    spectral_centroid = shot["spectral_centroid"]

    overall_rms = float(sum(energies.values()))
    loudness = loudness_word(overall_rms)

    # dominant_stem 与 brightness 推导
    if dominant_type == "bgm":
        dominant_stem = "drums" if energies.get("drums", 0.0) >= energies.get("bass", 0.0) else "bass"
        brightness = brightness_word(float(spectral_centroid.get(dominant_stem, 0.0)))
    elif dominant_type == "sfx":
        dominant_stem = "other"
        brightness = brightness_word(float(spectral_centroid.get("other", 0.0)))
    elif dominant_type == "mixed":
        # 四 stem 频谱按能量加权平均
        total_e = sum(energies.values()) + 1e-10
        weighted_hz = sum(energies.get(k, 0.0) * spectral_centroid.get(k, 0.0)
                          for k in ("vocals", "drums", "bass", "other")) / total_e
        brightness = brightness_word(float(weighted_hz))
    else:  # dialogue（及其它未知值兜底用 vocals）
        dominant_stem = "vocals"
        brightness = brightness_word(float(spectral_centroid.get("vocals", 0.0)))

    vocal_presence = float(ratios.get("vocals", 0.0))

    # tempo：仅当 drum stem 可读且 drums ratio 充分
    if drum_audio is not None and ratios.get("drums", 0.0) >= DRUM_RATIO_TEMPO_THRESHOLD:
        tempo_bpm, _onset_count = estimate_tempo_from_envelope(
            drum_audio, drum_sr, shot["start_sec"], shot["end_sec"])
    else:
        tempo_bpm = None

    # dialogue_excerpt（transcript_segments 为 None 时直接空串）
    dialogue_excerpt = find_dialogue_excerpt(
        transcript_segments, shot["start_sec"], shot["end_sec"])

    # leading phrase（dialogue + 无 transcript 时按频谱重心降级覆盖）
    leading = leading_phrase(dominant_type, brightness, vocal_presence)
    if dominant_type == "dialogue" and transcript_segments is None:
        vocals_sc = float(spectral_centroid.get("vocals", 0.0))
        if vocals_sc >= SC_HIGH_CENTROID_HZ:
            leading = "non-vocal melodic vocalise"
        else:
            leading = "vocal texture"

    prompt = compose_prompt(leading, tempo_bpm, dialogue_excerpt, loudness, brightness)

    return {
        "shot_id": shot["shot_id"],
        "start_sec": round(shot["start_sec"], 4),
        "end_sec": round(shot["end_sec"], 4),
        "duration": round(shot["duration"], 4),
        "prompt": prompt,
        "facets": {
            "dominant_type": dominant_type,
            "tempo_bpm": tempo_bpm,
            "brightness": brightness,
            "loudness": loudness,
            "vocal_presence": round(vocal_presence, 4),
            "dialogue_excerpt": dialogue_excerpt,
        },
    }


def gen_prompts(episode_dir: str, output_path: str):
    """对 episode_dir 下所有 shot 生成 prompt，写出 audio_prompts.json。"""
    episode_dir = str(Path(episode_dir))
    print(f"[stage] gen_audio_prompts — episode_dir={episode_dir}")

    shots_path = os.path.join(episode_dir, "shots.json")
    audio_analysis_path = os.path.join(episode_dir, "audio_analysis.json")
    transcript_path = os.path.join(episode_dir, "transcript.json")

    if not os.path.exists(shots_path):
        sys.exit(f"[stage] shots.json not found: {shots_path}")
    if not os.path.exists(audio_analysis_path):
        sys.exit(f"[stage] audio_analysis.json not found: {audio_analysis_path}")

    with open(shots_path) as f:
        shots_meta = json.load(f)
    with open(audio_analysis_path) as f:
        audio_analysis = json.load(f)

    # 按 shot_id 建索引字典（实测数组是顺序的，但不假设）
    analysis_by_id = {s["shot_id"]: s for s in audio_analysis.get("shots", [])}

    # transcript.json 缺失 → 降级路径 A
    if os.path.exists(transcript_path):
        with open(transcript_path) as f:
            transcript_segments = json.load(f).get("segments")
        print(f"[stage] transcript loaded ({len(transcript_segments or [])} segments)")
    else:
        print("[stage] no transcript.json — degrading (dialogue_excerpt will be empty)")
        transcript_segments = None

    # stem 目录解析兜底（镜像 separate_stems.py:67-73）
    ep_name = os.path.basename(episode_dir)
    drums_path_primary = os.path.join(episode_dir, "stems", "htdemucs", ep_name, "drums.wav")
    drums_path_secondary = os.path.join(episode_dir, "stems", "drums.wav")
    drum_audio = None
    drum_sr = 0
    if os.path.exists(drums_path_primary):
        drums_path = drums_path_primary
    elif os.path.exists(drums_path_secondary):
        drums_path = drums_path_secondary
    else:
        drums_path = None
    if drums_path is not None:
        try:
            drum_audio, drum_sr = load_audio_stem(drums_path)
            print(f"[stage] drums loaded ({len(drum_audio) / drum_sr:.1f}s, sr={drum_sr})")
        except Exception as e:
            print(f"[stage] stems not found — degrading (tempo will be null) [{e}]")
            drum_audio = None
    else:
        print("[stage] stems not found — degrading (tempo will be null)")

    out = []
    n_with_bpm = 0
    n_with_dialogue = 0
    for i, shot_meta in enumerate(shots_meta):
        shot_id = shot_meta["id"]
        analysis = analysis_by_id.get(shot_id)
        if analysis is None:
            sys.exit(f"[stage] shot_id={shot_id} not in audio_analysis.json — aborting")
        entry = derive_facets_and_prompt(
            analysis, drum_audio, drum_sr, transcript_segments)
        if entry["facets"]["tempo_bpm"] is not None:
            n_with_bpm += 1
        if entry["facets"]["dialogue_excerpt"]:
            n_with_dialogue += 1
        out.append(entry)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(shots_meta)}")

    print(f"[stage] stats: bpm-coverage={n_with_bpm}/{len(out)}, "
          f"with-dialogue={n_with_dialogue}/{len(out)}")

    with open(output_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="为每镜生成 audio-gen 风格 NL prompt（spike，sidecar 输出，不进 spec/pipeline）")
    ap.add_argument("--episode-dir", required=True,
                    help="episode 输出目录（包含 shots.json + audio_analysis.json）")
    ap.add_argument("--output", default=None,
                    help="输出 JSON 路径（默认 <episode-dir>/audio_prompts.json）")
    args = ap.parse_args()

    output = args.output or os.path.join(args.episode_dir, "audio_prompts.json")
    out = gen_prompts(args.episode_dir, output)
    print(f"[stage] wrote {len(out)} shot prompts → {output}")
    print("sidecar spike — NOT referenced by spec/asset.json (per D4)")


if __name__ == "__main__":
    main()
