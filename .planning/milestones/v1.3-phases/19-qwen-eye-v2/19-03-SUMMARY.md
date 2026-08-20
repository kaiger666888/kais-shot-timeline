---
phase: 19-qwen-eye-v2
plan: "03"
subsystem: pipeline-wiring
tags: [qwen-eye, vision-seq, run-pipeline, pre-step, wiring, sc1, sc4, evidence]
requires:
  - "19-01: analysis/vision_seq_facets.py 模块（CLI + 双信封 cache + 三策略归并）"
  - "19-02: 合并策略锁定 temporal = MERGE_STRATEGY_DEFAULT + sandbox route_cache（零重烧证据）+ build_sandbox --reset 语义"
provides:
  - "run_pipeline 无编号 pre-step 5.6 挂载（local_vision 后 step_reid 前）+ --vision-seq/--no-vision-seq/--no-ear 三 flag"
  - "tests/test_pipeline_vision_seq_wiring.py 四件套机器锁（顺序/flag 语义/banner plain-label/ear 直通）"
  - "SC1 全量收口：sandbox 置空六镜经默认策略填充（diff 可见）+ live ep01 sha256 负测试（byte-identical）"
  - "SC4 全量收口：cache 命中重跑 0.968s/0.939s 秒级 + 零引擎启动（wiring 形态复证）"
  - "VISION-01/VISION-02 收口（模块+spike+wiring 三半边齐）"
affects:
  - "20-h3-regen（消费 prompts.json 升级后的 action/camera facets）"
  - "21-scorer（同上——round-trip 上游输入质量提升）"
tech-stack:
  added: []   # 零新 pip 依赖 / 零新引擎 / 零模型下载（SC4 硬约束维持）
  patterns:
    - "无编号 pre-step 挂载三连（5.5 local_vision → 5.6 vision_seq → step_reid）：条件四连 + subprocess 按路径 + plain-label banner，step counter 恒不 bump"
    - "负测试证据链：live sha256 前后等值 + scratch work-dir 零写入 + git status output/ 为空（三重隔离证明）"
key-files:
  created:
    - tests/test_pipeline_vision_seq_wiring.py
    - spike/vision_seq/results/sc1_evidence.txt
  modified:
    - run_pipeline.py
    - .planning/research/vision-seq-spike-report.md
    - spike/vision_seq/sandbox/prompts.json
decisions:
  - "--reset 显式 --target sandbox（不用默认 both）：sandbox_ear 的 ear_on 证据状态原样保留 —— plan 括号明示「重置 sandbox 六镜 facets」，both 会把 sandbox_ear 置空后不再回填"
  - "TDD RED→GREEN 在本 plan 任务序（Task 1 先交付 wiring、Task 2 后置测试）下结构上不可分离 —— mirror 19-01 Task 3 先例，测试首跑即绿（4/4）"
  - "sandbox 重跑 argv 恒传 --audio-semantic + --no-ear（mirror wiring 形态而非最小 CLI）—— 生产路径形态的证据才是本 plan 要的半边"
metrics:
  duration: "~21m"
  completed: 2026-08-19
---

# Phase 19 Plan 03: pipeline wiring + SC1/SC4 集成证据 Summary

**run_pipeline 挂载无编号 pre-step 5.6（--vision-seq/--no-vision-seq/--no-ear 三 flag，5.5 后 step_reid 前，banner plain-label 不 bump step counter）+ wiring 四件套机器锁（62 tests 零回归）；SC1/SC4 wiring 形态收口：sandbox 六镜默认策略 temporal 填充 diff 可见、live sha256 前后等值负测试、cache 命中 0.968s/0.939s 秒级零引擎重跑，全部落 sc1_evidence.txt + 报告新节**

## Performance

- **Duration:** ~21 min（2026-08-19T18:26:39Z → ~18:47Z）
- **Tasks:** 3/3
- **Files modified:** 5（run_pipeline.py + 新测试 + 报告 + 证据文件 + sandbox prompts.json）
- **Tests:** 58 → 62 passed（+4 wiring 新测，v1 全套零回归）

## Accomplishments

- **Task 1（642c78e）**：argparse 加 `--vision-seq`/`--no-vision-seq`（dest=vision_seq 双 flag，默认启用）+ `--no-ear`；main() 体在 5.5 块后、`# 6. 跨镜 re-id` 前插 5.6 块——条件四连（vision_seq ∧ ¬skip_semantic ∧ prompts.json 在 ∧ frames_5fps 在）+ subprocess 按路径 + `run_step(cmd, "vision seq facets (qwen-eye v2 pre-step)")` plain label；`--audio-semantic` 引用 :736 `audio_semantic_json` 变量（存在性模块自判）；注释注明 ear 时序后果（5.6 在 step 7 前 → 首跑 ear 自动关零 warning，第二次管线跑才激活）；--force 段零改动仅加注释（route_cache 整目录 rmtree 天然覆盖 vision_seq/）。`grep -c vision_seq_facets.py == 1` 恰一处 subprocess 调用。
- **Task 2（e4e1bba）**：新建 tests/test_pipeline_vision_seq_wiring.py（102 行 ≥90）四件套 mirror v1 先例——--help 冒烟（三 flag 可见）/ argparse spy（_StopMain 短路：默认 vision_seq=True、no_ear=False，双 no-flag 翻转）/ 静态顺序锁（local_vision_facets.py < vision_seq_facets.py < step_reid 调用；`"--audio-semantic", audio_semantic_json` 在 5.6 cmd 构造内）/ banner 锁（v1 全部断言形态保留 + 新增 `[5.6/9] not in src`）。
- **Task 3（eb556a3）**：SC1/SC4 集成证据三组落档——(1) sandbox `--reset --target sandbox` 后默认策略重跑（不带 --merge-strategy → temporal，--no-ear 对齐 ear_off 信封，argv mirror wiring 形态恒传 --audio-semantic），六镜 action/camera 全填充，与 v1 现行值 diff 可见（逐帧「→」时序证据链 200-360 字 vs 单句概览 20-40 字）；(2) live ep01 负测试：`--work-dir /tmp/vision_seq_sc1_scratch` 运行前后 sha256 相等（`7cc4a484…ced5`，与 19-02 记录交叉验证），scratch 目录零写入、git status output/ 为空；(3) SC4 runtime：sandbox 重填 0.968s / live 93 镜扫描 0.939s，输出无任何引擎 banner（预判生命周期零实例化）。报告追加「SC1/SC4 集成证据（post-wiring）」节 + sc1_evidence.txt 全文（133 行，含可复现命令原文）。

## Task Commits

| # | Task | Commit | 关键产物 |
|---|------|--------|----------|
| 1 | run_pipeline flags + pre-step 5.6 挂载 | `642c78e` | +40 行（三 flag + 5.6 块 + force 注释） |
| 2 | wiring 四件套测试 | `e4e1bba` | tests/test_pipeline_vision_seq_wiring.py（102 行，4 tests） |
| 3 | SC1/SC4 集成证据 | `eb556a3` | 报告新节 + sc1_evidence.txt + sandbox temporal 填充 |

**Plan metadata:** 本文件所在 commit（docs: complete plan）

## Files Created/Modified

- `run_pipeline.py` — argparse 三 flag（--no-subject 组后）+ 5.6 pre-step 块（5.5 与 step 6 之间）+ --force 段注释
- `tests/test_pipeline_vision_seq_wiring.py` — 新（四件套，全离线零 GPU 零网络）
- `.planning/research/vision-seq-spike-report.md` — 追加「SC1/SC4 集成证据（post-wiring）」节（含全部命令原文与哈希）
- `spike/vision_seq/results/sc1_evidence.txt` — 新（六镜填充前后并排 + live sha 双值 + SC4 计时表）
- `spike/vision_seq/sandbox/prompts.json` — 6 目标镜 ×2 facet（llm 填充值 → temporal 填充值；其余 87 镜 byte-identical，脚本断言）

## Decisions Made

（除 frontmatter decisions 外）
- 5.6 注释不写模块文件名（`vision_seq_facets.py` 全文件恰出现 1 次 = subprocess 调用行）—— 保 `grep -c == 1` 验收项与 v1 同款洁净度。
- live 负测试的 `--video` 用 live `h264.mp4`（sandbox video.mp4 symlink 同源）—— cache key 无所谓（scratch work-dir），仅需存在的视频文件算 hash。

## Deviations from Plan

**None — plan executed exactly as written.** 两处执行说明（非偏差）：

1. `build_sandbox.py --reset` 以 `--target sandbox` 显式执行（plan 括号原文「重置 sandbox 六镜 facets」；README 本就注明 `--reset [--target …] 供 19-03 复用`）。若用默认 both 会把 sandbox_ear 三镜也置空且不回填，销毁 ear_on 证据状态。
2. Task 2 `tdd="true"` 的 RED→GREEN 分离在 plan 任务序下结构上不可能（Task 1 先交付 wiring）—— mirror 19-01 Task 3 已记录的同类情况；测试首跑即绿 4/4，且静态断言对象（vision_seq_facets.py 字符串等）在 Task 1 之前不存在于源码，测试有效性自明。

## Auth Gates

None.（全离线；证据跑全 cache 命中零引擎，:8125 存活状态与本 plan 无关）

## Known Stubs

None.（5.6 块是真实 subprocess 挂载；sandbox audio_semantic.json 为 19-02 已声明的设计性 demo 输入，只在 sandbox，报告头部已声明）

## Threat Flags

None.（T-19-09 mitigate 落实：live sha256 负测试 + scratch 隔离 + 零修改短路；T-19-10 accept：argv 列表传参无 shell 拼接，flag 均为 argparse 布尔；T-19-11 mitigate：sc1_evidence.txt + 报告节含全部命令原文与哈希可独立复验。无计划外新攻击面。）

## 遗留与移交

- Phase 19 三 plan 全部完成：VISION-01/VISION-02 本 plan 收口（模块 19-01 + spike 锁定 19-02 + wiring 19-03 三半边齐，mirror 18-01 先例的共享 requirement 模式）。
- 下游（Phase 20 h3-regen / 21 scorer）消费升级后的 action/camera facets；ep01 live facets 保持 route 时代值（只填空缺语义，永不覆盖——本 plan 负测试再证）。
- 已知 deferred 不变：v1 --help latent bug（19-01 deferred-items）、audio-analysis 路由 unmerged、报告「机器可见观察」节模型层现象（主体漂移/字幕读入）属后续 phase 议题。

## Self-Check: PASSED

- 文件在位：run_pipeline.py（5.6 块 + 三 flag）、tests/test_pipeline_vision_seq_wiring.py（102 行）、sc1_evidence.txt（133 行）、报告新节（grep sha256 命中）。
- 提交在位：642c78e / e4e1bba / eb556a3 全部 `git log` 可查。
- `python3 -m pytest tests/ -q` → **62 passed**（基线 58 零回归）；`grep -c vision_seq_facets.py run_pipeline.py` == 1；`! grep '\[5.6/9\]'` 零命中。
- live sha256 可复验：`7cc4a4841e7f53975e5cd28e6399f66a21fb996f32414f80cb55efa32afaced5` 与 19-02 报告记录一致。
