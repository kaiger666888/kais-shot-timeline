# External Integrations

**Analysis Date:** 2026-07-20

## APIs & External Services

**None — no network APIs are called by any code path.** This project is fully offline once ML models are cached locally. No HTTP client (`requests`, `httpx`, `aiohttp`, `urllib.request`) is imported anywhere in `*.py`.

The only outbound network traffic occurs **implicitly** on first run, inside third-party libraries:
- `faster-whisper` / `openai-whisper` download model weights from Hugging Face Hub (`https://huggingface.co/SYSTRAN/faster-whisper-large-v3`, `https://openaipublic.azureedge.net/...`) into `~/.cache/huggingface/` / `~/.cache/whisper/`
- `demucs` downloads `htdemucs` checkpoint from `https://dl.fbaipublicfiles.com/demucs/` into `~/.cache/torch/hub/checkpoints/`
- These URLs are **not referenced in project code**; they live inside the upstream packages

**External CLI tools (invoked via `subprocess`, treated as integrations):**

| Tool | Invocation site | Purpose |
|------|-----------------|---------|
| `ffmpeg` | `run_pipeline.py:71`, `detectors/detect_v3b.py:53,75`, `audio/transcribe.py:38`, `html/gen_shots_preview.py:29`, `html/gen_audio_html.py:27`, `html/gen_timeline_html.py:976` | AV1→H264 transcoding, frame extraction, 5-fps sampling, 16 kHz mono WAV extraction |
| `ffprobe` | `run_pipeline.py:43,51`, `detectors/detect_v3b.py:33,44`, `audio/transcribe.py:48,58` | Codec detection (AV1 vs H264), duration probing |
| `python -m demucs` | `audio/separate_stems.py:55-65` | 4-stem source separation (`htdemucs` default) |

All subprocess calls use `subprocess.run(cmd, check=True)` or `capture_output=True`. The demucs invocation explicitly prepends `sys.executable` so it runs in the same interpreter as the parent process.

## Data Storage

**Databases:**
- None. No SQL, NoSQL, vector DB, or search index

**File Storage:**
- Local filesystem only. All artifacts written under `output/<video-stem>/` (path template defined in `run_pipeline.py:206`)

**Inter-process contract (JSON schemas produced and consumed):**
- `shots.json` — array of `{id, start_sec, end_sec, duration}`. Produced by `detectors/detect_v3b.py:347-358`, consumed by `audio/separate_stems.py:146`, `html/gen_timeline_html.py:1032`, `html/gen_shots_preview.py:119`
- `audio_analysis.json` — `{episode, duration, stems, shots:[{shot_id, start_sec, end_sec, duration, energies, ratios, spectral_centroid, dominant_type}], type_distribution}`. Produced by `audio/separate_stems.py:182-191`, consumed by `html/gen_audio_html.py:339` and `html/gen_timeline_html.py:1036`
- `transcript.json` — `{backend, model, language, duration, segments:[{start, end, text}], text, source}`. Produced by `audio/transcribe.py:160-161`, consumed by `html/gen_timeline_html.py:1041-1044`
- `frames.json` — array of `{id, first_frame, last_frame}` where `first_frame`/`last_frame` are `data:image/jpeg;base64,...` URIs. Produced/consumed by `html/gen_timeline_html.py:947-1002`

**Caching:**
- None at runtime. Pipeline-level caching is via file existence checks (`run_pipeline.py:89, 107, 125, 143`). No Redis, no Memcached, no on-disk index beyond the file mtimes

## Authentication & Identity

**Auth Provider:**
- None. No login, no API keys, no tokens. No code reads `os.environ` for credentials.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, no Rollbar, no structured logger

**Logs:**
- Unstructured `print()` to stdout everywhere (e.g. `[1/5]`, `[pass1] PSD AdaptiveDetector: N cuts`, `[analyze] type distribution:`, `[demucs]`, `[ffmpeg]`, `[gen-timeline-html]`). No `logging` module usage. The pipeline entry point (`run_pipeline.py:79-81`) prints each step's command and a separator banner

**Metrics:**
- None. The only "telemetry" is the per-shot count summary printed at the end of detection (`detectors/detect_v3b.py:361-363` — `short<1s=N, long>8s=M`) and the type-distribution histogram from `audio/separate_stems.py:178-180`

## CI/CD & Deployment

**Hosting:**
- Local developer machine only. Generated HTML is opened via `scripts/serve.py` (Range-aware static server on `http://localhost:8765/`) or `python3 -m http.server`

**CI Pipeline:**
- None. No `.github/workflows/`, no `.gitlab-ci.yml`, no `Jenkinsfile`, no `Makefile`

**Release:**
- None. No git tags, no version identifier in any source file, no `__version__`. The most recent commit on `main` is `cacd7da fix stem 同步：换 Range-aware HTTP server + 简化 playStem`

## Environment Configuration

**Required env vars:**
- None. See STACK.md "Configuration" — all configuration is via CLI flags

**Secrets location:**
- N/A. No secrets, API keys, or credentials are read by the codebase
- Note: `~/.cache/huggingface` and `~/.cache/torch` contain Hugging Face / FAIR model weights (not credentials, but cached downloads). They are not project-managed

**Default model / language parameters (from `run_pipeline.py:181-190`):**
- Whisper model: `large-v3`
- Whisper language: `zh` (Chinese)
- Whisper backend: `auto` (faster-whisper first, openai-whisper fallback)
- Demucs model: `htdemucs` (4-stem: vocals / drums / bass / other)
- Device: unset → each backend picks (CUDA auto-detected by PyTorch)

## Webhooks & Callbacks

**Incoming:**
- None. `scripts/serve.py` is a one-way static file server with no POST/PUT handlers, no webhook routes

**Outgoing:**
- None

## Downstream Consumer Integration (kais-* platforms)

**Status:** **Not yet integrated.** The repo description mentions that structured datasets are intended to feed `kais-movie-center` / `kais-movie-pipeline` / `kais-aigc-platform`, but **no code in this repo exports to, calls, or references any of those platforms**. The handoff today is purely via the JSON intermediates listed above (`shots.json`, `audio_analysis.json`, `transcript.json`), which a downstream consumer would need to read from `output/<video-stem>/` out-of-band.

**Adjacent untracked artifacts (worth flagging for the planner):**
- `prompts/` directory — present in `git status` as `?? prompts/` (untracked) but empty on disk at analysis time. Likely a placeholder for prompt-extraction output intended for kais-aigc-platform
- `html/gen_prompts_html.py` — untracked, referenced in `git status` but not present on disk; presumably a future generator for prompt-extraction HTML (parallel to `gen_audio_html.py` / `gen_shots_preview.py`)

These are signals that a prompt-extraction pipeline step is planned but not yet implemented.

## Notable Integration Patterns

- **All "integrations" are local subprocess + filesystem contracts.** There is no RPC, no message queue, no shared database. Adding a real downstream integration (e.g. POST to a kais-movie-center ingest endpoint) would require introducing the first HTTP client in the codebase.
- **Stem files are referenced by basename convention, not path.** `html/gen_timeline_html.py:516,529` generates `<audio src="<basename>_vocals.wav">` and pre-loads via XHR to the same basename-relative URL. The HTML expects the three stem WAVs to be **co-located in the same directory as the HTML** (see `README.md:138-141`). The pipeline copies/symlinks are not automated — `run_pipeline.py:250-253` only prints a hint if the file is missing.
- **AV1 detection is a codec-aware shortcut.** `run_pipeline.py:59-74` + `detectors/detect_v3b.py:41-67` probe the input codec via `ffprobe`; if `av1`, the video is transcoded to H264 (`libx264 -preset fast -crf 20 -an`) before being fed to PySceneDetect, because PySceneDetect is unreliable on AV1. This is the only codec-specific branch in the codebase.

---

*Integration audit: 2026-07-20*
