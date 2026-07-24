# Project Research Summary

**Project:** kais-shot-timeline — v1.1 分镜语义深化 (Cinematography auto-fill + cross-shot character/prop re-id registry + prompt reference system + ShotTimelineAsset contract bump + dual-end display)
**Domain:** Loosely-coupled 2-repo video-shot-decomposition ecosystem — Python CLI producer (shot-timeline, this repo) + TS/React-Flow canvas consumer (kais-aigc-platform, cross-repo branch `feat/canvas-asset-collection`) + ComfyUI-hosted ML routes (also kais-aigc-platform)
**Researched:** 2026-07-24
**Confidence:** HIGH (every load-bearing claim LIVE-verified against both repos + PyPI + real route output `shot_003.json`)

---

## Executive Summary

v1.1 is a **strict-additive, contract-first minor bump** on top of the shipped v1.0 ShotTimelineAsset contract. It adds two new pipeline stages that call ML HTTP routes in `kais-aigc-platform` (cinematography analysis + cross-shot re-id), three new optional data files (`characters.json`, `props.json`, enriched `prompts.json`), an HITL review HTML deliverable, and a canvas consumer extension that emits character/prop child nodes. The milestone is genuinely cross-repo: producer work happens in this repo, the consumer edit + new routes happen in `kais-aigc-platform`, and the unmerged `feat/shot-geometry-nodes` + `feat/shot-analysis-route` branches are a hard blocking dependency for any end-to-end verification. Experts build this kind of system by (a) drafting the schema first so producer code never locks the wrong field names, (b) treating re-id as a **semi-automatic candidate-generator** because SOTA cloth-changing re-id is only 60-80% mAP on photorealistic content and worse on animation, and (c) keeping the producer thin (one HTTP client lib, zero ML deps) with mandatory graceful-degrade paths so the pipeline still ships a valid asset when routes are offline.

The recommended approach mirrors what worked in v1.0 (contract-first, additive-only, verify-harness-extends-in-lockstep) with two new operational concerns absent from v1.0: **route availability** (the pipeline was previously fully offline; v1.1 introduces its first network dependency, so `--offline`, per-shot cache with route-version fingerprint, preflight health check, and shot-level atomic caching are non-negotiable) and **HITL review as a first-class deliverable** (the review HTML is the registry's source of truth, not a polish step — every cluster ships as `review_state: "proposed"` until a human explicitly confirms; only `confirmed` entries flow into prompt references). The key architectural gift from v1.0 is that the canvas consumer's Zod schema already accepts `assetType: z.string().min(1)` and `AssetNode.tsx` falls back to `📦` for unknown assetTypes — meaning characters/props emit as `type: "asset"` + `assetType: "character"|"prop"` with **zero new node type, zero Zod bump, zero new renderer**.

Top risks to mitigate: (1) the contract accidentally becoming a major bump via field rename / semantic shift / added required field / tightened constraint — Pitfall 11, flagged highest-severity; (2) re-id silently mis-clustering and poisoning downstream prompts without the review HTML in place — Pitfall 7; (3) route unavailability breaking the previously-offline pipeline — Pitfall 8; (4) consumer `SHOT_TIMELINE_KNOWN_VERSIONS` not getting the new version appended, silently stripping v2 fields via Zod default-strip — Pitfalls 14 + 15; (5) the unmerged cinematography branches blocking end-to-end verification — operational dependency on a cross-repo merge. All five are prevented by sequencing: schemas + verify harness FIRST, route client with graceful-degrade SECOND, re-id with mandatory review THIRD, prompt enrichment FOURTH, canvas consumer LAST.

---

## Cross-Research Consensus (All 4 Researchers Agree)

These points are settled. Requirements-definer / roadmapper can treat them as ground truth.

### 1. shot-timeline stays THIN — one new dep, zero ML
- shot-timeline adds exactly **ONE runtime dep**: `httpx 0.28.1` (already installed in env). Zero new ML deps.
- All heavy ML — DINOv2 ViT-B/14 embeddings, scikit-learn AgglomerativeClustering, SAM3 segmentation — lives in a **NEW `character-reid` route** in `kais-aigc-platform`. Only `shot-analysis` route exists today; `character-reid` must be built.
- Consistent with v1.0's "external producer" + "loose coupling" + "don't touch shot-timeline algorithms" decisions.

### 2. Canvas consumer needs NO new node type and NO Zod bump
- LIVE-verified: `canvasAssetSchema.ts:82` types `assetType: z.string().min(1, "...(character|scene|prop)")` — any non-empty string.
- `AssetNode.tsx:123,171` falls back to `📦` for unknown assetTypes. `FlowCanvas.tsx:55-64` already registers `asset: AssetNodeComponent`.
- Characters/props emit as `type: "asset"` + `assetType: "character"|"prop"`.
- **The ONLY consumer edit needed:** append the new schema_version to `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"])` at `import-from-dir.ts:898`, AND refactor `extractShotTimelineArtifacts` (lines 943-1140) to emit character/prop child nodes gated on the new version.
- Consistent with v1.0's "no custom renderer / no contract bump on canvas side" decision.

### 3. Two new producer steps, both graceful-degrade
- **`step_semantic`** — slots between `step_transcribe` and `step_timeline`. Calls existing `POST /api/v1/production/shot-analysis`. Produces/merges into `prompts.json` (camera/action/lighting/style/subject facets).
- **`step_reid`** — runs after `step_semantic`, before `step_timeline`. Calls NEW `POST /api/v1/production/character-reid`. Produces `characters.json` + `props.json` and patches `prompts.json` with `character_refs[]`/`prop_refs[]`.
- Both: cache on file-existence, both `--skip-*-able`, both graceful-degrade to `None` on route failure (asset still exports).
- **First-ever network dependency in the pipeline** → needs `--offline` flag, per-shot cache, backoff. Mirror the existing `--skip-detect/--skip-separate/--skip-transcribe` kebab convention.

### 4. Contract work is pure-additive — DO NOT restructure existing fields
- NEW `characters.schema.json` + `props.schema.json` — OPTIONAL, not added to `asset.schema.json` `required` list (else = major bump).
- `prompts.schema.json` gets OPTIONAL `character_refs[]` / `prop_refs[]` array. **Do NOT restructure existing `camera: string` into `{shot_scale, camera_primitive, speed}`** — that is a breaking semantic shift (Pitfall 11). Add structured fields ALONGSIDE the existing string fields if needed.
- `verify_contract.py` `SIX_SHAPES` extends to `EIGHT_SHAPES` (add characters, props). Self-test extends with v2 fixtures + cross-version cases (v1 fixture under v2 consumer and vice versa).
- `additionalProperties: false` stays on every schema object — the bump mechanism works BECAUSE the schema is strict.

### 5. Re-id HITL review IS the feature — not a polish step
- SOTA cloth-changing re-id is ~60-80% mAP (photorealistic); animation is worse (out-of-distribution). SOTA cross-domain drops to 20-50% mAP.
- **Every cluster carries `review_state: proposed|confirmed|rejected`.** Only `confirmed` entries flow downstream into prompt references.
- Three-tier threshold (auto-merge ≥0.85 / review-required 0.6-0.85 / auto-distinct <0.6) + mandatory review HTML deliverable (mirror `gen_timeline_html.py` pattern).
- The review HTML is a FIRST-CLASS phase deliverable, not an afterthought script.

### 6. Build order: contract first, route-merge BLOCKING, canvas LAST
- **Contract schema draft can go FIRST** (no route needed; mirrors v1.0 contract-first that worked).
- **Route-branch-merge is BLOCKING** for any end-to-end verification (`feat/shot-geometry-nodes` + `feat/shot-analysis-route` must merge in `kais-aigc-platform`).
- **Review-UI is the HIGH-complexity critical path** within the re-id phase.
- **Canvas consumer work is LAST** and has the highest cross-repo coordination cost (~30% measured in v1.0).

---

## OPEN DECISION — schema_version `1→2` vs `1→1.1` (NEEDS USER CONFIRMATION BEFORE LOCK)

**This discrepancy MUST be reconciled before requirements / roadmap lock the value.** Do NOT silently pick one.

| Position | Source | Value | Argument |
|---|---|---|---|
| **RECOMMENDED** | `STACK.md` §"Schema Bump Nuance" | `"1.1"` | The project's own SPEC rule (`asset.schema.json:7` + `SPEC.md §4`) defines additive changes (new optional field, new data file, new enum value) as **minor bump** and reserves major (`"2"`) for **rename / semantic shift / removal / added required field / tightened constraint**. v1.1 is purely additive. Picking `"2"` (a) violates the project's own semver-lite rule and (b) burns the major-bump escape hatch for a future genuinely-breaking change. |
| Current PROJECT.md / PITFALLS.md / ARCHITECTURE.md wording | orchestrator + 2 researchers | `"2"` | Used throughout the v1.1 milestone framing. PITFALLS.md §11 even rests its "this is minor bump, not major" argument on this labeling while still using `"2"` as the literal — internally inconsistent. |

**Live verification of consumer behavior** (`src/routes/canvas/v2/import-from-dir.ts:892-898`): the consumer does NOT reject unknown versions — it warns and continues. So either `"1.1"` or `"2"` is functionally safe at the canvas side. The discrepancy is purely about **internal SPEC consistency**.

**Recommendation to planner (per STACK.md):** ship v1.1 as `schema_version: "1.1"`. Reserve `"2"` for the first genuinely breaking change (e.g. renaming `shots` → `segments`, removing `bass.wav`-tolerant fallback). Update PROJECT.md's `"1→2"` wording to `"1→1.1"` at Phase 1.

**If the user insists on `"2"`:** document it explicitly in SPEC.md §4 Changelog as a stated exception to the semver-lite rule (otherwise the SPEC contradicts itself and Pitfall 11's prevention checklist fails).

**This SUMMARY uses `"1.1"` in concrete field references below** (e.g. `KNOWN_VERSIONS = new Set(["1", "1.1"])`) and flags the alternative in each location. The roadmapper should not pick a phase structure that depends on either choice — both fit the same build order.

---

## Key Findings

### Recommended Stack (from STACK.md)

shot-timeline gains **one** new runtime dep (`httpx`); the canvas consumer gains **zero** new deps; the heavy-ML `character-reid` route in `kais-aigc-platform` gains `transformers` (DINOv2 loader) + `scikit-learn` (clustering). InsightFace (face-only ArcFace) is **deferred to v1.2** as a fusion signal if DINOv2 alone underperforms; both ArcFace packs are non-commercial-research-licensed.

**Core technologies (NEW for v1.1):**
- **`httpx 0.28.1`** (shot-timeline, already installed) — sync HTTP client for `step_semantic` + `step_reid` calling the analysis routes. Chosen over `urllib` (the comfyui driver's pattern) because route calls are long-running (up to 900s route-side `execFileSync` ceiling) and need per-pool/connect/read timeouts + transport-level retries. Graceful-degrade returns `None` on any failure.
- **DINOv2 ViT-B/14** (`facebook/dinov2-base`, kais-aigc-platform route side, loaded via `transformers 5.14.1`) — 768-d visual embedding for ANY crop (face/profile/back-of-head/body/object). One-model solution for both characters AND props; works where face-rec models return nothing. SOTA for self-supervised re-id. ~346 MB.
- **`scikit-learn 1.9.0`** (route side) — `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)`. Deterministic, interpretable dendrogram (matches HITL constraint). Starting threshold τ ≈ 0.30 cosine distance (≈ 0.70 similarity); per-show tuning required.
- **SAM3** (already in comfyui-primary container, route side) — `SAM3Segment` with `output_mode="Merged"` to mask main subjects per shot. Reused from validated P0–P4 cinematography work.
- **`jsonschema 4.26.0`** (shot-timeline, already used) — Draft 2020-12 inline validator. No new validation tooling.

**Critical version / design decisions:**
- DO NOT add `pydantic`, `fastjsonschema`, `tenacity`/`stamina` — premature or wrong-tool.
- DO NOT use OpenCLIP / OpenAI CLIP for re-id (image-text alignment is wrong for instance identity).
- DEFER InsightFace `antelopev2`/`buffalo_l` to v1.2 (non-commercial license; fragile download).

### Expected Features (from FEATURES.md)

**Must have — table stakes (P1):**
- Cinematography auto-fill HTTP client + graceful-degrade (LOW complexity; thin `httpx` client, ~150 LOC).
- Character/prop occurrence detection per shot via SAM3 (MEDIUM; reuses validated infra).
- Re-id embedding + initial clustering (MEDIUM; DINOv2 + Agglomerative).
- **Human review UI for cast/prop registry** (HIGH; most novel UI surface in v1.1 — merge/split/rename flows, new HTML generator, multi-file review state persistence).
- `characters.json` + `props.json` as canonical data files (LOW; two new schemas + 2 optional asset fields).
- Prompt reference fields `subject_refs` / `prop_refs` (MEDIUM; new optional schema fields + recompose `prompt_text`).
- Contract minor bump mechanics (LOW; additive only, SPEC §4 graceful-degrade designed for exactly this).
- Backward-compatibility smoke test in `spec/validate.py` (LOW; non-negotiable given v1.0 graceful-degrade promise).
- shot-timeline HTML: character/prop gallery section (MEDIUM; new section in `gen_timeline_html.py`).

**Should have — differentiators (P2):**
- Reference chips in prompt UI (MEDIUM; visual badges linking to cast/prop entry).
- Cluster confidence + review-state visualization (MEDIUM; cosine distance heatmap).
- Best-of-N representative crop auto-selection (MEDIUM; sharpness + mask-area + embedding-centroid scoring).
- `prompt_text` dialect switch (paragraph vs keyword) (LOW-MEDIUM; per AI-video-model target).
- Per-occurrence bbox visualization on first/last frames (LOW; SVG overlay).
- Canvas consumer cast/prop node emission (MEDIUM cross-repo; covered in build order).
- SchemaVer-labeled changelog section in SPEC.md (LOW; pure documentation).

**Anti-features (do NOT build):**
- Fully-automatic re-id without HITL (SOTA 20-50% cross-domain mAP; mis-cluster rate undermines continuity proposition).
- Cross-video character continuity (out of scope; defer to v1.2+).
- Dialogue → speaker attribution (separate hard ML problem; out of scope).
- Expanding prompts schema from 6 to 8 facets (YAGNI; encode `pacing`/`lens` inside existing `camera`/`style` strings if route ever exposes them).
- Synthesizing multi-angle turnaround sheets (back views may not exist; faked angles degrade downstream identity).
- **Bundling character crops as base64 inside `characters.json`** (bloats asset 10-50× past `frames.json`; use external `characters/<id>.png` files under asset root, listed in `asset.json#media.characters`, served by `scripts/serve.py`).
- Bumping the contract to `"3"` mid-v1.1 (reserve breaking changes for v2.0).
- Custom canvas renderer for cast/prop nodes (out of scope per v1.0 decision; reuse existing `asset` renderers).
- Storing raw embedding vectors inside `characters.json` (use out-of-line `characters/<id>.npy` or omit if no incremental re-clustering).
- Lip-sync / motion re-targeting (that's generation, not analysis).

### Architecture Approach (from ARCHITECTURE.md)

Three LIVE-verified discoveries reshape the plan:
1. **Canvas needs NO contract bump and NO new renderer** — `canvasAssetSchema.ts:76-94` already permissive on `assetType`; `AssetNode.tsx:123,171` falls back to `📦`. The v1.0 design reserved `asset` as a generic media-bearing primitive for exactly this.
2. **Consumer has ONE singular version gate** — `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"])` at `import-from-dir.ts:898`. This is THE integration seam to plan around.
3. **Cinematography route output maps near-1:1 onto existing `prompts.schema.json` facets** — verified against real `/mnt/agents/output/gpu1/shot_analysis/shot_003.json`. `semantic.shot_scale` + `geometry.primitive/speed` → `camera`; `semantic.subject_motion` + `subject.direction_cn` → `action`; `semantic.lighting` → `lighting`; `semantic.lens_feel` → `style`.

**Major NEW components (producer repo):**
1. `analysis/call_shot_analysis.py` — HTTP client → route → `prompts.json`.
2. `registry/extract_subjects.py` — Stage A: call subject-segmentation route (SAM3 masks → crops).
3. `registry/cluster.py` — Stage B: DINOv2 embeddings + AgglomerativeClustering → draft registry.
4. `html/gen_registry_review.py` — Stage C: HITL review HTML (CRITICAL-PATH deliverable).
5. `registry/apply_edits.py` — Stage D: apply reviewer's merge/split/rename → canonical `characters.json` + `props.json`.
6. `spec/schemas/characters.schema.json`, `spec/schemas/props.schema.json`, `spec/schemas/registry.schema.json` — NEW schemas.

**Major MODIFIED components (producer repo):**
- `run_pipeline.py` — insert `step_semantic` (step 5 of 8) + `step_reid` (step 6 of 8); add `--analysis-url`, `--skip-semantic`, `--skip-reid`, `--analysis-timeout`, `--offline` flags.
- `scripts/export_asset.py` — bump `schema_version` literal; emit optional `data.characters`/`data.props` + `media.characters`/`media.props` only when files exist; SCHEMA_VERSION constant as single source of truth.
- `html/gen_timeline_html.py` — render reference chips + character/prop gallery.
- `spec/schemas/asset.schema.json`, `prompts.schema.json` — extend with optional fields; bump `$comment`.
- `spec/SPEC.md` — §2 layout, §3 fields, §4 v1.1 changelog, new §5.6/5.7, §6 media extensions.
- `scripts/verify_contract.py` — `SIX_SHAPES` → `EIGHT_SHAPES`; cross-version self-tests.

**Major MODIFIED components (consumer repo, `kais-aigc-platform` branch `feat/canvas-asset-collection`):**
- `src/routes/canvas/v2/import-from-dir.ts:898` — append `"1.1"` (or `"2"`) to `SHOT_TIMELINE_KNOWN_VERSIONS`.
- `extractShotTimelineArtifacts` (lines 943-1140) — emit character/prop child nodes gated on new version.
- `AssetNode.tsx:17-19` — OPTIONAL: add `character: '🧑'`, `prop: '🔧'` to `typeIcons` (cosmetic only).
- `scripts/verify-canvas-shot-timeline.ts` — extend assertions for v1.1 character/prop node counts.

**Major NEW components (consumer repo, aigc-platform):**
- `src/routes/production/character-reid/` — NEW route (THIN wrapper pattern mirroring `shot-analysis/index.ts`).
- `scripts/character-reid/character_reid_driver.py` — SAM3 + DINOv2 + clustering driver script.

**Re-id data flow (end-to-end):**
```
frames.json + shots.json
    ↓ POST /api/v1/production/character-reid
    ↓ (in route) SAM3 masks → DINOv2 embeddings → Agglomerative clusters
    ↓
registry.draft.json  (every cluster has review_state: "proposed")
    ↓ html/gen_registry_review.py  (HITL Stage C — CRITICAL PATH)
    ↓
registry.edits.json  (reviewer merge/split/rename decisions)
    ↓ registry/apply_edits.py  (Stage D)
    ↓
characters.json + props.json  (only review_state:"confirmed" entries flow downstream)
    ↓ PATCH prompts.json with character_refs[]/prop_refs[]
    ↓
step_export → asset.json @ schema_version "1.1"
```

### Critical Pitfalls (from PITFALLS.md — top 6 by severity / recovery cost)

1. **Pitfall 11 — Contract bump actually a major bump in disguise (HIGHEST severity, HIGH recovery cost).** Prevention: schema PR diffs are only-`+` lines; new fields always optional (never in `required`); never rename / semantic-shift / remove / tighten existing fields; never reduce enum. v1 fixture stays unmodified at `schema_version: "1"`; new v1.1 fixture added alongside.
2. **Pitfall 7 — Re-id fully-automatic幻觉 (skip HITL).** Prevention: registry schema has `status: "draft"|"reviewed"|"locked"`; review HTML is a first-class phase deliverable; pipeline fails-loud if `registry.edits.json` is missing in `--non-interactive` mode.
3. **Pitfall 8 — Route dependency makes offline pipeline crash on network failure.** Prevention: route output cached to `output/<asset>/route_cache/<route>/<shot_id>.json`; cache key = `(video_content_hash, shot_id_range, route_name, route_version)`; `--offline` global flag; preflight health check before step 1; mirror Whisper backend fallback semantics.
4. **Pitfalls 14 + 15 — Consumer Zod default-strip silently drops v2 fields / v1 producer assets break on v2-aware consumer.** Prevention: explicitly reuse `asset` type + `assetType: "character"|"prop"` (NOT a new canvasType — that would be a major bump); NEVER use `.strict()` on Zod (would break 689 historical rows); new fields go through `pipeline-field-map.yaml`; cross-version verify both ways (v1 asset → v2 consumer should warn-once + render; v2 asset → v1 consumer should warn + degrade).
5. **Pitfall 1 — Wrong re-id embedding modality.** Prevention: DINOv2 ViT-B/14 as the universal default (works on faces, profiles, backs, bodies, objects); if v1.2 face-precision is insufficient, ADD InsightFace as fusion signal, not replacement; small-face threshold hardline (< 32px face width → face embedding treated as missing).
6. **Pitfall 6 — SAM3 single-frame crop unusable (hair/hand/prop truncated + motion blur + occlusion).** Prevention: sample N=3-5 frames per shot (25%/50%/75% time positions), not just first/last; `mask_quality` metric stored in schema; low-quality frames flagged `unusable` and skipped from clustering; first/last frames are fallback only.

---

## Implications for Roadmap

Suggested **5-phase** structure. Phase names align with PROJECT.md's 5 target features but reorder to respect dependencies (contract first; route wiring after branches merge; re-id with embedded HITL; canvas last).

### Phase 1: Contract v1.1 — Schemas + SPEC + Fixtures + Verify Harness
**Rationale:** No route dependency. Mirrors v1.0 contract-first sequencing that worked. Producer code MUST NOT lock wrong field names — drafting schema first prevents rework.
**Delivers:**
- `characters.schema.json`, `props.schema.json`, `registry.schema.json` (NEW)
- `prompts.schema.json` extended with optional `character_refs[]`/`prop_refs[]`
- `asset.schema.json` extended with optional `data.characters`/`data.props` + `media.characters`/`media.props`
- Bumped `schema_version` literal in `export_asset.py` SCHEMA_VERSION constant (RESOLVE "1.1" vs "2" first — see OPEN DECISION above)
- `SPEC.md` §4 Changelog entry, new §5.6/5.7
- v1.1 fixture set under `spec/fixtures/v1.1/` (v1 fixture at `spec/fixtures/minimal/` stays UNMODIFIED)
- `verify_contract.py`: `SIX_SHAPES` → `EIGHT_SHAPES`; new v1.1 self-test cases; cross-version verify (v1 fixture under v1.1 schema, v1.1 fixture under v1 schema)
**Addresses features:** Contract minor bump mechanics, registry schemas, prompt reference fields (schema level).
**Avoids pitfalls:** 11 (major-bump-in-disguise), 12 (forgot to bump), 13 (verify not extended), 5 (ID scope documented), 17 (cross-file integrity check), 18 (registry snapshot field design), 3 (costume-change `looks[]` schema), 16 (appearance edge type schema-level definition).

### Phase 2: Cinematography Auto-Fill (`step_semantic`)
**Rationale:** Requires `feat/shot-geometry-nodes` + `feat/shot-analysis-route` MERGED in kais-aigc-platform — **flag the merge as a phase prerequisite in the roadmap**, not a work item. After Phase 1 because the enriched `prompts.schema.json` must exist before the producer writes to it.
**Delivers:**
- `analysis/call_shot_analysis.py` — httpx client mapping `semantic.*`/`geometry.*`/`subject.*` → 6 prompt facets.
- `step_semantic` between `step_transcribe` and `step_timeline` in `run_pipeline.py`.
- Graceful-degrade: route down → `prompts.json` written with empty facet strings (schema-valid); asset still exports.
- CLI flags: `--analysis-url`, `--skip-semantic`, `--analysis-timeout` (default 960s, > route's 900s ceiling), `--offline`.
- Per-shot cache at `output/<asset>/route_cache/shot_analysis/shot_XXX.json`; cache key includes `(video_content_hash, shot_id, route_name, route_version)`.
- Preflight health check + `generator.warnings` populated on per-shot failure.
**Addresses features:** Cinematography auto-fill HTTP client + graceful-degrade.
**Avoids pitfalls:** 8 (route crashes pipeline), 9 (cache/offline mutual exclusion), 10 (per-shot partial failure).

### Phase 3: Cross-Shot Re-ID Registry + HITL Review (`step_reid`) — HIGHEST COMPLEXITY
**Rationale:** Re-id is the hardest feature in v1.1 (SOTA 60-80% mAP photorealistic, worse on animation). HITL review is the critical-path deliverable — without it the registry is noise and downstream features have nothing trustworthy to consume. After Phase 2 because the registry patches `prompts.json` which `step_semantic` enriched; the route-side infra (NEW `character-reid` route + driver) must be built in lockstep.
**Delivers:**
- NEW `src/routes/production/character-reid/` route in kais-aigc-platform (THIN wrapper).
- NEW `scripts/character-reid/character_reid_driver.py` — SAM3 mask → DINOv2 embeddings → AgglomerativeClustering → draft registry.
- `registry/extract_subjects.py`, `registry/cluster.py`, `registry/apply_edits.py` (producer-side clients / Stage D applier).
- **`html/gen_registry_review.py` (Stage C) — non-negotiable, first-class deliverable.** Mirror `gen_timeline_html.py` pattern: cluster cards with merge/split/rename, cosine-distance-sorted review queue, three-tier threshold visualization.
- Three-tier threshold: auto-merge ≥0.85 / review-required 0.6-0.85 / auto-distinct <0.6.
- `registry.draft.json` → review HTML → `registry.edits.json` → canonical `characters.json` + `props.json`.
- Every cluster `review_state: "proposed"` until human confirms; only `"confirmed"` flows downstream.
- SAM3 multi-frame sampling (N=3-5 per shot); `mask_quality` metric; `unusable` flag for low-quality frames.
- `step_reid` in `run_pipeline.py` (step 6 of 8).
**Addresses features:** Character/prop occurrence detection, re-id embedding + clustering, HITL review UI, registry data files.
**Avoids pitfalls:** 1 (modality), 2 (threshold sensitivity), 3 (costume-change `looks[]`), 4 (background leakage), 6 (SAM3 sheet quality), 7 (full-auto hallucination).

### Phase 4: Prompt Reference System + shot-timeline HTML Gallery
**Rationale:** After Phase 3 because references require the registry to exist with `review_state: "confirmed"` entries. The HTML gallery is the end-user-visible payoff.
**Delivers:**
- Post-process prompts.json: attach `character_refs[]`/`prop_refs[]` IDs based on `characters.json#appearance_shots[]`.
- Cross-file integrity check (no dangling IDs) — added to `verify_contract.py`.
- `html/gen_timeline_html.py` extended: character/prop gallery section + clickable reference chips in prompt rendering.
- Per-shot "运镜分析填充" indicator (green chip = route filled; gray = offline-degraded empty).
- `generator.registry_snapshot` field embedded in asset.json (freezes registry state for prompt reference stability on later mutations).
**Addresses features:** Prompt reference system, shot-timeline HTML gallery.
**Avoids pitfalls:** 17 (prompt dangling IDs), 18 (registry snapshot).

### Phase 5: Canvas Consumer Integration (cross-repo)
**Rationale:** LAST — highest cross-repo coordination cost (~30% measured in v1.0). Consumer must wait for producer to emit valid v1.1 manifests before it can be tested against them.
**Delivers:**
- `import-from-dir.ts:898` — append `"1.1"` (or `"2"`) to `SHOT_TIMELINE_KNOWN_VERSIONS`.
- `extractShotTimelineArtifacts` refactor: emit character/prop child nodes with `canvasType: "asset"`, `extra.assetType: "character"|"prop"`, gated on the new version.
- `AssetNode.tsx` typeIcons: optional `character: '🧑'`, `prop: '🔧'` (cosmetic).
- `verify-canvas-shot-timeline.ts` extended for v1.1 character/prop node counts.
- 3-mode `verify_contract.py` harness green on v1.1 fixture.
- Worktree-per-effort isolation (v1.0 RETROSPECTIVE pattern).
**Addresses features:** Canvas consumer cast/prop node emission.
**Avoids pitfalls:** 14 (Zod strip / new canvasType), 15 (v1 producer breaks on v2-aware consumer).

### Phase Ordering Rationale

- **Contract first (Phase 1)** — producer code MUST NOT lock wrong field names; v1.0 proved this sequencing works.
- **Route client second (Phase 2)** — proves the HTTP-client pattern + cache + offline design works before building ML pipelines on top. Blocked on cross-repo branch merges (flag explicitly).
- **Re-id third (Phase 3)** — review HTML is the longest-lead critical-path item; starting it earlier de-risks.
- **Prompt enrichment fourth (Phase 4)** — references require the registry's confirmed entries.
- **Canvas consumer last (Phase 5)** — must test against producer's real v1.1 manifests; cross-repo coordination is the highest-overhead activity in the milestone.

### Research Flags

**Phases likely needing `/gsd:plan-phase --research-phase <N>` during planning:**
- **Phase 2 (Cinematography Auto-Fill):** The `--analysis-video-mount-mode {container, host-staged}` deployment-time question — shot-timeline runs on host, route expects container-visible paths. Needs deployment-environment research.
- **Phase 3 (Re-ID Registry + HITL Review):** DINOv2 cosine threshold calibration on 《小江湖》-style animation (literature τ≈0.30 is unvalidated on animation); subject-segmentation route shape design (Stage A+B fused vs separate); embedding model choice finalization (DINOv2 vs DINOv2+InsightFace fusion).
- **Phase 5 (Canvas Consumer):** Cross-reference edge density (N×M character↔storyboard `appearance` edges) — may visually clutter; needs canvas-mockup research before committing to edge emission.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Contract v1.1):** v1.0 contract-first pattern is proven; only verification harness extension is mechanical.
- **Phase 4 (Prompt Reference System):** Schema fields already drafted in Phase 1; HTML rendering reuses v1.0 `gen_timeline_html.py` patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every recommended version LIVE-verified on PyPI + in-env; DINOv2 / scikit-learn / httpx all current; consumer Zod already permissive on `assetType`. |
| Features | HIGH for table-stakes shape (grounded in current schemas + real `shot_003.json` route output); MEDIUM for re-id accuracy on animation (no animation-domain benchmarks; SOTA photorealistic numbers are the best available proxy). |
| Architecture | HIGH | All claims LIVE-verified against `run_pipeline.py`, `export_asset.py`, `import-from-dir.ts`, `canvasAssetSchema.ts`, `AssetNode.tsx`, `FlowCanvas.tsx`, real route output sample. Branch states verified. |
| Pitfalls | HIGH for contract / route / canvas pitfalls (directly anchored in repo source); MEDIUM-HIGH for ML pitfalls (CC-ReID literature is mature but animation-domain transfer is uncertain). |

**Overall confidence:** HIGH

### Gaps to Address During Planning / Execution

1. **schema_version "1.1" vs "2" — UNRESOLVED.** See OPEN DECISION above. User must confirm before Phase 1 locks the literal.
2. **DINOv2 cosine threshold τ calibration on animation.** Literature τ≈0.30 is a starting point only. Phase 3 spike must produce an ep01 cosine-distribution histogram (same-person vs different-person) and pick the valley as the threshold; documented in phase SUMMARY.
3. **Crop storage: inline-base64 vs served-path.** FEATURES.md anti-feature flag is external files (`characters/<id>.png` under asset root, listed in `asset.json#media.characters`, served by `scripts/serve.py`). Confirm during Phase 1 schema design — `media.characters` path pattern locks this in.
4. **`prompts.json#scene` field unmapped.** No source in the current `shot-analysis` route output maps to `scene`. Phase 2 implementation must decide: leave empty (route's Qwen3-VL does not currently expose it) OR add a heuristic / defer to a future Qwen-VL extension. Do NOT fabricate.
5. **Registry ID scheme.** `ch_001` (FEATURES.md / PITFALLS.md) vs `char_001` (ARCHITECTURE.md / STACK.md). Pick one in Phase 1 schema `pattern` and lock it — ID immutability is non-negotiable (Pitfall 17).
6. **Review-UI form factor.** HTML (mirror `gen_timeline_html.py`) is the recommended default. Alternative: terminal-based CLI tool. Phase 3 planning should confirm HTML is the deliverable.
7. **`character-reid` route does not yet exist.** Only `shot-analysis` exists today. Phase 3 includes building it (NEW route + driver in kais-aigc-platform).
8. **`feat/shot-geometry-nodes` + `feat/shot-analysis-route` UNMERGED.** Both must merge before Phase 2 end-to-end verification. Roadmap should call this out as a hard external dependency / cross-repo work request.
9. **Interactive vs non-interactive `step_reid`.** Option A (single step, pause for review) vs Option B (three separate steps, off-pipeline review). ARCHITECTURE.md recommends Option A; Phase 3 planning confirms.

---

## Sources

### Primary (HIGH confidence — LIVE-verified source code)
- **Producer repo (read in full):** `run_pipeline.py` (step_* order, caching, --skip-*/--force flags); `scripts/export_asset.py` (asset dict construction, inline validator, required-data guard); `scripts/verify_contract.py` (3-mode harness, SIX_SHAPES L75, self-test, e2e assertions); `spec/schemas/{asset,prompts,frames}.schema.json`; `spec/SPEC.md` (§4 graceful-degrade rule, §6 media conventions); `spec/fixtures/minimal/asset.json`; `.planning/PROJECT.md` (v1.1 scope + constraints); `.planning/RETROSPECTIVE.md` (v1.0 lessons).
- **Consumer repo (read in full from `/data/workspace/kst-canvas-consumer` worktree):** `src/routes/canvas/v2/import-from-dir.ts` (extractShotTimelineArtifacts L943-1140, SHOT_TIMELINE_KNOWN_VERSIONS L898, short-circuit L1320-1354, sequence edges L1110-1128); `src/lib/canvasAssetSchema.ts` (assetDataSchemas L51-119, `assetType` permissive string L82); `packages/infinite-canvas/src/components/nodes/AssetNode.tsx` (typeIcons fallback to 📦 L123, L171); `packages/infinite-canvas/src/components/FlowCanvas.tsx` (nodeTypes registry L55-64).
- **aigc-platform repo:** `src/routes/production/shot-analysis/index.ts` (THIN route body schema L27-35, driver spawn L98-103 w/ 900_000ms timeout); `src/routes/production/shot-analysis/_shared/config.ts`; `scripts/shot-analysis/shot_analysis_driver.py` (ComfyUI workflow L40-109, SEMANTIC_PROMPT template, SAM3Segment config L91-100).
- **Real route output sample:** `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` (confirms near-1:1 mapping to prompts facets).
- **LIVE env probe:** `/usr/bin/python3` 3.12.3 + `pip index versions` for every recommended version (httpx 0.28.1, jsonschema 4.26.0, pillow 12.2.0, transformers 5.14.1, scikit-learn 1.9.0, insightface 1.0.1, onnxruntime-gpu 1.27.0).

### Secondary (MEDIUM-HIGH confidence — academic / industry literature)
- [Gu et al., Clothes-Changing Person Re-ID with RGB Modality Only, CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/papers/Gu_Clothes-Changing_Person_Re-Identification_With_RGB_Modality_Only_CVPR_2022_paper.pdf) — costume-change identity drift is open problem.
- [Cloth-Changing Person Re-identification: A Survey (2024)](https://www.researchgate.net/publication/401226752) — SOTA 60-80% mAP on cloth-changing.
- [Asperti/Naldi/Fiorilla, Investigation of Domain Gap in CLIP-Based Person Re-ID, Sensors 2025](https://www.mdpi.com/1424-8220/25/2/363) — same-domain 73-95% mAP; cross-domain 20-50% mAP; occlusion drops to ~60%.
- [facebook/dinov2-base on Hugging Face](https://huggingface.co/facebook/dinov2-base) — ViT-B/14 self-supervised, 768-d.
- [DINOv2 in HF Transformers (official docs)](https://huggingface.co/docs/transformers/en/model_doc/dinov2) — `AutoModel` + `pooler_output`.
- [Introducing SchemaVer — Snowplow](https://snowplow.io/blog/introducing-schemaver-for-semantic-versioning-of-schemas) — MODEL-REVISION-ADDITION; v1.0's semver-lite is deliberate simplification.
- [InsightFace model zoo & guide](https://www.insightface.ai/guides/choose-face-recognition-model-and-evaluate) — antelopev2/buffalo_l non-commercial research license.
- [Ultralytics SAM3 docs](https://docs.ultralytics.com/models/sam-3) + [Voxel51 / sam3ai.com limitations](https://sam3ai.com/limitations) — SAM3 failure modes on motion blur / occlusion / hair.
- [The Anatomy of a Video Prompt — OCDevel](https://ocdevel.com/podcaster/ai-video-generation/93d9a941-d6ac-437b-bb24-fdf8d7b66571) — 8-slot prompt model convergence across Veo/Sora/Seedance.
- [How to Use Storyboards and Character Sheets — MindStudio](https://www.mindstudio.ai/blog/storyboards-character-sheets-ai-video-generation) — character reference sheet best practices.

### Tertiary (LOW-MEDIUM confidence — emerging practice, needs validation)
- [A Multistage Pipeline for Character-Stable AI Video Stories — arXiv 2512.16954](https://arxiv.org/html/2512.16954v1) — ID-anchored character pipeline pattern.
- User memory `comfyui-primary-node-deploy.md` — comfyui-primary container deploy via kais-incremental aggregator + `docker restart` (NOT compose up).
- User memory `canvas-asset-collection-worktree.md` — v1.0 SHIPPED path; consumer worktree at `/data/workspace/kst-canvas-consumer`.

---
*Research completed: 2026-07-24*
*Ready for requirements / roadmap: yes — after user confirms schema_version `"1.1"` vs `"2"` in OPEN DECISION above.*
