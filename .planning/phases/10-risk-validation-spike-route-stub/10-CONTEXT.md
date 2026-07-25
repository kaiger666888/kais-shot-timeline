# Phase 10: Risk-Validation Spike + Route Stub - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — single area, all recommendations accepted

<domain>
## Phase Boundary

Empirically de-risk the 4 highest unknowns of v1.2 on **1 episode of 《小江湖》 BEFORE any contract locks** (mirror v1.1 Phase 7 DINOv2 τ spike — "先证模型、再立契约"). The 4 unknowns:

1. **Chinese SER cross-domain** — SenseVoice (native Mandarin) macro-F1 on ep01 vocals stem (RAVDESS-trained baseline → 中文动画对白 gap). Drives DIA-04 ship (≥50%) / ship-nullable (40-50%) / defer (<40%).
2. **Polyphonic instrument recognition** — MERT-v1-95M vs PANNs head-to-head mAP on ep01 `drums+bass+other` mix (esp. erhu/pipa/guzheng/dizi folk). Drives MUS-04 ship (≥0.30) / ship-nullable (0.20-0.30) / defer (<0.20) AND the MERT-vs-PANNs pick.
3. **WhisperX word-level drift** — wav2vec2 align drift on ≥N Chinese segments. Drives DIA-05 ship-experimental (<200ms drift on ≥80%) / defer AND the CUDA 12.8-upgrade vs stay-on-12.4 decision.
4. **CUDA 12.8 upgrade compatibility** — resolved as a byproduct of (3): WhisperX PyPI hard-requires 12.8; stay-on-12.4 (cu124 runtime) means WhisperX runs in an isolated venv on CPU.

PLUS the **ROUTE-01 route stub**: developer can POST to `/api/production/audio-analysis` and receive a `{"code":200,"data":{...}}` envelope even with ML models unloaded — giving the Phase 12 producer client an integration target before route ML lands (mirror v1.1 Phase 7 CAST deferred pattern).

**Mount path note:** `/api/production/audio-analysis` (NO `/v1/`) — verified against `kais-aigc-platform/src/router.ts`, which mounts the sibling `shot-analysis` route at `/api/production/shot-analysis`. An earlier draft of this context said `/api/v1/production/...`; the `/v1/` was a doc oversight corrected during Phase 10 planning (see 10-RESEARCH.md §"Note on mounting path discrepancy"). The Phase 12 client contract must match this actual mount.

This phase produces NO contract changes, NO producer pipeline code, NO schema edits. It produces: (a) a spike report at `.planning/research/audio-spike-report.md`, (b) the ROUTE-01 stub in kais-aigc-platform, (c) 4 locked outcomes in PROJECT.md Key Decisions.

</domain>

<decisions>
## Implementation Decisions

### Spike Methodology & Cross-Repo Stub

- **Episode: ep01** (`output/虫虫武侠小江湖…第01话…`) — full v1.1 intermediates already cached (shots.json, 4 htdemucs stems, transcript.json, frames.json, audio_analysis.json, prompts.json). Zero re-extraction; matches v1.1 fixture convention; results directly comparable to v1.1 Phase 7 DINOv2 τ spike evidence.
- **WhisperX word-align: isolated venv, CPU** — install whisperx in a throwaway venv so its CUDA-12.8-hungry deps cannot poison the project's `torch 2.6.0+cu124` runtime. Run wav2vec2 align on CPU. Measures real Chinese word-drift honestly; the CUDA 12.8-upgrade-vs-stay-on-12.4 decision is made from the resulting drift number (not from install convenience).
- **MUS-04 MIR: MERT-v1-95M + PANNs/HTS-AT head-to-head** on ep01 `drums+bass+other` mix — research SUMMARY explicitly defers the MERT-vs-PANNs pick to this spike. Run both, compute mAP on the same segments, pick the winner for the mAP ≥0.30/<0.20 threshold decision.
- **ROUTE-01 stub: new `feat/audio-analysis-route` branch** in kais-aigc-platform, mirroring the existing `feat/shot-analysis-route` sibling (`src/routes/production/audio-analysis/`). Envelope `{"code":200,"data":{...}}` via `@/lib/responseFormat.ts:success`. Stub mode returns schema-shaped empty data with ML unloaded.

### Claude's Discretion

- Exact N for "≥N Chinese segments" WhisperX drift sample — Claude picks a representative sample (target ≥20 segments spanning short/long/dense-speech) to make the drift stat robust.
- SenseVoice model variant / checkpoint pin, MERT/PANNs checkpoint pins, pyannote community-1 vs 3.1 weights — Claude picks per research SUMMARY §STACK + license constraints.
- Spike script location (`spike/` dir or `.planning/research/spike/`) — Claude's discretion; scripts are throwaway, the report is the deliverable.
- How to compute macro-F1 (Chinese SER has no ep01 ground-truth emotion labels) — Claude chooses a pragmatic proxy: either (a) manual annotation of a stratified sample by the developer post-spike, or (b) SenseVoice self-consistency + qualitative review. The report MUST state the methodology + caveat that without ground truth the number is a calibrated estimate, not a true F1. This honest framing is required by AF-02/AF-03 (don't fabricate signal).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- **ep01 cached intermediates** — `shots.json`, `stems/htdemucs/<ep01>/{vocals,drums,bass,other}.wav`, `transcript.json`, `frames.json`, `audio_analysis.json`. The spike reads these; it does NOT re-run detection/separation/transcription.
- **`analysis/call_shot_analysis.py`** (v1.1) — the per-shot httpx client pattern the Phase 12 `call_audio_analysis.py` will mirror. Phase 10 only needs its route-envelope expectations (`{"code":200,"data":{"shots":[...]}}`, 900s route-side timeout, graceful-degrade on ConnectError).
- **`analysis/call_reid.py`** (v1.1) — poisoned-cache invalidation + per-video cache pattern; reference for Phase 12, not Phase 10.
- **kais-aigc-platform `src/routes/production/shot-analysis/`** — the route stub template. The audio-analysis stub copies its index.ts structure + responseFormat envelope.

### Established Patterns

- **Route-vs-client split**: heavy ML lives behind the kais-aigc-platform route host; shot-timeline takes zero ML deps. Phase 10's spike scripts are throwaway (NOT producer code) and live outside the pipeline — they exist only to produce the report + feed PROJECT.md decisions.
- **Envelope contract**: `{"code":200,"data":{...},"message":"..."}` via `@/lib/responseFormat.ts`. The ROUTE-01 stub MUST match this exactly so Phase 12's client integrates without rework.
- **Spike-before-contract**: v1.1 Phase 7 DINOv2 τ spike is the precedent — empirical evidence → PROJECT.md Key Decisions → THEN contract locks in the next phase. Non-negotiable invariant #1.

### Integration Points

- **Spike report** → PROJECT.md Key Decisions table (4 outcomes) + STATE.md (resolves BLOCKER 1 CUDA path + the 3 conditional reqs DIA-04/MUS-04/DIA-05).
- **ROUTE-01 stub** → Phase 12 `call_audio_analysis.py` integration target (stub mode proves the envelope round-trip before route ML lands).
- **GPU is currently DOWN** (driver 580.159 kernel vs 580.173 userspace mismatch; needs reboot; gnome-shell holds /dev/nvidia*). **User decision: run spike CPU-only now.** Accuracy metrics (macro-F1/mAP/drift) are device-independent and remain valid; the report MUST flag all numbers as CPU-derived and note production latency/VRAM as unmeasured (not Phase 10 success criteria anyway).

</code_context>

<specifics>
## Specific Ideas

- The spike report is the single most important artifact of Phase 10 — it is the empirical basis for 3 conditional reqs (DIA-04/MUS-04/DIA-05) AND the CUDA-path decision. It must be honest about methodology (especially the SER ground-truth gap) per AF-02/AF-03 anti-fabrication.
- MERT-vs-PANNs must be a real head-to-head on the SAME segments — not two independent runs with different inputs. The comparison is the deliverable for the MUS-04 model pick.
- ROUTE-01 stub envelope must be byte-identical in shape to shot-analysis so Phase 12 can be built against it immediately.

</specifics>

<deferred>
## Deferred Ideas

- **Live ML round-trip through the route** (route host loading SenseVoice/WhisperX/MERT/PANNs) — deferred to post-merge smoke check, mirroring v1.1 Phase 7 CAST-01..04/08 deferred pattern. Phase 10 proves the stub envelope + the spike runs models directly (not through the route) to get the accuracy numbers fast.
- **GPU-derived latency/VRAM profiling** — deferred until GPU is back (post-reboot). Phase 10 success criteria are accuracy-only; latency/VRAM are production-sizing concerns for the route host, not blocking.
- **DIA-06 face-voice auto speaker→character** — v1.3 differentiator (v1.2 always HITL); out of scope for this spike.

</deferred>
