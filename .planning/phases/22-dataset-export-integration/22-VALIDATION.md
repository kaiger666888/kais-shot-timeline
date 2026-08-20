---
phase: 22
slug: dataset-export-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-20
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（wiring/XSS/edits-apply/dataset 单测）+ bash e2e 四场景 harness + ep01 抽样端到端真跑 |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + `bash tests/test_phase22_e2e.sh` + `python3 spec/validate.py` |
| **Estimated runtime** | 离线 ~4s；e2e harness ~2-5min；ep01 抽样 e2e 分钟级（cache 全命中） |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + validate.py
- **Before `/gsd:verify-work`:** 全绿 + ep01 e2e 证据（roundtrip.json + dataset 目录 + asset.json 挂载齐产）落 SUMMARY
- **Max feedback latency:** 离线 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | RT-05, DATASET-02, PIPE-01, PIPE-02, PRESENT-01 | — | XSS _esc 全覆盖（SC3 新 attack surface）；edits confirmed-only | unit + e2e + UAT | (planner fills) | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（三件套 + 先例模块 + e2e 先例均在；GPU/引擎按场景需要拉起）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| review 面板走查（双 video 同步播 + 三态覆盖 + export edits 流程） | PRESENT-01 (SC2) | 浏览器交互人类走查 | serve.py 起服务开 roundtrip_review.html → 走查 → checkpoint |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s（离线任务）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
