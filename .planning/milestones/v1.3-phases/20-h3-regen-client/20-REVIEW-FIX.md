---
phase: 20-h3-regen-client
fixed_at: 2026-08-19T21:17:48Z
review_path: .planning/phases/20-h3-regen-client/20-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 20: Code Review Fix Report

**Fixed at:** 2026-08-19T21:17:48Z
**Source review:** .planning/phases/20-h3-regen-client/20-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 7
- Fixed: 7
- Skipped: 0
- Info findings (IN-01..IN-08): out of scope per fix_scope, not attempted

**Verification:**
- `python3 -m pytest tests/ -q` → **119 passed** (103 baseline zero-regression + 16 new regression tests)
- `python3 spec/validate.py` → exit 0 (`[validate] OK`, failures=0 across all fixtures)

## Fixed Issues

### CR-01: Non-atomic mp4 download + stale cache meta ⇒ truncated video accepted as cache hit

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** 8a42230
**Applied fix:** `_view_download` streams into `dest + ".part"` and `os.replace`s into the final path only after a complete read; mid-transfer failure unlinks the `.part` and re-raises (a partial file can never occupy the final path). `cache_is_hit` additionally verifies the stored `mp4_sha256` on hit — backward-compatible: metas without the field degrade to size-only. Regression anchors: `test_view_download_atomic_on_mid_transfer_failure`, `test_view_download_success_leaves_no_part`, `test_truncated_mp4_rejected_as_cache_hit` (the exact three-run stale-meta/partial-file sequence).

### CR-02: `--force` destroys cache/artifacts/sidecar before the ComfyUI reachability gate

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** 0e9f85a
**Applied fix:** `--force` block moved to immediately after the `system_stats` gate; engine-down degrade now exits with cache, `roundtrip/`, and `roundtrip.json` byte-identical. Adaptation: the sampling/`--max-shot-sec` filter (which writes `skipped.json` under the rmtree'd dir) moved after the force clear so a forced run rewrites the skipped list for the new round. Module docstring step order updated. Regression anchor: `test_force_with_engine_down_preserves_everything`.

### WR-01: `--force` deletes `roundtrip.json` wholesale, violating the "rejected 永不删除" sidecar invariant

**Files modified:** `analysis/roundtrip/h3_regen.py`, `run_pipeline.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** 787d316
**Applied fix:** New `strip_sidecar_regen_half()` replaces the client's `unlink(roundtrip.json)`: per shot only `regen`/`status` keys are stripped; `scores`/`verdict` (incl. rejected) survive for the batch-end READ-merge to rehydrate; entries left with only `shot_id` are dropped; the file is removed only when no human data remains. `--force` help text updated. `run_pipeline.py` `--force` list tightened in sync — `roundtrip/` + `roundtrip.json` removed from the clear list (pipeline cannot regenerate roundtrip data; h3_regen is not a pipeline step); `route_cache/` rmtree still covers the h3_regen cache. Regression anchors: `test_force_preserves_verdicts_in_sidecar`, `test_force_strip_removes_file_when_no_human_data`.

### WR-02: 4-tuple cache key is blind to shot boundaries — re-segmentation reuses stale renders

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** 6ca15cb
**Applied fix:** `cache_is_hit` gained `expected_length`; `main` computes `h3_frame_count(shot["duration"])` before the cache probe (moved out of the render `try`), and a stored-vs-current length mismatch is a miss → re-render. 4-tuple key shape unchanged. Regression anchor: `test_resegmentation_same_prompt_invalidates` (boundary 2.0s→5.5s with unchanged prompt_text re-renders at length 141; sibling shot still hits).

### WR-03: No concurrency guard on cache/sidecar/warnings read-merge-write; fixed `.tmp` name

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** 6726120
**Applied fix:** `_atomic_write_json` tmp is PID-stamped (`{path}.tmp.{pid}`). New `acquire_batch_lock`/`release_batch_lock`: stdlib `fcntl.flock(LOCK_EX|LOCK_NB)` on `route_cache/h3_regen.lock` — deliberately outside the `--force` rmtree list so lock identity survives a force clear; flock auto-releases on process death (no stale locks). Acquired after the reachability gate and before the `--force` clear, so a contending second instance degrades exit-0 with a `[roundtrip]` str warning (str form stays off the 3-code closed enum) before any destructive action or TTS kill. Post-lock `main()` body wrapped in `try/finally` to always release. Regression anchors: `test_atomic_write_tmp_pid_stamped`, `test_batch_lock_second_instance_degrades`, `test_batch_lock_released_after_run`.

### WR-04: Sidecar write validates the *merged* payload — invalid pre-existing entries abort the write after the whole batch

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** be43006
**Applied fix:** `write_roundtrip_sidecar` now returns `list[str]` and validates in two layers: ① this batch's `entries` in isolation → `sys.exit` on error (fail-loud, unchanged); ② merged payload → offending entries attributed to `shot_id`s via error `absolute_path`, per-shot str warning, pre-existing file backed up to `roundtrip.json.bak-<ts>` (human data recoverable), entries dropped, re-validated, rest written — no retry deadlock. Unattributable top-level errors still fail loud. `main()` extends `pending_warnings` with the returned warnings before the flush (writing them directly would be eaten by the strip-previous-round semantics). Regression anchors: `test_sidecar_preexisting_bad_entry_skipped_not_deadlocked`, `test_sidecar_bad_preexisting_entry_e2e_warning_flush`; existing `test_sidecar_refuses_invalid_path` pins layer ①.

### WR-05: ffmpeg frame extraction and curl upload results unchecked — silent stale-frame upload possible

**Files modified:** `analysis/roundtrip/h3_regen.py`, `tests/test_h3_regen.py`, `.planning/phases/20-h3-regen-client/20-REVIEW.md`
**Commit:** fdf3ba9
**Applied fix:** `extract_endpoint_frames` unlinks `dest` before each ffmpeg run (stale bytes cannot survive a failed extraction) and raises `RuntimeError` with rc/dest/stderr on rc≠0, missing, or empty dest. `upload_image` raises on curl rc≠0 (stderr in detail), non-JSON stdout (snippet in detail), and JSON without `name` (server error body surfaced instead of `KeyError`). New `_stderr_snip` helper tolerates bytes/str/absent stderr. Raise paths land in the per-shot handler → `failed_detail` → sidecar `status.error` + failed-summary warning. Regression anchors: `test_ffmpeg_failure_no_stale_frame_survives`, `test_ffmpeg_empty_dest_fails`, `test_upload_failures_fail_loud`, `test_ffmpeg_failure_e2e_shot_failed_with_detail`.

## Skipped Issues

None — all 7 in-scope findings fixed.

## Notes

- **Smoke evidence validity:** the pre-fix smoke evidence (2 rendered mp4s + cache-hit rerun) remains valid for the fixed code — the seven fixes change download atomicity, cache-hit predicates, `--force` semantics, concurrency guarding, sidecar validation layering, and subprocess error propagation; none touch the render path (workflow injection, seed/length determinism, prompt submission, history polling) or the bytes a successful run produces. A successful full download is byte-identical before/after (`.part` → `os.replace`), and a successful cache hit now additionally re-verifies the sha it already stored.
- Per the fix contract, each finding's outcome is also annotated inline in `20-REVIEW.md` ("**Outcome (fix):** …" lines), committed together with that finding's atomic commit.
- Info findings IN-01..IN-08 were not in fix_scope (`critical_warning`) and were not attempted.
- All fixes applied in an isolated worktree on temp branch `gsd-reviewfix/20-3463716`; commits fast-forward back to `main` during cleanup.

---

_Fixed: 2026-08-19T21:17:48Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
