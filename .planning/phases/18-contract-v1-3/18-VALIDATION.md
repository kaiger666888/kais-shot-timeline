---
phase: 18
slug: contract-v1-3
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-19
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x（repo 现有 tests/ + jsonschema 4.26 direct validation） |
| **Config file** | tests/ 现有布局（无独立 config） |
| **Quick run command** | `python3 spec/validate.py` |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode cross-version && python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~30-60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 spec/validate.py`
- **After every plan wave:** Run `python3 spec/validate.py && python3 scripts/verify_contract.py --mode cross-version`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | RT-01..RT-04 | — | N/A（契约层，无 attack surface 增量；schema/fixture 本身是验证对象） | schema | `python3 spec/validate.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（spec/validate.py + verify_contract.py + tests/ 均已在位；本 phase 只增量扩展它们）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SPEC.md §4/§5 变更 + fidelity disclaimer 人类审阅 | RT-03 | 成功标准明文要求「一次人类审阅通过」 | 读 spec/SPEC.md diff，确认 §4 changelog 1.2→1.3、§5 roundtrip 形状、三层 disclaimer 措辞 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
