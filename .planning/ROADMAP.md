# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 ShotTimelineAsset Contract (Phases 1-4) — SHIPPED 2026-07-20</summary>

A repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection.

- [x] **Phase 1: ShotTimelineAsset Specification** — repo-agnostic contract (6 schemas + version + media refs + manifest) both repos implement against — COMPLETE 2026-07-20
- [x] **Phase 2: shot-timeline Exporter (Producer)** — pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served — COMPLETE 2026-07-20
- [x] **Phase 3: Canvas Consumer** — canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump) — COMPLETE 2026-07-21 *(code in kais-aigc-platform `feat/canvas-asset-collection`)*
- [x] **Phase 4: Cross-Repo Contract Verification** — end-to-end flow + regression protection against schema/media-reference drift — COMPLETE 2026-07-21

**Audit:** 12/12 requirements satisfied, 4/4 phases verified, integration complete — [v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

**Known deferred items (formally accepted):** WR-01/WR-04 (save-v2 secondary-path latent bugs → consumer-repo backlog; primary appendAndSync path unaffected); SC-1 prompt-children scope reduction (prompts/transcript are sidecar data refs, not canvas nodes).

</details>

### 📋 Next Milestone

*Not yet planned.* Run `/gsd:new-milestone` to start v1.1 / v2.0.

Likely candidates (from v1.0 Out-of-Scope / deferred):
- NATIVE-01/02: canvas native timeline renderer (stem playback engine, waveform canvas, native Range media service)
- ORCH-01: shot-timeline as canvas orchestration skill (tight-coupling alt — evaluate post-v1.0)
- save-v2 hardening (WR-01/04) in the consumer repo

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | v1.0 | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | v1.0 | 2/2 | Complete | 2026-07-20 |
| 3. Canvas Consumer | v1.0 | 1/1 | Complete | 2026-07-21 |
| 4. Cross-Repo Contract Verification | v1.0 | 2/2 | Complete | 2026-07-21 |
