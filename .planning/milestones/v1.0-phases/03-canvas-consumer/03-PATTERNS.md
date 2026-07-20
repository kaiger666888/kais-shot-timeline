# Phase 3: Canvas Consumer - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 3 (1 MODIFY + 2 NEW)
**Analogs found:** 3 / 3 (every new/modified file has a concrete in-repo analog)

**Cross-repo context:**
- Planning & this PATTERNS.md live in producer repo `/data/workspace/kais-shot-timeline/.planning/phases/03-canvas-consumer/`.
- Code changes (and all analogs cited below) live in the **consumer worktree** `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`, HEAD `686d526c`).
- Producer source for the golden fixture (file path embedded in `## Pattern Assignments` → fixture): `/data/workspace/kais-shot-timeline/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/routes/canvas/v2/import-from-dir.ts` (MODIFY: + ShotTimelineAsset branch in `scanWorkdirForArtifacts`, + new exported `extractShotTimelineArtifacts` helper, + possibly 1-line `RawArtifact.canvasType` extension + sequence-edge emission) | backend route + tree-builder (express route + pure transform fn) | file-I/O → transform → request-response (bootstrap persist via `appendAndSync`) | **self-referential** — same file's existing 13-phase logic (`scanWorkdirForArtifacts` L996-1135, `buildPhaseTree` L592-835, `extractArtifactsFromJSON` L270-327, `fsToOssUrl` L174-192, `appendAndSync` callers L1393-1405 / L1465-1477) | exact (in-file reuse) |
| `scripts/verify-canvas-shot-timeline.ts` (NEW) | test (standalone verify script) | transform (fixture replay → assertion) | `scripts/verify-import-roundtrip.ts` (140 lines, identical skeleton) | exact (template clone) |
| `scripts/fixtures/shot-timeline-ep01/` (NEW directory: asset.json + 5 data JSONs + ffmpeg-stub media) | test fixture (golden data) | file-I/O (static, read by verify script + by `extractShotTimelineArtifacts`) | `scripts/fixtures/sample-manifest.json` (existing in-repo fixture format) + real producer output at `/data/workspace/kais-shot-timeline/output/虫虫武侠…第01话…/asset.json` | role-match (existing fixture is single-JSON; this one is a multi-file directory tree copied from producer output) |

---

## Pattern Assignments

### `src/routes/canvas/v2/import-from-dir.ts` (backend route + tree-builder, file-I/O → transform → request-response)

**Analog:** itself (self-referential) — Phase 3 extends the file's existing 13-phase pipeline. Every excerpt below is the concrete shape to mirror or extend.

#### Imports pattern (lines 1-17)

The new helper (`extractShotTimelineArtifacts`) lives in this same file, so no new imports are needed at the top — but the helper body will use `join`, `readFile`, `tryReadJSON`, `fsToOssUrl`, `buildPhaseTree`, all already in scope. For `ffprobe` resolution probing, use dynamic `child_process.execFile` (matches the codebase's "lazy stdlib import" convention).

```typescript
import express from "express";
import { z } from "zod";
import { success, error } from "@/lib/responseFormat";
import { validateFields } from "@/middleware/middleware";
import { readdir, readFile, stat } from "fs/promises";
import { join, extname, basename } from "path";
import type { FlowGraphV2, FlowNodeV2, FlowLinkV2, FlowBranchV2 } from "@/types/flowgraph-v2";
import {
  ensureBootstrap,
  getLastEventId,
  listEvents,
} from "@/lib/canvasEventStore";
import { appendAndSync } from "@/lib/canvasEventStore";
import { broadcastToProject } from "@/utils/ws";
import u from "@/utils";
import { SCHEMA_ALIASES, ENUM_NORMALIZERS } from "../../../../schema/generated/frontend-enum-normalizers";
import { EXPECTED_PARAM_FIELDS_BY_TYPE } from "@/lib/canvasAssetSchema";
```

#### Auth / route-validation pattern (lines 1307-1316)

The route already wraps `validateFields(...)` for body shape — Phase 3 does NOT touch this (CONTEXT locks "single existing entrypoint, no new route"). The ShotTimelineAsset branch is purely a new code path INSIDE `scanWorkdirForArtifacts` / `scanAndBuildTree`, not a new route.

```typescript
export default router.post(
  "/",
  validateFields({
    projectId: z.number(),
    episodesId: z.number(),
    workdir: z.string().min(1),
    projectName: z.string().optional(),
    mode: z.enum(["merge", "replace"]).optional(),
  }),
  async (req, res) => { /* ... */ }
);
```

#### RawArtifact type definition — EXTENSION POINT for Solution A (lines 237-254)

This is the type to extend with `canvasType?: ...` if planner picks Solution A (per-artifact canvasType override). Additive: all 13 existing callers omit it → zero behavior change.

```typescript
interface RawArtifact {
  /** Display label for this artifact */
  label: string;
  /** The output_key this artifact came from */
  output_key: string;
  /** Optional name (more descriptive than label sometimes) */
  name?: string;
  /** Optional description */
  description?: string;
  /** Optional generation prompt (shown in detail panel; falls back to description) */
  prompt?: string;
  /** Optional media thumbnail URL */
  thumbnailUrl?: string;
  /** Optional media file path */
  filePath?: string;
  /** Optional extra data fields from the source item */
  extra?: Record<string, any>;
}
```

**Solution A extension to add (1-line additive):**
```typescript
  /** Phase 3: per-artifact canvasType override; omit → use phase default. */
  canvasType?: "script" | "asset" | "storyboard" | "audio" | "video";
```

#### buildPhaseTree — the central design tension (lines 592-835, esp. L802)

This is the structural constraint that drives Pattern 2 in RESEARCH.md. Line 802 forces `type: def.canvasType as any` for every artifact in the phase, so without an override mechanism, a single zone cannot hold heterogeneous storyboard/audio/video children.

**Summary node construction (lines 627-644)** — should remain phase-default type (don't change):
```typescript
const summaryNode: FlowNodeV2 = {
  id: `sum-${phasePrefix}`,
  type: def.canvasType as any,
  branchId: "main",
  phaseIndex: laneIndex + 1,
  phaseName: def.label,
  position: { x: baseX, y: SUMMARY_Y },
  size: { width: SUMMARY_WIDTH, height: SUMMARY_HEIGHT },
  state: "success",
  data: {
    label: def.label,
    description: `${artifacts.length} artifacts`,
    assetType: def.assetType,
    state: "success",
    tags: ["phase"],
  },
};
```

**Artifact node construction (lines 802-826)** — THIS is the line to change for Solution A (`art.canvasType ?? def.canvasType`); the rest of the artifact loop (extra-merge L696-704, alias L711-716, enum-normalize L723-728, expected-fields warn L737-748, E-Konte derive L753-800) all stay identical so the new ShotTimelineAsset path inherits every receiver-side compatibility shim:

```typescript
const artNode: FlowNodeV2 = {
  id: nodeId,
  type: def.canvasType as any,   // ← L804: change to `(art.canvasType ?? def.canvasType) as any` for Solution A
  branchId: "main",
  phaseIndex: laneIndex + 1,
  phaseName: def.label,
  position: {
    x: baseX + col * ART_COL_SPACING,
    y: ART_BASE_Y + row * ART_ROW_SPACING,
  },
  size: { width: ART_WIDTH, height: ART_HEIGHT },
  state: "success",
  data: artData,
};
nodes.push(artNode);

// Link: zone → artifact (zone-to-child pattern)
links.push({
  id: `zc-${phasePrefix}-${nodeId}`,
  source: phasePrefix,
  target: nodeId,
  branchId: "main",
  dataType: "output",
});
```

#### extractArtifactsFromJSON — reference for the helper's input-shape handling (lines 270-327)

Phase 3's `extractShotTimelineArtifacts` will NOT use `extractArtifactsFromJSON` (that function is for free-form list-valued dicts; ShotTimelineAsset has a known 5-JSON shape). But the patterns to mirror are: (a) the `SKIP_KEYS` allowlist discipline, (b) the `label.slice(0, 100)` / `description.slice(0, 200)` truncation caps, (c) early-return on null input, (d) returning `RawArtifact[]` so the downstream `buildPhaseTree` can consume.

#### fsToOssUrl — the media URL normalizer to reuse (lines 174-192)

The new helper calls this verbatim for every stem/video path. Pattern: feed it an absolute path; if it returns null, fall back to the raw path (matches `itemToArtifact` L391-393 `ossUrl || absPath`).

```typescript
function fsToOssUrl(fsPath: string): string | null {
  if (!fsPath || typeof fsPath !== "string") return null;
  if (fsPath.startsWith("/oss/")) return fsPath;
  const ossDir = "/data/workspace/kais-aigc-platform/data/oss";
  if (fsPath.startsWith(ossDir + "/")) {
    return "/oss/" + fsPath.substring(ossDir.length + 1);
  }
  if (_workdirToOss && fsPath.startsWith(_workdirToOss.workdir)) {
    const relPath = fsPath.substring(_workdirToOss.workdir.length);
    return _workdirToOss.ossPrefix + relPath;
  }
  if (fsPath.startsWith("http://") || fsPath.startsWith("https://")) return fsPath;
  return null;
}
```

**Usage convention** (mirror from `itemToArtifact` L385-393 and `artifactsFromMediaFiles` L493-501):
```typescript
const ossUrl = fsToOssUrl(absPath);
art.filePath = ossUrl || absPath;
```

#### tryReadJSON — catch-null JSON reader to reuse (lines 204-211)

For the helper's 5 parallel JSON reads + asset.json probe. Already handles missing-file + JSON-parse errors gracefully.

```typescript
async function tryReadJSON(filePath: string): Promise<any | null> {
  try {
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
```

#### scanWorkdirForArtifacts — INSERTION POINT for Pattern 1 (lines 996-1135)

Phase 3 inserts an early-recognize branch at the TOP of this function (before the `for (const file of rootFiles)` loop at L1018). The shape to mirror is the function's existing structure: it returns `Map<string, RawArtifact[]>`, and downstream `scanAndBuildTree` (L1226-1274) iterates that map.

Two viable insertion strategies (planner picks):

**Strategy 1 (RESEARCH Pattern 1, "early short-circuit + sentinel key"):** Detect `asset.json` at the top of `scanWorkdirForArtifacts`, set a sentinel map key (`__shot_timeline_asset__`), return early. Then in `scanAndBuildTree` (after L1263, before `buildZoneChainLinks`) check that key and call `extractShotTimelineArtifacts` directly to push nodes/links.

**Strategy 2 (more local):** Don't early-return; instead detect `asset.json` inside the existing root-files loop and stash the manifest into a closure-scoped variable. After the loop, if stashed, push the helper's output into a special phase key.

RESEARCH.md recommends Strategy 1 (more isolated, doesn't entangle with the existing `findPhaseFromFile` heuristic).

#### scanAndBuildTree — secondary hook for merge (lines 1226-1274)

This is where the ShotTimelineAsset sub-tree (1 zone + N storyboard + 3 audio + 1 video + sequence edges) merges with the rest of the canvas tree. Note: it already invokes `enrichMediaArtifactsFromJSON` (L1249), `buildZoneChainLinks` (L1266), `buildCrossReferenceLinks` (L1270) — Phase 3's new sub-tree should be merged BEFORE these so its nodes can participate in cross-reference linking (or after, if we want ShotTimelineAsset to stay self-contained — planner call).

```typescript
async function scanAndBuildTree(
  workdir: string,
): Promise<{ nodes: FlowNodeV2[]; links: FlowLinkV2[] }> {
  const allNodes: FlowNodeV2[] = [];
  const allLinks: FlowLinkV2[] = [];

  const workdirBase = basename(workdir.replace(/\/$/, ""));
  _workdirToOss = { workdir, ossPrefix: `/oss/${workdirBase}` };

  const phaseArtifacts = await scanWorkdirForArtifacts(workdir);
  if (phaseArtifacts.size === 0) return { nodes: [], links: [] };

  enrichMediaArtifactsFromJSON(phaseArtifacts);

  const activePhases: string[] = [];
  for (const def of PHASE_DEFS) {
    const artifacts = phaseArtifacts.get(def.prefix);
    if (!artifacts || artifacts.length === 0) continue;
    activePhases.push(def.prefix);
    const tree = buildPhaseTree(def.prefix, artifacts);
    allNodes.push(tree.zoneNode, tree.summaryNode);
    allNodes.push(...tree.artifactNodes);
    allLinks.push(...tree.links);
  }

  const chainLinks = buildZoneChainLinks(activePhases);
  allLinks.push(...chainLinks);

  const xrefLinks = buildCrossReferenceLinks(allNodes);
  allLinks.push(...xrefLinks);

  return { nodes: allNodes, links: allLinks };
}
```

#### appendAndSync — bootstrap persistence pattern (lines 1393-1405 + L1465-1477)

The new ShotTimelineAsset sub-tree flows through `scanAndBuildTree` → exactly the same `appendAndSync({ projectId, episodesId, clientId, source, events: [{ type: "bootstrap", payload: { graph } }] })` call. **No new persistence code is needed** — Phase 3's nodes/links enter via the same `{ newNodes, newLinks }` return from `scanAndBuildTree` at L1359.

Caller shape to mirror (both modes — replace L1393 and merge L1465):
```typescript
const clientId = `import-from-dir:replace:${projectId}:${episodesId}:${now}`;
await appendAndSync({
  projectId,
  episodesId,
  clientId,
  source: "import-from-dir",
  events: [
    {
      type: "bootstrap",
      nodeId: undefined,
      payload: { graph },
    },
  ],
});
```

#### OSS symlink bootstrap pattern (lines 1330-1356)

The route already creates `data/oss/{workdirBase} → workdir` symlink non-fatally. Phase 3 reuses this — `fsToOssUrl` depends on it for `/oss/{slug}/stems/vocals.wav` resolution. The verify script must either (a) point at a fixture dir under an already-symlinked location, or (b) monkey-patch `_workdirToOss` to avoid needing the symlink.

#### Sequence edge prior art (cross-file)

The `{ dataType: "data", data: { linkType: "sequence" } }` shape has an established precedent in the frontend mapper (`flowDataMapper.ts:163-172`) and is hard-recognized by `CanvasEdge.tsx:60-75` (blue solid + arrow marker). Phase 3 is the first time this shape is emitted at the backend, so the helper must match this shape exactly.

**flowDataMapper.ts L163-172** (precedent for sequence edge shape, frontend side):
```typescript
// 分镜顺序连线：相邻分镜之间插入 sequence link
if (i > 0) {
  const prevNodeId = `storyboard-${sortedSb[i - 1].id}`;
  edges.push({
    id: `seq-${edgeId++}`,
    source: prevNodeId,
    target: nodeId,
    data: { dataType: 'data', linkType: 'sequence' },
  });
}
```

Note: in the backend FlowLinkV2 type (`src/types/flowgraph-v2.ts:45-53`) `data` is NOT a declared field — it's `[k: string]: any`-style flexible. The backend emitter can put `data: { linkType: "sequence" }` and it will survive the SQLite roundtrip (load-v2 rowToLink will preserve it).

---

### `scripts/verify-canvas-shot-timeline.ts` (test / verify script, transform)

**Analog:** `scripts/verify-import-roundtrip.ts` (140 lines, byte-for-byte template)

Copy this skeleton verbatim, then swap two things:
1. **Import:** replace `flattenParamsToNodeData` with `extractShotTimelineArtifacts` (and/or `validateGraphNodes` from `canvasAssetSchema.ts`).
2. **Fixture loader:** replace the multi-fixture generator (lines 53-68) with a single fixed path `scripts/fixtures/shot-timeline-ep01/`.

#### Imports + scaffold pattern (analog lines 1-32)

```typescript
#!/usr/bin/env tsx
/**
 * verify-import-roundtrip.ts — Phase 46 VERIFY-02.
 *
 * Loads fixture manifests, runs each node through the production
 * flattenParamsToNodeData helper, and asserts:
 *   - Every scalar params.* key round-trips into the flattened output
 *   - For content-bearing types (asset/script/storyboard/video), the
 *     description field is non-empty AND ≥20 chars (Phase 42 contract)
 *
 * Run: npx tsx scripts/verify-import-roundtrip.ts
 */

import fs from "node:fs";
import path from "node:path";
import { flattenParamsToNodeData } from "../src/routes/canvas/v2/import-from-dir";

interface TestResult { name: string; pass: boolean; detail?: string; }
const results: TestResult[] = [];
function assert(cond: boolean, name: string, detail?: string): void {
  results.push({ name, pass: cond, detail });
  console.log(`  ${cond ? "PASS" : "FAIL"}: ${name}${detail ? " — " + detail : ""}`);
}

const REPO_ROOT = path.resolve(__dirname, "..");
```

#### Fixture-loading pattern (analog lines 53-68) — simplify to single dir

```typescript
function* fixtureFiles(): Generator<{ path: string; label: string }> {
  const inRepoFixture = path.join(REPO_ROOT, "scripts/fixtures/sample-manifest.json");
  if (fs.existsSync(inRepoFixture)) {
    yield { path: inRepoFixture, label: "in-repo fixtures/sample-manifest.json" };
  }
  const crossRepoDir = path.join(SIBLING_ROOT, "skills/kais-movie-pipeline/tests/fixtures/manifests");
  if (fs.existsSync(crossRepoDir) && fs.statSync(crossRepoDir).isDirectory()) {
    for (const f of fs.readdirSync(crossRepoDir)) {
      if (f.endsWith(".json")) {
        yield { path: path.join(crossRepoDir, f), label: `cross-repo ${f}` };
      }
    }
  }
}
```

**Phase 3 simpler equivalent:**
```typescript
const FIXTURE = path.resolve(__dirname, "fixtures/shot-timeline-ep01");
```

#### Main / assertion-runner / exit-code pattern (analog lines 70-140)

The shape to clone: `async function main()` prints banner → loops fixtures → runs production helper → pushes via `assert()` → tallies passed/failed → `process.exit(failed > 0 ? 1 : 0)`. The final `.catch()` wrapper (lines 137-140) ensures any thrown error becomes a non-zero exit:

```typescript
async function main(): Promise<void> {
  console.log("=== Phase 46 VERIFY-02 — verify-import-roundtrip.ts ===\n");
  let totalNodes = 0;
  let contentBearingNodes = 0;

  for (const { path: fp, label } of fixtureFiles()) {
    let manifest: ManifestShape;
    try {
      manifest = JSON.parse(fs.readFileSync(fp, "utf8"));
    } catch (err) {
      assert(false, `VERIFY-02: ${label} parses as JSON`, (err as Error).message);
      continue;
    }
    // ... assertions ...
  }

  const passed = results.filter((r) => r.pass).length;
  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

#### Assertion targets specific to Phase 3 (per RESEARCH.md Validation Architecture)

RESEARCH.md L437-441 specifies six assertions A–F. They map cleanly onto the analog's `assert(cond, name, detail)` shape. The production helper to import is `extractShotTimelineArtifacts` plus `validateGraphNodes` from `canvasAssetSchema.ts`:

```typescript
import { extractShotTimelineArtifacts } from "../src/routes/canvas/v2/import-from-dir";
import { validateGraphNodes } from "../src/lib/canvasAssetSchema";

// Inside main():
const { nodes, links } = await extractShotTimelineArtifacts(manifest, FIXTURE, path.join(FIXTURE, "asset.json"));

// CANVAS-01 (assert A): structure
assert(nodes.filter((n) => n.type === "zone").length === 1, "exactly 1 zone");
assert(nodes.filter((n) => n.type === "audio").length === 3, "exactly 3 audio stems");
assert(nodes.filter((n) => n.type === "video").length === 1, "exactly 1 master video");
assert(nodes.filter((n) => n.type === "storyboard").length > 0, "≥1 storyboard");

// CANVAS-02 (assert B/C): sequence edges
const seqEdges = links.filter((l: any) => l.data?.linkType === "sequence");
assert(seqEdges.length === storyboards.length - 1, `sequence edges = N-1`);

// CANVAS-03 (assert D/E): Zod strictness preserved
const errors = validateGraphNodes(nodes as any);
assert(errors.length === 0, "all nodes pass per-type Zod", errors.map((e) => `${e.nodeId}: ${e.errors}`).join(" | "));
```

For the additive-only assertion (CANVAS-03), RESEARCH.md L666-686 gives the exact `git diff --name-only origin/master..HEAD -- packages/infinite-canvas/` shape — clone verbatim.

---

### `scripts/fixtures/shot-timeline-ep01/` (test fixture, file-I/O)

**Analog:** `scripts/fixtures/sample-manifest.json` (in-repo, single-JSON fixture format) — but the new fixture is a **multi-file directory tree**, mirroring the producer's real output directory shape.

**Source (downsample target):** `/data/workspace/kais-shot-timeline/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/`

#### Fixture directory shape to produce

```text
scripts/fixtures/shot-timeline-ep01/
├── asset.json              # ~600 B, copy verbatim from producer (the manifest itself is tiny)
├── shots.json              # ~8 KB, copy verbatim (93 shots, schema locked)
├── audio_analysis.json     # ~50 KB, copy verbatim
├── transcript.json         # ~16 KB, copy verbatim
├── frames.json             # 7.6 MB → DOWNSAMPLE (see below)
├── prompts.json            # ~77 KB, copy verbatim
├── video.mp4               # ~46 MB → DOWNSAMPLE to ~1s silent stub via ffmpeg
└── stems/
    ├── vocals.wav          # ~70 MB → DOWNSAMPLE to ~1s silent via ffmpeg
    ├── drums.wav           # ~70 MB → DOWNSAMPLE
    └── other.wav           # ~70 MB → DOWNSAMPLE
```

#### asset.json — the manifest that drives the helper (copy verbatim)

This is the producer's real output (verified at the source path above):

```json
{
  "schema_version": "1",
  "asset_type": "shottimeline",
  "source": {
    "video_filename": "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。.mp4",
    "duration_sec": 308.352
  },
  "generator": {
    "tool": "kais-shot-timeline",
    "version": "63965d7",
    "generated_at": "2026-07-20T14:56:17Z"
  },
  "data": {
    "shots": "shots.json",
    "audio_analysis": "audio_analysis.json",
    "transcript": "transcript.json",
    "frames": "frames.json",
    "prompts": "prompts.json"
  },
  "media": {
    "video": "video.mp4",
    "stems": {
      "vocals": "stems/vocals.wav",
      "drums": "stems/drums.wav",
      "other": "stems/other.wav"
    }
  }
}
```

#### Downsample strategy (per RESEARCH.md Open Question 3 + Pitfall 4)

Producer real sizes (verified this session via `wc -c`):
- `frames.json` 7.6 MB (base64 thumbnails) — keep first 5 shots only, drop the rest (still exercises the data URI → `thumbnailUrl` path)
- `video.mp4` ~46 MB — generate 1s silent 1280x720 stub via `ffmpeg -f lavfi -i color=size=1280x720:rate=24:duration=1 -f lavfi -i anullsrc -c:v libx264 -c:a aac -shortest video.mp4`
- `stems/*.wav` ~70 MB each — generate 1s silent PCM via `ffmpeg -f lavfi -i anullsrc=r=16000:a=1 -t 1 -q:a 0 stems/vocals.wav` (and same for drums/other)

Total fixture size after downsample: < 1 MB (git-friendly, no LFS needed). Verify script's ffprobe call still returns a real `1280x720` resolution; Zod passes because `min(1)`.

#### Existing in-repo fixture format (analog lines 1-57 of sample-manifest.json)

The existing fixture format is a flat single-JSON list of nodes — Phase 3's fixture diverges by being a **directory of producer-format files**. The new fixture is NOT consumed by `verify-import-roundtrip.ts`; it's consumed only by the new `verify-canvas-shot-timeline.ts`. So strict format parity is not required; the only invariant is that the directory shape matches what `extractShotTimelineArtifacts` expects (asset.json at root + data JSON paths relative to root + media paths relative to root).

```json
{
  "phase_id": "phase44_fixture",
  "phase": "p44",
  "nodes": [ /* ... node objects with params.* ... */ ],
  "edges": []
}
```

---

## Shared Patterns (cross-cutting)

### Zone → Summary → Artifact tree construction
**Source:** `src/routes/canvas/v2/import-from-dir.ts` L592-835 (`buildPhaseTree`)
**Apply to:** the new `extractShotTimelineArtifacts` helper — must emit exactly this 3-level structure (one zone, one summary, N artifact children) plus zone→summary + zone→artifact `dataType:"output"` links. The autoLayout on the frontend (`packages/infinite-canvas/src/utils/autoLayout.ts:92-100`) groups children by shared `data.phase` + `phaseIndex`, so all sub-nodes MUST share the same `phaseIndex` (i.e. live under one phase prefix).

**Concrete skeleton (lines 608-625 for zone; 644-654 for zone→summary link):**
```typescript
const zoneNode: FlowNodeV2 = {
  id: phasePrefix,                         // "p13"
  type: "zone" as any,
  branchId: "main",
  phaseIndex: laneIndex + 1,
  phaseName: def.label,
  position: { x: baseX, y: 0 },
  size: { width: ZONE_WIDTH, height: ZONE_HEIGHT },
  state: "success",
  data: { label: def.label, phase: def.phaseGroup, state: "success" },
};
// zone → summary link
links.push({
  id: `zl2-${phasePrefix}-sum-${phasePrefix}`,
  source: phasePrefix,
  target: `sum-${phasePrefix}`,
  branchId: "main",
  dataType: "output",
});
```

### Media URL normalization via fsToOssUrl
**Source:** `src/routes/canvas/v2/import-from-dir.ts` L174-192
**Apply to:** every audio/video stem path in the new helper. The function depends on the module-scoped `_workdirToOss` global set at `scanAndBuildTree` L1235 — so the helper MUST be invoked from within `scanAndBuildTree`'s call chain (don't call from outside without setting `_workdirToOss` first).

```typescript
// Idiom (mirror from itemToArtifact L391-393 and artifactsFromMediaFiles L494):
const ossUrl = fsToOssUrl(absPath);
art.filePath = ossUrl || absPath;   // never null — fall back to raw path
```

### Zod per-type strictness (do NOT modify)
**Source:** `src/lib/canvasAssetSchema.ts` L51-119 (`assetDataSchemas`) + L194-204 (`EXPECTED_PARAM_FIELDS_BY_TYPE`)
**Apply to:** the helper must emit `data` fields that satisfy these schemas WITHOUT modifying them. Required keys to synthesize per child type:

| Node type | Required fields (must be in `node.data`) |
|-----------|------------------------------------------|
| zone | (none — structural pass-through, L122) |
| storyboard | `label`, `shot_id`, `shot_type`, `duration_sec` (L97-106) |
| audio | `filePath`, `shot_id`, `engine`, `duration_sec` (L53-61) |
| video | `filePath`, `shot_id`, `engine`, `duration_sec`, `resolution` (L64-73) |

Test assertion (for verify script):
```typescript
import { validateGraphNodes } from "../src/lib/canvasAssetSchema";
const errors = validateGraphNodes(nodes);
assert(errors.length === 0, "all nodes pass per-type Zod", JSON.stringify(errors));
```

### Sequence edge emission shape
**Source:** `packages/infinite-canvas/src/utils/flowDataMapper.ts` L163-172 (frontend precedent) + `packages/infinite-canvas/src/components/edges/CanvasEdge.tsx` L60-75 (renderer hard-recognizes `linkType === 'sequence'`)
**Apply to:** the helper, after constructing all storyboard children, sort by `shot_id` ascending and emit N-1 edges between consecutive pairs.

```typescript
const sbSorted = storyboardNodes.sort((a, b) =>
  Number((a.data as any).shot_id) - Number((b.data as any).shot_id)
);
for (let i = 1; i < sbSorted.length; i++) {
  links.push({
    id: `seq-${sbSorted[i - 1].id}-${sbSorted[i].id}`,
    source: sbSorted[i - 1].id,
    target: sbSorted[i].id,
    branchId: "main",
    dataType: "data",
    data: { linkType: "sequence" },
  } as FlowLinkV2);
}
```

**Critical shape details:**
- `dataType: "data"` (NOT `"output"` like zone→child links) — matches flowDataMapper L170 exactly
- `data: { linkType: "sequence" }` — hard-recognized at `CanvasEdge.tsx:60` to render blue solid stroke + arrow marker
- The TypeScript `FlowLinkV2` interface (flowgraph-v2.ts:45-53) doesn't declare `data`, but the SQLite roundtrip preserves extra keys (load-v2 rowToLink uses spread). The `as FlowLinkV2` cast matches the codebase's existing L611 `as any` discipline.

### Bootstrap persistence via appendAndSync
**Source:** `src/lib/canvasEventStore.ts` L203-209 + caller in `import-from-dir.ts` L1393-1405 (replace) and L1465-1477 (merge)
**Apply to:** NONE — Phase 3 does NOT add new persistence code. The new helper's `{ nodes, links }` output flows through the existing `scanAndBuildTree → appendAndSync` pipeline unchanged. This is a "reuse, don't touch" pattern.

```typescript
// canvasEventStore.ts L203-209 — exact signature, do not modify:
export async function appendAndSync(input: AppendInput): Promise<AppendResult> {
  const result = await appendEvents(input);
  if (!result.duplicated) {
    await recomputeGraph(input.projectId, input.episodesId);
  }
  return result;
}
// AppendInput shape (L11-17): { projectId, episodesId, clientId, source?, events: [{ type, nodeId?, payload }] }
```

### Subprocess convention for ffprobe (lazy stdlib import)
**Source:** codebase convention (CLAUDE.md "Import Organization" — "deferred imports for optional/heavy deps"). The producer repo also uses this pattern (`audio/transcribe.py:69,94` lazy Whisper import, `detectors/detect_v3b.py:100` lazy `import cv2`).
**Apply to:** `extractShotTimelineArtifacts`'s resolution-probe helper. Pattern: dynamic `import("child_process")` inside the function body, NOT a top-level import. This isolates the ffprobe dependency to the one function that needs it.

```typescript
async function probeResolution(videoPath: string): Promise<string> {
  try {
    const { execFile } = await import("child_process");
    const { promisify } = await import("util");
    const execFileP = promisify(execFile);
    const { stdout } = await execFileP("ffprobe", [
      "-v", "quiet", "-select_streams", "v:0",
      "-show_entries", "stream=width,height",
      "-of", "csv=p=0:s=x", videoPath,
    ]);
    return stdout.trim() || "0x0";
  } catch {
    return "0x0";   // Zod min(1) still passes; frontend renders raw value
  }
}
```

### Additive-only invariant guard (CANVAS-03 enforcement)
**Source:** none in production code (this is a Phase 3 verification need); pattern from RESEARCH.md L666-686
**Apply to:** `verify-canvas-shot-timeline.ts` as a runtime assertion that the worktree diff doesn't touch forbidden areas.

```typescript
import { execSync } from "node:child_process";

const treeDiff = execSync(
  `git diff --name-only origin/master..HEAD -- packages/infinite-canvas/`,
  { cwd: "/data/workspace/kst-canvas-consumer", encoding: "utf8" },
).trim();
assert(treeDiff === "", "CANVAS-03: packages/infinite-canvas/ diff is empty", treeDiff || "(empty)");

const schemaDiff = execSync(
  `git diff origin/master..HEAD -- src/lib/canvasAssetSchema.ts`,
  { cwd: "/data/workspace/kst-canvas-consumer", encoding: "utf8" },
).trim();
// Allow zero diff OR comment-only changes; FORBID new .optional() strictness relaxations
assert(!/\.optional\(\)/.test(schemaDiff.replace(/\/\/.*$/gm, "")),
  "CANVAS-03: no new .optional() in canvasAssetSchema.ts");
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every new/modified file has a concrete in-repo analog. `extractShotTimelineArtifacts` is self-referential to its own file's `buildPhaseTree`; the verify script has a byte-for-byte template; the fixture has both a format analog (`sample-manifest.json`) and a real-data source (producer ep01 output). |

**Partial-match caveats worth flagging to planner:**
1. The new helper's **parallel tree-builder fallback** (RESEARCH Pattern 2 Solution B, if Solution A is rejected) has NO in-repo analog — it would be ~80 lines of duplicated `buildPhaseTree` logic. Planner should prefer Solution A (additive `RawArtifact.canvasType` + 1-line `buildPhaseTree` change) precisely because Solution B introduces untested duplication.
2. **Sequence-edge emission at the backend** has no in-repo analog — `flowDataMapper.ts:163-172` does this on the frontend (consumer side of the SQLite row), but Phase 3 is the first backend emitter. The shape itself is locked (CanvasEdge.tsx:60 hard-coded), so the risk is "doing it for the first time" rather than "no pattern to follow".

---

## Metadata

**Analog search scope:**
- `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/` (full directory)
- `/data/workspace/kst-canvas-consumer/src/lib/` (canvasAssetSchema.ts, canvasEventStore.ts)
- `/data/workspace/kst-canvas-consumer/src/types/` (flowgraph-v2.ts, flowgraph-v2-schema.ts)
- `/data/workspace/kst-canvas-consumer/scripts/` (all verify-*.ts scripts + fixtures/)
- `/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/utils/flowDataMapper.ts` + `components/edges/CanvasEdge.tsx`
- `/data/workspace/kais-shot-timeline/output/虫虫武侠…第01话…/` (producer real output for fixture)

**Files scanned:** 8 production files + 1 fixture analog + 1 producer source directory (10 distinct sources total, all read in full)

**Pattern extraction date:** 2026-07-21
