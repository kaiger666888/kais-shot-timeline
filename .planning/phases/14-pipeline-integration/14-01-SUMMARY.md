---
phase: 14-pipeline-integration
plan: 01
subsystem: pipeline-orchestrator
tags: [pipeline-wiring, step-audio-semantic, banner-renumber, cli-flags, force-extension, mtime-cache, subprocess-shellout]
requires: [phase-12-call-audio-analysis, phase-13-link-speakers, v1.1-phase-6-step-semantic-pattern, v1.1-phase-7-step-reid-pattern]
provides: [step_audio_semantic, audio-semantic-cli-flags, audio-force-cache-clear, step-timeline-audio-mtime-cache]
affects: [run_pipeline.py, scripts/export_asset.py-downstream-behavior]
tech-stack:
  added: []
  patterns:
    - "subprocess.run list-form (no shell=True) — T-14-02 injection mitigation"
    - "explicit-list --force cache clear (NOT glob/rmtree) — T-14-01 mitigation"
    - "TOCTOU-safe mtime cache with video-stamp sidecar (mirror step_reid:269-286)"
    - "non-blocking standalone CLI hint (mirror v1.1 apply_edits.py pattern)"
key-files:
  created: []
  modified:
    - run_pipeline.py
decisions:
  - "Reuse global --offline (added Phase 6) for audio-semantic step rather than adding a step-specific flag — CONTEXT decision 'global', avoids flag explosion"
  - "link_speakers hint printed only when audio_semantic.json AND characters.json both exist — avoids noisy hint when characters not yet confirmed"
  - "Renumber [N/8]→[N/9] via Edit replace_all per literal — atomic + deterministic; grep audit confirmed 0 stragglers"
  - "--audio-timeout default 900s (= route-side execFileSync hard timeout, not 960s like step_semantic/step_reid) — CONTEXT decision 'mirror Phase 6 Pitfall 1' but with exact route-side match"
metrics:
  duration: 8m
  completed: 2026-07-25T23:52Z
  tasks: 1
  files: 1
  lines_added: 188
  lines_removed: 33
---

# Phase 14 Plan 01: Pipeline Integration (step_audio_semantic wiring) Summary

Wired `step_audio_semantic` into `run_pipeline.py` as slot 7/9 (between step_reid[6] and step_timeline[8]), renumbered all 24 `[N/8]` banner instances to `[N/9]`, added 4 new CLI flags with Chinese help, extended `--force` explicit-list with audio_semantic.json + speakers.json + route_cache/audio_analysis/ subdirectory, and extended step_timeline mtime-cache inputs additively.

## What Was Built

### step_audio_semantic function (run_pipeline.py:327-405, ~80 lines)

Mirrors `step_reid:235-313` pattern line-for-line with audio-analysis substitutions:
- Skip short-circuit (`[7/9] --skip-audio-semantic: skipping ...`) when `skip=True`
- TOCTOU-safe mtime cache with `<audio_semantic_json>.video-stamp` sidecar
- List-form `subprocess.run([sys.executable, str(HERE/"analysis"/"call_audio_analysis.py"), ...], check=True)` — NO shell=True (T-14-02 injection mitigation)
- Best-effort video-stamp write after subprocess

### Banner renumber [N/8] → [N/9]

All 24 instances renumbered atomically via Edit replace_all per unique literal:
- `[1/8]`×3 → `[1/9]`×3 (ensure_h264)
- `[2/8]`×3 → `[2/9]`×3 (step_detect)
- `[3/8]`×3 → `[3/9]`×3 (step_separate)
- `[4/8]`×3 → `[4/9]`×3 (step_transcribe)
- `[5/8]`×3 → `[5/9]`×3 (step_semantic)
- `[6/8]`×4 → `[6/9]`×4 (step_reid)
- `[7/8]`×2 → `[8/9]`×2 (step_timeline)
- `[8/8]`×3 → `[9/9]`×3 (step_export)
- 3 NEW `[7/9]` instances in step_audio_semantic (skip + cache + run_step)

Grep audit: `grep -c '\[.*/8\]' run_pipeline.py` == 0 (zero stragglers), `grep -c '\[.*/9\]' run_pipeline.py` == 27.

### 4 new CLI flags (Chinese help per CLAUDE.md)

- `--skip-audio-semantic` (action="store_true")
- `--audio-url` (default `http://127.0.0.1:8000/api/production/audio-analysis`, NO /v1/)
- `--audio-timeout` (type=float, default 900.0)
- `--skip-speaker-link` (action="store_true", controls HITL hint print ONLY — T-14-03 AF-05 mitigation: never subprocess-runs link_speakers)

### --force explicit-list extension (T-14-01 mitigation)

Additive entries to the existing Phase 6/7 tuple (no glob, no parent route_cache rmtree):
- `audio_semantic.json` (step_audio_semantic product)
- `audio_semantic.json + ".video-stamp"` (WR-01 sidecar)
- `speakers.json` (link_speakers product)
- `route_cache/audio_analysis/` subdirectory rmtree (NOT parent `route_cache/` — that would nuke sibling shot_analysis/character_reid caches silently)

### step_timeline mtime-cache extension (Pitfall 9 prevention)

Signature extended with `audio_semantic_json: str = None`, `speakers_json: str = None`. Inputs list conditionally appends both (mirror Phase 8 prompts_json addition at run_pipeline.py:347-353). When audio_semantic/speakers mtime changes → timeline regenerates (Phase 16 HTML gallery will rely on this for re-rendering audio chips).

### --skip-speaker-link hint

When (not skip_speaker_link AND audio_semantic.json exists AND characters.json exists), prints a multi-line `[hint]` block showing the exact `python registry/link_speakers.py ...` CLI command for the operator to run after HITL review. This is the ONLY behavior of --skip-speaker-link; it's a hint suppressor, not a subprocess invocation (T-14-03 mitigation: 全自动映射是 AF-05 violation).

## Verification

All automated grep audits from PLAN.md `<done>` criteria passed:

```
old [N/8] count (must be 0): 0
new [N/9] count (must be ≥27): 27
[7/9] count (must be ≥3): 3
[8/9] count (must be ≥2): 2
[9/9] count (must be ≥3): 3
step_audio_semantic defn: 1
--skip-audio-semantic: 4
--audio-url: 2
--audio-timeout: 2
--skip-speaker-link: 5
link_speakers subprocess invocation: 0  (T-14-03 verified — all 10 occurrences are comments/docstrings/hint prints)
shell=True: 0                            (T-14-02 verified)
parent route_cache rmtree (without explicit list): 0  (T-14-01 verified)
audio_analysis subdirectory rmtree: ≥1   (T-14-01 explicit list verified)
```

`python3 run_pipeline.py --help` shows all 4 new flags with Chinese help text.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. No placeholder/TODO/stub patterns in step_audio_semantic — it's a complete subprocess shell-out to analysis/call_audio_analysis.py (Phase 12 producer, fully implemented).

## Threat Flags

None. T-14-01/02/03 mitigations all verified by grep audit + manual code review. No new network endpoints, auth paths, or schema changes at trust boundaries beyond what Phase 12 already locked.

## Self-Check: PASSED

- run_pipeline.py: FOUND (1 file modified, syntax-valid per ast.parse)
- 813be45 (step_audio_semantic wiring commit): FOUND in git log
- All grep audits pass (zero `[N/8]` stragglers; 27 `[N/9]` instances)
- `--help` output shows all 4 new CLI flags
