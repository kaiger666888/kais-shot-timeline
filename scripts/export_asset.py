#!/usr/bin/env python3
"""ShotTimelineAsset 导出器：把 output/<video-stem>/ 打包成自描述的 asset.json。

目的：在 pipeline 末端把现有 5 个数据 JSON（shots / audio_analysis / transcript /
frames / prompts）+ 原始视频 + 3 个 canonical stems（vocals / drums / other）
打包成符合 spec/schemas/asset.schema.json 的 ShotTimelineAsset manifest，并
建立 canonical 媒体 symlink，让下游消费者（@kais/infinite-canvas）能以统一的
相对路径（`video.mp4`、`stems/{vocals,drums,other}.wav`）找到所有资产。

行为：
  * 读取 transcript.json 中的 `source` / `duration` 字段，回退到 ffprobe 兜底。
  * 写入 asset.json（schema_version=SCHEMA_VERSION（当前 "1.3"），asset_type="shottimeline"，generator
    含 tool / version(git SHA) / generated_at(ISO-8601 UTC)）。
  * 建立 4 个 canonical symlinks：
      - video.mp4             → 原始视频的绝对路径（含 audio 流，非 h264.mp4）
      - stems/vocals.wav      → stems/htdemucs/<video-stem>/vocals.wav
      - stems/drums.wav       → stems/htdemucs/<video-stem>/drums.wav
      - stems/other.wav       → stems/htdemucs/<video-stem>/other.wav
    bass.wav 显式剔除（schema 拒绝 + 前端只渲染 3 stems）。
  * 写完后立即用 inline Draft202012Validator(asset.schema.json) 自校验，
    不 subprocess 到 spec/validate.py（其 SMOKE_SHAPES 排除 asset）。
  * prompts.json 缺失时 sys.exit 非 0 + 中文 actionable 错误（schema required）。
  * 幂等：已存在的 symlink 若 target 一致则跳过；非 symlink 真实文件拒绝覆盖。

用法：
  python3 scripts/export_asset.py \
      --work-dir output/<video-stem>/ \
      --video /abs/path/to/original.mp4 \
      --stems-source-dir output/<video-stem>/stems/htdemucs/<video-stem>/ \
      --output output/<video-stem>/asset.json \
      [--force]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# scripts/export_asset.py → repo root（定位 spec/schemas/asset.schema.json）
REPO = Path(__file__).parent.parent.resolve()

# Phase 8 REVIEW WR-05 fix：canonical registry schema paths（用于 _build_registry_snapshot
# 内 schema-validate；mirror attach_refs.py WR-02 + apply_edits.py WR-05 防御）。
CHARACTERS_SCHEMA = REPO / "spec" / "schemas" / "characters.schema.json"
PROPS_SCHEMA = REPO / "spec" / "schemas" / "props.schema.json"

# ShotTimelineAsset 契约版本（单一真源）。schema_version pattern 在 spec/schemas/
# asset.schema.json 里保持宽松（接受 "1"/"1.1"/"2.0"），但实际 emit 的字面量在这里锁死。
# v1.3 = 增量（新增 optional roundtrip 数据文件 + roundtrip.schema.json 第 14 个 schema）。
# 诚实记录两处非纯 property-delta（对旧数据 additive）：① generator.warnings.items
# 加宽为 string | {code, detail}（v1.x 首个 items 类型加宽；旧 string 条目仍合法）；
# ② data.roundtrip 是首个 object 值 data.* 挂载（file ref + accepted/rejected 统计，
# roundtrip.json 缺席时字段 OMIT，byte-identical-absent）。
# 改这里即改全资产 emit；Pitfall 12（schema 变更后忘 bump 版本号）因此结构上不可能。
SCHEMA_VERSION = "1.3"

# RT-04：[roundtrip] degrade 记因的结构化 warnings code closed enum（与
# asset.schema.json#generator.warnings.items 的 anyOf object 分支逐字对齐）。
_ROUNDTRIP_WARNING_CODES = (
    "comfyui_unreachable",
    "vram_insufficient",
    "scorer_model_missing",
)


def _valid_warnings_list(candidate: object):
    """校验 warnings sidecar 候选值；合规返回原 list，否则 None（silent fallback）。

    RT-04 degrade 记因通道（v1.3 加宽）：接受 list[str | {code, detail}] ——
    元素是 str（v1.1/v1.2 legacy 纯文本）或 dict 且 keys ⊆ {code, detail}、
    code 在 _ROUNDTRIP_WARNING_CODES closed enum 内、detail 缺席或为 str。
    任何不合规（非 list / 元素形状错 / code 越界 / detail 非 str / 夹带未知键）
    → 整体回退 None（不持久化可疑条目，mirror 既有 silent-fallback 语义）。
    [] → None（缺省，不 emit —— 空列表与 None 同义，collapse 在此完成）。
    """
    if not isinstance(candidate, list):
        return None
    for w in candidate:
        if isinstance(w, str):
            continue
        if (isinstance(w, dict)
                and set(w.keys()) <= {"code", "detail"}
                and w.get("code") in _ROUNDTRIP_WARNING_CODES
                and ("detail" not in w or isinstance(w["detail"], str))):
            continue
        return None
    return candidate or None  # [] → None（缺省，不 emit）


def _probe_duration(path: str) -> float:
    """ffprobe 读取视频时长（秒）；失败回退 0.0。

    与 run_pipeline.py:probe_duration 行为一致（不跨 stage import，自带副本）。
    """
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def _git_sha() -> str:
    """取仓库短 git SHA 作为 generator.version；失败回退 "dev"。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2)
        return r.stdout.strip() or "dev"
    except (subprocess.SubprocessError, OSError):
        return "dev"


def ensure_symlink(link_path: str, target: str) -> None:
    """幂等创建 symlink link_path → target。

    分支：
      * target 必须是 regular file —— 拒绝目录/FIFO/device/special file
        （02-REVIEW WR-05）。否则 symlink-to-dir 会通过 schema pattern 校验 +
        pre-write os.path.exists assert（True for dir），把指向目录的"看似有效"
        manifest 落盘，下游打开 .wav 才崩。os.path.isfile 跟随 symlink 后 stat，
        等价于 "exists 且是 regular file"。
      * 若 link_path 已是 symlink：
          - readlink 与 target 一致 → skip（避免无谓的 unlink+recreate）
          - 不一致 → unlink + 重建
      * 若 link_path 存在但非 symlink（真实文件/目录）→ raise FileExistsError
        （拒绝静默覆盖真实文件）
      * 否则 → os.symlink(target, link_path)
    """
    # 02-REVIEW WR-05：用 isfile 而非 exists —— 显式排除 dir / FIFO / device / socket。
    if not os.path.isfile(target):
        raise FileNotFoundError(
            f"symlink target is not a regular file: {target}")
    if os.path.islink(link_path):
        try:
            current = os.readlink(link_path)
        except OSError:
            current = None
        if current == target:
            return  # idempotent skip
        os.unlink(link_path)
    elif os.path.exists(link_path):
        raise FileExistsError(
            f"refusing to overwrite non-symlink: {link_path} "
            f"(expected symlink → {target})")
    os.symlink(target, link_path)


def validate_asset_json(asset_dict: dict) -> None:
    """inline Draft202012Validator 自校验 asset_dict。

    绝不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES 显式排除 asset
    （spec/validate.py:49），subprocess 会让无效 manifest 悄悄通过。
    """
    # lazy import：沿用 CLAUDE.md 的 optional-dep lazy-import 惯例
    from jsonschema import Draft202012Validator

    schema_path = REPO / "spec" / "schemas" / "asset.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(asset_dict),
                    key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        sys.exit(
            f"asset.json failed schema validation ({len(errors)} error(s)):\n"
            + "\n".join(lines))


class _SchemaInvalid(Exception):
    """_build_registry_snapshot 内 schema 校验失败的信号异常（不 sys.exit）。

    attach_refs.py WR-02 的 _validate_registry 是 sys.exit（consumer 路径需要 fail
    loud 给操作者）；export_asset 是 producer 路径，WR-05 选择 warn + OMIT（让
    export 继续，但 snapshot 字段缺省，corruption 不进 asset.json）。本信号异常
    让 _build_registry_snapshot 在 try/except 内区分「schema invalid」与
    「JSON malformed」两类，统一走 warn + return None 路径。
    """
    def __init__(self, errors: list):
        super().__init__("schema invalid")
        self.errors = errors


def _validate_registry_for_snapshot(schema_path, instance, label: str) -> None:
    """Schema-validate loaded canonical registry；invalid → raise _SchemaInvalid（WR-05）。

    Mirror attach_refs._validate_registry 的 schema 检查逻辑，但 fail-soft（raise
    而非 sys.exit）—— 让 caller (_build_registry_snapshot) 自己决定 warn+OMIT 或
    fail-loud。当前 caller 选择 warn + return None（不 emit 空 snapshot 掩盖 corruption）。
    """
    # lazy import：沿用 CLAUDE.md 的 optional-dep lazy-import 惯例
    from jsonschema import Draft202012Validator
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    if errors:
        msgs = [f"[{'/'.join(str(p) for p in e.absolute_path) or '<root>'}] {e.message}"
                for e in errors[:10]]
        raise _SchemaInvalid(msgs)


def _build_registry_snapshot(work_dir: str):
    """读 characters.json + props.json → compact confirmed-only snapshot（PROMPT-04）。

    返回 None 当两个 registry 文件都不存在（graceful-degrade —— asset byte-identical
    到 v1.0；registry_snapshot 字段 OMITTED，schema optional）。
    confirmed-only hard filter（Pitfall 7 consistent —— 与 attach_refs._load_registry +
    apply_edits.py build-time hard gate + _producer_registry_integrity second-line assert
    对齐；非-confirmed 绝不进 snapshot）。
    representative_image 仅当 truthy 时 emit（Phase 7 WARNING-2：apply_edits 在 ffmpeg
    失败时 OMIT representative_image —— snapshot 不携带 dangling path）。

    Phase 8 REVIEW WR-05 fix：malformed JSON（JSONDecodeError / OSError）或 schema-
    invalid 的 canonical registry 文件不再静默降级为空 snapshot（旧行为会把 corruption
    伪装成 "该视频零角色/零道具" 持久化到 asset.json，下游不可见）。改为：
      * print [warn] 行（mirror line 437 sidecar pattern）
      * 返 None → registry_snapshot 字段 OMITTED（不持久化空 snapshot 掩盖 corruption）
    consistent with attach_refs.py WR-02 schema-gate + apply_edits.py WR-05 pre-write 防御。

    Returns:
        dict | None: {characters:[{id,name,representative_image?,appearance_shots}],
                      props:[{...}]} 或 None（两文件都缺席 / 任一文件 malformed）。
    """
    chars_path = os.path.join(work_dir, "characters.json")
    props_path = os.path.join(work_dir, "props.json")
    # 两文件都不存在 → snapshot OMITTED（graceful-degrade；schema optional）
    if not (os.path.isfile(chars_path) or os.path.isfile(props_path)):
        return None

    def _project(entries) -> list:
        """投影 confirmed-only compact shape（id/name/representative_image?/appearance_shots）。"""
        out = []
        if isinstance(entries, list):
            for e in entries:
                if not isinstance(e, dict):
                    continue
                # Pitfall 7 —— confirmed-only snapshot（与 build-time hard gate 对齐）
                if e.get("review_state") != "confirmed":
                    continue
                # representative_image 仅当 truthy（WARNING-2：apply_edits 在 ffmpeg
                # 失败时 OMIT；snapshot 不携带 dangling path）
                out.append({
                    "id": e.get("id"),
                    "name": e.get("name"),
                    **({"representative_image": e["representative_image"]}
                       if e.get("representative_image") else {}),
                    "appearance_shots": e.get("appearance_shots") or [],
                })
        return out

    # Phase 8 REVIEW WR-05 fix：任一侧 malformed → 整 snapshot OMITTED（不再返部分空的
    # snapshot dict）。先尝试 load + schema-validate 每一侧；任一失败 print [warn]
    # 并立即返 None。schema-validate mirror attach_refs._validate_registry（WR-02）。
    loaded: dict = {}
    for path, schema_path, key, label in (
            (chars_path, CHARACTERS_SCHEMA, "characters", "characters.json"),
            (props_path, PROPS_SCHEMA, "props", "props.json")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _validate_registry_for_snapshot(schema_path, data, label)
            loaded[key] = _project(data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warn] {label} malformed → registry_snapshot will be OMITTED: {e}")
            return None
        except _SchemaInvalid as e:
            print(f"[warn] {label} schema-invalid → registry_snapshot will be OMITTED: "
                  f"{e.errors[0] if e.errors else e}")
            return None
    return loaded


def build_asset_dict(work_dir: str, video_path: str,
                     warnings: list[str] | None = None) -> dict:
    """从现有 pipeline 产物组装 asset.json dict。

    字段 sourcing（全部对照 output/《小江湖》第03话…/ 实际产物验证过）：
      * schema_version: SCHEMA_VERSION 常量（当前 "1.3"；v1.0 minimal fixture 仍是 "1"，producer emit 的真实资产从此为 "1.3"）
      * asset_type: const "shottimeline"
      * source.video_filename: basename(video_path)；与 transcript.source 交叉
        校验（不一致仅 warn，不 fail）
      * source.duration_sec: transcript.duration 优先；缺失回退 _probe_duration
      * generator.tool: 字面量 "kais-shot-timeline"
      * generator.version: _git_sha() 短 SHA（失败 "dev"）
      * generator.generated_at: UTC ISO-8601（带 Z 后缀）
      * generator.warnings: 仅当 warnings 非空 list 时 emit（Phase 6 增量，v1.1 optional）。
        None / [] → 字段缺省（schema 合法；老资产 + 干净运行保持缺省）。
        来源：main() 读 route_cache/warnings.json sidecar（best-effort，由
        analysis/call_shot_analysis.py 写入 step_semantic 路由失败原因）。
      * data.*: 5 个数据 JSON 的字面量相对路径
      * media.video: 字面量 "video.mp4"
      * media.stems.*: 字面量 "stems/<name>.wav"（bass 不在内）

    Args:
      work_dir: 资产根目录（含 5 个数据 JSON + route_cache/ sidecar）。
      video_path: 原始视频绝对路径（含 audio 流）。
      warnings: 可选非致命警告字符串列表；非空时 emit 为 generator.warnings，
        None 或空列表时该字段 OMITTED（schema optional，graceful-degrade default）。
    """
    with open(os.path.join(work_dir, "transcript.json"), encoding="utf-8") as f:
        transcript = json.load(f)

    video_filename = os.path.basename(video_path)
    # 完整性交叉校验：transcript.source 与 video basename 应一致。
    # 不一致仅 warn（不 fail）—— 让用户看到但不阻塞导出。
    if transcript.get("source") and transcript["source"] != video_filename:
        print(f"[warn] transcript.source={transcript['source']!r} != "
              f"video basename={video_filename!r}")

    duration = transcript.get("duration")
    if not duration:
        duration = _probe_duration(video_path)

    # Phase 7: 把 data + media 块先建成局部 dict，再条件性 append characters/props
    # （CONTRACT-06 closure）。直接 mutate 字面量会让老资产在 "无 registry" 分支
    # 仍可能携带空 characters/props 字段（一旦 .get("characters") 之类的中间操作
    # 误触）；局部 dict + 组装时再决定是否赋值，保证「文件缺席 → 字段缺席」byte-identical。
    data_block = {
        "shots": "shots.json",
        "audio_analysis": "audio_analysis.json",
        "transcript": "transcript.json",
        "frames": "frames.json",
        "prompts": "prompts.json",
    }
    media_block = {
        "video": "video.mp4",
        "stems": {
            "vocals": "stems/vocals.wav",
            "drums": "stems/drums.wav",
            "other": "stems/other.wav",
        },
    }

    # Phase 7: CONDITIONAL characters/props emission (CONTRACT-06 closure).
    # 仅当 canonical 文件存在才 emit —— 老 assets (无 registry) 保持 byte-identical
    # 到 v1.0（字段 OMITTED；schema optional）。canonical 文件由 registry/apply_edits.py
    # 在 HITL 审阅后产出（Plan 03）。Route-down degrade → characters.json/props.json
    # 缺席 → export 仍合法（graceful-degrade，CAST-09）。
    chars_path = os.path.join(work_dir, "characters.json")
    props_path = os.path.join(work_dir, "props.json")
    if os.path.isfile(chars_path):
        data_block["characters"] = "characters.json"
    if os.path.isfile(props_path):
        data_block["props"] = "props.json"

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

    # Phase 18: CONDITIONAL data.roundtrip object mount (RT-01/RT-02)。mirror Phase 11
    # 条件发射模式，但值是 object（v1.x 首个）：file ref + verdict 统计。仅当
    # roundtrip.json 存在且可 JSON 解析（top-level 为 dict）才 emit —— 未跑 round-trip
    # 的 degrade 保持 byte-identical-absent（字段 OMITTED；schema optional）。
    # malformed / 非 dict → [warn] + OMIT（mirror _build_registry_snapshot WR-05
    # 「不持久化可疑统计」）。此处只做 JSON-parse + verdict 计数，不做完整 schema
    # 校验（Open Q3 锁定：schema gate 在 validate.py V13 / verify_contract producer
    # mode，export 内重复校验收益低）。verdict 缺席或 decision 非_accepted/_rejected
    # 的 shot 不计入（best-effort 计数）。
    roundtrip_path = os.path.join(work_dir, "roundtrip.json")
    if os.path.isfile(roundtrip_path):
        try:
            with open(roundtrip_path, encoding="utf-8") as f:
                rt = json.load(f)
            if not isinstance(rt, dict):
                raise ValueError(
                    f"top-level is {type(rt).__name__}, expected object")
            counts = {"accepted": 0, "rejected": 0}
            for s in rt.get("shots") or []:
                if not isinstance(s, dict):
                    continue  # 非法条目不计（计数是 best-effort）
                verdict = s.get("verdict")
                if isinstance(verdict, dict) and verdict.get("decision") in counts:
                    counts[verdict["decision"]] += 1
            data_block["roundtrip"] = {
                "path": "roundtrip.json",
                "accepted_count": counts["accepted"],
                "rejected_count": counts["rejected"],
            }
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"[warn] roundtrip.json malformed → data.roundtrip will be OMITTED: {e}")

    # media.characters[]/media.props[] —— 枚举实际存在的 PNG（canonical 命名）。
    # glob 只返回存在的文件，所以 list 内不会有 dangling path。Pre-write assert
    # 是 race / 手动删除的 defense-in-depth（apply_edits 写完 PNG 后立刻被外部删
    # 才会触发，极罕见）。
    char_pngs = sorted(glob.glob(os.path.join(work_dir, "characters", "*.png")))
    if char_pngs:
        media_block["characters"] = [
            f"characters/{os.path.basename(p)}" for p in char_pngs]
    prop_pngs = sorted(glob.glob(os.path.join(work_dir, "props", "*.png")))
    if prop_pngs:
        media_block["props"] = [
            f"props/{os.path.basename(p)}" for p in prop_pngs]

    # Pre-write assert: every media.characters[]/media.props[] PNG resolves.
    # CAST-09 graceful-degrade: NON-FATAL for character/prop PNGs（WARNING-2 fix）。
    # apply_edits.py 在 ffmpeg 失败时 OMIT representative_image + 不写 PNG，所以
    # glob-derived list 正常情况不会 dangling。这里是 race 兜底 —— 把缺失记进
    # warnings（若有 warnings 通道）+ 继续 export，不 sys.exit。stems/video 的
    # pre-write assert（在 main()）保持 FATAL —— 那些是 required + always present。
    # NOTE: warnings mutation 在 return 字典冻结前完成，warning 会进 generator.warnings。
    for rel in (media_block.get("characters", [])
                + media_block.get("props", [])):
        p = os.path.join(work_dir, rel)
        if not os.path.exists(p):
            _msg = (f"character/prop PNG missing before write: {rel} "
                    f"(expected at {p})")
            if warnings is not None:
                warnings.append(_msg)
            # 不 sys.exit —— CAST-09 graceful-degrade（asset 仍导出）

    # Phase 8 (PROMPT-04): registry_snapshot —— 冻结 confirmed-only compact view。
    # 调用 ONCE 存局部变量（避免重复读文件）。None when 两 registry 文件都不存在
    # （graceful-degrade —— 老 assets byte-identical 到 v1.0；snapshot OMITTED）。
    snapshot = _build_registry_snapshot(work_dir)

    return {
        "schema_version": SCHEMA_VERSION,
        "asset_type": "shottimeline",
        "source": {
            "video_filename": video_filename,
            "duration_sec": duration,
        },
        "generator": {
            "tool": "kais-shot-timeline",
            "version": _git_sha(),
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            # Phase 6: 仅当 warnings 非空 list 时 emit；None / [] → OMITTED
            # （generator.warnings 是 v1.1 optional，schema accepts both ways；
            #   graceful-degrade default = 干净运行缺省，老资产不受影响）。
            # Phase 7: 上方 character/prop PNG race-detection 也 append 到 warnings。
            **({"warnings": warnings} if warnings else {}),
            # Phase 8 (PROMPT-04): registry_snapshot —— additive conditional emit
            # （mirror Phase 6 warnings 模式）。None → OMITTED（老 assets / 无 re-id
            # degrade 保持 byte-identical；schema optional）。非-None 时含 confirmed-only
            # compact view（Pitfall 7 + WARNING-2 已在 _build_registry_snapshot 内处理）。
            **({"registry_snapshot": snapshot} if snapshot is not None else {}),
        },
        "data": data_block,
        "media": media_block,
    }


def main():
    ap = argparse.ArgumentParser(
        description="ShotTimelineAsset 导出器（manifest 写入 + canonical symlinks + inline jsonschema 自校验）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/，含 5 个数据 JSON）")
    ap.add_argument("--video", required=True,
                    help="原始视频绝对路径（含 audio 流；非 h264.mp4）")
    ap.add_argument("--stems-source-dir", required=True,
                    help="Demucs 输出 stems 目录（stems/htdemucs/<video-stem>/）")
    ap.add_argument("--output", required=True,
                    help="asset.json 写入路径（通常 <work-dir>/asset.json）")
    ap.add_argument("--force", action="store_true",
                    help="若 output 已存在则先删除再写（canonical symlinks 由 ensure_symlink 幂等处理）")
    args = ap.parse_args()

    # 路径绝对化：symlink target 必须是 abs path，否则会相对「symlink 所在目录」
    # 解析（不是 cwd）—— 相对 target 会让 stems/vocals.wav 解析到
    # stems/./output/.../vocals.wav 这种不存在的路径。video 同理（RESEARCH Pitfall 1）。
    work_dir = os.path.abspath(args.work_dir)
    video = os.path.abspath(args.video)
    stems_source_dir = os.path.abspath(args.stems_source_dir)
    output = os.path.abspath(args.output)

    # (a) 5 个数据 JSON 存在性 guard —— asset.schema.json 的 data.* 全部 required
    # （schema 第 61 行：required: shots/audio_analysis/transcript/frames/prompts）。
    # 任何缺失都 fail loud —— 不静默写入引用不存在文件的 manifest（02-REVIEW WR-02：
    # 原实现只 guard 了 prompts.json，其余 4 个缺失会让 schema 通过但下游崩）。
    # prompts.json 由独立步骤产出（未接入 run_pipeline），其余 4 个由 step_* 产出。
    required_data = ("shots.json", "audio_analysis.json", "transcript.json",
                     "frames.json", "prompts.json")
    for name in required_data:
        p = os.path.join(work_dir, name)
        if not os.path.exists(p):
            field = name.removesuffix(".json")
            if name == "prompts.json":
                hint = ("  prompts.json 当前由独立步骤产出（未接入 run_pipeline）；"
                        "请先就位再运行导出。\n")
            else:
                hint = ("  若是用 --skip-* 跳过了对应步骤，请先就位再运行导出。\n")
            sys.exit(
                f"{name} 不存在: {p}\n"
                f"  asset.schema.json 的 data.{field} 是 required 字段 —— 不可省略。\n"
                + hint)

    # (b) video 存在性
    if not os.path.exists(video):
        sys.exit(f"input video not found: {video}")

    # (c) 验证 video 含 audio 流（02-RESEARCH Pitfall 1 关键修复）
    # h264.mp4 是 -an 去 audio 的转码中间产物 —— video.mp4 symlink 决不能指它。
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", video], capture_output=True, text=True)
    # 02-REVIEW WR-04：先看 returncode —— ffprobe 失败（corrupt video、权限、PATH
    # 问题）时 stdout 为空，不查 returncode 会错误触发"no audio stream"，把用户
    # 带偏到 transcode -an 调试路径。真实原因是 ffprobe 没跑起来。
    if r.returncode != 0:
        sys.exit(
            f"ffprobe failed (rc={r.returncode}): {video}\n"
            f"  stderr: {r.stderr.strip() or '(empty)'}")
    if "audio" not in r.stdout:
        sys.exit(
            f"video has no audio stream: {video}\n"
            f"  (h264.mp4 transcode was -an stripped — exporter needs original)")

    # (d) stems/ 子目录
    os.makedirs(os.path.join(work_dir, "stems"), exist_ok=True)

    # (e) 4 个 canonical symlinks
    #   video.mp4 → 原始视频 abs path（NOT work_dir 内的 <original-name>.mp4，
    #   后者链到 -an 去 audio 的 h264.mp4 —— 会让消费者听不到声音）
    #   target 必须是 abs path —— 相对 target 会按「symlink 所在目录」解析（非 cwd）。
    ensure_symlink(os.path.join(work_dir, "video.mp4"), video)
    ensure_symlink(
        os.path.join(work_dir, "stems", "vocals.wav"),
        os.path.join(stems_source_dir, "vocals.wav"))
    ensure_symlink(
        os.path.join(work_dir, "stems", "drums.wav"),
        os.path.join(stems_source_dir, "drums.wav"))
    ensure_symlink(
        os.path.join(work_dir, "stems", "other.wav"),
        os.path.join(stems_source_dir, "other.wav"))
    # 不创建 stems/bass.wav —— schema 拒绝 + 前端只渲染 3 stems。
    # htdemucs 原始 bass.wav 在 stems-source-dir 中保持不动（additive-only）。

    # (f) --force 清空已存在的 output
    if args.force and os.path.exists(output):
        os.unlink(output)

    # (f.5) Phase 6: best-effort 读取 step_semantic 写的 warnings sidecar
    # （route_cache/warnings.json — 由 analysis/call_shot_analysis.py 在路由
    #   不可达 / per-shot 失败时写入；live route round-trip 未达时也可能缺省）。
    # ANY OSError / JSONDecodeError / 缺失文件 → warnings=None（silent fallback）：
    # exporter 不能因 sidecar 损坏而中断资产导出（graceful-degrade）。
    warnings_sidecar = os.path.join(work_dir, "route_cache", "warnings.json")
    warnings = None
    if os.path.exists(warnings_sidecar):
        try:
            with open(warnings_sidecar, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                candidate = loaded.get("warnings")
                # v1.3 加宽（RT-04 degrade 记因通道）：接受 list[str | {code, detail}]
                # （结构化条目来自 Phase 20 regen 客户端）；非合规形状整体回退 None
                # （silent-fallback 语义不变）。[] → None 的空列表 collapse 在
                # _valid_warnings_list 内完成（缺省，不 emit）。
                warnings = _valid_warnings_list(candidate)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warn] route_cache/warnings.json malformed → ignoring: {e}")

    # (g) 构建 manifest dict（warnings 非空时 emit generator.warnings）
    asset = build_asset_dict(work_dir, video, warnings=warnings)

    # (g0) duration_sec > 0 hard check —— asset.schema.json 仅约束 minimum:0，
    # schema 校验放过 0；但下游消费者拿到 duration_sec=0 会渲染失败。
    # 02-REVIEW WR-03：transcript.duration 缺失 + ffprobe 失败时 _probe_duration
    # 静默返回 0.0（低阶 helper 沿用项目惯例），exporter 必须把它当硬错误。
    if not asset["source"]["duration_sec"]:
        sys.exit(
            f"无法确定视频时长：duration_sec=0\n"
            f"  video={video}\n"
            f"  transcript.json 无 duration 字段，且 ffprobe 兜底失败（rc≠0 或 stdout 解析失败）。\n"
            f"  duration_sec 是 asset.schema.json 的 required 字段，不可为 0 —— "
            f"请检查 ffprobe 是否在 PATH、video 是否可读。")

    # (g') Pre-write assert：4 个 canonical paths 都 resolve 到真实文件
    # 必须在 write 之前 —— 否则 dangling-symlink 的 manifest 已经落盘，下游看到
    # schema-valid 但指向不存在媒体的文档（02-REVIEW WR-01）。
    # step (e) 已建好 symlink，这里只是兜底断言；schema 校验只看 path 字符串
    # pattern，验不出 dangling symlink。
    for rel in ("video.mp4", "stems/vocals.wav", "stems/drums.wav", "stems/other.wav"):
        p = os.path.join(work_dir, rel)
        if not os.path.exists(p):
            sys.exit(f"canonical path missing before write: {rel} (expected at {p})")

    # (i') inline schema 自校验（在写入之前 —— invalid 时 helper 内 sys.exit 非 0，
    # 避免 schema-invalid manifest 落盘被下游读到）
    validate_asset_json(asset)

    # (h) 原子写入（temp + os.replace）—— 避免 partial-write 状态被下游读到
    # （02-REVIEW WR-01）。ensure_ascii=False 强制 —— Chinese video_filename。
    tmp = output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)
    os.replace(tmp, output)

    # (k) Final-status print（CLAUDE.md bracketed-tag 惯例）
    print(f"[export-asset] wrote asset.json → {output}")
    print(f"[export-asset] canonical symlinks: video.mp4, stems/{{vocals,drums,other}}.wav")


if __name__ == "__main__":
    main()
