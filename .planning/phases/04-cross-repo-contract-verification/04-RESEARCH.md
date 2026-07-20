# Phase 4: Cross-Repo Contract Verification - Research

**Researched:** 2026-07-21
**Domain:** Cross-repo e2e + regression harness (producer kais-shot-timeline ↔ consumer kais-aigc-platform worktree)
**Confidence:** HIGH (both repos + DB inspected in person this session; Phase 3 leftover snapshot confirms end-to-end persistence path)

## Summary

Phase 4 是 v1.0 milestone 的 capstone:把 Phase 1 (spec) + Phase 2 (exporter) + Phase 3 (consumer importer) 扣合成一个**可验证、可回归**的整体,兑现「两仓库独立演进」的核心价值。本 phase 只加验证层 —— 不改 producer 导出逻辑、不改 consumer importer 逻辑、不改 spec schemas。

交付物有二 (CONTEXT 已锁定):

1. **HTTP-level e2e** (`VERIFY-01`):在 consumer worktree `/data/workspace/kst-canvas-consumer` 起 Express backend (entry `src/app.ts`, 默认 port 10588), 用**真实 producer ep01 输出** POST `/api/canvas/v2/import-from-dir` 走 primary `appendAndSync` 路径, 然后断言持久化的 FlowGraphV2 snapshot 在 `o_agentWorkData` 表里有正确结构 (1 zone + 1 summary + 93 storyboard + 3 audio + 1 video + 92 sequence edges)。**WR-01/WR-04 正式 accept** (save-v2 是 secondary path,不在 e2e 范围)。
2. **Canonical regression harness** (`VERIFY-02`):单一 Python 脚本 (e.g., `scripts/verify_contract.py`) 做**双侧**检查 —— producer 侧 re-export + jsonschema 校验抓 producer 漂移; consumer 侧 shell out 到 `npx tsx scripts/verify-canvas-shot-timeline.ts` (Phase 3 已落地, 17 asserts) 抓 consumer 漂移。host 在 shot-timeline (spec owner = contract authority)。

研究最关键的发现是 **consumer 持久化的双轨性**: import-from-dir 写 event + snapshot (`o_agentWorkData` JSON blob), 而 `POST /api/canvas/v2/load-v2` 读的是 **relational tables** (`canvas_nodes`/`canvas_links`) —— 两条路径**不交叉**。直接 POST load-v2 在 import-from-dir 之后会拿到 `null`。e2e 的 read-back 必须直接 SQL 查 `data/db2.sqlite` 的 `o_agentWorkData` 表 (Phase 3 测试 leftover 已验证此路径: 99 nodes / 190 links / 92 sequence edges 完整存活)。

第二个关键发现是 **worktree 当前 dirty**: `src/types/database.d.ts` 有未提交修改 (yarn install postinstall 在 dev 模式自动 regen, `@db-hash` 与一行 `score?: any → number` 类型差异)。Phase 4 executor 必须在 e2e 前 reconcile (commit 或 revert)。

**Primary recommendation:** 单一 Python harness `scripts/verify_contract.py` 在 shot-timeline repo, 三个 mode (`--producer` / `--consumer` / `--e2e`), 各自独立 exit code。e2e mode 起 backend subprocess + poll `/health` + POST import-from-dir + sqlite3 直查 `o_agentWorkData` + try/finally teardown。Cross-repo path 用 env var `CANVAS_CONSUMER_PATH` (default `/data/workspace/kst-canvas-consumer`) 参数化,避免硬编码脆弱。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### E2E 测试范围 + WR-01/04 处置 (VERIFY-01)
- **HTTP-level e2e** (不上 Playwright/浏览器): 在 consumer worktree `/data/workspace/kst-canvas-consumer` 跑 full `yarn install` (含 native bindings 编译) → 起 Express backend → POST `/api/canvas/v2/import-from-dir` 喂一个**真实 producer 导出的 asset** (重跑 shot-timeline pipeline 产 ep01 asset, 或直接用 Phase 2 已有的 ep01 导出) → 断言持久化的 graph (via API 或 DB): zone + N storyboard + 3 audio + 1 video + sequence edges 结构正确
- **走 primary appendAndSync 路径** (canvas 实际的 event-sourcing 持久化) —— sequence edges + sum-node 在这条路径上存活
- **WR-01/WR-04 正式接受为 documented limitations**: e2e 不走 save-v2 (secondary full-save), 故两者不浮现。VERIFICATION 报告显式记录: collection 经 primary 路径正确渲染; save-v2 路径存在 latent stripping (consumer-repo backlog, 非 v1.0 契约阻塞)。Phase 3 的 deferred-items.md 已有记录, Phase 4 在 VERIFICATION 里 cross-reference 并正式接受
- 理由: full-stack Playwright 对 autonomous 运行太重/太 flaky; save-v2 是次要路径, 修它要动共享 production schema (超出 milestone additive 范围)

#### Regression Harness 落地 (VERIFY-02)
- **shot-timeline (spec owner) host canonical harness**: 一个脚本 (如 `scripts/verify_contract.py` 或 `.ts`) 做**双侧检查**:
  - **producer 侧**: re-export 一个 golden asset (调 `scripts/export_asset.py` 对一个固定测试视频, 或直接用既有 ep01 导出) → 用 `spec/schemas/*.json` (Phase 1) + `spec/validate.py` 校验 → producer 漂移 (输出不再 schema-valid) 即 fail
  - **consumer 侧**: 调 consumer 的 `extractShotTimelineArtifacts` (从 worktree `/data/workspace/kst-canvas-consumer` import) 喂同一个 asset → 断言产出 1 zone + children 结构 + 所有 media 子节点过 per-type Zod → consumer 漂移 (importer 拒绝 valid asset) 即 fail
- 单一 canonical home (spec owner = contract authority); cross-repo reference 走 worktree path (不引入 submodule)
- 理由: spec owner 是契约权威方; 双侧检查覆盖两个漂移方向; 避免 submodule infra 负担

#### Golden Asset 策略
- **Pinned golden (consumer 侧回归的稳定靶子) + producer 侧 re-export-and-validate (抓 producer 漂移)**, 两个互补检查
- Pinned golden = Phase 3 在 consumer worktree 的 `scripts/fixtures/shot-timeline-ep01/` (736KB downsampled) —— consumer importer 必须持续接受它
- Producer 侧 re-export: Phase 4 harness 重新导出一个 asset (同一 ep01 源) → 校验 schema-valid。**不**把 re-export 结果覆盖 pinned golden (避免 flaky 靶子); 契约**故意**变更时手动 bump golden
- 理由: pinned-only 漏 producer 漂移; regenerate-every-run 把 producer 故意变更与 consumer 回归混淆 (noisy)

### Claude's Discretion
- e2e 测试脚本的语言/形式 (Python `requests` + assertions, 仿 shot-timeline 既有 standalone-script 风格; 或 tsx 仿 consumer 风格) —— 倾向 Python (shot-timeline 是 Python 工程, e2e 编排自然在 producer 侧)
- harness 是否复用 Phase 2 的 `spec/validate.py` + Phase 3 的 `verify-canvas-shot-timeline.ts` (倾向复用, 不重写)
- e2e 用的「真实 producer asset」: 重跑 pipeline 产 fresh, 还是直接用既有 ep01 导出 (倾向既有 ep01, 避免 GPU/Whisper 重跑; 但 ep03 的 cache 被 Phase 2 测试破坏过, 用 ep01)
- backend 启动/teardown 的 fixture 形式 (subprocess + port + health poll + try/finally)

### Deferred Ideas (OUT OF SCOPE)
- Full-stack Playwright e2e (backend + frontend + browser pixel assert) —— v1.0 用 HTTP-level 够; Playwright 留待 consumer repo 自己的 e2e 体系
- save-v2 路径的 WR-01 (sequence edge data stripping) + WR-04 (sum-node reject) 修复 —— consumer-repo backlog, 需改 FlowLinkV2Schema/save-v2 过滤逻辑, 超出 v1.0 additive 范围
- CI 集成 (把 harness 接到两仓库的 CI pipeline 自动跑) —— v1.0 落本地可跑的 harness; CI 接入留待后续
- cross-repo contract test 用 git submodule / 独立 repo —— v1.0 用 worktree path 句柄; submodule 留待评估
- None others —— 讨论保持在 phase 范围内
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VERIFY-01 | 导出端产物能被消费端成功 import, 并正确渲染出分镜/stem/字幕/prompt 集合 | HTTP-level e2e (本仓库 Python 脚本) → consumer worktree backend → POST import-from-dir → 持久化 snapshot 在 `o_agentWorkData` 表断言 (1 zone + 1 summary + N storyboard + 3 audio + 1 video + N-1 sequence edges)。Read-back 走 SQL 直查, 非走 `/api/canvas/v2/load-v2` (后者读 relational table, 不交叉; 见 `## Common Pitfalls` Pitfall 1)。WR-01/04 在 primary 路径不浮现, 在 VERIFICATION 显式 accept + cross-reference Phase 3 deferred-items。SC-1 提到的 "prompt children" 在 Phase 3 已显式 defer (CONTEXT 03 discretion: prompts/transcript 保留为 sidecar data refs, 不单独建节点) —— Phase 4 VERIFICATION 报告须显式记录此 scope 缩减 |
| VERIFY-02 | 契约一致性验证 —— 字段 schema 与媒体引用在导出端 ↔ 消费端两端对齐, 有回归保护 | `scripts/verify_contract.py` 双侧: (a) producer 侧 re-export + `jsonschema.Draft202012Validator` 校验 asset.json + 5 data shapes; (b) consumer 侧 shell out 到 `npx tsx scripts/verify-canvas-shot-timeline.ts` (Phase 3 已落地, 17 asserts 覆盖 A-F)。两侧任一失败即 exit ≠0, 兜住两个漂移方向 |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Producer-side re-export (asset.json 生成) | Producer CLI (`scripts/export_asset.py`) | — | Phase 2 已落地;harness 通过 subprocess 调用,不重写 |
| Schema validation (jsonschema Draft2020-12) | Producer harness (Python stdlib + `jsonschema`) | — | `spec/schemas/*.json` 是机器可校验权威源;复用 Phase 1 的 6 schemas + Phase 2 的 inline 自校验模式 |
| Consumer backend (Express + better-sqlite3) | Consumer worktree (`src/app.ts`) | — | Phase 3 已落地,零改动;e2e 通过 subprocess 起停 |
| import-from-dir 端到端导入 | Consumer route (`POST /api/canvas/v2/import-from-dir`) | — | Phase 3 已加 ShotTimelineAsset 分支;走 primary `appendAndSync` 路径 |
| 持久化 (event-sourcing + snapshot) | Consumer DB (`kv_canvasEvent` + `o_agentWorkData` 双表) | — | 关键:e2e 必须读 `o_agentWorkData` JSON blob snapshot,不是 relational `canvas_nodes` 表 |
| Regression harness orchestration | Producer repo (`scripts/verify_contract.py`) | — | spec owner = contract authority;单一 canonical home |
| Cross-repo consumer-side check | Consumer script (`scripts/verify-canvas-shot-timeline.ts`) | — | Phase 3 已落地 17 asserts;harness shell out 调用 |
| Health poll + teardown | Producer harness (Python subprocess + try/finally) | — | 仿 `scripts/check_range.py` (Phase 2) 的 server lifecycle 模式 |
| WR-01/WR-04 scope documentation | VERIFICATION 报告 + cross-ref Phase 3 deferred-items | — | 不修代码,只显式 accept + 记录 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` (Python) | 4.26.0 (system-installed, 无 pip) | Producer-side asset.json schema 校验 (Draft202012Validator) | `[VERIFIED: spec/validate.py:24 import + system probe]` Phase 1/2 已用,零新增依赖 |
| `sqlite3` (Python stdlib) | — (3.12 stdlib) | 直查 consumer worktree `data/db2.sqlite` 的 `o_agentWorkData` snapshot 表 | `[VERIFIED: python3 -c "import sqlite3"]` stdlib,无 install;唯一能读 snapshot 的低摩擦路径 (见 Pitfall 1) |
| `requests` (Python) | (待测, 可选) | e2e POST `/api/canvas/v2/import-from-dir` + poll `/health` | `[ASSUMED]` —— Python 3.12 stdlib `urllib.request` 也够用;若 `requests` 未装,用 urllib fallback (zero 新依赖) |
| `subprocess` (Python stdlib) | — | 起 Express backend (`npx tsx src/app.ts`) + 调 `export_asset.py` + 调 `npx tsx` | stdlib,无依赖 |
| Express (consumer) | ^5.2.1 (已装) | Backend HTTP server | `[VERIFIED: package.json L62]` Phase 3 已用,零新增 |
| `better-sqlite3` (consumer) | ^12.9.0 (已装) | Native binding, SQLite 持久化 | `[VERIFIED: node_modules/better-sqlite3/build/Release/better_sqlite3.node exists]` worktree yarn install 已编译 |
| `tsx` (consumer devDep) | ^4.21.0 (已装) | 跑 .ts 直接执行 (`npx tsx scripts/verify-*.ts` + `npx tsx src/app.ts`) | `[VERIFIED: node_modules/.bin/tsx exists]` Phase 3 已用模式 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `urllib.request` (Python stdlib) | — | HTTP POST + GET (fallback if `requests` 未装) | e2e HTTP 调用;stdlib 保证零新依赖 |
| `threading` / `subprocess.Popen` (Python stdlib) | — | backend 起停 + 异步等待 | backend lifecycle 管理 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python harness | tsx harness (in consumer repo) | CONTEXT 明确「harness 落 shot-timeline」+ 「倾向 Python」(producer repo 是 Python 工程);consumer repo 已有 7 个 verify-*.ts,但 harness 不属于 consumer |
| SQL 直查 snapshot (read-back) | 走 HTTP `/api/canvas/v2/load-v2` | load-v2 读 relational table,不交叉 import-from-dir 写的 snapshot;会拿到 null。SQL 直查是唯一非侵入路径 (见 Pitfall 1) |
| SQL 直查 snapshot | 加一个 consumer-side read shim (新 route 或 tsx -e) | 违反 additive-only (CONTEXT 锁「不改 consumer importer 逻辑」);SQL 直查无 consumer 改动 |
| `requests` (Python) | `urllib.request` (stdlib) | stdlib 保证 zero 新依赖;e2e 只需 POST + GET,无高级特性需求 |
| 单一脚本三 mode | 多脚本 (`verify_producer.py` + `verify_consumer.py` + `verify_e2e.py`) | 单一 canonical home (CONTEXT 决策),三 mode 共享 fixture path 与 cross-repo 句柄;少 orchestration 重复 |

### Package Legitimacy Audit

> 本 phase **不安装任何新包** —— 全部依赖已在两个 repo 中预装。仅做版本与可用性确认 (仿 Phase 3 RESEARCH 模式)。

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| jsonschema | PyPI (system) | 多年 | 极高 | github.com/python-jsonschema/jsonschema | (skip) | 既有,无新增 |
| sqlite3 | Python stdlib | — | — | (stdlib) | (skip) | stdlib |
| requests | PyPI | 多年 | 极高 | github.com/psf/requests | (skip) | 可选,有 urllib fallback |
| express | npm | 多年 | 极高 | github.com/expressjs/express | (skip) | 既有 |
| better-sqlite3 | npm | 多年 | 高 | github.com/WiseLibs/better-sqlite3 | (skip) | 既有,native binding 已编译 |
| tsx | npm | 多年 | 高 | github.com/privatenumber/tsx | (skip) | 既有 devDep |

**Packages removed due to slopcheck [SLOP] verdict:** none (本 phase 零新包安装)
**Packages flagged as suspicious [SUS]:** none

slopcheck 未执行 (本 phase 零新包安装,全部依赖已在两个 repo 的 manifest 中 `[VERIFIED]`)。

**Installation:**
```bash
# 本仓库 (producer) —— 无新增依赖,所有用到的都是 stdlib 或既有
python3 -c "import jsonschema, sqlite3, subprocess, urllib.request"  # 全部应无 ImportError

# Consumer worktree —— Phase 3 已 yarn install 完毕,node_modules 存在,native binding 已编译
ls /data/workspace/kst-canvas-consumer/node_modules/.bin/tsx              # 应存在
ls /data/workspace/kst-canvas-consumer/node_modules/better-sqlite3/build/Release/better_sqlite3.node  # 应存在
```

**Version verification (executed this session):**
- `python3 --version` = Python 3.12.3 (`[VERIFIED: env]`)
- `python3 -c "import jsonschema; print(jsonschema.__version__)"` = 4.26.0 (`[VERIFIED: system probe]`)
- worktree `node_modules/.bin/tsx` exists (`[VERIFIED: ls]`)
- worktree `node_modules/better-sqlite3/build/Release/better_sqlite3.node` exists (`[VERIFIED: ls]`)

## Architecture Patterns

### System Architecture Diagram

```text
 ┌─ PRODUCER (本仓库 kais-shot-timeline, feat/video-reverse-dataset) ──────────┐
 │                                                                              │
 │  scripts/verify_contract.py  ◀── canonical harness host (spec owner)         │
 │   ├─ mode=producer:                                                          │
 │   │   └─ subprocess.run([python3, scripts/export_asset.py,                  │
 │   │                       --work-dir, --video, --stems-source-dir,          │
 │   │                       --output, --force])                               │
 │   │      → writes <tmp>/asset.json (schema-valid by inline check)           │
 │   │   └─ jsonschema.Draft202012Validator(asset.schema.json)                │
 │   │      .validate(asset.json)  → 0 errors = PASS                          │
 │   │                                                                         │
 │   ├─ mode=consumer:                                                         │
 │   │   └─ subprocess.run([npx, tsx, scripts/verify-canvas-shot-timeline.ts],│
 │   │                       cwd=CANVAS_CONSUMER_PATH)                        │
 │   │      → Phase 3 17 asserts (A-F + E2) on pinned golden fixture          │
 │   │      → exit 0 = PASS                                                   │
 │   │                                                                         │
 │   └─ mode=e2e (heavy, env-gated):                                           │
 │       1. subprocess.Popen([npx, tsx, src/app.ts],                           │
 │            cwd=CANVAS_CONSUMER_PATH, env={PORT:<free>,NODE_ENV:dev})        │
 │       2. poll http://localhost:<port>/health until 200                      │
 │       3. POST /api/canvas/v2/import-from-dir                                │
 │            body={projectId:<ts>, episodesId:<ts>,                          │
 │                  workdir:<real ep01 asset dir>, mode:"replace"}            │
 │       4. sqlite3.connect(<worktree>/data/db2.sqlite)                       │
 │            SELECT data FROM o_agentWorkData                                 │
 │            WHERE projectId=<ts> AND episodesId=<ts>                        │
 │              AND key='canvasGraph'                                         │
 │       5. JSON.parse → assert structure (1 zone, N storyboard, etc.)        │
 │       6. teardown: server.terminate() + cleanup SQL DELETE                 │
 │                                                                              │
 └──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │  (cross-repo, via filesystem path)
                                       ▼
 ┌─ CONSUMER worktree (kais-aigc-platform, feat/canvas-asset-collection) ──────┐
 │                                                                              │
 │  src/app.ts  ◀── Express entrypoint                                         │
 │   ├─ startServe() → initDB → bootReady → server.listen(PORT || 10588)       │
 │   ├─ Auth bypass for /api/* (V6.0 — no token needed)                        │
 │   └─ Routes mounted: /api/canvas/v2/{import-from-dir, load-v2, health,...}  │
 │                                                                              │
 │  POST /api/canvas/v2/import-from-dir                                        │
 │   ├─ validateFields (projectId, episodesId, workdir)                        │
 │   ├─ scanAndBuildTree(workdir)                                              │
 │   │   └─ asset.json early-recognize → extractShotTimelineArtifacts()        │
 │   │      (Phase 3 helper, returns {nodes, links})                           │
 │   ├─ ensureBootstrap(projectId, episodesId)                                 │
 │   ├─ appendAndSync({projectId, episodesId, events:[{bootstrap, graph}]})    │
 │   │   ├─ appendEvents → INSERT into kv_canvasEvent                          │
 │   │   └─ recomputeGraph → reduceAll(events) → writeSnapshot                │
 │   │      → UPSERT o_agentWorkData row (key='canvasGraph', data=JSON)        │
 │   ├─ broadcastToProject('graph:saved') (no-op if no WS clients)             │
 │   └─ HTTP 200 {imported, links, artifacts, phases, mode, workdir}           │
 │                                                                              │
 │  data/db2.sqlite (gitignored, auto-created on boot)                         │
 │   ├─ o_agentWorkData: 1 row per (projectId, episodesId, key='canvasGraph')  │
 │   │   └─ data column: full FlowGraphV2 JSON blob (~290KB for ep01)        │
 │   ├─ kv_canvasEvent: 1 row per appendEvents call (event log)                │
 │   └─ canvas_nodes/canvas_links: EMPTY (only save-v2 path writes here)       │
 │                                                                              │
 │  scripts/verify-canvas-shot-timeline.ts (Phase 3, 17 asserts)               │
 │   └─ Pure-function check: extractShotTimelineArtifacts(fixture) → nodes    │
 │      No backend/DB/HTTP required                                            │
 │                                                                              │
 │  scripts/fixtures/shot-timeline-ep01/ (Phase 3 pinned golden, 736KB)        │
 │   └─ downsampled producer ep01 (6 JSON + ffmpeg silent stubs)              │
 └──────────────────────────────────────────────────────────────────────────────┘
```

**阅读路径:** harness 三 mode 各自独立。producer mode 在本仓库内闭合 (Python subprocess + jsonschema)。consumer mode shell out 到 worktree 的既有 verify script。e2e mode 起完整 backend,POST 真实 asset,然后**直接 SQL 查 `o_agentWorkData` snapshot 表**读回持久化结果 —— 关键决策,绕开 load-v2 relational mismatch (见 Pitfall 1)。

### Recommended Project Structure (本仓库新增)

```text
/data/workspace/kais-shot-timeline/              # producer repo (harness home)
├── scripts/
│   └── verify_contract.py                       # NEW: canonical harness (3 modes)
└── .planning/phases/04-cross-repo-contract-verification/
    ├── 04-CONTEXT.md                            # 已存在
    ├── 04-RESEARCH.md                           # 本文档
    ├── 04-01-PLAN.md                            # planner 产
    └── 04-01-VERIFICATION.md                    # execution 产 (含 WR-01/04 正式 accept)
```

**Worktree 侧零新增** —— Phase 3 已落 `scripts/verify-canvas-shot-timeline.ts` + `scripts/fixtures/shot-timeline-ep01/`,Phase 4 直接复用。Phase 4 executor 不在 worktree 加任何文件 (除可能的 `src/types/database.d.ts` dirty reconcile,见 Pitfall 2)。

### Pattern 1: 三 mode 单脚本,env-gated e2e

**What:** 单一 `scripts/verify_contract.py`,通过 CLI flag 或 env var 切换 mode。
**When to use:** Phase 4 三个交付物 (producer 漂移 / consumer 漂移 / e2e) 各有不同 cost 与依赖,不应强制一起跑。
**Why:** 仿 Phase 46 的 `PHASE46_RUN_E2E=1` env-gate 模式 (`[VERIFIED: scripts/verify-phase-46-e2e.ts:62-65]`);e2e 起 backend 重 (~10-30s),不应在每次 commit 都跑。

```python
# Source: 新增于 scripts/verify_contract.py (本仓库)
# 模板源:scripts/check_range.py (Phase 2 的 subprocess+poll+teardown) +
#         scripts/verify-phase-46-e2e.ts (env-gate 模式)

import argparse, os, sys, subprocess, json, sqlite3, time, urllib.request, urllib.error

DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"
DEFAULT_E2E_ASSET_DIR = (
    "/data/workspace/kais-shot-timeline/output/"
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)

def main():
    ap = argparse.ArgumentParser(description="Phase 4 cross-repo contract verification harness")
    ap.add_argument("--mode", choices=["producer", "consumer", "e2e", "all"],
                    default="all")
    ap.add_argument("--consumer-path", default=os.environ.get(
        "CANVAS_CONSUMER_PATH", DEFAULT_CONSUMER_PATH))
    ap.add_argument("--e2e-asset-dir", default=os.environ.get(
        "PHASE4_E2E_ASSET_DIR", DEFAULT_E2E_ASSET_DIR))
    ap.add_argument("--e2e-skip", action="store_true",
                    help="skip e2e mode even if --mode=all (CI-friendly)")
    args = ap.parse_args()

    results = []  # list of (mode_name, ok, detail)

    if args.mode in ("producer", "all"):
        results.append(("producer", run_producer_check(args), ""))
    if args.mode in ("consumer", "all"):
        results.append(("consumer", run_consumer_check(args), ""))
    if args.mode in ("e2e", "all") and not args.e2e_skip:
        # Env-gate like Phase 46 (heavy operation)
        if os.environ.get("PHASE4_RUN_E2E") != "1" and args.mode != "e2e":
            print("[harness] e2e skipped (set PHASE4_RUN_E2E=1 to enable)")
        else:
            results.append(("e2e", run_e2e_check(args), ""))

    # ... summary + exit code (any failure → exit 1)
```

### Pattern 2: Backend lifecycle (subprocess + health poll + try/finally)

**What:** e2e 起 Express backend 前先 poll `/health`,teardown 用 `try/finally` 兜底。
**When to use:** 任何需要起 backend 的测试。
**Why:** `src/app.ts:269` 在 `server.listen` 前 `await bootReady` —— DB 初始化完成才接请求,但仍要 poll 端口 readiness 避免竞争。`src/app.ts:183-185` 暴露 `/health` 返回 200,是天然 readiness probe。

```python
import socket, subprocess, time, urllib.request, urllib.error

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_backend(consumer_path, port):
    """启动 consumer backend,返回 Popen。"""
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["NODE_ENV"] = "dev"   # 触发 buildRoute() 与 initKnexType (database.d.ts regen)
    proc = subprocess.Popen(
        ["npx", "tsx", "src/app.ts"],
        cwd=consumer_path, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return proc

def poll_health(port, timeout=30):
    """轮询 /health 直到 200 或超时。"""
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(0.5)
    return False

# 在 e2e 函数中:
port = find_free_port()
proc = start_backend(args.consumer_path, port)
try:
    if not poll_health(port):
        return False, "backend failed to start within 30s"
    # ... POST import-from-dir, query DB, assert ...
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
```

### Pattern 3: SQL 直查 snapshot,绕开 relational mismatch

**What:** e2e read-back 不走 HTTP `/api/canvas/v2/load-v2` (读 `canvas_nodes` relational), 改直接 sqlite3 query `o_agentWorkData` 表 (snapshot JSON blob)。
**When to use:** import-from-dir 走 primary `appendAndSync` 路径,只写 event + snapshot,不写 relational。
**Why:** consumer 持久化是**双轨**的 —— primary 路径 (`appendAndSync`) 写 `o_agentWorkData` JSON blob + `kv_canvasEvent` 事件日志; secondary 路径 (`save-v2` HTTP) UPSERT 到 `canvas_nodes`/`canvas_links` 关系表。`load-v2` 读关系表,所以 import-from-dir 后 load-v2 返 null (见 Pitfall 1)。

```python
import sqlite3, json, os

def read_persisted_snapshot(consumer_path, project_id, episodes_id):
    """直查 o_agentWorkData 表拿 FlowGraphV2 snapshot。"""
    db_path = os.path.join(consumer_path, "data", "db2.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM o_agentWorkData "
            "WHERE projectId = ? AND episodesId = ? AND key = 'canvasGraph'",
            (str(project_id), str(episodes_id)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])  # FlowGraphV2 dict
    finally:
        conn.close()

# 断言示例
graph = read_persisted_snapshot(args.consumer_path, pid, eid)
nodes = graph["nodes"]
links = graph["links"]
zones = [n for n in nodes if n["type"] == "zone"]
storyboards = [n for n in nodes if n["type"] == "storyboard"]
audios = [n for n in nodes if n["type"] == "audio"]
videos = [n for n in nodes if n["type"] == "video"]
summaries = [n for n in nodes if n["id"].startswith("sum-")]
seq_edges = [l for l in links if (l.get("data") or {}).get("linkType") == "sequence"]

assert len(zones) == 1, f"want 1 zone, got {len(zones)}"
assert len(summaries) == 1, f"want 1 summary, got {len(summaries)}"
assert len(storyboards) == 93, f"want 93 storyboard, got {len(storyboards)}"
assert len(audios) == 3, f"want 3 audio, got {len(audios)}"
# video: 1 artifact + 1 summary(sum-p13, type=video per buildPhaseTree) = 2
assert len(videos) == 2, f"want 2 video (1 artifact + sum-p13), got {len(videos)}"
assert len(seq_edges) == 92, f"want 92 seq edges (N-1), got {len(seq_edges)}"
```

### Pattern 4: Cross-repo path 参数化 (env var)

**What:** worktree 路径用 `CANVAS_CONSUMER_PATH` env var,不硬编码。
**When to use:** 任何 harness 引用 worktree 的地方。
**Why:** worktree 路径可能变 (worktree move / 不同 developer setup)。env var + sensible default 兼顾稳健与 zero-config。

```python
DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"
CONSUMER_PATH = os.environ.get("CANVAS_CONSUMER_PATH", DEFAULT_CONSUMER_PATH)

if not os.path.isdir(CONSUMER_PATH):
    sys.exit(
        f"CANVAS_CONSUMER_PATH not found: {CONSUMER_PATH}\n"
        f"  Set CANVAS_CONSUMER_PATH=<worktree-path> or clone kais-aigc-platform\n"
        f"  and checkout branch feat/canvas-asset-collection."
    )
if not os.path.isdir(os.path.join(CONSUMER_PATH, ".git")):
    sys.exit(f"not a git worktree: {CONSUMER_PATH}")
```

### Pattern 5: Producer-side re-export + jsonschema 校验

**What:** producer mode 不依赖 `spec/validate.py` (它 auto-discovers `output/` + 不校验 asset.json shape), 而是 inline jsonschema + 调 `export_asset.py` 重导。
**When to use:** producer mode 的核心检查。
**Why:** `spec/validate.py:48` SMOKE_SHAPES 排除 asset shape (注释: "asset.json 由 Phase 2 导出器生成,真实生产目录里没有")。所以 harness 不能依赖 validate.py 校验 asset.json。`export_asset.py` 自带 inline Draft202012Validator 自校验,write 成功即 schema-valid;但 harness 再独立校验一次确保双重保险。

```python
from jsonschema import Draft202012Validator
import json, pathlib

REPO = pathlib.Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"

def validate_asset_json(asset_path):
    """对 asset.json 跑 6 schemas 中的 asset shape。"""
    schema = json.loads((SCHEMAS_DIR / "asset.schema.json").read_text())
    validator = Draft202012Validator(schema)
    instance = json.loads(pathlib.Path(asset_path).read_text())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return errors

def run_producer_check(args):
    """re-export → validate asset.json + 5 data shapes。"""
    # 1. 复用既有 ep01 asset (CONTEXT discretion: 避免重跑 GPU pipeline)
    asset_dir = args.e2e_asset_dir  # 默认 ep01
    if not os.path.isfile(os.path.join(asset_dir, "asset.json")):
        return False, f"ep01 asset.json missing at {asset_dir}"

    # 2. (可选) re-export 覆盖既有 asset.json —— 抓 producer 漂移
    #    CONTEXT 锁:不覆盖 pinned golden (worktree fixture),但可覆盖本仓库 output/ 内的
    re_export = os.environ.get("PHASE4_RE_EXPORT") == "1"
    if re_export:
        video = os.path.join(asset_dir, os.listdir(asset_dir)[0])  # 第一个 .mp4
        # 调 export_asset.py 重导 (subprocess)
        ...

    # 3. inline 校验 asset.json
    errs = validate_asset_json(os.path.join(asset_dir, "asset.json"))
    if errs:
        return False, f"asset.json schema-invalid: {errs[0].message}"

    # 4. 5 data shapes 各自校验
    manifest = json.loads(pathlib.Path(asset_dir, "asset.json").read_text())
    for shape_key, rel_path in manifest["data"].items():
        schema = json.loads((SCHEMAS_DIR / f"{shape_key}.schema.json").read_text())
        instance = json.loads(pathlib.Path(asset_dir, rel_path).read_text())
        errs = Draft202012Validator(schema).iter_errors(instance)
        errs = sorted(errs, key=lambda e: list(e.absolute_path))
        if errs:
            return False, f"{shape_key}.json schema-invalid: {errs[0].message}"

    return True, "producer asset.json + 5 data shapes all schema-valid"
```

### Anti-Patterns to Avoid

- **走 `/api/canvas/v2/load-v2` 做 read-back** —— 读 relational table,import-from-dir 不写,返 null (见 Pitfall 1)。改 SQL 直查 `o_agentWorkData`。
- **在 worktree 加新文件 (除 database.d.ts reconcile)** —— Phase 3 已落所有需要的 consumer 侧资产 (verify script + fixture);Phase 4 是验证层,不应改 consumer 代码。`extractShotTimelineArtifacts` 等 export 已存在,直接复用。
- **强制每次跑 e2e** —— 起 backend 10-30s,慢且可能 flaky;env-gate (`PHASE4_RUN_E2E=1`) 让开发者按需 opt-in。
- **覆盖 worktree 的 pinned golden fixture** —— CONTEXT 锁:goldens 只在契约**故意**变更时手动 bump;harness re-export 的结果不能覆盖 `scripts/fixtures/shot-timeline-ep01/`。
- **硬编码 worktree 路径** —— 用 `CANVAS_CONSUMER_PATH` env var (default `/data/workspace/kst-canvas-consumer`),允许 worktree move。
- **走 save-v2 路径让 read-back 工作** —— 严格禁止 (CONTEXT 锁:e2e 走 primary appendAndSync,save-v2 是 secondary,WR-01/04 会浮现);这是用错误的方式"修"问题。
- **修 WR-01 / WR-04** —— 显式 out-of-scope (CONTEXT deferred);Phase 4 只 cross-reference Phase 3 deferred-items + 在 VERIFICATION 显式 accept。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Producer re-export | 自己拼 asset.json dict | `subprocess.run([python3, scripts/export_asset.py, ...])` | Phase 2 已落地 + inline schema 自校验;`[VERIFIED: scripts/export_asset.py exists, 321 lines]` |
| Producer schema 校验 | 自己 if/else 字段 | `jsonschema.Draft202012Validator` (系统已装 4.26.0) | Phase 1 已用同一 lib + 6 schemas;`[VERIFIED: spec/validate.py:24]` |
| Consumer 侧 structure + Zod 校验 | 重写 17 asserts | `subprocess.run([npx, tsx, scripts/verify-canvas-shot-timeline.ts])` | Phase 3 已落地 (13022 bytes);直接复用,零代码重复 |
| Backend lifecycle | 自己写 server 启停 | 仿 `scripts/check_range.py` (Phase 2) 的 find_free_port + try/finally + poll pattern | `[VERIFIED: scripts/check_range.py exists]` Phase 2 已建立此模式 |
| Health readiness probe | TCP port 探活 | `GET /health` 返 200 (`src/app.ts:183-185`) | 既有 endpoint,语义比 TCP 探活更准 (DB boot 完成) |
| Read-back persisted graph | 加 HTTP route (违反 additive-only) | 直接 sqlite3 query `o_agentWorkData` 表 | 零 consumer 改动;snapshot JSON blob 已包含完整 FlowGraphV2 |
| 5 schemas 校验 | 自写 6 套 if/else | `Draft202012Validator(schema).iter_errors(instance)` | 系统已装 + Phase 1 已验证 |
| 随机 port 选择 | hardcoded 10588 | `socket.bind(("127.0.0.1", 0))` 拿 ephemeral port | 避免与 dev backend 端口冲突;`[VERIFIED: scripts/check_range.py uses this pattern]` |

**Key insight:** 这个 phase 的全部复杂度在「orchestration」, 不在「实现新基础设施」。任何「我需要新 endpoint / 新 consumer 文件 / 新 Python 包 / 新 DB 表」都是 anti-pattern 信号 —— Phase 1-3 已铺好所有砖,Phase 4 只是把它们扣在一起验证。

## Runtime State Inventory

> 本 phase 是 cross-repo **新增** (两仓库均零 production 代码改动,只在 producer 加 harness 脚本)。不存在 rename/refactor/migration 触发条件,但仍按 5 类核对:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **Phase 3 leftover snapshot in worktree `data/db2.sqlite`**: 1 row in `o_agentWorkData` (projectId=9001, episodesId=9001, ~290KB JSON blob) + 1 row in `kv_canvasEvent` (`[VERIFIED: sqlite3 query this session]`)。无生产 DB 数据引用即将引入的 harness | None —— Phase 4 e2e 用**新** projectId/episodesId (e.g., timestamp-based) 避免碰撞;可选在 teardown 时 DELETE 自己的 test rows (不删 Phase 3 leftover) |
| Live service config | None —— 无 n8n/Datadog/Tailscale 等外部服务引用 Phase 4 harness | None |
| OS-registered state | None —— 无 systemd/pm2/launchd 注册;harness 起 backend 是临时 subprocess,退出即清理 | None |
| Secrets/env vars | None —— `src/app.ts` 不读 secret env (auth bypassed for `/api/*` in V6.0); harness 仅读 `CANVAS_CONSUMER_PATH` / `PHASE4_RUN_E2E` / `PORT` (本地测试用) | None |
| Build artifacts | **worktree dirty: `src/types/database.d.ts`** —— yarn install postinstall 在 dev 模式自动 regen (sql-ts),改了 `@db-hash` 注释 + 1 行 `score?: any → number | null` (`[VERIFIED: git diff this session]`)。是 auto-generated noise,无语义变化 | **executor 须 reconcile**: 推荐 `git checkout -- src/types/database.d.ts` (revert) —— 它是 dev-mode regen 副产品,production 启动用 `data/serve/app.js` 不依赖它。或者 commit 它 (无害)。decision 在 plan 阶段定 |

**The canonical question** 「After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?」—— 本 phase 是纯新增 (producer 加 1 个 Python 脚本) + 临时 backend subprocess,无字符串替换,故所有类别都是 "Nothing found" (除 worktree database.d.ts dirty)。已逐项 explicit 答复。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | producer harness | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `jsonschema` (Python) | producer schema 校验 | ✓ | 4.26.0 (system) | 无 (hard dep) |
| `sqlite3` (Python stdlib) | e2e read-back | ✓ | stdlib | — |
| `requests` (Python) | e2e HTTP POST | (未测) | — | **`urllib.request` (stdlib)** —— zero 新依赖,推荐直接用 urllib |
| Consumer worktree `/data/workspace/kst-canvas-consumer` | consumer mode + e2e | ✓ | HEAD bb3eaaf4, 8 commits ahead of origin/master, on `feat/canvas-asset-collection` | env var `CANVAS_CONSUMER_PATH` 参数化 |
| Node.js | consumer tsx + backend | ✓ | v24.13.0 (nvm) | — |
| `yarn` | consumer install | ✓ | 1.22.22 | — |
| worktree `node_modules/` | consumer verify + backend | ✓ | pre-installed (Phase 3 yarn install) | — |
| `better-sqlite3` native binding | backend DB | ✓ | `node_modules/better-sqlite3/build/Release/better_sqlite3.node` exists | 重跑 `yarn install` (NOT `--ignore-scripts`) |
| `tsx` (consumer devDep) | consumer verify + backend start | ✓ | ^4.21.0 | — |
| `ffprobe` | backend `extractShotTimelineArtifacts` 探 resolution | ✓ | 6.1.1-3ubuntu5 | 合成 `"0x0"` (Zod `min(1)` 通过) |
| Real producer ep01 asset | e2e 真实输入 | ✓ | `/data/workspace/kais-shot-timeline/output/虫虫武侠…第01话…/asset.json` (schema_version="1", 93 shots) | None (CONTEXT 锁:用既有 ep01,不重跑 GPU pipeline) |
| Phase 3 pinned golden fixture | consumer mode 输入 | ✓ | `scripts/fixtures/shot-timeline-ep01/` (736KB, 10 files) | None (Phase 3 已落地) |
| Free port 10588 (consumer backend default) | e2e | (可能被占) | — | harness 用 ephemeral port (find_free_port),避免冲突 |
| Docker | (不需要) | (n/a) | — | v1.0 不用 docker compose (Phase 46 才用);直接 tsx 起 backend |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None (全部可用)。`requests` 未确认是否预装,但 urllib 是 zero-dep 替代,推荐后者。

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` —— 启用。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Python stdlib `assert` + `subprocess` + `urllib`/`sqlite3` (无 pytest/unittest 配置,沿用 shot-timeline standalone-script 风格 `[VERIFIED: CLAUDE.md "None. No pytest... present in the repo"]`) |
| Config file | 无 (harness 自带 argparse + assert + sys.exit) |
| Quick run command | `python3 scripts/verify_contract.py --mode=producer` (秒级,纯 Python + jsonschema) |
| Medium run command | `python3 scripts/verify_contract.py --mode=consumer` (~5s,npx tsx 启动开销) |
| Full suite command | `python3 scripts/verify_contract.py` (默认 `--mode=all`,e2e env-gated;若 `PHASE4_RUN_E2E=1` 则含 e2e) |
| E2E-only command | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` (~30s,起 backend + POST + SQL) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VERIFY-01 | Real producer asset → POST import-from-dir → persisted graph 正确结构 (1 zone + N storyboard + 3 audio + 1 video + sequence edges) | e2e (HTTP-level, no browser) | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | ❌ Wave 0 新建 |
| VERIFY-01 (sub) | backend lifecycle (start → health → teardown) 不 leak process | e2e (subprocess + try/finally) | 同上 (内嵌在 e2e mode) | ❌ Wave 0 |
| VERIFY-01 (sub) | WR-01/WR-04 在 primary 路径不浮现 (sequence edges + sum-p13 都在 snapshot 里) | e2e (SQL read-back + assert) | 同上 (内嵌) | ❌ Wave 0 |
| VERIFY-02 (producer side) | Producer asset.json schema-valid (6 schemas) | unit (jsonschema, no I/O) | `python3 scripts/verify_contract.py --mode=producer` | ❌ Wave 0 新建 |
| VERIFY-02 (producer side) | Producer re-export 抓漂移 (corrupt asset → fail) | self-test (可选,见 Validation Architecture §Sampling) | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | ❌ Wave 0 |
| VERIFY-02 (consumer side) | Consumer importer 接受 valid asset (17 asserts A-F) | unit (纯函数,无 backend) | `python3 scripts/verify_contract.py --mode=consumer` (shell out 到 `npx tsx scripts/verify-canvas-shot-timeline.ts`) | ✅ Phase 3 已建 (worktree) |

### Sampling Rate
- **Per task commit:** `python3 scripts/verify_contract.py --mode=producer` (秒级,producer-only —— 抓 producer 漂移)
- **Per wave merge:** `python3 scripts/verify_contract.py --mode=producer --mode=consumer` (双 mode,~5s)
- **Phase gate:** `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py` (全三 mode 绿,~30s) 方可 `/gsd:verify-work`

### Regression Invariants (deliberate-drift self-test)

> 可选:`PHASE4_SELF_TEST=1` mode 注入故意漂移,确认 harness fail-loud。Planner 取舍是否落地。

| Drift simulation | Expected outcome | Implementation |
|------------------|------------------|----------------|
| Corrupt `asset.json` schema_version field (e.g., `"v1"`) | producer mode → jsonschema fail (pattern mismatch) → exit 1 | harness 写 temp invalid asset.json → run validate_asset_json → assert returns ≥1 error |
| Delete `transcript.json` from temp asset dir | producer mode → jsonschema fail (data.transcript path 不存在 — export_asset.py guard) OR harness 校验 fail | harness 复制 asset 到 temp,删除 transcript.json,跑 export_asset.py → expect sys.exit ≠0 |
| (consumer drift 不能在 producer harness 内仿真) | — | consumer mode 直接信任 Phase 3 verify script 的 17 asserts;若 consumer repo 改了 importer 拒绝 valid asset,verify-canvas-shot-timeline.ts 自动 fail (无需额外仿真) |

### Wave 0 Gaps
- [ ] `scripts/verify_contract.py` —— 新建 (本仓库),单一脚本 3 mode,~250-350 行
- [ ] (worktree dirty) `src/types/database.d.ts` —— reconcile: `git checkout` 或 commit (decision 在 plan)
- [ ] e2e 用真实 ep01 asset dir —— 已存在,零新增 (`[VERIFIED: output/虫虫武侠…第01话…/asset.json]`)
- [ ] (可选) self-test mode —— planner 取舍是否纳入 v1.0 范围

*(无既有 test/config 文件需要改 —— 本 phase 全新增,Phase 1-3 验证基础设施已就位)*

## Security Domain

> `security_enforcement` 未在 .planning/config.json 显式设 (absent = enabled)。本 phase attack surface:**e2e 起 backend on localhost + SQL 直查本地 sqlite**。无网络暴露、无 user-supplied input、无新 endpoint。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | backend V6.0 已 bypass `/api/*` auth (`src/app.ts:225-234`);harness 不引入新 auth |
| V3 Session Management | no | 同上 |
| V4 Access Control | no | harness 走 `/api/*` 内部 mesh 假设;e2e 仅本地 127.0.0.1 |
| V5 Input Validation | yes | harness POST body 用 zod-validated endpoint (consumer 已有 `validateFields`);不直接处理 user input |
| V6 Cryptography | no | 无 crypto 操作 |
| V7 Error Handling | yes | backend 启动失败 / health poll 超时 / SQL query 失败 须 graceful + 清晰错误信息 + 非 0 exit |
| V8 Data Protection | no | 不写 secrets;sqlite DB 是 worktree-local gitignored 文件 |
| V9 Communications | no | 全 127.0.0.1 loopback |
| V12 Files & Resources | yes | SQL 直查只读 `data/db2.sqlite`;harness 不写 worktree 任何文件 (除 teardown 可选 DELETE test rows) |

### Known Threat Patterns for cross-repo e2e harness

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Backend subprocess leak (test crash 后未 teardown) | Denial of Service (local) | `try/finally proc.terminate(); proc.wait(timeout=10); proc.kill()` 三层兜底 |
| Port conflict (10588 被占) | Denial of Service | `find_free_port()` 拿 ephemeral port,不抢默认 |
| Stale DB rows 累积 (多次 e2e 跑) | Information Disclosure (harmless 本地) | teardown 可选 `DELETE FROM o_agentWorkData WHERE projectId=? AND episodesId=?`;或用 timestamp-based 唯一 ID 不碰撞 |
| worktree path injection (CANVAS_CONSUMER_PATH 指向恶意 repo) | Tampering | harness 校验 path 是 git worktree + 含 `feat/canvas-asset-collection` branch;非 git 目录直接 sys.exit |
| SQL injection via projectId/episodesId | Tampering | harness 自己生成 timestamp-based int,不接受 user input;sqlite3 参数化查询 (占位符) |

## Code Examples

### 示例 1: e2e mode 完整骨架 (Python,仿 check_range.py + verify-phase-46-e2e.ts)

```python
#!/usr/bin/env python3
"""Phase 4 跨仓库契约验证 harness。

三种 mode:
  producer  —— producer re-export + jsonschema 校验 (抓 producer 漂移)
  consumer  —— shell out 到 worktree 的 verify-canvas-shot-timeline.ts (抓 consumer 漂移)
  e2e       —— HTTP-level 端到端 (起 backend + POST import-from-dir + SQL read-back)

Usage:
  python3 scripts/verify_contract.py --mode=producer
  python3 scripts/verify_contract.py --mode=consumer
  PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e
  python3 scripts/verify_contract.py                  # all (e2e env-gated)
"""
# Source: 新增于本仓库 scripts/verify_contract.py
# 模板源:scripts/check_range.py (Phase 2 server lifecycle) +
#         consumer scripts/verify-phase-46-e2e.ts (env-gate 模式)
import argparse, json, os, pathlib, socket, sqlite3, subprocess, sys, time
import urllib.request, urllib.error
from jsonschema import Draft202012Validator

REPO = pathlib.Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"
DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"
DEFAULT_E01_ASSET = (
    REPO / "output" /
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_e2e_check(args):
    """起 backend → POST import-from-dir → SQL read-back → assert。"""
    consumer = args.consumer_path
    if not os.path.isdir(consumer):
        return False, f"consumer worktree missing: {consumer}"

    # 1. 起 backend
    port = find_free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["NODE_ENV"] = "dev"
    proc = subprocess.Popen(
        ["npx", "tsx", "src/app.ts"],
        cwd=consumer, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        # 2. poll /health
        if not _poll_health(port, timeout=45):
            return False, f"backend failed /health within 45s (port {port})"
        print(f"  [e2e] backend ready on port {port}")

        # 3. POST import-from-dir
        pid, eid = int(time.time()), int(time.time()) + 1
        body = json.dumps({
            "projectId": pid, "episodesId": eid,
            "workdir": args.e2e_asset_dir, "mode": "replace",
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/canvas/v2/import-from-dir",
            data=body, headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
                if r.status != 200:
                    return False, f"import-from-dir HTTP {r.status}: {resp}"
                print(f"  [e2e] imported: {resp.get('data', {}).get('imported')} nodes")
        except urllib.error.HTTPError as e:
            return False, f"import-from-dir failed: HTTP {e.code} {e.read()[:200]}"

        # 4. SQL read-back (Pattern 3: 直查 snapshot)
        db_path = os.path.join(consumer, "data", "db2.sqlite")
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT data FROM o_agentWorkData "
                "WHERE projectId = ? AND episodesId = ? AND key = 'canvasGraph'",
                (str(pid), str(eid)),
            )
            row = cur.fetchone()
            if not row:
                return False, f"snapshot missing for pid={pid} eid={eid}"
            graph = json.loads(row[0])
        finally:
            conn.close()

        # 5. 结构断言
        nodes = graph["nodes"]
        links = graph["links"]
        zones = [n for n in nodes if n["type"] == "zone"]
        storyboards = [n for n in nodes if n["type"] == "storyboard"]
        audios = [n for n in nodes if n["type"] == "audio"]
        videos = [n for n in nodes if n["type"] == "video"]
        summaries = [n for n in nodes if n["id"].startswith("sum-")]
        seq_edges = [l for l in links if (l.get("data") or {}).get("linkType") == "sequence"]

        assert len(zones) == 1, f"zones: want 1 got {len(zones)}"
        assert len(summaries) == 1, f"summaries: want 1 got {len(summaries)}"
        assert len(storyboards) >= 1, f"storyboards: want ≥1 got {len(storyboards)}"
        assert len(audios) == 3, f"audios: want 3 got {len(audios)}"
        # videos = 1 artifact + 1 sum-p13 (buildPhaseTree 强制 summary 的 type = phase canvasType)
        assert len(videos) == 2, f"videos: want 2 (artifact+sum) got {len(videos)}"
        # WR-01 验证:sequence edges 在 primary 路径存活 (save-v2 才会 strip)
        assert len(seq_edges) == len(storyboards) - 1, \
            f"seq_edges: want {len(storyboards)-1} got {len(seq_edges)}"

        # 6. cleanup (可选)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM o_agentWorkData WHERE projectId = ? AND episodesId = ?",
                (str(pid), str(eid)),
            )
            cur.execute(
                "DELETE FROM kv_canvasEvent WHERE projectId = ? AND episodesId = ?",
                (str(pid), str(eid)),
            )
            conn.commit()
        finally:
            conn.close()

        return True, (
            f"snapshot valid: {len(nodes)} nodes, {len(links)} links, "
            f"{len(seq_edges)} seq edges (WR-01 data survives primary path)"
        )
    finally:
        # teardown (Pattern 2)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _poll_health(port, timeout=45):
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(0.5)
    return False
```

### 示例 2: producer mode (jsonschema + 复用 export_asset.py)

```python
# Source: 新增于 scripts/verify_contract.py (节选)
def run_producer_check(args):
    asset_dir = pathlib.Path(args.e2e_asset_dir)
    asset_path = asset_dir / "asset.json"
    if not asset_path.is_file():
        return False, f"ep01 asset.json missing at {asset_dir}"

    # (可选) re-export 覆盖,抓 producer 漂移 (CONTEXT: 不覆盖 worktree pinned golden)
    if os.environ.get("PHASE4_RE_EXPORT") == "1":
        # 找原始 mp4 (canonical video.mp4 是 symlink,readlink 拿 target)
        video_sym = asset_dir / "video.mp4"
        video = os.readlink(video_sym) if video_sym.is_symlink() else str(video_sym)
        stems_src = asset_dir / "stems" / "htdemucs" / asset_dir.name
        rc = subprocess.run([
            sys.executable, str(REPO / "scripts" / "export_asset.py"),
            "--work-dir", str(asset_dir),
            "--video", video,
            "--stems-source-dir", str(stems_src),
            "--output", str(asset_path),
            "--force",
        ], capture_output=True, text=True)
        if rc.returncode != 0:
            return False, f"export_asset.py failed: {rc.stderr[:300]}"

    # inline 6-schema 校验
    manifest = json.loads(asset_path.read_text())
    failures = []
    for shape_key, schema_file in [
        ("asset", "asset.schema.json"),
        ("shots", "shots.schema.json"),
        ("audio_analysis", "audio_analysis.schema.json"),
        ("transcript", "transcript.schema.json"),
        ("frames", "frames.schema.json"),
        ("prompts", "prompts.schema.json"),
    ]:
        schema = json.loads((SCHEMAS_DIR / schema_file).read_text())
        if shape_key == "asset":
            instance = manifest
        else:
            rel = manifest["data"][shape_key]
            instance = json.loads((asset_dir / rel).read_text())
        errs = sorted(Draft202012Validator(schema).iter_errors(instance),
                      key=lambda e: list(e.absolute_path))
        if errs:
            failures.append(f"{shape_key}: {errs[0].message}")

    if failures:
        return False, "; ".join(failures)
    return True, "asset.json + 5 data shapes all schema-valid"
```

### 示例 3: consumer mode (shell out 到 Phase 3 verify)

```python
# Source: 新增于 scripts/verify_contract.py (节选)
def run_consumer_check(args):
    consumer = args.consumer_path
    verify_script = os.path.join(consumer, "scripts", "verify-canvas-shot-timeline.ts")
    if not os.path.isfile(verify_script):
        return False, f"Phase 3 verify script missing: {verify_script}"

    # shell out —— Phase 3 已落地 17 asserts (A/B/C/D/E/E2/F + F2)
    rc = subprocess.run(
        ["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"],
        cwd=consumer, capture_output=True, text=True, timeout=60,
    )
    print(rc.stdout)
    if rc.returncode != 0:
        return False, f"verify-canvas-shot-timeline.ts exit {rc.returncode}\n{rc.stderr[:300]}"
    return True, "Phase 3 17 asserts all green (importer accepts golden asset)"
```

## Common Pitfalls

### Pitfall 1: `load-v2` 读 relational,`import-from-dir` 写 snapshot —— 双轨不交叉 ⚠️ CRITICAL

**What goes wrong:** e2e 用 `POST /api/canvas/v2/load-v2` 做 read-back → 返 `success(null)` → harness 误判 "导入失败"。
**Why it happens:** consumer 持久化双轨:
- **Primary** (`appendAndSync`, import-from-dir 用): 写 `kv_canvasEvent` 事件 + `o_agentWorkData` JSON blob snapshot
- **Secondary** (`saveFullGraph`, save-v2 HTTP 用): UPSERT 到 `canvas_nodes`/`canvas_links` 关系表

`load-v2.ts:50` 调 `loadFullGraph` → 读 `canvas_nodes`/`canvas_links` —— import-from-dir 走 primary,不写关系表,所以返 null。

`[VERIFIED: this session sqlite3 query on Phase 3 leftover]` —— `o_agentWorkData` 有 1 row (290KB JSON), `canvas_nodes`/`canvas_links` 都是 0 rows。两个表数据不交叉。

**How to avoid:** harness read-back 走 SQL 直查 `o_agentWorkData` 表 (见 Pattern 3):
```python
SELECT data FROM o_agentWorkData
WHERE projectId = ? AND episodesId = ? AND key = 'canvasGraph'
```
返回 JSON blob,parse 后是完整 FlowGraphV2 (nodes + links + branches + meta)。Phase 3 leftover 验证此路径:99 nodes / 190 links / 92 sequence edges 全部存活。

**Warning signs:** e2e 测试看到 `load-v2` 返 null 但 import-from-dir HTTP 200 —— 第一反应不应该是「import 没生效」,而是「读错路径了」。先 SQL count `o_agentWorkData` 确认写入,再排查 read-back。

### Pitfall 2: worktree dirty —— database.d.ts 自动 regen 噪音

**What goes wrong:** Phase 4 executor 进 worktree 准备 e2e,发现 `src/types/database.d.ts` 有未提交修改,可能误以为是 Phase 3 遗留 bug。
**Why it happens:** `src/utils/db.ts:55-56` 在 `NODE_ENV=dev` 下调 `initKnexType(db)` → `@rmp135/sql-ts` 从 live DB schema regen typescript types → 写 `src/types/database.d.ts`。任何 prior `NODE_ENV=dev yarn install` (postinstall 跑 dev-mode regen) 或 dev-mode backend 启动都会触发。

`[VERIFIED: git diff this session]` —— 当前 diff 只有 2 处:
1. `// @db-hash a69fc9b7b364746f9adc21bfce8e59b4` → `9e6a5df0ed61360bb153396cf378b211` (hash 重算)
2. `score?: any | null` → `score?: number | null` (类型推断略变)

无语义变化,是 dev-mode 副产品。

**How to avoid:** executor 在 e2e 前 reconcile:
- **推荐** `git checkout -- src/types/database.d.ts` (revert,生产路径不依赖此文件)
- 或 commit 它 (无害,只是把 dev regen 状态固化)

**Warning signs:** `git status` 显示 `modified: src/types/database.d.ts` 但你预期 worktree clean。

### Pitfall 3: `addProject` endpoint 创建 project 但 e2e 不需要

**What goes wrong:** harness 误以为要先 POST `/api/project/addProject` 创建 project 才能用 import-from-dir,多走一步且失败 (该 endpoint required fields 多)。
**Why it happens:** `kv_canvasEvent` 与 `o_agentWorkData` 表的 `projectId`/`episodesId` 列**没有 FK 到 `o_project`** (`[VERIFIED: sqlite3 schema this session]`)。consumer 把它们当作 scoped integer key,任意值都接受。Phase 3 leftover 用 (9001, 9001) 而 `o_project` 表为空 (0 rows) —— 证实无 FK 约束。
**How to avoid:** harness 直接用 timestamp-based projectId/episodesId,跳过 project 创建。可选在 teardown 时 `DELETE FROM o_agentWorkData WHERE projectId=? AND episodesId=?` 清理 (不删 Phase 3 leftover 9001/9001)。
**Warning signs:** 看到 harness 代码调 `/api/project/addProject` —— 移除。

### Pitfall 4: ep03 asset.json 损坏 (CONTEXT 已警告)

**What goes wrong:** harness 误用 ep03 (`output/《小江湖》第03话…/asset.json`) 做 e2e 输入 → JSON parse 失败 → 测试崩。
**Why it happens:** Phase 2 测试破坏过 ep03 cache (`[VERIFIED: this session python3 json.load ep03 asset.json → JSONDecodeError]`)。ep01 完好 (`[VERIFIED: ep01 asset.json parses, schema_version=1, 93 shots]`)。
**How to avoid:** hardcode harness 默认 asset dir 指向 ep01 (DEFAULT_E01_ASSET in 示例 1)。文档化 ep03 不可用的原因。
**Warning signs:** harness 报 "asset.json invalid JSON" —— 检查 asset dir 是 ep01 还是 ep03。

### Pitfall 5: backend `NODE_ENV=dev` 触发 database.d.ts regen

**What goes wrong:** e2e 用 `NODE_ENV=dev` 起 backend → 又触发 `initKnexType` → 又 dirty `src/types/database.d.ts` (与 Pitfall 2 同源)。
**Why it happens:** `src/utils/db.ts:56` 显式 gate 在 `NODE_ENV === "dev"`。
**How to avoid:** 两个选项:
- **(推荐)** e2e 用 `NODE_ENV=production` 起 backend (走 `data/serve/app.js` 编译产物,不触发 regen);但需要先 `npm run build:server`
- 或 `NODE_ENV=dev` + 在 teardown 加 `git checkout -- src/types/database.d.ts` 兜底
- 或忽略 (Pitfall 2 已说明这是无害噪音)

planner 取舍 —— 倾向 `NODE_ENV=dev` + 兜底 checkout,因为 `npm run build:server` 是额外步骤且 esbuild bundle 时间长于 dev tsx 直接跑。

### Pitfall 6: ep01 视频路径含中文 + 特殊字符

**What goes wrong:** harness 把 ep01 dir 路径传给 backend POST body,JSON 里中文 + 全角括号 + spaces 可能 URL encode 错。
**Why it happens:** ep01 dir 名是 `虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。` —— 含 CJK + 全角 `？（)：，。` + 末尾 space。
**How to avoid:** 用 `urllib.request.Request` 时 body 是 bytes (`json.dumps(...).encode("utf-8")`),header 设 `Content-Type: application/json`,不依赖 URL encoding。workdir path 作为 JSON string value 直传,backend `fs.stat(workdir)` 接受任意 UTF-8 path。`[VERIFIED: Phase 3 fixture asset.json 的 source.video_filename 含同样的 CJK]`
**Warning signs:** backend 返 400 "workdir 不存在" 但 `ls` 显示存在 —— 检查 body encoding。

### Pitfall 7: backend stdout 阻塞 (subprocess.PIPE 满)

**What goes wrong:** backend 跑一会儿,`proc.stdout` pipe buffer 满了 (64KB Linux 默认),backend 阻塞 write → e2e hang。
**Why it happens:** backend 启动 + import 期间大量 console.log (bootReady IIFE、appendAndSync debug、broadcast)。
**How to avoid:** 用 `subprocess.PIPE` 时 harness 必须主动 drain;或用 `subprocess.DEVNULL` 丢弃 (但失去 debug);或用临时文件 redirect。最简方案:
```python
proc = subprocess.Popen(..., stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```
若需 debug,改为 `stdout=open(log_path, "wb")`。
**Warning signs:** e2e hang 在 health poll 阶段,但 backend 实际已起来 —— pipe 满。

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 46 docker-compose e2e (sibling repo + canvas_sync subscriber) | Phase 4 直接 tsx 起 backend + SQL 直查 | Phase 4 (本 phase) | 不依赖 docker / sibling repo;e2e 自包含,~30s 完成 |
| Phase 46 PHASE46_RUN_E2E env-gate | Phase 4 复用同一模式 (`PHASE4_RUN_E2E=1`) | Phase 4 | 一致的 opt-in 模式;CI-friendly |
| Phase 3 verify-canvas-shot-timeline.ts (纯函数 17 asserts) | Phase 4 直接 shell out 复用 | Phase 4 | consumer 侧零代码重复;Phase 3 verify 自动成 Phase 4 子集 |
| Phase 2 inline jsonschema (export_asset.py) | Phase 4 harness 再独立校验一次 | Phase 4 | 双重保险:export 自校验 + harness 独立校验,任一失败都 fail-loud |

**Deprecated/outdated:**
- Phase 46 e2e 用 docker compose v9 —— Phase 4 不用 (overkill,单机 e2e 够)
- save-v2 路径 (WR-01/04 latent bugs) —— Phase 4 显式不修,cross-reference Phase 3 deferred-items

## Assumptions Log

> 所有 `[ASSUMED]` claims 汇总。Planner 与 discuss-phase 用此识别需用户确认的决策。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | harness 用 Python 写 (而非 tsx),落本仓库 `scripts/verify_contract.py` | User Constraints + Pattern 1 | 低:CONTEXT discretion 明确倾向 Python;若改 tsx,需落 worktree (违反「harness 落 shot-timeline」决策) |
| A2 | e2e 用既有 ep01 asset (不重跑 GPU pipeline) | User Constraints + Pitfall 4 | 极低:CONTEXT 锁定;ep01 asset.json 实测 schema-valid + 93 shots |
| A3 | `CANVAS_CONSUMER_PATH` env var default `/data/workspace/kst-canvas-consumer` | Pattern 4 + Environment Availability | 低:worktree 路径目前稳定;env var 允许 future move |
| A4 | backend 用 `NODE_ENV=dev` + `npx tsx src/app.ts` 起 (而非 `node data/serve/app.js`) | Pattern 2 + Pitfall 5 | 中:dev 模式触发 database.d.ts regen (Pitfall 2/5);planner 须选 reconcile 策略 (checkout / commit / build:server) |
| A5 | e2e 用 timestamp-based projectId/episodesId,不调 addProject | Pitfall 3 | 极低:DB schema 无 FK,Phase 3 leftover 已验证 |
| A6 | SQL 直查 `o_agentWorkData` 是 read-back 唯一非侵入路径 | Pattern 3 + Pitfall 1 | 中:若有未发现的 HTTP route 读 snapshot,可用 HTTP 替代 SQL (更优雅);本 session grep 确认无此 route (`[VERIFIED: src/routes/**/*]) |
| A7 | teardown 可选 DELETE test rows (不强制) | Pattern 3 示例 | 极低:sqlite gitignored,本地 DB 噪音无害;但多次跑会累积 |
| A8 | `requests` Python 包可能未装,harness 用 `urllib.request` (stdlib) | Environment Availability | 极低:stdlib 保证 zero 新依赖 |
| A9 | Phase 3 verify-canvas-shot-timeline.ts 的 17 asserts 是 consumer 侧回归的充分覆盖 | Validation Architecture + Pattern 5 示例 3 | 低:Phase 3 SUMMARY 已确认全绿;Phase 4 直接复用不重写 |
| A10 | SC-1 "prompt children" 在 Phase 4 e2e 不可观测 (Phase 3 已 defer prompts 为 sidecar data refs,非独立节点) | User Constraints VERIFY-01 + Architecture Patterns | 中:若用户期望 e2e 断言 prompt 节点存在,会判 SC-1 未达成;VERIFICATION 报告须显式记录此 scope 缩减并 cross-reference Phase 3 CONTEXT discretion |
| A11 | worktree HEAD `bb3eaaf4` 在 Phase 4 execution 时仍是 feat/canvas-asset-collection 分支 tip | Environment Availability | 低:若 concurrent work 推了新 commit,harness 仍 work (verifies 状态);但 database.d.ts dirty state 可能变 |

**Overall confidence:** HIGH —— 大部分关键 claims 已 `[VERIFIED]` 或基于 CONTEXT 明确 discretion。A4 (NODE_ENV choice) 与 A10 (prompts scope) 有中等 risk,planner 须在 PLAN 显式处置。

## Open Questions

1. **e2e backend 启动模式:dev tsx vs production build?**
   - What we know: `NODE_ENV=dev` 触发 `initKnexType` regen database.d.ts (Pitfall 2/5);`NODE_ENV=production` 走 `data/serve/app.js` 但需要 `npm run build:server` (esbuild bundle ~10s)
   - What's unclear: 用户对 worktree dirty state 的容忍度
   - Recommendation: **dev tsx + teardown 时 `git checkout -- src/types/database.d.ts` 兜底** —— 避免 build step,与 Phase 3 verify 模式一致 (它也用 `npx tsx`)。planner 在 Wave 0 加 reconcile step。

2. **Producer mode 是否要 re-export 覆盖既有 asset.json?**
   - What we know: `scripts/export_asset.py` 已 inline 自校验,write 成功即 schema-valid;harness 再独立校验是双重保险
   - What's unclear: 既有 ep01 asset.json 是 Phase 2 测试时产生的 (固定),是否要 Phase 4 re-export 抓"今天 producer 还能产出 valid asset"
   - Recommendation: **默认不 re-export (用既有 asset.json) + 提供 `PHASE4_RE_EXPORT=1` opt-in** —— 避免每次跑 harness 都改 output/(可能影响其他工具),但允许 manual 完整回归。CONTEXT discretion 倾向此 (「避免 GPU/Whisper 重跑」)。

3. **SC-1 "prompt children" 措辞 vs Phase 3 实际 scope?**
   - What we know: SC-1 写 "分镜/stem/字幕/prompt 集合";Phase 3 CONTEXT discretion 把 transcript/prompts 显式 defer 为 sidecar data refs (不单独建节点);e2e observable 节点集合是 storyboard/audio/video
   - What's unclear: SC-1 是否要求 prompt 节点存在?还是 prompt data 附挂在某节点 data 上即可?
   - Recommendation: **VERIFICATION 报告显式记录此 scope 缩减** —— Phase 3 已决定 (CONTEXT discretion locked),Phase 4 不重判;在 VERIFICATION §SC-1 写 "prompts/transcript 作为 sidecar data refs 保留在 asset.json#data 里,collection 节点集合不含独立 prompt 节点 (Phase 3 CONTEXT discretion)",并 cross-reference Phase 3 SUMMARY 的 D3 deferral note。

4. **Self-test mode (`PHASE4_SELF_TEST=1`) 是否纳入 v1.0?**
   - What we know: deliberate-drift 仿真 (corrupt asset → expect fail) 是回归保护的黄金标准 (证明 harness fail-loud)
   - What's unclear: 用户是否接受额外 ~50-80 行代码做 self-test
   - Recommendation: **纳入** —— 成本低 (复用 producer mode 的 jsonschema,只需写 temp invalid asset + assert raises);价值高 (回归保护「证明」)。planner 取舍。

5. **e2e cleanup:删 test rows 还是保留?**
   - What we know: 多次 e2e 跑会在 `o_agentWorkData` 累积 rows (每次新 pid/eid);sqlite gitignored,本地无害
   - What's unclear: 是否有性能或清晰度问题 (loadGraph scan 全表?)
   - Recommendation: **teardown 时 DELETE 自己的 test rows (pid+eid WHERE clause)**,不删 Phase 3 leftover (9001/9001 是 Phase 3 测试产物,保留作 cross-reference 证据)。

## Sources

### Primary (HIGH confidence)
- **Producer side (本仓库):**
  - `spec/SPEC.md` L1-455 —— ShotTimelineAsset contract (Phase 1 lock)
  - `spec/schemas/*.schema.json` (6 files) —— 机器可校验权威源
  - `spec/validate.py` L1-184 —— Phase 1 校验器 (SMOKE_SHAPES 排除 asset,Pitfall 关键)
  - `scripts/export_asset.py` L1-321 —— Phase 2 exporter (inline Draft202012Validator 自校验 L306)
  - `scripts/check_range.py` (Phase 2) —— backend lifecycle 模板 (find_free_port + try/finally)
  - `output/虫虫武侠…第01话…/asset.json` —— 真实 ep01 (schema_version="1", 93 shots, 308.352s)
  - `.planning/phases/04-cross-repo-contract-verification/04-CONTEXT.md` —— Phase 4 用户锁定决策

- **Consumer worktree (`/data/workspace/kst-canvas-consumer`, HEAD bb3eaaf4):**
  - `src/app.ts` L1-302 —— Express entrypoint (startServe + bootReady await + default port 10588 + auth bypass for `/api/*` L225-234)
  - `src/utils/db.ts` L1-116 —— DB IIFE (initDB → fixDB → loadAllFromDB → seedDefaultIfEmpty + initKnexType dev-mode regen L56)
  - `src/utils/getPath.ts` —— `data/db2.sqlite` path resolution (basePath = cwd/data)
  - `src/router.ts` L153-165 —— canvas v2 routes mount (`/api/canvas/v2/import-from-dir` etc.)
  - `src/routes/canvas/v2/import-from-dir.ts` L1670-1864 —— POST route (validateFields body schema L1672-1678, appendAndSync L1756+1828, o_agentWorkData query L1771-1776)
  - `src/routes/canvas/v2/load-v2.ts` L1-119 —— POST load (loadFullGraph reads relational L50)
  - `src/lib/canvasEventStore.ts` L1-219 —— appendAndSync + recomputeGraph + ensureBootstrap + writeSnapshot/readSnapshot
  - `src/lib/canvasRelationalStore.ts` L371-637 —— saveFullGraph (relational UPSERT) + loadFullGraph (SELECT canvas_nodes)
  - `src/routes/canvas/v2/graph-helpers.ts` L1-80 —— loadGraph reads o_agentWorkData snapshot
  - `src/routes/canvas/v2/health.ts` L1-44 —— GET /health endpoint
  - `src/routes/canvas/v2/branches.ts` L34 —— uses loadGraphFromStore internally (confirms snapshot read pattern)
  - `src/lib/initDB.ts` L521-1535 —— o_agentWorkData schema (L521-528) + kv_canvasEvent schema (L1083-1092) + canvas_nodes relational schema (L1263-1286) + migration logic (L1387+)
  - `scripts/verify-canvas-shot-timeline.ts` L1-276 —— Phase 3 verify (17 asserts, exports `extractShotTimelineArtifacts` + `setWorkdirToOss` from import-from-dir.ts L27)
  - `scripts/verify-phase-46-e2e.ts` L1-199 —— env-gate + backend-poll 模板
  - `scripts/fixtures/shot-timeline-ep01/asset.json` —— Phase 3 pinned golden (736KB)
  - `package.json` —— scripts + dependencies (express ^5.2.1, better-sqlite3 ^12.9.0, tsx ^4.21.0, knex ^3.2.5)
  - `AGENTS.md` —— worktree 工作约定

- **Phase 3 planning artifacts (本仓库):**
  - `.planning/phases/03-canvas-consumer/03-RESEARCH.md` —— consumer 架构 + 持久化双轨 + Phase 3 决策
  - `.planning/phases/03-canvas-consumer/deferred-items.md` —— WR-01 (sequence edge data stripping on save-v2) + WR-04 (sum-p13 reject by save-v2) 详细记录
  - `.planning/phases/03-canvas-consumer/03-01-SUMMARY.md` —— Phase 3 完成报告

### Secondary (MEDIUM confidence)
- worktree env 实测 (this session):
  - `git status` —— 1 dirty file (`src/types/database.d.ts`),8 commits ahead of origin/master
  - `git diff src/types/database.d.ts` —— 2 changes (db-hash + score type)
  - `python3 sqlite3 data/db2.sqlite` —— tables list + Phase 3 leftover (9001/9001) snapshot 290KB JSON blob
  - Phase 3 leftover snapshot structure: 99 nodes (1 zone + 1 sum + 93 storyboard + 3 audio + 1 video+1 sum-p13 video) + 190 links + 92 sequence edges
  - `node_modules/.bin/tsx` exists; `node_modules/better-sqlite3/build/Release/better_sqlite3.node` exists
- ep01 asset 实测: schema_version="1", source.video_filename CJK, source.duration_sec=308.352, 5 data paths, 3 stems + 1 video
- ep03 asset 实测: JSON parse 失败 (corrupted, CONTEXT 警告验证)

### Tertiary (LOW confidence)
- 无 —— 所有 claims 均来自 Primary 源或 worktree 实测

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH —— 全部依赖已在两 repo `[VERIFIED]`;零新包
- Architecture: HIGH —— 两仓库代码 + DB schema + Phase 3 leftover snapshot 全部亲查;持久化双轨是 `sqlite3 query + grep HTTP routes` 双验证
- E2E read-back path: HIGH —— Phase 3 leftover snapshot 实测可读 (99 nodes / 190 links 全部存活)
- Pitfalls: HIGH —— 全部来自代码读 + 实测 (git diff, sqlite3, json.load)
- Cross-repo path stability: MEDIUM —— worktree 路径目前稳定,但 future move 可能 (env var 兜底)
- Verify infrastructure: HIGH —— Phase 3 verify-canvas-shot-timeline.ts 是字面模板;Phase 46 e2e 是 env-gate 字面模板

**Research date:** 2026-07-21
**Valid until:** 2026-08-20 (30 天;worktree feat/canvas-asset-collection 分支可能被 concurrent ltx 工作扰动 —— execution 前 executor 须 `git -C /data/workspace/kst-canvas-consumer status` 确认 dirty 状态 + `git log --oneline -3` 确认 HEAD 仍是 bb3eaaf4 或后续 commit)
