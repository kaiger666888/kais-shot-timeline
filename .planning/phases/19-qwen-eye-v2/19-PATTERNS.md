# Phase 19: qwen-eye v2 看片段 - Pattern Map

**Mapped:** 2026-08-19
**Files analyzed:** 8（3 modify + 5 new）
**Analogs found:** 8 / 8（6 exact + 2 role-match；无裸奔文件）

> 所有行号基于 2026-08-19 工作区实读（repo HEAD 含 d16ee6d local_vision 落地）。
> 上游真源 `/home/kai/workspace/kais-hermes-skills/plugins/kais_aigc/qwen_eye.py` 行号 @ commit c3949404。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `analysis/vision_seq_facets.py` (NEW) | service（CLI stage 模块） | batch（per-shot 循环）+ request-response（引擎调用）+ file-I/O（JSON 读写） | `analysis/local_vision_facets.py` | exact |
| `analysis/engine_clients/qwen_eye_client.py` (MODIFY: +`observe_pair`/`ask_text`) | service（引擎客户端） | request-response | 上游 `kais-hermes-skills/.../qwen_eye.py:268-284` `observe()` + 本文件 `observe_single` (:267-279) | exact |
| `run_pipeline.py` (MODIFY: pre-step 5.6 挂载 + 双 flag) | route（orchestrator wiring） | batch 编排 | `run_pipeline.py:801-822`（5.5 块）+ :684-690（flag 惯例） | exact |
| `tests/test_vision_seq_facets.py` (NEW) | test | unit（FakeEngine 离线） | `tests/test_local_vision_facets.py` | exact |
| `tests/test_pipeline_vision_seq_wiring.py` (NEW) | test | unit（静态源码断言 + argparse spy） | `tests/test_pipeline_vision_wiring.py` | exact |
| `tests/test_qwen_eye_client.py` (MODIFY: +pair/text shape 测试) | test | unit（monkeypatch `_call_llm`） | 本文件 `test_observe_single_request_shape` (:142-163) | exact |
| `.planning/research/vision-seq-spike-report.md` (NEW) | docs（spike 结论落档） | report（人工盲评 + 证据摘录） | `.planning/milestones/v1.2-research/audio-spike-report.md` | exact（结构级） |
| `spike/vision_seq/`（NEW：sandbox 脚手架 = README + 构建/运行脚本 + results/） | utility（THROWAWAY spike） | file-I/O（副本构建）+ request-response（引擎批量） | `spike/audio/`（README + run_*.py + results/ + tests/ 布局） | role-match（布局同、领域异） |

**注意**：CONTEXT/RESEARCH 均确认——`analysis/local_vision_facets.py` 本体 **零改动**（v1 零回归），不在 modify 清单里。

---

## Pattern Assignments

### `analysis/vision_seq_facets.py` (service, batch + request-response + file-I/O)

**Analog:** `analysis/local_vision_facets.py`（373 行全文已验证；v2 = mirror 换 facet（action/camera）+ 换帧策略（≤8 均匀 + 相邻对）+ 加 ear 注入与合并层）

**A. 文件头/module docstring 惯例**（analog lines 1-49）——全中文、必含：背景、facet 边界、cache 设计、graceful-degrade 契约、引擎生命周期、输出清单、CLI 用法。v2 docstring 需额外写进 RESEARCH Pitfall 5 的时序后果（「ear 激活发生在 audio_semantic.json 就位后的第二次管线跑」）。

**B. imports + sys.path 注入**（analog lines 50-65）——stage 脚本独占 engine_clients 的唯一例外写法，v2 必须复制：

```python
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# 引擎客户端是同仓 sibling 包模块（engine_clients/ 无 __init__.py —— 直接
# sys.path 注入其目录 import，mirror 上游「stage 脚本互相不 import，例外：
# 本文件独占拥有这个复制来的客户端」约定）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_clients.qwen_eye_client import (  # noqa: E402
    ENGINE_NAME,
    ENGINE_VERSION,
    QwenEye,
)
```

**C. 模块级常量块**（analog lines 67-96）——v2 版本对照（保留左列语义、换右列值）：

| v1 常量 (analog) | v2 值 |
|---|---|
| `CACHE_NAME = "local_vision"` (:70) | `"vision_seq"`（独立目录 `route_cache/vision_seq/`） |
| `PROMPT_VERSION = "local-vision-v1"` (:71) | `"vision-seq-v1"` |
| `MAX_FRAMES_PER_SHOT = 3` (:78) | **新增** `MAX_SEQ_FRAMES_PER_SHOT = 8`（不动 v1 的 3——CONTEXT 锁定） |
| `STEP_TAG = "[vision]"` (:81) | `"[vision-seq]"`（warnings 前缀区分） |
| `SCENE_PROMPT`/`SUBJECT_PROMPT` (:83-92) | `ACTION_PROMPT`/`CAMERA_PAIR_PROMPT`（分开问——CONTEXT 锁定；文案 mirror v1 风格：一句中文指令 + 「只输出…不要…」约束） |

Prompt 文案风格样例（analog lines 83-86，照此结构写 action/camera 版）：

```python
SCENE_PROMPT = (
    "请用一句简洁中文描述这一帧的画面场景与环境（地点、空间、背景元素、"
    "时代/世界观线索）。只输出场景描述本身，不要描述角色，不要编号或前缀。"
)
```

**D. video_content_hash**（analog lines 99-110）——原样复制，勿改（首尾 1MB + size 的毫秒级 hash）。

**E. 帧采样**（analog `select_frames` lines 113-137 + `_frame_number` 140-146）——v2 换均匀采样：保留 glob `f[0-9]*.jpg` + `"_ds" not in p.stem` 过滤（Pitfall 8）+ 时窗 lo/hi 计算，只把首/中/尾 picks 换成均匀索引：

```python
# v1 的 picks 段（analog lines 132-137）—— v2 替换为（RESEARCH Pattern 6 参考实现）：
    if len(window) <= max_frames:
        return window
    idx = {round(i * (len(window) - 1) / (max_frames - 1)) for i in range(max_frames)}
    return [window[i] for i in sorted(idx)]
```

**F. main() 总体骨架**（analog lines 181-300，顺序照抄）：
1. argparse（每个 add_argument 带中文 help，analog :182-199）
2. 读 prompts.json（缺席 → `sys.exit`，analog :210-212）/ shots.json / `video_content_hash`
3. cache 目录 + warnings sidecar READ（analog :219-224）
4. 引擎生命周期 try/finally（analog :226-271，见 Shared Pattern 1）
5. per-shot 循环 + 只填空缺守卫（analog :254-256）

```python
                for facet in facets:
                    if p.get(facet):
                        continue   # 已有值（route/人工产物）—— 不覆盖
```
v2 对 action/camera 两键逐键同款判断（已有值永不覆盖、不做「更短就替换」——CONTEXT 锁定）。

6. 每 10 镜进度行（analog :268-269：`if (sid % 10) == 0: print(f"[vision-seq] {sid}/{len(prompts)} shots processed")`）
7. 写前 Draft202012Validator 自校验（analog :273-282）
8. 原子写 tmp + os.replace（analog :284-288）
9. warnings sidecar strip-本-step-前缀-再-merge（analog :290-295，`STEP_TAG` 换 `[vision-seq]`）

**G. per-shot cache**（analog `_facet_cached` :303-322 + `_write_facet_cache` :325-347）——read-merge-write 同镜多键共享一个 shot_XXX.json。v2 变体（RESEARCH Pattern 2 关键设计）：`answers` dict 存**原始逐帧/逐对答案**（`action_frame_1..8` + `camera_pair_1..7`），合并产物另存 `merged_B` 等键；4-tuple `_cache_key`（analog :170-178）加第 5 维 ear：

```python
def _cache_key(vch: str, ear: bool) -> dict:
    return {
        "video_content_hash": vch,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ear": ear,                     # CONTEXT 锁定：ear on/off 进 cache key
    }
```

**H. 引擎调用层**（analog `_ask_facet` :350-369）——v1 是「逐帧 observe_single → 取最长」；v2 改为：action = 8 次 `observe_single`（每帧独立答案入 cache）；camera = 7 次 `observe_pair`；合并（A=纯归约 / B=`ask_text`）在写出时做。异常处理照抄 analog :360-363（`except (RuntimeError, OSError)` → per-shot warning + continue，不阻塞其余镜）。

**I. `_clean_answer`**（analog :149-152）——原样复制。

**J. CLI args**——v2 需在 v1 参数集（--shots/--frames-dir/--work-dir/--output/--video）之上加：`--audio-semantic`（ear 输入，文件存在性自判、缺席=自动无 ear 零 warning）、`--no-ear`（`action="store_true"`，CONTEXT：存在时默认开、此 flag 关）。flag 命名 kebab-case + 中文 help。

---

### `analysis/engine_clients/qwen_eye_client.py` (MODIFY: +observe_pair / +ask_text)

**Analog 1（消息 shape 真源）:** 上游 `kais-hermes-skills/plugins/kais_aigc/qwen_eye.py:268-284`（已实读验证）——多图 = 每图一条 user 消息，question 拼进最后一条图像消息的 text part：

```python
    def observe(self, image_paths: list[Path]) -> str:
        n = len(image_paths)
        messages: list[dict] = []
        for i, path in enumerate(image_paths):
            messages.append({"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + self._b64(path)}},
                {"type": "text", "text": f"(帧{i + 1}/{n})"},
            ]})
        return self._call_llm(messages, max_tokens=2000)
```

**Analog 2（同文件锚点）:** 仓内 `observe_single`（:267-279）——新方法紧随其后插入，风格/签名对齐：

```python
    def observe_single(self, image_path: Path, question: str,
                       max_tokens: int = 2000) -> str:
        messages = [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + self._b64(image_path)}},
            {"type": "text", "text": question},
        ]}]
        return self._call_llm(messages, max_tokens=max_tokens)
```

**v2 新增方法形态**（RESEARCH Pattern 3 已给出成品，直接用；两图 = 恰好两条 user 消息，规避 llama.cpp 多图丢弃 bug——单条 user 带 N 图只算 ceil(N/2) 张）：

```python
    def observe_pair(self, img_a: Path, img_b: Path, question: str,
                     max_tokens: int = 2000) -> str:
        messages = [
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + self._b64(img_a)}},
                {"type": "text", "text": "(第1帧/前一帧)"}]},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + self._b64(img_b)}},
                {"type": "text", "text": "(第2帧/当前帧)" + question}]},
        ]
        return self._call_llm(messages, max_tokens=max_tokens)

    def ask_text(self, question: str, max_tokens: int = 2000) -> str:
        """纯文本调用（策略 B 合并用）—— 无图 = 豁免多图丢弃 bug。"""
        return self._call_llm(
            [{"role": "user", "content": [{"type": "text", "text": question}]}],
            max_tokens=max_tokens)
```

**必改的头部注释**（:9-11 现文「本文件相对上游的裁剪：去掉 logging（…）、去掉 observe() 多图入口（local_vision_facets 只用 observe_single 单图问答）」）——v2 落地后此段过期，需更新为「裁剪 logging；本地扩展 observe_pair/ask_text（mirror 上游 observe() 多 user 消息 shape，question 版）」，并同步更新 docstring 用法示例（:36-44）。

**禁改区**：`_call_llm`（:234-261，`enable_thinking:false` 恒传在 :243——新方法必须走它，勿直接 `_http_json`）、生命周期（:159-231）、`ENGINE_NAME`/`ENGINE_VERSION`（:58-62）。Pitfall 2 警告：`vision_seq_facets.py` 里不得直调 `engine._call_llm` 私有 API。

---

### `run_pipeline.py` (MODIFY: pre-step 5.6 挂载)

**Analog:** 5.5 local_vision pre-step 块（:801-822）+ 双 flag 惯例（:684-690）。插入点：`:822`（5.5 块 `run_step(cmd_vision, ...)` 行）与 `:824`（`# 6. 跨镜 re-id` 注释）之间。

**flag 惯例**（analog :684-690 原文，dest+store_false 双 flag；v2 加在 ~:690 之后）：

```python
    ap.add_argument("--local-vision", dest="local_vision",
                    action="store_true", default=True,
                    help="启用本地 qwen-eye VL 填充 prompts.json 的 scene/subject "
                         "facets（默认启用；step 5 之后的无编号 pre-step）")
    ap.add_argument("--no-local-vision", dest="local_vision",
                    action="store_false",
                    help="禁用本地 VL facet 填充（scene/subject 保持 step 5 产出的空值）")
```

**pre-step 块惯例**（analog :801-822 原文——条件四连 + subprocess 按路径 + plain-label banner）：

```python
    # 5.5 本地 VL facet 填充（qwen-eye pre-step —— 无编号，mirror attach_refs
    # 先例 at step_timeline；不 bump step counter，保持 grep count 不变）。
    # ...（注释块）
    if (args.local_vision and not args.skip_semantic
            and os.path.exists(prompts_json)
            and os.path.isdir(frames_dir)):
        cmd_vision = [sys.executable,
                      str(HERE / "analysis" / "local_vision_facets.py"),
                      "--shots", shots,
                      "--frames-dir", frames_dir,
                      "--work-dir", work_dir,
                      "--output", prompts_json]
        if args.no_subject:
            cmd_vision += ["--no-subject"]
        cmd_vision += ["--video", video]
        # Banner label 故意不带 numeric 前缀 —— 与 attach_refs 同款 plain label。
        run_step(cmd_vision, "local vision facets (qwen-eye pre-step)")
```

v2 变体要点：
- 条件：`args.vision_seq and not args.skip_semantic and os.path.exists(prompts_json) and os.path.isdir(frames_dir)`
- 命令尾部追加 `--audio-semantic", audio_semantic_json`（该变量 :736 已定义；存在性由子模块自判——RESEARCH Pattern 4 明示）
- banner label：`"vision seq facets (qwen-eye v2 pre-step)"` —— **plain label，绝不带 `[5.6/9]`**（`tests/test_pipeline_vision_wiring.py:104` 的 `assert "[5.5/9]" not in src` 同款 grep 锁；v2 wiring 测试要加 `"[5.6/9]" not in src`）
- `--force` 清理（:741-773）：`route_cache_dir`（:755、:767）已整目录 rmtree，天然覆盖新 `route_cache/vision_seq/` 子目录——**无需**改 force 清单（mirror :750 注释「NOT 父级 route_cache」的反向保护逻辑）

---

### `tests/test_vision_seq_facets.py` (NEW, unit)

**Analog:** `tests/test_local_vision_facets.py`（312 行全文已验证）——v2 复制全套骨架，覆盖矩阵换成 RESEARCH「Validation Architecture → Phase Requirements → Test Map」列出的项（均匀采样 ≤8/<8 全取/_ds 忽略、只填空缺、cache 命中+stale miss、A/baseline 纯归约确定性、degrade、schema+原子写+sidecar merge、ear 三断言、无 audio 文件 byte-identical）。

**模块加载骨架**（analog :24-33）——importlib spec 加载 + engine_clients 临时 path：

```python
_spec = importlib.util.spec_from_file_location(
    "vision_seq_facets", ANALYSIS / "vision_seq_facets.py")
vsf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vsf)
```

**make_workdir 骨架**（analog :36-58）——v2 版：10 帧 frames_5fps + prompts.json 的 `action=""`/`camera=""`（而非 scene/subject）；sandbox 脚手架（见下节）同构。

**FakeEngine 骨架**（analog :61-77）——v2 需加 `observe_pair(self, img_a, img_b, question, max_tokens=2000)` 与 `ask_text(self, question, max_tokens=2000)` 两个计数方法（shape 与真客户端对齐）。

**run_main / patch_engine 骨架**（analog :80-99）——argv 注入 + `monkeypatch.setattr(lvf, "QwenEye", lambda: fake)` 原样 mirror（换成 vsf）。

**必 mirror 的 6 个测试**（analog 行号 = 直接对照改写）：
| v2 测试 | analog |
|---|---|
| cache 命中二跑零引擎调用 + `_cache_key` 4-tuple（+ear 维度）断言 | `test_cache_hit_second_run_zero_engine_calls` :128-146 |
| stale key miss 重拉 | `test_stale_cache_key_miss_refetches` :148-168 |
| 已有 action/camera 不被覆盖 | `test_existing_facet_not_overwritten` :171-179 |
| 引擎不可用 degrade（`[vision-seq]` warning + exit 0 + schema 合法） | `test_engine_unavailable_degrades` :184-205 |
| try/finally 生命周期（爆炸引擎也 stop） | `test_lifecycle_try_finally_stops_engine` :208-228 |
| sidecar READ-merge-write（他 step 条目保留、不 self-accumulate） | `test_warnings_sidecar_preserves_other_steps` :231-253 |
| 缺 prompts.json fail-loud | `test_missing_prompts_fails_loud` :280-291 |
| 采样函数单元（含 `_ds` 忽略） | `test_select_frames_first_mid_last` :296-311（v2 断言均匀 ≤8 语义） |

ear 专项（SC3 单元级，analog 无、按 RESEARCH Code Examples :368-386）：有 audio → 提问含音频子串；`--no-ear`/无文件 → 不含；白名单外字段（words/reproduction/spk_id）grep 负测试。

---

### `tests/test_pipeline_vision_seq_wiring.py` (NEW, unit: 静态 + argparse spy)

**Analog:** `tests/test_pipeline_vision_wiring.py`（106 行全文已验证）——四件套逐个 mirror：
1. `--help` subprocess 冒烟（analog :30-38）——断言 `--vision-seq`/`--no-vision-seq`/`--no-ear` 在 stdout
2. argparse spy（analog :41-78）——`_StopMain` 异常短路技巧；断言默认 `vision_seq is True`、`--no-vision-seq` → False
3. 静态顺序断言（analog :85-95）——`src.index("vision_seq_facets.py") < src.index("step_reid(video, work_dir")` 且 > 5.5 块位置（local_vision 之后）；banner 字符串 `'"vision seq facets (qwen-eye v2 pre-step)"' in src`
4. banner count 锁（analog :98-105）——**必须保留原有断言**并加 `assert "[5.6/9]" not in src`（`[5.5/9]` 断言在 v1 文件 :104 已存在，v2 文件同款）

---

### `tests/test_qwen_eye_client.py` (MODIFY: +2 个 shape 测试)

**Analog:** 本文件 `test_observe_single_request_shape`（:142-163）——monkeypatch `_call_llm` 捕获 messages 的写法原样复用：

```python
    captured = {}
    def fake_call_llm(self, messages, max_tokens):
        captured["messages"] = messages
        return "答"
    monkeypatch.setattr(QwenEye, "_call_llm", fake_call_llm)
```

v2 新增两个测试（mirror 该结构）：
- `test_observe_pair_request_shape`：`len(messages) == 2`；每条恰一个 `image_url` part + 一个 `text` part；question 子串只在第二条；第一条 text 含「前一帧」标记
- `test_ask_text_request_shape`：单条 user 消息、纯 `text` part、零 `image_url`；thinking 禁用已被 `test_call_llm_always_disables_thinking`（:166-178）覆盖，无需重复

---

### `.planning/research/vision-seq-spike-report.md` (NEW, spike 结论落档)

**Analog:** `.planning/milestones/v1.2-research/audio-spike-report.md`（254 行全文已验证；CONTEXT 明示 mirror 此先例）。结构映射（v1.2 章节 → v2 章节）：

| audio-spike-report 章节 (行号) | vision-seq 对应内容 |
|---|---|
| 头部元数据块 :1-10（Generated at / Repo HEAD / Fixture / Sample / fakes disclaimer） | 同款：ep01 fixture 全路径（目录名含全角括号——引用时用反引号包裹）、spike 镜清单（shot #91/#88/#66/#46/#70/#1，RESEARCH ep01 盘点表）、「盲评未做前标 DRAFT」 |
| Methodology :12-41 | 三策略定义（A 时序拼接 / B LLM 二次合并 / baseline 最长参照）+ ear on/off 双跑设计 + 「客观指标是辅助、人工盲评是主判据」反循环论证声明（Pitfall 4） |
| 分节 evidence（§1-3） | 每候选镜一节：三策略产物原文 + v1 现行值参照 + 客观指标（时序连接词密度/实体覆盖率/长度）+ ear diff 章节 |
| Recommendations 表 :194-210 | 合并策略锁定结论（A vs B + 理由 + 证据指针） |
| Reproducibility :212-245 | 重跑命令（spike 脚本 CLI）+ live prompts.json sha256 前后不变证明（SC1 负测试）+ cache 断点续跑说明 |

盲评材料形态（CONTEXT：Kai 人工并排盲评）：同镜三策略匿名编号（甲/乙/丙）并排 markdown 表格 + 帧图相对路径引用（RESEARCH Open Question 3 推荐 md 表格，repo `.html` 被 gitignore）。

---

### `spike/vision_seq/` (NEW, sandbox 脚手架)

**Analog:** `spike/audio/`（布局已验证：`README.md` + `common.py` + `run_*.py` × 3 + `aggregate_report.py` + `results/` + `tests/`）。

**README 头部惯例**（`spike/audio/README.md:1-8` 原文）——THROWAWAY 声明必须 mirror：

```markdown
# Phase 10 Audio Spike — THROWAWAY 脚本

> ⚠️ **THROWAWAY Phase 10 spike 脚本 —— 不是 pipeline 代码。**
>
> 不要在 `run_pipeline.py` 任何 `step_*` 函数里 `import` 本目录任何模块。
> 不要把它们接到 `analysis/*` 任何客户端。这些脚本**只**服务 Phase 10 的
> 4 个一次性 spike 任务，其最终交付物是
> `.planning/research/audio-spike-report.md`。脚本本身仅为可复现而提交。
```

v2 建议布局（RESEARCH Wave 0 Gaps）：`spike/vision_seq/` = README（同款 THROWAWAY banner，交付物指向 vision-seq-spike-report.md）+ sandbox 构建脚本（复制最小 work_dir：shots.json + prompts.json 副本 + frames_5fps symlink，抽样镜 action/camera 置 `""`，demo 级 audio_semantic.json 生成——dialogue.text 用 ep01 transcript 真实对白 + 手工 sfx）+ 双跑脚本（三策略 × ear on/off）+ `results/`。

**sandbox 构建的代码 analog**：`tests/test_local_vision_facets.py:make_workdir`（:36-58）——「shots.json + prompts.json + 假帧 jpg」三件套的最小构造写法直接放大到 sandbox 规模；demo audio_semantic.json 的结构参照 `spec/fixtures/v1.2/audio_semantic.json`（schema 最低要求仅 `schema_version` + `shots[].shot_id`，RESEARCH 已验证）。

**路径注意**（`spike/audio/README.md:71-72` 原文警告）：ep01 目录名含全角括号与中文冒号——用 `pathlib.Path`，不要走 shell 拼接。

---

## Shared Patterns

### 1. 引擎生命周期 try/finally（防 13.4GB 泄漏）
**Source:** `analysis/engine_clients/qwen_eye_client.py:159-231`（ensure_ready/stop_if_owned）+ `analysis/local_vision_facets.py:226-271`（使用侧）
**Apply to:** `vision_seq_facets.py` main()、spike 双跑脚本
```python
    engine = QwenEye()
    try:
        healthy, _owned = engine.ensure_ready()
        if not healthy:
            # graceful-degrade：目标 facet 保持原值，显式 warning，exit 0。
            ...
    finally:
        engine.stop_if_owned()   # 只停自己拉起的；预存在 lease 绝不动
```
勿重写 guard 链（health → VRAM 预检 → KAP allocate → kap-llm.sh fallback → 轮询+server.log Guard 2）——v1 已验收。

### 2. 4-tuple + PROMPT_VERSION cache key（幂等，SC4）
**Source:** `analysis/local_vision_facets.py:170-178`（key 构造）、:303-322（lookup：任一不匹配即 miss）、:325-347（read-merge-write 写入，同镜多键共享一个文件）
**Apply to:** `vision_seq_facets.py`（+ear 第 5 维）、spike 脚本复用同一 cache（断点续跑）
```python
    return {
        "video_content_hash": vch,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
```

### 3. graceful-degrade + warnings sidecar READ-merge-write
**Source:** `analysis/local_vision_facets.py:155-167`（_read_existing_warnings）、:233-238（degrade 分支）、:290-295（strip 本 step 前缀再 merge）
**Apply to:** `vision_seq_facets.py`（`[vision-seq]` 前缀；ear 无文件时的静默 degrade 是例外——零 warning，CONTEXT 锁定）
```python
    prior = [w for w in existing_warnings if not w.startswith(STEP_TAG)]
    with open(warnings_sidecar, "w", encoding="utf-8") as f:
        json.dump({"warnings": prior + warnings}, f, ensure_ascii=False, indent=2)
```

### 4. 写前 schema 自校验 + 原子写
**Source:** `analysis/local_vision_facets.py:273-288`
**Apply to:** `vision_seq_facets.py` 的 prompts.json 写出（沙箱跑同款）
```python
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(prompts_schema).iter_errors(prompts))
    if errors:
        sys.exit(f"prompts.json schema validation failed ...")
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    os.replace(tmp, args.output)
```

### 5. CLI / 日志 / 注释惯例（CLAUDE.md 全局约束）
**Apply to:** 全部新文件
- kebab-case flag、每个 add_argument 中文 help、布尔 `dest`+`store_true`/`store_false` 双 flag（analog `run_pipeline.py:684-690`）
- `print(f"[vision-seq] ...")` 括号前缀；无 logging 模块；长循环 10 进度计数（analog `local_vision_facets.py:268-269`）
- 注释/docstring 全中文；模块 docstring 必含 用途/算法步骤/输出 schema/CLI 用法
- JSON 写出恒 `ensure_ascii=False, indent=2`
- `subprocess.run(..., check=True)` fail-loud；缺输入 `sys.exit("...")`；无自定义异常类

### 6. anti-patterns（违反 = 静默劣化或测试破）
- 单条 user 消息带多图（llama.cpp 丢弃 bug）→ 对问必须两条 user（`qwen_eye_client.py:29-31`）
- 忘 `enable_thinking:false` → 必须走 `_call_llm`（:241-243）
- 并行调引擎（thread-unsafe by design，:33）
- banner 带 `[N/9]` 数字前缀 → `test_step_banner_count_unchanged` grep 锁破（`tests/test_pipeline_vision_wiring.py:98-105`）
- 停不属于自己的 server / 直调 `engine._call_llm` 私有 API
- 改 `analysis/local_vision_facets.py` 或 v1 的 `MAX_FRAMES_PER_SHOT`（零回归红线）

---

## No Analog Found

以下 v2 新逻辑无仓内直接实现，planner 用 RESEARCH.md 的参考实现（已给出成品代码）：

| 逻辑 | 归属文件 | RESEARCH 指针 |
|------|----------|---------------|
| ear prompt 组装（`build_audio_context` 白名单+截断） | `analysis/vision_seq_facets.py` | RESEARCH Code Examples「ear prompt 组装」节（:368-386 给了完整函数） |
| 合并策略 A（时序拼接纯归约）/ baseline（最长参照） | `analysis/vision_seq_facets.py` | RESEARCH Pattern 2 设计说明（cache 存原始证据、合并纯归约）；无代码先例——确定性纯函数，单测锁同输入同输出 |
| 均匀采样索引计算 | `analysis/vision_seq_facets.py` | RESEARCH Pattern 6 参考实现（`select_uniform_frames`）；时窗过滤段 mirror v1 `select_frames` |

## Metadata

**Analog search scope:** `analysis/`、`analysis/engine_clients/`、`tests/`、`run_pipeline.py`、`spike/audio/`、`.planning/milestones/v1.2-research/`、`spec/fixtures/v1.2/`、上游 `kais-hermes-skills/plugins/kais_aigc/qwen_eye.py`
**Files scanned:** 8 个 analog 全文实读（local_vision_facets.py 373 行 / qwen_eye_client.py 279 行 / run_pipeline.py :640-869 / 三个 test 文件全文 / audio-spike-report.md 254 行 / spike audio README / 上游 qwen_eye.py :255-299）
**Pattern extraction date:** 2026-08-19
