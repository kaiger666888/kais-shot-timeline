---
phase: 09-canvas-consumer-integration-cross-repo
reviewed: 2026-07-25T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts
  - /data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx
  - /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-07-25
**Depth:** standard (with empirical probe reinforcement)
**Files Reviewed:** 3 (cross-repo consumer — `feat/canvas-asset-collection` @ 90812e9d)
**Status:** issues_found

## Summary

The Phase 9 v1.1 character/prop emission works on the import path (the verify
harness passes 27/27), but it reintroduces the **exact WR-03 anti-pattern**
documented for v1.0 audio/video nodes: character/prop asset nodes are emitted
**without the `filePath` field that the asset schema marks required**
(`canvasAssetSchema.ts:23-25` + `:76-77`). Import succeeds (no per-type Zod
runs on the `appendAndSync` event-store path), but the next `save-v2` HTTP
roundtrip rejects every character/prop node with HTTP 400. The verify harness
does NOT catch this because `validateGraphNodes` is only asserted on the v1.0
ep01 run (line 176) — the v1.1 fixture run (lines 312-364) skips per-type
Zod entirely.

Empirical reproduction (12 injected-payload probes against the production
`extractShotTimelineArtifacts` + `validateGraphNodes`) confirms every
character/prop node produces `filePath: 无效输入：期望 string，实际接收
undefined`. This is a BLOCKER.

XSS (the prompt's PRIMARY focus area) is well-defended: all `name`/`label`
flows render through JSX text auto-escape in `AssetNode.tsx` (lines 128, 158,
206); no `dangerouslySetInnerHTML` / `innerHTML` / `eval` anywhere in the
node module. `<img src={thumbnailUrl}>` is React-attribute-escaped and `<img>`
cannot execute `javascript:` / `data:`-SVG scripts in modern browsers. No XSS
sink found.

The §7 post-process (FOCUS AREA 2) is correctly applied to all character/prop
`artifactNodes` and degrades cleanly on empty/missing registry. Graceful-
degrade (FOCUS AREA 5) is sound across all probed shapes (snapshot=null,
snapshot={}, missing `characters` field, null entries, etc.).

The Assert E baseline change (FOCUS AREA 3) is correct for THIS commit but
**structurally unsound as a permanent regression gate** — `HEAD~1..HEAD`
makes the gate commit-structure-dependent (an unrelated follow-up commit
would cause it to pass vacuously).

## Critical Issues

### CR-01: Character/prop asset nodes lack required `filePath` → save-v2 rejects with HTTP 400 (WR-03 pattern reintroduced)

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1118-1177` (the §7 push + post-process); schema at `/data/workspace/kst-canvas-consumer/src/lib/canvasAssetSchema.ts:23-25,76-77`
**Issue:**

`universalRequired` defines `filePath: z.string().min(1, "filePath is required for media nodes")`, and the `asset` schema spreads `...universalRequired` as required fields. save-v2 enforces this at `src/routes/canvas/v2/save-v2.ts:49-58` and rejects with HTTP 400 on any violation.

Phase 9 emits character/prop nodes via two steps:
1. Pre-`buildPhaseTree` push (lines 1118-1124): sets `label`, `output_key`, `canvasType:"asset"`, `name`, `description`. **No `filePath`.**
2. §7 post-process (lines 1164-1177): overwrites `data.assetType` and sets `data.thumbnailUrl` from `representative_image`. **Does not set `filePath`.**

Result: every character/prop node has `thumbnailUrl` set but `filePath` undefined → fails per-type Zod. The import path itself (via `appendAndSync`) bypasses Zod, so the canvas appears to work — but the next `save-v2` call rejects every character/prop node with HTTP 400, exactly the failure mode WR-03 (lines 978-993) was added to surface-and-warn for audio/video children.

This is also undocumented in WR-03's scope: WR-03 only warns about `source.duration_sec` malformed → audio/video `duration_sec=0`. The character/prop `filePath` gap is a parallel silent-Zod-fail that has neither a defensive warn nor a verify assertion.

Empirically reproduced (probe P2 with valid name, P5/P10 snapshot variants): every emitted character/prop node yields `filePath: 无效输入：期望 string，实际接收 undefined`. The v1.0 ep01 verify passes only because v1.0 has no `type:"asset"` children (audio/video/storyboard schemas each set `filePath` at import-from-dir.ts:1046,1062).

**Fix:** Set `filePath` alongside `thumbnailUrl` in the §7 post-process — `representative_image` IS a media PNG, so it satisfies both `thumbnailUrl` and `filePath` semantics:

```typescript
// import-from-dir.ts §7 post-process (around line 1170)
if (entry.representative_image) {
  const imgAbs = join(workdir, entry.representative_image);
  const imgOss = fsToOssUrl(imgAbs);
  const url = imgOss ?? imgAbs;
  data.thumbnailUrl = url;
  data.filePath = url;  // NEW — asset schema (canvasAssetSchema.ts:23-25) requires filePath
}
```

And add a `validateGraphNodes` assertion to the v1.1 fixture run in verify-canvas-shot-timeline.ts (see WR-03 below) so this regression cannot recur silently.

## Warnings

### WR-01: Assert E baseline `HEAD~1..HEAD` is structurally unsound as a permanent regression gate

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:199-203`
**Issue:**

The deviation rationale (origin/master advanced past branch tip → origin/master..HEAD carried ~56 pre-existing files) is factually correct for THIS commit — `git merge-base origin/master HEAD === bb3eaaf4 === HEAD~1`, so the two formulations happen to produce identical output today (verified empirically: both return only `AssetNode.tsx`).

But `HEAD~1..HEAD` makes the regression gate **commit-structure-dependent**:
- If a future contributor adds an unwanted `packages/infinite-canvas/.../NewRenderer.tsx` in commit N, then lands an unrelated fix in commit N+1, running verify at N+1 yields an empty `HEAD~1..HEAD` diff for `packages/infinite-canvas/` → assertion passes vacuously while the offending file lives in the tree.
- The original `origin/master..HEAD` intent was "branch-tip additive-only" (a state invariant); the deviation silently downgrades it to "last-commit additive-only".

**Fix:** Anchor against the merge-base (the actual divergence point), which is stable across future commits on this branch:

```typescript
const mergeBase = execSync(
  "git merge-base origin/master HEAD",
  { cwd: WORKTREE_CWD, encoding: "utf8" },
).trim();
treeDiff = execSync(
  `git diff --name-only ${mergeBase}..HEAD -- packages/infinite-canvas/`,
  { cwd: WORKTREE_CWD, encoding: "utf8" },
).trim();
```

If `origin/master` is missing (shallow clone / CI), fail loud like WR-08's pattern rather than silently degrading.

### WR-02: Assert E allowlist enforces "AssetNode.tsx file" but documents "typeIcons only"

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:207-218`
**Issue:**

The assertion name and detail string say "AssetNode.tsx typeIcons only (PRESENT-05 scoped relaxation)", but the actual enforcement is the file-level allowlist `{"packages/infinite-canvas/src/components/nodes/AssetNode.tsx"}`. A future commit that adds `dangerouslySetInnerHTML` for the label, an inline `<script>` for analytics, a new render branch, or any other dangerous/non-additive change to AssetNode.tsx would still PASS this assertion.

The spirit of PRESENT-05 (cosmetic emoji map extension only) is not enforced.

**Fix:** Either (a) rename the assertion to "AssetNode.tsx file allowlist" to match actual enforcement and document that the spirit invariant is review-time, not verify-time; or (b) add a hunk-content check that the AssetNode.tsx diff is contained to the `typeIcons` map (e.g., `git diff HEAD~1..HEAD -- packages/infinite-canvas/src/components/nodes/AssetNode.tsx` should only show lines inside the `typeIcons` object literal).

### WR-03: Verify harness skips `validateGraphNodes` on the v1.1 fixture run

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:312-364`
**Issue:**

The v1.0 ep01 run asserts `validateGraphNodes(childNodes).length === 0` (line 176-181) — the canonical regression catch for save-v2 Zod failures. The v1.1 fixture run (lines 312-364) asserts character/prop counts, thumbnailUrl prefix, output_key regex, and §7 zero-delivery-leak, but **never re-runs `validateGraphNodes` on the v1.1 childNodes**. This is precisely why CR-01 slipped through: the v1.1 character/prop nodes fail per-type Zod on `filePath`, but the harness doesn't look.

**Fix:** Add a v1.1-equivalent Step D:

```typescript
const v11ChildNodes = v11Nodes.filter((n: any) => n.type !== "zone" && !n.id.startsWith("sum-"));
const v11Errors = validateGraphNodes(v11ChildNodes);
assert(
  v11Errors.length === 0,
  "PRESENT-04 CANVAS-03: all v1.1 child nodes pass per-type Zod (regression catch for missing filePath / label)",
  v11Errors.length === 0 ? undefined : v11Errors.map((e) => `${e.nodeId}: ${e.errors}`).join(" | "),
);
```

### WR-04: §7 post-process join is fragile to cross-list duplicate registry IDs

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1164-1177`
**Issue:**

The join builds `registryById = new Map(registryEntries.map((e) => [e.output_key, e]))` — last-write-wins on key collision. If a buggy/malicious manifest emits the same `id` in both `snapshot.characters` and `snapshot.props` (e.g., both `char_001`), the character RawArtifact (already pushed with `output_key: "char_001"`) gets its `data.assetType` overwritten to `"prop"` in the post-process, silently mis-classifying the node.

Empirically reproduced (probe P4: chars=[{id:char_001,...}], props=[{id:char_001,...}] → emitted 0 chars, 2 props).

The producer schema enforces `^char_[0-9]{3}$` for character IDs and `^prop_[0-9]{3}$` for prop IDs, so cross-list collision is impossible in practice — but the consumer trusts the embedded `registry_snapshot` (asset.json is `any`, no Zod on import). Defense-in-depth missing.

**Fix:** Detect collisions when building `registryEntries` and warn:

```typescript
const seenIds = new Set<string>();
const collectRegistryEntries = (list: any, kind: "character" | "prop", ...) => {
  // ...
  const idStr = String(entry.id);
  if (seenIds.has(idStr)) {
    console.warn(`[v2/import] registry id collision: ${idStr} already emitted, last-write wins`);
  }
  seenIds.add(idStr);
  // ...
};
```

### WR-05: `representative_image` path not re-validated consumer-side (defense-in-depth gap)

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1171-1174`
**Issue:**

`const imgAbs = join(workdir, entry.representative_image)` resolves relative paths including `..` segments. `fsToOssUrl` returns null for paths outside both the OSS dir and `_workdirToOss.workdir`, so the fallback `data.thumbnailUrl = imgAbs` surfaces the raw escaped path (probe P7 with `representative_image="../../etc/passwd"` yielded `thumbnailUrl: "/data/workspace/kst-canvas-consumer/scripts/etc/passwd"`). The browser then issues a request for that path against the dev server origin — not an XSS vector (`<img>` cannot execute `javascript:`/SVG-script URIs), but a minor info-leak / confused-deputy surface.

The producer schema (`spec/schemas/characters.schema.json:25`) enforces `^(?!.*\\.\\.)([^/]+/)*characters/[^:*?\"<>|]+\\.png$`, so this can't occur via the canonical producer. The consumer trusts an `any`-typed manifest without re-validation.

**Fix:** Consumer-side defense-in-depth — reject or sanitize `representative_image` values containing `..`:

```typescript
if (entry.representative_image) {
  if (entry.representative_image.includes("..")) {
    console.warn(`[v2/import] refusing suspicious representative_image with '..': ${entry.representative_image}`);
    continue;
  }
  // ... existing join + fsToOssUrl
}
```

## Info

### IN-01: Empty `name` field silently produces Zod-failing label

**File:** `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts:1103`
**Issue:**

Guard `entry.name == null` uses loose equality — catches `null`/`undefined` but NOT empty string. An entry with `name: ""` is emitted with `label: ""`, which fails `asset` schema `label: z.string().min(1)`. Probe P1 confirmed: Zod error `label: asset node requires label` plus the CR-01 `filePath` error.

Producer schema (`characters.schema.json`) enforces `minLength: 1` on `name`, so producer-defended. Consumer trust gap.

**Fix:** Tighten guard to `entry.name == null || entry.name === ""`, or coerce to skip.

### IN-02: Assert E2 strictness counter is count-based, not semantics-based

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts:230-256`
**Issue:**

Assert E2 counts `.optional()` / `.nullable()` occurrences before and after, treating `headCount <= masterCount` as proof of "no strictness regression". A contributor could replace `z.string().min(1)` with `z.string()` (weakening) while keeping the `.optional()` count identical — assert passes. This is a known limitation already documented in the WR-08 comment block (lines 220-229) for the missing-master case, but the count-based weakness itself is unflagged.

Not blocking because PRESENT-04/05 don't touch `canvasAssetSchema.ts`, but worth flagging for future phases that do.

**Fix:** Consider a structural diff (parse both ASTs, compare field strictness semantically) or a property-based test that exercises edge cases.

### IN-03: XSS focus area — clean

**File:** `/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx` (whole file)
**Issue:**

Adversarial scan confirms no XSS sink. All `data.label` / `data.name` flows render as JSX text children (lines 128, 129, 141, 206, 228) which React auto-escapes. `<img src={displayThumb} alt={data.label}>` (lines 159-162) uses React's attribute serialization (quotes auto-escaped, no breakout possible). `displayThumb` for character/prop nodes comes from `representative_image` joined with workdir and optionally passed through `fsToOssUrl` — even a malicious `javascript:` URI would be a no-op in `<img src>` (modern browsers refuse to execute script URIs from `<img>`; only `<a href>` / `<iframe src>` / `<script src>` can). No `dangerouslySetInnerHTML` / `innerHTML` / `eval` / `Function(` / `setTimeout(string)` anywhere in the module.

Grep across `packages/infinite-canvas/src/components/nodes/` for `dangerouslySetInnerHTML|innerHTML|eval\(` returned no matches.

No action required. Recorded to document that the PRIMARY focus area was investigated, not skipped.

---

_Reviewed: 2026-07-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (with 12 injected-payload empirical probes against the production `extractShotTimelineArtifacts` + `validateGraphNodes`)_
