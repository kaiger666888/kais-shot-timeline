---
phase: 20-h3-regen-client
reviewed: 2026-08-19T21:03:05Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - analysis/roundtrip/h3_regen.py
  - analysis/roundtrip/workflow_fl2va.json
  - run_pipeline.py
  - tests/test_h3_regen.py
findings:
  critical: 2
  warning: 5
  info: 8
  total: 15
status: issues_found
---

# Phase 20: Code Review Report

**Reviewed:** 2026-08-19T21:03:05Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the h3 regen client (`analysis/roundtrip/h3_regen.py`, 1226 lines), the workflow template (`analysis/roundtrip/workflow_fl2va.json`), the `run_pipeline.py` `--force` increment (lines 753-794, rest pre-existing), and the test suite (`tests/test_h3_regen.py`). Cross-referenced against `spec/schemas/roundtrip.schema.json`, `scripts/export_asset.py` (SCHEMA_VERSION single source, warnings dual-shape reader, roundtrip mount block), `analysis/call_shot_analysis.py:video_content_hash`, and `analysis/engine_clients/qwen_eye_client.py:_http_json` — all claimed mirrors verified accurate.

Overall this is carefully engineered code: deepcopy template injection, list-form subprocess everywhere, atomic JSON writes, deterministic seed/sampling, path-traversal rejection on `/view` filenames, and a genuinely strong test suite (guard ordering, PID attribution anti-self-lock, dual-shape warnings merge, cache invalidation all have regression anchors). The test suite itself is reliable — no flaky patterns or missing assertions found.

However, two data-integrity defects sit on the exact axes the phase cares about (download completeness, cache boundaries, `--force` semantics), and both can silently corrupt or destroy the roundtrip deliverable:

1. **Non-atomic `/view` download writes directly to the final mp4 path.** A mid-download failure leaves a partial file while a matching stale cache meta survives, and `cache_is_hit` only checks `size > 1KB` — so the next run accepts a truncated mp4 as a hit and it flows into `roundtrip.json` and Phase 21.
2. **The `--force` destructive clear runs *before* the ComfyUI reachability gate.** With the engine down, `--force` irreversibly deletes the cache, the `roundtrip/` products, and the entire `roundtrip.json` (including any Phase 21 scores/human verdicts) and then exits 0 "gracefully" — directly contradicting the module's own "ComfyUI down 时先降级退出" ordering claim.

## Critical Issues

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

**Outcome (fix):** FIXED — `_view_download` now writes `dest + ".part"` and `os.replace`s into place only after a complete read (mid-transfer failure unlinks the `.part` and re-raises; final path never holds a partial file). `cache_is_hit` additionally verifies stored `mp4_sha256` on hit (backward-compatible: metas without the field degrade to size-only). Docstring "cache 惯例" updated. Regression anchors added: `test_view_download_atomic_on_mid_transfer_failure`, `test_view_download_success_leaves_no_part`, `test_truncated_mp4_rejected_as_cache_hit` (the three-run sequence).

### CR-02: `--force` destroys cache/artifacts/sidecar before the ComfyUI reachability gate

**File:** `analysis/roundtrip/h3_regen.py:1027-1037` (force clear) vs `1076-1082` (gate)
**Issue:** Execution order is: load inputs → **`--force` rmtree/unlink of `route_cache/h3_regen/`, `roundtrip/`, `roundtrip.json`** → resolution validation → ComfyUI `system_stats` gate → VRAM guard. If ComfyUI is down (the exact scenario the gate exists for), the run has *already* irreversibly deleted hours of render cache, the mp4 products, and the whole sidecar — then prints "graceful-degrade 退出" and returns 0. The module docstring (lines 15-17) claims "ComfyUI down 时先降级退出，不白杀 TTS、不空轮 eye lease" as the rationale for gate-first ordering, yet the most destructive action of all runs before the gate. Combined with the schema invariant "verdict … rejected 永不删除" (`spec/schemas/roundtrip.schema.json:97`), one `--force` during engine downtime silently and permanently destroys human HITL verdict data with a success exit code.

**Fix:** Move the `--force` block to immediately *after* the reachability gate (before `batch_start_guard`), so degrade-on-unreachable exits with everything intact:
```python
    status, _body = _http_json(f"{args.comfy_url}/system_stats")
    if status != 200:
        ...degrade exit 0...              # --force 未执行，cache/sidecar 完好

    if args.force:
        ...rmtree/unlink 清单...          # 引擎确认可用后才允许破坏性清除
```
(No existing test pins the current order — `test_client_force_rerenders_all` uses a healthy FakeHTTP, so the reorder is safe. Add a test: `--force` + non-200 gate → files still present.)

**Outcome (fix):** FIXED — `--force` block moved to immediately after the `system_stats` gate (before sampling/filter/guard). Engine-down degrade now exits with cache, `roundtrip/`, and `roundtrip.json` byte-identical. One deliberate adaptation: the sampling/`--max-shot-sec` filter (which writes `skipped.json` under `route_cache/h3_regen/`) was moved to *after* the force clear, so a `--force` run rewrites the skipped list for the new round instead of having it rmtree'd after being written. Module docstring step list updated. Regression anchor: `test_force_with_engine_down_preserves_everything`.

## Warnings

### WR-01: `--force` deletes `roundtrip.json` wholesale, violating the "rejected 永不删除" sidecar invariant

**File:** `analysis/roundtrip/h3_regen.py:1030-1036`; `run_pipeline.py:773-775, 788-789`
**Issue:** The READ-merge machinery (`write_roundtrip_sidecar`) exists precisely to preserve Phase 21 `scores`/`verdict` fields, and the schema states rejected verdicts are never deleted. But both `--force` paths `unlink(roundtrip.json)` unconditionally. After Phase 21 lands, an operator re-running with `--force` (or a pipeline `--force`, which also deletes roundtrip data the pipeline itself cannot regenerate — h3_regen is not a pipeline step) destroys all scoring and human verdict history for a re-render that, with deterministic seeds, may be byte-similar. The flag help text does mention the file, but the contract conflict is unacknowledged.
**Fix:** In both `--force` paths, either strip only the `regen`/`status` halves per shot (keeping `scores`/`verdict`), or rename to `roundtrip.json.bak-<ts>` instead of unlink. At minimum, print an explicit warning that verdicts will be lost.

**Outcome (fix):** FIXED (strip option) — new `strip_sidecar_regen_half()` replaces the client's `unlink(roundtrip.json)`: per shot only `regen`/`status` keys are removed, `scores`/`verdict` (incl. rejected) survive for the batch-end READ-merge to rehydrate; entries left with only `shot_id` are dropped, and the file is removed only when *no* human data remains (old semantics preserved for that degenerate case). `--force` help text updated. `run_pipeline.py` `--force` list tightened in sync: `roundtrip/` and `roundtrip.json` removed from the clear list (pipeline cannot regenerate roundtrip data — h3_regen is not a pipeline step); the `route_cache/` rmtree still covers `route_cache/h3_regen/` cache. Regression anchors: `test_force_preserves_verdicts_in_sidecar`, `test_force_strip_removes_file_when_no_human_data`.

### WR-02: 4-tuple cache key is blind to shot boundaries — re-segmentation reuses stale renders

**File:** `analysis/roundtrip/h3_regen.py:1115-1123` (key4), `552-565` (cache_read)
**Issue:** `key4 = {video_content_hash, engine_name, engine_version, prompt_version(prompt_text)}`. `video_content_hash` pins the *video*, not the *segmentation*. If `shots.json` is regenerated (different detector params/manual edits) with the same source video, a shot whose `prompt_text` happens to be unchanged (plausible — facet text can survive small boundary shifts) will cache-hit and reuse a render whose first/last frames were extracted at the *old* `start_sec`/`end_sec` and whose `length` reflects the old duration. Meta already stores `length`, so the mismatch is detectable but never checked.
**Fix:** Extend the hit check with the stored observables — cheapest option inside `cache_read`/hit path:
```python
if meta.get("length") != h3_frame_count(shot["duration"]):
    return None        # 边界变了 → 该镜重渲
```
(or fold `f"{start_sec:.3f}-{end_sec:.3f}"` into `prompt_version` input, which keeps the 4-tuple shape).

**Outcome (fix):** FIXED (first option) — `cache_is_hit` gained an `expected_length` parameter; `main` computes `h3_frame_count(shot["duration"])` before the cache probe (moved out of the render `try`) and a stored-vs-current length mismatch is a miss → re-render. The 4-tuple cache-key shape is unchanged. Docstring "cache 惯例" updated. Regression anchor: `test_resegmentation_same_prompt_invalidates` (boundary 2.0s→5.5s, prompt_text unchanged → re-render at length 141; untouched sibling shot still hits).

### WR-03: No concurrency guard on cache/sidecar/warnings read-merge-write; fixed `.tmp` name

**File:** `analysis/roundtrip/h3_regen.py:590-598` (`_atomic_write_json`), `620-634` (`append_roundtrip_warnings`), `705-743` (`write_roundtrip_sidecar`)
**Issue:** Two simultaneous `h3_regen` invocations on the same `--work-dir` (easy to do from two terminals, or a stray cron + manual run) have no mutual exclusion: (a) both run the VRAM guard and both kill TTS / post `/free`; (b) both submit full batches to the same ComfyUI queue; (c) the read-merge-write cycles on `warnings.json` and `roundtrip.json` are last-writer-wins — the second writer's read predates the first writer's write, so the first run's sidecar entries and warnings are silently dropped; (d) `_atomic_write_json` uses the fixed name `path + ".tmp"`, so concurrent writers to the same target interleave on the tmp file and can `os.replace` each other's partial content. Per-shot atomicity protects individual files, but the multi-file state (meta + mp4 + sidecar) has no coordination.
**Fix:** PID-stamp the tmp file (`tmp = f"{path}.tmp.{os.getpid()}"`) and take an flock at batch start (e.g., `fcntl.flock` on `route_cache/h3_regen/lock`, non-blocking → structured warning + exit 0, matching the graceful-degrade posture).

**Outcome (fix):** FIXED (stdlib minimal方案) — `_atomic_write_json` tmp is now `{path}.tmp.{pid}`. New `acquire_batch_lock`/`release_batch_lock`: `flock(LOCK_EX|LOCK_NB)` on `route_cache/h3_regen.lock` (deliberately *outside* the `--force` rmtree list so lock identity survives a force clear; flock auto-releases on process death — no stale locks). Acquisition sits after the reachability gate and before the `--force` clear, so a contending second instance degrades exit-0 with a `[roundtrip]` str warning (str form chosen to stay off the 3-code closed enum) *before* any destructive action or TTS kill. The post-lock body of `main()` is wrapped in `try/finally` to always release. Regression anchors: `test_atomic_write_tmp_pid_stamped`, `test_batch_lock_second_instance_degrades`, `test_batch_lock_released_after_run`.

### WR-04: Sidecar write validates the *merged* payload — invalid pre-existing entries abort the write after the whole batch

**File:** `analysis/roundtrip/h3_regen.py:732-742`
**Issue:** `write_roundtrip_sidecar` runs `Draft202012Validator.iter_errors` over the full merged payload, which includes foreign entries loaded from the existing `roundtrip.json`. Any pre-existing entry that is invalid against the *current* schema (hand-edited file, content written by a future Phase 21/22 under a newer schema — exactly the forward-evolution the READ-merge is built for) makes the client `sys.exit` **after the entire batch rendered**, leaving the sidecar unwritten. Retry hits the identical validation failure → permanent deadlock until the operator hand-edits or deletes the sidecar. Fail-closed against writing bad data is right; failing on *someone else's* stale data while discarding *this run's* valid results is not.
**Fix:** Validate this run's `entries` in isolation before merging; if merged validation fails, report the offending pre-existing `shot_id`s, and either (a) quarantine them to `roundtrip.json.rejected` and write the rest, or (b) back up the existing file before `sys.exit` so the retry path is recoverable. The batch results themselves are always schema-clean by construction (they were built by `build_sidecar_entries` under the same schema).

### WR-05: ffmpeg frame extraction and curl upload results unchecked — silent stale-frame upload possible

**File:** `analysis/roundtrip/h3_regen.py:383-388` (`extract_endpoint_frames`), `395-400` (`upload_image`)
**Issue:** Both `subprocess.run` return values are discarded. For ffmpeg: on failure (bad seek, transient decode error, `TimeoutExpired` is caught upstream but non-timeout failures are not) the dest file is never created *or* — because the dest name is deterministic per (vch, shot) — an **old frame from a previous run stays in place** and gets uploaded, producing a render conditioned on stale frames while the cache meta records the *new* prompt_version. For curl: a non-2xx or empty stdout only fails incidentally via `json.loads("")` → `JSONDecodeError`, whose message ("Expecting value") says nothing about the actual cause; a curl that exits 0 with a JSON error body (`{"error": ...}`) raises `KeyError: "name"` instead of surfacing the server message.
**Fix:**
```python
proc = subprocess.run([...], capture_output=True, timeout=60)
if proc.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) == 0:
    raise RuntimeError(f"ffmpeg 帧提取失败 rc={proc.returncode} dest={dest} "
                       f"stderr={proc.stderr.decode(errors='replace')[:200]}")
# upload_image 同理：
if proc.returncode != 0:
    raise RuntimeError(f"curl 上传失败 rc={proc.returncode} stderr={proc.stderr[:200]}")
info = json.loads(proc.stdout or "{}")
if "name" not in info:
    raise RuntimeError(f"上传响应异常: {str(info)[:200]}")
```
Also delete `dest` before invoking ffmpeg so stale bytes cannot survive a failed extraction.

## Info

### IN-01: No-op SIGINT handler

**File:** `analysis/roundtrip/h3_regen.py:1017`
**Issue:** `signal.signal(signal.SIGINT, signal.default_int_handler)` installs what is already Python's default; the comment implies it enables something. Dead statement.
**Fix:** Remove it, or implement the implied intent (catch `KeyboardInterrupt` in `main` and still flush warnings/sidecar before exiting — currently Ctrl-C skips the finalization block entirely since there is no `try/finally` around the batch loop).

### IN-02: `_ROUNDTRIP_WARNING_CODES` enum duplicated from `export_asset.py`

**File:** `analysis/roundtrip/h3_regen.py:144-150`
**Issue:** SCHEMA_VERSION is strictly single-sourced via importlib, but the three-code closed enum is copy-pasted with only a comment ("逐字对齐") enforcing sync. Drift would silently break the strip-match in `_is_roundtrip_warning` and export_asset's `_valid_warnings_list`.
**Fix:** Load the tuple from the same `export_asset` module already being imported for SCHEMA_VERSION (extend `_load_schema_version` into a small `_load_export_asset()` returning the module).

### IN-03: "kill 后" audit warning is not a re-probe

**File:** `analysis/roundtrip/h3_regen.py:896-899`
**Issue:** The after-kill audit warning reuses the pre-kill `listeners` list (`_listeners_desc(listeners)`), so it asserts pids/ports that were killed without verifying they died. If a TTS process ignores SIGTERM, the audit trail still reads as a successful kill; only the downstream free-VRAM gate would catch it.
**Fix:** Call `find_tts_listeners()` again after `kill_tts` and record the residual set in the after-warning.

### IN-04: `--comfy-url` trailing slash produces `//prompt` paths; late `jsonschema` import unguarded

**File:** `analysis/roundtrip/h3_regen.py:996-997`, `734`
**Issue:** (a) `f"{comfy_url}/prompt"` with a user-supplied trailing slash yields `http://host:8188//prompt`, which typically 404s and degrades the whole run as `comfyui_unreachable` — confusing failure mode; normalize with `args.comfy_url.rstrip("/")`. (b) `from jsonschema import Draft202012Validator` sits inside `write_roundtrip_sidecar`; if the dep is missing, the batch renders fully and *then* dies with a raw ImportError before any sidecar write (cache survives, but the run's warnings/summary are lost).
**Fix:** Normalize the URL at parse time; move the import to a guarded top-level try or a fail-fast preflight check before the batch starts.

### IN-05: `rendered_at` is local time without timezone

**File:** `analysis/roundtrip/h3_regen.py:605`
**Issue:** `time.strftime("%Y-%m-%dT%H:%M:%S")` is naive local time; the repo's timestamp convention (schema `decided_at`, asset `generated_at`) is ISO-8601 UTC. Cache meta timestamps become ambiguous across DST/machines.
**Fix:** `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`.

### IN-06: fps=24 hardcoded in template duplicates the `FPS` constant

**File:** `analysis/roundtrip/workflow_fl2va.json:20` vs `analysis/roundtrip/h3_regen.py:154`
**Issue:** `CreateVideo` fps is a literal in the template; the module's `FPS` drives the length grid. Changing one without the other silently desynchronizes rendered duration from `duration_sec` metadata. (Same applies to steps/cfg, though those are re-asserted in `build_workflow:443-444` — fps is not.)
**Fix:** Inject `fps` into node 42 alongside the other locked values, or add a template-vs-constant assertion at load time.

### IN-07: Malformed `shots.json` entry crashes with raw KeyError, contradicting degrade posture

**File:** `analysis/roundtrip/h3_regen.py:302`
**Issue:** `int(s["id"])` raises `KeyError` if any shot lacks `id` — an uncaught traceback rather than the structured warning + skip used for missing prompts. Same for non-numeric `start_sec`/`end_sec` via `float()`.
**Fix:** Guard per-entry (skip + `[roundtrip]` str warning), mirroring the prompt-join handling directly above.

### IN-08: Exit code 0 on total failure

**File:** `analysis/roundtrip/h3_regen.py:1221`
**Issue:** `main()` returns 0 in every path, including "all attempted shots failed" and "guard blocked the entire batch". Documented as graceful-degrade, and warnings/summary do record it — but automation wrapping this client cannot distinguish "2 镜回收成功" from "全部失败" without parsing stdout.
**Fix:** Consider a non-zero (or at least distinguishable) exit when `rendered == 0 and cache_hits == 0 and (failed or skipped)`, keeping the engine-down degrade path at 0 as currently contracted.

---

_Reviewed: 2026-08-19T21:03:05Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
