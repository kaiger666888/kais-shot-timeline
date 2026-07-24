# Phase 6: Cinematography Auto-Fill (`step_semantic`) - Context

**Gathered:** 2026-07-24
**Status:** Ready for planning

<domain>
## Phase Boundary

shot-timeline gains its **first-ever network dependency**: a new `step_semantic` pipeline stage that calls the kais-aigc-platform `POST /api/v1/production/shot-analysis` route (via a thin httpx client) and merges the cinematography/subject analysis into `prompts.json` (camera/action/lighting/style facets). Mandatory graceful-degrade: when the route is unreachable, `prompts.json` still writes schema-valid empty facet strings, the asset still exports, and `generator.warnings` is populated. Per-shot route output is cached with a content-hash key; `--offline` / `--skip-semantic` flags behave correctly.

**In scope:** `analysis/call_shot_analysis.py` (httpx client + field mapping); `run_pipeline.py` `step_semantic` (slots between `step_transcribe` and `step_timeline`, counter `[N/7]`); per-shot cache (`route_cache/shot_analysis/shot_XXX.json`); preflight health check + `generator.warnings`; `--analysis-url` / `--analysis-timeout` / `--offline` / `--skip-semantic` flags.
**Out of scope:** the route itself (lives in kais-aigc-platform `feat/shot-analysis-route`, **unmerged**); `prompt_text` recomposition with registry refs (Phase 8); re-id (Phase 7); changing detection/transcription/separation algorithms.

</domain>

<decisions>
## Implementation Decisions

### Route→prompts field mapping (CINEMA-01)
Real route output (`/mnt/agents/output/gpu1/shot_analysis/shot_003.json`) has `geometry` + `semantic`. Mapping to prompts facets:
- **`camera`** ← COMPOSE from `semantic.shot_scale` + `semantic.camera_primitive` + `semantic.camera_speed` + `geometry.primitive` (e.g. `"中景, follow, fast pan_right"`). All four carry camera-language signal.
- **`action`** ← `semantic.subject_motion` (e.g. `"飞虫持刀向前飞行"`).
- **`lighting`** ← `semantic.lighting` (e.g. `"雾气弥漫"`).
- **`style`** ← `semantic.lens_feel` (e.g. `"normal"`).
- **`subject`** ← empty string `""` (route has no subject/identity source — don't fabricate; Phase 7 re-id + Phase 8 refs handle identity).
- **`scene`** ← empty string `""` (route has no scene source; future Qwen-VL extension per STATE.md; never fabricate).
- **`prompt_text`** ← not recomposed here (Phase 8 PROMPT-02 owns narrative recomposition with registry refs).
- Mapping verified against the real `shot_003.json` sample (offline — no live route needed).

### step counter numbering (CINEMA-02)
Number the 7 post-Phase-6 steps **`[N/7]`**: codec[1] / detect[2] / separate[3] / transcribe[4] / **semantic[5]** / timeline[6] / export[7]. **No phantom gap** — Phase 7 bumps to `[N/8]` when it inserts `step_reid` at position 6. (CINEMA-02's literal "[N/8]" deferred to Phase 7 to avoid a missing-step-number gap now.)

### video_content_hash for cache key (CINEMA-04)
**sha256 of first 1MB + last 1MB + file size** (`hashlib.sha256(head_1MB + tail_1MB + str(size).encode())`). Fast (avoids reading multi-GB episode videos fully), deterministic, collision-resistant enough for cache invalidation. Cache key tuple = `(video_content_hash, shot_id, route_name, route_version)`. Cache dir: `output/<asset>/route_cache/shot_analysis/shot_XXX.json`.

### Graceful-degrade + merge semantics (CINEMA-03)
- **Route down** (`--offline` or unreachable host) → all route-sourced facets written as **empty strings `""`** (schema-valid — prompts.schema facets are `type:string` with no minLength); asset still exports; `generator.warnings` populated with the failure reason.
- **`step_semantic` is the first real prompt generator** (CONTEXT: shot-timeline has none today; `prompts/merge_prompts.py` only merges external `part_*.json`). step_semantic writes `prompts.json` from route facets. If `part_*.json` content exists, **route wins** for the 5 route-sourced fields (camera/action/lighting/style/scene) — route is authoritative when available. `prompt_text`/`subject` left as-is if present.

### Preflight + flags (CINEMA-05/06)
- Preflight health check (GET or HEAD on the route base) before the step; per-shot failure is **non-fatal** (does not abort the asset export — one bad shot doesn't sink the whole asset).
- `--analysis-url` (default `http://127.0.0.1:<port>/api/v1/production/shot-analysis`), `--analysis-timeout` (default **960s**, > route-side 900s `execFileSync` ceiling), `--offline` (global; cache-only, no network), `--skip-semantic` (skip the step entirely).

### Claude's Discretion
- Exact prose of warning messages; helper function organization within `analysis/call_shot_analysis.py` (mapping function, httpx call, cache read/write, preflight).
- Whether `--offline` implies `--skip-semantic` semantics or still reads cache (recommend: `--offline` reads cache, only network is suppressed; `--skip-semantic` skips the whole step).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_pipeline.py` — step function pattern (`step_detect`/`step_separate`/`step_transcribe`/`step_timeline`/`step_export`), each with `--skip-*` cache check + `run_step(cmd, "[N/6] label")` banner. step_semantic mirrors this shape. Argparse at the bottom (`--skip-detect` etc. — kebab-case `action="store_true"`).
- `prompts/merge_prompts.py` — existing prompts merger (external `part_*.json`); step_semantic produces the route-driven prompts that may feed or supersede it.
- `audio/separate_stems.py` / `audio/transcribe.py` — the pattern for a stage that produces a JSON artifact with caching + graceful behavior.
- `scripts/export_asset.py` — `generator.warnings` would be populated here (asset.json generator object); check whether export_asset already reads/emits warnings (if not, Phase 6 adds the warnings channel).

### Established Patterns
- **Stage = self-contained CLI script** invoked via `subprocess.run([sys.executable, str(HERE / "<dir>" / "<script>.py"), ...])` from run_pipeline.
- **Idempotent caching:** every step checks `os.path.exists(out)` before running; `--force` clears. step_semantic caches per-shot route output under `route_cache/`.
- **Subprocess-first:** httpx is imported (first in-process network lib); the route call is a direct httpx POST (not subprocess).
- **CLI flags:** kebab-case `--skip-*` / `--*-url` / `--*-timeout`; Chinese `help=` strings; `choices=[...]` for enums.

### Integration Points
- `run_pipeline.py:main()` — insert `step_semantic` call between `step_transcribe` and `step_timeline`; thread the new flags.
- `prompts.json` — step_semantic's output (consumed by step_timeline + step_export).
- `asset.json#generator.warnings` — populated on route-down (via export_asset.py, if it supports it; else documented).

</code_context>

<specifics>
## Specific Ideas

- The field mapping is verified against `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` (real captured route output, dated 2026-07-24 13:08) — this is the **mapping correctness oracle** (no live route needed).
- Graceful-degrade is fully testable NOW (the route is not running on any common port) — the "route down → empty facets + asset exports" path is the primary automated verification; the live round-trip is deferred until `feat/shot-analysis-route` merges (per STATE.md blocker, pre-authorized: "coding proceeds, E2E blocked").
- `--analysis-timeout` default 960s is deliberately > the route-side 900s `execFileSync` ceiling so the client outlives the route's own internal timeout (otherwise the route kills itself before the client gets a response).

</specifics>

<deferred>
## Deferred Ideas

- **Live route round-trip E2E** — deferred until kais-aigc-platform `feat/shot-analysis-route` + `feat/shot-geometry-nodes` merge (STATE.md blocker). Mapping verified against captured output; graceful-degrade verified against route-down. The live round-trip becomes a post-merge smoke test.
- **`scene` field from Qwen-VL** — future extension (route has no scene source today); left empty, never fabricated.
- **`prompt_text` recomposition** — Phase 8 (PROMPT-02) owns narrative recomposition with registry refs; Phase 6 only fills the 5 facets.
- **step_reid + `[N/8]` counter bump** — Phase 7.

</deferred>
