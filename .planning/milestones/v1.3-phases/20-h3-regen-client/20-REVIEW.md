---
phase: 20-h3-regen-client
reviewed: 2026-08-19T21:22:49Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - analysis/roundtrip/h3_regen.py
  - analysis/roundtrip/workflow_fl2va.json
  - run_pipeline.py
  - tests/test_h3_regen.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 20: Code Review Report

**Reviewed:** 2026-08-19T21:22:49Z (re-review, iteration 2 of --auto loop)
**Depth:** standard
**Files Reviewed:** 4
**Status:** clean (iteration 2 — all 7 fixes from 8a42230..fdf3ba9 verified correct, no new Critical/Warning)

## Summary

**Iteration 2 re-review after the 7 fixes (commits 8a42230..fdf3ba9).** Scope per the fix report: `analysis/roundtrip/h3_regen.py` (current state re-read in full, plus hunk-by-hunk diff against pre-fix 02b7c16), `run_pipeline.py` (force-list diff), `tests/test_h3_regen.py` (16 new regression anchors), and cross-reference against `spec/schemas/roundtrip.schema.json` (shots items require only `shot_id` — the stripped intermediate sidecar state is schema-valid).

All seven fixes are correctly implemented and each has a real regression anchor that fails on the pre-fix code shape. Both gates pass:

- `python3 -m pytest tests/ -q` → **119 passed** (matches expected count)
- `python3 spec/validate.py` → **exit 0** (`[validate] OK`, failures=0 across minimal/v1.1/v1.2/v1.3/smoke fixtures)
- `python3 -m py_compile` on both changed source files → OK (no dangling references to the removed `roundtrip_dir`/`roundtrip_json` force-list variables)

No new Critical or Warning findings. Status: **clean**.

## Re-Review Verification (iteration 2)

| Fix | Claim | Verified | Evidence |
|-----|-------|----------|----------|
| CR-01 | `.part` + `os.replace` download atomicity | ✅ | `h3_regen.py:558-580` — download streams to `dest + ".part"` (same dir → same filesystem → atomic replace); `except BaseException` unlinks the `.part` and re-raises, so a partial file can never occupy the final path. `test_view_download_atomic_on_mid_transfer_failure` / `test_view_download_success_leaves_no_part` |
| CR-01 | sha256 verify on hit + backward-compat | ✅ | `cache_is_hit` (`h3_regen.py:621-639`): `expected = meta.get("mp4_sha256"); return not expected or _file_sha256(...) == expected` — metas without the field degrade to size-only. `test_truncated_mp4_rejected_as_cache_hit` reproduces the exact three-run stale-meta/truncated-file sequence. Live check: the real ep01 smoke metas (`output/《小江湖》第01话…/route_cache/h3_regen/shot_00{1,47}.json`) do carry `mp4_sha256` and both match the on-disk mp4s, so actual caches are protected by the strict path |
| CR-02 | force-after-gate ordering; engine-down byte-identical | ✅ | `main()` order is now gate (`:1233-1239`) → lock (`:1245`) → force (`:1254-1266`) → sampling/filter → guard → loop. Engine-down returns 0 having touched only `warnings.json` (degrade record — by design). `test_force_with_engine_down_preserves_everything` asserts mp4/meta byte-identical, sidecar present, and `[force]` never printed |
| CR-02 | skipped.json/sampling relocation | ✅ | Sampling + `--max-shot-sec` filter moved after the force clear, so a forced run rewrites `skipped.json` for the new round instead of writing it into a dir about to be rmtree'd. Non-force runs READ-merge as before (idempotent per shot_id) |
| WR-01 | `strip_sidecar_regen_half` preserves scores/verdict | ✅ | `h3_regen.py:870-900` strips only `regen`/`status` keys; entries left with only `shot_id` are dropped; file removed only when no human data remains (old unlink semantics confined to the degenerate case). Schema check: shots items require only `shot_id`, so the stripped intermediate state is valid. `test_force_preserves_verdicts_in_sidecar` pins a `rejected`/`human` verdict surviving a `--force` re-render; `test_force_strip_removes_file_when_no_human_data` pins the degenerate case |
| WR-01 | pipeline force list no longer deletes roundtrip data | ✅ | `run_pipeline.py:774-793` diff: `roundtrip/` and `roundtrip.json` removed from the clear list; `route_cache/` rmtree still covers the h3_regen cache (documented trade-off: metas gone → next run re-renders, products/sidecar survive). Compile + grep confirm no dangling references |
| WR-02 | `expected_length` in hit predicate | ✅ | `h3_regen.py:1336-1340` — `h3_frame_count(shot["duration"])` computed *before* `cache_read`; mismatch → miss → re-render. Old metas missing `length` miss conservatively. `test_resegmentation_same_prompt_invalidates` (2.0s→5.5s boundary drift, prompt_text unchanged → re-render at length 141; untouched sibling still hits) |
| WR-03 | flock placement / lock file outside rmtree / degrade path | ✅ | Lock at `route_cache/h3_regen.lock` (`:1150-1151`) is a *sibling* of the rmtree'd `route_cache/h3_regen/` dir — verified path-join. Acquired after gate, before force: a contending instance degrades exit-0 with a `[roundtrip]` str warning *before* any destructive action or TTS kill (`test_batch_lock_second_instance_degrades` asserts zero submissions and no `ss` call). Post-lock body in `try/finally`; `test_batch_lock_released_after_run` re-acquires after main. `_atomic_write_json` tmp is PID-stamped (`test_atomic_write_tmp_pid_stamped`) |
| WR-04 | two-layer validation | ✅ | `write_roundtrip_sidecar` (`h3_regen.py:779-867`): layer ① validates this batch's entries in isolation → sys.exit (fail-loud, `test_sidecar_refuses_invalid_path` still pins it); layer ② attributes merged-payload errors to shot_ids via `absolute_path`, emits per-shot str warning, backs up to `roundtrip.json.bak-<ts>`, drops the entries, re-validates, writes the rest — no retry deadlock. Returned warnings flow through `pending_warnings` → flush (e2e test asserts warnings.json content). Unattributable top-level errors still fail loud |
| WR-04 | `.bak` accumulation bounded? | ✅ (effectively) | Layer ② triggers only on bad *pre-existing* entries and drops them, so the next run is clean — one `.bak` per bad-data introduction event, self-limiting. Same-second collisions overwrite (second-resolution timestamp), which requires two distinct bad-entry events within one second — negligible |
| WR-05 | rc checks + stale-frame unlink ordering | ✅ | `extract_endpoint_frames` (`:387-417`): `os.unlink(dest)` *before* each ffmpeg run (stale bytes cannot survive a failed extraction), then rc/dest-exists/size triple check with stderr in the RuntimeError. `upload_image` (`:420-441`): rc≠0 / non-JSON / missing-`name` all RuntimeError with the server body surfaced. `_stderr_snip` tolerates bytes/str/absent. All raise paths land in the per-shot handler → `failed_detail` → sidecar `status.error`. Four tests including the e2e `test_ffmpeg_failure_e2e_shot_failed_with_detail` (asserts no cache write for the failed shot) |

### Residual observations (non-blocking notes, not findings)

1. **Backward-compat size-only fallback** (`cache_is_hit`): a hypothetical pre-`mp4_sha256` meta degrades to size-only. This is the documented fix trade-off, and the actual ep01 smoke metas carry the field (verified live), so no real cache sits on the weak path.
2. **`run_pipeline.py --force` rmtrees the whole `route_cache/`**, which includes `route_cache/h3_regen.lock` — running a pipeline `--force` concurrently with an in-flight h3_regen batch would delete the lock file (new inode on next acquire → mutual exclusion breaks). This concurrency is already mutually destructive regardless of the lock (the rmtree also deletes the cache the batch is writing), so it is an operator-discipline matter, not a code defect introduced by the fix.
3. **Pre-existing (unchanged by fixes, per git blame of the merge loop):** non-dict / missing-`shot_id` entries in a hand-edited `roundtrip.json` are silently dropped by the READ-merge filter without the layer-② warning/backup path (layer ② only catches *schema*-invalid dict entries). Behavior is identical pre- and post-fix.
4. A mid-batch SIGKILL can leave a `shot_XXX_regen.mp4.part` on disk; nothing cleans stale `.part` files (a `--force` clear does). Harmless residue — the final path is never a partial file.

Known accepted per iteration 1 and not re-flagged: IN-01..IN-08; smoke evidence validity judgment.

---

## Iteration 1 Findings (historical record, all 7 Critical/Warning fixed — see outcomes inline)

**Originally reviewed:** 2026-08-19T21:03:05Z — 4 files, depth standard

Iteration 1 reviewed the h3 regen client (`analysis/roundtrip/h3_regen.py`), the workflow template (`analysis/roundtrip/workflow_fl2va.json`), the `run_pipeline.py` `--force` increment, and the test suite. Cross-referenced against `spec/schemas/roundtrip.schema.json`, `scripts/export_asset.py` (SCHEMA_VERSION single source, warnings dual-shape reader, roundtrip mount block), `analysis/call_shot_analysis.py:video_content_hash`, and `analysis/engine_clients/qwen_eye_client.py:_http_json` — all claimed mirrors verified accurate.

Overall carefully engineered code: deepcopy template injection, list-form subprocess everywhere, atomic JSON writes, deterministic seed/sampling, path-traversal rejection on `/view` filenames, and a genuinely strong test suite (guard ordering, PID attribution anti-self-lock, dual-shape warnings merge, cache invalidation all have regression anchors). The test suite itself is reliable — no flaky patterns or missing assertions found.

Two data-integrity defects sat on the exact axes the phase cares about (download completeness, cache boundaries, `--force` semantics), plus five warnings — all fixed in iteration 1's fix pass and verified above.

## Critical Issues (iteration 1 — fixed)

### CR-01: Non-atomic mp4 download + stale cache meta ⇒ truncated video accepted as cache hit

**File:** `analysis/roundtrip/h3_regen.py:517-527` (with `cache_is_hit` at 568-575, `cache_write` at 601-606)
**Issue:** `_view_download` opens the final destination (`roundtrip/shot_XXX_regen.mp4`) with `open(dest, "wb")` and streams `resp.read()` into it. If the read raises mid-transfer (`http.client.IncompleteRead`, timeout, connection reset), the per-shot `except` marks the shot failed — but the **partial file stays at the final path** and the **previous run's cache meta is never invalidated**. Trace:

- Run A: shot rendered, `shot_005.json` meta (4-tuple K, `mp4_sha256` of full file) + full mp4 written.
- mp4 deleted/truncated externally → Run B: `cache_is_hit` False (file missing) → re-render succeeds → `_view_download` fails midway → partial mp4 on disk, stale meta K untouched.
- Run C: `cache_read` matches K; `cache_is_hit` sees partial file `size > MIN_MP4_BYTES` (a multi-MB truncation passes the 1KB bar) → **true false-hit**. Sidecar is rebuilt from the stale meta whose `mp4_sha256` no longer matches the file; Phase 21 scorer and the exported dataset receive a broken video with no warning anywhere.

The size-only check is documented as intentional against *renderer corruption*, but download-truncation is a self-inflicted and fully preventable case — and `mp4_sha256` is already stored in meta yet never verified on hit.

**Fix:**
```python
def _view_download(item: dict, comfy_url: str, dest: str) -> None:
    q = urllib.parse.urlencode({...})
    tmp = dest + ".part"
    with urllib.request.urlopen(f"{comfy_url}/view?{q}", timeout=300) as resp, \
            open(tmp, "wb") as f:
        f.write(resp.read())
    os.replace(tmp, dest)          # partial file can never occupy the final path

def cache_is_hit(meta: dict | None, mp4_path: str) -> bool:
    ...
    if os.path.getsize(mp4_path) <= MIN_MP4_BYTES:
        return False
    expected = meta.get("mp4_sha256")            # 深检成本 ~50MB hash，远低于重渲
    return not expected or _file_sha256(mp4_path) == expected
```
Add a regression test mirroring this exact three-run sequence (current suite has no stale-meta/partial-file case).

**Outcome (fix):** FIXED — `_view_download` now writes `dest + ".part"` and `os.replace`s into place only after a complete read (mid-transfer failure unlinks the `.part` and re-raises; final path never holds a partial file). `cache_is_hit` additionally verifies stored `mp4_sha256` on hit (backward-compatible: metas without the field degrade to size-only). Docstring "cache 惯例" updated. Regression anchors added: `test_view_download_atomic_on_mid_transfer_failure`, `test_view_download_success_leaves_no_part`, `test_truncated_mp4_rejected_as_cache_hit` (the three-run sequence). **Verified in iteration 2 re-review.**

### CR-02: `--force` destroys cache/artifacts/sidecar before the ComfyUI reachability gate

**File:** `analysis/roundtrip/h3_regen.py:1027-1037` (force clear) vs `1076-1082` (gate)
**Issue:** Execution order is: load inputs → **`--force` rmtree/unlink of `route_cache/h3_regen/`, `roundtrip/`, `roundtrip.json`** → resolution validation → ComfyUI `system_stats` gate → VRAM guard. If ComfyUI is down (the exact scenario the gate exists for), the run has *already* irreversibly deleted hours of render cache, the mp4 products, and the whole sidecar — then prints "graceful-degrade 退出" and returns 0. The module docstring claims "ComfyUI down 时先降级退出，不白杀 TTS、不空轮 eye lease" as the rationale for gate-first ordering, yet the most destructive action of all runs before the gate. Combined with the schema invariant "verdict … rejected 永不删除" (`spec/schemas/roundtrip.schema.json:97`), one `--force` during engine downtime silently and permanently destroys human HITL verdict data with a success exit code.

**Fix:** Move the `--force` block to immediately *after* the reachability gate (before `batch_start_guard`), so degrade-on-unreachable exits with everything intact. (No existing test pinned the old order; add a test: `--force` + non-200 gate → files still present.)

**Outcome (fix):** FIXED — `--force` block moved to immediately after the `system_stats` gate (before sampling/filter/guard). Engine-down degrade now exits with cache, `roundtrip/`, and `roundtrip.json` byte-identical. One deliberate adaptation: the sampling/`--max-shot-sec` filter (which writes `skipped.json` under `route_cache/h3_regen/`) was moved to *after* the force clear, so a `--force` run rewrites the skipped list for the new round instead of having it rmtree'd after being written. Module docstring step list updated. Regression anchor: `test_force_with_engine_down_preserves_everything`. **Verified in iteration 2 re-review.**

## Warnings (iteration 1 — fixed)

### WR-01: `--force` deletes `roundtrip.json` wholesale, violating the "rejected 永不删除" sidecar invariant

**File:** `analysis/roundtrip/h3_regen.py:1030-1036`; `run_pipeline.py:773-775, 788-789`
**Issue:** The READ-merge machinery (`write_roundtrip_sidecar`) exists precisely to preserve Phase 21 `scores`/`verdict` fields, and the schema states rejected verdicts are never deleted. But both `--force` paths `unlink(roundtrip.json)` unconditionally. After Phase 21 lands, an operator re-running with `--force` (or a pipeline `--force`, which also deletes roundtrip data the pipeline itself cannot regenerate — h3_regen is not a pipeline step) destroys all scoring and human verdict history for a re-render that, with deterministic seeds, may be byte-similar.
**Fix:** In both `--force` paths, either strip only the `regen`/`status` halves per shot (keeping `scores`/`verdict`), or rename to `roundtrip.json.bak-<ts>` instead of unlink. At minimum, print an explicit warning that verdicts will be lost.

**Outcome (fix):** FIXED (strip option) — new `strip_sidecar_regen_half()` replaces the client's `unlink(roundtrip.json)`: per shot only `regen`/`status` keys are removed, `scores`/`verdict` (incl. rejected) survive for the batch-end READ-merge to rehydrate; entries left with only `shot_id` are dropped, and the file is removed only when *no* human data remains. `--force` help text updated. `run_pipeline.py` `--force` list tightened in sync: `roundtrip/` and `roundtrip.json` removed from the clear list. Regression anchors: `test_force_preserves_verdicts_in_sidecar`, `test_force_strip_removes_file_when_no_human_data`. **Verified in iteration 2 re-review.**

### WR-02: 4-tuple cache key is blind to shot boundaries — re-segmentation reuses stale renders

**File:** `analysis/roundtrip/h3_regen.py:1115-1123` (key4), `552-565` (cache_read)
**Issue:** `key4 = {video_content_hash, engine_name, engine_version, prompt_version(prompt_text)}`. `video_content_hash` pins the *video*, not the *segmentation*. If `shots.json` is regenerated with the same source video, a shot whose `prompt_text` happens to be unchanged will cache-hit and reuse a render whose first/last frames were extracted at the *old* `start_sec`/`end_sec` and whose `length` reflects the old duration. Meta already stores `length`, so the mismatch is detectable but never checked.
**Fix:** Extend the hit check with the stored observables — `if meta.get("length") != h3_frame_count(shot["duration"]): return None` (or fold boundaries into `prompt_version`).

**Outcome (fix):** FIXED (first option) — `cache_is_hit` gained an `expected_length` parameter; `main` computes `h3_frame_count(shot["duration"])` before the cache probe and a stored-vs-current length mismatch is a miss → re-render. The 4-tuple cache-key shape is unchanged. Regression anchor: `test_resegmentation_same_prompt_invalidates`. **Verified in iteration 2 re-review.**

### WR-03: No concurrency guard on cache/sidecar/warnings read-merge-write; fixed `.tmp` name

**File:** `analysis/roundtrip/h3_regen.py:590-598` (`_atomic_write_json`), `620-634` (`append_roundtrip_warnings`), `705-743` (`write_roundtrip_sidecar`)
**Issue:** Two simultaneous `h3_regen` invocations on the same `--work-dir` have no mutual exclusion: both run the VRAM guard and kill TTS / post `/free`; both submit full batches to the same ComfyUI queue; the read-merge-write cycles on `warnings.json` and `roundtrip.json` are last-writer-wins; `_atomic_write_json` uses the fixed name `path + ".tmp"`, so concurrent writers to the same target interleave on the tmp file.
**Fix:** PID-stamp the tmp file and take an flock at batch start (non-blocking → warning + exit 0, matching the graceful-degrade posture).

**Outcome (fix):** FIXED — `_atomic_write_json` tmp is now `{path}.tmp.{pid}`. New `acquire_batch_lock`/`release_batch_lock`: `flock(LOCK_EX|LOCK_NB)` on `route_cache/h3_regen.lock` (deliberately *outside* the `--force` rmtree list; flock auto-releases on process death). Acquisition sits after the reachability gate and before the `--force` clear; the post-lock body of `main()` is wrapped in `try/finally`. Regression anchors: `test_atomic_write_tmp_pid_stamped`, `test_batch_lock_second_instance_degrades`, `test_batch_lock_released_after_run`. **Verified in iteration 2 re-review.**

### WR-04: Sidecar write validates the *merged* payload — invalid pre-existing entries abort the write after the whole batch

**File:** `analysis/roundtrip/h3_regen.py:732-742`
**Issue:** `write_roundtrip_sidecar` validated the full merged payload including foreign entries; any pre-existing entry invalid against the current schema made the client `sys.exit` **after the entire batch rendered**, leaving the sidecar unwritten. Retry hits the identical failure → permanent deadlock.
**Fix:** Validate this run's `entries` in isolation before merging; on merged-validation failure, report the offending pre-existing `shot_id`s, quarantine/backup them, and write the rest.

**Outcome (fix):** FIXED (two-layer validation) — layer ① validates this batch's `entries` in isolation → `sys.exit` on error; layer ② attributes offending entries to `shot_id`s via error `absolute_path`, emits a per-shot str warning, backs the pre-existing file up to `roundtrip.json.bak-<ts>`, drops those entries, re-validates, and writes the rest. Unattributable top-level errors still fail loud. `main()` extends `pending_warnings` with the returned warnings before the flush. Regression anchors: `test_sidecar_preexisting_bad_entry_skipped_not_deadlocked`, `test_sidecar_bad_preexisting_entry_e2e_warning_flush`. **Verified in iteration 2 re-review (.bak accumulation effectively self-limiting — layer ② drops the offending entries, subsequent runs are clean).**

### WR-05: ffmpeg frame extraction and curl upload results unchecked — silent stale-frame upload possible

**File:** `analysis/roundtrip/h3_regen.py:383-388` (`extract_endpoint_frames`), `395-400` (`upload_image`)
**Issue:** Both `subprocess.run` return values were discarded. For ffmpeg: on failure the dest file is never created *or* — because the dest name is deterministic — an **old frame from a previous run stays in place** and gets uploaded. For curl: a non-2xx or empty stdout fails only via `json.loads("")` → `JSONDecodeError` ("Expecting value"); a curl that exits 0 with a JSON error body raises `KeyError: "name"` instead of surfacing the server message.
**Fix:** Check rc/dest existence/size with stderr in the error detail; delete `dest` before invoking ffmpeg so stale bytes cannot survive a failed extraction.

**Outcome (fix):** FIXED — `extract_endpoint_frames` unlinks `dest` before each ffmpeg invocation and raises `RuntimeError` on non-zero rc / missing / empty dest. `upload_image` raises on curl rc≠0, on non-JSON stdout, and on a JSON body without `name`. New `_stderr_snip` helper tolerates bytes/str/absent stderr. Regression anchors: `test_ffmpeg_failure_no_stale_frame_survives`, `test_ffmpeg_empty_dest_fails`, `test_upload_failures_fail_loud`, `test_ffmpeg_failure_e2e_shot_failed_with_detail`. **Verified in iteration 2 re-review.**

## Info (iteration 1 — accepted, out of fix scope)

### IN-01: No-op SIGINT handler

**File:** `analysis/roundtrip/h3_regen.py:1017`
**Issue:** `signal.signal(signal.SIGINT, signal.default_int_handler)` installs what is already Python's default; the comment implies it enables something. Dead statement.
**Fix:** Remove it, or implement the implied intent (catch `KeyboardInterrupt` in `main` and still flush warnings/sidecar before exiting).

### IN-02: `_ROUNDTRIP_WARNING_CODES` enum duplicated from `export_asset.py`

**File:** `analysis/roundtrip/h3_regen.py:144-150`
**Issue:** SCHEMA_VERSION is strictly single-sourced via importlib, but the three-code closed enum is copy-pasted with only a comment enforcing sync. Drift would silently break the strip-match in `_is_roundtrip_warning` and export_asset's `_valid_warnings_list`.
**Fix:** Load the tuple from the same `export_asset` module already being imported for SCHEMA_VERSION.

### IN-03: "kill 后" audit warning is not a re-probe

**File:** `analysis/roundtrip/h3_regen.py:896-899`
**Issue:** The after-kill audit warning reuses the pre-kill `listeners` list, so it asserts pids/ports that were killed without verifying they died.
**Fix:** Call `find_tts_listeners()` again after `kill_tts` and record the residual set in the after-warning.

### IN-04: `--comfy-url` trailing slash produces `//prompt` paths; late `jsonschema` import unguarded

**File:** `analysis/roundtrip/h3_regen.py:996-997`, `734`
**Issue:** (a) A trailing slash yields `http://host:8188//prompt`, which typically 404s and degrades the whole run as `comfyui_unreachable`. (b) `from jsonschema import Draft202012Validator` sits inside the write path; a missing dep kills the run with a raw ImportError before any sidecar write after the batch rendered.
**Fix:** Normalize the URL at parse time; move the import to a guarded top-level try or fail-fast preflight.

### IN-05: `rendered_at` is local time without timezone

**File:** `analysis/roundtrip/h3_regen.py:605`
**Issue:** Naive local time; the repo's timestamp convention is ISO-8601 UTC.
**Fix:** `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`.

### IN-06: fps=24 hardcoded in template duplicates the `FPS` constant

**File:** `analysis/roundtrip/workflow_fl2va.json:20` vs `analysis/roundtrip/h3_regen.py:154`
**Issue:** `CreateVideo` fps is a literal in the template; the module's `FPS` drives the length grid. Changing one without the other silently desynchronizes rendered duration from `duration_sec` metadata.
**Fix:** Inject `fps` into node 42 alongside the other locked values, or add a template-vs-constant assertion at load time.

### IN-07: Malformed `shots.json` entry crashes with raw KeyError, contradicting degrade posture

**File:** `analysis/roundtrip/h3_regen.py:302`
**Issue:** `int(s["id"])` raises `KeyError` if any shot lacks `id` — an uncaught traceback rather than the structured warning + skip used for missing prompts.
**Fix:** Guard per-entry (skip + `[roundtrip]` str warning), mirroring the prompt-join handling.

### IN-08: Exit code 0 on total failure

**File:** `analysis/roundtrip/h3_regen.py:1221`
**Issue:** `main()` returns 0 in every path, including "all attempted shots failed" — automation cannot distinguish success from total failure without parsing stdout.
**Fix:** Consider a non-zero exit when `rendered == 0 and cache_hits == 0 and (failed or skipped)`, keeping the engine-down degrade path at 0.

---

_Reviewed: 2026-08-19T21:22:49Z (iteration 2 re-review)_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
