# Phase 9: Canvas Consumer Integration (cross-repo) - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — recommended answers auto-accepted (mirrors Phase 5–8 pattern)

<domain>
## Phase Boundary

The `@kais/infinite-canvas` consumer in **kais-aigc-platform** (worktree `/data/workspace/kst-canvas-consumer`, branch `feat/canvas-asset-collection`) recognizes v1.1 ShotTimelineAssets and emits character/prop child nodes by **reusing the existing `asset` node type + AssetNode renderer** — no custom renderer, no Zod bump, no contract bump on the canvas side. The producer-side 3-mode `verify_contract.py` harness (built in v1.0) is confirmed green for v1.1 (producer mode already green from Phase 5–8; consumer mode bridges to the consumer's `verify-canvas-shot-timeline.ts`; e2e mode is heavy/optional).

**Cross-repo split:**
- **Consumer worktree** (`/data/workspace/kst-canvas-consumer`, branch `feat/canvas-asset-collection`): `src/routes/canvas/v2/import-from-dir.ts` (version gate + character/prop node emission); `packages/infinite-canvas/src/components/nodes/AssetNode.tsx` (typeIcons); `scripts/verify-canvas-shot-timeline.ts` (v1.1 assertions); a v1.1 fixture.
- **This repo** (shot-timeline): `scripts/verify_contract.py` (confirm 3-mode harness green for v1.1 — infrastructure already exists from v1.0; may need a v1.1-specific producer assertion if not already covered by Phase 7/8 registry integrity).

**In scope (consumer):** PRESENT-04 (`SHOT_TIMELINE_KNOWN_VERSIONS` += `"1.1"` + `extractShotTimelineArtifacts` emits character/prop child nodes `type:"asset"` + `assetType:"character"|"prop"`); PRESENT-05 (AssetNode `typeIcons` += `character:'🧑'`/`prop:'🔧'` + verify-canvas v1.1 node-count assertions); a v1.1 consumer fixture.
**In scope (shot-timeline):** PRESENT-06 (3-mode verify_contract.py harness green for v1.1).
**Out of scope:** custom canvas renderer (explicitly forbidden); Zod bump (assetType is already `z.string().min(1)`); canvas↔storyboard appearance edges (CANVAS-EDGE-01, v2); cross-video continuity (v2); the deferred Phase 6/7 cross-repo routes (shot-analysis, character-reid — separate branches).

</domain>

<decisions>
## Implementation Decisions

### PRESENT-04 — version gate + character/prop node emission
- **Q1 — `SHOT_TIMELINE_KNOWN_VERSIONS`:** ✅ add `"1.1"` to the Set at `import-from-dir.ts:898` → `new Set(["1", "1.1"])`. This suppresses the graceful-degrade `console.warn` for v1.1 assets (so a clean v1.1 import doesn't warn). v1.0 assets still accepted; unknown/newer versions still warn-not-crash (existing branch at `:948-958` unchanged).
- **Q2 — emission mechanism (THE load-bearing caveat):** ✅ **post-process `tree.artifactNodes` after `buildPhaseTree` returns** (option a). `buildPhaseTree` seeds `assetType = def.assetType` (`"delivery"` for p13) at `:692` and the `extra`-merge guard at `:724` silently drops `extra.assetType` — so pushing `{canvasType:"asset", extra:{assetType:"character"}}` would render as `assetType="delivery"` (WRONG). Instead: push character/prop as `RawArtifact{canvasType:"asset", label:<name>, output_key:<id>}` into the `artifacts` array BEFORE `buildPhaseTree` (so they become asset-type nodes under the p13 tree), THEN post-process the resulting `tree.artifactNodes` to overwrite `data.assetType` to `"character"`/`"prop"` + attach `data.thumbnail` (representative_image) + `data.description` — mirroring the existing post-process at `:1082-1084` (which overwrites `zoneNode.data.label`). This reuses the existing `asset` node type + AssetNode renderer (no custom renderer). Alt (build nodes outside buildPhaseTree + concat at `:1137`) rejected — breaks the zone/phase tree structure; alt (modify buildPhaseTree generic logic) rejected — risk to v1.0.
- **Q3 — gate:** ✅ emit character/prop nodes when the version is known (≥ v1.1 in the Set) AND `manifest.data.characters`/`manifest.data.props` (or `manifest.generator.registry_snapshot`) is present. **Data-presence is the real gate** — a v1.1 asset WITHOUT a registry (graceful-degrade producer) emits no character/prop nodes (clean). Version-string gate just controls the warn.
- **Q4 — data source:** ✅ `manifest.generator.registry_snapshot` preferred (embedded, self-contained — the export-time truth), else read `manifest.data.characters`/`manifest.data.props` files via `tryReadJSON` (mirror the existing data-file loads at `:962-968`). Confirmed-only entries only (the snapshot is already confirmed-only from Phase 8; defense-in-depth: filter `review_state === "confirmed"` if reading the external files).
- **Q5 — node identity:** ✅ character/prop nodes get `id` like `p13-char-<id>`/`p13-prop-<id>` (mirror the existing `p13-<kind>-<n>` id scheme), `label` = the registry `name`, `data.assetType` = `"character"`/`"prop"`, `data.thumbnail` = the representative_image path (served via the existing OSS filePath mechanism — `media.characters[]`/`media.props[]` paths), `data.description` = appearance-shot count or id.

### PRESENT-05 — typeIcons + verify-canvas assertions
- **Q1 — typeIcons (cosmetic):** ✅ add `character: '🧑'`, `prop: '🔧'` to the `typeIcons` map at `AssetNode.tsx:17-19` (currently `{role:'👤', tool:'🔧', scene:'🏞️', clip:'🎬'}`). Additive + safe — the map is `Record<string,string>` with `|| '📦'` fallback; rendering works with no TS change (the `data.assetType as string` cast at `:123,:171` already sidesteps the strict `AssetNodeData.assetType` TS union at `canvas.ts:75`).
- **Q2 — Assert E (additive-only frontend) relaxation:** ✅ the v1.0 invariant `git diff origin/master..HEAD -- packages/infinite-canvas/` is empty (`verify-canvas-shot-timeline.ts:164-178`). PRESENT-05 **intentionally relaxes** this for v1.1 (a cosmetic typeIcons addition is an explicit, sanctioned frontend change). Amend Assert E to: the `packages/infinite-canvas/` diff is **limited to the additive `typeIcons` extension in AssetNode.tsx** (character/prop keys only) — NO new components, NO structural renderer changes, NO custom renderer. This preserves the SPIRIT of Assert E (no custom renderer / no contract bump) while allowing PRESENT-05's cosmetic icons. The amendment is itself additive (the assertion grows a scoped allowlist).
- **Q3 — verify-canvas v1.1 assertions:** ✅ extend `verify-canvas-shot-timeline.ts`: add `const characters = childNodes.filter(n => n.type === "asset" && n.data?.assetType === "character")` (+ `props`) at the classification block (`:84-90`); add count assertions in the Assert A block (`:92-107`) for the v1.1 fixture (e.g. exactly N character nodes + M prop nodes matching the fixture registry). Run against the v1.1 fixture.

### PRESENT-06 — 3-mode verify_contract.py harness green for v1.1
- **Q1 — producer mode:** ✅ already green (Phase 5–8 — asset schema + registry integrity + snapshot). No change expected; confirm.
- **Q2 — consumer mode:** ✅ `verify_contract.py --mode=consumer` shells out to the consumer's `verify-canvas-shot-timeline.ts` (via `npx tsx`, `CANVAS_CONSUMER_PATH`). Green once PRESENT-04/05 + the v1.1 fixture land. No shot-timeline code change (the bridge exists from v1.0).
- **Q3 — e2e mode:** ✅ **heavy** (starts backend, POST import-from-dir, SQL read-back). DEFERRED/skipped via `--e2e-skip` (or `PHASE4_RUN_E2E` unset) — documented as a manual post-merge check, mirroring the Phase 6/7 deferred live-route pattern. The producer + consumer modes are the testable-now gates.

### Cross-repo execution + WIP avoidance
- **Q1 — execution model:** ✅ the consumer edits land in `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`) — the executor commits there (cwd = consumer worktree for those commits). The shot-timeline-side PRESENT-06 work commits in this repo. The `verify_contract.py --mode=consumer` bridges the two via `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer`.
- **Q2 — WIP avoidance:** ✅ the consumer worktree has uncommitted WIP (`scripts/fixtures/shot-timeline-ep01/prompts.json` modified + `action_chains.json` untracked — the user's intentional "action = FULL physical action chain" fixture upgrade). Phase 9 commits ONLY its own files (import-from-dir.ts, AssetNode.tsx, verify-canvas-shot-timeline.ts, the new v1.1 fixture); **never** `git add` prompts.json/action_chains.json. Use explicit `git add <file>` (never `git add -A`/`git add .` in the consumer).

### v1.1 fixture
- **Q1 — fixture location/shape:** ✅ add a NEW minimal v1.1 fixture in the consumer at `scripts/fixtures/shot-timeline-v1.1/` (do NOT disturb the v1.0 `shot-timeline-ep01/` fixture or its WIP). The v1.1 fixture = small asset.json (`schema_version:"1.1"`, `data.characters`/`data.props` + `media.characters[]`/`media.props[]` + `generator.registry_snapshot`) + a `characters.json`/`props.json` + the existing media (reuse shots/video/stems stubs or minimal stand-ins). The verify-canvas-shot-timeline.ts runs its v1.1 assertions against THIS fixture (the v1.0 93-shot assertions stay pinned to the ep01 fixture — run both, or parameterize).

### Claude's Discretion
- Exact character/prop node `id` scheme; exact v1.1 fixture content (keep minimal — 2 characters + 1 prop mirrors the shot-timeline v1.1 fixture); whether verify-canvas runs v1.0 + v1.1 fixtures in one pass or separate (recommend: keep the v1.0 ep01 assertions + add a v1.1 fixture import + assertions in the same script).

</decisions>

<code_context>
## Existing Code Insights (consumer — from the v1.0 map)

### Reusable Assets (consumer)
- `src/routes/canvas/v2/import-from-dir.ts:943-1140` — `extractShotTimelineArtifacts`; the artifacts array + `buildPhaseTree("p13", artifacts)` + the `:1082-1084` zoneNode post-process (the template for the character/prop assetType post-process).
- `import-from-dir.ts:898` — `SHOT_TIMELINE_KNOWN_VERSIONS` (add "1.1").
- `import-from-dir.ts:688-695, 721-728, 833-838` — `buildPhaseTree` artData assembly + extra-merge guard + node.type from canvasType (explains WHY post-process is needed).
- `packages/infinite-canvas/src/components/nodes/AssetNode.tsx:17-19` — typeIcons (add character/prop); `:123,:171` render via `typeIcons[assetType] || '📦'`.
- `packages/infinite-canvas/src/components/FlowCanvas.tsx:55-64` — nodeTypes registry (`asset` → AssetNodeComponent, already wired — no change).
- `src/lib/canvasAssetSchema.ts:82` — `asset.assetType: z.string().min(1)` (permissive — NO Zod bump).
- `scripts/verify-canvas-shot-timeline.ts` — assertions A/E/E2/F + classification at `:84-90` (the v1.1 extension point).

### Reusable Assets (shot-timeline)
- `scripts/verify_contract.py` — the 3-mode harness (`run_producer_check`/`run_consumer_check`/`run_e2e_check`); consumer mode shells out via `CANVAS_CONSUMER_PATH`. Built in v1.0 — confirm green, no rebuild.

### Integration Points
- Consumer: `extractShotTimelineArtifacts` post-process block (new) → `tree.artifactNodes[*].data.assetType` → AssetNode render.
- Bridge: `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer`.

</code_context>

<specifics>
## Specific Ideas

- The Phase 9 v1.0-precedent insight (from the Explore map): the canvas was DESIGNED for this — `asset` node type, permissive assetType Zod, AssetNode typeIcons fallback. v1.1 character/prop nodes are a first-class supported case, not a hack. The only real subtlety is the `buildPhaseTree` assetType-seed + extra-merge-guard (must post-process).
- PRESENT-05's typeIcons change is the ONLY `packages/infinite-canvas/` diff — Assert E's relaxation is narrow and well-scoped.
- The consumer-mode verify is fully testable NOW (no backend needed — it runs the importer function directly via tsx). Only e2e (backend) is heavy/deferred.

</specifics>

<deferred>
## Deferred Ideas

- **e2e mode (PRESENT-06-third-mode)** — heavy (starts backend); deferred/skipped via `--e2e-skip`, documented as manual post-merge (mirrors Phase 6/7 live-route deferral).
- **canvas↔storyboard appearance edges (CANVAS-EDGE-01)** — v2 (needs canvas mockup to assess visual clutter).
- **cross-video character continuity (CROSSVIDEO-01)** — v2.
- **Phase 6/7 cross-repo routes (shot-analysis, character-reid)** — separate unmerged branches; Phase 9 consumer works against the producer-emitted v1.1 manifest regardless of whether those routes are live.

</deferred>
