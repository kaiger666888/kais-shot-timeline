---
phase: 04-cross-repo-contract-verification
reviewed: 2026-07-21T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - scripts/verify_contract.py
findings:
  critical: 2
  warning: 8
  info: 5
  total: 15
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

`scripts/verify_contract.py` (696 lines) implements producer/consumer/e2e/self-test modes for the cross-repo `ShotTimelineAsset` contract regression harness. The architecture is largely sound: SQL is parameterized (`?` placeholders throughout — `scripts/verify_contract.py:122-126, 595-604`), every subprocess invocation uses list form (no shell), the e2e teardown is in a `finally` block (line 555), the self-test genuinely proves fail-loud behavior via try/finally + `shutil.rmtree(..., ignore_errors=True)`, and the timestamp-based pid/eid avoids colliding with Phase 3's leftover 9001/9001 rows.

However, the adversarial pass surfaced **2 BLOCKERs** that defeat core guarantees the harness is supposed to provide:

1. **`validate_six_shapes` raises uncaught `KeyError` on malformed manifests.** The exact failure mode this harness is supposed to catch and report cleanly (missing/invalid `data` field, missing shape key) instead produces a traceback that masks any prior schema errors accumulated in the same loop iteration. The self-test only corrupts `schema_version` so it never exercises this path — the bug is invisible to the fail-loud proof.

2. **Process-group teardown escalation has a race gap that can leak orphan `node` backends.** `os.killpg(SIGTERM)` is sent correctly, but the SIGKILL escalation only fires when `proc.wait(timeout=10)` raises `TimeoutExpired`. If `npx` dies quickly while the child `node` process ignores SIGTERM (e.g., a future `app.ts` installs a graceful-shutdown handler — exactly the kind of change a regression harness is supposed to survive), `proc.wait()` returns successfully and SIGKILL never runs. The Rule-1 deviation comment claims robustness against this scenario, but the implementation only covers it when the parent also hangs. Additionally, `os.getpgid(proc.pid)` is called *after* `proc.wait()` reaps the parent — a reaped PID raises `ProcessLookupError` and silently skips the SIGKILL block.

Plus 8 warnings (health-poll robustness, exception coverage, `Popen` outside try, relative-symlink handling, subdir creation in self-test, silent no-op on `--mode=e2e --e2e-skip`, misnamed `--e2e-asset-dir`, single-transaction cleanup rollback) and 5 info items.

What is clean and explicitly verified:
- **No SQL injection** — every `cur.execute` uses `?` placeholders; no string interpolation of `pid`/`eid` anywhere (`scripts/verify_contract.py:122-126, 595-604`).
- **No shell injection** — every `subprocess.run`/`Popen` uses list-form `args` (no `shell=True`); asset dir paths with CJK + full-width punctuation flow through JSON body bytes safely (`scripts/verify_contract.py:472-477`).
- **No hardcoded secrets** — none present.
- **`Draft202012Validator` use is correct** for well-formed manifests — the inline-validator decision is justified (avoids `spec/validate.py:SMOKE_SHAPES` silently skipping the asset shape).
- **Self-test cleanup** — try/finally + `shutil.rmtree(ignore_errors=True)` (`scripts/verify_contract.py:388-390`) genuinely leaves no temp residue; real ep01 bytes are never mutated (copies only).

## Critical Issues

### CR-01: `validate_six_shapes` raises uncaught `KeyError` on malformed manifests (defeats harness purpose)

**File:** `scripts/verify_contract.py:183`
**Issue:** When the producer asset.json is missing the `data` field, or `data` is present but one of the 5 shape keys (`shots`/`audio_analysis`/`transcript`/`frames`/`prompts`) is absent, the dict access `manifest["data"][shape]` raises `KeyError`. The wrapping `try/except` at lines 185-192 only catches `FileNotFoundError` and `json.JSONDecodeError` around the *file-read* on line 186 — the *dict-access* on line 183 is outside that try block, so `KeyError` propagates uncaught, crashes `run_producer_check`, and main() prints a raw Python traceback instead of the harness's normal `"[producer] FAIL: <reason>"` format.

Worse: because `SIX_SHAPES = ["asset", "shots", ...]` iterates `"asset"` first (which validates against the manifest), the first loop turn *does* detect the schema violation and appends to `failures` — but the second turn (`shape == "shots"`) then crashes before `failures` is returned, so the user sees a `KeyError: 'data'` traceback instead of the actionable `"asset at /data: 'data' is a required property"` message. The harness is literally designed to catch malformed producer output, and the most likely malformation (missing `data`) is the one path that crashes it.

The same defect exists if `manifest["data"][shape]` returns a non-string value (e.g., `null`, `int`) — `asset_dir / rel` on line 184 then raises `TypeError`, also uncaught.

**Fix:** Validate the manifest's `data` field defensively before iterating shapes, and use `.get()` with explicit failure recording:

```python
def validate_six_shapes(asset_dir: Path, manifest: dict) -> list:
    failures = []
    data_field = manifest.get("data") if isinstance(manifest, dict) else None
    if not isinstance(data_field, dict):
        # Asset-shape validation will report the schema error;
        # bail out of the data-shape loop cleanly.
        data_field = {}
    for shape in SIX_SHAPES:
        schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if shape == "asset":
            instance = manifest
        else:
            rel = data_field.get(shape)
            if not isinstance(rel, str):
                # Schema will report "data.<shape> is required" via the asset
                # iteration; record a data-side failure too and skip file load.
                if shape not in data_field:
                    continue  # asset-shape iter already flagged it
                failures.append(f"{shape}: data.{shape} is not a string: {rel!r}")
                continue
            instance_path = asset_dir / rel
            try:
                instance = json.loads(instance_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                failures.append(f"{shape}: data file missing at {instance_path}")
                continue
            except json.JSONDecodeError as e:
                failures.append(f"{shape}: invalid JSON in {instance_path}: {e}")
                continue
        errs = sorted(
            Draft202012Validator(schema).iter_errors(instance),
            key=lambda e: list(e.absolute_path),
        )
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            failures.append(f"{shape} at /{loc}: {errs[0].message}")
    return failures
```

Also recommend extending `run_self_test` to inject a second drift (e.g., delete `manifest_copy["data"]` entirely) to prove the harness reports it cleanly rather than crashing — this would have caught CR-01 at self-test time.

---

### CR-02: Process-group teardown escalation has a race gap (orphan node leak risk)

**File:** `scripts/verify_contract.py:452-576`
**Issue:** The teardown sequence for the e2e backend is:

```python
# Line 452
proc = subprocess.Popen(
    ["npx", "tsx", "src/app.ts"], ..., start_new_session=True,
)
...
# Line 559-576 (teardown a)
try:
    pgid = os.getpgid(proc.pid)
    os.killpg(pgid, _signal.SIGTERM)
except (ProcessLookupError, PermissionError):
    pass
try:
    proc.wait(timeout=10)            # waits on npx parent only
except subprocess.TimeoutExpired:
    try:
        pgid = os.getpgid(proc.pid)  # RACE: parent may be reaped already
        os.killpg(pgid, _signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
```

Two defects:

**(a) SIGKILL escalation only fires when `proc.wait(timeout=10)` times out.** If `npx` (the parent) dies within 10s of SIGTERM — which is the *common* case since `npx` is just a thin launcher that forwards signals and exits when its child does — `proc.wait()` returns successfully, the `except subprocess.TimeoutExpired` block never executes, and SIGKILL is never sent. If the child `node` process is still alive at that moment (because it installed a SIGTERM handler that doesn't call `process.exit()`, or because signal delivery to the child is delayed), it is now reparented to init and **leaks on the e2e port**. The `04-VERIFICATION.md` table row "Backend 干净 teardown (无 orphan npx/tsx 进程)" passes today only because Node's default SIGTERM behavior is to exit — but the explicit purpose of the Rule-1 deviation (per `04-02-SUMMARY.md` "Deviations from Plan" §1) was to make teardown robust against exactly this scenario. The current logic is robust only if *both* parent and child hang together; it fails when parent dies before child.

**(b) `os.getpgid(proc.pid)` is called AFTER `proc.wait()` may have reaped the parent.** In the `TimeoutExpired` branch, by the time we reach line 569 the parent may have just exited (race between the 10s timeout firing and the parent dying). `os.getpgid(reaped_pid)` raises `ProcessLookupError` (ESRCH), the `except` swallows it, and SIGKILL is silently skipped. The child — which is the whole reason we're escalating — never receives SIGKILL.

**Fix:** Cache the pgid at Popen time (it is *guaranteed* equal to `proc.pid` because `start_new_session=True` makes the child the session/group leader), then make SIGKILL unconditional after SIGTERM + bounded wait. This eliminates both the TOCTOU on `getpgid` and the parent-dies-before-child window:

```python
proc = subprocess.Popen(
    ["npx", "tsx", "src/app.ts"],
    cwd=consumer, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True,
)
# start_new_session=True guarantees pgid == proc.pid for the life of the group.
# Cache it now — later os.getpgid(proc.pid) calls would race with reaping.
pgid = proc.pid
...
finally:
    import signal as _signal
    # SIGTERM the entire group (npx + child node + any tsx workers).
    try:
        os.killpg(pgid, _signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    # Bounded wait on the parent; do NOT branch escalation on this timeout.
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    # UNCONDITIONAL SIGKILL of the whole group — mops up any child that
    # ignored SIGTERM or whose parent died before forwarding the signal.
    try:
        os.killpg(pgid, _signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # (Optional) assert group is empty so a leak turns into a test failure:
    #   try: os.killpg(pgid, 0)
    #   except ProcessLookupError: pass
    #   else: sys.stderr.write(f"[e2e] WARN: pgid {pgid} still has live members\n")
```

Until this is fixed, the "Rule 1 fix" claim in the code comment and verification report is only conditionally true.

## Warnings

### WR-01: `_poll_health` ignores `proc.poll()` — wastes up to 45s on a crashed backend

**File:** `scripts/verify_contract.py:89-106`
**Issue:** If the consumer backend dies during boot (e.g., `npx tsx src/app.ts` exits immediately due to a TypeScript compile error, missing `better-sqlite3`, port race, OOM), `_poll_health` keeps retrying `/health` every 0.5s for the full 45s timeout. The Popen handle `proc` is in the outer scope and is never consulted inside the poll loop. For a CI regression harness, a 45s hang on a dead backend is poor UX and slows feedback loops.
**Fix:** Pass `proc` into `_poll_health` (or check via closure) and bail early when `proc.poll() is not None`:

```python
def _poll_health(port: int, proc: subprocess.Popen, timeout: float = 45.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:        # backend died
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(0.5)
    return False
```

The resulting error message should also distinguish "timed out" from "process exited" so a developer sees `backend died (exit code=1)` rather than a misleading "未在 45s 内 ready".

---

### WR-02: `_poll_health` exception coverage too narrow — `HTTPException`/`ConnectionResetError` break the poll loop

**File:** `scripts/verify_contract.py:99-104`
**Issue:** The `try/except urllib.error.URLError` catches HTTP-level errors (which `urlopen` raises as `HTTPError`, a URLError subclass), but a half-booted Express server that sends malformed HTTP during early listen (incomplete headers, connection reset mid-response) raises `http.client.HTTPException` or `ConnectionResetError`, neither of which is a URLError subclass. These propagate out of `_poll_health`, skip the rest of the polling budget, and crash `run_e2e_check` with a traceback (the `finally` still tears down the backend, but the failure message is opaque).
**Fix:** Broaden the catch to `(urllib.error.URLError, OSError, http.client.HTTPException)` and import `http.client`:

```python
import http.client
...
except (urllib.error.URLError, OSError, http.client.HTTPException):
    pass
```

---

### WR-03: `subprocess.Popen` is outside the `try/finally` — small leak window

**File:** `scripts/verify_contract.py:452-464`
**Issue:** `proc = subprocess.Popen(...)` is on line 452, but the `try:` that guarantees teardown is on line 464. Lines 459-462 (`pid = int(time.time())`, `eid = pid + 1`, `db_path = ...`) run between Popen and try. If any of those lines raise (unlikely for these specific calls, but a defensive concern — and a real risk if a future maintainer inserts heavier logic there), or if the user sends SIGINT in that exact window, the backend process is orphaned with no teardown. This is precisely the class of bug the harness is supposed to prevent.
**Fix:** Hoist the `try:` to immediately follow Popen, or set `proc = None` before the try and check `if proc is not None` in finally:

```python
proc = subprocess.Popen(...)
try:
    pid = int(time.time())
    eid = pid + 1
    db_path = os.path.join(consumer, "data", "db2.sqlite")
    ...  # rest of e2e logic
finally:
    if proc is not None:
        # teardown a/b/c
```

---

### WR-04: `_resolve_canonical_video` returns raw symlink target — relative symlinks resolve against CWD, not asset_dir

**File:** `scripts/verify_contract.py:136-146`
**Issue:** When `video.mp4` is a relative symlink (e.g., target `../../originals/ep01.mp4` — a common layout when an asset dir is a sibling of a source cache), `os.readlink` returns the relative string. `run_producer_check` then passes it as `--video <path>` to `export_asset.py`. `export_asset.py` resolves the relative path against the *current working directory of the Python process* (typically `kais-shot-timeline/`), not against `asset_dir`. The re-export then fails with "input video not found" or — worse — picks up an unrelated same-named file in the CWD-relative resolution.
**Fix:** Resolve the symlink absolutely relative to `asset_dir`:

```python
def _resolve_canonical_video(asset_dir: Path) -> str:
    video_link = asset_dir / "video.mp4"
    if video_link.is_symlink():
        target = os.readlink(video_link)
        if not os.path.isabs(target):
            target = str((asset_dir / target).resolve())
        return target
    return str(video_link)
```

(Same fix needed if `target` contains `..` that escapes `asset_dir` — fine to allow, but resolve canonically.)

---

### WR-05: `run_self_test` data-file copy fails on subdirectory paths

**File:** `scripts/verify_contract.py:357-360`
**Issue:** The self-test copies each referenced data file via `shutil.copy2(src_data, temp_dir / rel)`. If a future asset's `data.<shape>` path contains a directory segment (e.g., `data/shots.json` — the schema pattern permits this: `^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$`), `shutil.copy2` raises `FileNotFoundError` because `temp_dir / "data"` doesn't exist. The current ep01 asset is flat (`shots.json`, etc.), so the bug is latent, but the schema intentionally allows one-or-more-directory-segment paths (`asset.schema.json:66`), so a future producer emitting `subdir/shots.json` would crash self-test.
**Fix:** Create parent dirs before copy:

```python
for shape, rel in manifest_copy.get("data", {}).items():
    src_data = src_dir / rel
    if src_data.is_file():
        dst = temp_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_data, dst)
```

---

### WR-06: `--mode=e2e --e2e-skip` silently exits 0 with no modes executed

**File:** `scripts/verify_contract.py:674-680, 691-692`
**Issue:** When the user runs `python3 scripts/verify_contract.py --mode=e2e --e2e-skip`, the dispatch skips e2e (because `args.e2e_skip` is true), no other mode runs (because `args.mode == "e2e"` excludes producer/consumer), `results == []`, `any_fail = any(...)` is `False`, and the harness exits 0. The user has explicitly asked for e2e and explicitly asked to skip it — a contradictory invocation that produces a silent success is misleading and can mask a CI misconfiguration (e.g., a wrapper script passing both flags).
**Fix:** Either reject the combination at argparse level, or warn loudly and exit non-zero:

```python
if args.mode == "e2e" and args.e2e_skip:
    sys.exit("[verify-contract] --mode=e2e conflicts with --e2e-skip "
             "(nothing to do)")
```

---

### WR-07: `--e2e-asset-dir` / `PHASE4_E2E_ASSET_DIR` is misnamed — also used by producer and self-test modes

**File:** `scripts/verify_contract.py:215, 342, 437, 633-635`
**Issue:** The flag is named `--e2e-asset-dir` and the env var `PHASE4_E2E_ASSET_DIR`, but `run_producer_check` (line 215) and `run_self_test` (line 342) also read it via `args.e2e_asset_dir` to locate the asset they validate. The help text ("e2e 用的真实 asset 目录（默认 ep01）") and the name both suggest e2e-only scope, which is misleading. A user wanting to point producer mode at a different asset would not think to set a flag named "e2e-asset-dir".
**Fix:** Rename to `--asset-dir` / `PHASE4_ASSET_DIR` (with a back-compat alias if needed). At minimum, update the help text to "asset 目录用于 producer/self-test/e2e 三种 mode".

---

### WR-08: SQL cleanup uses one transaction — if `kv_canvasEvent` DELETE fails, `o_agentWorkData` rows are rolled back and leak

**File:** `scripts/verify_contract.py:591-613`
**Issue:** The two `cur.execute("DELETE ...")` calls run in a single implicit sqlite3 transaction, committed once at line 605. If the second DELETE raises (e.g., `kv_canvasEvent` doesn't exist due to a consumer schema drift, or some future FK constraint), the outer `except sqlite3.Error` catches it, `conn.close()` in the inner `finally` rolls back the uncommitted transaction, and the first DELETE's `o_agentWorkData` rows remain in the DB. The harness writes a `[e2e] WARNING` to stderr but otherwise reports success (the structural asserts already passed before teardown). The result: idempotency is silently broken for partial-schema-mismatch cases — a future run with the same `pid` collides with leftover rows.
**Fix:** Commit after each DELETE so partial cleanup is possible, or run each in its own try/except:

```python
for sql in (
    "DELETE FROM o_agentWorkData WHERE projectId = ? AND episodesId = ?",
    "DELETE FROM kv_canvasEvent WHERE projectId = ? AND episodesId = ?",
):
    try:
        cur.execute(sql, (str(pid), str(eid)))
        conn.commit()
    except sqlite3.Error as e:
        sys.stderr.write(f"[e2e] WARNING: cleanup step failed: {e}\n")
```

## Info

### IN-01: Function-level `import signal as _signal` inside teardown

**File:** `scripts/verify_contract.py:559`
**Issue:** `import signal as _signal` runs inside the `finally` block, on every teardown. Cheap (cached after first import) but unconventional; the project convention is top-level imports. Also the `_signal` alias is unnecessary — no top-level `signal` name collides.
**Fix:** Move `import signal` to the top-level import block (after `import socket` on line 44) and drop the underscore alias.

---

### IN-02: `DEFAULT_CONSUMER_PATH` hardcoded to a specific machine path

**File:** `scripts/verify_contract.py:63`
**Issue:** `DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"` only exists on the primary dev machine. The mirrored checkout at `/home/kai/workspace/kais-shot-timeline` and any CI / collaborator machine will see "CANVAS_CONSUMER_PATH 不存在" failures until they set the env var. Acceptable as a default (overridable), but a same-repo relative path or a `../kst-canvas-consumer` candidate fallback would reduce friction.
**Fix:** Optional — add a secondary fallback that probes `Path(REPO).parent / "kst-canvas-consumer"` before giving up.

---

### IN-03: Self-test covers only one drift scenario (schema_version pattern violation)

**File:** `scripts/verify_contract.py:362-387`
**Issue:** The self-test injects exactly one corruption (`schema_version="v1"`) and proves the harness detects it. Other corruption shapes — missing required field, wrong `asset_type` const, additional property (rejected by `additionalProperties: false`), media path traversal — are not exercised. The single drift covered happens to bypass CR-01's crash path entirely.
**Fix:** Extend self-test to iterate a small table of corruptions and assert each produces ≥1 error:

```python
DRIFTS = [
    ("schema_version='v1'", lambda m: m.update(schema_version="v1")),
    ("missing data",         lambda m: m.pop("data", None)),
    ("bad asset_type",       lambda m: m.update(asset_type="not-it")),
    ("extra root key",       lambda m: m.update(unknown_field="x")),
]
```

This would have caught CR-01 at self-test time.

---

### IN-04: Dead `r.status != 200` check at `scripts/verify_contract.py:487`

**File:** `scripts/verify_contract.py:485-488`
**Issue:** `urllib.request.urlopen` raises `HTTPError` for any 3xx/4xx/5xx response, so inside the `with` block `r.status` is always 2xx. The `if r.status != 200` branch (returns a failure for 201/202/204) can never execute as written; and if the API ever returns 201 Created on success, the harness would incorrectly report failure despite `urlopen` succeeding. Defensive checks are fine, but the condition should reflect actual success semantics.
**Fix:** Either drop the check (urlopen already guarantees 2xx), or document it as belt-and-suspenders and broaden to `r.status < 200 or r.status >= 300`.

---

### IN-05: Producer mode validates JSON shapes but not media file existence

**File:** `scripts/verify_contract.py:169-200`
**Issue:** The 6-schema inline validator checks that `media.video` and `media.stems.{vocals,drums,other}` are *strings matching a path pattern*, but does not check that those files actually exist on disk relative to `asset_dir`. A producer bug that writes a valid-looking manifest pointing at a missing `video.mp4` would pass producer mode and only fail downstream (e2e import, or worse, consumer rendering). The schema intentionally delegates existence checks to runtime (path-traversal pattern is the schema's job; file presence is the harness's job).
**Fix:** Optional — after schema validation passes, add a follow-up pass:

```python
for media_rel in [manifest["media"]["video"],
                  manifest["media"]["stems"]["vocals"],
                  manifest["media"]["stems"]["drums"],
                  manifest["media"]["stems"]["other"]]:
    if not (asset_dir / media_rel).is_file():
        failures.append(f"media missing: {media_rel}")
```

---

_Reviewed: 2026-07-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
