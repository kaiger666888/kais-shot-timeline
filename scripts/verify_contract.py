#!/usr/bin/env python3
"""Phase 4 跨仓库契约验证 harness —— 抓 producer / consumer 两端漂移。

背景：v1.0 milestone 的核心价值是「两仓库（kais-shot-timeline = producer /
contract authority；kais-aigc-platform @kais/infinite-canvas = consumer）
独立演进，契约对齐有回归保护」。本 harness 是这张回归网 —— 单一 canonical
home（spec owner 一侧），三种 mode 覆盖两个漂移方向。

三种 mode（e2e 在 Plan 04-02 补完，本 plan 只占位）：
  producer  —— 对真实 ep01 asset 跑 6-schema inline jsonschema 校验
              （Draft202012Validator，绝不 subprocess 到 spec/validate.py ——
               其 SMOKE_SHAPES spec/validate.py:49 显式排除 asset shape，
               subprocess 会让无效 manifest 悄悄通过）
  consumer  —— subprocess shell-out 到 Phase 3 worktree 的
               verify-canvas-shot-timeline.ts（17 asserts A-F + E2 抓
               consumer importer 漂移）
  e2e       —— HTTP-level 端到端：起 Express backend → POST
               /api/canvas/v2/import-from-dir → SQL 直查 o_agentWorkData
               snapshot → 结构断言。Plan 04-02 实现。

opt-in 环境变量：
  PHASE4_RE_EXPORT=1     重导 asset.json（抓「今天 producer 还能产 valid asset」，
                          否则用既有 ep01 产物）
  PHASE4_SELF_TEST=1     self-test：注入 schema_version='v1' 故意漂移，
                          断言 harness fail-loud（Plan 04-01 Task 2 落地）
  PHASE4_RUN_E2E=1       启用 e2e mode（04-02 才会真正起作用）
  PHASE4_ASSET_DIR       producer/self-test/e2e 共用的 asset 目录（默认 ep01）。
                          WR-07：旧名 PHASE4_E2E_ASSET_DIR 仍向后兼容。

用法：
    python3 scripts/verify_contract.py --mode=producer
    python3 scripts/verify_contract.py --mode=consumer
    python3 scripts/verify_contract.py                  # 默认 --mode=all
    PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer
    CANVAS_CONSUMER_PATH=/path/to/worktree python3 scripts/verify_contract.py --mode=consumer

退出码：
    0 = 选中的 mode 全绿
    1 = 任一 mode fail（schema-invalid / subprocess rc≠0 / guard 拒绝）
"""
import argparse
import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator


# === 路径常量 ============================================================
# scripts/verify_contract.py → repo root（定位 spec/schemas/ + scripts/export_asset.py）
REPO = Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"

# cross-repo worktree 默认路径（CONTEXT 锁：feat/canvas-asset-collection 分支）
DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"

# e2e / producer mode 默认输入：真实 ep01 asset dir
# （CONTEXT 锁：用既有 ep01，避免 GPU/Whisper 重跑；ep03 cache 被 Phase 2 测试破坏过）
DEFAULT_E01_ASSET_DIR = (
    REPO / "output"
    / "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)

# v1.2 producer-mode recognized schema shapes (12 = v1.0 的 6 个 + v1.1 Phase 5 新增
# characters/props/registry + Phase 7 registry-edits 隐式走 registry-edits.schema.json
# 路径（不在 EIGHT_SHAPES 因 producer asset_dir 不 emit registry.edits.json —— 那是
# HITL 审阅 round-trip 中间产物）+ Phase 11 v1.2 新增 audio_semantic/speakers)。
# 名字保留 EIGHT_SHAPES（v1.0 历史叫法）以兼容既有 fail-loud self-test 文档引用；
# 实际是 11 个元素。SIX_SHAPES 别名 = 前 6 个（v1.0 producer-only asset 始终是这 6 个
# required 形状；characters/props/registry/audio_semantic/speakers 全是 optional ——
# absent 不算失败，mirror graceful-degrade）。
EIGHT_SHAPES = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry",
    # Phase 11 additive: audio_semantic + speakers (gated on data.<shape> existence,
    # mirror v1.1 characters/props pattern in validate_eight_shapes).
    "audio_semantic", "speakers",
]
SIX_SHAPES = EIGHT_SHAPES[:6]  # v1.0 backward-compat alias


# === 04-02 预定义 helper ================================================
# 本 plan（04-01）不用 find_free_port；预定义避免 04-02 e2e mode 需要回头改本文件。
def find_free_port() -> int:
    """让内核分配一个空闲 ephemeral 端口（bind 127.0.0.1:0 后读 getsockname）。

    模板源：scripts/check_range.py:32-36（Phase 2 server-lifecycle）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# === e2e helpers (Plan 04-02) ===========================================
def _poll_health(
    port: int, proc: subprocess.Popen, timeout: float = 45.0
) -> tuple:
    """轮询 http://127.0.0.1:{port}/health 直到 200 或超时。

    模板源：scripts/check_range.py:39-48 wait_ready 的 HTTP 版；04-RESEARCH.md
    §Pattern 2。timeout 默认 45s（consumer Express + better-sqlite3 boot 比
    scripts/serve.py 慢，src/app.ts:269 在 server.listen 前 await bootReady）。

    WR-01：每轮先看 proc.poll() —— backend 启动期崩溃（TS 编译错 / 缺
    better-sqlite3 / 端口占用）不再空耗 45s，立刻 fail-fast 返回带 exit code
    的可读原因。返回 tuple[bool, str] 让 caller 直接 embed reason。
    WR-02：异常覆盖从 urllib.error.URLError 扩到 (URLError, OSError,
    http.client.HTTPException) —— 半启动 Express 可能发畸形 HTTP 头触发
    HTTPException / ConnectionResetError（非 URLError 子类），不再逃出循环
    把 e2e 整体崩成 traceback。
    """
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        # WR-01：backend 进程已死就别再轮询 45s
        rc = proc.poll()
        if rc is not None:
            return (False, f"backend died before /health (exit code={rc})")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return (True, "ready")
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass
        time.sleep(0.5)
    return (False, f"backend /health 未在 {timeout:g}s 内 ready（port {port}）")


def _read_persisted_snapshot(db_path: str, project_id: int, episodes_id: int):
    """直查 consumer worktree data/db2.sqlite 的 o_agentWorkData snapshot。

    Pitfall 1 关键决策（04-RESEARCH.md §Pitfall 1）：绝不用
    /api/canvas/v2/load-v2 做 read-back —— 它读 relational canvas_nodes 表
    （import-from-dir 不写），返 null。o_agentWorkData JSON blob snapshot 是
    唯一非侵入路径。Phase 3 leftover (9001/9001, ~290KB) 验证此路径。

    T-04-01-T2 mitigation: sqlite3 占位符 `?` 参数化，绝不字符串拼接。
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM o_agentWorkData "
            "WHERE projectId = ? AND episodesId = ? AND key = 'canvasGraph'",
            (str(project_id), str(episodes_id)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])
    finally:
        conn.close()


# === producer-side helpers ==============================================
def _resolve_canonical_video(asset_dir: Path) -> str:
    """返回 video.mp4 symlink 的 target（或非 symlink 时直接绝对路径）。

    背景：Phase 2 决定 video.mp4 是 symlink，target = --video abs path（原始
    含 audio 流的视频，非 -an 转 h264.mp4）。PHASE4_RE_EXPORT=1 重导时需要
    把原始路径传给 export_asset.py。

    WR-04 修复：os.readlink 返回 symlink 字面 target —— 若 target 是相对路径
    （如 ``../../originals/ep01.mp4``，常见于 asset 目录与源 cache 同级布局），
    原实现直接 return 该相对串，后续 export_asset.py 会按 Python 进程 CWD
    （通常是 kais-shot-timeline/）解析，而非按 asset_dir —— 要么 "input video
    not found"，要么误中 CWD-relative 同名文件。改成始终返回绝对路径：相对
    target 相对 asset_dir 解析，绝对 target 也走一遍 realpath 规整掉 ``..``。
    """
    video_link = asset_dir / "video.mp4"
    if video_link.is_symlink():
        target = os.readlink(video_link)
        if not os.path.isabs(target):
            target = str((asset_dir / target).resolve())
        else:
            target = os.path.realpath(target)
        return target
    return str(video_link)


def validate_asset_json(asset_path) -> list:
    """对单份 asset.json 跑 spec/schemas/asset.schema.json 校验，返回 errors 列表。

    与 scripts/export_asset.py:106-127 的 inline validator 同源 —— 但 RETURN
    errors list（不 sys.exit），让 harness 收集后统一报告 + 让 self-test
    断言数量。模板源：scripts/export_asset.py L106-127；sort key 沿用项目惯例。

    绝不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES（spec/validate.py:49）
    显式排除 asset shape，subprocess 会让无效 manifest 悄悄通过。
    """
    asset_path = Path(asset_path)
    schema = json.loads((SCHEMAS_DIR / "asset.schema.json").read_text(encoding="utf-8"))
    instance = json.loads(asset_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )
    return errors


def validate_eight_shapes(asset_dir: Path, manifest: dict) -> list:
    """对 asset + 5 required data shapes + 3 v1.1 optional shapes 跑 schema 校验。

    v1.0 的 6 个 shape（asset/shots/audio_analysis/transcript/frames/prompts）始终
    required；v1.1 新增的 characters/props/registry 全是 OPTIONAL —— absent 不算失败
    （graceful-degrade，镜像 v1.0 哲学）。characters/props 在 asset.json#data 里
    （manifest["data"]["characters"] 等）；registry.draft.json 是 pipeline-internal
    工作产物，不在 asset.json#data，按 canonical 文件名直接查 asset 目录。

    模板源：spec/validate.py L52-94（_format_errors + sorted iter_errors 模式）。
    每个 shape 失败时只记第一条错误（actionable + 不刷屏）；self-test / 深度
    debug 走 validate_asset_json 拿完整列表。

    CR-01 修复：manifest 缺 data 字段或 data.<shape> 非字符串时不能抛
    KeyError/TypeError —— 那会把 harness 自身崩溃成 traceback，掩盖本该
    干净报告的 "asset: 'data' is a required" schema 错误。改用 .get() 链 +
    类型守护，让 asset-shape iter 负责报 missing-required，data 侧只记录
    「键存在但类型错」这一类 schema 抓不到的漂移。
    """
    failures = []
    # CR-01：data 缺失/类型错时退化成空 dict；asset-shape iter 会报
    # "data is a required property"，无需在 data 循环里再炸 KeyError。
    data_field = manifest.get("data") if isinstance(manifest, dict) else None
    if not isinstance(data_field, dict):
        data_field = {}
    for shape in EIGHT_SHAPES:
        schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if shape == "registry":
            # registry.draft.json 不在 asset.json#data（pipeline-internal 工作产物）；
            # 按 canonical 文件名直接查。absent → skip（v1.0 asset 没有 registry）。
            reg_path = asset_dir / "registry.draft.json"
            if not reg_path.is_file():
                continue
            try:
                instance = json.loads(reg_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                failures.append(f"registry: invalid JSON in {reg_path}: {e}")
                continue
        elif shape == "asset":
            instance = manifest
        else:
            rel = data_field.get(shape)
            if not isinstance(rel, str):
                # data.<shape> 缺失：由 asset-shape iter 报 "data is required"，
                # 不重复记录；只有「键存在但值非字符串」（schema 抓不到）才 flag。
                # v1.1 optional shapes（characters/props）absent 时走这里 continue。
                if shape not in data_field:
                    continue
                failures.append(f"{shape}: data.{shape} is not a string: {rel!r}")
                continue
            instance_path = asset_dir / rel
            try:
                instance = json.loads(instance_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                failures.append(f"{shape}: data file missing at {instance_path}")
                continue
            except json.JSONDecodeError as e:
                failures.append(f"{shape}: invalid JSON in {instance_path}: {e}")
                continue
        errs = sorted(
            Draft202012Validator(schema).iter_errors(instance),
            key=lambda e: list(e.absolute_path),
        )
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            failures.append(f"{shape} at /{loc}: {errs[0].message}")
    return failures


# === v1.1 contract-level checks (Phase 5) ==============================
def _recover_v1_schema(shape: str):
    """恢复 v1.0 schema 用于 backward cross-version check（CONTRACT-07）。

    Primary: ``git show v1.0:spec/schemas/<shape>.schema.json`` —— 最真实。
    Fallback（tag 缺失 / git 不可用）: 程序化剥离 —— deep-copy v1.1 schema，
    删除 v1.1 Phase 5 已知的 additive keys，得到等价的 v1 schema。两路径任一
    成功即返回 dict；都失败返回 None（caller 记 failure）。

    已知 v1.1 additive keys（CONTRACT-04/05，全 optional，绝不在 required[]）:
      asset:    data.properties.characters, data.properties.props,
                media.properties.characters, media.properties.props
      prompts:  items.properties.character_refs, items.properties.prop_refs
    """
    # Primary: git show v1.0 tag
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "show", f"v1.0:spec/schemas/{shape}.schema.json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    # Fallback: programmatic strip of known-added keys
    import copy
    try:
        stripped = copy.deepcopy(
            json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if shape == "asset":
        data_props = stripped.get("properties", {}).get("data", {}).get("properties", {})
        media_props = stripped.get("properties", {}).get("media", {}).get("properties", {})
        for k in ("characters", "props"):
            data_props.pop(k, None)
            media_props.pop(k, None)
    elif shape == "prompts":
        item_props = stripped.get("items", {}).get("properties", {})
        for k in ("character_refs", "prop_refs"):
            item_props.pop(k, None)
    return stripped


def _recover_v11_schema(shape: str):
    """恢复 v1.1 schema 用于 backward cross-version check v1.2→v1.1 (Phase 11 CONTRACT-03)。

    Primary: ``git show v1.1:spec/schemas/<shape>.schema.json`` —— v1.1 git tag
    的 immutable truth。Fallback（tag 缺失 / git 不可用，e.g. CI shallow clone）:
    程序化剥离 v1.2 additive keys —— deep-copy 当前（v1.2-extended）schema，
    删除 Phase 11 已知的 additive keys，得到等价的 v1.1 schema。两路径任一
    成功即返回 dict；都失败返回 None（caller 记 failure）。

    已知 v1.2 additive keys（CONTRACT-04/05，全 optional，绝不在 required[]）:
      asset:    data.properties.audio_semantic, data.properties.speakers
                （v1.2 没有 media.* additions；只有 data.*）

    与 _recover_v1_schema 的关系：v1 recover 剥离 v1.1 additions
    （characters/props），v1.1 recover 剥离 v1.2 additions（audio_semantic/speakers）。
    一致用 fallback 模式：deep-copy current → pop additive keys。
    """
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
    try:
        stripped = copy.deepcopy(
            json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if shape == "asset":
        data_props = stripped.get("properties", {}).get("data", {}).get("properties", {})
        for k in ("audio_semantic", "speakers"):
            data_props.pop(k, None)
    return stripped


def _cross_version_check() -> tuple:
    """schema-layer 双向 v1↔v1.1 兼容证明（CONTRACT-07；CONTEXT D-XX lock）。

    (a) FORWARD: spec/fixtures/minimal（v1）对 *当前 v1.1 已扩展* schema 校验 →
        必须 0 errors。证明 additive 扩展没破坏老资产（Pitfall 11 prevented）。
    (b) BACKWARD: spec/fixtures/v1.1（v1.1）对 v1 schema（_recover_v1_schema）
        校验 → 仅 additionalProperties errors（v1.1 新增 optional 字段触发），
        过滤掉后必须 0 errors。证明共享字段类型对齐，唯一 delta 是新增 optional
        字段 —— 这就是 "ignored-not-crashed" 的 schema-layer 实现（RESEARCH
        Pattern 7 实测：filter 后 0 error）。

    真实 TS consumer 的 runtime warn 行为由 Phase 9 验证 —— 本检查不 stub 假
    Python consumer（CONTEXT 锁）。registry/characters/props 是 v1.1 全新形状，
    无 v1 instance，故 forward 只跑 6 个 v1.0 形状；backward 只跑被 *扩展* 的
    asset + prompts（全新形状无 v1 schema 可对）。
    """
    failures = []
    minimal_dir = REPO / "spec" / "fixtures" / "minimal"
    v11_dir = REPO / "spec" / "fixtures" / "v1.1"

    # (a) FORWARD: v1 minimal fixture vs current (v1.1-extended) schemas
    forward_shapes = SIX_SHAPES  # the 6 v1.0 shapes
    for shape in forward_shapes:
        try:
            schema = json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
            instance = json.loads((minimal_dir / f"{shape}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            failures.append(f"forward {shape}: could not load schema/fixture: {e}")
            continue
        errs = list(Draft202012Validator(schema).iter_errors(instance))
        if errs:
            failures.append(
                f"forward {shape}: v1 fixture rejected by v1.1 schema with "
                f"{len(errs)} error(s); first: {errs[0].message}"
            )

    # (b) BACKWARD: v1.1 fixture vs recovered v1 schemas
    for shape in ("asset", "prompts"):
        v1_schema = _recover_v1_schema(shape)
        if v1_schema is None:
            failures.append(
                f"backward {shape}: could not recover v1 schema "
                f"(git show v1.0 + programmatic strip both failed)"
            )
            continue
        try:
            instance = json.loads((v11_dir / f"{shape}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            failures.append(f"backward {shape}: could not load v1.1 fixture: {e}")
            continue
        errs = list(Draft202012Validator(v1_schema).iter_errors(instance))
        # additionalProperties errors are EXPECTED (v1.1 added optional fields);
        # the invariant is that NO OTHER error type remains (shared fields aligned).
        non_addprop = [e for e in errs if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(
                f"backward {shape}: {len(non_addprop)} non-additionalProperties "
                f"error(s) (shared fields drifted); first: {non_addprop[0].message}"
            )

    # (c) Phase 11 FORWARD v1.1→v1.2: v1.1 fixture × current (v1.2-extended) schemas → 0 errors
    # Only asset — speakers/audio_semantic are NEW shapes with no v1.1 instance to test.
    # The 6 v1.0 shapes + characters/props/registry are byte-identical to v1.1 schemas
    # (Phase 11 doesn't touch them); already covered by pass (a) for minimal→current.
    # Only asset.schema.json got additive extension in Phase 11.
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
    # Proves no breaking change to shared fields. The v1.2 fixture's only deltas vs a
    # hypothetical v1.1 fixture should be the 2 new additive keys in asset.data
    # (audio_semantic + speakers) — which v1.1's additionalProperties:false correctly
    # rejects. Any OTHER error type = shared-field drift (breaking change).
    v12_dir = REPO / "spec" / "fixtures" / "v1.2"
    for shape in ("asset",):
        v11_schema = _recover_v11_schema(shape)
        if v11_schema is None:
            failures.append(
                f"backward v1.2→v1.1 {shape}: could not recover v1.1 schema "
                f"(git show v1.1 + programmatic strip both failed)"
            )
            continue
        try:
            instance = json.loads((v12_dir / f"{shape}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            failures.append(f"backward v1.2→v1.1 {shape}: load failed: {e}")
            continue
        errs = list(Draft202012Validator(v11_schema).iter_errors(instance))
        non_addprop = [e for e in errs if e.validator != "additionalProperties"]
        if non_addprop:
            failures.append(
                f"backward v1.2→v1.1 {shape}: {len(non_addprop)} non-additionalProperties "
                f"error(s) (shared fields drifted); first: {non_addprop[0].message}"
            )

    if failures:
        return (False, "v1.0↔v1.1↔v1.2 cross-version drift: " + "; ".join(failures))
    return (
        True,
        "v1.0↔v1.1↔v1.2 cross-version bidirectional compat proven "
        "(forward 0 errors; backward 0 non-additive errors)",
    )


def _fixture_consistency_check() -> tuple:
    """v1.1 fixture 自洽性检查（Pitfall C / 17 prevention）。

    验证 spec/fixtures/v1.1/ 跨文件 ID 一致性（"fixtures we ship don't ship broken"）：
      - prompts.character_refs[]  ⊆ characters[].id
      - prompts.prop_refs[]       ⊆ props[].id
      - characters.appearance_shots[] + looks[].appearance_shots[]  ⊆ shots[].id
      - props.appearance_shots[] + states[].appearance_shots[]      ⊆ shots[].id
      - registry clusters[].cluster_id 匹配 (char|prop)_[0-9]{3} 且（非 rejected 时）⊆ characters+props IDs
      - registry clusters[].members[].shot_id ⊆ shots[].id

    Robustness：v1.1 目录缺失 / 任一 list-rooted fixture 缺失或非 array → fail-loud
    （不静默返回 "0 dangling"）。registry.draft.json 是 optional —— 缺失只 skip。
    与 Phase 8 PROMPT-03（producer-emitted 完整 integrity check）区分。
    """
    import re
    v11 = REPO / "spec" / "fixtures" / "v1.1"
    failures = []

    if not v11.is_dir():
        return (False, f"v1.1 fixture dir missing: {v11} (fixture set incomplete)")

    def _load_list(name):
        """加载一个 list-rooted fixture;missing / 非 list / 坏 JSON → 记 failure 返 None。"""
        p = v11 / name
        if not p.is_file():
            failures.append(f"fixture missing: {p}")
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"fixture {name}: invalid JSON: {e}")
            return None
        if not isinstance(data, list):
            failures.append(f"fixture {name}: expected JSON array, got {type(data).__name__}")
            return None
        return data

    chars = _load_list("characters.json")
    props = _load_list("props.json")
    shots = _load_list("shots.json")
    prompts = _load_list("prompts.json")

    shot_ids = {s.get("id") for s in shots} if shots is not None else set()
    char_ids = {c.get("id") for c in chars} if chars is not None else set()
    prop_ids = {p.get("id") for p in props} if props is not None else set()

    def _check_shots(sid_list, owner, sub=""):
        for sid in sid_list or []:
            if sid not in shot_ids:
                failures.append(f"{owner}{sub} appearance_shots unknown shot {sid}")

    if prompts is not None:
        for shot in prompts:
            for cref in shot.get("character_refs", []):
                if cref not in char_ids:
                    failures.append(f"prompts shot {shot.get('shot_id')} refs unknown character {cref}")
            for pref in shot.get("prop_refs", []):
                if pref not in prop_ids:
                    failures.append(f"prompts shot {shot.get('shot_id')} refs unknown prop {pref}")

    if chars is not None:
        for c in chars:
            _check_shots(c.get("appearance_shots"), f"character {c.get('id')}")
            # WR-02：nested looks[].appearance_shots[] —— Phase 8 per-look prompt refs 依赖它
            for look in c.get("looks", []):
                _check_shots(look.get("appearance_shots"), f"character {c.get('id')}",
                             f" look {look.get('label')!r}")
    if props is not None:
        for p in props:
            _check_shots(p.get("appearance_shots"), f"prop {p.get('id')}")
            for st in p.get("states", []):
                _check_shots(st.get("appearance_shots"), f"prop {p.get('id')}",
                             f" state {st.get('label')!r}")

    # registry (optional —— validate if present)
    reg_path = v11 / "registry.draft.json"
    if reg_path.is_file():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"registry.draft.json: invalid JSON: {e}")
            registry = None
        if isinstance(registry, dict):
            for cl in registry.get("clusters", []):
                cid = cl.get("cluster_id")
                if not (isinstance(cid, str) and re.match(r"^(char|prop)_[0-9]{3}$", cid)):
                    failures.append(f"registry cluster_id malformed: {cid!r}")
                elif cl.get("review_state") != "rejected" and cid not in (char_ids | prop_ids):
                    # IN-04：rejected 簇的实体可能合法地不在 confirmed registries 里
                    failures.append(f"registry cluster_id {cid} not in characters+props IDs")
                for m in cl.get("members", []):
                    if m.get("shot_id") not in shot_ids:
                        failures.append(f"registry cluster {cid} member shot_id {m.get('shot_id')} unknown")

    # Phase 11 v1.2 fixture consistency: speakers.char_id ⊆ characters.id (Pitfall 17)
    # Gated on v1.2 fixture dir existence. speakers.json + characters.json
    # (byte-copied from v1.1) MUST exist; char_id non-null values MUST resolve
    # to a confirmed characters.json#id. Also enforces spk_id ^spk_[0-9]{3}$
    # pattern (T-07-01 mitigation) + turn.shot_id ⊆ shots.json#id.
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
                # Reuse characters.json from v1.2 fixture (byte-copied from v1.1)
                chars_v12_path = v12_fix_dir / "characters.json"
                chars_v12_ids = set()
                if chars_v12_path.is_file():
                    try:
                        for c in json.loads(chars_v12_path.read_text(encoding="utf-8")):
                            if isinstance(c, dict):
                                chars_v12_ids.add(c.get("id"))
                    except (json.JSONDecodeError, TypeError):
                        pass
                # Reuse shots.json from v1.2 fixture (byte-copied from v1.1) — symmetric
                # source-of-truth with chars_v12_ids above (WR-01 fix: was using v1.1
                # shot_ids, which would false-pass/fail if v1.2/shots.json ever diverges).
                shots_v12_path = v12_fix_dir / "shots.json"
                shots_v12_ids = set()
                if shots_v12_path.is_file():
                    try:
                        for s in json.loads(shots_v12_path.read_text(encoding="utf-8")):
                            if isinstance(s, dict):
                                shots_v12_ids.add(s.get("id"))
                    except (json.JSONDecodeError, TypeError):
                        pass
                shot_ids_for_speakers = shots_v12_ids or shot_ids  # fall back to v1.1 if v1.2 absent
                for spk in speakers_data.get("speakers", []):
                    sid = spk.get("spk_id")
                    if not (isinstance(sid, str) and re.match(r"^spk_[0-9]{3}$", sid)):
                        failures.append(f"v1.2 speakers.json: spk_id malformed: {sid!r}")
                    cid = spk.get("char_id")
                    if cid is not None and cid not in chars_v12_ids:
                        failures.append(
                            f"v1.2 speakers.json {sid}: char_id {cid!r} not in "
                            f"v1.2 characters.json IDs (Pitfall 17 — speaker→character dangling)"
                        )
                    # turn.shot_id ⊆ shots.json#id (mirror registry member check; v1.2 source)
                    for turn in spk.get("turns", []) or []:
                        if turn.get("shot_id") not in shot_ids_for_speakers:
                            failures.append(
                                f"v1.2 speakers.json {sid}: turn shot_id "
                                f"{turn.get('shot_id')} unknown"
                            )

    if failures:
        return (
            False,
            f"{len(failures)} fixture-consistency issue(s); first: {failures[0]}",
        )
    return (True, "v1.1 + v1.2 fixture set cross-file IDs consistent (0 dangling)")


# === producer-side registry integrity (Phase 7) ========================
def _producer_registry_integrity(asset_dir: Path) -> list:
    """Phase 7: producer asset dir 内 registry↔shots 跨文件 integrity 检查。

    Gated on file existence: 当 characters.json/props.json/registry.draft.json
    全部缺席（v1.0 asset / route-down degrade），返 []（clean —— no-op；这是
    Phase 6 graceful-degrade 的延续）。当任一存在时，执行：
      (a) appearance_shots[] in characters/props ⊆ shots.json IDs（无 dangling）
      (b) registry clusters[].members[].shot_id ⊆ shots.json IDs（无 dangling）
      (c) canonical IDs unique + match ^(char|prop)_[0-9]{3}$
      (d) NO review_state:"proposed" in canonical files (Pitfall 7 second-line
          assert —— 与 apply_edits.py 的 build-time hard gate 互为 defense-in-depth)

    这是 producer-gate 的扩展（additive），不改既有 _fixture_consistency_check
    （fixture 自洽性）+ _cross_version_check（schema 双向兼容）。
    Pitfall 7 second-line 的存在意义：即便 apply_edits.py 出 bug，producer
    gate 仍能在 asset 落盘前拦截。

    Args:
        asset_dir: producer asset 目录（如 output/《小江湖》第01话…/）。

    Returns:
        list[str] —— 失败描述；空 list = clean（no-op 或 0 failures）。
    """
    import re as _re
    failures: list = []
    shots_path = asset_dir / "shots.json"
    if not shots_path.is_file():
        return []   # 无 shots.json 无法做 cross-file check —— 静默跳过
    try:
        shots = json.loads(shots_path.read_text(encoding="utf-8"))
        shot_ids = {s.get("id") for s in shots} if isinstance(shots, list) else set()
    except (json.JSONDecodeError, TypeError):
        return [f"shots.json unreadable in {asset_dir}"]

    # Check each canonical file that exists
    # Phase 8: collect confirmed-ID sets for the downstream prompts→registry
    # integrity check (Pitfall 17). Phase 7 already asserts !=confirmed fails;
    # this additionally accumulates the confirmed IDs so prompts refs can be
    # validated against them. Both sets stay empty when the file is absent
    # (graceful-degrade —— no registry, nothing to check prompts against).
    char_confirmed_ids: set = set()
    prop_confirmed_ids: set = set()
    for name, id_prefix in (("characters.json", "char_"), ("props.json", "prop_")):
        path = asset_dir / name
        if not path.is_file():
            continue   # absent = graceful-degrade (v1.0 asset / route-down)
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{name}: invalid JSON: {e}")
            continue
        if not isinstance(entries, list):
            failures.append(f"{name}: expected array, got {type(entries).__name__}")
            continue
        seen_ids: set = set()
        for entry in entries:
            if not isinstance(entry, dict):
                failures.append(f"{name}: non-dict entry: {entry!r}")
                continue
            eid = entry.get("id")
            # (c) ID pattern
            if not (isinstance(eid, str)
                    and _re.match(rf"^{id_prefix}[0-9]{{3}}$", eid)):
                failures.append(
                    f"{name}: ID {eid!r} does not match {id_prefix}_[0-9]{{3}}")
            # (c) ID uniqueness
            if eid in seen_ids:
                failures.append(f"{name}: duplicate ID {eid!r}")
            seen_ids.add(eid)
            # (d) Pitfall 7 —— only 'confirmed' flows to canonical (WR-04: tighten
            #     from ==proposed to !=confirmed，让 rejected 泄漏也被捕获 ——
            #     schema enum 接受 proposed/confirmed/rejected，故 rejected 泄漏不会
            #     被 schema 校验拦住；apply_edits hard gate 是 `!= confirmed: continue`，
            #     本 second-line assert 与之对齐)。
            if entry.get("review_state") != "confirmed":
                failures.append(
                    f"{name} {eid}: review_state={entry.get('review_state')!r} "
                    f"in canonical (must be 'confirmed' — Pitfall 7)")
            else:
                # Phase 8: accumulate confirmed ID for prompts→registry check.
                # Pitfall 7 already failed above for non-confirmed; only confirmed
                # entries are legal prompt-ref targets.
                if id_prefix == "char_":
                    char_confirmed_ids.add(eid)
                elif id_prefix == "prop_":
                    prop_confirmed_ids.add(eid)
            # (a) appearance_shots ⊆ shots
            for sid in entry.get("appearance_shots", []) or []:
                if sid not in shot_ids:
                    failures.append(
                        f"{name} {eid}: appearance_shots references "
                        f"unknown shot {sid}")

    # (e) Phase 8 (PROMPT-03, Pitfall 17): prompts.character_refs[]/prop_refs[]
    #     MUST ⊆ confirmed characters.json/props.json IDs. Additive —— gated on
    #     prompts.json existence (graceful-degrade: no prompts → nothing to check).
    #     Mirrors the fixture-side _fixture_consistency_check (lines ~440-447); the
    #     producer-side extension is the runtime gate against real asset dirs. By
    #     construction attach_refs.py cannot produce a dangling ref (it attaches
    #     ONLY from confirmed registry inversion); this catches hand-edited drift.
    prompts_path = asset_dir / "prompts.json"
    if prompts_path.is_file():
        try:
            prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"prompts.json: invalid JSON: {e}")
            prompts = None
        if isinstance(prompts, list):
            for entry in prompts:
                if not isinstance(entry, dict):
                    continue
                sid = entry.get("shot_id")
                for cref in entry.get("character_refs", []) or []:
                    if cref not in char_confirmed_ids:
                        failures.append(
                            f"prompts.json shot {sid}: character_ref {cref!r} "
                            f"not in confirmed characters.json IDs "
                            f"(Pitfall 17 — prompt dangling ref)")
                for pref in entry.get("prop_refs", []) or []:
                    if pref not in prop_confirmed_ids:
                        failures.append(
                            f"prompts.json shot {sid}: prop_ref {pref!r} "
                            f"not in confirmed props.json IDs "
                            f"(Pitfall 17 — prompt dangling ref)")

    # (b) registry cluster members ⊆ shots.json
    reg_path = asset_dir / "registry.draft.json"
    if reg_path.is_file():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
            if isinstance(registry, dict):
                for cl in registry.get("clusters", []) or []:
                    if not isinstance(cl, dict):
                        continue
                    cid = cl.get("cluster_id", "?")
                    for m in cl.get("members", []) or []:
                        if not isinstance(m, dict):
                            continue
                        if m.get("shot_id") not in shot_ids:
                            failures.append(
                                f"registry.draft.json cluster {cid}: "
                                f"member shot_id {m.get('shot_id')} unknown")
        except json.JSONDecodeError as e:
            failures.append(f"registry.draft.json: invalid JSON: {e}")

    return failures


def run_producer_check(args) -> tuple:
    """producer mode：对真实 ep01 asset 跑 6-schema inline 校验。

    流程：
      1. 定位 asset.json（默认 ep01；可 PHASE4_ASSET_DIR 覆盖，旧名
         PHASE4_E2E_ASSET_DIR 仍向后兼容 —— WR-07）
      2. （opt-in）PHASE4_RE_EXPORT=1 调 scripts/export_asset.py 重导
      3. 加载 manifest
      4. validate_six_shapes 跑 6 个 schema
      5. 全绿返 (True, "...")；任一失败返 (False, "shape: reason; ...")

    返回 tuple[bool, str] —— 让 main() 统一格式化输出 + exit code。
    """
    asset_dir = Path(args.asset_dir)
    asset_path = asset_dir / "asset.json"
    if not asset_path.is_file():
        return (
            False,
            f"ep01 asset.json missing at {asset_dir}\n"
            f"  run `python3 run_pipeline.py --video <path>` + export first, or set\n"
            f"  PHASE4_ASSET_DIR=<path-to-asset-dir>",
        )

    # (可选) 重导抓 producer 漂移 —— CONTEXT 锁：本仓库 output/ 可覆盖，
    # worktree pinned golden（scripts/fixtures/shot-timeline-ep01/）绝不动。
    if os.environ.get("PHASE4_RE_EXPORT") == "1":
        print(f"[producer] PHASE4_RE_EXPORT=1 —— 重导 asset.json")
        video = _resolve_canonical_video(asset_dir)
        stems_src = asset_dir / "stems" / "htdemucs" / asset_dir.name
        rc = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "export_asset.py"),
                "--work-dir", str(asset_dir),
                "--video", video,
                "--stems-source-dir", str(stems_src),
                "--output", str(asset_path),
                "--force",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if rc.returncode != 0:
            return (
                False,
                f"export_asset.py failed (rc={rc.returncode}):\n"
                f"  stderr: {rc.stderr.strip()[:400] or '(empty)'}",
            )

    manifest = json.loads(asset_path.read_text(encoding="utf-8"))
    failures = validate_eight_shapes(asset_dir, manifest)
    if failures:
        return (False, "; ".join(failures))

    # Phase 7: producer asset dir registry↔shots integrity (additive — gated on
    # file existence: v1.0 asset / route-down degrade → no registry files → no-op).
    # Pitfall 7 second-line assert: catches "proposed" leak even if apply_edits
    # has a bug (defense-in-depth alongside its build-time hard gate).
    registry_failures = _producer_registry_integrity(asset_dir)
    if registry_failures:
        return (False, "; ".join(registry_failures))

    # v1.1 contract-level checks (Phase 5). 这两个检查跑 spec/fixtures/（确定性
    # contract invariants），不跑 producer asset dir —— producer 产物是否带 v1.1
    # 字段是 Phase 6+ 的事，本 harness 只锁 contract 本身的跨版本/自洽不变量。
    cv_ok, cv_detail = _cross_version_check()
    if not cv_ok:
        return (False, cv_detail)
    fc_ok, fc_detail = _fixture_consistency_check()
    if not fc_ok:
        return (False, fc_detail)

    return (
        True,
        f"asset.json + data shapes schema-valid; {cv_detail}; {fc_detail}",
    )


# === consumer-side helper ===============================================
def run_consumer_check(args) -> tuple:
    """consumer mode：subprocess shell-out 到 Phase 3 verify-canvas-shot-timeline.ts。

    流程：
      1. guard：CANVAS_CONSUMER_PATH 存在 + 是 git worktree（防 T-04-01-T1 恶意指向）
      2. guard：verify script 存在
      3. subprocess.run([npx, tsx, scripts/verify-canvas-shot-timeline.ts],
                        cwd=consumer, timeout=60)
      4. 透传 stdout（17 asserts 进度）
      5. rc==0 → (True, "...")；rc≠0 → (False, "...")

    模板源：04-RESEARCH.md §Code Examples 示例 3（L821-838）。
    """
    consumer = args.consumer_path

    if not os.path.isdir(consumer):
        return (
            False,
            f"CANVAS_CONSUMER_PATH 不存在: {consumer}\n"
            f"  set CANVAS_CONSUMER_PATH=<worktree> 或 clone kais-aigc-platform\n"
            f"  + checkout feat/canvas-asset-collection",
        )
    if not os.path.isdir(os.path.join(consumer, ".git")) and not os.path.isfile(
        os.path.join(consumer, ".git")
    ):
        return (False, f"not a git worktree: {consumer}")

    verify_script = os.path.join(consumer, "scripts", "verify-canvas-shot-timeline.ts")
    if not os.path.isfile(verify_script):
        return (
            False,
            f"Phase 3 verify script missing: {verify_script}\n"
            f"  ensure worktree is on feat/canvas-asset-collection branch\n"
            f"  (cd {consumer} && git checkout feat/canvas-asset-collection)",
        )

    try:
        rc = subprocess.run(
            ["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"],
            cwd=consumer, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return (False, f"verify-canvas-shot-timeline.ts timeout (>60s)")
    except FileNotFoundError:
        return (
            False,
            "npx not found —— Node.js / npm 未安装或不在 PATH\n"
            f"  consumer worktree expects `npx tsx ...`",
        )

    # 透传 Phase 3 17 asserts 输出（含 PASS/FAIL 行）
    if rc.stdout:
        sys.stdout.write(rc.stdout)
        if not rc.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if rc.returncode != 0:
        return (
            False,
            f"verify-canvas-shot-timeline.ts exit {rc.returncode}\n"
            f"  stderr: {(rc.stderr or '').strip()[:400] or '(empty)'}",
        )
    return (True, "Phase 3 17 asserts all green (importer accepts golden asset)")


# === self-test (PHASE4_SELF_TEST=1) ====================================
def run_self_test(args) -> tuple:
    """注入故意漂移（schema_version='v1'），证明 harness fail-loud。

    流程：
      1. 创建 /tmp/phase4-selftest-<rand>/ temp dir
      2. 复制真实 ep01 asset.json + 5 referenced data files 到 temp dir
         （shutil.copy2 保留 mtime；不改动真实 output/）
      3. 加载 asset.json copy → 把 schema_version 改为 'v1'（违反 pattern；原值是 producer emit 的合法版本号 —— v1.0 资产为 "1"、v1.1 为 "1.1"，注入 'v1' 都会触发 pattern 拒绝）
         （违反 asset.schema.json L13 pattern `^(0|[1-9]\\d*)(\\.(0|[1-9]\\d*))?$`）
      4. atomic write back（tmp + os.replace，per scripts/export_asset.py L308-313）
      5. validate_asset_json(temp_path) —— 期望返 ≥1 error
      6. ≥1 error → (True, "PASS: corrupt asset correctly rejected ...")
         空 errors → (False, "FAIL: harness 接受了损坏 asset —— 无法检测 producer drift")

    语义：self-test PASS = harness 工作正常（能检测 drift）→ 整体 exit 0；
          self-test FAIL = harness 损坏（无法检测 drift）→ 整体 exit 1。
    这与 RESEARCH §Validation Architecture "corrupt asset → exit 1" 一致 ——
    「exit 1」指底层 producer mode 遇到坏 asset 应 exit 1，self-test 是
    meta-test 验证这个属性成立。
    """
    src_dir = Path(args.asset_dir)
    src_asset = src_dir / "asset.json"
    if not src_asset.is_file():
        return (
            False,
            f"self-test 需要 ep01 asset.json 作为漂移注入源，但缺失: {src_asset}",
        )

    # 1. temp dir（mkdtemp 前缀方便 find /tmp -name 'phase4-selftest-*' 调试）
    temp_dir = Path(tempfile.mkdtemp(prefix="phase4-selftest-"))
    try:
        # 2. 复制 asset.json + 5 referenced data files
        temp_asset = temp_dir / "asset.json"
        shutil.copy2(src_asset, temp_asset)
        manifest_copy = json.loads(temp_asset.read_text(encoding="utf-8"))
        for shape, rel in manifest_copy.get("data", {}).items():
            src_data = src_dir / rel
            if src_data.is_file():
                dst = temp_dir / rel
                # WR-05：data.<shape> 允许 subdir 段（asset.schema.json L66 pattern
                # 不禁止），shutil.copy2 在 dst.parent 不存在时抛 FileNotFoundError。
                # mkdir parents 兜底未来 producer 产 ``subdir/shots.json`` 布局。
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_data, dst)

        # 3. 注入 drift：schema_version "1" → "v1"（违反 pattern 字段）
        manifest_copy["schema_version"] = "v1"

        # 4. atomic write back（per scripts/export_asset.py L308-313）
        tmp_write = str(temp_asset) + ".tmp"
        with open(tmp_write, "w", encoding="utf-8") as f:
            json.dump(manifest_copy, f, indent=2, ensure_ascii=False)
        os.replace(tmp_write, temp_asset)

        # 5. 跑 producer 侧 inline validator（asset shape only）
        errors = validate_asset_json(temp_asset)

        # 6. 断言
        if len(errors) >= 1:
            first = errors[0]
            loc = "/".join(map(str, first.absolute_path)) or "<root>"
            return (
                True,
                f"corrupt asset (schema_version='v1') correctly rejected with "
                f"{len(errors)} error(s); first at /{loc}: {first.message}",
            )
        return (
            False,
            "harness 接受了 schema_version='v1' —— 无法检测 producer drift "
            "（这是严重 regression；asset.schema.json 的 pattern 校验失效）",
        )
    finally:
        # T-04-03-T1：temp dir 不留残留（try/finally + ignore_errors 兜底）
        shutil.rmtree(temp_dir, ignore_errors=True)


# === e2e mode (Plan 04-02) ==============================================
def run_e2e_check(args) -> tuple:
    """e2e mode：起 backend → POST import-from-dir → SQL read-back → 结构断言。

    流程（Plan 04-02 <action>）：
      1. guard：consumer worktree 存在 + 是 git worktree（T-04-07-T2）
      2. guard：asset_dir 含 asset.json
      3. find_free_port() + Popen npx tsx src/app.ts（NODE_ENV=dev）
         stdout=DEVNULL（Pitfall 7：避免 pipe-buffer deadlock）
      4. timestamp-based pid/eid（int(time.time()), +1）—— 避免碰撞 Phase 3 9001/9001
      5. try:
           a. _poll_health(45s)
           b. POST /api/canvas/v2/import-from-dir body=UTF-8 encoded JSON bytes
              （Pitfall 6：workdir 路径含 CJK + 全角标点）
           c. _read_persisted_snapshot SQL 直查 o_agentWorkData
              （Pitfall 1：绝不用 load-v2 HTTP 读 relational）
           d. 结构断言：
              - 1 zone
              - ≥1 storyboard（ep01 实测 93，不硬编码）
              - 3 audio (vocals/drums/other)
              - ≥1 video（实测 1 artifact + 1 sum-p13 = 2）
              - N-1 sequence edges（WR-01 验证：primary 路径 sequence edges 存活）
         finally (teardown —— 3 层 + worktree reconcile + cleanup DELETE):
           a. proc.terminate → wait(10) → kill → wait(2) reap
              （模板源：scripts/check_range.py L104-118 + 02-REVIEW WR-06）
           b. git -C $consumer checkout -- src/types/database.d.ts
              （Pitfall 2/5：dev-mode regen 噪音兜底）
           c. DELETE FROM o_agentWorkData/kv_canvasEvent WHERE pid/eid=?
              （保留 Phase 3 leftover 9001/9001；T-04-04-T2 cleanup）

    返回 tuple[bool, str] —— 让 main() 统一格式化 + exit code。
    """
    consumer = args.consumer_path
    if not os.path.isdir(consumer) or not (
        os.path.isdir(os.path.join(consumer, ".git"))
        or os.path.isfile(os.path.join(consumer, ".git"))
    ):
        return (
            False,
            f"CANVAS_CONSUMER_PATH 不是 git worktree: {consumer}\n"
            f"  set CANVAS_CONSUMER_PATH=<worktree> 或 clone kais-aigc-platform\n"
            f"  + checkout feat/canvas-asset-collection",
        )

    asset_dir = args.asset_dir
    if not os.path.isfile(os.path.join(asset_dir, "asset.json")):
        return (
            False,
            f"e2e 输入 asset.json 缺失: {asset_dir}\n"
            f"  set PHASE4_ASSET_DIR=<real producer asset dir>",
        )

    port = find_free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["NODE_ENV"] = "dev"  # dev tsx 直跑 src/app.ts；production 需 esbuild bundle

    # timestamp-based pid/eid —— 避免碰撞 Phase 3 leftover 9001/9001
    # WR-03：挪到 Popen 之前 —— 这些值与 proc 无关，先算好消除 Popen↔try
    # 之间的 orphan 窗口（任何 Popen 之后、try 之前的异常原本会让 backend
    # 进程无 teardown 泄漏）。
    pid = int(time.time())
    eid = pid + 1
    db_path = os.path.join(consumer, "data", "db2.sqlite")

    # WR-03：proc/pgid 先置 None，让 finally 能识别「Popen 没成功」分支。
    proc = None
    pgid = None
    try:
        # Pitfall 7：DEVNULL 避免 pipe-buffer deadlock（backend 启动期大量 console.log）
        # start_new_session=True 让 npx + 子 node 进程成 process group（PGID=proc.pid），
        # teardown 用 os.killpg 一次清整个组（否则 SIGTERM 只打 npx，子 node 变 orphan）
        proc = subprocess.Popen(
            ["npx", "tsx", "src/app.ts"],
            cwd=consumer, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # CR-02：start_new_session=True 保证子进程成为新 session/group leader，
        # 所以 pgid == proc.pid 整个 group 生命周期不变。在 Popen 后立即缓存，
        # 避免事后 os.getpgid(reaped_pid) 与 reaping 竞争抛 ProcessLookupError
        # 把 SIGKILL escalation 整段跳过。
        pgid = proc.pid
        # a. poll /health
        ok, reason = _poll_health(port, proc, timeout=45.0)
        if not ok:
            return (False, reason)
        print(f"[e2e] backend ready on port {port}")

        # b. POST /api/canvas/v2/import-from-dir
        # Pitfall 6：workdir 含 CJK + 全角标点 —— body 用 UTF-8 encoded JSON bytes
        body = json.dumps({
            "projectId": pid,
            "episodesId": eid,
            "workdir": str(asset_dir),
            "mode": "replace",
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/canvas/v2/import-from-dir",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
                if r.status != 200:
                    return (False, f"import-from-dir HTTP {r.status}: {resp}")
        except urllib.error.HTTPError as e:
            err_body = e.read()[:300].decode("utf-8", errors="replace")
            return (False, f"import-from-dir failed: HTTP {e.code} {err_body}")
        imported = (resp.get("data") or {}).get("imported", "?")
        print(f"[e2e] import-from-dir OK: {imported} nodes imported")

        # c. SQL read-back —— 绕开 load-v2 relational mismatch（Pitfall 1）
        graph = _read_persisted_snapshot(db_path, pid, eid)
        if graph is None:
            return (
                False,
                f"snapshot 缺失 pid={pid} eid={eid} —— import-from-dir 写入但 "
                f"o_agentWorkData 查不到（可能 primary 路径异常）",
            )

        # d. 结构断言
        nodes = graph.get("nodes", [])
        links = graph.get("links", [])
        zones = [n for n in nodes if n.get("type") == "zone"]
        storyboards = [n for n in nodes if n.get("type") == "storyboard"]
        audios = [n for n in nodes if n.get("type") == "audio"]
        videos = [n for n in nodes if n.get("type") == "video"]
        summaries = [n for n in nodes if str(n.get("id", "")).startswith("sum-")]
        # WR-01 验证：sequence edges 在 primary appendAndSync 路径完整存活
        # （save-v2 才会经 FlowLinkV2Schema strip；e2e 不走 save-v2）
        # Phase 3 producer 字面形状：{dataType:"data", data:{linkType:"sequence"}}
        # —— 断言优先用 data.linkType 字段（语义权威）
        seq_edges = [
            l for l in links
            if (l.get("data") or {}).get("linkType") == "sequence"
        ]

        try:
            assert len(zones) == 1, f"zones: want 1 got {len(zones)}"
            assert len(storyboards) >= 1, \
                f"storyboards: want ≥1 got {len(storyboards)}"
            assert len(audios) == 3, \
                f"audios: want 3 (vocals/drums/other) got {len(audios)}"
            assert len(videos) >= 1, \
                f"videos: want ≥1 artifact got {len(videos)}"
            assert len(seq_edges) == len(storyboards) - 1, \
                f"seq_edges: want {len(storyboards)-1} (N-1) got {len(seq_edges)} " \
                f"—— WR-01 验证（primary 路径 sequence edges 应存活）"
        except AssertionError as e:
            return (
                False,
                f"snapshot 结构断言失败: {e}\n"
                f"  实测: {len(nodes)} nodes, {len(links)} links, "
                f"{len(zones)} zone, {len(storyboards)} storyboard, "
                f"{len(audios)} audio, {len(videos)} video, "
                f"{len(summaries)} summary, {len(seq_edges)} seq_edges"
            )

        print(
            f"[e2e] snapshot valid: {len(nodes)} nodes, {len(links)} links, "
            f"{len(zones)} zone, {len(storyboards)} storyboard, "
            f"{len(audios)} audio, {len(videos)} video, "
            f"{len(seq_edges)} seq edges "
            f"(WR-01 data survives primary path)"
        )
        return (
            True,
            f"snapshot valid: {len(storyboards)} storyboards + "
            f"{len(seq_edges)} sequence edges survive primary appendAndSync path "
            f"(WR-01/04 not surfaced)",
        )
    finally:
        # teardown a：3-layer proc-group cleanup
        # 模板源 scripts/check_range.py L104-118 + 升级到 process-group kill
        # （npx tsx 会 fork 子 node 进程；SIGTERM 只打 npx 留 orphan —— Rule 1 fix）
        # CR-02 修复两点：
        #   (a) pgid 已在 Popen 后缓存（start_new_session=True 时 pgid==proc.pid
        #       全程不变），消除 getpgid(reaped_pid) TOCTOU；
        #   (b) SIGKILL 改为外层 finally 无条件执行 —— 不再只在 TimeoutExpired
        #       分支里 escalation。修补 npx 父进程先死、子 node 没收到 SIGTERM
        #       （装了不 exit 的 handler / 信号延迟转发）的孤儿窗口。
        # WR-03：pgid is None 说明 Popen 没成功（或前置异常），跳过 proc 清理；
        # teardown b/c 不依赖 proc，仍可执行。
        import signal as _signal
        if pgid is not None:
            try:
                os.killpg(pgid, _signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            # bounded SIGTERM wait —— 父进程通常几秒内退；不依赖此超时触发 escalation
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            # 无条件 SIGKILL 整个 group —— 兜底所有 SIGTERM 没收齐的情形
            # （父先死 / 子装 handler 不 exit / 信号延迟转发）
            try:
                os.killpg(pgid, _signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

        # teardown b：worktree reconcile（Pitfall 2/5 —— database.d.ts dev regen 噪音）
        # best-effort，失败不阻塞 —— 是 auto-regen 副产品，生产路径不依赖
        try:
            subprocess.run(
                ["git", "-C", consumer, "checkout", "--",
                 "src/types/database.d.ts"],
                capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # teardown c：DELETE 自己的 test rows（保留 Phase 3 leftover 9001/9001）
        # T-04-04-T2 mitigation: parameterized SQL，绝不字符串拼接
        # WR-08：原实现把两条 DELETE 放同一隐式事务，第二条失败时 conn.close()
        # 在 finally 里 rollback，连第一条（o_agentWorkData）也回滚 —— 残留
        # 阻塞下次同 pid/eid 重跑（Phase 3 漂移 schema 没建 kv_canvasEvent 时
        # 正好踩此）。改成每条 DELETE 独立 try/except + 各自 commit —— 第一条
        # 成功就持久化，第二条失败只 WARN 自己那一张表。
        try:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                for sql in (
                    "DELETE FROM o_agentWorkData "
                    "WHERE projectId = ? AND episodesId = ?",
                    "DELETE FROM kv_canvasEvent "
                    "WHERE projectId = ? AND episodesId = ?",
                ):
                    try:
                        cur.execute(sql, (str(pid), str(eid)))
                        conn.commit()
                    except sqlite3.Error as e:
                        sys.stderr.write(
                            f"[e2e] WARNING: cleanup step failed ({sql[:40]}…): {e}\n"
                        )
            finally:
                conn.close()
        except sqlite3.Error as e:
            # 连接/打开失败 —— 整体 best-effort，不阻塞退出
            sys.stderr.write(
                f"[e2e] WARNING: test row cleanup failed to open DB: {e} "
                f"(pid={pid} eid={eid} 残留 in {db_path})\n"
            )


# === CLI ================================================================
def main():
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="Phase 4 跨仓库契约验证 harness —— 抓 producer / consumer 两端漂移"
    )
    ap.add_argument(
        "--mode", choices=["producer", "consumer", "e2e", "all"], default="all",
        help="验证模式（producer=导出端 schema, consumer=消费端 importer, "
             "e2e=端到端, all=全部；e2e 当前为 placeholder，04-02 实现）",
    )
    ap.add_argument(
        "--consumer-path",
        default=os.environ.get("CANVAS_CONSUMER_PATH", DEFAULT_CONSUMER_PATH),
        help="consumer worktree 路径（kais-aigc-platform feat/canvas-asset-collection）",
    )
    ap.add_argument(
        "--asset-dir", "--e2e-asset-dir",
        dest="asset_dir",
        default=os.environ.get("PHASE4_ASSET_DIR")
            or os.environ.get("PHASE4_E2E_ASSET_DIR")
            or str(DEFAULT_E01_ASSET_DIR),
        help="asset 目录（producer/self-test/e2e 三种 mode 共用，默认 ep01）。"
             "WR-07：旧名 --e2e-asset-dir / PHASE4_E2E_ASSET_DIR 仍向后兼容，"
             "推荐用 --asset-dir / PHASE4_ASSET_DIR。",
    )
    ap.add_argument(
        "--e2e-skip", action="store_true",
        help="跳过 e2e mode（CI-friendly；e2e 起 backend 重，默认就跳过）",
    )
    args = ap.parse_args()

    # WR-06：--mode=e2e + --e2e-skip 是矛盾组合 —— 用户显式要 e2e 又显式跳过它，
    # 不该静默 exit 0（会掩盖 CI wrapper 误传两 flag 的配置错）。直接拒掉。
    if args.mode == "e2e" and args.e2e_skip:
        sys.exit(
            "[verify-contract] --mode=e2e 与 --e2e-skip 冲突 —— "
            "要么去掉 --e2e-skip 让 e2e 跑，要么换 --mode=all 再加 --e2e-skip"
        )

    results = []  # list of (mode_name, ok, detail)

    # self-test (opt-in via PHASE4_SELF_TEST=1; only meaningful for producer/all)
    # 必须先于 producer mode 跑 —— 若 harness 本身损坏（fail-loud 失效），
    # producer mode 的「PASS」结果不可信，self-test FAIL 应让整体 exit 1。
    if os.environ.get("PHASE4_SELF_TEST") == "1" and args.mode in ("producer", "all"):
        print("[verify-contract] self-test mode starting (PHASE4_SELF_TEST=1)")
        ok, detail = run_self_test(args)
        tag = "[self-test] PASS" if ok else "[self-test] FAIL"
        print(f"{tag}: {detail}")
        results.append(("self-test", ok, detail))

    # producer mode
    if args.mode in ("producer", "all"):
        print("[verify-contract] mode=producer starting")
        ok, detail = run_producer_check(args)
        tag = "[producer] OK" if ok else "[producer] FAIL"
        print(f"{tag}: {detail}")
        results.append(("producer", ok, detail))

    # consumer mode
    if args.mode in ("consumer", "all"):
        print("[verify-contract] mode=consumer starting")
        ok, detail = run_consumer_check(args)
        tag = "[consumer] OK" if ok else "[consumer] FAIL"
        print(f"{tag}: {detail}")
        results.append(("consumer", ok, detail))

    # e2e mode —— Plan 04-02 接入（替换 04-01 placeholder）
    # 语义：--mode=e2e 显式 opt-in 时即使无 env var 也跑（用户明确要 e2e）；
    #       --mode=all 需要 PHASE4_RUN_E2E=1 才包含 e2e（CI-friendly，heavy：起 backend）
    if args.mode in ("e2e", "all") and not args.e2e_skip:
        e2e_enabled = (args.mode == "e2e") or (os.environ.get("PHASE4_RUN_E2E") == "1")
        if e2e_enabled:
            print("[verify-contract] mode=e2e starting (heavy: starts backend)")
            results.append(("e2e", *run_e2e_check(args)))
        else:
            print("[verify-contract] e2e skipped (set PHASE4_RUN_E2E=1 to enable)")

    # 汇总表
    print()
    print("[verify-contract] summary:")
    for name, ok, detail in results:
        status = "OK  " if ok else "FAIL"
        # 截断长 detail（self-test / schema error 可能很长）
        short = detail if len(detail) <= 120 else detail[:117] + "..."
        print(f"  {status}  {name:9s} {short}")

    any_fail = any(not ok for _, ok, _ in results)
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
