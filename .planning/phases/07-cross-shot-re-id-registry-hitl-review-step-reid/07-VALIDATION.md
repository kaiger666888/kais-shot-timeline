---
phase: 7
slug: cross-shot-re-id-registry-hitl-review-step-reid
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-25
---

# Phase 7 — Validation Strategy

> Derived from `07-RESEARCH.md` §Validation Architecture. The `character-reid` route is DEFERRED (does not exist in kais-aigc-platform yet — mirrors Phase 6's `feat/shot-analysis-route` pre-merge state). Verification = (a) schema-validity of registry.draft/edits/characters/props against the Phase-5-shipped contract, (b) graceful-degrade (route-down → asset exports without registry + `generator.warnings`), (c) confirmed-only gating (Pitfall 7 hard-assert), (d) apply_edits idempotency, (e) registry↔shots cross-file integrity, (f) 5-scenario smoke harness. Live round-trip + empirical τ calibration + HITL UX pilot are DEFERRED (pre-authorized per STATE.md blocker + CONTEXT Q2). Repo has no pytest — standalone `sys.exit(0/1)` scripts + inline jsonschema are the assertion engine (carried from Phase 6).

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (standalone Python, `sys.exit(0/1)`; inline jsonschema Draft202012Validator) — carried from Phase 6 |
| **Quick run command** | `python3 spec/validate.py` (schema regression) + `python3 -c "from registry.apply_edits import apply_edits; ..."` (inline unit) |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 scripts/verify_phase7_smoke.py` |
| **Estimated runtime** | ~5 seconds (Phase 6 ~3s + Phase 7 smoke ~2s) |

## Per-Task Verification Map

| Req | Plan | Wave | Behavior | Test Type | Automated Command | Status |
|-----|------|------|----------|-----------|-------------------|--------|
| registry-edits (schema) | 01 | 1 | `registry-edits.schema.json` (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids); fixture validates | schema-validity | `python3 spec/validate.py` (NINE_SHAPES incl. registry-edits green) | ⬜ |
| CAST-05 (draft shape) | 02 | 2 | `call_reid.py` normalizes route response → registry.draft.json schema-valid; v1.1 fixture green | unit (mapping) | inline `from analysis.call_reid import normalize_clusters` + `python3 spec/validate.py` | ⬜ |
| CAST-05 (proposed default) | 02 | 2 | every cluster in registry.draft.json has `review_state=="proposed"` | unit | inline check on fixture | ⬜ |
| CAST-06 (HTML renders) | 03 | 2 | `gen_registry_review.py` on fixture draft → HTML written + cluster cards + "Export edits" button + three-tier viz | integration | `python3 html/gen_registry_review.py --draft <fixture> --video <tiny> --output /tmp/review.html` + grep "Export edits" | ⬜ |
| CAST-07 (confirmed-only) | 03 | 2 | `apply_edits.py` on draft+edits → characters.json/props.json contain ONLY `review_state:"confirmed"` (hard assert) | unit (gate) | inline `all(c['review_state']=='confirmed' for c in chars)` | ⬜ |
| CAST-07 (idempotent) | 03 | 2 | same draft+edits → apply twice → byte-identical canonical files | integration | run apply_edits twice + `diff` | ⬜ |
| CAST-07 (appearance_shots ⊆ shots) | 03/04 | 2 | every appearance_shots[] / cluster member shot_id exists in shots.json | contract-integrity | `python3 scripts/verify_contract.py --mode=producer` (extended) | ⬜ |
| CAST-09 (route down degrade) | 04 | 2 | unreachable URL → registry.draft.json absent + asset exports without characters/props + generator.warnings non-empty | graceful-degrade | `python3 scripts/verify_phase7_smoke.py` (scenario 1) | ⬜ |
| CAST-09 (--skip-reid) | 04 | 2 | `--skip-reid` → step returns None, no subprocess | CLI | `python3 scripts/verify_phase7_smoke.py` (scenario 2) | ⬜ |
| CAST-09 (counter [N/8]) | 04 | 2 | run_pipeline.py has `[N/8]` counter + step_reid in slot 6 of 8 | integration | `grep -c "\[N/8\]" run_pipeline.py` + step order check | ⬜ |
| CONTRACT-06 (conditional emit) | 04 | 2 | characters.json present → emit data.characters/props + media.characters[]/props[]; absent → omit (byte-identical to v1.0) | contract-conformance | `python3 scripts/verify_phase7_smoke.py` (scenario 1 + 3) | ⬜ |
| CONTRACT-06 (media pattern) | 01/04 | 1 | media.characters[]/props[] paths match anti-traversal png pattern | schema-validity | `python3 spec/validate.py` (v1.1 asset fixture green) | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red*

## Wave 0 Requirements

- [ ] `spec/schemas/registry-edits.schema.json` — NEW edits round-trip schema (sequenced FIRST — contract-first, mirrors Phase 5/6 pattern)
- [ ] `spec/fixtures/v1.1/registry.edits.json` — NEW fixture (edits against the existing registry.draft.json fixture)
- [ ] `analysis/call_reid.py` — NEW httpx client + normalize_clusters + per-video cache (mirror call_shot_analysis.py)
- [ ] `registry/apply_edits.py` — NEW draft+edits → canonical confirmed-only gate (Pitfall 7)
- [ ] `html/gen_registry_review.py` — NEW HITL review HTML (first-class deliverable)
- [ ] `scripts/export_asset.py` — MODIFY build_asset_dict (conditional characters/props emission — closes CONTRACT-06)
- [ ] `scripts/verify_contract.py` — MODIFY _fixture_consistency_check (registry↔shots + confirmed-only assert)
- [ ] `scripts/verify_phase7_smoke.py` — NEW 5-scenario regression (mirror verify_phase6_smoke.py)
- [ ] `run_pipeline.py` — MODIFY +step_reid + `[N/7]`→`[N/8]` + 4 flags + --force cache list
- [ ] `spec/validate.py` — MODIFY EIGHT_SHAPES → NINE_SHAPES (add registry-edits)
- [ ] `README.md` install line — NO change (zero new deps; httpx already documented Phase 6)

*No new test framework — existing harness + inline checks.*

## Manual-Only Verifications

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Live route round-trip (route reachable, real re-id) | `character-reid` route DEFERRED (STATE.md blocker; mirrors `feat/shot-analysis-route` pre-merge state) — route not running | Post-merge: start kais-aigc-platform backend on the new route branch, run step_reid against ep01, confirm real registry.draft.json lands + review HTML renders real clusters |
| Empirical τ calibration on ep01 | Needs SAM3 character crops that don't exist until route ships (CONTEXT Q2) | Post-merge: follow RESEARCH §DINOv2 Re-ID Methodology → deferred τ calibration protocol (same-person vs different-person cosine histogram, valley pick), update registry.schema.json `$comment` |
| HITL review UX pilot | Visual review HTML is a first-class deliverable; automated check verifies presence of cards/buttons but not usability | Open review HTML in browser against ep01 fixture; confirm cluster cards readable, merge/split/rename intuitive, export produces valid registry.edits.json |

**Approval:** approved (2026-07-25) — verification scope is schema-validity + degrade + confirmed-only-gate + idempotency + cross-file integrity + smoke (all testable now); live E2E + τ calibration + UX pilot explicitly deferred per STATE.md + CONTEXT Q2.
