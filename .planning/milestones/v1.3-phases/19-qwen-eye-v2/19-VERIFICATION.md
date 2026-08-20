---
phase: 19-qwen-eye-v2
verified: 2026-08-20T00:00:00Z
status: passed
score: 16/16 must-haves verified
overrides_applied: 0
deferred: # Items documented out-of-scope — informational, not gaps
  - truth: "v1 local_vision_facets.py 同款 --help 裸 % latent bug 与 select_frames floor off-by-one 镜像"
    addressed_in: "未排期（v1 零改动红线约束，REQUIREMENTS Future 未列）"
    evidence: "deferred-items.md + 19-REVIEW-FIX.md「Deferred（v1 镜像，本 phase 不修）」"
  - truth: "detect_v3b 写 frames fps sidecar（彻底解旧 fps 采样错配）"
    addressed_in: "未排期（需触碰 validated 基线模块，REVIEW-FIX 建议另开小 phase）"
    evidence: "19-REVIEW-FIX.md WR-02 残留缺口"
---

# Phase 19: qwen-eye v2 看片段 Verification Report

**Phase Goal:** prompts.json 的 action/camera facet 从「3 静帧脑补」升级为「≤8 帧序列逐帧实证」（llama.cpp 单图 bug 硬约束下的务实版），v1.2 `audio_semantic` 作为 ear 融进视觉 prompt——独立于 round-trip 闭环就提升 prompt 质量。
**Verified:** 2026-08-20
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| - | ----- | ------ | -------- |
| 1 | SC1: 空缺 action/camera 被 v2 跨帧合并产物填充（与 v1 差异可见）；只填空缺永不覆盖（用户 smart-discuss 裁决措辞，Area 3 Q2 2026-08-19） | ✓ VERIFIED | `spike/vision_seq/results/sc1_evidence.txt` 六镜填充前后并排（temporal 链 200-360 字 vs v1 单句 20-40 字）；sandbox/prompts.json 实测 6/6 目标镜双 facet 非空；代码守卫 `vision_seq_facets.py:601-602`（`if p.get(facet): continue`，无更短替换逻辑）；单测 `test_existing_facet_not_overwritten` |
| 2 | SC1 负测试: live ep01 prompts.json 不被覆盖 | ✓ VERIFIED | 本 verifier 独立复算 `sha256sum` = `7cc4a4841e7f…afaced5`，与 sc1_evidence.txt/报告/19-02 三处记录完全一致（跑前=跑后=今天） |
| 3 | SC2: 合并策略 A/B + baseline 在 ep01 小样本 spike 对比后锁定，结论记录在案（人工盲评主判据） | ✓ VERIFIED | 报告 FINAL（无 DRAFT）含「锁定结论（SC2 收口）」节：Kai 盲评锁定甲=temporal（2026-08-20），映射 `results/strategy_mapping.txt` 回写；真实 GPU 实证 147 calls ≈15.5 min 逐 step 记录；反循环论证声明 + 盲评表（甲/乙/丙匿名）在档 |
| 4 | SC2: 锁定值成为模块默认 | ✓ VERIFIED | `vision_seq_facets.py:123` `MERGE_STRATEGY_DEFAULT = "temporal"`（本 verifier import 实测断言通过）；wiring 后生产路径默认 temporal |
| 5 | SC3: ear 融合可见生效（音频驱动「一类修正」） | ✓ VERIFIED | `results/ear_diff.md` + 报告 ear diff 节：#1「正闭眼倒数等待对方逗它开心」（对白「八七六」）、#88「挂着泪珠/屏息聆听」、#91「焦急地呼喊爸爸」（ear_off 靠读内嵌字幕）——音频系统性改变动作语义解读；Kai 同 checkpoint 复核 confirmed |
| 6 | SC3: --no-ear 跳过后输出与不带 ear 版本一致（additive、可跳过） | ✓ VERIFIED | 单测 `test_ear_absent_vs_no_ear_byte_identical`（byte-identical）+ `test_no_ear_flag_excludes_audio` + `test_audio_file_absent_silent_no_ear`（缺席零 warning）；ear 双信封隔离 `test_ear_envelope_isolation_dual_coexistence` |
| 7 | SC4: 重复运行幂等——cache 命中零 GPU、重跑秒级 | ✓ VERIFIED | 单测 `test_cache_hit_second_run_zero_engine_calls` + `test_full_cache_hit_never_instantiates_engine`（对当前 v2 代码）；runtime 实测 0.968s/0.939s（sc1_evidence.txt §3）；每调用增量落盘断点续跑（`_save_cache_envelope` per-answer write） |
| 8 | SC4: 零新引擎、零新模型下载 | ✓ VERIFIED | 模块仅经 `engine_clients/qwen_eye_client.py` 既有入口（observe_single/observe_pair/ask_text）；grep 零新网络端点/零 HF 下载代码；v1 `local_vision_facets.py` git 历史最后一次触碰 = Phase 1（d16ee6d，红线保持） |
| 9 | 19-01: qwen_eye_client 具备 observe_pair（两条 user 各一图规避多图丢弃 bug）与 ask_text（纯文本零图），均走 _call_llm 恒禁 thinking | ✓ VERIFIED | `qwen_eye_client.py:320-356` 两方法实读核对（shape 与 plan 逐字一致）；`test_observe_pair_request_shape`/`test_ask_text_request_shape`/`test_call_llm_always_disables_thinking`；`_call_llm` 直调检查 `grep _call_llm vision_seq_facets.py` = 0 |
| 10 | 19-01: vision_seq_facets.py 离线可加载且全套特性在位 | ✓ VERIFIED | 743 行模块实读 + 本 verifier 10 项 spot-check 全过（均匀 ≤8 帧/首尾在列/_ds 忽略/CR-01 ceil 修正/ear 白名单负测试/ear 提问注入/合并确定性/ear 第 5 维 cache key）；73 tests passed |
| 11 | 19-01: 既有测试零回归（v1 零改动） | ✓ VERIFIED | `python3 -m pytest tests/ -q` → **73 passed**（本 verifier 实跑）；git status 干净；`spec/validate.py` exit 0（minimal/v1.1/v1.2/v1.3/smoke 全 0 failures） |
| 12 | 19-02: sandbox（facet 置空副本）GPU 双跑 + RAW cache 断点续跑 | ✓ VERIFIED | 盘上 cache 实检：sandbox 6 镜 ear_off + sandbox_ear 3 镜 ear_on，各 15 RAW answers（8 action_frame + 7 camera_pair）；run.log 记录四步进度 |
| 13 | 19-02: 三策略同镜产物 + 客观指标 + 匿名盲评表落 spike report | ✓ VERIFIED | 报告 495 行：Evidence 节 6 镜 × 三策略 + v1 参照 + 指标（len/连接词密度/bigram 覆盖率）；盲评表甲/乙/丙；「机器可见观察」节诚实记录主体漂移/字幕读入/camera 对问矛盾 |
| 14 | 19-03: run_pipeline 无编号 pre-step 5.6 挂载（5.5 后 step_reid 前、plain banner、不 bump counter） | ✓ VERIFIED | `run_pipeline.py:848-866` 实读：条件四连 + subprocess 按路径 + `"vision seq facets (qwen-eye v2 pre-step)"` plain label；`grep '\[5\.6/9\]'` 零命中；`test_pre_step_wiring_static`（三连顺序 + --audio-semantic + --frame-fps 在 cmd 构造内）+ `test_step_banner_count_unchanged` |
| 15 | 19-03: --no-vision-seq 跳过 / --no-ear 直通 / --audio-semantic 传 step 7 路径 | ✓ VERIFIED | argparse 三 flag 实读（:696-704）+ `run_pipeline.py --help` 实跑三 flag 可见 + argparse spy 测试（默认 vision_seq=True/no_ear=False，no-flag 翻转）；:858 `--audio-semantic audio_semantic_json`（存在性模块自判） |
| 16 | 19-03: SC1/SC4 wiring 形态集成证据落报告 | ✓ VERIFIED | 报告「SC1/SC4 集成证据（post-wiring）」节（:420）+ sc1_evidence.txt 132 行（全部命令原文 + 双哈希 + 计时表，可独立复验——本 verifier 已复验 live sha） |

**Score:** 16/16 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `analysis/vision_seq_facets.py` | v2 模块全套 | ✓ VERIFIED | 743 行；存在+实质+wired（run_pipeline 5.6 subprocess + 28 单测）；数据流贯通（cache 15 RAW/镜 → 合并 → sandbox prompts.json 实填充） |
| `analysis/engine_clients/qwen_eye_client.py` | observe_pair/ask_text 扩展 | ✓ VERIFIED | 两方法在位走 _call_llm；WR-03 生命周期修复（_owned 语义 + KAP release 配对）+3 回归测试 |
| `tests/test_vision_seq_facets.py` | 离线矩阵 ≥250 行 | ✓ VERIFIED | 727 行 / 28 tests 全绿（含 SC3/SC4 单元级断言与全部 review-fix 回归） |
| `tests/test_pipeline_vision_seq_wiring.py` | wiring 四件套 ≥90 行 | ✓ VERIFIED | 107 行 / 4 tests |
| `run_pipeline.py` | 5.6 挂载 + 三 flag | ✓ VERIFIED | 见 truth 14/15 |
| `spike/vision_seq/README.md` | THROWAWAY 声明 | ✓ VERIFIED | THROWAWAY ×2 + sandbox 布局 + 全角括号 pathlib 警告 |
| `.planning/research/vision-seq-spike-report.md` | spike 证据 ≥120 行 | ✓ VERIFIED | 495 行，FINAL，含锁定结论/盲评表/ear diff/Reproducibility/post-wiring 节 |
| `spike/vision_seq/sandbox/prompts.json` | facet 置空副本（v2 填充对象） | ✓ VERIFIED | 6 目标镜已填充、87 镜与 live 逐值同；sandbox_ear 3 镜填充 |

**Artifact `contains` 偏差（设计性，非 gap）：** PLAN 19-01 frontmatter 指定 `PROMPT_VERSION = "vision-seq-v1"`，代码现为 `"vision-seq-v2"`（`vision_seq_facets.py:105`）——19-REVIEW CR-01 修复（时窗下界 floor→ceil）按 fix contract 升版使旧 cache 整体失效，为 review 生命周期内的既定变更，cache 版本旋钮语义（PROMPT_VERSION + ear 第 5 维 + window 契约 + ear_ctx_fp）完整在位且强于 plan 原案。

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `vision_seq_facets.py` | `engine_clients/qwen_eye_client.py` | sys.path 注入 + import | ✓ WIRED | :91-96，QwenEye/ENGINE_NAME/ENGINE_VERSION 三导入 |
| `vision_seq_facets.py` | `route_cache/vision_seq/shot_XXX.json` | 双信封 RAW cache | ✓ WIRED | :598 写 / :259 读；盘上 9 个 shot 文件实测（6 ear_off + 3 ear_on） |
| `run_spike.py` | `vision_seq_facets.py` | subprocess 按路径 | ✓ WIRED | run_spike.py:39 引用 + 每步 CLI 调用 |
| `run_pipeline.py` 5.6 块 | `vision_seq_facets.py` | subprocess `[sys.executable, HERE/analysis/vision_seq_facets.py, …]` | ✓ WIRED | :852，`grep -c vision_seq_facets.py run_pipeline.py` == 1 |
| 5.6 块 | `audio_semantic.json`（step 7 路径变量） | `--audio-semantic` 直传 | ✓ WIRED | :858 引用 `audio_semantic_json` 变量；静态测试锁 |
| 5.5 块 → 5.6 块 → step_reid | 源码顺序 | index 三连 | ✓ WIRED | :827 < :852 < :871，测试断言在档 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| sandbox/prompts.json action/camera | 逐镜 facet 值 | route_cache RAW answers → temporal 归约 | ✓（15 RAW/镜实存，填充值 200-360 字真实引擎产物） | ✓ FLOWING |
| sandbox_ear/prompts.json | 同上（ear_on 信封） | ear 提问（音频白名单注入）→ 引擎 | ✓（3 镜 diff 含音频驱动语义） | ✓ FLOWING |
| spike report Evidence 节 | 三策略文本 | 同一 RAW cache + merged_B | ✓（三策略同源证据，换策略零 GPU 实测） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全套测试 | `python3 -m pytest tests/ -q` | 73 passed in 3.21s | ✓ PASS |
| 模块 --help 冒烟 | `python3 analysis/vision_seq_facets.py --help` | exit 0，全部 flags（含 --frame-fps） | ✓ PASS |
| 管线 --help 三 flag | `python3 run_pipeline.py --help \| grep …` | --vision-seq/--no-vision-seq/--no-ear 均可见 | ✓ PASS |
| CR-01 采样回归 | `select_uniform_frames(dir, 0.5, 2.5, fps=5)` | 首帧 f000004（非 f000003）；对齐窗 [0.4,2.4] 首帧 f000003 | ✓ PASS |
| 均匀采样 ≤8 + 首尾在列 + _ds 忽略 | 31 帧窗 @5fps | 恰 8 帧，窗首/窗尾在列，_ds1280 不入 | ✓ PASS |
| ear 白名单 | `build_audio_context(...words/reproduction/spk_id/speakers...)` | 仅 对白「…」（情绪:…）；音效:…，禁入字段零泄漏 | ✓ PASS |
| ear 提问注入/直通 | `_ear_question` | 有 ctx → 「该镜音频：…。BASE」；无 ctx → BASE 原样 | ✓ PASS |
| 合并确定性 | `merge_answers` | temporal=「→」join；longest=最长单条 | ✓ PASS |
| ear 第 5 维 cache key | `_cache_key(v, True/False)` | 两 key 不等，ear 布尔维在位 | ✓ PASS |
| live sha256 独立复验 | `sha256sum <live ep01>/prompts.json` | = 7cc4a484…afaced5（与三处记录一致） | ✓ PASS |
| sandbox 填充态 | json 检查 | sandbox 6/6、sandbox_ear 3/3 目标镜双 facet 非空，全片零残留空缺 | ✓ PASS |
| 契约回归 | `python3 spec/validate.py` | exit 0，全部 fixtures 0 failures | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED（无 `scripts/*/tests/probe-*.sh` 约定；本 phase 验证靠 pytest + spike 证据链，上表 spot-checks 已覆盖）

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| VISION-01 | 19-01/02/03（三 plan 共享，mirror 18-01 先例） | ≤8 帧逐帧问答升级 action/camera + 合并策略 spike 锁定 + 只填空缺不覆盖 | ✓ SATISFIED | truths 1-4, 7-11, 14-16；REQUIREMENTS.md 已勾 [x] |
| VISION-02 | 同上 | ear 融合（audio_semantic 摘要注入，additive 可跳过 --no-ear） | ✓ SATISFIED | truths 5-6；白名单 + 字节级 byte-identical 单测 + ear diff 实证 |

无孤儿 requirement：REQUIREMENTS.md phase 19 行恰为 VISION-01..02，全部被三 plan 的 frontmatter `requirements` 声明并收口。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| （无） | - | TBD/FIXME/TODO/HACK/PLACEHOLDER 零命中（XXX 命中均为 `shot_XXX.json` 文件名模式，非 debt marker） | - | - |

### 设计性偏差与观察（Info 级，非 gap）

1. **Spike cache 已被 CR-01 设计性失效**：盘上信封实测为 v1 形态（`prompt_version: vision-seq-v1`、无 window、无 ear_ctx_fp），当前代码（v2 + window + ear_fp 匹配）必 miss。下次真实运行将一次性重烧（~15min/集，REVIEW-FIX 明示为正确行为，勿为保 cache 回退 bump）。
2. **SC1/SC4 runtime 证据采集时点在 CR-01 之前**（sc1_evidence.txt 02:30 vs fix 02:53 本地时间）：填充机制/不覆盖/秒级重跑均为内容无关的机制证明，且机制由当前代码的 28 项单测锁定，**判定证据仍有效**；但「重跑同命令秒级」对当前盘上 spike cache 不再即刻成立（需先重烧一次）。诚实记录在案。
3. **SC3 字面示例「雨声→scene=雨天」未出现**：v2 只拥有 action/camera（scene 属 v1 红线零改动）；ROADMAP 措辞为「一类修正」，实测音频驱动修正（倒数等待/泪珠聆听/焦急呼喊）满足该类，报告如实记录差异并在 Kai checkpoint 复核确认。
4. **报告引用行号漂移**：报告称 `MERGE_STRATEGY_DEFAULT`（:111），review fix 后实际在 :123（值正确，纯行号漂移）。
5. **deferred（见 frontmatter）**：v1 --help 裸 % bug、v1 floor off-by-one 镜像、fps sidecar、IN-01..09——均有档可查，不阻塞本 phase 目标，未被 Phase 20-22 覆盖（后续 phase 均为 round-trip 侧）。

### Human Verification Required

None — 本 phase 唯一人工门（19-02 Task 3 盲评 checkpoint，blocking）已执行并留档：裁决「锁定甲」（2026-08-20）记录于报告锁定结论节 + `results/strategy_mapping.txt` 回写；SC3 ear diff 同 checkpoint 复核 confirmed。PLAN 全部 auto 任务无 deferred `<verify><human-check>` 块。自动化证据链（单测 + 独立复验的 sha256 + 可复现命令原文）已覆盖目标判定。

### Gaps Summary

无 gap。16/16 truths 全部 VERIFIED：

- 机制层（模块 + 客户端 + wiring）逐行实读核对，73 单测全绿，12 项行为 spot-check 独立执行通过；
- 证据层三重独立复验：live sha256 今天重算与记录一致、sandbox 填充态 json 实检、盘上 cache 信封结构实测；
- 决策层全落档：SC2 盲评锁定（FINAL 报告 + mapping 回写 + 模块默认值一致）、SC1 措辞按用户裁决执行（只填空缺永不覆盖，代码无更短替换路径）；
- review 生命周期闭环：CR-01 + WR-01..04 五项修复全部带回归测试，re-review clean（gates: 73 passed / validate exit 0，本 verifier 复跑同样通过）。

Phase goal 达成：action/camera facet 升级为 ≤8 帧序列逐帧实证（含 ear 融合）已在生产 wiring（pre-step 5.6）就位，合并策略经 GPU 实证 + 人工盲评锁定，独立于 round-trip 闭环。

---

_Verified: 2026-08-20_
_Verifier: Claude (gsd-verifier)_
