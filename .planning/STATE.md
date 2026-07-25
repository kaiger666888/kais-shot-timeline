---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: 音频语义深化 — Audio Semantic Deepening
status: ready_to_plan
stopped_at: Phase 10 complete (6/6) — ready to discuss Phase 11
last_updated: 2026-07-25T14:28:08.942Z
last_activity: 2026-07-25
progress:
  total_phases: 8
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
  percent: 13
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-25)

**Core value:** 把成片解构成可导航、多轨道、带语义的分镜资产（分镜 + 分离音轨 + 对白 + 镜头语言 prompt + 跨镜可复用角色/道具注册表 + 三模态音频语义），且形态可移植——能作为下游 `@kais/infinite-canvas` 的「最终资产集合形态」被直接消费。
**Current focus:** Phase 11 — contract v1.2

## Current Position

Phase: 11
Plan: Not started
Status: Ready to plan
Last activity: 2026-07-25

Progress: [██████████] 100%

## Performance Metrics

**Velocity (cumulative v1.0 + v1.1 historical):**

- Total plans completed: 31 (v1.0: 7, v1.1: 16 — archived)
- v1.2 plans completed: 0

**By Phase (v1.2 — populates as plans complete):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 10. Risk-Validation Spike + Route Stub | 0/? | - | - |
| 11. Contract v1.2 | 0/? | - | - |
| 12. Producer Route Client | 0/? | - | - |
| 13. SPEAKER-01 Linkage HITL | 0/? | - | - |
| 14. Pipeline Integration | 0/? | - | - |
| 15. Layered Reproduction Prompts | 0/? | - | - |
| 16. HTML Gallery | 0/? | - | - |
| 17. Canvas Consumer | 0/? | - | - |
| 10 | 6 | - | - |

*v1.2 metrics populate as plans complete*
| Phase 10 P01 | 7m20s | 3 tasks | 7 files |
| Phase 10 P02 | 38 | 2 tasks | 3 files |
| Phase 10 P06 | ~25min | 3 tasks (1 checkpoint pre-resolved) | 4 files |
| Phase 10 P06 | 25min | 3 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Locked decisions entering v1.2 (from /gsd:new-milestone):

- **v1.2 engine location**: kais-aigc-platform route-based (NOT local ML in producer) — continues v1.0/v1.1 loose coupling; shot-timeline takes zero new ML deps; reuses v1.1 `step_semantic` httpx+graceful-degrade pattern.
- **v1.2 three modalities together**: dialogue + music + sfx in one milestone (user needs all 3 to support "audio reproduction"); per-modality models but one milestone.
- **v1.2 layered reproduction prompts**: TTS / music-gen / foley (NOT single NL prompt) — different generators need different recipes.
- **v1.2 schema bump**: `1.1 → 1.2` (minor, pure-additive, byte-identical-absent) — NOT `"2"`, reserve major for future breaking change.
- **v1.2 SPEAKER-01 IN scope** (closes v1.1 SPEAKER-01 deferral via new `^spk_[0-9]{3}$` ID space + HITL linking; v1.1 had it as Out of Scope due to "大 lift", v1.2 reduces lift via pyannote route).
- **v1.2 spike retirement**: `audio/gen_audio_prompts.py` (quick task 260725-afz) promoted to pipeline producer; `--offline` fallback replaces spike.
- **v1.2 reproduction prompt = model-agnostic NL** (NOT NC-licensed weight embedding) — dissolves BLOCKER 2 license trap.
- **v1.2 CUDA 12.8 + WhisperX**: word-level timestamps in scope; Phase 10 spike drift threshold decides DIA-05 ship/defer.
- **v1.2 phase sequencing**: risk-validation-first (Phase 10 spike BEFORE Phase 11 contract lock) — mirrors v1.1 Phase 7 DINOv2 τ spike ("先证模型、再立契约"). Non-negotiable.

Carried from v1.0/v1.1 (still load-bearing):

- shot-timeline is authoritative spec owner / external producer (loose coupling)
- Canvas uses structural parent node (zone/phase pattern) — reuses 5 renderers, no contract bump
- Canvas work happens on branch `feat/canvas-asset-collection` in `kais-aigc-platform`
- Two-tier authority: schemas machine-checkable truth, SPEC.md human overview; on conflict schema wins
- schema_version pattern `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` (semver-lite); entire milestone shares ONE minor bump
- v1.x+1 fixture stays green under v1.x+2 schema (forward compat); v1.x+2 fixture under recovered-v1.x+1 schema yields only additionalProperties errors (backward compat proof)
- Conditional fields use `nullable + confidence` pattern; never fabricate signal when model degrades
- [Phase 10]: Plan 10-01 Wave 0 foundation complete: 7 files under spike/audio/ (common.py + 4 smoke files + aggregate_report.py scaffold + README). stratified_sample uses ceil(n/4) per bucket + dedupe (Rule 1 fix vs. plan body's n//4 which capped at 28 < 30). — Plans 03/04/05/06 can now import common.py; route_stub_smoke.sh is Plan 02's verify target.
- [Phase ?]: Plan 10-02 ROUTE-01: audio-analysis stub branched from feat/shot-analysis-route (NOT develop); mount at /api/production/audio-analysis (NO /v1/); envelope byte-identical to shot-analysis; full curl round-trip proven.
- [Phase 10]: Phase 10 spike: DIA-04 ship-nullable+confidence (SenseVoice self_consistency=100% proxy, no rigorous macro-F1) — Calibrated estimate + qualitative sanity coherent; rigorous macro-F1 deferred Phase 12+
- [Phase 10]: Phase 10 spike: MUS-04 defer to v1.3 (MERT no classifier head, PANNs zenodo-blocked) — MERT K-means clusters correlate with shot duration, NOT instruments; route host needs REAL MIR classifier
- [Phase 10]: Phase 10 spike: DIA-05 ship-experimental (boundary drift median=101.5ms<200ms; per-word aggregate low but metric-definition artifact) — Drift=word_start-segment_start inflates for interior words; refine metric Phase 12
- [Phase 10]: Phase 10 spike: CUDA path STAY-ON-12.4 (WhisperX runs cleanly on cu124 force-pin; BLOCKER 1 RESOLVED) — WhisperX 3.8.6 metadata declares torch~=2.8.0 but works on 2.6.0+cu124; not a forcing function for CUDA 12.8

### Pending Todos

- ✅ **Phase 10 spike report DONE** — `.planning/research/audio-spike-report.md` (254 lines, 4 sections + methodology + recommendations + reproducibility) covers Chinese SER (DIA-04), MIR head-to-head (MUS-04), WhisperX drift (DIA-05), CUDA path. 4 outcomes locked in PROJECT.md Key Decisions (lines 122-126).
- CONTRACT-03 `SCHEMA_VERSION="1.2"` single-source must remain producer-locked (export_asset.py:55) — do not duplicate literal.

### Blockers/Concerns

- ✅ **BLOCKER 1 — CUDA 12.8 upgrade (route host): RESOLVED stay-on-12.4** (Phase 10 Plan 06). WhisperX 3.8.6 metadata declares `torch~=2.8.0` but runs cleanly on force-pinned cu124 stack (torch 2.6.0+cu124) in an isolated venv; A1 CPU mode + full cuda:0 run both OK; system torch uncontaminated (3-point canary). Route host stays at cu124; WhisperX runs in isolated venv with cu124 force-pin (Plan 10-05 pattern becomes production); CUDA 12.8 upgrade deferred indefinitely. Evidence: `.planning/research/audio-spike-report.md#section-3-whisperx-drift--dia-05-evidence--cuda-path`.
- **BLOCKER 2 — Commercial-use license (dissolved)**: no open-weights commercial music-gen/sfx model exists mid-2026. Dissolved by locked decision #7 (model-agnostic NL prompts).
- ✅ **Chinese SER cross-domain risk: RESOLVED → ship-nullable+confidence** (Phase 10 Plan 06). SenseVoice self_consistency_pct=100.0 (label-stability proxy, NOT accuracy); qualitative sanity coherent; no rigorous macro-F1 (annotation deferred). `emotion` field NULLABLE + confidence populated + fidelity_disclaimer. Evidence: `.planning/research/audio-spike-report.md#section-1-ser-sensevoice--dia-04-evidence`.
- ✅ **Polyphonic instrument recognition on Chinese folk: RESOLVED → defer MUS-04 to v1.3** (Phase 10 Plan 06). MERT-v1-95M has NO instrument classifier head — only K-means embedding clusters (5) correlating with shot DURATION, NOT instruments. PANNs Cnn14 BLOCKED (zenodo.org download stalled; hf-mirror `.pth` conversion deferred). NO instrument predictions produced. `instruments` field omitted in v1.2 schema. Evidence: `.planning/research/audio-spike-report.md#section-2-mir-head-to-head-mert-vs-panns--mus-04-evidence`.
- **Cross-repo branch merge**: kais-aigc-platform branches `feat/shot-geometry-nodes` + `feat/shot-analysis-route` still unmerged from v1.1; Phase 12 end-to-end and Phase 17 consumer work blocked until v1.1 routes land (graceful-degrade-must-be-proven stays the contract).
- **Cross-repo coordination cost (Phase 17)**: ~30% overhead measured in v1.0/v1.1 for consumer-side work in kais-aigc-platform `feat/canvas-asset-collection` worktree at `/data/workspace/kst-canvas-consumer`.
- **`audio-analysis` route does not yet exist (as live ML)**: ROUTE-01 stub landed Plan 10-02 (envelope byte-identical to shot-analysis); live ML (SenseVoice/WhisperX/MERT/PANNs loaded behind the route) deferred to post-merge smoke check (mirror v1.1 Phase 7 CAST-01..04/08 deferred pattern).

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260725-afz | 音频 prompt 反推 spike — per-shot audio-gen NL prompt（本地启发式 Demucs+Whisper+onset-tempo, sidecar `audio_prompts.json`, 合约零改动）; concept validated on 3 episodes → 晋升 v1.2 Phase 15 pipeline producer input | 2026-07-25 | 3a85a56 | [260725-afz-prompt-spike-audio-gen-nl-prompt-demucs-](./quick/260725-afz-prompt-spike-audio-gen-nl-prompt-demucs-/) |

## Deferred Items

Items acknowledged and carried forward from v1.0 + v1.1 Out-of-Scope + v1.2 planning:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v1.0 (Out of Scope) | NATIVE-01/02: canvas native timeline renderer + native Range media service | Deferred — next milestone | 2026-07-20 |
| v1.0 (Out of Scope) | ORCH-01: shot-timeline as canvas orchestration skill (tight-coupling alt) | Deferred — evaluate post-v1.0 | 2026-07-20 |
| v1.0 (Accepted) | WR-01/WR-04: save-v2 secondary-path latent bugs | Consumer-repo backlog | 2026-07-21 |
| v1.1 (v2) | REID-01: InsightFace `antelopev2`/`buffalo_l` face fusion signal | Deferred — non-commercial license | 2026-07-24 |
| v1.1 (v2) | PROMPT-DIALECT-01: prompt_text dialect switch (paragraph vs keyword) | Deferred — v2 | 2026-07-24 |
| v1.1 (v2) | CROSSVIDEO-01: cross-video character continuity | Deferred — v2 | 2026-07-24 |
| v1.1 (v2) | BBOX-01/CANVAS-EDGE-01/TURNAROUND-01: display enhancements | Deferred — v2 | 2026-07-24 |
| v1.1 (Phase 6/7/9) | Live `shot-analysis` / `character-reid` route round-trip + τ calibration + e2e backend verify | Deferred — kais-aigc-platform branches unmerged; graceful-degrade proven | 2026-07-25 |
| v1.2 (Future) | DIA-06: face-voice auto speaker→character heuristic | Deferred — v1.3 differentiator; v1.2 always HITL | 2026-07-25 |
| v1.2 (Future) | MUS-07: BGM staff/MIDI transcription | Deferred — AF-10 boundary | 2026-07-25 |
| v1.2 (Future) | full V/A regression (valence mature from experimental) | Deferred — v1.3 | 2026-07-25 |
| v1.2 (Future) | cross-video audio continuity (same BGM theme / same speaker across videos) | Deferred — v2 | 2026-07-25 |
| v1.2 (CONDITIONAL) | DIA-04 dialogue emotion / DIA-05 word-level / MUS-04 instruments | Phase 10 spike resolved: DIA-04 ship-nullable+confidence; DIA-05 ship-experimental; MUS-04 defer to v1.3 | 2026-07-25 |
| v1.2 (Phase 10 spike) | MUS-04 instruments field in `audio_semantic.json` schema | Deferred — MERT has no classifier head; PANNs Cnn14 zenodo-blocked at spike time; route host needs REAL MIR classifier (Phase 12+ / v1.3) | 2026-07-25 |
| v1.2 (Phase 10 spike) | Rigorous DIA-04 macro-F1 (developer-annotated 30-segment ground truth) | Deferred — methodology_b ~1hr labor deferred; ship on calibrated estimate (self-consistency + qualitative sanity) Phase 12+ | 2026-07-25 |
| v1.2 (Phase 10 spike) | WhisperX drift metric refinement (boundary drift, not per-word-from-segment-start) + multi-episode validation | Deferred — Phase 12 once route host is up | 2026-07-25 |
| v1.2 (Phase 10 spike) | PANNs Cnn14 head-to-head vs MERT (zenodo `Cnn14_mAP=0.431.pth` download) | Deferred — Phase 12+ route-host selection; hf-mirror `nicofarr/panns_Cnn14` safetensors→pth conversion non-trivial | 2026-07-25 |

## Session Continuity

Last session: 2026-07-25T13:38:23.121Z
Stopped at: "Phase 10 spike complete — 4 locked outcomes in PROJECT.md Key Decisions (lines 122-126: models_used per modality / CUDA stay-on-12.4 / DIA-04 ship-nullable+confidence / MUS-04 defer-v1.3 / DIA-05 ship-experimental). Spike report at `.planning/research/audio-spike-report.md` (254 lines). BLOCKER 1 RESOLVED stay-on-12.4. Phase 10 plans 01-06 all done. Ready for /gsd:verify-work then /gsd:plan-phase 11 (Contract v1.2 lock)."
Resume file: None

## Operator Next Steps

- Run `/gsd:verify-work` against Phase 10 (5 ROADMAP SC all empirically addressed)
- Then run `/gsd:plan-phase 11` to lock the v1.2 contract (Phase 11 must respect: DIA-04 emotion field NULLABLE + confidence + fidelity_disclaimer; MUS-04 instruments field OMITTED; DIA-05 word-level timestamps EXPERIMENTAL with metric-definition caveat; WhisperX runs in isolated cu124 venv)
- Phase 11 contract lock is now unblocked — empirical basis delivered by Phase 10 spike (non-negotiable invariant #1 satisfied)
