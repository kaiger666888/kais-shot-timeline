#!/usr/bin/env python3
"""为 prompts.json 挂 character_refs[]/prop_refs[] + 重组 prompt_text（PROMPT-01/02）。

行为：
  * 读 characters.json + props.json（confirmed registry）+ prompts.json。
  * 反向索引 appearance_shots[] → 为每个 shot 挂 character_refs[]/prop_refs[]。
  * 重组 prompt_text（Pattern 2 锁定模板 —— 见下方 _recompose docstring）。
  * 幂等：同输入 → byte-identical 输出（sorted(set(...)) + 固定模板顺序；无时间戳）。
  * graceful-degrade：characters.json/props.json 缺席 → refs 空，prompt_text 仅由
    facets 重组（无 identity 子句），schema-valid，exit 0。
  * Pre-write schema-validate（prompts.schema.json）+ atomic write（temp + os.replace）。

用法：
  python3 prompts/attach_refs.py \
      --prompts output/<stem>/prompts.json \
      --work-dir output/<stem>/ \
      [--output <path>]   # 默认 = --prompts（in-place rewrite）
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPTS_SCHEMA = REPO / "spec" / "schemas" / "prompts.schema.json"

# Pattern 2 separator —— U+00B7 middle dot, 空格分隔
_SEP = " · "


def _atomic_write(path: str, data) -> None:
    """temp + os.replace（mirror export_asset.py:402-405 原子写）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_registry(work_dir: str) -> tuple:
    """读 characters.json + props.json；任一缺席 → 返 [] for that side。

    graceful-degrade —— registry 缺席时 refs 空，prompt_text 仍可重组自 facets。
    仅 review_state == "confirmed" 条目参与（Pitfall 7 consistent ——
    与 apply_edits.py build-time hard gate + _producer_registry_integrity second-line
    assert 对齐，非-confirmed 绝不进 prompt refs）。
    坏 JSON / OSError 静默降级（不阻断 timeline 生成）。
    """
    chars: list = []
    props: list = []
    cp = os.path.join(work_dir, "characters.json")
    pp = os.path.join(work_dir, "props.json")
    if os.path.isfile(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                # 仅 confirmed 条目参与 prompt refs（Pitfall 7 consistent）
                chars = [c for c in loaded
                         if isinstance(c, dict)
                         and c.get("review_state") == "confirmed"]
        except (OSError, json.JSONDecodeError):
            pass   # 静默降级 —— 不阻断 timeline 生成
    if os.path.isfile(pp):
        try:
            with open(pp, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                props = [p for p in loaded
                         if isinstance(p, dict)
                         and p.get("review_state") == "confirmed"]
        except (OSError, json.JSONDecodeError):
            pass
    return chars, props


def attach(prompts, chars, props):
    """对每个 prompt 条目挂 character_refs[]/prop_refs[] + 重组 prompt_text。

    Idempotent: 同输入 → 同输出（sorted refs; prompt_text deterministic）。
    refs 来自 appearance_shots[] 反向索引（sorted(set(...)) —— Pitfall 2 防漂移）。
    """
    # 反向索引：shot_id → [char_id, ...]；name_by_char: id → name
    char_by_shot: dict = {}
    name_by_char: dict = {}
    for c in chars:
        cid = c.get("id")
        name_by_char[cid] = c.get("name", cid)
        for sid in c.get("appearance_shots") or []:
            char_by_shot.setdefault(sid, []).append(cid)
    prop_by_shot: dict = {}
    name_by_prop: dict = {}
    for p in props:
        pid = p.get("id")
        name_by_prop[pid] = p.get("name", pid)
        for sid in p.get("appearance_shots") or []:
            prop_by_shot.setdefault(sid, []).append(pid)

    out = []
    for entry in prompts:
        sid = entry.get("shot_id")
        # sorted(set(...)) —— idempotent guarantee（Pitfall 2 prevention）
        crefs = sorted(set(char_by_shot.get(sid, [])))
        prefs = sorted(set(prop_by_shot.get(sid, [])))
        new_entry = dict(entry)   # 浅拷贝 —— 保留所有现有 facet 字段
        new_entry["character_refs"] = crefs
        new_entry["prop_refs"] = prefs
        new_entry["prompt_text"] = _recompose(
            entry, crefs, prefs, name_by_char, name_by_prop)
        out.append(new_entry)
    return out


def _recompose(entry, crefs, prefs, name_by_char, name_by_prop) -> str:
    """PROMPT-02 deterministic identity-injecting recomposition（Pattern 2 锁定）。

    Template (locked by CONTEXT Q2 + RESEARCH Pattern 2):
      [style] · [scene] · 角色:[name1, name2] · 道具:[name1] · [subject] · [action] · [camera] · [lighting]

    空 facets 跳过（无 trailing separator）。
    refs 空时跳过对应 identity 子句。
    Names 仅来自 confirmed registry（无 fabrication）。
    """
    parts: list = []

    # Facet parts —— 固定顺序，跳过空值
    for facet in ("style", "scene"):
        v = (entry.get(facet) or "").strip()
        if v:
            parts.append(v)

    # Identity clauses —— 仅当 refs 非空
    if crefs:
        names = [name_by_char.get(cid, cid) for cid in crefs]
        parts.append(f"角色:[{', '.join(names)}]")
    if prefs:
        names = [name_by_prop.get(pid, pid) for pid in prefs]
        parts.append(f"道具:[{', '.join(names)}]")

    # Remaining facets —— 固定顺序，跳过空值
    for facet in ("subject", "action", "camera", "lighting"):
        v = (entry.get(facet) or "").strip()
        if v:
            parts.append(v)

    return _SEP.join(parts)


def main():
    ap = argparse.ArgumentParser(
        description="为 prompts.json 挂 character_refs/prop_refs + recompose prompt_text")
    ap.add_argument("--prompts", required=True,
                    help="prompts.json 路径（默认 in-place rewrite）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（含 characters.json/props.json）")
    ap.add_argument("--output", default=None,
                    help="输出路径（默认 = --prompts，in-place）")
    args = ap.parse_args()

    with open(args.prompts, encoding="utf-8") as f:
        prompts = json.load(f)
    if not isinstance(prompts, list):
        sys.exit(f"prompts.json expected JSON array, got {type(prompts).__name__}")

    chars, props = _load_registry(args.work_dir)
    out = attach(prompts, chars, props)

    # Pre-write schema validate（fails loud —— 项目惯例）
    from jsonschema import Draft202012Validator
    with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    errors = sorted(Draft202012Validator(schema).iter_errors(out),
                    key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        sys.exit(f"attach_refs output failed prompts.schema ({len(errors)} errors):\n"
                 + "\n".join(lines))

    out_path = args.output or args.prompts
    _atomic_write(out_path, out)
    print(f"[attach-refs] {len(out)} shots + "
          f"{sum(len(c.get('character_refs', [])) for c in out)} char refs + "
          f"{sum(len(c.get('prop_refs', [])) for c in out)} prop refs → {out_path}")


if __name__ == "__main__":
    main()
