---
phase: 21-scorer-threshold-calibration
reviewed: 2026-08-20T02:47:19Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - analysis/roundtrip/scorer.py
  - analysis/roundtrip/judge.py
  - tests/test_scorer.py
  - tests/test_judge.py
findings:
  critical: 1
  warning: 5
  info: 6
  total: 12
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-08-20T02:47:19Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

对 scorer.py（SigLIP so400m 帧窗打分 + cache + sidecar 半边写入）与 judge.py（qwen-eye 三分类 + verdict 冻结应用器 + --summarize）及其测试做了逐文件审读，并交叉核对了 h3_regen.py 共享件契约（`_ROUNDTRIP_WARNING_CODES`、`_CACHE_KEY_FIELDS`、`append_roundtrip_warnings`、`_atomic_write_json`、`load_shot_prompts`）与 `spec/schemas/roundtrip.schema.json`。41/41 测试实跑通过。

核心算法面**验证为正确**：

- 帧窗数学（`frame_ts`/`plan_frames`/`grid_ts`）：t_pct 序列 25→75、clamp 语义、`t=0/t=end` 在常规时长下结构性不可达，均与锚点一致；
- cosine 计算：`embed_frames` L2 归一 → `np.dot(emb[j], emb[8+j])` 逐位即余弦，mean 后 clamp [0,1] round 4，数学正确；fp16/fp32 device 匹配一致；
- JSON 解析容错：fence 剥离 / 花括号截取 / 尾 `}` 截断修复不放松 enum/conf/reason 校验（有回归测试）；confidence 的 bool-int 子类陷阱已显式排除；
- verdict 冻结：`_merge_write_sidecar` 的 verdict pop + kept-keys 保序使 auto/human verdict 永不覆盖，且与 h3_regen `write_roundtrip_sidecar` 双向互不破坏（有测试）；
- cache key 的 `window` 用 `list(WINDOW_PCT)` 而非 tuple（JSON roundtrip 后 list==list，否则会恒 miss）——细节正确；
- `scorer_model_missing` 确认在 h3_regen `_ROUNDTRIP_WARNING_CODES` 三码闭集内（strippable）；
- schema-write safety：原子写 + 两层自校验 + 剔除前 `.bak-<ts>` 备份齐全。

主要问题集中在**cache 与 sidecar 的分歧恢复路径**（CR-01）、**cache key 完整性缺口**（WR-01/WR-02）、以及两处健壮性缺口（WR-03/WR-05）。

## Critical Issues

### CR-01: cache 全命中路径永不回填 sidecar + cache 写先于 sidecar 写 —— 中断后重跑「静默成功」且分数永不落盘

**File:** `analysis/roundtrip/scorer.py:511-515`、`analysis/roundtrip/scorer.py:547-553`、`analysis/roundtrip/judge.py:730-734`、`analysis/roundtrip/judge.py:805-823`
**Issue:** 两个模块都是逐镜 `cache_write`（scorer L547 / judge L805）在批**内**，而 sidecar 写入在批**末**（scorer L552-554 / judge L821-823）。若批末写入未发生——`_atomic_write_json` 抛 OSError（磁盘满）、Ctrl-C、或 sidecar 写入 sys.exit——cache 已持久而 sidecar 没有分数。此后**每次重跑都走全命中早退分支**：

```python
if not misses:
    ...
    print(f"{STEP_TAG} 全部 cache 命中（hit={hits} miss=0）—— 零模型加载，无新分数")
    return 0
```

rc=0、无任何 warning、日志看似健康，但 midframe_sim/judge 半边**永远不会**落进 roundtrip.json（Phase 22 gallery / dataset 导出的唯一交付面）。sidecar 被删/损坏后重跑 pipeline 也落入同一死局（h3_regen 重建 regen 半边、scorer/judge 全命中不写、scores 半边永久丢失）。这与 h3_regen 自己的既有设计直接相悖——h3_regen L742-745 明确「cache-hit 镜从 cache meta 重建——断点续跑后 sidecar 完整性的关键」。真机 19 镜本轮未踩中（sidecar 已落），但 Phase 22 重渲/恢复流必踩。
**Fix:** 全命中（或命中子集）时从 cache payload 重建半边条目并写 sidecar，mirror h3_regen 的 cache-hit 重建语义：

```python
# scorer.py main（judge.py 同理）：misses 为空时也回填
replayed: list[dict] = []
for sid, _regen, _path in candidates:
    meta = cache_read(sid, work_dir, keys[sid])
    if meta is not None:
        replayed.append({"shot_id": sid, "scores": {"midframe_sim": {
            "score": meta["score"], "model": MODEL_LABEL}}})
if replayed and replayed != 已在 sidecar 的内容:
    pending_warnings.extend(write_scores_sidecar(work_dir, replayed))
```

（或最低成本修法：把批末单次 sidecar 写改为逐镜写 / 或在早退分支检测 sidecar 缺该半边时强制回放。）

**Outcome (fix):** FIXED — 两模块各新增 `_replay_hit_entries(work_dir, hit_shots, keys)`：cache-hit 镜从 cache meta（scorer 取 score / judge 取 parsed 三件套，字段原样透传）重建半边条目，与 sidecar 现存内容比对后只回填缺席/不同值的镜（纯 no-op 重跑不重写 roundtrip.json）。接入两条路径：① 全命中早退分支先回填再 return（含 pending_warnings flush）；② 命中子集路径在批尾 `new_entries.extend(replay)`——per-shot cache_write 先于批尾 sidecar 写的中断窗口由此闭环，重跑即自愈。选择主修法（回放）而非逐镜写：保持批末单次写的原子性/性能，语义 mirror h3_regen L742-745 的 cache-hit 重建。回归锚：`test_cache_hit_backfills_missing_sidecar_half`、`test_partial_hit_backfills_interrupted_half`（scorer）、`test_judge_cache_hit_backfills_missing_sidecar_half`（judge）。

## Warnings

### WR-01: judge cache key 缺 prompt 身份维 —— prompts.json 修订后 stale attribution 命中

**File:** `analysis/roundtrip/judge.py:131-132`、`analysis/roundtrip/judge.py:718-723`
**Issue:** judge 的 attribution 是 `prompt_text` 的直接函数，但 `_JUDGE_KEY_FIELDS = (video_content_hash, regen_mp4_sha256_16, engine_name, engine_version)` 不含任何 prompt 身份。prompts.json 改稿（prompt_text/prompt_version 变）而 regen mp4 未重渲（字节不变 → sha16 不变 → vch 不变）时，重跑 judge 全命中，返回基于旧 prompt 的归因。h3_regen 自己的 `_CACHE_KEY_FIELDS`（L602）就含 `prompt_version`——本模块对齐了引擎/产物维却漏掉了 repo 先例里已有的 prompt 维。
**Fix:** sidecar 的 `regen` 对象已带 `prompt_version`，judge 取 candidates 时把它（或 prompt_text 的 sha16）并入 key：

```python
key = {
    "video_content_hash": vch,
    "regen_mp4_sha256_16": regen_sha16(regen_path),
    "engine_name": ENGINE_NAME,
    "engine_version": ENGINE_VERSION,
    "prompt_version": str(regen.get("prompt_version") or ""),
}
```

**Outcome (fix):** FIXED — 采纳建议原样：`_JUDGE_KEY_FIELDS` 四字段 → 五字段（+`prompt_version`），key 装配处并入 `str(regen.get("prompt_version") or "")`（sidecar regen 半边自带该值，无需改 prompts.json 读路径）；payload = dict(key) 使该维自动进 cache 留档。模块 docstring 步骤 2 与 cache 惯例同步改为「五字段」。存量 judge cache 因缺该字段全部 miss 重判（预期行为——attribution 是 prompt_text 的直接函数）。回归锚：`test_judge_cache_key_prompt_revision_rejudges`（pv1→pv2、mp4 字节不变 → 重判 + payload 留档）；`test_judge_all_cache_hit_zero_instantization` 的预置 payload 同步补 `prompt_version`。

### WR-02: scorer cache key 缺 orig 侧镜几何维 —— 重分割后 stale 分数命中

**File:** `analysis/roundtrip/scorer.py:108-109`、`analysis/roundtrip/scorer.py:498-504`
**Issue:** midframe_sim 的 orig 半边帧窗由 shots.json 的 `start_sec`/`duration` 决定，但 key 五字段（vch + regen sha + model + n + window）不含镜几何。同一源视频重分割（vch 不变）且 regen 产物沿用时，shot N 的语义时间段已变，cache 仍命中并返回按旧时间戳算出的分数。scorer 不依赖 prompt（与 WR-01 不同），依赖的恰是这一维。
**Fix:** 把 orig 侧几何并入 key（payload 里本就存了 `frames.orig` 清单，key 加最小身份即可）：

```python
key = {
    "video_content_hash": vch,
    "regen_mp4_sha256_16": regen_sha16(regen_path),
    "orig_window": [round(float(shot.get("start_sec", 0.0)), 3),
                    round(dur, 3)],
    "model": MODEL_LABEL, "n_frames": N_FRAMES, "window": list(WINDOW_PCT),
}
```

（或以 shots.json 内容 hash 作一维。）

**Outcome (fix):** FIXED — 采纳建议原样：`_SCORER_KEY_FIELDS` 五字段 → 六字段（+`orig_window: [round(start_sec,3), round(duration,3)]`），key 装配处从 shots_index 取镜几何（dur 推导式与 score_shot 同义；round 3 为几何最小身份）。payload = dict(key) 使该维自动进 cache 留档。模块 docstring 步骤 2 / cache 惯例 / cache_read docstring 同步改「六字段」。存量 scorer cache 因缺该字段全部 miss 重打分（预期——scored_at/device 均会刷新，τ 校准锚不受影响）。回归锚：`test_cache_key_miss_on_geometry_change`（start 0→1.5、mp4 字节不变 → 重打分 + orig_window 留档 [1.5, 6.73]）。

### WR-03: scorer 的 `float(regen.get("duration_sec"))` 在 per-shot try 守卫之外 —— 单条坏值炸整批

**File:** `analysis/roundtrip/scorer.py:536-538`
**Issue:** 读侧 `_read_sidecar_shots` 不做 schema 校验（Phase 18 挂载前仅 JSON-parse 语义）。hand-edit/损坏 sidecar 里 `duration_sec: "6,73"` 之类非数值会让 `float()` 抛 ValueError——该行在 `try: score_shot(...)` 之外，未被「单镜失败不阻塞批」守卫捕获，整批 traceback 退出（rc≠0），违反本模块自述的不变量。judge.py 的同一逻辑在 try **内**（judge.py L764-767），两模块不一致本身就是漂移证据。
**Fix:** 把 coercion 挪进 try（对齐 judge.py）：

```python
try:
    regen_dur = float(regen.get("duration_sec") or 0.0)
    if regen_dur <= 0.0:
        regen_dur = h3s.probe_duration_sec(regen_path)
    payload = score_shot(model, processor, device, work_dir,
                         src_video, shot, regen_path, regen_dur, keys[sid])
except Exception as exc:
    ...
```

**Outcome (fix):** FIXED — 采纳建议原样：coercion + probe 三行挪进 `try:`（与 judge.py L764-767 逐行对齐，两模块不再漂移）；坏 `duration_sec`（如 `"6,73"`）→ ValueError 落 per-shot except → 打印异常 + `failed` 名单 + continue，批继续。回归锚：`test_bad_duration_sec_single_shot_fail_not_batch`（2 镜中 shot 1 duration_sec="6,73" → rc=0、shot 2 照常打分、shot 1 进 failed 名单且其坏条目被写侧 schema-invalid 层按既有 WR-04 语义剔除）。

### WR-04: 预存条目「形状不对」（非 dict / shot_id 非 int）在 merge 中被静默丢弃 —— 无 warning 无备份

**File:** `analysis/roundtrip/scorer.py:343-345`、`analysis/roundtrip/judge.py:346-348`（两处 merged 构建循环）
**Issue:** 既有 sidecar 里 `isinstance(s, dict) and isinstance(s.get("shot_id"), int)` 不成立的条目被直接跳过，最终 payload 不含它——即被**静默删除**。schema-invalid 的条目走 WR-04 路径有 str warning + `.bak-<ts>` 备份，而形状不对的条目（如 hand-edit 把 shot_id 写成字符串 `"3"`，其中可能带 human verdict）既无告警也无备份地消失。顶层同理：sidecar 顶层未知 key 在重建 payload 时（L331-332/L335-336 只保留 schema_version+shots）被静默丢弃。（该形状 mirror 自 Phase 20 的 h3_regen，但本 phase 复制了它，一并在本文件内修。）
**Fix:** merge 循环对被跳过的条目记 str warning，让操作者知道有数据未随迁：

```python
for s in existing["shots"]:
    if isinstance(s, dict) and isinstance(s.get("shot_id"), int):
        merged[int(s["shot_id"])] = s
    else:
        warnings.append(f"{STEP_TAG} roundtrip.json 预存条目形状非法"
                        f"（非 dict 或 shot_id 非整数），本次写入已丢弃: "
                        f"{str(s)[:120]}")
```

**Outcome (fix):** FIXED（含 .bak 补强）——两份 merge-writer（scorer `write_scores_sidecar` / judge `_merge_write_sidecar`）的 merged 构建循环补 else 分支收集 malformed 条目；驱逐前 `shutil.copy2` 备份原文件到 `roundtrip.json.bak-<ts>` 并逐条发 str warning（含条目内容截断 120 字 + 备份文件名）——与既有 schema-invalid 层完全同款的两层语义（warning + .bak），比 Fix 建议多补了备份（fix_contract 指明 mirror h3_regen WR-04 两层语义）。两函数 docstring 同步。顶层未知 key 丢弃未加告警（每次写入都会触发、噪音大于价值，维持 Fix 建议范围）。回归锚：两模块各 `test_preexisting_malformed_entry_warned_with_backup`（shot_id 字符串 "5" + human verdict → 剔除 + warning + .bak 恰一份 + 本批照常落盘）。

### WR-05: `regen_dur <= 0`（probe 失败返 0.0）无守卫 —— 退化为全 t=0 帧的静默垃圾打分/判定

**File:** `analysis/roundtrip/scorer.py:536-538`、`analysis/roundtrip/judge.py:765-767`
**Issue:** `h3s.probe_duration_sec` 文档明确「失败返回 0.0」。regen mp4 损坏到 ffprobe 失败但 ffmpeg 在 t=0 仍能抽帧时（截断但头有效的 mp4），`plan_frames(0.0)`/`grid_ts(0.0)` 全部时位 clamp 到 0 —— scorer 对 8 张相同帧打分、judge 对 4 行相同 REGEN 帧做归因（多半产出 `model_diverged`），无任何告警地污染分数面与数据集。`dur < ENDPOINT_GUARD_SEC` 的极短流同样全坍缩（scorer 侧窗位全贴 0，含被 condition 的首帧）。
**Fix:** probe 后仍 ≤0（或 < guard）即跳过该镜 + str warning，不给它产出数字：

```python
if regen_dur <= 0.0:
    regen_dur = h3s.probe_duration_sec(regen_path)
if regen_dur <= ENDPOINT_GUARD_SEC:
    pending_warnings.append(
        f"{STEP_TAG} shot {sid}: regen 时长不可测/过短（{regen_dur}），跳过打分")
    failed.append(sid)
    continue
```

**Outcome (fix):** FIXED — 采纳建议原样：两模块（scorer 打分循环 / judge 判定循环）在 probe 后加 `if regen_dur <= ENDPOINT_GUARD_SEC:` 守卫 → str warning（含实测时长值）+ `failed.append(sid)` + continue，不提取帧、不产分数/归因。scorer 侧守卫位于 WR-03 挪入的 per-shot try 内（judge 侧本就在 try 内）。阈值为 ENDPOINT_GUARD_SEC（0.2s）——该值以下 plan_frames/grid_ts 的全部窗位都坍缩到 t≈0，与「dur < guard 的极短流同样全坍缩」的 Issue 描述一致。回归锚：`test_regen_duration_unmeasurable_or_short_skips`（scorer：probe→0.0 与 0.15s 双形态 → 零帧提取零 cache 零 scores + 双 warning）、`test_judge_regen_duration_unmeasurable_skips`（judge：零归因调用 + 引擎编排照常 + warning）。

## Info

### IN-01: `QwenEye()` 构造在 try/finally 之外 —— 构造器异常绕过 graceful-degrade

**File:** `analysis/roundtrip/judge.py:739`
**Issue:** `engine = QwenEye()` 在 `try:` 之外。构造器抛异常（配置缺失/文件损坏）会以 traceback 炸批（rc≠0），「引擎不可用 → rc=0 degrade」语义到不了。测试只覆盖了 all-cache-hit 不实例化的路径，未覆盖构造失败。
**Fix:** 构造挪进 try（或单独 try/except 转 str warning + return 0）。

### IN-02: 测试死代码 —— 未使用的 helper 与 import

**File:** `tests/test_judge.py:214-225`、`tests/test_judge.py:28`
**Issue:** `judge_scores_entry` 与 `sim_scores_entry` 定义后从未被调用；`sim_scores_entry` 内 `jm.ENGINE_NAME and "siglip-so400m-patch14-384"` 是无意义死表达式（恒取后者）；`import os` 未使用。删除以免误导后续用例复制。

### IN-03: `--tau-sim` 无取值校验 —— NaN/越界静默全拒

**File:** `analysis/roundtrip/judge.py:640-653`、`analysis/roundtrip/judge.py:482`
**Issue:** `type=float` 接受 `nan`/`-1`/`2`。τ=NaN 时所有 `sim >= tau` 为 False → 全部 rejected 且无任何提示；τ 已冻结 verdict 不可逆（rejected 永不删除），坏 τ 一次就是 19 镜级事故。建议 `if not (0.0 <= args.tau_sim <= 1.0): sys.exit(...)`。

### IN-04: `--summarize` 行装配未排除 bool（与 apply_verdict/summarize_scores 的守卫不一致）

**File:** `analysis/roundtrip/judge.py:675-676`、`analysis/roundtrip/judge.py:567-569`
**Issue:** `isinstance(sim_obj.get("score"), (int, float))` 不排 bool（`True` 会打印成 `1.0000`）；同文件 `apply_verdict`（L477）与 `summarize_scores._is_num`（L523）都显式排了。只影响只读打印面，但对齐成本一行。

### IN-05: scorer/judge 两份 ~90 行 merge-writer 及 5 个小 helper 整段复制 —— 漂移已发生

**File:** `analysis/roundtrip/scorer.py:312-399` vs `analysis/roundtrip/judge.py:317-401`；另 `_stderr_snip`/`extract_frame`/`regen_sha16`/`parse_shots_subset`/`_read_sidecar_shots` 双份
**Issue:** 两段 merge-writer 除 verdict 冻结 pop 外逐行相同，却各自维护——WR-03 的不一致（try 边界）正是这种复制的实证漂移。repo 自述原则是「单源不漂移（h3s 共享件）」，这两份彼此复制违背同一原则。建议把 merge 骨架下沉进 h3s（参数化 verdict-freeze 开关），小 helper 至少 `regen_sha16`/`parse_shots_subset` 收敛到 h3s。

### IN-06: scorer cache key 不含 device/dtype —— fp16-cuda 与 fp32-cpu 分数跨设备混源复用

**File:** `analysis/roundtrip/scorer.py:108-109`
**Issue:** cuda 路径 fp16、cpu fallback float32，两者余弦在 1e-3 量级有差；τ=0.9670 是按 GPU0 fp16 分数校准的，降级 cpu 重跑后 cache 可跨设备命中复用。payload 存了 `device` 供审计（可查证），但 key 不区分——若在意校准一致性，把 device（或 dtype）并入 key，或在 schema/SPEC 注明「分数以首次打分设备为准」。

---

_Reviewed: 2026-08-20T02:47:19Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
