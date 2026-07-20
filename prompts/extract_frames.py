#!/usr/bin/env python3
"""从 frames.json 解出每个分镜的首尾帧图片文件。

frames.json 由 pipeline 生成，格式：[{"id": 1, "first_frame": "data:image/jpeg;base64,...", "last_frame": "..."}, ...]

用法：
  python prompts/extract_frames.py --frames output/<stem>/frames.json --output-dir output/<stem>/shot_frames/
"""
import argparse
import base64
import json
import os
import re


def decode_data_url(data_url: str) -> bytes:
    m = re.match(r"data:image/\w+;base64,(.*)", data_url, re.S)
    if not m:
        raise ValueError("not a base64 data URL")
    return base64.b64decode(m.group(1))


def main():
    ap = argparse.ArgumentParser(description="frames.json → 每镜首尾帧 jpg")
    ap.add_argument("--frames", required=True, help="frames.json 路径")
    ap.add_argument("--output-dir", required=True, help="输出目录")
    args = ap.parse_args()

    with open(args.frames, encoding="utf-8") as f:
        entries = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)
    n = 0
    for e in entries:
        sid = e["id"]
        for kind in ("first_frame", "last_frame"):
            if kind not in e or not e[kind]:
                continue
            out = os.path.join(args.output_dir, f"shot_{sid:03d}_{kind.split('_')[0]}.jpg")
            if os.path.exists(out):
                continue
            with open(out, "wb") as f:
                f.write(decode_data_url(e[kind]))
            n += 1
    print(f"[done] {len(entries)} shots → {args.output_dir} ({n} files written)")


if __name__ == "__main__":
    main()
