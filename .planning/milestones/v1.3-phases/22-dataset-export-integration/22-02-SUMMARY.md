---
phase: 22-dataset-export-integration
plan: 02
subsystem: roundtrip-hitl
tags: [hitl-apply, confirmed-only, idempotent, dataset-export, rt-05, dataset-02, present-01, hard-negatives]

requires:
  - phase: 20-h3-regen-client
    provides: roundtrip.json regen 半边 + route_cache/h3_regen/frames/ 帧缓存（19 对全在）
  - phase: 21-scorer-threshold
    provides: scores{midframe_sim, judge} + verdict{auto} 冻结态（ep01 4 accepted / 15 rejected）+ τ_sim=0.9670
  - phase: 22-dataset-export-integration/22-01
    provides: exportEdits payload 契约（accept_overrides/reject_overrides/review_notes——UI-SPEC §5，已被 22-01 测试源级锁定）
provides:
  - spec/schemas/roundtrip-edits.schema.json（registry-edits 直系变体；apply 安全门的一半）
  - analysis/roundtrip/apply_edits.py confirmed-only 回写 CLI（PRESENT-01 回写半边；human 覆盖唯一冻结替换路径；重放 byte-idempotent）
  - analysis/roundtrip/export_dataset.py accepted 子集独立 dataset 目录导出（RT-05 + DATASET-02 模块半边；消费端零 asset.json/roundtrip/ 引用）
  - tests/test_roundtrip_apply_edits.py（15 用例）+ tests/test_export_dataset.py（10 用例）
affects: [22-03 step_roundtrip wiring（dataset post-step 挂载）, 22-04 e2e harness（output/dataset 齐产断言）]

tech-stack:
  added: []  # 零新增依赖（jsonschema/pytest 已在库；stdlib shutil.copy2/importlib）
  patterns:
    - "READ-merge 语义反转：verdict 半边在 edits 命中时替换（human 覆盖唯一路径）vs judge._merge_write_sidecar pop 冻结 verdict"
    - "帧两级来源：route_cache 直拷优先 → 缺席回落 extract_endpoint_frames 回填 cache 后改名（同一实现同分辨率确定性）"
    - "重放真 no-op：全跳过时不重写 sidecar（连 mtime 都不动），decided_at 不漂移"
    - "prune 显式清单：只删自身陈旧 shot_NNN 目录（regex 形状锁定），绝不 glob/rmtree 父级或兄弟 video-stem"

key-files:
  created:
    - spec/schemas/roundtrip-edits.schema.json
    - analysis/roundtrip/apply_edits.py
    - analysis/roundtrip/export_dataset.py
    - tests/test_roundtrip_apply_edits.py
    - tests/test_export_dataset.py
  modified: []

key-decisions:
  - "PRESENT-01 随本 plan 勾选 —— 呈现半边（22-01 面板+XSS+exportEdits）+ 回写半边（本 plan schema+confirmed-only apply CLI）双侧齐备；RT-05/DATASET-02 保持未勾选（模块半边已交付，pipeline 挂载 22-03 与 e2e 齐产 22-04 共享同 requirement IDs——mirror 18-01/19-01/20-01/21-01/22-01 先例）"
  - "discretion 定名 #1：apply CLI 落 analysis/roundtrip/apply_edits.py（非 registry/apply_roundtrip_edits.py）——与 roundtrip 三件套同目录便于 importlib 共享 h3s；与 registry/apply_edits.py 跨目录无命名冲突"
  - "discretion 定名 #2：dataset 导出落 analysis/roundtrip/export_dataset.py（RESEARCH 建议名直接采纳）"
  - "源视频解析 graceful 分歧：_find_source_video 返 None 而非 h3s.resolve_source_video 的 sys.exit——本模块是 post-step 语义，帧回落缺席时降级跳过该镜不炸整批"
  - "plan verify demo 的 shot_id 3 不在 ep01 sidecar（sidecar 只含 19 抽样镜 1,5,10,...,89）——demo edits 改 {accept:[5], reject:[10]}，保双向覆盖语义"

patterns-established:
  - "fail-loud 消息断言走 SystemExit.code（sys.exit(str) 的消息在 code 对象上，仅未被解释器捕获时才打 stderr）"

requirements-completed: [PRESENT-01]  # RT-05/DATASET-02 半边交付，22-03/22-04 收口后勾选

duration: 6min
completed: 2026-08-20
---

# Phase 22 Plan 02: edits schema + apply CLI + dataset 导出 Summary

**PRESENT-01 回写半边 + RT-05/DATASET-02 模块半边落地：roundtrip-edits schema（confirmed-only 硬门的一半）+ apply CLI（human 覆盖唯一冻结替换路径、重放 byte-idempotent）+ accepted 子集独立 dataset 导出（消费端零契约依赖，25 个新用例 + ep01 只读双演示全绿）。**

## Performance

- **Duration:** ~6 min（04:43:50Z → 04:49:34Z）
- **Started:** 2026-08-20T04:43:50Z
- **Completed:** 2026-08-20T04:49:34Z
- **Tasks:** 2/2
- **Files modified:** 5 (all created)

## Accomplishments

- **edits schema + confirmed-only apply CLI**（PRESENT-01 回写半边收口）：`roundtrip-edits.schema.json` 对 22-01 面板 payload 形状合法、对坏 edits 三态（字符串 id/未知属性/负数）非法；apply CLI 固定序（schema 预校验 → 交集 fail-loud → 未知 shot_id 列出 fail-loud → READ-merge 写 verdict{source:"human", decided_at} → 两层自校验 → 原子写），任何失败路径 sidecar 原字节不动
- **语义反转点正测**：judge._merge_write_sidecar 对预存 verdict pop 冻结（judge.py:371-372）——apply CLI 恰相反，edits 命中镜 verdict 半边替换（human 覆盖唯一路径），该镜 regen/scores 半边与未命中镜 byte 级保留（单测断言）
- **真 idempotent**（A3）：已 human 且同 decision 跳过不写（decided_at 不漂移）——重放第二遍 sidecar byte 级 no-op 且 **mtime 不动**（全跳过时根本不落盘）
- **dataset 独立导出**（RT-05 + DATASET-02）：accepted 镜 → `dataset/<video-stem>/shot_NNN/{first,last}_frame.jpg + prompt.json`（自含 16 字段，regen 无 path）+ manifest（τ/引擎版本/分桶/shots 索引）+ accepted/rejected 分清单（rejected.txt 每行 `shot_NNN sim={:.4f} {attribution} {reason[:80]}` 可 grep）；帧直拷 route_cache 优先（字节即 h3 实喂帧）、缺席回落 extract_endpoint_frames 回填 cache；消费端独立性机器证明（dataset 内 JSON 全文零 `asset.json`/`roundtrip/` 引用、零 symlink）

## ep01 副本 apply 演示实录（命令与输出）

```console
$ EP01=$(ls -d output/虫虫武侠*第01话*/ | head -1) && \
  cp "$EP01/roundtrip.json" /tmp/rt_apply_demo_dir/roundtrip.json && \
  printf '{"accept_overrides":[5],"reject_overrides":[10],"review_notes":"demo"}' > /tmp/rt_edits_demo.json && \
  python3 analysis/roundtrip/apply_edits.py --work-dir /tmp/rt_apply_demo_dir --edits /tmp/rt_edits_demo.json
[roundtrip-apply] shot_005 auto→human/accepted
[roundtrip-apply] shot_010 auto→human/rejected
[roundtrip-apply] 完成：applied=2 same_decision_replay=0 skipped=0 → /tmp/rt_apply_demo_dir/roundtrip.json

# 同 edits 重放第二遍（byte 级 no-op + mtime 不动）：
$ python3 analysis/roundtrip/apply_edits.py --work-dir /tmp/rt_apply_demo_dir --edits /tmp/rt_edits_demo.json
[roundtrip-apply] shot_005 已 human 同 decision 跳过（human/accepted）
[roundtrip-apply] shot_010 已 human 同 decision 跳过（human/rejected）
[roundtrip-apply] 完成：applied=0 same_decision_replay=2 skipped=0（无写入，sidecar 原样）
```

ep01 正本 sha256 前后不变（diff 为空）。demo edits 用 shot 5/10（auto-rejected→human-accepted + auto-accepted→human-rejected 双向各一条）——plan verify 块写的 shot 3 不在 ep01 sidecar（见 Deviations #1）。

## dataset 演示目录树（ep01 只读导出 → /tmp/p22-ds-demo）

```
/tmp/p22-ds-demo/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/
├── shot_010/{first_frame.jpg, last_frame.jpg, prompt.json}
├── shot_061/{first_frame.jpg, last_frame.jpg, prompt.json}
├── shot_075/{first_frame.jpg, last_frame.jpg, prompt.json}
├── shot_084/{first_frame.jpg, last_frame.jpg, prompt.json}
├── manifest.json
├── accepted.txt          # 4 行：shot_010/061/075/084
└── rejected.txt          # 15 行，如：shot_001 sim=0.9351 prompt_faithful REGEN 忠实呈现了 …
```

manifest 实测：`tau_sim=0.967 / engine_versions=["fl2va-int8/euler+simple/15/1344x768"] / accepted_count=4 / rejected_count=15 / rejected_buckets{faithful_below_tau=6, diverged=9, underspecified=0} / shots{"10":"shot_010",...}`——与 21-03 裁决分布逐值吻合（DATASET-02 hard-negative 索引可审计）。ep01 work_dir 零写入（find -newermt 5min = 0 文件）；output/dataset 正式产出留给 22-04 e2e。

## 两个 discretion 定名记录

1. **apply CLI = `analysis/roundtrip/apply_edits.py`**（备选 `registry/apply_roundtrip_edits.py`）——落 roundtrip 三件套同目录，importlib 共享 h3s 装载块与三件套逐字一致（judge.py:100-103）；与 `registry/apply_edits.py` 跨目录无命名冲突，registry 先例骨架（standalone docstring/硬门语义/_validate 预校验/固定序）逐项 mirror
2. **dataset 导出 = `analysis/roundtrip/export_dataset.py`**——RESEARCH §Recommended Project Structure 建议名直接采纳（CONTEXT "Claude's Discretion" 清单第 3 项收口）

## Task Commits

1. **Task 1: roundtrip-edits schema + apply_edits.py confirmed-only 回写 CLI** — `aae1f45` (test, RED) + `2eb674a` (feat, GREEN)
2. **Task 2: export_dataset.py 独立 dataset 目录导出** — `afa69ca` (test, RED) + `3bf2672` (feat, GREEN)

## Files Created/Modified

- `spec/schemas/roundtrip-edits.schema.json` — edits 契约（Draft 2020-12 / additionalProperties:false / 全字段 optional / 空 {} valid；integer minimum 1 是与 registry-edits 的唯一结构差异）
- `analysis/roundtrip/apply_edits.py` — confirmed-only 回写 CLI（283 行；--work-dir + --edits；audit 注释列 h3s 复用符号 4 件）
- `analysis/roundtrip/export_dataset.py` — dataset 导出（407 行；--work-dir/--dataset-root(默认 work_dir 同级 dataset/)/--tau-sim(默认 0.9670)；h3s 复用符号 5 件）
- `tests/test_roundtrip_apply_edits.py` — 15 用例（242 行；七断言组）
- `tests/test_export_dataset.py` — 10 用例（279 行；九断言组）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan bug] plan verify demo 的 shot_id 3 不在 ep01 sidecar**
- **Found during:** Task 1 ep01 烟测准备
- **Issue:** plan verify 块 edits 用 `{"accept_overrides":[3],...}` 并断言 `shot_003 auto→human/accepted`——但 ep01 roundtrip.json 只含 19 抽样镜（1,5,10,14,...,89），shot 3 缺席，会触发本 CLI 自己的未知 id fail-loud（恰好证明防护有效但 demo 跑不通）
- **Fix:** demo edits 改 `{"accept_overrides":[5],"reject_overrides":[10]}`——shot 5（auto-rejected）→ human-accepted、shot 10（auto-accepted）→ human-rejected，保住 plan 要的「auto→human 双向各一条」语义；测试不受影响（合成 fixture 自带 shot 1/2/3）
- **Files modified:** 无源码改动（仅 demo 命令适配）
- **Commit:** 2eb674a（提交信息载明）

**2. [Rule 1 - Test bug] 未知 shot_id 消息断言走错流**
- **Found during:** Task 1 GREEN 迭代
- **Issue:** 测试断言未知 id 消息在 stdout——`sys.exit(str)` 的消息挂在 SystemExit.code 上，pytest.raises 捕获后不进任何流
- **Fix:** 断言改 `str(ei.value.code)`（已沉淀为 patterns-established）
- **Files modified:** tests/test_roundtrip_apply_edits.py
- **Commit:** 2eb674a

**3. [Rule 3 - Blocking] export_dataset 初稿两处死代码**
- **Found during:** Task 2 实现（提交前自查）
- **Issue:** walrus-import 黑科技构造 `_SHOT_DIR_RE` + 一行非法 except 表达式（实现过程中自产自纠，未流入任何 commit）
- **Fix:** 顶部正规 `import re`/`import subprocess`，except 收 `(RuntimeError, OSError, subprocess.SubprocessError)`
- **Files modified:** analysis/roundtrip/export_dataset.py
- **Commit:** 3bf2672（修复后提交，无中间态入库）

### Plan 语义澄清（非偏差）

- 合成 fixture 2 rejected（plan 写「2 accepted + 1 rejected」）：多一条 rejected 使 faithful/diverged 双分桶在同 fixture 可测——九断言组「manifest 分桶」的必要条件
- manifest `tau_sim` 序列化为 0.967（JSON number 无尾随零概念，`== 0.9670` 成立）——非精度丢失

## Test Evidence

- `python3 -m pytest tests/test_roundtrip_apply_edits.py -q` → **15 passed**
- `python3 -m pytest tests/test_export_dataset.py -q` → **10 passed**
- `python3 -m pytest tests/ -q` → **215 passed**（基线 190 + 新增 25，零回归）
- ep01 apply 演示：双向覆盖 + 重放 byte 幂等 + 正本 sha256 不变
- ep01 dataset 演示：4 目录/jpg 非空/字段齐/分桶 6:9/清单 4:15 行/work_dir 零写入

## Self-Check: PASSED

文件（5/5 FOUND）：spec/schemas/roundtrip-edits.schema.json / analysis/roundtrip/apply_edits.py / analysis/roundtrip/export_dataset.py / tests/test_roundtrip_apply_edits.py / tests/test_export_dataset.py；commits（4/4 FOUND）：aae1f45 / 2eb674a / afa69ca / 3bf2672。
