---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: 分镜语义深化 — 镜头语言 + 跨镜角色/道具注册表
status: ready_to_plan
stopped_at: Phase 8 complete (3/3) — ready to discuss Phase 9
last_updated: 2026-07-24T21:23:00.575Z
last_activity: 2026-07-24
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 14
  completed_plans: 14
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-24)

**Core value:** 把成片解构成可导航、多轨道、带语义的分镜资产（分镜 + 分离音轨 + 对白 + 镜头语言 prompt + 跨镜可复用角色/道具注册表），且形态可移植——能作为下游 `@kais/infinite-canvas` 的「最终资产集合形态」被直接消费。
**Current focus:** Phase 9 — canvas consumer integration (cross repo)

## Current Position

Phase: 9
Plan: Not started
Status: Ready to plan
Last activity: 2026-07-24

**v1.1 phase sequence (dependency-ordered, research-validated):**

1. Phase 5 — Contract v1.1 (no route dep; mirrors v1.0 contract-first)
2. Phase 6 — Cinematography Auto-Fill `step_semantic` (blocked on cross-repo branch merges)
3. Phase 7 — Cross-Shot Re-ID Registry + HITL Review `step_reid` (HIGHEST complexity)
4. Phase 8 — Prompt Reference System + shot-timeline HTML Gallery
5. Phase 9 — Canvas Consumer Integration (cross-repo, highest coordination cost)

## Performance Metrics

**Velocity (v1.0 historical):**

- Total plans completed: 23 (across 4 phases)
- Average duration: ~20min
- Total execution time: ~40min

**By Phase (v1.0):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 2 | - | - |
| 2 | 2 | - | - |
| 3 | 1 | - | - |
| 4 | 2 | - | - |
| 5 | 4 | - | - |
| 6 | 3 | - | - |
| 7 | 4 | - | - |
| 8 | 3 | - | - |

| Phase 02 P02 | 15min | 2 tasks | 3 files |
| Phase 3 P1 | 45min | 3 tasks | 13 files |
| Phase 04 P01 | 12min | 2 tasks | 1 files |
| Phase 04 P02 | 7min | 2 tasks | 2 files |

**v1.1:**

| Phase.Plan | Duration | Tasks | Files |
|------------|----------|-------|-------|
| Phase 05 P01-04 | (see Phase 5 SUMMARY) | — | — |
| Phase 06 P01 | 4min | 2 tasks | 4 files |
| Phase 06 P02 | 11min | 2 tasks | 9 files |

*v1.1 metrics populate as plans complete*
| Phase 6 P02 | 11min | 2 tasks | 9 files |
| Phase 06 P03 | 10min | 2 tasks | 2 files |
| Phase 7 P01 | 4min | 2 tasks | 3 files |
| Phase 07 P02 | 4min | 1 tasks | 1 files |
| Phase 07 P03 | 18min | 2 tasks | 2 files |
| Phase 07 P04 | 22min | 3 tasks | 4 files |
| Phase 08 P01 | 2min | 2 tasks | 3 files |
| Phase 08 P02 | 6min | 3 tasks | 4 files |
| Phase 08 P03 | 16min | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current v1.1 work (post-milestone-bootstrap):

- **v1.1 schema_version**: `"1.1"` (minor bump, NOT `"2"`) — per project SPEC semver-lite rule; pure additive changes = minor; reserve major for future genuinely-breaking change. Research SUMMARY OPEN DECISION resolved.
- **v1.1 new analysis**: shot-timeline calls kais-aigc-platform HTTP routes (thin httpx client, zero ML deps) — reuses validated cinematography infra; maintains v1.0 loose coupling
- **v1.1 re-id**: cross-shot registry with mandatory HITL review (accept SOTA 60-80% mAP, treat review as feature not polish)
- **v1.1 canvas edit scope**: append `"1.1"` to `SHOT_TIMELINE_KNOWN_VERSIONS` + emit character/prop child nodes as `type:"asset"` + `assetType:"character"|"prop"` — NO custom renderer, NO Zod bump (canvas Zod already permissive on `assetType`)
- **v1.1 Phase 6 generator.warnings**: additive-only `array<string>` under `asset.schema.json#generator.properties` (Phase 6 Plan 01). required[] byte-identical to v1.0; `additionalProperties:false` retained; `schema_version` stays `"1.1"` (entire milestone shares one minor). Producer emits ONLY when non-empty list (clean runs byte-identical to v1.0). Sidecar `route_cache/warnings.json` → `export_asset.py:main` best-effort read → `generator.warnings`.

Carried from v1.0 (still load-bearing):

- shot-timeline is authoritative spec owner / external producer (loose coupling)
- Canvas uses structural parent node (zone/phase pattern) — reuses 5 renderers, no contract bump
- Canvas work happens on branch `feat/canvas-asset-collection` in `kais-aigc-platform`
- Two-tier authority: schemas are machine-checkable truth, SPEC.md is human-readable overview; on conflict schema wins
- schema_version pattern `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` (semver-lite)
- [Phase ?]: Phase 6 Plan 02: LOCKED route to prompts mapping (camera=join shot_scale+camera_primitive+camera_speed+geometry.primitive filtering falsy; action/lighting/style from semantic; subject/scene empty) verified against all 7 captured fixtures -> 0 schema errors. analysis/call_shot_analysis.py is the project first network dependency (httpx 0.28.1).
- [Phase ?]: Phase 6 Plan 02: graceful-degrade via httpx.HTTPError root catch-all + single preflight short-circuit; per-shot cache key (video_content_hash head+tail 1MB sha256, route_name, route_version). CINEMA-01/03/04/05 complete at component level; CINEMA-02/06 close in Plan 03 (run_pipeline step_semantic + flag wiring).
- [Phase ?]: Phase 6 Plan 03: run_pipeline step_semantic integrated as slot 5 of 7; [N/7] counter lock per CONTEXT D-XX (Phase 7 bumps to [N/8]); 4 flags + --force cache list extension; verify_phase6_smoke.py 3 scenarios green.
- [Phase 7]: registry-edits.schema.json locks the HITL edits round-trip contract (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes) — structured + deterministic + idempotent per CONTEXT Q2; free-form notes rejected; all 7 props optional (empty edits {} valid); apply order merge→split→rename→type_override→confirm/reject guarantees byte-identical re-apply (Pitfall 5)
- [Phase 7]: registry-edits is the 10th v1.1 fixture-regression shape (spec/validate.py 9→10); NOT an asset-dir shape — verify_contract.py EIGHT_SHAPES untouched (Plan 04 extends); CAST-06/CAST-07 NOT marked complete (split across plans 01 contract-layer + 03 implementation)
- [Phase ?]: normalize_clusters is CAST-05 shape-agnostic projector: every cluster gets review_state=proposed, extra route fields dropped, empty-member clusters skipped
- [Phase ?]: Re-id cache is per-video (video_<vch>.json) NOT per-shot — re-id is cross-shot aggregation (Pitfall 4)
- [Phase ?]: Warnings sidecar READ-merge-write: step_semantic warnings preserved + re-id appended (non-destructive)
- [Phase 07]: apply_edits.py confirmed-only HARD GATE at build-entry time (NOT filter-after-write) — Pitfall 7 enforcement; idempotent via fixed apply order + deterministic _next_id (max+1); validates registry-edits pre-apply (T-07-02) + characters/props pre-write
- [Phase 07]: representative_image OMITTED on ffmpeg failure (WARNING-2 fix authoritative over verify-block assertions) — schema-optional, no dangling PNG path reaches export_asset glob
- [Phase 07]: HITL HTML pre-selects auto_merge + auto_distinct as confirmed (RESEARCH Q2 Claude's Discretion); review tier left unselected — must be human-decided; cosine-sort surfaces review tier first
- [Phase 7]: step_reid integrated as slot 6 of 8; 20× [N/7]→[N/8] renumbered + 4 new [6/8] labels = 24 total. 3 new flags (--skip-reid/--reid-url/--reid-timeout); --offline shared. step_reid NON-BLOCKING — produces draft + auto-invokes gen_registry_review HTML; apply_edits remains standalone CLI per CONTEXT Q2.
- [Phase 7]: CONTRACT-06 closure: export_asset.py conditionally emits data.characters/props + media.characters[]/props[] ONLY when files exist. Old assets byte-identical to v1.0. Pre-write PNG assert NON-FATAL (CAST-09 graceful-degrade / WARNING-2); placed inside build_asset_dict so warning propagates to generator.warnings.
- [Phase 7]: _producer_registry_integrity is Pitfall 7 SECOND-LINE assert (defense-in-depth alongside apply_edits build-time hard gate). Additive + gated on file existence: v1.0 asset / route-down degrade → no registry files → no-op.
- [Phase 7]: CAST-01/02/03/04/08 documented DEFERRED cross-repo in 07-04-SUMMARY.md (kais-aigc-platform feat/character-reid-route, unmerged). Phase 7 ships as graceful-degrade producer; live route round-trip + τ calibration become post-merge smoke checks. Reference: 07-CONTEXT.md <deferred> + 07-RESEARCH.md §DINOv2 Re-ID Methodology.
- [Phase 08]: registry_snapshot is additive-OPTIONAL within v1.1 (not in generator.required; absent on v1.0/v1.1-no-reid assets still schema-valid) — Mirrors Phase 6 'warnings' precedent; CONTEXT Q1/Q2 LOCK
- [Phase 08]: NO schema_version bump for Phase 8 — registry_snapshot stays within '1.1' — STATE.md milestone lock; Pitfall 10 prevented at contract layer
- [Phase 08]: Pattern 2 recompose template locked (08-02): [style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting] — deterministic, idempotent, identity clauses skipped when refs empty
- [Phase 08]: Pitfall 17 producer integrity additive (08-02): prompts→registry check extended _producer_registry_integrity in place (no fork); reuses confirmed-ID sets from existing loop
- [Phase ?]: Phase 8 Plan 03: attach_refs banner omits [N/M] prefix to keep step-banner count at 24 (Pitfall 5 prevented); CONTEXT Q3 lock still honored (no new numbered step)
- [Phase ?]: Phase 8 Plan 03: gallery data source priority registry_snapshot > characters.json > None (RESEARCH Open Question 2 resolution)
- [Phase ?]: Phase 8 Plan 03: HTML XSS defense carried verbatim from Phase 7 CR-04 fix 336d04f — Python _esc + JS _esc + JSON-in-script .replace on all 5 inlined JSON literals

### Pending Todos

None yet for v1.1 execution (planning not yet started).

### Blockers/Concerns

- **Cross-repo branch merge (Phase 6 hard prerequisite):** kais-aigc-platform branches `feat/shot-geometry-nodes` + `feat/shot-analysis-route` are unmerged. Phase 6 contract/coding can proceed, but end-to-end verification is blocked until both merge. Flag explicitly in `/gsd:plan-phase 6`.
- **DINOv2 threshold calibration (Phase 7 research spike):** Literature τ≈0.30 cosine distance unvalidated on 《小江湖》-style animation. Plan-phase 7 must run `/gsd:plan-phase --research-phase 7` to produce ep01 same-person vs different-person cosine histogram and document the valley pick before locking the default τ.
- **Cross-repo coordination cost (Phase 9):** ~30% overhead measured in v1.0 for consumer-side work in kais-aigc-platform `feat/canvas-asset-collection` worktree at `/data/workspace/kst-canvas-consumer`.
- **`character-reid` route does not yet exist (Phase 7):** Only `shot-analysis` exists today. Phase 7 includes building the new route + driver in kais-aigc-platform (THIN wrapper mirroring `shot-analysis`).
- **`prompts.json#scene` field unmapped:** Current `shot-analysis` route output has no scene source. Phase 6 must decide leave-empty vs future Qwen-VL extension. Do NOT fabricate.

## Deferred Items

Items acknowledged and carried forward from v1.0 + v1.1 Out-of-Scope:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v1.0 (Out of Scope) | NATIVE-01/02: canvas native timeline renderer + native Range media service | Deferred — next milestone | 2026-07-20 |
| v1.0 (Out of Scope) | ORCH-01: shot-timeline as canvas orchestration skill (tight-coupling alt) | Deferred — evaluate post-v1.0 | 2026-07-20 |
| v1.0 (Accepted) | WR-01/WR-04: save-v2 secondary-path latent bugs | Consumer-repo backlog | 2026-07-21 |
| v1.1 (v2) | REID-01: InsightFace `antelopev2`/`buffalo_l` face fusion signal | Deferred — non-commercial license; evaluate if DINOv2 underperforms | 2026-07-24 |
| v1.1 (v2) | PROMPT-DIALECT-01: prompt_text dialect switch (paragraph vs keyword) | Deferred — v2 | 2026-07-24 |
| v1.1 (v2) | CROSSVIDEO-01: cross-video character continuity | Deferred — v2 | 2026-07-24 |
| v1.1 (v2) | SPEAKER-01: dialogue → speaker attribution | Deferred — v2 | 2026-07-24 |
| v1.1 (v2) | BBOX-01/CANVAS-EDGE-01/TURNAROUND-01: display enhancements | Deferred — v2 | 2026-07-24 |

## Session Continuity

Last session: 2026-07-24T20:55:26.493Z
Stopped at: "Phase 6 complete (all 3 plans shipped 2026-07-24) — run_pipeline.py step_semantic wired as slot 5 of 7; [N/7] counter locked (Phase 7 bumps to [N/8]); 4 new flags + --force cache list extension; scripts/verify_phase6_smoke.py 3 scenarios green (route-down / --skip-semantic / cache-hit-offline). Phase 6 now shippable as graceful-degrade producer; live route round-trip still deferred per blocker (feat/shot-analysis-route unmerged). Ready for /gsd:verifier-phase 6 then /gsd:plan-phase 7."
Resume file: None

## Operator Next Steps

- `/gsd:plan-phase 5` — Plan the Contract v1.1 phase (no external dependencies, unblock first)
- After Phase 5: `/gsd:plan-phase 6` — flag cross-repo branch merge prerequisite in the plan
- `/gsd:plan-phase 7` — use `--research-phase 7` for DINOv2 τ calibration spike
