#!/usr/bin/env bash
# Wave 0 smoke-check suite — Wave-merge gate per .planning/.../10-VALIDATION.md.
#
# 调用顺序：
#   1. results_schema_check.py  — results/*.json 形状校验（空 results/ 时 exit 0）
#   2. staleness_check.sh       — git_sha vs HEAD 一致性（空 results/ 时 exit 0）
#   3. route_stub_smoke.sh      — ROUTE-01 envelope 3 项 curl 检查
#                                  - SKIP_ROUTE_STUB=1 跳过
#                                  - 服务器未运行 → Wave 0 自动跳过（exit 0）
#                                  - 服务器在线（Plan 02+）→ 跑 3 项检查
#
# Wave 0 baseline（results/ 空 + 路由 host 未存在）应整体 exit 0；
# 任一非自动跳过的 sub-check 失败 → 立即 exit 非零。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPIKE_AUDIO_DIR="$(cd "${HERE}/.." && pwd)"
RESULTS_DIR="${SPIKE_AUDIO_DIR}/results"

echo "[smoke:all] starting Wave 0 smoke suite"
echo "[smoke:all] spike/audio=${SPIKE_AUDIO_DIR}"
echo "[smoke:all] results=${RESULTS_DIR}"
echo "[smoke:all] SKIP_ROUTE_STUB=${SKIP_ROUTE_STUB:-0}"
echo "[smoke:all] AUDIO_ROUTE_URL=${AUDIO_ROUTE_URL:-http://localhost:3000}"

# --- 1. schema check ---
echo ""
echo "[smoke:all] === [1/3] results_schema_check.py ==="
if [[ -d "${RESULTS_DIR}" && -n "$(ls -A "${RESULTS_DIR}" 2>/dev/null)" ]]; then
    python3 "${HERE}/results_schema_check.py"
else
    echo "[smoke:all] results/ empty — schema check skipped (Wave 0 baseline)"
fi

# --- 2. staleness check ---
echo ""
echo "[smoke:all] === [2/3] staleness_check.sh ==="
bash "${HERE}/staleness_check.sh"

# --- 3. route stub smoke (skippable) ---
echo ""
echo "[smoke:all] === [3/3] route_stub_smoke.sh ==="
bash "${HERE}/route_stub_smoke.sh"

echo ""
echo "[smoke:all] ALL SMOKE CHECKS PASS"
