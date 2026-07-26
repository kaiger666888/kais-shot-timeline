#!/usr/bin/env python3
"""每镜分层复现 prompt producer（v1.2 Phase 15 —— quick task 260725-afz spike 晋升版）

本模块在 v1.2 Phase 15 中由 quick-task spike（sidecar 实验脚本，产 NL prompt
数组到 episode 目录）
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

# ===== 可调阈值常量（composer + 既有 helper 共用；UPPER_CASE per CLAUDE.md） =====
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

    # 决策：是否 emit music_gen —— Plan 15-01 Task 1 spec lock：emit triggers are
    # BGM presence OR tempo BPM available. Mood alone is a MODIFIER, not a trigger
    # （dialogue.emotion 在没有 BGM/tempo 时不构成音乐证据 —— 否则会对纯对白
    # shot over-claim 音乐复现）。
    if not bgm_present and tempo_bpm is None:
        return None

    # confidence（SPEC §10.2 music-gen 60-75% central estimate calibrated）
    confidence = MUSIC_GEN_CONFIDENCE_BASE
    if tempo_bpm is not None:
        confidence += MUSIC_GEN_CONFIDENCE_TEMPO_STEP
    if mood_word is not None:
        confidence += MUSIC_GEN_CONFIDENCE_MOOD_STEP
    confidence = max(0.0, min(1.0, confidence))

    # NL 拼接（确定性 —— 不 emit 任何乐器名词；T-15-02 mitigation）
    # 注：到此处 bgm_present 或 tempo_bpm 至少一个非 None（前面 early-return 保证）
    parts = []
    if mood_word:
        parts.append(mood_word)
    if bgm_present and tempo_bpm is not None:
        parts.append("rhythmic instrumental bed")
        parts.append(f"~{tempo_bpm}bpm")
    elif bgm_present:
        parts.append("instrumental bed (BGM detected)")
    else:   # tempo_bpm is not None, bgm_present is False
        parts.append(f"rhythmic bed ~{tempo_bpm}bpm")
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
# Phase 15-02 Task 1: --recompose CLI mode (spike retirement, locked decision #6)
# ============================================================================
# quick task 260725-afz 的旧 sidecar spike CLI 行为（扫描 episode 目录、产
# NL prompt 数组 sidecar）已 RETIRE。新 CLI 入口是 --recompose：离线
# in-place recompose 已有 audio_semantic.json#shots[].reproduction。Plan 15-02
# SC#6 byte-identical determinism proof 的目标对象。library 入口
# compose_reproduction 仍由 analysis/call_audio_analysis.py 内联调用
# （producer hot path）。


def recompose_audio_semantic(input_path: str,
                             output_path: str | None = None,
                             audio_analysis_json: str | None = None,
                             schema_path: str | None = None) -> dict:
    """离线 in-place recompose audio_semantic.json#shots[].reproduction。

    读取现有 audio_semantic.json + 可选 audio_analysis.json side input，对每个
    shot invoke compose_reproduction 写回 reproduction 层，atomic 重写。

    Pure given file contents（无 RNG、无时间戳、无绝对路径嵌入输出）—— 相同
    输入 → byte-identical 输出（mirror v1.1 Pattern 2 deterministic recompose；
    SC#6 load-bearing）。

    Args:
        input_path: 待 recompose 的 audio_semantic.json 路径（REQUIRED）。
        output_path: 输出路径（默认 = input_path；in-place 重写）。当传入与
            input_path 不同的路径时，可用于 dry-run / 测试。
        audio_analysis_json: 可选 audio_analysis.json side input（per-shot
            Demucs 频谱/能量）。提供时 composer 用其 drums ratio 估 tempo；
            缺席时 music_gen 降级为 BGM/mood 信号 only。
        schema_path: 可选 schema 路径（默认仓库 spec/schemas/
            audio_semantic.schema.json）。写前 Draft202012Validator 自校验。

    Returns:
        Recomposed payload dict（同时写到 output_path）。

    Raises:
        SystemExit on schema validation failure（mirror call_audio_analysis.py
        801-804 fail-loud 惯例）。
    """
    if output_path is None:
        output_path = input_path
    if schema_path is None:
        schema_path = str(Path(__file__).resolve().parent.parent
                          / "spec" / "schemas" / "audio_semantic.schema.json")

    # 1. Load existing audio_semantic.json
    with open(input_path, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        sys.exit(f"[recompose] {input_path} root must be object, got "
                 f"{type(payload).__name__}")
    shots = payload.get("shots")
    if not isinstance(shots, list):
        sys.exit(f"[recompose] {input_path}#shots must be array, got "
                 f"{type(shots).__name__ if shots is not None else 'absent'}")

    # 2. Optional side input
    analysis_by_id: dict = {}
    if audio_analysis_json and os.path.exists(audio_analysis_json):
        try:
            with open(audio_analysis_json, encoding="utf-8") as f:
                aan = json.load(f)
            if isinstance(aan, dict) and isinstance(aan.get("shots"), list):
                analysis_by_id = {
                    s["shot_id"]: s for s in aan["shots"]
                    if isinstance(s, dict) and isinstance(s.get("shot_id"), int)}
        except (OSError, json.JSONDecodeError) as e:
            print(f"[recompose] warning: audio_analysis.json load failed ({e}); "
                  f"composer degraded to no-side-input mode")

    # 3. Per-shot: replace ONLY shots[i].reproduction (preserve everything else
    #    —— T-15-07 mitigation: schema_version / word_level_experimental /
    #    shots[i].dialogue / shots[i].sfx / timing 全部 verbatim 保留).
    #    CONTRACT-05 preservation: 仅当 ≥1 layer 非 null 才 emit reproduction key
    #    —— 全 null 时 OMIT 整个子对象（mirror call_audio_analysis.py 行为；
    #    防 recompose 写出空 reproduction 后被下游误判为 "有数据"）。
    n_tts = n_music = n_foley = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue   # defensive —— skip malformed entry
        sid = shot.get("shot_id")
        analysis_shot = analysis_by_id.get(sid) if isinstance(sid, int) else None
        repro = compose_reproduction(shot, analysis_shot=analysis_shot)
        if isinstance(repro, dict) and any(
                repro.get(k) is not None for k in ("tts", "music_gen", "foley")):
            shot["reproduction"] = repro    # overwrite; preserves all other keys
        else:
            shot.pop("reproduction", None)
        if repro.get("tts"):
            n_tts += 1
        if repro.get("music_gen"):
            n_music += 1
        if repro.get("foley"):
            n_foley += 1

    # 4. Pre-write schema validation (T-15-07 defense-in-depth)
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        jsonschema = None
        print("[recompose] warning: jsonschema not installed; "
              "skipping pre-write schema validation (defense-in-depth skipped)")
    else:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        if errors:
            sys.exit(
                f"[recompose] schema validation failed ({len(errors)} errors): "
                + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                            for e in errors[:3]))

    # 5. Atomic write: temp + os.replace (T-15-06 mitigation —— 防 partial-write
    #    被下游读到)
    tmp = output_path + ".tmp"
    try:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            # ensure_ascii=False + indent=2 mirror call_audio_analysis.py:810
            # + spec fixture format —— 字节级稳定。
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, output_path)
    except OSError as e:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        sys.exit(f"[recompose] atomic write failed: {e}")

    print(f"[recompose] updated {len(shots)} shots reproduction "
          f"(tts={n_tts}, music_gen={n_music}, foley={n_foley}) → {output_path}")
    return payload


def main():
    """CLI entry —— --recompose mode (locked decision #6 spike retirement)."""
    ap = argparse.ArgumentParser(
        description="离线 recompose audio_semantic.json#shots[].reproduction "
                    "（Phase 15 producer；locked decision #6 spike 退休）")
    ap.add_argument("--recompose", required=True, metavar="AUDIO_SEMANTIC_JSON",
                    help="待 recompose 的 audio_semantic.json 路径"
                         "（in-place 重写 reproduction 层）")
    ap.add_argument("--audio-analysis-json", default=None,
                    help="audio_analysis.json side input（per-shot Demucs 频谱/能量；"
                         "提供时 composer 用其 drums ratio 估 tempo；"
                         "缺席时 music_gen 降级）")
    ap.add_argument("--schema", default=None,
                    help="audio_semantic.schema.json 路径"
                         "（默认仓库 spec/schemas/audio_semantic.schema.json）")
    args = ap.parse_args()

    recompose_audio_semantic(
        input_path=args.recompose,
        audio_analysis_json=args.audio_analysis_json,
        schema_path=args.schema)


if __name__ == "__main__":
    main()
