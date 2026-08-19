---
phase: 21
slug: scorer-threshold-calibration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-20
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（FakeSigLIP/FakeEye mock + 帧窗数学 + JSON 容错）+ GPU smoke（2 镜既有 regen 上真跑 scorer+judge）+ overnight 批（19 镜 @1344×768 ≈3-4.5h） |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + `python3 spec/validate.py` |
| **Estimated runtime** | 离线 ~3s；GPU smoke ~10min；overnight 批 3-4.5h（tmux/nohup） |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + validate.py
- **Before `/gsd:verify-work`:** 全绿 + 校准报告 + 20 镜 roundtrip.json schema 合法
- **Max feedback latency:** 离线 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | SCORE-01..03, DATASET-01 | — | N/A（本地打分模块；judge reason 是模型文本→sidecar 有 schema 长度约束） | unit + smoke + calibration | (planner fills) | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（SigLIP cache 已补全可离线加载；qwen-eye judge JSON 可靠性已探针实证；h3_regen 批驱动 + smoke 2 镜 regen 已在盘）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| judge 归因抽检（5 镜一致率 ≥4/5） | SCORE-02 (SC3) | 归因质量人类判断 | 看抽检表 judge 归因 vs 自己判断 → checkpoint 裁决 |
| τ_sim 分布裁决 | SCORE-03 (SC4) | 阈值是人类决策（SC4 明文记 Key Decisions） | 看校准报告散点/分位数表 → 定 τ_sim + 理由 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s（离线任务）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
