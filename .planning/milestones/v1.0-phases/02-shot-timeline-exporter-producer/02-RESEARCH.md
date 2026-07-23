# Phase 2: shot-timeline Exporter (Producer) - Research

**Researched:** 2026-07-20
**Domain:** Python CLI pipeline / additive export layer / manifest authoring / HTTP Range serving
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 导出触发与调用模型 (EXPORT-01, SC-1)
- 导出逻辑放在**新增 `step_export`（step 6）**里，shell out 到新脚本 `export_asset.py`（沿用现有「orchestrator 经 `[sys.executable, 脚本路径]` 调子进程」模式，不跨 stage import）
- **默认 always-on** —— 跑完 `run_pipeline.py` 自动产出 ShotTimelineAsset；新增 `--skip-export` flag
- **缓存策略**：cache on `asset.json` 存在 + mtime-vs-inputs（mirror `step_timeline` 的 `os.path.getmtime` 模式）；`--force` 一并清掉 `asset.json`

#### Canonical 媒体策略 (EXPORT-02, SC-1)
- **Symlink（符号链接）** 产出 canonical 媒体，in-place 在 `output/<video-stem>/` 根：
  - `stems/vocals.wav` → `stems/htdemucs/<stem>/vocals.wav`
  - `stems/drums.wav` → `stems/htdemucs/<stem>/drums.wav`
  - `stems/other.wav` → `stems/htdemucs/<stem>/other.wav`（bass 不导出）
  - `video.mp4` → `<original-name>.mp4`（**非** `h264.mp4`，后者 `-an` 去掉了音轨）
- **零磁盘开销 + 不破坏 `timeline.html`** 现有引用 —— 符号链接让新旧引用共存，additive only

#### prompts.json 间隙 + 自校验 (EXPORT-01, SC-1)
- **Exporter 要求 prompts.json 存在** —— `asset.schema.json` 的 `data` 把 5 个 JSON 全部列为 `required`；若缺失，exporter **fails loud**（带可操作错误信息）
- **写完 `asset.json` 后跑 schema 自校验** —— invalid 则导出失败

#### serve.py 加固范围 (EXPORT-03, SC-3)
- **只修 FD-leak**（真实正确性 bug：错误路径下 `f.close()` 未保证）
- **新增 tiny Range-206 自检**：assert 206 + `Content-Range` + `Accept-Ranges`
- **defer** `0.0.0.0` unauth / bind-address / auth 加固 —— 单机离线 dev 工具，属 scope creep

### Claude's Discretion
- `export_asset.py` 的精确字段填充逻辑（asset.json 各字段从 ffprobe/已有 JSON 取值的具体实现）
- `generator.version` 取值来源（git SHA / hardcode / `__version__`）
- Range-206 自检脚本的落地形式（独立 `scripts/check_range.py` 还是 export_asset 的 post-step 子命令）

### Deferred Ideas (OUT OF SCOPE)
- prompts.json 生成步骤的 pipeline 化（接入 run_pipeline）—— 仍由独立步骤产出；本 phase 要求其存在但不生成
- serve.py 的 bind-address / auth / HTTPS 加固
- Windows 下 symlink 兼容（需管理员权限）—— Linux-first
- asset 目录打成 zip/tar 分发 —— v1.0 只定义目录形态
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXPORT-01 | 实现 shot-timeline 导出器，把 `run_pipeline.py` 产出的 `output/<stem>/` 打包成符合 SPEC 的 ShotTimelineAsset 产物 | `## Standard Stack` (stdlib only); `## Architecture Patterns` (subprocess-by-path + symlink manifest writer); `## Code Examples` (asset.json field sourcing); `## Don't Hand-Roll` (inline jsonschema reuse) |
| EXPORT-02 | 导出产物带版本号、自描述 manifest，且不改变现有检测/转录/分离算法（仅在其输出之上加导出层） | `## Standard Stack` (schema-strict manifest); `## Architecture Patterns` (additive layering — zero algorithm touches); `## Common Pitfalls` (existing `<original-name>.mp4` symlink already chains to h264.mp4 — exporter must bypass) |
| EXPORT-03 | 导出端通过 Range-aware server（`scripts/serve.py`）对外提供媒体文件，满足消费端 stem/视频 seek 依赖 | `## Common Pitfalls` (FD-leak root cause: `_Partial.close()` missing); `## Code Examples` (Range-206 self-check); `## Validation Architecture` (Range 206 + Content-Range + Accept-Ranges invariant) |
</phase_requirements>

## Summary

Phase 2 is a **thin additive layer** on top of the existing 5-step pipeline. It writes one new JSON (`asset.json`) and creates 4 symlinks (1 video + 3 stems). It does NOT touch any algorithm, does NOT regenerate existing JSON, does NOT modify `timeline.html`'s generator. The complexity is in **(a) sourcing manifest fields from the right places**, **(b) picking the correct symlink target for `video.mp4` (the original video WITH audio — NOT the existing `<original-name>.mp4` symlink in work_dir, which itself chains to the audio-stripped `h264.mp4`)**, and **(c) fixing the actual FD-leak bug in serve.py which is NOT what CONTEXT.md's prose described — the leak is the `_Partial` class lacking a `close()` method, not missing `f.close()` calls on error paths**.

All dependencies are already satisfied: Python 3.12.3, ffprobe 6.1.1, jsonschema 4.26.0, curl 8.5.0, and the 5 data JSONs in the existing `output/` already pass `spec/validate.py --strict-smoke` 5/5 (verified live this session). No new pip packages are needed — the exporter is pure stdlib + `jsonschema` (already installed). This is a LOW-risk phase mechanically; the risk is concentrated in correctly understanding the existing work_dir layout (which has more files than CONTEXT.md enumerates) and the serve.py control flow (which has a subtler bug than CONTEXT.md describes).

**Primary recommendation:** Implement `scripts/export_asset.py` as a standalone argparse CLI invoked via subprocess from a new `step_export` in `run_pipeline.py`. Inside the exporter, perform **inline jsonschema validation** of the written `asset.json` against `spec/schemas/asset.schema.json` (do NOT rely on `spec/validate.py` subprocess — its smoke pass only validates 5 data shapes, not `asset.json`). Fix serve.py by giving `_Partial` a `close()` method that closes the underlying file object. Ship Range-206 self-check as a standalone `scripts/check_range.py` using stdlib `urllib` + `subprocess` (avoid curl dependency — though curl is available, urllib keeps the check portable).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Manifest authoring (`asset.json`) | Pipeline / CLI (Python) | — | Producer-side metadata; pure stdlib JSON serialization matching schema-required fields |
| Canonical media symlink creation | Pipeline / CLI (filesystem) | — | In-place symlinks under `output/<video-stem>/`; Linux `os.symlink`; zero disk copy |
| Self-validation of written manifest | Pipeline / CLI (Python) | — | Inline `jsonschema.Draft202012Validator` against `asset.schema.json`; fail export on invalid |
| Subprocess orchestration | `run_pipeline.py` (orchestrator) | `export_asset.py` (child) | Mirror existing `step_*` pattern: `[sys.executable, str(HERE / "scripts" / "export_asset.py"), ...]` |
| HTTP Range serving | Static dev server (`scripts/serve.py`) | — | Existing server; Phase 2 only fixes FD-leak bug. Media files (video+stems) are served as-is via symlinks |
| Range-206 invariant verification | Standalone check script (`scripts/check_range.py`) | — | Boot serve.py on random port → urllib request → assert 206/Content-Range/Accept-Ranges → teardown |
| prompts.json presence guard | Pipeline / CLI (Python) | — | `asset.schema.json` lists all 5 data JSONs as `required`; exporter fails loud if `prompts.json` absent |
| Caching / idempotency | `run_pipeline.py:step_export` | — | `os.path.getmtime(asset.json) > max(input mtimes)` pattern mirroring `step_timeline` |
| Field value sourcing (video_filename, duration_sec) | Existing pipeline outputs | ffprobe (fallback) | Read from `transcript.json#source` + `audio_analysis.json#duration` (already proven correct); fall back to `probe_duration(video)` if missing |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `argparse` | 3.12.3 | `export_asset.py` CLI flags (`--work-dir`, `--video`, `--stems-source-dir`, `--force`) | Every existing script uses argparse with Chinese `help=`; consistency required `[VERIFIED: codebase grep]` |
| Python stdlib `json` | 3.12.3 | Write `asset.json` with `ensure_ascii=False, indent=2` | Project-wide convention; matches all `json.dump` calls `[VERIFIED: codebase grep]` |
| Python stdlib `os` / `pathlib` | 3.12.3 | `os.symlink`, `os.path.exists`, `os.path.getmtime`, `Path.stem` | Symlink creation + cache logic `[VERIFIED: codebase]` |
| Python stdlib `subprocess` | 3.12.3 | `run_pipeline.py` shells out to `export_asset.py`; Range check shells out to `serve.py` | Existing subprocess-by-path pattern `[VERIFIED: codebase]` |
| Python stdlib `datetime` | 3.12.3 | `generator.generated_at` ISO-8601 UTC timestamp | `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` `[CITED: asset.schema.json#properties.generator.properties.generated_at]` |
| Python stdlib `urllib.request` | 3.12.3 | Range-206 self-check (avoid curl dependency) | stdlib-only, portable; use `Request(url, headers={"Range": "bytes=0-1023"})` `[CITED: docs.python.org/3/library/urllib.request.html]` |
| Python stdlib `http.server` / `socketserver` | 3.12.3 | serve.py base (already used); Range check imports `ThreadingHTTPServer` | Existing `scripts/serve.py:99-107` pattern `[VERIFIED: codebase]` |
| `jsonschema.Draft202012Validator` | 4.26.0 | Inline validation of written `asset.json` against schema | Already used by `spec/validate.py`; same backend `[VERIFIED: spec/validate.py:26, python3 -c "import jsonschema; print(jsonschema.__version__)" → 4.26.0]` |
| ffprobe | 6.1.1-3ubuntu5 | `source.duration_sec` field (fallback if JSONs lack duration) | Already invoked by `run_pipeline.py:probe_duration` `[VERIFIED: ffprobe -version]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `tempfile` | 3.12.3 | Not needed by exporter; Range-check uses ephemeral test asset dir | Skip unless check_range.py creates test fixtures |
| Python stdlib `sys` | 3.12.3 | `sys.exit("...")` on hard failures (mirror existing error pattern) | Match `run_pipeline.py:203` style `[VERIFIED: codebase]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline `jsonschema.validate` in exporter | Subprocess to `spec/validate.py` | **Don't subprocess.** validate.py's smoke pass only covers the 5 data shapes, NOT `asset.json` (its SMOKE_SHAPES excludes asset). Inline validation is more direct and actually verifies the manifest `[VERIFIED: spec/validate.py:49 SMOKE_SHAPES]` |
| `urllib.request` for Range check | `curl` CLI | curl 8.5.0 is installed but urllib is stdlib and portable; CONTEXT.md said "curl-based" but discretion allows either. **Recommend urllib** — keeps the check self-contained `[VERIFIED: curl --version]` |
| `os.symlink` for canonical media | File copy (`shutil.copy`) | Copy wastes 4× ~34 MB stems + ~140 MB video = ~270 MB/episode. Symlink is zero-disk. CONTEXT locked symlinks `[VERIFIED: ls -la output/《小江湖》第03话…/ shows ~34 MB × 4 stems]` |
| Hardcode `generator.version = "1"` | `git rev-parse --short HEAD` | CONTEXT discretion. **Recommend git SHA** — gives provenance traceability; schema accepts any string. Verified `git rev-parse --short HEAD → 3647ce9` works in this repo `[VERIFIED: bash]` |

**Installation:**
```bash
# No install needed — all dependencies already present
python3 -c "import jsonschema; print(jsonschema.__version__)"  # 4.26.0
```

**Version verification** (run before planning):
```bash
python3 --version          # Python 3.12.3 ✓
ffprobe -version           # 6.1.1-3ubuntu5 ✓
python3 -c "import jsonschema; print(jsonschema.__version__)"  # 4.26.0 ✓
curl --version | head -1   # curl 8.5.0 ✓ (optional, for ad-hoc checks)
git rev-parse --short HEAD # 3647ce9 (for generator.version source)
```

## Package Legitimacy Audit

> This phase installs **zero** external packages. All imports are Python 3.12.3 stdlib + the already-installed `jsonschema` 4.26.0 (used by `spec/validate.py` since Phase 1). Slopcheck gate skipped — no `pip install` commands will be emitted by any task in this phase.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none) | — | — | — | — | — | No new packages — phase is stdlib-only |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
                            ┌─────────────────────────────────────┐
                            │       run_pipeline.py (orchestrator) │
                            │                                     │
  --video <path> ─────────▶ │  1. ensure_h264 (AV1 transcode)     │
  --output-dir <dir>        │  2. step_detect → shots.json        │
  --skip-export (NEW)       │  3. step_separate → audio_analysis  │
  --force (now clears       │  4. step_transcribe → transcript    │
       asset.json too)      │  5. step_timeline → timeline.html   │
                            │  6. step_export (NEW) ─────┐         │
                            └────────────────────────────┼────────┘
                                                         │
                                          subprocess.run([sys.executable,
                                              "scripts/export_asset.py",
                                              "--work-dir", ...,
                                              "--video", <original-path>,
                                              "--stems-source-dir", <htdemucs/<stem>>,
                                              "--force"?])

                                                         ▼
              ┌──────────────────────────────────────────────────────────┐
              │              scripts/export_asset.py (NEW)               │
              │                                                          │
              │  1. Read inputs:                                         │
              │     - shots.json, audio_analysis.json,                   │
              │       transcript.json, frames.json, prompts.json         │
              │     - <video> (original abs path)                        │
              │     - <stems-source-dir> (htdemucs/<stem>)               │
              │  2. Guard: fail loud if any of 5 JSONs missing           │
              │  3. Create canonical symlinks (additive, idempotent):    │
              │     work_dir/video.mp4   → <video>         (NEW)         │
              │     work_dir/stems/vocals.wav → <src>/vocals.wav         │
              │     work_dir/stems/drums.wav → <src>/drums.wav           │
              │     work_dir/stems/other.wav → <src>/other.wav           │
              │     (mkdir stems/ first; os.symlink; clobber if exists)  │
              │  4. Build asset.json dict:                               │
              │     - schema_version: "1" (hardcoded)                    │
              │     - asset_type: "shottimeline" (const)                 │
              │     - source.video_filename: basename(video)             │
              │       (or transcript.json#source as cross-check)         │
              │     - source.duration_sec: transcript.duration           │
              │       (fallback probe_duration(video))                   │
              │     - generator.tool: "kais-shot-timeline"               │
              │     - generator.version: git SHA (or "dev")              │
              │     - generator.generated_at: now UTC ISO-8601           │
              │     - data.{shots,audio_analysis,transcript,frames,      │
              │       prompts}: "<name>.json" relative paths             │
              │     - media.video: "video.mp4"                           │
              │     - media.stems.{vocals,drums,other}: "stems/X.wav"    │
              │  5. Write asset.json (ensure_ascii=False, indent=2)      │
              │  6. Inline validate against spec/schemas/asset.schema.json│
              │     using Draft202012Validator; fail export on invalid   │
              │     (also: assert symlinks resolve to real files)        │
              │  7. print "[6/6] asset: <path>"                          │
              └──────────────────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
                    ┌────────────────────────────────────────────┐
                    │   output/<video-stem>/  (asset root)       │
                    │   ├── asset.json          (NEW)            │
                    │   ├── shots.json          (existing)       │
                    │   ├── audio_analysis.json (existing)       │
                    │   ├── transcript.json     (existing)       │
                    │   ├── frames.json         (existing)       │
                    │   ├── prompts.json        (existing, ext)  │
                    │   ├── video.mp4 → <orig>  (NEW symlink)    │
                    │   ├── stems/              (NEW dir)        │
                    │   │   ├── vocals.wav → …  (NEW symlink)    │
                    │   │   ├── drums.wav → …   (NEW symlink)    │
                    │   │   └── other.wav → …   (NEW symlink)    │
                    │   ├── stems/htdemucs/<stem>/ (existing)    │
                    │   ├── h264.mp4             (existing)       │
                    │   ├── <orig-name>.mp4 → h264 (existing)     │
                    │   └── timeline.html       (existing)       │
                    └────────────────────────────────────────────┘
                                 │
                                 │ consumer mounts via:
                                 │   python3 scripts/serve.py <asset-root> 8765
                                 ▼
                    ┌────────────────────────────────────────────┐
                    │     scripts/serve.py  (FD-leak FIXED)       │
                    │                                            │
                    │   HTTP GET /video.mp4                      │
                    │     Range: bytes=0-1023                    │
                    │     → 206 Partial Content                  │
                    │       Content-Range: bytes 0-1023/<total>  │
                    │       Accept-Ranges: bytes                 │
                    │   (follows symlinks via translate_path +   │
                    │    os.fstat — verified this session)       │
                    └────────────────────────────────────────────┘
                                 │
                                 │ scripts/check_range.py (NEW)
                                 │   boots serve.py on random port,
                                 │   urllib GET with Range header,
                                 │   asserts 206 + Content-Range + Accept-Ranges,
                                 │   tears down server (daemon_threads=True)
                                 ▼
                            PASS / FAIL exit code
```

### Recommended Project Structure

```text
kais-shot-timeline/
├── run_pipeline.py            # EDIT: add step_export + --skip-export flag; --force clears asset.json
├── scripts/
│   ├── export_asset.py        # NEW: manifest writer + canonical symlinks + inline jsonschema
│   ├── check_range.py         # NEW: standalone Range-206 self-check (urllib + subprocess)
│   └── serve.py               # EDIT: FD-leak fix (_Partial.close() method + try/except wrap)
├── spec/
│   ├── schemas/asset.schema.json  # UNCHANGED — Phase 1 locked
│   └── validate.py                # UNCHANGED — smoke mode doesn't cover asset.json
└── output/<video-stem>/
    ├── asset.json              # NEW — produced by step_export
    └── stems/{vocals,drums,other}.wav  # NEW symlinks (htdemucs/<stem>/ unchanged)
```

### Pattern 1: Subprocess-by-path (mirror existing step_*)

**What:** Orchestrator invokes child script via `[sys.executable, str(HERE / "scripts" / "export_asset.py"), ...args]`; child is a self-contained argparse CLI with `main()` + `if __name__ == "__main__"`. Never cross-stage imports.

**When to use:** For every new pipeline step. This is the project's only invocation pattern.

**Example:**
```python
# Source: run_pipeline.py:139-166 (step_timeline) — pattern to mirror
def step_export(work_dir: str, video: str, stems_source_dir: str,
                asset_json: str, skip: bool, force: bool) -> str:
    if skip:
        print("[6/6] --skip-export: skipping asset export")
        return asset_json if os.path.exists(asset_json) else None

    # mtime cache (mirror step_timeline:143-148)
    inputs = [
        os.path.join(work_dir, "shots.json"),
        os.path.join(work_dir, "audio_analysis.json"),
        os.path.join(work_dir, "transcript.json"),
        os.path.join(work_dir, "frames.json"),
        os.path.join(work_dir, "prompts.json"),
        video,  # original video path
    ]
    inputs_exist = [p for p in inputs if os.path.exists(p)]
    if (not force and os.path.exists(asset_json)
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

### Pattern 2: Idempotent symlink creation (clobber if exists)

**What:** Before creating each canonical symlink, check if it already exists. If it exists and points to the wrong target (or isn't a symlink), unlink + recreate. This makes `step_export` re-runnable.

**When to use:** Always — exporter must be idempotent so `--force` and cache rebuilds don't fail on existing symlinks.

**Example:**
```python
# Source: applied pattern — no codebase precedent (this is new code)
import os

def ensure_symlink(link_path: str, target: str) -> None:
    """Create or replace a symlink at link_path → target. Idempotent.

    If link_path exists as a symlink (any target), unlink + recreate.
    If link_path exists as a regular file/dir, raise (don't silently clobber real files).
    """
    if os.path.islink(link_path):
        os.unlink(link_path)
    elif os.path.exists(link_path):
        raise FileExistsError(
            f"refusing to overwrite non-symlink: {link_path} (expected symlink → {target})")
    os.symlink(target, link_path)
```

### Pattern 3: Inline schema validation (do NOT shell out to spec/validate.py)

**What:** Load `spec/schemas/asset.schema.json` directly inside `export_asset.py` using the same `Draft202012Validator` that `spec/validate.py` uses. Validate the freshly-written `asset.json` dict in-memory before declaring success.

**When to use:** Always after writing `asset.json`. CONTEXT.md says "runs spec/validate.py post-write" but `spec/validate.py`'s smoke pass explicitly excludes `asset.json` (`SMOKE_SHAPES = ["shots", "audio_analysis", "transcript", "frames", "prompts"]` — line 49) and only validates the minimal fixture for the asset shape. Subprocess to validate.py would NOT catch an invalid manifest written to `output/`.

**Example:**
```python
# Source: spec/validate.py:52-57 (load_validator) — pattern to mirror inline
from jsonschema import Draft202012Validator

def validate_asset_json(asset_dict: dict, asset_root: str) -> None:
    """Validate the just-written asset dict against asset.schema.json.

    Raises AssertionError with formatted errors on failure.
    """
    import json
    # spec/ lives one level above the work_dir's parent — find via __file__
    here = Path(__file__).parent.parent  # scripts/ → repo root
    schema_path = here / "spec" / "schemas" / "asset.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(asset_dict), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        raise AssertionError(
            f"asset.json failed schema validation ({len(errors)} error(s)):\n" + "\n".join(lines))
```

### Anti-Patterns to Avoid

- **DON'T subprocess to `spec/validate.py` for asset.json validation** — its smoke pass only validates the 5 data JSONs, not `asset.json`. The asset shape is only checked on `spec/fixtures/minimal/asset.json`. Inline validation is required.
- **DON'T symlink `video.mp4` → `<original-name>.mp4` (the existing symlink in work_dir)** — that symlink itself chains to `h264.mp4` (audio stripped via `-an`). The exporter MUST link directly to the original video file (absolute path passed via `--video`).
- **DON'T use `shutil.copy` for canonical media** — 4× stem WAV + 1× video = ~270 MB/episode wasted. CONTEXT locked symlinks.
- **DON'T skip the `_Partial.close()` fix in serve.py** — this is a real bug verified live (AttributeError printed on every Range request). It's not theoretical.
- **DON'T strip bass.wav from `stems/htdemucs/<stem>/`** — bass is still in `audio_analysis.json#shots[].energies.bass` (data layer keeps 4-stem). Only the `stems/` canonical export dir excludes bass. The pre-canonical Demucs output stays untouched.
- **DON'T bump the bracketed stage prefix count lazily** — existing code says `[1/5]..[5/5]`. Phase 2 introduces step 6, so ALL existing `[N/5]` prefixes in `run_pipeline.py` must change to `[N/6]`. (Lines 63, 67, 69, 87, 91, 105, 108, 124, 126, 143, 147, 165.) Missing this creates confusing `[5/6] timeline` then `[5/5] export` output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation of `asset.json` | Custom field-by-field `if`/`raise` checks | `jsonschema.Draft202012Validator` (already installed, used by spec/validate.py) | Schema has 6 pattern regexes + nested object validations; hand-rolling will miss edge cases. Schema is the authority `[CITED: spec/schemas/asset.schema.json]` |
| Field value sourcing for `source.video_filename` | Manual `os.path.basename` + heuristic | Read `transcript.json#source` (already basename-confirmed) OR `os.path.basename(args.video)` | transcript.py:161 already writes this field; cross-check both for integrity `[VERIFIED: audio/transcribe.py + inspected transcript.json]` |
| ISO-8601 timestamp | Manual string concatenation | `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` | Schema requires ISO-8601 string; `datetime.isoformat()` omits the `Z` suffix. SPEC.md example shows `2026-07-20T00:00:00Z` `[CITED: spec/SPEC.md §3, asset.schema.json generated_at description]` |
| Range request semantics | Custom socket loop | `urllib.request.Request(url, headers={"Range": "bytes=0-1023"})` | stdlib handles HTTP parsing; need only inspect `status` + headers `[CITED: docs.python.org/3/library/urllib.request.html]` |
| Subprocess + argparse pattern | New "pipeline framework" | Mirror `step_timeline` exactly | Project has no framework, intentionally. Adding one violates anti-patterns in CLAUDE.md `[VERIFIED: CLAUDE.md "God-script" anti-pattern]` |
| Test framework | `pytest`/`unittest` discovery | Standalone `scripts/check_range.py` with `sys.exit(0/1)` | Repo has zero test files; introducing pytest is scope creep. A self-contained script matches project style `[VERIFIED: find . -name "test_*.py" -o -name "*_test.py" → none]` |

**Key insight:** This phase adds a metadata + I/O layer. The "cleverness" is in sourcing fields from the right existing JSONs and getting the symlink targets right. There is no algorithmic novelty — and any attempt to add framework-y abstraction (asset builder classes, manifest dataclasses, validation pipelines) violates the project's flat-function style.

## Runtime State Inventory

> Phase 2 is **additive** (new files + new symlinks), not a rename/refactor/migration. The Runtime State Inventory categories below are answered for completeness because the phase creates filesystem state that persists across runs.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data (DBs / datastores) | None — no databases in this project. All state is filesystem JSON. `[VERIFIED: grep -r "sqlite\|chromadb\|redis\|mem0" --include="*.py" → none]` | None |
| Live service config (external UIs/services) | None — no external services configured from outside git. `scripts/serve.py` reads config only from CLI args. | None |
| OS-registered state (Task Scheduler / launchd / systemd / pm2) | None — no OS-level registrations. `[VERIFIED: no systemd unit, no crontab entries reference this repo]` | None |
| Secrets / env vars | None — CLAUDE.md: "No .env file. No environment variables are read by any script." | None |
| Build artifacts / installed packages | No `pyproject.toml`/`setup.py`/`egg-info` — scripts are invoked by absolute path, not installed. New `scripts/export_asset.py` is a standalone file, no install step. | None |

**The canonical question — "After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?"** — has answer: **none for this phase**. Phase 2 only ADDS files; it does not rename or delete. The `step_export` cache (`asset.json`) is rebuilt by `--force`. Existing `timeline.html` references to old `<basename>_vocals.wav` filenames are unaffected because the new canonical symlinks (`stems/vocals.wav`) have different paths.

**One caveat for the planner:** existing `output/《小江湖》第03话…/` already contains a manual `<original-name>.mp4 → h264.mp4` symlink (created by some pre-existing manual step or older tool version). The exporter must NOT touch this existing symlink — it must only ADD the new `video.mp4` symlink. Idempotent re-runs of `step_export` will only manage the new symlinks.

## Common Pitfalls

### Pitfall 1: Wrong `video.mp4` symlink target (CRITICAL)

**What goes wrong:** Naively following CONTEXT.md's "video.mp4 → `<original-name>.mp4`" verbatim produces a `video.mp4` symlink that resolves to the audio-stripped `h264.mp4`. Consumers hear nothing when playing the video alongside stems.

**Why it happens:** The existing `<original-name>.mp4` symlink in `output/<video-stem>/` (verified live: `《小江湖》第03话….mp4 → h264.mp4`) is itself a symlink chain ending at `h264.mp4`, which was transcoded with `-an` (audio dropped — confirmed via `ffprobe`: original has `aac,audio` stream; `h264.mp4` has only `h264,video`). CONTEXT.md's prose was correct in intent ("not h264.mp4, audio stripped") but ambiguous in target ("<original-name>.mp4" is itself the wrong thing).

**How to avoid:** Symlink `video.mp4` **directly to the original video file's absolute path** (passed via `--video` from `run_pipeline.py`, which holds `os.path.abspath(args.video)` on line 201). Verify the target has an audio stream before creating the symlink (`ffprobe -show_entries stream=codec_type`); fail export if missing.

**Warning signs:** `ffprobe video.mp4` shows no `audio` stream; consumer reports video plays but no sound; `ls -La video.mp4` shows target ending in `h264.mp4`.

`[VERIFIED: ffprobe original → "av1,video\naac,audio"; ffprobe h264.mp4 → "h264,video" only. Existing <original-name>.mp4 → h264.mp4 confirmed via ls -la.]`

### Pitfall 2: serve.py FD-leak root cause is `_Partial.close()`, not "missing f.close() on error paths"

**What goes wrong:** If the planner reads CONTEXT.md's "错误路径下 `f.close()` 未保证" and just adds `f.close()` calls to the 416/NOT_FOUND branches, the actual leak persists.

**Why it happens:** The real bug is in the **success path**, not the error path. `send_head` returns a `_Partial()` object for the 206 case. `SimpleHTTPRequestHandler.do_GET`/`do_HEAD` then does `f.close()` in a `finally` block. But `_Partial` defines only `read()`, not `close()` — so `f.close()` raises `AttributeError: '_Partial' object has no attribute 'close'`, the exception propagates, and the underlying file object captured in `_Partial`'s closure is **never closed**. Each Range request leaks one FD. Verified live: every Range request in this session's test printed this exact AttributeError traceback to stderr.

**How to avoid:** The fix is to add a `close()` method to the `_Partial` class that closes the underlying `f`:

```python
class _Partial:
    def __init__(self, f):
        self._f = f
    def read(self, _n=None):
        # ... existing logic ...
    def close(self):
        self._f.close()
```

(Or refactor to pass `f` as an attr instead of closure variable — but the minimal fix is a one-liner `close` method.)

**Secondary fix (defensive):** Wrap the body of `send_head` after `f = open(...)` in `try:/except: f.close(); raise` so that any unexpected exception (e.g., `os.fstat(...).st_mtime` on line 77 if it ever fails) doesn't leak `f`. Belt-and-braces; the primary fix is `_Partial.close()`.

The 416 branch already has `f.close()` (line 60). The NOT_FOUND branch never opens `f` (the `open()` itself fails into `except OSError`). The 200 branch returns `f` directly, which has a real `.close()`. So CONTEXT's "错误路径下 f.close() 未保证" is **inaccurate** — the 416 path is the only error path with `f` open and it DOES close. The real leak is on the SUCCESS 206 path.

**Warning signs:** `ls /proc/<pid>/fd | wc -l` grows with each Range request; `AttributeError: '_Partial' object has no attribute 'close'` in server stderr; eventually `OSError: [Errno 24] Too many open files` after ~1000 seeks.

`[VERIFIED: live test this session — curl Range request printed the AttributeError traceback to stderr, confirming the leak mechanism. Source: /usr/lib/python3.12/http/server.py:681 `f.close()` in do_GET finally block.]`

### Pitfall 3: Stale `[N/5]` stage prefixes after adding step 6

**What goes wrong:** If `step_export` is added but existing `print("[1/5] ...")` etc. lines aren't updated, the output reads `[5/5] timeline HTML` then `[6/6] export` (or worse, `[5/5] timeline` then `[1/1] export`). Confusing for users tracking progress.

**Why it happens:** The existing 5 stages all hardcode `[N/5]` literals (`run_pipeline.py:63, 67, 69, 87, 91, 105, 108, 124, 126, 143, 147, 165`). No constant centralizes the total.

**How to avoid:** Find/replace all `[N/5]` → `[N/6]` literals in `run_pipeline.py`. Use a new `[6/6]` prefix in `step_export`. Alternatively (cleaner) introduce a `TOTAL_STEPS = 6` constant — but project style is "flat functions, no over-abstraction", so literal find/replace is fine.

**Warning signs:** `grep "\[.\/5\]" run_pipeline.py` returns any hits after the phase lands.

### Pitfall 4: prompts.json absence mode (CONTEXT locked, but easy to get the error message wrong)

**What goes wrong:** Exporter runs after a pipeline invocation that skipped the manual prompts step; exporter silently writes asset.json referencing missing prompts.json; consumer import fails opaquely downstream.

**Why it happens:** `prompts.json` has NO Python producer in this repo (`grep -rn "prompts.json" --include="*.py"` returns only `spec/validate.py:41`; no `gen_prompts*.py` exists despite SPEC.md §5 mentioning `html/gen_prompts_html.py` — that file does NOT exist). prompts.json is produced by an external/manual step (currently: observed present in all 3 episode output dirs, but with no in-repo generator). The exporter is the first pipeline stage that actually requires prompts.json to exist.

**How to avoid:** Add a presence check at the TOP of `export_asset.py:main()` before doing anything else. On missing prompts.json, exit with an actionable Chinese error message per CLAUDE.md error-handling convention:

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

**Warning signs:** asset.json written but consumer crashes on import with "prompts.json not found"; or exporter succeeds but inline validation fails on `data.prompts` schema violation.

`[VERIFIED: find . -name "gen_prompts*.py" → none; grep -rn "prompts.json" --include="*.py" → only spec/validate.py. prompts.json IS present in all 3 output/ subdirs but no Python producer exists in repo.]`

### Pitfall 5: Spec drift — `SPEC.md` claims `html/gen_prompts_html.py` exists, but it doesn't

**What goes wrong:** Planner reads SPEC.md §5 Prompts section ("Producer: `html/gen_prompts_html.py`") and assumes the file exists. It doesn't. Either the planner builds the exporter around that assumption (wrong) or wastes time hunting for the script.

**Why it happens:** SPEC.md was written in Plan 01-02 against what the spec author THOUGHT was the producer. The file is non-existent. The prompts.json is produced by an external/manual step (likely a notebook or one-off script not committed).

**How to avoid:** Phase 2 treats `prompts.json` as an **opaque external input** — required-to-exist, never produced. Phase 2's deferred ideas list explicitly carries "prompts.json 生成步骤的 pipeline 化". Document this drift in RESEARCH.md (done here) so the planner doesn't fall into the trap. **Optional:** suggest a follow-up task to fix SPEC.md §5 producer reference (cosmetic — doesn't affect SC).

`[VERIFIED: ls html/ → only gen_audio_html.py, gen_shots_preview.py, gen_timeline_html.py. find . -name "gen_prompts*.py" → none.]`

### Pitfall 6: Stale symlink targets after re-running with different --video

**What goes wrong:** User runs pipeline twice with different source videos for the same `<video-stem>` work_dir (unlikely but possible if filename collides). Second run's symlinks point to the first run's original video.

**Why it happens:** `ensure_symlink` only unlinks if `os.path.islink` is true. It DOES unlink + recreate. So this is handled by Pattern 2 above. But the planner should explicitly verify the test for "is the existing symlink pointing at THIS run's target" is part of the idempotent check — otherwise unchanged target still triggers unlink+recreate which is fine but wasteful.

**How to avoid:** Compare `os.readlink(link_path) == target` before unlinking — skip recreation if already correct (saves mtime churn, helps cache). Minor optimization, not correctness.

## Code Examples

### Verified asset.json field sourcing

Verified against the live `output/《小江湖》第03话…/` directory:

```python
# Source: live verification this session against output/《小江湖》第03话：…/
import json, os
from datetime import datetime, timezone
from pathlib import Path

def build_asset_dict(work_dir: str, video_path: str) -> dict:
    """Build the asset.json dict from existing pipeline outputs.

    Field sourcing (all verified against live output):
      - schema_version: hardcoded "1" (CONTEXT D-02; matches spec/fixtures/minimal)
      - asset_type: const "shottimeline" (asset.schema.json)
      - source.video_filename: basename(video_path) — cross-check against
        transcript.json#source (they match in well-formed outputs)
      - source.duration_sec: transcript.json#duration (fallback probe_duration)
      - generator.tool: literal "kais-shot-timeline"
      - generator.version: git SHA via subprocess (fallback "dev")
      - generator.generated_at: datetime.now(timezone.utc) ISO-8601 with Z
      - data.*: literal "<name>.json" paths (schema rejects parent traversal)
      - media.video: literal "video.mp4" (schema pattern: ^(?:[^/]+/)*video\.mp4$)
      - media.stems.*: literal "stems/<name>.wav" (schema requires lowercase name)
    """
    # Source fields — read transcript.json for cross-check + duration
    with open(os.path.join(work_dir, "transcript.json"), encoding="utf-8") as f:
        transcript = json.load(f)

    video_filename = os.path.basename(video_path)
    # Integrity cross-check (warn, don't fail, on mismatch)
    if transcript.get("source") and transcript["source"] != video_filename:
        print(f"[warn] transcript.source={transcript['source']!r} != "
              f"video basename={video_filename!r}")

    duration = transcript.get("duration")
    if not duration:
        # Fallback: probe_duration(video_path) — defined in run_pipeline.py:49
        from run_pipeline import probe_duration  # NOT allowed by project pattern
        # Instead: inline the ffprobe call
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path], capture_output=True, text=True)
        try:
            duration = float(r.stdout.strip())
        except (ValueError, AttributeError):
            duration = 0.0

    return {
        "schema_version": "1",
        "asset_type": "shottimeline",
        "source": {
            "video_filename": video_filename,
            "duration_sec": duration,
        },
        "generator": {
            "tool": "kais-shot-timeline",
            "version": _git_sha(),  # "3647ce9" or "dev"
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "data": {
            "shots": "shots.json",
            "audio_analysis": "audio_analysis.json",
            "transcript": "transcript.json",
            "frames": "frames.json",
            "prompts": "prompts.json",
        },
        "media": {
            "video": "video.mp4",
            "stems": {
                "vocals": "stems/vocals.wav",
                "drums": "stems/drums.wav",
                "other": "stems/other.wav",
            },
        },
    }


def _git_sha() -> str:
    """Get short git SHA for generator.version. Fallback 'dev'."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2)
        return r.stdout.strip() or "dev"
    except (subprocess.SubprocessError, OSError):
        return "dev"
```

### Verified mtime-cache inputs (R7)

```python
# Source: mirror run_pipeline.py:143-148 (step_timeline cache logic)
# Verified inputs against output/《小江湖》第03话…/ directory listing
EXPORT_INPUTS = [
    "shots.json",           # produced by step_detect
    "audio_analysis.json",  # produced by step_separate
    "transcript.json",      # produced by step_transcribe
    "frames.json",          # produced by gen_timeline_html:extract_frames_if_needed
    "prompts.json",         # produced externally (no in-repo .py generator)
]
# Plus the original video path (passed via --video) — its mtime matters because
# video.mp4 symlink target depends on it.
# Stems source dir mtime is NOT a cache input — individual .wav files don't change
# once Demucs writes them; if they did, audio_analysis.json would also change.
```

### Verified FD-leak fix for serve.py

```python
# Source: scripts/serve.py:85-96 (current broken _Partial) + python http/server.py:681
# Fix: give _Partial a close() method so do_GET's `finally: f.close()` works.

class _Partial:
    """Wraps f to limit read to `remaining` bytes. MUST have close() because
    SimpleHTTPRequestHandler.do_GET does `finally: f.close()` on whatever
    send_head returns."""
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
```

### Verified Range-206 self-check (scripts/check_range.py)

```python
# Source: standalone script, stdlib only. Boots serve.py, sends Range request,
# asserts 206 + Content-Range + Accept-Ranges, tears down.
# Verified: curl test this session returned HTTP 206 + Content-Range: bytes 0-4/36
#!/usr/bin/env python3
"""Range-206 自检：启动 serve.py → Range 请求 → assert 206/Content-Range/Accept-Ranges。"""
import http.client
import os
import random
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def wait_ready(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def check(asset_root: str) -> int:
    if not os.path.exists(os.path.join(asset_root, "video.mp4")):
        print(f"[check-range] no video.mp4 in {asset_root} — nothing to probe")
        return 1

    port = find_free_port()
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / "serve.py"), asset_root, str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_ready(port):
            print(f"[check-range] FAIL: server did not start on port {port}")
            return 1

        url = f"http://127.0.0.1:{port}/video.mp4"
        req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_range = resp.headers.get("Content-Range")
            accept_ranges = resp.headers.get("Accept-Ranges")
            body = resp.read()

        ok = True
        if status != 206:
            print(f"[check-range] FAIL: expected 206, got {status}")
            ok = False
        if not content_range or not content_range.startswith("bytes 0-1023/"):
            print(f"[check-range] FAIL: bad Content-Range: {content_range!r}")
            ok = False
        if accept_ranges != "bytes":
            print(f"[check-range] FAIL: bad Accept-Ranges: {accept_ranges!r}")
            ok = False
        if len(body) != 1024:
            print(f"[check-range] FAIL: expected 1024-byte body, got {len(body)}")
            ok = False
        if ok:
            print(f"[check-range] OK: 206 + Content-Range={content_range} "
                  f"+ Accept-Ranges=bytes + 1024-byte body")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Range-206 自检")
    ap.add_argument("asset_root", nargs="?",
                    default=str(REPO / "output") + "/<first-dir>",
                    help="asset directory containing video.mp4")
    args = ap.parse_args()
    # Default: auto-pick first output subdir with video.mp4
    if not os.path.isdir(args.asset_root):
        output_root = REPO / "output"
        for child in sorted(output_root.iterdir()) if output_root.is_dir() else []:
            if (child / "video.mp4").exists():
                args.asset_root = str(child)
                break
    sys.exit(check(args.asset_root))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 5-step pipeline (detect/separate/transcribe/timeline) | 6-step pipeline with export layer | Phase 2 (this phase) | run_pipeline gains `step_export`; consumers can `import-from-dir` the output |
| Non-canonical stems layout (`stems/htdemucs/<stem>/…`) | Canonical symlinks (`stems/{vocals,drums,other}.wav`) coexist with non-canonical originals | Phase 2 | Both layouts work; old references (`<basename>_vocals.wav` in timeline.html) and new references (`stems/vocals.wav` in asset.json) resolve |
| Output dir = ad-hoc collection | Output dir = self-describing ShotTimelineAsset | Phase 2 | `asset.json` becomes the entry point for downstream consumers |
| serve.py leaks FDs on every Range request | serve.py closes FDs correctly | Phase 2 | Long seek sessions no longer exhaust file descriptors |

**Deprecated/outdated:**
- `SPEC.md §5 Prompts` mentions `html/gen_prompts_html.py` as producer — file does NOT exist (spec drift; producer is external). Not blocking for Phase 2 since the exporter treats prompts.json as opaque input.

## Assumptions Log

> Claims tagged `[ASSUMED]` in this research. Planner and discuss-phase should confirm these before locking the plan.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | prompts.json is produced by an external/manual step outside this repo (notebook, ad-hoc script, one-off LLM call) | Pitfall 4, Pitfall 5, Validation Architecture | If a Python producer exists somewhere not grepped (e.g., notebook, shell script), the planner may want to surface it. Mitigation: confirmed via `find . -name "*.py"`, `grep -rn prompts.json --include="*.py"` — no in-repo producer. **Risk: LOW** (exporter behavior correct either way) `[ASSUMED]` |
| A2 | `generator.version = git short SHA` is acceptable to users (CONTEXT discretion) | Code Examples | Some users may prefer a hardcoded semver like "1.0.0". **Risk: LOW** — schema accepts any string; easy to change one line. `[ASSUMED]` |
| A3 | Range-206 self-check belongs in `scripts/check_range.py` as a standalone script (not pytest, not subcommand of export_asset.py) | Architecture Patterns, Code Examples | If user prefers a pytest, that introduces a test framework (the repo has zero test files). If user prefers subcommand, exporter's argparse gets messy. **Risk: LOW** — both are easily refactored. `[ASSUMED]` |
| A4 | Step prefix `[N/6]` is preferred over introducing a `TOTAL_STEPS` constant | Pitfall 3 | Minor stylistic choice; literal find/replace vs constant. **Risk: TRIVIAL**. `[ASSUMED]` |
| A5 | `video.mp4` symlink pointing to an absolute path OUTSIDE the asset root (e.g., `/data/home/kai/下载/bilibili_xiaojianghu/…mp4`) is acceptable for v1.0 | Pitfall 1 | Asset dir is non-portable (moving it breaks the symlink). CONTEXT.md deferred zip/portability to v2. **Risk: MEDIUM** — if user expects to `cp -r output/<asset>/ /elsewhere/` and have it work, it won't. Mitigation: print a warning when the symlink target is outside the asset root. `[ASSUMED]` |

## Open Questions (RESOLVED)

> All 3 questions resolved during planning — plans implement the recommendations verbatim. Resolution markers added post plan-checker (doc-format fix, no content change).

1. **Should the exporter fail or warn when `transcript.source != basename(video)`?**
   - What we know: Both are usually identical (transcribe.py writes `source` from the same basename). Cross-check verified identical for episode 03.
   - What's unclear: If they diverge (e.g., user renamed the video after transcribe), should export fail or warn?
   - Recommendation: **Warn + use `basename(video)`** (the authoritative `--video` arg). Don't fail — the schema accepts any string; provenance divergence isn't a schema violation.
   - RESOLVED: Plan 02-01 implements warn-don't-fail with `basename(video)` as authoritative.

2. **Should `step_export` run if `prompts.json` is missing, skipping only the export (not failing the pipeline)?**
   - What we know: CONTEXT says exporter "fails loud". But pipeline-level, should `step_export` failure cascade to non-zero exit of `run_pipeline.py`?
   - What's unclear: Is "exporter fails loud" an exporter-internal behavior (sys.exit inside export_asset.py) or a pipeline-level behavior (step_export propagates CalledProcessError → main exits non-zero)?
   - Recommendation: **Exporter sys.exits with non-zero → subprocess.run(check=True) raises CalledProcessError → run_pipeline.py crashes with traceback.** Matches existing `subprocess.run([...], check=True)` pattern. This is "fails loud" by the project's existing convention.
   - RESOLVED: Plan 02-01 relies on `subprocess.run(..., check=True)` → `CalledProcessError` cascade (matches recommendation).

3. **Should the Range-206 self-check script be auto-invoked at the end of `step_export`, or be a separate manual step?**
   - What we know: CONTEXT discretion ("落地形式 plan 阶段定"). SC-3 needs "206 Partial Content responses observed" — automated check provides evidence.
   - What's unclear: Should running `run_pipeline.py` always run the Range check (adds ~1s + spawns a server), or should the check be opt-in via a separate CLI?
   - Recommendation: **Standalone script, NOT auto-run by step_export.** Reasons: (a) the check requires `serve.py` to bind a port (concurrency risk in parallel pipelines); (b) step_export is a producer concern, Range serving is a server concern — coupling them muddies the architecture; (c) the check is a verification step, belongs with `/gsd:verify-work` or Phase 4 regression harness, not every pipeline run. The phase plan should include a task to run check_range.py manually as part of acceptance.
   - RESOLVED: Plan 02-02 keeps `check_range.py` standalone (not wired to step_export); manual run in acceptance.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | export_asset.py, serve.py, check_range.py | ✓ | 3.12.3 | — |
| ffprobe | source.duration_sec sourcing (fallback path) | ✓ | 6.1.1-3ubuntu5 | Read duration from transcript.json (always present, no fallback needed) |
| jsonschema | inline asset.json validation | ✓ | 4.26.0 | — (already used by spec/validate.py since Phase 1; no install needed) |
| git CLI | generator.version (git SHA) | ✓ | (any) | Hardcoded "dev" string if git missing |
| curl (optional) | ad-hoc manual Range tests | ✓ | 8.5.0 | urllib (used by check_range.py instead — no curl dependency) |
| ffmpeg | NOT REQUIRED by Phase 2 (no transcoding in export step) | ✓ | 6.1.1 | — |
| Linux symlinks | canonical media symlink creation | ✓ | ext4 (verified via `ln -s` test) | Phase deferred Windows compat (CONTEXT) |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none — all required dependencies verified present.

`[VERIFIED: bash command -v / --version for each]`

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — Dimension 8 validation requirement applies. Repo has NO existing test framework (no pytest, no unittest files). Phase 2 introduces **standalone verification scripts** instead of a framework, matching project style.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None (project convention — standalone scripts with `sys.exit(0/1)`) |
| Config file | none — Wave 0 will NOT add pytest (scope creep) |
| Quick run command | `python3 spec/validate.py` (validates Phase 1 minimal fixture + smoke on output/) |
| Full suite command | `python3 spec/validate.py --strict-smoke && python3 scripts/check_range.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPORT-01 | asset.json present + conforms to asset.schema.json | smoke (inline + schema) | `python3 -c "import json,sys; from jsonschema import Draft202012Validator; v=Draft202012Validator(json.load(open('spec/schemas/asset.schema.json'))); errs=list(v.iter_errors(json.load(open('output/<dir>/asset.json')))); sys.exit(1 if errs else 0)"` | ❌ Wave 0 (asset.json not yet produced; will exist post-task) |
| EXPORT-01 | prompts.json-presence guard fires correctly | unit (exit-code check) | `python3 scripts/export_asset.py --work-dir /tmp/empty --video x.mp4 --stems-source-dir /tmp/empty 2>&1 \| grep -q "prompts.json 不存在"` | ❌ Wave 0 (script not yet written) |
| EXPORT-01 | asset.json schema validation included in export step | integration | `python3 spec/validate.py --strict-smoke` (after export, this validates 5 data shapes strictly) | ✅ EXISTS (spec/validate.py from Phase 1) |
| EXPORT-02 | Existing algorithms untouched (additive only) | manual / git-diff inspection | `git diff main -- detectors/ audio/ html/gen_timeline_html.py` (expect no changes) | ❌ Wave 0 (manual, no script) |
| EXPORT-02 | Manifest carries version + self-describing fields | smoke (schema-validated) | covered by EXPORT-01 schema check (asset.schema.json requires schema_version + generator) | ❌ Wave 0 |
| EXPORT-03 | Range request returns 206 + Content-Range + Accept-Ranges | smoke (HTTP) | `python3 scripts/check_range.py` | ❌ Wave 0 (script not yet written) |
| EXPORT-03 | Canonical media symlinks resolve to real files | unit (path resolution) | `python3 -c "import os,sys; [sys.exit(1) for p in ['video.mp4','stems/vocals.wav','stems/drums.wav','stems/other.wav'] if not os.path.exists('output/<dir>/'+p)]"` (inline in export_asset.py post-write) | ❌ Wave 0 |
| EXPORT-03 | serve.py no longer leaks FDs on Range requests | manual (observable via stderr) | `python3 scripts/serve.py output/<dir> 8765 & done; for i in {1..50}; do curl -s -o /dev/null -H 'Range: bytes=0-1023' http://localhost:8765/video.mp4; done; ls /proc/<pid>/fd \| wc -l` (expect no AttributeError in stderr; FD count stable) | ❌ Wave 0 (manual verification) |

### Sampling Rate
- **Per task commit:** `python3 spec/validate.py` (quick — ~1s, no network)
- **Per wave merge:** `python3 spec/validate.py --strict-smoke && python3 scripts/check_range.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`. Specifically:
  - `spec/validate.py` minimal 6/6 `[valid]`
  - `spec/validate.py --strict-smoke` smoke 5/5 `[smoke-valid]`
  - `scripts/check_range.py` exits 0 (206 + Content-Range + Accept-Ranges observed)
  - Manual: `git diff main -- detectors/ audio/ html/gen_timeline_html.py` shows zero algorithm changes
  - Manual: 50 consecutive Range requests produce no `AttributeError` in serve.py stderr

### Wave 0 Gaps
- [ ] `scripts/export_asset.py` — produces asset.json (covers EXPORT-01, EXPORT-02)
- [ ] `scripts/check_range.py` — Range-206 self-check (covers EXPORT-03)
- [ ] No new framework install needed (uses standalone-script convention)

*(No test framework gap — project explicitly has none and Phase 2 should not introduce one.)*

## Security Domain

> `security_enforcement` is not explicitly set in `.planning/config.json` — defaults to enabled. Phase 2 has minimal security surface (CLI tool, no auth, no network listeners added — serve.py already exists). Light coverage here.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in this phase (serve.py binds 0.0.0.0 unauth — deferred per CONTEXT) |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | CLI tool, runs as user |
| V5 Input Validation | yes | jsonschema validation of asset.json (pattern-based path traversal rejection in asset.schema.json) |
| V6 Cryptography | no | No crypto |
| V12 Files & Resources | yes | Path traversal prevention via asset.schema.json patterns `(?!.*\.\.)`; canonical symlink targets validated before creation |

### Known Threat Patterns for Python CLI + static HTTP server

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via malicious asset.json paths (e.g., `data.shots = "../../etc/passwd"`) | Tampering | asset.schema.json regex rejects `..` in all data/media paths; exporter doesn't read user-supplied paths into asset.json (all paths are literals) `[CITED: spec/schemas/asset.schema.json]` |
| Symlink swap attack (TOCTOU) | Tampering | Low risk for offline CLI; ensure_symlink uses `os.symlink` atomically; pre-check `os.path.islink` to avoid clobbering regular files |
| FD exhaustion via long-lived Range session | Denial of Service | Fixed by `_Partial.close()` (Pitfall 2) |
| Bind to 0.0.0.0 unauth | Information Disclosure | DEFERRED per CONTEXT (single-user offline dev tool) — out of Phase 2 scope |

## Sources

### Primary (HIGH confidence)
- **Codebase inspection (this session):**
  - `run_pipeline.py` — orchestrator, step_* patterns, mtime cache, subprocess-by-path
  - `scripts/serve.py` — Range server, FD-leak locus, `_Partial` class
  - `spec/validate.py` — jsonschema validator, SMOKE_SHAPES excludes asset
  - `spec/schemas/asset.schema.json` — manifest schema (all 6 pattern regexes)
  - `spec/fixtures/minimal/asset.json` — canonical reference manifest
  - `spec/SPEC.md` — prose contract (455 lines)
  - `output/《小江湖》第03话：…/` — live production output verified
  - `html/gen_timeline_html.py:139-166` — step_timeline pattern (mtime cache)
- **Live verification (this session):**
  - `python3 spec/validate.py` → minimal 6/6 valid, smoke 5/5 valid
  - `ffprobe original video` → `av1,video\naac,audio` (has audio)
  - `ffprobe h264.mp4` → `h264,video` (audio stripped via `-an`)
  - `ls -la output/<dir>/` → existing `<original-name>.mp4 → h264.mp4` symlink chain
  - `curl -H 'Range: bytes=0-4' http://localhost:8767/test.txt` → 206 + Content-Range + AttributeError traceback (FD-leak root cause)
  - `ls output/<dir>/stems/htdemucs/<video-stem>/` → 4 wavs (vocals/drums/bass/other, ~34 MB each)
  - `find . -name "gen_prompts*.py"` → none (SPEC.md §5 producer reference is wrong)

### Secondary (MEDIUM confidence)
- **Python stdlib docs** — `urllib.request` semantics, `datetime.isoformat` behavior
- **http/server.py source** (`/usr/lib/python3.12/http/server.py:681`) — `do_GET`/`do_HEAD` `finally: f.close()` contract

### Tertiary (LOW confidence)
- None — all claims verified live or against codebase/schema

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — all stdlib + already-installed jsonschema; verified via `python3 -c "import …"`
- Architecture: **HIGH** — directly mirrors existing `step_*` patterns; no novel architecture
- Pitfalls: **HIGH** — all verified live (especially FD-leak root cause and video.mp4 symlink chain)
- Code examples: **HIGH** — sourced from live output dir + existing codebase patterns
- prompts.json producer: **MEDIUM** — confirmed absent in repo, but the actual external producer is unknown (assumed notebook/manual)

**Research date:** 2026-07-20
**Valid until:** 2026-08-19 (30 days — stable; this phase touches no fast-moving library)
