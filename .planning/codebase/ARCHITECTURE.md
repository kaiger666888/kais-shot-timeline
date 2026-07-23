<!-- refreshed: 2026-07-20 -->
# Architecture

**Analysis Date:** 2026-07-20

## System Overview

`kais-shot-timeline` is a single-host, CLI-driven media analysis pipeline that decomposes an input video into per-shot datasets for a downstream video-creation platform. It is orchestrated by `run_pipeline.py`, which invokes a chain of standalone Python stage scripts as subprocesses. The stages communicate **only through JSON files** cached under `output/<video-stem>/`.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                  Orchestrator: `run_pipeline.py`                    │
│   main() parses args → builds work_dir paths → calls step_*() in    │
│   order, each step shells out to a stage script via sys.executable. │
└───────┬──────────────┬──────────────┬──────────────┬───────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐
│  DETECT      │ │  SEPARATE   │ │  TRANSCRIBE  │ │  RENDER HTML     │
│ `detectors/  │ │ `audio/     │ │ `audio/      │ │ `html/           │
│  detect_v3b  │ │  separate_  │ │  transcribe  │ │  gen_timeline_   │
│  .py`        │ │  stems.py`  │ │  .py`        │ │  html.py`        │
└──────┬───────┘ └──────┬──────┘ └──────┬───────┘ └────────┬─────────┘
       │                │               │                  │
       ▼                ▼               ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│            External Binaries (subprocess.run)                    │
│  ffmpeg / ffprobe  │  demucs (python -m demucs)  │  opencv (cv2) │
│  PySceneDetect     │  faster-whisper / openai-whisper            │
└──────────────────────────────────────────────────────────────────┘
       │                │               │                  │
       ▼                ▼               ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│           JSON-Cached Intermediate State (work_dir)              │
│   output/<video-stem>/                                            │
│   ├── shots.json  ├── frames.json  ├── audio_analysis.json      │
│   ├── transcript.json  ├── frames_5fps/  ├── stems/htdemucs/…   │
│   └── timeline.html  (+ prompts.json / prompts.html when run)    │
└──────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Pipeline orchestrator | Drives the 5 stages, manages cache, builds work_dir layout | `run_pipeline.py` |
| AV1 transcode guard | Probes codec, transcodes AV1→H264 so PySceneDetect is stable | `run_pipeline.py:ensure_h264` + `detectors/detect_v3b.py:ensure_h264` |
| V3b shot detector (recommended) | 4-pass fusion: PSD AdaptiveDetector + HistCorr + long-shot scan + dissolve detection | `detectors/detect_v3b.py` |
| V1 shot detector (legacy) | Single-pass PySceneDetect AdaptiveDetector + HTML preview | `detectors/psd_shot_preview_v1.py` |
| V2 shot detector (legacy) | Two-detector coarse+fine pass + fragment merge + HTML preview | `detectors/psd_shot_preview_v2.py` |
| Stem separation + per-shot audio profile | Runs Demucs, computes RMS / spectral centroid / dominant_type per shot | `audio/separate_stems.py` |
| Whisper transcription | Extracts 16 kHz mono wav, runs faster-whisper (fallback openai-whisper) | `audio/transcribe.py` |
| Timeline HTML generator | Merges shots + frames + audio + transcript → self-contained dual-panel HTML | `html/gen_timeline_html.py` |
| Shots grid HTML (alt view) | Simple shot-card grid from any shots JSON | `html/gen_shots_preview.py` |
| Audio analysis HTML (alt view) | Per-shot 4-stem energy bars + dialogue text | `html/gen_audio_html.py` |
| Range-aware static server | Serves timeline.html with proper HTTP 206 Range responses for `<video>` seek | `scripts/serve.py` |

## Pattern Overview

**Overall:** Pipeline orchestrator + standalone stage scripts + JSON-file intermediate cache.

**Key Characteristics:**
- Each stage is a **self-contained CLI script** (argparse + `main()` + `if __name__ == "__main__"`), runnable in isolation. `run_pipeline.py` invokes them via `subprocess.run([sys.executable, "...script.py", ...args])`.
- Stages are **decoupled by JSON contracts** — a stage never imports another stage. It reads its input JSON path from `--shots` / `--audio-json` / etc.
- **Idempotent caching:** every `step_*` in `run_pipeline.py` checks `os.path.exists(out)` before running; `--force` clears the cache. Timeline regenerates only if newer than its inputs (`os.path.getmtime` check).
- **Subprocess-first:** ffmpeg/ffprobe/demucs/whisper are always shelled out, never imported as libraries (except `cv2`, `numpy`, `PIL`, `scenedetect`, which are imported).
- **Self-contained HTML output:** `gen_timeline_html.py` inlines all CSS/JS/data (base64 thumbnails, JSON-embedded shot/stem/transcript arrays) into a single `.html` file. Stem `.wav` files remain external siblings.

## Layers

**Orchestration layer:**
- Purpose: Parse CLI args, resolve all paths under `output/<video-stem>/`, sequence stages, honor `--skip-*` and `--force`.
- Location: `run_pipeline.py`
- Contains: `probe_codec`, `probe_duration`, `ensure_h264`, `run_step`, `step_detect`, `step_separate`, `step_transcribe`, `step_timeline`, `main`.
- Depends on: All stage scripts (via subprocess) + ffmpeg/ffprobe.
- Used by: Developer / CI invoking `python run_pipeline.py --video …`.

**Detection layer:**
- Purpose: Produce `shots.json` — a list of `{id, start_sec, end_sec, duration}` covering `[0, duration]` with no gaps.
- Location: `detectors/`
- Contains: Three detector revisions (V1/V2/V3b). V3b is the canonical one wired into the pipeline.
- Depends on: `scenedetect`, `cv2`, `numpy`, `PIL`, ffmpeg/ffprobe.
- Used by: `run_pipeline.py:step_detect`.

**Audio layer:**
- Purpose: Produce `audio_analysis.json` (per-shot stem energies + `dominant_type`) and `transcript.json` (Whisper segments).
- Location: `audio/`
- Depends on: `demucs` (via `python -m demucs` subprocess), `faster-whisper` / `openai-whisper`, `numpy`, ffmpeg.
- Used by: `run_pipeline.py:step_separate` and `step_transcribe`.

**Rendering layer:**
- Purpose: Read shots/frames/audio/transcript JSON and emit a single `.html` file.
- Location: `html/`
- Contains: `gen_timeline_html.py` (canonical, 1083 lines), plus two alternate viewers (`gen_shots_preview.py`, `gen_audio_html.py`).
- Depends on: `numpy`, `wave` (Python stdlib) for stem bucketing, ffmpeg for first/last frame extraction.
- Used by: `run_pipeline.py:step_timeline`.

**External binary layer:**
- ffmpeg / ffprobe — codec probing, AV1 transcode, frame extraction, 16 kHz wav extraction, 5 fps sampling.
- Demucs v4 (`htdemucs`) — invoked as `python -m demucs --name htdemucs -o <dir> <input>`.
- Whisper — either `faster_whisper.WhisperModel` (CTranslate2 backend) or `openai-whisper` library.

## Data Flow

### Primary Request Path (full pipeline)

1. `python run_pipeline.py --video X.mp4` (`run_pipeline.py:169 main()`)
2. Resolve `work_dir = output/<X>/`, create dir, optionally clear cache if `--force` (`run_pipeline.py:206-222`).
3. `ensure_h264(video, work_dir)` — if `ffprobe` reports `av1`, run `ffmpeg -c:v libx264 -preset fast -crf 20 -an h264.mp4` (`run_pipeline.py:59-74`).
4. `step_detect` → `detectors/detect_v3b.py --video … --frames-dir … --sample-fps 5 --output shots.json` (`run_pipeline.py:84-98`).
5. Inside V3b (`detectors/detect_v3b.py:detect_shots`):
   - `sample_frames` → ffmpeg dumps `f000001.jpg…` into `frames_5fps/` at `sample_fps`.
   - `run_pass1` → PySceneDetect `AdaptiveDetector(4.0, min_scene_len=30)` → coarse cuts.
   - `run_pass2_histcorr` → 8×8×8 RGB histogram cosine corr over sampled frames, refine each raw cut by ±0.3 s frame-level scan.
   - `detect_rapid_zones` + `merge_cuts` → dedup PSD+HistCorr, apply per-zone `min_scene_len`.
   - `run_pass3_long_shots` → for each segment >3 s, frame-level 16×16×16 scan (corr_thresh=0.88).
   - `run_pass4_dissolves` → sliding window (window=15) corr valley + RGB monotonicity → dissolve cuts.
   - Assemble `[{id, start_sec, end_sec, duration}, …]` and write `shots.json`.
6. `step_separate` → `audio/separate_stems.py --input … --shots shots.json --output-dir stems/ --output audio_analysis.json --model htdemucs` (`run_pipeline.py:101-117`).
   - Demucs writes `stems/htdemucs/<X>/{vocals,drums,bass,other}.wav`.
   - `analyze_shots` loads each stem wav, computes per-shot RMS + spectral centroid, classifies `dominant_type ∈ {dialogue, bgm, sfx, mixed}`, writes `audio_analysis.json`.
7. `step_transcribe` → `audio/transcribe.py --input … --output transcript.json --model large-v3 --language zh --backend auto` (`run_pipeline.py:120-136`).
   - ffmpeg extracts 16 kHz mono wav to a temp file; Whisper runs; temp wav is deleted in `finally`.
8. `step_timeline` → `html/gen_timeline_html.py --shots … --audio-json … --frames … --transcript … --stems-dir … --video … --output timeline.html` (`run_pipeline.py:139-166`).
   - `extract_frames_if_needed` pulls first/last frame per shot via ffmpeg, caches base64 data URIs in `frames.json`.
   - `build_shots_js` merges shot + frame + audio + transcript-segment-per-shot.
   - `build_js_stems` buckets vocals/drums/other into ~350 ms RMS integers (0–100) for canvas drawing.
   - `build_html` inlines everything into the final `.html`.
9. Final output paths printed: `timeline.html` + work dir, with a hint if the `<video src>` basename is missing from work_dir.

### Alternate Output Path (prompts)

The repo also produces `prompts.json` / `prompts.html` / `prompt_parts/part_NNN-MMM.json` under work_dir (observed in `output/《小江湖》第03话…/`). The generator script `html/gen_prompts_html.py` is **not present** in the working tree (referenced in git status as untracked, but missing on disk) — `run_pipeline.py` does not invoke it. Each prompt entry schema: `{shot_id, start_sec, end_sec, duration, subject, action, camera, scene, lighting, style, prompt_text}`. Restoring/regenerating this script is required to reproduce prompt output.

**State Management:**
- No runtime in-memory state shared across stages. All state lives in the filesystem cache under `work_dir`.
- `--skip-*` flags make each stage optional; if skipped and the cached JSON is missing, the dependent downstream stage runs without that data (e.g. timeline renders without dialogue if `transcript.json` is absent).
- Frontend (timeline.html) keeps all mutable state in JS globals: `SHOTS`, `STEMS`, `TRANSCRIPT_SEGMENTS`, `SHOT_LAYOUT`, `MODE`, `currentShot`, `playbackMode`, `activeStemKey`, `stopAtTime`.

## Key Abstractions

**Shots JSON:**
- Purpose: Authoritative shot segmentation shared by all downstream stages.
- Schema: `[{"id": int, "start_sec": float, "end_sec": float, "duration": float}, …]`, contiguous from 0 to video duration.
- Examples: `output/<video>/shots.json`, `examples/ep01_shots.json`, `examples/xiaojianghu_ep01_shots_v2.json`.
- Pattern: Plain JSON array, written by `detectors/detect_v3b.py:main` and consumed by `audio/separate_stems.py:analyze_shots` + `html/gen_timeline_html.py:build_shots_js`.

**Audio analysis JSON:**
- Purpose: Per-shot audio profile for both timeline rendering and downstream dataset use.
- Schema: `{episode, duration, stems:[...], shots:[{shot_id, start_sec, end_sec, duration, energies, ratios, spectral_centroid, dominant_type}], type_distribution}`.
- Producer: `audio/separate_stems.py:analyze_shots`.

**Transcript JSON:**
- Purpose: Time-stamped dialogue segments for the live caption bar and per-shot dialogue text.
- Schema: `{backend, model, language, duration, segments:[{start, end, text}], text, source}`.
- Producer: `audio/transcribe.py:main`.

**Frames JSON cache:**
- Purpose: Avoid re-extracting first/last thumbnails on every timeline regeneration.
- Schema: `[{id, first_frame:<data-uri>, last_frame:<data-uri>}, …]`.
- Producer: `html/gen_timeline_html.py:extract_frames_if_needed`.

**HTML timeline (frontend):**
- Purpose: Interactive dual-panel viewer — left panel shot rows (with thumbnails + dialogue), right panel vertical timeline with three stem waveforms.
- Producer: `html/gen_timeline_html.py:build_html`.
- Pattern: All data is inlined as JS constants at the top of `<script>`; the rest of the script builds DOM imperatively (`document.createElement`, `appendChild`). Stem playback uses raw `<audio>` elements (not Web Audio API) for mobile/Telegram compatibility.

## Entry Points

**`run_pipeline.py` (primary):**
- Location: `run_pipeline.py`
- Triggers: `python run_pipeline.py --video <path> [options]`
- Responsibilities: End-to-end run with caching + skip flags.

**Per-stage CLI (secondary):**
- `detectors/detect_v3b.py --video … --output shots.json` — V3b detection only.
- `detectors/psd_shot_preview_v1.py --video …` — V1 detection + simple HTML.
- `detectors/psd_shot_preview_v2.py --video …` — V2 detection + simple HTML.
- `audio/separate_stems.py --input … --shots … --output …` — Demucs + analysis only (`--skip-separate` reuses existing stems).
- `audio/transcribe.py --input … --output …` — Whisper only.
- `html/gen_timeline_html.py --shots … --output …` — Timeline HTML only.
- `html/gen_shots_preview.py --video … --shots …` — Shots grid HTML only.
- `html/gen_audio_html.py --video … --audio-json … --stems-dir …` — Audio analysis HTML only.
- `scripts/serve.py [dir] [port]` — Range-aware static server (default port 8765) for serving `timeline.html` + sibling video/stem assets.

## Architectural Constraints

- **Python version:** Python 3.10+ required (`run_pipeline.py` docstring).
- **External binaries required:** `ffmpeg` (with `libdav1d` for AV1 input) and `ffprobe` must be on PATH. Pipeline will hard-fail (`subprocess.run(..., check=True)`) without them.
- **GPU optional but expected:** Demucs and Whisper default to `cuda`; `--device cpu` is the escape hatch. `run_pipeline.py:--device` propagates to both.
- **Threading:** Single-threaded orchestrator. Each stage blocks until its subprocess exits. The timeline HTML server (`scripts/serve.py`) uses `ThreadingMixIn` only for concurrent HTTP requests.
- **Global state:** None at the Python level — every stage is a fresh process. The frontend has module-level JS globals (listed above) but no shared backend state.
- **AV1 input:** PySceneDetect is unreliable on AV1; the pipeline auto-transcodes to H264 (`-an`, audio dropped) and the H264 file is what detection runs against. Downstream stages (Demucs, Whisper, frame extraction) use the **original** video path for audio fidelity.
- **Canvas height cap:** Browsers cap `<canvas>` height near 65535 px; `gen_timeline_html.py` chunks each stem track into ≤60000 px segments (`CANVAS_MAX_H = 60000`).
- **No package structure:** No `__init__.py`, no `setup.py`/`pyproject.toml`. Stages are invoked by absolute file path (`HERE / "detectors" / "detect_v3b.py"`), not imported.
- **Cyclic imports:** Not possible — stages never import each other.

## Anti-Patterns

### God-script with inlined HTML/CSS/JS template

**What happens:** `html/gen_timeline_html.py` is 1083 lines. `build_html` returns a single f-string containing the entire HTML document with embedded `<style>` and a multi-hundred-line `<script>` block. Python `{{` / `}}` escaping is required throughout the JS.
**Why it's wrong:** Any frontend tweak requires editing a Python f-string; JS syntax errors surface only at HTML render time; the f-string braces make the JS hard to read and easy to break. CSS is also duplicated between `gen_timeline_html.py`, `gen_shots_preview.py:build_default_css`, and `gen_audio_html.py`.
**Do this instead:** Move the HTML/CSS/JS into a sibling template file (`html/templates/timeline.html.template`) read at runtime, or split `build_html` into per-section builders (`_head`, `_style`, `_header`, `_left_panel`, `_right_panel`, `_script`) that each return plain strings concatenated at the end.

### Duplicated `probe_duration` / `ensure_h264` / `extract_frame`

**What happens:** `probe_duration` is defined independently in `run_pipeline.py:49`, `detectors/detect_v3b.py:31`, `audio/transcribe.py:46`, and `detectors/psd_shot_preview_v1.py:30` (as `get_video_duration`). `ensure_h264` is duplicated in `run_pipeline.py:59` and `detectors/detect_v3b.py:59`. First/last frame extraction logic is duplicated in `gen_timeline_html.py:947 extract_frames_if_needed`, `gen_shots_preview.py:42 extract_first_last_frames`, `gen_audio_html.py:22 extract_frame`, and both `psd_shot_preview_v*.py` files.
**Why it's wrong:** Bug fixes (e.g. handling `N/A` duration, or new codec probing) must be applied in N places; the four copies already diverge subtly (different default fallbacks, different `ffprobe` selectors).
**Do this instead:** Extract a `common/ffmpeg_utils.py` (or `common/frames.py`) module with `probe_duration`, `probe_codec`, `ensure_h264`, `extract_frame_b64`, and import it. Since stages are invoked as subprocesses, this module must be on `PYTHONPATH` or staged into each script's dir; alternatively, inline the import via `sys.path.insert(0, str(HERE / "common"))`.

### Stage scripts invoked by path, not by package

**What happens:** `run_pipeline.py:93` invokes `[sys.executable, str(HERE / "detectors" / "detect_v3b.py"), …]`. Stage scripts cannot import shared helpers from a sibling `common/` directory without `sys.path` hacks.
**Why it's wrong:** No way to share utilities (see duplication anti-pattern above); IDE jump-to-definition across stages does not work; refactoring a stage's CLI signature requires hand-editing the corresponding `step_*` in `run_pipeline.py`.
**Do this instead:** Either convert to an installable package (`pyproject.toml` with console_scripts entry points) so stages are invoked as `kst-detect`, `kst-separate`, etc., or have `run_pipeline.py` `import` the stage module and call its `main(argv)` directly (passing args as a list) instead of spawning a subprocess.

## Error Handling

**Strategy:** Fail fast via `subprocess.run(..., check=True)`. Any non-zero exit from ffmpeg/demucs/whisper/stage scripts raises `CalledProcessError`, which propagates up through `run_step` and aborts the pipeline.

**Patterns:**
- ffmpeg frame extraction is wrapped in `try/except` with `timeout=10` and falls back to `""` (empty data URI) if the temp file is missing or undersized (`gen_timeline_html.py:980-987`, `gen_audio_html.py:24-37`).
- Whisper backend fallback: `transcribe.py:transcribe` tries `faster-whisper` first, on `ImportError` or other exceptions falls back to `openai-whisper` unless `--backend faster-whisper` was explicit (`audio/transcribe.py:109-123`).
- Whisper's temp wav is deleted in a `finally` block (`audio/transcribe.py:150-155`).
- Demucs stem dir lookup has a fallback: if `output_dir/model/<basename>` is missing, tries `output_dir/model` directly (`audio/separate_stems.py:67-73`).
- Missing optional inputs (no `audio-json`, no `transcript`) do not crash the timeline generator — it degrades to empty dialogue / zero-array waveforms (`gen_timeline_html.py:1051-1059`).

## Cross-Cutting Concerns

**Logging:** Plain `print()` statements throughout, prefixed with stage-specific tags (`[1/5]`, `[pass1]`, `[demucs]`, `[analyze]`, `[gen-timeline-html]`, `[whisper]`, `[serve]`). No logger, no log levels, no structured output. Progress reported as `f"  {i+1}/{len(shots)}"` every 10–20 items.

**Validation:** None. JSON inputs are trusted. `json.load(f)` is called without try/except. Shot start/end times are clamped to `[0, duration]` only inside `compute_rms_energy` (`audio/separate_stems.py:91-98`); no schema validation anywhere.

**Authentication:** Not applicable — purely local CLI tool.

**Configuration:** All config via argparse flags on each script. No config file, no env vars (except whatever Demucs/Whisper read internally, e.g. `CUDA_VISIBLE_DEVICES`). Pipeline defaults: `--sample-fps 5.0`, `--demucs-model htdemucs`, `--whisper-model large-v3`, `--whisper-language zh`, `--whisper-backend auto`, `--output-dir ./output`.

---

*Architecture analysis: 2026-07-20*
