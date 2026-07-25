#!/usr/bin/env python3
"""registry/link_speakers.py — 把 HITL 审阅决定 (speaker-edits.json) 应用到
diarization 输出 (audio_semantic.json#dialogue.spk_id) 上，产出 canonical
speakers.json (Phase 11 speakers.schema.json)。

本脚本是 **独立 standalone CLI**（CONTEXT Q2 锁：非阻塞 —— run_pipeline.py
永远不调用它；操作员在审阅完 html/gen_speaker_review.py 产出的 HITL HTML
后手动运行；mirror registry/apply_edits.py:5-7 v1.1 Phase 7 先例）。

应用顺序（LOCKED — Phase 11 speaker-edits.schema.json $comment lock +
13-CONTEXT.md decisions；保证 deterministic + idempotent）：

    1. merge_groups   —— 多 speaker 合并（首个 ID 作 canonical，其余软退役；
                          turns 全部并入 canonical；total_speech_sec 求和）
    2. splits         —— 单 speaker 拆分为 N 个（确定性新 spk_id：
                          _next_speaker_id = max_existing_N + 1，按 label
                          字典序绑定 —— Pitfall 5 idempotency guard；
                          member_indexes 必须 complete partition —— 无遗漏/
                          重叠/越界，fail-loud）
    3a. confirm_ids   —— 标记 review_state = "confirmed"
    3b. reject_ids    —— 标记 review_state = "rejected"（软删除，ID 保留以
                          维护 audio_semantic.json#dialogue.spk_id 引用完整性）
    4. link_mappings  —— 写 char_id 字段（spk→char N:M 映射 —— SPEAKER-01 核心）

HARD GATE (Pitfall 7，mirror apply_edits.py:476-480)：build canonical 条目时
`if review_state != "confirmed": continue`（hard skip，NOT filter-after-write）。
proposed/rejected 永不流向下游 speakers.json。

Idempotency guards (Pitfall 5，mirror apply_edits.py:118 + :262-268 + :476)：
  - sorted(clusters.keys()) 遍历（显式排序，跨 Python 版本 byte-identical）
  - sorted(turns, key=(shot_id, start_sec)) 排序 turns
  - _next_speaker_id 确定性（max existing N + 1，零填充 3 位）
  - _atomic_write (temp + os.replace，POSIX atomic；防 partial-write 状态)

char_id resolution (Pitfall 17 second-line)：
  - char_id nullable —— 旁白/群杂 speakers 无角色映射（DIA-03）
  - non-null char_id MUST 解析到 characters.json#id 中 review_state='confirmed'
    的条目（cross-file check；fail-loud sys.exit on dangling ref）
  - link_mappings 中出现的 spk_id 应已在 confirm_ids 中（runtime cross-field
    check schema 无法表达 —— Phase 11 schema $comment lock）

用法：
    python registry/link_speakers.py \\
        --audio-semantic <abs path>   (必填 — audio_semantic.json，Phase 12 producer 产物，提供 dialogue.spk_id 来源) \\
        --characters     <abs path>   (必填 — characters.json，cross-ref target，filter 到 confirmed) \\
        --edits          <abs path>   (必填 — speaker-edits.json，HITL HTML 导出) \\
        --work-dir       <abs path>   (必填 — output/<asset>/；speakers.json 写入此目录) \\
        --output         <abs path>   (必填 — speakers.json 输出路径)

退出码：0 成功；非零 = schema 校验失败 (edits 或 canonical 输出无效) 或
confirmed-only gate 违反 (后者在 well-formed edits 下不可能触发 —— hard assert
是 defense-in-depth) 或 dangling char_id 或 orphan link_mapping (spk 未 confirm)。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ============================================================================
# Module-level constants
# ============================================================================

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

SPEAKER_EDITS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "speaker-edits.schema.json"
SPEAKERS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "speakers.schema.json"

# T-13-03 mitigation: compiled pattern constants, reused at _load_speaker_draft
# defensive check (audio_semantic.json#dialogue.spk_id 是 untrusted route 产物)
# + link_mappings validation. Speakers 用 ^spk_[0-9]{3}$，刻意 disjoint from
# ^char_[0-9]{3}$ (声学身份 ≠ 视觉身份，SPEAKER-01 Phase 13 核心目标)。
SPK_PATTERN = re.compile(r"^spk_[0-9]{3}$")
CHAR_PATTERN = re.compile(r"^char_[0-9]{3}$")


# ============================================================================
# Helpers
# ============================================================================

def _next_speaker_id(existing_ids):
    """确定性 split ID 分配 —— Pitfall 5 idempotency guard。

    从 existing_ids 中筛出 spk_ 前缀的 ID，取其最大数字部分 +1，零填充 3 位
    返回。若无 spk_ ID，返回 "spk_001"。

    Mirror apply_edits.py:_next_id(:109-134)，但特化为 "spk" prefix
    (speakers 无 char/prop 二义性 —— Phase 11 SUMMARY:115 lock)。

    Args:
        existing_ids: iterable[str] —— 当前所有 spk_id 集合（含已被 merge/split 的）。

    Returns:
        str —— 新分配的 spk_id，形如 "spk_004"。
    """
    max_n = 0
    for sid in existing_ids:
        if not isinstance(sid, str) or not sid.startswith("spk_"):
            continue
        suffix = sid[len("spk_"):]
        try:
            n = int(suffix)
        except (ValueError, TypeError):
            continue
        if n > max_n:
            max_n = n
    return f"spk_{max_n + 1:03d}"


def _validate(schema_path, instance):
    """Schema 自校验 —— fails loud。lazy-import jsonschema (v1.0 baseline 4.26.0)。

    Mirror apply_edits.py:_validate(:239-259) verbatim. T-07-02 mitigation:
    永不信任未校验的操作员输入 —— speaker-edits.json MUST 在 apply 前校验。

    Args:
        schema_path: Path 对象。
        instance:    待校验的 Python 对象 (通常 dict/list)。

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
            f"[link-speakers] FAIL: {schema_path.name} validation failed "
            f"({len(errors)} errors):\n" + "\n".join(msgs)
            + (f"\n  ... and {len(errors) - 10} more" if len(errors) > 10 else "")
        )


def _atomic_write(path, data):
    """原子写：temp + os.replace (POSIX atomic；防 partial-write 状态)。

    Mirror apply_edits.py:_atomic_write(:262-268) verbatim. Idempotency guard
    的最后一环 —— 写失败时不会留下半写文件污染 canonical 状态。
    """
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_speaker_draft(audio_semantic_path):
    """从 audio_semantic.json#shots[].dialogue.spk_id 聚合隐式 speakers draft。

    v1.2 输入聚合器（无 v1.1 analog —— apply_edits.py 读 registry.draft.json
    独立草稿文件；本 plan 从 diarization 输出重建 draft）。Phase 12
    analysis/call_audio_analysis.py:normalize_audio_semantic 已 emit
    per-shot dialogue.spk_id；本函数把这些 ID 聚合成 per-speaker turns 列表。

    算法 (13-01-PLAN.md interfaces section lock)：
        for shot in audio_semantic.shots:
            dlg = shot.get("dialogue")
            if dlg is dict and SPK_PATTERN.match(dlg.get("spk_id") or ""):
                spk = dlg["spk_id"]
                turn = {shot_id, start_sec, end_sec}
                draft[spk].turns.append(turn)
                draft[spk].total_speech_sec += max(0, end - start)

    Defensive guards (CR-02 mirror —— apply_edits.py:316-321 degraded-skip not crash):
        - 非 dict shot / 缺 dialogue / null spk_id / 不匹配 SPK_PATTERN → 静默跳过
        - audio_semantic 不是 dict 或无 shots list → 返 {} (graceful empty draft)

    Args:
        audio_semantic_path: abs path to audio_semantic.json (Phase 12 producer).

    Returns:
        dict[spk_id, {"turns": list[dict], "total_speech_sec": float}]。
        空 dict 表示 audio_semantic 无可用 dialogue 或文件缺失/畸形。
    """
    try:
        with open(audio_semantic_path, encoding="utf-8") as f:
            audio_sem = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if not isinstance(audio_sem, dict):
        return {}
    shots = audio_sem.get("shots")
    if not isinstance(shots, list):
        return {}

    draft = {}
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        dlg = shot.get("dialogue")
        if not isinstance(dlg, dict):
            continue
        raw_spk = dlg.get("spk_id")
        # T-13-03: route 产物 untrusted —— 再校验 SPK_PATTERN (defense-in-depth
        # 跟 schema 校验互补；非字符串 / null / 畸形 → 静默 skip)
        if not isinstance(raw_spk, str) or not SPK_PATTERN.match(raw_spk):
            continue
        # 累加 turn + total_speech_sec
        start_sec = shot.get("start_sec", 0.0)
        end_sec = shot.get("end_sec", start_sec)
        try:
            start_sec = float(start_sec)
            end_sec = float(end_sec)
        except (TypeError, ValueError):
            start_sec = 0.0
            end_sec = 0.0
        turn = {
            "shot_id": shot.get("shot_id"),
            "start_sec": start_sec,
            "end_sec": end_sec,
        }
        if raw_spk not in draft:
            draft[raw_spk] = {"turns": [], "total_speech_sec": 0.0}
        draft[raw_spk]["turns"].append(turn)
        draft[raw_spk]["total_speech_sec"] += max(0.0, end_sec - start_sec)

    return draft


def _load_confirmed_char_ids(characters_path):
    """读取 characters.json，filter 到 confirmed 条目，返回 char_id 集合。

    Pitfall 17 second-line 的依据：link_mappings 的 char_id MUST 解析到此集合
    中的某 ID。本函数加载 + filter；link_speakers 主流程做 set membership check。

    Args:
        characters_path: abs path to characters.json (v1.1 apply_edits.py 产物)。

    Returns:
        set[str] —— confirmed char_NNN IDs。空 set 表示 characters.json 中无
        confirmed 条目（合法但所有 link_mappings 都会 fail dangling check）。

    On missing file / malformed JSON: sys.exit non-zero with clear message
        （link_speakers REQUIRES confirmed characters to validate links against；
         absent characters.json = operator error —— 不 graceful-degrade）。
    """
    try:
        with open(characters_path, encoding="utf-8") as f:
            characters = json.load(f)
    except FileNotFoundError:
        sys.exit(
            f"[link-speakers] FAIL: characters.json not found at {characters_path} "
            f"(link_speakers requires confirmed characters to validate char_id links against)"
        )
    except json.JSONDecodeError as e:
        sys.exit(f"[link-speakers] FAIL: characters.json invalid JSON: {e}")

    if not isinstance(characters, list):
        sys.exit(
            f"[link-speakers] FAIL: characters.json expected array, "
            f"got {type(characters).__name__}"
        )

    confirmed = set()
    for entry in characters:
        if not isinstance(entry, dict):
            continue
        if entry.get("review_state") != "confirmed":
            continue
        cid = entry.get("id")
        # Defensive: confirmed character should already match CHAR_PATTERN
        # (apply_edits.py enforces). Re-check here in case of hand-edited drift.
        if isinstance(cid, str) and CHAR_PATTERN.match(cid):
            confirmed.add(cid)
    return confirmed


# ============================================================================
# Core apply function (mirror apply_edits.py:apply_edits :275-509)
# ============================================================================

def link_speakers(audio_semantic_path, characters_path, edits_path,
                  work_dir, output_path):
    """audio_semantic + characters + speaker-edits → canonical speakers.json。

    应用顺序 (LOCKED — Phase 11 schema $comment)：
        merge_groups → splits → confirm_ids/reject_ids → link_mappings。
    confirmed-only HARD GATE (Pitfall 7) at build-entry time。
    Idempotent：同 inputs+edits 重复 apply 产生 byte-identical speakers.json
    (Pitfall 5 guard)。

    Args:
        audio_semantic_path: abs path to audio_semantic.json (Phase 12 producer).
        characters_path:     abs path to characters.json (cross-ref target).
        edits_path:          abs path to speaker-edits.json (HITL HTML 导出).
        work_dir:            abs path to output dir (unused currently; reserved
                             for future side artifacts, mirror apply_edits.py
                             --work-dir convention).
        output_path:         abs path to speakers.json output.

    Side effects:
        - 写 output_path speakers.json (atomic；validates speakers.schema.json).
    """
    # 1. 读取 + 校验 edits pre-apply (T-07-02 mitigation)
    with open(edits_path, encoding="utf-8") as f:
        edits = json.load(f)
    _validate(SPEAKER_EDITS_SCHEMA, edits)

    # 2. 加载 confirmed character IDs (Pitfall 17 second-line 依据)
    confirmed_char_ids = _load_confirmed_char_ids(characters_path)

    # 3. 构建 clusters dict (从 audio_semantic.json 聚合 + 初始化 review_state)
    draft = _load_speaker_draft(audio_semantic_path)
    clusters = {}
    for spk_id, info in draft.items():
        clusters[spk_id] = {
            "spk_id": spk_id,
            "review_state": "proposed",   # 默认 proposed;confirm/reject step 改写
            "turns": list(info.get("turns", [])),
            "total_speech_sec": float(info.get("total_speech_sec", 0.0)),
            "char_id": None,   # 默认无映射;link_mappings step 写入
        }

    # ========================================================================
    # 4. FIXED-ORDER APPLY (Phase 11 schema $comment + 13-CONTEXT.md decisions)
    # ========================================================================

    # --- 4a. merge_groups (mirror apply_edits.py:332-361) ---
    # merge_map 记录 {被合并的 spk_id: canonical_id}，供后续 confirm/reject 转发
    # 意图 (CR-05 mirror；operator 同时 merge + confirm 表示合并后整体确认)。
    merge_map = {}
    for group in edits.get("merge_groups", []) or []:
        if len(group) < 2:
            continue
        canonical_id = group[0]
        merged_turns = []
        total_speech = 0.0
        for sid in group:
            cl = clusters.get(sid)
            if not cl:
                continue
            merged_turns.extend(cl.get("turns", []))
            total_speech += float(cl.get("total_speech_sec", 0.0))
            if sid != canonical_id:
                # 软退役 —— 从 clusters 移除 (draft 文件不动 —— 引用完整性)。
                # 记录 forwarding map（confirm/reject 时转发到 canonical_id）。
                merge_map[sid] = canonical_id
                clusters.pop(sid, None)
        canonical = clusters.get(canonical_id)
        if canonical is None:
            # canonical 自身不在 clusters —— 创建占位
            canonical = {
                "spk_id": canonical_id,
                "review_state": "proposed",
                "turns": [],
                "total_speech_sec": 0.0,
                "char_id": None,
            }
            clusters[canonical_id] = canonical
        canonical["turns"] = merged_turns
        canonical["total_speech_sec"] = total_speech

    # --- 4b. splits (mirror apply_edits.py:368-414 with members→turns) ---
    # 完整 PARTITION 强制：每个 member_index 恰好分配到一个 child（无遗漏/重叠/
    # 越界）。新 spk_id 通过 _next_speaker_id(clusters.keys())，按 sorted(label)
    # 字典序绑定 (idempotency guard)。
    splits = edits.get("splits", {}) or {}
    for src_id in sorted(splits.keys()):
        children_def = splits[src_id] or []
        if src_id not in clusters or len(children_def) < 2:
            continue
        src = clusters[src_id]
        src_turns = src.get("turns", []) or []
        n_turns = len(src_turns)

        # 校验完整分区
        assigned = set()
        for child in children_def:
            if not isinstance(child, dict):
                sys.exit(
                    f"[link-speakers] FAIL: split {src_id} child def is not "
                    f"an object: {child!r}"
                )
            for idx in child.get("member_indexes") or []:
                if not isinstance(idx, int) or idx < 0 or idx >= n_turns:
                    sys.exit(
                        f"[link-speakers] FAIL: split {src_id} member_index "
                        f"{idx} out of range [0, {n_turns}) (malformed partition)"
                    )
                if idx in assigned:
                    sys.exit(
                        f"[link-speakers] FAIL: split {src_id} member_index "
                        f"{idx} assigned to multiple children (overlap — use "
                        f"disjoint indexes)"
                    )
                assigned.add(idx)
        if len(assigned) != n_turns:
            missing = set(range(n_turns)) - assigned
            sys.exit(
                f"[link-speakers] FAIL: split {src_id} incomplete partition — "
                f"member_indexes {sorted(missing)} unassigned "
                f"(must partition ALL {n_turns} source turns; no silent data loss)"
            )

        # 按 label 字典序确定性分配新 spk_id (deterministic binding —— idempotency)
        for child in sorted(children_def, key=lambda c: c.get("label", "")):
            label = child.get("label", "")
            part_idxs = child.get("member_indexes") or []
            new_id = _next_speaker_id(clusters.keys())
            child_turns = [src_turns[i] for i in sorted(part_idxs)]
            child_total = sum(
                max(0.0, float(t.get("end_sec", 0.0)) - float(t.get("start_sec", 0.0)))
                for t in child_turns
            )
            clusters[new_id] = {
                "spk_id": new_id,
                "review_state": src.get("review_state", "proposed"),
                "turns": child_turns,
                "total_speech_sec": child_total,
                "char_id": None,
            }
        # 软退役源 spk_id
        clusters.pop(src_id, None)

    # --- 4c. confirm_ids (mirror apply_edits.py:452-458 with merge forwarding) ---
    # CR-05 mirror：被 merge 走的 ID 的 confirm 意图转发到 canonical 目标，
    # 而非静默丢弃 (维护 "ID 保留以维护引用完整性" + operator 意图)。
    for sid in edits.get("confirm_ids", []) or []:
        target = clusters.get(sid)
        if target is None and sid in merge_map:
            target = clusters.get(merge_map[sid])
        if target is not None:
            target["review_state"] = "confirmed"

    # --- 4d. reject_ids (mirror apply_edits.py:462-467 with merge forwarding) ---
    for sid in edits.get("reject_ids", []) or []:
        target = clusters.get(sid)
        if target is None and sid in merge_map:
            target = clusters.get(merge_map[sid])
        if target is not None:
            target["review_state"] = "rejected"

    # --- 4e. link_mappings (NEW for SPEAKER-01; no v1.1 analog) ---
    # Phase 11 speaker-edits.schema.json $comment lock: link_mappings 中出现的
    # spk_id 应已在 confirm_ids 中 (runtime cross-field check schema 无法表达).
    # Pitfall 17 second-line: non-null char_id MUST resolve to confirmed
    # characters.json#id (fail-loud sys.exit on dangling).
    for sid, char_id in (edits.get("link_mappings", {}) or {}).items():
        target = clusters.get(sid)
        if target is None:
            sys.exit(
                f"[link-speakers] FAIL: link_mappings references unknown spk_id "
                f"{sid} (must be present in input speakers or merge_groups; "
                f"if it was reject_ids, ID is reserved but not linkable)"
            )
        if target["review_state"] != "confirmed":
            sys.exit(
                f"[link-speakers] FAIL: link_mappings links {sid} which is "
                f"{target['review_state']!r} (must be 'confirmed' —— spk_id "
                f"in link_mappings MUST also appear in confirm_ids; "
                f"Phase 11 schema $comment lock)"
            )
        if not isinstance(char_id, str) or not CHAR_PATTERN.match(char_id):
            sys.exit(
                f"[link-speakers] FAIL: link_mappings {sid}→{char_id!r} "
                f"malformed (char_id must match char_[0-9]{{3}})"
            )
        if char_id not in confirmed_char_ids:
            sys.exit(
                f"[link-speakers] FAIL: link_mappings {sid}→{char_id} "
                f"dangling (char_id not in confirmed characters.json IDs —— "
                f"Pitfall 17 second-line; speaker→character dangling)"
            )
        target["char_id"] = char_id

    # ========================================================================
    # 5. HARD GATE (Pitfall 7, mirror apply_edits.py:476-480) —— confirmed-only
    # ========================================================================
    speakers = []
    # 显式 sorted(cluster_id) 遍历 (idempotency guard —— 跨 Python 版本 byte-identical)
    for sid in sorted(clusters.keys()):
        cl = clusters[sid]
        if cl.get("review_state") != "confirmed":
            # HARD GATE —— proposed/rejected 永不流向下游 (NOT filter-after-write)
            continue
        # turns 排序：(shot_id, start_sec) 字典序；保证 idempotent byte output。
        # WR-01 fix (mirror gen_speaker_review.py:175-178 _aggregate_speakers)：
        # shot_id 若 missing/null/non-int，用大 sentinel (1<<30) 兜底，避免
        # `1 < None` 触发 TypeError 在 schema validation gate 之前崩溃（route
        # 退化或 hand-edit 可能产生 null shot_id；schema validation 仍是干净
        # 的 fail-loud 边界，仅在排序时降级而非崩溃）。
        sorted_turns = sorted(
            cl.get("turns", []) or [],
            key=lambda t: (
                t.get("shot_id") if isinstance(t, dict) and isinstance(t.get("shot_id"), int) else (1 << 30),
                float(t.get("start_sec", 0.0)) if isinstance(t, dict) else 0.0,
            ),
        )
        speakers.append({
            "spk_id": sid,
            "char_id": cl.get("char_id"),   # None if never linked (schema-nullable)
            "total_speech_sec": float(cl.get("total_speech_sec", 0.0)),
            "review_state": "confirmed",   # HARD-CODED —— confirmed-only gate (Pitfall 7)
            "turns": sorted_turns,
        })

    # ========================================================================
    # 6. Schema validation pre-write (fails loud — Pitfall 1 prevention)
    # ========================================================================
    _validate(SPEAKERS_SCHEMA, {"speakers": speakers})

    # ========================================================================
    # 7. Atomic write
    # ========================================================================
    _atomic_write(output_path, {"speakers": speakers})

    return speakers


# ============================================================================
# CLI entry point
# ============================================================================

def main():
    ap = argparse.ArgumentParser(
        description=(
            "把 HITL 审阅决定 (speaker-edits.json) 应用到 diarization 输出 "
            "(audio_semantic.json#dialogue.spk_id)，产出 canonical speakers.json。"
            "独立 CLI —— run_pipeline.py 不调用；操作员在审阅 HITL HTML 后手动运行。"
            "Mirror v1.1 registry/apply_edits.py 的 confirmed-only hard gate + "
            "idempotent re-apply 模式。"
        )
    )
    ap.add_argument("--audio-semantic", required=True,
                    help="audio_semantic.json 路径 (Phase 12 producer 产物，提供 dialogue.spk_id 来源)")
    ap.add_argument("--characters", required=True,
                    help="characters.json 路径 (cross-ref target，filter 到 confirmed;char_id MUST 解析到此)")
    ap.add_argument("--edits", required=True,
                    help="speaker-edits.json 路径 (HITL HTML 导出)")
    ap.add_argument("--work-dir", required=True,
                    help="输出目录 output/<asset>/ (speakers.json 写入此)")
    ap.add_argument("--output", required=True,
                    help="speakers.json 输出路径")
    args = ap.parse_args()

    speakers = link_speakers(
        audio_semantic_path=args.audio_semantic,
        characters_path=args.characters,
        edits_path=args.edits,
        work_dir=args.work_dir,
        output_path=args.output,
    )
    print(f"[link-speakers] wrote {args.output} ({len(speakers)} confirmed speakers)")


if __name__ == "__main__":
    sys.exit(main())
