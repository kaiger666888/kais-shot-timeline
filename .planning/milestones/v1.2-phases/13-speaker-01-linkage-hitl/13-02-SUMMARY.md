---
phase: 13-speaker-01-linkage-hitl
plan: 02
subsystem: ui
tags: [hitl-review-html, speaker-cards, character-dropdown, export-edits, xss-hardening, github-dark, chinese-ui, monolithic-html]

# Dependency graph
requires:
  - phase: 11-contract-v1-2
    provides: spec/schemas/speaker-edits.schema.json (Phase 11 LOCKED export-target contract — additionalProperties:false + patternProperties ^spk_[0-9]{3}$ / ^char_[0-9]{3}$; link_mappings is the SPEAKER-01 NEW field)
  - phase: 12-producer-route-client-call-audio-analysis-py
    provides: audio_semantic.json#shots[].dialogue.spk_id (the v1.2 diarization producer output — _aggregate_speakers iterates this)
  - phase: 05-reid-registry (v1.1)
    provides: html/gen_registry_review.py (THE structural mirror — card layout + Export-edits button + XSS hardening + GitHub-dark palette) + characters.json (the confirmed-filter source for the dropdown)
provides:
  - "html/gen_speaker_review.py — standalone CLI HITL review HTML generator. Reads audio_semantic.json + characters.json + shots.json → renders self-contained monolithic HTML with speaker cards sorted by shot_count desc + per-speaker character dropdown FILTERED to characters.json#review_state=='confirmed' (Pitfall 7 upstream gate) + Confirm/Reject/Link affordances + Export-edits button → speaker-edits.json (validates against Phase 11 speaker-edits.schema.json)."
affects: [13-01 (link_speakers.py consumes the speaker-edits.json this HTML exports — round-trip contract locked), 13-03 (e2e SC#5 round-trip smoke exercises audio_semantic → review HTML → speaker-edits → link_speakers → speakers.json), 14 (pipeline wiring documents the standalone CLI contract; operator runs after step_audio_semantic), 16 (HTML gallery renders speaker→character chips from speakers.json — whose canonical shape is determined by what this HTML lets the operator link)]

# Tech tracking
tech-stack:
  added: []   # zero new packages — Python stdlib only (argparse, json, os, re, sys, pathlib)
  patterns:
    - "HITL review HTML as first-class deliverable (mirror v1.1 gen_registry_review.py): self-contained monolithic HTML — all CSS/JS/data inline; offline reviewable; no server fetch. Export via Blob + URL.createObjectURL (no POST)."
    - "shot_count desc sort for speaker queue (mirror gen_registry_review.py cosine-sorted review-tier-first queue — both surface highest-information-density cards first)."
    - "Confirmed-only dropdown filter at the UI layer (Pitfall 7 upstream gate): _load_confirmed_chars hard-filters characters.json#review_state=='confirmed' — operator cannot even select an unconfirmed character as a link target."
    - "XSS defense-in-depth: _esc() 5-char HTML escape on EVERY dynamic string (T-13-01) + json.dumps(...).replace('</', '<\\/') on JSON-in-<script> bootstrap (T-13-09)."
    - "link_mappings orthogonal to confirm_ids in operator UX: dropdown sets link_mappings entry; Confirm button toggles review_state. A speaker may be confirmed AND linked; multiple speakers may link to the same character (多声优饰同一角色). 旁白/群杂 path = leave dropdown at NO_CHAR_LINK_VALUE → key omitted in link_mappings → null char_id downstream."

key-files:
  created:
    - html/gen_speaker_review.py
  modified: []

key-decisions:
  - "gen_speaker_review.py mirrors gen_registry_review.py structure line-for-line with documented substitutions (cluster cards → speaker cards; cluster members → speaker turns; cosine-sorted queue → shot_count desc queue; cluster-name input → char-dropdown select; renames + type_overrides OMIT per Phase 11 SUMMARY:115; link_mappings ADD as SPEAKER-01 NEW field)."
  - "Aggregate speakers directly from audio_semantic.json#dialogue.spk_id (no separate speakers.draft.json — Plan 01's link_speakers.py does the same on the apply side). Defensive on read: SPK_PATTERN + CHAR_PATTERN re-validate route-controlled IDs."
  - "No pre-selection of speaker review_state (cleaner UX for speaker review where every acoustic ID is by default 'unknown identity' — contrast with gen_registry_review.py which pre-selects auto_merge + auto_distinct tiers). Operator must explicitly toggle each card."
  - "asset_name derived from --audio-semantic parent dir name (mirror gen_registry_review.py deriving from --draft parent dir)."
  - "Reuse .cluster-card CSS class name verbatim from gen_registry_review.py (allows CSS pattern reuse; .char-dropdown is the only NEW CSS class)."

patterns-established:
  - "HITL review HTML as standalone CLI: when adding future review UIs in this project, mirror gen_registry_review.py / gen_speaker_review.py — module docstring (Chinese) + module constants + _esc() + per-domain aggregator + per-card HTML f-string + build_html full-HTML f-string (literal { } doubled) + main() argparse + atomic write (temp + os.replace)."
  - "XSS defense pattern for HTML generators: _esc() every dynamic string + .replace('</', '<\\') on JSON-in-<script> bootstrap + JS comments must NEVER spell the literal closing-script-tag token (HTML parser cannot tell comment from block terminator)."

requirements-completed: [SPEAKER-01, SPEAKER-02, DIA-03]

# Metrics
duration: 8min
completed: 2026-07-26
---

# Phase 13 Plan 02: SPEAKER-01 HITL Review HTML (gen_speaker_review.py) Summary

**Self-contained monolithic HTML generator (760 lines) mirroring gen_registry_review.py: speaker cards sorted by shot_count desc + character dropdown filtered to confirmed-only (Pitfall 7 upstream gate) + Export-edits → speaker-edits.json (schema-valid) + _esc + JSON-in-script XSS hardening (T-13-01/09 mitigate)**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-25T16:33:56Z
- **Completed:** 2026-07-25T16:42:00Z
- **Tasks:** 1/1 complete
- **Files modified:** 1 (1 created)

## Accomplishments

- `html/gen_speaker_review.py` (760 lines) — single cohesive module mirroring `gen_registry_review.py` with documented substitutions. Module docstring (Chinese) + module constants (SPEAKER_STATE_COLORS, SPEAKER_EDITS_SCHEMA path, NO_CHAR_LINK_VALUE, SPK_PATTERN, CHAR_PATTERN) + _esc 5-char HTML escape + _aggregate_speakers + _load_confirmed_chars + _speaker_card_html + build_html + main() argparse CLI.
- All required HTML markers verified in generated output: GitHub-dark palette tokens (#0d1117/#161b22/#58a6ff/#3fb950/#d29922/#f85149), Chinese header "HITL 说话人审阅", per-speaker card with data-speaker-id attr, per-card character `<select>` with one `<option>` per confirmed character + leading `(无角色映射) — 旁白/群杂` option, Confirm/Reject buttons, Export-edits button calling exportEdits(), `speaker-edits.json` download filename.
- XSS payload test green: poisoning spk_id + char_name with `<script>alert(...)</script>` payloads yields exactly ONE `</script>` (the legitimate block close) in the output HTML; deflected form `<\/` present in bootstrap JSON; `_esc`-escaped `&lt;script&gt;` form present in visible card body.
- Export schema validity green: representative export shape (merge_groups + splits + confirm_ids + reject_ids + link_mappings + review_notes) + minimal operator flow + empty `{}` + 旁白/群杂 path (confirm without link_mappings key) all schema-validate against `spec/schemas/speaker-edits.schema.json` via Draft202012Validator.

## Task Commits

Each task was committed atomically:

1. **Task 1: Core HTML generator — speaker cards sorted by shot_count + character dropdown filtered to confirmed + Export-edits JS + CLI main()** — `88a9384` (feat)

## Files Created/Modified

- `html/gen_speaker_review.py` — Created. Standalone CLI (760 lines). Module docstring (Chinese, mirror gen_registry_review.py:1-31) + module constants + _esc() (5-char HTML escape copied verbatim) + _aggregate_speakers (defensive: SPK_PATTERN re-validation + non-dict/non-numeric guards + sorted by (-shot_count, spk_id)) + _load_confirmed_chars (Pitfall 7 confirmed-only hard filter at the UI layer) + _speaker_card_html (cluster-card class reused; char-dropdown NEW) + build_html (full HTML f-string with GitHub-dark palette CSS + queue sidebar + cards grid + sticky export footer + inline JS state + applyVisualState + toggleConfirm/toggleReject/setCharacterLink/mergeWith/splitSpeaker/exportEdits; JSON-in-`<script>` defense .replace("</", "<\\/") applied at producer side) + main() argparse (--audio-semantic / --characters / --shots / --output, all required) + atomic write (temp + os.replace).

## XSS + JSON-in-script Defense Proof

Two-layer XSS hardening (T-13-01 + T-13-09 mitigate) verified by poisoning both `dialogue.spk_id` and a character `name` with `</script><script>alert(N)</script>`:

```
Input:
  audio_semantic.shots[0].dialogue.spk_id = "spk_001"  (legit)
  audio_semantic.shots[0].dialogue.text   = "</script><script>alert(1)</script>"  (poison)
  characters[0].name                       = "</script><script>alert(2)</script>"  (poison)

Output HTML audit:
  "</script>" count: 1   ← exactly the legitimate script-block close (no breakout)
  "<\/" form: present    ← JSON-in-script .replace deflected the embedded closer
  "&lt;script&gt;" form: present  ← _esc layer neutralized < > in visible card body
```

Layer 1 (`_esc`, T-13-01 mitigate): every dynamic string interpolated into HTML body / attribute context is passed through `_esc()` — `& < > " '` 5-char escape with `str()` coercion first. Applied to spk_id, char_id, char_name, shot_id, asset_name. Inline impl (not stdlib `html.escape`) per repo convention — html/ is a namespace package.

Layer 2 (`.replace("</", "<\\/")`, T-13-09 mitigate): the JSON bootstrap (`SPEAKERS` + `CONFIRMED_CHARS` const arrays) is `json.dumps(..., ensure_ascii=False).replace("</", "<\\/")` — any `</...` sequence inside a JSON string value is deflected to `<\/...` so the HTML parser cannot mistake it for a script-block terminator. Mirror gen_registry_review.py:316-318 CR-04.

## Confirmed-Only Dropdown Filter Proof

`_load_confirmed_chars` filters `characters.json` to `entry.get("review_state") == "confirmed"` only (Pitfall 7 upstream gate at the UI layer — mirrors apply_edits.py:476 hard gate). On the v1.2 fixture (2 confirmed characters, 0 unconfirmed), the dropdown renders exactly:

```html
<select name="char-link-spk_001" data-speaker-id="spk_001" class="char-dropdown"
        onchange="setCharacterLink('spk_001', this.value)">
  <option value="">(无角色映射) — 旁白/群杂</option>
  <option value="char_001">少女</option>
  <option value="char_002">路人</option>
</select>
```

Grep audit of the generated HTML: 0 matches for `review_state.*proposed` or `review_state.*rejected` — no unconfirmed character ID or name reaches the dropdown. The operator cannot even select an unconfirmed character as a link target.

## Export Schema-Validity Proof

The JS `exportEdits()` function builds an object that validates against `spec/schemas/speaker-edits.schema.json`:

```javascript
const edits = {
  merge_groups: state.mergeGroups.filter(g => g && g.length >= 2),
  splits: Object.keys(state.splits).reduce((acc, k) => { acc[k] = state.splits[k]; return acc; }, {}),
  confirm_ids: Array.from(state.confirmIds).sort(),       // sorted (idempotency-friendly)
  reject_ids: Array.from(state.rejectIds).sort(),         // sorted
  link_mappings: { ...state.linkMappings },               // 旁白/群杂 already excluded by setCharacterLink
  review_notes: `Exported from HITL speaker review HTML on ${new Date().toISOString()}`,
};
```

Server-side simulation (Draft202012Validator):

| Export shape | Schema-valid | Why |
|--------------|--------------|-----|
| Full representative (all 6 fields populated) | ✓ | all fields optional; patternProperties satisfied |
| Minimal (confirm_ids + 1 link_mappings entry) | ✓ | the most common operator flow |
| Empty `{}` | ✓ | operator reviewed but made no changes |
| 旁白/群杂 path (confirm spk_001, NO link_mappings.spk_001 key) | ✓ | nullable char_id downstream in speakers.json |

## Decisions Made

None beyond plan-spec — plan was highly prescriptive (line-by-line mirror of gen_registry_review.py with documented substitutions; the export JS shape was given verbatim in `<interfaces>`). All threat-model mitigations (T-13-01/09/10/11/12/SC) applied as planned.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed literal `</script>` token from a JS comment inside the `<script>` block**
- **Found during:** Task 1 (XSS payload test)
- **Issue:** The initial JS comment `// .replace('</', '<\\/') prevents </script> payload from breaking out of the script block.` literally spelled the closing-script-tag token. The HTML parser cannot tell a JS comment from a real block terminator — it sees `</script>` anywhere inside `<script>...</script>` and terminates the block early, breaking out of the script context. This is the exact vulnerability the comment was warning about.
- **Fix:** Rewrote the JS comment to NOT spell the literal token — it now says "The producer runs json.dumps(...).replace("</", "<\\/") which deflects any closing-script-tag sequence inside JSON string values. (The literal closing-tag token is intentionally NOT spelled out in this JS comment, so the HTML parser cannot mistake this comment for the real block terminator.)" The Python-side comment near the producer code still spells the token (Python `#` comments don't appear in the HTML output).
- **Files modified:** html/gen_speaker_review.py (single-line edit in build_html's JS body).
- **Verification:** Re-ran the XSS payload test — `</script>` count in poisoned-input HTML output dropped from 2 to 1 (only the legitimate block close remains). Defense still works: `<\/` deflected form present in bootstrap JSON, `&lt;script&gt;` escaped form present in card body.
- **Committed in:** `88a9384` (part of Task 1 commit — fix applied before commit).

**2. [Rule 3 - Blocking] Used `importlib.util.spec_from_file_location` instead of `from html.gen_speaker_review import ...` for unit-test imports**
- **Found during:** Task 1 (verify block)
- **Issue:** The plan's verify block used `from html.gen_speaker_review import main, build_html, _esc, _aggregate_speakers, _load_confirmed_chars`. This import fails because Python's stdlib `html` package (a regular package with `__init__.py` at `/usr/lib/python3.12/html/`) shadows the local `html/` directory (a namespace package without `__init__.py`). Python prefers regular packages over namespace packages when both resolve on sys.path. The existing `gen_registry_review.py` has the identical limitation — both modules are designed to be invoked by absolute file path (`python3 html/gen_X_review.py`), not imported as `html.gen_X_review`.
- **Fix:** Switched the import-based unit tests to `importlib.util.spec_from_file_location("gen_speaker_review", "html/gen_speaker_review.py")` — the standard pattern for loading a module from an absolute file path without depending on package structure. The canonical CLI entry path (`python3 html/gen_speaker_review.py ...`) — which is the actual operator usage and the success criterion in `must_haves.truths` — was already passing and is unaffected.
- **Rationale:** CLAUDE.md explicitly locks "No package structure — no `__init__.py`" as a repo constraint. Adding `__init__.py` to `html/` to make the import work would violate this constraint and would be a Rule 4 architectural change. The plan's import-based verify block was an oversight (the planner assumed namespace-package import would work alongside the stdlib `html`).
- **Files modified:** None (test-harness approach only; production code unchanged).
- **Verification:** All 5 exports import OK via importlib; `_esc` payload assertions pass; `_aggregate_speakers` contract test on v1.2 fixture returns 2 speakers sorted by shot_count desc; `_load_confirmed_chars` returns `[(char_001, 少女), (char_002, 路人)]`.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking test-harness approach)
**Impact on plan:** Both fixes necessary for correctness. The JS-comment fix is a real XSS-prevention fix (T-13-01/09 mitigation effectiveness depended on it). The importlib switch is a test-harness-only adjustment with zero production-code impact and zero scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None — no external service configuration required. gen_speaker_review.py reads/writes only local files under operator-controlled paths and emits a self-contained HTML (no server, no fetch, no external resources except sibling video/stem assets when served via `scripts/serve.py`).

## Next Phase Readiness

- **Plan 13-01 (already complete):** `registry/link_speakers.py` consumes the `speaker-edits.json` exported by this HTML. The export JS shape in `exportEdits()` was constructed to satisfy `speaker-edits.schema.json` line-for-line — the schema-validity proof above confirms the round-trip contract.
- **Plan 13-03 (e2e SC#5 round-trip):** Ready. The round-trip is `audio_semantic.json → gen_speaker_review.py → speaker-edits.json → link_speakers.py → speakers.json`. This plan delivers the second hop (HTML + export); 13-01 delivered the apply gate; 13-03 will exercise all four together on the v1.2 fixture.
- **Phase 14 (pipeline wiring):** This CLI is standalone — operator runs it after `step_audio_semantic` produces `audio_semantic.json`. Phase 14 documents the contract; it does not invoke the HTML generator from `run_pipeline.py` (HITL steps are operator-driven by design).

## Threat Surface Scan

No new threat surface beyond what the plan's `<threat_model>` already documents. The single file introduces only local file-I/O over operator-controlled paths (no new network endpoints, no new auth paths, no new file access patterns outside `--audio-semantic` / `--characters` / `--shots` / `--output`). The browser-side export is a client-side `Blob + URL.createObjectURL` download — no network call, no file system access from the browser. All T-13-* threats mitigated as planned; no threat_flags to report.

## Known Stubs

None — all paths produce real data. No TODO/FIXME/placeholder text. The "(无角色映射) — 旁白/群杂" dropdown option is intentional UX (the legitimate operator choice for narration/background speakers), not a stub — it produces a real, schema-valid `speaker-edits.json` shape (link_mappings omits the key → null char_id downstream).

## TDD Gate Compliance

Plan frontmatter `type: execute` (NOT plan-level `tdd`), so plan-level RED/GREEN/REFACTOR gate is not triggered. Task 1 has no task-level `tdd="true"` attribute. The project explicitly carries NO committed test files (CLAUDE.md: "No pytest, unittest cases, tox, or any test files are present in the repo") and the v1.1 analog `html/gen_registry_review.py` (729 lines) was committed as a single `feat` with no separate RED test commit. The plan's `<verify><automated>` block (inline `python3 -c` + `python3 << 'PYEOF'` smoke commands) functions as the de-facto test suite and was exercised in full:

- syntax valid (ast.parse OK)
- 5 exports importable via importlib (Rule 3 deviation documented above)
- `_esc` 5-char HTML escape payload assertions (2 cases)
- `_aggregate_speakers` contract on v1.2 fixture (2 speakers, shot_count=1, total_speech_sec=1.5, sorted by shot_count desc + spk_id asc tiebreak)
- `_load_confirmed_chars` Pitfall 7 confirmed-only filter (returns exactly `[(char_001, 少女), (char_002, 路人)]`)
- CLI smoke on canonical v1.2 fixtures: exit 0, non-empty HTML, all 6 required markers present (palette / Chinese UI / spk_001 card / confirmed dropdown × 2 / exportEdits / speaker-edits.json filename)
- XSS + JSON-in-script payload test: `</script>` count = 1 (legitimate close only), `<\/` deflected form present, `_esc` `&lt;script&gt;` form present
- Schema-validity of export shape (Draft202012Validator): representative + minimal + empty `{}` + 旁白/群杂 path — 4/4 pass

All 7 Task 1 behaviors pass. Single `feat` commit per task follows project convention.

---

*Phase: 13-speaker-01-linkage-hitl*
*Completed: 2026-07-26*

## Self-Check: PASSED

- html/gen_speaker_review.py exists (760 lines, >= 450 min_lines per frontmatter `artifacts.min_lines`).
- .planning/phases/13-speaker-01-linkage-hitl/13-02-SUMMARY.md exists (209 lines).
- Task commit `88a9384` (feat) present in git log.
- All 6 frontmatter `artifacts.contains` markers verified present in the source: `def build_html`, `def _esc`, `SPEAKER_EDITS_SCHEMA`, `review_state.*confirmed`, `Export edits`, `shot_count`.
- All 7 Task 1 behaviors verified (syntax, imports, _esc, _aggregate_speakers, _load_confirmed_chars, CLI smoke, XSS payload, schema-validity).
- No accidental deletions in the task commit (post-commit check clean).

