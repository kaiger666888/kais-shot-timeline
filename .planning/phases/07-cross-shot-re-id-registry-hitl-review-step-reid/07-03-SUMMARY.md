---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
plan: 03
subsystem: ui
tags: [hitl, registry, html, ffmpeg, jsonschema, idempotent, confirmed-only, cast-06, cast-07, cast-08]

# Dependency graph
requires:
  - phase: 05-contract-v1.1
    provides: registry.schema.json + characters.schema.json + props.schema.json + v1.1 fixture set (the frozen target shapes this plan's tools produce/consume)
  - phase: 07-cross-shot-re-id-registry-hitl-review-step-reid (plan 01)
    provides: registry-edits.schema.json + spec/fixtures/v1.1/registry.edits.json (the edits round-trip contract that apply_edits consumes + gen_registry_review exports)
provides:
  - registry/apply_edits.py — draft+edits → canonical confirmed-only characters.json/props.json (idempotent, deterministic, schema-validated, ffmpeg representative PNG)
  - html/gen_registry_review.py — first-class HITL review HTML (cluster cards + cosine-sorted queue + three-tier viz + Export edits button)
affects: [07-04 (step_reid auto-invokes gen_registry_review; verify_phase7_smoke.py exercises apply_edits), phase-08-prompt-reference (consumes canonical characters.json/props.json)]

# Tech tracking
tech-stack:
  added: []  # zero new deps — jsonschema 4.26.0 v1.0 baseline; ffmpeg 6.1.1 env; httpx NOT needed (HTML export is client-side Blob)
  patterns:
    - "Confirmed-only HARD GATE at build-entry time (NOT filter-after-write): `if review_state != 'confirmed': continue` — Pitfall 7 enforcement at the assertion layer"
    - "Fixed-order apply (merge → split → rename → type_override → confirm/reject) + deterministic _next_id (max_existing_N + 1) → byte-identical re-apply (Pitfall 5 idempotency)"
    - "Schema-validated operator input: apply_edits validates registry-edits.json against registry-edits.schema.json BEFORE applying (T-07-02 mitigation — never trust unvalidated operator input)"
    - "ffmpeg representative PNG via arg-list subprocess (no shell mode; T-07-13) + timeout=10s (T-07-16 DoS); failure → OMIT schema-optional representative_image (WARNING-2 fix)"
    - "Monolithic self-contained HITL HTML pattern: CSS/JS/data inlined, base64 thumbnails (Pitfall 2 prevention — canonical PNGs don't exist yet because apply_edits runs AFTER review)"
    - "Cosine-sorted review queue: mid-band (0.6-0.85 review tier) surfaces first (hardest decisions first; CONTEXT Q1 lock)"
    - "Client-side export: Blob + URL.createObjectURL + a.download → registry.edits.json (no server; offline review; review is a manual step)"

key-files:
  created:
    - registry/apply_edits.py
    - html/gen_registry_review.py
  modified: []

key-decisions:
  - "Confirmed-only HARD GATE enforced at build-entry time (Pitfall 7): the gate is an `if review_state != 'confirmed': continue` skip at canonical-construction time, NOT a post-write filter. Any intermediate-state bug cannot leak proposed/rejected downstream."
  - "representative_image OMITTED on ffmpeg failure (WARNING-2 fix authoritative): the field is schema-optional (not in characters.schema.json/props.schema.json `required`), so omitting keeps the canonical entry schema-valid; the PNG file is also not written, so export_asset.py's glob naturally skips → no dangling path reaches the pre-write assert."
  - "Pre-select auto_merge + auto_distinct tiers as confirmed in the HITL HTML (Claude's Discretion lock per RESEARCH Q2); review tier (0.6-0.85) left UNSELECTED — must be human-decided."
  - "Cosine-sorted queue surfaces review-tier first (priority 0), then auto_merge (1), then auto_distinct (2). Within tier, lower mean_cosine first (closer to boundary = harder decision)."
  - "Stand-alone CLI (apply_edits.py): NOT invoked by run_pipeline.py — operator runs it manually after reviewing the HTML (CONTEXT Q2 non-blocking lock; pipeline never waits on a human)."

patterns-established:
  - "HITL edits round-trip implementation pattern: schema-first freeze (Plan 01) → tools build against frozen target (Plan 03) — mirrors Phase 5/6 contract-first sequencing"
  - "Deterministic split-ID allocation (_next_id = max_existing_N + 1, zero-padded 3-digit) — Pitfall 5 idempotency guard, future-proof against dict-ordering changes"
  - "Best-member selection ranking (QUALITY_RANK = high:0 > medium:1 > low:2 > unusable:3) — CAST-08 producer-side fallback when route's SAM3 crops absent"
  - "Three reused GitHub-dark palette tokens across all HTML generators (#0d1117 body / #161b22 panel / #30363d border / #58a6ff accent / #3fb950 green / #d29922 yellow / #8b949e grey) — visual consistency"

requirements-completed: [CAST-06, CAST-07, CAST-08]

# Metrics
duration: 18min
completed: 2026-07-25
---

# Phase 7 Plan 03: HITL Review Tooling (apply_edits.py + gen_registry_review.py) Summary

**Confirmed-only canonical registry producer (`apply_edits.py` with fixed-order deterministic apply + ffmpeg representative PNG) plus first-class HITL review HTML (`gen_registry_review.py` with cosine-sorted queue + three-tier viz + client-side edits export) — closes CAST-06/07/08 producer-side**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-25T (approx)
- **Completed:** 2026-07-25T
- **Tasks:** 2
- **Files modified:** 2 (both new)

## Accomplishments
- Shipped `registry/apply_edits.py` — the human-decision surface that turns a draft + edits into canonical `characters.json` + `props.json` containing ONLY `review_state:"confirmed"` entries (Pitfall 7 hard gate at build-entry time, not filter-after-write). Same draft+edits applied twice produces byte-identical output (Pitfall 5 idempotency verified inline). Validates edits against `registry-edits.schema.json` pre-apply (T-07-02) and canonical output against `characters/props.schema.json` pre-write (fails loud).
- Shipped `html/gen_registry_review.py` — a FIRST-CLASS HITL review deliverable (CAST-06 explicit: "一等交付物，非附属脚本"). Self-contained monolithic HTML (CSS/JS/data inlined — mirrors `gen_timeline_html.py`); base64-inlined representative thumbnails extracted via ffmpeg at HTML-gen time (Pitfall 2 prevention); cosine-sorted review queue surfaces mid-band decisions first; three-tier threshold viz (green/yellow/grey); "Export edits" button serializes `registry.edits.json` client-side via Blob+download (no server — review is offline).
- Verified all 10 inline assertions for each task green (idempotency, hard gate, appearance_shots derivation, schema validation, self-contained HTML, palette reuse, cosine-sorted queue, Export button, etc.). No regression in `spec/validate.py` (10 v1.1 shapes green) or `scripts/verify_contract.py` (producer mode green).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create registry/apply_edits.py (confirmed-only gate + idempotent apply + ffmpeg PNG)** - `2337df9` (feat)
2. **Task 2: Create html/gen_registry_review.py (HITL review HTML)** - `2f22ea0` (feat)

## Files Created/Modified
- `registry/apply_edits.py` - Standalone CLI (474 lines): `apply_edits()` core function with fixed-order merge→split→rename→type_override→confirm/reject apply; `_resolve_frame_ts()` (frame_pos → seconds); `_next_id()` (deterministic split ID allocation, Pitfall 5 guard); `_build_char_entry()`/`_build_prop_entry()` (hard-coded review_state="confirmed"); `_extract_representative_png()` (ffmpeg via arg-list subprocess, OMIT on failure per WARNING-2 fix); `_validate()` (Draft202012Validator fails-loud); `_atomic_write()` (temp + os.replace); `main()` (standalone CLI, NOT in run_pipeline per CONTEXT Q2).
- `html/gen_registry_review.py` - Standalone CLI (650 lines): `build_html()` returns the complete monolithic HTML string; `_extract_frame_b64()` (ffmpeg → base64 data URI); `_resolve_frame_ts()` + `_best_member_ts()` (best-member selection via QUALITY_RANK); `_cluster_card_html()` (per-cluster f-string template); `_tier_sort_key()` (cosine-sorted queue); `main()` (atomic HTML write). Inline JS implements toggleConfirm/toggleReject/toggleType/mergeWith/splitCluster/exportEdits — export uses `Blob` + `URL.createObjectURL` + `a.download`.

## Decisions Made
- **HARD GATE location:** At canonical-construction time (`if cl.get("review_state") != "confirmed": continue`) — this is the assertion-layer gate that Pitfall 7 demands. Filter-after-write would be vulnerable to any intermediate-state bug. Verified by inline test: a draft cluster marked `proposed` (char_099, not in confirm_ids) never reaches characters.json.
- **`_next_id` algorithm:** Extract numeric suffixes from existing IDs with the same prefix, take max, +1, zero-pad to 3 digits. `max_n = 0` default (empty set → `_001`). This is deterministic + idempotent (Pitfall 5 guard) and future-proof against dict-ordering changes across Python versions. Inline test: `_next_id('char', {'char_001', 'char_003'}) == 'char_004'`.
- **Default name localization:** `_default_name` returns "角色 NNN" / "道具 NNN" (Chinese) — matches CLAUDE.md comment language convention. Operator can rename via the HITL HTML's editable name input.
- **Pre-select confirm for auto_merge + auto_distinct tiers (RESEARCH Q2 Claude's Discretion):** High-confidence tiers (≥0.85 or <0.6) are pre-selected as confirmed in the HITL HTML JS bootstrap; review tier (0.6-0.85) is left unselected — must be human-decided. This reduces reviewer burden without compromising the gate (operator can still toggle off).
- **Cosine-sort key:** `(priority, mean_cosine)` where priority 0=review/1=auto_merge/2=auto_distinct; within tier, lower mean_cosine first (closer to boundary = harder decision). Verified: with the fixture (char_001 auto_merge 0.92, char_002 review 0.72, prop_001 auto_distinct 0.45), char_002 surfaces as the first cluster card.
- **`gen_registry_review.py` standalone CLI:** run_pipeline.py (Plan 04) will auto-invoke this script after step_reid produces the draft — same pattern as step_timeline. The HTML is regenerated every step_reid run (cheap; thumbnails cached by ffmpeg -y overwrite).

## Deviations from Plan

### Plan-Internal Inconsistency (representative_image assertion vs WARNING-2 fix)

**1. [Rule 3 - Blocking] Plan verify block expects `representative_image` always set, but action text (WARNING-2 fix) says OMIT on ffmpeg failure**
- **Found during:** Task 1 (verification)
- **Issue:** The Task 1 `<verify>` block uses `video = os.path.abspath('run_pipeline.py')` (a Python text file — `__file__` is undefined in `python3 -c` mode, hence the substitution). ffmpeg on a non-video file returns rc=183 (`Error opening input: Invalid data found when processing input`). Per the plan's action text (step 3, WARNING-2 fix explicitly called out in `critical_context`): on ffmpeg failure (nonzero rc / missing / zero-byte output) `entry.pop("representative_image", None)` — the field is schema-optional so the canonical entry stays valid. The verify block assertions `assert char1['representative_image'] == 'characters/char_001.png'` directly contradict this — they expect the field to always be present.
- **Fix:** Followed the action text (more recent revision; WARNING-2 fix is explicitly the authoritative source per `critical_context`). Implementation correctly OMITS `representative_image` when ffmpeg fails. The verify block was run with the representative_image assertions adjusted to assert the OMIT behavior (`assert 'representative_image' not in char1`); all OTHER assertions (idempotency, hard gate, appearance_shots derivation, names from edits fixture, schema validity, malformed-edits rejection) pass unmodified.
- **Files modified:** None (no code change — implementation correctly follows action text).
- **Verification:**
  - Inline test confirmed `char1.keys() == ['id', 'name', 'appearance_shots', 'review_state']` (representative_image omitted) on `run_pipeline.py` input.
  - With a REAL video file, ffmpeg succeeds and `representative_image` IS set to the canonical path (verified locally with the ffmpeg arg-list subprocess pattern).
  - `characters.schema.json` `required` is `["id", "name", "review_state"]` — `representative_image` is correctly optional. The schema-validity gate (`_validate(CHARACTERS_SCHEMA, chars)` pre-write) passes both with and without the field.
- **Committed in:** `2337df9` (Task 1 commit) — implementation is correct; deviation is purely a verify-block-vs-action-text documentation inconsistency in the plan.

---

**Total deviations:** 1 plan-internal inconsistency (documentation only; no functional impact; implementation is correct per the authoritative WARNING-2 fix).

**Impact on plan:** None — implementation strictly follows the action text. The WARNING-2 fix is the explicit authoritative source per `critical_context` ("On ffmpeg FAILURE: OMIT representative_image from the entry (schema-optional — not in required) AND don't write the PNG"). The verify block has stale assertions from before the WARNING-2 revision; this mirrors the Plan 07-01 documentation inconsistency pattern (where a verify-block grep proxy conflicted with the action-text instruction).

## Issues Encountered
None during implementation. ffmpeg behavior on `run_pipeline.py` (rc=183, "Invalid data found") was confirmed upfront via direct test — this informed the representative_image deviation analysis above. The arg-list subprocess form (no shell mode) was already proven via `gen_shots_preview.py:24-39` precedent.

## User Setup Required
None - no external service configuration required. This plan adds zero new dependencies (jsonschema 4.26.0 is v1.0 baseline; ffmpeg 6.1.1 is in env and already documented in CLAUDE.md; no httpx needed because HTML export is client-side Blob). The two CLIs are standalone — operator runs `apply_edits.py` manually after reviewing the HTML (CONTEXT Q2 non-blocking lock).

## Next Phase Readiness
- **CAST-06 (HITL HTML first-class deliverable) CLOSED.** `gen_registry_review.py` produces a genuinely usable review interface: visual cluster cards with thumbnails, cosine-sorted queue, three-tier viz, schema-valid edits export.
- **CAST-07 (apply confirmed-only canonical) CLOSED.** `apply_edits.py` hard-gates proposed/rejected at build-entry time; idempotent + deterministic; schema-validated pre-apply + pre-write.
- **CAST-08 (producer-side ffmpeg representative PNG fallback) CLOSED** (producer-side half; route-side best-of-N crop selection DEFERRED per plan). When the route ships SAM3 foreground-masked crops, they will supersede the producer-side ffmpeg extraction (route crops are cleaner) — no schema change needed (representative_image path is the same shape).
- **Plan 07-04 unblocked.** run_pipeline.py step_reid will auto-invoke gen_registry_review.py after producing the draft; verify_phase7_smoke.py scenario 4 exercises apply_edits idempotency; scripts/export_asset.py adds conditional characters/props emission (CONTRACT-06 closure); scripts/verify_contract.py adds registry↔shots integrity asserts.
- **Phase 8 unblocked.** `prompts.json#character_refs[]`/`prop_refs[]` can attach to confirmed registry IDs via `appearance_shots[]` — the canonical substrate is now produced deterministically.

---
*Phase: 07-cross-shot-re-id-registry-hitl-review-step-reid*
*Completed: 2026-07-25*

## Self-Check: PASSED

- Files: `registry/apply_edits.py` FOUND, `html/gen_registry_review.py` FOUND, `07-03-SUMMARY.md` FOUND
- Commits: `2337df9` FOUND, `2f22ea0` FOUND
- Inline Task 1 verify block green (idempotency + hard gate + appearance_shots + schema validation + malformed-edits rejection + merge_groups + reject_ids + empty-edits)
- Inline Task 2 verify block green (self-contained HTML + Export button + cluster cards + three-tier viz + palette reuse + Blob export JS)
- `python3 spec/validate.py` exits 0 (10 v1.1 + 6 minimal green; 2 pre-existing smoke failures unrelated)
- `python3 scripts/verify_contract.py --mode=producer` exits 0 (no regression)
