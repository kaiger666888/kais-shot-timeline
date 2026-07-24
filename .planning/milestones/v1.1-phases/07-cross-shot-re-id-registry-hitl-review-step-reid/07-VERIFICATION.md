---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
verified: 2026-07-25T00:00:00Z
status: human_needed
score: 12/12 must-haves verified (all producer-side truths green; 3 deferred items routed to human per CONTEXT/VALIDATION lock)
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live character-reid route round-trip against ep01"
    expected: "Start kais-aigc-platform backend on the merged route branch, run `python3 run_pipeline.py --video <ep01> ...` (no --skip-reid), confirm real `registry.draft.json` lands with non-empty `clusters[]` + representative crops + that `_tier_for` classifications are sane (not all auto_merge / all auto_distinct)."
    why_human: "Route is DEFERRED cross-repo (kais-aigc-platform). Producer-side graceful-degrade is fully tested via verify_phase7_smoke.py scenario 1, but live ML round-trip cannot run without the unmerged route. Mirrors Phase 6 feat/shot-analysis-route pre-merge state. Pre-authorized deferral per CONTEXT.md <deferred> + STATE.md Blockers."
  - test: "Empirical three-tier τ calibration on ep01 character crops"
    expected: "Post-merge, follow 07-RESEARCH.md §DINOv2 Re-ID Methodology → 'Deferred τ calibration protocol': collect same-person vs different-person cosine pairs from route-produced SAM3 foreground-masked crops (≥50 same + ≥200 different); plot overlaid histogram; pick valley as new τ; update `_tier_for` defaults + registry.schema.json `$comment`. If distributions overlap heavily on stylized animation, widen review band + document that HITL is load-bearing."
    why_human: "Needs SAM3 foreground-masked character crops that do not exist until CAST-02 route ships. A full-frame DINOv2 spike now would mislead — background dominates embeddings on stylized insect animation; face detection fails on non-photoreal characters. CONTEXT Q2 explicitly locks literature defaults (≥0.85/0.6-0.85/<0.6) as advisory + defers empirical calibration."
  - test: "HITL review HTML UX pilot against real ep01 clusters"
    expected: "Open the generated `registry_review.html` in a browser against real route-produced clusters; confirm cluster cards are visually readable, thumbnails legible, merge/split/rename/confirm/reject controls intuitive, cosine-sorted queue surfaces the hardest mid-band decisions first, Export button produces a schema-valid `registry.edits.json` that round-trips through `apply_edits.py` cleanly."
    why_human: "07-03 SUMMARY self-check verifies presence of cards/buttons/palette/Blob export (CAST-06 automated surface) but cannot judge usability. HITL HTML is a FIRST-CLASS deliverable per CONTEXT — visual ergonomics need human eyes. The CR-01 split UX (per-label member_indexes partition input) especially needs pilot feedback."
---

# Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`) Verification Report

**Phase Goal:** A working cross-shot character/prop registry pipeline with mandatory human-in-the-loop review — `registry.draft.json` → HITL review HTML → `registry.edits.json` → canonical `characters.json` + `props.json` containing only confirmed entries. Highest-complexity phase in v1.1.
**Verified:** 2026-07-25
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The producer-side goal — `registry.draft.json` → HITL review HTML → `registry.edits.json` → canonical `characters.json`/`props.json` (confirmed-only) — is **fully implemented, wired, and regression-tested** in the codebase. All 12 must-have truths derived from ROADMAP success criteria + PLAN frontmatter pass all four verification levels (exists, substantive, wired, data-flows). The 11 code-review findings (5 BLOCKER + 6 WARNING) are **all closed** with empirically-verified fixes (CR-01..CR-05, WR-01..WR-06).

The ML route half (CAST-01/02/03/04/08) is **pre-authorized deferred cross-repo** per CONTEXT.md `<deferred>` + 07-VALIDATION.md Manual-Only + STATE.md Blockers (mirrors Phase 6 `feat/shot-analysis-route` pre-merge state). Three human-verification items route the deferred work to the post-merge window — they do NOT block this phase.

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `registry-edits.schema.json` validates structured edits round-trip shape (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes) | ✓ VERIFIED | `spec/schemas/registry-edits.schema.json` read in full: 7 properties, `additionalProperties:false` top-level + nested, cluster_id pattern `^(char\|prop)_[0-9]{3}$` on all ID fields; `python3 spec/validate.py` exits 0 with `[valid-v11] registry-edits` line |
| 2 | `registry.edits.json` fixture schema-valid + consistent with existing draft/canonical fixtures | ✓ VERIFIED | Fixture read; exercises CR-01 partitioned splits `{char_001:[{day,[0,1]},{night,[2]}]}` + 4 confirm_ids + 4 renames (少女(日)/少女(夜)/路人/落叶); smoke scenario 4 confirms `apply_edits(draft, edits)` produces byte-identical canonical across 2 runs |
| 3 | `spec/validate.py` validates 10 v1.1 shapes green (was 9; +1 registry-edits); minimal v1.0 (6 shapes) unaffected | ✓ VERIFIED | Output: 10 `[valid-v11]` lines + 6 `[valid]` lines; exit 0; CONTRACT-09 backward-compat intact |
| 4 | `call_reid.py` normalizes route response → `registry.draft.json` with every cluster `review_state="proposed"` (CAST-05); drops extra route fields (additionalProperties:false defense) | ✓ VERIFIED | Inline behavior test: input with `centroid_embedding:[0.1]*768` → output cluster has NO `centroid_embedding`; `review_state` hardcoded to `"proposed"` in normalize_clusters (line 203) |
| 5 | `call_reid.py` is per-video cache (route_cache/character_reid/video_<vch>.json) NOT per-shot (Pitfall 4); preflight short-circuits; route-down → empty clusters + warnings sidecar (CAST-09 degrade) | ✓ VERIFIED | Smoke scenario 1 (route_down): unreachable URL → exit 0 + `clusters==[]` + 2 warnings containing `preflight`/`ConnectError`/`character-reid`; smoke scenario 5 (cache_hit_offline): pre-seeded cache → 3 clusters reused + stdout has `[reid] cache hit` + 0 network calls |
| 6 | `call_reid.py` warnings sidecar is non-destructive (READ-merge-write); URL userinfo scrubbed via `_safe_error` (WR-05); `[reid]` step-tag dedup prevents self-accumulate on re-run (WR-01) | ✓ VERIFIED | `_safe_error('http://user:pass@host/...')` → no `user:pass@` (scrubbed to `***@`); source lines 443-447 show STEP_TAG strip-prior pattern; cross-step warnings preserved |
| 7 | `apply_edits.py` confirmed-only HARD GATE at build-entry time (NOT filter-after-write) — Pitfall 7 prevention | ✓ VERIFIED | Test: draft with extra `char_099 review_state="proposed"` (NOT in confirm_ids) → `char_099` NEVER appears in canonical characters.json (verified via `assert 'char_099' not in {c['id'] for c in chars_a}`); source line 478 `if cl.get("review_state") != "confirmed": continue` |
| 8 | `apply_edits.py` idempotent — same draft+edits applied twice produces byte-identical canonical files (Pitfall 5 guard); fixed-order apply (merge→split→rename→type_override→confirm/reject) | ✓ VERIFIED | Smoke scenario 4: 2 isolated work_dirs, same fixture seed → byte-identical characters.json + props.json (verified via `json.dumps sort_keys=True` equality); apply order documented in module docstring lines 8-15 + implemented in code order |
| 9 | `apply_edits.py` validates edits against registry-edits.schema.json pre-apply AND canonical output against characters/props.schema.json pre-write (fails loud); ffmpeg representative PNG via arg-list subprocess (CAST-08 producer-side fallback); OMITS representative_image on ffmpeg failure (schema-optional) | ✓ VERIFIED | `_validate(REGISTRY_EDITS_SCHEMA, edits)` at line 303 + `_validate(REGISTRY_SCHEMA, draft)` at line 309 (WR-05) + pre-write validates at lines 500-501; ffmpeg uses `subprocess.run(["ffmpeg", ...], capture_output=True, timeout=10)` (arg-list, no shell=True); on failure `entry.pop("representative_image", None)` (line 236) |
| 10 | `gen_registry_review.py` produces self-contained monolithic HTML — base64 thumbnails (Pitfall 2 prevention), cosine-sorted queue surfaces mid-band first, three-tier viz, Export button serializes registry.edits.json client-side via Blob+download | ✓ VERIFIED | Generated 21518-byte HTML from fixture; `<style>`+`<script>` inlined; ≥3 `cluster-card` divs; palette tokens `#0d1117`/`#161b22`/`#30363d` reused; `Blob`+`createObjectURL` present; `_tier_sort_key` function at line 170 implements cosine-sort |
| 11 | `run_pipeline.py:step_reid` is slot 6 of 8 — subprocess-calls `call_reid.py` then auto-invokes `gen_registry_review.py`; 20 old `[N/7]` renamed to `[N/8]` (24 total incl. 4 new `[6/8]`); 3 new flags (`--skip-reid`/`--reid-url`/`--reid-timeout`) + shared `--offline`; `--force` clears registry artifacts | ✓ VERIFIED | `grep -cE '\[[1-8]/8\]' run_pipeline.py` → 24; `grep -cE '\[[1-7]/7\]'` → 0; `def step_reid` at line 235, called at line 573; `run_pipeline.py --help` shows all 3 new flags; source lines 514-515 declare `registry_draft`/`review_html` path constants; `--force` list extended (lines 534-535) |
| 12 | `export_asset.py` CONDITIONALLY emits `data.characters`/`data.props` + `media.characters[]`/`media.props[]` ONLY when files exist (CONTRACT-06 closure; old assets byte-identical to v1.0); `verify_contract.py` extends producer gate with registry↔shots integrity + Pitfall 7 second-line assert; `verify_phase7_smoke.py` 5 scenarios green | ✓ VERIFIED | Inline test: build_asset_dict without registry files → no `characters`/`props` keys in data/media; with files → all 4 keys present. `_producer_registry_integrity` (verify_contract.py:492) catches `proposed` AND `rejected` leaks (WR-04 tightened to `!= "confirmed"` at line 559). Smoke harness: `[phase7-smoke] OK: 5/5 scenarios green`; Phase 6 regression: 4/4 green |

**Score:** 12/12 truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `analysis/call_reid.py` | httpx client + normalize_clusters + per-video cache + preflight + graceful-degrade + warnings sidecar MERGE | ✓ VERIFIED | 457 LOC; clean import; all 10+ behavior rows pass; CR-02 malformed-cluster graceful skip; WR-03 mean_cosine clamp; WR-02 cache invalidate-on-failure |
| `registry/apply_edits.py` | Confirmed-only gate + idempotent apply + ffmpeg PNG + schema validation | ✓ VERIFIED | 547 LOC; standalone CLI (NOT in pipeline); fixed-order apply verified; CR-01 splits PARTITION members (not clone); CR-03 collision detection; CR-05 merge-state forwarding |
| `html/gen_registry_review.py` | Self-contained HITL HTML — cluster cards + cosine queue + 3-tier viz + Export button | ✓ VERIFIED | 728 LOC; GitHub-dark palette reused; `_esc()` helper (CR-04 body escape) + JSON-in-script `</` → `<\/` defense; 5 JS handlers (toggleConfirm/toggleReject/toggleType/mergeWith/splitCluster/exportEdits) |
| `run_pipeline.py` (modified) | `step_reid` slot 6 of 8 + `[N/7]`→`[N/8]` renumber + 3 flags + `--force` cache list | ✓ VERIFIED | `step_reid(video, work_dir, shots_json, registry_draft, review_html, skip, offline, reid_url, reid_timeout)` at line 235; called at line 573; 24 `[N/8]` occurrences; 0 residual `[N/7]` |
| `scripts/export_asset.py` (modified) | Conditional characters/props emission (CONTRACT-06) + non-fatal PNG assert | ✓ VERIFIED | `data_block`/`media_block` built as locals then conditionally extended; pre-write PNG check inside `build_asset_dict` propagates warnings to `generator.warnings` (rule-2 fix in 07-04-SUMMARY) |
| `scripts/verify_contract.py` (modified) | Producer-side registry↔shots integrity + Pitfall 7 second-line | ✓ VERIFIED | `_producer_registry_integrity(asset_dir)` at line 492 wired into `run_producer_check`; checks appearance_shots ⊆ shots + cluster members ⊆ shots + ID uniqueness/pattern + `!= "confirmed"` (WR-04 tightened) |
| `scripts/verify_phase7_smoke.py` | 5-scenario regression harness | ✓ VERIFIED | 5/5 scenarios green: route_down / skip_reid / empty_draft_handoff / apply_edits_idempotent / cache_hit_offline |
| `spec/schemas/registry-edits.schema.json` | Edits round-trip contract | ✓ VERIFIED | Draft 2020-12; 7 optional properties; strict additionalProperties:false; CR-01 reshape: splits value is now `[{label, member_indexes}]` array (not bare `string[]`) |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `run_pipeline.py:step_reid` | `analysis/call_reid.py` + `html/gen_registry_review.py` | Two sequential `subprocess.run([sys.executable, str(HERE/"analysis"/"call_reid.py"), ...], check=True)` + same for gen_registry_review | ✓ WIRED | Verified in source lines 288-312; SECOND subprocess gated on `os.path.exists(registry_draft)` (route-down still writes empty draft, HTML still generates) |
| `analysis/call_reid.py:main` | `route_cache/character_reid/video_<vch>.json` | Per-video cache file with embedded `_cache_key` 4-tuple | ✓ WIRED | Cache key checks `(video_content_hash, route_name, route_version)`; mismatch → miss |
| `analysis/call_reid.py:main` | `route_cache/warnings.json` sidecar | READ-merge-write (non-destructive cross-step; `[reid]`-tagged self-dedup cross-run) | ✓ WIRED | WR-01 fix: `prior = [w for w in existing_warnings if not w.startswith("[reid]")]` |
| `analysis/call_reid.py:normalize_clusters` | `spec/schemas/registry.schema.json` | `Draft202012Validator.iter_errors` pre-write self-check | ✓ WIRED | Lines 412-431; on failure: invalidate poisoned cache (WR-02) + `sys.exit` fails-loud |
| `registry/apply_edits.py:main` | `registry.draft.json` + `registry.edits.json` + `shots.json` | `json.load` all three inputs; fixed-order apply | ✓ WIRED | All three files loaded + schema-validated (edits + draft per WR-05) before any mutation |
| `registry/apply_edits.py:_extract_representative_png` | ffmpeg subprocess | `subprocess.run(["ffmpeg", "-y", "-ss", ts, "-i", video, ...], timeout=10)` arg-list form | ✓ WIRED | NEVER shell=True (T-07-13 mitigation holds — `grep -cE 'shell=True'` returns 0 across all 7 Phase 7 files) |
| `html/gen_registry_review.py:main` | `registry.draft.json` | `json.load` + render cluster cards | ✓ WIRED | Sorts clusters via `_tier_sort_key` (priority 0=review/1=auto_merge/2=auto_distinct, then by mean_cosine) |
| `html/gen_registry_review.py` export button JS | `registry.edits.json` shape | Client-side `Blob([JSON.stringify(edits, null, 2)]) + URL.createObjectURL + a.download` | ✓ WIRED | All 6 edits fields (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids) serialized |
| `scripts/export_asset.py:build_asset_dict` | `characters.json`/`props.json` + `characters/*.png` + `props/*.png` | Conditional file-existence check + `glob.glob` PNG enumeration | ✓ WIRED | Old assets byte-identical to v1.0 (keys omitted, schema-optional); pre-write PNG assert non-fatal (CAST-09 graceful-degrade) |
| `scripts/verify_contract.py:run_producer_check` | registry↔shots cross-file integrity | New `_producer_registry_integrity(asset_dir)` helper, additive, gated on file-existence | ✓ WIRED | Called AFTER `validate_eight_shapes` BEFORE `_cross_version_check`; no-op when registry files absent (ep01 case) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `analysis/call_reid.py` | `clusters` (in `registry_draft`) | `normalize_clusters(route_data)` projects route response | ✓ FLOWING (route-up) / ✓ FLOWING (route-down → `[]` empty, schema-valid degrade) | Verified: route_data dict → projected cluster list with `review_state="proposed"` + dropped extras |
| `registry/apply_edits.py` | `chars` + `props` (canonical lists) | `clusters` dict after fixed-order apply + confirmed-only gate | ✓ FLOWING | Verified: char_001 → 少女 with appearance_shots=[1,2] from cluster members |
| `html/gen_registry_review.py` | rendered HTML | `draft["clusters"]` sorted by `_tier_sort_key` + base64 thumbnails | ✓ FLOWING | Verified: 3 cluster cards generated from fixture; char_002 (review tier 0.72) surfaces first |
| `scripts/export_asset.py` | `asset["data"]["characters"]` etc. | file-existence check + glob PNG enumeration | ✓ FLOWING (when apply_edits ran) / ✓ FLOWING (omitted when absent — byte-identical v1.0) | Both paths verified inline |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Schema regression suite green | `python3 spec/validate.py` | exit 0; 10 `[valid-v11]` + 6 `[valid]`; 0 failures | ✓ PASS |
| Phase 7 smoke harness green | `python3 scripts/verify_phase7_smoke.py` | `[phase7-smoke] OK: 5/5 scenarios green`; exit 0 | ✓ PASS |
| Phase 6 regression (no breakage) | `python3 scripts/verify_phase6_smoke.py` | `[phase6-smoke] OK: 4/4 scenarios green`; exit 0 | ✓ PASS |
| Producer contract on ep01 | `PHASE4_ASSET_DIR=<ep01> python3 scripts/verify_contract.py --mode=producer` | exit 0; "asset.json + data shapes schema-valid; v1↔v1.1 cross-version bidirectional compat proven; 0 dangling" | ✓ PASS |
| run_pipeline counter integrity | `grep -cE '\[[1-8]/8\]' run_pipeline.py` | 24 (expected: 20 renumbered + 4 new step_reid `[6/8]`) | ✓ PASS |
| Old counters fully purged | `grep -cE '\[[1-7]/7\]' run_pipeline.py` | 0 | ✓ PASS |
| 3 new flags exposed | `python3 run_pipeline.py --help \| grep -cE '\-\-skip-reid\|\-\-reid-url\|\-\-reid-timeout'` | 5 (3 flag entries + 2 usage-banner echoes — 07-04 deviation #1 documents why plan's strict `=3` was over-strict) | ✓ PASS |
| HITL HTML generation on fixture | `python3 html/gen_registry_review.py --draft spec/fixtures/v1.1/registry.draft.json --video <tiny> --shots ... --output /tmp/x.html` | exit 0; 21518-byte self-contained HTML with cluster cards + Export button + palette + Blob JS | ✓ PASS |
| call_reid route-down degrade | inline test: unreachable URL → empty clusters + warnings + exit 0 | exit 0; `clusters==[]`; 2 warnings with `preflight`/`ConnectError`/`character-reid` | ✓ PASS |
| call_reid cache-hit offline | inline test: pre-seeded per-video cache → `--offline` short-circuits | exit 0; 3 fixture clusters reused; stdout has `[reid] cache hit`; 0 network calls | ✓ PASS |
| apply_edits Pitfall 7 hard gate | inline test: draft with extra `char_099 proposed` cluster | `char_099` NEVER in canonical characters.json | ✓ PASS |
| apply_edits idempotency (Pitfall 5) | inline test: 2 isolated work_dirs, same fixture seed | byte-identical characters.json + props.json | ✓ PASS |
| CR-01 split partitions (not clones) | inline test: split char_001 (3 members) into day/night | char_002=[1,2] + char_003=[3] (partitioned); not both [1,2,3] | ✓ PASS |
| CR-02 graceful-degrade malformed cluster | inline test: cluster without cluster_id | `normalize_clusters` returns `[]`; no KeyError traceback | ✓ PASS |
| CR-03 type_override collision detection | inline test: char_002 → prop when prop_002 exists | exit non-zero with `collides with an existing cluster (data loss prevented)` | ✓ PASS |
| CR-05 merge forwards confirm intent | inline test: merge_groups=[[A,B]] + confirm_ids=[A,B] | canonical char_001 confirmed with appearance_shots=[1,2] (B's intent forwarded) | ✓ PASS |
| WR-03 mean_cosine clamp | inline test: route returns `mean_cosine=2.5` | clamped to 1.0; draft schema-valid | ✓ PASS |
| WR-04 producer-gate tighten | inline test: canonical with `review_state="rejected"` | `_producer_registry_integrity` flags as `must be 'confirmed' — Pitfall 7` | ✓ PASS |
| WR-06 string-encoded numeric frame_pos | inline test: `frame_pos="7.5"` | parsed as absolute seconds 7.5 (was 0.5 mid-shot default) | ✓ PASS |
| CONTRACT-06 conditional emission | inline test: build_asset_dict without/with registry files | without: keys absent (byte-identical v1.0); with: all 4 keys present | ✓ PASS |
| No shell=True anywhere (T-07-13) | `grep -cE 'shell=True' <all 7 phase 7 files>` | 0 across all files | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| --- | --- | --- | --- |
| `spec/validate.py` | `python3 spec/validate.py` | exit 0 | ✓ PASS |
| `verify_phase7_smoke.py` | `python3 scripts/verify_phase7_smoke.py` | exit 0; 5/5 scenarios green | ✓ PASS |
| `verify_phase6_smoke.py` (regression) | `python3 scripts/verify_phase6_smoke.py` | exit 0; 4/4 scenarios green | ✓ PASS |
| `verify_contract.py --mode=producer` (ep01) | `PHASE4_ASSET_DIR=<ep01> python3 scripts/verify_contract.py --mode=producer` | exit 0; 0 dangling | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **CAST-01** | 07-04 (deferred doc) | kais-aigc-platform `character-reid` route + driver (SAM3 → DINOv2 → clustering) | ✓ DEFERRED (cross-repo, pre-authorized) | Producer-side httpx client (`analysis/call_reid.py`) ships; live route does not exist in kais-aigc-platform today (verified during 07-RESEARCH). 07-04-SUMMARY "Deferred Items" table documents the post-merge smoke protocol. |
| **CAST-02** | 07-04 (deferred doc) | SAM3 multi-frame sampling (N=3-5 per shot, 25/50/75%) + mask_quality + unusable skip | ✓ DEFERRED (route-side) | `registry.schema.json#members[].mask_quality` is type-loose (accepts `'high'/'medium'/'low'/'unusable'` OR numeric); `QUALITY_RANK` in apply_edits.py + gen_registry_review.py uses these values for best-member selection. |
| **CAST-03** | 07-04 (deferred doc) | DINOv2 ViT-B/14 + AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ) | ✓ DEFERRED (route-side) | `normalize_clusters` is a shape-agnostic projector (CAST-05) — projects whatever shape the route emits onto registry.schema.json#clusters[] allowed fields; drops extras via additionalProperties:false. |
| **CAST-04** | 07-04 (deferred doc) | Three-tier thresholds (≥0.85/0.6-0.85/<0.6); default τ calibrated on ep01 | ✓ DEFERRED (calibration) — defaults locked advisory | `_tier_for` in `analysis/call_reid.py:124-138` implements the three CONTEXT-locked defaults; calibration protocol documented in 07-RESEARCH.md §DINOv2 Re-ID Methodology (same-person vs different-person histogram, valley pick). |
| **CAST-05** | 07-02 | Each cluster `review_state: proposed`; only `confirmed` flows downstream; produces `registry.draft.json` | ✓ SATISFIED (producer-side) | `normalize_clusters` hardcodes `review_state: "proposed"` (line 203); smoke scenario 1 confirms `registry.draft.json` written on route-down with empty clusters. NOTE: REQUIREMENTS.md line 124 has CAST-05 as "Pending" — this is a tracking-checkbox nit, NOT a gap (implementation is shipped + verified). |
| **CAST-06** | 07-01 (contract) + 07-03 (impl) | `html/gen_registry_review.py` HITL review HTML (first-class deliverable) | ✓ SATISFIED | 728-LOC generator; cluster cards + cosine-sorted queue (`_tier_sort_key` line 170) + three-tier viz + Export button (Blob+createObjectURL); CR-04 XSS escaping applied (body `_esc()` + JSON-in-script `</`→`<\/`). |
| **CAST-07** | 07-01 (contract) + 07-03 (impl) | `registry/apply_edits.py` → canonical `characters.json` + `props.json` (confirmed-only) | ✓ SATISFIED | 547-LOC standalone CLI; confirmed-only HARD GATE at build-entry (line 478); idempotent (Pitfall 5 verified); CR-01 partition splits + CR-03 collision detection + CR-05 merge forwarding all verified. |
| **CAST-08** | 07-03 (producer fallback) + 07-04 (deferred route-side) | best-of-N representative crop auto-selection → `characters/<id>.png` | ✓ SATISFIED (producer-side) / ✓ DEFERRED (route-side SAM3 crops) | `apply_edits.py:_extract_representative_png` uses `QUALITY_RANK` to pick best member + ffmpeg arg-list extraction; OMITS `representative_image` on ffmpeg failure (WARNING-2 fix — schema-optional). When route ships SAM3 foreground-masked crops, they supersede the producer-side fallback. |
| **CAST-09** | 07-02 (component) + 07-04 (integration) | `run_pipeline.py:step_reid` (after `step_semantic`); `--skip-reid`; graceful-degrade | ✓ SATISFIED | `step_reid` at slot 6 of 8; 3 new flags + shared `--offline`; smoke scenarios 1 (route_down) + 2 (skip_reid) + 5 (cache_hit_offline) all green; `--force` clears registry_draft + stamp + review_html. |

**Orphaned requirements:** None. All 9 CAST IDs are accounted for: 5 producer-side SATISFIED (CAST-05/06/07/08/09 partial-or-full) + 5 cross-repo DEFERRED with documented post-merge protocol (CAST-01/02/03/04 + CAST-08 route-side). NOTE: CAST-05 is the only ID marked "Pending" in REQUIREMENTS.md traceability matrix (line 124) — this is a stale checkbox; the producer-side implementation IS shipped and verified. Recommend updating the checkbox to `[x]` (out of scope for verification — flag for next plan/quick).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `scripts/verify_contract.py` | 1073, 1132 | `placeholder` references for `e2e` mode (Phase 4 carryover — NOT Phase 7 file) | ℹ️ Info | Pre-existing Phase 4 leftover; not introduced or modified by Phase 7. Out of scope. |
| `html/gen_registry_review.py` | 246, 634, 636 | `placeholder="展示名"` HTML attribute + JS reading it (legitimate HTML input placeholder, NOT a stub) | ℹ️ Info | Native HTML form placeholder semantics; intentional UX hint. Not a stub. |
| `analysis/call_reid.py` | 161, 164, 165, 179, 342 | `return []`, `clusters = []`, `members = []`, `cached = {}` | ℹ️ Info | All are legitimate initial-state / defense-in-depth defaults that get populated by route data or are the schema-valid degrade output (empty clusters on route-down). NOT stubs. |
| `registry/apply_edits.py` | 314, 337 | `clusters = {}`, `merged_members = []` | ℹ️ Info | Initial state populated by cluster-build loop + merge_groups application. NOT stubs. |

**Debt markers (TBD/FIXME/XXX):** NONE in Phase 7 modified files (`analysis/call_reid.py`, `registry/apply_edits.py`, `html/gen_registry_review.py`, `scripts/export_asset.py`, `scripts/verify_contract.py`, `scripts/verify_phase7_smoke.py`, `run_pipeline.py`, `spec/schemas/registry-edits.schema.json`). Gate is clean.

**Shell injection vector:** `grep -cE 'shell=True'` returns 0 across all 7 Phase 7 Python files. T-07-13 mitigation holds — all ffmpeg/subprocess invocations use arg-list form.

### Human Verification Required

Three items route to human verification — all **pre-authorized deferred** per CONTEXT.md `<deferred>` + 07-VALIDATION.md Manual-Only + STATE.md Blockers. They are the cross-repo / empirical-calibration / UX-pilot tail of Phase 7 that cannot be automated in the producer-side repo today. They do NOT block phase progression — Phase 7 ships as a fully-tested graceful-degrade producer; these items activate post-merge.

### 1. Live character-reid route round-trip against ep01

**Test:** Start kais-aigc-platform backend on the merged `feat/character-reid` route branch, run `python3 run_pipeline.py --video <ep01> ...` (no `--skip-reid`), confirm real `registry.draft.json` lands with non-empty `clusters[]` + representative crops + sane `_tier_for` classifications.
**Expected:** Non-empty clusters with DINOv2-derived mean_cosine values distributed across the three tiers (not all auto_merge / all auto_distinct); representative crops appear in the HITL review HTML.
**Why human:** Route is DEFERRED cross-repo (kais-aigc-platform, unmerged — mirrors Phase 6 `feat/shot-analysis-route` pre-merge state). Producer-side graceful-degrade is fully tested via `verify_phase7_smoke.py` scenario 1 (route-down → empty clusters + warnings + asset still exports, exit 0), but live ML round-trip cannot run without the unmerged route. Pre-authorized deferral per CONTEXT.md `<deferred>` + STATE.md Blockers.

### 2. Empirical three-tier τ calibration on ep01 character crops

**Test:** Post-merge, follow `07-RESEARCH.md` §DINOv2 Re-ID Methodology → "Deferred τ calibration protocol": collect same-person vs different-person cosine pairs from route-produced SAM3 foreground-masked crops (≥50 same + ≥200 different); plot overlaid histogram; pick valley as new τ; update `_tier_for` defaults + `registry.schema.json#clusters $comment`.
**Expected:** If distributions are well-separated, tighten `auto_merge`/`review` boundaries; if they overlap heavily on stylized insect animation, widen the review band + document that HITL review is load-bearing (CONTEXT Q2 explicit prediction).
**Why human:** Needs SAM3 foreground-masked character crops that do not exist until CAST-02 route ships. A full-frame DINOv2 spike now would mislead — background dominates embeddings on stylized insect animation; face detection fails on non-photoreal characters. CONTEXT Q2 explicitly locks literature defaults (`auto_merge ≥0.85` / `review 0.6-0.85` / `auto_distinct <0.6`) as advisory + defers empirical calibration to post-merge. `_tier_for` is documented as advisory; the `tier` field is the authoritative label.

### 3. HITL review HTML UX pilot against real ep01 clusters

**Test:** Open the generated `registry_review.html` in a browser against real route-produced clusters; confirm cluster cards are visually readable, thumbnails legible, merge/split/rename/confirm/reject controls intuitive, cosine-sorted queue surfaces the hardest mid-band decisions first, Export button produces a schema-valid `registry.edits.json` that round-trips through `apply_edits.py` cleanly.
**Expected:** Reviewer can complete a full review session without confusion; export → apply_edits → canonical characters.json/props.json flow works end-to-end on real clusters. Especially pilot the CR-01 split UX (per-label `member_indexes` partition input) — it requires the reviewer to assign source members to children, which is the most complex interaction.
**Why human:** 07-03 SUMMARY self-check verifies presence of cards/buttons/palette/Blob export (CAST-06 automated surface) but cannot judge usability. HITL HTML is a FIRST-CLASS deliverable per CONTEXT (`"一等交付物，非附属脚本"`) — visual ergonomics need human eyes. The 21518-byte fixture-rendered HTML passes all structural assertions; UX pilot confirms the design works on real (messier) cluster data.

### Gaps Summary

**No gaps.** All 12 must-have truths VERIFIED. All 11 code-review findings (CR-01..CR-05 BLOCKER + WR-01..WR-06 WARNING) empirically closed. All artifacts exist, are substantive, are wired, and flow real data. All key links connected. All automated probes green (`spec/validate.py`, `verify_phase7_smoke.py` 5/5, `verify_phase6_smoke.py` 4/4 regression, `verify_contract.py --mode=producer` on ep01). No debt markers in Phase 7 files. No `shell=True` injection vector. No anti-pattern stubs.

The three human-verification items are **pre-authorized deferred cross-repo / empirical / UX work** documented in CONTEXT.md `<deferred>` + 07-VALIDATION.md Manual-Only + 07-04-SUMMARY.md Deferred Items table. They activate when the `character-reid` route merges in kais-aigc-platform (mirrors Phase 6 deferral philosophy exactly). Phase 7 ships as a **fully-tested graceful-degrade producer** that demonstrably works end-to-end on the producer side today (smoke scenarios 1-5 prove every code path), with the ML half waiting on the cross-repo merge.

**Tracking nit (NOT a gap):** REQUIREMENTS.md line 124 has CAST-05 as "Pending" — the producer-side implementation IS shipped (call_reid.py `normalize_clusters` hardcodes `review_state: "proposed"`). Recommend updating the checkbox to `[x]` (defer to next plan/quick — out of scope for verification).

---

_Verified: 2026-07-25_
_Verifier: Claude (gsd-verifier)_
