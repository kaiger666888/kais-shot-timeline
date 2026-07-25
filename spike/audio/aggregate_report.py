"""Phase 10 spike 结果聚合 + staleness 检查（scaffold）。

⚠️ THROWAWAY Phase 10 spike 代码 —— 不是 pipeline 代码。
本脚本只读 spike/audio/results/*.json；不写任何 pipeline 文件。

两个 flag（Plan 10-01 Task 3 scope）：
  --check-staleness (staleness gate, Pitfall 10):
      对每个 results/*.json，比较其顶层 ``git_sha`` 与当前 HEAD（common.git_sha()）。
      任一文件 sha 不匹配当前 HEAD → 打印 WARNING + exit 1。
      results/ 空 → exit 0（Wave 0 baseline）。
      HEAD 不可获取（``unknown``）→ 全部视为匹配，exit 0（spike 容错）。

  --aggregate (Plan 06 实现；此处仅占位):
      读 results/*.json 数量 N；打印一行占位信息；exit 0。

默认行为（无 flag）：等同 --aggregate（占位）。
"""
import argparse
import json
import sys
from pathlib import Path

# common.py 同目录导入（spike 脚本约定）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402  sys.path 注入后才能 import common


def check_staleness(results_dir: Path) -> int:
    """Pitfall 10 staleness gate."""
    if not results_dir.exists():
        print("[aggregate] results/ does not exist — Wave 0 baseline, exit 0")
        return 0
    files = sorted(results_dir.glob("*.json"))
    if not files:
        print("[aggregate] results/ empty — Wave 0 baseline, exit 0")
        return 0
    current_sha = common.git_sha()
    if current_sha == "unknown":
        print("[aggregate] git HEAD unavailable — skipping staleness check (spike 容错)")
        return 0
    stale = []
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001  spike 容错
            print(f"[aggregate] WARNING: cannot parse {fp.name}: {e}")
            stale.append((fp.name, "<parse-error>"))
            continue
        file_sha = d.get("git_sha", "<missing>")
        if file_sha != current_sha:
            stale.append((fp.name, file_sha))
    if stale:
        print(f"[aggregate] WARNING: stale results (current HEAD={current_sha}):")
        for name, sha in stale:
            print(f"  {name}: git_sha={sha}")
        return 1
    print(f"[aggregate] all {len(files)} result file(s) match HEAD {current_sha}")
    return 0


def aggregate(results_dir: Path) -> int:
    """Plan 06 实现；此处仅占位。"""
    if not results_dir.exists():
        n = 0
    else:
        n = len(list(results_dir.glob("*.json")))
    print(f"[aggregate] skeleton — Plan 06 fleshes this out; got {n} result file(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--check-staleness",
        action="store_true",
        help="比较 results/*.json 的 git_sha 与当前 HEAD（Pitfall 10 staleness gate）",
    )
    g.add_argument(
        "--aggregate",
        action="store_true",
        help="聚合 results/*.json 到报告（Plan 06 实现；此处占位）",
    )
    args = parser.parse_args()

    results_dir = common.RESULTS_DIR

    if args.check_staleness:
        return check_staleness(results_dir)
    # --aggregate 或无 flag 默认 → 占位
    return aggregate(results_dir)


if __name__ == "__main__":
    sys.exit(main())
