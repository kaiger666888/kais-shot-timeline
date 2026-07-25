---
phase: 12-producer-route-client-call-audio-analysis-py
plan: 02
subsystem: testing
tags: [stub-round-trip, sc4-proof, smoke-harness, graceful-degrade-proof, cache-proof, live-cross-check]

# Dependency graph
requires:
  - phase: 12-01
    provides: analysis/call_audio_analysis.py (producer client under test)
  - phase: 10-02
    provides: ROUTE-01 cross-repo stub envelope contract (kais-aigc-platform:feat/audio-analysis-route)
provides:
  - "SC#4 deterministic proof: in-process mock stub (tests/audio_analysis_stub_server.py) + 5 frozen scenarios proving call_audio_analysis.py handles Phase 10 stub envelope (parse + cache write/read + warnings merge) BEFORE route ML live"
  - "Live cross-repo confirmation: producer client integrates cleanly with the actual feat/audio-analysis-route stub host (PORT 10595 harness, byte-identical envelope, exit 0 + [audio] warning + audio_semantic.json absent)"
affects: []

# Tech tracking
tech-stack:
  added: []  # zero new deps — stub server uses only Python stdlib (http.server, argparse, json)
  patterns:
    - "Frozen-fixture stub: byte-snapshot of Phase 10 envelope served deterministically (no ML, no network beyond loopback)"
    - "5-scenario bash smoke: route-up-write / cache-hit byte-identical / poisoned-cache-invalidate / full-degrade / offline-empty — one assert per CONTRACT-05/PIPE-02 invariant"
    - "Best-effort live cross-repo cross-check via tsx module-load harness (mirrors Phase 10 _smoke_harness.ts pattern, NOT committed to either repo)"

key-files:
  created:
    - "tests/audio_analysis_stub_server.py (118 lines) — http.server.BaseHTTPRequestHandler stub: POST → fixture (200), GET → 405 (explicit Content-Length, HTTP/1.1 to avoid Python 3.12 send_error empty-reply bug)"
    - "tests/fixtures/audio_analysis_stub_response_empty.json (1 line) — byte-snapshot of Phase 10 stub envelope (10-02-SUMMARY.md:166, VERIFIED byte-identical)"
    - "tests/fixtures/audio_analysis_stub_response_nonempty.json (36 lines) — shape-correct non-empty envelope using spec/fixtures/v1.2/audio_semantic.json shot 1 structure with spike-derived HAPPY emotion + WhisperX-shaped word timestamps"
    - "tests/run_audio_analysis_smoke.sh (207 lines) — 5-scenario bash orchestration with trap cleanup + assert helpers; ALL_SCENARIOS_PASS on green"
  modified: []

key-decisions:
  - "Scenario 3 corruption changed from plan's emotion=123 (silently dropped by normalize_audio_semantic isinstance guard → never triggers poisoned-invalidation path) to word.start=-5 (passes type guard, fails schema minimum:0 → actually triggers unlink + 'invalidated poisoned cache' log). Rule 1 deviation — plan's corruption was a test bug."
  - "Stub server HTTP/1.1 + explicit Content-Length on GET (not Python's send_error): Python 3.12 BaseHTTPRequestHandler.send_error + default HTTP/1.0 yields 'empty reply from server' (curl 52, httpx RemoteProtocolError 'Server disconnected without sending a response') — preflight fails. Rule 1 fix."
  - "Ports 10593/10594 (not plan's 10591/10592): pre-existing kais-aigc-platform kontext-service.py on PID 5574 holds 10591. Rule 3 — switch to free ports, do NOT kill unrelated service."
  - "Task 2 took the LIVE path (not graceful-skip): cross-repo worktree at /tmp/kais-aigc-platform-audio-route exists; symlinked node_modules from main checkout + wrote uncommitted _p12_smoke_harness.ts (mirrors Phase 10 _smoke_harness.ts). Stub mounted on PORT 10595, returned byte-identical Phase 10 envelope, producer client ran cleanly."

patterns-established:
  - "Producer-client smoke harness pattern: stub server in tests/ + fixtures in tests/fixtures/ + orchestration in tests/run_*.sh — applies cleanly to future call_route_* siblings (call_shot_analysis, call_reid)"

requirements-completed: [PIPE-02]

# Metrics
duration: 32min
completed: 2026-07-26
---

# Phase 12 Plan 02: Producer-Route Client Stub Round-Trip Summary

**SC#4 doubly proven: Task 1 delivers a deterministic 5-scenario smoke harness (in-process mock stub) proving `call_audio_analysis.py` correctly parses the Phase 10 stub envelope, manages per-shot cache (write/hit/poisoned-invalidate), and merges `[audio]` warnings non-destructively with `[semantic]`/`[reid]` tags. Task 2 supplementary live cross-repo cross-check SUCCEEDED (not deferred): producer client integrated cleanly with the actual `feat/audio-analysis-route` stub host, exit 0, audio_semantic.json absent (CONTRACT-05 byte-identical v1.1), `[audio]` warning with stub_mode:true diagnostic present.**

## Performance

- **Duration:** ~32 min
- **Started:** 2026-07-26T00:00Z
- **Completed:** 2026-07-26T00:32Z
- **Tasks:** 2/2 complete (Task 1 commit + Task 2 verification-only)
- **Files created:** 4 test artifacts (118 + 1 + 36 + 207 lines)
- **Production code changes:** ZERO (test-only plan)

## Accomplishments

- **SC#4 stub-only round-trip proven deterministically** (Task 1): 5/5 smoke scenarios PASS against a frozen-fixture stub that mirrors the Phase 10 ROUTE-01 envelope byte-for-byte. Every code path in `call_audio_analysis.py` (parse → cache write → cache hit → poisoned invalidate → warnings read-merge-write → byte-identical-absent) is exercised.
- **Live cross-repo confirmation** (Task 2): symlinked node_modules from main checkout + wrote uncommitted `_p12_smoke_harness.ts` in the audio-route worktree (mirrors Phase 10's pattern). Stub mounted on PORT 10595, returned byte-identical Phase 10 envelope. Producer client ran against it: exit 0, audio_semantic.json absent, [audio] warning with `stub_mode:true — ML not loaded` diagnostic.
- **Non-destructive read-merge-write proven** (Scenario 4): `[audio]` coexists with `[semantic]` + `[reid]` tags in route_cache/warnings.json (cross-step preservation invariant for PIPE-02).
- **Poisoned-cache invalidation proven reachable** (Scenario 3): the schema-probe path at `call_audio_analysis.py:657-667` (which initially looked like defensive dead code) fires correctly when cache content violates `audio_semantic.schema.json` (word.start ≥ 0 constraint).
- **No production code touched** — pure test-harness plan; zero risk to v1.2 contract or pipeline.

## Task Commits

1. **Task 1: Local stub server + 2 fixtures + 5-scenario smoke script** — `73d257a` (feat) in `kais-shot-timeline:main`
2. **Task 2: Live cross-repo stub cross-check** — verification only, no commit (per plan `<files>(no file changes — verification only)</files>`)

**Plan metadata commit:** this `docs(12-02)` commit (SUMMARY only).

## Files Created

**This repo (`kais-shot-timeline:main`):**
- `tests/audio_analysis_stub_server.py` (118 lines) — Python 3 stdlib `http.server.BaseHTTPRequestHandler` minimal stub. POST `/api/production/audio-analysis` → 200 + fixture bytes; GET → 405 (explicit response, not `send_error` due to Python 3.12 empty-reply bug). HTTP/1.1 + Content-Length. Argparse CLI: `--fixture` (required), `--port` (default 10591), `--host` (default 127.0.0.1). Startup prints `[stub] listening on http://...` for smoke-script readiness polling.
- `tests/fixtures/audio_analysis_stub_response_empty.json` (1 line) — byte-snapshot of the Phase 10 stub envelope from `10-02-SUMMARY.md:166`. Verified byte-identical via `diff`. This is the SC#4 contract target.
- `tests/fixtures/audio_analysis_stub_response_nonempty.json` (36 lines) — shape-correct non-empty envelope. `data.shots[0]` mirrors `spec/fixtures/v1.2/audio_semantic.json` shot 1 structure (dialogue with HAPPY emotion + WhisperX-shaped word timestamps + sfx + reproduction.tts). Spike-derived values: HAPPY emotion label from `ser_sensevoice_ep01.json` shot 1, Speech event, word scores ~0.95-0.99 matching WhisperX `mean_word_score` range. Schema-validates against `audio_semantic.schema.json` when `data.shots[]` lifted to top-level.
- `tests/run_audio_analysis_smoke.sh` (207 lines) — 5-scenario bash orchestration. Computes `REPO_ROOT` from `BASH_SOURCE` (1 level up — tests/ is depth-1, NOT depth-2 as plan stated). Unique `/tmp/p12-smoke-$$` workdir. Trap cleanup kills stub PIDs + rm workdir on EXIT. Assert helpers: `assert_file_exists/absent`, `assert_grep/not_grep`, `wait_stub_ready`. ALL_SCENARIOS_PASS on green; exit 1 with diff/grep evidence on red.

**Not committed (mirrors Phase 10 pattern):**
- `/tmp/kais-aigc-platform-audio-route/_p12_smoke_harness.ts` — minimal Express harness mounting only route139 on PORT 10595. Removed after Task 2 (never committed to kais-aigc-platform — same convention as Phase 10's `_smoke_harness.ts`).
- `/tmp/kais-aigc-platform-audio-route/node_modules` symlink — removed after Task 2.

## 5-Scenario Smoke Results

`bash tests/run_audio_analysis_smoke.sh` final output (exit 0):

```
[smoke] SCENARIO 1: route-up + non-empty → audio_semantic.json written + schema-valid
  [PASS] S1 audio_semantic.json written: file exists (audio_semantic.json)
  [PASS] S1 audio_semantic.json schema-valid (Draft202012Validator)
  [PASS] S1 cache file written: file exists (route_cache/audio_analysis/shot_001.json)
  [PASS] S1 zero [audio] warnings on success: grep '\[audio\]' NOT in warnings.json (expected)
[smoke] SCENARIO 1: PASS

[smoke] SCENARIO 2: --offline cache-hit → byte-identical to scenario 1
  [PASS] S2 byte-identical to scenario 1 (deterministic cache read)
  [PASS] S2 cache hit logged: grep 'shot 1: cache hit' in scen2.log
[smoke] SCENARIO 2: PASS

[smoke] SCENARIO 3: poisoned cache (word.start=-5 violates schema minimum:0)
  [PASS] S3 'invalidated poisoned cache' logged: grep 'invalidated poisoned cache' in scen3.log
  [PASS] S3 poisoned cache file unlinked: file absent (route_cache/audio_analysis/shot_001.json)
  [PASS] S3 [audio] warning in sidecar: grep '\[audio\]' in warnings.json
[smoke] SCENARIO 3: PASS

[smoke] SCENARIO 4: empty stub (stub_mode:true) → byte-identical-absent + cross-step tags preserved
  [PASS] S4 audio_semantic.json absent (CONTRACT-05 byte-identical v1.1): file absent (audio_semantic.json)
  [PASS] S4 [audio] warning appended: grep '\[audio\]' in warnings.json
  [PASS] S4 [semantic] tag preserved: grep '\[semantic\]' in warnings.json
  [PASS] S4 [reid] tag preserved: grep '\[reid\]' in warnings.json
[smoke] SCENARIO 4: PASS

[smoke] SCENARIO 5: --offline --force + empty cache → byte-identical-absent + [audio] warning
  [PASS] S5 audio_semantic.json absent: file absent (audio_semantic.json)
  [PASS] S5 [audio] warning in sidecar: grep '\[audio\]' in warnings.json
[smoke] SCENARIO 5: PASS

ALL_SCENARIOS_PASS
```

**Per-scenario contract mapping:**
| # | Scenario | Contract proven | Result |
|---|----------|-----------------|--------|
| 1 | route-up + nonempty fixture | cache write + schema-valid + 0 warnings on success | PASS |
| 2 | re-run `--offline` | byte-identical output (deterministic cache) | PASS |
| 3 | poisoned cache (word.start=-5) | auto-invalidate + unlink + `[audio]` warning | PASS |
| 4 | empty stub_mode:true + sidecar pre-existing tags | byte-identical-absent + non-destructive read-merge-write | PASS |
| 5 | `--offline --force` + empty cache | byte-identical v1.1 asset + `[audio]` warning | PASS |

## Task 2 Results (Live Cross-Repo Stub Cross-Check)

**Path taken:** LIVE CROSS-CHECK SUCCEEDED (NOT graceful-skip).

### Setup

- Cross-repo worktree confirmed at `/tmp/kais-aigc-platform-audio-route` on branch `feat/audio-analysis-route`.
- Source verified present: `src/routes/production/audio-analysis/index.ts` + `_shared/config.ts`.
- `node_modules` MISSING in worktree (Phase 10's symlink was removed post-Task-2). Per Rule 3 EXCLUSION, did NOT run `npm install`. Instead symlinked `node_modules` from main checkout `/data/workspace/kais-aigc-platform/node_modules` (mirrors Phase 10 Task 2 pattern).
- Wrote minimal Express harness `_p12_smoke_harness.ts` in worktree (NOT committed — same convention as Phase 10's `_smoke_harness.ts`). Mounts only route139 on PORT 10595.

### Live stub envelope (curl round-trip)

```bash
$ curl -sS -X POST http://127.0.0.1:10595/api/production/audio-analysis \
    -H 'Content-Type: application/json' -d '{"video":"/x","shots":"/y"}'

{"code":200,"data":{"shots":[],"count":0,"errors":[],"stub_mode":true,"message":"Phase 10 stub: ML models not loaded. Producer client envelope round-trip proven."},"message":"Audio analysis stub"}
```

**Byte-identical to Task 1's empty fixture** — local stub harness matches live route output exactly.

### Producer client against live stub

```bash
$ python3 analysis/call_audio_analysis.py \
    --video /tmp/p12-live-.../video.mp4 \
    --shots /tmp/p12-live-.../shots.json \
    --work-dir /tmp/p12-live-... \
    --output /tmp/p12-live-.../audio_semantic.json \
    --stems-dir /tmp/p12-live-.../stems \
    --route-url http://127.0.0.1:10595/api/production/audio-analysis

[audio] shot 1: FAIL route returned 0 shots for shot_id_range=[1, 1] (stub_mode:true — ML not loaded)
[audio] zero shots with data → audio_semantic.json absent (byte-identical v1.1 asset, CONTRACT-05)
[audio] audio_semantic.json absent (2 new warnings)
---exit: 0
```

### SC#4 contract verification

| Criterion (plan Task 2 Step 3 expected) | Result |
|-----------------------------------------|--------|
| exit code 0 | PASS |
| `audio_semantic.json` NOT written (stub returns shots:[] → full-degrade) | PASS |
| `route_cache/warnings.json` contains `[audio]` tag | PASS |
| Client did NOT crash on `stub_mode:true` | PASS |
| Cache file NOT written (route returned no shots to cache) | PASS (route_cache/audio_analysis/ empty) |

**Supplementary confirmation:** Task 1's local mock stub harness already proves SC#4 deterministically across 5 scenarios; Task 2's live cross-check confirms the local fixture matches the actual cross-repo route output byte-for-byte.

### Process / artifact cleanup

- `_p12_smoke_harness.ts` removed from worktree (NOT committed).
- `node_modules` symlink removed from worktree.
- Orphan tsx/node child processes from `npx tsx` killed via `pkill -f _p12_smoke_harness.ts`.
- Port 10595 confirmed free.
- Worktree `git status` clean (no uncommitted p12 artifacts left behind).

## Decisions Made

### Scenario 3 corruption: `word.start=-5` instead of plan's `emotion=123`

**Rule 1 deviation (test bug).** The plan specified `d['dialogue']={'emotion':123}` to trigger schema-validate failure in the poisoned-cache probe (`call_audio_analysis.py:657-667`). Empirically tracing `normalize_audio_semantic`:

```python
if "emotion" in raw_dialogue:
    emo = raw_dialogue["emotion"]
    if emo is None or isinstance(emo, str):  # 123 is neither
        dialogue["emotion"] = emo
    # 非 str/null 丢弃 — silently dropped
```

`emotion=123` is silently dropped by the isinstance guard. The resulting `dialogue` dict either lacks `emotion` or — if no other fields are present — is empty and omitted entirely. `normalize_audio_semantic` then returns a schema-valid skeleton. The probe at line 657 (`validator.iter_errors(probe_payload)`) yields ZERO errors, so the unlink path never fires. The plan's literal assertions (`invalidated poisoned cache` logged + cache file unlinked) would FAIL.

**Fix:** switched to `d['dialogue']={'words': [{'start': -5, 'end': 0.5, 'text': 'poison'}]}`. `-5` is `isinstance(_, (int, float))` → passes normalize's type filter, but violates `audio_semantic.schema.json` `words[].start minimum: 0`. The schema probe fails → unlink fires → `[audio] shot 1: invalidated poisoned cache` logged → `[audio] shot 1: offline/stale-cache (poisoned or _cache_key mismatch) → absent from audio_semantic` warning appended. All plan assertions PASS.

This was a genuine plan bug — `normalize_audio_semantic` is defensive-by-design (drops bad fields rather than passing them through), so the schema probe is only reachable via values that pass type guards but fail value constraints. Negative numbers are the canonical example.

### Stub server HTTP/1.1 + explicit Content-Length (not Python's `send_error`)

**Rule 1 deviation (bug).** Initial stub used `BaseHTTPRequestHandler.send_error(405)` for GET. Empirically (curl probe) this yields `curl: (52) Empty reply from server` and `httpx.RemoteProtocolError: Server disconnected without sending a response`. The producer client's `preflight()` then fails → `route_down` short-circuit → all route-up scenarios fail.

Root cause: Python 3.12's `BaseHTTPRequestHandler.send_error` + default `protocol_version = "HTTP/1.0"` interacts poorly with httpx's HTTP/1.1 keep-alive expectations on certain code paths. Fix: set `protocol_version = "HTTP/1.1"` and construct the 405 response explicitly with `send_response` + `send_header("Content-Type", "application/json")` + `send_header("Content-Length", ...)` + `end_headers` + `wfile.write(body)`. Same pattern for the POST 404 branch (defensive — currently unreachable since the smoke script always hits the canonical path).

### Ports 10593/10594 (not plan's 10591/10592)

**Rule 3 deviation (blocking).** Plan specified port 10591 for nonempty stub. Empirically: pre-existing `kontext-service.py` from kais-aigc-platform (PID 5574, unrelated to this work) holds port 10591. Per **scope boundary**, did NOT kill the unrelated service. Switched to free ports 10593 (nonempty) + 10594 (empty), verified free via `ss -tln`.

### Task 2 path: live cross-check (not graceful-skip)

**Decision:** Per prompt's `checkpoint_handling`, the graceful-skip path is the autonomous-mode default when the worktree can't start cleanly. Attempted the live cross-check first (symlinked node_modules + minimal harness). Stub started cleanly, returned byte-identical Phase 10 envelope, producer client integrated without issue. **LIVE path taken** — no deferral needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Scenario 3 corruption changed to actually trigger poisoned-invalidation path**
- **Found during:** Task 1 smoke harness first run (Scenario 3 assertions would have failed)
- **Issue:** Plan's `emotion=123` corruption is silently dropped by `normalize_audio_semantic` isinstance guard → schema probe passes → unlink path never fires.
- **Fix:** Use `word.start=-5` instead — passes type filter, fails schema `minimum:0`.
- **Files modified:** `tests/run_audio_analysis_smoke.sh` (Scenario 3 corruption line + comment explaining the deviation)
- **Verification:** Scenario 3 now logs `invalidated poisoned cache` + unlinks cache file + appends `[audio]` warning. All 3 assertions PASS.
- **Committed in:** `73d257a`

**2. [Rule 1 - Bug] Stub server GET response emits empty reply under Python 3.12 + HTTP/1.0**
- **Found during:** Task 1 first run (preflight failed with `RemoteProtocolError`)
- **Issue:** `BaseHTTPRequestHandler.send_error(405)` + default `HTTP/1.0` protocol yields `curl: (52) Empty reply from server` — httpx interprets as server disconnect.
- **Fix:** Set `protocol_version = "HTTP/1.1"` + construct 405 response explicitly with Content-Length.
- **Files modified:** `tests/audio_analysis_stub_server.py`
- **Verification:** curl probe shows complete 405 response with JSON body; producer client preflight succeeds.
- **Committed in:** `73d257a`

**3. [Rule 3 - Blocking] REPO_ROOT path depth off-by-one**
- **Found during:** Task 1 first run (stub_server.py path resolved to `/home/kai/workspace/tests/...` instead of repo root)
- **Issue:** Plan said `cd $(dirname $0)/../..` assuming tests/ is 2 levels deep. Reality: tests/ is 1 level deep.
- **Fix:** Changed to `cd $(dirname $0)/..`
- **Files modified:** `tests/run_audio_analysis_smoke.sh`
- **Verification:** Script resolves REPO_ROOT correctly; all paths work.
- **Committed in:** `73d257a`

**4. [Rule 3 - Blocking] Stub port 10591 collision with unrelated service**
- **Found during:** Task 1 second run (`OSError: [Errno 98] Address already in use`)
- **Issue:** Pre-existing `kontext-service.py` (PID 5574, kais-aigc-platform) holds port 10591.
- **Fix:** Switched nonempty stub to 10593, empty stub to 10594. Verified free via `ss -tln`.
- **Files modified:** `tests/run_audio_analysis_smoke.sh`
- **Verification:** Both stubs bind cleanly.
- **Committed in:** `73d257a`

---

**Total deviations:** 4 auto-fixed (1 test bug, 1 stub bug, 2 blocking). All necessary to make the plan's literal assertions satisfiable. None changed plan intent. Zero scope creep.

## Issues Encountered

### 1. Pre-existing kais-aigc-platform dev server (PID 745351, port 10588, branch `feat/flowgraph-v3-canvas`)

When Task 2 probed for an already-running audio-analysis route host, found a pre-existing dev server on port 10588 (auto-discovered via `ss -tlnp`). Confirmed it does NOT have audio-analysis mounted (both `/api/production/audio-analysis` and `/api/v1/production/audio-analysis` return `{"message":"API 404 Not Found"}`) — expected, since the cross-repo PR for `feat/audio-analysis-route` is deferred to post-Phase 10 per CONTEXT.md. Did NOT touch this server. Used the worktree's own harness on a separate port (10595) instead.

### 2. Orphan tsx child processes from `npx tsx`

The harness was wrapped in `timeout 25 npx tsx _p12_smoke_harness.ts`. When the parent `timeout` exits, the npm→sh→tsx→node child process chain sometimes survives (different process group). Detected 5 orphan processes via `ps aux | grep _p12_smoke_harness`. Killed via `pkill -f _p12_smoke_harness.ts`. Port 10595 confirmed free afterward.

This is a known `npx` quirk (mirrors Phase 10 SUMMARY "Process cleanup" note). Documented for any future agent that reuses this harness pattern.

## User Setup Required

None. The smoke harness is self-contained (Python 3 stdlib only, no new packages). Operator runs `bash tests/run_audio_analysis_smoke.sh` — that's it.

For the supplementary live cross-repo cross-check (Task 2 pattern), the operator needs:
- The cross-repo worktree at `/tmp/kais-aigc-platform-audio-route` (or recreate via `git worktree add`).
- Main checkout of kais-aigc-platform with `node_modules` present (for symlink).
- The uncommitted `_p12_smoke_harness.ts` snippet (see SUMMARY source — not committed per Phase 10 convention).

These are operator-driven supplementary checks; Task 1's deterministic proof is the SC#4 baseline.

## Known Stubs

None in production code. The stubs in this plan are **test-only fixtures** (frozen snapshots of the Phase 10 envelope):
- `tests/fixtures/audio_analysis_stub_response_empty.json` — byte-snapshot of the Phase 10 stub_mode:true envelope. Intentional test fixture, not a production stub.
- `tests/fixtures/audio_analysis_stub_response_nonempty.json` — shape-correct non-empty envelope for exercising the cache-write + normalize + schema-validate paths. Intentional test fixture.

The actual Phase 10 stub (`kais-aigc-platform:feat/audio-analysis-route`) is documented in `10-02-SUMMARY.md` and deferred to post-Phase 10 cross-repo PR. Not a stub created by this plan.

## Threat Flags

None. No new security-relevant surface introduced:
- T-12-06 (tampering via stub payload): accept+mitigate per plan — client schema-validates normalized payload pre-write (T-12-02 in Plan 01), so a malformed fixture would be caught at the schema gate. Confirmed empirically: Scenario 3 corrupts cache → schema probe catches it → unlink + warning.
- T-12-07 (DoS / port conflict): accept per plan — unique `/tmp/p12-smoke-$$` workdir per run, configurable `--port`, trap-based PID cleanup. Port conflict with kontext-service.py surfaced as `Address already in use` (clear error, not silent false-pass); Rule 3 fix applied (different port).
- T-12-08 (info disclosure via fixture): accept per plan — fixtures contain only synthetic shape-correct data; no real video paths, tokens, or PII. Empty fixture is a byte-snapshot of the already-public Phase 10 stub message.
- T-12-SC (supply chain): accept per plan — zero pip/npm installs. Stub server uses only Python stdlib. Task 2 reused existing `node_modules` via symlink (no install).

## Next Phase Readiness

- **SC#4 (Phase 12 ROADMAP)** is satisfied: producer client `call_audio_analysis.py` (Plan 01) correctly handles the Phase 10 stub envelope (parse + cache + warnings) BEFORE route ML goes live. Proven deterministically (Task 1) + confirmed against live route (Task 2).
- **Phase 14 wires** `call_audio_analysis.py` into `run_pipeline.py:step_audio_semantic` as a subprocess (per `call_audio_analysis.py:85` docstring). The smoke harness gives Phase 14 a deterministic regression target.
- **Phase 15** (audio recomposition) can rely on the cache + warnings sidecar semantics proven here.
- **Cross-repo PR** for `feat/audio-analysis-route` remains deferred to post-Phase 10 per CONTEXT.md. When merged, the producer client will integrate without code changes (contract is firm per Task 2 live cross-check).

### Concerns

- The `_p12_smoke_harness.ts` pattern for live cross-checks is fragile (depends on main checkout's `node_modules` matching the worktree's expected deps). For routine post-merge CI, a proper integration test in `kais-aigc-platform` itself would be more robust. Out-of-scope for Phase 12.
- `normalize_audio_semantic`'s defensive design means the poisoned-cache invalidation path (`call_audio_analysis.py:657-667`) is only reachable via narrowly-crafted cache corruption (e.g., negative numbers). For defense-in-depth this is fine, but it's worth flagging that simple type-confusion corruptions are silently corrected by normalize rather than triggering invalidation. Future Plan might consider validating the RAW cached payload (pre-normalize) for stricter cache integrity — out-of-scope here.

## Self-Check: PASSED

- FOUND: `tests/audio_analysis_stub_server.py` (118 lines, `do_POST` + `do_GET` + `audio-analysis` + `Content-Length` + `application/json` markers present)
- FOUND: `tests/fixtures/audio_analysis_stub_response_empty.json` (byte-identical to Phase 10 stub via `diff`)
- FOUND: `tests/fixtures/audio_analysis_stub_response_nonempty.json` (dialogue + emotion + words + reproduction markers present; schema-valid when data.shots lifted to top-level)
- FOUND: `tests/run_audio_analysis_smoke.sh` (207 lines, `audio_analysis_stub_server\.py` + `audio_semantic.json` + `SCENARIO` + `exit 1` markers present; `call_audio_analysis\.py` link via subprocess invocation)
- FOUND: Task 1 commit `73d257a` in git log
- PASS: `bash tests/run_audio_analysis_smoke.sh` exits 0 with `ALL_SCENARIOS_PASS`
- PASS: Task 2 live cross-check exit 0 (NOT graceful-skip)

---
*Phase: 12-producer-route-client-call-audio-analysis-py*
*Plan: 02*
*Completed: 2026-07-26*
