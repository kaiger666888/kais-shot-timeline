#!/usr/bin/env python3
"""逐镜头音频语义深化路由调用（audio-analysis route）→ audio_semantic.json

本模块是 shot-timeline 的第三个网络依赖（sibling of analysis/call_shot_analysis.py
与 analysis/call_reid.py）：通过 httpx sync client 调用 kais-aigc-platform 的
`POST /api/production/audio-analysis` 路由（分支 feat/audio-analysis-route，
Phase 10 ROUTE-01 stub），把每镜的音频语义三模态（对话 / 音效 / 复现 prompt）
归一化成 audio_semantic.json 的 shots[] 结构（schema 见
spec/schemas/audio_semantic.schema.json，Phase 11 LOCKED）。

路由 REQUEST 契约（直接从 feat/audio-analysis-route:src/routes/production/
audio-analysis/index.ts zod bodySchema 读取，Phase 10 10-02-SUMMARY.md:156-186）：
    {
      "video":         "<host abs path>",            # REQUIRED；路由自行 docker cp
      "shots":         "<host abs path>/shots.json",  # REQUIRED
      "shot_id_range": [N, N],   # OPTIONAL；Phase 12 恒传 [N,N] 做 per-shot 隔离
      "stems_dir":     "<abs path>/stems/htdemucs/<video-stem>/",
                                                   # REQUIRED；SER/MIR 输入（vocals/drum/...）
      "models":        {                             # OPTIONAL default pinned in config
        "ser": "iic/SenseVoiceSmall",                #   SenseVoice 情绪 + 事件
        "asr": "large-v3",                           #   Whisper 转录（WhisperX 词级 align）
        "mir": "m-a-p/MERT-v1-95M"                   #   MERT MIR embedding（乐器识别 MUS-04 DEFERRED）
      },
      "language":      "zh"                          # OPTIONAL；对白语言代码
    }

路由 RESPONSE envelope（@/lib/responseFormat.ts:success —— 与 shot-analysis byte-identical）：
    {"code": 200,
     "data": {"shots":[<per-shot 3-modality payload>],
              "count": N,
              "errors": [...],
              "stub_mode": <bool>,
              "message": "..."},
     "message": "Audio analysis complete" | "Audio analysis stub"}
per-shot 调用（shot_id_range=[N,N]）时 data.shots 恰好 1 个元素，取 [0]。

stub_mode 语义（Phase 10 ROUTE-01 stub）：`stub_mode:true` = ML 未上线，路由
返回 data.shots=[]（空 array），客户端视为 "0 shots 有数据 → graceful-degrade"。
这是 Phase 12 SC#4 的集成目标 —— 在路由 ML 上线前就证明 envelope 解析 + cache +
warnings 合并工作正常（mirror v1.1 Phase 7 CAST deferred 模式）。

路由侧 900s 硬超时（execFileSync(timeout=900_000)）—— 客户端 --route-timeout
默认 960s 故意超出 60s，让路由先自杀完毕、客户端拿到确定的 500 走 graceful-degrade
（Phase 6 Pitfall 1 analog）。

映射（CONTEXT D-XX LOCKED + Phase 11 schema $comment LOCKED）：
    schema_version     ← lazy-import from scripts/export_asset.py:SCHEMA_VERSION
                         （CONTRACT-03 单一真源，绝不硬编码字面量 "1.2"）
    word_level_experimental ← bool（任一 shot.dialogue.words[] 非空即 true）
    shots[].dialogue   ← 路由 SER+ASR 输出（text/spk_id/emotion/emotion_confidence/
                         events/words 各自独立投影，isinstance 守卫 CR-02）
    shots[].sfx        ← 路由 SenseVoice 非语音 events（events[]/description）
    shots[].reproduction ← producer-composed by audio/gen_audio_prompts.py
                          ：compose_reproduction (Phase 15 owns；Phase 12 transparent
                          passthrough RETIRED)

phase-10-informed field shape rules（PROJECT.md + Phase 11 schema $comment）：
    emotion       : ["string","null"]  —— SenseVoice self_consistency=100% 是
                       label-stability 代理，NOT 校准精度；闭枚举会越权声称校准。
                       与 emotion_confidence:0..1 配对。
    words[]       : EXPERIMENTAL —— WhisperX wav2vec2 align 产出。顶层
                       word_level_experimental=true 当且仅当任一 words 非空。
    「乐器」字段  : OMITTED —— MUS-04 deferred v1.3（MERT 无 classifier head；
                       PANNs zenodo-blocked）。全文用中文「乐器」/ "MIR label"
                       指代，绝不出现英文 M-I 开头那个字面（Phase 11 schema
                       $comment lock；case-insensitive 全文 grep 必须空）。

输出：
  1. audio_semantic.json —— {schema_version, word_level_experimental, shots: [...]}，
     写前用 Draft202012Validator(audio_semantic.schema.json) 自校验（fails loud 惯例）。
  2. route_cache/audio_analysis/shot_XXX.json —— 每镜路由响应（含 _cache_key 三元组
     video_content_hash/route_name/route_version；shot_id 隐含在文件名 → 4-tuple per PIPE-02），
     不匹配即视为 miss。
  3. route_cache/warnings.json —— {"warnings": [...]} sidecar，**READ-merge-write**
     （非破坏性合并，mirror call_reid.py:443-449）：先读 step_semantic / step_reid
     可能写入的现有 warnings，APPEND 本步 [audio] warnings，再写回。STEP_TAG="[audio]"
     self-dedup（剥掉本步上一轮写的 warnings 防 self-accumulate）。

graceful-degrade（CONTRACT-05 byte-identical-absent）：路由不可达（--offline /
preflight ConnectError / per-shot 失败）AND 零 shot 有数据 → audio_semantic.json
NOT 写（byte-identical v1.1 asset，schema.json 不在 output 出现），warnings sidecar
记失败原因，asset 仍导出（audio_semantic 缺席）。preflight 只跑一次，失败即短路
（Pitfall 7：无 per-shot retry storm）。offline + cache miss 不静默（Pitfall 4：
显式记 warning，让操作员看见输出被降级）。

用法（被 run_pipeline.py:step_audio_semantic 以 subprocess 调用 —— Phase 14 wires）：
  python3 analysis/call_audio_analysis.py \\
      --video /abs/path/to/video.mp4 \\
      --shots /abs/path/to/shots.json \\
      --work-dir output/<video-stem>/ \\
      --output output/<video-stem>/audio_semantic.json \\
      --stems-dir output/<video-stem>/stems/htdemucs/<video-stem>/ \\
      [--route-url http://127.0.0.1:8000/api/production/audio-analysis] \\
      [--route-timeout 960] \\
      [--models '{"ser":"iic/SenseVoiceSmall","asr":"large-v3","mir":"m-a-p/MERT-v1-95M"}'] \\
      [--language zh] \\
      [--offline] \\
      [--force]
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


# ─── 模块级常量 ─────────────────────────────────────────────────────────────
# cache key 组成部分。ROUTE_VERSION 是 cache-invalidation 旋钮 —— 路由逻辑变了
# 就 bump 此串 → 全部 cache miss（Pitfall 5：避免"改了代码但行为不变"）。
ROUTE_NAME = "audio_analysis"
ROUTE_VERSION = "phase-12-stub-v1"

# 路由 path（CONTEXT lock + 10-02-SUMMARY:113-117 lock，硬编码 —— 不可由 --route-url
# 自定义）。IN-01：旧实现把此串散落在 call_route.post / preflight.rsplit / preflight.get
# 三处，改 path 需改三行无编译期保证。抽成单一真源。
# ROUTE_PATH mount: /api/production/audio-analysis (NO /v1/) —— differs from shot-analysis
# sibling 的 /api/v1/production/shot-analysis per 10-02-SUMMARY:113-117 mount-path flag；
# do NOT add /v1/ —— feat/audio-analysis-route 分支明确 mount 在 /api/production 之下。
ROUTE_PATH = "/api/production/audio-analysis"

# audio_semantic.schema.json 绝对路径（写前 Draft202012Validator 自校验用 + 命中
# cache 时 poisoned-invalidation 用）。
# analysis/call_audio_analysis.py → repo root/spec/schemas/audio_semantic.schema.json
AUDIO_SEMANTIC_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "audio_semantic.schema.json"


def video_content_hash(video_path: str) -> str:
    """sha256(first_1MB + last_1MB + str(filesize)) —— multi-GB 视频也快。

    全文件 sha256 在 multi-GB episode 视频上需数十秒；首尾各 1MB + 文件大小
    是 git-annex / content-defined chunking 的成熟简化，毫秒级、确定性、
    collision-resistant 足够做 cache invalidation（CONTEXT CINEMA-04 锁定）。

    返回 hexdigest()[:16]（16 字符 hex —— cache key 用，非安全 hash）。
    """
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))                    # head 1MB
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)            # 跳到尾部前 1MB
            h.update(f.read(1024 * 1024))                # tail 1MB
    h.update(str(size).encode())                         # 文件大小参与 hash
    return h.hexdigest()[:16]


def _safe_error(msg: str) -> str:
    """抹掉 URL 中的 user:pass@ userinfo（WR-05 defense-in-depth）。

    httpx 异常的 str() 通常含请求 URL；若操作员把 basic-auth 嵌进 --route-url
    （http://user:pass@host），warning 串会带凭据 → 流进 route_cache/warnings.json
    → scripts/export_asset.py → asset.json#generator.warnings 随资产外发。schema
    （asset.schema.json:59）显式禁止 warnings 含 auth token/body payloads。现代 httpx
    已在 URL.__str__ 里 mask 成 user:***@，但 exporter 接受任意 list[str] 不做 redaction
    —— 这里兜底，防 httpx 回归 / 自定义 transport / 路由 message 回显 URL 暴露凭据。
    无 URL 时是 no-op（正则不匹配）。T-12-04 mitigation：所有错误串均过此函数。
    """
    return re.sub(r"(https?://)([^@/]+@)", r"\1***@", msg)


def normalize_audio_semantic(route_shot: dict | None, shot_meta: dict) -> dict:
    """路由单镜响应 → audio_semantic.schema.json#shots[] 投影（Phase 11 LOCKED）。

    显式投影：路由多塞的字段（embedding / model metadata / 调试 stub_mode 等）一律
    丢弃 —— schema additionalProperties:false 全程生效。Phase-10-informed field shapes：
    emotion 是 nullable string（NOT enum）+ emotion_confidence nullable number[0,1]；
    words[] EXPERIMENTAL（顶层 word_level_experimental 须置 true）；乐器字段 OMITTED
    全文（MUS-04 deferred v1.3）。

    Args:
        route_shot: 单镜路由响应 data.shots[0]（含 dialogue/sfx/reproduction 三个子
            对象，或 None）。None / 非 dict 一律降级为 skeleton。
        shot_meta: shots.json 中该镜的权威元数据 {id, start_sec, end_sec, duration}。
            producer 拥有时间对齐 —— 永远以 shot_meta 为准，NOT 路由可能塞进的时间戳。

    Returns:
        dict 符合 audio_semantic.schema.json#shots[]。最简形态（无 modality 投影）
        {"shot_id", "start_sec", "end_sec", "duration"}（schema-valid skeleton ——
        shot_id 是唯一 required 字段，其余 optional）。每个 modality 独立 try/except，
        畸形输入降级为该 modality 缺席（不 crash pipeline，mirror call_reid.py:208-210）。

    生产方契约：
        - timing 永远来自 shot_meta（producer-owns-timing invariant）。
        - modality 缺席即整子对象 OMIT（不 emit 空 dict —— schema 任一子对象
          additionalProperties:false，空 dict 形式上合法但语义混乱）。
        - 乐器字段：本函数永不 emit 任何乐器相关字段（MUS-04 deferred v1.3；
          Phase 11 schema $comment lock）。
    """
    # 生产方骨架：timing + shot_id 来自 shot_meta（权威源）。即使 route_shot=None 也
    # 能返回 schema-valid skeleton（graceful-degrade 不破坏 schema）。
    # WR-03：schema 只 required shot_id；start_sec/end_sec/duration 全 optional
    # （audio_semantic.schema.json:27-48）。手改 / 部分 shots.json（如 {"id":1}）
    # 缺 timing 字段时不应让 KeyError 崩 pipeline —— 用 .get() + isinstance 守卫，
    # 缺席或非 number 一律 OMIT（schema-valid skeleton 允许只含 shot_id）。
    skeleton: dict = {"shot_id": shot_meta["id"]}
    for _k in ("start_sec", "end_sec", "duration"):
        _v = shot_meta.get(_k)
        if isinstance(_v, (int, float)):
            skeleton[_k] = _v
    # CR-02：route_shot 非 dict（路由 bug 回 list/string，或 None graceful-degrade）
    # → 直接返回 skeleton。isinstance 守卫统一 None 与 truthy 非 dict。
    if not isinstance(route_shot, dict):
        return skeleton

    out = dict(skeleton)

    # ─── dialogue 投影（ASR + SER + WhisperX word-level） ─────────────────
    # 单个 modality 独立 try/except：畸形输入降级为该 modality 缺席，不波及其他 modality。
    try:
        raw_dialogue = route_shot.get("dialogue")
        if isinstance(raw_dialogue, dict):
            dialogue: dict = {}
            # text：segment-level 转录（string）
            text = raw_dialogue.get("text")
            if isinstance(text, str) and text:
                dialogue["text"] = text
            # spk_id：可选；必须匹配 ^spk_[0-9]{3}$ 或 null（schema 联合类型 + pattern）
            if "spk_id" in raw_dialogue:
                spk = raw_dialogue["spk_id"]
                if spk is None:
                    dialogue["spk_id"] = None
                elif isinstance(spk, str) and re.match(r"^spk_[0-9]{3}$", spk):
                    dialogue["spk_id"] = spk
                # 不符合 pattern 的 spk_id 一律丢弃（防 schema reject）。
            # emotion：nullable string（NOT enum —— Phase 10 spike 锁定）
            if "emotion" in raw_dialogue:
                emo = raw_dialogue["emotion"]
                if emo is None or isinstance(emo, str):
                    dialogue["emotion"] = emo
                # 非 str/null 丢弃。
            # emotion_confidence：nullable number [0,1]，越界 clamp（WR-03 analog）
            if "emotion_confidence" in raw_dialogue:
                ec = raw_dialogue["emotion_confidence"]
                if ec is None:
                    dialogue["emotion_confidence"] = None
                elif isinstance(ec, (int, float)):
                    dialogue["emotion_confidence"] = max(0.0, min(1.0, float(ec)))
            # events：SenseVoice 8-event list[str]（Speech/BGM/Applause/...）
            raw_events = raw_dialogue.get("events")
            if isinstance(raw_events, list):
                events = [e for e in raw_events if isinstance(e, str)]
                if events:
                    dialogue["events"] = events
            # words：EXPERIMENTAL —— WhisperX word-level align。每 word 独立验证，
            # 畸形 word 丢弃（schema required start/end/text，score optional [0,1]）。
            raw_words = raw_dialogue.get("words")
            if isinstance(raw_words, list):
                words = []
                for w in raw_words:
                    if not isinstance(w, dict):
                        continue
                    try:
                        start = w.get("start")
                        end = w.get("end")
                        wtext = w.get("text")
                        # 必需三字段全 number/number/string(non-empty)。
                        if (isinstance(start, (int, float))
                                and isinstance(end, (int, float))
                                and isinstance(wtext, str) and wtext):
                            word = {"start": float(start),
                                    "end": float(end),
                                    "text": wtext}
                            score = w.get("score")
                            if isinstance(score, (int, float)):
                                word["score"] = max(0.0, min(1.0, float(score)))
                            words.append(word)
                    except (TypeError, ValueError, KeyError, IndexError):
                        continue   # 单 word 畸形不影响其他 word
                if words:
                    dialogue["words"] = words
            # 任何子字段成功投影即 emit dialogue 子对象。
            if dialogue:
                out["dialogue"] = dialogue
    except (KeyError, TypeError, ValueError, IndexError):
        pass   # dialogue 整体畸形 → 缺席（skeleton 仍合法）

    # ─── sfx 投影（SenseVoice 非语音 events + NL description） ─────────────
    # 注：sfx.events 是 non-speech 子集（Speech 不在此 —— 它在 dialogue.events）。
    # Phase 12 仅承载 SenseVoice 8-event 子集；PANNs 527-class deferred（schema $comment）。
    try:
        raw_sfx = route_shot.get("sfx")
        if isinstance(raw_sfx, dict):
            sfx: dict = {}
            raw_events = raw_sfx.get("events")
            if isinstance(raw_events, list):
                events = [e for e in raw_events if isinstance(e, str)]
                if events:
                    sfx["events"] = events
            desc = raw_sfx.get("description")
            if isinstance(desc, str) and desc:
                sfx["description"] = desc
            if sfx:
                out["sfx"] = sfx
    except (KeyError, TypeError, ValueError, IndexError):
        pass   # sfx 畸形 → 缺席

    # ─── reproduction: Phase 15 producer-composed (NOT projected from route) ──
    # Phase 12 transparently passed route-returned reproduction; Phase 15 (locked
    # decision #6) retires that pattern and owns producer composition. Composer
    # is invoked post-normalize in main() per-shot loop (see line ~730). Route-
    # returned reproduction (if any) is silently dropped —— producer-composed
    # version wins. No code path here emits a reproduction object.
    try:
        # Defensive: drop any route-returned reproduction to keep semantics clean.
        # (normalize never reads it, but if route_shot accidentally carries one,
        # we explicitly do NOT forward it.)
        if isinstance(route_shot, dict) and "reproduction" in route_shot:
            pass   # intentionally not projected
    except (KeyError, TypeError):
        pass

    # 乐器字段 OMITTED —— MUS-04 deferred v1.3（MERT 无 classifier head；
    # Phase 11 schema $comment lock）。不要在此处或文件任何位置 emit 乐器字段。
    return out


def call_route(client, body: dict) -> tuple[dict | None, str | None]:
    """单镜路由 POST 调用（CINEMA-01 route call analog + CINEMA-03 degrade）。

    与 call_shot_analysis.py:165-217 同构：httpx POST → raise_for_status → JSON
    解码守卫 → envelope isinstance 守卫 → code!=200 守卫 → data.shots[0] 取值。
    单镜调用（shot_id_range=[N,N]）恒取 data.shots[0]。

    Args:
        client: httpx.Client（base_url 已含路由 host root）。
        body: POST body（shot_id_range=[N,N] per-shot 隔离；含 stems_dir / models /
            language 等 Phase 10 ROUTE-01 contract 字段）。

    Returns:
        (route_shot_dict, None) 成功 —— 取 data.shots[0]（per-shot 调用只 1 个）。
            stub_mode:true 且 data.shots=[] 时也返回 (None, msg) —— 这是 Phase 10
            ROUTE-01 stub 的"ML 未上线"信号，驱动 graceful-degrade（不是错误）。
        (None, error_msg) 任意失败 —— httpx.HTTPError 根异常覆盖
            ConnectError/TimeoutException/HTTPStatusError/NetworkError（Pattern 2），
            以及 envelope 畸形 / 字段缺失等非 httpx 异常（CR-02 broaden except）。
        不 retry —— per-shot 失败非致命（CONTEXT D-XX graceful-degrade）。
    """
    import httpx  # lazy import —— 沿用 audio/transcribe.py 的 optional-dep 惯例
    try:
        resp = client.post(ROUTE_PATH, json=body)
        resp.raise_for_status()                          # 4xx/5xx → HTTPStatusError
        # CR-02：非 JSON 200 body（反代 HTML 错误页 / 代理 502 伪 200）——
        # resp.json() raise JSONDecodeError(ValueError)。单独包一层 except ValueError
        # 走 degrade（graceful-degrade 不可破）。
        try:
            payload = resp.json()
        except ValueError as e:
            # WR-05：body 可能是反代 HTML 错误页（回显 URL），_safe_error 兜底抹凭据。
            return None, _safe_error(
                f"route returned non-JSON body: {type(e).__name__}: {e}")
        # CR-02：envelope 非 dict（路由 bug 回 bare list/string/number）→ degrade。
        if not isinstance(payload, dict):
            return None, _safe_error(
                f"route envelope not a dict: {type(payload).__name__}")
        if payload.get("code") != 200:
            # WR-05：route message 可能回显 URL，_safe_error 兜底。
            return None, _safe_error(
                f"route code={payload.get('code')}: {payload.get('message')}")
        # CR-02：data 字段防御性 isinstance（data 若是非 dict truthy 如 string，
        # `(data or {}).get` 仍会崩）。
        data = payload.get("data")
        shots = data.get("shots") if isinstance(data, dict) else None
        shots = shots or []
        if not shots:
            # Phase 10 stub_mode:true 时 data.shots=[] —— 这是合法的 "ML 未上线"
            # 信号，不是错误。客户端将其转为 graceful-degrade（route_shot=None →
            # skeleton-only shot，驱动 byte-identical-absent 当所有镜都 degrade）。
            stub_flag = ""
            if isinstance(data, dict) and data.get("stub_mode"):
                stub_flag = " (stub_mode:true — ML not loaded)"
            return None, (f"route returned 0 shots for "
                          f"shot_id_range={body.get('shot_id_range')}{stub_flag}")
        return shots[0], None                            # per-shot 调用恒取 [0]
    except (httpx.HTTPError, ValueError, AttributeError,
            TypeError, KeyError) as e:
        # CR-02：broaden except —— httpx.HTTPError 覆盖 ConnectError/Timeout/
        # HTTPStatusError/NetworkError；其余覆盖 envelope 畸形 / 字段缺失等非
        # httpx 异常（defense-in-depth，防任何漏网访问路径让 step_audio_semantic 崩
        # → run_pipeline abort）。一律走 degrade：warning 记异常类。
        # WR-05：str(httpx 异常) 含请求 URL —— 可能带 user:pass@，_safe_error 抹掉。
        # T-12-04：所有错误串均过 _safe_error，防凭据流进 warnings sidecar。
        return None, _safe_error(f"{type(e).__name__}: {e}")


def preflight(base_url: str, timeout: float = 5.0) -> tuple[bool, str | None]:
    """步前健康探测（CINEMA-05 analog）—— 只跑一次，失败短路。

    ANY HTTP 响应（哪怕 404/405 —— 路由只 define POST /，GET 探测预期 404/405）
    都算 "up"（Assumption A3：任何 HTTP 响应证明 host:port 可达）。
    仅 httpx.HTTPError（ConnectError 等）→ (False, msg)，驱动 route_down 短路
    剩余 shots（Pitfall 7：无 per-shot retry storm）。

    WR-03 analog：ROUTE_PATH 是单一真源 —— preflight 必须用与 main client 同源
    的 prefix strip。但 audio-analysis mount 是 `/api/production/audio-analysis`
    （NO /api/v1 —— 不同于 shot-analysis 的 `/api/v1/production/...`，10-02-SUMMARY
    mount-path flag）。因此 rsplit 锚点是 `/api/production`（NOT `/api/v1`）。
    """
    import httpx
    # base_url 含 /api/production/audio-analysis path；探测时 rsplit 掉 /api/production
    # 之后的部分取 host root，再拼 ROUTE_PATH。
    # ⚠ 与 call_shot_analysis.py:232 的 rsplit("/api/v1", 1) 不同 —— 这是 audio-analysis
    # mount-path flag（10-02-SUMMARY:113-117）；切勿盲目复制 shot-analysis 的 /api/v1。
    base = base_url.rsplit("/api/production", 1)[0]
    try:
        with httpx.Client(base_url=base,
                          timeout=httpx.Timeout(connect=5.0, read=5.0,
                                                write=5.0, pool=5.0)) as probe:
            probe.get(ROUTE_PATH, timeout=timeout)
        return True, None
    except httpx.HTTPError as e:
        # WR-05：str(httpx 异常) 含请求 URL —— 可能带 user:pass@，_safe_error 抹掉
        # 防凭据流进 warnings sidecar → asset.json#generator.warnings。
        return False, _safe_error(
            f"preflight route unreachable: {type(e).__name__}: {e}")


# ─── 4-tuple cache key 命中校验（mirror call_shot_analysis.py:327-334 + WR-04） ───
def _cache_key_matches(cached: dict, vch: str) -> bool:
    """3-tuple _cache_key 校验（video_content_hash + route_name + route_version）。

    PIPE-02 lock：shot_id 隐含在文件名 shot_{sid:03d}.json 中，因此 _cache_key
    本身只校验三元组。完整 4-tuple = (vch, route_name, route_version, shot_id-from-filename)。

    Args:
        cached: cache 文件 JSON（dict 或损坏后的 {}）。
        vch: 当前视频的 video_content_hash。

    Returns:
        True 当三元组全部匹配 —— cache 命中。False 当任一不匹配（video 变 /
        route_name 异 / ROUTE_VERSION bump）—— stale miss。
    """
    if not isinstance(cached, dict):
        return False
    ck = cached.get("_cache_key", {})
    if not isinstance(ck, dict):
        return False
    return (ck.get("video_content_hash") == vch
            and ck.get("route_name") == ROUTE_NAME
            and ck.get("route_version") == ROUTE_VERSION)


def _cache_key_payload(vch: str) -> dict:
    """写 cache 时附加的 _cache_key 三元组（mirror call_shot_analysis.py:355-359）。"""
    return {
        "video_content_hash": vch,
        "route_name": ROUTE_NAME,
        "route_version": ROUTE_VERSION,
    }


def main():
    """CLI 入口 —— 被 run_pipeline.py:step_audio_semantic 以 subprocess 调用（Phase 14 wires）。

    流程：
      1. 解析 CLI（11 flags，Chinese help per CLAUDE.md）。
      2. 载入 shots_meta + 计算 video_content_hash。
      3. SCHEMA_VERSION lazy-import（CONTRACT-03 单一真源 in scripts/export_asset.py:56）。
      4. 准备 cache_dir / warnings_sidecar / audio_warnings。
      5. --force 处理（显式列表 unlink，NOT glob —— 项目惯例）。
      6. warnings sidecar 读取（READ-merge-write 第 1 阶段：保 [semantic]/[reid]）。
      7. Preflight（非 offline）—— 失败即 route_down 短路。
      8. 长驻 httpx.Client（WR-02：offline 不建）。
      9. per-shot 循环：cache lookup → poisoned-cache invalidation → miss+POST →
         normalize → 收集 shots_out（仅含数据的镜）。
      10. 决策：写 audio_semantic.json（≥1 shot 有数据）OR byte-identical-absent（CONTRACT-05）。
      11. 写前 schema-validate（Draft202012Validator）—— 失败 unlink poisoned cache + sys.exit。
      12. warnings sidecar 写回（STEP_TAG="[audio]" self-dedup + cross-step 保）。
      13. 打印 summary 行。

    Exit codes：0 正常（含 byte-identical-absent graceful-degrade）；非 0 schema 校验失败。
    """
    # ─── (1) argparse CLI（11 flags，mirror call_shot_analysis.py + Phase 12 加项） ───
    ap = argparse.ArgumentParser(
        description="逐镜头音频语义深化路由调用 → audio_semantic.json（第三个网络依赖步骤）")
    ap.add_argument("--video", required=True,
                    help="原始视频绝对路径（含 audio 流）")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径（含 id/start/end/duration）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录 output/<video-stem>/ —— route_cache 写在其下")
    ap.add_argument("--output", required=True,
                    help="audio_semantic.json 输出路径")
    ap.add_argument("--stems-dir", required=True,
                    help="Demucs stems 目录（htdemucs/<video-stem>/，传给路由做 SER/MIR 输入）")
    # Phase 15：audio_analysis.json side input —— reproduction composer 用其 drums
    # ratio + 频谱重心估 tempo/brightness。缺席时 composer 降级（music_gen 仅靠
    # BGM/mood 信号；schema 仍合法）。
    ap.add_argument("--audio-analysis-json", default=None,
                    help="audio_analysis.json 路径（per-shot Demucs 频谱/能量 side input；"
                         "Phase 15 reproduction composer 用其 drums ratio + 频谱重心；"
                         "缺席时 composer 降级为 BGM/mood-only music_gen（schema 仍合法）")
    ap.add_argument("--route-url",
                    default="http://127.0.0.1:8000/api/production/audio-analysis",
                    help="audio-analysis 路由 URL（含 /api/production/audio-analysis path；"
                         "NO /v1/ —— 10-02-SUMMARY mount-path flag）")
    ap.add_argument("--route-timeout", type=float, default=960.0,
                    help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync；"
                         "mirror Phase 6 Pitfall 1）")
    ap.add_argument("--models",
                    default='{"ser":"iic/SenseVoiceSmall","asr":"large-v3","mir":"m-a-p/MERT-v1-95M"}',
                    help="路由侧模型 ID JSON 串（ROUTE-02 producer-side contract slice；"
                         "SenseVoice SER / WhisperX ASR / MERT MIR —— MUS-04 乐器识别 deferred）")
    ap.add_argument("--language", default="zh",
                    help="对白语言代码（传给路由 WhisperX/SenseVoice）")
    ap.add_argument("--offline", action="store_true",
                    help="仅读 route_cache 不联网（cache 命中即用，miss 则降级 —— byte-identical v1.1 asset）")
    ap.add_argument("--force", action="store_true",
                    help="忽略 cache 强制重跑（清 route_cache/audio_analysis/shot_*.json + audio_semantic.json；"
                         "显式列表 NOT glob —— 项目惯例）")
    args = ap.parse_args()

    # 解析 --models JSON（早失败：坏 JSON 直接 sys.exit，不浪费 cache lookup）
    try:
        models_dict = json.loads(args.models)
        if not isinstance(models_dict, dict):
            raise ValueError(f"--models must decode to object, got {type(models_dict).__name__}")
    except (json.JSONDecodeError, ValueError) as e:
        sys.exit(f"--models JSON parse failed: {e}")

    # ─── (2) 载入 shots 元数据 + 计算 video_content_hash ─────────────────
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    if not isinstance(shots_meta, list):
        sys.exit(f"--shots must point to a JSON array, got {type(shots_meta).__name__}")
    vch = video_content_hash(args.video)

    # Phase 15: audio_analysis.json side-input index —— composer 用其 drums
    # ratio 决定是否估 tempo。缺席时 analysis_by_id 为空 dict；composer 收到
    # analysis_shot=None 仍可工作（music_gen 降级为 BGM/mood 信号 only）。
    analysis_by_id: dict = {}
    if args.audio_analysis_json and os.path.exists(args.audio_analysis_json):
        try:
            with open(args.audio_analysis_json, encoding="utf-8") as _f:
                _aan = json.load(_f)
            if isinstance(_aan, dict) and isinstance(_aan.get("shots"), list):
                analysis_by_id = {
                    s["shot_id"]: s for s in _aan["shots"]
                    if isinstance(s, dict) and isinstance(s.get("shot_id"), int)}
        except (OSError, json.JSONDecodeError) as _e:
            print(f"[audio] warning: audio_analysis.json load failed ({_e}); "
                  f"composer degraded to no-side-input mode")

    # ─── (3) SCHEMA_VERSION 单一真源（CONTRACT-03） ─────────────────────
    # scripts/export_asset.py:56 是 SCHEMA_VERSION = "1.2" 的单一真源 —— 本步骤
    # 绝不硬编码字面量 "1.2"。lazy-import 避免 module-load 副作用 + stage-decoupling
    # 违例（scripts/ 不应被 analysis/ 在 import-time 依赖）。fallback 字面量仅当
    # export_asset.py 在运行时不可用（极罕见 —— 仓库损坏 / 部分检出）。
    try:
        # sys.path 补 repo root 让 `from scripts.export_asset import SCHEMA_VERSION` 可达
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        # scripts/ 不是 package（无 __init__.py）—— 用 importlib 按 filesystem 路径加载。
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_export_asset_for_version", repo_root / "scripts" / "export_asset.py")
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)   # type: ignore[arg-type]
            SCHEMA_VERSION = mod.SCHEMA_VERSION
        else:
            raise ImportError("spec_from_file_location returned None")
    except (ImportError, AttributeError, FileNotFoundError, OSError) as e:
        SCHEMA_VERSION = "1.2"   # CONTRACT-03 fallback —— 仅 export_asset.py 不可用时
        print(f"[audio] warning: SCHEMA_VERSION lazy-import failed ({e}); "
              f"using fallback literal '{SCHEMA_VERSION}'")

    # ─── (3b) Phase 15: compose_reproduction lazy-import ────────────────
    # Mirror SCHEMA_VERSION lazy-import pattern（避免 stage-decoupling 违例 ——
    # audio/ 不是 package，用 importlib.util filesystem load）。Fallback
    # _compose_reproduction=None on import failure: composer 缺席 → reproduction
    # 层缺席（schema-valid skeleton per CONTRACT-05 graceful-degrade）。
    _compose_reproduction = None
    try:
        _gap_spec = importlib.util.spec_from_file_location(
            "_gen_audio_prompts_for_compose",
            repo_root / "audio" / "gen_audio_prompts.py")
        if _gap_spec is not None and _gap_spec.loader is not None:
            _gap_mod = importlib.util.module_from_spec(_gap_spec)
            _gap_spec.loader.exec_module(_gap_mod)   # type: ignore[arg-type]
            if hasattr(_gap_mod, "compose_reproduction"):
                _compose_reproduction = _gap_mod.compose_reproduction
            else:
                print("[audio] warning: audio/gen_audio_prompts.py has no "
                      "compose_reproduction attr; reproduction layer will be absent")
        else:
            raise ImportError("spec_from_file_location returned None")
    except (ImportError, AttributeError, FileNotFoundError, OSError, SyntaxError) as _e:
        print(f"[audio] warning: compose_reproduction lazy-import failed ({_e}); "
              f"reproduction layer will be absent (schema-valid skeleton)")

    # ─── (4) cache_dir + warnings_sidecar + 本步 warnings ─────────────
    # cache dir: route_cache/audio_analysis/ —— v1.1 convention（NOT .cache/）。
    # 保一致性：warnings sidecar 在 route_cache/warnings.json 与 call_shot_analysis /
    # call_reid 共用，--force cache-clearing 逻辑也按 route_cache/<ROUTE_NAME>/ 走。
    cache_dir = os.path.join(args.work_dir, "route_cache", ROUTE_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    warnings_sidecar = os.path.join(args.work_dir, "route_cache", "warnings.json")

    # ─── (5) --force 处理（显式列表，NOT glob —— 项目惯例） ────────────
    # 不触 route_cache/warnings.json（其他 step 的 warnings 在那）。
    if args.force:
        for s in shots_meta:
            sid = s.get("id")
            if isinstance(sid, int):
                cf = os.path.join(cache_dir, f"shot_{sid:03d}.json")
                if os.path.exists(cf):
                    try:
                        os.unlink(cf)
                    except OSError:
                        pass
        if os.path.exists(args.output):
            try:
                os.unlink(args.output)
            except OSError:
                pass

    # ─── (6) warnings sidecar 读取（READ 阶段，保 [semantic]/[reid]/etc） ─
    existing_warnings: list[str] = []
    if os.path.exists(warnings_sidecar):
        try:
            with open(warnings_sidecar, encoding="utf-8") as f:
                sidecar = json.load(f)
            if isinstance(sidecar, dict) and isinstance(sidecar.get("warnings"), list):
                existing_warnings = [w for w in sidecar["warnings"] if isinstance(w, str)]
        except (OSError, json.JSONDecodeError):
            existing_warnings = []   # 损坏 sidecar 不阻塞本步

    # 本步新增 warnings（写阶段会 prepend STEP_TAG="[audio]" 并 strip 旧 [audio] tags）
    audio_warnings: list[str] = []

    # ─── (7) Preflight（非 offline）—— 失败即 route_down 短路 ──────────
    route_down = args.offline
    if not args.offline:
        ok, msg = preflight(args.route_url)
        if not ok:
            route_down = True
            audio_warnings.append(f"preflight failed: {msg}")
            print(f"[audio] preflight failed → route_down mode: {msg}")

    # ─── (8) 长驻 httpx.Client（WR-02：offline 不建） ─────────────────
    client = None
    if not args.offline:
        import httpx
        # WR-03 analog：base 只取 host root（rsplit 掉 /api/production 之后部分），
        # post 用 ROUTE_PATH。audio-analysis mount 在 /api/production/audio-analysis
        # （NO /v1/）—— rsplit 锚点必须与 preflight 一致（/api/production）。
        base = args.route_url.rsplit("/api/production", 1)[0]
        client = httpx.Client(
            base_url=base,
            timeout=httpx.Timeout(connect=5.0, read=args.route_timeout,
                                  write=5.0, pool=5.0))

    # ─── schema validator（poisoned-cache + 写前双重用） ──────────────
    from jsonschema import Draft202012Validator
    with open(AUDIO_SEMANTIC_SCHEMA, encoding="utf-8") as f:
        audio_schema = json.load(f)
    validator = Draft202012Validator(audio_schema)

    # ─── (9) per-shot 循环 ────────────────────────────────────────────
    shots_out: list[dict] = []
    words_present = False
    poisoned_cache_files: list[str] = []   # 命中时校验失败 → 累积，结束时统一警告

    try:
        for s in shots_meta:
            # WR-02：守卫 mirror --force 分支（:569-570）—— 非 dict 或 id 非 int
            # 一律 skip + warn（畸形 shots.json 条目不应让 :03d format 抛 TypeError /
            # missing id 抛 KeyError 而崩溃 pipeline）。
            if not isinstance(s, dict) or not isinstance(s.get("id"), int):
                bad = type(s).__name__ if not isinstance(s, dict) else s.get("id")
                audio_warnings.append(
                    f"skip malformed shots.json entry (not dict or id not int): {bad!r}")
                continue
            sid = s["id"]
            cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")

            # (a) cache lookup
            # cache_stale: cache_file 存在但 _cache_key 不匹配（CR-01：必须与"文件
            # 缺失"区分开 —— offline + stale-cache 也要显式记 warning，防 Pitfall 4
            # 静默降级）。
            route_shot = None
            cache_stale = False
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        cached = json.load(f)
                except (OSError, json.JSONDecodeError):
                    cached = {}
                if _cache_key_matches(cached, vch):
                    # (b) POISONED-CACHE INVALIDATION —— 写前 schema 自校验 mirror
                    # call_reid.py:418-427，但这里是 per-shot + on-hit：把 cached 当
                    # 作合法 audio_semantic payload 的一部分校验。如果 schema 收紧
                    # （Phase 11 之后）导致 stale 形态 fail，自动 unlink + miss。
                    normalized_probe = normalize_audio_semantic(cached, s)
                    probe_payload = {
                        "schema_version": SCHEMA_VERSION,
                        "shots": [normalized_probe],
                    }
                    probe_errors = list(validator.iter_errors(probe_payload))
                    if probe_errors:
                        try:
                            os.unlink(cache_file)
                            print(f"[audio] shot {sid}: invalidated poisoned cache "
                                  f"(schema-validate fail on hit: "
                                  f"{probe_errors[0].message[:80]})")
                            poisoned_cache_files.append(cache_file)
                            cache_stale = True   # 视同 stale，触发显式 warning
                        except OSError:
                            pass   # best-effort；不阻塞主流程
                    else:
                        print(f"[audio] shot {sid}: cache hit")
                        route_shot = cached
                else:
                    cache_stale = True

            # (c) cache miss + 非 route_down → 联网 per-shot POST
            if route_shot is None and not route_down:
                body = {
                    "video": os.path.abspath(args.video),
                    "shots": os.path.abspath(args.shots),
                    "shot_id_range": [sid, sid],   # per-shot 隔离（Pitfall 6）
                    "stems_dir": os.path.abspath(args.stems_dir),
                    "models": models_dict,
                    "language": args.language,
                }
                route_shot, err = call_route(client, body)
                if err:
                    audio_warnings.append(f"shot {sid}: {err}")
                    print(f"[audio] shot {sid}: FAIL {err}")
                    route_shot = None   # degrade → skeleton-only（仍加入 shots_out）
                else:
                    # 写 cache（带 _cache_key 三元组；shot_id 在文件名 = 4-tuple per PIPE-02）
                    cache_payload = {**route_shot,
                                     "_cache_key": _cache_key_payload(vch)}
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(cache_payload, f, ensure_ascii=False, indent=2)
                    except OSError as e:
                        audio_warnings.append(f"shot {sid}: cache write failed: {e}")

            # (d) cache miss + route_down —— Pitfall 4：不静默，显式记 warning
            if route_shot is None and route_down:
                if cache_stale:
                    audio_warnings.append(
                        f"shot {sid}: offline/stale-cache (poisoned or _cache_key mismatch) "
                        f"→ absent from audio_semantic")
                else:
                    audio_warnings.append(
                        f"shot {sid}: offline/cache-miss → absent from audio_semantic")

            # (e) normalize → shots_out
            # 关键决策：route_shot=None 时 normalize 返回 skeleton（shot_id + timing），
            # 仍 schema-valid 但 producer 决定：是否把 skeleton 计入 shots_out？
            # CONTRACT-05：byte-identical-absent 仅在零 shot 有数据；如果有 ≥1 shot
            # 有真数据，skeleton 镜也写入（保持 shots[] 覆盖全片 —— mirror spec fixture
            # v1.2/audio_semantic.json:38-55 第二镜只有稀疏 dialogue）。
            # 但 skeleton-only 镜（route_shot=None）若计入会让 word_level_experimental
            # 等标志语义稳定 —— 这里采用：始终写入 normalize 的 shot（含或不含 modality）。
            normalized = normalize_audio_semantic(route_shot, s)
            # Phase 15: producer owns reproduction composition（locked decision #6）。
            # compose_reproduction 是 pure + defense-in-depth（任何异常 → 该 shot 的
            # reproduction 层整体 OMIT，schema-valid skeleton）。pre-write
            # schema validator at line ~800 catches any escape。
            # T-15-04: composer NEVER reads dialogue.words[]（DIA-05 gating）。
            if _compose_reproduction is not None:
                try:
                    analysis_shot = analysis_by_id.get(s.get("id"))
                    normalized["reproduction"] = _compose_reproduction(
                        normalized, analysis_shot=analysis_shot)
                except Exception as _e:
                    audio_warnings.append(
                        f"shot {s.get('id')}: reproduction composer raised "
                        f"{type(_e).__name__}: {_e}")
                    normalized.pop("reproduction", None)
            # 若 lazy-import 失败（_compose_reproduction=None），reproduction 层
            # 缺席 —— schema-valid skeleton（CONTRACT-05 graceful-degrade）。
            # 仅当 route_shot 非 None（实际有数据）才计入 words_present 判定。
            if route_shot is not None:
                dlg = normalized.get("dialogue")
                if isinstance(dlg, dict) and isinstance(dlg.get("words"), list) and dlg["words"]:
                    words_present = True
            shots_out.append(normalized)
    finally:
        # WR-02：client 仅在非 offline 时建 → 条件 close（None 时跳过）。
        if client is not None:
            client.close()

    # WR-01：poisoned_cache_files 累积了"命中时 schema-validate fail → unlink"的
    # cache 文件。route_down 路径已在 per-shot 循环里发 offline/stale-cache warning
    # （:702-704），此处仅补 route-up 路径：refetch 成功后操作员仍需看见 cache 曾
    # 被 schema 收紧而失效（smoke Scenario 3 用 --offline 触不到此分支）。
    if poisoned_cache_files and not route_down:
        audio_warnings.append(
            f"invalidated {len(poisoned_cache_files)} poisoned cache file(s) "
            f"on schema-validate fail on hit (route-up → refetched)")

    # ─── (10) 决策：写 audio_semantic.json OR byte-identical-absent ────
    # CONTRACT-05：route 不可达 / preflight fail / --offline AND 零 shot 有数据 →
    # audio_semantic.json NOT 写（asset.json#data.audio_semantic OPTIONAL → 缺席）。
    # 关键判定："有数据" = route_shot 非 None 的镜 ≥1（不是"shots_out 非空"——
    # shots_out 在我们采用 always-append 后恒等于 shots_meta 长度）。
    has_any_data = any(
        # shot 含 dialogue / sfx / reproduction 任一子对象即视为"有数据"
        bool(shot.get("dialogue") or shot.get("sfx") or shot.get("reproduction"))
        for shot in shots_out
    )

    if not has_any_data:
        # byte-identical-absent：不写 args.output（操作员可能保留了上一轮的有效产物，
        # 不主动 unlink）。print + warning 让操作员看见降级。
        msg = (f"zero shots with data → audio_semantic.json absent "
               f"(byte-identical v1.1 asset, CONTRACT-05)")
        audio_warnings.append(msg)
        print(f"[audio] {msg}")
        write_payload = None
    else:
        # 构建 payload（word_level_experimental 由 words_present 决定；schema_version
        # 来自 CONTRACT-03 lazy-import）。
        write_payload = {
            "schema_version": SCHEMA_VERSION,
            "word_level_experimental": words_present,
            "shots": shots_out,
        }

    # ─── (11) 写前 schema-validate（fails loud —— 项目惯例） ──────────
    # 仅在 write_payload 非 None 时校验 + 写入。poisoned-cache 失败再次触发 unlink。
    if write_payload is not None:
        errors = list(validator.iter_errors(write_payload))
        if errors:
            # poisoned-cache invalidation pass：找到哪些 shot 触发的错误，unlink 它们
            # 的 cache 文件，让下一轮重新拉路由 / degrade（mirror call_reid.py:418-431）。
            bad_shots = set()
            for e in errors:
                # absolute_path 形如 ['shots', N, 'dialogue', ...] —— 提取 shot index
                if e.absolute_path and e.absolute_path[0] == "shots":
                    idx = e.absolute_path[1]
                    if isinstance(idx, int) and 0 <= idx < len(shots_out):
                        bad_shots.add(shots_out[idx].get("shot_id"))
            for bad_sid in bad_shots:
                if isinstance(bad_sid, int):
                    cf = os.path.join(cache_dir, f"shot_{bad_sid:03d}.json")
                    if os.path.exists(cf):
                        try:
                            os.unlink(cf)
                            print(f"[audio] shot {bad_sid}: invalidated poisoned cache "
                                  f"(pre-write schema-validate fail)")
                        except OSError:
                            pass
            sys.exit(
                f"audio_semantic.json schema validation failed ({len(errors)} errors): "
                + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                            for e in errors[:3]))

        # 原子写（temp + os.replace —— 防 partial-write 被下游读到）
        tmp = args.output + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(write_payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, args.output)
        except OSError as e:
            sys.exit(f"audio_semantic.json write failed: {e}")

    # ─── (12) warnings sidecar READ-merge-write（mirror call_reid.py:443-449） ─
    # WR-01 self-dedup：strip prior [audio]-tagged warnings（本 step 上一轮写的）
    # 再 append fresh，防 self-accumulate（同 route-down 重跑导致 2N 增长）。
    # cross-step [semantic]/[reid]/etc tags 保留（非破坏性合并）。
    STEP_TAG = "[audio]"
    prior = [w for w in existing_warnings if not w.startswith(STEP_TAG)]
    tagged_audio = [f"{STEP_TAG} {w}" if not w.startswith(STEP_TAG) else w
                    for w in audio_warnings]
    all_warnings = prior + tagged_audio
    try:
        # sidecar 目录可能与 cache_dir 共享 route_cache/ —— 已在 step 4 cache_dir
        # makedirs 时创建；但保 defensive。
        sidecar_dir = os.path.dirname(warnings_sidecar)
        if sidecar_dir:
            os.makedirs(sidecar_dir, exist_ok=True)
        with open(warnings_sidecar, "w", encoding="utf-8") as f:
            json.dump({"warnings": all_warnings}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        # sidecar 写失败不阻塞主输出（export_asset.py best-effort 读 sidecar）。
        print(f"[audio] warning: sidecar write failed: {e}")

    # ─── (13) summary 行 ─────────────────────────────────────────────
    if write_payload is not None:
        print(f"[audio] wrote {args.output} "
              f"({len(shots_out)} shots, word_level_experimental={words_present}, "
              f"{len(audio_warnings)} new warnings)")
    else:
        print(f"[audio] audio_semantic.json absent ({len(audio_warnings)} new warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
