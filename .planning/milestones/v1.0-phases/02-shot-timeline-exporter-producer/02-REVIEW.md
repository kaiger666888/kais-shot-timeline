---
phase: 02-shot-timeline-exporter-producer
reviewed: 2026-07-20T15:30:00Z
depth: standard
iteration: 1
files_reviewed: 4
files_reviewed_list:
  - scripts/export_asset.py
  - run_pipeline.py
  - scripts/serve.py
  - scripts/check_range.py
findings:
  critical: 0
  warning: 0
  info: 7
  total: 7
status: clean
---

# Phase 02: Code Review Report (Iteration 1 — post-fix re-review)

**Reviewed:** 2026-07-20T15:30:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** clean
**Iteration:** 1 (re-review after WR-01..WR-07 fixes from `02-REVIEW-FIX.md`)

## Summary

Re-reviewed Phase 2 source files after the iteration-1 fix run. All 7 prior Warnings (WR-01..WR-07) are **RESOLVED** with correct, well-documented fixes. The exporter now fails loud and early: data-file guards run before manifest build, schema validation runs before disk write, atomic write (`tmp` + `os.replace`) guarantees no partial manifest reaches consumers, symlinks validate their targets are regular files, ffprobe returncode is checked before stdout interpretation, the Range-206 self-check reaps its SIGKILL'd subprocess, and `step_export`'s cache is now TOCTOU-safe and keyed on a video-identity sidecar.

**No new Critical or Warning issues** were introduced by the fixes. The `.video-stamp` sidecar added by WR-07 is a benign artifact (gitignored under default `output/`, doesn't collide with anything in the schema, best-effort semantics are correct). The `.tmp` atomic-write scratch file is self-cleaning on next success and never visible to consumers.

**Additive-only invariant verified** via `git diff --stat 0901fbc..HEAD -- detectors/ audio/ html/` (empty) — Phase 2 touched only `run_pipeline.py` and the three `scripts/` files. Detection / separation / transcription / timeline logic untouched.

Per iteration-1 guidance, status is **`clean`**: all warnings resolved, no new Warning/Critical issues. Residual Info-level notes (carried over from the original review plus one new observation) are documented below but do not block ship.

## Verification of Prior Warnings

### WR-01 — Manifest written before canonical-path assert + schema validation → **RESOLVED**

`scripts/export_asset.py:279-313` reorders the (g)-(j) sequence exactly as the original fix suggestion recommended:

| Step | Line | Action |
|------|------|--------|
| (g) | 280 | `asset = build_asset_dict(work_dir, video)` |
| (g0) | 282-292 | duration_sec > 0 hard check (WR-03 fix) |
| (g') | 294-302 | Pre-write assert: 4 canonical paths resolve via `os.path.exists` |
| (i') | 304-306 | `validate_asset_json(asset)` — inline `Draft202012Validator` runs against in-memory dict |
| (h) | 308-313 | Atomic write: `tmp = output + ".tmp"` → `json.dump` → `os.replace(tmp, output)` |

If any of (g0), (g'), (i') fails, `sys.exit` fires before `os.replace`, so the on-disk `asset.json` (if any) is the previously-valid version. Verified by reading lines 279-313. **Clean.**

### WR-02 — Missing existence guards for 4 of 5 data files → **RESOLVED**

`scripts/export_asset.py:213-232` introduces a uniform guard loop:

```python
required_data = ("shots.json", "audio_analysis.json", "transcript.json",
                 "frames.json", "prompts.json")
for name in required_data:
    p = os.path.join(work_dir, name)
    if not os.path.exists(p):
        ...
        sys.exit(...)
```

Each missing file produces an actionable Chinese error citing the corresponding `data.<field>` schema requirement plus a context-appropriate hint (`prompts.json` → "独立步骤产出"; others → `--skip-*` diagnostic). All 5 schema-required files are now guarded. **Clean.**

### WR-03 — `duration_sec: 0` silently ships → **RESOLVED**

`scripts/export_asset.py:282-292` inserts a hard check between `build_asset_dict` and the pre-write assert:

```python
if not asset["source"]["duration_sec"]:
    sys.exit(f"无法确定视频时长：duration_sec=0\n  ...")
```

The low-level `_probe_duration` helper retains its swallow-and-return-0.0 behavior (correct — it's shared with the pipeline's internal use where 0 means "unknown"). Only the exporter path treats 0 as fatal. Schema's `minimum: 0` would have let 0 through; this hard check plugs the gap. **Clean.**

### WR-04 — ffprobe audio-stream check ignores returncode → **RESOLVED**

`scripts/export_asset.py:240-253` adds the returncode short-circuit exactly as the original fix suggested:

```python
r = subprocess.run(["ffprobe", ...], capture_output=True, text=True)
if r.returncode != 0:
    sys.exit(f"ffprobe failed (rc={r.returncode}): {video}\n"
             f"  stderr: {r.stderr.strip() or '(empty)'}")
if "audio" not in r.stdout:
    sys.exit(f"video has no audio stream: ...")
```

ffprobe-that-runs-but-fails (corrupt file, EACCES, etc.) now surfaces as a ffprobe failure with stderr, not a misleading "no audio stream" message. **Clean.**

### WR-05 — `ensure_symlink` accepts symlink-to-dir → **RESOLVED**

`scripts/export_asset.py:87-90` adds the target-type check at the top of `ensure_symlink`:

```python
if not os.path.isfile(target):
    raise FileNotFoundError(f"symlink target is not a regular file: {target}")
```

Uses `os.path.isfile` (follows symlink, then stat) — explicitly excludes dir / FIFO / device / socket. The check fires before any link-state inspection, so a misconfigured `--stems-source-dir` pointing at a directory tree containing `vocals.wav/` subdirs now fails loud at symlink creation, before the pre-write canonical-path assert (which would have falsely passed via `os.path.exists` on a dir). **Clean.**

### WR-06 — `proc.kill()` not followed by `proc.wait()` → **RESOLVED**

`scripts/check_range.py:104-118` adds a nested best-effort `wait` after `kill`:

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
            pass  # kernel reaps on parent exit
```

Zombie accumulation under Phase 4 regression loops is closed. Best-effort semantics (final timeout → pass) matches the documented kernel-reaps-on-parent-exit fallback. **Clean.**

### WR-07 — `step_export` TOCTOU + cache key ignores `--video` identity → **RESOLVED**

`run_pipeline.py:174-199` introduces two helpers and `step_export` (202-268) consumes both:

1. **TOCTOU fix** — `_safe_mtime(path)` (lines 174-184) single-shots `os.path.getmtime` inside a `try/except OSError`; missing input returns `+inf` to force cache miss. Replaces the old `exists` + `getmtime` two-step pattern.

2. **Cache-key fix** — `_video_identity(video)` (lines 187-199) fingerprints `path|size|mtime_ns` and writes it to the sidecar `<asset_json>.video-stamp`. The cache-hit predicate (lines 244-248) now ANDs:
   - `not force`
   - `os.path.exists(asset_json)`
   - `all_inputs_present` (no input is +inf)
   - `_safe_mtime(asset_json) > max_input_mtime`
   - `cached_video_id is not None`
   - `cached_video_id == current_video_id`

   Stale-manifest-on-`--video`-swap window is closed. `--force` cleanup loop (line 326) includes the sidecar. Sidecar write (lines 261-266) is best-effort: failure just means next run re-exports, which is correct fallback behavior. **Clean.**

## Residual Info Notes

These items do not block ship — Info-level only, classified honestly per iteration-1 guidance.

### IN-01: `.video-stamp` sidecar — placement, .gitignore coverage, and consumer visibility (new, from WR-07 fix)

**File:** `run_pipeline.py:234,261-266,326`
**Issue:** The WR-07 fix introduces a new sibling artifact `<asset_json>.video-stamp` next to `asset.json`. Verified characteristics:
- **`.gitignore` coverage:** `output/` is gitignored (`.gitignore:1`), so under default `--output-dir ./output` the sidecar is ignored. If a user runs `--output-dir examples/` (or any committed dir), the sidecar leaks into git. Low risk — only triggered by non-default invocation.
- **Consumer confusion:** `asset.schema.json` only governs the JSON document inside `asset.json`; it places no constraints on sibling files. A consumer listing the asset directory will see both `asset.json` and `asset.json.video-stamp`. The `asset.json.<suffix>` naming pattern is conventional (editor swap files, etc.) and unlikely to be parsed as a manifest. Acceptable.
- **Format contents:** Plain-text `path|size|mtime_ns` containing the absolute video path. If the asset directory is shipped to another machine, the path string reveals the producer's local filesystem layout. Not sensitive (no creds), but worth knowing.
- **Cleanup semantics:** If a user manually deletes `asset.json` but leaves the sidecar, the next run hits `os.path.exists(asset_json)` → False → cache miss → re-export → sidecar rewritten. Correct self-healing.

No fix required. If desired, an info print on first sidecar creation (e.g. `[export] wrote video-stamp sidecar`) would aid discoverability.

### IN-02: Atomic-write `.tmp` leftover on `json.dump` failure (new, from WR-01 fix)

**File:** `scripts/export_asset.py:310-313`
**Issue:** The atomic write sequence is:
```python
tmp = output + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(asset, f, indent=2, ensure_ascii=False)
os.replace(tmp, output)
```
If `json.dump` raises (disk full, EIO), `tmp` lingers on disk. `with` closes the file but does not unlink. Self-cleaning on next successful run (`open(tmp, "w")` truncates). If user gives up, `.tmp` lingers forever as a sibling to `asset.json`. Benign — consumers read `asset.json`, not `.tmp`. No schema concern. The old `asset.json` (if any) is untouched because `os.replace` never fires.

No fix required. If hardened, wrap in `try/except: os.unlink(tmp); raise` — but the failure mode is benign enough that the current code is acceptable.

### IN-03: `--force` removes `asset.json` before validation — failure leaves no manifest (new side-effect of WR-01 ordering)

**File:** `scripts/export_asset.py:275-277`
**Issue:** Pre-existing characteristic, not a regression: `if args.force and os.path.exists(output): os.unlink(output)` runs at step (f), before validation. If validation at step (i') fails, the previous (valid) `asset.json` is already gone. Without `--force`, the old `asset.json` survives (correct). The `--force` path is "user asked for it" — acceptable but worth noting. Not introduced by the fixes.

No fix required. Documenting for completeness.

### IN-04: `_Partial` class defined inside `send_head` (carried from prior IN-01)

**File:** `scripts/serve.py:84-102`
**Issue:** `_Partial` is re-declared on every request (rebuilt class object). Pre-existing, not a Phase 2 regression. Negligible perf impact at dev-server scale.
**Fix (optional):** Move `class _Partial:` to module scope.

### IN-05: `serve.py` binds to `0.0.0.0` by default (carried from prior IN-02)

**File:** `scripts/serve.py:116`
**Issue:** `ThreadingHTTPServer(("0.0.0.0", port), ...)` exposes dev server to LAN. Pre-existing. CLAUDE.md describes the tool as "one-shot local analysis" — `127.0.0.1` would be safer default; `0.0.0.0` could be opt-in via `--bind` flag.
**Fix (optional):** Default bind to `127.0.0.1`; add `--bind 0.0.0.0` opt-in.

### IN-06: `--force` passthrough from `run_pipeline.py` to `export_asset.py` is redundant (carried from prior IN-03)

**File:** `run_pipeline.py:323-329` → `scripts/export_asset.py:275-277`
**Issue:** Top-level `--force` already unlinks `asset.json` (and now the `.video-stamp` sidecar) at line 325-326 of run_pipeline.py. Then `step_export` passes `--force` to `export_asset.py`, which re-checks `if args.force and os.path.exists(output)` — but `output` is already gone, so it's a no-op. No bug; redundancy only.
**Fix (optional):** Drop the `--force` passthrough (export_asset.py's idempotent symlink logic handles reuse correctly without it).

### IN-07: `step_export` always prints `asset: {asset_json}` regardless of skip (carried from prior IN-04)

**File:** `run_pipeline.py:362`
**Issue:** After `step_export(...)`, `main()` unconditionally prints `f"       asset: {asset_json}"`. If user passed `--skip-export`, this advertises a path that has no file. Cosmetic only.
**Fix (optional):** Guard on `os.path.exists(asset_json)` or capture `step_export`'s return value.

---

## Verification Artifacts

| Check | Tool | Result |
|-------|------|--------|
| All 7 warnings resolved | Line-by-line re-read of cited fix locations | PASS (7/7) |
| Additive-only invariant | `git diff --stat 0901fbc..HEAD -- detectors/ audio/ html/` | PASS (empty diff) |
| Schema conformance | Cross-check exporter outputs vs `asset.schema.json` patterns | PASS (literal strings `stems/vocals.wav`, `video.mp4`, `shots.json` etc. all match regexes; `duration_sec` is `number`-typed) |
| Fixer self-verification | `02-REVIEW-FIX.md` Tier 1-3 matrix (help / export / fail fixture / range / cache) | PASS (per fixer report) |
| No new Critical/Warning introduced | Full re-read of all 4 in-scope files | PASS |

---

_Reviewed: 2026-07-20T15:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 1_
