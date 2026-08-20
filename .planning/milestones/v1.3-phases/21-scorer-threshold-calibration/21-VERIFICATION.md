---
phase: 21-scorer-threshold-calibration
verified: 2026-08-20T03:21:43Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
warnings:
  - "校准报告内残留 DRAFT 痕迹：footer（L345）仍写 'status: DRAFT —— 待 Kai 裁决' 与头部 FINAL（L3）矛盾；§6.3 抽检一致率 / §6.4 裁决记录 两个 '待裁决后回填' 占位节（L299-304）未随裁决收口删除；§6.3 编号重复（L236 与 L299）且排在 §6.1/6.2 之前——内容完整（裁决记录 + rejected 分桶审计均在），属文档卫生问题非 goal 缺口"
  - "STATE.md stopped_at 仍写 '21-03 Task 2 checkpoint 待 Kai 裁决'（裁决已完成且 ROADMAP/REQUIREMENTS 已标 Complete）——stale 一行，status: verifying 本身与当前工作流一致"
---

# Phase 21: Scorer + 阈值校准 Verification Report

**Phase Goal:** 双信号打分——中段帧 CLIP/SigLIP 轨迹相似度（便宜信号）+ VLM judge 归因（区分 prompt 好/h3 不行 vs prompt 欠约束）——在 ep01 ≤20 镜抽样上实测分布、锁定 accepted 双门槛，verdict 写入 schema 合法的 `roundtrip.json`，rejected 永不删除。
**Verified:** 2026-08-20T03:21:43Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths（ROADMAP Success Criteria）

| # | Truth | Status | Evidence |
| - | ----- | ------ | -------- |
| 1 | 对抽样 regen 镜跑 scorer：每镜产出 scores{midframe_sim, judge}，roundtrip.json 条目过 Phase 18 schema gate（含 verdict + attribution + reason） | ✓ VERIFIED | 19/19 条目双半边齐（`scores.midframe_sim{score,model}` + `scores.judge{attribution,confidence,reason}`）+ 19 条 verdict{decision,source,decided_at}；**验证器本会话实跑** `h3s._iter_sidecar_errors` → **0 errors**；19 个 regen mp4 @1344x768 在盘（engine_version 全 `fl2va-int8/euler+simple/15/1344x768`） |
| 2 | midframe 相似度显式只用 25%-75% 时窗帧——t=0/t=end 排除（打分帧清单可审计） | ✓ VERIFIED | 代码：`frame_ts = dur·(0.25+0.5·j/(n-1))` + `min(ts, max(dur-0.2, 0.0))` clamp（scorer.py L123-130）——n=8 时 t_pct 序列 25.0..75.0，t=0/t=end 结构性不可达；**验证器本会话审计全部 19 个 scorer cache**：orig+regen 38 侧 × 8 帧 = 304 帧全落 [25.0, 75.0]，**0 违例**；cache 逐帧存 {j, t_pct, t_sec, path} + per_position_cos 8 元 |
| 3 | judge 归因三分类以结构化输出产出，ep01 抽样上有人工抽检一致的示例 | ✓ VERIFIED | 19 judge cache 全含 parsed{attribution∈闭集, confidence, reason}（结构化，fence 剥离+花括号截取+严格校验+retry-with-feedback ≤2）；三桶分布 faithful=10 / diverged=9 / underspecified=0；19 张 grid 图在盘（1370×1476，285-676KB，含抽检 5 镜 61/47/14/52/19）；人工抽检经 blocking checkpoint 由 Kai 完成（approved，记录于报告 §6.3 + PROJECT.md L150） |
| 4 | ep01 ≤20 镜双信号分布实测 → accepted 双门槛锁定 + 决策记录进 PROJECT.md Key Decisions；rejected 占比记录可审计 | ✓ VERIFIED | 分布实测 19 镜（p10=0.9005/p50=0.9457/p90=0.9741，报告 §4.3）；τ_sim=0.9670 + 硬合取（sim ≥ τ ∧ prompt_faithful）锁定；**PROJECT.md L150 Key Decisions 行已录**（值 + 双门槛定义 + decided 2026-08-20 + 证据指针）；rejected 15/19=79% 按归因分桶可审计（报告 §6.3：faithful<τ=6 + diverged=9 + underspecified=0；§6.1 全 21 档 τ 预演表逐档分桶） |
| 5 | verdict 合并幂等：重跑不丢 rejected | ✓ VERIFIED | **验证器本会话独立重跑** `judge.py --apply-verdict --tau-sim 0.9670` → `applied=0 frozen=19 skipped=0`，rc=0，roundtrip.json sha256 前后字节级相同（`63543baf…336dd73`——与 SUMMARY 声称的哈希一致）；15 条 rejected 原样在盘；冻结语义代码级确认（judge.py L530-532：已有 verdict 一律 skip，auto/human 一视同仁） |

**Score:** 5/5 truths verified

**Plan-level truths（21-01/02/03 frontmatter）:** 全部核实——帧窗锚点/clamp（test_frame_ts_window_anchors/endpoint_clamp）、FakeSigLIP 精确 cos（test_fake_siglip_exact_per_position_cos）、浅合并不丢对侧/不丢 verdict（test_sidecar_shallow_merge_preserves_judge_and_verdict + test_pitfall8_h3_regen_rewrite_preserves_verdict）、degrade 三码（test_scorer_model_missing_degrade + test_engine_unavailable_degrade）、解析容错 7 类 + 重问 ≤2（test_parse_* 矩阵 + test_run_judge_shot_retry_feedback/three_bad_gives_up）、896×512 smoke + overnight 批（overnight_20.log 收尾行 `rendered=19 cache-hit=0 failed=0 sampled=20 skipped=1`，PID 已正常退出）。

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `analysis/roundtrip/scorer.py` | SCORE-01 SigLIP 中段帧轨迹相似度 | ✓ VERIFIED | 660 行；含 `pooler_output`/frame_ts 25-75 窗/cache/per_position_cos；WR-06 sentinel（L565）在 |
| `analysis/roundtrip/judge.py` | SCORE-02 三分类 + --apply-verdict 冻结应用器 | ✓ VERIFIED | 922 行；`apply-verdict`/`--summarize`/retry-with-feedback/WR-01 prompt_version key 全在 |
| `tests/test_scorer.py` | 帧窗数学 + cache + degrade 离线单测（≥250 行） | ✓ VERIFIED | 639 行 18 用例（超 min_lines） |
| `tests/test_judge.py` | 解析矩阵 + 冻结/合并/schema 单测（≥350 行） | ✓ VERIFIED | 861 行 35+ 用例（超 min_lines） |
| `<EP01>/route_cache/scorer/shot_*.json` | 帧清单 + per_position_cos 审计面 | ✓ VERIFIED | 19 文件 + frames/ 304 jpg；帧窗审计 0 违例 |
| `<EP01>/route_cache/judge/shot_*.json` | grid + attempts + parsed 三件套 | ✓ VERIFIED | 19 文件；attempts 审计 + parsed 结构化 |
| `<EP01>/roundtrip/_judge_grids/*.jpg` | SC3 抽检素材 | ✓ VERIFIED | 19 张 1370×1476 真图（285-676KB） |
| `<EP01>/roundtrip.json` | 19 条双信号 + verdict | ✓ VERIFIED | schema 0 errors；accepted=4（10/61/75/84）/ rejected=15，source 全 auto |
| `.planning/research/roundtrip-threshold-calibration.md` | 校准报告（≥120 行） | ✓ VERIFIED（带 warning） | 346 行七节 FINAL：分位数表 + 反循环论证声明 §3.3 + τ 全档预演 §6.1 + 裁决记录 §6.3；残留 DRAFT 占位节/footer（见 warnings） |
| `.planning/PROJECT.md` | Key Decisions τ_sim 行 | ✓ VERIFIED | L150：τ_sim=0.9670 ∧ prompt_faithful 硬合取 + decided 2026-08-20 + 证据指针 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| scorer.py + judge.py | h3_regen.py 共享件 | importlib spec_from_file_location | ✓ WIRED | 两文件各 1 处；`h3s._iter_sidecar_errors`/`append_roundtrip_warnings` 实跑有效 |
| judge.py | engine_clients/qwen_eye_client | `from engine_clients.qwen_eye_client import`（L92） | ✓ WIRED | sys.path parent.parent off-by-one 处理正确；19 次真调用产物在盘 |
| scorer.py | route_cache/scorer/shot_XXX.json | per_position_cos + 帧清单落盘 | ✓ WIRED | 19 cache 全含 8 元 per_position_cos + 16 帧清单 |
| judge.py --apply-verdict | roundtrip.json | READ-merge 冻结写入 | ✓ WIRED | 验证器独立重跑 applied=0 frozen=19，sha256 不变 |
| 19 镜双信号 | 校准报告 | --summarize 分位数/分桶/τ 预演 | ✓ WIRED | §4.3 表 + §6.1 全 21 档预演与 sidecar 数据逐镜核对一致 |
| 裁决记录 | PROJECT.md Key Decisions | append-only 行 | ✓ WIRED | L150 格式合乎既有行式样 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| roundtrip.json scores | midframe_sim.score | SigLIP so400m 真权重 GPU0 前向（cache key 含 regen_mp4_sha256_16） | Yes — 19 镜分数连续分布 0.8382-0.9828、per_position_cos 逐位各异 | ✓ FLOWING |
| roundtrip.json scores | judge.attribution/reason | qwen-eye 真 grid 真调用（cache 含 attempts raw_len + grid 指针） | Yes — reason 引用 prompt 原文短语（报告 §5.2 摘录） | ✓ FLOWING |
| 校准报告 §4.3/§6.1 | 分位数/τ 预演 | sidecar 19 镜实测 | Yes — 与验证器直读 sidecar 的逐镜值一致（shot 84=0.9670 边界含 ≥） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全套件测试 | `python3 -m pytest tests/ -q` | 171 passed (3.77s) | ✓ PASS |
| spec 校验门 | `python3 spec/validate.py` | exit 0，全 fixture failures=0 | ✓ PASS |
| Phase 18 schema gate | `h3s._iter_sidecar_errors(roundtrip.json)` | 0 errors | ✓ PASS |
| 帧窗审计 | 遍历 19 scorer cache 全部 frames | 304/304 帧落 [25,75]，0 违例 | ✓ PASS |
| SC5 幂等 | 重跑 `--apply-verdict --tau-sim 0.9670` | applied=0 frozen=19 skipped=0，rc=0，sha256 字节级不变 | ✓ PASS |
| 硬合取判定 | sidecar 19 镜 vs τ=0.9670 | accepted 恰 = {sim≥τ ∧ faithful} = {10,61,75,84}（84 在边界 ≥ 含）；rejected=15（faithful<τ=6 + diverged=9） | ✓ PASS |
| overnight 批完成 | tail overnight_20.log | `rendered=19 cache-hit=0 failed=0 sampled=20 skipped=1`，PID 已退出 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SCORE-01 | 21-01, 21-02 | 中段帧 SigLIP 轨迹相似度，显式排除 t=0/t=end | ✓ SATISFIED | scorer.py + 19 真机分数 + 帧窗 0 违例审计 |
| SCORE-02 | 21-01, 21-02 | VLM judge 三分类结构化 verdict | ✓ SATISFIED | judge.py + 19 parsed 结构化归因 + grid/attempts 审计 |
| SCORE-03 | 21-03 | ep01 ≤20 镜实测分布 → 锁双门槛，rejected 占比可审计 | ✓ SATISFIED | 19 镜分布 + τ_sim=0.9670 锁定 + PROJECT.md L150 + §6.1/§6.3 分桶审计 |
| DATASET-01 | 21-01, 21-03 | verdict 合并写 roundtrip.json，rejected 永不删除 | ✓ SATISFIED | 19 verdict schema 合法；15 rejected 在盘；幂等重跑字节级不变 |

**Orphaned requirements:** 无 —— REQUIREMENTS.md 映射 Phase 21 的 ID 恰为 SCORE-01/02/03 + DATASET-01，与三份 PLAN frontmatter 声明的并集完全一致；REQUIREMENTS.md L39-44 四项均已勾选。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| scorer.py/judge.py/tests | L7/L27/L113/L50 | `XXX` 命中 | ℹ️ Info | 文件名通配惯例 `shot_XXX_regen.mp4`，非债务标记——误报排除 |
| 校准报告 | L299-304, L345 | 残留 "待裁决后回填" 占位节 + footer "status: DRAFT" | ⚠️ Warning | 与头部 FINAL 矛盾、§6.3 编号重复（L236/L299）——裁决内容本身完整在 §6.3 最终裁决记录，纯文档卫生；建议 Phase 22 前顺手清理 |
| .planning/STATE.md | stopped_at | 仍写 "待 Kai 裁决"（裁决已完成） | ⚠️ Warning | stale 一行；status: verifying 与当前工作流一致，orchestrator 收口时自然刷新 |

无 TBD/FIXME/TODO/HACK/PLACEHOLDER 债务标记；无 stub 实现（scorer/judge 全链真机跑通，171 测试含 FakeSigLIP/FakeEye 契约面）。

### Human Verification Required

None remaining —— 本 phase 唯一人工门（SC3 抽检 5 镜 + τ_sim 裁决）已按 plan 的 blocking checkpoint 设计由 Kai 完成（2026-08-20：τ_sim=0.9670 + 抽检 approved），记录于校准报告 §6.3 + PROJECT.md L150，orchestrator 交接上下文与在盘证据一致。HITL 复核覆盖（human verdict 改写）按计划属 Phase 22 PRESENT-01。

### Gaps Summary

无 goal-blocking 缺口。5/5 ROADMAP success criteria 全部以代码 + 在盘数据 + 验证器独立实跑（schema gate / 帧窗审计 / 幂等重跑 / pytest / validate）核实。SUMMARY 声称的关键数字（19 镜、accepted=4 shots 10/61/75/84、rejected=15 = faithful<τ 6 + diverged 9、sha256 63543baf…336dd73、171 passed）与代码库实际状态逐项一致，未发现虚报。两条 Warning 均为文档卫生（报告残留 DRAFT 占位节 + STATE stopped_at stale），不影响 goal 达成，建议随下一 phase 收口顺手清理。

---

_Verified: 2026-08-20T03:21:43Z_
_Verifier: Claude (gsd-verifier)_
