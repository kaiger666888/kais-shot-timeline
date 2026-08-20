---
phase: 20
slug: h3-regen-client
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-20
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（FakeComfyUI HTTP mock + nvidia-smi/ss/os.kill mock）+ 真 ComfyUI smoke（--sample-shots 2 级别） |
| **Config file** | tests/ 现有布局（无配置文件——repo 惯例裸 pytest） |
| **Quick run command** | `python3 -m pytest tests/test_h3_regen.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + roundtrip.json 过 `spec/schemas/roundtrip.schema.json` |
| **Estimated runtime** | 离线全套 ~5-15s；真机 smoke 单镜 3-8min（896×512） |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/test_h3_regen.py -x -q`（20-03 Task 2 起改跑全套）
- **After every plan wave:** Full suite `python3 -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** 全绿 + ep01 smoke 证据（2 mp4 + cache-hit 重跑输出）落 SUMMARY
- **Max feedback latency:** 离线 60s（sleep 已 monkeypatch）

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-T1 | 20-01 | 1 | REGEN-01 | T-20-01/02 | prompt 只走 json.dumps；/view 文件名净化；subprocess list-form | unit（纯函数断言） | 见 20-01-PLAN Task 1 `<automated>`（py_compile + length 网格/seed/注入/deepcopy 断言） | 待建 | ⬜ pending |
| 20-01-T2 | 20-01 | 1 | REGEN-02 | T-20-03/04 | warnings detail 无凭据；--force 显式清单 | unit（cache/warnings/force 断言） | 见 20-01-PLAN Task 2 `<automated>`（cache hit/miss + 双形 merge + run_pipeline force 块断言） | 待建 | ⬜ pending |
| 20-01-T3 | 20-01 | 1 | REGEN-01, REGEN-02 | T-20-01 | FakeComfyUI 全链路零真引擎 | unit | `python3 -m pytest tests/test_h3_regen.py -x -q`（≥12 用例） | 待建（Wave 0 本 plan 内创建） | ⬜ pending |
| 20-02-T1 | 20-02 | 2 | REGEN-03 | T-20-05/06/07 | 端口→PID 定向 kill（非宽 pkill）；fail-open 读数；22GB gate | unit（源码断言） | 见 20-02-PLAN Task 1 `<automated>`（query-compute-apps/os.kill/SIGTERM/阈值常量存在性） | 待建 | ⬜ pending |
| 20-02-T2 | 20-02 | 2 | REGEN-04 | — | 分辨率 %32/7:4/MAX_PIXELS 校验 | unit（锚点断言） | 见 20-02-PLAN Task 2 `<automated>`（uniform-20 锚点清单逐项相等 + 分辨率拒收） | 待建 | ⬜ pending |
| 20-02-T3 | 20-02 | 2 | REGEN-03, REGEN-04 | T-20-05 | guard 五步序列 + 反自锁回归锚 | unit | `python3 -m pytest tests/test_h3_regen.py -k "vram or kill or free or sample or resolution or skip" -x -q`（≥9 用例） | 待建 | ⬜ pending |
| 20-03-T1 | 20-03 | 3 | REGEN-01 | T-20-08/09 | sidecar 写前 schema 自校验（拒路径穿越）；error ≤2000 字符 | unit（merge + schema） | 见 20-03-PLAN Task 1 `<automated>`（三层 parent SCHEMA_PATH + merge 保留 scores + jsonschema 零错） | 待建 | ⬜ pending |
| 20-03-T2 | 20-03 | 3 | REGEN-01, REGEN-02, REGEN-04 | T-20-10 | smoke 限 2 镜 896×512；guard 真机路径执行 | smoke（真 ComfyUI） | 见 20-03-PLAN Task 2 `<automated>`（pytest + mp4 size + sidecar schema + cache-hit 重跑）；预期 wall 10-30min | 待建 | ⬜ pending |
| 20-03-T3 | 20-03 | 3 | REGEN-01 | — | — | manual（人类目视） | checkpoint:human-verify（Task 3 步骤） | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

tests/test_h3_regen.py 与 FakeComfyUI mock 设施由 **20-01 Task 3（wave 1 内）** 创建——先于任何依赖它的 verify 消费；真 ComfyUI :8188 已在跑（v0.30.0, GPU1 3090）；fl2va 模板 JSON 内容由 20-RESEARCH §Code Examples 逐字给出。无外部 MISSING 依赖。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| regen mp4 目视抽检（首尾帧 condition 贴合 + 运动合理） | REGEN-01 | 视觉质量判断不可自动化 | 20-03 Task 3：_compare/ 原镜段 vs regen 并排同播，三点检查（首尾帧一致 / 运动符合 prompt / 无爆裂黑帧） |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（20-03-T3 为唯一 human checkpoint，其余全 automated）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify（每 plan 末 task 均有 pytest 门）
- [x] Wave 0 covers all MISSING references（test 文件在 20-01 wave 1 内先建）
- [x] No watch-mode flags
- [x] Feedback latency < 60s（离线任务；真机 smoke 例外已标注 wall 预期）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner sign-off 2026-08-20（smoke 任务已标 GPU 时长预期；checkpoint plan autonomous:false）
