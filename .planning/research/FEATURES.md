# Feature Research — v1.2 音频语义深化

**Domain:** 三模态音频语义分析（对白 / 音乐 / 音效）+ 分层复现 prompt（TTS / music-gen / foley），路由式架构，针对中文动画成片（如《小江湖》——中文对白 + synth+folk+orchestral BGM 混合体）。
**Researched:** 2026-07-25
**Confidence:** MEDIUM（核心方法学 HIGH；中文跨域精度数据 LOW — 需 Phase 1 risk-validation 取证）

> 本文件聚焦 PROJECT.md 已锁的 v1.2 scope。架构/技术栈细节见 STACK.md（sibling），陷阱见 PITFALLS.md（sibling）。本文件只回答："每模态通常怎么工作、真实保真上限、如何分组为 table-stakes / differentiator / anti-feature、与现有 shot grid + Demucs stems 的依赖关系"。

---

## 诚实保真上限（先看这张表）

**这是最重要的节。复现 prompt ≠ 复刻原音频。** 路由式分析给出"够用的反向配料表"，不是无损还原。下表是 Phase 1 risk-validation 必须验证的真实预期（取中位数，非最佳 demo 数字）。

| Modality / 子能力 | 输入源 | 路由模型 | 实测预期保真（中文动画成片） | 字段用途 | Phase 1 必须 spike? |
|---|---|---|---|---|---|
| **词级时间戳** (WhisperX) | vocals stem | WhisperX + wav2vec2 align | 段级准（~80-150ms 偏差）；**词级在中文上 unreliable**（已知 issue #1220/#1247，char 不在 dict 时漂移） | 字幕 sync、TTS 节奏提示 | **YES（最高优先）** |
| **说话人分离** (speaker turn) | vocals stem | pyannote 3.1 | DER ~15-20%（开源 3.1 on broadcast；纯对白 vocals 上 8-12%） | speaker_id 字段 | YES |
| **说话人 → 角色映射** | speaker_id + v1.1 character registry | 无模型，HITL-only | ~100%（人工） / ~50-70%（face-voice 启发式） | `speaker_map.json` | NO（用 HITL） |
| **对白情绪分类** (discrete, 5-6 class) | vocals stem | emotion2vec+ large | **跨域 ~45-60%**（in-corpus CASIA ~75-85%；spontaneous 动画对白 drop 显著） | emotion tag | **YES（最高风险）** |
| **对白 V/A 回归** | vocals stem | emotion2vec / wav2vec2 + head | arousal 可 (~0.6-0.7 CCC)，valence 不可 (~0.2-0.3 CCC) | v/a scores | NO（anti-feature） |
| **BGM 出现 / 边界 / 淡入淡出** | drums+bass+other stem | librosa RMS + effects.split | **可靠**（RMS envelope slope 阈值法，>90% 准） | bgm_segments[] | NO（成熟） |
| **Tempo (BPM)** | drums+bass+other stem | librosa.beat.tempo | ±4% 准确（clean BGM）；~10-20% 八度倍频错误 | tempo_bpm | NO |
| **Key (大调 / 小调 + 主音)** | other stem | librosa chroma + Krumhansl | ~60-70%（commercial 音乐；synth/folk 混合更低） | key | NO（可选） |
| **多标签乐器识别** (西洋) | other stem | MERT finetune / OpenMIC-style | 西洋 ensemble ~mAP 0.4-0.5（piano/strings/guitar/drums） | instruments[] | YES（次要） |
| **多标签乐器识别** (中国民族) | other stem | ChMusic-trained / 通用 MIR | **~mAP 0.15-0.30（高风险）**；erhu/pipa/guzheng/dizi 训练数据稀缺 | instruments[] | **YES（最高风险）** |
| **BGM V/A 情绪** | other stem | MERT + 回归头 | 同 SER：arousal 中等、valence 弱 | mood | NO（用离散标签兜底） |
| **Foley 描述** | other stem（非 BGM / 非对白段） | Qwen-Audio / MTG-AudioSetDocs | ~60-75% 类别（dog bark / door slam / rain）；细粒度（材质、动作序列）~30-50% | sfx_description | YES |
| **TTS prompt 复现度** | speaker_id + text + emotion | （cosyvoice / F5-TTS / GPT-SoVITS） | "feeling" 接近 ~70%；**音色≠原声**（除非用 reference audio） | tts_prompt | NO（prompt-only） |
| **Music-gen prompt 复现度** | mood + genre + tempo + instruments | （MusicGen / Suno） | "风格情绪" 接近 ~60-75%；**旋律/编曲不可能 1:1 复刻** | music_prompt | NO |
| **Foley prompt 复现度** | sfx_description | （AudioGen / ElevenLabs SFX） | 单事件（脚步 / 关门）~80%；环境层 / 复杂事件序列 ~40-60% | foley_prompt | NO |

**Phase 1 risk-validation 取证优先级（如果 Phase 1 时长受限，按序 spike）：**
1. **中文 SER 跨域**（最高风险 — 取一集《小江湖》对白，跑 emotion2vec+ large，肉眼校验 5-6 类离散标签）
2. **多音轨乐器识别**（次高风险 — 同集 BGM，验证西洋/民族乐器分别的 mAP）
3. **词级时间戳中文漂移**（决定是否降级到段级）
4. Foley 描述（如果时间允许）

---

## Feature Landscape

### Table Stakes（用户期望必有的）

> 缺失 = 产品感觉残缺。这些是 v1.2 必交付项；下游 canvas 消费者会直接读这些字段。

| ID | Feature | Why Expected | Complexity | 依赖 | Notes |
|----|---------|--------------|------------|------|-------|
| **DIA-01** | 段级对白时间戳 + 文本 | 当前 transcript.json 已有，但是 faster-whisper segment 级；v1.2 保持兼容（**段级是 baseline**；词级见 differentiator） | LOW | shots.json, transcript.json | 沿用现状，不破坏现有 schema |
| **DIA-02** | 说话人分离（每段打 speaker_id） | 用户已把 SPEAKER-01 列为 v1.2 in-scope；v1.1 曾因"大 lift" defer 到 v1.2 | MEDIUM | vocals stem (Demucs 已有) | pyannote 3.1 + num_speakers hint；输出 `speaker_turns[]` 加进 transcript.json（additive） |
| **DIA-03** | speaker_id → character_id 映射（HITL） | 没映射就没有"真实叙事连贯"；raw speaker_00/01 对消费者无用 | MEDIUM | DIA-02 + v1.1 characters.json | 复用 v1.1 HITL pattern（registry-edits schema 模板）；speaker_map.json sidecar |
| **MUS-01** | BGM 出现 / 不出现分段（per-shot 是否有 BGM） | 当前 `dominant_type` 启发式粗糙（drums+bass > 50%）；用户期待准确"BGM in/out" | LOW | shots.json, drums+bass+other stems | librosa.effects.split + RMS slope；输出 `bgm_segments[]` |
| **MUS-02** | BGM tempo (BPM) per segment | 复现 prompt 必备字段；spike `audio/gen_audio_prompts.py` 已试过 envelope peak-pick | LOW | drums stem | librosa.beat.tempo；置信度 < 阈值时 null |
| **MUS-03** | BGM 离散情绪标签（calm / tense / joyful / sad / epic） | 复现 music-gen prompt 必备；与 SER 同型（discrete labels） | MEDIUM | other stem | emotion2vec+ 在 music 上的迁移 OR MERT + 头；与 DIA-04 共享模型 |
| **SFX-01** | 每镜 foley 描述（NL 字符串） | 当前 dominant_type=sfx 没语义；用户要"什么音效" | MEDIUM | other stem + DIA-02（排除对白段） | Qwen-Audio / AudioSet 多标签；输出 `sfx_description` NL |
| **CONTRACT-01** | `audio_semantic.json` optional sidecar，schema_version `1.1`→`1.2` | 契约 bump 是 milestone 核心机制；纯 additive（与 v1.0/v1.1 缺省 byte-identical） | LOW | v1.1 contract | 新 schema：`audio_semantic.schema.json`；asset.data.audio_semantic 加 optional path |
| **CONTRACT-02** | producer 客户端 `analysis/call_audio_analysis.py`（httpx + per-shot cache + graceful-degrade） | 镜像 v1.1 `step_semantic` 模式；route 不可达 → sidecar 缺省，资产仍导出 | MEDIUM | route (deferred 跨仓库) | ROUTE_NAME/ROUTE_VERSION/cache_key 4-tuple pattern 直接复用 |
| **PROMPT-01** | 每镜 3 套分层 prompt（tts_prompt / music_prompt / foley_prompt） | 用户目标 = 复现音频，单一 NL prompt 服务不了任何生成器 | MEDIUM | DIA-04, MUS-02/03, SFX-01 | spike `gen_audio_prompts.py` 退役；新 `analysis/build_layered_prompts.py` |
| **DEGRAD-01** | 路由不可达时 graceful-degrade（schema 合法的空字段 + generator.warnings） | v1.1 已建立的 pattern；用户期待"producer 永远能 ship" | LOW | CONTRACT-02 | 复用 call_shot_analysis.py 的 preflight + cache-stale 标记 |
| **PIPE-01** | `run_pipeline.py` 加 `step_audio_semantic`（slot 7 of 9） | step_reid 是 slot 6 of 8；新 step 在 step_transcribe 之后、step_timeline 之前 | LOW | CONTRACT-02 | 沿用 4 flag pattern（--skip-audio-semantic / --offline / --analysis-url / --analysis-timeout） |

### Differentiators（竞争优势）

> v1.1 没有的，且显著提升复现管线价值。**非必须 ship，但任一交付都会让 milestone 突出**。

| ID | Feature | Value Proposition | Complexity | 依赖 | Notes |
|----|---------|-------------------|------------|------|-------|
| **DIA-04** | 对白情绪分类（5-6 类 Ekman-lite 离散标签） | 下游 TTS prompt 直接用；当前完全无情绪信息 | HIGH（中文跨域风险） | DIA-01, vocals stem | emotion2vec+ large；**Phase 1 必验**（~45-60% 跨域精度是 honest ceiling） |
| **DIA-05** | 词级时间戳（WhisperX） | TTS 节奏对齐 / 字幕精确同步；段级在长段中不够细 | MEDIUM（中文 unreliable） | DIA-01 | **Phase 1 必验**；若 char dict 漂移严重，降级到段级 + 把词级标 "experimental" |
| **DIA-06** | 说话人 → 角色 face-voice 自动启发式（active-speaker + v1.1 character registry） | 全自动 HITL 替代；视频有人脸时可靠 | HIGH | DIA-02, v1.1 characters.json + faces | 跨 modal re-id；可选 defer 到 v1.3（HITL 兜底先 ship） |
| **MUS-04** | 多标签乐器识别（per-BGM-segment，西洋 + 民族） | music-gen prompt 必备（"piano + strings" vs "erhu + dizi"） | HIGH（民族乐器高风险） | other stem | ChMusic / MTG-Medley 训练；**Phase 1 必验**（民族乐器 mAP 可能 <0.3 → 决定字段是否标 `confidence`） |
| **MUS-05** | BGM key（大调 / 小调 + 主音） | music-gen prompt 进阶字段；非必须但有价值 | MEDIUM | other stem | librosa chroma + Krumhansl；置信度低时 null |
| **MUS-06** | BGM V/A 回归（arousal + valence 连续值） | 与离散标签互补；适合情绪曲线可视化 | HIGH（valence 不可靠） | other stem | arousal ship；valence 标 experimental OR drop |
| **SFX-02** | Foley 时间戳 + 分类（AudioSet 本体） | 精确复现需要"sfx 何时发生"；不止每镜一个描述 | MEDIUM | SFX-01 | AudioSet 527 类标签 + 时间段；与 music 分段冲突时优先 music |
| **SFX-03** | Foley 复杂事件序列（NL：先 X 后 Y 再 Z） | 单镜多事件（如"开门→脚步→放下杯子"）更贴近生成器期望 | MEDIUM | SFX-01 | ElevenLabs SFX prompt pattern；输出按时间排序的事件列表 |
| **CONSUMER-01** | canvas 侧 audio_semantic 节点（跨仓库 kais-aigc-platform） | 用户端到端可见；v1.1 已建 character/prop 节点 pattern | MEDIUM | CONTRACT-01 | structuralTypes 透传 + §7 post-process；无 custom renderer |
| **PROMPT-02** | TTS prompt 含 reference audio 引用（指向 vocals stem 时间段） | 真实复现音色需要 reference；纯文本 prompt 复不出原声 | LOW | DIA-02 | tts_prompt = {speaker_id, text, emotion, ref_start, ref_end} |
| **PROMPT-03** | Music-gen prompt 含结构 tag（[Intro]/[Verse]/[Chorus]） | Suno/MusicGen 对结构 tag 响应强 | LOW | MUS-01 | 每 BGM segment 转 [PartN] tag |

### Anti-Features（**明确不做**）

> 这些"看似高级但实际有害"。v1.2 必须在 Out of Scope 明确拒绝，防止 scope creep。

| Anti-Feature | Why Requested（surface appeal） | Why Problematic | What to Do Instead |
|--------------|--------------------------------|-----------------|-------------------|
| **AF-01 完美复刻原音频**（"restoration grade"） | 用户期待"反推 → 还原 → 与原片同步对比" | **生成器根本做不到**：TTS 复不出原声纹；MusicGen 复不出原旋律；AudioGen 复不出原混音。Promise 这个 = 必然失望 | **诚实定位为"复现配料表"**：每 prompt 字段标 expected_fidelity；PROMPT-02 给 reference audio 兜底音色 |
| **AF-02 强制每镜都有 emotion tag** | 一致性 / 字段 always filled | 跨域精度 ~50% 时，强行填 = 50% 错标签 → 误导下游 TTS（"angry" 实际是 neutral） | emotion 字段 nullable + `emotion_confidence`；< 阈值时 null + warning |
| **AF-03 强制每镜都有乐器列表** | 同上，一致性 | 民族乐器 mAP ~0.2 时，强行填 = 大量错误 → music-gen prompt 误指 | instruments[] 在置信度 < 阈值时 null；标 `instruments_confidence` |
| **AF-04 全 V/A 回归（连续 valence + arousal）** | "更精细 than discrete" | Valence 跨域 CCC ~0.2-0.3 = 几乎随机；hard-coded 给下游是噪声 | 只 ship arousal（中等可靠）+ discrete label；valence 标 `experimental` 或 drop |
| **AF-05 全自动 speaker→character 映射（无人 review）** | "去掉 HITL 的 friction" | 误映射 = 错误角色归属流向 prompt → 角色连贯叙事被破坏（v1.1 re-id 教训） | HITL 是 table-stakes；face-voice 启发式仅作 proposed 候选 |
| **AF-06 路由全本地 fallback 实现** | "路由挂了我自己跑" | 重 ML 依赖（pyannote/emotion2vec/MERT）全进 producer 仓库 = 破坏松耦合 + 多 GB 模型下载 | graceful-degrade 到空字段 + warning；spike `gen_audio_prompts.py`（纯 stdlib）作 `--offline` NL prompt fallback（已锁 v1.2 决策） |
| **AF-07 重训练模型 / 自建中文 SER 数据集** | "提升中文精度" | v1.x 是工程 milestone，不是研究项目；retraining 成本远超 ROI | 用 emotion2vec+ large 预训练 + 接受 honest 跨域精度；Phase 1 取证后决定是否 ship DIA-04 |
| **AF-08 复刻原视频 exact 同步对位** | "下游把 prompt 喂生成器，期望秒级对齐原视频" | 生成器输出长度 ≠ 输入 prompt 暗示长度；TTS 段长漂移 ±20%；music-gen 段长不可控 | prompt 标 _expected_duration + ref audio 段；下游自行重新对齐 |
| **AF-09 词级时间戳保证 < 50ms 精度** | "WhisperX 论文说 sub-100ms" | 中文 char dict 缺失 → 漂移数百毫秒；强制精度 = 必然违约 | 词级字段标 `experimental`；段级是 SLA |
| **AF-10 全 BGM 五线谱 / MIDI 转录** | "更结构化 than prompt" | Spotify Basic-Pitch 在 polyphonic mixed BGM 上误差大；MIDI 输出对 music-gen 无用（gen 模型吃 NL 不吃 MIDI） | 输出 instruments[] + key + tempo 已足够；MIDI 留给下游消费者 |

---

## Feature Dependencies

```
[shots.json] (existing) ────┬─→ DIA-01 段级对白（沿用）
                            ├─→ MUS-01 BGM 出现分段
                            ├─→ SFX-01 Foley 描述
                            └─→ PROMPT-01 分层 prompt（per-shot loop）

[DIA-01 段级对白]──────┬─→ DIA-02 说话人分离（pyannote 3.1）
                       ├─→ DIA-04 对白情绪（emotion2vec+）  ← Phase 1 spike
                       └─→ DIA-05 词级时间戳（WhisperX）     ← Phase 1 spike

[DIA-02 说话人]──────┬─→ DIA-03 speaker→character HITL（依赖 v1.1 characters.json）
                     └─→ DIA-06 face-voice 启发式（v1.3 deferral 候选）

[MUS-01 BGM 分段]──────┬─→ MUS-02 tempo
                       ├─→ MUS-03 BGM 情绪
                       ├─→ MUS-04 乐器识别                    ← Phase 1 spike
                       ├─→ MUS-05 key
                       └─→ MUS-06 V/A 回归

[DIA-04 + MUS-03]──→ 共享 SER/MIR emotion 模型（emotion2vec+ 同时用）

[SFX-01 Foley NL]──→ SFX-02 时间戳分段
                  └─→ SFX-03 复杂事件序列

[DIA-02 + DIA-04 + MUS-02 + MUS-03 + MUS-04 + SFX-01]
                       │
                       └─→ PROMPT-01 分层 prompt（tts/music/foley 三套）
                              │
                              ├─→ PROMPT-02 TTS ref audio 引用（tts_prompt 子字段）
                              └─→ PROMPT-03 music 结构 tag（music_prompt 子字段）

[CONTRACT-01 audio_semantic.json schema]
       │
       ├─→ CONTRACT-02 producer 客户端（httpx + cache + degrade）
       │      │
       │      └─→ PIPE-01 step_audio_semantic slot 7
       │
       └─→ CONSUMER-01 canvas 节点（跨仓库 deferred）
```

### Dependency Notes

- **所有路由源特性都依赖 CONTRACT-02（producer 客户端）**：DIA-02/04/05, MUS-01-06, SFX-01-03 全部走同一路由（`POST /api/v1/production/audio-analysis`），但返回分模态子对象（`dialogue`/`music`/`sfx`）。**单一路由 → 三模态**，简化 cache key。
- **DIA-03 (HITL speaker→character) 依赖 v1.1 characters.json 存在**：若 v1.1 re-id 路由未跑（deferred），characters.json 缺省 → speaker_map.json 仍写 raw speaker_id，HITL UI 提示"先跑 step_reid"。
- **PROMPT-01 依赖几乎所有上游**：分层 prompt 是"汇总层"，必须在 DIA/MUS/SFX 全部就绪后跑。**这是 phase 排序的关键**：PROMPT-01 必须在最后 phase。
- **CONTRACT-01 是 phase 1 lock 的目标**：契约必须先冻结（v1.1 lesson: contract-first sequencing），producer 后写。
- **CONSUMER-01 跨仓库，可能 defer**：graceful-degrade 模式让本仓库 milestone 不被 kais-aigc-platform PR 阻塞。
- **DIA-04 与 MUS-03 共享 emotion 模型**：emotion2vec+ 同时用于 speech 与 music emotion；省一次模型加载。
- **AF-02/AF-03 与 DIA-04/MUS-04 冲突**：若 Phase 1 spike 证明精度不足，**降级方案是 DIA-04/MUS-04 整体 defer 到 v1.3**，留 nullable 字段 + warning。

---

## MVP Definition（v1.2 ship 必备）

### Phase 1 — Risk-Validation Spike（不锁契约，先取证）

- [ ] 路由搭建：`POST /api/v1/production/audio-analysis` 在 kais-aigc-platform 落地（whisperX + pyannote 3.1 + emotion2vec+ + librosa MIR + ChMusic-tuned instrument head）
- [ ] 取一集《小江湖》ep01 跑路由，取证：
  - 中文 SER 跨域精度（5-6 类离散标签，肉眼校验 ≥50% 可接受 / <40% defer DIA-04）
  - 民族乐器识别 mAP（≥0.30 可接受 / <0.20 标 experimental）
  - 词级时间戳中文漂移（≥80% 段词级误差 <200ms 可 ship / 否则只 ship 段级）
  - 端到端延迟 + 显存（决定 GPU 路由是否单实例可服务）

### Phase 2 — Contract v1.2（lock 后冻结）

- [ ] CONTRACT-01 `audio_semantic.schema.json` + `asset.data.audio_semantic` optional path（schema_version `1.1`→`1.2` 纯增量）
- [ ] v1.1↔v1.2 双向 self-test（v1.1 fixture 仍绿；新 fixture 验证 additive）
- [ ] emotion/instruments 字段全部 nullable + confidence 字段（AF-02/03 的 schema 体现）

### Phase 3 — Producer 客户端（不依赖路由上线）

- [ ] CONTRACT-02 `analysis/call_audio_analysis.py`（httpx + per-shot cache + preflight + graceful-degrade；镜像 v1.1 pattern）
- [ ] DEGRAD-01 路由不可达 → audio_semantic.json 缺省 + generator.warnings
- [ ] PIPE-01 step_audio_semantic slot 7 of 9 + 4 CLI flag

### Phase 4 — Dialogue & Music & SFX 分析（路由上线后）

- [ ] DIA-01 段级（沿用）
- [ ] DIA-02 说话人分离
- [ ] DIA-03 HITL speaker→character（speaker_map.json + review HTML，复用 v1.1 pattern）
- [ ] DIA-04 对白情绪（**条件性**：Phase 1 spike 通过则 ship，否则 defer）
- [ ] DIA-05 词级（**条件性**：Phase 1 spike 通过则 ship experimental 标）
- [ ] MUS-01 BGM 分段
- [ ] MUS-02 tempo
- [ ] MUS-03 BGM 情绪
- [ ] MUS-04 乐器识别（**条件性**）
- [ ] SFX-01 Foley 描述

### Phase 5 — 分层 Prompt + Spike 退役

- [ ] PROMPT-01 三套 prompt（tts/music/foley）
- [ ] PROMPT-02 TTS ref audio 引用
- [ ] PROMPT-03 music 结构 tag
- [ ] spike `audio/gen_audio_prompts.py` 降级为 `--offline` fallback（已锁决策）

### Phase 6 — Canvas Consumer Integration（跨仓库，可能 defer）

- [ ] CONSUMER-01 canvas audio_semantic 节点（graceful-degrade 不阻塞本仓库 ship）

### Future（v1.3+）

- [ ] DIA-06 face-voice 自动 speaker→character（依赖 v1.1 character faces + active speaker detection）
- [ ] MUS-05 key（如果 Phase 4 发现用户真需要）
- [ ] MUS-06 V/A arousal-only（如果离散标签不够细）
- [ ] SFX-02 / SFX-03 时间戳 + 事件序列（细分 foley）

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | 备注 |
|---------|------------|---------------------|----------|------|
| CONTRACT-01 audio_semantic schema 1.2 | HIGH | LOW | P1 | v1.1 lesson: contract first |
| CONTRACT-02 producer 客户端 | HIGH | MEDIUM | P1 | 复用 v1.1 模式 |
| DIA-02 说话人分离 | HIGH | MEDIUM | P1 | SPEAKER-01 已 in-scope |
| DIA-03 speaker→char HITL | HIGH | MEDIUM | P1 | 没映射就没用 |
| MUS-01 BGM 分段 | HIGH | LOW | P1 | librosa 成熟 |
| MUS-02 tempo | MEDIUM | LOW | P1 | spike 已试过 envelope |
| PROMPT-01 分层 prompt | HIGH | MEDIUM | P1 | milestone 核心目标 |
| DEGRAD-01 graceful-degrade | HIGH | LOW | P1 | v1.1 已建立 |
| PIPE-01 step_audio_semantic | HIGH | LOW | P1 | 沿用 slot 模式 |
| DIA-04 对白情绪 | HIGH | HIGH | **P1 条件** | Phase 1 spike 决定 |
| MUS-04 乐器识别 | HIGH | HIGH | **P1 条件** | Phase 1 spike 决定 |
| SFX-01 Foley 描述 | MEDIUM | MEDIUM | P1 | 难度低于 DIA-04/MUS-04 |
| DIA-05 词级时间戳 | MEDIUM | MEDIUM | P2 experimental | 中文 unreliable |
| MUS-03 BGM 情绪 | MEDIUM | MEDIUM | P1 | 与 DIA-04 共享模型 |
| PROMPT-02 TTS ref audio | MEDIUM | LOW | P2 | 子字段 |
| PROMPT-03 music 结构 tag | MEDIUM | LOW | P2 | 子字段 |
| CONSUMER-01 canvas 节点 | HIGH | MEDIUM | P1 跨仓库 | 可能 defer |
| MUS-05 key | LOW | MEDIUM | P3 | 用户调研后再定 |
| MUS-06 V/A 回归 | LOW | HIGH | P3 | valence 不可靠 |
| SFX-02/03 时间戳/事件序列 | MEDIUM | MEDIUM | P2/P3 | Phase 5 后再扩 |
| DIA-06 face-voice 自动 | LOW（HITL 兜底） | HIGH | P3 v1.3 | HITL 先 ship |

**P1 (ship-gated)**: CONTRACT-01/02, DIA-02/03, MUS-01/02/03, SFX-01, PROMPT-01, DEGRAD-01, PIPE-01, CONSUMER-01（可 defer）
**P1 条件**: DIA-04, MUS-04 (Phase 1 spike pass → ship; fail → defer to v1.3)
**P2 (可选 ship)**: DIA-05, PROMPT-02, PROMPT-03, SFX-02
**P3 (defer)**: MUS-05/06, DIA-06, SFX-03

---

## 中文动画成片（《小江湖》-style）特有风险

> 路由式架构让 v1.2 与 v1.1 共享"中文跨域"风险模式。下面是 Phase 1 必须取证的具体失败模式。

| 风险 | 触发场景 | 实测影响 | 缓解 |
|-----|---------|---------|------|
| **中文 SER 跨域 drop** | RAVDESS/IEMOCAP（英文表演式）训练 → 《小江湖》自然对白（节奏快、情绪淡） | accuracy 50-60%（vs in-corpus 85%+）；下游 TTS 误情绪 | Phase 1 取证 → 若 < 40% 则 DIA-04 整体 defer；若 40-60% ship 但标 `emotion_confidence` + nullable；>60% 正常 ship |
| **民族乐器训练数据稀缺** | ChMusic 11 类（erhu/pipa/guzheng/dizi 等）vs 西洋 OpenMIC 覆盖 | 民族乐器 mAP ~0.15-0.30；西洋 ~0.40-0.50 | Phase 1 取证 → 民族乐器标 `instruments_confidence`；置信度 <0.5 时只返回 top-1 不返回 list |
| **WhisperX 中文 char dict 漂移** | wav2vec2 align 模型未覆盖中文字符（issue #1220/#1247） | 词级时间戳偏移 100-500ms | 优先 Montreal Forced Aligner（MFA）备选；若 MFA 部署成本高，ship 段级 + 词级标 experimental |
| **说话人交叠处理** | 多人对话、抢话场景 | pyannote 3.1 Powerset multi-class CE 支持但精度降 | 默认开 overlap detection；交叠段标 `overlapped=true`，下游 prompt 注明"multiple speakers" |
| **BGM 与对白能量混叠** | Demucs 分离不彻底（synth pad 渗到 vocals stem） | 误把 BGM 当对白情绪 | 用 vocals stem 跑 SER 而非 mixdown；confidence 阈值过滤 |
| **BGM 段落边界模糊** | 渐入 / 渐弱 / 长尾 pad | librosa RMS 阈值边界不稳定 | 用 hysteresis 阈值（in 0.05 / out 0.02）+ 最短段 1.5s 过滤 |
| **foley 与 BGM 在 other stem 混叠** | 风声、雨声、底噪 vs melodic BGM | 难分"sfx 主导"vs "BGM 主导" | 用 onset density + spectral flatness 区分（BGM 有节奏 onset pattern，sfx 分散） |
| **TTS 复现音色失败** | 用户期望"还原原配音员" | cosyvoice/F5-TTS 复出"近似但不原"声音 | PROMPT-02 给 reference audio 引用（指向 vocals stem 时间段）；文档明说"用 reference 比纯 prompt 更接近" |

---

## 与现有管线 / Demucs stems 的依赖矩阵

| 现有产物 | 是否复用 | v1.2 新消费方式 | 升级是否破坏 |
|---------|---------|----------------|-------------|
| `shots.json` (V3b 4-pass) | YES | per-shot 时间窗对齐所有分析 | NO |
| `transcript.json` (faster-whisper segment) | YES | 段级沿用；DIA-02 在 segments 上加 speaker_id；DIA-05 加 words[] | NO（additive） |
| `audio_analysis.json` (Demucs + RMS + dominant_type) | YES | dominant_type 仍作为 fallback；v1.2 加更细粒度字段在新 sidecar | NO（v1.1 形状不变） |
| Demucs vocals stem | YES | 跑 SER + diarization（更干净的输入） | NO |
| Demucs drums stem | YES | tempo 估计（spike 已验证 envelope peak-pick） | NO |
| Demucs bass stem | YES | BGM 分段（drums+bass+other 合成 non-vocal） | NO |
| Demucs other stem | YES | 乐器识别 + foley 描述（"other" 是 non-vocal/non-drum/non-bass 残余，最杂） | NO |
| `prompts.json` (v1.1 含 character_refs) | YES | PROMPT-01 三套 prompt 与现有 prompts.json **同一文件**（additive 新字段 tts_prompt/music_prompt/foley_prompt） | NO（additive，v1.1 字段不变） |
| `characters.json` (v1.1 re-id registry) | YES | DIA-03 speaker→character 映射目标 | NO（v1.1 形状不变；speaker_map.json 是新 sidecar） |
| v1.1 `analysis/call_shot_analysis.py` pattern | YES（设计模式） | CONTRACT-02 完全镜像（httpx + cache + degrade） | NO |

**关键不变量**：v1.2 不动 shots/detection/transcribe/separate 任何基线算法；所有新分析走 kais-aigc-platform 路由，沿用 v1.1 的"thin 客户端"模式。

---

## 与复现生成器的接口期望

> 这是 prompt 设计的下游约束。每个生成器吃不同格式；prompt 必须"够用它"。

### TTS prompt（cosyvoice / F5-TTS / GPT-SoVITS / ElevenLabs）

**生成器吃**：
- text（必需，要还原的对白文本）
- speaker embedding OR reference audio（必需，音色；纯文本出不来原声）
- emotion tag（可选，影响韵律）
- speed / pitch_shift（可选）

**v1.2 输出 tts_prompt 应包含**：
```json
{
  "speaker_id": "SPEAKER_00",
  "character_id": "char_001",
  "text": "你好世界",
  "emotion": "neutral",
  "emotion_confidence": 0.72,
  "ref_audio": {
    "stem": "vocals.wav",
    "start_sec": 12.5,
    "end_sec": 14.8
  },
  "expected_duration_sec": 2.3
}
```

**诚实声明**：TTS 复现度取决于 reference audio 质量；emotion 跨域精度 50-60%。

### Music-gen prompt（MusicGen / Suno / Stable Audio）

**生成器吃**：
- natural language description（4-7 descriptors：genre + mood + instruments + tempo + structure）
- 可选 duration hint
- 可选 structure metatags `[Intro] [Verse] [Chorus]`

**v1.2 输出 music_prompt 应包含**：
```json
{
  "segments": [
    {
      "start_sec": 0.0, "end_sec": 6.5,
      "description": "calm orchestral bed with piano lead and sustained strings, ~70bpm, gentle, melancholic",
      "structure_tag": "[Intro]",
      "instruments": ["piano", "strings"],
      "instruments_confidence": 0.62,
      "tempo_bpm": 72,
      "mood": "calm",
      "key": "C_major"
    }
  ]
}
```

**诚实声明**：music-gen 复出"风格近似"但旋律/编曲不可能 1:1；tempo 八度倍频错误 ~10-20%。

### Foley prompt（AudioGen / ElevenLabs SFX）

**生成器吃**：
- text description（subject + material + action + environment）
- 可选 duration
- 复杂事件用 sequencing（"A 然后 B 然后 C"）

**v1.2 输出 foley_prompt 应包含**：
```json
{
  "shot_id": 42,
  "events": [
    {
      "time_sec": 1.2,
      "description": "high-quality, professionally recorded, leather shoes stepping on wooden floor, approaching"
    },
    {
      "time_sec": 3.8,
      "description": "wooden door creaking open slowly"
    }
  ],
  "ambient_bed": "quiet room tone with distant wind"
}
```

**诚实声明**：单事件 foley ~80% 像；环境层 / 复杂事件序列 ~40-60% 像。

---

## Sources

**SER / Emotion（highest-risk 中文跨域）：**
- [emotion2vec: Self-Supervised Pre-Training for Speech Emotion Recognition (ACL 2024)](https://arxiv.org/abs/2312.15185) — SOTA universal SER，跨语言 incl. Chinese，420+ citations
- [emotion2vec+ GitHub](https://github.com/ddlBoJack/emotion2vec) — "Whisper of SER" 目标的开源实现
- [Cross-Corpus SER Based on Attention Mechanism (MDPI 2025)](https://www.mdpi.com/2078-2489/16/11/945) — 跨 corpus 仅 ~46.75% 准确率基线
- [CSEMOTIONS Mandarin dataset](https://huggingface.co/datasets/ATH-MaaS/CSEMOTIONS) — 中文情绪语料
- [CNSCED 中文自然语音复杂情绪数据集](https://www.scidb.cn/en/detail?dataSetId=394f27fbc9014cd486951b770fdefa10) — 中文自发语料
- [EmoBox (INTERSPEECH 2024)](https://eprints.whiterose.ac.uk/id/eprint/222971/1/INTERSPEECH2024_EmoBox-2.pdf) — 多语种 SER 基线含 emotion2vec
- [audEERING "valence gap"](https://www.audeering.com/closing-the-valence-gap-in-emotion-recognition/) — valence 难预测的工业界共识
- [Benchmarking Pretrained Models for SER (MDPI Computers 2024)](https://www.mdpi.com/2073-431X/13/12/315) — RAVDESS/EMODB/SAVEEE 95/82/85%（in-corpus 上限参考）

**Speaker Diarization：**
- [pyannote/speaker-diarization-3.1 HuggingFace model card](https://huggingface.co/pyannote/speaker-diarization-3.1) — 输入 mono 16kHz；输出 Annotation（→ RTTM）；3.0 + 纯 PyTorch（去 onnxruntime）
- [pyannote.audio 2.1 pipeline paper (Bredin, INTERSPEECH 2023)](https://www.isca-archive.org/interspeech_2023/bredin23_interspeech.pdf) — 管线架构与基准
- [Benchmarking Diarization Models (arXiv 2024)](https://arxiv.org/html/2509.26177v1) — pyannoteAI 商业版 11.2% DER；开源 3.1 推断 15-20%
- [Unsupervised Speaker Identification in TV Broadcast (Poignant et al.)](https://hal.science/hal-01060827/file/POIGNANT--ASLP--2013-2.pdf) — speaker→character 自动映射的参考
- [TVSHOWGUESS (NAACL 2022)](https://aclanthology.org/2022.naacl-main.317.pdf) — 角色 / speaker 关联任务基准

**WhisperX / Forced Alignment（中文词级时间戳风险）：**
- [WhisperX GitHub](https://github.com/m-bain/whisperx) — 主仓库
- [WhisperX paper (Bain et al. 2023)](https://www.robots.ox.ac.uk/~vgg/publications/2023/Bain23/bain23.pdf) — 词级 alignment 原理
- [WhisperX #1220 wrong word-level timestamps](https://github.com/m-bain/whisperX/issues/1220) — 中文 drift 已知 issue
- [WhisperX #1247 inaccurate word timestamps](https://github.com/m-bain/whisperX/issues/1247) — 多语种 drift issue
- [Comparison of Modern ASR Methods for Forced Alignment (arXiv 2406.19363)](https://arxiv.org/html/2406.19363v1) — MFA > WhisperX 中文精度
- [MFA Mandarin acoustic model v2.0.0a](https://mfa-models.readthedocs.io/en/latest/acoustic/Mandarin/Mandarin%20MFA%20acoustic%20model%20v2_0_0a.html) — 备选 aligner
- [lars76/forced-alignment-chinese](https://github.com/lars76/forced-alignment-chinese) — MFA 中文实践参考

**Music MIR / Instrument：**
- [MERT: Acoustic Music Understanding (ICLR 2024)](https://arxiv.org/html/2306.00107v5) — SOTA 通用音乐理解 transformer，instrument classification 在 NSynth/MTG-Medley
- [MIRFLEX (arXiv 2411.00469)](https://arxiv.org/html/2411.00469v1) — 模块化 MIR 特征库（tempo/key/chord/genre/instrument）
- [ChMusic: Traditional Chinese Music Dataset (Gong et al. 2021)](https://arxiv.org/pdf/2108.08470) — 11 类民族乐器 benchmark，45 cites
- [China Traditional Music Instrument Dataset (Zenodo)](https://zenodo.org/records/8012071) — 15 类民族乐器数据集
- [Multi-Feature Fusion + Attention for Chinese Instruments (Yang 2025)](https://www.mdpi.com/2079-9292/14/14/2805) — 民族乐器 SOTA
- [Instrument Activity Detection in Polyphonic Music (Gururani, ISMIR 2018)](https://ismir2018.ircam.fr/doc/pdfs/275_Paper.pdf) — polyphonic 多标签
- [librosa.onset.onset_detect docs](https://librosa.org/doc/0.11.0/generated/librosa.onset.onset_detect.html) — onset peak-pick
- [librosa.effects.trim docs](https://librosa.org/doc/main/generated/librosa.effects.trim.html) — RMS-based silence/fade 边界

**Layered Reproduction Prompts：**
- [Suno Prompts Complete Guide (musci.io)](https://musci.io/blog/suno-prompts) — genre + mood + instruments + vocals 4 组件
- [AudioCraft/MusicGen (Meta)](https://github.com/facebookresearch/audiocraft) — music-gen 自然语言 prompt（非 tag 语法）
- [MusicGen Prompt Library](https://rsxdalv.github.io/musicgen-prompts/) — NL prompt 范例
- [ElevenLabs SFX prompting guide](https://help.elevenlabs.io/hc/en-us/articles/25735604945041-How-do-I-prompt-for-sound-effects) — simple vs complex prompt 模式
- [AudioGen official demo](https://audiocraft.metademolab.com/audiogen.html) — environmental sound prompt 范例
- [Spotify Basic Pitch](https://basicpitch.spotify.com/about) — audio→MIDI 但对 gen 无用（AF-10 论证）

**Confidence:** 核心方法学（pyannote 3.1 输入输出、emotion2vec 跨语种能力、librosa MIR 成熟度）= **HIGH**；中文跨域具体精度数字（~45-60% SER / 民族乐器 mAP < 0.3）= **MEDIUM-LOW**（文献 + 工业共识支撑，但《小江湖》-style 动画成片实测需 Phase 1 取证）。

---
*Feature research for: v1.2 音频语义深化（dialogue/music/sfx 三模态 + 分层 TTS/music-gen/foley 复现 prompt）*
*Researched: 2026-07-25*
