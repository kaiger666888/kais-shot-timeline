"""Phase 10 MIR spike —— MERT-v1-95M vs PANNs Cnn14 头对头乐器识别测量。

⚠️ THROWAWAY 参考脚本，非 pipeline 代码。不要接进 run_pipeline.py 任何 step_*。

Methodology: ``mir_c``（CONTEXT.md "Claude's Discretion" 委托；checkpoint
resolution 在 10-04-SUMMARY.md 记录）。
  - (c) 定性比较 —— 跳过严谨 mAP（无中文民乐 GT），仅记录两模型 top-5
    预测 + 每段 embedding 度量；开发者 "sensible rating" 显式 DEFER 给
    Plan 06 user checkpoint（本 spike 不替开发者打分）。
  - metric_value = null（mir-c 无严谨度量）；metric_name = "qualitative_top5"。

为什么 mir-c 而非 mir-a/b/ab：
  - mir-a/b/ab 全部依赖开发者 ~1.5hr 手工标注 30 段多标签 ground truth。
    CONTEXT.md 把方法论选择委托给 Claude；orchestrator checkpoint_resolution
    选了 mir-c（零人工 labor，最快进入 Plan 06 决策）。
  - 这意味着 MUS-04 ≥0.30 mAP 阈值 **不能**字面应用 —— Plan 06 必须基于
    定性 "sensible-rate" 判断，本 spike 仅提供原始预测供其评估。

锁定约束（CONTEXT.md / VALIDATION.md spike invariants）：
  - sample_size=30, seed=10（与 SER/WhisperX 共享同 30 段——Pitfall 9 完整性）
  - device="cpu"（GPU 当前 DOWN；common.py:write_result 强制 stamp "cpu"）
  - MERT canonical HF ID = ``m-a-p/MERT-v1-95M``（T-10-03）
  - PANNs Cnn14 = ``panns_inference.AudioTagging(checkpoint_path=None)``
    （T-10-03 supply-chain mitigation —— 走 PyPI 官方 CDN，永不指定本地路径）
  - 输入混音 = drums + bass + other stems 叠加（vocals 留给 SER spike）

Pitfall 覆盖：
  - Pitfall 3：MERT 训练率 24kHz / PANNs Cnn14 训练率 32kHz —— librosa.load
    显式 ``sr=24000`` / ``sr=32000``，硬编码不可配置（防误用 44.1kHz）。
  - Pitfall 6 / T-10-01：所有 transformers / panns_inference 异常路径必经
    ``_safe_error`` redact（HF_TOKEN 可能被 echo 进 stderr）。
  - Pitfall 8：pathlib.Path 处理全角中文目录名，不走 shell。
  - Pitfall 9：sample 必须 EXACTLY 匹配 ``sample_mir_ep01.json`` 的 shot_id
    列表 —— ``assert shot_ids == sample_audit`` 在 run() 入口校验。

HF 镜像：本机 huggingface.co 不可达；脚本在 ``from transformers import``
之前 ``os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")``
（hf-mirror.com 可达；HF_TOKEN 已设）。

MERT-v1-95M 架构限制（影响 predicted_instruments 形态）：
  - MERT 是 audio encoder（12-layer 768-dim），**没有 instrument classifier
    head**。要拿乐器标签需 (a) fine-tune 一个 head，或 (b) 用 labeled
    embedding bank 做 nearest-neighbor —— spike 两者都没有。
  - 替代方案：对 30 段 embedding 做 k-means(k=5) 聚类，``predicted_instruments
    = ["mert_cluster_<id>"]`` —— Plan 06 可以定性看 "MERT 把哪些段聚到一起"。
    ``metric_per_sample = embedding L2 norm``（信号强度代理）。
  - 这是诚实标注，不是 "MERT 识别出乐器 X"。caveat 明示此限制。
"""
import argparse
import json
import os
import sys
from pathlib import Path

# HF_ENDPOINT 必须在 ``from transformers import`` 之前设置（HF 被墙 → 镜像）
# huggingface.co 本机不可达；hf-mirror.com 可达。HF_TOKEN 已在环境里。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import librosa  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

# Plan 01 spike helpers
from common import (  # noqa: E402
    EP01_DRUMS,
    EP01_BASS,
    EP01_OTHER,
    EP01_SHOTS,
    stratified_sample,
    write_result,
    _safe_error,
)

# ============================================================================
# 常量
# ============================================================================
MERT_MODEL_ID = "m-a-p/MERT-v1-95M"        # T-10-03 canonical HF ID
MERT_SR = 24000                            # Pitfall 3 — MERT 训练率，硬编码不可改
PANNS_SR = 32000                           # Pitfall 3 — Cnn14 训练率，硬编码不可改
PANNS_CHECKPOINT = None                    # None = 默认 Cnn14_mAP=0.431.pth（T-10-03）
SAMPLE_SIZE = 30                           # VALIDATION.md invariant
SAMPLE_SEED = 10                           # VALIDATION.md invariant (NOT 42)
DEVICE = "cpu"                             # CONTEXT.md locked
TOP_K = 5                                  # per-segment top-5 预测
N_MERT_CLUSTERS = 5                        # k-means 聚类数（MERT 无 classifier head）

SAMPLE_AUDIT_PATH = (
    Path(__file__).resolve().parent / "results" / "sample_mir_ep01.json"
)

# caveat 必须含字面 "calibrated estimate"（plan 10-04 verify grep gate）
CAVEAT_MERT = (
    "MERT-v1-95M is an audio encoder with NO instrument classifier head —— "
    "predicted_instruments here are k-means cluster IDs over the 30-segment "
    "embedding set, not literal instrument labels. metric_per_sample is the "
    "L2 norm of the 768-d layer-averaged embedding (a signal-strength "
    "indicator, NOT an accuracy score). This is a calibrated estimate of "
    "MERT's discriminative power on Chinese folk instrumentation, NOT a "
    "publishable mAP. No canonical Chinese-folk-instrument (erhu/pipa/"
    "guzheng/dizi) ground truth exists for these 30 segments; mir-c "
    "deliberately skipped rigorous mAP —— the MUS-04 >=0.30 mAP threshold "
    "CANNOT be applied literally. Developer sensible-rating is deferred to "
    "Plan 06 user checkpoint (this spike does NOT pre-rate). Plan 06 must "
    "compose the final MUS-04 ship/defer judgment and pick MERT vs PANNs as "
    "the route-host MIR model; this spike provides raw predictions only."
)

CAVEAT_PANNS = (
    "PANNs Cnn14 (Cnn14_mAP=0.431.pth default checkpoint) was trained on "
    "AudioSet, whose 527 classes do NOT include Chinese folk instruments "
    "(erhu / pipa / guzheng / dizi) —— top-5 predictions are the closest "
    "AudioSet equivalents (e.g. erhu -> Violin, pipa/guzheng -> Harp or "
    "Plucked instrument, dizi -> Flute). metric_per_sample is the top-1 "
    "clipwise probability (a confidence proxy, NOT an accuracy score). "
    "This is a calibrated estimate of PANNs's coverage of Chinese folk "
    "instrument timbres, NOT a publishable mAP. No canonical ground truth "
    "exists; mir-c deliberately skipped rigorous mAP —— the MUS-04 >=0.30 "
    "threshold CANNOT be applied literally. Developer sensible-rating is "
    "deferred to Plan 06 user checkpoint. Plan 06 composes the final "
    "MUS-04 ship/defer decision and the MERT-vs-PANNs route-host pick."
)


# ============================================================================
# 模型加载（lazy）
# ============================================================================
def load_mert():
    """加载 m-a-p/MERT-v1-95M (encoder + Wav2Vec2 processor)。

    第一次调用会从 HF（走 hf-mirror.com 镜像）下载 ~350MB 权重。CPU 加载
    约 10-20s。所有 transformers 异常经 _safe_error redact 后再 raise。
    """
    from transformers import AutoModel, Wav2Vec2FeatureExtractor
    try:
        print(f"[mir] loading MERT {MERT_MODEL_ID} (device={DEVICE}, mirror={os.environ.get('HF_ENDPOINT')})")
        model = AutoModel.from_pretrained(MERT_MODEL_ID, trust_remote_code=True)
        processor = Wav2Vec2FeatureExtractor.from_pretrained(
            MERT_MODEL_ID, trust_remote_code=True
        )
        model.to(DEVICE)
        model.eval()
    except Exception as e:  # noqa: BLE001  spike 容错
        # T-10-01：transformers 异常可能 echo HF_TOKEN
        raise RuntimeError(_safe_error(f"MERT load failed: {e}")) from None
    return model, processor


def load_panns():
    """加载 PANNs Cnn14 via panns_inference.AudioTagging(checkpoint_path=None)。

    checkpoint_path=None → panns_inference 从其官方 CDN 拉 Cnn14_mAP=0.431.pth
    （~250MB）。T-10-03 supply-chain mitigation：永不指定本地路径，永远走
    PyPI 默认 CDN。CDN 不可达时 raise（Plan 06 fallback 见 spike README）。
    """
    from panns_inference import AudioTagging, labels as panns_labels
    try:
        print(f"[mir] loading PANNs Cnn14 (checkpoint_path={PANNS_CHECKPOINT}, device={DEVICE})")
        at = AudioTagging(checkpoint_path=PANNS_CHECKPOINT, device=DEVICE)
    except Exception as e:  # noqa: BLE001  spike 容错
        raise RuntimeError(_safe_error(f"PANNs load failed: {e}")) from None
    return at, list(panns_labels)


# ============================================================================
# 切片 + 混音：drums + bass + other
# ============================================================================
def load_mix_slice(start_sec: float, end_sec: float, target_sr: int) -> np.ndarray:
    """从 drums/bass/other stems 切出 [start, end] 段，加和成 mono mix。

    librosa.load(path, sr=target_sr, mono=True, offset, duration) 直接读
    WAV + 重采样到目标率，省去 ffmpeg subprocess（Demucs 输出是标准 WAV，
    soundfile 可以原地 seek）。三 stems 长度按最短对齐后 numpy 加和。
    """
    dur = max(0.1, end_sec - start_sec)
    stems = []
    for stem_path in (EP01_DRUMS, EP01_BASS, EP01_OTHER):
        try:
            y, _ = librosa.load(
                str(stem_path),
                sr=target_sr,
                mono=True,
                offset=start_sec,
                duration=dur,
            )
        except Exception as e:  # noqa: BLE001  spike 容错
            raise RuntimeError(_safe_error(
                f"librosa.load({stem_path.name}, sr={target_sr}, "
                f"offset={start_sec:.3f}, dur={dur:.3f}) failed: {e}"
            )) from None
        stems.append(y)
    min_len = min(len(y) for y in stems)
    mix = np.zeros(min_len, dtype=np.float32)
    for y in stems:
        mix += y[:min_len]
    # 防 clipping：归一化到 [-1, 1]（若加和超出）
    peak = float(np.max(np.abs(mix)))
    if peak > 1.0:
        mix = mix / peak
    return mix


# ============================================================================
# MERT 推理 → embedding
# ============================================================================
def mert_embed(model, processor, audio_24k: np.ndarray) -> np.ndarray:
    """跑 MERT-v1-95M 前向，返回 768-d layer-averaged embedding。

    Pattern 来自 RESEARCH.md §Pattern 2（lines 386-415）：
      - 24kHz 训练率（调用方传入 audio_24k，已 librosa.load(sr=24000)）
      - output_hidden_states=True → 拿到 13 层（input + 12 transformer）
      - 对 13 层做时间维 mean-pool → [13, 768] → 再对 layer 维 mean → [768]
    """
    if audio_24k.size == 0:
        return np.zeros(768, dtype=np.float32)
    inputs = processor(audio_24k, sampling_rate=MERT_SR, return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
    try:
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)
    except Exception as e:  # noqa: BLE001  spike 容错
        raise RuntimeError(_safe_error(f"MERT forward failed: {e}")) from None
    # hidden_states: tuple of (num_layers+1) tensors, each (batch=1, T, 768).
    # ⚠️ 必须用 .squeeze()（无参）—— 移除所有 size-1 维（batch=1）。
    #    .squeeze(0) 不会动 dim 0（=L+1=13，非 1）→ batch 维残留 → mean 维度
    #    错位 → embedding 变成 (T, 768) 而非 (768,) → np.array 报 inhomogeneous
    #    shape（smoke run Task 3 bug fix）。
    all_layers = torch.stack(outputs.hidden_states).squeeze()   # (L+1, T, 768)
    time_reduced = all_layers.mean(dim=1)                       # (L+1, 768)
    embedding = time_reduced.mean(dim=0).cpu().float().numpy()  # (768,)
    return embedding


# ============================================================================
# PANNs 推理 → top-K AudioSet labels + probs
# ============================================================================
def panns_topk(at, labels, audio_32k: np.ndarray, k: int = TOP_K):
    """跑 PANNs Cnn14 → clipwise_output (527) → top-k labels + probs。

    Pattern 来自 RESEARCH.md §Pattern 3（lines 418-441）：
      - 32kHz 训练率（调用方传入 audio_32k，已 librosa.load(sr=32000)）
      - at.inference(audio) 返回 (clipwise_output, embedding)
      - clipwise_output shape (1, 527) —— 527 个 AudioSet 类的概率
    """
    if audio_32k.size == 0:
        return [], 0.0
    audio_batched = audio_32k[None, :]  # (1, samples)
    try:
        clipwise, _embedding = at.inference(audio_batched)
    except Exception as e:  # noqa: BLE001  spike 容错
        raise RuntimeError(_safe_error(f"PANNs inference failed: {e}")) from None
    probs = np.asarray(clipwise).flatten()  # (527,)
    top1_prob = float(probs.max()) if probs.size else 0.0
    if probs.size == 0:
        return [], 0.0
    top_idx = np.argsort(probs)[::-1][:k]
    topk = [
        {"label": str(labels[i]) if i < len(labels) else f"idx_{int(i)}",
         "prob": round(float(probs[i]), 4)}
        for i in top_idx
    ]
    return topk, top1_prob


# ============================================================================
# 校验 sample 与 pre-commit audit 一致（Pitfall 9）
# ============================================================================
def load_sample(smoke_only: int = 0):
    """读 shots.json + stratified_sample → 30 段；与 sample_mir_ep01.json 比对。

    sample_mir_ep01.json 是 Task 2 在两模型运行**之前**就提交的 audit trail。
    如果这里抽出的 shot_id 列表 ≠ audit，立刻 fail（Pitfall 9 head-to-head
    integrity violation）。
    """
    try:
        shots_raw = json.loads(EP01_SHOTS.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001  spike 容错
        print(_safe_error(f"[mir] FATAL shots.json unreadable: {e}"),
              file=sys.stderr)
        sys.exit(2)
    # common.stratified_sample 期望 start/end（不是 start_sec/end_sec）—— 归一化
    shots_norm = [
        {"id": s["id"], "start": s["start_sec"], "end": s["end_sec"],
         "start_sec": s["start_sec"], "end_sec": s["end_sec"],
         "duration": s.get("duration", s["end_sec"] - s["start_sec"])}
        for s in shots_raw
    ]
    sample = stratified_sample(shots_norm, n=SAMPLE_SIZE, seed=SAMPLE_SEED)
    actual_ids = [s[1]["id"] for s in sample]

    # Pitfall 9 audit gate
    try:
        audit = json.loads(SAMPLE_AUDIT_PATH.read_text(encoding="utf-8"))
        audit_ids = audit["shot_ids"]
    except Exception as e:  # noqa: BLE001  spike 容错
        print(_safe_error(f"[mir] FATAL sample_mir_ep01.json unreadable: {e}"),
              file=sys.stderr)
        sys.exit(2)
    if actual_ids != audit_ids:
        print(f"[mir] FATAL Pitfall 9 violation: live sample ({actual_ids[:5]}...) "
              f"!= audit ({audit_ids[:5]}...)", file=sys.stderr)
        sys.exit(3)
    print(f"[mir] Pitfall 9 audit GREEN: live sample matches "
          f"sample_mir_ep01.json ({len(actual_ids)} shot_ids)")

    if smoke_only > 0:
        sample = sample[:smoke_only]
        print(f"[mir] SMOKE MODE: first {len(sample)} of {SAMPLE_SIZE}")
    return sample


# ============================================================================
# MERT head-to-head run
# ============================================================================
def run_mert(sample, smoke_only: int):
    """跑 MERT 在每段上 → 收集 embedding → k-means 聚类 → per_sample entries。

    返回 list[dict]，每条 = {shot_id, predicted_instruments, metric_per_sample,
    mert_embedding_l2, mert_cluster_id}。predicted_instruments 是单元素
    ``["mert_cluster_<id>"]`` —— MERT 没 classifier head，cluster ID 是诚实
    替代（Plan 06 可定性看 "MERT 把哪些段聚到一起"）。
    """
    from sklearn.cluster import KMeans  # 延迟导入：sklearn 已 transitive 装好

    model, processor = load_mert()
    embeddings = []
    entries = []
    for i, (_idx, shot) in enumerate(sample):
        shot_id = shot["id"]
        start_sec = float(shot["start_sec"])
        end_sec = float(shot["end_sec"])
        try:
            audio_24k = load_mix_slice(start_sec, end_sec, MERT_SR)
            emb = mert_embed(model, processor, audio_24k)
        except Exception as e:  # noqa: BLE001  spike 容错 —— 单段失败不毁全局
            entries.append({
                "shot_id": shot_id,
                "predicted_instruments": ["<error>"],
                "metric_per_sample": 0.0,
                "mert_embedding_l2": 0.0,
                "mert_cluster_id": -1,
                "error": _safe_error(str(e)),
            })
            embeddings.append(np.zeros(768, dtype=np.float32))
        else:
            l2 = float(np.linalg.norm(emb))
            embeddings.append(emb)
            entries.append({
                "shot_id": shot_id,
                "predicted_instruments": [],  # 占位 —— 聚类后回填
                "metric_per_sample": round(l2, 4),
                "mert_embedding_l2": round(l2, 4),
            })
        if (i + 1) % 5 == 0 or (i + 1) == len(sample):
            print(f"[mir] MERT {i + 1}/{len(sample)} shot_id={shot_id} "
                  f"emb_l2={entries[-1]['mert_embedding_l2']:.3f}")

    # k-means 聚类（MERT 无 classifier head —— 给 Plan 06 一个跨段相似性视图）
    X = np.array(embeddings)
    n_clusters = min(N_MERT_CLUSTERS, len(X))
    if n_clusters >= 1 and len(X) >= n_clusters:
        km = KMeans(n_clusters=n_clusters, random_state=SAMPLE_SEED, n_init=10)
        labels_km = km.fit_predict(X)
        for entry, cid in zip(entries, labels_km):
            entry["mert_cluster_id"] = int(cid)
            # predicted_instruments 必须是 list[str] —— 单元素 cluster marker
            entry["predicted_instruments"] = [f"mert_cluster_{int(cid)}"]
    else:
        for entry in entries:
            entry["mert_cluster_id"] = -1
            entry["predicted_instruments"] = ["<no_cluster>"]
    return entries


# ============================================================================
# PANNs head-to-head run
# ============================================================================
def run_panns(sample, smoke_only: int):
    """跑 PANNs Cnn14 在每段上 → top-K AudioSet labels + top-1 prob → entries。

    返回 list[dict]，每条 = {shot_id, predicted_instruments, metric_per_sample,
    panns_top5_with_probs, panns_top1_prob}。predicted_instruments 是 top-5
    AudioSet label 字符串列表（无 Chinese-folk 子集过滤 —— 留给 Plan 06 评估）。
    """
    at, labels = load_panns()
    entries = []
    for i, (_idx, shot) in enumerate(sample):
        shot_id = shot["id"]
        start_sec = float(shot["start_sec"])
        end_sec = float(shot["end_sec"])
        try:
            audio_32k = load_mix_slice(start_sec, end_sec, PANNS_SR)
            topk, top1 = panns_topk(at, labels, audio_32k, k=TOP_K)
        except Exception as e:  # noqa: BLE001  spike 容错
            entries.append({
                "shot_id": shot_id,
                "predicted_instruments": ["<error>"],
                "metric_per_sample": 0.0,
                "panns_top1_prob": 0.0,
                "panns_top5_with_probs": [],
                "error": _safe_error(str(e)),
            })
            continue
        label_strs = [t["label"] for t in topk]
        entries.append({
            "shot_id": shot_id,
            "predicted_instruments": label_strs,
            "metric_per_sample": round(top1, 4),
            "panns_top1_prob": round(top1, 4),
            "panns_top5_with_probs": topk,
        })
        if (i + 1) % 5 == 0 or (i + 1) == len(sample):
            top1_label = label_strs[0] if label_strs else "?"
            print(f"[mir] PANNs {i + 1}/{len(sample)} shot_id={shot_id} "
                  f"top1={top1_label}({top1:.3f})")
    return entries


# ============================================================================
# 主流程
# ============================================================================
def run(model_choice: str = "both", smoke_only: int = 0) -> None:
    sample = load_sample(smoke_only=smoke_only)
    print(f"[mir] sample size: {len(sample)}  seed={SAMPLE_SEED}  "
          f"model={model_choice}  drums={EP01_DRUMS.name}  "
          f"MERT@{MERT_SR}Hz  PANNs@{PANNS_SR}Hz")

    if model_choice in ("mert", "both"):
        mert_entries = run_mert(sample, smoke_only)
        payload_mert = {
            "model_id": MERT_MODEL_ID,
            "checkpoint": f"hf:{MERT_MODEL_ID} (transformers AutoModel, CPU)",
            "sample_size": len(mert_entries),
            "per_sample": mert_entries,
            "methodology": "mir_c",
            "metric_name": "qualitative_top5",
            "metric_value": None,                  # mir-c: 无严谨度量
            "top_k": TOP_K,
            "sample_rate_hz": MERT_SR,             # Pitfall 3 留痕
            "n_mert_clusters": N_MERT_CLUSTERS,
            "embedding_dim": 768,
            "mix_strategy": "drums+bass+other stems summed (vocals excluded — SER owns vocals)",
            "caveat": CAVEAT_MERT,
            "sensible_rating_deferred_to": "Plan 06 user checkpoint",
        }
        write_result("mir_mert", "ep01", payload_mert)
        print(f"[mir] MERT done: {len(mert_entries)} entries written")

    if model_choice in ("panns", "both"):
        panns_entries = run_panns(sample, smoke_only)
        payload_panns = {
            "model_id": "panns_inference.AudioTagging(Cnn14_mAP=0.431.pth)",
            "checkpoint": "Cnn14_mAP=0.431.pth (panns_inference default CDN, checkpoint_path=None)",
            "sample_size": len(panns_entries),
            "per_sample": panns_entries,
            "methodology": "mir_c",
            "metric_name": "qualitative_top5",
            "metric_value": None,                  # mir-c: 无严谨度量
            "top_k": TOP_K,
            "sample_rate_hz": PANNS_SR,            # Pitfall 3 留痕
            "audioset_classes_total": 527,
            "mix_strategy": "drums+bass+other stems summed (vocals excluded — SER owns vocals)",
            "caveat": CAVEAT_PANNS,
            "sensible_rating_deferred_to": "Plan 06 user checkpoint",
        }
        write_result("mir_panns", "ep01", payload_panns)
        print(f"[mir] PANNs done: {len(panns_entries)} entries written")

    # Pitfall 9 final guard（both 模式下）：shot_id 顺序必须一致
    if model_choice == "both":
        mert_ids = [e["shot_id"] for e in mert_entries]
        panns_ids = [e["shot_id"] for e in panns_entries]
        assert mert_ids == panns_ids, (
            f"Pitfall 9 violation: MERT shot_ids {mert_ids[:5]}... "
            f"!= PANNs shot_ids {panns_ids[:5]}..."
        )
        print(f"[mir] head-to-head integrity GREEN: "
              f"MERT == PANNs == sample ({len(mert_ids)} shot_ids)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Phase 10 MIR spike —— MERT-v1-95M vs PANNs Cnn14 head-to-head "
                    "on ep01 drums+bass+other mix (methodology_c)"
    )
    ap.add_argument(
        "--smoke-only", type=int, default=0, metavar="N",
        help="仅跑前 N 段（Wave 1 快速验证，默认 0=跑全 30 段）",
    )
    ap.add_argument(
        "--model", choices=["mert", "panns", "both"], default="both",
        help="选择跑哪个模型（默认 both —— 头对头比较需要 both）",
    )
    args = ap.parse_args()
    try:
        run(model_choice=args.model, smoke_only=args.smoke_only)
    except Exception as e:  # noqa: BLE001  spike 容错
        # T-10-01：顶层异常兜底，所有 transformers / panns 异常字符串必经 _safe_error
        print(_safe_error(f"[mir] FATAL: {e}"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
