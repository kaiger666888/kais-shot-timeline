#!/usr/bin/env python3
"""逐镜头运镜分析路由调用（shot-analysis route）→ prompts.json facets

本模块是 shot-timeline 首个网络依赖：通过 httpx sync client 调用
kais-aigc-platform 的 `POST /api/v1/production/shot-analysis` 路由（分支
feat/shot-analysis-route），把每镜的运镜分析（geometry + semantic）映射进
prompts.json 的 camera/action/lighting/style 结构化字段。

路由 REQUEST 契约（直接从 feat/shot-analysis-route:src/routes/production/
shot-analysis/index.ts 读取，Phase 6 研究 §Route REQUEST Contract）：
    {
      "video":         "<host abs path>",            # REQUIRED；路由自行 docker cp
      "shots":         "<host abs path>/shots.json",  # REQUIRED
      "shot_id_range": [N, N],   # OPTIONAL；Phase 6 恒传 [N,N] 做 per-shot 隔离
      "semantic":      true,     # OPTIONAL default false；Phase 6 MUST 传 true
                                 #   （否则 semantic.* 不填，映射失效）
      "subject":       false,    # OPTIONAL default false；Phase 6 传 false（不用 SAM3 层）
      "grid_n":        20,       # OPTIONAL 1-200 default 20
      "fps":           24        # OPTIONAL 1-120 default 24
    }

路由 RESPONSE envelope（@/lib/responseFormat.ts:success）：
    {"code": 200, "data": {"shots": [<shot_XXX.json>], "count": N, ...}, "message": "..."}
per-shot 调用（shot_id_range=[N,N]）时 data.shots 恰好 1 个元素，取 [0]。

路由侧 900s 硬超时（execFileSync(timeout=900_000)）—— 客户端 --analysis-timeout
默认 960s 故意超出 60s，让路由先自杀完毕、客户端拿到确定的 500 走 graceful-degrade
（Pitfall 1）。

映射（CONTEXT D-XX LOCKED，已对 7 个真实 captured fixtures 验证 0 schema 错误）：
    camera   ← COMPOSE(semantic.shot_scale, semantic.camera_primitive,
                       semantic.camera_speed, geometry.primitive)  # ", " 连接，滤 None/""
    action   ← semantic.subject_motion
    lighting ← semantic.lighting
    style    ← semantic.lens_feel
    subject  ← ""   # 永不伪造（Phase 7 re-id 处理身份）
    scene    ← ""   # 永不伪造（未来 Qwen-VL 扩展）
    prompt_text ← "" # Phase 8 PROMPT-02 owns narrative recomposition

输出：
  1. prompts.json —— array[{shot_id, start_sec, end_sec, duration, subject,
     action, camera, scene, lighting, style, prompt_text}]，写前用
     Draft202012Validator(prompts.schema.json) 自校验（fails loud 惯例）。
  2. route_cache/shot_analysis/shot_XXX.json —— 每镜路由响应（含 _cache_key），
     key = (video_content_hash, route_name, route_version)；不匹配即视为 miss。
  3. route_cache/warnings.json —— {"warnings": [...]} sidecar，由
     scripts/export_asset.py:main() best-effort 读取并合并进 generator.warnings。

graceful-degrade：路由不可达（--offline / preflight ConnectError / per-shot 失败）
→ 所有路由源 facets 写为空串 ""（prompts.schema facets 是 type:string 无 minLength，
schema 合法），asset 仍导出，warnings sidecar 记失败原因（Pitfall 4：offline cache
miss 不静默）。preflight 只跑一次，失败即短路（Pitfall 7：无 per-shot retry storm）。

用法（被 run_pipeline.py:step_semantic 以 subprocess 调用）：
  python3 analysis/call_shot_analysis.py \\
      --video /abs/path/to/video.mp4 \\
      --shots /abs/path/to/shots.json \\
      --work-dir output/<video-stem>/ \\
      --output output/<video-stem>/prompts.json \\
      [--analysis-url http://127.0.0.1:8000/api/v1/production/shot-analysis] \\
      [--analysis-timeout 960] \\
      [--offline]
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


# ─── 模块级常量 ─────────────────────────────────────────────────────────────
# cache key 组成部分。ROUTE_VERSION 是 cache-invalidation 旋钮 —— 路由逻辑变了
# 就 bump 此串 → 全部 cache miss（Pitfall 5：避免"改了代码但行为不变"）。
ROUTE_NAME = "shot_analysis"
ROUTE_VERSION = "feat-shot-analysis-route-v1"

# 路由 path（CONTEXT lock，硬编码 —— 不可由 --analysis-url 自定义）。IN-01：旧实现
# 把此串散落在 call_route.post / preflight.rsplit / preflight.get 三处，改 path 需
# 改三行无编译期保证。抽成单一真源。WR-03：--analysis-url 的 /api/v1 之后部分会被
# 一致 strip 掉（preflight + main client 都 rsplit 到 host root 再拼 ROUTE_PATH），
# 不再出现"main 用全 URL 作 base、preflight 却 strip"的静默不一致。
ROUTE_PATH = "/api/v1/production/shot-analysis"

# prompts.schema.json 绝对路径（写前 Draft202012Validator 自校验用）。
# analysis/call_shot_analysis.py → repo root/spec/schemas/prompts.schema.json
PROMPTS_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "prompts.schema.json"


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


def compose_facets(route_shot: dict | None) -> dict:
    """路由响应 → prompts facets 映射（CONTEXT D-XX LOCKED）。

    Args:
        route_shot: 单镜路由响应（含 geometry + semantic），或 None（cache miss +
            route down —— graceful-degrade 走全空 facets）。

    Returns:
        {"camera", "action", "lighting", "style", "subject", "scene"} 六个 str。
        None/空字段自动滤除（Pitfall 3：防 "None" 字面 + 前导 ", "）。
    """
    # CR-02：route_shot 非 dict（route bug 回 list/string，或 None）→ 全空 facets。
    # 旧 `if route_shot is None` 漏了 truthy 非 dict —— 后续 .get 会 AttributeError
    # 逃出 except httpx.HTTPError。统一 isinstance 守卫，None 与非 dict 同走降级。
    if not isinstance(route_shot, dict):
        return {"camera": "", "action": "", "lighting": "",
                "style": "", "subject": "", "scene": ""}

    # CR-02：`or {}` 只能把 None/falsy 强转空 dict —— route bug 回 list/string 时
    # `route_shot.get("semantic") or {}` 会返回那个 list/string，下一行 .get 崩
    # （CR-02 第 3 点：compose_facets 在非 dict truthy sem/geo 上崩溃）。改 isinstance
    # 守卫：非 dict 一律当空 dict（路由 Qwen3-VL 低信号镜头回 null 也由这里兜住）。
    sem = route_shot.get("semantic") if isinstance(route_shot.get("semantic"), dict) else {}
    geo = route_shot.get("geometry") if isinstance(route_shot.get("geometry"), dict) else {}

    def join(*parts):
        # `if p` 滤除 None / "" / 0 —— Pitfall 3 修复。
        return ", ".join(str(p) for p in parts if p)

    return {
        "camera":   join(sem.get("shot_scale"), sem.get("camera_primitive"),
                         sem.get("camera_speed"), geo.get("primitive")),
        "action":   sem.get("subject_motion") or "",    # None → ""
        "lighting": sem.get("lighting") or "",
        "style":    sem.get("lens_feel") or "",
        "subject":  "",    # 永不伪造 —— Phase 7 re-id 处理身份
        "scene":    "",    # 永不伪造 —— 未来 Qwen-VL 扩展
    }


def call_route(client, body: dict) -> tuple[dict | None, str | None]:
    """单镜路由 POST 调用（CINEMA-01 route call + CINEMA-03 degrade）。

    Args:
        client: httpx.Client（base_url 已含路由 path 前缀）。
        body: POST body（shot_id_range=[N,N] per-shot 隔离）。

    Returns:
        (route_shot_dict, None) 成功 —— 取 data.shots[0]（per-shot 调用只 1 个）。
        (None, error_msg) 任意失败 —— httpx.HTTPError 根异常覆盖
            ConnectError/TimeoutException/HTTPStatusError/NetworkError（Pattern 2）。
        不 retry —— per-shot 失败非致命（CONTEXT D-XX）。
    """
    import httpx  # lazy import —— 沿用 audio/transcribe.py 的 optional-dep 惯例
    try:
        resp = client.post(ROUTE_PATH, json=body)
        resp.raise_for_status()                          # 4xx/5xx → HTTPStatusError
        # CR-02：非 JSON 200 body（反代 HTML 错误页 / 代理 502 伪 200）——
        # resp.json() raise JSONDecodeError(ValueError)，旧实现 except 只抓
        # httpx.HTTPError 漏了它 → uncaught traceback → step_semantic 崩。单独
        # 包一层 except ValueError 走 degrade（graceful-degrade 不可破）。
        try:
            payload = resp.json()
        except ValueError as e:
            return None, f"route returned non-JSON body: {type(e).__name__}: {e}"
        # CR-02：envelope 非 dict（路由 bug 回 bare list/string/number）——
        # payload.get 会 AttributeError；isinstance 守卫走 degrade。
        if not isinstance(payload, dict):
            return None, f"route envelope not a dict: {type(payload).__name__}"
        if payload.get("code") != 200:
            return None, f"route code={payload.get('code')}: {payload.get('message')}"
        # CR-02：data 字段也防御性 isinstance（data 若是非 dict truthy 如 string，
        # `(data or {}).get` 仍会崩）。与 compose_facets 的 sem/geo 守卫同模式。
        data = payload.get("data")
        shots = data.get("shots") if isinstance(data, dict) else None
        shots = shots or []
        if not shots:
            return None, (f"route returned 0 shots for "
                          f"shot_id_range={body.get('shot_id_range')}")
        return shots[0], None                            # per-shot 调用恒取 [0]
    except (httpx.HTTPError, ValueError, AttributeError,
            TypeError, KeyError) as e:
        # CR-02：broaden except —— httpx.HTTPError 覆盖 ConnectError/Timeout/
        # HTTPStatusError/NetworkError；其余覆盖 envelope 畸形 / 字段缺失等非
        # httpx 异常（defense-in-depth，防任何漏网访问路径让 step_semantic 崩 →
        # run_pipeline abort）。一律走 degrade：空 facets + warning 记异常类。
        return None, f"{type(e).__name__}: {e}"


def preflight(base_url: str, timeout: float = 5.0) -> tuple[bool, str | None]:
    """步前健康探测（CINEMA-05）—— 只跑一次，失败短路。

    ANY HTTP 响应（哪怕 404/405 —— 路由只 define POST /，GET 探测预期 404/405）
    都算 "up"（Assumption A3：任何 HTTP 响应证明 host:port 可达）。
    仅 httpx.HTTPError（ConnectError 等）→ (False, msg)，驱动 route_down 短路
    剩余 shots（Pitfall 7：无 per-shot retry storm）。
    """
    import httpx
    # base_url 含 /api/v1/production/shot-analysis path；探测时 rsplit 掉 /api/v1
    # 之后的部分取 host root，再拼 ROUTE_PATH（WR-03：与 main client 一致 strip，
    # 不再用散落的字面串 —— ROUTE_PATH 单一真源）。
    base = base_url.rsplit("/api/v1", 1)[0]
    try:
        with httpx.Client(base_url=base,
                          timeout=httpx.Timeout(connect=5.0, read=5.0,
                                                write=5.0, pool=5.0)) as probe:
            probe.get(ROUTE_PATH, timeout=timeout)
        return True, None
    except httpx.HTTPError as e:
        return False, f"preflight route unreachable: {type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(
        description="逐镜头运镜分析路由调用 → prompts.json（首个网络依赖步骤）")
    ap.add_argument("--video", required=True,
                    help="原始视频绝对路径（含 audio 流）")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径（pipeline 中间产物，含 id/start/end/duration）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— route_cache 写在其下")
    ap.add_argument("--output", required=True,
                    help="prompts.json 输出路径")
    ap.add_argument("--analysis-url",
                    default="http://127.0.0.1:8000/api/v1/production/shot-analysis",
                    help="shot-analysis 路由 URL（含 /api/v1/production/shot-analysis path）")
    ap.add_argument("--analysis-timeout", type=float, default=960.0,
                    help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
    ap.add_argument("--offline", action="store_true",
                    help="仅读 route_cache 不联网（cache 命中即用，miss 则降级空 facets）")
    args = ap.parse_args()

    # 1. 载入 shots 元数据 + 计算 video_content_hash（cache key 组成）
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    vch = video_content_hash(args.video)

    # 2. cache 目录 + warnings sidecar 路径
    cache_dir = os.path.join(args.work_dir, "route_cache", ROUTE_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    warnings_sidecar = os.path.join(args.work_dir, "route_cache", "warnings.json")
    warnings: list[str] = []
    prompts: list[dict] = []

    # 3. Preflight（非 offline 才探）—— 失败即标 route_down，短路剩余 shots
    route_down = args.offline
    if not args.offline:
        ok, msg = preflight(args.analysis_url)
        if not ok:
            route_down = True
            warnings.append(msg)
            print(f"[semantic] preflight failed → route_down mode: {msg}")

    # 4. 长驻 client（read timeout = --analysis-timeout，故意 > 路由侧 900s）
    # WR-02：offline 模式不联网 → 不 import httpx、不建 client（cache-only 在无 httpx
    # 的 box 上也能跑，沿用 CLAUDE.md optional-dep lazy-import 惯例）。per-shot 循环
    # 仍跑（读 cache + 写 prompts）；call_route 仅在 `not route_down` 分支被调用，
    # offline 时 route_down=True → client=None 永不触网。
    client = None
    if not args.offline:
        import httpx
        # WR-03：base 只取 host root（rsplit 掉 /api/v1 之后部分），post 用 ROUTE_PATH。
        # 旧实现 base_url=全 URL + post 绝对路径 → RFC 3986 把 /api/v1 之前的 path
        # 前缀（如反代 /prod/api/v1）静默丢弃，且与 preflight（strip 过）不一致。
        # 现与 preflight 一致 strip 到 host root；ROUTE_PATH 是 CONTEXT-locked 常量。
        base = args.analysis_url.rsplit("/api/v1", 1)[0]
        client = httpx.Client(
            base_url=base,
            timeout=httpx.Timeout(connect=5.0, read=args.analysis_timeout,
                                  write=5.0, pool=5.0))
    try:
        # 5. per-shot 循环
        for s in shots_meta:
            sid = s["id"]
            cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")

            # (a) cache lookup —— _cache_key 不匹配（video 变 / route_version 旧）= miss
            route_shot = None
            # cache_stale: cache_file 存在但 _cache_key 不匹配（CR-01：必须与"文件
            # 缺失"区分开 —— offline + stale-cache 同样要显式记 warning，否则操作员
            # 拿到空 facets 的 prompts.json 毫无察觉，正是 Pitfall 4 要防的静默降级）。
            cache_stale = False
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        cached = json.load(f)
                except (OSError, json.JSONDecodeError):
                    cached = {}
                ck = cached.get("_cache_key", {})
                # WR-04：文档化的 4-tuple (video_content_hash, route_name, route_version)
                # 全部参与比对。旧实现漏了 route_name —— 今天 ROUTE_NAME 是常量无影响，
                # 但 Phase 7 若在同 route_cache/ 树缓存第二条 route（如 re-id），route_name
                # 不比对会让 shot_001.json 跨 route 误命中（latent bug + 与文档矛盾）。
                if (ck.get("video_content_hash") == vch
                        and ck.get("route_name") == ROUTE_NAME
                        and ck.get("route_version") == ROUTE_VERSION):
                    print(f"[semantic] shot {sid}: cache hit")
                    route_shot = cached
                else:
                    # 文件在但 key 不匹配（video 变 / route_name 异 / ROUTE_VERSION bump）→ stale miss
                    cache_stale = True   # fall through：route_shot 保持 None（Pitfall 5）

            # (b) cache miss + 非 route_down → 联网 per-shot POST（CONTEXT lock: semantic=True, subject=False）
            if route_shot is None and not route_down:
                body = {
                    "video": os.path.abspath(args.video),
                    "shots": os.path.abspath(args.shots),
                    "shot_id_range": [sid, sid],     # per-shot 隔离（Pitfall 6）
                    "semantic": True,                # MUST（否则映射失效）
                    "subject": False,                # Phase 6 不用 SAM3 层
                    "grid_n": 20,
                    "fps": 24,
                }
                route_shot, err = call_route(client, body)
                if err:
                    warnings.append(f"shot {sid}: {err}")
                    print(f"[semantic] shot {sid}: FAIL {err}")
                    route_shot = None                # degrade 走空 facets
                else:
                    # 写 cache（带 _cache_key，四元组 video_content_hash/route_name/route_version）
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump({**route_shot, "_cache_key": {
                            "video_content_hash": vch,
                            "route_name": ROUTE_NAME,
                            "route_version": ROUTE_VERSION,
                        }}, f, ensure_ascii=False, indent=2)

            # (c) cache miss + route_down —— Pitfall 4：不静默，显式记 warning
            # CR-01 修复：旧实现用 `not os.path.exists(cache_file)` 把"文件存在但
            # _cache_key 不匹配"的情况漏了 —— 那正是 ROUTE_VERSION bump / video 替换
            # 后最常见的 offline 场景，操作员会拿到空 facets 的 prompts.json 且零 warning。
            # 现按 cache_stale 标记区分两种 miss，两种都显式记 warning（schema 合法
            # 但内容降级 —— 必须让操作员看见输出被降级）。
            if route_shot is None and route_down:
                if cache_stale:
                    warnings.append(
                        f"shot {sid}: offline/stale-cache (_cache_key mismatch) "
                        f"→ empty facets")
                else:
                    warnings.append(f"shot {sid}: offline/cache-miss → empty facets")

            # (d) 映射 → facets（route_shot is None → 全空，schema 仍合法）
            facets = compose_facets(route_shot)

            # (e) 组 prompts entry（prompt_text 留空 —— Phase 8 owns recomposition）
            prompts.append({
                "shot_id": sid,
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "duration": s["duration"],
                "subject": facets["subject"],
                "action": facets["action"],
                "camera": facets["camera"],
                "scene": facets["scene"],
                "lighting": facets["lighting"],
                "style": facets["style"],
                "prompt_text": "",
            })
    finally:
        # WR-02：client 仅在非 offline 时建 → 条件 close（None 时跳过）。
        if client is not None:
            client.close()

    # 6. 写前 schema 自校验（fails loud —— 项目惯例，防映射写错字段流向下游）
    from jsonschema import Draft202012Validator
    with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
        prompts_schema = json.load(f)
    errors = list(Draft202012Validator(prompts_schema).iter_errors(prompts))
    if errors:
        sys.exit(
            f"prompts.json schema validation failed ({len(errors)} errors): "
            + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                        for e in errors[:3]))

    # 7. 原子写 prompts.json（temp + os.replace —— 防 partial-write 被下游读到）
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    os.replace(tmp, args.output)

    # 8. 写 warnings sidecar（Plan 01 contract：{"warnings": [...]}；export_asset 读）
    with open(warnings_sidecar, "w", encoding="utf-8") as f:
        json.dump({"warnings": warnings}, f, ensure_ascii=False, indent=2)

    print(f"[semantic] wrote {args.output} "
          f"({len(prompts)} shots, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
