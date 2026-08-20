---
phase: 22-dataset-export-integration
reviewed: 2026-08-20T12:53:33Z
depth: standard
review_iteration: 2
review_mode: re-review after fixes (--auto loop iteration 2; fixes 6cc0cde..bc51e50)
fix_range: 4699142..bc51e50
files_reviewed: 4
files_reviewed_list:
  - html/gen_roundtrip_review.py
  - analysis/roundtrip/export_dataset.py
  - analysis/roundtrip/judge.py
  - run_pipeline.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
gates:
  pytest: "234 passed"
  spec_validate: "exit 0"
  ep01_sidecar_sha: 63543baf9da845de930c02f13a1d3a5eb1a6b91a04ee172d9625f7482436dd73
---

# Phase 22: Code Review Report — Re-review (Iteration 2)

**Reviewed:** 2026-08-20T12:53:33Z
**Depth:** standard
**Mode:** Re-review after fixes (`--auto` loop iteration 2)
**Fix range:** `4699142..bc51e50` (CR-01 `6cc0cde`, WR-01 `d4d8b11`, WR-02 `c7bcd6c`, WR-03 `daf8365`, WR-04 `bc51e50`)
**Files Reviewed:** 4 (three in `<files_to_read>` + `judge.py`, which the WR-03 fix touched)
**Status:** clean — all 5 in-scope fixes verified correct; no new Critical or Warning findings

## Summary

Re-reviewed the five iteration-1 fixes adversarially: source-level trace of every changed hunk, runtime verification of the dataset-export edges with synthetic scenarios (not just the repo's own tests), artifact-level verification of the regenerated ep01 review panel, and independent gate runs.

**Gates (run by reviewer, not trusted from fix report):**

- `python3 -m pytest tests/ -q` → **234 passed** (223 baseline + 11 new regression anchors)
- `python3 spec/validate.py` → **exit 0** (minimal/v1.1/v1.2/v1.3/smoke all 0 failures; roundtrip.schema.json untouched — two-tier authority lock held)
- ep01 `roundtrip.json` sha → `63543baf9da845de930c02f13a1d3a5eb1a6b91a04ee172d9625f7482436dd73` — unchanged (runtime sidecar zero-touch held)

**Per-fix verification:**

- **CR-01 (queue span)** — `applyVisualState` now selects `q.querySelector('.queue-check')` and writes only the dedicated placeholder span; the anchor's topline/micro-sim-bar children are never reassigned. Enumerated every DOM writer in the generated ep01 HTML: 7 `textContent` sites (check span, pill, counter, sync buttons ×3, video-well error placeholder — the last replaces only the failed `<video>`, by design), zero `innerHTML`, zero writes on the queue anchor. Initial load (`applyVisualState()` at script end) sets server-rendered empty spans to `''` — a no-op; queue intact. All state paths (accept/reject/keepAuto/toggle-off) route through the same span write. Artifact check: 19/19 queue items with topline + empty `.queue-check` spans, `q.textContent` count 0. Regression anchor `test_queue_checkmark_targets_dedicated_span` is meaningful (selector presence, anchor-write absence, fill-form lock, server span count, anchor-children integrity).
- **WR-01 (exported-only index)** — `accepted.txt` / `manifest["shots"]` / `accepted_count` all derive from the in-loop `exported_names` success set. Runtime-verified three-way consistency (`accepted_count == len(shots) == accepted.txt lines`) under full degrade (0/0/0), partial success (1/1/1), and prompts-missing skip; skipped ids isolated in `manifest["exported_skipped"]`, never in the index.
- **WR-02 (created = not isdir)** — Runtime-verified: prior-round dir survives a degraded rerun byte-identical (first/last_frame.jpg + prompt.json untouched) with an audit warning; this-round half-built dirs are still rmtree'd; prompts-missing prior dirs untouched; stale non-accepted dirs still pruned; non-shot-dir entries (e.g. manifest.json itself) never touched by prune.
- **WR-03 (τ in cache key + double record)** — (a) `judge.apply_verdict` writes the `roundtrip.json.verdict-tau` stamp only when `entries` is non-empty (actual new applies — frozen-only reruns don't stamp) and only when no readable stamp exists; τ-mismatch reruns warn and do not overwrite; stamp write ordered after `_merge_write_sidecar`. (b) `step_roundtrip` cache key is `video-identity|tau=<τ>` on both compare and write; old-format stamps miss once then self-heal; the cache-hit path still regenerates the review HTML; `video-identity` None → miss (safe). Float formatting is round-trip stable (`str(float(...))`). (c) `export_dataset` manifest carries `verdict_tau` (from stamp; absent/corrupt → null + warning) and `export_tau` (CLI τ) with a mismatch warning — runtime-verified against stamp values 0.92/absent. Known accepted residuals (iteration-1 contract): mixed-batch stamp keeps first τ (warned), and the panel pill displays the current review τ rather than `verdict_tau` (mismatch surfaced via judge warning + manifest double-record).
- **WR-04 (engine_version tail + docstring)** — Fold summary is now `▸ Prompt 快照 (prompt v{pv} · {engine_version})` with both parts through `_esc`, degrading gracefully when either/both are absent (no tail / single segment). Docstring's layer-1 XSS list now matches the fields that actually reach the HTML (`engine_name` explicitly documented as not rendered — it goes to dataset prompt.json). Artifact check: 19/19 ep01 summaries carry the engine version.

**No new bugs introduced:** no debug artifacts in the three files; no dead variables (`current_dirs` still drives prune; `skipped_shots` still printed); working tree clean (reviewed content == committed content). Edge cases traced and found non-issues: corrupt stamp silently re-stamped on next real apply (best-effort, prior value unreadable); fully-degraded run writes an empty `accepted.txt` (correct per this-round-truth contract, prior dirs preserved on disk); duplicate `shot_id`s in a hand-edited sidecar could diverge count vs index, but unreachable via the toolchain (READ-merge dedupes by id) and pre-existing.

All reviewed files meet quality standards for this re-review scope. No new issues found. Iteration-1 Info findings (IN-01..IN-08) remain out of scope and open, as agreed.

---

## Archived: Iteration-1 Findings (all in-scope findings fixed and re-verified)

Originally reviewed 2026-08-20T08:59:50Z · depth standard · 9 files · findings 1 critical / 4 warning / 8 info · status issues_found.

### CR-01: Queue sidebar wiped on page load — `textContent` set on the `<a>` instead of the `.queue-check` placeholder span

**File:** `html/gen_roundtrip_review.py:659-660` (render site `:316`, initial call `:746`)
**Issue:** `applyVisualState()` set `q.textContent` on the queue item anchor `<a class="queue-item">`, replacing all children (check span, topline with shot id + sim number, micro sim bar) with a single text node. Invoked once at script load, it blanked every queue item on page load, before any interaction — the τ-sorted review queue lost all content on every generated panel. Source-level tests cannot catch DOM behavior.
**Outcome:** fixed (6cc0cde) — verified in iteration 2 (see Summary).

### WR-01: `accepted.txt` and `manifest["shots"]` listed accepted shots whose directories were never created (or were removed)

**File:** `analysis/roundtrip/export_dataset.py:318, 363-369`
**Issue:** Index artifacts were derived from the full accepted set before the export loop; shots skipped mid-loop (prompts entry missing, frame-source failure) remained listed while their dirs were absent/partial, and `accepted_count` disagreed with `len(manifest["shots"])`.
**Outcome:** fixed (d4d8b11) — verified in iteration 2 (see Summary).

### WR-02: Degraded rerun deleted previously-good dataset shot directories

**File:** `analysis/roundtrip/export_dataset.py:338-346`
**Issue:** `rmtree(shot_dir)` on frame-source failure destroyed the prior run's valid export even when the directory pre-existed the current run.
**Outcome:** fixed (c7bcd6c) — verified in iteration 2 (see Summary).

### WR-03: τ change on a cache-hit rerun displayed a non-governing τ as governing (panel pill/tick/queue-sort + dataset manifest)

**File:** `run_pipeline.py:630-651`, `analysis/roundtrip/export_dataset.py:355-357`
**Issue:** `--tau-sim` was not part of the step_roundtrip cache key; verdicts frozen at τ1 were re-displayed/re-recorded under τ2 with no provenance distinction.
**Outcome:** fixed (daf8365) — τ added to the outer cache-stamp identity; judge stamps decision τ at first real apply; manifest double-records `verdict_tau`/`export_tau`. Verified in iteration 2 (see Summary).

### WR-04: UI-SPEC data-mapping deviation — `regen.engine_version` never rendered; `_esc` docstring overclaimed coverage

**File:** `html/gen_roundtrip_review.py:262-264`, docstring `:20-22`
**Issue:** Only `prompt_version` appeared in the prompt-fold summary; `engine_version` was rendered nowhere despite the UI-SPEC mapping row, and the docstring claimed escaping for fields that never reached the HTML.
**Outcome:** fixed (bc51e50) — verified in iteration 2 (see Summary).

### Info (out of scope for the fix round; open)

- IN-01 apply_edits no-op early-return swallows malformed-entry warnings; `skipped` counter structurally dead — `analysis/roundtrip/apply_edits.py:185-191`
- IN-02 apply_edits `applied` count overstates writes when a target shot is quarantined by merge validation — `analysis/roundtrip/apply_edits.py:183, 217-250`
- IN-03 Bootstrap `</`-only escape leaves a parser-state DoS vector (`<!--` + `<script>` without `-->`) — `html/gen_roundtrip_review.py` bootstrap
- IN-04 `RT_SHOTS` bootstrap JSON is dead weight — only `.length` consumed
- IN-05 Dataset frame-fallback timing sourced from prompts.json while cache frames are keyed from shots.json timing — `analysis/roundtrip/export_dataset.py:174-176`
- IN-06 `accepted.txt` / `rejected.txt` written non-atomically while JSONs use `_atomic_write_json` — `analysis/roundtrip/export_dataset.py:417-422`
- IN-07 No revert-to-auto path once a human verdict is applied — "⟲ 维持 auto" misleading on human-verdict cards
- IN-08 `--force` consistency gap — step_roundtrip takes no `force` parameter; `roundtrip.json.video-stamp` missing from the force-clear list (currently masked)

---

_Re-reviewed: 2026-08-20T12:53:33Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (iteration 2, re-review after fixes)_
