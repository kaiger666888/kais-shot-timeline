# Pitfalls Research — kais-shot-timeline v1.2 音频语义深化

**Domain:** 向 validated 多轨道分镜资产管线（v1.1 已 SHIPPED：分镜 + Demucs 4-stem + faster-whisper segment-level + 镜头语言 + 跨镜角色/道具注册表 + ShotTimelineAsset schema 1.1）追加路由式音频语义三模态（对白情绪/说话人、BGM 乐器/tempo/key/VA、音效 foley）、分层复现 prompt（TTS/music-gen/foley）、schema 1.1→1.2 minor bump，并把 v1.1 推迟的 SPEAKER-01 纳入 scope。
**Researched:** 2026-07-25
**Confidence:** HIGH（v1.1 代码 pitfalls 直接锚定本仓库 `run_pipeline.py` / `analysis/call_*.py` / `spec/validate.py` / `scripts/verify_contract.py` / `RETROSPECTIVE.md`；ML 模型类 pitfalls 由 faster-whisper/WhisperX/pyannote 3.1/HF gated-repo 官方文档与 issue tracker 支撑）

> **如何读这份文档：** 每条 pitfall 按 `出了什么 → 为什么 → 怎么预防 → 预警信号 → 应在哪个 phase 解决` 给出。最后两张表把 pitfalls 浓缩成 planner 可直接派进 ROADMAP 的核验项，并按 **BLOCKER-class（必须解决才能 ship）** vs **DEGRADATION-acceptable（可降级通过，route-down 走 v1.1 graceful-degrade 模式）** 分类。
> **关于契约的措辞：** 沿用 v1.1 RETROSPECTIVE 的口径——「breaking change」严格指 rename / 语义漂移 / 删除 / 新增 required 字段（见 `spec/SPEC.md §4` + `asset.schema.json#schema_version.description`）。v1.2 决定是 **minor bump（`"1.1"` → `"1.2"`，纯增量）**——见 `PROJECT.md` Constraints。凡是会触发 breaking change 的，都是 **致命** pitfall。
> **关于 v1.1 经验的复用：** v1.1 RETROSPECTIVE 列出 9 个 blocker + 22 warning。其中 **5 类**会再次出现：① green verify harness 隐藏 blocker；② XSS `_esc` sink 每 phase 复发；③ `__file__`-in-`python3 -c` 验证 snippet 复发；④ [N/M] banner 重编号 error-prone；⑤ graceful-degrade 必须证明而非假设。本文件把这些直接编进 pitfalls 而不是附录，因为它们就是 v1.2 的现实约束。

---

## Critical Pitfalls (BLOCKER-class — must solve to ship)

### Pitfall 1 — 中文 SER 跨域：RAVDESS/英文表演式模型静默错标中文对白情绪

**What goes wrong:**
Phase 1 直接拉一个开源 SER 模型（最常见是 RAVDESS / IEMOCAP / MELD 上训练的 wav2vec2 / hubert / emotion2vec），跑中文动画对白 → 输出情绪标签。标签看起来合理（discrete 标签空间小，看不出明显错），但与人工标注对照，准确率掉到 30-40%（接近随机基线），且错误集中在「中文对白特有的语调/语气词」上（「哦」「嗯」「啊」带语调变化，英文模型把这些当中性/疑问，中文语境实际是感叹/无奈/讽刺）。最坏情况：标签流向 `audio_semantic.json` → 分层 prompt 写进 TTS 情绪指令 → 用户拿去生成 TTS，声音情绪与原片完全不符。

**Why it happens:**
- RAVDESS 是英文专业演员表演的 8 类情绪，分布极不自然（每类情绪等量、强度夸张）。
- 中文动画对白：① 演员表演更含蓄（情绪强度低于 RAVDESS 平均）；② 大量语码切换 / 文白异读；③ 背景音乐残留（即使 Demucs 分离后，vocals 仍带 bleed）。
- emotion2vec / hubert-large-superb 在 Mandarin 上的 ER（emotion recognition）数据是 Vimeo/播客/Drama，不是动画对白 —— 域差距叠两层（语言 + 风格）。
- 没有 confidence score → 错标也写进 JSON，操作员无法过滤。

**How to avoid:**
1. **Phase 1 risk-validation 必须用 1 集真实 ep01 数据跑中文 SER 候选模型**（候选：emotion2vec+, ChineseBERT-wenlv, Chinese-Wav2Vec2-Emotion, ISCSI_audio_emotion），与**人工标注 3-5 分钟抽样**对照，记录 confusion matrix。低于阈值（建议 macro-F1 ≥ 0.5）→ **SPEAKER-01 SER 子项 deferred，schema 仍带 `emotion` 字段但 producer emit 空串 + warning**（镜像 v1.1 graceful-degrade）。
2. **必须 emit confidence** —— `audio_semantic.json` 的 emotion 字段是 `{label, confidence, source_model}` 而不是裸字符串。低于阈值（如 0.4）的预测 producer 不写 label，写 `confidence: low`。
3. **prompt 反推侧门控** —— 分层 TTS prompt 引用 emotion 仅当 `confidence ≥ 0.6`；否则 TTS prompt 不带情绪指令（让下游 TTS 用默认）。
4. **不准在 Phase 1 commit 任何契约** —— 信号未验证前不锁 emotion schema shape（参考 v1.1 Phase 7 DINOv2 τ spike 的「先证模型、再立契约」纪律）。

**Warning signs:**
- Phase 1 报告出现「RAVDESS 预训练模型直接用」字样，无中文验证 → blocker。
- `audio_semantic.json` emotion 字段是 `string`（裸标签）而非 `{label, confidence}` → blocker。
- 操作员在 ep01 抽 3 个 shot 看 emotion 标签，发现「哦」「啊」全部标 `neutral` → 域失败信号。
- Phase 2 contract 把 `emotion` 写进 required[] → 违反 minor-bump 规则。

**Phase to address:** **Phase 1 (model risk-validation)**. 若模型不可用，**Phase 2 (contract)** 必须把 emotion 设计为 optional + 空串/降级 schema 合法（镜像 v1.1 graceful-degrade）。

---

### Pitfall 2 — WhisperX 迁移破坏 faster-whisper fallback 路径 + 词级对齐在长音频上漂移

**What goes wrong:**
v1.1 `audio/transcribe.py:69-123` 的现有架构是：`faster_whisper.WhisperModel` 优先 → `ImportError` 或 runtime failure → fallback `openai_whisper.load_model`。v1.2 要换成 WhisperX 拿词级时间戳（pyannote diarization 也通过 WhisperX）—— 这破坏了两件事：

1. **Fallback 路径断裂**：WhisperX 内部已用 CTranslate2（即 faster-whisper 同后端），但 API 不同（`whisperx.load_model` vs `WhisperModel`），且 WhisperX 强依赖 pyannote（gated）+ wav2vec2 alignment 模型（gated）。任意一环缺 → WhisperX 整条 import 失败 → 现有 `ImportError` fallback 链触发 openai-whisper，但 **openai-whisper 没有词级对齐** → 下游 diarization 失败、prompt 词级时间戳字段全部空 → 看起来「fallback 成功」但实际能力全部降级。
2. **词级对齐漂移**：WhisperX 的 wav2vec2 forced alignment 在长音频（≥ 30min ep）上会累积漂移 —— 词时间戳与音频实际位置偏差 0.5-2 秒（PyAnnote alignment 模型训练集是短音频）。对话密集 + BGM 残留时尤其严重。下游对 `transcript.segments[].words[].start/end` 做精确切片（per-shot, per-turn, per-word）的代码会拿错切片 → 字幕错位、情绪标签错镜、speaker turn 边界错。

**Why it happens:**
- v1.1 fallback 设计的前提是「两种 backend 输出 segment-level 同形状」。WhisperX 加 word-level + speaker 字段后形状不同，fallback 不再是「换 backend」而是「换能力」。
- WhisperX 把 `condition_on_previous_text` 等选项硬编码为 False（与 batched pipeline 不兼容）—— v1.1 `transcribe.py` 若依赖这些参数会静默忽略，导致转录质量回归。
- wav2vec2 alignment 模型（常见 `jonatasgrosman/wav2vec2-large-xlsr-53-chinese`）训练数据是 read-speech，对动画对白（高语速、情感强度、BGM bleed）的 alignment 质量未验证。

**How to avoid:**
1. **Phase 1 risk-validation 跑长音频对齐漂移测试** —— 用 ep01 全集（≥ 20min）跑 WhisperX，抽 5 个密集对话段，与 ffmpeg+人工切片对照词边界，记录偏差。
2. **Phase 2 dialogue 实现**：保留现有 `--whisper-backend {auto, faster-whisper, openai-whisper}` flag 不动（v1.1 已 ship），**新增 `whisperx` 作为 backend 选项**而不是替换。`auto` 顺序：`whisperx` → `faster-whisper` → `openai-whisper`。**只有 whisperx backend 跑词级 + diarization；其余 backend 输出 segment-level，不 emit 词级字段，diarization 标记为 "deferred"**。
3. **schema 形状兼容**：`audio_semantic.json` 的 `words[]` + `speaker_id` 全 optional。无 WhisperX 时这些字段缺失（schema 合法），仅 segments-level 对白可用，warning sidecar 记原因。
4. **绝不删除现有 `audio/transcribe.py` 的 fallback try/except**（v1.1 SHIPPED 的代码，注释 + 行号都在）。WhisperX 是**叠加层**而非替代。
5. **对齐漂移门控**：词级字段流进 layered prompt 时，做时间一致性 sanity check（word.end > word.start, word.start within segment.start..end）。不一致的词丢弃，warning 记录。

**Warning signs:**
- Phase 1 risk-validation 跳过长音频测试 → blocker。
- `audio/transcribe.py` 出现 `import whisperx` 替换 faster-whisper → 破坏 v1.1 SHIPPED 代码的 fallback 路径。
- `whisperx` backend 路径不写 warnings sidecar，操作员看不见能力降级 → blocker。
- 词级字段 `words[].start` 出现负值或超过总时长 → 对齐漂移信号。

**Phase to address:** **Phase 1** 验证（漂移测试）→ **Phase 2 dialogue implementation** 实施（叠加 backend flag、保留 fallback、shape 兼容）→ **Phase 2 contract** 锁词级字段 optional。

---

### Pitfall 3 — pyannote 3.1 diarization：HF token + license acceptance blocker + speaker-count / overlap / speaker↔character mapping 模糊

**What goes wrong:**
v1.2 把 SPEAKER-01 纳入 scope，需要 pyannote 3.1 speaker-diarization。四个子坑：

(a) **HF gated repo 准入 blocker**：pyannote speaker-diarization-3.1 + segmentation-3.0 都是 gated，必须 HF 账号 + 接受两份 user conditions + HF_TOKEN（read）。常见 401 即使「已接受」也会出现（环境变量冲突、git credentials 抢占）。Phase 1 第一次跑模型时如果 token 没配好，整个 diarization 路径无法启动 → 看似「模型不可用」其实是「准入流程没完成」。

(b) **speaker-count 错误**：pyannote 默认 `ClusterSemanticSpeakerDiarization` 不限定 speaker 数；动画常见情况：① 角色变声（同一配音员演多角色）→ 系统合并成 1 个 speaker；② 多个角色共用一个配音风格 → 过合并；③ 旁白 + 角色 + 群杂 → 系统裂出 N+ speaker。pyannote 3.1 的 clustering 对超短发言（< 1s 的「啊」「哦」）尤其敏感。

(c) **overlap segments 处理**：动画常见抢话、合唱、群杂。pyannote 默认输出有 overlap segments（同一时间多个 speaker_id），但 shot 边界 + speaker turn 边界 + word 边界三者不重合时，归属谁说了哪句台词变成歧义。

(d) **speaker_id ↔ character 映射模糊**（v1.1 DEFERRED 的「大 lift」问题）：① 同一 speaker_id 对应多个 character（配音员变声、声音克隆）—— 用户期望 `SPEAKER-01` 直接是 `char_001`，实际需要人审；② 同一 character 对应多个 speaker_id（角色换配音、回忆杀音色变化）；③ 群杂/旁白没有对应 character 注册表项。这是 v1.1 Out of Scope 的核心原因，v1.2 借 pyannote 路由化降 lift 但**完全解决仍然不可能**。

**Why it happens:**
- pyannote 3.1 准入流程是 HuggingFace 强加的（research-only license + 用户 traceability），无法绕开（fork 版本如 3.0 开源但仍需 segmentation-3.0 准入）。
- 动画对白特性（变声、群杂、配音员多角色）超出 pyannote 训练分布（播客/会议/访谈，真人单角色）。
- speaker→character 是**语义**层映射，pyannote 只产 acoustic 层 speaker_id —— 必须额外人审/对齐步骤（v1.1 character registry 的 HITL review 模式适用，但要新增映射层）。

**How to avoid:**
1. **Phase 1 risk-validation 文档化准入流程**：列出 HF account + accept segmentation-3.0 + accept diarization-3.1 + generate read token + `HF_TOKEN` env var 五步。**Producer 侧（shot-timeline）永不内联 HF_TOKEN** —— token 在 kais-aigc-platform 路由侧配置，shot-timeline 只发 httpx 请求（与 v1.1 thin-client 模式一致）。
2. **Phase 2 contract：speaker_id 是 acoustic 层，非 character 层**。`audio_semantic.json` 只产 `speaker_id: "SPEAKER_01"` 等，**不**自动映射到 character registry。character mapping 是**新加的 HITL 步骤**（镜像 v1.1 apply_edits.py 的 confirmed-only 模式）：产 `speaker_character_map.draft.json`，操作员 review 后产 `speaker_character_map.json` 才生效。
3. **shot 统计层处理多 speaker**：一个 shot 内多 speaker 时，`audio_semantic.json#dialogue.shot_SSS` 用 `dominant_speaker` + `speakers: [list]` 而非单一 speaker。每 speaker 的发言时长占比 emit 出来（`{speaker_id, duration_sec, ratio}`）。
4. **overlap segments 不丢弃，标记为 `overlapping: true`** —— 下游消费者自决定如何呈现，shot-timeline 不替它决策。
5. **SPEAKER-01 子项 graceful-degrade 显式声明**：HF token 缺失 / 路由未上线 / clustering 失败 → `audio_semantic.json#dialogue.speakers = []`，warning sidecar 记原因，asset 仍导出。**这是 acceptable degradation**（schema 合法，未触及 required 字段）。

**Warning signs:**
- Phase 1 出现 `use_auth_token=` 在 shot-timeline 仓库代码里 → 越界（token 应在路由侧）。
- `speaker_character_map.json` 是 producer 自动产（无 HITL） → 违反 v1.1 confirmed-only 模式，blocker。
- 一个 shot 内只允许单 speaker（schema 限制 speakers[] maxItems=1） → 现实里有抢话镜头会被强行单选，blocker。
- pyannote 3.1 在 ep01 上跑出来 SPEAKER_01..SPEAKER_15+（动画单集一般 3-6 个主要 speaker） → speaker-count 失败信号，需调 cluster 阈值或加 VAD 前置。

**Phase to address:** **Phase 1** 验证（HF 准入 + 模型在 ep01 上的 speaker-count 是否合理）→ **Phase 2 contract**（speaker_id 与 character 解耦、overlap 标记、map draft 设计）→ **Phase 2 dialogue implementation**（HITL map 模式镜像 v1.1）。

---

### Pitfall 4 — 契约 1.1→1.2 bump 破坏「v1.0/v1.1 byte-identical-absent」保证 + validate.py shape-count drift + verify_contract.py modes

**What goes wrong:**
v1.1 的核心保证：v1.0 minimal fixture 对 v1.1-extended schema 仍 6/6 valid（forward compat），v1.1 fixture 对 v1 schema 仅 additionalProperties 错（backward compat）。v1.2 必须延续：**v1.0 + v1.1 fixture 对 v1.2-extended schema 仍 100% valid，v1.2 fixture 对 v1.1 schema 仅 additionalProperties 错**。

四个子坑：

(a) **byte-identical-absent 保证破裂**：v1.1 决策是「audio semantic 数据是 sidecar `audio_semantic.json`，audio_analysis.json 不动」（PROJECT.md:25 明确）。但实施时诱惑是「顺手给 audio_analysis.json 加 `dominant_emotion`、`tempo`、`key` 字段」（已有的 per-shot shape，复用方便）。一旦这么做，audio_analysis.json 在 v1.2 producer 与 v1.1 不再 byte-identical —— 违反 minor-bump 的「缺省 byte-identical」保证（v1.1 SCHEMA_VERSION producer-locked 模式的延伸）。

(b) **validate.py shape-count drift**：v1.1 加到 10 shapes（V11_ORDER = 10 项）。v1.2 若新增 audio_semantic shape + speaker_character_map shape → 12 shapes。VALIDATE.py 的 V11_ORDER / EIGHT_SHAPES / SIX_SHAPES 常量名已经不准确（v1.1 文档承认 "名字保留 EIGHT_SHAPES（v1.0 历史叫法）以兼容既有 fail-loud self-test 文档引用；实际是 9 个元素"）。再加 shape 容易把 v1.2 fixture gate 写漏（一个 shape 缺 fixture 但 validate.py 不报）。

(c) **verify_contract.py 模式覆盖漂移**：v1.1 的 `validate_eight_shapes` 跑 9 个 shape（v1.0 6 required + v1.1 3 optional）。v1.2 新增 shape 必须加到 EIGHT_SHAPES，但**新增的全是 optional**（graceful-degrade），不能让 producer 模式因为「v1.0 asset 不含 audio_semantic.json」失败。 `_cross_version_check` 在 v1.1 已有，v1.2 必须扩展为 v1↔v1.1↔v1.2 三向（或至少 v1.1↔v1.2 双向），否则 v1.1 consumer 在收到 v1.2 asset 时静默跳过的行为无回归保护。

(d) **SCHEMA_VERSION producer-locked constant 漏 bump**：v1.1 在 `export_asset.py` 设了 `SCHEMA_VERSION = "1.1"` 单一真源。v1.2 必须改成 `"1.2"`。漏改 → producer 仍 emit `"1.1"`，v1.2 新字段流进 `"1.1"` asset → v1.1 schema additionalProperties:false 拒 → 但因为 SCHEMA_VERSION 还是 "1.1"，schema 选错 → 整个 producer 自校验崩溃。

**Why this happens:**
- 「顺手加字段」诱惑强：audio_analysis.json 已是 per-shot shape，多塞 4 个字段比新建 sidecar 文件摩擦小。但破坏 minor-bump 哲学。
- 形状数累积时文档常量名（EIGHT_SHAPES/NINE_SHAPES/V11_ORDER）不更新，新 shape 漏加 fixture 但 validate.py 不报。
- v1.1 retrospective 提到「green verify harness can hide blockers if it skips a check on the new code path」（Phase 9 CR-01：v1.1 run skipped `validateGraphNodes`）。v1.2 同样陷阱：v1.2 run 跳 v1.1 fixture 验证就触发不到 shape drift。
- SCHEMA_VERSION 是单点，但在 `export_asset.py` + `prompts/attach_refs.py` + 可能的 `analysis/call_audio_analysis.py` 都可能引用，分散引用容易漏 bump。

**How to avoid:**
1. **Phase 2 contract 锁死：所有 v1.2 新数据进新 sidecar `audio_semantic.json`，audio_analysis.json 不动一个字节**（与 v1.1 「prompts schema 扩展 character_refs 是 additive 但 prompts 已存在」不同——这里 v1.2 完全新文件，零修改 v1.1 文件）。Verify: `git diff v1.1..v1.2 -- spec/schemas/audio_analysis.schema.json` 必须 0 行。
2. **validate.py 三阶 shape gate**：MINIMAL_ORDER（6 v1.0）、V11_ORDER（10 v1.1）、V12_ORDER（≥12 v1.2）三组分别校验，每组缺失 fixture 都 fail-loud。常量重命名为 `SHAPES_V10 / SHAPES_V11 / SHAPES_V12`，EIGHT_SHAPES 加 deprecation alias 保留 1 个 milestone 周期。
3. **verify_contract.py 扩展 cross-version**：新增 `_cross_version_check_v1_1_v1_2()`（v1.1 fixture 对 v1.2 schema 必须 0 错；v1.2 fixture 对 v1.1 schema 仅 additionalProperties 错）。**新 fixture 必须 immediate-fail-loud**：写完 fixture 当下跑 verify_contract.py producer mode，0 错才入 main。
4. **SCHEMA_VERSION producer-locked 单源扩展**：单一常量 `SCHEMA_VERSION = "1.2"` 在 `export_asset.py`，其他文件**不复制字面量**，全部 import。Phase 2 加 grep assertion：`grep -rn '"1\.[12]"' analysis/ prompts/ scripts/ spec/ | grep -v SCHEMA_VERSION` 必须空。
5. **Phase 2 verify 必须包含「v1.0 + v1.1 minimal fixture 对 v1.2 schema」forward compat 检查**——这是 v1.1 _cross_version_check 的延伸，不能跳。

**Warning signs:**
- Phase 2 PR diff 里 `audio_analysis.schema.json` 有非空改动 → 立即 blocker。
- `SCHEMA_VERSION` 在多文件出现字面量 → blocker。
- validate.py 新增 shape 但 fixture 没建 → fail-loud 应立即触发；若 CI 绿 → 测试本身坏了。
- verify_contract.py v1.2 fixture 对 v1.1 schema 跑出错（除 additionalProperties）→ 共享字段类型漂移。
- `audio_semantic.json` 是 optional sidecar 但 producer 总是 emit（即使 route-down 时空字段）—— 违反「缺省 byte-identical」（v1.0/v1.1 asset 不应有此文件）。

**Phase to address:** **Phase 2 contract** 锁死规则 → **Phase 2 implementation** 加 verify 与 cross-version check → 每个 producer phase 执行时重跑 verify_contract.py。

---

### Pitfall 5 — [N/8] → [N/9] banner 重编号（v1.1 Pitfall 5 复发）

**What goes wrong:**
v1.1 RETROSPECTIVE 明确把 banner 重编号列为 Pitfall 5：从 [N/7] 到 [N/8] 时多处漏改，造成 `[5/8]` 出现两次、grep count 不一致、verify 脚本 banner-count assert 失败。v1.2 添加 `step_audio_semantic`（slot 7 of 8 → 9）会复发：

- `run_pipeline.py` 里 17 处 `[N/8]` 字面量分布在 `ensure_h264`/`step_detect`/`step_separate`/`step_transcribe`/`step_semantic`/`step_reid`/`step_timeline`/`step_export` 的 print 语句里（grep `\[1/8\]`…`\[8/8\]` 看实际位置）。
- 新 step `step_audio_semantic` 插入位置（5/6/7 of 9 都合理）决定哪些 step 重编号 —— 每个位置选择都有 grep count 变化。
- v1.1 Phase 8 的 CONTEXT Q3 lock 把 `attach_refs` 显式定成「不带 numeric 前缀」的 plain label（`run_pipeline.py:339`），就是为避免这次重编号。但 v1.2 不可能再用此 trick（audio_semantic 是 numbered step）。

**Why it happens:**
- banner counter 是隐式约定，无 single-source-of-truth。Python 没有 compile-time check 能 catch `print("[5/9]")` 出现两次。
- 加 step 时操作员机械替换 `\[./8\]` → `\[./9\]`，但漏了 1-2 处 → banner 重复 → 下游 verify 的 grep count 失败 → 卡住整 phase。

**How to avoid:**
1. **Phase 2/3 实现 step_audio_semantic 前，写一个 banner 一致性测试**：扫 `run_pipeline.py` 所有 `\[N/M\]` 字面量，断言 (a) M 是单值（all 9 或 all 8），(b) N 从 1 到 M 无重复无缺失。Phase 1 verification 阶段 grep assertion：`grep -c '\[[0-9]/[0-9]\]' run_pipeline.py` 必须 == M。
2. **使用 `f"[{n}/{TOTAL_STEPS}]"` 占位符**：把 TOTAL_STEPS 提成模块级常量，所有 step 函数接受 `step_num` 参数，banner 由 `run_step` 统一格式化。重编号时只改 TOTAL_STEPS + 调用处顺序。
3. **新 step 显式选位置**：建议把 `step_audio_semantic` 放在 **slot 6 of 9**（在 step_semantic 之后、step_reid 之前）—— 逻辑上 audio semantic 与 cinematography 都是分析填充，紧挨；re-id 留后（依赖 character registry，与 audio speaker 映射逻辑相关）。这个位置需 Phase 2 决定并文档化。
4. **Phase 1 plan-checker 必须重跑 grep count 验证**（v1.1 Pitfall 5 是 plan-checker 抓的，沿用此纪律）。

**Warning signs:**
- PR review 看到 `[5/9]` 出现两次 → blocker。
- run_pipeline.py grep `\[./9\]` count != 9 → blocker。
- verify_phase{N}_smoke.py 报 banner-count mismatch → blocker。
- step_audio_semantic 没有 [N/9] banner → 漏加。

**Phase to address:** **Phase 2 implementation**（step 插入） + **每 phase code review**（grep count check）。**DEGRADATION-acceptable**——纯 mechanical 错误，不会破坏契约，只阻塞当前 phase 通过 verify。

---

## Critical Pitfalls (cont.) — Domain-specific model/integration risks

### Pitfall 6 — 多音轨动画 BGM 乐器识别 false-confidence（MIR on polyphonic animation BGM post-Demucs）

**What goes wrong:**
Phase 1 选 MIR 模型（候选：MERT、MIRFlex、MusicNN、openl3、AudioSet VGGish）跑 Demucs 分离后的 `other.wav`（htdemucs 的 other stem 涵盖 BGM 乐器）或 `drums.wav`。两个失败模式：

(a) **多音轨场景识别 false-confidence**：动画 BGM 通常多乐器叠加（弦乐 + 钢琴 + 合成器 + 打击乐），即使 Demucs 分离后 other.wav 仍混。单标签模型（如 MIRFlex 的 dominant instrument）会输出一个高 confidence 的「钢琴」标签，但实际是「钢琴 + 弦乐」混合 → 用户拿分层 prompt 去 music-gen，生成的音乐只有钢琴，丢失弦乐层。
(b) **Demucs bleed 干扰**：Demucs 4-stem 分离不是 surgical —— drums stem 常带 bass bleed（反之亦然），other stem 可能漏掉 bass 线。MIR 在 bleed 的 stem 上跑会标错（drums.wav 标出「bass」）。

**Why it happens:**
- MIR 模型训练数据（IRMAS、OpenMIC）多为单乐器主导录音，不是动画 BGM 的多乐器混合。
- Demucs htdemucs 在 vocals/drums/bass/other 四分轨是为 source separation 设计，不是为下游 MIR 设计—— bleed 是已知现象（论文报告 SDR 4-8dB，残余显著）。
- 没有 multi-label 输出 + 没有 confidence → 用户看不见「这是混合」。
- 动画 BGM 常有「环境氛围」段（pad/synth drone），乐器模糊，主流 MIR 模型会强行标出某个具体乐器。

**How to avoid:**
1. **Phase 1 risk-validation 在 ep01 抽 5 个音乐镜头跑候选 MIR 模型**，输出对比 + 抽样人工标注（每镜头允许 1-3 个乐器 ground truth）。低于 multi-label F1 ≥ 0.4 的模型 → 子项 deferred。
2. **Phase 2 contract：instruments 字段是 list 而非 string** —— `[{"label": "piano", "confidence": 0.78}, {"label": "strings", "confidence": 0.45}]`，按 confidence 降序。低于阈值（0.3）的乐器不写。
3. **emit 信号源**：每乐器标 `source: "MIRFlex|AudioSet|manual"` 让下游 prompt 知道可信度。AudioSet（VGGish）做粗分类（music/speech/sfx），MIRFlex/MERT 做细分类（乐器）—— 两者结果可交叉验证。
4. **phase 2 producer 实现侧：MIR 跑在 drums.wav + other.wav + bass.wav 三个 stem 上各跑一次**，结果 union，避免单一 stem 视角偏。vocals.wav 跳过（人声不是乐器）。
5. **`tempo` 字段门控 dominant_type**：现有 v1.1 `audio_analysis.json#shots[].dominant_type` 是 `{dialogue, music, sfx, mixed}` —— Phase 1 spike 已发现 tempo 在 dialogue/sfx 镜头会产 bogus bpm（v1.2 milestone context 也提到）。Producer emit `tempo` 仅当 `dominant_type ∈ {music, mixed}` 且 `music_ratio > 0.4`；其余情况 `tempo: null` + warning 记「dominant_type=dialogue, tempo suppressed」。

**Warning signs:**
- Phase 1 报告出现「MIRFlex 单乐器标签可用」无验证 → blocker。
- `audio_semantic.json#music.instruments` 是 `string` 而非 `list[{label, confidence}]` → blocker。
- dialogue 镜头出现 `tempo: 128` 等具体 bpm → bogus 信号。
- Phase 1 在 vocals.wav 上跑 MIR → 误用 stem。

**Phase to address:** **Phase 1 risk-validation**（精度 + 假阳性测试）→ **Phase 2 contract**（multi-label schema + dominant_type 门控）→ **Phase 2 music implementation**（stem union + null fallback）。

---

### Pitfall 7 — 分层复现 prompt 忠实度过承诺（用户期望「prompt → 完美还原音频」）

**What goes wrong:**
v1.2 PROJECT.md 把分层 prompt 列为核心交付（TTS / music-gen / foley 三套）。用户（与 README 描述的目标受众：内容创作者 + AI 影视管线）拿到带情绪标签 + 乐器 + tempo 的 prompt，期望「丢进 Suno/ElevenLabs/AudioGen 直接还原原片音频」。实际：① TTS 模型对中文情绪标签（尤其小语种如「哀怨」「戏谑」）支持差；② music-gen 模型（MusicGen/Stable Audio）对「钢琴 90bpm A minor 氛围」的还原是分布采样，单次生成不接近原片；③ foley 模型（AudioGen）对「脚步踩雪」的细节还原与原片导演意图差很远。

**Why it happens:**
- 「prompt」一词在 LLM 时代有「精确指令」的暗示，但生成模型是分布采样，不是确定性还原。
- 分层 prompt 的形状（label + confidence + 参数）让用户错觉「这是 spec」而不是「这是 hint」。
- 没有「对照原片验证」环节 → 用户首次失败后失去信任。
- 项目愿景文档（PROJECT.md:5）「把成片解构成可导航、多轨道、带语义的分镜资产」隐含资产可复现，但实际复现精度受生成模型限制。

**How to avoid:**
1. **Phase 2 contract 显式标注 prompt 是「reproduction hint」而非「reproduction spec」** —— 在 `audio_semantic.json#layered_prompts` 加 `fidelity_disclaimer` 字段（schema-level string，emit 时硬编码「These prompts are hints; actual generation varies by model and sampling」）。SPEC 文档化。
2. **每层 prompt 携带 confidence** —— TTS prompt 引用 emotion 时必须含 emotion confidence；music prompt 引用 instruments 时含每乐器 confidence。低 confidence 字段用 `~` 前缀或 optional 标记（如 `[maybe: strings]`），下游生成模型可灵活处理。
3. **HTML 展示侧用「estimated」标签** —— 不写「Emotion: Sad」而是「Emotion: ~Sad (confidence 0.42, model: emotion2vec)」。让操作员一眼看出信号强度。
4. **README + SPEC 明确 v1.2 不保证还原精度**，只保证「prompt 是结构化的、可信度可见的、与原片对齐的」。这是 acceptable scope —— 用户得到的是「可编辑的 hint 起点」而非「一键还原」。
5. **不 emit 模型没产生的字段** —— emotion 模型 confidence 低 → TTS prompt 不带情绪指令而非带空指令。`attach_refs.py` 模式适用（v1.1 的「确定性 Pattern 2 recompose」纪律）。

**Warning signs:**
- README/SPEC 出现「perfectly reconstruct」「exact restoration」字样 → blocker（over-promise）。
- `layered_prompts[].emotion = "sad"`（无 confidence） → blocker。
- 用户反馈「prompt 没还原音频」但无 fidelity_disclaimer 字段 → 文档失败。
- 分层 prompt 字段是 `string` 而非 `{hint, confidence}` 结构 → blocker。

**Phase to address:** **Phase 2 contract**（disclaimer + confidence schema）→ **每层 prompt 生成 phase**（hint-not-spec 心态）→ **HTML 展示 phase**（estimated 标签）。

---

## Critical Pitfalls (cont.) — Cache + integration + verify harness

### Pitfall 8 — Per-shot vs per-video cache key 混淆（v1.1 reid per-video / v1.2 SER+MIR per-shot）

**What goes wrong:**
v1.1 代码：
- `analysis/call_shot_analysis.py` cache **per-shot**（`route_cache/shot_analysis/shot_XXX.json`）—— 因为运镜分析是逐镜。
- `analysis/call_reid.py` cache **per-video**（`route_cache/character_reid/video_<vch>.json`）—— 因为 re-id 是跨镜聚合。

v1.2 三模态 cache 粒度不同：
- SER (per-shot emotion) → per-shot cache（如 shot_analysis）
- WhisperX + pyannote diarization (per-video transcript + speaker clustering) → per-video cache（如 reid）
- MIR (per-shot music analysis) → per-shot cache
- speaker_character_map HITL → per-video + 操作员手动编辑

诱惑是 copy-paste 一个 cache pattern 到所有，导致：
- 把 diarization（per-video）放 per-shot cache → 每镜重跑整支视频的 clustering，N 倍耗时。
- 把 SER（per-shot）放 per-video cache → 同一 emotion 写 N 份冗余，且 video 变 → SER 全失效（实际只需该 shot 重跑）。
- cache key `_cache_key` 四元组 `(video_content_hash, route_name, route_version, ...)` 在不同 step 不一致（v1.1 WR-04 已修复 route_name 缺失 bug，v1.2 复发风险存在）。

**Why it happens:**
- v1.1 两个 step 的 cache 逻辑相似但不完全一致，copy-paste 后忘记调粒度。
- ROUTE_VERSION bump 时 per-shot cache 有 N 个文件要失效，per-video 只 1 个 —— 失效逻辑不一样。
- cross-step warnings sidecar 合并：v1.1 call_reid.py 已实现 READ-merge-write（`run_pipeline.py` 的 step_reid 注释提到）。v1.2 加 step_audio_semantic 时若不沿用此模式 → 覆盖 step_semantic + step_reid 的 warnings。

**How to avoid:**
1. **Phase 2 contract 文档化每个 step 的 cache 粒度**：表格 `step → granularity → cache path template → ROUTE_NAME → ROUTE_VERSION`。三个新 step 都对应。
2. **抽 helper**：`analysis/_cache.py` 提供 `per_shot_cache_path(work_dir, route_name, shot_id)` + `per_video_cache_path(work_dir, route_name, vch)`。禁止新 step 重新实现路径拼接。
3. **warnings sidecar 合并纪律**：所有新 step **必须 READ-merge-write**（v1.1 call_reid.py:443-449 模式）。STEP_TAG 模式（`[audio_semantic]`、`[dialogue]` 等）让 self-dedup cross-run 工作。
4. **`video_stamp` sidecar 模式扩展**：v1.1 已为 prompts.json + registry.draft.json 加 `.video-stamp`（防 mtime-only cache 误命中）。v1.2 新 output（audio_semantic.json、speaker_character_map.json）同样需要。

**Warning signs:**
- 新 step cache 路径不符合 `route_cache/<route_name>/{shot_XXX,video_<vch>}.json` 模式 → blocker。
- 两个 step 共用 cache 文件名 → cross-route 误命中。
- warnings.json 在 step_audio_semantic 后丢失 step_semantic warnings → 覆盖 bug。
- ROUTE_VERSION bump 后旧 cache 不失效 → stale 数据流向下游。

**Phase to address:** **Phase 2 contract**（cache 粒度表）→ **Phase 2 implementation**（helper + READ-merge-write）→ **每 phase code review**（cache key 一致性）。

---

### Pitfall 9 — 跨仓库协调：audio-analysis 路由未 merge → graceful-degrade 必须承载整个 milestone（v1.1 模式复用）

**What goes wrong:**
v1.2 PROJECT.md 决策：「引擎放 kais-aigc-platform（路由式，非全本地）」。这意味着所有三模态分析依赖 kais-aigc-platform 新建 `audio-analysis` 路由，**路由今日不存在**（v1.1 RETROSPECTIVE deferred 列表显示 shot-analysis 路由仍未 merge、character-reid 路由未建）。最坏情况：

- 整个 v1.2 milestone 在 producer/contract 侧完成，但 audio-analysis 路由分支未 merge → 用户拿到的资产全是空字段（graceful-degrade 触发），实际能力为 0。
- 跨仓库 PR 协调失败（kais-aigc-platform review 拖延、CI 红、合并冲突），producer 这边 ship 了但消费端没人接。
- v1.1 的 audio-analysis 路由分支已建但未 merge，v1.2 再叠 audio-analysis 路由 → 两条 unmerged 分支叠加，合并风险指数增长。

**Why it happens:**
- 跨仓库 milestone 实测加 ~30% 开销（v1.0 + v1.1 RETROSPECTIVE 一致结论）。
- 路由实现依赖 ComfyUI 节点（shot-analysis 已落地，audio-analysis 未）—— 工作流调试 + 显存 + 模型下载都是阻塞。
- v1.1 已 deferred 3 项，v1.2 再 deferred 会让 producer-only ship 的比例越来越高 → 「实际可用的 milestone」与「形式上 ship 的 milestone」脱节。

**How to avoid:**
1. **Phase 1 风险验证可在本仓库 spike**：用 ep01 + 临时本地脚本（不进 producer main）验证模型可用性。**不依赖 kais-aigc-platform 路由**。
2. **每个 producer phase（Phase 2 dialogue/music/sfx）必须 graceful-degrade proven**（v1.1 标准）：route-down 触发时，schema 合法的空字段 asset 仍导出，warning sidecar 记原因。verify 脚本三个场景必跑：route-up / route-down / cache-hit-offline。
3. **跨仓库 audio-analysis 路由分支 EARLY 建（Phase 1 末尾）**：即使内容是 stub，让 producer 客户端开发有 target URL + envelope shape。Phase 2 起 producer 客户端针对真实路由做集成测试（哪怕路由侧是 fake response）。
4. **明确 deferred 列表**：v1.2 ship 时 deferred 包括：① audio-analysis 路由 live round-trip；② SPEAKER-01 → character mapping HITL；③ 中文 SER 精度（如 Phase 1 验证失败）。**producer/contract 侧必须完整**（与 v1.1 同样标准）。
5. **跨仓库 commit 纪律**（v1.1 SHIPPED 经验）：`git add` 显式列文件，不 `git add -A`，保留用户 uncommitted WIP。

**Warning signs:**
- Phase 2 client 代码引用路由 URL 但路由分支未建 → 集成测试无法跑。
- 跨仓库 PR 在 v1.2 ship 时仍未 merge → milestone audit 必须列入 deferred。
- producer verify 不包含 route-down 场景 → graceful-degrade 假定未证。
- 操作员报告 v1.2 ship 的资产全是空字段 → 路由未上线，但 milestone audit 没说清。

**Phase to address:** **跨 phase（每个 producer phase）**。**DEGRADATION-acceptable** —— v1.1 模式已证明此 pattern 可 ship，关键是文档化 deferred + warning sidecar。

---

### Pitfall 10 — Green verify harness 隐藏 blocker（v1.1 Phase 9 CR-01 复发：新代码路径跳 schema 校验）

**What goes wrong:**
v1.1 RETROSPECTIVE 明确教训：「A green verify harness can still hide blockers if it skips a check on the new code path」。Phase 9 CR-01 是 v1.1 run 跳了 `validateGraphNodes` 让 filePath-missing bug 隐藏。v1.2 复发场景：

- 新加 v1.2 fixture 时，validate.py 的 v1.2 path 跑 schema 校验，但忘了跑 `_fixture_consistency_check` 扩展（v1.1 已对 v1.1 fixture 做了 ID 一致性，v1.2 speaker_id ↔ character refs 一致性需要新加）。
- verify_contract.py 跑 producer mode 时对 audio_semantic.json 用 v1.2 schema 校验绿，但 cross-version check 跳了 v1.2 fixture 对 v1.1 schema 的 backward 检查 → 共享字段漂移隐藏。
- 新 step_audio_semantic 的 smoke verify（如 verify_phaseN_smoke.py）三场景全绿，但其中「cache-hit-offline」场景的 cache 是 v1.1 残留的 stale cache，实际 route-down 路径未触发 → graceful-degrade 假成功。

**Why it happens:**
- 新代码路径的 verify 通常 copy v1.1 verify 模板，但 v1.1 verify 是针对 v1.1 shape 设计的，v1.2 加字段后 verify 没同步加 check。
- 「绿」本身是测过的，但测的是旧路径。v1.1 Phase 9 教训：新 code path 必须镜像 v1.0 path 的 rigor。
- verify 脚本自己有 bug（如 skip Zod on v1.2）时，CI 绿不代表代码对。

**How to avoid:**
1. **每 phase plan-checker 必须列「v1.2 新代码路径对应的 verify 路径」表** —— 每条新路径必须有镜像 v1.1 rigor 的 verify。
2. **Phase 2 contract phase 结束时跑一次「故意漂移」self-test**（v1.1 PHASE4_SELF_TEST 模式）：注入坏 audio_semantic.json（如 speaker_id 格式错），verify 必须 fail-loud。
3. **fixture 一致性扩展**：v1.1 `_fixture_consistency_check` 已查 character_refs ⊆ characters[].id 等；v1.2 加 `speaker_character_map.speaker_id ⊆ audio_semantic.speakers[].id` + `speaker_character_map.character_id ⊆ characters[].id`。
4. **verify_phase{N}_smoke.py 三场景必跑且必真**：route-up（真路由或 mock）、route-down（preflight fail 模拟）、cache-hit-offline（cache 必是 fresh 写入的，不是 v1.1 残留）。
5. **CR phase（code review）必须 grep `skip|pass|TODO` 在新 verify 脚本里** —— 任何 skip 都需显式文档化原因。

**Warning signs:**
- Phase 2+ 出现新 fixture 但 verify 没加对应一致性检查 → blocker。
- self-test 注入坏数据但 verify 绿 → harness 失效 blocker。
- verify_phase{N}_smoke.py 三场景在 5 秒内全绿 → 可能是 cache 残留，重跑 --force。
- code review 看到 `if version == "1.2": pass` 类 skip 逻辑 → 立即问原因。

**Phase to address:** **每 phase（contract + implementation + verify）**。Phase 2 contract 必须先把 fixture-consistency 扩展 + self-test 写完才入 implementation。

---

### Pitfall 11 — XSS `_esc` sink 复发（v1.1 每 phase 都发现的新 sink）

**What goes wrong:**
v1.1 RETROSPECTIVE 列出：「CR-04 XSS lesson carried forward to Phase 8 (title/video_src) — the lesson propagated, though it still found new sinks each phase」。每 phase 给 HTML 加新数据呈现路径就复发。v1.2 新增 XSS attack surface：

- HTML 展示 layered prompt（TTS/music-gen/foley 三套 hint）—— prompt 内容来自 ML 模型输出，模型可能产奇怪字符（虽然不像 user input 那么危险，但 emotion label 如 `<script>` 论理可能）。
- emotion label / instrument label 来自固定 enum，但若模型返回 arbitrary string（route bug），不 escape 会注入。
- speaker_character_map 操作员 review HTML（mirror v1.1 registry_review.html）—— 操作员可能输入任意 review_notes 文本。

**Why it happens:**
- HTML 生成是 Python f-string 模板 + JSON literal embed（`gen_timeline_html.py` 845 行 `build_html`）—— 每加一个字段就要 `_esc()` 一次。
- v1.1 已有 `_esc` helper（`gen_timeline_html.py` 的 CR-04 fix），但新字段忘了调。
- 操作员 review HTML（gen_registry_review 模式）的 review_notes 是直接 user input，XSS 风险最高。

**How to avoid:**
1. **Phase 2 任何新 HTML generator 必须用 v1.1 的 `_esc` helper** —— grep `_esc(` 在新文件里出现的次数 == 新嵌入字段数。
2. **emotion/instrument label 在 producer 侧 enum-locked** —— 即使模型返回 arbitrary string，producer 投影到固定 enum（不匹配 → 空 + warning）。enum 内字符串无 XSS 风险。
3. **layered prompt 字段在 HTML 用 `<textarea readonly>` 或 data-attribute** —— 不直接 innerHTML 注入。
4. **speaker_character_map review HTML 沿用 gen_registry_review.py 的 XSS hardening**（CR-04 verbatim）。
5. **Phase 2+ code review 必须列新 HTML 嵌入点 + 标注每点的 escape**。

**Warning signs:**
- 新 HTML generator 里 `innerHTML =` 出现但前面没 `_esc` → blocker。
- emotion/instrument 字段在 schema 里是 arbitrary string 而非 enum → blocker。
- code review 没列新嵌入点 → blocker。

**Phase to address:** **每 phase（HTML 修改 phase）**。**DEGRADATION-acceptable**：单 XSS sink 不阻塞契约，但 ship 前必修。

---

### Pitfall 12 — `__file__`-in-`python3 -c` 验证 snippet 复发（v1.1 Phase 7 复发教训）

**What goes wrong:**
v1.1 RETROSPECTIVE：「`__file__`-in-`python3 -c` blocker recurred in Phase 7 planning — the Phase 6 close-fix had fixed it in code, but the Phase 7 PLAN re-introduced it in verify blocks」。

Pattern：plan / verify snippet 写 `python3 -c "from pathlib import Path; print(Path(__file__).parent)"`，但 `python3 -c` 模式下 `__file__` 是 `"<stdin>"`，没有 parent。Plan-checker 在 v1.1 抓过，但 plan 作者 copy-paste 旧 snippet 容易再引入。v1.2 plan 数量预计 ≥ v1.1（16 plans），复发概率高。

**Why it happens:**
- 没有项目级 lint 规则禁止 `__file__` in `-c` mode。
- copy-paste 旧 verify snippet 是 plan 作者的自然行为。
- v1.1 没有 commit hook 自动检测。

**How to avoid:**
1. **Phase 1 plan template 加显式 warning**：「不要在 `python3 -c` 用 `__file__`，改用 `os.path.abspath` 或具体路径」。
2. **plan-checker 必跑 grep**：`grep -rn '__file__' .planning/phases/*/0*-PLAN.md` 配合 `grep -B2 -A2 'python3.*-c'`，找出 -c 模式 + `__file__` 共现。
3. **项目级 test**：`.planning/phases/verify-no-file-in-c.sh` 扫所有 plan + verify 脚本。

**Warning signs:**
- plan 里 `python3 -c "...__file__..."` 出现 → blocker。
- verify 脚本在 `cwd != repo root` 跑失败 → `__file__` 相对路径信号。

**Phase to address:** **每 phase plan-checker**。**DEGRADATION-acceptable**：纯文档/机械错误，不阻塞实现。

---

## Moderate Pitfalls

### Pitfall 13 — 多模态时间分辨率聚合歧义（shot / turn / word / frame 边界不对齐）

**What goes wrong:**
v1.2 四种时间分辨率：
- shot 边界（V3b 检测，秒级）
- WhisperX word 边界（毫秒级）
- pyannote speaker turn 边界（百毫秒级）
- MIR frame 边界（如 50ms hop）

一个 shot 跨多 speaker turn，一个 turn 跨多 word，一个 word 跨多 MIR frame。Per-shot 聚合时歧义：
- shot 的 emotion 是所有 word/turn emotion 的 mode？mean？weighted by duration？
- shot 的 dominant_speaker 是 duration 最长的 speaker？发声次数最多的？
- shot 的 tempo 是该 shot 内 MIR 估计的 mode？

不锁规则 → 操作员无法预测，下游消费者（canvas、layered prompt 生成器）拿到的 per-shot 字段语义不一致。

**How to avoid:**
1. **Phase 2 contract 文档化聚合规则**：每字段标 `{level, aggregation}` —— 如 `dominant_speaker: {level: "shot", aggregation: "max_duration"}`。
2. **保留底层分辨率数据**：`audio_semantic.json` 不只 emit per-shot 聚合，也 emit per-turn / per-word（在 optional `turns[]` / `words[]` 字段），让下游 canvas 可自行聚合。
3. **聚合规则优先选「max_duration」**（语义最直观），「mode」（适合 emotion）。「mean」对分类字段不适用。

**Warning signs:**
- 字段无 aggregation 标签 → blocker。
- 下游 layered prompt 生成器在不同 shot 跑出 inconsistent 输出 → 聚合歧义信号。

**Phase to address:** **Phase 2 contract**。

---

### Pitfall 14 — pyannote/WhisperX 模型下载几十 MB～GB 级，首次跑超时

**What goes wrong:**
首次跑路由时，pyannote segmentation-3.0 (~100MB) + speaker-diarization-3.1 (~100MB) + wav2vec2 alignment (~1GB) + Whisper large-v3 (~3GB) 全要下载。若 kais-aigc-platform 路由侧未预热，Phase 1 risk-validation 第一次跑会 timeout（v1.1 默认 960s 客户端 / 900s 路由侧 execFileSync）。

**Why it happens:**
- HF 下载速度依赖网络 + HF CDN。
- 模型缓存在 `~/.cache/huggingface`，首次冷启动慢。
- v1.1 已观察到 Whisper large-v3 首跑 ~3GB 下载。

**How to avoid:**
1. **Phase 1 risk-validation 第一步显式预下载所有模型**：路由侧跑 `python -c "from transformers import ...; .from_pretrained(...)"` 触发下载，再开始计时。
2. **Phase 2 client 实现 `--model-cache-dir` flag**（透传给路由侧），允许操作员指定预下载位置。
3. **首次跑 timeout 不视为模型不可用** —— 区分「下载慢」与「模型不准」。

**Warning signs:**
- Phase 1 第一次跑直接 timeout → 可能是下载而非模型问题。
- `~/.cache/huggingface` 在首跑前后大小不变 → 模型未下载成功。

**Phase to address:** **Phase 1 risk-validation**。**DEGRADATION-acceptable**。

---

## Minor Pitfalls

### Pitfall 15 — `dominant_type` 门控 tempo 但现有字段未必可信

**What goes wrong:**
Pitfall 6 建议「tempo 仅在 `dominant_type ∈ {music, mixed}` 时 emit」。但 v1.0 `audio_analysis.json#shots[].dominant_type` 是基于 RMS + spectral centroid 启发式，本身有 ~20% 误分类（v1.0 baseline 论文未严格验证）。

**How to avoid:**
1. **额外加 MIR 自己的 confidence**（来自 MIRFlex / AudioSet），低 confidence → 不 emit tempo。
2. **producer emit 时双门控**：dominant_type + MIR confidence 都过阈值才写 tempo。

**Phase to address:** **Phase 2 music implementation**。

### Pitfall 16 — `_safe_error` 在 audio_analysis 路由 401 时回显 HF_TOKEN

**What goes wrong:**
v1.1 已加 `_safe_error` 抹 `user:pass@`，但 v1.2 audio-analysis 路由可能在 401 时返回 HF_TOKEN 在 error message 里（HF 错误响应偶尔包含 auth header echo）。Token 流进 warnings sidecar → asset.json#generator.warnings 外发 → token 泄漏。

**How to avoid:**
1. **`_safe_error` 扩展**：除 URL userinfo 外，也 grep `hf_`、`token=`、`Bearer ` 模式抹掉。
2. **路由侧不回显 auth header**（跨仓库 PR 纪律）。
3. **producer 端 warning 内容做白名单**（只允许特定 prefix 如 `[dialogue]`、`[music]`、route-down 标准消息）。

**Phase to address:** **Phase 2 implementation**。

---

## Integration Gotchas（跨服务集成常见错误）

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| WhisperX backend | 替换 faster-whisper（破坏 v1.1 fallback） | 新增 `whisperx` 为 backend 选项，`auto` 顺序 whisperx→faster-whisper→openai-whisper；保留 v1.1 try/except 结构 |
| pyannote 3.1 HF gated | 内联 HF_TOKEN 在 shot-timeline | token 仅在 kais-aigc-platform 路由侧 env var；shot-timeline 永不持有凭据 |
| MIR on Demucs stems | 只在 other.wav 跑 | 在 drums/bass/other 三 stem 各跑一次，结果 union；vocals.wav 跳过 |
| emotion2vec cross-lingual | 直接用 RAVDESS pretrained | Phase 1 必跑中文验证，<50% F1 → 子项 deferred |
| audio-analysis 路由（v1.2 新） | 等路由 merge 才开始 producer | producer 先行，路由用 stub envelope，graceful-degrade 承载 |
| layered prompt → 生成模型 | over-promise 还原精度 | hint-not-spec，confidence 显式，fidelity_disclaimer 字段 |
| warnings sidecar cross-step | 单 step 覆盖他 step warnings | READ-merge-write（v1.1 call_reid.py:443-449 STEP_TAG 模式） |
| `_cache_key` 四元组 | 漏 route_name（v1.1 WR-04 fixed） | helper 强制全四元组，新增 route_name 必填 |
| speaker_character_map HITL | producer 自动映射（无 HITL） | confirmed-only，镜像 v1.1 apply_edits.py；draft → review → canonical 三步 |
| verify harness 新代码路径 | copy v1.1 verify 但跳 v1.2 path check | 每个新路径镜像 v1.1 rigor + self-test 注入坏数据 fail-loud |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| WhisperX 在长音频对齐漂移 | 词时间戳偏差 0.5-2s | Phase 1 长音频测试 + word-level field optional | ≥ 30min ep |
| pyannote clustering 在 100+ speaker 视频超时 | 路由侧 900s 超时 | Phase 1 测试 + 显式 max_speakers 上限（如 15） | 群杂/合唱镜头 |
| Demucs + MIR 三 stem union 显存峰值 | OOM | 路由侧 batch 处理 + `--device cuda:1` 单卡 | 多集批量处理 |
| per-shot cache 文件爆炸 | inode 耗尽 | 每 shot ≤ 4 cache 文件（4 stem），定期清理 | ≥ 1000 shot 视频 |
| audio_semantic.json 单文件过大 | HTML 嵌入后超浏览器解析能力 | 分文件（dialogue.json / music.json / sfx.json）或外置 | 单集 dialogue segments ≥ 5000 |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| HF_TOKEN 流进 warnings sidecar | token 泄漏随资产外发 | `_safe_error` 扩展 + 路由侧不回显 + warning 白名单 |
| `_safe_error` 漏 HF token pattern | 同上 | 正则 `(hf_[a-zA-Z0-9_]+ \| token=\w+ \| Bearer\s+\w+)` 抹掉 |
| XSS in layered prompt HTML | 模型返回 string 含 `<script>` 注入 | producer enum-lock + HTML `_esc` + textarea readonly |
| operator review_notes 注入 | user-input XSS | 沿用 gen_registry_review.py 的 _esc hardening |
| operator speaker_character_map 任意 character_id 注入 | 引用未注册 character | producer 校验 ⊆ characters.json IDs（v1.1 attach_refs 模式） |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| 分层 prompt 无 fidelity_disclaimer | 用户期望还原失败后失去信任 | 字段 + README 明示 hint-not-spec |
| emotion 标签无 confidence | 用户无法判断可信度 | label + confidence 一起展示，低 confidence 标 `~` |
| speaker_id 直接显示 SPEAKER_01 | 用户不知道是哪个角色 | HTML 双显示（SPEAKER_01 + 映射的 character，若有） |
| 多 speaker shot 只显一个 | 信息丢失 | 列出全部 speakers + 占比 |
| tempo 在对话镜头显示 bogus bpm | 误导操作员 | dominant_type 门控 + null fallback |
| 乐器单标签 | 多乐器叠加丢失 | list + confidence |

---

## "Looks Done But Isn't" Checklist

- [ ] **dialogue 模态：** 词级时间戳齐全 — 验证 word-level 字段在 ≥ 90% segments 非空（长音频漂移会让部分词缺失）
- [ ] **dialogue 模态：** speaker_id 全 shot 覆盖 — 验证无 `speaker_id: null` 在有声 shot（无声 shot 应有 `silent: true`）
- [ ] **music 模态：** tempo 门控 — 验证 dialogue 镜头 `tempo: null`
- [ ] **music 模态：** 乐器 list — 验证至少 1 个 confidence ≥ 0.5 的乐器，否则 `instruments: []`
- [ ] **sfx 模态：** foley 描述 — 验证 dialogue-only shot 不 emit foley（避免「人声」被当 sfx）
- [ ] **layered prompt：** 三套（TTS/music-gen/foley）齐全 — 验证任一缺失有 warning
- [ ] **schema 1.1→1.2：** audio_analysis.json 字节不变 — `git diff v1.1..v1.2 -- spec/schemas/audio_analysis.schema.json` 0 行
- [ ] **schema 1.1→1.2：** v1.0/v1.1 fixture 对 v1.2 schema 仍 valid — verify_contract.py forward compat 0 错
- [ ] **schema 1.1→1.2：** SCHEMA_VERSION 单源 — grep `'"1\.[12]"'` 排除 SCHEMA_VERSION 行后为空
- [ ] **schema 1.1→1.2：** validate.py 三阶 shape gate 全跑 — MINIMAL/V11/V12 fixture 缺失任一 fail-loud
- [ ] **cache：** per-shot vs per-video 粒度正确 — dialogue=per-video，SER/MIR=per-shot
- [ ] **cache：** warnings sidecar READ-merge-write — step_audio_semantic 后 step_semantic/step_reid warnings 仍在
- [ ] **cache：** video_stamp sidecar 在新 output 文件 — audio_semantic.json.video-stamp 存在
- [ ] **banner：** `[N/9]` count == 9 — grep `\[[0-9]/9\]` run_pipeline.py == 9
- [ ] **graceful-degrade：** route-down 场景三模态全空字段 asset 仍导出 — verify_phase{N}_smoke.py 跑证
- [ ] **graceful-degrade：** warning sidecar 记失败原因 — route-down 后 warnings.json 非空
- [ ] **HITL：** speaker_character_map producer emit draft（不自动 confirmed） — apply_edits 模式镜像
- [ ] **XSS：** 新 HTML 嵌入点全 _esc — grep `_esc(` 在新文件 == 嵌入字段数
- [ ] **跨仓库：** audio-analysis 路由分支已建（即使 stub） — Phase 2 起 producer 有 target
- [ ] **跨仓库：** deferred 列表 ship 时文档化 — milestone audit 列入 deferred

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| 中文 SER 跨域失败 | LOW | emotion 字段 emit 空串 + warning；schema 仍带 optional 字段；后续 milestone 换中文 fine-tune 模型 |
| WhisperX 词级漂移 | MEDIUM | 切回 segment-level fallback；词级字段在 schema 仍 optional；用户拿到无词级但仍有 segment |
| pyannote 准入失败 | LOW | diarization 子项 deferred；speaker_id 字段空；TTS prompt 不带 speaker info |
| pyannote speaker-count 错 | MEDIUM | 调 cluster 阈值；加 max_speakers；失败则单 speaker 假设 + warning |
| speaker↔character mapping 失败 | LOW | SPEAKER-01 子项 deferred；speaker_id acoustic 层仍 emit；mapping 留空 |
| 契约 byte-identical-absent 破裂 | HIGH | 回滚 audio_analysis.schema.json 改动；新字段迁回 sidecar audio_semantic.json；已 emit 数据重导 |
| validate.py shape drift | LOW | 加 fixture + 重跑 validate.py；常量重命名 |
| [N/8]→[N/9] banner 漏改 | LOW | grep 扫 + 改；helper 化 banner counter |
| 多模态聚合歧义 | MEDIUM | 文档化聚合规则；保留底层分辨率数据；下游 canvas 自行聚合 |
| XSS sink 复发 | LOW | 加 `_esc` 调用；enum-lock label；CR 检查 |
| `__file__`-in-c 复发 | LOW | plan-checker grep；改 `os.path.abspath` |
| 跨仓库路由未 merge | LOW | graceful-degrade 已 proven；deferred 列表文档化 |

---

## Pitfall-to-Phase Mapping

| Pitfall | Class | Prevention Phase | Verification |
|---------|-------|------------------|--------------|
| 1. 中文 SER 跨域 | BLOCKER | Phase 1 risk-validation | ep01 抽样人工标注 + F1 ≥ 0.5；不足 → 子项 deferred，schema optional |
| 2. WhisperX 破坏 fallback | BLOCKER | Phase 1（漂移测试）+ Phase 2 dialogue（叠加 backend） | 长音频对齐偏差 < 1s；v1.1 try/except 仍在；whisperx backend 失败时 fallback 走通 |
| 3. pyannote 准入/speaker-count/overlap/mapping | BLOCKER | Phase 1（HF 准入 + ep01 验证）+ Phase 2 contract（speaker↔char 解耦）+ Phase 2 dialogue（HITL map） | token 在路由侧不在 producer；speaker_id acoustic 层；HITL confirmed-only |
| 4. schema 1.1→1.2 byte-identical-absent | BLOCKER | Phase 2 contract | `git diff` audio_analysis.schema.json 0 行；SCHEMA_VERSION 单源；三阶 shape gate |
| 5. [N/8]→[N/9] banner | ACCEPTABLE | Phase 2 implementation + 每 phase CR | grep count == 9；helper banner counter |
| 6. 多音轨 MIR false-confidence | BLOCKER | Phase 1（精度测试）+ Phase 2 contract（multi-label）+ Phase 2 music（stem union） | 多 label F1 ≥ 0.4；instruments list；dominant_type 门控 tempo |
| 7. 分层 prompt over-promise | BLOCKER | Phase 2 contract（disclaimer + confidence） + HTML phase（estimated 标签） | fidelity_disclaimer 字段；README 无 over-promise 字样 |
| 8. cache 粒度混淆 | BLOCKER | Phase 2 contract + helper | 粒度表文档化；helper 强制；READ-merge-write |
| 9. 跨仓库路由未 merge | ACCEPTABLE | 每 producer phase（graceful-degrade proven） | route-down 三场景 verify；deferred 列表 |
| 10. green verify 隐藏 blocker | BLOCKER | 每 phase（plan-checker + self-test） | 故意漂移 fail-loud；新代码路径镜像 v1.1 rigor |
| 11. XSS `_esc` sink 复发 | ACCEPTABLE | 每 HTML phase | grep `_esc(` count == 嵌入字段；enum-lock label |
| 12. `__file__`-in-c 复发 | ACCEPTABLE | 每 phase plan-checker | grep `python3.*-c.*__file__` 为空 |
| 13. 多模态聚合歧义 | BLOCKER | Phase 2 contract | 字段标 `{level, aggregation}`；保留底层分辨率 |
| 14. 模型下载超时 | ACCEPTABLE | Phase 1 risk-validation | 显式预下载；首跑 timeout 不视为模型不可用 |
| 15. dominant_type 误分类 | ACCEPTABLE | Phase 2 music | 双门控（dominant_type + MIR confidence） |
| 16. HF_TOKEN 泄漏 | BLOCKER | Phase 2 implementation | `_safe_error` 扩展；warning 白名单 |

---

## BLOCKER vs Acceptable 总览

**BLOCKER-class（必须解决才能 ship，解决不全则 milestone audit 列入 deferred）：**
- Pitfall 1（中文 SER 跨域）—— 可降级（emotion 字段空）但 Phase 1 必须证伪
- Pitfall 2（WhisperX fallback）—— 必须 implementation 时保留 v1.1 fallback 路径
- Pitfall 3（pyannote 准入 + speaker mapping HITL）—— 准入流程文档化 + HITL 不容妥协
- Pitfall 4（schema 1.1→1.2 byte-identical）—— Phase 2 contract 硬规则
- Pitfall 6（MIR false-confidence）—— 可降级（空 instruments）但 Phase 1 必须证伪
- Pitfall 7（layered prompt over-promise）—— Phase 2 contract + 文档硬规则
- Pitfall 8（cache 粒度混淆）—— Phase 2 helper + 文档
- Pitfall 10（green verify 隐藏 blocker）—— 每 phase 纪律
- Pitfall 13（多模态聚合歧义）—— Phase 2 contract 文档化
- Pitfall 16（HF_TOKEN 泄漏）—— Phase 2 implementation 硬规则

**DEGRADATION-acceptable（route-down / 子项失败时 schema 合法，warning sidecar 记录，milestone 仍 ship）：**
- Pitfall 5（[N/9] banner 漏改）—— 机械错误，CR 抓
- Pitfall 9（跨仓库路由未 merge）—— v1.1 模式已证明
- Pitfall 11（XSS sink 复发）—— 每 HTML phase CR 抓
- Pitfall 12（`__file__`-in-c）—— plan-checker grep
- Pitfall 14（模型下载超时）—— Phase 1 预下载
- Pitfall 15（dominant_type 误分类）—— 双门控兜底

---

## Sources

**v1.1 仓库内部锚点（HIGH 置信度）：**
- `.planning/RETROSPECTIVE.md` — 9 blocker + 22 warning 复发模式
- `.planning/PROJECT.md:25-32` — v1.2 决策（schema 1.1→1.2 sidecar、SPEAKER-01 in scope）
- `.planning/PROJECT.md:97-104` — Constraints（不动核心算法、契约 minor bump、媒体服务）
- `.planning/MILESTONES.md` — v1.1 deferred 列表（shot-analysis route + character-reid route）
- `analysis/call_shot_analysis.py` — per-shot cache + graceful-degrade + warnings sidecar 模式
- `analysis/call_reid.py` — per-video cache + READ-merge-write + STEP_TAG 模式
- `run_pipeline.py:101-105`（run_step banner）+ 17 处 `[N/8]` 字面量
- `run_pipeline.py:296-313`（step_reid 两子进程模式，v1.2 step_audio_semantic 类比）
- `spec/validate.py:46-71`（MINIMAL/V11_ORDER 三阶 shape gate 已存在，v1.2 加 V12_ORDER）
- `scripts/verify_contract.py:74-82`（EIGHT_SHAPES / SIX_SHAPES 常量已不准确）
- `scripts/verify_contract.py:319-385`（_cross_version_check v1↔v1.1，v1.2 需扩展 v1.1↔v1.2）
- `scripts/verify_contract.py:388-488`（_fixture_consistency_check v1.1，v1.2 加 speaker↔character）

**v1.1 milestone phase archives（HIGH，v1.2 直接复用模式）：**
- `.planning/milestones/v1.1-phases/05-contract-v1-1/` — Contract phase 模式
- `.planning/milestones/v1.1-phases/06-cinematography-auto-fill-step-semantic/` — thin httpx client + graceful-degrade
- `.planning/milestones/v1.1-phases/07-cross-shot-re-id-registry-hitl-review-step-reid/` — HITL confirmed-only 模式
- `.planning/milestones/v1.1-phases/08-prompt-reference-system-shot-timeline-html-gallery/` — attach_refs 模式 + XSS CR-04

**ML 模型文档（MEDIUM-HIGH，web 验证）：**
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — WhisperX 同后端
- [WhisperX architecture overview (vexascribe)](https://vexascribe.com/whisperx) — 词级 forced alignment via wav2vec2
- [Modal blog: faster-whisper vs WhisperX](https://modal.com/blog/choosing-whisper-variants) — WhisperX 牺牲 speed 换 alignment + diarization
- [pyannote/speaker-diarization-3.1 (HF)](https://huggingface.co/pyannote/speaker-diarization-3.1) — gated repo 准入流程官方文档
- [HF Discuss: pyannote 401 / authorized list](https://discuss.huggingface.co/t/cannot-access-gated-repo-for-pyannote-speaker-diarization-3-1-restricted-and-you-are-not-in-the-authorized-list/171972) — 准入常见失败
- [pyannote licensing (HF Discuss)](https://discuss.huggingface.co/t/licensing-and-commercial-use-of-pyannote-for-visionaryai-tagger-investor-backed-project/167631) — 3.1 MIT license

**Cross-domain SER / MIR（MEDIUM，文献级，需 Phase 1 实测）：**
- RAVDESS / IEMOCAP 训练分布 vs 中文动画对白 — 跨域 ER 是已知学术问题（CCSER、EMO-DB 跨语言 transfer 学习论文）
- MIRFlex / MERT / AudioSet VGGish — 多音轨 polyphonic 识别精度文献
- Demucs htdemucs SDR 4-8dB（paper）— stem bleed 量化

**Confidence 自评：**
- 仓库内部 pitfalls（1-12、14、15 中关于本仓库模式的部分）— HIGH（直接源码锚定）
- WhisperX/pyannote 模型行为 pitfalls（2、3、6、14）— MEDIUM-HIGH（官方文档 + 社区 issue tracker 支撑，但 v1.2 Phase 1 实测才能 100% 确认）
- 中文 SER 跨域、MIR 乐器识别精度具体阈值 — MEDIUM（文献支撑趋势，但本仓库 ep01 实测未做）

---
*Pitfalls research for: v1.2 音频语义深化 — SER + diarization + MIR + layered prompts + schema 1.1→1.2 bump*
*Researched: 2026-07-25*
