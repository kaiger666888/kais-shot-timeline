# Architecture Research: v1.2 音频语义深化 — Integration with Existing Pipeline + v1.1 Route Pattern

**Domain:** Loosely-coupled producer (Python CLI pipeline) adding a 3rd ML-route-dependent semantic layer (audio: dialogue/music/sfx) on top of v1.0 (asset contract) + v1.1 (shot cinematography + cross-shot re-id registry).
**Researched:** 2026-07-25
**Confidence:** HIGH (all integration claims verified against live source — `run_pipeline.py:108-490` step_* functions, `analysis/call_shot_analysis.py:73-424`, `analysis/call_reid.py:76-457`, `scripts/export_asset.py:48-380`, `spec/validate.py:54-71`, `scripts/verify_contract.py:319-385`, `spec/schemas/asset.schema.json:144-153`, `audio/gen_audio_prompts.py:1-399`, `spec/SPEC.md:158-168` Changelog). External model claims (WhisperX, pyannote, MIRFLEX, MERT) verified via official repos / arXiv.

---

## Executive Summary

v1.2 audio semantic deepening integrates cleanly into the existing producer pipeline as a **third sibling of the v1.1 route-pattern family** (`call_shot_analysis.py` per-shot, `call_reid.py` per-video → new `call_audio_analysis.py` per-shot). All v1.0/v1.1 architecture invariants carry: loose coupling, no core-algorithm churn, contract minor-bump-only, graceful-degrade keeping assets byte-identical when the route is down.

Five concrete findings reshape the plan:

1. **Pipeline slot inserts at position 7, not appended** — between `step_reid[6]` and `step_timeline[7]`. SPEAKER-01 linkage needs `characters.json` produced post-`step_reid`+HITL apply_edits, and `step_timeline` needs audio_semantic in hand to render the new gallery/chips. Counter renumbers `[N/8]` → `[N/9]` (17 banner instances, mirroring the v1.1 Phase 6 `[N/7]→[N/8]` renumber at `run_pipeline.py:111,129,148,...`).
2. **Caching granularity is per-shot (mirror `call_shot_analysis.py`, NOT `call_reid.py`)** — SER/MIR/diarization are shot-local analyses; per-shot cache files `route_cache/audio_analysis/shot_XXX.json` with the same 4-tuple `_cache_key {video_content_hash, route_name, route_version, shot_id}`. Per-video would force full recompute on any single-shot edit and conflicts with the proven Phase 6 cache-invalidation pattern.
3. **WhisperX must be used as the integrated WhisperX+pyannote pipeline, not WhisperX+standalone-pyannote** — WhisperX's `align()` + diarize integrate pyannote internally with consistent VAD; the standalone-Pyannote alternative has a documented temporal-drift bug (WhisperAlign arXiv:2603.04809). This is a Phase 1 risk-validation question to confirm.
4. **SPEAKER-01 uses a NEW ID space `^spk_[0-9]{3}$` + a NEW `speakers.json` sidecar mapping `spk_NNN → char_NNN|null`** — DO NOT overload pyannote to emit `char_NNN` directly (route has no registry context; would couple producer-side route to consumer-confirmed registry). Producer emits raw `spk_NNN`; reviewer runs a NEW `registry/link_speakers.py` HITL step (mirrors v1.1 `apply_edits.py` confirmed-only gate) producing `speakers.json` that downstream resolves. Decouples route availability from registry availability.
5. **Schema bump propagation is mechanical and locked by precedent** — 6 touchpoints (SCHEMA_VERSION constant, asset.schema.json data.audio_semantic, validate.py V12_ORDER, verify_contract.py cross-version + fixture-consistency extension, SPEC §4 Changelog + §5.8, export_asset.py build_asset_dict conditional emit). v1.1 already proved this exact 6-touchpoint pattern in Phase 5; v1.2 mostly copy-modifies.

The biggest architectural risk (per PROJECT.md:121 Phase 1 lock) is **model risk on Chinese SER cross-domain** (RAVDESS English-performance-trained → Chinese animation dialogue) and **MIR precision on multi-stem mixes** (separation artifacts). Phase 1 is therefore an empirical spike on 1 episode — mirrors v1.1 Phase 7 DINOv2 τ spike (先证模型、再立契约). **NO contract changes in Phase 1.**

---

## 1. Existing Architecture Baseline (Live-Verified)

### 1.1 Current `[N/8]` step pipeline (`run_pipeline.py:108-490`)

```
[1/8] ensure_h264       AV1→H264 transcode guard              (run_pipeline.py:83-98)
[2/8] step_detect       → shots.json                          (run_pipeline.py:108-122)
[3/8] step_separate     → audio_analysis.json + stems/        (run_pipeline.py:125-141)
[4/8] step_transcribe   → transcript.json                     (run_pipeline.py:144-160)
[5/8] step_semantic     → prompts.json (route: shot-analysis) (run_pipeline.py:163-232)
[6/8] step_reid         → registry.draft.json + HITL html     (run_pipeline.py:235-313)
[7/8] step_timeline     → timeline.html                       (run_pipeline.py:316-393)
[8/8] step_export       → asset.json + canonical symlinks     (run_pipeline.py:424-490)
```

Banner format is `f"[{N}/8] {label}"` at every `step_*` + inside `ensure_h264`. v1.1 Phase 6/7 already renumbered `[N/6]→[N/7]→[N/8]` twice — the pattern is mechanical grep-and-replace (verified in v1.1 milestone audit: "renumbered 17 `[N/6]`→`[N/7]` labels" then "20× `[N/7]`→`[N/8]`").

### 1.2 The two route-client patterns to mirror (v1.1 SHIPPED)

Both live in `analysis/`. They share identical scaffolding (DRY-duplicated today, not factored — Phase 1 of v1.2 should consider extracting a `_route_client_base.py` but that's optional refactor):

| Aspect | `call_shot_analysis.py` (Phase 6) | `call_reid.py` (Phase 7) | v1.2 `call_audio_analysis.py` (recommended) |
|---|---|---|---|
| **Cache granularity** | per-shot `shot_{id:03d}.json` | per-video `video_{vch}.json` | **per-shot `shot_{id:03d}.json`** (SER/MIR/diarization are shot-local) |
| **Cache key** | 4-tuple `(video_content_hash, route_name, route_version)` + implicit shot_id from filename | 4-tuple `(video_content_hash, route_name, route_version)` | 4-tuple `(video_content_hash, route_name, route_version)` + implicit shot_id |
| **Route URL** | `POST /api/v1/production/shot-analysis` | `POST /api/v1/production/character-reid` | `POST /api/v1/production/audio-analysis` |
| **Per-call POST body** | `{video, shots, shot_id_range:[N,N], semantic:true, ...}` | `{video, shots, mask_samples, embedding_model, tau, fps}` (no shot_id_range — cross-shot aggregation) | `{video, shots, shot_id_range:[N,N], stems_dir?, models:[dialogue,music,sfx], language}` |
| **Response envelope** | `{code:200, data:{shots:[<shot>], count}, message}` → take `[0]` | `{code:200, data:{clusters, count, outputDir, crops}, message}` → take `data` whole | `{code:200, data:{shots:[<analysis>], count}, message}` → take `[0]` (mirror shot-analysis) |
| **Schema self-validate before write** | `Draft202012Validator(prompts.schema.json)` | `Draft202012Validator(registry.schema.json)` | `Draft202012Validator(audio_semantic.schema.json)` (NEW) |
| **Warnings sidecar write** | overwrite `route_cache/warnings.json` | **read-merge-write** (preserves `[semantic]` tags, strips prior `[reid]` tags) | **read-merge-write** with `[audio]` tag (mirror call_reid.py — by Phase 6/7/8 there are 2+ steps contributing warnings, non-destructive merge is mandatory) |
| **`--offline` behavior** | preflight skipped, `route_down=True` short-circuits remaining shots, empty facets written | same pattern, empty clusters | same pattern, empty dialogue/music/sfx objects written (all-optional schema) |
| **Poisoned-cache invalidation on schema-validate fail** | not present | present (`call_reid.py:418-427` deletes cache_file on validation fail) | **MANDATORY** (mirror call_reid.py — route emits large nested structures, more corruption surface) |
| **ROUTE_VERSION constant** | `"feat-shot-analysis-route-v1"` | `"deferred-character-reid-route-v1"` | `"audio-analysis-route-v1"` (bump on any route-logic change → cache invalidation) |

### 1.3 SCHEMA_VERSION + sidecar emission pattern (the contract propagation path)

The single-source producer-locked schema literal lives at `scripts/export_asset.py:55`:
```python
SCHEMA_VERSION = "1.1"  # v1.1 = 纯增量 (新增 optional characters/props 数据文件 + 丰富 prompts schema)
```
v1.1 Phase 5/6/7/8 ALREADY proved 4 micro-additions under `"1.1"` (no per-addition bump): `data.characters`/`data.props`/`media.characters[]`/`media.props[]` (Phase 5), `generator.warnings` (Phase 6), `registry-edits.schema.json` (Phase 7), `generator.registry_snapshot` (Phase 8). v1.2's `audio_semantic.json` is a larger logical bundle (new modality) → bumps to `"1.2"` per PROJECT.md:118 decision.

The conditional-emit pattern for OPTIONAL sidecars (`export_asset.py:307-330`):
```python
chars_path = os.path.join(work_dir, "characters.json")
if os.path.isfile(chars_path):
    data_block["characters"] = "characters.json"
# ... byte-identical to v1.0 when file absent (CONTRACT-06 closure)
```
v1.2 reuses this exact pattern for `audio_semantic.json`: `if os.path.isfile(audio_semantic_path): data_block["audio_semantic"] = "audio_semantic.json"`. No new conditional-emit infrastructure needed.

---

## 2. Recommended Architecture: v1.2 Integration

### 2.1 Component boundaries (NEW vs MODIFIED files)

#### NEW producer-side files

| File | Purpose | Mirror of |
|---|---|---|
| `analysis/call_audio_analysis.py` | httpx client → audio-analysis route; per-shot cache; graceful-degrade; warnings sidecar merge | `analysis/call_shot_analysis.py` (per-shot pattern) + `call_reid.py` (poisoned-cache + read-merge-write warnings) |
| `audio/gen_audio_prompts.py` (PROMOTED, not new) | existing spike → pipeline producer of layered TTS/music-gen/foley reproduction prompts derived from `audio_semantic.json` | existing `audio/gen_audio_prompts.py:1-399` spike; add `--offline` fallback (producer-only recompute from cached `audio_semantic.json` when route is down) |
| `registry/link_speakers.py` | HITL CLI mapping `spk_NNN → char_NNN|null`; confirmed-only gate (mirror `apply_edits.py` pattern); produces `speakers.json` sidecar | `registry/apply_edits.py` (confirmed-only hard gate) |
| `html/gen_speaker_review.py` | HITL review HTML for spk→char mapping (cluster-like cards with character dropdown) | `html/gen_registry_review.py` (cosine-sorted queue + cards + export button) |
| `spec/schemas/audio_semantic.schema.json` | top-level object schema for `audio_semantic.json` (3 modalities × layered reproduction prompts) | `spec/schemas/audio_analysis.schema.json` (per-shot object schema) + `registry.schema.json` (top-level object with array) |
| `spec/schemas/speakers.schema.json` | `speakers.json` mapping table schema (`spk_NNN → char_NNN|null` + display_name); pipeline-internal until confirmed, but IS canonical asset data (unlike `registry.draft.json`) | `spec/schemas/characters.schema.json` (`^char_[0-9]{3}$` pattern reuse) |
| `spec/schemas/speaker-edits.schema.json` | HITL round-trip shape for `gen_speaker_review.py` → `link_speakers.py` (merge_groups/renames/confirm_ids/reject_ids) | `spec/schemas/registry-edits.schema.json` |
| `spec/fixtures/v1.2/*` | NEW 11-file fixture set: copy v1.1 (10 files) + add `audio_semantic.json` + `speakers.json` + extend `asset.json` with `data.audio_semantic` + `data.speakers` | `spec/fixtures/v1.1/*` (v1.1 was 10 files, v1.0 substrate + 4 new) |
| `scripts/verify_phase_audio_smoke.py` | N-scenario regression harness (route-down / --skip-audio-semantic / cache-hit-offline / poisoned-cache / spk→char linking) | `scripts/verify_phase7_smoke.py` (5-scenario) |

#### MODIFIED producer-side files

| File | Change | Existing pattern referenced |
|---|---|---|
| `run_pipeline.py` | (1) Add `step_audio_semantic(...)` after `step_reid`, before `step_timeline`. (2) Renumber 17 `[N/8]` → `[N/9]` (grep-precise, mirror v1.1 Phase 6/7 renumbers). (3) Add CLI flags `--skip-audio-semantic` / `--audio-url` (default `http://127.0.0.1:8000/api/v1/production/audio-analysis`) / `--audio-timeout` (default 960s > route-side 900s). (4) `--force` cache list extension to include `audio_semantic.json` + `speakers.json` + `audio_semantic.json.video-stamp` + `route_cache/audio_analysis/` (mirror Phase 6/7 cache list at `run_pipeline.py:578-592`). (5) Add `--skip-speaker-link` flag (mirror `--skip-reid` non-blocking pattern). | Phase 6 `step_semantic` wiring (lines 163-232); Phase 7 `step_reid` (lines 235-313) |
| `run_pipeline.py:step_timeline` | Pass `--audio-semantic` and `--speakers` to `gen_timeline_html.py` (extend existing `--characters`/`--props`/`--asset-json` block at lines 380-391); add `audio_semantic.json` + `speakers.json` to `inputs[]` mtime cache list (Pitfall 9 prevention, mirror Phase 8 prompts_json addition at lines 352-353) | Phase 8 wiring at `run_pipeline.py:316-393` |
| `scripts/export_asset.py` | (1) `SCHEMA_VERSION = "1.1"` → `"1.2"` (line 55). (2) In `build_asset_dict`: add `if os.path.isfile(audio_semantic_path): data_block["audio_semantic"] = "audio_semantic.json"` (mirror lines 312-318). (3) Same conditional for `speakers.json`. (4) Extend `_build_registry_snapshot` OR add `_build_speaker_snapshot` to embed speaker→character mapping in `generator` block (optional, defer if too heavy). | Phase 7 CONTRACT-06 conditional emit (lines 307-318); Phase 8 PROMPT-04 registry_snapshot (lines 349-375) |
| `spec/schemas/asset.schema.json` | Add `data.audio_semantic` (optional string path) + `data.speakers` (optional string path) under `data.properties`. NO changes to `required[]`. NO changes to `media.*` (audio_semantic + speakers are JSON, not media). | v1.1 additive pattern at `asset.schema.json:144-153` |
| `spec/schemas/prompts.schema.json` | OPTIONAL (decision in Phase 6): add `audio_prompt_text` (string) for the layered reproduction prompt joined into the existing `prompt_text` re-compose — OR keep audio prompts entirely in `audio_semantic.json#shots[].reproduction.{tts,music_gen,foley}`. **Recommendation: keep separate** (different consumers — prompts.json is for video-gen, audio_semantic reproduction is for audio-gen). NO CHANGES to prompts.schema.json. | v1.1 additive `character_refs`/`prop_refs` at prompts.schema.json:70-85 |
| `spec/validate.py` | (1) Add `V12_FIXTURE_DIR` + `V12_FIXTURE_MAP` + `V12_ORDER` (12 shapes: 10 from v1.1 + audio_semantic + speakers). (2) Add `validate_v12()` function. (3) Wire `validate_v12()` into `main()` between `validate_v11()` and `validate_smoke()`. (4) Bump shape count in error messages. | v1.1 `V11_ORDER` at `validate.py:54-71` (v1.0 was 6 → v1.1 was 10, v1.2 → 12) |
| `scripts/verify_contract.py` | (1) Extend `_cross_version_check` to cover v1.1↔v1.2 (forward: v1.1 fixture vs v1.2 schema, 0 errors; backward: v1.2 fixture vs v1.1 schema, only additionalProperties errors). (2) Extend `_fixture_consistency_check` for `audio_semantic.shots[].shot_id ⊆ shots[].id` + `dialogue.segments[].speaker_id ⊆ speakers[].speaker_id` (if speakers.json present) + `speakers[].char_id ⊆ characters[].id` (Pitfall 17 dangling-prevention for spk→char). (3) Extend `_recover_v1_schema` for v1.1→v1.2 strip (programmatic removal of `data.audio_semantic`/`data.speakers` keys). (4) Bump `EIGHT_SHAPES` → `TWELVE_SHAPES` (or add `V12_SHAPES` constant). | v1.1 `_cross_version_check` at lines 319-385 + `_fixture_consistency_check` at lines 388-440 |
| `spec/SPEC.md` | (1) §4 Changelog: add `1.2` entry dated 2026-XX-XX, additive-only statement, list of new files. (2) §5: add §5.8 Audio Semantic + §5.9 Speakers sub-sections. (3) §3 manifest table: add `data.audio_semantic` + `data.speakers` rows. (4) §1 schema index: add 3 new schemas (audio_semantic, speakers, speaker-edits). | v1.1 §4 Changelog entry at SPEC.md:161-168 |
| `html/gen_timeline_html.py` | (1) Add `--audio-semantic` flag (mirror existing `--characters`/`--props` wiring at lines 380-391 of run_pipeline). (2) Render dialogue/music/sfx chips in shot rows (mirror PRESENT-01 character gallery + PRESENT-02 reference chip from Phase 8). (3) Add speaker label chip linking to character (when `speakers.json` mapping resolves). | Phase 8 gallery/chip work in `gen_timeline_html.py` |
| `PROJECT.md` | Update "Current Milestone" → "Last Shipped"; move SPEAKER-01 from Out of Scope (line 78: "v1.2 进 scope") into Active→Validated. | v1.1 milestone roll-forward pattern |
| `.planning/REQUIREMENTS.md` | CREATE (does not exist yet for v1.2). REQ-ID prefixes: ROUTE / DIALOGUE / MUSIC / SFX / CONTRACT / CONSUMER / SPEAKER. **CRITICAL: avoid collision with archived v1.1 SPEAKER-01** — the v1.1 REQUIREMENTS list "SPEAKER-01" under v2 (lines 95-97); reuse that exact ID as the v1.2 requirement closure (formal scope-in). | v1.1 REQUIREMENTS archived at `milestones/v1.1-REQUIREMENTS.md` |

#### NEW consumer-side files (cross-repo `kais-aigc-platform`)

| File | Change | Mirror of |
|---|---|---|
| `packages/infinite-canvas/src/utils/import-from-dir.ts` | (1) `SHOT_TIMELINE_KNOWN_VERSIONS`: append `"1.2"` (line 898 v1.1 precedent). (2) `extractShotTimelineArtifacts` §7 post-process: extend to emit audio-semantic child nodes when v1.2 detected — 1 dialogue + 1 music + 1 sfx node per shot where present, `type:"asset"` + `assetType:"dialogue"|"music"|"sfx"` (mirror v1.1 PRESENT-04 character/prop node emission at feat/canvas-asset-collection). | v1.1 Phase 9 PRESENT-04/05 |
| `packages/infinite-canvas/src/components/AssetNode.tsx` | `typeIcons` cosmetic extension: `dialogue:"💬"` / `music:"🎵"` / `sfx:"🔊"` (mirror v1.1 character:"🧑"/prop:"🔧" at PRESENT-05) | v1.1 PRESENT-05 |
| `verify-canvas-shot-timeline.ts` | Extend assertion counts for v1.2 audio nodes (mirror v1.1 27→29 assertion bump) | v1.1 PRESENT-05 |

#### NEW route-side files (cross-repo `kais-aigc-platform`, route deferred per PROJECT.md:118)

| File | Purpose |
|---|---|
| `src/routes/production/audio-analysis/index.ts` | Express route thin-wrapper (mirror `shot-analysis/index.ts`); accepts `{video, shots, shot_id_range, stems_dir?, models, language}`; calls driver |
| `src/routes/production/audio-analysis/driver/audio_analysis_driver.py` | Per-shot orchestrator: ffmpeg extract segment → run WhisperX (transcribe+align+diarize) on vocals stem → run SER on vocal segments → run MIRFLEX on `drums+bass+other` mix → compose layered reproduction prompts → return envelope |
| (deferred) | Live route round-trip (mirror v1.1 deferred items in PROJECT.md:67-69) |

### 2.2 Data flow (end-to-end v1.2)

```
                                         ┌─── kais-aigc-platform route (DEFERRED) ───┐
                                         │  POST /api/v1/production/audio-analysis    │
                                         │  driver: WhisperX + pyannote + SER +       │
                                         │           MIRFLEX + MERT                   │
                                         └────────────────────────────────────────────┘
                                                          ▲
                                                          │ httpx (per-shot)
                                            ┌─────────────┴──────────────┐
                                            │ analysis/call_audio_       │
                                            │ analysis.py                │
                                            │ (per-shot cache +          │
                                            │  graceful-degrade +        │
                                            │  warnings sidecar merge)   │
                                            └─────────────┬──────────────┘
                                                          │
  [1/9] ensure_h264      ──┐                              │
  [2/9] step_detect       ├─→ shots.json ──────────────┐  │
  [3/9] step_separate     │   audio_analysis.json      │  │
  [4/9] step_transcribe   │   stems/htdemucs/<stem>/  ─┼──┼─→ (stems_dir passed to route)
  [5/9] step_semantic     │   transcript.json          │  │
  [6/9] step_reid         │   registry.draft.json      │  │
       apply_edits (HITL) │   characters.json ─────────┼──┼─→ (for SPEAKER-01 linking)
                         ─┘   props.json               │  │
                                                          │
  [7/9] step_audio_semantic ←─ audio_semantic.json ←──────┘
       link_speakers (HITL) ←─ speakers.json
                                                         │
  [8/9] step_timeline ←──── audio_semantic.json + speakers.json + prompts.json
                           ↓
                           timeline.html (gallery: dialogue/music/sfx chips +
                                          speaker→character linkage)
                         │
  [9/9] step_export ←──── audio_semantic.json + speakers.json
                           ↓
                           asset.json (schema_version="1.2",
                                       data.audio_semantic + data.speakers
                                       conditionally emitted)
```

**Critical ordering rationale:**
- `step_audio_semantic` AFTER `step_reid`: SPEAKER-01 → char_NNN linking requires `characters.json` (produced by `apply_edits.py` after `step_reid`'s HITL review). If audio-analysis ran first, route emits `spk_NNN`; reviewer could not link to characters yet.
- `step_audio_semantic` BEFORE `step_timeline`: HTML gallery needs audio_semantic + speakers to render dialogue/music/sfx chips + speaker linkage.
- `step_audio_semantic` BEFORE `step_export`: asset.json conditionally references `audio_semantic.json` + `speakers.json`.
- `link_speakers` (HITL) is non-blocking: `step_audio_semantic` writes `audio_semantic.json` with raw `spk_NNN` IDs and exits. `link_speakers.py` is a standalone CLI (mirror `apply_edits.py`), operator runs after HTML review.

---

## 3. The Route Contract (REQUEST/RESPONSE envelope)

### 3.1 REQUEST shape (mirror shot-analysis per-shot pattern)

```json
POST /api/v1/production/audio-analysis
{
  "video":      "<host abs path>",
  "shots":      "<host abs path>/shots.json",
  "shot_id_range": [N, N],
  "stems_dir":  "<host abs path>/stems/htdemucs/<video-stem>/",
  "models":     ["dialogue", "music", "sfx"],
  "language":   "zh",
  "fps":        24,
  "vocals_target_sr":  16000,
  "music_target_sr":   22050
}
```

**Stem routing (route-internal, NOT producer-side decision):**
- **Dialogue modality** (WhisperX + pyannote + SER) operates on **vocals stem** (Demucs already isolates speech). 16 kHz mono re-extract from vocals.wav (mirror `audio/transcribe.py:14-16 kHz mono WAV extraction`). Route does NOT see the original mix for dialogue — vocals stem improves diarization precision significantly (WhisperX+pyannote on raw mix gets cross-talk bleed).
- **Music modality** (MIRFLEX + MERT) operates on **`drums+bass+other` mixdown**. The route mixes the 3 non-vocal stems back together (simple ffmpeg amix or numpy sum). Vocals are excluded to prevent MIR key/tempo detection from locking onto vocal melody rather than harmonic backing.
- **SFX modality** operates on **`other` stem** (Demucs isolates non-vocal non-musical content here — footsteps, wind, doors). Optionally cross-check against `drums` for rhythm-anchored SFX (gunshots synced to drum hits).

**`stems_dir` is OPTIONAL but RECOMMENDED**: producer already has Demucs output from `step_separate`. Passing `stems_dir` saves the route from re-running Demucs server-side (~1 min/ep on GPU, ~30 min/ep on CPU). If `stems_dir` absent or stems missing, route falls back to its own Demucs pass on the `video` path.

**`shot_id_range: [N,N]` is per-shot isolation** (mirror Phase 6 `call_shot_analysis.py:341`). Avoids route recomputing full-video analysis on each call; lets producer parallelize (TODO optimization, not Phase 1).

### 3.2 RESPONSE envelope (mirror shot-analysis)

```json
{
  "code": 200,
  "data": {
    "shots": [
      {
        "shot_id": 1,
        "dialogue": {
          "language": "zh",
          "segments": [
            {
              "start": 0.12, "end": 1.84,
              "speaker_id": "spk_001",
              "emotion": "neutral",
              "text": "你好世界",
              "words": [
                {"word": "你好", "start": 0.12, "end": 0.74, "score": 0.98},
                {"word": "世界", "start": 0.78, "end": 1.84, "score": 0.97}
              ]
            }
          ]
        },
        "music": {
          "tempo_bpm": 96,
          "key": "C major",
          "instruments": ["piano", "strings", "synth_pad"],
          "valence_arousal": {"valence": 0.62, "arousal": 0.41},
          "presence": "background",
          "coverage": 0.85
        },
        "sfx": {
          "description": "gentle wind, distant bird call",
          "onset_times_sec": [0.5, 2.3, 4.1],
          "confidence": 0.78
        },
        "reproduction": {
          "tts":       "neutral emotion 女声普通话，语速中等",
          "music_gen": "calm piano in C major, 96bpm, valence 0.62, arousal 0.41, piano/strings/synth_pad",
          "foley":     "gentle wind bed + distant bird call at 0.5s/2.3s/4.1s"
        }
      }
    ],
    "count": 1,
    "models_used": {
      "dialogue": "whisperx-large-v3+pyannote-3.1+chinese-hubert-ser",
      "music":    "mirflex-v1+mert-95M",
      "sfx":      "audiosep-llama-qwen2"
    }
  },
  "message": "Audio analysis complete for shot 1"
}
```

**Per-shot modality optionality:** any of `dialogue`/`music`/`sfx` may be absent (null) when the modality detects no signal (e.g. silent shot → no dialogue; pure-dialogue shot → no music). Producer-side `compose_audio_semantic_entry()` must tolerate missing modalities — schema makes all 3 optional per shot.

**`reproduction` is the layered TTS/music-gen/foley prompt bundle** (replaces v1.0 single-NL-prompt `audio_prompts.json` spike at `audio/gen_audio_prompts.py:218-231`). Producer emits all 3 always (even if modality is absent → emit "silence" / "no music" / "quiet" prompt) so downstream generators have a complete recipe.

---

## 4. `audio_semantic.json` Sidecar Schema Shape

### 4.1 Top-level shape (additive optional, byte-identical-absent)

```json
{
  "generated_at": "2026-08-01T12:34:56Z",
  "video_content_hash": "abc1234def5678",
  "models": {
    "dialogue": "whisperx-large-v3+pyannote-3.1+chinese-hubert-ser",
    "music":    "mirflex-v1+mert-95M",
    "sfx":      "audiosep-llama-qwen2"
  },
  "language": "zh",
  "shots": [
    {
      "shot_id": 1,
      "start_sec": 0.0,
      "end_sec": 6.73,
      "duration": 6.73,
      "dialogue":  { /* schema object, OPTIONAL per shot */ },
      "music":     { /* schema object, OPTIONAL per shot */ },
      "sfx":       { /* schema object, OPTIONAL per shot */ },
      "reproduction": {
        "tts":       "...",   // required string (emit "silence" if no dialogue)
        "music_gen": "...",   // required string
        "foley":     "..."    // required string
      }
    }
  ]
}
```

### 4.2 Schema design constraints (mirror v1.1 precedent)

- **`additionalProperties: false`** on every object — strict-schema × lenient-consumer (SPEC.md:135-137).
- **All per-shot modality objects OPTIONAL** — absent when route degrades or modality not requested (`models: ["dialogue"]` → only dialogue populated).
- **`shots[].shot_id` MUST align 1:1 with `shots.json#id`** — mirror `audio_analysis.schema.json:32-34` constraint; enforce in `_fixture_consistency_check`.
- **`speakers.json` is a SEPARATE sidecar** — decouples route output (always has `spk_NNN` IDs) from HITL linking (resolves spk→char). `speakers.json` references both ID spaces.
- **`reproduction` is required when `audio_semantic.json` is emitted at all** — producer always emits some prompt string per modality (even "silence") so downstream generators have a complete recipe.

### 4.3 `speakers.json` sidecar (SPEAKER-01 closure)

```json
[
  {
    "speaker_id": "spk_001",
    "char_id": "char_001",
    "display_name": "少女",
    "review_state": "confirmed",
    "shot_ids": [1, 2, 5, 8]
  },
  {
    "speaker_id": "spk_002",
    "char_id": null,
    "display_name": "旁白",
    "review_state": "confirmed",
    "shot_ids": [3, 7]
  }
]
```

- **`speaker_id` pattern**: `^spk_[0-9]{3}$` (new ID space, mirror `^char_[0-9]{3}$`/`^prop_[0-9]{3}$`).
- **`char_id` is NULLABLE** — pyannote may detect speakers that don't map to any re-id character (e.g. off-screen narrator, crowd ambient). NULL is a valid resolved state.
- **`review_state`** enum: `proposed` (default from route output) / `confirmed` (HITL) / `rejected` (soft-delete ID for reference integrity — mirror characters.schema.json Pitfall 17).
- **`char_id` MUST be a confirmed `characters.json#id`** — `_fixture_consistency_check` enforces; non-null `char_id` ⊆ `characters.json#id` where `review_state=="confirmed"` (Pitfall 7 second-line at producer level).

---

## 5. Schema 1.1 → 1.2 Bump Propagation Path

### 5.1 The 6 mechanical touchpoints (locked by v1.1 Phase 5 precedent)

| # | File | Change | v1.1 precedent location |
|---|---|---|---|
| 1 | `scripts/export_asset.py:55` | `SCHEMA_VERSION = "1.1"` → `"1.2"` | v1.0→v1.1 at same line (PROJECT.md:116 "schema_version `"1.1"` producer-locked via SCHEMA_VERSION constant") |
| 2 | `spec/schemas/asset.schema.json` | Add `data.audio_semantic` + `data.speakers` under `data.properties`; NOT in `required[]` | v1.1 added `data.characters`/`data.props` at lines 144-153 |
| 3 | `spec/schemas/audio_semantic.schema.json` (NEW) + `speakers.schema.json` (NEW) + `speaker-edits.schema.json` (NEW) | 3 new schemas | v1.1 added 3 new schemas (characters/props/registry) + 1 (registry-edits) in Phase 7 |
| 4 | `spec/validate.py` | Add `V12_FIXTURE_DIR` + `V12_FIXTURE_MAP` + `V12_ORDER` (12 shapes) + `validate_v12()` + wire into `main()` | v1.1 added `V11_FIXTURE_*` at lines 54-71 |
| 5 | `scripts/verify_contract.py` | Extend `_cross_version_check` for v1.1↔v1.2; extend `_fixture_consistency_check` for audio_semantic + speakers; extend `_recover_v1_schema` (or add `_recover_v11_schema`) for programmatic strip; bump shape constant | v1.1 extended these at lines 275-385 (cross-version) + 388-440 (consistency) |
| 6 | `spec/SPEC.md` | §4 Changelog `1.2` entry; §5.8 audio_semantic + §5.9 speakers shapes; §3 manifest rows; §1 schema index | v1.1 §4 entry at lines 161-168 |

### 5.2 Cross-version bidirectional proof (extend `_cross_version_check`)

Mirror v1.1's CONTRACT-07 bidirectional compat proof at `verify_contract.py:319-385`:

- **FORWARD v1.1 → v1.2**: `spec/fixtures/v1.1/*` (10 files) loaded against CURRENT v1.2-extended schemas → MUST yield 0 errors. Proves additive extension didn't break v1.1 assets (Pitfall 11 prevented).
- **BACKWARD v1.2 → v1.1**: `spec/fixtures/v1.2/*` (12 files) loaded against `_recover_v11_schema()` (programmatic strip of `data.audio_semantic`/`data.speakers` keys from asset.schema.json) → MUST yield ONLY `additionalProperties` errors (filter them out, then 0 non-additive errors). Proves shared fields didn't drift semantically.

The v1.1→v1.2 strip in `_recover_v11_schema(shape="asset")` is the mirror of `_recover_v1_schema` at `verify_contract.py:306-316`:
```python
if shape == "asset":
    data_props = stripped.get("properties", {}).get("data", {}).get("properties", {})
    for k in ("audio_semantic", "speakers"):   # v1.2 additive keys
        data_props.pop(k, None)
```

### 5.3 Graceful-degrade byte-identical path (CRITICAL for v1.0/v1.1 compat)

The v1.2 contract MUST keep `asset.json` byte-identical to v1.1 in 3 scenarios (Pitfall: silent field drift breaks consumers at rest):

1. **Audio-analysis route down** (`--offline` + cache miss, or preflight fail):
   - `call_audio_analysis.py` writes `audio_semantic.json` with `shots:[]` (empty array — schema-legal, mirrors `registry.draft.json` empty-clusters degrade in `call_reid.py:402-410`)
   - `speakers.json` is NOT written (no spk IDs to map)
   - `export_asset.py` conditional emit: `if os.path.isfile(audio_semantic_path)` is True (empty file still exists) → `data_block["audio_semantic"] = "audio_semantic.json"`
   - **decision required**: should empty `audio_semantic.json` be referenced in `asset.json` or omitted? **Recommendation: omit empty file too** — mirror characters/props "absent when no content" rule (CONTRACT-06 closure, `export_asset.py:312-318`). `call_audio_analysis.py` should NOT write the file on full-degrade; only write warnings sidecar.

2. **`--skip-audio-semantic` flag**:
   - `step_audio_semantic` short-circuits, no file written, `export_asset.py` omits `data.audio_semantic` → asset byte-identical to v1.1.4.

3. **No dialogue/music/sfx detected on a particular shot** (route up, but modality empty):
   - `audio_semantic.json` IS written with `shots: [...]` where each shot has `dialogue/music/sfx` OPTIONAL fields omitted (null-absent) but `reproduction` populated with "silence"/"no music"/"quiet" — schema-valid, asset still references file. NOT byte-identical to v1.1 (file IS referenced) but content clearly signals degrade via `reproduction` strings.

**The graceful-degrade "byte-identical" guarantee is for the FILE-PRESENCE level**, not field-content level: route-down → file absent → asset byte-identical to v1.1; route-up-with-empty-modality → file present with empty-but-valid content → asset references it. This mirrors v1.1 `characters.json` rule precisely (`export_asset.py:312-318` comments).

---

## 6. SPEAKER-01 → Character Registry Linkage

### 6.1 Why a NEW ID space + sidecar (NOT direct `char_NNN` emission from route)

| Option | Why rejected |
|---|---|
| Route emits `speaker_id: "char_001"` directly | Route has no `characters.json` context (registry is HITL-produced later); would couple route availability to confirmed registry. Also breaks when re-id hasn't run yet (`step_audio_semantic` slot 7 runs after `step_reid` slot 6 + `apply_edits`, but `apply_edits` is non-blocking standalone CLI). |
| Reuse `^char_[0-9]{3}$` for speakers | Conflates two identity signals (visual re-id from DINOv2 vs audio diarization from pyannote). Same character may have multiple speakers (voice actor change); same speaker may play multiple characters (one actor voicing two roles). |
| Producer-side heuristic auto-map (face ↔ voice) | High-error: face not visible (off-screen narrator) → no face embedding; two faces visible (over-shoulder shot) → ambiguous. Auto-mapping at producer time bakes errors into asset. |

**Decision (mirror v1.1 re-id decision in PROJECT.md:115):** pyannote emits raw speaker labels (`spk_NNN` normalized); a NEW HITL step `registry/link_speakers.py` lets the reviewer map each `spk_NNN` to `char_NNN|null`; output is `speakers.json` canonical sidecar; consumer resolves at render time (render speaker label always; link to character only if `char_id` non-null).

### 6.2 Reuse of v1.1 apply_edits / gen_registry_review infrastructure

| v1.1 component (Phase 7) | v1.2 reuse |
|---|---|
| `registry/apply_edits.py` confirmed-only hard gate | `registry/link_speakers.py` confirmed-only hard gate (`speakers.json#review_state=="confirmed"` only) |
| `registry/apply_edits.py` idempotent apply (fixed-order deterministic) | `link_speakers.py` idempotent: same `audio_semantic.json` + same `registry.edits.json` → same `speakers.json` |
| `html/gen_registry_review.py` HITL HTML (cosine-sorted queue + cards + export edits) | `html/gen_speaker_review.py` HITL HTML (speaker cards sorted by shot_count desc + character dropdown per speaker + export edits button) |
| `spec/schemas/registry-edits.schema.json` round-trip shape | `spec/schemas/speaker-edits.schema.json` round-trip shape (merge_speakers/renames/confirm_ids/reject_ids/char_overrides) |
| `verify_contract.py:_producer_registry_integrity` second-line assert | Extend to assert `speakers.json#char_id ⊆ characters.json#id` (when speakers.json present) — Pitfall 17 reference-integrity enforcement |

### 6.3 SPEAKER-01 scope-in (formal closure of v1.1 deferral)

v1.1 REQUIREMENTS explicitly deferred this (`milestones/v1.1-REQUIREMENTS.md` v2 list, lines 95-97: "SPEAKER-01: 对白→说话人归属（谁说了哪句台词）"). v1.2 PROJECT.md:78 promotes it: "v1.1 曾因「大 lift（需说话人识别/唇形对齐）」列为 Out of Scope，v1.2 借 pyannote 路由化降 lift". **Recommendation:** v1.2 REQUIREMENTS.md should reuse the exact REQ-ID `SPEAKER-01` (not renumber) to make the scope-in traceable in audit.

---

## 7. Consumer Node Emission (mirror v1.1 Phase 9 §7 buildPhaseTree)

### 7.1 The single version gate

`import-from-dir.ts:898` has `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1", "1.1"])` (v1.1 Phase 9 added `"1.1"`). v1.2 adds `"1.2"`. The §7 post-process `buildPhaseTree` extension MUST be gated on `KNOWN_VERSIONS.has("1.2")` — older consumers silently skip the new code path with only a graceful-degrade warning per SPEC §4 (verified behavior at v1.0/v1.1 boundary).

### 7.2 Node emission shape (mirror PRESENT-04 character/prop pattern)

For each shot with non-null modality, emit child nodes:
```typescript
// pseudo-TypeScript extending extractShotTimelineArtifacts §7 post-process
if (manifest.schema_version === "1.2" || KNOWN_VERSIONS.has("1.2")) {
  for (const shot of audioSemantic.shots) {
    if (shot.dialogue) {
      nodes.push({type:"asset", assetType:"dialogue",
                  parentId: storyboardNodeId[shot.shot_id],
                  data: {speaker_id, char_id, emotion, text_excerpt}});
    }
    if (shot.music) {
      nodes.push({type:"asset", assetType:"music",
                  parentId: storyboardNodeId[shot.shot_id],
                  data: {tempo_bpm, key, instruments, valence_arousal}});
    }
    if (shot.sfx) {
      nodes.push({type:"asset", assetType:"sfx",
                  parentId: storyboardNodeId[shot.shot_id],
                  data: {description, onset_times}});
    }
  }
}
```

- `type:"asset"` + `assetType:"<modality>"` reuses existing asset node renderer — NO custom renderer, NO Zod contract bump (mirror v1.1 PRESENT-04 closure).
- `AssetNode.tsx` `typeIcons` cosmetic addition: `dialogue:"💬"` / `music:"🎵"` / `sfx:"🔊"` (mirror PRESENT-05 character:"🧑"/prop:"🔧").
- `verify-canvas-shot-timeline.ts` extends assertion counts (v1.1 was 27/29; v1.2 should be ~35+ depending on fixture shot count × modality coverage).

### 7.3 Speaker → character cross-node reference (optional canvas enhancement)

When `speakers.json` resolves `spk_NNN → char_NNN`, canvas MAY emit an `appearance` edge between the dialogue node and the character node (deferred — v1.1 defers `CANVAS-EDGE-01` for visual clutter reasons; same defer applies here).

---

## 8. Suggested Phase / Build Order (Phase 1 = Risk-Validation)

**Strict mirror of v1.1 sequencing that worked (PROJECT.md:121 "Phase 1 先做模型 risk-validation 再锁契约")** — contract AFTER model validation, consumer LAST.

### Phase 1 — Route Scaffolding + Model Risk-Validation Spike (NO contract changes)

**Goal:** De-risk the highest unknowns (Chinese SER cross-domain, MIR precision on multi-stem, WhisperX+pyannote drift) on 1 real episode BEFORE locking any schema.

**Activities (mirror v1.1 Phase 7 DINOv2 τ spike):**
- Stand up minimal route stub in kais-aigc-platform (echo request, no ML yet) — prove httpx round-trip + per-shot cache pattern
- Run WhisperX+pyannote+SER on 1 episode vocals stem; document Chinese SER precision/recall vs English benchmark
- Run MIRFLEX+MERT on 1 episode `drums+bass+other` mixdown; document instrument-ID precision + tempo/key accuracy
- Spike output: empirical findings document (cosine-distribution analog for SER confidence; instrument confusion matrix; latency/VRAM profile per shot)
- Decision points locked: which models per modality, `models_used` strings, modality-specific thresholds (e.g. SER confidence ≥ X to emit emotion label, else emit "neutral")

**Output:** `.planning/research/audio-spike-report.md` (or similar). NO schema changes, NO producer changes.

**Exit criteria:** empirical proof that route output is good enough to base a contract on; locked `models_used` strings.

### Phase 2 — Contract v1.2 (schemas + SPEC + fixtures + validate + verify_contract)

**Goal:** Lock the v1.2 contract BEFORE any producer code writes against it — so all downstream field names, ID patterns, and the `schema_version: "1.2"` literal are frozen.

**Mirror v1.1 Phase 5 contract-first pattern.** Activities:
- Create 3 new schemas: `audio_semantic.schema.json` + `speakers.schema.json` + `speaker-edits.schema.json`
- Extend `asset.schema.json` additively (`data.audio_semantic` + `data.speakers`)
- Bump `SCHEMA_VERSION` constant `"1.1"` → `"1.2"`
- Create `spec/fixtures/v1.2/` 12-file set (copy v1.1 10 + 2 new + extend asset.json)
- Extend `spec/validate.py` (V12_ORDER) + `scripts/verify_contract.py` (_cross_version_check v1.1↔v1.2, _fixture_consistency_check spk→char integrity)
- Update `SPEC.md` §4 Changelog + §5.8/§5.9 + §3 manifest rows + §1 schema index

**Exit criteria:** v1.1 fixture still 10/10 green under v1.2 schema; v1.2 fixture 12/12 green; bidirectional cross-version proof 0 errors.

### Phase 3 — Producer Route Client (`analysis/call_audio_analysis.py`)

**Goal:** Producer-side httpx client mirrors `call_shot_analysis.py` per-shot pattern + `call_reid.py` poisoned-cache + read-merge-write warnings pattern.

**Activities:**
- Build `call_audio_analysis.py` from `call_shot_analysis.py` template (per-shot loop, 4-tuple cache key, preflight short-circuit, graceful-degrade to empty `shots:[]`)
- Add poisoned-cache invalidation on schema-validate fail (mirror `call_reid.py:418-427`)
- Read-merge-write warnings sidecar with `[audio]` tag (mirror `call_reid.py:443-449`)
- Lock route REQUEST body shape (stems_dir optional, models list, language)
- 3-modality response normalization (defense-in-depth isinstance guards — mirror `call_shot_analysis.py:139-148` `compose_facets` robustness)

**Exit criteria:** smoke test against Phase 1 route stub shows per-shot cache hits/misses correct; warnings sidecar merges cleanly with existing `[semantic]` + `[reid]` tags.

### Phase 4 — SPEAKER-01 Linkage HITL (`registry/link_speakers.py` + `html/gen_speaker_review.py`)

**Goal:** Close SPEAKER-01 deferral from v1.1.

**Mirror v1.1 Phase 7 producer-side (Plan 03).** Activities:
- `html/gen_speaker_review.py`: speaker cards sorted by `shot_ids.length` desc; character dropdown per speaker (filtered to `characters.json#review_state=="confirmed"`); export edits button → `speaker.edits.json`
- `registry/link_speakers.py`: confirmed-only hard gate (mirror `apply_edits.py`); idempotent apply; produces `speakers.json`
- Extend `scripts/verify_contract.py:_producer_registry_integrity` for `speakers.json#char_id ⊆ characters.json#id` assertion

**Exit criteria:** end-to-end HITL round-trip `audio_semantic.json` + `characters.json` → review HTML → `speaker.edits.json` → `speakers.json` (only confirmed mappings).

### Phase 5 — Pipeline Integration (`run_pipeline.py:step_audio_semantic` slot 7/9)

**Goal:** Wire `step_audio_semantic` into `run_pipeline.py`; renumber `[N/8]`→`[N/9]` (17 instances).

**Mirror v1.1 Phase 6/7 pipeline wiring.** Activities:
- Add `step_audio_semantic(...)` function (mirror signature of `step_semantic` at lines 163-232)
- Insert call after `step_reid` (line 625), before `step_timeline` (line 630)
- Renumber 17 `[N/8]` → `[N/9]` (grep-precise)
- Add CLI flags: `--skip-audio-semantic`, `--audio-url`, `--audio-timeout`, `--skip-speaker-link`
- Extend `--force` cache list (mirror Phase 6/7 extension at lines 578-592) to include `audio_semantic.json`, `audio_semantic.json.video-stamp`, `speakers.json`, `route_cache/audio_analysis/`
- Build `scripts/verify_phase_audio_smoke.py` N-scenario regression (route-down / --skip-audio-semantic / cache-hit-offline / poisoned-cache / spk-link-confirmed-only)
- Extend `step_timeline` inputs list with `audio_semantic.json` + `speakers.json` (Pitfall 9 prevention — mtime cache miss on regeneration)

**Exit criteria:** all N smoke scenarios pass; `--force` clears all v1.2 cache; pipeline produces `asset.json` with `schema_version: "1.2"`.

### Phase 6 — Layered Reproduction Prompts (promote `audio/gen_audio_prompts.py` spike)

**Goal:** Promote existing spike `audio/gen_audio_prompts.py:1-399` from sidecar experiment to pipeline producer; add `--offline` fallback that recomputes reproduction prompts from cached `audio_semantic.json` without hitting route.

**Activities:**
- Refactor `gen_audio_prompts.py`: input is now `audio_semantic.json` (not raw `audio_analysis.json` + `transcript.json`); output is `audio_semantic.json#shots[].reproduction` (in-place enrichment, NOT separate `audio_prompts.json` sidecar)
- The 3-string TTS/music-gen/foley composition (mirror existing `compose_prompt` at lines 218-231, extended to 3 strings)
- `--offline` flag: recompute reproduction strings from cached `audio_semantic.json` modalities (route-down path; cache file still has dialogue/music/sfx, just recompute the reproduction layer)

**Exit criteria:** `audio_semantic.json#shots[].reproduction` is deterministic given modalities; offline recompute produces byte-identical output.

### Phase 7 — shot-timeline HTML Gallery Extension

**Goal:** User-visible surface for v1.2 — dialogue/music/sfx chips in timeline HTML + speaker→character linkage chip.

**Mirror v1.1 Phase 8 PRESENT-01/02/03.** Activities:
- `html/gen_timeline_html.py` adds `--audio-semantic` + `--speakers` flags (mirror `--characters`/`--props`/`--asset-json` wiring at lines 380-391)
- Per-shot chip rendering: dialogue chip (speaker label + emotion), music chip (tempo/key/instruments), sfx chip (description excerpt)
- Speaker→character chip: when `speakers.json` resolves `spk_NNN → char_NNN`, render character chip linking to character gallery (mirror Phase 8 PRESENT-02 reference chip)
- XSS hardening: carry Phase 7 CR-04 `_esc` defense verbatim (any user-facing string from route is untrusted)

**Exit criteria:** timeline.html renders all 3 modality chips + speaker linkage; XSS test cases pass.

### Phase 8 — Canvas Consumer Integration (cross-repo)

**Goal:** Consumer v1.2-aware (mirror v1.1 Phase 9).

**Mirror v1.1 Phase 9 PRESENT-04/05/06.** Activities (in `kais-aigc-platform` repo):
- `import-from-dir.ts`: append `"1.2"` to `SHOT_TIMELINE_KNOWN_VERSIONS`; extend `extractShotTimelineArtifacts` §7 post-process for audio-semantic nodes
- `AssetNode.tsx`: `typeIcons` cosmetic (`dialogue:"💬"` / `music:"🎵"` / `sfx:"🔊"`)
- `verify-canvas-shot-timeline.ts`: extend assertions
- `scripts/verify_contract.py` 3-mode harness GREEN for v1.2 (producer / consumer; e2e deferred per v1.1 precedent)

**Exit criteria:** 3-mode `verify_contract.py` green for v1.2 fixture (producer + consumer; e2e deferred).

---

## 9. Phase-Specific Warnings + Pitfall Prevention

| Phase topic | Likely pitfall | Mitigation (anchored in v1.1 precedent) |
|---|---|---|
| Phase 1 (model spike) | Chinese SER cross-domain gives garbage emotions → contract locks wrong enum | Lock `emotion` as `type:string` NOT enum in schema (mirror `registry.schema.json:65-70` `mask_quality` decision — keep flexibility, don't lock enum until empirically calibrated) |
| Phase 2 (contract) | `_recover_v11_schema` programmatic strip misses a key | Use `git show v1.1:spec/schemas/asset.schema.json` as primary, programmatic strip as fallback only (mirror `verify_contract.py:289-297`) |
| Phase 3 (route client) | Producer reads malformed route response (non-dict envelope) → uncaught traceback | All `call_route` access goes through `isinstance(data, dict)` guards (mirror `call_shot_analysis.py:139-148` + `call_reid.py:160-170`) |
| Phase 4 (SPEAKER-01 HITL) | Auto-mapping `spk→char` bakes errors | NO auto-map; HITL mandatory (mirror PROJECT.md:101 re-id decision "接受「够用即可」，不追求全自动") |
| Phase 5 (pipeline) | Banner renumber breaks grep-based phase counters | Grep `\[.\//8\]` first, count occurrences, ensure all renumbered (mirror v1.1 Phase 6 audit "17 [N/6]→[N/7] renumber") |
| Phase 5 (pipeline) | `--force` cache list missing new files → stale cache survives force | Extend the explicit list at `run_pipeline.py:578-592` (DO NOT use directory glob — explicit list is the project convention for auditability) |
| Phase 6 (repro prompts) | Recompose produces different output across runs (non-deterministic) | Fixed key ordering in `json.dump(..., indent=2, ensure_ascii=False)` + deterministic string composition (mirror `prompts/attach_refs.py` "deterministic Pattern 2 recompose" in Phase 8) |
| Phase 7 (HTML) | XSS via route-emitted strings (emotion labels, music descriptions) | `_esc()` helper on EVERY route-derived string interpolated into HTML (mirror Phase 7 CR-04 + Phase 8 `_esc` carry-over) |
| Phase 8 (consumer) | Visual clutter with 3 new chip types per shot | Default-collapse chips into a single "audio" expandable section; per-modality chips revealed on click (deferred decision — visual mockup before commit, mirror v1.1 `CANVAS-EDGE-01` defer reasoning) |

---

## 10. Confidence Assessment

| Area | Confidence | Reason |
|---|---|---|
| Pipeline slot insertion (between reid + timeline) | HIGH | Direct read of `run_pipeline.py:108-490` + ordering constraints from character registry + HTML rendering |
| Route contract envelope (mirror shot-analysis) | HIGH | v1.1 has 2 SHIPPED siblings following this exact envelope pattern (`call_shot_analysis.py:165-217`, `call_reid.py:214-259`) |
| Per-shot caching granularity (NOT per-video) | HIGH | SER/MIR/diarization are shot-local; per-video would force full recompute on any single-shot edit, conflicts with v1.1 Phase 6 cache-invalidation pattern |
| Schema bump 6-touchpoint propagation | HIGH | v1.1 Phase 5 proved the exact pattern; v1.2 is mostly copy-modify |
| SPEAKER-01 → `^spk_[0-9]{3}$` separate ID space + HITL linking | MEDIUM-HIGH | Architecturally sound (decouples route from registry) but the specific HITL UX (dropdown vs free-text) needs Phase 4 user feedback |
| WhisperX integrated vs standalone-pyannote | HIGH | WhisperX repo + WhisperAlign arXiv paper both confirm standalone-pyannote temporal drift; WhisperX's built-in `align()+diarize()` is the correct path |
| Chinese SER precision on animation dialogue | LOW | Phase 1 spike MUST validate this; RAVDESS→Chinese cross-domain gap is the highest unknown per PROJECT.md:121 |
| MIR precision on Demucs-separated stems | MEDIUM | MIRFLEX/MERT validated on clean music tracks; Demucs separation artifacts (vocal bleed in `other` stem, drums in `vocals`) may degrade instrument-ID precision — Phase 1 spike validates |
| Consumer node emission via §7 post-process | HIGH | v1.1 Phase 9 proved the exact pattern (PRESENT-04); `type:"asset"` + `assetType:"<x>"` is the established escape hatch |
| 8-phase ordering with Phase 1 = spike | HIGH | Direct mirror of v1.1 Phase 7 DINOv2 τ spike sequencing + PROJECT.md:121 explicit lock |

---

## 11. Gaps to Address in Phase-Specific Research

- **Phase 1 (spike):** which Chinese SER model? (candidates: chinese-hubert-ser, emotion2vec, SpeechBrain ECAPA-TDNN + Chinese emotion dataset). Phase 1 empirical comparison on 1 episode.
- **Phase 1 (spike):** MIRFLEX vs MERT vs both? MIRFLEX gives structured output (key/chord/tempo/genre); MERT gives embeddings (needs downstream classifier). Recommendation: MIRFLEX primary (structured output ready), MERT for VA embedding (valence-arousal regression head).
- **Phase 2 (contract):** is `speakers.json` a canonical asset data file (in `asset.json#data`) OR pipeline-internal like `registry.draft.json`? **Recommendation: canonical data file** — `speakers.json` is HITL-confirmed output (like `characters.json`), NOT pipeline draft. This makes it `data.speakers` in asset.json.
- **Phase 4 (HITL):** can `speakers.json` reuse the `looks[]` mechanism from `characters.schema.json` (each speaker maps to multiple characters across shots)? Or is `speakers.json#char_id` per-speaker globally? **Recommendation: per-speaker globally** (one speaker maps to at most one character — voice consistency assumption; v1.2 doesn't solve voice-actor-playing-multiple-roles edge case, defer to v2).
- **Phase 6 (repro prompts):** TTS/music-gen/foley prompt dialect — keyword-style or sentence-style? Different generators prefer different formats. **Recommendation: keyword-style with explicit modality tags** (mirror `audio/gen_audio_prompts.py:225-231` `compose_prompt` keyword concat format, which was spiked and validated against audio-gen models in the v1.0 quick task).

---

## 12. Sources

- **Live source code (kais-shot-timeline repo, verified 2026-07-25):**
  - `run_pipeline.py:108-490` — all `step_*` functions + cache patterns + `[N/8]` banner instances
  - `analysis/call_shot_analysis.py:73-424` — per-shot route client pattern (Phase 6 SHIPPED)
  - `analysis/call_reid.py:76-457` — per-video route client pattern + poisoned-cache + read-merge-write warnings (Phase 7 SHIPPED)
  - `scripts/export_asset.py:48-380` — SCHEMA_VERSION constant + conditional sidecar emission (Phase 2/7 SHIPPED)
  - `spec/validate.py:54-71` — V11 fixture set + cross-version validation
  - `scripts/verify_contract.py:275-440` — `_recover_v1_schema` + `_cross_version_check` + `_fixture_consistency_check`
  - `spec/schemas/asset.schema.json:144-153` — v1.1 additive `data.characters`/`data.props` precedent
  - `spec/SPEC.md:158-168` — §4 Changelog `1.1` entry precedent
  - `audio/gen_audio_prompts.py:1-399` — existing spike to be promoted in Phase 6
- **External model documentation (verified 2026-07-25):**
  - [WhisperX (m-bain/whisperx)](https://github.com/m-bain/whisperx) — word-level timestamps + integrated pyannote diarization
  - [WhisperAlign arXiv:2603.04809](https://arxiv.org/html/2603.04809v1) — temporal drift caveat for standalone-Pyannote-alongside-WhisperX
  - [MIRFLEX (AMAAI-Lab/mirflex)](https://github.com/AMAAI-Lab/mirflex) — key/chord/tempo/genre extraction
  - [MERT arXiv:2306.00107](https://arxiv.org/html/2306.00107v5) — self-supervised music understanding, 14 MIR tasks
- **Project planning context:**
  - `.planning/PROJECT.md:11-141` — v1.1 SHIPPED state + v1.2 milestone goals + Key Decisions
  - `.planning/milestones/v1.1-REQUIREMENTS.md:95-97` — SPEAKER-01 v2 deferral that v1.2 closes
  - `.planning/milestones/v1.1-ROADMAP.md` — v1.1 phase sequencing that v1.2 mirrors
