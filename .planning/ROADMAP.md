# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 分镜语义深化** — Phases 5-9 (started 2026-07-24) — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump 1→1.1 + 双端展示

## Phases

<details>
<summary>✅ v1.0 ShotTimelineAsset Contract (Phases 1-4) — SHIPPED 2026-07-20</summary>

A repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection.

- [x] **Phase 1: ShotTimelineAsset Specification** — repo-agnostic contract (6 schemas + version + media refs + manifest) both repos implement against — COMPLETE 2026-07-20
- [x] **Phase 2: shot-timeline Exporter (Producer)** — pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served — COMPLETE 2026-07-20
- [x] **Phase 3: Canvas Consumer** — canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump) — COMPLETE 2026-07-21 *(code in kais-aigc-platform `feat/canvas-asset-collection`)*
- [x] **Phase 4: Cross-Repo Contract Verification** — end-to-end flow + regression protection against schema/media-reference drift — COMPLETE 2026-07-21

**Audit:** 12/12 requirements satisfied, 4/4 phases verified, integration complete — [v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

**Known deferred items (formally accepted):** WR-01/WR-04 (save-v2 secondary-path latent bugs → consumer-repo backlog; primary appendAndSync path unaffected); SC-1 prompt-children scope reduction (prompts/transcript are sidecar data refs, not canvas nodes).

</details>

### 🚧 v1.1 分镜语义深化 (Phases 5-9)

Strict-additive, contract-first minor bump on v1.0. Adds two new pipeline stages calling ML HTTP routes in `kais-aigc-platform` (cinematography analysis + cross-shot re-id), three new optional data files (`characters.json`, `props.json`, enriched `prompts.json`), an HITL review HTML deliverable, and a canvas consumer extension. Mirrors v1.0's contract-first sequencing that worked.

- [x] **Phase 5: Contract v1.1** — schemas + SPEC + fixtures + verify harness (no route dependency) (completed 2026-07-24)
- [x] **Phase 6: Cinematography Auto-Fill (`step_semantic`)** — httpx client + graceful-degrade + per-shot cache (completed 2026-07-24)
- [x] **Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`)** — HIGHEST complexity; new route + driver + review HTML (completed 2026-07-24)
- [x] **Phase 8: Prompt Reference System + shot-timeline HTML Gallery** — narrative continuity + producer-side display (completed 2026-07-24)
- [x] **Phase 9: Canvas Consumer Integration (cross-repo)** — append `"1.1"` + emit character/prop nodes (no renderer / no Zod bump) (completed 2026-07-24)

## Phase Details

### Phase 5: Contract v1.1

**Goal**: Lock the v1.1 contract (schemas + SPEC + fixtures + verify harness) BEFORE any producer code writes against it — so all downstream field names, ID patterns, and the `schema_version: "1.1"` literal are frozen.
**Depends on**: Nothing in v1.1 (v1.0 baseline complete). Mirrors v1.0 Phase 1 contract-first pattern that worked.
**Requirements**: CONTRACT-01, CONTRACT-02, CONTRACT-03, CONTRACT-04, CONTRACT-05, CONTRACT-06, CONTRACT-07, CONTRACT-08, CONTRACT-09
**Success Criteria** (what must be TRUE):

  1. v1 minimal fixture still validates green under v1.1 schema (graceful-degrade promise not broken — Pitfall 11 prevented)
  2. New v1.1 fixture set (`spec/fixtures/v1.1/`) for characters/props/registry/prompts all pass `verify_contract.py EIGHT_SHAPES` validation
  3. Cross-version self-test passes both ways: v1 fixture warns-not-crashes under v1.1-only consumer, AND v1.1 fixture warns-not-crashes under v1-only consumer
  4. Locked literals: `asset.schema.json#schema_version` stays a pattern (NOT `const:"1.1"` — CONTEXT D-XX lock is producer-side); `export_asset.py SCHEMA_VERSION` single-source constant = `1.1`; `characters.schema.json` ID pattern `^char_[0-9]{3}$`; `props.schema.json` ID pattern `^prop_[0-9]{3}$`; all new fields are OPTIONAL (never in `required`)
  5. `SPEC.md` §4 Changelog `1.1` entry + new §5.6/§5.7 document characters/props data shapes and external media convention; `media.characters`/`media.props` path pattern locks external-png-not-base64 decision

**Plans**: 4 plans in 3 waves (mirrors v1.0 Phase 1 contract-first sequencing)

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — 5 schemas (3 new: characters/props/registry; 2 extended additively: prompts/asset) [CONTRACT-01..05]
- [x] 05-02-PLAN.md — export_asset.py SCHEMA_VERSION="1.1" constant + PROJECT.md drift fix (parallel w/ 01) [CONTRACT-06]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-03-PLAN.md — v1.1 fixture set (9 files: 4 reuse + 5 new content) [CONTRACT-01..05 fixtures + CONTRACT-09]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-04-PLAN.md — verify_contract.py EIGHT_SHAPES + _cross_version_check + _fixture_consistency_check + validate.py v1.1 pass + SPEC.md/README.md prose [CONTRACT-07, 08, 09]

### Phase 6: Cinematography Auto-Fill (`step_semantic`)

**Goal**: shot-timeline can call the kais-aigc-platform `shot-analysis` route and merge its cinematography/subject/scene analysis into `prompts.json`, with mandatory graceful-degrade when the route is unreachable (first-ever network dependency in the previously-offline pipeline).
**Depends on**: Phase 5 (enriched `prompts.schema.json` must exist before producer writes to it). **EXTERNAL PREREQUISITE (not REQs, phase-blockers)**: kais-aigc-platform branches `feat/shot-geometry-nodes` + `feat/shot-analysis-route` must merge before end-to-end verification is possible.
**Requirements**: CINEMA-01, CINEMA-02, CINEMA-03, CINEMA-04, CINEMA-05, CINEMA-06
**Success Criteria** (what must be TRUE):

  1. With route reachable, `step_semantic` fills `prompts.json` `camera`/`action`/`lighting`/`style`/`subject` facets from real route output (verified against `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` near-1:1 mapping)
  2. With route down (`--offline` or unreachable host), `prompts.json` still writes schema-valid empty facet strings; asset still exports; `generator.warnings` populated (Pitfall 8 prevented)
  3. Per-shot route output cached at `output/<asset>/route_cache/shot_analysis/shot_XXX.json` with cache key `(video_content_hash, shot_id, route_name, route_version)`; `--skip-semantic` + `--offline` flags both behave correctly
  4. `run_pipeline.py` step counter `[N/8]` updated with `step_semantic` slotted between `step_transcribe` and `step_timeline`
  5. Preflight health check runs before the step; per-shot failure is non-fatal (does not abort the rest of the asset export)

> **Counter lock (CONTEXT D-XX):** Phase 6 uses `[N/7]` (codec[1]/detect[2]/separate[3]/transcribe[4]/semantic[5]/timeline[6]/export[7]). The `[N/8]` literal in CINEMA-02 / criterion #4 is deferred to Phase 7 (inserts `step_reid` at slot 6) to avoid a phantom missing-step gap now.

**Plans**: 3 plans in 3 waves (mirrors Phase 5 contract-first → implementation → integration sequencing)

Plans:
**Wave 1** *(contract-first — unblocks Plans 02/03)*

- [x] 06-01-PLAN.md — asset.schema.json#generator.warnings (optional array<string>) + export_asset.py build_asset_dict(warnings=None) + SPEC §3 row + Changelog Phase 6 bullet + spec/fixtures/v1.1/asset.json warnings example [CINEMA-05]

**Wave 2** *(blocked on Wave 1)*

- [x] 06-02-PLAN.md — analysis/call_shot_analysis.py (httpx sync client + compose_facets LOCKED mapping + video_content_hash + per-shot cache + preflight + warnings sidecar) + 7 captured fixtures copied to examples/shot_analysis/ + README install line [CINEMA-01, CINEMA-03, CINEMA-04, CINEMA-05]

**Wave 3** *(blocked on Waves 1 + 2)*

- [x] 06-03-PLAN.md — run_pipeline.py step_semantic (slots between transcribe + timeline) + 17 [N/6]→[N/7] renumber + 4 new flags (--skip-semantic/--offline/--analysis-url/--analysis-timeout) + --force cache list extension + scripts/verify_phase6_smoke.py 3-scenario regression [CINEMA-02, CINEMA-03, CINEMA-06]

### Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`)

**Goal**: A working cross-shot character/prop registry pipeline with mandatory human-in-the-loop review — `registry.draft.json` → HITL review HTML → `registry.edits.json` → canonical `characters.json` + `props.json` containing only confirmed entries. Highest-complexity phase in v1.1.
**Depends on**: Phase 6 (registry patches `prompts.json` which `step_semantic` enriched; route-side infra pattern proven by `shot-analysis` is reused).
**Requirements**: CAST-01, CAST-02, CAST-03, CAST-04, CAST-05, CAST-06, CAST-07, CAST-08, CAST-09
**Success Criteria** (what must be TRUE):

  1. New `character-reid` route in kais-aigc-platform (SAM3 multi-frame masks → DINOv2 ViT-B/14 embeddings → `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)`) returns `registry.draft.json` with every cluster tagged `review_state: "proposed"`
  2. `html/gen_registry_review.py` produces a usable HITL review HTML — cluster cards with merge/split/rename, cosine-distance-sorted review queue, three-tier threshold visualization (≥0.85 auto-merge / 0.6-0.85 review / <0.6 auto-distinct). FIRST-CLASS deliverable, not an afterthought script
  3. Full flow demonstrable end-to-end: `registry.draft.json` → review HTML → `registry.edits.json` → `registry/apply_edits.py` → canonical `characters.json` + `props.json` containing ONLY `review_state: "confirmed"` entries (Pitfall 7 prevented)
  4. SAM3 multi-frame sampling (N=3-5 per shot at 25/50/75% positions, not just first/last) with `mask_quality` metric; low-quality frames flagged `unusable` and skipped from clustering (Pitfall 6 prevented); best-of-N representative crop auto-selected for `characters/<id>.png`
  5. `step_reid` in `run_pipeline.py` (step 6 of 8) with `--skip-reid` graceful-degrade; DINOv2 cosine threshold τ calibrated on ep01 (planning-phase research spike produces same-person vs different-person cosine histogram + documents the valley pick)

**Plans**: 4 plans in 3 waves (mirrors Phase 5/6 contract-first → implementation → integration)

Plans:
**Wave 1** *(contract-first — unblocks Plans 02/03)*

- [x] 07-01-PLAN.md — spec/schemas/registry-edits.schema.json + spec/fixtures/v1.1/registry.edits.json + spec/validate.py wiring (10th v1.1 shape) [CAST-06, CAST-07 contract layer]

**Wave 2** *(blocked on Wave 1; Plans 02 + 03 parallel)*

- [x] 07-02-PLAN.md — analysis/call_reid.py (httpx client + normalize_clusters + per-video cache + preflight + graceful-degrade + warnings sidecar MERGE — mirror call_shot_analysis.py) [CAST-05, CAST-09 degrade]
- [x] 07-03-PLAN.md — registry/apply_edits.py (confirmed-only hard gate + idempotent apply + ffmpeg representative PNG) + html/gen_registry_review.py (HITL review HTML — first-class: cluster cards + cosine-sorted queue + three-tier viz + Export edits button) [CAST-06, CAST-07, CAST-08 producer fallback]

**Wave 3** *(blocked on Waves 1 + 2)*

- [x] 07-04-PLAN.md — run_pipeline.py step_reid (slot 6 of 8) + 20× [N/7]→[N/8] renumber + 3 new flags + --force cache list; scripts/export_asset.py conditional characters/props emission (CONTRACT-06 closure); scripts/verify_contract.py producer registry↔shots integrity + Pitfall 7 assert; scripts/verify_phase7_smoke.py 5-scenario regression; CAST-01/02/03/04/08 deferral documentation [CAST-09, CONTRACT-06, CAST-01/02/03/04/08 deferred]

**UI hint**: yes

### Phase 8: Prompt Reference System + shot-timeline HTML Gallery

**Goal**: Prompts reference confirmed registry entries by ID (achieving real narrative continuity across shots), the asset carries a frozen `registry_snapshot` for reference stability, and users see a character/prop gallery + reference chips in the shot-timeline HTML.
**Depends on**: Phase 7 (confirmed registry entries are the substrate prompt refs attach to).
**Requirements**: PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04, PRESENT-01, PRESENT-02, PRESENT-03
**Success Criteria** (what must be TRUE):

  1. `prompts.json` post-processed to attach `character_refs[]` / `prop_refs[]` IDs to shots per `characters.json#appearance_shots[]`; `verify_contract.py` cross-file integrity check confirms zero dangling prompt↔registry IDs (Pitfall 17 prevented)
  2. `prompt_text` recomposed referencing characters/props by identity → produces narrative-coherent prompt text consumable by downstream AI video pipelines
  3. `gen_timeline_html.py` extended with: (a) character/prop gallery section rendering external png via `serve.py`; (b) clickable reference chips inside prompt rendering linking back to gallery entries; (c) per-shot "运镜分析填充" chip indicator (green = route filled / gray = offline degraded)
  4. `asset.json` embeds `generator.registry_snapshot` freezing the registry state at export time — later registry mutations cannot invalidate already-exported prompt references (Pitfall 18 prevented)

**Plans**: 3 plans in 3 waves (mirrors Phase 5/6/7 contract-first → producer → integration)

Plans:
**Wave 1** *(contract-first — unblocks Plan 02)*

- [x] 08-01-PLAN.md — asset.schema.json#generator.registry_snapshot (additive optional) + spec/fixtures/v1.1/asset.json example + SPEC.md §3 row + Changelog Phase 8 bullet [PROMPT-04]

**Wave 2** *(blocked on Wave 1)*

- [x] 08-02-PLAN.md — prompts/attach_refs.py (attach refs + deterministic Pattern 2 recompose + idempotent + graceful-degrade) + spec/fixtures/v1.1/prompts.json prompt_text sync + scripts/export_asset.py _build_registry_snapshot conditional emit + scripts/verify_contract.py prompts↔registry integrity (Pitfall 17) [PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04]

**Wave 3** *(blocked on Waves 1 + 2)*

- [x] 08-03-PLAN.md — html/gen_timeline_html.py gallery + ref-chips + semantic-fill indicator + _esc() + JSON-in-script defense (CR-04 carry) + run_pipeline.py step_timeline attach_refs pre-step + mtime cache prompts_json (Pitfall 9, NO [N/9] bump) + scripts/verify_phase8_smoke.py 6-scenario regression [PRESENT-01, PRESENT-02, PRESENT-03]
**UI hint**: yes

### Phase 9: Canvas Consumer Integration (cross-repo)

**Goal**: The `@kais/infinite-canvas` consumer in kais-aigc-platform recognizes v1.1 assets and emits character/prop child nodes by reusing the existing `asset` node type — no custom renderer, no Zod bump, no contract bump on the canvas side.
**Depends on**: Phase 8 (consumer needs real producer-emitted v1.1 manifests to test against). Highest cross-repo coordination cost (~30% measured in v1.0).
**Requirements**: PRESENT-04, PRESENT-05, PRESENT-06
**Success Criteria** (what must be TRUE):

  1. `import-from-dir.ts` `SHOT_TIMELINE_KNOWN_VERSIONS` includes `"1.1"`; `extractShotTimelineArtifacts` emits character/prop child nodes with `type: "asset"` + `assetType: "character"|"prop"`, gated on the new version (Pitfalls 14 + 15 prevented)
  2. Real v1.1 asset imports cleanly → canvas renders character/prop nodes for a producer asset (existing v1 asset still warns-not-crashes — graceful-degrade verified both ways)
  3. `verify-canvas-shot-timeline.ts` extended with v1.1 character/prop node count assertions; 3-mode `verify_contract.py` harness (producer / consumer / e2e) green on v1.1 fixture

**Plans**: 2 plans in 2 waves (Wave 1 = consumer repo PRESENT-04/05 cohesive; Wave 2 = shot-timeline PRESENT-06 contract gate, depends on Wave 1)

Plans:
**Wave 1** *(consumer repo — commits in /data/workspace/kst-canvas-consumer on feat/canvas-asset-collection)*

- [x] 09-01-PLAN.md — consumer v1.1 fixture + import-from-dir.ts gate "1.1" + character/prop node emission via §7 post-process + AssetNode typeIcons + verify-canvas v1.1 assertions + Assert E scoped relaxation [PRESENT-04, PRESENT-05] — COMPLETE 2026-07-24 (consumer @ 90812e9d)

**Wave 2** *(blocked on Wave 1; shot-timeline repo — normal commit flow)*

- [x] 09-02-PLAN.md — verify_contract.py 3-mode green for v1.1 (producer + consumer; e2e deferred) [PRESENT-06]

**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | v1.0 | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | v1.0 | 2/2 | Complete | 2026-07-20 |
| 3. Canvas Consumer | v1.0 | 1/1 | Complete | 2026-07-21 |
| 4. Cross-Repo Contract Verification | v1.0 | 2/2 | Complete | 2026-07-21 |
| 5. Contract v1.1 | v1.1 | 4/4 | Complete    | 2026-07-24 |
| 6. Cinematography Auto-Fill (`step_semantic`) | v1.1 | 3/3 | Complete    | 2026-07-24 |
| 7. Cross-Shot Re-ID Registry + HITL Review (`step_reid`) | v1.1 | 4/4 | Complete    | 2026-07-24 |
| 8. Prompt Reference System + shot-timeline HTML Gallery | v1.1 | 3/3 | Complete    | 2026-07-24 |
| 9. Canvas Consumer Integration (cross-repo) | v1.1 | 2/2 | Complete    | 2026-07-24 |
