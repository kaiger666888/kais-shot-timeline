---
phase: 19-qwen-eye-v2
fixed_at: 2026-08-19T18:52:08Z
review_path: .planning/phases/19-qwen-eye-v2/19-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 19: Code Review Fix Report

**Fixed at:** 2026-08-19T18:52:08Z
**Source review:** .planning/phases/19-qwen-eye-v2/19-REVIEW.md
**Iteration:** 1
**Scope:** Critical + Warning（fix_scope 默认；IN-01..07 为 Info，不在本次范围）

**Summary:**
- Findings in scope: 5（CR-01 + WR-01..04）
- Fixed: 5
- Skipped: 0

**Gates（fix 后全量回归）:**
- `python3 -m pytest tests/ -q` → **73 passed**（62 baseline 零回归 + 11 个新回归测试）
- `python3 spec/validate.py` → exit 0（minimal/v1.1/v1.2/v1.3 fixtures 全 valid，failures=0）

## Fixed Issues

### CR-01: select_uniform_frames 时窗下界 off-by-one（~78-96% 真实镜头取到镜前帧）

**Files modified:** `analysis/vision_seq_facets.py`, `tests/test_vision_seq_facets.py`
**Commit:** 0caae2a
**Applied fix:**
- `lo = int(start_sec * fps) + 1` → `lo = math.ceil(start_sec * fps) + 1`（帧 N 时间戳 = (N-1)/fps，首个 t≥start 的帧号是 ceil+1；ceil 对网格对齐边界与旧行为逐位一致，`hi` 保持 floor inclusive-safe 不变）。
- `PROMPT_VERSION` bump `vision-seq-v1` → `vision-seq-v2`（按 fix contract 指定值，非 REVIEW 建议的 v1b）：RAW cache 键按帧号索引，修正改变了帧号→图像映射，旧 cache 必须整体失效。
- 回归测试 `test_select_uniform_frames_fractional_window`：[0.5, 2.5]@5fps 首帧必须是 f000004（帧 3 t=0.4<0.5 是上一镜尾帧，绝不入列）；整数 start*fps 边界行为不变。

**⚠️ Spike cache 失效说明（按 fix contract 指示，设计行为）：**
bump 使既有 `route_cache/vision_seq/`（含 spike 实录烧出的证据）全部 miss。**本次 fix 未重烧** —— 下次真实运行的 cache miss + 重烧是正确行为（spike 实录约 15min/集）。不要为「保 cache」回退 bump。

**Deferred（v1 镜像，本 phase 不修）：**
`analysis/local_vision_facets.py:126` 的 `select_frames` 用同一 `int(start_sec * FRAME_SAMPLING_FPS) + 1` floor 惯例 —— 同源 off-by-one 存在于 v1（scene/subject 3 静帧路径，首帧偏移同样会带进上一镜尾帧，但 scene 静态描述受影响小于 action/camera 时序链）。**v1 红线零改动**，未触碰；如需修复应另开 phase（同步 bump v1 侧 cache 版本）。

### WR-01: cache 键缺采样维度；merge 消费无界 stale 键；merged_B 不随 RAW 失效

**Files modified:** `analysis/vision_seq_facets.py`, `tests/test_vision_seq_facets.py`
**Commit:** 9209d75
**Applied fix:**
- **window 契约进信封**：每 shot 信封持久化 `{"start_sec", "end_sec", "fps", "n_frames", "needed": {"action": N, "camera": M}}`，`_load_cache_envelope` / `_save_cache_envelope` 均参与匹配 —— shots 重检测/参数变化产生的窗口漂移 → 整体 miss 重拉（reviewer 的 seeded-stale repro 场景不再可达）。
- **合并限界**：`_facet_answer_values(env, facet, needed)` 只收索引 1..needed —— 超窗残留键（旧更密采样的 action_frame_7/8）绝不进 temporal/longest/llm 任何合并。
- **merged_B 失效**：`_save_cache_envelope(new_answers=...)` 落盘时 pop 受影响 facet 的 merged_B；main step 5 内存信封同步 pop —— llm 策略不再被陈旧 merged_B「已缓存零 GPU」短路。
- **空答显式 warning**：needed 键在位但清答为 ""（引擎空答被缓存为已答）→ `[vision-seq] shot X: N/M RAW answers empty — merging partial evidence`，部分证据合不再静默。
- 4 个回归测试：window 篡改 → miss；超窗键不进合并；merged_B 随补烧失效重合并；空答 warning。

### WR-02: FRAME_SAMPLING_FPS 硬编码 5.0 vs run_pipeline --sample-fps 可配

**Files modified:** `analysis/vision_seq_facets.py`, `run_pipeline.py`, `tests/test_vision_seq_facets.py`, `tests/test_pipeline_vision_seq_wiring.py`
**Commit:** 72e1878
**Applied fix:**
- `vision_seq_facets` 新增 `--frame-fps`（type=float，默认 5.0；≤0 fail-loud），`select_uniform_frames` 增 `fps` 参数参与 lo/hi 换算。
- `run_pipeline` cmd_vseq 直通 `"--frame-fps", str(args.sample_fps)`（REVIEW Fix 的主方案）。
- fps 进 window 契约：抽帧率变化 → 帧号↔时窗映射变化 → cache 必 miss 重烧（测试 `test_frame_fps_mismatch_misses_cache` 锁定）。
- 静态接线锁：`tests/test_pipeline_vision_seq_wiring.py` 断言 `--frame-fps` 直通在 5.6 调用构造内（5.5 之后、step 6 之前）。

**残留缺口（deferred，非本次范围）：**
直通值反映**本次 flag**；若 frames_5fps 是按旧 `--sample-fps` 抽出、而 shots.json 存在令 detect 步命中缓存，目录实际帧率与本 flag 仍错配。完整修法是 detect_v3b 写 `frames_5fps/fps.json` sidecar 供消费方读取（REVIEW Fix 的备选方案）—— 需触碰 validated 基线检测模块，建议另开小 phase。

### WR-03: 引擎生命周期泄漏 —— 失败 start 返回 (False, True) 但 _owned=False；KAP allocate 无 release 配对

**Files modified:** `analysis/engine_clients/qwen_eye_client.py`, `tests/test_qwen_eye_client.py`
**Commit:** a97ae2c
**Applied fix:**
- **归属修正**：allocate 成功或 fallback 脚本已跑（= 实际发起过 start）即置 `self._owned = True`，不再等 health-OK —— 慢启动超时 / Guard-2 load 失败的 (False, True) 路径现在同样被 `stop_if_owned()` 覆盖，半启动 server 不再 13.4GB 无人管理。预存在（health 即命中、从未发起 start）依旧绝不动。
- **KAP lease 配对释放（已落地，非仅文档）**：`_lease_granted` 记录 allocate 授予；`stop_if_owned()` 停 server 后 best-effort `POST :10588/api/production/llm/release`（payload mirror allocate 的 caller 归因；幂等不重复）。
  - 证据：release 路由存在于 kais-aigc-platform `src/routes/production/llm/index.ts:135-147`（解除 GPU 队列服务级占位 + scheduler.release）。
  - 反证（为何必须显式 release）：本机核验 `/opt/qwen-llm/kap-llm.sh`（180 行）—— stop 仅 `pkill -f llama-server`，全脚本无任何 10588/lease/release 调用。
- 3 个回归测试：超时路径 owned+stop；load-fail 路径 owned+stop；allocate→stop→release 配对 + 幂等。

### WR-04: ear cache 维度 boolean-only —— audio_semantic.json 内容变化永不失效

**Files modified:** `analysis/vision_seq_facets.py`, `tests/test_vision_seq_facets.py`
**Commit:** 0523483
**Applied fix:**
- `_audio_ctx_fp(audio_ctx)` = sha256[:8]；ear_on 信封持久化 `ear_ctx_fp` 并参与 load/save 匹配 —— audio_semantic 内容变化（route 重跑/修复后）→ miss 重烧，无需 bump PROMPT_VERSION（那会连 ear_off 证据一起丢）。
- audio_ctx 在 step 4 预判阶段一次算好存 work item，step 5 提问复用（消除重复计算）。
- 回归测试：对白内容改写（ear 开关不变）→ miss 重烧 + 新提问含新对白 + 信封 fp 更新。

## Skipped Issues

None — 全部 5 个 in-scope findings 已修复。

**Out of scope:** IN-01..IN-07（Info 级：答案长度 cap / 注入面文档 / v1 共享 caller identity / MERGE_B_PROMPT 版本文档 / ear 重烧 docstring 措辞 / warnings sidecar 原子写 / spike 自检假阳性）—— fix_scope 默认 Critical+Warning，未触碰。

---

_Fixed: 2026-08-19T18:52:08Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
