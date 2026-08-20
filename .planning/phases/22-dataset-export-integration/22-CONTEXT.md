# Phase 22: Dataset Export + Integration - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

闭环进流水线（`step_roundtrip` slot + CLI flags）+ gallery round-trip HITL 审阅面板 + accepted 子集独立 dataset 目录导出——用户对 ep01 跑一次抽样流水线即端到端拿到 (首帧, 尾帧, prompt) 真值数据集。

Requirements: RT-05, DATASET-02, PIPE-01, PIPE-02, PRESENT-01。

**In scope:**
- `step_roundtrip` pipeline 编号 step（export 前）+ flags 全透传 + banner 重编号 + e2e
- 独立 review HTML 面板（双 video 同步播放 + 双分数 + 三态覆盖）+ roundtrip-edits.json + confirmed-only apply CLI
- dataset/<video-stem>/ 导出（per-shot 自含 + manifest + accepted/rejected 分清单）
- XSS `_esc()` hardening 覆盖 verdict/reason/attribution 全部模型产出文本
- smoke 回归 harness ≥4 场景（bash e2e mirror v1.2 Phase 14）
- UI-SPEC 生成（ROADMAP UI hint: yes——进 plan 前出设计契约）

**NOT in scope:**
- canvas roundtrip 消费（CANVAS-RT-01 后续 milestone）
- 音频 round-trip 对比（AUDIO-CMP-01 v1.4）
- h3/scorer/judge 本体改动（Phase 20/21 已锁）

</domain>

<decisions>
## Implementation Decisions

### step_roundtrip 挂载与编排（PIPE-01）
- **step_export 之前**的编号 step（regen+score+verdict 必须在 export 前完成——export 挂载 roundtrip.json 进 asset.json#data.roundtrip）；banner 重编号 [N/10]（SC1 明文）；dataset 导出在 export 后作为 plain-label post-step
- subprocess 串四模块：h3_regen → scorer → judge（--apply-verdict --tau-sim）→ dataset export（mirror sibling-subprocess 惯例；每模块自带 cache/降级）
- flags 全透传：`--skip-roundtrip` / `--comfy-url` / `--sample-shots` / `--regen-resolution` / `--max-shot-sec` / `--tau-sim`（默认 0.9670——Phase 21 锁定值进默认）
- e2e 验证：ep01 抽样端到端一次真跑（--sample-shots 2：已渲镜 cache 命中秒级 + export 挂载 + dataset 目录齐产）作 SC1 live 证明

### gallery HITL 审阅面板（PRESENT-01）
- **独立 review HTML**（`html/gen_roundtrip_review.py` 产 roundtrip_review.html——mirror gen_registry_review/gen_speaker_review 先例：操作员 offline 开、隔离 XSS 面、confirmed-only apply）
- HITL 语义 mirror registry/speaker 全套：面板勾选覆盖（accept/reject/维持 auto）→ 产 `roundtrip-edits.json` → 独立 apply CLI confirmed-only 写回 sidecar（`source: "human"` + `decided_at`；human 覆盖是唯一允许改已冻结 verdict 的路径——schema source 字段为此设计）
- **双 `<video>` 同步播放**（原片段时窗裁切 vs regen mp4，同步 play/pause；serve.py Range 服务已在）
- 呈现字段：双分数（sim 数值条 + 归因标签色块）+ judge reason + prompt 快照（可折叠）+ 当前 verdict 与来源标记（auto/human）+ 覆盖按钮三态 + 已复核计数

### dataset 导出（RT-05, DATASET-02）
- `dataset/<video-stem>/`：per-shot `shot_NNN/`（first_frame.jpg + last_frame.jpg + prompt.json 自含）+ manifest.json（索引/汇总/τ/引擎版本）+ accepted.txt / rejected.txt 分清单
- prompt.json **自含可独立消费**：prompt_text + 全 facets 快照 + character_refs/prop_refs + 该镜 scores + attribution + 引擎版本 + vch
- 首尾帧**复用 h3_regen 的全分辨率提帧**（同源同分辨率同实现——SFT 消费端要的就是喂给 h3 的那对帧）
- rejected.txt 每行 `shot_id sim attribution reason摘要`（可 grep 可审计）+ manifest 里 rejected 分桶统计（faithful<τ=N / diverged=N）

### smoke 回归 harness + UI-SPEC（PIPE-02）
- ComfyUI down 场景：`--comfy-url http://127.0.0.1:1`（dead port）→ roundtrip 缺席 + `[roundtrip]` warning + v1.2 数据文件 byte-identical（RT-01 红线 pipeline 级复验）
- **bash e2e 脚本** `tests/test_phase22_e2e.sh`（mirror v1.2 Phase 14）+ pytest 单测补 wiring；四场景：down-degrade / cache-hit 续跑（二跑零重渲断言 + wall 对比）/ 抽样模式 / VRAM-guard 拒提交
- **UI-SPEC 生成**（gsd-ui-phase——审阅面板设计契约先锁，再进 plan；XSS hardening 呈现与三态按钮语义进契约）

### Claude's Discretion
- review HTML 排版细节（mirror registry review 风格基调）、manifest 具体字段次序
- e2e 脚本断言措辞、日志 grep 锚点
- dataset 导出模块文件名（analysis/roundtrip/export_dataset.py 或类似）

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analysis/roundtrip/{h3_regen,scorer,judge}.py`（Phase 20/21 已验证三件套——step_roundtrip 的编排对象）
- `html/gen_registry_review.py` + `html/gen_speaker_review.py`（HITL review HTML + confirmed-only apply 先例——面板全套路数）
- `registry/apply_edits.py`（confirmed-only 硬门 + idempotent 先例——roundtrip apply CLI 的直接模板）
- `run_pipeline.py`（step 编排 + banner 惯例 + plain-label post-step 先例 5.5/5.6 + --force 清单）
- `scripts/export_asset.py`（data.roundtrip 挂载已在——step 编排只需保证顺序）
- `scripts/serve.py`（Range-aware 媒体服务——双 video 同步播放的载体）
- v1.2 Phase 14 e2e 先例（bash smoke harness 模式）
- Phase 18 `roundtrip-edits` 无先例但 registry-edits schema 有（edits 文件 schema 化惯例）

### Established Patterns
- confirmed-only HITL 硬门（面板永不直接写 sidecar）
- `_esc()` XSS 三层 hardening（timeline.html 先例——PRESENT-01 明文扩展到 verdict/reason/attribution）
- 子进程 sibling 调用 + graceful-degrade + [N/9] banner 计数

### Integration Points
- run_pipeline.py step 序列（export 前插编号 step + banner 重编号波及）
- asset.json#data.roundtrip 挂载（export 时机）
- serve.py 媒体路径（review HTML 的 video src）
- dataset/<video-stem>/ 全新目录（消费端零契约依赖）

</code_context>

<specifics>
## Specific Ideas

- SC3 明文注入用例：`<script>` / `onerror=` / base64 三类不执行——测试集硬要求
- SC5 四场景 mirror v1.2 Phase 14 模式（ROADMAP 明文）
- τ_sim=0.9670 是 Phase 21 Kai 裁决值——进 --tau-sim 默认

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.（canvas 消费 / 音频对比均 REQUIREMENTS Future 名单）

</deferred>
