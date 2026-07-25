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
    shots[].reproduction ← 路由返回的 tts/music_gen/foley 三层 repro_prompt
                          （Phase 12 仅透传；Phase 15 owns recomposition）

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
    skeleton = {
        "shot_id": shot_meta["id"],
        "start_sec": shot_meta["start_sec"],
        "end_sec": shot_meta["end_sec"],
        "duration": shot_meta["duration"],
    }
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

    # ─── reproduction 投影（tts / music_gen / fley 三层 repro_prompt） ────
    # Phase 12 仅透传路由返回的 repro_prompt；Phase 15 owns recomposition。
    # 每层 type: ['object','null'] —— null 合法，object 必须有非空 text。
    try:
        raw_repro = route_shot.get("reproduction")
        if isinstance(raw_repro, dict):
            repro: dict = {}
            for key in ("tts", "music_gen", "foley"):
                layer = raw_repro.get(key)
                if layer is None:
                    repro[key] = None
                elif isinstance(layer, dict):
                    text = layer.get("text")
                    if isinstance(text, str) and text:
                        proj: dict = {"text": text}
                        conf = layer.get("confidence")
                        if isinstance(conf, (int, float)):
                            proj["confidence"] = max(0.0, min(1.0, float(conf)))
                        disc = layer.get("fidelity_disclaimer")
                        if isinstance(disc, str) and disc:
                            proj["fidelity_disclaimer"] = disc
                        repro[key] = proj
                    # object 但无有效 text → 视同缺席（不 emit 该 key）
                # 其他类型（list/number）→ 不 emit 该 key
            if repro:
                out["reproduction"] = repro
    except (KeyError, TypeError, ValueError, IndexError):
        pass   # reproduction 畸形 → 缺席

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
