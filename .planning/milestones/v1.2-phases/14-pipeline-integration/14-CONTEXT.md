# Phase 14: Pipeline Integration - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — pipeline-wiring phase mirroring v1.1 step_reid/step_semantic patterns; shape forced by run_pipeline.py structure + Phase 12 client + Phase 13 link_speakers. All recommendations accepted per user momentum preference.

<domain>
## Phase Boundary

Wire `step_audio_semantic` into `run_pipeline.py` as slot 7 of 9 (between `step_reid[6]` and `step_timeline[8]`): invokes `analysis/call_audio_analysis.py` (Phase 12) per-video + `registry/link_speakers.py` (Phase 13) as a non-blocking standalone step. Includes all CLI flags, `--force` cache extension (explicit list, NOT glob), mtime-cache extension for step_timeline, and a 5-scenario smoke regression harness.

This phase produces the pipeline wiring ONLY — NO new ML, NO new HTML. It connects Phase 12 (client) + Phase 13 (link_speakers) into the orchestrator.

</domain>

<decisions>
## Implementation Decisions

### step_audio_semantic (mirror step_reid pattern — slot 7/9)

- New `step_audio_semantic(video, work_dir, shots_json, ...)` in run_pipeline.py, invoked AFTER `step_reid`, BEFORE `step_timeline`. Shell-out to `analysis/call_audio_analysis.py` via subprocess (mirror how step_reid/step_semantic shell out).
- Non-blocking standalone `link_speakers.py`: step_audio_semantic produces `audio_semantic.json`; `link_speakers.py` runs as a non-blocking standalone CLI between step_audio_semantic and step_timeline (mirror how apply_edits.py is a standalone CLI after step_reid — NOT auto-invoked; operator runs it after HITL review).
- Renumber ALL `[N/8]` banner instances → `[N/9]` (17 instances per SC#1 — grep audit, zero stragglers; Pitfall: phase-counter drift).

### CLI flags (mirror existing argparse conventions)

- `--skip-audio-semantic` (skip the step entirely), `--audio-url` (route host, default the ROUTE-01 stub/production host), `--audio-timeout` (per-shot, default 900s), `--skip-speaker-link` (skip the link_speakers invocation), `--offline` (forward to call_audio_analysis.py graceful-degrade). Chinese help= per CLAUDE.md.

### --force cache extension (explicit list, NOT glob — project convention)

- `--force` now also clears: `audio_semantic.json` + `speakers.json` + `route_cache/audio_analysis/` (the per-shot cache from Phase 12). Explicit list (mirror how step_reid's --force clears registry.draft.json + route_cache/reid/ explicitly — NEVER a glob/rmtree).

### mtime-cache extension (Pitfall 9 — mirror Phase 8 prompts_json addition)

- `step_timeline`'s mtime-cache inputs list extended to include `audio_semantic.json` + `speakers.json` → step_timeline regenerates when either changes (mirror how Phase 8 added prompts.json to step_timeline's inputs list).

### 5-scenario smoke (mirror Phase 6/7 3-scenario + Phase 8 6-scenario harness)

- `scripts/verify_phase_audio_smoke.py`: route-up (audio_semantic written), route-down (graceful-degrade, byte-identical-absent), cache-hit-offline (--offline hits cache), conditional-field-defer (nullable+confidence fields present, instruments absent), stub-only (stub_mode:true envelope). All 5 GREEN.

### End-to-end (SC#5)

- `python run_pipeline.py --video <ep>` produces `asset.json` with `schema_version: "1.2"` + conditionally emits `data.audio_semantic` + `data.speakers` (via Phase 11 export_asset.py conditional emission).

### Claude's Discretion

- Exact step_audio_semantic signature (mirror step_reid's).
- Whether link_speakers is invoked inside step_audio_semantic or as a separate sequential call in main() (mirror how step_reid → apply_edits is structured).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`run_pipeline.py`** — the orchestrator (649 lines). step_detect/separate/transcribe/semantic/reid/timeline/export. step_audio_semantic slots between step_reid (line 235) and step_timeline (line 316).
- **`step_reid` + `step_semantic`** — THE patterns: subprocess shell-out, --force explicit-list cache clear, mtime-cache, non-blocking standalone apply CLI.
- **`analysis/call_audio_analysis.py`** (Phase 12) — the client step_audio_semantic invokes.
- **`registry/link_speakers.py`** (Phase 13) — the non-blocking HITL apply CLI.
- **Phase 11 `export_asset.py`** — already conditionally emits data.audio_semantic/data.speakers (Phase 11 work); step_export wires it.

### Established Patterns
- **Subprocess shell-out to sibling scripts** (sys.executable + script path).
- **--force explicit-list cache clear** (never glob).
- **mtime-cache with inputs list** (TOCTOU-safe, mirror step_semantic).
- **[N/total] banner per step** (the phase-counter that must renumber 8→9).

### Integration Points
- Phase 15 (Layered Reproduction Prompts) extends step_audio_semantic to populate reproduction.{tts,music_gen,foley}.
- Phase 16 HTML gallery reads audio_semantic.json + speakers.json.

</code_context>

<specifics>
## Specific Ideas

- The `[N/8] → [N/9]` renumber is the most error-prone part (17 instances; easy to miss one). Grep audit `grep -c '\[.*/8\]' run_pipeline.py` must return 0 after.
- `--force` MUST be explicit-list (audio_semantic.json + speakers.json + route_cache/audio_analysis/), NEVER a glob/rmtree — project convention + safety.
- link_speakers is NON-blocking (operator runs it after HITL review, like apply_edits) — do NOT auto-invoke it in the pipeline; just document/optional --skip-speaker-link flag controls whether the hint is shown.

</specifics>

<deferred>
## Deferred Ideas

- **Live route ML** — Phase 14 wires the stub/client; live ML is post-merge smoke.
- **Reproduction prompts population** — Phase 15.

</deferred>
