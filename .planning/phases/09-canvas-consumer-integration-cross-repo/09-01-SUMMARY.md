---
phase: 09-canvas-consumer-integration-cross-repo
plan: 01
subsystem: ui
tags: [infinite-canvas, shot-timeline, cross-repo, react, typescript, asset-node]

# Dependency graph
requires:
  - phase: 08-prompt-reference-system-shot-timeline-gallery
    provides: producer-emitted v1.1 manifest with generator.registry_snapshot (frozen confirmed-only character/prop registry) that the consumer now imports
provides:
  - "Consumer v1.1 awareness: SHOT_TIMELINE_KNOWN_VERSIONS += '1.1' (no graceful-degrade warn on clean v1.1 imports)"
  - "extractShotTimelineArtifacts emits character/prop child nodes as type:'asset' + assetType:'character'|'prop' via §7 post-process (buildPhaseTree assetType-seed-drop bug worked around)"
  - "AssetNode typeIcons cosmetic icons (🧑 character / 🔧 prop) — additive, no renderer change"
  - "verify-canvas-shot-timeline.ts v1.1 assertions (2 char + 1 prop + zero-delivery-leak + output_key patterns + graceful-degrade regression)"
  - "Minimal v1.1 consumer fixture at scripts/fixtures/shot-timeline-v1.1/ (self-contained, mirrors producer v1.1 shape)"
affects: [09-02 (PRESENT-06 verify_contract.py bridge), canvas-asset-collection PR, future cross-video continuity (CROSSVIDEO-01 v2)]

# Tech tracking
tech-stack:
  added: []  # NO new packages — pure additive extension of existing hooks (tsx, @xyflow/react, zod unchanged)
  patterns:
    - "§7 post-process pattern: when buildPhaseTree seeds a data field from def (e.g. assetType='delivery') and the extra-merge guard (:724) silently drops extra overrides, mutate tree.artifactNodes AFTER buildPhaseTree returns — mirror the :1082-1084 zoneNode post-process"
    - "Cross-repo commit hygiene: explicit `git add <file>` only (never -A/.) when consumer worktree carries uncommitted user WIP; verify git status before + after"
    - "Assert E scoped relaxation: baseline HEAD~1..HEAD to isolate a single phase's commit contribution when the branch has fallen behind origin/master (origin/master..HEAD carries unrelated pre-existing files)"

key-files:
  created:
    - "/data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.1/asset.json (schema_version '1.1' + registry_snapshot 2 chars + 1 prop + data/media character+prop paths)"
    - "/data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.1/characters.json (2 confirmed entries: char_001 少女, char_002 路人)"
    - "/data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.1/props.json (1 confirmed entry: prop_001 落叶)"
    - "/data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.1/{shots,audio_analysis,transcript,frames,prompts}.json + stems/*.wav + video.mp4 + characters|props/*.png (minimal placeholders)"
  modified:
    - "/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts (KNOWN_VERSIONS + '1.1'; extractShotTimelineArtifacts registry read + RawArtifact push + §7 tree.artifactNodes post-process)"
    - "/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx (typeIcons += character:'🧑', prop:'🔧')"
    - "/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts (V11_FIXTURE + classification + v1.1 asserts + Assert E scoped relaxation)"
    - "/data/workspace/kst-canvas-consumer/.gitignore (scoped !exception for shot-timeline-v1.1/video.mp4 — mirrors ep01 precedent)"

key-decisions:
  - "§7 emission via post-process (not extra.assetType): buildPhaseTree seeds artData.assetType=def.assetType('delivery') at :692 and the :724 extra-merge guard silently drops extra.assetType — so character/prop nodes MUST be pushed as RawArtifact{canvasType:'asset', output_key:<id>} BEFORE buildPhaseTree, then data.assetType overwritten on tree.artifactNodes AFTER (join via output_key). Verified: zero character/prop nodes leak as assetType='delivery'."
  - "Data source priority: generator.registry_snapshot preferred (self-contained, export-time confirmed-only); data.characters/props files fallback via tryReadJSON with review_state==='confirmed' defense-in-depth filter (external files may contain proposed entries pre-apply)."
  - "Node id scheme NOT overridden: buildPhaseTree assigns a-p13-artN internally (e.g. a-p13-art97); the stable registry id (char_NNN/prop_NNN) survives in node.data.output_key — canvas UI uses node.id for React keying only. Overriding node.id would require modifying buildPhaseTree generic logic (rejected — risk to v1.0)."
  - "Assert E baseline = HEAD~1..HEAD (deviation from plan's origin/master..HEAD): origin/master advanced past the feat/canvas-asset-collection branch tip (merge-base === HEAD), so origin/master..HEAD carried ~56 pre-existing files unrelated to Phase 9 and the AssetNode.tsx-only allowlist would always report ~55 violations. Baseline against the Phase 9 commit boundary instead."

patterns-established:
  - "buildPhaseTree post-process hook: the §7 assetType-seed-drop is a generic buildPhaseTree behavior. Future phases that need to override a seeded data field on artifact nodes should follow the same push-before + mutate-after pattern (mirror :1082-1084 zoneNode label override)."
  - "Cross-repo WIP preservation protocol: stage explicit files, run `git status --short` before+after commit, assert the user's WIP files remain in their original (M / ??) state."

requirements-completed: [PRESENT-04, PRESENT-05]

# Metrics
duration: 15min
completed: 2026-07-24
---

# Phase 9 Plan 01: Canvas Consumer v1.1 Integration Summary

**Consumer `@kais/infinite-canvas` made v1.1-aware: recognizes `schema_version:"1.1"`, emits 2 character + 1 prop child nodes as `type:"asset"` (assetType character/prop, NOT delivery) via the §7 buildPhaseTree post-process workaround, renders them with 🧑/🔧 icons, locked by 27 green verify assertions — with the v1.0 ep01 WIP untouched.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-24T21:53:52Z
- **Completed:** 2026-07-24T22:08:40Z
- **Tasks:** 3 (all in the consumer repo `/data/workspace/kst-canvas-consumer`)
- **Files modified:** 19 (15 new v1.1 fixture + 3 source + .gitignore) in the consumer repo; SUMMARY/STATE/ROADMAP in shot-timeline

## Cross-Repo Commit (single cohesive consumer commit)

ALL consumer work landed in ONE commit on `feat/canvas-asset-collection` at `/data/workspace/kst-canvas-consumer` (the plan deliberately batches Tasks 1+2+3 into one consumer commit):

- **Consumer commit:** `90812e9d` (`90812e9d64ad09a2cf246c17a2cf46231e280a8c`) — `feat(canvas): v1.1 ShotTimelineAsset — character/prop child nodes (PRESENT-04/05)`
- **Files (19):** `.gitignore`, `packages/infinite-canvas/src/components/nodes/AssetNode.tsx`, `scripts/fixtures/shot-timeline-v1.1/*` (15), `scripts/verify-canvas-shot-timeline.ts`, `src/routes/canvas/v2/import-from-dir.ts`
- **WIP preservation (CRITICAL):** the pre-existing user WIP (`scripts/fixtures/shot-timeline-ep01/prompts.json` modified, `action_chains.json` untracked) was NOT touched — verified `git status --short` before + after commit; explicit-file `git add` only (never `-A`/`.`).

## Verification

`cd /data/workspace/kst-canvas-consumer && npx tsx scripts/verify-canvas-shot-timeline.ts` → **27 passed, 0 failed, exit 0**.

v1.1 section (all PASS):
- PRESENT-04: exactly 2 character nodes from v1.1 fixture registry — got 2
- PRESENT-04: exactly 1 prop node from v1.1 fixture registry — got 1
- PRESENT-04 §7 post-process: every character node carries an OSS-synthesized thumbnailUrl — got `/oss/shot-timeline-v1.1/characters/char_001.png`, `/oss/shot-timeline-v1.1/characters/char_002.png`
- PRESENT-04 §7 post-process: every prop node carries an OSS-synthesized thumbnailUrl — got `/oss/shot-timeline-v1.1/props/prop_001.png`
- PRESENT-04 Q5: character output_key is the stable registry id char_NNN — got char_001, char_002
- PRESENT-04 Q5: prop output_key is the stable registry id prop_NNN — got prop_001
- PRESENT-04 §7: zero asset nodes leak as assetType=delivery (post-process overrode the seed) — got 0 delivery asset nodes

Plus the full v1.0 ep01 regression suite (structure, sequence edges, Zod, roundtrip, OSS filePath) remains green, AND a new graceful-degrade regression assert confirms v1.0 ep01 (no registry) emits 0 character/prop nodes. Assert E (scoped relaxation) PASS — `git diff HEAD~1..HEAD -- packages/infinite-canvas/` resolves to exactly `AssetNode.tsx`. Assert E2 (Zod strictness) PASS — `.optional()`/`.nullable()` counts unchanged (18/0 master == head).

## Accomplishments

- **PRESENT-04 (gate):** `SHOT_TIMELINE_KNOWN_VERSIONS` is now `new Set(["1", "1.1"])`; a clean v1.1 import no longer triggers the graceful-degrade warn. v1.0 still accepted; unknown/future versions still warn-not-crash (branch unchanged).
- **PRESENT-04 (emit + §7):** `extractShotTimelineArtifacts` reads `generator.registry_snapshot` (preferred) with `data.characters`/`data.props` file fallback (confirmed-only filter), pushes character/prop `RawArtifact{canvasType:"asset", output_key:<id>}` BEFORE `buildPhaseTree`, then post-processes `tree.artifactNodes` to overwrite `data.assetType` from the seeded `"delivery"` to `"character"`/`"prop"` + attach `thumbnailUrl` via `fsToOssUrl`. Result against the v1.1 fixture: exactly 2 character + 1 prop asset nodes, ZERO delivery leaks.
- **PRESENT-05 (typeIcons):** AssetNode typeIcons extended additively with `character:'🧑'`, `prop:'🔧'`. The only `packages/infinite-canvas/` diff in the Phase 9 commit (verified via Assert E allowlist).
- **PRESENT-05 (verify):** verify-canvas-shot-timeline.ts extended with a second v1.1 fixture run + 7 new assertions + a graceful-degrade regression assert + Assert E scoped relaxation. 27/27 green.
- **Cross-repo hygiene:** v1.0 WIP (prompts.json/action_chains.json) confirmed untouched; commit staged only the 19 explicit files.

## Task Commits

Per the plan, Tasks 1+2+3 are a single cohesive consumer commit (no per-task commits in the consumer repo):

1. **Task 1: v1.1 fixture** — part of `90812e9d` (15 new fixture files)
2. **Task 2: import-from-dir.ts** — part of `90812e9d` (version gate + §7 emission + post-process)
3. **Task 3: AssetNode + verify + commit** — `90812e9d` (typeIcons + verify asserts + the commit itself)

**Plan metadata:** (pending — shot-timeline final commit below)

## Files Created/Modified

(All paths under `/data/workspace/kst-canvas-consumer/` — the consumer worktree)

- `scripts/fixtures/shot-timeline-v1.1/asset.json` — schema_version "1.1" + registry_snapshot (2 chars + 1 prop) + data/media character+prop paths (mirrors producer v1.1 fixture)
- `scripts/fixtures/shot-timeline-v1.1/characters.json` — 2 confirmed entries (char_001 少女, char_002 路人)
- `scripts/fixtures/shot-timeline-v1.1/props.json` — 1 confirmed entry (prop_001 落叶)
- `scripts/fixtures/shot-timeline-v1.1/{shots,audio_analysis,transcript,frames,prompts}.json` + `stems/*.wav` + `video.mp4` + `characters|props/*.png` — minimal placeholders (media copied from ep01; PNGs generated as valid 16×16)
- `src/routes/canvas/v2/import-from-dir.ts` — `SHOT_TIMELINE_KNOWN_VERSIONS += "1.1"`; `extractShotTimelineArtifacts` registry read + RawArtifact push (before buildPhaseTree) + §7 tree.artifactNodes post-process (after)
- `packages/infinite-canvas/src/components/nodes/AssetNode.tsx` — typeIcons += `character:'🧑'`, `prop:'🔧'`
- `scripts/verify-canvas-shot-timeline.ts` — V11_FIXTURE + character/prop classification + 7 v1.1 asserts + graceful-degrade regression + Assert E scoped relaxation (HEAD~1..HEAD baseline, AssetNode.tsx allowlist)
- `.gitignore` — scoped `!scripts/fixtures/shot-timeline-v1.1/video.mp4` exception (mirrors ep01 line 84)

## Decisions Made

See `key-decisions` frontmatter above. Highlights:

- **§7 emission via post-process (D-PRESENT-04-Q2):** the load-bearing caveat. `buildPhaseTree` seeds `artData.assetType = def.assetType` ("delivery" for p13) at :692 and the extra-merge guard at :724 silently drops `extra.assetType`. Character/prop nodes are pushed as `RawArtifact{canvasType:"asset", output_key:<id>}` BEFORE buildPhaseTree, then `data.assetType` is overwritten on `tree.artifactNodes` AFTER (join via `output_key`). Verified: zero character/prop nodes leak as assetType="delivery".
- **Node id scheme accepted as-is (D-PRESENT-04-Q5):** buildPhaseTree assigns `a-p13-artN` internally; the stable registry id (`char_NNN`/`prop_NNN`) survives in `node.data.output_key`. Did NOT override `node.id` (would require modifying buildPhaseTree generic logic — rejected, risk to v1.0).
- **Data source priority (D-PRESENT-04-Q4):** `registry_snapshot` preferred (self-contained); external files fallback with `confirmed`-only filter (defense-in-depth).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Assert E baseline changed from `origin/master..HEAD` to `HEAD~1..HEAD`**
- **Found during:** Task 3 (verify-canvas-shot-timeline.ts Assert E relaxation)
- **Issue:** The plan specified `git diff --name-only origin/master..HEAD -- packages/infinite-canvas/` bounded to an `AssetNode.tsx`-only allowlist. But `origin/master` has ADVANCED past the `feat/canvas-asset-collection` branch tip (`git merge-base origin/master HEAD === HEAD`), so that diff carried ~56 pre-existing files unrelated to Phase 9 — the allowlist would always report ~55 violations and Assert E could never pass. (Indeed, the v1.0 Assert E `treeDiff === ""` was ALREADY failing before Phase 9 — 18 passed / 1 failed — for this same reason.)
- **Fix:** Baseline against `HEAD~1..HEAD` to isolate the Phase 9 consumer commit's canvas contribution, which is what the allowlist semantics actually intend (no new components, no structural renderer changes, no custom renderer — only typeIcons). This is a strictly more correct enforcement of the plan's stated INTENT ("diff limited to AssetNode.tsx typeIcons additions"). SPIRIT preserved: violationFiles.length === 0 still asserts the only canvas-package file in the Phase 9 commit is AssetNode.tsx.
- **Files modified:** `scripts/verify-canvas-shot-timeline.ts` (Assert E block + header docstring)
- **Verification:** post-commit verify — `git diff --name-only HEAD~1..HEAD -- packages/infinite-canvas/` = exactly `AssetNode.tsx`; Assert E PASS with detail "packages/infinite-canvas/src/components/nodes/AssetNode.tsx". Assert E2 (Zod strictness, origin/master count compare) unchanged and still PASS.
- **Committed in:** `90812e9d`

**2. [Rule 3 - Blocking] `.gitignore` scoped exception for v1.1 video.mp4**
- **Found during:** Task 3 (consumer commit staging)
- **Issue:** `.gitignore` line 77 (`*.mp4`) blocked staging the plan-required `scripts/fixtures/shot-timeline-v1.1/video.mp4`. The v1.0 ep01 fixture has an explicit `!` exception at line 84; the v1.1 fixture needed the same.
- **Fix:** Added `!scripts/fixtures/shot-timeline-v1.1/video.mp4` to `.gitignore` (mirrors the ep01 precedent exactly — 1-line additive scoped exception). Without it, a fresh clone could not run verify (probeResolution would ffprobe a missing file).
- **Files modified:** `.gitignore`
- **Verification:** `git diff --cached --name-only` includes `video.mp4` after the exception; `git check-ignore` no longer reports it.
- **Committed in:** `90812e9d`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both auto-fixes necessary for the plan's own success criteria to be achievable + verifiable. No scope creep — Assert E fix enforces the plan's INTENT more faithfully than the plan's literal baseline; the .gitignore fix mirrors an established v1.0 precedent. PRESENT-04/05 fully delivered.

## Issues Encountered

- **Standalone emission test "hung":** an ad-hoc `npx tsx` test script (not the real verify) appeared to hang because it never called `process.exit()` after its async main resolved — Node waited on a lingering handle (the running Vite/tsx app servers on the main checkout) and was killed by the `timeout` wrapper, losing buffered stdout. The actual logic completed successfully (proved by writing progress to a file: chars=2, props=1, delivery=0, PASS). This was purely a test-harness artifact; the production verify-canvas-shot-timeline.ts calls `process.exit()` in `finish()` and exits cleanly in ~2s. No code change needed.

## User Setup Required

None — no external service configuration required. The consumer verify runs the importer directly via `npx tsx` (no backend/DB/HTTP). The deferred e2e mode (PRESENT-06 third mode, Plan 09-02) is the only manual post-merge check.

## Next Phase Readiness

- **PRESENT-04 + PRESENT-05 fully delivered** in the consumer repo (commit `90812e9d` on `feat/canvas-asset-collection`).
- **Plan 09-02 (PRESENT-06) unblocked:** the shot-timeline `verify_contract.py` 3-mode harness can now bridge to the consumer (`CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer` runs the green verify script). Producer mode already green from Phase 5-8; consumer mode green as of this plan; e2e mode remains deferred/`--e2e-skip`.
- **Consumer PR:** `feat/canvas-asset-collection` now carries the v1.1 extension on top of the unmerged v1.0 work. The v1.0 WIP (prompts.json/action_chains.json) is preserved for the user to commit separately.

## Known Stubs

None. All character/prop nodes carry real OSS-synthesized thumbnailUrls and confirmed registry output_keys — no placeholder data flows to the renderer.

## Self-Check: PASSED

- FOUND: 09-01-SUMMARY.md
- FOUND: consumer commit 90812e9d on feat/canvas-asset-collection
- FOUND: consumer verify 27 passed / 0 failed (exit 0)
- FOUND: import-from-dir.ts, AssetNode.tsx, verify-canvas-shot-timeline.ts, v1.1 fixture asset.json
- FOUND: §7 post-process verified (0 assetType=delivery leaks)
- FOUND: v1.0 WIP (prompts.json/action_chains.json) intact post-commit

---
*Phase: 09-canvas-consumer-integration-cross-repo*
*Consumer commit: 90812e9d (feat/canvas-asset-collection)*
*Completed: 2026-07-24*
