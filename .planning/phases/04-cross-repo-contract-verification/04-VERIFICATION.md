---
phase: 04-cross-repo-contract-verification
verified: 2026-07-20T19:50:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "WR-01: sequence edge data 字段经 save-v2 HTTP roundtrip 后是否存活 (FlowLinkV2Schema strips unknown keys)"
    addressed_in: "Phase 4 (accepted, not fixing)"
    evidence: "本报告 §WR-01/04 正式 Acceptance —— e2e 走 primary appendAndSync 路径,sequence edges 完整存活 (92 edges 断言通过);save-v2 是 secondary 路径,不在 v1.0 e2e scope 内。归属:kais-aigc-platform feat/canvas-asset-collection backlog"
  - truth: "WR-04: sum-p13 summary node 经 save-v2 HTTP path 通过 validateGraphNodes 校验"
    addressed_in: "Phase 4 (accepted, not fixing)"
    evidence: "本报告 §WR-01/04 正式 Acceptance —— e2e snapshot 含 sum-p13 且经 primary 路径写入;appendAndSync 不调 validateGraphNodes (Phase 3 deferred-items.md 已记录此分叉)。pre-existing pattern (每 phase summary 自 P01 起同形状),v1.0 additive 范围外不修"
---

# Phase 4: Cross-Repo Contract Verification — Capstone Report

**Phase Goal:** A real ShotTimelineAsset flows end-to-end from producer to consumer, and a regression harness exists to keep the contract aligned as both repos evolve independently.
**Verified:** 2026-07-20
**Status:** passed
**Re-verification:** No — initial verification (capstone of v1.0 milestone)

## 1. Phase Success Criteria 验证

### SC-1: real ShotTimelineAsset imports successfully → renders collection of storyboard / stem-audio / video / prompt children — **VERIFIED with scope reduction recorded**

| Observable | Source | Status | Evidence |
|------------|--------|--------|----------|
| 真实 producer ep01 asset (schema_version="1", 93 shots, 308.352s) | `output/虫虫武侠…第01话…/asset.json` | ✓ | Phase 2 产出,被 e2e 直接喂入 |
| consumer backend HTTP /api/canvas/v2/import-from-dir 接受 | `run_e2e_check` POST 返 200 | ✓ | `[e2e] import-from-dir OK: 99 nodes imported` |
| 持久化 snapshot 结构正确 | SQL 直查 `o_agentWorkData` (key='canvasGraph') | ✓ | 99 nodes / 190 links,断言全绿 (见下表) |
| 1 zone 父节点聚合 children | zones count = 1 | ✓ | zone.data.label = manifest.source.video_filename (Phase 3 SC-1 兑现) |
| N storyboard (shot_id chain) | storyboards count = 93 | ✓ | 匹配 ep01 shots.json |
| 3 stem-audio (vocals/drums/other) | audios count = 3 | ✓ | 与 Demucs 4-stem 减 bass 的 contract 一致 |
| video artifact | videos count = 2 (1 artifact + 1 sum-p13) | ✓ | buildPhaseTree 强制 sum-p13.type = phase.canvasType = "video" |
| N-1 sequence edges | seq_edges count = 92 | ✓ | **WR-01 验证:primary 路径 sequence edges 完整存活** (Phase 3 producer 字面形状 `{dataType:"data", data:{linkType:"sequence"}}` 写入 o_agentWorkData JSON blob 不被 strip) |

**Snapshot 结构汇总 (实测,exit 0):**
```
[e2e] snapshot valid: 99 nodes, 190 links, 1 zone, 93 storyboard,
                        3 audio, 2 video, 92 seq edges
                        (WR-01 data survives primary path)
```

#### SC-1 prompt-children Scope Reduction (显式记录)

ROADMAP Phase 4 SC-1 原文提「storyboard / stem-audio / video / **prompt** children」。Phase 3 CONTEXT (D3 discretion) 显式 defer prompts/transcript 为 **sidecar data refs** —— asset.json#data.prompts / #data.transcript 是文件路径引用,而非独立 canvas 节点。Phase 4 e2e observable collection 节点集合是 storyboard/audio/video (collection 节点);prompts data 附挂在 asset.json 的 data.prompts 字段里,经 importer 校验存在后作为 sidecar 引用暴露给前端,但**不**单独建 prompt canvas 节点。

- **不是 gap** —— 这是 Phase 3 显式设计决定 (CONTEXT 03 discretion locked)。Phase 4 e2e 在 SC-1 上的 observable 集合已经匹配 Phase 3 实际 importer 语义。
- **Cross-reference:**
  - `.planning/phases/03-canvas-consumer/03-CONTEXT.md` (Phase 3 D3 deferral note)
  - `.planning/phases/03-canvas-consumer/03-01-SUMMARY.md` (summary acknowledgment)
  - `04-CONTEXT.md` (Phase 4 锁:接受此 scope 缩减,VERIFICATION 显式记录)

### SC-2: regression test exists that fails on producer/consumer drift — **VERIFIED (both directions + fail-loud proof)**

| Mode | Direction | Command | What it catches |
|------|-----------|---------|-----------------|
| producer | producer → contract | `python3 scripts/verify_contract.py --mode=producer` | producer asset.json 或 5 data shapes schema-invalid (Draft202012Validator inline,asset shape 不 subprocess 到 spec/validate.py 因为 SMOKE_SHAPES 排除) |
| consumer | contract → consumer | `python3 scripts/verify_contract.py --mode=consumer` | consumer importer 拒绝 valid asset (shell-out 到 Phase 3 verify-canvas-shot-timeline.ts 17 asserts A-F + E2 + F2) |
| self-test | harness fail-loud proof | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | harness 损坏时无法检测 producer drift (注入 `schema_version='v1'` → assert ≥1 jsonschema error) |
| e2e | end-to-end primary path | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | real producer asset → consumer backend → persisted snapshot 结构漂移 (zone/storyboard/audio/video/seq-edge counts) |

**Fail-loud 实证 (self-test):**
```
[self-test] PASS: corrupt asset (schema_version='v1') correctly rejected
                with 1 error(s); first at /schema_version:
                'v1' does not match pattern
                ^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$
```

## 2. Requirements Coverage

| Req ID | Behavior | Automated Command | Status | Evidence |
|--------|----------|--------------------|--------|----------|
| VERIFY-01 | 导出端产物能被消费端成功 import,并正确渲染出分镜/stem/字幕/prompt 集合 (observable e2e) | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | ✓ SATISFIED | e2e exit 0 + snapshot 结构断言全绿 (1 zone + 93 storyboard + 3 audio + 2 video + 92 seq edges);SC-1 prompt scope reduction 显式记录见上 |
| VERIFY-02 | 契约一致性验证 —— 字段 schema 与媒体引用在导出端 ↔ 消费端两端对齐,有回归保护 | `python3 scripts/verify_contract.py` (默认 --mode=all,含 producer + consumer) | ✓ SATISFIED | producer mode: 6 schemas inline validate;consumer mode: Phase 3 17 asserts shell-out 全绿;self-test 证明 fail-loud (corrupt asset 正确 reject) |

## 3. WR-01 / WR-04 正式 Acceptance (闭环 Phase 3 deferred items)

### 背景

Phase 3 code review (`03-REVIEW.md`) 在 consumer 的 **secondary `save-v2` HTTP 路径** 发现两个 latent bugs,因触及 consumer 仓库共享 production schema (`flowgraph-v2-schema.ts`) 超出 Phase 3 additive 范围,在 `deferred-items.md` 显式 defer 给 Phase 4 triage:

- **WR-01:** `FlowLinkV2Schema` 不声明 `data` 字段 → `save-v2.ts` 经 `z.object(...).safeParse` strip sequence edge 的 `data: { linkType: "sequence" }`,前端 `CanvasEdge.tsx:33` 读 `data?.linkType` 拿 undefined,sequence edge 视觉降级为普通 edge (失去蓝色实线 + 箭头)。
- **WR-04:** `validateNodeData` (canvasAssetSchema.ts:133) 在 `save-v2.ts:49` 全节点列表调用时不 filter `sum-` 前缀 → `sum-p13` (type="video" 但 data 非媒体) 被 Zod reject → HTTP 400。

### Phase 4 决定:**accept, not fixing in v1.0**

依据:

1. **e2e 走 primary `appendAndSync` 路径** —— 该路径不 Zod-parse graph payload,仅 append event 到 `kv_canvasEvent` + recompute snapshot → 写 `o_agentWorkData` JSON blob。不触发 `FlowLinkV2Schema` (WR-01) 或 `validateGraphNodes` summary-node 检查 (WR-04)。
2. **e2e SQL read-back 实证** —— `o_agentWorkData` snapshot 含完整 sequence edges (实测 92,匹配 N-1 where N=93 storyboards),证明 WR-01 在 primary 路径不浮现;snapshot 也含 sum-p13 node (实测 1 个,在 2 video 里),证明 WR-04 在 primary 路径不浮现。
3. **secondary `save-v2` 路径的修复需动 consumer 共享 production schema** (`flowgraph-v2-schema.ts` / `canvasAssetSchema.ts`) —— 这是跨所有 14 phases 的 cross-cutting 变更,超出 v1.0 ShotTimelineAsset Contract milestone 的 additive 范围 (CONTEXT D-WR 锁;Phase 3 CANVAS-03 同 spirit)。
4. **WR-04 是 pre-existing pattern** —— 自 P01 起每 phase 的 summary node (sum-p01..sum-p13) 都是同形状,Phase 3 不是引入 bug,只是扩大触发频率。

**Cross-reference:**
- `.planning/phases/03-canvas-consumer/deferred-items.md` WR-01 (§37-65) + WR-04 (§110-148) 原文
- `.planning/phases/03-canvas-consumer/03-VERIFICATION.md` deferred 字段 (L13-22) 三条「addressed_in: "Phase 4"」项目正式闭环
- `04-CONTEXT.md` D-WR 决策锁定 (Phase 4 显式 accept,cross-reference Phase 3 deferred-items)

### 闭环状态

| Item | Phase 3 status | Phase 4 status | 最终归属 |
|------|---------------|----------------|----------|
| WR-01 sequence edge data stripping (save-v2 路径) | deferred: Phase 4 triage | **accepted, not fixing in v1.0** (primary 路径不受影响,e2e 实证) | consumer-repo backlog (`kais-aigc-platform` feat/canvas-asset-collection) — 后续 persistence-hardening phase 或 save-v2 重构时处置 |
| WR-04 sum-p13 Zod-reject (save-v2 路径) | deferred: Phase 4 triage | **accepted, not fixing in v1.0** (primary 路径不受影响,e2e snapshot 含 sum-p13 实证) | 同上 |

Phase 3 `03-VERIFICATION.md` deferred 字段「addressed_in: "Phase 4"」的三条项目 (WR-01 / WR-04 / full HTTP e2e) 全部闭环:
- WR-01: 本节 accept
- WR-04: 本节 accept
- full HTTP e2e: §SC-1 + §1 e2e 实证 (exit 0 + snapshot 结构断言)

## 4. 3-mode + self-test 运行结果

| Mode | 命令 | 耗时 (实测) | 结果 | Evidence 摘要 |
|------|------|------------|------|---------------|
| producer | `python3 scripts/verify_contract.py --mode=producer` | <1s | ✓ exit 0 | asset.json + 5 data shapes all schema-valid (Draft202012Validator inline,asset shape 不走 spec/validate.py SMOKE_SHAPES 排除) |
| consumer | `python3 scripts/verify_contract.py --mode=consumer` | ~3s | ✓ exit 0 | Phase 3 verify-canvas-shot-timeline.ts 19 sub-asserts PASS (CANVAS-01 structure + CANVAS-02 sequence chain + CANVAS-03 Zod/additive-only + F roundtrip + F2 WR-07 filePath synthesis) |
| self-test | `PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | <1s | ✓ exit 0 (PASS = harness detects drift) | 注入 `schema_version='v1'` → 1 jsonschema pattern error 检出 |
| e2e | `PHASE4_RUN_E2E=1 python3 scripts/verify_contract.py --mode=e2e` | ~15s (boot + import + SQL + teardown) | ✓ exit 0 | snapshot valid: 99 nodes / 190 links / 1 zone / 93 storyboard / 3 audio / 2 video / 92 seq edges |
| **full gate** | `PHASE4_RUN_E2E=1 PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py` | ~20s | ✓ exit 0 | self-test + producer + consumer + e2e 四 mode 全绿 |

### Backend lifecycle 实证

| 不变量 | 实测 | Status |
|--------|------|--------|
| Backend 干净 teardown (无 orphan npx/tsx 进程) | `pgrep -af "tsx src/app.ts"` 返空 | ✓ PASS (start_new_session=True + os.killpg 三层兜底,Rule 1 fix) |
| Worktree src/types/database.d.ts 干净 | `git -C ... status --short src/types/database.d.ts` 返空 | ✓ PASS (teardown `git checkout --` reconcile dev-mode regen) |
| Phase 3 leftover (9001/9001) 保留 | `sqlite3 ... SELECT count(*) ... = 1` | ✓ PASS (e2e 用 timestamp-based pid/eid,teardown parameterized DELETE WHERE projectId/episodesId = own pid/eid) |
| e2e own test rows 已清 | `sqlite3 ... SELECT count(*) WHERE projectId NOT IN ('9001') = 0` | ✓ PASS |
| SQL 全部参数化 | grep `"SELECT data FROM o_agentWorkData WHERE projectId = \?"` 等 | ✓ PASS (T-04-01-T2 mitigation) |

## 5. 闭环 Status

### Phase 4 milestone 完成

- VERIFY-01 (real asset → consumer import → 渲染分镜/stem/字幕/prompt 集合 observable e2e): **SATISFIED** with SC-1 prompt-children scope reduction 显式记录 (Phase 3 D3 deferral)
- VERIFY-02 (契约一致性回归保护): **SATISFIED** via producer mode (6-schema inline validate) + consumer mode (Phase 3 17 asserts shell-out) + self-test (fail-loud proof)

### 跨仓库契约验证体系落地

`scripts/verify_contract.py` (682 lines) —— 单一 canonical home (spec owner = contract authority),4 mode (producer / consumer / e2e / self-test) 兜住两个漂移方向 + fail-loud 自检。Phase 1 (schemas) + Phase 2 (exporter) + Phase 3 (importer) 的产物被此 harness 持续校验。

### v1.0 ShotTimelineAsset Contract milestone 全部 4 phase 闭合

| Phase | Status | Closed |
|-------|--------|--------|
| Phase 1 (spec) | COMPLETE | 2026-07-20 |
| Phase 2 (exporter) | COMPLETE | 2026-07-20 |
| Phase 3 (consumer) | COMPLETE | 2026-07-20 (deferred-items 留 WR-01/04) |
| Phase 4 (verification) | COMPLETE | 2026-07-20 (WR-01/04 正式 accept + 闭环) |

### Phase 3 deferred items 闭环

- WR-01: **accepted in Phase 4** (not deferred further)
- WR-04: **accepted in Phase 4** (not deferred further)
- Full HTTP e2e: **satisfied in Phase 4** (e2e mode + snapshot 结构断言)

### 已记录的 scope reductions

- **SC-1 prompt children**: prompts/transcript 是 sidecar data refs (asset.json#data.{prompts,transcript}),非独立 canvas 节点 (Phase 3 D3 discretion)。Phase 4 e2e observable collection = storyboard/audio/video。
- **save-v2 路径不在 v1.0 scope**: e2e 走 primary appendAndSync,save-v2 latent bugs (WR-01/04) 正式 accept + 归属 consumer-repo backlog。

### Gaps Summary

**No gaps.** All 8 must-have truths (6 truths + 2 artifacts) verified. All 2 success criteria satisfied (with scope reductions explicitly recorded). All 2 requirements (VERIFY-01, VERIFY-02) SATISFIED. Phase 3 deferred items (WR-01/04) formally accepted + cross-referenced. v1.0 milestone 全部 4 phase 闭合。

---

_Verified: 2026-07-20_
_Verifier: Claude (gsd-plan-executor)_
_Phase: 04-cross-repo-contract-verification (capstone)_
_Milestone: v1.0 ShotTimelineAsset Contract_
