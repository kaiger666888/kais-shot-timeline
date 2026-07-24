---
phase: 9
slug: canvas-consumer-integration-cross-repo
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-25
---

# Phase 9 — Validation Strategy

> Derived from `09-RESEARCH.md` §Validation Architecture. Cross-repo: consumer changes verified by the consumer's `verify-canvas-shot-timeline.ts` (run via `npx tsx`); shot-timeline's `verify_contract.py` 3-mode harness bridges via `CANVAS_CONSUMER_PATH`. **Producer + consumer modes testable NOW** (consumer verify runs the importer directly, no backend). Only e2e is heavy/deferred.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Consumer framework** | `scripts/verify-canvas-shot-timeline.ts` (standalone, `npx tsx`) — extends for v1.1 |
| **Shot-timeline bridge** | `scripts/verify_contract.py --mode={producer,consumer,e2e,all}` (built v1.0) |
| **Full suite** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer` |
| **Estimated runtime** | ~15s (consumer verify ~10s + producer ~5s) |

## Per-Task Verification Map

| Req | Plan | Wave | Behavior | Test Type | Automated Command | Status |
|-----|------|------|----------|-----------|-------------------|--------|
| PRESENT-04 (gate) | 01 | 1 | `SHOT_TIMELINE_KNOWN_VERSIONS` includes "1.1"; v1.1 asset imports without warn | source + behavior | grep `new Set(\["1", "1.1"\])` + consumer verify no warn on v1.1 fixture | ⬜ |
| PRESENT-04 (emit) | 01 | 1 | character/prop nodes emitted with `type:"asset"` + `assetType:"character"/"prop"` (NOT "delivery") | integration | consumer verify: `characters.length === N && characters.every(n => n.data.assetType === "character")` | ⬜ |
| PRESENT-04 (data source) | 01 | 1 | reads `generator.registry_snapshot` (preferred) or `data.characters`/`data.props` | integration | consumer verify on fixture with snapshot | ⬜ |
| PRESENT-05 (typeIcons) | 01 | 1 | AssetNode typeIcons has `character:'🧑'`/`prop:'🔧'`; renders via existing AssetNode | source + additive-only | grep typeIcons + `git diff origin/master..HEAD -- packages/infinite-canvas/` limited to AssetNode.tsx typeIcons | ⬜ |
| PRESENT-05 (verify assert) | 01 | 1 | verify-canvas v1.1 character/prop node-count assertions pass | integration | `npx tsx scripts/verify-canvas-shot-timeline.ts` (v1.1 fixture) exit 0 | ⬜ |
| PRESENT-05 (Assert E relaxed) | 01 | 1 | Assert E amended: packages/infinite-canvas/ diff scoped to typeIcons additions (no custom renderer) | source | grep the amended assertion | ⬜ |
| PRESENT-06 (producer) | 02 | 2 | shot-timeline producer green for v1.1 | contract | `python3 scripts/verify_contract.py --mode=producer` exit 0 | ⬜ |
| PRESENT-06 (consumer) | 02 | 2 | bridge green | integration | `CANVAS_CONSUMER_PATH=... python3 scripts/verify_contract.py --mode=consumer` exit 0 | ⬜ |
| PRESENT-06 (e2e) | 02 | 2 | heavy | DEFERRED | `--e2e-skip`; manual post-merge | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red*

## Wave 0 Requirements

- [ ] `src/routes/canvas/v2/import-from-dir.ts` (consumer) — MODIFY: `SHOT_TIMELINE_KNOWN_VERSIONS` += "1.1" + character/prop node emission (post-process tree.artifactNodes per §7 caveat) + data-characters/props/registry_snapshot read.
- [ ] `packages/infinite-canvas/src/components/nodes/AssetNode.tsx` (consumer) — MODIFY: typeIcons += character/prop.
- [ ] `scripts/verify-canvas-shot-timeline.ts` (consumer) — MODIFY: v1.1 character/prop assertions + Assert E scoped relaxation.
- [ ] `scripts/fixtures/shot-timeline-v1.1/` (consumer) — NEW minimal v1.1 fixture (asset.json schema_version "1.1" + characters.json/props.json + data.characters/props + media.characters[]/props[] + registry_snapshot).
- [ ] `scripts/verify_contract.py` (shot-timeline) — confirm 3-mode green (likely no change — infrastructure from v1.0); extend only if a v1.1 producer assertion is missing.

## Manual-Only Verifications

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| e2e (backend round-trip) | heavy: starts backend, POST import-from-dir, SQL read-back | Post-merge: `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` (or `--mode=all`) |
| Canvas visual pilot | character/prop nodes render with correct icons/thumbnails in the actual canvas UI | Open the canvas in a browser against an imported v1.1 asset; confirm 🧑/🔧 nodes appear under the p13 zone with thumbnails |

**Approval:** approved (2026-07-25) — producer + consumer modes testable now (consumer verify runs importer directly, no backend). e2e + visual pilot are non-blocking deferred items (mirror Phase 6/7 deferral pattern).
