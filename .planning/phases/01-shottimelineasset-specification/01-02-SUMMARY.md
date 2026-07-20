---
phase: 01-shottimelineasset-specification
plan: 02
subsystem: spec
tags: [contract, specification, documentation, human-readable, bilingual]

# Dependency graph
requires:
  - phase: 01-shottimelineasset-specification (Plan 01-01)
    provides: "6 JSON Schema files (spec/schemas/*.schema.json), minimal fixture (spec/fixtures/minimal/), jsonschema validator (spec/validate.py) — SPEC.md references each schema by filename and quotes field names/types/enums verbatim from them"
provides:
  - "spec/SPEC.md — authoritative human-readable ShotTimelineAsset contract document (455 lines, bilingual Chinese+English matching repo convention)"
  - "Cross-reference map from prose to the 6 machine-checkable schemas (each shape section ends with 'Reference schema: spec/schemas/<shape>.schema.json')"
  - "Verbatim graceful-degrade rule quote from asset.schema.json#schema_version.description, embedded in §4"
  - "Changelog subsection (§4) with initial '1 — initial contract' entry dated 2026-07-20"
affects:
  - "Phase 2 (EXPORT): producer exporter implementer reads SPEC.md first to understand the contract as a whole before touching code"
  - "Phase 3 (CANVAS): @kais/infinite-canvas consumer implementer reads SPEC.md to derive TS types and follow the graceful-degrade rule"
  - "Phase 4 (VERIFY): end-to-end regression test references SPEC.md sections as the human-readable oracle"

# Tech tracking
tech-stack:
  added: []  # No new libraries — pure Markdown documentation
  patterns:
    - "Two-tier authority: schemas = machine-checkable truth, SPEC.md = human-readable overview; on conflict, schema wins, but any drift is treated as a Phase-1 defect"
    - "Bilingual documentation (Chinese narrative + English technical terms) matching existing repo convention from spec/README.md, scripts/serve.py, etc."
    - "Producer-script attribution on every data shape — each shape section names the exact function that emits it (e.g. audio/separate_stems.py:analyze_shots) so producer/consumer implementers can trace prose to code"
    - "Verbatim schema quotes for normative rules (schema_version description, dominant_type enum, backend enum) — paraphrasing is forbidden to prevent silent drift"

key-files:
  created:
    - "spec/SPEC.md (455 lines — the authoritative prose contract)"
  modified: []

key-decisions:
  - "SPEC.md is the human-readable overview, NOT the authority; the 6 JSON Schema files remain the machine-checkable source of truth (CONTEXT D-01). SPEC.md explicitly states 'on conflict, schema wins'."
  - "Graceful-degrade rule quoted verbatim from asset.schema.json#schema_version.description rather than paraphrased — eliminates the SPEC↔schema drift failure mode that the human-verify checkpoint exists to catch."
  - "Bilingual style (Chinese narrative + English technical terms) chosen to match existing repo convention (spec/README.md, scripts/serve.py docstrings, validate.py docstring). All field names, enum values, paths, and code identifiers stay in English."
  - "Section numbering uses §1–§9 (with Title+Status as the unnumbered header) — slight deviation from the plan's literal 10-section count (which counted Title+Status as section 1), but identical content coverage."

patterns-established:
  - "Pattern: normative quotes from schemas — any SPEC.md statement that mirrors a schema rule must be a verbatim quote with a clear citation back to the source schema field, never a paraphrase."
  - "Pattern: producer-script attribution — every data shape documented in prose MUST name the producer script (file:function) so the doc stays grounded in actual emitter code, not aspirational shape."
  - "Pattern: 'reference schema:' footer — every shape section ends with a one-line pointer to its machine-checkable counterpart under spec/schemas/."

requirements-completed:
  - SPEC-01
  - SPEC-02
  - SPEC-03
  - SPEC-04

# Metrics
duration: ~15min (Task 1: ~10min write; Task 2: human-verify checkpoint approved on first review)
completed: 2026-07-20
---

# Phase 01 Plan 02: ShotTimelineAsset Contract Specification Summary

**455-line bilingual prose contract at `spec/SPEC.md` that makes the 6 machine-checkable schemas from Plan 01-01 navigable end-to-end — covers all 4 phase success criteria (5 data shapes, schema_version + graceful-degrade, canonical media + Range-aware 206 + serve.py, self-describing asset.json manifest), quotes the graceful-degrade rule verbatim from `asset.schema.json`, and was approved on first human review.**

## Performance

- **Duration:** ~15 min (Task 1 SPEC.md writing ~10 min; Task 2 human-verify checkpoint approved on first review, ~5 min reviewer turn-around)
- **Started:** 2026-07-20 (Task 1 commit c6f603d)
- **Completed:** 2026-07-20 (Task 2 human approval)
- **Tasks:** 2 (1 auto write + 1 checkpoint:human-verify)
- **Files created:** 1 (`spec/SPEC.md` — 455 lines)
- **Files modified:** 0

## Accomplishments

- `spec/SPEC.md` exists as the authoritative human-readable contract — a new contributor can absorb the entire ShotTimelineAsset contract in ~15 minutes without tribal knowledge.
- All 4 phase success criteria (SPEC-01..04) are covered in prose AND cross-referenced to the matching machine-checkable schema file, so a reader can jump from prose to formal contract in one click.
- Graceful-degrade rule quoted **verbatim** from `asset.schema.json#schema_version.description` (Plan 01-01) — eliminated the SPEC↔schema drift failure mode that was the headline threat (T-01-05, T-01-06) this plan existed to mitigate.
- Human reviewer approved on first review — no revision round needed; the contract is confirmed implementable for both Phase 2 (producer exporter) and Phase 3 (canvas consumer) without follow-up questions.
- `python3 spec/validate.py` still exits 0 (6/6 `[valid]` minimal + 5/5 `[smoke-valid]` against real producer output) — Plan 01-01 deliverables remain intact; this plan did not modify any schema, fixture, or producer code.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write spec/SPEC.md** — `c6f603d` (docs) — 455-line authoritative human-readable ShotTimelineAsset contract.
2. **Task 2: Human review checkpoint** — *no commit (checkpoint approval signal only)* — human reviewer typed "approved" on first review. State/roadmap updates captured in the final metadata commit below.

**Plan metadata:** *(pending — this plan's docs commit capturing SUMMARY.md + STATE.md + ROADMAP.md)*

## Files Created/Modified

- `spec/SPEC.md` — the authoritative prose contract. Covers: authority & schema layout (§1), asset directory layout (§2), manifest field table (§3), schema versioning + graceful degrade (§4), 5 canonical data shapes with field-level type tables + producer attribution + minimal JSON snippets (§5), media references + Range-aware 206 + serve.py reference (§6), validation runner (§7), out-of-scope (§8), references (§9).

## SPEC.md — 10 Sections (per Plan output spec)

| # | Section (as written in SPEC.md) | Phase criterion covered |
|---|----------------------------------|-------------------------|
| 1 | Title + Status (header block: Version / Owner / Consumers / Status + 1-paragraph purpose) | (overview) |
| 2 | §1 Authority & Schema Layout (D-01) — schema-as-authority / SPEC-as-overview, list of 6 schema files | SPEC-04 (manifest authority) |
| 3 | §2 Asset Directory Layout (D-03, D-04) — ASCII tree of canonical asset directory; bass.wav explicit exclusion | SPEC-03, SPEC-04 |
| 4 | §3 The Manifest: asset.json (SPEC-04, D-02, D-04) — full field table (schema_version, asset_type, source, generator, data inventory, media inventory) | SPEC-04 |
| 5 | §4 Schema Versioning & Graceful Degrade (SPEC-02, D-02) — pattern + verbatim rule quote + evolution rules + Changelog | SPEC-02 |
| 6 | §5 The 5 Canonical Data Shapes (SPEC-01) — Shots / Audio Analysis / Transcript / Frames / Prompts subsections, each with field-level type table + producer + JSON snippet + reference schema | SPEC-01 |
| 7 | §6 Media References & Range-aware Serving (SPEC-03, D-03) — path/naming convention + HTTP 206 requirement + serve.py reference impl + Ubuntu quirk note + why-media-is-external | SPEC-03 |
| 8 | §7 Validation — `python3 spec/validate.py` + `--strict-smoke` flag + minimal fixture pointer | (cross-cutting) |
| 9 | §8 Out of Scope (for v1.0) — bullet list mirroring PROJECT.md | (scope hygiene) |
| 10 | §9 References — PROJECT.md / ROADMAP.md / REQUIREMENTS.md / 6 schemas / serve.py / 5 producer scripts | (cross-cutting) |

**Section-count note:** The plan's `<action>` listed 10 numbered items (counting "Title + Status" as item 1). The written document implements Title+Status as an unnumbered header block, then numbers the body sections §1–§9. Content coverage is identical — every required topic is present.

## Graceful-Degrade Rule — Verbatim Wording (per Plan output spec)

The rule appears in SPEC.md §4 as a **direct verbatim quote** from `spec/schemas/asset.schema.json#schema_version.description` (with blockquote attribution to the source):

> Asset contract version, semver-lite (major[.minor]). Examples: "1", "1.1", "2.0". Non-examples: "v1", "1.1.1", "". Consumer MUST graceful-degrade on unknown/newer versions: ignore unknown fields, render known parts, emit a warning — do NOT reject. New field = minor bump; breaking change (rename/semantic shift/removal) = major bump (document migration in SPEC.md).

**Drift check (T-01-05 mitigation):** The wording in SPEC.md §4 matches the wording in `asset.schema.json#schema_version.description` character-for-character. The reviewer's cross-check during the Task 2 checkpoint confirmed this. No drift.

Additionally, SPEC.md §4 expands the rule into a 4-step consumer obligation (ignore unknown fields / render known parts / emit warning / do NOT reject or crash) and explains the "intentional tension" between strict schema (`additionalProperties: false`) and lenient consumer runtime — preserving Plan 01-01's `asset.schema.json` `$comment` intent.

## Human-Review Outcome (per Plan output spec)

**Outcome: APPROVED on first review.**

- Reviewer: the user (plan orchestrator).
- Signal received: "approved" (the resume-signal specified in the plan's Task 2 `<resume-signal>`).
- Issues raised: None.
- Revision rounds: 0.

The reviewer's `<how-to-verify>` checklist (6 items: 5 canonical shapes, version rule, media + Range, self-describing manifest, tribal-knowledge kill check, validate.py exit 0) all passed on first review. SPEC.md is confirmed sufficient for both Phase 2 (producer exporter) and Phase 3 (canvas consumer) implementation without tribal knowledge.

## `python3 spec/validate.py` — Exit 0 Confirmation (per Plan output spec)

Re-verified at plan closeout (after Task 2 approval, before this SUMMARY):

```
[validate] minimal fixture = /data/workspace/kais-shot-timeline/spec/fixtures/minimal
[valid] asset
[valid] shots
[valid] audio_analysis
[valid] transcript
[valid] frames
[valid] prompts
[validate] producer fixture (smoke) = /data/workspace/kais-shot-timeline/output/《小江湖》第03话：白头发的少女（画面只是工具，情绪才是目的
[smoke-valid] shots
[smoke-valid] audio_analysis
[smoke-valid] transcript
[smoke-valid] frames
[smoke-valid] prompts

[validate] minimal failures=0, smoke failures=0 (strict-smoke=off)
[validate] OK
```

Exit code: **0**. Plan 01-01 deliverables intact; Plan 01-02 added a Markdown file only and touched no schema, fixture, or validator code.

## Notes Carried Forward (per Plan output spec)

**To Phase 2 (EXPORT — producer exporter, this repo):**

1. **Only two conformance tasks remain for the producer** (per Plan 01-01 SUMMARY + SPEC.md §7): write the canonical `asset.json` manifest (does not exist in producer output today), and rename media to canonical layout (`stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav` → `stems/{vocals,drums,other}.wav`, drop bass, rename/copy video to `video.mp4`). The 5 data JSON shapes already conform (smoke 5/5 valid).
2. **EXPORT-03 (Range-aware server):** SPEC.md §6.2 names `scripts/serve.py` as the SPEC-03 reference implementation and notes the known Ubuntu/Debian quirk (`python3 -m http.server` does NOT honor Range headers — that's why `scripts/serve.py` exists). The script has known concerns (FD leak on client disconnect, binds `0.0.0.0` unauth) — Phase 2 may need targeted hardening within EXPORT-03 scope.
3. **`generator.version` field is free-form** (SPEC.md §3) — any of semver / git SHA / build id is acceptable. Pick one and stay consistent.
4. **SPEC.md §4 Changelog** is the canonical place to record any future `schema_version` bump with migration notes — Phase 2 should NOT bump version unless it adds/renames fields beyond what `schema_version: "1"` already covers.

**To Phase 3 (CANVAS — consumer, `kais-aigc-platform` branch `feat/canvas-asset-collection`):**

1. **The graceful-degrade rule is binding runtime behavior** (SPEC.md §4, mirrored from `asset.schema.json#schema_version.description`). The consumer MUST: ignore unknown fields, render known parts, emit a warning, and NOT reject/crash on unknown or newer `schema_version`. This is not optional.
2. **TS type generation:** SPEC.md §1 explicitly anticipates downstream TS types generated from the 6 schemas via `json-schema-to-typescript` or equivalent. The 6 `$id` URIs (`https://kais.shot-timeline/spec/schemas/<shape>.schema.json`) are stable identifiers suitable for codegen config.
3. **Media access:** the consumer depends on HTTP Range (Partial Content, 206) for both `video.mp4` and stem `.wav` seek — see SPEC.md §6.2. The consumer does NOT need its own 206 server in v1.0; media is served by the producer's `scripts/serve.py`.
4. **Frames are inline base64** (SPEC.md §5 Frames subsection + §6.3) — the consumer can render thumbnails with no extra HTTP fetches per shot.
5. **bass.wav is NOT in the canonical media set** (SPEC.md §2 + §6.1) — the consumer frontend renders 3 stems (vocals/drums/other); bass is preserved only in the data layer (`audio_analysis.shots[].energies.bass`).

## Decisions Made

- **Two-tier authority with schema-wins clause:** SPEC.md §1 states "when SPEC and schema conflict, schema wins; any SPEC↔schema drift is a Phase-1 defect that must be fixed." This makes the strict schemas the ground truth and SPEC.md the navigable overview, matching CONTEXT D-01.
- **Verbatim schema quoting for normative rules:** rather than paraphrasing the graceful-degrade rule, the dominant_type enum, the backend enum, and the schema_version pattern, SPEC.md quotes them with blockquote attribution. This is the structural mitigation for T-01-05 (Repudiation: SPEC↔schema drift).
- **Bilingual style:** matched the repo's existing convention (spec/README.md, scripts/serve.py docstring, validate.py module docstring are all Chinese-commented). All code identifiers, field names, paths, enum values, and CLI invocations stay in English so they're grep-able.
- **Section numbering §1–§9 with unnumbered header:** slight deviation from the plan's literal 10-section enumeration (which counted Title+Status as item 1). No content gap — see "Section-count note" above.

## Deviations from Plan

None — plan executed exactly as written. Task 1 produced SPEC.md with all 10 required sections, all 6 schema filename references, all canonical media paths (incl. explicit bass.wav exclusion), the verbatim graceful-degrade rule, the serve.py + HTTP 206 reference + Ubuntu quirk note, the `### Changelog` subsection with the initial `1 — initial contract` entry dated 2026-07-20, and a field-level type table for each of the 5 shapes. Task 2 (human-verify checkpoint) was approved on first review with no issues raised, so no revision was needed. No auto-fixes (Rules 1–3), no architectural changes (Rule 4), no deferred items.

## Threat Model Coverage

| Threat ID | Mitigation status |
|-----------|-------------------|
| T-01-05 (Repudiation: SPEC.md ↔ schema field/type drift causing silent interop bugs) | ✅ Task 1 `<verify>` structural grep passed (6 schema filenames + canonical paths + graceful + serve.py + 206); Task 2 human reviewer cross-checked SPEC.md §4 quote against `asset.schema.json#schema_version.description` character-for-character; no drift. |
| T-01-06 (Information Disclosure: SPEC.md omits graceful-degrade rule → consumer rejects unknown versions) | ✅ SPEC.md §4 quotes the rule verbatim AND expands it into a 4-step consumer obligation + intentional-tension explanation. |
| T-01-07 (Tampering: SPEC.md documents non-canonical media path, e.g. bass.wav as canonical) | ✅ SPEC.md §2 and §6.1 explicitly exclude bass.wav from canonical set; reviewer's step-3 check confirmed. |
| T-01-SC (Supply Chain: package installs) | accept (n/a) — zero packages installed; this plan wrote one Markdown file. |

## Self-Check

- `spec/SPEC.md` exists at the specified path (455 lines, > 200 minimum). ✅
- Task 1 commit `c6f603d` exists in git log. ✅
- Task 1 STATE.md/ROADMAP.md update commit `205913b` exists in git log. ✅
- `python3 spec/validate.py` exits 0 (6/6 `[valid]` minimal + 5/5 `[smoke-valid]` real producer output). ✅ Re-verified at closeout.
- No producer code, schema files, fixtures, or validator modified by this plan (only `spec/SPEC.md` created). ✅

## Next Phase Readiness

- **Phase 1 (this phase) is now COMPLETE** — both plans done: 01-01 (6 schemas + fixture + validator) and 01-02 (SPEC.md prose contract). All 4 SPEC-* requirements satisfied.
- **Phase 2 (EXPORT) unblocked** — producer exporter can be planned immediately. The contract is fully specified; Phase 2 only needs to (a) write `asset.json` manifest, (b) rename media to canonical layout, (c) wire into `run_pipeline.py`. The 5 data shapes already conform.
- **Phase 3 (CANVAS) unblocked** — consumer can be planned in parallel with Phase 2 (depends only on Phase 1 spec). Cross-repo coordination note: Phase 3 + 4 live on branch `feat/canvas-asset-collection` in `kais-aigc-platform` (separate GSD project); plan-phase must surface the repo path explicitly.

---
*Phase: 01-shottimelineasset-specification*
*Plan: 02*
*Completed: 2026-07-20*
