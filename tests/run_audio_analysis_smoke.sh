#!/usr/bin/env bash
# Phase 12 SC#4 stub round-trip smoke —— 5 scenarios 证明
# analysis/call_audio_analysis.py（Plan 12-01 产出）正确处理 Phase 10 stub envelope
# （解析 + cache write/read + warnings 合并）—— 在 route ML 上线前的确定性证明。
#
# 镜像 spike/audio/tests/route_stub_smoke.sh 的 bash 编排风格：
#   后台启 stub → 调 client → 断言文件输出/日志标记 → trap 清理。
#
# Scenarios（与 12-02-PLAN.md must_haves 一一对应）：
#   1. route-up + non-empty      → audio_semantic.json 写入 + schema-valid + 0 [audio]
#   2. cache-hit (re-run offline)→ byte-identical to scenario 1（deterministic）
#   3. poisoned cache            → schema-validate fail → unlink + [audio] warning
#   4. full-degrade empty stub   → byte-identical-absent + [semantic]/[reid] preserved
#   5. offline + empty cache     → byte-identical-absent + [audio] warning
#
# 全部 PASS → echo "ALL_SCENARIOS_PASS" + exit 0；任一 FAIL → exit 1 + 证据。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="/tmp/p12-smoke-$$"
STUB_PORT_NONEMPTY=10593
STUB_PORT_EMPTY=10594
STUB_PID_NONEMPTY=""
STUB_PID_EMPTY=""

cleanup() {
    if [[ -n "${STUB_PID_NONEMPTY}" ]] && kill -0 "${STUB_PID_NONEMPTY}" 2>/dev/null; then
        kill "${STUB_PID_NONEMPTY}" 2>/dev/null || true
        wait "${STUB_PID_NONEMPTY}" 2>/dev/null || true
    fi
    if [[ -n "${STUB_PID_EMPTY}" ]] && kill -0 "${STUB_PID_EMPTY}" 2>/dev/null; then
        kill "${STUB_PID_EMPTY}" 2>/dev/null || true
        wait "${STUB_PID_EMPTY}" 2>/dev/null || true
    fi
    rm -rf "${WORK}"
}
trap cleanup EXIT

# ─── 路径 ────────────────────────────────────────────────────────────────
CLIENT="${REPO_ROOT}/analysis/call_audio_analysis.py"
STUB="${REPO_ROOT}/tests/audio_analysis_stub_server.py"
FIXTURE_NONEMPTY="${REPO_ROOT}/tests/fixtures/audio_analysis_stub_response_nonempty.json"
FIXTURE_EMPTY="${REPO_ROOT}/tests/fixtures/audio_analysis_stub_response_empty.json"
SCHEMA="${REPO_ROOT}/spec/schemas/audio_semantic.schema.json"

# ─── helpers ─────────────────────────────────────────────────────────────
run_client() {
    # wraps producer client with predictable workdir paths.
    # 附加 flags 通过 "$@" 透传（--offline / --force / --route-url ...）。
    python3 "${CLIENT}" \
        --video "${WORK}/video.mp4" \
        --shots "${WORK}/shots.json" \
        --work-dir "${WORK}" \
        --output "${WORK}/audio_semantic.json" \
        --stems-dir "${WORK}/stems" \
        "$@"
}

assert_file_exists() {
    local label="$1" path="$2"
    if [[ -f "${path}" ]]; then
        echo "  [PASS] ${label}: file exists (${path#${WORK}/})"
    else
        echo "  [FAIL] ${label}: file missing (${path})"
        exit 1
    fi
}

assert_file_absent() {
    local label="$1" path="$2"
    if [[ ! -f "${path}" ]]; then
        echo "  [PASS] ${label}: file absent (${path#${WORK}/})"
    else
        echo "  [FAIL] ${label}: file unexpectedly present (${path#${WORK}/})"
        exit 1
    fi
}

assert_grep() {
    local label="$1" pattern="$2" file="$3"
    if grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: grep '${pattern}' in $(basename "${file}")"
    else
        echo "  [FAIL] ${label}: grep '${pattern}' NOT found in $(basename "${file}")"
        cat "${file}" 2>/dev/null || echo "(file missing)"
        exit 1
    fi
}

assert_not_grep() {
    local label="$1" pattern="$2" file="$3"
    if ! grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: grep '${pattern}' NOT in $(basename "${file}") (expected)"
    else
        echo "  [FAIL] ${label}: grep '${pattern}' unexpectedly found in $(basename "${file}")"
        cat "${file}" 2>/dev/null
        exit 1
    fi
}

wait_stub_ready() {
    # 轮询 stub log 直到 "listening" 标记出现（最多 30×100ms=3s）
    local log="$1" label="$2"
    for _ in $(seq 1 30); do
        if grep -q "listening" "${log}" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    echo "[FAIL] ${label} did not announce ready within 3s"
    cat "${log}" 2>/dev/null || echo "(no log)"
    exit 1
}

# ─── prepare $WORK ───────────────────────────────────────────────────────
mkdir -p "${WORK}/stems"
cat > "${WORK}/shots.json" <<'JSON'
[{"id":1,"start_sec":0.0,"end_sec":1.5,"duration":1.5}]
JSON
# content-hash reads head/tail bytes; empty file is fine (stub ignores body anyway)
touch "${WORK}/video.mp4"

# ─── start nonempty stub ────────────────────────────────────────────────
echo "[smoke] starting nonempty stub on port ${STUB_PORT_NONEMPTY}..."
python3 -u "${STUB}" --fixture "${FIXTURE_NONEMPTY}" --port "${STUB_PORT_NONEMPTY}" \
    > "${WORK}/stub_nonempty.log" 2>&1 &
STUB_PID_NONEMPTY=$!
wait_stub_ready "${WORK}/stub_nonempty.log" "stub_server (nonempty)"

# ═══ SCENARIO 1: route-up + non-empty → write ═══════════════════════════
echo "[smoke] SCENARIO 1: route-up + non-empty → audio_semantic.json written + schema-valid"
SCEN1_LOG="${WORK}/scen1.log"
run_client --route-url "http://127.0.0.1:${STUB_PORT_NONEMPTY}/api/production/audio-analysis" \
    > "${SCEN1_LOG}" 2>&1
assert_file_exists "S1 audio_semantic.json written" "${WORK}/audio_semantic.json"

# schema-valid against audio_semantic.schema.json (Draft202012Validator)
python3 -c "
import json, jsonschema
schema = json.load(open('${SCHEMA}'))
payload = json.load(open('${WORK}/audio_semantic.json'))
jsonschema.Draft202012Validator(schema).validate(payload)
" && echo "  [PASS] S1 audio_semantic.json schema-valid (Draft202012Validator)" \
  || { echo "  [FAIL] S1 audio_semantic.json schema-invalid"; exit 1; }

assert_file_exists "S1 cache file written" "${WORK}/route_cache/audio_analysis/shot_001.json"
# 成功路径：[audio] warnings 应缺席（或 sidecar 全空）
if [[ -f "${WORK}/route_cache/warnings.json" ]]; then
    assert_not_grep "S1 zero [audio] warnings on success" "\\[audio\\]" "${WORK}/route_cache/warnings.json"
else
    echo "  [PASS] S1 zero [audio] warnings (sidecar absent — clean success)"
fi
# 快照 scenario 1 输出供 scenario 2 byte-diff
cp "${WORK}/audio_semantic.json" "${WORK}/scenario1.json"
echo "[smoke] SCENARIO 1: PASS"

# ═══ SCENARIO 2: cache-hit → byte-identical ═════════════════════════════
echo "[smoke] SCENARIO 2: --offline cache-hit → byte-identical to scenario 1"
SCEN2_LOG="${WORK}/scen2.log"
run_client --offline > "${SCEN2_LOG}" 2>&1
if diff -q "${WORK}/scenario1.json" "${WORK}/audio_semantic.json" >/dev/null; then
    echo "  [PASS] S2 byte-identical to scenario 1 (deterministic cache read)"
else
    echo "  [FAIL] S2 byte-different from scenario 1:"
    diff "${WORK}/scenario1.json" "${WORK}/audio_semantic.json" || true
    exit 1
fi
assert_grep "S2 cache hit logged" "shot 1: cache hit" "${SCEN2_LOG}"
echo "[smoke] SCENARIO 2: PASS"

# ═══ SCENARIO 3: poisoned cache → auto-invalidate ═══════════════════════
# 注：12-02-PLAN.md 原始 corruption (emotion=123) 会被 normalize_audio_semantic
# 静默丢弃（emotion 非 str/null 一律 skip）—— schema probe 永远 PASS，触发不了
# poisoned-invalidation 路径。改用 word.start=-5：passes normalize's isinstance
# guard (number) 但 violates schema minimum:0 → schema probe FAILS → unlink。
# 这是 Rule 1 deviation（test bug — plan 的 corruption 没触发预期的代码路径）。
echo "[smoke] SCENARIO 3: poisoned cache (word.start=-5 violates schema minimum:0)"
python3 -c "
import json
p = '${WORK}/route_cache/audio_analysis/shot_001.json'
d = json.load(open(p))
d['dialogue'] = {'words': [{'start': -5, 'end': 0.5, 'text': 'poison'}]}
json.dump(d, open(p, 'w'), ensure_ascii=False)
"
SCEN3_LOG="${WORK}/scen3.log"
run_client --offline > "${SCEN3_LOG}" 2>&1
assert_grep "S3 'invalidated poisoned cache' logged" "invalidated poisoned cache" "${SCEN3_LOG}"
assert_file_absent "S3 poisoned cache file unlinked" "${WORK}/route_cache/audio_analysis/shot_001.json"
assert_grep "S3 [audio] warning in sidecar" "\\[audio\\]" "${WORK}/route_cache/warnings.json"
echo "[smoke] SCENARIO 3: PASS"

# ═══ SCENARIO 4: full-degrade empty stub + read-merge-write ══════════════
echo "[smoke] SCENARIO 4: empty stub (stub_mode:true) → byte-identical-absent + cross-step tags preserved"
# 切到新端口 + 空 fixture（避免 TIME_WAIT 干扰）
echo "[smoke] starting empty stub on port ${STUB_PORT_EMPTY}..."
python3 -u "${STUB}" --fixture "${FIXTURE_EMPTY}" --port "${STUB_PORT_EMPTY}" \
    > "${WORK}/stub_empty.log" 2>&1 &
STUB_PID_EMPTY=$!
wait_stub_ready "${WORK}/stub_empty.log" "stub_server (empty)"

# 模拟跨 step warnings sidecar：预填 [semantic]+[reid]（read-merge-write 第 1 阶段）
mkdir -p "${WORK}/route_cache"
echo '{"warnings":["[semantic] shot 1: prefill","[reid] cluster 0: review"]}' \
    > "${WORK}/route_cache/warnings.json"

SCEN4_LOG="${WORK}/scen4.log"
run_client --route-url "http://127.0.0.1:${STUB_PORT_EMPTY}/api/production/audio-analysis" \
    --force > "${SCEN4_LOG}" 2>&1
assert_file_absent "S4 audio_semantic.json absent (CONTRACT-05 byte-identical v1.1)" "${WORK}/audio_semantic.json"
assert_grep "S4 [audio] warning appended" "\\[audio\\]" "${WORK}/route_cache/warnings.json"
assert_grep "S4 [semantic] tag preserved" "\\[semantic\\]" "${WORK}/route_cache/warnings.json"
assert_grep "S4 [reid] tag preserved" "\\[reid\\]" "${WORK}/route_cache/warnings.json"
echo "[smoke] SCENARIO 4: PASS"

# ═══ SCENARIO 5: offline + empty cache → byte-identical-absent ═══════════
echo "[smoke] SCENARIO 5: --offline --force + empty cache → byte-identical-absent + [audio] warning"
rm -rf "${WORK}/route_cache/audio_analysis"
SCEN5_LOG="${WORK}/scen5.log"
run_client --offline --force > "${SCEN5_LOG}" 2>&1
assert_file_absent "S5 audio_semantic.json absent" "${WORK}/audio_semantic.json"
assert_grep "S5 [audio] warning in sidecar" "\\[audio\\]" "${WORK}/route_cache/warnings.json"
echo "[smoke] SCENARIO 5: PASS"

echo ""
echo "ALL_SCENARIOS_PASS"
exit 0
