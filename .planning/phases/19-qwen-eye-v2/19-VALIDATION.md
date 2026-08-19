---
phase: 19
slug: qwen-eye-v2
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-19
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest（27 离线用例 0.16s）+ 引擎在线 smoke（spike 期间） |
| **Config file** | tests/ 现有布局 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + sandbox 幂等双跑 + validate.py（回归） |
| **Estimated runtime** | 离线 ~1s；在线 spike 1-3h（tmux 后台 + cache 断点续跑） |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + `python3 spec/validate.py`（契约回归）
- **Before `/gsd:verify-work`:** Full suite green + spike report 落档 + sandbox 证据
- **Max feedback latency:** 离线 60s；在线任务以引擎日志/cache 增量监控

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-T1 | 19-01 | 1 | VISION-01 | T-19-03 | 常量端点、消息 shape 受控（两条 user 各一图规避多图 bug；走 _call_llm 恒禁 thinking） | unit | `python3 -m pytest tests/test_qwen_eye_client.py -q` | ✅（扩展） | ⬜ pending |
| 19-01-T2 | 19-02 依赖的模块本体 | 1 | VISION-01, VISION-02 | T-19-01/02/05 | 写前 schema 校验；5 字段 cache key；ear 白名单提取（words/reproduction/spk_id 永不进） | unit（加载+常量断言+CLI 冒烟） | `python3 -c "importlib 加载 + assert MAX_SEQ_FRAMES_PER_SHOT==8 / PROMPT_VERSION=='vision-seq-v1' / STEP_TAG=='[vision-seq]'"` + `--help` | ❌ Wave 0（本任务创建） | ⬜ pending |
| 19-01-T3 | 19-01 | 1 | VISION-01, VISION-02 | T-19-01/02/05 | 采样/只填空缺/cache 幂等/合并确定性/degrade/ear 三断言/零修改短路/预判生命周期全覆盖 | unit（≥15 用例，FakeEngine 零网络） | `python3 -m pytest tests/test_vision_seq_facets.py -q` | ❌ Wave 0（本任务创建） | ⬜ pending |
| 19-02-T1 | 19-02 | 2 | VISION-01, VISION-02 | T-19-06 | sandbox 构建只写 spike/（脚本内 assert 输出前缀）；demo audio 过 schema 校验 | integration（离线构建断言） | `python3 spike/vision_seq/build_sandbox.py && python3 -c "sandbox 置空镜计数==6/3 + audio schema 断言"` | ❌ Wave 0（本任务创建） | ⬜ pending |
| 19-02-T2 | 19-02 | 2 | VISION-01, VISION-02 | T-19-06/08 | GPU 双跑限 ≤10 镜 ~150 calls；live sha256 前后等值负测试；SC4 秒级重跑计时 | integration（GPU + 文件断言） | `test -f .planning/research/vision-seq-spike-report.md && test $(ls spike/vision_seq/sandbox/route_cache/vision_seq/shot_*.json \| wc -l) -ge 6` | ❌（本任务创建） | ⬜ pending |
| 19-02-T3 | 19-02 | 2 | VISION-01 (SC2) | T-19-07 | 盲评映射落 results/strategy_mapping.txt + 报告回写；锁定值进模块默认 | manual（Kai 盲评 = blocking 人工门）+ 定稿断言 | `! grep -q DRAFT <report> && grep -q 锁定 <report> && python3 -m pytest tests/ -q` | ❌（本任务定稿） | ⬜ pending |
| 19-03-T1 | 19-03 | 3 | VISION-01, VISION-02 | T-19-09/10 | argv 列表传参无 shell 拼接；banner plain-label；条件四连守卫 | unit（静态 + --help 冒烟） | `grep -q '"vision seq facets (qwen-eye v2 pre-step)"' run_pipeline.py && ! grep -q '\[5\.6/9\]' run_pipeline.py && python3 run_pipeline.py --help \| grep -e --vision-seq -e --no-vision-seq -e --no-ear` | ✅（run_pipeline.py 既有） | ⬜ pending |
| 19-03-T2 | 19-03 | 3 | VISION-01, VISION-02 | — | wiring 四件套（flag 语义/顺序/banner 锁/ear 直通） | unit（静态 + argparse spy，≥4 用例） | `python3 -m pytest tests/test_pipeline_vision_seq_wiring.py -q` | ❌ Wave 0（本任务创建） | ⬜ pending |
| 19-03-T3 | 19-03 | 3 | VISION-01 (SC1), VISION-02 | T-19-09/11 | sandbox 填充可见 diff + live sha 等值负测试 + 秒级重跑，命令原文落档可复验 | integration（cache-hit 路径） | `test -f spike/vision_seq/results/sc1_evidence.txt && python3 -c "sandbox 填充计数≥6 断言"` | ❌（本任务创建） | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Wave 0 gaps are created in-phase by the plans themselves（19-01-T3 建 `tests/test_vision_seq_facets.py`、19-03-T2 建 `tests/test_pipeline_vision_seq_wiring.py`、19-02-T1 建 spike 脚手架）——先于各自被依赖行为生效；现有 27 test + spec/validate.py 覆盖契约回归；引擎 :8125 可拉起，GPU1 free 22.5GB ≥ 14GB 门槛（执行前复探）。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 合并策略盲评（3 策略同镜产物打分） | VISION-01 (SC2) | Q3 27B 动作描述质量是 Pitfall 3 明示的未验证假设；机器判据循环论证 | 看 spike report 盲评表（甲/乙/丙 + v1 参照）→ 裁定锁定策略 → 回复 resume-signal（19-02-T3 blocking checkpoint） |
| ear 双跑 diff 效果确认 | VISION-02 (SC3) | 「修正可见」是人类感知判断 | 看 spike report ear on/off diff 节（#1/#88/#91）→ 确认生效（与盲评同 checkpoint 一并确认） |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（19-02-T3 为人工盲评门，其定稿段有 automated 断言）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（新测试文件/脚手架由 19-01-T3 / 19-02-T1 / 19-03-T2 在依赖生效前创建）
- [x] No watch-mode flags
- [x] Feedback latency < 60s（离线任务；GPU 任务以 cache 增量监控）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending（executor 执行后回填各 task status）
