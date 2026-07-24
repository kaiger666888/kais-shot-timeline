# Phase 5: Contract v1.1 - Context

**Gathered:** 2026-07-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Lock the v1.1 ShotTimelineAsset contract (3 new schemas: `characters.schema.json` / `props.schema.json` / `registry.schema.json`; additive extension of `prompts.schema.json` + `asset.schema.json`; `SPEC.md` §4 Changelog `1.1` entry + new §5.6/§5.7; new `spec/fixtures/v1.1/` fixture set; `verify_contract.py` `SIX_SHAPES`→`EIGHT_SHAPES` + schema-layer cross-version self-test; `export_asset.py` `SCHEMA_VERSION` single-source constant) BEFORE any producer code (Phase 6+) writes against it. All downstream field names, ID patterns, and the `schema_version: "1.1"` literal are frozen by this phase. No route dependency — mirrors v1.0 Phase 1 contract-first pattern.

**In scope:** schemas + SPEC prose + fixtures + verify harness extension + producer version constant.
**Out of scope:** any producer code that *calls* a route or *writes* registry data (Phase 6/7/8); consumer-side v1.1 node emission (Phase 9); DINOv2 τ calibration (Phase 7 research spike).

</domain>

<decisions>
## Implementation Decisions

### schema_version 锁定策略 (resolves success-criteria #4 vs CONTRACT-09 tension)
- Keep `schema_version` as the **pattern** in `asset.schema.json` (`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` — accepts `"1"`, `"1.1"`, `"2.0"`). Do NOT hardcode a JSON-Schema `const:"1.1"` (that would reject the v1 minimal fixture's `"1"` and break CONTRACT-09 + Pitfall 11).
- Lock the *value* at the **producer** layer: `scripts/export_asset.py` introduces `SCHEMA_VERSION = "1.1"` module-level single-source constant; the literal `"schema_version": "1"` at `export_asset.py:160` is replaced by the constant.
- The v1 minimal fixture (`spec/fixtures/minimal/asset.json`) keeps `schema_version: "1"` and MUST stay green — this is the backward-compat proof.
- A NEW `spec/fixtures/v1.1/asset.json` carries `schema_version: "1.1"` + the new `characters`/`props` data+media refs.

### characters / props schema 丰富度
- `characters.schema.json`: immutable ID (pattern `^char_[0-9]{3}$`) + `name` + `representative_image` (external png ref) + `appearance_shots:[int]` + `review_state` + `looks:[{label:str, image_ref:str, appearance_shots:[int]}]` (costume/造型 variants carry their own shot list).
- `props.schema.json`: **same core shape** but the variant field is `states[]` (not `looks[]`) — props vary by state (open/closed, intact/broken) not costume. ID pattern `^prop_[0-9]{3}$`.
- All new fields OPTIONAL (never in `required`); `additionalProperties: false` preserved (strict-schema × lenient-consumer tension from v1.0 holds).

### registry.schema.json cluster 细节
- `clusters[]` members store **refs only**: `{shot_id:int, frame_pos:str|number, mask_quality:str}` — no 768-d DINOv2 embeddings inlined (bloat prevention).
- Each cluster carries `review_state: "proposed"|"confirmed"|"rejected"` + `tier: "auto_merge"|"review"|"auto_distinct"` enum + `mean_cosine: float`.
- Three-tier threshold constants (auto-merge ≥0.85 / review 0.6–0.85 / auto-distinct <0.6) documented in the schema `$comment`/`description`, NOT as numeric schema fields (default τ calibrated in Phase 7, not locked here).

### v1.1 fixture + 跨版本自检机制
- New `spec/fixtures/v1.1/` directory: reuse minimal's 2 shots; add 2 characters (`char_001` 少女 / `char_002` 路人) + 1 prop (`prop_001` 落叶) + `registry.draft.json` (3 clusters, one per tier) + `prompts.json` carrying `character_refs[]`/`prop_refs[]`. Self-contained synthetic sample (not sliced ep01).
- Cross-version self-test realized at the **schema layer** in `verify_contract.py`: new `_cross_version_check()` — (a) v1 fixture passes v1.1 schema (additive optional fields don't break), (b) v1.1 fixture passes a permissive check proving extra fields are ignored-not-crashed. The genuine consumer-side warn-not-crash behavior is verified for real in Phase 9 (TS consumer) — Phase 5 does not stub a fake Python consumer.

### Claude's Discretion
- Exact prose wording of SPEC.md §5.6/§5.7 + §4 Changelog `1.1` entry.
- Internal helper organization within `verify_contract.py` (where `_cross_version_check` slots, how `EIGHT_SHAPES` is threaded through `run_producer_check`).
- Whether `spec/README.md` layout block + `SPEC.md` §1 schema-file index get a parallel update (they should, for consistency).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `spec/validate.py` — existing Draft202012Validator harness with `SHAPE_TO_FIXTURE` / `MINIMAL_ORDER` / `SMOKE_SHAPES` maps; `load_validator(shape)` helper. Phase 5 extends the shape maps (adds characters/props/registry) rather than rewriting.
- `scripts/verify_contract.py` — `SIX_SHAPES` constant (line 75), `run_producer_check` / `run_consumer_check` / `run_self_test` (injects `schema_version='v1'` to prove fail-loud, line 369-381). Phase 5 renames to `EIGHT_SHAPES` + adds `_cross_version_check`.
- `scripts/export_asset.py:160` — the `"schema_version": "1"` literal to replace with the `SCHEMA_VERSION` constant; `_git_sha()` helper (line 61) is the model for a module-level constant.
- `spec/schemas/asset.schema.json` + `prompts.schema.json` — the two schemas to extend additively (both already `additionalProperties:false` with strict `required` lists — new fields go in `properties`, never in `required`).

### Established Patterns
- **Strict schema × lenient consumer** tension: `additionalProperties:false` everywhere; graceful-degrade is a runtime consumer responsibility documented in `$comment` + `schema_version.description`. New v1.1 fields are optional → old consumers ignore them.
- **Schema-file index parity**: `SPEC.md` §1 lists all schema files by filename; `spec/README.md` layout block mirrors it. Adding 3 schemas → both indexes updated.
- **Fixture = self-contained tiny sample**: `spec/fixtures/minimal/` is a 2-shot synthetic asset, not real ep01. v1.1 fixture follows the same philosophy.
- **Path patterns reject traversal**: asset.schema.json uses `^(?!.*\.\.)...` patterns for data/media paths; characters/props png refs must follow the same anti-traversal pattern.

### Integration Points
- `export_asset.py` emits `asset.json` — Phase 5 adds the `SCHEMA_VERSION` constant + (optionally, scaffolded) conditional characters/props emit (full conditional emit logic lands in Phase 7/8; Phase 5 only locks the version constant + schema shape).
- `verify_contract.py` is the cross-version harness — Phase 5's `_cross_version_check` becomes the regression guard for all later phases.
- `spec/fixtures/v1.1/` is consumed by `validate.py` (minimal-equivalent green check) + `verify_contract.py` (cross-version).

</code_context>

<specifics>
## Specific Ideas

- `looks[]` MUST carry per-look `appearance_shots[]` (not just label+image) — accepted in Grey Area 2. This is what lets Phase 8 attach prompt refs per-look, not just per-character.
- Props use `states[]` not `looks[]` — semantic precision over schema uniformity.
- The `schema_version` "lock" is producer-side (`SCHEMA_VERSION` constant), NOT a schema `const` — this is the deliberate resolution of the success-criteria #4 wording (which said "const" loosely) against CONTRACT-09.
- Cross-version self-test is schema-layer only in Phase 5; do NOT build a fake lenient Python consumer — that would mock behavior the real TS consumer must own in Phase 9.

</specifics>

<deferred>
## Deferred Ideas

- Default DINOv2 cosine threshold τ value — Phase 7 research spike calibrates on ep01 (same-person vs different-person cosine histogram, valley pick); Phase 5 only locks the *schema shape* (`tier` enum + `mean_cosine` float), threshold constants documented but not empirically validated.
- `export_asset.py` conditional characters/props emit logic (only-when-files-exist) — scaffolded/locked in Phase 5 schema, full producer emit wired in Phase 7/8.
- Consumer-side (canvas) v1.1 warn-not-crash verification — Phase 9 against real TS consumer.
- `prompts.schema.json#scene` source mapping (route has no scene output today) — Phase 6 decides leave-empty vs future Qwen-VL extension; Phase 5 only ensures `scene` stays a valid optional string.

</deferred>
