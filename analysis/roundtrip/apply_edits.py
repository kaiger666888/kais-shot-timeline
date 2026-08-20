#!/usr/bin/env python3
"""analysis/roundtrip/apply_edits.py — 把 HITL 审阅决定 (roundtrip-edits.json)
应用到 roundtrip.json verdict 半边的 confirmed-only 回写 CLI（PRESENT-01 回写半边）。

本脚本是 **独立 standalone CLI**（mirror registry/apply_edits.py 先例：非阻塞 ——
run_pipeline.py 永远不调用它；操作员在审阅完 html/gen_roundtrip_review.py 产出的
HITL 面板、导出 roundtrip-edits.json 后手动运行）。

与 judge.apply_verdict 的关键语义差（CONTEXT lock，本 CLI 的存在理由）：
    judge（judge.py:530-532）—— 预存 verdict（auto 或 human）一律跳过（冻结）；
    本 CLI 恰相反 —— human 覆盖是**唯一**允许替换已冻结 verdict 的路径。
    edits 命中的镜 verdict 半边替换为 {decision, source:"human", decided_at}；
    该镜 regen/scores/status 半边与其余全部镜 byte 级保留（READ-merge）。

流程固定序（mirror registry/apply_edits.py :275-509 骨架）：

    1. edits 过 roundtrip-edits.schema.json Draft202012Validator 预校验
       （T-22-05：坏 edits sys.exit 非零——此刻 sidecar 零改动，confirmed-only 硬门）
    2. accept/reject 两清单交集检查（同一 shot 双向覆盖 → sys.exit fail-loud）
    3. 读 roundtrip.json（缺席/损坏 → sys.exit）
    4. 逐条 shot_id 存在检查（未知 id → sys.exit 列出，typo 防护）
    5. 逐镜覆盖 + 审计行 + idempotency guard（A3）：
       已 human 且同 decision → 跳过不写（decided_at 不漂移，重放 byte no-op）
    6. READ-merge 写回（kept-keys merge；坏既有条目 .bak-<ts> 备份 mirror scorer
       惯例）→ 合并 payload 过 h3s._iter_sidecar_errors 两层校验 → 原子写

Idempotent：同 edits 重放第二遍是 no-op diff——全跳过时不重写 sidecar
（连 mtime 都不动）。审计行逐镜打印，收尾打印计数汇总。

用法：
    python3 analysis/roundtrip/apply_edits.py \\
        --work-dir  <abs path>   (必填 — output/<video-stem>/，roundtrip.json 所在) \\
        --edits     <abs path>   (必填 — roundtrip-edits.json，HITL 面板导出)

退出码：0 成功（含空 {} no-op 与全跳过重放）；非零 = edits schema 校验失败 /
交集冲突 / 未知 shot_id / sidecar 缺席损坏 / 合并校验失败（以上任一发生时
sidecar 保持原字节不动——写盘只发生在全部检查通过之后）。
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

# h3_regen 共享件经 importlib 文件加载（mirror judge.py:100-103 单源不漂移；
# 模块级无副作用、main 有 guard，加载安全）。本模块用：
#   h3s._load_schema_version（export_asset SCHEMA_VERSION 单源）
#   h3s._iter_sidecar_errors（roundtrip.schema.json 两层自校验）
#   h3s._atomic_write_json（PID-tmp + os.replace 原子写）
#   h3s.append_roundtrip_warnings（route_cache/warnings.json strip-append）
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)

# ─── 模块级常量 ─────────────────────────────────────────────────────────────

STEP_TAG = "[roundtrip-apply]"

# edits schema（registry-edits 直系变体；**三层 parent**——本模块在
# analysis/roundtrip/ 下，repo root 必须 parent.parent.parent，off-by-one 陷阱
# mirror h3_regen.SCHEMA_PATH 注释）。
EDITS_SCHEMA = (Path(__file__).resolve().parent.parent.parent
                / "spec" / "schemas" / "roundtrip-edits.schema.json")


# ─── 小工具 ─────────────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    """UTC ISO-8601 秒精度（decided_at 留档；mirror judge.py:321-323）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _validate_edits(instance) -> None:
    """edits schema 预校验 —— fails loud（mirror registry/apply_edits.py:239-259）。

    lazy-import jsonschema；iter_errors 前 10 条拼进退出消息。此刻 sidecar
    尚未被读——confirmed-only 硬门的第一道闸（T-22-05）。
    """
    from jsonschema import Draft202012Validator
    with open(EDITS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    if errors:
        msgs = [f"  - [{'/'.join(str(p) for p in e.absolute_path) or '<root>'}] {e.message}"
                for e in errors[:10]]
        sys.exit(
            f"{STEP_TAG} FAIL: roundtrip-edits.schema.json 校验失败 "
            f"（{len(errors)} errors，sidecar 零改动）:\n" + "\n".join(msgs)
            + (f"\n  ... and {len(errors) - 10} more" if len(errors) > 10 else ""))


def _read_json_file(path: str, what: str) -> object:
    """读 JSON 文件；缺席/损坏 → sys.exit（fail-loud，不静默兜空）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"{STEP_TAG} FAIL: 无法读取 {what}: {path}（{type(e).__name__}: {e}）")


def _validate_entries_batch(entries: list, schema_version: str) -> None:
    """① 本批 entries 单独校验（fail-loud——WR-04 第一层；本批数据坏是本 CLI
    自己的问题，重试前必须修，绝不落盘）。"""
    own_errors = h3s._iter_sidecar_errors(
        {"schema_version": schema_version, "shots": entries})
    if own_errors:
        detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                           for e in own_errors[:3])
        sys.exit(f"{STEP_TAG} FAIL: 本批 verdict 条目 schema 校验失败"
                 f"（{len(own_errors)} 错误，拒绝落盘）: {detail}")


def apply_edits(work_dir: str, edits: dict) -> int:
    """edits → roundtrip.json verdict 半边 human 覆盖（confirmed-only 主流程）。

    返回 0；一切失败路径经 sys.exit（非零退出码 + sidecar 原字节不动）。
    """
    # ── 1. schema 预校验（硬门第一道闸）────────────────────────────────────
    _validate_edits(edits)

    # ── 2. 交集检查（同一 shot 双向覆盖 = edits 自相矛盾 → fail-loud）─────
    accept_ids = sorted({int(x) for x in edits.get("accept_overrides") or []})
    reject_ids = sorted({int(x) for x in edits.get("reject_overrides") or []})
    inter = sorted(set(accept_ids) & set(reject_ids))
    if inter:
        sys.exit(f"{STEP_TAG} FAIL: shot {inter} 同时出现在 accept_overrides 与 "
                 f"reject_overrides（交集冲突，sidecar 零改动）——面板导出的 "
                 f"edits 不应出现，请检查文件是否被手改")

    # ── 3. 读 sidecar（缺席/损坏/形状不对 → fail-loud）────────────────────
    sidecar_path = os.path.join(work_dir, "roundtrip.json")
    existing = _read_json_file(sidecar_path, "roundtrip.json sidecar")
    if not isinstance(existing, dict) or not isinstance(existing.get("shots"), list):
        sys.exit(f"{STEP_TAG} FAIL: {sidecar_path} 形状不对（top-level 应为 "
                 f"object 且 shots 为 array）")

    schema_version = h3s._load_schema_version()

    # ── 4. 逐条 shot_id 存在检查（typo 防护）─────────────────────────────
    merged: dict[int, dict] = {}
    malformed: list[str] = []
    for s in existing["shots"]:
        if isinstance(s, dict) and isinstance(s.get("shot_id"), int):
            merged[int(s["shot_id"])] = s
        else:
            # 形状非法的预存条目——不静默丢弃（.bak 备份 + warning，mirror
            # scorer WR-04 惯例；见下文 malformed flush）。
            malformed.append(str(s)[:120])
    known = set(merged)
    targets = ([(sid, "accepted") for sid in accept_ids]
               + [(sid, "rejected") for sid in reject_ids])
    unknown = sorted({sid for sid, _ in targets if sid not in known})
    if unknown:
        sys.exit(f"{STEP_TAG} FAIL: 未知 shot_id {unknown}（sidecar 现存 "
                 f"{sorted(known)}，sidecar 零改动）——roundtrip.json 只收录有 "
                 f"regen 产物的镜；请核对面板导出的 edits")

    # ── 5. 逐镜覆盖 + idempotency guard（A3）+ 审计行 ─────────────────────
    entries: list[dict] = []
    applied = 0
    same_replay = 0
    for sid, decision in targets:
        prev = merged.get(sid) or {}
        prev_verdict = prev.get("verdict") if isinstance(prev.get("verdict"), dict) else None
        if (prev_verdict is not None
                and prev_verdict.get("source") == "human"
                and prev_verdict.get("decision") == decision):
            # 已 human 且同 decision → 跳过不写（decided_at 不漂移——重放
            # byte 级 no-op 的实现基础；与 judge frozen-skip 的「跳过」语义
            # 对齐但判据不同：human 显式态允许重放确认）。
            same_replay += 1
            print(f"{STEP_TAG} shot_{sid:03d} 已 human 同 decision 跳过（human/{decision}）")
            continue
        prev_source = prev_verdict.get("source") if prev_verdict is not None else "none"
        entries.append({"shot_id": sid, "verdict": {
            "decision": decision,
            "source": "human",            # human 覆盖是唯一冻结替换路径
            "decided_at": _utc_now_iso(),
        }})
        applied += 1
        print(f"{STEP_TAG} shot_{sid:03d} {prev_source}→human/{decision}")
    skipped = len(targets) - applied - same_replay   # 结构上恒 0；防御性记账

    if not entries:
        # 空 {} edits 或全跳过重放 → 真 no-op：不读后续校验不写盘（mtime 不动）。
        print(f"{STEP_TAG} 完成：applied={applied} same_decision_replay={same_replay} "
              f"skipped={skipped}（无写入，sidecar 原样）")
        return 0

    # ── 6. READ-merge + 两层校验 + 原子写 ─────────────────────────────────
    # ① 本批 verdict 条目单独校验（fail-loud）
    _validate_entries_batch(entries, schema_version)
    # verdict 半边替换（语义反转点：不 pop、不冻结——human 覆盖生效）；其余
    # 半边与未命中镜 byte 级保留（dict 原位赋值保持既有键序）。
    for e in entries:
        sid = int(e["shot_id"])
        prev = dict(merged.get(sid) or {})
        prev["verdict"] = e["verdict"]
        merged[sid] = prev
    warnings: list = []
    if malformed:
        import shutil
        bak = f"{sidecar_path}.bak-{int(time.time())}"
        if os.path.isfile(sidecar_path):
            shutil.copy2(sidecar_path, bak)
        for s in malformed:
            warnings.append(
                f"{STEP_TAG} roundtrip.json 预存条目形状非法（非 dict 或 "
                f"shot_id 非整数），本次写入已丢弃（原文件备份 "
                f"{os.path.basename(bak)}，人工数据未销毁）: {s}")
    payload = {"schema_version": schema_version,
               "shots": [merged[k] for k in sorted(merged)]}
    # ② 合并校验：预存坏条目归因 shot_id → warning + 剔除 + 备份 → 复验
    errors = h3s._iter_sidecar_errors(payload)
    if errors:
        bad_ids: set[int] = set()
        for err in errors:
            parts = list(err.absolute_path)
            if (len(parts) >= 2 and parts[0] == "shots"
                    and isinstance(parts[1], int)
                    and 0 <= parts[1] < len(payload["shots"])):
                shot = payload["shots"][parts[1]]
                if isinstance(shot, dict) and isinstance(shot.get("shot_id"), int):
                    bad_ids.add(int(shot["shot_id"]))
        if not bad_ids:
            detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                               for e in errors[:3])
            sys.exit(f"{STEP_TAG} FAIL: roundtrip.json schema 校验失败"
                     f"（{len(errors)} 错误，且无法归因到预存条目，拒绝落盘）: {detail}")
        import shutil
        bak = f"{sidecar_path}.bak-{int(time.time())}"
        if os.path.isfile(sidecar_path):
            shutil.copy2(sidecar_path, bak)          # 被剔除条目人工数据可找回
        for sid in sorted(bad_ids):
            warnings.append(
                f"{STEP_TAG} roundtrip.json 预存条目 shot {sid} 违反当前 schema"
                f"——本次写入已剔除该条目（原文件备份 {os.path.basename(bak)}，"
                f"人工数据未销毁）")
            merged.pop(sid, None)
        payload = {"schema_version": schema_version,
                   "shots": [merged[k] for k in sorted(merged)]}
        errors = h3s._iter_sidecar_errors(payload)
        if errors:
            detail = "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                               for e in errors[:3])
            sys.exit(f"{STEP_TAG} FAIL: 剔除预存坏条目后仍校验失败"
                     f"（{len(errors)} 错误，拒绝落盘）: {detail}")
    h3s._atomic_write_json(sidecar_path, payload)
    if warnings:
        h3s.append_roundtrip_warnings(work_dir, warnings)
        for w in warnings:
            print(w)
    print(f"{STEP_TAG} 完成：applied={applied} same_decision_replay={same_replay} "
          f"skipped={skipped} → {sidecar_path}")
    return 0


# ─── CLI entry point ────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "把 HITL 审阅决定 (roundtrip-edits.json) 应用到 roundtrip.json "
            "verdict 半边（confirmed-only；human 覆盖是唯一允许替换已冻结 "
            "verdict 的路径）。独立 CLI —— run_pipeline.py 不调用；操作员在"
            "审阅 HITL 面板后手动运行。"))
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— roundtrip.json 所在")
    ap.add_argument("--edits", required=True,
                    help="roundtrip-edits.json 路径（HITL 面板 exportEdits 导出）")
    args = ap.parse_args(argv)

    edits = _read_json_file(args.edits, "roundtrip-edits.json（HITL 面板导出）")
    if not isinstance(edits, dict):
        sys.exit(f"{STEP_TAG} FAIL: {args.edits} top-level 应为 object")
    return apply_edits(args.work_dir, edits)


if __name__ == "__main__":
    sys.exit(main())
