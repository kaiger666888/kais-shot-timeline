# Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`) - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — recommended answers auto-accepted (grey areas mirror the Phase 5–6 pattern: user accepted "recommended" for every area; cross-repo route + empirical τ deferred per the established Phase 6 deferral philosophy)

<domain>
## Phase Boundary

shot-timeline gains the **consumer side of the re-id pipeline**: a `step_reid` stage that calls the (cross-repo) kais-aigc-platform `POST /api/v1/production/character-reid` route via a thin httpx client (mirroring `step_semantic`), producing `registry.draft.json`; a **first-class HITL review HTML** (`html/gen_registry_review.py`) that turns the draft into `registry.edits.json`; and `registry/apply_edits.py` which applies the reviewed edits into canonical `characters.json` + `props.json` containing **only `review_state:"confirmed"` entries**. `export_asset.py` then conditionally emits `data.characters`/`data.props` + `media.characters[]`/`media.props[]` (closes the CONTRACT-06 emission clause). The contract layer (characters/props/registry schemas) is **already shipped in Phase 5** — Phase 7 is producer plumbing + HITL tooling + emission wiring.

**In scope (this repo):** `analysis/call_reid.py` (httpx client + cache + graceful-degrade); `run_pipeline.py` `step_reid` (slot 6 of 8, counter `[N/7]`→`[N/8]`); `html/gen_registry_review.py` (cluster cards + merge/split/rename + cosine-sorted queue + three-tier viz → exports `registry.edits.json`); `registry/apply_edits.py` (draft+edits → canonical characters.json/props.json, confirmed-only); `scripts/export_asset.py` conditional characters/props emission; `spec/schemas/registry-edits.schema.json` (edits round-trip shape); `scripts/verify_contract.py` registry cross-file integrity (no dangling shot_ids / cluster_ids); `scripts/verify_phase7_smoke.py` (route-down degrade + skip-reid + cache-hit + empty-draft).
**Out of scope (cross-repo / deferred):** the `character-reid` route + `character_reid_driver.py` (SAM3 multi-frame masks → DINOv2 ViT-B/14 → AgglomerativeClustering) lives in kais-aigc-platform, **unmerged** (mirrors `feat/shot-analysis-route`); empirical τ calibration on ep01 (needs SAM3 character crops that don't exist until the route ships); re-id algorithm changes.

</domain>

<decisions>
## Implementation Decisions

### Cross-repo split & deferral scope (CAST-01..05, CAST-09)
- **Q1 — route + driver location:** ✅ **kais-aigc-platform (cross-repo, deferred).** shot-timeline builds ONLY the thin httpx client + `step_reid` + HITL tooling + apply + emission — zero ML deps in this repo (preserves CLAUDE.md loose-coupling + "stages invoked by path, thin client" convention proven in Phase 6). Alt (local fallback DINOv2 driver in shot-timeline) rejected — violates loose-coupling + adds torch/sklearn dep to the producer.
- **Q2 — empirical τ calibration timing:** ✅ **defer to post-route; lock literature three-tier defaults now.** Calibration needs SAM3 character crops (clean foreground masks) — those don't exist until the route ships. A full-frame DINOv2 spike now would be **misleading** (background dominates embeddings on stylized insect animation; face detection fails on non-photoreal characters). Defaults locked from registry.schema.json `$comment`: similarity tiers `auto_merge ≥0.85 / review 0.6–0.85 / auto_distinct <0.6` (cosine DISTANCE τ ≈ 0.15 / 0.40 boundaries; literature τ≈0.30 distance ≈ similarity 0.70 sits mid-review-band — documented as advisory, not hardcoded numeric schema constraints). The RESEARCH spike documents the calibration protocol (same-person vs different-person cosine histogram on route-produced crops) as a post-merge human-verification item. Mirrors Phase 6's "mapping proven offline; live round-trip deferred."
- **Q3 — `step_reid` graceful-degrade when route down:** ✅ **registry.draft.json not written (or empty-draft); characters.json/props.json absent; asset exports without them; `generator.warnings` populated.** Schema permits omission (CONTRACT-06 "only emit when file exists" — characters/props are optional in asset.schema.json). Identical shape to `step_semantic` route-down. Alt (hard-fail) rejected — breaks the v1.0 graceful-degrade principle + would sink an entire asset on one unreachable route.

### HITL review format & edit round-trip (CAST-06, CAST-07)
- **Q1 — review HTML interaction model:** ✅ **self-contained static HTML (monolithic, mirrors `gen_timeline_html.py` pattern — all CSS/JS/data inlined; references only the source video + representative PNGs).** Cluster cards with merge/split/rename controls + confirm/reject toggles; cosine-similarity-sorted review queue; three-tier threshold visualization (≥0.85 green auto-merge / 0.6–0.85 yellow review / <0.6 grey auto-distinct). "Export edits" button serializes `registry.edits.json` as a download (no server needed — review is offline, like timeline.html is served by `scripts/serve.py`). Alt (CLI interactive prompt) rejected — visual cluster review needs thumbnails, not a TTY; alt (live review server) rejected — overkill for a single-pass review.
- **Q2 — `registry.edits.json` shape:** ✅ **structured, deterministic, schema-validated** (`spec/schemas/registry-edits.schema.json`): `{merge_groups:[[cluster_id,...]], splits:{cluster_id:[new_label,...]}, renames:{cluster_id:name}, type_overrides:{cluster_id:"char"|"prop"}, confirm_ids:[cluster_id], reject_ids:[cluster_id]}`. `apply_edits.py` consumes these deterministically + idempotently. Alt (free-form notes) rejected — non-reproducible, unverifiable.
- **Q3 — `representative_image` PNG source:** ✅ **producer-side ffmpeg frame extraction at the cluster's best member `frame_pos` → `characters/<id>.png` (fallback when the route's SAM3 crops are absent).** When the route IS available and emits crop PNGs, those supersede (route crops are foreground-masked, higher quality). This keeps the producer-side flow demonstrable end-to-end NOW (route deferred) — `apply_edits.py` extracts the representative frame via the same `ffmpeg -ss <ts> -i <video> -frames:v 1 -q:v 2 -vf scale=...` pattern already used by `gen_timeline_html.py`. Alt (require route crops) rejected — blocks producer-side demo when route is deferred.
- **Q4 — confirmed-only emission (Pitfall 7):** ✅ **`characters.json`/`props.json` contain ONLY `review_state:"confirmed"` entries; `apply_edits.py` hard-rejects emitting proposed/rejected** (rejected IDs are soft-deleted — preserved in registry.draft for reference integrity, never flowed downstream). Alt (emit all) rejected — directly causes Pitfall 7 (unreviewed clusters contaminating downstream prompt refs).

### step integration & counter (CAST-09)
- **Q1 — `step_reid` position + counter:** ✅ **slot 6 of 8** (codec[1]/detect[2]/separate[3]/transcribe[4]/semantic[5]/**reid[6]**/timeline[7]/export[8]); counter `[N/7]`→`[N/8]`. This is the deferred `[N/8]` bump promised by Phase 6 CONTEXT (CINEMA-02). Alt (after timeline) rejected — registry must exist before timeline/prompts so Phase 8 refs can attach.
- **Q2 — review blocking semantics:** ✅ **non-blocking.** `step_reid` produces `registry.draft.json` + auto-invokes `gen_registry_review.py` to emit the review HTML, but does NOT block on human review. Review is an **offline manual step** between `step_reid` and `apply_edits`; `apply_edits.py` is a separate standalone CLI (run by the operator after reviewing). The pipeline never waits on a human. Alt (block pipeline) rejected — pipelines must not wait on humans.
- **Q3 — flags:** ✅ mirror `step_semantic` exactly — `--skip-reid` (skip step), `--reid-url` (default `http://127.0.0.1:<port>/api/v1/production/character-reid`), `--reid-timeout` (default **960s**, > route-side ceiling), `--offline` (global; suppresses network, cache-only). `--force` clears `registry.draft.json` + `route_cache/character-reid/`.

### CONTRACT-06 emission gap + cross-file integrity
- **Q1 — `export_asset.py` characters/props emission:** ✅ **add conditional emission in `build_asset_dict`** — `data.characters`/`data.props` (relative .json paths) + `media.characters[]`/`media.props[]` (external .png relative paths) emitted ONLY when `characters.json`/`props.json` exist on disk. Old assets (no registry) stay byte-identical to v1.0 (field omitted, schema-valid). Closes the CONTRACT-06 emission clause that Phase 5 schema-supported but didn't wire (no characters.json existed until Phase 7). Alt (leave for later) rejected — CONTRACT-06 is marked done; the producer must actually emit.
- **Q2 — `verify_contract.py` registry cross-file integrity:** ✅ **extend the producer gate** — when characters.json/props.json/registry.draft.json exist: (a) every `appearance_shots[]` shot_id must exist in shots.json (no dangling); (b) every cluster `members[].shot_id` must exist in shots.json; (c) characters.json/props.json IDs are unique + match `^(char|prop)_[0-9]{3}$`; (d) no `review_state:"proposed"` leaked into canonical files. PROMPT-03 (prompt→registry ID integrity) is Phase 8's surface, but registry↔shots integrity is Phase 7's. Alt (defer all to Phase 8) rejected — registry integrity must hold before Phase 8 attaches refs.

### Claude's Discretion
- Exact prose of `generator.warnings` re-id messages; HTML/CSS layout of cluster cards (reuse GitHub-dark palette from gen_timeline_html.py); helper function organization within `analysis/call_reid.py` (httpx call, cache, preflight, draft normalization); whether `registry-edits.schema.json` lives under `spec/schemas/` (yes — consistent with other schemas); the exact cosine-similarity formatting in the review UI.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analysis/call_shot_analysis.py` — **the direct template** for `call_reid.py`: httpx client, `video_content_hash` (sha256 head+tail 1MB), per-call cache under `route_cache/`, preflight, graceful-degrade via broadened `except` (CR-02 fix), `--offline` cache-only path, lazy httpx import (WR-02 fix), URL-userinfo scrubbing (WR-05 fix). `call_reid.py` mirrors this shape verbatim — only the endpoint + payload + response-normalization differ.
- `run_pipeline.py:step_semantic` — **the direct template** for `step_reid`: slot insertion, `run_step(cmd, "[N/8] label")` banner, `--skip-*` cache check, `--force` cache-list extension, 4-flag threading. The `[N/7]`→`[N/8]` renumber is mechanical (17 step labels + the new [6/8]).
- `html/gen_timeline_html.py` — template for the monolithic self-contained HTML pattern (f-string template, inlined CSS/JS/data, base64 or external PNG refs, GitHub-dark palette, `document.createElement` imperative DOM). `gen_registry_review.py` reuses the palette + monolithic structure.
- `scripts/export_asset.py` — `build_asset_dict` + `ensure_symlink` + `validate_asset_json`; Phase 7 adds the conditional characters/props block + PNG canonical-path pre-write assert (mirror the existing stems assert).
- `spec/schemas/{characters,props,registry}.schema.json` — **already shipped Phase 5**, encode every Pitfall mitigation (confirmed-only gating, ID immutability, anti-traversal PNGs, three-tier `$comment`). Phase 7 only ADDS `registry-edits.schema.json`.
- `scripts/verify_contract.py` — `validate_eight_shapes` + `_fixture_consistency_check`; Phase 7 extends the consistency check with registry↔shots integrity (additive, gated on file-existence).

### Established Patterns
- **Stage = self-contained CLI script** invoked via `subprocess.run([sys.executable, str(HERE / "<dir>" / "<script>.py"), ...], check=True)`.
- **Idempotent caching** on file-existence; `--force` clears.
- **Graceful-degrade** as first-class (route-down → schema-valid empty/absent + warning, asset still exports) — Phase 6 proven.
- **JSON I/O:** `indent=2`, `ensure_ascii=False` (Chinese names).
- **Atomic write** (temp + os.replace) for canonical files.

### Integration Points
- `run_pipeline.py:main()` — insert `step_reid` between `step_semantic` and `step_timeline`; thread 4 new flags; bump counter.
- `registry.draft.json` (work dir) — `step_reid` output → consumed by `gen_registry_review.py` → `registry.edits.json` → `apply_edits.py`.
- `characters.json`/`props.json` (work dir) — `apply_edits.py` output → consumed by `export_asset.py` (conditional emission) + Phase 8 prompt-ref attachment + Phase 9 canvas child nodes.
- `asset.json#data.characters`/`data.props` + `media.characters[]`/`media.props[]` — emitted by `export_asset.py` when files exist.

</code_context>

<specifics>
## Specific Ideas

- The HITL review HTML is a **FIRST-CLASS deliverable** (CAST-06 explicitly: "一等交付物，非附属脚本") — not a debug script. It must be genuinely usable: visual cluster cards with representative thumbnails, clear merge/split/rename/confirm/reject affordances, cosine-sorted queue so the hardest (mid-band) decisions surface first, three-tier color viz. Reuse `gen_timeline_html.py`'s GitHub-dark palette + monolithic self-contained pattern.
- Graceful-degrade is fully testable NOW (route not running): `verify_phase7_smoke.py` proves route-down → asset exports without characters/props + warning; `--skip-reid` skip; cache-hit offline; empty-draft handling. Mirrors Phase 6's smoke harness exactly (4 scenarios).
- `apply_edits.py` must be **idempotent + deterministic** — re-running with the same edits.json produces byte-identical characters.json/props.json. Confirmed-only gating is a hard assert, not a filter-after-the-fact.
- The producer-side ffmpeg representative-frame extraction lets the FULL flow (`draft → review HTML → edits → apply → characters.json/props.json + PNGs → asset.json emission`) be demonstrated end-to-end on ep01 NOW, even with the route deferred. This is Phase 7's analog of Phase 6's "mapping proven offline against 7 fixtures."

</specifics>

<deferred>
## Deferred Ideas

- **`character-reid` route + SAM3/DINOv2 driver (CAST-01/02/03/08)** — kais-aigc-platform cross-repo (mirrors `feat/shot-analysis-route`, unmerged). shot-timeline producer-side is fully buildable + testable without it; live round-trip becomes a post-merge smoke test.
- **Empirical τ calibration on ep01 (CAST-04-spike)** — needs SAM3 character crops (clean foreground masks) that don't exist until the route ships. Literature three-tier defaults locked as advisory; calibration protocol (same-person vs different-person cosine histogram, valley pick) documented in RESEARCH as a post-merge human-verification item. A full-frame DINOv2 spike now would mislead (background-dominated).
- **SAM3 foreground-masked crop PNGs** — when the route ships, its crops supersede the producer-side ffmpeg frame-extraction fallback for `representative_image` (route crops are cleaner). The fallback exists precisely so the producer flow is demonstrable now.
- **`prompts.json#character_refs[]`/`prop_refs[]` attachment** — Phase 8 (PROMPT-01) owns attaching registry IDs to prompts via `appearance_shots[]`. Phase 7 only produces the confirmed registry.
- **`generator.registry_snapshot` freeze** — Phase 8 (PROMPT-04) owns freezing registry state into asset.json so later registry changes don't invalidate exported prompt refs.

</deferred>
