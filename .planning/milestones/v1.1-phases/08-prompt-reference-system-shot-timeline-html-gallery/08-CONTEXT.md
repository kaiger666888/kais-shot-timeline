# Phase 8: Prompt Reference System + shot-timeline HTML Gallery - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — recommended answers auto-accepted (mirrors Phase 5–7 pattern; fully in-repo, no cross-repo deferral)

<domain>
## Phase Boundary

Wire the **confirmed Phase-7 registry onto the prompts + the timeline UI + the asset manifest**: post-process `prompts.json` to attach `character_refs[]`/`prop_refs[]` (per `characters.json#appearance_shots[]`) and recompose `prompt_text` referencing characters/props by name; extend `verify_contract.py` with prompt↔registry ID integrity (Pitfall 17); embed `generator.registry_snapshot` in `asset.json` (freeze registry state — Pitfall 18); and extend `gen_timeline_html.py` with a character/prop gallery + clickable reference chips + a per-shot "运镜分析填充" indicator (green = route filled / gray = offline degraded). All in-repo — no cross-repo route dependency. The Phase-7 confirmed registry (or its absence, graceful-degrade) is the substrate.

**In scope:** `prompts/attach_refs.py` (NEW — attach refs + recompose prompt_text); `run_pipeline.py` (invoke attach_refs within step_timeline, NO new numbered step / NO `[N/8]`→`[N/9]` bump); `spec/schemas/asset.schema.json` (additive `generator.registry_snapshot`); `scripts/export_asset.py` (emit registry_snapshot); `spec/fixtures/v1.1/asset.json` (example registry_snapshot); `scripts/verify_contract.py` (prompt↔registry integrity); `html/gen_timeline_html.py` (gallery + chips + semantic-fill indicator); `scripts/verify_phase8_smoke.py` (NEW smoke harness).
**Out of scope:** the canvas consumer (PRESENT-04/05/06 are Phase 9 cross-repo); re-id route/driver (Phase 7 deferred); changing detection/transcription/separation/semantic algorithms; PROMPT dialect switch / cross-video continuity (v2 deferred).

</domain>

<decisions>
## Implementation Decisions

### Prompt-ref attachment + recompose (PROMPT-01, PROMPT-02)
- **Q1 — attach mechanism:** ✅ `prompts/attach_refs.py` reads `characters.json` + `props.json` (confirmed registry) + `prompts.json` + `shots.json`; for each shot, attaches `character_refs[]`/`prop_refs[]` = the IDs whose `appearance_shots[]` contains that shot_id. Idempotent (re-running produces byte-identical prompts.json). Schema-validated output (prompts.schema.json already allows the optional refs — Phase 5 CONTRACT-04). Alt (LLM-based) rejected — non-deterministic, adds dep.
- **Q2 — prompt_text recompose:** ✅ **deterministic template join** — resolve refs → names (from characters.json/props.json `name`), then recompose `prompt_text` by injecting identity into a stable template that combines the existing facets (subject/action/camera/scene/lighting/style). When no refs: prompt_text recomposed from facets alone (no identity clause). NO LLM, NO fabrication — names come only from the confirmed registry. Recomposition is deterministic + idempotent. Alt (LLM rewrite) rejected; alt (leave prompt_text untouched) rejected (PROMPT-02 explicitly requires identity-referencing recomposition).
- **Q3 — pipeline integration (avoid counter bump):** ✅ `step_timeline` invokes `prompts/attach_refs.py` as a **pre-step** (modifies prompts.json in place) BEFORE `gen_timeline_html.py` runs. NO new numbered banner, NO `[N/8]`→`[N/9]` counter bump (ROADMAP Phase 8 success criteria don't call for a new step). attach_refs is a standalone CLI script invoked via subprocess (mirrors the stage pattern), just not given its own `[N/M]` slot. Alt (new step_prompt_refs slot 7 → [N/9]) rejected — unnecessary counter churn.

### Registry snapshot freeze (PROMPT-04)
- **Q1 — snapshot shape:** ✅ `generator.registry_snapshot` = compact frozen view: `{characters:[{id,name,representative_image,appearance_shots}], props:[{id,name,representative_image,appearance_shots}]}` containing ONLY `review_state:"confirmed"` entries (Pitfall 7 consistent). Embeds enough for a consumer to resolve prompt refs + render a gallery WITHOUT re-reading external characters.json/props.json (the snapshot is the export-time truth). Additive OPTIONAL field in `asset.schema.json#generator.properties` (like `warnings` — absent on old assets, schema-valid). Alt (content-hash only) rejected — can't resolve refs offline; alt (full registry.blob) rejected — bloat.
- **Q2 — schema bump:** ✅ **NO version bump** — `generator.registry_snapshot` is additive-optional within v1.1 (the whole milestone shares `schema_version:"1.1"` per STATE.md decision). `SCHEMA_VERSION` constant in export_asset.py stays `"1.1"`. Strict `additionalProperties:false` means the schema MUST declare the new property (else it fails) — add it to `asset.schema.json#generator.properties`.

### Cross-file integrity (PROMPT-03)
- **Q1 — check scope:** ✅ extend `verify_contract.py` `_fixture_consistency_check` (additive, file-existence-gated): when prompts.json + characters.json/props.json exist → (a) every `character_refs[]`/`prop_refs[]` ID in prompts.json MUST exist in characters.json/props.json (no dangling — Pitfall 17); (b) every confirmed registry entry's appearance_shots ⊆ shots.json (already checked in Phase 7's `_producer_registry_integrity` — reuse, don't duplicate). Alt (separate verifier) rejected — keep integrity checks unified in verify_contract.py.

### HTML gallery + chips + indicator (PRESENT-01, PRESENT-02, PRESENT-03)
- **Q1 — gallery section:** ✅ extend `gen_timeline_html.py:build_html` with a character/prop gallery section (cards: representative thumbnail via external png served by `serve.py`, name, ID, appearance-shot count). Reuse GitHub-dark palette + monolithic self-contained pattern. Gallery reads characters.json/props.json (or the embedded registry_snapshot if present).
- **Q2 — reference chips:** ✅ in the per-shot prompt rendering, render `character_refs[]`/`prop_refs[]` as clickable badge chips (🧑 name / 🔧 name) that link/scroll to the corresponding gallery entry. Clickable via in-page anchor (no server needed — mirrors the self-contained HTML pattern).
- **Q3 — semantic-fill indicator:** ✅ per-shot "运镜分析填充" chip: **green** when the route filled the cinematography facets (camera/action/lighting/style non-empty AND sourced from route — detected via prompts.json having non-empty route-sourced facets) / **gray** when offline-degraded (facets empty, sourced from graceful-degrade). The indicator reads the facet content (empty = degraded). Consistent with Phase 6's generator.warnings (which records the degrade reason).

### Claude's Discretion
- Exact gallery card CSS/layout; chip color shades (reuse palette tokens); prompt_text recompose template prose (deterministic, identity-injecting); whether the gallery reads characters.json or the embedded registry_snapshot (recommend: registry_snapshot when present, else characters.json — graceful).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `prompts/merge_prompts.py` + `prompts/extract_frames.py` — the prompts/ module pattern; `attach_refs.py` is the new sibling.
- `html/gen_timeline_html.py` (1083 lines) — `build_html` is the extension point; reuse the GitHub-dark palette (#0d1117/#161b22/#30363d/#58a6ff/#3fb950/#d29922/#f85149/#8b949e) + monolithic self-contained pattern + base64/external-png refs.
- `scripts/export_asset.py:build_asset_dict` — Phase 6 added `generator.warnings` (conditional emit); Phase 8 adds `generator.registry_snapshot` the same way (conditional on registry files existing).
- `spec/schemas/prompts.schema.json` — ALREADY has optional `character_refs[]`/`prop_refs[]` (Phase 5 CONTRACT-04). No schema change needed for prompts.
- `spec/schemas/asset.schema.json#generator` — has tool/version/generated_at/warnings; Phase 8 ADDS registry_snapshot (additive).
- `scripts/verify_contract.py:_fixture_consistency_check` + `_producer_registry_integrity` (Phase 7) — extend with prompt↔registry ID integrity.

### Established Patterns
- Stage = self-contained CLI script (subprocess invocation). attach_refs mirrors this.
- Graceful-degrade: absent registry → refs empty, gallery empty, snapshot absent — all schema-valid.
- Idempotent + atomic writes.
- Chinese docstrings/comments, ensure_ascii=False, indent=2.

### Integration Points
- `run_pipeline.py:step_timeline` — invoke `prompts/attach_refs.py` before `gen_timeline_html.py`.
- `prompts.json` — attach_refs output (consumed by gen_timeline_html + step_export).
- `asset.json#generator.registry_snapshot` — emitted by export_asset.py when characters.json/props.json exist.

</code_context>

<specifics>
## Specific Ideas

- The full ref-attachment flow is testable NOW on the v1.1 fixture set (registry.draft → apply_edits → characters.json/props.json → attach_refs → prompts.json with refs → verify_contract integrity). No live route needed — the confirmed registry fixture is the substrate.
- registry_snapshot must be a TRUE freeze: once asset.json is written, later registry mutations (re-review, re-cluster) MUST NOT invalidate the exported prompt references. The snapshot is the export-time truth (Pitfall 18).
- The semantic-fill indicator (PRESENT-03) ties back to Phase 6's generator.warnings — a shot degraded offline shows the gray chip + the warning is in generator.warnings.
</specifics>

<deferred>
## Deferred Ideas

- **Canvas consumer gallery/chips (PRESENT-04/05/06)** — Phase 9 cross-repo (kais-aigc-platform `feat/canvas-asset-collection`); the producer-side snapshot + refs are the contract the canvas consumes.
- **PROMPT dialect switch (paragraph vs keyword)** — v2 (PROMPT-DIALECT-01 deferred).
- **Cross-video character continuity** — v2 (CROSSVIDEO-01 deferred).
- **Speaker attribution (dialogue → speaker)** — v2 (SPEAKER-01 deferred).
</deferred>
