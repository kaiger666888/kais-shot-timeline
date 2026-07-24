---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
plan: 04
subsystem: pipeline-integration
tags: [pipeline, export, contract-verify, smoke-regression, graceful-degrade]
requires:
  - 07-02-SUMMARY.md   # analysis/call_reid.py
  - 07-03-SUMMARY.md   # registry/apply_edits.py + html/gen_registry_review.py
provides:
  - "run_pipeline.py step_reid integration (slot 6 of 8)"
  - "export_asset.py conditional characters/props emission (CONTRACT-06 closure)"
  - "verify_contract.py producer-side registry↔shots integrity (Pitfall 7 second-line)"
  - "scripts/verify_phase7_smoke.py 5-scenario permanent regression"
affects:
  - run_pipeline.py
  - scripts/export_asset.py
  - scripts/verify_contract.py
tech-stack:
  added: []
  patterns:
    - "step_reid mirrors step_semantic TOCTOU-safe mtime cache + video identity sidecar (WR-01/WR-07)"
    - "Conditional emission via file-existence gating (byte-identical to v1.0 when absent)"
    - "Producer-gate additive integrity check (Pitfall 7 second-line defense-in-depth)"
    - "5-scenario standalone sys.exit(0/1) smoke harness mirroring verify_phase6_smoke.py"
key-files:
  created:
    - scripts/verify_phase7_smoke.py
  modified:
    - run_pipeline.py
    - scripts/export_asset.py
    - scripts/verify_contract.py
decisions:
  - "step_reid makes TWO subprocess calls (call_reid.py + gen_registry_review.py) but stays non-blocking per CONTEXT Q2 — apply_edits remains standalone CLI"
  - "export_asset pre-write PNG assert placed inside build_asset_dict (before return) so warning propagates to generator.warnings; stems/video assert in main() stays FATAL"
  - "Pitfall 7 second-line assert lives in producer gate (_producer_registry_integrity) as defense-in-depth alongside apply_edits.py build-time hard gate"
metrics:
  duration: 22min
  completed: 2026-07-25
  tasks: 3
  files: 4
---

# Phase 7 Plan 04: Pipeline Integration + CONTRACT-06 Closure + Smoke Regression Summary

Wired Phase 7 Wave 2 outputs (`call_reid.py` + `apply_edits.py` + `gen_registry_review.py`) into the pipeline + exporter + verifier; locked the producer-side graceful-degrade regressions; documented the 5 cross-repo deferred requirements.

## What Was Built

### 1. `run_pipeline.py` — step_reid (slot 6 of 8) + counter + flags

- **`step_reid` function** mirrors `step_semantic` shape exactly: skip short-circuit, video identity sidecar (WR-01 path+size+mtime_ns), TOCTOU-safe mtime cache via `_safe_mtime`, `subprocess.run(check=True)` fail-loud. Makes TWO subprocess calls: `analysis/call_reid.py` (POST character-reid → `registry.draft.json`), then `html/gen_registry_review.py` (HITL HTML). Non-blocking per CONTEXT Q2 — `apply_edits.py` is a separate standalone CLI.
- **Counter renumber**: 20 old `[N/7]` → `[N/8]` (timeline moves `[6/7]`→`[7/8]`, export moves `[7/7]`→`[8/8]`, slots 1–5 unchanged). 4 new `[6/8]` labels inside `step_reid` (skip + cache + call_reid banner + gen_registry_review banner) → **24 total `[N/8]` occurrences**, verified by `grep -cE '\[[1-8]/8\]' run_pipeline.py`.
- **3 new argparse flags**: `--skip-reid`, `--reid-url` (default `http://127.0.0.1:8000/api/v1/production/character-reid`), `--reid-timeout` (default 960.0s). `--offline` (Phase 6) shared. All carry Chinese `help=` strings per CLAUDE.md convention.
- **`--force` cache list extended**: `registry_draft` + `registry_draft + ".video-stamp"` + `review_html` added; `route_cache/` rmtree already covers `character_reid/` subdir.
- **Module docstring** updated: 8-step pipeline list + new output-layout entries (`registry.draft.json`, `registry_review.html`, `route_cache/character_reid/video_<vch>.json`).

### 2. `scripts/export_asset.py` — CONTRACT-06 closure

- `build_asset_dict` restructured: `data_block` + `media_block` assembled as locals first, then conditional `characters`/`props` appended. `data.characters`/`data.props` (relative `.json` paths) + `media.characters[]`/`media.props[]` (relative `.png` paths via `glob`) emitted **ONLY** when files exist on disk.
- Old assets (no registry) stay **byte-identical to v1.0** — fields OMITTED. Schema optional. Verified inline: no-registry build → no fields; with-registry build → all 4 fields present.
- Pre-write PNG assert: **NON-FATAL** for character/prop PNGs (CAST-09 graceful-degrade / WARNING-2 fix). Placed inside `build_asset_dict` before `return` so the warning propagates into `generator.warnings`. Stems/video pre-write assert in `main()` stays FATAL (required + always present).
- `import glob` added at module top.

### 3. `scripts/verify_contract.py` — producer registry integrity

- New `_producer_registry_integrity(asset_dir)` helper (additive, gated on file existence — no-op for v1.0 assets without registry files). Checks:
  - (a) `appearance_shots[]` in characters/props ⊆ `shots.json` IDs (no dangling)
  - (b) `registry.draft.json` cluster `members[].shot_id` ⊆ `shots.json` IDs
  - (c) canonical IDs unique + match `^(char|prop)_[0-9]{3}$`
  - (d) NO `review_state:"proposed"` in canonical files (**Pitfall 7 second-line assert** — defense-in-depth alongside `apply_edits.py`'s build-time hard gate)
- Wired into `run_producer_check` AFTER `validate_eight_shapes` BEFORE `_cross_version_check`. No regression: ep01 has no registry files → check is a no-op.
- `EIGHT_SHAPES` array deliberately NOT renamed (historical alias) and `registry-edits` deliberately NOT added (it's an operator review artifact, not a canonical asset-dir shape — its schema regression is owned by `spec/validate.py`).

### 4. `scripts/verify_phase7_smoke.py` — 5-scenario regression

Standalone `sys.exit(0/1)` script (no pytest), mirroring `verify_phase6_smoke.py` structure verbatim:

| # | Scenario | Locks | Assertions |
|---|----------|-------|------------|
| 1 | `route_down` | CAST-09 graceful-degrade | `call_reid.py` vs `http://127.0.0.1:1/...` → exit 0 + `clusters == []` + warnings ≥1 with `preflight`/`ConnectError`/`character-reid` |
| 2 | `skip_reid` | CAST-09 flag | `run_pipeline.step_reid(skip=True)` → stdout has `--skip-reid: skipping` + NO `[6/8] cross-shot re-id` banner (subprocess never spawned) |
| 3 | `empty_draft_handoff` | CAST-05/06/07 boundary | Empty `clusters:[]` draft → `gen_registry_review.py` still emits HTML with `Export edits` button + `apply_edits.py` exits 0 with `characters.json == []` + `props.json == []` |
| 4 | `apply_edits_idempotent` | CAST-07 + Pitfall 5 | 2 independent work_dirs with same fixture seed → byte-identical canonical files + all `review_state="confirmed"` (Pitfall 7) + schema-valid + `appearance_shots ⊆ [1, 2]` + canonical IDs ⊆ `confirm_ids` |
| 5 | `cache_hit_offline` | CAST-09 + CINEMA-04 analog | Pre-seed `route_cache/character_reid/video_<vch>.json` with fixture + matching `_cache_key` → `call_reid.py --offline` → exit 0 + draft has `char_001` from cache + stdout has `[reid] cache hit` |

All 5 green via `python3 scripts/verify_phase7_smoke.py`; outputs `[phase7-smoke] OK: 5/5 scenarios green`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Plan's `--help` grep expected 3 matches, actual is 5**

- **Found during:** Task 1 verification
- **Issue:** The plan's automated verify block does `python3 run_pipeline.py --help | grep -cE '\-\-skip-reid|\-\-reid-url|\-\-reid-timeout' | grep -qE '^(3)$'` expecting exactly 3. Actual is 5 because argparse's usage banner echoes the flag names too (`[--skip-reid]`, `[--reid-url REID_URL] [--reid-timeout REID_TIMEOUT]` on the usage line + the 3 flag-block entries).
- **Fix:** No code change needed — the 3 argparse flags ARE present in `--help` and behave correctly. The verification script's count expectation was over-strict. Documented here for transparency; the plan's spirit ("all 3 new flags appear in `--help`") is met.
- **Files modified:** None (no-op; semantic check passes)
- **Commit:** (rolled into Task 1 commit `99fbbc3`)

**2. [Rule 2 — Auto-add missing critical functionality] Pre-write PNG assert placement**

- **Found during:** Task 2 implementation
- **Issue:** Plan's prose says the character/prop PNG pre-write assert goes "near the existing stems pre-write assert (lines 340-343) in `main()`". But `build_asset_dict` is called BEFORE that assert in `main()`, so a warning appended to `warnings` there would NOT propagate into `generator.warnings` (the dict is already constructed).
- **Fix:** Placed the character/prop PNG check INSIDE `build_asset_dict`, right before the `return` statement. `warnings` mutation now happens before dict construction → warning correctly flows into `generator.warnings`. The stems/video FATAL assert stays in `main()` (unchanged).
- **Files modified:** `scripts/export_asset.py`
- **Commit:** `a7c114e`

## Phase 7 Gate (all 4 plans together)

| Check | Status |
|-------|--------|
| `python3 spec/validate.py` (Plan 01: registry-edits schema + 10-shape regression) | green |
| `analysis/call_reid.py` degrade + cache paths (Plan 02) | green (verified via smoke scenarios 1 + 5) |
| `registry/apply_edits.py` confirmed-only + idempotent (Plan 03) | green (verified via smoke scenario 4) |
| `html/gen_registry_review.py` HITL HTML on empty + populated drafts (Plan 03) | green (verified via smoke scenarios 3 + manual run on fixture) |
| `scripts/verify_phase7_smoke.py` 5-scenario regression (Plan 04) | green (5/5) |
| `python3 scripts/verify_contract.py --mode=producer` (no regression) | green |
| `python3 scripts/verify_phase6_smoke.py` (no Phase 6 regression) | green (4/4) |
| `python3 run_pipeline.py --help` shows 3 new flags | green |

## Deferred Items

The following requirements are **deferred cross-repo** per CONTEXT `<deferred>` lock + 07-RESEARCH.md §DINOv2 Re-ID Methodology post-merge protocol. Phase 7 ships as a **graceful-degrade producer** — live route round-trip + empirical τ calibration become **post-merge smoke checks** (NOT Phase 7 gates).

| REQ | Description | Deferred Rationale | Post-Merge Verification Protocol |
|-----|-------------|---------------------|-----------------------------------|
| **CAST-01** | `character-reid` route + driver | Cross-repo in `kais-aigc-platform` (mirrors `feat/shot-analysis-route`, unmerged). shot-timeline producer-side is fully buildable + testable without it (proven by Phase 7 gate green). | Post-merge smoke: start backend on the merged route branch, run `step_reid` against ep01, confirm real `registry.draft.json` lands with non-empty `clusters[]` + representative crops. Reference: 07-CONTEXT.md `<deferred>`. |
| **CAST-02** | SAM3 multi-frame mask sampling (N=3–5 per shot at 25/50/75% positions) | Route-side. Producer schema (`registry.schema.json#members[].mask_quality`) is deliberately type-loose (`"high"/"medium"/"low"/"unusable"` enum) to accept future driver output without contract bump. | Post-merge smoke: verify route emits `members[].mask_quality` populated; spot-check `unusable` frames actually excluded from clustering (Pitfall 6). Reference: 07-RESEARCH.md §SAM3 multi-frame sampling. |
| **CAST-03** | DINOv2 ViT-B/14 embeddings + `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)` | Route-side. `analysis/call_reid.py:normalize_clusters` is a shape-agnostic projector (CAST-05) — it normalizes whatever shape the route emits via explicit field projection. No producer-side ML deps. | Post-merge smoke: verify cluster `mean_cosine` distribution looks sane (not all 1.0 / all 0.0); cross-reference against route's own embedding logs. Reference: 07-RESEARCH.md §Pattern 1 (shape-agnostic projection). |
| **CAST-04** | Three-tier τ calibration on ep01 (same-person vs different-person cosine histogram, valley pick) | Deferred per CONTEXT Q2. Literature defaults (`auto_merge ≥ 0.85` / `review 0.6–0.85` / `auto_distinct <0.6`) locked as **advisory** in `registry.schema.json $comment` + `_tier_for` function. Calibration needs SAM3 character crops (clean foreground masks) — those don't exist until CAST-02 ships. A full-frame DINOv2 spike now would mislead (background dominates embeddings on stylized insect animation). | Post-merge protocol per 07-RESEARCH.md §DINOv2 Re-ID Methodology "Deferred τ calibration protocol": (1) collect same-person vs different-person cosine pairs from route-produced crops; (2) plot histogram; (3) pick valley as new τ; (4) update `_tier_for` defaults + `registry.schema.json $comment`. Reference: STATE.md "Blockers/Concerns" → "DINOv2 threshold calibration". |
| **CAST-08** | Route-side best-of-N representative crop selection (cleanest foreground mask) | Deferred. Producer-side `ffmpeg` frame-extraction fallback implemented in `registry/apply_edits.py` (Plan 03) — picks best member by `mask_quality` rank, extracts frame at `frame_pos`. When route ships SAM3 crops, they **supersede** the producer-side fallback (cleaner foreground masks). | Post-merge: route emits `outputDir/crops/<cluster_id>.png`; `apply_edits.py` prefers route crops when present, falls back to `ffmpeg` otherwise. Reference: 07-CONTEXT.md `<deferred>` (representative PNG). |

**Reference docs:**
- `07-CONTEXT.md` §`<deferred>` — locked deferral scope decisions
- `07-RESEARCH.md` §DINOv2 Re-ID Methodology — post-merge τ calibration protocol
- `STATE.md` §Blockers/Concerns — cross-repo branch merge prerequisite + DINOv2 τ spike entry

## Threat Surface Scan

No new threat surface introduced beyond what the plan's `<threat_model>` already mitigates:
- `--force` rmtree scope (T-07-17): mitigated by fixed known-paths list, no user-supplied paths.
- `--reid-timeout` DoS (T-07-18): mitigated by explicit default 960s + preflight short-circuit (5s).
- export_asset.py PNG glob (T-07-19): mitigated by fixed canonical dirs + asset.schema.json anti-traversal pattern.
- Producer Pitfall 7 leak (T-07-20): mitigated by `_producer_registry_integrity` second-line assert.
- step_reid cache silent-skip (T-07-21): mitigated by `[6/8]` labeled stdout on both skip + cache-hit paths.
- Temp-dir leak (T-07-22): mitigated by `tempfile.mkdtemp` + `finally: shutil.rmtree(ignore_errors=True)` per scenario.

## Self-Check: PASSED

Files created/modified verified to exist; commits verified in git log.

**Files:**
- `FOUND: run_pipeline.py` (modified — step_reid + counter + flags)
- `FOUND: scripts/export_asset.py` (modified — conditional emission)
- `FOUND: scripts/verify_contract.py` (modified — `_producer_registry_integrity`)
- `FOUND: scripts/verify_phase7_smoke.py` (created — 5 scenarios)

**Commits:**
- `FOUND: 99fbbc3` — feat(07-04): add step_reid (slot 6 of 8) + [N/7]→[N/8] renumber + 3 flags
- `FOUND: a7c114e` — feat(07-04): close CONTRACT-06 emission + producer registry integrity
- `FOUND: 7e30657` — test(07-04): add verify_phase7_smoke.py 5-scenario regression harness
