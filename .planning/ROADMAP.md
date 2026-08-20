# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 分镜语义深化** — Phases 5-9 (shipped 2026-07-25) — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump 1→1.1 + 双端展示 — [archived](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 音频语义深化** — Phases 10-17 (shipped 2026-07-26) — route-based 三模态音频语义（对白/音乐/音效）+ 分层复现 prompt (TTS/music-gen/foley) + 说话人↔角色 HITL + 契约 minor bump 1.1→1.2 + 双端展示 — [archived](milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Round-trip Validation** — Phases 18-22 (shipped 2026-08-20) — qwen-eye v2 看片段逆推 → h3 fl2va 复现 → 中段帧打分 + 归因 → accepted 数据集导出；契约 minor bump 1.2→1.3 — [archived](milestones/v1.3-ROADMAP.md)

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

<details>
<summary>✅ v1.3 Round-trip Validation (Phases 18-22) — SHIPPED 2026-08-20</summary>

**Milestone Goal:** 用「qwen-eye 看片段逆推 prompt → h3 fl2va 首尾帧复现 → 中段帧打分 + VLM judge 归因」的闭环，把 prompts.json 从「看起来合理」升级为「经复现验证的可信真值」，产出 (首帧, 尾帧, prompt) 高价值数据集 —— rejection sampling 造 SFT 真值。

Round-trip closes the loop the first three milestones opened: qwen-eye v2 watches shot frame-sequences to upgrade action/camera facets (v1.2 `audio_semantic` as ear), a new ComfyUI-direct client regenerates each shot from (首帧, 尾帧, prompt) via MiniMax H3 fl2va, a dual-signal scorer (mid-frame CLIP/SigLIP trajectory + VLM judge attribution) validates the round-trip on an ep01 ≤20-shot sample, and accepted triples export as an independent SFT-grade dataset directory. Schema bump `1.2 → 1.3` pure-additive. Ordering constraints from research: **契约先行** (contract before any round-trip code writes), **抽样先行** (≤20 shots calibrate thresholds before overnight 8-13h full runs), **VRAM 串行编排** (qwen-eye 13.4GB lease and h3 batch never co-resident on the 3090).

- [x] **Phase 18: Contract v1.3** — `roundtrip.schema.json` sidecar + `SCHEMA_VERSION="1.3"` + fixture/validate gate + SPEC + graceful-degrade 契约层（mirror v1.2 三层门） (completed 2026-08-19)
- [x] **Phase 19: qwen-eye v2 看片段** — 每镜 ≤8 帧逐帧 `observe_single` 问答升级 action/camera facet + audio_semantic ear 融合（合并策略 ep01 spike 后锁定） (completed 2026-08-19)
- [x] **Phase 20: h3 复现客户端** — kst 直连 ComfyUI 提交 MiniMax H3 fl2va workflow + per-shot 4-tuple cache + 断点续跑 + VRAM guard（TTS kill + `/free` + eye↔h3 串行编排） (completed 2026-08-20)
- [x] **Phase 21: Scorer + 阈值校准** — 中段帧 CLIP/SigLIP 轨迹相似度 + VLM judge 归因三分类 + ep01 ≤20 镜实测分布锁 accepted 双门槛 + verdict 写 `roundtrip.json`（rejected 永不删除） (completed 2026-08-20)
- [x] **Phase 22: Dataset Export + Integration** — `step_roundtrip` 流水线集成 + ≥4 场景 smoke 回归 + gallery round-trip HITL 审阅面板 + accepted 子集独立 dataset 目录导出 (completed 2026-08-20)

**Audit:** 19/19 requirements satisfied, 5/5 phases verified, 20/22 integration wiring（B1 已修、B2 数据层溯源缺口经 Kai 裁决接受，自愈路径在案）— [v1.3-MILESTONE-AUDIT.md](milestones/v1.3-MILESTONE-AUDIT.md)

**Full phase details:** [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)

</details>
