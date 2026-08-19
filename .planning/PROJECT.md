# kais-shot-timeline

## What This Is

视频分镜解构工具：把一支成片拆解成可导航、多轨道、带语义的分镜资产——分镜边界（首尾帧）+ Demucs 4-stem 分离音轨 + Whisper 对白转录 + 镜头语言/动作/场景的结构化 prompt + 跨镜可复用的角色/道具注册表，并以交互式 HTML 时间轴呈现（点击 stem 波形即静音视频、单独试听该轨，与画面同步）。服务于想把成片逆向成结构化分镜资产、并用于真实叙事连贯的内容创作者与 AI 影视管线。

## Core Value

把成片解构成可导航、多轨道的分镜资产（分镜 + 分离音轨 + 对白 + prompt），且这套形态可移植——能作为无限画布等下游消费者的「最终资产集合形态」被直接消费。

## Prior Milestone: v1.1 分镜语义深化 —— 镜头语言 + 跨镜角色/道具注册表 (SHIPPED 2026-07-25)

**Goal:** 把成片从「边界 + 音轨 + 对白 + prompt 文本」升级为带镜头语言、动作、可复用跨镜角色/道具注册表的叙事资产——prompt 引用注册表实现真实叙事连贯，并把 ShotTimelineAsset 契约 minor-bump 到 v1.1。**DELIVERED** — 5 phases, 16 plans, 34/34 requirements satisfied; producer/contract side complete, 3 cross-repo route dependencies pre-authorized deferred (see `.planning/milestones/v1.1-ROADMAP.md`).

## Last Shipped Milestone: v1.2 音频语义深化 — Audio Semantic Deepening (SHIPPED 2026-07-26)

**Status:** DELIVERED — 8 phases (10-17), 20 plans, 33/33 requirements satisfied; milestone audit `tech_debt` (0 blockers, all 6 cross-phase integration checks GREEN, E2E flow complete). Archive: `.planning/milestones/v1.2-ROADMAP.md`.

**Shipped:**
- **v1.2 contract lock** — 3 new schemas (`audio_semantic`/`speakers`/`speaker-edits`) + additive `asset.schema` extension + `SCHEMA_VERSION="1.2"` single-source + 12-file fixture + bidirectional v1.0↔v1.1↔v1.2 cross-version proof.
- **Phase-10-informed field shapes** — emotion nullable+confidence (DIA-04 ship-nullable); word-level experimental (DIA-05); **MUS-04 instruments DEFERRED to v1.3** (MERT has no classifier + PANNs zenodo-blocked).
- **Producer chain** — `call_audio_analysis.py` httpx client (4-tuple cache + poisoned invalidation + `[audio]` warnings merge + graceful-degrade) + `link_speakers.py` confirmed-only HITL gate + `gen_audio_prompts.py` layered reproduction (tts/music_gen/foley, model-agnostic NL) + `step_audio_semantic` pipeline slot 7/9.
- **SPEAKER-01 closed** — new `^spk_[0-9]{3}$` acoustic ID space (disjoint from `char_NNN`) + HITL review HTML + idempotent confirmed-only apply.
- **Rendering** — `timeline.html` dialogue/music/sfx chips + speaker→character chip + reproduction panel ("estimated" labels) + XSS 3-layer hardening; canvas consumer recognizes `schema_version:"1.2"` + emits per-shot audio `type:"asset"` children via §7 buildPhaseTree.
- **CUDA path resolved (BLOCKER 1)** — stay-on-12.4 (WhisperX runs on cu124 force-pin isolated venv; not a forcing function for 12.8).

**Known deferred (pre-authorized, scope-fenced):** cross-repo PRs (`feat/audio-analysis-route` + `feat/canvas-asset-collection`, post-milestone per v1.1 Phase 9 precedent); MUS-04 instruments v1.3; rigorous DIA-04 macro-F1 annotation; WhisperX drift metric refinement; PANNs Cnn14 re-eval when zenodo-reachable; Phase 13/16 browser UAT; e2e backend verify mode.

**Next:** ✅ v1.3 已启动（2026-08-19）——Round-trip Validation（见下 Current Milestone）；MUS-04 / DIA-06 继续 defer。

## Current Milestone: v1.3 Round-trip Validation（逆推→复现→比对闭环数据集）

**Goal:** 用「qwen-eye 看片段逆推 prompt → h3 fl2va 首尾帧复现 → 与原片段比对打分」的闭环，把 prompts.json 从「看起来合理」升级为「经复现验证的可信真值」，产出 (首帧, 尾帧, prompt) 高价值数据集——rejection sampling 造 SFT 真值。

**Target features:**
- **Contract v1.3**——`roundtrip.schema.json` sidecar（per-shot: regen video ref + scores + verdict{accepted/rejected} + attribution + reason）+ `asset.json#data` optional 挂载 + fixture + validate gate（mirror v1.2 三层门）
- **qwen-eye v2 看片段**——每镜抽 8 帧序列逐帧 `observe_single` 问答 → 升级 action/camera facet（现只看首/中/尾 3 静帧是最大质量缺口）；同时把 v1.2 `audio_semantic` 当 ear 输入融进视觉 prompt（雨声→scene=雨天）
- **h3 复现客户端**——kst 直连 ComfyUI API 提交 MiniMax H3 fl2va workflow（参考 kmc `h3_batch_render_v4.py` 模式），per-shot cache + 断点续跑 + VRAM guard（自动 `/free` + TTS 共存检测，p11b pitfalls）
- **Scorer**——中段帧 CLIP/SigLIP 轨迹相似度（首尾帧被 fl2va condition 无信息量，信号全在中段）+ VLM judge 归因（区分 prompt 好/h3 不行 vs prompt 欠约束）
- **数据集产出**——verdict 写 `roundtrip.json`；accepted 子集导出独立 dataset 目录（首帧/尾帧/prompt.json/manifest）；rejected 带归因保留（hard negatives + h3 能力边界）；gallery 加 round-trip 审阅面板（原片段 vs 重生成并排 + 分数 + accept 按钮）

**Key context:** 基础设施 ~80% 就位（详见 `.planning/research/v1.3-roundtrip-validation-proposal.md` + `SUMMARY.md`）：qwen-eye 引擎 :8125 已接（`analysis/local_vision_facets.py`）但 llama.cpp 单图 bug 硬约束；h3 fl2va 3090 实战化（5s/124帧 5-8min/镜，11-22GB VRAM）；~100 镜/集 × 5-8min = 8-13h/轮 → 必须 per-shot cache + 抽样先行校准阈值。**最高风险**：① verdict 混淆 prompt 质量与 h3 能力（不归因则数据集系统性偏向简单动作）② h3 渲染时长/VRAM 竞争 ③ 帧序列问答在 Q3 27B 上的动作描述质量未验证。

## Requirements

### Validated

<!-- 已发布、确认有价值。v1.0 之前的 pre-GSD 基线。 -->

- ✓ 分镜检测（V1 Adaptive / V2 双检测器+后处理 / V3b 4 趟融合推荐版）— PySceneDetect — pre-GSD 基线
- ✓ 音轨分离（Demucs htdemucs 4-stem: vocals/drums/bass/other）+ 分镜级能量/频谱分析 — pre-GSD 基线
- ✓ 语音转录（Whisper，faster-whisper 优先、openai-whisper 回退）— pre-GSD 基线
- ✓ 交互式时间轴 HTML（双面板：分镜卡片首尾帧 + 竖向 stem 波形 + 视频播放器 + 实时字幕条 + 点击播放分离 stem）— pre-GSD 基线
- ✓ 分镜卡片网格 / 音频分析卡片网格 / prompt 审阅 HTML（一键复制）— pre-GSD 基线
- ✓ 分镜 prompt 反推（首尾帧 → 结构化 prompt + 连贯 prompt 文本 → prompts.json）— pre-GSD 基线
- ✓ Range-aware HTTP server（scripts/serve.py，206 Partial Content）用于 stem/视频 seek 播放 — pre-GSD 基线
- ✓ ShotTimelineAsset 规范（6 个 JSON Schema draft 2020-12 + 版本号 graceful-degrade 规则 + 媒体引用约定 + 自描述 manifest + validate.py）— Validated in Phase 1: ShotTimelineAsset Specification
- ✓ shot-timeline 导出 ShotTimelineAsset 产物（export_asset.py 写 asset.json + canonical symlinks；run_pipeline.py step_export 第 6 步 always-on；serve.py FD-leak 修复 + check_range.py Range-206 自检；additive-only）— Validated in Phase 2: shot-timeline Exporter (Producer)
- ✓ 画布侧（@kais/infinite-canvas）消费 ShotTimelineAsset，表示为 collection（import-from-dir.ts 新增 ShotTimelineAsset 分支：asset.json 识别 → extractShotTimelineArtifacts → 复用 buildPhaseTree；1 zone 父节点 + storyboard/audio/video 子节点 + sequence edges；合成字段满足 per-type Zod，不改 renderer / 不 bump contract；跨仓库 kais-aigc-platform feat/canvas-asset-collection）— Validated in Phase 3: Canvas Consumer
- ✓ 跨仓库契约一致性验证（scripts/verify_contract.py 三模式 harness：producer inline schema 校验 + consumer shells Phase 3 verify + e2e 真 producer→backend→SQL read-back 断言 1 zone+93 storyboard+3 audio+video+92 sequence edges；self-test 证 fail-loud；WR-01/04 正式接受）— Validated in Phase 4: Cross-Repo Contract Verification
- ✓ v1.1 契约（3 新 schema：characters/props/registry + 2 additive 扩展：prompts character_refs/prop_refs + asset data.characters/props/media.characters[]/props[]/generator.warnings/registry_snapshot；schema_version `1`→`1.1` producer-locked via SCHEMA_VERSION constant；v1↔v1.1 bidirectional cross-version self-test）— Validated in Phase 5: Contract v1.1
- ✓ 镜头语言自动填充（analysis/call_shot_analysis.py httpx 客户端 + LOCKED route→prompts 映射 + per-shot cache + preflight + graceful-degrade；run_pipeline step_semantic slot 5 of 8 + 4 flags + generator.warnings sidecar）— Validated in Phase 6: Cinematography Auto-Fill (route deferred; mapping proven against 7 fixtures)
- ✓ 跨镜角色/道具注册表 + HITL（analysis/call_reid.py 客户端 + registry/apply_edits.py confirmed-only 硬门 + idempotent + ffmpeg 代表图 + html/gen_registry_review.py 一等 HITL review HTML + registry-edits schema；step_reid slot 6 of 8 + [N/7]→[N/8]）— Validated in Phase 7: Cross-Shot Re-ID + HITL (route + τ deferred; producer/contract complete)
- ✓ Prompt 引用系统 + HTML 画廊（prompts/attach_refs.py 确定性 Pattern 2 recompose + idempotent + generator.registry_snapshot 冻结 + Pitfall 17 integrity + gen_timeline_html 画廊/reference chip/运镜填充指示器 + _esc XSS 防御）— Validated in Phase 8: Prompt Reference System + HTML Gallery
- ✓ Canvas 消费者 v1.1（import-from-dir.ts SHOT_TIMELINE_KNOWN_VERSIONS += "1.1" + character/prop asset 子节点经 §7 post-process + AssetNode typeIcons 🧑/🔧 + verify-canvas 29/29；无 custom renderer / 无 Zod bump）— Validated in Phase 9: Canvas Consumer Integration (e2e deferred)

### Active

<!-- v1.3 Round-trip Validation — requirements scoped via /gsd:new-milestone; full REQ-IDs live in .planning/REQUIREMENTS.md. -->

_v1.3 requirements defined in `.planning/REQUIREMENTS.md` (categories: CONTRACT / VISION / REGEN / SCORE / DATASET / PIPELINE / PRESENT)._

- ✓ **Phase 18 (Contract v1.3) DELIVERED** — RT-01..04：roundtrip.schema.json（14th schema）+ asset.schema data.roundtrip 首个 object 挂载 + warnings items 加宽 string|{code,detail} + SCHEMA_VERSION "1.3" 单源 + 13-file fixture + validate 四阶 gate + v1.2↔v1.3 bidirectional proof（A3 负测试防盲过滤）+ SPEC §4/§5.10/§10.5 三层 fidelity disclaimer（人类审阅通过 2026-08-19）。代码评审 6 warnings 全修 + 复审 clean。

### Known Deferred (v1.1 → post-merge / v2)

Cross-repo dependencies out of this repo's control; producer/contract side complete + graceful-degrade proven for each:

- [ ] Phase 6 live `shot-analysis` route round-trip (kais-aigc-platform `feat/shot-analysis-route` unmerged)
- [ ] Phase 7 `character-reid` route + SAM3 multi-frame driver + DINOv2 embedding/clustering + empirical τ calibration on ep01 crops (route not yet built)
- [ ] Phase 9 e2e backend mode of `verify_contract.py` (heavy) + canvas visual pilot



### Out of Scope

<!-- 明确边界，含理由，防止回头再加。v1.1 在 v1.0 基础上更新。 -->

- 完全自动 re-id（无人 review）— re-id 不可能 100% 准，v1.1 必须 human-in-the-loop；全自动留待 re-id 精度成熟后再评估
- ~~对白→角色归属（谁说了哪句台词）~~ — **v1.2 进 scope**（SPEAKER-01：说话人分离 speaker_id 挂 character registry）；v1.1 曾因「大 lift（需说话人识别/唇形对齐）」列为 Out of Scope，v1.2 借 pyannote 路由化降 lift
- 跨成片角色连续性（同一角色跨不同视频识别为同一实体）— v1.1 只在单支成片内 re-id；跨片留后续
- 画布内原生时间轴渲染器（stem 播放引擎、波形 canvas、Range 媒体服务）— 完整原生交互是后续 milestone
- 新增画布 custom renderer — v1.1 用「新节点类型 + 复用现有渲染器」路径，仍不引入 custom renderer（契约 bump 仅是 schema_version + 新数据文件，渲染复用）
- 修改 shot-timeline 现有检测/转录/分离算法本身 — 仍是 validated 基线；v1.1 新分析（镜头语言/角色道具）全部走外部 kais-aigc-platform 路由，不动 shot-timeline 自身算法
- 把 shot-timeline 的检测/转录/分离拆成画布编排 skill（紧耦合方案）— 仍维持「外部生产者」松耦合

## Context

**跨仓库关系。** 本仓库（kais-shot-timeline）是新建立的 GSD 工程，作为 ShotTimelineAsset 格式的**生产者/权威定义方**。消费方是 `/data/workspace/kais-aigc-platform/packages/infinite-canvas`（`@kais/infinite-canvas`，React Flow + Zustand + Vite/TS）。两个仓库松耦合：shot-timeline 导出产物，画布通过其现有 `import-from-dir` 路径吃进来。画布的 GSD 工程独立（已到 v2.0），不在本仓库追踪。

**画布侧关键事实（决定本 milestone 形态）。** 画布当前**没有「相关资产集合」概念**——`storyboard` 节点 = 单个镜头，镜头序列只靠 `sequence` 边表达。shot-timeline 的格式本质是一个同步多镜头集合（分镜 + stems + 转录 + prompts），因此本 milestone 实际上是给画布引入一个目前不存在的实体类型。低摩擦落地路径：用一个结构化父节点（沿用 `zone`/`phase` 模式，持有子节点 ID）聚合现有 `storyboard`/`audio`/`video` 子节点——画布的 receiver schema (`canvasAssetSchema.ts`) 已经把 `structuralTypes = {zone, phase, suggestion, reference}` 透传不校验，复用现有 5 个渲染器，无需 `default_renderer` 新选项（contract bump）。

**shot-timeline 当前数据形状（导出契约的来源）。** 5 个 JSON 喂给 HTML 生成器：`shots.json`（`{id, start_sec, end_sec, duration}`，canonical 镜头列表）、`audio_analysis.json`（Demucs 分析 + 每镜能量/谱/`dominant_type`）、`transcript.json`（Whisper segments）、`frames.json`（首尾帧 base64）、`prompts.json`（结构化 prompt）。运行时还需 video mp4 + 3 个 stem wav（`_vocals/_drums/_other`）经 Range-aware server 提供。timeline.html 自包含（内联 CSS/JS、帧内联 base64），唯独这 3 个媒体文件外置。

**v1.1 新增语义层（镜头语言 + 角色/道具注册表）。** 现状关键事实：① `prompts.json` schema 已含 `subject/action/camera/scene/lighting/style/prompt_text` 结构化字段，但 shot-timeline **没有 prompt 生成器**——`prompts/merge_prompts.py` 只合并外部产出的 `prompt_parts/part_*.json`，字段目前靠外部/手动填。② 运镜分析能力**已在 kais-aigc-platform 用 ComfyUI 落地**（geometry 自建节点跑稀疏光流出运镜 + SAM3.1 主体跟踪出主体运动 + Qwen3-VL-8B INT8 出景别/机位/语义；driver `scripts/shot-analysis/shot_analysis_driver.py` 读 `shots.json` 逐镜投喂，路由 `POST /api/v1/production/shot-analysis`），P0-P4 验证完成（2026-07-23），但**两特性分支未 merge**（`feat/shot-geometry-nodes` 节点 + `feat/shot-analysis-route` driver/路由）。该输出几乎一一映射到现有 prompts 字段。③ 角色/道具切图 + 跨镜 re-id 是**全新能力**，尚不存在。v1.1 决定：shot-timeline 作 HTTP 客户端调这些路由（运镜复用、角色道具新建端点），合并 JSON 进资产；re-id 走「DINOv2 embedding + Agglomerative 聚类 + 三档阈值 + 人工 review」半自动路径；契约 minor bump 到 schema_version `"1.1"`（纯增量，按项目 SPEC semver-lite 规则），靠 v1.0 graceful-degrade 规则兜底老消费者。

## Constraints

- **跨仓库**：shot-timeline（本 GSD 工程）= 生产者 + 路由客户端 + 契约权威；kais-aigc-platform = 分析路由宿主 + canvas 消费者（每 phase 独立分支/PR）
- **松耦合**：shot-timeline = 外部生产者，画布 = 消费者；产物必须自描述、带版本号，两个仓库可独立演进
- **不动 shot-timeline 核心算法**：分镜检测/转录/分离仍是 validated 基线；v1.1 新分析（镜头语言/角色道具）**全部走 kais-aigc-platform 路由**，不在 shot-timeline 内重跑 ML
- **路由依赖**：shot-timeline 的镜头语言/角色道具填充依赖 kais-aigc-platform 路由可用 + 两未 merge 运镜分支先上线；路由不可用时 shot-timeline 必须能 graceful-degrade（跳过该步、资产仍可生成）
- **re-id 精度上限**：跨镜 re-id 不可能 100% 准，必须 human-in-the-loop review；接受「够用即可」，不追求全自动
- **契约仅 minor bump**：v1.1 把 schema_version 升到 `"1.1"`，新增字段/数据文件，但不做破坏性变更（无 rename/语义漂移/删除）；老消费者靠 graceful-degrade 不崩。仍不引入画布 custom renderer（新节点类型复用现有渲染器）
- **媒体服务**：导出约定需覆盖 Range-aware HTTP 服务（画布消费 stem/视频 seek 依赖 206 响应）；角色/道具图作为新媒体类别纳入约定

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1.0 交付 = 格式契约（非原生组件移植、非 iframe 嵌入） | 格式是骨架，原生渲染/嵌入都建立在它之上；v1.0 先落契约 + 画布最小消费 | — Pending |
| shot-timeline 作为「外部生产者」（非画布编排 skill） | 与「shot-timeline 独立 GSD 工程」决策一致；两仓库松耦合、独立演进 | ✓ Validated Phase 2（export_asset.py + step_export 落地导出层，additive-only） |
| 画布用结构化父节点表示 collection（非新 node type / custom renderer） | receiver schema 已透传 structural types，复用现有 5 渲染器，零 contract bump | — Pending |
| GSD 工程建在 shot-timeline（非 aigc-platform） | 格式权威定义方 = 生产者；aigc-platform 已有独立 GSD（v2.0） | — Pending |
| 在 `feat/canvas-asset-collection` 分支开发（非 main / 非 worktree） | main 保留可交付、隔离多 phase 工作；worktree 无法跨仓库组合且拆分 .planning/ 状态 | ✓ Validated Phase 3/4（v1.0 已 ship） |
| **v1.1** 新分析走「shot-timeline 调 kais-aigc-platform 路由」（非本地实现） | 运镜 infra 已在 comfyui 侧建好；延续 v1.0 松耦合；shot-timeline 不增重 ML 依赖；需先 merge 两运镜分支 | ✓ Validated Phase 6/7（thin httpx 客户端 + graceful-degrade；零 ML 依赖进 producer；route round-trip deferred 待分支 merge） |
| **v1.1** 角色道具做「跨镜 re-id 注册表」（非单镜提取） | 「真实叙事连贯」的核心 = 同一角色跨镜是同一引用；接受 re-id 不准、用人工 review 兜底 | ✓ Validated Phase 7（producer 客户端 + 一等 HITL review HTML + apply_edits confirmed-only；route/driver/τ deferred） |
| **v1.1** 升级 ShotTimelineAsset 到 schema_version `"1.1"`（minor bump，非侧车数据；刻意不用 `"2"`） | 纯增量变更按项目 SPEC semver-lite 规则 = minor；保留 `"2"` 给未来破坏性变更；资产自描述、可移植、一等公民；v1.0 graceful-degrade 规则专为这种 minor bump 设计 | ✓ Validated Phase 5/8（schema_version `"1.1"` producer-locked；v1↔v1.1 bidirectional cross-version self-test 0 errors；全 milestone 共享一个 minor） |
| **v1.1** 双端展示（shot-timeline HTML + canvas 新节点类型） | 用户要端到端可见；接受跨仓库 ~30% 额外开销（v1.0 实测） | ✓ Validated Phase 8/9（HTML 画廊/chip/指示器 + canvas character/prop asset 节点经 §7 post-process；无 custom renderer / 无 Zod bump） |
| **v1.2** 引擎放 kais-aigc-platform（路由式，非全本地） | 延续 v1.0/v1.1 松耦合；shot-timeline 不增重 ML 依赖；复用 v1.1 `step_semantic` 的 httpx+graceful-degrade 模式；用户硬件虽可本地，但项目约束偏好路由 | — Pending（Phase 1 risk-validation 起验证） |
| **v1.2** 三模态一起（对白/音乐/音效） | 用户目标需三模态才能支撑「复现音频」；分模态做但同一 milestone | — Pending |
| **v1.2** 分层复现 prompt（TTS / music-gen / foley） | 复现对白/音乐/音效面向不同生成器，单一 NL prompt 服务不了任一；分层才能真复现 | — Pending |
| **v1.2** Phase 1 先做模型 risk-validation 再锁契约 | 中文 SER 跨域 + 乐器识别未验证是最高风险；镜像 v1.1 Phase 7 DINOv2 τ spike（先证模型、再立契约） | ✓ Validated Phase 10（spike report `.planning/research/audio-spike-report.md` + 4 outcomes locked in this table） |
| **v1.2 Phase 10 — models_used per modality** (Row 1 of 5 locked outcomes) | Phase 10 spike validated; canonical IDs only (T-10-03 supply-chain mitigation); per-modality selection from head-to-head evidence where available, provisional where blocked | Dialogue (SER + events): `iic/SenseVoiceSmall` via funasr (route-host, ModelScope canonical) · Dialogue (transcribe + word-align + diarize): `WhisperX large-v3 + wav2vec2-large-xlsr-53-chinese-zh-cn` (route-host, cu124 isolated venv) · Music (MIR): `m-a-p/MERT-v1-95M` PROVISIONAL (PANNs Cnn14 comparison PENDING Phase 12 — zenodo-blocked at spike time) · SFX (audio events): folded into SenseVoice 8-event + PANNs 527-class (PANNs pending). *(decided_at: 2026-07-25; phase: 10; evidence: `.planning/research/audio-spike-report.md#section-4-recommendations`)* |
| **v1.2 Phase 10 — CUDA path: STAY-ON-12.4 (cu124)** (Row 2 of 5; resolves BLOCKER 1) | WhisperX 3.8.6 metadata declares `torch~=2.8.0` but RUNS CLEANLY on force-pinned cu124 stack (torch 2.6.0+cu124) in isolated venv; A1 (CPU mode) OK; full cuda:0 run OK; system torch uncontaminated (3-point canary) | **BLOCKER 1 RESOLVED.** Route host stays at cu124; WhisperX runs in isolated venv with cu124 force-pin (Plan 10-05 pattern becomes production); CUDA 12.8 upgrade deferred indefinitely (revisit only if a future model strictly requires it); DIA-05 ships experimental at best. *(decided_at: 2026-07-25; phase: 10; evidence: `.planning/research/audio-spike-report.md#section-3-whisperx-drift--dia-05-evidence--cuda-path`)* |
| **v1.2 Phase 10 — DIA-04 dialogue emotion: SHIP-NULLABLE+CONFIDENCE** (Row 3 of 5) | SenseVoice self_consistency_pct=100.0 is a LABEL-STABILITY proxy (NOT accuracy); short clips + deterministic CPU explain the 100%; qualitative sanity coherent (HAPPY dialogue→HAPPY, ANGRY→😡-tagged confrontational lines); no rigorous macro-F1 (methodology_b developer annotation deferred — ~1hr labor) | `emotion` field NULLABLE in `audio_semantic.json` schema + `confidence` field populated + `fidelity_disclaimer` applies. Rigorous macro-F1 deferred to Phase 12+ once route host is up + developer-annotated ground truth exists. *(decided_at: 2026-07-25; phase: 10; evidence: `.planning/research/audio-spike-report.md#section-1-ser-sensevoice--dia-04-evidence`)* |
| **v1.2 Phase 10 — MUS-04 instruments: DEFER to v1.3** (Row 4 of 5) | MERT-v1-95M has NO instrument classifier head — spike only produced K-means embedding clusters (5) correlating with shot DURATION (mean-pooling artifact), NOT instruments; PANNs Cnn14 BLOCKED (zenodo.org download stalled; hf-mirror `nicofarr/panns_Cnn14` `.pth` conversion deferred); NO instrument predictions produced | `instruments` field OMITTED/DEFERRED in v1.2 `audio_semantic.json` schema; route host needs a REAL MIR classifier (PANNs once zenodo-reachable, or fine-tuned MERT head) — Phase 12+ / v1.3. *(decided_at: 2026-07-25; phase: 10; evidence: `.planning/research/audio-spike-report.md#section-2-mir-head-to-head-mert-vs-panns--mus-04-evidence`)* |
| **v1.2 Phase 10 — DIA-05 word-level timestamps: SHIP-EXPERIMENTAL** (Row 5 of 5) | A1 (CPU `load_align_model`) OK in 7.9s; A2 (arbitrary-segment align) OK; **boundary drift median=101.5ms (<200 ✓)**; dense-speech bucket `pct_under_200ms=0.933` (≥0.80 ✓); aggregate per-word `pct_under_200ms=0.189` is BELOW 0.80 — BUT this is a **METRIC-DEFINITION ARTIFACT** (drift=`word_start−segment_start` inflates for interior words in long segments; `mean_drift_ms=2393` dominated by this) | Word-level timestamps SHIP as EXPERIMENTAL with metric-definition caveat; refine drift metric in Phase 12 (use boundary drift, not per-word-from-segment-start) + validate on more episodes; segment-level remains SLA path. *(decided_at: 2026-07-25; phase: 10; evidence: `.planning/research/audio-spike-report.md#section-3-whisperx-drift--dia-05-evidence--cuda-path`)* |
| **v1.3** = Round-trip Validation（逆推→复现→比对闭环数据集） | prompt 静帧反推无验证机制，round-trip 是唯一客观信号；rejection sampling 把「看起来合理」变成「经复现验证的真值」 | — Pending |
| **v1.3** qwen-eye v2 走「N 帧序列逐帧问答」务实版（非先上 vLLM 视频原生） | 现引擎 llama.cpp 单图 bug 硬约束 + ctx 16K；`/data/models/comfyui/LLM/Qwen-VL/Qwen3-VL-8B-Instruct` 已在盘上留升级位，先零新基建跑通 | — Pending |
| **v1.3** ear = 复用 v1.2 `audio_semantic` 融合进视觉 prompt（不新引音频理解引擎） | 对白/sfx/foley 语义 v1.2 已产出；缺的只是融合进 prompt 修正（雨声→scene=雨天） | — Pending |
| **v1.3** 打分围绕中段帧 + verdict 必须归因 + rejected 保留 | 首尾帧被 fl2va condition 无信息量；不归因则数据集系统性偏向简单动作；rejected = hard negatives + h3 能力边界测绘 | — Pending |
| **v1.3** h3 客户端 kst 直连 ComfyUI API（非经 kmc/hermes runtime） | 闭环是 kst 资产生产一部分；mirror route-client 模式 + p11b VRAM pitfalls（kill TTS + `/free`）+ per-shot cache | — Pending |
| **v1.3** dataset 导出独立目录（非 asset.json 内嵌 subset） | 消费端不受契约约束；asset 契约只 additive 挂 `roundtrip.json` sidecar | — Pending |
| **v1.3** MUS-04 乐器识别继续 defer（v1.2 遗留，PANNs zenodo-blocked 未解） | 本 milestone 已满载不捎带；DIA-06 同理继续 defer | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-19 — Phase 18 (Contract v1.3) complete; v1.3 contract locked ahead of round-trip producers (Phases 19-22)**v1.3 Round-trip Validation** (qwen-eye v2 看片段逆推 → h3 fl2va 复现 → 中段帧打分 + 归因 → accepted 数据集导出; schema 1.2→1.3). v1.2 音频语义深化 SHIPPED (8 phases, 20 plans, 33/33 reqs).*
