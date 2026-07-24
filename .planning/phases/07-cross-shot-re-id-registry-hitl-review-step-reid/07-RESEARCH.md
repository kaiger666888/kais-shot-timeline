# Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`) - Research

**Researched:** 2026-07-25
**Domain:** Producer-side re-id registry pipeline (httpx client → `registry.draft.json` → first-class HITL review HTML → `registry.edits.json` → canonical `characters.json` + `props.json` + conditional asset emission + cross-file integrity). The ML route (SAM3 multi-frame → DINOv2 → AgglomerativeClustering) is DEFERRED cross-repo — mirrors Phase 6 deferral philosophy exactly.
**Confidence:** HIGH (contract layer ALREADY shipped in Phase 5 — registry/characters/props schemas + v1.1 fixture set are the frozen target shape; producer-side flow is field-reshaping + HTML generation + ffmpeg frame extraction, all patterns proven in Phase 6 + gen_timeline_html.py; literature τ defaults documented as advisory with calibration deferred per CONTEXT lock)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (不可重开)

**Cross-repo split & deferral scope (CAST-01..05, CAST-09)** — Q1/Q2/Q3:
- **route + driver live in kais-aigc-platform (cross-repo, DEFERRED).** shot-timeline builds ONLY the thin httpx client + `step_reid` + HITL tooling + apply + emission — zero ML deps in this repo (preserves CLAUDE.md loose-coupling + thin-client convention proven in Phase 6).
- **empirical τ calibration DEFERRED to post-route; lock literature three-tier defaults now.** Calibration needs SAM3 character crops (clean foreground masks) — those don't exist until the route ships. A full-frame DINOv2 spike now would be misleading (background dominates embeddings on stylized insect animation; face detection fails on non-photoreal characters). Defaults locked from registry.schema.json `$comment`: tiers `auto_merge ≥0.85 / review 0.6–0.85 / auto_distinct <0.6` (cosine DISTANCE τ ≈ 0.15 / 0.40 boundaries; literature τ≈0.30 distance ≈ similarity 0.70 sits mid-review-band — documented advisory, NOT hardcoded numeric schema constraints). RESEARCH documents the calibration protocol as a post-merge human-verification item.
- **graceful-degrade when route down:** `registry.draft.json` not written (or empty-draft); `characters.json`/`props.json` absent; asset exports without them; `generator.warnings` populated. Schema permits omission (CONTRACT-06 "only emit when file exists" — characters/props are optional in asset.schema.json). Identical shape to `step_semantic` route-down.

**HITL review format & edit round-trip (CAST-06, CAST-07)** — Q1/Q2/Q3/Q4:
- **review HTML = self-contained static monolithic HTML** (mirrors `gen_timeline_html.py` — all CSS/JS/data inlined). Cluster cards with merge/split/rename + confirm/reject; cosine-similarity-sorted review queue; three-tier threshold viz (≥0.85 green auto-merge / 0.6–0.85 yellow review / <0.6 grey auto-distinct). "Export edits" button serializes `registry.edits.json` as a download (no server).
- **`registry.edits.json` shape = structured, deterministic, schema-validated** (`spec/schemas/registry-edits.schema.json`): `{merge_groups:[[cluster_id,...]], splits:{cluster_id:[new_label,...]}, renames:{cluster_id:name}, type_overrides:{cluster_id:"char"|"prop"}, confirm_ids:[cluster_id], reject_ids:[cluster_id]}`. `apply_edits.py` consumes these deterministically + idempotently.
- **`representative_image` PNG source = producer-side ffmpeg frame extraction** at the cluster's best member `frame_pos` → `characters/<id>.png` (fallback when route's SAM3 crops are absent). When the route IS available and emits crop PNGs, those supersede. `apply_edits.py` extracts the representative frame via the same `ffmpeg -ss <ts> -i <video> -frames:v 1 -q:v 2 -vf scale=...` pattern already used by `gen_timeline_html.py`. **This keeps the producer flow demonstrable end-to-end NOW (route deferred).**
- **confirmed-only emission (Pitfall 7):** `characters.json`/`props.json` contain ONLY `review_state:"confirmed"` entries; `apply_edits.py` hard-rejects emitting proposed/rejected (rejected IDs are soft-deleted — preserved in registry.draft for reference integrity, never flowed downstream).

**step integration & counter (CAST-09)** — Q1/Q2/Q3:
- **`step_reid` = slot 6 of 8** (codec[1]/detect[2]/separate[3]/transcribe[4]/semantic[5]/**reid[6]**/timeline[7]/export[8]); counter `[N/7]`→`[N/8]`. This is the deferred `[N/8]` bump promised by Phase 6 CONTEXT (CINEMA-02).
- **review blocking = non-blocking.** `step_reid` produces `registry.draft.json` + auto-invokes `gen_registry_review.py` to emit the review HTML, but does NOT block on human review. Review is an offline manual step between `step_reid` and `apply_edits`; `apply_edits.py` is a separate standalone CLI (run by the operator after reviewing). The pipeline never waits on a human.
- **flags mirror `step_semantic` exactly** — `--skip-reid` (skip step), `--reid-url` (default `http://127.0.0.1:<port>/api/v1/production/character-reid`), `--reid-timeout` (default **960s**, > route-side ceiling), `--offline` (global; suppresses network, cache-only). `--force` clears `registry.draft.json` + `route_cache/character-reid/`.

**CONTRACT-06 emission gap + cross-file integrity** — Q1/Q2:
- **`export_asset.py` conditional characters/props emission:** add conditional emission in `build_asset_dict` — `data.characters`/`data.props` (relative .json paths) + `media.characters[]`/`media.props[]` (external .png relative paths) emitted ONLY when `characters.json`/`props.json` exist on disk. **Old assets (no registry) stay byte-identical to v1.0** (field omitted, schema-valid). Closes CONTRACT-06 that Phase 5 schema-supported but didn't wire.
- **`verify_contract.py` registry cross-file integrity:** extend the producer gate — when characters.json/props.json/registry.draft.json exist: (a) every `appearance_shots[]` shot_id must exist in shots.json (no dangling); (b) every cluster `members[].shot_id` must exist in shots.json; (c) characters.json/props.json IDs are unique + match `^(char|prop)_[0-9]{3}$`; (d) no `review_state:"proposed"` leaked into canonical files. PROMPT-03 (prompt→registry ID integrity) is Phase 8's surface, but registry↔shots integrity is Phase 7's.

### Claude's Discretion

- Exact prose of `generator.warnings` re-id messages; HTML/CSS layout of cluster cards (reuse GitHub-dark palette from gen_timeline_html.py); helper function organization within `analysis/call_reid.py`; whether `registry-edits.schema.json` lives under `spec/schemas/` (yes — consistent with other schemas); the exact cosine-similarity formatting in the review UI.

### Deferred Ideas (OUT OF SCOPE)

- **`character-reid` route + SAM3/DINOv2 driver (CAST-01/02/03/08)** — kais-aigc-platform cross-repo (mirrors `feat/shot-analysis-route`, unmerged). shot-timeline producer-side is fully buildable + testable without it; live round-trip becomes a post-merge smoke test.
- **Empirical τ calibration on ep01 (CAST-04-spike)** — needs SAM3 character crops. Literature three-tier defaults locked as advisory; calibration protocol (same-person vs different-person cosine histogram, valley pick) documented in RESEARCH as a post-merge human-verification item. A full-frame DINOv2 spike now would mislead (background-dominated).
- **SAM3 foreground-masked crop PNGs** — when the route ships, its crops supersede the producer-side ffmpeg frame-extraction fallback for `representative_image`.
- **`prompts.json#character_refs[]`/`prop_refs[]` attachment** — Phase 8 (PROMPT-01) owns attaching registry IDs to prompts. Phase 7 only produces the confirmed registry.
- **`generator.registry_snapshot` freeze** — Phase 8 (PROMPT-04) owns freezing registry state into asset.json.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **CAST-01** | kais-aigc-platform `character-reid` route + driver (SAM3 → DINOv2 → clustering) | **DEFERRED cross-repo.** Route does not exist in kais-aigc-platform today (verified: `src/routes/production/` has `shot-analysis` but no `character-reid`; no `feat/character-reid*` branch). Mirrors `feat/shot-analysis-route` deferral. shot-timeline builds the thin httpx client + STEP integration only. |
| **CAST-02** | SAM3 multi-frame sampling (N=3-5 per shot at 25/50/75%) + mask_quality + unusable skip | **DEFERRED** (route-side). Producer-side impact: `registry.schema.json#clusters[].members[].mask_quality` is schema-flexible (deliberately NOT enum-constrained — accepts 'high'/'medium'/'low'/'unusable' OR numeric scores, future-proof). |
| **CAST-03** | DINOv2 ViT-B/14 (768-d) embedding + `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)` | **DEFERRED** (route-side). Producer-side impact: `call_reid.py` normalizes route response → `registry.draft.json` shape (clusters[] with `cluster_id`/`review_state="proposed"`/`tier`/`mean_cosine`/`members`). Literature confirms τ≈0.30 distance ≈ similarity 0.70 sits mid-review-band;AgglomerativeClustering API verified (see Code Examples). |
| **CAST-04** | Three-tier thresholds (auto-merge ≥0.85 / review 0.6-0.85 / auto-distinct <0.6); default τ calibrated on ep01 | **Defaults locked (advisory).** Calibration DEFERRED per CONTEXT Q2. Three-tier rationale + calibration protocol documented in §DINOv2 Re-ID Methodology. |
| **CAST-05** | Each cluster `review_state: proposed`; only `confirmed` flows downstream; produces `registry.draft.json` | **IN SCOPE.** `call_reid.py` writes `registry.draft.json` with all clusters `review_state="proposed"` (matches spec/fixtures/v1.1/registry.draft.json target shape). Confirmed-only gating is `apply_edits.py` responsibility (CAST-07). |
| **CAST-06** | `html/gen_registry_review.py` HITL review HTML (first-class deliverable): cluster cards + merge/split/rename + cosine-sorted queue + three-tier viz → `registry.edits.json` | **IN SCOPE.** Monolithic HTML pattern + GitHub-dark palette + ffmpeg-representative-frame-as-base64 pattern all anchored in gen_timeline_html.py / gen_shots_preview.py. registry-edits.schema.json shape locked in CONTEXT. |
| **CAST-07** | `registry/apply_edits.py` → canonical `characters.json` + `props.json` (confirmed-only) | **IN SCOPE.** Deterministic + idempotent + confirmed-only hard assert (Pitfall 7). appearance_shots[] from cluster members' shot_ids; representative_image = producer-side ffmpeg frame extraction at best member's frame_pos → `characters/<id>.png`. |
| **CAST-08** | best-of-N representative crop auto-selection → `characters/<id>.png` | **DEFERRED** (route-side crop selection). Producer-side fallback: pick the cluster member with highest `mask_quality` (or first member if no signal) as the representative; ffmpeg-extract that frame. |
| **CAST-09** | `run_pipeline.py` `step_reid` (after `step_semantic`); `--skip-reid` flag; graceful-degrade (route down → skip, asset still exports) | **IN SCOPE.** step insertion point located (between step_semantic and step_timeline); 17 `[N/7]` occurrences identified for renumber; 4-flag wiring (--skip-reid/--reid-url/--reid-timeout + shared --offline); --force cache-list extension (+registry.draft.json +route_cache/character-reid/). |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP route 调用（POST character-reid） | API client (in-process, shot-timeline side) | External route (kais-aigc-platform, DEFERRED) | shot-timeline 是 thin 外部生产者；ML 推理在路由侧 ComfyUI 容器；客户端仅组 body / 发请求 / 收 response / normalize. |
| 路由 response → registry.draft.json normalize | Pipeline stage (analysis/) | — | 纯字段重组（clusters[].cluster_id/review_state/tier/mean_cosine/members）；确定性函数；fixture-verified. |
| HITL 审阅界面 | Static HTML generator (html/) | Served by scripts/serve.py (offline review) | 一等交付物；monolithic self-contained（reuse gen_timeline_html palette）；review 是 offline manual step. |
| 审阅决定 → canonical characters/props | Pipeline stage (registry/apply_edits.py) | ffmpeg (representative frame extraction) | 确定性、幂等；confirmed-only hard gate；外观 shot_ids 由 cluster members 推导. |
| Conditional emission in asset.json | Exporter (scripts/export_asset.py) | Schema (asset.schema.json, already supports) | 仅当 characters.json/props.json 存在才 emit；CONTRACT-06 closure. |
| Cross-file integrity | Verify harness (scripts/verify_contract.py) | — | registry↔shots dangling check；producer gate extension（additive，gated on file-existence）. |
| ffmpeg frame extraction (representative PNGs) | Pipeline stage (registry/apply_edits.py) | — | 同 gen_timeline_html.py:972-987 / gen_shots_preview.py:24-39 已用模式. |
| Per-video 路由缓存 | Filesystem (output/<asset>/route_cache/character-reid/) | — | 沿用 Phase 6 cache 模式；ROUTE_VERSION bump 即全 miss. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` [VERIFIED: env + pip show + in-env introspection] | 0.28.1 | sync HTTP client 调用 (DEFERRED) character-reid 路由 | env 已装（`/home/kai/.local/lib/python3.12/site-packages`）；Phase 6 已引入 + 验证 + 用同款 API；Author=Tom Christie；BSD-3-Clause；下游 diffusers/openai/mcp/huggingface_hub 都依赖. |
| `jsonschema` | 4.26.0 | inline `Draft202012Validator` 自校验 registry.draft/edits/characters/props | v1.0 已用；Phase 5 extend 时复用；本 phase 仅校验，不改 schema 工具. |
| Python stdlib `hashlib` / `json` / `pathlib` / `argparse` / `subprocess` / `re` | stdlib | cache key / JSON I/O / CLI / ffmpeg 调用 / URL scrub | 项目惯例 — 零新依赖；CLAUDE.md "stdlib-first". |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsonschema.Draft202012Validator` | 4.26.0 | registry.draft.json + registry.edits.json + characters.json + props.json 写前/读后自校验 | fails loud 惯例 — 防畸形输出流向下游；apply_edits.py 必须在写前 assert characters/props schema-valid + confirmed-only. |
| `httpx.Timeout` | 0.28.1 | 分离 connect/read/write/pool 超时 | `Timeout(connect=5.0, read=960.0, write=5.0, pool=5.0)` — read 960s 故意 > 路由 900s `execFileSync` ceiling（同 Phase 6 Pitfall 1）. |
| ffmpeg / ffprobe (外部 binary) | 6.1.1 | representative frame PNG 抽取 + duration probe | `ffmpeg -ss <ts> -i <video> -frames:v 1 -q:v 2 -vf scale=480:-1 <png>`（gen_timeline_html.py:975-979 已用）. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx` sync Client (mirroring Phase 6) | `requests` / `urllib` | Phase 6 已锁 httpx — 一致性 > 探索；env 已装；exception 层级更清晰. |
| 静态 monolithic HITL HTML | CLI 交互式 prompt / live review server | CONTEXT Q1 已锁：视觉簇审阅需缩略图（非 TTY）；单次审阅无需服务器；静态 HTML 与 timeline.html 同款（scripts/serve.py 提供）. |
| producer-side ffmpeg 代表图抽取 | 要求路由 SAM3 crops | CONTEXT Q3 已锁：路由 deferred；ffmpeg fallback 让 producer flow 现今就可端到端演示；路由出货后 SAM3 crops 超越（foreground-masked 更干净）. |
| 手写聚类 / 本地 DINOv2 | 走外部路由 | CLAUDE.md "不碰核心算法" + CONTEXT Q1 已锁；本地 fallback 会引入 torch/sklearn 依赖到 producer（破坏 thin-client）. |

**Installation:**
```bash
# 本 phase 零新依赖 — httpx 0.28.1 + jsonschema 4.26.0 Phase 6 已装 + 验证。
# ffmpeg 6.1.1 在 PATH（CLAUDE.md 已记录）。
pip show httpx        # Version: 0.28.1, Author: Tom Christie, License: BSD-3-Clause
pip show jsonschema   # Version: 4.26.0
ffmpeg -version       # 6.1.1-3ubuntu5
```

**Version verification (executed during research):**
- `python3 -c "import httpx; print(httpx.__version__)"` → `0.28.1`
- `pip show httpx` → Author-email: Tom Christie, License: BSD-3-Clause, Required-by: diffusers, gradio_client, hermes-agent, huggingface_hub, mcp, openai, python-telegram-bot, weasel
- `python3 -c "import jsonschema; print(jsonschema.__version__)"` → `4.26.0` (DeprecationWarning on `.__version__` access — cosmetic)
- `python3 -c "import sklearn"` → `ModuleNotFoundError: No module named 'sklearn'` (CONFIRMS producer-side has zero ML deps — correct per CONTEXT Q1)
- `python3 -c "import torch"` → `ModuleNotFoundError` (same — producer stays thin)
- `ffmpeg -version` → `6.1.1-3ubuntu5`

## Package Legitimacy Audit

> slopcheck 在 env（`/home/kai/.local/bin/slopcheck`），但 `install` 子命令会尝试真装、`scan` 子命令需 cwd 有 requirements.txt/pyproject.toml 等 dependency file（本 repo 无 lockfile，CLAUDE.md 已记录）。无 "verify-only" 模式。按 Protocol graceful-degradation：本 phase 零新包；唯一推荐包 `httpx` 已在 env 安装、Phase 6 已用、`pip show` 强证据（Author=Tom Christie、BSD-3-Clause、9 个下游知名包依赖）— 实际 risk 极 LOW。

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `httpx` | PyPI | ~6 yrs (0.28.1 current) | 顶层包（被 openai/diffusers/mcp/huggingface_hub 依赖） | github.com/encode/httpx | `[scan: no dependency files in cwd]` → treat as `[VERIFIED: env + pip show]`（in-env introspection 强于 slopcheck） | Approved — Phase 6 已引入 + 验证；planner 无需 checkpoint |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Note（重要 — zero new deps）：** 本 phase 唯一外部 Python 包是 `httpx`（Phase 6 已装）；jsonschema 是 v1.0 基线；其余全 stdlib + ffmpeg binary。sklearn / torch 刻意不在 env（验证确认）— 它们属于 DEFERRED 的路由侧 driver，不属于 producer。

## Architecture Patterns

### Route REQUEST Contract（DEFERRED route — shape inferred from `shot-analysis` analog）

`character-reid` 路由今天在 kais-aigc-platform 不存在（已验证：`src/routes/production/` 含 `shot-analysis` 但无 `character-reid`；无 `feat/character-reid*` 分支）。它的形状会**镜像** `feat/shot-analysis-route` 的 THIN-wrapper 模式（CONTEXT Q1 锁；已 `git -C /data/workspace/kais-aigc-platform show feat/shot-analysis-route:src/routes/production/shot-analysis/index.ts` 直接读取验证模式）：

**Predicted endpoint:** `POST /api/v1/production/character-reid`

**Predicted request body**（镜像 shot-analysis，按 driver 需求调整）:
```typescript
{
  video:           string,            // REQUIRED, host abs path（路由 docker cp 进 ComfyUI）
  shots:           string,            // REQUIRED, host path to shots.json（聚类按 shot 组织）
  shot_id_range?:  [int, int],        // OPTIONAL（shot-analysis 已证 per-shot 隔离模式）
  // 注：re-id 是跨镜聚合，可能整批调用而非 per-shot —— 但保持 shot_id_range 兼容
  mask_samples?:   int,               // OPTIONAL, default 3-5（每 shot SAM3 采样帧数 — CAST-02）
  embedding_model?:string,            // OPTIONAL, default 'facebook/dinov2-base'
  tau?:            number,            // OPTIONAL, default 0.30（cosine DISTANCE — CAST-04）
  fps?:            number,            // OPTIONAL, default 24
}
```

**Predicted response envelope**（`@/lib/responseFormat.ts:success`，同 shot-analysis）:
```json
{
  "code": 200,
  "data": {
    "clusters":   [<cluster>, ...],    // 即 registry.schema.json#clusters[] 的源头
    "count":      N,
    "outputDir":  "/mnt/agents/output/gpu1/character_reid",
    "driverStdout": "...",
    "crops":      ["char_001.png", ...]   // OPTIONAL — 路由若 emit SAM3 crops 则在此
  },
  "message": "Character re-id complete"
}
```

**Predicted cluster shape**（route → producer normalize → registry.schema.json）:
```json
{
  "cluster_id": "char_001",            // proposed ID（reviewer 在 HITL 期间可改 prefix）
  "review_state": "proposed",          // producer 永远 emit 'proposed'（CAST-05）
  "tier": "auto_merge",                // mean_cosine vs τ 决定（CAST-04）
  "mean_cosine": 0.92,                 // cosine SIMILARITY（advisory 数值）
  "members": [
    {"shot_id": 1, "frame_pos": "first", "mask_quality": "high"},
    {"shot_id": 1, "frame_pos": "last",  "mask_quality": "high"},
    {"shot_id": 2, "frame_pos": "first", "mask_quality": "medium"}
  ]
}
```

**关键：producer 的 `call_reid.py` 不假设 cluster shape 超过 registry.schema.json 的约束。** 任何路由多塞的字段（如 centroid_embedding、mask_bbox）会被 schema `additionalProperties:false` 拒掉；`call_reid.py` 在 normalize 时**显式投影**到 schema-allowed 字段（cluster_id/review_state/tier/mean_cosine/members，members 投影到 shot_id/frame_pos/mask_quality）。这与 Phase 6 `compose_facets` 显式映射同款思路。

**Route-side 900s timeout（继承 shot-analysis）：** `execFileSync(timeout=900_000)` —— 客户端 `--reid-timeout` 默认 960s 故意超出 60s（同 Phase 6 Pitfall 1）。

### System Architecture Diagram

```
   ┌── shots.json ── ── ── ── ── ── ── ──┐
   │                                        │
   ▼                                        │
  ┌──────────────────────────────┐          │
  │ run_pipeline.py:main()       │          │
  │  [1] codec                   │          │
  │  [2] detect → shots.json ────┼──────────┘
  │  [3] separate                │
  │  [4] transcribe              │
  │  [5] semantic (prompts.json) │
  │  [6] step_reid ◄────────────── NEW (this phase)
  │       │                      │
  │       │ subprocess           │
  │       ▼                      │
  │  ┌─────────────────────────────────────────────┐
  │  │ analysis/call_reid.py                       │
  │  │  1. video_content_hash (mirror Phase 6)     │
  │  │  2. preflight health probe ─────────┐       │
  │  │  3. POST /character-reid (if up)     │       │
  │  │     normalize resp → clusters[]      │       │
  │  │  4. write registry.draft.json        │       │
  │  │     + route_cache/character-reid/    │       │
  │  │  5. write warnings sidecar (route    │       │
  │  │     down → warning)                  │       │
  │  └─────────────────────────────────────────────┘
  │       │ registry.draft.json                    │
  │       ▼                                        │
  │  ┌─────────────────────────────────────────────┐
  │  │ html/gen_registry_review.py                 │
  │  │  - ffmpeg extract representative frame per  │
  │  │    cluster (best member's frame_pos)        │
  │  │  - inline as base64 (monolithic HTML)       │
  │  │  - GitHub-dark cluster cards + cosine-      │
  │  │    sorted queue + three-tier viz            │
  │  │  - "Export edits" button → download         │
  │  │    registry.edits.json                      │
  │  └─────────────────────────────────────────────┘
  │       │ registry.edits.json (operator-reviewed, offline)
  │       │                                        │
  │       │   ┌──────────────────────────────────┐ │
  │       └──►│ registry/apply_edits.py          │ │
  │           │  (standalone CLI, run AFTER      │ │
  │           │   human review — NOT in pipeline)│ │
  │           │  1. load draft + edits           │ │
  │           │  2. apply merges/splits/renames/ │ │
  │           │     type_overrides               │ │
  │           │  3. mark confirm_ids/reject_ids  │ │
  │           │  4. HARD ASSERT: confirmed-only  │ │
  │           │     (Pitfall 7)                  │ │
  │           │  5. ffmpeg extract PNG per       │ │
  │           │     confirmed cluster →          │ │
  │           │     characters/<id>.png +        │ │
  │           │     props/<id>.png               │ │
  │           │  6. atomic write characters.json │ │
  │           │     + props.json                 │ │
  │           └──────────────────────────────────┘ │
  │                                               │
  │  [7] timeline (reads prompts — unchanged)     │
  │  [8] export (CONDITIONAL emit data.characters │
  │       /data.props + media.characters[]/       │
  │       media.props[] ONLY if files exist)      │
  └──────────────────────────────┘           │
                                              ▼
                               ┌─────────────────────────┐
                               │ kais-aigc-platform      │
                               │ POST /api/v1/production/│
                               │      character-reid     │
                               │  (DEFERRED — does not   │
                               │   exist today; will     │
                               │   mirror shot-analysis) │
                               │  1. zod validate body   │
                               │  2. docker cp video     │
                               │  3. execFileSync driver │
                               │     (900s ceiling)      │
                               │     SAM3 multi-frame →  │
                               │     DINOv2 ViT-B/14 →   │
                               │     AgglomerativeCluster│
                               │  4. return {data,code}  │
                               └─────────────────────────┘

  ── on route down / --offline ──
  step_reid: registry.draft.json NOT written (or empty-draft);
             characters.json/props.json absent;
             export_asset.py emits asset WITHOUT data.characters/props +
             media.characters[]/props[] (schema-valid, byte-identical
             to v1.0); generator.warnings populated.
```

### Recommended Project Structure（Phase 7 增量）

```
analysis/                                  # 已存在（Phase 6, flat-file — NO __init__.py per CLAUDE.md）
└── call_reid.py                            # NEW — httpx client + normalize + cache (mirror call_shot_analysis.py)
registry/                                  # NEW directory (Phase 7 创建)
└── apply_edits.py                          # NEW — draft+edits → canonical characters/props (confirmed-only)
html/                                      # 已存在
└── gen_registry_review.py                  # NEW — HITL review HTML (FIRST-CLASS deliverable, CAST-06)
spec/schemas/                              # 已存在
└── registry-edits.schema.json             # NEW — edits round-trip shape
scripts/                                   # 已存在
├── export_asset.py                         # MODIFY — conditional characters/props emission
├── verify_contract.py                      # MODIFY — registry↔shots cross-file integrity
└── verify_phase7_smoke.py                  # NEW — 5-scenario regression (mirror verify_phase6_smoke.py)
run_pipeline.py                            # MODIFY — +step_reid +[N/8] counter + 4 flags + --force cache list
output/<asset>/                            # 运行时产物
├── registry.draft.json                    # NEW — step_reid 产物（pipeline-internal，NOT in asset.json#data）
├── registry.edits.json                    # NEW — operator 审阅后下载（offline manual step）
├── route_cache/
│   ├── warnings.json                      # 复用 Phase 6 sidecar（re-id 失败原因并入）
│   └── character_reid/                    # NEW — per-video 路由响应缓存
│       └── video_<hash>.json              # whole-video 聚类响应（不同于 shot_analysis 的 per-shot）
├── characters.json                        # NEW — apply_edits.py 产物（canonical, confirmed-only）
├── props.json                             # NEW — apply_edits.py 产物
├── characters/                            # NEW — 外置 PNG 目录
│   ├── char_001.png                       # ffmpeg representative frame
│   └── ...
├── props/                                 # NEW
│   ├── prop_001.png
│   └── ...
└── asset.json                             # CONDITIONAL +data.characters/props +media.characters[]/props[]
```

### Pattern 1: call_reid.py mirrors call_shot_analysis.py (Phase 6 template)

**What:** `call_reid.py` 是 `call_shot_analysis.py` 的 sibling — 同款 httpx sync client + video_content_hash + cache + preflight + graceful-degrade。
**When to use:** 唯一差异：(a) ROUTE_NAME/ROUTE_VERSION/ROUTE_PATH 常量；(b) cache 是 per-video（不是 per-shot，因为 re-id 是跨镜聚合）；(c) normalize 函数把 route response 投影到 registry.schema.json shape。

```python
# Source: Phase 6 analysis/call_shot_analysis.py + CONTEXT D-XX lock
# (call_shot_analysis.py 是 DIRECT template — 逐行对照即可)
ROUTE_NAME = "character_reid"
ROUTE_VERSION = "deferred-character-reid-route-v1"  # 路由 merge 后 bump
ROUTE_PATH = "/api/v1/production/character-reid"
REGISTRY_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "registry.schema.json"

def normalize_clusters(route_data: dict | None) -> list[dict]:
    """route response → registry.schema.json#clusters[] shape.

    显式投影：路由多塞的字段（centroid_embedding/mask_bbox 等）被丢弃 ——
    schema additionalProperties:false 会拒；这里只留 schema-allowed。
    """
    if not isinstance(route_data, dict):
        return []
    raw = route_data.get("clusters") if isinstance(route_data.get("clusters"), list) else []
    clusters = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        members = []
        for m in r.get("members") or []:
            if isinstance(m, dict) and isinstance(m.get("shot_id"), int):
                members.append({
                    "shot_id": m["shot_id"],
                    "frame_pos": m.get("frame_pos", "first"),   # 接受 string 或 number
                    **({"mask_quality": m["mask_quality"]} if m.get("mask_quality") else {}),
                })
        if not members:
            continue   # 空 cluster 丢弃（schema minItems:1）
        mc = r.get("mean_cosine")
        clusters.append({
            "cluster_id": r["cluster_id"],          # schema pattern ^(char|prop)_[0-9]{3}$
            "review_state": "proposed",              # CAST-05：producer 永远 emit proposed
            "tier": _tier_for(mc),                   # auto_merge/review/auto_distinct
            "mean_cosine": float(mc) if isinstance(mc, (int, float)) else 0.0,
            "members": members,
        })
    return clusters

def _tier_for(mean_cosine: float | None) -> str:
    """CONTEXT-locked 三档（advisory —— calibration deferred）。"""
    if not isinstance(mean_cosine, (int, float)):
        return "review"   # 未知 → 进 review 队列让人决定
    if mean_cosine >= 0.85:
        return "auto_merge"
    if mean_cosine >= 0.6:
        return "review"
    return "auto_distinct"
```

**Cache 策略差异（重要）：** re-id 是**跨镜聚合**，per-shot 调用无意义（单镜内聚类 = trivial）。所以 cache key 是 **per-video**：`route_cache/character_reid/video_<vch>.json`，存整批 clusters。不同于 shot_analysis 的 `shot_XXX.json` per-shot。

### Pattern 2: registry-edits.schema.json (the round-trip contract)

**What:** HITL HTML 产、apply_edits.py 消费的结构化 edits shape。CONTEXT Q2 锁定。
**When to use:** 任何审阅决定都序列化进这个 shape；apply_edits.py 按固定顺序应用（merge → split → rename → type_override → confirm/reject）保证 deterministic + idempotent。

```jsonc
// spec/schemas/registry-edits.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/registry-edits.schema.json",
  "title": "Registry HITL 审阅 edits（review HTML 产 → apply_edits.py 消费）",
  "$comment": "Deterministic + idempotent round-trip shape. apply_edits.py 按固定顺序应用：merge → split → rename → type_override → confirm/reject。同一 edits.json 重复 apply 产生 byte-identical characters.json/props.json。",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "merge_groups": {
      "type": "array",
      "description": "簇合并：每组 cluster_id 合并为一个（首个 ID 作为 canonical，其余 members 并入）。",
      "items": {
        "type": "array",
        "items": {"type": "string", "pattern": "^(char|prop)_[0-9]{3}$"},
        "minItems": 2
      }
    },
    "splits": {
      "type": "object",
      "description": "簇拆分：key=源 cluster_id，value=新 label 列表（apply_edits 按顺序分配新 ID）。",
      "additionalProperties": false,
      "patternProperties": {
        "^(char|prop)_[0-9]{3}$": {
          "type": "array",
          "items": {"type": "string", "minLength": 1},
          "minItems": 2
        }
      }
    },
    "renames": {
      "type": "object",
      "description": "簇重命名：key=cluster_id，value=新展示名（ID 不变）。",
      "additionalProperties": false,
      "patternProperties": {
        "^(char|prop)_[0-9]{3}$": {"type": "string", "minLength": 1}
      }
    },
    "type_overrides": {
      "type": "object",
      "description": "簇类型纠正：key=cluster_id，value=新 type（决定 ID prefix char_/prop_ +流向 characters/props）。",
      "additionalProperties": false,
      "patternProperties": {
        "^(char|prop)_[0-9]{3}$": {"type": "string", "enum": ["char", "prop"]}
      }
    },
    "confirm_ids": {
      "type": "array",
      "description": "确认条目（→ review_state='confirmed'，流向 canonical）。",
      "items": {"type": "string", "pattern": "^(char|prop)_[0-9]{3}$"}
    },
    "reject_ids": {
      "type": "array",
      "description": "拒绝条目（→ review_state='rejected'，软删除，不流向 canonical 但 ID 保留以维护引用完整性）。",
      "items": {"type": "string", "pattern": "^(char|prop)_[0-9]{3}$"}
    },
    "review_notes": {
      "type": "string",
      "description": "可选自由文本审阅备注（apply_edits 忽略；审计用）。"
    }
  }
}
```

### Pattern 3: apply_edits.py confirmed-only gate (Pitfall 7 enforcement)

**What:** apply_edits.py 的核心不变量：`characters.json`/`props.json` 永远只含 `review_state:"confirmed"` 条目；proposed/rejected 永不流向下游。
**When to use:** 写 canonical 文件前的硬 assert（不是事后过滤）。

```python
# Source: CONTEXT D-XX Q4 lock + characters.schema.json/props.schema.json $comment
def apply_edits(draft_path, edits_path, work_dir, video_path):
    with open(draft_path, encoding="utf-8") as f:
        registry = json.load(f)
    with open(edits_path, encoding="utf-8") as f:
        edits = json.load(f)

    clusters = {c["cluster_id"]: dict(c) for c in registry["clusters"]}

    # 1. merge_groups：合并（首个 ID 作 canonical）
    for group in edits.get("merge_groups", []):
        canonical_id = group[0]
        merged_members = []
        sum_cos, n = 0.0, 0
        for cid in group:
            cl = clusters.get(cid)
            if not cl:
                continue
            merged_members.extend(cl["members"])
            if isinstance(cl.get("mean_cosine"), (int, float)):
                sum_cos += cl["mean_cosine"]; n += 1
            if cid != canonical_id:
                clusters.pop(cid, None)   # 被并的 ID 软退役
        clusters[canonical_id] = {
            **clusters[canonical_id],
            "members": merged_members,
            "mean_cosine": sum_cos / n if n else 0.0,
        }

    # 2. splits：按新 label 分配新 ID（顺序沿用 max+1）
    # 3. renames：name 覆盖（在 canonical 转换时应用）
    # 4. type_overrides：改 cluster_id prefix（char_ ↔ prop_）
    # ... (omitted for brevity — pattern clear)

    # 5. confirm/reject
    for cid in edits.get("confirm_ids", []):
        if cid in clusters:
            clusters[cid]["review_state"] = "confirmed"
    for cid in edits.get("reject_ids", []):
        if cid in clusters:
            clusters[cid]["review_state"] = "rejected"
    # 其余保持 'proposed'

    # 6. ★ PITFALL 7 HARD GATE ★ —— confirmed-only, assert 在 build 时
    chars, props = [], []
    for cid, cl in clusters.items():
        if cl["review_state"] != "confirmed":
            continue   # proposed/rejected 永不流向下游
        # cluster_id prefix 决定流向
        if cid.startswith("char_"):
            chars.append(_build_char_entry(cl, edits.get("renames", {})))
        else:
            props.append(_build_prop_entry(cl, edits.get("renames", {})))

    # 7. ffmpeg 抽 representative PNG（route crops 缺失时 fallback）
    for entry in chars + props:
        _extract_representative_png(entry, work_dir, video_path)

    # 8. 写前 schema 自校验（fails loud）
    _validate(characters_schema, chars)
    _validate(props_schema, props)

    # 9. 原子写
    _atomic_write(os.path.join(work_dir, "characters.json"), chars)
    _atomic_write(os.path.join(work_dir, "props.json"), props)
```

### Pattern 4: ffmpeg representative frame extraction (fallback when route crops absent)

**What:** apply_edits.py 抽 confirmed 簇的代表帧 PNG。同 gen_timeline_html.py:975-979 / gen_shots_preview.py:24-39 已用模式。
**When to use:** 每个 confirmed cluster；best member = 最高 mask_quality（或无信号时首 member）。

```python
# Source: gen_timeline_html.py:975-979 + gen_shots_preview.py:24-39 (existing pattern)
def _resolve_frame_ts(shot_id: int, frame_pos, shots_meta: list) -> float:
    """frame_pos ('first'/'last'/'25%'/'50%'/'75%' 或 number) → seconds."""
    shot = next((s for s in shots_meta if s["id"] == shot_id), None)
    if not shot:
        return 0.0
    start, end = shot["start_sec"], shot["end_sec"]
    if isinstance(frame_pos, (int, float)):
        return float(frame_pos)
    pos = {"first": 0.0, "25%": 0.25, "50%": 0.5, "75%": 0.75, "last": 1.0}
    return start + (end - start) * pos.get(str(frame_pos), 0.5)

def _extract_representative_png(entry: dict, work_dir: str, video: str,
                                 shots_meta: list) -> None:
    """抽 best member 的帧 → characters/<id>.png（或 props/<id>.png）。

    best member 选择：mask_quality='high' > 'medium' > 'low'（无信号时首 member）。
    输出 PNG 经 canonical 路径 schema-valid：characters/char_001.png 等。
    """
    subdir = "characters" if entry["id"].startswith("char_") else "props"
    out = os.path.join(work_dir, subdir, f"{entry['id']}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # best member: 优先 high mask_quality
    members = entry["_members"]   # apply_edits 内部字段，写前删
    quality_rank = {"high": 0, "medium": 1, "low": 2}
    best = min(members, key=lambda m: quality_rank.get(m.get("mask_quality", ""), 3))
    ts = _resolve_frame_ts(best["shot_id"], best.get("frame_pos", "first"), shots_meta)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(ts), "-i", video,
         "-frames:v", "1", "-q:v", "2", "-vf", "scale=480:-1",
         out, "-loglevel", "error"],
        capture_output=True, timeout=10)
    entry["representative_image"] = f"{subdir}/{entry['id']}.png"
```

### Pattern 5: export_asset.py conditional emission (CONTRACT-06 closure)

**What:** `build_asset_dict` 仅在 characters.json/props.json 存在时 emit `data.characters`/`data.props` + `media.characters[]`/`media.props[]`。老资产 byte-identical to v1.0。
**When to use:** 永远（条件式 — 文件不存在就跳过，schema optional）。

```python
# Source: scripts/export_asset.py build_asset_dict (modify in place)
def build_asset_dict(work_dir: str, video_path: str,
                     warnings: list[str] | None = None) -> dict:
    # ... 现有逻辑（schema_version/source/generator/data/media 五字段）...
    asset = {
        "schema_version": SCHEMA_VERSION,
        "asset_type": "shottimeline",
        "source": {...},
        "generator": {...},
        "data": {
            "shots": "shots.json",
            "audio_analysis": "audio_analysis.json",
            "transcript": "transcript.json",
            "frames": "frames.json",
            "prompts": "prompts.json",
        },
        "media": {
            "video": "video.mp4",
            "stems": {...},
        },
    }
    # Phase 7: CONDITIONAL characters/props emission (CONTRACT-06)
    chars_path = os.path.join(work_dir, "characters.json")
    props_path = os.path.join(work_dir, "props.json")
    if os.path.isfile(chars_path):
        asset["data"]["characters"] = "characters.json"
    if os.path.isfile(props_path):
        asset["data"]["props"] = "props.json"
    # media.characters[]/media.props[]：列举实际存在的 PNG（canonical 命名）
    char_pngs = sorted(glob.glob(os.path.join(work_dir, "characters", "*.png")))
    if char_pngs:
        asset["media"]["characters"] = [
            f"characters/{os.path.basename(p)}" for p in char_pngs]
    prop_pngs = sorted(glob.glob(os.path.join(work_dir, "props", "*.png")))
    if prop_pngs:
        asset["media"]["props"] = [
            f"props/{os.path.basename(p)}" for p in prop_pngs]
    return asset
```

**Pre-write assert（mirror 现有 stems assert, scripts/export_asset.py:340-343）：** 每个 `media.characters[]`/`media.props[]` path 必须 resolve 到真实文件，否则 sys.exit（防 dangling-PNG-reference manifest）。

### Pattern 6: step_reid integration into run_pipeline.py

**Step counter `[N/7]` → `[N/8]` 全量更新点**（直接 grep 出的 20 处，mirror Phase 6 的 17 处 [N/6]→[N/7]）：

| File:line | 当前 (Phase 6) | Phase 7 后 |
|-----------|----------------|------------|
| `run_pipeline.py:77,81,83` | `[1/7] codec` (3 处) | `[1/8]` |
| `run_pipeline.py:101,104,111` | `[2/7] scene detection` (3 处) | `[2/8]` |
| `run_pipeline.py:119,122,130` | `[3/7] Demucs` (3 处) | `[3/8]` |
| `run_pipeline.py:138,141,149` | `[4/7] Whisper` (3 处) | `[4/8]` |
| `run_pipeline.py:182,204,213` | `[5/7] semantic` (3 处) | `[5/8]` |
| `run_pipeline.py:233,251` | `[6/7] timeline` (2 处) | `[7/8]`（让位给新 step 6） |
| `run_pipeline.py:298,330,339` | `[7/7] export` (3 处) | `[8/8]` |

**新 `step_reid` 插入：** 当前 `run_pipeline.py:459` 是 step_semantic 调用结束，line 461 是 `# 6. 时间轴 HTML`。在两者之间插入：

```python
# 6. 跨镜 re-id（character-reid 路由 —— DEFERRED；graceful-degrade）
registry_draft = os.path.join(work_dir, "registry.draft.json")
step_reid(video, work_dir, shots, registry_draft,
          args.skip_reid, args.offline,
          args.reid_url, args.reid_timeout)
```

**新 `step_reid` 函数（mirror `step_semantic`，line 153-222）：**

```python
def step_reid(video: str, work_dir: str, shots_json: str,
              registry_draft: str, skip: bool, offline: bool,
              reid_url: str, reid_timeout: float) -> str:
    """跨镜 re-id —— 调用（DEFERRED）character-reid 路由，产 registry.draft.json。

    路由不可达时 graceful-degrade：不写 registry.draft.json（或写空 draft），
    characters.json/props.json 缺席，asset 仍导出（CONTRACT-06 conditional emission），
    generator.warnings 记失败原因。
    """
    if skip:
        print("[6/8] --skip-reid: skipping cross-shot re-id")
        return registry_draft if os.path.exists(registry_draft) else None
    # mtime cache（mirror step_semantic，TOCTOU-safe via _safe_mtime）
    video_stamp = registry_draft + ".video-stamp"
    cached_video_id = None
    if os.path.exists(video_stamp):
        try:
            with open(video_stamp, encoding="utf-8") as f:
                cached_video_id = f.read().strip()
        except OSError:
            cached_video_id = None
    current_video_id = _video_identity(video)
    if (os.path.exists(registry_draft)
            and _safe_mtime(registry_draft) > _safe_mtime(shots_json)
            and cached_video_id is not None
            and cached_video_id == current_video_id):
        print(f"[6/8] cached registry draft: {registry_draft}")
        return registry_draft
    cmd = [sys.executable, str(HERE / "analysis" / "call_reid.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", registry_draft,
           "--reid-url", reid_url,
           "--reid-timeout", str(reid_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[6/8] cross-shot re-id (character-reid route)")
    if current_video_id is not None:
        try:
            with open(video_stamp, "w", encoding="utf-8") as f:
                f.write(current_video_id)
        except OSError:
            pass
    return registry_draft if os.path.exists(registry_draft) else None
```

**新 argparse flags（mirror step_semantic 的 4 flags）：**

```python
ap.add_argument("--skip-reid", action="store_true",
                help="跳过跨镜 re-id（character-reid 路由调用）")
# --offline 已在 Phase 6 加（全局，reid 复用）
ap.add_argument("--reid-url",
                default="http://127.0.0.1:8000/api/v1/production/character-reid",
                help="character-reid 路由 URL（含 /api/v1/production/character-reid path；"
                     "默认端口 8000 — 路由 DEFERRED 未上线，首跑需 verify 实际端口）")
ap.add_argument("--reid-timeout", type=float, default=960.0,
                help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
```

**`--force` cache 清单扩展（run_pipeline.py:423-432）：**

```python
for p in (shots_json, frames_json, audio_json, transcript, out_html,
          asset_json, asset_json + ".video-stamp",
          prompts_json, prompts_json + ".video-stamp",
          registry_draft,                                   # NEW Phase 7
          registry_draft + ".video-stamp",                  # NEW Phase 7
          route_cache_dir):                                 # Phase 6（已含；reid cache 在其下）
```

### Pattern 7: HITL review HTML design (CAST-06 — FIRST-CLASS deliverable)

**What:** `html/gen_registry_review.py` 产 self-contained HTML，让 reviewer 视觉审阅 cluster 草稿并导出 `registry.edits.json`。
**When to use:** step_reid 后；操作员在 `scripts/serve.py` 上打开审阅；下载 edits.json；手动跑 `apply_edits.py`。

**Layout（reuse gen_timeline_html.py palette + monolithic pattern）：**
- **Header:** asset name + cluster count + 三档 summary（`🟢 N auto-merge · 🟡 M review · ⚪ K auto-distinct`）
- **Cosine-sorted review queue（右侧或顶部）:** mid-band (0.6–0.85) 簇优先 surface（最难决定先审）；每条显示 cluster_id + mean_cosine bar + thumbnail
- **Cluster cards（主体）:**
  - Representative thumbnail（base64 inline — gen_registry_review 在 HTML 生成时 ffmpeg 抽帧，因为 canonical PNGs 还没存在）
  - cluster_id + editable name input
  - tier badge（green/yellow/grey）
  - members list（shot_id + frame_pos + mask_quality chip）
  - mean_cosine progress bar
  - Actions: [✓ Confirm] [✗ Reject] [↔ Merge with...] [✂ Split] [🔄 Type: char/prop]
- **Footer:** "Export edits" button（serialize registry.edits.json → download as file，no server）

**关键设计决策：**
- **Thumbnails = base64 inline at HTML-generation time.** 因为 apply_edits.py 在 review *之后* 才抽 PNG，review 时 canonical PNGs 不存在。gen_registry_review.py 自己 ffmpeg 抽每个 cluster 的代表帧（同 Pattern 4 的 best-member 选择），inline 成 data URI。这让 review HTML 完全自包含（同 timeline.html）。
- **Cosine-sorted queue surface mid-band first.** auto_merge (≥0.85) 默认全选 confirm；auto_distinct (<0.6) 默认全选 confirm 为独立实体；review band (0.6–0.85) 是人必须决定的，surface 在顶部。
- **Export = client-side download.** `Blob([JSON.stringify(edits)]) + URL.createObjectURL + a.download`。无服务器依赖（review 是 offline manual step）。

### Anti-Patterns to Avoid

- **把 ML 推理搬进 shot-timeline**（本地 DINOv2 / sklearn 聚类 fallback）：CONTEXT Q1 已拒；破坏 thin-client + 加 torch/sklearn 依赖（验证：env 无 sklearn/torch，刻意保持）。
- **`apply_edits.py` 过滤而非 gate**：写全量再 filter 留 confirmed —— 任何中间步骤 bug 都可能让 proposed 泄漏下游。必须 hard assert 在 build 时（Pattern 3 step 6）。
- **HITL HTML 假设 canonical PNGs 已存在**：review 在 apply_edits 之前，PNGs 还没抽。HTML 必须 inline base64 thumbnails（gen_registry_review.py 自己 ffmpeg 抽）。
- **`call_reid.py` per-shot 调用**：re-id 是跨镜聚合，per-shot 调用无意义。cache 是 per-video，不是 per-shot（与 shot_analysis 差异）。
- **`export_asset.py` 无条件 emit characters/props**：必须 file-existence gated（CONTRACT-06 "only emit when file exists"）；老资产保持 byte-identical。
- **`registry-edits.schema.json` 允许自由文本 notes 替代结构化字段**：CONTEXT Q2 已锁结构化 + deterministic + idempotent；自由文本不可重现。
- **step_reid 阻塞 pipeline 等人审阅**：CONTEXT Q2 已锁非阻塞；apply_edits 是独立 CLI，pipeline 永不等人。
- **`--reid-url` 默认端口假设**：路由 DEFERRED 未上线，端口未验证（Phase 6 同款 Open Question）；文档化"首跑需 verify"。
- **`_safe_error` URL scrubbing 缺失**：Phase 6 WR-05 已修；call_reid.py 必须复用同款 `re.sub(r"(https?://)([^@/]+@)", r"\\1***@", msg)` 防 user:pass@ 流进 warnings → asset.json。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP 连接池 / timeout / retry | 手 socket / urllib | `httpx.Client` (Phase 6 已用) | env 已装、exception 层级清晰、Phase 6 验证 |
| Per-video cache key | 全文件 sha256 | head 1MB + tail 1MB + size sha256 (Phase 6 已实现) | multi-GB episode 视频全读需数十秒 |
| AgglomerativeClustering / DINOv2 / SAM3 | 在本仓库跑 ML | 走 DEFERRED 路由 | CLAUDE.md "不碰核心算法" + CONTEXT Q1 |
| schema 校验 | 手写字段检查 | `jsonschema.Draft202012Validator` (v1.0 已用) | strict-schema × lenient-consumer 原则 |
| Frame 抽取 | PIL / cv2 read | `ffmpeg -ss <ts> -i ... -frames:v 1` (项目惯例) | gen_timeline_html.py + gen_shots_preview.py 已证 |
| HTML 模板 / palette | 自己配色 | GitHub-dark tokens (gen_timeline_html.py:131-941) | 项目视觉一致性 |
| URL userinfo 抹除 | 自己写正则 | Phase 6 `_safe_error` (call_shot_analysis.py:111-122) | 已实现 + 已审（WR-05） |

**Key insight:** Phase 7 的本 phase 边界是"网络调用 + 字段重组 + HITL HTML + 确定性 apply + 条件 emission"。任何把 ML 搬进本仓库的冲动都是范围溢出（CONTEXT Q1 + REQUIREMENTS Out-of-Scope 已明列）。

## DINOv2 Re-ID Methodology (CAST-03/04 — deferred route-side, documented for planner context)

### Why DINOv2 not CLIP (REQUIREMENTS Out-of-Scope lock)

REQUIREMENTS.md `## Out of Scope` 明列：「CLIP / OpenCLIP 做 re-id embedding — image-text 对齐不适合实例身份识别；DINOv2 自监督才是正解」。文献支持：

- **CLIP** 训练目标是 image-text 对齐（contrastive on caption pairs）—— embedding 空间优化的是"这张图匹配这段文字"，不是"这两个视觉实例是同一实体"。同一身份不同视角/光照下 CLIP embedding 可能漂移；不同身份但语义相似（"a man in red"）可能聚拢。
- **DINOv2** (Meta AI, 2023) 自监督训练（image-level self-distillation + patch-level masked modeling）—— embedding 空间自然涌现 instance-level 不变性。官方 paper 报告 image retrieval by cosine similarity 作为核心评估；社区已广泛用于 instance similarity / face search（Kaggle DINOv2 face similarity notebook, Reddit r/computervision instance similarity thread）。

[CITED: arxiv.org/abs/2304.07193 — DINOv2 paper, image retrieval via cosine similarity]
[CITED: huggingface.co/docs/transformers/en/model_doc/dinov2 — ViT-B/14, 768-d features]

### AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ) — verified API

scikit-learn current (v1.9) API — confirmed via official docs fetched during research:

- **Parameter is `metric`** (NOT `affinity` — `affinity` deprecated in 1.2, removed slated; `metric` added 1.2). Valid values: `"euclidean"`, `"l1"`, `"l2"`, `"manhattan"`, `"cosine"`, `"precomputed"`.
- **`linkage="average"` valid with `metric="cosine"`** — only `linkage="ward"` restricts to euclidean/l2.
- **`distance_threshold` semantics:** "The linkage distance threshold at or above which clusters will not be merged." Requires `n_clusters=None` + `compute_full_tree=True` (auto-True when distance_threshold set).
- **distance = 1 - cosine_similarity** (Stack Overflow + scikit-learn GitHub issue #27434) — cosine distance ranges [0, 2]; for L2-normalized features cosine_sim ∈ [-1, 1] so distance ∈ [0, 2], but in practice for non-negative image features distance ∈ [0, 1].

[CITED: scikit-learn.org/stable/modules/generated/sklearn.cluster.AgglomerativeClustering.html — official v1.9 docs, fetched 2026-07-25]

### Three-tier default justification (CAST-04 — advisory, calibration deferred)

registry.schema.json `$comment` locks: `auto_merge ≥0.85 / review 0.6–0.85 / auto_distinct <0.6` (cosine SIMILARITY). Equivalent cosine DISTANCE boundaries: `auto_merge ≤0.15 / review 0.15–0.40 / auto_distinct >0.40`.

**Literature anchoring (advisory, not authoritative for animation domain):**
- **τ ≈ 0.30 cosine DISTANCE ≈ similarity 0.70** sits mid-review-band — matches unsupervised re-id literature typical `distance_threshold` range 0.3–0.7 (scikit-learn practitioner surveys; Hu et al. 2021 threshold-based hierarchical clustering on Market-1501 achieves mAP=68.8%, DukeMTMC-reID 78.5%).
- **SOTA unsupervised re-id mAP 60–80%** (Market-1501 / DukeMTMC-reID benchmarks) — matches REQUIREMENTS.md Out-of-Scope justification「SOTA 换衣 re-id 60-80% mAP、动画更差；误聚类率破坏叙事连贯命题——人工 review 是 feature 不是 polish」. This is *why* HITL is mandatory (CAST-06 first-class), not optional polish.
- **DINOv2-specific published threshold 0.85 NOT FOUND in literature** — WebSearch returned no paper using exactly 0.85 as DINOv2 ViT-B/14 re-id threshold. The value is application-specific, depends on: dataset (photoreal vs stylized animation), feature pooling (CLS token vs patch average), L2-normalization, fine-tuning. **This is exactly why CONTEXT Q2 defers empirical calibration** — locking 0.85 as "the answer" without ep01 crops would be false precision.

[CITED: arxiv.org/abs/1705.10444 — Fan et al. 2017 unsupervised re-id clustering + threshold λ (893 citations)]
[CITED: pmc.ncbi.nlm.nih.gov/articles/PMC8145342/ — Hu et al. 2021 threshold-based hierarchical clustering, Market-1501 mAP=68.8%]

### Deferred τ calibration protocol (post-merge human-verification item)

**Trigger:** After `character-reid` route merges + ships SAM3 multi-frame crops for ep01.

**Protocol:**
1. Run route on ep01 → collect SAM3 foreground-masked character crops (per shot, N=3-5 frames).
2. Run DINOv2 ViT-B/14 on each crop → 768-d embeddings (L2-normalize).
3. **Same-person pairs:** manually label ~50 known-same-identity crop pairs (across shots). Compute cosine similarity distribution.
4. **Different-person pairs:** sample ~200 known-different pairs. Compute cosine similarity distribution.
5. **Histogram overlay:** plot both distributions; the valley (minimum overlap) is the optimal τ (Bayes-optimal decision boundary).
6. **Three-tier refinement:** if valley is sharp, tighten auto_merge/review boundaries; if distributions overlap heavily (likely on stylized animation), widen review band + document that HITL is load-bearing (not optional).
7. **Lock:** update registry.schema.json `$comment` with calibrated values; bump `ROUTE_VERSION` in call_reid.py to invalidate stale caches.

**Why deferred (CONTEXT Q2 rationale):**
- SAM3 crops don't exist until route ships (clean foreground masks; full-frame DINOv2 spike now would mislead — background dominates embeddings on stylized insect animation; face detection fails on non-photoreal characters).
- Locking literature defaults as *advisory* (not numeric schema constraints) keeps the contract flexible — calibration can refine without schema revision (`tier` field is authoritative label, `mean_cosine` is advisory number).

## Runtime State Inventory

> Phase 7 is **greenfield-additive** in this repo (new files: call_reid.py / apply_edits.py / gen_registry_review.py / registry-edits.schema.json / verify_phase7_smoke.py; modified: export_asset.py / verify_contract.py / run_pipeline.py). No rename/refactor/migration of existing runtime state. SKIPPED (not a rename/refactor phase).

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — all new files write to `output/<asset>/` work_dir (pipeline-internal) | None |
| Live service config | None — no external service config in this repo (route is cross-repo DEFERRED) | None |
| OS-registered state | None | None |
| Secrets/env vars | None — CLAUDE.md confirms no .env, all config via CLI flags | None |
| Build artifacts | None — no egg-info / compiled binaries; Python runs directly | None |

## Common Pitfalls

### Pitfall 1: Proposed/rejected leaking into canonical characters.json/props.json (Pitfall 7 in registry.schema.json $comment)
**What goes wrong:** apply_edits.py 写全量 clusters 再 filter，中间步骤 bug 让 `review_state:"proposed"` 条目流进 characters.json → 下游 prompt 引用挂到未审阅实体 → 叙事连贯命题崩。
**Why it happens:** filter-after-write 比 build-time gate 更易写；看起来等价但任何 build 顺序错（如先组装 entries 再 apply confirm/reject）就泄漏。
**How to avoid:** apply_edits.py Pattern 3 step 6 — build canonical entries 时 `if cl["review_state"] != "confirmed": continue`（hard gate，非 filter）。**verify_contract.py 必须加 assert：characters.json/props.json 中无 `review_state:"proposed"`**（CONTEXT Q2 锁）。
**Warning signs:** characters.json/props.json 含 `review_state` 非 `confirmed` 值；或条目数 > registry.draft.json 中 confirmed count。

### Pitfall 2: HITL HTML references canonical PNGs that don't exist yet
**What goes wrong:** gen_registry_review.py 假设 `characters/<id>.png` 已存在 → `<img src="characters/char_001.png">` broken icon → reviewer 看不到缩略图，审阅无效。
**Why it happens:** canonical PNGs 是 apply_edits.py *在 review 之后* 抽取的；review 时它们不存在。
**How to avoid:** gen_registry_review.py **自己** ffmpeg 抽代表帧（同 Pattern 4），inline 成 base64 data URI（同 timeline.html 的 frames.json 模式）。HTML 完全自包含。
**Warning signs:** review HTML `<img>` 指向 `characters/*.png`（应指向 `data:image/jpeg;base64,...`）。

### Pitfall 3: export_asset.py unconditional characters/props emission breaks byte-identical promise
**What goes wrong:** 开发者在 `build_asset_dict` 直接 emit `data.characters`/`data.props`（不管文件是否存在）→ 老 asset 重导时多出空字段 → 不 byte-identical to v1.0 → 跨版本 fixture regression 失败。
**Why it happens:** 忘了 CONTRACT-06 "only emit when file exists" 是 conditional，不是 always。
**How to avoid:** Pattern 5 — `if os.path.isfile(chars_path): asset["data"]["characters"]=...`。verify_phase7_smoke.py 场景 1（route_down）必须 assert asset.json 无 characters/props 字段。
**Warning signs:** v1.0 minimal fixture 重导后含 characters/props 字段（应为 absent）。

### Pitfall 4: call_reid.py per-shot cache key (wrong granularity)
**What goes wrong:** 沿用 shot_analysis 的 `shot_XXX.json` per-shot cache → re-id 是跨镜聚合，per-shot cache 文件存的是不完整中间态，重跑时 miss/命中逻辑混乱。
**Why it happens:** copy-paste Phase 6 模式未思考 re-id 的跨镜语义。
**How to avoid:** Pattern 1 — cache 是 **per-video**：`route_cache/character_reid/video_<vch>.json`，存整批 clusters。cache key = `(video_content_hash, route_name, route_version)`（无 shot_id）。
**Warning signs:** route_cache/character_reid/ 下出现 shot_XXX.json（应为 video_<hash>.json）。

### Pitfall 5: apply_edits.py 非幂等（重跑产生不同 ID）
**What goes wrong:** splits 分配新 ID 用 `len(clusters)+1` 而非确定性排序 → 同一 edits.json 两次 apply 产生不同 char_004/char_005 分配 → 重跑后 characters.json 不 byte-identical → Phase 8 prompt refs 指向错 ID。
**Why it happens:** dict 迭代顺序 + 自增 counter 不稳定。
**How to avoid:** 新 ID 分配用确定性算法：`max_existing_N + 1`（按 cluster_id 数值部分排序）；splits 内部按 label 字典序分配。CONTEXT Q2 锁"idempotent"。
**Warning signs:** 同 edits.json 两次 apply 产生不同 characters.json（diff 非空）。

### Pitfall 6: `--force` 不清 registry cache → 改代码后行为不变
**What goes wrong:** bump ROUTE_VERSION 但 `--force` 只清了 Phase 6 列表 → route_cache/character_reid/ 残留旧版响应 → call_reid 读 cache 跳过网络。
**Why it happens:** `--force` 清单（run_pipeline.py:423-432）当前是 Phase 6 列表，无 Phase 7 项。
**How to avoid:** Pattern 6 — `--force` 清单 +`registry_draft` + `registry_draft + ".video-stamp"`（route_cache_dir 已在 Phase 6 列表，rmtree 会一并清 character_reid/ 子目录）。
**Warning signs:** 改 ROUTE_VERSION 但 registry.draft.json 内容没变。

### Pitfall 7: `mean_cosine` 与 `tau` 单位混淆（distance vs similarity）
**What goes wrong:** registry.schema.json 同时有 `tau`（cosine DISTANCE）和 `cluster.mean_cosine`（cosine SIMILARITY）—— 开发者误把 `mean_cosine < tau` 当合并条件（实际应 `mean_cosine > 1 - tau`）。
**Why it happens:** schema 同一字段名前缀 `cosine` 但语义相反。
**How to avoid:** schema `$comment` 已明确区分；call_reid.py `_tier_for()` 用 similarity 直接比对（0.85/0.6）不转换；apply_edits.py 不读 tau（tier 字段是 authoritative label）。代码注释复述语义。
**Warning signs:** tier 字段与 mean_cosine 不一致（如 mean_cosine=0.9 但 tier="auto_distinct"）。

### Pitfall 8: step_reid 阻塞 pipeline 等人审阅
**What goes wrong:** step_reid 调 apply_edits.py 或等 reviewer 反馈 → pipeline 卡住，单集导出从分钟级变小时级。
**Why it happens:** 混淆"产 draft + emit review HTML"（pipeline 内）与"consume edits → canonical"（offline manual step）。
**How to avoid:** CONTEXT Q2 锁：step_reid 只产 registry.draft.json + 自动调 gen_registry_review.py 产 HTML；apply_edits.py 是**独立 standalone CLI**（不在 run_pipeline 内）。
**Warning signs:** run_pipeline.py 出现 apply_edits subprocess 调用。

### Pitfall 9: registry.draft.json 流进 asset.json#data（它不是 canonical asset data）
**What goes wrong:** 把 `registry.draft.json` 加进 `data` 字段 → 下游消费者看到 proposed 状态草稿 → Pitfall 7 在 consumer 侧复发。
**Why it happens:** 混淆 pipeline-internal 工作产物与 canonical asset data。
**How to avoid:** registry.schema.json description 已明列「registry.draft.json 是 pipeline-internal 工作产物，不在 asset.json#data 中列出——只有审阅后的 characters.json + props.json 才是 canonical asset data files」。verify_contract.py `validate_eight_shapes` 已按 canonical 文件名直接查 registry.draft.json（不读 asset.json#data）。
**Warning signs:** asset.json#data 含 `"registry": "registry.draft.json"`。

## Code Examples

### Example 1: DINOv2 embedding + AgglomerativeClustering (route-side, DEFERRED — documented for context)

```python
# Source: CAST-03 REQUIREMENTS + scikit-learn v1.9 official docs (fetched 2026-07-25)
# THIS CODE LIVES IN kais-aigc-platform character_reid_driver.py (DEFERRED) — NOT in this repo.
# Documented here so the planner understands what the route produces + what call_reid.py normalizes.

import numpy as np
from sklearn.cluster import AgglomerativeClustering
# DINOv2 ViT-B/14 via transformers or torch.hub
# embeddings: np.ndarray shape (N_crops, 768), L2-normalized

# L2-normalize (so cosine_sim = dot product)
embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

TAU = 0.30   # cosine DISTANCE threshold (CAST-04 default; calibration deferred)
clusterer = AgglomerativeClustering(
    n_clusters=None,              # REQUIRED when distance_threshold set
    metric="cosine",              # v1.2+ parameter name (NOT affinity — deprecated)
    linkage="average",            # valid with cosine (only 'ward' requires euclidean)
    distance_threshold=TAU,       # clusters merge below this distance, separate at/above
)
labels = clusterer.fit_predict(embeddings)

# Build clusters[] for registry.draft.json:
for label in sorted(set(labels)):
    member_idxs = np.where(labels == label)[0]
    member_embeddings = embeddings[member_idxs]
    # mean pairwise cosine SIMILARITY within cluster (advisory)
    sim_matrix = member_embeddings @ member_embeddings.T
    mean_cosine = float(sim_matrix[np.triu_indices(len(member_idxs), k=1)].mean())
    tier = "auto_merge" if mean_cosine >= 0.85 else "review" if mean_cosine >= 0.6 else "auto_distinct"
    # emit cluster {cluster_id, review_state:"proposed", tier, mean_cosine, members:[...]}
```

### Example 2: call_reid.py normalize + write registry.draft.json (IN SCOPE)

```python
# Source: Phase 6 analysis/call_shot_analysis.py template + CONTEXT D-XX
import httpx  # lazy import (WR-02 pattern)

def call_reid_route(client, body, timeout):
    """单次 per-video POST（re-id 是跨镜聚合，非 per-shot）。"""
    try:
        resp = client.post(ROUTE_PATH, json=body)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as e:
            return None, _safe_error(f"non-JSON body: {type(e).__name__}: {e}")
        if not isinstance(payload, dict):
            return None, _safe_error(f"envelope not dict: {type(payload).__name__}")
        if payload.get("code") != 200:
            return None, _safe_error(f"code={payload.get('code')}: {payload.get('message')}")
        data = payload.get("data")
        return (data if isinstance(data, dict) else None), None
    except (httpx.HTTPError, ValueError, AttributeError, TypeError, KeyError) as e:
        return None, _safe_error(f"{type(e).__name__}: {e}")

# main() flow:
# 1. video_content_hash(video) → vch
# 2. cache_file = route_cache/character_reid/video_<vch>.json (per-video, NOT per-shot)
# 3. cache hit (with _cache_key matching vch+route_name+route_version)? → use cached
# 4. else: preflight + POST → normalize_clusters(data) → write cache
# 5. compose registry.draft.json: {generated_at, model, tau, clusters: normalize_clusters(...)}
# 6. schema-validate via Draft202012Validator(registry.schema.json)
# 7. atomic write registry.draft.json
# 8. write warnings sidecar (route down → warning, file still absent)
```

### Example 3: verify_phase7_smoke.py scenario skeleton (mirror Phase 6)

```python
# Source: scripts/verify_phase6_smoke.py (DIRECT template — 4 scenarios → 5 scenarios)
# 5 scenarios（每独立 temp work_dir，互不污染）：

# 1. route_down (CAST-09 graceful-degrade)
#    unreachable URL → registry.draft.json absent + asset exports WITHOUT
#    data.characters/props + generator.warnings 含 "reid" 字样

# 2. skip_reid (CAST-09 flag)
#    run_pipeline.step_reid(skip=True) → stdout 含 "--skip-reid: skipping"
#    + 不含 "[6/8] cross-shot re-id" run_step banner

# 3. empty_draft_handoff (CAST-05 boundary)
#    seed registry.draft.json with clusters:[] → gen_registry_review.py 仍产
#    HTML（empty state）+ apply_edits.py 产空 characters.json/props.json
#    （或文件缺席）+ asset exports without them

# 4. apply_edits_idempotent (CAST-07 confirmed-only + idempotency)
#    seed registry.draft.json fixture + registry.edits.json fixture →
#    run apply_edits.py twice → assert characters.json/props.json
#    byte-identical + only confirmed entries + schema-valid +
#    appearance_shots ⊆ fixture shots.json

# 5. cache_hit_offline (CAST-09 + CINEMA-04 analog)
#    seed route_cache/character_reid/video_<vch>.json with fixture clusters +
#    correct _cache_key → run call_reid.py --offline → exit 0 + draft 用
#    cache 值 + stdout 含 "cache hit" + 0 网络调用
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CLIP for re-id | DINOv2 self-supervised | DINOv2 (2023) | 实例身份不变性涌现；CLIP image-text 对齐不适合 |
| `affinity='cosine'` (sklearn) | `metric='cosine'` | sklearn 1.2 (2022) | affinity deprecated；新参数名 metric |
| 全自动 re-id（无 HITL） | mandatory HITL review | 本项目 CONTEXT Q1 | 接受 SOTA 60-80% mAP，review 是 feature 非 polish |
| base64 内嵌角色图 | 外置 characters/<id>.png | Phase 5 schema lock | 防 10-50× 资产膨胀（frames.json 教训） |
| per-shot cache | per-video cache（re-id 跨镜聚合） | 本 phase 设计 | cache 粒度匹配算法语义 |

**Deprecated/outdated:**
- sklearn `affinity` parameter (deprecated 1.2, use `metric`).
- CLIP for instance re-id (REQUIREMENTS Out-of-Scope — image-text alignment wrong objective).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `character-reid` route will mirror `shot-analysis` THIN-wrapper pattern (Zod body + docker cp + execFileSync driver + `{code,data,message}` envelope) | Route REQUEST Contract | 低 — shot-analysis 是同团队同 repo 的成熟模板；route 出货后偏差需 call_reid.py normalize 适配（已设计显式投影，见 Pattern 1） |
| A2 | Route endpoint path is `/api/v1/production/character-reid` | Route REQUEST Contract + flags default | 低 — CONTEXT Q3 lock；aigc-platform 路由典型 mount；route 出货后 verify |
| A3 | Default dev port 8000 for character-reid route | flags default | 中 — 路由 DEFERRED 未上线，端口未验证（同 Phase 6 Open Question #1）；文档化"首跑需 verify" |
| A4 | `--reid-timeout` 960s 正确（路由侧 900s execFileSync ceiling） | flags | 低 — 假设 character-reid driver 沿用 shot-analysis 的 900s；route 出货后 verify |
| A5 | Literature three-tier defaults (≥0.85/0.6–0.85/<0.6) are reasonable advisory starting points | DINOv2 Methodology | 中 — 动画域未验证；CONTEXT Q2 已明示 advisory + calibration deferred；不会阻塞 producer-side（tier 字段 authoritative） |
| A6 | DINOv2 ViT-B/14 (768-d) is the route-side embedding model | Route contract + REQUIREMENTS | 极低 — CAST-03 REQUIREMENTS 明列 `facebook/dinov2-base`；producer 不依赖维度（只透传 mean_cosine） |
| A7 | `ROUTE_VERSION = "deferred-character-reid-route-v1"` 是合理初始串 | Pattern 1 | 极低 — cache invalidation 旋钮；route merge 后 bump |
| A8 | httpx 0.28.1 是合法包（slopcheck 无 verify-only 模式，但 pip show + 下游依赖强证据） | Standard Stack / Package Audit | 极低 — Phase 6 已用 + 验证；env 已装；Author=Tom Christie；BSD-3-Clause；9 下游知名包依赖 |

## Open Questions (RESOLVED)

1. **`character-reid` 路由的实际 request/response shape？**
   - What we know: 镜像 shot-analysis THIN-wrapper 模式（CONTEXT Q1 lock）；endpoint `/api/v1/production/character-reid`（CONTEXT Q3）。
   - What's unclear: 精确 body 字段（mask_samples? embedding_model? tau? 是否 per-shot 还是整批？）；response envelope 的 `data.clusters` 是否就是 registry.schema.json#clusters[] shape 还是需要 normalize。
   - Recommendation: call_reid.py **不假设 shape 超过 registry.schema.json 约束**（Pattern 1 显式投影）；route 出货后实测调整 normalize 函数。STATE.md 已记录 deferred blocker。
   - **— RESOLVED: deferred per CONTEXT `<deferred>` + STATE.md blocker; call_reid.py (Plan 07-02 Task 1) implemented as shape-agnostic projector — `normalize_clusters` projects whatever the route emits onto registry.schema.json#clusters[] allowed fields (drops extras via additionalProperties:false). Live shape confirmed post-merge.**

2. **HITL review HTML 是否需要 batch 操作（如"全选 auto_merge confirm"）？**
   - What we know: CONTEXT Q1 lock "cosine-sorted queue surface mid-band first"；auto_merge/auto_distinct 默认行为未明示。
   - What's unclear: 默认是否预选 auto_merge 全 confirm？还是要求人逐个点？
   - Recommendation: Claude's Discretion 范围（CONTEXT 列）；建议 auto_merge 默认预选 confirm（reviewer 可改），auto_distinct 默认预选 confirm 为独立实体，review band 必须人逐个决定。这降低 reviewer 负担且符合"feature not polish"精神。
   - **— RESOLVED: Claude's Discretion lock confirmed; Plan 07-03 Task 2 (`html/gen_registry_review.py`) implements pre-select-confirm for auto_merge (≥0.85) + auto_distinct (<0.6) tiers, and forces explicit human review on the mid-band 0.6–0.85 review tier. `_tier_for` defaults locked in Plan 07-02 Task 1.**

3. **apply_edits.py splits 的新 ID 分配算法？**
   - What we know: CONTEXT Q2 lock "deterministic + idempotent"；新 ID 不可重用已 retired 的（Pitfall 17）。
   - What's unclear: split 一个 char_001 成两个时，新 ID 是 char_001 + char_004（max+1）还是别的？
   - Recommendation: 源 ID 保留（char_001），新分裂出的用 `max_existing_N + 1`（按 cluster_id 数值部分排序）；apply_edits 内部文档化此规则。Pitfall 5 守护。
   - **— RESOLVED: implemented in Plan 07-03 Task 1 `_next_id(prefix, existing_ids)` — extracts numeric suffixes from existing IDs with the same prefix, takes `max_N + 1` (default 0 if none), returns `f"{prefix}_{max_N + 1:03d}"`. Deterministic + idempotent (Pitfall 5 guard). Inline test: `_next_id('char', {'char_001', 'char_003'}) == 'char_004'`.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | 所有 pipeline 脚本 | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `httpx` | call_reid.py 路由调用 | ✓ | 0.28.1 (Phase 6 已用) | 无（核心；缺失则 fail-loud） |
| `jsonschema` | schema 自校验 | ✓ | 4.26.0 (v1.0 基线) | — |
| ffmpeg / ffprobe | representative frame PNG 抽取 + duration probe | ✓ | 6.1.1-3ubuntu5 | — |
| `slopcheck` | Package Legitimacy Audit | ✓ | `/home/kai/.local/bin/slopcheck` | N/A（无 verify-only 模式；用 pip show 替代） |
| `sklearn` / `torch` (route-side) | DINOv2 + AgglomerativeClustering | ✗ | — | **DEFERRED cross-repo** — 不在本仓库（刻意保持；CLAUDE.md "不碰核心算法"） |
| character-reid ROUTE | CAST-01..09 live round-trip | ✗ | — | **DEFERRED to post-merge** — producer-side 用 graceful-degrade + fixture + smoke harness 验证；live E2E 推到 route 出货后 |

**Missing dependencies with no fallback:**
- 无（httpx + jsonschema + ffmpeg 全在 env；route live round-trip 是 STATE.md 已记录的 deferred blocker，不阻塞 Phase 7 coding）。

**Missing dependencies with fallback:**
- 路由不可用 → `--offline` + cache fixtures / `--skip-reid`；live 验证 deferred。
- SAM3 crops 缺席 → producer-side ffmpeg frame extraction fallback（Pattern 4）。

## Validation Architecture

> `workflow.nyquist_validation: true`（config.json 确认）— 本 section REQUIRED。
> **沿用 Phase 6 VALIDATION.md 决策：repo 保持 pytest-free**（CLAUDE.md / v1.0 RETROSPECTIVE："no test framework; standalone `sys.exit(0/1)` scripts"）。assertion engine = inline `python3 -c` checks + standalone `scripts/verify_phase7_smoke.py`（mirror Phase 6 的 `verify_phase6_smoke.py`，Plan 03 落地）+ `scripts/verify_contract.py`（extended）。Planner 应参考 06-VALIDATION.md 的实际策略，不引入 pytest。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | **None** (standalone Python, `sys.exit(0/1)`; inline jsonschema Draft202012Validator) — 沿用 Phase 6 |
| Config file | none（无 pytest.ini / pyproject.toml） |
| Quick run command | `python3 spec/validate.py` (schema regression) + `python3 -c "from registry.apply_edits import apply_edits; ..."` (inline unit) |
| Full suite command | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 scripts/verify_phase7_smoke.py` |
| Estimated runtime | ~5 seconds（Phase 6 ~3s + Phase 7 smoke ~2s） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CAST-05 (draft shape) | `call_reid.py` normalize route response → registry.draft.json schema-valid (Draft202012Validator) | unit (mapping) | inline `python3 -c "from analysis.call_reid import normalize_clusters; ..."` + `python3 spec/validate.py` (v1.1 fixture registry green) | ✅ (fixture: spec/fixtures/v1.1/registry.draft.json) |
| CAST-05 (proposed default) | every cluster in registry.draft.json has `review_state=="proposed"` | unit | inline check on fixture | ✅ |
| CAST-06 (HTML renders) | `gen_registry_review.py` on fixture draft → HTML file written + contains cluster cards + export button | integration | `python3 html/gen_registry_review.py --draft <fixture> --video <tiny> --output /tmp/review.html` + grep "Export edits" | ❌ Wave 0 (script) |
| CAST-07 (confirmed-only) | `apply_edits.py` on draft+edits fixture → characters.json/props.json contain ONLY `review_state:"confirmed"` entries (hard assert) | unit (gate) | `python3 -c "from registry.apply_edits import apply_edits; ..."` + inline assert `all(c['review_state']=='confirmed' for c in chars)` | ❌ Wave 0 |
| CAST-07 (idempotent) | same draft+edits → apply twice → characters.json byte-identical | integration | run apply_edits twice + `diff` | ❌ Wave 0 |
| CAST-07 (appearance_shots ⊆ shots) | every appearance_shots[] in characters.json/props.json exists in shots.json | contract-integrity | `python3 scripts/verify_contract.py --mode=producer` (extended) | ✅ (verify_contract.py exists, extended in Phase 7) |
| CAST-09 (route down degrade) | unreachable URL → registry.draft.json absent + asset exports without characters/props + generator.warnings non-empty | graceful-degrade | `python3 scripts/verify_phase7_smoke.py` (scenario 1) | ❌ Wave 0 (script) |
| CAST-09 (--skip-reid) | `--skip-reid` → step returns None, no subprocess | CLI | `python3 scripts/verify_phase7_smoke.py` (scenario 2) | ❌ Wave 0 |
| CAST-09 (counter [N/8]) | run_pipeline.py has 24 `[N/8]` occurrences (20 renumbered + 4 new step_reid [6/8]) + step_reid in slot 6 | integration | `grep -c "\[N/8\]" run_pipeline.py` + step order check | ❌ Wave 0 |
| CONTRACT-06 (conditional emit) | asset.json with characters.json present → emit data.characters/props; without → omit (byte-identical to v1.0) | contract-conformance | `python3 scripts/verify_phase7_smoke.py` (scenario 1 + 3) | ❌ Wave 0 |
| CONTRACT-06 (media.characters[] pattern) | media.characters[] paths match `^(?!.*\\.\\.)([^/]+/)*characters/[^:*?"<>|]+\\.png$` | schema-validity | `python3 spec/validate.py` (v1.1 asset fixture green) | ✅ |
| registry-edits schema | registry.edits.json fixture validates against registry-edits.schema.json | schema-validity | `python3 spec/validate.py` (extended EIGHT_SHAPES → NINE_SHAPES) | ❌ Wave 0 (schema + fixture) |

### Sampling Rate
- **Per task commit:** `python3 spec/validate.py`（quick < 3s）
- **Per wave merge:** `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer`（full < 10s）
- **Phase gate:** Full suite green + `python3 scripts/verify_phase7_smoke.py` 5 scenarios green + `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer`

### Wave 0 Gaps
- [ ] `spec/schemas/registry-edits.schema.json` — NEW edits round-trip schema
- [ ] `spec/fixtures/v1.1/registry.edits.json` — NEW fixture (edits against existing registry.draft.json fixture)
- [ ] `analysis/call_reid.py` — NEW httpx client + normalize_clusters + per-video cache
- [ ] `registry/apply_edits.py` — NEW draft+edits → canonical confirmed-only gate
- [ ] `html/gen_registry_review.py` — NEW HITL review HTML
- [ ] `scripts/export_asset.py` — MODIFY build_asset_dict (conditional characters/props emission)
- [ ] `scripts/verify_contract.py` — MODIFY _fixture_consistency_check (registry↔shots + confirmed-only assert)
- [ ] `scripts/verify_phase7_smoke.py` — NEW 5-scenario regression (mirror verify_phase6_smoke.py)
- [ ] `run_pipeline.py` — MODIFY +step_reid + 20× `[N/7]`→`[N/8]` + 4 flags + --force cache list
- [ ] `spec/validate.py` — MODIFY EIGHT_SHAPES → NINE_SHAPES (add registry-edits)
- [ ] `README.md` install line — no change (zero new deps; httpx already documented Phase 6)

### Manual-Only Verifications

| Behavior | Why Manual | Instructions |
|----------|------------|--------------|
| Live route round-trip (route reachable, real re-id) | `character-reid` route DEFERRED (STATE.md blocker; mirrors `feat/shot-analysis-route` pre-merge state) — route not running | Post-merge: start kais-aigc-platform backend on the new route branch, run step_reid against ep01, confirm real registry.draft.json lands + review HTML renders real clusters |
| Empirical τ calibration on ep01 | Needs SAM3 character crops that don't exist until route ships (CONTEXT Q2) | Post-merge: follow §DINOv2 Re-ID Methodology → "Deferred τ calibration protocol" (same-person vs different-person cosine histogram, valley pick), update registry.schema.json `$comment` |
| HITL review UX pilot | Visual review HTML is a first-class deliverable; automated check can verify presence of cards/buttons but not usability | Open review HTML in browser against ep01 fixture; confirm cluster cards readable, merge/split/rename intuitive, export produces valid registry.edits.json |

## Security Domain

> `security_enforcement` 未在 config.json 显式 false（absent = enabled）— 本 section REQUIRED。
> Phase 7 安全面与 Phase 6 同构（本地 CLI、调本地/DEFERRED 路由、无多用户、无 PII），加代表性 PNG 抽取的文件路径安全。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 路由无认证（local dev）；不引入凭据 |
| V3 Session Management | no | 无 session 概念 |
| V4 Access Control | no | 单用户 CLI |
| V5 Input Validation | yes | `registry-edits.schema.json` Draft202012Validator 校验 edits；`registry.schema.json`/`characters`/`props` schema 校验 producer 输出；`--reid-url` httpx `InvalidURL` 自然抛 |
| V6 Cryptography | no | 无 crypto 操作（sha256 cache key 是 fingerprint，非安全 hash） |
| V7 Error Handling | yes | graceful-degrade（route-down → schema-valid absent + warning）；apply_edits hard-gate confirmed-only（Pitfall 7）；per-video 失败非致命 |
| V8 Data Protection | no | 无敏感数据落地（registry/clusters 是视觉分析，无 PII）；`_safe_error` 抹 URL userinfo 防 auth token 流进 warnings（Phase 6 WR-05 复用） |
| V9 Communications | yes | localhost HTTP（生产可 HTTPS）；httpx `verify=True` 默认开 SSL |
| V12 Files & Resources | yes | PNG 路径由 cluster_id 派生（schema anti-traversal pattern `^(?!.*\\.\\.)([^/]+/)*characters/[^:*?"<>|]+\\.png$` 拒 `../`/绝对路径/Windows 保留字符）；`--force` rmtree 仅限已知 `route_cache/` + work_dir 内 registry 文件 |

### Known Threat Patterns for httpx → DEFERRED route + ffmpeg PNG extraction stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 路由 SSRF（`--reid-url` 用户输入当 URL） | Tampering | CLI flag 非运行时用户输入；httpx `base_url` 校验；同 Phase 6 |
| PNG path traversal（malicious cluster_id 注入 `../`） | Tampering / Path Traversal | registry.schema.json `cluster_id` pattern `^(char\|prop)_[0-9]{3}$` 拒任意字符；characters.schema.json `representative_image` pattern anti-traversal；apply_edits 不从外部输入取路径，只从 schema-validated cluster_id 派生 |
| Cache poisoning（篡改 route_cache/character_reid/） | Tampering | 本地 filesystem trust boundary；`_cache_key` 防版本串；不签名（YAGNI） |
| Proposed leaking downstream（Pitfall 7） | Tampering / Integrity | apply_edits.py build-time hard gate；verify_contract.py assert；smoke harness scenario 4 |
| `--video` 路径注入 route body | Information Disclosure | CLI arg 非外部输入；同 Phase 6 |
| ffmpeg 抽帧 timeout / hang | Denial of Service | `subprocess.run(..., timeout=10)`（gen_timeline_html.py:979 已用）；失败 → 空 PNG（schema-conditional，asset 仍导出） |

## Sources

### Primary (HIGH confidence)
- **本 repo 源码（DIRECT anchors）**:
  - `analysis/call_shot_analysis.py` (425 行) — DIRECT template for `call_reid.py`（httpx + cache + preflight + graceful-degrade + `_safe_error` URL scrub + normalize pattern 全在）。
  - `run_pipeline.py:153-222` (`step_semantic`) — DIRECT template for `step_reid`；`run_pipeline.py:416-433` (`--force` cache list) — Phase 7 扩展点；`run_pipeline.py:364-394` (argparse) — 4-flag wiring 模式。
  - `scripts/export_asset.py:135-208` (`build_asset_dict`) — Phase 7 条件 emission 扩展点；`scripts/export_asset.py:340-343` (pre-write stems assert) — characters/props PNG assert 模板。
  - `scripts/verify_contract.py:204-271` (`validate_eight_shapes`) + `:388-488` (`_fixture_consistency_check`) — Phase 7 registry↔shots integrity 扩展点（已含部分 registry checks）。
  - `scripts/verify_phase6_smoke.py` — DIRECT template for `verify_phase7_smoke.py`（4-scenario → 5-scenario）。
  - `html/gen_timeline_html.py:99-260` (palette + monolithic HTML pattern) — `gen_registry_review.py` 复用 GitHub-dark tokens + f-string template 模式。
  - `html/gen_shots_preview.py:24-39` (`extract_frame_b64` ffmpeg pattern) — apply_edits.py representative PNG 抽取模板。
  - `run_pipeline.py` 全文 grep：20 处 `[N/7]`（mirror Phase 6 的 17 处 `[N/6]` renumber）。
- **Phase 5 已 SHIPPED contract layer（frozen target shapes）**:
  - `spec/schemas/registry.schema.json` — clusters[] shape + tier enum + $comment 三档阈值约定（advisory）。
  - `spec/schemas/characters.schema.json` + `props.schema.json` — canonical confirmed-only shape + anti-traversal PNG pattern + ID immutability。
  - `spec/schemas/asset.schema.json:94-103` (data.characters/props) + `:140-155` (media.characters[]/props[]) — Phase 7 CONDITIONAL emission 的 schema 已就位（Phase 5 加，Phase 7 wire）。
  - `spec/fixtures/v1.1/registry.draft.json` + `characters.json` + `asset.json` — Phase 5 fixture set 是 producer 产物的 frozen 参照（registry.draft 含 3 clusters、characters 含 2 confirmed、asset 含 data.characters/props + media.characters[]/props[]）。
- **Phase 6 RESEARCH + VALIDATION（DIRECT analog）**: `.planning/phases/06-.../06-RESEARCH.md` + `06-VALIDATION.md` — httpx 0.28.1 API、graceful-degrade 模式、smoke harness 4-scenario shape、pytest-free 决策全继承。
- **httpx 0.28.1 in-env introspection**: `pip show httpx` → Author=Tom Christie, BSD-3-Clause, Required-by diffusers/gradio_client/hermes-agent/huggingface_hub/mcp/openai/python-telegram-bot/weasel。
- **kais-aigc-platform 路由源码（DEFERRED route 的 analog）**: `git -C /data/workspace/kais-aigc-platform show feat/shot-analysis-route:src/routes/production/shot-analysis/index.ts` + `scripts/shot-analysis/shot_analysis_driver.py` + `_shared/config.ts` — THIN-wrapper pattern（Zod body + docker cp + execFileSync 900s + `{code,data,message}` envelope + driver 落盘 shot_XXX.json）；character-reid 会镜像。
- **DEFERRED route 不存在验证**: `ls /data/workspace/kais-aigc-platform/src/routes/production/` → 有 `shot-analysis` 但无 `character-reid`；`git branch -a` → 有 `feat/shot-analysis-route` 但无 `feat/character-reid*`。

### Secondary (MEDIUM confidence)
- **scikit-learn AgglomerativeClustering v1.9 official docs** (fetched 2026-07-25 via firecrawl) — `metric` 参数（非 deprecated `affinity`）、`linkage="average"` 与 `metric="cosine"` 兼容、`distance_threshold` 语义（"at or above which clusters will not be merged"，需 `n_clusters=None`+`compute_full_tree=True`）。
- **DINOv2 paper** (arxiv.org/abs/2304.07193, Meta AI 2023) — self-supervised ViT、image retrieval via cosine similarity、ViT-B/14 768-d features。
- **Unsupervised re-id clustering literature**: Fan et al. 2017 (arxiv.org/abs/1705.10444, 893 citations) + Hu et al. 2021 threshold-based hierarchical clustering (pmc.ncbi.nlm.nih.gov/articles/PMC8145342/, Market-1501 mAP=68.8%) — 锚定 SOTA 60-80% mAP 范围 + 三档阈值 advisory 合理性。

### Tertiary (LOW confidence — marked for validation)
- **DINOv2-specific published threshold 0.85 NOT FOUND** — WebSearch 无论文用 DINOv2 ViT-B/14 + 0.85 re-id threshold；值是 application-specific（dataset/pooling/normalization 依赖）—— 这正是 CONTEXT Q2 defer calibration 的原因。
- **character-reid route 实际 shape** — route DEFERRED，REQUEST/RESPONSE 是基于 shot-analysis analog 推断；call_reid.py 设计为显式投影（不假设 shape 超过 schema）。
- **aigc-platform dev port 8000** — 同 Phase 6 Open Question #1；route unmerged 无法验证。

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — httpx 0.28.1 Phase 6 已装 + 验证 + 用；jsonschema v1.0 基线；ffmpeg 6.1.1 env；零新依赖（sklearn/torch 刻意不在 env）。
- Contract layer: **HIGH** — Phase 5 已 SHIPPED registry/characters/props/asset schemas + v1.1 fixture set；本 phase 是纯 producer 实现 + 一个新 schema（registry-edits）。
- Architecture (run_pipeline 整合): **HIGH** — step_semantic 是 DIRECT template；插入点 + 20 处 renumber 已 grep 定位；Pattern proven。
- HITL HTML: **HIGH** — gen_timeline_html palette + monolithic pattern 已证；gen_shots_preview ffmpeg-base64 已证；UX 是 Claude's Discretion。
- apply_edits.py (confirmed-only gate): **HIGH** — schema $comment 明列 Pitfall 7 gating；hard-gate pattern 清晰；idempotency 算法明确。
- Conditional emission: **HIGH** — asset.schema.json 已支持 optional characters/props；build_asset_dict 扩展点清晰；byte-identical 保证（条件式）。
- Cross-file integrity: **HIGH** — verify_contract.py `_fixture_consistency_check` 已含部分 registry checks；扩展点 additive。
- DINOv2 τ defaults: **MEDIUM** — 文献 anchoring 强（SOTA 60-80% mAP + τ 0.3-0.7 range）但动画域未验证；CONTEXT Q2 明示 advisory + calibration deferred；不阻塞 producer。
- Pitfalls: **HIGH** — 9 个 pitfall 全 anchored 在 schema $comment / 现有源码 / Phase 6 lessons / 文献。

**Research date:** 2026-07-25
**Valid until:** 2026-08-25（30 天；route 分支 merge 后 ROUTE_VERSION / endpoint shape / τ defaults 需复核）

## RESEARCH COMPLETE
