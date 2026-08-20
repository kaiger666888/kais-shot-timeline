---
phase: 21-scorer-threshold-calibration
fixed_at: 2026-08-20T03:15:25Z
review_path: .planning/phases/21-scorer-threshold-calibration/21-REVIEW.md
iteration: 2
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 21: Code Review Fix Report (Iteration 2 — WR-06)

**Fixed at:** 2026-08-20T03:15:25Z
**Source review:** .planning/phases/21-scorer-threshold-calibration/21-REVIEW.md（re-review iteration 2，review range `95fadc2..c4fc324`）
**Iteration:** 2

**Summary:**
- Findings in scope (fix_scope = WR-06 single finding): 1
- Fixed: 1
- Skipped: 0
- Iteration 1（CR-01 + WR-01..05，6 项全修）见 git 历史 `95fadc2..c4fc324` 与本文件前序版本（`git show 462a881:.planning/phases/21-scorer-threshold-calibration/21-REVIEW-FIX.md`）。

**Verification:**
- `python3 -m pytest tests/ -q` → **171 passed**（iteration-2 基线 170 + 1 个 WR-06 新回归锚，零回归）
- `python3 spec/validate.py` → exit 0（`[validate] OK`，failures=0 全 fixture）
- Diff scope: only `analysis/roundtrip/scorer.py`、`tests/test_scorer.py`、`21-REVIEW.md`（WR-06 outcome 注记）——judge.py 核查后未改动（无同款模式），runtime `roundtrip.json` 数据 / ROADMAP / STATE 未触碰；19 个冻结 verdict（τ=0.9670）语义不受影响（改动只在 scorer cache 预判的容错路径，verdict freeze 逻辑未动）。

## Fixed Issues

### WR-06: orig_window key 推导的 `float()` 在 per-shot try 之外 —— 单条坏 shots.json 几何重新炸整批（WR-03 类回归，WR-02 修复引入）

**Files modified:** `analysis/roundtrip/scorer.py`, `tests/test_scorer.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** 59b8c80
**Applied fix:** 采纳 Fix 建议原样：cache 预判循环的几何推导（start/dur 两个 `float()` + `round` 三行，原 L551-554）包进 per-candidate `try:`，`(TypeError, ValueError)` 时落哨兵 `orig_window = [None, None]`——真实打分只产 float 对，`cache_read` 的 `!=` 全等比较下哨兵必 miss 且无异常面。坏几何镜随后进 miss 循环，由 `score_shot` 自身的同款推导在 per-shot try 内炸成单镜失败（WR-03 不变量：打印异常 + `failed` 名单 + warning flush + 批继续），CR-01 的 hit 回填不再被预判崩溃阻断。哨兵永不入 cache（`score_shot` 在 payload 构造前即抛，坏镜无 `cache_write`，run-1 存量 payload 原样）。模块 docstring 步骤 2 同步补 WR-06 容错语义。**judge.py 核查结论：无同款模式**——其 key 无几何维（只有 vch/sha16/engine/prompt_version），dur/start 的 `float()` 本就在 per-shot try 内（judge.py:852-855，re-review 已确认），未改动。回归锚：`test_bad_shots_geometry_precheck_tolerant_replay_not_blocked`——2 镜基线全打分入 cache → shots.json shot 1 `duration="6,73"` + sidecar scores 半边全丢（模拟中断）→ 断言 rc=0（修复前预判 `ValueError: could not convert string to float: '6,73'` 确定性炸批）、`failed shots: [1]` warning、shot 2 从 cache 回填（CR-01 不被阻断）、shot 1 的 run-1 cache payload `orig_window == [0.0, 6.73]` 原样未被哨兵覆写、sidecar 过 schema 校验。

## Skipped Issues

None — the single in-scope finding (WR-06) was fixed. Info findings IN-07/IN-08/IN-09 均不在本次 fix_scope（single finding WR-06）内，未尝试。

---

_Fixed: 2026-08-20T03:15:25Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
