---
phase: 21-scorer-threshold-calibration
plan: "02"
subsystem: testing
tags: [siglip, gpu-smoke, qwen-eye, judge, midframe-sim, overnight-batch, h3-regen, 1344x768]

# Dependency graph
requires:
  - phase: 21-scorer-threshold-calibration (21-01)
    provides: analysis/roundtrip/scorer.py + judge.py（离线替身 38 用例已验证的 CLI 面）
  - phase: 20-h3-regen-client
    provides: h3_regen.py 批渲染客户端（guard 五步 + uniform 采样 + 断点续跑）+ 2 镜 896×512 smoke regen 素材
  - phase: 19-qwen-eye-v2
    provides: engine_clients.qwen_eye_client（judge 引擎生命周期）
provides:
  - SCORE-01/SCORE-02 的 live 半边真机证据（2 镜 896×512 双信号 + schema 合法 sidecar + SC2 帧清单 cache + SC3 grid 素材）
  - uniform-20 @1344×768 overnight 批（后台运行 + pidfile/日志交接协议——21-03 校准的素材前提）
affects: [21-03 uniform-20 校准批, 22 Dataset Export]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "nohup 后台批 + python3 -u（stdout 重定向到文件时块缓冲会让审计日志滞后数小时——启动 invocation 必须无缓冲）"
    - "GPU smoke 先于 overnight 批（cache key 含 regen mp4 身份，批后 1344×768 自然重打分——research 建议采纳）"

key-files:
  created:
    - "output/<ep01>/route_cache/scorer/shot_001.json + shot_047.json（+ frames/ 32 jpg）"
    - "output/<ep01>/route_cache/judge/shot_001.json + shot_047.json（+ frames/ 16 jpg）"
    - "output/<ep01>/roundtrip/_judge_grids/shot_001.jpg + shot_047.jpg"
    - "output/<ep01>/route_cache/h3_regen/overnight_20.log + overnight_20.pid"
  modified:
    - "output/<ep01>/roundtrip.json（scores 双半边 READ-merge 写入，schema 0 errors）"

key-decisions:
  - "GPU smoke 走既有 896×512 regen（shots 1/47）先行验证全链，不等 overnight 批——cache key 含 regen_mp4_sha256_16，1344×768 批后自然 miss 重打分"
  - "overnight 批以 python3 -u 重启（首启 stdout 块缓冲致日志 0 字节——Rule 3 修复，h3_regen.py 零代码变更）"
  - "896×512 对照数据点（21-03 报告用）：shot 1 sim=0.9309 / shot 47 sim=0.8396，双镜均 prompt_faithful conf=0.95"

requirements-completed: []   # SCORE-01/SCORE-02 与 21-03 校准批共享 requirement IDs——live 证据半边本 plan 交付，勾选留待 21-03 收口（mirror 18-01/19-01/20-01/21-01 先例）

# Metrics
duration: TBD
completed: 2026-08-20
---

# Phase 21 Plan 02: GPU smoke + overnight 批启动 Summary

（执行中——Task 1 已完成并验证，Task 2 overnight 批运行中。最终形态在本 plan 收口时补齐。）

## Task 1: 2 镜 896×512 真 GPU smoke（scorer 真跑 + judge 真跑 + schema gate）

**结论：rc 0 全链一次过——scorer/judge 模块零 bug 零修复（smoke 修复回路未触发），全套件 157 passed 零回归。**

### 真机双信号（896×512 对照数据点，21-03 校准报告引用）

| shot | midframe_sim | per_position_cos（8 位） | judge 归因 | confidence |
|------|-------------|--------------------------|-----------|------------|
| 1 | **0.9309** | 0.9439 / 0.9513 / 0.9221 / 0.9091 / 0.9151 / 0.9286 / 0.9148 / 0.9625 | prompt_faithful | 0.95 |
| 47 | **0.8396** | 0.8718 / 0.8823 / 0.8495 / 0.8830 / 0.8763 / 0.8729 / 0.7068 / 0.7745 | prompt_faithful | 0.95 |

- scorer：GPU0（3060Ti，fp16，起跑 free 4.65GiB）真 SigLIP 离线加载（HF_HUB_OFFLINE=1，~10s）→ 32 帧提取 → 2 次前向；分数落在 RESEARCH 实测窄带（0.85-0.98）下沿附近（shot 47 的 0.8396 略低于带——per-position 后两位 0.71/0.77 拖低，属真实分布信息，只记录不判阈）
- judge：GPU1 qwen-eye 真拉起（comfy_free 先行；本次 ensure_ready 一次过未触发 120s 重试）→ 2 grid（1370×1476，453KB/330KB）→ 2 次 observe_single **attempts 均 1/1 parse-ok**（探针 5/5 先例延续，重问路径未触发）
- judge reason 质量抽读：两镜 reason 均引用 prompt 原文短语（shot 1：'独角仙武士'、'弯腰'、'红浆果'…；shot 47：'暗红多足巨蜈蚣长身贴地疾行'…）且以 t=33%/66% 中段行为为主要证据——提示词指令被遵守
- 引擎卫生：judge 收尾 stop_if_owned 生效（GPU1 回落 1586 MiB 基线，:8125 关闭，13.4GB lease 零泄漏）

### 机器断言（plan verify 块全过 + pytest）

- sidecar 双半边：scores.midframe_sim{score∈[0,1], model 非空} + scores.judge{attribution ∈ 三值闭集, confidence ∈ [0,1], reason ≤2000}——两镜齐
- scorer cache：frames.orig/regen 各 8 条、per_position_cos 8 元、t_pct 全落 [25,75]（SC2 真机证据）
- judge cache：attempts ≥1 + parsed 三件套（SC2/SC3 审计面）
- grid 文件：1370×1476、>100KB（可目检）
- **schema gate：`h3s._iter_sidecar_errors` 全量 0 errors**
- 全套件 pytest：**157 passed**（3.59s，21-01 基线保持，零回归）

## Task 2: uniform-20 @1344×768 overnight 批（运行中）

（批交接信息块在收口时落于此——pidfile/日志绝对路径、启动时间戳、预期完成窗口。）
