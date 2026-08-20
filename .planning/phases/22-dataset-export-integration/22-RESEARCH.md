# Phase 22: Dataset Export + Integration - Research

**Researched:** 2026-08-20
**Domain:** pipeline integration (step wiring + banner renumber + force/cache lists) + HITL review HTML (mirror registry/speaker precedent) + dataset export module (stdlib-only) + bash smoke harness
**Confidence:** HIGH（全部关键断言经本 session 逐行 Read/grep 实证；外部依赖零新增，无 npm/PyPI 包需要验证）

## Summary

Phase 22 是纯集成 phase：三件套（h3_regen/scorer/judge，Phase 20/21 已验证）已存在且各自带 cache/degrade，本 phase 的工作是把它们串进 `run_pipeline.py` 编号 step、新增 `html/gen_roundtrip_review.py` + roundtrip-edits apply CLI（mirror registry 先例）、新增 `analysis/roundtrip/export_dataset.py`（复用 `h3_regen.extract_endpoint_frames`）、加 XSS 注入测试与 4 场景 bash harness。**零新依赖、零新 schema 概念**（roundtrip-edits.schema.json 是 registry-edits 的直系变体）。

最关键的三个集成事实（均已实证）：(1) **`step_export` 的 mtime cache inputs 不含 roundtrip.json**（run_pipeline.py:573-580）——若不把 roundtrip.json 作为**条件性 input** 加进去（mirror :471-474 audio_semantic 模式），ep01 e2e 会 cache-hit 陈旧 asset.json（现存 asset.json 是 schema 1.2、无 data.roundtrip，export 于 08-19 早于 roundtrip.json 08-20），SC1 的挂载断言必失败；反之若**无条件**加入，roundtrip.json 缺席时 `_safe_mtime` 返 +inf → 永久 cache miss → 每跑必重写 asset.json，破坏 byte-identical-absent。条件性 append 是唯一正解。(2) **banner 重编号波及 3 个文件 29 处 + 两个 wiring 测试的正则与子串断言**（`\[\d/9\]` 假定单位数字，[10/10] 是双位）——测试不更新则全红。(3) **ep01 现存 roundtrip.json 19 镜 verdict 全冻结（4 accepted: shot 10/61/75/84 / 15 rejected）且 `uniform_sample(93,2)=[1,47]` 双双 cache 命中**——`--sample-shots 2` e2e 真实零重渲，"秒级"承诺成立；但 h3_regen 批前 guard 无条件跑（TTS kill + 2×POST /free + VRAM 检查），当前 GPU1 free 22990MiB 仅高出阈值 22528MiB **约 460MiB**，margin 很薄，e2e 前需探测。

**Primary recommendation:** step_roundtrip 插在 step_timeline[8] 与 step_export 之间成为 [9/10]（export 变 [10/10]，timeline 不动——gen_timeline_html.py 零 roundtrip 引用已验证）；dataset 导出做 export 后 plain-label post-step（mirror 9.5 canvas-import，keyed on roundtrip.json 存在）；review HTML 在 step_roundtrip 内作为末位 subprocess（mirror step_reid 双 subprocess 先例），外层 mtime cache 命中时仍补生成 HTML（纯 Python 毫秒级）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**step_roundtrip 挂载与编排（PIPE-01）**
- **step_export 之前**的编号 step（regen+score+verdict 必须在 export 前完成——export 挂载 roundtrip.json 进 asset.json#data.roundtrip）；banner 重编号 [N/10]（SC1 明文）；dataset 导出在 export 后作为 plain-label post-step
- subprocess 串四模块：h3_regen → scorer → judge（--apply-verdict --tau-sim）→ dataset export（mirror sibling-subprocess 惯例；每模块自带 cache/降级）
- flags 全透传：`--skip-roundtrip` / `--comfy-url` / `--sample-shots` / `--regen-resolution` / `--max-shot-sec` / `--tau-sim`（默认 0.9670——Phase 21 锁定值进默认）
- e2e 验证：ep01 抽样端到端一次真跑（--sample-shots 2：已渲镜 cache 命中秒级 + export 挂载 + dataset 目录齐产）作 SC1 live 证明

**gallery HITL 审阅面板（PRESENT-01）**
- **独立 review HTML**（`html/gen_roundtrip_review.py` 产 roundtrip_review.html——mirror gen_registry_review/gen_speaker_review 先例：操作员 offline 开、隔离 XSS 面、confirmed-only apply）
- HITL 语义 mirror registry/speaker 全套：面板勾选覆盖（accept/reject/维持 auto）→ 产 `roundtrip-edits.json` → 独立 apply CLI confirmed-only 写回 sidecar（`source: "human"` + `decided_at`；human 覆盖是唯一允许改已冻结 verdict 的路径——schema source 字段为此设计）
- **双 `<video>` 同步播放**（原片段时窗裁切 vs regen mp4，同步 play/pause；serve.py Range 服务已在）
- 呈现字段：双分数（sim 数值条 + 归因标签色块）+ judge reason + prompt 快照（可折叠）+ 当前 verdict 与来源标记（auto/human）+ 覆盖按钮三态 + 已复核计数

**dataset 导出（RT-05, DATASET-02）**
- `dataset/<video-stem>/`：per-shot `shot_NNN/`（first_frame.jpg + last_frame.jpg + prompt.json 自含）+ manifest.json（索引/汇总/τ/引擎版本）+ accepted.txt / rejected.txt 分清单
- prompt.json **自含可独立消费**：prompt_text + 全 facets 快照 + character_refs/prop_refs + 该镜 scores + attribution + 引擎版本 + vch
- 首尾帧**复用 h3_regen 的全分辨率提帧**（同源同分辨率同实现——SFT 消费端要的就是喂给 h3 的那对帧）
- rejected.txt 每行 `shot_id sim attribution reason摘要`（可 grep 可审计）+ manifest 里 rejected 分桶统计（faithful<τ=N / diverged=N）

**smoke 回归 harness + UI-SPEC（PIPE-02）**
- ComfyUI down 场景：`--comfy-url http://127.0.0.1:1`（dead port）→ roundtrip 缺席 + `[roundtrip]` warning + v1.2 数据文件 byte-identical（RT-01 红线 pipeline 级复验）
- **bash e2e 脚本** `tests/test_phase22_e2e.sh`（mirror v1.2 Phase 14）+ pytest 单测补 wiring；四场景：down-degrade / cache-hit 续跑（二跑零重渲断言 + wall 对比）/ 抽样模式 / VRAM-guard 拒提交
- **UI-SPEC 生成**（gsd-ui-phase——已交付：22-UI-SPEC.md approved，XSS hardening 呈现与三态按钮语义已进契约）

### Claude's Discretion
- review HTML 排版细节（mirror registry review 风格基调）、manifest 具体字段次序
- e2e 脚本断言措辞、日志 grep 锚点
- dataset 导出模块文件名（analysis/roundtrip/export_dataset.py 或类似）

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.（canvas 消费 CANVAS-RT-01 / 音频对比 AUDIO-CMP-01 均 REQUIREMENTS Future 名单）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RT-05 | accepted 子集独立 dataset 目录导出——`dataset/<video-stem>/`（per-shot 首帧/尾帧 jpg + prompt.json + manifest 含 scores/attribution）；消费端不依赖 asset 契约 | `extract_endpoint_frames` 复用形状（h3_regen.py:387-417）+ prompts.json 76/93 镜实测字段（§dataset 导出细节）+ 现成 route_cache/h3_regen/frames/ 19 对帧可直拷 |
| DATASET-02 | dataset manifest + hard-negative 索引——accepted/rejected 分清单，含 prompt 快照与引擎版本（可复现、可审计） | roundtrip.schema.json 全字段（regen 4-tuple 含 engine_version/vch）+ τ 分桶算法（judge.summarize_scores 先例）+ ep01 实测 4/15 分布 |
| PIPE-01 | `step_roundtrip` 流水线 slot + CLI flags + banner 重编号 + `--force` 缓存清单扩展 | 29 处 banner 清单 + 插入点论证（§Pattern 1）+ step_export 条件性 input 修补（**必须**，否则 e2e 断言失败）+ --force 清单现状与建议 |
| PIPE-02 | smoke 回归 harness ≥4 场景，mirror v1.2 Phase 14 模式 | 四场景逐个可触发路径实证（§Validation Architecture）+ v1.2 Phase 14 harness 形态（783 行 python、ALL_SCENARIOS_PASS、exit 契约）+ Phase 12 bash 风格（tests/run_audio_analysis_smoke.sh） |
| PRESENT-01 | gallery round-trip 审阅面板 + HITL 复核导出 + XSS `_esc()` hardening | UI-SPEC 已锁全部设计契约；`_esc()` 三层惯例实证（§XSS）+ registry/speaker 双先例 CLI 形状 + apply CLI confirmed-only 模板（registry/apply_edits.py） |
</phase_requirements>

## Architectural Responsibility Map

本项目是 CLI pipeline + 静态 HTML 生成器（无 web 服务层），按 pipeline 编排/计算模块/HITL 面/导出面/消费端分层：

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| roundtrip 编排（regen→score→verdict→review HTML） | run_pipeline.py step_roundtrip（subprocess 串） | 各模块自带 cache/degrade | 模块已各自成熟能独立跑；编排层只管顺序+flags+cache 短路，不掺业务逻辑（sibling-subprocess 惯例） |
| asset.json#data.roundtrip 挂载 | scripts/export_asset.py（已有，:375-404） | run_pipeline step_export 条件性 mtime input | 挂载逻辑 Phase 18 已交付；本 phase 只保证顺序 + 修补 mtime inputs |
| dataset 导出 | analysis/roundtrip/export_dataset.py（新，post-step） | — | 独立目录独立模块，消费端零 asset 契约依赖（locked decision #6）；从 sidecar+prompts 纯派生 |
| HITL 审阅呈现 | html/gen_roundtrip_review.py（新，生成器） | scripts/serve.py（Range 服务 video） | 静态 HTML offline 开；video src 相对路径经 serve.py 206 |
| verdict 写回（human 覆盖） | roundtrip apply CLI（新，standalone） | roundtrip.schema.json verdict.source 字段 | 面板永不写 sidecar（HITL 硬门）；apply 是唯一冻结覆盖路径 |
| XSS 防护 | 生成器内联 `_esc()`（Python）+ JSON bootstrap `</` 转义 + JS textContent | schema maxLength 2000 上界 | html/ 是 namespace package，跨文件 import 禁止——必须每文件内联（gen_registry_review.py:83-84 实证惯例） |

## Standard Stack

### Core（全部已存在，零新增）

| Library/Module | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib（argparse/subprocess/json/importlib/urllib） | 3.12.3 | 全部新代码 | 项目零三方依赖惯例（CLAUDE.md stack 段）[VERIFIED: codebase] |
| analysis/roundtrip/h3_regen.py | 1444 行 | regen 编排对象 + `extract_endpoint_frames`/`resolve_source_video`/`video_content_hash`/`load_shot_prompts`/`_atomic_write_json` 共享件 | Phase 20 已验证；judge.py 已以 importlib 别名 `h3_regen_shared` 复用（judge.py:99-103）[VERIFIED: codebase] |
| analysis/roundtrip/scorer.py / judge.py | 660/922 行 | scores 半边 / verdict 冻结应用器 | Phase 21 已验证；CLI 形状见 §Pattern 3 [VERIFIED: codebase] |
| html/gen_registry_review.py + gen_speaker_review.py | 728/760 行 | review HTML + exportEdits 先例 | UI-SPEC 指定唯一模板 [VERIFIED: codebase] |
| registry/apply_edits.py | 547 行 | confirmed-only apply CLI 模板 | "直接模板"（CONTEXT code_context 明文）[VERIFIED: codebase] |
| scripts/serve.py | 125 行 | Range-aware 媒体服务（默认 :8765） | 双 video seek 依赖 206 [VERIFIED: codebase] |
| pytest | 9.0.3 | wiring/单测 | 已装可用 [VERIFIED: runtime `python3 -m pytest --version`] |
| jsonschema（Draft202012Validator） | 已在用（apply_edits/scorer/judge） | edits schema 预校验 | T-07-02 惯例 [VERIFIED: codebase grep] |

### Supporting
无。

### Alternatives Considered
无——CONTEXT 锁死先例 mirror 路线，零替代探索。

**Installation:** 无任何安装。**注意**：本 phase 明确不引入 npm/CDN/三方 JS/CSS（UI-SPEC Registry Safety 段锁定）。

## Package Legitimacy Audit

无外部包安装。全部实现 = Python stdlib + 浏览器原生 API（Blob/URL.createObjectURL/Media Fragments）+ 已在库依赖。**Disposition: N/A（零新增）**。

## Architecture Patterns

### System Architecture Diagram

```
run_pipeline.py（[N/10] 重编号后）
│
├─ [1..8/10]  既有步骤（detect/separate/transcribe/semantic+5.5+5.6/reid/audio_semantic/timeline）── 全部不动（除 banner 分母）
│
├─ [9/10] step_roundtrip（新编号 step；subprocess 串，每段 check=True fail-loud、模块内自带 degrade exit 0）
│    ├─ subprocess 1: h3_regen.py     ──regen mp4──▶ roundtrip/shot_NNN_regen.mp4 + sidecar regen 半边
│    │      （gate: ComfyUI /system_stats 不可达 → warning comfyui_unreachable + exit 0 → 整步降级）
│    ├─ subprocess 2: scorer.py       ──scores.midframe_sim──▶ sidecar（cache-hit 零模型加载）
│    ├─ subprocess 3: judge.py --apply-verdict --tau-sim 0.9670 ──verdict{source:auto}──▶ sidecar（冻结跳过）
│    └─ subprocess 4: gen_roundtrip_review.py ──▶ roundtrip_review.html（读 sidecar+shots+prompts+原视频）
│
├─ [10/10] step_export（原 [9/9]；mtime inputs **条件性加 roundtrip.json**）
│    └─ export_asset.py:375-404 读 work_dir/roundtrip.json ──▶ asset.json#data.roundtrip{path,accepted_count,rejected_count}
│
└─ (plain-label post-step) dataset 导出（mirror 9.5 canvas-import；keyed on roundtrip.json 存在）
     └─ export_dataset.py ──▶ dataset/<video-stem>/{shot_NNN/{first_frame.jpg,last_frame.jpg,prompt.json}, manifest.json, accepted.txt, rejected.txt}
            首尾帧来源: route_cache/h3_regen/frames/kst_{vch}_shot{NNN}_{ff,lf}.jpg（现成直拷）→ 缺席则 extract_endpoint_frames 重提（同一实现）

离线 HITL 环（操作员手动，pipeline 永不调用）：
  roundtrip_review.html ──(三态按钮 + Blob 下载)──▶ roundtrip-edits.json
       └─▶ apply CLI（standalone，schema 预校验 + confirmed-only + idempotent）
              ──▶ roundtrip.json verdict{decision, source:"human", decided_at}（唯一冻结覆盖路径）
                     └─▶ 重跑 step_roundtrip/dataset 导出 → accepted 子集随之更新
```

### Recommended Project Structure（新增文件）

```
analysis/roundtrip/export_dataset.py   # dataset 导出模块（discretion 定名；importlib 复用 h3_regen 共享件，mirror judge.py:99-103）
html/gen_roundtrip_review.py           # 审阅面板生成器（内联 _esc，mirror gen_registry_review.py 结构）
registry/apply_roundtrip_edits.py      # 或 analysis/roundtrip/apply_edits.py（discretion）——confirmed-only apply CLI
spec/schemas/roundtrip-edits.schema.json  # edits schema（mirror registry-edits.schema.json）
tests/test_phase22_e2e.sh              # 4 场景 bash harness（CONTEXT 锁定文件名）
tests/test_roundtrip_review.py         # XSS 三注入用例 + 面板生成单测（SC3）
tests/test_export_dataset.py           # dataset 导出单测（RT-05）
tests/test_roundtrip_apply_edits.py    # apply CLI 单测（confirmed-only/idempotent）
tests/test_pipeline_roundtrip_wiring.py # step_roundtrip wiring 静态断言（mirror vision_wiring 系列）
tests/fixtures/roundtrip_sample.json   # 合成 sidecar fixture（schema-valid，含注入 payload 变体）
```

### Pattern 1: 编号 step 插入 + banner 重编号（PIPE-01）

**What:** step_roundtrip 成为编号 step [9/10]，插在 step_timeline 与 step_export 之间。
**When to use / 论证:** gen_timeline_html.py 经 grep 实证**零** roundtrip 引用 → timeline 不消费 sidecar → 插在 timeline 后只改 export 一个编号（8 保持、roundtrip=9、export 9→10）；若插 timeline 前则 8/9 两步都要改号，纯增 churn。export 必须在 roundtrip 后（挂载条件 export_asset.py:375-404 已在，只要顺序保证）。

**重编号精确波及面（本 session 实测）：**

| 文件 | 波及点 | 说明 |
|------|--------|------|
| run_pipeline.py | **29 处** `[N/9]` banner 字面量（grep `\[[0-9]/9\]` 实数） | 1-8 步只改分母 9→10；export 3 处 `[9/9]` → `[10/10]`（**双位数**）；新 step_roundtrip 增 ~4 处 `[9/10]`（skip/cached/run_step/HTML） |
| run_pipeline.py 模块 docstring（:4-35） | 步骤清单散文 | 必须同步插入 roundtrip 条目 + 重排 canvas post-step 编号（否则文档漂移，mirror 既有 docstring 精确习惯） |
| tests/test_pipeline_vision_wiring.py:98-107 | `re.findall(r"\[\d/9\]", src)` + `assert "[5.5/9]" not in src and "[6/9" in src` | **必须更新**：regex `\[\d/9\]` 单位数字假定被 `[10/10]` 打破；`"[6/9"` 子串在 `[6/10]` 中不存在 → 断言红。改为 `\[\d+/10\]` + `"[6/10"` |
| tests/test_pipeline_vision_seq_wiring.py:98-107 | 同上 + `"[5.6/9]" not in src` 锁 | 同步改（5.5/5.6 plain-label 锁语义保持：`"[5.5/10]" not in src` 等） |

**Banner grep 锚（e2e/测试用）：** `[9/10] roundtrip`、`[10/10] ShotTimelineAsset export`；step 内模块输出沿用各自 STEP_TAG `[roundtrip]`（三模块同 tag，warnings strip 语义共用——h3_regen.py:153/scorer.py:79/judge.py:107 实证）。

**新 step 的外层 cache（推荐，mirror step_reid :287-307）：** TOCTOU-safe mtime（`roundtrip.json` vs `prompts.json`+`shots.json`）+ video 身份 sidecar（`roundtrip.json.video-stamp`，mirror :293-306）。**关键细节**：cache 命中路径仍需在 roundtrip.json 存在时生成 review HTML（HTML 可能尚未存在——ep01 首跑 e2e 正是此态：sidecar 已在、HTML 是新文件；HTML 生成纯 Python 毫秒级，无条件补跑无代价）。若无外层 cache 则每次跑都过 h3_regen 批前 guard（含 eye lease 等待，最长 1800s 阻塞风险）——外层 cache 同时消除该风险。

### Pattern 2: dataset 导出 post-step（mirror 9.5 canvas-import）

**What:** step_export 之后 plain-label post-step，**keyed on `roundtrip.json` 文件存在**（mirror run_pipeline.py:926-933 canvas-import keyed on asset.json 的形态），不占编号不 bump counter。
**Example（骨架，源 run_pipeline.py:926-953 实测形态）:**
```python
# (roundtrip-dataset post-step —— 无编号 plain label，mirror canvas-import 先例)
rt_json = os.path.join(work_dir, "roundtrip.json")
if not os.path.isfile(rt_json):
    print("[roundtrip-dataset] warning: roundtrip.json 不存在（step_roundtrip 被跳过/降级），跳过 dataset 导出")
else:
    cmd = [sys.executable, str(HERE / "analysis" / "roundtrip" / "export_dataset.py"),
           "--work-dir", work_dir, "--tau-sim", str(args.tau_sim)]
    # NOT run_step —— graceful-degrade 自写 check=False（mirror canvas-import T-AW2-03）
```
**目录根建议（Open Question #1）:** CONTEXT/RT-05 写 `dataset/<video-stem>/`（两层）——暗示独立 dataset 根。推荐 `--dataset-root` 默认 `<output-dir>/dataset` → 落盘 `output/dataset/<video-stem>/`（跨视频可累积集合，符合"消费端取数据集"心智）。若解读为 work_dir 内 `output/<video-stem>/dataset/` 则 video-stem 层冗余。需 planner 收口。

### Pattern 3: sibling-subprocess 串四模块 + flags 透传

四模块 CLI 实测形状（透传表，全部 [VERIFIED: codebase]）：

| run_pipeline flag（新） | 默认 | 透传到 | 目标模块 flag |
|---|---|---|---|
| `--skip-roundtrip` | False | （本步短路，mirror step_semantic :212-214） | — |
| `--comfy-url` | `http://127.0.0.1:8188`（h3_regen.py:142 COMFY_URL_DEFAULT） | h3_regen / judge | `--comfy-url`（两模块同名） |
| `--sample-shots` | 0（0=全量，h3_regen.py:1202） | h3_regen | `--sample-shots` |
| `--regen-resolution` | `1344x768`（h3_regen.py:1206-1209） | h3_regen | `--regen-resolution` |
| `--max-shot-sec` | 10.0（h3_regen.py:1204） | h3_regen | `--max-shot-sec` |
| `--tau-sim` | **0.9670**（Phase 21 Kai 锁定值，PROJECT.md Key Decisions v1.3 Phase 21 行 + 21-VERIFICATION #4 实证） | judge + export_dataset | `--tau-sim` |

**注意两点：**
1. **ROADMAP SC1 写 `--comfyui-url`，CONTEXT 与 h3_regen 实际 flag 是 `--comfy-url`**——以 CONTEXT 为准（`--comfy-url`），ROADMAP 是散文笔误；plan 里加一条 grep 断言防漂移。
2. **judge.py `--tau-sim` 自身 default=None 且 `--apply-verdict` 无 τ 时 sys.exit（judge.py:712-716）**——推荐**不改 judge**（保持 standalone 显式门），由 run_pipeline 默认 0.9670 并**总是显式透传**。这样 standalone 用户的显式安全门不破，pipeline 用户拿到锁定默认。

scorer 透传：`--device`（pipeline 无对应 flag；可用现有 `--device`？**不要**——pipeline `--device` 默认 cuda:1 是 Demucs/Whisper 共用，scorer 默认 cuda:0=3060Ti 零竞争是刻意设计 scorer.py:512-514，不透传、让 scorer 用自身默认）。judge 透传：`--comfy-url`（judge 启动前 POST /free 用）。

### Pattern 4: step_export 条件性 mtime input（本 phase 最重要的一行修补）

```python
# step_export 内（run_pipeline.py:573-580 inputs 列表之后追加）：
# Phase 22：roundtrip.json 条件性入 cache inputs（mirror step_timeline :471-474 audio_semantic
# 模式）。存在且比 asset.json 新 → miss → 重导出挂载 data.roundtrip；缺席 → 不入 inputs
# → cache 命中保持 → byte-identical-absent（RT-01 红线）。**绝不无条件 append**：
# _safe_mtime(缺席)=+inf 会永久 miss，每跑重写 asset.json。
roundtrip_json_path = os.path.join(work_dir, "roundtrip.json")
if os.path.exists(roundtrip_json_path):
    inputs.append(roundtrip_json_path)
```

**实证必要性：** ep01 现存 asset.json（mtime 08-19 10:51，schema **1.2**、data.roundtrip **缺席**）早于 roundtrip.json（08-20 10:05）——不修则 e2e 里 export cache-hit、挂载断言（`data.roundtrip == {path, accepted_count:4, rejected_count:15}` + `schema_version == "1.3"`）必失败；修了则正好构成 e2e 的 live 证明（陈旧 1.2 asset 被正确强制重导出升 1.3）。

### Pattern 5: HITL 面板 + apply CLI（mirror registry 全套）

- 面板生成器 CLI（UI-SPEC 已锁）：`--roundtrip <roundtrip.json> --video <原视频> --shots <shots.json> --prompts <prompts.json> --tau-sim <τ 默认 0.9670> --output <roundtrip_review.html>`（对照 gen_registry_review.py:695-701 的 --draft/--video/--shots/--output 四 required 先例，多 --prompts/--tau-sim 两个）
- exportEdits JS：逐行 mirror gen_registry_review.py:642-669（Blob + URL.createObjectURL + a.download + revoke）；payload = UI-SPEC 锁定的 `{accept_overrides:[int], reject_overrides:[int], review_notes:str}`，shot_id 升序、只收显式覆盖
- roundtrip-edits.schema.json：mirror registry-edits.schema.json 骨架——`additionalProperties:false`、全字段 optional、空 `{}` valid（操作员无改动）、`accept_overrides/reject_overrides: array of integer minimum 1`（shot_id 是 int，非 char_NNN 字符串 pattern——这是与 registry-edits 的唯一结构性差异）、`review_notes: string`。**推荐建 schema**（问 2 答复）：两先例（registry/speaker）都建了且 T-07-02 强制 apply 前 Draft202012Validator 预校验，schema 是 apply 安全门的一半。
- apply CLI：mirror registry/apply_edits.py 的骨架——schema 预校验 → 逐条写 `verdict{decision, source:"human", decided_at:UTC ISO}` → READ-merge 写 sidecar（**复用 judge._merge_write_sidecar 语义**，importlib 拉 judge 或 h3s 共享件）→ 逐行审计 `[roundtrip-apply] shot_007 auto→human/accepted` → 计数汇总。idempotent：重放同 edits 文件第二遍是 no-op diff（decided_at 会变——**取舍点**：registry 先例 idempotent 到 byte-identical；roundtrip 的 decided_at 重放更新可接受（仍是 human 态）或加"已 human 且同 decision 则跳过"守卫。**推荐后者**（真 idempotent + 审计友好），与 judge.apply_verdict 的 frozen-skip 语义对齐）。
- **与 judge.apply_verdict 的关键语义差**：apply_verdict 对已冻结 verdict 一律跳过（judge.py:530-532）；apply CLI 恰相反——human 覆盖是**唯一**允许改冻结 verdict 的路径（CONTEXT 明文，schema source 字段设计用途）。

### Pattern 6: dataset 导出模块内部形状

```python
# analysis/roundtrip/export_dataset.py —— importlib 复用共享件（mirror judge.py:99-103）
import importlib.util
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)
# 可复用：h3s.extract_endpoint_frames / resolve_source_video / video_content_hash /
#         load_shot_prompts / _atomic_write_json / _iter_sidecar_errors（写前自校验）
```

- **首尾帧来源（推荐两级）：** 先查 `route_cache/h3_regen/frames/kst_{vch}_shot{NNN:03d}_{ff,lf}.jpg`（ep01 实测 19 对全在，直拷零成本、字节即 h3 实喂帧）→ 缺席才 `h3s.extract_endpoint_frames(src_video, shot, vch, tmp_dir)` 重提（同一实现=同分辨率同 q:v 2 确定性）→ 统一改名落 `dataset/<video-stem>/shot_NNN/first_frame.jpg|last_frame.jpg`。注意 `extract_endpoint_frames` 的目标名是固定的 `kst_..._ff.jpg`——落 dataset 名需提取后 rename（或提进 shot 目录再改名，函数本身不管命名契约）。
- **prompt.json 自含字段（ep01 prompts.json 实测 entry keys）：** `shot_id, start_sec, end_sec, duration, prompt_text, subject, action, camera, scene, lighting, style, character_refs, prop_refs`（**顶层是 list、六 facet 是平键非嵌套 facets 对象、无 prompt_version 键**——版本从 roundtrip regen.prompt_version 取）+ 合并 sidecar 的 `scores`/`verdict`/`attribution` + `regen.{engine_name, engine_version, prompt_version, video_content_hash}`。
- **manifest：** 索引（shot_id→dir）+ 汇总（accepted/rejected 计数）+ τ + 引擎版本 + rejected 分桶 `faithful_below_tau=N / diverged=N`（算法 mirror judge.summarize_scores 的分桶 judge.py:604-622，但导出时直接从冻结 verdict 统计即可，无需重算）。
- **写前自校验：** 导出的 prompt.json/manifest 无独立 schema（dataset 不是契约面——消费端不依赖 asset 契约是 RT-05 的点）；**不要**为 dataset 建 schema（过度契约化，违背 locked decision #6 精神）。sidecar 读取端可复用 `h3s._iter_sidecar_errors` 做 defensive 校验。

### Anti-Patterns to Avoid

- **无条件把 roundtrip.json append 进 step_export inputs** → 永久 cache miss + asset.json 每跑重写（generated_at 漂移）→ 破 byte-identical-absent（见 Pattern 4）
- **pipeline --force 清 roundtrip/ 或 roundtrip.json** → 违反 Phase 20 20-REVIEW WR-01 收紧（verdict 是人工/冻结数据，红线"rejected 永不删除"；run_pipeline.py:768-773 注释明文）。--force 现有清单**保持不动**；route_cache rmtree 已天然覆盖 h3_regen/scorer/judge 三 cache 目录。dataset/ 是纯派生数据，若要清由 export_dataset 模块自管（每次重建自身目录，显式清单不 glob 父级——T-14-01 惯例），pipeline --force 不必加。
- **让 dataset post-step 用 run_step（check=True）** → 导出失败会 raise 阻断管线；post-step 必须 graceful-degrade（mirror canvas-import 自写 check=False）
- **在 html/ 内跨文件 import `_esc`** → html/ 是 namespace package 无 `__init__.py`，先例是每文件内联（gen_registry_review.py:83-84 docstring 明文"避免 import-resolution 歧义"）
- **把 review HTML 生成做成独立编号 step 或 pipeline 外手动步骤** → step_reid 先例（:327-334）是 draft 产出后同 step 内第二 subprocess；roundtrip_review.html 同理挂在 step_roundtrip 尾部
- **step_roundtrip 透传 pipeline `--device` 给 scorer** → 会把 cuda:1（3090，h3 渲染位）灌给 scorer，违背其 cuda:0 零竞争刻意默认（scorer.py:512-514）

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 首尾帧提取 | 自写 ffmpeg 时窗 seek/guard/命名 | `h3_regen.extract_endpoint_frames`（:387-417） | CONTEXT 明文"同源同分辨率同实现"；LAST_FRAME_GUARD_SEC 前移防越界、删旧再提防残留、fail-loud stderr 附带全是踩过的坑 |
| sidecar READ-merge 写入 | 自写 merge/backup/校验 | `judge._merge_write_sidecar` + `h3s._atomic_write_json` + `.bak-<ts>` 备份惯例（scorer.py:347-451 全套先例） | 剔除坏条目保人工数据、写前两层 schema 自校验、原子写 |
| edits schema 校验 | 手写 if 校验 | Draft202012Validator + roundtrip-edits.schema.json（T-07-02 惯例） | registry/speaker 双先例同款安全门 |
| banner/步骤静态锁 | 手工数 | wiring test 的 `re.findall` 计数断言（test_pipeline_vision_seq_wiring.py:98-107 直接改用） | grep 锁是本 repo 防 phantom bump 的成熟机制 |
| VRAM guard / cache / 降级 | 任何复刻 | 三模块自带（Phase 20/21 已验证） | 编排层只透传 flags |

**Key insight:** 本 phase 的全部新颖性在"接线"与"呈现"，计算/缓存/降级/写盘语义全部已存在且被测试覆盖——新代码应当主要是 argv 构造、HTML 模板和文件搬运。

## Common Pitfalls

### Pitfall 1: banner 正则单位数字假定
**What goes wrong:** 新 banner `[10/10]` 是双位数；wiring 测试 `re.findall(r"\[\d/9\]", src)` 匹配不到任何 `[10/10]`，且 `"[6/9" in src` 断言假——两个既有测试文件必红。
**Why:** 测试写于 9 步时代，隐含 N<M≤9 假定。
**How to avoid:** 重编号 commit 必须同步改两个 wiring 测试（regex → `\[\d+/10\]`、子串 → `"[6/10"`、5.5/5.6 锁 → `"[5.5/10]" not in src`）。新 wiring 测试同样用 `\d+` 形态。
**Warning signs:** pytest tests/test_pipeline_vision*_wiring.py 红。

### Pitfall 2: step_export cache 陈旧命中（本 phase 独有）
**What goes wrong:** ep01 e2e 后 asset.json 仍是 1.2 无 data.roundtrip——roundtrip.json 不在 step_export inputs 里，mtime cache 判 asset 新于全部 inputs → 跳过重导出。
**How to avoid:** Pattern 4 条件性 append。**Warning signs:** e2e 断言 `data.roundtrip` None / schema_version 停在 1.2。

### Pitfall 3: e2e GPU1 free VRAM margin 仅 ~460MiB
**What goes wrong:** guard 阈值 BATCH_MIN_FREE_MIB=22528（22GB，h3_regen.py:210），当前 3090 free=22990MiB——ComfyUI 自身 cache 驻留波动（docstring 记载可达 ~18GB，:60）或任一进程多占 500MB 即触发 `批开始 free=... < 22528MiB` 拒绝 → e2e 降级路径而非全链路。
**How to avoid:** e2e 脚本先探测（nvidia-smi 查 GPU1 free ≥ 22528）再跑；不满足时打印诊断退出（fail-fast with reason 而非误判功能坏）。**Warning signs:** harness 日志 `批开始 guard 拒绝（reason=...）`。

### Pitfall 4: guard 副作用——TTS kill 与 POST /free 真的会执行
**What goes wrong:** h3_regen 批前 guard 五步固定序**无条件**跑（含 kill_tts 定向 SIGTERM + 2×POST /free，h3_regen.py:1030+ 实测）——cache-hit 二跑也会执行。当前 5110/5111 无监听（no-op 安全，本 session 实测）但若 TTS 服务器在跑会被杀。
**How to avoid:** harness/文档注明；e2e 跑前确认无 TTS 在跑（ss -tlnp | grep 511）。这也是 Pattern 1 推荐外层 mtime cache 的第二理由（cache 命中跳过整个 subprocess 即跳过 guard）。

### Pitfall 5: 中文+全角字符 work_dir 路径
**What goes wrong:** ep01 work_dir 名含全角括号/句号（`虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。`）——bash 直接引号引用易错、glob 排序即目录序。
**How to avoid:** harness 用 `WORK="$(ls -d output/*/ | head -1)"` 或 python glob 取路径；断言全部相对 work_dir 而非硬编码全路径。dataset/<video-stem>/ 同样带全角名——所有路径操作走 pathlib/os.path。

### Pitfall 6: byte-identical-absent 场景不能用 ep01 现态
**What goes wrong:** ep01 已有 roundtrip.json（19 镜冻结）——ComfyUI-down 场景跑 ep01 仍会挂载 data.roundtrip（文件在），"absent" 语义测不到。
**How to avoid:** down 场景在 harness 自造的 fixture work_dir（mkdtemp + 最小 shots.json/prompts.json，mirror Phase 12 smoke 的 `/tmp/p12-smoke-$$` 形态）跑，断言 5 个数据 JSON + asset.json md5 前后等值 + roundtrip.json 缺席 + warnings 含 `comfyui_unreachable`。

### Pitfall 7: verdict 全冻结时 judge apply 的 e2e 预期
**What goes wrong:** 误以为 e2e 会产出新 verdict——ep01 19 镜全冻结（judge frozen-skip），apply-verdict 输出 `applied=0 frozen=19`。断言写错就误判失败。
**How to avoid:** e2e 断言集按"缓存续跑"语义写：`applied=0 frozen=19` + sidecar sha256 前后不变（幂等证明，顺带覆盖 SC5 场景 2 的一半）。dataset 断言用**现存**分布：accepted=4（shot 10/61/75/84，21-03-SUMMARY:191 实证）/ rejected=15。

### Pitfall 8: f-string 模板内字面 `{}`
**What goes wrong:** gen_roundtrip_review.py 大 JS 块里 CSS/JS 字面花括号忘 `{{ }}` 转义 → ValueError: unexpected '{' in field name。
**How to avoid:** mirror gen_registry_review.py 全文先例（JS 函数体全 `{{`）；UI-SPEC 生成器形态契约已明文此惯例。

## Code Examples

### XSS 三层 hardening（PRESENT-01 / SC3 —— 从先例逐字提取）

```python
# 第 1 层：Python _esc() —— 必须内联进 gen_roundtrip_review.py（html/ namespace package 禁跨文件 import）
# Source: html/gen_registry_review.py:79-91（gen_timeline_html.py:24 同款）
def _esc(s):
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;"))   # & 先转，防双重转义；str() 兜底非字符串

# 第 2 层：JSON-in-<script> bootstrap 防 </script> 破出
# Source: html/gen_registry_review.py:318
draft_json = json.dumps(draft, ensure_ascii=False).replace("</", "<\\/")

# 第 3 层：JS 侧动态更新一律 textContent，禁止 innerHTML 拼模型文本
# Source: gen_timeline_html.py:329-330（JS _esc 镜像 + textContent 惯例）
```
SC3 强制清单（UI-SPEC XSS 节逐字）：`judge.reason`、`attribution`（enum 也转）、`verdict.decision/source`、`status.error`、`midframe_sim.model`、`engine_name/engine_version/prompt_version`、`prompt_text` + 全部 facets、`character_refs/prop_refs`、`asset_name`；数字先 `str()`。schema maxLength 2000 已 bound（roundtrip.schema.json status.error/judge.reason，T-18-02）。

### SC3 注入测试形态（新建，无先例文件——grep 实证 tests/ 零 XSS 测试）

```python
# tests/test_roundtrip_review.py（骨架）—— 三 payload × reason + attribution 邻位
PAYLOADS = [
    "<script>alert(1)</script>",
    '" onerror="alert(1)" x="',          # 属性破出型（onerror=）
    "PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",  # base64（须以纯文本呈现，不被任何 decode 路径执行）
]
def test_xss_injection_not_executed(tmp_path):
    sidecar = make_fixture(reason=payload, attribution=...)   # schema-valid fixture（maxLength 内）
    run gen_roundtrip_review.main([...])                       # subprocess 或 importlib 直调
    html = out.read_text()
    assert "<script>alert(1)</script>" not in html             # 原文不存活
    assert "&lt;script&gt;" in html                            # 转义态在场
    assert 'onerror="' not in html.replace("onerror=&quot;", "")  # 属性注入不存活
```

### 汇总 grep 锚（harness 断言用，全部实测在场）

| 锚 | 来源 | 场景 |
|----|------|------|
| `[roundtrip] ComfyUI 不可达（status=0）—— graceful-degrade 退出` | h3_regen.py:1238 | down-degrade |
| `"code": "comfyui_unreachable"` | h3_regen.py:1235-1236 → warnings.json | down-degrade |
| `[roundtrip] 批开始 free=` + `< 22528MiB` | h3_regen.py:1094 | VRAM 拒提交 |
| `[roundtrip] 批开始 guard 拒绝（reason=` | h3_regen.py:1304 | VRAM 拒提交 |
| `[roundtrip] 完成：rendered=N cache-hit=N failed=N sampled=N skipped=N` | h3_regen.py:1434 | cache-hit 续跑（cache-hit=2 rendered=0）/ 抽样（sampled=2） |
| `[roundtrip] 全部 cache 命中（hit=N miss=0）—— 零模型加载` | scorer.py:593 附近 | cache-hit 续跑 |
| `[roundtrip] verdict 应用完成：applied=0 frozen=19 skipped=0 accepted=0 rejected=0（τ_sim=0.9670）` | judge.py:718-721 | e2e（全冻结态） |
| `[roundtrip] --sample-shots 2: 2/93 镜入样（均匀间隔，全镜列表上做）` | h3_regen.py:1279-1280 | 抽样模式 |

## State of the Art

内部代码库无外部 fast-moving 依赖。repo 内"旧→新"演进对照（对本 phase 有影响的）：

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| roundtrip 三件套是 standalone CLI（管线不生产 roundtrip 数据） | step_roundtrip 进管线（本 phase） | Phase 22 | run_pipeline --force 注释 :768-773 的"不清 roundtrip"理由之一失效——但 verdict 红线仍在，**清单仍不清**，理由改述为"verdict/scores 是冻结人工数据" |
| h3_regen --force 剥 regen 半边保 scores/verdict（WR-01） | 不变，pipeline --force 与模块 --force 两级各自语义 | Phase 20 | 透传时 pipeline --force **不**等于给 h3_regen 传 --force（route_cache rmtree 已达同效且更强）；不要双清 |
| asset schema 1.2 | 1.3（export_asset.py:59 SCHEMA_VERSION 单源，**勿复制字面量**） | Phase 18 | e2e 断言从单源读，勿硬编码字符串常量进测试（import 或 grep 锚均可） |

**Deprecated/outdated（防误用）：** ROADMAP SC1 的 `--comfyui-url` 拼写（实际 flag `--comfy-url`）；`[N/9]` 全部形态（重编号后 grep 应为 0 存活——可作 e2e 断言：`grep -c "/9\]" run_pipeline.py == 0`）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | dataset 目录根 = `<output-dir>/dataset/<video-stem>/`（两层解读） | Pattern 2 / Open Q1 | 若 Kai 意指 work_dir 内 `output/<video-stem>/dataset/`，导出路径与 e2e 断言全改（小时级）；需 planner/discretion 收口 |
| A2 | review HTML 在 cache-hit 路径仍补生成（纯 Python 无代价） | Pattern 1 | 若 planner 选择无条件跑全链 subprocess，e2e 仍绿（guard 副作用见 Pitfall 4），仅多秒级开销 + eye-wait 阻塞风险 |
| A3 | apply CLI 对"已 human 且同 decision"跳过（真 idempotent） | Pattern 5 | 若选择 decided_at 每次更新，重放非 byte-idempotent（registry 先例标准下略弱，但 schema 不违约） |
| A4 | 首尾帧优先直拷 route_cache/h3_regen/frames/ 现存文件、缺席才重提 | Pattern 6 | 若 route_cache 帧曾被清（--force 后未重渲），回落到重提路径——同一函数，字节等价，无正确性风险仅耗时 |
| A5 | scorer/judge 不透传 pipeline `--device`（保持模块自身默认） | Pattern 3 | 若 Kai 想统一设备控制，需加映射逻辑；现状默认已是精心设计的分卡 |

## Open Questions

1. **dataset 目录根的两层解读**
   - What we know: RT-05/CONTEXT 写 `dataset/<video-stem>/`；PROJECT.md locked decision #6 只说"独立目录（非 asset.json 内嵌）"。
   - What's unclear: dataset 根在 output/ 下还是 work_dir 内。
   - Recommendation: `--dataset-root` 默认 `<output-dir>/dataset`（跨视频集合心智 + 消费端一个根取全量）。plan 里作 discretion 决策显式记录即可，不必回问。

2. **roundtrip-edits 要不要 schema —— 推荐要（已在 Pattern 5 给理由）**
   - registry/speaker 双先例都建了；T-07-02 把"apply 前 Validator 预校验"列为强制；UI-SPEC 也已把 schema 文件路径写进契约（`spec/schemas/roundtrip-edits.schema.json`）。执行即可，非真开放问题。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| ComfyUI API | h3_regen regen / judge /free | ✓（:8188 实测 200） | 0.30.0 build（Pitfall 3 注释记载） | down 场景反而是测试目标；正常 e2e 需它 up |
| GPU1 3090 free VRAM ≥22528MiB | h3_regen 批前 guard | ✓（free=22990MiB，**margin ~460MiB**） | — | 无——不足即 guard 拒绝（属降级路径）；e2e 前探测（Pitfall 3） |
| GPU0 3060Ti | scorer（cuda:0） | ✓（8GB 卡，free~5GB） | — | scorer 自带 cpu 降级 |
| TTS :5110/:5111 | guard kill_tts | 未监听（no-op 安全） | — | — |
| ffmpeg/ffprobe | 帧提取/时长探测 | ✓（管线全程依赖） | 6.1.1 | — |
| pytest | wiring/单测 | ✓ | 9.0.3 | — |
| python3 | 全部 | ✓ | 3.12.3 /usr/bin/python3 | — |
| scripts/serve.py :8765 | review 面板 video 播放 | 未跑（操作员手动起） | — | 面板生成不依赖它；只有人看时需要 |

**Missing dependencies with no fallback:** 无（e2e 硬依赖 ComfyUI + GPU margin，均实测在场；VRAM margin 薄是风险不是缺失）。
**Missing dependencies with fallback:** serve.py 未运行——按设计 operator 手动起，不阻塞自动化。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3（无 pytest.ini——测试文件自足；bash harness 独立跑） |
| Config file | none（repo 无 pytest 配置，沿用现状） |
| Quick run command | `python3 -m pytest tests/ -x -q`（<30s：全为静态断言/合成 fixture 单测） |
| Full suite command | `python3 -m pytest tests/ -q && bash tests/test_phase22_e2e.sh`（harness 内部单场景 `timeout` 包裹，mirror Phase 12/14 惯例） |

### Phase Requirements → Test Map（SC → 可检验断言）

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 / SC1 | banner 重编号：`grep -c "/9\]" run_pipeline.py == 0`；`[9/10] roundtrip` 与 `[10/10] ShotTimelineAsset export` 在场；顺序 roundtrip < export | unit（静态 grep，mirror vision_wiring 形态） | `python3 -m pytest tests/test_pipeline_roundtrip_wiring.py -x` | ❌ Wave 0 |
| PIPE-01 / SC1 | flags 透传：--skip-roundtrip 短路 / --comfy-url/--sample-shots/--regen-resolution/--max-shot-sec/--tau-sim 在 h3_regen/judge argv 构造内（index 顺序断言，mirror test_pipeline_vision_seq_wiring.py:74-93） | unit（静态源码断言） | 同上 | ❌ Wave 0 |
| PIPE-01 / SC1 | 既有 wiring 测试随重编号更新后仍绿 | unit | `python3 -m pytest tests/test_pipeline_vision_wiring.py tests/test_pipeline_vision_seq_wiring.py -x` | ✅（需改） |
| PIPE-01 / SC1 | step_export 条件性 roundtrip input（Pattern 4 形态断言） | unit（静态） | 同上 wiring 文件 | ❌ Wave 0 |
| SC1 e2e | ep01 --sample-shots 2 一次跑出齐产物：roundtrip.json 存在 + roundtrip/shot_001|047_regen.mp4 + `asset.json#schema_version=="1.3"` + `data.roundtrip=={path,accepted_count:4,rejected_count:15}` + dataset 目录（manifest + 4 shot dir + accepted.txt 4 行 + rejected.txt 15 行）+ roundtrip_review.html | e2e（bash harness 内 live 场景或独立段落；ep01 work_dir 经 glob 取全角名路径） | `bash tests/test_phase22_e2e.sh`（live 段） | ❌ Wave 0 |
| PRESENT-01 / SC2 | 面板生成：正常/空 sidecar/regen-failed 降级/未打分 四态 HTML 可产（UI-SPEC States 表）+ exportEdits payload 形状（accept/reject 升序、维持 auto 不进） | unit（importlib 直调 gen + 断言 HTML 子串/结构） | `python3 -m pytest tests/test_roundtrip_review.py -x` | ❌ Wave 0 |
| PRESENT-01 / SC3 | XSS 三注入 payload（`<script>` / `onerror=` / base64）注入 reason + attribution 邻位 → 渲染后原文不存活、转义态在场、无属性注入存活 | unit | 同上 | ❌ Wave 0 |
| PRESENT-01 / SC2 | apply CLI：schema 预校验拒坏 edits、confirmed-only 写 verdict{source:"human",decided_at}、human 同向重放 idempotent（A3 守卫）、审计行 `[roundtrip-apply] shot_NNN auto→human/accepted` 在场 | unit（tmp sidecar fixture） | `python3 -m pytest tests/test_roundtrip_apply_edits.py -x` | ❌ Wave 0 |
| RT-05 / SC4 | dataset 导出：4 shot dir（shot_010/061/075/084）各含 first_frame.jpg+last_frame.jpg+prompt.json（自含字段集断言：prompt_text+六 facet+refs+scores+attribution+engine_version+vch）+ manifest（τ=0.9670/引擎版本/rejected 分桶 faithful_below_tau=6/diverged=9）+ rejected.txt 15 行可 grep | unit（合成 fixture work_dir）+ e2e（live ep01 段） | `python3 -m pytest tests/test_export_dataset.py -x`；`bash tests/test_phase22_e2e.sh` | ❌ Wave 0 |
| RT-05 / SC4 | 消费端独立性：dataset 目录内无任何对 asset.json/roundtrip/ 的引用（grep 断言 manifest+prompt.json 无 `"asset.json"`/`roundtrip/` 路径依赖——首尾帧为拷贝非 symlink） | unit | 同上 | ❌ Wave 0 |
| PIPE-02 / SC5 场景1 | ComfyUI down（--comfy-url http://127.0.0.1:1）：fixture work_dir 上 5 数据 JSON + asset.json md5 前后等值 + roundtrip.json 缺席 + warnings `comfyui_unreachable` + `[roundtrip]` 降级日志 | e2e（bash，mkdtemp fixture，mirror Phase 12 smoke :36-56 形态） | `bash tests/test_phase22_e2e.sh` 场景 1 | ❌ Wave 0 |
| PIPE-02 / SC5 场景2 | cache-hit 断点续跑：ep01 二跑 `cache-hit=2 rendered=0` + scorer `全部 cache 命中` + judge `applied=0 frozen=19` + sidecar sha256 前后不变 + wall 对比（二跑 roundtrip 段 < 首跑 1/5 量级或绝对秒数上界断言） | e2e（live） | 同上 场景 2 | ❌ Wave 0 |
| PIPE-02 / SC5 场景3 | 抽样模式：--sample-shots 2 → `2/93 镜入样` 日志 + 本轮 regen 产物仅样内（sidecar 19 镜 READ-merge 不丢存量） | e2e（live，同场景 2 复用产物） | 同上 场景 3 | ❌ Wave 0 |
| PIPE-02 / SC5 场景4 | VRAM-guard 拒提交：ComfyUI up + `--gpu-index 0`（3060Ti 8GB 结构性 < 22GB）→ `批开始 free=... < 22528MiB` + guard 拒绝日志 + warnings `vram_insufficient` + cache 保留（二跑可续） | e2e（live，前置 GPU 探测） | 同上 场景 4 | ❌ Wave 0 |
| RT-01 红线复验 | byte-identical-absent pipeline 级：场景 1 的 md5 等值断言即 pipeline 级复验（roundtrip 缺席 → v1.2 数据文件零字节变化） | e2e（并入场景 1） | 同上 | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -q && bash tests/test_phase22_e2e.sh`（harness 含 live 场景需 ComfyUI/GPU 前置探测，失败输出诊断）
- **Phase gate:** 全绿后 `/gsd:verify-work`；SC1 live 证明 = harness live 段一次全绿跑

### Wave 0 Gaps
- [ ] `tests/test_pipeline_roundtrip_wiring.py` —— SC1 静态断言（banner/flags/顺序/条件 input）
- [ ] `tests/test_pipeline_vision_wiring.py` + `tests/test_pipeline_vision_seq_wiring.py` —— 重编号同步改（regex `\[\d+/10\]` + 子串断言）
- [ ] `tests/test_roundtrip_review.py` —— SC2 四态 + SC3 三注入
- [ ] `tests/test_roundtrip_apply_edits.py` —— apply CLI confirmed-only/idempotent/schema 拒坏
- [ ] `tests/test_export_dataset.py` —— RT-05 目录/字段/分桶/独立性
- [ ] `tests/fixtures/roundtrip_sample.json` —— schema-valid sidecar fixture（含注入 payload 与四态变体）
- [ ] `tests/test_phase22_e2e.sh` —— 4 场景 harness（含 GPU/ComfyUI 前置探测函数）

*(test framework 本身在场，无框架安装 gap)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | offline 静态面板 + 本地 CLI，无认证面 |
| V3 Session Management | no | 无 session |
| V4 Access Control | no | 单机操作员工具 |
| V5 Input Validation | yes | roundtrip-edits.schema.json + Draft202012Validator apply 前预校验（T-07-02 mirror）；roundtrip.json 读取端 `_iter_sidecar_errors` defensive 校验；shot_id integer（schema minimum 1）天然拒 path-traversal |
| V6 Cryptography | no | 无新密码学（vch 是 cache-invalidation hash 非安全 hash，schema 注释明文） |

### Known Threat Patterns for {stdlib-Python 生成 HTML + edits 文件管道}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via 模型产出文本（judge.reason/status.error/prompt_text 流入 HTML） | Tampering/Elevation | `_esc()` 5 字符全动态字符串 + JSON bootstrap `</`→`<\/` + JS textContent-only（三层，SC3 测试集锁定）；schema maxLength 2000 bound（T-18-02） |
| edits 文件注入（伪造 accept_overrides 篡改 verdict） | Tampering | schema 预校验（integer array、additionalProperties:false、free-form 结构拒收）+ confirmed-only CLI 显式运行 + idempotent 重放安全 |
| path traversal via regen.path / 导出路径 | Tampering | regen.path schema pattern 防 `..`（roundtrip.schema.json:38）；dataset 路径全部由 integer shot_id 格式化构造，无用户字符串进路径 |
| subprocess 注入 | Tampering | 全 list-form argv（T-14-02 惯例），新 step 编排沿用；prompt_text 绝不进 argv（h3_regen build_workflow 注释 :473 先例） |
| `--force` 误删人工数据 | Destruction | 显式清单永不 glob/rmtree 父级（T-14-01）；roundtrip.json/roundtrip/ 永不进 pipeline --force（WR-01 红线） |

## Sources

### Primary (HIGH confidence —— 全部本 session 逐行实证)
- run_pipeline.py（全文 965 行 Read：29 处 banner、:573-580 export inputs、:777-793 force 清单、:926-953 canvas post-step 形态、:471-474 条件 input 先例）
- analysis/roundtrip/h3_regen.py（:142 COMFY_URL_DEFAULT、:153 STEP_TAG、:207-215 guard 常量、:387-417 extract_endpoint_frames、:99-103 importlib 先例〔judge.py〕、:1184-1310 CLI+gate+guard 序、:1434 汇总输出）
- analysis/roundtrip/scorer.py（:505-516 CLI、cache-hit 零加载路径）+ judge.py（:503-567 apply_verdict 冻结语义、:692-721 CLI τ 门、:80-95 sys.path/engine_clients）
- scripts/export_asset.py（:59 SCHEMA_VERSION "1.3"、:375-404 条件挂载）
- spec/schemas/roundtrip.schema.json（全文：regen 4-tuple/status/scores/verdict 字段与 maxLength 2000）+ registry-edits.schema.json + speaker-edits.schema.json（edits 惯例）
- html/gen_registry_review.py（:79-91 _esc、:318 JSON bootstrap、:642-669 exportEdits、:695-701 CLI）+ gen_timeline_html.py（:24 _esc docstring 惯例）
- registry/apply_edits.py（:1-35 独立 CLI + 硬门语义）
- tests/test_pipeline_vision_wiring.py / test_pipeline_vision_seq_wiring.py（:98-107 grep 锁形态）
- tests/run_audio_analysis_smoke.sh（bash harness 形态）+ .planning/milestones/v1.2-phases/14-pipeline-integration/14-VERIFICATION.md（v1.2 Phase 14 harness 模式）
- .planning/PROJECT.md Key Decisions（τ_sim=0.9670 Kai 裁决行）+ 21-VERIFICATION.md / 21-03-SUMMARY.md（accepted=4: shot 10/61/75/84 / rejected=15 分桶）
- ep01 运行时实测（output/<全角名>/：roundtrip.json 19 镜冻结 4/15、route_cache 三 cache 目录全满、uniform_sample(93,2)=[1,47] 双命中、asset.json 1.2 无 roundtrip 挂载、GPU/ComfyUI/TTS/serve 探测）

### Secondary (MEDIUM confidence)
- 无

### Tertiary (LOW confidence)
- 无

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH —— 零新依赖，全部既有模块本 session 实证
- Architecture: HIGH —— 插入点/波及面/cache 修补全部行号级实证；唯 dataset 根目录两义（A1）标 discretion
- Pitfalls: HIGH —— 8 条全部来自代码行实证或运行时探测（VRAM margin/TTS 端口/中文路径为 live 探测）

**Research date:** 2026-08-20
**Valid until:** 2026-09-19（内部代码库稳定；外部无依赖 drift 风险——ComfyUI/GPU 状态是易变项，e2e 前置探测已内置）
