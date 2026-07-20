#!/usr/bin/env python3
"""合并 prompt_parts/*.json 分片 → prompts.json,并补上 shots.json 的时间元数据。

用法:
  python prompts/merge_prompts.py \
      --parts-dir output/<stem>/prompt_parts/ \
      --shots output/<stem>/shots.json \
      --output output/<stem>/prompts.json
"""
import argparse
import glob
import json
import os
import sys

REQUIRED_FIELDS = ("subject", "action", "camera", "scene", "lighting", "style", "prompt_text")


def main():
    ap = argparse.ArgumentParser(description="合并 prompt 分片 → prompts.json")
    ap.add_argument("--parts-dir", required=True, help="prompt_parts 目录")
    ap.add_argument("--shots", required=True, help="shots.json 路径")
    ap.add_argument("--output", required=True, help="输出 prompts.json 路径")
    args = ap.parse_args()

    with open(args.shots, encoding="utf-8") as f:
        shots = {s["id"]: s for s in json.load(f)}

    prompts = {}
    for path in sorted(glob.glob(os.path.join(args.parts_dir, "part_*.json"))):
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            sid = e["shot_id"]
            if sid in prompts:
                print(f"[warn] duplicate shot_id {sid} in {path}", file=sys.stderr)
            prompts[sid] = e

    missing = sorted(set(shots) - set(prompts))
    extra = sorted(set(prompts) - set(shots))
    if missing:
        print(f"[error] missing shot_ids: {missing}", file=sys.stderr)
    if extra:
        print(f"[warn] extra shot_ids not in shots.json: {extra}", file=sys.stderr)
    if missing:
        sys.exit(1)

    merged = []
    bad_fields = []
    for sid in sorted(prompts):
        p = prompts[sid]
        s = shots.get(sid, {})
        for fld in REQUIRED_FIELDS:
            if not p.get(fld):
                bad_fields.append((sid, fld))
        merged.append({
            "shot_id": sid,
            "start_sec": s.get("start_sec"),
            "end_sec": s.get("end_sec"),
            "duration": s.get("duration"),
            "subject": p.get("subject", ""),
            "action": p.get("action", ""),
            "camera": p.get("camera", ""),
            "scene": p.get("scene", ""),
            "lighting": p.get("lighting", ""),
            "style": p.get("style", ""),
            "prompt_text": p.get("prompt_text", ""),
        })

    if bad_fields:
        print(f"[warn] empty fields: {bad_fields}", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[done] merged {len(merged)} shots → {args.output}")


if __name__ == "__main__":
    main()
