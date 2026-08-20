---
phase: 22
slug: dataset-export-integration
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-20
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 离线（面板 XSS/六态 + apply + dataset + wiring 四组单测）+ bash e2e 四场景 harness + ep01 抽样端到端真跑 |
| **Config file** | tests/ 现有布局（无 pytest.ini，测试文件自足；bash harness 独立跑） |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` + `bash tests/test_phase22_e2e.sh` + `python3 spec/validate.py` |
| **Estimated runtime** | 离线 ~5s；e2e harness ~3-6min（S1 离线秒级 + S2/S3/S4 live 分钟级）；ep01 抽样 e2e 分钟级（cache 全命中） |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Full suite + `python3 spec/validate.py`
- **Before `/gsd:verify-work`:** 全绿 + ep01 e2e 证据（roundtrip.json sha 不变 + asset 1.3 挂载 + dataset 目录 + review HTML）落 SUMMARY
- **Max feedback latency:** 离线 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22-01-T1 | 22-01 | 1 | PRESENT-01 (SC2/SC3 呈现) | T-22-01..04 | `_esc` 强制清单全过 + bootstrap `</` 转义 + 零 innerHTML（生成器侧） | unit + live 烟测（ep01 19 卡） | plan 内 verify（gen 命令 + HTML 锚断言） | ⬜ create | ⬜ pending |
| 22-01-T2 | 22-01 | 1 | PRESENT-01 (SC3) | T-22-01..03 | 三注入 payload（script/onerror/base64）原文不存活/转义态在场/无属性注入；六态；payload 形状 | unit | `python3 -m pytest tests/test_roundtrip_review.py -x -q` | ⬜ create | ⬜ pending |
| 22-02-T1 | 22-02 | 1 | PRESENT-01 (SC2 回写) + DATASET 门槛 | T-22-05..07 | edits schema 拒坏三态；confirmed-only 写 source:human；frozen 可被 human 替换（唯一路径）；重放 byte 幂等；交集/未知 id fail-loud | unit + ep01 副本 live demo | `python3 -m pytest tests/test_roundtrip_apply_edits.py -x -q`（+ plan 内 demo 链） | ⬜ create | ⬜ pending |
| 22-02-T2 | 22-02 | 1 | RT-05, DATASET-02 | T-22-08..09 | dataset 目录布局/prompt.json 自含/manifest 分桶 6:9/两清单行格式/帧直拷-回落/消费端零引用/prune 不越界 | unit + ep01 只读 demo | `python3 -m pytest tests/test_export_dataset.py -x -q`（+ plan 内 demo 链） | ⬜ create | ⬜ pending |
| 22-03-T1 | 22-03 | 2 | PIPE-01 (SC1) | T-22-11,13 | step_roundtrip 编号挂载 + 六 flag + banner [N/10] 重编号 + 外层 cache 短路；既有 wiring 测试同步 | unit（静态源码断言） | `python3 -m pytest tests/test_pipeline_vision_wiring.py tests/test_pipeline_vision_seq_wiring.py -x -q` | ✅（2 文件需改） | ⬜ pending |
| 22-03-T2 | 22-03 | 2 | PIPE-01 (SC1) | T-22-09,12 | Pattern 4 条件 input（存在才 append）+ dataset post-step graceful + --force 清单零改动；新 wiring 四测 | unit（静态源码断言） | `python3 -m pytest tests/test_pipeline_roundtrip_wiring.py -x -q` | ⬜ create | ⬜ pending |
| 22-04-T1 | 22-04 | 3 | PIPE-02 (SC5) | T-22-14,17 | 四场景 harness + 前置探测（ComfyUI/GPU1/TTS）+ S1 fixture byte-identical-absent | bash e2e（S1 离线段本地跑） | `bash -n tests/test_phase22_e2e.sh` + S1 实跑（plan verify） | ⬜ create | ⬜ pending |
| 22-04-T2 | 22-04 | 3 | PIPE-02 (SC5) + PIPE-01 (SC1 live) + RT-05 (e2e) | T-22-14..16 | 四场景 ALL_SCENARIOS_PASS + asset 1.3 挂载 4/15 + dataset 齐产 + sidecar sha 三点不变 + 复跑幂等 | bash e2e（live）+ JSON 字段断言 | `bash tests/test_phase22_e2e.sh`（+ plan verify 链） | ⬜ create（脚本 T1） | ⬜ pending |
| 22-04-T3 | 22-04 | 3 | PRESENT-01 (SC2 终验) | T-22-15 | 人机闭环走查：双 video 同步/三态/edits 导出/apply 演示（ep01 正本默认零改动） | checkpoint:human-verify | `<human-check>`（走查步骤 1-6） | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*（pytest 9.0.3 / jsonschema / bash / serve.py / ComfyUI+GPU 均在场——RESEARCH §Environment Availability 实测；GPU1 free 余量薄（22539 vs 22528）已通过 harness 前置探测 + S3 文档化降级分支消化，非缺失。全部新测试文件由 22-01/22-02/22-03/22-04 各 task 自建——Wave 0 无独立安装/框架 gap。）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| review 面板走查（双 video 同步播 + 三态覆盖 + export edits 流程） | PRESENT-01 (SC2) | 浏览器交互人类走查 | serve.py 起服务开 roundtrip_review.html → 走查 6 步（22-04 Task 3 how-to-verify）→ checkpoint approved |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s（离线任务）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner sign-off 2026-08-20（每 task 均有 <60s 离线 verify 或显式 live/checkpoint 分类；唯一人验点 = 22-04-T3 走查）
