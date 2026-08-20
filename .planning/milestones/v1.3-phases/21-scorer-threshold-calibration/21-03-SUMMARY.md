---
phase: 21-scorer-threshold-calibration
plan: "03"
subsystem: testing
tags: [siglip, threshold-calibration, qwen-eye, judge, midframe-sim, verdict, checkpoint, 1344x768]

# Dependency graph
requires:
  - phase: 21-scorer-threshold-calibration (21-02)
    provides: overnight 批 19 镜 @1344×768 regen 产物 + pidfile/log 交接块 + 896×512 对照数据点
  - phase: 21-scorer-threshold-calibration (21-01)
    provides: scorer.py/judge.py CLI 面（--summarize/--apply-verdict）+ 157 pytest 基线
provides:
  - 19 镜 @1344×768 双信号全量实测分布（schema 0 errors，校准集纯度断言过）
  - 校准报告 DRAFT（分位数表 + 三桶 + τ 全值预演 + per-position 分布 + 抽检 5 镜素材）
  - parse_judge_answer 末尾 } 截断修复（b43aa19，TDD 3 用例，160 pytest）
affects: [21-03 Task 3 continuation, 22 Dataset Export + HITL 面板]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "分位数关键档 + faithful 桶间隙双轴呈现 τ 候选（最大间隙 0.9358→0.9670 显式标注）"
    - "抽检 5 镜确定性 stratified 规则代码化进报告 §5.1（空桶顺延次低镜，不临场挑）"
    - "截断修复模式：{ 开头无 } 收尾补一个 } 再解析——只补括号不放松语义校验"

key-files:
  created:
    - .planning/research/roundtrip-threshold-calibration.md
    - .planning/research/roundtrip-calibration-scatter.png
  modified:
    - analysis/roundtrip/judge.py（parse_judge_answer 截断修复）
    - tests/test_judge.py（+3 用例）

key-decisions:
  - "shot 19 三连 no-brace 根因 = 引擎在 。\" 后提前 EOS 吃掉闭括号 —— 传输层截断而非判定内容问题，Rule 1 TDD 修复（b43aa19）；判定语义零改动"
  - "区分度不足如实呈现：两桶 sim 重叠 0.9011-0.9780（最高分镜 80=diverged、最低分镜 47=faithful），三处置选项进报告 §6.2 由 Kai 裁决——不静默调参（T-21-11 兑现）"
  - "prompt_underspecified 空桶（0/19）如实记录——judge 全部归因模型执行；是否 judge 偏好属抽检 5 镜人裁区"
  - "STATE/ROADMAP 不做 advance/complete 类更新（checkpoint 暂停非收口）——Task 3 continuation 后统一收口"

requirements-completed: []  # SCORE-03/DATASET-01 待 Task 3（Kai 裁决后 --apply-verdict + 审计表落档）

# Metrics
duration: ~30m（Task 1 + checkpoint 材料；Task 3 continuation 另计）
completed: 2026-08-20（checkpoint 暂停于 Task 2）
---

# Phase 21 Plan 03: 校准批收口 Summary（FINAL —— Task 2 暂停）

**19 镜 @1344×768 双信号全量烧录 + 校准报告 DRAFT（分位数/三桶/τ 预演/per-position）——暂停于 Task 2 blocking checkpoint：τ_sim 裁决 + 抽检 5 镜归因待 Kai（机器不代裁，SCORE-03 HITL 硬门）**

> **状态：PAUSED at Task 2/3。** Task 1 完成并已 commit；Task 2 为 checkpoint:human-verify
> (gate=blocking)——等待 Kai 回复 `tau=<float>` + 抽检结论；Task 3（--apply-verdict + 幂等证明
> + PROJECT.md 决策行 + 报告 FINAL）**未启动**，由 continuation agent 在裁决后执行。

## Performance

- **Duration:** ~30m（2026-08-20T01:42Z–02:12Z；Task 1 全量双信号 + 报告草稿 + 截断修复）
- **Tasks:** 1/3 完成（Task 2 = checkpoint 待人工；Task 3 未启动）
- **Files modified:** 4（报告 + 散点 PNG 新建；judge.py + test_judge.py 修复性修改）
- **Commits:** `b43aa19`（fix：截断修复 TDD）+ `1132bfd`（feat：报告 DRAFT + 散点）+ 本 docs commit

## Task 1 成果（批完成确认 + 19 镜全量双信号 + 分布材料 + 报告草稿）

- **批验收（21-02 交接块）：** PID 4112729 死亡 + 收尾行齐（rendered=19 cache-hit=0 failed=0
  sampled=20 skipped=1）+ 19 mp4 在盘 + sidecar 19 条 regen 半边全 1344x768——dead-with-full-artifacts 路径
- **scorer 全量：** 1m19s（GPU0，19 miss→19 分，SigLIP fp16 离线加载）；**judge 全量：** 2m30s
  （GPU1，18 judged + shot 19 截断修复后 5.9s 补齐）
- **双信号分布：** sim p10=0.9005 / p25=0.9143 / **p50=0.9457** / p75=0.9678 / p90=0.9741，
  span 0.8382-0.9828（stdev 0.0372）；attribution 三桶 faithful=10 / diverged=9 /
  **underspecified=0（空桶）**
- **关键观察（如实呈现）：** 两桶 sim 重叠 0.9011-0.9780 覆盖 17/19 镜；全量最高分镜（80，
  0.9828）model_diverged、最低分镜（47，0.8382）prompt_faithful——sim 单信号与归因弱耦合，
  区分度不足处置三选项（accept-with-caveat / 调 N·窗口·特征层 / 宽容 τ）进报告 §6.2 供裁决
- **报告草稿：** `.planning/research/roundtrip-threshold-calibration.md`（七节 254 行，status
  DRAFT）+ 散点 PNG（Noto Sans CJK）；τ 全值预演表（21 档）+ faithful 桶最大间隙
  0.9358→0.9670 显式标注；896×512 对照数据点收录（shot 1: 0.9309→0.9351、shot 47:
  0.8396→0.8382——分辨率切换分数稳定）
- **抽检 5 镜（确定性 stratified 规则，代码进报告 §5.1）：** 61（faithful-max）/ 47（faithful-min）/
  14（diverged-median）/ 52（空桶顺延·全量次低）/ 19（global-median）——grid 绝对路径 +
  原片时窗 + reason 引擎原文摘录全在报告 §5.2
- **Reproducibility：** cache 全命中重跑 scorer 0.184s / judge 0.103s（秒级证明留档报告 §7.2）；
  roundtrip.json 裁决前 sha256 = `84b5d24453609b4e05cbe744b28e46f91b92f7dbec2a706409fcb5cb1b34c3fe`
- **机器断言全过：** 19 条双半边 + `_iter_sidecar_errors` 0 errors + engine_version 全 1344x768 +
  报告 ≥120 行七 token 断言 + pytest **160 passed**（157 基线 + 3 新）

## Task Commits

1. **Task 1a（Rule 1 deviation 内嵌）: parse_judge_answer 截断修复** - `b43aa19` (fix)
2. **Task 1: 19 镜双信号全量 + 校准报告 DRAFT** - `1132bfd` (feat)
3. **Plan metadata（本 FINAL SUMMARY + STATE）** - 见下方最终 docs commit

## CHECKPOINT（Task 2 —— 待 Kai）

| 项 | 内容 |
|----|------|
| **裁决材料** | `.planning/research/roundtrip-threshold-calibration.md`（DRAFT）——重点 §4 观察两桶重叠 / §6.1 τ 预演表 / §6.2 三选项 / §5.2 抽检 5 镜 |
| **τ_sim 裁决** | 从 §6.1 选值 + 一句理由（或选 §6.2 选项 2/3 注明参数） |
| **抽检（SC3）** | §5.2 五镜逐一开 grid 图自判归因 vs judge 归因，记 agree/disagree（≥4/5 可接受；不一致不返工只记录） |
| **grid 路径** | `<EP01>/roundtrip/_judge_grids/shot_{061,047,014,052,019}.jpg`（EP01 前缀见报告 §5.2；1370×1476，左 ORIGINAL 右 REGEN） |
| **resume-signal** | 回复：`tau=<float>`；抽检=`<approved 或不一致镜号+正确归因>`；选了选项 2/3 注明选项号 |
| **Task 3 将做** | --apply-verdict --tau-sim <τ> + 幂等 sha256 双值 + PROJECT.md Key Decisions 行 + 报告 FINAL + rejected 分桶审计表 |

**（Task 3 落档项的占位——裁决后回填本 SUMMARY 或由 continuation 记录：τ 锁定值 / checkpoint
回复原文 / accepted-rejected 计数与分桶 / 幂等 sha256 双值。）**

## Files Created/Modified

- `.planning/research/roundtrip-threshold-calibration.md` - 校准报告 DRAFT（七节：元数据/烧录实录/Methodology+反循环论证声明/机器可见观察/Evidence/裁决候选/Reproducibility）
- `.planning/research/roundtrip-calibration-scatter.png` - 双信号散点（x=sim、y=attribution 抖动、p50/p25 参考线、镜号标注）
- `analysis/roundtrip/judge.py` - parse_judge_answer 末尾 `}` 截断修复（Rule 1）
- `tests/test_judge.py` - +3 用例（截断修复/不掩盖坏 JSON/校验仍生效）
- output/ 运行产物（gitignored by design）：roundtrip.json 双半边 + scorer/judge cache ×19 + grids ×19 + frames

## Decisions Made

- **shot 19 截断按 Rule 1 TDD 修复而非绕过**：根因字节级定位（raw 以 `"` 收尾、`{` 开头）；
  修复只补括号不放松语义校验；probe 证实引擎判定内容本身一致（model_diverged「闭眼」未执行）
- **空桶顺延规则定为「全量 sim 次低镜」**（prompt_underspecified=0/19）：低分段是欠约束类
  典型栖息区，规则代码先于结果固定进报告 §5.1
- **checkpoint 暂停不推进 STATE 计数**：state.advance-plan / roadmap update / requirements
  mark-complete 全部留给 Task 3 收口（避免 3/3 假完成态）；本 SUMMARY 明确 PAUSED 标注

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] parse_judge_answer 末尾 `}` 截断修复（shot 19 三连 no-brace）**
- **Found during:** Task 1 步骤 3（全量 judge：18/19，shot 19 三答 no-brace，重跑仍三连）
- **Issue:** 引擎在 `。"` 后提前 EOS，闭括号被 token 截断——`\{.*\}` 无匹配落 no-brace，
  retry-with-feedback 也拿不到 `}`；shot 52 的 [no-brace→ok] 证明一次性截断可自然恢复，
  shot 19 是 ~2/3+ 截断率的极端个例（19 镜中唯一）
- **Fix:** `{` 开头却无 `}` 收尾的文本补一个 `}` 再解析；真坏 JSON 仍落 json: 码进重问路径
- **Files modified:** analysis/roundtrip/judge.py + tests/test_judge.py（+3 用例）
- **Verification:** TDD RED（3 failed）→ GREEN（30/30 judge 用例）；全套件 160 passed 零回归；
  shot 19 修复后 judged model_diverged conf=0.9，reason 与修复前 probe 引擎原文一致
- **Committed in:** b43aa19

**2. [Rule 1 - Bug] 成功重跑后的 stale warning 残留清除**
- **Found during:** Task 1 步骤 3（shot 19 补齐后 warnings.json 仍载「judge failed shots: [19]」）
- **Issue:** judge.py 仅在 pending_warnings 非空时调 append_roundtrip_warnings——成功轮无
  pending 则不触发 strip，上一轮失败 warning 永久残留（审计面失真）
- **Fix:** 经既有 strip 语义清障（append_roundtrip_warnings(work_dir, [])，零代码变更）；
  judge.py 的「成功轮也应 strip」留作后续小改进不入本 plan scope
- **Files modified:** 无代码（route_cache/warnings.json 数据修正为 []）
- **Verification:** warnings.json = {"warnings": []}；shot 19 judge 分在 sidecar
- **Committed in:** 无需 commit（gitignored 运行产物）

---

**Total deviations:** 2 auto-fixed（2 Rule 1 bug）
**Impact on plan:** 均为正确性必需（解析器传输层截断 / 审计面失真），判定语义与校准数据零改动，无 scope creep。

## Issues Encountered

- judge 首轮全量 shot 19 三连 no-brace（根因与修复见 deviation 1）；另 ComfyUI 批后 GPU1
  驻留 18GB 由 judge.py 自带 comfy_free 正常处置，无需干预

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - 无占位实现。报告 §6.3/§6.4 与本 SUMMARY 的「裁决后回填」占位是 checkpoint 流程设计
（DRAFT→FINAL 生命周期），非实现 stub；Task 3 continuation 收口。

## Next Phase Readiness

- **Task 3 continuation 输入：** Kai 的 `tau=<float>` + 抽检结论 → `--apply-verdict --tau-sim <τ>` →
  幂等证明（对照本 SUMMARY 记录的裁决前 sha256）→ PROJECT.md Key Decisions 行 → 报告 FINAL
- **Phase 22 素材就绪度：** 19 镜双信号已在 sidecar（schema 合法）；verdict 半边待 Task 3；
  grid 图 ×19 + reason 留档（HITL 面板素材）
- **阻塞点：** 无技术阻塞——纯人工裁决门

## Self-Check: PASSED

- 文件存在：.planning/research/roundtrip-threshold-calibration.md + roundtrip-calibration-scatter.png FOUND（本会话直读）
- commit 存在：b43aa19 / 1132bfd FOUND（git log 直读）
- 机器断言：19 双半边 + schema 0 errors + 1344x768 纯度 + 报告 ≥120 行全过；pytest 160 passed
- checkpoint 状态：Task 3 未启动（无 verdict 写入、PROJECT.md 未动、报告仍 DRAFT）——已核实

---
*Phase: 21-scorer-threshold-calibration*
*Status: PAUSED at Task 2 checkpoint —— 2026-08-20（待 Kai 裁决后 Task 3 continuation）*

---

## Final Close-out（continuation 由 429 中断后 orchestrator 收尾，2026-08-20）

- verdict 应用：accepted=4（shot 10/61/75/84，#84 恰在 τ=0.9670 边界 ≥ 含）/ rejected=15（faithful<τ=6 + diverged=9 + underspecified=0）/ source 全 auto
- 幂等证明（SC5）：apply 二跑 `applied=0 frozen=19`，roundtrip.json sha256 字节级相同（63543baf…336dd73）
- 校准报告 FINAL（§6.3 裁决记录 + rejected 分桶审计）
- PROJECT.md Key Decisions 行已加（line 150）
- REQUIREMENTS SCORE-01/02/03 + DATASET-01 → Complete
- 注：Task 3 应用器本体在 429 中断前已由 executor 执行（verdict 已在盘）；文档收尾五步由 orchestrator 完成
