# Phase 4: Cross-Repo Contract Verification - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — grey areas accepted as recommended

<domain>
## Phase Boundary

证明一个**真实** ShotTimelineAsset 能端到端从 producer（kais-shot-timeline）流到 consumer（@kais/infinite-canvas），并落地一个**回归 harness** 让两侧仓库独立演进时能抓到契约漂移。这是 v1.0 milestone 的 capstone —— 把 Phase 1（spec）+ Phase 2（exporter）+ Phase 3（consumer）扣合成一个可验证、可回归的整体，兑现「松耦合、两仓库独立演进」的核心价值。

本 phase **只加验证/回归层**：不改 producer 的导出逻辑、不改 consumer 的 importer 逻辑、不改 spec schemas。交付物：(1) 一个 HTTP-level 端到端测试（真 producer 输出 → consumer backend `/api/canvas/v2/import-from-dir` → 持久化 graph 断言）；(2) 一个 canonical 回归 harness（producer 侧 re-export + schema 校验 + 调 consumer importer 确认接受）。

**Goal:** A real ShotTimelineAsset flows end-to-end from producer to consumer, and a regression harness exists to keep the contract aligned as both repos evolve independently.
**Requirements:** VERIFY-01, VERIFY-02
**Repo:** 跨仓库 —— harness 落 shot-timeline（spec owner / contract authority）；e2e 测试操作 kais-aigc-platform worktree backend
**Depends on:** Phase 2（exporter）, Phase 3（consumer importer + golden fixture）

</domain>

<decisions>
## Implementation Decisions

### E2E 测试范围 + WR-01/04 处置 (VERIFY-01)
- **HTTP-level e2e**（不上 Playwright/浏览器）：在 consumer worktree `/data/workspace/kst-canvas-consumer` 跑 full `yarn install`（含 native bindings 编译）→ 起 Express backend → POST `/api/canvas/v2/import-from-dir` 喂一个**真实 producer 导出的 asset**（重跑 shot-timeline pipeline 产 ep01 asset，或直接用 Phase 2 已有的 ep01 导出）→ 断言持久化的 graph（via API 或 DB）：zone + N storyboard + 3 audio + 1 video + sequence edges 结构正确
- **走 primary appendAndSync 路径**（canvas 实际的 event-sourcing 持久化）—— sequence edges + sum-node 在这条路径上存活
- **WR-01/WR-04 正式接受为 documented limitations**：e2e 不走 save-v2（secondary full-save），故两者不浮现。VERIFICATION 报告显式记录：collection 经 primary 路径正确渲染；save-v2 路径存在 latent stripping（consumer-repo backlog，非 v1.0 契约阻塞）。Phase 3 的 deferred-items.md 已有记录，Phase 4 在 VERIFICATION 里 cross-reference 并正式接受
- 理由：full-stack Playwright 对 autonomous 运行太重/太 flaky；save-v2 是次要路径，修它要动共享 production schema（超出 milestone additive 范围）

### Regression Harness 落地 (VERIFY-02)
- **shot-timeline（spec owner）host canonical harness**：一个脚本（如 `scripts/verify_contract.py` 或 `.ts`）做**双侧检查**：
  - **producer 侧**：re-export 一个 golden asset（调 `scripts/export_asset.py` 对一个固定测试视频，或直接用既有 ep01 导出）→ 用 `spec/schemas/*.json`（Phase 1）+ `spec/validate.py` 校验 → producer 漂移（输出不再 schema-valid）即 fail
  - **consumer 侧**：调 consumer 的 `extractShotTimelineArtifacts`（从 worktree `/data/workspace/kst-canvas-consumer` import）喂同一个 asset → 断言产出 1 zone + children 结构 + 所有 media 子节点过 per-type Zod → consumer 漂移（importer 拒绝 valid asset）即 fail
- 单一 canonical home（spec owner = contract authority）；cross-repo reference 走 worktree path（不引入 submodule）
- 理由：spec owner 是契约权威方；双侧检查覆盖两个漂移方向；避免 submodule infra 负担

### Golden Asset 策略
- **Pinned golden（consumer 侧回归的稳定靶子）+ producer 侧 re-export-and-validate（抓 producer 漂移）**，两个互补检查
- Pinned golden = Phase 3 在 consumer worktree 的 `scripts/fixtures/shot-timeline-ep01/`（736KB downsampled）—— consumer importer 必须持续接受它
- Producer 侧 re-export：Phase 4 harness 重新导出一个 asset（同一 ep01 源）→ 校验 schema-valid。**不**把 re-export 结果覆盖 pinned golden（避免 flaky 靶子）；契约**故意**变更时手动 bump golden
- 理由：pinned-only 漏 producer 漂移；regenerate-every-run 把 producer 故意变更与 consumer 回归混淆（noisy）

### Claude's Discretion
- e2e 测试脚本的语言/形式（Python `requests` + assertions，仿 shot-timeline 既有 standalone-script 风格；或 tsx 仿 consumer 风格）—— 倾向 Python（shot-timeline 是 Python 工程，e2e 编排自然在 producer 侧）
- harness 是否复用 Phase 2 的 `spec/validate.py` + Phase 3 的 `verify-canvas-shot-timeline.ts`（倾向复用，不重写）
- e2e 用的「真实 producer asset」：重跑 pipeline 产 fresh，还是直接用既有 ep01 导出（倾向既有 ep01，避免 GPU/Whisper 重跑；但 ep03 的 cache 被 Phase 2 测试破坏过，用 ep01）
- backend 启动/ teardown 的 fixture 形式（subprocess + port + health poll + try/finally）

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Producer 侧（this repo）**：
  - `scripts/export_asset.py`（Phase 2）—— 产 asset.json + canonical symlinks；harness 的 re-export 步骤调它
  - `spec/validate.py` + `spec/schemas/*.schema.json`（Phase 1）—— harness 的 schema 校验步骤调它
  - `run_pipeline.py` —— 完整 pipeline；e2e 若需 fresh asset 可 `--skip-detect --skip-separate --skip-transcribe` 复用 cache 秒出 asset
  - `output/虫虫武侠小故事《小江湖》第01话：…/asset.json`（Phase 2 实测产物）—— 真实 e2e asset 来源
- **Consumer 侧（worktree `/data/workspace/kst-canvas-consumer`）**：
  - `src/routes/canvas/v2/import-from-dir.ts`（Phase 3）—— POST `/api/canvas/v2/import-from-dir` 入口；exported `extractShotTimelineArtifacts` + `setWorkdirToOss`（harness 直接 import 做 consumer 侧检查）
  - `scripts/verify-canvas-shot-timeline.ts`（Phase 3，19 asserts）—— harness 的 consumer 侧检查可复用/调它
  - `scripts/fixtures/shot-timeline-ep01/`（Phase 3 pinned golden）—— consumer 侧回归靶子
  - `package.json` scripts `verify:*`（6 个既有 verify 脚本）—— harness 命名/形式参考
- **跨仓库**：worktree path `/data/workspace/kst-canvas-consumer` 是 harness 访问 consumer 侧的稳定句柄（feat/canvas-asset-collection 分支）

### Established Patterns
- **shot-timeline standalone-script 风格**：argparse + main() + `sys.exit(0/1)` + bracketed print（见 `scripts/serve.py`, `scripts/check_range.py`）—— e2e/harness 脚本沿用
- **consumer verify 脚本风格**：`npx tsx scripts/verify-*.ts` + assert + process.exit —— consumer 侧检查沿用
- **Cross-repo 操作**：Phase 3 已建立 worktree-isolation 模式（在 `/data/workspace/kst-canvas-consumer` 操作，commits 落 feat/canvas-asset-collection；planning artifacts 落 this repo feat/video-reverse-dataset）
- **Subprocess + try/finally**：`scripts/check_range.py`（Phase 2）的「起 server → poll ready → assert → teardown」是 e2e backend 启停的直接模板

### Integration Points
- e2e：`POST /api/canvas/v2/import-from-dir` body `{projectId, episodesId, workdir, mode}` —— 需一个 pre-existing project+episodes（或 backend 自动建）。workdir 指向真实 ep01 asset 目录
- harness：Python 脚本 `subprocess.run([sys.executable, "scripts/export_asset.py", ...])` re-export → `subprocess.run([sys.executable, "spec/validate.py", ...])` 校验 → `subprocess.run(["npx","tsx","-e", "...import from /data/workspace/kst-canvas-consumer/..."])` 调 consumer importer
- VERIFICATION 报告 cross-reference Phase 3 `deferred-items.md`（WR-01/04 正式接受）

</code_context>

<specifics>
## Specific Ideas

- e2e 必须用**真实** producer 输出（不是 fixture），证明端到端 —— 区别于 Phase 3 的 fixture-based 纯函数 verify
- harness 的 producer 侧检查 = Phase 2 inline validation 的独立化、可回归化（脱离 pipeline 单独跑）
- WR-01/WR-04 不在 Phase 4 修（save-v2 是次要路径；修要动共享 production schema，超范围）—— 但必须在 VERIFICATION 里**正式**accept + cross-reference Phase 3 deferred-items，不能默默漏掉
- milestone 的核心价值「两仓库独立演进」由 VERIFY-02 的 regression harness 兑现 —— 这是 Phase 4 最重要的交付物

</specifics>

<deferred>
## Deferred Ideas

- Full-stack Playwright e2e（backend + frontend + browser pixel assert）—— v1.0 用 HTTP-level 够；Playwright 留待 consumer repo 自己的 e2e 体系
- save-v2 路径的 WR-01（sequence edge data stripping）+ WR-04（sum-node reject）修复 —— consumer-repo backlog，需改 FlowLinkV2Schema/save-v2 过滤逻辑，超出 v1.0 additive 范围
- CI 集成（把 harness 接到两仓库的 CI pipeline 自动跑）—— v1.0 落本地可跑的 harness；CI 接入留待后续
- cross-repo contract test 用 git submodule / 独立 repo —— v1.0 用 worktree path 句柄；submodule 留待评估
- None others —— 讨论保持在 phase 范围内

</deferred>
