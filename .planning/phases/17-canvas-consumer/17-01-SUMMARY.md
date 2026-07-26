---
phase: 17-canvas-consumer
plan: 01
subsystem: canvas-consumer
tags: [canvas-consumer, v1.2-audio-semantic, dialogue-music-sfx-children, known-versions-1.2, graceful-degrade, buildphasetree-postprocess, typeicons-emoji, verify-contract-3-mode, mus-04-omitted, no-zod-bump, no-custom-renderer, cross-repo]

# Dependency graph
requires:
  - phase: 16-html-gallery
    provides: "v1.2 layered reproduction prompts + HTML gallery (PRESENT-01 shipped) — Phase 17 consumer mirrors the dialogue/music/sfx modality split"
  - phase: 11-contract-v1-2
    provides: "schema_version 1.2 literal + audio_semantic.schema.json (music sub-object OMITTED, instruments absent — MUS-04 LOCKED) + speakers.schema.json"
provides:
  - "Cross-repo @kais/infinite-canvas consumer recognizes schema_version 1.2 (KNOWN_VERSIONS Set entry appended)"
  - "§7 buildPhaseTree post-process emits 1 dialogue + 1 music + 1 sfx type:asset child per shot with non-null modality, gated on KNOWN_VERSIONS.has(version) && version === '1.2' (T-17-01 graceful-degrade gate)"
  - "AssetNode.tsx typeIcons cosmetic extension (💬 dialogue / 🎵 music / 🔊 sfx)"
  - "verify-canvas-shot-timeline.ts extended with v1.2 fixture run (40 assertions total, +11 new)"
  - "Producer-side verify_contract.py 3-mode GREEN for v1.2 (producer + consumer; e2e deferred per v1.1 precedent)"
affects: [milestone-audit, v1.3-audio-modality-extension, cross-repo-PR]

# Tech tracking
tech-stack:
  added: []  # No new libraries — reuses existing Zod, React, tsx, jsonschema
  patterns:
    - "§7 buildPhaseTree post-process override (3-step): (1) push RawArtifact{canvasType:\"asset\"} BEFORE buildPhaseTree, (2) buildPhaseTree seeds assetType=\"delivery\", extra-merge guard drops extra.assetType, (3) post-process tree.artifactNodes override data.assetType via output_key join. Pattern proven in v1.1 PRESENT-04 character/prop; Phase 17 applies it to dialogue/music/sfx."
    - "Graceful-degrade gate (`KNOWN_VERSIONS.has(version) && version === \"1.2\"`) — older consumers skip audio child emission entirely via SPEC §4 contract; the deferrability mechanism."
    - "Music child forward-compat: v1.2 schema OMITS music sub-object (only reproduction.music_gen NL prompt is the music signal); when v1.3 adds music modality, the same emission code can extend without consumer-side rewrite."

key-files:
  created:
    # consumer repo (kst-canvas-consumer @ feat/canvas-asset-collection)
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/asset.json
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/audio_semantic.json
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/speakers.json
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/shots.json
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/{audio_analysis,frames,transcript,prompts,characters,props}.json
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/{characters,props,stems}/*
    - /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/video.mp4
    # producer repo
    - .planning/phases/17-canvas-consumer/17-01-SUMMARY.md
  modified:
    - /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts  # KNOWN_VERSIONS += "1.2"; §7 audio child emission + post-process
    - /data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx  # typeIcons += dialogue/music/sfx
    - /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts  # v1.2 fixture section + 11 new assertions

key-decisions:
  - "Music child emission gated on `reproduction.music_gen` non-null (NOT a future music sub-object) — v1.2 audio_semantic.schema.json OMITS the music sub-object entirely (MUS-04 instruments absent → no music content to contract). The reproduction.music_gen NL prompt is the ONLY music signal in v1.2. Forward-compat: when v1.3 adds the music sub-object, the emission logic extends."
  - "Audio child filePath = master video (NOT per-modality stem) — asset schema (canvasAssetSchema.ts:23-25) marks filePath as universalRequired; semantic truth is all audio analysis is derived from analyzing the video's audio track. Per-modality stem selection (vocals for dialogue, drums+bass+other for music) was considered but rejected as over-engineering for v1.2."
  - "thumbnailUrl deliberately undefined for audio children — AssetNode.tsx :127 falls back to typeIcons emoji (💬/🎵/🔊 via Task 3 cosmetic extension), no broken image preview."
  - "v1.2 consumer fixture is RICHER than producer fixture — Shot 1 has dialogue + sfx + reproduction.music_gen non-null to exercise ALL three child types from one shot; Shot 2 has dialogue only to test graceful-degrade of music/sfx. Producer fixture's Shot 1 has reproduction.music_gen=null which would only exercise dialogue+sfx paths."

patterns-established:
  - "Pattern: §7 buildPhaseTree audio child emission (3-step RawArtifact push → seed → post-process override) — reuses v1.1 PRESENT-04 character/prop pattern verbatim. Future v1.x+3 modalities can follow the same shape."
  - "Pattern: graceful-degrade version gate (`KNOWN_VERSIONS.has(version) && version === \"X.Y\"`) — deferrability mechanism shared across v1.1 (PRESENT-04 character/prop) and v1.2 (CONSUMER-01 audio). Older consumers silently skip emission via SPEC §4 contract."
  - "Pattern: cross-repo consumer fixture (scripts/fixtures/shot-timeline-v{X,Y}/) — small, self-contained, richer than producer fixture to exercise every emission path. Registry_snapshot + key sidecars carried verbatim from prior version fixture to prove zero-regression."

requirements-completed: [CONSUMER-01]

# Metrics
duration: 13min
completed: 2026-07-26
---

# Phase 17 Plan 01: Canvas Consumer v1.2 Summary

**Cross-repo `@kais/infinite-canvas` consumer recognizes schema_version 1.2 + emits per-shot dialogue/music/sfx type:asset children via §7 buildPhaseTree post-process (gated on KNOWN_VERSIONS.has("1.2")); AssetNode typeIcons 💬🎵🔊 cosmetic; verify_contract 3-mode GREEN (40 assertions, +11 new); MUS-04 instruments absent; v1.1 Phase 9 invariant (no custom renderer / no Zod bump) preserved.**

## Performance

- **Duration:** ~13 min (combined plan + execute)
- **Started:** 2026-07-26T01:01:51Z
- **Completed:** 2026-07-26T01:14:37Z
- **Tasks:** 5 (4 consumer @ feat/canvas-asset-collection + 1 producer @ main)
- **Files modified:** 3 consumer files + 4 new consumer fixture files (+ 10 copied shared fixture files) + 1 producer SUMMARY

## Accomplishments

- **SC#1 KNOWN_VERSIONS gate**: `import-from-dir.ts:905` appends literal `"1.2"` to `SHOT_TIMELINE_KNOWN_VERSIONS` Set. Older consumers (without the entry) skip audio emission via existing :953 graceful-degrade warn (SPEC §4 contract).
- **SC#2 §7 audio child emission**: For each `audio_semantic.json#shots[]` entry with non-null modality, emits 1 dialogue + 1 music + 1 sfx `type:"asset"` child. The block is GATED on `KNOWN_VERSIONS.has(version) && version === "1.2"` (T-17-01 graceful-degrade). Uses the 3-step §7 pattern (push RawArtifact before buildPhaseTree → buildPhaseTree seeds assetType="delivery" → post-process overrides data.assetType via output_key join).
- **SC#3 typeIcons cosmetic**: AssetNode.tsx `typeIcons` map extended with `dialogue: '💬', music: '🎵', sfx: '🔊'` (3 additive tuples mirroring v1.1 character '🧑' / prop '🔧'). Render code at :127 + :175 already reads `typeIcons[data.assetType] || '📦'` — zero render-logic change.
- **SC#4 verify-canvas-shot-timeline.ts**: Third fixture-run section added (mirror v1.1 PRESENT-04/05). 11 new assertions; total now 40 (was 29). v1.2 fixture emits 2 dialogue + 1 music + 1 sfx children with zero delivery leak, output_keys match `^audio_(dia|mus|sfx)_\d+$`, zero instruments fields (MUS-04), v1.1 character/prop still emit (2/1), all child nodes pass per-type Zod.
- **SC#5 verify_contract.py 3-mode GREEN**: producer mode GREEN (carried from Phase 11), consumer mode GREEN (40 assertions), `--mode=all --e2e-skip` GREEN. e2e deferred per v1.1 Phase 9 precedent (needs Express backend running).
- **MUS-04 LOCKED invariant**: Zero `instruments` field emissions anywhere in import-from-dir.ts (3 grep matches are all comments documenting the MUS-04 absence — "MUS-04 instruments 永不 emit", "NO instruments field is EVER emitted", "NO instruments").
- **v1.1 Phase 9 invariant preserved**: NO custom renderer (reuses existing 5 renderers), NO Zod contract bump (canvasAssetSchema.ts strictness counts unchanged: .optional()=18, .nullable()=0).
- **Zero regression**: 29 existing v1.0 + v1.1 assertions stay GREEN alongside the 11 new v1.2 assertions.

## Task Commits

Each task was committed atomically. **Cross-repo commit graph** (the two repos share NO commits):

**Consumer repo (`kais-aigc-platform` @ `feat/canvas-asset-collection` — DO NOT push/PR):**

1. **Task 1: KNOWN_VERSIONS 1.2 gate (SC#1)** — `886edbf2` (feat)
2. **Task 2: §7 audio child emission + v1.2 fixture (SC#2)** — `61f1890b` (feat)
3. **Task 3: AssetNode typeIcons cosmetic (SC#3)** — `b312f8cd` (feat)
4. **Task 4: verify-canvas-shot-timeline.ts v1.2 section (SC#4)** — `70b342c3` (test)

**Producer repo (`kais-shot-timeline` @ `main`):**

5. **Plan creation** — `7caf41a` (docs) — pre-execution plan commit
6. **Task 5: SUMMARY + verify_contract.py 3-mode GREEN proof** — (this commit, docs)

**Cross-repo HEAD SHAs (for audit trail):**
- Consumer HEAD: `70b342c3b57bb736693bc2ca3243b4ab41479bbd` (feat/canvas-asset-collection)
- Producer HEAD after Task 5: see `git rev-parse HEAD` post-commit

## Files Created/Modified

### Consumer repo (kst-canvas-consumer @ feat/canvas-asset-collection)

- `src/routes/canvas/v2/import-from-dir.ts` — KNOWN_VERSIONS += "1.2" (:905); (d.2) audio child emission block (gated on `KNOWN_VERSIONS.has(version) && version === "1.2"`); (e.3) post-process override for audio child assetType via output_key join. Net: +150 lines.
- `packages/infinite-canvas/src/components/nodes/AssetNode.tsx` — typeIcons map extended with `dialogue: '💬', music: '🎵', sfx: '🔊'` (3 additive tuples). Net: +4 lines.
- `scripts/verify-canvas-shot-timeline.ts` — Third fixture-run section (mirror v1.1 PRESENT-04/05 at :376-457). 11 new assertions. Net: +113 lines.
- `scripts/fixtures/shot-timeline-v1.2/asset.json` — schema_version "1.2", registry_snapshot carried verbatim from v1.1 (so character/prop children still emit and we don't regress), data.audio_semantic + data.speakers references.
- `scripts/fixtures/shot-timeline-v1.2/audio_semantic.json` — Richer than producer fixture: Shot 1 has dialogue (HAPPY, spk_001) + sfx (Laughter) + reproduction.music_gen NON-NULL (upbeat acoustic prompt); Shot 2 has dialogue only. Schema-valid (no music sub-object, no instruments field).
- `scripts/fixtures/shot-timeline-v1.2/speakers.json` — spk_001 + spk_002 (mirrors audio_semantic.dialogue.spk_id), char_id null, review_state confirmed.
- `scripts/fixtures/shot-timeline-v1.2/{shots,audio_analysis,frames,transcript,prompts,characters,props}.json` + `{characters,props,stems}/*` + `video.mp4` — Copied verbatim from v1.1 fixture (10 files + 3 directories).

### Producer repo (kais-shot-timeline @ main)

- `.planning/phases/17-canvas-consumer/17-01-SUMMARY.md` — this file.
- `.planning/phases/17-canvas-consumer/17-01-PLAN.md` — pre-execution plan (committed separately at `7caf41a`).
- NO producer code changes — verify_contract.py was already consumer-mode-ready from Phase 4 (shells out to verify-canvas-shot-timeline.ts at :941-1002); Phase 17 needed zero producer code.

## Decisions Made

1. **Music child payload = reproduction.music_gen ONLY** — The v1.2 audio_semantic.schema.json `$comment` explicitly states "music 子对象 OMITTED in v1.2 (MUS-04 乐器识别字段缺席 → 无音乐内容可契约)". So the music modality sub-object (tempo/mood/key/VA/instruments) does NOT exist in v1.2. The ONLY music signal is `reproduction.music_gen` (the model-agnostic NL prompt). The music child carries that payload only. NO instruments field (MUS-04 LOCKED defer v1.3). Tempo/mood/key/VA are v1.3 territory when the music sub-object is added. The emission code is forward-compat: when v1.3 adds the music sub-object, the same emission logic extends.

2. **Audio child filePath = master video** — `canvasAssetSchema.ts:23-25` marks filePath as universalRequired for asset nodes. Without a non-empty filePath, the audio children would fail per-type Zod (CR-01 regression catch in the verify harness). Audio semantic children have NO dedicated media file (the actual stems are the existing vocals/drums/other audio nodes). The truthful non-empty filePath is the master video — all audio analysis is derived from its audio track. Per-modality stem selection (vocals for dialogue, drums+bass+other for music) was considered and rejected as over-engineering for v1.2.

3. **v1.2 consumer fixture richer than producer fixture** — Producer's v1.2 fixture has reproduction.music_gen=null in Shot 1, which would only exercise dialogue+sfx paths. Consumer's v1.2 fixture sets reproduction.music_gen to a non-empty NL prompt in Shot 1 to exercise ALL three child types from one shot. Shot 2 keeps dialogue-only to test graceful-degrade of music+sfx emission.

4. **Pre-existing consumer worktree changes left untouched** — The consumer worktree at `/data/workspace/kst-canvas-consumer` had pre-existing uncommitted changes (`scripts/fixtures/shot-timeline-ep01/prompts.json` modified + `scripts/fixtures/shot-timeline-ep01/action_chains.json` untracked). Per scope boundary rules, these were NOT touched — only my Phase 17 files were staged in each commit.

## Deviations from Plan

None - plan executed exactly as written. All 5 SC addressed, all 5 tasks committed atomically with the prescribed format. T-17 threat model mitigations all empirically verified:
- T-17-01 (graceful-degrade gate): emission block gated on `KNOWN_VERSIONS.has(version) && version === "1.2"` ✓
- T-17-02 (MUS-04 instruments absent): zero `\binstruments?\b` field emissions in code (3 grep matches are comments documenting the absence) ✓
- T-17-03 (v1.1 invariant — no renderer/Zod bump): Assert E + E2 + WR-02 all green ✓
- T-17-04 (XSS safe-by-React-JSX): AssetNode.tsx uses `{data.label}` (auto-escaped), no dangerouslySetInnerHTML ✓
- T-17-05 (no vacuous-pass): existing `baselineCompareOk`/`schemaCompareOk` null-trip-state pattern preserved ✓

## Issues Encountered

- **Initial speakers.json fixture failed schema validation** — First draft had `episode`/`duration`/`schema_version` top-level and `label`/`turn_count` per-speaker fields, all rejected by speakers.schema.json's `additionalProperties:false`. Fixed by simplifying to schema-conformant shape (`speakers[]` only at root, per-speaker fields limited to `spk_id`/`char_id`/`total_speech_sec`/`review_state`/`turns`). Re-validated GREEN before committing.
- **Standalone smoke test hung** — A one-off `npx tsx` script timed out (likely import-chain slowness on the consumer repo). Bypassed by extending verify-canvas-shot-timeline.ts directly (Task 4) — which is the intended verification path per the plan. Task 4's 40-assertion run exercises all of Task 1+2+3+4 in one shot.

## User Setup Required

None — no external service configuration required. The cross-repo PR (feat/canvas-asset-collection → upstream) is deferred per the v1.1 Phase 9 precedent (post-Phase-17 concern, not part of this plan).

## Next Phase Readiness

- **Phase 17 is the LAST phase of v1.2 milestone.** Next step is the v1.2 milestone audit (33/33 requirements, 8 phases).
- **CONSUMER-01 is now complete** — all 33 v1.2 requirements satisfied (was 32/33 before Phase 17).
- **Cross-repo PR** (`feat/canvas-asset-collection` → upstream `kais-aigc-platform`) is the only outstanding v1.2 cross-repo concern. Not blocking — graceful-degrade contract proven; consumer commits land on the branch when the PR opens.
- **STATE.md / ROADMAP.md intentionally NOT updated** per user constraint — milestone audit will advance state in a separate workflow.

## Self-Check: PASSED

Verified files exist + commits exist on appropriate branches:

**Consumer files (feat/canvas-asset-collection @ 70b342c3):**
- FOUND: /data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts (KNOWN_VERSIONS contains "1.2")
- FOUND: /data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx (typeIcons 💬🎵🔊)
- FOUND: /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts (v1.2 section)
- FOUND: /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/asset.json
- FOUND: /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/audio_semantic.json
- FOUND: /data/workspace/kst-canvas-consumer/scripts/fixtures/shot-timeline-v1.2/speakers.json

**Consumer commits:**
- FOUND: 886edbf2 (Task 1 — KNOWN_VERSIONS)
- FOUND: 61f1890b (Task 2 — §7 emission + v1.2 fixture)
- FOUND: b312f8cd (Task 3 — typeIcons)
- FOUND: 70b342c3 (Task 4 — verify-canvas v1.2 section)

**Producer verification:**
- FOUND: 7caf41a (Plan creation)
- verify_contract.py --mode=all --e2e-skip → exit 0 (producer + consumer GREEN)
- 40 assertions pass in verify-canvas-shot-timeline.ts (29 existing + 11 new v1.2)

---
*Phase: 17-canvas-consumer*
*Completed: 2026-07-26*
