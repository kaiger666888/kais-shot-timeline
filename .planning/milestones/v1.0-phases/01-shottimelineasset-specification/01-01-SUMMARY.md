---
phase: 01-shottimelineasset-specification
plan: 01
subsystem: spec
tags: [schema, contract, jsonschema, validation]
requires: []
provides:
  - "6 JSON Schema (draft 2020-12) contract files for ShotTimelineAsset (shots/audio_analysis/transcript/frames/prompts/asset)"
  - "Minimal complete fixture (spec/fixtures/minimal/) proving schema coherence"
  - "jsonschema validation runner (spec/validate.py) with smoke mode against real producer output"
affects:
  - "Phase 2 (EXPORT): exporter MUST emit JSON conforming to these 6 schemas; canonical media layout enforced"
  - "Phase 3 (CANVAS): @kais/infinite-canvas consumer derives TS types from these schemas and follows graceful-degrade rule"
tech-stack:
  added:
    - "jsonschema Draft202012Validator (4.26.0, system-installed — no pip install)"
  patterns:
    - "Strict schemas + lenient consumer (additionalProperties:false everywhere; consumer ignores unknown fields at runtime)"
    - "Path-traversal-safe relative path patterns (negative lookahead (?!.*\\.\\.) on every media/data path)"
key-files:
  created:
    - "spec/schemas/shots.schema.json"
    - "spec/schemas/audio_analysis.schema.json"
    - "spec/schemas/transcript.schema.json"
    - "spec/schemas/frames.schema.json"
    - "spec/schemas/prompts.schema.json"
    - "spec/schemas/asset.schema.json"
    - "spec/fixtures/minimal/{asset,shots,audio_analysis,transcript,frames,prompts}.json"
    - "spec/validate.py"
    - "spec/README.md"
  modified: []
decisions:
  - "Schema Version pattern: ^(0|[1-9]\\d*)(\\.(0|[1-9]\\d*))?$ — semver-lite (\"1\" / \"1.1\"), rejects v1, 1.1.1, empty"
  - "Canonical media layout enforced via regex patterns: video.mp4 + stems/{vocals,drums,other}.wav (bass excluded — consumer frontend only renders 3 stems)"
  - "asset schema additionalProperties:false (strict schema is the contract; graceful-degrade is a runtime consumer behavior, not schema-loosening)"
  - "audio_analysis.shots[].energies/ratios/spectral_centroid factored into $defs/stem_float_map (DRY across 3 identical-shape fields)"
metrics:
  duration: ~25min
  completed: 2026-07-20
  tasks: 2
  files_created: 15
---

# Phase 01 Plan 01: ShotTimelineAsset Schema Contract Summary

**One-liner:** 6 strict JSON Schema (draft 2020-12) files for the ShotTimelineAsset contract — 5 canonical data shapes (shots / audio_analysis / transcript / frames / prompts) + a self-describing asset.json manifest — plus a minimal fixture and a `jsonschema`-based validator that passes 6/6 on the minimal fixture AND 5/5 smoke-valid on the producer's real `output/《小江湖》第03话…/` data.

## What Was Built

### Schema files (`spec/schemas/*.schema.json`)

| File | $id | Top-level | Producer | Key constraints |
|------|-----|-----------|----------|-----------------|
| `shots.schema.json` | `https://kais.shot-timeline/spec/schemas/shots.schema.json` | array | `detectors/detect_v3b.py:main` | id≥1, start_sec≥0, duration>0, contiguous |
| `audio_analysis.schema.json` | `https://kais.shot-timeline/spec/schemas/audio_analysis.schema.json` | object | `audio/separate_stems.py:analyze_shots` | stems=[vocals,drums,bass,other] (4 unique); dominant_type ∈ {dialogue,bgm,mixed,sfx}; type_distribution all 4 counts |
| `transcript.schema.json` | `https://kais.shot-timeline/spec/schemas/transcript.schema.json` | object | `audio/transcribe.py:main` | backend ∈ {faster-whisper,openai-whisper}; segment={start,end,text} |
| `frames.schema.json` | `https://kais.shot-timeline/spec/schemas/frames.schema.json` | array | `html/gen_timeline_html.py:extract_frames_if_needed` | first/last_frame pattern `^data:image/jpeg;base64,` |
| `prompts.schema.json` | `https://kais.shot-timeline/spec/schemas/prompts.schema.json` | array | `html/gen_prompts_html.py` | 7 string facets + prompt_text, shot_id≥1 |
| `asset.schema.json` | `https://kais.shot-timeline/spec/schemas/asset.schema.json` | object | Phase 2 exporter (TBD) | schema_version semver-lite; canonical media patterns reject path traversal |

Every object schema (root + nested) sets `additionalProperties: false`. Enum values exactly match the real producer output.

### Canonical media layout enforced by `asset.schema.json` (CONTEXT D-03)

- Video: `^(?!.*\.\.)([^/]+/)*video\.mp4$` — accepts `video.mp4` / `subdir/video.mp4`; rejects `../video.mp4`, `/abs/video.mp4`, `video.avi`, `Video.mp4`
- Stems: `^(?!.*\.\.)([^/]+/)*stems/(vocals|drums|other)\.wav$` — accepts `stems/vocals.wav`; rejects `stems/bass.wav` (bass excluded), bare `vocals.wav` (must be under `stems/`), `../stems/vocals.wav`
- Data paths: `^(?!.*\.\.)[^:*?"<>|]+\.json$` — no parent traversal, no Windows reserved chars, must end in `.json`

The producer's pre-canonical layout (`stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav`) is intentionally NOT accepted — Phase 2 exporter renames to canonical before writing asset.json.

### Graceful-degrade rule (SPEC-02 / CONTEXT D-02)

The rule is embedded in TWO places in `asset.schema.json` so it cannot be missed:

1. **`schema_version.description`** (consumer reads the schema):
   > Asset contract version, semver-lite (major[.minor]). Examples: "1", "1.1", "2.0". Non-examples: "v1", "1.1.1", "". Consumer MUST graceful-degrade on unknown/newer versions: ignore unknown fields, render known parts, emit a warning — do NOT reject. New field = minor bump; breaking change (rename/semantic shift/removal) = major bump (document migration in SPEC.md).

2. **Top-level `$comment`** (schema author intent / spec context):
   > The schema is intentionally strict (additionalProperties: false on every object). Strictness at validation time is what forces explicit version bumps. The CONSUMER, however, must be lenient at RUNTIME: on an unknown or newer schema_version, ignore unknown fields, render the known parts, and emit a warning — do NOT reject or crash. [...] Semver-lite: major[.minor], e.g. "1" or "1.1" — NOT full semver.

`schema_version` pattern: `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`
- Accepts: `1`, `1.1`, `2.0`, `0`, `10`, `1.0`
- Rejects: `v1`, `1.1.1`, `` (empty), `01` (leading zero), `1.`, `.1`

### Minimal fixture (`spec/fixtures/minimal/`)

A complete 2-shot ShotTimelineAsset exercising every required field: ids 1+2 spanning 0.0–3.0s, dialogue+bgm dominant types, faster-whisper backend, two JPEG data URIs, structured Chinese prompts, asset.json manifest referencing all 5 data files + canonical media (`video.mp4` + `stems/{vocals,drums,other}.wav`).

### Validator (`spec/validate.py`)

- **Minimal mode**: validates all 6 shapes against `spec/fixtures/minimal/`. Exits 0 only if 6/6 `[valid]`.
- **Smoke mode**: auto-discovers first subdir under `output/` containing `shots.json`, validates 5 data shapes against the real producer output. Prints `[smoke-valid]` / `[smoke-FAIL]`. Default: informational (does not affect exit code). With `--strict-smoke`: counts toward exit code (CI / Phase 2 regression).
- Imports only stdlib + `jsonschema` (4.26.0 system-installed — verified, no pip install).
- Module docstring in Chinese; `main()` + `if __name__ == "__main__":` guard per CONVENTIONS.md; `[validate]` log prefix.

### Spec README (`spec/README.md`)

One-page index: layout tree, how-to-validate (default + `--strict-smoke`), canonical media layout (CONTEXT D-03), Range-aware HTTP 206 reference to `scripts/serve.py` (SPEC-03), graceful-degrade rule summary (CONTEXT D-02), and a clear marker that `SPEC.md` (prose spec) is pending Plan 02.

## Smoke result against real producer output

Producer fixture auto-discovered: `output/《小江湖》第03话：白头发的少女（画面只是工具，情绪才是目的/`

```
[smoke-valid] shots
[smoke-valid] audio_analysis
[smoke-valid] transcript
[smoke-valid] frames
[smoke-valid] prompts

[validate] minimal failures=0, smoke failures=0 (strict-smoke=off)
[validate] OK
```

**5/5 smoke-valid — the producer's existing 5 data JSON shapes already conform to the strict schemas.** No `[smoke-FAIL]` lines, so there is **no Phase-2 cleanup work** required for the 5 data shapes. Phase 2's only conformance work is:

1. Writing the canonical `asset.json` manifest (does not exist in producer output today — producer emits 5 flat JSONs with no manifest).
2. Renaming media to canonical layout (`stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav` → `stems/{vocals,drums,other}.wav`; bass dropped; video renamed/copy to `video.mp4`).

This is a stronger outcome than the plan anticipated (the plan said "smoke failures are acceptable Phase-2 feedback").

## How to run

```bash
# Default — minimal 6/6 must pass; smoke is informational
python3 spec/validate.py

# Strict — smoke failures also count toward exit code (CI / Phase 2 regression)
python3 spec/validate.py --strict-smoke
```

Both currently exit 0.

## Decisions Made

- **Strict schema + lenient consumer (intentional tension)**: The schema sets `additionalProperties: false` everywhere (forces explicit version bumps at producer-validation time). The graceful-degrade rule is a runtime behavior the consumer MUST follow (ignore unknown fields + warn, do not reject). The schema is the strict contract surface; the consumer is the lenient runtime. This tension is documented in `asset.schema.json`'s top-level `$comment`.
- **`schema_version` is single-field at manifest level (not per-file)**: one `schema_version` on `asset.json` covers the entire asset. CONTEXT D-02 decision, implemented as required top-level field.
- **Stem map factored into `$defs`** in audio_analysis.schema.json: `energies` / `ratios` / `spectral_centroid` all have identical shape `{vocals,drums,bass,other}` of floats — refactored to `$defs/stem_float_map` for DRY.
- **Stems array uses enum + minItems/maxItems/uniqueItems**: producer's `["vocals","drums","bass","other"]` order is producer-determined but all 4 must be present exactly once. Did not enforce order via `prefixItems` — current plan did not require it.
- **`media.stems` patterns reject `bass.wav`** intentionally (bass excluded from canonical — consumer frontend only renders 3 stems). Producer's 4-stem set is preserved in `audio_analysis.stems` (data layer) but the **media inventory** is 3-stem.

## Deviations from Plan

None — plan executed exactly as written. Every must_have truth, every acceptance criterion, every verification point passed on first execution. No auto-fixes (Rules 1–3), no architectural changes (Rule 4), no deferred items.

## Threat Model Coverage

| Threat ID | Mitigation status |
|-----------|-------------------|
| T-01-01 (Tampering: field-shape drift) | ✅ 6 strict schemas + jsonschema validation runner (Draft202012Validator) |
| T-01-02 (Info Disclosure / DoS: consumer crashes on unknown version) | ✅ graceful-degrade rule embedded in `asset.schema.json` `schema_version.description` + `$comment` |
| T-01-03 (Tampering: media path traversal) | ✅ All `media` / `data` path patterns use negative lookahead `(?!.*\.\.)` + reject Windows reserved chars + absolute paths |
| T-01-04 (Spoofing: generator identity claimed) | accept — documented field, no signature scheme in v1.0 |
| T-01-SC (Supply Chain: package installs) | accept (n/a) — ZERO packages installed; `jsonschema` already system-wide |

## Self-Check

- All 6 schema files + 6 fixture files + validate.py + README exist at the specified paths. ✅
- Both commits exist: `807d1f7` (Task 1, 6 schemas), `b5dc555` (Task 2, fixtures + validator + README). ✅
- `python3 spec/validate.py` exits 0 with 6 `[valid]` lines + 5 `[smoke-valid]` lines. ✅
- `python3 spec/validate.py --strict-smoke` also exits 0. ✅
