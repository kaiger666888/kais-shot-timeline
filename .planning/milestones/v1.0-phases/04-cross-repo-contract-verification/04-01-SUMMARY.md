---
phase: 04-cross-repo-contract-verification
plan: 01
subsystem: testing
tags: [contract, regression, jsonschema, cross-repo, harness, verify]

requires:
  - phase: 01-contract-spec
    provides: spec/schemas/*.schema.json (6 schemas, machine-checkable truth)
  - phase: 02-export-and-asset-emission
    provides: scripts/export_asset.py + real ep01 output/asset.json + scripts/check_range.py (server lifecycle analog)
  - phase: 03-canvas-consumer
    provides: worktree /data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts (17 asserts A-F + E2 + F2)
provides:
  - "scripts/verify_contract.py —— canonical regression harness (3 modes + self-test + find_free_port)"
  - "Producer mode: inline Draft202012Validator on 6 schemas (asset + 5 data shapes) against real ep01 asset"
  - "Consumer mode: subprocess shell-out to Phase 3 verify-canvas-shot-timeline.ts"
  - "Self-test mode (PHASE4_SELF_TEST=1): injects schema_version='v1' corrupt asset, asserts harness fail-loud"
  - "find_free_port helper pre-defined for Plan 04-02 e2e mode"
affects: [04-02 (e2e mode implementation), v1.0 milestone sign-off]

tech-stack:
  added: []  # zero new packages — jsonschema 4.26.0 already system-installed
  patterns:
    - "3-mode single-script orchestrator (producer/consumer/e2e) with env-gated opt-in"
    - "Inline Draft202012Validator on 6 schemas (vs subprocess to spec/validate.py which excludes asset shape)"
    - "Self-test meta-check: inject deliberate drift → assert harness detects (fail-loud regression proof)"
    - "Cross-repo worktree parameterization via CANVAS_CONSUMER_PATH env var"

key-files:
  created:
    - scripts/verify_contract.py
  modified: []

key-decisions:
  - "Inline jsonschema (not subprocess to spec/validate.py) for asset shape validation — spec/validate.py SMOKE_SHAPES L49 excludes asset, subprocess would silently pass invalid manifests"
  - "Self-test semantics: PASS = harness detects drift (exit 0); FAIL = harness broken (exit 1). Aligned with RESEARCH §Regression Invariants — meta-test of the fail-loud property"
  - "e2e mode = placeholder in 04-01 (sys.exit-style message; --mode=all silently skips). Plan 04-02 implements real e2e (HTTP POST + SQL read-back)"
  - "find_free_port pre-defined in 04-01 even though unused — so 04-02 e2e doesn't need to edit this file"
  - "Self-test runs BEFORE producer in main() — harness integrity gates trustworthiness of producer PASS result"
  - "Cross-repo guard: CANVAS_CONSUMER_PATH must exist + be a git worktree (T-04-01-T1 mitigation — refuses silent pass on malicious/non-worktree path)"

patterns-established:
  - "Bracketed [verify-contract]/[producer]/[consumer]/[self-test] logging (CLAUDE.md convention)"
  - "Tuple[bool, str] return shape for all check functions — main() collects + formats uniformly"
  - "Atomic JSON write for self-test temp corruption (tmp + os.replace, ensure_ascii=False)"
  - "try/finally + shutil.rmtree(ignore_errors=True) for temp cleanup (T-04-03-T1)"

requirements-completed: [VERIFY-02]

duration: 12min
completed: 2026-07-20
---

# Phase 4 Plan 01: Contract Verification Harness (Producer + Consumer + Self-Test) Summary

**Single-file Python harness that gates producer↔consumer contract alignment via 6-schema inline validation (producer) + Phase 3 17-assert shell-out (consumer) + deliberate-drift self-test (fail-loud proof).**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-20T19:33:04Z
- **Completed:** 2026-07-20T19:45:00Z (approx)
- **Tasks:** 2
- **Files modified:** 1 (scripts/verify_contract.py, 425 lines)

## Accomplishments

- **Producer mode (VERIFY-02 producer side):** Real ep01 asset (`output/虫虫武侠小故事《小江湖》第01话…/asset.json`, schema_version="1", 93 shots) passes inline `Draft202012Validator` across all 6 schemas (asset + shots + audio_analysis + transcript + frames + prompts). Inlined (not subprocess) because `spec/validate.py:49` `SMOKE_SHAPES` deliberately excludes asset — subprocess would let invalid manifests silently pass.
- **Consumer mode (VERIFY-02 consumer side):** `subprocess.run(["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"], cwd=CANVAS_CONSUMER_PATH)` shells out to Phase 3 worktree. 19 sub-asserts all green (CANVAS-01 structure + CANVAS-02 sequence chain + CANVAS-03 Zod/additive-only + F roundtrip + F2 WR-07 filePath synthesis).
- **Self-test mode (RESEARCH §Regression Invariants):** `PHASE4_SELF_TEST=1` injects a copy of ep01 asset into `/tmp/phase4-selftest-*/`, corrupts `schema_version` `"1" → "v1"` (violates asset.schema.json L13 pattern `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`), runs `validate_asset_json`, asserts ≥1 error returned. Confirms harness fail-loud — without this, future producer drift could silently break the contract. Real ep01 bytes untouched (T-04-04-T1 mitigation). Temp dir cleaned via try/finally (T-04-03-T1).
- **e2e placeholder:** `--mode=e2e` returns actionable "not implemented yet, see Plan 04-02"; `--mode=all` (default) silently skips e2e so the default invocation doesn't fail.
- **find_free_port pre-defined** (per scripts/check_range.py:32-36 analog) — Plan 04-02 e2e mode will use it without editing this file.
- **Defense guards:** `CANVAS_CONSUMER_PATH` must exist + be a git worktree (file or dir `.git`). `/nonexistent` → actionable Chinese error. `/tmp` → "not a git worktree". (T-04-01-T1 mitigation.)

## Task Commits

Each task was committed atomically:

1. **Task 1: skeleton + producer + consumer modes** — `459b9b2` (feat)
2. **Task 2: PHASE4_SELF_TEST=1 self-test mode** — `cccb62d` (feat)

**Plan metadata:** (pending — see final commit)

## Files Created/Modified

- `scripts/verify_contract.py` (425 lines) — canonical Phase 4 contract verification harness:
  - Module docstring (Chinese) describing 3 modes + 4 env vars + exit codes
  - Constants: `REPO`, `SCHEMAS_DIR`, `DEFAULT_CONSUMER_PATH`, `DEFAULT_E01_ASSET_DIR`, `SIX_SHAPES`
  - `find_free_port()` (pre-defined for 04-02)
  - `_resolve_canonical_video(asset_dir)` (symlink target resolution for PHASE4_RE_EXPORT=1)
  - `validate_asset_json(asset_path) → list[dict]` (inline Draft202012Validator on asset shape; returns errors list, doesn't sys.exit — reusable by self-test)
  - `validate_six_shapes(asset_dir, manifest) → list[str]` (iterates 6 schemas, returns failures list)
  - `run_producer_check(args) → tuple[bool, str]` (locates ep01 asset, optional re-export, 6-schema validate)
  - `run_consumer_check(args) → tuple[bool, str]` (worktree guards + shell-out to Phase 3 verify)
  - `run_self_test(args) → tuple[bool, str]` (temp dir + corrupt + assert ≥1 error + cleanup)
  - `main()` — argparse `--mode {producer,consumer,e2e,all}`, `--consumer-path`, `--e2e-asset-dir`, `--e2e-skip`; dispatches + prints summary table + exit code

## Verification Results

All plan-level verification commands from 04-01-PLAN.md `<verification>` section executed green:

| # | Command | Expected | Actual |
|---|---------|----------|--------|
| 1 | `python3 scripts/verify_contract.py --mode=producer` | exit 0 + "[producer] asset.json + 5 data shapes all schema-valid" | ✅ exit 0 |
| 2 | `python3 scripts/verify_contract.py --mode=consumer` | exit 0 + "[consumer] Phase 3 17 asserts all green" | ✅ exit 0 (19 sub-asserts) |
| 3 | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | exit 0 + "[self-test] PASS: corrupt asset correctly rejected" | ✅ exit 0 (1 error detected) |
| 4 | `python3 scripts/verify_contract.py` (default `--mode=all`) | exit 0, e2e placeholder skipped | ✅ exit 0 |
| 5 | `CANVAS_CONSUMER_PATH=/tmp python3 scripts/verify_contract.py --mode=consumer` | exit 1 + actionable Chinese error | ✅ exit 1 "not a git worktree" |

## Threat Model Mitigation Coverage

All `mitigate` dispositions from 04-01-PLAN.md `<threat_model>` applied:

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-04-01-T1 (Tampering: CANVAS_CONSUMER_PATH → malicious repo) | Guard: `os.path.isdir` + `.git` file/dir check; actionable Chinese `sys.exit` | ✅ Applied (run_consumer_check guards) |
| T-04-02-T1 (Tampering: subprocess injection via CJK path) | All `subprocess.run` use list argv (no `shell=True`) | ✅ Applied (both producer re-export + consumer shell-out) |
| T-04-03-T1 (Info Disclosure: self-test temp residue) | `try/finally + shutil.rmtree(temp_dir, ignore_errors=True)` | ✅ Applied (run_self_test) — verified `/tmp/phase4-selftest-*` empty after run |
| T-04-04-T1 (Tampering: self-test mutates real ep01) | Operates on `shutil.copy2` copy in temp dir; real `output/asset.json` untouched | ✅ Applied — verified `git diff --quiet output/` exit 0 |
| T-04-05-T1 (Repudiation: no audit trail) | All modes bracketed `[verify-contract]/[producer]/[consumer]/[self-test]` prints + summary table | ✅ Applied |
| T-04-SC (npm/pip/cargo poisoning) | N/A — zero new packages installed | ✅ N/A (jsonschema 4.26.0 system pre-installed) |

## Deviations from Plan

None — plan executed exactly as written. The harness core + producer + consumer + self-test modes all match the `<action>` specification verbatim. The e2e placeholder is intentionally minimal (per plan: "本 plan 不实现 e2e mode —— 它在 04-02 落地").

## Known Stubs

- **e2e mode placeholder:** `scripts/verify_contract.py:298` (in `main()` e2e branch) returns `"e2e not implemented yet — see Plan 04-02"` when invoked explicitly via `--mode=e2e`, and prints a skip notice under `--mode=all`. **Intentional:** Plan 04-01 scope is producer + consumer + self-test only. **Resolve:** Plan 04-02 Task 1 will implement the real e2e (start Express backend + POST `/api/canvas/v2/import-from-dir` + SQL read-back on `o_agentWorkData` + try/finally teardown). The `find_free_port` helper is already in place so 04-02 doesn't need to edit this file's preamble.

## Self-Check: PASSED

- `scripts/verify_contract.py` exists (425 lines, ≥ 200 minimum). ✅
- `grep -c "run_producer_check\|run_consumer_check\|run_self_test\|validate_asset_json\|find_free_port\|main" scripts/verify_contract.py` = 8 (all required helpers + main defined). ✅
- Commit `459b9b2` exists (Task 1). ✅
- Commit `cccb62d` exists (Task 2). ✅
- All 5 plan-level verification commands pass (see table above). ✅
