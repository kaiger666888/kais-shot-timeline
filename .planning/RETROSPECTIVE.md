# Retrospective — kais-shot-timeline

## Milestone: v1.0 — ShotTimelineAsset Contract

**Shipped:** 2026-07-20
**Phases:** 4 | **Plans:** 7 | **Tasks:** 13 | **Commits:** ~62 work commits

### What Was Built

A repo-agnostic ShotTimelineAsset format contract spanning two repos (loose coupling):
- **Phase 1:** 6 JSON Schemas (draft 2020-12) + 455-line bilingual SPEC.md + validate.py — the contract both sides implement against
- **Phase 2:** `scripts/export_asset.py` (manifest + canonical symlinks + inline jsonschema) + `run_pipeline.py:step_export` + `serve.py` FD-leak fix + `check_range.py` — the producer (additive-only over validated detection/transcription/separation baseline)
- **Phase 3** (cross-repo kais-aigc-platform): `import-from-dir.ts` ShotTimelineAsset branch — ingests asset.json → 1 zone + N storyboard + 3 audio + 1 video + sequence edges, reusing the canvas's existing 5 renderers (no contract bump)
- **Phase 4:** `scripts/verify_contract.py` — 3-mode canonical harness (producer/consumer/e2e) + self-test, proving real producer→consumer flow + drift regression both directions

### What Worked

- **Goal-backward verification with live evidence.** Every phase verified by RUNNING (export → schema validate, e2e → SQL read-back, self-test → corrupt-asset fail-loud), not by trusting SUMMARY claims. The gsd-verifier + gsd-code-reviewer agents caught real bugs (Phase 2 FD-leak root cause, Phase 4 CR-01 KeyError + CR-02 teardown race) that SUMMARYs missed.
- **Smart-discuss grey-area batching.** Proposing recommended answers with alternatives in a single AskUserQuestion per phase kept autonomy moving without rubber-stamping — the user accepted recommendations 100% but had override at every decision.
- **Research corrections > CONTEXT prose.** In all three executable phases, the researcher's live verification CORRECTED CONTEXT.md assumptions (Phase 2 FD-leak root cause, video.mp4 symlink target, validate.py SMOKE exclusion; Phase 3 buildPhaseTree canvasType constraint + persistence dual-track; Phase 4 o_agentWorkData vs load-v2). Plans followed research, not CONTEXT prose, where they conflicted.
- **Worktree isolation for the cross-repo consumer.** A clean worktree of kais-aigc-platform from origin/master kept the concurrent ltx work on master untouched and Phase 3's diff clean.

### What Was Inefficient

- **Phase 2 executor wiped ep03 caches** (`--force + --skip-detect` combo) triggering a background Whisper regen that failed (backend quota/Whisper issue) — left ep03 half-written. Mitigated by using ep01 as the stable test target, but the data-dir caveat surfaced repeatedly in later audits.
- **Context budget on deep phases.** Phase 3 (cross-repo, 1502-line importer + 5 renderers + Zod) and Phase 4 (e2e backend + SQL) pushed planner to split into 2 plans each to stay under context targets — correct calls, but the 2-plan split adds plan-checker/review overhead.
- **One quota 429 mid-Phase-4** paused the run ~1.5h. Resume was clean (CONTEXT committed, just re-ran research) but the interruption cost wall-clock.

### Patterns Established

- **ShotTimelineAsset is the canonical "asset collection shape"** — producer (Python) and consumer (TS) evolve independently against the JSON Schemas; `scripts/verify_contract.py` is the regression harness guarding both sides.
- **Inline jsonschema validation** (Draft202012Validator) over subprocess-to-validate.py — because validate.py's SMOKE_SHAPES excludes the asset shape. Two-tier authority: schemas are machine-checkable truth, SPEC.md is human overview.
- **Per-phase standalone verify scripts** (no pytest/jest) — shot-timeline's `scripts/*.py` + consumer's `npx tsx scripts/verify-*.ts`, both sys.exit(0/1). Matches both repos' no-test-framework convention.
- **Worktree-per-effort** for cross-repo consumer work (isolates the dirty main checkout's concurrent work).

### Key Lessons

- **Live-verify during research pays for itself.** The researcher agents that booted backends / ran ffprobe / inspected SQLite found the load-bearing findings (persistence dual-track, FD-leak root cause) that pure code-reading missed. Worth the extra agent minutes.
- **Formally-accept-and-document > silently-fix-or-drop.** Phase 3's WR-01/WR-04 (save-v2 latent bugs) and SC-1 prompt-children scope reduction were carried explicitly through deferred-items.md → Phase 4 VERIFICATION acceptance → milestone audit. No silent scope shrinkage; every reduction is cross-referenced.
- **Cross-repo milestones need explicit execution-model decisions.** "Drive from producer repo's GSD" vs "hand off to consumer's own GSD" was a genuine fork that deserved a user decision (not a default) — it touches a separate production codebase.

### Cost Observations

- **Model mix:** planner=opus (4 phases), executors/researchers/checkers/verifiers=sonnet, explorers=Explore. Opus for planning paid off in the 2-plan splits + research-correction encoding.
- **Subagents spawned:** ~20 across the milestone (4× {researcher, pattern-mapper, planner, checker, executor×waves, code-reviewer, code-fixer, verifier} + integration-checker + 2 explorers).
- **Cross-repo added ~30% overhead** vs a single-repo milestone (worktree setup, two-repo commits, cross-repo executor prompts, dual spot-checks).

---

## Cross-Milestone Trends

*(First milestone — trends populate as v1.1+ ship.)*
