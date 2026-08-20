---
phase: 22-dataset-export-integration
plan: 03
subsystem: pipeline-orchestration
tags: [step-roundtrip, banner-renumber, pattern4-conditional-input, dataset-post-step, pipe-01, tau-sim-default, wr-01-force-redline]

requires:
  - phase: 20-h3-regen-client
    provides: analysis/roundtrip/h3_regen.py CLI（fl2va regen + 4-tuple cache + 批前 guard + graceful-degrade）
  - phase: 21-scorer-threshold
    provides: scorer.py / judge.py CLI + τ_sim=0.9670 Kai 裁决锁定值
  - phase: 22-dataset-export-integration/22-01
    provides: html/gen_roundtrip_review.py 审阅面板生成器（六 flag CLI）
  - phase: 22-dataset-export-integration/22-02
    provides: analysis/roundtrip/export_dataset.py + apply_edits.py CLI（dataset post-step 编排对象）
provides:
  - run_pipeline step_roundtrip 编号 step [9/10]（外层 mtime+video-stamp cache 短路 + h3_regen→scorer→judge→gen_review 四 subprocess 串）
  - 六 CLI flag 全透传（--skip-roundtrip / --comfy-url / --sample-shots / --regen-resolution / --max-shot-sec / --tau-sim 默认 0.9670）
  - banner [N/9]→[N/10] 重编号（27 字面量 + 2 散文 + docstring，grep '/9]' 零存活）
  - Pattern 4：step_export mtime inputs 条件性 append roundtrip.json（陈旧 asset.json cache-hit 修补）
  - dataset 导出 plain-label post-step + roundtrip HITL hint
  - tests/test_pipeline_roundtrip_wiring.py 五测静态锁（SC1 代码半边机器证明）
affects: [22-04 e2e harness（全部管线侧前置就绪——ep01 live 证明 + 四场景 harness）]

tech-stack:
  added: []  # 零新增依赖（纯编排层：subprocess list-form argv + os.path mtime cache）
  patterns:
    - "外层 mtime+video-stamp cache 短路整条 subprocess 链（mirror step_reid :290-307；连带跳过 h3_regen 批前 guard 的 TTS kill /free eye-wait 副作用）"
    - "条件性 mtime input append（存在才进 inputs——缺席保 byte-identical-absent，绝不无条件 append 防 +inf 永久 miss）"
    - "post-step graceful-degrade 自写 check=False + OSError 双防线（NOT run_step——keyed-on-file 而非 CLI flag）"

key-files:
  created:
    - tests/test_pipeline_roundtrip_wiring.py
  modified:
    - run_pipeline.py
    - tests/test_pipeline_vision_wiring.py
    - tests/test_pipeline_vision_seq_wiring.py
    - tests/test_canvas_import.py

key-decisions:
  - "PIPE-01 保持未勾选 —— 编排半边（step_roundtrip + flags + 重编号 + Pattern 4 + post-step 五件套）已交付，ep01 live 证明在 22-04 共享同 requirement ID（mirror 18-01/19-01/20-01/21-01/22-01/22-02 半边交付先例）"
  - "judge --tau-sim pipeline 总是显式透传（默认 0.9670）—— 不改 judge 的 standalone 显式安全门（default=None + apply 无 τ sys.exit）；scorer 不透传 --device（cuda:0=3060Ti 零竞争分卡红线）"
  - "cache 命中路径仍补生成 review HTML（A2：纯 Python 毫秒级，HTML 是新文件可能尚未生成——ep01 首跑 e2e 正是此态）"
  - "--force 清单零改动（WR-01 红线）——注释理由改述为 verdict/scores 冻结人工数据；route_cache rmtree 已覆盖三模块 cache"

patterns-established:
  - "重编号波及面按「锁点」而不只按「字面量」清点：grep 形态锁（vision/seq regex）+ 前瞻幻影锁（canvas '[10/' not in）都要同 commit 前移"

requirements-completed: []  # PIPE-01 编排半边交付，22-04 e2e live 证明后勾选

duration: 8min
completed: 2026-08-20
---

# Phase 22 Plan 03: run_pipeline wiring（step_roundtrip 编号 step）Summary

**PIPE-01 落地：step_roundtrip 成为编号 step [9/10]（timeline 与 export 之间）——外层 mtime+video-stamp cache 短路 + 四 subprocess 串（judge --tau-sim 总是显式）+ 六 flag 全透传（τ_sim=0.9670 进默认）+ banner [N/10] 重编号零存活 + Pattern 4 条件挂载修补 + dataset post-step，220 pytest 零回归。**

## Performance

- **Duration:** ~8 min（04:55:44Z → 05:03:07Z）
- **Started:** 2026-08-20T04:55:44Z
- **Completed:** 2026-08-20T05:03:07Z
- **Tasks:** 2/2
- **Files modified:** 5（1 新测试 + 4 改）

## Accomplishments

- **step_roundtrip 编排五件套齐**（PIPE-01 / SC1 代码半边）：一条命令跑出 roundtrip.json + regen mp4 + scores/verdict + review HTML + dataset 目录的全链管线侧前置就绪（ep01 live 证明在 22-04）
- **外层 cache 短路整个 subprocess 链**：mtime 三条件（rt > shots ∧ rt > prompts ∧ video-stamp 匹配）命中时跳过 h3_regen/scorer/judge 全部子进程——连带跳过 h3_regen 批前 guard 的 TTS kill + POST /free + eye-wait（最长 1800s 阻塞，T-22-13）——但仍补生成 review HTML（A2 毫秒级）
- **反模式全避开**（success_criteria 逐条）：scorer argv 无 --device（wiring 测试锁死）；judge --tau-sim 无条件显式；Pattern 4 os.path.exists 守卫（非无条件 append）；post-step 自写 check=False（非 run_step）；--force 清单 byte-identical

## banner 重编号前后计数（plan output 要求）

| 项 | 前 | 后 |
|----|----|----|
| `/9]` 行存活（grep -c） | 29（27 字面量 + 2 散文 :35/:921） | **0** |
| `[N/10]` 总数（regex `\[\d+/10\]`） | — | **34** |
| 分布 | `[1..5/9]`×3 + `[6/9]`×4 + `[7/9]`×3 + `[8/9]`×2 + `[9/9]`×3 | `[1..5/10]`×3 + `[6/10]`×4 + `[7/10]`×3 + `[8/10]`×2 + **`[9/10]`×7**（新 step：skip/cached/regen/scoring/judge/review-HTML/降级）+ **`[10/10]`×3**（export） |
| docstring 步骤清单 | 9 步 + canvas post-step "10." | roundtrip=9 / export=10 / canvas "10.5" / dataset post-step 新条目 |
| 两锚 | — | `[9/10] roundtrip` ✓ / `[10/10] ShotTimelineAsset export` ✓ |

## step_roundtrip 源码索引窗（plan output 要求）

- **定义窗**：`def step_roundtrip` **:570** ～ `def step_export` **:696**（step_timeline def :442 < roundtrip :570 < export :696 ✓）
- **main() 调用序**：`step_roundtrip(work_dir, video, shots, prompts_json, ...)` **:1090** < `step_export(work_dir, video, stems_source_dir, ...)` **:1096**
- 四 subprocess：h3_regen（cmd_regen list-form，--sample-shots>0 才透传）→ scorer（--work-dir only）→ judge（--apply-verdict + --tau-sim str(tau_sim) 显式）→ gen_roundtrip_review（`_gen_review_html()` 闭包，cache 命中/miss 两路径共用）
- 降级分支：h3_regen 后 `if not os.path.exists(rt_json)` → 打印 `[9/10]` 前缀降级说明 → 跳过 scorer/judge/HTML → return None

## Pattern 4 插入行号 + dataset post-step（plan output 要求）

- **Pattern 4**：run_pipeline.py **:724-730**（inputs 列表 :716-722 之后、`_safe_mtime` 计算 :732 之前）——`roundtrip_json_path = os.path.join(work_dir, "roundtrip.json")` :728 + `if os.path.exists(roundtrip_json_path): inputs.append(roundtrip_json_path)` :729-730，五行为注释（缺席→byte-identical-absent / 绝不无条件 append 的 rationale）
- **dataset post-step**：main() **:1135-1162**——`rt_json` :1139 keyed-on-file；缺席 → `[roundtrip-dataset] warning: roundtrip.json 不存在（step_roundtrip 被跳过/降级），跳过 dataset 导出`；在场 → export_dataset.py argv（--work-dir / --tau-sim str(args.tau_sim)；--dataset-root 走模块默认 = work_dir 同级 dataset/）+ 自写 check=False + OSError 双防线
- **HITL hint**：:1163-1171（mirror speaker-link :893-904）——roundtrip_review.html 在场时打印 apply_edits.py confirmed-only CLI 用法

## --force 清单 diff=0 证明（plan output 要求 / WR-01 红线）

regex 提取 `for p in (shots_json...):` 清单元组，`git show HEAD:run_pipeline.py`（Task 1 commit 后）与工作树（Task 2 改述后）逐字比对 → **identical: True**。改动仅 :937-945 注释块（Phase 20 三行理由改述为「verdict/scores 是冻结人工数据（human 覆盖唯一路径 = apply_edits.py confirmed-only CLI）；route_cache rmtree 已天然覆盖三模块 cache；--force 只清可重建的 cache/派生物」（T-22-10）。

## Task Commits

1. **Task 1: 六 flag + step_roundtrip 编号 step + banner 重编号 + 既有 wiring 测试同步** — `2058412` (feat)
2. **Task 2: step_export 条件性 roundtrip input（Pattern 4）+ dataset post-step + 新 wiring 测试** — `7ab3482` (feat)

## Files Created/Modified

- `run_pipeline.py` — step_roundtrip 函数（:570-694）+ 六 argparse flag + main 调用 :1090 + Pattern 4 :724-730 + dataset post-step :1135-1162 + HITL hint + banner 34 处 [N/10] + docstring 三段同步
- `tests/test_pipeline_roundtrip_wiring.py` — 新 182 行五测（help / defaults spy / step wiring 静态 / Pattern 4+post-step 锁 / banner 计数）
- `tests/test_pipeline_vision_wiring.py` — regex `\[\d/9\]`→`\[\d+/10\]` + `[5.5/10]`/`[6/10` 子串锁
- `tests/test_pipeline_vision_seq_wiring.py` — 同上 + `[5.6/10]` 锁
- `tests/test_canvas_import.py` — `[10/` 幻影锁前移 `[11/`（见 Deviations #1）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan bug] 重编号波及面漏列第三处锁：test_canvas_import.py:222 `[10/` 幻影锁**
- **Found during:** Task 1 全套件回归（215 → 1 failed）
- **Issue:** canvas 测试断言 `assert "[10/" not in src`——写于 9 步时代，锁「canvas post-step banner 绝不占用下一个未用编号 10」；重编号后 export 合法占用 `[10/10]`，断言误红。plan/PATTERNS 波及面清单（27 字面量 + 2 散文 + 2 wiring 测试）漏列此前瞻锁
- **Fix:** 锁点前移 `assert "[11/" not in src`（10 步时代的下一个未用号 = 11），语义不变：canvas post-step banner 永不带数字前缀；docstring 同步说明
- **Files modified:** tests/test_canvas_import.py
- **Commit:** 2058412（随 Task 1 同 commit，保住「重编号 + 测试锁同步」原子性）

**2. [Rule 3 - Verify 澄清] plan verify 的 `--help | grep -c ... == 6` 实测 10**
- **Found during:** Task 1 verify
- **Issue:** argparse 自动生成的 usage 块（help 输出前部）也列出六 flag（4 行）+ 六 flag 定义行 = 10 匹配行；plan 假定只匹配 6 行
- **Fix:** 无代码改动——六 flag 全部在 --help 的意图完全满足（6 定义行逐一在场）；SUMMARY 记录此 verify 措辞与实际的差异，新 wiring 测试改用逐 flag `in stdout` 断言（不受 usage 块影响）

### Plan 语义澄清（非偏差）

- 新 wiring 测试五测而非 plan 写的「四测」：静态 wiring 拆成 step-roundtrip 窗口与 Pattern 4/post-step 两测（四测覆盖域完整保留 + 逐域独立失败信息）——superset，非缩水

## Test Evidence

- `python3 -m pytest tests/test_pipeline_roundtrip_wiring.py -x -q` → **5 passed**
- `python3 -m pytest tests/test_pipeline_vision_wiring.py tests/test_pipeline_vision_seq_wiring.py -q` → **8 passed**
- `python3 -m pytest tests/ -q` → **220 passed**（基线 215 + 新增 5，零回归；含 canvas 锁前移后恢复绿）
- `grep -c "/9\]" run_pipeline.py` → **0**；两锚 `[9/10] roundtrip` / `[10/10] ShotTimelineAsset export` 在场
- `--force` 清单元组 git 比对 → **identical: True**（WR-01）

## Self-Check: PASSED

文件（5/5 FOUND）：run_pipeline.py / tests/test_pipeline_roundtrip_wiring.py / tests/test_pipeline_vision_wiring.py / tests/test_pipeline_vision_seq_wiring.py / tests/test_canvas_import.py；commits（2/2 FOUND）：2058412 / 7ab3482。
