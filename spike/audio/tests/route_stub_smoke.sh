#!/usr/bin/env bash
# 3 个 ROUTE-01 envelope smoke 检查（curl-based）。
#
# 目标 host: ${AUDIO_ROUTE_URL:-http://localhost:3000}/api/production/audio-analysis
#   （注意：NO /v1/ 前缀 —— 10-RESEARCH.md §"Note on mounting path discrepancy"）
#
# 检查项：
#   (1) Happy path: POST {"video":"/x","shots":"/y"} → envelope code==200 AND
#       data.stub_mode==true（ML 未加载时 stub_mode 必须为真）。
#   (2) Validation: POST {} → envelope code==400（zod 必填校验）。
#   (3) Informational: AUDIO_ANALYSIS_STUB_MODE 注入时仍然 stub_mode=true；
#       服务器侧把 stub_mode 改成 false 而 ML 没载入时应该返回 501 —— 这一项
#       仅 echo 结果，不计入失败判定（route stub 当前不暴露 env-flip 端点）。
#
# Wave 0：路由 host 还没存在（Plan 02 才建）。本脚本必须：
#   - SKIP_ROUTE_STUB=1 → 直接 exit 0（Plan 02 verify 也会用这个）
#   - 连接被拒 → exit 0 + 警告（Wave 0 baseline）
#   - 连上 → 跑 3 项检查，checks 1+2 pass 才 exit 0
set -euo pipefail

AUDIO_ROUTE_URL="${AUDIO_ROUTE_URL:-http://localhost:3000}"
ENDPOINT="${AUDIO_ROUTE_URL}/api/production/audio-analysis"
# NO /v1/ per 10-RESEARCH.md §"mounting path discrepancy" —— router.ts mounts
# shot-analysis at /api/production/shot-analysis (no /v1/), audio mirrors it.

if [[ "${SKIP_ROUTE_STUB:-0}" == "1" ]]; then
    echo "[smoke:route-stub] SKIP — SKIP_ROUTE_STUB=1 set"
    exit 0
fi

# 探测服务器是否在线（2s 超时，避免 Wave 0 长时间挂起）
if ! curl -fsS --max-time 2 -o /dev/null "${AUDIO_ROUTE_URL}/" 2>/dev/null \
   && ! curl -fsS --max-time 2 -o /dev/null "${ENDPOINT}" 2>/dev/null; then
    echo "[smoke:route-stub] SKIP — server not running at ${AUDIO_ROUTE_URL} (Wave 0 baseline; set SKIP_ROUTE_STUB=1 to silence)"
    exit 0
fi

echo "[smoke:route-stub] server detected at ${AUDIO_ROUTE_URL}; running 3 checks..."

PASS=0
FAIL=0

# --- check 1: happy path → code=200 + stub_mode=true ---
HAPPY=$(curl -fsS --max-time 10 \
    -H 'Content-Type: application/json' \
    -X POST "${ENDPOINT}" \
    -d '{"video":"/x","shots":"/y"}' 2>/dev/null || echo '')
HAPPY_CODE=$(printf '%s' "${HAPPY}" | jq -r '.code // "MISSING"' 2>/dev/null || echo "JQ_FAIL")
HAPPY_STUB=$(printf '%s' "${HAPPY}" | jq -r '.data.stub_mode // "MISSING"' 2>/dev/null || echo "JQ_FAIL")
if [[ "${HAPPY_CODE}" == "200" && "${HAPPY_STUB}" == "true" ]]; then
    echo "[smoke:route-stub] check 1 HAPPY: code=200 stub_mode=true ✓"
    PASS=$((PASS + 1))
else
    echo "[smoke:route-stub] check 1 HAPPY: FAIL (code=${HAPPY_CODE} stub_mode=${HAPPY_STUB})"
    echo "    response: ${HAPPY}"
    FAIL=$((FAIL + 1))
fi

# --- check 2: validation → code=400 ---
VAL=$(curl -fsS --max-time 10 \
    -H 'Content-Type: application/json' \
    -X POST "${ENDPOINT}" \
    -d '{}' 2>/dev/null || echo '')
VAL_CODE=$(printf '%s' "${VAL}" | jq -r '.code // "MISSING"' 2>/dev/null || echo "JQ_FAIL")
if [[ "${VAL_CODE}" == "400" ]]; then
    echo "[smoke:route-stub] check 2 VALIDATION: code=400 ✓"
    PASS=$((PASS + 1))
else
    echo "[smoke:route-stub] check 2 VALIDATION: FAIL (code=${VAL_CODE}, expected 400)"
    echo "    response: ${VAL}"
    FAIL=$((FAIL + 1))
fi

# --- check 3 (informational only): stub_mode env flip ---
# Plan 02 才会暴露 AUDIO_ANALYSIS_STUB_MODE flip 路径；Wave 0 仅打 info。
echo "[smoke:route-stub] check 3 STUB-FLIP: informational only (Phase 10 Plan 02 sets env var; not asserted here)"

echo "[smoke:route-stub] summary: ${PASS} pass / ${FAIL} fail (check 3 excluded)"
if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
