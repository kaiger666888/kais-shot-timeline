---
phase: 04-cross-repo-contract-verification
reviewed: 2026-07-21T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - scripts/verify_contract.py
findings:
  critical: 0
  warning: 0
  info: 5
  total: 5
status: clean
iteration: 2
previous_findings:
  critical: 2
  warning: 8
  info: 5
  total: 15
---

# Phase 4: Code Review Report (Re-Review, Iteration 2)

**Reviewed:** 2026-07-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 1 (`scripts/verify_contract.py`, 791 lines)
**Status:** clean
**Previous iteration:** 2 BLOCKERs + 8 WARNINGs (5 INFO intentionally deferred)

## Summary

Iteration 1 fix report (`04-REVIEW-FIX.md`) claimed all 10 in-scope findings (CR-01/02 + WR-01..08) applied cleanly across 10 dedicated commits (`4f20d1f` through `44e65cd`). This re-review **independently verifies** those claims by tracing each fix against its original failure mode, then probes the +141/-46 diff for newly-introduced regressions.

**Verdict:** Both BLOCKERs are genuinely resolved. All 8 WARNINGs are genuinely resolved. No newly-introduced BLOCKER or WARNING issues. The 5 IN-* info findings remain present (correctly deferred per `fix_scope = critical_warning`). Status: **clean**.

What was specifically probed (per task instructions):

1. **CR-01 negative path** — `validate_six_shapes` no longer raises uncaught `KeyError`/`TypeError` when `manifest["data"]` is missing, null, or non-dict, or when an individual `data.<shape>` value is null/non-string. The `.get()` + `isinstance` guard chain degrades cleanly and the asset-shape iteration reports the missing-required error via normal `Draft202012Validator.iter_errors`. No false negatives on well-formed manifests (traced 7 manifest shapes — all correct).
2. **CR-02 process-group teardown** — `pgid = proc.pid` is cached at `Popen` time, SIGKILL is now **unconditional** in the outer `finally` (not gated on `TimeoutExpired`), and the `if pgid is not None` guard makes the teardown safe against a Popen that itself fails. The cached-pgid approach eliminates the `getpgid(reaped_pid)` TOCTOU. Process-group isolation is preserved (`start_new_session=True` ⇒ `pgid == proc.pid` for the life of the group; unrelated groups untouched).
3. **No regressions** in the +141/-46 diff: SQL still parameterized (no injection), subprocess still list-form (no shell), no new debug artifacts, all 4 `args.asset_dir` reference sites updated, all 4 flag/env forms work via alias.

## Resolution Matrix (Iteration 1 → Iteration 2)

| ID | Original severity | Original failure mode | Fix location | Verified resolution |
|----|------|----------------------|--------------|---------------------|
| CR-01 | BLOCKER | `manifest["data"][shape]` raised `KeyError` on missing `data`, masking schema errors with a traceback | `scripts/verify_contract.py:210-215, 222-229` | `data_field = manifest.get("data") if isinstance(manifest, dict) else None` then `if not isinstance(data_field, dict): data_field = {}`. Per-shape access uses `data_field.get(shape)` + `isinstance(rel, str)` guard. Missing-required errors flow through the existing asset-shape iter; only "key present but non-string" (a case schema cannot catch) is recorded on the data side. **RESOLVED.** |
| CR-02 | BLOCKER | SIGKILL escalation only fired on `TimeoutExpired`; `os.getpgid(proc.pid)` raced with reaping | `scripts/verify_contract.py:511-527, 619-651` | `pgid = proc.pid` cached immediately after `Popen(..., start_new_session=True)` (POSIX guarantee: pgid == pid for group lifetime). `os.killpg(pgid, SIGKILL)` is now unconditional in `finally` after a bounded `proc.wait(timeout=10)`. Both `(ProcessLookupError, PermissionError)` guards retained. `if pgid is not None` skips teardown-a cleanly when Popen fails. **RESOLVED.** |
| WR-01 | WARNING | `_poll_health` ignored `proc.poll()`, wasted up to 45s on a dead backend | `scripts/verify_contract.py:91-122, 528-531` | Signature changed to `(port, proc, timeout)` returning `tuple[bool, str]`. Each iteration checks `proc.poll()` first; returns `(False, "backend died before /health (exit code=N)")` immediately. Caller embeds `reason` in failure message. **RESOLVED.** |
| WR-02 | WARNING | `_poll_health` exception coverage too narrow; `HTTPException` / `ConnectionResetError` escaped the loop | `scripts/verify_contract.py:42, 119` | `import http.client` at module top; except broadened to `(urllib.error.URLError, OSError, http.client.HTTPException)`. Half-booted Express malformed-HTTP no longer crashes e2e with a traceback. **RESOLVED.** |
| WR-03 | WARNING | `Popen` outside `try/finally` — orphan window between Popen and try | `scripts/verify_contract.py:506-527, 619, 632` | `pid`/`eid`/`db_path` hoisted before Popen (they don't depend on proc). `proc = None; pgid = None` initialized pre-try. `try:` immediately precedes Popen. Finally guards teardown-a with `if pgid is not None`; teardown-b/c still run even if Popen raised. **RESOLVED.** |
| WR-04 | WARNING | `_resolve_canonical_video` returned raw relative symlink target — resolved against Python CWD, not `asset_dir` | `scripts/verify_contract.py:152-174` | After `os.readlink`, branch on `os.path.isabs(target)`: relative targets resolved via `(asset_dir / target).resolve()`; absolute targets passed through `os.path.realpath` to canonicalize embedded `..`. **RESOLVED.** |
| WR-05 | WARNING | `run_self_test` `shutil.copy2` crashed on `subdir/foo.json` data paths | `scripts/verify_contract.py:404-412` | `dst = temp_dir / rel; dst.parent.mkdir(parents=True, exist_ok=True)` before `shutil.copy2`. Schema pattern permits one-or-more directory segments; future producers emitting `subdir/shots.json` no longer crash. **RESOLVED.** |
| WR-06 | WARNING | `--mode=e2e --e2e-skip` silently exited 0 | `scripts/verify_contract.py:730-736` | Argparse-time guard: if both set, `sys.exit("[verify-contract] --mode=e2e 与 --e2e-skip 冲突 ...")` (exits 1 with stderr message). `--mode=all --e2e-skip` (legitimate "all-minus-e2e") still works. **RESOLVED.** |
| WR-07 | WARNING | `--e2e-asset-dir` / `PHASE4_E2E_ASSET_DIR` misnamed — also used by producer and self-test | `scripts/verify_contract.py:714-723` | Flag renamed to `--asset-dir` (dest=`asset_dir`) with `--e2e-asset-dir` argparse alias. Env preference: `PHASE4_ASSET_DIR` first, `PHASE4_E2E_ASSET_DIR` back-compat fallback. Help text documents the dual scope. All 4 reference sites (`262, 389, 489` + error messages) updated to `args.asset_dir`. **RESOLVED.** |
| WR-08 | WARNING | SQL cleanup one transaction — second DELETE failure rolled back the first | `scripts/verify_contract.py:671-695` | Restructured into `for sql in (...)` loop; each DELETE in its own `try/except sqlite3.Error` calling `conn.commit()` immediately after `cur.execute()`. First DELETE commits durably; second DELETE failure writes `[e2e] WARNING` to stderr only. Outer `try/except sqlite3.Error` guards `sqlite3.connect` failure. **RESOLVED.** |

## Cross-Verification of Pre-Existing Strengths (still intact)

These properties were called out as clean in iteration 1 and were re-verified after the +141/-46 diff to ensure no regression:

- **No SQL injection** — every `cur.execute` uses `?` placeholders (`scripts/verify_contract.py:138-142, 675-680, 682`). `pid`/`eid` are bound as `str(pid)`/`str(eid)` parameters, never interpolated.
- **No shell injection** — every `subprocess.run`/`Popen` uses list-form args; no `shell=True` anywhere in the file.
- **Subprocess list-form with CJK paths** — `workdir: str(asset_dir)` flows through `json.dumps(...).encode("utf-8")` body bytes, never through a shell (`scripts/verify_contract.py:536-547`).
- **`Draft202012Validator` use preserved** — still inline (never delegates to `spec/validate.py`'s `SMOKE_SHAPES`-filtered path) at `scripts/verify_contract.py:188-194, 239-242`.
- **Self-test try/finally cleanup** — `shutil.rmtree(temp_dir, ignore_errors=True)` at `scripts/verify_contract.py:440-442` still genuine; real `output/` bytes never mutated (copies only).
- **No hardcoded secrets, no `eval`/`exec`, no debug artifacts** — grep confirms only one `console.log` match in the file and it is inside a comment string describing backend logging semantics (`scripts/verify_contract.py:514`).

## Targeted Edge-Case Probes (newly-introduced issues check)

Per task instruction "Check for newly-introduced issues from the fixes," the following adversarial probes were performed. **None surfaced a defect.**

### Probe 1: Does unconditional SIGKILL endanger unrelated process groups?

**Concern:** Caching `pgid` and firing `SIGKILL` unconditionally might hit a recycled PID or an unrelated group.

**Result:** Safe. `start_new_session=True` calls `setsid()` in the child before `exec`, making the child both session leader and process-group leader with `pgid == child.pid`. All descendants (npx's `node`, tsx workers) inherit this pgid unless they explicitly call `setpgid`/`setsid` — standard Node.js does not. `os.killpg(pgid, sig)` only signals processes whose group membership equals `pgid`, which is precisely our descendant tree. The Python parent and any unrelated processes are in different groups. PID recycling within the microsecond window between `proc.wait()` returning and `os.killpg()` firing is theoretically possible but vanishingly unlikely, and the `(ProcessLookupError, PermissionError)` catch covers the "group already empty" case. **No defect.**

### Probe 2: Does the defensive `data_field` access produce false negatives on well-formed manifests?

**Concern:** The new `.get()` + `isinstance` guard chain might silently skip valid shapes.

**Result:** No false negatives. Traced 7 manifest shapes:
- Well-formed (`data` is a dict, all 5 shape keys present as strings) → `data_field = manifest["data"]` (real dict), each `data_field.get(shape)` returns the string path, `isinstance(rel, str)` True, schema validation runs normally.
- `data` missing entirely → `data_field = {}`, asset-shape iter reports `"data is required"`, data-side loop `continue`s cleanly.
- `data = None` → `data_field = None` → degraded to `{}`, same path.
- `data = "string"` → `data_field = "string"` → `isinstance` False → degraded to `{}`.
- `manifest` itself not a dict (e.g., parsed JSON array) → `isinstance(manifest, dict)` False → `data_field = None` → `{}`. Asset-shape iter catches "manifest is not of type object".
- `data.shots = None` (key present, null value) → `rel = None`, `isinstance(rel, str)` False, `"shots" in data_field` True → records `"shots: data.shots is not a string: None"` (schema cannot catch this; harness-level correct).
- `data.shots = "subdir/foo.json"` and file exists → loads and validates normally.

**No defect.** The defensive code only relaxes the *crash path*; the *validation path* is unchanged.

### Probe 3: Does WR-03's `try: Popen` restructure accidentally drop teardown on a Popen failure?

**Concern:** `Popen` inside try, but `proc.wait` etc. expected `proc` non-None.

**Result:** Correct. `proc = None; pgid = None` initialized pre-try (`scripts/verify_contract.py:511-512`). If `subprocess.Popen` raises (e.g., FileNotFoundError if `npx` not on PATH), the finally block sees `pgid is None`, skips teardown-a (the `os.killpg` block at lines 632-651 is gated by `if pgid is not None`). Teardown-b (git reconcile, line 654-662) and teardown-c (SQL DELETE, lines 671-695) don't depend on `proc` and still run. **No orphan leak.**

### Probe 4: Are there asymmetric error-handling gaps introduced by the WR-01/02 changes?

**Concern:** `_poll_health` now returns `tuple`; old callers might still expect bool.

**Result:** Only one caller (`run_e2e_check:529`) and it unpacks `ok, reason = _poll_health(...)`. No other call sites. **No defect.**

### Probe 5: Did the WR-07 rename leave any reference site stale?

**Concern:** Renaming `--e2e-asset-dir` to `--asset-dir` could have missed a caller.

**Result:** `grep -n "args\.e2e_asset_dir"` returns zero hits. All four access sites (`262, 389, 489` + error message at `494`) use `args.asset_dir`. `grep -n "PHASE4_E2E_ASSET_DIR"` returns four hits, all in back-compat contexts (docstring `28, 254`; env-fallback `718`; help text `721`). **No defect.**

### Probe 6: Does the WR-08 per-DELETE commit interact badly with sqlite3 transaction state?

**Concern:** A failed `cur.execute` could leave the connection in an aborted transaction state, causing the next iteration to fail spuriously.

**Result:** The code orders the most-likely-to-succeed DELETE (`o_agentWorkData`, the main consumer table) first and the most-likely-to-fail DELETE (`kv_canvasEvent`, susceptible to consumer schema drift) second. The fixer's smoke test (`04-REVIEW-FIX.md` verification matrix row "WR-08 smoke") confirms the documented scenario works: first DELETE commits, second warns. If the *first* DELETE were to fail (catastrophic consumer schema drift), both would fail — but that scenario indicates a broken consumer DB where partial cleanup is the least concern. Theoretical concern only; **no practical defect.**

## Residual Info Findings (deferred per fix_scope)

The 5 IN-* info findings from iteration 1 remain present in the code. This is **correct and acceptable** — `fix_scope = critical_warning` per the fixer task, so info-level findings were intentionally not addressed. They are listed here for downstream visibility (no action required for status=clean).

### IN-01 (residual): Function-level `import signal as _signal` inside teardown

**File:** `scripts/verify_contract.py:631`
**Issue:** `import signal as _signal` runs inside the `finally` block on every teardown. Cheap (cached after first import) but unconventional; the project convention is top-level imports. The `_signal` alias is also unnecessary — no top-level `signal` name collides.
**Fix (optional):** Move `import signal` to the top-level import block (after `import socket` on line 46) and drop the underscore alias.

### IN-02 (residual): `DEFAULT_CONSUMER_PATH` hardcoded to a specific machine path

**File:** `scripts/verify_contract.py:65`
**Issue:** `DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"` only exists on the primary dev machine. Mirrored checkout at `/home/kai/workspace/kais-shot-timeline` and any CI/collaborator machine will see "CANVAS_CONSUMER_PATH 不存在" until they set the env var. Acceptable as a default (overridable), but friction-reducing fallback would help.
**Fix (optional):** Add a secondary fallback probing `Path(REPO).parent / "kst-canvas-consumer"` before giving up.

### IN-03 (residual): Self-test covers only one drift scenario

**File:** `scripts/verify_contract.py:414-439`
**Issue:** The self-test injects exactly one corruption (`schema_version="v1"`) and proves the harness detects it. Other corruption shapes (missing required field, wrong `asset_type` const, additional property, media path traversal, missing `data` field) are not exercised. Extending to a DRIFTS table would have caught CR-01 at self-test time and provides defense against future regressions in `validate_six_shapes`.
**Fix (optional):** Iterate a small table of corruptions, assert each produces ≥1 error.

### IN-04 (residual): Dead `r.status != 200` check

**File:** `scripts/verify_contract.py:551`
**Issue:** `urllib.request.urlopen` raises `HTTPError` for any non-2xx response, so inside the `with` block `r.status` is always 2xx. The `if r.status != 200` branch can never execute as written; if the API ever returns 201 Created on success, the harness would incorrectly report failure despite `urlopen` succeeding.
**Fix (optional):** Drop the check (urlopen guarantees 2xx), or document as belt-and-suspenders and broaden to `r.status < 200 or r.status >= 300`.

### IN-05 (residual): Producer mode validates JSON shapes but not media file existence

**File:** `scripts/verify_contract.py:197-246`
**Issue:** The 6-schema inline validator checks that `media.video` and `media.stems.{vocals,drums,other}` are strings matching a path pattern, but does not check that those files exist on disk relative to `asset_dir`. A producer bug writing a valid-looking manifest pointing at a missing `video.mp4` would pass producer mode and only fail downstream (e2e import or consumer rendering).
**Fix (optional):** After schema validation passes, add a follow-up pass checking `(asset_dir / media_rel).is_file()` for each media path.

## Out-of-Scope Observations (no action needed, documented for completeness)

These are **not** findings — they are pre-existing patterns noted during cross-verification that predate iteration 1 and were not introduced by the fix diff. They are documented here to prevent re-flagging in future iterations.

1. **`urllib.error.URLError` (non-HTTP) is uncaught in the POST path** (`scripts/verify_contract.py:548-555`). If the backend dies between `/health` OK and the POST, `urlopen` raises `URLError` which propagates out of `run_e2e_check`. The `finally` teardown still runs (good), but `main()` then crashes at `*run_e2e_check(args)` unpacking. This is asymmetric with `run_consumer_check:347` which explicitly catches `FileNotFoundError`. Predates iteration 1 — not a regression. A future iteration could add `except urllib.error.URLError as e: return (False, f"import-from-dir connection failed: {e}")` for symmetric error reporting.
2. **`run_e2e_check` does not catch `FileNotFoundError` from `subprocess.Popen`** (the same npx-not-installed scenario that `run_consumer_check:347` handles). Predates iteration 1 — not a regression. The WR-03 fix's `pgid is None` guard ensures teardown-b/c still run, but the function still exits via exception.

---

_Reviewed: 2026-07-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 2 (post-fix re-review)_
