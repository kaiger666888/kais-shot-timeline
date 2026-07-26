#!/usr/bin/env python3
"""每镜分层复现 prompt producer（v1.2 Phase 15 —— quick task 260725-afz spike 晋升版）

本模块在 v1.2 Phase 15 中由 quick-task spike（sidecar audio_prompts.json 实验脚本）
**晋升为 pipeline producer**（locked decision #6 spike 退休）：把 audio_semantic.json
的单镜 normalized shot（dialogue/sfx modality）+ 可选 audio_analysis.json 频谱 side
input 组合成 model-agnostic NL 复现 prompt，写到 audio_semantic.json#shots[].reproduction
。**不内嵌 NC 权重**（locked decision #7）—— 仅 NL 文本。

两个入口点：

  (1) **library function `compose_reproduction(shot, analysis_shot=None)`** ——
      被 analysis/call_audio_analysis.py 在每镜 normalize 之后、写盘之前调用。
      Pure function（无 I/O、无 RNG、无时间戳）—— 相同输入 byte-identical 输出
      （mirror v1.1 Pattern 2 deterministic recompose）。

  (2) **CLI `--recompose <audio_semantic.json>`** —— 操作员在路由 round-trip 完成后
      离线迭代复现 prompt 组合：读现有 audio_semantic.json + 可选 audio_analysis.json
      side input → 每镜 invoke compose_reproduction → in-place atomic 重写。Plan 15-02
      owns this CLI；Plan 15-01 仅建立 library function。

输出形态（spec/schemas/audio_semantic.schema.json#$defs/repro_prompt LOCKED）：

  shots[i].reproduction = {
      "tts":       {"text": str(≥1), "confidence": 0..1,
                    "fidelity_disclaimer": str(SPEC §10 lock)} | null,
      "music_gen": {...} | null,
      "foley":     {...} | null
  }

每非 null 层都带 SPEC §10 LOCKED 的 fidelity_disclaimer literal ——
  - tts:        "TTS ~70% similarity to source voice (AF-01 mitigation)"
  - music_gen:  "music-gen ~60-75% harmonic/rhythmic similarity; timbre not guaranteed (AF-01 mitigation)"
  - foley:      "foley ~80% similarity for defined event types (AF-01 mitigation)"
**绝不**出现绝对化复现措辞（SPEC §10.1 称为「绝对化复现措辞」的统称 —— 中英文
均禁止；AF-01 grep 守门；Phase 11 SC#5 lock）。

CONDITIONAL 字段 gating（Phase 10 spike LOCKED outcomes）：
  - DIA-04 emotion ship-nullable+confidence —— emotion 进入 TTS prompt 词缀（nullable）
  - DIA-05 word-level ship-experimental —— composer NEVER 读 dialogue.words[]；仅
    用 dialogue.text（segment-level）。word_level_experimental flag 由 call_audio_analysis
    顶层管理（ROUTE 侧 WhisperX 是否上线）。
  - MUS-04 乐器识别 DEFER v1.3 —— composer NEVER emit 任何乐器相关字段或乐器名词；
    music_gen bed 描述仅用 generic NL 词（"rhythmic bed"/"instrumental bed"）。

确定性：相同输入 → byte-identical 输出。无时间戳、无绝对路径、dict key 固定序
（Python 3.7+ insertion-order）、set-derived list 走 sorted()、float 走 round(x, 4)。
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


# ============================================================================
# Phase 15 reproduction composer（locked decision #6 spike 晋升）
# ============================================================================
# SPEC §10 LOCKED fidelity_disclaimer literals —— 每个 non-null repro_prompt
# layer 必须 emit 对应字面量；**禁止**改写或省略 (AF-01 mitigation)。
FIDELITY_DISCLAIMER_TTS = (
    "TTS ~70% similarity to source voice (AF-01 mitigation)")
FIDELITY_DISCLAIMER_MUSIC_GEN = (
    "music-gen ~60-75% harmonic/rhythmic similarity; "
    "timbre not guaranteed (AF-01 mitigation)")
FIDELITY_DISCLAIMER_FOLEY = (
    "foley ~80% similarity for defined event types (AF-01 mitigation)")

# DIA-04 emotion → TTS 语气词缀（5 类；闭枚举会 over-claim 校准 —— SenseVoice
# self_consistency=100% 是 label-stability 代理，NOT 精度。任何 emotion 落在
# 表外 → 不加语气词缀（中性 TTS 描述）。Phase 10 spike LOCKED。）
EMOTION_TONE_MAP = {
    "HAPPY":   "开心愉悦",
    "SAD":     "低落伤感",
    "ANGRY":   "激动愤怒",
    "NEUTRAL": "平稳中性",
    # emo_unk 与表外值 → 不加语气词缀（emitted "中性" by default in text）
}

# MUS-03 emotion → music_gen mood 形容词（与 EMOTION_TONE_MAP 同源；英文
# 形容词用于 music_gen prompt 因 music-gen 模型训练语料以英文为主）。
MOOD_MAP = {
    "HAPPY":   "upbeat",
    "SAD":     "melancholic",
    "ANGRY":   "tense",
    "NEUTRAL": "mellow",
    # emo_unk 与表外值 → 不加 mood 词缀
}

# SFX-01 SenseVoice 8-event 非语音子集 → 中文标签（用于 foley prompt 词缀）。
# Speech 不在此（Speech 属于 dialogue.events）。
EVENT_CN_MAP = {
    "Applause": "掌声",
    "Laughter": "笑声",
    "Cry":      "哭声",
    "Sneeze":   "喷嚏",
    "Breath":   "呼吸声",
    "Cough":    "咳嗽声",
}

# composer 数值常量
TTS_CONFIDENCE_BASE = 0.65        # dialogue.text 存在但 emotion 缺席时的基线
TTS_CONFIDENCE_EMOTION_STEP = 0.20  # emotion_confidence=1.0 时的增量
TTS_CONFIDENCE_DEFAULT_EMOTION = 0.5  # emotion 缺席时使用的代理 emotion_confidence
TTS_TEXT_MAX_CHARS = 40           # dialogue.text 截断阈值（中文按字符）

MUSIC_GEN_CONFIDENCE_BASE = 0.55  # music_gen 基线（SPEC §10.2 music-gen 60-75%）
MUSIC_GEN_CONFIDENCE_TEMPO_STEP = 0.15  # tempo 可推导时增量
MUSIC_GEN_CONFIDENCE_MOOD_STEP = 0.05   # mood 可推导时增量

FOLEY_CONFIDENCE_WITH_DESC = 0.80  # SPEC §10.2 foley ~80% central estimate
FOLEY_CONFIDENCE_EVENTS_ONLY = 0.70  # 仅 events[] 时（标签，无 NL 描述）


def _compose_tts_layer(dialogue: dict | None) -> dict | None:
    """TTS 复现 prompt layer（DIA-01 段级文本 + DIA-04 emotion nullable+confidence）。

    DIA-05 word-level：本函数 NEVER 读 dialogue.words[] —— word_level_experimental
    顶层 flag 由 call_audio_analysis.py 管理；composer 是 segment-level only（T-15-04）。

    Returns:
        {"text": str(non-empty), "confidence": float[0,1],
         "fidelity_disclaimer": FIDELITY_DISCLAIMER_TTS}
        或 None（dialogue 缺席 OR text 为空）。
    """
    if not isinstance(dialogue, dict):
        return None
    text = dialogue.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()

    # 拼 TTS NL prompt —— 段级文本（截断）+ 语气词缀 + 语言固定（CONTEXT D-XX zh 锁定）
    excerpt = text[:TTS_TEXT_MAX_CHARS]
    emotion = dialogue.get("emotion")
    emotion_confidence = dialogue.get("emotion_confidence")
    # confidence 计算（SPEC §10.2 TTS ~70% central estimate calibrated）
    if isinstance(emotion_confidence, (int, float)):
        ec = max(0.0, min(1.0, float(emotion_confidence)))
    elif emotion is not None:
        ec = TTS_CONFIDENCE_DEFAULT_EMOTION   # emotion 存在但 confidence 缺席
    else:
        ec = 0.0                                # 无 emotion → 基线
    confidence = max(0.0, min(1.0,
        TTS_CONFIDENCE_BASE + TTS_CONFIDENCE_EMOTION_STEP * ec))

    # NL 拼接（确定性 —— 按固定序；无 RNG）
    parts = ["再说一遍段级文本：", f"「{excerpt}」"]
    if isinstance(emotion, str) and emotion in EMOTION_TONE_MAP:
        parts.append(f"，语气{EMOTION_TONE_MAP[emotion]}")
    parts.append("，中文普通话，节奏自然")
    return {
        "text": "".join(parts),
        "confidence": round(confidence, 4),
        "fidelity_disclaimer": FIDELITY_DISCLAIMER_TTS,
    }


def _compose_music_gen_layer(shot_semantic: dict,
                             analysis_shot: dict | None,
                             drum_audio=None,
                             drum_sr: int = 0) -> dict | None:
    """music_gen 复现 prompt layer。

    Source signals:
      - MUS-01 BGM presence（dialogue.events OR sfx.events 含 "BGM" SenseVoice tag）
      - MUS-02 tempo BPM（analysis_shot.ratios.drums ≥ DRUM_RATIO_TEMPO_THRESHOLD 且
        drum_audio 可读 → spike's estimate_tempo_from_envelope；onset < 3 → null）
      - MUS-03 mood（shot.dialogue.emotion via MOOD_MAP；emotion 缺席 → 无 mood 词缀）
      - MUS-05 key / MUS-06 VA：v1.2 路由不产信号 → 始终 null（differentiator-populated-
        when-route-produces-signal is null-by-default）
      - MUS-04 乐器：v1.3 deferred → NEVER emit 任何乐器字段或乐器名词
        （T-15-02 mitigation；NL bed 描述仅用 generic 词）

    Returns:
        {"text": str, "confidence": float[0,1],
         "fidelity_disclaimer": FIDELITY_DISCLAIMER_MUSIC_GEN}
        或 None（无 BGM 信号 AND 无 tempo AND 无 mood）。
    """
    if not isinstance(shot_semantic, dict):
        return None

    # MUS-01 BGM presence（SenseVoice 8-event 的 "BGM" tag —— 可能在 dialogue.events
    # 或 sfx.events 任一处出现；SenseVoice 的 BGM tag 是 BGM 存在检测的强信号）
    bgm_present = False
    dlg = shot_semantic.get("dialogue")
    if isinstance(dlg, dict):
        evts = dlg.get("events")
        if isinstance(evts, list) and "BGM" in evts:
            bgm_present = True
    if not bgm_present:
        sfx = shot_semantic.get("sfx")
        if isinstance(sfx, dict):
            evts = sfx.get("events")
            if isinstance(evts, list) and "BGM" in evts:
                bgm_present = True

    # MUS-02 tempo（仅当 audio_analysis.json side input 提供 drums ratio + drum_audio）
    tempo_bpm = None
    if (isinstance(analysis_shot, dict)
            and drum_audio is not None and drum_sr > 0):
        ratios = analysis_shot.get("ratios")
        if isinstance(ratios, dict) and isinstance(ratios.get("drums"), (int, float)):
            if float(ratios["drums"]) >= DRUM_RATIO_TEMPO_THRESHOLD:
                try:
                    tempo_bpm, _onset_count = estimate_tempo_from_envelope(
                        drum_audio, drum_sr,
                        float(shot_semantic.get("start_sec", 0.0)),
                        float(shot_semantic.get("end_sec", 0.0)))
                except Exception:
                    tempo_bpm = None   # defense-in-depth

    # MUS-03 mood（emotion via MOOD_MAP；表外值 → 无词缀）
    mood_word = None
    if isinstance(dlg, dict):
        emotion = dlg.get("emotion")
        if isinstance(emotion, str) and emotion in MOOD_MAP:
            mood_word = MOOD_MAP[emotion]

    # 决策：是否 emit music_gen（任一信号源存在即 emit）
    if not bgm_present and tempo_bpm is None and mood_word is None:
        return None

    # confidence（SPEC §10.2 music-gen 60-75% central estimate calibrated）
    confidence = MUSIC_GEN_CONFIDENCE_BASE
    if tempo_bpm is not None:
        confidence += MUSIC_GEN_CONFIDENCE_TEMPO_STEP
    if mood_word is not None:
        confidence += MUSIC_GEN_CONFIDENCE_MOOD_STEP
    confidence = max(0.0, min(1.0, confidence))

    # NL 拼接（确定性 —— 不 emit 任何乐器名词；T-15-02 mitigation）
    parts = []
    if mood_word:
        parts.append(mood_word)
    if bgm_present and tempo_bpm is not None:
        parts.append("rhythmic instrumental bed")
        parts.append(f"~{tempo_bpm}bpm")
    elif bgm_present:
        parts.append("instrumental bed (BGM detected)")
    elif tempo_bpm is not None:
        parts.append(f"rhythmic bed ~{tempo_bpm}bpm")
    else:
        # 仅 mood 可推导（dialogue.emotion non-null 但无 BGM/tempo）——
        # emit minimal "{mood} ambient bed"，confidence 最低
        parts.append("ambient bed")
    return {
        "text": " ".join(parts),
        "confidence": round(confidence, 4),
        "fidelity_disclaimer": FIDELITY_DISCLAIMER_MUSIC_GEN,
    }


def _compose_foley_layer(sfx: dict | None) -> dict | None:
    """foley 复现 prompt layer。

    Source signals:
      - SFX-01 sfx.description NL（verbatim pass-through）+ sfx.events（SenseVoice
        8-event 非语音子集，转 EVENT_CN_MAP 中文标签拼 [笑声, 掌声] 词缀）
      - SFX-02 AudioSet timestamps / SFX-03 foley complex events：v1.3 deferred → null

    Returns:
        {"text": str, "confidence": float[0,1],
         "fidelity_disclaimer": FIDELITY_DISCLAIMER_FOLEY}
        或 None（sfx 缺席 OR (description 空 AND events 空)）。
    """
    if not isinstance(sfx, dict):
        return None
    description = sfx.get("description")
    if not isinstance(description, str):
        description = ""
    raw_events = sfx.get("events")
    events_cn = []
    if isinstance(raw_events, list):
        # 确定性：sorted（防 set order 不稳定）+ 仅 EVENT_CN_MAP 命中的中文标签
        for e in sorted(set(str(x) for x in raw_events if isinstance(x, str))):
            if e in EVENT_CN_MAP:
                events_cn.append(EVENT_CN_MAP[e])

    description = description.strip()
    if not description and not events_cn:
        return None

    # NL 拼装（确定性）
    if events_cn and description:
        text = f"[{', '.join(events_cn)}]: {description}"
        confidence = FOLEY_CONFIDENCE_WITH_DESC
    elif events_cn:
        text = f"[{', '.join(events_cn)}]"
        confidence = FOLEY_CONFIDENCE_EVENTS_ONLY
    else:
        text = description
        confidence = FOLEY_CONFIDENCE_WITH_DESC
    return {
        "text": text,
        "confidence": round(confidence, 4),
        "fidelity_disclaimer": FIDELITY_DISCLAIMER_FOLEY,
    }


def compose_reproduction(shot_semantic: dict,
                         analysis_shot: dict | None = None,
                         drum_audio=None,
                         drum_sr: int = 0) -> dict:
    """Per-shot reproduction composer（Phase 15 LOCKED producer entry point）。

    Pure function：无 I/O、无 RNG、无时间戳。相同输入 → byte-identical 输出
    （mirror v1.1 Pattern 2 deterministic recompose）。

    Args:
        shot_semantic: 单镜 normalized shot（output of call_audio_analysis.
            normalize_audio_semantic）—— 含 shot_id/start_sec/end_sec/duration
            + 可选 dialogue {text, spk_id, emotion, emotion_confidence, events,
            words} + 可选 sfx {events, description}。本函数 NEVER 读 dialogue.words
            （DIA-05 word-level gating —— T-15-04 mitigation；word_level_experimental
            flag 由 call_audio_analysis 顶层管理）。
        analysis_shot: 可选 audio_analysis.json#shots[i] side input —— 含 ratios/
            energies/spectral_centroid/dominant_type（Demucs 启发式特征）。composer
            用其 ratios.drums 决定是否估 tempo；缺席时 music_gen 降级。
        drum_audio: 可选 drums.wav mono numpy 数组（仅在 CLI --recompose 模式下
            提供，用于 spike's estimate_tempo_from_envelope）。producer 内联调用
            时传 None —— music_gen 不依赖 envelope 分析（只用 BGM/mood 信号）。
        drum_sr: drum_audio 的采样率；drum_audio=None 时忽略。

    Returns:
        dict shaped {"tts": repro_prompt | None,
                     "music_gen": repro_prompt | None,
                     "foley": repro_prompt | None}
        其中 repro_prompt = {"text": str(non-empty), "confidence": float[0,1],
                              "fidelity_disclaimer": str(SPEC §10 lock)}。
        各层 null 当对应模态无信号 —— schema 允许（#$defs/repro_prompt type
        是 ['object','null']）。
    """
    if not isinstance(shot_semantic, dict):
        return {"tts": None, "music_gen": None, "foley": None}
    dlg = shot_semantic.get("dialogue")
    sfx = shot_semantic.get("sfx")
    return {
        "tts":       _compose_tts_layer(dlg),
        "music_gen": _compose_music_gen_layer(shot_semantic, analysis_shot,
                                              drum_audio=drum_audio, drum_sr=drum_sr),
        "foley":     _compose_foley_layer(sfx),
    }


# ============================================================================
# SPIKE CLI (quick task 260725-afz) —— 在 Plan 15-02 Task 1 中退休。
# 新 pipeline 入口是上面的 compose_reproduction()，由 analysis/call_audio_analysis.py
# 在每镜 normalize 后 invoke。下面的 main()/gen_prompts()/derive_facets_and_prompt()
# 在本 commit 中保留以让文件可运行；15-02 用 --recompose 模式替换之。
# ============================================================================

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
