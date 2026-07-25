# Phase 11: Contract v1.2 — Research

**Researched:** 2026-07-25
**Domain:** JSON Schema (draft 2020-12) contract extension + bidirectional cross-version proof + SPEC prose
**Confidence:** HIGH (every claim verified against v1.1 source files in this repo — line numbers cited inline)

## Summary

Phase 11 is the **third contract-locking phase** in this repo's history (Phase 1 = v1.0 initial, Phase 5 = v1.1 additive). It is a **mechanical-mirror-with-three-deviations** phase: every architectural decision was already proven by Phase 5, and the empirical deviations are forced by Phase 10's spike outcomes — which are already locked in CONTEXT.md and PROJECT.md. There is no novel technical research to perform; this research is a **pattern-extraction exercise** that gives the planner exact line numbers, JSON paths, and function names to copy.

**The three locked Phase-10-informed deviations** (from CONTEXT.md, non-negotiable):

1. **`instruments` field = OMITTED from v1.2 entirely.** MUS-04 deferred to v1.3. MERT-v1-95M has NO instrument classifier head (Phase 10 spike only produced duration-correlated K-means clusters); PANNs Cnn14 was zenodo-blocked at spike time. This OVERRIDES the ROADMAP Phase-11 dependency note (line 77, "instruments as `list[{label,confidence}]`") — that note predated the spike and is stale. The plan MUST NOT add an `instruments` field to `audio_semantic.schema.json`, `asset.schema.json`, or any SPEC shape table.
2. **`dialogue.emotion` = `type: "string"` (NOT enum), nullable + paired with `emotion_confidence: number` (0..1).** SenseVoice's `self_consistency_pct=100.0` is a label-stability proxy, NOT calibrated accuracy — a closed 7-class enum would over-claim calibration we do not have.
3. **`dialogue.words[]` = EXPERIMENTAL OPTIONAL sub-field.** Per-segment word-level timestamps are gated behind a top-level `word_level_experimental: boolean` flag. Segment-level remains the SLA path. WhisperX boundary drift median=101.5ms (<200ms ✓) but aggregate per-word drift is a metric-definition artifact (defer Phase 12).

**Primary recommendation:** Mirror Phase 5 line-for-line. The planner should be able to write tasks that say "mirror `scripts/export_asset.py:312-330` (Phase 7 conditional characters/props emission) for `data.audio_semantic`/`data.speakers`" and "mirror `_cross_version_check` at `scripts/verify_contract.py:319-385` for v1.1↔v1.2 forward/backward proof." All 12 file paths, the 10-point schema anatomy template, the exact `required[]`-invariance rule, and the V11→V12_ORDER mirror table are documented below with line numbers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema definitions (`audio_semantic`, `speakers`, `speaker-edits`) | Spec layer (`spec/schemas/`) | — | Schema files are the machine-checkable authority (CLAUDE.md "Two-tier authority"). Producer + consumer both bind to them. |
| Asset manifest additive fields | Spec layer (`spec/schemas/asset.schema.json`) | Producer (`scripts/export_asset.py`) | Schema declares `data.audio_semantic`/`data.speakers` as optional properties; producer's `build_asset_dict` conditionally emits them. |
| Schema-version literal | Producer (`scripts/export_asset.py:55`) | — | SINGLE source of truth. Pattern stays loose in schema (`^(0\|[1-9]\d*)...`); literal `"1.2"` locked in producer only (Pitfall 12 prevented). |
| Fixture data | Spec layer (`spec/fixtures/v1.2/`) | — | 12-file canonical example asset; consumer importers and bidirectional proof both depend on it. |
| Cross-version bidirectional proof | Test layer (`scripts/verify_contract.py`) | — | `_cross_version_check` + new `_recover_v11_schema` prove additive invariant. |
| Three-tier shape gate (MINIMAL/V11/V12) | Test layer (`spec/validate.py`) | — | `V11_ORDER` (lines 68-71) is the template for `V12_ORDER`. |
| SPEC.md prose + fidelity_disclaimer | Spec layer (`spec/SPEC.md`) | — | Human-readable overview; schemas win on conflict. `fidelity_disclaimer` belongs HERE (not in schema). |
| Speaker↔character consistency | Test layer (`verify_contract.py:_fixture_consistency_check`) | — | Where CONTEXT.md mandates `speakers.char_id ⊆ characters.id` check. |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (honor verbatim — these are not research recommendations, they are user decisions)

#### Phase-10-informed field shapes (the core of this phase)

- **`dialogue.emotion` = `type: string` (NOT enum).** SenseVoice self-consistency=100% is a label-stability proxy, NOT calibrated accuracy (DIA-04 ship-nullable+confidence). A closed 7-class enum would over-claim calibration we do not have. `emotion` is **nullable** + paired with `emotion_confidence: number` (0..1). The `fidelity_disclaimer` applies. *(Phase 10 evidence: ser_sensevoice_ep01.json methodology_ab; PROJECT.md DIA-04 row.)*
- **`instruments` field = OMITTED from v1.2.** MUS-04 deferred to v1.3. MERT-v1-95M has NO instrument classifier head; PANNs Cnn14 was zenodo-blocked. There is no instrument signal to contract yet. **This deviates from the ROADMAP Phase-11 dependency note** — that note predated the spike; the spike overrules it. Do NOT add an `instruments` field to `audio_semantic.schema.json` or `asset.schema.json`. *(Phase 10 evidence: mir_mert_ep01.json + mir_panns_ep01.json status=blocked; PROJECT.md MUS-04 defer row.)*
- **`dialogue.words` (word-level timestamps) = EXPERIMENTAL optional sub-field.** DIA-05 ship-experimental. `words: [{start, end, text, score}]` is OPTIONAL under each dialogue segment. A top-level `word_level_experimental: boolean` flag marks the whole `audio_semantic.json` when word-level is present. *(Phase 10 evidence: whisperx_align_ep01.json — boundary drift median 101.5ms, dense bucket 93.3%; aggregate per-word metric is a definition artifact.)*
- **`dialogue.events` = `array<string>` (SenseVoice 8-event tags: Speech/BGM/Applause/Laughter/Cry/Sneeze/Breath/Cough).** Free-string (not enum) for forward-compat.
- **`sfx` sub-object:** SenseVoice events + (future) PANNs 527-class. v1.2 = SenseVoice `events` projection (non-speech events). No PANNs multi-label yet.
- **`music` sub-object:** OMITTED in v1.2 (instruments deferred → no music content to contract). Reserve the key as a documented future slot in SPEC.md §5 but do NOT add to the schema.

#### Speakers + speaker-edits schemas (new ID space)

- **`speakers.schema.json`** — per-shot acoustic speaker turns using a NEW `^spk_[0-9]{3}$` ID space (NOT reusing `^char_[0-9]{3}$` — avoids identity-signal conflation per Phase 13 goal).
- **`speaker-edits.schema.json`** — HITL confirmed edits (mirror `registry-edits.schema.json` pattern): confirmed `spk_id → char_id` links + status. Phase 13 consumes this; Phase 11 just defines the contract.

#### Contract mechanics (mirror v1.1 Phase 5 — proven patterns)

- **`SCHEMA_VERSION = "1.2"`** single-source in `scripts/export_asset.py` (currently `"1.1"` at line 55). Schema pattern unchanged (`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`). Pure-additive minor bump.
- **`asset.schema.json` additive extension:** optional `data.audio_semantic` + `data.speakers` (both NOT in `required[]`). v1.0/v1.1 fixtures remain **byte-identical** when these are absent (CONTRACT-05 graceful-degrade proof — Pitfall 11 prevented).
- **3 new schemas:** `audio_semantic.schema.json`, `speakers.schema.json`, `speaker-edits.schema.json` — all draft 2020-12, `additionalProperties: false`.
- **12-file fixture** under `spec/fixtures/v1.2/`: copy v1.1's 10 files + add `audio_semantic.json` + `speakers.json`. Use ep01 Phase-10 spike results as realistic fixture content.
- **`verify_contract.py` bidirectional cross-version self-test:** forward (v1.1 fixture × v1.2 schema = 0 errors) + backward (v1.2 fixture × recovered-v1.1 schema = ONLY additionalProperties errors) + fixture-consistency (`speakers.char_id ⊆ characters.id` where characters present).
- **SPEC.md:** §4 Changelog `1.2` entry + §5 audio_semantic/speakers shapes + `fidelity_disclaimer` (AF-01 "perfect restoration" explicitly out-of-scope).

### Claude's Discretion

- Exact field names/casing within the locked shapes (mirror v1.1 conventions: snake_case, draft 2020-12, `$id`/`$schema`/`title`/`description` headers matching the 10 existing schemas).
- The `speakers.schema.json` internal structure (per-shot vs top-level turns) — pick whichever composes cleanly with Phase 13's HITL flow.
- Fixture content realism (use ep01 spike JSONs as source; synthesize shape-correct spk_NNN turns).
- Whether to factor a shared `_common` snippet for the nullable+confidence pattern (if v1.1 has a precedent, follow it; else inline).

### Deferred Ideas (OUT OF SCOPE — ignore completely)

- **`instruments` field** — v1.3 (pending real MIR classifier). Document in SPEC §4 as deferred.
- **PANNs 527-class SFX multi-label** — folded into future sfx expansion once PANNs is reachable.
- **word-level drift metric refinement** — Phase 12.
- **Live ML round-trip through the route** — Phase 12+.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (from REQUIREMENTS.md) | Research Support (where this finding lives) |
|----|------------------------------------|---------------------------------------------|
| CONTRACT-01 | `audio_semantic.json` sidecar schema — per-shot 三模态 (dialogue/music/sfx) + reproduction prompts；additive optional；`audio_analysis.json`/`transcript.json`/`prompts.json` 一字节不动 | **§ Architecture Patterns → Pattern 2 (3 new schema anatomy)** + **§ Code Examples → schema header template**. Music sub-object OMITTED per user_constraints. Instruments field OMITTED. |
| CONTRACT-02 | `speakers.json` sidecar schema (`spk_NNN → char_NNN|null`, `review_state`) + `speaker-edits.schema.json` (HITL round-trip, mirror registry-edits) | **§ Architecture Patterns → Pattern 2c/2d** + **§ Code Examples → registry-edits mirror template** (line-for-line). `^spk_[0-9]{3}$` regex is locked. |
| CONTRACT-03 | `SCHEMA_VERSION = "1.2"` producer-locked 单源；`validate.py` 三阶 shape gate (MINIMAL/V11/V12)；`verify_contract.py` v1.1↔v1.2 bidirectional cross-version + fixture-consistency | **§ Code Examples → SCHEMA_VERSION location (export_asset.py:55)** + **§ Pattern 4 (V11_ORDER mirror)** + **§ Pattern 5 (bidirectional proof + _recover_v11_schema)**. |
| CONTRACT-04 | SPEC §4 (changelog 1.1→1.2) + §5 新增 audio_semantic / speakers 形状 + `fidelity_disclaimer` 文档 | **§ Architecture Patterns → Pattern 6 (SPEC.md section structure)**. §4 Changelog 1.1 entry (lines 161-168) is the literal template. `fidelity_disclaimer` belongs in SPEC prose (two-tier authority), NOT in schema. |
| CONTRACT-05 | graceful-degrade —— 路由不可达/条件字段模型不达标 → sidecar 缺省（与 v1.0/v1.1 byte-identical）/ 字段 nullable；资产仍导出；`generator.warnings` 记原因 | **§ Common Pitfalls → Pitfall 11 (additive-only, byte-identical-absent)** + **§ Code Examples → export_asset.py conditional emission pattern (lines 312-330)**. The proof obligation is the forward direction of the bidirectional check (v1.0/v1.1 fixture × v1.2 schema = 0 errors). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.10+ (runtime in this workspace: Python 3.12.3, `/usr/bin/python3`). All schema/validator/fixture scripts are Python.
- **JSON I/O:** `indent=2` universally; `ensure_ascii=False` **always** for output containing Chinese. Many fixtures contain Chinese (e.g. `name: "少女"`, `name: "落叶"`). v1.2 fixture files MUST follow.
- **Docstrings:** All comments and docstrings in **Chinese (Simplified)**. Exception: short inline comments in English. Schema `title`/`description`/`$comment` fields are bilingual but lean Chinese narrative (see existing schemas for the established voice).
- **Brackets:** Stage prefix `print(f"[stage] ...")` for every progress line. The validators use `[valid]`/`[FAIL]`/`[valid-v11]`/`[FAIL-v11]` — Phase 11 adds `[valid-v12]`/`[FAIL-v12]` following the same pattern.
- **No package manifest:** No `pyproject.toml`, `requirements.txt`, `setup.py`. The only dependency is `jsonschema` (system-installed 4.26.0). Phase 11 installs NO new packages.
- **Naming:** `snake_case.py` for scripts, `kebab-case.schema.json` for schema filenames. Existing precedent: `registry-edits.schema.json`. So new file is `speaker-edits.schema.json` (NOT `speaker_edits`).
- **Two-tier authority:** Schemas = machine-checkable truth, SPEC.md = human overview. On conflict schema wins. `fidelity_disclaimer` lives in SPEC.md prose, NOT in schema `$comment`.
- **Subprocess-first:** Never import a sibling script as a module — `verify_contract.py` deliberately inlines its own `Draft202012Validator` instance rather than subprocess-ing to `spec/validate.py` (the latter's `SMOKE_SHAPES` excludes `asset` shape; subprocess-ing would let invalid manifests silently pass — see `scripts/export_asset.py:118-138` and `scripts/verify_contract.py:184-201`). Phase 11 honors this.
- **GSD Workflow Enforcement:** All file-changing work goes through `/gsd-execute-phase`. This is a planned phase so that's satisfied.

## Standard Stack

### Core (no new packages — all are existing project deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` | 4.26.0 (system) | `Draft202012Validator` for all schema validation | Already used by `spec/validate.py:26`, `scripts/export_asset.py:125`, `scripts/verify_contract.py:56`. **The only validation library this phase touches.** `[VERIFIED: import jsonschema in scripts/export_asset.py, scripts/verify_contract.py, spec/validate.py]` |
| Python stdlib `json` | 3.12 | Fixture I/O, schema loading | Universal project convention. |
| Python stdlib `argparse` | 3.12 | CLI for any new validator hook | Project pattern (every script). |
| Python stdlib `subprocess` | 3.12 | `git show v1.0:` / `git show v1.1:` for schema recovery in `_recover_v*_schema` | Already used by `scripts/verify_contract.py:289-296`. |
| Python stdlib `copy.deepcopy` | 3.12 | Programmatic-strip fallback in `_recover_v*_schema` | Already used by `scripts/verify_contract.py:299-316`. |
| Python stdlib `re` | 3.12 | ID-pattern assertions in `_fixture_consistency_check` | Already used by `scripts/verify_contract.py:474, 554`. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib.Path` | 3.12 | Repo-relative path resolution (`REPO = Path(__file__).parent.parent.resolve()`) | Mirror existing helper at `scripts/export_asset.py:44`, `scripts/verify_contract.py:61`. |
| `git` CLI | any | Cross-version schema recovery (`git show v1.0:...`, `git show v1.1:...`) | v1.0 and v1.1 tags both exist locally (verified). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `git show` for schema recovery | Hard-coded "known-added-keys" strip only | Strip-only already exists as fallback (`verify_contract.py:298-316`). Git show is PRIMARY (most real); strip is FALLBACK. Don't reverse this priority. |
| Adding a `pydantic` model | Existing `Draft202012Validator` | **REJECTED** — introduces a new dep, breaks the "no package manifest" convention. All v1.0/v1.1 schemas use pure JSON Schema; v1.2 follows. |
| Adding a `conda` env file | Nothing | **REJECTED** — `jsonschema` already system-installed; no manifest needed (per CLAUDE.md). |

**Installation:**

```bash
# NO INSTALL NEEDED. All deps are existing project runtime + stdlib.
# Verify pre-flight:
python3 -c "from jsonschema import Draft202012Validator; print('ok')"
git tag --list 'v1*'   # must list v1.0 + v1.1 (used by _recover_v1_schema / new _recover_v11_schema)
```

**Version verification (run before writing the Standard Stack table):**

```bash
$ python3 -c "import jsonschema; print(jsonschema.__version__)" 2>/dev/null
4.26.0
$ python3 --version
Python 3.12.3
$ git tag --list 'v1*'
v1.0
v1.1
$ python3 -c "from jsonschema import Draft202012Validator; print('available')"
available
```

## Package Legitimacy Audit

> **This phase installs ZERO external packages.** No `pip install`, no `npm install`, no `cargo add`. All work reuses existing system Python 3.12 + jsonschema 4.26.0 + git CLI. The Package Legitimacy Gate therefore has nothing to audit. Slopcheck step skipped as there are no packages to run it on.

*If for any reason a package install creeps into a plan during PLANNING, the planner MUST stop and add a `checkpoint:human-verify` task before that install — this research explicitly did NOT audit any package.*

## Architecture Patterns

### System Architecture Diagram (Phase 11 work product flow)

```
                    ┌───────────────────────────────────────┐
                    │  Phase 10 spike outcomes (LOCKED)     │
                    │  - ser_sensevoice_ep01.json           │
                    │  - mir_mert_ep01.json (no instr head) │
                    │  - whisperx_align_ep01.json (drift)   │
                    └───────────────────┬───────────────────┘
                                        │
                                        ▼
            ┌───────────────────────────────────────────────────┐
            │  CONTEXT.md decisions (frozen shapes)             │
            │  - instruments OMITTED                            │
            │  - emotion type:string nullable + confidence      │
            │  - word_level_experimental flag                   │
            │  - spk_NNN new ID space                           │
            └───────────────────────┬───────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
   ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │ 3 new schemas   │    │ asset.schema     │    │ SCHEMA_VERSION   │
   │ - audio_semantic│    │ additive ext:    │    │ "1.1" → "1.2"    │
   │ - speakers      │    │ data.audio_*     │    │ single-source    │
   │ - speaker-edits │    │ data.speakers    │    │ export_asset:55  │
   └────────┬────────┘    └────────┬─────────┘    └────────┬─────────┘
            │                      │                       │
            ▼                      ▼                       ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ spec/fixtures/v1.2/ (12 files = v1.1's 10 + 2 new)             │
   │ - audio_semantic.json (from spike ep01 data)                   │
   │ - speakers.json (synthetic-but-shape-correct spk_NNN)          │
   └────────────────────────────────┬───────────────────────────────┘
                                    │
                                    ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ 3 validation gates (all must GREEN):                           │
   │                                                                │
   │ 1. spec/validate.py — V12_ORDER 12-shape gate                  │
   │ 2. scripts/verify_contract.py — _cross_version_check extended: │
   │    FORWARD:   v1.1 fixture × v1.2 schema  = 0 errors           │
   │    BACKWARD:  v1.2 fixture × rec-v1.1 schema = ONLY addProp    │
   │    speakers.char_id ⊆ characters.id  (new consistency check)   │
   │ 3. byte-identical-absent proof (Pitfall 11)                    │
   └────────────────────────────────┬───────────────────────────────┘
                                    │
                                    ▼
                   ┌────────────────────────────────┐
                   │ spec/SPEC.md prose             │
                   │ - §4 Changelog 1.2 entry       │
                   │ - §5 audio_semantic / speakers │
                   │ - fidelity_disclaimer          │
                   └────────────────────────────────┘
```

A reader can trace the primary use case (CONTRACT-03 bidirectional proof) by following: spike JSONs → CONTEXT decisions → schemas → fixture → 3 gates → all GREEN = contract locked.

### Recommended Project Structure (additive only — NO new directories)

```
spec/
├── schemas/                              # 10 existing + 3 new = 13 schemas
│   ├── asset.schema.json                 # EXTENDED (additive: data.audio_semantic + data.speakers)
│   ├── audio_analysis.schema.json        # UNCHANGED (byte-identical)
│   ├── transcript.schema.json            # UNCHANGED
│   ├── frames.schema.json                # UNCHANGED
│   ├── shots.schema.json                 # UNCHANGED
│   ├── prompts.schema.json               # UNCHANGED
│   ├── characters.schema.json            # UNCHANGED
│   ├── props.schema.json                 # UNCHANGED
│   ├── registry.schema.json              # UNCHANGED
│   ├── registry-edits.schema.json        # UNCHANGED (template for speaker-edits)
│   ├── audio_semantic.schema.json        # NEW (Phase 11)
│   ├── speakers.schema.json              # NEW (Phase 11)
│   └── speaker-edits.schema.json         # NEW (Phase 11)
├── fixtures/
│   ├── minimal/                          # UNCHANGED (v1.0 substrate, 6 files)
│   ├── v1.1/                             # UNCHANGED (10 files)
│   └── v1.2/                             # NEW — copy v1.1's 10 + add 2 = 12 files
│       ├── asset.json                    # schema_version="1.2" + data.audio_semantic + data.speakers
│       ├── (10 v1.1 files copied verbatim)
│       ├── audio_semantic.json           # NEW — realistic ep01 spike content
│       └── speakers.json                 # NEW — synthetic-but-shape-correct spk_NNN turns
├── validate.py                           # EXTENDED (+ V12_FIXTURE_DIR/MAP/ORDER + validate_v12)
├── README.md                             # EXTENDED (v1.2 section)
└── SPEC.md                               # EXTENDED (§4 1.2 entry + §5 shapes + fidelity_disclaimer)

scripts/
├── export_asset.py                       # EXTENDED (SCHEMA_VERSION="1.2" + conditional data.* emission)
└── verify_contract.py                    # EXTENDED (_recover_v11_schema + forward/backward v1.1↔v1.2 + speakers⊆characters check)
```

**No `__init__.py`, no new package structure, no `requirements.txt`** — the project has none and Phase 11 doesn't add any (per CLAUDE.md "Notable Architecture Choices").

### Pattern 1: Schema Anatomy Template (10-point header — copy verbatim, change only the title/description)

Every one of the 10 existing schemas opens with the same 10-line header. The 3 new schemas MUST match this anatomy exactly (any deviation breaks consumer TS type generation expectations and the "two-tier authority" invariant).

**Verified template** (extracted from `spec/schemas/characters.schema.json:1-12` and `registry-edits.schema.json:1-10`):

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/<NAME>.schema.json",
  "draft": "2020-12",
  "title": "<Chinese narrative title — what this schema is>",
  "description": "<English+Chinese mixed: producer path → consumer path. Always end with: '严格遵守 v1.0 的 strict-schema × lenient-consumer 原则:schema 校验时 additionalProperties:false 全程生效。'>",
  "$comment": "<Cross-reference Pitfalls by number: Pitfall 5/7/17/etc. Document the non-obvious design choices. Author intent.>",
  "type": "<object|array>",
  "additionalProperties": false,
  "required": [<minimal required keys — never include optional additive fields>],
  "properties": { ... }
}
```

**The 4 mandatory fields in EVERY new schema (cross-verified against all 10 existing schemas):**

| Header field | Value | Why |
|--------------|-------|-----|
| `$schema` | `"https://json-schema.org/draft/2020-12/schema"` | Draft 2020-12 — the version `Draft202012Validator` validates against. |
| `$id` | `"https://kais.shot-timeline/spec/schemas/<NAME>.schema.json"` | Canonical URI; used by `$ref` resolution if added later. The host `kais.shot-timeline` is fictional but consistent across all 10 schemas — DON'T change it. |
| `draft` | `"2020-12"` | Redundant with `$schema` but every existing schema has it — keep for consistency. |
| `additionalProperties: false` | (at every object level, including nested) | The strict-schema half of the strict/lenient contract (SPEC.md §4). |

### Pattern 2: Three new schemas — concrete shape recommendations

> **Planner's note:** These are recommendations within the user-locked shapes. CONTEXT.md grants discretion on internal structure; the shapes below are the most natural fits to (a) the existing v1.1 anatomy, (b) Phase 12 producer's expected route response, (c) Phase 13 SPEAKER-01 HITL flow. Departures are OK if the user-locked constraints (especially the `spk_NNN` regex) are honored.

#### Pattern 2a: `audio_semantic.schema.json` — top-level object keyed by shot_id

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/audio_semantic.schema.json",
  "draft": "2020-12",
  "title": "音频语义深化（per-shot 三模态 + 分层复现 prompt）",
  "description": "Canonical v1.2 audio sidecar — per-shot dialogue/music/sfx sub-objects + reproduction.{tts,music_gen,foley} layered prompts. Producer (Phase 15) writes audio_semantic.json after route-host round-trip; consumers (Phase 16 HTML gallery, Phase 17 canvas) read it to render modality chips + reproduction panels. 严格遵守 v1.0 的 strict-schema × lenient-consumer 原则。v1.2 additive: absent on v1.0/v1.1 assets (byte-identical; asset.schema.json#data.audio_semantic is OPTIONAL).",
  "$comment": "Phase 10 spike outcomes (LOCKED in PROJECT.md): (1) instruments field OMITTED — MERT-v1-95M has no instrument classifier head; PANNs Cnn14 zenodo-blocked at spike time; MUS-04 deferred to v1.3 (do NOT add instruments anywhere in this schema). (2) emotion is type:string NOT enum — SenseVoice self_consistency=100% is a label-stability proxy, NOT calibrated accuracy; emotion is NULLABLE + paired with emotion_confidence:0..1; a closed enum would over-claim calibration. (3) word_level_experimental top-level flag gates word-level timestamps (segment-level is the SLA path; WhisperX boundary drift median=101.5ms but aggregate per-word drift is a metric-definition artifact). music sub-object OMITTED in v1.2 (instruments absent → no music content to contract); future slot documented in SPEC §5 only. sfx carries SenseVoice non-speech events (PANNs 527-class folded into future expansion). fidelity_disclaimer lives in SPEC.md (two-tier authority).",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "shots"],
  "properties": {
    "schema_version": { "type": "string", "pattern": "^(0|[1-9]\\d*)(\\.(0|[1-9]\\d*))?$" },
    "word_level_experimental": {
      "type": "boolean",
      "description": "Top-level flag: true when ANY shot.dialogue.words[] is populated. Consumers (canvas/HTML) read this first and may graceful-degrade segment-only when false."
    },
    "shots": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["shot_id"],
        "properties": {
          "shot_id": { "type": "integer", "minimum": 1 },
          "start_sec": { "type": "number", "minimum": 0 },
          "end_sec": { "type": "number", "minimum": 0 },
          "duration": { "type": "number", "minimum": 0 },
          "dialogue": {
            "type": "object",
            "additionalProperties": false,
            "required": [],
            "properties": {
              "text": { "type": "string" },
              "spk_id": { "type": ["string", "null"], "pattern": "^spk_[0-9]{3}$" },
              "emotion": {
                "type": ["string", "null"],
                "description": "Free-string emotion label (SenseVoice emits HAPPY/ANGRY/NEUTRAL/SAD/emo_unk/etc.). NOT enum — calibrated-estimate, NOT accuracy-validated. NULLABLE."
              },
              "emotion_confidence": {
                "type": ["number", "null"],
                "minimum": 0, "maximum": 1,
                "description": "Confidence in [0,1]. SenseVoice self_consistency_pct/100. Populated when emotion is non-null; null when emotion absent."
              },
              "events": {
                "type": "array",
                "items": { "type": "string" },
                "description": "SenseVoice 8-event tags: Speech/BGM/Applause/Laughter/Cry/Sneeze/Breath/Cough. Free-string for forward-compat."
              },
              "words": {
                "type": "array",
                "items": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": ["start", "end", "text"],
                  "properties": {
                    "start": { "type": "number", "minimum": 0 },
                    "end": { "type": "number", "minimum": 0 },
                    "text": { "type": "string" },
                    "score": { "type": "number", "minimum": 0, "maximum": 1 }
                  }
                },
                "description": "Word-level timestamps (WhisperX wav2vec2 align). EXPERIMENTAL — gated by top-level word_level_experimental flag. Per-word drift metric is a definition artifact (Phase 12 refines)."
              }
            }
          },
          "sfx": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "events": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Non-speech SenseVoice events (subset of 8-tag set: BGM/Applause/Laughter/Cry/Sneeze/Breath/Cough). Speech is under dialogue.events."
              },
              "description": { "type": "string", "description": "Free-text NL description for foley reproduction prompt input." }
            }
          },
          "reproduction": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "tts": { "$ref": "#/$defs/repro_prompt" },
              "music_gen": { "$ref": "#/$defs/repro_prompt" },
              "foley": { "$ref": "#/$defs/repro_prompt" }
            },
            "description": "Layered reproduction prompts (model-agnostic NL — no NC weight embedding). Each layer nullable + carries confidence."
          }
        }
      }
    }
  },
  "$defs": {
    "repro_prompt": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "required": ["text"],
      "properties": {
        "text": { "type": "string", "minLength": 1, "description": "NL prompt for the named generator family." },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "fidelity_disclaimer": { "type": "string", "description": "Per-prompt fidelity disclaimer (e.g. 'TTS ~70% similar'; AF-01 mitigation)." }
      }
    }
  }
}
```

**Planner's note on discretion:** The `reproduction` shape above uses a `$defs/repro_prompt` ref for DRY. If the planner prefers inline-repeated shape (simpler, matches Phase 5 style which avoided `$defs` except in `characters`/`props` for `looks`/`states`), inline is also valid. CONTEXT.md grants this discretion explicitly.

#### Pattern 2b: `speakers.schema.json` — top-level object (recommended over per-shot array)

**Why top-level rather than per-shot:** Phase 13 SPEAKER-02 confirmed-only apply gate needs the **full speaker inventory** in one place to (a) iterate speakers in deterministic order, (b) check char_id uniqueness, (c) total_speech_sec aggregation. A per-shot array would require reduce-step in apply. Mirror `registry.schema.json`'s top-level `{clusters: [...]}` shape.

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/speakers.schema.json",
  "draft": "2020-12",
  "title": "说话人注册表（声学 spk_NNN + 可选 char_NNN 映射）",
  "description": "Canonical v1.2 speaker registry — per-shot acoustic turns using ^spk_[0-9]{3}$ ID space (NEW, not reusing ^char_[0-9]{3}$ to avoid identity-signal conflation). Producer (Phase 13 registry/link_speakers.py after HITL apply) writes speakers.json; consumer (Phase 16 HTML gallery + Phase 17 canvas) reads it to render speaker→character chips. 严格遵守 v1.0 的 strict-schema × lenient-consumer 原则。v1.2 additive: absent on v1.0/v1.1 assets (byte-identical; asset.schema.json#data.speakers is OPTIONAL).",
  "$comment": "Pitfall 17 (prompt dangling) extension: spk_id once confirmed is immutable (mirror char_/prop_ convention). Pitfall 7 (review_state gating): only 'confirmed' mappings flow to downstream (Phase 13 hard gate mirrors apply_edits.py). char_id NULLABLE — 旁白/群杂 speakers have no character mapping (DIA-03). When char_id is non-null, MUST resolve to a characters.json#id with review_state='confirmed' (verify_contract.py fixture-consistency check enforces this). Phase 11 only DEFINES the contract; Phase 13 implements the HITL flow that populates confirmed entries. Speaker identity is ACOUSTIC (pyannote/WhisperX diarize embedding), distinct from visual identity (DINOv2 char_ embedding) — the two ID spaces are deliberately disjoint.",
  "type": "object",
  "additionalProperties": false,
  "required": ["speakers"],
  "properties": {
    "speakers": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["spk_id", "review_state"],
        "properties": {
          "spk_id": { "type": "string", "pattern": "^spk_[0-9]{3}$" },
          "char_id": {
            "type": ["string", "null"],
            "pattern": "^char_[0-9]{3}$",
            "description": "Linked character ID (nullable for 旁白/群杂). MUST resolve to a confirmed characters.json entry when non-null."
          },
          "total_speech_sec": { "type": "number", "minimum": 0 },
          "review_state": {
            "enum": ["proposed", "confirmed", "rejected"],
            "description": "HITL gating. Only 'confirmed' flows downstream (Pitfall 7)."
          },
          "turns": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["shot_id", "start_sec", "end_sec"],
              "properties": {
                "shot_id": { "type": "integer", "minimum": 1 },
                "start_sec": { "type": "number", "minimum": 0 },
                "end_sec": { "type": "number", "minimum": 0 }
              }
            }
          }
        }
      }
    }
  }
}
```

#### Pattern 2c: `speaker-edits.schema.json` — line-for-line mirror of `registry-edits.schema.json`

The existing `registry-edits.schema.json` is the **proven HITL round-trip template** — Phase 13 SPEAKER-02's `gen_speaker_review.py` → `link_speakers.py` flow will follow the exact same pattern. The new file should be a near-clone with these substitutions:

| registry-edits field | speaker-edits equivalent |
|-----------------------|----------------------------|
| `^(char\|prop)_[0-9]{3}$` (cluster_id) | `^spk_[0-9]{3}$` (spk_id) |
| `merge_groups` | `merge_groups` (speakers merged by acoustic similarity) |
| `splits` (member_partitions) | `splits` (analogous — turn_indexes partition) |
| `renames` (display name) | OMIT (speakers don't have display names; they ARE their spk_id) OR keep as `display_label` if Phase 13 wants a free-text alias |
| `type_overrides` (char↔prop) | OMIT (speakers have no type prefix ambiguity) |
| `confirm_ids` (→ characters/props) | `confirm_ids` (→ speakers.json with char_id populated) |
| `reject_ids` | `reject_ids` (soft-delete, ID preserved — Pitfall 17) |
| Plus NEW: `link_mappings` | `{spk_id: char_id}` map — the SPEAKER-01 core use case. Distinct field because links are not confirmations. |

**The header `$comment` should mirror registry-edits.schema.json:7** almost verbatim:
- Cite Pitfall 5 (idempotency via fixed apply order)
- Cite Pitfall 7 (confirmed-only gate downstream)
- Cite Pitfall 17 (ID immutability — once confirmed, spk_id is forever reserved)
- Document T-07-01 (path-traversal: `^spk_[0-9]{3}$` rejects any malformed ID)
- Document T-07-02 (link_speakers.py MUST `Draft202012Validator` pre-validate before apply)
- "All fields optional — empty edits `{}` schema-valid"

### Pattern 3: asset.schema additive extension (THE critical pattern — Pitfall 11 prevention)

**Verified v1.1 additive structure** (extracted by comparing `git show v1.0:spec/schemas/asset.schema.json` vs current):

```python
# Verified via: python3 -c "..." (see Environment Availability)
v1.0 data.* keys:     ['audio_analysis', 'frames', 'prompts', 'shots', 'transcript']
v1.1 data.* keys:     ['audio_analysis', 'characters', 'frames', 'prompts', 'props', 'shots', 'transcript']
v1.1 added:           ['characters', 'props']
v1.0 data.required:   ['shots', 'audio_analysis', 'transcript', 'frames', 'prompts']
v1.1 data.required:   ['shots', 'audio_analysis', 'transcript', 'frames', 'prompts']  # UNCHANGED
```

**Phase 11 MUST extend by adding to `properties.data.properties` (NOT to `properties.data.required`):**

```jsonc
// EXISTING (asset.schema.json:113-155) — DO NOT TOUCH required[]:
"data": {
  "type": "object",
  "additionalProperties": false,
  "required": ["shots", "audio_analysis", "transcript", "frames", "prompts"],
  "properties": {
    /* ... existing 5 required + characters + props (v1.1 additive) ... */
    
    // ADD (Phase 11):
    "audio_semantic": {
      "type": "string",
      "pattern": "^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$",
      "description": "v1.2 additive (OPTIONAL — absent on v1.0/v1.1 assets). Relative path to audio_semantic.json (the canonical per-shot 三模态 + reproduction produced by Phase 15). Emitted only when route-host round-trip succeeded; older assets omit it and still validate (graceful-degrade, CONTRACT-05)."
    },
    "speakers": {
      "type": "string",
      "pattern": "^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$",
      "description": "v1.2 additive (OPTIONAL — absent on v1.0/v1.1 assets). Relative path to speakers.json (canonical confirmed speaker registry produced by Phase 13 HITL link_speakers). Same emission rule as characters/props."
    }
  }
}
```

**Pitfall 11 prevention rule (load-bearing):** the new keys go ONLY in `properties.data.properties` and NOWHERE in `required[]` (anywhere — root, data, generator, anywhere). The instant any new key enters a `required[]` array, the v1.0 minimal fixture and v1.1 fixture both break their forward-compat check. The forward proof (v1.x fixture × v1.(x+1) schema = 0 errors) catches this in the bidirectional test (Pattern 5 below).

### Pattern 4: spec/validate.py — V12_ORDER mirror of V11_ORDER

**Verified existing structure** (`spec/validate.py:51-71`):

```python
V11_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.1"
V11_FIXTURE_MAP = {
    "asset": "asset.json",
    "shots": "shots.json",
    # ... 10 entries ...
    "registry": "registry.draft.json",
    "registry-edits": "registry.edits.json",
}
V11_ORDER = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry", "registry-edits",
]
```

**Phase 11 adds the v1.2 mirror — exact diff:**

```python
# ADD after V11_ORDER (around line 72):
V12_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.2"
V12_FIXTURE_MAP = {
    # Copy all 10 v1.1 entries verbatim (same filenames; v1.2 fixture reuses the same substrate files):
    "asset": "asset.json",
    "shots": "shots.json",
    "audio_analysis": "audio_analysis.json",
    "transcript": "transcript.json",
    "frames": "frames.json",
    "prompts": "prompts.json",
    "characters": "characters.json",
    "props": "props.json",
    "registry": "registry.draft.json",
    "registry-edits": "registry.edits.json",
    # 2 NEW v1.2 shapes:
    "audio_semantic": "audio_semantic.json",
    "speakers": "speakers.json",
    # speaker-edits deferred to Phase 13 (no fixture until HITL flow exists)
}
V12_ORDER = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry", "registry-edits",
    "audio_semantic", "speakers",
]
```

**Then add `validate_v12()` mirroring `validate_v11()` (lines 119-151) verbatim**, changing only:
- the directory/map constants
- the print prefix `[valid-v12]` / `[FAIL-v12]` (mirror v1.1 → v1.2)
- the function name

**Then extend `main()` (lines 198-242):** add `v12_failures = validate_v12()` between v11 and smoke; add `+ v12_failures` to `total_strict_failures`. Update the closing print.

**Fixture count assertions:** minimal 6, v1.1 10, v1.2 12, smoke ≥5.

### Pattern 5: verify_contract.py — bidirectional cross-version proof

**Verified existing `_cross_version_check` structure** (`scripts/verify_contract.py:319-385`):

```
(a) FORWARD: spec/fixtures/minimal × v1.1-extended schemas → 0 errors
(b) BACKWARD: spec/fixtures/v1.1 × recovered v1 schemas → only additionalProperties errors
```

**Recovered-schema mechanism** (`scripts/verify_contract.py:275-316`): `_recover_v1_schema(shape)` does:
1. PRIMARY: `subprocess.run(["git", "show", f"v1.0:spec/schemas/{shape}.schema.json"], ...)` → parse JSON
2. FALLBACK: `copy.deepcopy` the current schema, then `.pop()` the known-added keys (asset: data.characters/props + media.characters/props; prompts: character_refs/prop_refs)

**Phase 11 adds the v1.1→v1.2 mirror — 4-part change:**

1. **Add `_recover_v11_schema(shape)`** — line-for-line clone of `_recover_v1_schema`, changing:
   - git ref: `v1.0:spec/schemas/...` → `v1.1:spec/schemas/...`
   - fallback strip keys: add `audio_semantic` + `speakers` to the asset strip list (data + media — though v1.2 doesn't add media.* for these, just data.*)
   
   *Alternative cleaner approach:* parameterize — `_recover_schema(shape, version="1.0")`. The planner has discretion but parameterization is preferred (DRY, fewer copy-paste bugs).

2. **Extend `_cross_version_check` to add 2 new passes:**

```
(c) FORWARD v1.1→v1.2: spec/fixtures/v1.1 × current (v1.2-extended) schemas → 0 errors
    Loop over v1.1 fixture shapes that v1.2 EXTENDED (asset only — speakers/audio_semantic
    are new shapes with no v1.1 instance to test). Assert 0 errors.
    
(d) BACKWARD v1.2→v1.1: spec/fixtures/v1.2 × recovered-v1.1 schemas → ONLY additionalProperties
    Loop over v1.2-extended shapes (asset). Assert non-addProp errors = 0.
```

**Critical detail:** existing `_cross_version_check` already covers v1.0↔v1.1. Phase 11 ADDS v1.1↔v1.2 — does NOT replace. Both proofs must remain green.

3. **Extend `validate_eight_shapes` (lines 204-271) to handle the 3 new shapes** as optional (gated on file existence, just like the v1.1 shapes already are). The `EIGHT_SHAPES` list (lines 78-82, actually 9 elements — name is legacy) becomes 12 elements:
   ```python
   ALL_SHAPES = [
       "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
       "characters", "props", "registry", "registry-edits",
       "audio_semantic", "speakers",  # v1.2 (speaker-edits deferred to Phase 13)
   ]
   # Keep EIGHT_SHAPES / SIX_SHAPES as backward-compat aliases for legacy docs.
   ```
   For new shapes, `data.<shape>` lookup in the manifest continues to govern (mirror lines 245-263: absent → skip).

4. **Extend `_fixture_consistency_check` (lines 388-488) with `speakers.char_id ⊆ characters.id`**:

```python
# ADD inside _fixture_consistency_check (or a new v1.2 variant):
v12 = REPO / "spec" / "fixtures" / "v1.2"
if v12.is_dir():
    spk_path = v12 / "speakers.json"
    if spk_path.is_file():
        speakers = json.loads(spk_path.read_text(encoding="utf-8"))
        # Reuse chars from v1.1 fixture (copied verbatim into v1.2)
        chars_in_v12 = {c.get("id") for c in json.loads((v12/"characters.json").read_text(encoding="utf-8"))}
        for spk in speakers.get("speakers", []):
            cid = spk.get("char_id")
            if cid is not None and cid not in chars_in_v12:
                failures.append(
                    f"speakers.json {spk.get('spk_id')}: char_id {cid!r} "
                    f"not in v1.2 characters.json IDs (Pitfall 17 — speaker dangling)")
            # spk_id pattern check
            sid = spk.get("spk_id")
            if not (isinstance(sid, str) and re.match(r"^spk_[0-9]{3}$", sid)):
                failures.append(f"speakers.json: spk_id malformed: {sid!r}")
```

### Pattern 6: SPEC.md section structure (where each deliverable lives)

**Verified §4 Changelog format** (`spec/SPEC.md:157-168`):

The `1.1` entry at line 161 is the literal template for the `1.2` entry. Structure:
```
- **<DATE> — `<VERSION>`(<flavor>)** — <one-line summary>. <Pure-additive claim>. <"Pitfall N prevented" reference>.变更:
  - **<N> 个新 schema**:<list>
  - **`<existing>.schema.json` additive**:<what was added, with `required[]` byte-identical callout>
  - **`schema_version` pattern 不变**(<pattern>)— version literal locked at `<file>:<line>`, NOT schema const.
  - **向后兼容**:<fixture counts green; verify_contract.py bidirectional proof status>
  - (Optional phase-specific bullets)
```

**The 1.2 entry MUST mention:**
- Pure-additive claim (`Pitfall 11 prevented` explicit)
- 3 new schemas: `audio_semantic.schema.json`, `speakers.schema.json`, `speaker-edits.schema.json`
- `asset.schema.json` additive: `data.audio_semantic` + `data.speakers` (NOT in `required[]`)
- `schema_version` pattern unchanged + literal locked at `scripts/export_asset.py:55`
- Phase-10-informed deviations documented as rationale:
  - **instruments field OMITTED** (MUS-04 defer — MERT no classifier + PANNs zenodo-blocked)
  - **emotion type:string nullable + emotion_confidence** (SenseVoice self-consistency is stability proxy, NOT accuracy)
  - **word_level_experimental flag** (WhisperX drift metric-definition artifact)
- Backward-compat proof status: v1.0 minimal still 6/6 green, v1.1 still 10/10, v1.2 12/12, all three bidirectional proofs GREEN

**Verified §5 shapes format** (`spec/SPEC.md:172-420` for v1.0/v1.1 shapes):

Each shape follows the same 4-block structure:
1. **`**Producer:**` `<file:func>`** line**
2. **`**顶层形状:**` <JSON value kind description>** line
3. **Field table** with columns `| Field | Type | Required | Notes |`
4. **`**最小片段:**`** code block with realistic JSON
5. **`Reference schema:` `<path>`** closing line

For Phase 11, add **§5.8 Audio Semantic (v1.2)** + **§5.9 Speakers (v1.2)** following this exact template. The §5 intro paragraph (line 176) already says "v1.1 新增 §5.6 Characters + §5.7 Props"; Phase 11 adds a parallel sentence: "v1.2 新增 §5.8 Audio Semantic + §5.9 Speakers (均 optional — 仅 route-host round-trip 跑过且条件字段达标后 emit)".

**`fidelity_disclaimer` placement:** a new **§10 Fidelity Disclaimer (v1.2)** section, OR a sub-section of §4 right after the Changelog. It documents:
- AF-01 explicitly out-of-scope ("perfectly reconstruct"/"exact restoration" forbidden in README/SPEC)
- Per-modality fidelity estimates: TTS ~70%, music ~60-75%, foley ~80%
- Emotion = calibrated estimate (not accuracy)
- Word-level = experimental (segment-level is SLA)
- Instruments = absent

The `fidelity_disclaimer` belongs in SPEC **prose** (two-tier authority: schema = machine-checkable truth, SPEC = human overview). DO NOT add a `fidelity_disclaimer` field to schemas — it would either be a non-machine-checkable string in `additionalProperties:false` strict schemas (rejected) or duplicated across every shape. Prose is the right home.

### Anti-Patterns to Avoid

- **Adding any new key to ANY `required[]` array.** This is Pitfall 11 in literal form — it would break the v1.0/v1.1 fixtures' forward-compat proof. The bidirectional test catches this immediately, but the trap is easy to fall into if you copy an existing additive block and miss the `required[]` exclusion. **Mitigation:** every additive pattern in this research doc explicitly says `required[] UNCHANGED`; the plan-checker should reject any task that edits a `required[]`.
- **Duplicating SCHEMA_VERSION anywhere other than `export_asset.py:55`.** The "single-source" rule is structural (CLAUDE.md, SPEC.md §4). Hardcoding `"1.2"` in `validate.py` or `verify_contract.py` or SPEC.md prose creates a second source that drifts on the next bump. **Mitigation:** SPEC.md may quote the literal once in the Changelog entry but MUST link to `export_asset.py:55` as the source of truth.
- **Adding `fidelity_disclaimer` as a schema field.** Schema fields must be machine-checkable. A disclaimer string belongs in prose. **Mitigation:** only emit it in SPEC.md §4/§10 prose and in the `reproduction.<layer>.fidelity_disclaimer` per-prompt field (which IS machine-checkable as a string field that downstream UIs render).
- **Reusing `^char_[0-9]{3}$` for speakers.** Phase 13 SPEAKER-01 explicitly uses a NEW `^spk_[0-9]{3}$` space to avoid identity-signal conflation. The two ID spaces are deliberately disjoint. **Mitigation:** the regex is locked in CONTEXT.md; the planner has no discretion here.
- **Adding `instruments` field despite the user_constraints.** The ROADMAP Phase-11 dependency note is STALE — it predated the spike. Do NOT add `instruments` anywhere in v1.2. **Mitigation:** the planner must reject any task that introduces `instruments` (or `instrument_labels`, `instruments_detected`, etc.) into schemas or SPEC.
- **Subprocess-ing to `spec/validate.py` from `scripts/verify_contract.py`.** Its `SMOKE_SHAPES` (line 49) excludes the `asset` shape — subprocess-ing lets invalid manifests silently pass. Both files inline their own `Draft202012Validator` for the asset schema. **Mitigation:** mirror the existing inline pattern (`verify_contract.py:184-201`).
- **Tagging v1.2 before contract is locked.** The `_recover_v11_schema()` mechanism depends on `v1.1` git tag pointing at the v1.1 final state. If v1.2 introduces a v1.2 tag, it must point at the v1.2 final state (post-Phase-17). Do NOT tag mid-Phase-11.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema recovery for backward test | Hand-maintained "v1.1 schema copy" directory | `git show v1.1:spec/schemas/<shape>.schema.json` (mirror `verify_contract.py:289-296`) | The git tag is the immutable v1.1 truth; a copied directory drifts the moment v1.1 is patched. Tag is verified to exist (`git tag --list 'v1*'` shows both v1.0 and v1.1). |
| ID pattern validation | Custom regex in `_fixture_consistency_check` | Reuse existing `re.match(r"^(char\|prop)_[0-9]{3}$", cid)` (verify_contract.py:474) — extend to `^spk_[0-9]{3}$` | The existing pattern is battle-tested; adding one alt to the alternation is the surgical change. |
| Schema-version pattern | New `pattern` in any v1.2 schema | Reuse `^(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$` from asset.schema.json:14 | The pattern is documented in SPEC.md §4 and load-bearing for the "semver-lite" rule. Don't change it. |
| Path-traversal negative-lookahead | Hand-rolled `[^.][^.]` etc. | Reuse `^(?!.*\\.\\.)[^:*?\"<\|]+\\.json$` from asset.schema.json:121 (or the equivalent png pattern for media) | Anti-traversal patterns are subtle; the existing 4 patterns (json path, video, stems, png) cover every case Phase 11 needs. |
| Atomic write (tmp + os.replace) | Direct `open(... 'w')` | Mirror `export_asset.py:522-525` | Avoids partial-write state being read by downstream — established project pattern. |
| UTF-8 JSON dump for Chinese content | Default `json.dump` | `json.dump(obj, f, indent=2, ensure_ascii=False)` always | CLAUDE.md "JSON I/O Conventions" — v1.2 fixtures will contain Chinese (`emotion: "HAPPY"`, dialogue text, fidelity disclaimers in Chinese). |
| Bidirectional test framework | New harness | Extend existing `_cross_version_check` (verify_contract.py:319-385) | The existing test already does v1.0↔v1.1; Phase 11 just adds a v1.1↔v1.2 pass. No new file, no new abstractions. |

**Key insight:** Phase 11 is a "force-multiply the existing v1.1 patterns" phase, NOT a "build new infrastructure" phase. Every mechanism the planner needs already exists in v1.1 with battle-tested line numbers. The Don't-Hand-Roll list above is exhaustive for this phase.

## Common Pitfalls

### Pitfall 11: byte-identical-absent (additive-only invariant)

**What goes wrong:** A new optional field is added to `properties` but the producer accidentally starts emitting it as a default empty value (`"audio_semantic": null`) even when the route is down. This makes "route down" assets differ from v1.0/v1.1 assets, breaking the byte-identical-absent proof.

**Why it happens:** The natural lazy-default in `build_asset_dict` is `data_block["audio_semantic"] = None`. This is wrong — it emits the key.

**How to avoid:** Mirror `export_asset.py:312-317` (Phase 7 conditional emission pattern):

```python
# Correct (mirror lines 312-317):
audio_semantic_path = os.path.join(work_dir, "audio_semantic.json")
if os.path.isfile(audio_semantic_path):
    data_block["audio_semantic"] = "audio_semantic.json"
speakers_path = os.path.join(work_dir, "speakers.json")
if os.path.isfile(speakers_path):
    data_block["speakers"] = "speakers.json"
# WRONG (would emit empty key):
# data_block["audio_semantic"] = "audio_semantic.json" if os.path.isfile(...) else None
```

**Warning signs:** Forward proof fails (`v1.0 fixture × v1.2 schema = N errors`) — but only if the new key accidentally lands in `required[]`. The byte-identical-absent requirement is STRONGER than the schema requires: schema says "absent is legal"; spec says "absent when content absent". The bidirectional test only catches the former; an additional "byte-diff against golden v1.1 fixture" check is needed for the latter. **The planner should add a byte-diff task.**

### Pitfall 12: schema change without version bump

**What goes wrong:** A schema is extended but `SCHEMA_VERSION` literal isn't bumped.

**Why it happens:** SCHEMA_VERSION lives in ONE place (`export_asset.py:55`); easy to miss when editing schemas.

**How to avoid:** The structural mitigation is already in place — single-source at `export_asset.py:55`. The Phase 11 plan should have ONE task that does the literal bump and that task should reference this exact line. `[VERIFIED: export_asset.py:55 — currently `SCHEMA_VERSION = "1.1"`]`

**Warning signs:** A v1.2 fixture asset.json with `"schema_version": "1.1"`. The `validate_asset_json` check (export_asset.py:118-138) won't catch this because the pattern accepts both — the planner needs an explicit fixture-content assertion.

### Pitfall 17: ID immutability + prompt dangling

**What goes wrong:** A spk_id referenced in `audio_semantic.json#shots[].dialogue.spk_id` doesn't resolve in `speakers.json#speakers[].spk_id` — dangling reference.

**Why it happens:** `audio_semantic.json` is produced by Phase 15 (route round-trip); `speakers.json` is produced by Phase 13 (HITL apply). The two are decoupled.

**How to avoid:** v1.2 fixture MUST have its `audio_semantic.json#dialogue.spk_id` values be a subset of `speakers.json#speakers[].spk_id` values. Add a fixture-consistency check in `verify_contract.py` analogous to the existing prompts→characters check (lines 440-447, 604-615).

**Warning signs:** The v1.2 fixture passes individual shape validation but fails cross-file consistency. **The planner must add this check** (mirror `_fixture_consistency_check` lines 440-447 — adapt for `audio_semantic.shots[].dialogue.spk_id ⊆ speakers.speakers[].spk_id`).

### Pitfall C (existing): schema drift between fixtures and reality

**What goes wrong:** v1.2 fixture ships with hand-crafted field shapes that the route host doesn't actually produce.

**Why it happens:** Phase 11 writes the contract BEFORE Phase 12 route client exists. The fixture is "what we expect the route to produce" — if the assumption is wrong, Phase 12 hits a contract violation.

**How to avoid:** Use **real spike JSONs** (`spike/audio/results/ser_sensevoice_ep01.json`, `whisperx_align_ep01.json`) as fixture source material. The emotion labels (`HAPPY`/`ANGRY`/`NEUTRAL`/`emo_unk`) and event tags (`Speech`) are real model outputs. `[VERIFIED: spike/audio/results/ser_sensevoice_ep01.json per_sample[2].predicted_emotion="HAPPY", predicted_events=["Speech"]]`

**Warning signs:** Phase 12 implementation discovers the route returns a different shape. Mitigation: the contract is LOCKED in Phase 11; Phase 12 must conform. If Phase 12 hits a real shape problem, that's a v1.3 contract bump, not a Phase 11 fix.

### Pitfall: JSON Schema draft 2020-12 `nullable` gotcha

**What goes wrong:** Developer writes `"type": "null"` expecting it to mean "any value can be null" — but in JSON Schema, `null` is a strict type that REJECTS strings.

**Why it happens:** Old OpenAPI/Schema draft 4 habits.

**How to avoid:** For nullable fields use the **union type array**: `"type": ["string", "null"]` or `"type": ["number", "null"]` or `"type": ["object", "null"]`. The existing schemas use this correctly (e.g. `registry.schema.json:64` `frame_pos` uses `"type": ["string", "number"]`).

**Warning signs:** `validate_asset_json` raises a confusing "got null, expected string" error on a legitimately-absent field. The `emotion`/`emotion_confidence`/`spk_id`/`char_id`/`words[].score` fields in Pattern 2a/2b above all use the union-array form. **The planner should audit every nullable field for this.**

### Pitfall: `additionalProperties: false` at every nesting level

**What goes wrong:** Outer object has `additionalProperties: false` but a nested object (e.g. `dialogue`, `reproduction`, `repro_prompt`) forgets it. New optional field added later passes validation by accident.

**Why it happens:** Copy-paste of partial templates; missing the inner repetition.

**How to avoid:** Every object in EVERY new schema must have `additionalProperties: false`. The existing 10 schemas enforce this rigorously (e.g. `asset.schema.json` has it at root, source, generator, registry_snapshot, registry_snapshot.characters.items, registry_snapshot.props.items — 6 levels deep).

**Warning signs:** A v1.3 field added later passes Phase 11 schema validation when it shouldn't. **The plan-checker should grep each new schema for `"type": "object"` and verify the next non-whitespace line is `"additionalProperties": false`.**

## Code Examples

### Example 1: Exact SCHEMA_VERSION single-source location

**Verified by Read** (`scripts/export_asset.py:50-55`):

```python
# ShotTimelineAsset 契约版本（单一真源）。schema_version pattern 在 spec/schemas/
# asset.schema.json 里保持宽松（接受 "1"/"1.1"/"2.0"），但实际 emit 的字面量在这里锁死。
# v1.1 = 纯增量（新增 optional characters/props 数据文件 + 丰富 prompts schema）。改这里
# 即改全资产 emit；Pitfall 12（schema 变更后忘 bump 版本号）因此结构上不可能。
SCHEMA_VERSION = "1.2"  # ← Phase 11: bump from "1.1" to "1.2"
```

**The literal is at line 55.** Phase 11 changes ONE character (well, two — `1.1` → `1.2`). Nothing else in this file's SCHEMA_VERSION story needs to change.

### Example 2: Conditional data.* emission (mirror exactly for audio_semantic + speakers)

**Verified by Read** (`scripts/export_asset.py:307-330`):

```python
    # Phase 7: CONDITIONAL characters/props emission (CONTRACT-06 closure).
    # 仅当 canonical 文件存在才 emit —— 老 assets (无 registry) 保持 byte-identical
    # 到 v1.0（字段 OMITTED；schema optional）。canonical 文件由 registry/apply_edits.py
    # 在 HITL 审阅后产出（Plan 03）。Route-down degrade → characters.json/props.json
    # 缺席 → export 仍合法（graceful-degrade，CAST-09）。
    chars_path = os.path.join(work_dir, "characters.json")
    props_path = os.path.join(work_dir, "props.json")
    if os.path.isfile(chars_path):
        data_block["characters"] = "characters.json"
    if os.path.isfile(props_path):
        data_block["props"] = "props.json"

    # ... media.characters[]/media.props[] glob emission follows (lines 319-330) ...

    # PHASE 11 ADDITION (mirror lines 312-317 EXACTLY):
    audio_semantic_path = os.path.join(work_dir, "audio_semantic.json")
    speakers_path = os.path.join(work_dir, "speakers.json")
    if os.path.isfile(audio_semantic_path):
        data_block["audio_semantic"] = "audio_semantic.json"
    if os.path.isfile(speakers_path):
        data_block["speakers"] = "speakers.json"
```

**Planner writes this as "extend `build_asset_dict` mirroring Phase 7's conditional characters/props emission at lines 307-317; do NOT touch the registry_snapshot code path (Phase 8 PROMPT-04) — speakers does not need a snapshot."**

### Example 3: Bidirectional cross-version check structure

**Verified by Read** (`scripts/verify_contract.py:319-385`):

```python
def _cross_version_check() -> tuple:
    """schema-layer 双向 v1↔v1.1 兼容证明（CONTRACT-07；CONTEXT D-XX lock）。
    ...
    """
    failures = []
    minimal_dir = REPO / "spec" / "fixtures" / "minimal"
    v11_dir = REPO / "spec" / "fixtures" / "v1.1"

    # (a) FORWARD: v1 minimal fixture vs current (v1.1-extended) schemas
    forward_shapes = SIX_SHAPES  # the 6 v1.0 shapes
    for shape in forward_shapes:
        # ... load schema + fixture ...
        errs = list(Draft202012Validator(schema).iter_errors(instance))
        if errs:
            failures.append(f"forward {shape}: ...")

    # (b) BACKWARD: v1.1 fixture vs recovered v1 schemas
    for shape in ("asset", "prompts"):
        v1_schema = _recover_v1_schema(shape)
        # ... load v1.1 fixture ...
        errs = list(Draft202012Validator(v1_schema).iter_errors(instance))
        # additionalProperties errors are EXPECTED (v1.1 added optional fields)
        non_addprop = [e for e in errs if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(f"backward {shape}: ...")
    
    # PHASE 11 ADDS:
    v12_dir = REPO / "spec" / "fixtures" / "v1.2"
    # (c) FORWARD v1.1→v1.2: v1.1 fixture vs current (v1.2-extended) schemas
    # (Only asset — speakers/audio_semantic are NEW shapes with no v1.1 instance)
    for shape in ("asset",):
        schema = json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
        instance = json.loads((v11_dir / f"{shape}.json").read_text(encoding="utf-8"))
        errs = list(Draft202012Validator(schema).iter_errors(instance))
        if errs:
            failures.append(f"forward v1.1→v1.2 {shape}: v1.1 fixture rejected by v1.2 schema; first: {errs[0].message}")
    
    # (d) BACKWARD v1.2→v1.1: v1.2 fixture vs recovered v1.1 schema
    for shape in ("asset",):
        v11_schema = _recover_v11_schema(shape)  # NEW helper, see Example 4
        instance = json.loads((v12_dir / f"{shape}.json").read_text(encoding="utf-8"))
        errs = list(Draft202012Validator(v11_schema).iter_errors(instance))
        non_addprop = [e for e in errs if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(f"backward v1.2→v1.1 {shape}: {len(non_addprop)} non-additive errors; first: {non_addprop[0].message}")
    
    return (False, "...".join(failures)) if failures else (True, "v1.0↔v1.1↔v1.2 cross-version bidirectional compat proven")
```

### Example 4: Schema recovery generalization

**Verified by Read** (`scripts/verify_contract.py:275-316`):

```python
def _recover_v1_schema(shape: str):
    """恢复 v1.0 schema 用于 backward cross-version check（CONTRACT-07）。"""
    # Primary: git show v1.0 tag
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "show", f"v1.0:spec/schemas/{shape}.schema.json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    # Fallback: programmatic strip ...
    import copy
    stripped = copy.deepcopy(json.loads(...))
    # ... strip known v1.1 additive keys ...
    return stripped

# PHASE 11 ADDS (recommended: parameterize; alternative: clone):
def _recover_v11_schema(shape: str):
    """恢复 v1.1 schema 用于 backward cross-version check v1.2→v1.1 (Phase 11)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "show", f"v1.1:spec/schemas/{shape}.schema.json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    # Fallback: strip v1.2-additive keys from current schema
    import copy
    stripped = copy.deepcopy(json.loads(...))
    if shape == "asset":
        data_props = stripped.get("properties", {}).get("data", {}).get("properties", {})
        # v1.2 added: data.audio_semantic, data.speakers (NO media.* additions in v1.2)
        for k in ("audio_semantic", "speakers"):
            data_props.pop(k, None)
    return stripped
```

**Planner's note:** v1.1 git tag is verified to exist (`git tag --list 'v1*'` → `v1.0` + `v1.1`), so the primary path works. The fallback exists for environments without git history (CI shallow clones).

### Example 5: Realistic audio_semantic.json fixture content from spike data

**Verified by Read** (`spike/audio/results/ser_sensevoice_ep01.json` per_sample[2], shot_id 77):

```json
{
  "schema_version": "1.2",
  "word_level_experimental": true,
  "shots": [
    {
      "shot_id": 77,
      "start_sec": 224.8,
      "end_sec": 226.43,
      "duration": 1.63,
      "dialogue": {
        "text": "真的，说话算话。😊",
        "spk_id": "spk_001",
        "emotion": "HAPPY",
        "emotion_confidence": 1.0,
        "events": ["Speech"],
        "words": [
          {"start": 224.8, "end": 225.1, "text": "真的", "score": 0.99},
          {"start": 225.1, "end": 225.5, "text": "说话", "score": 0.95},
          {"start": 225.5, "end": 226.43, "text": "算话", "score": 0.92}
        ]
      },
      "sfx": {"events": [], "description": ""},
      "reproduction": {
        "tts": {
          "text": "成年女性说话者，语气开心愉悦，中文普通话，节奏自然",
          "confidence": 0.7,
          "fidelity_disclaimer": "TTS ~70% similarity to source voice (AF-01 mitigation)"
        },
        "music_gen": null,
        "foley": null
      }
    }
  ]
}
```

**Note:** The text/spk_id linkage is realistic (real SenseVoice output + plausible WhisperX words + plausible speaker ID linking back to a synthetic `speakers.json` entry). The numbers come from real model output — `emotion: "HAPPY"`, `proxy_confidence: 1.0`, `predicted_events: ["Speech"]` are LITERAL Phase-10 spike outputs (`ser_sensevoice_ep01.json:30-44`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OpenAPI 3.0 schemas for asset contracts | JSON Schema draft 2020-12 | v1.0 (2026-07-20, Phase 1) | `Draft202012Validator` is the canonical validator; no Swagger/OpenAPI tooling needed. |
| Hand-rolled bidirectional compat proofs | `_cross_version_check` with `git show` recovery + `additionalProperties` filter | v1.0 Phase 4 (verify_contract.py original) + v1.1 Phase 5 extension | The recovery mechanism is the project's proven pattern; don't reinvent. |
| Per-shape version literals | Single `SCHEMA_VERSION` source at `export_asset.py:55` | v1.0 Phase 2 | Structural Pitfall 12 prevention; bumping is one character. |

**Deprecated/outdated in this domain (do NOT use in Phase 11):**

- JSON Schema draft 7 / draft 4 — outdated; `jsonschema` supports 2020-12 natively (4.26.0 verified). All v1.0/v1.1 schemas are 2020-12; v1.2 follows.
- Schema `const` for `schema_version` — would reject v1.0 minimal fixture (`"1"`) — explicitly documented in SPEC.md:165 as a Pitfall. The literal stays in producer code (`export_asset.py:55`), NOT in schema `const`.
- Custom exception classes for schema errors — CLAUDE.md "No custom exception classes" + `sys.exit(...)` with Chinese message is the project convention (e.g. `export_asset.py:136-138`, `verify_contract.py` returns tuples instead of raising).

## Assumptions Log

> Most claims in this research were verified against v1.1 source files in this repo. The assumptions below are the few items that depend on Phase 12+ implementation that hasn't shipped yet.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `speakers.schema.json` should be top-level object `{speakers:[...]}` rather than per-shot array | Pattern 2b | If Phase 13 SPEAKER-02 implementation prefers per-shot (e.g. the review HTML iterates shots not speakers), a top-level schema still works but requires client-side pivot. Low risk — Phase 13 can adapt. |
| A2 | `audio_semantic.schema.json` should use a `reproduction` sub-object with `$defs/repro_prompt` ref | Pattern 2a | If the planner inlines the shape 3x (mirror Phase 5 `looks`/`states` style), the schema is slightly larger but functionally identical. Cosmetic. |
| A3 | `word_level_experimental` flag at top level (rather than per-shot or per-segment) | Pattern 2a | If route host produces per-shot word-level selectively, top-level may over/under-report. Mitigation: Phase 12 client computes the flag = OR of all per-shot word-level presence (cheap). Low risk. |
| A4 | `speaker-edits.schema.json` will be defined in Phase 11 (NOT just deferred to Phase 13) | CONTRACT-02 | The CONTEXT.md says "Phase 13 consumes this; Phase 11 just defines the contract." So defining it now is locked. Low risk. |
| A5 | v1.1 git tag will continue to point at the v1.1 final state after Phase 11 ships | Pattern 5 / Example 4 | If the tag is moved mid-Phase-11 (for a v1.1.1 patch), `_recover_v11_schema` would return the patched schema. Mitigation: don't move the tag — established project convention. |
| A6 | Phase 12's route response shape will match the audio_semantic.json contract | Pattern 2a, Pitfall C | If Phase 12 hits a real mismatch (route produces a different field name/shape), Phase 11's contract needs amending → would be a Phase 11 plan revision or a v1.3 bump. MEDIUM risk — but CONTEXT.md locks the shapes from user-side, so the route must conform, not the contract. |

**All other claims in this research were verified directly against v1.1 source files** (line numbers cited inline) or against the project CLAUDE.md / REQUIREMENTS.md / STATE.md. No `[ASSUMED]` tags appear in the Standard Stack — every package mentioned (jsonschema, Python stdlib) is `[VERIFIED]` via import success or grep against existing scripts.

## Open Questions

1. **Should `speakers.schema.json` include `turns` inside each speaker entry, or as a separate top-level `turns_per_shot` array?**
   - What we know: CONTEXT.md lists both options ("per-shot, or a top-level {speakers:[...], turns_per_shot:[...]}").
   - What's unclear: Which shape Phase 13 SPEAKER-02 review HTML iterates more naturally.
   - Recommendation: Use `speakers[].turns[]` (Pattern 2b) — one schema object, turns colocated with the speaker. Phase 13 can flatten if needed. The CONTEXT.md grants this discretion.

2. **Should `audio_semantic.schema.json`'s `reproduction` field be required when present (i.e. when shot has dialogue/sfx), or always optional?**
   - What we know: PROMPT-01/02 are Phase 15 requirements; Phase 11 just defines the contract.
   - What's unclear: Whether the contract should require reproduction fields whenever modality fields are populated, or leave it Phase 15's job.
   - Recommendation: Always optional at v1.2 contract level. Phase 15 enforces "always emit reproduction when modality present" as producer logic. The contract stays permissive — graceful-degrade default.

3. **Should `speaker-edits.schema.json` include a `link_mappings` field (NEW vs registry-edits), or reuse `confirm_ids` with side-channel spk→char map?**
   - What we know: SPEAKER-01 core use case is spk_id→char_id mapping; registry-edits doesn't have an analogous "link" concept.
   - What's unclear: Whether the HITL UI is "confirm this speaker is character X" (single concept, fits confirm_ids extension) or "link N speakers to M characters in batch" (needs a new field).
   - Recommendation: Add `link_mappings: {spk_id: char_id}` as a NEW field (Pattern 2c). Cleaner than overloading confirm_ids; Phase 13 link_speakers.py consumes it directly.

4. **Should the byte-identical-absent check (Pitfall 11 hardening) be automated in `verify_contract.py`, or kept as a manual fixture-diff task?**
   - What we know: Schema-level check (additionalProperties:false + absent-not-required) is automated; byte-diff against golden v1.1 fixture is not.
   - What's unclear: Whether the runtime cost of a golden-fixture-diff is worth it for an invariant the producer code structurally guarantees.
   - Recommendation: Add a lightweight automated check (`diff spec/fixtures/v1.1/asset.json spec/fixtures/v1.2/asset.json` filtered for the 2 new keys). Cheap, catches accidental producer drift in Phase 12. Plan as Wave 2 task (after contract lands).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | all schema/validator/fixture scripts | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `jsonschema` lib | `Draft202012Validator` in `spec/validate.py`, `scripts/export_asset.py`, `scripts/verify_contract.py` | ✓ | 4.26.0 (system) | — |
| `git` CLI | `_recover_v*_schema` (PRIMARY path for cross-version) | ✓ | any | Fallback: programmatic-strip in `_recover_v1_schema` lines 298-316 (Phase 11 extends for v1.1) |
| `v1.0` git tag | `_recover_v1_schema` PRIMARY | ✓ | verified via `git tag --list 'v1*'` | Same fallback |
| `v1.1` git tag | NEW `_recover_v11_schema` PRIMARY | ✓ | verified via `git tag --list 'v1*'` | Same fallback (Phase 11 adds v1.2-added keys to strip list) |
| Phase 10 spike JSONs | realistic fixture content | ✓ | `spike/audio/results/{ser,whisperx,mir}*.json` | — |
| `ffmpeg`/`ffprobe` | NOT required by Phase 11 (no media work) | n/a | n/a | n/a |
| GPU | NOT required by Phase 11 (no ML work) | n/a | n/a | n/a |

**Missing dependencies with no fallback:** None. All Phase 11 dependencies are existing project runtime.

**Missing dependencies with fallback:** None. Phase 11 needs nothing new.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json:19` → this section REQUIRED.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Python stdlib + `jsonschema.Draft202012Validator` (4.26.0, system-installed) |
| Config file | none — `spec/validate.py` and `scripts/verify_contract.py` are self-contained CLI scripts |
| Quick run command | `python3 spec/validate.py` (minimal 6 + v1.1 10 + smoke 5; gate exit code) |
| Full suite command | `python3 scripts/verify_contract.py --mode=producer` (producer schema + bidirectional + fixture-consistency) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONTRACT-01 | `audio_semantic.schema.json` validates a fixture instance | schema unit | `python3 -c "from jsonschema import Draft202012Validator as V; import json; V(json.load(open('spec/schemas/audio_semantic.schema.json'))).validate(json.load(open('spec/fixtures/v1.2/audio_semantic.json')))"` | ❌ Wave 0 (schema + fixture don't exist yet) |
| CONTRACT-01 | v1.0/v1.1 fixtures still pass forward against v1.2-extended asset.schema | schema cross-version | `python3 scripts/verify_contract.py --mode=producer` (extended `_cross_version_check` part (c)) | ❌ Wave 0 (v1.2 extension + check not yet wired) |
| CONTRACT-02 | `speakers.schema.json` validates a fixture instance | schema unit | `python3 -c "from jsonschema import Draft202012Validator as V; import json; V(json.load(open('spec/schemas/speakers.schema.json'))).validate(json.load(open('spec/fixtures/v1.2/speakers.json')))"` | ❌ Wave 0 |
| CONTRACT-02 | `speaker-edits.schema.json` validates an empty-edits fixture | schema unit | (same pattern) | ❌ Wave 0 |
| CONTRACT-03 | `SCHEMA_VERSION = "1.2"` literal in `export_asset.py` | grep assertion | `grep -c 'SCHEMA_VERSION = "1.2"' scripts/export_asset.py` (expect 1) | ❌ Wave 0 (still "1.1") |
| CONTRACT-03 | `validate.py` 3-tier gate: minimal/v1.1/v1.2 all green | CLI | `python3 spec/validate.py` (expect `minimal failures=0, v1.1 failures=0, v1.2 failures=0`) | ❌ Wave 0 (v1.2 fixture + V12_ORDER not added yet) |
| CONTRACT-03 | `verify_contract.py` v1.1↔v1.2 bidirectional forward 0 errors | CLI | `python3 scripts/verify_contract.py --mode=producer` | ❌ Wave 0 |
| CONTRACT-03 | `verify_contract.py` v1.1↔v1.2 backward ONLY additionalProperties | CLI | `python3 scripts/verify_contract.py --mode=producer` | ❌ Wave 0 |
| CONTRACT-03 | `speakers.char_id ⊆ characters.id` fixture-consistency | CLI | `python3 scripts/verify_contract.py --mode=producer` | ❌ Wave 0 |
| CONTRACT-04 | SPEC.md §4 has `1.2` Changelog entry | grep assertion | `grep -c '\`1.2\`' spec/SPEC.md` (expect ≥1) | ❌ Wave 0 |
| CONTRACT-04 | SPEC.md §5 has audio_semantic + speakers shapes | grep assertion | `grep -E 'Audio Semantic.*v1.2\|Speakers.*v1.2' spec/SPEC.md` | ❌ Wave 0 |
| CONTRACT-04 | SPEC.md has `fidelity_disclaimer` | grep assertion | `grep -c 'fidelity_disclaimer' spec/SPEC.md` (expect ≥3 — header + at least 2 modality references) | ❌ Wave 0 |
| CONTRACT-05 | No `instruments` field anywhere in v1.2 schemas | grep negative | `! grep -r '"instruments"' spec/schemas/audio_semantic.schema.json spec/schemas/asset.schema.json` (expect rc=1, no match) | ❌ Wave 0 (proves Pitfall: instruments omission) |
| CONTRACT-05 | Byte-identical-absent: v1.1 fixture asset.json unchanged bytes | diff | `diff spec/fixtures/v1.1/asset.json <(git show v1.1:spec/fixtures/v1.1/asset.json)` (expect empty) | ✅ pre-exists (will guard against accidental Phase 11 edits) |
| CONTRACT-05 | `required[]` byte-identical to v1.1 in asset.schema | programmatic | `python3 -c "import json; s=json.load(open('spec/schemas/asset.schema.json')); print(s['properties']['data']['required'])"` (expect `['shots', 'audio_analysis', 'transcript', 'frames', 'prompts']` — 5 keys, NO audio_semantic/speakers) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python3 spec/validate.py` (3-tier gate — minimal 6 + v1.1 10 + v1.2 12 = 28 shapes green). Fast (<2s).
- **Per wave merge:** `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer` (full bidirectional + consistency).
- **Phase gate:** Full suite green before `/gsd:verify-work`:
  1. `python3 spec/validate.py` exits 0
  2. `python3 scripts/verify_contract.py --mode=producer` exits 0
  3. `grep -c 'SCHEMA_VERSION = "1.2"' scripts/export_asset.py` = 1
  4. `! grep -r '"instruments"' spec/schemas/` (no instruments field)
  5. Manual spot-check: v1.2 fixture asset.json has `schema_version: "1.2"` and `data.audio_semantic` + `data.speakers` keys

### Wave 0 Gaps

Before implementation can begin, the following infrastructure must exist (will be created in Wave 0 of the plan):

- [ ] `spec/schemas/audio_semantic.schema.json` — covers CONTRACT-01
- [ ] `spec/schemas/speakers.schema.json` — covers CONTRACT-02
- [ ] `spec/schemas/speaker-edits.schema.json` — covers CONTRACT-02
- [ ] `spec/fixtures/v1.2/` directory + 12 fixture files (10 copied from v1.1 + 2 new) — covers CONTRACT-01..05 fixture substrate
- [ ] `spec/validate.py` extended with `V12_FIXTURE_DIR`/`V12_FIXTURE_MAP`/`V12_ORDER` + `validate_v12()` — covers CONTRACT-03 (3-tier gate)
- [ ] `scripts/export_asset.py:55` bumped to `SCHEMA_VERSION = "1.2"` + `build_asset_dict` extended with conditional `data.audio_semantic`/`data.speakers` emission — covers CONTRACT-03 (single-source) + CONTRACT-05 (graceful-degrade)
- [ ] `scripts/verify_contract.py` extended with `_recover_v11_schema` + extended `_cross_version_check` (v1.1↔v1.2 forward + backward) + extended `_fixture_consistency_check` (speakers.char_id ⊆ characters.id) — covers CONTRACT-03 (bidirectional proof)
- [ ] `asset.schema.json` extended with optional `data.audio_semantic` + `data.speakers` properties (NOT in `required[]`) — covers CONTRACT-01/02 (asset additive extension)
- [ ] `spec/SPEC.md` extended with §4 Changelog `1.2` entry + §5.8 Audio Semantic + §5.9 Speakers + fidelity_disclaimer section — covers CONTRACT-04

*(No test framework install needed — existing `jsonschema` 4.26.0 + Python 3.12 covers all assertions.)*

## Security Domain

> `security_enforcement` not in `.planning/config.json` → defaults to enabled. Brief treatment: this is a **contract/schema phase** with no new external input surfaces — the threat surface is the existing asset.json path-traversal/Windows-reserved-char protection, which Phase 11 extends cosmetically (no new media types, no new external input paths).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a — Phase 11 has no auth surface |
| V3 Session Management | no | n/a — Phase 11 has no session surface |
| V4 Access Control | no | n/a — Phase 11 is contract files, no runtime access |
| V5 Input Validation | **yes** | JSON Schema `additionalProperties: false` + `pattern` regex on every data/media path (reused from v1.0/v1.1 — no new patterns invented in Phase 11) |
| V6 Cryptography | no | n/a |
| V7 Error Handling & Logging | **yes (mild)** | `verify_contract.py` returns tuples `(bool, str)` and the str may include fixture paths but NEVER credentials, tokens, or model outputs beyond what's already in fixtures. Mirror existing convention. |
| V8 Data Protection | no | n/a — Phase 11 doesn't handle PII |
| V9 Communications | no | n/a — no network surface in Phase 11 |
| V13 API & Web Service | no | n/a — Phase 11 has no API surface |
| V14 Configuration | **yes (mild)** | `SCHEMA_VERSION = "1.2"` literal — single source, structurally prevented from drift (Pitfall 12) |

### Known Threat Patterns for JSON Schema contract extension

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `data.audio_semantic` or `data.speakers` path | Tampering | Reuse existing anti-traversal pattern `^(?!.*\\.\\.)[^:*?\"<>\|]+\\.json$` from asset.schema.json:121 (and 126, 131, 136, 141, 146, 151). Phase 11 uses the SAME pattern for the 2 new data.* fields — no new pattern invented. `[VERIFIED: pattern reuse, see Code Examples]` |
| Malformed spk_id references (path-traversal via spk_id) | Tampering | `^spk_[0-9]{3}$` strict regex (T-07-01 mitigation, mirror registry-edits schema:16). Pattern is in CONTEXT.md locked decisions. |
| Producer emits empty audio_semantic key when route down (byte-identical-absent violation) | Information disclosure (corruption disguised as clean) | Conditional emission via `os.path.isfile()` gate (mirror export_asset.py:312-317). Plus the byte-identical-absent diff check (Validation Architecture, CONTRACT-05 row). |
| Schema-invalid fixture ships (silent interop bug) | Tampering / repudiation | `validate_v12()` strict gate (Phase 11 adds to validate.py); failures count toward exit code. |
| Cross-version drift (v1.2 schema accidentally breaks v1.1 forward compat) | Information disclosure / DoS on old consumers | `_cross_version_check` extended to v1.1↔v1.2 — must be GREEN (0 forward errors, 0 non-addProp backward errors). |

**No new ASVS-relevant controls introduced by Phase 11.** All existing controls (path-traversal regex, `additionalProperties: false`, conditional emission, bidirectional proof) are reused verbatim from v1.0/v1.1.

## Sources

### Primary (HIGH confidence — verified via tool against v1.1 source)

- `Read` of `/data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json` — full file (210 lines), header anatomy, `data.characters`/`data.props` additive positions (lines 144-153), `additionalProperties: false` at every nesting level verified, `schema_version.pattern` at line 14.
- `Read` of `/data/workspace/kais-shot-timeline/spec/schemas/registry-edits.schema.json` — full file (77 lines), HITL round-trip template (line-for-line reference for `speaker-edits.schema.json`).
- `Read` of `/data/workspace/kais-shot-timeline/spec/schemas/characters.schema.json` + `props.schema.json` — `^char_[0-9]{3}$` / `^prop_[0-9]{3}$` ID patterns, `looks[]`/`states[]` sub-structures, `review_state` enum.
- `Read` of `/data/workspace/kais-shot-timeline/spec/schemas/registry.schema.json` — top-level object `{clusters:[...]}` shape (template for `speakers.schema.json`).
- `Read` of `/data/workspace/kais-shot-timeline/scripts/export_asset.py` — full file (534 lines); `SCHEMA_VERSION = "1.1"` at line 55 (single-source); `build_asset_dict` at lines 246-379; conditional characters/props emission at lines 307-317 (mirror target); `_build_registry_snapshot` at lines 173-243 (NOT to be mirrored — Phase 11 has no equivalent); `validate_asset_json` at lines 118-138 (inline validator pattern).
- `Read` of `/data/workspace/kais-shot-timeline/scripts/verify_contract.py` — full file (1205 lines); `EIGHT_SHAPES` legacy name at lines 78-82 (actually 9 elements); `validate_eight_shapes` at lines 204-271; `_recover_v1_schema` at lines 275-316 (template for `_recover_v11_schema`); `_cross_version_check` at lines 319-385 (template for v1.1↔v1.2 extension); `_fixture_consistency_check` at lines 388-488 (template for speakers⊆characters check); `_producer_registry_integrity` at lines 492-637 (Phase 13 will extend).
- `Read` of `/data/workspace/kais-shot-timeline/spec/validate.py` — full file (247 lines); `V11_FIXTURE_DIR`/`V11_FIXTURE_MAP`/`V11_ORDER` at lines 55-71 (template for `V12_*`); `validate_v11` at lines 119-151 (template for `validate_v12`); `main()` at lines 198-242 (where to wire v1.2 into exit code).
- `Read` of `/data/workspace/kais-shot-timeline/spec/SPEC.md` — full file (549 lines); §1 Authority + schema layout (lines 12-39); §4 Changelog with `1.1` entry template (lines 161-168); §5 shapes format (lines 172-420); §6 media + Range-aware serving (lines 424-483).
- `Read` of `/data/workspace/kais-shot-timeline/spec/README.md` — schema layout overview; v1.1 update footer (line 80) is the template for v1.2 update footer.
- `Read` of `/data/workspace/kais-shot-timeline/spec/fixtures/v1.1/asset.json` — manifest→data-file wiring reference (10 files cross-referenced).
- `Read` of `/data/workspace/kais-shot-timeline/spec/fixtures/v1.1/characters.json` — fixture realism reference (Chinese `name` field, `looks[]` shape).
- `Read` of `/data/workspace/kais-shot-timeline/.planning/phases/11-contract-v1-2/11-CONTEXT.md` — user decisions (locked shapes; instruments OMITTED; emotion type:string nullable+confidence; word-level experimental; spk_NNN regex locked).
- `Read` of `/data/workspace/kais-shot-timeline/.planning/REQUIREMENTS.md` — CONTRACT-01..05 acceptance criteria.
- `Read` of `/data/workspace/kais-shot-timeline/.planning/STATE.md` — Phase 10 locked outcomes + carried decisions.
- `Read` of `/data/workspace/kais-shot-timeline/.planning/research/audio-spike-report.md` — Phase 10 empirical evidence (SenseVoice self_consistency=100%, MERT no classifier, WhisperX boundary drift=101.5ms).
- `Read` of `/data/workspace/kais-shot-timeline/.planning/config.json` — `workflow.nyquist_validation: true` (Validation Architecture section required).
- `Read` of `/data/workspace/kais-shot-timeline/CLAUDE.md` — project conventions (Chinese docstrings, `ensure_ascii=False`, two-tier authority, no package manifest, subprocess-first, etc.).
- `Read` of `/data/workspace/kais-shot-timeline/spike/audio/results/ser_sensevoice_ep01.json` (head) — real model output shapes for fixture realism (shot 77 = HAPPY/`["Speech"]`/proxy_confidence=1.0).
- `Bash` (verified) `python3 -c "import jsonschema; ..."` — jsonschema 4.26.0 + Draft202012Validator confirmed.
- `Bash` (verified) `git tag --list 'v1*'` — `v1.0` + `v1.1` tags both exist (required for `_recover_v*_schema`).
- `Bash` (verified) `python3 -c "...git show v1.0 vs v1.1 asset.schema..."` — v1.1 added `data.characters`/`data.props` to `properties` while `required[]` stayed byte-identical at 5 keys (forward-compat invariant proven).
- `Bash` (verified) `grep` on prompts.schema.json — `character_refs`/`prop_refs` at lines 70-86 with "v1.1 additive (OPTIONAL — never required)" annotation (additive pattern template).

### Secondary (MEDIUM confidence — single source but authoritative)

- `.planning/ROADMAP.md` Phase 11 section (lines 75-85) — success criteria 1-5 verbatim. (Note: line 77 dependency note "instruments as `list[{label,confidence}]`" is STALE per CONTEXT.md — Phase 10 overrules it.)
- `.planning/PROJECT.md` (referenced via STATE.md) — Key Decisions rows for DIA-04/MUS-04/DIA-05/CUDA path.

### Tertiary (LOW confidence — none)

No claims in this research are LOW confidence. Every architectural claim has a line number in the v1.1 source; every empirical claim has a Phase-10 spike JSON.

## Metadata

**Confidence breakdown:**

- **Standard stack:** HIGH — every package verified via existing imports in v1.0/v1.1 scripts. No new packages.
- **Architecture (schemas + asset.schema extension):** HIGH — every pattern extracted from v1.1 source with line numbers. The bidirectional proof mechanism is already proven for v1.0↔v1.1; extending to v1.1↔v1.2 is mechanical.
- **Pitfalls:** HIGH — every pitfall is documented in CLAUDE.md, STATE.md, or inline in v1.1 source code comments.
- **Phase-10-informed deviations:** HIGH — empirical basis from spike report + locked in CONTEXT.md (user decisions, not research assumptions).
- **Speaker-edits schema shape:** MEDIUM — built by mirroring registry-edits.schema.json but with one new field (`link_mappings`); exact field is at planner's discretion per CONTEXT.md.
- **audio_semantic internal structure (reproduction $defs vs inline):** MEDIUM — both shapes are valid; planner picks.

**Research date:** 2026-07-25
**Valid until:** 2026-08-25 (30 days). Contract-locking phases are stable; the v1.1 reference is git-tagged and will not shift. The risk of staleness is LOW — only Phase 12 implementation feedback would invalidate this research, and Phase 12 hasn't started.
