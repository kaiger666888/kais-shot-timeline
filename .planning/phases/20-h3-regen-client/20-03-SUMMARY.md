---
phase: 20-h3-regen-client
plan: 03
subsystem: analysis
tags: [comfyui, fl2va, h3, regen, roundtrip, sidecar, smoke, resume-proof, checkpoint]

# Dependency graph
requires:
  - phase: 20-h3-regen-client
    provides: 20-01/20-02 h3_regen.py 渲染链 + 4-tuple cache + guard/抽样/降载 + FakeHTTP/FakeClock 测试基建
  - phase: 18-contract-v1.3
    provides: roundtrip.schema.json（regen 半边 degrade 中间态合法性 + path/长度 pattern）
provides:
  - write_roundtrip_sidecar（regen 半边 + READ-merge 保留 Phase 21 scores/verdict + Draft202012Validator 写前自校验 + export_asset SCHEMA_VERSION 单源加载）
  - SC1 真机闭环证据：ep01 shots 1/47 真提交→真回收（896×512/175f/124f）→ 同命令重跑 2 镜全 cache-hit、/history 零新增
  - Open Q1 渲后水位实测数据（post_render_free_mib 22539/1321——PID 归因复查设计必要性的一手证据）
  - 3 个 sidecar 单测（degenerate schema 合法 / READ-merge / 路径穿越拒绝），全套 103 passed
  - 目视抽检素材：roundtrip/_compare/ 原镜切段 ×2 + compare.html 并排同播页（tailscale 可达）
affects: [21-scorer, 22-dataset-export]

# Tech tracking
tech-stack:
  added: []   # 零新包（jsonschema 4.26.0 已是 spec/ 既有依赖）
  patterns:
    - "READ-merge by shot_id：只替换 regen/status 半边，陌生键（Phase 21 scores/verdict）原样保留——增量补齐无全量重写负担"
    - "schema_version 单源加载：importlib.util.spec_from_file_location('export_asset_version', scripts/export_asset.py) 取属性，模块内无字面量"
    - "写前自校验（mirror vision_seq L705-713）：Draft202012Validator.iter_errors → 前 3 错误 sys.exit → tmp + os.replace"
    - "三层 parent 路径修正：analysis/roundtrip/ 比 vision_seq 深一层，repo root = parent.parent.parent（PATTERNS §F 陷阱）"
    - "sidecar results 双形态元素：cache meta + shot_id + mp4 绝对路径（rendered/cache-hit）或 {shot_id, error}（failed）"

key-files:
  created:
    - .planning/phases/20-h3-regen-client/deferred-items.md
  modified:
    - analysis/roundtrip/h3_regen.py
    - tests/test_h3_regen.py
  runtime-artifacts (output/ gitignored, 不进 git):
    - "output/<ep01>/roundtrip.json（schema 1.3 校验过，shots [1,47]）"
    - "output/<ep01>/roundtrip/shot_001_regen.mp4（970KB/7.292s/896×512/175f）"
    - "output/<ep01>/roundtrip/shot_047_regen.mp4（1.36MB/5.167s/896×512/124f）"
    - "output/<ep01>/route_cache/h3_regen/shot_001.json + shot_047.json（prompt_id/seed/length/post_render_free_mib）"
    - "output/<ep01>/roundtrip/_compare/{shot_001_orig,shot_047_orig}.mp4 + compare.html（Task 3 抽检素材）"

key-decisions:
  - "REGEN-01/02/04 保持未勾选 —— Task 3 目视抽检（blocking checkpoint）待 Kai approved 后由 continuation 勾选（mirror 20-01/20-02 先例）"
  - "早退路径（ComfyUI 不可达 / guard 拒绝）不写 sidecar：本轮无新增产物，READ-merge 空集本就是恒等变换，既有 roundtrip.json 原样保留"
  - "cache-hit 镜从 cache meta 重建 sidecar 条目（非仅本轮 rendered）——断点续跑后 roundtrip.json 完整性的关键"
  - "failed 明细 failed_detail[sid] 随四类失败点收集（超时/文件名非法/产物过小/异常），error 截 2000（schema T-18-02 上界）"

requirements-completed: []   # Task 3 approved 后统一勾选 REGEN-01/02/04

# Metrics
duration: ~18min（至 checkpoint；Task 3 目视抽检另计）
completed: 2026-08-20（Tasks 1-2；Task 3 pending）
---

# Phase 20 Plan 03: sidecar + 真机 smoke + 目视抽检 Summary

**roundtrip.json regen 半边写入（READ-merge + schema 写前自校验 + 单源版本）+ ep01 真 ComfyUI smoke 双镜真提交真回收 10.5min + 同命令重跑全 cache-hit 零新提交 + 渲后水位实测——Task 3 目视抽检 checkpoint 待 Kai**

> **状态：CHECKPOINT（2/3 tasks complete）**——Task 3（blocking human-verify）已备好并排抽检素材，
> 等 Kai 目视裁决。批准后 continuation 需做的收尾见文末「Continuation Steps (after approved)」。

## Performance

- **Duration:** ~18 min（Tasks 1-2 至 checkpoint；2026-08-19T20:29Z–20:46Z）
- **Tasks:** 2/3（Task 3 awaiting Kai）
- **Files modified:** 2 代码/测试 + 1 deferred-items（output/ 产物 gitignored 不计）

## Task Commits

1. **Task 1: write_roundtrip_sidecar（regen 半边 + READ-merge + schema 写前自校验）** - `2d6d41a` (feat)
2. **Task 2: sidecar 单测 ×3 + ep01 真 ComfyUI smoke + cache-hit 重跑实证** - `9a5174b` (test)
3. **Task 3: 目视抽检 checkpoint** — 素材已备（_compare/ 切段 + compare.html），无代码 commit，待 approved

## Accomplishments

### Task 1 — write_roundtrip_sidecar（Open Q2 裁决落地）

- `SCHEMA_PATH` 三层 parent 命中 `spec/schemas/roundtrip.schema.json`（存在性断言过）；`_load_schema_version()` importlib 加载 `scripts/export_asset.py` 取 `SCHEMA_VERSION`（='1.3'，模块内 grep 不到字面量赋值）
- READ-merge：既有同 shot_id 条目只替换 regen/status 半边，scores/verdict 等 Phase 21 字段原样保留；JSON 损坏→空重建；写前 Draft202012Validator 全量 iter_errors（有错 sys.exit 不落盘）→ tmp+os.replace 原子写
- main() 收尾接线：cache-hit 镜从 cache meta 重建条目；failed 明细四类失败点收集（error 截 2000）
- plan 的 verify 片段全过（merge 保留断言 + schema 零错断言 + '1.3' 单源断言）

### Task 2 — 单测 + 真机 smoke + 断点续跑实证

**离线**：3 个 sidecar 用例（degenerate schema 零错 / READ-merge 保留未来字段+损坏重建 / path 含 `..` → sys.exit 且文件未写）；全套 **103 passed**（100 基线 + 3 新增，零回归，3.4s）。

**真机 smoke（唯一真 GPU 步骤，wall ~10.5 min，落在 10-30min 预估带内）**：

| 阶段 | 时刻（本地） | 事件 |
|------|------------|------|
| 预检 | 04:29 | ComfyUI 0.30.0 /system_stats 200；GPU1 total=24576 **free=22539**（≥22528 过线 11MiB，music3 676 + ComfyUI idle 692 常驻——Pitfall 9 锚点复现）；:5110/:5111 无监听（guard no-op 安全） |
| 起批 | 04:32 | `--sample-shots 2 --regen-resolution 896x512`；uniform 93→[1,47]；guard 五步过（双 /free + gate 22539≥22528） |
| shot 1 | 04:32→04:38:25 | 真提交 prompt_id `25b6bb59…` → 回收 **970,483B / 7.292s / 896×512 / 175f**（≈6min 含首镜模型加载） |
| shot 47 | 04:38→04:42:26 | 真提交 prompt_id `785e18ff…` → 回收 **1,389,813B / 5.167s / 896×512 / 124f**（≈4min） |
| 收尾 | 04:42 | roundtrip.json 写入（2 shots，schema 1.3 校验通过）；rendered=2 failed=0 skipped=0 |

**重跑（同命令）**：2 行 `cache hit, skipping`、rendered=0、rc=0；`/history` 69 条目**零新增**（kst prompt 恰两条且为首跑两个 prompt_id）；roundtrip.json shots [1,47] 稳定不变。**SC1 断点续跑真机实证成立。**

**cache 元数据**：prompt_id/seed（129233213 / 1379825726）/length（175/124）/width/height 全落位；**post_render_free_mib = 22539（shot 1）/ 1321（shot 47）**。

**Open Q1 渲后水位分析**：渲后 free 可低至 **1321MiB**（ComfyUI 自身 cache 驻留 ~21GB），也可在 offload 后回到 22539——同机同批两镜间波动一个数量级。这直接证明 20-02「每镜复查走 PID 归因、绝不设绝对 free 下限」的设计是必要的（绝对值复查在 1321 水位必然自锁）；批开始严格 gate（冷启动时刻）语义仍成立。副产物证据：紧接首跑的重跑中，批开始 eye 绝对值检查瞬时读到 used=23255（=24576−1321，正是 shot 47 渲后驻留）短暂等待后自愈——见 deferred-items D2。

### SC1 验证姿态（must_haves 显式要求载明）

SC1 的 `--sample-shots 20` 语义以**双证据**覆盖：
1. **uniform-20 离线锚点**：20-02 `test_uniform_sample_ep01`（93 镜 n=20 → 20 个确定位置 [1,5,10,…,89]，shot 70 落样后被 >10s 跳过 → 实渲 19）+ `test_sample_before_filter`（先抽样后过滤的 A6 语义）；
2. **N=2 live 证明**：本 plan `--sample-shots 2` 真机全链（同一 uniform_sample 函数、同一提交/回收/cache 路径）。

**uniform-20 全量 live（19 镜可渲 + shot 70 跳过）不在本 phase 执行**——安排为 **Phase 21 前置 overnight 批任务**（CONTEXT NOT-in-scope 载明；smoke 严格限 2 镜 + 896×512，threat T-20-10 禁止扩全量）。

## Files Created/Modified

- `analysis/roundtrip/h3_regen.py` - +161 行（1066→1225）：sidecar 四函数 + main 收尾接线 + docstring
- `tests/test_h3_regen.py` - +111 行（749→860）：3 个 sidecar 用例 + jsonschema import
- `.planning/phases/20-h3-regen-client/deferred-items.md` - D1/D2 两条执行期发现
- 真机产物（gitignored）：见 frontmatter runtime-artifacts

## Deviations from Plan

None - plan executed exactly as written（Task 2e 中断变体按 plan 标注 stretch 可选未做——`test_resume_only_missing` 已锚定该语义，不阻塞验收）。

## Issues Encountered

- 真机重跑时批开始 eye 检查瞬时误读自身 cache（used=23255≥13721）→ 15s 等待一周期后 /free 驱逐生效自动放行（自愈、rc=0）。保守方向假阳性，fail-safe 语义内；详见 deferred-items D2。
- poll 心跳日志渲染期间不可达（ComfyUI /history 只收录已完成 prompt）——cosmetic，正确性零影响；详见 deferred-items D1。

## User Setup Required

**Task 3 目视抽检（blocking checkpoint）——需要 Kai 看片裁决**：

- 并排同播页（推荐， tailscale 可达）: `http://100.124.72.88:8765/_compare/compare.html`
- 或逐个看（serve 根 = ep01 roundtrip/）:
  - 原镜: `http://100.124.72.88:8765/_compare/shot_001_orig.mp4` / `shot_047_orig.mp4`
  - regen: `http://100.124.72.88:8765/shot_001_regen.mp4` / `shot_047_regen.mp4`
- 本地路径: `output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。/roundtrip/`
- **三点检查**：① 首帧/尾帧与原镜首尾帧内容一致（condition 贴合，构图无偏移糊化）② 主体与运动方向大体符合该镜 prompt_text ③ 无明显爆裂/黑帧/时长异常（896×512 模式比内容不比清晰度；regen 因 17k+5 网格略长于原镜属预期）
- **resume-signal**: 回复 "approved"（2 镜均贴合）或描述问题镜号与现象（如 "shot 47 首帧偏色"）
- 静态服务进程: `python3 scripts/serve.py <roundtrip dir> 8765`（PID 见 /tmp/kst_serve_2003.log；看片后可 kill）

## Continuation Steps (after approved)

1. SUMMARY 本节补 approved 记录（或问题镜号进 deferred/learnings）；State Update: Self-Check 补验
2. `gsd-sdk query requirements.mark-complete REGEN-01 REGEN-02 REGEN-04`（REGEN-03 已随 20-02+本 smoke 的 guard 真机行为满足——四项一并勾选前按 REQUIREMENTS 实际语义复核 REGEN-03 归属 20-02/20-03 共享）
3. `gsd-sdk query state.advance-plan` + `state.update-progress` + `state.record-metric 20 3 <dur> 3 2` + ROADMAP 20-03 勾选（本次已按 checkpoint 态标注未勾）
4. 视 Kai 反馈决定是否触发 Phase 21 前置 overnight uniform-20 批任务

## Self-Check: PASSED

- Files: h3_regen.py / test_h3_regen.py / deferred-items.md / 20-03-SUMMARY.md 存在；真机产物 2 mp4 >1KB、roundtrip.json schema 零错（本 plan verify 块实跑通过）
- Commits: 2d6d41a / 9a5174b 在 git log
- Full suite: 103 passed（100 基线 + 3 新增，零回归）
- Task 3 素材: _compare/ 2 切段（6.733s/3.200s 1920×1080 faststart）+ compare.html 200 可达（206 Range 验证过）

---
*Phase: 20-h3-regen-client*
*Tasks 1-2 completed: 2026-08-20；Task 3 checkpoint pending Kai*
