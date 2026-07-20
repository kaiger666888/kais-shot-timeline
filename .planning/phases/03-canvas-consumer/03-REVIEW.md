---
phase: 03-canvas-consumer
reviewed: 2026-07-21T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts
  - /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts
findings:
  critical: 0
  warning: 8
  info: 5
  total: 13
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-21
**Depth:** standard
**Repo reviewed:** `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`, diff base `origin/master`)
**Files Reviewed:** 2 (`src/routes/canvas/v2/import-from-dir.ts`, `scripts/verify-canvas-shot-timeline.ts`)
**Status:** issues_found

## Summary

The Phase 3 ShotTimelineAsset importer is competently built and largely additive as claimed. The `buildPhaseTree` L823 `?? def.canvasType` override is genuinely behavior-preserving for existing 13-phase callers (verified by tracing every call site). The 17 verify asserts exercise the production `extractShotTimelineArtifacts` helper and confirm structural / sequence-edge / per-type-Zod invariants for the producer's golden fixture.

However, the review surfaced **a contract gap between the producer's link shape and the consumer's Zod schema** that silently strips the `linkType: "sequence"` payload on the `save-v2` HTTP path (the import path itself is unaffected because `appendAndSync` does not Zod-parse). The SUMMARY acknowledges a *separate* pre-existing `save-v2` issue (summary-node Zod reject) but does NOT acknowledge this one. Several other latent robustness gaps also ride on the same `save-v2` code path: `sourceDuration === 0` from a malformed manifest rejects all 4 media children; the new `sum-p13` adds blast radius to that pre-existing summary-node reject; and a mixed workdir (ShotTimelineAsset + 13-phase files) silently drops the 13-phase data via an unconditional short-circuit.

The verify script is meaningful (not tautological) but has its own gaps: it does not set the `_workdirToOss` global that production sets, so derived `filePath` values differ from production; its `git diff` / `git show` additive-only guards pass vacuously if `origin/master` is missing; and its sequence-edge shape check filters by `data?.linkType === "sequence"` but never byte-compares against `flowDataMapper.ts:163-172` (the shapes actually differ in `dataType` placement, contradicting the SUMMARY's "byte-match" claim).

All findings are WARNING-or-below; none block the import-from-dir path itself. The BLOCKER-tier risks are confined to the cross-endpoint `save-v2` roundtrip, which Phase 3 explicitly defers ("Phase 4 如果走 save-v2.ts HTTP 路径可能触发").

## Warnings

### WR-01: Sequence edge `data` field is silently stripped by `save-v2` Zod parse — feature degrades after any full save

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1067-1074` (producer) and `/data/workspace/kst-canvas-consumer/src/types/flowgraph-v2-schema.ts:53-61` (schema)
**Issue:**
The producer emits sequence edges with a nested `data` field:
```ts
{
  id: `seq-${sbNodes[i - 1].id}-${sbNodes[i].id}`,
  source: sbNodes[i - 1].id,
  target: sbNodes[i].id,
  branchId: "main",
  dataType: "data",
  data: { linkType: "sequence" },
} as FlowLinkV2
```
But `FlowLinkV2Schema` (flowgraph-v2-schema.ts:53-61) declares only `{ id, source, target, branchId, dataType, isExplore?, isInactive? }` — no `data` field. `z.object(...)` defaults to **strip** unknown keys, so when the graph flows through `save-v2.ts:36` (`FlowGraphV2Schema.safeParse(graph)`), every sequence edge's `data: { linkType: "sequence" }` is silently discarded. The frontend's `CanvasEdge.tsx:33` reads `data?.linkType`; after a `save-v2` roundtrip this is `undefined`, and sequence edges render as plain edges (losing the blue solid + arrow styling that `CanvasEdge.tsx:60-75` provides).

The import-from-dir path itself does NOT trigger this (it uses `appendAndSync` → event store → snapshot JSON, none of which Zod-parses). But any subsequent full save via the `save-v2` endpoint will silently break the visual feature. The producer also requires `as FlowLinkV2` to compile (see WR-05), which masked this gap during type-check.

The verify script does NOT catch this because it calls `extractShotTimelineArtifacts` directly and never runs the result through `FlowGraphV2Schema.safeParse`.

**Fix (choose one):**
1. Add `data: z.record(z.string(), z.any()).optional()` to `FlowLinkV2Schema`. This is technically a schema change but is *additive* (loosens nothing; previously-unknown key becomes a known optional). Maintains the CANVAS-03 "no strictness loosening" invariant in spirit (the new field is optional, existing strict fields unchanged).
2. Or: emit `linkType` as a top-level field on the link (would require frontend + schema coordination — more invasive).
3. Or: document explicitly that sequence edges are not supported on the `save-v2` persistence path and the feature is import-from-dir-only.

Recommended: option 1, plus extend the verify script to round-trip the produced graph through `FlowGraphV2Schema.safeParse` and assert `data?.linkType` survives.

---

### WR-02: `scanWorkdirForArtifacts` unconditional short-circuit silently drops 13-phase data when `asset.json` is present

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1269-1281`
**Issue:**
```ts
const manifestProbe = await tryReadJSON(assetManifestPath);
if (manifestProbe && manifestProbe.asset_type === "shottimeline") {
  phaseArtifacts.set(SHOT_TIMELINE_SENTINEL_KEY, [...]);
  return phaseArtifacts;  // ← hard early-return
}
```
Any workdir that legitimately contains BOTH a `ShotTimelineAsset` AND conventional 13-phase files (`p02_outline.json`, `output/*.mp4`, `assets/scene_images/*`, etc.) will have the 13-phase data **silently ignored**. No warning is logged. The user sees only the ShotTimelineAsset collection on the canvas, with no signal that their existing pipeline outputs were dropped.

This is a plausible migration scenario (e.g., a user drops a ShotTimelineAsset into an existing 13-phase workdir, or a future pipeline emits both). The early-return is unconditional — not a merge.

The reverse direction is also a concern: if a producer's `asset.json` happens to land in a workdir with other phase files for a legitimate reason (e.g., the producer writes sibling manifests), those sibling files become invisible to the canvas.

**Fix:** Either (a) drop the early-return and instead set the sentinel alongside normal scan results (the existing file→phase scanner won't pick up `shots.json` / `audio_analysis.json` / etc. because they don't match `p0X` prefixes), or (b) keep the short-circuit but emit a `console.warn` listing the ignored phase files so the operator can see what was dropped.

```ts
// Option (b) — minimal-change warn
if (manifestProbe && manifestProbe.asset_type === "shottimeline") {
  const others = (await readdir(workdir).catch(() => [])).filter(f =>
    f.endsWith(".json") && f !== "asset.json" && findPhaseFromFile(f));
  if (others.length > 0) {
    console.warn(`[v2/import] ShotTimelineAsset detected at ${assetManifestPath}; ` +
      `ignoring ${others.length} co-located phase file(s): ${others.join(", ")}`);
  }
  phaseArtifacts.set(SHOT_TIMELINE_SENTINEL_KEY, [...]);
  return phaseArtifacts;
}
```

---

### WR-03: `sourceDuration === 0` from malformed manifest makes all audio + video children fail per-type Zod

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:959, 1014-1037`
**Issue:**
```ts
const sourceDuration = Number(manifest?.source?.duration_sec ?? 0) || 0;
// ...
// audio:
extra: { ..., duration_sec: sourceDuration, ... }
// video:
extra: { ..., duration_sec: sourceDuration, ... }
```
The Zod schemas require `duration_sec: z.number().positive(...)` for both `audio` (`canvasAssetSchema.ts:57`) and `video` (`canvasAssetSchema.ts:68`). If the manifest lacks `source.duration_sec` (or it is `0`, `null`, `""`, or non-numeric), `sourceDuration === 0`, and:
- The `EXPECTED_PARAM_FIELDS_BY_TYPE` *warn* at L755 does **not** fire (because `0 == null` is `false` and `0 === ""` is `false`), so `__incomplete` is not stamped — no signal.
- The per-type Zod at `save-v2.ts:49` **rejects** all 3 audio + 1 video nodes with HTTP 400.

Result: import succeeds silently (no warn, no incomplete flag), but the next `save-v2` call rejects with "资产节点结构化参数校验失败". The user sees an apparently-working canvas that fails on save.

**Fix:**
```ts
const sourceDuration = Number(manifest?.source?.duration_sec) || 0;
if (!(sourceDuration > 0)) {
  console.warn(
    `[v2/import] ShotTimelineAsset manifest missing/invalid source.duration_sec ` +
    `(${manifestPath}); audio/video children will fail Zod validation on save-v2.`,
  );
}
```
Optionally also clamp to a small positive sentinel (`0.001`) so the import survives `save-v2`, with the warn providing the audit trail.

---

### WR-04: Phase 3 expands the blast radius of the pre-existing `save-v2` summary-node Zod-reject bug

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1043` (calls `buildPhaseTree("p13", ...)`); `/data/workspace/kst-canvas-consumer/src/lib/canvasAssetSchema.ts:122-158`
**Issue:**
`buildPhaseTree` always emits a summary node whose `.type` is `def.canvasType` (for `p13`, `"video"`). The summary's `data` is structural (`{label, description, assetType, state, tags}`) — it carries no media fields. The production validator `validateNodeData` (`canvasAssetSchema.ts:133`) looks up `assetDataSchemas["video"]` and rejects (missing `filePath/shot_id/engine/duration_sec/resolution`).

The SUMMARY acknowledges this as a pre-existing issue (lines 153, 269): "save-v2.ts 调用 validateGraphNodes 时,既有 p10/p11/p12/p13 summary 节点同样会因 .type='video'/'audio' 而 Zod reject —— 这是 pre-existing issue,与本 phase 无关 (scope boundary)。"

But Phase 3 **expands the blast radius**: previously `sum-p13` only appeared if P13 was active in a 13-phase pipeline. Now **every** ShotTimelineAsset import adds a `sum-p13` node with `type: "video"`. Any canvas that imports ShotTimelineAsset and then goes through `save-v2` will hit the reject — whereas before, only canvases with active P13 would. The verify script sidesteps this by filtering `childNodes` (excluding `sum-` prefix) before calling `validateGraphNodes`, which is a test-harness-only filter; production `save-v2.ts:49` does NOT filter.

This is not a new bug, but it is a meaningful regression in the *frequency* of the latent failure mode, and the SUMMARY's framing ("pre-existing, not our problem") understates the impact.

**Fix:** Either (a) fix the pre-existing bug in a follow-up (filter zone+summary out of `validateGraphNodes` at the production call site, or change `structuralTypes` to include a "summary" pseudo-type and detect by `id.startsWith("sum-")` — though the latter introduces an ID-shape coupling), or (b) explicitly document in `extractShotTimelineArtifacts` that the produced graph is not `save-v2`-safe and add a runtime assertion / warn in the importer so operators see the limitation.

---

### WR-05: Sequence edge shape does NOT byte-match `flowDataMapper.ts:163-172` (SUMMARY claim is inaccurate)

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1054-1075`; frontend precedent `/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/utils/flowDataMapper.ts:163-172`
**Issue:**
The SUMMARY and inline comment at L1055 claim "shape 字面匹配 flowDataMapper.ts:163-172". They don't match:

Frontend (`flowDataMapper.ts:163-172`):
```ts
edges.push({
  id: `seq-${edgeId++}`,
  source: prevNodeId,
  target: nodeId,
  data: { dataType: 'data', linkType: 'sequence' },  // ← BOTH fields nested in data
})
```

Phase 3 backend (L1067-1074):
```ts
{
  id: `seq-${...}`,
  source: sbNodes[i - 1].id,
  target: sbNodes[i].id,
  branchId: "main",                                  // ← frontend omits
  dataType: "data",                                  // ← TOP LEVEL, not nested
  data: { linkType: "sequence" },                    // ← only linkType nested
}
```

Three concrete differences:
1. `branchId` present in backend, absent in frontend precedent.
2. `dataType` is top-level in backend, nested inside `data` in frontend precedent.
3. Backend `data` contains only `linkType`; frontend `data` contains both `dataType` and `linkType`.

Rendering still works because `CanvasEdge.tsx:33` only reads `data?.linkType` — both shapes produce the same value for that field. But the byte-match claim is false, and any future frontend code that reads `data.dataType` (or any code that assumes the frontend precedent shape) will silently miss data.

**Fix:** Either (a) update the comment to "matches frontend rendering intent (`data.linkType === 'sequence'`), shape differs from `flowDataMapper.ts` in `dataType` placement" so future maintainers aren't misled, or (b) align the backend shape with the frontend precedent by moving `dataType` inside `data` (would require `as FlowLinkV2` cast to already-noted missing `data` field — see WR-01/WR-06).

---

### WR-06: `as FlowLinkV2` cast masks TypeScript type gap (the producer emits a field not in the interface)

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1074`
**Issue:**
```ts
data: { linkType: "sequence" },
} as FlowLinkV2);
```
The cast is load-bearing because `FlowLinkV2` (`flowgraph-v2.ts:45-53`) does not declare a `data?: Record<string, any>` field. The runtime object has the field; the type does not. Downstream consumers typed as `FlowLinkV2` will not see `data` via autocomplete or compile-time checks, and any future refactor that drops the cast (or refactors around the typed shape) will silently break the feature. This is the type-level manifestation of WR-01.

The frontend already has the analogous field: `CanvasEdge.tsx:8-15` declares `EdgeData` with `dataType`, `linkType`, `refType`, etc. — the backend `FlowLinkV2` interface is simply out of sync with what the renderer expects.

**Fix:** Update `FlowLinkV2` (and `FlowLinkV2Schema`) to declare `data?: Record<string, any>` so the cast becomes unnecessary and the type system can catch real shape drift. (This is the same fix as WR-01 option 1.)

---

### WR-07: Verify script does not set `_workdirToOss` global — runs with non-production-realistic `filePath` values

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:58-59`
**Issue:**
`extractShotTimelineArtifacts` internally calls `fsToOssUrl(stemAbs)`, which depends on the module-level `_workdirToOss` global. In production this is set by `scanAndBuildTree` at L1508: `_workdirToOss = { workdir, ossPrefix: \`/oss/${workdirBase}\` }`. The verify script calls `extractShotTimelineArtifacts` directly without setting this global, so `_workdirToOss === null` during the verify run, and `fsToOssUrl` falls through every branch (workdir is `/data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-ep01`, not under `/data/workspace/kais-aigc-platform/data/oss`).

Result: verify-harness `filePath` values are raw absolute paths (`/data/workspace/.../stems/vocals.wav`); production `filePath` values would be `/oss/shot-timeline-ep01/stems/vocals.wav`. The verify script makes no assertions on `filePath`, so it doesn't fail — but it also doesn't actually exercise the production-realistic URL synthesis path. A bug in `fsToOssUrl`'s workdir-prefix branch would not be caught.

**Fix:**
```ts
// At top of main(), before extractShotTimelineArtifacts:
import {  } from "../src/routes/canvas/v2/import-from-dir";
// _workdirToOss is not exported — either export a setter from the production module
// or invoke via scanAndBuildTree(FIXTURE) to drive the realistic code path.
```
The cleanest fix is to have the verify script drive `scanAndBuildTree` end-to-end (so it exercises sentinel detection + global setup + helper invocation), rather than calling the helper in isolation.

---

### WR-08: Verify script's additive-only Zod-strictness guard passes vacuously when `origin/master` is missing

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:171-196`
**Issue:**
```ts
let masterOpt = -1, headOpt = -1, masterNull = -1, headNull = -1;
let schemaDiffStatus = "";
try {
  const masterSrc = execSync("git show origin/master:src/lib/canvasAssetSchema.ts", ...);
  const headSrc = fs.readFileSync(...);
  masterOpt = (masterSrc.match(/\.optional\(\)/g) || []).length;
  headOpt = (headSrc.match(/\.optional\(\)/g) || []).length;
  // ...
} catch (err) {
  schemaDiffStatus = `(compare failed: ${(err as Error).message})`;
}
assert(
  headOpt <= masterOpt && headNull <= masterNull,  // -1 <= -1 && -1 <= -1 → true
  ...
);
```
If `origin/master` ref is missing (fresh shallow clone, CI environment without `--fetch-depth=full`, detached-HEAD builder), `execSync` throws → all four counters stay at `-1` → the assertion condition `headOpt <= masterOpt && headNull <= masterNull` evaluates to `true` (`-1 <= -1`) → **the additive-only invariant PASSES VACUOUSLY**. The detail string does say "(compare failed: ...)" but the assertion itself is recorded as PASS and the script exits 0.

The same defect affects Assert E at L154-169 (`git diff --name-only origin/master..HEAD -- packages/infinite-canvas/`): on `origin/master` missing, the catch sets `treeDiff = "(git diff failed: ...)"`, and the assertion `treeDiff === ""` is FALSE → that one correctly fails. So Assert E is robust but Assert E2 is not — inconsistent.

Additionally, the count-based check has a semantic loophole: changing `z.string().min(1)` to `z.string()` (loosening min-length strictness) changes neither `.optional()` nor `.nullable()` count, so it would not be detected.

**Fix:**
```ts
let schemaCompareOk: boolean | null = null;  // null = couldn't compare
try {
  // ...
  schemaCompareOk = headOpt <= masterOpt && headNull <= masterNull;
} catch (err) {
  schemaDiffStatus = `(compare failed: ...)`;
}
assert(
  schemaCompareOk === true,  // fails if null (couldn't compare) or false (regression)
  "CANVAS-03 additive-only: canvasAssetSchema.ts strictness preserved",
  schemaDiffStatus || `.optional() master=${masterOpt} head=${headOpt}; ...`,
);
```

---

## Info

### IN-01: Misleading defense-in-depth comment about path-traversal protection

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1266-1268`
**Issue:**
The comment claims: "consumer 侧 tryReadJSON + join 不跨 workdir." This is incorrect. Node's `path.join(workdir, "/etc/passwd")` returns `"/etc/passwd"` (any absolute argument resets the join). The producer's regex `^(?!.*\.\.)` blocks `..` but not absolute paths. A tampered `asset.json` with `media.stems.vocals: "/etc/passwd"` would propagate `/etc/passwd` as the literal `filePath` string in the audio node's data. No file *content* is leaked (no read is attempted on the media path; `fsToOssUrl` just returns null for non-mapped paths), but the path string is exposed via the canvas.

Severity is low (producer is trusted, attacker would need write access to the workdir). The comment overstates the protection.

**Fix:** Either fix the comment ("consumer trusts the producer's paths; defense is at the producer schema"), or add consumer-side validation: `if (path.isAbsolute(rel)) throw new Error("manifest path must be relative: " + rel);`

---

### IN-02: `probeResolution` silently degrades to `"0x0"` with no warn

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:895-911`
**Issue:**
When ffprobe fails (binary missing, video unreadable, timeout), the catch returns `"0x0"` with no log. The Zod (`z.string().min(1)`) accepts `"0x0"`, so the import "succeeds" but the video node carries a meaningless resolution that the frontend will render verbatim. Operators have no signal that the synthesis failed. The inline comment at L890-894 explains the fallback choice but doesn't justify the silence.

**Fix:**
```ts
} catch (err) {
  console.warn(`[v2/import] ffprobe failed for ${videoPath}: ${(err as Error).message}; using "0x0"`);
  return "0x0";
}
```

---

### IN-03: Hardcoded 3-stem set couples consumer to Demucs `htdemucs` configuration

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1005`
**Issue:**
```ts
for (const stem of ["vocals", "drums", "other"] as const) {
```
This skips `bass` (which Demucs `htdemucs` *does* emit — see project CLAUDE.md "Demucs 4-stem source separation"). The producer's `stems/htdemucs/<video-stem>/{vocals,drums,bass,other}.wav` layout has 4 stems; the consumer imports only 3. The `bass` stem is silently dropped from the canvas. The fixture mirrors this (only 3 stems), so the verify doesn't catch the omission. Either the consumer should iterate over `Object.keys(stems)` (data-driven) or the producer's manifest should declare which stems are canonical.

**Fix:**
```ts
const stemKeys = Object.keys(stems).length > 0
  ? Object.keys(stems)
  : ["vocals", "drums", "other"];
for (const stem of stemKeys) { ... }
```

---

### IN-04: Verify script's summary classification by ID prefix is undocumented coupling

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:76-77`
**Issue:**
```ts
const summaries = nodes.filter((n) => n.id.startsWith("sum-"));
const childNodes = nodes.filter((n) => n.type !== "zone" && !n.id.startsWith("sum-"));
```
This relies on the production convention that summary node IDs start with `"sum-"`. The convention is implicit (only `buildPhaseTree`'s `\`sum-${phasePrefix}\`` uses this prefix), and a future rename would silently change verify semantics. Worth either a constant or a comment.

**Fix:**
```ts
// Summary node IDs follow the buildPhaseTree convention `\`sum-${phasePrefix}\``;
// filter them out so per-type Zod (which they would fail) doesn't apply to structural parents.
const SUMMARY_ID_PREFIX = "sum-";
const summaries = nodes.filter((n) => n.id.startsWith(SUMMARY_ID_PREFIX));
```

---

### IN-05: Verify script's "exactly 93 storyboard children" is fixture-coupled, not contract-locked

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:94-98`
**Issue:**
The assertion `storyboards.length === 93` matches the specific ep01 fixture. If the fixture is regenerated from a different episode (or ep01 is re-detected with different parameters), this magic number will fail without explaining why. The "≥1 storyboard" assertion immediately above is the actual contract invariant; the 93 lock is a fixture-specific canary.

**Fix:** Add a comment making the fixture-coupling explicit (already partially done at L93), or read the expected count from the fixture's `shots.json` length and assert equality dynamically:
```ts
const expectedShotCount = JSON.parse(fs.readFileSync(path.join(FIXTURE, "shots.json"), "utf8")).length;
assert(storyboards.length === expectedShotCount, ...);
```

---

_Reviewed: 2026-07-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
