#!/usr/bin/env python3
"""registry/apply_edits.py — 把 HITL 审阅决定 (registry.edits.json) 应用到 re-id 草稿
(registry.draft.json) 上，产出 canonical characters.json + props.json + 代表帧 PNG。

本脚本是 **独立 standalone CLI**（CONTEXT Q2 锁：非阻塞 —— run_pipeline.py 永远不调用它；
操作员在审阅完 html/gen_registry_review.py 产出的 HITL HTML 后手动运行）。

应用顺序（LOCKED — CONTEXT Q2 + RESEARCH Pattern 3；保证 deterministic + idempotent）：

    1. merge_groups   —— 多 cluster 合并（首个 ID 作 canonical，其余软退役；mean_cosine 平均）
    2. splits         —— 单 cluster 拆分为 N 个（确定性新 ID：max_existing_N + 1）
    3. renames        —— 重命名（在 build-entry 时应用，不改 cluster_id）
    4. type_overrides —— 改 cluster_id prefix（char_ ↔ prop_），数字保留
    5a. confirm_ids   —— 标记 review_state = "confirmed"
    5b. reject_ids    —— 标记 review_state = "rejected"（软删除，ID 保留以维护引用完整性）

HARD GATE (Pitfall 7)：build canonical entries 时 `if review_state != "confirmed": continue`
（hard skip，NOT filter-after-write）。proposed/rejected 永不流向下游 characters.json/props.json。

代表性 PNG (CAST-08 producer-side fallback)：对每个 confirmed 条目，挑 best member
(最高 mask_quality；无信号时首 member)，经 ffmpeg 抽帧 → characters/<id>.png 或 props/<id>.png。
ffmpeg 失败时 (timeout/nonzero rc/zero-byte 输出) **OMIT** representative_image 字段
(schema-optional，下游 export_asset.py 的 glob 自然跳过 → 无 dangling path —— WARNING-2 fix)。

用法：
    python registry/apply_edits.py \\
        --draft     <abs path>   (必填 — registry.draft.json，step_reid 产物) \\
        --edits     <abs path>   (必填 — registry.edits.json，HITL HTML 导出) \\
        --work-dir  <abs path>   (必填 — output/<asset>/；characters.json + props.json + characters/ + props/ 写入此目录) \\
        --video     <abs path>   (必填 — 原视频，ffmpeg 抽帧用) \\
        --shots     <abs path>   (必填 — shots.json，frame_pos → 时间戳解析)

退出码：0 成功；非零 = schema 校验失败 (edits 或 canonical 输出无效) 或 confirmed-only gate 违反
(后者在 well-formed edits 下不可能触发 —— hard assert 是 defense-in-depth)。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ============================================================================
# Module-level constants
# ============================================================================

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

CHARACTERS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "characters.schema.json"
PROPS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "props.schema.json"
REGISTRY_EDITS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "registry-edits.schema.json"

# Best-member selection ranking for CAST-08 producer-side fallback.
# Lower rank = higher quality. Default (no signal / unknown value) = 3 (worst).
QUALITY_RANK = {"high": 0, "medium": 1, "low": 2, "unusable": 3}

# frame_pos keyword → shot-relative fraction (RESEARCH Pattern 4 lines 522-531).
_FRAME_POS_FRACTIONS = {
    "first": 0.0,
    "25%": 0.25,
    "50%": 0.5,
    "75%": 0.75,
    "last": 1.0,
}


# ============================================================================
# Helpers
# ============================================================================

def _resolve_frame_ts(shot_id, frame_pos, shots_meta):
    """frame_pos ('first'/'last'/'25%'/'50%'/'75%' 或 number) → 绝对秒数。

    若 shot_id 在 shots_meta 中找不到，返回 0.0 (advisory —— 不阻塞抽帧；
    ffmpeg -ss 0 抽首帧，可接受 fallback)。

    Args:
        shot_id:    int —— 交叉引用 shots.json#id。
        frame_pos:  str ('first'/'last'/'25%'/'50%'/'75%') 或 number (绝对秒)。
        shots_meta: list[dict] —— shots.json，每条 {id, start_sec, end_sec, duration}。

    Returns:
        float —— 绝对秒数。
    """
    shot = next((s for s in shots_meta if s.get("id") == shot_id), None)
    if not shot:
        return 0.0
    start = shot.get("start_sec", 0.0)
    end = shot.get("end_sec", start)
    # number → 绝对秒数（直接返回）
    if isinstance(frame_pos, (int, float)):
        return float(frame_pos)
    # string keyword → shot 内插值
    fraction = _FRAME_POS_FRACTIONS.get(str(frame_pos), 0.5)
    return float(start) + float(end - start) * fraction


def _next_id(prefix, existing_ids):
    """确定性 split ID 分配 —— Pitfall 5 idempotency guard。

    从 existing_ids 中筛出同 prefix 的 cluster_id，取其最大数字部分 +1，零填充 3 位返回。
    若无同 prefix ID，返回 f"{prefix}_001"。

    Args:
        prefix:        "char" 或 "prop"。
        existing_ids:  iterable[str] —— 当前所有 cluster_id 集合（含已被 merge/split 的）。

    Returns:
        str —— 新分配的 cluster_id，形如 "char_004" / "prop_007"。
    """
    max_n = 0
    prefix_ = prefix + "_"
    for cid in existing_ids:
        if not isinstance(cid, str) or not cid.startswith(prefix_):
            continue
        suffix = cid[len(prefix_):]
        try:
            n = int(suffix)
        except (ValueError, TypeError):
            continue
        if n > max_n:
            max_n = n
    return f"{prefix}_{max_n + 1:03d}"


def _build_char_entry(cluster, renames):
    """构建 canonical character 条目（review_state="confirmed" 硬编码 —— Pitfall 7 gate）。

    Args:
        cluster:  dict —— 至少含 cluster_id + members（来自 draft clusters 经 merge/split 后）。
        renames:  dict{cluster_id: new_name} —— 来自 edits.renames。

    Returns:
        dict —— canonical character entry。注意 _members 是 internal 字段
               (供后续 _extract_representative_png 用；写前必须 pop)。
    """
    cid = cluster["cluster_id"]
    default_name = f"角色 {cid[-3:]}"
    name = renames.get(cid, default_name)
    members = cluster.get("members", []) or []
    appearance_shots = sorted({m["shot_id"] for m in members if "shot_id" in m})
    return {
        "id": cid,
        "name": name,
        "representative_image": f"characters/{cid}.png",  # default; popped on ffmpeg failure
        "appearance_shots": appearance_shots,
        "review_state": "confirmed",  # HARD-CODED —— confirmed-only hard gate (Pitfall 7)
        "_members": list(members),  # internal; deleted before write
    }


def _build_prop_entry(cluster, renames):
    """构建 canonical prop 条目（review_state="confirmed" 硬编码 —— Pitfall 7 gate）。

    与 _build_char_entry 同构，差别在 default name "道具 <NNN>" + representative_image 用 props/ 前缀。
    """
    cid = cluster["cluster_id"]
    default_name = f"道具 {cid[-3:]}"
    name = renames.get(cid, default_name)
    members = cluster.get("members", []) or []
    appearance_shots = sorted({m["shot_id"] for m in members if "shot_id" in m})
    return {
        "id": cid,
        "name": name,
        "representative_image": f"props/{cid}.png",
        "appearance_shots": appearance_shots,
        "review_state": "confirmed",
        "_members": list(members),
    }


def _extract_representative_png(entry, work_dir, video, shots_meta):
    """对 confirmed entry 抽 best member 代表帧 → characters/<id>.png 或 props/<id>.png。

    best member 选择 (CAST-08 producer-side fallback)：按 QUALITY_RANK 取 rank 最小者
    (high=0 > medium=1 > low=2 > unusable=3；未知=3)。无信号时取首 member。

    ffmpeg invoked via arg-list form (list argv, never shell mode; T-07-13 mitigation)。
    timeout=10s (gen_timeline_html.py:979 + gen_shots_preview.py 已用惯例；T-07-16 DoS mitigation)。

    On ffmpeg success (rc=0 AND 文件存在 AND 非零字节)：保留 entry["representative_image"] (default 已设)。
    On ffmpeg failure：entry.pop("representative_image", None) —— OMIT 字段 (schema-optional；
                       不写 PNG —— export_asset.py glob 自然跳过 → 无 dangling path；WARNING-2 fix)。
    """
    cid = entry["id"]
    subdir = "characters" if cid.startswith("char_") else "props"
    out_dir = os.path.join(work_dir, subdir)
    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, f"{cid}.png")

    members = entry.get("_members") or []
    if not members:
        # 无 member 无法抽帧 —— 退化为 omit (schema-optional)
        entry.pop("representative_image", None)
        return

    # best member：min rank；并列时取首 (stable)
    best = min(members, key=lambda m: QUALITY_RANK.get(m.get("mask_quality", ""), 3))
    shot_id = best.get("shot_id")
    frame_pos = best.get("frame_pos", "first")
    ts = _resolve_frame_ts(shot_id, frame_pos, shots_meta)

    try:
        result = subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                                 "-frames:v", "1", "-q:v", "2", "-vf", "scale=480:-1",
                                 out_png, "-loglevel", "error"],
                                capture_output=True, timeout=10)
        ok = (result.returncode == 0
              and os.path.exists(out_png)
              and os.path.getsize(out_png) > 0)
    except (subprocess.TimeoutExpired, OSError):
        ok = False

    if ok:
        # default path 已设；保留 (canonical characters/<id>.png / props/<id>.png)
        entry["representative_image"] = f"{subdir}/{cid}.png"
    else:
        # ffmpeg 失败 —— OMIT representative_image (schema-optional；不写 dangling PNG)
        # 清理可能的零字节文件
        if os.path.exists(out_png) and os.path.getsize(out_png) == 0:
            try:
                os.unlink(out_png)
            except OSError:
                pass
        entry.pop("representative_image", None)


def _validate(schema_path, instance):
    """Schema 自校验 —— fails loud。lazy-import jsonschema (v1.0 baseline 4.26.0)。

    Args:
        schema_path: Path 对象。
        instance:    待校验的 Python 对象 (通常 list/dict)。

    On validation error: sys.exit non-zero with descriptive message。
    """
    from jsonschema import Draft202012Validator
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    if errors:
        msgs = [f"  - [{'/'.join(str(p) for p in e.absolute_path) or '<root>'}] {e.message}"
                for e in errors[:10]]
        sys.exit(
            f"[apply-edits] FAIL: {schema_path.name} validation failed "
            f"({len(errors)} errors):\n" + "\n".join(msgs)
            + (f"\n  ... and {len(errors) - 10} more" if len(errors) > 10 else "")
        )


def _atomic_write(path, data):
    """原子写：temp + os.replace (POSIX atomic；防 partial-write 状态)。"""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ============================================================================
# Core apply function (RESEARCH Pattern 3 lines 449-513)
# ============================================================================

def apply_edits(draft_path, edits_path, work_dir, video, shots_path):
    """draft + edits → canonical characters.json + props.json + representative PNGs。

    应用顺序 (LOCKED)：merge → split → rename → type_override → confirm/reject。
    confirmed-only HARD GATE (Pitfall 7) at build-entry time。
    Idempotent：同 draft+edits 重复 apply 产生 byte-identical canonical 文件 (Pitfall 5 guard)。

    Args:
        draft_path:  abs path to registry.draft.json (Plan 02 产物)。
        edits_path:  abs path to registry.edits.json (HITL HTML 导出)。
        work_dir:    abs path to output dir (characters.json/props.json/characters//props/ 写入此)。
        video:       abs path to original video (ffmpeg 抽帧用)。
        shots_path:  abs path to shots.json (frame_pos → timestamp 解析)。

    Side effects:
        - 写 <work_dir>/characters.json (atomic)
        - 写 <work_dir>/props.json (atomic)
        - 写 <work-dir>/characters/<id>.png + <work-dir>/props/<id>.png (ffmpeg；失败时跳过)
    """
    # 1. 读取三输入
    with open(draft_path, encoding="utf-8") as f:
        draft = json.load(f)
    with open(edits_path, encoding="utf-8") as f:
        edits = json.load(f)
    with open(shots_path, encoding="utf-8") as f:
        shots_meta = json.load(f)

    # 2. 校验 edits pre-apply (T-07-02 mitigation: 永不信任未校验的操作员输入)
    _validate(REGISTRY_EDITS_SCHEMA, edits)

    # 3. 构建 clusters dict (copy + stash _members 内部字段)
    # CR-02：畸形 cluster（非 dict / 缺 cluster_id）降级跳过，不 crash（defense-in-depth；
    # WR-05 的 schema 预校验是第一道闸，这里是兜底）。
    clusters = {}
    for c in draft.get("clusters", []):
        if not isinstance(c, dict):
            continue
        cid = c.get("cluster_id")
        if not isinstance(cid, str):
            continue
        clusters[cid] = {**c, "members": list(c.get("members", []))}

    # ========================================================================
    # 4. FIXED-ORDER APPLY (CONTEXT Q2 + RESEARCH Pattern 3)
    # ========================================================================

    # --- 4a. merge_groups ---
    # CR-05：merge_map 记录 {被合并掉的 cid: canonical_id}，供后续 confirm_ids/
    # reject_ids 把被 merge 走的 ID 的审阅意图转发到 canonical 目标（不静默丢弃）。
    # 语义：operator 同时 merge_groups=[[A,B]] + confirm_ids=[A,B] 表示
    # "A 与 B 是同一实体并确认"——canonical A 继承 B 的 confirmed 状态。
    merge_map: dict[str, str] = {}
    for group in edits.get("merge_groups", []) or []:
        if len(group) < 2:
            continue
        canonical_id = group[0]
        merged_members = []
        sum_cos = 0.0
        n_cos = 0
        for cid in group:
            cl = clusters.get(cid)
            if not cl:
                continue
            merged_members.extend(cl.get("members", []))
            mc = cl.get("mean_cosine")
            if isinstance(mc, (int, float)):
                sum_cos += float(mc)
                n_cos += 1
            if cid != canonical_id:
                # 软退役 —— 从 clusters 移除 (draft 文件不动 —— 引用完整性)。
                # 记录 forwarding map（confirm/reject 时转发到 canonical_id）。
                merge_map[cid] = canonical_id
                clusters.pop(cid, None)
        canonical = clusters.get(canonical_id)
        if canonical is None:
            # canonical 自身不在 clusters —— 创建占位
            canonical = {"cluster_id": canonical_id, "review_state": "proposed",
                         "tier": "review", "mean_cosine": 0.0, "members": []}
            clusters[canonical_id] = canonical
        canonical["members"] = merged_members
        canonical["mean_cosine"] = (sum_cos / n_cos) if n_cos else 0.0

    # --- 4b. splits (成员分区；deterministic ID allocation: max_existing_N + 1) ---
    # CR-01 fix:旧实现把源 members 全量 clone 到每个 child(语义错误——两个新簇
    # 拥有 byte-identical appearance_shots)。新 shape (registry-edits.schema.json)
    # 强制 operator 显式 partition:每个 child 携带 member_indexes(0-based 索引到
    # 源 cluster.members[])。apply_edits 校验完整分区(无遗漏/重叠/越界)→ FAIL on 违规。
    splits = edits.get("splits", {}) or {}
    # 按源 cluster_id 字典序处理 (idempotency guard)
    for src_id in sorted(splits.keys()):
        children_def = splits[src_id] or []
        if src_id not in clusters or len(children_def) < 2:
            continue
        src = clusters[src_id]
        prefix = src_id.split("_", 1)[0]  # "char" 或 "prop"
        src_members = src.get("members", []) or []
        n_members = len(src_members)

        # 校验完整分区：每个 member 恰好分配到一个 child
        assigned: set[int] = set()
        for child in children_def:
            if not isinstance(child, dict):
                sys.exit(f"[apply-edits] FAIL: split {src_id} child def is not an object: {child!r}")
            for idx in child.get("member_indexes") or []:
                if not isinstance(idx, int) or idx < 0 or idx >= n_members:
                    sys.exit(f"[apply-edits] FAIL: split {src_id} member_index {idx} "
                             f"out of range [0, {n_members}) (malformed partition)")
                if idx in assigned:
                    sys.exit(f"[apply-edits] FAIL: split {src_id} member_index {idx} "
                             f"assigned to multiple children (overlap — use disjoint indexes)")
                assigned.add(idx)
        if len(assigned) != n_members:
            missing = set(range(n_members)) - assigned
            sys.exit(f"[apply-edits] FAIL: split {src_id} incomplete partition — "
                     f"member_indexes {sorted(missing)} unassigned "
                     f"(must partition ALL {n_members} source members; no silent data loss)")

        # 按 label 字典序确定性分配新 ID (deterministic binding —— idempotency guard)
        for child in sorted(children_def, key=lambda c: c.get("label", "")):
            label = child.get("label", "")
            part_idxs = child.get("member_indexes") or []
            new_id = _next_id(prefix, clusters.keys())
            new_cluster = {
                "cluster_id": new_id,
                "review_state": src.get("review_state", "proposed"),
                "tier": src.get("tier", "review"),
                "mean_cosine": src.get("mean_cosine", 0.0),
                # CR-01: 按 member_indexes 分区(非 clone-all)
                "members": [src_members[i] for i in sorted(part_idxs)],
                "name_hint": label,  # 保留供操作员审计/未来 _build_*_entry fallback；当前 _build_*_entry 仅查 renames
            }
            clusters[new_id] = new_cluster
        # 软退役源 ID
        clusters.pop(src_id, None)

    # --- 4c. renames (在 build-entry 时应用；此处只读取 dict) ---
    renames = edits.get("renames", {}) or {}

    # --- 4d. type_overrides (改 cluster_id prefix；数字保留) ---
    type_overrides = edits.get("type_overrides", {}) or {}
    for cid in list(type_overrides.keys()):
        new_type = type_overrides[cid]
        if cid not in clusters:
            continue
        # 解析原 ID 的数字部分
        parts = cid.split("_", 1)
        if len(parts) != 2:
            continue
        num_part = parts[1]
        new_id = f"{new_type}_{num_part}"
        if new_id == cid:
            continue
        # CR-03：目标 ID 已存在 → 拒绝静默覆盖（防数据丢失）。
        # 操作员必须先 rename/merge 解决冲突，再 type_override。
        if new_id in clusters:
            sys.exit(
                f"[apply-edits] FAIL: type_override {cid} → {new_id} collides "
                f"with an existing cluster (data loss prevented). "
                f"Resolve the collision first (rename or merge {new_id})."
            )
        # 移到新 key；cluster_id 内部字段也更新
        cl = clusters.pop(cid)
        cl["cluster_id"] = new_id
        clusters[new_id] = cl
        # 若 renames 也指向旧 ID，迁移
        if cid in renames:
            renames[new_id] = renames.pop(cid)

    # --- 4e. confirm_ids ---
    # CR-05：被 merge 走的 ID（不在 clusters）的 confirm 意图转发到 canonical 目标，
    # 而非静默丢弃（维护"ID 保留以维护引用完整性"+ operator 意图）。
    for cid in edits.get("confirm_ids", []) or []:
        target = clusters.get(cid)
        if target is None and cid in merge_map:
            # 被合并掉的 ID → 转发到 canonical merge 目标
            target = clusters.get(merge_map[cid])
        if target is not None:
            target["review_state"] = "confirmed"

    # --- 4f. reject_ids ---
    # 同款 forwarding（CR-05）：被 merge 走的 ID 的 reject 转发到 canonical 目标。
    for cid in edits.get("reject_ids", []) or []:
        target = clusters.get(cid)
        if target is None and cid in merge_map:
            target = clusters.get(merge_map[cid])
        if target is not None:
            target["review_state"] = "rejected"

    # ========================================================================
    # 5. HARD GATE (Pitfall 7) —— confirmed-only canonical build
    # ========================================================================
    chars = []
    props = []
    # 按 cluster_id 排序遍历 (idempotency guard —— dict 顺序虽 Python 3.7+ 保证插入序，
    # 但显式排序让 byte-identical 在跨 Python 版本下也成立)
    for cid in sorted(clusters.keys()):
        cl = clusters[cid]
        if cl.get("review_state") != "confirmed":
            # HARD GATE —— proposed/rejected 永不流向下游 (NOT filter-after-write)
            continue
        if cid.startswith("char_"):
            entry = _build_char_entry(cl, renames)
            chars.append(entry)
        elif cid.startswith("prop_"):
            entry = _build_prop_entry(cl, renames)
            props.append(entry)
        # 其他 prefix 静默忽略 (schema-validated cluster_id 不会出现，defense-in-depth)

    # ========================================================================
    # 6. ffmpeg 抽 representative PNG (CAST-08 producer-side fallback)
    # ========================================================================
    for entry in chars + props:
        _extract_representative_png(entry, work_dir, video, shots_meta)
        # 删除 _members 内部字段 (写前清理 —— schema additionalProperties:false 会拒)
        entry.pop("_members", None)

    # ========================================================================
    # 7. Schema validation pre-write (fails loud — Pitfall 1 prevention)
    # ========================================================================
    _validate(CHARACTERS_SCHEMA, chars)
    _validate(PROPS_SCHEMA, props)

    # ========================================================================
    # 8. Atomic write
    # ========================================================================
    _atomic_write(os.path.join(work_dir, "characters.json"), chars)
    _atomic_write(os.path.join(work_dir, "props.json"), props)

    return chars, props


# ============================================================================
# CLI entry point
# ============================================================================

def main():
    ap = argparse.ArgumentParser(
        description=(
            "把 HITL 审阅决定 (registry.edits.json) 应用到 re-id 草稿 "
            "(registry.draft.json)，产出 canonical characters.json + props.json。"
            "独立 CLI —— run_pipeline.py 不调用；操作员在审阅 HITL HTML 后手动运行。"
        ))
    ap.add_argument("--draft", required=True,
                    help="registry.draft.json 路径 (step_reid 产物)")
    ap.add_argument("--edits", required=True,
                    help="registry.edits.json 路径 (HITL HTML 导出)")
    ap.add_argument("--work-dir", required=True,
                    help="输出目录 (output/<asset>/)；characters.json + props.json + characters/ + props/ 写入此")
    ap.add_argument("--video", required=True,
                    help="原视频路径 (ffmpeg 抽代表帧用)")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径 (frame_pos → 时间戳解析)")
    args = ap.parse_args()

    chars, props = apply_edits(
        draft_path=args.draft,
        edits_path=args.edits,
        work_dir=args.work_dir,
        video=args.video,
        shots_path=args.shots,
    )
    print(f"[apply-edits] wrote characters.json ({len(chars)} entries) "
          f"+ props.json ({len(props)} entries) → {args.work_dir}")


if __name__ == "__main__":
    sys.exit(main())
