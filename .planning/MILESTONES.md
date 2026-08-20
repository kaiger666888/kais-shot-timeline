# Milestones

## v1.3 Round-trip Validation（逆推→复现→比对闭环数据集） (Shipped: 2026-08-20)

**Phases completed:** 5 phases, 16 plans, 39 tasks

**Key accomplishments:**

- One-liner:
- One-liner:
- One-liner:
- qwen_eye_client 加 observe_pair（两条 user 各一图规避 llama.cpp 多图丢弃 bug）/ask_text（纯文本合并）入口；新建 vision_seq_facets.py v2 模块（均匀 ≤8 帧采样 + action 逐帧问 + camera 相邻对问 + ear 白名单注入 + 双信封 RAW cache + 三策略合并 + 只填空缺 + 预判生命周期 + 零修改短路），22 个新离线单测全套 58 passed，v1 文件零字节改动
- One-liner:
- run_pipeline 挂载无编号 pre-step 5.6（--vision-seq/--no-vision-seq/--no-ear 三 flag，5.5 后 step_reid 前，banner plain-label 不 bump step counter）+ wiring 四件套机器锁（62 tests 零回归）；SC1/SC4 wiring 形态收口：sandbox 六镜默认策略 temporal 填充 diff 可见、live sha256 前后等值负测试、cache 命中 0.968s/0.939s 秒级零引擎重跑，全部落 sc1_evidence.txt + 报告新节
- ComfyUI 直连 fl2va 复现客户端核心链路：13 节点 workflow 模板 deepcopy 注入 + 提交/轮询/view 下载 + per-shot 4-tuple cache 断点续跑 + warnings 双形 merge，15 个全离线单测零真引擎
- batch_start_guard 五步固定序（TTS 端口→PID 定向 SIGTERM + 审计 / eye 13.7GB 串行等待 / 双 /free / 22GB 严格 gate）+ per-shot PID 归因防自锁 + 均匀抽样/超时跳过/分辨率降载三 CLI，12 个全离线单测（fake nvidia-smi/ss/os.kill），全套 100 passed 零真机
- roundtrip.json regen 半边写入（READ-merge + schema 写前自校验 + 单源版本）+ ep01 真 ComfyUI smoke 双镜真提交真回收 10.5min + 同命令重跑全 cache-hit 零新提交 + 渲后水位实测——Task 3 目视抽检 checkpoint 待 Kai
- SigLIP 中段帧轨迹相似度打分器 + qwen-eye 三分类归因 judge + --apply-verdict 硬合取冻结应用器，全离线 FakeSigLIP/FakeEye 替身 38 用例零 GPU 验证（157 passed 零回归）
- 2 镜 896×512 真 GPU 双信号（SigLIP scorer @GPU0 + qwen-eye judge @GPU1，模块零 bug 零修复 + 157 pytest 零回归）+ uniform-19 @1344×768 overnight 批 nohup 运行中（guard 过线、shot 1 已回收、pidfile/日志交接就位）
- 19 镜 @1344×768 双信号全量烧录 + 校准报告 DRAFT（分位数/三桶/τ 预演/per-position）——暂停于 Task 2 blocking checkpoint：τ_sim 裁决 + 抽检 5 镜归因待 Kai（机器不代裁，SCORE-03 HITL 硬门）
- round-trip HITL 审阅面板生成器（双 video 并排 + 三态覆盖 + exportEdits）落地，XSS 三层 hardening 以 19 个注入/六态/形状断言 + mutation 探针锁定为机器证明而非宣称。
- PRESENT-01 回写半边 + RT-05/DATASET-02 模块半边落地：roundtrip-edits schema（confirmed-only 硬门的一半）+ apply CLI（human 覆盖唯一冻结替换路径、重放 byte-idempotent）+ accepted 子集独立 dataset 导出（消费端零契约依赖，25 个新用例 + ep01 只读双演示全绿）。
- PIPE-01 落地：step_roundtrip 成为编号 step [9/10]（timeline 与 export 之间）——外层 mtime+video-stamp cache 短路 + 四 subprocess 串（judge --tau-sim 总是显式）+ 六 flag 全透传（τ_sim=0.9670 进默认）+ banner [N/10] 重编号零存活 + Pattern 4 条件挂载修补 + dataset post-step，220 pytest 零回归。
- Status:

---

## v1.2 v1.2 (Shipped: 2026-07-26)

**Phases completed:** 8 phases, 20 plans, 39 tasks

**Key accomplishments:**

- `common.py` (260 lines)
- Express stub route mounted at `/api/production/audio-analysis` in kais-aigc-platform with byte-identical envelope shape to shot-analysis — Phase 12 producer client has a POST target before any ML lands. Full curl round-trip proven (code:200 + stub_mode:true on happy path; code:400 on validation failure).
- funasr 1.3.29 install (Pitfall 1 clear):
- Package install (panns-inference 0.1.1 + transitive fixes):
- A1 (CPU mode works without CUDA 12.8 toolkit):
- Aggregated 4 Phase 10 spike JSONs (SER/MERT/PANNs-blocked/WhisperX) into a 254-line empirical report + locked 5 PROJECT.md Key Decisions rows resolving BLOCKER 1 (CUDA stay-on-12.4) + 3 CONDITIONAL requirements (DIA-04 ship-nullable / MUS-04 defer-v1.3 / DIA-05 ship-experimental).
- 1. [Rule 1 — Bug] Strict instruments-grep required rewording $comment to avoid the English word "instrument"
- 12-file v1.2 fixture (10 byte-copied from v1.1 + audio_semantic.json with real SenseVoice spike outputs + speakers.json with synthetic spk_NNN turns) wired into a 3-tier shape gate (minimal/v1.1/v1.2 all 0-failure) + verify_contract.py extended with v1.0↔v1.1↔v1.2 bidirectional proof (forward 0 errors, backward 0 non-additive errors) + speakers.char_id ⊆ characters.id consistency check.
- 827-line httpx producer client for POST /api/production/audio-analysis — third sibling of v1.1 route-pattern family, with per-shot 4-tuple cache, poisoned-cache schema-invalidated auto-cleanup, byte-identical-absent graceful-degrade, and non-destructive [audio] warnings sidecar merge; SC#4 stub round-trip proven end-to-end before any ML lands.
- SC#4 doubly proven: Task 1 delivers a deterministic 5-scenario smoke harness (in-process mock stub) proving `call_audio_analysis.py` correctly parses the Phase 10 stub envelope, manages per-shot cache (write/hit/poisoned-invalidate), and merges `[audio]` warnings non-destructively with `[semantic]`/`[reid]` tags. Task 2 supplementary live cross-repo cross-check SUCCEEDED (not deferred): producer client integrated cleanly with the actual `feat/audio-analysis-route` stub host, exit 0, audio_semantic.json absent (CONTRACT-05 byte-identical v1.1), `[audio]` warning with stub_mode:true diagnostic present.
- link_speakers.py confirmed-only apply gate mirroring apply_edits.py (548 lines, byte-identical re-apply) + additive speakers.json block in _producer_registry_integrity (73 new lines, no-op when absent)
- Self-contained monolithic HTML generator (760 lines) mirroring gen_registry_review.py: speaker cards sorted by shot_count desc + character dropdown filtered to confirmed-only (Pitfall 7 upstream gate) + Export-edits → speaker-edits.json (schema-valid) + _esc + JSON-in-script XSS hardening (T-13-01/09 mitigate)
- 1. [Rule 1 — Bug] Scenario 4 poison spec didn't actually exercise `_esc`
- 1. [Rule 1 - Test Bug] TINY_VIDEO has no audio stream → ffprobe fails on e2e
- One-liner:
- One-liner:
- CLI flags
- Cross-repo `@kais/infinite-canvas` consumer recognizes schema_version 1.2 + emits per-shot dialogue/music/sfx type:asset children via §7 buildPhaseTree post-process (gated on KNOWN_VERSIONS.has("1.2")); AssetNode typeIcons 💬🎵🔊 cosmetic; verify_contract 3-mode GREEN (40 assertions, +11 new); MUS-04 instruments absent; v1.1 Phase 9 invariant (no custom renderer / no Zod bump) preserved.

---

## v1.2 v1.2 (Shipped: 2026-07-26)

**Phases completed:** 8 phases, 20 plans, 39 tasks

**Key accomplishments:**

- `common.py` (260 lines)
- Express stub route mounted at `/api/production/audio-analysis` in kais-aigc-platform with byte-identical envelope shape to shot-analysis — Phase 12 producer client has a POST target before any ML lands. Full curl round-trip proven (code:200 + stub_mode:true on happy path; code:400 on validation failure).
- funasr 1.3.29 install (Pitfall 1 clear):
- Package install (panns-inference 0.1.1 + transitive fixes):
- A1 (CPU mode works without CUDA 12.8 toolkit):
- Aggregated 4 Phase 10 spike JSONs (SER/MERT/PANNs-blocked/WhisperX) into a 254-line empirical report + locked 5 PROJECT.md Key Decisions rows resolving BLOCKER 1 (CUDA stay-on-12.4) + 3 CONDITIONAL requirements (DIA-04 ship-nullable / MUS-04 defer-v1.3 / DIA-05 ship-experimental).
- 1. [Rule 1 — Bug] Strict instruments-grep required rewording $comment to avoid the English word "instrument"
- 12-file v1.2 fixture (10 byte-copied from v1.1 + audio_semantic.json with real SenseVoice spike outputs + speakers.json with synthetic spk_NNN turns) wired into a 3-tier shape gate (minimal/v1.1/v1.2 all 0-failure) + verify_contract.py extended with v1.0↔v1.1↔v1.2 bidirectional proof (forward 0 errors, backward 0 non-additive errors) + speakers.char_id ⊆ characters.id consistency check.
- 827-line httpx producer client for POST /api/production/audio-analysis — third sibling of v1.1 route-pattern family, with per-shot 4-tuple cache, poisoned-cache schema-invalidated auto-cleanup, byte-identical-absent graceful-degrade, and non-destructive [audio] warnings sidecar merge; SC#4 stub round-trip proven end-to-end before any ML lands.
- SC#4 doubly proven: Task 1 delivers a deterministic 5-scenario smoke harness (in-process mock stub) proving `call_audio_analysis.py` correctly parses the Phase 10 stub envelope, manages per-shot cache (write/hit/poisoned-invalidate), and merges `[audio]` warnings non-destructively with `[semantic]`/`[reid]` tags. Task 2 supplementary live cross-repo cross-check SUCCEEDED (not deferred): producer client integrated cleanly with the actual `feat/audio-analysis-route` stub host, exit 0, audio_semantic.json absent (CONTRACT-05 byte-identical v1.1), `[audio]` warning with stub_mode:true diagnostic present.
- link_speakers.py confirmed-only apply gate mirroring apply_edits.py (548 lines, byte-identical re-apply) + additive speakers.json block in _producer_registry_integrity (73 new lines, no-op when absent)
- Self-contained monolithic HTML generator (760 lines) mirroring gen_registry_review.py: speaker cards sorted by shot_count desc + character dropdown filtered to confirmed-only (Pitfall 7 upstream gate) + Export-edits → speaker-edits.json (schema-valid) + _esc + JSON-in-script XSS hardening (T-13-01/09 mitigate)
- 1. [Rule 1 — Bug] Scenario 4 poison spec didn't actually exercise `_esc`
- 1. [Rule 1 - Test Bug] TINY_VIDEO has no audio stream → ffprobe fails on e2e
- One-liner:
- One-liner:
- CLI flags
- Cross-repo `@kais/infinite-canvas` consumer recognizes schema_version 1.2 + emits per-shot dialogue/music/sfx type:asset children via §7 buildPhaseTree post-process (gated on KNOWN_VERSIONS.has("1.2")); AssetNode typeIcons 💬🎵🔊 cosmetic; verify_contract 3-mode GREEN (40 assertions, +11 new); MUS-04 instruments absent; v1.1 Phase 9 invariant (no custom renderer / no Zod bump) preserved.

---

## v1.1 分镜语义深化 — 镜头语言 + 跨镜角色/道具注册表 (Shipped: 2026-07-24)

**Phases completed:** 5 phases, 16 plans, 32 tasks

**Key accomplishments:**

- 3 new registry-flavor schemas + 2 additive schema extensions locking the v1.1 ShotTimelineAsset contract — all pure-additive, v1 minimal fixture still validates 6/6 green.
- Producer-side schema_version lock — `SCHEMA_VERSION = \"1.1\"` single-source constant in export_asset.py; PROJECT.md:83 stale `\"2\"` drift corrected to `\"1.1\"`.
- 9-file self-contained v1.1 fixture sample — exercises every new + extended schema with cross-file-consistent IDs; v1 minimal fixture unaffected (6/6 green).
- Regression harness extended (EIGHT_SHAPES + bidirectional cross-version proof + fixture-consistency check) + SPEC/README v1.1 prose — the v1.1 contract is now locked, documented, and regression-protected.
- Optional `asset.schema.json#generator.warnings: array<string>` added additively under v1.1 (no schema_version bump); `export_asset.py` plumbs a `route_cache/warnings.json` sidecar → `build_asset_dict(warnings=None)` → conditional emit — the channel Plan 02's cinematography route client will populate on graceful-degrade.
- httpx sync client calling kais-aigc-platform `shot-analysis` route, mapping geometry+semantic into prompts.json facets with content-hash per-shot cache, single preflight short-circuit, and graceful-degrade to schema-valid empty facets when the route is down
- Wired step_semantic into run_pipeline.py as pipeline slot 5 of 7 (between transcribe + timeline), renumbered 17 [N/6]→[N/7] labels, added 4 CLI flags (--skip-semantic/--offline/--analysis-url/--analysis-timeout), extended --force to clear prompts.json + route_cache/, and built scripts/verify_phase6_smoke.py (3-scenario regression: route-down / --skip-semantic / cache-hit-offline).
- Draft 2020-12 schema freezing the HITL edits round-trip shape (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes) with strict additionalProperties:false + anti-traversal cluster_id pattern, plus a fixture consistent with the existing 3-cluster registry.draft.json, wired as the 10th v1.1 shape in spec/validate.py
- httpx sync client mirroring Phase 6's call_shot_analysis.py — calls the DEFERRED character-reid route once per video (cross-shot aggregation), normalizes the response into registry.draft.json via shape-agnostic projection (CAST-05: all clusters review_state='proposed'), with per-video cache, single preflight probe, broadened graceful-degrade except, and non-destructive warnings sidecar merge
- Confirmed-only canonical registry producer (`apply_edits.py` with fixed-order deterministic apply + ffmpeg representative PNG) plus first-class HITL review HTML (`gen_registry_review.py` with cosine-sorted queue + three-tier viz + client-side edits export) — closes CAST-06/07/08 producer-side
- 1. [Rule 3 — Blocking issue] Plan's `--help` grep expected 3 matches, actual is 5
- Additive `generator.registry_snapshot` schema property (compact confirmed-only freeze of characters+props) with v1.1 fixture example + SPEC §3/§4 documentation — contract-first layer unblocking Plan 02's producer emission.
- Three independent producer-side files wiring the confirmed Phase-7 registry onto prompts (attach_refs.py — PROMPT-01/02), the asset manifest (export_asset.py registry_snapshot — PROMPT-04), and the integrity gate (verify_contract.py Pitfall 17 — PROMPT-03); all pure JSON post-processing, zero ML, zero new deps.
- Three additive changes closing Phase 8's user-visible surface: `html/gen_timeline_html.py` extended with a character/prop gallery + clickable reference chips + per-shot semantic-fill indicator (PRESENT-01/02/03) carrying Phase 7 CR-04 XSS hardening verbatim; `run_pipeline.py:step_timeline` wired to invoke `prompts/attach_refs.py` as a pre-step with the mtime cache extended to include prompts_json (Pitfall 9 prevented); and a new 6-scenario `scripts/verify_phase8_smoke.py` regression harness mirroring the Phase 7 smoke structure.
- Consumer `@kais/infinite-canvas` made v1.1-aware: recognizes `schema_version:"1.1"`, emits 2 character + 1 prop child nodes as `type:"asset"` (assetType character/prop, NOT delivery) via the §7 buildPhaseTree post-process workaround, renders them with 🧑/🔧 icons, locked by 27 green verify assertions — with the v1.0 ep01 WIP untouched.
- The shot-timeline-side `scripts/verify_contract.py` 3-mode harness is confirmed GREEN for v1.1 across producer + consumer modes — ZERO source changes, the v1.0 bridge infrastructure handled everything Phase 9 needed. E2e mode remains deferred (`--e2e-skip`) as the manual post-merge check. PRESENT-06 closed.

---

## v1.0 ShotTimelineAsset Contract (Shipped: 2026-07-20)

**Phases completed:** 4 phases, 7 plans, 13 tasks

**Key accomplishments:**

- One-liner:
- 455-line bilingual prose contract at `spec/SPEC.md` that makes the 6 machine-checkable schemas from Plan 01-01 navigable end-to-end — covers all 4 phase success criteria (5 data shapes, schema_version + graceful-degrade, canonical media + Range-aware 206 + serve.py, self-describing asset.json manifest), quotes the graceful-degrade rule verbatim from `asset.schema.json`, and was approved on first human review.
- Task 1 端到端
- Root cause (verified live against `/usr/lib/python3.12/http/server.py:681`):
- 让 `@kais/infinite-canvas` 的现有 import-from-dir 入口识别 ShotTimelineAsset 目录,折叠成 1 zone + N storyboard + 3 audio + 1 video collection 子图,storyboard 间按 shot_id 升序 emit sequence edges,所有子节点通过 per-type Zod 且前端零改动。
- Single-file Python harness that gates producer↔consumer contract alignment via 6-schema inline validation (producer) + Phase 3 17-assert shell-out (consumer) + deliberate-drift self-test (fail-loud proof).
- Real-producer-asset e2e (backend lifecycle + POST import-from-dir + SQL read-back on o_agentWorkData + structural asserts + 3-layer teardown) + capstone report formally accepting WR-01/04 and recording SC-1 scope reduction.

---
