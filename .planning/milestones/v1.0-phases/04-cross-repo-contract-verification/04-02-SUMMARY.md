---
phase: 04-cross-repo-contract-verification
plan: 02
subsystem: testing
tags: [e2e, cross-repo, sqlite, backend-lifecycle, capstone, tdd]

requires:
  - phase: 04-cross-repo-contract-verification
    provides: scripts/verify_contract.py 04-01 harness (producer/consumer/self-test + find_free_port pre-defined)
  - phase: 03-canvas-consumer
    provides: worktree /data/workspace/kst-canvas-consumer (import-from-dir.ts POST route + appendAndSync + verify-canvas-shot-timeline.ts + pinned golden + Phase 3 leftover 9001/9001)
  - phase: 02-export-and-asset-emission
    provides: output/虫虫武侠…第01话…/asset.json (real producer ep01, schema_version="1", 93 shots)
  - phase: 01-contract-spec
    provides: spec/schemas/*.schema.json (6 schemas — e2e implicitly exercises them via the asset it consumes)
provides:
  - "scripts/verify_contract.py run_e2e_check —— backend lifecycle + POST import-from-dir + SQL read-back + structural asserts + 3-layer teardown (3-mode + self-test harness complete)"
  - ".planning/phases/04-cross-repo-contract-verification/04-VERIFICATION.md —— Phase 4 capstone (status: passed; WR-01/04 formally accepted; SC-1 prompt-children scope reduction recorded; Phase 3 deferred-items closed)"
affects: [v1.0 milestone sign-off]

tech-stack:
  added: []  # zero new packages — sqlite3/time/urllib all Python stdlib, pre-installed
  patterns:
    - "Backend lifecycle via subprocess.Popen + start_new_session=True + os.killpg teardown (Rule 1 fix: npx tsx forks child node process; SIGTERM-only leaves orphan)"
    - "SQL 直查 o_agentWorkData JSON blob (Pitfall 1: load-v2 HTTP reads relational canvas_nodes which import-from-dir doesn't write → returns null)"
    - "Parameterized sqlite3 ? placeholders (T-04-01-T2 mitigation: never shell-interpolate projectId/episodesId)"
    - "UTF-8 encoded JSON body bytes (Pitfall 6: ep01 workdir path has CJK + full-width punctuation)"
    - "stdout=DEVNULL on backend subprocess (Pitfall 7: avoid pipe-buffer deadlock during boot/console.log spam)"
    - "3-layer teardown: terminate → wait(10) → killpg(SIGKILL) → wait(2) reap + git checkout database.d.ts reconcile + parameterized DELETE own rows"

key-files:
  created:
    - .planning/phases/04-cross-repo-contract-verification/04-VERIFICATION.md
  modified:
    - scripts/verify_contract.py  # +216 / -18 lines (682 total): run_e2e_check + _poll_health + _read_persisted_snapshot + main() e2e dispatch

key-decisions:
  - "Backend teardown uses start_new_session=True + os.killpg, not bare proc.terminate() —— Rule 1 auto-fix: npx tsx spawns a child node process; SIGTERM-only on npx leaves orphan node backend running on the port"
  - "e2e uses NODE_ENV=dev + npx tsx src/app.ts (matches Phase 3 verify pattern; teardown `git checkout -- src/types/database.d.ts` reconciles auto-regen noise)"
  - "SQL 直查 o_agentWorkData JSON blob is the only non-invasive read-back path (RESEARCH Pitfall 1) —— /api/canvas/v2/load-v2 reads relational canvas_nodes table which import-from-dir doesn't write"
  - "seq_edges assertion uses data.linkType field (Phase 3 producer literal shape {dataType:'data', data:{linkType:'sequence'}}) —— directly validates WR-01 (sequence edges survive primary appendAndSync path)"
  - "timestamp-based pid/eid (int(time.time()), +1) avoids colliding with Phase 3 leftover 9001/9001; teardown DELETEs only own rows via parameterized WHERE clause"
  - "SC-1 prompt-children scope reduction formally recorded in 04-VERIFICATION.md —— Phase 3 D3 discretion deferred prompts/transcript to sidecar data refs, so observable collection = storyboard/audio/video (not a gap)"
  - "WR-01/04 formally accepted (not fixing in v1.0) —— primary appendAndSync path unaffected (no Zod-parse); save-v2 latent bugs belong to consumer-repo backlog"

patterns-established:
  - "Bracketed [e2e] logging for backend lifecycle progress lines"
  - "Tuple[bool, str] return shape consistent with producer/consumer/self-test modes (main() collects + formats uniformly)"
  - "Assertion block wrapped in try/except AssertionError → returns (False, msg) without raising (matches existing harness pattern)"

requirements-completed: [VERIFY-01]

duration: 7min
completed: 2026-07-20
---

# Phase 4 Plan 02: E2E Mode + Capstone Verification Summary

**Real-producer-asset e2e (backend lifecycle + POST import-from-dir + SQL read-back on o_agentWorkData + structural asserts + 3-layer teardown) + capstone report formally accepting WR-01/04 and recording SC-1 scope reduction.**

## Performance

- **Duration:** ~7 min (388s wall)
- **Started:** 2026-07-20T19:39:38Z
- **Completed:** 2026-07-20T19:46:06Z (approx)
- **Tasks:** 2
- **Files modified:** 2 (scripts/verify_contract.py +216/-18 lines; 04-VERIFICATION.md +180 lines new)

## Accomplishments

- **Task 1 e2e mode (VERIFY-01):** `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` boots consumer Express backend (`npx tsx src/app.ts` in CANVAS_CONSUMER_PATH, NODE_ENV=dev, ephemeral port via find_free_port) → polls `/health` until 200 → POSTs `/api/canvas/v2/import-from-dir` with body `{projectId, episodesId, workdir=<real ep01 asset dir>, mode:"replace"}` (UTF-8 encoded JSON bytes; timestamp-based pid/eid avoid colliding with Phase 3 leftover 9001/9001) → SQL直查 `data/db2.sqlite` `SELECT data FROM o_agentWorkData WHERE projectId=? AND episodesId=? AND key='canvasGraph'` (parameterized) → asserts 1 zone + N storyboard + 3 audio + ≥1 video + (N-1) sequence edges → teardown (3-layer proc-group kill + git checkout database.d.ts + parameterized DELETE own rows).
- **WR-01 验证 (primary 路径 sequence edges 存活):** e2e SQL read-back returns snapshot with 92 sequence edges (data.linkType='sequence'), matching N-1 where N=93 storyboards. This proves the primary `appendAndSync` path (event log → JSON blob snapshot) does not strip sequence edge data — only the secondary `save-v2` path does (via FlowLinkV2Schema safeParse).
- **Backend lifecycle leak-free:** `start_new_session=True` + `os.killpg` teardown (Rule 1 fix) — first implementation used bare `proc.terminate()` which left orphan `node tsx` child process (npx spawns a child). pgrep returns empty after teardown.
- **Worktree clean after teardown:** `git -C ... checkout -- src/types/database.d.ts` reverts dev-mode regen noise (auto-triggered by `initKnexType` under NODE_ENV=dev). `git status --short` empty.
- **Phase 3 leftover preserved:** e2e uses own timestamp pid/eid; teardown DELETE WHERE projectId=? AND episodesId=? only removes own rows. `SELECT count(*) ... WHERE projectId='9001'` returns 1 before and after.
- **Task 2 capstone (04-VERIFICATION.md):** 180 lines covering SC-1 (with prompt-children scope reduction recorded per Phase 3 D3), SC-2 (4-mode regression coverage), Requirements Coverage (VERIFY-01/02), WR-01/04 formal acceptance (cross-references Phase 3 deferred-items.md), 3-mode + self-test运行结果, Phase 3 deferred-items闭环 status. `status: passed`, `score: 8/8`.

## Task Commits

Each task committed atomically (TDD RED + GREEN for Task 1):

1. **Task 1 RED:** `test(04-02): add run_e2e_check stub + wire e2e dispatch (TDD RED)` — `a506093` (84 inserts, 11 deletes)
2. **Task 1 GREEN:** `feat(04-02): implement run_e2e_check end-to-end (TDD GREEN)` — `21654f2` (216 inserts, 18 deletes)
3. **Task 2:** `docs(04-02): write Phase 4 capstone verification report` — `d97e3b9` (180 inserts, new file)

**TDD Gate Compliance:** Task 1 has `tdd="true"`. git log shows: `test(04-02): ...TDD RED` (a506093) → `feat(04-02): ...TDD GREEN` (21654f2). RED gate verifies `--mode=e2e` fails predictably (exit 1 + "TDD RED" message); GREEN gate verifies it passes (exit 0 + snapshot structural asserts green). No REFACTOR commit needed (clean implementation, no followup cleanup warranted).

## Verification Results

All plan-level verification commands from 04-02-PLAN.md `<verification>` section executed green:

| # | Command | Expected | Actual |
|---|---------|----------|--------|
| 1 | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | exit 0 + snapshot 结构汇总含「seq edges (WR-01 data survives primary path)」 | ✅ exit 0 — 99 nodes / 190 links / 1 zone / 93 storyboard / 3 audio / 2 video / 92 seq edges |
| 2 | `pgrep -af "tsx src/app.ts" \| grep -v grep` | 空 (无 orphan backend) | ✅ empty |
| 3 | `git -C /data/workspace/kst-canvas-consumer status --short src/types/database.d.ts` | 空 (reconcile 成功) | ✅ empty |
| 4 | `sqlite3 ... SELECT count(*) FROM o_agentWorkData WHERE projectId='9001' AND episodesId='9001'` | 1 (Phase 3 leftover 保留) | ✅ 1 |
| 5 | `sqlite3 ... SELECT count(*) FROM o_agentWorkData WHERE projectId NOT IN ('9001')` | 0 (e2e own rows cleaned) | ✅ 0 |
| 6 | `PHASE4_RUN_E2E=1 PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py` | exit 0 (3 mode + self-test 全绿) | ✅ exit 0 (self-test + producer + consumer + e2e all OK) |
| 7 | `test -f 04-VERIFICATION.md && grep -c "WR-01\|WR-04\|SC-1\|VERIFY-01\|VERIFY-02\|deferred-items"` | exists + ≥6 key refs | ✅ 180 lines + 38 key refs |

## Threat Model Mitigation Coverage

All `mitigate` dispositions from 04-02-PLAN.md `<threat_model>` applied:

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-04-01-T2 (Tampering: SQL injection via projectId/episodesId) | sqlite3 parameterized `?` placeholders in SELECT + DELETE; harness generates own timestamp-based int (no user input) | ✅ Applied (_read_persisted_snapshot + teardown c) |
| T-04-02-T2 (DoS: Backend subprocess leak) | try/finally 3-layer: killpg(SIGTERM) → wait(10) → killpg(SIGKILL) → wait(2); PLUS start_new_session=True so killpg reaches child node | ✅ Applied + Rule 1 fix (extended beyond check_range.py template — original was insufficient for npx+tsx child-forking) |
| T-04-03-T2 (DoS: Pipe-buffer deadlock) | stdout=DEVNULL + stderr=DEVNULL | ✅ Applied (Popen arg) |
| T-04-04-T2 (Info Disclosure: Stale test rows) | teardown parameterized DELETE o_agentWorkData + kv_canvasEvent WHERE own pid/eid | ✅ Applied (verified sqlite count = 0 for non-9001) |
| T-04-05-T2 (Tampering: database.d.ts dev regen) | teardown `git -C consumer checkout -- src/types/database.d.ts` (best-effort, capture_output) | ✅ Applied (verified `git status --short` empty) |
| T-04-06-T2 (DoS: Port conflict) | find_free_port() ephemeral bind 127.0.0.1:0 | ✅ Applied (port 47155, 57421, 35307 across runs — all ephemeral) |
| T-04-07-T2 (Tampering: malicious CANVAS_CONSUMER_PATH) | Guard: os.path.isdir + .git file/dir check | ✅ Applied (run_e2e_check entry guard) |
| T-04-08-T2 (Repudiation: residual backend/rows) | try/finally teardown + pgrep/sqlite count post-run verify | ✅ Applied (commands 2/3/4/5 in verification table above) |
| T-04-SC (npm/pip/cargo poisoning) | N/A — zero new packages installed (sqlite3/time/urllib.* all Python stdlib, pre-installed) | ✅ N/A |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Backend teardown extended with start_new_session + os.killpg**
- **Found during:** Task 1 GREEN run
- **Issue:** Original plan template (check_range.py L104-118) used bare `proc.terminate()` → wait(10) → kill(). For `npx tsx src/app.ts`, this is insufficient: npx spawns a child node process (the actual backend server). SIGTERM on npx parent does not propagate to the child node process, leaving an orphan backend running on the port.
- **Evidence:** `pgrep -af "tsx src/app.ts"` showed PID 311399 still running after first e2e teardown.
- **Fix:** `subprocess.Popen(..., start_new_session=True)` puts npx+child in a process group (PGID = proc.pid). Teardown uses `os.killpg(pgid, SIGTERM)` then `os.killpg(pgid, SIGKILL)` to clean the entire group atomically. Pattern documented in teardown comment with Rule 1 attribution.
- **Files modified:** scripts/verify_contract.py (Popen line + teardown a block)
- **Commit:** `21654f2`

No other deviations. Plan executed as written for everything else.

## Known Stubs

None. The e2e mode is fully implemented — backend lifecycle, POST, SQL read-back, structural asserts, teardown all functional. The 04-01 e2e placeholder has been replaced. No deferred functionality remains in scripts/verify_contract.py.

## TDD Gate Compliance

Task 1 has `tdd="true"` in the plan frontmatter. Following the RED/GREEN/REFACTOR cycle:

- **RED gate** (`a506093`): Added `_poll_health` + `_read_persisted_snapshot` as real helpers (they're pure utility functions, not the unit under test). Added `run_e2e_check` as a STUB returning `(False, "TDD RED ...")`. Wired main() dispatch. Verified `python3 scripts/verify_contract.py --mode=e2e` exits 1 with "TDD RED" message; `--mode=all` (default) skips e2e and exits 0. RED gate confirmed the test infrastructure works before writing the implementation.

- **GREEN gate** (`21654f2`): Replaced `run_e2e_check` stub with full implementation. Verified `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` exits 0 with snapshot structural asserts green.

- **REFACTOR gate**: Not warranted — GREEN implementation is clean (single function, clear sections, no duplication). No refactor commit needed.

Both gates present in git log: `test(04-02):` (RED) precedes `feat(04-02):` (GREEN). **TDD gate compliance: PASSED.**

## Self-Check: PASSED

- `scripts/verify_contract.py` exists (682 lines, ≥ 350 minimum). ✅
- `grep -c "run_e2e_check\|_poll_health\|_read_persisted_snapshot" scripts/verify_contract.py` = 8 (3 def + 5 call/ref, ≥ 6 minimum). ✅
- `.planning/phases/04-cross-repo-contract-verification/04-VERIFICATION.md` exists (180 lines, ≥ 80 minimum). ✅
- 04-VERIFICATION.md key refs: 38 (≥ 6 minimum covering VERIFY-01/02/WR-01/04/SC-1/scope reduction/deferred-items/appendAndSync). ✅
- 04-VERIFICATION.md sections: 5 (`## 1.` through `## 5.`, ≥ 4 minimum). ✅
- 04-VERIFICATION.md frontmatter: `status: passed`, `score: 8/8`, `deferred: [...]` populated with WR-01/04 addressed_in Phase 4. ✅
- Commit `a506093` exists (Task 1 RED). ✅
- Commit `21654f2` exists (Task 1 GREEN). ✅
- Commit `d97e3b9` exists (Task 2 capstone). ✅
- All 7 plan-level verification commands pass (see table above). ✅
