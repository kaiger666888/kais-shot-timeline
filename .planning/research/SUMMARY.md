# Project Research Summary — v1.2 音频语义深化

**Project:** kais-shot-timeline
**Milestone:** v1.2 音频语义深化 (route-based three-modality audio semantic analysis + layered reproduction prompts)
**Domain:** Loosely-coupled media-asset producer adding a 3rd route-dependent ML semantic layer on top of v1.0 (ShotTimelineAsset contract) and v1.1 (cinematography route + cross-shot re-id registry)
**Researched:** 2026-07-25
**Confidence:** **HIGH** overall — integration patterns are direct mirrors of v1.1 SHIPPED phases; cross-domain Chinese ML precision numbers (SER, MIR on folk instruments) are MEDIUM-LOW until Phase 1 spike validates on 《小江湖》.

## Executive Summary

v1.2 extends the validated v1.0 Demucs+Whisper baseline and the v1.1 route-pattern family (`call_shot_analysis.py` per-shot, `call_reid.py` per-video) with a **third sibling: `analysis/call_audio_analysis.py`** — a thin httpx client that talks to a new `kais-aigc-platform/audio-analysis` route and produces a single new optional sidecar `audio_semantic.json` carrying three modalities (dialogue / music / sfx) plus layered reproduction prompts (TTS / music-gen / foley). The `shot-timeline` repo takes **zero new ML dependencies** — every heavy model lives behind the route host. The milestone closes the v1.1 SPEAKER-01 deferral via a new `spk_NNN` ID space + HITL `link_speakers.py` mirroring v1.1's `apply_edits.py` confirmed-only gate. The schema bump `1.1 → 1.2` is **pure-additive** and follows the exact 6-touchpoint propagation pattern v1.1 Phase 5 proved.

**Recommended approach: risk-validation-first sequencing** (unanimous across all 4 researchers, mirrors v1.1 Phase 7 DINOv2 τ spike): Phase 1 must empirically validate four unknowns on **1 episode of 《小江湖》** before any contract locks — (a) Chinese SER cross-domain accuracy via **SenseVoice** (FunAudioLLM, native Mandarin+Cantonese, emits 7 emotions + 8 audio-event tags in one pass — directly mitigates the highest cross-domain risk); (b) polyphonic instrument recognition esp. Chinese folk (erhu/pipa/guzheng/dizi; ChMusic suggests mAP 0.15-0.30); (c) WhisperX word-level alignment drift on long Chinese audio; (d) pyannote community-1 diarization DER. **DIA-04 (dialogue emotion), MUS-04 (instrument recognition), DIA-05 (word-level) are CONDITIONAL** — ship-or-defer-to-v1.3 hinges on Phase 1 thresholds.

**Two BLOCKER-class prerequisites** (see callouts): (1) **CUDA 12.8 upgrade** required by WhisperX (project on cu124); (2) **commercial-use license trap** — no open-weights commercial music-gen/sfx model exists mid-2026. **Both dissolvable with clean scoping decisions** (see OPEN DECISIONS #1/#2).

**Fidelity ceiling is the defining constraint.** Reproduction prompts ≠ exact audio restoration: TTS ~70%, music-gen ~60-75%, foley ~80% single / 40-60% ambient. **AF-01 "perfect restoration" must go in Out of Scope.** Every prompt field needs `nullable + confidence`.

## Key Findings

### Recommended Stack (detail: STACK.md)

**Route-vs-client split governs everything:**

| Side | Adds | Forbids |
|------|------|---------|
| **`kais-aigc-platform/audio-analysis` route (cross-repo)** | WhisperX, pyannote.audio 3.1, SenseVoice (funasr), MERT-v1-95M, librosa, PANNs (optional) | — (already a ComfyUI-bearing route host) |
| **`shot-timeline` (this repo)** | `analysis/call_audio_analysis.py` (near-clone of `call_shot_analysis.py`); `httpx` (already a v1.1 dep); stdlib only | ANY new ML dep |

**Headline picks (route side):**
- **SenseVoice (FunAudioLLM)** — **headline pick**, mitigates #1 cross-domain risk. Native Mandarin+Cantonese SER (NOT RAVDESS English), MIT, 8.9k★, 5-15× faster than Whisper. Emits 7 emotion labels + 8 audio-event tags (BGM/applause/laughter/cry/cough/sneeze/breath) in ONE pass — covers dialogue-emotion AND part of sfx free.
- **WhisperX** (CUDA 12.8 hard-req) — wraps faster-whisper (preserves `large-v3`) + wav2vec2 word-alignment + bundled `pyannote/speaker-diarization-community-1` (CC-BY-4.0, NOT gated). Use WhisperX integrated `align()+diarize()`, NOT WhisperX + standalone-pyannote (temporal-drift bug, arXiv 2603.04809).
- **pyannote.audio 3.1** — fallback diarization; MIT code; 3.1 weights gated / community-1 CC-BY-4.0.
- **MERT-v1-95M** (m-a-p, transformers ≥4.40) — SOTA on 14 MIR tasks (ICLR 2024); 95M over 330M for VRAM discipline. Phase 1 MUST confirm on Chinese pop/animation BGM.
- **librosa 0.11.x** — production-honest DSP baseline (beat_track + chroma key + onset_detect); CPU-only.
- **PANNs / HTS-AT** — complement to MERT for polyphonic sfx taxonomy (AudioSet 527 classes); sfx COMPLEMENT, not MERT replacement.
- **CosyVoice 2 / Fun-CosyVoice 3.0** (Apache 2.0) — **commercial-safe TTS** reproduction-prompt target; same FunAudioLLM family as SenseVoice; zero-shot voice cloning (fits SPEAKER-01).
- **GPT-SoVITS v4** (MIT) — alternate TTS target (1-min few-shot cloning).

**Critical:** WhisperX PyPI hard-requires **CUDA 12.8** (project runtime is `torch 2.6.0+cu124`). SenseVoice/pyannote/MERT/librosa all work on 12.4. *(Orchestrator note: dropping WhisperX + using faster-whisper (existing) + standalone pyannote keeps everything on 12.4 — see OPEN DECISION #2.)*

### Expected Features (detail: FEATURES.md)

**Table stakes (must):** DIA-01 segment-level dialogue; DIA-02 speaker diarization; DIA-03 speaker_id→character_id HITL; MUS-01 BGM presence segmentation; MUS-02 BGM tempo; MUS-03 BGM discrete mood; SFX-01 per-shot foley description; CONTRACT-01 audio_semantic.json sidecar + schema 1.1→1.2; CONTRACT-02 producer httpx client; PROMPT-01 3-layer reproduction prompts; DEGRAD-01 graceful-degrade; PIPE-01 step_audio_semantic slot.

**Differentiators (should, several CONDITIONAL):** DIA-04 dialogue emotion (**CONDITIONAL: ship if Phase 1 SER ≥50%, defer if <40%**); DIA-05 word-level timestamps (**CONDITIONAL: ship experimental if <200ms drift on ≥80% segments; unreliable on Chinese**); MUS-04 multi-label instrument incl. folk (**CONDITIONAL: ship if mAP ≥0.30, defer if <0.20**); MUS-05 BGM key; MUS-06 V/A regression (arousal ship, valence experimental); SFX-02 foley timestamps + AudioSet; SFX-03 foley complex sequences; PROMPT-02 TTS reference audio citation; PROMPT-03 music structure tags; CONSUMER-01 canvas audio nodes (deferrable); DIA-06 face-voice auto (defer v1.3).

**Anti-features (Out of Scope):** AF-01 perfect restoration; AF-02 forced emotion every shot; AF-03 forced instruments every shot; AF-04 full V/A regression; AF-05 full-auto speaker→character; AF-06 route-local fallback in producer; AF-07 retraining models; AF-08 exact sync reproduction; AF-09 word-level <50ms guarantee; AF-10 BGM staff/MIDI transcription.

### Architecture Approach (detail: ARCHITECTURE.md)

`step_audio_semantic` = **third sibling of the v1.1 route-pattern family** — per-shot httpx client + per-shot cache + poisoned-cache invalidation + read-merge-write warnings + graceful-degrade. All v1.0/v1.1 invariants carry.

**Major components:**
1. **`analysis/call_audio_analysis.py`** (NEW) — per-shot cache `route_cache/audio_analysis/shot_XXX.json` (4-tuple key); poisoned-cache invalidation (mirror `call_reid.py`); read-merge-write `[audio]` warnings tag; graceful-degrade to empty `shots:[]`. Mirrors `call_shot_analysis.py` (NOT `call_reid.py` — SER/MIR/diarization are shot-local).
2. **`registry/link_speakers.py` + `html/gen_speaker_review.py`** (NEW) — HITL CLI mapping `spk_NNN → char_NNN|null`; confirmed-only hard gate (mirror `apply_edits.py`); produces `speakers.json` sidecar.
3. **3 new schemas** — `audio_semantic.schema.json` + `speakers.schema.json` + `speaker-edits.schema.json`.
4. **Pipeline slot 7** (between `step_reid[6]` and `step_timeline`); counter `[N/8] → [N/9]` (17 banner instances).
5. **Schema bump propagation** — 6 mechanical touchpoints (SCHEMA_VERSION, asset.schema.json data.audio_semantic+data.speakers, validate.py V12_ORDER, verify_contract.py cross-version + fixture-consistency, SPEC §4 Changelog + §5.8/§5.9, export_asset.py conditional emit).
6. **SPEAKER-01 → `^spk_[0-9]{3}$`** NEW ID space (NOT reusing `^char_[0-9]{3}$`); `speakers.json` canonical; `char_id` nullable (narrator/crowd); `review_state` proposed/confirmed/rejected.
7. **Canvas consumer** — `import-from-dir.ts` appends `"1.2"`; §7 post-process emits 1 dialogue + 1 music + 1 sfx `type:"asset"` child per shot; NO custom renderer, NO Zod bump.

### Critical Pitfalls (detail: PITFALLS.md)

**10 BLOCKER-class (must solve to ship):** (1) Chinese SER cross-domain drop — SenseVoice + Phase 1 spike, defer DIA-04 if macro-F1 <0.5; (2) WhisperX migration breaks faster-whisper fallback + word drift — add whisperx as OPTION not replacement, word-level optional; (3) pyannote gating + speaker-count/overlap/mapping — HF_TOKEN route-side only, spk_NNN acoustic-only, HITL mandatory, `overlapping:true` flag; (4) **schema byte-identical-absent** — `git diff v1.1..v1.2 -- spec/schemas/audio_analysis.schema.json` must be 0 lines, three-tier shape gate (MINIMAL/V11/V12), bidirectional cross-version self-test; (5) MIR false-confidence — `instruments: list[{label,confidence}]`, MIR on drums+bass+other union, tempo double-gated; (6) layered-prompt over-promise — `fidelity_disclaimer` field + per-field confidence + HTML "estimated" labels; (7) per-shot vs per-video cache confusion — cache-granularity table + abstract `_cache.py` helper; (8) green-verify-hides-blocker (v1.1 Phase 9 CR-01 recurrence) — Phase 2 writes 故意漂移 self-test; (9) **multi-resolution time aggregation ambiguity** (NEW) — Phase 2 documents `{level,aggregation}` per field; (10) HF_TOKEN leakage via `_safe_error` on 401 — extend regex + warning-sidecar whitelist.

**Recurring v1.1 (DEGRADATION-acceptable, mandatory prevention):** [N/8]→[N/9] banner renumber (17 instances, recommend TOTAL_STEPS constant); XSS `_esc` sink (layered-prompt HTML = new attack surface); `__file__`-in-`python3 -c` verify (plan-checker grep); cross-repo route unmerged + graceful-degrade-must-be-proven (3-scenario verify per phase); model download timeout on cold start (pre-download).

---

## BLOCKER Prerequisites (callout)

### BLOCKER 1 — CUDA 12.8 upgrade (route host)
WhisperX PyPI hard-requires CUDA 12.8; project is `torch 2.6.0+cu124`. WhisperX alone forces it — SenseVoice/pyannote 3.1/MERT/librosa all work on 12.4. **Dissolvable:** drop WhisperX → stay 12.4 → use faster-whisper (existing) + standalone pyannote + SenseVoice + MERT/librosa. Cost: lose word-level alignment (DIA-05), already flagged unreliable-on-Chinese/experimental. → OPEN DECISION #2.

### BLOCKER 2 — Commercial-use license escalation (roadmap decision)
CosyVoice 2 (Apache 2.0) + GPT-SoVITS v4 (MIT) are commercial-safe TTS. But F5-TTS / Stable Audio Open / AudioLDM2 are all NC-licensed; **no open-weights commercial music-gen/sfx model exists mid-2026.** **Dissolvable:** ship model-agnostic NL reproduction prompts (commercial-safe output; generators = user's downstream choice) — Phase 1 documents target dialect without shipping NC weights. → OPEN DECISION #1.

---

## Out-of-Scope Callout — Fidelity Ceiling

**AF-01 "Perfect restoration" must be in Out of Scope.** Reproduction prompt ≠ exact restoration. Ceilings: TTS ~70%, music-gen ~60-75%, foley ~80% single / 40-60% ambient. Every prompt field MUST carry `nullable + confidence`. SPEC documents `fidelity_disclaimer`. README must NOT say "perfectly reconstruct"/"exact restoration".

---

## Suggested 8-Phase Structure (for roadmapper)

| # | Phase | Goal | Key REQs | Research? |
|---|-------|------|----------|-----------|
| 1 | Risk-Validation Spike + Route Stub | validate SenseVoice/MERT/pyannote/WhisperX on 1 ep BEFORE contract; CUDA + license decisions | de-risks DIA-04/05, MUS-04 | HIGH (IS the research) |
| 2 | Contract v1.2 | 3 schemas + 12-file fixture + SCHEMA_VERSION="1.2" + cross-version self-test | CONTRACT-01 | standard (mirror v1.1 P5) |
| 3 | Producer Route Client | `call_audio_analysis.py` thin httpx + per-shot cache + graceful-degrade | CONTRACT-02, DEGRAD-01 | standard (mirror v1.1 P6) |
| 4 | SPEAKER-01 Linkage HITL | `link_speakers.py` + `gen_speaker_review.py` confirmed-only → `speakers.json` | DIA-02, DIA-03 | MEDIUM (HITL UX) |
| 5 | Pipeline Integration | `step_audio_semantic` slot 7 + [N/9] renumber + smoke harness | PIPE-01 | standard (mirror v1.1 P6/7) |
| 6 | Layered Reproduction Prompts | promote `gen_audio_prompts.py` spike → in-place `reproduction.{tts,music_gen,foley}` + `--offline` fallback | PROMPT-01/02/03 | MEDIUM (prompt dialect) |
| 7 | HTML Gallery | dialogue/music/sfx chips + speaker→character chip + XSS hardening | (PRESENT) | standard (mirror v1.1 P8) |
| 8 | Canvas Consumer (deferrable) | `import-from-dir.ts` v1.2 + audio asset nodes | CONSUMER-01 | standard (mirror v1.1 P9) |

---

## OPEN DECISIONS for the User

1. **Reproduction-prompt target roadmap** — (a) model-agnostic NL prompts now (commercial-safe, generators = user's downstream choice) [recommended: dissolves BLOCKER 2]; (b) research-only specific models (NC-licensed); (c) Stable Audio paid API (commercial). Affects Phase 2 `reproduction.music_gen`/`reproduction.foley` field shape.
2. **WhisperX + CUDA 12.8 vs stay-on-12.4** — (a) stay 12.4, drop WhisperX, segment-level SLA + standalone pyannote (word-level DIA-05 becomes deferred/experimental) [recommended: dissolves BLOCKER 1, aligns with Features' Chinese-word-level caveat]; (b) upgrade CUDA 12.8 for WhisperX word-level.
3. **Phase 1 pass/fail thresholds** (calibrate against 《小江湖》) — proposed defaults: SER ≥50% ship DIA-04 / <40% defer; folk-instrument mAP ≥0.30 ship MUS-04 / <0.20 defer; word drift <200ms on ≥80% (moot if WhisperX dropped); pyannote DER <15% community-1 / >20% switch to gated 3.1.
4. **Pipeline slot 6 vs 7** — ARCHITECTURE recommends **7** (step_timeline rendering depends on audio_semantic final); PITFALLS suggested 6. [Orchestrator pick: **7**.]
5. **Layered-prompt file shape** — (a) in-place `audio_semantic.json#shots[].reproduction.{tts,music_gen,foley}` [recommended]; (b) 3 separate sidecars.
6. **MERT vs PANNs head-to-head** — defer pick to Phase 1 (no benchmark on Chinese pop).

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (production picks); MEDIUM (MIR MERT-vs-PANNs → Phase 1); MEDIUM (music-gen/sfx license) | SenseVoice = headline, mitigates #1 risk |
| Features | MEDIUM (methodology HIGH; Chinese precision LOW until Phase 1) | DIA-04/MUS-04/DIA-05 conditional |
| Architecture | HIGH (all claims verified against live source) | 3rd-sibling addition, every pattern v1.1 proved |
| Pitfalls | HIGH (v1.1 9 blockers + 22 warnings anchored; ML pitfalls via official docs) | Recurring v1.1 pitfalls mechanical w/ proven greps |

**Overall:** HIGH for integration/contract/producer; MEDIUM for ML precision (pending Phase 1 on 《小江湖》).

## Gaps to Address
- **MuQ**: did NOT surface as a real published 2025 model (possible name confusion) — treat not-available until proven.
- **Polyphonic instrument recognition on Chinese pop**: no MERT-vs-PANNs benchmark on erhu/pipa/guzheng — Phase 1 must produce.
- **SenseVoice cross-domain on Chinese animation**: benchmark is standard test sets, not animation — Phase 1 spot-check.
- **WhisperX community-1 DER on Chinese animation**: multi-speaker + overlap + BGM — Phase 1 measures.

## Sources (aggregated)

**Primary (HIGH):** v1.1 SHIPPED code (run_pipeline.py, analysis/call_shot_analysis.py, analysis/call_reid.py, scripts/export_asset.py, spec/validate.py, scripts/verify_contract.py, spec/schemas/asset.schema.json, audio/gen_audio_prompts.py, spec/SPEC.md); v1.1 phase archives + RETROSPECTIVE; WhisperX (github m-bain); pyannote 3.1 (HF card); SenseVoice (github FunAudioLLM, funasr ≥1.3.26); MERT-v1 (arXiv 2306.00107, ICLR 2024); CosyVoice (Apache 2.0); GPT-SoVITS v4 (MIT); Stable Audio Open (Stability Community = NC); F5-TTS (MIT code + CC-BY-NC pretrained); librosa docs.

**Secondary (MEDIUM):** WhisperX Issue #810 + alignment.py (Chinese default align model jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn); arXiv 2603.04809 WhisperAlign (temporal drift w/ standalone pyannote); emotion2vec+ (ACL 2024); ChMusic (Gong 2021, 11-class folk); MIRFLEX (arXiv 2411.00469); Cross-Corpus SER (MDPI 2025 ~46.75%); audEERING valence gap; EmoBox (INTERSPEECH 2024).

**Tertiary (LOW — Phase 1 validation):** SenseVoice SER figures (standard sets, not animation); MERT on Chinese pop/animation BGM; MuQ (unverified).

---

*Research completed: 2026-07-25. Detail docs: STACK.md / FEATURES.md / ARCHITECTURE.md / PITFALLS.md (committed 491bcad). Ready for requirements → roadmap.*
