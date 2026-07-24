# Feature Research

**Domain:** v1.1 of an existing video-shot-decomposition tool (kais-shot-timeline) — adding semantic depth (cinematography auto-fill, cross-shot character/prop registry, prompt reference system) and bumping the ShotTimelineAsset contract from `schema_version: "1"` to `"2"`.
**Researched:** 2026-07-24
**Confidence:** HIGH for table-stakes shape (grounded in current `prompts.schema.json`, `frames.schema.json`, `asset.schema.json`); MEDIUM for re-id accuracy ceilings (grounded in SOTA photorealistic benchmarks — animation/anime is an unknown further gap); HIGH for contract-bump mechanics (the v1.0 graceful-degrade rule already specifies the path).

> **Scope note.** This file covers ONLY the 5 new v1.1 feature areas. v1.0-validated capabilities (shot detection / Demucs / Whisper / 5-JSON asset / Range server / contract v1) are treated as pre-existing and NOT re-researched.

---

## How Real Tooling Does Each Feature

This grounds each feature in observed industry practice before the table-stakes/differentiator/anti-feature split.

### (1) Cinematography → structured-prompt auto-fill

**Industry convergence.** Major video-model labs independently arrived at near-identical prompt facets — Google Veo's guide lists 7 elements; OpenAI Sora breaks prompts into scene/cinematography/action/dialogue/sound; ByteDance Seedance walks subject→action→environment→camera→style. OCDevel's 2026 synthesis names **8 slots** that sort into a "still half" (subject, lens/framing, lighting, mood/color, setting — what an image prompt carries) and a "motion half" (action, camera move, pacing — video-only). The discipline: name the **change between first and last frame**, or the model invents unwanted motion ("living-photo drift").

**Mapping onto the existing `prompts.schema.json`.** The schema already has 6 facets + `prompt_text`:

| Existing facet (current schema) | Source in kais-aigc-platform infra | Slot in industry 8-part model |
|---|---|---|
| `subject` (string) | Qwen3-VL semantic (subject description) | Still — subject |
| `action` (string) | SAM3.1 subject-motion tracking | **Motion — action** |
| `camera` (string) | Geometry nodes (optical-flow → camera movement) + Qwen3-VL shot scale | **Motion — camera move** + Still — lens/framing |
| `scene` (string) | Qwen3-VL scene/setting | Still — setting |
| `lighting` (string) | Qwen3-VL lighting (if exposed) or unfilled | Still — lighting |
| `style` (string) | (likely unfilled by current ComfyUI route) | Still — mood/color grade |
| `prompt_text` (string) | Composed from the above | synthesized |

**Implication for v1.1.** The mapping is near 1:1. v1.1's "auto-fill" job is essentially a thin HTTP client merging the route's per-shot JSON into these 6 facets + recomposing `prompt_text`. Pacing (slot 7) and lens focal-length (sub-slot of camera) are not currently exposed by the ComfyUI route — they can stay in the facet strings or be left unfilled. **Do not expand the schema to 8 facets just to mirror the industry model** — 6 already capture the route's actual output (anti-feature, see below).

### (2) Character/prop "sheet" extraction from first/last frames

**What makes a usable character reference image for AI video** (MindStudio/Seedance workflow guidance, 2026):

- **Sharp, well-lit frames.** Blurry or motion-blurred frames degrade downstream generation quality significantly. SAM3 masks on motion-blurred frames are also noisier.
- **5–7 most visually distinguishing attributes** — not every attribute. The sheet's job is identity anchoring, not a complete description.
- **Multi-angle (front / three-quarter / side; back if recurring).** Models can follow ~3–5 attributes reliably for 1–2 generations; drift accumulates over longer sequences.
- **Neutral pose preferred for the canonical reference;** action shots valuable as secondary references.
- **Clean crop** (subject isolated, neutral or removed background) — the canonical AI-video workflow does not paste the sheet verbatim, it pulls distinguishing attributes into a prompt, so the sheet is both a visual anchor for image-to-video and a structured-text source.
- **Image-to-video chaining** (last frame of clip A → reference image for clip B) is the most reliable continuity tool — text alone loses identity over multiple generations.

**Constraint from v1.0 `frames.schema.json`.** First/last frames are JPEG base64 data URIs at 480px wide (per `gen_timeline_html.py` ffmpeg `-vf scale=480:-1`). That is sufficient resolution for AI-video reference use (smaller than ideal but above the bar), but the framing is whatever the shot happened to be — not a controlled turnaround. **The v1.1 system can crop subjects out of existing frames via SAM3 masks, but it cannot synthesize angles that don't exist in the source.** This bounds what a character "sheet" can be in v1.1: it is a registry of observed occurrences with a chosen representative crop, NOT a classic animation character model sheet.

### (3) Cross-shot character/prop re-id registry — the difficulty cliff

**This is the hardest feature in v1.1 and the one most likely to be mis-scoped.** Documented SOTA accuracy:

**Same-domain (in-dataset) re-id — CLIP-ReID ViT-B/16, 2023–2025:**

| Benchmark | mAP | Rank-1 |
|---|---|---|
| Market-1501 | 89.6 | 95.5 |
| DukeMTMC-reID | 82.5 | 90.0 |
| MSMT17 | 73.4 | 88.7 |
| **Occluded Duke** (occlusion) | **59.5** | **67.1** |

**Cross-domain (domain gap, the real-world setting) — same SOTA:**

| Train → Test | mAP | Rank-1 |
|---|---|---|
| Market → DukeMTMC | 50.2 | 68.9 |
| Market → CUHK03 | 38.6 | 40.4 |
| Market → ENTIRe-ID | 38.9 | 38.4 |
| **Market → Airport** (worst case) | **20.0** | **22.4** |

**Why this matters for kais-shot-timeline:**

1. **These benchmarks are photorealistic pedestrian surveillance.** kais-shot-timeline's content (per `output/` examples) is Chinese animation / 3D animation / cartoons (`《小江湖》` etc.). Animation is a **further domain gap** not represented in any of these training sets. Expect WORSE than the cross-domain numbers above.
2. **Cross-shot re-id inside a single video is the "single-camera non-overlapping" setting** — the hardest unsupervised re-id formulation. No labeled gallery, no overlap between shot cuts.
3. **Occlusion alone drops mAP from ~90 to ~60** even in-domain. Many shot first/last frames have partial occlusion (character entering/leaving frame).
4. **A naive "same embedding → same entity" decision is wrong 30–60% of the time in this setting.** That means hundreds of mis-clusters across a typical episode.

**Verdict: human-in-the-loop review is not a polish step — it is the feature.** The ML provides candidates; the human is the source of truth.

**Typical data shape — "cast table" / "prop table"** (synthesized from re-id literature + cinematic script-writer patterns):

```json
{
  "schema_version": "2",
  "characters": [
    {
      "id": "char_001",                  // stable handle referenced by prompts
      "label": "白发少女",                // human-editable display name
      "representative_image": "characters/char_001.jpg",  // canonical crop
      "attributes": {"hair": "white", "outfit": "white dress", ...},
      "occurrences": [
        {"shot_id": 1, "frame_role": "first", "bbox": [120, 80, 340, 460]},
        {"shot_id": 1, "frame_role": "last",  "bbox": [...]},
        {"shot_id": 7, "frame_role": "first", "bbox": [...]}
      ],
      "embedding_ref": "characters/char_001.npy",  // for incremental re-clustering
      "review_state": "confirmed"          // confirmed | proposed | rejected
    }
  ],
  "props": [ /* same shape */ ]
}
```

The `review_state` field is non-negotiable. Without it there is no way for a consumer to know whether a cluster is ML-only or human-confirmed.

### (4) Prompt reference system

**Three layered mechanisms in observed tools** (cinematic-script-writer AI agents, arXiv multistage character-stable pipelines):

| Mechanism | Where it lives | Audience | Example |
|---|---|---|---|
| **ID tokens** | Machine-readable data (prompts.json fields) | Pipeline / downstream AI models | `"subject": "[char_001] 白发少女, 白色衣裙"` |
| **Reference chips** | UI rendering (HTML, canvas) | Human reviewing | `[char_001 白发少女]` rendered as a clickable badge inside the prompt facet |
| **@-mentions** | Free-text inside `prompt_text` | Human-readable narrative | `"prompt_text": "... @char_001 走入画面 ..."` |

**The key design decision: the ID is the anchor, the free text is for humans.** A prompt facet stores BOTH the structured ID reference AND a human label, so:
- Downstream consumers can resolve `[char_001]` to the canonical cast entry (image + attributes) for image-to-video use.
- Human readers see a readable label even if they never resolve the ID.
- `prompt_text` (the composed plain-text prompt) stays model-friendly — many AI video models do NOT understand `@mentions`, so the composed prompt should substitute the canonical short description, not the raw token.

**Continuity semantics that ARE in scope for v1.1:** identity continuity (same character across shots = same ID reference). Continuity NOT in scope: dialogue attribution (who spoke), gaze direction, blocking — those are larger lifts and explicitly out-of-scope per `PROJECT.md`.

### (5) Asset-contract minor-version bump mechanics

**The v1.0 graceful-degrade rule is already aligned with SchemaVer** (Snowplow's industry-standard schema-versioning formula):

| SchemaVer change | Trigger | v1.0 equivalent |
|---|---|---|
| ADDITION (+) | New optional field, all historical data still valid | "minor bump" per `asset.schema.json#schema_version.description` |
| REVISION (-) | Schema change that MAY break some historical data | (collapses into "major bump" in v1.0's semver-lite) |
| MODEL (-) | Breaks interaction with ALL historical data | "major bump" |

v1.0 uses semver-lite (major.minor, no patch component) — a deliberate simplification over SchemaVer's three-part `MODEL-REVISION-ADDITION`, justified in `SPEC.md §4` because ShotTimelineAsset is a single-producer format (no consumer-facing patch-release semantics).

**What v1.1 actually needs to do for the bump** — grounded in the current `asset.schema.json` and `prompts.schema.json`:

| Change | Schema-level action | Old-consumer impact |
|---|---|---|
| Add `characters.json` / `props.json` as new data files | Add optional `data.characters`, `data.props` to `asset.schema.json` (NOT to `required`) | Old consumers ignore unknown fields per graceful-degrade rule |
| Add new optional fields to each prompt object (e.g. `subject_refs: [char_id]`) | Add to `prompts.schema.json` properties, NOT to `required` | Old consumers ignore unknown fields; render existing facets |
| Add new media category (character crop images) | Add optional `media.characters` pattern to `asset.schema.json` | Old consumers ignore unknown media |
| Bump `schema_version` | `"1"` → `"2"` in producer output + `SPEC.md §4` Changelog entry | Old consumers emit warning, render v1 fields normally |
| Update `spec/validate.py` | New schema fixture for v2; v1 fixtures still validate | — |

**Critical v1.0 invariant that v1.1 must NOT break:** `additionalProperties: false` on every object. This is what forces explicit version bumps. The bump mechanics work BECAUSE the schema is strict — relaxing it would silently allow producers to add unversioned fields.

**The v1.0 design already anticipated exactly this kind of minor bump.** v1.1 is the first exercise of the schema-evolution path; the graceful-degrade rule was written for it (`SPEC.md §4`: "New field = minor bump; breaking change (rename/semantic shift/removal) = major bump").

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Cinematography auto-fill: HTTP client to existing kais-aigc-platform route** | Manual `part_*.json` + `merge_prompts.py` is the current workflow — it is documented in `PROJECT.md` as the thing v1.1 replaces. Users will expect the pipeline to call the validated P0–P4 route directly. | LOW | Thin `requests.post`-style client. Map JSON fields → 6 facets. ~150 LOC in a new `step_fill_cinematography` pipeline stage. Graceful-degrade (skip + warn) when route unavailable. |
| **Cinematography graceful-degrade when route offline** | Pipeline must still produce an asset (PROJECT.md constraint: "路由不可用时 shot-timeline 必须能 graceful-degrade"). | LOW | Mirror the existing `--skip-*` pattern. If route times out / 4xx/5xx, fall back to current `prompts.json` (filled by `merge_prompts.py` or empty). Print `[fill_cinematography] route unavailable, skipping`. |
| **Character/prop occurrence detection per shot (bbox + crop)** | Without this, the registry is empty. This is the SAM3 layer (already built in kais-aigc-platform) applied to first/last frames. | MEDIUM | Re-uses validated SAM3 infra. New endpoint in kais-aigc-platform; shot-timeline is a client. Output: per-shot list of detections with bbox + cropped image. |
| **Re-id embedding + initial clustering** | Raw detections are useless for continuity without cluster IDs. Embedding (DINOv2 / CLIP-ReID style) + clustering is the floor. | MEDIUM | Compute embedding per crop (route-side). Agglomerative clustering with conservative threshold. **Output every cluster as `review_state: "proposed"` — never auto-confirm.** |
| **Human review UI for cast/prop registry** | re-id WILL be wrong 20–60% of the time (see numbers above). Without review, the registry is noise. | HIGH | New HTML generator (mirror `gen_timeline_html.py` pattern): show cluster representative + all member crops + merge/split/rename actions. Output the edited registry as `characters.json` / `props.json`. This is the most novel UI work in v1.1. |
| **Cast/prop registry as canonical data files (`characters.json`, `props.json`)** | Prompts can't reference IDs without a registry. Self-describing assets must carry their own cast table. | LOW | Two new schemas mirroring the shape in section (3) above. Optional fields in `asset.schema.json`. Producer (`export_asset.py`) writes them when review is complete; omit them when re-id was skipped. |
| **Prompt reference: stable character/prop IDs in prompts.json** | "Real narrative continuity" (the v1.1 core value per PROJECT.md) requires prompts to reference the same character consistently. | MEDIUM | Add optional `subject_refs: ["char_001"]` and `prop_refs: ["prop_003"]` to `prompts.schema.json` items. Producer resolves these against `characters.json` when composing `prompt_text`. |
| **Contract minor bump mechanics (`schema_version: "1"` → `"2"`)** | Adding fields/files without a bump is a silent interop bug — explicitly forbidden by v1.0 SPEC §4. | LOW | Additive schema changes only (see section 5 above). Update `SPEC.md §4` Changelog. Update `spec/fixtures/minimal/` and `spec/validate.py`. Verify v1 consumer still graceful-degrades. |
| **shot-timeline HTML: character/prop gallery section** | v1.0 HTML already shows shots/frames/audio/transcript. Cast/props are a new track and users will expect to see them. | MEDIUM | New section in `gen_timeline_html.py` (or a new `gen_registry_html.py` mirror). Show representative crops + occurrence list + (differentiator) reference chips in prompts. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Reference chips in prompt UI** | Visual clickable badges inside each prompt facet, linking to the cast/prop entry. Makes the ID-reference system legible to humans — far better than raw `[char_001]` tokens. | MEDIUM | Inline HTML in `gen_timeline_html.py` prompt rendering. Click → scroll to cast/prop entry. Reuses GitHub-dark chip styles already in the codebase. |
| **Cluster confidence + review-state visualization** | Show the re-id model's confidence (e.g. embedding-distance heatmap) and `review_state` color-coding. Tells the user where to focus review effort. | MEDIUM | Embeddings already computed; expose cosine distance in the review UI. Color: green=confirmed, yellow=proposed, red=low-confidence. |
| **Best-of-N representative crop auto-selection** | For each character, pick the sharpest / best-lit / most frontal crop from all occurrences as the canonical `representative_image`. Improves downstream AI-video quality. | MEDIUM | Score each crop (laplacian variance for sharpness, SAM3 mask area for visibility, embedding-centroid distance for typicality). Pick max. |
| **`prompt_text` dialect switch (paragraph vs keyword)** | Different AI video models prefer different prompt styles (Sora/Veo = rich paragraph; Runway = terse keyword). Auto-emit the right one based on a CLI flag or per-asset config. | LOW-MEDIUM | Two composition templates in the prompt-text builder. Pure UX lift; no schema impact. |
| **Backward-compatibility smoke test in `spec/validate.py`** | Test that v1 consumers can still parse v2 assets (and vice versa). Makes the graceful-degrade rule testable, not aspirational. | LOW | New harness mode: load v2 fixture, walk v1 schema fields only, assert no exceptions. Catches accidental removals of v1 fields. |
| **Per-occurrence bbox visualization on first/last frames** | Draw the detected character/prop bbox onto the frame thumbnails. Lets reviewer verify detection quality at a glance. | LOW | SVG overlay or canvas in HTML. Frame JPEGs already in `frames.json`. |
| **SchemaVer-aligned changelog section in SPEC.md** | Document the bump with structured ADDITION/REVISION/MODEL labels per change. Gives auditors a clear migration path. | LOW | Pure documentation. Update `SPEC.md §4` Changelog with a v2 entry. |

### Anti-Features (Commonly Requested, Often Problematic)

Features to explicitly NOT build. PROJECT.md already lists some; this section expands.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Fully-automatic re-id (no human review)** | "Just let the model figure out who's who" | SOTA cross-domain re-id is 20–50% mAP on photorealistic pedestrians; animation is worse. A 30–60% mis-cluster rate makes the registry actively misleading and undermines downstream continuity. The whole value proposition (narrative continuity) collapses. | Semi-automatic: ML proposes, human reviews, `review_state` tracks truth. Already decided in PROJECT.md — re-affirmed. |
| **Cross-video character continuity (same character across different episodes)** | "Build a series-wide cast registry" | Requires solving cross-video domain gap ON TOP of cross-shot — an even harder re-id problem. Also requires identity matching between unrelated animations (different art styles, same character). Out of scope per PROJECT.md. | Per-asset registries only. Each video has its own `char_001`. A future cross-asset linking layer can sit on top if needed. |
| **Dialogue → character attribution (who said what)** | "Auto-assign each transcript line to a speaker" | Requires speaker identification (audio embedding) or lip-sync alignment (visual). Both are separate hard ML problems. Major lift on top of v1.1. Out of scope per PROJECT.md. | `transcript.json` stays speaker-agnostic in v1.1. Add `speaker_ref` field in a future milestone. |
| **Expanding prompts schema from 6 to 8 facets (adding `pacing`, `lens`)** | "Match the industry 8-slot model" | Schema bloat for slots the existing ComfyUI route does not expose. YAGNI — `pacing` and `lens` can live as text inside `camera` or `style` if needed. Forces every prompt to fill new required-like fields. | Keep 6 facets. Encode `pacing` / `lens` inside existing `camera`/`style` strings if the route ever exposes them. |
| **Synthesizing multi-angle turnaround sheets** | "Generate a back view / side view of each character" | Pure generation — back views may not exist in the source. Faked angles degrade downstream AI-video identity consistency (the model invents features). Worse than honest single-crop. | Register only observed occurrences. The "sheet" is a registry of real crops, not a generated turnaround. |
| **Bundling character crops as base64 inside `characters.json`** | "Keep everything self-contained like frames.json" | Character crops for a full episode (many characters × many occurrences × full-resolution) can exceed frames.json by 10–50×. Base64-in-JSON bloats the asset past useful. Frames.json is already the documented single exception (SPEC §7.3). | External `characters/char_NNN.jpg` files under the asset root, listed in `asset.json#media.characters`. Mirrors how `stems/*.wav` are external. |
| **Bumping the contract to `schema_version: "3"` mid-v1.1** | "Add a feature that breaks v2" | v1.1 is a minor-bump milestone. Inventing a breaking change mid-stream splits consumer compatibility. | Defer breaking changes to v2.0. v1.1 = minor bump only. |
| **Adding a custom canvas renderer for cast/prop nodes** | "Render character galleries natively in @kais/infinite-canvas" | Explicitly out of scope per PROJECT.md — reuses existing renderers via new node type. A custom renderer would force a separate contract bump on the canvas side. | New structured node type that reuses existing renderers. Already decided. |
| **Lip-sync / motion re-targeting onto character sheets** | "Make the character sheet poseable" | Out of scope for a decomposition tool — that's generation, not analysis. | Sheet is a static reference, not a rig. |
| **Storing raw embedding vectors inside `characters.json`** | "Keep everything in one file" | Embeddings are 512–768 floats × N characters × M occurrences. Inflates JSON; consumers don't need them at runtime. | Out-of-line `characters/char_NNN.npy` (or omit entirely if no incremental re-clustering planned). |

---

## Feature Dependencies

```
[Cinematography auto-fill]
    └──requires──> [kais-aigc-platform feat/shot-geometry-nodes + feat/shot-analysis-route merged]
    └──requires──> [existing prompts.json schema (v1.0)]  (enriches, doesn't replace)
    └──enhances──> [Prompt reference system]  (filled facets give context to IDs)

[Character/prop occurrence detection]
    └──requires──> [SAM3 infra in kais-aigc-platform]
    └──requires──> [existing frames.json first/last frames]

[Re-id clustering]
    └──requires──> [Character/prop occurrence detection]
    └──produces──> [proposed clusters with review_state="proposed"]

[Human review UI]
    └──requires──> [Re-id clustering output]
    └──produces──> [confirmed characters.json / props.json]

[Prompt reference system]
    └──requires──> [confirmed characters.json / props.json]  (to resolve IDs)
    └──requires──> [existing prompts.json schema]  (adds subject_refs / prop_refs)
    └──enhances──> [Cinematography auto-fill]  (subject facets carry IDs)

[Contract minor bump]
    └──requires──> [all of the above — they define what fields/files are added]
    └──requires──> [v1.0 graceful-degrade rule]  (lets old consumers survive)

[shot-timeline HTML gallery]
    └──requires──> [confirmed characters.json / props.json]
    └──requires──> [Prompt reference system]  (to render reference chips)

[Canvas consumer new node type]
    └──requires──> [Contract minor bump]  (cross-repo, kais-aigc-platform)
    └──requires──> [confirmed characters.json / props.json]

[Auto-fill]        ──independent of──>     [Re-id / Review / Registry]
[Re-id / Review]   ──independent of──>     [Auto-fill]
    (the two new semantic layers can be developed in parallel;
     they only meet at [Prompt reference system] and [Contract bump])
```

### Dependency Notes

- **Cinematography auto-fill requires the two unmerged ComfyUI branches.** This is a hard external dependency — `feat/shot-geometry-nodes` (geometry nodes for camera motion) and `feat/shot-analysis-route` (driver + HTTP route) must merge in kais-aigc-platform before this feature works end-to-end. PROJECT.md flags this. Requirements-definer should treat the merge as a phase prerequisite, not a work item.
- **Cinematography and re-id pipelines are parallelizable.** They share only the underlying shot/frames data; no code-level dependency. Phases can be ordered to develop them in parallel branches and merge independently.
- **Prompt reference system requires the registry exists first.** It is the integration point between the two pipelines. Schedule it AFTER both have produced output.
- **Contract bump requires everything.** It is the LAST step — it codifies what the producer actually emits. Bumping the schema before the producer fields are settled causes rework.
- **Canvas consumer work conflicts with nothing but adds cross-repo overhead.** PROJECT.md notes ~30% overhead for cross-repo work (measured in v1.0). Reserve capacity.
- **Human review UI is the critical-path bottleneck for the registry.** Without it, the registry can't reach `review_state: "confirmed"` and downstream features (prompt reference, gallery) have nothing trustworthy to consume.

---

## MVP Definition

### Launch With (v1.1)

Minimum viable v1.1 — what's needed to validate "shot decomposition with reusable cross-shot identity + cinematography + continuity-aware prompts":

- [ ] **Cinematography auto-fill HTTP client + graceful-degrade** — replaces manual `part_*.json`. Essential to the milestone's "镜头语言/动作/语义自动填充" target.
- [ ] **Character/prop occurrence detection (per-shot bbox + crop)** — without it there is no registry to review.
- [ ] **Re-id embedding + proposed clustering** — without it the registry is just a list of unrelated crops.
- [ ] **Human review UI (merge / split / rename / confirm)** — the only path to trustworthy clusters. Cannot defer.
- [ ] **`characters.json` + `props.json` as canonical data files** — required for prompt references and contract bump.
- [ ] **Prompt reference fields (`subject_refs`, `prop_refs`) in prompts schema** — the "real narrative continuity" deliverable.
- [ ] **Contract minor bump to `schema_version: "2"`** — adding fields without bumping violates the v1.0 contract.
- [ ] **Backward-compatibility smoke test** — verify v1 consumers still work on v2 assets. Non-negotiable given the v1.0 graceful-degrade promise.
- [ ] **shot-timeline HTML: character/prop gallery section** — end-user visibility. PROJECT.md target: "用户要端到端可见".

### Add After Validation (v1.x)

Features to add once v1.1 core is working:

- [ ] **Reference chips in prompt UI** — nice-to-have polish; once IDs are stable in the data, the chips are pure rendering.
- [ ] **Cluster confidence heatmap in review UI** — improves review throughput once the basic review loop is proven.
- [ ] **Best-of-N representative crop selection** — quality lift once registry structure is settled.
- [ ] **`prompt_text` dialect switch** — wait for user feedback on which downstream AI video models are actually used.
- [ ] **Canvas consumer cast/prop node type** — cross-repo; schedule via kais-aigc-platform milestone. May land slightly after shot-timeline v1.1 ships.

### Future Consideration (v2+)

Features to defer until v1.1 is validated in real use:

- [ ] **Dialogue → speaker attribution** — large lift (speaker ID or lip-sync). Defer until cast registry is proven useful.
- [ ] **Cross-video character continuity** — defer until per-asset registries are stable; needs a separate linking layer.
- [ ] **LoRA / character-model training off the registry** — generation-side feature, not decomposition. Different milestone.
- [ ] **Native canvas timeline renderer (stems + waveforms + Range media)** — explicitly deferred per PROJECT.md; relies on contract stability from v1.1.
- [ ] **Cross-asset search ("find all shots with char_001 across the library")** — depends on cross-video continuity; very deferred.
- [ ] **Real-time / incremental re-clustering as new shots arrive** — v1.1 will batch-recluster on demand.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Cinematography auto-fill HTTP client | HIGH | LOW | P1 |
| Cinematography graceful-degrade | HIGH | LOW | P1 |
| Character/prop occurrence detection | HIGH | MEDIUM | P1 |
| Re-id embedding + clustering | HIGH | MEDIUM | P1 |
| Human review UI | HIGH | HIGH | P1 |
| `characters.json` / `props.json` schemas | HIGH | LOW | P1 |
| Prompt reference fields (`subject_refs`, `prop_refs`) | HIGH | MEDIUM | P1 |
| Contract bump `1` → `2` + SPEC changelog | HIGH | LOW | P1 |
| Backward-compat smoke test | HIGH | LOW | P1 |
| shot-timeline HTML gallery | MEDIUM-HIGH | MEDIUM | P1 |
| Reference chips in prompt UI | MEDIUM | MEDIUM | P2 |
| Cluster confidence visualization | MEDIUM | MEDIUM | P2 |
| Best-of-N representative crop | MEDIUM | MEDIUM | P2 |
| `prompt_text` dialect switch | LOW-MEDIUM | LOW | P2 |
| Canvas consumer cast/prop node | MEDIUM | MEDIUM (cross-repo) | P2 |
| Per-occurrence bbox overlay | LOW-MEDIUM | LOW | P2 |
| SchemaVer-labeled changelog | LOW | LOW | P2 |

**Priority key:**
- P1: Must have for v1.1 launch — defines the milestone
- P2: Should have, add when possible within v1.1
- P3: Future milestone

---

## Competitor / Adjacent-Tool Feature Analysis

No direct competitor does exactly this (decompose a finished film into a portable multi-track asset with cross-shot character registry). Adjacent tools and what they do in each feature area:

| Feature | AI-video prompting guides (Veo/Sora/Seedance/Runway) | Traditional VFX / animation pipelines | Re-id academic SOTA | Our Approach (v1.1) |
|---------|---|---|---|---|
| Cinematography → prompt facets | Converged on 7–8 slot model; human-written | N/A (shots defined at storyboard) | N/A | Auto-extract from existing film via external ML route; map to 6 existing schema facets |
| Character reference | Manual: human writes sheet or curates images | Manual model sheets (animation) / on-set photography (VFX) | N/A | Auto-crop from first/last frames via SAM3; human-reviewable registry |
| Cross-shot re-id | Not addressed | Manual continuity logging | CLIP-ReID etc. — 90%+ in-domain, 20–50% cross-domain, animation worse | Semi-automatic: ML proposes, human confirms; `review_state` field |
| Prompt reference to characters | "Reference image" features in image-to-video models | N/A | N/A | Structured `subject_refs` IDs in prompts.json; resolve to registry entries |
| Schema evolution | N/A | N/A | N/A | SchemaVer-aligned minor bump; v1.0 graceful-degrade rule |

**The genuine differentiator of kais-shot-timeline v1.1** is not any single feature — it is the **portable, contract-versioned asset that ties all four together**. Tools like Seedance or Runway expect the user to manually manage references and continuity. Traditional VFX pipelines are linear and tool-locked. The v1.1 milestone produces a self-describing asset that any downstream consumer (canvas, training pipeline, AI-video model) can read with stable character identities and graceful-degrade guarantees. That package is the differentiator.

---

## Complexity Ratings Summary (for requirements-definer)

| Feature | Complexity | Why |
|---------|------------|-----|
| Cinematography auto-fill | LOW | Thin HTTP client; field-map to existing schema; mirror existing `--skip-*` degrade pattern |
| Cinematography graceful-degrade | LOW | Reuse v1.0 cache-skip pattern |
| Character/prop occurrence detection | MEDIUM | New endpoint in kais-aigc-platform (cross-repo); SAM3 mask → bbox → crop pipeline |
| **Re-id clustering** | **MEDIUM** | Embedding extraction + agglomerative clustering are well-understood; tuning threshold for animation domain is the work |
| **Human review UI** | **HIGH** | Most novel UI surface in v1.1; merge/split/rename flows; new HTML generator; multi-file review state persistence |
| Registry schemas | LOW | Two new schemas + 2 optional fields in asset.schema.json |
| Prompt reference fields | MEDIUM | New optional schema fields + producer must recompose `prompt_text` against the registry |
| Contract bump | LOW | Additive only; v1.0 graceful-degrade rule was designed for exactly this |
| shot-timeline HTML gallery | MEDIUM | Mirror existing HTML generator pattern; new section, not new file |
| Canvas cast/prop node | MEDIUM (cross-repo) | Reuses existing renderers per PROJECT.md; cross-repo coordination cost ~30% |

---

## Sources

- **v1.0 contract (authoritative for current state):**
  - `/data/workspace/kais-shot-timeline/spec/SPEC.md` — graceful-degrade rule (§4), 5 canonical data shapes (§5), media conventions (§6)
  - `/data/workspace/kais-shot-timeline/spec/schemas/prompts.schema.json` — 6 facet schema
  - `/data/workspace/kais-shot-timeline/spec/schemas/frames.schema.json` — base64 JPEG first/last frames
  - `/data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json` — `schema_version` pattern, `additionalProperties: false`, required data/media inventories
  - `/data/workspace/kais-shot-timeline/.planning/PROJECT.md` — v1.1 feature list + out-of-scope decisions
- **Prompt facet decomposition (MEDIUM-HIGH confidence):**
  - [The Anatomy of a Video Prompt: Subject, Action, Camera, and Light — OCDevel](https://ocdevel.com/podcaster/ai-video-generation/93d9a941-d6ac-437b-bb24-fdf8d7b66571) — 8-slot model convergence across Veo/Sora/Seedance guides
- **Character reference sheets (MEDIUM confidence):**
  - [How to Use Storyboards and Character Sheets to Get Better AI Video Results — MindStudio](https://www.mindstudio.ai/blog/storyboards-character-sheets-ai-video-generation) — what to include, multi-angle, image-to-video chaining
- **Re-id accuracy ceilings (HIGH confidence for photorealistic; LOW for animation domain):**
  - [An Investigation of the Domain Gap in CLIP-Based Person Re-Identification — Asperti/Naldi/Fiorilla, Sensors 2025](https://www.mdpi.com/1424-8220/25/2/363) — same-domain 73–95% mAP; cross-domain 20–50% mAP; occlusion drops to ~60% mAP
  - [Tracking Classroom Movement Patterns with Person Re-ID — EDM 2024](https://educationaldatamining.org/edm2024/proceedings/2024.EDM-posters.72/index.html) — clustering same person across shots via embedding
- **Prompt reference / character ID tokens (LOW-MEDIUM confidence; emerging practice):**
  - [A Multistage Pipeline for Character-Stable AI Video Stories — arXiv 2512.16954](https://arxiv.org/html/2512.16954v1) — ID-anchored character pipeline
  - [Cinematic Script Writer AI Skill — ExplainX](https://explainx.ai/skills/praveenspeaks/cinematic-script-writer/cinematic-script-writer) — character consistency in cinematic AI prompting
- **Schema evolution / SchemaVer (HIGH confidence):**
  - [Introducing SchemaVer — Snowplow](https://snowplow.io/blog/introducing-schemaver-for-semantic-versioning-of-schemas) — MODEL-REVISION-ADDITION rules; v1.0's semver-lite is a deliberate simplification
  - [Aligning views on stability guarantees — JSON Schema Org discussion](https://github.com/orgs/json-schema-org/discussions/295) — graceful-degrade is a runtime concern, not a schema-spec concern (mirrors v1.0 SPEC §4 "intentional tension")

---
*Feature research for: kais-shot-timeline v1.1 — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 v2 + 双端展示*
*Researched: 2026-07-24*
