---
phase: 06-cinematography-auto-fill-step-semantic
plan: 01
subsystem: infra
tags: [jsonschema, contract, asset-manifest, graceful-degrade, sidecar]

# Dependency graph
requires:
  - phase: 05-contract-v1-1
    provides: asset.schema.json v1.1 (additionalProperties:false + generator.required=[tool,version,generated_at])
provides:
  - "asset.schema.json#generator.warnings: array<string> (optional, additive-only — the channel Plan 02's analysis/call_shot_analysis.py populates on cinematography route failure)"
  - "export_asset.build_asset_dict(warnings=None) signature + main() route_cache/warnings.json sidecar read"
  - "SPEC.md §3 generator.warnings row + §4 Changelog Phase 6 bullet (no schema_version bump)"
  - "spec/fixtures/v1.1/asset.json generator.warnings example (route-down scenario)"
affects: [06-02-call-shot-analysis-client, 06-03-run-pipeline-integration, 07-reid-registry, 09-canvas-consumer]

# Tech tracking
tech-stack:
  added: []  # zero new packages — stdlib (json/os) + existing jsonschema only
  patterns:
    - "Contract-first schema extension (mirror Phase 5 sequencing): extend asset.schema.json BEFORE producer emits the new field — inline Draft202012Validator (validate_asset_json) would otherwise reject generator.warnings under additionalProperties:false"
    - "Additive-only field addition under v1.1: new optional property inside generator.properties; required[] byte-identical; additionalProperties:false retained; schema_version unchanged — entire v1.1 milestone (phases 5-9) shares one minor"
    - "Best-effort sidecar read pattern: producer reads work_dir-local JSON sidecar, silent fallback to None on any OSError/JSONDecodeError/missing-file/malformed-shape — exporter MUST NOT fail on bad sidecar (graceful-degrade)"
    - "Conditional dict emit: `**({'warnings': warnings} if warnings else {})` — Python idiom for 'include key only when value is truthy', keeping clean runs / old assets byte-compatible with v1.0 emit shape"

key-files:
  created:
    - .planning/phases/06-cinematography-auto-fill-step-semantic/06-01-SUMMARY.md
  modified:
    - spec/schemas/asset.schema.json
    - scripts/export_asset.py
    - spec/SPEC.md
    - spec/fixtures/v1.1/asset.json

key-decisions:
  - "Additive-only under v1.1 (no schema_version bump): generator.warnings is an optional property; required[] stays [tool,version,generated_at]; entire v1.1 milestone (phases 5-9) keeps schema_version='1.1'. Major bump reserved for genuinely-breaking change."
  - "Producer emits warnings ONLY when non-empty list (None / [] → OMITTED). Schema accepts both ways; graceful-degrade default = clean runs produce no warnings key, byte-identical to v1.0 emit shape."
  - "Sidecar poisoning accepted (T-06-03): route_cache/warnings.json lives inside operator work_dir filesystem trust boundary (same trust level as shots.json, transcript.json). Best-effort read on malformed sidecar; no signing introduced (YAGNI — single-user CLI)."
  - "Operator-facing failure content only (T-06-01 mitigation): schema description + SPEC §3 description both forbid PII/auth tokens/body payloads — warnings carry exception class+message and route status codes only."

patterns-established:
  - "Contract-first phase sequencing: when a downstream plan will emit a new schema field, the schema/SPEC/fixture extension MUST land in an earlier plan than the producer code — otherwise the producer's own inline validator (Draft202012Validator with additionalProperties:false) rejects the output mid-pipeline."
  - "Sidecar → manifest merge pattern: pipeline stages write work_dir-local sidecar JSONs (e.g. route_cache/warnings.json); the exporter reads them best-effort and merges into the manifest. Stages stay decoupled — no inter-stage imports."
  - "Graceful-degrade evidence channel: generator.warnings is the runtime trail showing *why* an asset degraded (route unreachable, per-shot failure). Consumers read it for diagnostics; producers emit it on any non-fatal deviation."

requirements-completed: [CINEMA-05]

# Metrics
duration: 4min
completed: 2026-07-24
---

# Phase 6 Plan 01: generator.warnings Contract Extension Summary

**Optional `asset.schema.json#generator.warnings: array<string>` added additively under v1.1 (no schema_version bump); `export_asset.py` plumbs a `route_cache/warnings.json` sidecar → `build_asset_dict(warnings=None)` → conditional emit — the channel Plan 02's cinematography route client will populate on graceful-degrade.**

## Performance

- **Duration:** ~4 min (250s)
- **Started:** 2026-07-24T14:45:33Z
- **Completed:** 2026-07-24T14:49:43Z
- **Tasks:** 2
- **Files modified:** 4 (all in plan scope)

## Accomplishments

- **Schema extended additively:** `asset.schema.json#generator.properties.warnings` is now `array<string>` (optional, v1.1 Phase 6). `required[]` byte-identical to Phase 5 (`[tool, version, generated_at]`); `additionalProperties: false` retained; `schema_version` pattern unchanged (literal stays `"1.1"`). Threat model T-06-02 (schema injection via unknown fields) mitigated.
- **Producer plumbing landed:** `build_asset_dict(work_dir, video, warnings=None)` conditionally emits `generator.warnings` only when the list is non-empty (None / `[]` → key omitted, schema-valid both ways). `main()` reads `route_cache/warnings.json` sidecar best-effort with silent fallback on `OSError`/`JSONDecodeError`/missing-file/non-`list[str]` shape — exporter never fails on a bad sidecar (T-06-03 accept, T-06-04 mitigate).
- **SPEC synchronized:** §3 field table gains `generator.warnings` row (v1.1 optional, producer flow documented); §4 Changelog's existing `1.1` entry's header renamed `Phase 5` → `Phases 5-9` and gains a Phase 6 bullet (no new dated entry → no version bump).
- **Fixture round-trip closed:** `spec/fixtures/v1.1/asset.json` carries a 2-item `generator.warnings` example demonstrating the route-down scenario (preflight `ConnectError` + per-shot route `code=500`); `spec/fixtures/minimal/asset.json` (v1) unchanged — proves graceful-degrade backward compatibility.
- **Regression gates green:** `python3 spec/validate.py` exits 0 (minimal 6/6 + v1.1 9/9); `python3 scripts/verify_contract.py --mode=producer` exits 0 (cross-version forward 0 errors / backward 0 non-additive errors).

## Task Commits

Each task was committed atomically:

1. **Task 1: schema extension + exporter plumbing** — `2a6d56b` (feat)
2. **Task 2: SPEC §3 + Changelog + v1.1 fixture example** — `1e13039` (docs)

## Files Created/Modified

- `spec/schemas/asset.schema.json` — added `generator.properties.warnings` (array<string>, optional, v1.1 Phase 6); required[] / additionalProperties / schema_version pattern untouched. Pure additive: `git diff` shows only new lines inside the generator.properties block.
- `scripts/export_asset.py` — `build_asset_dict` signature gained `warnings: list[str] | None = None`; conditional emit `**({"warnings": warnings} if warnings else {})`; `main()` reads `route_cache/warnings.json` best-effort (silent fallback on any error/malformed shape); docstrings updated (Chinese, per CLAUDE.md).
- `spec/SPEC.md` — §3 field table: new `generator.warnings` row after `generator.generated_at`; §4 Changelog: existing `1.1` entry header renamed `Phase 5` → `Phases 5-9`, new Phase 6 bullet appended (no version bump, no new dated entry).
- `spec/fixtures/v1.1/asset.json` — generator block gains 2-item warnings example (preflight ConnectError + per-shot route code=500); existing tool/version/generated_at unchanged.

## Decisions Made

- **Additive-only under v1.1 (no schema_version bump):** Generator warnings are an optional property; required[] stays `[tool,version,generated_at]`. The entire v1.1 milestone (phases 5-9) shares `schema_version="1.1"` — major bump is reserved for genuinely-breaking change (rename/semantic-shift/removal/added-required). Verified via `git diff` showing only new lines inside the properties block.
- **Producer emits warnings ONLY when non-empty list:** `None` / `[]` → key omitted. This means a clean run produces an asset.json byte-identical to the v1.0 emit shape (graceful-degrade default), and the v1 minimal fixture staying warnings-free is proof of optionality.
- **Best-effort sidecar read with shape validation:** Beyond just catching `OSError`/`JSONDecodeError`, the loader also verifies `.get("warnings")` is a `list[str]` — non-str elements or wrong shape → silent fallback to None. Threat model T-06-03 (sidecar poisoning) explicitly accepted: sidecar lives inside operator work_dir trust boundary.
- **SPEC Changelog extension (not new entry):** Adjusted the existing `2026-07-24 — 1.1` entry header to `Phases 5-9` and appended a Phase 6 bullet. Did NOT create a new dated entry — that would imply a version bump which does not occur.

## Deviations from Plan

None - plan executed exactly as written. The plan's `<interfaces>` block and `<critical_constraints>` (additive-only, required unchanged, additionalProperties:false retained, schema_version "1.1") were followed byte-for-byte. All Task 1 and Task 2 acceptance criteria passed on first run; no auto-fixes (Rules 1-3) or architectural decisions (Rule 4) were needed.

## Issues Encountered

None. Pre-existing orchestrator changes to `.planning/STATE.md` (execution-start metadata) were present in the working tree but were correctly excluded from both task commits (only plan-listed files staged per task_commit_protocol).

## User Setup Required

None - no external service configuration required. This plan adds zero new packages (stdlib `json`/`os` + existing `jsonschema` only) and touches only contract/spec/fixture files. The `route_cache/warnings.json` sidecar is written by `analysis/call_shot_analysis.py` in Plan 02 (not yet present) — until Plan 02 lands, `main()` simply observes the sidecar is missing and falls back to `warnings=None`.

## Next Phase Readiness

**Ready for Plan 02 (analysis/call_shot_analysis.py):** The schema + exporter channel is now open. Plan 02 can write `output/<asset>/route_cache/warnings.json` on any cinematography route failure (preflight unreachable / per-shot non-200 / `httpx.HTTPError`) and trust that `export_asset.py:main` will read it and surface the failures in `generator.warnings` without breaking asset export.

**Ready for Plan 03 (run_pipeline integration):** `step_export` is already wired to call `export_asset.py`; no further plumbing needed in Plan 03 for the warnings flow itself. Plan 03's job is `step_semantic` slot insertion + flag threading (`--analysis-url`, `--analysis-timeout`, `--offline`, `--skip-semantic`).

**Blockers/concerns:** None for this plan. The Phase 6 cross-repo branch merge blocker (kais-aigc-platform `feat/shot-geometry-nodes` + `feat/shot-analysis-route` unmerged) only affects live E2E round-trip verification (Plans 02/03 use captured fixtures + route-down mode, per STATE.md pre-authorization).

## Self-Check: PASSED

- **Files created/modified:** all 5 FOUND (`spec/schemas/asset.schema.json`, `scripts/export_asset.py`, `spec/SPEC.md`, `spec/fixtures/v1.1/asset.json`, `06-01-SUMMARY.md`).
- **Task commits:** both FOUND (`2a6d56b` Task 1, `1e13039` Task 2).
- **`python3 spec/validate.py`:** exits 0 — minimal 6/6 + v1.1 9/9 green (additive proof + fixture round-trip closed).
- **`python3 scripts/verify_contract.py --mode=producer`:** exits 0 — no harness regression; cross-version forward 0 errors / backward 0 non-additive errors.

---
*Phase: 06-cinematography-auto-fill-step-semantic*
*Plan: 01*
*Completed: 2026-07-24*
