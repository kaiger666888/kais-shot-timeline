# Phase 18: Contract v1.3 - Pattern Map

**Mapped:** 2026-08-19
**Files analyzed:** 8 (1 new schema + 1 new fixture dir + 6 modified)
**Analogs found:** 8 / 8 (all in-codebase — this phase is a near-clone of Phase 11; every mechanism has a verified analog except 4 novel sub-mechanisms listed in §No Analog Found)

> 所有行号基于 2026-08-19 盘上状态核对（RESEARCH 的行号引用已逐一复核，全部一致）。
> 运行时事实已验证：git tags `v1.0`/`v1.1`/`v1.2` 均在；`spec/fixtures/v1.2/shots.json` ids = `[1, 2]`；`.planning/phases/18-contract-v1-3/` 已存在。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `spec/schemas/roundtrip.schema.json` (NEW) | schema (contract artifact) | static contract | `spec/schemas/audio_semantic.schema.json` | exact |
| `spec/schemas/asset.schema.json` (MODIFY) | schema (contract artifact) | static contract | 自身 `data.audio_semantic`/`data.speakers` mount（lines 154-163）+ `generator.warnings`（lines 56-59） | exact (mount) / **novel** (items 加宽) |
| `scripts/export_asset.py` (MODIFY) | producer script (manifest emitter) | file-I/O + conditional emission | 自身 Phase 11 conditional block（lines 320-329）+ `_build_registry_snapshot` WR-05 warn+OMIT（lines 227-243） | exact |
| `spec/fixtures/v1.3/` 13 files (NEW) | test fixture data | static fixture | `spec/fixtures/v1.2/`（12 文件 build pattern） | exact |
| `spec/validate.py` (MODIFY) | validation gate script | batch validation | 自身 V12 tier 三件套（lines 73-98, 181-214, 279-310） | exact |
| `scripts/verify_contract.py` (MODIFY) | cross-version proof harness | batch + transform (schema recovery/filter) | 自身 pass (c)/(d)（lines 428-472）+ `_recover_v11_schema`（lines 326-365） | exact (结构) / **novel** (过滤扩展 + object 特判) |
| `spec/SPEC.md` (MODIFY) | documentation | n/a | 自身 §4 v1.2 changelog entry（lines 173-183）+ §5.8 四块结构（lines 439-501）+ §10（lines 664-723） | exact |
| `spec/README.md` (MODIFY) | documentation | n/a | 自身 v1.2 Update section（lines 80-111）+ footer（line 122） | exact |

**推荐 plan 分组（mirror Phase 11 三 plan 拆分，RESEARCH Summary 锁定）：**
- Plan 01（wave 1）: `roundtrip.schema.json` + `asset.schema.json` + `export_asset.py`（schemas + producer emission）
- Plan 02（wave 2, depends 01）: `spec/fixtures/v1.3/` + `validate.py` + `verify_contract.py`（fixtures + gates + proof）
- Plan 03（wave 2, depends 01）: `SPEC.md` + `spec/README.md`（docs）

---

## Pattern Assignments

### `spec/schemas/roundtrip.schema.json` (schema, static contract)

**Analog:** `spec/schemas/audio_semantic.schema.json`（全文 167 行 —— 完整骨架模板，RESEARCH Code Ex. A 就是它的逐字段改写）

**Header + 顶层形状 pattern**（analog lines 1-16）:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kais.shot-timeline/spec/schemas/audio_semantic.schema.json",
  "draft": "2020-12",
  "title": "音频语义深化（per-shot 三模态 + 分层复现 prompt）",
  "description": "Canonical v1.2 audio sidecar —— ... 严格遵守 v1.0 的 strict-schema × lenient-consumer 原则：schema 校验时 additionalProperties:false 全程生效（...）。v1.2 additive：缺席 on v1.0/v1.1 assets（byte-identical；asset.schema.json#data.audio_semantic 是 OPTIONAL）。",
  "$comment": "Phase-10 spike outcomes（PROJECT.md LOCKED）：(1) ... (2) emotion 是 type:string NOT enum —— ...",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "shots"],
  "properties": {
    "schema_version": {
      "type": "string",
      "pattern": "^(0|[1-9]\\d*)(\\.(0|[1-9]\\d*))?$",
      "description": "Asset contract 版本 semver-lite (major[.minor])，与 asset.json#schema_version 同源。Producer emit '1.2'；pattern 保持宽松（兼容 '1'/'1.1'）。"
    },
```
Roundtrip 版：`$id` 换 roundtrip、title/description 换 v1.3 roundtrip 语义（"Producer emit '1.3'；pattern 宽松兼容 '1'/'1.1'/'1.2'"）。`$comment` 承载决策溯源 —— mirror analog line 7 的编号列表风格（CONTEXT 锁定的 5 条：attribution enum 理由 / midframe_sim 必带 model / judge 无连续分 / shots[] 结果集语义 / fps-seed-workflow 不收）。

**Per-shot「仅 shot_id required」degrade pattern**（analog lines 21-33）:
```json
    "shots": {
      "type": "array",
      "description": "Per-shot 音频语义条目，shot_id 交叉引用 shots.json#id。",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["shot_id"],
        "properties": {
          "shot_id": {
            "type": "integer",
            "minimum": 1,
            "description": "Shot ID（交叉引用 shots.json#id）。仅此字段 required —— 其余全部 optional 以支持 route-down graceful-degrade。"
          },
```

**嵌套子对象全 optional pattern**（analog lines 49-53 —— regen/scores/verdict/status 子对象照此）:
```json
          "dialogue": {
            "type": "object",
            "additionalProperties": false,
            "description": "Per-shot 对话模态（可缺席 —— 非语音 shot 不 emit dialogue 字段）。所有字段 optional ...",
            "properties": {
```

**score/confidence 0..1 + enum 决策判例**（analog lines 63-71 vs 101-105）:
```json
              "emotion": {
                "type": ["string", "null"],
                "description": "Free-string emotion label ... NOT enum —— Phase 10 spike 证实 SenseVoice self_consistency=100% 是 label-stability 代理，NOT 校准精度；闭枚举会越权声称校准。"
              },
```
对照：`judge.attribution` 是我们自有三分类 → **closed enum**（CONTEXT 明确与 emotion free-string 先例不矛盾）；`midframe_sim.score`/`judge.confidence` 用 `{"type":"number","minimum":0,"maximum":1}`（analog line 101-105 score 同款）。

**path pattern 惯例**（来源 `asset.schema.json` lines 174/185 + RESEARCH）：json 文件 `^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$`；媒体（regen.path 是 mp4）mirror 媒体风格 `^(?!.*\\.\\.)([^/]+/)*…\\.mp4$`（anti-traversal 负向前瞻 + 无 drive letter + 扩展名锁定）。

---

### `spec/schemas/asset.schema.json` (schema, static contract) — MODIFY

**Analog A — `data.roundtrip` optional 挂载**：自身 `data.audio_semantic`/`data.speakers`（lines 154-163）:
```json
        "audio_semantic": {
          "type": "string",
          "pattern": "^(?!.*\\.\\.)[^:*?\"<>|]+\\.json$",
          "description": "v1.2 additive (OPTIONAL — 缺席 on v1.0/v1.1 assets). Relative path to audio_semantic.json (...). Emitted only when route-host round-trip succeeded AND the file exists on disk; older assets omit it and still validate (graceful-degrade, CONTRACT-05)."
        },
```
Roundtrip 版 **mirror 挂载模式**（optional、不进 `required[]`——line 116 的 5 keys 不动、description 带 "v1.3 additive (OPTIONAL — 缺席 on v1.0/v1.1/v1.2 assets)" + emission rule），但值形状是 **object `{path, accepted_count, rejected_count}`**（`additionalProperties:false`）——这是 v1.x 第一个 object 值 data.* 挂载（Wrinkle 2，见 §No Analog Found）。`path` 字段内嵌 line 156 同款 json pattern。

**Analog B — `generator.warnings` items 加宽点**：自身 lines 56-59（现状）:
```json
        "warnings": {
          "type": "array",
          "items": { "type": "string" },
          "description": "v1.1 additive (OPTIONAL — Phase 6). Non-fatal warnings ... Operator-facing failure reasons only (exception class + message, route status codes) — no PII, no auth tokens, no body payloads.",
        },
```
v1.3 把 `items` 加宽为 `anyOf: [string, {code enum + detail}]` 双形（RESEARCH Wrinkle 1 给出完整 JSON）。description 保留 "no PII, no auth tokens" 惯例（Security Domain 引用此行）。

---

### `scripts/export_asset.py` (producer script, file-I/O + conditional emission) — MODIFY

**Analog A — `SCHEMA_VERSION` 单源 bump**（自身 lines 51-56）:
```python
# ShotTimelineAsset 契约版本（单一真源）。schema_version pattern 在 spec/schemas/
# asset.schema.json 里保持宽松（接受 "1"/"1.1"/"2.0"），但实际 emit 的字面量在这里锁死。
# v1.2 = 纯增量（新增 optional audio_semantic/speakers 数据文件；emotion/word-level/events
# 字段在 audio_semantic.schema.json）。改这里即改全资产 emit；Pitfall 12（schema 变更后
# 忘 bump 版本号）因此结构上不可能。
SCHEMA_VERSION = "1.2"
```
v1.3：字面量改 `"1.3"` + 注释块同步改写（诚实记录两处非纯新增量：warnings items 加宽 + data.roundtrip object 挂载——对旧数据 additive 但非 property-delta）。

**Analog B — 条件发射块（roundtrip 挂载的直接模板）**（自身 lines 320-329）:
```python
    # Phase 11: CONDITIONAL audio_semantic/speakers emission (CONTRACT-05 graceful-degrade).
    # 仅当 canonical 文件存在才 emit —— route-down degrade / v1.0/v1.1 assets 保持
    # byte-identical（字段 OMITTED；schema optional）。audio_semantic.json 由 Phase 15
    # 路由往返后产出；speakers.json 由 Phase 13 HITL link_speakers 产出。
    audio_semantic_path = os.path.join(work_dir, "audio_semantic.json")
    speakers_path = os.path.join(work_dir, "speakers.json")
    if os.path.isfile(audio_semantic_path):
        data_block["audio_semantic"] = "audio_semantic.json"
    if os.path.isfile(speakers_path):
        data_block["speakers"] = "speakers.json"
```
Roundtrip 版 mirror 结构但值是 object（读 roundtrip.json → 数 `shots[].verdict.decision` → `{"path": "roundtrip.json", "accepted_count": N, "rejected_count": M}`）。**byte-identical-absent 防御**：局部 `data_block` dict（lines 288-298 注释明确「直接 mutate 字面量会让老资产误触空字段」）+ 条件 append，绝不写 `data_block.get("roundtrip")` 类中间操作（Pitfall 4）。

**Analog C — malformed 输入 warn+OMIT**（`_build_registry_snapshot` 自身 lines 232-243）:
```python
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _validate_registry_for_snapshot(schema_path, data, label)
            loaded[key] = _project(data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warn] {label} malformed → registry_snapshot will be OMITTED: {e}")
            return None
```
malformed roundtrip.json → `[warn] roundtrip.json malformed → data.roundtrip will be OMITTED: ...` + 不挂载（mirror WR-05「不持久化可疑统计」；RESEARCH Code Ex. D）。

**Analog D — warnings sidecar 装载加宽点**（自身 main() lines 488-501）:
```python
    warnings_sidecar = os.path.join(work_dir, "route_cache", "warnings.json")
    warnings = None
    if os.path.exists(warnings_sidecar):
        try:
            with open(warnings_sidecar, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                candidate = loaded.get("warnings")
                # 仅接受 list[str]；其它形状（dict / None / 非 str 元素）回退 None。
                if (isinstance(candidate, list)
                        and all(isinstance(w, str) for w in candidate)):
                    warnings = candidate or None  # [] → None（缺省，不 emit）
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warn] route_cache/warnings.json malformed → ignoring: {e}")
```
v1.3 加宽 line 497-498 的 element check：接受 `str` 或 `{"code": <三 enum 之一>, "detail": str}`；非合规整体回退 None（保持 silent-fallback 语义）。下游 emit 点 line 382 `**({"warnings": warnings} if warnings else {})` 不动。

**写盘/自校验不变**：inline `Draft202012Validator`（lines 530）→ 原子写 `tmp + os.replace`（lines 534-537）→ `indent=2, ensure_ascii=False`。

---

### `spec/fixtures/v1.3/` 13 files (test fixture, static) — NEW

**Analog:** `spec/fixtures/v1.2/`（12 文件 = 9 个 v1.1 substrate byte-copied + asset.json 编辑 + 2 新形状；v1.3 同构：**11 个非 asset 文件 byte-copy 自 v1.2** + `asset.json` 编辑 + `roundtrip.json` 新增 = 13 文件）

**asset.json 编辑 pattern**（analog `spec/fixtures/v1.2/asset.json` 全文，关键行）:
```json
  "schema_version": "1.2",
  ...
  "generator": {
    "tool": "kais-shot-timeline",
    "version": "0.3.0-spec-fixture-v1.2",
    "generated_at": "2026-07-24T00:00:00Z",
    "warnings": [
      "preflight route unreachable: ConnectError: [Errno 111] Connection refused",
      "shot 3: route code=500: SHOT_ANALYSIS_DRIVER_FAILED"
    ],
```
v1.3 编辑点：`schema_version: "1.3"`；`generator.version: "0.3.0-spec-fixture-v1.3"` 风格版本串；`warnings` **双形并存**（保留 1 条 legacy string + 增 1+ 条 `{"code": "...", "detail": "..."}` —— SC#4「双形可表达」的证明载体）；`data` 块加 `"roundtrip": {"path": "roundtrip.json", "accepted_count": N, "rejected_count": M}` object。

**roundtrip.json 新形状 pattern**（analog `spec/fixtures/v1.2/audio_semantic.json` 的 2-shot 结构 —— shot 1 全字段 / shot 2 degrade）:
```json
{
  "schema_version": "1.2",
  "word_level_experimental": true,
  "shots": [
    { "shot_id": 1, ... 全字段（dialogue/sfx/reproduction） },
    { "shot_id": 2, ... degrade 中间态（仅 dialogue） }
  ]
}
```
Roundtrip 版按 RESEARCH Open Q1 推荐：shot 1 = full（regen 5-tuple + 双 score + verdict{accepted, auto}）；shot 2 = degrade+human（regen + midframe_sim + verdict{rejected, human, decided_at}）。**硬约束：shot_id ∈ {1, 2}**（v1.2 shots.json substrate 实测 ids=[1,2]，byte-copy 不可改）；其余形状（status.failed、judge 缺席、width/height）走 VERIFICATION 的 direct-validator 实例检查覆盖。

---

### `spec/validate.py` (validation gate, batch) — MODIFY

**Analog:** 自身 V12 tier 三件套 + main 聚合（v1.3 是纯第四阶增量，逐行同构）。

**常量三件套 pattern**（analog lines 73-98）:
```python
# v1.2 fixture set (Phase 11 additive) —— 12 shapes. minimal + v1.1 + v1.2 三阶 gate。
# ...
V12_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.2"
V12_FIXTURE_MAP = {
    # 10 v1.1 entries verbatim (v1.2 fixture reuses the same substrate filenames):
    "asset": "asset.json",
    ...
    # 2 NEW v1.2 shapes:
    "audio_semantic": "audio_semantic.json",
    "speakers": "speakers.json",
}
V12_ORDER = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry", "registry-edits",
    "audio_semantic", "speakers",
]
```
v1.3：`V13_FIXTURE_DIR` / `V13_FIXTURE_MAP`（12 v1.2 entries verbatim + `"roundtrip": "roundtrip.json"`）/ `V13_ORDER = V12_ORDER + ["roundtrip"]`。

**validate_vXX() 函数 pattern**（analog lines 181-214）：循环体与 `validate_v12()` 逐行同构 —— `[FAIL-v13]`/`[valid-v13]` 前缀、`load_validator` + `_format_errors` 复用、返回 failures 计数。docstring 说明「11 个非 asset 文件 byte-copied + asset.json 编辑 + roundtrip.json 新增」。

**退出码聚合 pattern**（analog lines 279-310，关键 lines 293-299）:
```python
    total_strict_failures = minimal_failures + v11_failures + v12_failures
    if args.strict_smoke:
        total_strict_failures += smoke_failures

    print()
    print(
        f"[validate] minimal failures={minimal_failures}, "
        f"v1.1 failures={v11_failures}, "
        f"v1.2 failures={v12_failures}, "
        f"smoke failures={smoke_failures} "
```
v1.3：加 `v13_failures = validate_v13()` + 聚合式 + 汇总行加 `v1.3 failures=` 段。

---

### `scripts/verify_contract.py` (cross-version proof harness, batch + transform) — MODIFY

**Analog A — schema recovery（`_recover_v12_schema` 模板）**：自身 `_recover_v11_schema`（lines 326-365）:
```python
def _recover_v11_schema(shape: str):
    """恢复 v1.1 schema 用于 backward cross-version check v1.2→v1.1 (Phase 11 CONTRACT-03)。

    Primary: ``git show v1.1:spec/schemas/<shape>.schema.json`` —— v1.1 git tag
    的 immutable truth。Fallback（tag 缺失 / git 不可用，e.g. CI shallow clone）:
    程序化剥离 v1.2 additive keys —— deep-copy 当前（v1.2-extended）schema，
    ...
    # Primary: git show v1.1 tag
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "show", f"v1.1:spec/schemas/{shape}.schema.json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    # Fallback: programmatic strip of v1.2-additive keys from current schema
    import copy
    ...
    if shape == "asset":
        data_props = stripped.get("properties", {}).get("data", {}).get("properties", {})
        for k in ("audio_semantic", "speakers"):
            data_props.pop(k, None)
    return stripped
```
`_recover_v12_schema`：tag 换 `v1.2`（已验证 `git show v1.2:spec/schemas/asset.schema.json` 可用）；strip fallback **除 pop `data.properties.roundtrip` 外，必须还原 `generator.properties.warnings.items = {"type": "string"}`**（首个非 property-delta —— Wrinkle 1 连锁 3）。

**Analog B — pass (e)/(f) 结构模板**：自身 pass (c)/(d)（lines 428-472）:
```python
    # (c) Phase 11 FORWARD v1.1→v1.2: v1.1 fixture × current (v1.2-extended) schemas → 0 errors
    # Only asset — speakers/audio_semantic are NEW shapes with no v1.1 instance to test.
    for shape in ("asset",):
        try:
            schema = json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
            instance = json.loads((v11_dir / f"{shape}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            failures.append(f"forward v1.1→v1.2 {shape}: load failed: {e}")
            continue
        errs = list(Draft202012Validator(schema).iter_errors(instance))
        if errs:
            failures.append(
                f"forward v1.1→v1.2 {shape}: v1.1 fixture rejected by v1.2 schema "
                f"with {len(errs)} error(s); first: {errs[0].message}"
            )

    # (d) Phase 11 BACKWARD v1.2→v1.1: v1.2 fixture × recovered-v1.1 schema → ONLY additionalProperties errors
    v12_dir = REPO / "spec" / "fixtures" / "v1.2"
    for shape in ("asset",):
        v11_schema = _recover_v11_schema(shape)
        ...
        errs = list(Draft202012Validator(v11_schema).iter_errors(instance))
        non_addprop = [e for e in errs if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(
                f"backward v1.2→v1.1 {shape}: {len(non_addprop)} non-additionalProperties "
                f"error(s) (shared fields drifted); first: {non_addprop[0].message}"
            )
```
Pass (e) forward v1.2→v1.3 逐行 mirror (c)（仅 asset；roundtrip 是全新形状无旧实例）。Pass (f) backward v1.3→v1.2 mirror (d) 结构，**但 line 467 的过滤规则必须扩展**（见 §No Analog Found #1）。最终汇总行（lines 475-480）话术更新为四向 `v1.0↔v1.1↔v1.2↔v1.3` + backward 话术诚实化「(excluding documented v1.3 deltas: data.roundtrip + warnings items widening)」。

**Analog C — fixture 一致性块模板**：自身 v1.2 speakers 块（`_fixture_consistency_check` lines 578-632）:
```python
    v12_fix_dir = REPO / "spec" / "fixtures" / "v1.2"
    if v12_fix_dir.is_dir():
        spk_path = v12_fix_dir / "speakers.json"
        if spk_path.is_file():
            try:
                speakers_data = json.loads(spk_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                failures.append(f"v1.2 speakers.json: invalid JSON: {e}")
                speakers_data = None
            if isinstance(speakers_data, dict):
                # ... 加载同目录 shots.json ids → 逐条 turn.shot_id ⊆ shots ids
                for turn in spk.get("turns", []) or []:
                    if turn.get("shot_id") not in shot_ids_for_speakers:
                        failures.append(
                            f"v1.2 speakers.json {sid}: turn shot_id "
                            f"{turn.get('shot_id')} unknown"
                        )
```
v1.3 mirror 一块（gated on `spec/fixtures/v1.3/` is_dir）：roundtrip.shots[].shot_id ⊆ v1.3 fixture shots.json ids（source-of-truth 用 v1.3 目录自己的 shots.json —— mirror lines 603-615 的 WR-01 教训，勿复用 v1.1 ids）。末尾成功话术（line 639）加 v1.3 段。

**Analog D — EIGHT_SHAPES 追加**（自身 lines 82-89）:
```python
EIGHT_SHAPES = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry",
    # Phase 11 additive: audio_semantic + speakers (gated on data.<shape> existence,
    # mirror v1.1 characters/props pattern in validate_eight_shapes).
    "audio_semantic", "speakers",
]
```
追加 `"roundtrip"` + 注释（Phase 18 additive, gated on data.roundtrip existence）——**必须与 validate_eight_shapes 的 object 特判同 plan 落地**（Wrinkle 2，见 §No Analog Found #2），否则 Phase 20 producer 挂载即误报。

---

### `spec/SPEC.md` (documentation) — MODIFY

**Analog A — §1 schema 表**（lines 18, 23-38）：「13 份」→「14 份」+ 表尾加 roundtrip 行（mirror line 36-38 audio_semantic/speakers 行的一句话概述风格 + `**`1.3`**` 版本标记）。

**Analog B — §4 Changelog 条目**（v1.2 entry, lines 173-183 —— 六段结构：日期—版本—纯增量声明 / 新 schema / asset.schema additive / pattern 不变+单源位置 / phase-informed deviations / 向后兼容证据）:
```markdown
- **2026-07-25 — `1.2`(v1.2 additive extension,Phases 10-17)** — 第二个 minor bump,纯增量(...)。变更:
  - **3 个新 schema**:`audio_semantic.schema.json`(...)、...
  - **`asset.schema.json` additive**:新增 optional `data.audio_semantic` / `data.speakers`(JSON 路径)。`required[]` 与 v1.0/v1.1 byte-identical(仍 5 keys)。
  - **`schema_version` pattern 不变**(...)— 版本字面量锁在 producer 单一真源 `scripts/export_asset.py:SCHEMA_VERSION = "1.2"`(line 55),非 schema `const`(...)。
  - **Phase-10-informed deviations**(NON-NEGOTIABLE,empirical basis): ...
  - **向后兼容**:`spec/fixtures/minimal/`(v1)仍 6/6 绿;...;`scripts/verify_contract.py` `_cross_version_check` 实测三向兼容(...)。
```
v1.3 条目 mirror 此结构，**且必须诚实记录两处非纯新增量**（warnings items 加宽 + object 挂载——对旧数据 additive 但非 property-delta）。v1.2 entry 里的 Phase-10 deviations 段对应 v1.3 的「CONTEXT-locked decisions」段（attribution enum / midframe model 标识 / judge 无连续分 / shots[] 结果集语义）。

**Analog C — §5 形状文档四块结构**（§5.8 Audio Semantic, lines 439-501）：
1. `**Producer:**` / `**Consumers:**` 行（lines 441-442；roundtrip: Producer = Phase 20/21, Consumers = Phase 22 HTML gallery / dataset 导出 —— 均 pending，mirror v1.2 当时的 pending 措辞如 line 380）
2. `**顶层形状:**` 段（line 443）
3. 字段表 `| Field | Type | Required | Notes |`（lines 445-466；enum 值逐字对齐 schema，如 lines 241-248 dominant_type enum 表）
4. `**最小片段**`（摘自 fixture，lines 476-499）+ `Reference schema:` 行（line 501）

新 §5.10 Round-trip + §5 引言 blockquote（lines 191-193 风格）追加 v1.3 说明。

**Analog D — §10 Fidelity Disclaimer**（lines 664-723）：v1.3 三层 disclaimer mirror §10 的分层结构 + **AF-01 禁语 invariant 延续**（lines 674：绝对化复现措辞 FORBIDDEN，grep 守门 0 匹配 —— Plan 03 must-haves 必含，mirror 11-03 先例）。

**Analog E — 文末 footer**（lines 726-728）:
```markdown
*Created: 2026-07-20 (Phase 01 Plan 02 — initial publication ...).*
* schema_version "1" — initial contract. ...*
* 2026-07-25 (Phase 11 Plan 03 — v1.2 additive extension: §4 Changelog `1.2` + §5.8 Audio Semantic + §5.9 Speakers + §10 Fidelity Disclaimer). schema_version "1.2".*
```
追加 v1.3 行。头部 line 3 的 Version 行 + line 6 Status 行同步更新。

---

### `spec/README.md` (documentation) — MODIFY

**Analog:** 自身 v1.2 Update section（lines 80-111）+ footer（lines 121-122）。v1.3 section mirror：`## v1.3 Update (Phase 18, <date>)` + 新 schema 描述 + asset.schema additive（诚实记录 items 加宽/object 挂载）+ SCHEMA_VERSION 单源位置（注意 v1.2 section line 92 写的是 `line 55`，v1.3 时实际是 line 56 —— **引用行号前先 grep 复核**）+ 13-file fixture 描述 + 双向证明话术。footer 追加 `*Updated: ... (Phase 18 — v1.3 additive extension: ...)*`。Layout 图（lines 9-47）加 roundtrip.schema.json + fixtures/v1.3/ 行，计数 13→14。

---

## Shared Patterns

### Strict-schema × additive-only × lenient-consumer
**Source:** `spec/schemas/asset.schema.json` line 7 `$comment` + line 15 schema_version description
**Apply to:** `roundtrip.schema.json` 每一层嵌套 object + asset.schema.json 两个编辑点
```json
"$comment": "Graceful-degrade rule (SPEC-02 / CONTEXT D-02): The schema is intentionally strict (additionalProperties: false on every object). Strictness at validation time is what forces explicit version bumps. The CONSUMER, however, must be lenient at RUNTIME: ... New field = minor version bump (old consumers degrade gracefully). ..."
```
铁律：`additionalProperties:false` 全程；新字段只进 properties 绝不进 required[]；`data.required` 保持 5 keys 不动（asset.schema.json line 116）。

### 版本字面量单源（Pitfall 12 防御）
**Source:** `scripts/export_asset.py:56` `SCHEMA_VERSION = "1.2"`
**Apply to:** 唯一 bump 点；schema pattern 保持宽松 `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`（schema 用 const 会拒绝 minimal fixture 的 "1"，破坏 CONTRACT-09）。VERIFICATION 固定两条 grep：`= "1.3"` 恰 1 处、`= ` 恰 1 处。

### byte-identical-absent 条件发射
**Source:** `scripts/export_asset.py` lines 288-298（局部 dict 组装注释）+ lines 320-329（Phase 11 条件块）
**Apply to:** export_asset.py 的 roundtrip 挂载
```python
    # Phase 7: 把 data + media 块先建成局部 dict，再条件性 append characters/props
    # （CONTRACT-06 closure）。直接 mutate 字面量会让老资产在 "无 registry" 分支
    # 仍可能携带空 characters/props 字段（一旦 .get("characters") 之类的中间操作
    # 误触）；局部 dict + 组装时再决定是否赋值，保证「文件缺席 → 字段缺席」byte-identical。
```
红线证明框架（照抄 Phase 11 VERIFICATION SC#2 语义，勿发明全文件 diff）：SCHEMA_VERSION grep + synthetic producer smoke（仅 5 required JSON 的 work_dir → data keys == 5 + warnings 缺省）+ files-present smoke + 11 文件 `diff -r` v1.2 clean。

### graceful-degrade warn+OMIT（malformed 侧车输入）
**Source:** `scripts/export_asset.py` lines 237-243（WR-05）+ lines 488-501（sidecar best-effort）
**Apply to:** roundtrip.json malformed 处理 + warnings sidecar 装载加宽 —— `[warn]` 打印 + 字段 OMIT / 整体回退 None，绝不 sys.exit（producer 路径 fail-soft；对照 consumer 路径 `validate_asset_json` lines 134-139 的 sys.exit fail-loud）。

### 排序错误输出 + fail 计数
**Source:** `spec/validate.py` `_format_errors`（lines 109-115）+ `verify_contract.py` line 204-208
**Apply to:** 所有新校验路径
```python
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
```

### CLI/文档语言惯例
**Source:** CLAUDE.md Conventions 段
**Apply to:** 所有 .py 修改（中文 docstring/注释、bracketed-tag print `[valid-v13]`/`[warn]`、UPPER_CASE 常量、4-space 缩进）+ schema description 中文行文（CONTEXT discretion）+ JSON 写出 `indent=2, ensure_ascii=False`。

---

## No Analog Found

代码库无先例、planner 必须按 RESEARCH 设计落地的子机制（均为本 phase 与 Phase 11 的真实差异）：

| # | 子机制 | 所在文件 | Reason | 设计来源 |
|---|--------|----------|--------|----------|
| 1 | backward pass (f) 过滤规则扩展：`e.validator == "additionalProperties"` OR（`e.validator in ("type","anyOf")` 且 `e.absolute_path[:2] == ("generator","warnings")`）——首个 items 类型加宽产生的 `type` 错误需豁免，其余仍算 shared-field drift | `scripts/verify_contract.py` | v1.1/v1.2 delta 全是新 optional property（additionalProperties 错误天然豁免）；items 加宽是第一例非 property-delta | RESEARCH §Wrinkle 1 + Code Ex. C；**必须配负测试**（注入真 drift 如 `asset_type:"other"` 须仍 FAIL —— A3） |
| 2 | `validate_eight_shapes` 的 object 值特判：EIGHT_SHAPES 加 `"roundtrip"` 后，lines 253-261 的 `isinstance(rel, str)` 假设需特判取 `rel.get("path")` | `scripts/verify_contract.py` lines 253-261 | v1.x 历史 data.* 挂载全是 string；data.roundtrip 是第一个 object 挂载 | RESEARCH §Wrinkle 2；与 EIGHT_SHAPES 追加同 plan（勿做一半，A5） |
| 3 | `generator.warnings.items` 的 `anyOf: [string, {code enum, detail}]` 双形 | `spec/schemas/asset.schema.json` lines 56-59 | 首次对既有字段的 items 类型加宽 | RESEARCH §Wrinkle 1（完整 JSON 已给出）；required=["code"] detail optional 为推荐值（A2） |
| 4 | `data.roundtrip` object 挂载（file ref + accepted/rejected 统计）+ producer 计数逻辑 | `spec/schemas/asset.schema.json` + `scripts/export_asset.py` | 首个 object 值 data.* 挂载；audio_semantic 挂载是 string 不可直接照抄值形状 | RESEARCH §Wrinkle 2 + Code Ex. D；字段名 `path/accepted_count/rejected_count` 为推荐值（A1） |

---

## Metadata

**Analog search scope:** `spec/schemas/`（13 schema 全目录）、`spec/fixtures/{minimal,v1.1,v1.2}/`、`spec/validate.py`、`spec/SPEC.md`、`spec/README.md`、`scripts/{export_asset,verify_contract}.py`、`CLAUDE.md`（conventions 段）
**Files scanned:** 11 个源文件全文读取（全部 < 2,000 行）+ runtime 验证（git tags、fixture shots ids、phase dir 存在性）
**早期停止说明:** 本 phase 是 Phase 11 近克隆，全部 analog 在 RESEARCH 已逐行核对；未额外扫描 analysis/ html/ registry/ 生产者目录（phase 边界明确排除生产者代码）
**Pattern extraction date:** 2026-08-19
