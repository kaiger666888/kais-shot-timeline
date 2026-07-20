---
phase: 03-canvas-consumer
documented_at: 2026-07-21T00:00:00Z
review_path: .planning/phases/03-canvas-consumer/03-REVIEW.md
status: open
items: 2
---

# Phase 3: Deferred Items (Cross-Repo Consumer Architecture)

**Documented:** 2026-07-21
**Source review:** `.planning/phases/03-canvas-consumer/03-REVIEW.md`
**Consumer repo:** `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`)
**Scope:** Findings flagged by Phase 3 code review that are **out of Phase 3 scope**
because they touch the consumer repo's shared production persistence architecture.
Phase 4 will decide whether to bring the `save-v2` HTTP roundtrip into VERIFY scope.

## Why these are deferred (not fixed in Phase 3)

Both items live in the **consumer repo's `save-v2.ts` HTTP code path** — a
shared production-schema layer used by every canvas full-save call across all
14 phases (P01–P13 + ShotTimelineAsset). Fixing either item requires changing
`FlowLinkV2Schema` (WR-01) or `validateGraphNodes`'s summary-node handling
(WR-04) — both of which are **cross-cutting production schema changes**, not
Phase 3-consumer additive code. The CANVAS-03 invariant for Phase 3 explicitly
locks "no Zod schema loosening in `canvasAssetSchema.ts`" and "no edits to
`packages/infinite-canvas/`"; the same spirit applies to
`flowgraph-v2-schema.ts` (it's the graph-level peer of the asset schema).
Phase 4 (or a dedicated persistence-hardening phase) is the right venue to
decide whether `save-v2` is in VERIFY scope at all.

**Phase 3 import-from-dir path is NOT affected** by either item — it uses
`appendAndSync` → event store → snapshot JSON, none of which Zod-parses the
graph. The deferred bugs only fire on the **secondary** `save-v2` full-save
HTTP path.

---

## WR-01: Sequence edge `data` field silently stripped by `save-v2` Zod parse

**Source:** `03-REVIEW.md` WR-01
**Consumer files:**
- `src/routes/canvas/v2/import-from-dir.ts:1067-1074` (producer emits `data: { linkType: "sequence" }`)
- `src/types/flowgraph-v2-schema.ts:53-61` (`FlowLinkV2Schema` does not declare `data`)
- `src/types/flowgraph-v2.ts:45-53` (`FlowLinkV2` interface does not declare `data`)

**Symptom:**
The Phase 3 producer (`extractShotTimelineArtifacts`) emits sequence edges
shaped like:
```ts
{
  id: `seq-${prevId}-${nextId}`,
  source: prevId, target: nextId,
  branchId: "main",
  dataType: "data",
  data: { linkType: "sequence" },
}
```
But `FlowLinkV2Schema` declares only `{ id, source, target, branchId, dataType,
isExplore?, isInactive? }` — no `data` field. `z.object(...)` defaults to
**strip** unknown keys. When the graph flows through
`save-v2.ts:36` (`FlowGraphV2Schema.safeParse(graph)`), every sequence edge's
`data: { linkType: "sequence" }` is silently discarded. The frontend's
`CanvasEdge.tsx:33` reads `data?.linkType`; after a `save-v2` roundtrip this is
`undefined`, and sequence edges render as plain edges — losing the blue-solid +
arrow styling that `CanvasEdge.tsx:60-75` provides.

**Scope boundary:**
- **Primary path (import-from-dir → `appendAndSync` → event store → snapshot):**
  unaffected. `appendAndSync` does not Zod-parse the graph payload; the `data`
  field survives intact. The Phase 3 verify script
  (`scripts/verify-canvas-shot-timeline.ts`) confirms this — Assert C verifies
  every sequence edge has `data.linkType === "sequence"` and forms a monotonic
  chain.
- **Secondary path (any subsequent full save via `save-v2` HTTP endpoint):**
  latent bug. The first time a user hits "Save" on a canvas that contains a
  ShotTimelineAsset collection, sequence edges silently downgrade to plain
  edges.

**Why deferred:**
Adding `data: z.record(z.string(), z.any()).optional()` to `FlowLinkV2Schema`
(or `data?: Record<string, any>` to the `FlowLinkV2` interface) is technically
additive (no existing strict field is loosened; the new field is optional), but
it touches the **shared production graph schema** used by every canvas full-save
call across all 14 phases. That's a cross-cutting production-schema change
beyond Phase 3's "additive ShotTimelineAsset consumer" mandate. The
CANVAS-03 "no contract bump" spirit applies to `flowgraph-v2-schema.ts` as the
graph-level peer of `canvasAssetSchema.ts`.

**Phase 3 mitigation already in place:**
- Inline comment at `import-from-dir.ts` sequence-edge block (added by
  `fix(03): WR-05 + WR-06 ...`) now accurately documents the
  `save-v2`-strips-`data` caveat so future maintainers see the gap.
- The `as FlowLinkV2` cast that previously masked the type gap (WR-06) has
  been replaced with a local typed extension `SequenceLink = FlowLinkV2 & {
  data?: ... }`, making the field visible to TS at the construction site and
  documenting the interface gap.

**Phase 4 decision needed:**
1. Add `data?: Record<string, any>` to `FlowLinkV2` interface and
   `FlowLinkV2Schema` (additive optional — recommended by reviewer).
2. OR: explicitly document that sequence edges are import-from-dir-only and
   not supported on the `save-v2` persistence path.
3. Then: extend `verify-canvas-shot-timeline.ts` to round-trip the produced
   graph through `FlowGraphV2Schema.safeParse` and assert `data?.linkType`
   survives — closing the verify-loophole.

---

## WR-04: `sum-p13` summary node is Zod-rejectable by `save-v2` (pre-existing pattern, Phase 3 expands blast radius)

**Source:** `03-REVIEW.md` WR-04
**Consumer files:**
- `src/routes/canvas/v2/import-from-dir.ts:1043` (calls `buildPhaseTree("p13", ...)`)
- `src/lib/canvasAssetSchema.ts:122-158` (`structuralTypes` does not include summary pseudo-type)

**Symptom:**
`buildPhaseTree` always emits a summary node (`sum-p13` for Phase 3) whose
`.type` is the phase's `canvasType` (`"video"` for P13). The summary's `data`
is structural (`{label, description, assetType, state, tags}`) — it carries no
media fields. The production validator `validateNodeData`
(`canvasAssetSchema.ts:133`) looks up `assetDataSchemas["video"]` and rejects
(missing `filePath/shot_id/engine/duration_sec/resolution`).

This is a **pre-existing pattern** — every phase's summary node
(`sum-p01` through `sum-p13`) has the same shape and would be rejected by
`validateGraphNodes`. The SUMMARY (Phase 3 plan summary) acknowledges this:
"save-v2.ts 调用 validateGraphNodes 时,既有 p10/p11/p12/p13 summary 节点同样
会因 .type='video'/'audio' 而 Zod reject —— 这是 pre-existing issue,与本
phase 无关 (scope boundary)."

**Phase 3 expands the blast radius:**
Previously `sum-p13` only appeared if P13 was active in a 13-phase pipeline.
Now **every** ShotTimelineAsset import adds a `sum-p13` node with
`type: "video"`. Any canvas that imports ShotTimelineAsset and then goes
through `save-v2` will hit the reject — whereas before, only canvases with
active P13 would.

**Scope boundary:**
- **Primary path (import-from-dir → `appendAndSync` → event store → snapshot):**
  unaffected. `appendAndSync` does not call `validateGraphNodes`. The Phase 3
  verify script confirms structural correctness — it filters `sum-` prefixed
  nodes out before calling `validateGraphNodes` (matching the plan SC "全部子节点
  通过 validateGraphNodes" intent — child nodes, not structural parents).
- **Secondary path (any subsequent full save via `save-v2` HTTP endpoint):**
  latent bug. `save-v2.ts:49` calls `validateGraphNodes` on the full node list
  **without** the `sum-` filter the verify harness uses. Result: HTTP 400
  "资产节点结构化参数校验失败" with errors citing `sum-p13` first.

**Why deferred:**
The fix touches production `save-v2.ts:49` (the call site) — either filter
zone+summary out at the production call site (matches verify-harness behavior)
or change `structuralTypes` (`canvasAssetSchema.ts:122`) to include a "summary"
pseudo-type detected by `id.startsWith("sum-")`. Both are **production call-site
changes** beyond Phase 3's mandate. The pre-existing nature (every summary node
since P01 has the same shape) means Phase 3 is not introducing the bug, only
increasing its trigger frequency.

**Phase 3 mitigation already in place:**
- The Phase 3 verify script filters `sum-` prefixed nodes before
  `validateGraphNodes` (matching plan SC intent) so the verify harness correctly
  validates only the media-bearing children. Assert D confirms 0 errors on
  `childNodes` (storyboards + audio + video).
- This deferred-items.md entry documents that the `sum-p13` summary node is a
  known rejectable shape on `save-v2`, inherited from the pre-existing pattern.

**Phase 4 decision needed:**
1. Filter zone+summary out of `validateGraphNodes` at the production call site
   in `save-v2.ts:49` (matches verify-harness behavior).
2. OR: change `structuralTypes` to include a "summary" pseudo-type and detect
   by `id.startsWith("sum-")` (introduces ID-shape coupling — less clean).
3. OR: change `buildPhaseTree` to emit summary nodes with a dedicated
   structural type instead of inheriting the phase's `canvasType`.
4. Then: add a verify-harness assert that runs the FULL node list (no `sum-`
   filter) through `FlowGraphV2Schema.safeParse` to catch the production-path
   reject.

---

## Cross-references

- **Phase 3 SUMMARY:** `.planning/phases/03-canvas-consumer/03-01-SUMMARY.md`
  (acknowledges pre-existing summary-node reject as scope boundary; this file
  extends that scope-boundary acknowledgment to WR-01's sequence-edge `data`
  strip).
- **Phase 3 REVIEW:** `.planning/phases/03-canvas-consumer/03-REVIEW.md`
  (WR-01 §37-65, WR-04 §134-148).
- **Consumer repo fixes applied in Phase 3:** WR-02, WR-03, WR-05, WR-06,
  WR-07, WR-08 (commits `788fc6d2`, `368de27d`, `061154d1`, `ce0e41cc`,
  `bb3eaaf4` on branch `feat/canvas-asset-collection`).

---

_Documented: 2026-07-21_
_Author: Claude (gsd-code-fixer)_
_Phase: 03-canvas-consumer_
_Status: open — Phase 4 to triage_
