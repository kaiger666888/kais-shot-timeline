---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
plan: 03
subsystem: producer-ui
tags: [html-gallery, ref-chips, semantic-fill-indicator, xss-defense, cr-04-carry, pipeline-wiring, pitfall-9, smoke-harness]

# Dependency graph
requires:
  - phase: 08-prompt-reference-system-shot-timeline-html-gallery
    plan: 02
    provides: "prompts/attach_refs.py (refs + Pattern 2 recompose) + scripts/export_asset.py registry_snapshot + scripts/verify_contract.py Pitfall 17 — the producer substrate this plan renders + wires"
  - phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
    provides: "html/gen_registry_review.py:79-91 _esc() helper (CR-04 fix commit 336d04f) — copied verbatim into gen_timeline_html.py"
provides:
  - "html/gen_timeline_html.py — gallery section + reference chips + semantic-fill indicator + _esc() (Python + JS) + JSON-in-script .replace defense (PRESENT-01/02/03 + XSS hardening)"
  - "run_pipeline.py:step_timeline — invokes attach_refs.py as pre-step + mtime cache includes prompts_json (Pitfall 9 prevented) + passes --prompts/--characters/--props/--asset-json to gen_timeline_html"
  - "scripts/verify_phase8_smoke.py — 6-scenario Phase 8 regression (graceful-degrade / idempotency / snapshot freeze / integrity / confirmed-only / XSS inert)"
affects: [09-canvas-consumer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HTML XSS hardening carry-over (Phase 7 CR-04 fix 336d04f verbatim): Python _esc() for body/attribute context + .replace('</', '<\\/') after every json.dumps landing in <script>. Applied to 5 inlined JSON literals + every name interpolation in gallery card HTML + JS ref-chip template literals."
    - "JS-side _esc mirrors Python _esc — ref-chips are client-rendered (name resolves from CHARACTERS/PROPS at chip-build time), so JS string context needs its own escape. Mirrors Python escape semantics (5 chars: & < > \" ')."
    - "Pre-step pattern (CONTEXT Q3 lock): attach_refs invoked WITHIN step_timeline BEFORE gen_timeline_html — NO new numbered step, NO [N/8]→[N/9] counter bump. Banner label intentionally omits [N/M] prefix to keep step-banner grep count at 24."
    - "Mtime cache input extension (Pitfall 9): prompts_json added to step_timeline cache inputs. attach_refs runs BEFORE cache check → new prompts.json mtime → cache miss → timeline regenerates with new refs/chips."
    - "Gallery data source priority (RESEARCH Open Question 2 resolution): asset.json#generator.registry_snapshot preferred (export-time truth) → characters.json/props.json fallback (mid-pipeline before export) → None (gallery OMITTED, graceful-degrade)."
    - "Smoke scenario 6 XSS-inert assert: seed name='</script><script>alert(1)</script>' → assert literal payload does not survive in HTML. Covers BOTH body context (_esc → &lt;/script&gt;) and JSON-in-script context (.replace → <\\/script>)."

key-files:
  created:
    - scripts/verify_phase8_smoke.py
  modified:
    - html/gen_timeline_html.py
    - run_pipeline.py

key-decisions:
  - "attach_refs banner label omits [N/M] prefix to satisfy the must_have '[N/8] count unchanged at 24'. The plan RESEARCH Pattern 6 suggested '[7/8] prompt-ref attachment' but the count-lock truth in must_haves takes precedence (Rule 2 — both constraints must be satisfied). Plain label 'prompt-ref attachment (attach_refs pre-step)' clearly signals the step context without contributing to the grep count."
  - "JS-side _esc is a runtime function (not a const) — mirrors Python _esc semantics 1:1 (5-char escape, & first to prevent double-escape). Used by buildShotChips() template literals so chip names resolve + escape at render time, not at server-build time."
  - "Gallery HTML rendered server-side (Python f-string) using _esc on every operator-influenced interpolation. JS-side _esc is for the chips that resolve names from CHARACTERS/PROPS at client-render time. Two-layer defense consistent with Phase 7 CR-04."
  - "Smoke scenario 3 (snapshot_freeze) double-asserts: (a) re-read of disk asset.json shows snapshot unchanged after registry mutation (freeze guarantee), AND (b) re-call of build_asset_dict shows NEW snapshot reflecting mutation (proves the freeze is structural to the disk artifact, not a build-time cache)."

requirements-completed: [PRESENT-01, PRESENT-02, PRESENT-03]

# Metrics
duration: 16min
completed: 2026-07-24
---

# Phase 8 Plan 03: HTML Gallery + Pipeline Wiring + Smoke Summary

**Three additive changes closing Phase 8's user-visible surface: `html/gen_timeline_html.py` extended with a character/prop gallery + clickable reference chips + per-shot semantic-fill indicator (PRESENT-01/02/03) carrying Phase 7 CR-04 XSS hardening verbatim; `run_pipeline.py:step_timeline` wired to invoke `prompts/attach_refs.py` as a pre-step with the mtime cache extended to include prompts_json (Pitfall 9 prevented); and a new 6-scenario `scripts/verify_phase8_smoke.py` regression harness mirroring the Phase 7 smoke structure.**

## Performance

- **Duration:** ~16 min (963s)
- **Started:** 2026-07-24T20:38:25Z
- **Completed:** 2026-07-24T20:54:28Z
- **Tasks:** 3
- **Files modified:** 3 (1 new + 2 modified)

## Accomplishments

- **`html/gen_timeline_html.py` (MODIFIED, PRESENT-01/02/03 + XSS)** — five additive extensions, zero existing-behavior regressions:
  - `_esc(s)` helper at module top, copied VERBATIM from `html/gen_registry_review.py:79-91` (Phase 7 CR-04 fix commit 336d04f). 5-char HTML escape (`& < > " '`), self-contained inline impl (avoids stdlib `html.escape` namespace-package shadowing by local `html/` dir). Applied to every operator-influenced name/ID interpolation in gallery card HTML.
  - `build_shots_js` extended with `prompts_by_id=None` param. Each shot dict gains `route_filled` (ALL of camera/action/lighting/style non-empty → True; ANY empty → False), `character_refs[]`, `prop_refs[]` — so JS chip rendering needs no separate lookup.
  - `build_html` extended with `characters_data=None, props_data=None`. JSON-in-script defense `.replace("</", "<\\/")` applied to ALL 5 inlined JSON literals (shots + stems + transcript + characters + props). New `chars_json` / `props_json` consts power the JS-side `CHARACTERS` / `PROPS` arrays.
  - JS-side `_esc(s)` function (mirrors Python _esc 1:1) + `buildShotChips(s)` helper that renders ref-chips (in-page `#gallery-<id>` anchors with `encodeURIComponent` + `_esc(name)`) + fill-chip (green `✓ 运镜` when `s.route_filled`, gray `○ 降级` otherwise).
  - Gallery section: server-rendered cards with external PNG thumbnails (`<img src="characters/char_001.png">` served via `scripts/serve.py` Range handler) + `onerror="this.style.display='none'"` fallback (Pitfall 7: apply_edits OMITS representative_image on ffmpeg failure → no broken icon). Gallery OMITTED entirely when both `characters_data` and `props_data` are empty (graceful-degrade).
  - `main()` extended with 4 new CLI flags: `--prompts`, `--characters`, `--props`, `--asset-json`. Data source priority: `asset.json#generator.registry_snapshot` (preferred — export-time truth) → `--characters`/`--props` (fallback) → None (graceful-degrade).
  - Ref-chips + fill-chip appended to BOTH shot-row templates (linear mode + adaptive `rebuildAll`). Existing stem playback / video / caption logic untouched.
- **`run_pipeline.py` (MODIFIED, Pitfall 9 + CONTEXT Q3)** — `step_timeline` wired as Phase 8 contract surface:
  - `step_timeline` signature gains `prompts_json: str = None` kwarg.
  - Invokes `prompts/attach_refs.py` as a pre-step BEFORE the mtime cache check + BEFORE `gen_timeline_html.py` runs. Banner label `"prompt-ref attachment (attach_refs pre-step)"` intentionally omits `[N/M]` prefix to keep `grep -cE '\[[1-8]/8\]'` count at 24 (Pitfall 5 prevented; CONTEXT Q3 lock honored).
  - mtime cache inputs extended to include `prompts_json`: attach_refs rewrites prompts.json → new mtime → cache miss → timeline regenerates with new refs/chips (Pitfall 9 prevented).
  - `gen_timeline_html.py` subprocess now passes `--prompts`, `--characters`, `--props`, `--asset-json` (each gated on file existence) so the HTML reflects attached refs + gallery.
  - `main()` call to `step_timeline` updated with `prompts_json=prompts_json`.
- **`scripts/verify_phase8_smoke.py` (NEW)** — 6-scenario regression harness mirroring `verify_phase7_smoke.py` structure (standalone `sys.exit(0/1)`, no pytest, temp work_dir per scenario, finally rmtree cleanup, bracketed `[phase8-smoke] PASS/FAIL` tags). Covers: (1) attach_no_registry graceful-degrade, (2) attach_idempotent byte-diff, (3) snapshot_freeze Pitfall 18, (4) integrity_dangling_ref Pitfall 17, (5) snapshot_confirmed_only Pitfall 7, (6) html_xss_inert CR-04 carry. All 6 green in ~3s.

## Task Commits

Each task committed atomically:

1. **Task 1: gen_timeline_html.py gallery + chips + indicator + XSS** - `dfc7850` (feat)
2. **Task 2: run_pipeline.py step_timeline attach_refs pre-step + cache** - `669a10f` (feat)
3. **Task 3: verify_phase8_smoke.py 6 scenarios** - `c94eef9` (test)

## Files Created/Modified

- `html/gen_timeline_html.py` (MODIFIED, +207 / -9 lines) — added `_esc()` Python helper; extended `build_shots_js` with `prompts_by_id` + `route_filled`/`character_refs`/`prop_refs`; extended `build_html` with `characters_data`/`props_data` + JSON-in-script defense on 5 inlined JSON literals + gallery section server-rendered HTML; added JS `_esc()` + `buildShotChips()` + `CHARACTERS`/`PROPS` consts; extended both shot-row templates (linear + adaptive) with chips; extended `main()` with 4 new CLI flags + gallery data loading (snapshot-preferred).
- `run_pipeline.py` (MODIFIED, +45 / -3 lines) — `step_timeline` signature gains `prompts_json` kwarg; invokes attach_refs.py pre-step under plain banner label; mtime cache inputs include prompts_json (Pitfall 9); gen_timeline_html subprocess receives --prompts/--characters/--props/--asset-json.
- `scripts/verify_phase8_smoke.py` (NEW, 592 lines) — 6-scenario regression harness.

## Decisions Made

- **attach_refs banner label omits `[N/M]` prefix** (Rule 2 — auto-satisfy competing must_haves). The plan RESEARCH Pattern 6 suggested reusing the `[7/8]` banner prefix (`"[7/8] prompt-ref attachment"`), but the must_haves truth `[N/8] count unchanged from Phase 7 (24 occurrences)` is a hard constraint that the `[7/8]` banner would violate (+1 occurrence). The resolution: plain banner label `"prompt-ref attachment (attach_refs pre-step)"` clearly signals the step context (within step_timeline) without contributing to the step-banner grep count. Both constraints satisfied. Documented in step_timeline docstring.
- **JS-side `_esc()` mirrors Python `_esc()` 1:1** — chips resolve names from `CHARACTERS`/`PROPS` arrays at client-render time (not at server-template time), so the JS string context needs its own escape function. Self-contained (no `String.prototype.escapeHTML` library) for the same reason as the Python side: monolithic self-contained HTML pattern + zero deps. Two-layer XSS defense (server + client) consistent with Phase 7 CR-04.
- **Gallery data source priority: registry_snapshot > characters.json > None** (RESEARCH Open Question 2 resolution). `asset.json#generator.registry_snapshot` is the export-time frozen truth — preferred when present. Falls back to `--characters`/`--props` when the asset hasn't been exported yet (mid-pipeline timeline regen). None → gallery OMITTED entirely (graceful-degrade, HTML still schema-valid + self-contained).
- **Smoke scenario 3 double-assert** — (a) re-read of disk `asset.json` shows snapshot unchanged after registry mutation (the freeze guarantee — Pitfall 18), AND (b) re-call of `build_asset_dict` shows NEW snapshot reflecting the mutation (proves the freeze is structural to the disk artifact, not a Python-level cache of the build function). The two together close the Pitfall 18 reasoning.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Consistency] attach_refs banner label `[N/M]` would have broken the count lock**
- **Found during:** Task 2 verify
- **Issue:** The plan RESEARCH Pattern 6 + Task 2 `<action>` suggested the banner `"[7/8] prompt-ref attachment (attach_refs)"`. But the must_haves truth + acceptance criterion `[N/8] count unchanged from Phase 7 (24 occurrences)` would be violated (+1 → count 25).
- **Fix:** Use plain banner label `"prompt-ref attachment (attach_refs pre-step)"` (no `[N/M]` prefix). Both the CONTEXT Q3 lock (no new numbered step) AND the count lock (24 occurrences) are satisfied. Documented in step_timeline docstring.
- **Files modified:** `run_pipeline.py` (banner label only).
- **Commit:** `669a10f` (Task 2).

**2. [Rule 1 - Bug] Initial `_img_onerror()` helper placement broke `build_html` structure**
- **Found during:** Task 1 implementation
- **Issue:** First edit attempt placed a `def _img_onerror():` helper BETWEEN the `gallery_html = ...` line and the `stat_spans = ...` line, which structurally terminated `build_html` early (the rest of the function body became orphaned).
- **Fix:** Replaced the helper function with a local `_IMG_ONERROR` string constant inside `build_html`. Same behavior (shared onerror attribute string), no module-level helper, no structural issue.
- **Files modified:** `html/gen_timeline_html.py` (refactor only, no behavior change).
- **Commit:** `dfc7850` (Task 1, fixed before commit).

Otherwise: None — plan executed exactly as written.

## Issues Encountered

None beyond the two auto-fixes above. The Phase 7 → Phase 8 XSS defense carry-over was mechanical (verbatim copy from `gen_registry_review.py:79-91`). The pipeline wiring reused the existing `run_step` helper + step_timeline cache pattern. The smoke harness mirrored `verify_phase7_smoke.py` line-by-line in structure.

## User Setup Required

None — pure producer-side HTML extension + pipeline wiring + smoke regression. No external services, no env vars, no CLI configuration beyond the existing pipeline. The gallery reads PNGs via the existing `scripts/serve.py` Range handler (already established for video/stems).

## Manual-Only Verifications (NON-BLOCKING — per 08-VALIDATION.md)

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Gallery UX pilot | Automated check verifies cards/chips presence but not visual readability | Open generated `timeline.html` in browser against the v1.1 fixture set; confirm gallery cards render with thumbnails, chips click-scroll to the correct gallery entry (`#gallery-char_001` anchor + CSS `scroll-behavior:smooth`), indicator colors match operator expectation (green `✓ 运镜` when all four facets filled, gray `○ 降级` otherwise) |
| Operator review of recomposed `prompt_text` readability (Phase 8 plan 02 carry-over) | Deterministic template (Pattern 2) guarantees structure; does NOT guarantee the recomposed prose reads naturally for downstream AI video pipelines | Spot-check 3-5 recomposed `prompt_text` strings in `output/<asset>/prompts.json`; if awkward, adjust the Pattern 2 template prose (Claude's Discretion per CONTEXT Q2) and re-lock |

> These 2 manual items are UX/readability pilots, NOT blockers. Every Phase 8 requirement is testable NOW on the v1.1 fixture set (verified by `scripts/verify_phase8_smoke.py` 6/6 green + `spec/validate.py` + `verify_contract.py --mode=producer`).

## Deferred Items (Phase 9 cross-repo)

- **PRESENT-04/05/06 (canvas consumer gallery/chips)** — Phase 9 cross-repo (kais-aigc-platform `feat/canvas-asset-collection`). The producer-side `generator.registry_snapshot` (Plan 02) + gallery rendering (this plan) are the contract the canvas consumes. The canvas node will read the embedded snapshot + render its own gallery; the producer HTML gallery is operator-facing only.

## Next Phase Readiness

- **Phase 8 complete: producer-side prompt references + snapshot freeze + integrity + gallery all wired end-to-end.** The full v1.1 producer side (contract + registry + prompts + gallery) is shippable.
- **Phase 9 (canvas consumer) unblocked.** The producer emits:
  - `asset.json#generator.registry_snapshot` (frozen confirmed-only compact view)
  - `prompts.json` with `character_refs[]`/`prop_refs[]` + Pattern 2 recomposed `prompt_text`
  - `timeline.html` with operator-facing gallery + chips + indicator
  - Canonical `characters.json`/`props.json` + `characters/*.png`/`props/*.png` media (via serve.py Range)
- **Threat model T-08-10/11/12 (XSS via operator-influenced names) all mitigated** at the HTML layer: Python `_esc()` + JS `_esc()` + JSON-in-script `.replace("</", "<\\/")` on all 5 inlined JSON literals. Smoke scenario 6 asserts payload `"</script><script>alert(1)</script>"` is inert in generated HTML.
- **Pitfall 5 (phantom step-counter bump) prevented** — `grep -cE '\[[1-9]/9\]' run_pipeline.py` returns 0; `grep -cE '\[[1-8]/8\]'` returns 24 (unchanged from Phase 7).
- **Pitfall 9 (cache stale after attach_refs) prevented** — `prompts_json` in step_timeline mtime cache inputs; attach_refs runs BEFORE cache check.
- **No blockers.**

## Self-Check: PASSED

- FOUND: `html/gen_timeline_html.py` (modified)
- FOUND: `run_pipeline.py` (modified)
- FOUND: `scripts/verify_phase8_smoke.py` (created)
- FOUND: `08-03-SUMMARY.md` (this file)
- FOUND: commit `dfc7850` (Task 1, feat)
- FOUND: commit `669a10f` (Task 2, feat)
- FOUND: commit `c94eef9` (Task 3, test)
- FOUND: `python3 scripts/verify_phase8_smoke.py` exits 0 (6/6 scenarios green)
- FOUND: `python3 spec/validate.py` exits 0 (no schema regression)
- FOUND: `python3 scripts/verify_contract.py --mode=producer` exits 0 (no contract regression)
- FOUND: `grep -cE '\[[1-9]/9\]' run_pipeline.py` returns 0 (Pitfall 5 prevented)
- FOUND: `grep -cE '\[[1-8]/8\]' run_pipeline.py` returns 24 (count lock preserved)

---
*Phase: 08-prompt-reference-system-shot-timeline-html-gallery*
*Completed: 2026-07-24*
