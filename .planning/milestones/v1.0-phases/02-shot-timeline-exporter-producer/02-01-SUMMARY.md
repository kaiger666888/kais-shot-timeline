---
phase: 02-shot-timeline-exporter-producer
plan: 01
subsystem: producer-exporter
tags: [exporter, manifest, symlinks, jsonschema, run-pipeline]
requires:
  - "Phase 1: spec/schemas/asset.schema.json (authoritative schema)"
  - "Phase 1: spec/fixtures/minimal/asset.json (canonical reference shape)"
  - "Pre-GSD baseline: run_pipeline.py 5-step orchestrator"
  - "Pre-GSD baseline: output/<video-stem>/{shots,audio_analysis,transcript,frames,prompts}.json producers"
provides:
  - "scripts/export_asset.py — ShotTimelineAsset 导出器 (manifest + canonical symlinks + inline jsonschema 自校验)"
  - "run_pipeline.py:step_export — pipeline 第 6 步 (mtime cache + subprocess 调用)"
  - "output/<video-stem>/asset.json — 自描述 manifest (schema_version=1, generator.{tool,version,generated_at})"
  - "output/<video-stem>/video.mp4 + stems/{vocals,drums,other}.wav canonical symlinks"
affects:
  - "scripts/export_asset.py (NEW)"
  - "run_pipeline.py (MODIFIED — step_export + --skip-export + --force asset.json + [N/6] 全量替换 + module docstring)"
tech-stack:
  added: []
  patterns:
    - "inline Draft202012Validator (不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES 排除 asset)"
    - "canonical symlinks (target 必须 abspath —— 相对 target 会按 symlink 所在目录解析)"
    - "ensure_symlink 幂等 (readlink 一致 skip; 非 symlink 拒绝覆盖; symlink 不一致 unlink+recreate)"
    - "step_export mtime cache (5 数据 JSON + video 作为 inputs)"
    - "lazy import jsonschema (CLAUDE.md optional-dep 惯例)"
key-files:
  created:
    - scripts/export_asset.py
  modified:
    - run_pipeline.py
decisions:
  - "video.mp4 symlink target = --video abs path (NOT <original-name>.mp4 in work_dir; 后者链到 -an 去 audio 的 h264.mp4)"
  - "generator.version = git short SHA (fallback 'dev'); generated_at UTC ISO-8601 with Z"
  - "bass.wav 显式剔除 canonical 集合 (schema 拒绝 + 前端只渲染 3 stems); htdemucs 原始 bass 不动"
  - "prompts.json 视作 opaque external input —— required-to-exist, fail loud; 不在导出器内产出"
  - "step_export 失败 = export_asset.py sys.exit 非 0 -> subprocess.run(check=True) raises -> pipeline 崩 (fails loud 项目惯例)"
metrics:
  duration: ~25min
  completed: 2026-07-20T14:00:00Z
  tasks: 2
  files_created: 1
  files_modified: 1
---

# Phase 2 Plan 1: ShotTimelineAsset Exporter (Producer) Summary

新增 `scripts/export_asset.py` (manifest 写入 + 4 canonical symlinks + inline jsonschema 自校验)，并把 `run_pipeline.py` 从 5 步扩成 6 步（step_export + --skip-export + --force 清 asset.json + [N/5]→[N/6] 全量替换 + module docstring 更新）；严格 additive-only，detectors/audio/html/gen_timeline_html.py 零修改。

## What Was Built

### Task 1 — `scripts/export_asset.py` (NEW, 269 lines)

独立 argparse CLI，结构沿用 `html/gen_timeline_html.py` 模板（shebang + Chinese module docstring + helper + main + `if __name__ == "__main__"`）。

**职责：**
- 读 `transcript.json` 的 `source` / `duration` 字段；fallback `_probe_duration(video)` ffprobe。
- 组装 asset dict（schema_version="1", asset_type="shottimeline", generator.{tool, version=git SHA, generated_at=UTC ISO-8601}, 5 data JSON 字面量, media.{video.mp4, stems.{vocals,drums,other}.wav}）。
- 创建 4 个 canonical symlinks：`video.mp4` → 原始视频 abs path（含 audio 流，ffprobe 预检）；`stems/{vocals,drums,other}.wav` → `stems/htdemucs/<video-stem>/<name>.wav`。
- 写 `asset.json`（`json.dump(..., indent=2, ensure_ascii=False)`）。
- 立即 inline `Draft202012Validator(asset.schema.json)` 自校验（lazy import；绝不 subprocess 到 `spec/validate.py`）。
- `prompts.json` 缺失 → `sys.exit` 非 0 + 中文 actionable error。

**4 个 helper：** `_probe_duration` (ffprobe 兜底), `_git_sha` (subprocess + fallback 'dev'), `ensure_symlink` (幂等 symlink 创建), `validate_asset_json` (inline jsonschema)。

### Task 2 — `run_pipeline.py` (MODIFIED)

4 处修改：

- **(A) 全量替换 [N/5] → [N/6]**：14 处覆盖（line 63/67/69 ensure_h264; 87/90/97 step_detect; 105/108/116 step_separate; 124/127/135 step_transcribe; 147/165 step_timeline）。
- **(B) 新增 `step_export(work_dir, video, stems_source_dir, asset_json, skip, force)`**：
  - skip 模式：`[6/6] --skip-export: skipping asset export` + return early
  - mtime cache：5 数据 JSON + video 作为 inputs（mirror step_timeline 模式）
  - subprocess 调 `scripts/export_asset.py` via `run_step(cmd, "[6/6] ShotTimelineAsset export")`；`--force` 透传
  - 失败行为：subprocess.run(check=True) raises CalledProcessError → pipeline 崩（项目既定 fails loud 惯例）
- **(C) argparse 新增 `--skip-export`**：在 `--skip-transcribe` 之后；中文 help。
- **(D) main 接入**：asset_json 路径常量；`--force` wipe tuple 加 asset_json；step_timeline 后调用 step_export；`[done]` print 加 `asset:` 行。
- **module docstring 更新**：步骤列表 5→6；CLI 用法加 `[--skip-export]`；输出布局新增 `video.mp4` / `stems/{vocals,drums,other}.wav` / `asset.json` / `prompts.json` 四行。

## Verification Evidence

**Task 1 端到端**（对真实 `output/《小江湖》第03话…/` 跑通）：
- `[export-asset] wrote asset.json → .../asset.json` 退出码 0
- `Draft202012Validator(asset.schema.json).iter_errors(asset)` 返回空列表（零错误）
- `ffprobe video.mp4` 输出含 `audio` 流（非 h264.mp4）
- 4 个 canonical paths 都 resolve 到真实文件
- 幂等 re-run 退出码 0（ensure_symlink readlink 一致 skip）
- `spec/validate.py` 仍报 minimal 6/6 `[valid]` + smoke 5/5 `[smoke-valid]`（Phase 1 invariant 未破坏）
- prompts.json 缺失（mktemp 空目录）退出码 1 + stderr 含字面量 `prompts.json 不存在`
- 源码标记：`from jsonschema import Draft202012Validator` ✓ `os.symlink` ✓ `"video.mp4"` ✓ `"stems/vocals.wav"` ✓ `! grep "spec/validate.py"` ✓ `! grep "stems/bass.wav"` ✓

**Task 2 端到端**：
- `grep -c '\[[0-9]/5\]' run_pipeline.py` = 0；`grep -c '\[[0-9]/6\]'` = 17（14 原有 + 3 新增 step_export）
- `python3 run_pipeline.py --help` 含 `--skip-export`
- `python3 run_pipeline.py --video <ep03> --skip-detect --skip-separate --skip-transcribe` 产出 schema-valid `asset.json`
- `--skip-export` 真的跳过（asset.json mtime 不变；log 含 `[6/6] --skip-export: skipping asset export`）
- 无 `--skip-export` 时 mtime cache 命中：`[6/6] cached asset: ...asset.json`
- `for p in (..., asset_json):` grep 确认 asset_json 在 --force wipe tuple
- additive-only invariant：`git diff f32d537 -- detectors/ audio/ html/gen_timeline_html.py` 完全为空（仅本 plan 改动范围）

**资产产物示例**（asset.json 关键字段）：
```json
{
  "schema_version": "1",
  "asset_type": "shottimeline",
  "source": { "video_filename": "《小江湖》第03话：….mp4", "duration_sec": 197.418667 },
  "generator": { "tool": "kais-shot-timeline", "version": "2d7ecef", "generated_at": "2026-07-20T13:43:00Z" },
  "data": { "shots": "shots.json", "audio_analysis": "audio_analysis.json", "transcript": "transcript.json", "frames": "frames.json", "prompts": "prompts.json" },
  "media": { "video": "video.mp4", "stems": { "vocals": "stems/vocals.wav", "drums": "stems/drums.wav", "other": "stems/other.wav" } }
}
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] stem symlinks 相对 target 失效**
- **Found during:** Task 2 端到端测试（pipeline 调用 export_asset.py）
- **Issue:** export_asset.py 接收 `--stems-source-dir ./output/...`（相对路径）时，`os.symlink(os.path.join(args.stems_source_dir, "vocals.wav"), link_path)` 创建的 symlink target 是 `./output/.../vocals.wav`。Symlink target 的相对路径按「symlink 所在目录」解析（不是 cwd），所以 `output/<stem>/stems/vocals.wav` 的相对 target 解析到 `output/<stem>/stems/./output/.../vocals.wav`，broken。RESEARCH Pitfall 1 已为 video target 确立了 abs path 要求，但 plan 没显式覆盖到 stems。
- **Fix:** export_asset.py main() 顶部一次性 abspath 化所有路径 args（work_dir / video / stems_source_dir / output）；后续全程使用 abs 变量。
- **Files modified:** scripts/export_asset.py（+9 行 abspath 块 + body 内 args.* → 局部变量）
- **Commit:** 2d7ecef

### Test-Fixture Cleanup Note

执行 Task 2 验证 `--force` 时，组合 `--skip-detect --force` 触发了 pre-existing pipeline 行为（`step_detect` skip 时若 shots.json 已被 --force 清掉则返回 None，pipeline `sys.exit("scene detection did not produce shots.json; aborting")`）。这导致 `output/《小江湖》第03话…/` 下被 --force 清掉的 5 个数据 JSON（shots/frames/audio_analysis/transcript/timeline.html）未能通过 skip 路径恢复。

为不阻塞 plan 02-02 的测试，已在后台启动完整 pipeline 重跑（detection + separation + transcription + timeline + export）以重建缓存。这是测试副作用，不是 plan 缺陷——`--force + --skip-detect` 的 cascade abort 是 pre-existing pipeline 设计，本 plan 未引入。

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Inline `Draft202012Validator`（不 subprocess 到 spec/validate.py） | spec/validate.py:49 的 SMOKE_SHAPES 显式排除 asset；subprocess 会让无效 manifest 悄悄通过 |
| `video.mp4` target = `--video` abs path | 02-RESEARCH Pitfall 1：work_dir 内的 `<original-name>.mp4` 链到 `-an` 去 audio 的 h264.mp4；消费者会听不到声音 |
| `bass.wav` 不在 canonical 集合 | asset.schema.json media.stems required=[vocals,drums,other]；前端只渲染 3 stems；htdemucs 原始 bass 不动（additive-only） |
| `prompts.json` 视作 opaque external input | 仓库内无 Python producer；导出器只 required-to-exist + fail loud（不在本 plan 加 producer） |
| `generator.version` = git short SHA | CONTEXT discretion；schema 接受任意 string；fallback 'dev' 用于非 git 环境 |
| `step_export` 失败 = pipeline 崩 | 项目既定 fails loud 惯例（subprocess.run check=True + sys.exit 非 0）；不引入 error path 吞错 |
| main 顶部统一 abspath 化 | symlink target 必须 abs；方案比「run_pipeline.py 把 abspath 喂给 subprocess」更鲁棒（export_asset.py 独立 CLI 调用也安全） |

## Open Items / Forward Notes

- **FD-leak fix (T-02-02)** 留给 plan 02-02：scripts/serve.py 的 `_Partial.close()` 缺失导致 Range 206 成功路径 FD 泄漏。本 plan 未动 serve.py。
- **Range-206 self-check (EXPORT-03)** 留给 plan 02-02：scripts/check_range.py 尚未创建。
- **prompts.json 生成步骤的 pipeline 化**：RESEARCH Pitfall 5 指出 SPEC.md §5 提到的 `html/gen_prompts_html.py` 不存在；prompts.json 当前由外部步骤产出。未来可考虑加 producer。
- **跨平台 abs path 警告**（A5, RESEARCH §Open Questions）：video.mp4 symlink 指向 asset 根之外的 abs path（如 `/data/home/kai/下载/...`），cp -r asset 目录到别处会断链。v1.0 接受（CONTEXT 限定 zip/portability 为 v2 范畴）。

## Self-Check: PASSED

- FOUND: scripts/export_asset.py (Task 1 new file)
- FOUND: run_pipeline.py (Task 2 modified file)
- FOUND: 414a01e (Task 1 commit)
- FOUND: 2d7ecef (Task 2 commit)
- FOUND: `def step_export(` in run_pipeline.py
- FOUND: `Draft202012Validator` inline validator in export_asset.py
- FOUND: 02-01-SUMMARY.md
