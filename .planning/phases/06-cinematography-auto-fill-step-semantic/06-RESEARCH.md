# Phase 6: Cinematography Auto-Fill (`step_semantic`) - Research

**Researched:** 2026-07-24
**Domain:** 网络依赖的 pipeline 扩展（httpx sync client → kais-aigc-platform `POST /api/v1/production/shot-analysis` → `prompts.json` facet 映射）+ per-shot 缓存 + graceful-degrade
**Confidence:** HIGH（路由 REQUEST contract 直接从 `feat/shot-analysis-route` 分支 `git show` 取得；映射函数对全部 7 个真实 captured 输出验证 0 schema 错误；httpx 0.28.1 API 通过 in-env 内省确认）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions（不可重开）

**Route→prompts field mapping (CINEMA-01)** — 真实路由输出 `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` 含 `geometry` + `semantic`。映射到 prompts facets：
- `camera` ← COMPOSE from `semantic.shot_scale` + `semantic.camera_primitive` + `semantic.camera_speed` + `geometry.primitive`（如 `"中景, follow, fast pan_right"`）。四个都带相机语言信号。
- `action` ← `semantic.subject_motion`（如 `"飞虫持刀向前飞行"`）。
- `lighting` ← `semantic.lighting`（如 `"雾气弥漫"`）。
- `style` ← `semantic.lens_feel`（如 `"normal"`）。
- `subject` ← empty string `""`（路由无 subject/identity 源 — 不要伪造；Phase 7 re-id + Phase 8 refs 处理身份）。
- `scene` ← empty string `""`（路由无 scene 源；未来 Qwen-VL 扩展；永不伪造）。
- `prompt_text` ← 不在此重组（Phase 8 PROMPT-02 owns narrative recomposition with registry refs）。
- 映射已对真实 `shot_003.json` 样本验证（offline — 无需 live route）。

**step counter numbering (CINEMA-02)** — Phase 6 起 post-Phase-6 步骤编号 **`[N/7]`**：codec[1] / detect[2] / separate[3] / transcribe[4] / **semantic[5]** / timeline[6] / export[7]。**No phantom gap** — Phase 7 再升 `[N/8]`（在位置 6 插 `step_reid`）。CINEMA-02 字面的 "[N/8]" 推迟到 Phase 7 以避免当前的缺步号。

**video_content_hash for cache key (CINEMA-04)** — sha256 of first 1MB + last 1MB + file size (`hashlib.sha256(head_1MB + tail_1MB + str(size).encode())`)。快（避免全读 multi-GB episode 视频）、确定性、collision-resistant 足够做缓存失效。Cache key tuple = `(video_content_hash, shot_id, route_name, route_version)`。Cache dir：`output/<asset>/route_cache/shot_analysis/shot_XXX.json`。

**Graceful-degrade + merge semantics (CINEMA-03)**：
- Route down（`--offline` 或不可达）→ 所有路由源 facets 写为 **空串 `""`**（schema 合法 — prompts.schema facets 是 `type:string` 无 `minLength`）；asset 仍导出；`generator.warnings` 记失败原因。
- `step_semantic` 是首个真正的 prompt generator（CONTEXT：shot-timeline 现今没有；`prompts/merge_prompts.py` 只合并外部 `part_*.json`）。step_semantic 从路由 facets 写 `prompts.json`。若 `part_*.json` 内容存在，**route wins** for the 5 route-sourced fields（camera/action/lighting/style/scene）— 路由可用时为权威。`prompt_text`/`subject` 若已存在则保持不动。

**Preflight + flags (CINEMA-05/06)**：
- 步前 preflight health check（GET 或 HEAD on the route base）；per-shot 失败 **非致命**（不阻断 asset export — 一个坏 shot 不沉整资产）。
- `--analysis-url`（默认 `http://127.0.0.1:<port>/api/v1/production/shot-analysis`）、`--analysis-timeout`（默认 **960s**，> 路由侧 900s `execFileSync` 上限）、`--offline`（全局；cache-only，无网络）、`--skip-semantic`（整步跳过）。

### Claude's Discretion

- Warning 消息的具体措辞；`analysis/call_shot_analysis.py` 内 helper 函数组织（mapping 函数、httpx call、cache read/write、preflight）。
- `--offline` 是否蕴含 `--skip-semantic` 语义或仍读缓存（**推荐**：`--offline` 读缓存，仅压制网络；`--skip-semantic` 整步跳过）。

### Deferred Ideas（OUT OF SCOPE）

- **Live route round-trip E2E** — 推迟到 kais-aigc-platform `feat/shot-analysis-route` + `feat/shot-geometry-nodes` merge（STATE.md blocker）。映射已对 captured 输出验证；graceful-degrade 已对 route-down 验证。Live round-trip 变 post-merge smoke test。
- **`scene` field from Qwen-VL** — 未来扩展（路由现今无 scene 源）；留空，永不伪造。
- **`prompt_text` recomposition** — Phase 8（PROMPT-02）owns narrative recomposition with registry refs；Phase 6 仅填 5 个 facets。
- **step_reid + `[N/8]` counter bump** — Phase 7。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **CINEMA-01** | `analysis/call_shot_analysis.py` — httpx 客户端调 `POST /api/v1/production/shot-analysis`，把 `semantic.*`/`geometry.*`/`subject.*` 映射到 prompts 的 `camera`/`action`/`lighting`/`style`/`subject` 字段 | **Route REQUEST body 已从 `feat/shot-analysis-route:src/routes/production/shot-analysis/index.ts` 取得**（见 Architecture Patterns §"Route REQUEST Contract"）；映射函数已对全部 7 个 captured fixtures 验证 0 schema 错误（见 Validation Architecture）；httpx 0.28.1 sync API 通过 in-env 内省确认；**`subject.*` 映射按 CONTEXT 决策为空串（路由 SAM3 层不提供身份）**。 |
| **CINEMA-02** | `run_pipeline.py` 新增 `step_semantic`（位于 `step_transcribe` 与 `step_timeline` 之间），`[N/8]` 计数全量更新 | step counter 按 CONTEXT 锁定为 `[N/7]`（非 `[N/8]`），推迟 Phase 7 bump。插入点已定位（line 348 后、line 350 前）；6 处 `[N/6]` 出现点列在 Architecture Patterns §"run_pipeline.py Integration"。 |
| **CINEMA-03** | 路由不可达时 graceful-degrade — `prompts.json` 仍写出（空 facet 字段、schema 合法），资产仍导出；`--skip-semantic` 旗标 | 6 facets 在 prompts.schema 都是 `type:string` 无 `minLength`，空串合法（已 schema 验证）；httpx `HTTPError` 捕获涵盖所有 transport/timeout/status 错误；`prompts/merge_prompts.py` 已用 `p.get(fld, "")` 模式，step_semantic 复用。 |
| **CINEMA-04** | 每镜路由输出缓存 `output/<asset>/route_cache/shot_analysis/shot_XXX.json`，cache key 含 `(video_content_hash, shot_id, route_name, route_version)`；`--offline` 全局旗标只用缓存不联网 | 路由原生支持 `shot_id_range: [N, N]` 做 per-shot 调用（见 REQUEST contract）；每 shot 返回的 `data.shots[0]` 直接落盘即缓存文件；`--offline` 设计：cache 命中即用、cache miss 跳过该 shot（不联网）。 |
| **CINEMA-05** | 步前 preflight 健康检查 + 失败时 `generator.warnings` 记录（per-shot 失败不致命，不阻断资产导出） | **`asset.schema.json#generator` 当前是 `additionalProperties:false` + 只有 `tool/version/generated_at`，无 `warnings` 字段 — Phase 6 必须做小额 schema 扩展**（见 Architecture Patterns §"Schema Delta vs Phase 5"）；preflight 设计：捕获 `httpx.ConnectError` 即标"route down"，余下 shots 不再重试网络。 |
| **CINEMA-06** | `--analysis-url` / `--analysis-timeout`（默认 960s，> 路由侧 900s `execFileSync` 上限）旗标 | 路由 `execFileSync` timeout=900_000ms 已在 `index.ts` 确认；客户端 read timeout 960s 故意超出 60s 让路由先自杀完毕；httpx `Timeout(connect=5.0, read=960.0, write=5.0, pool=5.0)` 配置模式见 Code Examples。 |
</phase_requirements>

## Summary

Phase 6 给 shot-timeline 引入**首个网络依赖**：新 `step_semantic` pipeline 阶段通过一个 thin httpx sync client 调用 kais-aigc-platform 的 `POST /api/v1/production/shot-analysis` 路由，把逐镜头运镜分析合并进 `prompts.json` 的 `camera`/`action`/`lighting`/`style` facets（`subject`/`scene` 按决策留空，永不伪造）。Mandatory graceful-degrade 保证路由不可达时 `prompts.json` 仍写 schema-legal 的空 facet 字符串、asset 仍导出、`generator.warnings` 记失败原因。每镜路由输出用 `(video_content_hash, shot_id, route_name, route_version)` 四元组 key 在 `route_cache/shot_analysis/shot_XXX.json` 缓存；`--offline` 仅读缓存不联网，`--skip-semantic` 整步跳过。

**Primary recommendation:** 写一个 ~150-200 LOC 的 `analysis/call_shot_analysis.py`（httpx sync client + 映射函数 + per-shot cache + preflight）作为自包含 CLI 脚本（沿用项目 stage pattern），从 `run_pipeline.py:main()` 在 `step_transcribe` 与 `step_timeline` 之间以 subprocess 调用。**call body 必须传 `semantic: true`**（否则 `semantic.*` 字段不填，映射失效）；**不传 `subject: true`**（Phase 6 不用 SAM3 层）。**`generator.warnings` 要求一个小额 schema 扩展**（Phase 5 没加），仍是纯增量、不破坏 `1.1` minor bump 语义。

**最关键的研究发现**：(1) 路由 REQUEST body 已直接从 `feat/shot-analysis-route` 分支提取，是 `{video, shots, shot_id_range?, semantic?, subject?, grid_n?, fps?}`，其中 `video`/`shots` 是宿主机路径（路由自行 `docker cp` 进 ComfyUI 容器），`shot_id_range: [N, N]` 是 per-shot 调用模式；(2) 映射函数对 7 个真实 captured 输出全部 0 schema 错误（已用 `Draft202012Validator` 实测），含 null/空串边界（shot_002 shot_scale=null、shot_005 subject_motion=""、shot_007 subject_motion=null）；(3) httpx 0.28.1 已在环境安装、API 直接内省确认、BSD-3-Clause、众多下游依赖（openai/diffusers/huggingface_hub/mcp 等）— legitimacy HIGH，但 slopcheck 因网络不可达标 `[ASSUMED]`。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP route 调用（POST shot-analysis） | API client (in-process, shot-timeline side) | External route (kais-aigc-platform) | shot-timeline 是 thin 外部生产者；ML 推理在路由侧 ComfyUI 容器；客户端仅负责组 body / 发请求 / 收 response。 |
| 路由 → prompts facet 映射 | Pipeline stage (analysis/) | — | 纯字段重组；无 ML；确定性函数；测试用 fixture 即可。 |
| Per-shot 缓存读写 | Filesystem (output/<asset>/route_cache/) | — | 沿用项目"idempotent cache on file-existence"惯例；cache key 含 video_content_hash + route_version 防陈旧。 |
| video_content_hash 计算 | Pipeline stage (analysis/) | — | sha256 of first/last 1MB + size；避免全读 multi-GB 视频。 |
| `prompts.json` 写入 | Pipeline stage (analysis/) | merge_prompts.py（外部工具，现今未接入 run_pipeline） | step_semantic 是 run_pipeline 内首个真正 prompts producer。 |
| `generator.warnings` 通道 | Exporter (scripts/export_asset.py) | Schema (asset.schema.json) | warnings 经 exporter 写入 asset.json#generator；schema 需新增 optional `warnings: array<string>`。 |
| Preflight health check | Pipeline stage (analysis/) | — | 步前发一次短超时探测；失败即标"route down"，全步骤降级。 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` [VERIFIED: env + pip show + in-env introspection] | 0.28.1 | sync HTTP client 调用 shot-analysis 路由 | 已在 env（`/home/kai/.local/lib/python3.12/site-packages`）；`pip show` Author=Tom Christie（Django REST framework 作者）；众多下游依赖（diffusers/openai/mcp/huggingface_hub）；BSD-3-Clause；sync `Client.post(json=...)` API 直接服务单线程 pipeline。 |
| `jsonschema` | 4.26.0 | inline `Draft202012Validator` 自校验产出 prompts.json | v1.0 已用；Phase 5 extend 时复用；本 phase 仅校验，不改 schema 工具。 |
| Python stdlib `hashlib` / `json` / `pathlib` / `argparse` / `subprocess` | stdlib | cache key / JSON I/O / CLI / 调用 | 项目惯例 — 零新依赖；CLAUDE.md "stdlib-first"。 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsonschema.Draft202012Validator` | 4.26.0 | 本地 prompts.json 自校验（写前 assert） | 产 prompts.json 后立即 `iter_errors`；有错 sys.exit 非 0（fails loud 惯例）。 |
| `httpx.Timeout` | 0.28.1 | 分离 connect/read/write/pool 超时 | `Timeout(connect=5.0, read=960.0, write=5.0, pool=5.0)` — read 960s 故意 > 路由 900s `execFileSync` ceiling。 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx` sync Client | `urllib.request`（路由 driver 用的） | urllib 无 connection pool、无分粒度 timeout、无 first-class exception 层级；route 调用 long-running（≤900s）需 pool/read 超时分离 → httpx 更合适。 |
| `httpx` sync Client | `requests` | requests 仍维护但 httpx 是同一作者下一代、HTTP/2-ready、更清晰的 exception 层级；env 里 httpx 已装、requests 可能没装。 |
| `tenacity`/`stamina`（retry） | 手写或 skip retry | per-shot 失败非致命（CONTEXT 决策），retry 是 YAGNI；planner 不引入。 |

**Installation:**
```bash
# httpx 0.28.1 ALREADY installed — no install needed for Phase 6
pip show httpx   # 验证：Version: 0.28.1, Location: /home/kai/.local/lib/python3.12/site-packages
# 若新环境复刻：
pip install "httpx==0.28.1"
```

**Version verification (executed during research):**
- `pip index versions httpx` → `Available versions: 0.28.1, 0.28.0, ... ; INSTALLED: 0.28.1`
- `python3 -c "import httpx; print(httpx.__version__)"` → `0.28.1`
- `pip show httpx` → Author-email: Tom Christie, License: BSD-3-Clause, Required-by: diffusers, gradio_client, hermes-agent, huggingface_hub, mcp, openai, python-telegram-bot, weasel

## Package Legitimacy Audit

> slopcheck ran but PyPI registry unreachable in sandbox (`IncompleteRead`）；按 Protocol graceful-degradation：所有包标 `[ASSUMED]`，planner 应在每个 install 前加 `checkpoint:human-verify`。本 phase 唯一包 `httpx` 已在 env 安装、版本/作者/下游依赖/API 均直接验证 — 实际 risk LOW。

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `httpx` | PyPI | ~6 yrs (0.28.1 当前) | 顶层包（被 openai/diffusers/mcp/huggingface_hub 依赖） | github.com/encode/httpx | `[ERR] registry unreachable` → treat as `[ASSUMED]` | Approved — 但 planner 加 `checkpoint:human-verify`（protocol 要求；实际 risk LOW：已装、已内省、Author=Tomm Christie、下游依赖众多） |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Note（cross-ecosystem 命名陷阱）：** npm registry 上也有一个无关的 `httpx` 包（v3.0.1，JavaScript）。本 phase 用的是 **PyPI 的 Python `httpx`**。`npm view httpx version` 不应用于本 phase 校验（CLAUDE.md：project 是 Python，无 node 依赖）。

## Architecture Patterns

### Route REQUEST Contract（THE #1 DELIVERABLE）

直接 `git -C /data/workspace/kais-aigc-platform show feat/shot-analysis-route:src/routes/production/shot-analysis/index.ts` 读取，未 checkout 分支（repo 当前在 `feat/flowgraph-v3-canvas`，未扰动）。

**Endpoint:** `POST /api/v1/production/shot-analysis`

**Request body**（Zod `bodySchema` 校验，`index.ts:25-33`）：
```typescript
{
  video:           string,            // REQUIRED, min 1 char. Host path.
                                      // 路由自行判断：若非 /root/ComfyUI/* 或 /mnt/agents/* 开头，
                                      // execFileSync("docker", ["cp", video, "comfyui-primary:/root/ComfyUI/input/<basename>"])
                                      // 否则原样透传（视为容器挂载可见）。
  shots:           string,            // REQUIRED, min 1 char. Host path to shots.json.
  shot_id_range?:  [int, int],        // OPTIONAL. 元组 [LO, HI] 过滤处理哪些 shot id。
                                      // Phase 6 per-shot 模式：传 [N, N] 即只处理单个 shot。
  semantic?:       boolean,           // OPTIONAL, default false. 开启 QwenVL 语义层。
                                      // **Phase 6 MUST pass `true`** — 否则 semantic.* 不填，映射失效。
  subject?:        boolean,           // OPTIONAL, default false. 开启 SAM3 主体层。
                                      // **Phase 6 pass `false`** — CONTEXT 决策不用 subject.* 字段。
  grid_n?:         int,               // OPTIONAL, 1-200, default 20. 几何分析网格密度。
  fps?:            number,            // OPTIONAL, 1-120, default 24. 帧率。
}
```

**Response envelope**（`@/lib/responseFormat.ts:success(data, message)`，`index.ts:140-152`）：
```json
{
  "code": 200,
  "data": {
    "shots":      [<shot_003.json 内容>, ...],   // 数组，每元素 = 一份 driver 落盘的 shot_XXX.json
    "count":      N,
    "outputDir":  "/mnt/agents/output/gpu1/shot_analysis",
    "driverStdout": "..."                         // driver 末尾 2000 字符
  },
  "message": "Shot analysis complete"
}
```

**HTTP status code**（`index.ts:75, 89, 107, 116, 132, 134`）：
- 200 = 成功
- 400 = Zod `VALIDATION_ERROR`（body schema 不过）
- 500 = `SHOT_ANALYSIS_STAGING_FAILED`（docker cp 失败）/ `SHOT_ANALYSIS_DRIVER_FAILED`（driver 非零退出）/ `SHOT_ANALYSIS_OUTPUT_UNREADABLE`（outputDir 读不出）

**Route-side timeout（关键约束）：** `execFileSync(argv[0], argv.slice(1), { timeout: 900_000, maxBuffer: 16*1024*1024 })`（`index.ts:101-106`）— 路由自己 900s 杀 driver。客户端 read timeout 必须 > 900s（CONTEXT 默认 960s 正确）。

**Per-shot 调用模式（推荐）：** 客户端循环每 shot：
```python
for shot in shots:
    body = {
        "video": video_host_path,           # 宿主机绝对路径
        "shots": shots_json_host_path,      # 宿主机绝对路径
        "shot_id_range": [shot_id, shot_id],
        "semantic": True,                   # MUST
        "subject": False,                   # Phase 6 不用
        "grid_n": 20,
        "fps": 24,
    }
    resp = client.post("/api/v1/production/shot-analysis", json=body)
```
路由会过滤 driver 只处理该 shot，返回 `data.shots` 数组里只有 1 个元素，可直接写 `route_cache/shot_analysis/shot_XXX.json`。

**Route outputDir 共享：** 路由把所有输出写到固定 `/mnt/agents/output/gpu1/shot_analysis/shot_XXX.json`。多次 per-shot 调用会覆写各自的 `shot_XXX.json`（互不冲突），但**这是路由侧的共享目录，不是 shot-timeline 的 cache dir**。shot-timeline 自己的 cache 在 `output/<asset>/route_cache/shot_analysis/`。

### System Architecture Diagram

```
                   ┌── shots.json ──┐
                   │                 │
                   ▼                 │
   ┌─────────────────────────┐       │
   │ run_pipeline.py:main()  │       │
   │  [1] codec              │       │
   │  [2] detect → shots.json│───────┘
   │  [3] separate           │
   │  [4] transcribe         │
   │  [5] step_semantic ◄─────── NEW (this phase)
   │       │                │
   │       │ subprocess     │
   │       ▼                │
   │  ┌────────────────────────────────┐
   │  │ analysis/call_shot_analysis.py│
   │  │  1. compute video_content_hash│
   │  │  2. preflight health probe ───┼──┐
   │  │  3. for shot in shots.json:   │  │ (if route up)
   │  │     - cache hit? skip network │  │
   │  │     - else POST /shot-analysis│  │
   │  │       with shot_id_range=[N,N]│  │
   │  │     - map response → facets   │  │
   │  │     - write cache file        │  │
   │  │  4. assemble prompts.json     │  │
   │  │  5. write warnings sidecar    │  │
   │  └────────────────────────────────┘  │
   │       │ prompts.json                │
   │       ▼                             │
   │  [6] timeline (reads prompts)       │
   │  [7] export (reads prompts + warnings sidecar)
   └─────────────────────────┘           │
                                          ▼
                            ┌─────────────────────────┐
                            │ kais-aigc-platform      │
                            │ POST /api/v1/production/│
                            │      shot-analysis      │
                            │  (feat/shot-analysis-   │
                            │   route — UNMERGED)     │
                            │  1. zod validate body   │
                            │  2. docker cp video     │
                            │  3. execFileSync driver │
                            │     (900s ceiling)      │
                            │  4. aggregate shot_*.json│
                            │  5. return {data,code}  │
                            └─────────────────────────┘

  ── on route down / --offline ──
  step_semantic writes prompts.json with empty-string facets (schema-valid)
  + warnings sidecar → asset still exports with generator.warnings populated
```

### Recommended Project Structure（Phase 6 增量）

```
analysis/                                  # NEW directory (Phase 6 创建)
├── __init__.py                            # 空（Python package marker；项目首个 package 化目录）
└── call_shot_analysis.py                   # httpx client + 映射 + cache + preflight (NEW)
output/<asset>/                            # 运行时产物
├── prompts.json                           # NEW producer: step_semantic（若 part_*.json 存在则 merge）
├── route_cache/                           # NEW
│   ├── warnings.json                      # 失败原因列表（export_asset 读）
│   └── shot_analysis/                     # route_name 子目录
│       └── shot_XXX.json                  # per-shot cached route response
└── asset.json                             # 写时含 generator.warnings（schema 扩展后）
run_pipeline.py                            # +step_semantic +4 flags +[N/7] counter
scripts/export_asset.py                    # +warnings 参数透传
spec/schemas/asset.schema.json             # +generator.warnings (optional array<string>)
spec/SPEC.md                               # +generator.warnings 行进 §3 表
```

### Schema Delta vs Phase 5（重要：Phase 5 未加 warnings）

Phase 5 VERIFICATION 已确认 `asset.schema.json#generator.required == [tool, version, generated_at]` 且 `additionalProperties: false`，**`warnings` 字段不存在**。Phase 6 需做纯增量扩展：

```jsonc
// spec/schemas/asset.schema.json — generator object
"generator": {
  "type": "object",
  "additionalProperties": false,
  "required": ["tool", "version", "generated_at"],   // 不变
  "properties": {
    "tool":        { /* 不变 */ },
    "version":     { /* 不变 */ },
    "generated_at":{ /* 不变 */ },
    "warnings": {                                      // NEW (Phase 6)
      "type": "array",
      "items": { "type": "string" },
      "description": "v1.1 additive (OPTIONAL). Non-fatal warnings encountered during asset generation (e.g. cinematography route unreachable → empty prompts facets). Older assets omit it and still validate (graceful-degrade)."
    }
  }
}
```

- 仍是 minor-bump 兼容：optional 字段、不改 required、不改现有字段语义、`additionalProperties:false` 保留。
- **不需要 bump schema_version past "1.1"**（仍是纯增量）。
- 必须 sync 更新：`scripts/verify_contract.py` 的 v1.1 fixture `asset.json`（加 `"warnings": [...]` 演示）+ `spec/SPEC.md` §3 generator 表加 warnings 行 + `spec/fixtures/v1.1/asset.json`（可选：加 warnings 字段）。
- `scripts/export_asset.py:build_asset_dict` 当前签名 `build_asset_dict(work_dir, video)` → 扩展为 `build_asset_dict(work_dir, video, warnings=None)`，非空时 emit `"warnings": warnings`。

### run_pipeline.py Integration

**Step counter `[N/6]` → `[N/7]` 全量更新点**（直接 grep 出的 18 处）：

| File:line | 当前 | Phase 6 后 |
|-----------|------|-----------|
| `run_pipeline.py:68` | `[1/6] codec={codec}, no transcode needed` | `[1/7]` |
| `run_pipeline.py:72` | `[1/6] cached H264: {out}` | `[1/7]` |
| `run_pipeline.py:74` | `[1/6] transcoding AV1 → H264` | `[1/7]` |
| `run_pipeline.py:92,95,102` | `[2/6] ... scene detection` | `[2/7]` |
| `run_pipeline.py:110,113,121` | `[3/6] ... Demucs` | `[3/7]` |
| `run_pipeline.py:130,133,140` | `[4/6] ... Whisper` | `[4/7]` |
| `run_pipeline.py:152,170` | `[5/6] ... timeline HTML` | `[6/7]`（让位给新 step 5） |
| `run_pipeline.py:217,249,258` | `[6/6] ... asset export` | `[7/7]` |

**新 `step_semantic` 插入：** 当前 `run_pipeline.py:348` 是 step_transcribe 调用结束，line 350 是 `# 5. 时间轴 HTML`。在两者之间插入：

```python
# 5. 语义填充（运镜分析路由）—— 首个网络依赖步骤
prompts_json = os.path.join(work_dir, "prompts.json")
prompts = step_semantic(video, work_dir, shots, prompts_json,
                        args.skip_semantic, args.offline,
                        args.analysis_url, args.analysis_timeout)
```

**新 `step_semantic` 函数签名（mirror `step_transcribe`）**：
```python
def step_semantic(video: str, work_dir: str, shots_json: str,
                  prompts_json: str, skip: bool, offline: bool,
                  analysis_url: str, analysis_timeout: float) -> str:
    if skip:
        print("[5/7] --skip-semantic: skipping cinematography analysis")
        return prompts_json if os.path.exists(prompts_json) else None
    # prompts.json 已存在且新于 shots.json → cache 命中
    if (not offline and os.path.exists(prompts_json)
            and _safe_mtime(prompts_json) > _safe_mtime(shots_json)):
        print(f"[5/7] cached prompts: {prompts_json}")
        return prompts_json
    cmd = [sys.executable, str(HERE / "analysis" / "call_shot_analysis.py"),
           "--video", video, "--shots", shots_json,
           "--work-dir", work_dir, "--output", prompts_json,
           "--analysis-url", analysis_url,
           "--analysis-timeout", str(analysis_timeout)]
    if offline:
        cmd += ["--offline"]
    run_step(cmd, "[5/7] cinematography analysis (shot-analysis route)")
    return prompts_json
```

**`--force` cache 清单（`run_pipeline.py:326-327`）必须扩：**
```python
for p in (shots_json, frames_json, audio_json, transcript, out_html,
          asset_json, asset_json + ".video-stamp",
          prompts_json,                                      # NEW
          os.path.join(work_dir, "route_cache")):            # NEW — 整个 route_cache dir
    if os.path.exists(p):
        if os.path.isdir(p):
            import shutil; shutil.rmtree(p)
        else:
            os.unlink(p)
```

**新 argparse flags（`run_pipeline.py:272-304` 块内追加）：**
```python
ap.add_argument("--skip-semantic", action="store_true",
                help="跳过运镜语义分析（shot-analysis 路由调用）")
ap.add_argument("--offline", action="store_true",
                help="全局：仅读缓存不联网（route_cache 命中即用，miss 则降级空 facets）")
ap.add_argument("--analysis-url",
                default="http://127.0.0.1:8000/api/v1/production/shot-analysis",
                help="shot-analysis 路由 URL（含 /api/v1/production/shot-analysis path）")
ap.add_argument("--analysis-timeout", type=float, default=960.0,
                help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
```

### Pattern 1: Per-shot Cache with Content-Hash Key

**What:** 每 shot 的路由响应独立缓存，key 由 4 元组锁定。
**When to use:** 任何 per-shot 网络调用；保证视频文件改、route 版本升、shot id 变都不污染。

```python
# Source: Phase 6 design (CONTEXT CINEMA-04 锁定)
import hashlib, os, json

ROUTE_NAME = "shot_analysis"
ROUTE_VERSION = "feat-shot-analysis-route-v1"   # 路由逻辑变了就 bump 此串 → 全 cache miss

def video_content_hash(video_path: str) -> str:
    """sha256(first_1MB + last_1MB + str(size)) — multi-GB 视频也快。"""
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))                    # head 1MB
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)
            h.update(f.read(1024 * 1024))                # tail 1MB
    h.update(str(size).encode())
    return h.hexdigest()[:16]                            # 16 char 足够防碰撞

def cache_path(work_dir: str, shot_id: int) -> str:
    return os.path.join(work_dir, "route_cache", ROUTE_NAME,
                        f"shot_{shot_id:03d}.json")

def cache_key_matches(cache_file: str, vch: str) -> bool:
    """缓存文件内置 `_cache_key` 字段比对。"""
    try:
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f).get("_cache_key") == {
                "video_content_hash": vch,
                "route_name": ROUTE_NAME,
                "route_version": ROUTE_VERSION,
            }
    except (OSError, json.JSONDecodeError):
        return False
```

### Pattern 2: Graceful-Degrade via `httpx.HTTPError` Catch-all

**What:** 单个 try/except 捕获所有 httpx 失败 → 空串 facets + warning。
**When to use:** 每次 per-shot POST 调用环绕；preflight 也是同款。

```python
# Source: httpx 0.28.1 exception 层级（in-env 内省确认）
# HTTPError (root)
# ├─ RequestError → TransportError → TimeoutException → {ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout}
# │                                → NetworkError → {ConnectError, ReadError, WriteError, CloseError}
# │                                → ProtocolError, ProxyError, UnsupportedProtocol
# └─ HTTPStatusError  (4xx/5xx 响应)

import httpx

def call_route_per_shot(client: httpx.Client, body: dict, timeout: float
                        ) -> tuple[dict | None, str | None]:
    """Return (response_data, error_message). 任意失败 → (None, msg)."""
    try:
        resp = client.post("/api/v1/production/shot-analysis", json=body)
        resp.raise_for_status()                          # → HTTPStatusError on 4xx/5xx
        payload = resp.json()
        if payload.get("code") != 200:
            return None, f"route body code={payload.get('code')}: {payload.get('message')}"
        shots = payload.get("data", {}).get("shots", [])
        if not shots:
            return None, f"route returned 0 shots for body={body}"
        return shots[0], None                            # per-shot 调用只取 [0]
    except httpx.HTTPError as e:
        return None, f"{type(e).__name__}: {e}"
```

`httpx.HTTPError` 是 root exception，catch 它即覆盖所有 ConnectError/TimeoutException/HTTPStatusError — 对 graceful-degrade 最简洁。

### Anti-Patterns to Avoid

- **把 `subject`/`scene` facets 从路由 `subject.direction_cn` 或别的字段硬凑出来**：CONTEXT 决策明确留空，不要"看起来有用就填"；身份由 Phase 7 re-id 处理。
- **批调用全 shots（不带 `shot_id_range`）**：路由批返回 `data.shots[]` 后任一 shot 失败会让整个响应 500，丢掉所有 shots 的成果。per-shot 调用隔离失败。
- **`generator.warnings` 不扩 schema 直接写**：`additionalProperties:false` 会让 inline validator（`export_asset.py:validate_asset_json`）拒绝 manifest，asset 导出失败。必须先扩 schema。
- **`--force` 不清 `route_cache/`**：开发者切到新 ROUTE_VERSION 或新视频后，旧 cache 仍命中，出现"修了代码但行为不变"的困惑。
- **read timeout ≤ 900s**：路由 `execFileSync` timeout=900_000ms，路由会先自杀；客户端若 read timeout 更短会先抛 ReadTimeout；若等长会 race。960s 故意超出 60s 余量。
- **`prompts.json` 写后不 schema 自校验**：inline `Draft202012Validator` 是项目惯例（export_asset 就这么做）；映射写错字段会立即被 schema 拒绝而不是流向下游。
- **借用 `prompts/merge_prompts.py` 做路由合并**：那个工具只合 `part_*.json` 分片，与 step_semantic 职责正交。step_semantic 是首个真正的 prompts producer in run_pipeline。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP 连接池 / keep-alive / retry transport | 手 socket / urllib + 自己写 pool | `httpx.Client(base_url=..., timeout=...)` | httpx 自带连接池、HTTP/1.1 keep-alive、SSL、clear exception 层级；env 已装 |
| Timeout 分粒度控制 | 单一 timeout 标量 | `httpx.Timeout(connect=5, read=960, write=5, pool=5)` | 路由是 long-running（≤900s）；connect 应秒级失败，read 须 >900s |
| Exception 分类（连接拒绝 vs DNS 失败 vs 4xx vs 超时） | 看 errno / 看 status 字符串 | `httpx.ConnectError`/`TimeoutException`/`HTTPStatusError` | httpx 提供一级异常根 `HTTPError` + 细分层级（已内省） |
| Per-shot cache key | 全文件 sha256 | head 1MB + tail 1MB + size sha256 | multi-GB episode 视频全读需数十秒；首尾 1MB 是 git-annex / content-defined chunking 的成熟简化 |
| prompts.json schema 校验 | 手写字段检查 | `jsonschema.Draft202012Validator` | v1.0 已用；schema 是 machine-truth（PROJECT 两层权威决策） |
| ComfyUI workflow 构建 / SAM3 / DINOv2 | 在 shot-timeline 里跑 ML | 走路由（kais-aigc-platform 侧） | CLAUDE.md "不碰核心算法" + SUMMARY "shot-timeline 保持 thin（仅 httpx，零 ML 依赖）" |

**Key insight:** shot-timeline 的本 phase 边界是"网络调用 + 字段重组 + 缓存"。任何把 ML 推理搬进本仓库的冲动都是范围溢出（OUT OF SCOPE 已明列）。

## Common Pitfalls

### Pitfall 1: 路由侧 900s 自杀 vs 客户端 timeout 竞态
**What goes wrong:** 路由 driver `execFileSync(timeout=900_000)` 到点杀 driver，路由返回 500；客户端若 read timeout ≤ 900s 会先抛 ReadTimeout；若等长 race。
**Why it happens:** 路由内部有自己的硬超时；客户端不知道。
**How to avoid:** `--analysis-timeout` 默认 **960s**（>900s 60s 余量），让路由先自杀完毕，客户端拿到确定的 500 响应走 graceful-degrade。
**Warning signs:** 间歇性 ReadTimeout + 紧接 500；或 driverStdout 截断。

### Pitfall 2: `generator.warnings` schema 未扩 → asset.json 被自己 inline validator 拒
**What goes wrong:** 开发者直接在 `export_asset.py:build_asset_dict` 加 `"warnings": [...]`，没改 `asset.schema.json`；`validate_asset_json` 用 `additionalProperties:false` 的 schema 检测出 unknown property，sys.exit 非 0，asset 导出失败。
**Why it happens:** Phase 5 锁了 schema 但没加 warnings 字段；Phase 6 忘记同步扩。
**How to avoid:** 把 schema 扩展作为 Phase 6 第一个任务（先 schema 后 producer code，沿用 Phase 5 contract-first 模式）；同步更新 SPEC §3、verify_contract.py fixture。
**Warning signs:** `asset.json failed schema validation: at generator: Additional properties are not allowed ('warnings' was unexpected)`。

### Pitfall 3: 路由字段为 null / 空串 → 映射出现 `"None"` / leading 逗号
**What goes wrong:** captured shot_002 的 `semantic.shot_scale = None`、shot_005 `subject_motion = ""`、shot_007 `subject_motion = null`。若映射函数 `", ".join([shot_scale, ...])` 不滤，会得 `"None, follow, ..."` 或 `", follow, ...`。
**Why it happens:** 路由 Qwen3-VL 在低信号镜头上回 null/""。
**How to avoid:** 映射函数 `join_nonempty(*parts)` 过滤 `if p` 后再 join；None/"" 自动剔除。（已在本 research 实测验证，见 Validation Architecture。）
**Warning signs:** prompts.json 出现字面 `"None"` 或前导 `, `。

### Pitfall 4: `--offline` cache miss 时静默不填字段
**What goes wrong:** 用户 `--offline` 跑，某 shot cache miss（首次跑或 cache 被清），代码跳过该 shot 不警告 → prompts.json 该 shot 全空 facets，用户以为路由填好了。
**Why it happens:** offline 模式不联网是对的，但不告知用户"这个 shot 没填"。
**How to avoid:** offline 模式 cache miss 时写 warning 到 sidecar：`"shot N: offline mode + cache miss → empty facets"`；export 时进 generator.warnings。
**Warning signs:** offline 跑完 asset.json warnings 空、但 prompts.json 大量空 facets。

### Pitfall 5: `--force` 没清 route_cache → 改代码后行为不变
**What goes wrong:** 开发者 bump ROUTE_VERSION 但 `--force` 只清了 shots.json/prompts.json 等，route_cache 残留旧版本响应；step_semantic 读 cache 跳过网络，以为"新版本路由"的输出但其实还是旧的。
**Why it happens:** `--force` 清单（`run_pipeline.py:326-327`）当前不含 route_cache。
**How to avoid:** Phase 6 把 `route_cache/` 目录加进 `--force` 清单（rmtree）。同时 cache 文件内置 `_cache_key` 字段，版本不匹配自动失效（双保险）。
**Warning signs:** 改了 ROUTE_VERSION 但 prompts.json 内容没变。

### Pitfall 6: 全批调用丢部分失败
**What goes wrong:** 客户端图省事一次 POST 不带 shot_id_range，路由 driver 处理到一半某 shot 报错 → 整个 `execFileSync` 非零退出 → 路由回 500 + 全部 shots 丢失。
**Why it happens:** 路由 driver 内部 `for s in shots` 循环无 per-shot try/except。
**How to avoid:** 强制 per-shot 调用（`shot_id_range: [N, N]`）；单 shot 失败仅丢那一镜，余下继续。
**Warning signs:** 单个坏 shot 让整集 prompts.json 全空。

### Pitfall 7: preflight 每镜重试拖慢整集
**What goes wrong:** N=100 镜的 episode，每镜都先 GET 探测路由，路由 down 时每镜 connect 失败要等 connect timeout（默认 5s × 100 = 500s）。
**Why it happens:** 没有短路标志。
**How to avoid:** preflight 只跑一次；探测失败立即设 `route_down = True`，余下 shot 全跳过网络、直接降级。
**Warning signs:** offline 跑快，online 路由 down 时奇慢。

## Code Examples

### Example 1: 完整 step_semantic 调用客户端（参考实现骨架）

```python
# Source: Phase 6 design synthesized from CONTEXT 决策 + httpx 0.28.1 verified API +
#         feat/shot-analysis-route route contract (git show 读取)
# 落地文件：analysis/call_shot_analysis.py
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path
import httpx
from jsonschema import Draft202012Validator

ROUTE_NAME = "shot_analysis"
ROUTE_VERSION = "feat-shot-analysis-route-v1"
PROMPTS_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "prompts.schema.json"


def video_content_hash(video_path: str) -> str:
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)
            h.update(f.read(1024 * 1024))
    h.update(str(size).encode())
    return h.hexdigest()[:16]


def compose_facets(route_shot: dict) -> dict:
    """CONTEXT-locked 映射 — null/空串自动滤除。"""
    sem = route_shot.get("semantic") or {}
    geo = route_shot.get("geometry") or {}
    def join(*parts):
        return ", ".join(str(p) for p in parts if p)
    return {
        "camera":   join(sem.get("shot_scale"), sem.get("camera_primitive"),
                         sem.get("camera_speed"), geo.get("primitive")),
        "action":   sem.get("subject_motion") or "",
        "lighting": sem.get("lighting") or "",
        "style":    sem.get("lens_feel") or "",
        "subject":  "",    # 永不伪造 — Phase 7 re-id 处理身份
        "scene":    "",    # 永不伪造 — 未来 Qwen-VL 扩展
    }


def call_route(client: httpx.Client, body: dict) -> tuple[dict | None, str | None]:
    try:
        resp = client.post("/api/v1/production/shot-analysis", json=body)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200:
            return None, f"route code={payload.get('code')}: {payload.get('message')}"
        shots = payload.get("data", {}).get("shots", [])
        return (shots[0] if shots else None), (None if shots else "route returned 0 shots")
    except httpx.HTTPError as e:
        return None, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description="逐镜头运镜分析路由调用 → prompts.json")
    ap.add_argument("--video", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output", required=True, help="prompts.json 输出路径")
    ap.add_argument("--analysis-url", default="http://127.0.0.1:8000/api/v1/production/shot-analysis")
    ap.add_argument("--analysis-timeout", type=float, default=960.0)
    ap.add_argument("--offline", action="store_true", help="仅读 cache 不联网")
    args = ap.parse_args()

    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    vch = video_content_hash(args.video)

    cache_dir = os.path.join(args.work_dir, "route_cache", ROUTE_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    warnings sidecar path = os.path.join(args.work_dir, "route_cache", "warnings.json")
    warnings = []
    prompts = []

    # Preflight（非 offline 模式才探）
    route_down = args.offline
    if not args.offline:
        try:
            with httpx.Client(base_url=args.analysis_url.rsplit("/api/v1", 1)[0],
                              timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)) as probe:
                probe.get("/api/v1/production/shot-analysis", timeout=5.0)  # 路由只定义 POST /，404 也算"up"
        except httpx.HTTPError as e:
            route_down = True
            warnings.append(f"preflight route unreachable: {type(e).__name__}: {e}")
            print(f"[semantic] preflight failed → route_down mode: {e}")

    with httpx.Client(base_url=args.analysis_url,
                      timeout=httpx.Timeout(connect=5.0, read=args.analysis_timeout,
                                            write=5.0, pool=5.0)) as client:
        for s in shots_meta:
            sid = s["id"]
            cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")

            # 1) cache hit?
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("_cache_key", {}).get("video_content_hash") == vch \
                        and cached.get("_cache_key", {}).get("route_version") == ROUTE_VERSION:
                    print(f"[semantic] shot {sid}: cache hit")
                    route_shot = cached
                else:
                    route_shot = None  # stale, fall through
            else:
                route_shot = None

            # 2) cache miss → 联网（route_down 模式跳过）
            if route_shot is None and not route_down:
                body = {"video": os.path.abspath(args.video),
                        "shots": os.path.abspath(args.shots),
                        "shot_id_range": [sid, sid],
                        "semantic": True, "subject": False, "grid_n": 20, "fps": 24}
                route_shot, err = call_route(client, body)
                if err:
                    warnings.append(f"shot {sid}: {err}")
                    print(f"[semantic] shot {sid}: FAIL {err}")
                else:
                    # 写 cache（带 _cache_key）
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump({**route_shot, "_cache_key": {
                            "video_content_hash": vch,
                            "route_name": ROUTE_NAME,
                            "route_version": ROUTE_VERSION}}, f, ensure_ascii=False, indent=2)

            # 3) 映射 → facet（route_shot is None → 全空 facets，schema 仍合法）
            facets = compose_facets(route_shot) if route_shot else {
                "camera": "", "action": "", "lighting": "", "style": "", "subject": "", "scene": ""}
            prompts.append({
                "shot_id": sid,
                "start_sec": s["start_sec"], "end_sec": s["end_sec"], "duration": s["duration"],
                "subject": facets["subject"], "action": facets["action"],
                "camera": facets["camera"], "scene": facets["scene"],
                "lighting": facets["lighting"], "style": facets["style"],
                "prompt_text": "",   # Phase 8 owns recomposition
            })

    # 4) 写前 schema 自校验（fail loud）
    with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(prompts))
    if errors:
        sys.exit(f"prompts.json schema validation failed ({len(errors)} errors): "
                 + "; ".join(f"{'/'.join(map(str,e.absolute_path))}: {e.message}" for e in errors[:3]))

    # 5) 原子写 prompts.json
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    os.replace(tmp, args.output)

    # 6) warnings sidecar（export_asset.py 读取并合并进 generator.warnings）
    with open(warnings_sidecar_path, "w", encoding="utf-8") as f:
        json.dump({"warnings": warnings}, f, ensure_ascii=False, indent=2)

    print(f"[semantic] wrote {args.output} ({len(prompts)} shots, {len(warnings)} warnings)")
    return 0
```

### Example 2: export_asset.py 读取 warnings sidecar

```python
# Source: Phase 6 design（scripts/export_asset.py 扩展点）
def build_asset_dict(work_dir: str, video_path: str, warnings: list[str] | None = None) -> dict:
    # ... 现有逻辑 ...
    generator = {
        "tool": "kais-shot-timeline",
        "version": _git_sha(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if warnings:                                # 仅非空时 emit（schema optional）
        generator["warnings"] = warnings
    return { /* ... */ "generator": generator /* ... */ }


def main():
    # ... 现有 ...
    warnings_sidecar = os.path.join(work_dir, "route_cache", "warnings.json")
    warnings = None
    if os.path.exists(warnings_sidecar):
        try:
            with open(warnings_sidecar, encoding="utf-8") as f:
                warnings = json.load(f).get("warnings")
        except (OSError, json.JSONDecodeError):
            pass
    asset = build_asset_dict(work_dir, video, warnings=warnings)
```

### Example 3: 映射对 7 个真实 captured fixtures 的实测输出

```
shot       camera                                        action                    lighting     style
--------------------------------------------------------------------------------------------------------------
shot_001   中景, follow, fast, tilt_up                     向下坠落                  自然光        wide
shot_002   follow, fast, pan_right                       向前跳跃飞行                自然光        normal
shot_003   中景, follow, fast, pan_right                   飞虫持刀向前飞行            雾气弥漫      normal
shot_004   中景, follow, fast, dolly_or_zoom_in            向前奔跑                  自然光        normal
shot_005   static, slow, static                                                    自然光        wide
shot_006   近景, dolly_in, fast, pan_right                 向前冲刺挥刀               自然光        normal
shot_007   中景, static, slow, pan_right                                             自然光        normal
```

（shot_002 `shot_scale=null`、shot_005 `subject_motion=""` 自动被 `join_nonempty` 滤除 — schema 0 错误。）

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requests` + 自己 retry | `httpx` + `httpx.Timeout` 分粒度 + 不 retry（per-shot 失败非致命） | httpx 0.28（2024-11） | 更清晰异常层级、HTTP/2 ready、同作者下一代 |
| 全文件 sha256 cache key | head 1MB + tail 1MB + size sha256 | 本 phase 设计（CONTEXT D-04） | multi-GB episode 视频 hash 从数十秒降到毫秒 |
| Zod-validated POST body | （路由侧已用 Zod） | 路由侧 `feat/shot-analysis-route` | 客户端只需发 JSON，schema 错误回 400 + VALIDATION_ERROR |
| `execFileSync` 单体 driver | 路由内 spawn 已 vendor 的 Python driver | 路由侧 | 900s 硬超时；客户端须 >900s |

**Deprecated/outdated:**
- `httpx.Proxies` 参数：0.28 起移除，用 `proxy=` 单值（本 phase 不用代理，N/A）。
- `urllib.request`（driver 用的）：对 long-running POST 不合适（无分粒度 timeout、无 connection pool）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `httpx` 0.28.1 是合法、主流包（slopcheck 因网络不可达无法验证，标 `[ASSUMED]`） | Standard Stack / Package Legitimacy Audit | 极低 — env 已装、`pip show` 显示 BSD-3-Clause + Tom Christie 作者 + 众多下游依赖、API 已 in-env 内省。planner 加 `checkpoint:human-verify` 即可。 |
| A2 | `--analysis-url` 默认端口 8000（路由 typical dev port） | run_pipeline.py Integration | 中 — aigc-platform 实际路由挂哪个端口未验证（路由 unmerged）；用户首跑需 `--analysis-url` 显式给值。推荐不假设端口，文档化常见值。 |
| A3 | 路由 GET `/api/v1/production/shot-analysis`（路由只 define POST `/`）会回 404 或 405 — 算"up"信号 | Pattern 2 / Preflight | 低 — 任何 HTTP 响应（哪怕 404）证明 host:port 可达；只有 `httpx.ConnectError` 才算"down"。 |
| A4 | `ROUTE_VERSION = "feat-shot-analysis-route-v1"` 是合理的初始串 | Pattern 1 | 低 — 只是 cache invalidation 字符串，路由 merge 后可改 `"v1"` 等；bump 即全 cache miss。 |
| A5 | 路由 `/api/v1/production/shot-analysis` 路径前缀正确（`/api/v1` 版本前缀） | Route REQUEST Contract | 极低 — `index.ts` 默认 export router，aigc-platform typical mount point；branch merge 后用户 verify。 |
| A6 | 路由 base host 是 `127.0.0.1`（本地开发） | flags 默认 | 低 — 生产可改；CONTEXT 决策 URL 可配。 |

## Open Questions (RESOLVED — all addressed in plans 06-02 / 06-03)

1. **aigc-platform 路由实际监听哪个端口？**
   - What we know: `--analysis-url` 默认值需要 host:port；CONTEXT 给的是 `http://127.0.0.1:<port>/api/v1/production/shot-analysis`（`<port>` 占位符）。
   - What's unclear: aigc-platform 服务的 default dev port（8000? 3000? 自定义?）— 路由分支 unmerged，没机会启动验证。
   - RESOLVED: Plan 03 把默认 URL 设为 `http://127.0.0.1:8000/api/v1/production/shot-analysis`（typical dev port），文档化"用户首跑需 verify 端口"。STATE.md 已记录 live round-trip deferred（路由 unmerged）。

2. **`step_semantic` 是否应该读 `prompts/merge_prompts.py` 的 `part_*.json` 产物？**
   - What we know: CONTEXT 决策 "若 `part_*.json` 存在 route wins for 5 fields"。
   - What's unclear: 当前 `merge_prompts.py` 是手动外部步骤，未接 run_pipeline；step_semantic 应该 call 它、还是仅做"route 不存在的字段回退到 part_*.json"？
   - RESOLVED (documented deviation): merge **NOT** implemented in Plan 02 — `merge_prompts.py` 当前是手动外部步骤，**未**接 run_pipeline，pipeline run 期间不产 `part_*.json`。Plan 02 直接从 route facets 写 prompts.json（`prompt_text=""`、`subject=""`），并在 objective 显式记录该 deviation + 未来 wiring 路径（merge_prompts.py 接入后扩展 Task 1 compose step 预载 part_*.json 作 base）。Q2 的 Recommendation（直接读 part_*.json）因前提不成立而 deferred，非静默丢弃。

3. **ROUTE_VERSION 字符串应在哪定义？**
   - What we know: cache key 须含它，否则路由逻辑改后 cache 陈旧。
   - What's unclear: 是硬编码在 `call_shot_analysis.py` 顶层常量、还是从路由 response 探测（路由没显式返回版本）？
   - RESOLVED: Plan 02 硬编码 module-level 常量 `ROUTE_VERSION = "feat-shot-analysis-route-v1"`（响应无版本字段，无法自动探测）；路由 merge 后手动 bump 即失效全部 cache。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | 所有 pipeline 脚本 | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| `httpx` | CINEMA-01 路由调用 | ✓ | 0.28.1 (`/home/kai/.local/lib/python3.12/site-packages`) | 无（核心依赖；若缺则 step_semantic fail-loud） |
| `jsonschema` | schema 自校验 | ✓ | 4.26.0（v1.0 已用） | — |
| ffmpeg / ffprobe | probe_duration 等（step_export 仍用） | ✓ | 6.1.1（CLAUDE.md） | — |
| shot-analysis ROUTE | CINEMA-01..06 live round-trip | ✗ | — | **DEFERRED to post-merge** — mapping & graceful-degrade 用 captured fixtures + route-down 模式验证；live E2E 推到 `feat/shot-analysis-route` merge 后 |
| Captured route fixtures | 测试与开发 | ✓ | 7 文件 @ `/mnt/agents/output/gpu1/shot_analysis/shot_00{1..7}.json` | 复制进 repo `examples/` 或测试 fixtures 防丢失 |

**Missing dependencies with no fallback:**
- 无（httpx + jsonschema + ffmpeg 全在 env；route live round-trip 是 STATE.md 已记录的 deferred blocker，不阻塞 Phase 6 coding）。

**Missing dependencies with fallback:**
- 路由不可用 → `--offline` + cache fixtures / `--skip-semantic`；live 验证 deferred。

## Validation Architecture

> `workflow.nyquist_validation: true`（config.json 确认）— 本 section REQUIRED。
>
> **OVERRIDDEN by `06-VALIDATION.md`** (newer, `status: approved` 2026-07-24): the project stays **pytest-free** per CLAUDE.md / v1.0 RETROSPECTIVE ("no test framework; standalone `sys.exit(0/1)` scripts"). The pytest + `tests/` recommendations below were the researcher's default framing; the actual assertion engine is inline `python3 -c` checks + the standalone `scripts/verify_phase6_smoke.py` (Plan 03, mirrors `scripts/verify_contract.py`). Plans follow VALIDATION.md, not the pytest suggestions below.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | **pytest** (要新装 — repo 当前无测试框架，CLAUDE.md: "None. No pytest, unittest cases, tox, or any test files present") |
| Config file | none — Wave 0 创建 `pytest.ini` 或 `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest tests/ -x -q` |
| Full suite command | `python3 -m pytest tests/ -v` |

> Phase 6 是项目首个引入测试的 phase（CLAUDE.md 明示无测试）。Wave 0 必须装 pytest + 建 `tests/` 目录 + 建 `conftest.py` 共享 fixtures。

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CINEMA-01 (mapping) | `compose_facets(shot_003.json)` → `camera="中景, follow, fast, pan_right"`、`action="飞虫持刀向前飞行"`、`lighting="雾气弥漫"`、`style="normal"`、`subject=""`、`scene=""` | unit | `python3 -m pytest tests/test_compose_facets.py -x` | ❌ Wave 0 |
| CINEMA-01 (null 边界) | shot_002 (shot_scale=null) → `camera` 不出现 "None" 字面；shot_005 (subject_motion="") → `action=""` | unit | `python3 -m pytest tests/test_compose_facets.py::test_null_fields -x` | ❌ Wave 0 |
| CINEMA-01 (schema 合法) | 合成 prompts.json 从全部 7 fixtures → `Draft202012Validator` 0 errors | unit | `python3 -m pytest tests/test_prompts_schema.py -x` | ❌ Wave 0 |
| CINEMA-03 (route down 降级) | `httpx.Client` 指向不可达 URL（如 `http://127.0.0.1:1/`）→ 所有 facets 空 + warnings 非空 + prompts.json schema 合法 | integration | `python3 -m pytest tests/test_route_down_graceful.py -x` | ❌ Wave 0 |
| CINEMA-04 (cache hit) | 预填 cache 文件（含正确 `_cache_key`），`--offline` 跑 → 0 网络调用，prompts.json 用 cache 数据 | integration | `python3 -m pytest tests/test_cache_offline.py -x` | ❌ Wave 0 |
| CINEMA-04 (cache stale) | cache 文件 `_cache_key.route_version` 旧 → 视为 miss；route down → 降级空 facets | integration | `python3 -m pytest tests/test_cache_stale.py -x` | ❌ Wave 0 |
| CINEMA-04 (video_content_hash) | 同一 video 两次 hash 相同；改 1 byte 内容 → hash 变 | unit | `python3 -m pytest tests/test_video_hash.py -x` | ❌ Wave 0 |
| CINEMA-05 (warnings sidecar) | route down → `route_cache/warnings.json` 写出含原因 | integration | `python3 -m pytest tests/test_warnings_sidecar.py -x` | ❌ Wave 0 |
| CINEMA-05 (schema 扩展) | asset.json 含 `generator.warnings=["..."]` 通过 `validate_asset_json` | unit | `python3 -m pytest tests/test_generator_warnings_schema.py -x` | ❌ Wave 0 |
| CINEMA-06 (--skip-semantic) | `--skip-semantic` → step 返回 None，不调子进程 | unit | `python3 -m pytest tests/test_skip_semantic.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -x -q`（quick < 10s）
- **Per wave merge:** `python3 -m pytest tests/ -v`（full < 30s）
- **Phase gate:** Full suite green + `python3 spec/validate.py`（v1.1 fixture 仍全绿）+ `python3 scripts/verify_contract.py --mode=producer`

### Wave 0 Gaps
- [ ] `tests/__init__.py` — 空 marker
- [ ] `tests/conftest.py` — 共享 fixtures：`fixture_shot_003`（load /mnt/.../shot_003.json 或复制进 repo 的副本）、`tmp_work_dir`（tmp_path factory）、`unreachable_client`（httpx.Client 指向 closed port）
- [ ] `tests/fixtures/shot_analysis/shot_00{1..7}.json` — 把 `/mnt/agents/output/gpu1/shot_analysis/` 复制进 repo，保证 CI/离线开发可用（captured output 不在 repo 内）
- [ ] Framework install: `pip install pytest` — 若 env 未装
- [ ] `pytest.ini` 或 `pyproject.toml [tool.pytest.ini_options]`：`testpaths = tests`, `python_files = test_*.py`

*(若 planner 决定 Wave 0 仅做最小 fixture + 一个 happy-path mapping test 也 OK — 但 graceful-degrade 测试是 CINEMA-03 的核心证据，不可省。)*

## Security Domain

> `security_enforcement` 未在 config.json 显式 false（absent = enabled）— 本 section REQUIRED。
> Phase 6 安全面很小：本地 CLI 工具、调本地路由、无多用户、无 PII 处理。仍列适用项。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 路由无认证（local dev）；不引入凭据 |
| V3 Session Management | no | 无 session 概念 |
| V4 Access Control | no | 单用户 CLI |
| V5 Input Validation | yes | Zod 在路由侧校验 body；客户端不重复校验，但 `--analysis-url` 须是合法 URL（httpx `InvalidURL` 自然抛） |
| V6 Cryptography | no | 无 crypto 操作（sha256 cache key 是 fingerprint，非安全 hash） |
| V7 Error Handling | yes | graceful-degrade — `httpx.HTTPError` catch-all，任意失败不崩溃；per-shot 失败不阻断整集 |
| V8 Data Protection | no | 无敏感数据落地（路由响应是运镜分析，无 PII） |
| V9 Communications | yes | localhost HTTP（生产可 HTTPS）；httpx `verify=True` 默认开 SSL 验证（HTTPS 时） |
| V12 Files & Resources | yes | cache 文件路径不来自用户输入（由 `work_dir` + shot_id 组成，无 traversal 风险）；`--force` rmtree 仅限已知 `route_cache/` 目录 |

### Known Threat Patterns for httpx → local HTTP route stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 路由 SSRF（客户端把用户输入当 URL） | Tampering | `--analysis-url` 是开发者 CLI flag，非运行时用户输入；httpx `base_url` 校验 |
| 路由 down 拖垮 pipeline（DoS） | Denial of Service | `--analysis-timeout`（默认 960s）+ preflight 短路 + per-shot 失败非致命 + `--skip-semantic` escape hatch |
| Cache poisoning（篡改 route_cache 文件） | Tampering | cache 文件属本地 filesystem trust boundary；`_cache_key` 字段防版本串；Phase 6 不引入签名（YAGNI） |
| `--video` 路径注入到 route body | Information Disclosure | 视频路径是 CLI arg，非外部输入；路由侧 `docker cp` 接受任意路径但只在容器 input dir 写 basename（无 traversal） |

## Sources

### Primary (HIGH confidence)
- **路由源码（直接 git show，未 checkout）**: `git -C /data/workspace/kais-aigc-platform show feat/shot-analysis-route:src/routes/production/shot-analysis/index.ts` — POST body Zod schema、driver spawn argv、900s `execFileSync` timeout、response envelope `{code,data,message}`。`_shared/config.ts` — `containerName="comfyui-primary"`、`shotAnalysisDir="/mnt/agents/output/gpu1/shot_analysis"`。`scripts/shot-analysis/shot_analysis_driver.py` — ComfyUI workflow 构建、SAM3 + QwenVL 节点配置、SEMANTIC_PROMPT 模板（解释了 `semantic: true` 为何必需）。
- **Captured route output（7 文件）**: `/mnt/agents/output/gpu1/shot_analysis/shot_00{1..7}.json` — 全部 schema 验证 0 错误；mapping 边界用例（null/""/mixed）覆盖。
- **httpx 0.28.1 in-env introspection**: `python3 -c "import httpx, inspect; ..."` 直接打印 exception 层级（`HTTPError → RequestError → TransportError → TimeoutException/NetworkError`）、`Client.__init__` / `Client.post` / `Timeout` / `raise_for_status` signatures。比文档更权威。
- **`pip show httpx`**: Author=Tom Christie、BSD-3-Clause、Required-by diffusers/gradio_client/hermes-agent/huggingface_hub/mcp/openai/python-telegram-bot/weasel — 众多下游依赖证明主流合法。
- **本 repo 源码**: `run_pipeline.py`（step_* pattern、argparse、`[N/6]` 18 处、`--force` 清单、`_safe_mtime` helper）；`scripts/export_asset.py`（`build_asset_dict` 当前签名、`validate_asset_json` inline validator）；`prompts/merge_prompts.py`（`part_*.json` 合并模式、`p.get(fld, "")` 惯例）；`spec/schemas/{prompts,asset}.schema.json`（generator `additionalProperties:false` 无 warnings、prompts facets `type:string` 无 minLength）。
- **Phase 5 VERIFICATION**: `.planning/phases/05-contract-v1-1/05-VERIFICATION.md` — 确认 generator required byte-identical to v1.0（无 warnings 字段）；v1.1 schemas + EIGHT_SHAPES + cross-version check SHIPPED。

### Secondary (MEDIUM confidence)
- **`@/lib/responseFormat.ts`**: `{ code: 200/400, data, message }` envelope shape（`success(data, message)` / `error(message, data)` helper）。
- **[HTTPX Timeouts — official docs](https://www.python-httpx.org/advanced/timeouts/)** via WebSearch summary — 默认 5s timeout、`Timeout(connect=, read=, write=, pool=)` 分粒度、`raise_for_status()` 抛 `HTTPStatusError`。
- **[HTTPX Exceptions — official docs](https://www.python-httpx.org/exceptions/)** via WebSearch summary — exception 层级与 in-env 内省一致。

### Tertiary (LOW confidence — marked for validation)
- **aigc-platform 实际 dev port**（Open Question #1）— 路由 unmerged 无法启动验证；typical Express port 3000/8000，CONTEXT 给占位符。
- **`httpx` PyPI 下载量元数据**（slopcheck registry unreachable）— 无法定量；但定性证据（pip show 下游依赖、Author、版本连续性）强。

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — httpx 0.28.1 env 已装 + pip show 验证 + API in-env 内省；jsonschema v1.0 已用。
- Route REQUEST contract: **HIGH** — 直接 git show 读取未 checkout 的 feat/shot-analysis-route；body schema、response envelope、900s timeout 全源码确认。
- Mapping correctness: **HIGH** — 7 个真实 fixtures 全 0 schema 错误；null/"" 边界覆盖。
- Architecture (run_pipeline 整合): **HIGH** — 直接 grep 出 18 处 `[N/6]` + 插入点；step_* 模式成熟。
- Schema delta (generator.warnings): **HIGH** — Phase 5 VERIFICATION 直接确认未加；本 phase 加法清晰。
- Pitfalls: **HIGH** — 路由 timeout race、warnings schema 漏扩、null 映射、cache stale、批调用失败、preflight 短路 全 anchored 在源码或 captured fixtures。
- Live route E2E: **DEFERRED** — STATE.md blocker（feat/shot-analysis-route unmerged）；非本 phase 可达。

**Research date:** 2026-07-24
**Valid until:** 2026-08-24（30 天；route 分支 merge 后 ROUTE_VERSION 等 literal 需复核）

## RESEARCH COMPLETE
