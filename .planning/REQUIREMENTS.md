# Requirements: kais-shot-timeline

**Defined:** 2026-07-24
**Milestone:** v1.1 分镜语义深化 — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump + 双端展示
**Core Value:** 把成片解构成可导航、多轨道、带语义的分镜资产（分镜 + 分离音轨 + 对白 + 镜头语言 prompt + 跨镜可复用角色/道具注册表），且形态可移植——能作为下游 `@kais/infinite-canvas` 的「最终资产集合形态」被直接消费。

> 研究依据见 `.planning/research/SUMMARY.md`（HIGH 置信，全部 live-verified）。REQ-ID 前缀与 v1.0（SPEC/EXPORT/CANVAS/VERIFY）刻意不冲突。

## v1 Requirements

v1.1 milestone 范围。每条映射到一个 phase（见 Traceability）。

### CONTRACT — ShotTimelineAsset 契约 minor bump (schema_version 1→1.1，纯增量)

- [x] **CONTRACT-01**: 新增 `characters.schema.json`——角色注册表：不可变 ID（模式 `^char_[0-9]{3}$`）+ 名称 + 代表图引用 + `appearance_shots[]` + `review_state` + `looks[]`（换装/造型变更）
- [x] **CONTRACT-02**: 新增 `props.schema.json`——道具注册表（同构，ID 模式 `^prop_[0-9]{3}$`）
- [x] **CONTRACT-03**: 新增 `registry.schema.json`——草稿/审阅形状：`clusters[]`（每簇带 `review_state: proposed|confirmed|rejected` + 三档阈值标记 + 成员 shot/frame 列表）
- [x] **CONTRACT-04**: `prompts.schema.json` **纯增量**扩展——新增 optional `character_refs[]` / `prop_refs[]`（不改动现有 6 字段，**不**重构 `camera: string`）
- [x] **CONTRACT-05**: `asset.schema.json` **纯增量**扩展——`data` 新增 optional `characters`/`props` 路径；`media` 新增 optional `characters[]`/`props[]`（外置 png 相对路径，**非** base64）；`schema_version` const 升 `1`→`1.1`
- [x] **CONTRACT-06**: `export_asset.py` 引入 `SCHEMA_VERSION` 单一源常量 = `1.1`；仅当文件存在时才 emit characters/props（data+media），老资产（无这些文件）仍合法导出
- [x] **CONTRACT-07**: `verify_contract.py` `SIX_SHAPES`→`EIGHT_SHAPES` + 新增 v1.1 fixture 集 + 跨版本自检（v1 fixture 过 v1.1 schema、v1.1 fixture 过 v1 schema，各 warn-not-crash）
- [x] **CONTRACT-08**: `SPEC.md` §4 Changelog 记 `1.1` 条目 + 新增 §5.6/§5.7（characters/props 数据形状与外置媒体约定）
- [x] **CONTRACT-09**: 向后兼容冒烟——`spec/validate.py` 对 v1 `minimal` fixture 仍全绿（graceful-degrade 承诺不破）

### CINEMA — 镜头语言/动作/语义自动填充 (`step_semantic`)

- [x] **CINEMA-01**: `analysis/call_shot_analysis.py`——httpx 客户端调 `POST /api/v1/production/shot-analysis`，把 `semantic.*`/`geometry.*`/`subject.*` 映射到 prompts 的 `camera`/`action`/`lighting`/`style`/`subject` 字段
- [x] **CINEMA-02**: `run_pipeline.py` 新增 `step_semantic`（位于 `step_transcribe` 与 `step_timeline` 之间），`[N/8]` 计数全量更新
- [x] **CINEMA-03**: 路由不可达时 graceful-degrade——`prompts.json` 仍写出（空 facet 字段、schema 合法），资产仍导出；`--skip-semantic` 旗标
- [x] **CINEMA-04**: 每镜路由输出缓存 `output/<asset>/route_cache/shot_analysis/shot_XXX.json`，cache key 含 `(video_content_hash, shot_id, route_name, route_version)`；`--offline` 全局旗标只用缓存不联网
- [x] **CINEMA-05**: 步前 preflight 健康检查 + 失败时 `generator.warnings` 记录（per-shot 失败不致命，不阻断资产导出）
- [x] **CINEMA-06**: `--analysis-url` / `--analysis-timeout`（默认 960s，> 路由侧 900s `execFileSync` 上限）旗标

> **外部前置依赖（非 REQ，phase 前置条件）**：`feat/shot-geometry-nodes` + `feat/shot-analysis-route` 两未 merge 分支需先在 kais-aigc-platform 上线，否则 `step_semantic` 无法端到端验证。

### CAST — 跨镜角色/道具注册表 + re-id (`step_reid`)（最高复杂度）

- [ ] **CAST-01**: 新建 kais-aigc-platform `character-reid` 路由（`POST /api/v1/production/character-reid`，thin wrapper 仿 `shot-analysis`）+ driver `character_reid_driver.py`（SAM3 mask → DINOv2 embedding → Agglomerative 聚类 → draft registry）
- [ ] **CAST-02**: SAM3 **多帧采样**（每 shot N=3-5 帧，25/50/75% 时位，非仅首尾）+ `mask_quality` 指标 + `unusable` 标记跳过低质量帧
- [ ] **CAST-03**: DINOv2 ViT-B/14（`facebook/dinov2-base`，768-d）embedding + scikit-learn `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=τ)`
- [ ] **CAST-04**: 三档阈值（auto-merge ≥0.85 / review 0.6-0.85 / auto-distinct <0.6）；默认 τ 在 ep01 实标定（同人/异人 cosine 分布直方图取谷）后锁定
- [ ] **CAST-05**: 每簇带 `review_state: proposed|confirmed|rejected`；**仅 `confirmed` 流向下游**；产出 `registry.draft.json`
- [x] **CAST-06**: `html/gen_registry_review.py`——HITL review HTML（**一等交付物，非附属脚本**）：簇卡片 + 合并/拆分/重命名 + cosine 距离排序审阅队列 + 三档阈值可视化；产出 `registry.edits.json`
- [x] **CAST-07**: `registry/apply_edits.py`——应用审阅决定 → canonical `characters.json` + `props.json`（仅 confirmed 条目）
- [x] **CAST-08**: best-of-N 代表图自动选取（清晰度 + mask 面积 + embedding-centroid 评分）→ `characters/<id>.png` 外置文件
- [ ] **CAST-09**: `run_pipeline.py` 新增 `step_reid`（`step_semantic` 之后）；`--skip-reid` 旗标；graceful-degrade（路由不可达→跳过，资产仍导出）

### PROMPT — prompt 引用系统（叙事连贯）

- [ ] **PROMPT-01**: 后处理 `prompts.json`——按 `characters.json#appearance_shots[]` 挂 `character_refs[]`/`prop_refs[]` ID 到对应 shot
- [ ] **PROMPT-02**: `prompt_text` 重Compose——引用角色/道具时生成叙事连贯、可被 AI 视频管线复用的 prompt 文本
- [ ] **PROMPT-03**: 跨文件完整性检查（prompt 引用的 ID 必须在 registry 中存在，无 dangling）加入 `verify_contract.py`
- [ ] **PROMPT-04**: `asset.json` 嵌 `generator.registry_snapshot`（冻结 registry 状态，防后续 registry 变动使已导出资产的 prompt 引用失效）

### PRESENT — 双端展示（shot-timeline HTML + canvas 消费者）

- [ ] **PRESENT-01**: `gen_timeline_html.py` 扩展——角色/道具画廊区（外置 png 经 `serve.py` 提供）+ 点击跳转
- [ ] **PRESENT-02**: prompt 渲染加 reference chip（角色/道具可点击徽章，链接到画廊条目）
- [ ] **PRESENT-03**: 每镜「运镜分析填充」指示器（绿 chip = 路由填充；灰 chip = offline 降级空字段）
- [ ] **PRESENT-04**: canvas 消费者（kais-aigc-platform `feat/canvas-asset-collection`）——`import-from-dir.ts` `SHOT_TIMELINE_KNOWN_VERSIONS` 追加 `"1.1"` + `extractShotTimelineArtifacts` emit character/prop 子节点（`type:"asset"` + `assetType:"character"|"prop"`，gated on 新版本）；**不引入** custom renderer / 不 bump Zod
- [ ] **PRESENT-05**: `AssetNode.tsx` `typeIcons` 加 `character:'🧑'`/`prop:'🔧'`（cosmetic）+ `verify-canvas-shot-timeline.ts` 扩展 v1.1 character/prop 节点计数断言
- [ ] **PRESENT-06**: 3-mode `verify_contract.py` harness 对 v1.1 fixture 全绿（producer / consumer / e2e 三模式）

## v2 Requirements

已确认但推迟，不在当前 roadmap。

### Re-ID 精度增强
- **REID-01**: InsightFace `antelopev2`/`buffalo_l` 作为 DINOv2 精度不足时的 face fusion 信号（face-only；非商业研究许可，需评估）

### Prompt 表达
- **PROMPT-DIALECT-01**: `prompt_text` dialect 切换（段落体 vs 关键词体，按目标 AI 视频模型）

### 叙事扩展
- **CROSSVIDEO-01**: 跨成片角色连续性（同一角色跨不同视频识别为同一实体）
- **SPEAKER-01**: 对白→说话人归属（谁说了哪句台词）

### 展示增强
- **BBOX-01**: 首尾帧 per-occurrence bbox SVG 叠加
- **CANVAS-EDGE-01**: canvas character↔storyboard `appearance` 边（需先做 canvas mockup 评估视觉杂乱再定）
- **TURNAROUND-01**: 合成多角度角色 turnaround sheet（源片不存在的角度不伪造）

## Out of Scope

显式排除，含理由，防止回头再加。

| Feature | Reason |
|---------|--------|
| 角色图 base64 内嵌 `characters.json` | 资产膨胀 10-50×（甚于 frames.json）；用外置 `characters/<id>.png` + `serve.py` |
| 把 `camera: string` 重构成 `{shot_scale, primitive, speed}` 结构对象 | 破坏性 semantic shift → 触发 major bump（违反 minor-only 决定）；要结构化就**并列**加新字段 |
| shot-timeline 内重跑 ML（SAM3/DINOv2/聚类/Whisper） | 走外部 kais-aigc-platform 路由，shot-timeline 保持 thin（仅 httpx，零 ML 依赖） |
| 画布 custom renderer / 新 canvasType | 复用现有 `asset` 节点 + `assetType`，v1.0 已透传 structural Types，零 contract bump |
| CLIP / OpenCLIP 做 re-id embedding | image-text 对齐不适合实例身份识别；DINOv2 自监督才是正解 |
| schema_version 跳 `"2"` / `"3"` | 按项目 SPEC semver-lite：纯增量 = minor (`1.1`)；major 留给未来破坏性变更 |
| 修改 shot-timeline 现有检测/转录/分离算法 | validated 基线不动；新分析全部走外部路由 |
| 全自动 re-id（无 HITL） | SOTA 换衣 re-id 60-80% mAP、动画更差；误聚类率破坏叙事连贯命题——人工 review 是 feature 不是 polish |
| `prompts.schema.json` 扩到 8 facet（加 pacing/lens） | YAGNI；route 若将来暴露，编码进现有 `camera`/`style` 字符串 |

## Traceability

Phase 编号续接 v1.0（Phase 1-4 SHIPPED）。v1.1 从 Phase 5 起，dependency-ordered。

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONTRACT-01 | Phase 5 | Complete |
| CONTRACT-02 | Phase 5 | Complete |
| CONTRACT-03 | Phase 5 | Complete |
| CONTRACT-04 | Phase 5 | Complete |
| CONTRACT-05 | Phase 5 | Complete |
| CONTRACT-06 | Phase 5 | Complete |
| CONTRACT-07 | Phase 5 | Complete |
| CONTRACT-08 | Phase 5 | Complete |
| CONTRACT-09 | Phase 5 | Complete |
| CINEMA-01 | Phase 6 | Complete |
| CINEMA-02 | Phase 6 | Complete |
| CINEMA-03 | Phase 6 | Complete |
| CINEMA-04 | Phase 6 | Complete |
| CINEMA-05 | Phase 6 | Complete |
| CINEMA-06 | Phase 6 | Complete |
| CAST-01 | Phase 7 | Pending |
| CAST-02 | Phase 7 | Pending |
| CAST-03 | Phase 7 | Pending |
| CAST-04 | Phase 7 | Pending |
| CAST-05 | Phase 7 | Pending |
| CAST-06 | Phase 7 | Complete |
| CAST-07 | Phase 7 | Complete |
| CAST-08 | Phase 7 | Complete |
| CAST-09 | Phase 7 | Pending |
| PROMPT-01 | Phase 8 | Pending |
| PROMPT-02 | Phase 8 | Pending |
| PROMPT-03 | Phase 8 | Pending |
| PROMPT-04 | Phase 8 | Pending |
| PRESENT-01 | Phase 8 | Pending |
| PRESENT-02 | Phase 8 | Pending |
| PRESENT-03 | Phase 8 | Pending |
| PRESENT-04 | Phase 9 | Pending |
| PRESENT-05 | Phase 9 | Pending |
| PRESENT-06 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34 ✓
- Unmapped: 0

**Phase distribution:**
- Phase 5 (Contract v1.1): 9 requirements — CONTRACT-01..09
- Phase 6 (Cinematography Auto-Fill): 6 requirements — CINEMA-01..06
- Phase 7 (Cross-Shot Re-ID + HITL Review): 9 requirements — CAST-01..09
- Phase 8 (Prompt Reference + HTML Gallery): 7 requirements — PROMPT-01..04, PRESENT-01..03
- Phase 9 (Canvas Consumer Integration): 3 requirements — PRESENT-04..06

---
*Requirements defined: 2026-07-24*
*Last updated: 2026-07-24 after /gsd:new-project roadmap creation — 34/34 requirements mapped, 0 unmapped*
