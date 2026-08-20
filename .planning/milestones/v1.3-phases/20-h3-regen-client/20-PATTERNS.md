# Phase 20: h3 复现客户端 - Pattern Map

**Mapped:** 2026-08-20
**Files analyzed:** 4 (3 new + 1 modified)
**Analogs found:** 3 / 4（1 个无 repo 先例——模板 JSON，内容已由 RESEARCH 完整给出）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `analysis/roundtrip/h3_regen.py` | service（repo 惯例「stage 脚本」：argparse + main()） | request-response（ComfyUI HTTP）+ batch（逐镜串行）+ file-I/O（cache/产物） | `analysis/vision_seq_facets.py` | exact（批处理 stage 脚本 + 引擎生命周期 + 4-tuple cache + graceful-degrade，Phase 19 刚验证） |
| `analysis/roundtrip/workflow_fl2va.json` | config（纯数据模板，代码分离） | data（无流程——被 deepcopy 消费） | 无（repo 首个 workflow 数据文件） | none |
| `tests/test_h3_regen.py` | test | offline unit（全 monkeypatch 零真引擎） | `tests/test_vision_seq_facets.py` + `tests/test_qwen_eye_client.py` | exact |
| `run_pipeline.py`（MODIFY `--force` 清单，L753-787） | pipeline orchestrator（清理清单） | file-I/O | 自身扩展（Phase 19 注释先例 L766-767） | exact（in-place 扩展） |

次级 analog（h3_regen.py 的局部模式来源，非整体模板）：
- `analysis/engine_clients/qwen_eye_client.py` — stdlib `_http_json` + nvidia-smi 查询式读数 + fail-open
- `/data/workspace/kais-hermes-skills/.../P11/h3_batch_render_v4.py`（repo 外）— **只抄轮询 crash-safe 骨架**；提交/下载/参数下发有 4 个已实证陷阱不可照抄（见下）

---

## Pattern Assignments

### `analysis/roundtrip/h3_regen.py` (service, request-response + batch + file-I/O)

**主 Analog:** `analysis/vision_seq_facets.py`（743 行，Phase 19 交付，全套 cache/降级/生命周期惯例）
**局部 Analog:** `analysis/engine_clients/qwen_eye_client.py`（HTTP plumbing + VRAM 读数）、kmc `h3_batch_render_v4.py`（仅轮询骨架）

#### A. 模块骨架（vision_seq_facets.py 整体结构）

**文件头 + imports**（L1, L78-96）：
```python
#!/usr/bin/env python3
"""…docstring：背景/算法步骤/graceful-degrade 语义/cache 惯例/用法（argv 示例）…"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
```
注意：vision_seq L91-96 有 `sys.path.insert` 导入 engine_clients——**h3_regen 不需要**（无 sibling 包依赖，全 stdlib）；但模板加载需要 `copy.deepcopy`（`import copy`）与 `urllib.request`/`urllib.parse`。

**模块级常量块**（mirror L98-123）：
```python
CACHE_NAME = "vision_seq"          # → h3_regen 用 "h3_regen"
PROMPT_VERSION = "vision-seq-v2"   # cache-invalidation 旋钮
STEP_TAG = "[vision-seq]"          # → "[roundtrip]"
```
h3_regen 常量集（来自 RESEARCH Code Examples / VRAM guard 节）：`COMFY = "http://127.0.0.1:8188"`、`VRAM_GPU_INDEX = 1`、`BATCH_MIN_FREE_MIB = 22528`（22GB）、`EYE_LEASE_MIB = 13721`、`_ROUNDTRIP_WARNING_CODES`（mirror `scripts/export_asset.py:63-67` 三码 enum）。

**video_content_hash**（L150-161——照抄，cache key 第一维；repo 权威实现在 `analysis/call_shot_analysis.py:91-108`，此处是等价复制）：
```python
def video_content_hash(video_path: str) -> str:
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)
            h.update(f.read(1024 * 1024))
    h.update(str(size).encode())
    return h.hexdigest()[:16]
```

#### B. cache：4-tuple key + 元数据/产物分离（REGEN-02）

**Analog:** vision_seq_facets.py L229-238（`_cache_key`）+ L259-284（`_load_cache_envelope` miss 语义）+ L287-340（`_save_cache_envelope` read-merge-write）。

`_cache_key` 形状（L229-238，h3_regen 去掉 ear 维 = 正好 4-tuple）：
```python
def _cache_key(vch: str, ear: bool) -> dict:
    return {
        "video_content_hash": vch,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ear": ear,
    }
```
h3_regen 适配：`engine_name = "comfyui-fl2va"`、`engine_version` 按 RESEARCH Open Question 3 推荐 `"comfyui-0.30.0_fl2va-int8-convrot_euler-simple-15"`（分辨率并入，Pitfall 7：sampler/scheduler/steps 冻进版本串）、`prompt_version = sha256(该镜 prompt_text)[:8]`（per-shot，CONTEXT 锁定——**与 vision_seq 的全局 PROMPT_VERSION 串不同**，这里每镜一算）。

miss 语义（L259-284 节选——任一不匹配 → 全新空信封，绝不部分复用）：
```python
    env = data.get(_envelope_name(ear))
    if not isinstance(env, dict) or env.get("_cache_key") != key:
        return miss
```
h3_regen 的 shot_XXX.json 是单信封（无双 ear），简化为 `_cache_key` dict 全等比较 + mp4 实体独立校验（存在 + size>1KB——mirror kmc v4 L188/L307 的 `> 1000` 下限）。

**原子写**（L333-338，照抄）：
```python
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        tmp = cache_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cache_file)
```

#### C. HTTP plumbing（qwen_eye_client.py L113-131）

```python
    @staticmethod
    def _http_json(url: str, payload: dict | None = None,
                   timeout: float = 30.0) -> tuple[int, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300] if exc.fp else ""
            return exc.code, body
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return 0, str(exc)[:300]
```
h3_regen 用于 `/prompt`（POST）、`/history/{id}`（GET）、`/free`（POST）、`/system_stats`（GET 探活）。**例外**：`/upload/image` multipart 走 `subprocess.run(["curl", …])`（RESEARCH Pitfall 5：requests 大图 ConnectionResetError；GET 该路由 404 属正常）。`/view` 下载是二进制不是 JSON——用裸 `urllib.request.urlopen` + `f.write(r.read())`（RESEARCH Code Examples 已给全骨架，直接用）。

#### D. VRAM guard（qwen_eye_client.py L140-153 照抄 + 扩展）

```python
    @staticmethod
    def _vram_free_mib() -> int | None:
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits",
                 "-i", str(_VRAM_GPU_INDEX)],
                capture_output=True, text=True, timeout=10,
            )
            return int(proc.stdout.strip().splitlines()[0])
        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            return None        # fail-open：预检绝不阻塞
```
新增同款 `_compute_apps()`（`--query-compute-apps=pid,used_memory`，Pitfall 1 的每镜 PID 归因 gate）与 `kill_tts()`（`pkill -f voicedesign_server.py / indextts25-server.py`，pattern 精确到脚本名——Security Domain 条款）。kill 前后各记一条 `[roundtrip]` warning（CONTEXT 锁定）。

#### E. 轮询 crash-safe 骨架（kmc h3_batch_render_v4.py —— 只抄这 4 点）

| 可照抄 | 来源 | 不可照抄（RESEARCH Pitfall 2 四偏差） |
|--------|------|----------------------------------------|
| poll 异常 → `continue`（L223-227） | `try: poll = … except Exception as e: … continue` | (a) 它 POST KAP multipart（L139/L150）——h3_regen 走 ComfyUI 原生 `/prompt` + `{"prompt": wf}` JSON |
| 60s 节流日志（L264-265 `if elapsed % 60 == 0`） | | (b) `download_from_container` docker cp 三 pattern 猜名（L172-212）——h3_regen 用 history 条目的确切 filename 调 `/view` |
| sleep 15s 轮询节奏（L219-220） | | (c) `h3_frame_count()` 结果只进日志（L312-313），multipart data（L121-127）无 length 字段——h3_regen 必须写进节点 20 `inputs.length` |
| 产物 `size > 1000` 有效性下限（L188, L307）+ 批循环 completed/failed 收尾清单（L301-331） | | (d) seed = `50000 + abs(hash(sid)) % 9999`（L125）跨进程不确定——用 RESEARCH 的 `int(sha256(f"{vch}:{shot_id}")[:8], 16) % 2**31` |

`h3_frame_count` 的 17k+5 网格算法形状（L42-49）可参考，但按 RESEARCH「Don't Hand-Roll」用 `max(124, min(ceil-on-grid, 362))`（floor 124 + cap 362 是 kmc 没有的）。超时按 Pitfall 8 缩放（`900 + length*3` 或默认 2400s），不要照抄 max_wait=900。

#### F. 批循环 + 降级 + 写出（vision_seq_facets.py main() 结构）

**argparse main() 骨架**（L489-518）：
```python
def main():
    ap = argparse.ArgumentParser(description="…")
    ap.add_argument("--shots", required=True, help="…")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— route_cache 写在其下")
    …
    args = ap.parse_args()
```
h3_regen flags：`--work-dir`（必填）、`--comfy-url`、`--gpu-index`、`--sample-shots N`、`--max-shot-sec`（默认 10）、`--regen-resolution`（默认 1344x768）、`--force`、`--shot-timeout`（Pitfall 8）。

**per-shot 预判 + 10 进度计数**（L619-620，照抄）：
```python
        done += 1
        if (done % 10) == 0:
            print(f"[vision-seq] {done}/{len(prompts)} shots processed")
```

**批开始 gate + graceful-degrade**（L631-644 的形态——h3_regen 对应「批开始 kill TTS + /free + free<22GB 拒整批」）：
```python
            healthy, _owned = engine.ensure_ready()
            if not healthy:
                warnings.append(
                    f"{STEP_TAG} engine unavailable "
                    f"(ensure_ready failed: VRAM/startup) — "
                    f"pending action/camera facets left as-is")
                print(f"[vision-seq] engine unavailable — degrading")
```
h3_regen 语义：ComfyUI `/system_stats` 非 200 → `[roundtrip] {code: "comfyui_unreachable"}` warning + **exit 0**（资产照常——CONTEXT 锁定）；free < 22528 → `vram_insufficient` + exit 0。**无 try/finally 引擎生命周期**（不拥有 ComfyUI 进程，与 vision_seq 的 QwenEye 拥有语义不同——只在批开始做 gate）。

**per-shot degrade 不阻塞批**（L660-664）：
```python
                    if err:
                        item["error"] = True
                        warnings.append(f"{STEP_TAG} shot {item['sid']}: …")
                        continue   # 该镜该 facet degrade，不阻塞其余
```

**输出写保护 + schema 自校验 + 原子写**（L703-717——roundtrip.json 写 regen 半边时同款，jsonschema 已是 spec/ 依赖）：
```python
    if changed:
        from jsonschema import Draft202012Validator
        with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
            prompts_schema = json.load(f)
        errors = list(Draft202012Validator(prompts_schema).iter_errors(prompts))
        if errors:
            sys.exit(f"…schema validation failed ({len(errors)} errors): …")
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)
```
schema 路径解析 mirror L147（`Path(__file__).resolve().parent.parent / "spec" / "schemas" / "roundtrip.schema.json"`——注意 h3_regen 在 `analysis/roundtrip/` 下，多一层 `roundtrip/`，parent.parent 仍指 repo root？**否**：`analysis/roundtrip/h3_regen.py`.parent = `analysis/roundtrip/`，.parent.parent = `analysis/`——需要 `.parent.parent.parent`。planner 注意这个 off-by-one）。

**收尾 print**（L729-738，照抄形状）+ `if __name__ == "__main__": sys.exit(main())`（L742-743）。

---

### `analysis/roundtrip/workflow_fl2va.json` (config, data)

**Analog:** 无 repo 先例（首个「代码旁置数据模板」文件）。

**内容来源：** 20-RESEARCH.md §Code Examples「完整 fl2va workflow 模板」——9 节点 native KSampler 链 JSON **逐字落盘**（节点 10/11/12/13/14/15/20/21/30/40/41/42/50，占位符 `<FF_FILENAME>`/`<LF_FILENAME>`/`<PROMPT_TEXT>`/`<PREFIX>` 保留原样，运行时 deepcopy 后按注入表改）。RESEARCH 已双源核对（KAP i2va.ts 源码 + live history 三条成功渲染），**planner/实现不要再改节点拓扑**——sampler=euler / scheduler=simple / steps=15 / cfg=1.0 / shift_video=12.0 是 CONTEXT SC1 + Pitfall 7 锁定值。

加载侧约定（h3_regen.py 内）：`json.load(open(Path(__file__).parent / "workflow_fl2va.json"))` → `copy.deepcopy` → 改 inputs（CONTEXT「mirror kmc 模式」= 深拷贝改节点这个动作，**不是** kmc 的提交协议）。

---

### `tests/test_h3_regen.py` (test, offline unit)

**主 Analog:** `tests/test_vision_seq_facets.py`（FakeEngine + tmp_path workdir + argv 注入 main）
**局部 Analog:** `tests/test_qwen_eye_client.py`（FakeHTTP 记录式替身 + subprocess.run fake + monkeypatch classmethod/staticmethod）

**模块加载（不污染 sys.path）**（test_vision_seq_facets.py L20-36，照抄）：
```python
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "vision_seq_facets", ANALYSIS / "vision_seq_facets.py")
vsf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vsf)
```
→ h3_regen 版：`spec_from_file_location("h3_regen", REPO_ROOT / "analysis" / "roundtrip" / "h3_regen.py")`。**注意**：h3_regen.py import 时会读模板 JSON——模块级读则用相对 `Path(__file__)`（对 tmp cwd 免疫）；若挪进函数/常量更稳，planner 定。

**workdir 搭建 helper**（L39-69，照抄形状——h3_regen 版需 shots.json（含 start_sec/end_sec/duration）+ prompts.json（prompt_text）+ 假 h264.mp4 + 假 ComfyUI 帧图）：
```python
def make_workdir(tmp_path, n_shots=2, …):
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = [{"id": i + 1, "start_sec": i * 1.0, "end_sec": i * 1.0 + 1.0, …}]
    (work / "shots.json").write_text(json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    …
```

**argv 注入 run_main + 替身 patch**（L128-148，照抄）：
```python
def run_main(work, prompts_path, extra_args=None):
    argv = ["vision_seq_facets.py", "--shots", str(work / "shots.json"), …]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = vsf.main()
    finally:
        sys.argv = old_argv
    return rc


def patch_engine(monkeypatch, fake):
    monkeypatch.setattr(vsf, "QwenEye", lambda: fake)
```
→ h3_regen 版 patch 点：`monkeypatch.setattr(h3m, "_http_json", …)`（若 h3_regen 采用 qwen_eye 同款 `_http_json` 静态方法则测试免费获得单一 patch 点——**建议实现就这么写**）、`monkeypatch.setattr(h3m.subprocess, "run", fake)`（喂假 nvidia-smi / curl / pkill 输出）、`monkeypatch.setattr(h3m.time, "sleep", lambda s: None)`（不真等 15s——test_qwen_eye_client.py L120 同款）。

**FakeHTTP 记录式替身**（test_qwen_eye_client.py L26-38——h3_regen 的 FakeComfyUI 核心）：
```python
class FakeHTTP:
    """记录式 _http_json 替身 —— 按调用序回放预设 (status, body)。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []          # (url, payload) 元组

    def __call__(self, url, payload=None, timeout=30.0):
        status, body = self.responses.pop(0) if self.responses else (0, None)
        self.calls.append((url, payload))
        if isinstance(body, str):
            body = body.encode()
        return status, body
```

**subprocess fake fixture**（test_qwen_eye_client.py L41-52，照抄）：
```python
@pytest.fixture
def no_engine(monkeypatch):
    calls = []
    monkeypatch.setattr(qec.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or _FakeProc())
    return calls


class _FakeProc:
    stdout = "0"
    returncode = 0
```
→ h3_regen 版 `_FakeProc.stdout` 按命令分发假输出（nvidia-smi query-gpu → `"22539"`；query-compute-apps → `"1234, 676 MiB"`）。

**断点续跑用例形态**（L280 `test_cache_hit_second_run_zero_engine_calls` 的结构）：跑两次 run_main，第二次换新 FakeEngine/FakeHTTP 并断言 `fake2.calls == 0`——h3_regen 的「重跑同命令 → 全 cache-hit 零提交」unit 版即此（REGEN-02 resume 测试）。

inline fixtures（假 history entry success/error/timeout 三形）按 RESEARCH Wave 0 gaps 测试内联，无需 conftest。

---

### `run_pipeline.py` — MODIFY `--force` 清单（SC4, REGEN-02）

**Analog:** 自身（L753-787 现有块）+ Phase 19 注释先例（L766-767）。

**现状（已核实，L768-787）：**
```python
        import shutil
        route_cache_dir = os.path.join(work_dir, "route_cache")
        audio_analysis_cache_dir = os.path.join(route_cache_dir, "audio_analysis")
        for p in (shots_json, frames_json, audio_json, transcript, out_html,
                  asset_json, asset_json + ".video-stamp",
                  prompts_json,                                      # Phase 6
                  prompts_json + ".video-stamp",                     # Phase 6 WR-01
                  registry_draft,                                    # Phase 7
                  registry_draft + ".video-stamp",                   # Phase 7 WR-01
                  review_html,                                       # Phase 7
                  audio_semantic_json,                               # Phase 14
                  audio_semantic_json + ".video-stamp",              # Phase 14 WR-01
                  speakers_json,                                     # Phase 14
                  route_cache_dir,                                   # Phase 6+7
                  audio_analysis_cache_dir):                         # Phase 14
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.unlink(p)
        print(f"[force] cleared cache under {work_dir}")
```

**核实结论（与 REGEN-02 研究一致）：**
1. `route_cache/` **整目录 rmtree（L781）已天然覆盖 `route_cache/h3_regen/`** —— 无需加条目，只需 mirror Phase 19 的注释行（L766-767 先例）：
   ```python
        # Phase 20：route_cache 整目录 rmtree 已天然覆盖 route_cache/h3_regen/
        # 子目录（h3 复现元数据 cache）—— 无需单列进清单。
   ```
2. **真正要加的**：`roundtrip/` 产物目录不在清单（现清单无任何 roundtrip 项）。在 L740-749 变量块加：
   ```python
    # Phase 20：roundtrip/（h3 复现产物目录）+ roundtrip.json（RT 契约 sidecar）
    roundtrip_dir = os.path.join(work_dir, "roundtrip")
    roundtrip_json = os.path.join(work_dir, "roundtrip.json")
   ```
   并入 for 元组（带 `# Phase 20` 尾注）。`roundtrip.json` 是否清理 planner 定——CONTEXT 只点名 `route_cache/h3_regen/` + `roundtrip/` 产物目录；sidecar 是 READ-merge 语义，清了也只丢 degrade 历史，倾向一并清（force = 全重跑语境）。
3. 守住 L763 既有纪律：**EXPLICIT LIST，NEVER glob/rmtree 父级**。

---

## Shared Patterns

### 1. `[stage]` 前缀日志 + 进度计数 + banner
**Source:** `analysis/vision_seq_facets.py` L120 (`STEP_TAG = "[vision-seq]"`)、L619-620（10 计数）、L729-738（收尾 summary print）
**Apply to:** h3_regen.py 全部 print。`STEP_TAG = "[roundtrip]"`。

### 2. JSON 原子写 + indent=2 ensure_ascii=False
**Source:** `analysis/vision_seq_facets.py` L333-338（cache）、L714-717（输出）
**Apply to:** h3_regen 的 shot_XXX.json cache、roundtrip.json、warnings.json、skipped 清单——全部 tmp + `os.replace`。

### 3. 4-tuple cache key + miss-即-全新 + 元数据/产物分离
**Source:** `analysis/vision_seq_facets.py` L229-238、L259-284、L287-340
**Apply to:** `route_cache/h3_regen/shot_XXX.json`；hit 判定外加 mp4 实体校验（存在 + >1KB，kmc v4 L188 同款下限），**不做** ffprobe（CONTEXT 锁定）。

### 4. graceful-degrade：引擎不可达 → 结构化 warning + exit 0
**Source:** `analysis/vision_seq_facets.py` L637-644（形态）；结构化条目规范 `scripts/export_asset.py` L63-91
**Apply to:** ComfyUI 不可达（`comfyui_unreachable`）/ VRAM 不足（`vram_insufficient`）→ warning + exit 0；per-shot 失败 → status{failed} + continue。

### 5. warnings sidecar READ-merge-write（双形保留——**不可照抄 vision_seq 的读法**）
**Source:** `analysis/vision_seq_facets.py` L214-226（`_read_existing_warnings`——**Pitfall 6：L225 的 `isinstance(w, str)` 过滤会丢 dict 条目，禁止照抄**）；双形合法规范 `scripts/export_asset.py` L70-91（`_valid_warnings_list`：str 或 `{code, detail}` 且 code ∈ 三码 enum）；修正版 merge helper 已在 20-RESEARCH.md §Code Examples「warnings 追加（双形保留 merge）」给出完整代码
**Apply to:** h3_regen 的 warnings 合并——strip 逻辑按「dict 且 code ∈ `_ROUNDTRIP_WARNING_CODES`」识别上一轮条目（不用 `startswith(STEP_TAG)`——本 step 条目是 dict 不是 str）。

### 6. nvidia-smi 查询式读数 + fail-open
**Source:** `analysis/engine_clients/qwen_eye_client.py` L140-153（`--query-gpu=memory.free --format=csv,noheader,nounits -i 1`，异常 → None 不阻塞）
**Apply to:** 批开始 gate（free 读数）+ 每镜 gate（`--query-compute-apps=pid,used_memory` 同款调用形状，RESEARCH Code Examples 已给 `compute_apps()` 全码）。

### 7. stdlib-only `_http_json`（status, body）返回对
**Source:** `analysis/engine_clients/qwen_eye_client.py` L113-131
**Apply to:** h3_regen 全部 JSON 端点；且写成 staticmethod——测试免费获得单一 monkeypatch 点（test_qwen_eye_client.py L60-61 的 `classmethod(lambda cls, url, **kw: fake(url, **kw))` patch 形状）。

### 8. schema 写前自校验
**Source:** `analysis/vision_seq_facets.py` L703-713（Draft202012Validator + iter_errors + 前 3 错误 sys.exit）
**Apply to:** roundtrip.json 写前过 `spec/schemas/roundtrip.schema.json`（jsonschema 已是 spec/ 依赖，测试内 `jsonschema.validate` 同源）。

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `analysis/roundtrip/workflow_fl2va.json` | config | data | repo 无「代码旁置 JSON 数据模板」先例（spec/schemas/*.json 是校验规约非运行时输入）。内容不靠类比——20-RESEARCH.md §Code Examples 已给逐字模板 + 注入表，直接落盘 |

其余无先例的**行为**（而非文件）也已由 RESEARCH Code Examples 给出完整参考实现：submit/poll/download 骨架、VRAM guard、双形 warnings merge——planner 直接引用 RESEARCH 代码块，无需在 repo 内另找 analog。

## Metadata

**Analog search scope:** `/home/kai/workspace/kais-shot-timeline/`（analysis/ tests/ scripts/ run_pipeline.py spec/schemas/）+ 外部 `/data/workspace/kais-hermes-skills/skills/kais-movie-pipeline/episodes/ep-shencongshenyuan-ep01/assets/P11/h3_batch_render_v4.py`
**Files scanned:** vision_seq_facets.py（743L 全读）、qwen_eye_client.py（349L 全读）、kmc h3_batch_render_v4.py（335L 全读）、run_pipeline.py L740-794（--force 块）、export_asset.py L60-94（双形校验）、test_vision_seq_facets.py L17-161 + 结构 outline、test_qwen_eye_client.py L1-105 + 结构 outline
**Pattern extraction date:** 2026-08-20
