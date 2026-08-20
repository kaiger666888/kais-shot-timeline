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

## Milestone: v1.1 — 分镜语义深化 (镜头语言 + 跨镜角色/道具注册表)

**Shipped:** 2026-07-25
**Phases:** 5 | **Plans:** 16 | **Tasks:** 32 | **Requirements:** 34/34 satisfied

### What Was Built
- v1.1 ShotTimelineAsset contract (3 new registry schemas + 2 additive schema extensions; schema_version `1`→`1.1` producer-locked; v1↔v1.1 bidirectional cross-version self-test).
- Cinematography auto-fill `step_semantic` (httpx client + LOCKED route→prompts mapping + per-shot cache + graceful-degrade + generator.warnings).
- Cross-shot re-id registry + first-class HITL review HTML (`call_reid.py` + `apply_edits.py` confirmed-only gate + `gen_registry_review.py` + registry-edits schema; `step_reid` slot 6 of 8).
- Prompt reference system (`attach_refs.py` deterministic recompose + `registry_snapshot` freeze + gallery/chips/indicator + XSS hardening).
- Canvas consumer v1.1 (character/prop `asset` nodes via §7 post-process + typeIcons; no custom renderer / no Zod bump; 29/29 verify).

### What Worked
- **Contract-first sequencing held** (Phase 5 schemas → Phase 6-9 producer): zero "shape churn" — every producer wrote against a frozen contract. The v1.0 pattern reproduced cleanly.
- **Code review caught real blockers every phase** (Phase 6: 2, Phase 7: 5, Phase 8: 1, Phase 9: 1 — total 9 blockers + 22 warnings, ALL fixed + empirically verified). The empirically-reproduce-before-reporting discipline was load-bearing (especially the Phase 9 CR-01 filePath-missing bug hidden by a verify harness that skipped Zod on the v1.1 run).
- **Graceful-degrade as first-class** let every cross-repo route dependency (shot-analysis, character-reid, e2e) be DEFERRED without blocking the producer/contract side — the milestone shipped complete-in-this-repo with documented pre-authorized deferrals.
- **Phase 7 CR-04 XSS lesson carried forward** to Phase 8 (title/video_src) — the lesson propagated, though it still found new sinks each phase (worth a project-wide XSS pass next).
- **Cross-repo execution via explicit-file `git add` discipline** preserved the user's uncommitted WIP in the consumer worktree across all 8+ consumer commits.

### What Was Inefficient
- **`wave_0_complete: false` frontmatter flags stale on 07/08/09** — the VALIDATION.md frontmatter wasn't flipped after execution (the Wave 0 work IS done). Minor doc staleness; the actual verification (validate.py + smoke) is authoritative.
- **`__file__`-in-`python3 -c` blocker recurred in Phase 7 planning** — the Phase 6 close-fix had fixed it in code, but the Phase 7 PLAN re-introduced it in verify blocks. The plan-checker caught it, but a project-wide lint/checklist would prevent recurrence.
- **Assert E baseline (`origin/master..HEAD`) was structurally broken** on the consumer branch (origin/master advanced past the branch tip) — discovered in Phase 9 review, fixed to `merge-base`. A pre-flight check of the baseline before relying on it would help.

### Patterns Established
- **Graceful-degrade deferral pattern**: cross-repo route unavailable → schema-valid empty/absent field + generator.warnings + asset still exports. Enables shipping the producer/contract side ahead of the cross-repo route.
- **Confirmed-only gating at N defense-in-depth layers** (build + attach + snapshot + verify + consumer filter) — Pitfall 7 enforced redundantly.
- **`registry_snapshot` freeze (Pitfall 18)**: export-time truth embedded in asset.json so later registry mutations can't invalidate exported refs.
- **§7 buildPhaseTree post-process workaround**: emit asset nodes via RawArtifact push + post-process `tree.artifactNodes[*].data.assetType` (because the extra-merge guard drops it). Documented for future canvas node-type additions.

### Key Lessons
- **A green verify harness can still hide blockers** if it skips a check on the new code path (Phase 9 CR-01: v1.1 run skipped `validateGraphNodes`). New-code-path verification must mirror the v1.0 path's rigor.
- **The deferred cross-repo routes are the critical path for v1.1's full value** — the producer/contract side is done, but the user only gets real cinematography/re-id when `feat/shot-analysis-route` merges + `character-reid` is built. Track these as post-merge smoke items.

### Cost Observations
- **Model mix:** planner=opus, executors/researchers/checkers/verifiers/code-reviewers/code-fixers/integration-checker=sonnet, consumer-map=Explore. Opus planning produced clean wave splits + caught the §7 caveat.
- **Subagents spawned:** ~35 across the milestone (5× {researcher, planner, checker, executor×waves, code-reviewer, code-fixer, verifier} + integration-checker + 1 Explore + 2 inline revisions).
- **Code review ROI high**: 9 blockers caught before ship — without it, the Phase 9 save-v2 HTTP 400 + the Phase 7/8 XSS + the Phase 7 silent-data-loss bugs would have shipped.

---

## Cross-Milestone Trends

*(2 milestones shipped. Trends below compare v1.0 → v1.1.)*

| Trend | v1.0 | v1.1 |
|-------|------|------|
| Phases / Plans | 4 / 7 | 5 / 16 |
| Code-review blockers caught | (not run uniformly) | 9 (all fixed) |
| Cross-repo overhead | ~30% | ~30% (consistent) |
| Deferred-at-ship items | 2 (WR-01/04) | 3 (cross-repo routes + e2e) |
| Graceful-degrade deferrals | 1 (canvas) | 3 (shot-analysis, character-reid, e2e) — pattern now standard |

## Milestone: v1.3 — Round-trip Validation（逆推→复现→比对闭环数据集）

**Shipped:** 2026-08-20
**Phases:** 5 | **Plans:** 16 | **Tasks:** 39

### What Was Built
- 契约层：roundtrip.schema.json（v1.x 首个 object 挂载 + warnings 双形）+ SCHEMA_VERSION 1.3 单源 + 四阶 fixture gate + v1.2↔v1.3 双向证明
- qwen-eye v2：≤8 帧序列逐帧实证升级 action/camera facet + ear 融合（盲评锁定 temporal 合并）
- h3 复现客户端：ComfyUI 直连 fl2va + 4-tuple cache 断点续跑 + VRAM guard 五步 + PID 归因反自锁
- Scorer：SigLIP so400m 中段帧轨迹 + VLM judge 三分类；τ_sim=0.9670 Kai 看分布裁决；verdict 冻结（rejected 永不删除）
- 集成层：step_roundtrip [9/10] + HITL 审阅面板（双 video 同步）+ confirmed-only apply + dataset 独立导出 + 四场景 e2e

### What Worked
- 契约先行 + 抽样先行 + 串行编排三大 ordering 约束全程未破
- 每 phase 的 code-review→fix→re-review 链抓到 5 个 Critical（含 2 个 DOM/缓存真 bug）——复审二次发现的「修复引入回归」类（WR-06×2）证明 re-review 不是走过场
- 冻结红线（rejected 永不删除）在 --force/重跑/apply/prune 四处语义一致，sha256 三点证明落地
- GPU 任务 nohup + cache 断点续跑设计让 429 中断零损失恢复

### What Was Inefficient
- 3 次 API 429 使用限额中断（10.5h 15:34 20:35）——overnight/harness 类长任务依赖 orchestrator inline 续跑收尾
- 22-04 首次正本尝试的 attach_refs 改写 live prompts.json 造成 B2 溯源断裂（COPY 载体教训：**任何 live 数据上的管线首跑都该先副本**）
- plan-checker 的 test-count 基线类 warning 三次重复出现（19/20/21 各一次）——planner 模板可固化「相对断言」规则

### Patterns Established
- 「verdict 冻结 + human 覆盖唯一路径」的 HITL 数据语义（source: auto/human）
- 正本零触碰测试法：副本载体 + 正本 sha 三点断言
- PROMPT_VERSION/cache key 强化 = 设计性 stale 重打分（verdict 不动）

### Key Lessons
- SigLIP 余弦高窄带（随机噪声 0.99）使阈值直觉全部失效——分布实测 + 人类裁决不可省
- 字符串断言测试测不出 DOM 级 bug（CR-01 queue 摧溃）——面板类交付需要浏览器走查硬门
- 中断恢复：executor 半途死 → git log + 产物 sha 对账 → inline 机械收尾，比重跑省 80%

### Cost Observations
- Timeline: 08-19 20:54 → 08-20 21:14（~24h 墙钟，含 2 次 overnight GPU 批 + 3 次 429 等待）
- ~65 milestone commits；234 tests（36 → 234，+198）
- Notable: GPU 实测远优于预估（overnight 批 2h53m vs 预估 3-4.5h；smoke 147 calls 15.5min vs 预估 1-3h）
