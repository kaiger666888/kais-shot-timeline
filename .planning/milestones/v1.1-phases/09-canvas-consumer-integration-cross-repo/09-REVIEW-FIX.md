---
phase: 09-canvas-consumer-integration-cross-repo
fixed_at: 2026-07-25T00:00:00Z
review_path: .planning/phases/09-canvas-consumer-integration-cross-repo/09-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-07-25
**Source review:** `.planning/phases/09-canvas-consumer-integration-cross-repo/09-REVIEW.md`
**Iteration:** 1
**Repo fixed:** `/data/workspace/kst-canvas-consumer` (branch `feat/canvas-asset-collection`)

**Summary:**
- Findings in scope: 7 (1 Critical/BL + 5 Warning + IN-01 added per cheap-fix instruction)
- Fixed: 7
- Skipped: 0
- INFO IN-02 / IN-03 intentionally out of scope (IN-02 is a known limitation already documented in-code; IN-03 is the clean-XSS no-action finding).

**Cross-repo discipline preserved:** every consumer commit used explicit file paths
only (`git add <file>`); the user's uncommitted WIP
(`M scripts/fixtures/shot-timeline-ep01/prompts.json` +
`?? scripts/fixtures/shot-timeline-ep01/action_chains.json`) was verified untouched
after every commit and remains in the working tree at the end of the run.

## Per-finding outcome

| ID | Severity | File | Consumer commit | Status | Verification |
|----|----------|------|-----------------|--------|--------------|
| CR-01 | Critical | `src/routes/canvas/v2/import-from-dir.ts:1171-1188` | `9e1802f6` | fixed | probe: `validateGraphNodes` errors 3→0 on v1.1 char/prop |
| WR-01 | Warning | `scripts/verify-canvas-shot-timeline.ts:183-241` | `79e53317` | fixed | harness 27→27 green (merge-base ≡ HEAD~1 today); stable forward |
| WR-02 | Warning | `scripts/verify-canvas-shot-timeline.ts:243-289` | `51a8cc3a` | fixed | harness +28 green; real diff ALLOWed, `dangerouslySetInnerHTML`/`import`/JSX REJECTed |
| WR-03 | Warning | `scripts/verify-canvas-shot-timeline.ts:439-459` | `1c550314` | fixed | harness +29 green; would fail if CR-01 reverted (proven empirically) |
| WR-04 | Warning | `src/routes/canvas/v2/import-from-dir.ts:1094-1140` | `226839db` | fixed | probe: disjoint IDs → 0 warns; collision → 1 warn |
| WR-05 | Warning | `src/routes/canvas/v2/import-from-dir.ts:1172-1192` | `05308299` | fixed | probe: `../../etc/passwd` refused (`undefined` + warn); legit path unchanged |
| IN-01 | Info | `src/routes/canvas/v2/import-from-dir.ts:1110-1118` | `2ad3dff3` | fixed | probe: `name:""`/`null` → label=`char_NNN`; 0 Zod label errors |

## Fixed Issues

### CR-01: Character/prop asset nodes lack required `filePath` → save-v2 rejects with HTTP 400

**Files modified:** `src/routes/canvas/v2/import-from-dir.ts`
**Commit:** `9e1802f6`
**Root cause:** the §7 post-process set `data.thumbnailUrl` from `representative_image`
but never `data.filePath`. The `asset` Zod schema marks `filePath` as
`universalRequired` (`canvasAssetSchema.ts:23-25`); `save-v2.ts:49-58` enforces it
and rejects with HTTP 400. Import succeeded (the `appendAndSync` event-store path
bypasses per-type Zod), so the canvas appeared to work — but the next save-v2
roundtrip would reject every character/prop node. This is the WR-03 anti-pattern
reintroduced for v1.1.

**Applied fix:** in the §7 post-process, synthesize `data.filePath` from the SAME
`fsToOssUrl(rep_abs) ?? rep_abs` value used for `thumbnailUrl` — mirroring the
v1.0 audio/video node synthesis at `:1040-1061`. Character/prop nodes ARE asset
nodes whose `representative_image` IS a media PNG, so the same URL satisfies both
`thumbnailUrl` and `filePath` semantics.

**Reproduction closed:** before fix, probe showed all 3 v1.1 char/prop nodes with
`filePath: undefined` and `validateGraphNodes` returning 3 errors
(`filePath: 无效输入：期望 string，实际接收 undefined`). After fix, all 3 carry
`/oss/shot-timeline-v1.1/{characters,props}/...png` and `validateGraphNodes`
returns 0 errors.

### WR-01: Assert E baseline `HEAD~1..HEAD` is structurally unsound as a permanent regression gate

**Files modified:** `scripts/verify-canvas-shot-timeline.ts`
**Commit:** `79e53317`
**Root cause:** `HEAD~1..HEAD` makes the additive-only gate commit-structure-dependent.
A future contributor landing an unwanted `packages/infinite-canvas/.../NewRenderer.tsx`
in commit N, then an unrelated fix in commit N+1, would see the gate pass vacuously
(empty `HEAD~1..HEAD` diff) while the offending file lives in the tree.

**Applied fix:** anchor against `git merge-base origin/master HEAD` (the actual
divergence point), which is stable across future commits on this branch. Handles
the missing-`origin/master` case (shallow clone / CI) by failing loud — mirroring
the WR-08 pattern (`schemaCompareOk === null` → assert FAIL, never pass vacuously).
`mergeBase` + `baselineCompareOk` are reused by WR-02's hunk check.

**Reproduction closed:** empirically `merge-base origin/master HEAD === HEAD~1 === bb3eaaf4`
today, so `merge-base..HEAD` produces the identical single-file diff
(`AssetNode.tsx`) — harness stays 27 green. The merge-base is stable: adding
commits to `feat/canvas-asset-collection` does not shift it (only an
`origin/master` merge would).

### WR-02: Assert E allowlist enforces "AssetNode.tsx file" but documents "typeIcons only"

**Files modified:** `scripts/verify-canvas-shot-timeline.ts`
**Commit:** `51a8cc3a`
**Root cause:** the file-level allowlist `{"AssetNode.tsx"}` passes for ANY change
to that file. The PRESENT-05 SPIRIT is "cosmetic typeIcons emoji-map extension only",
but a future `dangerouslySetInnerHTML`, inline `<script>`, new import, or new render
branch would also pass.

**Applied fix:** added a hunk-content check (reusing WR-01's `mergeBase`): the
`AssetNode.tsx` diff must be PURELY ADDITIVE (no removed content lines) AND every
added line must be either a `//` comment or one-or-more `key:'emoji',` map tuples
(regex `/^(\w+:\s*'[^']*',?\s*)+$/`). Non-conforming additions fail loud.

**Reproduction closed:** against the real `merge-base..HEAD` diff, all 4 added
lines (3 comments + `character: '🧑', prop: '🔧',`) are ALLOWed. Synthetic
dangerous lines (`const x = dangerouslySetInnerHTML`, `import { evil }`,
`return (<div>...)`) are all REJECTed.

### WR-03: Verify harness skips `validateGraphNodes` on the v1.1 fixture run

**Files modified:** `scripts/verify-canvas-shot-timeline.ts`
**Commit:** `1c550314`
**Root cause:** the v1.0 ep01 run asserts `validateGraphNodes(childNodes).length === 0`
(Step D, the canonical regression catch for save-v2 Zod failures). The v1.1 fixture
run asserted counts/thumbnailUrl/output_key but NEVER re-ran per-type Zod — which
is precisely why CR-01 (missing `filePath`) slipped through.

**Applied fix:** added a v1.1-equivalent Step D — `validateGraphNodes(v11ChildNodes)`
must return 0 errors. Assertion name explicitly cites `filePath / label` to document
the CR-01 regression intent.

**Reproduction closed:** after CR-01 is fixed, the new assertion PASSES (0 errors).
The regression-catch property is proven: the CR-01 probe (before fix) showed
`validateGraphNodes` returns 3 `filePath` errors on the v1.1 nodes — i.e. had
WR-03 existed pre-fix, it would have failed loud and caught CR-01.

### WR-04: §7 post-process join is fragile to cross-list duplicate registry IDs

**Files modified:** `src/routes/canvas/v2/import-from-dir.ts`
**Commit:** `226839db`
**Root cause:** `registryById = new Map(entries.map(e => [e.output_key, e]))` is
last-write-wins. If a malformed/malicious manifest emits the same `id` in both
`snapshot.characters` and `snapshot.props`, the character node's `assetType` gets
silently overwritten to `"prop"` (or vice versa). The producer guarantees disjoint
`char_NNN`/`prop_NNN` formats, but the consumer trusts an `any`-typed manifest.

**Applied fix:** added a `seenRegistryIds` Set in `collectRegistryEntries`; on
collision, `console.warn` surfaces the mis-classify risk. (Producer guarantees
make this impossible in practice — the warn is defense-in-depth.)

**Reproduction closed:** disjoint fixture → 0 collision warns. Injected collision
(same `char_001` in both lists) → 1 warn with correct detail.

### WR-05: `representative_image` path not re-validated consumer-side (defense-in-depth gap)

**Files modified:** `src/routes/canvas/v2/import-from-dir.ts`
**Commit:** `05308299`
**Root cause:** `join(workdir, entry.representative_image)` resolves `..` segments.
`fsToOssUrl` returns null for paths outside the OSS/workdir scope, so the fallback
surfaces the raw escaped absolute path (probe P7 with `../../etc/passwd` yielded
`thumbnailUrl: "/data/.../etc/passwd"`). The producer enforces `^(?!.*\.\.)`, but
the consumer trusts an `any` manifest.

**Applied fix:** consumer-side re-validation — reject `representative_image`
values containing `..` or starting with `/` before `join`+`fsToOssUrl`, with a
`console.warn`. Mirrors the producer's anti-traversal regex. Legitimate paths are
unaffected (wrapped in an `else` branch that contains the existing
thumbnailUrl/filePath synthesis).

**Reproduction closed:** legitimate `characters/char_001.png` → `filePath`/`thumbnailUrl`
synthesized normally. Injected `../../etc/passwd` → both fields `undefined` + warn
emitted (refused, not leaked).

### IN-01: Empty `name` field silently produces Zod-failing label

**Files modified:** `src/routes/canvas/v2/import-from-dir.ts`
**Commit:** `2ad3dff3`
**Root cause:** guard `entry.name == null` uses loose equality — catches
`null`/`undefined` but NOT empty string. An entry with `name: ""` was emitted with
`label: ""`, failing the asset schema `label: z.string().min(1)`.

**Applied fix:** dropped `entry.name == null` from the skip guard (still skip on
`entry.id == null`) and coerce empty/missing/whitespace name to the stable registry
id (`rawName = idStr`). Used `rawName` for both `registryEntries.name` and the
artifact `label`/`name`, guaranteeing a non-empty label.

**Reproduction closed:** `name:""` → label `char_001`; `name:null` → label `char_002`
(previously skipped entirely, now emitted with the id fallback). 0 Zod label errors.

## Skipped Issues

None — all 7 in-scope findings were fixed.

Out-of-scope (default scope = critical + warning; IN-01 added per cheap-fix
instruction): IN-02 (count-based strictness counter — known limitation already
documented in the WR-08 comment block, no PRESENT-04/05 schema touch) and IN-03
(clean XSS focus area, no action required).

## Final gate (all green)

```
# Gate 1 — consumer verify harness (29 green: 27 v1.0 + WR-02 + WR-03)
cd /data/workspace/kst-canvas-consumer && npx tsx scripts/verify-canvas-shot-timeline.ts
  → 29 passed, 0 failed   EXIT=0

# Gate 2 — consumer contract
CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer
  → [consumer] OK: Phase 3 17 asserts all green   EXIT=0

# Gate 3 — full contract (producer + consumer, e2e skipped)
python3 scripts/verify_contract.py --mode=all --e2e-skip
  → OK producer + OK consumer   EXIT=0
```

## WIP preservation

The user's uncommitted consumer WIP was verified untouched after every one of the
7 atomic commits:

```
M  scripts/fixtures/shot-timeline-ep01/prompts.json        (user WIP — untouched)
?? scripts/fixtures/shot-timeline-ep01/action_chains.json  (user WIP — untouched)
```

All consumer commits used explicit file paths (`git add <file>`) — never
`git add -A`/`git add .`/`git add scripts/fixtures/`.

---

_Fixed: 2026-07-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
