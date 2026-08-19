# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 分镜语义深化** — Phases 5-9 (shipped 2026-07-25) — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump 1→1.1 + 双端展示 — [archived](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 音频语义深化** — Phases 10-17 (shipped 2026-07-26) — route-based 三模态音频语义（对白/音乐/音效）+ 分层复现 prompt (TTS/music-gen/foley) + 说话人↔角色 HITL + 契约 minor bump 1.1→1.2 + 双端展示 — [archived](milestones/v1.2-ROADMAP.md)
- 🚧 **v1.3 Round-trip Validation（逆推→复现→比对闭环数据集）** — Phases 18-22 (in progress) — qwen-eye v2 看片段逆推 → h3 fl2va 复现 → 中段帧打分 + 归因 → accepted 数据集导出；契约 minor bump 1.2→1.3

## Phases

<details>
<summary>✅ v1.0 ShotTimelineAsset Contract (Phases 1-4) — SHIPPED 2026-07-20</summary>

A repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection.

- [x] **Phase 1: ShotTimelineAsset Specification** — repo-agnostic contract (6 schemas + version + media refs + manifest) both repos implement against — COMPLETE 2026-07-20
- [x] **Phase 2: shot-timeline Exporter (Producer)** — pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served — COMPLETE 2026-07-20
- [x] **Phase 3: Canvas Consumer** — canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump) — COMPLETE 2026-07-21 *(code in kais-aigc-platform `feat/canvas-asset-collection`)*
- [x] **Phase 4: Cross-Repo Contract Verification** — end-to-end flow + regression protection against schema/media-reference drift — COMPLETE 2026-07-21

**Audit:** 12/12 requirements satisfied, 4/4 phases verified, integration complete — [v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v1.1 分镜语义深化 (Phases 5-9) — SHIPPED 2026-07-25</summary>

Strict-additive, contract-first minor bump on v1.0. Adds two new pipeline stages calling ML HTTP routes in `kais-aigc-platform` (cinematography analysis + cross-shot re-id), three new optional data files (`characters.json`, `props.json`, enriched `prompts.json`), a first-class HITL review HTML deliverable, and a canvas consumer extension. Mirrors v1.0's contract-first sequencing that worked.

- [x] **Phase 5: Contract v1.1** — 3 new registry schemas + 2 additive schema extensions + SPEC + 9-file v1.1 fixture + verify harness (no route dependency) — COMPLETE 2026-07-24
- [x] **Phase 6: Cinematography Auto-Fill (`step_semantic`)** — httpx client + graceful-degrade + per-shot cache + generator.warnings — COMPLETE 2026-07-24
- [x] **Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`)** — producer client + HITL review HTML + `apply_edits.py` confirmed-only gate — COMPLETE 2026-07-25
- [x] **Phase 8: Prompt Reference System + shot-timeline HTML Gallery** — `attach_refs.py` + `registry_snapshot` freeze + gallery/chips/indicator — COMPLETE 2026-07-25
- [x] **Phase 9: Canvas Consumer Integration (cross-repo)** — consumer recognizes `"1.1"` + emits character/prop `asset` nodes (no renderer / no Zod bump) — COMPLETE 2026-07-25

**Audit:** 34/34 requirements satisfied, 5/5 phases verified — [v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**Full phase details:** [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

<details>
<summary>✅ v1.2 音频语义深化 (Phases 10-17) — SHIPPED 2026-07-26</summary>

Route-based audio semantic deepening: a third sibling of the v1.1 route-pattern family. Adds 3 modalities (dialogue/music/sfx) + layered reproduction prompts (TTS/music-gen/foley) + closes the v1.1 SPEAKER-01 deferral via a new `spk_NNN` ID space + HITL linking. Schema bump `1.1 → 1.2` pure-additive. "先证模型、再立契约" sequencing via Phase 10 audio model spike.

- [x] **Phase 10: Risk-Validation Spike + Route Stub** — SenseVoice/MERT/pyannote/WhisperX validated BEFORE contract; CUDA stay-on-12.4 locked; route stub envelope — COMPLETE 2026-07-25
- [x] **Phase 11: Contract v1.2** — 3 new schemas + 12-file fixture + SCHEMA_VERSION="1.2" + bidirectional cross-version proof — COMPLETE 2026-07-25
- [x] **Phase 12: Producer Route Client** — `call_audio_analysis.py` thin httpx + per-shot cache + poisoned-cache + [audio] warnings merge + graceful-degrade — COMPLETE 2026-07-25
- [x] **Phase 13: SPEAKER-01 Linkage HITL** — `link_speakers.py` confirmed-only + `gen_speaker_review.py` → `speakers.json` — COMPLETE 2026-07-25
- [x] **Phase 14: Pipeline Integration** — `step_audio_semantic` slot 7 of 9 + banner renumber + 4 CLI flags + 5-scenario smoke harness — COMPLETE 2026-07-26
- [x] **Phase 15: Layered Reproduction Prompts** — in-place `reproduction.{tts,music_gen,foley}` + `--offline` fallback + CONDITIONAL field gating — COMPLETE 2026-07-26
- [x] **Phase 16: HTML Gallery** — dialogue/music/sfx chips + speaker→character chip + reproduction panel + XSS hardening — COMPLETE 2026-07-26
- [x] **Phase 17: Canvas Consumer (deferrable)** — v1.2 recognition + audio asset nodes via §7 post-process (no renderer / no Zod bump) — COMPLETE 2026-07-26

**Audit:** 33/33 requirements satisfied, 8/8 phases verified, `tech_debt` grade (0 blockers, all 6 cross-phase integration checks GREEN) — [v1.2-MILESTONE-AUDIT.md](milestones/v1.2-MILESTONE-AUDIT.md)

**Full phase details:** [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)

</details>

### 🚧 v1.3 Round-trip Validation（逆推→复现→比对闭环数据集）(Phases 18-22) — ACTIVE

**Milestone Goal:** 用「qwen-eye 看片段逆推 prompt → h3 fl2va 首尾帧复现 → 中段帧打分 + VLM judge 归因」的闭环，把 prompts.json 从「看起来合理」升级为「经复现验证的可信真值」，产出 (首帧, 尾帧, prompt) 高价值数据集 —— rejection sampling 造 SFT 真值。

Round-trip closes the loop the first three milestones opened: qwen-eye v2 watches shot frame-sequences to upgrade action/camera facets (v1.2 `audio_semantic` as ear), a new ComfyUI-direct client regenerates each shot from (首帧, 尾帧, prompt) via MiniMax H3 fl2va, a dual-signal scorer (mid-frame CLIP/SigLIP trajectory + VLM judge attribution) validates the round-trip on an ep01 ≤20-shot sample, and accepted triples export as an independent SFT-grade dataset directory. Schema bump `1.2 → 1.3` pure-additive. Ordering constraints from research: **契约先行** (contract before any round-trip code writes), **抽样先行** (≤20 shots calibrate thresholds before overnight 8-13h full runs), **VRAM 串行编排** (qwen-eye 13.4GB lease and h3 batch never co-resident on the 3090).

- [x] **Phase 18: Contract v1.3** — `roundtrip.schema.json` sidecar + `SCHEMA_VERSION="1.3"` + fixture/validate gate + SPEC + graceful-degrade 契约层（mirror v1.2 三层门） (completed 2026-08-19)
- [ ] **Phase 19: qwen-eye v2 看片段** — 每镜 ≤8 帧逐帧 `observe_single` 问答升级 action/camera facet + audio_semantic ear 融合（合并策略 ep01 spike 后锁定）
- [ ] **Phase 20: h3 复现客户端** — kst 直连 ComfyUI 提交 MiniMax H3 fl2va workflow + per-shot 4-tuple cache + 断点续跑 + VRAM guard（TTS kill + `/free` + eye↔h3 串行编排）
- [ ] **Phase 21: Scorer + 阈值校准** — 中段帧 CLIP/SigLIP 轨迹相似度 + VLM judge 归因三分类 + ep01 ≤20 镜实测分布锁 accepted 双门槛 + verdict 写 `roundtrip.json`（rejected 永不删除）
- [ ] **Phase 22: Dataset Export + Integration** — `step_roundtrip` 流水线集成 + ≥4 场景 smoke 回归 + gallery round-trip HITL 审阅面板 + accepted 子集独立 dataset 目录导出

## Phase Details

### Phase 18: Contract v1.3

**Goal**: Lock the v1.3 contract — `roundtrip.schema.json` sidecar（per-shot: regen video ref + scores{midframe_sim, judge} + verdict{accepted/rejected} + attribution + reason）+ `asset.json#data.roundtrip` optional 挂载 + `SCHEMA_VERSION="1.3"` 单源 + fixture/validate gate + SPEC — BEFORE any round-trip code writes against it（契约先行，mirror v1.1 Phase 5 / v1.2 Phase 11 先例）。
**Depends on**: Nothing (first phase of milestone; v1.2 baseline shipped)
**Requirements**: RT-01, RT-02, RT-03, RT-04
**Success Criteria** (what must be TRUE):

  1. `spec/schemas/roundtrip.schema.json`（draft 2020-12、`additionalProperties:false`）对一个人工 fixture 全字段校验通过（regen video ref / scores{midframe_sim, judge} / verdict{accepted,rejected} / attribution / reason）；`asset.schema.json` 增 optional `data.roundtrip`（不进 `required[]`）
  2. `SCHEMA_VERSION = "1.3"` 在 export_asset.py 单源锁定；roundtrip.json 缺席时 v1.2 及以前全部数据文件 byte-identical（RT-01 红线，契约级证明）
  3. `validate.py` shape gate 扩展三层门（minimal / v1.2 / v1.3 fixture 全绿）+ `verify_contract.py` v1.2↔v1.3 bidirectional cross-version proof（forward 0 errors / backward 0 non-additive errors）
  4. roundtrip 数据缺席时导出照常 + `[roundtrip]` warnings sidecar 记因通道落地——ComfyUI 不可达 / VRAM 不足 / 打分模型缺席三种因由在 warnings 形状中可表达（RT-04 契约级 degrade）
  5. SPEC.md §4 changelog 1.2→1.3 + §5 roundtrip 形状文档 + fidelity disclaimer（accepted = 「h3 可复现」≠「prompt 完美」）一次人类审阅通过

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] 18-01-PLAN.md — roundtrip.schema.json + asset.schema.json 两处 delta（data.roundtrip object 挂载 + warnings items 加宽）+ export_asset.py（SCHEMA_VERSION "1.3" + 挂载统计 + warnings 装载加宽）

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 18-02-PLAN.md — spec/fixtures/v1.3/ 13 文件 + validate.py 四阶 gate + verify_contract.py v1.2↔v1.3 双向证明（backward 过滤扩展 + 负测试 + EIGHT_SHAPES object 特判 + 一致性块）

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 18-03-PLAN.md — SPEC.md §1/§4/§5/§10 + README v1.3（三层 fidelity disclaimer + AF-01 守门 + 人类审阅 checkpoint）

### Phase 19: qwen-eye v2 看片段

**Goal**: prompts.json 的 action/camera facet 从「3 静帧脑补」升级为「≤8 帧序列逐帧实证」（llama.cpp 单图 bug 硬约束下的务实版），v1.2 `audio_semantic` 作为 ear 融进视觉 prompt——独立于 round-trip 闭环就提升 prompt 质量。
**Depends on**: Nothing hard within v1.3（可与 Phase 18 并行规划；qwen-eye :8125 引擎与 v1.2 audio_semantic 数据已在位，零新基建）
**Requirements**: VISION-01, VISION-02
**Success Criteria** (what must be TRUE):

  1. ep01 抽样镜跑 v2 后，prompts.json 的 action/camera facet 含跨帧合并出的完整动作链/运镜描述（与 v1 三静帧产物对比差异可见）；只填空缺/更短 facet——route/人工已有产物不被覆盖（mirror local_vision 边界，兼容 260819-aw2-fast 防覆盖守卫）
  2. 合并策略（最长回答 vs 时序拼接）在 ep01 小样本 spike 上 A/B 对比后锁定，结论记录在案——Q3 27B 帧序列动作描述质量有实证而非假设（research Pitfall 3）
  3. 带 `audio_semantic.json` 的集上 ear 融合可见生效（雨声→scene=雨天、脚步声→动作链补「走近」一类修正）；`--no-ear` 跳过后输出与不带 ear 版本一致（additive、可跳过）
  4. 重复运行幂等：per-shot cache 命中不重复烧 GPU（重跑秒级完成）；全程逐帧 `observe_single`，零新引擎、零新模型下载

**Plans**: 3 plans

Plans:
**Wave 1**

- [ ] 19-01-PLAN.md — qwen_eye_client 扩展（observe_pair/ask_text + shape 测试）+ `analysis/vision_seq_facets.py` v2 模块（均匀 ≤8 帧/相邻帧对问/RAW-answer 双信封 cache/ear 白名单注入/只填空缺）+ 离线单测矩阵（全离线零 GPU）

**Wave 2** *(blocked on 19-01)*

- [ ] 19-02-PLAN.md — ep01 spike：sandbox 置空副本双跑（no-ear 6 镜 + ear 3 镜，tmux 后台 + cache 断点续跑）→ 三策略产物 + 客观指标 + ear diff → spike report DRAFT → Kai 盲评 checkpoint 锁合并策略 + 定稿

**Wave 3** *(blocked on 19-01 + 19-02)*

- [ ] 19-03-PLAN.md — run_pipeline 无编号 pre-step 5.6 挂载（--vision-seq/--no-vision-seq/--no-ear，plain-label banner）+ wiring 四件套测试 + SC1/SC4 集成证据（sandbox 填充 diff + live prompts.json sha 不变负测试 + 秒级重跑实测）

### Phase 20: h3 复现客户端

**Goal**: kst 侧 ComfyUI 直连客户端把每镜 (首帧, 尾帧, prompt) 用 MiniMax H3 fl2va 复现成 regen mp4——per-shot 4-tuple cache + 断点续跑 + VRAM guard + 串行编排，让 8-13h/集 的批量渲染可管理、不撞 OOM（不经 kmc/hermes runtime，不经 subagent）。
**Depends on**: Phase 18（`[roundtrip]` warnings 通道 + regen video ref 约定 + byte-identical-absent 红线是客户端的写入目标）
**Requirements**: REGEN-01, REGEN-02, REGEN-03, REGEN-04
**Success Criteria** (what must be TRUE):

  1. `analysis/roundtrip/` 客户端对 ep01 `--sample-shots 20` 提交 fl2va workflow（shift_video=12.0 / cfg=1.0 / euler+simple / length 17k+5 对齐），每镜回收 regen mp4；中断后重跑只补缺失镜（cache-hit 不重渲）——直接 API 提交+轮询，不经 subagent（p11b Pitfall 7）
  2. VRAM guard 生效：TTS 服务器（VoiceDesign :5111 / IndexTTS :5110）占用时先 kill + `POST /free`；剩余显存 <22GB 拒绝提交并记 `[roundtrip]` warning（不撞 OOM / 黑屏）
  3. qwen-eye（13.4GB lease）与 h3 批串行编排：eye 批跑完释放后 h3 才提交——同卡不互踩（research Pitfall 1）
  4. per-shot 4-tuple cache（video_content_hash + engine_name + engine_version + prompt_version，mirror WR-04）：prompt_version 变化后旧 cache 失效重渲；`--force` 清单扩展清 regen cache
  5. >10s 长镜按配置跳过（跳过清单可查）+ `--regen-resolution` 降分辨率验证模式可用

**Plans**: TBD

### Phase 21: Scorer + 阈值校准

**Goal**: 双信号打分——中段帧 CLIP/SigLIP 轨迹相似度（便宜信号）+ VLM judge 归因（区分 prompt 好/h3 不行 vs prompt 欠约束）——在 ep01 ≤20 镜抽样上实测分布、锁定 accepted 双门槛，verdict 写入 schema 合法的 `roundtrip.json`，rejected 永不删除。
**Depends on**: Phase 18（schema gate 是 verdict 写入的校验目标）+ Phase 20（regen mp4 是打分对象）；judge 复用 qwen-eye——与 h3 批串行（复用 Phase 20 编排约定）
**Requirements**: SCORE-01, SCORE-02, SCORE-03, DATASET-01
**Success Criteria** (what must be TRUE):

  1. 对抽样 regen 镜跑 scorer：每镜产出 `scores{midframe_sim, judge}`，`roundtrip.json` 条目过 Phase 18 schema gate（含 verdict + attribution + reason）
  2. midframe 相似度显式只用 25%-75% 时窗帧——t=0/t=end 被 fl2va condition 无信息量，排除在打分外（打分帧清单可审计，research Pitfall 4）
  3. judge 归因三分类（`prompt_faithful` / `model_diverged` / `prompt_underspecified`）以结构化输出产出（glm-structured-output 模式），ep01 抽样上有人工抽检一致的示例——归因不是信口开河
  4. ep01 ≤20 镜双信号分布实测 → accepted 双门槛锁定 + 决策记录进 PROJECT.md Key Decisions；rejected 占比被记录且可审计（防数据集静默偏向简单动作，research Pitfall 5）
  5. verdict 合并幂等：重跑不丢 rejected（hard negatives + h3 能力边界测绘数据永续保留）

**Plans**: TBD

### Phase 22: Dataset Export + Integration

**Goal**: 闭环进流水线（`step_roundtrip` slot + CLI flags）+ gallery round-trip HITL 审阅面板 + accepted 子集独立 dataset 目录导出——用户对 ep01 跑一次抽样流水线即端到端拿到 (首帧, 尾帧, prompt) 真值数据集。
**Depends on**: Phase 18（schema/warnings）+ Phase 20（regen mp4 + flags）+ Phase 21（verdict/scores）（Phase 19 独立、不阻塞本 phase；全流水线 e2e 时 ep01 自然带上 v2 facets）
**Requirements**: RT-05, DATASET-02, PIPE-01, PIPE-02, PRESENT-01
**Success Criteria** (what must be TRUE):

  1. `step_roundtrip` 进 run_pipeline（slot 精确位置本 phase 定）+ CLI flags（`--skip-roundtrip` / `--comfyui-url` / `--sample-shots` / `--regen-resolution` 等）+ banner 重编号 + `--force` 缓存清单扩展；ep01 抽样端到端一次跑出 roundtrip.json + regen mp4 + dataset 目录
  2. gallery round-trip 审阅面板：原片段 vs 重生成片段并排播放 + 双分数 + 归因标签 + accept/reject 按钮（HITL 复核硬门，mirror registry/speaker review 先例），复核结果可导出回写
  3. XSS `_esc()` hardening 覆盖 verdict / reason / attribution 全部模型产出文本（新 attack surface），注入用例（`<script>` / `onerror=` / base64）不执行
  4. accepted 子集导出独立 `dataset/<video-stem>/`：per-shot 首帧/尾帧 jpg + prompt.json + manifest（scores / attribution / 引擎版本 / prompt 快照）+ accepted/rejected 分清单（hard-negative 索引）——消费端不依赖 asset 契约可直接取用
  5. smoke 回归 harness ≥4 场景全绿：ComfyUI down（byte-identical-absent degrade）/ cache-hit 断点续跑 / 抽样模式 / VRAM-guard 拒提交（mirror v1.2 Phase 14 模式）

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
v1.3 phases execute in numeric order: 18 → 19 → 20 → 21 → 22
（Phase 19 对 18 无硬依赖，二者可并行规划；20 依赖 18；21 依赖 18+20；22 依赖 18+20+21）

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | v1.0 | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | v1.0 | 2/2 | Complete | 2026-07-20 |
| 3. Canvas Consumer | v1.0 | 1/1 | Complete | 2026-07-21 |
| 4. Cross-Repo Contract Verification | v1.0 | 2/2 | Complete | 2026-07-21 |
| 5. Contract v1.1 | v1.1 | 4/4 | Complete | 2026-07-24 |
| 6. Cinematography Auto-Fill (`step_semantic`) | v1.1 | 3/3 | Complete | 2026-07-24 |
| 7. Cross-Shot Re-ID Registry + HITL Review (`step_reid`) | v1.1 | 4/4 | Complete | 2026-07-25 |
| 8. Prompt Reference System + shot-timeline HTML Gallery | v1.1 | 3/3 | Complete | 2026-07-25 |
| 9. Canvas Consumer Integration | v1.1 | 2/2 | Complete | 2026-07-25 |
| 10. Risk-Validation Spike + Route Stub | v1.2 | 6/6 | Complete | 2026-07-25 |
| 11. Contract v1.2 | v1.2 | 3/3 | Complete | 2026-07-25 |
| 12. Producer Route Client | v1.2 | 2/2 | Complete | 2026-07-25 |
| 13. SPEAKER-01 Linkage HITL | v1.2 | 3/3 | Complete | 2026-07-25 |
| 14. Pipeline Integration | v1.2 | 2/2 | Complete | 2026-07-26 |
| 15. Layered Reproduction Prompts | v1.2 | 2/2 | Complete | 2026-07-26 |
| 16. HTML Gallery | v1.2 | 1/1 | Complete | 2026-07-26 |
| 17. Canvas Consumer | v1.2 | 1/1 | Complete | 2026-07-26 |
| 18. Contract v1.3 | v1.3 | 3/3 | Complete    | 2026-08-19 |
| 19. qwen-eye v2 看片段 | v1.3 | 0/TBD | Not started | - |
| 20. h3 复现客户端 | v1.3 | 0/TBD | Not started | - |
| 21. Scorer + 阈值校准 | v1.3 | 0/TBD | Not started | - |
| 22. Dataset Export + Integration | v1.3 | 0/TBD | Not started | - |
