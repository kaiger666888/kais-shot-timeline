---
phase: 01-shottimelineasset-specification
verified: 2026-07-20T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 1: ShotTimelineAsset Specification — Verification Report

**Phase Goal (ROADMAP.md):** A repo-agnostic ShotTimelineAsset contract document exists that both producer and consumer can implement against without tribal knowledge.
**Verified:** 2026-07-20
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SPEC-01: 5 canonical JSON shapes defined with field-level types (shots / audio_analysis / transcript / frames / prompts) | VERIFIED | 5 schema files under `spec/schemas/` (plus `asset.schema.json`). Each declares `$schema: draft 2020-12`, has `$id`, title, description, required fields, and `additionalProperties: false` on every object (15 occurrences across 6 files). Field types match real producer output: minimal fixture passes 6/6 `[valid]`, smoke pass 5/5 `[smoke-valid]` against `output/《小江湖》第03话…/`. Enum values exact: `dominant_type ∈ {dialogue,bgm,mixed,sfx}`, `backend ∈ {faster-whisper,openai-whisper}`, stems `["vocals","drums","bass","other"]` (minItems=maxItems=uniqueItems=4). |
| 2 | SPEC-02: schema_version field + graceful-degrade rule on unknown version | VERIFIED | `asset.schema.json#schema_version` has pattern `^(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$`. Behavioral spot-check: accepts `"1"`, `"1.1"`, `"2.0"`; rejects `"v1"`, `"1.1.1"`, `""`, `"01"`. Graceful-degrade rule embedded in TWO places: (a) `schema_version.description` and (b) top-level `$comment`. SPEC.md §4 quotes the rule **verbatim** from the schema — character-for-character identical (programmatically diffed, MATCH). Rule explicitly states consumer obligation: ignore unknown fields, render known parts, emit warning, do NOT reject. |
| 3 | SPEC-03: media file path/naming convention (video.mp4 + stems/{vocals,drums,other}.wav) + Range-aware HTTP 206 requirement | VERIFIED | `asset.schema.json` media patterns: `^(?!.*\.\.)([^/]+/)*video\.mp4$` and `^(?!.*\.\.)([^/]+/)*stems/(vocals\|drums\|other)\.wav$`. Behavioral spot-check: accepts canonical paths, rejects `../video.mp4`, `/abs/video.mp4`, `video.avi`, `Video.mp4`, `stems/bass.wav`, bare `vocals.wav`, `../stems/vocals.wav`. Adding `media.stems.bass` is rejected (`additionalProperties: false`). SPEC.md §6 documents: path/naming convention (§6.1), HTTP 206 Range requirement with Ubuntu/Debian `python3 -m http.server` quirk note (§6.2), why-media-is-external (§6.3). `scripts/serve.py` exists on disk and is cited 6 times in SPEC.md as the reference implementation. |
| 4 | SPEC-04: self-describing manifest (content inventory, source, generator tool/version) | VERIFIED | `asset.schema.json` requires 6 top-level fields: `schema_version`, `asset_type` (const `"shottimeline"`), `source` (`video_filename`, `duration_sec`), `generator` (`tool`, `version`, `generated_at`), `data` (5 JSON relative paths), `media` (`video`, `stems.{vocals,drums,other}`). SPEC.md §3 has a complete field table covering every required field with types and descriptions, ending with "Reference schema: `spec/schemas/asset.schema.json`". Minimal fixture `spec/fixtures/minimal/asset.json` exercises every required field and validates cleanly. |

**Score:** 4/4 truths verified.

### Phase Goal: Repo-Agnostic, Implementable Without Tribal Knowledge

| Aspect | Status | Evidence |
|--------|--------|----------|
| Contract is machine-checkable | VERIFIED | 6 JSON Schema (draft 2020-12) files; `python3 spec/validate.py` runs in <1s, exits 0 with 6/6 minimal + 5/5 smoke-valid against real producer output. Both default and `--strict-smoke` modes pass. |
| Contract is human-navigable | VERIFIED | `spec/SPEC.md` is 455 lines (well over the 200 minimum), structured into 9 numbered sections plus header block, references each of the 6 schema files by filename (3–8 occurrences each), includes field-level type tables for all 5 data shapes, and embeds the verbatim graceful-degrade quote. |
| No drift between prose and schema | VERIFIED | Programmatic diff of `asset.schema.json#schema_version.description` vs SPEC.md §4 blockquote: character-for-character identical (MATCH). Enum values in SPEC.md §5 (dominant_type, backend) match schema enums exactly. Canonical path patterns cited in SPEC.md §6.1 match schema regexes. |
| Producer-side implementable (Phase 2) | VERIFIED | Smoke validation confirms the producer's existing 5 data JSON shapes (`output/《小江湖》第03话…/`) already conform to the strict schemas 5/5. Phase 2 only needs to write the canonical `asset.json` manifest and rename media to canonical layout — the data shapes themselves are already contract-conformant. |
| Consumer-side implementable (Phase 3) | VERIFIED | Graceful-degrade rule is binding runtime behavior documented in two layers (schema description + SPEC.md §4 with 4-step consumer obligation). 6 `$id` URIs are stable identifiers suitable for TS codegen via `json-schema-to-typescript`. SPEC.md §1 explicitly anticipates downstream TS type generation. |
| Tribal-knowledge kill check | VERIFIED | 5 of 6 cited producer scripts exist on the spec branch with the cited functions (`detectors/detect_v3b.py:main`, `audio/separate_stems.py:analyze_shots`, `audio/separate_stems.py:classify_shot`, `audio/transcribe.py:main`, `html/gen_timeline_html.py:extract_frames_if_needed`). The 6th (`html/gen_prompts_html.py`) exists on `main` branch but not on the spec branch — see INFO note below. The `prompts.json` data shape itself is real and smoke-validates, so the contract is grounded in actual emitter output. Plan 01-02 Task 2 (`checkpoint:human-verify`) recorded an "approved" resume-signal per the plan's `<resume-signal>` specification, confirming a human reviewer judged the contract sufficient for both producer and consumer implementation. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `spec/schemas/shots.schema.json` | draft 2020-12, strict array schema for shot boundaries | VERIFIED | 36 lines, contains `"draft": "2020-12"`, `additionalProperties: false` on item schema, `id≥1` (integer minimum), `duration` with `exclusiveMinimum: 0`. |
| `spec/schemas/audio_analysis.schema.json` | strict schema with `dominant_type` enum | VERIFIED | 109 lines, `dominant_type` enum exactly `["dialogue","bgm","mixed","sfx"]`, stems array constrained (`minItems=4 maxItems=4 uniqueItems=true`), `energies`/`ratios`/`spectral_centroid` DRY-refactored into `$defs/stem_float_map`, 4 `additionalProperties: false` occurrences. |
| `spec/schemas/transcript.schema.json` | strict schema with `segments` and `backend` enum | VERIFIED | 62 lines, `backend` enum exactly `["faster-whisper","openai-whisper"]`, segment items strict, 2 `additionalProperties: false` occurrences. |
| `spec/schemas/frames.schema.json` | strict schema with `first_frame`/`last_frame` data URI pattern | VERIFIED | 30 lines, `^data:image/jpeg;base64,` pattern on both fields, items strict. |
| `spec/schemas/prompts.schema.json` | strict schema with `prompt_text` and 7 facets | VERIFIED | 72 lines, all 10 required fields (`shot_id`, `start_sec`, `end_sec`, `duration`, `subject`, `action`, `camera`, `scene`, `lighting`, `style`, `prompt_text`), items strict. Description honestly hedges producer as "(planned)". |
| `spec/schemas/asset.schema.json` | strict manifest schema with `schema_version` + canonical media patterns + graceful-degrade rule | VERIFIED | 128 lines, 6 `additionalProperties: false` occurrences (root + source + generator + data + media + stems), schema_version pattern works correctly (spot-checked), graceful-degrade rule embedded in BOTH `schema_version.description` AND top-level `$comment`, media path patterns reject traversal/absolute/bass/non-canonical. |
| `spec/fixtures/minimal/{asset,shots,audio_analysis,transcript,frames,prompts}.json` | complete minimal example asset exercising every required field | VERIFIED | 6 JSON files exist. `asset.json` manifest references all 5 data files + canonical media (`video.mp4` + `stems/{vocals,drums,other}.wav`). `shots.json` is a 2-shot contiguous list spanning 0.0–3.0s. All 6 validate cleanly. |
| `spec/validate.py` | jsonschema Draft202012Validator runner with `main()` + smoke pass + `--strict-smoke` flag | VERIFIED | 185 lines, imports only stdlib + `jsonschema` (4.26.0 system-installed), exposes `main()` and `__name__ == "__main__"` guard, `--strict-smoke` CLI flag implemented, smoke auto-discovers first `output/` subdir containing `shots.json`, informational vs strict modes both work. Exits 0 on conforming input, exits 1 on failure. |
| `spec/SPEC.md` | authoritative human-readable contract document, ≥200 lines, references all 6 schemas, covers all 4 phase success criteria | VERIFIED | 455 lines, 9 numbered sections + header block, references each schema 3–8 times, includes field-level type tables for all 5 shapes with enum values quoted verbatim, embeds graceful-degrade rule as verbatim blockquote matching schema, includes `### Changelog` subsection with initial "1 — initial contract" entry dated 2026-07-20, cites `scripts/serve.py` as Range 206 reference implementation 6 times. |
| `spec/README.md` | one-page index of spec/ directory with how-to-validate + canonical layout + Range 206 reference | VERIFIED | 68 lines, layout tree, both validation invocations documented, canonical media layout one-liner, Range 206 one-liner referencing `scripts/serve.py`, graceful-degrade rule summary. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `spec/schemas/asset.schema.json` | `spec/fixtures/minimal/asset.json` | jsonschema Draft202012Validator validation | WIRED | `validate_minimal()` loads asset.schema.json, builds `Draft202012Validator`, iterates errors against `asset.json` fixture → `[valid] asset` on execution. |
| `spec/validate.py` | `spec/schemas/*.schema.json` | file path lookup + jsonschema validation per shape | WIRED | `load_validator(shape)` opens `SCHEMAS_DIR / f"{shape}.schema.json"` and constructs validator; loop iterates over `MINIMAL_ORDER = ["asset","shots","audio_analysis","transcript","frames","prompts"]`. |
| `spec/validate.py` | `output/《小江湖》第03话…/*.json` | real-fixture smoke validation pass | WIRED | `discover_producer_fixture()` scans `REPO_ROOT/output/` for first subdir containing `shots.json`, `validate_smoke(producer_dir)` iterates 5 data shapes, prints `[smoke-valid]` × 5 on execution. |
| `spec/SPEC.md` | `spec/schemas/asset.schema.json` | filename reference in manifest section (§3) | WIRED | "Reference schema: `spec/schemas/asset.schema.json`" appears at end of §3; `asset.schema.json` cited 8 times total in SPEC.md. |
| `spec/SPEC.md` | `spec/schemas/{shots,audio_analysis,transcript,frames,prompts}.schema.json` | filename references in data-shapes section (§5) | WIRED | Each §5 subsection ends with "Reference schema: `spec/schemas/<shape>.schema.json`"; each schema filename cited 3–4 times. |
| `spec/SPEC.md` | `scripts/serve.py` | Range-aware HTTP 206 server reference (§6.2) | WIRED | §6.2 names `scripts/serve.py` as "(SPEC-03 的 reference server)", includes invocation example `python3 scripts/serve.py <asset-root> 8765`, and explains the Ubuntu/Debian `python3 -m http.server` Range-header quirk. File exists on disk at `scripts/serve.py`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `spec/validate.py` | `instance` (loaded JSON) | `spec/fixtures/minimal/*.json` (real hand-built fixture) + `output/《小江湖》第03话…/*.json` (real producer output) | Yes — both produce real JSON conforming to schemas | FLOWING |
| `spec/fixtures/minimal/asset.json` | `data.*` / `media.*` field values | Hard-coded canonical relative paths (`shots.json`, `stems/vocals.wav` etc.) | Yes — paths point to real sibling files in the same fixture directory | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Validator passes default mode | `python3 spec/validate.py` | Exits 0; prints 6 `[valid]` + 5 `[smoke-valid]` + `[validate] OK` | PASS |
| Validator passes strict-smoke mode | `python3 spec/validate.py --strict-smoke` | Exits 0; same output; strict-smoke=on | PASS |
| schema_version pattern accepts valid | `python3` spot-check via Draft202012Validator | `"1"`, `"1.1"`, `"2.0"` all accepted | PASS |
| schema_version pattern rejects invalid | same | `"v1"`, `"1.1.1"`, `""`, `"01"` all rejected | PASS |
| Media path traversal rejected | same | `../video.mp4`, `/abs/video.mp4` rejected | PASS |
| bass.wav excluded from canonical stems | same | `stems/bass.wav` in vocals slot rejected; adding `media.stems.bass` rejected as additional property | PASS |
| Non-canonical video rejected | same | `video.avi`, `Video.mp4` rejected | PASS |
| Unknown top-level field rejected | same | `{...,"foo":"bar"}` rejected (additionalProperties false) | PASS |
| Graceful-degrade rule drift between schema and SPEC.md | programmatic string diff | Character-for-character identical (MATCH) | PASS |
| Schema strictness (`additionalProperties: false`) | grep across 6 files | 15 occurrences total across all object schemas | PASS |
| Schema $id / draft sanity | json load + field check | All 6 have correct `$id` URI + `"draft": "2020-12"` | PASS |

### Probe Execution

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| `spec/validate.py` (the phase's canonical probe) | `python3 spec/validate.py` | exit 0, 6/6 valid + 5/5 smoke-valid | PASS |
| `spec/validate.py --strict-smoke` | `python3 spec/validate.py --strict-smoke` | exit 0 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SPEC-01 | 01-01, 01-02 | 5 canonical JSON shapes with field-level types | SATISFIED | 5 schema files (shots/audio_analysis/transcript/frames/prompts) with strict field-level types + enums. Smoke validates against real producer output 5/5. SPEC.md §5 documents each shape with field tables. |
| SPEC-02 | 01-01, 01-02 | schema_version field + graceful-degrade rule on unknown version | SATISFIED | `asset.schema.json#schema_version` with semver-lite pattern + graceful-degrade rule embedded in `description` AND top-level `$comment`. SPEC.md §4 quotes rule verbatim. Behavioral spot-check confirms pattern accepts/rejects correctly. |
| SPEC-03 | 01-01, 01-02 | media file path/naming (video.mp4 + 3 stems) + Range-aware HTTP 206 | SATISFIED | `asset.schema.json` media patterns enforce canonical naming, reject traversal/bass/non-canonical. SPEC.md §6 documents paths + HTTP 206 requirement + Ubuntu quirk + `scripts/serve.py` reference implementation (file exists). |
| SPEC-04 | 01-01, 01-02 | self-describing manifest (content inventory, source, generator tool/version) | SATISFIED | `asset.schema.json` requires `schema_version` + `asset_type` + `source` + `generator` + `data` (5 files) + `media` (video + 3 stems). SPEC.md §3 has full field table. Minimal fixture exercises every field. |

**Orphaned requirements:** None. REQUIREMENTS.md Traceability table maps SPEC-01..04 to Phase 1; all 4 are claimed by plans 01-01 and 01-02 (`requirements: [SPEC-01, SPEC-02, SPEC-03, SPEC-04]` in both PLAN frontmatters) and all 4 are SATISFIED. REQUIREMENTS.md checkboxes all marked `[x]` for SPEC-* with "Complete (Plan 01-01)" status.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | No `TBD`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` markers, no `return null`/`return {}`/`return []`/`=> {}` stubs, no "coming soon"/"not yet implemented" strings in any of the 15 spec files (6 schemas + 6 fixtures + SPEC.md + README.md + validate.py). |

### INFO Notes (Non-Blocking)

**Cross-branch producer file reference (INFO, not a gap):**

SPEC.md §5 (Prompts) and §9 (References) cite `html/gen_prompts_html.py` as the producer for `prompts.json`. This file exists on the `main` and `feat/canvas-asset-collection` branches (commit `4e60b3d` — "feat: 分镜 prompt 反推") but is NOT present on the current spec branch `feat/video-reverse-dataset`. The cited function-level claims in SPEC.md cannot be grep-verified on this branch.

This is **not a contract gap** because:
1. The `prompts.json` data shape itself is real — `output/《小江湖》第03话…/prompts.json` exists and smoke-validates 5/5 against `prompts.schema.json`. The contract is grounded in actual emitter output, not aspirational shape.
2. `prompts.schema.json#description` honestly hedges with the word "(planned)" — Producer: `html/gen_prompts_html.py (planned); current producer shape observed in output/...`. The schema-level claim is accurate.
3. SPEC.md §5's wording "(已建立" (established) is slightly stronger than the schema's "(planned)" hedge — a minor prose precision issue, but it does not undermine contract clarity for either producer (Phase 2) or consumer (Phase 3) implementers. The 7-facet + `prompt_text` shape is fully specified at the schema level.
4. Phase 2 will produce the canonical exporter regardless of the current branch topology — the producer script's current branch residence is a workflow orchestration concern, not a Phase 1 deliverable quality concern.
5. The contract is repo-agnostic per the phase goal — it does not depend on any specific producer script path existing in any specific branch. The script citation is for traceability, not contract completeness.

Suggested follow-up (optional, INFO only): when Phase 2 lands or when `feat/video-reverse-dataset` merges with `main`, soften SPEC.md §5's "(已建立" to "(planned, see schema description)" to match the schema's hedge wording. This is a documentation polish item, not a verification blocker.

### Human Verification Required

None.

The original plan 01-02 Task 2 was a `checkpoint:human-verify` task with `<resume-signal>Type "approved"...</resume-signal>`. The Plan 01-02 SUMMARY records that approval signal was received ("approved" on first review). This is the documented human-verification gate for the phase goal's "tribal-knowledge kill check" — the gate was satisfied as part of workflow execution.

All four phase success criteria are independently verifiable through automated means (schemas + validator + grep checks + behavioral spot-checks), all pass, and the cross-references between prose and schemas are programmatically confirmed non-drifting. No additional human verification is required beyond the documented checkpoint already in the workflow record.

### Gaps Summary

No gaps found. All four SPEC-* requirements are SATISFIED with strong automated evidence:
- 6 strict JSON Schema (draft 2020-12) files define the contract machine-checkably.
- Minimal fixture passes 6/6, real producer output passes 5/5 smoke.
- Graceful-degrade rule embedded in two layers of `asset.schema.json` and quoted verbatim in SPEC.md (no drift).
- Canonical media layout enforced via regex patterns (traversal-resistant, bass-excluded).
- Self-describing manifest carries source/generator/data inventory/media inventory per SPEC-04.
- 455-line bilingual SPEC.md navigates the contract end-to-end with field-level type tables for all 5 data shapes.
- Range-aware HTTP 206 requirement documented with `scripts/serve.py` reference implementation (file exists).

The phase goal — a repo-agnostic ShotTimelineAsset contract document that both producer (Phase 2) and consumer (Phase 3) can implement against without tribal knowledge — is achieved. The contract is implementable: the producer's existing 5 data shapes already conform (smoke 5/5), leaving Phase 2 only to write the canonical `asset.json` manifest and rename media; the consumer has 6 stable `$id` URIs for TS codegen and a binding graceful-degrade runtime rule.

---

_Verified: 2026-07-20_
_Verifier: Claude (gsd-verifier)_
