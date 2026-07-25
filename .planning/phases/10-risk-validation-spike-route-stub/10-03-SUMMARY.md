---
phase: 10-risk-validation-spike-route-stub
plan: 03
subsystem: spike/audio
tags: [spike, ser, sensevoice, dia-04, methodology-ab, af-02, af-03]
requires:
  - 10-01 (common.py: EP01_*, stratified_sample, parse_sensevoice_tags, write_result, _safe_error)
provides:
  - spike/audio/run_ser_sensevoice.py (throwaway reference script)
  - spike/audio/results/ser_sensevoice_ep01.json (empirical DIA-04 evidence for Plan 06)
affects:
  - .planning/research/audio-spike-report.md (Plan 06 reads this JSON)
  - .planning/PROJECT.md Key Decisions (Plan 06 locks DIA-04 ship/defer)
tech-stack:
  added: [funasr==1.3.29]
  patterns: [funasr AutoModel with fsmn-vad, methodology-ab self-consistency proxy]
key-files:
  created:
    - spike/audio/run_ser_sensevoice.py
    - spike/audio/results/ser_sensevoice_ep01.json
decisions:
  - methodology-ab chosen for SER spike (CONTEXT.md delegated Claude's Discretion; deferred manual annotation until self-consistency resolves ambiguity)
  - 3 SenseVoice instances with VAD max_single_segment_time variants (30000/25000/20000ms) as the perturbation source for self-consistency measurement
metrics:
  duration_sec: 95
  completed: 2026-07-25T19:05:00Z
  tasks: 3
  files_committed: 2
---

# Phase 10 Plan 03: SenseVoice SER Spike (DIA-04) Summary

Empirical macro-F1 proxy measurement for Chinese SER cross-domain risk: ran SenseVoice on 30 stratified ep01 vocals segments using methodology-ab (self-consistency across VAD-segmentation variants), producing the evidence Plan 06 needs to lock the DIA-04 ship/defer decision.

## Task 1: Methodology Choice — methodology_ab

Per the checkpoint resolution hint and CONTEXT.md `decisions → "Claude's Discretion"` delegation, the methodology choice was made autonomously (no blocking wait): **methodology_ab** — run self-consistency first; only request developer annotation if the result is borderline (40-50%).

Rationale: option (a+b) defers the ~1hr manual annotation labor until the cheap experiment shows whether the result is ambiguous. ep01 has no ground-truth emotion labels, so AF-02/AF-03 forbid fabricating a rigorous F1 number; self-consistency is an honest stability proxy with a clearly-framed caveat.

## Task 2: funasr Install + Spike Script

**funasr 1.3.29 install (Pitfall 1 clear):**
```
funasr 1.3.29 installed (transitive: librosa 0.11.0, jieba, oss2, etc.)
torch: 2.6.0+cu124 intact (assert '+cu124' in torch.__version__ passes)
```
No torch drift — WhisperX-style CUDA 12.8 poisoning did NOT occur.

**`spike/audio/run_ser_sensevoice.py`** (366 lines, Chinese module docstring, throwaway 参考脚本):
- Loads 3 SenseVoice AutoModel instances on CPU with VAD `max_single_segment_time` ∈ {30000, 25000, 20000} ms.
- Per shot: ffmpeg-slice vocals.wav to 16kHz mono tmp wav, call `generate(language="zh", use_itn=True, ban_emo_unk=False)` 3× (one per model instance), parse raw text via `parse_sensevoice_tags()` BEFORE `rich_transcription_postprocess` (Pitfall 2 prevention).
- Agreement per shot = max emotion count / 3 → `proxy_confidence` ∈ {0.333, 0.667, 1.0}.
- Metric: `self_consistency_pct = mean(proxy_confidence) × 100`.
- methodology-b path: if `ser_ground_truth_ep01.json` exists, compute per-class P/R/F1 + macro-F1; else `annotation_recommended=true` (does NOT auto-annotate).
- Caveat string contains literal `"calibrated estimate"` + explicit warning that self-consistency is NOT directly comparable to DIA-04 ≥50% macro-F1 accuracy threshold.
- `--smoke-only N` flag for Wave 1 fast iteration.
- All exception paths route through `_safe_error()` (T-10-01 token-redact mitigation).

Task 2 commit: `b612dfe` — `spike(ser): Phase 10 DIA-04 SenseVoice SER spike script (methodology_ab)`

## Task 3: Smoke + Full Run + Commit

**Smoke run (`--smoke-only 3`):** first-run ModelScope download of `iic/SenseVoiceSmall` (~1GB, anonymous, NO HF_TOKEN needed — A4 confirmed). 3 segments processed, JSON written, parser produced sensible output (shot 77 → HAPPY + Speech, clean text `"真的，说话算话。😊"`).

**Full run (30 segments, 50s wall-clock on CPU):**
- `sample_size=30`, `per_sample[30]` all valid
- `self_consistency_pct = 100.00` (every segment had 3/3 agreement across VAD variants)
- `metric_name = "self_consistency_pct"`, `methodology = "methodology_ab"`
- Model loaded from canonical ModelScope ID `iic/SenseVoiceSmall` (T-10-03 ✓)

**Emotion distribution across 30 segments:**

| Emotion | Count | Note |
|---------|-------|------|
| emo_unk | 9 | Silent clips where VAD found no speech — honest "no prediction" rather than defaulting to NEUTRAL |
| HAPPY | 8 | Coherent with promise/positive content (often with 😊 emoji) |
| NEUTRAL | 7 | Flat statements without strong affect |
| ANGRY | 6 | Coherent with conflict/threat content (often with 😡 emoji) |
| SAD / FEARFUL / DISGUSTED / SURPRISED | 0 each | Not predicted on this sample |

**Parse failures:** 0 hard failures. 9 segments produced `emo_unk` because VAD detected no speech (silent shots / BGM-only shots); this is honest behavior — `ban_emo_unk=False` was set explicitly to distinguish "no prediction" from "wrong prediction".

**Token leak grep gate:** clean — no `hf_<20+char>` / `token=` / `Bearer ` patterns in the committed JSON (T-10-01 ✓).

Task 3 commit: `30b8759` — `spike(ser): Phase 10 DIA-04 SenseVoice macro-F1 on ep01 vocals (methodology=methodology_ab)`

## Qualitative Sanity Check (NOT Ground Truth)

Spot-check of one entry per predicted emotion class (NO comparison to ground truth — these are model outputs only):

| shot_id | predicted | ASR text (truncated) | Coherent? |
|---------|-----------|----------------------|-----------|
| 77 | HAPPY | "真的，说话算话。😊" | YES — promise-keeping + smile emoji |
| 84 | ANGRY | "你打不过我31，我只能自己动手了。😡" | YES — threat + angry emoji |
| 79 | NEUTRAL | "前辈都怪我。" | YES — flat apology, no strong affect |
| 43 | emo_unk | (empty/SILENT) | YES — 1.83s clip, VAD found no speech |

The model is parsing Chinese text + emojis and producing semantically coherent emotion labels. This is NOT a substitute for ground-truth macro-F1 — it only confirms the parser pipeline is not obviously broken.

## annotation_recommended: TRUE

`spike/audio/results/ser_ground_truth_ep01.json` does NOT exist. Per methodology-ab:
- `ground_truth_macro_f1 = null`
- `ground_truth_per_class = null`
- `annotation_recommended = true`
- `ground_truth_note`: "ser_ground_truth_ep01.json not found —— true macro-F1 requires developer annotation of these 30 segments (~1hr labor). Re-run after annotating to enter methodology-b path."

The 30 segments are listed in `per_sample[]` with `shot_id`, `start_sec`, `end_sec`, `clean_text` — a developer can annotate them directly from the JSON without re-running the spike.

## Honest Framing of self_consistency_pct=100 (AF-02/AF-03)

**The 100% self-consistency does NOT imply 100% accuracy.** It only shows that SenseVoice is deterministic across VAD `max_single_segment_time` variants on this corpus. This is expected for short clips (<10s): all three VAD thresholds (30s/25s/20s) exceed clip length, so segmentation is identical across runs, and CPU inference is deterministic.

The `caveat` field in the result JSON explicitly states:
- The metric is a `"calibrated estimate"` of label stability, NOT a true macro-F1.
- Self-consistency is `"NOT directly comparable to the DIA-04 >=50% macro-F1 accuracy threshold"`.
- A model that deterministically predicts NEUTRAL on every clip would score 100% self-consistency yet unknown real accuracy.
- Plan 06 composes the final DIA-04 ship/defer judgment — this spike does NOT lock DIA-04 from `self_consistency_pct` alone.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] stratified_sample key mismatch**
- **Found during:** Task 2 script design (pre-write analysis)
- **Issue:** `common.py:stratified_sample` expects segment dicts with `start`/`end` keys, but `shots.json` uses `start_sec`/`end_sec`.
- **Fix:** Normalized shot dicts in `run_ser_sensevoice.py:run()` before calling `stratified_sample` (added `start`/`end` aliases). Did NOT modify `common.py` — keeps the Plan 01 contract intact for the other 3 spike scripts.
- **Files modified:** `spike/audio/run_ser_sensevoice.py` only.
- **Commit:** `b612dfe` (folded into Task 2 commit).

No other deviations — plan executed as written.

## Self-Check

```text
[✓] spike/audio/run_ser_sensevoice.py exists (366 lines, parses, all required tokens present)
[✓] spike/audio/results/ser_sensevoice_ep01.json exists (14795 bytes, sample_size=30)
[✓] commit b612dfe exists (Task 2: script)
[✓] commit 30b8759 exists (Task 3: results JSON)
[✓] funasr 1.3.29 installed; torch 2.6.0+cu124 intact
[✓] caveat contains "calibrated estimate" (grep gate)
[✓] no hf_<20+char> token patterns (grep gate)
[✓] methodology_ab recorded in SUMMARY (Task 1 verify gate)
[✓] schema check passes (results_schema_check.py)
```

## Self-Check: PASSED
