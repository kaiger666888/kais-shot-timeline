---
phase: 11
slug: contract-v1-2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-25
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for the v1.2 contract lock. This phase is pure schema/contract/fixture/proof work — validation is jsonschema validation + bidirectional cross-version proof + byte-identical-absent diff, NOT unit tests.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `jsonschema` 4.26.0 (already installed) + Python 3.12.3 stdlib |
| **Config file** | none — Wave 0 reuses existing `scripts/verify_contract.py` |
| **Quick run command** | `python3 scripts/verify_contract.py --quick` (schema-validate v1.2 fixture 12/12) |
| **Full suite command** | `python3 scripts/verify_contract.py` (bidirectional: forward v1.1×v1.2=0 errors + backward v1.2×recovered-v1.1=only additionalProperties + speakers⊆characters consistency) |
| **Estimated runtime** | ~5 seconds (jsonschema validation is fast; no ML) |

---

## Sampling Rate

- **After every task commit:** Run `python3 -c "import json,glob,jsonschema; ..."` quick schema-validates any new/changed fixture file.
- **After every plan wave:** Run `python3 scripts/verify_contract.py` (full bidirectional proof).
- **Before `/gsd:verify-work`:** Full suite must be GREEN (forward 0 errors + backward only-additionalProperties + 12/12 fixtures valid + byte-identical-absent diff clean).
- **Max feedback latency:** ~5 seconds.

---

## Validation Dimensions (contract phase)

| Dimension | What it proves | Automated command |
|-----------|----------------|-------------------|
| **Schema validity** | 3 new + 10 extended schemas are draft 2020-12 + `additionalProperties:false` | `jsonschema.Draft202012Validator` on each `spec/schemas/*.schema.json` |
| **Fixture conformance** | 12-file v1.2 fixture validates 12/12 under V12_ORDER | `verify_contract.py` forward path |
| **Additive-only proof (Pitfall 11)** | v1.0/v1.1 fixtures byte-identical when audio_semantic.json + speakers.json absent | `git diff` v1.1 fixture vs v1.2 fixture minus the 2 new files = empty |
| **Backward compatibility** | v1.2 fixture × recovered-v1.1 schema = ONLY additionalProperties errors (no breaking change) | `verify_contract.py` `_recover_v11_schema()` backward path |
| **Cross-version forward** | v1.1 fixture × v1.2 schema = 0 errors (additive) | `verify_contract.py` forward path |
| **Fixture consistency** | `speakers.char_id ⊆ characters.id` where characters present | new consistency check in verify_contract.py |
| **SCHEMA_VERSION single-source** | `"1.2"` literal in exactly one place (export_asset.py), schema pattern unchanged | `grep -c 'SCHEMA_VERSION = "1.2"' scripts/export_asset.py` == 1 |

---

## Per-Task Verification Map

> Populates after the planner emits PLAN task IDs. Each schema/fixture/proof task maps to its validation command above. The verifier (Phase 11 VERIFICATION.md) checks all 5 ROADMAP success criteria (SC#1 schemas validate + asset extended; SC#2 SCHEMA_VERSION single-source + byte-identical-absent; SC#3 12-file fixture 12/12 + v1.1 still 10/10; SC#4 verify_contract.py bidirectional GREEN; SC#5 SPEC §4 Changelog + §5 shapes + fidelity_disclaimer).

| Task ID | Plan | Wave | Requirement | Automated Command | Status |
|---------|------|------|-------------|-------------------|--------|
| _(pending planner task IDs)_ | | | CONTRACT-01..05 | _(see Dimensions above)_ | draft |

---

## Manual-Only Verifications

- **SPEC.md prose review** — the §4 Changelog 1.2 entry + §5 shapes + fidelity_disclaimer are human-readable; reviewer confirms they honestly frame the Phase-10-informed deviations (instruments absent, emotion=calibrated estimate, word-level=experimental). AF-01/AF-02/AF-03 invariant.
- **fidelity_disclaimer completeness** — must explicitly state: emotion=calibrated estimate (not rigorous F1), word-level=experimental, instruments=absent (deferred v1.3). Reviewer confirms all three present.
