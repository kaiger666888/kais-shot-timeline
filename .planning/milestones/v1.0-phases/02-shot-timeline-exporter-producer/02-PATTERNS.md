# Phase 2: shot-timeline Exporter (Producer) - Pattern Map

**Mapped:** 2026-07-20
**Files analyzed:** 4 (2 NEW + 2 MODIFY)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/export_asset.py` (NEW) | utility (standalone CLI manifest writer) | file-I/O + transform | `html/gen_timeline_html.py` (CLI shape) + `spec/validate.py` (inline jsonschema) + `run_pipeline.py:probe_duration` (ffprobe fallback) | exact (multi-source) |
| `scripts/check_range.py` (NEW) | test (standalone exit-0/1 verifier) | request-response (HTTP) + subprocess | `spec/validate.py` (exit-code verifier shape) + `scripts/serve.py` (server boot target) | role-match |
| `run_pipeline.py` (MODIFY) | orchestrator (pipeline driver) | event-driven (step sequence) | self-referential — mirror `step_timeline` / `step_transcribe` | exact (self) |
| `scripts/serve.py` (MODIFY) | server / middleware (Range-aware HTTP) | request-response (HTTP Range) | self-referential — `_Partial` class (lines 85-96) | exact (self) |

---

## Pattern Assignments

### `scripts/export_asset.py` (utility, file-I/O + transform)

**Analog (primary):** `html/gen_timeline_html.py` — newest standalone CLI in this repo using the argparse + `main()` + `if __name__ == "__main__"` shape with Chinese `help=` strings and a single `print(f"[<tag>] ...")` final-status line.

**Analog (secondary, inline jsonschema):** `spec/validate.py:52-57, 69-94` — canonical `Draft202012Validator` usage.

**Analog (tertiary, ffprobe fallback):** `run_pipeline.py:49-56` — `probe_duration` pattern.

#### Module docstring pattern

**Source:** `html/gen_timeline_html.py:1-17`

```python
#!/usr/bin/env python3
"""生成时间轴双面板 HTML（音轨波形 + stem 播放 + 自适应/线性双模式）。

该脚本由最终 855 行版本的 xiaojianghu_ep01_timeline.html 反向提取而来，
所有前端特性都对应保留：

  * 线性 vs 自适应双模式（toggleMode + buildShotLayout + getTimeY/getYTime）
  * ...
"""
```

**Apply to `export_asset.py`:** Chinese module docstring describing purpose, the 5 input JSONs, the 4 canonical symlinks produced, and CLI usage. Match this exact shape (shebang + triple-quoted docstring + bullet list of behaviors).

#### Imports pattern

**Source:** `html/gen_timeline_html.py:18-21`

```python
import argparse
import json
import os
from pathlib import Path
```

**Apply to `export_asset.py`:** Same stdlib-first block, plus `import sys` (for `sys.exit` on hard failure) and `import subprocess` (for ffprobe fallback + git SHA) and `from datetime import datetime, timezone` (for `generated_at`). `jsonschema` import should be **function-local inside the validate helper** (mirror `spec/validate.py:26` top-level is fine too, but function-local matches CLAUDE.md "lazy import for optional deps" convention).

#### argparse + Chinese help pattern

**Source:** `html/gen_timeline_html.py:1005-1030`

```python
def main():
    ap = argparse.ArgumentParser(description="时间轴双面板 HTML 生成器（含 stem 播放）")
    ap.add_argument("--shots", required=True, help="分镜 JSON")
    ap.add_argument("--audio-json", default=None,
                    help="audio/separate_stems.py 输出的 per-shot 分析 JSON")
    ap.add_argument("--frames", default=None,
                    help="首尾帧 JSON（[{id, first_frame, last_frame}]）；"
                         "若缺省，将从 --video 抽帧")
    # ... more flags ...
    ap.add_argument("--output", required=True, help="输出 HTML 路径")
    args = ap.parse_args()
```

**Apply to `export_asset.py`:** Same shape — argparse + Chinese `help=` + `--output required=True`. Required flags: `--work-dir`, `--video`, `--stems-source-dir`, `--output`. Optional: `--force` (`action="store_true"`).

#### JSON write pattern (ensure_ascii=False, indent=2)

**Source:** `audio/separate_stems.py:190` / `audio/transcribe.py:161` / `html/gen_audio_html.py:362` (all identical):

```python
json.dump(out, f, indent=2, ensure_ascii=False)
```

**Apply to `export_asset.py`:** Use exactly `json.dump(asset_dict, f, indent=2, ensure_ascii=False)` when writing `asset.json`. Per CLAUDE.md: `ensure_ascii=False` is mandatory for any file that may contain Chinese (asset.json's `source.video_filename` will contain Chinese for this project's episodes).

#### ffprobe fallback pattern (for `source.duration_sec`)

**Source:** `run_pipeline.py:49-56`

```python
def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0
```

**Apply to `export_asset.py`:** Copy verbatim (or inline the same logic) as a private `_probe_duration` helper. Prefer reading duration from `transcript.json#duration` first (always populated by `audio/transcribe.py`); use ffprobe only as a fallback if that field is missing.

#### Hard-failure error pattern

**Source:** `run_pipeline.py:203`

```python
video = os.path.abspath(args.video)
if not os.path.exists(video):
    sys.exit(f"input video not found: {video}")
```

**Apply to `export_asset.py`** (for the `prompts.json` presence guard mandated by CONTEXT/RESEARCH Pitfall 4):

```python
prompts_path = os.path.join(work_dir, "prompts.json")
if not os.path.exists(prompts_path):
    sys.exit(
        f"prompts.json 不存在: {prompts_path}\n"
        f"  asset.schema.json 的 data.prompts 是 required 字段 —— 不可省略。\n"
        f"  prompts.json 当前由独立步骤产出（未接入 run_pipeline）；"
        f"请先就位再运行导出。"
    )
```

#### Inline jsonschema validation pattern

**Source:** `spec/validate.py:52-57` (load_validator) + `spec/validate.py:87-94` (iter_errors + format)

```python
def load_validator(shape: str) -> Draft202012Validator:
    """根据形状名加载对应的 Draft202012Validator。"""
    schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


# ... inside validate_minimal() ...
validator = load_validator(shape)
errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
if errors:
    print(f"[FAIL] {shape}: {len(errors)} error(s)")
    print(_format_errors(errors))
    failures += 1
else:
    print(f"[valid] {shape}")
```

**Apply to `export_asset.py`:** Do NOT subprocess to `spec/validate.py` — its `SMOKE_SHAPES` (`spec/validate.py:49`) excludes `asset.json`, so subprocess validation would only check the 5 data shapes, not the freshly-written manifest. Instead inline the validator:

```python
# Path resolution: scripts/export_asset.py → repo root → spec/schemas/asset.schema.json
here = Path(__file__).parent.parent  # scripts/ → repo root
schema_path = here / "spec" / "schemas" / "asset.schema.json"
with open(schema_path, encoding="utf-8") as f:
    schema = json.load(f)
validator = Draft202012Validator(schema)
errors = sorted(validator.iter_errors(asset_dict), key=lambda e: list(e.absolute_path))
if errors:
    lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
             for e in errors]
    sys.exit(f"asset.json failed schema validation ({len(errors)} error(s)):\n"
             + "\n".join(lines))
```

#### Final-status print pattern

**Source:** `html/gen_timeline_html.py:1079`

```python
print(f"[gen-timeline-html] wrote {len(html):,} bytes → {args.output}")
```

**Apply to `export_asset.py`:** Use bracketed tag style (matches the project's logging convention from CLAUDE.md):

```python
print(f"[export-asset] wrote asset.json → {args.output}")
print(f"[export-asset] canonical symlinks: video.mp4, stems/{{vocals,drums,other}}.wav")
```

---

### `scripts/check_range.py` (test, request-response + subprocess)

**Analog (primary, exit-code verifier shape):** `spec/validate.py:141-180` — canonical standalone-script-with-sys.exit pattern.

**Analog (secondary, subprocess + argparse):** `run_pipeline.py:77-81` (`run_step`) and `html/gen_timeline_html.py:1005-1030` (argparse style).

**Analog (target under test):** `scripts/serve.py` — the server the check boots.

#### Standalone verifier-script shape (sys.exit(0/1))

**Source:** `spec/validate.py:141-180`

```python
def main() -> None:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="ShotTimelineAsset 规范校验器(对 minimal fixture + 真实生产产物做 schema 校验)"
    )
    ap.add_argument(
        "--strict-smoke",
        action="store_true",
        help="smoke 失败也计入退出码(默认 smoke 仅打印,不影响退出码)",
    )
    args = ap.parse_args()

    # ... work ...

    if total_strict_failures == 0:
        print("[validate] OK")
        sys.exit(0)
    else:
        print("[validate] FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Apply to `check_range.py`:** Same shape — argparse + Chinese `help=` + final `sys.exit(0 if ok else 1)`. No pytest (repo has zero test files — see RESEARCH §Validation Architecture).

#### Subprocess-to-Python-script pattern (boot serve.py)

**Source:** `run_pipeline.py:77-81` (run_step) + `run_pipeline.py:93-97` (child invocation):

```python
def run_step(cmd: list, label: str):
    """运行子进程，失败时抛出 RuntimeError。"""
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


# ...
run_step(
    [sys.executable, str(HERE / "detectors" / "detect_v3b.py"),
     "--video", video, "--frames-dir", frames_dir,
     "--sample-fps", str(sample_fps),
     "--output", shots_json],
    "[2/5] V3b scene detection")
```

**Apply to `check_range.py`:** Mirror the `[sys.executable, str(REPO / "scripts" / "serve.py"), asset_root, str(port)]` invocation — but use `subprocess.Popen` (not `run`) since the server runs until terminated. Use `try:/finally:` to ensure `proc.terminate()` runs even if assertion fails (mirrors `audio/transcribe.py:150-155` finally-cleanup idiom for temp wav).

#### Bracketed tag log style

**Source:** `spec/validate.py:153, 169-174` + CLAUDE.md "Bracketed stage prefix" convention:

```python
print(f"[validate] minimal fixture = {FIXTURE_DIR}")
# ...
print(f"[validate] minimal failures={minimal_failures}, "
      f"smoke failures={smoke_failures} "
      f"(strict-smoke={'on' if args.strict_smoke else 'off'})")
```

**Apply to `check_range.py`:** Use `[check-range]` prefix for all output lines (success and failure paths). Single OK/FAIL line at end matching `spec/validate.py:176,179` style.

#### Path-anchor constant pattern

**Source:** `run_pipeline.py:38`

```python
HERE = Path(__file__).parent.resolve()
```

**Apply to `check_range.py`:**

```python
REPO = Path(__file__).parent.parent.resolve()  # scripts/ → repo root
```

This lets the check locate `scripts/serve.py` regardless of CWD.

---

### `run_pipeline.py` changes (orchestrator, self-modification)

**Analog:** self-referential — the existing `step_timeline` (lines 139-166) is the literal template for `step_export`.

#### step_export template (mtime cache + subprocess)

**Source:** `run_pipeline.py:139-166` (`step_timeline` — the mtime-cache variant, most similar to export)

```python
def step_timeline(video: str, work_dir: str, shots_json: str,
                  audio_json: str, transcript: str, frames_json: str,
                  stems_dir: str, out_html: str, video_src: str,
                  stem_basename: str) -> str:
    if os.path.exists(out_html) and os.path.getmtime(out_html) > max(
            os.path.getmtime(shots_json),
            os.path.getmtime(audio_json) if audio_json else 0,
            os.path.getmtime(transcript) if transcript else 0):
        print(f"[5/5] cached timeline: {out_html}")
        return out_html
    cmd = [sys.executable, str(HERE / "html" / "gen_timeline_html.py"),
           "--shots", shots_json, "--output", out_html]
    if audio_json:
        cmd += ["--audio-json", audio_json]
    # ... more conditional flags ...
    run_step(cmd, "[5/5] timeline HTML generation")
    return out_html
```

**Apply to `step_export`:**

```python
def step_export(work_dir: str, video: str, stems_source_dir: str,
                asset_json: str, skip: bool, force: bool) -> str:
    if skip:
        print("[6/6] --skip-export: skipping asset export")
        return asset_json if os.path.exists(asset_json) else None
    # mtime cache: mirror step_timeline, but inputs are the 5 data JSONs + the video
    inputs = [
        os.path.join(work_dir, "shots.json"),
        os.path.join(work_dir, "audio_analysis.json"),
        os.path.join(work_dir, "transcript.json"),
        os.path.join(work_dir, "frames.json"),
        os.path.join(work_dir, "prompts.json"),
        video,
    ]
    inputs_exist = [p for p in inputs if os.path.exists(p)]
    if (not force and os.path.exists(asset_json)
            and inputs_exist
            and os.path.getmtime(asset_json) > max(os.path.getmtime(p) for p in inputs_exist)):
        print(f"[6/6] cached asset: {asset_json}")
        return asset_json
    cmd = [sys.executable, str(HERE / "scripts" / "export_asset.py"),
           "--work-dir", work_dir,
           "--video", video,
           "--stems-source-dir", stems_source_dir,
           "--output", asset_json]
    if force:
        cmd += ["--force"]
    run_step(cmd, "[6/6] ShotTimelineAsset export")
    return asset_json
```

Note: `step_export` takes a `skip` parameter (mirror `step_detect:86-88`, `step_separate:104-106`, `step_transcribe:123-125`) — `step_timeline` is the only step that doesn't take `skip`, so use the other three as the skip-handling template.

#### --skip-export flag (argparse)

**Source:** `run_pipeline.py:179-180`

```python
ap.add_argument("--skip-transcribe", action="store_true",
                help="跳过 Whisper 转录")
```

**Apply to run_pipeline.py main():** Insert after `--skip-transcribe`:

```python
ap.add_argument("--skip-export", action="store_true",
                help="跳过 ShotTimelineAsset 导出（asset.json + canonical symlinks）")
```

#### --force cache clear (add asset.json)

**Source:** `run_pipeline.py:218-222`

```python
if args.force:
    for p in (shots_json, frames_json, audio_json, transcript, out_html):
        if os.path.exists(p):
            os.unlink(p)
    print(f"[force] cleared cache under {work_dir}")
```

**Apply:** Add `asset_json` to the tuple:

```python
if args.force:
    for p in (shots_json, frames_json, audio_json, transcript, out_html, asset_json):
        if os.path.exists(p):
            os.unlink(p)
    print(f"[force] cleared cache under {work_dir}")
```

Also define `asset_json = os.path.join(work_dir, "asset.json")` alongside the other path constants at `run_pipeline.py:210-214`.

#### Wire step_export into main() + bump stage prefixes

**Source:** `run_pipeline.py:242-253` (where step_timeline is called)

```python
# 5. 时间轴 HTML
stem_basename = args.stem_basename or stem
video_src = args.video_src or os.path.basename(video)
html = step_timeline(video, work_dir, shots, audio, tr, frames_json,
                     stems_dir, out_html, video_src, stem_basename)

print(f"\n[done] timeline: {html}")
```

**Apply:** Add step 6 before the `[done]` line:

```python
# 6. ShotTimelineAsset 导出
asset_json_path = os.path.join(work_dir, "asset.json")
step_export(work_dir, video, stems_dir, asset_json_path,
            args.skip_export, args.force)
```

**Bracketed stage prefix bump (mandatory per RESEARCH Pitfall 3):**

Find/replace all `[N/5]` → `[N/6]` literals. Lines to change (verified via grep):
- Line 63: `[1/5]` → `[1/6]` (ensure_h264, "codec=...no transcode needed")
- Line 67: `[1/5]` → `[1/6]` (ensure_h264, "cached H264")
- Line 69: `[1/5]` → `[1/6]` (ensure_h264, "transcoding AV1 → H264")
- Line 87: `[2/5]` → `[2/6]` (step_detect, skip message)
- Line 90: `[2/5]` → `[2/6]` (step_detect, cached)
- Line 97: `[2/5]` → `[2/6]` (step_detect, run_step label)
- Line 105: `[3/5]` → `[3/6]` (step_separate, skip)
- Line 108: `[3/5]` → `[3/6]` (step_separate, cached)
- Line 116: `[3/5]` → `[3/6]` (step_separate, run_step label)
- Line 124: `[4/5]` → `[4/6]` (step_transcribe, skip)
- Line 127: `[4/5]` → `[4/6]` (step_transcribe, cached)
- Line 135: `[4/5]` → `[4/6]` (step_transcribe, run_step label)
- Line 147: `[5/5]` → `[5/6]` (step_timeline, cached)
- Line 165: `[5/5]` → `[5/6]` (step_timeline, run_step label)

`step_export` uses `[6/6]` consistently (skip + cached + run_step label).

---

### `scripts/serve.py` `_Partial.close()` fix (server, request-response)

**Analog:** self-referential — `_Partial` class definition at lines 85-96.

#### Current broken _Partial (success-path FD-leak root cause)

**Source:** `scripts/serve.py:80-96`

```python
        if start > 0:
            f.seek(start)
        remaining = end - start + 1
        chunk_size = 64 * 1024

        class _Partial:
            def read(self, _n=None):
                nonlocal remaining
                if remaining <= 0:
                    return b""
                n = min(chunk_size, remaining)
                data = f.read(n)
                remaining -= len(data)
                return data

        # 返回一个能 read 的对象，SimpleHTTPRequestHandler 用 wfile.copyfile
        return _Partial() if partial else f
```

**Root cause (verified live per RESEARCH Pitfall 2):** `SimpleHTTPRequestHandler.do_GET` / `do_HEAD` (at `/usr/lib/python3.12/http/server.py:681`) does `finally: f.close()` on whatever `send_head` returns. `_Partial` defines only `read()`, so `f.close()` raises `AttributeError: '_Partial' object has no attribute 'close'`, the exception propagates, and the **underlying file object captured in the closure is never closed**. Every Range request leaks one FD.

#### Minimal fix (one-method addition)

**Apply to serve.py:** Add a `close()` method to `_Partial`. Refactor `f` from a closure variable to an instance attribute so `close()` can reach it. Keep `read()` semantics identical (same chunking, same `remaining` countdown):

```python
        class _Partial:
            def __init__(self, f, start, end, chunk_size=64 * 1024):
                self._f = f
                self._remaining = end - start + 1
                self._chunk_size = chunk_size
                if start > 0:
                    f.seek(start)
            def read(self, _n=None):
                if self._remaining <= 0:
                    return b""
                n = min(self._chunk_size, self._remaining)
                data = self._f.read(n)
                self._remaining -= len(data)
                return data
            def close(self):
                self._f.close()

        return _Partial(f, start, end) if partial else f
```

This removes the `if start > 0: f.seek(start)` + `remaining` + `chunk_size` setup that currently lives at lines 80-83 (moved into `__init__`).

#### Defensive secondary fix (optional belt-and-braces)

Wrap the body after `f = open(path, "rb")` (line 36) in `try:/except: f.close(); raise` so any unexpected exception between `open()` and the `return _Partial(...)` also releases the FD. Primary fix above is sufficient for the verified AttributeError; this is optional hardening per RESEARCH Pitfall 2 "Secondary fix".

---

## Shared Patterns

### Subprocess-by-path (orchestrator → child script)

**Source:** `run_pipeline.py:92-97, 110-116, 129-135, 149-165`
**Apply to:** `run_pipeline.py:step_export` (calling `scripts/export_asset.py`) AND `scripts/check_range.py` (calling `scripts/serve.py`)

```python
cmd = [sys.executable, str(HERE / "scripts" / "export_asset.py"), ...args]
subprocess.run(cmd, check=True)  # or Popen for long-running server
```

Convention: never `import` a stage script as a module. Always shell out via `[sys.executable, <abspath>, ...]`. `HERE`/`REPO` is computed once at module top via `Path(__file__).parent.resolve()` (or `.parent.parent` for scripts/).

### JSON output convention (ensure_ascii=False, indent=2)

**Source:** `audio/separate_stems.py:190`, `audio/transcribe.py:161`, `html/gen_audio_html.py:362`
**Apply to:** `scripts/export_asset.py` (asset.json write)

```python
with open(path, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2, ensure_ascii=False)
```

Per CLAUDE.md: `ensure_ascii=False` is mandatory whenever the content may contain Chinese (all `output/<video-stem>/asset.json` will, because `source.video_filename` is Chinese for this project's episodes). `indent=2` universal.

### Hard-failure sys.exit pattern

**Source:** `run_pipeline.py:203` (`sys.exit(f"input video not found: {video}")`)
**Apply to:** `scripts/export_asset.py` (prompts.json missing guard) + `scripts/check_range.py` (server failed to start)

Short Chinese message, actionable, single line. No exception classes (CLAUDE.md: "No custom exception classes").

### Bracketed-tag logging

**Source:** CLAUDE.md "Bracketed stage prefix" + `run_pipeline.py:[1/5]..[5/5]` + `spec/validate.py:[validate] ...`
**Apply to:** All NEW and MODIFIED files

- `run_pipeline.py`: `[N/6]` for all 6 steps (bump from `[N/5]`)
- `export_asset.py`: `[export-asset] ...`
- `check_range.py`: `[check-range] ...`
- `serve.py`: existing `[serve] ...` prefix unchanged

### Module docstring (Chinese, multi-line)

**Source:** `html/gen_timeline_html.py:1-17`, `run_pipeline.py:1-30`, `audio/separate_stems.py:1-29`
**Apply to:** Both NEW files (`export_asset.py`, `check_range.py`)

```python
#!/usr/bin/env python3
"""<一句中文目的描述>。

<可选：背景/动机>

输出/行为：
  * ...

用法：
  python3 scripts/<name>.py --flag ...
"""
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `scripts/check_range.py` Range-request HTTP inspection | test | request-response (HTTP) | No existing Python script in this repo issues HTTP requests with custom headers and inspects response status/headers. `scripts/serve.py` is the server side only. RESEARCH §Code Examples provides the verified `urllib.request.Request(url, headers={"Range": "bytes=0-1023"})` pattern directly. Planner should lift that example wholesale. |
| `scripts/export_asset.py` idempotent symlink creation (`ensure_symlink`) | utility | file-I/O | No existing code in this repo creates symlinks. RESEARCH §Pattern 2 provides the verified `ensure_symlink` helper (with the `os.path.islink` / `os.path.exists` / `FileExistsError` clobber guard). Planner should lift that example wholesale. |
| `scripts/export_asset.py` git-SHA sourcing (`_git_sha`) | utility | subprocess | No existing code in this repo calls `git` as a subprocess. RESEARCH §Code Examples provides the verified `_git_sha()` helper with `"dev"` fallback. Planner should lift that example wholesale. |

---

## Metadata

**Analog search scope:**
- `/data/workspace/kais-shot-timeline/run_pipeline.py` (full read, 258 lines)
- `/data/workspace/kais-shot-timeline/scripts/serve.py` (full read, 117 lines)
- `/data/workspace/kais-shot-timeline/spec/validate.py` (full read, 185 lines)
- `/data/workspace/kais-shot-timeline/html/gen_timeline_html.py` (targeted reads: 1-25 header, 945-1083 main+frame-extract)
- `/data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json` (full read, 128 lines)
- `/data/workspace/kais-shot-timeline/spec/fixtures/minimal/asset.json` (full read, 28 lines)
- Targeted grep for `json.dump` / `ensure_ascii` across `audio/`, `html/` (confirmed canonical convention)

**Files scanned:** 7 (4 analogs + 3 spec/fixture references)
**Pattern extraction date:** 2026-07-20
