# Roadmap: kais-shot-timeline — v1.0 ShotTimelineAsset Contract

## Overview

This milestone delivers a repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection. The journey flows in four derivation-driven steps: (1) write the contract both sides implement against, (2) build the producer exporter in this repo, (3) build the consumer ingestion in the canvas repo via a low-friction structural parent node (no custom renderer, no contract bump), (4) verify end-to-end flow with regression protection. The cross-repo boundary is explicit: Phase 1 + 2 + 4-partial live in `kais-shot-timeline`; Phase 3 + 4-partial live in `kais-aigc-platform` on branch `feat/canvas-asset-collection`.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: ShotTimelineAsset Specification** - Define the repo-agnostic contract (schema + version + media refs + manifest) both repos implement against
- [ ] **Phase 2: shot-timeline Exporter (Producer)** - Implement the producer: pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served
- [ ] **Phase 3: Canvas Consumer** - Implement canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump)
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

- [ ] 01-01-PLAN.md — Write 6 JSON Schema (draft 2020-12) contract files + minimal fixture + jsonschema validation runner

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02-PLAN.md — Write the authoritative human-readable spec/SPEC.md + human review checkpoint

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

**Plans**: TBD

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

**Plans**: TBD
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

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | 0/2 | Not started | - |
| 2. shot-timeline Exporter (Producer) | 0/TBD | Not started | - |
| 3. Canvas Consumer | 0/TBD | Not started | - |
| 4. Cross-Repo Contract Verification | 0/TBD | Not started | - |

---

*Roadmap created: 2026-07-20 — v1.0 ShotTimelineAsset Contract bootstrap*
