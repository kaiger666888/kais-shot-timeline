---
phase: quick
plan: 260819-aw2
subsystem: canvas-export
tags: [canvas, kap, import, pipeline-post-step, urllib]
requires:
  - "kap 画布 HTTP API（127.0.0.1:10588：/api/canvas/projects、/api/project/addProject、/api/canvas/v2/import-from-dir）"
  - "run_pipeline.py step_export 产物 asset.json"
provides:
  - "scripts/canvas_import.py —— 独立画布导入 CLI（按名找/建项目 → import-from-dir，纯 urllib）"
  - "run_pipeline.py --canvas-auto-import 可选 post-step（graceful-degrade）+ --ep-name / --canvas-project-name"
  - "tests/test_canvas_import.py 6 用例（三场景 mock + wiring 冒烟）"
affects:
  - run_pipeline.py（argparse + step_export 后 post-step；默认关闭时零行为变化）
tech-stack:
  added: []          # 纯 stdlib（urllib.request），零新增依赖
  patterns:
    - "urlopen 层记录式替身（mirror test_qwen_eye_client.py FakeHTTP 模式）"
    - "plain-label 无编号 post-step banner（mirror attach_refs / local-vision 先例，[N/9] grep count 不变）"
key-files:
  created:
    - scripts/canvas_import.py
    - tests/test_canvas_import.py
  modified:
    - run_pipeline.py
decisions:
  - "addProject 响应无 id → 建完回读 /api/canvas/projects 按 name 匹配（kap addProject.ts:44 事实，被 Test 2 钉死）"
  - "import 默认 mode=replace（重复导入幂等覆盖，与画布 ep01 口径一致）；episodes-id 默认 1"
  - "post-step 自写 subprocess.run(check=False) 而非 run_step —— graceful-degrade lock（T-AW2-03）"
metrics:
  duration: 3m09s
  completed: "2026-08-19T00:00:08Z"
---

# Phase quick Plan 260819-aw2: 导出后自动导入画布（canvas_import + pipeline 接线）Summary

**One-liner:** 纯 urllib 的画布导入 CLI（按名找/建 kap 项目 → POST import-from-dir，addProject 无 id 响应靠回读拿新 id）+ run_pipeline 可选 graceful-degrade post-step + 6 用例 mock 测试。

## What Was Built

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 (RED) | canvas_import 三场景失败测试 | a6c13aa | tests/test_canvas_import.py |
| 1 (GREEN) | canvas_import.py 独立 CLI | d87e80e | scripts/canvas_import.py, tests/test_canvas_import.py |
| 2 | run_pipeline --canvas-auto-import post-step 接线 | 10103c7 | run_pipeline.py |
| 3 | wiring 冒烟测试（--help 三 flag + 静态断言） | 0e1feb9 | tests/test_canvas_import.py |

**scripts/canvas_import.py（236 行，纯 stdlib）：**
- `_post_json` 唯一 HTTP 出口：UTF-8（`ensure_ascii=False` + `.encode("utf-8")`）、Content-Type `application/json; charset=utf-8`、HTTPError/URLError/非 200 code 全中文 fail-loud（standalone 惯例）。
- `find_project`：POST `/api/canvas/projects`（body `{}`）按 name 精确匹配 → 复用 int id，零 addProject。
- `create_project`：POST `/api/project/addProject` 11 字段（8 空串 + name + intro + `mode="canvas-v2"`，对齐画布 ep01 行实测）→ **回读** projects 按 name 拿新 id（addProject 响应只含 `{message}`，无 id）。
- `run_import`：POST `/api/canvas/v2/import-from-dir`，projectId/episodesId 为 JSON number、workdir 取 abspath；超时 30s（list）/ 600s（import 扫媒体目录）。
- `_episode_intro`：asset.json `source.video_filename` stem；缺失/损坏 fallback 目录名（graceful 不 exit）。

**run_pipeline.py（+50 行）：**
- 三 flag：`--canvas-auto-import`（store_true）、`--ep-name`、`--canvas-project-name`（缺省 `小江湖·逆推资产集({ep_label})`，ep_label = --ep-name 或 video stem）。
- step_export 后 post-step：argv 只传 `--asset-dir` + `--project-name`；自写 `subprocess.run(..., check=False)` + OSError 捕获 → 失败仅 `[canvas-import] warning ...（graceful-degrade，管线继续）`，绝不 re-raise。
- asset.json 缺席（export 被跳过/失败）→ 一行 warning 后继续。
- banner 为 plain label（`canvas auto-import (canvas_import post-step)`），无 `[10/]` 编号；既有 `[N/9]` banner 全部未动（grep count 27 不变）；默认关闭时零新子进程零新输出。

## Verification Results

1. `python3 -m pytest tests/ -q` → **30 passed**（新增 6 + 既有 24，零回归）。
2. `python3 run_pipeline.py --help` → 三 flag 齐全且带中文 help。
3. `python3 -m pytest tests/test_pipeline_vision_wiring.py -q` → 4 passed（step-counter 锁未破坏）。
4. live 冒烟（非变更，--no-create-project 只走 list+match）：`python3 scripts/canvas_import.py --asset-dir "output/虫虫武侠小故事《小江湖》第01话：…" --project-name 不存在的名字-260819 --no-create-project` → `[canvas-import] 项目不存在且指定了 --no-create-project` + exit 1，对真实 server（127.0.0.1:10588，61 项目）往返成功，零写入。
5. fail-loud：`--asset-dir /nonexistent` → exit 1；`--help` 六 flag（--asset-dir/--base-url/--project-name/--episodes-id/--mode/--no-create-project）齐全。
6. 默认零行为变化：post-step 整体在 `if args.canvas_auto_import:` 单一 guard 之后（结构性保证 + 静态断言），未加 flag 时无 `[canvas-import]` 输出、无新子进程。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Test 3 的 CJK 断言载体从「项目名」改为「workdir」**
- **Found during:** Task 1 GREEN
- **Issue:** 原测试断言 import body raw bytes 含 CJK 项目名，但 import body 按 Task 1 action spec 只有 4 键（projectId/episodesId/workdir/mode），无 name 字段 —— 断言永假。
- **Fix:** 测试改用 CJK+全角标点命名的 asset-dir（`虫虫武侠小故事《小江湖》第01话：测试`），断言 workdir 以 UTF-8 原文出现在 raw bytes —— 恰是 T-AW2-01（CJK 路径进 JSON body）真正要钉的性质。
- **Files modified:** tests/test_canvas_import.py
- **Commit:** d87e80e

**2. [Rule 1 - Test bug] banner label 断言去掉引号锚定**
- **Found during:** Task 3
- **Issue:** mirror vision 测试写法时我加了 `'"canvas auto-import (...)"' in src` 引号锚定断言，但 plan 指定的 banner 是单条含内嵌 `\n` 的 f-string print（与 run_step 的独立 label 参数不同构），带引号字面量不存在。
- **Fix:** 断言放宽为 label 文本本身 `in src`（仍钉住 banner 无编号这一意图）；run_pipeline.py banner 行保持 plan 指定原样。
- **Files modified:** tests/test_canvas_import.py
- **Commit:** 0e1feb9

无其他偏差 —— 三任务均按 plan 执行（文件位置、flag 语义、超时取值、11 字段形状、回读行为全部对齐）。

## Threat Model Mitigations Applied

- **T-AW2-01 (mitigate):** `json.dumps(..., ensure_ascii=False).encode("utf-8")` + list-form subprocess argv（不经 shell）；Test 3 用 CJK+全角标点目录钉死编码路径。
- **T-AW2-03 (mitigate):** post-step `check=False` + `[canvas-import] warning` + 管线继续到 `[done]`；Test 6 静态断言 `check=False` 在调用块内。
- **T-AW2-02 / T-AW2-04 (accept):** 与既有 route 步骤同威胁模型/日志口径，无新增缓解。

## TDD Gate Compliance

RED `test` commit（a6c13aa，4 用例 ModuleNotFoundError 全红）先于 GREEN `feat` commit（d87e80e，4 用例全绿）—— 门序满足；Task 3 追加 2 wiring 用例后全套件 30 passed。

## Self-Check: PASSED

- scripts/canvas_import.py 存在（236 行 ≥ 120）；tests/test_canvas_import.py 存在（222 行 ≥ 80）；run_pipeline.py 含 canvas_import.py 调用块。
- 四个 commit（a6c13aa / d87e80e / 10103c7 / 0e1feb9）均在 git log；工作树无未提交代码变更（仅 orchestrator 管辖的 plan 目录与两个先前已存在的 untracked 分析脚本）。
