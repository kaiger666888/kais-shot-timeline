#!/usr/bin/env bash
# Phase 22 SC5 四场景 e2e harness（PIPE-02 / 22-04 Task 1）
#
# 证明 run_pipeline step_roundtrip→step_export→dataset post-step 全链（22-03
# wiring）在四类环境态下行为正确 —— mirror v1.2 Phase 14 / Phase 12
# tests/run_audio_analysis_smoke.sh 的 bash 编排形态（scenario 头 + assert
# helpers + cleanup trap + ALL_SCENARIOS_PASS exit 契约 + 前置环境探测）。
#
# Scenarios（22-04-PLAN must_haves 逐条对应）：
#   S1 ComfyUI down（离线确定性，/tmp fixture）：
#      a) 管线全 skip flags + --skip-export → h3_regen 探活降级
#         （roundtrip.json 缺席 + warnings comfyui_unreachable + 5 数据 JSON
#          md5 前后等值 + asset.json 未创建）
#      b) 同 fixture 去掉 --skip-export 重跑 → export fresh（asset.json 存在
#         且无 data.roundtrip 键 —— absent-不挂载 pipeline 级证明）
#      c) 再跑 → export cache-hit（asset.json md5 等值）
#   S2 抽样 e2e 真跑（ep01 COPY 上 live，SC1 证明）：run_pipeline --sample-shots 2
#      → 全链产四类产物（asset 1.3 + data.roundtrip 4/15 + review HTML 19 卡 +
#      dataset 目录/manifest/两清单）；verdict 冻结块 byte-equal + 正本
#      roundtrip.json sha 全程不变。COPY 载体的原因（Task 2 实测发现，Rule 1
#      plan bug）：ep01 的 prompts.json 在 direct-module 时代从未被 attach_refs
#      归一化——管线首跑会 recompose prompt_text → h3_regen 的 per-shot cache
#      key 含 prompt_version=sha256(prompt_text)[:8] → 19 镜 overnight 渲染
#      缓存全失效。在正本上重渲 = 改写冻结 regen/scores 半边（HITL 红线）；
#      故 S2/S3/S4 全部在 cp -a 副本上跑，正本只做 sha 三点断言（证明零触碰）。
#      首跑副本：attach_refs no-op（已归一化）→ h3_regen 真渲 2 镜（rendered=2）
#      → scorer 全量补分 19 镜（直调时代的正本 cache 是五字段扁平旧 schema，
#      WR-02 orig_window 进 key 后全 stale——hit=0 miss-scored=19）→ judge
#      applied=0 frozen=19（verdict 冻结在新渲染上不动 —— 比 plan 预期的
#      cache-hit 更强的冻结证明）。
#   S3 抽样模式（ep01 COPY 上，GPU1-gated 双分支）：S2 已暖 1/47 缓存 → 直调
#      h3_regen --sample-shots 2 → 2/93 镜入样 + cache-hit=2 rendered=0 +
#      sidecar 19 镜 READ-merge 不丢 + scorer/judge 直调全 cache 命中冻结
#      不动；GPU1 free（/free 后）< 22528MiB → 文档化降级分支（PASS-with-note）
#   S4 VRAM-guard 拒提交（确定性，GPU0=3060Ti ~4.9GB free）：直调 h3_regen
#      --gpu-index 0 → 批开始 guard 拒绝 + vram_insufficient + exit 0 +
#      sidecar sha 等值（cache 保留，二跑可续）
#
# 环境旋钮：
#   P22_LIVE=0       只跑 S1（离线确定性）+ 探测；S2/S3/S4 标 SKIP-with-note
#                    （Task 1 本地离线验证用；live 三场景需 ComfyUI up）
#   P22_EP_DIR=path  复用已暖副本（跳过 cp -a + 跳过重渲：外层 cache 命中
#                    `[9/10] cached roundtrip sidecar` 稳态锚）——Task 2 的
#                    幂等复跑用（mirror plan「复跑一遍全绿」分钟级预期）
#   P22_COMFY_URL    ComfyUI API URL（默认 http://127.0.0.1:8188）
#
# 全部 PASS → echo "ALL_SCENARIOS_PASS" + exit 0；任一 FAIL → exit 1 + 证据。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d /tmp/p22-e2e-XXXXXX)"
P22_LIVE="${P22_LIVE:-1}"
COMFY_URL="${P22_COMFY_URL:-http://127.0.0.1:8188}"
# 批开始 guard 的 GPU 门槛（h3_regen BATCH_MIN_FREE_MIB=22528，22GB）
VRAM_GATE_MIB=22528

# 清理契约：全 PASS 且未设 P22_KEEP → 删 WORK；FAIL 或 P22_KEEP=1 → 保留并
# 打印路径（FAIL 证据 + 已暖副本可复用：P22_EP_DIR 指向其 rt/<stem> 做幂等复跑）。
ALL_PASS=0
cleanup() {
    if [[ "${ALL_PASS}" == "1" && -z "${P22_KEEP:-}" ]]; then
        rm -rf "${WORK}"
    else
        echo "[cleanup] WORK 保留（ALL_PASS=${ALL_PASS} P22_KEEP=${P22_KEEP:-0}）：${WORK}"
    fi
}
trap cleanup EXIT

# ─── helpers（mirror run_audio_analysis_smoke.sh）─────────────────────────
assert_file_exists() {
    local label="$1" path="$2"
    if [[ -f "${path}" ]]; then
        echo "  [PASS] ${label}: file exists (${path##*/})"
    else
        echo "  [FAIL] ${label}: file missing (${path})"
        exit 1
    fi
}

assert_file_absent() {
    local label="$1" path="$2"
    if [[ ! -f "${path}" ]]; then
        echo "  [PASS] ${label}: file absent (${path##*/})"
    else
        echo "  [FAIL] ${label}: unexpectedly present (${path})"
        exit 1
    fi
}

assert_grep() {
    local label="$1" pattern="$2" file="$3"
    if grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: grep '${pattern}'"
    else
        echo "  [FAIL] ${label}: pattern '${pattern}' NOT found in ${file}"
        cat "${file}" 2>/dev/null || echo "(file missing)"
        exit 1
    fi
}

assert_not_grep() {
    local label="$1" pattern="$2" file="$3"
    if ! grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: pattern '${pattern}' NOT in log (expected)"
    else
        echo "  [FAIL] ${label}: pattern '${pattern}' unexpectedly found"
        grep -nE "${pattern}" "${file}" | head -5
        exit 1
    fi
}

# 状态感知 OR：ep01 首跑（video-stamp 缺席 → 全链跑）与复跑（外层 cache 命中）
# 的合法锚不同 —— 两锚任一命中即 PASS，并把命中态打进证据。
assert_either_grep() {
    local label="$1" pat_a="$2" pat_b="$3" file="$4"
    if grep -qE "${pat_a}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: matched [${pat_a}]"
    elif grep -qE "${pat_b}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: matched [${pat_b}] (steady-state anchor)"
    else
        echo "  [FAIL] ${label}: neither '${pat_a}' nor '${pat_b}' in ${file}"
        tail -30 "${file}" 2>/dev/null || echo "(file missing)"
        exit 1
    fi
}

assert_md5_equal() {
    local label="$1" a="$2" b="$3"
    if [[ "$(md5sum "${a}" | cut -d' ' -f1)" == "$(md5sum "${b}" | cut -d' ' -f1)" ]]; then
        echo "  [PASS] ${label}: md5 equal"
    else
        echo "  [FAIL] ${label}: md5 differs (${a} vs ${b})"
        exit 1
    fi
}

assert_sha_equal() {
    local label="$1" a="$2" b="$3"
    if [[ "$(sha256sum "${a}" | cut -d' ' -f1)" == "$(sha256sum "${b}" | cut -d' ' -f1)" ]]; then
        echo "  [PASS] ${label}: sha256 equal"
    else
        echo "  [FAIL] ${label}: sha256 differs (${a} vs ${b})"
        exit 1
    fi
}

# ─── 前置环境探测（Pitfall 3 fail-fast with reason）──────────────────────
probe_comfyui() {
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
        "${COMFY_URL}/system_stats" 2>/dev/null || echo 000)"
    echo "${code}"
}

probe_gpu_free_mib() {
    # $1 = gpu index；nvidia-smi 失败输出 -1（调用方走降级分支）
    nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits \
        -i "$1" 2>/dev/null | tr -d ' ' || echo -1
}

probe_tts() {
    # TTS 5110/5111 监听时 guard 的 step① kill 会命中真实服务 —— 打印警告
    if ss -tlnp 2>/dev/null | grep -qE ':(5110|5111)\b'; then
        echo "[probe][WARN] TTS 5110/5111 正在监听 —— h3_regen 批前 guard 的 TTS kill 将命中真实进程（设计行为，请知悉）"
    else
        echo "[probe] TTS 5110/5111 未监听（guard kill no-op 安全）"
    fi
}

# run_logged <label> <timeout_sec> <log> <cmd...>：非 0 退出 → FAIL + 日志尾。
# timeout 杀（rc=124）也会走这里（set -e 下裸跑会静默退出，丢诊断）。
run_logged() {
    local label="$1" secs="$2" log="$3"
    shift 3
    if ! timeout "${secs}" "$@" > "${log}" 2>&1; then
        echo "  [FAIL] ${label}: 非 0 退出（timeout ${secs}s 或自身错误），日志尾："
        tail -40 "${log}" 2>/dev/null || echo "(no log)"
        exit 1
    fi
}

echo "═══ Phase 22 SC5 e2e harness ═══"
echo "[probe] ComfyUI ${COMFY_URL}/system_stats → HTTP $(probe_comfyui)"
GPU0_FREE="$(probe_gpu_free_mib 0)"
GPU1_FREE="$(probe_gpu_free_mib 1)"
echo "[probe] GPU0 free=${GPU0_FREE}MiB / GPU1 free=${GPU1_FREE}MiB (guard gate ${VRAM_GATE_MIB}MiB)"
probe_tts
echo "[probe] P22_LIVE=${P22_LIVE}"

# ─── S1 fixture 构造（Pitfall 6：ep01 现态不可用于 absent 场景）──────────
mk_fixture_workdir() {
    local out_dir="$1"   # = $WORK/out（--output-dir）
    local stem="tiny"
    local wd="${out_dir}/${stem}"

    # ~4s 640x360 h264 mp4，带静音 aac 音轨（export_asset 要求 video 含 audio
    # 流；-an 的纯视频会在 export 直接 sys.exit —— Pitfall: h264.mp4 同理）
    ffmpeg -y -v error -f lavfi -i testsrc=duration=4:size=640x360:rate=24 \
        -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -t 4 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
        "${WORK}/tiny.mp4"

    mkdir -p "${wd}/stems/htdemucs/${stem}"
    # 3 个 canonical stem wav（vocals/drums/other —— 无 bass，schema 拒绝）
    for t in vocals drums other; do
        ffmpeg -y -v error -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=44100" \
            -t 4 -c:a pcm_s16le "${wd}/stems/htdemucs/${stem}/${t}.wav"
    done

    # 真实 1 帧 jpg → data URI（frames.json 的 first/last_frame 必须非空，
    # 否则 frames 消费方会走重抽帧路径）
    ffmpeg -y -v error -ss 1 -i "${WORK}/tiny.mp4" -frames:v 1 \
        -vf scale=160:90 "${WORK}/frame.jpg"
    local DATA_URI
    DATA_URI="data:image/jpeg;base64,$(base64 -w0 "${WORK}/frame.jpg")"

    # 5 个数据 JSON（shape mirror ep01 真实产物 —— 2 镜全覆盖 4s 时长）
    cat > "${wd}/shots.json" <<'JSON'
[{"id":1,"start_sec":0.0,"end_sec":2.0,"duration":2.0},
 {"id":2,"start_sec":2.0,"end_sec":4.0,"duration":2.0}]
JSON
    python3 - "$wd" "$DATA_URI" <<'PYEOF'
import json, sys
wd, uri = sys.argv[1], sys.argv[2]
energies = {"vocals": 0.05, "drums": 0.01, "bass": 0.01, "other": 0.02}
ratios = {"vocals": 0.6, "drums": 0.1, "bass": 0.1, "other": 0.2}
centroid = {"vocals": 2400.0, "drums": 4300.0, "bass": 8500.0, "other": 5800.0}
json.dump({
    "episode": "tiny", "duration": 4.0,
    "stems": ["vocals", "drums", "bass", "other"],
    "shots": [
        {"shot_id": 1, "start_sec": 0.0, "end_sec": 2.0, "duration": 2.0,
         "energies": energies, "ratios": ratios,
         "spectral_centroid": centroid, "dominant_type": "dialogue"},
        {"shot_id": 2, "start_sec": 2.0, "end_sec": 4.0, "duration": 2.0,
         "energies": energies, "ratios": ratios,
         "spectral_centroid": centroid, "dominant_type": "bgm"},
    ],
    "type_distribution": {"dialogue": 1, "bgm": 1},
}, open(f"{wd}/audio_analysis.json", "w", encoding="utf-8"),
    ensure_ascii=False, indent=2)
json.dump({
    "backend": "openai-whisper", "model": "tiny", "language": "zh",
    "segments": [{"start": 0.0, "end": 3.5, "text": "离线固定测试对白"}],
    "text": "离线固定测试对白", "duration": 4.0, "source": "tiny.mp4",
}, open(f"{wd}/transcript.json", "w", encoding="utf-8"),
    ensure_ascii=False, indent=2)
json.dump([
    {"id": 1, "first_frame": uri, "last_frame": uri},
    {"id": 2, "first_frame": uri, "last_frame": uri},
], open(f"{wd}/frames.json", "w", encoding="utf-8"),
    ensure_ascii=False, indent=2)
facets = {"subject": "绒毛小生物", "action": "向前奔跑", "camera": "跟随镜头",
          "scene": "阳光森林", "lighting": "白昼自然光", "style": "三维动画"}
prompts = []
for sid, (s, e) in ((1, (0.0, 2.0)), (2, (2.0, 4.0))):
    p = {"shot_id": sid, "start_sec": s, "end_sec": e, "duration": 2.0,
         "prompt_text": "placeholder", "character_refs": [], "prop_refs": []}
    p.update(facets)
    prompts.append(p)
json.dump(prompts, open(f"{wd}/prompts.json", "w", encoding="utf-8"),
    ensure_ascii=False, indent=2)
PYEOF

    # h3_regen resolve_source_video：h264.mp4 缺席回退 video.mp4（都缺 → 非
    # degrade 语境的硬退出）；export 的 ensure_symlink 同名同 target 幂等跳过。
    ln -sf "${WORK}/tiny.mp4" "${wd}/video.mp4"

    # attach_refs 归一化 pass：把 prompt_text recompose 成稳态 —— 后续管线内的
    # attach_refs pre-step 零改动不重写（22-04 Rule 3 guard），prompts.json mtime
    # 保持稳定 → S1 断言「5 数据 JSON md5 前后等值」可过。
    python3 "${REPO_ROOT}/prompts/attach_refs.py" \
        --prompts "${wd}/prompts.json" --work-dir "${wd}" >/dev/null
}

# ═══ SCENARIO 1: ComfyUI down → 全链 graceful-degrade（离线确定性）═══════
echo ""
echo "═══ SCENARIO 1: ComfyUI down（fixture）—— degrade + absent-不挂载 + export cache ═══"
mk_fixture_workdir "${WORK}/out"
FIX_WD="${WORK}/out/tiny"

PIPE_SKIP_FLAGS=(--skip-detect --skip-separate --skip-transcribe --skip-semantic
                 --skip-reid --skip-audio-semantic --skip-speaker-link
                 --no-local-vision --no-vision-seq)

# 5 数据 JSON md5 快照（证明 pre-step 零重写 —— Rule 3 guard 的 e2e 锁）
mkdir -p "${WORK}/snap"
for f in shots audio_analysis transcript frames prompts; do
    cp "${FIX_WD}/${f}.json" "${WORK}/snap/${f}.json"
done

# —— 子跑 a：--skip-export + ComfyUI 指到必拒端口 → degrade 链 ——
S1A_LOG="${WORK}/s1a.log"
run_logged "S1a pipeline" 300 "${S1A_LOG}" \
    python3 "${REPO_ROOT}/run_pipeline.py" \
    --video "${WORK}/tiny.mp4" --output-dir "${WORK}/out" \
    "${PIPE_SKIP_FLAGS[@]}" --skip-export \
    --comfy-url "http://127.0.0.1:1" --sample-shots 2
echo "  [PASS] S1a pipeline exit 0（graceful-degrade 全链不崩）"

assert_grep "S1a h3_regen 探活降级日志" "ComfyUI 不可达（status=" "${S1A_LOG}"
assert_grep "S1a step_roundtrip 降级说明" "roundtrip\.json 缺席（h3_regen 降级" "${S1A_LOG}"
assert_grep "S1a dataset post-step 跳过警告" "\[roundtrip-dataset\] warning: roundtrip\.json 不存在" "${S1A_LOG}"
assert_not_grep "S1a scorer 未空转" "roundtrip scoring" "${S1A_LOG}"
assert_not_grep "S1a judge 未空转" "roundtrip judge" "${S1A_LOG}"
assert_file_absent "S1a roundtrip.json absent（degrade 不产 sidecar）" "${FIX_WD}/roundtrip.json"
assert_file_absent "S1a roundtrip_review.html absent" "${FIX_WD}/roundtrip_review.html"
assert_file_exists "S1a warnings sidecar 写入" "${FIX_WD}/route_cache/warnings.json"
assert_grep "S1a warnings 记 comfyui_unreachable" "comfyui_unreachable" "${FIX_WD}/route_cache/warnings.json"
assert_file_absent "S1a asset.json 未创建（--skip-export）" "${FIX_WD}/asset.json"
for f in shots audio_analysis transcript frames prompts; do
    assert_md5_equal "S1a ${f}.json 未被 pre-step 重写" "${WORK}/snap/${f}.json" "${FIX_WD}/${f}.json"
done

# —— 子跑 b：去掉 --skip-export → export fresh（无 data.roundtrip 键）——
S1B_LOG="${WORK}/s1b.log"
run_logged "S1b pipeline" 300 "${S1B_LOG}" \
    python3 "${REPO_ROOT}/run_pipeline.py" \
    --video "${WORK}/tiny.mp4" --output-dir "${WORK}/out" \
    "${PIPE_SKIP_FLAGS[@]}" \
    --comfy-url "http://127.0.0.1:1" --sample-shots 2
echo "  [PASS] S1b pipeline exit 0"
assert_grep "S1b export fresh 跑" "\[10/10\] ShotTimelineAsset export" "${S1B_LOG}"
assert_file_exists "S1b asset.json 产出" "${FIX_WD}/asset.json"
if python3 -c "
import json, sys
a = json.load(open('${FIX_WD}/asset.json'))
sys.exit(0 if 'roundtrip' not in a.get('data', {}) else 1)
"; then
    echo "  [PASS] S1b data.roundtrip 键 absent（degrade 不挂载 —— pipeline 级证明）"
else
    echo "  [FAIL] S1b data.roundtrip unexpectedly mounted"
    exit 1
fi
cp "${FIX_WD}/asset.json" "${WORK}/snap/asset_b.json"

# —— 子跑 c：再跑 → export cache-hit + md5 等值 ——
S1C_LOG="${WORK}/s1c.log"
run_logged "S1c pipeline" 300 "${S1C_LOG}" \
    python3 "${REPO_ROOT}/run_pipeline.py" \
    --video "${WORK}/tiny.mp4" --output-dir "${WORK}/out" \
    "${PIPE_SKIP_FLAGS[@]}" \
    --comfy-url "http://127.0.0.1:1" --sample-shots 2
echo "  [PASS] S1c pipeline exit 0"
assert_grep "S1c export cache-hit" "\[10/10\] cached asset" "${S1C_LOG}"
assert_md5_equal "S1c asset.json md5 等值（cache 命中不重写）" "${WORK}/snap/asset_b.json" "${FIX_WD}/asset.json"
echo "[smoke] SCENARIO 1: PASS"

# ═══ live 前置：ep01 定位 + ComfyUI 探活 ═══════════════════════════════
# CJK work_dir 全程 glob 取路径零硬编码（Pitfall 4）
EP01_REL="$(cd "${REPO_ROOT}" && ls -d output/*第01话* | head -1)"
if [[ -z "${EP01_REL}" || ! -d "${REPO_ROOT}/${EP01_REL}" ]]; then
    echo "[FAIL] ep01 work dir not found under output/ (glob *第01话*)"
    exit 1
fi
EP01_DIR="${REPO_ROOT}/${EP01_REL}"
RT_JSON="${EP01_DIR}/roundtrip.json"
COMFY_CODE="$(probe_comfyui)"

if [[ "${P22_LIVE}" != "1" ]]; then
    echo ""
    echo "[SKIP] P22_LIVE=0 —— S2/S3/S4（live 三场景）按要求跳过；S1 + 探测已绿"
    echo ""
    echo "ALL_SCENARIOS_PASS"
    exit 0
fi

if [[ "${COMFY_CODE}" != "200" ]]; then
    echo "[FAIL] ComfyUI ${COMFY_URL}/system_stats → HTTP ${COMFY_CODE}（live 三场景硬前置；拉起后重跑）"
    exit 1
fi

# 冻结红线基线（正本）：roundtrip.json sha256 快照——S2/S3/S4 后三点复测等值，
# 证明 harness 全程零触碰正本（Task 3 Kai 走查的就是这份冻结数据）。
RT_SHA_BASE="${WORK}/rt_sha_base"
sha256sum "${RT_JSON}" | cut -d' ' -f1 > "${RT_SHA_BASE}"
echo "[freeze] 正本 roundtrip.json sha256 基线 = $(cat "${RT_SHA_BASE}")"

assert_freeze_sha() {
    local label="$1"
    local now
    now="$(sha256sum "${RT_JSON}" | cut -d' ' -f1)"
    if [[ "${now}" == "$(cat "${RT_SHA_BASE}")" ]]; then
        echo "  [PASS] ${label}: 正本 roundtrip.json sha256 等值（零触碰冻结红线）"
    else
        echo "  [FAIL] ${label}: 正本 sha256 漂移：${now} != $(cat "${RT_SHA_BASE}")"
        exit 1
    fi
}

# verdict 冻结块指纹（副本侧红线：regen/scores 半边可随重渲更新，verdict
# 半边是冻结人工数据——19 镜的 verdict 对象 byte-equal）。
verdict_blocks_sha() {
    python3 - "$1" <<'PYV'
import hashlib, json, sys
rt = json.load(open(sys.argv[1]))
blocks = {str(s["shot_id"]): s.get("verdict") for s in rt["shots"]}
canon = json.dumps(blocks, ensure_ascii=False, sort_keys=True, indent=2)
print(hashlib.sha256(canon.encode()).hexdigest())
PYV
}

# ─── ep01 工作副本（Task 2 实测发现的载体架构，见文件头 S2 注释）────────
# P22_EP_DIR 指向已暖副本（S2 已跑过 → 外层 cache 命中稳态）时直接复用；
# 否则 cp -a 全量副本（775M，mtime 全保留 → timeline/export cache 语义一致）。
if [[ -n "${P22_EP_DIR:-}" ]]; then
    EP_WORK="${P22_EP_DIR}"
    echo "[copy] 复用已暖副本：${EP_WORK}"
else
    COPY_ROOT="${WORK}/rt"
    mkdir -p "${COPY_ROOT}"
    echo "[copy] cp -a 正本 → 副本（${EP01_DIR} → ${COPY_ROOT}/）……"
    cp -a "${EP01_DIR}" "${COPY_ROOT}/"
    EP_WORK="${COPY_ROOT}/$(basename "${EP01_DIR}")"
fi
if [[ ! -f "${EP_WORK}/roundtrip.json" ]]; then
    echo "[FAIL] 副本 roundtrip.json missing: ${EP_WORK}"
    exit 1
fi
RT_WORK="${EP_WORK}/roundtrip.json"
VB_BASE="$(verdict_blocks_sha "${RT_WORK}")"
echo "[freeze] 副本 verdict 冻结块指纹基线 = ${VB_BASE}"

assert_verdict_freeze() {
    local label="$1"
    local now
    now="$(verdict_blocks_sha "${RT_WORK}")"
    if [[ "${now}" == "${VB_BASE}" ]]; then
        echo "  [PASS] ${label}: 副本 19 镜 verdict 冻结块 byte-equal"
    else
        echo "  [FAIL] ${label}: verdict 冻结块漂移（${now} != ${VB_BASE}）"
        exit 1
    fi
}

# ═══ SCENARIO 2: ep01 副本抽样 e2e 真跑（SC1 live 证明）═════════════════
echo ""
echo "═══ SCENARIO 2: ep01 副本 --sample-shots 2 端到端（asset 1.3 + dataset + HTML 19 卡）═══"
# Deviation（Rule 1 plan bug）：plan 写 --video "$EP01/h264.mp4"，但 h264.mp4
# 是 -an 去 audio 的转码中间产物 → export_asset sys.exit "video has no audio
# stream"。改传 readlink -f video.mp4（原始片源，含音轨；与 ep01 既有
# video-stamp/canonical symlink 同一身份 → cache 语义不变）。
EP01_VIDEO="$(readlink -f "${EP01_DIR}/video.mp4")"
if [[ ! -f "${EP01_VIDEO}" ]]; then
    echo "[FAIL] ep01 original video missing: ${EP01_VIDEO}"
    exit 1
fi

# Deviation（Rule 3 环境确定性）：S2 显式钉死 step 1-7 的全部 skip flag——
# ep01 五数据文件齐备且冻结，但 step 5/6/7 的路由（10588 shot-analysis /
# reid / audio-analysis）实测 ALIVE：外层 cache stamps 缺席（prompts.video-stamp
# 等）+ per-shot route_cache 已清空 → 不跳过会向路由真提交 93 镜任务（小时级，
# 且非 SC1 证明面）。--skip-semantic 连带跳过 5.5/5.6 qwen-eye pre-steps
#（ep01 facets 93/93 全满 → 语义 no-op，且避免 21.9GB llama-server 冷启动×2）。
# SC1 证明面 = step 9/10 + dataset post-step 的 wiring，不受早期 step skip 影响。
S2_SKIP_FLAGS=(--skip-detect --skip-separate --skip-transcribe --skip-semantic
               --skip-reid --skip-audio-semantic --skip-speaker-link)
S2_LOG="${WORK}/s2.log"
# timeout 1800：全新副本首跑 = 真渲 2 镜（fl2va 单镜 ~8min ×2 + scorer/judge/
# export/dataset）；P22_EP_DIR 暖副本复跑 = 外层 cache 命中秒级。
run_logged "S2 pipeline" 1800 "${S2_LOG}" \
    python3 "${REPO_ROOT}/run_pipeline.py" \
    --video "${EP01_VIDEO}" --output-dir "$(dirname "${EP_WORK}")" \
    "${S2_SKIP_FLAGS[@]}" \
    --sample-shots 2
echo "  [PASS] S2 pipeline exit 0（全链四类产物一次齐产）"

# 状态感知锚：全新副本首跑（video-stamp 缺席 → 全链 miss + 真渲 2 镜）vs
# 暖副本复跑（外层 cache 命中短路整链）
assert_either_grep "S2 step_roundtrip 链（首跑 regen / 复跑 cached）" \
    "\[9/10\] cached roundtrip sidecar" "\[9/10\] roundtrip regen \(h3" "${S2_LOG}"
if grep -qE "\[9/10\] roundtrip regen \(h3" "${S2_LOG}"; then
    # 首跑重渲锚（Rule 1 deviation：attach_refs 首次归一化 ep01 prompts →
    # prompt_version bump → 19 镜 overnight h3 缓存全失效；plan 预期的
    # rendered=0 cache-hit=2 在正本上不可达，副本上以真渲 + judge 冻结证明）
    assert_grep "S2 h3_regen 重渲 2 镜零失败" "完成：rendered=2 cache-hit=0 failed=0" "${S2_LOG}"
    # scorer 六字段 key 含 orig_window（WR-02 镜几何进 key）——直调时代的
    # 正本 cache 是五字段扁平旧 schema（无 orig_window）→ 19 镜全 stale，
    # 首跑全量补分（SigLIP 一次加载 19 镜打分，cache 以新 key 重写；S3 的
    # 「全部 cache 命中」证明新 key 稳态命中）。
    assert_grep "S2 scorer 全量补分（旧五字段 cache 全 stale）" "完成：hit=0 miss-scored=19 failed=0" "${S2_LOG}"
    assert_grep "S2 judge 冻结不动（新渲染上 verdict 仍冻结）" "applied=0 frozen=19" "${S2_LOG}"
fi
assert_grep "S2 review HTML 产出" "\[roundtrip-review\] wrote .* \(19 shots\)" "${S2_LOG}"
assert_either_grep "S2 export（fresh 重导出 / cached）" \
    "\[10/10\] ShotTimelineAsset export" "\[10/10\] cached asset" "${S2_LOG}"
assert_grep "S2 dataset post-step 跑" "\[roundtrip-dataset\] 完成" "${S2_LOG}"

# asset.json：schema 1.3 + data.roundtrip 4/15（陈旧 asset 重导出 —— roundtrip.json
# mtime 新于 asset.json → Pattern 4 条件 input 强制 miss；verdict 计数不受重渲影响）
python3 - "${EP_WORK}/asset.json" <<'PYEOF'
import json, sys
a = json.load(open(sys.argv[1]))
assert a.get("schema_version") == "1.3", f"schema_version={a.get('schema_version')!r}"
rt = a.get("data", {}).get("roundtrip")
assert rt is not None, "data.roundtrip missing"
assert rt.get("accepted_count") == 4, f"accepted_count={rt.get('accepted_count')}"
assert rt.get("rejected_count") == 15, f"rejected_count={rt.get('rejected_count')}"
print("  [PASS] S2 asset.json schema_version=1.3 + data.roundtrip{accepted:4, rejected:15}")
PYEOF

# review HTML 19 卡
HTML_CARDS="$(grep -c 'class="shot-card' "${EP_WORK}/roundtrip_review.html" || true)"
if [[ "${HTML_CARDS}" == "19" ]]; then
    echo "  [PASS] S2 roundtrip_review.html 19 卡"
else
    echo "  [FAIL] S2 roundtrip_review.html cards=${HTML_CARDS} (expected 19)"
    exit 1
fi

# dataset 目录：manifest + 两清单 + 4 个 accepted shot 目录（dataset-root =
# 副本 work_dir 同级 dataset/ —— 副本树内，不污染 repo output/）
EP01_STEM="$(basename "${EP01_DIR}")"
DS_DIR="$(dirname "${EP_WORK}")/dataset/${EP01_STEM}"
for d in shot_010 shot_061 shot_075 shot_084; do
    assert_file_exists "S2 dataset ${d}/" "${DS_DIR}/${d}/prompt.json"
    assert_file_exists "S2 dataset ${d} 首帧" "${DS_DIR}/${d}/first_frame.jpg"
done
python3 - "${DS_DIR}" <<'PYEOF'
import json, sys
d = sys.argv[1]
m = json.load(open(f"{d}/manifest.json"))
assert m["accepted_count"] == 4, f"manifest accepted={m['accepted_count']}"
assert m["rejected_count"] == 15, f"manifest rejected={m['rejected_count']}"
b = m["rejected_buckets"]
assert sum(b.values()) == 15, f"buckets sum={sum(b.values())} != 15: {b}"
acc = [l.strip() for l in open(f"{d}/accepted.txt", encoding="utf-8") if l.strip()]
rej = [l.strip() for l in open(f"{d}/rejected.txt", encoding="utf-8") if l.strip()]
assert len(acc) == 4, f"accepted.txt {len(acc)} lines"
assert len(rej) == 15, f"rejected.txt {len(rej)} lines"
# WR-03 后 manifest τ 双记：verdict_tau（决策时刻留档，旧 sidecar 先于留档机制可为 null）
# + export_tau（本次导出 CLI 值）——harness 断言取 export_tau（B1 修复 2026-08-20）
assert m.get("export_tau") == 0.9670, f"manifest export_tau={m.get('export_tau')}"
print(f"  [PASS] S2 manifest 4/15 + buckets {b} + accepted.txt 4 行 + rejected.txt 15 行 + export_tau=0.9670（verdict_tau={m.get('verdict_tau')}）")
PYEOF

# 冻结红线第 1 点：正本零触碰 + 副本 verdict 块 byte-equal
assert_freeze_sha "S2 后"
assert_verdict_freeze "S2 后"
RT_WORK_SHA_S2="$(sha256sum "${RT_WORK}" | cut -d' ' -f1)"
echo "${RT_WORK_SHA_S2}" > "${WORK}/rt_work_sha_s2"
cp "${EP_WORK}/asset.json" "${WORK}/snap/asset_s2.json"
echo "[smoke] SCENARIO 2: PASS"

# ═══ SCENARIO 3: 抽样模式直调（副本上，GPU1-gated 双分支）══════════════
echo ""
echo "═══ SCENARIO 3: h3_regen --sample-shots 2 直调（GPU1 gate=${VRAM_GATE_MIB}MiB）═══"
# gate 探测在 S2 之后现测：S2 渲染后 ComfyUI 驻留模型 → 先 best-effort POST
# /free（mirror guard 步骤② 的既有语义；队列为空时仅卸模型）再读 free。
curl -s --max-time 10 -X POST -H 'Content-Type: application/json' \
    -d '{"unload_models": true, "free_memory": true}' \
    "${COMFY_URL}/free" >/dev/null 2>&1 || true
sleep 4
GPU1_FREE_NOW="$(probe_gpu_free_mib 1)"
echo "[probe] S3 前置（/free 后）GPU1 free=${GPU1_FREE_NOW}MiB"
if [[ "${GPU1_FREE_NOW}" -ge ${VRAM_GATE_MIB} ]]; then
    S3_LOG="${WORK}/s3.log"
    run_logged "S3 h3_regen 直调" 300 "${S3_LOG}" \
        python3 "${REPO_ROOT}/analysis/roundtrip/h3_regen.py" \
        --work-dir "${EP_WORK}" --comfy-url "${COMFY_URL}" \
        --sample-shots 2 --vram-wait-timeout 90
    echo "  [PASS] S3 h3_regen exit 0（guard 五步过 gate）"
    assert_grep "S3 抽样 2/93 镜入样" "2/93 镜入样" "${S3_LOG}"
    assert_grep "S3 cache-hit=2 rendered=0（S2 已暖 1/47 缓存）" "rendered=0 cache-hit=2" "${S3_LOG}"

    S3_SCORE_LOG="${WORK}/s3_scorer.log"
    run_logged "S3 scorer 直调" 300 "${S3_SCORE_LOG}" \
        python3 "${REPO_ROOT}/analysis/roundtrip/scorer.py" \
        --work-dir "${EP_WORK}"
    assert_grep "S3 scorer 直调全 cache 命中" "全部 cache 命中" "${S3_SCORE_LOG}"

    S3_JUDGE_LOG="${WORK}/s3_judge.log"
    run_logged "S3 judge 直调" 300 "${S3_JUDGE_LOG}" \
        python3 "${REPO_ROOT}/analysis/roundtrip/judge.py" \
        --work-dir "${EP_WORK}" --comfy-url "${COMFY_URL}" \
        --apply-verdict --tau-sim 0.9670
    assert_grep "S3 judge 直调冻结不动" "applied=0 frozen=19" "${S3_JUDGE_LOG}"

    # sidecar READ-merge 不丢存量：仍 19 镜 + sha 等值（vs S2 后快照——cache-hit
    # 重写 byte-identical）+ 冻结红线第 2 点
    python3 -c "
import json, sys
rt = json.load(open('${RT_WORK}'))
assert len(rt['shots']) == 19, f\"sidecar shots={len(rt['shots'])} != 19（READ-merge 丢存量）\"
print('  [PASS] S3 sidecar 仍 19 镜（READ-merge 不丢存量）')
"
    RT_NOW_WORK="$(sha256sum "${RT_WORK}" | cut -d' ' -f1)"
    if [[ "${RT_NOW_WORK}" == "$(cat "${WORK}/rt_work_sha_s2")" ]]; then
        echo "  [PASS] S3 后副本 sidecar sha256 等值（cache-hit 重写 byte-identical）"
    else
        echo "  [FAIL] S3 后副本 sha256 漂移：${RT_NOW_WORK} != $(cat "${WORK}/rt_work_sha_s2")"
        exit 1
    fi
    assert_verdict_freeze "S3 后"
    assert_freeze_sha "S3 后"
    echo "[smoke] SCENARIO 3: PASS"
else
    # 文档化降级分支（PASS-with-note）：GPU1 free < gate 是环境余量，非功能失败。
    # 模块级 cache 语义已由 Phase 20 pytest + S2 链路覆盖；S4 独立证明 guard 语义。
    echo "  [SKIP] GPU1 free=${GPU1_FREE_NOW} < ${VRAM_GATE_MIB}（环境余量，非功能失败；模块级 cache 已由 Phase 20 测试 + S2 链路覆盖）"
    echo "[smoke] SCENARIO 3: PASS-with-note（GPU1 余量不足走文档化降级分支）"
fi

# ═══ SCENARIO 4: VRAM-guard 拒提交（副本上，GPU0=3060Ti 确定性触发）════
echo ""
echo "═══ SCENARIO 4: h3_regen --gpu-index 0 → 批开始 guard 拒提交 ═══"
GPU0_FREE_NOW="$(probe_gpu_free_mib 0)"
if [[ "${GPU0_FREE_NOW}" -lt ${VRAM_GATE_MIB} ]]; then
    S4_LOG="${WORK}/s4.log"
    run_logged "S4 h3_regen 直调（--gpu-index 0）" 300 "${S4_LOG}" \
        python3 "${REPO_ROOT}/analysis/roundtrip/h3_regen.py" \
        --work-dir "${EP_WORK}" --comfy-url "${COMFY_URL}" \
        --gpu-index 0 --sample-shots 2 --vram-wait-timeout 90
    echo "  [PASS] S4 h3_regen exit 0（guard 拒绝是 graceful-degrade 非 crash）"
    assert_grep "S4 guard 拒绝日志" "批开始 guard 拒绝（reason=" "${S4_LOG}"
    assert_grep "S4 warnings 记 vram_insufficient" "vram_insufficient" "${EP_WORK}/route_cache/warnings.json"
    # 冻结红线第 3 点：cache 保留（二跑可续）——副本 sha vs S3 后 + 正本零触碰
    RT_NOW_WORK="$(sha256sum "${RT_WORK}" | cut -d' ' -f1)"
    if [[ "${RT_NOW_WORK}" == "$(cat "${WORK}/rt_work_sha_s2")" ]]; then
        echo "  [PASS] S4 后副本 sidecar sha256 等值（cache 保留，二跑可续）"
    else
        echo "  [FAIL] S4 后副本 sha256 漂移：${RT_NOW_WORK} != $(cat "${WORK}/rt_work_sha_s2")"
        exit 1
    fi
    assert_verdict_freeze "S4 后"
    assert_freeze_sha "S4 后"
    echo "[smoke] SCENARIO 4: PASS"
else
    echo "  [SKIP] GPU0 free=${GPU0_FREE_NOW} ≥ ${VRAM_GATE_MIB}（本机预期 3060Ti ~4.9GB —— 环境态意外，guard 拒绝位不成立；非功能失败）"
    echo "[smoke] SCENARIO 4: PASS-with-note（GPU0 余量异常走文档化降级分支）"
fi

# 收尾冻结红线（第 3 点，无条件——S3/S4 降级分支也要证明正本零触碰）
assert_freeze_sha "全场景收尾"
echo ""
ALL_PASS=1
echo "ALL_SCENARIOS_PASS"
exit 0
