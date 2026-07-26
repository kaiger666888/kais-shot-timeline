---
phase: 13-speaker-01-linkage-hitl
reviewed: 2026-07-26T00:00:00Z
depth: quick
files_reviewed: 5
files_reviewed_list:
  - registry/link_speakers.py
  - registry/apply_edits.py
  - html/gen_speaker_review.py
  - html/gen_registry_review.py
  - scripts/verify_contract.py
  - scripts/verify_phase13_smoke.sh
  - tests/fixtures/speaker_edits_phase13_smoke.json
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-07-26
**Depth:** quick
**Files Reviewed:** 5 (Plan 01 link_speakers.py + Plan 02 gen_speaker_review.py + Plan 03 verify_contract extension + smoke harness; v1.1 analogs loaded for mirror-diff baseline)
**Status:** issues_found (0 blockers, 2 warnings, 1 info)

## Summary

`registry/link_speakers.py` (548 lines) and `html/gen_speaker_review.py`
(760 lines) are the second and third siblings of the v1.1 HITL round-trip
family (`registry/apply_edits.py` + `html/gen_registry_review.py`). The
mirror is faithful: identical `_esc` 5-char XSS escape, identical
`_atomic_write` (temp + os.replace), identical confirmed-only HARD GATE
shape (`if review_state != "confirmed": continue` at build-entry, NOT
filter-after), identical idempotency guards (`sorted(clusters.keys())`,
sorted turns, deterministic `_next_speaker_id`).

All four core threat-model invariants verified present and correct:

- **T-13-01 XSS**: `_esc` applied to every dynamic string in HTML body
  (`spk`, `cid`, `cname`, `asset_name`, `shot_id` in turn list); JSON
  bootstrap uses `.replace("</", "<\\/")` on both `speakers_json` AND
  `confirmed_chars_json` (gen_speaker_review.py:343-347). Client-side JS
  uses text-only DOM APIs (textContent, classList, alert/prompt) — no
  `innerHTML` anywhere. The full XSS surface is clean.

- **T-13-02 confirmed-only HARD gate not bypassable**: build-entry gate
  at link_speakers.py:477-481 hard-`continue`s on non-confirmed; output
  `review_state` hardcoded to `"confirmed"` at :494. Schema validation
  at :501 catches any leak as defense-in-depth. Producer-gate extension
  (`_producer_registry_integrity` at verify_contract.py:777-781) is a
  second-line assert that fires on `proposed`/`rejected` in canonical
  speakers.json even if link_speakers has a bug.

- **T-13-03 path traversal**: `SPK_PATTERN = ^spk_[0-9]{3}$` and
  `CHAR_PATTERN = ^char_[0-9]{3}$` enforced at FIVE call sites —
  `_load_speaker_draft` (input aggregation), `_load_confirmed_char_ids`
  (characters filter), `link_mappings` loop (runtime cross-field check
  schema cannot express), `_load_confirmed_chars` in HTML gen, and
  `_producer_registry_integrity`. No file paths are derived from these
  IDs (unlike apply_edits.py which writes `characters/{cid}.png`), so
  path traversal is structurally impossible in link_speakers.

- **T-13-04 idempotency**: `sorted(clusters.keys())` iteration +
  `sorted(children_def, key=label)` for split ID allocation +
  `_next_speaker_id = max_existing_N + 1` + sorted turns at build time
  → byte-identical re-apply confirmed by smoke Scenario 2 (3×sha256 match).

Cross-file correctness invariants confirmed by tracing:
- char_id resolution uses `confirmed_char_ids` set built from
  characters.json BEFORE any apply step; link_mappings check at :464
  fails-loud sys.exit on dangling char_id (Pitfall 17 second-line).
- `_producer_registry_integrity` speakers block (verify_contract.py:749-807)
  is purely additive — gated on `speakers.json` file existence, no-op
  when absent (Pitfall 11 byte-identical-absent for v1.0/v1.1 assets).
- HTML dropdown filtered to confirmed chars at HTML-gen time
  (`_load_confirmed_chars`:211) — operator cannot even SEE unconfirmed
  character as link target in the UI (Pitfall 7 upstream gate).

Findings below are real quality/robustness gaps the 5-scenario smoke
harness does NOT cover (frozen fixture has `splits={}` and
`merge_groups=[]`; no malformed audio_semantic; no hand-edited JSON
with overlapping groups).

## Warnings

### WR-01: Turn sort crashes with TypeError on mixed missing/non-int shot_id

**File:** `registry/link_speakers.py:483-489`
**Issue:** The HARD-GATE turn sort uses an unguarded `t.get("shot_id")`
in its sort key:

```python
sorted_turns = sorted(
    cl.get("turns", []) or [],
    key=lambda t: (
        t.get("shot_id") if isinstance(t, dict) else 0,
        float(t.get("start_sec", 0.0)) if isinstance(t, dict) else 0.0,
    ),
)
```

If `audio_semantic.json` contains any shot with missing/null `shot_id`
alongside shots with int `shot_id` (e.g., a future Phase 12 producer
regression, route-down degradation, or hand-edited file), the comparison
`1 < None` raises `TypeError: '<' not supported between instances of
'NoneType' and 'int'` (verified by repro). This crashes BEFORE the
schema validation at :501 would have caught it cleanly.

The mirror in `gen_speaker_review.py:_aggregate_speakers:175-178`
handles exactly this case with a `(1 << 30)` fallback for non-int
shot_ids. The two siblings diverge: HTML path is robust, canonical
path is not.

The docstring at `link_speakers.py:169` claims "CR-02 mirror —
apply_edits.py:316-321 degraded-skip not crash" pattern, but this sort
site does not honor it. The result is an ugly traceback rather than
the documented fail-loud-with-clean-message behavior.

Confirmed via repro:
```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
```

**Fix:** Mirror gen_speaker_review.py's defensive coercion:
```python
sorted_turns = sorted(
    cl.get("turns", []) or [],
    key=lambda t: (
        t.get("shot_id") if isinstance(t, dict) and isinstance(t.get("shot_id"), int) else (1 << 30),
        float(t.get("start_sec", 0.0)) if isinstance(t, dict) else 0.0,
    ),
)
```
(Or pre-filter `turns` to drop non-dict / non-int-shot_id entries before
sort, recording a warning. Either keeps the schema-validation gate at
:501 as the clean fail-loud boundary.)

### WR-02: Overlapping `merge_groups` in hand-edited JSON produce split canonical entities

**File:** `registry/link_speakers.py:328-357`
**Issue:** The merge phase iterates `merge_groups` entries independently
without checking whether a `canonical_id` from a later group was
already merged away as a non-canonical member of an earlier group.
Result: a placeholder canonical is recreated with only the later
group's turns, while the earlier canonical retains the earlier turns.

Confirmed via repro with `merge_groups=[[spk_001, spk_002], [spk_002, spk_003]]`:

```
Final clusters:
  spk_001: turns=['T1', 'T2'] total=3.0    <- operator wanted T1+T2+T3 here
  spk_002: turns=['T3'] total=3.0           <- placeholder, reborn!
merge_map: {'spk_002': 'spk_001', 'spk_003': 'spk_002'}
```

Operator intent (transitive): ONE canonical entity with T1+T2+T3.
Actual result: TWO confirmed speakers leak to canonical. Compounding
the issue, `merge_map[spk_003]` points to the placeholder `spk_002`
(not the transitively-resolved `spk_001`), so confirm/reject forwarding
for `spk_003` lands on the wrong target.

Reachability:
- **HTML path SAFE**: `gen_speaker_review.py:595-604` `mergeWith()` does
  `state.mergeGroups.find(g => g.includes(sid) || g.includes(target))`
  and unions into the existing group, so the HTML export cannot emit
  overlapping groups.
- **Hand-edited JSON UNSAFE**: `speaker-edits.schema.json:11-19` places
  NO cross-group uniqueness constraint on `merge_groups` items —
  schema-validates the overlapping input, then link_speakers produces
  the surprising split. The v1.1 mirror `apply_edits.py:332-353` has
  the same pattern (inherited defect).

**Fix:** Either (a) detect overlap pre-apply and fail loud:
```python
# After reading merge_groups, before applying:
seen = set()
for group in edits.get("merge_groups", []) or []:
    for sid in group:
        if sid in seen:
            sys.exit(
                f"[link-speakers] FAIL: spk_id {sid} appears in multiple "
                f"merge_groups (use ONE group per equivalence class; "
                f"the HTML UI does this automatically)"
            )
        seen.add(sid)
```
Or (b) union overlapping groups in pre-processing before applying.
Option (a) is simpler and matches the fail-loud philosophy already used
for malformed splits (incomplete partition, overlap, out-of-range).

## Info

### IN-01: Smoke harness skips splits AND merge_groups entirely

**File:** `tests/fixtures/speaker_edits_phase13_smoke.json`, `scripts/verify_phase13_smoke.sh:129-216`
**Issue:** The frozen fixture is `{"merge_groups": [], "splits": {}, ...}` —
both complex code paths are completely unexercised by the 5 scenarios.
Specifically untested:

- `splits` partition validation (`link_speakers.py:363-419`): the
  complete-partition fail-loud checks (out-of-range, overlap,
  incomplete) and the deterministic ID allocation
  (`_next_speaker_id` + sorted-by-label binding) have NO coverage.
  These are the most logic-dense branches in the file.
- `merge_groups` apply path (`:328-357`): turn/total accumulation,
  canonical placeholder creation, `merge_map` forwarding for
  confirm_ids/reject_ids (CR-05 mirror).
- Cross-step interactions: split-then-confirm child IDs,
  merge-then-link canonical, reject-after-merge forwarding.

The Phase 12 sibling smoke has the same gap (single-shot, happy-path
only). Phase 7 (`run_registry_review_smoke.sh`) is the one prior harness
that DOES exercise splits + merges in its fixture — that pattern should
be mirrored here.

**Fix:** Add Scenario 6 (or extend the frozen fixture) with at least:
- one `splits` entry exercising partition + new ID allocation,
- one `merge_groups` entry exercising canonical/merge_map forwarding,
- assert resulting canonical `speakers.json` has the expected
  `spk_id` set + `turns` partition + `total_speech_sec` sums.

---

_Reviewed: 2026-07-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
