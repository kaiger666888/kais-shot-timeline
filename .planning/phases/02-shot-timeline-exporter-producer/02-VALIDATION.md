---
phase: 2
slug: shot-timeline-exporter-producer
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-20
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` §Validation Architecture. Repo has NO existing test framework — Phase 2 uses **standalone verification scripts** (sys.exit 0/1), matching project convention. No pytest is introduced (scope creep).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (project convention — standalone scripts with `sys.exit(0/1)`) |
| **Config file** | none — Wave 0 will NOT add pytest (scope creep) |
| **Quick run command** | `python3 spec/validate.py` |
| **Full suite command** | `python3 spec/validate.py --strict-smoke && python3 scripts/check_range.py` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 spec/validate.py` (~1s, no network)
- **After every plan wave:** Run `python3 spec/validate.py --strict-smoke && python3 scripts/check_range.py`
- **Before `/gsd:verify-work`:** Full suite must be green — minimal 6/6 `[valid]`, smoke 5/5 `[smoke-valid]`, check_range exits 0, manual git-diff shows zero algorithm changes
- **Max feedback latency:** 3 seconds

---

## Per-Task Verification Map

> Task IDs populate when PLAN.md files are written. Mapped from research §Phase Requirements → Test Map.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | EXPORT-01 | — | N/A | smoke (inline schema) | inline `Draft202012Validator(asset.schema.json).iter_errors(asset.json)` inside export_asset.py | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | EXPORT-01 | — | N/A | unit (exit-code) | `export_asset.py` with missing prompts.json → non-zero + Chinese error containing `prompts.json` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | EXPORT-01 | V5/V12 | path-traversal rejected by schema patterns | integration | `python3 spec/validate.py --strict-smoke` (5 data shapes strictly valid) | ✅ EXISTS | ⬜ pending |
| TBD | 01 | 1 | EXPORT-02 | — | algorithms untouched | manual / git-diff | `git diff main -- detectors/ audio/ html/gen_timeline_html.py` (expect no changes) | ❌ W0 (manual) | ⬜ pending |
| TBD | 01 | 1 | EXPORT-02 | — | manifest self-describing | smoke | covered by EXPORT-01 schema check (asset.schema.json requires schema_version + generator) | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | EXPORT-03 | DoS (FD exhaust) | `_Partial.close()` prevents FD leak | smoke (HTTP) | `python3 scripts/check_range.py` (206 + Content-Range + Accept-Ranges) | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | EXPORT-03 | — | symlinks resolve | unit (path) | export_asset.py post-write asserts `video.mp4`, `stems/{vocals,drums,other}.wav` exist | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | EXPORT-03 | DoS | no AttributeError on Range | manual (stderr) | 50× `curl -H 'Range: bytes=0-1023'` → no AttributeError in serve.py stderr; FD count stable | ❌ W0 (manual) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `scripts/export_asset.py` — produces asset.json + inline jsonschema validation + symlinks (covers EXPORT-01, EXPORT-02)
- [ ] `scripts/check_range.py` — Range-206 self-check (covers EXPORT-03)
- [ ] No new framework install needed (uses standalone-script convention)

*Existing infrastructure (spec/validate.py from Phase 1) covers the data-shape smoke. No test framework gap — project explicitly has none and Phase 2 must not introduce one.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Detection/transcription/separation algorithms untouched | EXPORT-02 | Additive-only is a diff-inspection invariant, not a runtime behavior | `git diff main -- detectors/ audio/ html/gen_timeline_html.py` — expect empty diff |
| serve.py no longer leaks FDs under sustained Range load | EXPORT-03 | Requires observing stderr + /proc/<pid>/fd across 50 requests | `python3 scripts/serve.py output/<dir> 8765 &`; 50× `curl -H 'Range: bytes=0-1023' http://localhost:8765/video.mp4`; confirm no `AttributeError` in stderr, FD count stable |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (Wave 0 tasks ARE the plan tasks — self-bootstrapping, no external test framework)
- [x] No watch-mode flags
- [x] Feedback latency < 3s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-20 (post plan-checker; Dimension 8 substantive checks 8a–8d all PASS; `wave_0_complete` flips to true after Plan 02-01 lands)
