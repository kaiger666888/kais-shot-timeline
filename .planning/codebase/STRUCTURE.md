# Codebase Structure

**Analysis Date:** 2026-07-20

## Directory Layout

```
kais-shot-timeline/
├── run_pipeline.py             # End-to-end orchestrator (sole entry point)
│
├── detectors/                  # Shot-boundary detection stages (V1 / V2 / V3b)
│   ├── detect_v3b.py           #   Canonical 4-pass fusion detector (wired into pipeline)
│   ├── psd_shot_preview_v1.py  #   Legacy V1: single AdaptiveDetector + HTML
│   └── psd_shot_preview_v2.py  #   Legacy V2: dual-detector + fragment merge + HTML
│
├── audio/                      # Audio analysis (Demucs stem separation + Whisper ASR)
│   ├── separate_stems.py       #   Demucs 4-stem + per-shot RMS/centroid/classification
│   └── transcribe.py           #   Whisper (faster-whisper preferred, openai-whisper fallback)
│
├── html/                       # HTML generators (each emits a self-contained .html)
│   ├── gen_timeline_html.py    #   Canonical dual-panel timeline (1083 lines)
│   ├── gen_shots_preview.py    #   Shot-card grid (alt view)
│   ├── gen_audio_html.py       #   Per-shot 4-stem energy bars (alt view)
│   └── (gen_prompts_html.py)   #   Referenced in git status as untracked, MISSING from disk
│
├── scripts/                    # Dev tooling
│   └── serve.py                #   Range-aware static HTTP server for timeline.html
│
├── examples/                   # Committed sample data (test fixtures)
│   ├── ep01_shots.json
│   └── xiaojianghu_ep01_shots_v2.json
│
├── output/                     # Generated artifacts (gitignored, except index.html)
│   ├── index.html              #   Hand-curated episode index page
│   └── <video-stem>/           #   One subdir per processed video (work_dir)
│       ├── h264.mp4            #     AV1→H264 transcode cache (only if input was AV1)
│       ├── shots.json          #     V3b shot list
│       ├── frames.json         #     First/last frame base64 cache
│       ├── frames_5fps/        #     V3b Pass2 sampled frames (f000001.jpg…)
│       ├── stems/htdemucs/<video-stem>/
│       │   ├── vocals.wav
│       │   ├── drums.wav
│       │   ├── bass.wav
│       │   └── other.wav
│       ├── audio_analysis.json #     Per-shot stem energies + dominant_type
│       ├── transcript.json     #     Whisper segments
│       ├── shot_frames/        #     First/last JPG per shot (alt to frames.json data URIs)
│       ├── prompt_parts/       #     Chunked prompts (part_NNN-MMM.json)
│       ├── prompts.json        #     Full prompts array (subject/action/camera/scene/...)
│       ├── prompts.html        #     Prompt viewer page
│       └── timeline.html       #     Final dual-panel interactive HTML
│
├── prompts/                    # Listed in git status as untracked, NOT present on disk
│
├── README.md                   # Bilingual (Chinese) project overview + CLI docs
└── .gitignore                  # Ignores output/, *.mp4, *.wav, *.html, __pycache__/
```

## Directory Purposes

**`/` (repo root):**
- Purpose: All top-level Python scripts live here; no `src/` layout, no package files.
- Contains: `run_pipeline.py` (orchestrator) + `README.md` + `.gitignore`.
- Key files: `run_pipeline.py` is the only file developers invoke directly.

**`detectors/`:**
- Purpose: Shot-boundary detection algorithms. Each revision is a standalone script with its own `detect_shots*()` + HTML preview generator (V1/V2) or pure JSON output (V3b).
- Contains: 3 Python files (~1145 LOC total).
- Key files: `detect_v3b.py` (canonical, 4-pass fusion), `psd_shot_preview_v1.py` (single-detector baseline), `psd_shot_preview_v2.py` (dual-detector with fragment merge).

**`audio/`:**
- Purpose: Audio-side analysis — Demucs stem separation + Whisper transcription. Both scripts are independently runnable and accept `--device cuda:0` etc.
- Contains: 2 Python files (~395 LOC total).
- Key files: `separate_stems.py` (Demucs + RMS/centroid analysis), `transcribe.py` (Whisper with backend fallback).

**`html/`:**
- Purpose: HTML rendering stages. The canonical `gen_timeline_html.py` produces the final pipeline output; the other two are alternate viewers used during development.
- Contains: 3 Python files (~1744 LOC total; `gen_timeline_html.py` alone is 1083 lines).
- Key files: `gen_timeline_html.py` (inlines all data + CSS + JS into a single `.html`).

**`scripts/`:**
- Purpose: Developer-facing utilities, not part of the pipeline.
- Contains: `serve.py` (Range-aware HTTP server).
- Key files: `serve.py` — required because `python3 -m http.server` on Ubuntu/Debian does not honor `Range` headers, breaking `<video>` seek.

**`examples/`:**
- Purpose: Committed sample `shots.json` files used as inputs for offline HTML testing without re-running detection.
- Contains: 2 JSON files (~15 KB total).

**`output/`:**
- Purpose: All generated artifacts. One subdir per processed video, named by `Path(video).stem`.
- Contains: JSON / HTML / wav / mp4 / jpg artifacts + `index.html` (a hand-curated landing page linking to each episode's `timeline.html`).
- Generated: Yes, fully generated by the pipeline.
- Committed: `output/` is in `.gitignore`; only `output/index.html` appears to be tracked. Large media files (`*.mp4`, `*.wav`, `*.html`) are explicitly gitignored at the repo root.

## Key File Locations

**Entry Points:**
- `run_pipeline.py`: Pipeline orchestrator — `python run_pipeline.py --video input.mp4`.
- `detectors/detect_v3b.py`: Standalone V3b detector — `python detectors/detect_v3b.py --video … --output shots.json`.
- `audio/separate_stems.py`: Standalone Demucs + analysis.
- `audio/transcribe.py`: Standalone Whisper.
- `html/gen_timeline_html.py`: Standalone timeline HTML generator.
- `scripts/serve.py`: Static server — `python3 scripts/serve.py output/<video-stem> 8765`.

**Configuration:**
- No config files. All configuration via argparse flags. Run `python <script> --help` for the canonical flag list.
- `.gitignore`: Ignores `output/`, `*.mp4`, `*.wav`, `*.html`, `__pycache__/`, `*.pyc`, `.DS_Store`.

**Core Logic:**
- `detectors/detect_v3b.py:detect_shots` (line 317): The 4-pass fusion entry point.
- `detectors/detect_v3b.py:run_pass1` / `run_pass2_histcorr` / `run_pass3_long_shots` / `run_pass4_dissolves`: Individual detection passes.
- `audio/separate_stems.py:analyze_shots` (line 132): Per-shot audio profiling.
- `audio/separate_stems.py:classify_shot` (line 118): `dominant_type` decision rules.
- `html/gen_timeline_html.py:build_html` (line 99): HTML f-string assembly.
- `html/gen_timeline_html.py:build_js_stems` (line 57): ~350 ms RMS bucketing for canvas.

**Caches / Intermediate State:**
- `output/<video-stem>/shots.json` — shot segmentation.
- `output/<video-stem>/frames.json` — base64 first/last frames per shot.
- `output/<video-stem>/audio_analysis.json` — per-shot audio profile.
- `output/<video-stem>/transcript.json` — Whisper segments.
- `output/<video-stem>/h264.mp4` — AV1→H264 transcode cache.

**Testing:**
- No test directory, no test files, no test framework configured. See TESTING.md (not applicable for arch focus).

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (`run_pipeline.py`, `separate_stems.py`, `gen_timeline_html.py`).
- Detector revisions are suffixed `_v1` / `_v2` / `_v3b` (`psd_shot_preview_v1.py`, `detect_v3b.py`). V3b uses lowercase `b` (no `_`).
- HTML generators all prefixed `gen_` (`gen_timeline_html.py`, `gen_shots_preview.py`, `gen_audio_html.py`, missing `gen_prompts_html.py`).
- Legacy PSD detectors prefixed `psd_` (`psd_shot_preview_v*.py`).

**Functions:**
- `snake_case` everywhere (`detect_shots`, `ensure_h264`, `run_pass1`, `step_separate`, `build_html`, `compute_rms_energy`).
- Pipeline step wrappers in `run_pipeline.py` are prefixed `step_` (`step_detect`, `step_separate`, `step_transcribe`, `step_timeline`).
- Detector internal passes prefixed `run_passN_` (`run_pass1`, `run_pass2_histcorr`, `run_pass3_long_shots`, `run_pass4_dissolves`).

**Variables / module constants:**
- `UPPER_SNAKE` for module-level constants (`HERE` in `run_pipeline.py`; in the generated HTML frontend: `SHOTS`, `STEMS`, `TRANSCRIPT_SEGMENTS`, `DURATION`, `TIMELINE_H`, `TRACK_W`, `CANVAS_MAX_H`, `PX_PER_SEC_LINEAR`, `MIN_SHOT_PX`).
- `camelCase` for JS functions and locals in the inlined frontend (`playStem`, `stopStem`, `selectShot`, `toggleMode`, `syncAdaptiveLayout`, `getYTime`, `getTimeY`).

**Directories:**
- Plural nouns for category dirs (`detectors/`, `audio/`, `html/`, `scripts/`, `examples/`, `prompts/`).
- `output/<video-stem>/` — work_dir is the input filename without extension (e.g. `《小江湖》第03话：白头发的少女（画面只是工具，情绪才是目的`).
- Inside work_dir, fixed filenames: `shots.json`, `frames.json`, `audio_analysis.json`, `transcript.json`, `timeline.html`, `h264.mp4`, `frames_5fps/`, `stems/htdemucs/<video-stem>/`.

**JSON schema field names:**
- `snake_case` for all JSON keys (`start_sec`, `end_sec`, `shot_id`, `dominant_type`, `spectral_centroid`, `type_distribution`).
- Transcript segments use bare `start` / `end` / `text` (Whisper's native shape) — divergence from the `*_sec` convention elsewhere.

**Output asset naming (referenced by timeline HTML):**
- Stem wavs: `<video-stem>_vocals.wav`, `<video-stem>_drums.wav`, `<video-stem>_other.wav` (note: `<basename>` is controlled by `--stem-basename`, defaults to video filename stem; bass is not referenced by the frontend).
- Sampled frames: `frames_5fps/f000001.jpg`, `f000002.jpg`, … (6-digit zero-padded).
- Shot frame pairs (alt cache): `shot_frames/shot_001_first.jpg`, `shot_001_last.jpg`.
- Prompt chunks: `prompt_parts/part_NNN-MMM.json` (e.g. `part_001-011.json`, `part_012-022.json`).

## Where to Add New Code

**New analysis stage (e.g. a new pass, a new classifier):**
1. Create `detectors/<new_detector>.py` (or `audio/<new_analysis>.py`) with `detect_<thing>(...)` + `main()` that accepts `--video`, `--output`, etc. Follow the same argparse + `if __name__ == "__main__"` pattern.
2. Add a `step_<name>` wrapper in `run_pipeline.py` (mirror `step_detect` at lines 84–98): build the `[sys.executable, str(HERE / "<dir>" / "<script>.py"), ...]` command, honor a new `--skip-<name>` flag, cache to `output/<video-stem>/<name>.json`.
3. Wire it into `run_pipeline.py:main()` between the appropriate existing stages; add a new `--skip-<name>` argparse argument near lines 175–180.
4. Add the output filename to the `--force` cache-clear list at `run_pipeline.py:219`.

**New HTML viewer (mirroring `gen_shots_preview.py` / `gen_audio_html.py`):**
1. Create `html/gen_<view>_html.py` with a `build_html(...)` that returns a single HTML string + a `main()` that reads JSON inputs and writes the HTML.
2. Either invoke standalone or wire into `run_pipeline.py` as a new `step_<view>`.

**New utility shared across stages:**
- Currently there is no shared module — every stage redefines its own `probe_duration` / `extract_frame` / etc. To add one, create `common/<util>.py` and have each stage insert its parent dir onto `sys.path` (e.g. `sys.path.insert(0, str(Path(__file__).parent.parent))`) before `import`. There is no precedent for this in the current codebase.

**New detector revision (V4, etc.):**
- Add `detectors/detect_v4.py` alongside `detect_v3b.py`. Do not modify V3b — keep it as the documented fallback. Bump the default in `run_pipeline.py:step_detect` only after V4 is validated.

**New example fixture:**
- Drop a JSON file under `examples/`. The format must match the `shots.json` schema (`[{id, start_sec, end_sec, duration}, …]`) to be consumable by `html/gen_shots_preview.py --shots examples/<file>.json`.

**New dev script (not part of pipeline):**
- Place under `scripts/`. Follow `serve.py`'s pattern: standalone `main()` with `if __name__ == "__main__":` guard, prints `[serve]`/`[<tag>]`-prefixed status.

**Test files:**
- No precedent. If introducing tests, do not co-locate under `detectors/` or `audio/` (those are runtime scripts invoked by subprocess); create a top-level `tests/` directory and import the stage modules directly for unit tests of pure functions (e.g. `merge_cuts`, `classify_shot`, `build_shots_js`).

## Special Directories

**`output/`:**
- Purpose: All pipeline artifacts (work_dir per video + hand-curated `index.html`).
- Generated: Yes (except `index.html`).
- Committed: No — listed in `.gitignore`. Repo-root `*.mp4`, `*.wav`, `*.html` patterns also block any stray artifacts elsewhere.

**`output/<video-stem>/frames_5fps/`:**
- Purpose: V3b Pass2 sampled JPEG frames at `--sample-fps` (default 5 fps). Written by `detectors/detect_v3b.py:sample_frames` via `ffmpeg -vf fps=5`.
- Generated: Yes.
- Committed: No (under `output/`).
- Lifetime: Reused across runs unless `frames_dir` is reassigned or `--force` clears `shots.json` (which triggers re-detection but does **not** clear `frames_5fps/` itself — only `shots.json`/`frames.json`/`audio_analysis.json`/`transcript.json`/`timeline.html` are in the `--force` clear list at `run_pipeline.py:219`).

**`output/<video-stem>/stems/htdemucs/<video-stem>/`:**
- Purpose: Demucs output — four stem wavs (`vocals.wav`, `drums.wav`, `bass.wav`, `other.wav`). The double `<video-stem>` nesting is Demucs's own layout (`-o output_dir` → `output_dir/<model>/<input-basename>/`).
- Generated: Yes (by `python -m demucs`).
- Committed: No.

**`examples/`:**
- Purpose: Committed reference fixtures for offline HTML testing.
- Generated: No (hand-curated).
- Committed: Yes.

**`scripts/`:**
- Purpose: Developer utilities (static server). Not invoked by the pipeline.
- Generated: No.
- Committed: Yes.

**`prompts/` and `html/gen_prompts_html.py`:**
- Purpose: Prompt extraction (subject / action / camera / scene / lighting / style / prompt_text per shot). Artifacts `prompts.json` / `prompts.html` / `prompt_parts/` exist under `output/<video-stem>/`, but the generator script is missing from disk and untracked in git (the directory `prompts/` is also absent despite being listed in `git status` as untracked).
- Generated: N/A — script is currently absent.
- Committed: No.

**`.planning/codebase/`:**
- Purpose: This document and sibling analysis files, consumed by `/gsd:plan-phase` and `/gsd:execute-phase`.
- Generated: Yes (by `/gsd:map-codebase`).
- Committed: As the user directs.

---

*Structure analysis: 2026-07-20*
