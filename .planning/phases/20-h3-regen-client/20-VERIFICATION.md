---
phase: 20-h3-regen-client
verified: 2026-08-20T06:05:00Z
status: passed
score: 5/5 roadmap success criteria verified (16/17 plan-level truths verified + 1 via override)
overrides_applied: 1
overrides:
  - must_have: "run_pipeline --force 清单新增 roundtrip/ 产物目录 + roundtrip.json sidecar（显式清单，绝不 glob 父级）(20-01 truth 6)"
    reason: "WR-01 代码评审红线修正（commit 787d316，re-review clean）：run_pipeline --force 不再删 roundtrip/ 与 roundtrip.json——管线自身不生产 roundtrip 数据（h3_regen 是独立 CLI），且整体 unlink 会违反 schema 红线「verdict rejected 永不删除」。等价能力保留在更强语义上：route_cache/ rmtree 天然覆盖 route_cache/h3_regen/（regen cache 仍被清，满足 ROADMAP SC4 字面），客户端自身 --force 清 roundtrip/ 并以 strip_sidecar_regen_half 只剥 regen/status 半边（scores/verdict 保留）。回归锚 test_force_preserves_verdicts_in_sidecar / test_force_strip_removes_file_when_no_human_data 锁定新语义。"
    accepted_by: "gsd-verifier (carried from 20-REVIEW.md WR-01 governance; pending Kai ratification — strike to reopen)"
    accepted_at: 2026-08-20T06:05:00Z
re_verification:
  previous_status: none
deferred:
  - truth: "uniform-20 全量 live 渲染（19 镜可渲 + shot 70 跳过，ep01 --sample-shots 20 真机全执行）"
    addressed_in: "Phase 21"
    evidence: "ROADMAP Phase 21 depends on Phase 20（regen mp4 是打分对象）且 SC1/SC4 要求『对抽样 regen 镜跑 scorer』『ep01 ≤20 镜双信号分布实测』——uniform-20 渲染是其前置 overnight 批任务；CONTEXT NOT-in-scope 明文『ep01 全量 8-13h 渲染执行（本 phase 交付客户端 + smoke 验证）』"
---

# Phase 20: h3 复现客户端 Verification Report

**Phase Goal:** kst 侧 ComfyUI 直连客户端把每镜 (首帧, 尾帧, prompt) 用 MiniMax H3 fl2va 复现成 regen mp4——per-shot 4-tuple cache + 断点续跑 + VRAM guard + 串行编排，让 8-13h/集 的批量渲染可管理、不撞 OOM（不经 kmc/hermes runtime，不经 subagent）。
**Verified:** 2026-08-20T06:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 客户端对 ep01 `--sample-shots 20` 提交 fl2va workflow（shift_video=12.0 / cfg=1.0 / euler+simple / length 17k+5 对齐），每镜回收 regen mp4；中断重跑只补缺失镜；直接 API 提交+轮询不经 subagent | ✓ VERIFIED | 模板 `analysis/roundtrip/workflow_fl2va.json` 实测：node 21 `shift_video==12.0`、node 30 `euler/simple/steps==15/cfg==1.0`、node 20 `MiniMaxH3ImageToVideo`；`h3_frame_count` 网格断言 0.5→124/5.5→141/6.73→175/19.7→362（全部 n%17==5）。**真机 N=2 live**：shot_001_regen.mp4（970,483B，ffprobe 896×512/**175f**@24fps/7.292s）+ shot_047_regen.mp4（1,389,813B，896×512/**124f**/5.167s），cache meta 含真 prompt_id（25b6bb59…/785e18ff…）。**uniform-20 离线锚点**：`uniform_sample(真实 ep01 shots.json 93 镜 ids, 20)` 与锚点清单 [1,5,…,89] 逐项相等（本 verifier 用真实数据独立复算，非仅信单测）；shot 70 实测 19.73s（>10s，落样后会被跳过）。断点续跑：cache 谓词对当前真产物返回 hit=True（重跑今日即零提交）+ `test_cache_hit_second_run_zero_submissions` / `test_resume_only_missing`（预置 3/5 只补 2 镜）。不经 subagent：grep 不到 `:10588`/`websocket`，提交走 stdlib `/prompt`→`/history/{id}`→`/view`。uniform-20 全量 live = Phase 21 前置 overnight 任务（CONTEXT NOT-in-scope 锁定 + checker 裁定，见 Deferred） |
| 2 | VRAM guard 生效：TTS 占用时先 kill + `POST /free`；剩余显存 <22GB 拒绝提交并记 `[roundtrip]` warning | ✓ VERIFIED | `batch_start_guard`（h3_regen.py:1030-1103）五步固定序：①ss -tlnp :5110/:5111→PID→`os.kill(SIGTERM)` 定向（pkill 仅 ss 失败回退且限两个精确脚本名）+ kill 前后审计 warning ②`comfy_free`（`{"unload_models":true,"free_memory":true}`）③eye 等待 ④二次 /free ⑤`free<22528` 拒整批。测试：`test_vram_batch_gate_refuses`（free=21000→rc0+零提交+warning detail 含 22528 与 top 占用者 pid）、`test_vram_free_called_twice`（/free 恰 2 次 + 批中不调）、`test_kill_tts_port_pid`（SIGTERM 恰发往 {111,222}）。真机证据：ep01 warnings.json 含 smoke 真跑的 guard 审计条目「TTS 端口 [5110,5111] 无监听」；批 gate 真机过线（free=22539≥22528） |
| 3 | qwen-eye（13.4GB lease）与 h3 批串行编排：eye 批跑完释放后 h3 才提交 | ✓ VERIFIED | 批开始绝对值检查 `used=total-free ≥ EYE_LEASE_MIB=13721` → 15s 轮询至 `--vram-wait-timeout`（可配）超时拒批；批中以 PID 归因识别外来占用（`baseline_pid_snapshot` = compute-apps ∪ docker inspect comfyui-primary 主 PID；foreign Σ≥4096MiB 才等待/终止）。测试：`test_vram_batch_eye_wait_timeout`、`test_vram_per_shot_own_cache_not_blocking`（Pitfall 1 反自锁：基线内自身 18GB 驻留直接提交）、`test_vram_per_shot_foreign_blocks`。真机观测：D2 记录 smoke 重跑时 eye 检查真实触发（used=23255 读到渲后驻留 → 等待 → /free 驱逐自愈放行）——guard 在真 GPU 上真实运行 |
| 4 | per-shot 4-tuple cache：prompt_version 变化后旧 cache 失效重渲；`--force` 清单扩展清 regen cache | ✓ VERIFIED | 真数据实证（本 verifier 在真实 ep01 上跑）：`prompt_version_for(真实 prompts.json shot1)` = 8e5b30fd 与 cache meta 一致；**改一字 → cache_read miss；切分辨率 → miss；边界漂移 length 不一致 → miss**（WR-02）。`mp4_sha256` 复核：真实 mp4 分块 sha256 与 meta 存档全等（CR-01 保护在真产物上生效）。测试：`test_prompt_version_change_invalidates`（仅该镜重渲、sibling 仍 hit）、`test_resegmentation_same_prompt_invalidates`、`test_truncated_mp4_rejected_as_cache_hit`。--force：run_pipeline force 块 `route_cache_dir` rmtree 天然覆盖 `route_cache/h3_regen/`（代码含 Phase 20 注释）；客户端自身 `--force` rmtree `route_cache/h3_regen/` + `roundtrip/` + `strip_sidecar_regen_half`（verdict 红线）。SC4 字面（清 regen cache）两条路径均满足；plan 级超出 SC 的 roundtrip.json unlink 已被 WR-01 评审否决（见 override） |
| 5 | >10s 长镜按配置跳过（跳过清单可查）+ `--regen-resolution` 降分辨率验证模式可用 | ✓ VERIFIED | `--max-shot-sec` 默认 10.0，超限镜：str warning + `route_cache/h3_regen/skipped.json` 条目 {shot_id, reason:"duration_over_max", duration_sec}（READ-merge 原子写）。`--regen-resolution`：`validate_resolution`（%32 + 严格 7:4 + ≤MAX_PIXELS）拒 100x100/897x512；896x512 冻进 engine_version（`fl2va-int8/euler+simple/15/896x512`）→ 切换即整 cache 失效。测试：`test_sample_before_filter`（93 镜 uniform-20 → shot 70 落样被跳 → **实渲 19** + skipped.json=[70] + rendered=19/skipped=1/sampled=20）、`test_resolution_flag_invalidates_cache`、`test_resolution_invalid_rejected`。真机：smoke 以 896x512 真渲两镜成功 |

**Score:** 5/5 roadmap success criteria verified

### Plan-Level Must-Have Truths

| Plan | Truth | Status | Evidence |
|------|-------|--------|----------|
| 20-01 | deepcopy 注入后每镜 workflow 携带正确首/尾帧名、prompt_text、17k+5 length、确定性 seed | ✓ VERIFIED | `build_workflow`（:468-487）改 14/15/20/30/50 五组节点；`test_workflow_injection_five_node_groups` + 模板占位符未被污染（磁盘 `<FF_FILENAME>` 原样）；`derive_seed` 跨进程确定（sha256，非 hash()） |
| 20-01 | FakeComfyUI 全链路 mp4 落盘 >1KB | ✓ VERIFIED | `test_submit_poll_download_success`（/upload→/prompt→/history(images 键)→view 下载→cache 写入含 prompt_id） |
| 20-01 | 同 4-tuple + mp4>1KB 重跑 cache-hit；prompt 改一字即重渲 | ✓ VERIFIED | 真数据实证（见 SC4）+ 单测 |
| 20-01 | 预置 3/5 镜 cache 重跑只补缺失 2 镜 | ✓ VERIFIED | `test_resume_only_missing`（断言 fake2.calls 恰 2 次 /prompt + 3 行 cache hit） |
| 20-01 | warnings 双形 merge：dict roundtrip 条目 strip 重写，陌生 str 条目保留 | ✓ VERIFIED | `_is_roundtrip_warning`（dict code∈三码 或 str 前缀）+ `test_warnings_dual_shape_merge` |
| 20-01 | run_pipeline --force 清单新增 roundtrip/ + roundtrip.json | ✓ PASSED (override) | **字面未满足——WR-01 评审红线修正**（commit 787d316）：清单移除两项（防违反「rejected 永不删除」schema 红线 + 管线不产 roundtrip 数据）；regen cache 仍经 route_cache/ rmtree 覆盖（SC4 满足）；等价能力在客户端 --force 以更强语义保留。回归锚 ×2 + re-review clean。详见 frontmatter overrides（待 Kai 批准） |
| 20-02 | 批开始 guard 五步（kill+审计→/free→eye 等待→/free→严格 gate <22528 拒批 exit 0） | ✓ VERIFIED | 代码 + `test_vram_batch_gate_refuses/passes` + `test_vram_free_called_twice` |
| 20-02 | 每镜复查 PID 归因（排除基线含 ComfyUI 自身，渲后 cache 驻留不自锁） | ✓ VERIFIED | `per_shot_vram_ok` + `test_vram_per_shot_own_cache_not_blocking`（pid=100 used=18432 在基线 → 直接提交） |
| 20-02 | eye 串行：used≥13721 等待（--vram-wait-timeout 可配）；批中 eye 以新 foreign PID 识别 | ✓ VERIFIED | `test_vram_batch_eye_wait_timeout` + `test_vram_per_shot_foreign_blocks`（新 pid=999 → 等待→超时→优雅终止） |
| 20-02 | --sample-shots 先抽样后 >10s 过滤；--max-shot-sec 默认 10 + skipped.json | ✓ VERIFIED | `test_sample_before_filter`（A6 语义机器证明） |
| 20-02 | --regen-resolution 896x512 可用且冻进 engine_version → 切换整体失效 | ✓ VERIFIED | 真数据：896x512 cache_read 对 1344x768 key 返回 miss + `test_resolution_flag_invalidates_cache` |
| 20-03 | ep01 真机 --sample-shots 2 896x512：shots 1/47 各回收 >1KB regen mp4 | ✓ VERIFIED | 真产物 ffprobe 安证（尺寸/帧数/时长全对）+ 真 prompt_id + sha256 全等 |
| 20-03 | SC1 验证姿态显式（uniform-20 离线锚点 + N=2 live 双证据；全量 live 为 Phase 21 前置） | ✓ VERIFIED | 20-03-SUMMARY「SC1 验证姿态」节 + 本 verifier 用真实 shots.json 独立复算锚点清单通过 |
| 20-03 | 同命令重跑 2 镜全 cache-hit 零新 /prompt | ✓ VERIFIED | SUMMARY 记录 /history 69 条目零新增；离线强证：cache 谓词对当前真产物 hit=True（今日重跑即零提交）+ `test_cache_hit_second_run_zero_submissions` |
| 20-03 | roundtrip.json regen 半边 schema 合法 degrade 中间态 | ✓ VERIFIED | Draft202012Validator 实测零错（schema_version=1.3，shots [1,47] 全 regen 字段）；duration_sec 7.292/5.167 与 ffprobe 全等 |
| 20-03 | cache meta 含 post_render_free_mib | ✓ VERIFIED | 实测 22539（shot 1）/ 1321（shot 47）——PID 归因设计必要性的一手证据落档 |
| 20-03 | 目视抽检通过（Kai 确认） | ✓ VERIFIED | 记录于 20-03-SUMMARY：Kai approved 2026-08-20 三点检查过；素材可审计（_compare/ 原镜段 ×2 + compare.html 在盘） |

**Plan-level score:** 17/17 (16 direct + 1 override)

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | uniform-20 全量 live 渲染（19 镜 + shot 70 跳过的真机全执行） | Phase 21 | Phase 21 depends on Phase 20 + SC1/SC4 要求 ep01 ≤20 镜抽样打分实测（渲染是其前置 overnight 批任务）；CONTEXT NOT-in-scope 明文本 phase 只交付客户端 + smoke |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `analysis/roundtrip/workflow_fl2va.json` | fl2va 13 节点模板（数据/代码分离） | ✓ VERIFIED | 13 节点（10-15,20,21,30,40,41,42,50）；SC1 锁定参数全在；占位符原样 |
| `analysis/roundtrip/h3_regen.py` | 提交/轮询/下载 + cache + guard + CLI（min 300 行） | ✓ VERIFIED | 1444 行（review-fix 后）；全 stdlib；WIRED（main 入口 + 46 测试） |
| `tests/test_h3_regen.py` | 离线单测（min 250/400/450 行递增） | ✓ VERIFIED | 1214 行 / 46 用例 / 全绿 |
| `run_pipeline.py` | --force 清单扩展（regen cache 覆盖） | ✓ VERIFIED | route_cache_dir rmtree 覆盖 h3_regen/ + Phase 20 注释；roundtrip 两项按 WR-01 移除（override） |
| `output/<ep01>/roundtrip.json` | smoke sidecar | ✓ VERIFIED | schema 1.3 零错，shots [1,47] |
| `output/<ep01>/roundtrip/shot_001_regen.mp4` + `shot_047_regen.mp4` | 真机 regen mp4 | ✓ VERIFIED | 970KB/1.36MB；896×512；175f/124f@24fps |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| h3_regen.py | workflow_fl2va.json | `TEMPLATE_PATH = Path(__file__).parent / …` + deepcopy | ✓ WIRED | `load_template()`，模板磁盘未被污染 |
| h3_regen.py | ComfyUI /prompt /history /view | stdlib `_http_json` + urlopen /view | ✓ WIRED | 真 prompt_id 回收实证 |
| h3_regen.py | route_cache/h3_regen/shot_XXX.json | 4-tuple 元数据与 mp4 分离 | ✓ WIRED | 真文件在盘且与真 mp4 sha 全等 |
| h3_regen.py | nvidia-smi | `--query-compute-apps` list-form | ✓ WIRED | `compute_apps`/`gpu_mem_mib` |
| h3_regen.py | ss -tlnp / os.kill(SIGTERM) | 端口→PID 定向 kill | ✓ WIRED | `find_tts_listeners`/`kill_tts`，绝不宽 pkill（回退限 2 精确脚本名） |
| h3_regen.py | ComfyUI POST /free | `_http_json` 双 bool payload | ✓ WIRED | kill 后 + 批开始前各一次（测试锁定恰 2 次） |
| h3_regen.py | route_cache/h3_regen/skipped.json | >10s 跳镜清单 | ✓ WIRED | `write_skipped_entry` READ-merge 原子写 |
| h3_regen.py | spec/schemas/roundtrip.schema.json | `parent.parent.parent` + Draft202012Validator 写前自校验 | ✓ WIRED | SCHEMA_PATH 存在 + 真产物过校验 |
| h3_regen.py | scripts/export_asset.py | importlib 单源加载 SCHEMA_VERSION | ✓ WIRED | 实测返回 '1.3'，模块内无字面量赋值 |
| run_pipeline.py | route_cache/h3_regen/ | --force route_cache rmtree 覆盖 | ✓ WIRED | 显式清单条目 route_cache_dir（SC4 满足） |
| run_pipeline.py | roundtrip/ + roundtrip.json | --force 显式清理条目 | ⚠️ DEVIATED (override) | WR-01 移除（verdict 红线）；等价能力在客户端 --force |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| roundtrip/shot_001_regen.mp4 | mp4 bytes | ComfyUI /view（prompt_id 25b6bb59…） | ✓ 真 render（175f@24fps/896×512/7.292s，与 6.73s 镜长 17k+5 对齐一致） | ✓ FLOWING |
| roundtrip/shot_047_regen.mp4 | mp4 bytes | ComfyUI /view（prompt_id 785e18ff…） | ✓ 真 render（124f/5.167s，3.2s→floor 124 对齐） | ✓ FLOWING |
| roundtrip.json | shots[] | cache meta / 渲染结果 | ✓ duration_sec 与 ffprobe 全等；vch/prompt_version 与源数据可复算一致 | ✓ FLOWING |
| cache shot_00N.json | meta | 渲染循环写入 | ✓ mp4_sha256 与在盘产物全等（本 verifier 复算） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 全套测试 | `python3 -m pytest tests/ -q` | **119 passed** in 3.42s（与 REVIEW-FIX 声称一致） | ✓ PASS |
| length 网格 + seed 确定性 + 模板参数 + 分辨率校验 | python -c 断言组（20-01/20-02 verify 复跑） | 全过（124/141/175/362 全 n%17==5；896x512 真、100x100/897x512 假） | ✓ PASS |
| uniform-20 锚点 vs **真实** ep01 shots.json | `uniform_sample(real_ids, 20)` | 与 [1,5,…,89] 逐项相等；93 镜；shot 70=19.73s | ✓ PASS |
| roundtrip.json schema 校验 | Draft202012Validator.iter_errors | 零错误（schema_version 1.3，shots [1,47]） | ✓ PASS |
| regen mp4 实体探针 | ffprobe | 896×512 / 175f & 124f @24fps / 7.292s & 5.167s / 970KB & 1.36MB | ✓ PASS |
| 真数据 cache-hit 谓词（今日重跑即零提交） | cache_read + cache_is_hit(expected_length) | shot 1/47 均 hit=True，sha256 与 meta 全等；改一字/切分辨率均 miss | ✓ PASS |
| SCHEMA_VERSION 单源 | `_load_schema_version()` | '1.3'（h3_regen.py 内无字面量赋值） | ✓ PASS |
| spec 门 | `python3 spec/validate.py` | `[validate] OK` failures=0，exit 0 | ✓ PASS |
| 禁用模式扫描 | grep `:10588`\|`websocket`\|`import requests`\|`shell=True` | 零命中（不经 KAP/subagent、纯 stdlib、subprocess 全 list-form） | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — 本 phase 未声明 probe 脚本，`scripts/*/tests/probe-*.sh` 无匹配；验证走 pytest + spec/validate.py + 真机 smoke 产物（均在 Behavioral Spot-Checks 覆盖）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REGEN-01 | 20-01, 20-03 | ComfyUI API 客户端（fl2va 模板 + 提交/轮询/回收，不经 subagent） | ✓ SATISFIED | 模板参数实证 + 真机 N=2 真提交真回收 + 46 测试 |
| REGEN-02 | 20-01, 20-03 | per-shot 4-tuple cache + 断点续跑 + --force 清单扩展 | ✓ SATISFIED | 真数据失效语义三连验证 + resume 测试 + 双侧 --force（run_pipeline 覆盖 cache / 客户端清产物+strip sidecar） |
| REGEN-03 | 20-02 | VRAM guard（TTS kill + /free + <22GB 拒提交）+ eye 串行 | ✓ SATISFIED | 五步序代码+测试 + 真机 guard 真跑（审计 warning 落盘 + gate 22539 过线 + D2 观测） |
| REGEN-04 | 20-02, 20-03 | --sample-shots / --regen-resolution / >10s 跳过 | ✓ SATISFIED | uniform-20 真数据复算 + shot70 跳过测试 + 896x512 真机模式 |

Orphaned requirements: 无 — REQUIREMENTS.md 映射 Phase 20 的 REGEN-01..04 恰被 20-01/02/03 三个 plan 的 requirements 字段全覆盖，且四条已勾选 Complete（与 Traceability 表一致）。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| h3_regen.py | 7, 597 | grep "XXX" 命中 | ℹ️ Info | 非债务标记——是 `shot_XXX_regen.mp4` 文件名占位符约定的组成部分 |
| h3_regen.py | 多处 | IN-01..IN-08（评审 Info 项：no-op SIGINT handler、三码 enum 复制、kill 后审计非复探等） | ℹ️ Info | 评审裁定 out of fix_scope 接受；非阻塞，不影响目标 |
| deferred-items.md | D1/D2 | poll 心跳渲染期不可达（cosmetic）/ 重跑起批 eye 检查瞬时误读自身 cache（自愈） | ℹ️ Info | 已记录 + Phase 21 前建议；非 gap（正确性零影响 / fail-safe 方向） |

无 TBD/FIXME/TODO/PLACEHOLDER 债务标记；无空实现；无 console.log-only 路径；subprocess 全 list-form 无 shell 插值。

### Human Verification

无待办人工项。Phase 唯一 human checkpoint（20-03 Task 3 目视抽检）已由 Kai 于 2026-08-20 执行并 approved（三点检查：首尾帧贴合 / 运动符合 prompt / 无爆裂黑帧），记录于 20-03-SUMMARY；抽检素材（roundtrip/_compare/ 原镜段 ×2 + compare.html）在盘可审计。其余全部行为已由本 verifier 以代码/真产物/测试自动化复核。

**Override 待批注记（供 Kai 裁决，非阻塞）**：frontmatter overrides 中 1 条——run_pipeline --force 不再清 roundtrip/ + roundtrip.json（WR-01 评审红线修正：防删除 Phase 21 人工 scores/verdict、管线不产 roundtrip 数据）。ROADMAP SC4 字面（清 regen cache）不受影响（route_cache/ rmtree 已覆盖）。若不认可该偏差，移除本 override 即转为 gap 重开规划。

### Gaps Summary

无阻塞 gap。全部 5 条 ROADMAP 成功标准以「代码 + 离线测试锚 + 真机真产物」三层证据验证通过；REGEN-01..04 全部 SATISFIED；119 测试全绿 + spec validate exit 0；评审生命周期完整（2C+5W 修复 → re-review clean → 16 回归锚）。一处 plan 级字面偏差（run_pipeline --force 的 roundtrip 两项）为评审治理下的有意收紧，以 override 形式记录待 Kai 批准；uniform-20 全量 live 为 Phase 21 前置 overnight 任务（CONTEXT 锁定 scope），已列 deferred。

---

_Verified: 2026-08-20T06:05:00Z_
_Verifier: Claude (gsd-verifier)_
