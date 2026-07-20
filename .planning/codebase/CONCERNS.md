# Codebase Concerns

**Analysis Date:** 2026-07-20

**Scope:** Full repo (`kais-shot-timeline`). Current branch `feat/video-reverse-dataset` —
note that `main` branch additionally contains `prompts/extract_frames.py`,
`prompts/merge_prompts.py`, and `html/gen_prompts_html.py` which are NOT present on this
branch. Treat the prompt-extraction feature as half-merged (see "Branch divergence" below).

## Tech Debt

### Duplicated ffmpeg/ffprobe probe code
- Issue: `probe_duration()` is reimplemented verbatim in three modules; `extract_frame()`
  is reimplemented in five modules with near-identical bodies. No shared utility module exists.
- Files: `run_pipeline.py:49`, `detectors/detect_v3b.py:31`, `audio/transcribe.py:46`
  (probe_duration); `html/gen_audio_html.py:22`, `html/gen_shots_preview.py:24`,
  `detectors/psd_shot_preview_v1.py:61`, `detectors/psd_shot_preview_v2.py:121`,
  `html/gen_timeline_html.py:972` (extract_frame).
- Impact: Bug fixes (e.g. timeout, error handling) must be applied in five places.
  Divergence already visible — some versions pass `-loglevel error`, some don't, some
  use `scale=480:-1`, some don't.
- Fix approach: Extract a `common/ffmpeg_utils.py` (or `utils/media.py`) module exposing
  `probe_duration`, `probe_codec`, `extract_frame_b64(video, ts, ...)`. All generators
  and detectors import from there.

### Duplicated WAV loader
- Issue: `load_audio_stem` / `load_audio_mono` (wave → mono float32 numpy) reimplemented
  three times with the same int16 / 32768.0 / stereo-mean logic.
- Files: `audio/separate_stems.py:77-88`, `html/gen_timeline_html.py:66-74`,
  `html/gen_audio_html.py:40-50`.
- Impact: Any change to dtype handling or sample-rate normalization must be applied in
  three places. Risk of subtle drift in RMS/energy calculations between modules.
- Fix approach: Move to shared `audio/io.py` and have HTML generators import it.

### Three near-duplicate detector scripts
- Issue: `detectors/psd_shot_preview_v1.py` (287 lines), `detectors/psd_shot_preview_v2.py`
  (462 lines), `detectors/detect_v3b.py` (396 lines) all reimplement shot-list-to-HTML,
  frame extraction, and JSON shape. README explicitly designates V3b as "推荐" (recommended).
  V1/V2 are legacy.
- Files: `detectors/psd_shot_preview_v1.py`, `detectors/psd_shot_preview_v2.py`,
  `detectors/detect_v3b.py`.
- Impact: Three HTML/CSS blocks to maintain, three subprocess invocation patterns, three
  sources of truth for the shot JSON schema. Hard to onboard new contributors.
- Fix approach: Either delete V1/V2 (mark in README as deprecated/archived examples) or
  extract their shared `generate_html` into `html/gen_shots_preview.py` (which already
  exists as the canonical parameterized version) and delete the legacy HTML builders.

### Branch divergence / half-merged prompt feature
- Issue: `main` (commit `4e60b3d`) contains `html/gen_prompts_html.py`,
  `prompts/extract_frames.py`, `prompts/merge_prompts.py`, an expanded `audio/transcribe.py`
  (~310 lines, with `torch` import and GPU adaptation), and a 39-line larger README. The
  current branch `feat/video-reverse-dataset` removed all of these and shrunk
  `audio/transcribe.py` to 166 lines. Neither branch is merged to the other.
- Files: deleted on this branch — `prompts/`, `html/gen_prompts_html.py`;
  modified — `audio/transcribe.py`, `run_pipeline.py`, `README.md`.
- Impact: Two parallel lines of development; anyone switching branches loses work or
  gets a different feature set. README on this branch no longer documents the prompts
  workflow that exists on main.
- Fix approach: Decide which direction is canonical (rebase or merge). If
  `feat/video-reverse-dataset` is the keeper, open a PR to delete the prompts feature
  from main; otherwise rebase this branch onto main and restore the prompts files.

### No dependency manifest
- Issue: No `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`, or `poetry.lock`.
  Dependencies are documented only as a `pip install` line in README.
- Files: missing (project root).
- Impact: No version pinning. `scenedetect`, `demucs`, `faster-whisper`, `openai-whisper`,
  `torch`, `opencv-python`, `numpy`, `pillow` all have breaking-change history; a fresh
  install can pull incompatible versions. Reproducibility is impossible.
- Fix approach: Add a `requirements.txt` pinning at least major versions of the heavy ML
  deps (`torch>=2.0,<3.0`, `faster-whisper==1.0.*`, `demucs==4.0.*`,
  `scenedetect>=0.6,<0.8`). Better: migrate to `pyproject.toml`.

### Hardcoded magic numbers in V3b detection
- Issue: Correlation thresholds (`0.90`, `0.88`, `0.78`, `0.93`), window sizes (`15`,
  `9`, `15`), RGB delta thresholds (`3.0`, `8.0`), monotonicity ratio (`0.7`), and
  pixel-per-second (`PX_PER_SEC_LINEAR=396`, `MIN_SHOT_PX=280`) are inline constants.
  Only `adaptive_threshold`, `min_scene_len`, `sample_fps` are CLI-exposed.
- Files: `detectors/detect_v3b.py:117-313` (Pass2/3/4), `html/gen_timeline_html.py:254-258`.
- Impact: Tuning detection quality requires editing source code. Cannot A/B test
  parameter sweeps from the CLI.
- Fix approach: Add CLI args (`--corr-thresh-pass2`, `--corr-thresh-pass3`,
  `--dissolve-thresh`, `--dissolve-window`) with current values as defaults.

### Inline JS/CSS embedded in Python f-strings
- Issue: `html/gen_timeline_html.py` lines 124-943 are one giant f-string. Every `{` and
  `}` in the JS/CSS body must be doubled (`{{` / `}}`) to escape Python's format string.
  ~700 lines of escaped JS is extremely error-prone to edit and impossible to lint with
  standard JS tooling.
- Files: `html/gen_timeline_html.py:124-943`, `html/gen_audio_html.py:150-313`,
  `detectors/psd_shot_preview_v1.py:93-236`, `detectors/psd_shot_preview_v2.py:188-403`.
- Impact: Adding a JS feature risks a `KeyError` from Python or a silent syntax break.
  IDEs cannot syntax-check the embedded JS. No way to run eslint/prettier.
- Fix approach: Move HTML templates to standalone `.html` / `.js` files loaded at runtime,
  OR switch from f-strings to `string.Template` / `str.replace` for the few interpolated
  values, leaving the JS/CSS body untouched.

### Deprecated `event` global in inline onclick handlers
- Issue: Multiple generated HTML files call `event.target` inside `onclick` handlers
  without receiving `event` as a parameter. Relies on the deprecated `window.event`
  global, which is not standards-compliant and behaves differently across browsers.
- Files: `html/gen_audio_html.py:259,266`, `detectors/psd_shot_preview_v2.py:312,319`,
  `html/gen_timeline_html.py:709,715`.
- Impact: Buttons may silently fail to update active state in stricter browsers or
  future Chrome versions. Already broken in strict-mode modules.
- Fix approach: Pass `event` explicitly in the handler signature: `onclick="setCols(3, event)"`
  and define `function setCols(n, ev) { ev.target.classList... }`.

## Known Bugs

### Potential infinite loop in `detect_rapid_zones`
- Symptoms: If the rapid-zone detection logic regresses, the `while` loop never advances `i`.
- Files: `detectors/detect_v3b.py:156-167`.
- Trigger: Currently safe because the `len(nearby) >= 3` branch advances `i` by
  `len(nearby) - 1` plus the unconditional `i += 1` on line 167. But if someone refactors
  the condition (e.g. changes `>= 3` to `>= 2` while `len(nearby) == 1` is possible due to
  a filter change), `i` will not advance → hang the whole pipeline.
- Workaround: Add an assertion `assert len(nearby) >= 2` before the skip, or restructure
  as a `for` loop with explicit index management.

### HTML/JS injection via transcription text
- Symptoms: If Whisper outputs text containing backticks (`` ` ``), `${...}`, or HTML
  metacharacters, the generated HTML breaks or executes injected JS.
- Files: `html/gen_timeline_html.py:364,815` (uses `` `...${s.dialogue}...` `` template
  literal unescaped); `html/gen_audio_html.py:84` (f-string with raw dialogue);
  `detectors/psd_shot_preview_v1.py:144`, `detectors/psd_shot_preview_v2.py:163`.
- Trigger: Run pipeline on a video whose Whisper transcript contains any of: `` ` ``
  `${` `<` `>` `&` `"` — which Chinese whisper models routinely emit for code/URLs.
- Workaround: None. Users have to manually edit the transcript JSON.
- Fix approach: JSON-encode text once (already done via `json.dumps` for the data array),
  then in JS read from the data array — do NOT concatenate raw strings into template
  literals. For Python f-string HTML, use `html.escape(text)`.

### HTML injection via video filename / title / ep_name
- Symptoms: A video file named `<script>alert(1)</script>.mp4` produces HTML that executes
  the script when opened.
- Files: Every generator that embeds `{title}`, `{ep_name}`, `{stem_basename}`,
  `{video_src}` via f-string: `html/gen_timeline_html.py:128,209`, `html/gen_audio_html.py:155`,
  `html/gen_shots_preview.py:142,231`, `detectors/psd_shot_preview_v1.py:128`,
  `detectors/psd_shot_preview_v2.py:263`.
- Trigger: Malicious or pathological filename passed as `--video`.
- Workaround: Avoid exotic filenames.
- Fix approach: Wrap every interpolation in `html.escape(...)`. The `main` branch's
  `html/gen_prompts_html.py` already imports `html as html_mod` — replicate that pattern.

### Whisper fallback swallows all exceptions
- Symptoms: `faster-whisper` failing for any reason (CUDA OOM, model download error,
  corrupted audio, file permission) is silently caught and retried with `openai-whisper`,
  hiding the real error from the user.
- Files: `audio/transcribe.py:119-122`.
- Trigger: Any non-`ImportError` exception from `transcribe_faster_whisper`.
- Workaround: Run with `--backend faster-whisper` to force the error to surface.
- Fix approach: Narrow the except clause to specific recoverable exceptions
  (`RuntimeError`, `OSError`). Log the full traceback before falling back.

### `serve.py` leaks file descriptors on client disconnect
- Symptoms: If a browser cancels a Range request mid-stream (e.g. seeks repeatedly),
  the underlying `f = open(path, "rb")` may not be closed because `_Partial.read` returns
  `b""` on exhaustion but the wrapper never calls `f.close()`.
- Files: `scripts/serve.py:36,80-96`.
- Trigger: Many concurrent Range requests with frequent cancels (typical when scrubbing
  a long video).
- Workaround: Restart the server periodically.
- Fix approach: Make `_Partial` a context manager (`__enter__`/`__exit__`) or have
  `SimpleHTTPRequestHandler` close `f` in its `finally` block by overriding `copyfile`.

### Stale-cache false positive when `step_timeline` source missing
- Symptoms: `os.path.getmtime(shots_json)` will raise `FileNotFoundError` if `shots.json`
  was deleted between steps; `run_pipeline.py:143-148` does not guard this.
- Files: `run_pipeline.py:143-148`.
- Trigger: User deletes `shots.json` but leaves `timeline.html` in place, then re-runs.
- Workaround: Run with `--force` to clear cache.
- Fix approach: Wrap mtime comparisons in `if not os.path.exists(...): rebuild()`.

## Security Considerations

### `scripts/serve.py` binds to `0.0.0.0` with no auth
- Risk: `RangeRequestHandler` listens on all interfaces (line 107) on port 8765 with no
  authentication, no rate limiting, and no access control. Anyone on the LAN can browse
  the entire working directory (it calls `os.chdir(sys.argv[1])`) — including the
  source video, stems, and any other files in that directory.
- Files: `scripts/serve.py:107`, `scripts/serve.py:21-34` (directory listing via
  inherited `list_directory`).
- Current mitigation: None. The print on line 108 says `http://localhost:` but the
  actual bind is `0.0.0.0`.
- Recommendations: Bind to `127.0.0.1` by default; add a `--host` flag for explicit
  opt-in to LAN exposure. Document the risk in README.

### Path traversal via `serve.py`
- Risk: While `SimpleHTTPRequestHandler.translate_path` does basic normalization, the
  handler serves whatever directory the user runs from. Combined with `0.0.0.0` binding,
  a user who runs `python scripts/serve.py ~` exposes their home directory.
- Files: `scripts/serve.py:21-23,107`.
- Current mitigation: Relies on stdlib `translate_path` (rejects `..` escape).
- Recommendations: Restrict to `output/<stem>/` only; reject paths outside the served
  root explicitly.

### Unescaped strings in generated HTML
- Risk: See "HTML injection via video filename" under Known Bugs. Filenames, episode
  names, and transcription text all flow into HTML/JS contexts without escaping.
- Files: All `html/*.py` generators.
- Current mitigation: None on this branch. `main` branch's `gen_prompts_html.py`
  demonstrates the correct pattern with `html.escape`.
- Recommendations: Add `import html as html_mod` to every generator; wrap every
  f-string interpolation of user-derived text in `html_mod.escape(...)`.

### `.gitignore` excludes generated HTML
- Risk: `.gitignore` lists `*.html`, `*.mp4`, `*.wav`, `output/`. This is correct for
  artifacts but means an attacker who tricks a user into running the pipeline on a
  crafted video can produce an HTML file with injected JS that the user then shares
  publicly (e.g. commits to a different repo, hosts on a static site).
- Files: `.gitignore:1-8`.
- Current mitigation: None.
- Recommendations: Validate / escape inputs (fixes the root cause). Optionally add
  a warning banner to generated HTML when filename looks suspicious.

## Performance Bottlenecks

### `run_pass4_dissolves` loads every frame into memory
- Problem: The function reads the entire video frame-by-frame and stores all histograms
  (`all_h`) and mean RGB values (`all_rgb`) as Python lists before doing any analysis.
- Files: `detectors/detect_v3b.py:232-244`.
- Cause: O(N) memory where N = total frames. A 30-min video at 30fps = 54,000 entries ×
  (4096-float histogram + 3-tuple) ≈ 900MB resident. 1-hour video can OOM on a 4GB box.
- Improvement path: Stream the dissolve detection in a single pass — compute the
  sliding-window correlation online (keep a deque of last `window` histograms) instead
  of materializing the full list.

### Frame extraction spawns one ffmpeg per shot
- Problem: `extract_first_last_frames` and equivalents loop over shots and call
  `subprocess.run(["ffmpeg", "-ss", ...])` once per (shot, frame_type).
- Files: `detectors/psd_shot_preview_v1.py:80-88`, `detectors/psd_shot_preview_v2.py:139-147`,
  `html/gen_shots_preview.py:42-50`, `html/gen_timeline_html.py:965-996`.
- Cause: For 500 shots × 2 frames = 1000 ffmpeg subprocess spawns. Each spawn has
  ~50-200ms overhead plus codec init, on top of actual seek+decode work.
- Improvement path: Use a single `ffmpeg -vf "select='eq(n,FRAME_NO)+...'"` batch call,
  or open the video once with `cv2.VideoCapture` and seek within the Python process.

### Pass3 uses `cap.set(CAP_PROP_POS_FRAMES, ...)` for seeking
- Problem: Per-shot, the function seeks the capture to `sf` then reads sequentially.
  H.264 intra-frame seeking in OpenCV is approximate and may decode from the previous
  keyframe, wasting CPU.
- Files: `detectors/detect_v3b.py:208`.
- Cause: For videos with sparse keyframes (typical of CRF=20 H.264 output), each seek
  re-decodes from the last IDR frame, making Pass3 effectively O(N²) on long videos.
- Improvement path: Pre-decode the video to a lossless intermediate (or read sequentially
  across all long-shot segments in a single pass, tracking which segment each frame
  belongs to).

### `run_pass2_histcorr` decodes JPEGs in a pure-Python loop
- Problem: Lines 105-114 open each sampled frame with PIL, convert to numpy, and compute
  an 8x8x8 histogram per iteration. No vectorization, no batch loading.
- Files: `detectors/detect_v3b.py:105-114`.
- Cause: 5fps × 1-hour video = 18,000 PIL.Image.open calls + per-frame numpy ops.
  Python overhead dominates wallclock.
- Improvement path: Use `cv2.VideoCapture` to read directly (skip the JPEG sample Frames
  dir entirely), or batch-decode with `imageio` / `pyav`.

### XHR blob preload loads all 3 stem wavs into browser memory
- Problem: On page load, three parallel `XMLHttpRequest`s fetch `vocals.wav`, `drums.wav`,
  `other.wav` as blobs and convert to object URLs.
- Files: `html/gen_timeline_html.py:524-540`.
- Cause: Demucs 48kHz stems for a 5-min video are ~50-100MB each → 300MB+ resident in
  the browser tab on page load. Long videos can exhaust browser memory / crash the tab.
- Improvement path: Drop the XHR preload; rely on HTTP Range seeking on the `<audio>`
  element (the `scripts/serve.py` Range-aware server exists precisely for this). Or
  lazy-load stems only on first click.

### `drawWaveforms` re-runs on every resize without debouncing
- Problem: `window.addEventListener('resize', () => setTimeout(drawWaveforms, 100))`
  schedules a new redraw for every resize event without clearing prior timers.
- Files: `html/gen_timeline_html.py:486`.
- Cause: Rapid window resizing stacks dozens of redraw calls; canvas paint is expensive
  at high TIMELINE_H. Visible jank.
- Improvement path: Track the timer ID and `clearTimeout` before scheduling a new one.

## Fragile Areas

### `html/gen_timeline_html.py` monolith
- Files: `html/gen_timeline_html.py` (1083 lines).
- Why fragile: Mixes Python argument parsing, JSON loading, frame extraction, wav I/O,
  HTML/CSS/JS template (700+ lines in one f-string), and CLI entry point in one file.
  The f-string doubling of every `{`/`}` makes any JS edit a hazard.
- Safe modification: Test the generated HTML by actually opening it in a browser after
  every change; do not trust Python syntax validity alone (a successful f-string render
  does not imply valid JS).
- Test coverage: None.

### `run_pipeline.py` step functions return `None` on skip
- Files: `run_pipeline.py:84-166`.
- Why fragile: Each `step_*` function returns either the output path or `None` depending
  on skip flag and cache state. Downstream code must defensively handle `None` for every
  input. `step_timeline` line 145 already has `if audio_json else 0` guards, but
  `os.path.getmtime(shots_json)` on line 144 assumes `shots_json` exists (no None guard
  since `step_detect` exits the process if missing).
- Safe modification: Read the function's skip branch carefully before changing argument
  flow; do not assume non-None returns from skipped steps.
- Test coverage: None.

### Cache invalidation by filename only
- Files: `run_pipeline.py:88-95,107-109,127-129`.
- Why fragile: Existence of `shots.json` / `audio_analysis.json` / `transcript.json`
  is treated as proof of validity. If a user renames a different video to match an
  existing `<stem>` name, stale results are silently loaded. No checksum, no video
  mtime check, no duration sanity check.
- Safe modification: When changing pipeline behavior, always pass `--force` to invalidate
  caches during testing.
- Test coverage: None.

### `detect_v3b.ensure_h264` filename collision
- Files: `detectors/detect_v3b.py:64` writes `<stem>_h264.mp4` next to the input video;
  `run_pipeline.py:65` writes `h264.mp4` (no stem) into `work_dir`.
- Why fragile: Two different cache locations for the same transcode. Switching between
  `python detectors/detect_v3b.py --video X.mp4` and `python run_pipeline.py --video X.mp4`
  causes the transcode to run twice.
- Safe modification: Always invoke via `run_pipeline.py` for consistent caching.
- Test coverage: None.

### `cv2` imports deferred to function body
- Files: `detectors/detect_v3b.py:100,197,231`.
- Why fragile: `import cv2` lives inside functions rather than at module top. Means
  import errors surface at runtime mid-pipeline rather than at startup. Also hides the
  cv2 dependency from any dependency scanner.
- Safe modification: Leave as-is if you want to allow running Pass1 without cv2 (the
  function-level import does enable partial execution). Move to top-level otherwise.
- Test coverage: None.

## Scaling Limits

### Pass3 + Pass4 frame-by-frame cv2 reads
- Current capacity: Tested on short-form content (≤10 min based on example JSONs).
- Limit: Quadratic decode cost on long videos with sparse keyframes. 30-min+ videos
  may take hours in Pass3/Pass4.
- Scaling path: Pre-decode to lossless intermediate, or rewrite passes to share a single
  sequential scan.

### HTML output size (base64-embedded frames)
- Current capacity: ~500 shots × 2 frames × ~30KB ≈ 30MB HTML works in modern browsers.
- Limit: Browsers degrade past ~50MB HTML; mobile Safari hard-fails around 25MB.
- Scaling path: Stop embedding frames as base64. Write frames to disk alongside HTML
  and reference by relative path. `gen_timeline_html.py` already does this for stems —
  extend the pattern to frames.

### Canvas 65535px height cap
- Current capacity: Handled by segmenting into multiple `<canvas>` elements at
  `CANVAS_MAX_H = 60000` (`html/gen_timeline_html.py:409`).
- Limit: Very long videos (TIMELINE_H > 600000px) create 10+ canvas elements per track
  → DOM bloat, slower `drawWaveforms`.
- Scaling path: Switch to WebGL waveforms, or downsample buckets for long videos.

### Demucs single-shot processing
- Current capacity: One Demucs run per video; no chunking.
- Limit: 1-hour video = single 1-hour Demucs run with no progress checkpointing. Any
  failure (OOM, signal) loses everything.
- Scaling path: Chunk by silence boundaries (use Whisper VAD output), run Demucs per
  chunk, then concatenate stems.

## Dependencies at Risk

### `openai-whisper` vs `faster-whisper` API drift
- Risk: The two backends have different output shapes (`faster-whisper` uses `s.start`
  attribute access, `openai-whisper` uses `s["start"]` dict access). The code keeps two
  separate transcription paths, but if either library ships a breaking release, the
  affected path breaks silently — users on `--backend auto` won't know which ran.
- Impact: Transcription fails or returns malformed JSON.
- Migration plan: Pin both libraries in a (future) `requirements.txt`. Add a smoke test
  that loads each backend and transcribes a 1-second clip in CI.

### Demucs CLI output path drift
- Risk: `audio/separate_stems.py:67-74` already has a fallback path
  (`if not stem_dir.exists(): candidate = output_dir / model`) to handle "某些 Demucs
  版本" — the comment indicates Demucs output layout has already changed across releases.
- Impact: Newer Demucs may write stems somewhere unexpected; downstream audio analysis
  fails with `FileNotFoundError`.
- Migration plan: Pin `demucs==4.0.*`. Long-term, prefer Demucs's Python API over the CLI
  for stable output paths.

### PySceneDetect detector API
- Risk: `AdaptiveDetector(adaptive_threshold=..., min_scene_len=...)` and
  `ContentDetector(threshold=..., min_scene_len=...)` signatures assumed stable across
  `scenedetect` versions. v0.7 renamed parameters.
- Impact: V1/V2/V3b detectors break on upgrade.
- Migration plan: Pin `scenedetect>=0.6,<0.7` (or whatever version works). Add import-
  time API check.

### `torch` imported unconditionally on `main` branch
- Risk: `audio/transcribe.py` on `main` does `import torch` at module top — but
  `faster-whisper` does not strictly require torch (it uses CTranslate2). This forces a
  heavy dep on CPU-only users.
- Impact: Install fails or imports slow on machines without a CUDA toolkit.
- Migration plan: Move `import torch` inside the device-selection branch where it's
  actually used.

## Missing Critical Features

### No automated tests
- Problem: Zero `test_*.py` / `*_test.py` files in the entire repo. No `pytest.ini`,
  `tox.ini`, or `conftest.py`. No CI configuration (`.github/`, `.gitlab-ci.yml`).
- Blocks: Cannot safely refactor the duplicated ffmpeg/detector code; cannot verify
  detection thresholds still produce sane output after a change; cannot catch HTML
  escaping regressions.
- Priority: High.

### No dependency manifest
- Problem: No `requirements.txt` / `pyproject.toml`. See "Tech Debt" above.
- Blocks: Reproducible installs, CI setup, contributor onboarding.
- Priority: High.

### No structured logging
- Problem: Every module uses `print()` for status output. No `logging` framework, no
  log levels, no way to silence progress or capture debug info to a file.
- Blocks: Debugging long pipeline runs; silencing output when run from a scheduler.
- Priority: Medium.

### No resume from partial failure
- Problem: `--skip-detect` / `--skip-separate` / `--skip-transcribe` exist but require
  manual intervention. If Demucs dies at 95%, the user must re-run with `--skip-detect`
  manually and loses Demucs progress.
- Blocks: Long unattended runs; CI integration.
- Priority: Medium.

### No GPU preflight check
- Problem: `--device cuda:0` is passed blindly to Demucs and Whisper subprocesses. If
  CUDA is unavailable or the GPU has insufficient VRAM, the error surfaces deep inside
  the subprocess with an unhelpful traceback.
- Blocks: Friendly UX for first-time users.
- Priority: Low.

## Test Coverage Gaps

### Entire pipeline is untested
- What's not tested: Every component — `run_pipeline.py` step orchestration,
  `detectors/detect_v3b.py` (4 detection passes with magic thresholds),
  `audio/separate_stems.py` (Demucs invocation + per-shot RMS),
  `audio/transcribe.py` (backend auto-selection + fallback), all four HTML generators
  (string templating with injection risks), `scripts/serve.py` (Range header parsing).
- Files: All `.py` files in repo.
- Risk: Any refactor or dependency bump can break the pipeline silently. Detection
  quality cannot be regression-tested against known example JSONs in `examples/`.
- Priority: High — at minimum add: (1) unit tests for pure functions
  (`merge_cuts`, `classify_shot`, `compute_rms_energy`, Range parser in `serve.py`);
  (2) a smoke test that runs the full pipeline on a 5-second test video and asserts
  expected JSON schema for each stage output; (3) snapshot test that generated HTML
  contains expected structural elements and escapes `<script>` in a malicious filename.

### No fixture video for integration testing
- What's not tested: End-to-end behavior on a real video.
- Files: `examples/` contains only output JSONs, no input video.
- Risk: Cannot run the pipeline in CI without a test fixture.
- Priority: Medium — commit a small (≤2s) test MP4 under `examples/test/` and write
  a `tests/test_pipeline_e2e.py` that runs each stage and validates output schema.

---

*Concerns audit: 2026-07-20*
