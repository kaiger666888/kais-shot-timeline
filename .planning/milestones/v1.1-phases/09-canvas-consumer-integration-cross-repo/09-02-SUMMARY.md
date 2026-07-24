---
phase: 09-canvas-consumer-integration-cross-repo
plan: 02
subsystem: contract
tags: [verify-harness, cross-repo, contract-gate, present-06, v1.1]

# Dependency graph
requires:
  - phase: 09-canvas-consumer-integration-cross-repo
    provides: "09-01 consumer verify-canvas-shot-timeline.ts green (27/27) on feat/canvas-asset-collection @ 90812e9d — the script the consumer bridge invokes"
  - phase: 05-08
    provides: "producer-side v1.1 invariants already locked (EIGHT_SHAPES + _producer_registry_integrity + _cross_version_check + _fixture_consistency_check)"
provides:
  - "PRESENT-06 closed: the 3-mode verify_contract.py harness is confirmed green for v1.1 across producer + consumer modes (e2e deferred)"
  - "Cross-repo bridge validated end-to-end: shot-timeline verify_contract.py --mode=consumer → CANVAS_CONSUMER_PATH → npx tsx verify-canvas-shot-timeline.ts (27/27 green)"
affects: [Phase 9 sign-off, canvas-asset-collection PR merge readiness, future cross-version contract bumps]

# Tech tracking
tech-stack:
  added: []  # ZERO source changes — pure confirmation run
  patterns:
    - "Documentation-only confirmation commit: when a plan's expected outcome is 'green unchanged' (CONTEXT D-PRESENT-06-Q1 'No change expected; confirm'), the honest artifact is an --allow-empty docs commit recording the green status — NOT a cosmetic code comment that pretends a change happened"

key-files:
  created:
    - "/data/workspace/kais-shot-timeline/.planning/phases/09-canvas-consumer-integration-cross-repo/09-02-SUMMARY.md (this file — records the 3-mode green confirmation)"
  modified: []  # ZERO source files modified — scripts/verify_contract.py unchanged

key-decisions:
  - "ZERO source change (D-PRESENT-06-Q1 'confirm, no change expected'): producer mode exited 0 unchanged (Phase 5/7/8 invariants already locked the v1.1 producer concerns); consumer mode exited 0 via the v1.0 bridge (version-agnostic exit-code check, no code path depends on the manifest version). The plan's decision tree explicitly sanctions a docs-only --allow-empty commit when both modes are green with no assertion gap."
  - "Did NOT add _producer_registry_snapshot_integrity helper: the plan's step (a) frames it as conditional on producer mode FAILING. Producer mode passed. Additionally, the ep01 producer artifact under test is a v1.0 schema_version='1' asset with NO generator.registry_snapshot, NO data.characters/props, and NO external characters.json/props.json/registry.draft.json — so the hypothetical helper would be a complete no-op (graceful-degrade gated on file existence) against the current test artifact. The build-time gate (export_asset.py / apply_edits.py) already enforces snapshot↔file consistency at emit time; the schema validator already ensures the snapshot is well-formed. Adding a producer-side cross-check would be scope creep beyond what the plan + CONTEXT prescribe."
  - "E2e mode deferred (D-PRESENT-06-Q3): heavy (starts Express backend, POST import-from-dir, SQL read-back). Skipped via --e2e-skip. Documented as the manual post-merge check: PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e (or --mode=all). Mirrors the Phase 6/7 deferred live-route pattern."

patterns-established:
  - "3-mode contract gate closure: when closing a PRESENT-XX contract-verification requirement, run all testable-now modes (producer + consumer) + document the heavy/deferred mode (e2e) with its exact post-merge command. The SUMMARY is the audit trail; the commit records the green status."

requirements-completed: [PRESENT-06]

# Metrics
duration: 1min
completed: 2026-07-25
---

# Phase 9 Plan 02: verify_contract.py 3-Mode Harness Green for v1.1 Summary

**The shot-timeline-side `scripts/verify_contract.py` 3-mode harness is confirmed GREEN for v1.1 across producer + consumer modes — ZERO source changes, the v1.0 bridge infrastructure handled everything Phase 9 needed. E2e mode remains deferred (`--e2e-skip`) as the manual post-merge check. PRESENT-06 closed.**

## Performance

- **Duration:** ~1 min (confirmation run; no code changes to write/test)
- **Started:** 2026-07-24T22:16:40Z
- **Completed:** 2026-07-24T22:17:44Z
- **Tasks:** 1 (Task 1: run producer + consumer modes; extend only if a producer gap is found — none was)
- **Files modified:** 0 source files (documentation-only outcome — the plan's explicitly sanctioned primary path per CONTEXT D-PRESENT-06-Q1)

## Verification Results

All four success-criteria commands exit 0:

| # | Command | Exit | Result |
|---|---------|------|--------|
| 1 | `python3 spec/validate.py` | 0 | minimal=0 failures, v1.1=0 failures, smoke=2 (pre-existing ep03 missing transcript/frames — out of scope, strict-smoke=off) |
| 2 | `python3 scripts/verify_contract.py --mode=producer` | 0 | `asset.json + data shapes schema-valid; v1↔v1.1 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors); v1.1 fixture set cross-file IDs consistent (0 dangling)` |
| 3 | `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer` | 0 | Bridge invoked `npx tsx scripts/verify-canvas-shot-timeline.ts` in the consumer worktree → **27 passed, 0 failed** (20 v1.0 ep01 asserts + 7 v1.1 fixture asserts) |
| 4 | `python3 scripts/verify_contract.py --mode=all --e2e-skip` | 0 | producer OK + consumer OK; e2e skipped (`set PHASE4_RUN_E2E=1 to enable`) |

### Producer mode coverage (already locked in Phase 5/7/8 — confirmed green, no change)

The producer check (`run_producer_check` at `scripts/verify_contract.py:640`) runs four v1.1-aware invariants against the real ep01 asset dir:

1. **`validate_eight_shapes`** (Phase 5 extension) — 9 schemas: the v1.0 6 required shapes + the v1.1 optional `characters`/`props`/`registry` shapes (all optional, graceful-degrade when absent).
2. **`_producer_registry_integrity`** (Phase 7 + Phase 8 extension) — registry↔shots cross-file integrity: canonical ID patterns/uniqueness, `appearance_shots[] ⊆ shots.json`, registry cluster members ⊆ shots, **Pitfall 7 confirmed-only hard gate** (`review_state != "confirmed"` fails), **Pitfall 17 prompt refs ⊆ confirmed IDs** (Phase 8 PROMPT-03). Gated on file existence → no-op for v1.0 assets without registry files.
3. **`_cross_version_check`** (Phase 5 CONTRACT-07) — schema-layer bidirectional v1↔v1.1 compat: forward (v1 fixture vs v1.1-extended schema → 0 errors) + backward (v1.1 fixture vs recovered v1 schema → 0 non-additionalProperties errors).
4. **`_fixture_consistency_check`** (Phase 5 Pitfall C/17) — `spec/fixtures/v1.1/` cross-file ID consistency (prompts refs ⊆ character/prop IDs, appearance_shots ⊆ shot IDs, registry cluster IDs match canonical pattern + ⊆ character+prop IDs).

All four green unchanged. **No v1.1-specific producer assertion was missing.**

### Consumer mode (the bridge — v1.0 infrastructure, version-agnostic)

`run_consumer_check` (`scripts/verify_contract.py:717`) shells out via `subprocess.run(["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"], cwd=consumer, timeout=60)`. The bridge is a pure exit-code check — it does NOT inspect manifest version or assert v1.1-specific behavior itself; it delegates all v1.1 awareness to the consumer verify script (which 09-01 extended). The three v1.0 guards held:

1. `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer` exists + is a git worktree (`.git` file present — T-09-04 mitigation).
2. `scripts/verify-canvas-shot-timeline.ts` exists in the worktree (on `feat/canvas-asset-collection`).
3. Consumer verify exited 0 (27/27 asserts green).

The consumer worktree under test: `feat/canvas-asset-collection` @ `90812e9d` (the 09-01 commit — `feat(canvas): v1.1 ShotTimelineAsset — character/prop child nodes (PRESENT-04/05)`).

### E2e mode (DEFERRED — D-PRESENT-06-Q3)

NOT run in this plan. Heavy: starts Express backend, POST `/api/canvas/v2/import-from-dir`, SQL read-back via `_read_persisted_snapshot`. Skipped via `--e2e-skip` (the default for `--mode=all` unless `PHASE4_RUN_E2E=1`).

**Manual post-merge check (exact command):**
```bash
PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e
# or combined:
PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=all
```
This mirrors the Phase 6/7 deferred live-route pattern. The e2e mode infrastructure is unchanged from v1.0 (Plan 04-02); running it post-merge will exercise the full HTTP-level round-trip including the v1.1 character/prop node emission path through the real backend.

## Accomplishments

- **PRESENT-06 (producer gate):** confirmed green unchanged. The Phase 5/7/8 invariants (EIGHT_SHAPES schema coverage + `_producer_registry_integrity` registry↔shots integrity + Pitfall 7 confirmed-only hard gate + Pitfall 17 prompt-ref integrity + `_cross_version_check` v1↔v1.1 bidirectional schema compat + `_fixture_consistency_check` fixture self-consistency) fully cover the v1.1 producer concerns. No assertion gap found.
- **PRESENT-06 (consumer gate):** confirmed green via the v1.0 bridge. The bridge (`run_consumer_check`) is version-agnostic — it delegates all v1.1 awareness to the consumer verify script, which 09-01 extended to 27/27 green (20 v1.0 ep01 + 7 v1.1 fixture asserts including the 2-character/1-prop node counts, OSS-synthesized thumbnails, stable registry output_keys, and the zero-delivery-leak §7 post-process check).
- **PRESENT-06 (e2e gate):** documented as deferred. The exact manual post-merge command is recorded above.
- **Cross-repo bridge validated end-to-end:** the shot-timeline `verify_contract.py` → `CANVAS_CONSUMER_PATH` → consumer `npx tsx verify-canvas-shot-timeline.ts` chain works as designed in v1.0, with no v1.1 friction. This is the contract-regression net for the two-repo split (shot-timeline = producer/contract authority; `@kais/infinite-canvas` = consumer).

## Task Commits

Per the plan's step (d)/(e) primary path (both modes green + no assertion gap → ZERO source changes), this plan lands a single documentation-only `--allow-empty` commit:

1. **Task 1: confirm 3-mode green + close PRESENT-06** — `docs(contract): PRESENT-06 — record 3-mode verify green for v1.1` (`--allow-empty`; records the green status + e2e deferral).

**Plan metadata:** SUMMARY + STATE + ROADMAP land in the final metadata commit (separate from the per-task commit per GSD protocol).

## Files Created/Modified

- `.planning/phases/09-canvas-consumer-integration-cross-repo/09-02-SUMMARY.md` — this file (records the 3-mode green confirmation + e2e deferral + the decision not to add the hypothetical `_producer_registry_snapshot_integrity` helper).

**ZERO source files modified.** `scripts/verify_contract.py` is unchanged — the v1.0 bridge infrastructure handled all Phase 9 needs (producer invariants locked Phase 5/7/8; consumer bridge version-agnostic).

## Decisions Made

See `key-decisions` frontmatter above. Highlights:

- **ZERO source change (D-PRESENT-06-Q1):** the plan's decision tree is explicit — "If BOTH producer and consumer modes exit 0 with NO new assertion needed: this plan makes ZERO source changes." Both modes exited 0; no assertion gap was found (producer mode was green unchanged from Phase 5/7/8; the ep01 producer artifact under test is a v1.0 asset with no registry_snapshot to cross-check). The documentation-only `--allow-empty` commit is the plan's sanctioned primary path.
- **Did NOT add `_producer_registry_snapshot_integrity`:** the plan frames this helper as conditional on producer mode FAILING. Producer mode passed. Additionally, the helper would be a no-op against the current ep01 test artifact (which has no `generator.registry_snapshot` and no external characters.json/props.json/registry.draft.json). The build-time gate (`export_asset.py` / `apply_edits.py`) already enforces snapshot↔file consistency at emit time. Adding a producer-side cross-check would be scope creep beyond the plan + CONTEXT prescription, with no observable benefit against the current test artifact.
- **E2e deferred (D-PRESENT-06-Q3):** heavy backend round-trip; skipped via `--e2e-skip`. Documented as manual post-merge (mirrors Phase 6/7 pattern).

## Deviations from Plan

None - plan executed exactly as written. The plan's decision tree explicitly sanctioned the documentation-only path; both verification modes passed on the first run with no need for any auto-fix.

## Issues Encountered

None.

## User Setup Required

None for producer + consumer modes (both run without external services — producer is inline schema validation; consumer runs the importer directly via `npx tsx`, no backend).

The deferred e2e mode (the manual post-merge check) requires the consumer worktree's Express backend + better-sqlite3 — already operational from Phase 4/6/7.

## Next Phase Readiness

- **PRESENT-06 fully delivered** (producer + consumer green; e2e deferred with documented post-merge command). This closes the Phase 9 contract-verification gate.
- **Phase 9 (Wave 2) complete:** 09-01 shipped the consumer v1.1 extension (27/27 green); 09-02 confirms the cross-repo bridge harness is green for v1.1. The `feat/canvas-asset-collection` PR is ready for merge review (carries both v1.0 + v1.1 consumer work; the v1.0 WIP `prompts.json`/`action_chains.json` remains preserved for the user to commit separately).
- **Post-merge follow-ups:** (1) run the deferred e2e mode (`PHASE4_RUN_E2E=1 ...`); (2) optional canvas visual pilot — open the canvas UI against an imported v1.1 asset and confirm the 🧑/🔧 nodes render under the p13 zone with thumbnails.

## Known Stubs

None. No source files were modified; no stubs introduced.

## Self-Check: PASSED

- FOUND: 09-02-SUMMARY.md (this file)
- FOUND: `python3 spec/validate.py` exit 0
- FOUND: `python3 scripts/verify_contract.py --mode=producer` exit 0
- FOUND: `CANVAS_CONSUMER_PATH=/data/workspace/kst-canvas-consumer python3 scripts/verify_contract.py --mode=consumer` exit 0 (27/27 consumer asserts green)
- FOUND: `python3 scripts/verify_contract.py --mode=all --e2e-skip` exit 0
- FOUND: consumer worktree on `feat/canvas-asset-collection` @ `90812e9d` (09-01 commit present)
- FOUND: ZERO source files modified (documentation-only outcome — `git status` clean before the docs commit)

---
*Phase: 09-canvas-consumer-integration-cross-repo*
*Plan: 02 (PRESENT-06)*
*Consumer bridge target: feat/canvas-asset-collection @ 90812e9d*
*Completed: 2026-07-25*
