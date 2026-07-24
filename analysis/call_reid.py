#!/usr/bin/env python3
"""跨镜角色 re-id 路由调用（character-reid route）→ registry.draft.json

本模块是 shot-timeline 的第二个网络依赖（sibling of analysis/call_shot_analysis.py）：
通过 httpx sync client 调用 kais-aigc-platform 的
`POST /api/v1/production/character-reid` 路由（DEFERRED —— 路由今日不存在，
镜像 feat/shot-analysis-route pre-merge 状态），把整支视频的跨镜角色聚类
（DINOv2 embedding + AgglomerativeClustering）归一化成 registry.draft.json
的 clusters[] 结构（每簇 review_state="proposed"）。

re-id 是**跨镜聚合**（NOT per-shot）—— 单镜内聚类是 trivial，所以整支视频
一次性 POST，cache 也是 per-video（route_cache/character_reid/video_<vch>.json），
不同于 shot_analysis 的 per-shot shot_XXX.json（Pitfall 4 prevention）。

路由 REQUEST 契约（DEFERRED —— shape 推断自 shot-analysis THIN-wrapper analog；
call_reid.py 是 shape-agnostic projector，不假设 shape 超过 registry.schema.json
约束 —— Pattern 1 显式投影丢弃路由多塞的字段）：
    {
      "video":           "<host abs path>",            # REQUIRED；路由自行 docker cp
      "shots":           "<host abs path>/shots.json",  # REQUIRED
      "mask_samples":    3,           # OPTIONAL；每 shot SAM3 采样帧数（CAST-02）
      "embedding_model": "facebook/dinov2-base",   # OPTIONAL default
      "tau":             0.30,        # OPTIONAL；cosine DISTANCE（CAST-04 advisory）
      "fps":             24           # OPTIONAL
    }
注：re-id 是跨镜聚合，无 shot_id_range（不同于 shot-analysis 的 per-shot 隔离）。

路由 RESPONSE envelope（@/lib/responseFormat.ts:success，同 shot-analysis）：
    {"code": 200,
     "data": {"clusters": [<cluster>, ...], "count": N, "outputDir": "...",
              "crops": ["char_001.png", ...]},
     "message": "Character re-id complete"}
route → producer normalize → registry.schema.json#clusters[]：
    {"cluster_id": "char_001", "mean_cosine": 0.92,
     "members": [{"shot_id": 1, "frame_pos": "first", "mask_quality": "high"}, ...]}
normalize_clusters 投影此 shape：加 review_state="proposed"（CAST-05 lock —— producer
永不 emit confirmed/rejected），加 tier（_tier_for by mean_cosine 三档 ≥0.85/0.6/<0.6），
丢弃路由多塞的字段（centroid_embedding/mask_bbox 等 —— schema additionalProperties:false
会拒）。路由侧 900s 硬超时（execFileSync）—— 客户端 --reid-timeout 默认 960s 故意超出
60s（同 Phase 6 Pitfall 1）。

输出：
  1. registry.draft.json —— {generated_at, model, tau, clusters: [...]}，写前用
     Draft202012Validator(registry.schema.json) 自校验（fails loud 惯例）。
  2. route_cache/character_reid/video_<vch>.json —— per-video 路由响应缓存（含
     _cache_key = (video_content_hash, route_name, route_version)；不匹配即 miss）。
  3. route_cache/warnings.json —— {"warnings": [...]} sidecar，**READ-merge-write**：
     先读 step_semantic 可能写入的现有 warnings，APPEND re-id warnings，再写回
     （非破坏性合并 —— 不同于 shot_analysis 的 overwrite）。

graceful-degrade（CAST-09）：路由不可达（--offline / preflight ConnectError / POST
失败）→ registry.draft.json 写空 clusters:[]（schema 合法），warnings sidecar 记失败
原因，asset 仍导出（characters.json/props.json 缺席，CONTRACT-06 conditional emission）。
preflight 只跑一次，失败即短路（Pitfall 7：无 retry storm）。offline + cache miss
不静默（Pitfall 4：显式记 warning）。

用法（被 run_pipeline.py:step_reid 以 subprocess 调用）：
  python3 analysis/call_reid.py \\
      --video /abs/path/to/video.mp4 \\
      --shots /abs/path/to/shots.json \\
      --work-dir output/<video-stem>/ \\
      --output output/<video-stem>/registry.draft.json \\
      [--reid-url http://127.0.0.1:8000/api/v1/production/character-reid] \\
      [--reid-timeout 960] \\
      [--offline]
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
ROUTE_NAME = "character_reid"
ROUTE_VERSION = "deferred-character-reid-route-v1"

# 路由 path（CONTEXT lock，硬编码 —— 不可由 --reid-url 自定义）。单一真源。
ROUTE_PATH = "/api/v1/production/character-reid"

# registry.schema.json 绝对路径（写前 Draft202012Validator 自校验用）。
# analysis/call_reid.py → repo root/spec/schemas/registry.schema.json
REGISTRY_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "registry.schema.json"


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

    httpx 异常的 str() 通常含请求 URL；若操作员把 basic-auth 嵌进 --reid-url
    （http://user:pass@host），warning 串会带凭据 → 流进 route_cache/warnings.json
    → scripts/export_asset.py → asset.json#generator.warnings 随资产外发。schema
    （asset.schema.json:59）显式禁止 warnings 含 auth token/body payloads。现代 httpx
    已在 URL.__str__ 里 mask 成 user:***@，但 exporter 接受任意 list[str] 不做 redaction
    —— 这里兜底，防 httpx 回归 / 自定义 transport / 路由 message 回显 URL 暴露凭据。
    无 URL 时是 no-op（正则不匹配）。
    """
    return re.sub(r"(https?://)([^@/]+@)", r"\1***@", msg)


def _tier_for(mean_cosine) -> str:
    """CONTEXT-locked 三档（advisory —— calibration deferred per Q2）。

    mean_cosine 是 cosine SIMILARITY（1.0 = 完全相同；0.0 = 正交）。
    registry.schema.json $comment 里的 τ 是 cosine DISTANCE（= 1 - similarity）。
    tier 字段是 authoritative label —— 不依赖 numeric schema 字段强制；
    mean_cosine 是 advisory 数值，Phase 7 ep01 spike 校准后可能调整阈值。
    """
    if not isinstance(mean_cosine, (int, float)):
        return "review"   # 未知 / 非 number → 进 review 队列让人决定
    if mean_cosine >= 0.85:
        return "auto_merge"
    if mean_cosine >= 0.6:
        return "review"
    return "auto_distinct"


def normalize_clusters(route_data: dict | None) -> list[dict]:
    """route response → registry.schema.json#clusters[] shape（CAST-05 投影）。

    显式投影：路由多塞的字段（centroid_embedding/mask_bbox 等）被丢弃 ——
    schema additionalProperties:false 会拒；这里只留 schema-allowed 字段
    （cluster_id/review_state/tier/mean_cosine/members；members 投影到
    shot_id/frame_pos/mask_quality）。

    Args:
        route_data: 路由 data 字段（含 clusters key），或 None（cache miss +
            route down —— graceful-degrade 走空 clusters）。

    Returns:
        list of cluster dicts，每个 schema-conforming。空 clusters 在 schema
        里合法（clusters 是 array 无 minItems）。非 dict / clusters 非 list /
        畸形条目一律降级为空列表（defense-in-depth）。
    """
    # CR-02 同款 isinstance 守卫：route_data 非 dict（route bug 回 list/string，
    # 或 None）→ 空 clusters。
    if not isinstance(route_data, dict):
        return []
    raw = route_data.get("clusters")
    if not isinstance(raw, list):
        return []
    clusters = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        # CR-02：畸形 cluster（缺 cluster_id / 类型错 / pattern 不符）一律降级跳过
        # （defense-in-depth —— 本 docstring 承诺"畸形条目一律降级为空列表"）。
        # broad try/except 兜底任何未预见畸形（KeyError/TypeError/ValueError/IndexError）。
        try:
            cid = r.get("cluster_id")
            if not (isinstance(cid, str)
                    and re.match(r"^(char|prop)_[0-9]{3}$", cid)):
                # cluster_id 缺失 / 非 str / pattern 不符 → 跳过（不 crash）
                continue
            # members 投影：只留 schema-allowed 字段
            members = []
            for m in r.get("members") or []:
                # shot_id 必须是 int（schema type:integer）；非 int 的 member 跳过
                # （路由 bug 回 string shot_id 不应流向下游）
                if isinstance(m, dict) and isinstance(m.get("shot_id"), int):
                    member = {
                        "shot_id": m["shot_id"],
                        "frame_pos": m.get("frame_pos", "first"),   # 接受 string 或 number
                    }
                    # mask_quality 可选（schema optional）；有才加
                    if m.get("mask_quality"):
                        member["mask_quality"] = m["mask_quality"]
                    members.append(member)
            if not members:
                continue   # 空 cluster 丢弃（schema minItems:1）
            mc = r.get("mean_cosine")
            clusters.append({
                "cluster_id": cid,                            # schema pattern ^(char|prop)_[0-9]{3}$
                "review_state": "proposed",                   # CAST-05：producer 永远 emit proposed
                "tier": _tier_for(mc),                        # auto_merge/review/auto_distinct
                "mean_cosine": float(mc) if isinstance(mc, (int, float)) else 0.0,
                "members": members,
            })
        except (KeyError, TypeError, ValueError, IndexError):
            # 任意畸形字段访问 → 跳过本 cluster（graceful-degrade，不 crash pipeline）
            continue
    return clusters


def call_route(client, body: dict) -> tuple[dict | None, str | None]:
    """单次 per-video 路由 POST 调用（re-id 是跨镜聚合，非 per-shot）。

    Args:
        client: httpx.Client（base_url 已含路由 host root）。
        body: POST body（整支视频，无 shot_id_range）。

    Returns:
        (data_dict, None) 成功 —— 取整个 data（含 clusters key），不同于
            shot_analysis 的取 shots[0]（re-id 返回 data.clusters list）。
        (None, error_msg) 任意失败 —— httpx.HTTPError 根异常覆盖
            ConnectError/TimeoutException/HTTPStatusError/NetworkError。
        不 retry —— per-video 失败非致命（CONTEXT D-XX graceful-degrade）。
    """
    import httpx  # lazy import —— WR-02：offline 模式不联网不 import httpx
    try:
        resp = client.post(ROUTE_PATH, json=body)
        resp.raise_for_status()                          # 4xx/5xx → HTTPStatusError
        # CR-02：非 JSON 200 body（反代 HTML 错误页 / 代理 502 伪 200）
        try:
            payload = resp.json()
        except ValueError as e:
            # WR-05：body 可能是反代 HTML 错误页（回显 URL），_safe_error 兜底抹凭据。
            return None, _safe_error(
                f"route returned non-JSON body: {type(e).__name__}: {e}")
        # CR-02：envelope 非 dict（路由 bug 回 bare list/string/number）→ degrade
        if not isinstance(payload, dict):
            return None, _safe_error(
                f"route envelope not a dict: {type(payload).__name__}")
        if payload.get("code") != 200:
            # WR-05：route message 可能回显 URL，_safe_error 兜底。
            return None, _safe_error(
                f"route code={payload.get('code')}: {payload.get('message')}")
        # CR-02：data 字段防御性 isinstance；re-id 返回整个 data dict（含 clusters）
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, _safe_error(
                f"route data not a dict: {type(data).__name__}")
        return data, None
    except (httpx.HTTPError, ValueError, AttributeError,
            TypeError, KeyError) as e:
        # CR-02：broaden except —— httpx.HTTPError 覆盖 ConnectError/Timeout/
        # HTTPStatusError/NetworkError；其余覆盖 envelope 畸形 / 字段缺失等非
        # httpx 异常（defense-in-depth）。一律走 degrade：空 clusters + warning。
        # WR-05：str(httpx 异常) 含请求 URL —— 可能带 user:pass@，_safe_error 抹掉。
        return None, _safe_error(f"{type(e).__name__}: {e}")


def preflight(base_url: str, timeout: float = 5.0) -> tuple[bool, str | None]:
    """步前健康探测（CINEMA-05 analog）—— 只跑一次，失败短路。

    ANY HTTP 响应（哪怕 404/405 —— 路由只 define POST /，GET 探测预期 404/405）
    都算 "up"（Assumption A3：任何 HTTP 响应证明 host:port 可达）。
    仅 httpx.HTTPError（ConnectError 等）→ (False, msg)，驱动 route_down 短路
    （Pitfall 7：无 retry storm）。
    """
    import httpx
    # base_url 含 /api/v1/production/character-reid path；探测时 rsplit 掉 /api/v1
    # 之后的部分取 host root，再拼 ROUTE_PATH（WR-03：与 main client 一致 strip）。
    base = base_url.rsplit("/api/v1", 1)[0]
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


def main():
    from datetime import datetime, timezone

    ap = argparse.ArgumentParser(
        description="跨镜角色 re-id 路由调用 → registry.draft.json（第二个网络依赖步骤）")
    ap.add_argument("--video", required=True,
                    help="原始视频绝对路径（含 audio 流）")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径（pipeline 中间产物，含 id/start/end/duration）")
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— route_cache 写在其下")
    ap.add_argument("--output", required=True,
                    help="registry.draft.json 输出路径")
    ap.add_argument("--reid-url",
                    default="http://127.0.0.1:8000/api/v1/production/character-reid",
                    help="character-reid 路由 URL（含 /api/v1/production/character-reid path；"
                         "默认端口 8000 —— 路由 DEFERRED 未上线，首跑需 verify 实际端口）")
    ap.add_argument("--reid-timeout", type=float, default=960.0,
                    help="单次路由调用 read 超时秒（默认 960，> 路由侧 900s execFileSync）")
    ap.add_argument("--offline", action="store_true",
                    help="仅读 route_cache 不联网（cache 命中即用，miss 则降级空 clusters）")
    args = ap.parse_args()

    # 1. 载入 shots 元数据（验证可读 + 路径用于 route body）+ 计算 video_content_hash
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    vch = video_content_hash(args.video)

    # 2. cache 目录（per-video —— re-id 是跨镜聚合，不同于 shot_analysis 的 per-shot）
    cache_dir = os.path.join(args.work_dir, "route_cache", ROUTE_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"video_{vch}.json")

    # 3. warnings sidecar —— READ existing（step_semantic 可能已写入，非破坏性合并）
    warnings_sidecar = os.path.join(args.work_dir, "route_cache", "warnings.json")
    existing_warnings = []
    if os.path.exists(warnings_sidecar):
        try:
            with open(warnings_sidecar, encoding="utf-8") as f:
                sidecar = json.load(f)
            if isinstance(sidecar, dict) and isinstance(sidecar.get("warnings"), list):
                existing_warnings = [w for w in sidecar["warnings"] if isinstance(w, str)]
        except (OSError, json.JSONDecodeError):
            existing_warnings = []   # 损坏的 sidecar 不阻塞本步骤

    # 4. 本步骤新增 warnings
    reid_warnings: list[str] = []

    # 5. cache lookup —— _cache_key 不匹配（video 变 / route_version 旧）= miss
    route_data = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)
        except (OSError, json.JSONDecodeError):
            cached = {}
        ck = cached.get("_cache_key", {})
        if (ck.get("video_content_hash") == vch
                and ck.get("route_name") == ROUTE_NAME
                and ck.get("route_version") == ROUTE_VERSION):
            print(f"[reid] cache hit: {cache_file}")
            route_data = cached
        # else: stale（video 变 / ROUTE_VERSION bump）→ route_data 保持 None（Pitfall 5）

    # 6. Preflight（非 offline 才探）—— 失败即标 route_down，短路剩余 POST
    route_down = args.offline
    if not args.offline:
        ok, msg = preflight(args.reid_url)
        if not ok:
            route_down = True
            reid_warnings.append(msg)
            print(f"[reid] preflight failed → route_down: {msg}")

    # 7. cache miss + 非 route_down → 联网 per-video POST
    if route_data is None and not route_down:
        import httpx   # WR-02：offline 模式不 import httpx
        base = args.reid_url.rsplit("/api/v1", 1)[0]
        client = httpx.Client(
            base_url=base,
            timeout=httpx.Timeout(connect=5.0, read=args.reid_timeout,
                                  write=5.0, pool=5.0))
        try:
            body = {
                "video": os.path.abspath(args.video),
                "shots": os.path.abspath(args.shots),
                "mask_samples": 3,
                "embedding_model": "facebook/dinov2-base",
                "tau": 0.30,
                "fps": 24,
            }
            route_data, err = call_route(client, body)
            if err:
                reid_warnings.append(f"character-reid: {err}")
                print(f"[reid] route FAIL: {err}")
                route_data = None
            else:
                # 写 cache（带 _cache_key 四元组）
                cache_payload = {
                    **route_data,
                    "_cache_key": {
                        "video_content_hash": vch,
                        "route_name": ROUTE_NAME,
                        "route_version": ROUTE_VERSION,
                    },
                }
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache_payload, f, ensure_ascii=False, indent=2)
        finally:
            client.close()

    # 8. cache miss + route_down —— Pitfall 4：不静默，显式记 warning
    if route_data is None and route_down:
        reid_warnings.append("character-reid: offline/cache-miss → empty draft")

    # 9. normalize route response → registry.schema.json#clusters[] shape
    clusters = normalize_clusters(route_data)

    # 10. 组 registry.draft.json（generated_at 每次新鲜 —— pipeline-internal draft）
    registry_draft = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "facebook/dinov2-base",
        "tau": 0.30,
        "clusters": clusters,
    }

    # 11. 写前 schema 自校验（fails loud —— 项目惯例，防畸形输出流向下游）
    from jsonschema import Draft202012Validator
    with open(REGISTRY_SCHEMA, encoding="utf-8") as f:
        registry_schema = json.load(f)
    errors = list(Draft202012Validator(registry_schema).iter_errors(registry_draft))
    if errors:
        sys.exit(
            f"registry.draft.json schema validation failed ({len(errors)} errors): "
            + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                        for e in errors[:3]))

    # 12. 原子写 registry.draft.json（temp + os.replace —— 防 partial-write 被下游读到）
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry_draft, f, ensure_ascii=False, indent=2)
    os.replace(tmp, args.output)

    # 13. warnings sidecar —— READ-merge-write（非破坏性：APPEND 到 step_semantic 现有）
    all_warnings = existing_warnings + reid_warnings
    with open(warnings_sidecar, "w", encoding="utf-8") as f:
        json.dump({"warnings": all_warnings}, f, ensure_ascii=False, indent=2)

    print(f"[reid] wrote {args.output} "
          f"({len(clusters)} clusters, {len(reid_warnings)} new warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
