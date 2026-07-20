---
phase: 02-shot-timeline-exporter-producer
reviewed: 2026-07-20T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - scripts/export_asset.py
  - run_pipeline.py
  - scripts/serve.py
  - scripts/check_range.py
findings:
  critical: 0
  warning: 7
  info: 6
  total: 13
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 2 introduces an additive export layer (`scripts/export_asset.py` + `scripts/check_range.py`) on top of the validated video-decomposition pipeline, wires it into `run_pipeline.py` as step 6/6, and ships a focused FD-leak fix in `scripts/serve.py` (`_Partial.close()`).

**Strengths confirmed by adversarial review:**
- The `_Partial.close()` FD-leak fix in `serve.py` is **correct and minimal**. CPython's `BaseHTTPRequestHandler.do_GET` and `do_HEAD` both call `f.close()` in a `finally` block (verified by inspecting CPython source). The 206 path returns a `_Partial` instance, so without `close()` the underlying file object leaks one FD per Range request. The new `close()` method calls `self._f.close()` exactly once, and file `close()` is idempotent under double-call. The 200 / 416 / NOT_FOUND paths were already correct and are not regressed.
- Inline `Draft202012Validator` validation is **correctly wired**: schema `$schema` matches validator class, schema is loaded from the canonical repo path, errors are surfaced via `sys.exit` (fails loud). Cross-checked: the schema rejects `bass` in `media.stems` (additionalProperties:false), rejects `../` in data paths, accepts the literal strings the exporter writes.
- `run_pipeline.py` diff is **purely additive** (verified via `git diff 0901fbc..HEAD`): `[N/5]` → `[N/6]` numbering, new `step_export`, new `--skip-export` flag, `asset.json` added to the `--force` clear loop. Detection / separation / transcription / timeline logic untouched.
- `--force` clears `asset.json` (run_pipeline.py:264); `ensure_symlink` idempotency handles stale symlinks on `--video` changes.

**Primary concerns:** The exporter can persist an **invalid manifest to disk before its own sanity checks fire** (WR-01), and existence guards are **inconsistent** — only `prompts.json` is explicitly guarded out of 5 required data files (WR-02). Both create windows where a schema-valid but semantically-broken `asset.json` reaches downstream consumers. The remaining findings are robustness / hygiene gaps (silent failure modes, misleading errors, zombie reaping).

No Critical issues were found. The implementation is fundamentally sound; the Warnings below should be addressed before this code ships to a downstream consumer.

## Critical Issues

_No critical issues found._

## Warnings

### WR-01: Manifest written to disk BEFORE post-write canonical-path assert and schema validation

**File:** `scripts/export_asset.py:255-265`
**Issue:**
The exporter executes its steps in this order:
1. (e) Create 4 canonical symlinks — `os.symlink` does **not** require the target to exist, so broken symlinks are silently created when Demucs output is missing.
2. (h) `json.dump(asset, f, ...)` writes `asset.json` to disk.
3. (i) `validate_asset_json(asset)` runs inline schema validation against the in-memory dict.
4. (j) Post-write assert that the 4 canonical paths actually resolve (`os.path.exists` follows symlinks → False for broken targets).

If step (j) fails, the script `sys.exit`s non-zero — but `asset.json` is **already on disk** referencing the broken canonical paths. The schema (step i) only validates that path strings match a regex; it does not verify file existence, so an invalid manifest persists. A downstream consumer subsequently loading `asset.json` sees a schema-valid document pointing at non-existent media.

The same concern applies to step (i) itself: if `build_asset_dict` produced something schema-invalid (e.g., user hand-edited `transcript.json` to put a string in `duration`), `json.dump` writes the invalid manifest to disk before `validate_asset_json` catches it.

**Fix:** Reorder so validation and existence checks happen **before** the write, or write atomically (temp file + rename on success):

```python
# (g) Build manifest
asset = build_asset_dict(work_dir, video)

# (g') Pre-write assert: canonical paths must resolve (symlinks must not be dangling)
for rel in ("video.mp4", "stems/vocals.wav", "stems/drums.wav", "stems/other.wav"):
    p = os.path.join(work_dir, rel)
    if not os.path.exists(p):
        sys.exit(f"canonical path missing before write: {rel} (expected at {p})")

# (i') Validate the in-memory dict BEFORE persisting
validate_asset_json(asset)

# (h) Atomic write
tmp = output + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(asset, f, indent=2, ensure_ascii=False)
os.replace(tmp, output)
```

---

### WR-02: Missing existence guards for 3 of 5 data files (inconsistent with prompts.json guard)

**File:** `scripts/export_asset.py:204-211`
**Issue:**
The exporter's docstring (lines 22) and code single out `prompts.json` for an explicit existence guard (`sys.exit` with actionable Chinese error). The rationale given is "schema required" — but **all 5 data files are schema-required** (`asset.schema.json:61`: `required: ["shots", "audio_analysis", "transcript", "frames", "prompts"]`).

Existence coverage today:
- `prompts.json` — explicit guard at line 206-211 (clean `sys.exit`)
- `transcript.json` — implicit guard via `build_asset_dict` reading it (line 136); failure mode is an uncaught `FileNotFoundError` traceback (ugly but loud)
- `video` — explicit guard at line 214-215
- `shots.json` — **not checked**
- `audio_analysis.json` — **not checked**
- `frames.json` — **not checked**

Trigger: `python run_pipeline.py --video X.mp4 --skip-separate --skip-export` followed by `python run_pipeline.py --video X.mp4` (without `--skip-export`) — the cached `audio_analysis.json` is missing because step_separate was skipped, but the exporter happily writes a manifest referencing it. Schema validation passes (paths are string literals). Consumer breaks at render time.

**Fix:** Add a uniform existence guard loop before any manifest work:

```python
required_data = ("shots.json", "audio_analysis.json", "transcript.json",
                 "frames.json", "prompts.json")
for name in required_data:
    p = os.path.join(work_dir, name)
    if not os.path.exists(p):
        sys.exit(
            f"{name} 不存在: {p}\n"
            f"  asset.schema.json 的 data.{name.removesuffix('.json')} 是 required 字段。\n"
            f"  若是用 --skip-* 跳过了对应步骤，请先就位再运行导出。")
```

---

### WR-03: `_probe_duration` returns 0.0 silently — manifest ships with `duration_sec: 0`

**File:** `scripts/export_asset.py:46-57` (mirror at `run_pipeline.py:54-61`)
**Issue:**
`_probe_duration` swallows `(ValueError, AttributeError)` and returns `0.0` on any ffprobe failure (missing binary, unreadable file, malformed stdout). The schema only constrains `duration_sec` with `minimum: 0` (verified by feeding `duration_sec: 0` through `Draft202012Validator` — accepted). Combined with the exporter's fallback chain `transcript.duration → _probe_duration`, a missing `duration` field in `transcript.json` plus any ffprobe hiccup produces a manifest with `duration_sec: 0`, which is schema-valid but semantically broken.

The project convention (per CLAUDE.md) is that `probe_duration` returning 0.0 is "intentional — treated as unknown rather than fatal" for the **pipeline's internal use**. But for an **exported manifest consumed by external systems**, silent 0 is the wrong failure mode — it should fail loud or omit the field.

**Fix:** For the exporter path specifically, treat 0.0 as a failure:

```python
duration = transcript.get("duration")
if not duration:
    duration = _probe_duration(video_path)
if not duration:
    sys.exit(
        f"无法确定视频时长: transcript.json 无 duration 字段且 ffprobe 失败。\n"
        f"  video={video}\n"
        f"  duration_sec 是 asset.schema.json 的 required 字段，不可为 0。")
```

---

### WR-04: ffprobe audio-stream check ignores returncode — misleading error on ffprobe failure

**File:** `scripts/export_asset.py:219-225`
**Issue:**
```python
r = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
     "-of", "csv=p=0", video], capture_output=True, text=True)
if "audio" not in r.stdout:
    sys.exit(f"video has no audio stream: {video}\n"
             f"  (h264.mp4 transcode was -an stripped — exporter needs original)")
```
If ffprobe fails (returns non-zero with empty stdout — e.g., corrupt video, permission denied, ffprobe not on PATH but caught by some shell fallback), `r.stdout` is empty, the check fires, and the user sees "video has no audio stream" — which is misleading: the actual failure is "ffprobe did not run successfully". The error message leads the user down the wrong debugging path (looking at transcode `-an` logic when the real issue is ffprobe).

Note: if ffprobe is entirely missing, `subprocess.run` raises `FileNotFoundError` (loud, OK). The gap is ffprobe-that-runs-but-fails.

**Fix:** Check returncode and capture stderr:

```python
r = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
     "-of", "csv=p=0", video], capture_output=True, text=True)
if r.returncode != 0:
    sys.exit(
        f"ffprobe failed (rc={r.returncode}): {video}\n"
        f"  stderr: {r.stderr.strip() or '(empty)'}")
if "audio" not in r.stdout:
    sys.exit(f"video has no audio stream: {video}\n"
             f"  (h264.mp4 transcode was -an stripped — exporter needs original)")
```

---

### WR-05: `ensure_symlink` doesn't validate target is a regular file — symlink-to-dir passes post-write assert

**File:** `scripts/export_asset.py:71-94` (function), `71-94:262-265` (post-write assert consumer)
**Issue:**
`ensure_symlink(link_path, target)` checks: link_path is symlink? readlink matches? link_path exists as non-symlink? Then calls `os.symlink(target, link_path)`. It never validates that `target` itself is a regular file. The post-write assert uses `os.path.exists(p)` which returns True for symlinks resolving to directories.

Failure mode: if `--stems-source-dir` is misconfigured to point at a directory containing subdirectories named `vocals.wav/`, `drums.wav/`, etc. (unlikely but possible), the symlinks would point at directories. Schema validation passes (paths are strings matching the pattern). Post-write assert passes (`os.path.exists` → True for dir). Manifest ships. Consumer tries to open `stems/vocals.wav` as a WAV and fails with a confusing error.

**Fix:** Add target file-type validation in `ensure_symlink`:

```python
def ensure_symlink(link_path: str, target: str) -> None:
    if not os.path.isfile(target):
        raise FileNotFoundError(
            f"symlink target is not a regular file: {target}")
    # ... existing logic
```

(Using `os.path.isfile` rather than `os.path.exists` because we specifically want to reject directories, FIFOs, devices, etc.)

---

### WR-06: `check_range.py` `proc.kill()` not followed by `proc.wait()` — zombie process until parent exits

**File:** `scripts/check_range.py:104-110`
**Issue:**
```python
finally:
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        # ← no proc.wait() here
```
After `proc.kill()` (SIGKILL), the serve.py process becomes a zombie on Linux until the parent reaps it via `wait()`. Python's `subprocess.Popen.__del__` eventually reaps it on GC, but in a long-running harness (Phase 4 regression suite invocations of `check_range.check()` from a loop), zombies accumulate. The same pattern would also leak the process if `proc.kill()` itself raises (rare but possible on EPERM).

**Fix:** Add a final `wait()` after kill, and wrap each cleanup step defensively:

```python
finally:
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass  # best-effort; kernel will reap on parent exit
```

---

### WR-07: `step_export` mtime cache has a TOCTOU on input files; cache key ignores `--video` identity

**File:** `run_pipeline.py:185-199`
**Issue:**
Two related concerns with the cache check:

1. **TOCTOU on input files**: The code does `inputs_exist = [p for p in inputs if os.path.exists(p)]` and then `os.path.getmtime(p) for p in inputs_exist`. Between the `exists` check and `getmtime` call, another process (or the user) could delete the file. `getmtime` then raises `FileNotFoundError`, which propagates as an uncaught traceback. Low probability but a real robustness gap — the same pattern exists in `step_timeline` (pre-existing), so this is consistent with project conventions but worth noting.

2. **Cache key ignores `--video` identity**: The cache hit condition is "asset.json mtime > max(existing input mtimes)". The inputs include the video path, so a different `--video` with newer mtime triggers cache miss. But if the user passes a different video file with **older or equal mtime** (e.g., restored from backup with original timestamps), the cache hit fires and a stale manifest (referencing the old video filename) is returned.

**Fix (TOCTOU):** Wrap getmtime in try/except:

```python
def _safe_mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return float("inf")  # treat missing as +inf → force cache miss
```

**Fix (cache key):** If preserving cache semantics, document the limitation. Alternatively, hash the video path into a sidecar stamp file.

---

## Info

### IN-01: `_Partial` class defined inside `send_head` (recreated per request)

**File:** `scripts/serve.py:84-102`
**Issue:** The `_Partial` class is declared inside `send_head`, so Python rebuilds the class object on every request. Pre-existing (Phase 2 only added the `close()` method, did not introduce this pattern). Negligible perf impact at dev-server scale, but moving `_Partial` to module scope would be cleaner.
**Fix:** Move `class _Partial:` to module level (outside `RangeRequestHandler.send_head`).

---

### IN-02: `serve.py` binds to `0.0.0.0` by default — serves files to entire network

**File:** `scripts/serve.py:116`
**Issue:** `ThreadingHTTPServer(("0.0.0.0", port), ...)` exposes the dev server (and any asset under cwd, including future exports with potentially sensitive filenames) to anything on the LAN. Pre-existing (not a Phase 2 regression). For a tool whose own CLAUDE.md describes it as "one-shot local analysis", `127.0.0.1` would be a safer default; `0.0.0.0` could be opt-in via a `--bind` flag.
**Fix:** Default bind to `127.0.0.1`; add `--bind 0.0.0.0` opt-in for users who need LAN exposure.

---

### IN-03: `--force` pass-through from `run_pipeline.py` to `export_asset.py` is redundant

**File:** `run_pipeline.py:205-206` → `export_asset.py:192,248-249`
**Issue:** Top-level `--force` in `run_pipeline.py` already unlinks `asset.json` at line 264. Then `step_export` passes `--force` to `export_asset.py`, whose `--force` handler (line 248-249) checks `if args.force and os.path.exists(output): os.unlink(output)` — but `output` was already unlinked, so this is a no-op. No bug; just redundancy worth noting. The behavior is correct either way.
**Fix:** No action required. If cleaning up, drop the `--force` passthrough (export_asset.py's idempotent symlink logic handles reuse correctly without it).

---

### IN-04: `step_export` always prints "asset: {asset_json}" regardless of skip

**File:** `run_pipeline.py:300`
**Issue:** After `step_export(...)`, `main()` unconditionally prints `f"       asset: {asset_json}"`. If the user passed `--skip-export` and `asset.json` doesn't exist, this is misleading — it advertises a path that has no file. Cosmetic only.
**Fix:** Guard on whether `asset_json` exists, or capture `step_export`'s return value:

```python
if os.path.exists(asset_json):
    print(f"       asset: {asset_json}")
else:
    print(f"       asset: (skipped — run without --skip-export to generate)")
```

---

### IN-05: `_Partial.read(_n=None)` ignores the requested read length

**File:** `scripts/serve.py:92-98`
**Issue:** The method signature accepts `_n` (the requested read length from `copyfileobj`) but ignores it, always reading `min(self._chunk_size, self._remaining)`. Today `http.client.copyfileobj` loops on short reads, so behavior is correct. But the file-like API contract is that `read(n)` returns at most `n` bytes — a future Python version or subclass using a different copy strategy could pass a smaller `n` (e.g., for write-rate throttling) and get more bytes than requested, breaking the contract. Pre-existing pattern.
**Fix:** Honor `_n`:

```python
def read(self, n=None):
    if self._remaining <= 0:
        return b""
    if n is None:
        n = self._chunk_size
    n = min(n, self._chunk_size, self._remaining)
    data = self._f.read(n)
    self._remaining -= len(data)
    return data
```

---

### IN-06: `check_range.py` `find_free_port` has inherent TOCTOU

**File:** `scripts/check_range.py:32-36`
**Issue:** `find_free_port` binds a socket to `:0`, reads the assigned port via `getsockname()`, then closes the socket (end of `with` block). The port is now "free" from the kernel's perspective, but another process could grab it in the window between the socket close and serve.py's bind. Standard practice for ephemeral port allocation (the same pattern is used in `multiprocessing`, `pytest` fixtures, etc.); the risk is low and the failure mode (serve.py fails to bind, `wait_ready` times out, script exits 1 with a clear message) is acceptable.
**Fix:** No action — the failure mode is loud and the message is actionable.

---

_Reviewed: 2026-07-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
