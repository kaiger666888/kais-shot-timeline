---
phase: 03-canvas-consumer
reviewed: 2026-07-21T00:00:00Z
iteration: 1
review_kind: auto-re-review
depth: standard
repo_reviewed: /data/workspace/kst-canvas-consumer
branch_reviewed: feat/canvas-asset-collection
diff_base: origin/master
files_reviewed: 2
files_reviewed_list:
  - /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts
  - /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts
fixes_verified:
  - WR-02
  - WR-03
  - WR-05
  - WR-06
  - WR-07
  - WR-08
fixes_status: all_resolved
deferred_documented:
  - WR-01
  - WR-04
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 3: Code Review Report — Iteration 1 (auto-re-review)

**Reviewed:** 2026-07-21
**Depth:** standard
**Repo reviewed:** `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`, diff base `origin/master`)
**Files Reviewed:** 2 (`src/routes/canvas/v2/import-from-dir.ts`, `scripts/verify-canvas-shot-timeline.ts`)
**Iteration:** 1 of fix→re-review loop (`--auto`)
**Status:** clean

## Summary

This is the iteration-1 re-review after the Phase 3 fixer applied fixes for WR-02 / WR-03 / WR-05 / WR-06 / WR-07 / WR-08 (consumer-repo commits `788fc6d2`, `368de27d`, `061154d1`, `ce0e41cc`, `bb3eaaf4` on `feat/canvas-asset-collection`).

**Outcome: all 6 fixes are RESOLVED. WR-01 and WR-04 remain as documented known-limitations in `deferred-items.md` (not silently dropped). No new BLOCKER / WARNING issues were introduced by the fixes.** The verify harness runs to 19 passed / 0 failed (executed locally — see Verification Run section).

Additive-only invariants still hold:
- `git diff --name-only origin/master..HEAD` lists only `.gitignore`, `scripts/fixtures/shot-timeline-ep01/*`, `scripts/verify-canvas-shot-timeline.ts`, `src/routes/canvas/v2/import-from-dir.ts`. No edits to `packages/infinite-canvas/`, `src/types/flowgraph-v2-schema.ts`, `src/types/flowgraph-v2.ts`, or `src/lib/canvasAssetSchema.ts`.
- Assert E (frontend zero-touch) PASS: `packages/infinite-canvas/` diff is empty.
- Assert E2 (schema strictness) PASS: `.optional()` count `master=18 head=18`, `.nullable()` count `master=0 head=0`. Strictness preserved.

## Fix Verification (per-warning)

### WR-02: `scanWorkdirForArtifacts` warns on co-located phase files before short-circuit — RESOLVED

**Evidence:** `import-from-dir.ts:1322-1354`. Before the unconditional `return phaseArtifacts`, the code now does:
```ts
try {
  const collocated = (await readdir(workdir)).filter(
    (f) => f.endsWith(".json") && f !== "asset.json" && findPhaseFromFile(f),
  );
  if (collocated.length > 0) {
    console.warn(
      `[v2/import] ShotTimelineAsset detected at ${assetManifestPath}; ` +
      `ignoring ${collocated.length} co-located phase file(s): ${collocated.join(", ")}`,
    );
  }
} catch { /* readdir failure (permissions race) — non-fatal */ }
```
The filter correctly uses `findPhaseFromFile` so ShotTimelineAsset-native files (`shots.json`, `audio_analysis.json`, `transcript.json`, `prompts.json`, `frames.json`) do NOT produce false-positive warns — they don't match any `p0X*` prefix in `FILE_TO_PHASE`. The catch guards the readdir race without masking the short-circuit. Matches fix option (b) from the original WR-02 proposal verbatim.

### WR-03: `sourceDuration <= 0` warns (Zod-doomed children surfaced) — RESOLVED

**Evidence:** `import-from-dir.ts:974-992`. After computing `sourceDuration`, the code warns before constructing audio+video children:
```ts
const sourceDuration = Number(manifest?.source?.duration_sec ?? 0) || 0;
// ...
if (!(sourceDuration > 0)) {
  console.warn(
    `[v2/import] ShotTimelineAsset manifest missing/invalid source.duration_sec ` +
    `(${manifestPath}); audio/video children will fail Zod validation on save-v2.`,
  );
}
```
The guard `!(sourceDuration > 0)` correctly catches `0`, `NaN`, and any negative value (the `Number(...) || 0` coercion above means `null`/`undefined`/`""` all become `0`). The warn message names the manifest path and identifies the downstream symptom (save-v2 Zod reject) so operators have an actionable audit trail. The fix is warn-only (no clamp to a positive sentinel) — this is option (b) from the original proposal; option (a) clamp remains explicitly available if Phase 4 wants tighter behavior. The golden fixture has `duration_sec: 308.352` so the warn does not fire in the verify path.

### WR-05: Comment accurately describes the shape (no false "byte-match" claim) — RESOLVED

**Evidence:** `import-from-dir.ts:1086-1108`. The new comment block is split into two paragraphs:
1. **L1087-1090** — accurate framing: "形状意图匹配 flowDataMapper.ts:163-172 (frontend precedent) 的渲染语义" + "backend 渲染结果与 frontend precedent 等价". Both statements are scoped to **rendering semantics / rendering result**, which is accurate — both shapes produce the same `data?.linkType === "sequence"` read at `CanvasEdge.tsx:33`.
2. **L1092-1097** — explicit disclaimer with three concrete differences enumerated:
   ```
   // WR-05: 形状 NOT 字面 byte-match flowDataMapper.ts:163-172 —— 三处差异:
   //   1. backend 顶层有 branchId:"main";frontend precedent 省略 (前端默认隐含).
   //   2. backend dataType:"data" 在顶层;frontend precedent 嵌在 data.dataType.
   //   3. backend data 只装 {linkType};frontend precedent data 装 {dataType,linkType}.
   ```
Future maintainers reading either paragraph will not be misled — the disclaimer is unambiguous and the migration hazard (future code reading `data.dataType`) is called out. No false "byte-match" claim remains.

### WR-06: `as FlowLinkV2` cast replaced with typed local extension; FlowLinkV2 interface untouched — RESOLVED

**Evidence:** `import-from-dir.ts:1099-1128`. The cast is gone, replaced with:
```ts
type SequenceLink = FlowLinkV2 & { data?: Record<string, unknown> };
const sequenceLinks: SequenceLink[] = [];
// ...
for (let i = 1; i < sbNodes.length; i++) {
  const link: SequenceLink = {
    id: `seq-${sbNodes[i - 1].id}-${sbNodes[i].id}`,
    source: sbNodes[i - 1].id,
    target: sbNodes[i].id,
    branchId: "main",
    dataType: "data",
    data: { linkType: "sequence" },
  };
  sequenceLinks.push(link);
}
```
Type-safety analysis:
- `SequenceLink` extends `FlowLinkV2` with an optional `data` field — it's a strict supertype. Object-literal assignment to `SequenceLink` type-checks without coercion.
- The function's return type is still `{ nodes: FlowNodeV2[]; links: FlowLinkV2[] }`. Spreading `sequenceLinks` (a `SequenceLink[]`) into `FlowLinkV2[]` is sound by array covariance (subtype→supertype assignment).
- The `data` field survives at runtime — the change is purely compile-time. The produced graph is byte-identical to the pre-fix version.
- `FlowLinkV2` (`src/types/flowgraph-v2.ts:45-53`) is unchanged — still does not declare `data`. `git diff origin/master..HEAD -- src/types/flowgraph-v2.ts` returns empty.

The local `SequenceLink` alias is the minimal-touch type-level mitigation; once `FlowLinkV2` adds `data?: ...` (WR-01 fix in Phase 4), the alias becomes redundant and can be deleted. The comment at L1099-1103 documents this.

### WR-07: Verify harness sets `_workdirToOss` via exported `setWorkdirToOss`; F2 asserts confirm `/oss/shot-timeline-ep01/` prefix — RESOLVED

**Evidence (3 parts):**

1. **New export.** `import-from-dir.ts:173-186` exports `setWorkdirToOss(mapping)`, which simply assigns the module-level `_workdirToOss`. Production caller `scanAndBuildTree` (L1581) continues to assign `_workdirToOss` directly — it does NOT use the new export, so no production behavior changes. Verified via grep: the only callers of `setWorkdirToOss` are the verify harness import (L27) + invocation (L63) and the definition itself (L182). No production caller breaks.

2. **Harness sets the global.** `verify-canvas-shot-timeline.ts:62-63`:
   ```ts
   const workdirBase = path.basename(FIXTURE.replace(/\/$/, ""));
   setWorkdirToOss({ workdir: FIXTURE, ossPrefix: `/oss/${workdirBase}` });
   ```
   This mirrors `scanAndBuildTree:1580-1581` exactly (`workdirBase = basename(workdir.replace(/\/$/, ""))`, `ossPrefix = \`/oss/${workdirBase}\``), so the verify path now exercises the same `fsToOssUrl` workdir-branch that production exercises.

3. **F2 asserts confirm prefix.** `verify-canvas-shot-timeline.ts:245-260`:
   ```ts
   const expectedFilePrefix = `/oss/${workdirBase}/`;
   assert(audios.every((a) => typeof a.data?.filePath === "string" && a.data.filePath.startsWith(expectedFilePrefix)), ...);
   assert(typeof videos[0]?.data?.filePath === "string" && videos[0].data.filePath.startsWith(expectedFilePrefix), ...);
   ```
   Both asserts are meaningful: they fail if `_workdirToOss` was not set (filePath would be a raw absolute path like `/data/workspace/...`), and they fail if `fsToOssUrl`'s workdir-branch logic regresses. Assert A above (lines 96-100) gates F2 by asserting `audios.length === 3` and `videos.length === 1` first, so F2's `.every` cannot pass vacuously on an empty collection.

**Verification run confirms:** the harness executed locally produces `F2 (WR-07): every audio.data.filePath synthesized as /oss/{slug}/... (production-realistic) — expected prefix '/oss/shot-timeline-ep01/'; got /oss/shot-timeline-ep01/stems/vocals.wav, /oss/shot-timeline-ep01/stems/drums.wav, /oss/shot-timeline-ep01/stems/other.wav` and `F2 (WR-07): video.data.filePath synthesized as /oss/{slug}/... (production-realistic) — expected prefix '/oss/shot-timeline-ep01/'; got '/oss/shot-timeline-ep01/video.mp4'`. Both PASS.

### WR-08: Assert E2 fails loud when `origin/master` is missing (no vacuous pass) — RESOLVED

**Evidence:** `verify-canvas-shot-timeline.ts:190-216`. A new `schemaCompareOk: boolean | null` variable (distinct from the count variables) tracks comparison outcome explicitly:
```ts
let masterOpt = -1, headOpt = -1, masterNull = -1, headNull = -1;
let schemaDiffStatus = "";
let schemaCompareOk: boolean | null = null;
try {
  // ... execSync + readFileSync + counts ...
  schemaCompareOk = headOpt <= masterOpt && headNull <= masterNull;
} catch (err) {
  schemaDiffStatus = `(compare failed: ${(err as Error).message})`;
  schemaCompareOk = null;
}
assert(
  schemaCompareOk === true,
  "CANVAS-03 additive-only: canvasAssetSchema.ts strictness preserved",
  schemaDiffStatus ||
    `.optional() master=${masterOpt} head=${headOpt}; .nullable() master=${masterNull} head=${headNull}`,
);
```
- If `origin/master` is missing (fresh shallow clone, CI without `--fetch-depth=full`, detached-HEAD builder): `execSync` throws → `schemaCompareOk = null` → `assert(null === true, ...)` FAILS. No vacuous pass.
- If comparison succeeds and strictness preserved: `schemaCompareOk = true` → PASS with informative detail string.
- If comparison succeeds and regression detected: `schemaCompareOk = false` → FAIL with counts.
The comment block at L182-189 explicitly documents the prior vacuous-pass failure mode and why the new variable closes it. Asymmetry with Assert E (which already failed loud via `treeDiff === ""`) is resolved — both additive-only guards now fail loud on `origin/master` missing.

**Verification run confirms:** the harness executed locally with `origin/master` present produces `PASS: CANVAS-03 additive-only: canvasAssetSchema.ts strictness preserved — .optional() master=18 head=18; .nullable() master=0 head=0`. Detail string shows the actual counts, confirming the comparison ran (not skipped).

**Note (carried forward from original review):** the count-based check has a semantic loophole — changing `z.string().min(1)` to `z.string()` (loosening min-length strictness) would change neither `.optional()` nor `.nullable()` count and would not be detected. This remains an Info-level limitation, not a regression introduced by the fix. No fix proposed here; out of iteration-1 scope.

## Deferred Items Documentation (WR-01, WR-04)

### WR-01: Sequence edge `data` field silently stripped by `save-v2` Zod parse — DOCUMENTED (not fixed, by design)

`deferred-items.md:39-107` documents WR-01 with full fidelity:
- Symptom (sequence edges downgrade to plain edges after `save-v2` roundtrip)
- Scope boundary (primary `appendAndSync` path unaffected; secondary `save-v2` HTTP path has latent bug)
- Why deferred (touches shared production graph schema across all 14 phases; CANVAS-03 spirit applies to `flowgraph-v2-schema.ts`)
- Phase 3 mitigations already in place (the WR-05 comment now accurately documents the `save-v2`-strips-`data` caveat; the WR-06 fix replaced the silent `as FlowLinkV2` cast with the local `SequenceLink` typed extension so the gap is visible to TS at the construction site)
- Phase 4 decision needed (3 options listed)

The deferral rationale is sound and the item is not silently dropped. WR-01 is correctly classified as a WARNING-tier latent bug in the **deferred** state.

### WR-04: Phase 3 expands blast radius of pre-existing `save-v2` summary-node Zod-reject — DOCUMENTED (not fixed, by design)

`deferred-items.md:110-177` documents WR-04 with full fidelity:
- Symptom (`sum-p13` summary node inherits `.type = "video"` from `buildPhaseTree`, fails `validateNodeData` media-fields check)
- Pre-existing pattern (every phase's summary node since P01 has the same shape; Phase 3 increases trigger frequency)
- Scope boundary (primary path unaffected; secondary `save-v2` HTTP path latent)
- Why deferred (fix touches production `save-v2.ts:49` call site — beyond Phase 3 mandate)
- Phase 3 mitigations already in place (verify script filters `sum-` prefixed nodes before `validateGraphNodes` to match plan SC intent; the deferral itself documents the limitation)
- Phase 4 decision needed (4 options listed)

The deferral rationale is sound and the item is not silently dropped. WR-04 is correctly classified as a WARNING-tier latent bug in the **deferred** state.

## Regression Check (newly-introduced issues)

The fixes were inspected for regressions along the following axes; **no new BLOCKER or WARNING issues found.**

1. **WR-02 readdir catch hides readdir errors.** The `try/catch` around `readdir` (L1332-1342) only guards the warn-emission path; the unconditional short-circuit at L1345-1354 runs regardless. If `readdir` fails, operators lose the warn but not the import behavior. Acceptable — same failure mode as no-warn, no regression.

2. **WR-03 is warn-only (no clamp).** Audio+video children with `duration_sec=0` are still produced and will Zod-fail on the next `save-v2`. The warn provides the audit trail; the import path itself remains non-failing (graceful-degrade per SPEC §4). This matches option (b) of the original proposal. The fixture has `duration_sec: 308.352` so no behavioral change in the verify path. No regression.

3. **`SequenceLink` typed extension correctness.** `SequenceLink = FlowLinkV2 & { data?: Record<string, unknown> }` is a strict supertype of `FlowLinkV2`. The link literal type-checks without coercion; spreading into the `FlowLinkV2[]` return type is sound by array covariance. The runtime object is byte-identical to the pre-fix version (`data: { linkType: "sequence" }` is still emitted). The local alias is encapsulated inside `extractShotTimelineArtifacts` — it does not leak into the public return type signature. No regression.

4. **`setWorkdirToOss` export not breaking other callers.** Grep confirms only the verify harness calls the new export. Production (`scanAndBuildTree:1581`) continues to assign `_workdirToOss` directly. The export is purely additive — a new public surface for test harnesses, with no production-side behavior change. The new export does not introduce a new race condition: the module-level `_workdirToOss` was already mutable global state shared across concurrent requests pre-fix; the export adds a programmatic setter but doesn't change the concurrency model. No regression.

5. **F2 asserts meaningful (not tautological).** `expectedFilePrefix = \`/oss/${workdirBase}/\`` is a concrete string (`/oss/shot-timeline-ep01/`) independent of the produced `filePath`. The `startsWith` check would fail if (a) `_workdirToOss` were not set (filePath would be the raw absolute path), (b) `fsToOssUrl` regressed on its workdir-prefix branch, or (c) the fixture path basename changes without the prefix being updated. Assert A gates F2 by ensuring `audios.length === 3` and `videos.length === 1`, so the `.every` predicate cannot pass vacuously on an empty collection. The asserts catch real regressions.

6. **Schema diff `schemaCompareOk` semantics.** The new `boolean | null` tri-state correctly distinguishes "couldn't compare" (null) from "compared + ok" (true) from "compared + regression" (false). The assert condition `=== true` fails on both null and false, matching the documented intent. The detail string includes counts when comparison ran and the error message when it didn't, preserving diagnostic value either way. No regression.

## Additive-Only Invariant

Still holds after iteration-1 fixes:

- `git diff --name-only origin/master..HEAD` lists exactly: `.gitignore`, `scripts/fixtures/shot-timeline-ep01/{asset,audio_analysis,frames,prompts,shots,transcript}.json`, `scripts/fixtures/shot-timeline-ep01/stems/{vocals,drums,other}.wav`, `scripts/fixtures/shot-timeline-ep01/video.mp4`, `scripts/verify-canvas-shot-timeline.ts`, `src/routes/canvas/v2/import-from-dir.ts`.
- `packages/infinite-canvas/` — UNCHANGED (Assert E PASS).
- `src/types/flowgraph-v2-schema.ts` — UNCHANGED (FlowLinkV2Schema still strips unknown keys; WR-01 deferred).
- `src/types/flowgraph-v2.ts` — UNCHANGED (FlowLinkV2 interface still does not declare `data`; WR-06 fix is local-only).
- `src/lib/canvasAssetSchema.ts` — UNCHANGED (strictness counts equal: 18/18 `.optional()`, 0/0 `.nullable()`; Assert E2 PASS).
- `.gitignore` — adds a single negation `!scripts/fixtures/shot-timeline-ep01/video.mp4` so the golden fixture's real mp4 container (needed for `ffprobe` resolution probing) is committed. Benign and scoped to the fixture path only.

## Verification Run (local)

The verify harness was executed locally (`npx tsx scripts/verify-canvas-shot-timeline.ts`) and produced **19 passed, 0 failed**. Highlights:
- All CANVAS-01 structural asserts PASS (1 zone, 1 summary, 3 audio, 1 video, 93 storyboard matching real ep01 shots.json).
- All CANVAS-02 sequence-edge asserts PASS (92 edges, monotonic shot_id chain, single chain).
- CANVAS-03 per-type Zod PASS (validateGraphNodes returns 0 errors on childNodes after filtering `sum-` prefix).
- Assert E PASS (`packages/infinite-canvas/` diff empty).
- Assert E2 PASS with informative detail (`master=18 head=18` for optional, `master=0 head=0` for nullable — strictness preserved, comparison actually ran).
- All F roundtrip asserts PASS (zone label, video duration, audio engine, video resolution `1280x720`, storyboard shot_id).
- **Both F2 asserts PASS** — every audio filePath is `/oss/shot-timeline-ep01/stems/{vocals,drums,other}.wav`, video filePath is `/oss/shot-timeline-ep01/video.mp4`. The `_workdirToOss` workdir-branch in `fsToOssUrl` is now exercised by the harness.

A noisy `better-sqlite3` native-module error appears in stderr during module import (transitive import chain via `canvasEventStore` → `@/utils` → knex), but it does not affect test outcome — `extractShotTimelineArtifacts` is a pure function that never touches the DB, and the asserts all run to completion with exit code 0.

## Status Determination

Per the iteration-1 acceptance criteria: all 6 fixed warnings (WR-02, WR-03, WR-05, WR-06, WR-07, WR-08) are RESOLVED with concrete evidence; WR-01 and WR-04 are documented in `deferred-items.md` (not silently dropped, not fixed by design — both are correctly classified as WARNING-tier latent bugs in the deferred state, owned by Phase 4); no new BLOCKER or WARNING issues were introduced by the fixes; additive-only invariants hold. **Status: clean.**

The clean status reflects the fix-iteration outcome. It does not assert that the underlying codebase is bug-free — WR-01 and WR-04 remain as documented known-limitations on the secondary `save-v2` HTTP path (Phase 3 primary `appendAndSync` path unaffected), explicitly owned by Phase 4 per `deferred-items.md`.

---

_Reviewed: 2026-07-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 1 (auto-re-review)_
