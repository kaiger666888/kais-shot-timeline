---
phase: 8
slug: prompt-reference-system-shot-timeline-html-gallery
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-25
---

# Phase 8 — Validation Strategy

> Derived from `08-RESEARCH.md` §Validation Architecture. **NO deferred-blocking humans this phase** (unlike Phase 7's route-blocked items) — every requirement is testable NOW on the v1.1 fixture set (confirmed registry + fixture prompts + fixture asset). The 2 manual items (gallery UX pilot, recomposed prompt_text readability) are pilots, not blockers. Repo has no pytest — standalone `sys.exit(0/1)` scripts + inline jsonschema (carried from Phase 5–7).

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (standalone Python, `sys.exit(0/1)`; inline jsonschema Draft202012Validator) — carried from Phase 5–7 |
| **Quick run command** | `python3 spec/validate.py` (schema regression, ~3s) |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 scripts/verify_phase8_smoke.py` (~8s) |
| **Estimated runtime** | ~8 seconds |

## Per-Task Verification Map

| Req | Plan | Wave | Behavior | Test Type | Automated Command | Status |
|-----|------|------|----------|-----------|-------------------|--------|
| PROMPT-04 (schema additive) | 01 | 1 | `asset.schema.json#generator.registry_snapshot` declared; old assets (no snapshot) still validate; new assets validate | schema-validity | `python3 spec/validate.py` (v1.1 asset fixture green) | ⬜ |
| PROMPT-01 (attach) | 02 | 2 | `attach_refs.py` on fixture registry+prompts → every shot has correct `character_refs[]`/`prop_refs[]` per `appearance_shots[]` | unit (mapping) | inline `from prompts.attach_refs import attach` + assert vs fixture | ⬜ |
| PROMPT-01 (graceful) | 02 | 2 | no characters.json/props.json → refs empty, schema-valid, exit 0 | graceful-degrade | `python3 scripts/verify_phase8_smoke.py` (scenario 1) | ⬜ |
| PROMPT-02 (determinism) | 02 | 2 | recompose → `prompt_text` matches template; re-run byte-identical | unit + integration | inline `_recompose` + smoke scenario 2 (byte-diff) | ⬜ |
| PROMPT-04 (snapshot freeze) | 02 | 2 | `registry_snapshot` reflects confirmed registry at export; mutating registry after export doesn't change snapshot | integration (freeze) | smoke scenario 3 | ⬜ |
| PROMPT-04 (confirmed-only) | 02 | 2 | snapshot filters non-confirmed (Pitfall 7) | unit (filter) | smoke scenario 5 | ⬜ |
| PROMPT-03 (integrity) | 02 | 2 | dangling `character_refs[]`/`prop_refs[]` ID detected by producer verify_contract.py | contract-integrity | `python3 scripts/verify_contract.py --mode=producer` (extended) + smoke scenario 4 | ⬜ |
| PRESENT-01 (gallery) | 03 | 3 | `gen_timeline_html.py` → HTML contains gallery section with character/prop cards | integration | grep `"gallery-card"` on generated HTML | ⬜ |
| PRESENT-02 (chips) | 03 | 3 | per-shot row contains ref-chip anchors linking to `#gallery-<id>` | integration | grep `"ref-chip"` | ⬜ |
| PRESENT-03 (indicator) | 03 | 3 | per-shot row contains fill-chip; green when facets filled, gray when empty | integration + unit | grep `"fill-filled"` / `"fill-degraded"` | ⬜ |
| PRESENT-01/02 XSS inert | 03 | 3 | `name="</script>..."` → HTML does NOT contain raw `</script><script>` | security (XSS) | smoke scenario 6 | ⬜ |
| Pitfall 9 (mtime cache) | 03 | 3 | step_timeline regenerates after attach_refs rewrites prompts (mtime cache includes prompts_json) | integration | smoke / code-inspect mtime inputs | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red*

## Wave 0 Requirements

- [ ] `spec/schemas/asset.schema.json` — MODIFY (additive `generator.registry_snapshot` property; schema_version stays "1.1")
- [ ] `spec/fixtures/v1.1/asset.json` — MODIFY (example registry_snapshot; sync prompts.json prompt_text if needed)
- [ ] `spec/SPEC.md` — MODIFY (§3 generator row + Changelog Phase 8 bullet)
- [ ] `prompts/attach_refs.py` — NEW (attach + recompose + schema validate + atomic write; idempotent)
- [ ] `scripts/export_asset.py` — MODIFY (`_build_registry_snapshot` helper + conditional emit)
- [ ] `scripts/verify_contract.py` — MODIFY (`_producer_registry_integrity` + prompts↔registry direction)
- [ ] `html/gen_timeline_html.py` — MODIFY (gallery + chips + indicator + `_esc()` + JSON-in-script escape)
- [ ] `run_pipeline.py` — MODIFY (`step_timeline` invokes attach_refs as pre-step + mtime cache includes prompts_json)
- [ ] `scripts/verify_phase8_smoke.py` — NEW 6-scenario regression (mirror verify_phase7_smoke.py)
- [ ] `README.md` install line — NO change (zero new deps)

## Manual-Only Verifications (pilots, NOT blockers)

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Gallery UX pilot | Visual gallery is a first-class deliverable; automated checks verify presence of cards/chips, not readability | Open generated timeline.html in browser against ep01; confirm gallery cards render w/ thumbnails, chips click-scroll correctly, indicator colors match |
| Recomposed prompt_text readability | Deterministic template guarantees structure, not natural prose for downstream AI pipelines | Spot-check 3-5 recomposed prompt_text strings; if awkward, adjust template (Claude's Discretion per CONTEXT Q2) + re-lock |

**Approval:** approved (2026-07-25) — verification scope is schema-validity + attach idempotency/determinism + snapshot freeze + integrity + XSS-inert + graceful-degrade (all testable now on the fixture set). 2 UX/readability pilots are non-blocking.
