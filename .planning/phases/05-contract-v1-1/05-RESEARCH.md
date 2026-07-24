# Phase 5: Contract v1.1 - Research

**Researched:** 2026-07-24
**Domain:** JSON Schema (draft 2020-12) contract authoring + cross-version validation harness design
**Confidence:** HIGH

## Summary

Phase 5 is a **pure contract-first** phase that locks the v1.1 ShotTimelineAsset extension BEFORE any producer code (Phase 6+) writes against it. The work is almost entirely schema authoring + fixture creation + verify-harness extension — no new runtime dependencies, no new packages, no ML, no network. Every load-bearing pattern needed (Draft 2020-12 `$defs`/`pattern`/`enum`/`additionalProperties:false` through `$ref`, anti-traversal path regex, the strict-schema × lenient-consumer tension) is already proven in the existing v1.0 schemas (`asset.schema.json`, `audio_analysis.schema.json`, `prompts.schema.json`) and was empirically re-verified against `jsonschema 4.26.0` during this research.

The single most important design invariant — pulled forward from PITFALLS.md #11 (HIGHEST severity) and locked in `05-CONTEXT.md` — is that the extension must be **only-`+` lines on every schema diff**: new fields go in `properties` never in `required`; `additionalProperties: false` stays on every object; the `schema_version` pattern stays unchanged (NOT converted to a `const:"1.1"`); the v1 minimal fixture stays unmodified at `schema_version: "1"` and MUST remain green. The version literal is locked producer-side via a new `SCHEMA_VERSION = "1.1"` module constant in `scripts/export_asset.py` (modeled on the existing `_git_sha()` helper at line 61). The cross-version self-test is realized at the schema layer by (a) validating the v1 fixture against the extended v1.1 schemas (passes — additive optional fields don't break anything) and (b) validating the v1.1 fixture against the v1 schemas and proving the ONLY errors are `additionalProperties` violations (i.e., shared fields remain type-aligned; the sole delta is added optional fields). Approach (b) was empirically verified during research and produces exactly 1 error per added property, all with `validator="additionalProperties"`.

**Primary recommendation:** Extend the three existing harness primitives in lockstep — `spec/validate.py` `SHAPE_TO_FIXTURE`/`MINIMAL_ORDER` (add 3 new shapes, gate behind a v1.1 fixture pass), `scripts/verify_contract.py` `SIX_SHAPES`→`EIGHT_SHAPES` (add `characters`/`props`/`registry`), and `scripts/export_asset.py` `SCHEMA_VERSION` constant. The 3 new schemas + 2 extended schemas + 1 new fixture set + `_cross_version_check()` helper are the entire phase deliverable. No new tooling, no new deps, no pydantic, no fastjsonschema.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema authoring (characters/props/registry) | Spec / Contract (`spec/schemas/`) | — | Machine-checkable authority; lives in the repo as static JSON Schema files. No runtime tier owns this. |
| Schema extension (prompts/asset additive optional fields) | Spec / Contract (`spec/schemas/`) | — | Same authority layer; the only place where `additionalProperties:false` + `required` lists are allowed to change. |
| Fixture authoring (v1.1 self-contained sample) | Spec / Contract (`spec/fixtures/v1.1/`) | — | Test data that proves the schemas are satisfiable; doubles as the canonical example for consumers. |
| Verify harness extension (EIGHT_SHAPES + cross-version self-test) | Test tooling (`scripts/verify_contract.py`, `spec/validate.py`) | — | Regression harness; extends in-place (no rewrite) per the v1.0 `SIX_SHAPES` pattern. |
| `SCHEMA_VERSION` constant | Producer (`scripts/export_asset.py`) | — | Single-source-of-truth for the version literal written into every manifest; replaces the line-160 `"1"` string literal. |
| SPEC.md prose (§4 Changelog, §5.6/§5.7, §1 index) | Documentation (`spec/SPEC.md`, `spec/README.md`) | — | Human-readable overview; must mirror schema authority (on conflict, schema wins per SPEC §1). |

All work is in the **spec/contract + test-tooling + producer-constant** tiers. No browser, API, database, CDN, or ML tier is involved. This is the simplest possible responsibility map — Phase 5 has zero cross-cutting runtime concerns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**schema_version 锁定策略 (resolves success-criteria #4 vs CONTRACT-09 tension)**
- Keep `schema_version` as the **pattern** in `asset.schema.json` (`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` — accepts `"1"`, `"1.1"`, `"2.0"`). Do NOT hardcode a JSON-Schema `const:"1.1"` (that would reject the v1 minimal fixture's `"1"` and break CONTRACT-09 + Pitfall 11).
- Lock the *value* at the **producer** layer: `scripts/export_asset.py` introduces `SCHEMA_VERSION = "1.1"` module-level single-source constant; the literal `"schema_version": "1"` at `export_asset.py:160` is replaced by the constant.
- The v1 minimal fixture (`spec/fixtures/minimal/asset.json`) keeps `schema_version: "1"` and MUST stay green — this is the backward-compat proof.
- A NEW `spec/fixtures/v1.1/asset.json` carries `schema_version: "1.1"` + the new `characters`/`props` data+media refs.

**characters / props schema 丰富度**
- `characters.schema.json`: immutable ID (pattern `^char_[0-9]{3}$`) + `name` + `representative_image` (external png ref) + `appearance_shots:[int]` + `review_state` + `looks:[{label:str, image_ref:str, appearance_shots:[int]}]` (costume/造型 variants carry their own shot list).
- `props.schema.json`: **same core shape** but the variant field is `states[]` (not `looks[]`) — props vary by state (open/closed, intact/broken) not costume. ID pattern `^prop_[0-9]{3}$`.
- All new fields OPTIONAL (never in `required`); `additionalProperties: false` preserved (strict-schema × lenient-consumer tension from v1.0 holds).

**registry.schema.json cluster 细节**
- `clusters[]` members store **refs only**: `{shot_id:int, frame_pos:str|number, mask_quality:str}` — no 768-d DINOv2 embeddings inlined (bloat prevention).
- Each cluster carries `review_state: "proposed"|"confirmed"|"rejected"` + `tier: "auto_merge"|"review"|"auto_distinct"` enum + `mean_cosine: float`.
- Three-tier threshold constants (auto-merge ≥0.85 / review 0.6–0.85 / auto-distinct <0.6) documented in the schema `$comment`/`description`, NOT as numeric schema fields (default τ calibrated in Phase 7, not locked here).

**v1.1 fixture + 跨版本自检机制**
- New `spec/fixtures/v1.1/` directory: reuse minimal's 2 shots; add 2 characters (`char_001` 少女 / `char_002` 路人) + 1 prop (`prop_001` 落叶) + `registry.draft.json` (3 clusters, one per tier) + `prompts.json` carrying `character_refs[]`/`prop_refs[]`. Self-contained synthetic sample (not sliced ep01).
- Cross-version self-test realized at the **schema layer** in `verify_contract.py`: new `_cross_version_check()` — (a) v1 fixture passes v1.1 schema (additive optional fields don't break), (b) v1.1 fixture passes a permissive check proving extra fields are ignored-not-crashed. The genuine consumer-side warn-not-crash behavior is verified for real in Phase 9 (TS consumer) — Phase 5 does not stub a fake Python consumer.

### Claude's Discretion
- Exact prose wording of SPEC.md §5.6/§5.7 + §4 Changelog `1.1` entry.
- Internal helper organization within `verify_contract.py` (where `_cross_version_check` slots, how `EIGHT_SHAPES` is threaded through `run_producer_check`).
- Whether `spec/README.md` layout block + `SPEC.md` §1 schema-file index get a parallel update (they should, for consistency).

### Deferred Ideas (OUT OF SCOPE)
- Default DINOv2 cosine threshold τ value — Phase 7 research spike calibrates on ep01 (same-person vs different-person cosine histogram, valley pick); Phase 5 only locks the *schema shape* (`tier` enum + `mean_cosine` float), threshold constants documented but not empirically validated.
- `export_asset.py` conditional characters/props emit logic (only-when-files-exist) — scaffolded/locked in Phase 5 schema, full producer emit wired in Phase 7/8.
- Consumer-side (canvas) v1.1 warn-not-crash verification — Phase 9 against real TS consumer.
- `prompts.schema.json#scene` source mapping (route has no scene output today) — Phase 6 decides leave-empty vs future Qwen-VL extension; Phase 5 only ensures `scene` stays a valid optional string.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONTRACT-01 | 新增 `characters.schema.json`——角色注册表：不可变 ID（模式 `^char_[0-9]{3}$`）+ 名称 + 代表图引用 + `appearance_shots[]` + `review_state` + `looks[]` | `## Architecture Patterns` → Pattern 1 (characters.schema.json). Empirically verified: `$defs`/`look` cross-ref + `additionalProperties:false` through `$ref` + ID pattern + enum + path anti-traversal all pass `jsonschema 4.26.0`. |
| CONTRACT-02 | 新增 `props.schema.json`——道具注册表（同构，ID 模式 `^prop_[0-9]{3}$`） | `## Architecture Patterns` → Pattern 2 (props.schema.json). Mirror of characters with `states[]` replacing `looks[]`. Same empirical verification. |
| CONTRACT-03 | 新增 `registry.schema.json`——草稿/审阅形状：`clusters[]`（每簇带 `review_state` + 三档阈值标记 + 成员 shot/frame 列表） | `## Architecture Patterns` → Pattern 3 (registry.schema.json). Members are refs-only (no embeddings inlined); thresholds documented in `$comment` not enforced as numeric fields. |
| CONTRACT-04 | `prompts.schema.json` 纯增量扩展——新增 optional `character_refs[]`/`prop_refs[]`（不改动现有 6 字段，重构 `camera: string`） | `## Architecture Patterns` → Pattern 4 (prompts additive extension). Two new optional array properties added to `items.properties`; `required` array unchanged; `additionalProperties:false` preserved. |
| CONTRACT-05 | `asset.schema.json` 纯增量扩展——`data` 新增 optional `characters`/`props` 路径；`media` 新增 optional `characters[]`/`props[]`；`schema_version` const 升 `1`→`1.1` | `## Architecture Patterns` → Pattern 5 (asset additive extension). **Critical caveat:** `schema_version` stays a PATTERN, NOT a `const:"1.1"` (locked decision). The "升 1→1.1" is realized producer-side via `SCHEMA_VERSION` constant (CONTRACT-06), not schema-side. |
| CONTRACT-06 | `export_asset.py` 引入 `SCHEMA_VERSION` 单一源常量 = `1.1`；仅当文件存在时才 emit characters/props | `## Architecture Patterns` → Pattern 6 (SCHEMA_VERSION constant). Modeled on `_git_sha()` helper at line 61. Conditional emit scaffolding is Phase 7/8; Phase 5 only adds the constant + replaces the line-160 literal. |
| CONTRACT-07 | `verify_contract.py` `SIX_SHAPES`→`EIGHT_SHAPES` + 新增 v1.1 fixture 集 + 跨版本自检 | `## Architecture Patterns` → Pattern 7 (EIGHT_SHAPES + cross-version). Empirically verified cross-version mechanics: filter `additionalProperties` errors from v1.1-against-v1 validation → if empty, shared fields are type-aligned. |
| CONTRACT-08 | `SPEC.md` §4 Changelog 记 `1.1` 条目 + 新增 §5.6/§5.7 | `## Architecture Patterns` → Pattern 8 (SPEC prose). §4 Changelog mirrors the 2026-07-20 `1` entry format; §5.6/§5.7 describe characters/props data shapes + external media convention. Claude's discretion on exact wording. |
| CONTRACT-09 | 向后兼容冒烟——`spec/validate.py` 对 v1 `minimal` fixture 仍全绿 | `## Validation Architecture` → Phase Requirements → Test Map. Empirically confirmed: v1 fixture has no characters/props/registry fields, so extending the schemas with optional fields does not affect v1 validation. Re-verified: `jsonschema 4.26.0` accepts v1 instance against extended v1.1 schema (0 errors). |
</phase_requirements>

## Standard Stack

This phase installs **zero** new packages. The entire stack is already present and battle-tested in v1.0.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` | 4.26.0 (latest PyPI; installed) | Draft 2020-12 inline validator — validates every fixture + manifest | Already used by `spec/validate.py`, `scripts/export_asset.py:validate_asset_json`, `scripts/verify_contract.py:validate_asset_json`. Same `Draft202012Validator` API. `[VERIFIED: pip index versions jsonschema → 4.26.0 latest; python3 -c "import jsonschema" → 4.26.0 installed]` |
| Python stdlib `json` | 3.12.3 (system Python) | Fixture authoring + manifest I/O | Project convention: `indent=2`, `ensure_ascii=False` always for Chinese content (CLAUDE.md JSON I/O Conventions). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib.Path` | stdlib | Schema/fixture path resolution | Mirror the `SCHEMAS_DIR = SPEC_DIR / "schemas"` pattern from `spec/validate.py:31`. |
| `argparse` | stdlib | CLI flag parsing if any new opt-in flag is added to `verify_contract.py` | Follow kebab-case `--*` convention (CLAUDE.md CLI Argument Conventions). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `jsonschema.Draft202012Validator` | `fastjsonschema` (compiled validator) | Faster but compiles schemas at import time; v1.0 already chose stdlib `jsonschema` for all 3 validation sites. Switching would add a dep for no perceptible gain on fixture-scale inputs. |
| JSON Schema draft 2020-12 | draft 7 | Draft 2020-12 is the current standard; v1.0 schemas already declare `"$schema": "https://json-schema.org/draft/2020-12/schema"`. No reason to downgrade. |
| Custom Python validation | `pydantic` models | Would introduce a new dep + a parallel type system; the project's strict-schema × lenient-consumer tension is best expressed in JSON Schema directly (schema = machine-checkable truth; consumer runtime stays lenient). |

**Installation:**
```bash
# No installation needed — jsonschema 4.26.0 already installed.
# Verify before proceeding:
python3 -c "import jsonschema; print(jsonschema.__version__)"  # → 4.26.0
```

**Version verification (run during research, documented here for the planner):**
```bash
pip index versions jsonschema 2>/dev/null | head -2
# → jsonschema (4.26.0); INSTALLED: 4.26.0; LATEST: 4.26.0  [VERIFIED]
```

## Package Legitimacy Audit

> This phase installs **zero** external packages. The Package Legitimacy Gate protocol (Steps 1–4) is therefore trivially satisfied — there is nothing to audit.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none) | — | — | — | — | — | N/A — phase adds no new deps |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*The only existing package this phase touches (`jsonschema 4.26.0`) was already vetted and installed during v1.0 Phase 1. No re-verification needed.*

## Architecture Patterns

### System Architecture Diagram

```text
                    Phase 5 Contract Layer (all static files, zero runtime)
                    ═══════════════════════════════════════════════════════

  ┌──────────────────────────────────────────────────────────────────────┐
  │  spec/schemas/  (machine-checkable authority — 8 files after phase)  │
  │                                                                      │
  │  v1.0 (UNCHANGED semantically)          v1.1 NEW / EXTENDED          │
  │  ─────────────────────────────          ──────────────────────────  │
  │  shots.schema.json         (v1.0)       characters.schema.json (NEW) │
  │  audio_analysis.schema.json (v1.0)      props.schema.json      (NEW) │
  │  transcript.schema.json    (v1.0)       registry.schema.json   (NEW) │
  │  frames.schema.json        (v1.0)                                      │
  │  prompts.schema.json       (v1.0)  →    + character_refs[],prop_refs[]│
  │                                       (optional, additive ONLY)      │
  │  asset.schema.json         (v1.0)  →    + data.characters/props      │
  │                                       + media.characters[]/props[]   │
  │                                       (optional, additive ONLY;      │
  │                                        schema_version PATTERN         │
  │                                        unchanged — NOT const:"1.1")   │
  └──────────────────────────────────────────────────────────────────────┘
                                │
                                │ validates
                                ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  spec/fixtures/  (two fixture sets, both must stay green)            │
  │                                                                      │
  │  minimal/ (v1.0 — UNMODIFIED)         v1.1/ (NEW — synthetic sample) │
  │  ├── asset.json    (schema_version "1")├── asset.json (sv "1.1" +    │
  │  ├── shots.json                       │     data/media chars+props) │
  │  ├── audio_analysis.json              ├── shots.json (reuse 2 shots) │
  │  ├── transcript.json                  ├── characters.json (2 chars) │
  │  ├── frames.json                      ├── props.json (1 prop)       │
  │  └── prompts.json                     ├── registry.draft.json       │
  │                                       │     (3 clusters, 1 per tier)│
  │                                       └── prompts.json              │
  │                                             (with char/prop refs)   │
  └──────────────────────────────────────────────────────────────────────┘
                                │
                                │ validated by
                                ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Verification harness (extends in-place — no rewrite)                │
  │                                                                      │
  │  spec/validate.py                                                    │
  │    SHAPE_TO_FIXTURE/MINIMAL_ORDER  → add 3 new shapes + v1.1 pass    │
  │                                                                      │
  │  scripts/verify_contract.py                                          │
  │    SIX_SHAPES (L75) → EIGHT_SHAPES (+ characters/props/registry)     │
  │    run_self_test (L369) → keep v1 drift injection                    │
  │    NEW _cross_version_check():                                       │
  │      (a) v1 fixture → v1.1 schema  = 0 errors (forward-compat)       │
  │      (b) v1.1 fixture → v1 schema   = ONLY additionalProperties      │
  │          errors (shared fields type-aligned — backward-compat        │
  │          modulo additive optional fields)                            │
  │                                                                      │
  │  scripts/export_asset.py                                             │
  │    L160 literal "1" → SCHEMA_VERSION = "1.1" module constant         │
  │    (conditional characters/props emit deferred to Phase 7/8)         │
  └──────────────────────────────────────────────────────────────────────┘
```

**Trace the primary use case (CONTRACT-09 backward-compat):** v1 minimal fixture → `spec/validate.py` → loads each of 6 (now 9) schemas via `Draft202012Validator` → v1 instance has no `characters`/`props` fields, but those are optional in v1.1 schemas → 0 errors → fixture stays green. The cross-version check at `verify_contract.py:_cross_version_check` proves the same property holds programmatically.

### Recommended Project Structure
```
spec/
├── schemas/
│   ├── shots.schema.json              (v1.0 — UNCHANGED)
│   ├── audio_analysis.schema.json     (v1.0 — UNCHANGED)
│   ├── transcript.schema.json         (v1.0 — UNCHANGED)
│   ├── frames.schema.json             (v1.0 — UNCHANGED)
│   ├── prompts.schema.json            (v1.0 → EXTENDED: + character_refs[], prop_refs[])
│   ├── asset.schema.json              (v1.0 → EXTENDED: + data.{characters,props}, media.{characters[],props[]})
│   ├── characters.schema.json         (NEW — Phase 5 CONTRACT-01)
│   ├── props.schema.json              (NEW — Phase 5 CONTRACT-02)
│   └── registry.schema.json           (NEW — Phase 5 CONTRACT-03)
├── fixtures/
│   ├── minimal/                       (v1.0 — UNMODIFIED; backward-compat proof)
│   └── v1.1/                          (NEW — Phase 5)
│       ├── asset.json                 (schema_version "1.1" + data/media chars+props)
│       ├── shots.json                 (reuse minimal's 2 shots)
│       ├── audio_analysis.json        (reuse minimal's)
│       ├── transcript.json            (reuse minimal's)
│       ├── frames.json                (reuse minimal's)
│       ├── prompts.json               (with character_refs[]/prop_refs[])
│       ├── characters.json            (2 chars: char_001 少女, char_002 路人)
│       ├── props.json                 (1 prop: prop_001 落叶)
│       └── registry.draft.json        (3 clusters, one per tier)
├── validate.py                        (EXTENDED: shape maps add 3 new + v1.1 pass)
├── SPEC.md                            (EXTENDED: §4 Changelog +1.1 entry, §5.6/§5.7 NEW)
└── README.md                          (EXTENDED: layout block + index)

scripts/
├── verify_contract.py                 (EXTENDED: SIX_SHAPES→EIGHT_SHAPES + _cross_version_check)
└── export_asset.py                    (EXTENDED: SCHEMA_VERSION constant + L160 literal replaced)
```

### Pattern 1: characters.schema.json — immutable ID + looks[] via $defs
**What:** Top-level JSON array of character objects. Each carries an immutable ID (pattern-locked), a name, a representative image (external png ref with anti-traversal), a shot appearance list, a review state enum, and optional `looks[]` for costume/造型 variants.
**When to use:** Authoring the canonical character registry schema; the producer (Phase 7/8) writes `characters.json` conforming to this after HITL review confirms entries.
**Example:**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/characters.schema.json",
  "draft": "2020-12",
  "title": "Characters (cross-shot character registry)",
  "description": "Canonical character registry ... (CONTEXT D-XX: immutable IDs, review_state gating, looks[] for costume variants). Producer: registry/apply_edits.py (Phase 7/8). Only review_state='confirmed' entries flow downstream into prompt references.",
  "$comment": "Pitfall 5 (identity drift scope): character IDs are asset-local — single-asset only, no cross-asset continuity guarantee. Pitfall 3 (costume change): looks[] lets the same character carry multiple 造型 variants, each with its own shot list. Pitfall 17 (prompt dangling): ID immutability is non-negotiable — reviewer may merge/split but IDs are never reused or reformatted.",
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": ["id", "name", "review_state"],
    "properties": {
      "id": {
        "type": "string",
        "pattern": "^char_[0-9]{3}$",
        "description": "Immutable character ID (zero-padded 3-digit). Pattern locked in Phase 5; NEVER reused or reformatted (Pitfall 17)."
      },
      "name": {
        "type": "string",
        "minLength": 1,
        "description": "Display name (Chinese or English). Reviewer-editable; ID is not."
      },
      "representative_image": {
        "type": "string",
        "pattern": "^(?!.*\\.\\.)([^/]+/)*characters/[^:*?\"<>|]+\\.png$",
        "description": "External png relative path (NOT base64 — asset bloat prevention). Anti-traversal: rejects ../, absolute paths, Windows reserved chars. Canonical: characters/<id>.png."
      },
      "appearance_shots": {
        "type": "array",
        "items": {"type": "integer", "minimum": 1},
        "description": "Shot IDs where this character appears. Cross-references shots.json id field. Drives prompts.json character_refs[] attachment in Phase 8."
      },
      "review_state": {
        "enum": ["proposed", "confirmed", "rejected"],
        "description": "HITL review gate. Only 'confirmed' entries flow downstream into prompt references (Pitfall 7). 'proposed' = draft from re-id clustering; 'rejected' = soft-deleted (ID preserved for referential integrity)."
      },
      "looks": {
        "type": "array",
        "items": {"$ref": "#/$defs/look"},
        "description": "Optional costume/造型 variants. Each look carries its own appearance_shots[] so Phase 8 can attach per-look prompt refs, not just per-character."
      }
    }
  },
  "$defs": {
    "look": {
      "type": "object",
      "additionalProperties": false,
      "required": ["label", "image_ref"],
      "properties": {
        "label": {"type": "string", "minLength": 1, "description": "Human-readable look name (e.g. '默认造型', '回忆杀')."},
        "image_ref": {
          "type": "string",
          "pattern": "^(?!.*\\.\\.)([^/]+/)*characters/[^:*?\"<>|]+\\.png$",
          "description": "External png for this look. Same anti-traversal pattern as representative_image."
        },
        "appearance_shots": {
          "type": "array",
          "items": {"type": "integer", "minimum": 1},
          "description": "Shots where this specific look appears (subset of parent character's appearance_shots)."
        }
      }
    }
  }
}
```

**Empirically verified during research** (`jsonschema 4.26.0`):
- Valid instance (char with 2 looks): 0 errors
- ID `ch_001` (wrong format): 1 error, `validator=pattern`, message `"'ch_001' does not match '^char_[0-9]{3}$'"`
- `review_state: "draft"` (not in enum): 1 error, `validator=enum`
- `representative_image: "../escape.png"`: 1 error, `validator=pattern` (anti-traversal catches it)
- Look with `extra_field`: 1 error, `validator=additionalProperties` (strictness propagates through `$ref`) `[VERIFIED: empirical test with jsonschema 4.26.0]`

### Pattern 2: props.schema.json — mirror with states[] NOT looks[]
**What:** Same core shape as characters (immutable ID + name + representative_image + appearance_shots + review_state) but the variant field is `states[]` not `looks[]`. Props vary by state (open/closed, intact/broken), not by costume.
**When to use:** Authoring the canonical prop registry schema.
**Key design rule:** Semantic precision over schema uniformity. Resist the urge to unify characters and props into a single "entity" schema with a `type` discriminator — that would complicate the ID pattern (two patterns in oneOf) and the variant field name (`looks` vs `states` is meaningful to downstream consumers and prompt rendering).
**Example (delta from characters — full schema mirrors Pattern 1 with these substitutions):**
```json
{
  "...": "same $schema, $id (props.schema.json), title, description structure",
  "items": {
    "properties": {
      "id": {
        "type": "string",
        "pattern": "^prop_[0-9]{3}$",
        "description": "Immutable prop ID (zero-padded 3-digit)."
      },
      "states": {
        "type": "array",
        "items": {"$ref": "#/$defs/state"},
        "description": "Optional state variants (open/closed, intact/broken). Props vary by state, not by costume."
      }
    }
  },
  "$defs": {
    "state": {
      "type": "object",
      "additionalProperties": false,
      "required": ["label", "image_ref"],
      "properties": {
        "label": {"type": "string", "minLength": 1, "description": "State name (e.g. '打开', '关闭', '完好', '破碎')."},
        "image_ref": {"type": "string", "pattern": "^(?!.*\\.\\.)([^/]+/)*props/[^:*?\"<>|]+\\.png$"},
        "appearance_shots": {"type": "array", "items": {"type": "integer", "minimum": 1}}
      }
    }
  }
}
```

### Pattern 3: registry.schema.json — refs-only members + tier enum + $comment thresholds
**What:** Top-level JSON object describing the DRAFT re-id clustering output (pre-HITL-review). Carries `clusters[]` where each cluster has a `review_state`, a `tier` (auto_merge/review/auto_distinct), a `mean_cosine` similarity float, and a `members[]` list of shot/frame refs (NO inlined embeddings).
**When to use:** Validating `registry.draft.json` produced by Phase 7's re-id driver. NOT a canonical data file in `asset.json#data` — it's a working artifact (like `route_cache/` files) that feeds the HITL review HTML.
**Critical design rules:**
1. **Members are refs only** — `{shot_id, frame_pos, mask_quality}`. Never inline 768-d DINOv2 embeddings (bloat: a 50-cluster registry with embeddings would be ~150 KB vs ~5 KB refs-only).
2. **Thresholds documented, not enforced** — the three-tier constants (≥0.85 / 0.6–0.85 / <0.6) live in `$comment`/`description` as guidance for the Phase 7 default τ calibration, NOT as numeric schema fields. The schema validates the SHAPE of a cluster's tier label, not the cosine value that produced it.
3. **registry is NOT in asset.json#data** — it's a pipeline-internal artifact; only the post-review `characters.json` + `props.json` become canonical asset data files.

**Example:**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/registry.schema.json",
  "draft": "2020-12",
  "title": "Registry draft (pre-review re-id clustering output)",
  "description": "Draft clustering output from DINOv2 + AgglomerativeClustering. Consumed by html/gen_registry_review.py (HITL Stage C). This is NOT a canonical asset data file — registry.draft.json lives in the asset dir but is not listed in asset.json#data. Only after apply_edits.py (Stage D) do confirmed entries flow into canonical characters.json + props.json.",
  "$comment": "Three-tier threshold convention (CONTEXT-locked, Phase 7 calibrates default τ): tier='auto_merge' when mean_cosine >= 0.85; tier='review' when 0.6 <= mean_cosine < 0.85; tier='auto_distinct' when mean_cosine < 0.6. These thresholds are DOCUMENTED here as guidance, NOT enforced as schema numericMinimum/Maximum — the tier field is the authoritative label, mean_cosine is advisory. Phase 7's ep01 spike picks the actual τ via cosine-distribution valley.",
  "type": "object",
  "additionalProperties": false,
  "required": ["clusters"],
  "properties": {
    "generated_at": {
      "type": "string",
      "description": "ISO-8601 UTC timestamp of the clustering run."
    },
    "model": {
      "type": "string",
      "description": "Embedding model id (e.g. 'facebook/dinov2-base'). Advisory — for traceability."
    },
    "tau": {
      "type": "number",
      "description": "Cosine distance threshold τ used for this run (advisory — Phase 7 spike calibrates). NOTE: this is cosine DISTANCE (1 - similarity), so τ=0.30 ≈ similarity 0.70."
    },
    "clusters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["cluster_id", "review_state", "tier", "mean_cosine", "members"],
        "properties": {
          "cluster_id": {
            "type": "string",
            "pattern": "^(char|prop)_[0-9]{3}$",
            "description": "Proposed ID — must match either the character or prop ID pattern (the reviewer assigns final type during HITL)."
          },
          "review_state": {
            "enum": ["proposed", "confirmed", "rejected"],
            "description": "HITL gate. 'proposed' on draft emit; transitions to 'confirmed' or 'rejected' after review."
          },
          "tier": {
            "enum": ["auto_merge", "review", "auto_distinct"],
            "description": "Three-tier classification from mean_cosine vs τ. See $comment for threshold convention."
          },
          "mean_cosine": {
            "type": "number",
            "minimum": -1,
            "maximum": 1,
            "description": "Mean cosine SIMILARITY across cluster members (1.0 = identical; 0.0 = orthogonal; -1.0 = opposite). Note: distinct from tau which is cosine DISTANCE."
          },
          "members": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["shot_id", "frame_pos"],
              "properties": {
                "shot_id": {"type": "integer", "minimum": 1, "description": "Shot ID (cross-references shots.json id)."},
                "frame_pos": {
                  "type": ["string", "number"],
                  "description": "Frame position — either a label ('first'/'last'/'25%'/'50%'/'75%') or a time-in-seconds number. Producer-determined; schema accepts both for flexibility."
                },
                "mask_quality": {
                  "type": "string",
                  "description": "SAM3 mask quality metric. Recommended values: 'high'/'medium'/'low'/'unusable' (the latter skips clustering). NOT enum-constrained — Phase 7 driver may emit numeric scores or different tiers."
                }
              }
            }
          }
        }
      }
    }
  }
}
```

**Design note on `mask_quality` and `frame_pos` typing:** Both are intentionally loose (`string` / `string|number`) rather than strict enums. The CONTEXT locks the SHAPE (these fields exist and are strings/numbers); the exact enum values are producer-side (Phase 7 driver) — locking them now would force a schema revision if the driver's quality metric changes. This mirrors how the threshold constants live in `$comment` not in numeric fields. `[ASSUMED: the recommended enum values for mask_quality ('high'/'medium'/'low'/'unusable') — to be confirmed when Phase 7's driver is built]`

### Pattern 4: prompts.schema.json — additive optional character_refs[]/prop_refs[]
**What:** Extend the existing `items.properties` with two new OPTIONAL array properties. Never touch `required[]`. Never touch the existing 7 fields. Preserve `additionalProperties: false`.
**When to use:** The prompts schema extension.
**Critical invariant:** The `required` array (lines 11–22 of the current schema) stays exactly:
```json
["shot_id", "start_sec", "end_sec", "duration", "subject", "action", "camera", "scene", "lighting", "style", "prompt_text"]
```
Adding `character_refs` or `prop_refs` to `required` would be a MAJOR bump (Pitfall 11) — old producers that emit prompts.json without these fields would fail validation.
**Example (the ONLY properties block delta):**
```json
{
  "properties": {
    "...": "(all 11 existing fields unchanged — shot_id, start_sec, end_sec, duration, subject, action, camera, scene, lighting, style, prompt_text)",
    "character_refs": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^char_[0-9]{3}$",
        "description": "Character ID cross-reference (must exist in characters.json)."
      },
      "description": "Optional character IDs appearing in this shot. Attached in Phase 8 (PROMPT-01) based on characters.json#appearance_shots[]. Empty array or absent = no characters identified."
    },
    "prop_refs": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^prop_[0-9]{3}$",
        "description": "Prop ID cross-reference (must exist in props.json)."
      },
      "description": "Optional prop IDs appearing in this shot. Same attachment semantics as character_refs."
    }
  }
}
```

### Pattern 5: asset.schema.json — additive optional data/media + schema_version UNCHANGED
**What:** Extend `data.properties` with optional `characters`/`props` path strings; extend `media.properties` with optional `characters`/`props` png-path arrays. The `schema_version` pattern is UNCHANGED (stays `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`). The value `"1.1"` is locked producer-side (CONTRACT-06), NOT via JSON-Schema `const`.
**When to use:** The manifest schema extension.
**Three anti-patterns to explicitly avoid (Pitfall 11 — HIGHEST severity):**
1. **Do NOT** add `characters`/`props` to `data.required` — that would reject every v1 producer asset.
2. **Do NOT** add `characters`/`props` to `media.required` — same.
3. **Do NOT** change `schema_version` from `pattern` to `const: "1.1"` — that would reject the v1 minimal fixture's `"1"` (breaking CONTRACT-09).

**Example (properties delta only — required arrays unchanged):**
```json
{
  "data": {
    "properties": {
      "...": "(shots, audio_analysis, transcript, frames, prompts — unchanged)",
      "characters": {
        "type": "string",
        "pattern": "^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$",
        "description": "Optional relative path to characters.json (asset-local registry). Absent on v1 producer assets — consumers graceful-degrade."
      },
      "props": {
        "type": "string",
        "pattern": "^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$",
        "description": "Optional relative path to props.json."
      }
    }
  },
  "media": {
    "properties": {
      "...": "(video, stems — unchanged)",
      "characters": {
        "type": "array",
        "items": {
          "type": "string",
          "pattern": "^(?!.*\\.\\.)([^/]+/)*characters/[^:*?\"<>|]+\\.png$"
        },
        "description": "Optional canonical character png inventory (external files, NOT base64). Parallel to media.stems — the manifest-level inventory; characters.json#representative_image owns the ID→path mapping."
      },
      "props": {
        "type": "array",
        "items": {
          "type": "string",
          "pattern": "^(?!.*\\.\\.)([^/]+/)*props/[^:*?\"<>|]+\\.png$"
        },
        "description": "Optional canonical prop png inventory."
      }
    }
  }
}
```

**Why `media.characters` is an ARRAY (not an object with named keys like `media.stems`):** Character IDs are dynamic (`char_001`...`char_NNN`), unlike stems which are a fixed 4-element enum. An object with dynamic keys would require `patternProperties` (schema complexity). An array of path strings mirrors how files are listed in a directory and lets characters.json own the ID→path mapping (single source of truth). `[VERIFIED: design rationale grounded in CONTEXT-locked decision + SUMMARY anti-feature "external characters/<id>.png files under asset root, listed in asset.json#media.characters"]`

### Pattern 6: SCHEMA_VERSION constant in export_asset.py
**What:** Replace the literal `"schema_version": "1"` at `scripts/export_asset.py:160` with a module-level `SCHEMA_VERSION = "1.1"` constant. Modeled on the existing `_git_sha()` helper at line 61 (same "single-source module constant" pattern).
**When to use:** The producer version lock.
**Example:**
```python
# scripts/export_asset.py — near the top, after REPO constant (line 43)
# === 契约版本（单一源）=================================================
# SCHEMA_VERSION 是 asset.json 写出的 schema_version 字段的唯一来源。
# 改这个常量 = bump 契约版本。每次 spec/schemas/ 改动后必须同步审阅：
#   - 纯增量（新增 optional 字段）= minor bump（"1" → "1.1"）
#   - rename/语义漂移/删除/新增 required = major bump（→ "2"），必须先写 SPEC 迁移说明
# 见 SPEC.md §4 Schema Versioning + asset.schema.json#schema_version.description。
SCHEMA_VERSION = "1.1"

# ... later in build_asset_dict() ...
return {
    "schema_version": SCHEMA_VERSION,  # was literal "1" at line 160
    "...": "...",
}
```

**Important Phase-5 boundary:** Phase 5 only adds the constant + replaces the literal. The **conditional emit logic** (only write `data.characters`/`data.props`/`media.characters`/`media.props` when the files exist on disk) is Phase 7/8 work. Phase 5's `build_asset_dict` continues to emit the v1-shape manifest (5 required data files + video + 3 stems) — the new optional fields are added to the SCHEMA but not yet populated by the producer. This keeps the producer green (the v1.1 schema accepts v1-shape manifests since all new fields are optional). `[CITED: CONTEXT.md deferred ideas — "export_asset.py conditional characters/props emit logic ... scaffolded/locked in Phase 5 schema, full producer emit wired in Phase 7/8"]`

### Pattern 7: EIGHT_SHAPES + _cross_version_check in verify_contract.py
**What:** Rename `SIX_SHAPES` → `EIGHT_SHAPES` (add `characters`/`props`/`registry`). Add `_cross_version_check()` helper that proves the contract is bidirectionally compatible. Thread the 3 new shapes through `validate_six_shapes` (rename to `validate_eight_shapes` for clarity, or keep `validate_six_shapes` and just rebind the constant — the latter is less churn but the former is clearer).
**When to use:** CONTRACT-07.
**Cross-version mechanics (empirically verified during research):**

```python
def _cross_version_check() -> tuple[bool, str]:
    """Schema-layer proof of bidirectional v1↔v1.1 compatibility.

    Two assertions:
      (a) Forward-compat: v1 fixture passes v1.1 (extended) schemas.
          → Extended schemas are pure-additive optional → v1 instance validates cleanly.
      (b) Backward-compat modulo additive fields: v1.1 fixture validated against
          v1 (unextended) schemas produces ONLY `additionalProperties` errors.
          → Shared fields are type-aligned; the sole delta is added optional fields.
          → This is the schema-layer equivalent of "consumer ignores unknown fields,
            renders known parts, emits a warning" (SPEC §4 graceful-degrade rule).
          The REAL consumer-side warn-not-crash behavior is verified in Phase 9
          against the TS consumer — Phase 5 does NOT stub a fake Python consumer
          (would mock behavior the real consumer must own).
    """
    failures = []

    # (a) Forward: v1 minimal fixture → v1.1 extended schemas
    for shape in EIGHT_SHAPES:
        v1_fixture = load json from spec/fixtures/minimal/{shape}.json
        v11_schema = load from spec/schemas/{shape}.schema.json  # extended in-place
        errors = Draft202012Validator(v11_schema).iter_errors(v1_fixture)
        if errors:
            failures.append(f"(a) v1 {shape} failed v1.1 schema: {errors[0].message}")

    # Skip (a) for shapes that have no v1 fixture (characters/props/registry are NEW)
    # — those shapes only exist in v1.1.

    # (b) Backward: v1.1 fixture → v1 schemas (filter additionalProperties)
    # Build a v1 schema by removing the v1.1-added properties from a copy of each
    # extended schema. OR: keep the extended schema, validate v1.1 instance against
    # it, and assert the instance HAS the new fields populated (different assertion).
    #
    # Cleaner approach: validate v1.1 fixture against the CURRENT (v1.1) schema
    # and separately strip+revalidate. But simplest: just check the v1.1 fixture's
    # v1-compatible subset by filtering errors.
    for shape in ["asset", "prompts"]:  # only the EXTENDED schemas, not the new ones
        v11_fixture = load from spec/fixtures/v1.1/{shape}.json
        v1_schema = reconstruct v1 schema (remove v1.1-added properties)
        all_errors = Draft202012Validator(v1_schema).iter_errors(v11_fixture)
        non_addprop = [e for e in all_errors if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(
                f"(b) v1.1 {shape} has non-additive drift against v1 schema: "
                f"{len(non_addprop)} error(s); first: {non_addprop[0].message}"
            )

    if failures:
        return (False, "; ".join(failures))
    return (True, "v1↔v1.1 bidirectional compat proven (additive-only)")
```

**Empirical verification (run during research):**
```
(a) v1 instance vs v1.1 schema: 0 errors (expect 0) ✓
(b) v1.1 instance vs v1 schema: 1 error (expect ≥1 — additionalProperties)
    validator=additionalProperties, path=['data'], msg='characters' was unexpected
(b-prime) non-additionalProperties errors: 0 (expect 0 — shared fields type-aligned) ✓
```

**How to "reconstruct v1 schema" in code:** Two options:
1. **Git-based:** `git show v1.0-tag:spec/schemas/asset.schema.json` — recovers the exact v1 schema from the v1.0 tag. Most authentic; requires the tag to exist (v1.0 was tagged, per user memory).
2. **Copy-on-write:** Maintain a frozen `spec/schemas/v1/` snapshot directory alongside the live `spec/schemas/`. More moving parts; duplicates schema files.

**Recommendation:** Use option 1 (git-based) inside `_cross_version_check` — `subprocess.run(["git", "-C", str(REPO), "show", "v1.0:spec/schemas/asset.schema.json"])`. If the tag name differs, fall back to a hardcoded commit SHA. If neither is available, fall back to programmatic stripping (walk the v1.1 schema, remove the known-added property keys from `properties` dicts). `[ASSUMED: v1.0 git tag exists and points at the v1.0 schema set — user memory confirms "v1.0 SHIPPED 2026-07-20 (tag v1.0)"; planner should verify tag name and fall back to commit SHA if needed]`

**Threading EIGHT_SHAPES through `run_producer_check`:** The 3 new shapes (characters/props/registry) are **validate-when-present** — they're optional data files, not required by asset.schema.json. The producer check should:
- Always validate the 5 v1.0 data shapes + asset shape (required).
- If `data.characters` exists in the manifest → validate `characters.json` against `characters.schema.json`.
- Same for `props`.
- If `registry.draft.json` exists in the asset dir → validate it against `registry.schema.json` (registry is NOT in asset.json#data — it's a working file, discovered by filename).

This mirrors the v1.0 graceful-degrade philosophy: absence is not failure.

### Pattern 8: SPEC.md prose — §4 Changelog + §5.6/§5.7
**What:** Add a `1.1` entry to §4 Changelog (mirroring the 2026-07-20 `1` entry format). Add §5.6 (Characters) and §5.7 (Props) describing the data shapes + external media convention. Update §1 schema-file index (6 → 9 files). Update `spec/README.md` layout block to match.
**When to use:** CONTRACT-08. Claude's discretion on exact wording (per CONTEXT.md).
**§4 Changelog entry shape (recommendation):**
```markdown
- **2026-07-XX — `1.1` (additive extension)** — Phase 5 minor bump. Added 3 new
  optional data files (`characters.json`, `props.json`, `registry.draft.json`)
  + 3 new schemas (`characters`/`props`/`registry`). Extended `prompts.schema.json`
  with optional `character_refs[]`/`prop_refs[]`. Extended `asset.schema.json`
  with optional `data.characters`/`data.props` paths + `media.characters[]`/
  `media.props[]` external png inventories. Character/prop images are EXTERNAL
  png files (not base64 — asset bloat prevention, mirrors frames.json exception
  in reverse). schema_version pattern unchanged; producer locks value at "1.1"
  via SCHEMA_VERSION constant. v1 minimal fixture stays green (CONTRACT-09).
  Cross-version self-test in verify_contract.py proves bidirectional compat.
```

**§5.6/§5.7 shape:** Mirror the existing §5.1–§5.5 pattern (Producer line + field table + enum table if applicable + minimal JSON snippet + "Reference schema:" footer). The characters/props media convention sub-section should explicitly call out: external png (not base64), anti-traversal pattern, canonical `characters/<id>.png` naming, served by `scripts/serve.py` (Range-aware not required for pngs — they're small enough to serve as 200 OK, but the existing serve.py handles them transparently).

### Anti-Patterns to Avoid

- **ANTI: Adding to `required[]` on any extended schema.** Any new field in `required` = MAJOR bump (Pitfall 11). The v1 minimal fixture has no `character_refs`, `characters`, `looks`, etc. — adding these to `required` would make CONTRACT-09 fail. **Prevention:** diff each extended schema; the `required` array must be byte-identical to v1.0.
- **ANTI: Changing `schema_version` from `pattern` to `const:"1.1"`.** This is the single most tempting mistake (it "feels" like the right way to lock the version). It would reject every v1 asset including the minimal fixture. **Prevention:** the lock is producer-side (`SCHEMA_VERSION` constant), not schema-side. The pattern stays `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`.
- **ANTI: Inlining DINOv2 embeddings in registry members.** A 50-cluster × 768-d float32 registry would be ~150 KB; refs-only is ~5 KB. **Prevention:** members are `{shot_id, frame_pos, mask_quality}` only.
- **ANTI: Making `media.characters` an object with dynamic char_XXX keys.** Would require `patternProperties`; duplicates the ID→path mapping that characters.json already owns. **Prevention:** `media.characters` is `array<string>` — a flat path inventory.
- **ANTI: Enforcing the three-tier thresholds as numeric schema fields.** Locks the calibration before Phase 7's ep01 spike. **Prevention:** thresholds live in `$comment`; the `tier` enum is the authoritative label.
- **ANTI: Stubbing a fake lenient Python consumer to test graceful-degrade.** Mocks behavior the real TS consumer must own in Phase 9. **Prevention:** cross-version check is schema-layer only (`additionalProperties` error filtering); real consumer warn-not-crash is Phase 9.
- **ANTI: Modifying the v1 minimal fixture.** The fixture is the backward-compat proof. **Prevention:** `spec/fixtures/minimal/` is read-only for Phase 5; all new content goes in `spec/fixtures/v1.1/`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Draft 2020-12 validation | Custom recursive validator | `jsonschema.Draft202012Validator` (already installed, 4.26.0) | Already used at 3 sites (validate.py, export_asset.py, verify_contract.py); battle-tested in v1.0; handles `$ref`/`$defs`/`pattern`/`enum`/`additionalProperties` correctly. |
| Cross-version schema diff | Manual property-key walking | `git show <tag>:spec/schemas/<name>.schema.json` to recover v1 schema, then `Draft202012Validator.iter_errors()` + filter `e.validator != "additionalProperties"` | Git is the authoritative version history; the v1.0 tag gives the exact v1 schema without maintaining a parallel snapshot directory. `[ASSUMED: v1.0 tag exists]` |
| Anti-traversal path regex | Custom path validator | JSON Schema `pattern` with negative lookahead `^(?!.*\.\.)...` (mirrors `asset.schema.json:66`) | Already proven in v1.0 asset.schema.json; re-use the exact same pattern shape for consistency. |
| Reusable subschema (look/state/cluster member) | Copy-paste property blocks | JSON Schema `$defs` + `$ref` (mirrors `audio_analysis.schema.json:96-108` `stem_float_map`) | DRY; `additionalProperties:false` correctly propagates through `$ref` (empirically verified). |
| Manifest version literal | Hardcoded `"1.1"` strings scattered in `build_asset_dict` | `SCHEMA_VERSION = "1.1"` module constant (mirrors `_git_sha()` pattern at `export_asset.py:61`) | Single source of truth; Pitfall 12 ("forgot to bump") becomes impossible to accidentally cause. |

**Key insight:** This phase's hardest design work is deciding what NOT to enforce in schemas (thresholds, mask_quality enums, frame_pos typing) — over-constraining now forces schema revisions later. The v1.0 philosophy "strict schema × lenient consumer" applies inward too: the schema should be strict about ID patterns and required structure, but lenient about producer-determined metadata.

## Runtime State Inventory

> Phase 5 is a **contract/spec extension phase** (greenfield additive), NOT a rename/refactor/migration phase. The trigger criteria ("rename, rebrand, refactor, string replacement, or migration") are NOT met — the `schema_version` change is a new VALUE from a new constant, not a rename of an existing field. However, for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **1 item (intentionally NOT migrated):** `output/虫虫武侠小故事《小江湖》第01话：…/asset.json` has `schema_version: "1"`. After Phase 5, new exports write `"1.1"`, but this existing asset stays at `"1"` — it's the CONTRACT-09 backward-compat proof. The cross-version self-test proves v1 assets remain valid against v1.1 schemas. | **None** — explicitly preserved. Do NOT re-export ep01 during Phase 5. |
| Live service config | None — no external services hold the schema_version string. The canvas consumer reads it from each imported asset at runtime (Phase 9 concern, not Phase 5). | None — verified by codebase scan; schema_version only appears in `asset.json` files + `export_asset.py:160` + schema `$comment`s. |
| OS-registered state | None — no Task Scheduler / launchd / systemd / pm2 entries reference schema_version. | None — verified by CLAUDE.md Platform Requirements ("no deployment target ... one-shot local analysis tool"). |
| Secrets/env vars | None — no env vars read by any script (CLAUDE.md Configuration: "No .env file. No environment variables are read by any script"). | None. |
| Build artifacts | **1 item:** `spec/__pycache__/` may contain stale `validate.py` bytecode after editing. Also `verify_contract.py` is not in a package — no `.egg-info` concerns. | **Auto-resolves** — Python recompiles on next run. No action needed beyond standard `__pycache__` ignore (already in `.gitignore`). |

**Nothing found requiring migration.** The phase is pure-additive at every layer: schemas gain optional fields, fixtures gain a new directory, harness gains new shapes + a helper, producer gains a constant. No existing data is rewritten.

## Common Pitfalls

### Pitfall A: Accidental major bump via added required field (PITFALLS.md #11 — HIGHEST severity)
**What goes wrong:** A new field (e.g. `character_refs`) lands in the schema's `required` array. Every v1 producer asset instantly fails validation. CONTRACT-09 breaks. The "minor bump" claim becomes a lie.
**Why it happens:** JSON Schema `required` is a top-level array that's easy to edit carelessly. Copy-pasting from a "complete" example fixture (where every field is populated) tempts the author to mark all fields required.
**How to avoid:** Diff discipline — `git diff spec/schemas/<name>.schema.json` must show ONLY `+` lines in `properties` blocks; the `required` array must be byte-identical to v1.0. Add a verification step that loads both v1 and v1.1 schemas and asserts `set(v1["required"]) == set(v1.1["required"])` for the extended schemas.
**Warning signs:** `spec/validate.py` reports `[FAIL] asset` on the v1 minimal fixture after schema changes.

### Pitfall B: schema_version as const instead of pattern (CONTEXT-locked resolution)
**What goes wrong:** Developer "locks" the version by changing `asset.schema.json#schema_version` from `{"type":"string", "pattern":"..."}` to `{"const":"1.1"}`. The v1 minimal fixture (`schema_version: "1"`) instantly fails.
**Why it happens:** "Locking" a value feels like it should be a `const`. The distinction between schema-layer lock (const) and producer-layer lock (constant) is subtle.
**How to avoid:** The lock is at `export_asset.py:SCHEMA_VERSION = "1.1"` (producer-side). The schema pattern stays unchanged. CONTEXT.md explicitly locks this decision — do not re-open.
**Warning signs:** `[FAIL] asset: '1' does not match const "1.1"` in validate.py output.

### Pitfall C: Dangling prompt↔registry IDs in fixtures (PITFALLS.md #17)
**What goes wrong:** The v1.1 fixture's `prompts.json` references `char_001` but `characters.json` lists `char_001` as `char_0001` (or doesn't list it at all). The fixture is internally inconsistent.
**Why it happens:** Authoring 8+ fixture files by hand; ID typos propagate silently because jsonschema validates structure, not cross-file referential integrity.
**How to avoid:** The Phase 5 fixtures must be internally consistent — every `prompts[].character_refs[]` ID must exist in `characters.json`, and every `characters[].appearance_shots[]` shot ID must exist in `shots.json`. Add a fixture-consistency check to `_cross_version_check` or a new `_fixture_consistency_check` helper. (The full cross-file integrity check is Phase 8 PROMPT-03, but fixtures should be self-consistent from day 1.)
**Warning signs:** Manual grep shows ID mismatches between fixture files.

### Pitfall D: Cross-version check uses wrong direction
**What goes wrong:** Developer writes `_cross_version_check` to validate v1 fixture against v1 schema (tautology — always passes) and v1.1 fixture against v1.1 schema (also tautology). The actual contract invariant (v1 fixture passes v1.1 schema; v1.1 fixture's v1-subset is clean) is never tested.
**Why it happens:** The "both directions" language is ambiguous without specifying which fixture against which schema.
**How to avoid:** Be explicit: (a) v1 fixture → v1.1 schema (forward-compat, must be 0 errors); (b) v1.1 fixture → v1 schema, filtered to non-`additionalProperties` errors (backward-compat modulo additive fields, must be 0 errors). The filtering step is the key insight — `additionalProperties` errors are EXPECTED and don't count as drift.
**Warning signs:** The cross-version check always passes trivially regardless of schema changes.

### Pitfall E: Over-constraining producer-determined metadata
**What goes wrong:** `mask_quality` is locked as `enum: ["high","medium","low","unusable"]` in registry.schema.json. Phase 7's driver emits `"0.87"` (numeric score) or `"acceptable"` — schema rejects it, forcing a Phase 7 schema revision.
**Why it happens:** Schema authors want maximum strictness; "document in $comment" feels weaker than "enforce with enum".
**How to avoid:** Distinguish between **contract invariants** (ID patterns, required structure, review_state values — these MUST be enforced because downstream consumers depend on them) and **producer metadata** (mask_quality scores, frame_pos formats, threshold values — these are producer-determined and should be loose-typed with `$comment` guidance). The threshold constants are the canonical example: documented in `$comment`, NOT in numeric fields.
**Warning signs:** Phase 7/8 can't emit valid data without a Phase 5 schema revision.

## Code Examples

### Cross-version validation mechanics (empirically verified)
```python
# Source: empirical verification during Phase 5 research (jsonschema 4.26.0)
from jsonschema import Draft202012Validator

# (a) Forward-compat: v1 fixture must pass v1.1 (extended) schema
v11_schema = json.loads((SCHEMAS_DIR / "asset.schema.json").read_text("utf-8"))
v1_asset = json.loads((FIXTURE_DIR / "minimal" / "asset.json").read_text("utf-8"))
forward_errors = list(Draft202012Validator(v11_schema).iter_errors(v1_asset))
assert len(forward_errors) == 0  # additive optional fields don't break v1

# (b) Backward-compat: v1.1 fixture against v1 schema, filter additionalProperties
# Recover v1 schema via git (preferred) or programmatic strip
import subprocess, json
v1_schema_raw = subprocess.run(
    ["git", "-C", str(REPO), "show", "v1.0:spec/schemas/asset.schema.json"],
    capture_output=True, text=True, check=True
).stdout
v1_schema = json.loads(v1_schema_raw)

v11_asset = json.loads((FIXTURE_DIR / "v1.1" / "asset.json").read_text("utf-8"))
all_errors = list(Draft202012Validator(v1_schema).iter_errors(v11_asset))
non_addprop_errors = [e for e in all_errors if e.validator != "additionalProperties"]
assert len(non_addprop_errors) == 0  # shared fields type-aligned; only delta is added optional fields
# The additionalProperties errors ARE expected — they prove the v1.1 fixture
# carries fields the v1 schema doesn't know about, which is exactly what
# "additive minor bump" means.
```

### EIGHT_SHAPES threading (validate-when-present)
```python
# Source: extending the existing validate_six_shapes pattern (verify_contract.py:197-246)
# The 3 new shapes are optional — absence is NOT failure (graceful-degrade).

EIGHT_SHAPES = ["asset", "shots", "audio_analysis", "transcript",
                "frames", "prompts",
                "characters", "props", "registry"]  # last 3 are NEW

def validate_eight_shapes(asset_dir: Path, manifest: dict) -> list:
    """Extended: validates the 5 v1 required shapes + asset always,
    then validates characters/props/registry ONLY when present."""
    failures = []
    data_field = manifest.get("data") if isinstance(manifest, dict) else None
    if not isinstance(data_field, dict):
        data_field = {}

    # --- v1.0 shapes (always validated — they're required) ---
    for shape in ["asset", "shots", "audio_analysis", "transcript", "frames", "prompts"]:
        # (existing logic from validate_six_shapes — unchanged)
        ...

    # --- v1.1 NEW shapes (validate-when-present — optional) ---
    # characters/props are referenced by data.<shape> in the manifest
    for shape in ["characters", "props"]:
        rel = data_field.get(shape)
        if not isinstance(rel, str):
            continue  # absent — graceful-degrade, not failure
        instance_path = asset_dir / rel
        if not instance_path.is_file():
            failures.append(f"{shape}: data.{shape} references missing file {instance_path}")
            continue
        # ... validate against spec/schemas/{shape}.schema.json

    # registry is NOT in asset.json#data — discover by canonical filename
    registry_path = asset_dir / "registry.draft.json"
    if registry_path.is_file():
        # ... validate against spec/schemas/registry.schema.json
        pass  # absent → skip (registry is a working artifact, not canonical data)

    return failures
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JSON Schema draft 7 | Draft 2020-12 | v1.0 Phase 1 (2026-07-20) | `$defs` replaces `definitions`; `prefixItems` replaces draft-7 `items`+`additionalItems`. All v1.0 schemas already on 2020-12. |
| Single fixture set (`spec/fixtures/minimal/`) | Dual fixture sets (`minimal/` + `v1.1/`) | Phase 5 (this phase) | v1 fixture proves backward-compat; v1.1 fixture exercises new fields. Cross-version check compares both. |
| `SIX_SHAPES` hardcoded list | `EIGHT_SHAPES` (still hardcoded) | Phase 5 (this phase) | Considered data-driven auto-discovery (glob `spec/schemas/*.schema.json`), but explicit list catches accidental schema-file additions and keeps the list reviewable. Matches v1.0 philosophy. |
| `schema_version` literal at `export_asset.py:160` | `SCHEMA_VERSION` module constant | Phase 5 (this phase) | Single-source-of-truth; Pitfall 12 prevention. |

**Deprecated/outdated:**
- `"schema_version": "2"` wording in `.planning/PROJECT.md:83` — this is **stale doc drift** from before the SUMMARY OPEN DECISION resolved on `"1.1"`. Line 97 of the same file already says `"1.1"`. The planner should fix line 83 as a doc-consistency fix (low-risk, aligned with CONTRACT-08's spirit even though PROJECT.md is not explicitly in CONTRACT-08 scope). `[ASSUMED: this is doc drift, not a locked decision — user confirmed "1.1" via CONTEXT.md]`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The v1.0 git tag exists and points at the v1.0 schema set (for `_cross_version_check` git-based v1 schema recovery). | Architecture Patterns → Pattern 7 | If tag is missing/renamed, fall back to programmatic property stripping or a hardcoded commit SHA. User memory says "v1.0 SHIPPED 2026-07-20 (tag v1.0)" — high confidence but planner should `git tag -l "v1*"` to confirm. |
| A2 | `mask_quality` recommended enum values are `"high"/"medium"/"low"/"unusable"`. | Architecture Patterns → Pattern 3 | If Phase 7's driver emits different values, the schema (loose-typed `string`) still accepts them — no revision needed. The `$comment` recommendation may need updating. Low risk. |
| A3 | `frame_pos` should accept both string labels and numeric seconds (`type: ["string","number"]`). | Architecture Patterns → Pattern 3 | If the Phase 7 driver standardizes on one format, the schema can be tightened later. Current looseness is intentional flexibility. |
| A4 | `.planning/PROJECT.md:83` (`schema_version "2"`) is stale doc drift, not a locked decision. | State of the Art → Deprecated | If the user actually intended `"2"`, the entire phase literal changes. CONTEXT.md (the authoritative locked-decisions source) says `"1.1"`, so this is almost certainly drift. Planner should fix the doc inconsistency. |
| A5 | `media.characters` should be `array<string>` (not an object with named keys). | Architecture Patterns → Pattern 5 | If the team prefers an object for consistency with `media.stems`, the schema shape changes — but the CONTEXT-locked decision and SUMMARY anti-feature both point to external png files listed as an array. Medium confidence. |

**Note:** All other claims in this research are either `[VERIFIED]` (empirically tested with `jsonschema 4.26.0` or `pip index versions`), `[CITED]` (directly quoted from CONTEXT.md / SPEC.md / source code), or direct codebase observations.

## Open Questions

1. **Exact v1.0 git tag name for v1 schema recovery**
   - What we know: User memory says "tag v1.0"; SUMMARY says "v1.0 SHIPPED 2026-07-20".
   - What's unclear: Whether the tag is literally `v1.0` or `v1` or includes a date suffix.
   - Recommendation: Planner runs `git tag -l "v1*"` in Wave 0; if absent, `_cross_version_check` falls back to programmatic property stripping (walk v1.1 schema, remove known-added keys, revalidate).

2. **Whether `_cross_version_check` should also test prompts/asset with the registry fixture**
   - What we know: The registry is NOT in asset.json#data, so asset↔registry cross-version is N/A.
   - What's unclear: Whether the planner wants a separate "fixture self-consistency" check (prompt IDs ⊆ character IDs ⊆ shots IDs).
   - Recommendation: Add a lightweight `_fixture_consistency_check` that greps IDs across the v1.1 fixture set. This is distinct from CONTRACT-07 (cross-version) but prevents Pitfall C (dangling IDs). Phase 8's PROMPT-03 is the full integrity check; Phase 5's is just "fixtures don't ship broken".

3. **PROGRAMMATIC schema reconstruction vs git-based**
   - What we know: Git-based is most authentic; programmatic is most portable.
   - What's unclear: Whether the planner prefers minimal subprocess calls (programmatic) or maximal authenticity (git).
   - Recommendation: Git-based primary, programmatic fallback. The fallback can be a simple function that takes the v1.1 schema + a list of known-added property paths and returns a stripped copy.

## Environment Availability

> Phase 5 has minimal external dependencies (contract/spec work). All required tools are already installed and used by v1.0.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All schema/fixture/harness work | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `jsonschema` | All validation (validate.py, export_asset.py, verify_contract.py) | ✓ | 4.26.0 (latest PyPI) | — |
| `git` | `_cross_version_check` v1 schema recovery (if git-based approach) | ✓ | (repo is git-tracked) | Programmatic property stripping |
| `ffmpeg`/`ffprobe` | NOT required by Phase 5 (no media processing) | ✓ (per CLAUDE.md) | — | — |
| `httpx` | NOT required by Phase 5 (Phase 6 dep) | ✓ | 0.28.1 | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — all Phase 5 dependencies are met.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — section REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | No pytest/jest — project uses standalone Python scripts that `sys.exit(0/1)` (v1.0 RETROSPECTIVE "Patterns Established": "Per-phase standalone verify scripts ... both sys.exit(0/1). Matches both repos' no-test-framework convention.") |
| Config file | none — inline in `spec/validate.py` + `scripts/verify_contract.py` |
| Quick run command | `python3 spec/validate.py` (validates minimal + v1.1 fixtures, ~1s) |
| Full suite command | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONTRACT-01 | characters.schema.json validates v1.1 fixture | schema-validity | `python3 -c "from jsonschema import Draft202012Validator as V; import json; s=json.load(open('spec/schemas/characters.schema.json')); i=json.load(open('spec/fixtures/v1.1/characters.json')); assert not list(V(s).iter_errors(i))"` | ❌ Wave 0 (schema + fixture both NEW) |
| CONTRACT-02 | props.schema.json validates v1.1 fixture | schema-validity | (same pattern, swap schema/fixture names) | ❌ Wave 0 |
| CONTRACT-03 | registry.schema.json validates v1.1 fixture (3 clusters, one per tier) | schema-validity | (same pattern) | ❌ Wave 0 |
| CONTRACT-04 | prompts.schema.json extended additively (v1 fixture still passes) | schema-validity + cross-version | `python3 spec/validate.py` (v1 minimal prompts.json stays green) + `_cross_version_check` (a) | ❌ Wave 0 (cross-version helper NEW) |
| CONTRACT-05 | asset.schema.json extended additively (v1 fixture still passes; v1.1 fixture validates) | schema-validity + cross-version | `python3 spec/validate.py` + `_cross_version_check` (a)+(b) | ❌ Wave 0 |
| CONTRACT-06 | export_asset.py emits `schema_version: "1.1"` via SCHEMA_VERSION constant | producer smoke | `python3 scripts/export_asset.py --work-dir <tmp> --video <fixture> --stems-source-dir <fixture> --output <tmp>/asset.json && python3 -c "import json; assert json.load(open('<tmp>/asset.json'))['schema_version']=='1.1'"` | ❌ Wave 0 (constant NEW) |
| CONTRACT-07 | verify_contract.py EIGHT_SHAPES + cross-version self-test both directions | harness | `python3 scripts/verify_contract.py --mode=producer` (includes cross-version check) + `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` (fail-loud still works) | ❌ Wave 0 (helper NEW) |
| CONTRACT-08 | SPEC.md §4 Changelog + §5.6/§5.7 exist and are consistent with schemas | manual review (prose) | (no automated prose check — human review per CLAUDE.md "two-tier authority: schemas are machine-checkable truth, SPEC.md is human overview") | ❌ Wave 0 (prose NEW) |
| CONTRACT-09 | v1 minimal fixture stays 6/6 green after schema extensions | backward-compat | `python3 spec/validate.py` (minimal fixture pass) | ✅ exists (extends in place) |

### Sampling Rate
- **Per task commit:** `python3 spec/validate.py` — fast (~1s), catches schema breakage on either fixture set immediately.
- **Per wave merge:** `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` — full harness including cross-version both directions + self-test fail-loud.
- **Phase gate:** Full suite green before `/gsd:verify-work`. Specifically: minimal fixture 6/6 green (CONTRACT-09), v1.1 fixture 8/8 green (CONTRACT-01..05), cross-version both directions pass (CONTRACT-07), self-test fail-loud still works.

### Wave 0 Gaps
- [ ] `spec/schemas/characters.schema.json` — NEW (CONTRACT-01)
- [ ] `spec/schemas/props.schema.json` — NEW (CONTRACT-02)
- [ ] `spec/schemas/registry.schema.json` — NEW (CONTRACT-03)
- [ ] `spec/schemas/prompts.schema.json` — EXTENDED (CONTRACT-04: + character_refs[]/prop_refs[])
- [ ] `spec/schemas/asset.schema.json` — EXTENDED (CONTRACT-05: + data/media characters/props)
- [ ] `spec/fixtures/v1.1/` directory — NEW (8 files: asset/shots/audio_analysis/transcript/frames/prompts/characters/props/registry.draft)
- [ ] `scripts/export_asset.py` — `SCHEMA_VERSION` constant + line-160 replacement (CONTRACT-06)
- [ ] `scripts/verify_contract.py` — `EIGHT_SHAPES` rename + `_cross_version_check` helper (CONTRACT-07)
- [ ] `spec/validate.py` — shape maps extended to discover + validate v1.1 fixture set (CONTRACT-09 regression coverage)
- [ ] `spec/SPEC.md` — §4 Changelog +1.1 entry + §5.6/§5.7 + §1 index update (CONTRACT-08)
- [ ] `spec/README.md` — layout block + index update (CONTRACT-08 consistency)

*(No new test framework needed — existing harness extends in place.)*

## Security Domain

> `security_enforcement` not explicitly set in `.planning/config.json` — treat as enabled. However, Phase 5 is a contract/spec phase with **no network surface, no auth, no user input, no secrets**. The security surface is minimal — limited to path-traversal defenses in schema patterns and the immutability contract on registry IDs.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 5 has no authentication surface (no network, no users). |
| V3 Session Management | no | No sessions. |
| V4 Access Control | no | No access control — static schema files. |
| V5 Input Validation | **yes** | JSON Schema `pattern` + `additionalProperties:false` IS the input validation. Every field touching a filesystem path uses the anti-traversal pattern `^(?!.*\.\.)...` (mirrors asset.schema.json:66). ID fields use strict patterns (`^char_[0-9]{3}$`, `^prop_[0-9]{3}$`). |
| V6 Cryptography | no | No crypto operations. |
| V7 Error Handling | **partial** | Schema validation errors are surfaced via `_format_errors` (validate.py:60-66) and `validate_asset_json` (export_asset.py:106-127). No sensitive info leakage — schemas and fixtures are non-secret. |
| V8 Data Protection | no | No PII handling (synthetic fixtures use fictional character names like "少女"). |
| V12 Files & Resources | **yes** | External png paths (characters/props media) are validated against anti-traversal patterns. The schema rejects `../`, absolute paths, and Windows reserved chars — same defense as v1.0 asset.schema.json media paths. |

### Known Threat Patterns for JSON Schema contract phases

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via malicious fixture/asset path | Tampering | `^(?!.*\.\.)` negative-lookahead pattern on every filesystem path field (data.*, media.*, representative_image, image_ref). `[VERIFIED: empirically rejects "../escape.png" in jsonschema 4.26.0]` |
| Registry ID hijacking (malicious producer reuses a confirmed ID) | Spoofing | ID pattern `^char_[0-9]{3}$` + immutability rule documented in `$comment` (Pitfall 17). Runtime enforcement is Phase 7/8 (apply_edits.py guarantees freshness). |
| Schema injection via additionalProperties | Tampering | `additionalProperties: false` on every object — recursively verified through `$ref` (empirically confirmed: a `look` with an extra field fails validation). |
| DoS via pathological fixture (deeply nested, huge arrays) | Denial of Service | Out of scope for Phase 5 (fixtures are author-controlled, not user-input). Phase 7+ producer should add `maxItems`/`maxDepth` if untrusted input is ever accepted. `[ASSUMED: fixtures remain author-controlled throughout v1.1]` |

## Sources

### Primary (HIGH confidence)
- **Empirical verification with `jsonschema 4.26.0`** (run during research):
  - Cross-version mechanics: v1 instance vs v1.1 schema = 0 errors; v1.1 instance vs v1 schema = 1 additionalProperties error; filtered non-additionalProperties errors = 0.
  - characters.schema.json pattern: `$defs`/`$ref` + `additionalProperties:false` propagation + ID pattern + enum + anti-traversal all behave correctly.
- **Codebase (read in full)**:
  - `spec/schemas/{asset,prompts,audio_analysis,frames,shots}.schema.json` — the schemas to extend + the patterns to mirror (`$defs` in audio_analysis, anti-traversal in asset, `additionalProperties:false` everywhere).
  - `spec/validate.py` — `SHAPE_TO_FIXTURE`/`MINIMAL_ORDER`/`SMOKE_SHAPES` maps + `load_validator` helper + `_format_errors` pattern.
  - `scripts/verify_contract.py` — `SIX_SHAPES` (L75), `validate_six_shapes` (L197-246), `run_self_test` (L369-442, injects `schema_version='v1'`), `run_producer_check` (L249-300).
  - `scripts/export_asset.py` — `build_asset_dict` (L129-187, esp. L160 `"schema_version": "1"` literal), `_git_sha()` (L60-68, model for SCHEMA_VERSION constant), `validate_asset_json` (L106-127).
  - `spec/SPEC.md` — §4 Schema Versioning (L100-151, esp. Changelog L148-150), §5 canonical data shapes (L154-337), §1 schema-file index (L23-34), §6 media conventions (L341-389).
  - `spec/fixtures/minimal/{asset,prompts,shots,frames}.json` — the v1 fixture shape to mirror in v1.1/ (2-shot synthetic sample, schema_version "1").
  - `spec/README.md` — layout block (L9-28) + schema-file index.
- **Planning artifacts**:
  - `.planning/phases/05-contract-v1-1/05-CONTEXT.md` — all locked decisions (schema_version pattern-not-const, ID patterns, registry refs-only, fixture content, cross-version mechanics).
  - `.planning/REQUIREMENTS.md` — CONTRACT-01..09 verbatim.
  - `.planning/research/SUMMARY.md` — cross-research consensus (Phase 1 contract-first pattern proven; httpx 0.28.1 + jsonschema 4.26.0 live-verified).
  - `.planning/research/PITFALLS.md` — Pitfalls 11 (highest severity), 17 (dangling IDs), 7 (review_state gating), 5 (ID scope), 3 (looks[] costume change), 6 (mask_quality).
  - `.planning/STATE.md` — v1.1 schema_version `"1.1"` locked decision.
  - `.planning/RETROSPECTIVE.md` — v1.0 lessons (inline jsonschema over subprocess-to-validate.py; per-phase standalone verify scripts; formally-accept-and-document).

### Secondary (MEDIUM confidence)
- `pip index versions jsonschema` — confirmed 4.26.0 is latest + installed.
- `pip index versions httpx` — confirmed 0.28.1 is latest (Phase 6 dep, not Phase 5).
- User memory `canvas-asset-collection-worktree.md` — v1.0 tagged `(tag v1.0)` (basis for A1 assumption).

### Tertiary (LOW confidence)
- None — all claims are empirically verified or directly cited from repo source.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages; `jsonschema 4.26.0` is already installed, latest, and battle-tested in v1.0.
- Architecture: HIGH — all patterns empirically verified against `jsonschema 4.26.0`; cross-version mechanics proven end-to-end.
- Pitfalls: HIGH — directly anchored in repo source (PITFALLS.md) + CONTEXT.md locked decisions; no ML/route uncertainty (those are Phase 6/7 concerns).
- Validation: HIGH — extends existing `sys.exit(0/1)` harness pattern; no new framework.
- Security: MEDIUM-HIGH — minimal surface (path traversal + ID immutability); empirically verified anti-traversal patterns.

**Research date:** 2026-07-24
**Valid until:** 2026-08-24 (30 days — stable domain; JSON Schema draft 2020-12 is a fixed standard, jsonschema 4.26.0 is mature)

## RESEARCH COMPLETE

**Phase:** 5 - Contract v1.1
**Confidence:** HIGH

### Key Findings
- **Cross-version self-test mechanics empirically proven:** validating the v1.1 fixture against the v1 schema produces ONLY `additionalProperties` errors; filtering those leaves 0 errors — proving shared fields stay type-aligned. This is the schema-layer realization of "ignored-not-crashed" without needing a fake Python consumer.
- **Every JSON Schema pattern needed is already proven in v1.0:** `$defs`+`$ref` (audio_analysis), anti-traversal regex (asset), `enum`+`additionalProperties:false` propagation through `$ref` — all empirically re-verified during research against `jsonschema 4.26.0`.
- **schema_version lock is producer-side, NOT schema-side:** the pattern stays `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`; the literal `"1.1"` lives in a new `SCHEMA_VERSION` constant in `export_asset.py` (modeled on `_git_sha()` at line 61). Converting to `const:"1.1"` would break CONTRACT-09.
- **Zero new dependencies:** `jsonschema 4.26.0` (latest) is already installed and used at 3 validation sites. No pydantic, no fastjsonschema, no new test framework. The entire phase deliverable is schema files + fixtures + harness extension + 1 producer constant.
- **Pitfall 11 (accidental major bump) is the single highest-severity risk:** prevention is diff discipline (`required` arrays byte-identical to v1.0; only `+` lines in `properties` blocks) + the cross-version check as automated guard.

### File Created
`/data/workspace/kais-shot-timeline/.planning/phases/05-contract-v1-1/05-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Zero new packages; `jsonschema 4.26.0` installed + verified as latest. |
| Architecture | HIGH | All patterns empirically verified; cross-version mechanics proven end-to-end with real jsonschema runs. |
| Pitfalls | HIGH | Directly anchored in repo PITFALLS.md + CONTEXT.md locked decisions; no ML/route uncertainty in Phase 5 scope. |
| Validation | HIGH | Extends proven v1.0 `sys.exit(0/1)` standalone-script pattern; no framework gap. |

### Open Questions
1. Exact v1.0 git tag name for `_cross_version_check` schema recovery (low-risk fallback: programmatic strip).
2. Whether to add a fixture self-consistency check (prompt IDs ⊆ character IDs) alongside the cross-version check — recommended but not strictly required by CONTRACT-07.
3. `.planning/PROJECT.md:83` doc drift (`"2"` vs `"1.1"`) — almost certainly stale; planner should fix as a consistency item.

### Ready for Planning
Research complete. Planner can now create PLAN.md files. The phase is low-risk, zero-new-deps, and follows the proven v1.0 contract-first pattern. The only design subtlety is the schema_version lock location (producer constant, not schema const) — already resolved in CONTEXT.md.
