---
phase: 18-contract-v1-3
plan: 03
subsystem: contract
tags: [docs, spec, prose, changelog, fidelity-disclaimer, human-review, roundtrip]
requires:
  - "18-01 — roundtrip.schema.json + asset.schema.json v1.3 两处 delta + SCHEMA_VERSION=1.3 单源（散文描述的契约实体）"
  - "18-02 — spec/fixtures/v1.3/ fixture + validate.py 四阶 gate + verify_contract 四向双向证明（§4/README 引用的证据）"
provides:
  - "spec/SPEC.md v1.3 散文层 — §1 14-schema 布局、§4 Changelog 1.3（诚实记录两个非 property-delta）、§5.10 Round-trip 4-block 形状文档、§10.5 三层 fidelity disclaimer、header Version 1.3 / footer"
  - "spec/README.md v1.3 Update section + layout 14 schemas + fixtures/v1.3 行 + Phase 18 footer"
  - "RT-03 人类半边 — 一次人类审阅通过（Kai approved 2026-08-19，无 wording issues）"
affects:
  - "Phase 20 (h3 regen client) — §5.10 Producer 措辞即其写入契约的预告"
  - "Phase 21 (scorer/verdict) — §10.5 三层 disclaimer + 双阈值 Phase 21 校准指针是 scorer 的语义边界"
  - "Phase 22 (gallery/dataset) — Consumers 措辞 + _esc() XSS 义务预告（PRESENT-01）"
  - "所有 dataset 消费者 — §10.5 防止 over-trust accepted/rejected verdict"
tech-stack:
  added: []
  patterns:
    - "Changelog 非 property-delta 诚实记录模式（items 加宽 / object 挂载 不套用 v1.2 纯增量模板）"
    - "三层 fidelity disclaimer（accepted≠prompt-perfect / rejected=hard-negatives / attribution=model-judgment）作为一等交付物"
    - "AF-01 mention-not-use 处理：枚举句改写为 pattern-composition 描述（grep 无法区分提及与使用）"
key-files:
  created:
    - .planning/phases/18-contract-v1-3/18-03-SUMMARY.md
  modified:
    - spec/SPEC.md
    - spec/README.md
decisions:
  - "单源位置引用 grep 实测 export_asset.py:59（v1.2 README 小节所引 line 55 已过时 — PATTERNS 预警命中，两处新散文均引 59）"
  - "§10.1 / README v1.2 小节的 AF-01 枚举句改写而非保留 — 禁词 grep 是机器门，mention-not-use 无法被区分，枚举句本身必须重写为 pattern-composition 描述"
  - "阈值零数值：§5.10/§10.5 仅给 Phase 21 校准指针（two-tier authority — 阈值是散文+校准报告，永不进 schema）"
metrics:
  duration: "~30 min (13:50Z 执行 → 13:55Z 两 commit → 14:21Z human review approve + close-out)"
  completed: 2026-08-19
---

# Phase 18 Plan 03: SPEC v1.3 散文层 + 人类审阅 Summary

**One-liner:** SPEC.md v1.3 散文层落地 —— §1 布局 13→14、§4 Changelog `1.3` 诚实记录 v1.x 史上首个 items 加宽与首个 object 挂载（对旧数据 additive 但非 property-delta，不套 v1.2 纯增量模板）、§5.10 Round-trip 4-block 形状文档（enum 逐字对齐 schema、最小片段摘自 fixture）、§10.5 三层 fidelity disclaimer（accepted=「h3 可复现」≠「prompt 完美」/ rejected=hard negatives 非垃圾 / attribution=模型判断带 confidence 非 ground truth）+ README v1.3 小节 —— 一次人类审阅通过，RT-03 收口、Phase 18 三 plan 全部完成。

## What Was Built

### Task 1 — SPEC.md v1.3 散文 (commit ead9aaf)

98 insertions / 8 deletions，七处编辑：

- **§1**: heading「14 个 schema 文件」+ authority 表「(14 份)」+ TS note 14 + roundtrip.schema.json 行（顶层对象 — per-shot h3 重生成 ref + scores + verdict, `1.3` 样式对齐 siblings）。
- **Header**: Version 行 → `1.3 (active; schema_version: "1.3")`（顺带修复 stale v1.1 remnant）；Status 行追加 Phase 18 v1.3 additive extension (2026-08-19)。
- **§4 Changelog `1.3`**: mirror v1.2 entry 结构，但 bullets 如实记录**两个非纯 property delta** —— `generator.warnings.items` 加宽（string | {code, detail}，code enum 三值）与 `data.roundtrip` 首个 object 值挂载（对旧数据 additive 但非 property-delta，backward 证明过滤规则同步扩展）；schema_version pattern 不变 + 单源位置 **export_asset.py:59（grep 实测）**；CONTEXT-locked decisions 段（attribution closed enum / midframe_sim 必带 model / judge 无连续分 / shots[] 结果集语义 / fps-seed-workflow 不收）；向后兼容 bullet 引 validate.py 四阶 + v1.0↔v1.1↔v1.2↔v1.3 双向证明 + 11 substrate 文件 byte-identical。
- **§5 intro**: 追加 v1.3 句（新增 §5.10 Round-trip，optional — 仅 Phase 20/21 往返后 emit）。
- **§5.10 `### Round-trip (`1.3`)`**: 4-block 模板 —— Producer = Phase 20 + Phase 21（pending 措辞 mirror v1.2 当时写法）/ Consumers = Phase 22（pending）/ 顶层形状段（shots[] 结果集语义：有产物才在、失败=status{state:failed}、未尝试=缺席）/ 字段表（regen 8 字段 + status + scores 双信号 + verdict，enum 值与 schema 逐字一致，Notes 注明 regen 互斥、midframe model 标识理由、verdict.source=human 是 PRESENT-01 HITL 覆盖）/ 最小片段摘自 spec/fixtures/v1.3/roundtrip.json（2-shot 简化，结构 byte 一致）/ Reference schema 行。附 judge.reason/status.error 的 Phase 22 HTML 渲染 MUST `_esc()`（PRESENT-01 XSS 义务预告）+ data.roundtrip object 挂载说明。
- **§10.5 三层 disclaimer**: ① accepted = 「h3 可复现」≠「prompt 完美」—— fl2va 首尾帧条件渲染的幸存者偏差，prompt 未渲染维度不可由此 verdict 证伪；② rejected = hard negatives + h3 能力边界测绘数据，非垃圾（SCORE-03 rejected 占比审计依赖此语义）；③ judge attribution 是模型判断带 confidence 非 ground truth —— 三分类是自有分类学、confidence 未校准。附：accepted 双阈值由 Phase 21 ep01 ≤20 镜抽样校准后锁定，校准前 SPEC 不给数值（two-tier authority 重申）。
- **Footer**: Phase 18 Plan 03 行追加（v1.3 additive extension 摘要 + schema_version "1.3"）。

### Task 2 — README.md v1.3 小节 (commit 3f9a792)

47 insertions / 5 deletions，三处编辑：

- **Layout diagram**: 「13 个」→「14 个」；tree 增 roundtrip.schema.json（schemas/ 下）+ fixtures/v1.3/ 块（13 JSON）；validate.py 行三→四 pass；SPEC.md tree 行 + §5.10。
- **`## v1.3 Update (Phase 18, 2026-08-19)`**（v1.2 小节之后、Origin 之前，mirror 其结构）: 1 个新 schema 一句话；**两处 delta 诚实记录**（data.roundtrip 首个 object 值挂载 + warnings items 首次加宽，code enum 三值，对旧数据 additive）；**单源位置 export_asset.py:59**（明示 v1.2 小节 "line 55" 已过时）；CONTEXT-locked decisions bullets；13-file fixture（11 byte-copy + asset.json 编辑 + roundtrip.json 新增）；双向证明话术（四阶 gate + 四向 forward 0 errors / backward 0 non-additive excluding documented v1.3 deltas）；字段保真度边界 pointer 至 SPEC §10 三层。
- **Footer**: `*Updated: 2026-08-19 (Phase 18 — v1.3 additive extension: …)*` 行追加。

### Task 3 — 人类审阅 checkpoint (RT-03「一次人类审阅通过」)

- **呈现**: git diff spec/SPEC.md + spec/README.md 全量 v1.3 散文 delta、三层 disclaimer 措辞、AF-01 grep、可选 gate 复跑（how-to-verify 步骤 1-4）。
- **Verdict**: **approved** — Kai 于 2026-08-19 批准，**无 wording issues、无返修**（resume-signal 为批准等效确认）。
- RT-03 人类半边达成；ROADMAP Phase 18 SC#5（「SPEC.md §4 changelog 1.2→1.3 + §5 roundtrip 形状文档 + fidelity disclaimer 一次人类审阅通过」）为 TRUE。

## Task Commits

1. **Task 1: SPEC.md v1.3 prose** — `ead9aaf` (docs)
2. **Task 2: README.md v1.3 section** — `3f9a792` (docs)
3. **Task 3: human review** — 无 commit（review-only checkpoint；verdict 记录于本 SUMMARY，per plan Task 3 `<action>`）

## Files Created/Modified

- `spec/SPEC.md` — v1.3 人类可读契约：§1 布局 14、§4 Changelog 1.3、§5.10 Round-trip 形状文档、§10.5 三层 fidelity disclaimer、header/footer
- `spec/README.md` — schema 布局索引 + v1.3 update 小节 + Phase 18 footer

## Decisions Made

- 单源位置行号 grep 实测引用（export_asset.py:59），不 copy v1.2 小节的 stale "line 55" —— PATTERNS 预警在两处新散文中均规避。
- 阈值零数值原则贯穿：§5.10 Notes 列与 §10.5 均只给「见 §10 / Phase 21」指针（two-tier authority）。
- §10.5 采用独立子节（10.5 起）而非改写 v1.2 的 10.1-10.4 —— v1.2 disclaimer 原文保留，v1.3 三层作为增量层追加。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AF-01 枚举句本身含禁词（mention-not-use 但 grep 无法区分）**
- **Found during:** Task 1（SPEC.md §10.1）与 Task 2（README v1.2 小节）
- **Issue:** v1.2 遗留的 AF-01 枚举句（「不宣称 绝对复现 / 完美重建 …」一类）以提及方式罗列禁词 —— 语义是禁止而非宣称，但 AF-01 验收 grep 是纯字面匹配，mention 与 use 不可区分，本 plan 的 AF-01 验收（grep 0）会被自己的枚举句击穿。
- **Fix:** 枚举句改写为 pattern-composition 描述（描述禁词的构成模式而不字面复现禁词）；语义等价、验收门恢复可机器化。
- **Files modified:** spec/SPEC.md（§10.1）、spec/README.md（v1.2 小节）
- **Verification:** `grep -c '完美复刻\|精确复原\|perfectly reconstruct\|exact restoration\|完美重建\|绝对复现' spec/SPEC.md spec/README.md` → 0/0（close-out 复跑）
- **Committed in:** ead9aaf（SPEC 半边）、3f9a792（README 半边）

---

**Total deviations:** 1 auto-fixed (Rule 1 — 两文件同根因，随各自 task commit)
**Impact on plan:** 必要且最小 —— 不修则 plan 自身验收门（AF-01 grep 0）自相矛盾。无 scope creep。

## Auth Gates

None — no auth-required operations in this plan.

## Known Stubs

None — 纯散文交付，无代码 stub/placeholder。

## Verification Evidence

Close-out 复跑（2026-08-19T14:20-14:21Z，approval 之后）：

- Task 1 automated verify: `[spec-ok] §1 14 + §4 1.3 + Round-trip section + §10 三层 + AF-01 clean + fixture-consistent excerpt`（首次执行时绿）。
- Task 2 automated verify: `[readme-ok] v1.3 section + layout 14 + footer + AF-01 clean`（首次执行时绿）。
- **AF-01**: `grep -c '完美复刻\|精确复原\|perfectly reconstruct\|exact restoration\|完美重建\|绝对复现' spec/SPEC.md spec/README.md` → **0 / 0**。
- **validate.py**: exit 0（四阶 gate：minimal/v1.1/v1.2/v1.3 全绿 —— 散文编辑零回归）。
- **verify_contract producer**: exit 0 —— `v1.0↔v1.1↔v1.2↔v1.3 cross-version bidirectional compat proven (forward 0 errors; backward 0 non-additive errors, excluding documented v1.3 deltas: data.roundtrip + warnings items widening)` + `v1.1 + v1.2 + v1.3 fixture set cross-file IDs consistent (0 dangling)`。按 18-02 文档化路由 `PHASE4_ASSET_DIR`=ep02 跑；默认 ep01 目录的 FAIL 仍是**pre-existing** registry.draft.json 漂移（deferred-items #2，与本 plan 零代码改动无关，失败文案与 18-02 记录逐字一致）。
- **单源位置一致性**: `grep -n 'SCHEMA_VERSION = ' scripts/export_asset.py` → **59**；SPEC §4 与 README v1.3 小节均引 `export_asset.py:59`。
- **Human review**: approved（Task 3，2026-08-19）—— plan `<verification>` 第 4 条满足。

## Self-Check: PASSED

- Files: spec/SPEC.md FOUND (modified) · spec/README.md FOUND (modified) · 18-03-SUMMARY.md FOUND
- Commits: ead9aaf FOUND · 3f9a792 FOUND
- Close-out gates 全绿（AF-01 0/0 · validate exit 0 · verify_contract producer exit 0 via documented ep02 route）

## Next Phase Readiness

- Phase 18 三 plan 全部完成：RT-01/RT-02/RT-03/RT-04 四 requirement 收口 —— v1.3 契约层（schema + fixture/gate/proof + 散文 + 人类审阅）整体就绪。
- Phase 20（h3 复现客户端）已有完整写入契约：roundtrip.schema.json + §5.10 形状文档 + warnings 三 code degrade 通道。
- Phase 21（scorer）语义边界已锁：三层 disclaimer + 双阈值校准流程（校准前零数值）。
- Phase 22（gallery/dataset）消费契约 + `_esc()` XSS 义务已在散文预告。
- 遗留（非阻塞）: deferred-items #2 —— ep01 registry.draft.json 运行时漂移需 orchestrator 裁决（widen schema vs 重生成 draft），仅影响默认目录 producer-mode exit code。

---
*Phase: 18-contract-v1-3*
*Completed: 2026-08-19*
