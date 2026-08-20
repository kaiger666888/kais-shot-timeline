---
phase: 19-qwen-eye-v2
plan: 01
subsystem: analysis
tags: [qwen-eye, vl, facets, vision-seq, ear, cache, offline-tests]

# Dependency graph
requires:
  - phase: 18-contract-v1.3
    provides: v1.3 契约层（roundtrip schema 家族，本 plan 无直接消费但同 milestone 前置）
  - phase: v1.2-phases-10-17
    provides: audio_semantic.json 数据形状（ear 白名单输入）、local_vision v1 全套先例（生命周期/cache/degrade/写保护）
provides:
  - qwen_eye_client.observe_pair / ask_text 本地扩展（相邻帧对问 + 纯文本合并入口，均走 _call_llm）
  - analysis/vision_seq_facets.py v2 模块（均匀 ≤8 帧采样、action 逐帧问、camera 相邻对问、双信封 RAW cache、ear 白名单注入、temporal/llm/longest 三策略合并、只填空缺、预判生命周期、零修改短路）
  - 22 个新离线单测（2 客户端 shape + 20 模块矩阵），全套 58 passed
affects: [19-02-spike, 19-03-wiring, 20-h3-regen, 21-scorer]

# Tech tracking
tech-stack:
  added: []   # 零新 pip 依赖（SC4 硬约束）
  patterns:
    - "cache 双信封（ear_on/ear_off 同文件共存，read-merge-write 只更新本 ear）"
    - "cache 存 RAW 逐帧/逐对答案（合并纯归约，策略切换零 GPU 重烧）"
    - "cache 覆盖预判：pending 空 → QwenEye 零实例化（全命中重跑秒级）"
    - "RAW 答案增量落盘（每调用一次即写 cache —— spike 中断恢复不丢已答帧）"
    - "零修改短路：零 facet 改动 → 不重写输出不建 sidecar（byte-identical 证明）"

key-files:
  created:
    - analysis/vision_seq_facets.py
    - tests/test_vision_seq_facets.py
  modified:
    - analysis/engine_clients/qwen_eye_client.py
    - tests/test_qwen_eye_client.py

key-decisions:
  - "merged_B 按 facet 分键存 dict（{action, camera}）—— plan 契约 JSON 的单串占位无法承载两 facet 各自合并结果"
  - "RAW 答案键存在即已问（空答案也落 cache 为 \"\"）—— 防「引擎回空 → 键缺席 → 每轮重问」死循环；合并只 join 非空值"
  - "facet 产出要求 RAW 证据完整（缺失键/本轮 error → 不产出）—— 完整证据或空缺，绝不用半截序列合并"
  - "llm 策略 + merged_B 未缓存 + 引擎不可用 → facet 保持 \"\"（严格策略语义，不静默降级成 temporal）"
  - "信封内不存 shot_id（文件名已编码）—— 保持 cache 契约 JSON 恰为 _cache_key/answers/merged_B 三键"
  - "VISION-01/02 保持未勾选 —— 本 plan 只交付模块+单测半边，spike 锁定（19-02）与 wiring（19-03）共享同 requirement IDs（mirror 18-01 先例）"

patterns-established:
  - "%% 转义：argparse help 含 f%06d 这类裸 % 格式串必须写 %%，否则 --help 直接 TypeError"

requirements-completed: []   # VISION-01/02 属 phase 级，spike+wiring 完成后才勾（见 key-decisions）

# Metrics
duration: 13min
completed: 2026-08-19
---

# Phase 19 Plan 01: qwen-eye v2 核心模块与客户端扩展 Summary

**qwen_eye_client 加 observe_pair（两条 user 各一图规避 llama.cpp 多图丢弃 bug）/ask_text（纯文本合并）入口；新建 vision_seq_facets.py v2 模块（均匀 ≤8 帧采样 + action 逐帧问 + camera 相邻对问 + ear 白名单注入 + 双信封 RAW cache + 三策略合并 + 只填空缺 + 预判生命周期 + 零修改短路），22 个新离线单测全套 58 passed，v1 文件零字节改动**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-08-19T17:36:03Z
- **Completed:** 2026-08-19T17:49:00Z
- **Tasks:** 3/3
- **Files modified:** 5（4 个 files_modified + deferred-items.md）

## Accomplishments
- 客户端两个受控入口落地且 shape 测试锁定：observe_pair 恰两条 user 各一图一文本、问句只在第 2 条、两图 base64 对应 a/b；ask_text 单 user 纯 text 零图。均经 `_call_llm`（enable_thinking:false 恒传只此一处设置），禁改区（生命周期/ENGINE_NAME/ENGINE_VERSION/_call_llm）零触碰。
- v2 模块完整交付 CONTEXT 全部锁定决策：MAX_SEQ_FRAMES_PER_SHOT=8 新常量（v1 的 3 帧上限不受影响）、route_cache/vision_seq/ + PROMPT_VERSION="vision-seq-v1" + ear 第 5 维进 cache key、ear 白名单注入（dialogue.text 截断/emotion/sfx.events/description；words/reproduction/spk_id 永不进）、--no-ear + 文件缺席静默 degrade、只填空缺永不覆盖（无更短替换）。
- cache 存 RAW 逐帧/逐对答案（action_frame_N/camera_pair_M + merged_B）—— 合并纯归约，策略切换零 GPU 重烧；SC4 预判（全命中零 QwenEye 实例化）与 SC3 单元级（ear 含/不含子串 + 白名单负测试）都有机器证明。

## Task Commits

Each task was committed atomically:

1. **Task 1: qwen_eye_client 扩展 observe_pair / ask_text + shape 单测** - `afc6c88` (test, TDD RED) + `bef80cc` (feat, TDD GREEN)
2. **Task 2: 新建 analysis/vision_seq_facets.py v2 模块** - `51faa41` (feat)
3. **Task 3: tests/test_vision_seq_facets.py 离线单测矩阵** - `91ebd8a` (test)

**Plan metadata:** 本文件所在 commit（docs: complete plan）

## Files Created/Modified
- `analysis/engine_clients/qwen_eye_client.py` - +observe_pair/ask_text 两方法（紧随 observe_single，mirror 上游 observe() 多 user 消息 shape）；头部裁剪清单注释与 docstring 用法示例同步更新
- `analysis/vision_seq_facets.py` - v2 帧序列逐帧问答 facet 升级模块（656 行，mirror v1 全套惯例 + 全部 v2 新逻辑）
- `tests/test_qwen_eye_client.py` - +2 shape 测试（monkeypatch _call_llm 捕获写法 mirror 既有 test_observe_single_request_shape）
- `tests/test_vision_seq_facets.py` - 20 用例离线矩阵（importlib 加载 + FakeEngine 零网络）
- `.planning/phases/19-qwen-eye-v2/deferred-items.md` - v1 --help latent bug 记档（scope boundary）

## Decisions Made
（除 frontmatter key-decisions 外补充）
- ear 提问形式照 plan 锁定原文 `f"该镜音频：{audio_ctx}。{基础提问}"`（RESEARCH 示例的「结合这一帧」变体不采用 —— plan 契约优先）。
- `--video` 保持 mirror v1 的可选语义（缺席 → "unknown"），未按 interfaces 用例行升为 required —— task action 明文「mirror v1 参数集」。
- build_audio_context 在 RESEARCH 成品之上加 isinstance 硬化（plan 的 V5 语义要求：类型错跳过该字段）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] --help 因裸 % 格式串崩溃**
- **Found during:** Task 2（argparse 冒烟验收）
- **Issue:** `--frames-dir` help 含 `f%06d.jpg`，argparse 对 help 做 `%` 格式化 → `TypeError: %d format: a real number is required, not dict`，`--help` 无法打印（acceptance criterion 硬项）
- **Fix:** help 文案改写 `f%%06d.jpg`（argparse 转义），一行修复
- **Files modified:** analysis/vision_seq_facets.py
- **Verification:** `python3 analysis/vision_seq_facets.py --help` 正常打印全部 flags；pytest 全套绿
- **Committed in:** `51faa41`（Task 2 commit）

**2. [Scope boundary - 记档不修] v1 local_vision_facets.py 存在同款 --help latent bug**
- **Found during:** Task 2
- **Issue:** v1 `--frames-dir` help 同样含裸 `%06d`，`--help` 同样 TypeError（pre-existing，非本 plan 引入）
- **Fix:** 不修（v1 是零改动红线）—— 记入 `.planning/phases/19-qwen-eye-v2/deferred-items.md`，留待未来触碰 v1 的 phase 一行 `%%` 修复
- **Verification:** `python3 analysis/local_vision_facets.py --help` → Traceback（复现确认）

---

**Total deviations:** 1 auto-fixed（Rule 1）+ 1 out-of-scope 记档
**Impact on plan:** 修复是 acceptance criterion 的必经项，无 scope creep；v1 latent bug 记档符合 scope boundary 规则。

## Issues Encountered
- Task 3 的 tdd 标记在 plan 任务序（Task 2 先交付模块）下无法做严格 RED→GREEN 分离；Task 1 已按完整 TDD 双 commit 执行（RED afc6c88 → GREEN bef80cc），Task 3 为测试后置编写（20/20 首跑即绿，未发现模块缺陷需要回改）。

## User Setup Required

None - no external service configuration required.（本 plan 全离线；引擎/GPU 是 19-02 spike 的事）

## Next Phase Readiness
- 19-02 spike 可直接消费本模块 CLI（--merge-strategy 三策略 + --audio-semantic/--no-ear 双跑）与 RAW cache（断点续跑已内置：每调用增量落盘）；spike 镜建议用 RESEARCH ep01 盘点表（#91/#88/#66/#46/#70/#1）。
- 19-03 wiring 消费 CLI 契约（Pattern 4：--audio-semantic 由 run_pipeline :736 变量传入，存在性模块自判）。
- 无 blockers；v1 --help latent bug 与 audio-analysis 路由 404 均为已知 deferred，不阻塞。

## Self-Check: PASSED

- 4 个交付文件全部在档（2 源文件 + 2 测试文件 + SUMMARY.md）
- 4 个 task commit 全部可查（afc6c88 / bef80cc / 51faa41 / 91ebd8a）
- `python3 -m pytest tests/ -q` → 58 passed（基线 36 → 38 → 58，既有测试零回归）

---
*Phase: 19-qwen-eye-v2*
*Completed: 2026-08-19*
