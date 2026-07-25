#!/usr/bin/env bash
# 包一层 aggregate_report.py --check-staleness（Pitfall 10 staleness gate）。
# Wave 0 baseline: results/ 为空 → exit 0；后续 Plan 03+ 写入结果后，
# aggregate_report.py 检查每个 *.json 的 git_sha 与当前 HEAD 是否一致。
#
# 单行 wrapper —— aggregate_report.py 才是真正的 staleness 逻辑所在。
set -euo pipefail

# common.py 与 aggregate_report.py 同目录；脚本相对路径解析。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPIKE_AUDIO_DIR="$(cd "${HERE}/.." && pwd)"

echo "[smoke:staleness] delegating to aggregate_report.py --check-staleness"
exec python3 "${SPIKE_AUDIO_DIR}/aggregate_report.py" --check-staleness
