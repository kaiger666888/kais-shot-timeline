# Pitfalls Research — kais-shot-timeline v1.1

**Domain:** 向 validated 多轨道分镜资产管线（v1.0 ShotTimelineAsset 契约）追加：① 路由化镜头语言填充、② 跨镜角色/道具 re-id 注册表、③ prompt 引用系统、④ 契约 v2 minor bump、⑤ 画布新节点类型 — 在保持向后兼容与离线鲁棒性的前提下。
**Researched:** 2026-07-24
**Confidence:** HIGH（pitfalls 直接锚定本仓库 SPEC.md / schemas / verify_contract.py / RETROSPECTIVE.md，以及 cross-repo `canvasAssetSchema.ts` / `import-from-dir.ts` 源码；ML 类 pitfalls 由 CC-ReID 学术文献支撑）

> **如何读这份文档：** 每条 pitfall 都按 `出了什么 → 为什么 → 怎么预防 → 预警信号 → 应在哪个 phase 解决` 给出。最后的「Pitfall-to-Phase Mapping」表把所有 pitfalls 浓缩成 planner 可直接派进 ROADMAP 的核验项。
> **关于契约的措辞：** 当本文说「breaking change」时，**逐字** 采用 `spec/SPEC.md` §4 + `asset.schema.json#schema_version.description` 的定义——
> > "New field = minor bump; **breaking change (rename/semantic shift/removal) = major bump** ... Add required field = major bump."
>
> v1.1 决定是 **minor bump（`"1"` → `"2"`）**——见 `.planning/PROJECT.md` Constraints。所以下面凡是会触发 rename/语义漂移/删除/新增必填字段的，都是 **致命** pitfall，不是「权衡」。

---

## Critical Pitfalls

### Pitfall 1 — Re-ID 嵌入模型选错模态（face / body / clothing）

**出了什么问题：**
跨镜 re-id 的相似度信号一开始就走偏。三种常见错配：① 用 face embedding（ArcFace / FaceNet）做远景镜头（人脸 < 30px），全部 embedding 退化为噪声，跨镜识别变随机；② 用 full-body / clothing embedding（OSNet、BoT、person-reid checkpoints）处理换装角色（多集 OVA 角色变身、反派揭晓、回忆杀换色），同一身份被拆成 N 个 cluster；③ 用 full-body embedding 处理特写镜头（只有脸），embedding 缺身体语义 → 与全身镜次距离过大 → 过分裂。

**为什么会发生：**
开发者默认把"re-id = person re-id = 用 OSNet/BoT 跑全身"当通用答案，没有意识到 CC-ReID（Cloth-Changing Re-ID）是一个独立子领域，而面部识别又是一个完全不同子领域。在没有标注数据校准阈值的情况下，单模态 embedding 在边界场景（特写 / 远景 / 换装）系统性失效。

**怎么预防：**
- **双模态 + 融合，而非单模态。** 同时跑 face embedding（小脸检测器 + ArcFace）和 full-body / clothing embedding（OSNet-x1.0）。相似度 = `max(face_sim if face_detected, body_sim * w_body)`。任一模态缺失时降级为单模态。
- **把"哪一镜用了哪个模态主导"记进注册表元数据**（`characters[].shots[].modality: "face" | "body" | "fused"`），让人工 review 能按 modality 排序看异常。
- **小脸阈值硬线：** 裁出的人脸宽度 < 32px（或检测器置信度 < 阈值）→ face embedding 视为缺失，禁用 face_sim，不强制算。
- **接受 `OUT OF SCOPE` 决策：** `.planning/PROJECT.md` 已写明"完全自动 re-id — Out of Scope"，所以 v1.1 不必追求 SOTA，但要保证人工 review 看到的 candidate merge/split 列表是「双模态都判同」+「单模态判同」+「两模态打架」三类分组，让 reviewer 能精准操作。

**预警信号：**
- 注册表里出现大量 2-3 镜的「孤儿 character」（典型过分裂，full-body 模态在远景/特写边界失效）。
- 同一角色在 ep01 的不同镜次中出现 >5 个 cluster（检查是否换装镜头未被识别）。
- 注册表里同一 character 的 thumbnails 看起来都像但 review 反馈"这明明不是同一个人"（典型过合并，face embedding 在远景镜头被噪声主导）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表（设计子 phase）。** 落地前必须先 spike：ep01 上跑双模态 + 看分布，把模态选择写进 phase 设计文档。不要在 production code 里写死单模态。

---

### Pitfall 2 — 聚类阈值敏感：过合并 vs 过分裂

**出了什么问题：**
re-id 聚类只有一个全局阈值。设高了（cosine > 0.7 才算同一人）→ 同一角色换装、不同角度、阴影下被拆成多个 cluster（**过分裂**），注册表里有 20 个 "小江湖少女" 条目。设低了（cosine > 0.3 都算同一人）→ 不同角色但服装 / 发色相似的镜次被合并（**过合并**），注册表里反派主角挤在一个 character id 下。**没有"正确"的阈值**——任何固定值在某些镜次上都是错的。

**为什么会发生：**
开发者把聚类阈值当超参，跑一遍看效果，调到看起来"差不多"的值就提交。但阈值对每个 episode、每种画面风格（动画 vs 真人）、每个镜头采样策略都敏感。v1.1 处理的是多支成片，单一阈值在跨片场景下必然漂移。

**怎么预防：**
- **三档阈值 + 人工 review 优先级排序，而非二分合并。**
  - `high_confidence_merge` (e.g. cosine > 0.85 且双模态都判同) → 自动合并，不打扰 reviewer。
  - `review_required` (0.6 ~ 0.85) → 列入 review 队列，按相似度排序展示给 reviewer。
  - `high_confidence_distinct` (< 0.6) → 自动判不同，不进 review。
- **阈值是 phase 1 spike 的输出，不是常量。** 在 ep01 上画 cosine 分布直方图（同一人 vs 不同人），用分布的"波谷"作起点，而不是凭直觉选 0.7。
- **reviewer 的 split/merge 操作要能写回 ground truth**，作为后续 episode 阈值校准的微调数据。
- **警惕 silhouette / DBSCAN 自动调参**：CC-ReID 文献明确指出，在低 SNR 嵌入空间上，自动聚类算法（DBSCAN、HDBSCAN）会退化成"按镜头采样密度聚类"而非"按身份聚类"。优先用 supervised threshold + 人工兜底，不要把决策完全交给自动聚类。

**预警信号：**
- 注册表里同一 character 的 thumbnail 集合突然出现两批明显不同的人。
- review 队列里 >50% 是 split 操作（说明阈值偏低 → 过合并），或 >50% 是 merge 操作（说明阈值偏高 → 过分裂）。
- 同一 character 在不同 shot 的 `modality` 字段频繁切换（说明两模态相似度都在阈值边缘反复横跳）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表。** 阈值设计是这 phase 的核心交付物之一，不能拖到「双端展示」phase 才发现。

---

### Pitfall 3 — 换装 / 造型变化导致 identity drift

**出了什么问题：**
角色在 ep 中段换装（变身、回忆杀、雨天湿身、反派揭晓），同一身份被拆成 2-3 个 cluster。reviewer 手动 merge 后，注册表的"演员表"条目含多套服装；下游 prompt 引用 `{character_id: ch_001}` 时，prompt 还原出的"角色描述"在换装前后会漂移。

**为什么会发生：**
CC-ReID（Cloth-Changing Person Re-ID）是 re-id 学界的开放问题。文献（[Gu CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/papers/Gu_Clothes-Changing_Person_Re-Identification_With_RGB_Modality_Only_CVPR_2022_paper.pdf), [Cloth-Changing Survey 2024](https://www.researchgate.net/publication/401226752)）明确指出：**服装是最强的视觉信号**，靠 clothing 主导的 embedding 在换装场景下系统性失效。任何全身 embedding 都有这个问题。

**怎么预防：**
- **每个 character 条目支持多个 "look" 子条目。** 注册表 schema（v2 新增）应允许 `characters[].looks: [{look_id, first_seen_shot, last_seen_shot, description, thumbnail_set}]`。换装后是同一 character 的不同 look，prompt 引用 character 时携带 `look_id` 做还原。
- **face embedding 在换装场景下是兜底。** 即使服装全变，脸（在特写镜次中）能拉住 identity。
- **reviewer 显式标注 "costume change" 操作。** 当 reviewer 把两个 cluster 标记为同一 character 的不同 look（而非简单 merge），schema 把这条信息保下来——`character.looks[]` 而非合并 thumbnail。
- **永远不删 thumbnail。** 即使 merge 后，原 cluster 的 thumbnail 保留为 `archived_thumbnails`，避免后续 review 误判时丢信息。

**预警信号：**
- 注册表里同一 character 有 >3 个 thumbnail 但 reviewer 没标 costume change（提示可能漏标）。
- prompt 引用 character 描述时，description 字段在 shot 之间跳变（提示没区分 look）。
- 跨镜识别 confidence 在 ep 中段突然下降（提示换装时刻未捕获）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表（schema 设计阶段）。** schema 必须一开始就支持 `looks[]`，否则后期重做要 migrate 数据。

---

### Pitfall 4 — 背景泄漏进 embedding

**出了什么问题：**
re-id embedding 直接吃 SAM3 切出的 mask 边界框。如果 mask 略大于主体（含一部分背景：街道、家具、配角），embedding 把这部分背景也算进去。结果：同一角色站在不同背景前 → embedding 距离变大 → 过分裂；不同角色站在同一背景前（如同一房间）→ embedding 距离变小 → 过合并。背景成为相似度的主要信号。

**为什么会发生：**
SAM3 的 mask 不是像素级精准，尤其在 hair / 手部 / 衣服飘动处会 leak（见 Pitfall 6）。如果 re-id 流程直接 `crop = bbox(mask) → resize → embedding()`，bbox 不可避免地含一点背景。问题出在 re-id 流程吃 SAM3 输出前没有做 mask-to-crop 的精修。

**怎么预防：**
- **mask 用作 alpha 通道，背景填中性灰（128,128,128）或图像均值色后再喂 embedding。** 不要直接 bbox-crop。
- **bbox 仅作 size sanity check。** 若 bbox 宽高比异常（如 >1:3 或 >3:1），可能是 partial occlusion 切到一半，flag 为 `low_confidence`，不参与 cluster。
- **背景占比指标。** 计算 `mask_pixels / bbox_pixels`。若 < 0.4（背景占 >60%），mask 质量已差，flag 不进 cluster。
- **两阶段裁剪：** SAM3 mask → mask-aware padding（5-10% 外扩）→ 再喂 embedding。这能容忍 mask 边缘误差，又不让背景占主导。

**预警信号：**
- 同一 character 在不同场景（室内 vs 室外）的相似度，显著低于同一 character 在相似场景的不同角度（背景主导）。
- cluster 里某些 thumbnail 的"主体"只占画面 30%（mask 严重 leak）。
- 在「同一角色同一服装」的 ground truth 上，相似度方差极大（说明 embedding 信号被背景噪声主导）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表（mask 后处理子任务）。** mask → embedding 之间的 pipeline 步骤是这 phase 的实现细节，但 schema 必须存 `mask_quality` 元数据让人工 review 能筛。

---

### Pitfall 5 — Identity drift 累积（长视频 / 跨 ep）

**出了什么问题：**
v1.1 的 OUT OF SCOPE 写明"跨成片角色连续性 — 留后续"，所以 v1.1 只在单支成片内 re-id。但在单支成片内（特别是 20 分钟以上的 ep），仍可能出现：① 同一角色 ep 前段（明亮场景）与后段（夜景）的 embedding 分布漂移，cluster 在夜景处断裂；② 跨 ep 角色被识别为不同 character（在 v1.1 范围内是预期行为，但用户可能期待一致）。

**为什么会发生：**
embedding 模型对光照、色温敏感，没有做颜色归一化。单支成片内的"叙事时间跨度"（晨昏、季节、情绪转变）足以让 embedding 漂移。

**怎么预防：**
- **接受单 ep 内漂移存在，但加 temporal smoothing。** 同一 cluster 在 ep 内的 shot 时间序列上应连续；若 cluster 在中段突然消失又后段出现，且中间的 shot 有相似（但低于阈值）的 embedding，应 trigger review 而非自动断开。
- **明确写进 SPEC：** v1.1 character ID 只在单 asset（= 单 ep）内有意义，跨 asset 不保证连续。canvas 消费者必须把不同 asset 的 `ch_001` 视为不同实体。
- **在 character schema 里存 `asset_local_id`（"ch_001"）+ `display_name`（"少女"）两套标识。** 跨 ep 时 display_name 可一致（人工填），但 asset_local_id 必然不同。这样未来 v1.2 跨 ep re-id 时可以平滑引入 `global_character_id` 不破坏 v2 schema。

**预警信号：**
- 同一 character 在 ep 不同时间段被分到不同 cluster。
- 用户反馈"明明是同一个人为什么注册表里有两个"，且发生在 ep 内场景切换处。
- 跨 asset 消费时，canvas 显示多个 `ch_001` 让用户混淆（提示 schema 没把 asset scope 讲清楚）。

**应在哪个 phase 解决：**
**Phase: 契约 v2（schema 设计）+ 跨镜 re-id 注册表。** schema 里的 ID 命名规则必须在 phase 1 就定死，否则 v1.2 跨 ep 时无法平滑升级。

---

### Pitfall 6 — SAM3 单帧切图产物不可用（头发/手/道具截断 + 运动模糊 + 遮挡）

**出了什么问题：**
从首尾帧 SAM3 切出的角色 "sheet"（thumbnail）质量低：① hair 边缘被裁掉（SAM3 mask 在 hair 处边界不精确，crop 出来头顶秃一截）；② 手 / 道具被切掉（mask 只包主体躯干，hands 持物时被排除）；③ 运动模糊帧（首尾帧常是镜头切换瞬间，subject 处于运动状态）→ embedding 退化；④ 部分遮挡（配角在前面）→ mask 切到一半主体。

**为什么会发生：**
首尾帧是分镜检测算法（PySceneDetect + V3b 4-pass）的副产物，**不是为 re-id 选的最优帧**。切换瞬间的帧语义是"边界代表"，运动模糊概率最高。SAM3 文档与第三方评测（[Ultralytics SAM3 docs](https://docs.ultralytics.com/models/sam-3), [Voxel51 analysis](https://sam3ai.com/limitations)）明确指出 **强运动模糊、部分遮挡、hair 等精细结构** 是 SAM3 主要失败模式。

**怎么预防：**
- **不只用首尾帧。** 从 shot 内部采样 N=3-5 帧（如 25%、50%、75% 时位），每帧跑 SAM3，挑 mask quality 最高的作 character sheet。把 `sheet_source_frame_sec` 写进 schema。
- **mask quality 自动评分。** 计算 `mask_area / bbox_area`（应 0.4-0.95）、`mask_boundary_smoothness`（毛刺越多越差）、`mask_confidence`（SAM3 输出）。低分帧标 `low_quality`，进 review 队列。
- **运镜检测器输出用作先验。** v1.1 同时上了镜头语言检测（Pitfall 8 路由），运镜结果能告诉 re-id：「这镜是 handheld / quick pan」→ 跳过这些 shot 的模糊帧采样。
- **reject-low-confidence 是人工兜底前的自动门。** 全 shot 没有一帧 mask quality > 阈值 → 不为这 shot 产 character sheet，标 `sheet_status: "unusable"`，不进 cluster。让 reviewer 看到这 shot 被跳过，而不是塞一个垃圾 embedding 污染聚类。
- **首尾帧仅作 fallback。** 若 shot 内部采样都失败，再用首尾帧。

**预警信号：**
- 注册表 thumbnail 集合里 >20% 的角色看起来头部被切、手被切。
- 同一 character 在不同 shot 的 thumbnail 主体大小差异巨大（10%-90% bbox 占比，说明 mask 质量不稳定）。
- `sheet_status: "unusable"` 的 shot 占比 >15%（说明采样策略对这支成片不合适）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表（sheet 生成子任务）。** 是这 phase 的实现细节，但 sheet 质量元数据必须存进 schema（contract v2 phase）。

---

### Pitfall 7 — Re-ID 全自动幻觉（绕过 human-in-the-loop）

**出了什么问题：**
开发者把 re-id 做成"产出注册表 → 直接进 prompt 引用 → 直接渲染画布"全自动管线，跳过人工 review。结果：错误 cluster 静默进入下游，prompt 引用了错的角色，画布显示错的角色，用户最终看到时已经污染了多个数据文件。修复成本极高——需要回溯重跑多个 phase。

**为什么会发生：**
人工 review 听起来"不工程化"，开发者想用更高的阈值 + 更好的模型"解决"re-id 精度问题。但 CC-ReID 文献明确指出：**SOTA 模型在换装场景下准确率也只有 60-80%**（见 [Cloth-Changing Survey](https://www.researchgate.net/publication/401226752)），不可能 100%。任何"全自动就够"的假设都是错的。

**怎么预防：**
- **注册表 schema 有 `status: "draft" | "reviewed" | "locked"` 字段。** 默认 `draft`，未 review 的 character 不能被 prompt 引用（schema 强制）。
- **review 工具是这 phase 的一等交付物，不是附属脚本。** 类似 v1.0 `scripts/verify_contract.py` 把验证当成核心代码，re-id review HTML / CLI 必须是 phase 的核心 artifact，不是事后补丁。
- **显式遵循 RETROSPECTIVE 模式：** v1.0 的 "Formally-accept-and-document > silently-fix-or-drop" 教训（见 `.planning/RETROSPECTIVE.md` "Key Lessons"）适用——若 review 工具来不及做完，**正式接受为 WR（deferred item）**，绝不静默上线全自动。

**预警信号：**
- 注册表里 character `status` 全是 `draft` 但 prompt 已引用（schema 没强制 → bug）。
- 没有 review HTML / CLI 工具的 phase SUMMARY 直接 ship 了"re-id 完成"。
- character 数量异常（远多于 / 远少于 ep 中出现的人物数）。

**应在哪个 phase 解决：**
**Phase: 跨镜 re-id 注册表。** Review 工具是这 phase 的 IN-SCOPE 必交付物。

---

### Pitfall 8 — 路由依赖让离线管线断网即崩

**出了什么问题：**
v1.0 的 shot-timeline 管线**完全离线**（README 明示无网络调用）。v1.1 把镜头语言填充 + 角色/道具切图都改成调 `kais-aigc-platform` HTTP 路由——管线现在有了硬运行时依赖。如果路由宕机（ComfyUI 重启中、Docker 镜像 landmine、kais-incremental aggregator 没起来——见 user memory `comfyui-primary-node-deploy.md`），或路由分支未 merge（`feat/shot-geometry-nodes` + `feat/shot-analysis-route` 在 PROJECT.md 明确"两分支未 merge"），管线就断。`.planning/RETROSPECTIVE.md` "What Was Inefficient" 已记录 v1.0 Phase 4 实际踩过 quota 429（Whisper 后端）暂停 1.5h，v1.1 把这种风险放大到每个 ep 的每次 run。

**为什么会发生：**
开发者把路由当本地函数调用，没考虑：① 路由分支还在 feat/ 上没 merge → pull 上游后路由消失；② 路由调用是同步阻塞 15 分钟（shot-analysis route `index.ts:102` 的 `timeout: 900_000`），中途断网无重试；③ 第一次 run 用了路由，缓存了结果，但缓存键设计错（如基于 video filename 而非 content hash），第二次 run 用同名不同内容视频时被脏缓存命中。

**怎么预防：**
- **路由输出必须落盘到 `output/<asset>/route_cache/<route>/*.json`，缓存键 = `f"{video_stem}:{shot_id}:{route_version}:{params_hash}"`。** 管线 step 先查缓存，命中就跳过；未命中才发 HTTP。
- **graceful-degrade 语义对齐 Whisper 后端 fallback 模式（`audio/transcribe.py:109-123`）。** 路由失败时：①5xx/timeout → 等待 + 重试 1 次；②429 → exponential backoff（30s, 2min, 5min）；③仍失败 → 标 `prompts[i].camera = ""`（空），asset 仍然生成，HTML 显示 "运镜分析未填充"，**不让管线崩溃**。这与 v1.0 现有的 `--skip-detect` 等降级路径一致。
- **route client 是 step 函数，包在 try/except 里。** 仿照 `run_pipeline.py:run_step` 的 `subprocess.run(..., check=True)` 模式，把 HTTP call 包成 `run_route_or_skip(route_name, ...)`，failure 打印 `[stage] route X failed, degrading` banner。
- **加 `--offline` 全局 flag。** 跳过所有路由调用，只用缓存。这对开发期反复跑 HTML 渲染至关重要。
- **路由版本指纹：** 调用前先 `GET /api/v1/production/shot-analysis/version`（或等价），把路由的 git SHA / driver version 记进 asset.json 的 `generator` 字段。如果路由版本变了，缓存失效，重跑。
- **依赖前置 check：** 管线 step 1 之前加 `preflight_route_check()`：HTTP ping 一下路由 health，若不可达 → 立即提示用户「路由不可用，本 run 将 graceful-degrade，所有镜头语言字段将为空。设 OFFLINE=1 跳过此提示。」，**不要让用户等到第 4 个 shot 才发现路由挂了**。

**预警信号：**
- 管线跑到一半 exit code != 0，错误信息含 "ECONNREFUSED" 或 "HTTP 502"。
- 路由可用但 prompts.json 里 `camera/action` 字段全空（缓存没命中 + 路由静默失败）。
- 路由分支 merge 后旧 cache 仍被复用（缓存键没含 route_version）。
- 单次 run 的 wall-clock 显著高于 v1.0（路由同步阻塞累积）。

**应在哪个 phase 解决：**
**Phase: 镜头语言自动填充（route client 设计子任务）+ 契约 v2（generator 字段加 route_version）。** Route client 必须是这 phase 第一个 deliverable，先于 prompt 字段填充。

---

### Pitfall 9 — 缓存让"离线重跑"和"路由升级"互斥

**出了什么问题：**
为了 Pitfall 8 的离线鲁棒性加了缓存，但缓存策略写错：① 只命中 file-existence，不查路由版本 → 路由分支更新后还用旧输出；② 反过来，每次都 invalidate → 离线 flag 失效；③ 缓存键含 `generated_at` 时间戳 → 永远命中不了；④ 缓存键含绝对路径 → asset 目录搬家后失效。**v1.0 已经踩过类似坑**：RETROSPECTIVE 提到 "Phase 2 executor wiped ep03 caches (`--force + --skip-detect` combo) triggering a background Whisper regen"，这是 `--force` 全清的副作用；v1.1 的 route cache 必须更精细。

**为什么会发生：**
v1.0 的 idempotent caching 是 file-existence 检查（`run_pipeline.py:67,90,108,127,147` 都用 `os.path.exists(out)`），简单但粒度粗。开发者直接套这个模式到 route 输出上，没意识到 route 输出有"上游算法版本"维度（路由升级 → 同一 shot 的运镜分析可能改变），而 shots.json / stems 的"上游算法"是稳定的。

**怎么预防：**
- **缓存键四元组：** `(video_content_hash, shot_id_range, route_name, route_version)`。前三个稳定，第四个通过 preflight 查询路由版本得到。任一变化 → invalidate。
- **`--force-route` 单独 flag，与 `--force` 区分。** v1.0 的 `--force` 是全清；v1.1 要让开发者能"只重跑 route 不重跑 Whisper"。仿照现有 `--skip-detect/--skip-separate/--skip-transcribe` 粒度，加 `--refresh-cinematography` / `--refresh-reid`。
- **绝对路径不入缓存键。** 缓存文件名用相对 asset root 的路径，绝对路径只在运行时算。
- **route_version 是 advisory 不是 blocking。** 路由 health endpoint 不可达时 → 用 "unknown" 占位，缓存仍可命中（不阻塞离线 rerun）。

**预警信号：**
- 用户报告"路由分支 merge 了但 ep 的 prompts.json 没变"。
- 用户报告"我改了 video 文件，pipeline 没重跑 route"。
- 同一 asset 反复跑 → route HTTP 调用次数单调增（缓存键漂移）。

**应在哪个 phase 解决：**
**Phase: 镜头语言自动填充（cache 层子任务）。** Cache 设计是这 phase 的核心实现细节，要写在 phase SUMMARY 里。

---

### Pitfall 10 — 路由部分失败：N 个 shot 中 K 个返回错

**出了什么问题：**
路由 driver 是逐 shot 跑 ComfyUI 工作流（`shot_analysis_driver.py` 单镜一次 ComfyUI submit + history poll）。N=100 镜的 ep 中，第 47 个 shot 因为 ComfyUI OOM / 模型加载失败 / GPU 抖动 返回错。开发者默认 fail-loud（抛异常让整个 step 失败），导致：① 前 46 个 shot 的结果丢失（未落盘）；② 用户被迫完全重跑；③ 离线缓存策略无效（每次都全量重试）。

**为什么会发生：**
开发者沿用 `run_pipeline.py:run_step` 的 `subprocess.run(..., check=True)` 模式，把整个 route step 当作原子单元。但 route driver 内部是 N 次独立调用，不应让一次失败拖垮全部。`shot_analysis_driver.py` 已经把结果按 shot_XXX.json 分文件落盘（见 shot-analysis route `index.ts:114-118` 的 "聚合 driver 落盘的 shot_XXX.json"），但 driver 内部对单 shot 失败的处理未必把已成功的先 flush 到磁盘。

**怎么预防：**
- **shot-level atomic caching。** 每个 shot 的 route 输出独立写文件（`output/<asset>/route_cache/shot_analysis/shot_001.json`...）。任一 shot 失败不影响其他 shot 的产物落盘。
- **route client 内部 try/except per shot。** 单 shot 失败 → 该 shot 字段填空 + 在 asset.json `generator.warnings: ["shot_47 cinematography analysis failed: OOM"]`。这与现有的 `audio_analysis` 缺失字段降级模式一致。
- **driver 改造（与 kais-aigc-platform 协调）：** 请求 driver 对单 shot 失败要写一个 `shot_XXX.error.json` 占位（而非不写），让 client 知道哪些 shot 已尝试过。这是跨仓库协调点，应在 WR（work request）里追踪，仿照 v1.0 的 WR-01/04 模式。
- **resume 模式：** 管线第二跑时，已成功的 shot 跳过；只重试失败的 shot；用户可加 `--refresh-failed-shots` 强制重试所有失败的。

**预警信号：**
- ep 跑完后某些 shot 的 prompts 字段全空，但没有显式 warning（driver 静默丢 shot）。
- 重跑同 ep → 所有 shot 都重新调路由（无 shot-level cache）。
- asset.json `generator.warnings` 数组为空但实际有 shot 失败。

**应在哪个 phase 解决：**
**Phase: 镜头语言自动填充。** Shot-level granularity 是这 phase 必交付的设计决策。

---

### Pitfall 11 — 契约 v2 实际是 major bump 伪装成 minor（**最高危**）

**出了什么问题：**
v1.1 决定是 **schema_version `"1"` → `"2"` minor bump**（PROJECT.md Constraints 第三条：契约仅 minor bump，新增字段/数据文件，**不做破坏性变更**）。但开发者无意中做了被 SPEC §4 列为 major 的操作：

按 `spec/SPEC.md` §4 演进规则表 + `asset.schema.json#schema_version.description` 逐字定义，**这些都算 breaking change（major bump）**：
1. **Rename 现有字段** — 例如把 `prompts[].prompt_text` 重命名为 `prompts[].composed_text` "更清晰"。SPEC: "rename ... = major bump"。
2. **改语义** — 例如把 `prompts[].camera` 从"自由文本"改成"必须从 enum 选"（`{shot_scale, camera_primitive, ...}`）—— 旧消费者写入的自由文本会 schema-invalid。SPEC: "semantic shift ... = major bump"。
3. **删字段** — 例如把 `audio_analysis.shots[].ratios` 删掉因为 "没人用"。SPEC: "removal ... = major bump"。
4. **新增 required 字段** — 例如给 `prompts[]` 加 `character_refs: [{id, role}]` 当 required。SPEC §4 表格："加 required 字段 = major bump"。旧 producer 产出的 prompts.json 没有 `character_refs` → 新 schema 校验失败。
5. ** tightening 约束** — 例如 `prompts[].shot_id` 从 `integer ≥1` 改成 `string pattern "^ch_"`。表面"还是 required"，但语义彻底变。
6. **改 enum 减少** — 例如 `dominant_type` 去掉 `sfx` 选项。SPEC §4: 减 enum 值是 removal = major。

**任何一条都让"老消费者 graceful-degrade"承诺失效**——因为 graceful-degrade 的前提是"新字段被老消费者忽略"，而上述操作改的是老消费者正在用的字段。

**为什么会发生：**
开发者把"丰富 prompts schema"理解为"现有字段不够好，重新设计"。CC-ReID 的天然需求是把 `camera: "近景，固定机位"` 拆成结构化 `{shot_scale, camera_primitive, speed}`——但这要在保留 `camera` 字段（旧消费者依赖）的前提下 *新增* `camera_structured` 字段，而非替换。开发者想不到 minor vs major 的差别如此严格，因为完整 semver 允许更宽松的语义。

**怎么预防：**
- **规则铁律（贴在每个 schema PR 的 description 模板里）：**
  > v2 = minor bump。SPEC §4 允许的：① 新增 optional 字段；② 新增 enum 值（不减）；③ 新增数据文件（如 `characters.json`、`props.json`）；④ 新增 media 类别。
  > 一切其他变更必须先停下来 review。
- **新增字段必须 optional（不在 `required` 数组里）。** `prompts[].character_refs`、`prompts[].camera_structured`、`asset.json.data.characters`、`asset.json.media.characters_sheet` 都是 optional。
- **保持所有 v1 字段的类型 + 语义不变。** `shot_id` 仍是 `integer ≥1`，`prompt_text` 仍是 string，`schema_version` 仍是 semver-lite。
- **schema PR 检查清单：** diff 必须 only-add，不允许 modify / delete。在 phase verification step 跑 `git diff spec/schemas/v1..v2` 应只看到 `+` 行（除 `$comment` / `description` 这些非语义性改动）。
- **保留 v1 fixture 不动。** `spec/fixtures/minimal/asset.json` 的 `schema_version` 仍是 `"1"`，且必须 v2 schema 也接受它（minor 允许老形态）。**加一个新 fixture `spec/fixtures/v2/`** 用 schema_version `"2"` 测新字段。
- **canvas 消费者更新时跑双向 verify：** v2 producer asset → 老 consumer（v1 known set）应 graceful-degrade warn；v1 producer asset → 新 consumer（v2 known set）应正常渲染不报错。扩展 `scripts/verify_contract.py` 加这两种 cross-version 用例（见 Pitfall 13）。

**预警信号：**
- schema PR diff 出现 `-` 行（字段被删/改）。
- `spec/fixtures/minimal/asset.json` 被修改（v1 fixture 应永不改）。
- v2 schema 校验 v1 fixture 失败（说明 v2 隐性收紧了约束）。
- consumer `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1", "2"])` 加了 "2" 后，v1 producer asset 在新 consumer 上 warn（不应 warn——v1 是已知版本）。
- consumer 加载 v2 asset 时抛 Zod 解析错（说明 v2 用了 strict mode 拒绝 v1 字段）。

**应在哪个 phase 解决：**
**Phase: 契约 v2（schema 设计 + 跨仓库 verify）。** 这是这 phase 的核心交付物。**Phase 1 必须先做 schema，再实现填充逻辑**——否则填充代码会锁定错误的字段名。

---

### Pitfall 12 — 忘了 bump schema_version（或 bump 写错形式）

**出了什么问题：**
开发者加了 `characters.json` 数据文件、扩展了 `prompts.schema.json` 加 `character_refs` 字段，但忘了把 `asset.json` 的 `schema_version` 从 `"1"` 改成 `"2"`。结果：v1 消费者按 v1 schema 严格校验（`additionalProperties:false`），新的 `character_refs` 字段被拒，asset 整体 schema-invalid。或者反过来 bump 但写成 `"v2"` / `"2.0.0"` / `"2.0.1"`，违反 `asset.schema.json` 的 pattern `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`，asset 直接 invalid。

**为什么会发生：**
schema_version 是单字段，写在 `asset.json` 顶层，不在 schema 文件里——容易被忘。开发者改完 schema 文件就提交，没改 exporter 写 manifest 的代码。bump 写错形式是因为不熟悉 semver-lite（拒 `"v1"`、`"1.1.1"`、`"01"`、前导零等——见 `asset.schema.json#schema_version.pattern` 注释）。

**怎么预防：**
- **`scripts/export_asset.py` 的 `schema_version` 是常量定义（不是分散在代码里的字面量）。** PR 改 schema 必须同步改这个常量，作为一处单一来源。
- **CI / 本地 verify 强制：** `scripts/verify_contract.py` 加一条 check：跑 `git diff` 看 `spec/schemas/` 是否被改；若被改但 `export_asset.py` 的 `SCHEMA_VERSION` 常量没改 → fail-loud，提示 "schema 改了但版本号没 bump"。
- **self-test 加 v2 漂移注入用例：** 现有 self-test（`verify_contract.py:run_self_test`）只测 `schema_version='v1'`（违反 pattern）。**v1.1 必须加新用例：** 注入 v2 fixture 但删一个新字段（如 `character_refs`）→ 应 fail-loud（验证新字段被 schema 接受 + required 设置正确）。Pitfall 13 展开。
- **fixture 双轨：** `spec/fixtures/minimal/`（v1，永不改）+ `spec/fixtures/v2/`（v2 形态，必填字段全填）。两个 fixture 都被 verify_contract 跑。

**预警信号：**
- schema PR 没有 asset.json / exporter 改动（schema_version 没同步 bump）。
- producer mode verify 报 `'v2' does not match pattern`（写错形式）。
- consumer 永远走 graceful-degrade warn 分支（producer 写出的 version 不在 known set）。

**应在哪个 phase 解决：**
**Phase: 契约 v2（exporter 修改 + verify harness 扩展）。** exporter bump + self-test 是 phase verification step。

---

### Pitfall 13 — `verify_contract.py` 没扩展，drift 静默通过

**出了什么问题：**
v1.0 的 `scripts/verify_contract.py` 是契约 drift 回归网（RETROSPECTIVE "Patterns Established" 第一条）。v1.1 新增 `characters.schema.json` / `props.schema.json` + 扩展 `prompts.schema.json` + bump version。如果 verify_contract 不扩展：
- `SIX_SHAPES = ["asset", "shots", "audio_analysis", "transcript", "frames", "prompts"]`（`verify_contract.py:75`）—— 漏了新 shapes，新 schema 即使写错也不被抓。
- `validate_six_shapes` 函数名/循环结构按 6 写死，加新 shape 后名字 misleading。
- `run_self_test` 只测 v1 注入 `schema_version='v1'`，没测 v2 → v2 漂移不被抓。
- consumer mode 调 `verify-canvas-shot-timeline.ts`，该脚本断言 "1 zone + 93 storyboard + 3 audio + N-1 seq edges"（基于 ep01 v1.0 形态）—— v2 加了 character/prop 节点后这些数字错位，verify 误报。
- e2e mode 断言同上。

**为什么会发生：**
开发者把 verify_contract 当 v1.0 完工的不动产，新 phase 只改 schema / exporter，忘了回归网要随契约一起演进。RETROSPECTIVE 的 "Live-verify during research pays for itself" 教训在这里同样适用——verify 不更新 = 静默 drift。

**怎么预防：**
- **`SIX_SHAPES` 改成数据驱动（从 `spec/schemas/*.schema.json` 自动发现）。** 或显式扩成 `EIGHT_SHAPES`，强制名字也对齐。
- **新增 self-test 用例：** ① 注入 v2 fixture 删 `characters` 字段 → 若 v2 schema 把 characters 设为 required，应 fail；optional 则 pass（验证 required 设计意图）。② 注入 v2 fixture 改 `prompts[].character_refs` 为 unknown enum 值 → 应 pass（SPEC §4 "加 enum 值是 minor"，老消费者把 unknown enum 归 "未知" + warn）。
- **新增 cross-version verify：** v2 producer asset → v1 consumer (consumer 已知集仍 `["1"]`) 应 graceful-degrade warn（不 reject）；v1 producer asset → v2 consumer 应正常渲染。这两 case 是 graceful-degrade 规则的真验证。
- **consumer verify 脚本（cross-repo `verify-canvas-shot-timeline.ts`）扩展：** 接受 v1 ep01（93 storyboard）和 v2 ep01（93 storyboard + K character + L prop + reference 节点）两种形态，断言对应数。
- **跨仓库协调（仿 v1.0 模式）：** `verify_contract.py` 在 producer 仓库（本仓库），但 consumer 验证调 cross-repo worktree 的脚本——两个仓库必须同步更新。在 phase SUMMARY 显式列 cross-repo WR。

**预警信号：**
- verify_contract green，但实际 v2 producer asset 在新 consumer 上抛错（harness 有盲区）。
- `SIX_SHAPES` 仍是 6 个但 schemas 目录有 8 个文件（harness 落后于 schema）。
- self-test 仍是 v1 注入，没加 v2 case（harness 没跟着契约走）。
- ep01 storyboard count 断言硬编码 "93"，换 fixture 就误报。

**应在哪个 phase 解决：**
**Phase: 契约 v2（verify harness 扩展子任务）+ 跨仓库 verify phase。** 是 phase 必交付物。

---

### Pitfall 14 — 画布新节点触发 Zod additionalProperties 拒绝 / 静默 strip

**出了什么问题：**
v1.1 决定"canvas 新增角色/道具节点类型"（PROJECT.md Active 第 5 条）。但 `canvasAssetSchema.ts` 的 `assetDataSchemas` 只有 5 个 type（`audio, video, asset, storyboard, script`），**且 `asset` 类型已经支持 `assetType: "character" | "scene" | "prop"`**（`canvasAssetSchema.ts:81`）。开发者两条岔路都可能踩：

**路径 A — 发明新 canvasType `character` / `prop`：**
- `validateNodeData` 查不到 schema → 走 "Unknown type — allow but warn" 分支（`canvasAssetSchema.ts:142-145`）→ 表面看通过，但：① 任何 per-type required-field 校验都跳过（数据质量门没了）；② `EXPECTED_PARAM_FIELDS_BY_TYPE` 没条目 → import-from-dir 的 `__incomplete` 标记逻辑失效；③ renderer dispatch 找不到匹配 → fallback 渲染可能不是想要的画廊样式；④ 与 v1.0 P04 character 的既有路径（`assetType: "character"`）分裂，两种 character 表达并存。

**路径 B — 复用 `asset` type + `assetType: "character"`：**
- Zod schema `asset` 用的是 `z.object({...})`，**不是 `.strict()`** → 默认 Zod 行为是 **strip unknown keys**（不拒绝但不保留）。如果 v2 在 node.data 加新字段（如 `look_id`、`appearances: [...]`），save-v2 HTTP 调用时这些字段被静默剥离，落库后再读出来字段就没了。用户看到画布第一次显示正确，刷新后字段消失。
- 若改用 `.passthrough()`：字段保下来但 Zod 不校验，脏数据可入。
- 若改用 `.strict()`：v1 producer 写入的旧字段（不在新 schema 里）会被拒绝，**v1 asset 在新 consumer 上崩溃 → 违反 graceful-degrade**。

**为什么会发生：**
- 路径 A：开发者没意识到 v1.0 已经用 `asset + assetType="character"` 表达角色（`import-from-dir.ts:90` 的 "P04 character turnaround"），自然想"既然是 character 类型，新建一个 canvasType"。
- 路径 B：Zod 默认 strip 行为反直觉，开发者以为"没报错 = 没问题"。canvasAssetSchema.ts L84-87 注释 "Kept optional because legacy data lacks both, and rejecting on full-graph save would break the UI for 689 pre-existing asset rows" 已经显示 v1.0 团队踩过 strict 模式的坑。

**怎么预防：**
- **明确决策：v1.1 角色节点复用 `asset` type + `assetType: "character"`，不新建 canvasType。** 同样 `assetType: "prop"` 表示道具。这与 v1.0 P04 既有路径一致，新数据落在已有 schema 内。
- **新字段（如 `look_id`、`character_ref_id`、`appearances`）走两条路之一：**
  - **首选：** 加入 `schema/pipeline-field-map.yaml`（被 `frontend-zod-extensions.ts` 加载为 optional 字段，`canvasAssetSchema.ts:37-49` 的 `withYamlOptional`）。这是 v1.0 既有的"扩展点"，跨 Python 后端 / TS 前端 / import enum normalizer 三处的单一来源。
  - **次选：** 直接在 `assetDataSchemas.asset` 加 optional 字段。但这条路跨仓库协调成本高。
- **绝不要对 `assetDataSchemas` 用 `.strict()`** —— 会破坏 689 个历史 row 的兼容性 + 违反 v1 asset 的 graceful-degrade。
- **跨仓库 verify：** v2 producer 写出含 `look_id` 的 asset → cross-repo consumer worktree import → save-v2 → SQL 读回 → 断言 `look_id` 字段保下来（没被 strip）。扩展 `verify-canvas-shot-timeline.ts` 加这条断言。
- **新 canvasType 是 contract bump**：若团队最终决定必须新建 `character` / `prop` canvasType（如 renderer 真的需要独立 dispatch），那就 **不是 minor bump**，必须升 major + 加 graceful-degrade 路径。v1.1 决定是 minor，所以应避免这条路。

**预警信号：**
- 画布刷新后 character 节点的某些字段消失（Zod strip）。
- consumer console 出现 "Unknown type — allow but warn" 针对每秒 N 个节点（用了新 canvasType）。
- consumer 改 `.strict()` 后 v1 producer 的 ep01 asset 在新 worktree 上抛 Zod 错。
- `EXPECTED_PARAM_FIELDS_BY_TYPE` 与实际 node type 集合不同步。

**应在哪个 phase 解决：**
**Phase: 双端展示（canvas 新节点子任务）+ 契约 v2（决定 asset 复用 vs 新 type 必须先做）。** 决策时机：phase 1 契约设计时就要定。

---

### Pitfall 15 — Consumer 更新后 v1 producer 资产崩（known-set + Zod 双重断裂）

**出了什么问题：**
v1.1 把 producer 升到 schema_version `"2"`，consumer worktree 同步加 `"2"` 进 `SHOT_TIMELINE_KNOWN_VERSIONS`（`import-from-dir.ts:898`）。但这有两个隐性陷阱：
1. **consumer 加 v2 支持时改了 v1 路径的代码**（比如重构 `extractShotTimelineArtifacts`），结果 v1 producer asset 在新 consumer 上抛错——破坏了"v1 / v2 共存"承诺。
2. **producer 在 v2 schema 加了字段但 consumer 没同步**（跨仓库 PR 没协调）→ consumer 用 v1 解析逻辑看到 v2 字段时，由于 `additionalProperties:false` 是 schema 层（不是 consumer runtime），runtime Zod 默认 strip 掉，UI 显示"少了字段"。

**为什么会发生：**
v1.0 团队已踩过类似：RETROSPECTIVE 提到 "Phase 3 buildPhaseTree canvasType constraint + persistence dual-track" 是研究阶段才发现的 load-bearing finding。`import-from-dir.ts:892-898` 显式注释 "SPEC §4 mandate: consumer 遇未知/更新版本时 graceful-degrade" + "本 phase 仅处理 '1'; future major bump 时在此处加版本分支处理"——说明 v1.0 团队**已经预料到这个 pitfall**，留了版本分支位置。v1.1 必须正确地填进去，而不是绕开。

**怎么预防：**
- **`SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1", "2"])`**（在 cross-repo worktree 上改）。同时 `extractShotTimelineArtifacts` 内部按 version 分支：v1 走原路径，v2 多读 `characters.json` / `props.json` + 渲染 character/prop 子节点 + reference chip。
- **v1 路径必须有回归测试**：扩展 `verify-canvas-shot-timeline.ts` 加 "v1 producer asset 在 v2-aware consumer 上应正常渲染 + warn 一次 schema_version='1' is older" 的 case。
- **跨仓库 WR 显式追踪**：仿照 v1.0 的 WR-01 / WR-04 模式（RETROSPECTIVE "Formally-accept-and-document"），把"consumer 必须加 v2 known-set 条目"作为 cross-repo phase 的 acceptance criteria。
- **producer mode verify 加双向 case：**
  - v1 fixture → 新 consumer（含 v2 支持）应正常 import + warn。
  - v2 fixture → 老 consumer（v1 only，比如 v1.0 已部署的 worktree）应 graceful-degrade warn。
  - 后者是为了验证 v1.0 的 SPEC §4 承诺仍成立。

**预警信号：**
- consumer 的 `KNOWN_VERSIONS` 没加 "2"（每次 import v2 asset 都 warn）。
- consumer 加 "2" 后 v1 asset 的导入路径行为变了（重构破坏 v1）。
- v1 producer asset 在新 consumer 上抛 Zod 错（v1 路径被误改）。

**应在哪个 phase 解决：**
**Phase: 双端展示（canvas consumer 更新子任务，跨仓库）。** 同 Pitfall 14 一起做。

---

### Pitfall 16 — Character 出现的 sequence-edge 语义模糊

**出了什么问题：**
v1.0 的 sequence edge 表达"分镜之间时序"——`(N-1)` 条边把 N 个 storyboard 串起来（`verify_contract.py:593` 断言）。v1.1 加 character 节点后，character 在 ep 中"出现"的时序怎么表达？三种可能都不对：
1. **character → 每个 shot 都连一条边** → 边数爆炸（N characters × M shots），画布变成毛线球。
2. **character → 出现的 shot 范围只连首末两条边** → 时序信息丢失（不知道中段是否出场）。
3. **character → shot 用 sequence edge** → 语义混淆，sequence edge 原本表达 "shot A 之后播 shot B"，character 不是 "之后播"。

**为什么会发生：**
v1.0 的 sequence edge 语义是"播放顺序"，character 出现的语义是"包含关系"（character 出现在 shot 中）。两种语义不同。开发者混用一种 edge 类型表达两种关系，导致画布渲染与数据语义错位。

**怎么预防：**
- **明确：character/prop 出现的语义是 "reference"（包含/引用），不是 "sequence"（时序）。** 用新的 edge 类型 `appearance`（或复用 `dataType:"data", data:{linkType:"appearance"}`），而非 `linkType:"sequence"`。
- **每条 character-shot 边带元数据：** `{character_id, shot_id, look_id?, role: "subject" | "background" | "cameo"}`。让画布能按 character filter 高亮所有出现的 shot。
- **不要试图把 character 也插入 storyboard sequence 链。** Character 节点是 cross-cutting（横跨多个 shot），不是 linear（在 shot 之间）。两者数据模型不同。
- **画布上 character 节点的位置：** 在 zone 内单独区域（与 storyboard 序列并列），用 appearance edges 把 character 连到每个出现的 shot。这与 phase 1 (zone) / phase N (storyboard sequence) 的层级一致。
- **sequence edge 断言不变：** `verify_contract.py:593` 仍断言 `seq_edges == N_storyboards - 1`。新增 `appearance_edges` 是独立断言。

**预警信号：**
- e2e verify 报 seq_edges 数量异常（character 被错插入 sequence）。
- 画布渲染 character 节点时整个 layout 错乱（边数爆炸）。
- 用户反馈"看不出 character 在哪几个 shot 出现"（边语义不对，画布没正确高亮）。

**应在哪个 phase 解决：**
**Phase: 双端展示（canvas 子图设计子任务）+ 契约 v2（edge 类型定义在 schema）。** Schema 必须先定义 edge 类型语义，画布才能实现。

---

### Pitfall 17 — Prompt 引用悬空 ID（registry mutation 让旧 prompt 失效）

**出了什么问题：**
prompt 引用系统的设计：`prompts[].prompt_text` 内嵌 `{character_ref: "ch_001"}`，渲染时把 `ch_001` 替换为注册表里的 character 描述。三种悬空场景：
1. **Character 注册表条目被删**（reviewer 误操作或 re-id 重跑时 ID 重置）→ prompt 引用 `ch_001` 找不到目标。
2. **ID 编号方案变**（v1 → v2 把 `ch_001` 改成 `char_001`）→ 旧 prompt 引用全部悬空。
3. **Prompt 引用了一个未进注册表的 character**（pipeline bug，prompt 生成器瞎编 ID）。

**为什么会发生：**
开发者在 prompt 引用系统设计时，把 `prompt_text` 当成"渲染时模板替换"的运行时行为，没考虑注册表是会被 review 修改的活数据。注册表 mutation → 模板变量失效。

**怎么预防：**
- **prompt 引用是 schema-validatable 的强引用。** `prompts[].character_refs: [{id: "ch_001", role: "subject", look_id: "look_002"}]` 是结构化字段（不是字符串内嵌），schema 校验时必须存在 `characters.json#characters[].id == "ch_001"`。
- **注册表 ID 是 immutable。** reviewer 可以 merge / split character，但 ID 不重用、不改格式。merge 时新 ID 是 fresh（如 `ch_042`），旧 ID `ch_001`、`ch_007` 标 `archived: true` + `merged_into: "ch_042"`，prompt 仍能解析（`archived` 字段告诉渲染器用 merge target）。
- **reviewer 删 character → 软删（`status: "deleted"`），不真删。** prompt 引用解析时若发现 `status: deleted` 走 graceful-degrade（不替换 + warn）。
- **verify_contract 加 cross-file integrity check：** 跑一遍 producer asset，扫描所有 `prompts[].character_refs[].id` 必须能在 `characters.json` 找到。任一悬空 fail-loud。
- **prompt 模板渲染在 producer 与 HTML 渲染时都跑一次**：producer 写 `prompt_text` 时已展开（向后兼容老消费者），HTML 渲染时再次展开（reviewer 改了注册表后能立即看到）。两份都存。

**预警信号：**
- producer verify 报 "prompt references ch_XXX not in characters.json"。
- 注册表 review 后，老 prompt 渲染出空字符串或 "???"。
- 注册表 ID 格式不一致（混用 ch_ / char_ / character_）。

**应在哪个 phase 解决：**
**Phase: prompt 引用系统（schema 设计）+ 契约 v2（注册表 + prompt 引用 schema）。** ID immutability 规则是 phase 1 schema 设计决策。

---

### Pitfall 18 — Registry 重跑让旧 asset 的 prompt 引用失效

**出了什么问题：**
re-id 是 iterative 的（reviewer merge 一次 → re-id 用 merge 当 supervision 再跑一次 → 更准 → reviewer 再 review）。每次 re-id 重跑可能产新 character IDs（因为 ID 是 immutable + 不重用，新 run 用 fresh IDs）。旧 asset 的 prompts.json 引用的是上一次 run 的 IDs → 失效。

**为什么会发生：**
开发者把 re-id 当一次性 pipeline step（`step_reid`），没考虑它是会被反复跑的（reviewer 修一次就要重跑）。或者反过来，re-id 重跑时强制保留旧 IDs → 但 schema 设计时没规划 ID 复用 → 实现混乱。

**怎么预防：**
- **明确 re-id 重跑的 ID continuity 规则：**
  - 第一次 run：所有 character 拿 fresh ID `ch_001...ch_NNN`。
  - review 后 re-run（不是从 scratch，而是 incremental）：保留 reviewed-and-locked IDs，只对 `status: "draft"` 的 character 重新 cluster。这与 git rebase 的 commit保留语义类似。
- **asset 的 prompt 引用快照：** asset.json 里存一份 `generator.registry_snapshot: {characters: [...], props: [...]}`（注册表当时的状态）。这样即使后续注册表 mutate，老 asset 的 prompt 引用永远能解析（用自己的 snapshot）。
- **跨 asset 的 registry 是 advisory，不是 source of truth。** 每个 asset 自带 registry snapshot。这跟 v1.0 "asset 自描述" 原则一致。
- **registry 全量 mutate（如批量改名）时，提供 migration 脚本**，扫所有 asset 的 `prompts.json`，按需更新引用。这是 phase 之外的 ops 工作。

**预警信号：**
- 重跑 re-id 后，旧 asset 的 prompt 引用全部失效。
- asset.json 没存 registry snapshot，只能查当前 registry，prompt 渲染不稳定。
- 用户报告"我什么都没改，但重新打开 asset 看到的角色名变了"。

**应在哪个 phase 解决：**
**Phase: prompt 引用系统（registry snapshot 设计）+ 契约 v2（asset manifest 加 generator.registry_snapshot 字段，但需注意这是 v2 新字段，仍 minor bump）。**

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| 单模态 re-id embedding（只 OSNet 全身） | 管线简单，少跑一个模型 | 换装场景系统性失效；reviewer 工作量翻倍 | **Never**（v1.1）—— 双模态是基本要求 |
| 全局聚类阈值（凭感觉定 0.7） | 短期 ep01 上"看起来 ok" | 跨 ep、跨风格必漂；reviewer 没优先级排序 | 仅 spike 阶段定初值；上线前必须三档阈值 |
| 缓存键用 video filename | 简单 | 同名不同内容视频脏命中；asset 搬家失效 | **Never** |
| 跳过人工 review 全自动 re-id | 省一个 phase 的工作量 | 错误 cluster 静默下游污染；修复成本 10x | **Never**（OUT OF SCOPE 已明示） |
| Route 失败 fail-loud | 短期看是"显式" | 离线重跑不可用；用户被困 | 仅 driver 内部 sanity check（如 schema 错）；网络/超时/5xx 必须 graceful-degrade |
| 在 prompts schema 里替换字段名（rename） | "更清晰" | breaking change，违反 minor bump | **Never**——加新字段，保留旧字段 |
| 用 `.strict()` 修 Zod schema | "数据更干净" | v1 producer 的 689 历史行 + v1 asset 全崩 | **Never**——`additionalProperties:false` 在 producer schema 层，consumer runtime 保持 lenient |
| SHOT_TIMELINE_KNOWN_VERSIONS 加 "2" 但不重构 extractShotTimelineArtifacts | 速过 verify | v2 字段被静默 strip，UI 缺数据 | 仅当 v2 字段全是 optional 且不渲染时（仍要 plan 真正实现）|
| 把 character 直接塞进 storyboard sequence edge 链 | 省一个 edge 类型 | 边数爆炸 + 语义混淆 | **Never**——用 appearance edge 类型 |
| 用 single-fixture verify（只测 v2 ep01） | 简化 verify | v1 fixture 漂移不被抓 | **Never**——必须双 fixture（v1 + v2） |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `kais-aigc-platform` cinematography route | 假设路由永远 online；pull main 后路由消失（两 feat 分支未 merge） | preflight health check + offline mode + 缓存键含 route SHA |
| `shot-analysis` route driver（Python） | 假设单 shot 失败 = 整 step 失败；丢已成功 shot | driver 内部 per-shot try/except + 写 `shot_XXX.error.json` 占位；client side per-shot cache |
| ComfyUI 容器（`comfyui-primary`） | 走 compose up 重启（user memory `comfyui-primary-node-deploy.md` 明示会重建镜像，运行镜像 -qwen-tts 与 .env 不符） | 走 kais-incremental aggregator + `docker restart`；preflight 之前等容器 healthy |
| Cross-repo consumer worktree | 在 main checkout 上同时改 producer + consumer，污染 ltx 并发工作 | worktree-per-effort（v1.0 模式，RETROSPECTIVE "Worktree isolation"） |
| Zod strict vs strip | 默认 `z.object({})` 静默 strip 未知字段，UI 表面正常但刷新后丢字段 | 显式决定每 schema 的 passthrough / strict / strip；新字段进 `pipeline-field-map.yaml` |
| `import-from-dir.ts` 已知版本集合 | 加 v2 时只改 set，不重构 helper 内分支 → 新字段被 helper 跳过 | v2 分支显式读 characters/props JSON + 渲染新节点 |
| `audio_analysis` 缺 `dominant_type` enum 新值（如 v1.1 加 `silent`） | 旧消费者 enum 校验失败 | SPEC §4 明示"加 enum 值是 minor"，旧消费者必须把 unknown enum 归"未知"+ warn |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Route 同步阻塞 15min/shot | 100-shot ep 单 run 25h | shot-level 并行（ComfyUI 多 job 排队）+ 缓存 + 离线 rerun | N>30 shots |
| Re-id embedding 全 ep 同步算 | 单 ep 跑 30min，迭代慢 | 缓存 embedding tensor 到 `output/<asset>/embeddings/*.npy`；reviewer merge/split 不重算 embedding | N>50 characters |
| SAM3 sheet 生成跑所有帧 | 单 shot 跑 N 帧 × 5s SAM3 = 30s+ | 只采样 3-5 帧/shot；首尾帧 fallback；low-confidence skip | 单 ep >100 shots |
| Verify_contract 跑 e2e（起 Express backend） | 单跑 90s+ | dev cycle 用 `--mode=producer`，CI 用 `all` + `PHASE4_RUN_E2E=1` | 每次 commit |
| Producer 内联 jsonschema 校验大 asset | 单 asset 校验数秒 | cache invalidation only on schema change；fixture 用 minimal | ep frames.json >100MB |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Route client 把 `params.video` 绝对路径直接 POST | 跨仓库传递主机路径，可能泄露 | 始终用 `os.path.abspath` + 校验在 `output/` 之内；preflight 拒绝外部路径 |
| Cinematography route `docker cp` 把 source video 拷进容器（`shot-analysis/index.ts:63`） | 大文件 IO；并发 run 时容器磁盘塞满 | 路由侧问题，但 producer 应意识到：调用前估算 video 大小，超阈值 warn |
| Re-id thumbnail（character sheet）含路人脸 | 隐私 / 后续发布时泄 | 默认 character sheet 不导出 base64（外置媒体，仿 v1.0 stem）；用户手动 export 才落盘 |
| Consumer `extractShotTimelineArtifacts` 信任 manifest.source.duration_sec | 0 / NaN → 后续 audio 节点 `z.number().positive()` 失败（`import-from-dir.ts:977-992` 已 warn） | producer 显式校验 duration_sec > 0，fail-loud before export |
| Asset.json 内嵌 `generated_at` 时区 | 非 UTC 时间戳造成跨仓库时间错位 | 强制 ISO-8601 UTC（v1.0 已立规矩，v2 维持） |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Re-id review 工具不存在 / 太粗糙 | Reviewer 用肉眼对照 JSON，错误率高 | review HTML 是 phase 必交付物（仿 gen_timeline_html.py 模式）；按相似度排序、双模态分组、键盘快捷键 |
| 角色/道具在画布上没有 thumbnail | 用户只看到节点 ID 不知是谁 | character sheet 在画布渲染为 image asset（复用 v1.0 P04 模式） |
| Cinematography 字段在 timeline.html 里不显示 | 用户看不出 route 工作没工作 | timeline.html prompt 区域加"运镜分析填充"标识（绿色 chip = route 填了；灰色 = 离线降级空） |
| Prompt 引用 chip 在 HTML 里不可点 | 用户看不到引用的是注册表哪个 character | chip 渲染为可点击，hover 显示 character thumbnail + look |
| 失败 shot 静默被跳过 | 用户以为整 ep 都分析了，实际有空洞 | timeline.html 在该 shot 卡片角标 "运镜分析失败" + 资产 `generator.warnings` 数组 |

## "Looks Done But Isn't" Checklist

- [ ] **Re-ID 注册表：** Often missing human review tool — verify `scripts/review_registry.html`（或等价）存在且能产出 `status: reviewed` 的 registry
- [ ] **Re-ID 注册表：** Often missing cluster threshold 调参依据 — verify phase SUMMARY 含 ep01 cosine 分布直方图 + 阈值选择理由
- [ ] **契约 v2：** Often missing self-test 扩展 — verify `verify_contract.py:run_self_test` 含 v2 fixture + 新字段 required/optional 断言
- [ ] **契约 v2：** Often missing cross-version verify — verify v1 fixture 在 v2 consumer、v2 fixture 在 v1 consumer 两种 case 都跑
- [ ] **契约 v2：** Often missing `SIX_SHAPES` 扩展 — verify `verify_contract.py:75` list 与 `spec/schemas/*.schema.json` 文件数对齐
- [ ] **路由依赖：** Often missing offline mode — verify `--offline` flag 跳过路由 + 只用缓存，asset 仍能生成
- [ ] **路由依赖：** Often missing per-shot cache — verify `output/<asset>/route_cache/shot_analysis/shot_001.json` 文件级缓存存在
- [ ] **路由依赖：** Often missing preflight — verify 管线 step 1 之前有路由 health check，失败时 graceful banner
- [ ] **画布新节点：** Often missing `KNOWN_VERSIONS` 加 "2"（跨仓库） — verify consumer worktree `import-from-dir.ts:898` 含 "2"
- [ ] **画布新节点：** Often missing v1 回归断言 — verify `verify-canvas-shot-timeline.ts` 仍能 import v1 ep01 asset 不崩
- [ ] **画布新节点：** Often missing appearance edge type — verify sequence edge 数（N-1）不变，新增 appearance edges 独立计数
- [ ] **Prompt 引用：** Often missing cross-file integrity check — verify `prompts[].character_refs[].id` 全部能在 `characters.json` 找到
- [ ] **Prompt 引用：** Often missing registry snapshot in asset.json — verify `generator.registry_snapshot` 字段在 v2 producer 写出
- [ ] **SAM3 sheet：** Often missing mask quality metric — verify `characters[].sheets[].mask_quality` 字段存在 + 低质量帧被标 `unusable`
- [ ] **v1 fixture 完好：** Often missing 不变性 — verify `spec/fixtures/minimal/asset.json` 在 v1.1 PR 里没被改

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| 1（模型选错） | MEDIUM | 改模态 + 重算 embedding（缓存使不上）；re-id 重跑；review 重做 |
| 2（阈值错） | LOW | 改阈值 + 重新 cluster（embedding 可缓存重用）；review 重做 |
| 3（换装未识别） | MEDIUM | 加 `looks[]` schema；回填已识别 character 的 look 分裂；重做 prompt 引用 |
| 4（背景泄漏） | LOW | mask → alpha + 灰背景；重算 embedding；re-cluster |
| 5（identity drift） | LOW（v1.1 内）| 接受；schema 文档化 ID scope；不影响数据 |
| 6（SAM3 单帧不可用） | MEDIUM | 多帧采样 + 重算 mask；低质量帧重切 |
| 7（全自动幻觉） | HIGH | 回滚；加 review 工具；可能已污染 prompt / canvas，需 migrate |
| 8（路由断网即崩） | LOW | 加缓存 + offline flag；下次 run 可重用 |
| 9（缓存策略错） | LOW | 修缓存键；删旧缓存；重跑 |
| 10（路由部分失败） | LOW | shot-level cache 让 resume 可行；重试失败 shot |
| 11（隐性 major bump） | **HIGH** | schema 已发 → consumer 已部署 → 必须发 v3 major + 迁移文档；或回滚 producer |
| 12（忘 bump schema_version） | LOW | 改 exporter 常量；下一 producer run 自动写对 |
| 13（verify 没扩展） | MEDIUM | drift 可能已发生；扩展 verify；扫现存 asset 找漂移 |
| 14（Zod strip / 新 canvasType） | MEDIUM | 数据落库已丢字段；要 producer 重导；或加 migration script |
| 15（v1 在 v2 consumer 崩） | HIGH | v1 资产已部署，consumer 升级即 break；必须 hotfix consumer 加 v1 兼容路径 |
| 16（sequence edge 误用） | MEDIUM | 画布渲染逻辑要重写；边数据要重导 |
| 17（prompt 悬空） | LOW | cross-file check 找出；reviewer 修注册表 |
| 18（registry 重跑失效） | MEDIUM | registry snapshot 设计实施；老 asset 需要 backfill |

## Pitfall-to-Phase Mapping

> Phase 名是建议（基于 PROJECT.md target features + v1.0 phase ordering 模式 = 契约先于实现）。最终 phase 名以 ROADMAP 为准。每条都列出"phase 内必交付的预防物"+"verification 怎么验"。

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 11 (隐性 major bump) | **Phase A: 契约 v2（schema 第一）** | `git diff spec/schemas/` only-`+` lines；v1 fixture v2 schema 接受；v2 fixture v1 schema graceful-degrade |
| 12 (忘 bump version) | **Phase A: 契约 v2** | `scripts/export_asset.py` SCHEMA_VERSION 常量；CI check schema 改动同步常量 |
| 5 (identity drift scope) | **Phase A: 契约 v2**（schema 注释 ID scope） | SPEC.md 增段说明 character ID 单 asset 内有效 |
| 17 (prompt 悬空) | **Phase A: 契约 v2**（schema 强引用 + cross-file check） | `verify_contract.py` cross-file integrity check |
| 18 (registry snapshot) | **Phase A: 契约 v2**（`generator.registry_snapshot` 字段） | v2 fixture 含 snapshot；旧 asset 重导保 snapshot |
| 3 (costume change looks[]) | **Phase A: 契约 v2**（schema `looks[]`） | v2 fixture 含多 look character；re-id 输出多 look 不报错 |
| 13 (verify 没扩展) | **Phase A: 契约 v2** + **Phase D: 跨仓库 verify** | `SIX_SHAPES` 扩展；self-test 加 v2 case；cross-version verify 双向跑 |
| 8 (路由断网即崩) | **Phase B: 镜头语言填充**（route client） | offline rerun 能产 asset；preflight route down 提示；generator.warnings 含失败 shot |
| 9 (缓存键) | **Phase B: 镜头语言填充** | cache 文件名含 route_version；同 video 同 SHA 命中；offline flag 工作 |
| 10 (路由部分失败) | **Phase B: 镜头语言填充** | shot-level cache 文件存在；resume 跑只重试失败 |
| 1 (embedding 模型选错) | **Phase C: 跨镜 re-id 注册表**（spike 子任务） | ep01 双模态分布直方图；模态字段存 schema |
| 2 (阈值敏感) | **Phase C: 跨镜 re-id 注册表** | 三档阈值；review 队列按相似度排序；阈值选择理由在 SUMMARY |
| 4 (背景泄漏) | **Phase C: 跨镜 re-id 注册表** | mask → alpha pipeline；mask_quality 字段；低质量 flag |
| 6 (SAM3 sheet 不可用) | **Phase C: 跨镜 re-id 注册表** | 多帧采样；sheet_source_frame_sec 字段；unusable status |
| 7 (全自动幻觉) | **Phase C: 跨镜 re-id 注册表** | review HTML 交付；status: draft/reviewed/locked；schema 强制 reviewed 才能被 prompt 引用 |
| 14 (Zod strip / 新 canvasType) | **Phase D: 双端展示**（决策在 Phase A 契约） | 决策：复用 asset + assetType；新字段进 pipeline-field-map.yaml |
| 15 (v1 在 v2 consumer 崩) | **Phase D: 双端展示**（跨仓库） | KNOWN_VERSIONS 含 "1" 和 "2"；v1 fixture 在 v2 consumer import + warn |
| 16 (sequence edge 误用) | **Phase D: 双端展示** + **Phase A: 契约 v2**（edge 类型 schema） | seq_edges 断言不变（N-1）；appearance_edges 独立计数 |

## Sources

**仓库内（HIGH confidence，直接引用）：**
- `/data/workspace/kais-shot-timeline/.planning/PROJECT.md` — v1.1 决定（4 条 Key Decisions）、Constraints（minor bump / 路由依赖 / re-id 精度上限 / human-in-the-loop）、Out of Scope（完全自动 re-id）
- `/data/workspace/kais-shot-timeline/.planning/RETROSPECTIVE.md` — v1.0 教训：429 mid-Phase-4、`--force + --skip-detect` cache wipe、formally-accept-and-document 模式、worktree-per-effort 模式
- `/data/workspace/kais-shot-timeline/spec/SPEC.md` §4 — Graceful-degrade 规则（"rename/semantic shift/removal = major bump"、"加 required 字段 = major bump"）逐字引用
- `/data/workspace/kais-shot-timeline/spec/schemas/asset.schema.json` — `additionalProperties:false` 全程、`schema_version.description` 嵌入 graceful-degrade 规则、pattern 字段
- `/data/workspace/kais-shot-timeline/spec/schemas/prompts.schema.json` — `additionalProperties:false` 在 prompts object 上（任何新字段必须 schema 加，否则 producer 写出 invalid）
- `/data/workspace/kais-shot-timeline/scripts/verify_contract.py` — `SIX_SHAPES` 硬编码 L75、`run_self_test` 只测 v1、e2e 断言 N-1 seq edges L593
- `/data/workspace/kais-shot-timeline/spec/fixtures/minimal/asset.json` — v1 fixture，schema_version="1"
- `/data/workspace/kst-canvas-consumer/src/lib/canvasAssetSchema.ts` — Zod 默认 strip 行为（非 strict）、`asset` type 已支持 `assetType: "character" | "scene" | "prop"` L81、structuralTypes / optionalTypes 旁路 Zod、`assetDataSchemas` 5 type、L84-87 注释明确避免 strict（"rejecting on full-graph save would break the UI for 689 pre-existing asset rows"）
- `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts` L888-998 — `SHOT_TIMELINE_KNOWN_VERSIONS = new Set(["1"])` L898（v2 bump 必须 cross-repo 加 "2"）、`extractShotTimelineArtifacts` L943 已有 version 分支占位、`source.duration_sec` Zod positive 风险 L977-992
- `/data/workspace/kais-aigc-platform/src/routes/production/shot-analysis/index.ts` — route driver 同步 spawn L98-103（`timeout: 900_000` = 15min）、`docker cp` L63、单 shot 失败 driver 内部行为不可控
- `/data/workspace/kais-aigc-platform/scripts/shot-analysis/shot_analysis_driver.py` — SAM3Segment `output_mode: "Merged"` L97（hair/手边界处 mask 精度有限）、`confidence_threshold: 0.5` L98、单 shot 失败 driver 处理不明确
- User memory `comfyui-primary-node-deploy.md` — comfyui-primary 容器部署走 kais-incremental aggregator + `docker restart`，不走 compose up（landmine）
- User memory `canvas-asset-collection-worktree.md` — v1.0 SHIPPED 路径，consumer 在 worktree `/data/workspace/kst-canvas-consumer`

**学术 / 业界（MEDIUM-HIGH confidence）：**
- [Gu et al., "Clothes-Changing Person Re-Identification with RGB Modality Only", CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/papers/Gu_Clothes-Changing_Person_Re-Identification_With_RGB_Modality_Only_CVPR_2022_paper.pdf) — 换装 re-id 必须提取 clothes-irrelevant features（face, hairstyle, body shape, gait）
- [Cloth-Changing Person Re-identification: A Survey (2024)](https://www.researchgate.net/publication/401226752) — 换装 identity drift 是开放问题；SOTA 准确率仍 60-80%
- [Masked Attribute Description Embedding for Cloth-Changing ReID, arXiv 2024](https://arxiv.org/abs/2401.05646) — face / body / clothing 多模态融合
- [Clothes-Changing ReID Based on Skeleton Features, arXiv 2025](https://arxiv.org/html/2503.10759v1) — 传统 appearance-based ReID 在服装变化下的失效
- [Ultralytics SAM3 docs](https://docs.ultralytics.com/models/sam-3) — SAM3 occlusion prediction head、masklet detection scores、periodic re-prompting
- [Voxel51 / sam3ai.com limitations](https://sam3ai.com/limitations) — SAM3 在 strong motion blur、partial occlusion、hair 等精细结构上的失败模式
- [Segment Anything Even Occluded, arXiv 2503.06261](https://arxiv.org/abs/2503.06261) — 复杂遮挡下的边界 delineation

---
*Pitfalls research for: kais-shot-timeline v1.1（镜头语言 + 跨镜 re-id + 契约 v2 + 双端展示）*
*Researched: 2026-07-24*
