---
phase: 20-h3-regen-client
plan: 02
subsystem: analysis
tags: [comfyui, vram-guard, tts-kill, sampling, regen, roundtrip, offline-tests]

# Dependency graph
requires:
  - phase: 20-h3-regen-client
    provides: 20-01 h3_regen.py 渲染链 + 4-tuple cache + main() 骨架（guard 标准序注释位、FakeHTTP/FakeClock 测试基建）
  - phase: 19-qwen-eye-v2
    provides: qwen_eye_client fail-open 读模式先例（异常→None 不阻塞）
provides:
  - batch_start_guard 五步固定序（TTS 端口→PID kill + 前后审计 warning → POST /free → eye 串行等待 → 二次 /free → 22GB 严格 gate）
  - per-shot PID 归因复查（baseline_pid_snapshot + per_shot_vram_ok：外来进程 Σused≥4096MiB 才阻塞，ComfyUI 自身 cache 驻留永不自锁）
  - TTS 安全 kill 语义（ss -tlnp 端口→PID → os.kill(SIGTERM) 定向；ss 不可用才回退两个精确脚本名 pkill，绝不宽 pkill）
  - --sample-shots 均匀抽样 + --max-shot-sec 跳过清单（skipped.json）+ --regen-resolution 降载（engine_version 冻结 resolution，切换即全 cache 失效）
  - 12 个离线 guard/抽样单测（fake nvidia-smi/ss/os.kill/docker/pkill），全套 100 passed
affects: [20-03-smoke, 21-scorer, 22-dataset-export]

# Tech tracking
tech-stack:
  added: []   # 零新依赖（nvidia-smi/ss/docker/pkill 系统工具 + stdlib）
  patterns:
    - "fail-open 读模式（mirror qwen_eye_client）：nvidia-smi/ss 异常→None/[]，gate 在读数可得时才保守判拒"
    - "guard 五步固定序注释锁定（20-01 已注明）：可达性 gate → batch_start_guard → 批循环"
    - "per-shot PID 归因防自锁：外来 = 当前 compute-apps − baseline（∪ docker inspect comfyui-primary 主 PID），非绝对 free 水位"
    - "None 哨兵区分『ss 不可用』（回退 pkill）与『无监听』（no-op + 审计 warning）"
    - "uniform_sample 去重取整位置集 {int(i*len/n)} 映射升序 ids —— n≥len 或 ≤0 退化为全量"
    - "抽样先于 max-shot-sec 过滤（A6：抽样代表性不被过滤顺序扭曲；被抽中后超时 → sampled 计数保留 + skipped.json 记录）"
    - "fake subprocess dispatcher 按 cmd[0] 分发 + None 触发 OSError（模拟 ss 缺失）+ list 逐条 pop 模拟批中外来进程中途出现"

key-files:
  created: []
  modified:
    - analysis/roundtrip/h3_regen.py
    - tests/test_h3_regen.py

key-decisions:
  - "REGEN-03/04 保持未勾选 —— 本 plan 交付离线代码半边，真机 smoke（20-03）共享同 requirement IDs（mirror 18-01/19-01/20-01 先例）"
  - "guard 五步固定序 + kill 审计 warning 沿用 vram_insufficient 码（三码闭包内做事件归因，不扩 enum —— 契约 18-01 锁定）"
  - "先抽样后过滤（--sample-shots 先于 --max-shot-sec 作用于全量清单）+ 切换 --regen-resolution 冻 engine_version 整 cache 失效（Q3 裁决延伸）"
  - "每镜复查只看外来进程 Σused≥4096MiB，绝不设绝对 free 下限 —— ComfyUI 自身 ~18GB cache 驻留在 baseline 内，防 Pitfall 1 自锁"
  - "skipped.json READ-merge 按 shot_id 替换重排序原子写（与 shot cache 同目录 route_cache/h3_regen/）"

patterns-established:
  - "guard 测试形态：ok_responses 前插 GUARD_FREES=[(200,{freed}),×2] —— 后续新增 HTTP 前置调用需同步此序列"
  - "kill 安全测试断言三件套：killed PID 集合精确、全部 SIGTERM、无 pkill 调用"

requirements-completed: []   # REGEN-03/04 属 phase 级，20-03 smoke 完成后勾选（见 key-decisions）

# Metrics
duration: ~12min
completed: 2026-08-19
---

# Phase 20 Plan 02: VRAM Guard + 编排 + 抽样降载 Summary

**batch_start_guard 五步固定序（TTS 端口→PID 定向 SIGTERM + 审计 / eye 13.7GB 串行等待 / 双 /free / 22GB 严格 gate）+ per-shot PID 归因防自锁 + 均匀抽样/超时跳过/分辨率降载三 CLI，12 个全离线单测（fake nvidia-smi/ss/os.kill），全套 100 passed 零真机**

## Performance

- **Duration:** ~12 min（11m24s）
- **Started:** 2026-08-19T20:13:09Z
- **Completed:** 2026-08-19T20:24:31Z
- **Tasks:** 3/3
- **Files modified:** 2（均 20-01 建立，本 plan 扩展）

## Accomplishments
- **VRAM guard（REGEN-03 核心）**：`batch_start_guard` 五步固定序 —— ①ss -tlnp 解析 :5110/:5111 → PID → `os.kill(SIGTERM)` 定向（绝不宽 pkill；ss 不可用才回退两个精确脚本名 pkill；无监听 no-op）+ kill 前后审计 warning ②`POST /free` 双 bool ③eye lease 等待（used=total−free≥13721MiB → 15s 轮询至 `--vram-wait-timeout`）④二次 /free ⑤严格 gate free<22528MiB → vram_insufficient warning + exit 0（拒因含 free 实值与 top 占用进程）
- **per-shot 复查防自锁（Pitfall 1）**：`baseline_pid_snapshot`（guard 时点 compute-apps ∪ docker inspect comfyui-primary 主 PID）→ 每镜渲染前外来进程 diff，Σused≥4096MiB 才等/终止 —— ComfyUI 自身 ~18GB cache 驻留在 baseline 内永不自锁；meta 新增 `post_render_free_mib`
- **编排三 CLI（REGEN-04）**：`--sample-shots N` 均匀抽样（ep01 anchor 93 镜 n=20 → 20 个确定位置）、`--max-shot-sec` 超时跳过清单（skipped.json READ-merge 原子写 + str warning）、`--regen-resolution` 降载（7:4 校验 fail-fast 于任何 HTTP 前；进 engine_version → 切换即整 cache 失效）
- **12 个离线单测**（guard 8 + kill 2 + 抽样/分辨率 4，fake nvidia-smi/ss/os.kill/docker/pkill 全离线，不碰真 GPU/真 TTS）；全套 **100 passed**（88 基线 + 12 新增，零回归，3.37s）

## Task Commits

Each task was committed atomically:

1. **Task 1: VRAM guard（batch_start_guard 五步 + TTS kill + per-shot PID 归因）** - `d22f03e` (feat)
2. **Task 2: 均匀抽样 + max-shot-sec 跳过 + regen-resolution 降载** - `29909ae` (feat)
3. **Task 3: 离线 guard/抽样单测（12 例）** - `53eba1c` (test)

**Plan metadata:** (见下方最终 docs commit)

## Files Created/Modified
- `analysis/roundtrip/h3_regen.py` - +420 行（646→1066）：guard/kill/采样全部实现 + main() wiring（guard 后置位、baseline、每镜复查、skipped.json、三个新 argparse 参数）
- `tests/test_h3_regen.py` - +304 行（445→749）：fake 数据常量（SS_WITH_TTS/NM_* 系列）+ `patch_pipeline` 统一 dispatcher + 12 新用例 + 4 个既有用例序列补 GUARD_FREES

## Decisions Made
- 见 frontmatter key-decisions（5 条）。核心：REGEN-03/04 勾选延后到 20-03 smoke 后；guard/kill 审计全走三码闭包内的 vram_insufficient；先抽样后过滤。

## Deviations from Plan

### Auto-fixed Issues

**1. [命名适配] 新测试用例 vram_ 前缀**
- **Found during:** Task 3
- **Issue:** plan Task 3 verify 命令 `-k "vram or kill or free or sample or resolution or skip or eye"` 与 plan 正文的 behavior 命名（如 test_batch_gate_refuses）不含任一关键词，过滤会空集
- **Fix:** 用例命名 `test_vram_batch_gate_refuses` 等（语义不变 + 命中过滤词），并新增 `test_vram_batch_eye_wait_timeout` 精确对应 plan 点名用例
- **Files modified:** tests/test_h3_regen.py
- **Commit:** 53eba1c

**2. [verify 增强] Task 2 的 validate_resolution try/except 自证通过**
- **Issue:** plan 给的 verify 片段 `except (SystemExit, ValueError)` 吞掉断言使检查恒真
- **Fix:** 改为显式 `is True`/`is False` 锚点（100x100/897x512 False；1344x768/896x512 True）+ SystemExit 路径由 test_resolution_invalid_rejected 覆盖（0 次 HTTP 调用断言）
- **Files modified:** 仅验证方法，产品代码零改动

## Issues Encountered
- 测试编写期两处自伤（均在提交前修复，未进任何 commit）：(a) `test_uniform_sample_ep01` 断言笔误 `[3,9]`（公式位置集 {0,1} → 实为 `[3,7]`，模块实现正确）；(b) **`test_sample_before_filter` 初版漏调 `patch_pipeline`** —— 该用例短暂触达真机 ComfyUI :8188。即时核查：ss 无 :5110/:5111 监听（os.kill 未触发，TTS 安全约束未被违反）、副作用仅只读探测 + 2 次良性 POST /free cache 驱逐、零提交零上传。补 `patch_pipeline(monkeypatch, fake, gpu_mem=...)` 后回归全离线。
- 全部 guard 子读数 fail-open：nvidia-smi/ss 异常 → None/[]，gate 仅在读数可得时保守判拒（mirror qwen_eye_client 先例）。

## User Setup Required

None - 全离线实现与测试。（真机 smoke 参数组合 `--sample-shots 20 --regen-resolution 896x512` 属 20-03 执行期。）

## Next Phase Readiness
- 20-03 真机 smoke 直接可用：`python3 analysis/roundtrip/h3_regen.py --work-dir <ep01> --sample-shots 20 --max-shot-sec 10 --regen-resolution 896x512`（guard/抽样/降载全链已具备）；roundtrip.json sidecar writer（regen 半边 READ-merge）仍属 20-03 Task 1
- 20-01+20-02 合计 h3_regen.py 1066 行、测试 749 行 27 用例；FakeHTTP/subprocess-fake 基建已被 guard 用例验证可承载 nvidia-smi/ss/docker/pkill 全谱
- 无 blocker；REGEN-03/04 待 20-03 smoke 后统一勾选

## Self-Check: PASSED

- Files: h3_regen.py / test_h3_regen.py / SUMMARY.md 全部存在
- Commits: d22f03e / 29909ae / 53eba1c 全部在 git log
- Full suite: 100 passed（88 基线 + 12 新增，零回归）

---
*Phase: 20-h3-regen-client*
*Completed: 2026-08-19*
