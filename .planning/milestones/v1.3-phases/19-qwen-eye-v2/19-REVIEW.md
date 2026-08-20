---
phase: 19-qwen-eye-v2
reviewed: 2026-08-19T18:38:14Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - analysis/engine_clients/qwen_eye_client.py
  - analysis/vision_seq_facets.py
  - run_pipeline.py
  - spike/vision_seq/build_sandbox.py
  - spike/vision_seq/run_spike.py
  - tests/test_qwen_eye_client.py
  - tests/test_vision_seq_facets.py
  - tests/test_pipeline_vision_seq_wiring.py
findings:
  critical: 1
  warning: 4
  info: 7
  total: 12
status: clean
fixed_at: 2026-08-19T18:52:08Z
fix_scope: critical_warning
fix_report: 19-REVIEW-FIX.md
re_reviewed: 2026-08-19T18:58:22Z
re_review_iteration: 2
re_review_mode: "--auto re-review after fixes (0caae2a..0523483)"
re_review_files:
  - analysis/vision_seq_facets.py
  - analysis/engine_clients/qwen_eye_client.py
  - run_pipeline.py
re_review_findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
re_review_gates:
  pytest: "73 passed"
  spec_validate: "exit 0"
---

# Phase 19: Code Review Report

**Reviewed:** 2026-08-19T18:38:14Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** clean（re-review iteration 2 —— CR-01 + WR-01..04 五项修复全部验证通过，无新 Critical/Warning；门禁绿。原始 12 项发现及修复产出保留下方）

## Summary

Reviewed the qwen-eye v2 frame-sequence facet module, the copied engine client, the run_pipeline 5.6 wiring, both spike drivers, and the three test files. Cross-checked claims against `spec/schemas/prompts.schema.json`, `analysis/local_vision_facets.py` (v1 mirror), and `analysis/call_shot_analysis.py` (hash mirror). Two findings were verified empirically (executed the module / sampling function against synthetic and live `shots.json` data), not just by reading.

Overall architecture is solid: cache envelope isolation, never-overwrite semantics, schema self-validation before atomic write, and the zero-modification short-circuit all check out and are well tested. However, **the frame-window lower bound has an off-by-one that fires on ~78–96% of real shots** (verified against three live `output/*/shots.json` files), pulling pre-shot (previous-shot) frames into action and camera evidence — this is the default pipeline path, so it is a blocker. Separately, the cache key omits the sampling/window dimension and the merge reads unbounded cached keys — a provable stale-merge repro. Engine lifecycle has a leak path after a partially-successful start, and the ear cache dimension is boolean-only so audio-content changes never invalidate.

## Re-review (iteration 2 — post-fix verification, 2026-08-19T18:58:22Z)

**Scope:** 3 files after fix commits `0caae2a..0523483`（CR-01 → 9209d75 → 72e1878 → a97ae2c → 0523483）。
**Gates run by reviewer:** `python3 -m pytest tests/ -q` → **73 passed**；`python3 spec/validate.py` → **exit 0**。
**Outcome: clean** —— 5/5 修复验证正确，无新 Critical/Warning。2 项 Info 级残留观察（IN-08/09，不阻塞）。

### Fix verification detail

| Fix | Commit | Verdict | Evidence |
|---|---|---|---|
| CR-01 ceil + PROMPT_VERSION v2 | 0caae2a | **correct** | `lo = math.ceil(start_sec*fps)+1`（vision_seq_facets.py:194）与 t=(N-1)/fps 推导一致；`hi` 保持 floor（inclusive-safe 侧）正确。对 269 条 live shots（3 个 output/*/shots.json）：0 例下界欠收紧（首采帧 t < start 污染方向）、26 例网格对齐边界 0 例 ceil 浮点过冲（常见 1 位小数 ×5 在 IEEE double 下恰好落在整数上）。`PROMPT_VERSION = "vision-seq-v2"`（:105）。**cache-miss 设计实测成立**：构造 v1 旧信封（v1 key、无 window、无 ear_ctx_fp、含旧 answers/merged_B）→ `_load_cache_envelope` 干净 miss（返回带 window+ear_ctx_fp 的全新空信封，无异常），盘上 sibling ear 信封原样保留；中间态信封（v2 key + window、无 ear_ctx_fp，9209d75↔0523483 间写出）ear_off 命中（采样语义完全一致，正确）、ear_on miss（安全方向重烧）。 |
| WR-01 window 契约 + 合并限界 + merged_B 失效 + 空答 warning | 9209d75 | **correct** | window {start_sec,end_sec,fps,n_frames,needed{action,camera}}（:588-591）随信封持久化并在 load（:278-279）/save（:308-310）双侧匹配；`_facet_answer_values` 以 `idx > needed` 限界（:406-407）——实测 needed=6 时盘上残留 action_frame_7/8 不进合并；merged_B 失效双路径（落盘 :315-326 实测 pop / 内存 :653-657）；空答显式 warning（:684-691，`missing` 为空时 empty_cnt 恰为清答数，语义正确）。 |
| WR-02 --frame-fps 直通 + 契约维 + fail-loud | 72e1878 | **correct** | run_pipeline.py:859-862 在 5.6 cmd 构造内传 `--frame-fps str(args.sample_fps)`（静态接线锁 test_pipeline_vision_seq_wiring.py idx_ffps 断言）；子模块 flag 默认 5.0（:514-517）+ `fps<=0` sys.exit fail-loud（:520-521）+ fps 进 window 契约（:589）。str(float) repr 往返精确，跨运行 float 相等成立。 |
| WR-03 _owned 语义 + KAP release 配对 | a97ae2c | **correct** | `_owned=True` 在实际发起 start 后、health 轮询前置位（qwen_eye_client.py:229）——超时 (False,True) 与 Guard-2 load 失败路径均被 stop_if_owned 覆盖；预存在健康 server（(True,False)）与 VRAM 不足未发起 start（(False,False)）均不动。**release 只在授予时发**：`_lease_granted` 仅当 status==200 且 body.data.granted is True（:206-212），stop_if_owned 在 `_lease_granted` 门内 POST release（:262-269），payload mirror caller，幂等不重复。调用方 try/finally（vision_seq_facets.py:634-668）不受影响，stop_if_owned never-raises（subprocess/_http_json 双层吞异常）。3 个回归测试断言到位（超时 owned+stop、Guard-2 owned+stop、granted→release 恰一次+幂等）。 |
| WR-04 ear_ctx_fp 指纹 | 0523483 | **correct** | `_audio_ctx_fp`=sha256(audio_ctx)[:8]（:246-251）；预判阶段一次算好存 work item（:595-597），提问复用同一字符串（:649-650）——**指纹与提问文本同源**，不变式闭合；信封持久化 + load（:280-281）/save（:310）匹配；ear_off 恒 ""（与旧缺省兼容）。实测：ear 开、对白内容改写 → miss 重烧。ear 开而该镜无音频上下文 → fp=sha256("")[:8] 常量，内容出现即变 → miss，方向正确。 |

### Re-review Info（残留观察，不阻塞 clean）

### IN-08: window 契约未锁定采样帧的物理帧号 —— frames 目录内容漂移可静默重映射索引→图像

**File:** `analysis/vision_seq_facets.py:588-591, 196-205`
**Issue:** WR-01 契约锁定 {start,end,fps,n_frames,needed}，但均匀下采样索引 `round(i*(len(window)-1)/(max_frames-1))` 还依赖**降采样前的窗内帧数** `len(window)`，该值不在契约中。若 frames 目录内容变化（窗中删/增一帧）而窗内计数仍 >8，n_frames 仍为 8、契约全匹配 → 命中旧信封，但 action_frame_N 索引指向的物理图像已漂移。触发条件苛刻（frames 目录是 detect 步一次性产物；需不动 shots.json/video 的目录级篡改或部分抽取），且 video_content_hash 不覆盖 frames 目录。非本次修复引入的回归 —— 是 WR-01 修复收窄后仍存的边缘。
**Fix:** window 契约另存实际采样帧号列表（或其 sha256[:8]），load 匹配时比对 —— 帧身份而非帧数。

### IN-09: `--frame-fps nan/inf` 绕过 `<= 0` 门（仍 fail-loud，但是裸 traceback）

**File:** `analysis/vision_seq_facets.py:520-521`
**Issue:** `float('nan') <= 0` 为 False → NaN 通过门禁，随后 `math.ceil(start*nan)` raise ValueError（inf 同理 OverflowError）——依然是响亮失败、无静默污染，只是丢掉了干净的 sys.exit 提示。仅 CLI 调用者自伤面，无攻击面。
**Fix:** `if not (args.frame_fps > 0) or not math.isfinite(args.frame_fps): sys.exit(...)`（`not (x > 0)` 形式同时捕获 NaN）。

## Critical Issues

### CR-01: `select_uniform_frames` lower bound off-by-one — pre-shot frame sampled for ~78–96% of real shots

**File:** `analysis/vision_seq_facets.py:175`
**Issue:** `lo = int(start_sec * FRAME_SAMPLING_FPS) + 1` uses `int()` (floor), but the docstring specifies "首个 ≥ start 的帧号". Frame N has timestamp `(N-1)/fps`, so the first frame with `t >= start_sec` is `N = ceil(start_sec*fps) + 1`. When `start_sec*fps` is non-integer, `lo` is one frame too low, including a frame up to 0.2s **before** the shot start — i.e., typically the last frame of the *previous* shot (hard cut).

Verified empirically:
- `select_uniform_frames(dir, 0.5, 2.5)` picks frame 3 (`t=0.4 < 0.5`); correct first pick is frame 4.
- Live data: `output/《小江湖》第03话…/shots.json` — 74/76 shots; ep01 — 73/93; ep02 — 96/100 have `start_sec*5` non-integer. This is the common case, not an edge.

Consequences on the default path for most shots:
1. `action` facet: first temporal segment describes previous-shot content, merged into this shot's action chain (`temporal` join).
2. `camera` facet: `camera_pair_1` = `observe_pair(prev_shot_last_frame, first_in_shot_frame)` — the model is asked "相对第1帧，第2帧的镜头怎么运动了" *across a scene cut*, producing a cut-misread-as-camera-movement answer that leads the merged camera facet.
3. Because facets are never overwritten once filled, the wrong values persist across runs.

Note `hi` (line 176) is correct (floor errs on the inclusive-safe side); only `lo` is wrong.
**Fix:**
```python
import math
lo = math.ceil(start_sec * FRAME_SAMPLING_FPS) + 1   # 首个 t=(N-1)/fps >= start 的帧号
```
`math.ceil` is a no-op for grid-aligned boundaries (integer `start*fps` behaves identically to today). Because the RAW cache keys (`action_frame_N`) are frame-index based, the fix changes *which image* each index maps to — bump `PROMPT_VERSION` (e.g., `vision-seq-v1b`) in the same change so existing caches don't serve answers burned against the shifted window, and add a regression test with a fractional window (e.g., `[0.5, 2.5]` must start at frame 4).

**Outcome (fix pass 2026-08-19 UTC):** fixed @ 0caae2a — `lo = math.ceil(start_sec*fps)+1` + `PROMPT_VERSION` bump `vision-seq-v1`→`vision-seq-v2` + 回归测试（[0.5,2.5] 首帧=4、网格对齐边界行为不变）。v1 镜像 `analysis/local_vision_facets.py:126` 同 floor 惯例 —— v1 红线零改动，本 phase 不修，记 deferred（见 19-REVIEW-FIX.md）。
**Re-review (iter 2):** verified correct — 269 live shots 0 欠收紧/0 ceil 过冲；旧 v1 信封干净 miss（详见 Re-review 表）。

## Warnings

### WR-01: Cache key omits the sampling/window dimension; merge consumes unbounded stale keys and `merged_B` is never invalidated on RAW change

**File:** `analysis/vision_seq_facets.py:210-219, 337-353, 587-604`
**Issue:** `_cache_key` = {video_content_hash, engine_name, engine_version, prompt_version, ear}. It does not cover the shot time window or frame count. `_facet_answer_values()` returns **all** non-empty `action_frame_*` / `camera_pair_*` keys sorted by index, without bounding to the current `_needed_count`. If `shots.json` is regenerated (e.g., operator deletes it to re-detect, or detection params change) while `route_cache/vision_seq/` survives — `--force` nukes the cache, but plain re-detection does not — then:

- envelope keys from the old denser window satisfy `missing` checks (key presence is the only test), and
- step 6 merges **extra stale answers beyond the current window** into the facet.

Proven by execution: seeded a cache with `action_frame_1..8`, ran with a 6-frame window → `missing` empty, output facet = `旧答1→…→旧答8` (frames 7–8 outside the current window included). Additionally, `_save_cache_envelope(new_answers=...)` (line 273-275) updates `answers` but leaves `merged_B` untouched, so under `--merge-strategy llm` a re-burn produces RAW evidence that `merged_B` no longer reflects, and `_merge_llm_pass` short-circuits on the stale `merged_B` ("已缓存 —— 零 GPU").

Also note: an engine answer that `_clean_answer` reduces to `""` is cached as `""`, permanently counts as "answered" (never re-asked), and is silently dropped from the merge — partial evidence merges without any warning.
**Fix:** Persist the sampling contract inside the envelope (e.g., `"window": {"start_sec", "end_sec", "fps", "n_frames", "needed": {"action": N, "camera": M}}`) and treat it as part of the key match in `_load_cache_envelope`; bound `_facet_answer_values` to the current needed indices in step 6; delete `env["merged_B"][facet]` whenever new RAW answers are written for that facet; optionally warn when a non-zero share of needed answers is empty.

**Outcome (fix pass 2026-08-19 UTC):** fixed @ 9209d75 — window 契约（start/end/fps/n_frames/needed）随信封持久化并参与 load/save 匹配；合并限界当前 needed 索引；merged_B 随新 RAW 答案失效（落盘 + 内存双路径）；空答占比显式 [vision-seq] warning。4 个回归测试。
**Re-review (iter 2):** verified correct（含残留边缘 IN-08 —— 契约锁帧数不锁帧号，Info 级不阻塞）。

### WR-02: `FRAME_SAMPLING_FPS` hardcoded 5.0 while `run_pipeline --sample-fps` is configurable — wrong windows at any non-default fps

**File:** `analysis/vision_seq_facets.py:99, 161-176`; `run_pipeline.py:706-707, 793-794`
**Issue:** `run_pipeline.py` exposes `--sample-fps` (default 5.0) and passes it to `detect_v3b`, which writes `frames_5fps/` at that rate. `vision_seq_facets.py` hardcodes `FRAME_SAMPLING_FPS = 5.0` and receives no fps argument. At `--sample-fps 10`, a shot `[10, 20]` maps to computed frame numbers 51..101, which on the 10fps grid are `t=5.0..10.0` — the module questions frames from the **wrong half of the shot**, silently. No warning is produced; facets are filled from misaligned evidence. (The v1 5.5 module shares the assumption, but this phase's code hardcodes it anew.)
**Fix:** Thread the actual rate through: `run_pipeline` adds `--frame-fps`, `str(args.sample_fps)` to `cmd_vseq`, and `vision_seq_facets` takes `--frame-fps` (default 5.0) used by `select_uniform_frames`. Alternatively have `detect_v3b` write a `frames_5fps/fps.json` sidecar that consumers read.

**Outcome (fix pass 2026-08-19 UTC):** fixed @ 72e1878 — 直通方案落地：`--frame-fps` flag + `run_pipeline` 传 `str(args.sample_fps)` + fps 进 window 契约（fps 变 → cache 必 miss）+ fps<=0 fail-loud + 单测/静态接线锁。残留缺口（deferred）：frames 目录按旧 `--sample-fps` 抽出而 shots.json 命中缓存时，直通值仍反映新 flag —— 完整修法是 detect_v3b 写 fps sidecar（需碰 validated 基线模块，见 19-REVIEW-FIX.md）。
**Re-review (iter 2):** verified correct（nan/inf 微残留见 IN-09，Info 级不阻塞）。

### WR-03: Engine lifecycle leak — failed start returns `(False, True)` but `_owned` stays False; KAP allocate has no release counterpart

**File:** `analysis/engine_clients/qwen_eye_client.py:207-218, 220-234`
**Issue:** `_owned` is set True only on the health-OK path (line 210). The fallback-script/KAP-allocate start attempts that fail to reach health within the deadline return `(False, True)` (lines 216, 218) — the tuple contract per the docstring says "started_by_us=True → 用完即停适用于自己拉起的" — yet `stop_if_owned()` is a no-op because `_owned` is False. A slow-loading server that misses the 120s deadline keeps loading after the caller exits, eventually holding 13.4GB VRAM with nobody managing it, and the KAP lease granted at allocate (`POST :10588/api/production/llm/allocate`) is never released — the file contains no release call; the only teardown is `kap-llm.sh stop`, which is gated on `_owned`. `vision_seq_facets.main()` correctly relies on `stop_if_owned()` in `finally`, so it inherits this hole. (The header claims line-for-line equivalence with upstream `qwen_eye.py` @c3949404, so this is likely inherited — but it is new code in this repo and the phase brief explicitly asks for lifecycle leak paths.)
**Fix:** Set `self._owned = True` before the health-polling loop starts whenever the allocate or fallback-script path actually issued a start (i.e., track "we attempted a start" separately from "we observed healthy"), so `stop_if_owned()` stops the half-started server; and pair the KAP allocate success with a release call (or document that `kap-llm.sh stop` releases the lease server-side, with a comment pointing at the evidence).

**Outcome (fix pass 2026-08-19 UTC):** fixed @ a97ae2c — start 发起（allocate 成功或 fallback 脚本已跑）即 `_owned=True`，慢启动超时 / Guard-2 load 失败的 (False, True) 路径同样被 stop_if_owned 覆盖；KAP lease 配对释放已落地：allocate 授予过才 `POST :10588/api/production/llm/release`（mirror caller；路由证据 kais-aigc-platform `src/routes/production/llm/index.ts:135-147`；已核验 kap-llm.sh stop 仅 pkill、不触碰 lease —— 脚本内无任何 release 调用）。3 个回归测试。
**Re-review (iter 2):** verified correct — release 仅在 granted 时发、stop 路径 try/finally 安全、幂等（详见 Re-review 表）。

### WR-04: ear cache dimension is boolean — audio_semantic.json content changes never invalidate the ear_on envelope

**File:** `analysis/vision_seq_facets.py:210-219, 319-324`
**Issue:** The ear question content depends on `audio_semantic.json` *content* (dialogue.text/emotion, sfx.events/description via `build_audio_context`), but the cache key records only `ear: bool`. If step 7 re-runs with changed route output (route cache version bump in `call_audio_analysis`, or the file regenerated after a route fix), the questions change while the key does not — stale RAW answers burned against the old audio context are served for the new questions. Unlike prompts, there is no manual knob (`PROMPT_VERSION` covers only ACTION/CAMERA text; bumping it to force ear re-burn also discards ear_off evidence).
**Fix:** When `ear` is on, fold a cheap content fingerprint of the per-shot audio context into the key or envelope (e.g., `sha256(audio_ctx)[:8]` stored per shot alongside the answers, treated as part of the key match).

**Outcome (fix pass 2026-08-19 UTC):** fixed @ 0523483 — `ear_ctx_fp`（sha256(audio_ctx)[:8]）随 ear_on 信封持久化并参与 load/save 匹配；audio_ctx 在预判阶段一次算好存 work item 复用。回归测试：对白内容改写（ear 开关不变）→ miss 重烧 + 新提问串含新对白。
**Re-review (iter 2):** verified correct — 指纹与提问文本同源（同一 audio_ctx 字符串），不变式闭合（详见 Re-review 表）。

## Info

### IN-01: No length cap on engine answers flowing into prompts.json

**File:** `analysis/vision_seq_facets.py:189-192, 601-604`
**Issue:** `_clean_answer` strips whitespace/quotes/trailing punctuation only. Each call allows `max_tokens=2000`, and `temporal` joins up to 8 answers, so a verbose or runaway engine output becomes a multi-KB facet string. `prompts.schema.json` sets no `maxLength` on `action`/`camera`, so schema validation will not catch it; the bloat propagates into `prompt_text` via attach_refs and downstream prompts.
**Fix:** Add a sanity cap in `_clean_answer` or before write (e.g., truncate facet at ~500 chars with a `[vision-seq]` warning), and consider `maxLength` in the schema.

### IN-02: Injection surface note (proportionate)

**File:** `analysis/vision_seq_facets.py:113-131, 319-324`; `analysis/engine_clients/qwen_eye_client.py:285-314`
**Issue:** Model-generated text flows through two interpolation points: (1) `audio_semantic` dialogue/sfx text (route/whisper output — itself model-generated from audio) is interpolated into the VL question via `_ear_question`; (2) VL answers (derived from video pixels — text visible in frames can be transcribed into facets) flow into `prompts.json`, which attach_refs recomposes into `prompt_text` for downstream LLM consumption. There is no code-execution/XSS surface here (pure JSON with `ensure_ascii=False`; the spike markdown tables escape `|` and newlines via `_md_escape_cell`), so this is a prompt-injection trust-chain consideration only. The ear whitelist (no words/spk_id/reproduction) is a good pattern.
**Fix:** No structural change required for v2; keep the whitelist discipline, and treat facet text as untrusted when it crosses into downstream prompt composition (document it in the module docstring's 边界 section).

### IN-03: v1 and v2 share the KAP caller identity `kst:vision_facets`

**File:** `analysis/engine_clients/qwen_eye_client.py:68, 96`; `analysis/vision_seq_facets.py:551`
**Issue:** `vision_seq_facets.main()` instantiates `QwenEye()` with the default `CALLER = "kst:vision_facets"`, identical to v1 `local_vision_facets.py:228`. KAP lease attribution cannot distinguish the 5.5 and 5.6 steps in scheduler logs.
**Fix:** `engine = QwenEye(caller="kst:vision_seq")`.

### IN-04: `PROMPT_VERSION` knob documentation omits `MERGE_B_PROMPT`

**File:** `analysis/vision_seq_facets.py:92-95, 127-131`
**Issue:** The comment says bump `PROMPT_VERSION` when `ACTION_PROMPT`/`CAMERA_PAIR_PROMPT` change, but `merged_B` is cached per facet without its own versioning — changing only `MERGE_B_PROMPT` without a bump serves stale `merged_B` under `--merge-strategy llm`.
**Fix:** Extend the comment to name all three prompt constants (or version `merged_B` separately).

### IN-05: Docstring overstates ear re-burn behavior in the pipeline

**File:** `analysis/vision_seq_facets.py:34-36`; `run_pipeline.py:843-847`
**Issue:** Both claim that after `audio_semantic.json` lands, the second pipeline run activates ear and "重烧一次". In practice the first run already filled the facets, and never-overwrite semantics mean filled facets are **never** re-burned — only facets that were still empty (degraded) get the ear treatment. Obtaining ear evidence for already-filled shots requires manually clearing facets.
**Fix:** Reword to "ear 仅影响当时仍空缺的 facet；已填 facet 永不重烧，需 ear 证据须手动清空".

### IN-06: warnings sidecar written non-atomically

**File:** `analysis/vision_seq_facets.py:626-630`
**Issue:** The sidecar is written with a plain `open(w)` while every other JSON write in the module uses tmp + `os.replace`. A crash mid-write corrupts `route_cache/warnings.json`, which is shared with other steps; `_read_existing_warnings` tolerates corruption by returning `[]`, silently discarding sibling steps' warnings that export_asset reads. (Mirrors the v1 module / call_reid pattern — codebase-wide, not phase-specific.)
**Fix:** Use the same tmp + `os.replace` dance for the sidecar.

### IN-07: Spike self-check false-positive risk if live data gains empty facets

**File:** `spike/vision_seq/build_sandbox.py:162-170`
**Issue:** `_self_check` infers "blanked" shots by `not action and not camera` over the *whole* written file. Any live shot outside `blank_ids` that already has both facets empty (ep01 today has 0/93, so it works) makes the check `sys.exit` spuriously. Also `--reset` mode still requires `transcript.json` to exist (loaded unconditionally in `main()` before mode dispatch). Throwaway spike code — acceptable, noting for reuse.
**Fix:** Compare against the pre-blank live values per shot_id instead of the global both-empty heuristic; skip transcript load when `reset_only`.

### IN-08 / IN-09: re-review iteration 2 残留观察

见上方 Re-review 章节内的 IN-08（window 契约锁帧数不锁物理帧号）与 IN-09（`--frame-fps nan/inf` 绕过 `<= 0` 门，仍 fail-loud）。均为 Info 级，不阻塞。

---

_Reviewed: 2026-08-19T18:38:14Z_
_Re-reviewed: 2026-08-19T18:58:22Z (iteration 2, post-fix 0caae2a..0523483 — clean)_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
