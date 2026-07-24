# Phase 9 — Research: Canvas Consumer v1.0 Integration Map

> This RESEARCH.md distills a read-only Explore map of the kais-aigc-platform canvas consumer's v1.0 ShotTimelineAsset integration (worktree `/data/workspace/kst-canvas-consumer`, branch `feat/canvas-asset-collection`). All file:line citations are current as of 2026-07-25. The map IS the research — Phase 9's implementation is a surgical v1.1 extension of these exact hooks.

## 1. Version gate — `SHOT_TIMELINE_KNOWN_VERSIONS`

**File:** `src/routes/canvas/v2/import-from-dir.ts:898`
```ts
const SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"]);
```
**Graceful-degrade** (`:948-958`): unknown/newer version → `console.warn` + render known fields (warn-not-crash; no throw/return). **v1.1 action:** add `"1.1"` to the Set.

## 2. `extractShotTimelineArtifacts` (`:943-1140`)

**Signature:** `extractShotTimelineArtifacts(manifest, workdir, manifestPath) → {nodes, links}`.
**Reads:** `manifest.data.{shots,audio_analysis,transcript,frames,prompts}` (`:962-968`, parallel `tryReadJSON`), `manifest.media.video` + `stems.{vocals,drums,other}`, `manifest.source.{duration_sec,video_filename}`. **Does NOT read** `data.characters`/`data.props`/`generator.registry_snapshot` (zero grep hits).
**Emits (v1.0):** storyboard×N + audio×3 + video×1, all via one `buildPhaseTree("p13", artifacts)` at `:1075`.
**v1.1 hook:** push character/prop `RawArtifact{canvasType:"asset", label, output_key}` into `artifacts` BEFORE `:1075`, THEN post-process (see §7 caveat).

## 3. `AssetNode.tsx` typeIcons (`:17-19`)
```ts
const typeIcons: Record<string, string> = { role: '👤', tool: '🔧', scene: '🏞️', clip: '🎬' };
```
`character`/`prop` absent (📦 fallback). Render at `:123,:171` via `typeIcons[data.assetType as string] || '📦'`. **v1.1 action:** add `character:'🧑'`, `prop:'🔧'` (additive; `as string` cast already sidesteps the strict TS union at `canvas.ts:75`).

## 4. `verify-canvas-shot-timeline.ts`
Run: `npx tsx scripts/verify-canvas-shot-timeline.ts` (no npm alias). Asserts: A structure (1 zone/1 summary/3 audio/1 video/93 storyboard), B/C seq edges, D Zod on childNodes, **E additive-only frontend** (`git diff origin/master..HEAD -- packages/infinite-canvas/` empty, `:164-178`), E2 additive-only Zod, F roundtrip, F2 OSS filePath. **v1.1 hook:** classification at `:84-90` (add `characters`/`props` filters) + count assertions in Assert A.

## 5. Fixture `scripts/fixtures/shot-timeline-ep01/`
v1.0: `asset.json` schema_version `"1"`, NO characters/props/snapshot. **WIP (uncommitted, user's intentional action-chain upgrade — DO NOT TOUCH):** `prompts.json` modified, `action_chains.json` untracked. **v1.1 action:** add a NEW minimal fixture `scripts/fixtures/shot-timeline-v1.1/` (don't disturb ep01).

## 6. Zod — assetType is permissive (`src/lib/canvasAssetSchema.ts:82`)
`asset.assetType: z.string().min(1, "asset node requires assetType (character|scene|prop)")` — **NOT `z.enum`**. Adding `assetType:"character"`/`"prop"` needs **NO Zod bump** (Assert E2 counts `.optional()`/`.nullable()`, unaffected). asset.json itself is parsed as `any` (never Zod-validated on the import path).

## 7. Node assetType trace — THE load-bearing caveat
`buildPhaseTree` seeds `artData.assetType = def.assetType` (`"delivery"` for p13) at `:692`, then the extra-merge guard `if (!(k in artData))` at `:724` **silently drops** `extra.assetType`. So `{canvasType:"asset", extra:{assetType:"character"}}` renders as `assetType="delivery"` (WRONG). **v1.1 fix:** post-process `tree.artifactNodes[*].data.assetType` AFTER `buildPhaseTree` returns (mirror the `:1082-1084` zoneNode post-process) to set `"character"`/`"prop"` + thumbnail + description. `node.type="asset"` → AssetNodeComponent (`FlowCanvas.tsx:58`) → renders via existing AssetNode. **No custom renderer.**

## Pitfalls (Phase 9-specific)
- **P14 (version gate):** adding "1.1" to KNOWN_VERSIONS prevents the graceful-degrade warn for clean v1.1 imports (else every v1.1 asset warns).
- **P15 (assetType seed):** the buildPhaseTree extra-merge guard — must post-process, not pass via extra.
- **Assert E relaxation:** v1.0 "no frontend change" invariant is INTENTIONALLY relaxed for v1.1's cosmetic typeIcons (PRESENT-05 explicit); amend Assert E to a scoped allowlist (typeIcons additions only).
- **Cross-repo WIP:** never `git add -A` in the consumer (prompts.json/action_chains.json WIP); explicit file adds only.

## Open Questions (RESOLVED)
- **Q1 emission mechanism** — RESOLVED: post-process tree.artifactNodes (§7).
- **Q2 data source** — RESOLVED: registry_snapshot preferred, else data.characters/props files (CONTEXT Q4).
- **Q3 Assert E** — RESOLVED: scoped allowlist relaxation (CONTEXT PRESENT-05 Q2).
- **Q4 e2e** — RESOLVED: deferred/--e2e-skip (CONTEXT PRESENT-06 Q3).

## Validation Architecture

> Nyquist enabled; repo (consumer) has its own verify script (`verify-canvas-shot-timeline.ts`, run via `npx tsx`). Shot-timeline's `verify_contract.py` 3-mode harness bridges. pytest-free on both sides.

### Test Map
| Req | Behavior | Test | Command |
|-----|----------|------|---------|
| PRESENT-04 (gate) | v1.1 asset imports without warn | consumer verify | `npx tsx scripts/verify-canvas-shot-timeline.ts` (v1.1 fixture) |
| PRESENT-04 (emit) | character/prop nodes appear type:"asset" + assetType:"character"/"prop" (NOT "delivery") | consumer verify count + assetType assert | same |
| PRESENT-05 (typeIcons) | AssetNode renders 🧑/🔧 (diff limited to typeIcons) | Assert E relaxed + grep | same + `git diff origin/master..HEAD -- packages/infinite-canvas/` scoped |
| PRESENT-06 (producer) | shot-timeline producer green for v1.1 | `python3 scripts/verify_contract.py --mode=producer` | exit 0 |
| PRESENT-06 (consumer) | bridge green | `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer` | exit 0 |
| PRESENT-06 (e2e) | heavy | DEFERRED (`--e2e-skip`) | manual post-merge |

### Manual-Only
| Behavior | Why | Instructions |
|----------|-----|--------------|
| e2e (backend round-trip) | heavy: starts backend, POST import-from-dir, SQL read-back | Post-merge: `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` |

**No DEFERRED-blocking humans on the producer/consumer modes** — both testable now (consumer verify runs the importer directly via tsx, no backend). Only e2e is heavy/deferred.

## RESEARCH COMPLETE
