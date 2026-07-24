---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
verified: 2026-07-25T00:00:00Z
status: passed
score: 4/4 roadmap success criteria + 18/18 PLAN must-have truths verified
overrides_applied: 0
re_verification:
  previous_status: none
  is_re_verification: false
human_verification:
  - test: "Gallery UX pilot — open generated timeline.html in browser against the v1.1 fixture set"
    expected: "Gallery cards render with thumbnails, ref-chips click-scroll to #gallery-<id>, fill-chip colors match operator expectation (green ✓ 运镜 when facets filled, gray ○ 降级 otherwise)"
    why_human: "Automated checks verify presence of cards/chips/anchors/escape forms; cannot verify visual readability, click-scroll UX feel, or color-perception. ADVISORY per 08-VALIDATION.md (non-blocking pilot)."
  - test: "Recomposed prompt_text readability pilot — spot-check 3-5 strings from output/<asset>/prompts.json"
    expected: "Pattern 2 recompose produces prose that reads naturally for downstream AI video pipelines; if awkward, adjust template (Claude's Discretion per CONTEXT Q2) + re-lock"
    why_human: "Deterministic template guarantees structure, not natural prose. ADVISORY per 08-VALIDATION.md (non-blocking pilot)."
---

# Phase 8: Prompt Reference System + shot-timeline HTML Gallery — Verification Report

**Phase Goal:** Prompts reference confirmed registry entries by ID (narrative continuity across shots), the asset carries a frozen `registry_snapshot` for reference stability, and users see a character/prop gallery + reference chips in the shot-timeline HTML.
**Verified:** 2026-07-25
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `prompts.json` post-processed to attach `character_refs[]`/`prop_refs[]` IDs to shots per `characters.json#appearance_shots[]`; `verify_contract.py` cross-file integrity confirms zero dangling prompt↔registry IDs (Pitfall 17 prevented) | ✓ VERIFIED | `prompts/attach_refs.py:121-155` inverts `appearance_shots[]` via `sorted(set(...))` (idempotent); fixture prompts.json shot 1 has `character_refs=['char_001','char_002']`, shot 2 has `prop_refs=['prop_001']`. `scripts/verify_contract.py:585-615` extends `_producer_registry_integrity` with prompts→registry direction; failure message includes `"Pitfall 17 — prompt dangling ref"`. Adversarial test: seeded `char_999` dangling ref → caught with Pitfall 17 message. `python3 scripts/verify_contract.py --mode=producer` exits 0 (0 dangling in fixture). |
| 2 | `prompt_text` recomposed referencing characters/props by identity → narrative-coherent prompt text consumable by downstream AI pipelines | ✓ VERIFIED | `prompts/attach_refs.py:158-190` `_recompose()` implements Pattern 2 locked template `[style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting]`. Fixture prompts.json shot 1 prompt_text: `3D 动画,写实渲染,柔和色彩 · 明亮城市街道,远景有树 · 角色:[少女, 路人] · 少女,白色衣裙 · ...`. Identity clauses skipped when refs empty (graceful-degrade); empty facets skipped. Idempotent (re-run produces byte-identical fixture, sha256 verified). |
| 3 | `gen_timeline_html.py` extended with: (a) character/prop gallery section rendering external png via `serve.py`; (b) clickable ref-chips linking back to gallery entries; (c) per-shot "运镜分析填充" chip indicator (green/gray) | ✓ VERIFIED | `html/gen_timeline_html.py:179-208` server-renders `<div class="gallery">` with `gallery-card` per entry (external `<img src="characters/char_001.png">` + `onerror="this.style.display='none'"` Pitfall 7 fallback + `_esc()` on every name). JS `buildShotChips()` at line 394-413 renders `<a href="#gallery-{id}" class="ref-chip char-chip|prop-chip">` anchors + `<span class="fill-chip fill-filled|fill-degraded">` (green when ALL 4 facets non-empty, gray otherwise). HTML generation test: `gallery-card` ×6, `ref-chip` ×10, `gallery-char_001` ×1 in generated HTML. `scroll-behavior:smooth` on html (line 227). |
| 4 | `asset.json` embeds `generator.registry_snapshot` freezing registry state at export time — later registry mutations cannot invalidate already-exported prompt refs (Pitfall 18 prevented) | ✓ VERIFIED | `scripts/export_asset.py:173-243` `_build_registry_snapshot(work_dir)` projects confirmed-only compact view; `build_asset_dict` line 352 calls it once + conditionally emits `**({"registry_snapshot": snapshot} if snapshot is not None else {})` at line 375. Spec fixture `asset.json#generator.registry_snapshot` mirrors canonical characters.json/props.json (2 chars + 1 prop). Adversarial freeze test: wrote asset.json → mutated characters.json (rename + new entry) → re-read disk asset.json → snapshot byte-identical (Pitfall 18 structural). `SCHEMA_VERSION="1.1"` (no bump — Pitfall 10 prevented). |

**Score:** 4/4 roadmap success criteria verified

### PLAN Must-Have Truths (combined across 08-01/02/03)

All 18 PLAN-level must_have truths verified — see evidence column above + artifact/key-link sections below. Highlights:

- asset.schema.json declares optional `registry_snapshot` (additive, `required:["tool","version","generated_at"]` unchanged, `additionalProperties:false` preserved at all 4 nesting levels)
- Old assets WITHOUT registry_snapshot still schema-validate green (CONTRACT-09 backward-compat — verified with synthetic v1.0-shape asset)
- SCHEMA_VERSION stays `"1.1"` (`scripts/export_asset.py:55`)
- attach_refs graceful-degrades (no registry → empty refs, facets-only prompt_text, exit 0)
- attach_refs idempotent (byte-identical re-run, sha256-hashed on real fixture)
- _producer_registry_integrity NOT forked (`grep -c 'def _producer_registry_integrity' == 1`, Pitfall 6 prevented)
- run_pipeline.py step_timeline invokes attach_refs BEFORE gen_timeline_html + mtime cache includes prompts_json (Pitfall 9 prevented)
- `[N/8]` count = 24 (unchanged from Phase 7), `[N/9]` count = 0 (Pitfall 5 phantom-bump prevented)
- HTML XSS defense: Python `_esc()` + JS `_esc()` + JSON-in-script `.replace("</", "<\\/")` on ALL 5 inlined JSON literals (shots/stems/transcript/characters/props). Smoke scenario 6 covers 5-sink × multi-payload matrix.
- Pitfall 7 confirmed-only snapshot filter (proposed/rejected entries never leak — adversarial test verified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `prompts/attach_refs.py` | Standalone CLI: attach refs + Pattern 2 recompose + idempotent + graceful-degrade + pre-write schema validate + atomic write | ✓ VERIFIED | 233 lines; 5 functions (`_atomic_write`, `_load_registry`, `_validate_registry` [WR-02 fix], `attach`, `_recompose`, `main`). ast.parse OK. CLI exits 0 on fixture. |
| `spec/fixtures/v1.1/prompts.json` | Synced to Pattern 2 recompose output (contract oracle) | ✓ VERIFIED | shot 1 contains `角色:[少女, 路人]`; shot 2 contains `道具:[落叶]`. Re-running attach_refs produces byte-identical file (sha256 match). |
| `scripts/export_asset.py` | `_build_registry_snapshot` + conditional emit; SCHEMA_VERSION="1.1" | ✓ VERIFIED | Helper at line 173-243; conditional emit at line 375. Returns None when no registry (graceful-degrade byte-identical to v1.0). |
| `scripts/verify_contract.py` | `_producer_registry_integrity` extended with prompts→registry (Pitfall 17) | ✓ VERIFIED | Extension at line 585-615 inside existing function (not forked). Gated on prompts.json existence. |
| `scripts/verify_phase8_smoke.py` | 6-scenario regression (mirror verify_phase7_smoke.py) | ✓ VERIFIED | 681 lines; 6 scenarios all PASS via `python3 scripts/verify_phase8_smoke.py` → `[phase8-smoke] OK: 6/6 scenarios green` exit 0. |
| `html/gen_timeline_html.py` | Gallery + chips + indicator + _esc + JSON-in-script defense | ✓ VERIFIED | Python `_esc()` line 24-41; JS `_esc()` line 384-388; `buildShotChips()` line 394-413; gallery section server-rendered line 179-208; JSON-in-script defense on 5 literals (line 159-163); 4 new CLI flags (line 1188-1199). |
| `run_pipeline.py` | step_timeline invokes attach_refs pre-step + mtime cache + --prompts/--characters/--props/--asset-json | ✓ VERIFIED | `step_timeline` signature line 316-320; attach_refs subprocess line 333-339 (plain banner, no [N/M]); cache inputs extended line 347-353; gen_timeline_html flags line 378-391. |
| `spec/schemas/asset.schema.json` | Additive optional `generator.registry_snapshot` declaration | ✓ VERIFIED | Line 61-110; strict `additionalProperties:false` at every level; `required:["characters","props"]` inside snapshot; item shape with id pattern + name minLength + optional representative_image anti-traversal pattern + appearance_shots int array. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `prompts/attach_refs.py:attach` | `characters.json#appearance_shots[]` + `props.json#appearance_shots[]` | invert appearance_shots → shot_id→[ids] map; sorted(set(...)) | ✓ WIRED | Verified by smoke scenario 2: shot 1 character_refs==[char_001,char_002] (matches fixture appearance_shots) |
| `prompts/attach_refs.py:_recompose` | Pattern 2 locked template | `[style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting]` | ✓ WIRED | Verified by fixture prompts.json shot 1 prompt_text content |
| `scripts/export_asset.py:build_asset_dict` | `asset.json#generator.registry_snapshot` | `_build_registry_snapshot(work_dir)` → conditional emit when not None | ✓ WIRED | Verified by adversarial test + spec fixture asset.json content |
| `scripts/verify_contract.py:_producer_registry_integrity` | prompts.character_refs[]/prop_refs[] ⊆ confirmed characters.json/props.json IDs | additive block after Phase 7 characters/props loop | ✓ WIRED | Verified by adversarial dangling-ref test (char_999 caught) |
| `run_pipeline.py:step_timeline` | `prompts/attach_refs.py` + `html/gen_timeline_html.py` | subprocess attach_refs BEFORE gen_timeline_html | ✓ WIRED | Code at line 333-392; verified by `python3 run_pipeline.py --help` exit 0 + structural code review |
| `html/gen_timeline_html.py ref-chip anchors` | `#gallery-<id>` | in-page href + CSS scroll-behavior:smooth | ✓ WIRED | `<a href="#gallery-' + encodeURIComponent(cid) + '"` in buildShotChips; `html { scroll-behavior:smooth; }` line 227 |
| `html/gen_timeline_html.py main()` gallery data source | `asset.json#generator.registry_snapshot` (preferred) → `--characters`/`--props` (fallback) | `--asset-json` flag + snapshot lookup + fallback chain | ✓ WIRED | Code at line 1231-1252; verified by HTML generation against fixture (gallery-card x6) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `html/gen_timeline_html.py` gallery | `characters_data` / `props_data` | `--asset-json` registry_snapshot preferred; `--characters`/`--props` fallback | ✓ Real fixture data (char_001 少女 + char_002 路人 + prop_001 落叶) | ✓ FLOWING |
| `html/gen_timeline_html.py` ref-chips | `s.character_refs` / `s.prop_refs` | `prompts_by_id` from `--prompts` flag → `build_shots_js` | ✓ Real refs (shot 1: [char_001,char_002]; shot 2: [prop_001]) | ✓ FLOWING |
| `html/gen_timeline_html.py` fill-chip | `s.route_filled` | `prompts_by_id` camera/action/lighting/style non-empty check | ✓ Real route-fill state | ✓ FLOWING |
| `prompts/attach_refs.py` output | `character_refs` / `prop_refs` / `prompt_text` | `characters.json` / `props.json` inversion + Pattern 2 template | ✓ Real registry-driven refs | ✓ FLOWING |
| `scripts/export_asset.py` snapshot | `generator.registry_snapshot` | `_build_registry_snapshot(work_dir)` reads characters.json/props.json | ✓ Real confirmed-only registry data | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| spec validate green (10 v1.1 + 6 minimal shapes) | `python3 spec/validate.py` | exit 0; `[validate] OK` | ✓ PASS |
| Phase 8 smoke 6/6 scenarios green | `python3 scripts/verify_phase8_smoke.py` | exit 0; `[phase8-smoke] OK: 6/6 scenarios green` | ✓ PASS |
| Phase 7 smoke regression (5/5) | `python3 scripts/verify_phase7_smoke.py` | exit 0; `[phase7-smoke] OK: 5/5 scenarios green` | ✓ PASS |
| Phase 6 smoke regression (4/4) | `python3 scripts/verify_phase6_smoke.py` | exit 0; `[phase6-smoke] OK: 4/4 scenarios green` | ✓ PASS |
| Producer contract gate green | `python3 scripts/verify_contract.py --mode=producer` | exit 0; 0 dangling refs | ✓ PASS |
| Step-counter lock `[N/8]`=24 / `[N/9]`=0 | `grep -cE '\[[1-8]/8\]' run_pipeline.py` | 24 / 0 | ✓ PASS |
| attach_refs idempotent on real fixture | sha256-hash before/after attach_refs run | byte-identical (`669668d0...`) | ✓ PASS |
| Snapshot freeze (Pitfall 18) | write asset → mutate characters.json → re-read disk asset | snapshot byte-identical | ✓ PASS |
| Pitfall 17 dangling ref detection | seed char_999 in prompts.json → _producer_registry_integrity | failure mentions `char_999` + `Pitfall 17` | ✓ PASS |
| Pitfall 7 confirmed-only filter | seed confirmed+proposed+rejected → _build_registry_snapshot | snapshot contains only `['char_001']` | ✓ PASS |
| Graceful-degrade (no registry → snapshot OMITTED) | build_asset_dict with no characters.json/props.json | `generator` keys = `['tool','version','generated_at']` only | ✓ PASS |
| HTML gallery generation | `python3 html/gen_timeline_html.py --shots ... --characters ... --props ... --prompts ... --asset-json ... --output /tmp/phase8_timeline.html` | exit 0; HTML contains gallery-card x6 + ref-chip x10 + gallery-char_001 anchor | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
|------|---------|--------|--------|
| Phase 8 smoke | `bash scripts/verify_phase8_smoke.py` (via `python3`) | `[phase8-smoke] OK: 6/6 scenarios green`, exit 0 | PASS |
| Phase 7 smoke regression | `bash scripts/verify_phase7_smoke.py` (via `python3`) | `[phase7-smoke] OK: 5/5 scenarios green`, exit 0 | PASS |
| Phase 6 smoke regression | `bash scripts/verify_phase6_smoke.py` (via `python3`) | `[phase6-smoke] OK: 4/4 scenarios green`, exit 0 | PASS |
| spec validate | `bash spec/validate.py` (via `python3`) | minimal failures=0, v1.1 failures=0, exit 0 | PASS |
| producer contract | `bash scripts/verify_contract.py --mode=producer` (via `python3`) | OK, exit 0 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROMPT-01 | 08-02 | Attach `character_refs[]`/`prop_refs[]` per `appearance_shots[]` | ✓ SATISFIED | `prompts/attach_refs.py`; smoke scenario 2 (idempotent + correct refs) |
| PROMPT-02 | 08-02 | Recompose `prompt_text` referencing characters/props by identity | ✓ SATISFIED | Pattern 2 template in `_recompose`; fixture prompts.json shows `角色:[少女, 路人]` + `道具:[落叶]` |
| PROMPT-03 | 08-02 | Cross-file integrity check (no dangling prompt↔registry IDs) | ✓ SATISFIED | `scripts/verify_contract.py:585-615`; smoke scenario 4 (Pitfall 17 dangling-ref detected) |
| PROMPT-04 | 08-01 + 08-02 | `asset.json#generator.registry_snapshot` freezes registry at export | ✓ SATISFIED | Schema declared (Plan 01); `_build_registry_snapshot` emits (Plan 02); smoke scenarios 3 (freeze) + 5 (confirmed-only) |
| PRESENT-01 | 08-03 | `gen_timeline_html.py` character/prop gallery section | ✓ SATISFIED | `gallery-card` CSS+HTML; HTML generation produces gallery with thumbnails + onerror fallback |
| PRESENT-02 | 08-03 | Reference chips in prompt rendering linking to gallery | ✓ SATISFIED | JS `buildShotChips()` renders `<a href="#gallery-<id>" class="ref-chip char-chip|prop-chip">` |
| PRESENT-03 | 08-03 | Per-shot "运镜分析填充" chip indicator (green/gray) | ✓ SATISFIED | `route_filled` computed in `build_shots_js`; `fill-chip fill-filled` (green) / `fill-degraded` (gray) classes |

**Orphaned requirements:** None. REQUIREMENTS.md maps PROMPT-01..04 + PRESENT-01..03 to Phase 8 (all 7 IDs appear in plan frontmatter and are satisfied). PRESENT-04/05/06 are explicitly Phase 9 (deferred, not orphaned — Traceability table line 136-138).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `html/gen_timeline_html.py` | 692, 751 | `console.log` debug statements in embedded production HTML | ℹ️ Info | IN-01 in 08-REVIEW.md; explicitly accepted out-of-scope (INFO-only, not addressed by REVIEW-FIX). Debug-only, no functional impact. |
| `run_pipeline.py` | 48 | `shot_XXX.json` filename pattern in docstring | ℹ️ Info | NOT a debt marker — `XXX` is a numeric placeholder (e.g. `shot_001.json`, `shot_002.json`). Pattern documented in CINEMA-04 cache key convention. |

**No 🛑 BLOCKER anti-patterns** (no unreferenced TBD/FIXME/XXX, no TODO/HACK/PLACEHOLDER, no empty implementations, no orphaned artifacts, no unwired code paths).

### Human Verification Required

### 1. Gallery UX Pilot

**Test:** Open the generated `timeline.html` (from `python3 html/gen_timeline_html.py --shots spec/fixtures/v1.1/shots.json --characters spec/fixtures/v1.1/characters.json --props spec/fixtures/v1.1/props.json --prompts spec/fixtures/v1.1/prompts.json --asset-json spec/fixtures/v1.1/asset.json --output /tmp/phase8_timeline.html`) in a browser.
**Expected:** Gallery cards render with thumbnails (char_001 少女, char_002 路人, prop_001 落叶); ref-chips in shot rows click-scroll to the matching `#gallery-<id>` anchor; fill-chip shows green `✓ 运镜` for route-filled shots, gray `○ 降级` for offline-degraded shots; missing PNGs degrade silently (onerror hides broken icon).
**Why human:** Automated checks verify presence of `gallery-card`, `ref-chip`, anchor IDs, and escaped forms, but cannot verify visual readability, click-scroll UX feel, color contrast, or aspect-ratio rendering.

### 2. Recomposed prompt_text Readability Pilot

**Test:** Spot-check 3-5 recomposed `prompt_text` strings from a real `output/<asset>/prompts.json` (the fixture has 2 samples; generate more by running the full pipeline against a longer video).
**Expected:** The Pattern 2 recompose (`[style] · [scene] · 角色:[names] · 道具:[names] · [subject] · [action] · [camera] · [lighting]`) produces prose that reads naturally for downstream AI video pipelines.
**Why human:** Deterministic template guarantees structure but not natural prose. If awkward, the Pattern 2 template prose can be adjusted (Claude's Discretion per CONTEXT Q2) and re-locked.

> **Scope clarification (per 08-VALIDATION.md + 08-03-SUMMARY.md):** These 2 manual items are **advisory UX/readability pilots, NOT blockers**. Every Phase 8 requirement is testable NOW on the v1.1 fixture set (verified by `scripts/verify_phase8_smoke.py` 6/6 green + `spec/validate.py` + `verify_contract.py --mode=producer`). Per scope_context: "If all automated must-haves pass, status should be `passed` (the 2 pilots are advisory)."

### Gaps Summary

**No gaps.** All 4 roadmap success criteria verified, all 7 requirement IDs satisfied, all 18 PLAN must_have truths verified, all 7 artifacts exist + substantive + wired + flowing real data, all 7 key links wired, all 6 review findings (1 BLOCKER + 5 WARNING) closed (REVIEW-FIX.md status=`all_fixed`), no blocker anti-patterns, no orphaned requirements.

**Status: passed.**

Phase 8 producer-side prompt references + snapshot freeze + Pitfall 17 integrity + gallery + chips + indicator all wired end-to-end. Phase 9 (canvas consumer) is the cross-repo follow-up that consumes the now-frozen producer contract.

---

_Verified: 2026-07-25_
_Verifier: Claude (gsd-verifier)_
