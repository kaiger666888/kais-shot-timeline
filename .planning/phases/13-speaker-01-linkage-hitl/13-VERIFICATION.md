---
phase: 13-speaker-01-linkage-hitl
verified: 2026-07-26T00:55:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open generated speaker_review.html in a browser; click Confirm + Reject buttons on a card; verify state toggles + summary pills update + mutual exclusivity"
    expected: "Confirm button turns card border green + state badge shows '已确认' + summary pill increments; Reject mutually exclusive; both can be unselected"
    why_human: "JS onclick handlers' runtime behavior in a real DOM cannot be exercised by grep; producer proves the JS is present + syntactically valid + exportEdits shape schema-validates, but click→state mutation requires browser execution"
  - test: "In the browser, select a character from the dropdown on a speaker card, then click 'Export edits (speaker-edits.json)' button"
    expected: "Browser downloads a file named speaker-edits.json whose contents schema-validate against spec/schemas/speaker-edits.schema.json (the operator-decision shape link_speakers.py consumes)"
    why_human: "Blob + URL.createObjectURL + a.click() client-side download flow cannot be triggered from a non-browser context; producer can only verify the JS shape via static simulation (Draft202012Validator on representative export object)"
  - test: "Visual inspection of the generated HTML — GitHub-dark palette (#0d1117/#161b22/#58a6ff/#3fb950/#f85149), Chinese UI strings render correctly, sticky header + queue sidebar + cards grid + sticky export footer layout"
    expected: "Layout matches the gen_registry_review.py mirror; cards in shot_count desc order; dropdown options are confirmed characters only (no unfiltered entries leak through)"
    why_human: "CSS rendering fidelity + font/Chinese-glyph rendering cannot be verified by grep — only structural markers (palette hex codes, class names, Chinese strings present) can be checked programmatically"
---

# Phase 13: SPEAKER-01 Linkage HITL Verification Report

**Phase Goal:** Close the v1.1 SPEAKER-01 deferral via NEW `^spk_[0-9]{3}$` acoustic ID space + HITL review HTML + confirmed-only apply gate (mirror apply_edits.py) + producer registry integrity + e2e round-trip proof.
**Verified:** 2026-07-26T00:55:00Z
**Status:** human_needed (all 5 SCs VERIFIED via automated evidence; 3 browser-UX items deferred to human UAT)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (5 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `html/gen_speaker_review.py` renders HITL HTML with speaker cards sorted by shot_count desc + per-speaker character dropdown filtered to `characters.json#review_state=="confirmed"` + export-edits button → `speaker-edits.json` | ✓ VERIFIED | `html/gen_speaker_review.py` (760 lines, commits `88a9384`): `_aggregate_speakers` sorts by `(-shot_count, spk_id)` (line 188); `_load_confirmed_chars` filters `review_state=='confirmed'` only (line 211); `build_html` emits `<select class="char-dropdown">` with confirmed-only options + leading `(无角色映射)` 旁白/群杂 sentinel (lines 262-265); `exportEdits()` JS serializes `merge_groups/splits/confirm_ids/reject_ids/link_mappings/review_notes` → Blob download `speaker-edits.json` (lines 655-681). Smoke Scenario 1 grep: `data-speaker-id="spk_001"` + `<option value="char_001">少女</option>` present; `review_state.*proposed\|rejected` NOT in HTML (Pitfall 7 upstream gate). Representative export shape schema-validates via Draft202012Validator. |
| 2 | `registry/link_speakers.py` confirmed-only hard gate at build-entry (mirror `apply_edits.py`); idempotent re-apply byte-identical; deterministic `_next_speaker_id` | ✓ VERIFIED | `registry/link_speakers.py` (548 lines, commit `9f31ae9`): line 479 `if cl.get("review_state") != "confirmed": continue` (HARD skip, NOT filter-after-write — mirror apply_edits.py:476-480); line 477 `sorted(clusters.keys())` iteration; line 483 `sorted(turns, key=(shot_id, start_sec))`; line 84-110 `_next_speaker_id` deterministic (max existing N + 1, zero-pad 3); line 139-149 `_atomic_write` (temp + os.replace). Smoke Scenario 2: sha256 `6379c72780ea190db8a7d22dd4b8d38cd2c18d152584cfc65e00c5b22ae023be` byte-identical across 3 runs. Independent test: reject_ids → spk_003 omitted from canonical (HARD gate exercised). |
| 3 | `speakers.json` validates against speakers.schema.json; `char_id` nullable (旁白/群杂 supported); non-null `char_id` resolves to confirmed `characters.json#id` | ✓ VERIFIED | `link_speakers.py` line 501 `_validate(SPEAKERS_SCHEMA, {"speakers": speakers})` pre-write (Draft202012Validator). Frozen fixture + smoke output both Draft202012Validator-validated. `speakers.schema.json` declares `char_id` as `["string","null"]`. Smoke canonical output: spk_001→char_001 (confirmed 少女), spk_002→null (旁白/群杂). Independent dangling-char_id test: `link_mappings spk_001→char_999` → exit non-zero with stderr `dangling (char_id not in confirmed characters.json IDs — Pitfall 17 second-line)`. |
| 4 | Producer registry integrity assert extended additively (gated on file existence — no-op on v1.0/v1.1/route-down assets); catches speakers→characters dangling | ✓ VERIFIED | `scripts/verify_contract.py` lines 741-807 (commit `fd94a03`); git diff confirms purely additive block slotted AFTER characters/props loop, BEFORE prompts check. Line 748 `if speakers_path.is_file():` gates entry (Pitfall 11 byte-identical-absent). Independent no-op test: `_producer_registry_integrity` on v1.0/v1.1 dir without speakers.json returns `[]`. 5 failure modes each surface (malformed spk_id, duplicate, non-confirmed, dangling char_id, unknown turn.shot_id). Phase 8 smoke 6/6 still green (no regression). `python3 scripts/verify_contract.py --mode producer` exits OK. |
| 5 | End-to-end HITL round-trip on fixture: `audio_semantic.json` + `characters.json` → HTML → `speaker-edits.json` → `speakers.json` (confirmed-only); DIA-02 + DIA-03 exercised | ✓ VERIFIED | `bash scripts/verify_phase13_smoke.sh` prints `PHASE13_ROUND_TRIP_PASS` + exit 0 (5/5 scenarios PASS). DIA-02: input `audio_semantic.json#shots[].dialogue.spk_id` (`spk_001`, `spk_002`) consumed end-to-end (Phase 12 WhisperX diarization output). DIA-03: operator `link_mappings` (spk→char) in frozen fixture → resolved `char_id` field in canonical `speakers.json` (spk_001→char_001 少女). Trap cleanup verified; `git diff --quiet -- spec/fixtures/v1.2/` clean (canonical untouched). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `registry/link_speakers.py` | Standalone CLI apply gate (mirror apply_edits.py); confirmed-only hard gate + idempotent + Draft202012Validator pre-apply + char_id resolution; min 380 lines; contains `def link_speakers`, `SPEAKER_EDITS_SCHEMA`, `SPEAKERS_SCHEMA`, `Draft202012Validator`, `review_state != "confirmed"`, `_next_speaker_id`, `link_mappings` | ✓ VERIFIED | 548 lines; all 7 contains-markers present in source; mirrors apply_edits.py:476-480 hard gate at line 479; deterministic `_next_speaker_id` at lines 84-110; `_atomic_write` (temp+os.replace) at lines 139-149; orphan link_mappings rejection at lines 446-458; dangling char_id rejection at lines 459-469 |
| `html/gen_speaker_review.py` | HITL HTML generator; min 450 lines; contains `def build_html`, `def _esc`, `SPEAKER_EDITS_SCHEMA`, `review_state.*confirmed`, `Export edits`, `shot_count` | ✓ VERIFIED | 760 lines; all 6 contains-markers present; `_esc` 5-char HTML escape (lines 88-101); `_aggregate_speakers` sorted by (-shot_count, spk_id) (line 188); `_load_confirmed_chars` filters to review_state=='confirmed' (line 211); `build_html` full HTML f-string (lines 303-689) with GitHub-dark palette + sticky header + queue sidebar + cards grid + export footer + JSON bootstrap `.replace("</","<\\/")` defense (line 343) |
| `scripts/verify_phase13_smoke.sh` | 5-scenario smoke harness; min 130 lines; contains `gen_speaker_review.py`, `link_speakers.py`, `PHASE13_ROUND_TRIP_PASS`, `_producer_registry_integrity`, `SCENARIO`, `exit 1` | ✓ VERIFIED | 332 lines; all 6 contains-markers present; 5 scenarios (happy-path / idempotency / confirmed-only gate / XSS regression / producer integrity); `set -euo pipefail` + trap cleanup; READ-ONLY canonical fixture discipline + `git diff --quiet` tail guard |
| `tests/fixtures/speaker_edits_phase13_smoke.json` | Frozen operator-decision fixture; schema-validates against speaker-edits.schema.json; contains `confirm_ids`, `link_mappings`, `spk_001`, `char_001` | ✓ VERIFIED | 8 lines; all 4 contains-markers present; Draft202012Validator-validated at smoke start (T-13-13 mitigation); frozen shape: confirm spk_001+spk_002, link spk_001→char_001, spk_002 stays 旁白/群杂 |
| `scripts/verify_contract.py` extension | Additive speakers.json block in `_producer_registry_integrity`; existing checks byte-identical | ✓ VERIFIED | +73 lines (lines 741-807); purely additive (git diff `fd94a03` confirms zero changes to existing characters/props/registry/prompts blocks); gated on `speakers_path.is_file()` (Pitfall 11) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `link_speakers.py` | `spec/schemas/speaker-edits.schema.json` | `Draft202012Validator` pre-apply (T-07-02) | ✓ WIRED | line 303 `_validate(SPEAKER_EDITS_SCHEMA, edits)` before any apply logic; lazy-import jsonschema (line 125) |
| `link_speakers.py` | `spec/schemas/speakers.schema.json` | `Draft202012Validator` pre-write | ✓ WIRED | line 501 `_validate(SPEAKERS_SCHEMA, {"speakers": speakers})` before atomic write |
| `link_speakers.py` | `audio_semantic.json#shots[].dialogue.spk_id` | `_load_speaker_draft` aggregates per-speaker turns | ✓ WIRED | lines 152-223; SPK_PATTERN re-validation on route-controlled field (line 202, T-13-03 defense-in-depth) |
| `link_speakers.py` | `characters.json#review_state==confirmed` | `_load_confirmed_char_ids` cross-ref gate | ✓ WIRED | lines 226-271; non-null char_id MUST resolve to confirmed set (line 464) |
| `gen_speaker_review.py` | `audio_semantic.json#dialogue.spk_id` | `_aggregate_speakers` iterates shots | ✓ WIRED | lines 104-189; SPK_PATTERN re-validates (line 137) |
| `gen_speaker_review.py` | `characters.json#review_state==confirmed` | character dropdown filtered to confirmed | ✓ WIRED | `_load_confirmed_chars` (lines 192-219) hard-filters; dropdown builder (lines 262-265) only emits confirmed options |
| `gen_speaker_review.py` | `speaker-edits.json` (client-side Blob) | `exportEdits()` JS handler | ✓ WIRED (producer-side) | JS at lines 655-681; blob + download `'speaker-edits.json'`; representative shape schema-validates via Draft202012Validator. **Browser-side click→download needs human UAT** (see human_verification #2) |
| `scripts/verify_contract.py:_producer_registry_integrity` | `speakers.json` (when present) | additive block: spk_id pattern + uniqueness + confirmed-only + char_id dangling + turn.shot_id ⊆ shots | ✓ WIRED | lines 741-807; reuses `char_confirmed_ids` set built by characters.json loop (lines 730-733) |
| `scripts/verify_phase13_smoke.sh` | `link_speakers.py` + `gen_speaker_review.py` + `_producer_registry_integrity` + frozen fixture | subprocess invocations across 5 scenarios | ✓ WIRED | all 4 key links exercised; `PHASE13_ROUND_TRIP_PASS` printed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `link_speakers.py` canonical output | `speakers` list | `audio_semantic.json#dialogue.spk_id` aggregated via `_load_speaker_draft` | ✓ Yes — 2 spk_ids (spk_001 + spk_002) on canonical fixture, real `total_speech_sec=1.5` each, real turn shot_ids [1, 2] | ✓ FLOWING |
| `gen_speaker_review.py` HTML bootstrap | `SPEAKERS` const | `_aggregate_speakers` output | ✓ Yes — non-empty list with real spk_id + turns + shot_count | ✓ FLOWING |
| `gen_speaker_review.py` dropdown | `confirmed_chars` options | `_load_confirmed_chars` filtered characters.json | ✓ Yes — 2 confirmed chars (char_001 少女, char_002 路人); zero unconfirmed leak | ✓ FLOWING |
| `verify_contract.py` speakers block | `char_confirmed_ids` set | reuses characters.json loop output (Phase 8 pattern) | ✓ Yes — set populated when characters.json confirmed entries exist | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Smoke harness end-to-end | `bash scripts/verify_phase13_smoke.sh` | `PHASE13_ROUND_TRIP_PASS` + exit 0; 5/5 scenarios PASS | ✓ PASS |
| Contract verification (no regression) | `python3 scripts/verify_contract.py --mode producer` | `[producer] OK: ... 0 errors` | ✓ PASS |
| Phase 8 smoke (regression) | `python3 scripts/verify_phase8_smoke.py` | `[phase8-smoke] OK: 6/6 scenarios green` | ✓ PASS |
| Confirmed-only HARD gate (reject_ids) | link_speakers.py with reject_ids=['spk_003'] on augmented 3-speaker audio | canonical = ['spk_001', 'spk_002']; spk_003 absent | ✓ PASS |
| Idempotency (3× byte-identical) | sha256 across 3 re-applies | `6379c727...` identical × 3 | ✓ PASS |
| Orphan link_mappings rejection | link_speakers.py with link_mappings.spk_002 not in confirm_ids | exit 1, stderr mentions `confirm` + `link_mappings` | ✓ PASS |
| Dangling char_id rejection | link_speakers.py with link_mappings spk_001→char_999 | exit 1, stderr mentions `char_999` + `dangling` | ✓ PASS |
| Malformed edits rejection | link_speakers.py with `confirm_ids: 'not_an_array'` | exit 1, stderr: `speaker-edits.schema.json validation failed` | ✓ PASS |
| Additive no-op on v1.0/v1.1 | `_producer_registry_integrity` on dir without speakers.json | `[]` (zero failures) | ✓ PASS |
| `_esc` 5-char HTML escape | `_esc('<script>alert(1)</script>')` | `&lt;script&gt;alert(1)&lt;/script&gt;` | ✓ PASS |
| spk_NNN disjoint from char_NNN | regex check on canonical fixture | disjoint (no spk matches char pattern, no char matches spk pattern) | ✓ PASS |
| CLI happy path round-trip | gen_speaker_review → link_speakers on canonical fixtures | exit 0 both; 2-speaker canonical speakers.json | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| `scripts/verify_phase13_smoke.sh` | `bash scripts/verify_phase13_smoke.sh` | `PHASE13_ROUND_TRIP_PASS`; exit 0; 5/5 scenarios PASS | ✓ PASS |
| `scripts/verify_contract.py --mode producer` | `python3 scripts/verify_contract.py --mode producer` | `[producer] OK: ... 0 errors`; exit 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SPEAKER-01 | 13-01, 13-02 | New `^spk_[0-9]{3}$` acoustic ID space (disjoint from `^char_[0-9]{3}$`); `speakers.json` canonical sidecar; `char_id` nullable (旁白/群杂) | ✓ SATISFIED | SPK_PATTERN + CHAR_PATTERN compiled in both `link_speakers.py:76-77` and `gen_speaker_review.py:80-81`; disjoint check verified; `speakers.schema.json` declares char_id nullable; speakers.json canonical producer delivered |
| SPEAKER-02 | 13-01, 13-02 | HITL review HTML + confirmed-only hard apply gate (mirror `apply_edits.py`, idempotent); reject full-auto mapping (AF-05) | ✓ SATISFIED | `gen_speaker_review.py` (760 lines) + `link_speakers.py` (548 lines) both delivered; hard gate at `link_speakers.py:479`; idempotency proven (Scenario 2); HTML is HITL (no auto-link) |
| SPEAKER-03 | 13-01 | producer registry integrity assert extension for speakers (additive + gated on file existence) | ✓ SATISFIED | `scripts/verify_contract.py:741-807` (+73 lines additive); no-op when speakers.json absent (Pitfall 11 verified) |
| DIA-02 | 13-03 | Speaker diarization (`spk_NNN` from pyannote via WhisperX integrated diarize) | ✓ EXERCISED (consumer side) | Input `audio_semantic.json#shots[].dialogue.spk_id` (Phase 12 producer output of WhisperX diarization) consumed end-to-end by both `link_speakers.py` and `gen_speaker_review.py`. **Note:** the ML diarization itself is Phase 12's deliverable (ROUTE-02); Phase 13 consumes its output. Smoke Scenario 1 exercises the consumer path. |
| DIA-03 | 13-01, 13-02, 13-03 | `speaker_id → character_id` HITL mapping | ✓ SATISFIED | `link_mappings` field in `speaker-edits.schema.json` (Phase 11 lock); runtime cross-field check in `link_speakers.py:444-470` (Pitfall 17); UI dropdown in `gen_speaker_review.py:262-265`; e2e exercised in Smoke Scenario 1 (spk_001→char_001 link resolved in canonical) |

**No orphaned requirements** — REQUIREMENTS.md maps exactly SPEAKER-01/02/03 + DIA-02/03 to Phase 13, matching plan `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/verify_contract.py` | 1344, 1403 | `placeholder` (e2e mode defer) | ℹ️ Info | **PRE-EXISTING** from Phase 4 (verified via `git log -p`); references Plan 04-02 deferred work, unrelated to SPEAKER. NOT introduced by Phase 13 commit `fd94a03`. Not a stub — the e2e mode is intentionally deferred to Phase 14 per ROADMAP. |

**No Phase 13-introduced debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) in any of:** `registry/link_speakers.py`, `html/gen_speaker_review.py`, `scripts/verify_phase13_smoke.sh`, `tests/fixtures/speaker_edits_phase13_smoke.json`. All paths produce real data.

### Human Verification Required

3 items need browser-side human UAT. The producer-side contract (HTML structure, JS export shape, schema-validity) is fully verified programmatically; only the runtime browser interaction remains:

### 1. HITL Button Toggle Behavior

**Test:** Open generated `speaker_review.html` (from `python3 html/gen_speaker_review.py --audio-semantic spec/fixtures/v1.2/audio_semantic.json --characters spec/fixtures/v1.2/characters.json --shots spec/fixtures/v1.2/shots.json --output /tmp/review.html`) in a browser. On a speaker card, click "✓ Confirm" then "✗ Reject"; verify mutual exclusivity + summary pill updates + state badge text changes.
**Expected:** Confirm button adds `.active` class + card border turns green (#3fb950) + state badge shows "已确认" + header summary pill `🟢 N 已确认` increments. Reject mutually exclusive (clicking it removes Confirm). Both can be unselected to return to "待审".
**Why human:** JS onclick handlers' runtime DOM mutation in a real browser cannot be exercised by grep or static analysis. Producer verifies the JS is present + syntactically valid + state mutation logic correct by inspection, but click→DOM update requires browser execution.

### 2. Dropdown → Export Edits Round-Trip

**Test:** In the browser, on spk_001's card, select "少女 (char_001)" from the character `<select>` dropdown; on spk_002's card, leave dropdown at "(无角色映射) — 旁白/群杂"; click both Confirm buttons; click "📥 Export edits (speaker-edits.json)" button.
**Expected:** Browser downloads a file named `speaker-edits.json`. Open it — contents should match the frozen fixture shape: `confirm_ids: ["spk_001","spk_002"]`, `link_mappings: {"spk_001":"char_001"}`, `reject_ids: []`. Running `python3 registry/link_speakers.py --audio-semantic spec/fixtures/v1.2/audio_semantic.json --characters spec/fixtures/v1.2/characters.json --edits <downloaded> --work-dir /tmp --output /tmp/speakers.json` should produce canonical speakers.json schema-valid + spk_001→char_001 + spk_002→null.
**Why human:** `Blob + URL.createObjectURL + a.click()` client-side download flow cannot be triggered from a non-browser context. Producer can only verify the JS shape via static simulation (Draft202012Validator on representative export object — which passes).

### 3. Visual Layout + Chinese Rendering

**Test:** Visual inspection of the rendered HTML in a browser.
**Expected:** GitHub-dark palette (#0d1117 body bg, #161b22 panels, #58a6ff accents, #3fb950 green, #f85149 red); Chinese strings render correctly (HITL 说话人审阅 header, 已确认/已拒绝/待审 badges, 无角色映射 — 旁白/群杂 dropdown option); sticky header + 240px queue sidebar (left) + auto-fill cards grid + sticky export footer layout; cards in shot_count desc order.
**Why human:** CSS rendering fidelity + Chinese glyph rendering cannot be verified by grep — only structural markers (palette hex codes, class names, Chinese string literals present) can be checked programmatically.

### Gaps Summary

**No gaps found.** All 5 ROADMAP success criteria are verified with strong automated evidence:
- All required artifacts exist, are substantive (548 / 760 / 332 lines vs 380 / 450 / 130 minimums), and are fully wired.
- Data flows are real (no hardcoded empty values, no stubs, no orphaned components).
- The bash smoke harness `PHASE13_ROUND_TRIP_PASS` proves the SC#5 end-to-end composition on the canonical v1.2 fixture set.
- Phase 8 smoke 6/6 green confirms the producer integrity extension is non-regressive (Pitfall 11 byte-identical-absent invariant preserved).
- No Phase 13-introduced debt markers; the 2 `placeholder` strings in `verify_contract.py` are pre-existing from Phase 4 (verified via `git log`).
- 5 requirement IDs (SPEAKER-01/02/03, DIA-02/03) all satisfied or exercised end-to-end.

**Status `human_needed`** is set strictly per the verification decision tree: 3 browser-side UX items (button toggle behavior, Blob download round-trip, visual layout/Chinese rendering) cannot be exercised programmatically and require human UAT. The producer-side contract is fully proven — the human items are downstream runtime concerns (operator uses the HTML in a browser), not implementation gaps. Once a human confirms the browser interaction works as expected, the phase can be marked fully `passed`.

---

_Verified: 2026-07-26T00:55:00Z_
_Verifier: Claude (gsd-verifier)_
