---
phase: 5
slug: contract-v1-1
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-24
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` §Validation Architecture. Phase 5 is a **contract/spec phase** — the validation harness IS the test framework (this repo has no pytest/jest; per v1.0 RETROSPECTIVE "Patterns Established": standalone Python verify scripts that `sys.exit(0/1)`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (standalone Python scripts, `sys.exit(0/1)`) — `jsonschema 4.26.0` Draft202012Validator is the assertion engine |
| **Config file** | none — inline in `spec/validate.py` + `scripts/verify_contract.py` |
| **Quick run command** | `python3 spec/validate.py` |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` |
| **Estimated runtime** | ~1 second (quick); ~3 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `python3 spec/validate.py`
- **After every plan wave:** Run the full suite command above
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~3 seconds

---

## Per-Task Verification Map

> Mapping mirrors ROADMAP.md Plan→REQ coverage. Plans: 05-01 (Wave 1: 5 schemas), 05-02 (Wave 1: SCHEMA_VERSION constant + PROJECT.md drift), 05-03 (Wave 2: v1.1 fixture set), 05-04 (Wave 3: harness + prose).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-T1 | 01 | 1 | CONTRACT-01 | T-V5/V12 | characters.schema.json `additionalProperties:false` + anti-traversal + ID `^char_[0-9]{3}$` + `looks[]` | schema-validity | `python3 -c "import json; from jsonschema import Draft202012Validator as V; s=json.load(open('spec/schemas/characters.schema.json')); i=json.load(open('spec/fixtures/v1.1/characters.json')); assert not list(V(s).iter_errors(i))"` | ❌ W0 | ⬜ pending |
| 05-01-T1 | 01 | 1 | CONTRACT-02 | T-V5/V12 | props.schema.json (ID `^prop_[0-9]{3}$`, `states[]` not `looks[]`) | schema-validity | same pattern, props schema/fixture | ❌ W0 | ⬜ pending |
| 05-01-T1 | 01 | 1 | CONTRACT-03 | T-V5 | registry.schema.json clusters[] refs-only + tier enum + mean_cosine + review_state | schema-validity | same pattern, registry schema/fixture | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 1 | CONTRACT-04 | — | prompts.schema.json additive (+character_refs[]/prop_refs[], `required` byte-identical to v1.0) | schema-validity + cross-version | `python3 spec/validate.py` (v1 minimal prompts green) + `_cross_version_check` (a) | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 1 | CONTRACT-05 | T-V12 | asset.schema.json additive (+data/media characters/props, schema_version pattern unchanged) | schema-validity + cross-version | `python3 spec/validate.py` + `_cross_version_check` (a)+(b) | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 1 | CONTRACT-06 | — | export_asset.py emits `schema_version:"1.1"` via `SCHEMA_VERSION` constant | producer smoke | export + `python3 -c "import json; assert json.load(open('<asset>'))['schema_version']=='1.1'"` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 2 | CONTRACT-01..05 | — | v1.1 fixtures (characters/props/registry/prompts/asset) validate green against Plan-01 schemas | schema-validity | `python3 spec/validate.py` (v1.1 pass) | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 2 | CONTRACT-09 | — | v1 minimal fixture stays 6/6 green after Plan-01 schema extensions | backward-compat | `python3 spec/validate.py` (minimal pass, regression guard) | ✅ exists | ⬜ pending |
| 05-04-T1 | 04 | 3 | CONTRACT-07 | — | verify_contract.py EIGHT_SHAPES + `_cross_version_check` both directions + fail-loud still works | harness | `python3 scripts/verify_contract.py --mode=producer && PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | ❌ W0 | ⬜ pending |
| 05-04-T2 | 04 | 3 | CONTRACT-08 | — | SPEC.md §4 Changelog 1.1 + §5.6/§5.7 + §1 index consistent with schemas | manual (prose) | human review (two-tier authority: schema is machine truth) | ❌ W0 | ⬜ pending |
| 05-04-T1 | 04 | 3 | CONTRACT-09 | — | validate.py dual-pass (minimal + v1.1) + backward cross-version check | backward-compat | `python3 spec/validate.py` (both fixture sets green) | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `spec/schemas/characters.schema.json` — NEW (CONTRACT-01)
- [ ] `spec/schemas/props.schema.json` — NEW (CONTRACT-02)
- [ ] `spec/schemas/registry.schema.json` — NEW (CONTRACT-03)
- [ ] `spec/schemas/prompts.schema.json` — EXTENDED additively (CONTRACT-04)
- [ ] `spec/schemas/asset.schema.json` — EXTENDED additively (CONTRACT-05)
- [ ] `spec/fixtures/v1.1/` — NEW (9 files: asset/shots/audio_analysis/transcript/frames/prompts/characters/props/registry.draft)
- [ ] `scripts/export_asset.py` — `SCHEMA_VERSION` constant + line-160 literal replacement (CONTRACT-06)
- [ ] `scripts/verify_contract.py` — `EIGHT_SHAPES` + `_cross_version_check` (CONTRACT-07)
- [ ] `spec/validate.py` — shape maps discover + validate v1.1 fixture set (CONTRACT-09 regression)
- [ ] `spec/SPEC.md` — §4 Changelog + §5.6/§5.7 + §1 index (CONTRACT-08)
- [ ] `spec/README.md` — layout block + index update (CONTRACT-08 consistency)

*No new test framework — existing `sys.exit(0/1)` harness extends in place.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SPEC.md §4/§5.6/§5.7 prose consistent with schemas | CONTRACT-08 | Prose has no machine checker; two-tier authority means schema is truth, SPEC is human overview | Read SPEC.md §4 Changelog has `1.1` entry; §5.6 documents characters data shape + external png convention; §5.7 documents props; §1 schema-file index lists the 3 new schemas |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 3s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (2026-07-24, plan-checker — 0 blockers, 4 doc-drift warnings fixed)
