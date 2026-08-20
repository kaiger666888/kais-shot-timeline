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
    - "nohup 后台批 + python3 -u（stdout 重定向到文件时块缓冲会让审计日志滞后数小时——后台批启动 invocation 必须无缓冲）"
    - "GPU smoke 先于 overnight 批（cache key 含 regen mp4 身份，批后 1344×768 自然 miss 重打分——research 建议采纳）"
    - "ComfyUI 0.30 /history 不含运行中 prompt → poll 循环所有 continue 分支都跳过 elapsed 打印：批中 per-shot 日志锚点是 rendered/cache-hit 完成行，非渲然中行"

key-files:
  created:
    - "output/<ep01>/route_cache/scorer/shot_001.json + shot_047.json（+ frames/ 32 jpg）"
    - "output/<ep01>/route_cache/judge/shot_001.json + shot_047.json（+ frames/ 16 jpg）"
    - "output/<ep01>/roundtrip/_judge_grids/shot_001.jpg + shot_047.jpg"
    - "output/<ep01>/route_cache/h3_regen/overnight_20.log + overnight_20.pid"
  modified:
    - "output/<ep01>/roundtrip.json（scores 双半边 READ-merge 写入，schema 0 errors）"

key-decisions:
  - "GPU smoke 走既有 896×512 regen（shots 1/47）先行验证全链，不等 overnight 批——cache key 含 regen_mp4_sha256_16，1344×768 批后自然 miss 重打分（Pitfall 7 设计兑现）"
  - "overnight 批以 python3 -u 重启（首启 stdout 块缓冲致日志 0 字节 5 分钟——Rule 3 修复，h3_regen.py 零代码变更，重启安全因批刚起零完成镜）"
  - "896×512 对照数据点（21-03 报告用）：shot 1 sim=0.9309 / shot 47 sim=0.8396，双镜均 prompt_faithful conf=0.95"
  - "SCORE-01/SCORE-02 保持未勾选——live 证据半边本 plan 交付，但 ≤20 镜校准集打分与分布锁定在 21-03（mirror 18-01/19-01/20-01/21-01 同 requirement 共享先例）"

requirements-completed: []   # 勾选留待 21-03 收口（见上决策）

# Metrics
duration: ~40m（含 overnight 批守卫观察窗口）
completed: 2026-08-20
---

# Phase 21 Plan 02: GPU smoke + overnight 批启动 Summary

**2 镜 896×512 真 GPU 双信号（SigLIP scorer @GPU0 + qwen-eye judge @GPU1，模块零 bug 零修复 + 157 pytest 零回归）+ uniform-19 @1344×768 overnight 批 nohup 运行中（guard 过线、shot 1 已回收、pidfile/日志交接就位）**

## Performance

- **Duration:** ~40m（22:30–23:10 UTC / 06:30–07:10 本地；含 Task 1 全链 + 批启动 + 守卫过线观察）
- **Started:** 2026-08-20 06:30 (本地)
- **Completed:** 2026-08-20 07:10 (本地；overnight 批继续后台运行)
- **Tasks:** 2/2
- **Files modified:** 全部为 output/ 运行产物（gitignored by design——roundtrip.json + 4 cache json + 2 grid jpg + 32+16 帧 jpg + log/pidfile）；代码零改动

## Task 1: 2 镜 896×512 真 GPU smoke（scorer 真跑 + judge 真跑 + schema gate）

**结论：rc 0 全链一次过——scorer/judge 模块零 bug 零修复（smoke 修复回路未触发），全套件 157 passed 零回归。**

### 真机双信号（896×512 对照数据点，21-03 校准报告引用）

| shot | midframe_sim | per_position_cos（8 位） | judge 归因 | confidence | attempts |
|------|-------------|--------------------------|-----------|------------|----------|
| 1 | **0.9309** | 0.9439 / 0.9513 / 0.9221 / 0.9091 / 0.9151 / 0.9286 / 0.9148 / 0.9625 | prompt_faithful | 0.95 | 1/1 ok |
| 47 | **0.8396** | 0.8718 / 0.8823 / 0.8495 / 0.8830 / 0.8763 / 0.8729 / 0.7068 / 0.7745 | prompt_faithful | 0.95 | 1/1 ok |

- **scorer（GPU0 3060Ti fp16）**：起跑 free 4.65GiB；SigLIP 真权重离线加载（HF_HUB_OFFLINE=1，~10s）→ 32 帧提取 → 2 次前向；分数落 RESEARCH 实测窄带（0.85-0.98）附近（shot 47 的 0.8396 微出下沿——per-position 后两位 0.71/0.77 拖低，属真实分布信息，只记录不判阈，τ 未锁）
- **judge（GPU1 qwen-eye 真拉起）**：comfy_free 先行；ensure_ready 本次一次过（~120s 启动未触发重试路径）；2 grid（1370×1476，453KB/330KB）→ 2 次 observe_single **attempts 均 1/1 parse-ok**（探针 5/5 先例延续，retry-with-feedback 保险未触发）
- **reason 质量抽读**：两镜 reason 均引用 prompt 原文短语（shot 1：'独角仙武士'、'弯腰'、'红浆果'、'丁达尔光束'…；shot 47：'暗红多足巨蜈蚣长身贴地疾行'、'贴地低角度横移跟拍'…）且以 t=33%/66% 中段行为为主要证据——提示词指令被遵守，归因非信口开河（SC3 素材先例）
- **引擎卫生**：judge 收尾 stop_if_owned 生效——GPU1 回落 1586 MiB 基线、:8125 关闭，13.4GB lease 零泄漏

### 机器断言（plan verify 块全过 + pytest）

- sidecar 双半边：scores.midframe_sim{score∈[0,1], model 非空} + scores.judge{attribution ∈ 三值闭集, confidence ∈ [0,1], reason ≤2000}——两镜齐
- scorer cache：frames.orig/regen 各 8 条、per_position_cos 8 元、t_pct 全落 [25,75]（SC2 真机证据）
- judge cache：attempts ≥1 + parsed 三件套（重问审计面）
- grid 文件：1370×1476、>100KB（可目检）
- **schema gate：`h3s._iter_sidecar_errors` 全量 0 errors**
- 全套件 pytest：**157 passed**（3.59s，21-01 基线保持，零回归）
- Commit：`9c5d1b7`（GPU-run docs 证据 commit——20-03 先例；产物在 output/ gitignored）

## Task 2: uniform-20 @1344×768 overnight 批 nohup 启动 + 守卫过线

### 批交接信息块（21-03 Task 1 完成度检查入口）

| 项 | 值 |
|----|-----|
| **pidfile** | `/home/kai/workspace/kais-shot-timeline/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/route_cache/h3_regen/overnight_20.pid` → **PID 4112729** |
| **日志** | 同目录 `overnight_20.log`（python3 -u 无缓冲，逐镜 rendered 行可 tail -f） |
| **命令** | `python3 -u analysis/roundtrip/h3_regen.py --work-dir <EP01> --sample-shots 20`（--regen-resolution 默认 1344x768） |
| **启动时间戳** | 2026-08-20 06:35:11 +0800（2026-08-19T22:35:11Z；首启 06:32:36 因 stdout 块缓冲被杀重启，零完成镜损失 ~4min GPU） |
| **预期完成窗口** | 本地 2026-08-20 上午 **~10:00-11:30**（shot 1 实测 ~17min 含模型加载；18 镜余量按 10-15min/镜外推，研究带 3-4.5h 兑现中） |
| **预期产物** | 19 × `roundtrip/shot_XXX_regen.mp4` @1344×768（shot 70 被 max-shot-sec 跳过）+ sidecar 19-20 条 regen 半边（shots 1/47 被 READ-merge 覆盖为 1344×768，**scores 保留**——Pitfall 8 语义）+ 收尾 flush warnings.json |

### 守卫过线证据（本 plan 收口时刻 06:53）

- **镜清单**：日志 `[roundtrip] --sample-shots 20: 20/93 镜入样` + `shot 70 skipped: 19.7s > max 10.0s`（skipped.json 落盘 duration_over_max）→ uniform-20 = 19 镜实渲
- **guard 序列过线（隐性证据）**：guard 成功路径不打印 stdout（TTS 审计走 warnings 通道，批收尾 flush——现存 warnings.json 内容为 20-03 smoke 遗留）；过线的机器证据 = 批进入渲染：ComfyUI /queue running:1 + GPU1 1586→18572 MiB + 首镜 endpoint 帧上传
- **首镜 /prompt 提交 + 回收**：`[roundtrip] shot 1: rendered shot_001_regen.mp4`（06:53，175f / 1344×768 / 1.74MB / post_render_free_mib=8553 留档）；cache `shot_001.json` engine_version=`fl2va-int8/euler+simple/15/1344x768`（896×512 旧 cache 正确全 miss，Pitfall 7 兑现）
- **进程存活**：kill -0 YES（批自续：shot 1 回收后已自动提交下一镜，queue running:1 持续）
- **T2 verify 块全过**：`[roundtrip]` 行在 + sampling 行在 + 无 guard 拒绝/ComfyUI 不可达 + per-shot activity（rendered 行）可见

## Overnight 批后 21-03 数据语义（预告）

- shots 1/47 的 scorer/judge cache（896×512 身份）在批后 key 失配 → 21-03 批量打分自动重算 @1344×768
- 批收尾的 sidecar READ-merge 只覆盖 regen/status 半边，本 plan 写入的 **scores 保留**（Pitfall 8 已验证语义）；21-03 重打分时 scores.midframe_sim 才被新 1344×768 分数 update（scores 可更新是设计语义——冻结只作用于 verdict 半边）
- 因此 896×512 对照数据点以本 SUMMARY Task 1 表格为准（sidecar 中的该数值生命周期到 21-03 重打分为止）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] overnight 批首启 stdout 块缓冲，日志 0 字节**
- **Found during:** Task 2（nohup 启动后 90s/4min 两轮轮询）
- **Issue:** `nohup python3 … > log 2>&1 &` 下 stdout 非 tty → Python 8KB 块缓冲；guard/采样行全部滞留 buffer（实测 5 min 后日志仍 0 字节，尽管进程已过 guard 在渲）。plan 的「3-5 min内日志可证」与 21-03 审计面均不可满足；且 ComfyUI 0.30 /history 不含运行中 prompt，poll 的 continue 分支全数跳过 elapsed 打印——渲中行永不出现，buffer 排空只靠完成行，滞后可达小时级
- **Fix:** SIGTERM 首启客户端（零完成镜，损失 ~4min GPU）+ POST /interrupt 清掉孤儿渲染 + 队列/GPU 复位确认（1586 MiB）→ `python3 -u` 重启同命令。**h3_regen.py 零代码变更**（files_modified 列它本就注明「本 task 无代码变更」）
- **Files modified:** 无代码；仅 invocation 变更（-u）+ 重写 log/pidfile
- **Verification:** 重启后 8s 内日志出现 3 行启动审计；后续 rendered 行实时落盘
- **Committed in:** 本 SUMMARY（docs commit）

---

**Total deviations:** 1 auto-fixed（blocking）
**Impact on plan:** 零 scope creep——仅启动 invocation 修正；断点续跑安全性是该客户端的已验证设计（20-03 SC1）。

## Issues Encountered

- 无其他。Task 1 smoke 修复回路未触发（scorer/judge 模块真机一次过——21-01 替身测试契约面的有效性得到反证）

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - 无占位实现。overnight 批是真实后台进程（非模拟），其**完成**属 21-03 Task 1 范围（本 plan 契约：「批已启动且过守卫」收口，不等 3-4.5h 批完成）。

## Next Phase Readiness

- **21-03 Task 1（批完成度检查）**：入口 = 上表 pidfile/log；`kill -0 $(cat overnight_20.pid)` 判存活；完成后 `roundtrip.json` 应有 19-20 条 regen 半边 @1344×768 + warnings.json 收尾 flush（guard TTS 审计 + 可能的 per-shot foreign-GPU 事件）；未完成部分断点续跑重发同命令即可（cache-hit 跳过已渲镜）
- **21-03 校准**：`scorer.py --work-dir <EP01>`（全量）→ `judge.py --work-dir <EP01>`（全量）→ `--summarize`；896×512 对照数据点见本 SUMMARY Task 1 表
- **SC3 抽检素材**：`roundtrip/_judge_grids/`（2 镜 896×512 已在盘；1344×768 批后 judge 全量跑会补齐）

## Self-Check: PASSED

- 文件存在：route_cache/scorer/shot_00{1,47}.json + route_cache/judge/shot_00{1,47}.json + roundtrip/_judge_grids/shot_00{1,47}.jpg + route_cache/h3_regen/overnight_20.{log,pid} 全 FOUND（本会话直读断言）
- commit 存在：9c5d1b7（Task 1 docs commit）FOUND；本 SUMMARY 为最终 docs commit
- 进程存活：PID 4112729 kill -0 YES（06:53 复核）；schema gate 0 errors；pytest 157 passed

---
*Phase: 21-scorer-threshold-calibration*
*Completed: 2026-08-20（overnight 批后台运行中，交接块见上）*
