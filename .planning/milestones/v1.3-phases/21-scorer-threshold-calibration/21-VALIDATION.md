---
phase: 21
slug: scorer-threshold-calibration
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-20
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（FakeSigLIP/FakeEye mock + 帧窗数学 + JSON 容错）+ GPU smoke（2 镜既有 regen 上真跑 scorer+judge）+ overnight 批（19 镜 @1344×768 ≈3-4.5h nohup） |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + `python3 spec/validate.py` |
| **Estimated runtime** | 离线 ~3s（基线 119 passed）；GPU smoke ~15-25min；overnight 批 3-4.5h（nohup 后台，不占 plan 上下文） |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + validate.py
- **Before `/gsd:verify-work`:** 全绿 + 校准报告 FINAL + 19 镜 roundtrip.json schema 合法 + verdict 幂等证明
- **Max feedback latency:** 离线 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-T1 scorer.py 模块 | 21-01 | 1 | SCORE-01 | T-21-02/04/05 | ffmpeg list-form；HF_HUB_OFFLINE 离线加载；帧清单进 cache（SC2 审计） | unit | py_compile + frame_ts/plan_frames 锚点 python -c（plan 内嵌） | tests/test_scorer.py（T3 建） | ⬜ pending |
| 21-01-T2 judge.py 模块 + 应用器 | 21-01 | 1 | SCORE-02, DATASET-01 | T-21-01/02/03 | reason [:2000] 截断；prompt_text 只进 HTTP body；grid 标签进图；冻结 merge | unit | py_compile + parse 矩阵/grid_ts clamp/CLI 面 python -c（plan 内嵌） | tests/test_judge.py（T3 建） | ⬜ pending |
| 21-01-T3 离线单测 | 21-01 | 1 | SCORE-01, SCORE-02, DATASET-01 | T-21-01/03 | 解析六码 / 布局像素断言 / 冻结幂等 / Pitfall 8 双向 | unit | `python3 -m pytest tests/test_scorer.py tests/test_judge.py -q && python3 -m pytest tests/ -q` | ✅（本 task 创建） | ⬜ pending |
| 21-02-T1 GPU smoke | 21-02 | 2 | SCORE-01, SCORE-02 | T-21-06/08 | GPU0 零竞争 + judge 前 /free；schema gate 复验 | manual+GPU | plan 内嵌 python -c（sidecar 双半边 + cache 清单 + schema 0 errors + grid 尺寸）+ 全套件 pytest | n/a（产物断言） | ⬜ pending |
| 21-02-T2 overnight 批启动 | 21-02 | 2 | SCORE-03（素材前提） | T-21-06/07 | guard 五步序过线 + pidfile 审计 | integration | plan 内嵌 bash（kill -0 + 日志守卫/抽样/渲染行断言） | n/a（日志断言） | ⬜ pending |
| 21-03-T1 全量双信号 + 报告草稿 | 21-03 | 3 | SCORE-03 | T-21-11 | 区分度不足如实呈现（不静默调参）；反循环论证声明 | integration+unit | plan 内嵌 python -c（19 条双半边 + engine_version 1344x768 + schema 0 errors + 报告 ≥120 行七节）+ 全套件 pytest | n/a | ⬜ pending |
| 21-03-T2 Kai 裁决 checkpoint | 21-03 | 3 | SCORE-02 (SC3), SCORE-03 (SC4) | T-21-09/11 | τ 人类裁决机器不代裁；抽检一致率 ≥4/5 | manual（blocking） | —（human-check；见 Manual-Only 表） | n/a | ⬜ pending |
| 21-03-T3 verdict 应用 + 审计 | 21-03 | 3 | SCORE-03, DATASET-01 | T-21-09/10 | 硬合取逐镜复算 + sha256 幂等 + rejected 分桶可 grep | integration | plan 内嵌 python -c（TAU_LOCKED env：19 verdict 判定复算 + /tmp/rt_a==rt_b + FINAL 报告 + PROJECT.md 行）+ 全套件 pytest | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（SigLIP cache 已补全可离线加载；qwen-eye judge JSON 可靠性已探针实证；h3_regen 批驱动 + smoke 2 镜 regen 已在盘；pytest 119 passed 基线）。新测试文件 tests/test_scorer.py + tests/test_judge.py 由 21-01 Task 3 交付（plan 内 verify 已声明 MISSING→create 路径）。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| judge 归因抽检（5 镜一致率 ≥4/5） | SCORE-02 (SC3) | 归因质量人类判断 | 看 roundtrip/_judge_grids/ 抽检 5 镜 grid（左 ORIGINAL 右 REGEN）+ 可选并排 regen vs 原片段 → 逐镜 agree/disagree → checkpoint 回复（21-03-T2） |
| τ_sim 分布裁决 | SCORE-03 (SC4) | 阈值是人类决策（SC4 明文记 Key Decisions；SigLIP 高窄带使直觉阈值失效） | 读校准报告分位数表/三桶/τ 预演 → 定 τ_sim + 理由 → checkpoint 回复 tau=&lt;float&gt;（21-03-T2） |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（checkpoint 任务按 Manual-Only 表豁免）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（两个新测试文件由 21-01-T3 首个交付；其余基础设施在位）
- [x] No watch-mode flags
- [x] Feedback latency < 60s（离线任务；GPU/批任务的延迟由其物理时长决定并显式标注）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-signed（2026-08-20）— 待执行期逐行勾选 Status
