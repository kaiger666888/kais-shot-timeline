---
phase: 21-scorer-threshold-calibration
plan: "01"
subsystem: testing
tags: [siglip, transformers, trajectory-similarity, qwen-eye, judge, verdict, threshold-calibration, offline-tests]

# Dependency graph
requires:
  - phase: 20-h3-regen-client
    provides: roundtrip.json regen 半边 + h3_regen 共享 helper（importlib 复用：_atomic_write_json/_load_schema_version/_iter_sidecar_errors/append_roundtrip_warnings/video_content_hash）
  - phase: 19-qwen-eye-v2
    provides: engine_clients.qwen_eye_client（ENGINE_NAME/ENGINE_VERSION/QwenEye.observe_single）+ comfy_free 编排先例
provides:
  - analysis/roundtrip/scorer.py —— SCORE-01 SigLIP 中段帧轨迹相似度打分器（N=8 @25%-75% 时窗 + route_cache/scorer 断点缓存 + scorer_model_missing 三码 degrade）
  - analysis/roundtrip/judge.py —— SCORE-02 qwen-eye 三分类归因（2×4 对比 grid + retry-with-feedback 解析）+ SCORE-03 --apply-verdict 硬合取冻结应用器 + --summarize 校准素材汇编器
  - tests/test_scorer.py + tests/test_judge.py —— FakeSigLIP/FakeEye 全链替身 38 用例（零 GPU 零网络）
affects: [21-02 GPU smoke, 21-03 uniform-20 校准批, 22 Dataset Export]

# Tech tracking
tech-stack:
  added: []   # 零新 pip 依赖（transformers/torch/PIL 均已在环境）
  patterns:
    - "importlib spec_from_file_location 复用 h3_regen 共享 helper（h3_regen.py 零修改）"
    - "scores 子对象浅合并 + verdict 冻结 pop（两个写入器互不破坏对偶半边，Pitfall 8 双向）"
    - "两层 WR-04 自校验（本批坏 sys.exit / 预存坏剔除+.bak-<ts>+str warning）"
    - "retry-with-feedback：parse 错误码回喂进下一问（1+2 次上限）"
    - "FakeSigLIP/FakeEye 确定性替身（cos 目标值手写、PIL 真 JPEG bytes）"

key-files:
  created:
    - analysis/roundtrip/scorer.py
    - analysis/roundtrip/judge.py
    - tests/test_scorer.py
    - tests/test_judge.py
  modified: []

key-decisions:
  - "frame_ts = dur·(0.25+0.5·j/(n-1)) + 0.2s 端点 clamp——t=0/t=end 结构性不可达（Pitfall 3 实测锚 7.2917→7.0917）"
  - "parse_judge_answer 显式排除 bool confidence（JSON true 是 int 子类，会穿 isinstance 后被 schema number 拒——Rule 2 补漏）"
  - "score 钳 [0,1] 后再 round；per-position 原始 cos 不钳进 cache（审计纯度）"
  - "硬合取无置信门：accepted ⇔ sim ≥ τ ∧ attribution == prompt_faithful"
  - "SC2 审计面：cache 记 per_position_cos + attempts（parse 码+raw_len）逐次留档"

patterns-established:
  - "scores 半边写入器模板：READ-merge by shot_id + scores 浅合并 + kept-keys 全保留（scorer/judge 同骨架，仅子对象 key 不同）"
  - "引擎编排模板：全 cache 命中零实例化；miss → comfy_free(GPU1 free) → ensure_ready 失败 sleep(30) 重试一次 → 仍败 str warning + rc=0；finally stop_if_owned"

requirements-completed: []   # SCORE-01/SCORE-02/DATASET-01 保持未勾选——本 plan 交付离线代码半边，21-02 GPU smoke 与 21-03 校准批共享同 requirement IDs（mirror 18-01/19-01/20-01 先例）

# Metrics
duration: 15m
completed: 2026-08-20
---

# Phase 21 Plan 01: Scorer + 阈值校准（离线半边）Summary

**SigLIP 中段帧轨迹相似度打分器 + qwen-eye 三分类归因 judge + --apply-verdict 硬合取冻结应用器，全离线 FakeSigLIP/FakeEye 替身 38 用例零 GPU 验证（157 passed 零回归）**

## Performance

- **Duration:** ~15m
- **Started:** 2026-08-20 06:15 (本地)
- **Completed:** 2026-08-20 06:28 (本地)
- **Tasks:** 3/3
- **Files modified:** 4（全部新建，h3_regen.py/spec/ 零改动）

## Accomplishments

- **scorer.py（565 行）**：SCORE-01 SigLIP so400m-patch14-384 打分——ffmpeg 逐帧抽取（N=8 @25%-75% 时窗 + 0.2s 端点 clamp，t=0/t=end 结构性排除）、`get_image_features().pooler_output` (B,1152) L2 归一余弦、per_position_cos 全留档 + score=mean 钳 [0,1]、5 字段 cache key 断点续跑（全命中零模型加载）、SigLIP 加载失败 → `scorer_model_missing` str warning + rc=0（sidecar 不动）
- **judge.py（821 行）**：SCORE-02 三分类归因——PIL 2×4 对比 grid（1370×1476，ORIGINAL/REGEN 列头 + t=0/33%/67%/end 行标签全部进图）、parse_judge_answer 六码解析（fence 剥离→花括号抽取→严格校验，reason ≥10 字符）、retry-with-feedback（1+2 次，错误码回喂下一问）；SCORE-03 `--apply-verdict` 冻结应用器（硬合取 accepted ⇔ sim ≥ τ ∧ prompt_faithful；预存 verdict 永不覆盖；缺信号跳过 + warning 列 shot_id）；`--summarize` 分位数/三桶/τ 预演汇编器（inclusive 线性插值，与 numpy linear 同义）
- **双写入器互不破坏**：scores 子对象浅合并（scorer 写 midframe_sim 不丢 judge，反向亦然）+ verdict 冻结 + 两层 WR-04 自校验（本批坏 sys.exit / 预存坏剔除 + .bak-<ts> 备份）——Pitfall 8 双向 e2e 测试锁定
- **测试 38 新用例**：test_scorer.py 11 + test_judge.py 27，全套件 157 passed（基线 119 零回归），3.58s，零 GPU 零网络零新依赖

## Task Commits

Each task was committed atomically:

1. **Task 1: scorer.py — SCORE-01 SigLIP 中段帧轨迹相似度模块** - `7225988` (feat)
2. **Task 2: judge.py — SCORE-02 三分类归因 + --apply-verdict 冻结应用器** - `106a413` (feat)
3. **Task 3: scorer/judge 离线单测（FakeSigLIP/FakeEye 全链替身）** - `6628de4` (test)

**Plan metadata:** （见下方最终 docs commit）

## Files Created/Modified

- `analysis/roundtrip/scorer.py` - SigLIP 打分器：帧窗规划/ffmpeg 抽帧/嵌入余弦/5 字段 cache/scores.midframe_sim 半边写入 + scorer_model_missing degrade
- `analysis/roundtrip/judge.py` - 三分类归因 judge：grid 合成/提示词构造/六码解析/重问/4 字段 cache + --apply-verdict + --summarize + 引擎编排（comfy_free → ensure_ready → retry → finally stop_if_owned）
- `tests/test_scorer.py` - 406 行/11 用例：帧窗锚点、FakeSigLIP 精确 cos（tol 1e-6）、cache 审计、浅合并对向、degrade、ffmpeg fail-loud
- `tests/test_judge.py` - 729 行/27 用例：解析矩阵 7 码、grid 布局像素采样、retry 审计、批 e2e（reason 截 2000/comfy_free 双布尔）、零实例化、引擎 degrade、apply-verdict 三态/冻结/缺信号、Pitfall 8 双向、WR-04 剔除+.bak、summarize 精确值

## Decisions Made

- **帧窗公式 + 端点 clamp**：`ts = dur·(0.25+0.5·j/(n-1))`，`min(ts, max(dur-0.2, 0.0))`——175f/24fps regen 流末帧 -ss 7.252 取不到帧（Pitfall 3），0.2s guard 结构性规避；t=0/t=end 在 N=8 布局下本就不可达，grid 行标签如实标注
- **bool confidence 显式排除（Rule 2 补漏）**：JSON `true` 是 int 子类，会穿 `isinstance(c,(int,float))` 后被 schema number 类型拒收触发本批 sys.exit——解析层提前拦到 conf-range 码
- **score 钳 [0,1] 后 round，per-position 原始 cos 不钳**：浮点过冲不炸 schema maximum，审计面保真
- **硬合取无置信门**：confidence 只留档不参与判定（plan 契约；校准期保持规则最简）
- **summarize buckets 只看归因、tau_preview 只看双信号齐备对**：n 如实计全部镜（分布分母不缩水），缺信号镜不进 τ 预演

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] parse_judge_answer 排除 bool confidence**
- **Found during:** Task 2（judge.py 解析器实现）
- **Issue:** RESEARCH Pattern 2 探针代码用 `isinstance(c,(int,float))` 校验 confidence——JSON `true` 会以 int 子类穿过、随后被 schema number 类型拒收，触发本批条目 sys.exit（fail-loud 误伤合法批次）
- **Fix:** 追加 `isinstance(c, bool)` 显式排除，bool 归 conf-range 码
- **Files modified:** analysis/roundtrip/judge.py（parse_judge_answer）
- **Verification:** tests/test_judge.py::test_parse_conf_range_three_forms 第三态断言
- **Committed in:** 106a413（Task 2 commit）

**2. [Rule 3 - Blocking] 测试替身需真 PIL 可读 JPEG bytes**
- **Found during:** Task 3（test_scorer.py 首跑 6 败）
- **Issue:** fake ffmpeg 写 `b"\xff\xd8fake-jpeg"` 假头——scorer/judge 的 `Image.open`/processor 链抛 UnidentifiedImageError（假字节过不了 PIL 解码器）
- **Fix:** `_valid_jpeg_bytes()` 用 PIL 真生成 64×36 JPEG 并缓存；两测试文件共用该模式
- **Files modified:** tests/test_scorer.py, tests/test_judge.py
- **Verification:** 38 用例全绿（0.32s）
- **Committed in:** 6628de4（Task 3 commit）

---

**Total deviations:** 2 auto-fixed（1 missing critical + 1 blocking）
**Impact on plan:** 两项均为正确性必需（schema 拒收误伤 / 替身不可解码），无 scope creep。

### TDD 顺序说明（非 deviation，记录在案）

Task 1/2 frontmatter 带 `tdd="true"`，但 plan 契约把全部测试显式放在 Task 3（`<files>` 两个测试文件 + min_lines 250/350 + ≥20 用例验收），且 must_haves 限定恰好 4 个新文件——按 plan 结构执行（Task 1/2 走 anchor 脚本验证，Task 3 一次性交付 RED→GREEN 语义的测试批）。测试与实现同 plan 内闭环，gate 意图（行为先于重构锁定）满足。

## Issues Encountered

- test_scorer.py 首跑 6 败（1 个根因：假 JPEG 字节不可解码 → 4 个级联 + 1 个 t_pct 4 位小数舍入超 1e-6 容差）——分别以 `_valid_jpeg_bytes()` 与直接对未舍入公式断言修复，无实现侧改动
- test_judge.py 首跑 9 败（3 个根因：FakeEye 类未实例化即传入 / `validate_sidecar` 误引不存在的 `jm.SCHEMA_PATH` / p75 手算错 0.945→实测 0.935 且 buckets 语义按实现文档为准）——全部测试侧修正，judge.py 零改动

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - 无占位实现。scorer/judge 的模型加载与引擎调用在 21-02（GPU smoke）真机验证，本 plan 的替身测试即为其契约面。

## Next Phase Readiness

- 21-02（GPU smoke）：`python3 analysis/roundtrip/scorer.py --work-dir <ep02 资产>` / `judge.py --work-dir ...` 真机跑法已在两文件 docstring；SigLIP 权重需 HF cache 离线可达（HF_HUB_OFFLINE 已在模块内 setdefault）
- 21-03（uniform-20 校准批）：`--summarize` 输出分位数/三桶/τ 预演即校准素材；`--apply-verdict --tau-sim <τ>` 冻结应用
- 依赖就绪：20-03 已备 regen 素材 sidecar；19-03 eye 串行编排先例可复用

## Self-Check: PASSED

- 文件存在：analysis/roundtrip/scorer.py / analysis/roundtrip/judge.py / tests/test_scorer.py / tests/test_judge.py 全 FOUND
- commit 存在：7225988 / 106a413 / 6628de4 全 FOUND（git log --all）
- 红线复核：h3_regen.py + spec/ 对 HEAD~3 diff 为 0 行；`torch_dtype` 字符串 grep 0 处；全套件 157 passed

---
*Phase: 21-scorer-threshold-calibration*
*Completed: 2026-08-20*
