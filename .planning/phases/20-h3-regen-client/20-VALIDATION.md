---
phase: 20
slug: h3-regen-client
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-20
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（FakeComfyUI HTTP mock + nvidia-smi/TTS mock）+ 真 ComfyUI smoke（--sample-shots 2 级别） |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + `python3 spec/validate.py`（契约回归） |
| **Estimated runtime** | 离线 ~2s；真机 smoke 单镜 5-8min |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + validate.py
- **Before `/gsd:verify-work`:** 全绿 + smoke 证据落档
- **Max feedback latency:** 离线 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | REGEN-01..04 | — | N/A（本地批客户端；ComfyUI :8188 是 localhost 信任边界；产物路径受 schema pattern 约束） | unit + smoke | (planner fills) | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（tests/ + FakeComfyUI mock 由 plan 内创建；真 ComfyUI :8188 已在跑（v0.30.0, GPU1 3090）；fl2va 模板来自 research Code Examples）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| regen mp4 目视抽检（首尾帧 condition 是否贴合原镜） | REGEN-01 | 视觉质量判断 | 看 smoke 产物 2-3 镜 mp4 vs 原镜并排 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s（离线任务）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
