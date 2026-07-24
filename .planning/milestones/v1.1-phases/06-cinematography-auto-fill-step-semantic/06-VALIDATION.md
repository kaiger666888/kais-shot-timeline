---
phase: 6
slug: cinematography-auto-fill-step-semantic
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-24
---

# Phase 6 — Validation Strategy

> Derived from `06-RESEARCH.md` §Validation Architecture. The route is NOT running, so verification = (a) mapping correctness against 7 captured fixtures, (b) graceful-degrade against route-down (testable now), (c) cache behavior with captured output as fixture. Live round-trip DEFERRED (feat/shot-analysis-route unmerged). Repo has no pytest — standalone `sys.exit(0/1)` scripts + inline jsonschema are the assertion engine.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (standalone Python, `sys.exit(0/1)`; inline jsonschema Draft202012Validator) |
| **Quick run command** | `python3 -c "from analysis.call_shot_analysis import compose_facets; ..."` (mapping unit check) + `python3 spec/validate.py` (schema regression) |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` |
| **Estimated runtime** | ~3 seconds |

## Per-Task Verification Map

| Req | Plan | Wave | Behavior | Test Type | Automated Command | Status |
|-----|------|------|----------|-----------|-------------------|--------|
| CINEMA-00 (schema) | 01 | 1 | asset.schema.json#generator + optional `warnings` array; additive, v1.1 unchanged | schema-validity | `python3 spec/validate.py` (minimal + v1.1 fixtures green) | ⬜ |
| CINEMA-01 | 02 | 2 | `analysis/call_shot_analysis.py` compose_facets maps route→prompts; verified against 7 captured fixtures | unit (mapping) | inline `compose_facets(json.load(shot_00X))` → schema-valid prompts entry for all 7 | ⬜ |
| CINEMA-01 | 02 | 2 | httpx POST body `{video, shots, shot_id_range:[N,N], semantic:true, subject:false}` matches route contract | contract-conformance | code review vs RESEARCH §Route REQUEST Contract | ⬜ |
| CINEMA-02 | 03 | 2 | run_pipeline `step_semantic` slots between transcribe + timeline; counter `[N/7]` | integration | `grep -c "\[N/7\]" run_pipeline.py` + step order in main() | ⬜ |
| CINEMA-03 | 02/03 | 2 | route-down (--offline / unreachable) → empty-string facets + `generator.warnings` + asset exports | graceful-degrade | run call_shot_analysis against bad URL → empty facets + warning; `python3 spec/validate.py` green | ⬜ |
| CINEMA-04 | 02 | 2 | per-shot cache `route_cache/shot_analysis/shot_XXX.json`; key (content_hash, shot_id, route_name, route_version); --offline cache-only | caching | seed cache with captured fixture, run --offline → cache hit, no network | ⬜ |
| CINEMA-05 | 02/03 | 2 | preflight health check; per-shot failure non-fatal; generator.warnings populated | behavior | mock per-shot failure → warning recorded, asset still exports | ⬜ |
| CINEMA-06 | 03 | 2 | `--analysis-url` / `--analysis-timeout` (default 960) / `--offline` / `--skip-semantic` flags | CLI | `python3 run_pipeline.py --help` lists all 4; defaults correct | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red*

## Wave 0 Requirements

- [ ] asset.schema.json#generator + optional `warnings` (CINEMA-00 schema extension, sequenced FIRST — contract-first)
- [ ] export_asset.py `build_asset_dict(warnings=None)` plumbing + emit
- [ ] analysis/call_shot_analysis.py (NEW — httpx client + compose_facets + cache + preflight)
- [ ] run_pipeline.py step_semantic + `[N/7]` renumber + 4 flags + --force cache list
- [ ] spec/fixtures/v1.1/asset.json + a v1.1 producer asset gain a `warnings` example (fixture sync)
- [ ] SPEC.md §3 generator.warnings row (CONTRACT-08-spirit)

*No new test framework — existing harness + inline checks.*

## Manual-Only Verifications

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Live route round-trip (route reachable, real fill) | feat/shot-analysis-route unmerged; route not running (STATE.md blocker, pre-authorized deferred) | Post-merge: start kais-aigc-platform backend on the route branch, run step_semantic against ep01, confirm real cinematography lands in prompts.json |

**Approval:** approved (2026-07-24) — verification scope is mapping+degrade+cache (all testable now); live E2E explicitly deferred per STATE.md.
