# Milestone v1.2 Requirements — 音频语义深化 (Audio Semantic Deepening)

**Goal:** 把音频从「能量/频谱启发式」升级为带对白情绪+说话人、BGM 乐器/调性/氛围/出现时间、音效描述的三模态语义资产，并产出分层复现 prompt（TTS / music-gen / foley）——镜像 v1.1 `step_semantic` 的「thin 客户端 → kais-aigc-platform 路由」模式。

**Locked decisions (user-approved):**
1. 引擎放 kais-aigc-platform（路由式，shot-timeline 零 ML 依赖）
2. 三模态一起（对白/音乐/音效）
3. 分层复现 prompt（TTS / music-gen / foley）
4. schema 1.1→1.2 additive optional（byte-identical-absent）
5. SPEAKER-01 进 scope
6. spike gen_audio_prompts.py 退役为 --offline fallback
7. 复现 prompt = **model-agnostic NL**（不内嵌 NC 权重；用户拿 prompt 喂自选生成器）—— dissolves license BLOCKER
8. **CUDA 12.8 升级 + WhisperX**（词级时间戳进 scope，Phase 1 drift 阈值决定 ship/defer）

**Reference:** `.planning/research/SUMMARY.md` (+ STACK/FEATURES/ARCHITECTURE/PITFALLS).

---

## v1.2 Requirements

### CONTRACT — 契约层（schema 1.1→1.2，纯增量）
- [ ] **CONTRACT-01**: `audio_semantic.json` sidecar schema — per-shot 三模态 (dialogue/music/sfx) + reproduction prompts；additive optional；`audio_analysis.json`/`transcript.json`/`prompts.json` **一字节不动**（byte-identical-absent 红线）
- [ ] **CONTRACT-02**: `speakers.json` sidecar schema (`spk_NNN → char_NNN|null`, `review_state`) + `speaker-edits.schema.json` (HITL round-trip, mirror registry-edits)
- [ ] **CONTRACT-03**: `SCHEMA_VERSION = "1.2"` producer-locked 单源；`validate.py` 三阶 shape gate (MINIMAL/V11/V12)；`verify_contract.py` v1.1↔v1.2 bidirectional cross-version + fixture-consistency
- [ ] **CONTRACT-04**: SPEC §4 (changelog 1.1→1.2) + §5 新增 audio_semantic / speakers 形状 + `fidelity_disclaimer` 文档
- [ ] **CONTRACT-05**: graceful-degrade —— 路由不可达/条件字段模型不达标 → sidecar 缺省（与 v1.0/v1.1 byte-identical）/ 字段 nullable；资产仍导出；`generator.warnings` 记原因

### ROUTE — kais-aigc-platform 引擎（跨仓库）
- [x] **ROUTE-01**: `audio-analysis` 路由 stub（envelope 镜像 shot-analysis `{"code":200,"data":{...}}`）—— 让 producer 客户端有 target URL + envelope，即使模型未加载也能集成测试
- [ ] **ROUTE-02**: 路由托管 SenseVoice (SER+events) + WhisperX (transcribe+align+diarize) + MERT/librosa/PANNs (MIR)；**CUDA 12.8 升级是 Phase 1 前置**（WhisperX 硬需）
- [ ] **ROUTE-03**: 路由 request/response 契约文档化（per-shot 输入：vocals→SER/diarize，drums+bass+other→MIR；输出：dialogue/music/sfx 子对象）

### DIALOGUE — 对白支路
- [ ] **DIA-01**: 段级对白（shot 对齐，enrich 现有 transcript 语义层）— *table-stakes*
- [ ] **DIA-02**: 说话人分离（pyannote via WhisperX integrated diarize）→ 每段 `spk_NNN` — *table-stakes*
- [ ] **DIA-03**: `speaker_id → character_id` HITL 映射（见 SPEAKER）— *table-stakes*
- [ ] **DIA-04**: 对白情绪（SenseVoice 7 emotions + VA）— *CONDITIONAL：Phase 1 SER macro-F1 ≥50% ship / <40% defer v1.3 / 40-50% ship nullable+confidence* — **Phase 10 resolved → ship-nullable+confidence** (PROJECT.md Key Decisions Row 3; implementation pending Phase 15)
- [ ] **DIA-05**: 词级时间戳（WhisperX wav2vec2 align）— *CONDITIONAL：Phase 1 <200ms drift on ≥80% segments ship experimental / 否则段级 only（用户已选 WhisperX 路线）* — **Phase 10 resolved → ship-experimental** (PROJECT.md Key Decisions Row 5; implementation pending Phase 15)

### SPEAKER — 说话人↔角色（关闭 v1.1 SPEAKER-01 deferral）
- [ ] **SPEAKER-01**: 新 `^spk_[0-9]{3}$` 声学 ID 空间（**不**复用 `^char_[0-9]{3}$`，避免身份信号混淆）；`speakers.json` canonical sidecar；`char_id` nullable（旁白/群杂）
- [ ] **SPEAKER-02**: HITL review HTML (`html/gen_speaker_review.py`) + confirmed-only 硬门 apply (`registry/link_speakers.py`，镜像 `apply_edits.py`，idempotent)；拒绝全自动映射（AF-05）
- [ ] **SPEAKER-03**: producer registry integrity assert 扩展 speakers（镜像 v1.1 `_producer_registry_integrity`，additive + gated on file existence）

### MUSIC — 音乐/BGM 支路
- [ ] **MUS-01**: BGM 出现/消失分段（in/out/fade）— *table-stakes*
- [ ] **MUS-02**: BGM tempo (BPM) — *table-stakes*
- [ ] **MUS-03**: BGM 离散 mood 标签 — *table-stakes*
- [ ] **MUS-04**: 多标签乐器识别（含民族：erhu/pipa/guzheng/dizi）— *CONDITIONAL：Phase 1 mAP ≥0.30 ship / <0.20 defer / 0.20-0.30 ship nullable+confidence；MERT vs PANNs 对决 defer 到 Phase 1* — **Phase 10 resolved → DEFER to v1.3** (PROJECT.md Key Decisions Row 4; instruments field omitted from v1.2 schema)
- [ ] **MUS-05**: BGM 调性 (key) — *differentiator*
- [ ] **MUS-06**: VA 情绪回归（arousal ship，valence experimental）— *differentiator*

### SFX — 音效支路
- [ ] **SFX-01**: per-shot foley/sfx 描述（含 SenseVoice 8 audio-event tags）— *table-stakes*
- [ ] **SFX-02**: foley 时间戳 + AudioSet taxonomy (PANNs) — *differentiator*
- [ ] **SFX-03**: foley 复合事件序列 — *differentiator*

### PROMPT — 分层复现 prompt
- [ ] **PROMPT-01**: per-shot 分层复现 prompt `reproduction.{tts, music_gen, foley}`，**model-agnostic NL**，in-place 在 `audio_semantic.json#shots[].reproduction` — *table-stakes*
- [ ] **PROMPT-02**: 每 prompt 字段 `nullable + confidence` + `fidelity_disclaimer`（AF-01 缓解：复现 ≠ 复原，TTS~70%/music~60-75%/foley~80%）— *table-stakes*
- [ ] **PROMPT-03**: spike `audio/gen_audio_prompts.py` 晋升为 pipeline producer（输入 audio_semantic.json，输出 in-place reproduction），`--offline` fallback（路由不可达降级为启发式）— *table-stakes；retires spike per locked decision #6*

### PIPELINE — 流水线集成
- [ ] **PIPE-01**: `step_audio_semantic` 流水线 slot 7（step_reid 与 step_timeline 之间）；`[N/8]→[N/9]` 重编号（17 banner instances）；CLI flags (`--skip-audio-semantic`/`--audio-url`/`--audio-timeout`/`--offline`)；`--force` 缓存清单扩展
- [ ] **PIPE-02**: per-shot cache（4-tuple key: video_content_hash/route_name/route_version/+shot_id 隐含于文件名）+ poisoned-cache invalidation + read-merge-write `[audio]` warnings sidecar
- [ ] **PIPE-03**: `scripts/verify_phase_audio_smoke.py` 5-scenario 回归（route-up/down/cache-hit-offline/条件字段-defer/stub-only）

### PRESENT — shot-timeline HTML 展示
- [ ] **PRESENT-01**: `gen_timeline_html.py` 扩展 `--audio-semantic`/`--speakers`；per-shot 对白/音乐/音效 chips + speaker→character chip + 复现 prompt 面板（"estimated" 标签）+ XSS `_esc()` hardening（layered-prompt HTML 是新 attack surface）

### CONSUMER — canvas 消费者（跨仓库，可 defer）
- [ ] **CONSUMER-01**: `@kais/infinite-canvas` 识别 `schema_version:"1.2"`；§7 post-process 每 shot emit 1 dialogue + 1 music + 1 sfx `type:"asset"` 子节点；typeIcons cosmetic（💬/🎵/🔊）；**无 custom renderer / 无 Zod bump**（跨仓库 kais-aigc-platform `feat/canvas-asset-collection`）；3-mode verify_contract.py v1.2 GREEN

---

## Future Requirements (deferred)

- **DIA-06**: face-voice 自动 speaker→character 启发式（v1.3 differentiator；v1.2 永远 HITL 兜底）
- **MUS-07**: BGM staff/MIDI 转写（AF-10 边界，未来）
- **full V/A regression**：valence 成熟后从 experimental 升 SLA（v1.3）
- **cross-video audio continuity**：同一 BGM 主题/同说话人跨片识别（v2，类比 cross-video character continuity）

## Out of Scope

- **AF-01 完美复刻原音频** — 复现 prompt ≠ 精确复原（TTS~70%/music~60-75%/foley~80%）；README/SPEC 不得出现 "perfectly reconstruct"/"exact restoration"；每字段带 confidence + fidelity_disclaimer
- **AF-02 强制每镜都有情绪** / **AF-03 强制每镜都有乐器** — 模型不达标时 nullable，不伪造
- **AF-05 全自动 speaker→character 映射** — 必须 HITL（吸取 v1.1 re-id 教训）
- **AF-06 producer 内本地 ML fallback** — shot-timeline 保持零 ML 依赖；路由不可达走 sidecar-absent degrade，不在 producer 内跑模型（spike 启发式仅作 reproduction 的 --offline 文本降级，非分析降级）
- **AF-07 重训模型** / **AF-08 精确同步复现** / **AF-09 词级 <50ms 保证** — 不现实承诺
- **画布内原生音频渲染器**（波形/stem 播放引擎）— 仍是后续 milestone；v1.2 只加语义数据 + 结构化 asset 节点
- **内嵌 NC 权重生成器**（Stable Audio Open/AudioLDM2/F5-TTS）— v1.2 只产 model-agnostic NL prompt，不绑死/不分发 NC 权重（locked decision #7）

---

## Traceability

Each v1.2 REQ-ID maps to exactly one phase. Coverage: 33/33 (100%).

| REQ-ID | Phase | Status |
|--------|-------|--------|
| CONTRACT-01 | Phase 11 (Contract v1.2) | Pending |
| CONTRACT-02 | Phase 11 (Contract v1.2) | Pending |
| CONTRACT-03 | Phase 11 (Contract v1.2) | Pending |
| CONTRACT-04 | Phase 11 (Contract v1.2) | Pending |
| CONTRACT-05 | Phase 11 (Contract v1.2) | Pending |
| ROUTE-01 | Phase 10 (Risk-Validation Spike + Route Stub) | Complete |
| ROUTE-02 | Phase 12 (Producer Route Client) | Pending |
| ROUTE-03 | Phase 12 (Producer Route Client) | Pending |
| DIA-01 | Phase 15 (Layered Reproduction Prompts) | Pending |
| DIA-02 | Phase 13 (SPEAKER-01 Linkage HITL) | Pending |
| DIA-03 | Phase 13 (SPEAKER-01 Linkage HITL) | Pending |
| DIA-04 | Phase 15 (Layered Reproduction Prompts) — *CONDITIONAL on Phase 10 SER macro-F1* | Phase 10 resolved (ship-nullable+confidence); Phase 15 implementation pending |
| DIA-05 | Phase 15 (Layered Reproduction Prompts) — *CONDITIONAL on Phase 10 WhisperX drift* | Phase 10 resolved (ship-experimental); Phase 15 implementation pending |
| SPEAKER-01 | Phase 13 (SPEAKER-01 Linkage HITL) | Pending |
| SPEAKER-02 | Phase 13 (SPEAKER-01 Linkage HITL) | Pending |
| SPEAKER-03 | Phase 13 (SPEAKER-01 Linkage HITL) | Pending |
| MUS-01 | Phase 15 (Layered Reproduction Prompts) | Pending |
| MUS-02 | Phase 15 (Layered Reproduction Prompts) | Pending |
| MUS-03 | Phase 15 (Layered Reproduction Prompts) | Pending |
| MUS-04 | Phase 15 (Layered Reproduction Prompts) — *CONDITIONAL on Phase 10 mAP* | Phase 10 resolved (DEFER v1.3); instruments field omitted from v1.2 schema |
| MUS-05 | Phase 15 (Layered Reproduction Prompts) | Pending |
| MUS-06 | Phase 15 (Layered Reproduction Prompts) | Pending |
| SFX-01 | Phase 15 (Layered Reproduction Prompts) | Pending |
| SFX-02 | Phase 15 (Layered Reproduction Prompts) | Pending |
| SFX-03 | Phase 15 (Layered Reproduction Prompts) | Pending |
| PROMPT-01 | Phase 15 (Layered Reproduction Prompts) | Pending |
| PROMPT-02 | Phase 15 (Layered Reproduction Prompts) | Pending |
| PROMPT-03 | Phase 15 (Layered Reproduction Prompts) | Pending |
| PIPE-01 | Phase 14 (Pipeline Integration) | Pending |
| PIPE-02 | Phase 12 (Producer Route Client) | Pending |
| PIPE-03 | Phase 14 (Pipeline Integration) | Pending |
| PRESENT-01 | Phase 16 (HTML Gallery) | Pending |
| CONSUMER-01 | Phase 17 (Canvas Consumer) | Pending |

**Phase coverage summary:**

| Phase | Requirements | Count |
|-------|--------------|-------|
| 10. Risk-Validation Spike + Route Stub | ROUTE-01 (+ de-risks DIA-04/DIA-05/MUS-04) | 1 |
| 11. Contract v1.2 | CONTRACT-01..05 | 5 |
| 12. Producer Route Client | ROUTE-02, ROUTE-03, PIPE-02 | 3 |
| 13. SPEAKER-01 Linkage HITL | SPEAKER-01..03, DIA-02, DIA-03 | 5 |
| 14. Pipeline Integration | PIPE-01, PIPE-03 | 2 |
| 15. Layered Reproduction Prompts | PROMPT-01..03, DIA-01, DIA-04, DIA-05, MUS-01..06, SFX-01..03 | 15 |
| 16. HTML Gallery | PRESENT-01 | 1 |
| 17. Canvas Consumer | CONSUMER-01 | 1 |
| **Total** | | **33** |
