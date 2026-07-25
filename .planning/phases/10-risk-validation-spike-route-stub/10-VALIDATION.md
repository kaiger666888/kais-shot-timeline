---
phase: 10
slug: risk-validation-spike-route-stub
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-25
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 10 is a research spike + route stub — validation = spike reproducibility checks + ROUTE-01 stub envelope smoke tests. The deliverable is the spike report + committed results JSON + ROUTE-01 stub, NOT a production test suite (throwaway spike code per CONTEXT.md).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | **bash smoke-check scripts** (primary — matches throwaway spike nature) + optional `pytest` for 2 deterministic helpers |
| **Config file** | none — Wave 0 creates `spike/audio/tests/` |
| **Quick run command** | `bash spike/audio/tests/smoke_all.sh` |
| **Full suite command** | `python3 spike/audio/aggregate_report.py --check-staleness && bash spike/audio/tests/smoke_all.sh` |
| **Estimated runtime** | ~5 seconds (smoke checks; ML inference is the spike itself, not the test) |

**Context:** CLAUDE.md notes zero existing test infrastructure. Research recommends bash smoke-checks (option b) over pytest for throwaway spike code. pytest is optional for pinning `common.py:parse_sensevoice_tags` + `stratified_sample` (deterministic pure functions).

---

## Sampling Rate

- **After every task commit:** Run `bash spike/audio/tests/smoke_all.sh`
- **After every plan wave:** Run `python3 spike/audio/aggregate_report.py --check-staleness && bash spike/audio/tests/smoke_all.sh`
- **Before `/gsd:verify-work`:** All 4 results JSON present + report has 4 sections + report has methodology caveats + PROJECT.md Key Decisions has 4 locked outcomes
- **Max feedback latency:** 5 seconds (smoke checks)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 0 | ROUTE-01 | T-10-04 | Stub does NOT read `video`/`shots` files in Phase 10 (path traversal deferred to Phase 12 sandboxing) | smoke | `bash spike/audio/tests/route_stub_smoke.sh` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 0 | ROUTE-01 | — | Stub returns `{"code":200,"data":{"shots":[],"count":0,"stub_mode":true},...}` ML-unloaded | smoke (curl) | `curl -sS -X POST …/audio-analysis -d '{"video":"/x","shots":"/y"}' \| jq '.code,.data.stub_mode'` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 0 | ROUTE-01 | — | Stub returns 400 on missing required field | smoke (curl) | `curl … -d '{}' \| jq '.code'` (expect 400) | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | DIA-04 | T-10-01 | SER results JSON non-empty `per_sample[]` of 30 | smoke (python) | `python3 -c "import json;d=json.load(open('spike/audio/results/ser_sensevoice_ep01.json'));assert len(d['per_sample'])==30"` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 1 | DIA-04 | — | Report cites "calibrated estimate" methodology caveat (AF-02/AF-03) | grep | `grep -c "calibrated estimate" .planning/research/audio-spike-report.md` (≥1) | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 1 | DIA-05 | T-10-05 | WhisperX drift stat based on ≥30 segments | smoke (python) | `python3 -c "import json;d=json.load(open('spike/audio/results/whisperx_align_ep01.json'));assert d['sample_size']>=30"` | ❌ W0 | ⬜ pending |
| 10-03-02 | 03 | 1 | DIA-05 | T-10-05 | Isolated venv did NOT poison system torch (`+cu124` intact) | smoke (python) | `python3 -c "import torch;assert '+cu124' in torch.__version__"` | ❌ W0 | ⬜ pending |
| 10-04-01 | 04 | 1 | MUS-04 | — | MERT + PANNs both produce JSON on SAME 30 segments (head-to-head integrity, Pitfall 9) | smoke (python) | compare `shot_id` lists in `mir_mert_ep01.json` vs `mir_panns_ep01.json` | ❌ W0 | ⬜ pending |
| 10-04-02 | 04 | 1 | MUS-04 | — | Head-to-head mAP comparison present in report | grep | `grep -c "MERT.*PANNs\|PANNs.*MERT" .planning/research/audio-spike-report.md` (≥1) | ❌ W0 | ⬜ pending |
| 10-05-01 | 05 | 2 | (gate) | T-10-02 | No `hf_` token patterns leaked into committed results/report | grep | `grep -rlE "hf_[a-zA-Z0-9]{20,}" spike/audio/results/ .planning/research/audio-spike-report.md` (expect none) | ❌ W0 | ⬜ pending |
| 10-06-01 | 06 | 2 | DIA-04/05/MUS-04 | — | PROJECT.md Key Decisions logs 4 locked outcomes | grep | `grep -cE "CUDA 12\.[48]|DIA-04|MUS-04|DIA-05" .planning/PROJECT.md` (≥4) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `spike/audio/tests/route_stub_smoke.sh` — 3 curl-based smoke tests for ROUTE-01 (envelope, 400-on-missing, stub_mode env flip)
- [ ] `spike/audio/tests/results_schema_check.py` — JSON shape validation for each model's results blob
- [ ] `spike/audio/tests/staleness_check.sh` — wrapper around `aggregate_report.py --check-staleness`
- [ ] `spike/audio/tests/smoke_all.sh` — top-level runner (wave merge gate)
- [ ] Optional: `pytest` + `spike/audio/tests/test_common.py` pinning `parse_sensevoice_tags` + `stratified_sample` (planner's discretion)

*Project has zero existing test infrastructure per CLAUDE.md — Wave 0 must create the smoke-check harness.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SER macro-F1 methodology choice (A3 open question) | DIA-04 | Requires human judgment on evidence strength (self-consistency vs 30-segment developer annotation vs benchmark-only) | At `checkpoint:human-confirm` task: user picks methodology; report records the choice |
| DIA-04/MUS-04/DIA-05 ship/defer decision per thresholds | DIA-04/MUS-04/DIA-05 | Threshold judgment call (≥50%/≥0.30/<200ms) from spike numbers — locked into PROJECT.md by developer | Review spike report → decide per threshold → record in PROJECT.md Key Decisions |
| SenseVoice emotion labels qualitatively sensible on ep01 | DIA-04 | No ground truth; qualitative review is the primary proxy | Developer eyeballs the 30 `per_sample` emotion labels against the dialogue |
| WhisperX word-align drift visually plausible on sample segments | DIA-05 | Drift stat needs spot-check that align timestamps track audio | Developer spot-checks 3-5 aligned segments in the results JSON |

---

## Spike Reproducibility Invariants

- **Deterministic model pins**: all 5 models loaded from canonical HF IDs (research §Sources) — never `./local-checkpoint`.
- **Fixed segment sample**: `common.py:stratified_sample(seed=10, n=30)` — same 30 segments across SER/MERT/PANNs/WhisperX runs (head-to-head integrity, Pitfall 9).
- **Committed results JSON**: `spike/audio/results/{ser,mir_mert,mir_panns,whisperx_align}_ep01.json` checked in so the report is regenerable + auditable.
- **Staleness gate**: `aggregate_report.py --check-staleness` fails loud if any results JSON is older than the report (Pitfall 10).
