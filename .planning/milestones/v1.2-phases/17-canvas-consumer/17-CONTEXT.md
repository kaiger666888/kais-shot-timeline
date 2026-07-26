# Phase 17: Canvas Consumer (deferrable) - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — cross-repo phase mirroring v1.1 Phase 9 canvas consumer patterns; shape forced by the §7 buildPhaseTree workaround + SPEC §4 graceful-degrade contract. All recommendations accepted per user momentum preference.

<domain>
## Phase Boundary

The `@kais/infinite-canvas` consumer (cross-repo `kais-aigc-platform` worktree at `/data/workspace/kst-canvas-consumer`, branch `feat/canvas-asset-collection`) recognizes `schema_version:"1.2"` and emits per-shot dialogue/music/sfx `type:"asset"` child nodes via the §7 `buildPhaseTree` post-process workaround. NO custom renderer, NO Zod contract bump (mirror v1.1 Phase 9). Plus the producer-side `verify_contract.py` consumer-mode shells GREEN for v1.2.

This phase is CROSS-REPO (consumer side) + the producer-side contract proof. It's deferrable via graceful-degrade (older consumers skip v1.2 audio nodes with a warning per SPEC §4).

</domain>

<decisions>
## Implementation Decisions

### Cross-repo consumer (kst-canvas-consumer on feat/canvas-asset-collection)

- **`import-from-dir.ts:899`** — append `"1.2"` to `SHOT_TIMELINE_KNOWN_VERSIONS` (currently `new Set(["1", "1.1"])`). v1.0/v1.1 asset dirs still import with zero regression (forward-compat proof).
- **§7 `buildPhaseTree` post-process** (`:616`) — emit 1 dialogue + 1 music + 1 sfx `type:"asset"` child per shot WITH non-null modality. Gated on `KNOWN_VERSIONS.has("1.2")` (`:953`); older consumers silently skip with a graceful-degrade warning per SPEC §4 (the `:953` else-branch already does this for unknown versions — verify the warning text covers 1.2 audio nodes).
- **`AssetNode.tsx` `typeIcons` cosmetic extension** — add `dialogue:"💬"` / `music:"🎵"` / `sfx:"🔊"` (mirror v1.1 character `🧑` / prop `🔧`). Find the AssetNode.tsx source (the typeIcons map; the built bundles have it but the source .tsx is the edit target).
- **`verify-canvas-shot-timeline.ts` assertion counts** — extended for v1.2 audio nodes (mirror the v1.1 27→29 bump pattern); GREEN on a v1.2 fixture.

### Producer-side contract proof

- **`scripts/verify_contract.py`** 3-mode harness GREEN for v1.2 fixture: producer mode (already GREEN from Phase 11) + consumer mode (shells verify-canvas-shot-timeline.ts against the v1.2 fixture, extended asserts). e2e backend mode deferred per v1.1 precedent (needs the Express backend running).

### NO custom renderer / NO Zod contract bump

- The v1.1 invariant (mirror Phase 9): reuse the existing structural parent node (zone/phase pattern) + 5 renderers. NO custom audio renderer. NO Zod schema contract bump (the consumer uses structural nodes, not typed audio contracts).

### Claude's Discretion

- Exact child-node ID scheme (mirror v1.1's shot/character/prop child naming).
- Whether music child emitted when MUS-04 instruments absent (yes — music_gen reproduction NL is non-null per Phase 15; the music child surfaces tempo/mood/key/VA + the reproduction prompt, NOT instruments).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (cross-repo consumer)
- **`/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts`** — THE file. `SHOT_TIMELINE_KNOWN_VERSIONS:899`, `buildPhaseTree:616`, graceful-degrade `:953`. The v1.1 character/prop child emission is the line-for-line template for v1.2 dialogue/music/sfx children.
- **v1.1 Phase 9 canvas work** — the precedent (structural parent node + buildPhaseTree workaround). The last commit `1c550314` (WR-03 v1.1 child node validateGraphNodes) is the current HEAD.
- **`scripts/verify_contract.py`** (producer repo) — consumer mode shells verify-canvas-shot-timeline.ts.

### Established Patterns
- **buildPhaseTree post-process** (§7 workaround) — the proven way to emit child nodes without a custom renderer.
- **KNOWN_VERSIONS graceful-degrade** (`:953`) — older consumers skip unknown versions with a SPEC §4 warning.
- **typeIcons cosmetic** — emoji per type (mirror v1.1 🧑/🔧).

### Integration Points
- This is the LAST milestone phase. After it, the milestone audit → complete → cleanup.
- The cross-repo PR (feat/canvas-asset-collection) is post-Phase 17 (not pushed during the phase).

</code_context>

<specifics>
## Specific Ideas

- The `KNOWN_VERSIONS.has("1.2")` gate is the graceful-degrade contract — older consumers (without the 1.2 entry) silently skip audio nodes per SPEC §4. This is the deferrability mechanism.
- Mirror the v1.1 27→29 assertion bump EXACTLY for verify-canvas-shot-timeline.ts (the v1.1 pattern is the template).
- The music child surfaces tempo/mood/key/VA + music_gen reproduction prompt — NOT instruments (MUS-04 deferred). Don't emit an instruments field in the child node.

</specifics>

<deferred>
## Deferred Ideas

- **e2e backend mode** (HTTP-level import-from-dir round-trip) — deferred per v1.1 precedent (needs Express backend running; producer + consumer shells prove the contract).
- **Cross-repo PR** (feat/canvas-asset-collection → upstream) — post-Phase 17.

</deferred>
