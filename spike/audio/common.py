"""Phase 10 风险验证 spike 脚本的共享助手。

⚠️ 这是 THROWAWAY Phase 10 spike 代码 —— 不是 pipeline 代码。
不要在 run_pipeline.py 任何 step_* 函数里 import 本模块；
不要把它接到 analysis/* 任何客户端。本模块只服务 Phase 10 的 4 个
一次性 spike 脚本（run_ser_sensevoice.py / run_mir_head_to_head.py /
run_whisperx_align.py / run_diarize_pyannote.py），以及 aggregate_report.py。
所有 spike 输出最终汇总到 .planning/research/audio-spike-report.md。

锁定约束（VALIDATION.md "Spike Reproducibility Invariants"）：
  - 分层抽样固定 n=30, seed=10 —— 4 个 spike 必须跑在同 30 段上，
    否则 MERT-vs-PANNs 头对头可比性失效（Pitfall 9）。
  - 所有 device="cpu"（CONTEXT.md user decision，GPU currently DOWN）。

Pitfall 6（HF_TOKEN 泄露）由 _safe_error 兜底：所有错误信息先过 redact 再 print。
"""
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# ep01 固定 fixture 路径
# ============================================================================
# 注意：目录名含全角括号 （）与中文冒号 ：（Pitfall 8）。用普通 Python 字符串字面量，
# pathlib.Path 自动 UTF-8 处理；切勿 subprocess.run(["ls", path]) 走 shell。
EP01_DIR = Path(
    "/data/workspace/kais-shot-timeline/output/"
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)
# stems layout: stems/htdemucs/<ep01-stem>/{vocals,drums,bass,other}.wav
EP01_STEM_DIR = EP01_DIR / "stems" / "htdemucs" / EP01_DIR.stem
EP01_VOCALS = EP01_STEM_DIR / "vocals.wav"
EP01_DRUMS = EP01_STEM_DIR / "drums.wav"
EP01_BASS = EP01_STEM_DIR / "bass.wav"
EP01_OTHER = EP01_STEM_DIR / "other.wav"

EP01_SHOTS = EP01_DIR / "shots.json"
EP01_TRANSCRIPT = EP01_DIR / "transcript.json"
EP01_AUDIO_ANALYSIS = EP01_DIR / "audio_analysis.json"

# ============================================================================
# 结果输出目录
# ============================================================================
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# SenseVoice 标签集合（rich_transcription_postprocess 之前的 raw 文本里的 tag）
# ============================================================================
# Source: SenseVoice README — 7 emotions + 8 audio events + 5 spoken languages.
EMOTIONS = {
    "HAPPY", "SAD", "ANGRY", "NEUTRAL",
    "FEARFUL", "DISGUSTED", "SURPRISED",
}
EVENTS = {
    "BGM", "Speech", "Applause", "Laughter",
    "Cry", "Sneeze", "Breath", "Cough",
}
LANGUAGES = {"zh", "en", "yue", "ja", "ko"}

# 所有 raw SenseVoice tag 形如 <|zh|><|HAPPY|><|Speech|><|woitn|>实际文本
TAG_RE = re.compile(r"<\|([A-Z_a-z]+)\|>")

# ============================================================================
# 安全：错误信息 redact（T-10-01 mitigation — extends call_shot_analysis.py:122）
# ============================================================================
# Pitfall 6: HF_TOKEN 可能被 pyannote / WhisperX 异常字符串带出 → 写进 results JSON
# → commit → 泄露。这里扩展 call_shot_analysis.py:122 的 _safe_error，加上：
#   hf_<token> / token=<val> / Bearer <val> / basic-auth URL。
# 用在所有 print/write 之前。
_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{20,}")
_TOKEN_KV_RE = re.compile(r"(?i)token=[A-Za-z0-9_\-\.]+")
_BEARER_RE = re.compile(r"(?i)Bearer\s+[A-Za-z0-9_\-\.]+")
_URL_USERINFO_RE = re.compile(r"(https?://)([^@/]+)@")


def _safe_error(msg: str) -> str:
    """Redact HF token / token= / Bearer / URL userinfo out of error strings.

    T-10-01 mitigation — extends analysis/call_shot_analysis.py:122 regex
    with hf_/token=/Bearer patterns per Pitfall 6 (HF_TOKEN leakage via
    pyannote / WhisperX exception sidecar strings).

    Args:
        msg: 原始错误/警告字符串。

    Returns:
        所有疑似凭据子串都被替换为 ``[REDACTED]`` 的字符串。无匹配则 no-op。
    """
    out = _HF_TOKEN_RE.sub("[REDACTED]", msg)
    out = _TOKEN_KV_RE.sub("token=[REDACTED]", out)
    # 整段 Bearer xyz 替换为 [REDACTED]，连前缀词 "Bearer " 一起抹掉
    # （plan verify 要求 'Bearer' literal 不残留）。
    out = _BEARER_RE.sub("[REDACTED]", out)
    out = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", out)
    return out


def git_sha() -> str:
    """当前 HEAD 的短 git sha —— 失败时短路到 'unknown'。

    T-10-05 accept: subprocess 只在我们自己的仓库 HEAD 上跑系统 git，
    没有不可信输入；check_output 失败（detached / shallow / 无 git）
    时返回 'unknown' 而非 raise，spike 不应被 git 状态阻塞。
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception as e:  # noqa: BLE001  spike 容错
        print(f"[common] git_sha unavailable: {_safe_error(str(e))}")
        return "unknown"


# ============================================================================
# 分层抽样（Pitfall 9 head-to-head integrity）
# ============================================================================
def stratified_sample(segments, n: int = 30, seed: int = 10):
    """固定 seed 的分层抽样：跨 short / medium / long / dense 四个桶各取 ceil(n/4)。

    Pitfall 9: MERT-vs-PANNs / SenseVoice-vs-... 必须在**完全相同**的
    30 段上跑，比较才有效。本函数锁定 seed=10、n=30，4 个 spike 都用
    同一返回值 → head-to-head integrity。

    Args:
        segments: list[dict]，每个 dict 至少含 ``start``、``end``、可选 ``text``
            （transcript.json 的 segments[] 满足此约定）。start/end 单位秒。
        n: 总样本数（默认 30，VALIDATION.md invariant）。
        seed: random seed（默认 10，VALIDATION.md invariant —— 不要改成 42）。

    Returns:
        list[tuple[int, dict]]：``(原始 index, segment_dict)`` 对，长度恰好 n
        （前提是 ``segments`` 至少 n 个；否则返回 ``min(n, len(unique))``）。
        ``dense`` 桶与 short/medium/long 三桶按定义会重叠（同一段可同时满足
        ``>10 chars/sec`` 与某个时长桶），所以本函数 dedupe by index：同一段
        只在结果里出现一次。同一 (segments, n, seed) 输入 → 同一输出（确定性）。

    Implementation note (Rule 1 fix vs. plan body):
        原 plan 写的是 ``per_bucket = max(1, n // 4)`` —— 对 n=30 给 7，4 桶最多
        合计 28 < 30，永远凑不到 n。改成 ceil(n/4) 让总候选数 ≥ n，再 dedupe +
        backfill 保证精确返回 n。语义不变（仍然按桶分层），只是数学上能真的凑到 n。
    """
    import random  # 延迟导入：仅本函数用到，避免顶层 import 改动 spike 全局
    rng = random.Random(seed)
    buckets = {"short": [], "medium": [], "long": [], "dense": []}
    for i, s in enumerate(segments):
        start = s.get("start", 0.0)
        end = s.get("end", 0.0)
        dur = end - start
        if dur < 2.0:
            buckets["short"].append((i, s))
        elif dur > 5.0:
            buckets["long"].append((i, s))
        else:
            buckets["medium"].append((i, s))
        # dense-speech：>10 字/秒（中文按字符数近似）
        text = s.get("text", "") or ""
        if dur > 0 and len(text) / dur > 10:
            buckets["dense"].append((i, s))
    # ceil(n/4) per bucket — 4 桶合计 ≥ n，下游 dedupe 后再 [:n] 截断到精确 n。
    per_bucket = max(1, (n + 3) // 4)
    seen = set()
    sample = []
    for b in buckets.values():
        rng.shuffle(b)
        taken = 0
        for idx, seg in b:
            if taken >= per_bucket:
                break
            if idx in seen:
                continue
            sample.append((idx, seg))
            seen.add(idx)
            taken += 1
    # Backfill：dense 桶与时长桶重叠，可能出现 per_bucket 还没填满该桶就耗尽
    # unique 的情况。从全部桶剩余未取段里按当前 rng-determined 顺序补齐。
    if len(sample) < n:
        for b in buckets.values():
            for idx, seg in b:
                if len(sample) >= n:
                    break
                if idx in seen:
                    continue
                sample.append((idx, seg))
                seen.add(idx)
    return sample[:n]


# ============================================================================
# SenseVoice tag 解析（Pitfall 2 prevention）
# ============================================================================
def parse_sensevoice_tags(raw_text: str) -> dict:
    """解析 raw SenseVoice 输出（rich_transcription_postprocess 之前）。

    Pitfall 2: SenseVoice 的 ``rich_transcription_postprocess`` 会把
    ``<|HAPPY|>``-style tag 全部 strip 掉，返回干净文本 —— SER spike 必须在
    post-process **之前** 解析 tag，否则所有 shot emotion 都会落到 NEUTRAL。

    Args:
        raw_text: ``model.generate(...)[0]["text"]`` 的原始返回，形如
            ``"<|zh|><|HAPPY|><|Speech|><|woitn|>他有一百种方法"``。

    Returns:
        ``{"language": str|None, "emotion": str, "events": list[str],
           "clean_text": str}``。
        - language: 匹配 LANGUAGES 集合则返回该字符串，否则 None。
        - emotion: 匹配 EMOTIONS 集合则返回该字符串，否则 "emo_unk"
          （SenseVoice 的 ``ban_emo_unk=False`` 让 ``<|emo_unk|>`` 显式出现，
          保留 unknown 计数 — 评估 SER 精度时区分 "无预测" 与 "预测错"）。
        - events: 所有匹配 EVENTS 的 tag 列表（可能为空）。
        - clean_text: 所有 tag 被 strip 后的剩余文本。
    """
    tags = TAG_RE.findall(raw_text or "")
    return {
        "language": next((t for t in tags if t in LANGUAGES), None),
        "emotion": next((t for t in tags if t in EMOTIONS), "emo_unk"),
        "events": [t for t in tags if t in EVENTS],
        "clean_text": TAG_RE.sub("", raw_text or "").strip(),
    }


# ============================================================================
# 结果写入（统一 stamp + Pitfall 6 redact）
# ============================================================================
def write_result(model: str, fixture: str, payload: dict, device: str = "cpu") -> Path:
    """写一份 spike 结果 JSON 到 ``spike/audio/results/<model>_<fixture>.json``。

    顶层 stamp 5 个字段（防 spike 脚本忘写）：
      - ``model``: 模型名（如 ``"ser_sensevoice"``）
      - ``fixture``: fixture 名（如 ``"ep01"``）
      - ``git_sha``: 当前 HEAD 短 sha（aggregate_report.py 用它做 staleness check）
      - ``timestamp_utc``: ISO8601 UTC 时间戳
      - ``device``: 默认 ``"cpu"``（CONTEXT.md CPU 锁 —— SER/MIR/diarize 都用默认）；
        WhisperX spike (Plan 10-05) 走 device="cuda:0" GPU 路径时显式传入。

    Args:
        model: 模型/脚本名，作为文件名前缀。
        fixture: fixture 名（通常 ``"ep01"``）。
        payload: 结果 dict（per_sample / sample_size / methodology / caveat 等）。
            本函数会就地补 stamp 字段。
        device: 设备标签，写入 ``payload["device"]``。默认 ``"cpu"`` 保持
            与 SER/MIR 等其它 Phase 10 spike 完全一致（向后兼容）。
            Plan 10-05 WhisperX full run 在 GPU 可用时显式传 ``"cuda:0"``，
            使落盘 JSON 的 device 字段如实反映 full-run 设备（device_directive
            + environment_facts 要求 audit trail 诚实）。

    Returns:
        写入的 Path。
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload["model"] = model
    payload["fixture"] = fixture
    payload["git_sha"] = git_sha()
    payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    payload["device"] = device
    out = RESULTS_DIR / f"{model}_{fixture}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    # 兜底：commit 前如果有残留 HF token，redact 一次再落盘。
    out.write_text(_safe_error(text), encoding="utf-8")
    print(f"[{model}] wrote {out} ({len(text)} bytes)")
    return out
