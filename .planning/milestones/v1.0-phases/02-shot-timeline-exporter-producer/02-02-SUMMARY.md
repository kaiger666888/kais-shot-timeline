---
phase: 02-shot-timeline-exporter-producer
plan: 02
subsystem: producer-exporter
tags: [serve-py, fd-leak, range-206, self-check, http-server]
requires:
  - "Phase 1: spec/schemas/asset.schema.json (no change — read-only reference)"
  - "Plan 02-01: scripts/export_asset.py + run_pipeline.py:step_export (asset.json + canonical symlinks)"
  - "Pre-GSD baseline: scripts/serve.py Range-aware HTTP server (FD-leak carrier)"
provides:
  - "scripts/serve.py — _Partial class with __init__/read/close; no AttributeError on do_GET finally f.close()"
  - "scripts/check_range.py — standalone Range-206 self-check (urllib + subprocess + try/finally teardown)"
affects:
  - "scripts/serve.py (MODIFIED — _Partial class refactor; 416/NOT_FOUND/200 branches + module docstring + main untouched)"
  - "scripts/check_range.py (NEW)"
tech-stack:
  added: []
  patterns:
    - "_Partial as instance-attr wrapper (not closure) so close() can reach underlying file"
    - "find_free_port via socket bind 127.0.0.1:0 (kernel-allocated ephemeral port — avoids 8765/8766 collisions)"
    - "wait_ready deadline-loop with socket.create_connection (no curl dependency)"
    - "try/finally subprocess teardown mirroring audio/transcribe.py:150-155 temp-wav cleanup idiom"
    - "Bracketed tag log style [check-range] matching spec/validate.py:[validate] convention"
key-files:
  created:
    - scripts/check_range.py
    - .planning/phases/02-shot-timeline-exporter-producer/deferred-items.md
  modified:
    - scripts/serve.py
decisions:
  - "_Partial.close() implemented as one-liner self._f.close(); f stored as self._f in __init__ (closure vars eliminated)"
  - "Primary fix only — secondary belt-and-braces try/except around open() skipped (primary fix verified sufficient: 0 FD drift over 50 requests)"
  - "416/NOT_FOUND/200 branches deliberately untouched (02-RESEARCH Pitfall 2 verified they are already correct)"
  - "check_range.py standalone (NOT wired to step_export) per 02-RESEARCH Open Question 3: avoid port-concurrency risk + keep producer/server concerns separate"
  - "check_range.py default scan = sorted(iterdir(output)) → first child with video.mp4 (Unicode sort order picks ep03 first; both ep01/ep03 pass)"
  - "Stable test target: ep01 (intact data JSONs); ep03 has half-written asset.json from interrupted background regen — out of scope (deferred-items.md)"
metrics:
  duration: ~15min
  completed: 2026-07-20T22:05:00Z
  tasks: 2
  files_created: 2
  files_modified: 1
---

# Phase 2 Plan 2: Servability Closure (FD-leak fix + Range-206 self-check) Summary

修复 `scripts/serve.py` 的 `_Partial` 类 FD-leak bug（每次 Range 206 请求泄漏一个 FD，因 `_Partial` 缺 `close()` 方法导致 `SimpleHTTPRequestHandler.do_GET` 的 `finally: f.close()` raise AttributeError），并新增 `scripts/check_range.py` 作为 EXPORT-03「206 Partial Content responses observed」的机器可检证据——stdlib-only（urllib + subprocess + socket），自动扫 `output/` 找含 `video.mp4` 的目录，启动 serve.py on free port，断言 206/Content-Range/Accept-Ranges/1024-byte body 四条不变量，try/finally 保证 tear-down。

## What Was Built

### Task 1 — `scripts/serve.py` _Partial FD-leak fix (MODIFIED, +21/-12 lines)

**Root cause (verified live against `/usr/lib/python3.12/http/server.py:681`):**
`SimpleHTTPRequestHandler.do_GET` does:
```python
f = self.send_head()
if f:
    try:
        self.copyfile(f, self.wfile)
    finally:
        f.close()  # ← calls .close() on whatever send_head returns
```

For 206 responses, `send_head` returned `_Partial()` (a class with only `read()`). The `finally: f.close()` then raised `AttributeError: '_Partial' object has no attribute 'close'`, the exception propagated, and the **underlying file object captured in `_Partial`'s closure was never closed**. Every Range 206 request leaked one FD; ~1000 seeks would hit EMFILE.

**Fix (minimal, per 02-PATTERNS.md template):**
- Refactored `_Partial` from a closure-based class to instance-attr class:
  - `__init__(self, f, start, end, chunk_size=64*1024)`: stores `self._f`, `self._remaining`, `self._chunk_size`; seeks f if `start > 0` (timing-equivalent to the old line-80 setup)
  - `read(self, _n=None)`: same chunking logic, uses `self._*` (removed `nonlocal remaining`)
  - `close(self)`: one-liner `self._f.close()` — **the core fix**
- Return statement: `_Partial(f, start, end) if partial else f` (was `_Partial() if partial else f`)
- Removed the three setup lines above the class (`if start > 0: f.seek(start)` / `remaining = ...` / `chunk_size = ...`) — moved into `__init__`

**Untouched (deliberately, per 02-RESEARCH Pitfall 2):**
- 416 branch (`f.close(); return None`) — already correct
- NOT_FOUND branch (open fails into `except OSError`, f never assigned) — already correct
- 200 branch (`return f` directly — real file object with native `.close()`) — already correct
- Module docstring, `ThreadingHTTPServer`, `main()` — zero changes

### Task 2 — `scripts/check_range.py` (NEW, 149 lines)

Standalone Range-206 self-check, stdlib-only. Structure follows `spec/validate.py:141-180` standalone-verifier shape (argparse + Chinese help + `sys.exit(0/1)` + bracketed `[check-range]` log).

**3 helpers:**
- `find_free_port() -> int`: `socket.bind(("127.0.0.1", 0))` → kernel-allocated ephemeral port. Avoids hardcoded 8765/8766 (both in use by pre-existing serve.py processes during testing).
- `wait_ready(port, timeout=5.0) -> bool`: deadline-loop polling `socket.create_connection` every 0.1s.
- `check(asset_root) -> int`: pre-check `video.mp4` exists → `subprocess.Popen` serve.py → `urllib.request.Request(url, headers={"Range": "bytes=0-1023"})` → assert 4 invariants → `try/finally` ensures `proc.terminate()` + `wait(timeout=2)` + `kill()` on timeout.

**4 invariants asserted:**
1. `status == 206`
2. `Content-Range` starts with `"bytes 0-1023/"`
3. `Accept-Ranges == "bytes"`
4. `len(body) == 1024`

**`main()`:** argparse positional `asset_root` (nargs="?", default=None). When None, scans `REPO/output/` sorted children for first dir containing `video.mp4`; actionable `sys.exit` if none found.

**Design decisions (per plan + 02-RESEARCH Open Question 3):**
- **Standalone, NOT wired to step_export.** Reasons: (a) server port-concurrency risk in parallel pipelines; (b) producer concern (export) vs server concern (serving) — coupling muddies architecture; (c) check belongs with `/gsd:verify-work` + Phase 4 regression harness, not every pipeline run.
- **stdlib urllib, not curl.** Portable, no external dep (CONTEXT discretion allowed either; urllib chosen).
- **try/finally (not try/except).** Any exception (including KeyboardInterrupt) must guarantee `proc.terminate()` — mirrors `audio/transcribe.py:150-155` temp-wav cleanup idiom.

## Verification Evidence

**Task 1 static checks:**
- `python3 -c "import ast; ast.parse(open('scripts/serve.py').read())"` → exit 0
- `grep "def close(" scripts/serve.py` ✓
- `grep -E "self\._f\.close\(\)" scripts/serve.py` ✓
- `grep "def __init__(self, f, start, end" scripts/serve.py` ✓
- `! grep "nonlocal remaining" scripts/serve.py` ✓ (closure eliminated)

**Task 1 behavioral — 50 consecutive Range requests (ep01 stable target, port 53519):**
```
serve PID: 788649
ready: 1
FD before: 4
FD after: 4
FD drift: 0
PASS: no AttributeError in stderr
```
All 50 server log lines: `"GET /video.mp4 HTTP/1.1" 206 -` (clean 206s, zero tracebacks).

**Task 1 206 semantics (single request):**
```
HTTP/1.0 206 Partial Content
Content-Range: bytes 0-1023/48783460
Content-Length: 1024
Accept-Ranges: bytes
body: 1024 bytes
```
All 4 invariants hold. Video file size 48783460 bytes matches `Content-Range` total.

**Task 1 git diff scope:**
```
scripts/serve.py | 33 +++++++++++++++++++++------------
1 file changed, 21 insertions(+), 12 deletions(-)
```
Confirmed: only `_Partial` class + 3 setup lines + return statement touched. 416/NOT_FOUND/200/main/docstring untouched.

**Task 2 static checks:**
- syntax OK (ast.parse)
- `--help` exit 0 with bilingual Chinese description
- `urllib.request` ✓ `Range.*bytes=0-1023` ✓ `scripts/serve.py` ✓ `proc.terminate` ✓
- No `curl` import or subprocess.run curl ✓
- 149 lines (> 80-line min)

**Task 2 behavioral:**
| Test | Target | Expected | Actual |
|------|--------|----------|--------|
| Explicit asset_root | ep01 | exit 0, OK msg | `[check-range] OK: 206 + Content-Range=bytes 0-1023/48783460 + Accept-Ranges=bytes + 1024-byte body`, exit 0 ✓ |
| Default scan (auto-pick) | sorted → ep03 | exit 0, OK msg | `[check-range] OK: 206 + Content-Range=bytes 0-1023/34149946 + Accept-Ranges=bytes + 1024-byte body`, exit 0 ✓ |
| Non-existent dir | /tmp/nonexistent_dir_xyz | exit 1, actionable msg | `[check-range] no video.mp4 in /tmp/nonexistent_dir_xyz — nothing to probe`, exit 1 ✓ |
| No serve.py leaked | after 3 runs | no orphan processes | Only pre-existing PIDs 1493593, 2025036 (pre-test) ✓ |

**Phase gate (per 02-VALIDATION.md §Sampling Rate):**
- `python3 spec/validate.py --strict-smoke` → **FAIL (pre-existing, NOT from this plan)** — ep03's transcript.json/frames.json missing from background regen carried over from 02-01 (documented in 02-01-SUMMARY Test-Fixture Cleanup Note + deferred-items.md). ep01 (stable target) all 5 data shapes schema-valid. Plan 02-02's deliverables don't touch any data JSON or spec/validate.py.
- `python3 scripts/check_range.py` → **PASS** (exit 0, 4 invariants hold on default scan)

## Deviations from Plan

None — plan executed exactly as written. Both tasks followed the 02-PATTERNS.md templates verbatim (Task 1 `_Partial.close()` minimal fix; Task 2 standalone verifier skeleton lifted from 02-RESEARCH.md §Code Examples).

## Known Stubs

None. Both deliverables are fully functional:
- `scripts/serve.py` `_Partial.close()` is a real method that closes the real underlying file (verified by FD-drift=0 over 50 requests)
- `scripts/check_range.py` runs end-to-end against real exported asset dirs and asserts real HTTP invariants

## Threat Flags

None. The threat model in 02-02-PLAN.md remains accurate:
- T-02-03 (FD-exhaustion DoS) — mitigated by this plan (Task 1)
- T-02-04 (serve.py 0.0.0.0 unauth) — accepted/deferred per CONTEXT D-04 (out of scope)
- T-02-07 (symlink crossing asset root) — accepted per 02-RESEARCH Pitfall 1 (video.mp4 must point to original video with audio; check_range.py validates serving behavior)
- T-02-08 (check_range port failure) — mitigated by find_free_port + wait_ready + try/finally

No new threat surface introduced. check_range.py only opens an outbound socket to a self-spawned localhost server; no new network listeners, auth paths, or schema changes.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Primary fix only (no secondary try/except around open()) | 02-RESEARCH Pitfall 2 suggested an optional belt-and-braces `try/except: f.close(); raise` around the body after `f = open(...)`. Skipped because primary fix verified sufficient: 0 FD drift over 50 requests, zero AttributeError in stderr. Adding it now would be unused defensive code. |
| 416/NOT_FOUND/200 branches deliberately untouched | 02-RESEARCH Pitfall 2 verified line-by-line that these branches are already correct. Touching them would expand blast radius without fixing any bug. |
| check_range.py standalone, not auto-run by step_export | 02-RESEARCH Open Question 3 resolution: (a) port-concurrency risk; (b) producer vs server concern separation; (c) check belongs with verify-work, not every pipeline run. |
| find_free_port via socket bind 127.0.0.1:0 (not hardcoded port) | Two pre-existing serve.py processes were running during testing (PIDs 1493593 on 8765, 2025036 on 8766). Hardcoded port would race. Kernel allocation is race-free. |
| Stable test target = ep01 | ep03 had half-written asset.json (0 bytes) from interrupted background regen. ep01's data JSONs all intact and schema-valid. Documented in deferred-items.md. |
| Default scan sorted(iterdir) — Unicode order picks ep03 first | Acceptable: check_range tests video.mp4 serving, which is independent of asset.json validity. Both ep01 and ep03 pass. |

## Open Items / Forward Notes

- **`spec/validate.py --strict-smoke` failure on ep03** — logged to `deferred-items.md`. Pre-existing from 02-01 background-regen interruption; not caused by 02-02. Suggested fix: re-run `python3 run_pipeline.py --video <ep03-video>` to rebuild transcript.json + frames.json.
- **serve.py secondary defensive fix** — 02-RESEARCH Pitfall 2 "Secondary fix" not implemented (belt-and-braces try/except around `f = open()`). Primary fix verified sufficient; secondary fix can be added if future bugs emerge in `send_head` body.
- **serve.py 0.0.0.0 unauth (T-02-04)** — deferred per CONTEXT D-04. Single-user offline dev tool. Out of v1.0 scope.
- **Phase 4 regression harness** — `scripts/check_range.py` is the foundation. Phase 4 can wrap it alongside `spec/validate.py` for full EXPORT-01/02/03 coverage.

## Self-Check: PASSED

- FOUND: scripts/serve.py (Task 1 modified — _Partial class with close())
- FOUND: scripts/check_range.py (Task 2 new file)
- FOUND: .planning/phases/02-shot-timeline-exporter-producer/deferred-items.md (out-of-scope log)
- FOUND: 1ba04ad (Task 1 commit — fix _Partial FD leak)
- FOUND: d56251d (Task 2 commit — add check_range.py)
- FOUND: `def close(` in scripts/serve.py:97
- FOUND: `self._f.close()` in scripts/serve.py:99
- FOUND: `Range.*bytes=0-1023` in scripts/check_range.py:78
- FOUND: `proc.terminate` in scripts/check_range.py:118
- FOUND: 02-02-SUMMARY.md
