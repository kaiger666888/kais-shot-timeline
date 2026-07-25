# Phase 10: Risk-Validation Spike + Route Stub - Research

**Researched:** 2026-07-25
**Domain:** ML risk-validation spike (Chinese SER / polyphonic MIR / WhisperX word-drift on CPU) + cross-repo Express route stub
**Confidence:** **HIGH** overall — model-loading patterns verified against current official model cards (SenseVoice / MERT / PANNs / WhisperX / pyannote) within this session; **MEDIUM** on whether the proposed pragmatic macro-F1 proxy methodology is acceptable to the user (needs plan-time confirmation); **MEDIUM** on whether the CPU-only spike will run within acceptable wall-clock (sample-size dependent).

## Summary

Phase 10 is **NOT a production-code phase.** It produces (a) a throwaway spike report at `.planning/research/audio-spike-report.md` that empirically de-risks DIA-04 / DIA-05 / MUS-04 against the threshold table in REQUIREMENTS.md, (b) a ROUTE-01 cross-repo Express stub at `kais-aigc-platform:src/routes/production/audio-analysis/{index.ts,_shared/config.ts}` that gives Phase 12's `call_audio_analysis.py` a target URL + envelope before any ML lands, and (c) 4 locked outcomes in PROJECT.md Key Decisions. **Zero producer pipeline code, zero contract changes, zero new ML deps in the shot-timeline repo.** This mirrors v1.1 Phase 7 DINOv2 τ spike ("先证模型、再立契约") — non-negotiable invariant #1.

The 4 spike models all run on CPU as **accuracy-only measurements** (per CONTEXT.md `code_context` GPU-DOWN note + user decision). Accuracy metrics (macro-F1, mAP, drift %) are device-independent. Wall-clock is NOT a success criterion. The WhisperX word-align step is the only model that requires an **isolated venv** because its PyPI deps hard-conflict with the project's `torch 2.6.0+cu124` runtime; SenseVoice/MERT/PANNs/pyannote all run cleanly on cu124 and can be installed in the system environment (or a separate non-conflicting venv).

**Primary recommendation:** Structure the spike as 4 independent throwaway Python scripts in `spike/audio/` (NOT `analysis/` — `analysis/` is producer code) that each (i) load one pinned model on CPU, (ii) read ep01's cached v1.1 intermediates (`stems/htdemucs/<ep01>/{vocals,drums,bass,other}.wav`, `transcript.json`, `audio_analysis.json` — all confirmed present at `output/虫虫武侠小故事《小江湖》第01话…/`), (iii) emit a deterministic JSON results blob to `spike/audio/results/<model>_<fixture>.json`, then a 5th aggregator script collates them into the report. ROUTE-01 mirrors `shot-analysis/index.ts` line-for-line in envelope shape (`{"code":200,"data":{...},"message":"..."}` via `@/lib/responseFormat.ts:success`) with a `STUB_MODE` env flag that returns schema-shaped empty data when ML is unloaded.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (verity copy — research must honor these, not explore alternatives)

- **Episode: ep01** (`output/虫虫武侠小故事《小江湖》…第01话…`) — full v1.1 intermediates already cached. **Zero re-extraction.** Spike reads cached assets only; results directly comparable to v1.1 Phase 7 DINOv2 τ spike.
- **WhisperX word-align: isolated venv, CPU.** WhisperX's CUDA-12.8-hungry deps must NOT poison the project's `torch 2.6.0+cu124` runtime. Run wav2vec2 align on CPU. The CUDA 12.8-upgrade-vs-stay-on-12.4 decision is made from the resulting drift number, not install convenience.
- **MUS-04 MIR: MERT-v1-95M + PANNs/HTS-AT head-to-head** on ep01 `drums+bass+other` mix. Run BOTH models on the SAME segments; pick the winner via measured mAP against the ≥0.30/<0.20 threshold.
- **ROUTE-01 stub: new `feat/audio-analysis-route` branch** in kais-aigc-platform, mirroring `feat/shot-analysis-route` sibling. Envelope `{"code":200,"data":{...}}` via `@/lib/responseFormat.ts:success`. Stub mode returns schema-shaped empty data with ML unloaded.

### Claude's Discretion (research recommends, planner picks)

- **Exact N for WhisperX drift sample** — research recommends **≥30 segments spanning short (<2s) / medium (2-5s) / long (>5s) / dense-speech (>10 chars/sec) buckets** to make the `<200ms on ≥80%` stat robust against the 155 total segments in ep01 transcript.json (a 30-segment stratified sample = ~19% of the population, comfortably statistical while keeping CPU wall-clock bounded).
- **SenseVoice / MERT / PANNs / pyannote checkpoint pins** — research provides verified pinned IDs (see §Standard Stack).
- **Spike script location** — research recommends `spike/audio/` (NOT `analysis/` — preserves the `analysis/` = producer-code convention). Commit `.planning/research/audio-spike-report.md` as the deliverable; commit scripts as throwaway reference (so the report is reproducible) but do NOT route them through the pipeline.
- **macro-F1 methodology** — Chinese SER has no ep01 ground-truth emotion labels. Research proposes **(a) self-consistency + qualitative review as primary** (zero extra labor, honest caveat) with **(b) optional developer-annotated stratified sample** as a stronger fallback if the user wants a more rigorous number. The report MUST state the chosen methodology + caveat that without ground truth the number is a calibrated estimate, not a true F1 (AF-02/AF-03 anti-fabrication).

### Deferred Ideas (OUT OF SCOPE — ignore completely)

- Live ML round-trip through the route (route host loading SenseVoice/WhisperX/MERT/PANNs) — deferred to post-merge smoke check, mirroring v1.1 Phase 7 CAST-01..04/08 deferred pattern.
- GPU-derived latency/VRAM profiling — deferred until GPU is back (post-reboot). Phase 10 success criteria are accuracy-only.
- DIA-06 face-voice auto speaker→character — v1.3 differentiator (v1.2 always HITL).

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **ROUTE-01** | `audio-analysis` route stub — envelope mirrors shot-analysis `{"code":200,"data":{...}}` so producer client can integrate-test even with models unloaded | §Architecture Patterns → ROUTE-01 Stub Structure (verified against live `kais-aigc-platform/src/routes/production/shot-analysis/index.ts` + `src/lib/responseFormat.ts` read this session); cross-repo branch `feat/audio-analysis-route` create + router.ts mounting in `/api/production/audio-analysis` (verified router mount pattern). |
| **DIA-04** (de-risked, CONDITIONAL) | Chinese SER macro-F1 ≥50% ship / <40% defer / 40-50% ship-nullable+confidence | §Spike Architecture → SER script (SenseVoice via funasr, emotion tag extraction via `rich_transcription_postprocess`); §Metric Methodology → pragmatic macro-F1 with self-consistency proxy + caveat required by AF-02/AF-03. |
| **DIA-05** (de-risked, CONDITIONAL) | WhisperX word-level drift <200ms on ≥80% segments ship experimental / else segment-only | §Spike Architecture → WhisperX align script (isolated venv, CPU, wav2vec2 align on existing faster-whisper segments — no re-transcription needed); §Metric Methodology → drift measured against `transcript.json` segment boundaries as ground truth. |
| **MUS-04** (de-risked, CONDITIONAL) | Polyphonic instrument mAP ≥0.30 ship / <0.20 defer / 0.20-0.30 ship-nullable+confidence; MERT-vs-PANNs pick deferred to Phase 10 | §Spike Architecture → MIR script runs BOTH MERT-v1-95M and PANNs Cnn14 on the SAME drums+bass+other mix segments; §Metric Methodology → head-to-head mAP with manual annotation of N=30 segments as pragmatic ground truth. |

</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Spike model loading (SenseVoice/MERT/PANNs/pyannote/WhisperX) | Throwaway Python scripts (NOT pipeline) | Isolated venv for WhisperX only | Models run in-process for accuracy measurement; never wired into `run_pipeline.py`. WhisperX isolated because its deps conflict with project torch 2.6.0+cu124. |
| Reading ep01 cached intermediates | Filesystem (read-only) | — | Spike reads `stems/htdemucs/<ep01>/*.wav` + `transcript.json` + `audio_analysis.json`; never writes back; never re-runs detection/separation/transcription. |
| ROUTE-01 stub HTTP envelope | kais-aigc-platform Express route (cross-repo) | `@/lib/responseFormat.ts:success` | Stub lives in the route host repo (where ML will eventually land); shot-timeline repo takes zero new ML deps. |
| ROUTE-01 stub-mode empty data | Route-side `STUB_MODE` env flag | — | When ML is unloaded (the default in Phase 10), route returns schema-shaped empty arrays/objects so the envelope round-trips. Phase 12's client integrates against this shape. |
| Spike report aggregation | Markdown report (`.planning/research/audio-spike-report.md`) | Per-model JSON results in `spike/audio/results/` | Report is the deliverable; JSON files are committed alongside scripts for reproducibility. |
| Outcome locking | PROJECT.md Key Decisions + STATE.md | — | Empirical evidence → 4 locked decisions (CUDA path + 3 conditional reqs). Non-negotiable invariant #1: contract does NOT lock until these are in PROJECT.md. |

---

## Standard Stack

### Spike Side — Throwaway Scripts (`spike/audio/`)

| Library | Version (verified this session) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `funasr` | 1.3.29 (PyPI latest, verified via `pip index versions`) | SenseVoice via `AutoModel` — SER + AED in one pass | Official SenseVoice runtime (README "funasr>=1.3.26 required"). slopcheck **[OK]**. Loads `iic/SenseVoiceSmall` (ModelScope ID) or `FunAudioLLM/SenseVoiceSmall` (HF ID) with `trust_remote_code=True`. Works on `torch 2.6.0+cu124` — no CUDA 12.8 needed. `[VERIFIED: PyPI registry]` |
| `transformers` | 5.6.2 (already installed in project env) | MERT-v1-95M via `AutoModel.from_pretrained` + `Wav2Vec2FeatureExtractor` | Already in the project env. MERT card confirms `trust_remote_code=True`, 24kHz sample rate, 13 hidden layers. `[VERIFIED: HF model card m-a-p/MERT-v1-95M fetched this session]` |
| `panns-inference` | 0.1.1 (PyPI, 11 versions over years — established) | Cnn14 AudioSet tagging (527-class polyphonic) | Official PANNs Python interface by qiuqiangkong. **Default loads `Cnn14_mAP=0.431.pth` — NOT HTS-AT.** HTS-AT checkpoint requires explicit `checkpoint_path` + the larger `audioset_tagging_cnn` repo. slopcheck **[OK]**. `[VERIFIED: PyPI + GitHub README qiuqiangkong/panns_inference fetched this session]` |
| `pyannote.audio` | 4.0.7 (PyPI latest) | Standalone diarization (community-1 + 3.1) | Official pyannote toolkit. 3.1 removed the `onnxruntime` dep that plagued 3.0. Works on cu124. slopcheck **[OK]** (no source repo linked — verify license terms independently). `[VERIFIED: PyPI registry + HF model card]` |
| `librosa` | 0.11.0 (PyPI latest stable) | Resampling + onset detection + sample-rate normalization | Industry-standard Python audio DSP. Already transitively present via project deps. slopcheck timed out transiently — package is well-established (~10 years of releases). `[VERIFIED: PyPI registry]` |
| `whisperx` | 3.8.6 (PyPI latest — install name is `whisperx`, NOT `m-bain/whisperx` which is the GitHub slug) | Word-level alignment + diarization (isolated venv only) | Official WhisperX PyPI package. Hard-requires CUDA 12.8 for **GPU** mode; CPU mode (`device="cpu", compute_type="int8"`) is the documented escape hatch (README "To run on CPU instead of GPU"). `[VERIFIED: PyPI + GitHub README m-bain/whisperX fetched this session]` |
| `torch` (already installed) | 2.6.0+cu124 (project runtime, verified) | Tensor backend for SenseVoice/MERT/PANNs/pyannote | Project's existing runtime. CUDA unavailable this session (`cuda available: False`) due to driver/library mismatch — spike runs CPU-only as user decided. |

**WhisperX isolated venv rationale:** WhisperX's PyPI deps pull `torch>=2.6` with the **CUDA 12.8** wheel tag, which conflicts with the project's installed `torch 2.6.0+cu124`. An isolated venv (created with `python3 -m venv` per PEP 668 / externally-managed-environment) gives WhisperX its own torch CPU wheel that does NOT touch `/usr/lib/python3.12` or `~/.local/lib/python3.12`.

**Installation (NOT run in Phase 10 plan — planner decides whether to install once vs. per-run):**

```bash
# Phase 10 spike-side install (NOT producer code; NOT committed to pipeline)
# System env (SenseVoice/MERT/PANNs/pyannote — compatible with cu124):
pip install --break-system-packages funasr==1.3.29 panns-inference==0.1.1 \
  "pyannote.audio==4.0.7" "librosa==0.11.0"
# transformers 5.6.2 + torch 2.6.0+cu124 already present

# WhisperX in ISOLATED venv (CPU wheel, NOT cu124):
python3 -m venv /tmp/whisperx-spike-venv
/tmp/whisperx-spike-venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
/tmp/whisperx-spike-venv/bin/pip install whisperx==3.8.6
```

### Route Stub Side — Cross-Repo (`kais-aigc-platform`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `express` | already on route host | Router + handler | Mirrors `shot-analysis/index.ts` exactly. |
| `zod` | already on route host | Body schema validation | Mirrors `shot-analysis/index.ts:40-49` pattern. |
| `@/lib/responseFormat.ts` | already on route host | Envelope `{code,data,message}` | Read this session: `success(data, message)` returns `{code:200, data, message:"成功"}`. Stub MUST use this exact helper. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `iic/SenseVoiceSmall` (ModelScope) | `FunAudioLLM/SenseVoiceSmall` (HuggingFace) | Same weights, different hub. ModelScope is canonical per funasr; HF works if user has HF_TOKEN but no ModelScope account. Recommend `iic/SenseVoiceSmall` (default). |
| PANNs Cnn14 (default `panns-inference`) | HTS-AT (from `audioset_tagging_cnn` repo) | Cnn14 is the documented default of the PyPI package and runs out-of-the-box; HTS-AT is more accurate per paper but requires cloning the larger repo + explicit checkpoint_path. **Spike runs BOTH** — Cnn14 via panns-inference, HTS-AT via audioset_tagging_cnn if time permits. |
| `pyannote/speaker-diarization-community-1` (CC-BY-4.0, WhisperX default) | `pyannote/speaker-diarization-3.1` (gated, MIT code) | Community-1 has no ToU gating friction; 3.1 is the gated standard. Spike uses **community-1** (matches WhisperX default); 3.1 only if community-1 DER is unacceptable. |
| `m-a-p/MERT-v1-95M` | `m-a-p/MERT-v1-330M` | STACK.md chooses 95M for VRAM discipline (production concern). For Phase 10 CPU spike, **95M is also faster on CPU** — same accuracy tier. |

---

## Package Legitimacy Audit

> slopcheck 0.6.1 available at `/home/kai/.local/bin/slopcheck`. Run this session.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `funasr` | PyPI | mature (130+ versions) | high (ModelScope flagship) | github.com/modelscope/FunASR | **[OK]** | Approved |
| `panns-inference` | PyPI | mature (11 versions, since 2020) | moderate | github.com/qiuqiangkong/panns_inference | **[OK]** | Approved |
| `pyannote.audio` | PyPI | mature (20+ versions) | high | github.com/pyannote/pyannote-audio (slopcheck flagged "no source repo linked" — false negative, repo exists) | **[OK]** | Approved (license verify independently) |
| `librosa` | PyPI | mature (10+ years, 30+ versions) | very high | github.com/librosa/librosa | transient timeout | Approved (well-established) |
| `whisperx` | PyPI | mature (32 versions) | high | github.com/m-bain/whisperX | (registry timeout on re-run; first run confirmed `m-bain/whisperx` is the SLOP form — correct name is bare `whisperx`) | Approved under correct name |

**Packages removed due to slopcheck [SLOP] verdict:** `m-bain/whisperx` (this is a GitHub slug, not a PyPI package name — the correct PyPI name is bare `whisperx`).

**Packages flagged as suspicious [SUS]:** none.

**Note on `m-bain/whisperx` SLOP verdict:** slopcheck correctly flagged `m-bain/whisperx` as hallucinated because PyPI does not have a package by that name — the canonical PyPI package is bare `whisperx` (verified: `pip index versions whisperx` returns `whisperx (3.8.6)`). This is a known name-confusion vector. The planner MUST specify the install command as `pip install whisperx` (NOT `pip install m-bain/whisperx`).

---

## Architecture Patterns

### Spike Script Architecture

**Directory layout (research recommends `spike/audio/`):**

```
spike/audio/
├── README.md                          # how to run, reproducibility notes
├── common.py                          # shared: ep01 fixture loader, sample stratifier, results writer
├── run_ser_sensevoice.py              # DIA-04 spike (SenseVoice emotion on vocals.wav segments)
├── run_mir_head_to_head.py            # MUS-04 spike (MERT-v1-95M vs PANNs Cnn14 on drums+bass+other mix)
├── run_whisperx_align.py              # DIA-05 spike (isolated-venv WhisperX wav2vec2 align on existing transcript)
├── run_diarize_pyannote.py            # optional 5th spike (pyannote community-1 DER — informational, not a gate)
├── aggregate_report.py                # collates per-model JSON → markdown sections of audio-spike-report.md
└── results/                           # committed JSON blobs for reproducibility
    ├── ser_sensevoice_ep01.json
    ├── mir_mert_ep01.json
    ├── mir_panns_ep01.json
    ├── whisperx_align_ep01.json
    └── diarize_pyannote_ep01.json
```

**Why `spike/audio/` and NOT `analysis/` or `.planning/research/spike/`:** `analysis/` is producer code (`call_shot_analysis.py`, `call_reid.py`) wired into the pipeline; spike scripts are throwaway. `.planning/research/spike/` buries them inside `.planning/` which is git-tracked but feels like doc-only. `spike/audio/` at the repo root mirrors how `audio/gen_audio_prompts.py` (the v1.1 quick task that became PROMPT-03 input) lived — top-level throwaway scripts that get retired post-milestone. Planner's discretion per CONTEXT.md, but this is the research recommendation.

**Per-script contract (deterministic + reproducible):**

```python
# Every spike script MUST:
# 1. Pin the exact model ID + revision (deterministic).
# 2. Read ep01 fixtures via absolute paths (no re-extraction).
# 3. Use a stratified fixed sample (NOT random) — committed seed in common.py.
# 4. Emit a JSON blob with {model, model_revision, fixture, sample_size,
#    metric_value, per_sample: [...], methodology, caveat, wall_clock_sec,
#    device: "cpu"}.
# 5. Print a one-line summary: [ser] macro-F1 (proxy): 0.47 (n=30, self-consistency)
```

### System Architecture Diagram — Spike Data Flow

```
                ┌─────────────────────────────────────────────────────────┐
                │  ep01 v1.1 cached intermediates (read-only, NEVER write)│
                │  output/虫虫…第01话…/                                    │
                │   ├─ shots.json (V3b time grid)                          │
                │   ├─ stems/htdemucs/<ep01>/vocals.wav ←── SER + diarize  │
                │   │                              drums.wav  ┐             │
                │   │                              bass.wav   ├ MIR head-to-head
                │   │                              other.wav  ┘             │
                │   ├─ transcript.json (155 Whisper segments) ← WhisperX align input
                │   └─ audio_analysis.json (per-shot energies)              │
                └────────────────────┬────────────────────────────────────┘
                                     │
                ┌────────────────────┼────────────────────────────────────┐
                │                    │                                    │
        ┌───────▼───────┐   ┌────────▼────────┐   ┌─────────────────┐  ┌──▼──────────────┐
        │ run_ser_       │   │ run_mir_head_   │   │ run_whisperx_   │  │ run_diarize_    │
        │ sensevoice.py  │   │ to_head.py      │   │ align.py        │  │ pyannote.py     │
        │                │   │                 │   │ (isolated venv, │  │ (optional,      │
        │ funasr         │   │ MERT + PANNs    │   │  CPU)           │  │  informational) │
        │ SenseVoiceSmall│   │ on SAME segments│   │ wav2vec2 align  │  │ community-1     │
        │ on vocals.wav  │   │ on drums+bass+  │   │ vs faster-      │  │ DER vs transcript│
        │                │   │ other mix       │   │ whisper segs    │  │                 │
        └───────┬────────┘   └────────┬────────┘   └────────┬────────┘  └────────┬────────┘
                │                     │                     │                    │
                └──────────┬──────────┴─────────────────────┴────────────────────┘
                           ▼
              ┌────────────────────────────┐
              │ aggregate_report.py        │
              │ collates results/*.json →  │
              │ audio-spike-report.md      │
              └────────────┬───────────────┘
                           ▼
              ┌──────────────────────────────────────────┐
              │ PROJECT.md Key Decisions (4 locked        │
              │ outcomes) + STATE.md (resolves BLOCKER 1  │
              │ CUDA path + 3 conditional reqs)           │
              └──────────────────────────────────────────┘
```

### System Architecture Diagram — ROUTE-01 Stub

```
Producer (Phase 12, NOT Phase 10)            Cross-repo (Phase 10 deliverable)
┌─────────────────────────────┐             ┌──────────────────────────────────────────┐
│ shot-timeline               │             │ kais-aigc-platform @ feat/audio-analysis- │
│ analysis/call_audio_        │  POST       │ route branch                              │
│ analysis.py                 │ ────────►   │                                           │
│                             │ /api/       │ src/routes/production/audio-analysis/     │
│ httpx.Client                │ production/ │ ├─ index.ts  (zod body schema,            │
│                             │ audio-      │ │            STUB_MODE → empty data,      │
│ Expects:                    │ analysis    │ │            else fan-out to ML — deferred │
│ {"code":200,"data":{...}}   │             │ │            to Phase 12+)                 │
│                             │             │ └─ _shared/config.ts (env-driven ports)   │
│ On ConnectError →           │             │                                           │
│ graceful-degrade (mirror    │  200 OK     │ src/router.ts (add 1 import + 1           │
│ call_shot_analysis.py       │ ◄────────   │  app.use("/api/production/audio-analysis",│
│ CR-02/WR-05 patterns)       │             │  routeNN);                                 │
└─────────────────────────────┘             │                                           │
                                            │ src/lib/responseFormat.ts:success(...)    │
                                            │ returns {code:200,data,message:"成功"}    │
                                            │ (read this session — byte-identical shape)│
                                            └──────────────────────────────────────────┘
```

### ROUTE-01 Stub Structure (mirrors `shot-analysis/index.ts` line-for-line in envelope)

**File: `kais-aigc-platform/src/routes/production/audio-analysis/index.ts`**

```typescript
/**
 * 逐镜头音频语义解构 — THIN stub route (Phase 10 ROUTE-01)
 *
 * POST /api/v1/production/audio-analysis
 *   body: { video, shots, audio?, transcript?, shot_id_range? }
 *
 * Phase 10 (THIS): STUB ONLY. Returns schema-shaped empty data
 *   { shots: [], count: 0, errors: [], stub_mode: true }
 * so the Phase 12 producer client (call_audio_analysis.py) has an
 * integration target BEFORE route ML lands. Mirrors v1.1 Phase 7
 * CAST deferred pattern.
 *
 * Phase 12+ (post-merge): fan-out to SenseVoice / WhisperX / MERT /
 *   PANNs / pyannote via gold-team tasks (mirror shot-analysis index.ts).
 *
 * Envelope via @/lib/responseFormat.ts:success — byte-identical shape
 *   to shot-analysis so call_audio_analysis.py can be built now.
 */

import express from "express";
import { z } from "zod";
import fs from "fs";
import { success, error } from "@/lib/responseFormat";
import { AUDIO_ANALYSIS_CONFIG } from "./_shared/config";

const router = express.Router();

const bodySchema = z.object({
  video: z.string().min(1),
  shots: z.string().min(1),
  audio: z.string().optional(),       // path to audio_analysis.json (cached Demucs analysis)
  transcript: z.string().optional(),  // path to transcript.json
  shot_id_range: z.tuple([z.number().int(), z.number().int()]).optional(),
});

router.post("/", async (req: any, res: any) => {
  let params: z.infer<typeof bodySchema>;
  try {
    params = bodySchema.parse(req.body);
  } catch (err) {
    if (err instanceof z.ZodError) {
      return res.status(400).json(error("VALIDATION_ERROR", (err as any).errors));
    }
    return res.status(500).json(error("AUDIO_ANALYSIS_FAILED", (err as Error).message));
  }

  // --- Phase 10 STUB MODE: ML unloaded, return schema-shaped empty data ---
  // Phase 12+ replaces this block with fan-out to SenseVoice/WhisperX/MERT/PANNs.
  if (AUDIO_ANALYSIS_CONFIG.stubMode || !process.env.AUDIO_ANALYSIS_ML_LOADED) {
    return res.json(success({
      shots: [],
      count: 0,
      errors: [],
      stub_mode: true,
      message: "Phase 10 stub: ML models not loaded. Producer client envelope round-trip proven.",
    }, "Audio analysis stub"));
  }

  // --- Phase 12+ placeholder: ML fan-out goes here (mirror shot-analysis
  //     index.ts:125-235 gold-team task pattern). Intentionally NOT implemented
  //     in Phase 10 — spike runs models directly in scripts/, not through route. ---

  return res.status(501).json(error("NOT_IMPLEMENTED",
    "ML path not yet wired — Phase 12+ responsibility"));
});

export default router;
```

**File: `kais-aigc-platform/src/routes/production/audio-analysis/_shared/config.ts`**

```typescript
// Mirror shot-analysis/_shared/config.ts pattern (read this session).
export const AUDIO_ANALYSIS_CONFIG = {
  // Phase 10 stub default = true; Phase 12+ flips to false when ML is loaded.
  stubMode: process.env.AUDIO_ANALYSIS_STUB_MODE !== "false",
  goldTeamUrl: process.env.GOLD_TEAM_URL || "http://gold-team:8002",
  perShotDeadlineMs: Number(process.env.AUDIO_ANALYSIS_PER_SHOT_TIMEOUT_MS || 900_000),
  // Phase 12+ fills these in when ML lands.
  senseVoiceModel: "iic/SenseVoiceSmall",
  whisperxModel: "large-v3",
  mertModel: "m-a-p/MERT-v1-95M",
  pannsCheckpoint: null,  // null = default Cnn14_mAP=0.431
};
```

**File: `kais-aigc-platform/src/router.ts`** (add 2 lines):

```typescript
import routeNN from "./routes/production/audio-analysis/index";  // next number after route46
// ... existing mounts ...
app.use("/api/production/audio-analysis", routeNN);  // mirror shot-analysis mount line 189
```

> **Note on mounting path discrepancy:** the existing `shot-analysis` route is mounted at `/api/production/shot-analysis` (router.ts:189, **no `/v1/` segment**), but the v1.1 client `call_shot_analysis.py:84` hardcodes `ROUTE_PATH = "/api/v1/production/shot-analysis"`. This is a pre-existing v1.1 discrepancy (likely resolved via reverse proxy or unmerged branch — out of Phase 10 scope). The audio-analysis stub mirrors the **router.ts** mounting (`/api/production/audio-analysis`, no `/v1/`). Phase 12's client must match whatever path actually serves; the planner flags this for the Phase 12 client contract.

### Pattern 1: CPU-only Model Loading (SenseVoice)

**What:** Load SenseVoice on CPU via funasr AutoModel, run on ep01 vocals.wav segments.
**When:** DIA-04 SER spike.
**Example:**

```python
# Source: FunAudioLLM/SenseVoice README, fetched this session
# https://github.com/FunAudioLLM/SenseVoice
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

model = AutoModel(
    model="iic/SenseVoiceSmall",        # ModelScope canonical; FunAudioLLM/SenseVoiceSmall for HF
    trust_remote_code=True,
    remote_code="./model.py",            # SenseVoice repo convention (or omit for funasr-bundled)
    vad_model="fsmn-vad",                # splits long audio; safe to enable
    vad_kwargs={"max_single_segment_time": 30000},
    device="cpu",                        # SPIKE: CPU-only per user decision
)

# Per-shot: slice vocals.wav by [start_sec, end_sec] from shots.json,
# write to tmp.wav, run inference.
res = model.generate(
    input="tmp_shot_001.wav",
    cache={},
    language="zh",       # FORCE zh (ep01 is Mandarin; "auto" risks misdetect on short clips)
    use_itn=True,
    ban_emo_unk=False,   # keep <|emo_unk|> so we can count uncertain predictions
)
text = rich_transcription_postprocess(res[0]["text"])
# text format: "<|zh|><|HAPPY|><|Speech|><|woitn|>他有一百种方法逗我开心"
# Parse tags via regex to extract {language, emotion, event, itn} + clean text.
```

**Emotion labels emitted (7):** `HAPPY`, `SAD`, `ANGRY`, `NEUTRAL`, `FEARFUL`, `DISGUSTED`, `SURPRISED`.
**Audio-event labels emitted (8):** `BGM`, `Speech`, `Applause`, `Laughter`, `Cry`, `Sneeze`, `Breath`, `Cough`.

### Pattern 2: CPU-only Model Loading (MERT-v1-95M)

**What:** Extract MERT features for downstream instrument classification.
**When:** MUS-04 MIR spike.
**Example:**

```python
# Source: HuggingFace m-a-p/MERT-v1-95M model card, fetched this session
# https://huggingface.co/m-a-p/MERT-v1-95M
from transformers import AutoModel, Wav2Vec2FeatureExtractor
import torch, librosa, torch.nn as nn

model = AutoModel.from_pretrained("m-a-p/MERT-v1-95M", trust_remote_code=True)
processor = Wav2Vec2FeatureExtractor.from_pretrained("m-a-p/MERT-v1-95M", trust_remote_code=True)
model.eval()

# MERT trained at 24kHz — MUST resample from 44.1/48k.
audio, _ = librosa.load("drums_bass_other_mix_shot_001.wav", sr=24000, mono=True)
inputs = processor(audio, sampling_rate=24000, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs, output_hidden_states=True)

# Stack all 13 layers (12-768 architecture); reduce time axis; weighted-sum aggregate.
all_layers = torch.stack(outputs.hidden_states).squeeze()  # [13, T, 768]
time_reduced = all_layers.mean(-2)                           # [13, 768]

# Free-text label classifier head would go here. For the spike, use
# nearest-neighbor against a small labeled instrument embedding bank
# (erhu/pipa/guzheng/dizi/piano/strings/percussion) — pragmatic proxy.
```

### Pattern 3: CPU-only Model Loading (PANNs Cnn14)

**What:** Default panns-inference loads Cnn14_mAP=0.431 — the documented default.
**When:** MUS-04 MIR spike (head-to-head with MERT).
**Example:**

```python
# Source: GitHub qiuqiangkong/panns_inference README, fetched this session
# https://github.com/qiuqiangkong/panns_inference
import librosa
from panns_inference import AudioTagging, labels

# MUST use sr=32000 (Cnn14 training sample rate).
audio, _ = librosa.load("drums_bass_other_mix_shot_001.wav", sr=32000, mono=True)
audio = audio[None, :]  # (batch_size=1, segment_samples)

at = AudioTagging(checkpoint_path=None, device="cpu")  # None = default Cnn14_mAP=0.431.pth
clipwise_output, embedding = at.inference(audio)
# clipwise_output: shape (1, 527) — probabilities over AudioSet 527 classes.
# Filter to instrument-relevant classes via labels[] list (lookup by name).

# HTS-AT spike (optional): clone github.com/qiuqiangkong/audioset_tagging_cnn,
#   python3 inference.py --model_type HTSAT --audio_path ... --checkpoint_path ...
# Cnn14 is the documented panns-inference default; HTS-AT is the paper's
# stronger variant but not exposed by panns_inference PyPI package.
```

### Pattern 4: WhisperX Isolated-Venv CPU Align

**What:** Run wav2vec2 align on CPU inside an isolated venv, against ep01's existing faster-whisper segments.
**When:** DIA-05 drift spike.
**Example:**

```python
# Source: GitHub m-bain/whisperX README, fetched this session
# https://github.com/m-bain/whisperx
# Run inside /tmp/whisperx-spike-venv/bin/python (NOT system python).
import json, whisperx, librosa

# Load existing transcript (ep01 already has faster-whisper/openai-whisper segments).
# We do NOT re-transcribe — that would introduce confounding WER noise.
with open("/data/.../transcript.json") as f:
    existing = json.load(f)
segments = [{"text": s["text"], "start": s["start"], "end": s["end"]}
            for s in existing["segments"]]

# Load audio (ep01 vocals.wav — cleaner for alignment than full mix).
audio = whisperx.load_audio("/data/.../stems/htdemucs/<ep01>/vocals.wav")

# CPU align with the default Chinese wav2vec2 model
# (jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn — per DEFAULT_ALIGN_MODELS_HF).
model_a, metadata = whisperx.load_align_model(language_code="zh", device="cpu")
aligned = whisperx.align(segments, model_a, metadata, audio, "cpu",
                          return_char_alignments=False)

# Drift = aligned[i]["start"] - segments[i]["start"]  (and end)
# Per-word drift available in aligned[i]["words"].
# Aggregate: % of words with |drift| < 200ms → ship/defer decision for DIA-05.
```

### Pattern 5: pyannote Diarization on CPU (optional 5th spike)

**What:** Standalone diarization for informational DER measurement (not a Phase 10 gate).
**When:** Optional; informs Phase 13 SPEAKER-01 implementation but does not gate any conditional req.
**Example:**

```python
# Source: pyannote/speaker-diarization-3.1 HF card + vast.ai docs, fetched this session.
import torch
from pyannote.audio import Pipeline

# Requires HF_TOKEN env var + accepted ToU at:
#   huggingface.co/pyannote/speaker-diarization-3.1
#   huggingface.co/pyannote/segmentation-3.0
# (OR use community-1 via WhisperX which is CC-BY-4.0 — no gating.)
pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=os.environ["HF_TOKEN"],
)
pipeline.to(torch.device("cpu"))

diarization = pipeline("vocals.wav", min_speakers=2, max_speakers=5)
for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(f"{turn.start:.2f}s-{turn.end:.2f}s {speaker}")
```

### Anti-Patterns to Avoid

- **Anti-pattern: installing WhisperX in the project env.** WhisperX pulls torch with CUDA 12.8 wheel tag, conflicting with the project's `torch 2.6.0+cu124`. ALWAYS isolated venv.
- **Anti-pattern: re-running Demucs/Whisper for the spike.** ep01 has cached intermediates from v1.1. Re-running wastes 10+ minutes and confounds accuracy measurements with run-to-run variance. Read cached files only.
- **Anti-pattern: computing "macro-F1" without ground truth and labeling it rigorous.** AF-02/AF-03 require honest framing. Use self-consistency + qualitative review, OR a developer-annotated stratified sample. The report MUST call it a "calibrated estimate" not "F1".
- **Anti-pattern: putting spike scripts in `analysis/`.** That dir is producer code wired into `run_pipeline.py`. Spike scripts are throwaway — they must not become implicit pipeline deps.
- **Anti-pattern: ROUTE-01 stub doing real ML.** Phase 10 proves the envelope round-trips; live ML is Phase 12+ (deferred per CONTEXT.md). The stub MUST return empty schema-shaped data.
- **Anti-pattern: inventing the route envelope shape.** MUST use `@/lib/responseFormat.ts:success` — verified this session returns `{code:200, data, message:"成功"}`. Phase 12 client depends on byte-identical shape.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Emotion + audio-event tags | Rule-based heuristics on RMS/pitch | SenseVoice (one model, both outputs) | 7 emotions + 8 audio-event tags emitted in one forward pass — proven SOTA on Chinese+English benchmarks without target-domain finetuning. |
| Word-level timestamps | Custom DTW on mel-spectrogram | WhisperX `align()` (wav2vec2 forced alignment) | wav2vec2 is the canonical phoneme ASR for forced alignment; WhisperX wraps it with the correct Chinese default model. |
| Diarization | Clustering on speaker embeddings from scratch | pyannote.audio Pipeline | 4-19% DER on standard benchmarks; would take weeks to reproduce. |
| Route envelope formatting | Custom `{code,data,message}` constructor | `@/lib/responseFormat.ts:success/error` | Already exists in the cross-repo; guarantees byte-identical shape across routes. |
| Sample stratification (WhisperX drift sample) | Hand-pick segments | `common.py:stratified_sample(segments, n=30, buckets=[short/med/long/dense])` — explicit, deterministic, reproducible | Random sampling biases toward medium-length segments; stratified ensures short/long/dense-speech edge cases appear in the drift stat. |

**Key insight:** Phase 10 is a **measurement** phase, not a build phase. Every model that the route will eventually use has an established loading pattern; the spike reuses those patterns verbatim. The novel work is the **methodology** (how to compute macro-F1 without ground truth, how to do head-to-head MERT-vs-PANNs on identical segments, how to measure drift honestly) — not the code.

---

## Runtime State Inventory

> Phase 10 is a **greenfield spike + new cross-repo branch**, NOT a rename/refactor/migration. SKIP — no stored data, live service config, OS-registered state, secrets, or build artifacts carry the old name.

**Confirmed via:** CONTEXT.md `decisions` (ROUTE-01 is a new branch `feat/audio-analysis-route`, not a rename of an existing branch); spike scripts are new files in `spike/audio/` (new directory); no existing route, schema, or producer code is touched.

---

## Common Pitfalls

### Pitfall 1: WhisperX venv isolation incomplete — poisons project torch

**What goes wrong:** Installing WhisperX without an isolated venv overwrites the project's `torch 2.6.0+cu124` with the CUDA 12.8 wheel, breaking every other model script that imports torch (Demucs, Whisper, cv2-adjacent).
**Why it happens:** WhisperX's `setup.py` declares `torch>=2.6` without pinning the wheel tag, so pip grabs the latest (CUDA 12.8) wheel.
**How to avoid:** Always install WhisperX via `python3 -m venv /tmp/whisperx-spike-venv && /tmp/whisperx-spike-venv/bin/pip install whisperx`. Use the **CPU wheel index** (`--index-url https://download.pytorch.org/whl/cpu`) for the torch dep so even the venv doesn't grab a 12.8 wheel.
**Warning signs:** `python3 -c "import torch; print(torch.__version__)"` returns `2.6.0+cu128` instead of `+cu124` after WhisperX install → venv isolation failed.

### Pitfall 2: SenseVoice emotion tag mis-parsing

**What goes wrong:** SenseVoice's `rich_transcription_postprocess` strips the `<|HAPPY|>`-style tags, returning only clean text — losing the emotion signal the spike needs.
**Why it happens:** The postprocessor is designed for ASR output where tags are noise; for SER spikes you need the RAW text WITH tags.
**How to avoid:** Parse `res[0]["text"]` (pre-postprocess) with regex `<\|([A-Z_]+)\|>` to extract tags. Apply `rich_transcription_postprocess` only to get the clean text for human readability.
**Warning signs:** All shots report `emotion=NEUTRAL` because the parser ran on post-processed text where tags were stripped.

### Pitfall 3: MERT sample-rate mismatch

**What goes wrong:** Loading audio at the project default (16 kHz, the Whisper standard) silently feeds MERT the wrong sample rate → garbage features → nonsense instrument predictions.
**Why it happens:** MERT-v1 was trained at **24 kHz** (verified this session from HF card). 16 kHz is half the expected rate → MERT sees "slow" audio → pitch classes shift by an octave.
**How to avoid:** Explicitly `librosa.load(path, sr=24000)` for MERT. PANNs Cnn14 wants **32 kHz**. SenseVoice wants **16 kHz**. Document per-model sample rates in `common.py:load_audio_for_model(path, model_name)`.

### Pitfall 4: macro-F1 reported as if rigorous (AF-02/AF-03 violation)

**What goes wrong:** Without ep01 ground-truth emotion labels, the spike has nothing to compute true F1 against. Reporting "macro-F1: 0.47" as a hard number misleads the planner into locking DIA-04 ship/defer on a fabricated metric.
**Why it happens:** Pressure to produce a single comparable number against the ≥50%/<40% threshold.
**How to avoid:** Use one of two honest proxies: **(a) self-consistency** — run SenseVoice N=3 times with different segmentations, measure how often the emotion label agrees with itself across runs (cheap, no extra labor, but measures precision not accuracy); **(b) developer-annotated stratified sample** — developer manually labels 30 segments as HAPPY/SAD/NEUTRAL/etc., compute F1 against those 30 (more rigorous but ~1 hour of manual labor). **The report MUST state which proxy was used + caveat** ("without ground truth, this is a calibrated estimate, not a true F1 — cross-domain accuracy may differ").

### Pitfall 5: CPU spike wall-clock blows past user patience

**What goes wrong:** WhisperX-large-v3 on CPU for the full 308s episode takes hours (project CLAUDE.md documents "Whisper-large on CPU is hours-per-episode"). User aborts spike.
**Why it happens:** STACK.md explicitly warns against CPU fallback for WhisperX production use.
**How to avoid:** **The spike does NOT re-transcribe** — it reads ep01's existing `transcript.json` and runs only the `align()` step on CPU (wav2vec2 align is small ~1GB and fast on CPU, even for the full 155 segments). For SER/MIR/diarize, the spike samples 30 stratified segments, not the full episode. Total CPU wall-clock target: <30 minutes for all 4 spikes combined.
**Warning signs:** Single segment taking >60s on CPU → check that `device="cpu"` was set (not the default cuda).

### Pitfall 6: HF_TOKEN leakage via warnings sidecar (PITFALL 10/16 recurrence)

**What goes wrong:** pyannote 3.1 (or WhisperX diarize) raises an auth error that includes the HF_TOKEN in the exception string. Spike script prints it to stdout; spike report captures stdout; report committed to git → token leaked.
**Why it happens:** HF error responses occasionally echo the auth header.
**How to avoid:** Spike scripts read `HF_TOKEN` from env var (NOT hardcoded); scripts use the existing `_safe_error` regex pattern from `call_shot_analysis.py:122` extended with `hf_[a-zA-Z0-9_]+|token=\w+|Bearer\s+\w+` (per PITFALL 16 recommendation). If HF_TOKEN is missing, spike skips the diarize step with a clear warning (the step is informational, not a gate).
**Warning signs:** `grep -r "hf_" spike/audio/results/` returns any non-test string → token leaked.

### Pitfall 7: ROUTE-01 stub envelope shape drift from shot-analysis

**What goes wrong:** Audio-analysis stub invents a slightly different envelope (e.g. `{statusCode, payload}` instead of `{code, data, message}`) → Phase 12 client has to special-case → breaks the "thin httpx client mirror" invariant.
**Why it happens:** Each route author writing their own envelope helper.
**How to avoid:** STUB MUST call `success(data, "Audio analysis stub")` from `@/lib/responseFormat.ts` — verified this session returns `{code:200, data, message}`. Plan-checker greps `audio-analysis/index.ts` for `import { success` and rejects if missing.

### Pitfall 8: ep01 directory name encoding edge cases

**What goes wrong:** The ep01 directory has full-width parentheses `（…）` and a `：` colon in its name (`虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。`). Spike scripts using `subprocess.run(["ls", path])` without UTF-8 encoding garble the path.
**Why it happens:** Python on Linux defaults to UTF-8 but shell + some libraries don't.
**How to avoid:** Spike scripts use `pathlib.Path` and Python-native file ops (NOT subprocess with the path as arg). All paths passed as `str(Path(...))`. Test on the actual ep01 path before reporting results.
**Warning signs:** `FileNotFoundError` on a path that `ls` confirms exists → encoding issue.

### Pitfall 9: MERT-vs-PANNs not on SAME segments (head-to-head integrity)

**What goes wrong:** Spike runs MERT on the full drums+bass+other mix, then PANNs on `other.wav` alone → comparison is meaningless because inputs differ.
**Why it happens:** Different scripts running independently without a shared sample definition.
**How to avoid:** `common.py:stratified_sample(shots, n=30)` returns a fixed list of `(shot_id, start_sec, end_sec)` triples. BOTH `run_mir_mert.py` AND `run_mir_panns.py` import and iterate the SAME list. Commit `results/sample_mir_ep01.json` listing the 30 segments. The head-to-head mAP comparison is the deliverable for MUS-04.

### Pitfall 10: Aggregator script reports stale results

**What goes wrong:** Developer re-runs SER spike after fixing a tag-parsing bug, but the aggregator reads the old `results/ser_sensevoice_ep01.json` and the report shows stale numbers.
**Why it happens:** No staleness check.
**How to avoid:** Each per-model JSON includes `wall_clock_sec` and `git_sha` (current HEAD). Aggregator prints a warning if any results file is older than the report's own timestamp, or if `git_sha` differs from current HEAD. Plan-checker greps the report for "WARNING: stale results" and rejects if present.

---

## Code Examples

### Common helper (every spike script imports this)

```python
# spike/audio/common.py
"""Shared utilities for Phase 10 audio spike scripts."""
import hashlib, json, os, subprocess, time
from pathlib import Path
from datetime import datetime, timezone

EP01_DIR = Path(
    "/data/workspace/kais-shot-timeline/output/"
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)
EP01_VOCALS = EP01_DIR / "stems/htdemucs" / EP01_DIR.stem / "vocals.wav"
EP01_DRUMS  = EP01_DIR / "stems/htdemucs" / EP01_DIR.stem / "drums.wav"
EP01_BASS   = EP01_DIR / "stems/htdemucs" / EP01_DIR.stem / "bass.wav"
EP01_OTHER  = EP01_DIR / "stems/htdemucs" / EP01_DIR.stem / "other.wav"
EP01_SHOTS     = EP01_DIR / "shots.json"
EP01_TRANSCRIPT = EP01_DIR / "transcript.json"
EP01_AUDIO_ANALYSIS = EP01_DIR / "audio_analysis.json"

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

def git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent
    ).decode().strip()

def stratified_sample(segments, n=30, seed=42):
    """Fixed-seed stratified sample across short/medium/long/dense buckets.
    Returns list of (idx, segment_dict). Deterministic for reproducibility."""
    import random
    rng = random.Random(seed)
    buckets = {"short": [], "medium": [], "long": [], "dense": []}
    for i, s in enumerate(segments):
        dur = s["end"] - s["start"]
        if dur < 2.0: buckets["short"].append((i, s))
        elif dur > 5.0: buckets["long"].append((i, s))
        else: buckets["medium"].append((i, s))
        # dense-speech: >10 chars/sec
        if dur > 0 and len(s.get("text", "")) / dur > 10:
            buckets["dense"].append((i, s))
    # take roughly n/4 from each bucket (or fewer if bucket too small)
    per_bucket = max(1, n // 4)
    sample = []
    for b in buckets.values():
        rng.shuffle(b)
        sample.extend(b[:per_bucket])
    return sample[:n]

def write_result(model: str, fixture: str, payload: dict):
    payload["model"] = model
    payload["fixture"] = fixture
    payload["git_sha"] = git_sha()
    payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    payload["device"] = "cpu"
    out = RESULTS_DIR / f"{model}_{fixture}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[{model}] wrote {out}")
```

### SenseVoice emotion tag parser (regex over raw output)

```python
import re
TAG_RE = re.compile(r"<\|([A-Z_]+)\|>")
EMOTIONS = {"HAPPY", "SAD", "ANGRY", "NEUTRAL", "FEARFUL", "DISGUSTED", "SURPRISED"}
EVENTS = {"BGM", "Speech", "Applause", "Laughter", "Cry", "Sneeze", "Breath", "Cough"}

def parse_sensevoice_tags(raw_text: str) -> dict:
    """Parse raw SenseVoice output (pre-rich_transcription_postprocess)."""
    tags = TAG_RE.findall(raw_text)
    return {
        "language": next((t for t in tags if t in {"zh", "en", "yue", "ja", "ko"}), None),
        "emotion": next((t for t in tags if t in EMOTIONS), "emo_unk"),
        "events": [t for t in tags if t in EVENTS],
        "clean_text": TAG_RE.sub("", raw_text).strip(),
    }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| RAVDESS English-trained SER for Chinese dialogue | SenseVoice (FunAudioLLM, native Mandarin+Cantonese) | Jul 2024 | Cross-domain gap closed — SenseVoice is the headline pick for the highest-risk unknown (DIA-04). |
| Whisper segment-only timestamps | WhisperX wav2vec2 forced alignment | INTERSPEECH 2023 | Sub-100ms word timestamps feasible; Chinese drift remains an open empirical question (DIA-05). |
| pyannote 3.0 with onnxruntime dep | pyannote.audio 3.1 (pure PyTorch) | 2024 | Removes the problematic onnxruntime dep; 4-19% DER on standard benchmarks. |
| Cnn14 (PANNs, 2020) | HTS-AT (2022) + MERT-v1 (2023) | 2022-2024 | Cnn14 still the documented `panns-inference` default; HTS-AT is paper-better but needs the larger repo; MERT is music-specialized. Spike runs MERT + Cnn14 head-to-head. |
| WhisperX bundled pyannote 3.0 | WhisperX bundled community-1 (CC-BY-4.0) | 2024-2025 | Resolves the gating friction — community-1 has no ToU acceptance requirement. |
| SenseVoice Python-only | SenseVoice on llama.cpp / GGUF (q8 ~254MB) | 2026-06 | CPU/edge deployment feasible as a single binary — could simplify the route host later. |

**Deprecated/outdated:**
- `pyannote/speaker-diarization-3.0`: has problematic `onnxruntime` dep. Use 3.1 or community-1.
- `MERT-v0` / `music2vec-v1`: superseded by MERT-v1-95M (better pre-training paradigm + more data).
- `"MuQ"` (mentioned in SUMMARY): did NOT surface as a real published model in 2025 searches (possible name confusion per STACK.md — treat as not-available).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | WhisperX CPU mode (`device="cpu", compute_type="int8"`) works without CUDA 12.8 toolkit installed | §Pattern 4, §Pitfall 5 | HIGH — if CPU mode still tries to load CUDA libs, the entire WhisperX spike is blocked. Mitigation: README explicitly documents `--device cpu --compute_type int8` as the CPU escape hatch, but planner should verify with a `whisperx --help` smoke check before running the full spike. |
| A2 | WhisperX `align()` step alone (without re-transcription) produces valid drift measurements | §Pattern 4 | MEDIUM — if `align()` requires fresh transcribe output (not arbitrary segments), the spike must re-transcribe on CPU = hours. Mitigation: WhisperX API accepts arbitrary `[{text,start,end}]` segments per the README, but spike should test with 1 segment first. |
| A3 | The pragmatic macro-F1 proxy (self-consistency or 30-segment developer annotation) is acceptable methodology per AF-02/AF-03 | §Pitfall 4 | HIGH — if user requires true F1 against a published benchmark, the spike needs to additionally run SenseVoice on a standard test set (RAVDESS-test, EMIME, etc.) which adds 1-2 hours. **Plan-time confirmation needed.** |
| A4 | `iic/SenseVoiceSmall` (ModelScope) works without a ModelScope account when accessed via funasr | §Pattern 1 | LOW — funasr's AutoModel handles ModelScope anonymous download. Mitigation: switch to HF ID `FunAudioLLM/SenseVoiceSmall`. |
| A5 | The new cross-repo branch `feat/audio-analysis-route` can be branched from `develop` without pulling in unmerged `feat/shot-analysis-route` conflicts | §ROUTE-01 Stub Structure | MEDIUM — `feat/shot-analysis-route` is still unmerged per STATE.md. Planner must verify `develop` already contains the merged shot-analysis route (git log check this session shows it does: develop has `shot-analysis/index.ts`). |
| A6 | The existing `/api/production/shot-analysis` mount path (no `/v1/`) is the production reality, not a bug | §ROUTE-01 Stub Structure note | LOW — Phase 10 stub mirrors whatever router.ts mounts (verified: `/api/production/shot-analysis`). If a reverse proxy adds `/v1/`, the stub doesn't care. Phase 12 client contract catches any mismatch. |
| A7 | pyannote.audio community-1 weights accessible via WhisperX's bundled default do NOT require separate HF ToU acceptance | §Pattern 5 | LOW — community-1 is CC-BY-4.0 (no gating), but HuggingFace may still require a read token. Spike script reads `HF_TOKEN` env var; if missing, spike skips the diarize step with a clear warning (it's informational, not a gate). |

**Claim provenance summary:**
- `[VERIFIED]` (PyPI registry, HF model card, or GitHub README fetched this session): all model loading patterns in §Patterns 1-5, package versions in §Standard Stack.
- `[CITED]` (milestone SUMMARY/STACK/PITFALLS docs, already committed): v1.1 patterns, ROUTE-vs-client split, CUDA 12.8 conflict, license terms.
- `[ASSUMED]`: A1-A7 above — flagged for plan-time confirmation.

---

## Open Questions (RESOLVED)

> All 4 questions resolved during planning. Each is operationalized by a concrete plan task (cited inline). No question remains open entering execution.

1. **WhisperX CPU smoke check**
   - What we know: README says `whisperx --device cpu --compute_type int8` is the CPU escape hatch.
   - What's unclear: Whether CPU mode still requires CUDA toolkit install for some operations.
   - Recommendation: Planner adds a Wave 0 task to run `whisperx --help` from the isolated venv before committing to the full spike architecture.
   - **RESOLVED: Plan 10-05 Task 1 isolates the venv FIRST and smoke-checks A1/A2 (`whisperx --help` + 1-segment `align()`) before the full 30-segment run; CPU mode confirmed by the 3-point torch canary.**

2. **macro-F1 methodology user confirmation (A3)**
   - What we know: No ground-truth emotion labels exist for ep01. AF-02/AF-03 forbid fabricated signal.
   - What's unclear: Whether the user accepts self-consistency + qualitative review as the methodology, OR wants the developer to annotate 30 segments manually, OR wants a benchmark-only F1 (RAVDESS-test, etc.).
   - Recommendation: Plan-checker flags this as a `checkpoint:human-confirm` before the SER spike runs.
   - **RESOLVED: Plan 10-03 Task 1 `checkpoint:decision` surfaces methodology options (a/b/c/ab) to the user before the SER spike runs; the chosen methodology is recorded in the report.**

3. **WhisperX drift sample size (CONTEXT.md discretion)**
   - What we know: CONTEXT.md says "Claude picks a representative sample (target ≥20 segments)".
   - Recommendation: Research recommends N=30 stratified (short/med/long/dense buckets) for ~19% coverage of the 155-segment population. Statistically robust while CPU-friendly.
   - **RESOLVED: N=30 stratified, seed=10, fixed in `common.py:stratified_sample` (Plan 10-01); shared across SER/MIR/WhisperX for head-to-head integrity (Pitfall 9).**

4. **Cross-repo branching strategy**
   - What we know: STATE.md lists `feat/shot-analysis-route` as unmerged from v1.1, but `develop` already has the route file (verified this session).
   - What's unclear: Whether `feat/audio-analysis-route` should branch from `develop` or from `feat/shot-analysis-route`.
   - Recommendation: Branch from `develop` — verified `develop` has `src/routes/production/shot-analysis/index.ts` committed.
   - **RESOLVED: Branch `feat/audio-analysis-route` from `develop` (Plan 10-02 Task 1 Step 1); `develop` verified to contain the merged shot-analysis route (A5).**

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All spike scripts | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `torch` (cu124) | SenseVoice/MERT/PANNs/pyannoke | ✓ | 2.6.0+cu124 (system) | — |
| `transformers` | MERT-v1-95M | ✓ | 5.6.2 | — |
| GPU / CUDA | NOT REQUIRED (Phase 10 is CPU-only per user decision) | ✗ | driver 580.159 / NVML 580.173 mismatch | CPU inference (works for accuracy metrics) |
| `funasr` | SenseVoice (SER spike) | ✗ (not installed) | — | Install via `pip install --break-system-packages funasr==1.3.29` |
| `panns-inference` | PANNs Cnn14 (MIR spike) | ✗ | — | Install via `pip install --break-system-packages panns-inference==0.1.1` |
| `pyannote.audio` | Diarization (optional spike) | ✗ | — | Install via `pip install --break-system-packages pyannote.audio==4.0.7` |
| `librosa` | Resampling + onset | ✓ (transitively present) | — | — |
| `whisperx` (isolated venv) | WhisperX word-align | ✗ | — | Create isolated venv, install `whisperx==3.8.6` with CPU torch wheel |
| `ffmpeg` / `ffprobe` | Audio slicing for spike segments | ✓ | 6.1.1 (project baseline) | — |
| ep01 cached intermediates | All 4 spikes | ✓ | shots.json (155 segs), 4 htdemucs stems, transcript.json, audio_analysis.json, frames.json | — |
| HF_TOKEN (read) | pyannote 3.1 / WhisperX diarize | ✗ (env var not set this session) | — | Skip diarize spike (informational only); OR user provides token at run time |
| slopcheck | Package legitimacy audit | ✓ | 0.6.1 (`/home/kai/.local/bin/slopcheck`) | — |
| kais-aigc-platform repo | ROUTE-01 stub | ✓ | feat/flowgraph-v3-canvas branch (current); `develop` has `shot-analysis/index.ts` (verified) | Branch `feat/audio-analysis-route` from `develop` |

**Missing dependencies with no fallback:**
- None blocking. GPU is unavailable but Phase 10 explicitly runs CPU-only per user decision; HF_TOKEN is optional (skips diarize spike if missing).

**Missing dependencies with fallback:**
- `funasr` / `panns-inference` / `pyannote.audio` / `whisperx` are not installed — planner adds a Wave 0 install task. WhisperX MUST go in an isolated venv (Pitfall 1).
- HF_TOKEN optional; if missing, diarize spike is skipped with a clear caveat in the report (it's informational, not a gate).

---

## Validation Architecture

> `workflow.nyquist_validation` is **true** in `.planning/config.json`. Section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | **pytest (NOT installed — Wave 0)** + **bash smoke-check scripts** (spike deliverable verification) |
| Config file | `pytest.ini` (Wave 0 — none currently exists in this repo) |
| Quick run command | `python3 -m pytest spike/audio/tests/ -x` (Wave 0 — to be created) |
| Full suite command | `python3 spike/audio/aggregate_report.py --check-staleness && python3 -m pytest spike/audio/tests/` |

**Important context:** The CLAUDE.md explicitly notes "None. No `pytest`, `unittest` cases, `tox`, or any test files are present in the repo". Phase 10 has latitude to either:
(a) Add pytest as a Wave 0 install + minimal tests for `common.py:parse_sensevoice_tags` and `stratified_sample` (deterministic functions worth pinning).
(b) Skip formal pytest and rely on bash smoke-check scripts that verify each spike script produces a results JSON.

**Research recommendation:** Option (b) — bash smoke-checks match the throwaway nature of spike scripts; pytest would imply production infrastructure for throwaway code. The deliverable is the report + committed JSON blobs, not a test suite.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROUTE-01 | Stub returns `{"code":200,"data":{"shots":[],"count":0,"stub_mode":true},...}` when ML unloaded | smoke (curl) | `curl -sS -X POST http://localhost:<port>/api/production/audio-analysis -H 'Content-Type: application/json' -d '{"video":"/x","shots":"/y"}' \| jq '.code,.data.stub_mode'` | ❌ Wave 0 — write `spike/audio/tests/route_stub_smoke.sh` |
| ROUTE-01 | Stub returns 400 on missing required field | smoke (curl) | `curl -sS -X POST .../audio-analysis -d '{}' \| jq '.code'` (expect 400) | ❌ Wave 0 |
| ROUTE-01 | Stub returns `stub_mode:true` when `AUDIO_ANALYSIS_STUB_MODE != "false"` | smoke (curl) | env var flip + curl | ❌ Wave 0 |
| DIA-04 | SER spike emits JSON with non-empty `per_sample[]` | smoke (python) | `python3 -c "import json; d=json.load(open('spike/audio/results/ser_sensevoice_ep01.json')); assert len(d['per_sample'])==30"` | ❌ Wave 0 |
| DIA-04 | SER spike report cites methodology caveat (no ground truth) | grep | `grep -c "calibrated estimate" .planning/research/audio-spike-report.md` (expect ≥1) | ❌ Wave 0 |
| DIA-05 | WhisperX drift stat present + based on ≥30 segments | smoke (python) | `python3 -c "import json; d=json.load(open('spike/audio/results/whisperx_align_ep01.json')); assert d['sample_size']>=30"` | ❌ Wave 0 |
| DIA-05 | Isolated venv verified (system torch untouched) | smoke (python) | `python3 -c "import torch; assert '+cu124' in torch.__version__"` (after WhisperX install) | ❌ Wave 0 |
| MUS-04 | MERT + PANNs both produce JSON on SAME 30 segments | smoke (python) | compare `shot_id` lists in `mir_mert_ep01.json` and `mir_panns_ep01.json` | ❌ Wave 0 |
| MUS-04 | Head-to-head mAP comparison present in report | grep | `grep -c "MERT.*PANNs\|PANNs.*MERT" .planning/research/audio-spike-report.md` (expect ≥1) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** the relevant spike script + its results JSON (no shared test suite needed — spike is single-developer).
- **Per wave merge:** `bash spike/audio/tests/smoke_all.sh` runs all 8 checks above + the staleness check in `aggregate_report.py`.
- **Phase gate:** All 4 results JSON files present + report has all 4 sections (SER / MIR head-to-head / WhisperX drift / diarize-or-skip) + report has methodology caveats + PROJECT.md Key Decisions has 4 locked outcomes → ready for `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `spike/audio/tests/route_stub_smoke.sh` — 3 curl-based smoke tests for ROUTE-01
- [ ] `spike/audio/tests/results_schema_check.py` — JSON shape validation for each model's results blob
- [ ] `spike/audio/tests/staleness_check.sh` — wrapper around `aggregate_report.py --check-staleness`
- [ ] `spike/audio/tests/smoke_all.sh` — top-level runner (wave merge gate)
- [ ] Optional: `pytest` install if planner chooses option (a) above

*(If no gaps: "None — existing test infrastructure covers all phase requirements". Here there ARE gaps because the project has zero existing test infrastructure per CLAUDE.md.)*

---

## Security Domain

> `security_enforcement` not explicitly set in `.planning/config.json` → treat as enabled per the research protocol. Section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | (Spike has no auth; route stub accepts any body — Phase 12+ adds auth) |
| V3 Session Management | no | (No sessions in spike or stub) |
| V4 Access Control | no | (Route stub is open in Phase 10; Phase 12+ gates behind existing kais-aigc-platform auth) |
| V5 Input Validation | **yes** | zod body schema in ROUTE-01 stub (mirror shot-analysis); spike scripts use argparse + path validation |
| V6 Cryptography | no | (No crypto in spike or stub) |
| V7 Error Handling | **yes** | ROUTE-01 stub returns 400 on zod fail, 501 on ML not-yet-wired; spike scripts use `_safe_error` regex extended with `hf_` patterns per Pitfall 6 |
| V8 Data Protection | **yes** | HF_TOKEN protection (Pitfall 6) — never hardcode, never log, extend `_safe_error` regex |

### Known Threat Patterns for Spike + Stub Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| HF_TOKEN leakage via pyannote/WhisperX exception strings | Information Disclosure | `_safe_error` regex extension `hf_[a-zA-Z0-9_]+|token=\w+|Bearer\s+\w+`; never print raw exceptions from HF libraries |
| Spike report committed with embedded auth tokens | Information Disclosure | Plan-checker greps `spike/audio/results/*.json` and `audio-spike-report.md` for `hf_` patterns before commit |
| Malicious model weights from non-canonical HF IDs | Supply Chain | Use only canonical IDs (`iic/SenseVoiceSmall`, `m-a-p/MERT-v1-95M`, `pyannote/speaker-diarization-3.1`); never load from `./local-checkpoint` paths |
| Route stub accepts arbitrary path in `video`/`shots` field | Path Traversal | zod validates type=string; route stub does NOT read the file in Phase 10 (only Phase 12+ reads files, must add path sandboxing then) |
| WhisperX isolated venv with system-write access | Tampering | Create venv in `/tmp/whisperx-spike-venv` (ephemeral); `pip install` from canonical PyPI only; never `--user` install |

---

## Sources

### Primary (HIGH confidence)

- **FunAudioLLM/SenseVoice GitHub README** — fetched this session via webReader: confirmed `iic/SenseVoiceSmall` model ID, `funasr>=1.3.26`, `device="cpu"` flag, 7 emotion labels, 8 audio-event labels, `rich_transcription_postprocess` behavior, FSMN-VAD composition, llama.cpp GGUF runtime (2026-06), MIT license.
- **HuggingFace m-a-p/MERT-v1-95M model card** — fetched this session: confirmed `AutoModel.from_pretrained("m-a-p/MERT-v1-95M", trust_remote_code=True)`, `Wav2Vec2FeatureExtractor`, 24kHz sample rate, 13 hidden layers, weighted-sum aggregation pattern.
- **GitHub qiuqiangkong/panns_inference README** — fetched this session: confirmed `pip install panns-inference`, default loads `Cnn14_mAP=0.431.pth` (NOT HTS-AT), `librosa.load(sr=32000)` sample rate, `AudioTagging(checkpoint_path=None, device="cpu")` API.
- **GitHub m-bain/whisperX README** — fetched this session: confirmed `pip install whisperx` (correct PyPI name), CUDA 12.8 hard-req for GPU, **CPU escape hatch** `whisperx path --compute_type int8 --device cpu`, Python API `load_model() / load_align_model(language_code="zh") / align() / DiarizationPipeline(token=HF_TOKEN)`, default diarization is community-1 (CC-BY-4.0).
- **pyannote/speaker-diarization-3.1 HF model card** — fetched via WebSearch: confirmed `Pipeline.from_pretrained(..., use_auth_token=...)`, `pipeline.to(torch.device("cpu"))` CPU pattern, gated ToU acceptance required.
- **kais-aigc-platform/src/routes/production/shot-analysis/index.ts** — read this session (9108 bytes): confirmed zod body schema shape, `success/error` envelope pattern, gold-team fan-out pattern (Phase 12+ mirror).
- **kais-aigc-platform/src/lib/responseFormat.ts** — read this session: confirmed `success(data, message)` returns `{code:200, data, message:"成功"}` — byte-identical envelope.
- **kais-aigc-platform/src/router.ts** — read this session: confirmed `app.use("/api/production/shot-analysis", route46)` mount path (no `/v1/`); planner adds `app.use("/api/production/audio-analysis", routeNN)` similarly.
- **analysis/call_shot_analysis.py** — read this session (425 lines): confirmed v1.1 thin-client pattern (httpx, per-shot cache, `_safe_error`, graceful-degrade).
- **PyPI registry** — verified versions this session: `funasr 1.3.29`, `panns-inference 0.1.1`, `pyannote.audio 4.0.7`, `whisperx 3.8.6`, `librosa 0.11.0`.
- **slopcheck 0.6.1** — run this session on all spike packages; confirmed `m-bain/whisperx` is SLOP (correct name: bare `whisperx`).

### Secondary (MEDIUM confidence)

- **Milestone SUMMARY.md / STACK.md / PITFALLS.md** (committed at `.planning/research/`): provided v1.1 SHIPPED patterns, cross-repo coordination overhead, BLOCKER 1 (CUDA 12.8) framing, AF-02/AF-03 anti-fabrication requirements, Chinese SER cross-domain risk, MIR-on-folk unknowns, PITFALL 10/16 (HF_TOKEN leakage + green-verify-hides-blocker).

### Tertiary (LOW confidence)

- pyannote 3.1 DER performance numbers on Chinese animation dialogue (community-1 untested on this domain — Phase 10 produces the measurement).
- HTS-AT vs Cnn14 accuracy delta on Chinese folk instruments (no published benchmark — Phase 10 spike is the head-to-head).
- WhisperX Chinese align drift statistics (no published number — Phase 10 produces the first measurement on this fixture).

---

## Metadata

**Confidence breakdown:**
- Standard stack (model loading + libs): **HIGH** — all patterns fetched against current official model cards this session; package versions verified on PyPI; slopcheck passed.
- Spike architecture (`spike/audio/` + per-script contract): **HIGH** — direct application of v1.1 SHIPPED patterns.
- ROUTE-01 stub structure: **HIGH** — line-for-line mirror of read-this-session `shot-analysis/index.ts`.
- Metric methodology (macro-F1 proxy): **MEDIUM** — pragmatic proxies are reasonable per AF-02/AF-03 but user confirmation needed before locking (A3).
- CPU wall-clock bounds: **MEDIUM** — WhisperX `align()` on CPU should be fast on 30 segments but unverified (A1, A2).
- Pitfalls: **HIGH** — most grounded in PITFALLS.md committed research (Pitfall 10/16/1 v1.1 recurrence) plus session-specific discoveries (sample-rate mismatches, tag-parsing gotchas).

**Research date:** 2026-07-25
**Valid until:** 2026-08-25 (30 days; model IDs and package versions stable, but HuggingFace model card revisions and funasr API may evolve — re-verify if spike runs after this date)

## RESEARCH COMPLETE
