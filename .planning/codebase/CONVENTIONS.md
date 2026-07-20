# Coding Conventions

**Analysis Date:** 2026-07-20

## Overview

This is a Python 3.10+ CLI/script codebase (video analysis tool). There is no
linter, formatter, type-checker, or build tool configured — conventions are
implicit and observed from the source. Two language contexts exist:

- **Python** — all logic in `*.py` files (the focus of this document).
- **Embedded JavaScript + CSS + HTML** — large string literals inside
  `html/gen_*.py` (e.g. `html/gen_timeline_html.py` ~1083 lines, most of it
  is an HTML f-string template). JS conventions noted at the end.

## Naming Patterns

**Files:**
- `snake_case.py` — universally applied.
- Verb-noun prefix by module role:
  - Entry/orchestrator: `run_pipeline.py`
  - Detectors: `detect_v3b.py`, `psd_shot_preview_v1.py`, `psd_shot_preview_v2.py` (versioned suffix `_v1` / `_v2` / `_v3b`).
  - HTML generators: `html/gen_*.py` (`gen_timeline_html.py`, `gen_audio_html.py`, `gen_shots_preview.py`).
  - Audio processors: `audio/separate_stems.py`, `audio/transcribe.py`.
  - Utilities: `scripts/serve.py`.

**Functions:**
- `snake_case` — universally (`compute_rms_energy`, `probe_duration`, `ensure_h264`, `extract_frame_b64`).
- Pure helpers tend to be verb-noun (`load_audio_stem`, `classify_shot`); pass-style pipeline steps prefixed `run_passN_...` (`run_pass1`, `run_pass2_histcorr`, `run_pass3_long_shots`, `run_pass4_dissolves`).
- Pipeline orchestrator step functions prefixed `step_...` (`step_detect`, `step_separate`, `step_transcribe`, `step_timeline`).

**Variables:**
- `snake_case` for locals/params (`video_path`, `sample_fps`, `stem_dir`).
- Module-level constants in `UPPER_CASE`: `HERE` (`run_pipeline.py:38`); JS-side `CANVAS_MAX_H`, `PX_PER_SEC_LINEAR`, `TRACK_W`, `MIN_SHOT_PX` (`html/gen_timeline_html.py:254-258`).

**Classes:**
- `PascalCase` — only two exist: `RangeRequestHandler`, `ThreadingHTTPServer` in `scripts/serve.py:19,99`. Rest of the codebase is function-based (no OOP).

**Types:**
- No `TypedDict` / `dataclass` / `NamedTuple` use. Data is passed as plain `dict` and `list[dict]`.

## Code Style

**Formatting:**
- No formatter configured (no `black`, `autopep8`, `yapf`, `ruff` config).
- Indentation: 4 spaces (consistent across all files).
- Line length: not enforced; lines up to ~110 chars appear (`detectors/detect_v3b.py:223-224`, `html/gen_timeline_html.py:922`).
- Trailing commas in multi-line collection literals: used inconsistently.
- Single quotes for short string literals (`'htdemucs'`, `'vocals'`) and double quotes for strings containing apostrophes / Chinese punctuation. Both styles appear in the same files.

**Linting:**
- Not configured. No `.flake8`, `.pylintrc`, `mypy.ini`, `ruff.toml`, `.pre-commit-config.yaml`.
- No `pyproject.toml`, `setup.cfg`, `requirements.txt`, `Pipfile`, `setup.py` — dependencies are documented only in `README.md` (`pip install scenedetect demucs faster-whisper pillow numpy opencv-python`).

**Type hints:**
- Applied inconsistently — treat them as optional aspiration, not enforced contract.
- Present in newer files: `audio/separate_stems.py`, `audio/transcribe.py`, `detectors/detect_v3b.py`, `run_pipeline.py` (full parameter + return annotations, e.g. `def separate_stems(input_video: str, output_dir: str, model: str = "htdemucs", ...) -> str:`).
- Absent in `html/gen_audio_html.py`, `html/gen_shots_preview.py`, `detectors/psd_shot_preview_v1.py`, `detectors/psd_shot_preview_v2.py`, `scripts/serve.py`.
- When adding code, match the surrounding file; prefer adding annotations for new public functions.

## Import Organization

**Order (observed in every file):**
1. Standard library, alphabetical (`argparse`, `base64`, `json`, `os`, `subprocess`, `sys`, `tempfile`, `from pathlib import Path`).
2. Blank line.
3. Third-party (`import numpy as np`, `from PIL import Image`, `from scenedetect import detect, AdaptiveDetector`).

Example (`detectors/detect_v3b.py:18-28`):
```python
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scenedetect import detect, AdaptiveDetector
```

**Deferred imports inside functions** are an accepted pattern for heavyweight or optional deps:
- `import cv2` inside `run_pass2_histcorr`, `run_pass3_long_shots`, `run_pass4_dissolves` (`detectors/detect_v3b.py:100,198,232`) — avoids top-level cv2 cost.
- `import wave` inside `load_audio_stem` / `load_audio_mono` (`audio/separate_stems.py:79`, `html/gen_audio_html.py:42`).
- `from faster_whisper import WhisperModel` / `import whisper` inside their backend functions (`audio/transcribe.py:69,94`) — enables the auto-fallback pattern.

**Path Aliases:**
- None. No `sys.path` manipulation; cross-module scripts are invoked as subprocesses (`sys.executable` + script path) rather than imported.

## Error Handling

**Strategy:** Pragmatic fail-loud at the orchestrator layer, defensive fallback at the I/O / optional-dependency layer.

**Patterns:**
- **Subprocess failures:** `subprocess.run([...], check=True)` — propagates `CalledProcessError`. The pipeline wrapper `run_step` (`run_pipeline.py:77-81`) adds a labeled header banner + echo of the command before delegating to `check=True`.
- **Missing required input file:** `sys.exit("...")` with a short message. See `run_pipeline.py:203` (`sys.exit(f"input video not found: {video}")`), `run_pipeline.py:231`.
- **Domain errors:** explicit `raise` with Chinese message:
  - `raise RuntimeError(f"无法读取视频时长: {video_path}")` (`detectors/detect_v3b.py:324`)
  - `raise FileNotFoundError(f"No stems found under {stem_dir}")` (`audio/separate_stems.py:144`)
- **Optional-dependency fallback:** `audio/transcribe.py:109-123` — try faster-whisper, catch `ImportError` (re-raise if explicitly requested) else fall back to openai-whisper, catch generic `Exception` and retry with fallback.
- **Probe / parsing fallbacks:** `probe_duration` swallows `(ValueError, AttributeError)` and returns `0.0` (`run_pipeline.py:49-56`, `detectors/detect_v3b.py:31-38`, `audio/transcribe.py:46-63`). This is intentional: a missing duration is treated as "unknown" rather than fatal.
- **`try/finally` for temp file cleanup:** `audio/transcribe.py:150-155` removes the intermediate wav even if transcription raises.
- **No custom exception classes.** No exception hierarchy — only stdlib types.

**Anti-pattern to avoid:** silent bare `except Exception` returning a default (`audio/transcribe.py:54,62`). When adding code, prefer narrow exception types (`FileNotFoundError`, `subprocess.CalledProcessError`) over broad catches.

## Logging

**Framework:** None. Uses `print()` directly to stdout.

**Patterns:**
- **Bracketed stage prefix** for every progress line: `print(f"[stage] ...")`.
  - Pipeline stages: `[1/5]`, `[2/5]`, `[3/5]`, `[4/5]`, `[5/5]`, `[force]`, `[done]` (`run_pipeline.py`).
  - Sub-system tags: `[ffmpeg]`, `[demucs]`, `[analyze]`, `[whisper]`, `[faster-whisper]`, `[openai-whisper]`, `[pass1]`...`[pass4]`, `[transcode]`, `[sample]`, `[merge]`, `[result]`, `[gen-timeline-html]`, `[gen-audio-html]`, `[warn]`, `[serve]`.
- **Banner blocks** between pipeline steps:
  ```python
  print(f"\n{'='*60}\n{label}\n{'='*60}")
  ```
  (`run_pipeline.py:79`).
- **Cached-result skips** print a `cached`/`skipping` line on every cache hit (`run_pipeline.py:67,90,108,127,147`).
- **Progress counters** for long loops: `if (i + 1) % 10 == 0: print(f"  {i+1}/{len(shots)}")` (`audio/separate_stems.py:171`, `html/gen_audio_html.py:359`, `html/gen_timeline_html.py:995`).
- No log levels, no `logging.getLogger`, no structured output.

When adding code: use `print(f"[<module-tag>] ...")` to match the existing convention. Use `[warn]` prefix for recoverable issues (`html/gen_timeline_html.py:80,1059`).

## Comments

**When to Comment:**
- Module docstring is mandatory on every executable file — describes purpose, algorithm steps, output JSON schema, and CLI usage. See `detectors/detect_v3b.py:1-17`, `audio/separate_stems.py:1-29`, `run_pipeline.py:1-30`.
- Function docstrings on most public functions: triple-quoted, Chinese narrative (`audio/separate_stems.py:42-53`, `detectors/detect_v3b.py:92-99`).
- Inline rationale comments for non-obvious heuristics — especially the dissolve-detection thresholds (`detectors/detect_v3b.py:270-312`) and stem playback mute-sync rationale (`html/gen_timeline_html.py:580-581`):
  ```python
  # 视频静音 + 同步播放：只有目标 stem 出声，画面跟着 stem 推进。
  # 不做 drift 修正 — 修正会在视频偶发卡顿时变成 seek 循环（"反复跳"）。
  ```
- Section dividers in CSS / JS embedded strings: `/* ===== Top: sticky header + player ===== */` (`html/gen_timeline_html.py:135`), `// === Stem playback via <audio> elements ===` (`html/gen_timeline_html.py:510`).

**Language:**
- All comments and docstrings are in **Chinese (Simplified)**. Exception: a few short inline comments in English (`scripts/serve.py:23`).
- Match the surrounding language when adding comments.

**JSDoc/TSDoc:** Not used. Embedded JS uses `//` line comments only.

## Function Design

**Size:** Wide variance. Pure helpers are small (5-15 lines: `compute_rms_energy`, `classify_shot`, `probe_duration`). Algorithm passes and HTML builders are large monolithic functions:
- `run_pass4_dissolves` (`detectors/detect_v3b.py:228-314`) ~85 lines.
- `build_html` in `html/gen_audio_html.py:75-314` ~240 lines (mostly template literal).
- `build_html` in `html/gen_timeline_html.py:99-944` ~845 lines (the single largest function; mostly HTML/CSS/JS template).

**Parameters:** Many parameters per function is normal for the pipeline steps — `step_timeline(video, work_dir, shots_json, audio_json, transcript, frames_json, stems_dir, out_html, video_src, stem_basename)` (`run_pipeline.py:139`). When adding new step-like functions, prefer keyword-only args via `*` if the param count grows further.

**Return Values:**
- Pipeline step functions return the output path on success or `None` on skip (`run_pipeline.py:84-166`).
- Detector returns `list[dict]` of shots (`detectors/detect_v3b.py:317-363`).
- HTML generators return the HTML string; `main()` writes it.
- Audio helpers return plain Python primitives / `dict` / `np.ndarray` (not custom types).

**Default arguments:** Used liberally for tunable thresholds (`threshold: float = 4.0`, `min_scene_len: int = 30`, `sample_fps: float = 5.0`, `bucket_ms=350`).

## Module Design

**Exports:**
- No `__all__` declarations. All public names are importable.
- Each executable module exposes a `main()` that does argparse + work, plus the helper functions above it.

**`main()` pattern (mandatory for executable scripts):**
```python
def main():
    ap = argparse.ArgumentParser(description="...")
    ap.add_argument("--video", required=True, help="...")
    # ...
    args = ap.parse_args()
    # ... work ...

if __name__ == "__main__":
    main()
```

Every script under `audio/`, `detectors/`, `html/`, `scripts/`, and the top-level `run_pipeline.py` follows this exact shape.

**Module-level constants** allowed at top of file after imports (`HERE = Path(__file__).parent.resolve()` in `run_pipeline.py:38`).

**Barrel files:** None. Each script is invoked directly; there are no `__init__.py` files and no shared utility module.

## CLI Argument Conventions

**Argparse style** (universal across all scripts):
- `--flag-name` with `kebab-case` for multi-word flags: `--skip-detect`, `--skip-separate`, `--skip-transcribe`, `--sample-fps`, `--demucs-model`, `--whisper-model`, `--whisper-language`, `--whisper-backend`, `--adaptive-threshold`, `--min-scene-len`, `--output-dir`, `--video-src`, `--stem-basename`, `--two-stems`, `--wav-out`, `--v2-html`, `--ep-name`.
- Every `add_argument` includes a Chinese `help=` string.
- Boolean flags use `action="store_true"` paired with a `--skip-*` / `--no-*` / `--force` name (`run_pipeline.py:175-198`).
- For mutually-destructive booleans use `dest` + `action="store_false"` pattern, e.g. `--extract-frames` / `--no-extract-frames` in `html/gen_audio_html.py:329-333`.
- `choices=[...]` for enum-like flags: `--whisper-backend` (`run_pipeline.py:189-190`).
- `type=float` / `type=int` for numeric flags; otherwise string.

**Default-output-path idiom** (very common): when `--output` is omitted, derive from input basename:
```python
out = args.output or os.path.join(
    os.path.dirname(args.video) or ".",
    f"{Path(args.video).stem}_v3b_shots.json")
```
(`detectors/detect_v3b.py:381-383`, `audio/transcribe.py:141-143`, `html/gen_shots_preview.py:123-125`).

## Caching & Idempotency Pattern

A distinctive pattern across the pipeline: **every step checks for an existing output file before running**, prints a `[N/5] cached X` line, and short-circuits. See `run_pipeline.py:86-91,104-109,123-128,143-148`.

```python
if os.path.exists(output_path):
    print(f"[2/5] cached shots: {output_path}")
    return output_path
```

`--force` (`run_pipeline.py:218-222`) clears the cache under the work dir before re-running.

For new pipeline stages: implement the same `if os.path.exists(out): print(...); return out` short-circuit at the top, and add a corresponding `--skip-<stage>` flag wired through `run_pipeline.py`.

## Subprocess Invocation Pattern

External binaries (`ffmpeg`, `ffprobe`, `demucs`, sibling Python scripts) are invoked via `subprocess.run` with a **list-form command** (never shell=True):

- **ffmpeg frame extraction:** `subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video, "-frames:v", "1", "-q:v", "2", "-vf", "scale=480:-1", tmp, "-loglevel", "error"], capture_output=True, timeout=10)`. Pattern repeated in `html/gen_audio_html.py:27-29`, `html/gen_shots_preview.py:28-31`, `html/gen_timeline_html.py:975-979`, `detectors/psd_shot_preview_v1.py:65-69`.
- **ffprobe duration / codec:** `subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", ...], capture_output=True, text=True)` (`run_pipeline.py:42-46,50-53`, `detectors/detect_v3b.py:32-35,43-47`).
- **Demucs:** `subprocess.run([sys.executable, "-m", "demucs", "--name", model, ...], check=True)` (`audio/separate_stems.py:55-65`).
- **Sibling Python scripts** (orchestrator invoking child stages): `subprocess.run([sys.executable, str(HERE / "detectors" / "detect_v3b.py"), "--video", video, ...], check=True)` (`run_pipeline.py:92-97,110-116,129-135,149-165`).

Use the same list-form + `check=True` (or `capture_output=True` + manual size check) style for new subprocess calls.

## JSON I/O Conventions

**Reading:** `with open(path) as f: data = json.load(f)` (no encoding arg needed — Python 3 default UTF-8).

**Writing:**
```python
with open(path, "w") as f:
    json.dump(obj, f, indent=2, ensure_ascii=False)
```
- `indent=2` universally.
- `ensure_ascii=False` **always** for output containing Chinese (`audio/separate_stems.py:190`, `audio/transcribe.py:161`, `html/gen_audio_html.py:362`, `html/gen_timeline_html.py:110-112`).
- Exception: `detectors/detect_v3b.py:391` uses `json.dump(shots, f, indent=2)` without `ensure_ascii=False` — but shots.json has no Chinese content, so it doesn't matter. Use `ensure_ascii=False` for any new file that may contain Chinese.

**For embedding into HTML `<script>` blocks:**
- `json.dumps(obj, ensure_ascii=False)` interpolated directly into a JS template literal (`html/gen_timeline_html.py:110-112,252`).

## Embedded JavaScript / CSS Conventions

The HTML generator scripts contain large JS/CSS string literals. Conventions within those strings:

- **JS variables:** `camelCase` (`currentShot`, `stopAtTime`, `playbackMode`, `activeStemKey`, `stemStopTimer`); constants `UPPER_SNAKE_CASE` (`SHOTS`, `STEMS`, `DURATION`, `TIMELINE_H`, `TRACK_W`, `CANVAS_MAX_H`, `PX_PER_SEC_LINEAR`, `MIN_SHOT_PX`).
- **JS functions:** `camelCase` (`playShot`, `playStem`, `stopStem`, `toggleMode`, `syncAdaptiveLayout`, `getTimeY`, `getYTime`, `scrollTimelineTo`).
- **CSS classes:** `kebab-case` (`.shot-card`, `.live-caption`, `.left-panel`, `.type-badge`, `.type-dialogue`).
- **CSS color palette:** GitHub-dark theme tokens reused across all HTML generators — `#0d1117` body bg, `#161b22` panel bg, `#30363d` border, `#58a6ff` accent blue, `#3fb950` green, `#d29922` yellow, `#f85149` red, `#8b949e` muted text. Reuse these for any new HTML output.
- **String templating:** All embedded JS uses f-string-safe doubled braces `{{ }}` to escape literal `{`/`}` because the surrounding HTML is a Python f-string. See `html/gen_timeline_html.py:131-941`.
- **DOM lookup:** mixes `document.getElementById` (cached top-level `const video = document.getElementById('player')`) and `document.querySelectorAll(...).forEach(...)`.
- **Event wiring:** inline `onclick=` attributes in template strings for static elements; `addEventListener` for dynamically created elements.

## File Permission Conventions

Note: in this repo, several source files were committed with `chmod 600` (owner-only):
`detectors/detect_v3b.py`, `detectors/psd_shot_preview_v1.py`, `detectors/psd_shot_preview_v2.py`, `html/gen_shots_preview.py`, `html/gen_timeline_html.py`. This is incidental (likely a backup-restore artifact), not an intentional convention. New files should use the default `644`.

---

*Convention analysis: 2026-07-20*
