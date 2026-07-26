# Phase 12: Producer Route Client (call_audio_analysis.py) - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — code phase mirroring 2 proven v1.1 analogs; shape forced by v1.1 patterns + Phase 11 schema + Phase 10 ROUTE-01 stub. All recommendations accepted per user momentum preference.

<domain>
## Phase Boundary

Producer-side thin httpx client `analysis/call_audio_analysis.py` that hits the Phase 10 ROUTE-01 stub (`POST /api/production/audio-analysis`) per-shot and normalizes the 3-modality response into `audio_semantic.json` (validating against the Phase 11 schema). Mirrors `call_shot_analysis.py` (httpx POST + normalize) + `call_reid.py` (per-shot cache + poisoned-cache invalidation + [audio] warnings sidecar merge).

This phase produces the producer client ONLY — NO route ML, NO pipeline wiring (Phase 14), NO HTML (Phase 16). The client is the bridge between the Phase 10 stub envelope and the Phase 11 schema.

</domain>

<decisions>
## Implementation Decisions

### Client structure (mirror v1.1 analogs — proven patterns)

- **httpx POST + normalize → `call_shot_analysis.py` analog.** Per-shot POST `{video, shots, shot_id_range, stems_dir, models, language}` to `POST /api/production/audio-analysis` (the Phase 10 ROUTE-01 mount, NO `/v1/`). Normalize the route's `{code:200, data:{shots:[...]}}` envelope into `audio_semantic.json` per the Phase 11 `audio_semantic.schema.json`. Route-side timeout 900s (mirror shot-analysis). `httpx.ConnectError` → graceful-degrade (below).
- **Per-shot 4-tuple cache + poisoned-cache invalidation → `call_reid.py:418-427` analog.** Cache key: `(video_content_hash, route_name="audio-analysis", route_version, shot_id)`. On cache hit: schema-validate the cached entry against `audio_semantic.schema.json`; if validation FAILS (poisoned), auto-invalidate + re-fetch (mirror call_reid.py:418-427). Cache dir under `output/<video>/.cache/audio-analysis/` (mirror reid cache layout).
- **Graceful-degrade + `[audio]` warnings sidecar → `call_reid.py:443-449` analog.** Route unreachable / preflight fail / `--offline` → `audio_semantic.json` NOT written (byte-identical to v1.1 asset — Pitfall 11/CONTRACT-05) AND an `[audio]` warning appended to the sidecar via read-merge-write (do NOT clobber existing `[semantic]`/`[reid]` tags). Mirror call_reid.py:443-449 read-merge-write exactly.
- **Stub-only round-trip proof.** Against the Phase 10 stub (models unloaded, `stub_mode:true`), the client confirms: envelope parsing + cache write + warnings merge all work BEFORE route ML is live. This is the SC#4 deliverable — proves the client integrates with the stub the moment the route host is up.

### Schema validation (Phase 11 contract = the client's pre-write gate)

- Before writing `audio_semantic.json`, the client MUST validate the normalized payload against `spec/schemas/audio_semantic.schema.json` (Draft202012Validator). Invalid → graceful-degrade (don't write poisoned data; append warning).
- Honor the Phase-10-informed field shapes: emotion nullable+confidence, word_level_experimental flag, instruments ABSENT (do NOT synthesize an instruments field — MUS-04 deferred).

### CLI surface (mirror call_shot_analysis.py / call_reid.py argparse)

- `--video`, `--shots`, `--output` (audio_semantic.json path), `--stems-dir`, `--route-url` (default the ROUTE-01 host), `--models`, `--language`, `--offline` (skip route, graceful-degrade), `--force` (ignore cache). Chinese `help=` strings per CLAUDE.md convention.

### Claude's Discretion

- Exact function decomposition (mirror call_shot_analysis.py's structure: argparse main + httpx call + normalize + cache helpers).
- Whether to factor a shared `_warnings_merge` helper (if call_reid.py's is reusable, import; else copy).
- Exact 4-tuple cache filename scheme (mirror call_reid.py's hashing).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (v1.1 analogs — Phase 12 mirrors, does NOT rewrite)
- **`analysis/call_shot_analysis.py`** (424 lines) — the httpx POST + normalize pattern. The route-envelope expectations (`{code:200, data:{shots:[...]}}`, 900s timeout, ConnectError graceful-degrade).
- **`analysis/call_reid.py`** (457 lines) — the per-shot cache + poisoned-cache invalidation (`:418-427`) + `[audio]`/`[semantic]` warnings sidecar read-merge-write (`:443-449`).
- **`spec/schemas/audio_semantic.schema.json`** (Phase 11) — the client's pre-write validation target.
- **Phase 10 ROUTE-01 stub** (`kais-aigc-platform feat/audio-analysis-route`) — the integration target. Body schema + envelope confirmed in 10-02-SUMMARY.
- **`spike/audio/results/*.json`** (Phase 10) — realistic shape reference for the normalized audio_semantic payload.

### Established Patterns
- **Route-vs-client split:** heavy ML behind the route host; shot-timeline takes zero ML deps. The client is pure httpx + jsonschema + cache.
- **Graceful-degrade contract (CONTRACT-05):** absent audio_semantic = byte-identical v1.1 asset; never crash the pipeline on route failure.
- **Read-merge-write sidecar:** warnings append, never clobber (the `[semantic]`/`[reid]`/`[audio]` tags coexist).

### Integration Points
- Phase 14 (`step_audio_semantic`) wires this client into run_pipeline.py as slot 7/9.
- Phase 13 (`link_speakers`) runs between this client and step_timeline (consumes speakers from the route response).

</code_context>

<specifics>
## Specific Ideas

- The poisoned-cache invalidation (schema-validate on hit, re-fetch on fail) is the key correctness feature — it means a Phase 11 schema tightening auto-invalidates stale cached entries. Mirror call_reid.py:418-427 exactly.
- The stub round-trip (SC#4) is the proof that the client works against the Phase 10 stub TODAY — don't defer it. Run it against the stub envelope (`stub_mode:true`) to prove envelope parsing + cache + warnings before route ML lands.
- The `[audio]` warnings sidecar merge MUST not clobber `[semantic]`/`[reid]` tags (read-merge-write). This is the cross-feature integration that keeps v1.1 features intact.

</specifics>

<deferred>
## Deferred Ideas

- **Live ML round-trip** (route host loading SenseVoice/WhisperX/MERT/PANNs) — Phase 12 proves the stub envelope round-trip; live ML is post-merge smoke (mirror v1.1 CAST deferred pattern).
- **Reproduction prompts** (`reproduction.{tts,music_gen,foley}` in audio_semantic) — Phase 15 promotes the gen_audio_prompts spike into the pipeline; Phase 12 just passes through whatever the route returns (or leaves reproduction absent if the route doesn't populate it yet).

</deferred>
