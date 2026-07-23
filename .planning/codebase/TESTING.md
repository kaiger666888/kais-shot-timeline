# Testing Patterns

**Analysis Date:** 2026-07-20

## TL;DR

**There is no test infrastructure in this codebase.** No test files, no test
framework, no fixtures, no CI. This is consistent with an early-stage
analysis/research tool that has been developed iteratively against real video
inputs. The information below documents the current state honestly and
provides guidance for introducing tests.

## Test Framework

**Runner:** Not configured. None of the following exist anywhere in the repo:

- `pytest.ini`, `pyproject.toml` `[tool.pytest]`, `setup.cfg [tool:pytest]`, `tox.ini`
- `conftest.py`
- Any file matching `test_*.py` or `*_test.py`
- `.pytest_cache/`, `.mypy_cache/`, `.coverage`, `htmlcov/`
- `requirements-dev.txt` / `requirements-test.txt`

**Assertion Library:** None. (If tests are added, `pytest` + stdlib `assert` is the recommended combo — see "Recommendations" below.)

**Run Commands:** None defined. No `Makefile`, no `scripts/test.*`, no npm-style `package.json`. The only executable in `scripts/` is `scripts/serve.py` (a dev HTTP server, unrelated to testing).

## Test File Organization

**Location:** N/A — no tests exist.

**Expected layout (when added):** based on the existing project structure (flat modules with `audio/`, `detectors/`, `html/`, `scripts/` packages without `__init__.py` files), tests should live in a parallel top-level `tests/` directory:

```
kais-shot-timeline/
├── audio/
├── detectors/
├── html/
├── scripts/
├── run_pipeline.py
└── tests/                      # NEW — recommended location
    ├── conftest.py             # shared fixtures (sample shot JSON, fake wav)
    ├── test_classify_shot.py   # unit tests for audio/separate_stems.py:classify_shot
    ├── test_compute_rms.py     # unit tests for audio/separate_stems.py:compute_rms_energy
    ├── test_merge_cuts.py      # unit tests for detectors/detect_v3b.py:merge_cuts
    └── test_build_shots_js.py  # unit tests for html/gen_timeline_html.py:build_shots_js
```

Co-locating as `audio/test_separate_stems.py` is also acceptable but `tests/` is preferable because the existing packages lack `__init__.py` and tests would otherwise be picked up by wildcard imports.

## Coverage

**Requirements:** None enforced.

**Current coverage:** Effectively 0% by automated tests. The only "checked at runtime" code paths are exercised by manually running `python run_pipeline.py --video <input.mp4>` and visually inspecting the generated HTML.

**Recommendation:** When introducing tests, target these high-leverage **pure functions** first — they have no I/O / ffmpeg / GPU dependencies and are the easiest to unit-test:

| Function | File:Line | Why test |
|----------|-----------|----------|
| `classify_shot(ratios)` | `audio/separate_stems.py:118-129` | Pure dict→str mapping with 4 branches (dialogue/bgm/sfx/mixed). One missing `>` flips output. |
| `compute_rms_energy(...)` | `audio/separate_stems.py:91-98` | Numpy math on a slice; easy to verify with hand-crafted arrays. |
| `compute_spectral_centroid(...)` | `audio/separate_stems.py:101-115` | FFT-based; could regress silently. |
| `merge_cuts(...)` | `detectors/detect_v3b.py:174-190` | Pure list-of-floats deduplication with rapid-zone logic. |
| `detect_rapid_zones(...)` | `detectors/detect_v3b.py:156-167` | Pure list-of-floats → list-of-tuples. |
| `in_rapid_zone(t, zones)` | `detectors/detect_v3b.py:170-171` | Trivial 1-liner; trivial test. |
| `build_shots_js(...)` | `html/gen_timeline_html.py:24-54` | Dict merge; segment→shot bucketing loop has off-by-one risk. |
| `probe_duration(...)` | `run_pipeline.py:49-56` / `audio/transcribe.py:46-63` | Wraps ffprobe; needs subprocess mocking but worth covering because fallback returns `0.0` silently. |

## What Has No Automated Verification Today

Listing the highest-risk untested areas (in rough priority order):

1. **`html/gen_timeline_html.py:build_html`** (~845 lines, ~50% of the codebase's logic). Embeds JS template with playhead / stem playback / scroll sync. Currently validated only by opening the output in a browser. Any Python f-string interpolation regression or unescaped `{{`/`}}` will silently corrupt the JS.
2. **`detectors/detect_v3b.py:detect_shots`** — the main 4-pass fusion. Depends on cv2 + PIL + actual video files; would need either a tiny fixture video or extensive mocking.
3. **`audio/transcribe.py`** — Whisper backends require GPU and a real model download; not unit-testable cheaply.
4. **`run_pipeline.py`** orchestration — subprocess-driven; integration-test territory.
5. **The CLI surface of every script's `main()`** — argparse contracts (`required=True`, default values, `choices=[...]`) drift silently. Smoke tests like `python -c "import subprocess; subprocess.run([sys.executable, 'detectors/detect_v3b.py', '--help'], check=True)"` would catch import-time errors.

## Fixtures and Factories

**Existing fixture-like data:**
- `examples/ep01_shots.json` — real shot-detection output, list of `{id, start_sec, end_sec, duration}`. Useful as a golden-input fixture for tests of `analyze_shots`, `build_shots_js`, `gen_timeline_html`.
- `examples/xiaojianghu_ep01_shots_v2.json` — V2 detector output, same schema.

No factory functions exist. Tests currently cannot be written for the audio/HTML pipeline without either (a) generating synthetic wav + JSON inputs or (b) reusing these example JSONs.

**Recommended fixture pattern** (when adding tests):
```python
# tests/conftest.py
import json, pathlib
import pytest
import numpy as np

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"

@pytest.fixture
def shots_ep01():
    return json.loads((EXAMPLES / "ep01_shots.json").read_text())

@pytest.fixture
def fake_vocals_stem():
    """1 second of silence at 16kHz mono — feeds compute_rms_energy."""
    return np.zeros(16000, dtype=np.float32), 16000
```

## Mocking

**Framework:** None installed. (`unittest.mock` is in the stdlib and usable without adding deps.)

**Patterns to adopt when adding tests:**

- **Mock `subprocess.run`** for ffprobe/ffmpeg wrappers. Keep cmd-shape assertions:
  ```python
  from unittest.mock import patch
  
  def test_probe_duration_parses_ffprobe_output():
      fake = subprocess.CompletedProcess(args=[], returncode=0,
                                         stdout="12.34\n", stderr="")
      with patch("subprocess.run", return_value=fake):
          assert probe_duration("any.mp4") == 12.34
  ```

- **Mock cv2.VideoCapture** for `run_pass3_long_shots` / `run_pass4_dissolves` — these read every frame sequentially. Inject a stub exposing `get(CAP_PROP_FPS)`, `set`, `read`, `release`.

- **Do NOT mock** the pure helpers (`classify_shot`, `compute_rms_energy`, `merge_cuts`). They take primitives and should be tested with hand-built inputs.

- **Do NOT try to mock** Demucs or Whisper — too many internal touch points. Mark such tests `@pytest.mark.integration` and skip by default (`pytest -m "not integration"`).

## Common Patterns

No existing test patterns to mirror. When introducing them, follow:

**Async Testing:** Not applicable — no async code anywhere in the codebase.

**Error Testing:** Validate the documented `raise` sites:
```python
import pytest
from audio.separate_stems import analyze_shots

def test_analyze_shots_raises_when_no_stems(tmp_path):
    empty = tmp_path / "empty_stems"
    empty.mkdir()
    shots = tmp_path / "shots.json"
    shots.write_text('[{"id":1,"start_sec":0,"end_sec":1,"duration":1}]')
    with pytest.raises(FileNotFoundError, match="No stems found"):
        analyze_shots(str(empty), str(shots), str(tmp_path / "out.json"))
```

This single test would have caught the `raise FileNotFoundError` contract at `audio/separate_stems.py:144`.

**Snapshot / golden testing:** Recommended for the HTML generators. Generate HTML for a known `shots.json` + synthetic stems, then assert key substrings appear in the output (`<title>`, `const SHOTS =`, `const DURATION =`). Full HTML equality is brittle due to embedded timestamps.

## Recommendations (Summary)

1. **Add `pytest`** as the first dev dependency. Document in a new `requirements-dev.txt` or `pyproject.toml`.
2. **Start with pure-function unit tests** for `audio/separate_stems.py` and `detectors/detect_v3b.py` — no mocking required, highest value per line.
3. **Add a `conftest.py`** that exposes the `examples/*.json` files as fixtures.
4. **Add one smoke test** per script: `[sys.executable, "audio/transcribe.py", "--help"]` must exit 0. Cheap and catches import-time / argparse breakage.
5. **Defer integration tests** (real video → full pipeline) until a CI runner with ffmpeg + GPU is available — they are heavy and currently infeasible to run in CI without significant setup.
6. **Do not attempt to retrofit tests for `html/gen_timeline_html.py:build_html` in full** — refactor the giant template into smaller helper functions first, then test those helpers in isolation.

## Test Types

**Unit Tests:** None.

**Integration Tests:** None.

**E2E Tests:** None. The de-facto "E2E test" today is the developer running `python run_pipeline.py --video <mp4>` on a real episode and visually verifying `output/<stem>/timeline.html` in a browser.

---

*Testing analysis: 2026-07-20*
