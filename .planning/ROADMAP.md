# Roadmap: kais-shot-timeline — v1.0 ShotTimelineAsset Contract

## Overview

This milestone delivers a repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection. The journey flows in four derivation-driven steps: (1) write the contract both sides implement against, (2) build the producer exporter in this repo, (3) build the consumer ingestion in the canvas repo via a low-friction structural parent node (no custom renderer, no contract bump), (4) verify end-to-end flow with regression protection. The cross-repo boundary is explicit: Phase 1 + 2 + 4-partial live in `kais-shot-timeline`; Phase 3 + 4-partial live in `kais-aigc-platform` on branch `feat/canvas-asset-collection`.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: ShotTimelineAsset Specification** - Define the repo-agnostic contract (schema + version + media refs + manifest) both repos implement against — COMPLETE 2026-07-20
- [x] **Phase 2: shot-timeline Exporter (Producer)** - Implement the producer: pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served (completed 2026-07-20)
- [x] **Phase 3: Canvas Consumer** - Implement canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump) (completed 2026-07-20)
- [ ] **Phase 4: Cross-Repo Contract Verification** - End-to-end smoke + regression protection against schema/media-reference drift

## Phase Details

### Phase 1: ShotTimelineAsset Specification

**Goal**: A repo-agnostic ShotTimelineAsset contract document exists that both producer and consumer can implement against without tribal knowledge.
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Repo**: `kais-shot-timeline` (authoritative spec owner)
**Requirements**: SPEC-01, SPEC-02, SPEC-03, SPEC-04
**Success Criteria** (what must be TRUE):

  1. The spec defines the 5 canonical JSON shapes (`shots` / `audio_analysis` / `transcript` / `frames` / `prompts`) with field-level types, so a reader can recognize any conforming asset
  2. The spec defines a schema version field and the rule consumers follow when they encounter an unknown/newer version (graceful degrade vs. reject)
  3. The spec defines how media files (video mp4 + 3 stem wavs) are path/naming-conventioned and the Range-aware HTTP 206 serving requirement consumers depend on for seek playback
  4. The spec defines a self-describing manifest (content inventory, source video, generator tool/version) so a consumer can understand an asset without external documentation

**Plans**: 2 plans

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Write 6 JSON Schema (draft 2020-12) contract files + minimal fixture + jsonschema validation runner — DONE 2026-07-20 (smoke 5/5 valid against real producer output)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Write the authoritative human-readable spec/SPEC.md + human review checkpoint — DONE 2026-07-20 (SPEC.md 455 lines, c6f603d; Task 2 human-verify checkpoint APPROVED on first review)

### Phase 2: shot-timeline Exporter (Producer)

**Goal**: Running the shot-timeline pipeline emits a self-describing ShotTimelineAsset artifact that conforms to the Phase 1 spec and is servable to a downstream consumer.
**Mode**: mvp
**Depends on**: Phase 1
**Repo**: `kais-shot-timeline` (this repo)
**Requirements**: EXPORT-01, EXPORT-02, EXPORT-03
**Success Criteria** (what must be TRUE):

  1. After `run_pipeline.py` finishes, a ShotTimelineAsset artifact (manifest + 5 JSON set + media references) exists under `output/<video-stem>/` that conforms to the Phase 1 spec
  2. The exported asset carries a version number and self-describing manifest, and the export layer adds this **without modifying** the existing detection/transcription/separation algorithms (additive only)
  3. The exported asset's media files (video + 3 stem wavs) are consumable via HTTP Range requests through `scripts/serve.py` — a consumer can seek without re-downloading the whole file (206 Partial Content responses observed)

**Plans**: 2 plans

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Create scripts/export_asset.py (manifest writer + canonical symlinks + inline jsonschema) + wire step_export into run_pipeline.py (bump [N/5]→[N/6], add --skip-export, --force clears asset.json)

**Wave 2** *(blocked on Wave 1 completion — check_range exercises canonical media produced by 02-01)*

- [x] 02-02-PLAN.md — Fix scripts/serve.py _Partial FD-leak (add close() method) + create scripts/check_range.py (Range-206 self-check)

### Phase 3: Canvas Consumer

**Goal**: The canvas's existing `import-from-dir` path ingests a ShotTimelineAsset directory and renders it as a first-class collection on the canvas, using only existing renderers.
**Mode**: mvp
**Depends on**: Phase 1 (spec), Phase 2 (a real exported asset to test against)
**Repo**: `kais-aigc-platform` branch `feat/canvas-asset-collection` (package `@kais/infinite-canvas`)
**Requirements**: CANVAS-01, CANVAS-02, CANVAS-03
**Success Criteria** (what must be TRUE):

  1. Dropping a ShotTimelineAsset directory into the canvas's `import-from-dir` path produces a single collection entity on the canvas (not loose nodes)
  2. The collection is represented as a **structural parent node** following the existing `zone`/`phase` pattern (holds child node IDs), aggregating `storyboard` / `audio` / `video` child nodes derived from the asset
  3. All child nodes render via the canvas's **existing 5 renderers** — no custom renderer is introduced, no receiver-schema contract bump occurs (`structuralTypes` passthrough suffices)

**Plans**: 1 plan

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Add ShotTimelineAsset branch to import-from-dir.ts (RawArtifact.canvasType + buildPhaseTree L804 override + extractShotTimelineArtifacts + sequence edges + scanAndBuildTree merge) + downsampled golden fixture + verify-canvas-shot-timeline.ts (asserts A–F + additive-only guards)

**UI hint**: yes

### Phase 4: Cross-Repo Contract Verification

**Goal**: A real ShotTimelineAsset flows end-to-end from producer to consumer, and a regression harness exists to keep the contract aligned as both repos evolve independently.
**Mode**: mvp
**Depends on**: Phase 2 (exporter), Phase 3 (consumer)
**Repo**: Spans both (`kais-shot-timeline` producer fixture + `kais-aigc-platform` consumer test)
**Requirements**: VERIFY-01, VERIFY-02
**Success Criteria** (what must be TRUE):

  1. A ShotTimelineAsset produced by `kais-shot-timeline` imports successfully into the canvas and renders the expected collection of storyboard / stem-audio / video / prompt children — observable end-to-end
  2. A regression test exists that fails when the field schema or media-reference convention drifts between the producer and consumer (catches silent breakage on either side)

**Plans**: 2 plans

Plans:
**Wave 1**

- [ ] 04-01-PLAN.md — Build scripts/verify_contract.py harness skeleton with producer mode (inline jsonschema 6-schema validate, NOT spec/validate.py since SMOKE_SHAPES excludes asset) + consumer mode (shell-out to Phase 3 verify-canvas-shot-timeline.ts) + PHASE4_SELF_TEST=1 self-test (corrupt-asset injection) — covers VERIFY-02 (regression against producer/consumer drift)

**Wave 2** *(blocked on Wave 1 completion — same-file extension; e2e needs the harness skeleton from 04-01)*

- [ ] 04-02-PLAN.md — Add e2e mode to verify_contract.py (backend lifecycle via subprocess.Popen + /health poll + POST /api/canvas/v2/import-from-dir with real ep01 + SQL read-back of o_agentWorkData canvasGraph snapshot + structural asserts + try/finally teardown incl. worktree database.d.ts reconcile) + write 04-VERIFICATION.md capstone (WR-01/04 acceptance + SC-1 prompt-children scope reduction cross-ref Phase 3 deferred-items) — covers VERIFY-01 (end-to-end observable)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | 2/2 | Complete    | 2026-07-20 |
| 3. Canvas Consumer | 1/1 | Complete    | 2026-07-20 |
| 4. Cross-Repo Contract Verification | 0/2 | Not started | - |

---

*Roadmap created: 2026-07-20 — v1.0 ShotTimelineAsset Contract bootstrap*
