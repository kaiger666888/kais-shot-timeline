# Phase 8: Prompt Reference System + shot-timeline HTML Gallery - Research

**Researched:** 2026-07-25
**Domain:** Producer-side prompt-reference attachment + deterministic `prompt_text` recompose + asset-level registry snapshot freeze + HTML gallery/chips/indicator extension. The substrate (confirmed `characters.json`/`props.json`) is shipped (Phase 7) and the schemas (`prompts.character_refs[]`/`prop_refs[]`, `asset.generator`) already permit the fields (Phase 5). This phase is pure **producer wiring + HTML extension** — zero new ML, zero new routes, zero cross-repo dependency.
**Confidence:** HIGH (every touched file has a DIRECT proven template in Phase 5/6/7: `attach_refs.py` mirrors `merge_prompts.py`; `export_asset.py#build_asset_dict` conditional emission mirrors the Phase 7 CONTRACT-06 closure; `verify_contract.py` extension mirrors Phase 7 `_producer_registry_integrity`; `gen_timeline_html.py` gallery/chips mirror the existing shot-row + the Phase 7 `_esc()`/JSON-in-script hardening from CR-04 fix `336d04f`).

## Summary

Phase 8 closes the v1.1 producer side: the confirmed Phase-7 registry (or its absence — graceful-degrade) is wired onto the prompts, the asset manifest, and the timeline UI. Four orthogonal concerns — all in-repo, all testable NOW on the v1.1 fixture set with zero deferred human items:

1. **`prompts/attach_refs.py` (PROMPT-01/02)** — reads the confirmed registry, attaches `character_refs[]`/`prop_refs[]` per shot via `appearance_shots[]`, then **deterministically recomposes** `prompt_text` to inject character/prop names. Pure stdlib + jsonschema. Idempotent (byte-identical re-run). No LLM, no fabrication — names come ONLY from the confirmed registry.
2. **`generator.registry_snapshot` freeze (PROMPT-04)** — `export_asset.py` emits a compact confirmed-registry snapshot inside `asset.json#generator` whenever `characters.json`/`props.json` exist, so later registry mutations (re-review, re-cluster) cannot invalidate already-exported prompt references. Additive schema property (like `warnings` in Phase 6).
3. **`verify_contract.py` prompt↔registry integrity (PROMPT-03)** — extends the Phase-7 `_producer_registry_integrity` with the missing direction: every `prompts.character_refs[]`/`prop_refs[]` ID must exist in canonical `characters.json`/`props.json` (no dangling — Pitfall 17).
4. **`gen_timeline_html.py` gallery + chips + indicator (PRESENT-01/02/03)** — extends `build_html` with: (a) character/prop gallery reading the embedded `registry_snapshot` (or external PNGs via `serve.py`); (b) clickable chips in the per-shot prompt rendering linking to gallery entries; (c) per-shot "运镜分析填充" chip (green = route filled / gray = offline degraded, tied to Phase 6 `generator.warnings`).

**Carry-over from Phase 7 review (CRITICAL):** Phase 7's `07-REVIEW.md` CR-04 found `html/gen_registry_review.py` XSS via unescaped operator-influenced strings in both HTML body and JSON-in-`<script>`. Fixed in `336d04f` via self-contained `_esc()` + `json.dumps(...).replace("</", "<\\/")`. **Phase 8's `gen_timeline_html.py` extension MUST carry the exact same hardening** because operator-influenced character/prop `name` fields (registry-reviewer-editable per `characters.schema.json:21` "reviewer 可编辑") now flow into gallery cards, chips, and the inlined `SHOTS`/`CHARACTERS` JSON literals. This is documented below as Pitfall 1 + Pattern 4.

**Primary recommendation:** Build wave-ordered — Wave 1 = contract layer (`asset.schema.json#generator.registry_snapshot` additive + fixture example + `SPEC.md` row); Wave 2 = `attach_refs.py` + `export_asset.py` + `verify_contract.py` extension (parallel, each independent); Wave 3 = `gen_timeline_html.py` gallery/chips/indicator + `run_pipeline.py` wire + `verify_phase8_smoke.py`. NO step-counter bump (`step_timeline` invokes `attach_refs.py` as a pre-step; CONTEXT Q3 lock).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (不可重开)

**Prompt-ref attachment + recompose (PROMPT-01, PROMPT-02)** — Q1/Q2/Q3:
- **Q1 — attach mechanism:** `prompts/attach_refs.py` reads `characters.json` + `props.json` (confirmed registry) + `prompts.json` + `shots.json`; for each shot, attaches `character_refs[]`/`prop_refs[]` = the IDs whose `appearance_shots[]` contains that `shot_id`. Idempotent (re-running produces byte-identical `prompts.json`). Schema-validated output (prompts.schema.json already allows the optional refs — Phase 5 CONTRACT-04). Alt (LLM-based) rejected — non-deterministic, adds dep.
- **Q2 — `prompt_text` recompose:** **deterministic template join** — resolve refs → names (from `characters.json`/`props.json` `name`), then recompose `prompt_text` by injecting identity into a stable template that combines the existing facets (subject/action/camera/scene/lighting/style). When no refs: `prompt_text` recomposed from facets alone (no identity clause). NO LLM, NO fabrication — names come only from the confirmed registry. Recomposition is deterministic + idempotent. Alt (LLM rewrite) rejected; alt (leave `prompt_text` untouched) rejected (PROMPT-02 explicitly requires identity-referencing recomposition).
- **Q3 — pipeline integration (avoid counter bump):** `step_timeline` invokes `prompts/attach_refs.py` as a **pre-step** (modifies `prompts.json` in place) BEFORE `gen_timeline_html.py` runs. NO new numbered banner, NO `[N/8]`→`[N/9]` counter bump (ROADMAP Phase 8 success criteria don't call for a new step). `attach_refs` is a standalone CLI script invoked via subprocess (mirrors the stage pattern), just not given its own `[N/M]` slot. Alt (new `step_prompt_refs` slot 7 → `[N/9]`) rejected — unnecessary counter churn.

**Registry snapshot freeze (PROMPT-04)** — Q1/Q2:
- **Q1 — snapshot shape:** `generator.registry_snapshot` = compact frozen view: `{characters:[{id,name,representative_image,appearance_shots}], props:[{id,name,representative_image,appearance_shots}]}` containing ONLY `review_state:"confirmed"` entries (Pitfall 7 consistent). Embeds enough for a consumer to resolve prompt refs + render a gallery WITHOUT re-reading external `characters.json`/`props.json` (the snapshot is the export-time truth). Additive OPTIONAL field in `asset.schema.json#generator.properties` (like `warnings` — absent on old assets, schema-valid). Alt (content-hash only) rejected — can't resolve refs offline; alt (full registry.blob) rejected — bloat.
- **Q2 — schema bump:** **NO version bump** — `generator.registry_snapshot` is additive-optional within v1.1 (the whole milestone shares `schema_version:"1.1"` per STATE.md decision). `SCHEMA_VERSION` constant in `export_asset.py` stays `"1.1"`. Strict `additionalProperties:false` means the schema MUST declare the new property (else it fails) — add it to `asset.schema.json#generator.properties`.

**Cross-file integrity (PROMPT-03)** — Q1:
- **Q1 — check scope:** extend `verify_contract.py` `_fixture_consistency_check` (additive, file-existence-gated): when `prompts.json` + `characters.json`/`props.json` exist → (a) every `character_refs[]`/`prop_refs[]` ID in `prompts.json` MUST exist in `characters.json`/`props.json` (no dangling — Pitfall 17); (b) every confirmed registry entry's `appearance_shots` ⊆ `shots.json` (already checked in Phase 7's `_producer_registry_integrity` — reuse, don't duplicate). Alt (separate verifier) rejected — keep integrity checks unified in `verify_contract.py`.

**HTML gallery + chips + indicator (PRESENT-01, PRESENT-02, PRESENT-03)** — Q1/Q2/Q3:
- **Q1 — gallery section:** extend `gen_timeline_html.py:build_html` with a character/prop gallery section (cards: representative thumbnail via external png served by `serve.py`, name, ID, appearance-shot count). Reuse GitHub-dark palette + monolithic self-contained pattern. Gallery reads `characters.json`/`props.json` (or the embedded `registry_snapshot` if present).
- **Q2 — reference chips:** in the per-shot prompt rendering, render `character_refs[]`/`prop_refs[]` as clickable badge chips (🧑 name / 🔧 name) that link/scroll to the corresponding gallery entry. Clickable via in-page anchor (no server needed — mirrors the self-contained HTML pattern).
- **Q3 — semantic-fill indicator:** per-shot "运镜分析填充" chip: **green** when the route filled the cinematography facets (camera/action/lighting/style non-empty AND sourced from route — detected via `prompts.json` having non-empty route-sourced facets) / **gray** when offline-degraded (facets empty, sourced from graceful-degrade). The indicator reads the facet content (empty = degraded). Consistent with Phase 6's `generator.warnings` (which records the degrade reason).

### Claude's Discretion

- Exact gallery card CSS/layout; chip color shades (reuse palette tokens); `prompt_text` recompose template prose (deterministic, identity-injecting); whether the gallery reads `characters.json` or the embedded `registry_snapshot` (recommend: `registry_snapshot` when present, else `characters.json` — graceful).

### Deferred Ideas (OUT OF SCOPE)

- **Canvas consumer gallery/chips (PRESENT-04/05/06)** — Phase 9 cross-repo (kais-aigc-platform `feat/canvas-asset-collection`); the producer-side snapshot + refs are the contract the canvas consumes.
- **PROMPT dialect switch (paragraph vs keyword)** — v2 (PROMPT-DIALECT-01 deferred).
- **Cross-video character continuity** — v2 (CROSSVIDEO-01 deferred).
- **Speaker attribution (dialogue → speaker)** — v2 (SPEAKER-01 deferred).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **PROMPT-01** | 后处理 `prompts.json`——按 `characters.json#appearance_shots[]` 挂 `character_refs[]`/`prop_refs[]` ID 到对应 shot | **IN SCOPE.** `prompts/attach_refs.py` (NEW, mirrors `prompts/merge_prompts.py` standalone-CLI pattern). Build `shot_id → [char_ids]` + `shot_id → [prop_ids]` maps by inverting `appearance_shots[]`; attach sorted (deterministic). Schema validates (Phase 5 already added optional `character_refs`/`prop_refs` — see `prompts.schema.json:70-85`). |
| **PROMPT-02** | `prompt_text` 重 Compose——引用角色/道具时生成叙事连贯、可被 AI 视频管线复用的 prompt 文本 | **IN SCOPE.** Deterministic template (see Pattern 2): `[style] · [scene] · 角色:[name1,name2] · 道具:[name1] · [subject] · [action] · [camera] · [lighting]`. Identity clause omitted when refs empty. Idempotent (same inputs → byte-identical output). NO LLM. |
| **PROMPT-03** | 跨文件完整性检查(prompt 引用的 ID 必须在 registry 中存在,无 dangling)加入 `verify_contract.py` | **IN SCOPE.** Extend `_producer_registry_integrity` (Phase 7 fn at `verify_contract.py:492-590`) with: for each shot in `prompts.json`, every `character_refs[]`/`prop_refs[]` ID MUST ⊆ confirmed `characters.json`/`props.json` IDs. Fixture-side `_fixture_consistency_check` already does this (lines 440-447); producer-side mirrors it. |
| **PROMPT-04** | `asset.json` 嵌 `generator.registry_snapshot`(冻结 registry 状态,防后续 registry 变动使已导出资产的 prompt 引用失效) | **IN SCOPE.** Add `generator.registry_snapshot` to `asset.schema.json` (additive optional, mirror `warnings`); `export_asset.py#build_asset_dict` emits compact confirmed-only view when `characters.json`/`props.json` exist. NO `schema_version` bump (stays `"1.1"`). |
| **PRESENT-01** | `gen_timeline_html.py` 扩展——角色/道具画廊区(外置 png 经 `serve.py` 提供)+ 点击跳转 | **IN SCOPE.** Gallery section appended above the two-panel layout. Reads `asset.json#generator.registry_snapshot` when present (embedded truth) else falls back to `characters.json`/`props.json`. Thumbnails = `<img src="characters/char_001.png">` (external PNGs, Range-served by `scripts/serve.py`). |
| **PRESENT-02** | prompt 渲染加 reference chip(角色/道具可点击徽章,链接到画廊条目) | **IN SCOPE.** In the per-shot row template (`gen_timeline_html.py:365-371` and `:818-824`), append chip badges after `.type-badge`. Each chip = in-page anchor `<a href="#char_001">🧑 _esc(name)</a>`. Click scrolls to gallery entry (browser native + `scroll-behavior:smooth` already set in CSS line 132). |
| **PRESENT-03** | 每镜「运镜分析填充」指示器(绿 chip = 路由填充;灰 chip = offline 降级空字段) | **IN SCOPE.** Per-shot detection: `route_filled = any(s.camera, s.action, s.lighting, s.style)` non-empty strings. Render green `✓ 运镜` chip when filled, gray `○ 降级` chip when all four empty. Tie to Phase 6 `generator.warnings` (already in asset.json). |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md is present — the planner MUST honor these directives (treat with same authority as locked decisions):

- **No package manifest / no `__init__.py` / namespace-package convention:** stages invoked by absolute file path via `subprocess.run([sys.executable, str(HERE / "prompts" / "attach_refs.py"), ...])`, NOT imported as modules. `prompts/` already has `merge_prompts.py` + `extract_frames.py` as siblings — `attach_refs.py` follows the same pattern.
- **No test framework:** standalone `sys.exit(0/1)` scripts. `scripts/verify_phase8_smoke.py` mirrors `verify_phase7_smoke.py` (bracketed prefix tags + exit-code contract + stdlib + jsonschema only). NO pytest.
- **Atomic writes:** temp file + `os.replace` (see `export_asset.py:402-405`, `gen_registry_review.py`). `attach_refs.py` MUST follow.
- **`ensure_ascii=False` + `indent=2`** for any JSON containing Chinese (`prompts.json` recompose output, `asset.json` registry_snapshot).
- **Chinese docstrings/comments + `print("[stage] ...")` bracketed prefixes** for every progress line.
- **CLI conventions:** `--flag-name` kebab-case, `argparse` with `help=` strings in Chinese, `action="store_true"` for booleans.
- **`httpx` 0.28.1 + `jsonschema` 4.26.0 already in env** (verified — see Environment Availability). Zero new deps this phase.
- **Strict-schema × lenient-consumer:** schema `additionalProperties:false` is the project pattern (every Phase 5 schema enforces it). `attach_refs.py` output MUST be schema-valid (run `Draft202012Validator(prompts_schema)` pre-write); `asset.schema.json` MUST declare `generator.registry_snapshot` (else strict schema rejects it).
- **Subprocess invocation:** `subprocess.run([sys.executable, ...], check=True)` for sibling Python scripts. `attach_refs.py` invoked exactly this way from `step_timeline`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `character_refs[]`/`prop_refs[]` attachment | Pipeline stage (`prompts/attach_refs.py`) | Filesystem (`prompts.json` in-place rewrite) | Pure producer-side post-processing; reads confirmed registry (FS truth) + writes back to FS; no UI, no network. |
| `prompt_text` deterministic recompose | Pipeline stage (`prompts/attach_refs.py`) | — | Names resolved from `characters.json#name` (registry truth) — no LLM, no fabrication. Determinism = same inputs → byte-identical output (idempotency guarantee). |
| `registry_snapshot` freeze | Exporter (`scripts/export_asset.py`) | Schema (`asset.schema.json#generator`) | Snapshot = export-time truth, frozen inside `asset.json#generator`. Later registry mutations cannot invalidate exported refs (Pitfall 18). |
| `prompt↔registry` ID integrity | Verify harness (`scripts/verify_contract.py`) | — | Unified producer gate; extends Phase 7 `_producer_registry_integrity` with prompts→registry direction. |
| Character/prop gallery | Static HTML generator (`html/gen_timeline_html.py`) | Served by `scripts/serve.py` (external PNG Range) | Monolithic self-contained HTML pattern (Phase 1-7 convention); gallery reads embedded `registry_snapshot` (preferred) or external `characters.json` (fallback). |
| Reference chips | Static HTML generator (in-page anchor wiring) | — | Pure client-side; in-page `#<id>` anchors, no server dependency. Browser-native smooth scroll already in CSS. |
| Semantic-fill indicator | Static HTML generator (reads facet content) | Phase 6 `generator.warnings` (degrade reason) | Empty camera/action/lighting/style strings = offline degraded; non-empty = route filled. |
| XSS hardening | Static HTML generator (`_esc()` + JSON-in-script escape) | Schema (defense-in-depth, not a substitute) | Carry Phase 7 CR-04 fix `336d04f` pattern verbatim — operator-influenced `name` strings flow into gallery + chips + inlined JSON. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` [VERIFIED: env + pip show + Phase 5-7 baseline] | 4.26.0 | `Draft202012Validator` pre-write validation of `prompts.json` (attach_refs output) + `asset.json` (snapshot extension) | v1.0 baseline; Phase 5 extended to 8 shapes; Phase 7 added `_producer_registry_integrity` using same lib; zero migration cost. |
| Python stdlib `json` / `pathlib` / `argparse` / `subprocess` / `os` / `re` | stdlib | JSON I/O / CLI / sibling invocation / atomic write / `</`→`<\/` post-processing | Project convention — zero new deps; CLAUDE.md "stdlib-first". |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsonschema.Draft202012Validator` | 4.26.0 | `attach_refs.py` validates recomposed `prompts.json` against `prompts.schema.json` BEFORE atomic write (fails loud — honors project pattern). | Always — never write schema-invalid output. |
| `html` escape helper (inline `_esc`) | n/a | 5-char HTML escape (`& < > " '`) self-contained inline impl — copy from `gen_registry_review.py:79-91` (CR-04 fix). | Every interpolation of operator-influenced string into HTML body or attribute context. |
| External ffmpeg/ffprobe binary | 6.1.1-3ubuntu5 | NOT used by attach_refs (it operates purely on JSON). Could be used by gallery thumbnail fallback if registry snapshot lacked image paths — but snapshot always carries `representative_image` (schema-required-pattern), so no ffmpeg needed. | n/a — Phase 8 does not extract frames. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Deterministic template join for `prompt_text` (PROMPT-02) | LLM rewrite / leave untouched | LLM = non-deterministic + new dep + latency; "leave untouched" violates PROMPT-02 explicit requirement. Template join is deterministic + idempotent + zero-dep. CONTEXT Q2 locks template. |
| Embed `registry_snapshot` inside `asset.json#generator` (PROMPT-04) | Separate `registry.json` file alongside / content-hash only / full blob | Separate file = consumer must read 6+ files (breaks self-describing manifest promise); content-hash can't resolve refs offline; full blob bloats 10-50× (REQUIREMENTS Out-of-Scope already rejected base64 for the same reason). Compact embedded snapshot = export-time truth, single-file read. |
| In-page `#<id>` anchors for chips (PRESENT-02) | JS scroll-to-handler / server-side routing | In-page anchors = zero JS, zero server, browser-native smooth scroll (CSS already sets `scroll-behavior:smooth` at line 132). Matches monolithic self-contained HTML pattern. |
| Inline `_esc()` (Phase 7 CR-04 carry-over) | `from html import escape` | Phase 7 CR-04 fix `336d04f` deliberately chose inline impl: the local `html/` directory is a namespace package and shadows the stdlib `html` module on import resolution. Inline `_esc()` avoids the ambiguity + matches standalone-script convention. |

**Installation:**
```bash
# 本 phase 零新依赖 — jsonschema 4.26.0 v1.0 baseline；Phase 6 已装 + 验证；ffmpeg 不用。
pip show jsonschema   # Version: 4.26.0
python3 -c "import jsonschema; print(jsonschema.__version__)"  # 4.26.0
```

**Version verification (executed during research):**
- `python3 -c "import jsonschema; print(jsonschema.__version__)"` → `4.26.0` (DeprecationWarning on `.__version__` access — cosmetic)
- `python3 -c "import httpx; print(httpx.__version__)"` → `0.28.1` (still present from Phase 6; not used by attach_refs but confirms env unchanged)
- `ffmpeg -version` → `6.1.1-3ubuntu5` (NOT used this phase — attach_refs is JSON-only)
- `python3 --version` → `3.12.3`

## Package Legitimacy Audit

> **Zero new packages this phase.** `jsonschema` is v1.0 baseline; `httpx` (Phase 6) is unused by `attach_refs.py`. No `pip install` is part of Phase 8. Per Package Legitimacy Protocol graceful-degradation: when zero new packages are introduced, the audit is trivially clean.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `jsonschema` | PyPI | ~14 yrs (4.26.0 current) | 顶层包（被 黑/redshift/etc 依赖） | github.com/python-jsonschema/jsonschema | n/a (v1.0 baseline, no new install) | Approved — v1.0 baseline; Phase 5-7 已用 + 验证；planner 无需 checkpoint |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Note（zero new deps）：** Phase 8 唯一 Python 包是 `jsonschema`（v1.0 baseline）+ stdlib。`httpx` 虽在 env 但本 phase 不用（attach_refs 纯 JSON 后处理，零网络）。

## Architecture Patterns

### System Architecture Diagram

```
   ┌── characters.json ── ── ── ── ── ── ── ──┐
   │   (Phase 7 apply_edits 产物, confirmed)    │
   │── props.json ── ── ── ── ── ── ── ── ── ──│
   │── prompts.json ── ── ── ── ── ── ── ── ── │
   │   (Phase 6 step_semantic 产物, 可能空 facets)│
   │                                            │
   ▼                                            │
  ┌──────────────────────────────┐              │
  │ run_pipeline.py:main()       │              │
  │  [1] codec                   │              │
  │  [2] detect → shots.json ────┼──────────────┘
  │  [3] separate                │
  │  [4] transcribe              │
  │  [5] semantic (prompts.json) │
  │  [6] step_reid → draft +     │
  │       review HTML (offline   │
  │       apply_edits →          │
  │       characters.json/       │
  │       props.json)            │
  │  [7] step_timeline ◄───────── NEW wiring point (this phase)
  │       │                      │
  │       │  ┌─────────────────────────────────────────┐
  │       └──► prompts/attach_refs.py (NEW — pre-step) │
  │          │  1. load characters.json/props.json     │
  │          │     (confirmed registry — Phase 7)      │
  │          │  2. build shot_id → [char_ids/prop_ids] │
  │          │     by inverting appearance_shots[]     │
  │          │  3. attach character_refs[]/prop_refs[] │
  │          │     to each prompts.json entry (sorted) │
  │          │  4. recompose prompt_text deterministic │
  │          │     (template join, see Pattern 2)      │
  │          │  5. jsonschema validate prompts.schema  │
  │          │  6. atomic write prompts.json in-place  │
  │          │     (idempotent byte-identical re-run)  │
  │          │  GRACEFUL: characters.json/props.json   │
  │          │   absent → refs empty, prompt_text      │
  │          │   recomposed from facets alone (no      │
  │          │   identity clause); exit 0; schema-valid│
  │          └─────────────────────────────────────────┘
  │       │
  │       ▼ prompts.json now has refs + recomposed prompt_text
  │  ┌─────────────────────────────────────────┐
  │  │ html/gen_timeline_html.py (MODIFY)       │
  │  │  - reads characters.json/props.json OR   │
  │  │    embedded registry_snapshot            │
  │  │  - gallery section: cards with external  │
  │  │    PNGs (serve.py Range-served) +        │
  │  │    _esc(name) + appearance count         │
  │  │  - per-shot row: reference chips as      │
  │  │    in-page #<id> anchors (after          │
  │  │    .type-badge)                          │
  │  │  - per-shot semantic-fill chip:          │
  │  │    green if camera/action/lighting/style │
  │  │    non-empty, else gray                  │
  │  │  - JSON-in-<script>: replace "</" "<\/"  │
  │  │    (CR-04 carry-over); _esc all operator │
  │  │    strings                               │
  │  └─────────────────────────────────────────┘
  │       │ timeline.html
  │       ▼
  │  [8] step_export → asset.json
  │       │
  │       ▼
  │  ┌──────────────────────────────────────────────┐
  │  │ scripts/export_asset.py (MODIFY build_asset_  │
  │  │  dict) — Phase 8 PROMPT-04                    │
  │  │  WHEN characters.json + props.json exist:     │
  │  │    emit generator.registry_snapshot = {       │
  │  │      characters: [{id, name,                  │
  │  │        representative_image, appearance_shots}│
  │  │      ], props: [{...}]}                       │
  │  │    containing ONLY review_state:"confirmed"   │
  │  │    (Pitfall 7 consistent)                     │
  │  │  ELSE: omit (graceful-degrade, byte-identical │
  │  │    to v1.0 — schema optional property)        │
  │  │  schema_version stays "1.1" (NO bump)         │
  │  └──────────────────────────────────────────────┘
  │
  └── scripts/verify_contract.py (MODIFY _producer_registry_integrity)
       ADD: prompts.character_refs[]/prop_refs[] ⊆ confirmed
            characters.json/props.json IDs (PROMPT-03, Pitfall 17)
            [fixture-side _fixture_consistency_check already does
             this — producer-side mirror]
```

### Recommended Project Structure（Phase 8 增量）

```
prompts/                                   # 已存在（Phase 5/6）
├── merge_prompts.py                       # 已有
├── extract_frames.py                      # 已有
└── attach_refs.py                         # NEW — attach refs + recompose prompt_text
                                            #        (standalone CLI, mirrors merge_prompts.py)
html/                                      # 已存在
└── gen_timeline_html.py                   # MODIFY — gallery section + chips + indicator
                                            #        + _esc() helper + JSON-in-script escape
spec/schemas/                              # 已存在
└── asset.schema.json                      # MODIFY — additive generator.registry_snapshot
spec/fixtures/v1.1/                        # 已存在（10 fixtures）
└── asset.json                             # MODIFY — example registry_snapshot field
scripts/                                   # 已存在
├── export_asset.py                        # MODIFY — emit registry_snapshot when registry exists
├── verify_contract.py                     # MODIFY — _producer_registry_integrity +prompts↔registry
└── verify_phase8_smoke.py                 # NEW — 6-scenario regression (mirror verify_phase7_smoke.py)
run_pipeline.py                            # MODIFY — step_timeline invokes attach_refs as pre-step
                                           #         (NO new numbered step / NO [N/8]→[N/9] bump)
output/<asset>/                            # 运行时产物（不变）
├── prompts.json                           # 现含 character_refs[]/prop_refs[] + recomposed prompt_text
└── asset.json                             # 现含 generator.registry_snapshot（条件性 emit）
```

### Pattern 1: attach_refs.py mirrors prompts/merge_prompts.py (standalone CLI)

**What:** `attach_refs.py` is a sibling of `merge_prompts.py` + `extract_frames.py` — same standalone CLI pattern (argparse + `main()` + `if __name__=="__main__"`), invoked by absolute path via `subprocess.run([sys.executable, str(HERE / "prompts" / "attach_refs.py"), ...])`.
**When to use:** Always — `step_timeline` invokes it as a pre-step before `gen_timeline_html.py`.

```python
# Source: prompts/merge_prompts.py (DIRECT template, line-by-line analog) +
#         Phase 5 prompts.schema.json (already permits character_refs[]/prop_refs[])
#         + CONTEXT Q1/Q2 lock.
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPTS_SCHEMA = REPO / "spec" / "schemas" / "prompts.schema.json"


def _atomic_write(path: str, data) -> None:
    """temp + os.replace（mirror export_asset.py:402-405）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_registry(work_dir: str) -> tuple[list, list]:
    """读 characters.json + props.json；任一缺席 → 返 [] for that side
    （graceful-degrade — refs empty，prompt_text 仍可重组自 facets）。"""
    chars, props = [], []
    cp = os.path.join(work_dir, "characters.json")
    pp = os.path.join(work_dir, "props.json")
    if os.path.isfile(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                # 仅 confirmed 条目参与 prompt refs（Pitfall 7 consistent）
                chars = [c for c in loaded
                         if isinstance(c, dict)
                         and c.get("review_state") == "confirmed"]
        except (OSError, json.JSONDecodeError):
            pass   # 静默降级 — 不阻断 timeline 生成
    if os.path.isfile(pp):
        try:
            with open(pp, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                props = [p for p in loaded
                         if isinstance(p, dict)
                         and p.get("review_state") == "confirmed"]
        except (OSError, json.JSONDecodeError):
            pass
    return chars, props


def attach(prompts: list, chars: list, props: list) -> list:
    """对每个 prompt 条目挂 character_refs[]/prop_refs[]。
    Idempotent: 同输入 → 同输出（sorted refs; prompt_text recomposed deterministic）。
    """
    # 反向索引：shot_id → [char_id, ...] (sorted for determinism)
    char_by_shot: dict[int, list[str]] = {}
    name_by_char: dict[str, str] = {}
    for c in chars:
        cid = c.get("id")
        name_by_char[cid] = c.get("name", cid)
        for sid in c.get("appearance_shots") or []:
            char_by_shot.setdefault(sid, []).append(cid)
    prop_by_shot: dict[int, list[str]] = {}
    name_by_prop: dict[str, str] = {}
    for p in props:
        pid = p.get("id")
        name_by_prop[pid] = p.get("name", pid)
        for sid in p.get("appearance_shots") or []:
            prop_by_shot.setdefault(sid, []).append(pid)

    out = []
    for entry in prompts:
        sid = entry.get("shot_id")
        crefs = sorted(set(char_by_shot.get(sid, [])))   # sorted = idempotent
        prefs = sorted(set(prop_by_shot.get(sid, [])))
        new_entry = dict(entry)   # 浅拷贝 — 保留所有现有 facet 字段
        new_entry["character_refs"] = crefs
        new_entry["prop_refs"] = prefs
        new_entry["prompt_text"] = _recompose(
            entry, crefs, prefs, name_by_char, name_by_prop)
        out.append(new_entry)
    return out


def _recompose(entry, crefs, prefs, name_by_char, name_by_prop) -> str:
    """PROMPT-02 deterministic template — see Pattern 2 for full spec."""
    # ... (see Pattern 2 below for exact template)
    pass


def main():
    ap = argparse.ArgumentParser(description="为 prompts.json 挂 character_refs/prop_refs + recompose prompt_text")
    ap.add_argument("--prompts", required=True, help="prompts.json 路径（in-place rewrite）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（含 characters.json/props.json）")
    ap.add_argument("--output", default=None,
                    help="输出路径（默认 = --prompts，in-place）")
    args = ap.parse_args()

    with open(args.prompts, encoding="utf-8") as f:
        prompts = json.load(f)
    if not isinstance(prompts, list):
        sys.exit(f"prompts.json expected JSON array, got {type(prompts).__name__}")

    chars, props = _load_registry(args.work_dir)
    out = attach(prompts, chars, props)

    # Pre-write schema validate（fails loud — 项目惯例）
    from jsonschema import Draft202012Validator
    with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    errors = sorted(Draft202012Validator(schema).iter_errors(out),
                    key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        sys.exit(f"attach_refs output failed prompts.schema ({len(errors)} errors):\n"
                 + "\n".join(lines))

    out_path = args.output or args.prompts
    _atomic_write(out_path, out)
    print(f"[attach-refs] {len(out)} shots + "
          f"{sum(len(c.get('character_refs',[])) for c in out)} char refs + "
          f"{sum(len(c.get('prop_refs',[])) for c in out)} prop refs → {out_path}")


if __name__ == "__main__":
    main()
```

### Pattern 2: prompt_text deterministic recompose template (PROMPT-02)

**What:** A single canonical template that injects character/prop identity (resolved names) into `prompt_text`, combining the 6 existing facets in a fixed order. Idempotent + deterministic. Identity clause omitted when no refs.
**When to use:** Every shot in `attach()`.

**Template (locked):**
```
[style] · [scene] · 角色:[name1, name2] · 道具:[name1] · [subject] · [action] · [camera] · [lighting]
```

When `character_refs` empty: omit the `角色:[...]` clause (skip the separator too).
When `prop_refs` empty: omit the `道具:[...]` clause (skip the separator too).
When both empty: `prompt_text` = `[style] · [scene] · [subject] · [action] · [camera] · [lighting]` (no identity clause at all).
When any facet empty: skip that facet (skip the separator too).

```python
# Source: CONTEXT Q2 lock + REQUIREMENTS PROMPT-02
# Deterministic: same facets + same refs → byte-identical output.
# Idempotent: re-running attach_refs produces the same prompt_text.
# Names come ONLY from confirmed registry (no fabrication).
_SEP = " · "   # 全角分隔（视觉清晰；不与逗号混）

def _recompose(entry, crefs, prefs, name_by_char, name_by_prop) -> str:
    """Deterministic identity-injecting recomposition.

    Template (locked by CONTEXT Q2 Claude's Discretion on prose):
      [style] · [scene] · 角色:[name1, name2] · 道具:[name1] · [subject] · [action] · [camera] · [lighting]

    Empty facets are skipped (no trailing separators).
    Identity clauses skipped when refs empty.
    """
    parts: list[str] = []

    # Facet parts — fixed order, skip empties
    for facet in ("style", "scene"):
        v = (entry.get(facet) or "").strip()
        if v:
            parts.append(v)

    # Identity clauses (only when refs present)
    if crefs:
        names = [name_by_char.get(cid, cid) for cid in crefs]
        parts.append(f"角色:[{', '.join(names)}]")
    if prefs:
        names = [name_by_prop.get(pid, pid) for pid in prefs]
        parts.append(f"道具:[{', '.join(names)}]")

    # Remaining facets
    for facet in ("subject", "action", "camera", "lighting"):
        v = (entry.get(facet) or "").strip()
        if v:
            parts.append(v)

    return _SEP.join(parts)
```

**Worked example on v1.1 fixture (shot 1):**
- Input facets: `style="3D 动画,写实渲染,柔和色彩"`, `scene="明亮城市街道,远景有树"`, `subject="少女,白色衣裙"`, `action="从画面左侧走入,举手打招呼"`, `camera="中景平视,固定机位"`, `lighting="自然日光,顺光,亮调"`.
- `character_refs=["char_001", "char_002"]` → names `["少女", "路人"]` (from fixture `characters.json`).
- `prop_refs=[]` → no 道具 clause.
- Recomposed `prompt_text`:
  ```
  3D 动画,写实渲染,柔和色彩 · 明亮城市街道,远景有树 · 角色:[少女, 路人] · 少女,白色衣裙 · 从画面左侧走入,举手打招呼 · 中景平视,固定机位 · 自然日光,顺光,亮调
  ```
- Shot 2 (`character_refs=["char_001"]`, `prop_refs=["prop_001"]`, facets per fixture):
  ```
  3D 动画,写实渲染,浅景深 · 城市街道,路面湿润 · 角色:[少女] · 道具:[落叶] · 街道特写,落叶飘过 · 镜头缓缓推近,一片落叶飘过前景 · 近景缓推 · 侧逆光,金色暖调
  ```

**Idempotency guarantee:** Re-running `attach_refs.py` on the output of a previous run produces byte-identical `prompt_text` because:
1. Refs come from registry inversion (same registry → same refs, sorted deterministically).
2. Names come from registry `name` field (stable unless registry re-edited).
3. Template is fixed order with empty-skip — no nondeterministic branching.

**Graceful-degrade when no refs:** When `characters.json`/`props.json` absent (registry not yet produced / route-down), `attach()` produces `character_refs=[]` + `prop_refs=[]` for every shot, and `_recompose()` skips the identity clauses. `prompt_text` = facets-only template. Schema-valid. Phase 6's empty-facets degrade case (route-down) → `prompt_text` = empty string (all facets skipped) — also schema-valid (`prompts.schema.json:67` allows empty string).

### Pattern 3: registry_snapshot freeze shape + export emission (PROMPT-04)

**What:** Compact frozen view of confirmed registry entries, embedded in `asset.json#generator`. Contains enough for a consumer to resolve prompt refs + render a gallery WITHOUT re-reading external `characters.json`/`props.json`.
**When to use:** `export_asset.py#build_asset_dict` emits it whenever `characters.json`/`props.json` exist on disk.

**Shape (locked by CONTEXT Q1):**
```json
{
  "characters": [
    {
      "id": "char_001",
      "name": "少女",
      "representative_image": "characters/char_001.png",
      "appearance_shots": [1, 2]
    }
  ],
  "props": [
    {
      "id": "prop_001",
      "name": "落叶",
      "representative_image": "props/prop_001.png",
      "appearance_shots": [2]
    }
  ]
}
```

**Compact by design:** omits `looks[]`/`states[]` (consumer reads canonical files for fine-grained per-look/per-state detail if needed; the snapshot covers prompt-ref resolution + gallery thumbnails). Includes `representative_image` so consumers can render gallery cards without round-tripping back to producer filesystem.

```python
# Source: scripts/export_asset.py build_asset_dict (modify in place, mirror Phase 7
#         conditional emission at lines 197-220)
def _build_registry_snapshot(work_dir: str) -> dict | None:
    """读 characters.json + props.json → compact confirmed-only snapshot。

    Returns None when neither file exists (graceful-degrade — asset byte-identical
    to v1.0). Confirmed-only hard filter (Pitfall 7 consistent — same gating as
    apply_edits.py build-time hard gate + _producer_registry_integrity assert).
    """
    chars_path = os.path.join(work_dir, "characters.json")
    props_path = os.path.join(work_dir, "props.json")
    if not (os.path.isfile(chars_path) or os.path.isfile(props_path)):
        return None   # 无 registry → snapshot 字段 OMITTED（schema optional）

    def _project(entries):
        out = []
        if isinstance(entries, list):
            for e in entries:
                if not isinstance(e, dict):
                    continue
                if e.get("review_state") != "confirmed":
                    continue   # Pitfall 7 — confirmed-only snapshot
                out.append({
                    "id": e.get("id"),
                    "name": e.get("name"),
                    **({"representative_image": e["representative_image"]}
                       if e.get("representative_image") else {}),
                    "appearance_shots": e.get("appearance_shots") or [],
                })
        return out

    snapshot = {}
    if os.path.isfile(chars_path):
        try:
            with open(chars_path, encoding="utf-8") as f:
                snapshot["characters"] = _project(json.load(f))
        except (OSError, json.JSONDecodeError):
            snapshot["characters"] = []
    if os.path.isfile(props_path):
        try:
            with open(props_path, encoding="utf-8") as f:
                snapshot["props"] = _project(json.load(f))
        except (OSError, json.JSONDecodeError):
            snapshot["props"] = []
    return snapshot


# In build_asset_dict (extend the generator block):
snapshot = _build_registry_snapshot(work_dir)
# ... existing return dict ...
"generator": {
    "tool": "kais-shot-timeline",
    "version": _git_sha(),
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    **({"warnings": warnings} if warnings else {}),
    # Phase 8: registry_snapshot (PROMPT-04) — additive, conditional emit
    **({"registry_snapshot": snapshot} if snapshot is not None else {}),
},
```

**Schema declaration (REQUIRED — `additionalProperties:false` strict):**
```jsonc
// asset.schema.json#generator.properties — add:
"registry_snapshot": {
  "type": "object",
  "additionalProperties": false,
  "required": ["characters", "props"],
  "description": "v1.1 additive (OPTIONAL — Phase 8). Frozen-at-export-time compact view of confirmed registry entries (characters + props). Embeds enough for a consumer to resolve prompts.character_refs[]/prop_refs[] and render a gallery WITHOUT re-reading external characters.json/props.json. Later registry mutations (re-review, re-cluster) cannot invalidate already-exported prompt references (Pitfall 18 prevented). Older assets omit it and still validate (graceful-degrade). Producer emits the field only when characters.json or props.json exists at export time; absent on assets produced without re-id (v1.0 byte-identical).",
  "properties": {
    "characters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "name", "appearance_shots"],
        "properties": {
          "id": {"type": "string", "pattern": "^char_[0-9]{3}$"},
          "name": {"type": "string", "minLength": 1},
          "representative_image": {
            "type": "string",
            "pattern": "^(?!.*\\.\\.)([^/]+/)*characters/[^:*?\"<>|]+\\.png$"
          },
          "appearance_shots": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1}
          }
        }
      }
    },
    "props": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "name", "appearance_shots"],
        "properties": {
          "id": {"type": "string", "pattern": "^prop_[0-9]{3}$"},
          "name": {"type": "string", "minLength": 1},
          "representative_image": {
            "type": "string",
            "pattern": "^(?!.*\\.\\.)([^/]+/)*props/[^:*?\"<>|]+\\.png$"
          },
          "appearance_shots": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1}
          }
        }
      }
    }
  }
}
```

**Why freeze (Pitfall 18 prevention):** Once `asset.json` is written, the snapshot is the **export-time truth**. If a reviewer later re-edits the registry (re-review, re-cluster, rename, merge), the canonical `characters.json`/`props.json` on the producer filesystem changes — but already-exported `asset.json#generator.registry_snapshot` does NOT. Downstream consumers reading the old asset still see consistent prompt references that resolve via the embedded snapshot. Without the freeze, an old asset's `character_refs: ["char_001"]` could resolve to a renamed entity in the live registry (narrative continuity broken).

### Pattern 4: HTML XSS hardening — carry Phase 7 CR-04 fix `336d04f` verbatim

**What:** Phase 7 review found `gen_registry_review.py` XSS via unescaped route/operator-controlled strings in (a) HTML body spans and (b) inline `<script>const DRAFT = {...}</script>` JSON literal. Fix `336d04f` added self-contained `_esc()` (5-char HTML escape) for body + `.replace("</", "<\\/")` after `json.dumps` for inlined JSON.
**When to use:** Every interpolation of operator-influenced string into HTML; every `json.dumps` whose result lands inside a `<script>` block.

**Phase 8 mandatory application** — operator-influenced strings now flow into `gen_timeline_html.py`:
- `character.name` / `prop.name` (registry-reviewer-editable per `characters.schema.json:21`)
- `character.id` / `prop.id` (schema-pattern-locked but escape anyway as defense-in-depth)
- These land in: gallery card HTML body, chip badges, AND inlined `const CHARACTERS = {...}` JSON literal in `<script>`.

```python
# Source: html/gen_registry_review.py:79-91 (Phase 7 CR-04 fix commit 336d04f)
# Copy verbatim into gen_timeline_html.py at module top.
def _esc(s):
    """HTML-escape 字符串以安全插值进 HTML text/attribute context (CR-04 XSS defense).

    转义 5 个字符: & < > " '. 顺序固定 (& 先，防双重转义)。
    Self-contained inline impl (不走 stdlib html.escape) —— 本仓库 html/ 目录是
    namespace package，避免任何 import-resolution 歧义；符合 standalone-script 约定。
    输入先 str() 兜底 (非 string 字段如 int shot_id 也安全)。
    """
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;"))


# JSON-in-<script> defense (CR-04 fix):
# After json.dumps for any data inlined into a <script> block:
chars_json = json.dumps(chars_data, ensure_ascii=False).replace("</", "<\\/")
shots_json = json.dumps(shots_js, ensure_ascii=False).replace("</", "<\\/")
# `\/` is a valid JS escape for `/`, so client-side data round-trips correctly
# while `</script>` can no longer terminate the script block.
```

**Why this is non-negotiable for Phase 8:**
- The `<phase_context>` of Phase 7 review explicitly lists "operator-supplied input trust" as a focus area. `characters.name` is **registry-reviewer-editable** (HITL review HTML lets operator rename). A reviewer typing `name: "</script><script>alert(1)</script>"` for a character — or a route/cache poisoning flow — produces HTML that executes scripts in the operator's browser when the timeline is opened.
- Schema constraints (`minLength: 1`) are defense-in-depth, NOT a substitute for output escaping (CR-04 lesson verbatim: "schema constraints are defense-in-depth, not a substitute for output escaping").
- Phase 7 fix precedent (`336d04f`) is the canonical pattern — applying it to `gen_timeline_html.py` is mechanical, not exploratory.

### Pattern 5: verify_contract.py prompt↔registry integrity extension (PROMPT-03)

**What:** Extends Phase 7's `_producer_registry_integrity` (`verify_contract.py:492-590`) with the prompts→registry direction. Phase 7 added registry↔shots; Phase 8 adds prompts→registry.
**When to use:** Producer mode (`verify_contract.py --mode=producer`) — runs against real ep01 asset dir.

```python
# Source: scripts/verify_contract.py:492-590 (Phase 7 _producer_registry_integrity)
# Phase 8 extension — additive, gated on file existence (mirror Phase 7 graceful-degrade).

# Inside _producer_registry_integrity, after the existing characters/props checks:
prompts_path = asset_dir / "prompts.json"
if prompts_path.is_file():
    try:
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        failures.append(f"prompts.json: invalid JSON: {e}")
    else:
        if isinstance(prompts, list):
            # Build confirmed-ID sets (already populated above in chars/props loops)
            # char_confirmed_ids = {e["id"] for e in chars if e.get("review_state")=="confirmed"}
            # prop_confirmed_ids = {e["id"] for e in props if ...}
            for entry in prompts:
                if not isinstance(entry, dict):
                    continue
                sid = entry.get("shot_id")
                for cref in entry.get("character_refs", []) or []:
                    if cref not in char_confirmed_ids:
                        failures.append(
                            f"prompts.json shot {sid}: character_ref {cref!r} "
                            f"not in confirmed characters.json IDs (Pitfall 17 — "
                            f"prompt dangling ref)")
                for pref in entry.get("prop_refs", []) or []:
                    if pref not in prop_confirmed_ids:
                        failures.append(
                            f"prompts.json shot {sid}: prop_ref {pref!r} "
                            f"not in confirmed props.json IDs (Pitfall 17)")
```

**Note:** Fixture-side `_fixture_consistency_check` (`verify_contract.py:440-447`) already does this for the v1.1 fixture set — so the **fixture regression will catch** any attach_refs bug that produces a dangling ref against the fixture. The producer-side extension here is the runtime gate (against real ep01 asset dir).

### Pattern 6: step_timeline integration — NO counter bump

**What:** `step_timeline` invokes `prompts/attach_refs.py` as a pre-step BEFORE `gen_timeline_html.py`. CONTEXT Q3 lock — NO new `[N/M]` slot, NO `[N/8]`→`[N/9]` renumber.
**When to use:** Modify `step_timeline` (`run_pipeline.py:316-343`) to add a pre-step invocation.

```python
# Source: run_pipeline.py:316-343 (step_timeline) + CONTEXT Q3 lock.
# Insert attach_refs invocation AFTER step_reid (which produces characters.json/
# props.json via the operator's offline apply_edits.py run) and BEFORE
# gen_timeline_html.py.
def step_timeline(video: str, work_dir: str, shots_json: str,
                  audio_json: str, transcript: str, frames_json: str,
                  stems_dir: str, out_html: str, video_src: str,
                  stem_basename: str,
                  prompts_json: str) -> str:   # NEW arg
    # Phase 8: invoke attach_refs as a pre-step (NO own [N/M] banner)
    # — modifies prompts.json in place BEFORE gen_timeline_html.py reads it.
    # Idempotent; fails-loud on schema-invalid output.
    # GRACEFUL: characters.json/props.json absent → refs empty, prompt_text
    # recomposed from facets alone; exit 0.
    if prompts_json and os.path.exists(prompts_json):
        cmd_refs = [sys.executable, str(HERE / "prompts" / "attach_refs.py"),
                    "--prompts", prompts_json,
                    "--work-dir", work_dir]
        run_step(cmd_refs, "[7/8] prompt-ref attachment (attach_refs)")  # REUSES existing [7/8] banner
    # ... existing step_timeline body (mtime cache + gen_timeline_html.py call) ...
```

**Why NO counter bump (CONTEXT Q3):**
- ROADMAP Phase 8 success criteria do NOT call for a new pipeline step.
- `attach_refs` is a deterministic post-processor, not a stage with its own failure modes / cache.
- `[N/8]` lock from Phase 7 (CONTEXT D-XX) is preserved — Phase 8 stays at `[N/8]`.
- Banner `[7/8] prompt-ref attachment` reuses the existing `step_timeline` slot's `[7/8]` prefix, clearly signaling it's part of timeline assembly.

### Pattern 7: gen_timeline_html.py gallery + chips + indicator

**What:** Three additive UI extensions to `build_html` (`gen_timeline_html.py:99-944`):
1. **Gallery section** above the two-panel layout.
2. **Reference chips** appended to each shot-row template.
3. **Semantic-fill indicator** chip per shot.

**Layout (reuse GitHub-dark palette):**
- Gallery: horizontal card row at top of `.app`, sticky above panels (or simple section). Each card = thumbnail + name + ID + appearance count.
- Chips: append after `.type-badge` in the existing shot-row innerHTML (`gen_timeline_html.py:369` and `:822`).
- Indicator: a small colored chip after `.times` line.

```python
# Source: gen_timeline_html.py:365-371 (existing shot-row template) + CONTEXT Q1/Q2/Q3

# In build_html signature — extend with registry data + warnings:
def build_html(shots_js, stems_js, duration, video_src, title,
               stem_basename, n_dialogue=None, n_bgm=None, n_sfx=None,
               n_shots=None, transcript_segments=None,
               # Phase 8 NEW args:
               characters_data=None, props_data=None,
               route_warnings=None):   # from asset.json#generator.warnings
    # ...
    # Inlined JSON — ALL with </ -> \/ defense (Pattern 4):
    chars_json = json.dumps(characters_data or [], ensure_ascii=False).replace("</", "<\\/")
    props_json = json.dumps(props_data or [], ensure_ascii=False).replace("</", "<\\/")
    shots_json = json.dumps(shots_js, ensure_ascii=False).replace("</", "<\\/")
    # ...
```

```javascript
// In the inlined <script> — Phase 8 extensions:

// 1. Per-shot reference chips (appended to shot-row template):
//    (in both buildShotList and rebuildAdaptive, lines 365 + 818)
const refChips = (s.character_refs||[]).map(cid => {
    const c = CHARACTERS.find(x => x.id === cid);
    const name = c ? c.name : cid;
    return `<a href="#gallery-${cid}" class="ref-chip char-chip" title="${_esc(name)}">🧑 ${_esc(name)}</a>`;
}).join('') + (s.prop_refs||[]).map(pid => {
    const p = PROPS.find(x => x.id === pid);
    const name = p ? p.name : pid;
    return `<a href="#gallery-${pid}" class="ref-chip prop-chip" title="${_esc(name)}">🔧 ${_esc(name)}</a>`;
}).join('');

// 2. Semantic-fill indicator:
//    route_filled = any of camera/action/lighting/style non-empty
const filled = (s.camera && s.action && s.lighting && s.style);
const fillChip = filled
    ? '<span class="fill-chip fill-filled" title="运镜分析已路由填充">✓ 运镜</span>'
    : '<span class="fill-chip fill-degraded" title="运镜分析 offline 降级">○ 降级</span>';

// 3. Append to existing row template:
row.innerHTML = `<span class="num">${s.id}</span>`
    + `<div class="body">`
    + `<div class="thumbs"><img src="${s.ff}"><span class="arrow">→</span><img src="${s.lf}"></div>`
    + `<div class="times">${s.start.toFixed(1)}→${s.end.toFixed(1)} <span class="${durCls}">(${s.dur}s)</span>`
    + `<span class="type-badge type-${s.type}">${typeIcons[s.type]||''} ${s.type}</span>`
    + `${refChips}${fillChip}</div>`                  // NEW: chips + indicator
    + `<div class="dlg">${dlg}</div>`
    + `</div>`;
```

```css
/* Add to existing <style> block (gen_timeline_html.py:131-202 palette):
   ref-chip / fill-chip styles — reuse #58a6ff (char blue), #d29922 (prop yellow),
   #3fb950 (filled green), #8b949e (degraded gray). */
.ref-chip { display:inline-block; font-size:9px; padding:0 4px; border-radius:2px;
            margin-left:3px; text-decoration:none; vertical-align:middle; }
.char-chip { background:#1a3a5e; color:#58a6ff; }
.prop-chip { background:#3e351a; color:#d29922; }
.ref-chip:hover { background:#264f78; }   /* char hover */
.prop-chip:hover { background:#5e4a1a; }
.fill-chip { display:inline-block; font-size:9px; padding:0 4px; border-radius:2px;
             margin-left:3px; vertical-align:middle; }
.fill-filled { background:#1a3e1a; color:#3fb950; }
.fill-degraded { background:#2a2a3e; color:#8b949e; }

/* Gallery section */
.gallery { padding:8px 12px; background:#161b22; border-bottom:1px solid #30363d;
           display:flex; gap:8px; overflow-x:auto; }
.gallery-card { flex:0 0 auto; width:120px; background:#0d1117; border:1px solid #30363d;
                border-radius:4px; padding:4px; }
.gallery-card img { width:100%; aspect-ratio:1; object-fit:cover; border-radius:3px;
                    background:#161b22; }
.gallery-card .gname { font-size:11px; color:#c9d1d9; margin-top:2px; }
.gallery-card .gid { font-size:9px; color:#8b949e; font-family:monospace; }
.gallery-card .gcount { font-size:9px; color:#58a6ff; }
```

**Gallery card HTML (in Python f-string, generated server-side):**
```python
# In build_html, BEFORE the <div class="app">:
gallery_html = ""
if characters_data or props_data:
    cards = []
    for c in (characters_data or []):
        cards.append(
            f'<div class="gallery-card" id="gallery-{_esc(c.get("id"))}">'
            f'<img src="{_esc(c.get("representative_image",""))}" '
            f'  onerror="this.style.display=\'none\'">'   # graceful: missing PNG
            f'<div class="gname">{_esc(c.get("name"))}</div>'
            f'<div class="gid">{_esc(c.get("id"))}</div>'
            f'<div class="gcount">{len(c.get("appearance_shots",[]))} shots</div>'
            f'</div>')
    for p in (props_data or []):
        cards.append(
            f'<div class="gallery-card" id="gallery-{_esc(p.get("id"))}">'
            f'<img src="{_esc(p.get("representative_image",""))}" '
            f'  onerror="this.style.display=\'none\'">'
            f'<div class="gname">🔧 {_esc(p.get("name"))}</div>'
            f'<div class="gid">{_esc(p.get("id"))}</div>'
            f'<div class="gcount">{len(p.get("appearance_shots",[]))} shots</div>'
            f'</div>')
    gallery_html = f'<div class="gallery">{"".join(cards)}</div>'
```

**Thumbnail source strategy (CONTEXT Claude's Discretion — recommend registry_snapshot first):**
- Gallery reads `output/<asset>/asset.json#generator.registry_snapshot` when present (embedded truth — preferred).
- Falls back to `characters.json`/`props.json` when `asset.json` doesn't yet have the snapshot (e.g., pipeline re-run without export).
- Thumbnails = external PNG paths served via `scripts/serve.py` Range handler (already established for video/stems).
- `onerror="this.style.display='none'"` graceful-degrades a missing PNG (apply_edits might have OMITTED `representative_image` on ffmpeg failure — Phase 7 WARNING-2 lesson).

### Anti-Patterns to Avoid

- **LLM-based `prompt_text` rewrite (PROMPT-02)** — non-deterministic + adds dep + latency + fabrication risk; CONTEXT Q2 explicitly rejected.
- **`registry_snapshot` includes proposed/rejected entries** — violates Pitfall 7 confirmed-only gating that Phase 7 enforces everywhere else; breaks narrative continuity if downstream renders a rejected entity.
- **`registry_snapshot` lives as a separate file alongside asset.json** — breaks self-describing manifest promise (consumer reads 6+ files); CONTEXT Q1 rejected.
- **`attach_refs.py` invoked as a new `[N/9]` numbered step** — CONTEXT Q3 explicitly rejected counter bump.
- **`gen_timeline_html.py` interpolates `name` without `_esc()`** — Phase 7 CR-04 lesson; XSS via operator-influenced strings is reproducible (commit `336d04f` precedent).
- **`json.dumps(...)` inlined into `<script>` without `.replace("</", "<\\/")`** — Phase 7 CR-04 lesson; `</script>` in any string field terminates the script block.
- **Schema `additionalProperties:false` violated by undeclared `registry_snapshot`** — strict schema rejects it; MUST declare the property in `asset.schema.json#generator.properties`.
- **`schema_version` bumped to `"1.2"`** — STATE.md locks entire v1.1 milestone to `"1.1"` (additive-only = minor); bumping would break cross-version compatibility tests.
- **Producer-side integrity check duplicates fixture-side check logic** — Phase 7's `_producer_registry_integrity` already establishes the pattern; Phase 8 EXTENDS it (additive), doesn't fork.
- **Gallery hard-codes external PNG paths without `onerror` fallback** — `apply_edits.py` may OMIT `representative_image` on ffmpeg failure (Phase 7 WARNING-2); missing PNG would show broken icon.
- **Chip click requires server round-trip** — in-page `#<id>` anchors are zero-server (monolithic self-contained HTML pattern).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `character_refs` attachment | LLM / regex over prompt_text | Invert `appearance_shots[]` → shot_id map | Deterministic + idempotent + zero-dep; registry is already the truth. |
| `prompt_text` recompose | LLM rewrite / templating engine | Fixed-order template join (Pattern 2) | Deterministic + idempotent + zero-dep; CONTEXT Q2 locks template approach. |
| `registry_snapshot` serialization | Custom binary / content-hash | Plain JSON in `asset.json#generator` | Schema-valid; consumer reads single file; Phase 5-7 pattern. |
| HTML escape | stdlib `html.escape` import | Inline `_esc()` (Phase 7 CR-04 carry) | Local `html/` namespace-package shadows stdlib on import resolution — Phase 7 verified. |
| JSON-in-script defense | Custom regex over JSON | `json.dumps(...).replace("</", "<\\/")` | Standard JSON-in-HTML defense; `\/` is valid JS escape for `/`. |
| Per-shot ref-chip wiring | Server-side routing | In-page `#<id>` anchors + browser smooth scroll | CSS already sets `scroll-behavior:smooth` (line 132); zero JS, zero server. |
| Cross-file ID integrity | Custom verifier script | Extend `_producer_registry_integrity` | Phase 7 unified pattern; same exit-code contract. |
| Atomic write | `os.rename` / direct write | temp + `os.replace` (mirror export_asset.py:402-405) | Cross-platform atomic; partial-write protection (Phase 2 lesson). |
| Schema validation | Hand-written field check | `jsonschema.Draft202012Validator` | v1.0 baseline; Pattern proven across 4 phases. |
| Smoke harness | pytest fixture | Standalone `sys.exit(0/1)` (mirror `verify_phase7_smoke.py`) | CLAUDE.md / v1.0 RETROSPECTIVE: pytest-free is the project pattern. |

**Key insight:** Every Phase 8 surface has a DIRECT proven template in Phase 5-7. The riskiest item (PROMPT-02 deterministic template) is locked by CONTEXT — Claude's Discretion is over prose only, not mechanism. Do not re-litigate the mechanism.

## Runtime State Inventory

> Phase 8 is **greenfield-additive** in this repo (new files: `prompts/attach_refs.py`, `scripts/verify_phase8_smoke.py`; modified: `html/gen_timeline_html.py`, `scripts/export_asset.py`, `scripts/verify_contract.py`, `run_pipeline.py`, `spec/schemas/asset.schema.json`, `spec/fixtures/v1.1/asset.json`). No rename/refactor/migration of existing runtime state. SKIPPED (not a rename/refactor phase).

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — `attach_refs.py` rewrites `prompts.json` in-place (additive fields only; existing facets preserved byte-identical when refs empty) | None |
| Live service config | None — `serve.py` unchanged; gallery PNGs use the existing Range-aware handler | None |
| OS-registered state | None | None |
| Secrets/env vars | None — CLAUDE.md confirms no `.env`, all config via CLI flags | None |
| Build artifacts | None — no egg-info / compiled binaries; Python runs directly | None |

## Common Pitfalls

### Pitfall 1: HTML XSS via operator-influenced character/prop names (Phase 7 CR-04 carry-over)

**What goes wrong:** `gen_timeline_html.py` extension interpolates `character.name` / `prop.name` into gallery cards, chip badges, AND the inlined `const CHARACTERS = {...}` JSON literal. A reviewer-entered `name: "</script><script>alert(1)</script>"` (legal per `characters.schema.json:21` — only `minLength: 1`) produces HTML that executes the script when the timeline is opened.
**Why it happens:** Operator-influenced strings (registry names are HITL-reviewer-editable per `characters.schema.json#name` description "reviewer 可编辑") flow into HTML without escaping; same root cause as Phase 7 CR-04 (`gen_registry_review.py`).
**How to avoid:** Pattern 4 — apply `_esc()` (verbatim from `gen_registry_review.py:79-91`, commit `336d04f`) to every body/attribute interpolation; apply `.replace("</", "<\\/")` after every `json.dumps` whose result lands in a `<script>` block. Schema constraints are defense-in-depth, NOT a substitute.
**Warning signs:** Any `f'...{name}...'` or `f'...{cid}...'` in `gen_timeline_html.py` extension without `_esc()` wrapping. Any `const X = {json.dumps(...)}` without the `</`→`<\/` replace.

### Pitfall 2: `attach_refs.py` recompose not idempotent (re-run drift)

**What goes wrong:** Recompose template injects identity but order is unstable (e.g., dict iteration order of refs) → re-running `attach_refs` produces a slightly different `prompt_text` → mtime cache thinks prompts.json changed → downstream cache thrash.
**Why it happens:** Python dict preserves insertion order but the insertion order of `appearance_shots[]` inversion depends on the registry's list order; if registry is re-sorted, refs reorder.
**How to avoid:** Pattern 1 + Pattern 2 — `sorted(set(char_by_shot.get(sid, [])))` (sorted = stable regardless of registry list order). Template uses fixed facet order. Idempotency assert in `verify_phase8_smoke.py` scenario 2 (run attach twice, byte-diff).
**Warning signs:** `git diff output/<asset>/prompts.json` non-empty after re-running attach_refs without registry change.

### Pitfall 3: `registry_snapshot` includes non-confirmed entries (Pitfall 7 leak in new clothes)

**What goes wrong:** `_build_registry_snapshot` iterates `characters.json`/`props.json` without filtering `review_state:"confirmed"` → a `proposed` or `rejected` entry leaks into the snapshot → consumer renders an entity the operator never confirmed → narrative continuity breaks downstream.
**Why it happens:** Easy to forget the filter when projecting compact shape — "just project id/name/representative_image/appearance_shots" looks correct.
**How to avoid:** Pattern 3 — explicit `if e.get("review_state") != "confirmed": continue` in `_project()`. Mirror Phase 7 `apply_edits.py` build-time hard gate + `_producer_registry_integrity` second-line assert.
**Warning signs:** Snapshot contains an entry whose `id` matches a `review_state:"proposed"` entry in canonical `characters.json`. Smoke scenario 5 catches this.

### Pitfall 4: `asset.schema.json` `additionalProperties:false` rejects `registry_snapshot` (schema not extended)

**What goes wrong:** `export_asset.py` emits `generator.registry_snapshot`, but `asset.schema.json#generator.properties` was not updated → `validate_asset_json()` fails → `sys.exit` → no asset exported.
**Why it happens:** Phase 7's CONTRACT-06 emission worked because Phase 5 had already declared `data.characters`/`data.props`/`media.characters[]`/`media.props[]`. Phase 8's `registry_snapshot` is NEW — the schema declaration MUST ship in the same wave as the producer code (Wave 1 contract layer first, mirroring Phase 6 Plan 01 sequencing).
**How to avoid:** Wave 1 = schema + fixture (mirror Phase 6 Plan 01); Wave 2 = producer code. `validate_asset_json()` inline check is the safety net.
**Warning signs:** `asset.json failed schema validation (1 error(s)): at generator: Additional properties are not allowed ('registry_snapshot' was unexpected)`.

### Pitfall 5: Step-counter phantom bump (CONTEXT Q3 violation)

**What goes wrong:** Planner adds `step_prompt_refs` as a new numbered step → `[N/8]`→`[N/9]` renumber (24 occurrences) → unnecessary churn + breaks the Phase 7 counter lock (CONTEXT D-XX).
**Why it happens:** Tempting to mirror Phase 6/7 step structure; but Phase 8 success criteria don't call for a new pipeline stage.
**How to avoid:** Pattern 6 — `step_timeline` invokes `attach_refs.py` as a pre-step under the existing `[7/8]` banner (e.g., `[7/8] prompt-ref attachment` then `[7/8] timeline HTML generation`).
**Warning signs:** `git diff run_pipeline.py` shows `[N/9]` literals.

### Pitfall 6: Producer integrity check duplicates fixture check logic (DRY violation)

**What goes wrong:** Developer writes a new standalone `_prompt_ref_integrity()` function instead of extending `_producer_registry_integrity` → logic drifts between fixture check (`_fixture_consistency_check:440-447`) and producer check → fixture passes but producer fails (or vice versa) on the same logical bug.
**Why it happens:** Tempting to mirror the fixture check's structure in a new function; CONTEXT Q1 explicitly rejected a separate verifier.
**How to avoid:** Pattern 5 — extend Phase 7's `_producer_registry_integrity` (additive block at the end, after the existing characters/props/registry loops). Same failure-message format (Pitfall 17 reference).
**Warning signs:** Two functions in `verify_contract.py` both iterating `prompts.character_refs`.

### Pitfall 7: Gallery hardcodes external PNG paths without `onerror` fallback (Phase 7 WARNING-2 carry-over)

**What goes wrong:** `<img src="characters/char_001.png">` renders a broken icon when `apply_edits.py` OMITTED `representative_image` (ffmpeg failure / `WARNING-2` precedent) or the PNG was deleted post-export.
**Why it happens:** `representative_image` is schema-OPTIONAL (Phase 7 graceful-degrade — non-fatal ffmpeg failure → omit field, no dangling path reaches manifest).
**How to avoid:** Pattern 7 — `onerror="this.style.display='none'"` on every gallery `<img>`; the card still shows name/ID/count without the thumbnail.
**Warning signs:** Broken-image icons in gallery when running against an asset where ffmpeg failed for some character.

### Pitfall 8: Semantic-fill indicator false-negative on partial route fill

**What goes wrong:** Indicator shows "degraded" (gray) for a shot that has camera+action filled but lighting+style empty (per-shot route failure non-fatal per CINEMA-05).
**Why it happens:** Naive check `if any(facet)` vs strict `if all(facets)` — the spec calls for "green = route filled" but partial fill is ambiguous.
**How to avoid:** Pattern 7 — define `filled = (s.camera && s.action && s.lighting && s.style)` (ALL non-empty = green, ANY empty = gray). Document the semantics in the chip title attribute (`title="运镜分析已路由填充"` vs `title="运镜分析 offline 降级"`). Alternative: any-filled = green, none-filled = gray (more lenient). Pick one and lock it (recommend ALL-non-empty = green, mirroring "full route success").
**Warning signs:** Indicator color disagrees with operator expectation when route filled some facets.

### Pitfall 9: `attach_refs.py` modifies prompts.json but cache thinks timeline unchanged

**What goes wrong:** `step_timeline` mtime cache (`run_pipeline.py:320-323`) checks if `out_html` is newer than inputs (`shots.json`, `audio.json`, `transcript.json`). If `prompts.json` was rewritten by `attach_refs` but isn't in the cache key set, the timeline regenerates without picking up the new refs/chips.
**Why it happens:** `step_timeline` cache currently keys on shots/audio/transcript — NOT prompts. `attach_refs` rewrites prompts but `step_timeline` doesn't notice.
**How to avoid:** Add `prompts_json` to the `step_timeline` mtime cache inputs (mirror Phase 6 `step_export:391-399` pattern that already includes prompts.json in its cache). Cache miss → timeline regenerates → gallery/chips reflect new refs.
**Warning signs:** Timeline HTML missing chips after first `attach_refs` run; second run (cache miss forced via `--force`) shows them.

### Pitfall 10: Schema `schema_version` accidentally bumped to `"1.2"`

**What goes wrong:** Developer thinks "new additive field = version bump" and bumps `SCHEMA_VERSION` in `export_asset.py` to `"1.2"` → cross-version compatibility tests fail → cascading rework.
**Why it happens:** Semver intuition ("new feature = minor bump"); but project uses semver-LITE where the entire v1.1 milestone shares `"1.1"` (STATE.md lock).
**How to avoid:** CONTEXT Q2 — `SCHEMA_VERSION` stays `"1.1"`. The schema_version pattern (`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`) accepts `"1.1"`; the literal is locked at export_asset.py:50.
**Warning signs:** `git diff scripts/export_asset.py` shows `SCHEMA_VERSION = "1.2"`.

## Code Examples

### Example 1: v1.1 fixture prompts.json AFTER attach_refs (current fixture is the target shape)

```json
// Source: spec/fixtures/v1.1/prompts.json (the TARGET shape — Phase 5 fixture was
//         pre-populated to lock the contract; attach_refs.py PRODUCES this state
//         at runtime from characters.json#appearance_shots[])
[
  {
    "shot_id": 1,
    "start_sec": 0.0,
    "end_sec": 1.5,
    "duration": 1.5,
    "subject": "少女,白色衣裙",
    "action": "从画面左侧走入,举手打招呼",
    "camera": "中景平视,固定机位",
    "scene": "明亮城市街道,远景有树",
    "lighting": "自然日光,顺光,亮调",
    "style": "3D 动画,写实渲染,柔和色彩",
    "prompt_text": "3D 动画,写实渲染,柔和色彩 · 明亮城市街道,远景有树 · 角色:[少女, 路人] · 少女,白色衣裙 · 从画面左侧走入,举手打招呼 · 中景平视,固定机位 · 自然日光,顺光,亮调",
    "character_refs": ["char_001", "char_002"],
    "prop_refs": []
  }
]
// NOTE: existing fixture has a HAND-CURATED prompt_text (Phase 5 locked it as the
// contract example). Phase 8 attach_refs recomposes it deterministically — the
// fixture's prompt_text may need a one-time update to match the recomposed output
// (otherwise the fixture-side _fixture_consistency_check still passes, but the
// fixture no longer represents post-attach_refs state). Planner decision: update
// fixture prompt_text in Wave 1 to match Pattern 2 recompose output.
```

### Example 2: registry_snapshot in asset.json (PROMPT-04 target shape)

```json
// Source: CONTEXT Q1 lock + spec/fixtures/v1.1/asset.json (modify in Wave 1)
{
  "schema_version": "1.1",
  "asset_type": "shottimeline",
  "source": {"video_filename": "sample.mp4", "duration_sec": 3.0},
  "generator": {
    "tool": "kais-shot-timeline",
    "version": "0.2.0-spec-fixture-v1.1",
    "generated_at": "2026-07-24T00:00:00Z",
    "warnings": [
      "preflight route unreachable: ConnectError: [Errno 111] Connection refused",
      "shot 3: route code=500: SHOT_ANALYSIS_DRIVER_FAILED"
    ],
    "registry_snapshot": {
      "characters": [
        {
          "id": "char_001",
          "name": "少女",
          "representative_image": "characters/char_001.png",
          "appearance_shots": [1, 2]
        },
        {
          "id": "char_002",
          "name": "路人",
          "representative_image": "characters/char_002.png",
          "appearance_shots": [1]
        }
      ],
      "props": [
        {
          "id": "prop_001",
          "name": "落叶",
          "representative_image": "props/prop_001.png",
          "appearance_shots": [2]
        }
      ]
    }
  },
  "data": {...},
  "media": {...}
}
```

### Example 3: verify_phase8_smoke.py scenario skeleton (6 scenarios)

```python
# Source: scripts/verify_phase7_smoke.py (DIRECT template — 5 scenarios → 6 scenarios)
# 6 scenarios (each independent temp work_dir, mirror Phase 7 isolation pattern):

# 1. attach_no_registry (PROMPT-01 graceful-degrade)
#    seed prompts.json (no character_refs) + NO characters.json/props.json →
#    run attach_refs.py → exit 0 + prompts.json schema-valid + every entry has
#    character_refs==[] + prop_refs==[] + prompt_text recomposed from facets
#    alone (no identity clause).

# 2. attach_idempotent (PROMPT-01/02 determinism)
#    seed prompts.json + characters.json/props.json (from v1.1 fixtures) →
#    run attach_refs.py TWICE → byte-diff the two outputs → assert identical.
#    Also assert character_refs/prop_refs match the fixture target shape.

# 3. snapshot_freeze (PROMPT-04 + Pitfall 18)
#    seed characters.json/props.json (confirmed) → run export_asset.py →
#    read asset.json#generator.registry_snapshot → mutate characters.json
#    (rename char_001 "少女" → " renamed", add new char_003) → RE-read
#    asset.json → assert snapshot UNCHANGED (export-time truth frozen).

# 4. integrity_dangling_ref (PROMPT-03 / Pitfall 17)
#    seed prompts.json with character_refs:["char_999"] (not in characters.json) +
#    characters.json (no char_999) → run verify_contract.py --mode=producer →
#    exit 1 + failure message mentions "character_ref 'char_999' not in
#    confirmed characters.json IDs (Pitfall 17)".

# 5. snapshot_confirmed_only (Pitfall 7 leak prevention)
#    seed characters.json with [{id:"char_001",review_state:"confirmed"},
#    {id:"char_002",review_state:"proposed"}] → run export_asset.py →
#    assert asset.json#generator.registry_snapshot.characters contains ONLY
#    char_001 (char_002 filtered out).

# 6. html_xss_inert (PRESENT-01/02 + CR-04 carry-over)
#    seed characters.json with name="</script><script>alert(1)</script>" →
#    run gen_timeline_html.py → read timeline.html → assert the literal
#    substring "</script><script>" does NOT appear (must be either
#    "&lt;/script&gt;" in body context or "<\/script>" in JSON-in-script).
#    Exit 0 on green; 1 if XSS payload survives.
```

### Example 4: Semantic-fill indicator detection (PRESENT-03)

```python
# Source: CONTEXT Q3 lock + Phase 6 generator.warnings + gen_timeline_html.py:365
# Per-shot detection runs in Python at HTML-generation time (data already loaded);
# the result is a boolean on each SHOTS entry that JS renders as the chip color.

def _detect_route_filled(prompt_entry: dict) -> bool:
    """green = 路由填充 / gray = offline 降级。

    'Route filled' = ALL four cinematography facets non-empty (Phase 6 step_semantic
    fills them from the route response; route-down → all four empty strings per
    CINEMA-03 graceful-degrade). Partial fill (some non-empty, some empty) is
    treated as degraded — documents that the route didn't fully populate this shot.
    """
    return all((prompt_entry.get(facet) or "").strip()
               for facet in ("camera", "action", "lighting", "style"))

# Wire into shots_js build (gen_timeline_html.py:40-54, extend build_shots_js):
#   shots_js.append({
#       ...,
#       "route_filled": _detect_route_filled(prompt_entry_for_shot),
#   })
# JS side reads s.route_filled to pick chip color.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `prompt_text` written by LLM / humans | Deterministic template join (recompose) | Phase 8 (this) | Idempotent + reproducible; ready for AI video pipeline consumption; no fabrication. |
| Prompt references resolve via live registry | Frozen `registry_snapshot` at export time | Phase 8 (PROMPT-04) | Old assets stay internally consistent regardless of later registry edits (Pitfall 18). |
| `gen_timeline_html.py` renders shot data only | Gallery + chips + indicator | Phase 8 (PRESENT-01/02/03) | Cross-shot narrative continuity visible in producer UI; offline-degrade visible at a glance. |
| HTML body interpolation unescaped (Phase 7 CR-04 pre-fix) | `_esc()` + JSON-in-script escape (CR-04 carry) | Phase 7 fix `336d04f` | XSS via operator-influenced strings defeated; Phase 8 must apply to new interpolations. |
| Pipeline stages invoked by absolute path | (unchanged) | v1.0 baseline | `attach_refs.py` follows same subprocess pattern — no import-resolution risk. |

**Deprecated/outdated:**
- None this phase. (Phase 8 is additive — no deprecations.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `prompts.schema.json` already permits optional `character_refs[]`/`prop_refs[]` (Phase 5 CONTRACT-04) — no schema change needed for prompts | Pattern 1, PROMPT-01 | 极低 — VERIFIED by reading `prompts.schema.json:70-85` directly during research. The v1.1 fixture `prompts.json` already contains `character_refs:["char_001","char_002"]` and validates. |
| A2 | `asset.schema.json#generator` uses `additionalProperties:false` — MUST declare `registry_snapshot` | Pattern 3, Pitfall 4 | 极低 — VERIFIED by reading `asset.schema.json:38-62` directly. Phase 6 `warnings` field was added the same way (declared in properties, optional in `required`). |
| A3 | Phase 7 CR-04 `_esc()` helper is the canonical XSS-defense pattern for this repo | Pattern 4, Pitfall 1 | 极低 — VERIFIED by reading `gen_registry_review.py:79-91` directly + commit `336d04f` (REVIEW-FIX.md). Phase 7 fix precedent is authoritative. |
| A4 | `_fixture_consistency_check` already checks `prompts.character_refs ⊆ characters IDs` for the v1.1 fixture set | Pattern 5, PROMPT-03 | 极低 — VERIFIED by reading `verify_contract.py:440-447` directly. The fixture-side check exists; Phase 8 mirrors it on the producer side. |
| A5 | `step_timeline` mtime cache currently does NOT include `prompts.json` as input | Pitfall 9 | 中 — based on reading `run_pipeline.py:320-323` (cache keys: shots/audio/transcript only). If `prompts.json` is silently already in the input set, Pitfall 9 is moot. Planner should verify and add `prompts_json` to cache inputs if missing. |
| A6 | v1.1 fixture `prompts.json` `prompt_text` field is hand-curated (Phase 5 lock) and will diverge from Pattern 2 recompose output | Code Examples Example 1 | 中 — the fixture passes schema validation either way (`prompt_text` is just a string); but if attach_refs.py runs against the fixture's source `characters.json` + a prompts.json with empty `prompt_text`, the recomposed output won't byte-match the fixture. Planner should update the fixture `prompt_text` in Wave 1 to match the recompose output (one-time edit, locks the contract example). |
| A7 | Registry `name` is the right field to resolve for prompt_text identity injection | Pattern 2 | 极低 — `characters.schema.json:21` confirms `name` is the display name (中文或英文); reviewer-editable; ID is immutable. `name` is the canonical human-readable identity. |
| A8 | `serve.py` (scripts/serve.py:19 RangeRequestHandler) already serves PNG files via Range without modification | Pattern 7 | 极低 — `serve.py` is a `SimpleHTTPRequestHandler` subclass; it serves any file in the served directory with Range support by default. PNGs in `characters/` + `props/` subdirectories will be served at relative paths. No code change needed. |
| A9 | The existing `[7/8]` banner in `step_timeline` can be reused for the attach_refs pre-step | Pattern 6 | 极低 — `run_step` (`run_pipeline.py:77-81`) takes a free-form banner string; passing `"[7/8] prompt-ref attachment"` is mechanical. |

## Open Questions (RESOLVED)

1. **`prompt_text` recompose exact template prose?**
   - What we know: CONTEXT Q2 locks "deterministic template join, identity-injecting, combines existing facets". Claude's Discretion covers exact prose.
   - What's unclear: Is `角色:[name1, name2]` the right format? Should names be comma or slash separated? Where in the template does identity go (start vs middle)?
   - Recommendation: Pattern 2 — `[style] · [scene] · 角色:[name1, name2] · 道具:[name1] · [subject] · [action] · [camera] · [lighting]`. Identity after scene (gives viewer context first), before subject (subject often restates identity — having canonical registry name just before disambiguates). Comma-separated names inside `[]`. `·` separator visually distinct from facet-internal commas.
   - **— RESOLVED: Pattern 2 locks the template; planner uses it verbatim. Claude's Discretion on prose is exercised in this resolution. Wave 1 fixture update uses the recomposed output as the canonical example.**

2. **Gallery reads `registry_snapshot` or external `characters.json`?**
   - What we know: CONTEXT Q1 says "registry_snapshot when present, else characters.json — graceful"; Claude's Discretion.
   - What's unclear: When both exist (normal case after Phase 8 export), which is preferred? Snapshot might be stale if export ran before latest apply_edits.
   - Recommendation: **Prefer `registry_snapshot`** (it's the export-time frozen truth; matches what a consumer sees). Fall back to `characters.json`/`props.json` when `asset.json` doesn't yet have the snapshot (e.g., timeline re-generated mid-pipeline before export step). Detection: `gen_timeline_html.py` reads `asset.json#generator.registry_snapshot` first, else reads `characters.json`/`props.json` directly.
   - **— RESOLVED: Pattern 7 specifies snapshot-preferred; planner implements the fallback chain.**

3. **Semantic-fill indicator: ALL non-empty vs ANY non-empty?**
   - What we know: CONTEXT Q3 says "green when route filled; gray when offline degraded; reads facet content (empty = degraded)".
   - What's unclear: Partial fill (camera+action filled but lighting+style empty) — green or gray?
   - Recommendation: **ALL four facets non-empty = green** (Pitfall 8). Mirrors "full route success" semantics. Partial fill = gray (degraded), which surfaces route instability to the operator. Lock this in the chip title attribute for clarity.
   - **— RESOLVED: Pattern 7 + Pitfall 8 lock ALL-non-empty = green. Planner implements accordingly.**

4. **Should `attach_refs.py` produce a byte-identical result on re-run when registry unchanged?**
   - What we know: CONTEXT Q1/Q2 both lock "idempotent".
   - What's unclear: Are there any nondeterminism sources (dict iteration, set ordering, timestamp)?
   - Recommendation: Yes — idempotency is hard-asserted in smoke scenario 2. Sources of determinism: `sorted(set(...))` for refs; fixed template order; no timestamps in prompts.json.
   - **— RESOLVED: Pattern 1 + Pitfall 2 enforce `sorted(set(...))`; smoke scenario 2 asserts byte-diff == 0.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | 所有 pipeline 脚本 | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `jsonschema` | `attach_refs.py` pre-write validate + `verify_contract.py` | ✓ | 4.26.0 (v1.0 baseline; Phase 5-7 已用) | — |
| `httpx` | (NOT used this phase — attach_refs is JSON-only) | ✓ | 0.28.1 (Phase 6 baseline) | n/a |
| ffmpeg / ffprobe | (NOT used this phase — no frame extraction) | ✓ | 6.1.1-3ubuntu5 | n/a — gallery uses existing PNGs |
| `slopcheck` | Package Legitimacy Audit | n/a | n/a | n/a — zero new packages this phase, audit trivially clean |
| `serve.py` Range handler | Gallery thumbnail serving (Pattern 7) | ✓ | existing (`scripts/serve.py:19 RangeRequestHandler`) | — serves PNGs by default via `SimpleHTTPRequestHandler` |

**Missing dependencies with no fallback:**
- 无（jsonschema + stdlib 全在 env；attach_refs 纯 JSON 后处理，零外部依赖）。

**Missing dependencies with fallback:**
- 无（本 phase 无 DEFERRED 阻塞 — 与 Phase 7 不同，Phase 7 的 `character-reid` route 是 STATE.md 记录的 deferred blocker；Phase 8 全部在 repo 内、全可在 v1.1 fixture set 上验证）。

## Validation Architecture

> `workflow.nyquist_validation: true`（config.json 确认）— 本 section REQUIRED。
> **沿用 Phase 5-7 VALIDATION.md 决策：repo 保持 pytest-free**（CLAUDE.md / v1.0 RETROSPECTIVE："no test framework; standalone `sys.exit(0/1)` scripts"）。assertion engine = inline `python3 -c` checks + standalone `scripts/verify_phase8_smoke.py`（mirror Phase 7 的 `verify_phase7_smoke.py`，6 scenarios）+ `scripts/verify_contract.py`（extended with prompt↔registry integrity）。**Planner 应参考 07-VALIDATION.md 的实际策略，不引入 pytest。**

### Test Framework
| Property | Value |
|----------|-------|
| Framework | **None** (standalone Python, `sys.exit(0/1)`; inline jsonschema Draft202012Validator) — 沿用 Phase 5-7 |
| Config file | none（无 pytest.ini / pyproject.toml） |
| Quick run command | `python3 spec/validate.py` (schema regression, ~3s) |
| Full suite command | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 scripts/verify_phase8_smoke.py` (~8s) |
| Estimated runtime | ~8 seconds（Phase 7 ~5s + Phase 8 smoke ~3s） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROMPT-01 (attach) | `attach_refs.py` on fixture registry+prompts → every shot has correct `character_refs[]`/`prop_refs[]` per `appearance_shots[]` | unit (mapping) | `python3 -c "from prompts.attach_refs import attach; ..."` + assert against fixture | ❌ Wave 0 (script) |
| PROMPT-01 (graceful) | `attach_refs.py` with no characters.json/props.json → refs empty, schema-valid, exit 0 | graceful-degrade | `python3 scripts/verify_phase8_smoke.py` (scenario 1) | ❌ Wave 0 |
| PROMPT-02 (determinism) | `attach_refs.py` recompose → `prompt_text` matches Pattern 2 template; re-run produces byte-identical output | unit (template) + integration (idempotency) | `python3 -c "from prompts.attach_refs import _recompose; ..."` + `verify_phase8_smoke.py` (scenario 2 byte-diff) | ❌ Wave 0 |
| PROMPT-03 (integrity) | Dangling `character_refs[]`/`prop_refs[]` ID detected by producer-side verify_contract.py | contract-integrity | `python3 scripts/verify_contract.py --mode=producer` (extended) + `verify_phase8_smoke.py` (scenario 4) | ✅ (verify_contract.py exists, Phase 8 extends _producer_registry_integrity) |
| PROMPT-04 (snapshot freeze) | `asset.json#generator.registry_snapshot` reflects confirmed registry at export time; mutating registry after export doesn't change snapshot | integration (freeze) | `python3 scripts/verify_phase8_smoke.py` (scenario 3) | ❌ Wave 0 |
| PROMPT-04 (confirmed-only) | Snapshot filters out non-confirmed entries (Pitfall 7 leak prevention) | unit (filter) | `python3 scripts/verify_phase8_smoke.py` (scenario 5) | ❌ Wave 0 |
| PROMPT-04 (schema additive) | `asset.schema.json#generator.properties.registry_snapshot` declared; old assets (no snapshot) still validate; new assets (with snapshot) validate | schema-validity | `python3 spec/validate.py` (v1.1 asset fixture green) | ✅ (validate.py exists; fixture modify Wave 1) |
| PRESENT-01 (gallery renders) | `gen_timeline_html.py` on fixture → HTML contains gallery section with character/prop cards | integration | `python3 html/gen_timeline_html.py --shots <fixture> --characters <fixture> --output /tmp/timeline.html` + grep `"gallery-card"` | ❌ Wave 0 |
| PRESENT-02 (chips render) | Per-shot row HTML contains ref-chip anchors linking to `#gallery-<id>` | integration | grep `"ref-chip"` on generated HTML | ❌ Wave 0 |
| PRESENT-03 (indicator) | Per-shot row HTML contains fill-chip; green when facets filled, gray when empty | integration + unit | grep `"fill-filled"` / `"fill-degraded"` on HTML generated from filled vs empty prompts | ❌ Wave 0 |
| PRESENT-01/02 XSS inert | `name="</script><script>alert(1)</script>"` in characters.json → HTML does NOT contain raw `</script><script>` | security (XSS) | `python3 scripts/verify_phase8_smoke.py` (scenario 6) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 spec/validate.py`（quick < 3s）
- **Per wave merge:** `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer`（full < 8s）
- **Phase gate:** Full suite green + `python3 scripts/verify_phase8_smoke.py` 6 scenarios green + `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer`

### Wave 0 Gaps
- [ ] `prompts/attach_refs.py` — NEW (attach + recompose + schema validate + atomic write)
- [ ] `spec/schemas/asset.schema.json` — MODIFY (additive `generator.registry_snapshot` property)
- [ ] `spec/fixtures/v1.1/asset.json` — MODIFY (add example `registry_snapshot`; update `prompts.json` `prompt_text` if needed to match recompose output)
- [ ] `spec/SPEC.md` — MODIFY (§3 generator row + Changelog Phase 8 bullet)
- [ ] `scripts/export_asset.py` — MODIFY (build_asset_dict + `_build_registry_snapshot` helper)
- [ ] `scripts/verify_contract.py` — MODIFY (`_producer_registry_integrity` +prompts↔registry direction)
- [ ] `html/gen_timeline_html.py` — MODIFY (gallery + chips + indicator + `_esc()` helper + JSON-in-script escape)
- [ ] `run_pipeline.py` — MODIFY (`step_timeline` invokes `attach_refs.py` as pre-step + extend mtime cache to include `prompts_json` per Pitfall 9)
- [ ] `scripts/verify_phase8_smoke.py` — NEW 6-scenario regression (mirror `verify_phase7_smoke.py`)
- [ ] `README.md` install line — no change (zero new deps; jsonschema already documented)

### Manual-Only Verifications

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Gallery UX pilot | Visual gallery rendering is a first-class deliverable; automated check verifies presence of cards/chips but not visual readability | Open generated `timeline.html` in browser against ep01 fixture; confirm gallery cards render with thumbnails, chips click-scroll to correct gallery entry, indicator colors match operator expectation |
| Operator review of recomposed `prompt_text` readability | Deterministic template guarantees structure; does NOT guarantee the recomposed prose reads naturally for downstream AI video pipelines | Spot-check 3-5 recomposed `prompt_text` strings; if awkward, adjust template (Claude's Discretion per CONTEXT Q2) and re-lock |

> **Note（vs Phase 7 — no DEFERRED humans this phase）:** Phase 7 had 3 manual-only items (live route round-trip, τ calibration, HITL UX pilot) because the character-reid route was DEFERRED. **Phase 8 has NO deferred-human items blocking verification** — every requirement is testable NOW on the v1.1 fixture set (confirmed registry + fixture prompts + fixture asset). The 2 manual items above are UX/readability pilots, not blockers.

## Security Domain

> `security_enforcement` 未在 config.json 显式 false（absent = enabled）— 本 section REQUIRED。
> Phase 8 安全面与 Phase 7 同构（本地 CLI、无网络、无多用户、无 PII），加 HTML XSS defense（Phase 7 CR-04 carry-over — 这是本 phase 的 primary security concern）。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 无认证（本地 CLI）；不引入凭据 |
| V3 Session Management | no | 无 session 概念 |
| V4 Access Control | no | 单用户 CLI |
| V5 Input Validation | yes | `attach_refs.py` validates recomposed `prompts.json` via `Draft202012Validator` pre-write; `asset.schema.json#generator.registry_snapshot` schema-validates producer output; `verify_contract.py` extends with prompt↔registry ID integrity (Pitfall 17 prevention) |
| V6 Cryptography | no | 无 crypto 操作 |
| V7 Error Handling | yes | `attach_refs.py` graceful-degrade（registry absent → refs empty, schema-valid, exit 0）; `export_asset.py` conditional emit（无 registry → snapshot omitted, byte-identical to v1.0）; `_producer_registry_integrity` fails-loud on dangling refs |
| V8 Data Protection | no | 无敏感数据落地（registry/clusters/prompts 是视觉分析，无 PII） |
| V9 Communications | no | 本 phase 零网络（attach_refs 纯 JSON 后处理） |
| V12 Files & Resources | yes | Atomic writes (`attach_refs.py` temp+`os.replace`); registry_snapshot paths derived from schema-validated `representative_image` pattern (anti-traversal); `gen_timeline_html.py` `_esc()` + JSON-in-script escape for HTML output integrity |
| **V5.3.x Output Encoding / XSS** | **yes (PRIMARY)** | **Phase 7 CR-04 carry-over — `_esc()` (5-char HTML escape) on every operator-influenced string interpolation + `.replace("</", "<\\/")` on every `json.dumps` landing in `<script>` blocks. `name` is registry-reviewer-editable (per `characters.schema.json:21`); schema constraints (`minLength:1`) are defense-in-depth, NOT a substitute for output escaping.** |

### Known Threat Patterns for prompt-ref + HTML gallery stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| HTML XSS via operator-influenced `name` (CR-04 carry-over) | Tampering / XSS | Pattern 4 — `_esc()` on body/attribute context + `.replace("</","<\\/")` on JSON-in-script; smoke scenario 6 asserts payload inert |
| JSON-in-`<script>` breakout via `</script>` in any string | Tampering / XSS | Pattern 4 — standard JSON-in-HTML defense (`\/` is valid JS escape for `/`); CR-04 fix `336d04f` precedent |
| Dangling prompt ref (`character_refs:["char_999"]` not in registry) | Tampering / Integrity | Pattern 5 — `_producer_registry_integrity` extends with prompts→registry direction; Pitfall 17 second-line assert |
| Non-confirmed entry leaks into `registry_snapshot` | Tampering / Integrity | Pattern 3 — `_project()` hard-filters `review_state != "confirmed": continue`; Pitfall 7 consistent; smoke scenario 5 |
| Snapshot mutation post-export (registry re-edit invalidates old refs) | Repudiation / Integrity | PROMPT-04 — snapshot is frozen at export time inside `asset.json`; later registry edits do NOT mutate already-exported asset.json (Pitfall 18 prevention); smoke scenario 3 asserts |
| Path traversal via `representative_image` | Path Traversal | `asset.schema.json#media.characters[].pattern` + `characters.schema.json#representative_image.pattern` both enforce `^(?!.*\\.\\.)([^/]+/)*characters/[^:*?"<>|]+\\.png$`; Phase 5 baseline; Phase 8 inherits |
| Atomic write race (partial `prompts.json` read by downstream) | Tampering / DoS | Pattern 1 — `_atomic_write` (temp + `os.replace`, mirror `export_asset.py:402-405`); cross-platform atomic |
| Cache staleness after `attach_refs` rewrites `prompts.json` | Integrity | Pitfall 9 — `step_timeline` mtime cache extended to include `prompts_json` as input |

## Sources

### Primary (HIGH confidence)

- **本 repo 源码（DIRECT anchors — 每个扩展点直接读源码 verified during research）**:
  - `prompts/merge_prompts.py` (80 行) + `prompts/extract_frames.py` (50 行) — DIRECT template for `attach_refs.py` (standalone CLI pattern + atomic write + `argparse` + Chinese docstring).
  - `scripts/export_asset.py:136-259` (`build_asset_dict`) — Phase 8 conditional-emission extension point; Phase 7 already added conditional `data.characters`/`data.props` + `media.characters[]`/`media.props[]` at lines 197-220 (DIRECT template for `registry_snapshot` conditional emission).
  - `scripts/export_asset.py:340-405` (pre-write asserts + atomic write) — `attach_refs.py` `_atomic_write` template.
  - `scripts/verify_contract.py:388-488` (`_fixture_consistency_check`) + `:440-447` (existing prompts→registry fixture check) + `:492-590` (`_producer_registry_integrity` Phase 7) — Phase 8 extends producer-side with prompts→registry direction.
  - `html/gen_timeline_html.py:99-260` (`build_html` + palette + CSS) + `:340-373` (shot-row JS template) + `:793-829` (adaptive rebuild) — Phase 8 extension points for gallery/chips/indicator.
  - `html/gen_registry_review.py:79-91` (`_esc()` helper, Phase 7 CR-04 fix commit `336d04f`) — VERBATIM source for `gen_timeline_html.py` XSS defense.
  - `html/gen_registry_review.py:315-321` (JSON-in-script `.replace("</", "<\\/")` defense) — VERBATIM source for Phase 8 JSON-inlining.
  - `run_pipeline.py:316-343` (`step_timeline`) — Phase 8 wiring point for attach_refs pre-step; `:77-81` (`run_step`) — banner helper; `:374-432` (`step_export` cache pattern + `--force` list) — template for cache-input extension per Pitfall 9.
  - `spec/schemas/prompts.schema.json:70-85` — VERIFIED optional `character_refs[]`/`prop_refs[]` already declared (Phase 5 CONTRACT-04).
  - `spec/schemas/asset.schema.json:38-62` (`generator` block with `additionalProperties:false` + Phase 6 `warnings` property as additive-optional precedent) — Phase 8 declares `registry_snapshot` the same way.
  - `spec/schemas/characters.schema.json:14-47` + `props.schema.json:14-47` — confirmed-only `review_state`, `appearance_shots[]`, `representative_image` anti-traversal pattern (Phase 5 baseline; Phase 8 snapshot projects these).
  - `spec/fixtures/v1.1/prompts.json` (already contains `character_refs:["char_001","char_002"]`) + `characters.json` + `props.json` + `asset.json` + `registry.draft.json` — frozen target shapes (Phase 5 fixtures are the contract substrate).
- **Phase 7 review artifacts (CRITICAL carry-over)**:
  - `.planning/phases/07-.../07-REVIEW.md` CR-04 (XSS via unescaped operator-influenced strings) + `.planning/phases/07-.../07-REVIEW-FIX.md` CR-04 fix (`336d04f` — `_esc()` + `.replace("</", "<\\/")`) — verbatim pattern for Phase 8 HTML hardening (Pitfall 1).
  - `.planning/phases/07-.../07-RESEARCH.md` §Validation Architecture (pytest-free decision) + §Architecture Patterns (graceful-degrade, atomic write, conditional emission) — Phase 8 inherits all.
  - `.planning/phases/07-.../07-RESEARCH.md` Pitfall 7 (confirmed-only gating) — Phase 8 `registry_snapshot` confirmed-only filter is the same pattern in new clothes.
- **Phase 6 review artifacts (graceful-degrade precedent)**:
  - `.planning/phases/06-.../06-RESEARCH.md` §Validation Architecture — pytest-free lock + smoke-harness 4-scenario shape.
  - `analysis/call_shot_analysis.py` (Phase 6) — `generator.warnings` sidecar write pattern that PRESENT-03 indicator reads.
- **Project-level locks**:
  - `.planning/STATE.md` — `schema_version:"1.1"` milestone-wide lock (Pitfall 10 prevention); Phase 7 `[N/8]` counter lock (Pitfall 5 prevention).
  - `.planning/config.json` — `workflow.nyquist_validation:true` (Validation Architecture section required); `commit_docs:true` (commit RESEARCH.md on completion).
  - `CLAUDE.md` — no `__init__.py`, no package manifest, namespace-package convention (inline `_esc()` rationale), atomic writes, `ensure_ascii=False`, Chinese docstrings, standalone CLI scripts via subprocess.

### Secondary (MEDIUM confidence)

- (none — Phase 8 is fully anchored in primary repo sources + Phase 5-7 precedent; no external library docs needed because zero new deps.)

### Tertiary (LOW confidence — marked for validation)

- (none — every claim verified by direct file read during research; no WebSearch needed because no new external library.)

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — `jsonschema` 4.26.0 v1.0 baseline + stdlib; zero new deps; verified via env introspection.
- Contract layer: **HIGH** — Phase 5 already shipped optional `character_refs[]`/`prop_refs[]` + Phase 6 `warnings` additive-optional precedent; `asset.schema.json` extension is mechanical.
- attach_refs.py (PROMPT-01/02): **HIGH** — `merge_prompts.py` is a DIRECT template; recompose template locked by CONTEXT Q2; idempotency via `sorted(set(...))`.
- registry_snapshot (PROMPT-04): **HIGH** — Phase 7 `build_asset_dict` conditional-emission is a DIRECT template; `_project()` confirmed-only filter mirrors Phase 7 gating.
- HTML gallery/chips/indicator (PRESENT-01/02/03): **HIGH** — `gen_timeline_html.py:99-944` is well-mapped extension point; `_esc()` + JSON-in-script patterns verbatim from Phase 7 CR-04 fix; CSS palette locked.
- Cross-file integrity (PROMPT-03): **HIGH** — fixture-side check exists; producer-side extension is additive mirror.
- XSS hardening (Phase 7 CR-04 carry): **HIGH** — fix `336d04f` is canonical precedent; pattern is mechanical copy.
- Pitfalls: **HIGH** — 10 pitfalls all anchored in repo source + Phase 5-7 lessons + CONTEXT locks.
- Wave 0 gaps / Validation Architecture: **HIGH** — every test runnable NOW on v1.1 fixture set; zero DEFERRED human items (contrast Phase 7's 3 deferred items due to route blocker).

**Research date:** 2026-07-25
**Valid until:** 2026-08-25（30 天；本 phase 全 in-repo，无 external route/calendar dependency；validity 信心高于 Phase 6/7）

## RESEARCH COMPLETE
