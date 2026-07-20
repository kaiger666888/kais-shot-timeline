---
phase: 3
slug: canvas-consumer
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-20
---

# Phase 3 — Validation Strategy

> Per-phase validation contract. Source: `03-RESEARCH.md` §Validation Architecture.
> Consumer repo has NO jest/vitest — uses the established `npx tsx scripts/verify-*.ts` pattern (6 existing verify scripts). Phase 3 adds one verify script + a downsampled fixture. All commands run in the **worktree cwd** (`/data/workspace/kst-canvas-consumer`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Node.js + `npx tsx` direct .ts execution (no jest/vitest) — matches worktree's 6 existing `verify:*` scripts |
| **Config file** | none (each verify script self-contains `assert` + `process.exit`) |
| **Quick run command** | `npx tsx scripts/verify-canvas-shot-timeline.ts` (worktree cwd) |
| **Full suite command** | `npx tsx scripts/verify-canvas-shot-timeline.ts && npm run verify:phase-46-contracts` (regression guard for existing 13-phase logic) |
| **Estimated runtime** | ~5 seconds (fixture inlined/downsampled) |

---

## Sampling Rate

- **After every task commit:** `npx tsx scripts/verify-canvas-shot-timeline.ts` (<5s)
- **After every wave:** + `npm run verify:phase-46-contracts` (regression — must not break existing import-from-dir phases)
- **Before `/gsd:verify-work`:** Full suite green; additive-only diff confirmed (`packages/infinite-canvas/` unchanged, `canvasAssetSchema.ts` strictness unchanged)
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

> Task IDs populate when PLAN.md files are written. From research §Validation Architecture.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | CANVAS-01 | — | N/A | unit | `npx tsx scripts/verify-canvas-shot-timeline.ts` assert A: asset.json recognized → extractShotTimelineArtifacts path; node count = 1 zone + 1 summary + (N+4) media children | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | CANVAS-02 | — | N/A | unit | assert B: 1 zone + N storyboard + 3 audio + 1 video; assert C: sequence edges length = N-1, shot_id monotonic | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | CANVAS-03 | V5 (input validation) | per-type Zod satisfied via synthesized fields (no schema loosening) | unit | assert D: `validateGraphNodes(allNodes).length === 0`; assert E: `git diff` packages/infinite-canvas/ empty + canvasAssetSchema.ts strictness unchanged | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | Roundtrip (Phase 4 seed) | — | N/A | unit | assert F: video_filename → zone label; duration_sec → audio/video duration_sec; asset.json fields survive into node.data | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `scripts/fixtures/shot-timeline-ep01/` — downsampled golden fixture (ffmpeg 1s silent media stubs + real data JSONs, <10MB; source: this repo's ep01 exported asset dir)
- [ ] `scripts/verify-canvas-shot-timeline.ts` — verify script covering CANVAS-01/02/03 + roundtrip spot-check (asserts A–F)
- [ ] `yarn install` — fresh worktree checkout, node_modules absent
- [ ] `extractShotTimelineArtifacts` exported (verify script imports it); if Pattern 2 Solution A chosen, `buildPhaseTree` also exported

*No existing test/config files modified — Phase 3 is all-new additions.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual canvas render (zone + storyboard/audio/video children + blue sequence arrows) | CANVAS-01/02 | Requires running backend + frontend + browser; the verify script proves structure/schema, not pixels | After backend importer + frontend load: open canvas, confirm one zone wrapping the collection, storyboard shots in shot_id order with blue sequence arrows, 3 audio + 1 video nodes; no FallbackNode (⚠) for any child |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (fixture + verify script + yarn install + exports)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-20 (post research; Dimension 8 substantive checks covered by asserts A–F; `wave_0_complete` flips true after the fixture + verify script land)
