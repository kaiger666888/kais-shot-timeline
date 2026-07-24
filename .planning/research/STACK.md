# Stack Research — v1.1 分镜语义深化

**Domain:** Video-shot-decomposition producer (Python CLI) + downstream canvas consumer (cross-repo TS/React) + external ComfyUI-hosted ML routes
**Researched:** 2026-07-24
**Confidence:** HIGH (live-verified against both repos + PyPI)

> Scope: ONLY the stack additions/changes for **v1.1 NEW capabilities** — shot-timeline calling kais-aigc-platform HTTP routes, cross-shot character/prop re-id, prompt reference system, ShotTimelineAsset contract bump, dual-end display. The validated v1.0 baseline (PySceneDetect / Demucs / Whisper / ffmpeg / jsonschema) is OUT OF SCOPE — already shipped, do not re-litigate.

---

## TL;DR — The Hard Boundary

**shot-timeline stays THIN.** v1.1 adds exactly **ONE new runtime dependency** to shot-timeline (`httpx`, already installed in the env) and **ZERO new ML dependencies**. All heavy ML (embeddings, clustering, SAM3 segmentation, VLM inference) stays in `kais-aigc-platform` behind HTTP routes — consistent with the v1.0 "external producer" + "loose coupling" + "don't touch shot-timeline algorithms" decisions.

| Surface | What's added in v1.1 |
|---|---|
| **shot-timeline (this repo, Python)** | `httpx` client lib (already in env); stdlib `json`/`argparse` (already); no torch, no transformers, no ML |
| **kais-aigc-platform route (cross-repo)** | DINOv2 ViT-B/14 via `transformers`; `scikit-learn` for clustering; SAM3 already there |
| **ShotTimelineAsset contract** | `schema_version` bump; 2 new optional data files (`characters.json`, `props.json`); existing `prompts.json` enriched; **NO breaking changes** |
| **Canvas consumer (cross-repo)** | Reuse existing `asset` node type with `assetType: "character"\|"prop"` (already in Zod). **NO new node type, NO contract bump.** |

---

## Recommended Stack

### 1. HTTP Client (shot-timeline → kais-aigc-platform route) — **httpx 0.28.1**

| Technology | Version | Status | Purpose | Why |
|---|---|---|---|---|
| **httpx** | **0.28.1** (latest) | **Already installed** in env (`/home/kai/.local/lib/python3.12/site-packages`) | Sync HTTP client to call `POST /api/v1/production/shot-analysis` (and the new character-reid route) | Already in env (zero new install); sync mode (CLI is blocking); `HTTPTransport(retries=N)` for transport-level retry on transient failures; clean `timeout=httpx.Timeout(connect=5, read=900, write=10, pool=5)` semantics that match the route's 900s `execFileSync` timeout (verified `shot-analysis/index.ts:103`); first-class `httpx.Client` connection pooling if shot-timeline later batches N shots in one run |

**Why httpx over the alternatives:**

| Option | Verdict | Reason |
|---|---|---|
| **httpx** | **RECOMMENDED** | Already installed; modern API; transport-level retries built-in (`HTTPTransport(retries=3)` — verified via `help(httpx.HTTPTransport)`); explicit per-pool/connect/read timeouts (the route driver has a 900s ceiling, so `read` timeout MUST be ≥900s — urllib's `socket.setdefaulttimeout` is global and clumsy) |
| stdlib `urllib.request` | Rejected for this use | The comfyui driver (`shot_analysis_driver.py:112-132`) uses urllib, BUT that driver makes tiny fire-and-forget POSTs to a localhost ComfyUI. shot-timeline→route calls are long-running (up to 900s), need explicit timeout carving, retry on 5xx, and JSON response parsing. Hand-rolling this on urllib is error-prone; the existing driver's pattern does NOT generalize to "robust client of a remote service" |
| `requests` 2.34.0 | Acceptable fallback | Also already installed, but sync-only; no transport-level retry without `urllib3` adapter boilerplate; httpx is the modern replacement and is already there |

**Retry / timeout / error semantics for the previously-offline CLI:**

```python
# concrete pattern for the new step_semantic / step_reid client
import httpx

ANALYSIS_TIMEOUT = httpx.Timeout(connect=5.0, read=960.0, write=10.0, pool=5.0)
# read=960 > route's execFileSync 900s ceiling → server-side timeout surfaces first
ANALYSIS_TRANSPORT = httpx.HTTPTransport(retries=2, limits=httpx.Limits(max_connections=4))

def call_analysis_route(url: str, payload: dict, timeout: float = 960.0) -> dict | None:
    """POST to kais-aigc-platform route; graceful-degrade returns None on any failure."""
    try:
        with httpx.Client(timeout=timeout, transport=ANALYSIS_TRANSPORT) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            body = r.json()
            # route uses {success, data, message} envelope (verified: lib/responseFormat)
            return body.get("data") if body.get("success") else None
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as e:
        print(f"[warn] analysis route unavailable, graceful-degrade: {e}")
        return None  # caller skips the step, asset still exports
```

- **Graceful-degrade is non-negotiable** (PROJECT.md Constraint: "路由不可用时 shot-timeline 必须能 graceful-degrade"). The route lives in **two unmerged branches** (`feat/shot-geometry-nodes`, `feat/shot-analysis-route`) — at v1.1 ship time it may be down on any given box. `None` return → step prints warn + skips → `prompts.json` falls back to existing manual/merged fields → asset.json still emits at `schema_version "1.1"`.
- **No global mutable state.** Use a fresh `httpx.Client` per call (context manager). Matches shot-timeline's "every stage is a fresh process" convention (CLAUDE.md "No global state at Python level").

### 2. Re-ID Embedding Model (lives in kais-aigc-platform ROUTE, not shot-timeline) — **DINOv2 ViT-B/14**

| Technology | Version | Status | Purpose | Why |
|---|---|---|---|---|
| **DINOv2 ViT-B/14** (`facebook/dinov2-base`) | model card on HF (weights stable since 2023, SOTA for self-supervised re-id); load via `transformers` 5.14.1 AutoModel | NEW in route | Produces 768-d visual embedding for any crop (face, profile, back-of-head, full-body, object, prop) — cluster across shots to form registry | Single-model solution for **both** characters AND props; works on non-frontal faces and objects where face-recognition models return nothing; k-NN retrieval on DINOv2 embeddings is a documented re-id pattern; runs in the existing torch 2.6+cu124 env (verified) |

**Why DINOv2 over the alternatives — this is the load-bearing decision:**

| Model | Verdict | Reason |
|---|---|---|
| **DINOv2 ViT-B/14** | **STANDARDIZE HERE** | (1) **Universal**: one model handles characters (face/frontal/profile/body) AND props (sword, cup, costume). The milestone registry is `characters` + `props` — one embedding space beats maintaining two pipelines. (2) **Self-supervised**: not biased toward text-prompt similarity (CLIP's failure mode for "same object, different framing"). (3) **No face-detection prerequisite**: InsightFace ArcFace requires a detectable 112×112 face; back-of-head / masked / wide shots produce no embedding and the crop is silently dropped. DINOv2 embeds anything. (4) **Human-in-the-loop absorbs its imprecision** — re-id won't be 100% accurate regardless of model (milestone Constraint), so the marginal accuracy of face-specific models is not worth a second pipeline. |
| InsightFace `antelopev2` / `buffalo_l` (ArcFace, 512-d, ONNX) | DEFER to a later phase as additive | Best-in-class **for faces only**; both packs are non-commercial-research-licensed (verified — `insightface.ai/guides/choose-face-recognition-model`); antelopev2 download is fragile (issue #2517). If v1.2 finds DINOv2 misses same-actor links across extreme costume changes, ADD InsightFace as a face-only confirmation signal (weighted fusion), not a replacement. InsightFace 1.0.1 + `onnxruntime-gpu` 1.27.0 (latest, verified) when that day comes. |
| OpenCLIP ViT-L/14 (`open-clip-torch` 3.3.0 latest) | Rejected as primary | CLIP-style models are trained for image-text alignment, not instance identity. Two crops of the same prop with very different framing can land far apart because their text-aligned features differ. Fine for zero-shot classification (which we don't need here), wrong tool for re-id. |
| OpenAI CLIP `ViT-L/14` (`openai-clip` 1.0.1 latest) | Rejected | Same image-text alignment issue as OpenCLIP; additionally the `openai-clip` PyPI package is essentially a maintenance fork. No advantage over OpenCLIP. |

**Concrete loading pattern (route side):**

```python
# route's re-id driver — NOT shot-timeline
from transformers import AutoModel, AutoImageProcessor
import torch

MODEL_ID = "facebook/dinov2-base"  # 768-d, ViT-B/14, ~87M params, ~346MB
processor = AutoImageProcessor.from_pretrained(MODEL_ID)
model = AutoModel.from_pretrained(MODEL_ID).to("cuda").eval()

@torch.inference_mode()
def embed_crops(crops: list["PIL.Image"]) -> torch.Tensor:  # [N, 768]
    inputs = processor(images=crops, return_tensors="pt").to("cuda")
    outputs = model(**inputs)
    # CLS-token pooler_output = image-level embedding (HF docs confirmed)
    return outputs.pooler_output  # [N, 768], already L2-normalize before clustering
```

### 3. Clustering (lives in ROUTE, not shot-timeline) — **scikit-learn 1.9.0**

| Technology | Version | Status | Purpose | Why |
|---|---|---|---|---|
| **scikit-learn** | **1.9.0** (latest, verified `pip index`) | NEW in route (numpy is already a shot-timeline dep but NOT a clustering lib) | AgglomerativeClustering (cosine, average linkage) over the DINOv2 embedding matrix → cluster ID per crop = registry entry ID | Built-in `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)` produces deterministic, interpretable clusters whose count is data-driven (no K to guess). Hand-rolling cosine linkage on numpy is a 50-line trap. |

**Why agglomerative + cosine, not DBSCAN:**

| Algorithm | Verdict | Reason |
|---|---|---|
| **AgglomerativeClustering** (cosine, average linkage, distance_threshold) | **RECOMMENDED** | Small N (≤ a few hundred crops per single video); deterministic; produces clean dendrogram for human review (matches "human-in-the-loop" milestone Constraint); `distance_threshold` lets the operator tune precision/recall at review time. Average linkage is the standard choice for re-id (resists single-linkage chaining). |
| DBSCAN | Acceptable alternative | Its "noise" label (`-1`) is useful for flagging one-off crops that shouldn't enter the registry. Could be offered as `--clusterer dbscan` flag. Slightly more sensitive to `eps` than agglomerative is to threshold. |
| Custom numpy cosine thresholding | Rejected | Reinvents the wheel; no dendrogram; no scikit-learn diagnostics. |

**Threshold starting point:** cosine distance `τ ≈ 0.30` (≈ 0.70 cosine similarity) is a commonly-cited starting point for DINOv2 instance re-id; expect per-show tuning. Flag in PITFALLS.md.

### 4. Character/Prop Image Extraction — **ROUTE owns it; shot-timeline only consumes JSON**

The milestone context asks: *"just consuming route output? or local Pillow/crop?"*

**Answer: just consume route output.** SAM3 segmentation already runs in the comfyui-side comfyui-primary container (`SAM3Segment` node, `output_mode="Merged"`, verified in `shot_analysis_driver.py:91-100`). The natural v1.1 extension is a NEW route (e.g. `POST /api/v1/production/character-reid`) that:

1. Reuses SAM3 to mask the main subject per shot (already deployed infra).
2. Applies the mask to first/last frames (Pillow `Image.crop` on the bbox — trivial, **route-side**).
3. Runs DINOv2 over each crop.
4. Agglomerative-clusters → returns `{characters: [{id, name?, crop_paths, shot_ids, embedding}], props: [...]}`.

shot-timeline's only "image" responsibility is reading the route's JSON response and **writing crop file paths into `characters.json`/`props.json`**. shot-timeline does NOT do `Image.open` itself unless it needs to thumbnail crops for HTML display (and Pillow 12.2.0 is ALREADY a shot-timeline dep for that — `detectors/detect_v3b.py` imports `PIL.Image`).

| Surface | Lib | Status |
|---|---|---|
| Crop extraction (mask → bbox → PNG) | Pillow 12.2.0 (route-side) | already a dep in shot-timeline; route will have it via the comfyui venv |
| Thumbnail rendering for HTML gallery | Pillow 12.2.0 (shot-timeline side, IF we render crops into timeline.html) | already installed; no new dep |

### 5. JSON Schema v2 Authoring/Validation — **jsonschema 4.26.0 (already used)**

| Technology | Version | Status | Purpose | Why |
|---|---|---|---|---|
| **jsonschema** (Draft 2020-12) | **4.26.0** (latest, verified) | ALREADY USED (`scripts/export_asset.py:113` lazy-imports `Draft202012Validator`) | Author + validate the v2 schemas (`characters.schema.json`, `props.schema.json`, enriched `prompts.schema.json`, bumped `asset.schema.json`) | No new tooling. Same inline-validator pattern as v1.0. |

**No new validation tooling.** The existing pattern in `scripts/export_asset.py:106-126` (load schema JSON → `Draft202012Validator` → `iter_errors` → fail loud with path) is the contract. v1.1 adds two new schemas following the same pattern; `spec/validate.py` SMOKE_SHAPES gets the two new files appended.

**Do NOT add:** `fastjsonschema` (compile-time optimization — premature for ~6 schemas); `pydantic` (wrong tool — schemas are data contracts not runtime models, and the project has survived without it).

### 6. Canvas Consumer Side — **Reuse existing `asset` node, NO Zod bump**

LIVE-verified against `kais-aigc-platform/src/lib/canvasAssetSchema.ts:76-94` and `packages/infinite-canvas/src/types/canvas.ts:57,71-96`:

- `CanvasNodeType` already includes `'asset'`.
- `canvasAssetSchema.ts:82` ALREADY accepts `assetType: z.string().min(1, "asset node requires assetType (character|scene|prop)")` — the docstring literally lists **`character|scene|prop`**.
- `AssetNodeData` (types/canvas.ts:71-96) already has `characterId`, `viewAngle`, `viewGroup`, `isPrimaryView` fields specifically for character multi-view registries.

**Implication:** the v1.1 character/prop registry needs **NO new node type, NO Zod schema bump** on the canvas side. The `extractShotTimelineArtifacts` helper in `src/routes/canvas/v2/import-from-dir.ts:943` just needs to emit additional `RawArtifact` entries with `canvasType: "asset"`, `extra.assetType: "character"` (or `"prop"`), sourced from the new `characters.json` / `props.json`.

| Surface | Change |
|---|---|
| `CanvasNodeType` union | **NONE** — `'asset'` already there |
| `canvasAssetSchema.ts` Zod | **NONE** — `assetType: "character"\|"prop"` already accepted |
| React renderers | **NONE** — AssetNode already renders character/prop; reuse 5 existing renderers (consistent with v1.0 "no custom renderer" decision) |
| `extractShotTimelineArtifacts` | **EXTEND** — add `asset` artifact entries for each character/prop; add zone→asset child edges; optionally add `reference` edges from each `storyboard` to its referenced `character`/`prop` nodes (the prompt reference system made visible) |
| `SHOT_TIMELINE_KNOWN_VERSIONS` (import-from-dir.ts:898) | **APPEND `"1.1"`** (or `"2"` — see Schema Bump Nuance below) — currently `new Set(["1"])`; bumping silences the graceful-degrade warn for the new version |

---

## Installation

```bash
# ── shot-timeline: NEW runtime deps for v1.1 ──────────────────────────────
# httpx is ALREADY installed in the runtime env (verified:
#   /home/kai/.local/lib/python3.12/site-packages/httpx 0.28.1)
# If/when shot-timeline grows a requirements.txt / pyproject.toml (it has none
# today — CLAUDE.md "No package manifest"), pin:
pip install "httpx>=0.28.1"
# (OPTIONAL, only if timeline.html renders character/prop crops inline —
#  Pillow is ALREADY installed: 12.2.0)
# pip install "pillow>=12.2.0"   # already there

# ── kais-aigc-platform route: NEW deps for the re-id route ────────────────
# (NOT installed in shot-timeline env; lives in route's venv)
pip install "transformers>=5.14.1" "scikit-learn>=1.9.0"
# DINOv2 weights cached via huggingface_hub on first call (~346MB to
# ~/.cache/huggingface) — same pattern as existing Whisper large-v3 download.

# ── DEFERRED (v1.2 if face-accuracy matters more): InsightFace ────────────
# pip install "insightface>=1.0.1" "onnxruntime-gpu>=1.27.0"
# Note antelopev2/buffalo_l are NON-COMMERCIAL research-licensed.
```

**Explicitly NOT installed in shot-timeline (the boundary):**
`torch`, `transformers`, `insightface`, `open-clip-torch`, `openai-clip`, `scikit-learn`, `timm`, `ultralytics`, `onnxruntime-gpu`, DINOv2/ArcFace weights. **All heavy ML stays behind the HTTP route in kais-aigc-platform.**

---

## Integration Points into shot-timeline (LIVE-verified against `run_pipeline.py`)

The current pipeline is 6 steps (`run_pipeline.py:1-30` docstring + `main():332-360`): `ensure_h264 → step_detect → step_separate → step_transcribe → step_timeline → step_export`. Two new steps slot in:

### New step A: `step_semantic` — between `step_transcribe` and `step_timeline`

```
after:    output/<stem>/transcript.json + shots.json + frames.json
call:     POST {ANALYSIS_URL}/api/v1/production/shot-analysis
          body: {video: <container-visible path>, shots: shots.json content,
                 semantic: true, subject: true}
produce:  output/<stem>/prompt_analysis.json  (the route's shot_XXX.json payload)
          + MERGE into output/<stem>/prompts.json (enriches camera/action/scene/
          lighting/style fields; preserves any pre-existing manual fields)
cache:    os.path.exists(prompt_analysis.json) → skip; --force clears
flags:    --skip-semantic  (new)
          --analysis-url   (new; default http://localhost:3000 or env ANALYSIS_URL)
graceful-degrade: route down → return None → prompts.json untouched → continue
```

Field mapping (verified against actual `shot_003.json` at `/mnt/agents/output/gpu1/shot_analysis/shot_003.json`):

| `prompts.json` field | Source in shot-analysis response |
|---|---|
| `camera` | `semantic.shot_scale` + `semantic.camera_primitive` + `geometry.primitive` + `geometry.speed` (e.g. "中景 / follow / fast") |
| `action` | `semantic.subject_motion` + `subject.direction_cn` (e.g. "飞虫持刀向前飞行 / 向右") |
| `lighting` | `semantic.lighting` (e.g. "雾气弥漫") |
| `style` | `semantic.lens_feel` (e.g. "normal") |
| `scene` | *(no direct source — leave for manual/Qwen-VL extension; do NOT fabricate)* |
| `subject` | *(deferred to re-id step — filled in step_reid from registry)* |

### New step B: `step_reid` — after `step_semantic`, before `step_timeline`

```
after:    shots.json + frames.json (first/last frames) + prompt_analysis.json
call:     POST {ANALYSIS_URL}/api/v1/production/character-reid   (NEW route)
          body: {video, shots, frames: frames.json content}
produce:  output/<stem>/characters.json   (NEW — registry of cross-shot characters)
          output/<stem>/props.json        (NEW — registry of cross-shot props)
          + PATCH prompts.json: each prompt gets character_refs[]/prop_refs[] IDs
cache:    os.path.exists(characters.json) → skip; --force clears
flags:    --skip-reid  (new)
graceful-degrade: route down → no characters.json/props.json → prompts.json
                  reference arrays stay empty → continue
```

### `step_export` and `export_asset.py` (verified at `scripts/export_asset.py`)

`step_export` already takes a hardcoded 5-tuple of data JSON paths (`run_pipeline.py:220-227`). For v1.1:

- `build_asset_dict` (`export_asset.py:129-187`) gets the `schema_version` bump + two new optional `data.characters`/`data.props` entries **only written when the files exist** (graceful-degrade if step_reid was skipped).
- The 5-required-JSON guard at `export_asset.py:218-232` stays as-is for `shots/audio_analysis/transcript/frames/prompts`; `characters.json`/`props.json` are OPTIONAL (not added to the required list — that would break graceful-degrade).
- The 4 canonical-symlink set (`video.mp4`, `stems/{vocals,drums,other}.wav`) stays. Character/prop crop images live as a NEW media category under `media.characters[i].crop_path` / `media.props[i].crop_path` — relative paths, served by the same `scripts/serve.py` Range-aware server.

### CLI flag additions (`run_pipeline.py:main`)

```
--analysis-url <url>     default env ANALYSIS_URL or http://localhost:3000
--skip-semantic          skip step_semantic (route-driven prompt enrichment)
--skip-reid              skip step_reid (character/prop registry)
--analysis-timeout <sec> default 960 (just over route's 900s ceiling)
```

These mirror the existing `--skip-detect/--skip-separate/--skip-transcribe/--skip-export` kebab-flag convention (CLAUDE.md "CLI Argument Conventions").

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| **httpx** for shot-timeline→route | stdlib `urllib.request` | Only if the project formally adopts "zero third-party HTTP deps ever" — but the existing driver's urllib pattern (for comfyui on localhost) does NOT justify extending to remote-service calls. Use urllib only if you're willing to hand-roll timeout/retry/JSON-error-parsing. |
| **DINOv2 ViT-B/14** for re-id | InsightFace antelopev2 | Wait for v1.2 if actual re-id precision on frontal faces proves insufficient AND the show is face-heavy. Then add as **fusion** (DINOv2 universal + ArcFace face-only confirmation), not replacement. Beware non-commercial license. |
| **DINOv2 ViT-B/14** (768-d, 346MB) | DINOv2 ViT-L/14 (1024-d, ~1.2GB) | Only if re-id quality on B/14 is observably too low at v1.1 review. L/14 doubles GPU memory and download size for marginal gains; B/14 is the documented sweet spot. ViT-S/14 too weak. |
| **AgglomerativeClustering** | DBSCAN | If the show produces many one-off "noise" crops that shouldn't enter the registry, DBSCAN's `-1` label is cleaner. Offer as a flag. |
| **transformers** for DINOv2 loading | `torch.hub.load(...)` or `timm` 1.0.28 | `transformers` is the canonical HF path with the cleanest AutoModel API and is almost certainly already in the route's venv (Qwen3-VL uses it). `timm` adds an unrelated dep. `torch.hub` requires facebookresearch/dinov2 git URL — works but bypasses HF cache and the existing Qwen3-VL/transformers ecosystem. |
| **scikit-learn AgglomerativeClustering** | numpy-only cosine thresholding | Never for this milestone. Reinvents linkage, gives no dendrogram for human review, no diagnostics. |

---

## What NOT to Use (the boundary, made explicit)

| Avoid (in shot-timeline) | Why | Lives Where Instead |
|---|---|---|
| `torch` / `transformers` / `timm` / `insightface` / `open-clip-torch` / `openai-clip` | Heavy ML; violates "shot-timeline stays thin" + "don't touch shot-timeline algorithms" decisions; multi-GB model downloads; GPU dependency shot-timeline doesn't own | kais-aigc-platform route (re-id driver) — already has comfyui+GPU infra |
| `scikit-learn` | Clustering is the route's job; even if shot-timeline wanted to re-cluster, embeddings never leave the route (only registry IDs come back) | kais-aigc-platform route |
| DINOv2 / ArcFace / SAM3 weights (any model `.pt`/`.safetensors`) | Same as above; shot-timeline has no GPU ownership model | route + comfyui-primary container |
| `pydantic` | Project has zero pydantic usage; jsonschema Draft 2020-12 is the contract surface; adding pydantic now would split validation | — (don't add anywhere) |
| `fastjsonschema` | Premature compile-time optimization for 6-8 schemas | — |
| A new canvas node type (e.g. `'character'`, `'prop'`) | `CanvasNodeType='asset'` + `assetType='character'\|'prop'` already exists in `canvasAssetSchema.ts:82`; a new node type would force a contract bump + new renderer, violating "no custom renderer / no contract bump" decisions | reuse existing `asset` node |
| Any retry framework (`tenacity`, `stamina`) | httpx `HTTPTransport(retries=N)` is enough at this scale | — |

---

## Stack Patterns by Variant

**If the route is reachable (`--analysis-url` resolves, route returns 200):**
- `step_semantic` POSTs shots → enriches prompts.json; `step_reid` POSTs frames → produces characters.json + props.json
- asset.json exports at `schema_version: "1.1"` with `data.characters` + `data.props` populated

**If the route is unreachable (DNS fail, connection refused, 5xx after retries, timeout):**
- Both new steps print `[warn] analysis route unavailable, graceful-degrade: <reason>` and return None
- prompts.json keeps whatever was there (manual `part_*.json` merge output or empty)
- characters.json/props.json are NOT written
- asset.json STILL exports at `schema_version: "1.1"` but with `data.characters`/`data.props` OMITTED (they're optional in v1.1 schema — old v1.0 consumers already gracefully-degrade on unknown versions)

**If only the re-id route is down but semantic works:**
- prompts.json gets enriched, characters.json/props.json absent; prompts' `character_refs[]`/`prop_refs[]` stay empty; `subject` field filled with Qwen's `subject_motion` text instead of a registry reference

**If shot-timeline is run on a box with no GPU at all:**
- Everything still works — shot-timeline itself never touches GPU; route-side ML is on the route's host

---

## Version Compatibility

Verified live against both repos + PyPI on 2026-07-24:

| Package | Version (this research) | Compatible With | Notes |
|---|---|---|---|
| `httpx` | 0.28.1 | Python 3.12.3 (env) | Already installed; `HTTPTransport(retries=...)` available |
| `jsonschema` | 4.26.0 | Python 3.12 | Draft 2020-12 Validator; already used |
| `pillow` | 12.2.0 | Python 3.12 | Already installed; `PIL.Image` used in detect_v3b.py |
| `transformers` | 5.14.1 | torch 2.6.0+cu124 (env) | Route side; loads `facebook/dinov2-base` |
| `scikit-learn` | 1.9.0 | numpy 2.2.6 (env) | Route side; `AgglomerativeClustering(metric="cosine")` supported |
| `facebook/dinov2-base` (HF weights) | stable since 2023 | transformers ≥4.31 (we have 5.14.1) | 768-d pooler_output, ViT-B/14, ~346MB |
| `zod` (canvas consumer) | 3.25.76 (infinite-canvas) / 4.3.5 (backend) | existing | NO bump needed — `assetType` already accepts character/prop |
| `express` (route host) | 5.2.1 | existing | shot-analysis route pattern proven; new re-id route mirrors it |

---

## Schema Bump Nuance — Flag for Planner

`PROJECT.md` says: *"v1.1 把 schema_version 升到 `"2"`"*. **This contradicts the project's own SPEC rule**, verified at `spec/schemas/asset.schema.json:7`:

> "New field = minor version bump (old consumers degrade gracefully). Breaking change (rename, semantic shift, removal) = major bump"

Adding `characters.json` + `props.json` + enriching `prompts.json` is **additive** — pure new fields, no rename/semantic-shift/removal. Per the project's own rule this is a **minor bump → `schema_version: "1.1"`**, NOT `"2"`.

LIVE verification of the consumer's graceful-degrade behavior (`src/routes/canvas/v2/import-from-dir.ts:892-898`):
```ts
const SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"]);
// ...
if (!SHOT_TIMELINE_KNOWN_VERSIONS.has(version)) {
  console.warn(`[v2/import] ShotTimelineAsset schema_version="${...}" not in known set ... — graceful-degrade (SPEC §4)`);
}
```
The consumer does NOT reject on unknown version — it warns and continues. So either `"1.1"` or `"2"` is functionally safe at the canvas side. **But picking `"2"` (a) violates the project's stated semver-lite rule and (b) burns the major-bump escape hatch for a future genuinely-breaking change.**

**Recommendation to planner:** ship v1.1 as `schema_version: "1.1"`. Reserve `"2"` for the first genuinely breaking change (e.g. renaming `shots` → `segments`, removing `bass.wav`-tolerant fallback, etc.). Update PROJECT.md's `"2"` wording to `"1.1"` at phase 1.

If the planner insists on `"2"`, document it explicitly in the SPEC.md migration section as an exception to the semver-lite rule (otherwise the SPEC contradicts itself).

---

## Gaps / Open Questions for Phase-Specific Research

1. **`character-reid` route does not yet exist.** Only `shot-analysis` exists (verified). A new route must be built in kais-aigc-platform (`src/routes/production/character-reid/`) mirroring the `shot-analysis` thin-wrapper pattern (`execFileSync` Python driver). Phase creating that route needs its own research for the SAM3-crop→DINOv2→cluster driver script.
2. **Container path plumbing for frames.json.** `frames.json` carries base64 data URIs (verified, `gen_timeline_html.py`), NOT filesystem paths. The re-id route needs actual frame images to mask. Either: (a) shot-timeline writes first/last frame PNGs to disk as part of `step_reid` and ships their paths; or (b) re-id route re-extracts frames via ffmpeg from `--video`. Option (b) matches the existing `shot-analysis` route's `docker cp` video-then-extract pattern (`shot-analysis/index.ts:53-77`). Recommend (b) — keeps shot-timeline's I/O surface unchanged.
3. **DINOv2 cosine threshold tuning.** τ=0.30 is a literature starting point, not validated on 《小江湖》-style animation. Phase that wires the route should A/B against hand-labeled ground truth on one episode; flag in PITFALLS.md.
4. **Two unmerged comfyui branches.** `feat/shot-geometry-nodes` + `feat/shot-analysis-route` must merge before v1.1 ships (milestone Constraint). The route is unreachable until they do. Planner should sequence phase 1 after those merges (or flag the dependency).

---

## Sources

- **LIVE-verified code in this repo:** `run_pipeline.py`, `scripts/export_asset.py`, `spec/schemas/asset.schema.json`, `spec/schemas/prompts.schema.json`, `prompts/merge_prompts.py`
- **LIVE-verified code cross-repo (`kais-aigc-platform`):** `src/routes/production/shot-analysis/index.ts`, `src/routes/production/shot-analysis/_shared/config.ts`, `scripts/shot-analysis/shot_analysis_driver.py`, `scripts/shot-analysis/README.md`, `src/lib/canvasAssetSchema.ts`, `packages/infinite-canvas/src/types/canvas.ts`, `src/routes/canvas/v2/import-from-dir.ts`
- **LIVE sample output:** `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` (the actual route response shape)
- **LIVE env probe:** `/usr/bin/python3` 3.12.3 + `pip index versions …` for every recommended version
- PyPI currency (HIGH confidence): httpx 0.28.1, scikit-learn 1.9.0, transformers 5.14.1, insightface 1.0.1, open-clip-torch 3.3.0, timm 1.0.28, onnxruntime-gpu 1.27.0, jsonschema 4.26.0
- [facebook/dinov2-base on Hugging Face](https://huggingface.co/facebook/dinov2-base) — model card, ViT-B/14 self-supervised, 768-d
- [DINOv2 in HF Transformers (official docs)](https://huggingface.co/docs/transformers/en/model_doc/dinov2) — `AutoModel` + `pooler_output` for image embeddings
- [DINOv2 official repo (facebookresearch/dinov2)](https://github.com/facebookresearch/dinov2) — ViT-B/14 checkpoint, re-id / image-matching use cases documented
- [InsightFace model zoo & guide](https://www.insightface.ai/guides/choose-face-recognition-model-and-evaluate) — buffalo_l vs antelopev2 (both ArcFace, 512-d, 112×112 input); **non-commercial research license**
- [immich-app/antelopev2 mirror](https://huggingface.co/immich-app/antelopev2) / [buffalo_l mirror](https://huggingface.co/immich-app/buffalo_l) — provenance for the ONNX packs
- [ShotTimelineAsset graceful-degrade rule](file:///data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json) — SPEC §4, semver-lite `(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`
