---
status: partial
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
source: [07-VERIFICATION.md]
started: 2026-07-25
updated: 2026-07-25
---

# Phase 7 — Human Verification (Deferred Items)

> All 12/12 producer-side must-haves verified automatically (07-VERIFICATION.md). The 3 items below are **pre-authorized deferred** per CONTEXT.md `<deferred>` + 07-VALIDATION.md Manual-Only + STATE.md Blockers — they depend on cross-repo work (kais-aigc-platform `character-reid` route, unmerged) that is out of this repo's control. They mirror Phase 6's deferred `feat/shot-analysis-route` round-trip exactly. Phase 7 ships as a fully-functional graceful-degrade producer; these become post-merge smoke checks.

## Tests

### 1. Live `character-reid` route round-trip against ep01
expected: `step_reid` against a running `POST /api/v1/production/character-reid` route produces a real `registry.draft.json` with clustered characters/props; review HTML renders real clusters; apply_edits → real canonical characters.json/props.json.
result: pending (route DEFERRED cross-repo — kais-aigc-platform, unmerged; mirrors Phase 6 `feat/shot-analysis-route` pre-merge state)
why deferred: producer-side graceful-degrade fully tested via verify_phase7_smoke.py scenario 1 (route-down → empty draft + warnings + asset exports).

### 2. Empirical three-tier τ calibration on ep01 crops
expected: same-person vs different-person DINOv2 cosine histogram on ep01 SAM3 foreground-masked crops → valley pick → update registry.schema.json `$comment` three-tier defaults from advisory to empirically-validated.
result: pending (needs SAM3 character crops that don't exist until CAST-02 route ships)
why deferred: CONTEXT Q2 locks literature three-tier defaults (sim ≥0.85 auto-merge / 0.6–0.85 review / <0.6 auto-distinct) as advisory; calibration protocol documented in 07-RESEARCH.md §DINOv2 Re-ID Methodology.

### 3. HITL review HTML UX pilot
expected: open `gen_registry_review.py` output in a browser against ep01 fixture; cluster cards readable, merge/split/rename/confirm/reject intuitive, "Export edits" produces a valid registry.edits.json. Especially pilot the CR-01 split-partition UX.
result: pending (visual ergonomics; automated checks verify presence of cards/buttons/Blob export + XSS-escaping, not usability)
why deferred: first-class deliverable; automated checks cover structure + security, human covers usability.

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

None — all 3 items are pre-authorized deferred cross-repo dependencies, not gaps in this repo's deliverable. Phase 7 producer-side is complete and code-review-clean (11/11 findings fixed).
