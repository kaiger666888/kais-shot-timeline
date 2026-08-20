---
phase: 20-h3-regen-client
plan: 01
subsystem: analysis
tags: [comfyui, fl2va, h3, regen, roundtrip, per-shot-cache, resume, offline-tests]

# Dependency graph
requires:
  - phase: 18-contract-v1.3
    provides: roundtrip 契约（regen.path 相对 asset root 约定、warnings 三码 enum、[roundtrip] 通道）
  - phase: 19-qwen-eye-v2
    provides: vision_seq 4-tuple cache / graceful-degrade / 批循环降级全套先例、qwen_eye_client._http_json stdlib plumbing
provides:
  - analysis/roundtrip/workflow_fl2va.json 模板（13 节点 native KSampler 链，euler+simple/15/cfg1.0/shift_video=12.0，数据与代码分离）
  - analysis/roundtrip/h3_regen.py 渲染链客户端（模板 deepcopy 注入 / ffmpeg 全分辨率首尾帧 / curl 上传 / 提交-轮询-下载 / 确定性 seed / 17k+5 length 网格）
  - 4-tuple per-shot cache（route_cache/h3_regen/shot_NNN.json 与 mp4 实体分离）+ 断点续跑 + 客户端 --force
  - warnings 双形 merge（str+dict 保留、上一轮 [roundtrip] strip、陌生 str 不误伤）
  - run_pipeline --force 显式清单扩展（roundtrip/ + roundtrip.json）
  - 15 个离线单测（FakeComfyUI + subprocess fake），全套 88 passed
affects: [20-02-vram-sampling, 20-03-smoke, 21-scorer, 22-dataset-export]

# Tech tracking
tech-stack:
  added: []   # 零新 pip 依赖（stdlib + 系统 curl/ffmpeg，RESEARCH 锁定）
  patterns:
    - "workflow JSON 数据模板 + deepcopy 注入（repo 首个代码旁置数据模板文件）"
    - "cache 元数据与 mp4 实体分离（hit = 4-tuple 全等 + 实体存在且 >1KB，无 ffprobe 深检）"
    - "per-shot prompt_version = sha256(prompt_text)[:8]（与 vision_seq 全局版本串不同——facet 级变化只重渲该镜）"
    - "engine_version 冻结 model+sampler+scheduler+steps+resolution（Q3 裁决，cache 不设第 5 维）"
    - "poll crash-safe 骨架（瞬态异常 continue + 60s 节流日志 + sleep 15s，kmc v4 四可抄点）"
    - "warnings 双形 merge helper（dict code∈enum 或 str [roundtrip] 前缀识别上一轮）"
    - "_http_json 模块级函数（非 staticmethod）—— 测试单一 monkeypatch 点"

key-files:
  created:
    - analysis/roundtrip/workflow_fl2va.json
    - analysis/roundtrip/h3_regen.py
    - tests/test_h3_regen.py
  modified:
    - run_pipeline.py

key-decisions:
  - "REGEN-01/02 保持未勾选 —— 本 plan 交付离线代码半边，VRAM guard+抽样（20-02）与真机 smoke（20-03）共享同 requirement IDs（mirror 18-01/19-01 先例）"
  - "derive_seed = int(sha256(f\"{vch}:{shot_id}\")[:8],16) % 2**31 —— 跨进程确定（kmc hash() 随机化是 Pitfall 2 实锤），seed 进 cache 元数据可追溯"
  - "load_shot_prompts 以 shots.json 为分割权威、prompts.json 按 shot_id 供 prompt_text —— 缺 prompt_text 的镜跳过并产 str warning（事件性说明走 legacy str 形永远合法）"
  - "单镜失败/超时/文件名非法/产物过小 → failed 清单 + continue，绝不阻塞批（mirror vision_seq L660 形态）；ComfyUI 不可达 → dict warning + exit 0"
  - "run_pipeline --force 的 roundtrip_dir/roundtrip_json 变量与元组条目都放 force 块内（不放 pre-run 变量区）—— 保证 verify 窗口内可见且语境正确"
  - "h3_regen 自带 --force 清 route_cache/h3_regen/ + roundtrip/ + roundtrip.json（与 run_pipeline --force 显式清单同语义，独立运行时也可全重跑）"

patterns-established:
  - "FakeComfyUI 测试形态：FakeHTTP 回放序列 + subprocess fake（curl/ffmpeg 按 cmd[0] 分发）+ _view_download 直写字节 + FakeClock 推进超时"
  - "客户端模块 docstring 必记 Pitfall 6 交互（vision_seq warnings 读法会丢 dict 条目，本模块双形 merge 不受影响）"

requirements-completed: []   # REGEN-01/02 属 phase 级，20-02/20-03 完成后才勾（见 key-decisions）

# Metrics
duration: 9min
completed: 2026-08-19
---

# Phase 20 Plan 01: h3 复现客户端渲染链 Summary

**ComfyUI 直连 fl2va 复现客户端核心链路：13 节点 workflow 模板 deepcopy 注入 + 提交/轮询/view 下载 + per-shot 4-tuple cache 断点续跑 + warnings 双形 merge，15 个全离线单测零真引擎**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-08-19T19:58:34Z
- **Completed:** 2026-08-19T20:07:12Z
- **Tasks:** 3/3
- **Files modified:** 4 (3 created + 1 modified)

## Accomplishments
- fl2va workflow 模板数据文件（13 节点 native KSampler 链）与渲染链核心：length 17k+5 网格对齐（124-362）、确定性 seed、7:4 分辨率校验、ffmpeg 全分辨率首尾帧提取（无 -vf/scale）、curl multipart 上传、stdlib 提交/轮询/view 下载全链
- REGEN-02 完整离线半边：4-tuple per-shot cache（元数据/实体分离）、prompt_version 改一字仅重渲该镜、断点续跑（预置 3/5 镜只补 2 镜）、客户端与 run_pipeline 双侧 --force 显式清单
- warnings 双形 merge + ComfyUI 可达性 graceful-degrade（exit 0 + comfyui_unreachable dict warning）；全套件 88 passed（73 基线 + 15 新增，零回归）

## Task Commits

Each task was committed atomically:

1. **Task 1: workflow_fl2va.json 模板 + h3_regen.py 渲染链核心** - `a3d2689` (feat)
2. **Task 2: 4-tuple cache + 断点续跑 main() + warnings 双形 merge + run_pipeline --force 扩展** - `d90ef18` (feat)
3. **Task 3: 离线单测 tests/test_h3_regen.py** - `addd874` (test)

**Plan metadata:** (见下方最终 docs commit)

## Files Created/Modified
- `analysis/roundtrip/workflow_fl2va.json` - 13 节点 fl2va 模板（占位符 `<FF_FILENAME>`/`<LF_FILENAME>`/`<PROMPT_TEXT>`/`<PREFIX>` 原样保留，运行时 deepcopy 注入）
- `analysis/roundtrip/h3_regen.py` - 渲染链 + cache + main() 单模块客户端（646 行，全 stdlib）
- `tests/test_h3_regen.py` - FakeComfyUI 离线单测（445 行，15 用例）
- `run_pipeline.py` - --force 块扩展（roundtrip_dir/roundtrip_json 两个显式条目 + h3_regen 覆盖注释）

## Decisions Made
- 见 frontmatter key-decisions（6 条）。核心：REGEN-01/02 勾选延后到 20-03 smoke 后（mirror 18-01/19-01 先例）；engine_version 冻结五参数进版本串。

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- 测试初版两处自伤（Task 3，均在提交前修复）：(a) `test_extract_frames_no_scale` 的 `"scale" not in " ".join(cmd)` 被 pytest tmp 目录名（含测试名 "no_scale"）误触发 → 改为 argv 元素级检查（`a == "scale"` / `startswith("scale=")`）；(b) `test_resume_only_missing` 的回放序列双层嵌套元组导致 FakeHTTP 解包错位 → 改为显式 for 循环平铺 append。均为测试代码问题，模块实现零改动。

## User Setup Required

None - no external service configuration required.（真机 smoke 需 ComfyUI :8188 存活，属 20-03 执行期检查。）

## Next Phase Readiness
- 20-02 直接叠加：VRAM guard（TTS kill + /free + PID 归因复查）插在 system_stats gate 之后（main() 已留标准序注释位）；`--sample-shots`/`--max-shot-sec`/`--regen-resolution` 接入批循环（parse_resolution/validate_resolution/h3_frame_count 已就位）
- 20-03 真机 smoke：`python3 analysis/roundtrip/h3_regen.py --work-dir <ep01 dir>` 全链已具备；roundtrip.json sidecar writer（regen 半边 READ-merge）是 20-03 Task 1 范围
- 无 blocker；FakeClock/FakeHTTP 测试基建可被 20-02 VRAM 用例直接复用

## Self-Check: PASSED

- Files: workflow_fl2va.json / h3_regen.py / test_h3_regen.py / run_pipeline.py / SUMMARY.md 全部存在
- Commits: a3d2689 / d90ef18 / addd874 全部在 git log
- Full suite: 88 passed（73 基线 + 15 新增，零回归）

---
*Phase: 20-h3-regen-client*
*Completed: 2026-08-19*
