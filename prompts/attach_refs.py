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
    仅 review_state == "confirmed" 条目参与（Pitfall 7 consistent）。
    """
    # STUB (RED) —— 真实实现见 GREEN 阶段
    return [], []


def attach(prompts, chars, props):
    """对每个 prompt 条目挂 character_refs[]/prop_refs[] + 重组 prompt_text。

    Idempotent: 同输入 → 同输出（sorted refs; prompt_text deterministic）。
    """
    # STUB (RED) —— 不挂 refs、不重组 prompt_text；行为断言将 FAIL
    out = []
    for entry in prompts:
        new_entry = dict(entry)
        new_entry["character_refs"] = []
        new_entry["prop_refs"] = []
        # prompt_text 保持原值（不重组）—— RED 断言会 FAIL
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
    # STUB (RED) —— 返空串；行为断言将 FAIL
    return ""


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
