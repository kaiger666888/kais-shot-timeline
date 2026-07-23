---
phase: 04-cross-repo-contract-verification
fixed_at: 2026-07-21T00:00:00Z
review_path: .planning/phases/04-cross-repo-contract-verification/04-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-07-21T00:00:00Z
**Source review:** `.planning/phases/04-cross-repo-contract-verification/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (2 blockers + 8 warnings; 5 info findings intentionally out of scope)
- Fixed: 10
- Skipped: 0

All 10 in-scope findings were applied cleanly to `scripts/verify_contract.py`. The harness still passes every required verification mode (producer / consumer / self-test / e2e) plus the new CR-01 negative-path test.

## Verification Matrix (post-fix)

| Test | Command | Expected | Result |
|------|---------|----------|--------|
| Producer mode | `python3 scripts/verify_contract.py --mode=producer` | exit 0 | PASS |
| Consumer mode | `python3 scripts/verify_contract.py --mode=consumer` | exit 0 | PASS (Phase 3 17 asserts green) |
| Self-test | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | exit 0 + corrupt asset detected | PASS |
| E2e mode | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | exit 0 + no orphan node/npx | PASS (99 nodes imported, 92 seq edges, clean teardown) |
| CR-01 negative | manifest missing `data` → producer mode | clean `[producer] FAIL` + exit 1 (no KeyError traceback) | PASS |
| CR-02 smoke | SIGTERM-ignoring grandchild outlives parent | grandchild reaped by unconditional SIGKILL | PASS |
| WR-03 layout | Popen moved inside try, `pgid=None` pre-guard | teardown skips proc cleanup cleanly when Popen fails | PASS (static) |
| WR-04 smoke | relative symlink `../originals/ep01.mp4` | resolves against asset_dir, not CWD | PASS |
| WR-05 smoke | data shape `subdir/foo.json` | parent dir auto-created before copy2 | PASS |
| WR-06 negative | `--mode=e2e --e2e-skip` | exit 1 with conflict message | PASS |
| WR-07 back-compat | both `--asset-dir` and `--e2e-asset-dir` + both env vars | all 4 forms work | PASS |
| WR-08 smoke | kv_canvasEvent missing → both DELETEs run independently | first DELETE commits, second warns | PASS |

## Fixed Issues

### CR-01: `validate_six_shapes` raises uncaught `KeyError` on malformed manifests

**Files modified:** `scripts/verify_contract.py`
**Commit:** `4f20d1f`
**Applied fix:** Restructured `validate_six_shapes` to pre-extract `data_field = manifest.get("data")` with type guard (degrade to `{}` if missing or non-dict). Replaced `manifest["data"][shape]` direct access with `data_field.get(shape)` plus a `isinstance(rel, str)` guard. Missing-required errors are reported by the existing asset-shape iter; only "key present but value not a string" (a case schema can't catch) is recorded on the data side. Verified via negative test: manifest missing `data` now produces clean `[producer] FAIL: asset at /<root>: 'data' is a required property` + exit 1 (no traceback).

### CR-02: Process-group teardown escalation has a race gap (orphan node leak risk)

**Files modified:** `scripts/verify_contract.py`
**Commit:** `f56f51a`
**Applied fix:** Cached `pgid = proc.pid` immediately after `Popen(..., start_new_session=True)` (guaranteed equal for the life of the group). Removed the conditional `os.getpgid(proc.pid)` calls that raced with reaping. Made `os.killpg(pgid, SIGKILL)` **unconditional** in the outer `finally` after a bounded `proc.wait(timeout=10)` on SIGTERM — closing the window where `npx` parent dies within 10s but child `node` ignores SIGTERM. Verified via standalone smoke test: SIGTERM-ignoring grandchild that outlives the parent gets reaped by the unconditional SIGKILL (would have leaked under pre-fix logic).

### WR-01: `_poll_health` ignores `proc.poll()` — wastes up to 45s on a crashed backend

**Files modified:** `scripts/verify_contract.py`
**Commit:** `bcbf801` (combined with WR-02)
**Applied fix:** Changed `_poll_health` signature to accept `proc: subprocess.Popen` and return `tuple[bool, str]` (ok, reason). Each iteration checks `proc.poll()` first — if the process has exited, returns immediately with `"backend died before /health (exit code=N)"` instead of polling for the full 45s. Updated the caller in `run_e2e_check` to pass `proc` and embed the reason string. Verified: dead proc returns in <0.1s with exit code in reason; live proc + no port exhausts timeout normally.

### WR-02: `_poll_health` exception coverage too narrow — `HTTPException`/`ConnectionResetError` break the poll loop

**Files modified:** `scripts/verify_contract.py`
**Commit:** `bcbf801` (combined with WR-01)
**Applied fix:** Added `import http.client` at module top. Broadened the except clause in `_poll_health` from `urllib.error.URLError` to `(urllib.error.URLError, OSError, http.client.HTTPException)`. Half-booted Express backends that send malformed HTTP during early listen no longer crash `run_e2e_check` with a traceback — they're swallowed and the loop continues (or fails fast via the WR-01 proc.poll() check if the backend actually died).

### WR-03: `subprocess.Popen` is outside the `try/finally` — small leak window

**Files modified:** `scripts/verify_contract.py`
**Commit:** `c65a5dc`
**Applied fix:** Hoisted the `pid`/`eid`/`db_path` computation (which doesn't depend on `proc`) to **before** Popen, then moved `try:` to immediately precede Popen. Initialized `proc = None` and `pgid = None` before the try so the `finally` block guards teardown-a with `if pgid is not None:` — if Popen fails or an exception fires before pgid is cached, teardown-a is skipped cleanly while teardown-b (worktree reconcile) and teardown-c (SQL DELETE) still run.

### WR-04: `_resolve_canonical_video` returns raw symlink target — relative symlinks resolve against CWD, not asset_dir

**Files modified:** `scripts/verify_contract.py`
**Commit:** `93d56f5`
**Applied fix:** After `os.readlink`, check `os.path.isabs(target)`. Relative targets are resolved via `(asset_dir / target).resolve()` (relative to the symlink's directory, not Python's CWD); absolute targets are passed through `os.path.realpath` to canonicalize any embedded `..`. Verified via smoke test: `../originals/ep01.mp4` symlink inside `asset_dir/video.mp4` now resolves to the real file under `originals/`, not a CWD-relative miss.

### WR-05: `run_self_test` data-file copy fails on subdirectory paths

**Files modified:** `scripts/verify_contract.py`
**Commit:** `3bd77a5`
**Applied fix:** In the self-test copy loop, compute `dst = temp_dir / rel` and call `dst.parent.mkdir(parents=True, exist_ok=True)` before `shutil.copy2(src_data, dst)`. The asset schema pattern (`^(?!.*\.\.)[^:*?\"<>|]+\.json$`) permits one-or-more directory segments; a future producer emitting `subdir/shots.json` no longer crashes self-test with `FileNotFoundError`. Verified via smoke test: synthetic manifest with `audio_analysis: subdir/audio_analysis.json` copies successfully.

### WR-06: `--mode=e2e --e2e-skip` silently exits 0 with no modes executed

**Files modified:** `scripts/verify_contract.py`
**Commit:** `3175d69`
**Applied fix:** Added an argparse-time guard in `main()`: if `args.mode == "e2e" and args.e2e_skip`, `sys.exit(...)` with a clear conflict message guiding the user to either drop `--e2e-skip` or switch to `--mode=all --e2e-skip` (the latter is a legitimate "all-minus-e2e" invocation). Verified: `--mode=e2e --e2e-skip` exits 1 with message; `--mode=all --e2e-skip` still works (runs producer + consumer, skips e2e).

### WR-07: `--e2e-asset-dir` / `PHASE4_E2E_ASSET_DIR` is misnamed — also used by producer and self-test modes

**Files modified:** `scripts/verify_contract.py`
**Commit:** `2628fa2`
**Applied fix:** Renamed the flag to `--asset-dir` (dest=`asset_dir`) and added `--e2e-asset-dir` as an argparse alias (both option strings map to the same dest). Renamed env var preference to `PHASE4_ASSET_DIR` first, `PHASE4_E2E_ASSET_DIR` as back-compat fallback. Updated help text to "asset 目录（producer/self-test/e2e 三种 mode 共用，默认 ep01）" with explicit back-compat note. Updated all `args.e2e_asset_dir` references to `args.asset_dir` (4 sites: producer check, self-test, e2e check, error messages). Updated module docstring and producer-mode docstring. Verified: all four forms (new flag, old flag, new env, old env) work; `--help` shows both aliases.

### WR-08: SQL cleanup uses one transaction — if `kv_canvasEvent` DELETE fails, `o_agentWorkData` rows are rolled back and leak

**Files modified:** `scripts/verify_contract.py`
**Commit:** `44e65cd`
**Applied fix:** Restructured teardown-c into a `for sql in (...)` loop where each DELETE runs in its own `try/except sqlite3.Error` and calls `conn.commit()` immediately after `cur.execute()`. A failure on the second DELETE (e.g., `kv_canvasEvent` doesn't exist due to consumer schema drift) writes a `[e2e] WARNING` to stderr but the first DELETE (`o_agentWorkData`) is already committed — no rollback leak. Verified via smoke test: dropped `kv_canvasEvent` after inserting rows in both tables, ran the new loop, confirmed `o_agentWorkData` row count is 0 (committed) despite the second DELETE failing.

## Skipped Issues

None — all 10 in-scope findings were applied successfully.

## Out-of-Scope (info findings, deferred)

The 5 IN-* findings from REVIEW.md were intentionally not addressed (fix_scope = critical_warning per the task):
- **IN-01** function-level `import signal as _signal` — left as-is (project precedent: `scripts/check_range.py` uses the same pattern; cosmetic).
- **IN-02** `DEFAULT_CONSUMER_PATH` hardcoded — overridable via env, acceptable default.
- **IN-03** self-test covers only one drift — extending to a DRIFTS table would be valuable but is an enhancement, not a defect.
- **IN-04** dead `r.status != 200` check — defensive belt-and-suspenders, low impact.
- **IN-05** producer mode doesn't check media file existence — schema delegates to runtime; enhancement, not a defect.

---

_Fixed: 2026-07-21T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
