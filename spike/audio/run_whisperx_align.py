#!/usr/bin/env python3
"""Phase 10 DIA-05 WhisperX 对齐漂移 spike —— 一次性 throwaway 脚本。

⚠️ THROWAWAY 参考脚本，非 pipeline 代码。不要接进 run_pipeline.py 任何 step_*。

【运行方式 —— 必须用隔离 venv 的 python，不要用系统 python】
    /tmp/whisperx-spike-venv/bin/python spike/audio/run_whisperx_align.py [--smoke-only N]

【为什么隔离 venv】
    Pitfall 1 (10-RESEARCH.md §Pitfalls)：whisperx 3.8.6 的 setup.py 把 torch 依赖
    声明为 ``torch~=2.8.0``，默认会拉 CUDA 12.8 wheel，覆盖项目系统 torch 2.6.0+cu124
    （会污染 Demucs / Whisper / cv2 等所有依赖 torch 的脚本）。所以必须在
    /tmp/whisperx-spike-venv 隔离环境里安装 + 运行，系统 python 完全不碰。

【device_directive —— GPU hybrid 策略】
    本机 GPU 现已 UP（RTX 3060 Ti + RTX 3090，torch.cuda.is_available()==True）。
    CONTEXT.md 原把所有 spike 锁在 CPU（planning-time GPU DOWN），但该前提已失效。
    按 user directive 改成：
      - A1 smoke（1 段）：device="cpu" —— 验证 CPU 模式可用（BLOCKER-1 信号）。
      - Full drift run（30 段）：device="cuda:0" —— GPU 加速推理。
    A1 + full-run 的 device 字段分别独立记录在结果 JSON 的 ``a1_device`` /
    ``full_run_device``，audit trail 诚实。

【Pitfall 1 cu124-in-venv 经验】
    whisperx 3.8.6 metadata 声明 torch~=2.8.0，但实测在 torch 2.6.0+cu124
    + torchaudio 2.6.0+cu124 + torchvision 0.21.0+cu124 栈上**可以正常 import 与
    运行**（pip metadata warning 仅为 advisory，Python import 不强校验）。
    → 即 stay-on-12.4 路径在隔离 venv 里 TECHNICALLY FEASIBLE（需手动 force-pin
    cu124 三件套，因为 whisperx 依赖树默认拉 cu128 版本）。Plan 06 据此判 stay-on-12.4
    仍可行（whisperx 不强依赖 cu128 runtime，只是 pip 元数据声明）。

【methodology】
    - 读取 ep01 transcript.json 的 155 段 faster-whisper/openai-whisper segments（A2
      验证：whisperx.align 接受任意 segments，无需重新转录，避免 WER 噪声）。
    - stratified_sample(segments, n=30, seed=10) —— 与 SER/MIR 共享同 30 段
      （Pitfall 9 head-to-head integrity）。
    - whisperx.load_audio(vocals.wav) 16kHz mono；whisperx.load_align_model(
      language_code="zh", device=...) 加载 jonatasgrosman/wav2vec2-large-xlsr-53-
      chinese-zh-cn（whisperx.alignment.DEFAULT_ALIGN_MODELS_HF["zh"]，T-10-03 canonical）。
    - 逐段 whisperx.align([single_seg], ...)；drift 定义见 compute_drift_stats docstring。
    - drift_stats 跨 30 段聚合，pct_under_200_ms 是 DIA-05 ship/defer 的 gating 统计。

【Pitfall 6 / T-10-01 token 防泄露】
    所有异常路径经 ``_safe_error`` redact；HF_ENDPOINT 镜像在 import whisperx 之前
    setdefault。结果 JSON 落盘前再过一次 redact（common.write_result 已做）。
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

# ============================================================================
# HF 镜像 —— 必须在 ``import whisperx`` 之前设置（HF 被墙 → hf-mirror.com 可达）
# ============================================================================
# Pitfall: huggingface.co 本机不可达（curl 测 5s timeout）；hf-mirror.com 可达。
# wav2vec2-large-xlsr-53-chinese-zh-cn 是 public model，HF_TOKEN 已设但非必需。
# 在 os.environ 层 setdefault，使子进程 (whisperx 内部 hf_hub_download) 也继承。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import whisperx  # noqa: E402

# ============================================================================
# NLTK punkt_tab monkey-patch —— Rule 3 auto-fix（blocking issue）
# ============================================================================
# 问题：whisperx/alignment.py:192-195 在 nltk_load(punkt_tab/<lang>.pickle)
# LookupError 时调用 ``nltk.download('punkt_tab', quiet=True)``。本机
# raw.githubusercontent.com（NLTK 默认 CDN）对 binary 下载严重 stall（实测 60s+
# 无进展），导致 whisperx.align() 永久挂起。
#
# Rule 3 auto-fix：在 whisperx.align 之前 monkey-patch：
#   (a) ``nltk.download`` → 立即返回 False，不走网络。
#   (b) ``nltk.data.load`` 拦截 ``tokenizers/punkt_tab/*.pickle``，返回一个
#       stub sentence-tokenizer（整个 segment 视作单个 sentence）。
# 对齐场景下 sentence_spans 只用于切分长段文本做 batched align；ep01 每段都
# 是短句，单 span 即正确。对齐精度不受此 patch 影响（word-level 时间戳由
# wav2vec2 acoustic forward 给出，不依赖 sentence split）。
import nltk  # noqa: E402
from nltk.data import load as _nltk_load_orig  # noqa: E402


class _StubPunktTokenizer:
    """单 sentence span 的 stub —— 满足 whisperx.alignment 调用约定。"""

    def span_tokenize(self, text: str):
        # 整段视作一个 sentence —— alignment 场景下每段 transcript 都是短句
        if not text:
            return iter([])
        return iter([(0, len(text))])


def _patched_nltk_load(resource_name: str, *args, **kwargs):
    if resource_name.startswith("tokenizers/punkt_tab/"):
        print(f"{_ERROR_MARKER} nltk.data.load: using stub for {resource_name} "
              f"(nltk.org unreachable — Rule 3 auto-fix)", flush=True)
        return _StubPunktTokenizer()
    return _nltk_load_orig(resource_name, *args, **kwargs)


def _patched_nltk_download(*args, **kwargs):
    print(f"{_ERROR_MARKER} nltk.download({args}): no-op "
          f"(nltk.org unreachable — Rule 3 auto-fix)", flush=True)
    return False


nltk.data.load = _patched_nltk_load
nltk.download = _patched_nltk_download

# Plan 10-01 共享助手（同目录 import；运行时 cwd 在 repo root，sys.path 已含 spike/audio）
from common import (  # noqa: E402
    EP01_TRANSCRIPT,
    EP01_VOCALS,
    _safe_error,
    stratified_sample,
    write_result,
)

# ============================================================================
# 常量（VALIDATION.md spike invariants）
# ============================================================================
SAMPLE_SIZE = 30                # VALIDATION.md "Spike Reproducibility Invariants"
SAMPLE_SEED = 10                # VALIDATION.md invariant (NOT 42 —— 与 SER/MIR 同 seed)
LANGUAGE_CODE = "zh"            # 硬编码 —— ep01 是中文（CLAUDE.md --whisper-language zh）
DRIFT_THRESHOLD_MS = 200        # DIA-05 ship/defer threshold（<200ms 视为"对齐良好"）
FULL_RUN_DEVICE = "cuda:0"      # device_directive：GPU hybrid full run
A1_SMOKE_DEVICE = "cpu"         # A1 信号：CPU mode 可用性（BLOCKER-1）

# traceback marker —— 帮助 grep 找异常路径是否真走了 _safe_error
_ERROR_MARKER = "[whisperx_align]"


# ============================================================================
# 系统 torch 探针（audit trail）
# ============================================================================
def probe_system_torch() -> str:
    """通过系统 python3 探测系统 torch 版本（不应被 venv 安装污染）。

    Pitfall 1 canary：venv 安装不应改写系统 torch。本函数在脚本运行（venv python）
    时，通过 subprocess 调用系统 ``python3``，验证系统 torch 仍是 2.6.0+cu124。
    """
    try:
        out = subprocess.check_output(
            ["python3", "-c", "import torch; print(torch.__version__)"],
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).decode().strip()
        return out
    except Exception as e:  # noqa: BLE001  spike 容错
        print(f"{_ERROR_MARKER} system torch probe failed: {_safe_error(str(e))}")
        return "unknown"


def probe_venv_torch() -> str:
    """venv 内 torch 版本（``import torch`` 直接读 —— 脚本本身在 venv 里跑）。"""
    try:
        import torch as _t
        return _t.__version__
    except Exception as e:  # noqa: BLE001
        return f"import-failed: {_safe_error(str(e))}"


# ============================================================================
# 数据加载
# ============================================================================
def load_transcript_segments() -> list:
    """读 ep01 transcript.json，返回 segments list。

    transcript schema: {backend, model, language, duration, segments:[{start,end,text}], ...}
    """
    if not EP01_TRANSCRIPT.exists():
        raise FileNotFoundError(
            f"ep01 transcript not found: {EP01_TRANSCRIPT} "
            "(expected output/虫虫…第01话…/transcript.json)"
        )
    data = json.loads(EP01_TRANSCRIPT.read_text(encoding="utf-8"))
    segs = data.get("segments", [])
    print(f"{_ERROR_MARKER} transcript: backend={data.get('backend')} "
          f"model={data.get('model')} lang={data.get('language')} "
          f"duration={data.get('duration')} segments={len(segs)}")
    return segs


# ============================================================================
# WhisperX 对齐 + drift 抽取
# ============================================================================
def align_one_segment(seg: dict, model_a, metadata, audio, device: str) -> dict:
    """对齐单段，返回 aligned result（含 word-level timestamps）。

    A2 smoke：传入 ``[{start, end, text}]`` 单段 list —— 验证 whisperx.align
    接受任意 segments（非完整转录）。
    """
    # 拷贝，防 whisperx.align 原地改输入
    seg_in = {"start": float(seg["start"]), "end": float(seg["end"]),
              "text": str(seg.get("text", ""))}
    result = whisperx.align(
        [seg_in], model_a, metadata, audio, device,
        return_char_alignments=False,
    )
    # result = {"segments": [<aligned_seg>], "word_segments": [...]}
    if not result.get("segments"):
        return {"words": [], "aligned_start": None, "aligned_end": None}
    aligned = result["segments"][0]
    return {
        "words": aligned.get("words", []) or [],
        "aligned_start": aligned.get("start"),
        "aligned_end": aligned.get("end"),
    }


def extract_drift_samples(seg: dict, aligned: dict) -> dict:
    """从 aligned segment 抽 per-word drift（毫秒）+ boundary drift。

    **Drift 定义（plan-literal + boundary 双口径）:**

    1. per_word_offset_drift（plan body 字面口径）:
       对每个 word ``w``：``drift_ms = abs(w["start"] - seg["start"]) * 1000``
       含义：该 word 起点相对段起点的偏移。
       注意：首字此值 = 段起点对齐修正量（有意义）；中段/末段 word 此值 = 段内位置
       （天然较大），所以此指标对长段天然不利。

    2. boundary_drift（research §Pattern 4 口径，更有 alignment-quality 含义）:
       ``start_drift = abs(aligned_start - seg_start) * 1000``
       ``end_drift   = abs(aligned_end   - seg_end)   * 1000``
       含义：whisperx 对齐后的段边界相对原 segment 边界的漂移 —— 直接反映 alignment
       修正幅度。60 个 sample（30 段 × 2 边界）。
    """
    seg_start = float(seg["start"])
    seg_end = float(seg["end"])
    words = aligned.get("words", [])
    # 1) per-word offset drift
    word_drifts = []
    for w in words:
        if w.get("start") is None:
            continue
        d_ms = abs(float(w["start"]) - seg_start) * 1000.0
        word_drifts.append(d_ms)
    # 2) boundary drift（段级，2 sample per segment）
    boundary_drifts = []
    if aligned.get("aligned_start") is not None:
        boundary_drifts.append(abs(float(aligned["aligned_start"]) - seg_start) * 1000.0)
    if aligned.get("aligned_end") is not None:
        boundary_drifts.append(abs(float(aligned["aligned_end"]) - seg_end) * 1000.0)
    # mean word alignment confidence（whisperx 返回 0..1 score）
    scores = [float(w.get("score", 0.0)) for w in words if w.get("score") is not None]
    return {
        "num_words": len(words),
        "word_drifts_ms": word_drifts,
        "boundary_drifts_ms": boundary_drifts,
        "max_word_drift_ms": max(word_drifts) if word_drifts else None,
        "mean_word_drift_ms": round(statistics.mean(word_drifts), 2) if word_drifts else None,
        "mean_word_score": round(statistics.mean(scores), 4) if scores else None,
    }


# ============================================================================
# drift 统计聚合（30 段 → drift_stats）
# ============================================================================
def compute_drift_stats(per_sample: list) -> dict:
    """跨所有 sample 聚合 drift 统计。

    返回 dict 含：
      - ``pct_under_200_ms`` (float 0..1)：所有 word 的 offset drift <200ms 的比例
        —— **plan body 字面口径**（per-word offset）。DIA-05 gating 阈值 ≥80%→ship。
      - ``pct_under_200ms`` (float)：alias（plan frontmatter / verify grep gate 用
        下划线缺失版；schema checker 要求下划线版）。两者数值一致。
      - ``mean_drift_ms`` / ``median_drift_ms``：所有 word offset drift 的均/中位数。
      - ``pct_boundary_under_200_ms`` (float)：段边界 drift <200ms 的比例（60 sample）。
      - ``mean_boundary_drift_ms`` / ``median_boundary_drift_ms``：段边界 drift 均/中位数。
      - ``total_words`` / ``total_boundary_samples``：分母。
      - ``per_bucket``：按段时长分桶（short<2s / medium 2-5s / long>5s / dense>10字/秒）
        的 drift 分布。
    """
    all_word_drifts = []
    all_boundary_drifts = []
    buckets = {"short": [], "medium": [], "long": [], "dense": []}
    for s in per_sample:
        seg = s["segment"]
        dur = float(seg["end"]) - float(seg["start"])
        text = str(seg.get("text", "")) or ""
        all_word_drifts.extend(s["word_drifts_ms"])
        all_boundary_drifts.extend(s["boundary_drifts_ms"])
        # 分桶（与 stratified_sample 一致）
        if dur < 2.0:
            buckets["short"].extend(s["word_drifts_ms"])
        elif dur > 5.0:
            buckets["long"].extend(s["word_drifts_ms"])
        else:
            buckets["medium"].extend(s["word_drifts_ms"])
        if dur > 0 and len(text) / dur > 10:
            buckets["dense"].extend(s["word_drifts_ms"])

    def _pct_under(arr, threshold=DRIFT_THRESHOLD_MS):
        if not arr:
            return None
        return round(sum(1 for x in arr if x < threshold) / len(arr), 4)

    def _mean(arr):
        return round(statistics.mean(arr), 2) if arr else None

    def _median(arr):
        return round(statistics.median(arr), 2) if arr else None

    pct = _pct_under(all_word_drifts)
    return {
        # 主指标（per-word offset drift，plan body 口径）
        "pct_under_200_ms": pct,
        "pct_under_200ms": pct,  # alias —— schema checker 用 _ms 后缀，plan grep gate 用无 _ms 版
        "mean_drift_ms": _mean(all_word_drifts),
        "median_drift_ms": _median(all_word_drifts),
        "total_words": len(all_word_drifts),
        # 段边界 drift（research §Pattern 4 口径，更有 alignment-quality 含义）
        "pct_boundary_under_200_ms": _pct_under(all_boundary_drifts),
        "mean_boundary_drift_ms": _mean(all_boundary_drifts),
        "median_boundary_drift_ms": _median(all_boundary_drifts),
        "total_boundary_samples": len(all_boundary_drifts),
        # 分桶（per-word offset drift by segment length bucket）
        "per_bucket": {
            b: {
                "n_words": len(arr),
                "pct_under_200_ms": _pct_under(arr),
                "mean_drift_ms": _mean(arr),
                "median_drift_ms": _median(arr),
            }
            for b, arr in buckets.items()
        },
    }


# ============================================================================
# A1 + A2 smoke check（device="cpu"，1 段）
# ============================================================================
def run_a1_a2_smoke(segments: list) -> dict:
    """A1 + A2 smoke：CPU 模式 + 单段 align 验证。

    A1：``whisperx.load_align_model(language_code="zh", device="cpu")`` 成功？
    A2：``whisperx.align([single_seg], ...)`` 接受任意 segment 成功？

    Returns:
        dict {a1_status, a2_status, a1_error, a2_error, num_words_aligned, device}
    """
    result = {
        "a1_status": "unknown", "a2_status": "unknown",
        "a1_error": None, "a2_error": None,
        "num_words_aligned": 0, "device": A1_SMOKE_DEVICE,
    }
    # 找一个非空 text 的段做 smoke（末段 text="" 会让 align 返回空 words）
    smoke_seg = next(
        (s for s in segments if str(s.get("text", "")).strip()),
        segments[0],
    )
    print(f"{_ERROR_MARKER} A1 smoke: loading align model on device={A1_SMOKE_DEVICE} ...")
    t0 = time.time()
    try:
        model_a, metadata = whisperx.load_align_model(
            language_code=LANGUAGE_CODE, device=A1_SMOKE_DEVICE,
        )
        result["a1_status"] = "ok"
        print(f"{_ERROR_MARKER} A1 OK ({time.time()-t0:.1f}s) — align model loaded on CPU")
    except Exception as e:
        result["a1_status"] = "failed"
        result["a1_error"] = _safe_error(f"{type(e).__name__}: {e}")
        print(f"{_ERROR_MARKER} A1 FAILED: {result['a1_error']}")
        return result

    # A2: load audio + align 1 seg
    print(f"{_ERROR_MARKER} A2 smoke: aligning 1 segment ...")
    t0 = time.time()
    try:
        audio = whisperx.load_audio(str(EP01_VOCALS))
        aligned = align_one_segment(smoke_seg, model_a, metadata, audio, A1_SMOKE_DEVICE)
        n_words = len(aligned["words"])
        result["num_words_aligned"] = n_words
        result["a2_status"] = "ok"
        print(f"{_ERROR_MARKER} A2 OK ({time.time()-t0:.1f}s) — "
              f"{n_words} words aligned in smoke segment")
    except Exception as e:
        result["a2_status"] = "failed"
        result["a2_error"] = _safe_error(f"{type(e).__name__}: {e}")
        print(f"{_ERROR_MARKER} A2 FAILED: {result['a2_error']}")
    return result


# ============================================================================
# Full run（30 段，GPU 或 CPU fallback）
# ============================================================================
def resolve_full_run_device(requested: str) -> tuple:
    """探测 GPU 可用性，必要时 fallback 到 cpu。

    device_directive：preferred cuda:0；OOM 或 cuda error 时回退 cpu。
    返回 (actual_device, fallback_reason_or_None)。
    """
    try:
        import torch as _t
        if not _t.cuda.is_available():
            return "cpu", "torch.cuda.is_available()==False"
        # 探测目标 GPU
        idx = int(requested.split(":")[1]) if ":" in requested else 0
        if idx >= _t.cuda.device_count():
            return "cpu", f"device index {idx} >= device_count {_t.cuda.device_count()}"
        props = _t.cuda.get_device_properties(idx)
        free, total = _t.cuda.mem_get_info(idx)
        print(f"{_ERROR_MARKER} GPU {idx}: {props.name} "
              f"mem free={free//(1024**2)}MiB total={total//(1024**2)}MiB")
        return requested, None
    except Exception as e:
        return "cpu", _safe_error(f"GPU probe failed: {type(e).__name__}: {e}")


def run_full_drift(segments: list, sample: list, device: str) -> tuple:
    """30 段 full drift run。返回 (per_sample, drift_stats, align_model_load_sec, align_total_sec)。"""
    print(f"{_ERROR_MARKER} full run: loading align model on device={device} ...")
    t0 = time.time()
    model_a, metadata = whisperx.load_align_model(
        language_code=LANGUAGE_CODE, device=device,
    )
    model_load_sec = time.time() - t0
    print(f"{_ERROR_MARKER} align model loaded ({model_load_sec:.1f}s)")

    audio = whisperx.load_audio(str(EP01_VOCALS))
    per_sample = []
    t_align0 = time.time()
    for i, (idx, seg) in enumerate(sample):
        try:
            aligned = align_one_segment(seg, model_a, metadata, audio, device)
            drift = extract_drift_samples(seg, aligned)
            entry = {
                "transcript_idx": idx,
                "segment": {"start": seg["start"], "end": seg["end"],
                            "text": str(seg.get("text", ""))},
                "duration_sec": round(float(seg["end"]) - float(seg["start"]), 3),
                **drift,
            }
            per_sample.append(entry)
            if (i + 1) % 5 == 0 or i == len(sample) - 1:
                print(f"{_ERROR_MARKER}   aligned {i+1}/{len(sample)} "
                      f"(idx={idx}, {drift['num_words']} words)")
        except Exception as e:
            # 单段失败不致命 —— 记 None-word entry，继续（ Rule 1 容错）
            safe = _safe_error(f"{type(e).__name__}: {e}")
            print(f"{_ERROR_MARKER}   segment idx={idx} FAILED: {safe}")
            per_sample.append({
                "transcript_idx": idx,
                "segment": {"start": seg["start"], "end": seg["end"],
                            "text": str(seg.get("text", ""))},
                "duration_sec": round(float(seg["end"]) - float(seg["start"]), 3),
                "num_words": 0, "word_drifts_ms": [], "boundary_drifts_ms": [],
                "max_word_drift_ms": None, "mean_word_drift_ms": None,
                "mean_word_score": None, "error": safe,
            })
    align_total_sec = time.time() - t_align0
    drift_stats = compute_drift_stats(per_sample)
    return per_sample, drift_stats, model_load_sec, align_total_sec


# ============================================================================
# main
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 10 DIA-05 WhisperX drift spike on ep01 vocals "
                    "(run via /tmp/whisperx-spike-venv/bin/python)")
    parser.add_argument(
        "--smoke-only", type=int, default=None,
        help="只跑 N 段 smoke（验证 A1+A2 + 下载 wav2vec2 模型）；不传则跑 full 30 段。")
    parser.add_argument(
        "--skip-a1-smoke", action="store_true",
        help="跳过 A1 smoke（已验证过，节省 ~10s 模型重载时间）。")
    args = parser.parse_args()

    smoke_n = args.smoke_only
    is_smoke = smoke_n is not None

    system_torch = probe_system_torch()
    venv_torch = probe_venv_torch()
    print(f"{_ERROR_MARKER} torch canary: system={system_torch} venv={venv_torch}")

    # 加载 transcript + sample
    segments = load_transcript_segments()
    n_target = smoke_n if is_smoke else SAMPLE_SIZE
    sample = stratified_sample(segments, n=n_target, seed=SAMPLE_SEED)
    print(f"{_ERROR_MARKER} sample: n={len(sample)} (target {n_target}, seed={SAMPLE_SEED})")

    # A1 + A2 smoke（CPU，1 段 —— A1 信号 BLOCKER-1）
    a1a2 = None
    if not args.skip_a1_smoke:
        a1a2 = run_a1_a2_smoke(segments)
    else:
        print(f"{_ERROR_MARKER} A1/A2 smoke skipped (--skip-a1-smoke)")

    # 决定 full-run device
    if is_smoke:
        full_device = A1_SMOKE_DEVICE  # smoke 走 CPU（节省 GPU 内存 + 模型已缓存在 CPU）
        fallback_reason = "smoke-mode (cpu by design)"
    else:
        full_device, fallback_reason = resolve_full_run_device(FULL_RUN_DEVICE)
    print(f"{_ERROR_MARKER} full-run device: {full_device}"
          f"{' (fallback: ' + fallback_reason + ')' if fallback_reason else ''}")

    # 如果 A1 smoke 失败 → 写 stub 结果，推荐 DIA-05 DEFER（不跑 full）
    if a1a2 and a1a2["a1_status"] != "ok":
        print(f"{_ERROR_MARKER} A1 FAILED —— 写 stub 结果，不跑 full run")
        payload = {
            "sample_size": 0,
            "per_sample": [],
            "drift_stats": {
                "pct_under_200_ms": None, "pct_under_200ms": None,
                "mean_drift_ms": None, "median_drift_ms": None,
                "total_words": 0,
                "pct_boundary_under_200_ms": None,
                "mean_boundary_drift_ms": None, "median_boundary_drift_ms": None,
                "total_boundary_samples": 0, "per_bucket": {},
            },
            "methodology": "WhisperX wav2vec2 forced align on existing faster-whisper "
                           "segments (no re-transcription). A1 smoke failed — full run skipped.",
            "caveat": (
                "WhisperX CPU-mode blocked (A1 FAILED) —— per plan fallback rule, "
                "DIA-05 auto-defers AND CUDA path recommendation is stay-on-12.4 "
                "(WhisperX unusable on this stack). A1 error: "
                + str(a1a2.get("a1_error", "unknown"))
            ),
            "a1_a2_smoke": a1a2,
            "a1_device": A1_SMOKE_DEVICE,
            "full_run_device": None,
            "system_torch": system_torch,
            "venv_torch": venv_torch,
            "status": "a1_failed",
        }
        write_result("whisperx_align", "ep01", payload, device=A1_SMOKE_DEVICE)
        return 2

    # Full run
    try:
        per_sample, drift_stats, model_load_sec, align_total_sec = run_full_drift(
            segments, sample, full_device,
        )
    except Exception as e:
        # 致命错误 —— _safe_error 写 stub（T-10-01）
        safe = _safe_error(f"{type(e).__name__}: {e}")
        print(f"{_ERROR_MARKER} full run crashed: {safe}")
        payload = {
            "sample_size": 0, "per_sample": [],
            "drift_stats": {
                "pct_under_200_ms": None, "pct_under_200ms": None,
                "mean_drift_ms": None, "median_drift_ms": None,
                "total_words": 0, "pct_boundary_under_200_ms": None,
                "mean_boundary_drift_ms": None, "median_boundary_drift_ms": None,
                "total_boundary_samples": 0, "per_bucket": {},
            },
            "methodology": "WhisperX wav2vec2 forced align (full run crashed).",
            "caveat": f"Full run crashed before producing drift data. Error: {safe}",
            "a1_a2_smoke": a1a2,
            "a1_device": A1_SMOKE_DEVICE,
            "full_run_device": full_device,
            "system_torch": system_torch,
            "venv_torch": venv_torch,
            "status": "full_run_crashed",
            "fatal_error": safe,
        }
        write_result("whisperx_align", "ep01", payload, device=full_device)
        return 3

    # 成功 —— 写完整结果
    pct = drift_stats.get("pct_under_200_ms")
    is_ship_candidate = pct is not None and pct >= 0.80
    caveat = (
        f"WhisperX Chinese wav2vec2-large-xlsr-53 align drift on {len(sample)} stratified "
        f"ep01 vocals segments. device_directive gpu-hybrid: A1 smoke device={A1_SMOKE_DEVICE}, "
        f"full run device={full_device}"
        + (f" (fallback: {fallback_reason})" if fallback_reason else "")
        + f". Drift stats are device-independent for this measurement "
        f"(wav2vec2 forward is deterministic given same audio; GPU/CPU differ in speed "
        f"not in alignment output modulo float precision). venv torch={venv_torch} "
        f"(cu124 stack force-pinned to match system; whisperx 3.8.6 metadata declares "
        f"torch~=2.8.0 but runs cleanly on 2.6.0+cu124 stack — documented for Plan 06 "
        f"CUDA stay-on-12.4 vs upgrade decision). system torch={system_torch} (Pitfall 1 "
        f"canary: venv install did NOT poison system torch). "
        f"Threshold judgment CANDIDATE (Plan 06 locks): pct_under_200_ms={pct} "
        f"{'≥0.80 → ship-experimental candidate' if is_ship_candidate else '<0.80 → defer candidate'}."
    )
    methodology = (
        "WhisperX wav2vec2 forced align on existing faster-whisper/openai-whisper segments "
        "(A2 validated: no re-transcription, segments passed as-is to whisperx.align). "
        f"Drift = abs(word_start - seg_start)*1000ms per word (plan body literal metric); "
        f"boundary_drift = abs(aligned_seg_boundary - original_seg_boundary)*1000ms "
        f"(research §Pattern 4口径, 2 samples per segment). "
        f"stratified_sample(n={SAMPLE_SIZE}, seed={SAMPLE_SEED}) — shared with SER/MIR "
        f"(Pitfall 9 head-to-head integrity). Threshold: pct_under_200_ms ≥ 0.80 → ship."
    )
    payload = {
        "sample_size": len(sample),
        "per_sample": per_sample,
        "drift_stats": drift_stats,
        "methodology": methodology,
        "caveat": caveat,
        "a1_a2_smoke": a1a2,
        "a1_device": A1_SMOKE_DEVICE,
        "full_run_device": full_device,
        "full_run_fallback_reason": fallback_reason,
        "system_torch": system_torch,
        "venv_torch": venv_torch,
        "device_path": "gpu-hybrid" if full_device.startswith("cuda") else "cpu-fallback",
        "align_model_load_sec": round(model_load_sec, 2),
        "align_total_sec": round(align_total_sec, 2),
        "wall_clock_sec": round(model_load_sec + align_total_sec, 2),
        "status": "ok",
    }
    write_result("whisperx_align", "ep01", payload, device=full_device)
    print(f"{_ERROR_MARKER} DONE — sample_size={len(sample)} "
          f"pct_under_200_ms={pct} device={full_device}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
