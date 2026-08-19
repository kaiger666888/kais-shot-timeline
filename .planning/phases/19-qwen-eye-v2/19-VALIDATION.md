---
phase: 19
slug: qwen-eye-v2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-19
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest（27 离线用例 0.16s）+ 引擎在线 smoke（spike 期间） |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + sandbox 幂等双跑 + validate.py（回归） |
| **Estimated runtime** | 离线 ~1s；在线 spike 1-3h（tmux 后台 + cache 断点续跑） |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + `python3 spec/validate.py`（契约回归）
- **Before `/gsd:verify-work`:** Full suite green + spike report 落档 + sandbox 证据
- **Max feedback latency:** 离线 60s；在线任务以引擎日志/cache 增量监控

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | VISION-01, VISION-02 | — | N/A（本地分析步骤，无新 attack surface；模型输出文本进 prompts.json 已有 schema 校验） | unit + integration | (planner fills) | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（tests/ + spec/validate.py 已在位；引擎 :8125 可拉起，GPU1 free 22.5GB ≥ 14GB 门槛）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 合并策略盲评（3 策略同镜产物打分） | VISION-01 (SC2) | Q3 27B 动作描述质量是 Pitfall 3 明示的未验证假设；机器判据循环论证 | 看 spike report 盲评表 → 选定策略 → 记录结论 |
| ear 双跑 diff 效果确认 | VISION-02 (SC3) | 「修正可见」是人类感知判断 | 看 spike report ear on/off diff 段 → 确认生效 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s（离线任务）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
