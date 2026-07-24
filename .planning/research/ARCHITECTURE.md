# Architecture Research: v1.1 Integration with Existing 2-Repo System

**Domain:** Loosely-coupled producer (Python CLI) / consumer (React-Flow canvas) ecosystem adding ML-route-dependent semantic enrichment + cross-shot re-id registry + contract minor bump.
**Researched:** 2026-07-24
**Confidence:** HIGH (all claims verified against live source — `run_pipeline.py:89-268`, `export_asset.py:129-187`, `import-from-dir.ts:880-1140`, `canvasAssetSchema.ts:51-119`, `routes/production/shot-analysis/index.ts`, `AssetNode.tsx`, real `shot_003.json` output)

---

## Executive Summary

The five v1.1 feature threads (route-wired prompt filling, characters/props data files, re-id registry, prompt references, canvas character/prop nodes) integrate cleanly into the existing v1.0 architecture **without** breaching any of the locked constraints (loose coupling, no core-algorithm churn, minor-bump-only contract, no custom renderer). The key enabler is that the v1.0 schema was deliberately designed with `additionalProperties: false` + semver-lite + graceful-degrade runtime — the *exact* mechanism SPEC §4 documents for this kind of additive minor bump.

Three concrete discoveries reshape the plan:

1. **Canvas character/prop rendering needs NO contract bump and NO new renderer.** `canvasAssetSchema.ts:76-94` already types `asset` nodes with `assetType: z.string().min(1)` (any non-empty string), and `AssetNode.tsx:123,171` falls back to `📦` for any unknown assetType. The v1.0 design reserved `asset` as a generic media-bearing primitive precisely so that character/prop nodes can be emitted as `type: "asset"` + `assetType: "character"|"prop"` with zero Zod change.
2. **The consumer has ONE singular version gate** — `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"])` at `import-from-dir.ts:898`. v1.1's new character/prop emission code MUST be gated on adding `"2"` here; if v2 manifests hit a consumer that still has `Set(["1"])`, the new code path is silently skipped (only a warn fires per SPEC §4 graceful-degrade). This is THE integration seam to plan around.
3. **The cinematography route's output shape maps near-1:1 onto the existing `prompts.schema.json` facets.** Verified from `/mnt/agents/output/gpu1/shot_analysis/shot_003.json`: `semantic.shot_scale` → `camera`, `semantic.camera_primitive` → `camera` (movement), `semantic.subject_motion` → `action`, `semantic.lighting` → `lighting`, `geometry.primitive/speed` → `camera` (auxiliary). The v1.0 prompts schema was designed against this exact shape.

The biggest architectural risk is **route dependency** (PROJECT.md:81): shot-timeline must produce a valid asset even when the kais-aigc-platform analysis routes are unreachable. This is solved by reusing the v1.0 pattern (`step_timeline`'s missing-input degrade at `gen_timeline_html.py:1051-1059`) and extending it — a NEW `step_analyze` that emits a minimal-but-schema-valid `prompts.json` (empty strings for the 7 required facets) when the route is down.

---

## 1. Existing Architecture (Live-Verified Baseline)

### Producer pipeline — `run_pipeline.py` step_* sequence

```
step 1/6: ensure_h264 (AV1 transcode guard)
step 2/6: step_detect       → shots.json
step 3/6: step_separate     → audio_analysis.json + stems/
step 4/6: step_transcribe   → transcript.json
step 5/6: step_timeline     → timeline.html (reads frames.json + shots + audio + transcript)
step 6/6: step_export       → asset.json + canonical symlinks (requires prompts.json present)
```

**Caching/idempotency pattern (verified):** Every `step_*` checks `os.path.exists(out)` first; `--skip-*` flags short-circuit; `--force` clears; `step_export` adds a TOCTOU-safe mtime check + video-identity sidecar (`run_pipeline.py:174-268`). Subprocess invocation pattern is uniform: `subprocess.run([sys.executable, str(HERE / "<dir>" / "<script>.py"), ...args], check=True)`.

**Critical integration fact:** `prompts.json` is a required asset.json data file (`asset.schema.json:61` + `export_asset.py:218-232`) but is NOT produced by any current pipeline step. `prompts/merge_prompts.py` is a separate off-pipeline tool. **v1.1 must introduce a producer for prompts.json inside the pipeline** — this is the natural home for `step_analyze`.

### Consumer ingestion — `import-from-dir.ts:extractShotTimelineArtifacts`

```
POST /api/canvas/v2/import-from-dir  body={workdir, projectId, episodesId, mode}
    ↓
scanWorkdirForArtifacts (lines 1320-1354): detect asset.json + asset_type==="shottimeline"
    ↓ SHORT-CIRCUIT 13-phase scan
extractShotTimelineArtifacts (lines 943-1140):
    • schema_version graceful-degrade check (KNOWN_VERSIONS gate)
    • Read 5 data JSON in parallel
    • ffprobe video.mp4 → resolution
    • Build RawArtifact[] with heterogeneous canvasType override (Solution A):
        - N storyboard children (from shots.json; thumbnail = frames.json.first_frame)
        - 3 audio children (vocals/drums/other, shot_id="collection")
        - 1 video child (master)
    • buildPhaseTree("p13", artifacts) → 1 zone + 1 summary + N+4 artifact nodes
    • Override zone label ← manifest.source.video_filename
    • Emit N-1 sequence edges between storyboard children (by shot_id asc)
    ↓
appendAndSync (event store; bypasses save-v2 FlowLinkV2Schema strip)
```

**The 5 child-node synthesis pattern (verified `import-from-dir.ts:1015-1069`):** synthetic fields are tagged `__synthetic_fields: ["shot_id","engine"]` etc. so reviewers can distinguish them. Storyboards carry `shot_type: "scene"` literal (Zod does not enum-lock). Audio/video carry `engine: "shot-timeline"` provenance + collection-level `shot_id: "collection"` sentinel.

### Contract authority — 6 schemas + SPEC.md + harness

| File | Role |
|------|------|
| `spec/schemas/{shots,audio_analysis,transcript,frames,prompts,asset}.schema.json` | Machine-checkable authority; all `additionalProperties: false` |
| `spec/SPEC.md` | Human-readable overview + §4 graceful-degrade rule + §6 media conventions |
| `scripts/export_asset.py:106-127` | Producer-side inline `Draft202012Validator` (never subprocesses to `spec/validate.py` because SMOKE_SHAPES excludes `asset`) |
| `scripts/verify_contract.py` | Cross-repo regression harness — 3 modes (producer/consumer/e2e), 6-shape validator, self-test for fail-loud |
| Consumer-side `import-from-dir.ts:892-898` | `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"])` — singular version gate |

---

## 2. v1.1 Integration Map — Per Feature

### Feature 1: NEW pipeline stage calling analysis routes (`step_analyze`)

**Integration point:** Insert as step 5 of 7, BETWEEN `step_transcribe` (current 4/6) and `step_timeline` (current 5/6). Rationale: timeline generator already consumes prompts (`gen_timeline_html.py` reads `--prompts`), and export requires prompts.json to exist. The new step REPLACES the current off-pipeline `prompts/merge_prompts.py` path.

**New pipeline sequence (v1.1):**
```
1/7: ensure_h264
2/7: step_detect        → shots.json
3/7: step_separate      → audio_analysis.json
4/7: step_transcribe    → transcript.json
5/7: step_analyze  ★NEW → prompts.json  (HTTP client → kais-aigc-platform route)
6/7: step_timeline      → timeline.html
7/7: step_export        → asset.json
```

**NEW components (producer repo):**
- `analysis/call_shot_analysis.py` — NEW module. Takes `shots.json` + `video` path, POSTs to `${ANALYSIS_URL}/api/v1/production/shot-analysis` (route exists, body shape verified at `shot-analysis/index.ts:27-35`), receives `{shots: [...]}`, maps semantic fields onto prompts schema:
  - `semantic.shot_scale` + `geometry.primitive` (e.g. "pan_right") + `geometry.speed` → `prompts[i].camera`
  - `semantic.subject_motion` + `subject.direction_cn` → `prompts[i].action`
  - `semantic.lighting` → `prompts[i].lighting`
  - Heuristic / Qwen text → `prompts[i].scene`, `subject`, `style`
  - Synthesized `prompt_text` (concatenation of facets)
- `run_pipeline.py:step_analyze` — NEW step function mirroring `step_transcribe` shape.
- CLI flags: `--analysis-url` (default `http://localhost:3000`), `--skip-analyze`, `--analysis-shot-range LO HI`, `--analysis-semantic`, `--analysis-subject`, `--analysis-timeout` (default 900s matching route's `maxBuffer` + driver's 600s timeout).

**MODIFIED components (producer repo):**
- `run_pipeline.py:main` — add steps sequence label update (6/6 → 7/7), `--force` cleanup adds `prompts.json` to the unlink list (currently NOT there because prompts is external), wire `step_analyze` between `step_transcribe` and `step_timeline`.
- `run_pipeline.py` argparse — add the 6 new flags above.

**Caching strategy:** Mirror `step_transcribe`. Idempotent on `prompts.json` existence; `--skip-analyze` returns cached path or `None`; `--force` unlinks. Cache key = `shots.json` mtime + route URL (if URL changes, re-run). No video-identity sidecar needed (prompts derived from shots + frames, not video bytes directly — though video is sent to route, the result is deterministic per shot slice).

**Graceful-degrade path (route unreachable):**
- Catch `(urllib.error.URLError, ConnectionRefusedError, TimeoutError, HTTPError ≥ 500)` from the route call.
- Log `[5/7] [warn] shot-analysis route unreachable ({reason}); writing minimal prompts.json with empty facets`.
- Write a schema-valid `prompts.json` with all 7 required facets as empty strings + a literal `prompt_text: ""`. This satisfies `export_asset.py:218` (file exists) + `prompts.schema.json:10-23` (all required keys present, empty strings pass `type: string`).
- `step_export` succeeds; asset.json marks v1 still (no cinematography enrichment). v1.1 contract bump is independent — see Feature 4.
- This is the explicit PROJECT.md:81 constraint made operational.

**HTTP client choice:** Use stdlib `urllib.request` (matches `shot_analysis_driver.py:114-120` precedent + avoids new dependency). No `requests` library.

**Data flow (end-to-end):**
```
shots.json + video.mp4 + frames.json
    ↓ analysis/call_shot_analysis.py
POST /api/v1/production/shot-analysis
    body: {video: "/path/in/container", shots: "...", semantic: true, subject: true, ...}
    ↓
kais-aigc-platform driver (already P0-P4 verified 2026-07-23):
    ComfyUI ShotGeometryLK + AILab_QwenVL_Advanced + SAM3Segment+SubjectMotionResidual
    → ShotJSONMerge → /mnt/agents/output/gpu1/shot_analysis/shot_XXX.json
    ↓ route aggregates → returns {shots: [shot_001.json, shot_002.json, ...]}
    ↓
Map semantic/geometry fields → prompts[].camera/action/scene/lighting/style/subject/prompt_text
    ↓
prompts.json written (atomic tmp + os.replace per `export_asset.py:308-313`)
```

**Caveate (must flag to planner):** The route expects `shots` to be a path readable from the container, and `video` to be container-visible (`shot-analysis/index.ts:53-77`). For shot-timeline running on the host, this means either (a) shot-timeline must run on the same docker network / mount `/mnt/agents/output/gpu1/`, or (b) the route's `docker cp` branch stages the video. This is a deployment-time dependency — the `--analysis-url` alone is insufficient; an `--analysis-video-mount-mode {container, host-staged}` flag may be needed.

---

### Feature 2: characters.json + props.json as NEW ShotTimelineAsset data files

**NEW components (producer repo):**

- `spec/schemas/characters.schema.json` — NEW. Proposed shape (array, mirrors `frames.schema.json` style):
  ```json
  [
    {
      "id": "char_001",                  // string ID, registry-stable
      "label": "少女",                    // human-readable
      "assetType": "character",           // const enum
      "first_seen_shot_id": 1,            // back-ref to shots.json
      "appearance_shots": [1, 5, 8],      // all shots where this entity appears
      "thumbnail": "characters/char_001.png",  // canonical media path
      "description": "白色衣裙少女..."    // optional
    }
  ]
  ```
- `spec/schemas/props.schema.json` — NEW. Same shape, `assetType: "prop"`.
- `scripts/export_asset.py` — MODIFIED `build_asset_dict` to add `data.characters` + `data.props` (optional, only emitted if files exist) and `media.characters` + `media.props` (canonical dir paths). The 5-JSON required guard at `export_asset.py:218-232` must NOT be extended to characters/props (they're optional).

**MODIFIED components (producer repo):**
- `spec/schemas/asset.schema.json` — EXTEND `data` properties to add optional `characters` + `props` (pattern: same path regex as existing 5). EXTEND `media` properties to add optional `characters` + `props` (pattern: `^(?!.*\.\.)([^/]+/)*characters/[^/]+\.(png|jpg|jpeg|webp)$`). Bump `$comment` schema_version mention. **Both must be OPTIONAL** (not in `required`) — per SPEC.md:144 "Add required field = major bump"; v1.1 is minor-only.
- `spec/SPEC.md` — add §5.6 Characters and §5.7 Props subsections; update §2 directory layout; update §3 manifest field table; add §4 Changelog entry for v2.

**Canonical media naming (NEW convention):**
```
<asset-root>/
├── characters/
│   ├── char_001.png        # first-seen thumbnail
│   ├── char_002.png
│   └── ...
├── props/
│   ├── prop_001.png
│   └── ...
```
Pattern (proposed for asset.schema.json): `^(?!.*\.\.)([^/]+/)*(characters|props)/[^/]+\.(png|jpg|jpeg|webp)$`.

**asset.json `data` + `media` extension (v2 manifest):**
```json
{
  "schema_version": "2",
  "asset_type": "shottimeline",
  ...
  "data": {
    "shots": "shots.json",
    ...5 existing...,
    "characters": "characters.json",     // OPTIONAL — absent in v1 manifests
    "props": "props.json"                 // OPTIONAL — absent in v1 manifests
  },
  "media": {
    "video": "video.mp4",
    "stems": {...},
    "characters": "characters/",          // OPTIONAL — dir prefix
    "props": "props/"                     // OPTIONAL — dir prefix
  }
}
```

---

### Feature 3: Re-ID registry data flow (the most complex new pipeline)

**End-to-end flow:**

```
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE A: subject extraction                                          │
│  ─────────────────────────                                            │
│  inputs:  frames.json (first/last per shot) + shots.json             │
│  process: NEW route POST /api/v1/production/subject-segmentation     │
│           (SAM3 on first/last frames → masks + crops)                │
│  output:  output/<video>/subjects/shot_001/char_0.png, prop_0.png... │
│           + subjects.raw.json (crops per shot, no IDs yet)           │
└──────────────────────┬───────────────────────────────────────────────┘
                       ↓
┌──────────────────────┴───────────────────────────────────────────────┐
│  STAGE B: embedding + clustering                                      │
│  ──────────────────────────────                                       │
│  inputs:  subjects.raw.json + crop images                            │
│  process: NEW route OR NEW local step                                 │
│           (CLIP/arcface image embedding → cosine sim → HDBSCAN)       │
│  output:  registry.draft.json — clusters w/ provisional IDs          │
│           [{cluster_id, members: [{shot_id, crop_path}], ...}]        │
└──────────────────────┬───────────────────────────────────────────────┘
                       ↓
┌──────────────────────┴───────────────────────────────────────────────┐
│  STAGE C: human review (HITL — PROJECT.md:58,82 mandate)             │
│  ─────────────────────────                                            │
│  inputs:  registry.draft.json + crops                                │
│  process: NEW html/gen_registry_review.py → registry_review.html     │
│           (gallery grid: per-cluster cards with merge/split/rename)  │
│  output:  registry.edits.json (user's merge/split/rename decisions)  │
└──────────────────────┬───────────────────────────────────────────────┘
                       ↓
┌──────────────────────┴───────────────────────────────────────────────┐
│  STAGE D: apply edits → canonical registry                           │
│  ─────────────────────────────                                       │
│  inputs:  registry.draft.json + registry.edits.json                  │
│  process: registry/apply_edits.py                                    │
│  output:  registry.json (final, canonical — IDs stable, labels set)  │
│           + characters.json + props.json (split by type)             │
│           + characters/<id>.png + props/<id>.png (canonical crops)   │
└──────────────────────────────────────────────────────────────────────┘
```

**NEW components (producer repo):**
- `registry/extract_subjects.py` — Stage A. Calls subject-segmentation route. CLI: `--frames`, `--shots`, `--output-subjects-dir`, `--route-url`.
- `registry/cluster.py` — Stage B. Either calls embedding route or does local CLIP clustering (CLIP model already pulled via the canvas v3 branch precedent). Writes `registry.draft.json`.
- `html/gen_registry_review.py` — Stage C. Static HTML generator following `gen_prompts_html.py` pattern (one-shot tool, all data inlined, vanilla JS).
- `registry/apply_edits.py` — Stage D. Reads draft + edits, writes final `registry.json` + `characters.json` + `props.json` + canonical PNGs.
- `spec/schemas/registry.schema.json` — NEW. Captures the draft + final shapes.

**NEW components (aigc-platform repo):**
- `src/routes/production/subject-segmentation/` — NEW route, body `{frames, shots, mode}`. THIN wrapper pattern mirroring `shot-analysis/index.ts` (execFileSync spawn). Calls a new driver script.
- `scripts/subject-segmentation/subject_segmentation_driver.py` — SAM3 invocation per frame.
- Optional: `src/routes/production/subject-embedding/` if embedding is route-side rather than producer-local.

**Pipeline integration — split across stages or one stage?**

Two design options:

**Option A (recommended): One `step_registry` that runs A→B, pauses for review, then user re-invokes pipeline with `--registry-edits` flag for D.**
- Pros: matches v1.0 pattern of one step = one artifact (registry.json); HITL pause is natural checkpoint.
- Cons: pipeline becomes interactive (must pause mid-run).
- Sequence position: **step 6 of 8** — after `step_analyze` (so prompts already exist for cross-ref), before `step_export`.

**Option B: Three separate steps (`step_extract_subjects` / `step_cluster` / `step_apply_edits`).**
- Pros: each step independently cacheable + skippable; non-interactive.
- Cons: pipeline grows to 9 steps; user runs review HTML off-pipeline.

**Recommended sequence with Option A (v1.1):**
```
1/8: ensure_h264
2/8: step_detect
3/8: step_separate
4/8: step_transcribe
5/8: step_analyze         (Feature 1)
6/8: step_registry   ★NEW (Feature 3: A→B; emits draft; fails-loud "run review HTML then re-invoke with --registry-edits")
7/8: step_timeline         (now reads characters.json/props.json for gallery)
8/8: step_export           (now writes v2 asset.json with characters/props)
```

**Re-id precision constraint (PROJECT.md:58,82):** "re-id 不可能 100% 准,必须 human-in-the-loop". The pipeline MUST fail-loud if `registry.edits.json` is missing when `step_registry` runs in `--non-interactive` mode, rather than silently emitting unchecked clusters as canonical IDs.

---

### Feature 4: Prompts referencing registry IDs (schema minor bump)

**MODIFIED `spec/schemas/prompts.schema.json`:**
Add ONE optional field `references`:
```json
{
  ...existing 11 required fields...,
  "references": {                      // OPTIONAL — minor bump
    "type": "array",
    "items": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "id"],
      "properties": {
        "kind": {"enum": ["character", "prop"]},
        "id":   {"type": "string", "pattern": "^(char|prop)_\\d{3}$"},
        "role": {"type": "string"}    // optional: "speaker"|"foreground"|"background"
      }
    }
  }
}
```

**Why this is MINOR not MAJOR (SPEC.md:142-146):**
- Adding optional field → minor bump (SPEC.md:142 "新增字段 → minor bump").
- `additionalProperties: false` is retained — the field is explicitly named in schema.
- v1 consumers ignore `references` (their `prompts.schema.json` doesn't list it, but they're ROBUST to unknown fields per graceful-degrade — wait, this is subtle).

**Critical subtlety — strict schema vs lenient consumer:**
- v1 PRODUCER-side validation would FAIL on a v2 prompts.json containing `references` (because v1 schema has `additionalProperties: false` and doesn't list `references`). v1.1 must ship the new schema first.
- v1 CONSUMER-side processing: consumer never validates prompts.json against a schema (verified — `import-from-dir.ts:1131-1135` `void prompts;  // reserved for future sidecar attach`). It reads it but doesn't act on it. So `references` would be silently ignored by v1 consumer — graceful-degrade satisfied.

**HTML rendering (Feature 5 — shot-timeline side):**
- `html/gen_timeline_html.py` — MODIFIED to render `references` as chips next to the prompt panel: `[👤 少女 (char_001)] [🔧 刀 (prop_001)]`. Inline base64 thumbnails of the referenced entity from `characters.json`/`props.json`.
- Storyboard detail cards get a "References" sub-panel.

---

### Feature 5: Canvas character/prop nodes (NO contract bump, NO new renderer)

**KEY DISCOVERY: zero Zod schema change needed.**

Verified at `canvasAssetSchema.ts:76-94`:
```typescript
asset: withYamlOptional("asset", z.object({
  ...universalRequired,
  label: z.string().min(1, ...),
  assetType: z.string().min(1, "asset node requires assetType (character|scene|prop)"),  // ANY non-empty string
  prompt: z.string().optional(),
  description: z.string().optional(),
  // ...
})),
```
The Zod accepts `assetType: "character"`, `"prop"`, `"scene"`, or any other non-empty string. The v1.0 schema was deliberately permissive on `assetType` enum so that new asset kinds don't require a contract bump.

Verified at `AssetNode.tsx:123,171`: renders any assetType via `typeIcons[data.assetType] || '📦'` fallback. No assetType-specific code paths in the component.

**NEW components (consumer repo, `@kais/infinite-canvas`):**
- `src/routes/canvas/v2/import-from-dir.ts:extractShotTimelineArtifacts` — EXTEND to emit character/prop child nodes when `manifest.data.characters` / `manifest.data.props` exist. Pattern (additive, inside the existing function):
  ```typescript
  // After the existing storyboard/audio/video artifact push (lines 1035-1069):
  const characters = await tryReadJSON(join(workdir, dataPaths.characters ?? "characters.json"));
  for (const ch of (characters ?? [])) {
    artifacts.push({
      label: ch.label,
      output_key: "asset",
      canvasType: "asset",               // reuse existing asset primitive
      filePath: fsToOssUrl(join(workdir, ch.thumbnail)),
      thumbnailUrl: fsToOssUrl(join(workdir, ch.thumbnail)),
      extra: {
        assetType: "character",           // ← Zod already accepts
        shot_id: "collection",            // satisfies no per-asset Zod rule
        label: ch.label,
        __synthetic_fields: ["shot_id"],
        __registry_id: ch.id,             // producer-side stable ID
      },
    });
  }
  // Same loop for props with assetType: "prop"
  ```

**MODIFIED components (consumer repo):**
- `src/routes/canvas/v2/import-from-dir.ts:898` — **THE critical edit**: `const SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1", "2"]);`. Without this edit, v2 manifests trigger graceful-degrade (line 952-958) and the new character/prop emission code below it must be written defensively (either gated on `version === "2"` OR always-run). Recommendation: extend the set + gate the new emission on `version === "2"` to keep v1 manifests producing identical subgraphs (regression-safe).
- `src/components/nodes/AssetNode.tsx:17-19` — minor: add icon mappings `character: '🧑'`, `prop: '🔧'` to `typeIcons` dict. Optional cosmetic only.

**Zero new renderer registration needed** — verified `FlowCanvas.tsx:55-64`:
```typescript
const nodeTypes = {
  default: FallbackNodeComponent,
  script: ScriptNodeComponent,
  asset: AssetNodeComponent,        // ← already registered, handles assetType="character"
  reference: AssetNodeComponent,
  storyboard: StoryboardNodeComponent,
  video: VideoNodeComponent,
  audio: AudioNodeComponent,
  zone: ZoneNodeComponent,
}
```

**Sequence edge emission for characters/props (open design question):**
- Should character nodes connect to the storyboard shots where they appear via `dataType: "reference"` edges? The cross-reference link builder `buildCrossReferenceLinks` (lines 1172-1280) already emits P09→P07 and P10→P09 reference edges by `scene_id`. ShotTimelineAsset could emit character→storyboard reference edges using `character.appearance_shots[]`. This adds N×M edges where N=characters, M=avg appearances.

**Recommendation to planner:** Phase the canvas work — first phase emit character/prop nodes WITHOUT cross-reference edges (matches v1.0 SC-01 scope discipline), second phase add reference edges if the canvas density stays manageable.

---

## 3. NEW vs MODIFIED File Lists (Per Repo)

### Producer repo (`kais-shot-timeline`)

| Status | File | Change |
|--------|------|--------|
| NEW | `analysis/call_shot_analysis.py` | HTTP client → route → prompts.json |
| NEW | `registry/extract_subjects.py` | Stage A: SAM3 subject extraction |
| NEW | `registry/cluster.py` | Stage B: embedding + HDBSCAN |
| NEW | `registry/apply_edits.py` | Stage D: canonical registry build |
| NEW | `html/gen_registry_review.py` | Stage C: HITL review HTML |
| NEW | `spec/schemas/characters.schema.json` | Character registry schema |
| NEW | `spec/schemas/props.schema.json` | Prop registry schema |
| NEW | `spec/schemas/registry.schema.json` | Re-id draft + final shape |
| NEW | `spec/fixtures/minimal/characters.json` | v2 fixture |
| NEW | `spec/fixtures/minimal/props.json` | v2 fixture |
| MODIFIED | `run_pipeline.py` | step_analyze (5) + step_registry (6) inserted; new argparse flags; renumber to 8 steps |
| MODIFIED | `scripts/export_asset.py` | build_asset_dict emits optional data.characters/props + media.characters/props; bump schema_version literal "1" → "2" |
| MODIFIED | `html/gen_timeline_html.py` | Render references chips + character/prop gallery |
| MODIFIED | `spec/schemas/asset.schema.json` | data.characters/props + media.characters/props (optional); bump $comment |
| MODIFIED | `spec/schemas/prompts.schema.json` | Add optional `references` array |
| MODIFIED | `spec/SPEC.md` | §2 layout, §3 fields, §4 v2 changelog, NEW §5.6/5.7, §6 media extensions |
| MODIFIED | `spec/fixtures/minimal/asset.json` | schema_version "1"→"2" |
| MODIFIED | `spec/fixtures/minimal/prompts.json` | Add `references` field |
| MODIFIED | `scripts/verify_contract.py` | SIX_SHAPES extends to 8 shapes (add characters, props); e2e assertions include character/prop node counts |

### Consumer repo (`kais-aigc-platform` — branch `feat/canvas-asset-collection`)

| Status | File | Change |
|--------|------|--------|
| MODIFIED | `src/routes/canvas/v2/import-from-dir.ts` | KNOWN_VERSIONS add "2"; extractShotTimelineArtifacts emit character/prop child nodes (gated on v2) |
| MODIFIED | `src/components/nodes/AssetNode.tsx` | (Optional) typeIcons add character/prop glyphs |
| MODIFIED | `scripts/verify-canvas-shot-timeline.ts` | Add asserts for character/prop child node counts in v2 manifests |

### Consumer repo — analysis route infrastructure (pre-existing branches, must merge)

| Status | File | Change |
|--------|------|--------|
| PRE-EXISTING | `scripts/shot-analysis/shot_analysis_driver.py` | On branch `feat/shot-analysis-route` — vendored, byte-identical to validated driver |
| PRE-EXISTING | `src/routes/production/shot-analysis/index.ts` + `_shared/config.ts` | On branch `feat/shot-analysis-route` — THIN route at `/api/v1/production/shot-analysis` |
| PRE-EXISTING | ComfyUI nodes (ShotGeometryLK, SubjectMotionResidual, ShotJSONMerge, SAM3Segment) | On branch `feat/shot-geometry-nodes` |
| NEW | `src/routes/production/subject-segmentation/` | NEW route for Feature 3 Stage A |
| NEW | `scripts/subject-segmentation/subject_segmentation_driver.py` | NEW SAM3 driver |

---

## 4. Build Order (Dependency-Respecting)

```
Phase A — Route foundation (BLOCKING: everything else depends on this)
─────────────────────────────────────────────────────────────────────
  A.1  Merge feat/shot-geometry-nodes       (ComfyUI custom nodes)
  A.2  Merge feat/shot-analysis-route       (driver + THIN route)
  A.3  Verify POST /api/v1/production/shot-analysis returns shot_XXX.json
       (smoke test from shot-timeline as HTTP client)
  ↓ produces: working cinematography route
  │
  v
Phase B — Producer route-wiring (Feature 1)
─────────────────────────────────────────────────────────────────────
  B.1  Implement analysis/call_shot_analysis.py
  B.2  Add step_analyze to run_pipeline.py (step 5 of 7)
  B.3  Add graceful-degrade path (route-down → minimal prompts.json)
  B.4  Map semantic/geometry fields → prompts schema fields
  ↓ produces: prompts.json auto-filled in pipeline
  │
  v
Phase C — Contract v2 schemas (Feature 2 + 4) — PARALLELIZABLE with Phase D
─────────────────────────────────────────────────────────────────────
  C.1  Write spec/schemas/characters.schema.json + props.schema.json
  C.2  Extend spec/schemas/prompts.schema.json (add optional references)
  C.3  Extend spec/schemas/asset.schema.json (add optional data/media entries)
  C.4  Update spec/fixtures/minimal/ to v2 (asset.json + prompts.json + new files)
  C.5  Update SPEC.md §2-§7 + v2 changelog
  C.6  Bump schema_version literal in export_asset.py
  ↓ produces: v2 contract authority (machine-checkable)
  │
  v
Phase D — Re-id registry (Feature 3) — needs A up; can start in parallel with C
─────────────────────────────────────────────────────────────────────
  D.1  Design + implement subject-segmentation route (aigc-platform)
  D.2  Implement registry/extract_subjects.py (Stage A client)
  D.3  Implement registry/cluster.py (Stage B)
  D.4  Implement html/gen_registry_review.py (Stage C HITL)
  D.5  Implement registry/apply_edits.py (Stage D)
  D.6  Wire step_registry into run_pipeline.py (step 6 of 8)
  ↓ produces: registry.json + characters.json + props.json + canonical images
  │
  v
Phase E — Prompt reference enrichment (Feature 4 finalize)
─────────────────────────────────────────────────────────────────────
  E.1  After D done, re-run step_analyze or post-process to attach
       references[] to prompts based on registry appearance_shots[]
  E.2  Update gen_timeline_html.py to render reference chips
  ↓ produces: enriched prompts.json with references
  │
  v
Phase F — Canvas consumer (Feature 5) — needs C + D + E
─────────────────────────────────────────────────────────────────────
  F.1  SHOT_TIMELINE_KNOWN_VERSIONS add "2" (the critical gate edit)
  F.2  Extend extractShotTimelineArtifacts to emit character/prop children
  F.3  (Optional) AssetNode.tsx typeIcons add character/prop glyphs
  F.4  Extend verify_contract.py assertions for character/prop nodes
  F.5  Run 3-mode harness (producer/consumer/e2e) green on v2 fixture
  ↓ produces: end-to-end working v1.1
```

**Dependency rationale:**
- **A blocks everything** — without the route, B has nothing to call and D has no SAM3 infra.
- **B before C** — proves the route-client pattern works before building schemas around its output.
- **C and D parallel** — schema work (C) is independent of ML pipeline work (D).
- **E after D** — references require registry to be finalized.
- **F last** — consumer must wait for producer to emit valid v2 manifests before it can be tested against them.
- **verify_contract.py extension happens in lockstep with each phase** — not a separate phase, but each phase's acceptance criteria includes harness green.

---

## 5. Architectural Patterns to Follow (verified in v1.0)

### Pattern 1: Stage-as-self-contained-CLI-script
**What:** Each pipeline step is a standalone Python script with argparse + main(); orchestrator invokes via `subprocess.run([sys.executable, abspath, ...])`.
**When:** Every new step (`step_analyze`, `step_registry`).
**Trade-off:** No shared in-process state; orchestrator overhead; matches v1.0 decoupling.

### Pattern 2: Idempotent mtime cache + skip flag
**What:** `if os.path.exists(out) and not force: return out` at step top; `--skip-<step>` short-circuits earlier.
**When:** `step_analyze` (cache on prompts.json mtime vs shots.json mtime); `step_registry` (cache on registry.json existence).
**Trade-off: Simple, no DB; but stale-cache risk if route URL changes (mitigation: include route URL hash in cache key for step_analyze).

### Pattern 3: Graceful-degrade on optional input
**What:** When an optional input is missing, the consumer/producer produces a reduced-but-valid output rather than failing.
**When:** `step_analyze` route-down → minimal prompts.json; consumer missing characters.json → no character nodes emitted (degrade to v1 subgraph).
**Example (mirror `gen_timeline_html.py:1051-1059`):**
```python
try:
    call_route(...)
except URLError as e:
    print(f"[5/8] [warn] analysis route unreachable: {e}; emitting empty prompts")
    prompts = [{"shot_id": s["id"], ..., "camera": "", ..., "prompt_text": ""} for s in shots]
    write_json(prompts, prompts_json)
```

### Pattern 4: Synthetic-field tagging for canvas nodes
**What:** Producer-emitted fields that don't come from upstream data are tagged `__synthetic_fields: [...]` so reviewers can distinguish them.
**When:** All new character/prop child nodes emitted by `extractShotTimelineArtifacts` (tag shot_id, engine, assetType).

### Pattern 5: Contract minor-bump via optional fields
**What:** New fields added as OPTIONAL in JSON schema (not in `required`); producer emits them; v1 consumers ignore them per graceful-degrade.
**When:** v1.1 schema bump. Critical: adding to `required` = MAJOR bump per SPEC.md:146; v1.1 stays minor.

---

## 6. Anti-Patterns to Avoid

### Anti-Pattern 1: Schema additionalProperties: false bypass
**What:** To avoid bumping the schema, adding fields while leaving schema unchanged.
**Why bad:** v1 producer-side validation fails (additionalProperties:false rejects unknown fields in prompts). The contract becomes liar — schema says one shape, producer emits another.
**Instead:** Bump schema to v2, add fields explicitly. The bump IS the contract.

### Anti-Pattern 2: Lazy SHOT_TIMELINE_KNOWN_VERSIONS update
**What:** Ship producer v2 manifests before updating consumer's KNOWN_VERSIONS set.
**Why bad:** Consumer's `import-from-dir.ts:952` prints warn and skips ALL new code paths; characters/props silently never emitted; user sees a v1-equivalent canvas with a warn in console. Silent feature loss.
**Instead:** The consumer's `KNOWN_VERSIONS = new Set(["1", "2"])` edit is a FIRST-CLASS Phase F task with explicit verify_contract.py assertion.

### Anti-Pattern 3: Synchronous HITL inside pipeline run
**What:** Pipeline blocks waiting for user to review registry in terminal.
**Why bad:** Pipeline is subprocess-orchestrated; blocking on stdin breaks `subprocess.run(check=True)` semantics; CI can't progress.
**Instead:** Pipeline emits draft registry + fails-loud with actionable message ("run `python html/gen_registry_review.py` then re-invoke with `--registry-edits path`"). Two pipeline invocations: draft → final.

### Anti-Pattern 4: re-id auto-apply without human review
**What:** Trust clusters as canonical IDs, skip Stage C.
**Why bad:** PROJECT.md:58,82 explicit constraint: "re-id 不可能 100% 准,必须 human-in-the-loop". Two characters merged into one ID poisons every downstream prompt reference.
**Instead:** Pipeline fails-loud until `registry.edits.json` exists; Stage D refuses to run without it.

---

## 7. Scalability / Operational Concerns

| Concern | Current (v1.0) | v1.1 impact |
|---------|----------------|-------------|
| Pipeline wall-clock | ~30 min on 20-min video (Whisper + Demucs dominate) | +Route round-trip latency (step_analyze 5-15 min depending on shot count + ComfyUI queue); +Stage A+B each ~5-15 min |
| Asset directory size | ~100 MB per episode (frames base64 + stems) | ++characters/props PNGs (small, <1 MB total) |
| Canvas node count (ep01) | 1 zone + 1 summary + 93 storyboard + 3 audio + 1 video + 92 sequence = 191 nodes | +N characters (typically 3-10) + M props (typically 5-20) + optionally N×M reference edges. ~10-30% growth |
| Cross-repo test surface | 6 schemas, 3 verify modes | 8 schemas, 3 verify modes, character/prop node assertions added |

---

## 8. Sources (verified live unless noted)

**Producer repo (read in full):**
- `/data/workspace/kais-shot-timeline/run_pipeline.py` — step_* order, caching pattern, --skip-*/--force flags
- `/data/workspace/kais-shot-timeline/scripts/export_asset.py` — asset.json dict construction (lines 129-187), inline validator, required-data guard (218-232)
- `/data/workspace/kais-shot-timeline/scripts/verify_contract.py` — 3-mode harness, SIX_SHAPES list (line 75), self-test, e2e teardown
- `/data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json` — additionalProperties:false, pattern constraints, schema_version pattern
- `/data/workspace/kais-shot-timeline/spec/schemas/prompts.schema.json` — current 11 required fields, no `references` yet
- `/data/workspace/kais-shot-timeline/spec/schemas/frames.schema.json` — base64 inline pattern (precedent for character thumbnail style)
- `/data/workspace/kais-shot-timeline/spec/SPEC.md` — graceful-degrade rule §4, media conventions §6, version pattern
- `/data/workspace/kais-shot-timeline/spec/fixtures/minimal/asset.json` — current v1 fixture shape
- `/data/workspace/kais-shot-timeline/.planning/PROJECT.md` — v1.1 milestone scope, constraints, key decisions

**Consumer repo (read in full from `/data/workspace/kst-canvas-consumer` worktree):**
- `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts` — extractShotTimelineArtifacts (943-1140), SHOT_TIMELINE_KNOWN_VERSIONS (898), short-circuit (1320-1354), sequence edge emission (1110-1128)
- `/data/workspace/kst-canvas-consumer/src/lib/canvasAssetSchema.ts` — assetDataSchemas (51-119) — confirms assetType permissive string (82)
- `/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/nodes/AssetNode.tsx` — typeIcons fallback to 📦 (123, 171) — confirms any assetType renders
- `/data/workspace/kst-canvas-consumer/packages/infinite-canvas/src/components/FlowCanvas.tsx` — nodeTypes registry (55-64) — confirms 5 renderers + zone + default fallback

**aigc-platform repo (read in full):**
- `/data/workspace/kais-aigc-platform/src/routes/production/shot-analysis/index.ts` — THIN route, body schema (27-35), driver spawn (98-103), aggregation (143-153)
- `/data/workspace/kais-aigc-platform/src/routes/production/shot-analysis/_shared/config.ts` — SHOT_ANALYSIS_CONFIG (comfyuiUrl, containerInputDir, shotAnalysisDir)
- `/data/workspace/kais-aigc-platform/scripts/shot-analysis/shot_analysis_driver.py` — ComfyUI workflow construction (40-109), SEMANTIC_PROMPT template (27-37)
- `/data/workspace/kais-aigc-platform/src/router.ts:49,189` — route138 import + mount (verified registered on current checkout's branch `feat/flowgraph-v3-canvas`)
- `/mnt/agents/output/gpu1/shot_analysis/shot_003.json` — real output sample: geometry.pan_right/fast + semantic.中景/follow/刀飞向画面右侧/雾气弥漫 + subject.magnitude 36.7 east. Confirms near-1:1 mapping to prompts facets.
- `/data/workspace/kais-aigc-platform/.planning/quick/260723-pn1-formalize-shot-analysis-vendor-proven-dr/260723-pn1-SUMMARY.md` — formalization plan, vendor-verbatim decision, route registered as routeN=138

**Branch state (verified):**
- `kais-aigc-platform` is on `feat/flowgraph-v3-canvas` (current HEAD: `20393616 feat(canvas): real backend integration`)
- `feat/shot-analysis-route` exists (unmerged) — contains driver + route
- `feat/shot-geometry-nodes` exists (unmerged) — contains ComfyUI custom nodes
- These two MUST merge before Phase A.3 can verify end-to-end

---

## 9. Open Questions for Downstream Phases

1. **Subject-segmentation route shape (Feature 3 Stage A):** Should it return embeddings too (Stage A+B fused) or just crops (Stage B local)? Affects whether producer pulls CLIP model or stays thin HTTP client.
2. **Embedding model choice:** CLIP-ViT-L/14 vs ArcFace vs DINOv2 for character re-id. Different trade-offs (identity-focus vs scene-focus). Needs phase-specific research.
3. **Cluster algorithm:** HDBSCAN vs agglomerative vs simple cosine threshold. Affects cluster.draft.json shape.
4. **Cross-reference edges in canvas (Feature 5):** N×M character↔storyboard edges may visually clutter — defer to Phase F.2 second pass?
5. **Route availability assumption:** Is the route expected to be up during normal producer runs, or only during dedicated "enrichment" runs? Affects whether graceful-degrade is the common path or the exception. PROJECT.md:81 implies it must always have a degrade path; deployment context will clarify.
6. **Interactive vs non-interactive registry review (Feature 3 Stage C):** Option A (single step, pause) vs Option B (three steps, off-pipeline review) — defer to phase planning.
