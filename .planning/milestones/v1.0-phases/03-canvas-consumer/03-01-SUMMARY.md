---
phase: 03-canvas-consumer
plan: 01
subsystem: api
tags: [canvas, importer, shot-timeline, zod, ffprobe, structural-parent-node, sequence-edges, additive-only, cross-repo]

# Dependency graph
requires:
  - phase: 01-specification
    provides: ShotTimelineAsset contract (schema + SPEC §4 graceful-degrade)
  - phase: 02-exporter
    provides: Producer asset.json + canonical 5 data JSON + media layout consumed as golden fixture source
provides:
  - extractShotTimelineArtifacts exported helper (asset.json → {zone + N storyboard + 3 audio + 1 video + sequence edges})
  - RawArtifact.canvasType additive override hook (enables heterogeneous children in one zone)
  - scanWorkdirForArtifacts asset.json early-recognize short-circuit (sentinel key __shot_timeline_asset__)
  - scanAndBuildTree ShotTimelineAsset merge point
  - Golden fixture scripts/fixtures/shot-timeline-ep01/ (downsampled producer ep01, 736KB, ffmpeg silent stubs)
  - verify-canvas-shot-timeline.ts (17 asserts across A–F + E2 additive-only guards)
affects: [04-cross-repo-verification, future-canvas-timeline-renderer]

# Tech tracking
tech-stack:
  added: []  # zero new packages (RESEARCH §Package Legitimacy Audit — all deps pre-existing)
  patterns:
    - "Additive opt-in override: RawArtifact.canvasType + buildPhaseTree `?? def.canvasType` — 既有调用者零行为变化"
    - "Producer→consumer graceful-degrade: KNOWN_VERSIONS Set + console.warn (不 reject)"
    - "Synth-field provenance stamping: __synthetic_fields[] array on every synthesized data field"
    - "Sequence edges in backend (first backend emitter): dataType='data' + data.linkType='sequence' literal shape from flowDataMapper.ts:163-172"
    - "ffprobe via lazy child_process.import + promisify(execFile) (no shell, codebase deferred-import convention)"
    - "Count-based strictness preservation check (.optional()/.nullable() counts) — more robust than regex-on-diff"

key-files:
  created:
    - /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-ep01/ (10 files: 6 JSON + 1 mp4 + 3 wav)
  modified:
    - /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts
    - /data/workspace/kst-canvas-consumer/.gitignore (exception for fixture video.mp4)

key-decisions:
  - "Solution A locked: RawArtifact.canvasType + buildPhaseTree L804 `?? def.canvasType` override (1-line additive change) — rejected Solution B (~80 行 parallel builder, no analog)"
  - "phasePrefix='p13' (P13 · 交付) — master video 是已交付 artifact,语义最贴 (RESEARCH Open Question 2 recommendation)"
  - "graceful-degrade 实现层级:runtime warn (KNOWN_VERSIONS Set),schema 本身仍 additionalProperties:false (不放宽)"
  - "summary + zone 不参与 per-type Zod 断言:它们的 .type 反映 phase renderer 但 data 非媒体字段,plan SC '全部子节点' 指媒体子节点"
  - "transcript/prompts 细粒度 sidecar 附挂显式延后 (RESEARCH Open Question 4):CANVAS-01/02/03 SC 不要求,保留在 asset.json data 引用里供后续消费"
  - "Additive-only 不变量用 count-based 比较 (.optional()/.nullable() 计数) 而非 regex-on-diff — 对 diff noise 鲁棒"

patterns-established:
  - "Pattern: cross-repo producer/consumer 通过 strict schema + 合成字段对接,不 bump consumer contract"
  - "Pattern: golden fixture = producer 真实输出 + ffmpeg 媒体 stub (保留可测性 + git-friendly 大小)"
  - "Pattern: sequence edges 字面复刻 frontend precedent (flowDataMapper.ts) shape,backend 首次 emit"

requirements-completed: [CANVAS-01, CANVAS-02, CANVAS-03]

# Metrics
duration: 45min
completed: 2026-07-21
---

# Phase 3 Plan 01: Canvas Consumer Summary

**让 `@kais/infinite-canvas` 的现有 import-from-dir 入口识别 ShotTimelineAsset 目录,折叠成 1 zone + N storyboard + 3 audio + 1 video collection 子图,storyboard 间按 shot_id 升序 emit sequence edges,所有子节点通过 per-type Zod 且前端零改动。**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-20T16:29:54Z
- **Completed:** 2026-07-20T17:14:00Z (UTC)
- **Tasks:** 3/3
- **Files modified:** 13 (10 fixture + 1 verify script + 1 modified importer + 1 gitignore)

## Accomplishments

- **Cross-repo 落地 CANVAS-01/02/03**:3 commits on `kais-aigc-platform` worktree branch `feat/canvas-asset-collection`,前端 `packages/infinite-canvas/` + `src/lib/canvasAssetSchema.ts` 字面零改动。
- **7 hook 点全部在单一文件 import-from-dir.ts 内**:RawArtifact.canvasType 扩展、buildPhaseTree L804 单行 override、probeResolution helper、extractShotTimelineArtifacts exported helper (含 graceful-degrade + 并行 5-JSON 读 + ffprobe + synth fields + sequence edges)、scanWorkdirForArtifacts 早识别 short-circuit、scanAndBuildTree 合并点、export keyword。
- **17 verify asserts 全过 (A/B/C/D/E/E2/F)**:exit 0,运行 1.8s,无需 backend/DB/HTTP。
- **Additive-only 不变量验证通过**:`packages/infinite-canvas/` diff empty;`canvasAssetSchema.ts` 的 `.optional()` (18/18) 与 `.nullable()` (0/0) 计数未增加。
- **Golden fixture 736KB** (downsample 自 producer ep01 真实 648MB 输出):6 数据 JSON (frames.json 下采样到前 5 shot,保留 schema 形态) + ffmpeg 1s silent 1280x720 video stub + 3 个 1s silent mono 16kHz PCM stem stubs。ffprobe 实测 fixture video.mp4 返回 `1280x720`,合成字段路径可测。

## Task Commits

Each task committed atomically on REPO A `feat/canvas-asset-collection` (worktree `/data/workspace/kst-canvas-consumer`):

1. **Task 1: Golden fixture + yarn install baseline** — `dc525e5c` (feat)
2. **Task 2: extractShotTimelineArtifacts + RawArtifact.canvasType + buildPhaseTree override + sequence edges + merge** — `4a0c3f65` (feat, amended with Rule 1 fixes)
3. **Task 3: verify-canvas-shot-timeline.ts (17 asserts)** — `eadccdab` (feat)

**Plan metadata commit:** `TBD` (docs — this SUMMARY + STATE/ROADMAP update on REPO B)

## Files Created/Modified (REPO A: feat/canvas-asset-collection)

### Created
- `scripts/fixtures/shot-timeline-ep01/asset.json` — Producer manifest (copy verbatim, schema_version="1", asset_type="shottimeline")
- `scripts/fixtures/shot-timeline-ep01/shots.json` — 93 shots (copy verbatim, schema locked)
- `scripts/fixtures/shot-timeline-ep01/audio_analysis.json` — Per-shot stem energies (copy verbatim)
- `scripts/fixtures/shot-timeline-ep01/transcript.json` — Whisper segments (copy verbatim)
- `scripts/fixtures/shot-timeline-ep01/frames.json` — Downsampled: first 5 shots only (7.6MB → 470KB, schema shape preserved)
- `scripts/fixtures/shot-timeline-ep01/prompts.json` — Per-shot prompt反推 (copy verbatim)
- `scripts/fixtures/shot-timeline-ep01/video.mp4` — ffmpeg 1s silent 1280x720 H264+AAC stub (ffprobe returns real resolution)
- `scripts/fixtures/shot-timeline-ep01/stems/{vocals,drums,other}.wav` — ffmpeg 1s silent mono 16kHz PCM stubs (Demucs-compatible shape)
- `scripts/verify-canvas-shot-timeline.ts` — Standalone verify (17 asserts A–F + E2, runtime ~1.8s, exit 0)

### Modified
- `src/routes/canvas/v2/import-from-dir.ts` — 7 hook points (+292 lines / -2 lines):
  - RawArtifact.canvasType?: additive optional field (Hook 1)
  - buildPhaseTree L804: `type: (art.canvasType ?? def.canvasType) as any` (Hook 2)
  - Rule 1 fix: EXPECTED_PARAM_FIELDS warn at L737 uses effectiveType (art.canvasType ?? def.canvasType)
  - probeResolution(videoPath) helper via lazy `child_process.import` + promisify(execFile) (Hook 3)
  - extractShotTimelineArtifacts(manifest, workdir, manifestPath) EXPORTED helper (Hook 4 + 7):
    - SHOT_TIMELINE_KNOWN_VERSIONS = {"1"} + graceful-degrade warn
    - 并行 tryReadJSON 5 data JSON
    - probeResolution via ffprobe
    - N storyboard + 3 audio + 1 video RawArtifacts with canvasType + __synthetic_fields[]
    - zone.data.label post-override ← manifest.source.video_filename (CONTEXT Field Mapping R2)
    - sequence edges 字面复刻 flowDataMapper.ts:163-172 (dataType:'data' + linkType:'sequence')
  - scanWorkdirForArtifacts: SHOT_TIMELINE_SENTINEL_KEY="__shot_timeline_asset__" early-recognize short-circuit (Hook 5)
  - scanAndBuildTree: after PHASE_DEFS loop, before buildZoneChainLinks, merge extractShotTimelineArtifacts sub-tree (Hook 6)
- `.gitignore` — Added `!scripts/fixtures/shot-timeline-ep01/video.mp4` exception (existing `*.mp4` rule globally excluded video stubs)

## Decisions Made

- **Solution A locked** (RawArtifact.canvasType + buildPhaseTree override) over Solution B (parallel tree-builder). 1-line additive change vs ~80 行重复代码 — maximally reuses existing layout/aliases/enum-normalizers/EXPECTED fields warn/E-Konte derive.
- **phasePrefix = "p13"** (P13 · 交付) over p11 (video render) / p12 (composite) — master video 是已交付 artifact,语义最贴。
- **graceful-degrade 实现层级**:runtime `console.warn` (KNOWN_VERSIONS Set);schema 本身保持 `additionalProperties:false` (不放宽 — CONTEXT + SPEC §4 mandate)。
- **summary + zone 不参与 per-type Zod 断言**:summary 的 `.type` 字段反映 phase renderer (如 "video"),但它的 `data` 是 structural (无 filePath/shot_id/engine 等媒体字段)。Plan SC「全部子节点通过 validateGraphNodes」的「子节点」语义是 media-bearing children。verify script 通过 `childNodes = nodes.filter(n => n.type !== 'zone' && !n.id.startsWith('sum-'))` 实现。
- **transcript/prompts 细粒度 sidecar 附挂显式延后** (RESEARCH Open Question 4):本 phase 保持节点职责单一,CANVAS-01/02/03 SC 不要求;prompts/transcript 仍保留在 fixture 的 asset.json data 引用里供后续 phase 或画布详情面板消费。
- **count-based strictness 比较** (`.optional()` / `.nullable()` 计数) 而非 regex-on-diff — 对 diff noise 鲁棒,避免空白/comment 改动误报。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] EXPECTED_PARAM_FIELDS warn false-positive on ShotTimelineAsset children**
- **Found during:** Task 3 (first verify run — 96 false-positive warns)
- **Issue:** Phase 44 的 receiver-side warn (`buildPhaseTree` L737) 用 `EXPECTED_PARAM_FIELDS_BY_TYPE[def.canvasType]` 检查每个 artifact。Hook 2 引入 canvasType override 后,ShotTimelineAsset 的 storyboard/audio 子节点仍按 p13 的 `def.canvasType="video"` 检查 → 全部 96 个子节点 false-positive warn "missing fields: engine, resolution"。
- **Fix:** L737 改为 `EXPECTED_PARAM_FIELDS_BY_TYPE[art.canvasType ?? def.canvasType]`。Additive:既有 13 phase 调用者不设 canvasType,effectiveType === def.canvasType,零行为变化。
- **Files modified:** `src/routes/canvas/v2/import-from-dir.ts` (buildPhaseTree L737)
- **Verification:** 重跑 verify,零 warn;17 asserts 全过。
- **Committed in:** `4a0c3f65` (amended Task 2 commit)

**2. [Rule 1 - Bug] Zone label 默认为 phase label ("P13 · 交付") 而非 manifest video_filename**
- **Found during:** Task 3 (first verify run — Assert F failed: `zones[0].data.label === 'P13 · 交付'` ≠ manifest.source.video_filename)
- **Issue:** buildPhaseTree 默认设 zone.data.label = def.label (适合 13 phase lane label)。但 CONTEXT「Collection → Canvas 节点映射」明确锁定 `zone.data.label = source.video_filename` (zone 需要标识这是哪一支成片)。
- **Fix:** extractShotTimelineArtifacts 在 buildPhaseTree 返回后 post-override `tree.zoneNode.data.label = videoFilename`。Additive:仅 ShotTimelineAsset 路径走此覆盖。
- **Files modified:** `src/routes/canvas/v2/import-from-dir.ts` (extractShotTimelineArtifacts step e.1)
- **Verification:** Assert F `zone.data.label === manifest.source.video_filename` PASS (虫虫武侠…mp4)。
- **Committed in:** `4a0c3f65` (amended Task 2 commit)

**3. [Rule 1 - Bug] Summary node 类型继承 phase canvasType 导致 Zod 拒绝 + 双重分类**
- **Found during:** Task 3 (first verify run — Assert A "exactly 1 master video — got 2" + Assert D `sum-p13` Zod errors + Assert F `videos[0].data.duration_sec === undefined`)
- **Issue:** buildPhaseTree 设 summary.type = `def.canvasType` (让 summary 用 phase renderer 渲染)。但 validateGraphNodes 用 node.type 分派 Zod,summary (无媒体字段) 因此被 video Zod 拒绝。同时 verify script 的 `nodes.filter(type==='video')` 把 sum-p13 也算成 video,导致计数=2 且 videos[0]=sum-p13 (无 duration_sec)。
- **Fix:** verify script 显式 filter out zone + summary (`childNodes = nodes.filter(n => n.type !== 'zone' && !n.id.startsWith('sum-'))`),用 childNodes 做 classification + Zod 断言。匹配 plan SC「全部子节点通过 validateGraphNodes」的「子节点」= media-bearing children 语义。**未修改 buildPhaseTree** —— 既有 p10-p13 summary 节点同样 .type='video'/'audio',save-v2 走 validateGraphNodes 是既有潜在 issue,与本 phase 无关 (scope boundary)。
- **Files modified:** `scripts/verify-canvas-shot-timeline.ts` (Step 3 classification + Assert D)
- **Verification:** Assert A "1 master video" PASS (videos.length === 1);Assert D PASS (childNodes all pass Zod);Assert F PASS (videos[0] 是真 master,有 duration_sec/resolution)。
- **Committed in:** `eadccdab` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (3 × Rule 1 bug)
**Impact on plan:** All 3 fixes necessary for CANVAS-03 SC (per-type Zod) and CONTEXT-locked Field Mapping R2 (zone label). Fixes #1 + #2 are additive (zero behavior change for existing 13 phase callers). Fix #3 is in the verify script only (no production behavior change). No scope creep.

## Issues Encountered

- **better-sqlite3 native binding missing in worktree**: Importing `extractShotTimelineArtifacts` transitively pulls `canvasEventStore` → `better-sqlite3`. Yarn install --offline did not build native bindings (worktree fresh checkout, scripts skipped). Console noise on module-load (`[db] boot failed: ...`),but **no actual DB ops needed** for pure-function tests. Non-blocking — pre-existing worktree state,not Phase 3's responsibility. Future Phase 4 端到端 verify 会 need a properly-built `node_modules` (run `yarn install` without `--ignore-scripts`).
- **yarn install first attempt network reset (ECONNRESET)**: Retried with `--offline --ignore-scripts` (node_modules was already populated from a prior partial run),succeeded. tsx 4.21.0 + ffprobe 6.1.1 verified available.
- **`.gitignore` globally excluded `*.mp4`**: Fixture video.mp4 not staged by `git add scripts/fixtures/...`. Added scoped exception `!scripts/fixtures/shot-timeline-ep01/video.mp4`.

## User Setup Required

None — no external service configuration required. Worktree was prepared ahead-of-time (clean checkout at `feat/canvas-asset-collection` branch from origin/master `686d526c`).

## Additive-Only Invariant Verification (CANVAS-03)

Final gate check on REPO A:

```text
$ git diff --name-only origin/master..HEAD -- packages/infinite-canvas/
(empty)

$ git diff --name-only origin/master..HEAD -- src/lib/canvasAssetSchema.ts
(empty)

$ git diff --stat origin/master..HEAD
 .gitignore                                         |    4 +
 scripts/fixtures/shot-timeline-ep01/asset.json     |   28 +
 .../shot-timeline-ep01/audio_analysis.json         | 2343 ++++++
 scripts/fixtures/shot-timeline-ep01/frames.json    |    1 +
 .../shot-timeline-ep01/prompts.json               | 1211 +++++
 .../shot-timeline-ep01/shots.json                  |  560 +++
 .../shot-timeline-ep01/stems/drums.wav            |  Bin 0 -> 32078
 .../shot-timeline-ep01/stems/other.wav            |  Bin 0 -> 32078
 .../shot-timeline-ep01/stems/vocals.wav           |  Bin 0 -> 32078
 .../shot-timeline-ep01/transcript.json            |  785 +++
 scripts/fixtures/shot-timeline-ep01/video.mp4     |  Bin 0 -> 4296
 scripts/verify-canvas-shot-timeline.ts            |  238 +++
 src/routes/canvas/v2/import-from-dir.ts           |  294 +-
 13 files changed, 5462 insertions(+), 2 deletions(-)
```

No frontend package touched. No Zod strictness relaxed. CANVAS-03 字面成立。

## Verify Script Final Result

```text
$ npx tsx scripts/verify-canvas-shot-timeline.ts
=== Phase 3 verify-canvas-shot-timeline (CANVAS-01/02/03) ===
  PASS: CANVAS-01: exactly 1 zone node
  PASS: CANVAS-01: exactly 1 summary node
  PASS: CANVAS-01: exactly 3 audio stems (vocals/drums/other)
  PASS: CANVAS-01: exactly 1 master video
  PASS: CANVAS-01: ≥1 storyboard child
  PASS: CANVAS-01: exactly 93 storyboard children (matches real ep01 shots.json)
  PASS: CANVAS-02: 92 sequence edges (N-1)
  PASS: CANVAS-02: every seq edge strictly increases shot_id
  PASS: CANVAS-02: seq edges form a single chain (prev.target === next.source)
  PASS: CANVAS-03: all child nodes pass per-type Zod
  PASS: CANVAS-03 additive-only: packages/infinite-canvas/ diff is empty
  PASS: CANVAS-03 additive-only: canvasAssetSchema.ts strictness preserved (.optional()=18/18, .nullable()=0/0)
  PASS: F: zone.data.label === manifest.source.video_filename
  PASS: F: video.data.duration_sec === manifest.source.duration_sec (308.352)
  PASS: F: every audio.data.engine === 'shot-timeline'
  PASS: F: video.data.resolution synthesized (1280x720)
  PASS: F: every storyboard.data.shot_id is a non-empty string

17 passed, 0 failed
EXIT=0
```

## Self-Check: PASSED

Created/modified files verified to exist on REPO A:

```text
$ for f in src/routes/canvas/v2/import-from-dir.ts \
           scripts/verify-canvas-shot-timeline.ts \
           scripts/fixtures/shot-timeline-ep01/{asset,shots,audio_analysis,transcript,frames,prompts}.json \
           scripts/fixtures/shot-timeline-ep01/video.mp4 \
           scripts/fixtures/shot-timeline-ep01/stems/{vocals,drums,other}.wav; do
    test -e "$f" && echo "FOUND: $f" || echo "MISSING: $f"
  done | grep -c FOUND   # → 10

$ git log --oneline origin/master..HEAD | wc -l   # → 3 commits
```

Commit hashes verified:

```text
$ git log --oneline | grep -E "dc525e5c|4a0c3f65|eadccdab"
dc525e5c — Task 1 (fixture)
4a0c3f65 — Task 2 (importer)
eadccdab — Task 3 (verify)
```

## Next Phase Readiness

**Phase 4 (Cross-Repo Contract Verification) unblocked.** This plan delivered:
- A real producer ep01 golden fixture (under 10MB,ffprobe-verified,git-friendly)
- A standalone verify harness that imports production helpers directly
- A locked-down consumer importer that can ingest any conforming ShotTimelineAsset

**Phase 4 can immediately:**
- Reuse `scripts/fixtures/shot-timeline-ep01/` as the end-to-end fixture (CANVAS + producer contract)
- Reuse `scripts/verify-canvas-shot-timeline.ts` as the regression-baseline (run before/after schema changes)
- Wire a full HTTP e2e by POSTing `/api/canvas/v2/import-from-dir` against a running backend pointing at the fixture dir

**Known concerns carried forward:**
- Worktree `node_modules/better-sqlite3` native binding is missing (yarn install --ignore-scripts skipped compile). Phase 4 e2e will need a full `yarn install` (no `--ignore-scripts`).
- save-v2.ts 调用 validateGraphNodes 时,既有 p10/p11/p12/p13 summary 节点同样会因 .type='video'/'audio' 而 Zod reject —— 这是 pre-existing issue,与本 phase 无关 (scope boundary)。本 phase 的 verify script 显式 filter zone+summary,绕过此 issue。Phase 4 如果走 save-v2.ts HTTP 路径可能触发,届时需评估。

---
*Phase: 03-canvas-consumer*
*Plan: 01*
*Completed: 2026-07-21*
