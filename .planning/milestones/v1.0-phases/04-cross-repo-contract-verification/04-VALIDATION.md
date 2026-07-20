---
phase: 4
slug: cross-repo-contract-verification
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 4 — Validation Strategy

> Per-phase validation contract. Source: `04-RESEARCH.md` §Validation Architecture.
> No pytest — single Python harness `scripts/verify_contract.py` with 3 modes (producer/consumer/e2e), shot-timeline standalone-script style. e2e is env-gated (`PHASE4_RUN_E2E=1`) since it starts the consumer backend.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python stdlib `assert` + `subprocess` + `urllib`/`sqlite3` (no pytest; matches shot-timeline standalone-script convention) |
| **Config file** | none (harness self-contains argparse + assert + sys.exit) |
| **Quick run command** | `python3 scripts/verify_contract.py --mode=producer` (seconds, pure Python + jsonschema) |
| **Medium run command** | `python3 scripts/verify_contract.py --mode=consumer` (~5s, npx tsx startup overhead) |
| **Full suite command** | `python3 scripts/verify_contract.py` (default `--mode=all`; e2e included only if `PHASE4_RUN_E2E=1`) |
| **E2E command** | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` (~30s, start backend + POST + SQL read-back) |
| **Estimated runtime** | producer ~2s · consumer ~5s · e2e ~30s |

---

## Sampling Rate

- **After every task commit:** `python3 scripts/verify_contract.py --mode=producer` (catches producer drift)
- **After every wave:** `python3 scripts/verify_contract.py --mode=producer --mode=consumer`
- **Before `/gsd:verify-work`:** `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py` (all 3 modes green)
- **Max feedback latency:** 30s (e2e); 5s (unit modes)

---

## Per-Task Verification Map

> Task IDs populate when PLAN.md is written. From research §Validation Architecture.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | VERIFY-02 (producer) | — | N/A | unit (jsonschema) | `python3 scripts/verify_contract.py --mode=producer` — asset.json schema-valid (6 schemas) | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | VERIFY-02 (producer drift) | — | N/A | self-test (opt) | `PHASE4_SELF_TEST=1 ... --mode=producer` — corrupt asset → exit 1 | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | VERIFY-02 (consumer) | — | N/A | unit (pure fn) | `python3 scripts/verify_contract.py --mode=consumer` — shells to Phase 3 verify-canvas-shot-timeline.ts (17 asserts) | ✅ Phase 3 | ⬜ pending |
| TBD | 01 | 1 | VERIFY-01 (e2e) | — | backend lifecycle no-leak (try/finally) | e2e (HTTP+SQL) | `PHASE4_RUN_E2E=1 ... --mode=e2e` — POST import-from-dir → SQL read-back o_agentWorkData → assert 1 zone + N storyboard + 3 audio + 1 video + sequence edges | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | VERIFY-01 (WR-01/04 primary path) | — | N/A | e2e (SQL) | e2e asserts 92 sequence edges survive in snapshot (WR-01 latent on save-v2 only, not primary) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `scripts/verify_contract.py` — NEW (this repo), single script 3 modes (~250–350 lines)
- [ ] Reconcile worktree dirty `src/types/database.d.ts` (auto-regen noise from yarn install postinstall; `git checkout --` in teardown per research)
- [ ] Real ep01 asset dir for e2e — already exists (`output/虫虫武侠小故事《小江湖》第01话：…/asset.json`); zero new
- [ ] (optional) self-test mode — planner decides v1.0 scope

*No existing test/config files modified — Phase 4 is all-new; Phase 1–3 verification infra reused.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual canvas render (zone + children + blue sequence arrows) | VERIFY-01 (spirit) | Requires browser; the e2e proves the persisted graph structure via SQL, not pixels | Optional: after e2e, open the canvas for (projectId, episodesId), confirm zone wraps the collection + sequence arrows visible. Not blocking — SQL read-back is the observable e2e evidence |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: producer mode runs every task commit
- [x] Wave 0 covers all MISSING references (verify_contract.py + worktree reconcile)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-21 (post research; Dimension 8 covered by producer/consumer/e2e modes; `wave_0_complete` flips true after verify_contract.py lands)
