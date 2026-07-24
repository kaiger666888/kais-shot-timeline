# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 分镜语义深化** — Phases 5-9 (shipped 2026-07-25) — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump 1→1.1 + 双端展示 — [archived](milestones/v1.1-ROADMAP.md)

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

<details>
<summary>✅ v1.1 分镜语义深化 (Phases 5-9) — SHIPPED 2026-07-25</summary>

Strict-additive, contract-first minor bump on v1.0. Adds two new pipeline stages calling ML HTTP routes in `kais-aigc-platform` (cinematography analysis + cross-shot re-id), three new optional data files (`characters.json`, `props.json`, enriched `prompts.json`), a first-class HITL review HTML deliverable, and a canvas consumer extension. Mirrors v1.0's contract-first sequencing that worked.

- [x] **Phase 5: Contract v1.1** — 3 new registry schemas + 2 additive schema extensions + SPEC + 9-file v1.1 fixture + verify harness (no route dependency) — COMPLETE 2026-07-24
- [x] **Phase 6: Cinematography Auto-Fill (`step_semantic`)** — httpx client + graceful-degrade + per-shot cache + generator.warnings — COMPLETE 2026-07-24
- [x] **Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`)** — HIGHEST complexity; producer client + HITL review HTML + `apply_edits.py` confirmed-only gate — COMPLETE 2026-07-25
- [x] **Phase 8: Prompt Reference System + shot-timeline HTML Gallery** — `attach_refs.py` + `registry_snapshot` freeze + gallery/chips/indicator — COMPLETE 2026-07-25
- [x] **Phase 9: Canvas Consumer Integration (cross-repo)** — consumer recognizes `"1.1"` + emits character/prop `asset` nodes (no renderer / no Zod bump) — COMPLETE 2026-07-25

**Audit:** 34/34 requirements satisfied, 5/5 phases verified, 4/4 cross-phase integration flows complete — [v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**Known deferred items (pre-authorized, cross-repo — producer/contract side complete + graceful-degrade proven):**
- Phase 6: live `shot-analysis` route round-trip (`feat/shot-analysis-route` unmerged in kais-aigc-platform; mapping proven against 7 captured fixtures).
- Phase 7: `character-reid` route + SAM3 multi-frame driver + DINOv2 embedding/clustering + empirical τ calibration on ep01 crops (route not yet built; literature three-tier defaults locked advisory).
- Phase 9: e2e backend mode of `verify_contract.py` (heavy; helper-level E2E proven 29/29) + canvas visual pilot.

**Full phase details:** [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | v1.0 | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | v1.0 | 2/2 | Complete | 2026-07-20 |
| 3. Canvas Consumer | v1.0 | 1/1 | Complete | 2026-07-21 |
| 4. Cross-Repo Contract Verification | v1.0 | 2/2 | Complete | 2026-07-21 |
| 5. Contract v1.1 | v1.1 | 4/4 | Complete | 2026-07-24 |
| 6. Cinematography Auto-Fill (`step_semantic`) | v1.1 | 3/3 | Complete | 2026-07-24 |
| 7. Cross-Shot Re-ID Registry + HITL Review (`step_reid`) | v1.1 | 4/4 | Complete | 2026-07-25 |
| 8. Prompt Reference System + shot-timeline HTML Gallery | v1.1 | 3/3 | Complete | 2026-07-25 |
| 9. Canvas Consumer Integration (cross-repo) | v1.1 | 2/2 | Complete | 2026-07-25 |
