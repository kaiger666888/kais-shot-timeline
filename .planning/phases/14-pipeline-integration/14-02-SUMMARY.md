---
phase: 14-pipeline-integration
plan: 02
subsystem: smoke-harness
tags: [smoke-harness, regression-guard, route-up, route-down, cache-hit-offline, conditional-field-defer, stub-only, e2e-proof, asset-schema-1-2]
requires: [phase-14-01-step-audio-semantic-wired, phase-12-call-audio-analysis-client, phase-12-stub-server, phase-12-stub-fixtures, phase-11-v1.2-schemas, phase-11-v1.2-fixtures]
provides: [verify_phase_audio_smoke-harness, regression-guard-against-CR-01-style-silent-degrade, e2e-schema-version-1.2-proof]
affects: []
tech-stack:
  added: []
  patterns:
    - "tempfile.mkdtemp + try/finally + shutil.rmtree per scenario (T-14-04 cleanup mitigation)"
    - "subprocess.Popen stub server with _start_stub poll + _stop_stub terminate/kill"
    - "filecmp.cmp(shallow=False) for byte-identical proof (cache-hit-offline scenario)"
    - "case-insensitive grep on output JSON (MUS-04 absent proof, Phase 11 schema $comment lock)"
    - "ffmpeg lavfi color+anullsrc for tiny 1s mp4 synthesis (Rule 1 fix for ffprobe requirement)"
key-files:
  created:
    - scripts/verify_phase_audio_smoke.py
  modified: []
decisions:
  - "Ported Phase 12 tests/run_audio_analysis_smoke.sh (bash) to Python for cross-platform determinism + integrated e2e asset.json proof (single-file harness vs 4 separate artifacts)"
  - "Used BASE_PORT=10593-10595 for Phase 14 smoke (distinct from Phase 12's 10591 to avoid TIME_WAIT collision on concurrent runs)"
  - "Scenario 4 nullable variant fixture written inline to temp work_dir (NOT to tests/fixtures/) — keeps fixture set stable + tests normalize on synthetic input"
  - "Scenario 6 e2e synthesizes 1s mp4 via ffmpeg lavfi at runtime instead of bundling a fixture video — avoids binary bloat in repo + tests against real ffprobe"
metrics:
  duration: 6m
  completed: 2026-07-25T23:54Z
  tasks: 1
  files: 1
  lines_added: 783
  lines_removed: 0
---

# Phase 14 Plan 02: 5-scenario smoke harness + e2e schema_version=1.2 proof Summary

Delivered `scripts/verify_phase_audio_smoke.py` — a single-file Python harness covering all 5 PIPE-03 scenarios + 1 e2e SC#5 sub-case, mirroring `scripts/verify_phase6_smoke.py:54-505` structure. All 6 scenarios GREEN on first complete run (after Rule 1 fix for ffprobe requirement).

## What Was Built

### 5 PIPE-03 scenarios + 1 e2e (SC#5)

| # | Scenario | What it proves | Key assertion |
|---|----------|----------------|---------------|
| 1 | route_up | PIPE-01 happy path | audio_semantic.json schema-valid + cache written + 0 [audio] warnings |
| 2 | route_down | CONTRACT-05 byte-identical-absent | audio_semantic.json NOT written + [audio] warning mentions preflight/ConnectError |
| 3 | cache_hit_offline | PIPE-02 cache proof | --offline byte-identical to baseline (filecmp.cmp) + 'cache hit' logged |
| 4 | conditional_field_defer | DIA-04 nullable + MUS-04 absent | schema-valid with emotion=null + 0 'instrument' case-insensitive matches |
| 5 | stub_only | Phase 10 ROUTE-01 stub envelope | audio_semantic.json NOT written + [audio] warning mentions stub_mode |
| 6 | e2e_asset_schema | SC#5 schema_version=1.2 + conditional emission | WITH: data.audio_semantic+speakers emitted; WITHOUT: both OMITTED, schema_version unchanged |

### Reused Phase 12 infrastructure (zero duplication)

- `tests/audio_analysis_stub_server.py` — background stub server returning fixture bytes on POST
- `tests/fixtures/audio_analysis_stub_response_nonempty.json` — nonempty envelope for scenario 1+3
- `tests/fixtures/audio_analysis_stub_response_empty.json` — empty stub envelope (byte-identical to Phase 10 stub) for scenario 5
- `spec/fixtures/v1.2/*` — canonical v1.2 fixtures for e2e
- `analysis/call_audio_analysis.py:video_content_hash` — for scenario 3 cache key construction (no reimplementation)

### Cleanup guarantee (T-14-04 mitigation)

EVERY scenario uses `tempfile.mkdtemp(prefix="phase14-smoke-")` captured in try, with `shutil.rmtree(ignore_errors=True)` in finally. Stub server subprocesses (`subprocess.Popen`) get `_stop_stub(proc)` in finally: `terminate() → wait(2s) → kill() → wait(1s)` defense-in-depth. Verified by `ps -ef | grep audio_analysis_stub` returning empty after harness exits.

## Verification

```
[phase14-smoke] PASS route_up: audio_semantic.json schema-valid, cache written, 0 [audio] warnings
[phase14-smoke] PASS route_down: audio_semantic absent (CONTRACT-05), 4 [audio] warning(s)
[phase14-smoke] PASS cache_hit_offline: byte-identical baseline + cache hit logged
[phase14-smoke] PASS conditional_field_defer: schema-valid with nullable emotion, 0 'instrument' matches
[phase14-smoke] PASS stub_only: audio_semantic absent + [audio] warning mentions stub_mode
[phase14-smoke] PASS e2e_asset_schema: WITH + WITHOUT sub-cases both green
[phase14-smoke] OK: 6/6 scenarios green
```

Exit 0. No lingering stub processes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Bug] TINY_VIDEO has no audio stream → ffprobe fails on e2e**
- **Found during:** Task 1 first run (e2e_asset_schema scenario FAILED)
- **Issue:** Original plan used `shutil.copy2(TINY_VIDEO, video_path)` where TINY_VIDEO is the harness `.py` file. `scripts/export_asset.py:444-458` uses ffprobe to assert video contains audio stream — `.py` file has no audio → ffprobe rc=1 → export_asset exits 1.
- **Fix:** Introduced `_make_tiny_mp4(path)` helper that uses `ffmpeg -f lavfi -i color=size=320x240:rate=30 -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t 1 -c:v libx264 -c:a -aac -shortest` to synthesize a 1-second black-silent mp4 at runtime. Uses ffmpeg 6.1.1 (project-required, already on PATH). No fixture bloat, no external dep beyond project baseline.
- **Files modified:** scripts/verify_phase_audio_smoke.py (added _make_tiny_mp4 helper + switched e2e sub-cases from copy to synthesize)
- **Commit:** ddd9837

No other deviations. Plan executed as written.

## Known Stubs

None. The smoke harness exercises real subprocess.run calls against real (Phase 12) stub servers and real (Phase 11) schemas. No mocked behavior, no TODO markers, no placeholder data.

## Threat Flags

None. The harness itself is a test artifact — no new network endpoints, auth paths, or schema changes at trust boundaries. T-14-04 (cleanup mitigation) verified by manual process inspection post-run.

## Self-Check: PASSED

- scripts/verify_phase_audio_smoke.py: FOUND (1 file created, 783 lines, syntax-valid, executable)
- ddd9837 (smoke harness commit): FOUND in git log
- All 6 scenarios PASS on `python3 scripts/verify_phase_audio_smoke.py`
- No lingering `audio_analysis_stub_server` processes (T-14-04 cleanup verified)
