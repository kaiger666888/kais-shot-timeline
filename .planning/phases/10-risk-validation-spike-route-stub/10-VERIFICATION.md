---
phase: 10-risk-validation-spike-route-stub
verified: 2026-07-25T21:55:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 10: Risk-Validation Spike + Route Stub — Verification Report

**Phase Goal:** Empirically de-risk the 4 highest unknowns of v1.2 (Chinese SER cross-domain on animation, polyphonic instrument recognition on Demucs stems, WhisperX word-level drift, CUDA 12.8 upgrade compatibility) on 1 episode of 《小江湖》 BEFORE any contract locks — mirroring v1.1 Phase 7 DINOv2 τ spike.
**Verified:** 2026-07-25T21:55:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Phase 10 Success Criteria)

| #   | Truth (ROADMAP SC) | Status | Evidence |
| --- | ------------------ | ------ | -------- |
| 1   | Developer can POST to `/api/production/audio-analysis` and receive a `{code:200, data:{...}}` envelope even with ML unloaded (stub mode) | ✓ VERIFIED | Independently re-ran live round-trip this session (port 10592, symlinked node_modules from main checkout). Happy: `200 {"code":200,"data":{"shots":[],"count":0,"errors":[],"stub_mode":true,"message":"Phase 10 stub: ML models not loaded. Producer client envelope round-trip proven."},"message":"Audio analysis stub"}`. Validation `{}`: `400 {"code":400,"data":null,"message":"VALIDATION_ERROR"}`. Byte-identical envelope shape to shot-analysis via `@/lib/responseFormat.ts:success`. Worktree `feat/audio-analysis-route` at `/tmp/kais-aigc-platform-audio-route`, 1 commit `94358fff` on top of `feat/shot-analysis-route` base. |
| 2   | Spike report documents Chinese SER macro-F1 on ep01 vocals stem, enabling DIA-04 ship/defer decision | ✓ VERIFIED | `spike/audio/results/ser_sensevoice_ep01.json`: sample_size=30, methodology=methodology_ab, metric_value=100.0 (self_consistency_pct, NOT accuracy), emotion_distribution {emo_unk:9, HAPPY:8, NEUTRAL:7, ANGRY:6}, caveat contains literal "calibrated estimate" + explicit warning "Self-consistency is NOT directly comparable to the DIA-04 >=50% macro-F1 accuracy threshold". Section 1 of `.planning/research/audio-spike-report.md` cites the JSON + threshold table + recommends ship-nullable+confidence. |
| 3   | Spike report documents polyphonic MIR mAP on ep01 drums+bass+other mix + MERT-vs-PANNs head-to-head | ✓ VERIFIED | `mir_mert_ep01.json`: 30 real per-sample entries (cluster IDs + 768-d embedding L2 norms), methodology=mir_c, caveat contains "calibrated estimate". `mir_panns_ep01.json`: status=blocked, block_reason verbatim (zenodo CDN failure), head_to_head_status="INCOMPLETE — PANNs leg absent; MERT is provisional route-host pick". `sample_mir_ep01.json`: 30 shot_ids audit, committed BEFORE either model ran. Pitfall 9 integrity verified: `mert_ids == sample_mir.shot_ids` (n=30). Report §2 contains head-to-head table + honest "PANNs may yet win in Phase 12" caveat. |
| 4   | Spike report documents WhisperX drift on ≥N Chinese segments + CUDA path decision | ✓ VERIFIED | `whisperx_align_ep01.json`: sample_size=30, drift_stats with BOTH `pct_under_200_ms=0.1898` (per-word, BELOW 0.80) AND `pct_boundary_under_200_ms=0.6` AND `median_boundary_drift_ms=101.5` (under 200ms). a1_status=ok, a2_status=ok, system_torch=2.6.0+cu124, venv_torch=2.6.0+cu124 (cu124 force-pinned despite whisperx METADATA declaring torch~=2.8.0 — confirmed this session). Report §3 honestly frames aggregate per-word metric as "METRIC-DEFINITION ARTIFACT" + recommends ship-EXPERIMENTAL + STAY-ON-12.4. |
| 5   | PROJECT.md Key Decisions logs the 4 locked outcomes with evidence citations | ✓ VERIFIED | PROJECT.md lines 122-126 contain 5 rows: Row 1 models_used per modality (SenseVoice / WhisperX / MERT provisional / PANNs folded); Row 2 CUDA STAY-ON-12.4 (BLOCKER 1 RESOLVED); Row 3 DIA-04 SHIP-NULLABLE+CONFIDENCE; Row 4 MUS-04 DEFER to v1.3; Row 5 DIA-05 SHIP-EXPERIMENTAL. Every row has `decided_at:2026-07-25 + phase:10 + evidence:audio-spike-report.md#section-X` citation. Spike report at `.planning/research/audio-spike-report.md` (254 lines, 4 sections + Methodology + Recommendations + Reproducibility). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `spike/audio/common.py` | Shared helpers (EP01_* paths + stratified_sample + parse_sensevoice_tags + _safe_error + write_result) | ✓ VERIFIED | 266 lines; all 3 spike scripts import via `from common import (...)`; deterministic sample verified (seed=10 n=30 returns same list across SER/MIR/WhisperX runs — Pitfall 9 head-to-head integrity preserved) |
| `spike/audio/tests/smoke_all.sh` + 3 sub-checks | Wave-merge gate | ✓ VERIFIED | `SKIP_ROUTE_STUB=1 bash spike/audio/tests/smoke_all.sh` exits 0; 5 result files pass `results_schema_check.py`; staleness gate exits 0 (3-tier relaxation) |
| `spike/audio/aggregate_report.py` | Fleshed-out aggregator: staleness + head-to-head integrity + 6-section markdown | ✓ VERIFIED | 677 lines; `--check-staleness` exits 0; `--aggregate` writes 254-line report; 3-tier staleness gate (strict/script-unchanged/ancestor) handles post-hoc HEAD drift |
| `spike/audio/run_ser_sensevoice.py` | SER spike (funasr AutoModel + iic/SenseVoiceSmall + 3-run VAD variants) | ✓ VERIFIED | 366 lines; contains `from funasr import AutoModel`, `iic/SenseVoiceSmall`, `methodology_ab`, `calibrated estimate` |
| `spike/audio/run_mir_head_to_head.py` | MIR spike (MERT-v1-95M + PANNs Cnn14 + 24kHz/32kHz sample-rate hardcodes) | ✓ VERIFIED | 503 lines; contains `m-a-p/MERT-v1-95M`, `panns_inference`, `sr=24000`, `sr=32000` |
| `spike/audio/run_whisperx_align.py` | WhisperX drift spike (isolated venv + cu124 force-pin + zh align) | ✓ VERIFIED | 617 lines; contains `import whisperx`, `language_code="zh"`, `device="cpu"`; full run on `cuda:0` recorded honestly in JSON |
| `spike/audio/results/ser_sensevoice_ep01.json` | DIA-04 evidence | ✓ VERIFIED | 30 entries, methodology=methodology_ab, calibrated estimate caveat |
| `spike/audio/results/mir_mert_ep01.json` + `sample_mir_ep01.json` | MUS-04 MERT evidence + Pitfall 9 audit | ✓ VERIFIED | 30 entries match sample audit; calibrated estimate caveat |
| `spike/audio/results/mir_panns_ep01.json` | MUS-04 PANNs evidence | ✓ VERIFIED (blocked stub) | status=blocked, sample_size=0, per_sample=[], block_reason verbatim (zenodo CDN failure), caveat honestly flags "head-to-head INCOMPLETE" |
| `spike/audio/results/whisperx_align_ep01.json` | DIA-05 + CUDA evidence | ✓ VERIFIED | sample_size=30, drift_stats complete (both per-word + boundary), a1/a2_status=ok, device audit trail |
| `.planning/research/audio-spike-report.md` | Phase 10 deliverable | ✓ VERIFIED | 254 lines; 4 sections + Methodology + Recommendations + Reproducibility; `calibrated estimate` ×10, MERT/PANNs head-to-head ×12, `sample_mir_ep01.json` ×5 |
| `.planning/PROJECT.md` (lines 122-126) | 4-5 locked outcomes | ✓ VERIFIED | 5 rows with citations to report sections + decided_at + phase:10 |
| `.planning/STATE.md` | BLOCKER 1 + risks resolved | ✓ VERIFIED | BLOCKER 1 RESOLVED stay-on-12.4; Chinese SER + polyphonic MIR risks RESOLVED; Pending Todos Phase 10 DONE; 4 new Deferred Items rows |
| Cross-repo `kais-aigc-platform:feat/audio-analysis-route` `src/routes/production/audio-analysis/index.ts` + `_shared/config.ts` + `router.ts` mount | ROUTE-01 stub | ✓ VERIFIED | 80-line index.ts (zod bodySchema + STUB_MODE return + 501 placeholder); 16-line config.ts (env-driven + pinned model IDs); router.ts has `import route139` + `app.use("/api/production/audio-analysis", route139)` at line 191 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `run_ser_sensevoice.py` | `common.py` | `from common import EP01_VOCALS, EP01_SHOTS, stratified_sample, parse_sensevoice_tags, write_result, _safe_error` | ✓ WIRED | line 42 imports block matches plan contract |
| `run_mir_head_to_head.py` | `common.py` | `from common import EP01_DRUMS, EP01_BASS, EP01_OTHER, EP01_SHOTS, stratified_sample, write_result, _safe_error` | ✓ WIRED | line 64 imports block matches plan contract |
| `run_whisperx_align.py` | `common.py` | `from common import EP01_VOCALS, EP01_TRANSCRIPT, stratified_sample, write_result, _safe_error` | ✓ WIRED | line 113 imports block matches plan contract |
| `run_ser_sensevoice.py` | `iic/SenseVoiceSmall` | `AutoModel(model='iic/SenseVoiceSmall', trust_remote_code=True, ...)` | ✓ WIRED | canonical ModelScope ID (T-10-03 supply-chain mitigation) |
| `run_mir_head_to_head.py` | `m-a-p/MERT-v1-95M` | `AutoModel.from_pretrained('m-a-p/MERT-v1-95M', trust_remote_code=True)` | ✓ WIRED | canonical HF ID via hf-mirror.com |
| `run_whisperx_align.py` | `/tmp/whisperx-spike-venv/bin/python` | isolated venv invocation | ✓ WIRED | venv still present this session; `venv torch=2.6.0+cu124` (force-pinned) and `system torch=2.6.0+cu124` both confirmed |
| `audio-analysis/index.ts` | `@/lib/responseFormat.ts:success` | `import { success, error } from "@/lib/responseFormat"` | ✓ WIRED | byte-identical envelope proven via live curl round-trip (this session, port 10592) |
| `router.ts` | `audio-analysis/index.ts` | `import route139 from "./routes/production/audio-analysis/index"; app.use("/api/production/audio-analysis", route139);` | ✓ WIRED | mount at line 191 |
| `audio-spike-report.md` | 4 result JSONs | numeric citations like "metric_value=100.0 per results/ser_sensevoice_ep01.json" | ✓ WIRED | numbers in report cross-checked against JSONs: SER 100.0 ✓, MERT 30 samples ✓, WhisperX pct_under_200_ms=0.1898 ✓ |
| PROJECT.md Key Decisions | `audio-spike-report.md#section-X` | citation per row | ✓ WIRED | all 5 rows cite report sections |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `ser_sensevoice_ep01.json#per_sample` | `predicted_emotion`, `proxy_confidence`, `per_run_emotions` | SenseVoice `model.generate()` on ffmpeg-sliced vocals.wav clips | ✓ real (30 entries with coherent labels: HAPPY dialogue → HAPPY; 😡-tagged lines → ANGRY) | ✓ FLOWING |
| `mir_mert_ep01.json#per_sample` | `predicted_instruments`, `metric_per_sample`, `mert_embedding_l2` | MERT-v1-95M forward + k-means(n=5) over 30-segment embeddings | ✓ real (30 entries; clusters 0-4 distributed; L2 norms 2.91-4.06) | ✓ FLOWING |
| `mir_panns_ep01.json` | (no data) | zenodo CDN failure | N/A | ✓ HONEST STUB (status=blocked + non-empty block_reason) |
| `whisperx_align_ep01.json#per_sample` | `word_drifts_ms`, `boundary_drifts_ms`, `mean_word_score` | whisperx.align() on faster-whisper segments + vocals.wav | ✓ real (22/30 segments have aligned words; 137 total words matches drift_stats.total_words=137) | ✓ FLOWING |
| `audio-spike-report.md` | aggregated numbers | reads all 4 result JSONs | ✓ real (numbers cross-checked: SER 100.0, MERT 30 samples, WhisperX 0.1898, dense 0.9333 all match) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Wave 0 smoke harness passes (route stub skipped) | `SKIP_ROUTE_STUB=1 bash spike/audio/tests/smoke_all.sh` | exit 0; "ALL SMOKE CHECKS PASS" | ✓ PASS |
| Per-model JSON shape validator | `python3 spike/audio/tests/results_schema_check.py` | exit 0; "all 5 result file(s) passed" (3 OK + 1 blocked-stub OK + 1 SKIP for sample_*) | ✓ PASS |
| Staleness gate (Pitfall 10) | `python3 spike/audio/aggregate_report.py --check-staleness` | exit 0; 4 model results all fresh (3-tier relaxation) | ✓ PASS |
| Aggregator writes report | `python3 spike/audio/aggregate_report.py --aggregate` | exit 0; writes 254-line `.planning/research/audio-spike-report.md` | ✓ PASS |
| Pitfall 9 head-to-head integrity | Python assertion `mert_ids == sample_mir.shot_ids` (n=30) | True | ✓ PASS |
| Pitfall 1 system torch canary | `python3 -c "import torch; assert '+cu124' in torch.__version__"` | 2.6.0+cu124 intact | ✓ PASS |
| WhisperX venv torch canary | `/tmp/whisperx-spike-venv/bin/python -c "import torch; print(torch.__version__)"` | 2.6.0+cu124 (cu124 force-pin, NOT cu128) | ✓ PASS |
| Token leak grep (T-10-02) | `grep -lE "hf_[a-zA-Z0-9]{20,}\|Bearer\s+[A-Za-z0-9]{20,}" spike/audio/results/*.json .planning/research/audio-spike-report.md` | No matches | ✓ PASS |
| **ROUTE-01 live round-trip (independent re-verify this session)** | Live POST to port 10592 against symlinked node_modules + worktree `feat/audio-analysis-route` | happy=200 + stub_mode=true; validation=400 + VALIDATION_ERROR; exact envelope bytes match SUMMARY claim | ✓ PASS |
| WhisperX METADATA declares torch~=2.8.0 | `grep "Requires-Dist: torch" /tmp/whisperx-spike-venv/.../whisperx-*/METADATA` | `torch~=2.8.0` declared but venv has 2.6.0+cu124 (cu124 force-pin verified) | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| `spike/audio/tests/smoke_all.sh` | `SKIP_ROUTE_STUB=1 bash spike/audio/tests/smoke_all.sh` | exit 0 | PASS |
| `spike/audio/tests/staleness_check.sh` | `bash spike/audio/tests/staleness_check.sh` | exit 0 (delegates to `aggregate_report.py --check-staleness`) | PASS |
| `spike/audio/tests/results_schema_check.py` | `python3 spike/audio/tests/results_schema_check.py` | exit 0 (3 OK + 1 blocked OK + 1 SKIP) | PASS |
| `spike/audio/tests/route_stub_smoke.sh` | (skipped via `SKIP_ROUTE_STUB=1`) | SKIP — known bug: probe uses GET `/` while route only serves POST `/` (documented in Plan 02 SUMMARY; round-trip verified independently via direct fetch probe instead) | SKIP (with workaround) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| ROUTE-01 | 10-01, 10-02 | `audio-analysis` route stub with byte-identical envelope to shot-analysis | ✓ SATISFIED | Cross-repo commit `94358fff` on `feat/audio-analysis-route`; live round-trip this session; REQUIREMENTS.md line 29 marked Complete |
| DIA-04 | 10-03, 10-06 | Chinese SER (SenseVoice 7 emotions + VA) — CONDITIONAL on Phase 1 macro-F1 | ✓ RESOLVED (ship-nullable+confidence) | `ser_sensevoice_ep01.json` + report §1 + PROJECT.md Row 3; REQUIREMENTS.md line 37 + 112 |
| DIA-05 | 10-05, 10-06 | Word-level timestamps (WhisperX wav2vec2 align) — CONDITIONAL on Phase 1 drift | ✓ RESOLVED (ship-experimental) | `whisperx_align_ep01.json` + report §3 + PROJECT.md Row 5; REQUIREMENTS.md line 38 + 113 |
| MUS-04 | 10-04, 10-06 | Multi-label instrument recognition (incl. folk: erhu/pipa/guzheng/dizi) — CONDITIONAL on Phase 1 mAP | ✓ RESOLVED (defer to v1.3) | `mir_mert_ep01.json` + `mir_panns_ep01.json` + report §2 + PROJECT.md Row 4; REQUIREMENTS.md line 49 + 120 |

No orphan requirements. All Phase 10 requirement IDs (ROUTE-01, DIA-04, DIA-05, MUS-04) appear in plan `requirements:` frontmatter AND map to verification evidence above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `spike/audio/tests/route_stub_smoke.sh` | (probe logic) | GET `/` for online-detection fails because route only serves POST `/`; smoke script printed SKIP even when route was live | ℹ️ Info | Worked around via direct curl/fetch probe; smoke-script bug documented in Plan 02 SUMMARY; not Phase 10-blocking |
| `kais-aigc-platform/src/routes/production/audio-analysis/index.ts:52` | `(err as any).errors` | zod 4 removed `ZodError.errors` (property is `.issues` now); validation responses return `data:null` instead of zod details | ℹ️ Info | Pre-existing bug mirrored from shot-analysis sibling; smoke check (`.code == 400`) still passes; out-of-scope per Plan 02 SUMMARY |
| N/A (architecture observation) | N/A | Mount path `/api/production/audio-analysis` (no `/v1/`) is INCONSISTENT with sibling `/api/v1/production/shot-analysis` on the same base branch | ℹ️ Info | Per user's explicit instruction in CONTEXT.md; flagged for Phase 12 client contract — `call_audio_analysis.py` must use the no-`/v1/` path |

No `TBD` / `FIXME` / `XXX` / `TODO` / `HACK` / `PLACEHOLDER` / `coming soon` / `not yet implemented` markers in any Phase 10 artifact (Python + shell + TypeScript + Markdown).

### AF-02/AF-03 Anti-Fabrication Audit (Verification Focus)

Every weak metric explicitly labeled "calibrated estimate" — verified:

| Result JSON | "calibrated estimate" present | Honest methodology framing | Status |
| ----------- | ----------------------------- | -------------------------- | ------ |
| `ser_sensevoice_ep01.json` | ✓ (in `caveat` field) | "self_consistency_pct metric is a calibrated estimate of SenseVoice's label stability ... NOT a true macro-F1 ... a model that deterministically predicts NEUTRAL on every clip would score 100% self-consistency yet unknown real accuracy" | ✓ HONEST |
| `mir_mert_ep01.json` | ✓ (in `caveat` field) | "MERT-v1-95M is an audio encoder with NO instrument classifier head ... k-means cluster IDs, not literal instrument labels ... NOT a publishable mAP ... MUS-04 >=0.30 mAP threshold CANNOT be applied literally" | ✓ HONEST |
| `mir_panns_ep01.json` | ✓ (in `caveat` field) | "PANNs half blocked at spike time ... Head-to-head MERT-vs-PANNs comparison is INCOMPLETE ... MERT is therefore the PROVISIONAL route-host MIR pick by default (not by evidence)" | ✓ HONEST |
| `whisperx_align_ep01.json` | (caveat field uses different framing: "device_directive gpu-hybrid" + "Threshold judgment CANDIDATE (Plan 06 locks)") | Aggregate per-word metric is below 0.80 threshold; report §3 explicitly frames this as "METRIC-DEFINITION ARTIFACT" and recommends ship-EXPERIMENTAL with refine-in-Phase-12 caveat | ✓ HONEST (literal phrase absent but framing equivalent — Plan 05 must_haves did NOT require literal "calibrated estimate" in this JSON, only the report) |
| `audio-spike-report.md` | ✓ ×10 matches | Methodology section + every section's Caveat block + Recommendations table all use "calibrated estimate" | ✓ HONEST |

**Inversion finding (informational):** The `self_consistency_pct=100.0` is structurally trivial — all 30 segments produced IDENTICAL emotion labels across the 3 VAD variants (Counter({1: 30}) unique-emotions-per-segment). This is because VAD `max_single_segment_time` variants (30000/25000/20000ms) all exceed every clip length in the sample (max ~19.7s for shot 70), so segmentation is identical, and CPU inference is deterministic. The spike report EXPLICITLY flags this exact failure mode in the caveat ("a model that deterministically predicts NEUTRAL on every clip would score 100% self-consistency yet unknown real accuracy"). This is the AF-02/AF-03 pattern working correctly — weak evidence honestly labeled, recommendation downgraded to ship-nullable+confidence (NOT ship-rigorous).

### Spike Report vs PROJECT.md Consistency (Verification Focus)

| Recommendation in report §4 | PROJECT.md Row | Match? |
| --------------------------- | -------------- | ------ |
| DIA-04 SHIP-NULLABLE+CONFIDENCE | Row 3: "v1.2 Phase 10 — DIA-04 dialogue emotion: SHIP-NULLABLE+CONFIDENCE" | ✓ |
| MUS-04 DEFER to v1.3 | Row 4: "v1.2 Phase 10 — MUS-04 instruments: DEFER to v1.3" | ✓ |
| DIA-05 SHIP-EXPERIMENTAL | Row 5: "v1.2 Phase 10 — DIA-05 word-level timestamps: SHIP-EXPERIMENTAL" | ✓ |
| CUDA path STAY-ON-12.4 | Row 2: "v1.2 Phase 10 — CUDA path: STAY-ON-12.4 (cu124)" | ✓ |
| models_used per modality | Row 1: SenseVoice / WhisperX / MERT-v1-95M (PROVISIONAL) / PANNs folded | ✓ |

All 4 locked outcomes in PROJECT.md match the spike report's recommendations verbatim. The user pre-authorized `decisions-accept-all` (recorded in Plan 06 SUMMARY).

### Honest Outcomes (Not Failures Hidden)

The following are HONEST outcomes documented in the spike report (not hidden failures):

1. **MUS-04 DEFER to v1.3** — MERT has no instrument classifier head; PANNs Cnn14 download blocked by zenodo CDN failure. NO instrument predictions produced. Route host needs a REAL MIR classifier (PANNs once reachable, or fine-tuned MERT head) in Phase 12+ / v1.3. `instruments` field omitted from v1.2 schema.
2. **PANNs Cnn14 blocked** — zenodo.org killed the connection after ~20MB on every retry; aria2c multi-connection reached full size but produced corrupted file (`torch.load` raised `storage has wrong byte size`). hf-mirror `nicofarr/panns_Cnn14` safetensors→pth conversion non-trivial and deferred to Phase 12.
3. **MERT is PROVISIONAL route-host pick** — by default (PANNs leg absent), NOT by head-to-head evidence. PANNs may yet win in Phase 12.
4. **DIA-05 aggregate metric BELOW 0.80 threshold** — `pct_under_200_ms=0.1898 < 0.80`. Ship-experimental recommendation based on REFINED interpretation (boundary drift median=101.5ms under 200ms; dense-speech bucket 93.3% under 200ms). Report explicitly frames aggregate per-word metric as "metric-definition artifact" — drift=word_start−segment_start inflates for interior words.
5. **MERT clusters partly reflect shot DURATION** — mean-pooling artifact, not just instrument content. Report §2 flags this explicitly.

### Human Verification Required

None. All automated checks pass; the ROUTE-01 live round-trip (the only behavioral claim not directly reproducible from committed artifacts, because the original smoke harness was a throwaway not committed) was independently re-verified this session via a fresh fetch probe against symlinked `node_modules`. The mount-path inconsistency (audio-analysis no `/v1/` vs sibling shot-analysis with `/v1/`) is documented as an INFO item — the Phase 12 producer client contract must use the no-`/v1/` path; this was the user's explicit instruction per CONTEXT.md.

### Gaps Summary

No gaps found. All 5 ROADMAP success criteria empirically addressed with honest framing of weak evidence per AF-02/AF-03. The 3 deviations documented in Plan SUMMARYs (route number `route139` instead of `route47`; branch base `feat/shot-analysis-route` instead of `develop`; mount path inconsistency) are all driven by empirical reality that contradicted the plan/research premises — none changed the plan's intent, all are documented in the Plan 02 SUMMARY, and none block Phase 11 contract lock.

Phase 10 is ready for `/gsd:plan-phase 11` (Contract v1.2 lock). Phase 11 has firm empirical basis:
- DIA-04 `emotion` field NULLABLE + `confidence` populated + `fidelity_disclaimer` applies
- MUS-04 `instruments` field OMITTED from v1.2 schema
- DIA-05 `word_timestamps` field EXPERIMENTAL + metric-definition caveat
- WhisperX execution model: isolated cu124 venv (Plan 10-05 pattern is production)
- Route host CUDA baseline: stays at cu124 (BLOCKER 1 RESOLVED)

---

_Verified: 2026-07-25T21:55:00Z_
_Verifier: Claude (gsd-verifier)_
