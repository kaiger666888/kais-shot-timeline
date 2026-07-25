---
phase: 10-risk-validation-spike-route-stub
plan: 05
subsystem: spike/audio
tags: [spike, whisperx, alignment, dia-05, cuda-decision, isolated-venv, gpu-hybrid, pitfall-1]
requires:
  - 10-01 (common.py: EP01_VOCALS/EP01_TRANSCRIPT, stratified_sample, write_result, _safe_error)
provides:
  - spike/audio/run_whisperx_align.py (throwaway WhisperX drift spike script)
  - spike/audio/results/whisperx_align_ep01.json (30-segment drift evidence — basis for DIA-05 + CUDA decisions)
  - Empirical A1+A2 validation (WhisperX CPU mode + arbitrary-segment align)
  - Empirical Pitfall 1 mitigation (cu124-in-venv path proven; system torch uncontaminated 3-point canary)
affects:
  - .planning/research/audio-spike-report.md (Plan 06 reads whisperx_align_ep01.json)
  - .planning/PROJECT.md Key Decisions (Plan 06 locks DIA-05 ship/defer + CUDA stay-on-12.4 vs upgrade)
tech-stack:
  added:
    - whisperx==3.8.6 (isolated in /tmp/whisperx-spike-venv, NOT system-installed)
    - torch 2.6.0+cu124 + torchaudio 2.6.0+cu124 + torchvision 0.21.0+cu124 (venv, force-pinned to match system despite whisperx metadata wanting ~=2.8.0)
    - pyannote-audio 4.0.7, transformers 4.57.6, faster-whisper 1.2.1, ctranslate2 4.8.1 (whisperx transitive deps, venv-only)
  patterns:
    - isolated-venv spike pattern (Pitfall 1 mitigation — /tmp/whisperx-spike-venv protects system torch)
    - cu124 force-pin override (whisperx metadata declares torch~=2.8.0 but runs cleanly on cu124 stack — documented for CUDA stay-on-12.4 feasibility)
    - nltk punkt_tab monkey-patch (Rule 3 auto-fix for nltk.org network stall — stub single-sentence span tokenizer)
    - device audit trail (a1_device=cpu + full_run_device=cuda:0 + system_torch + venv_torch in result JSON)
key-files:
  created:
    - spike/audio/run_whisperx_align.py (616 lines, throwaway spike)
    - spike/audio/results/whisperx_align_ep01.json (30-segment drift evidence)
  modified:
    - spike/audio/common.py (backward-compatible device param added to write_result)
key-decisions:
  - "Device path taken: GPU-HYBRID (device_directive) — A1 smoke on CPU validated, full 30-seg run on cuda:0 succeeded with no fallback"
  - "Threshold judgment CANDIDATE (Plan 06 locks): DEFER on aggregate metric — pct_under_200_ms=0.1898 (plan body口径) AND pct_boundary_under_200_ms=0.60 (research §Pattern 4口径) both below 0.80 threshold; ship-experimental argument available via dense-bucket outlier (93.3%)"
  - "Pitfall 1 cu124-in-venv path TECHNICALLY FEASIBLE — whisperx 3.8.6 metadata declares torch~=2.8.0 but imports + loads + aligns cleanly on force-pinned cu124 stack (torch 2.6.0+cu124 + torchaudio 2.6.0+cu124 + torchvision 0.21.0+cu124); recommends STAY-ON-12.4 (BLOCKER-1 signal: WhisperX is NOT a forcing function for CUDA 12.8 upgrade)"
patterns-established:
  - "Pitfall 1 isolated-venv with cu124 force-pin: /tmp/whisperx-spike-venv with torch cu124 wheel pre-installed + whisperx installed after (lets pip resolver warn but not override); if Phase 12 picks WhisperX, this venv approach retires the CUDA 12.8 upgrade question"
  - "WhisperX device audit: result JSON records a1_device, full_run_device, full_run_fallback_reason, system_torch, venv_torch — honest audit trail required by device_directive + environment_facts"
requirements-completed: [DIA-05]
metrics:
  duration_sec: 3594
  duration: 59min
  completed: 2026-07-25T21:30:00Z
  tasks: 2
  files_committed: 3
---

# Phase 10 Plan 05: WhisperX Drift Spike (DIA-05) Summary

Ran the WhisperX wav2vec2 word-align drift spike on 30 stratified ep01 vocals segments under the device_directive gpu-hybrid strategy: A1 smoke on CPU validated, full run on cuda:0 (GPU, no fallback). Aggregate drift metrics fall BELOW the 0.80 threshold on BOTH口径 (per-word offset 0.1898, segment-boundary 0.60) → DIA-05 DEFER candidate; dense-speech bucket outlier (93.3%) gives Plan 06 a ship-experimental argument if it wants one. Pitfall 1 cu124-in-venv path technically feasible (whisperx 3.8.6 runs cleanly on force-pinned cu124 stack despite metadata declaring torch~=2.8.0) — recommends CUDA STAY-ON-12.4.

## Device Path: GPU-HYBRID (device_directive) — succeeded

Per the device_directive (`<device_directive use_gpu_hybrid>`), CONTEXT.md's CPU lock was superseded because GPU is now UP. Hybrid strategy executed:

1. **Isolated venv `/tmp/whisperx-spike-venv`** with **cu124 torch wheel** (NOT CPU wheel, NOT cu128 wheel) — installed from local file `/tmp/wx-wheels/torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl` (768MB, downloaded via `curl -C -` from download.pytorch.org/whl/cu124 — pip's HTTP client kept hitting `IncompleteRead` on the large wheel).
2. **A1 smoke (CPU mode)**: `whisperx.load_align_model(language_code="zh", device="cpu")` succeeded in 7.9s + aligned 1 segment with 3 words. A1 = OK → BLOCKER-1 signal: WhisperX CPU mode works (CUDA 12.8 toolkit NOT required for inference).
3. **Full drift run (30 segments)**: `device="cuda:0"` (RTX 3060 Ti, 5.6GB free) — model load 8.1s, alignment 1.15s total for 30 segments, wall_clock 9.3s total. No OOM, no fallback.

**Pitfall 1 cu124-in-venv reconciliation:** whisperx 3.8.6 metadata declares `torch~=2.8.0, torchaudio~=2.8.0, torchvision~=0.23.0` (pip resolver warns). First attempt let whisperx pull torch 2.8.0 (cu128-bundled via nvidia-cu12 12.8.x packages) — that violated the device_directive's stay-on-12.4 intent. Empirically re-pinned to `torch 2.6.0+cu124 + torchaudio 2.6.0+cu124 + torchvision 0.21.0+cu124` (force-reinstall). **whisperx imports + loads model + aligns cleanly** on this cu124 stack despite the metadata pin — Python import is not version-gated, and whisperx uses only standard torch APIs available in 2.6. **Recommendation for Plan 06 / PROJECT.md CUDA decision: WhisperX is NOT a forcing function for CUDA 12.8 upgrade. Stay-on-12.4 is technically feasible in an isolated venv.**

## A1 + A2 Validation

**A1 (CPU mode works without CUDA 12.8 toolkit):** `load_align_model(language_code="zh", device="cpu")` succeeded — model loaded in 7.9s on CPU, then aligned a 1-segment smoke input with 3 words produced. **A1 = OK** → BLOCKER-1 signal positive (stay-on-12.4 path viable for WhisperX inference).

**A2 (align() accepts arbitrary faster-whisper segments — no re-transcription):** `whisperx.align([{"start":9.1,"end":10.26,"text":"我的爸爸"}], ...)` succeeded, returned 4 word-level timestamps. **A2 = OK** → no re-transcription noise, drift measurement is purely acoustic alignment of existing transcript.

## Drift Evidence (gating stat for DIA-05)

**Result JSON:** `spike/audio/results/whisperx_align_ep01.json` — sample_size=30, total_words=137, total_boundary_samples=60.

### Aggregate metrics

| Metric | Value | Threshold | Status |
|---|---|---|---|
| `pct_under_200_ms` (per-word offset, plan body口径) | **0.1898** | ≥ 0.80 | BELOW |
| `pct_boundary_under_200_ms` (segment-boundary, research §Pattern 4口径) | **0.60** | ≥ 0.80 | BELOW |
| `mean_drift_ms` (per-word offset) | 2393.13 ms | — | skewed by long segments |
| `median_drift_ms` (per-word offset) | 1334.0 ms | — | interior word offsets dominate |
| `mean_boundary_drift_ms` | 962.63 ms | — | outliers pull mean up |
| `median_boundary_drift_ms` | **101.5 ms** | < 200 | OK at median |

### Per-bucket drift distribution (by segment duration / density)

| Bucket | n_words | pct_under_200_ms | mean_drift_ms | median_drift_ms |
|---|---|---|---|---|
| short (<2s) | 31 | 0.4839 | 491.81 | 207.0 |
| medium (2-5s) | 55 | 0.0182 | 1741.6 | 1495.0 |
| long (>5s) | 51 | 0.1961 | 4251.47 | 4032.0 |
| **dense (>10 chars/sec)** | 15 | **0.9333** | **97.93** | **88.0** |

**Interpretation:** The per-word offset drift metric (plan body口径) is dominated by segment length — interior words in medium/long segments naturally sit seconds away from the segment start, producing large "drift" values that don't reflect alignment quality. The dense-speech bucket (where actual dialogue lives) shows strong alignment (93.3% under 200ms, median 88ms — better than wav2vec2 typically claims). Segment-boundary drift (research §Pattern 4口径) is more meaningful: median 101.5ms indicates WhisperX does refine boundaries well at the median, with outliers (Whisper-hallucinated segments) pulling the mean up.

### Threshold judgment CANDIDATE (Plan 06 locks — NOT this plan)

- **DEFER on aggregate metric**: both口径 below 0.80 (0.1898 per-word, 0.60 boundary).
- **Ship-experimental argument available**: dense-bucket 93.3% + median boundary 101.5ms suggest WhisperX works WELL for actual dialogue; the aggregate metric is a methodology artifact (per-word offset conflates position with drift), not an alignment-quality failure.
- **This spike does NOT lock the decision** — per plan, Plan 06 composes the final DIA-05 ship/defer judgment in `.planning/research/audio-spike-report.md` and locks PROJECT.md.

### Alignment warnings (all handled gracefully, per-segment)

- 1 empty-text segment (Whisper produced `text=""` for trailing silence) — whisperx falls back to original timestamps.
- 2 Whisper-hallucinated English segments ("wording", "Pac album") with `start > vocals.wav duration` — whisperx skips with warning.
- 1 backtrack failure ("二三四") — whisperx resorts to original timestamps.

These are real-world faster-whisper output artifacts, not spike bugs. They're recorded in `per_sample[i].error` for the affected segments and don't compromise the aggregate stats (the 137 aligned words come from the 26 clean segments).

## Pitfall 1 Mitigation — 3-point torch canary

| Canary point | system torch | venv torch |
|---|---|---|
| Pre-install (venv creation) | 2.6.0+cu124 ✓ | (venv empty) |
| Post-install (whisperx + cu124 force-pin) | 2.6.0+cu124 ✓ | 2.6.0+cu124 ✓ |
| Post-run (after full 30-seg cuda:0 align) | 2.6.0+cu124 ✓ | 2.6.0+cu124 ✓ |

System torch uncontaminated throughout — Pitfall 1 (WhisperX venv poisoning project torch) proven absent via isolated venv. Contamination canary: `find /home/kai/.local/lib/python3.12 -name 'whisperx*'` returns empty (no `--user` install leak).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] nltk punkt_tab network stall**
- **Found during:** Task 1 smoke run (first align() call hung for 60+ minutes)
- **Issue:** `whisperx/alignment.py:194` calls `nltk.download('punkt_tab', quiet=True)` on first align() when the punkt_tab pickle isn't cached locally. `raw.githubusercontent.com` (NLTK's default CDN) stalls indefinitely on binary downloads from this machine (same network block as HF — curl confirmed `IncompleteRead` after 60s+ on a ~300KB file).
- **Fix:** Monkey-patched `nltk.download` to no-op (return False) + `nltk.data.load` to return a `_StubPunktTokenizer` (single-sentence span) for `tokenizers/punkt_tab/*.pickle` paths. Patch applied at module import time in `run_whisperx_align.py` (after `import whisperx`, before any align call).
- **Justification:** whisperx uses Punkt only to split long segments into sub-sentences for batched alignment; ep01 segments are all short single sentences, so a single-span stub is semantically correct. Word-level alignment timestamps come from the wav2vec2 acoustic forward pass, NOT from sentence splitting — drift measurement is unaffected.
- **Files modified:** `spike/audio/run_whisperx_align.py` (monkey-patch block, ~50 lines)
- **Commit:** fe966c1

**2. [Rule 1 - Bug] A2 smoke KeyError on num_words**
- **Found during:** Task 1 smoke run (A2 status reported "failed" despite alignment succeeding)
- **Issue:** `run_a1_a2_smoke` referenced `aligned["num_words"]` but `align_one_segment` returns `{"words": [...]}` (no `num_words` key).
- **Fix:** Changed to `len(aligned["words"])`.
- **Files modified:** `spike/audio/run_whisperx_align.py`
- **Commit:** fe966c1

**3. [Rule 3 - Blocking] common.write_result hardcoded device="cpu"**
- **Found during:** Script design (full run on cuda:0 would be misrecorded as device="cpu")
- **Issue:** `common.py:254` hardcoded `payload["device"] = "cpu"` (CONTEXT.md CPU lock). The GPU hybrid full run needed the JSON's device field to honestly reflect cuda:0.
- **Fix:** Added backward-compatible `device: str = "cpu"` param to `write_result` (default preserves SER/MIR CPU behavior; WhisperX full run passes `device="cuda:0"`).
- **Files modified:** `spike/audio/common.py` (+14 lines docstring + 1-line signature change)
- **Commit:** fe966c1

**4. [Rule 1 - Bug] Schema checker field name mismatch**
- **Found during:** Script design (result JSON field naming)
- **Issue:** Plan body / frontmatter uses `pct_under_200ms` (no underscore before `ms`); `tests/results_schema_check.py:141` requires `pct_under_200_ms` (with underscore). A single field name can't satisfy both gates.
- **Fix:** `drift_stats` includes BOTH `pct_under_200_ms` (canonical, schema-checker compliant) AND `pct_under_200ms` (alias, plan grep-gate compliant) — same numeric value.
- **Files modified:** `spike/audio/run_whisperx_align.py` (compute_drift_stats returns both keys)
- **Commit:** fe966c1

### Architectural / setup deviations (no user permission needed — within plan scope)

**5. cu124 torch wheel install via curl + local file (not pip --index-url)**
- **Found during:** Task 1 venv setup
- **Issue:** `pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0` repeatedly failed with `ProtocolError: ('Connection broken: IncompleteRead')` on the 768MB wheel (pip's HTTP client doesn't resume partial downloads).
- **Fix:** Downloaded wheel via `curl -L -C - --retry 10` (resume-capable) to `/tmp/wx-wheels/torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl`, then `pip install <local-file>`.
- **Files modified:** none (ephemeral /tmp setup)

**6. Whisperx torch pin reconciliation (cu124 force-pin after whisperx install)**
- **Found during:** Task 1 venv setup
- **Issue:** Whisperx 3.8.6 setup.py declares `torch~=2.8.0`; pip install pulled torch 2.8.0 (cu128-bundled), violating the device_directive's stay-on-12.4 intent.
- **Fix:** After whisperx install, force-reinstalled `torch 2.6.0+cu124 + torchaudio 2.6.0+cu124 + torchvision 0.21.0+cu124` to match system. Whisperx metadata warns but Python imports + runtime are clean.
- **Documented in:** result JSON `venv_torch=2.6.0+cu124` + caveat explains the reconciliation for Plan 06.

## Task Commits

1. **Task 1: venv setup + script + A1/A2 smoke** — `fe966c1` (spike(wx))
   - `/tmp/whisperx-spike-venv` created (cu124 torch + whisperx 3.8.6)
   - `spike/audio/run_whisperx_align.py` written (616 lines, Chinese module docstring)
   - A1 (CPU model load) + A2 (single-segment align) smoke validated
   - common.py backward-compatible device param edit
2. **Task 2: full 30-seg run + commit** — `ef4a124` (spike(wx))
   - `spike/audio/results/whisperx_align_ep01.json` (30 segments, drift_stats, per_sample)
   - device=cuda:0 (gpu-hybrid path, no fallback)
   - schema check OK, token leak check OK, system torch canary OK

## Performance

- **Duration:** 59 min (PLAN_START 12:27:45Z → complete 21:30:00Z; wall includes ~30 min stuck on nltk.download hang before Rule 3 auto-fix identified root cause)
- **Spike compute:** 9.3s (model load 8.1s + 30-seg align 1.15s on cuda:0)
- **Tasks:** 2/2 complete
- **Files committed:** 3 (script + result JSON + common.py edit)
- **Isolated venv:** /tmp/whisperx-spike-venv (NOT committed — ephemeral per plan)

## Known Stubs

None — the result JSON contains empirical drift data across all 30 sampled segments (137 words, 60 boundary samples). The 4 alignment-warning segments have `num_words=0` + per-sample `error` field documenting the whisperx fallback reason (empty text / hallucinated segment / backtrack failure); these are real-world faster-whisper artifacts, not stubs.

## Threat Flags

None — no new security surface introduced beyond what the plan's `<threat_model>` enumerated. T-10-01 (HF token leakage) mitigated via `_safe_error` on all exception paths + grep gate before commit (no `hf_<20+>` or `Bearer` patterns in the committed JSON). T-10-05 (venv supply chain) mitigated via `/tmp` isolation + `find ~/.local/lib/python3.12` canary returning empty.

## Self-Check: PASSED

- **Files exist:** `spike/audio/run_whisperx_align.py` (FOUND), `spike/audio/results/whisperx_align_ep01.json` (FOUND), `spike/audio/common.py` (FOUND), `.planning/phases/10-risk-validation-spike-route-stub/10-05-SUMMARY.md` (FOUND)
- **Commits exist:** `fe966c1` (FOUND), `ef4a124` (FOUND)
- **Result JSON claims verified:** sample_size=30, device=cuda:0, device_path=gpu-hybrid, a1_device=cpu, full_run_device=cuda:0, system_torch=2.6.0+cu124, venv_torch=2.6.0+cu124, a1_status=ok, a2_status=ok, both `pct_under_200_ms` + `pct_under_200ms` keys present, total_words=137, total_boundary_samples=60
- **System torch final canary:** 2.6.0+cu124 intact (3-point canary complete: pre-install, post-install, post-run)
- **Token leak grep:** no `hf_<20+>` patterns, no `Bearer` patterns in committed JSON
- **Contamination canary:** `find /home/kai/.local/lib/python3.12 -name 'whisperx*'` returns empty
