# Phase 21: Scorer + 阈值校准 - Pattern Map

**Mapped:** 2026-08-19
**Files analyzed:** 7 (5 new, 2 modify — 1 of which is prefer-no-change)
**Analogs found:** 6 / 7 (2 sub-patterns have no in-repo analog; research probe code is the sanctioned source)

> 行号锚点基于当前 HEAD（Phase 20 完成态）。CLAUDE.md 全局约定贯穿所有新文件：
> 中文 docstring/注释、`print(f"[stage] …")` 括号前缀日志、argparse kebab-case flag 带
> 中文 help、`json.dump(..., ensure_ascii=False, indent=2)`、无 OOP（除 QwenEye 客户端）、
> `main()` + `if __name__ == "__main__": sys.exit(main())`。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `analysis/roundtrip/scorer.py` | service（CLI 分析模块） | batch transform + file-I/O（ffmpeg 帧提取→SigLIP embed→cosine→cache/sidecar） | `analysis/roundtrip/h3_regen.py` | exact（同目录、同 cache/sidecar/warnings/guard 骨架；h3_regen docstring L7 明示 scorer 是其下游） |
| `analysis/roundtrip/judge.py` | service（引擎驱动 + verdict 应用器） | request-response（LLM engine calls）+ batch loop + sidecar merge | `analysis/vision_seq_facets.py`（生命周期）+ `analysis/engine_clients/qwen_eye_client.py`（调用面）+ `h3_regen.py`（verdict merge） | role-match（组合三源） |
| `tests/test_scorer.py` | test | unit + fakes（零网络零 GPU） | `tests/test_h3_regen.py` | exact |
| `tests/test_judge.py` | test | unit + fakes（零网络零 GPU） | `tests/test_h3_regen.py` | exact |
| `.planning/research/roundtrip-threshold-calibration.md` | doc（校准报告） | n/a | `.planning/research/vision-seq-spike-report.md` | exact（结构 precedent，CONTEXT 明示） |
| `.planning/PROJECT.md`（MODIFY） | doc（Key Decisions 追加 τ_sim 行） | n/a | 自身 Key Decisions 表 L138-142 行格式 | exact（append-only） |
| `analysis/roundtrip/h3_regen.py`（MODIFY — 条件性） | service | n/a | — | **prefer 不改**：研究裁决用 importlib 文件加载复用其 helper（见 Shared Patterns §Import 纪律），verdict 应用器放 judge.py 则零修改 |

运行时产物（非 plan 文件，但路径契约在此锁定）：`output/<ep01>/route_cache/scorer/shot_XXX.json`、`route_cache/judge/shot_XXX.json`、`roundtrip/_judge_grids/shot_XXX.jpg`（mirror 20-03 `roundtrip/_compare/` 先例）、`roundtrip.json` scores+verdict 半边。

## Pattern Assignments

### `analysis/roundtrip/scorer.py`（service, batch transform）

**Analog:** `analysis/roundtrip/h3_regen.py`（主）；`analysis/vision_seq_facets.py`（零修改短路 + 写前 schema 自校验）

**A. 模块骨架**（mirror h3_regen.py L1-119, L139-153）：
```python
#!/usr/bin/env python3
"""SigLIP 中段帧轨迹相似度打分（Phase 21 / SCORE-01）—— …
背景 / 算法步骤 / graceful-degrade 语义 / cache 惯例 / argv 用法 五段式 docstring
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path

STEP_TAG = "[roundtrip]"            # 与 h3_regen 同 tag（同 step 家族，warnings strip 语义共用）
SCHEMA_PATH = (Path(__file__).resolve().parent.parent.parent
               / "spec" / "schemas" / "roundtrip.schema.json")   # 三层 parent（off-by-one，见 §F）
```
注意：h3_regen 用同一个 `STEP_TAG = "[roundtrip]"`（L153）与 `_is_roundtrip_warning`（L676-682）的 strip 规则——scorer/judge 复用该 tag 则重跑互 strip 上一轮，符合「[roundtrip] 条目按上一轮语义重写」的既有约定；若想独立演进可用 `[roundtrip-scorer]` 类似 vision_seq 的 `[vision-seq]`（L120），但需自带 strip 函数。**推荐沿用 `[roundtrip]`**（三码 enum 的 degrade 记因本就跨子步骤共享）。

**B. 4-tuple 风格 cache**（mirror h3_regen.py L591-618, L654-671；key 维度按 RESEARCH Pitfall 7 扩展）：
```python
# h3_regen.py L601-602 原文（cache key 字段名惯例）：
_CACHE_KEY_FIELDS = ("video_content_hash", "engine_name", "engine_version", "prompt_version")

# scorer 的 key 维（RESEARCH §Pitfall 7 裁决——分辨率/引擎身份联动）：
# {video_content_hash, regen_mp4_sha256_16, model("siglip-so400m-patch14-384"), n_frames:8, window:[0.25,0.75]}
# → 896×512 smoke regen 与 1344×768 批产物天然分离，不会混进校准集。

# h3_regen.py L654-663 原文（原子写——tmp 带 PID）：
def _atomic_write_json(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```
cache 文件形状：RESEARCH §Code Examples 已给完整推荐 JSON（frames.orig/regen 各带 `{j, t_pct, t_sec, path}` 审计清单——SC2 硬要求）。cache miss/hit 判定 mirror `cache_read`（L605-618：文件缺席/损坏/字段不等一律 miss，绝不部分复用）。

**C. ffmpeg 帧提取 fail-loud**（mirror h3_regen.py L387-417 的 `extract_endpoint_frames`；clamp 值按 RESEARCH Pitfall 3 从 0.04 提到 0.2）：
```python
# h3_regen.py L401-415 原文形状（scorer 逐帧版：N=8×2 侧循环）：
    lf_ts = max(start_sec, end_sec - LAST_FRAME_GUARD_SEC)   # scorer 改用 min(ts, max(dur - 0.2, 0.0))
    for ts, suffix in ((start_sec, "ff"), (lf_ts, "lf")):
        dest = os.path.join(frames_dir, f"kst_{vch}_shot{sid:03d}_{suffix}.jpg")
        if os.path.isfile(dest):
            os.unlink(dest)    # 先删旧帧——绝无「失败残留旧帧」（WR-05）
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", src_video,
             "-frames:v", "1", "-q:v", "2", dest, "-loglevel", "error"],
            capture_output=True, timeout=60)
        if (proc.returncode != 0 or not os.path.isfile(dest)
                or os.path.getsize(dest) == 0):
            raise RuntimeError(
                f"ffmpeg 帧提取失败 rc={proc.returncode} dest={dest} "
                f"stderr={_stderr_snip(proc)}")
```
帧位公式（RESEARCH Pattern 1，探针实测）：`t_j = dur * (0.25 + 0.5*j/(N-1))`，clamp `min(ts, max(dur-0.2, 0.0))`——175f/24fps 流末帧起点 7.25s，`-ss 7.252` 实测越界。原片段侧时窗 = `shot.start_sec + t_j*duration`（-ss 来自自家 shots.json，list-form 无 shell 拼接）。

**D. sidecar scores 半边 READ-merge**（mirror h3_regen.py L796-826 的 `write_roundtrip_sidecar`；本 phase 写 scores 而非 regen）：
```python
# h3_regen.py L813-824 原文（kept-keys 半边替换 merge——Phase 21 的对偶扩展点）：
    merged: dict[int, dict] = {}
    for s in existing["shots"]:
        if isinstance(s, dict) and isinstance(s.get("shot_id"), int):
            merged[int(s["shot_id"])] = s
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("shot_id"), int):
            continue
        sid = int(e["shot_id"])
        kept = {k: v for k, v in merged.get(sid, {}).items()
                if k not in ("regen", "status")}
        kept.update(e)                          # 新半边落位
        merged[sid] = kept
```
scorer 版差异：新条目只带 `{shot_id, scores: {midframe_sim: {score, model}}}`；**scores 子对象浅合并**（不整体替换——防丢 judge 半边，RESEARCH Pattern 4）。写前两层自校验（本批 fail-loud / 预存坏剔除+备份 `.bak-<ts>`）逐行 mirror L805-863。schema 校验入口 mirror `_iter_sidecar_errors`（L770-776，Draft202012Validator）。

**E. graceful-degrade gate**（mirror h3_regen.py L1233-1239 的 ComfyUI gate → scorer 的模型加载 gate）：
```python
# h3_regen.py L1233-1239 原文形状：
    status, _body = _http_json(f"{args.comfy_url}/system_stats")
    if status != 200:
        pending_warnings.append({"code": "comfyui_unreachable",
                                 "detail": f"system_stats status={status}"})
        append_roundtrip_warnings(work_dir, pending_warnings)
        print(f"{STEP_TAG} ComfyUI 不可达（status={status}）—— graceful-degrade 退出")
        return 0
```
scorer 对应：SigLIP 加载失败（`LocalEntryNotFoundError` / `TypeError: not a string`，RESEARCH Pitfall 1 的实际报错）→ `{"code": "scorer_model_missing", "detail": ...}` + rc=0（enum 三码已有此码，h3_regen L157-161）。**不要 sys.exit 炸批**。

**F. 路径 off-by-one 陷阱**（h3_regen.py L190-199 注释原文）：
```python
# roundtrip.json 写前自校验目标 schema。**三层 parent**：本模块在 analysis/roundtrip/
# 下，比 analysis/vision_seq_facets.py 深一层——repo root 必须 parent.parent.parent。
```
scorer.py/judge.py 同层（analysis/roundtrip/）→ 同样三层 parent。

**G. GPU 选择 + CPU 降级**（mirror h3_regen.py L918-929 `gpu_mem_mib`）：
```python
# h3_regen.py L918-929 原文（fail-open 读数）：
def gpu_mem_mib(gpu_index: int) -> tuple[int, int] | None:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits", "-i", str(gpu_index)],
            capture_output=True, text=True, timeout=10)
        cols = [c.strip() for c in proc.stdout.strip().splitlines()[0].split(",")]
        return int(cols[0]), int(cols[1])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return None
```
scorer 编排（RESEARCH Pitfall 4）：默认 `--device cuda:0`（GPU0 3060Ti 4.9GB free，零竞争）；OOM/不可用 → CPU 降级（19 镜分钟级）；**绝不**在批后立即跑 GPU1（ComfyUI cache 驻留 ~21GB）。SigLIP 加载本体无 in-repo analog——用 RESEARCH Pattern 1 探针代码（transformers 5.6.2：`get_image_features(...).pooler_output`，参数名 `dtype=` 非 `torch_dtype=`）。

---

### `analysis/roundtrip/judge.py`（service, request-response + verdict 应用器）

**Analog:** `analysis/vision_seq_facets.py`（引擎生命周期）+ `analysis/engine_clients/qwen_eye_client.py`（调用面）+ `h3_regen.py`（comfy_free / verdict merge / cache）

**A. import 纪律**（mirror vision_seq_facets.py L88-96 —— **深一层**）：
```python
# vision_seq_facets.py L88-96 原文（analysis/ 直下版）：
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_clients.qwen_eye_client import (  # noqa: E402
    ENGINE_NAME, ENGINE_VERSION, QwenEye,
)
# judge.py 在 analysis/roundtrip/ 下 → 必须：
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
`engine_clients` 是唯一被 sanction 的跨模块 import（RESEARCH §Import 约定裁决，证据 local_vision_facets.py:57-61 + vision_seq_facets.py:88-92）。h3_regen 共享件（`append_roundtrip_warnings` / `gpu_mem_mib` / `comfy_free` / `_atomic_write_json` / `_load_schema_version`）用 importlib 文件加载（见 Shared Patterns §Import 纪律），**不改 h3_regen 成包**。

**B. 引擎生命周期：预判 + try/finally**（mirror vision_seq_facets.py L631-668）：
```python
# vision_seq_facets.py L631-668 原文（缩略）：
    if needs_engine:
        engine = QwenEye()
        try:
            healthy, _owned = engine.ensure_ready()
            if not healthy:
                warnings.append(f"{STEP_TAG} engine unavailable ... left as-is")
                print(f"[vision-seq] engine unavailable — degrading")
            else:
                for item in work:
                    ...  # per-shot 调用；单镜异常 → warning + continue 不阻塞
        finally:
            engine.stop_if_owned()          # 崩溃也不泄漏 13.4GB
```
judge 差异：(1) 全 cache 命中时零实例化（mirror 同文件 L564-567 预判）；(2) `ensure_ready` 返回 `(False, owned)` 时显式重试一次（间隔 ≥30s——RESEARCH Pitfall 6：启动实测恰 120s 贴 `LLM_START_TIMEOUT_S` 上限）；(3) 启动前 `comfy_free(comfy_url)` best-effort 腾 GPU1（h3_regen.py L1005-1011 原文：`_http_json(f"{comfy_url}/free", payload={"unload_models": True, "free_memory": True})`）。

**C. 单次 judge 调用**（qwen_eye_client.py L306-318 原文——observe_single 是 judge 的调用面）：
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
调用契约：单图豁免多图丢弃 bug；`enable_thinking:false` 恒传已在 `_call_llm`（L273-300，温度 0.1 + 瞬态重试 1 次）；串行调用（thread-unsafe by design）。三分类定义逐字进提示词 + JSON 模板 + prompt_text 只进 HTTP JSON body（T-20-01 延续，绝不进 argv）。

**D. 解析容错 + 重问**（无 in-repo 生产 analog——glm-structured-output 模式零依赖借用；RESEARCH Pattern 2 探针 5/5 实测，直接抄）：
```python
# RESEARCH §Pattern 2（本会话探针 /tmp/judge_probe/judge_probe.py 验证通过）：
def parse_judge_answer(txt: str):
    t = re.sub(r"```(?:json)?", "", txt.strip()).strip("` \n")
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None, "no-brace"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, f"json:{e.msg[:40]}"
    if obj.get("attribution") not in ("prompt_faithful", "model_diverged",
                                      "prompt_underspecified"):
        return None, "enum"
    c = obj.get("confidence")
    if not isinstance(c, (int, float)) or not (0.0 <= c <= 1.0):
        return None, "conf-range"
    r = str(obj.get("reason") or "")
    if len(r) < 10:
        return None, "reason-short"
    return obj, "ok"
```
reason 写 sidecar 前截 2000（schema T-18-02 上界，roundtrip.schema.json L87）；失败重问 ≤2 次且错误信息回喂 prompt（retry-with-feedback）。

**E. verdict 应用器 `--apply-verdict --tau-sim <τ>`**（RESEARCH Open Q1 推荐放 judge.py；merge 语义 = h3_regen L813-824 的对偶，RESEARCH Pattern 4 给了完整骨架）：
```python
# RESEARCH §Pattern 4（冻结语义骨架——scores 可更新 / verdict 只补缺）：
    for e in entries:
        sid = int(e["shot_id"])
        prev = merged.get(sid, {})
        kept = {k: v for k, v in prev.items() if k not in ("scores",)}
        if "verdict" in prev:
            e.pop("verdict", None)          # 冻结：已有 verdict（auto 或 human）永不覆盖
        new_scores = e.get("scores") or {}
        merged_scores = dict(prev.get("scores") or {})
        merged_scores.update(new_scores)    # scores 子对象浅合并
        kept["scores"] = merged_scores
        kept.update({k: v for k, v in e.items() if k != "scores"})
        merged[sid] = kept
```
verdict 判定：`accepted ⇔ midframe_sim ≥ τ_sim ∧ attribution == prompt_faithful`（硬合取，无 confidence 第二门槛）；`{decision, source: "auto", decided_at: ISO}`。写前两层自校验复用 h3_regen WR-04 模式。**单测必须含 Pitfall 8 双向用例**（预存 verdict + h3_regen 风格重写 regen 半边 → verdict 原样）。输入读取：从 roundtrip.json 现存条目读 scores 双信号（非重算——校准后只应用不重跑引擎）。

**F. 2×4 grid 拼图**（无 in-repo analog——repo 的 PIL 仅 `Image.open` 级使用，无 ImageDraw/Image.new；RESEARCH Pattern 3 探针实测 27B 正确解读标注）。要点：cell 640×360、canvas 1370×1476 ≈2.0M px（token 预算锚：vision_seq 曾 1920×1080 单图 147 calls 无碍）；列头 ORIGINAL（#58a6ff 蓝）/ REGEN (h3)（#3fb950 绿）——GitHub-dark palette 是 repo CSS 惯例（CLAUDE.md §Embedded CSS）；行标签 t=0/33/66/100% 竖排；**标签必须进图**。落 `roundtrip/_judge_grids/shot_XXX.jpg`（SC3 抽检素材，mirror 20-03 `_compare/` 先例）。

---

### `tests/test_scorer.py` + `tests/test_judge.py`（test, unit + fakes）

**Analog:** `tests/test_h3_regen.py`（1214 行——repo 最新最全的 fake 基建；RESEARCH 推荐 two files，planner 也可合一）

**A. 被测模块加载**（test_h3_regen.py L61-66 原文——tests/ 全用 importlib 文件位置加载）：
```python
REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "h3_regen", REPO_ROOT / "analysis" / "roundtrip" / "h3_regen.py")
h3m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h3m)
```

**B. work_dir fixture + argv 注入**（L153-189 原文）：`make_workdir(tmp_path, n_shots, duration_by_id)` 写 shots.json + prompts.json（顶层 list、含 prompt_text）+ 假 h264.mp4；`run_main(work, extra_args)` 临时换 `sys.argv` 调 `main()` 返回 rc。judge 测试需追加：预置 `roundtrip/shot_XXX_regen.mp4`（几字节假 mp4）+ roundtrip.json 预存条目。

**C. patch 点全家桶**（L192-242 `patch_pipeline` —— scorer/judge 直接复制改名）：
```python
# L205-241 缩略：monkeypatch h3m._http_json → FakeHTTP；monkeypatch subprocess.run
# 按 cmd[0] 分发（ffmpeg 写假 jpg 字节 / nvidia-smi 回假 stdout / …）；
# monkeypatch time.sleep → no-op；产物下载函数 → 直写字节。
    monkeypatch.setattr(h3m.subprocess, "run", fake_run)
    monkeypatch.setattr(h3m.time, "sleep", lambda s: None)
```
scorer 专属 fake：SigLIP 加载函数 monkeypatch 成 FakeSigLIP（固定 1152d 向量替身——RESEARCH Validation Architecture 明示）；`probe_duration_sec` → 固定值（mirror L852 `monkeypatch.setattr(h3m, "probe_duration_sec", lambda p: 5.25)`）。judge 专属 fake：FakeEye 回放预设 observe_single 文本（重问矩阵用：首答坏 JSON、次答好 JSON）；grid 拼图纯 PIL 无需 fake。

**D. 回放/时钟替身**（L71-95 原文）：`FakeHTTP`（按调用序 pop 预设 `(status, body)`、耗尽回 `(0, None)`）+ `FakeClock`（每次 +step 秒，超时用例不真等）。

**E. sidecar 断言 helper**（L830-846 原文）：`read_sidecar(work)` / `validate_sidecar(data)`（Draft202012Validator 全量 iter_errors）/ `sidecar_result(sid, mp4, **over)` 构造 results 元素——judge 的 verdict 冻结测试直接复用。

**F. 直接可抄的测试模板**（Phase 21 最高价值的三个既有用例）：
- `test_sidecar_merge_preserves_future_fields`（L870-907）——READ-merge 保留语义的模板；judge 版断言反转方向：**预存 verdict 原样 + 新 scores 浅合并不丢 judge/midframe_sim 对侧子对象**（RESEARCH Validation 表 DATASET-01 两行）。
- `test_sidecar_preexisting_bad_entry_skipped_not_deadlocked`（L927-957）——WR-04 两层校验模板（坏条目剔除 + `.bak-*` 备份 + str warning）。
- `test_warnings_dual_shape_merge`（L580-603）——若沿用 `[roundtrip]` tag 则无需新测试（h3_regen 已覆盖）；若换 tag 需 mirror 一份。
- 帧窗数学锚点测试模板：`test_h3_frame_count_grid`（L273-282）的「锚点值 + 全域不变式」形状 → scorer 的 `frame_ts`（t=100% clamp 生效、t=0/t=end 结构性排除、25%-75% 界内）。

---

### `.planning/research/roundtrip-threshold-calibration.md`（doc, 校准报告）

**Analog:** `.planning/research/vision-seq-spike-report.md`（CONTEXT 明示结构参考）

结构映射（vision-seq-spike-report.md 行号）：
| 报告节 | Analog 位置 | Phase 21 对应内容 |
|--------|-------------|-------------------|
| 头部元数据块（Deliverable status / Generated at UTC / Repo HEAD / Fixture / 镜清单 / Fakes 声明） | L1-18 | 19 镜 @1344×768 清单（shot 70 跳过注明）、批渲染时段、raw 输出零改写声明 |
| 烧录实录表（步骤/调用量/结果） | L20-31 | overnight 批耗时 + scorer <5min + judge 19 镜调用数 |
| Methodology（含**反循环论证声明** L63-68） | L33-68 | 双门槛定义 + **τ_sim 只能由 Kai 看分布裁决、机器指标仅参考**（mirror 该声明的措辞姿态——SCORE-03 checkpoint 的法理基础） |
| 机器可见观察（不预判裁决） | L70-84 | sim 分布表/分位数/per-position 分布 + attribution 分桶——区分度不足时如实呈现（Pitfall 5） |
| Evidence（每镜并排） | L86-178 | 19 镜散点/表 + 抽检 5 镜 grid 引用（`_judge_grids/` 路径指针） |
| Recommendations（checkpoint 裁决记录） | L206-229 | τ_sim 裁决值 + 理由 + 抽检一致率（≥4/5）+ 不一致镜记录 + rejected 按归因分桶占比（SC4 防偏向审计） |
| Reproducibility（重跑命令 + sha256 + cache 秒级重跑实测） | L348-398 | scorer/judge argv 全文 + cache 全命中重跑秒级证明 |

关键 mirror 点：报告是 **checkpoint 的载体**——草稿（含 τ_sim 候选分位数表 + rejected 分桶预演）先行，Kai 裁决后终稿回写裁决记录（analog L340-346「裁决记录（Task 3 checkpoint —— 已收口）」节）。

---

### `.planning/PROJECT.md`（MODIFY — Key Decisions 追加行）

**Analog:** 自身 Key Decisions 表（L121-149）的 Phase 10 五行格式（L138-142）

行格式模板（L138 实样）：`| **决策标题** (Row N) | 理由 | 结论 + *(decided_at: YYYY-MM-DD; phase: 21; evidence: .planning/research/roundtrip-threshold-calibration.md#节锚)* |`

Phase 21 至少一行：τ_sim 锁定值 + 双门槛定义（accepted ⇔ sim ≥ τ ∧ prompt_faithful）+ 证据指针指向校准报告。SC4 明文要求落此表。

---

## Shared Patterns

### STEP_TAG 括号日志 + 中文 docstring
**Source:** CLAUDE.md §Logging/§Comments + h3_regen.py L153
**Apply to:** 全部新 py 文件。每条进度行 `print(f"{STEP_TAG} …")`；docstring 中文五段式（背景/算法步骤/degrade 语义/cache 惯例/argv 用法）。

### graceful-degrade warnings 三码 closed enum
**Source:** h3_regen.py L157-161
```python
_ROUNDTRIP_WARNING_CODES = (
    "comfyui_unreachable",
    "vram_insufficient",
    "scorer_model_missing",   # scorer 模型加载失败专用码——enum 已预留
)
```
**Apply to:** scorer.py（scorer_model_missing）、judge.py（引擎不可用走 str 形事件说明 + rc=0——mirror h3_regen「跳镜 str」先例，因三码 enum 无 judge 码；str 形永远合法，h3_regen.py L316 先例）。**复用 `append_roundtrip_warnings`**（h3_regen.py L685-699，双形保留 + 上一轮 strip）——importlib 加载，勿复制。

### Import 纪律（research §Import 约定裁决，VERIFIED）
**Apply to:** scorer.py / judge.py 的全部跨模块引用：
1. `engine_clients.qwen_eye_client` → `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` 后 import（judge.py 专用；深一层 off-by-one）；
2. h3_regen 共享件 → **importlib 文件加载**（单源不漂移；h3_regen 模块级无副作用、main 有 guard，加载安全）：
```python
# mirror h3_regen.py L708-712 的加载形状（其自身加载 export_asset 的方式）：
_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h3s)
# 用 h3s.append_roundtrip_warnings / h3s.gpu_mem_mib / h3s.comfy_free / h3s._atomic_write_json
```
3. SCHEMA_VERSION → 永远经 h3s（其 `_load_schema_version` 已指向 export_asset 单源），绝不复制字面量；
4. **不改 h3_regen 为包结构**（牵动 Phase 20 已验证代码——CONTEXT/研究双锁）。

### 原子写 + list-form subprocess
**Source:** h3_regen.py L654-663（`_atomic_write_json`，tmp 带 PID）+ L378-384（`_stderr_snip`）+ L407-410（ffmpeg list-form）
**Apply to:** 所有 JSON 落盘（cache/sidecar/warnings）与全部 ffmpeg/ffprobe 调用。`-ss` 数值只来自自家 shots.json/ffprobe；`capture_output=True, timeout=60`。

### sidecar 两层写前自校验（WR-04 防重试死锁）
**Source:** h3_regen.py L805-863（① 本批坏 sys.exit fail-loud；② 预存坏归因 shot_id → str warning + 剔除 + `.bak-<ts>` 备份 → 复验）
**Apply to:** scorer 的 scores 写入 + judge 的 verdict 写入。这是 DATASET-01「rejected 永不删除」之外的第二道数据安全闸。

### GPU 串行链编排
**Source:** h3_regen.py L1005-1011（`comfy_free`）+ L918-929（`gpu_mem_mib`）+ RESEARCH §Pitfall 4
**Apply to:** 三步串行（overnight h3 批 → scorer @GPU0 → judge @GPU1）：judge 启动前 best-effort `POST /free`（ComfyUI cache 驻留 ~21GB 实测）；scorer 默认 GPU0 零竞争 + CPU 降级路径；显存自查用 PID 归因或直接选零竞争卡，**绝不**绝对 free 下限式自查（20-02 决策教训）。

## No Analog Found

| File / 子模式 | Role | Data Flow | Reason | Sanctioned Source |
|------|------|-----------|--------|-------------------|
| scorer.py 的 SigLIP 加载块 | service | batch transform | repo 零 transformers 使用（grep 实证：analysis/html/detectors/scripts/audio 无命中） | RESEARCH §Pattern 1 探针代码（/tmp/probe_siglip3.py，transformers 5.6.2 实测：`.pooler_output`、`dtype=`） |
| judge.py 的 PIL 2×4 标注 grid | service | transform | repo PIL 仅 Image.open 级（grep 实证无 ImageDraw/Image.new 于源码目录） | RESEARCH §Pattern 3 探针（grid_shot1.jpg 27B 正确解读实测） |
| judge.py 的 parse_judge_answer + 重问 | service | request-response | repo 无结构化 LLM 输出解析生产代码（glm-structured-output 是全局 skill 非 repo 资产） | RESEARCH §Pattern 2（5/5 parse-ok 实测，直接抄） |
| 校准散点 PNG（可选） | doc 辅助 | n/a | repo 无 matplotlib 使用 | matplotlib 3.11.1 已装；fallback = markdown 表 + 文本直方图（RESEARCH Environment 表） |

## Metadata

**Analog search scope:** `analysis/`（含 `analysis/roundtrip/`、`analysis/engine_clients/`）、`tests/`、`spec/schemas/`、`.planning/research/`、`.planning/PROJECT.md`、`html/`、`detectors/`、`scripts/`、`audio/`
**Files scanned:** h3_regen.py（1444 行全文）、vision_seq_facets.py（743 行全文）、qwen_eye_client.py（349 行全文）、test_h3_regen.py（1214 行全文）、roundtrip.schema.json（107 行全文）、vision-seq-spike-report.md（495 行全文）、PROJECT.md（Key Decisions 节）、CLAUDE.md（全文）；grep 验证 PIL/transformers 缺席
**Pattern extraction date:** 2026-08-19
