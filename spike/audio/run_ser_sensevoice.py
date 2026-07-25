"""Phase 10 SER spike —— SenseVoice 在 ep01 vocals 上的情绪识别测量。

⚠️ THROWAWAY 参考脚本，非 pipeline 代码。不要接进 run_pipeline.py 任何 step_*。

Methodology: ``methodology_ab``（用户决策，已记录在 10-03-SUMMARY.md）。
  - (a) 主路径：每段跑 3 次 SenseVoice 推理（VAD ``max_single_segment_time``
    取 30000/25000/20000 三个变体），测 emotion label 在 3 次推理间的一致率
    → ``self_consistency_pct``。该数字度量 **label 稳定性**，不是 **accuracy**。
  - (b) 可选路径：若 ``spike/audio/results/ser_ground_truth_ep01.json`` 存在
    （开发者手动标注过 30 段），则计算 per-class precision/recall/F1 + macro-F1。
    文件不存在时报告 ``annotation_recommended=true``，并不自行标注（~1h 人工劳动）。

HONEST FRAMING（AF-02/AF-03）：``caveat`` 必须含字面 ``calibrated estimate``，
且必须声明 self-consistency 不可直接对照 DIA-04 ≥50% macro-F1 阈值。
本 spike 不在 self-consistency 单一数字基础上 ship/defer DIA-04；最终判断由
Plan 06 综合做。

锁定约束（CONTEXT.md / VALIDATION.md spike invariants）：
  - sample_size=30, seed=10（与其它 3 个 spike 共享同 30 段——Pitfall 9 完整性）
  - device="cpu"（GPU 当前 DOWN；common.py:write_result 强制 stamp "cpu"）
  - SenseVoice 模型 ID = ``iic/SenseVoiceSmall``（ModelScope canonical, T-10-03）

Pitfall 覆盖：
  - Pitfall 2：用 ``parse_sensevoice_tags`` 解析 raw 文本（在
    ``rich_transcription_postprocess`` **之前**），否则所有 emotion 落 NEUTRAL。
  - Pitfall 6 / T-10-01：所有 funasr 异常路径经 ``_safe_error`` redact 后再 print。
  - Pitfall 8：pathlib.Path 处理全角中文目录名，不走 shell。
"""
import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# funasr (T-10-03: canonical ModelScope ID)
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# Plan 01 spike helpers
from common import (
    EP01_VOCALS,
    EP01_SHOTS,
    stratified_sample,
    parse_sensevoice_tags,
    write_result,
    _safe_error,
)

# ============================================================================
# 常量
# ============================================================================
MODEL_ID = "iic/SenseVoiceSmall"          # T-10-03 ModelScope canonical
DEVICE = "cpu"                             # CONTEXT.md locked
SAMPLE_SIZE = 30                           # VALIDATION.md invariant
SAMPLE_SEED = 10                           # VALIDATION.md invariant (NOT 42)
EXPECTED_EMOTIONS = sorted({
    "HAPPY", "SAD", "ANGRY", "NEUTRAL",
    "FEARFUL", "DISGUSTED", "SURPRISED",
})
# methodology_ab：VAD max_single_segment_time 三变体（毫秒）
# 短 shot（<10s）几乎总落单段，但 VAD 边界微抖动会改变 SenseVoice 看到的 padding/
# batch shape，偶发改变 emotion 输出 → 一致率是稳定性代理。
VAD_VARIANTS_MS = (30000, 25000, 20000)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent / "results" / "ser_ground_truth_ep01.json"
)

# caveat 必须含字面 "calibrated estimate"（plan 10-03 verify grep gate）
CAVEAT = (
    "Without ep01 ground-truth emotion labels, the self_consistency_pct metric is a "
    "calibrated estimate of SenseVoice's label stability across VAD-segmentation "
    "variants, NOT a true macro-F1 against human annotations. Self-consistency is "
    "NOT directly comparable to the DIA-04 >=50% macro-F1 accuracy threshold: a "
    "model that deterministically predicts NEUTRAL on every clip would score 100% "
    "self-consistency yet unknown real accuracy. True macro-F1 requires developer "
    "annotation of these 30 segments (~1hr labor, see ser_ground_truth_ep01.json "
    "path). Cross-domain accuracy on other Chinese animation episodes may differ. "
    "Plan 06 composes the final DIA-04 ship/defer judgment —— this spike does NOT "
    "lock DIA-04 from self_consistency_pct alone."
)


# ============================================================================
# 工具：ffmpeg 切片 vocals.wav → 16kHz mono tmp wav
# ============================================================================
def slice_vocals(vocals_wav: Path, start_sec: float, end_sec: float,
                 out_wav: Path) -> None:
    """ffmpeg ``-ss``/``-t`` 切片，重采样到 SenseVoice 训练分布（16kHz mono）。

    vocals.wav 本身是 44.1kHz stereo；funasr 内部会重采样，但显式输出 16kHz mono
    可以让 VAD 输入分布与 SenseVoice 训练分布对齐，减少偶发推理漂移。
    """
    dur = max(0.1, end_sec - start_sec)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.3f}",
        "-t", f"{dur:.3f}",
        "-i", str(vocals_wav),
        "-ar", "16000",
        "-ac", "1",
        "-loglevel", "error",
        str(out_wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=15)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(_safe_error(
            f"ffmpeg slice failed rc={e.returncode}: "
            f"{(e.stderr or b'').decode('utf-8', errors='replace')}"
        )) from None
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(_safe_error(f"ffmpeg slice timeout: {e}")) from None


# ============================================================================
# 加载 3 个 SenseVoice 实例（VAD kwargs 变体）
# ============================================================================
def load_models():
    """3 个 AutoModel 实例，``vad_kwargs.max_single_segment_time`` 取三档。

    第一次实例化会从 ModelScope 拉取 ``iic/SenseVoiceSmall``（~1GB，匿名下载，
    不需要 HF_TOKEN —— A4）。后续两次复用本地缓存。CPU 加载每实例约 10-15s。
    """
    models = []
    for vad_ms in VAD_VARIANTS_MS:
        print(f"[ser] loading SenseVoice vad_max_single_segment_time={vad_ms}ms")
        try:
            m = AutoModel(
                model=MODEL_ID,
                trust_remote_code=True,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": vad_ms},
                device=DEVICE,
                disable_pbar=True,
            )
        except Exception as e:  # noqa: BLE001  spike 容错
            # T-10-01：funasr 异常可能 echo HF_TOKEN，必经 _safe_error。
            raise RuntimeError(_safe_error(f"AutoModel load failed: {e}")) from None
        models.append(m)
    return models


# ============================================================================
# 单段：3× 推理 + 一致性
# ============================================================================
def predict_one_shot(models, vocals_wav: Path, shot: dict) -> dict:
    shot_id = shot["id"]
    start_sec = float(shot["start_sec"])
    end_sec = float(shot["end_sec"])
    duration_sec = float(shot.get("duration", end_sec - start_sec))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_wav = Path(f.name)
    try:
        slice_vocals(vocals_wav, start_sec, end_sec, tmp_wav)
        runs = []
        for i, m in enumerate(models):
            try:
                res = m.generate(
                    input=str(tmp_wav),
                    cache={},
                    language="zh",        # FORCE zh: 短片段 auto-detect 误判率高
                    use_itn=True,
                    ban_emo_unk=False,    # 保留 <|emo_unk|>，区分 "无预测" 与 "预测错"
                )
            except Exception as e:  # noqa: BLE001  spike 容错
                raise RuntimeError(_safe_error(
                    f"generate() run {i + 1}/{len(models)} failed: {e}"
                )) from None
            raw_text = res[0]["text"] if res else ""
            # Pitfall 2：在 rich_transcription_postprocess 之前 parse 标签。
            tags = parse_sensevoice_tags(raw_text)
            # rich_transcription_postprocess 同时给出 ASR-干净文本（人类可读）。
            clean_asr = rich_transcription_postprocess(raw_text)
            runs.append({
                "emotion": tags["emotion"],
                "events": tags["events"],
                "language": tags["language"],
                "raw_text": raw_text,
                "clean_text": clean_asr,
            })
    finally:
        tmp_wav.unlink(missing_ok=True)

    emo_counts = Counter(p["emotion"] for p in runs)
    top_emo, top_count = emo_counts.most_common(1)[0]
    agreement = top_count / len(runs)
    events_union = sorted({e for p in runs for e in p["events"]})
    return {
        "shot_id": shot_id,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": duration_sec,
        "predicted_emotion": top_emo,
        "predicted_events": events_union,
        "proxy_confidence": round(agreement, 4),
        "clean_text": runs[0]["clean_text"],
        "per_run_emotions": [p["emotion"] for p in runs],
        "per_run_languages": [p["language"] for p in runs],
    }


# ============================================================================
# methodology-b：可选 ground-truth 路径
# ============================================================================
def maybe_compute_macro_f1(per_sample: list, gt_path: Path) -> dict:
    """若 ``ser_ground_truth_ep01.json`` 存在，计算 per-class P/R/F1 + macro-F1。

    Ground truth schema: list[{"shot_id": int, "emotion": str}]。
    不存在 → ``annotation_recommended=true``，提示开发者手动标注（~1h）。
    """
    if not gt_path.exists():
        return {
            "annotation_recommended": True,
            "macro_f1": None,
            "per_class": None,
            "note": (
                "ser_ground_truth_ep01.json not found —— true macro-F1 requires "
                "developer annotation of these 30 segments (~1hr labor). Re-run "
                "after annotating to enter methodology-b path. self_consistency_pct "
                "above remains a stability proxy, not an accuracy measure."
            ),
        }
    try:
        gt_list = json.loads(gt_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001  spike 容错
        return {
            "annotation_recommended": True,
            "macro_f1": None,
            "per_class": None,
            "note": _safe_error(f"ground truth parse failed: {e}"),
        }
    gt_map = {item["shot_id"]: item["emotion"] for item in gt_list}
    pred_map = {s["shot_id"]: s["predicted_emotion"] for s in per_sample}
    per_class = {}
    f1s = []
    for cls in EXPECTED_EMOTIONS:
        tp = sum(1 for sid in pred_map if pred_map[sid] == cls and gt_map.get(sid) == cls)
        fp = sum(1 for sid in pred_map if pred_map[sid] == cls and gt_map.get(sid) != cls)
        fn = sum(1 for sid in pred_map if pred_map[sid] != cls and gt_map.get(sid) == cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[cls] = {
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn,
        }
        f1s.append(f1)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return {
        "annotation_recommended": False,
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "note": f"macro-F1 computed against {gt_path.name}",
    }


# ============================================================================
# 主流程
# ============================================================================
def run(smoke_only: int = 0) -> None:
    print(f"[ser] ep01 shots: {EP01_SHOTS}")
    try:
        shots_raw = json.loads(EP01_SHOTS.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001  spike 容错
        print(_safe_error(f"[ser] FATAL shots.json unreadable: {e}"),
              file=sys.stderr)
        sys.exit(2)

    # stratified_sample 期望 segment dict 含 ``start`` / ``end``；shots.json 用
    # ``start_sec`` / ``end_sec`` —— 在调用前归一化键名（不改 common.py）。
    shots_norm = [
        {
            "id": s["id"],
            "start": s["start_sec"],
            "end": s["end_sec"],
            "start_sec": s["start_sec"],
            "end_sec": s["end_sec"],
            "duration": s.get("duration", s["end_sec"] - s["start_sec"]),
        }
        for s in shots_raw
    ]
    sample = stratified_sample(shots_norm, n=SAMPLE_SIZE, seed=SAMPLE_SEED)
    if smoke_only > 0:
        sample = sample[:smoke_only]
        print(f"[ser] SMOKE MODE: first {len(sample)} of {SAMPLE_SIZE}")
    print(f"[ser] sample size: {len(sample)}  seed={SAMPLE_SEED}  "
          f"vocals={EP01_VOCALS.name}")

    models = load_models()
    per_sample = []
    for i, (_idx, shot) in enumerate(sample):
        try:
            entry = predict_one_shot(models, EP01_VOCALS, shot)
        except Exception as e:  # noqa: BLE001  spike 容错 —— 单段失败不毁全局
            entry = {
                "shot_id": shot["id"],
                "start_sec": float(shot["start_sec"]),
                "end_sec": float(shot["end_sec"]),
                "duration_sec": float(shot.get("duration", 0.0)),
                "predicted_emotion": "emo_unk",
                "predicted_events": [],
                "proxy_confidence": 0.0,
                "clean_text": "",
                "per_run_emotions": ["emo_unk"] * len(models),
                "error": _safe_error(str(e)),
            }
        per_sample.append(entry)
        if (i + 1) % 5 == 0 or (i + 1) == len(sample):
            print(f"[ser] {i + 1}/{len(sample)} shot_id={entry['shot_id']} "
                  f"emotion={entry['predicted_emotion']} "
                  f"agree={entry['proxy_confidence']}")

    # metric: 平均一致率 × 100
    agreements = [s["proxy_confidence"] for s in per_sample]
    self_consistency_pct = (
        round(100.0 * sum(agreements) / len(agreements), 2) if agreements else 0.0
    )
    emo_dist = dict(Counter(s["predicted_emotion"] for s in per_sample))
    gt_result = maybe_compute_macro_f1(per_sample, GROUND_TRUTH_PATH)

    payload = {
        "model_id": MODEL_ID,
        "sample_size": len(per_sample),
        "per_sample": per_sample,
        "methodology": "methodology_ab",
        "metric_name": "self_consistency_pct",
        "metric_value": self_consistency_pct,
        "vad_variants_ms": list(VAD_VARIANTS_MS),
        "emotion_distribution": emo_dist,
        "emotion_classes_expected": EXPECTED_EMOTIONS,
        "annotation_recommended": gt_result["annotation_recommended"],
        "ground_truth_macro_f1": gt_result["macro_f1"],
        "ground_truth_per_class": gt_result["per_class"],
        "ground_truth_note": gt_result["note"],
        "caveat": CAVEAT,
    }
    write_result("ser_sensevoice", "ep01", payload)
    print(f"[ser] self_consistency_pct={self_consistency_pct:.2f}  "
          f"emotion_dist={emo_dist}")
    print(f"[ser] annotation_recommended={gt_result['annotation_recommended']}  "
          f"macro_f1={gt_result['macro_f1']}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Phase 10 SER spike —— SenseVoice on ep01 vocals (methodology_ab)"
    )
    ap.add_argument(
        "--smoke-only", type=int, default=0, metavar="N",
        help="仅跑前 N 段（Wave 1 快速验证，默认 0=跑全 30 段）",
    )
    args = ap.parse_args()
    try:
        run(smoke_only=args.smoke_only)
    except Exception as e:  # noqa: BLE001  spike 容错
        # T-10-01：顶层异常兜底，所有 funasr 异常字符串必经 _safe_error。
        print(_safe_error(f"[ser] FATAL: {e}"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
