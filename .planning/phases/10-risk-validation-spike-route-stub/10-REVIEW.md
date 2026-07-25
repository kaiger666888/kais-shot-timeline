---
phase: 10-risk-validation-spike-route-stub
reviewed: 2026-07-25T00:00:00Z
depth: quick
files_reviewed: 10
files_reviewed_list:
  - spike/audio/common.py
  - spike/audio/run_ser_sensevoice.py
  - spike/audio/run_mir_head_to_head.py
  - spike/audio/run_whisperx_align.py
  - spike/audio/aggregate_report.py
  - spike/audio/tests/results_schema_check.py
  - spike/audio/tests/route_stub_smoke.sh
  - spike/audio/tests/smoke_all.sh
  - spike/audio/tests/staleness_check.sh
  - cross-repo: src/routes/production/audio-analysis/index.ts (feat/audio-analysis-route)
  - cross-repo: src/routes/production/audio-analysis/_shared/config.ts (feat/audio-analysis-route)
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: findings
---

# Phase 10: Code Review Report (quick)

**Reviewed:** 2026-07-25
**Depth:** quick (pattern-matching + threat-model verification only)
**Files Reviewed:** 11 (8 spike scripts/tests + 2 cross-repo route stub files + 1 router mount)
**Status:** findings

## Summary

Phase 10 spike scripts and the cross-repo ROUTE-01 stub were reviewed at quick depth against the documented threat model (T-10-01 through T-10-05). Threat-model mitigations are largely sound:

- **T-10-01 (token redaction):** `_safe_error` (`common.py:80-99`) is wired into every exception path in all 3 spike scripts and into `write_result` (`common.py:264`) as defense-in-depth before disk write. Regex covers `hf_<20+ alnum>`, `token=<val>`, `Bearer <val>`, URL userinfo. Pattern-matching grep confirms no exception path bypasses it (24 call sites audited).
- **T-10-03 (canonical model IDs):** All spikes hardcode canonical IDs (`iic/SenseVoiceSmall`, `m-a-p/MERT-v1-95M`, `panns_inference.AudioTagging(checkpoint_path=None)`). No local checkpoint paths.
- **T-10-04 (route stub boundary sealed):** Verified via grep — `src/routes/production/audio-analysis/index.ts` contains zero `fs.*` / `readFile` / `path.join` / `path.resolve` calls on body fields. Only `bodySchema.parse(req.body)` touches user input. Phase 12+ fs guard duty is documented inline.
- **No command injection:** Every `subprocess.run` / `check_output` in the spikes uses list-args (no `shell=True`). ffmpeg, git, python3 probes all take hardcoded argument lists; user input never reaches the argv.
- **No path traversal:** Phase 10 stub does not read any body-supplied paths. Spike scripts only read hardcoded fixture paths.

Six issues surfaced — three warnings (one canary-defeating correctness bug in the WhisperX torch probe; hardcoded metric values in the aggregate report prose that violate AF-02/AF-03 if re-run; schema gate that silently forbids smoke-mode JSONs) and three info items. No blockers; the code is safe to ship as a Phase 10 spike artifact.

## Warnings

### WR-01: `probe_system_torch` canary defeated by venv `python3` shadowing

**File:** `spike/audio/run_whisperx_align.py:144-153`
**Issue:** The script's own docstring (`run_whisperx_align.py:6-13`) mandates running under the isolated venv `/tmp/whisperx-spike-venv/bin/python`. When invoked from that venv (i.e., the only correct way to run this spike), the bare `python3` passed to `subprocess.check_output(["python3", "-c", ...])` resolves to the **venv's** `python3` (because venvs shadow `PATH`), not `/usr/bin/python3`. The probe therefore reports the **venv** torch version under the `system_torch` key, making the Pitfall 1 canary (`system_torch == venv_torch`) trivially true regardless of whether the venv install poisoned the system torch — the exact failure mode the canary is designed to catch.

The aggregate report then asserts `system_torch='2.6.0+cu124' matches the venv force-pin AND the project baseline` (`aggregate_report.py:506-507`) — but this is two measurements of the same venv, not an independent verification.

**Fix:**
```python
# Use absolute path so venv PATH shadowing cannot interfere
out = subprocess.check_output(
    ["/usr/bin/python3", "-c", "import torch; print(torch.__version__)"],
    stderr=subprocess.DEVNULL,
    timeout=15,
).decode().strip()
```
Alternatively, fall back to `/bin/python3` if `/usr/bin/python3` does not exist (some distros).

### WR-02: Aggregate report hardcodes metric values in narrative conclusions (AF-02/AF-03 risk)

**File:** `spike/audio/aggregate_report.py:345, 459-465, 486-493, 537-540`
**Issue:** The report template embeds literal metric numbers inside prose conclusions:
- Line 345: ``self_consistency_pct=100.0``
- Line 486: ``pct_under_200_ms=0.1898 ... is BELOW the 0.80 threshold``
- Lines 464-465: `median_boundary_drift_ms = {drift.get(...)} — well under 200ms ✓` (annotation hardcoded regardless of actual value)
- Line 493: `dense-speech bucket pct_under_200_ms = {per_bucket.get(...)} — ≥ 0.80 ✓` (annotation hardcoded regardless of actual value)
- Lines 537, 539: Recommendations table hardcodes `100.0`, `101.5ms`, `0.933`, `0.189`

If a re-run (different fixture, different model version, post-Pitfall-1-fix rerun) produces different metrics, the JSON `drift_stats` block would update but the surrounding prose conclusions ("BELOW 0.80 threshold ✓", "well under 200ms ✓") would silently contradict the data. This is exactly the failure mode AF-02/AF-03 forbids (numbers in the report not matching source data). Parametrized fields (`{drift.get(...)}`) are correct; the hardcoded annotations attached to them are the defect.

**Fix:** Replace every hardcoded number + hardcoded truth annotation with parametrized assertions over the loaded JSON. Example for line 486:
```python
threshold = 0.80
pct_val = drift.get('pct_under_200_ms')
verdict = "BELOW" if (pct_val is not None and pct_val < threshold) else "AT/ABOVE"
lines.append(
    f"The aggregate per-word `pct_under_200_ms={pct_val}` is **{verdict}** "
    f"the {threshold} threshold ..."
)
```
Apply the same pattern to `median_boundary_drift_ms`, dense-bucket `pct_under_200_ms`, SER `self_consistency_pct`, and the recommendations-table evidence column.

### WR-03: `whisperx_align_*` schema requires `sample_size >= 30`, silently breaks `--smoke-only` JSONs

**File:** `spike/audio/tests/results_schema_check.py:137`
**Issue:** `_check_whisperx_align` rejects any JSON with `sample_size < 30`. But `run_whisperx_align.py:482-484` writes a JSON for *any* `--smoke-only N` value with `sample_size = N` (e.g., `--smoke-only 1` writes `sample_size: 1`). If a developer runs a smoke pass and then runs the schema check (or commits the smoke JSON), the schema gate fails:
```
[smoke:schema] FAIL whisperx_align_ep01.json: sample_size must be >=30
```
The SER (`results_schema_check.py:64`) and MIR (`results_schema_check.py:101`) checkers correctly allow `sample_size >= 1`. The WhisperX checker's stricter threshold is undocumented in the spike README and inconsistent with the SER/MIR pattern.

**Fix (pick one):**
- **(a) Match the SER/MIR pattern** (preferred for a throwaway spike): relax `_check_whisperx_align` to `>= 1`, like SER/MIR.
- **(b) Write smoke JSONs to a different filename** so they don't collide with the canonical `whisperx_align_ep01.json` name: e.g., `whisperx_align_ep01_smoke.json` (which the existing `fname.startswith("sample_")` skip pattern doesn't cover, but a `_smoke` suffix convention would).
- **(c) Document explicitly** in `spike/audio/README.md` that smoke-mode JSONs must be deleted before commit, and have `run_whisperx_align.py` refuse to call `write_result` when `is_smoke=True`.

## Info

### IN-01: `_safe_error` HF_TOKEN regex excludes `-`/`_`/`.` characters

**File:** `spike/audio/common.py:74`
**Issue:** `_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{20,}")` matches classic HuggingFace tokens (35-char alphanumeric after `hf_`). Newer token formats (e.g., fine-grained tokens with hyphens or underscores) would not be matched. Low real-world risk: classic format tokens are the common case, and `_TOKEN_KV_RE` / `_BEARER_RE` cover the other common leakage patterns.
**Fix (optional):** Broaden the char class to `r"hf_[A-Za-z0-9_\-]{20,}"` if you want belt-and-suspenders coverage.

### IN-02: `torch.stack(outputs.hidden_states).squeeze()` (no dim) over-collapses if T==1

**File:** `spike/audio/run_mir_head_to_head.py:227`
**Issue:** The squeeze()-without-dim fix (correctly replacing the buggy `.squeeze(0)` for the common case) has its own corner: if the MERT forward ever produced `T==1` frames (sub-millisecond audio at 24 kHz), `.squeeze()` would also remove the time dimension, causing `mean(dim=1)` to reduce the wrong axis. In practice, audio segments are clamped to `max(0.1, end-start)` seconds (`load_mix_slice:174`), so T is always >> 1. Not impactful, but worth a one-line docstring note.
**Fix (optional):** Use `torch.stack(...).squeeze(1)` to remove only the known size-1 batch dim (dim 1 of `(L+1, 1, T, 768)`), or add a docstring note that T>1 is a precondition.

### IN-03: Route stub uses `any` types + unsafe `err as Error` cast

**File:** `src/routes/production/audio-analysis/index.ts:42, 47-49` (cross-repo: `kais-aigc-platform` branch `feat/audio-analysis-route`)
**Issue:** The handler signature `async (req: any, res: any)` and the 500 branch `error("AUDIO_ANALYSIS_FAILED", (err as Error).message)` cast unknown to `Error` without checking. If a non-Error value is thrown (e.g., a string or a Zod-specific subclass that's not `ZodError`), `.message` is undefined and could surface as `undefined` in the response body — not a leak, but a malformed envelope. Acceptable for a Phase 10 stub; flagging for Phase 12+ hardening.
**Fix (for Phase 12+):** Type the handler with `express.Request` / `express.Response`, and in the 500 branch guard against non-Error throws: `const msg = err instanceof Error ? err.message : String(err)`.

---

_Reviewed: 2026-07-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
_Threat model verified: T-10-01 ✓ (24/24 exception paths redacted) · T-10-03 ✓ (canonical IDs only) · T-10-04 ✓ (route stub sealed, 0 fs ops on body) · no command injection (9/9 subprocess calls use list args)_
