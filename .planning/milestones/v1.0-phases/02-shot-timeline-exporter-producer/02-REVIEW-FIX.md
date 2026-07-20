---
phase: 02-shot-timeline-exporter-producer
fixed_at: 2026-07-20T14:50:00Z
review_path: .planning/phases/02-shot-timeline-exporter-producer/02-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-20T14:50:00Z
**Source review:** `.planning/phases/02-shot-timeline-exporter-producer/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (Warnings only — Critical=0, Info=6 out of scope)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### WR-01: Manifest written to disk BEFORE post-write canonical-path assert and schema validation

**Files modified:** `scripts/export_asset.py`
**Commit:** `e2dc742`
**Applied fix:** Reordered `main()` 的 (g)-(j) 段：先 build asset dict → pre-write assert 4 个 canonical paths 都 resolve 到真实文件（防 dangling symlink 通过 schema pattern 校验）→ inline `Draft202012Validator` schema 校验 → 最后 atomic write（`tmp = output + ".tmp"` + `os.replace`）。Schema-invalid 或 canonical-path 缺失都在落盘前 fail loud，避免下游读到 schema-valid 但语义破损的 manifest。

### WR-02: Missing existence guards for 4 of 5 data files (inconsistent with prompts.json guard)

**Files modified:** `scripts/export_asset.py`
**Commit:** `e29d352`
**Applied fix:** 把 (a) 段单一的 `prompts.json` guard 扩成统一存在性循环，覆盖 `shots.json / audio_analysis.json / transcript.json / frames.json / prompts.json` 全部 5 个 required data files。每个缺失文件都 fail loud，错误消息包含：绝对路径、对应 schema 字段（`data.<field>` 是 required）、以及 actionable 提示（`prompts.json` 提"独立步骤产出"，其余提"--skip-\* 跳过对应步骤"）。已通过临时 fixture（删 audio_analysis.json）验证 fail-loud 路径。

### WR-03: `_probe_duration` returns 0.0 silently — manifest ships with `duration_sec: 0`

**Files modified:** `scripts/export_asset.py`
**Commit:** `b32fbf3`
**Applied fix:** 在 `build_asset_dict` 之后插入 `(g0)` hard check：`if not asset["source"]["duration_sec"]: sys.exit(...)`。低阶 helper `_probe_duration` 维持原 swallow-and-return-0.0 行为（pipeline 内部使用，符合 CLAUDE.md 项目惯例），但 exporter 路径把 0 视为硬错误并给出 actionable 中文消息（提示检查 ffprobe 与 video 可读性）。

### WR-04: ffprobe audio-stream check ignores returncode — misleading error on ffprobe failure

**Files modified:** `scripts/export_asset.py`
**Commit:** `2c1152e`
**Applied fix:** (c) 段 `subprocess.run` 之后先查 `r.returncode != 0`：若非 0 则 fail loud 并 dump `stderr`；只有 returncode==0 时才检查 `"audio" not in r.stdout`。避免 ffprobe 失败（corrupt video / 权限 / PATH 问题）时 stdout 为空触发误导性的 "no audio stream" 错误，把用户带偏到 transcode `-an` 调试路径。

### WR-05: `ensure_symlink` doesn't validate target is a regular file — symlink-to-dir passes post-write assert

**Files modified:** `scripts/export_asset.py`
**Commit:** `b3fb2b9`
**Applied fix:** 在 `ensure_symlink` 函数顶部加 `if not os.path.isfile(target): raise FileNotFoundError(...)`。用 `os.path.isfile`（跟随 symlink 后 stat）而非 `os.path.exists`，显式排除目录 / FIFO / device / socket。这关掉了"误配 `--stems-source-dir` 指向含 `vocals.wav/` 子目录的根"导致 symlink-to-dir 通过 schema pattern + pre-write assert 的故障路径。

### WR-06: `check_range.py` `proc.kill()` not followed by `proc.wait()` — zombie process until parent exits

**Files modified:** `scripts/check_range.py`
**Commit:** `a2617b9`
**Applied fix:** 在 `proc.kill()` 之后补一个 `try: proc.wait(timeout=2) except subprocess.TimeoutExpired: pass`（best-effort）。保持原 try/finally 结构不变。这避免 SIGKILL'd serve.py 子进程在 Linux 上变 zombie —— Phase 4 回归 harness 在循环里多次调 `check()` 时 zombie 会累积。已重新跑 `check_range.py` 验证 206 自检仍 pass。

### WR-07: `step_export` mtime cache TOCTOU on input files; cache key ignores `--video` identity

**Files modified:** `run_pipeline.py`
**Commit:** `e3f0b90`
**Applied fix:** 两处修补（均在 `step_export` 与新增 helpers）：
1. **TOCTOU 修补**：新增 `_safe_mtime(path)` helper（try/except `os.path.getmtime`，缺失返回 `+inf` 强制 cache miss），替换掉原来的 `[p for p in inputs if os.path.exists(p)]` + `os.path.getmtime(p)` 两步模式。
2. **Cache key 修补**：新增 `_video_identity(video)` helper（path + size + mtime_ns 三件套），写入 sidecar `<asset_json>.video-stamp`；cache check 比对当前 `--video` 的身份与 sidecar 内记录，不同则强制 miss。这关掉了"换一个 mtime 更老/相等的 --video（如 backup 恢复）误命中陈旧 manifest"的窗口。`--force` 清缓存循环也加进 sidecar 路径。已端到端验证：sidecar 正确写入、二次运行命中 cache。

## Skipped Issues

_None — all 7 in-scope findings were applied successfully._

## Verification Summary

| Tier | Check | Result |
|------|-------|--------|
| Tier 1 (re-read) | 全部 7 个修改段已 re-read，文本符合预期 | PASS |
| Tier 2 (syntax) | `python3 -c "import ast; ast.parse(open(f).read())"` × 3 文件 + `--help` × 3 | PASS |
| Tier 3 (smoke) | 端到端 export → schema 校验 → check_range → pipeline cache hit | PASS |

Smoke 测试矩阵：
- `python3 scripts/export_asset.py --help`：argparse 仍正常
- 直接 export ep01：`asset.json` schema-valid（0 errors via `Draft202012Validator`），`duration_sec=308.352`（非 0），无 `.tmp` 残留（atomic `os.replace` 工作）
- 临时 fixture 缺 `audio_analysis.json`：fail loud 退出码 1，不写 `asset.json`（WR-02 验证）
- `python3 scripts/check_range.py <ep01>`：206 + Content-Range + Accept-Ranges + 1024 body 全 pass（WR-06 验证）
- `python3 run_pipeline.py --video <ep01> --skip-detect --skip-separate --skip-transcribe`：成功 export + 写入 `.video-stamp` sidecar；二次运行命中 `[6/6] cached asset`（WR-07 验证）

---

_Fixed: 2026-07-20T14:50:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
