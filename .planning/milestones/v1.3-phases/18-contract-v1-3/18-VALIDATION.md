---
phase: 18
slug: contract-v1-3
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-19
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | jsonschema 4.26.0（`Draft202012Validator`）+ Python 3.12 stdlib — mirror 11-VALIDATION「NOT unit tests」；pytest 9.0.3 仅作回归确认 |
| **Config file** | none — 复用 `spec/validate.py` + `scripts/verify_contract.py` |
| **Quick run command** | `python3 spec/validate.py`（四阶 gate，~1s） |
| **Full suite command** | `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~10-30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 spec/validate.py`
- **After every plan wave:** Run `python3 spec/validate.py && python3 scripts/verify_contract.py --mode=producer && python3 -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green + VERIFICATION 记录 byte-identical 证据（data-keys smoke + 11-file substrate diff-clean + SCHEMA_VERSION 双 grep）
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 18-01-T1 | 18-01 | 1 | RT-01 | T-18-01/02 | anti-traversal patterns on regen.path；maxLength 2000 on model text；closed enums | schema + schema(负) | Task `<verify>` python：check_schema + 全字段实例 + 4 个负变异（bogus 字段/score=1.5/attribution=banana/bad hash） | ⬜ (交付物自身) | ⬜ pending |
| 18-01-T2 | 18-01 | 1 | RT-01, RT-04 | T-18-01 | data.roundtrip path pattern 与 siblings 一致；warnings code closed enum(3) + detail str-only | schema + forward-compat | Task `<verify>` python：required[] 5 keys + 10 data props + minimal/v1.1/v1.2 三阶 forward-compat + warnings 双形 3 负例 | ✅ 目标文件在 | ⬜ pending |
| 18-01-T3 | 18-01 | 1 | RT-02, RT-04 | T-18-03/04/05 | byte-identical-absent（无 None/{} lazy-default）；malformed warn+OMIT；loader 非合规回退 None | smoke + grep | Task `<verify>` python：absent→5 keys + present→counts 1/1 + malformed/non-dict→OMIT + `_valid_warnings_list` 8 例 + `python3 spec/validate.py` | ✅ | ⬜ pending |
| 18-02-T1 | 18-02 | 2 | RT-01, RT-04 | T-18-10 | 11 substrate 文件 byte-identical（红线 substrate 半边）；shot_id ⊆ {1,2}；warnings 双形并存 | fixture + direct-validator | Task `<verify>` python：13 files + 11 diff-clean + 双 schema 校验 + counts 一致 + status.failed/3 attributions/3 warning codes/optional 缺席全覆盖 | ⬜ (交付物自身) | ⬜ pending |
| 18-02-T2 | 18-02 | 2 | RT-02 | T-18-11 | v1.3 阶计入退出码（fail-loud）；老阶不回归 | cli | `python3 spec/validate.py` → exit 0 + 13 条 `[valid-v13]` + `v1.3 failures=0` | ✅（待扩展） | ⬜ pending |
| 18-02-T3 | 18-02 | 2 | RT-01, RT-02 | T-18-07/08/09 | backward 过滤只豁免两类文档化 delta；注入 `asset_type:"other"` 真漂移必须 FAIL；_recover_v12 fallback 还原 items；EIGHT_SHAPES+特判成对 | cli + cli(负) | `python3 scripts/verify_contract.py --mode=producer` exit 0 + 四向证明话术 + 负测试 `[negative] … filter not blind` + `PHASE4_SELF_TEST=1` 绿 | ✅（待扩展） | ⬜ pending |
| 18-03-T1 | 18-03 | 3 | RT-03 | T-18-09/10/11 | AF-01 禁语 0 匹配；enum 与 schema 逐字一致；阈值只散文；XSS 义务预告 | grep + cli | Task `<verify>` python：§1 14 计数 + Changelog 1.3 + Round-trip 节 + §10 关键词 + 6 禁语 0 匹配 + fixture 一致最小片段 + validate.py 绿 | ✅（待编辑） | ⬜ pending |
| 18-03-T2 | 18-03 | 3 | RT-03 | T-18-09 | README 诚实 delta 记录 + AF-01 | grep | Task `<verify>` python：v1.3 section + 14 计数 + footer + 6 禁语 0 匹配 | ✅（待编辑） | ⬜ pending |
| 18-03-T3 | 18-03 | 3 | RT-03 | T-18-10/11 | 人类审阅 = RT-03「一次人类审阅通过」验收 | manual-only（见下表） | —（ROADMAP SC#5 明文要求） | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*注：标记 ⬜ (交付物自身) 的行是 mirror Phase 11 的既定模式 —— fixture/schema 是交付物，其验证内嵌在对应 task 的 `<verify>` automated 块中，无需独立测试文件（18-RESEARCH §Validation Architecture Wave 0 Gaps 同结论）。*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（spec/validate.py + scripts/verify_contract.py + tests/ 均在位且已验证：jsonschema 4.26.0、git tags v1.0/v1.1/v1.2、ep01 producer asset dir；本 phase 只增量扩展它们。零新依赖、零安装。）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SPEC.md §4/§5/§10 变更 + fidelity disclaimer 人类审阅（18-03-T3） | RT-03 | ROADMAP SC#5 成功标准明文「一次人类审阅通过」；措辞质量不可机判 | `git diff spec/SPEC.md spec/README.md` → 核对三层 disclaimer 措辞、两处非纯新增量诚实记录、enum 与 schema 逐字一致、AF-01 禁语 grep 0 → 回复 approved 或列修改点 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（18-03-T3 是 ROADMAP 明文的 manual-only checkpoint，登记于上表）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（无 MISSING 基建）
- [x] No watch-mode flags
- [x] Feedback latency < 60s（validate ~1s / verify_contract+pytest 数秒）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** set at planning time (2026-08-19) — per-task map populated from 18-01/02/03-PLAN.md `<verify>` blocks
