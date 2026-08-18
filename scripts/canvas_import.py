#!/usr/bin/env python3
"""画布导入器：把 output/<video-stem>/ 资产目录导入 kap 画布项目。

目的：在管线末端（或独立运行时）省掉手工 curl 三连（找项目 → 建项目 →
import-from-dir），让「小江湖·逆推资产集」类资产一键出现在 kap 画布里。
纯 urllib 实现（零新增依赖，CONTEXT lock —— 脚本层禁 httpx/requests）。

行为（kap-side API 事实全部经 127.0.0.1:10588 live probe + kap 源码直读验证）：
  * POST /api/canvas/projects（body {}）→ {code:200, data:[{id,name,mode,...}]}
    —— 按 name 精确匹配找已有项目；命中则复用其 int id，全程零 addProject。
  * 项目不存在且允许创建 → POST /api/project/addProject（validateFields 必填
    11 个全字符串字段；除 name/intro/mode="canvas-v2" 外全空串，对齐画布
    ep01 项目行实测取值）。addProject 响应不含项目 id（kap 源码
    src/routes/project/addProject.ts:44 只返 {message}，id 服务端 Date.now()）
    —— 建完后必须回读 /api/canvas/projects 按 name 再匹配拿新 id。
  * POST /api/canvas/v2/import-from-dir（zod schema：projectId z.number()、
    episodesId z.number()、workdir z.string().min(1)、mode z.enum(["merge",
    "replace"])，默认 merge）—— workdir 取 asset_dir 绝对路径，JSON 以 UTF-8
    编码（ensure_ascii=False，含 CJK + 全角标点路径不炸）。
  * intro 来源：asset.json 的 source.video_filename 去 extension（asset.json
    没有 episode 字段，video_filename stem 是最近似的「episode 名」）；
    asset.json 缺失/损坏 → asset_dir basename（graceful，不 exit）。
  * 网络错误（URLError/HTTPError/非 200 code）→ 中文错误 + sys.exit 非 0
    （standalone fail-loud 是项目惯例；pipeline 侧 graceful-degrade 由
    run_pipeline.py 的 post-step 接线负责，本脚本不吞错）。

用法：
  python3 scripts/canvas_import.py \
      --asset-dir output/<video-stem>/ \
      --project-name "小江湖·逆推资产集(ep01)" \
      [--base-url http://127.0.0.1:10588] \
      [--episodes-id 1] [--mode merge|replace] [--no-create-project]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 超时：projects/addProject 是轻查询（30s 足够）；import 要扫媒体目录 + 建
# symlink，慢路径给 600s（mirror run_pipeline --audio-timeout 900s 的"略大于
# 服务端最坏耗时"取值口径）。
LIST_TIMEOUT_SEC = 30.0
IMPORT_TIMEOUT_SEC = 600.0


def _post_json(base_url: str, path: str, payload: dict,
               timeout: float = LIST_TIMEOUT_SEC) -> dict:
    """唯一 HTTP 出口：POST JSON body → 解析 {code,data} envelope。

    UTF-8 编码强制（ensure_ascii=False + encode("utf-8")）：workdir 携带
    CJK + 全角标点路径（T-AW2-01），URL 只拼接纯 ASCII path，路径只进 body。

    失败一律中文错误 + sys.exit 非 0（standalone fail-loud）：
      * HTTPError（4xx/5xx）→ 读 body 拼 HTTP status + envelope message
      * URLError（连接拒绝/超时）→ 提示 kap 服务未启动
      * envelope.code != 200 → 打印整个 envelope 供排查
    """
    url = base_url.rstrip("/") + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        # HTTPError 也是 file-like —— e.read() 拿错误 body（kap envelope message）
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        sys.exit(f"[canvas-import] HTTP {e.code} 错误: POST {path}\n"
                 f"  响应: {detail or '(空)'}")
    except urllib.error.URLError as e:
        sys.exit(f"[canvas-import] 无法连接 kap 服务: {url}\n"
                 f"  原因: {e.reason}\n"
                 f"  请确认服务已启动（默认 http://127.0.0.1:10588）")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        sys.exit(f"[canvas-import] 响应不是合法 JSON: POST {path}\n"
                 f"  raw: {raw[:300]!r}")
    if not isinstance(envelope, dict) or envelope.get("code") != 200:
        sys.exit(f"[canvas-import] kap 返回失败: POST {path}\n  {envelope}")
    return envelope


def _episode_intro(asset_dir: str) -> str:
    """读 asset.json 的 source.video_filename 取 stem 作为项目 intro。

    asset.json 没有 episode 字段 —— source.video_filename 的 stem（如
    "虫虫武侠小故事《小江湖》第01话：…"）是最近似的「episode 名」。文件
    缺失 / JSON 损坏 / 字段缺席 / 非字符串 → fallback asset_dir basename
    （graceful，不 exit：intro 只是展示字段，不应阻塞导入）。
    """
    try:
        with open(os.path.join(asset_dir, "asset.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        filename = data["source"]["video_filename"]
        if isinstance(filename, str) and filename.strip():
            return Path(filename).stem
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return Path(asset_dir).name


def find_project(base_url: str, name: str,
                 timeout: float = LIST_TIMEOUT_SEC) -> int | None:
    """POST /api/canvas/projects（body {}）→ data 按 name 精确匹配 → int id。

    无匹配行返回 None（调用方决定复用/新建/拒绝）。
    """
    envelope = _post_json(base_url, "/api/canvas/projects", {},
                          timeout=timeout)
    rows = envelope.get("data")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("name") == name:
            return int(row["id"])
    return None


def create_project(base_url: str, name: str, intro: str,
                   timeout: float = LIST_TIMEOUT_SEC) -> int:
    """POST /api/project/addProject 建画布项目，回读 projects 按 name 拿新 id。

    11 字段对齐画布「小江湖·逆推资产集(ep01)」行实测取值：projectType/
    type/artStyle/directorManual/videoRatio/imageModel/videoModel/
    imageQuality 空串，name/intro 取实值，mode="canvas-v2"。

    addProject 响应不含 id（kap src/routes/project/addProject.ts:44 只返
    {message:"新增项目成功"}）—— 建完必须回读 /api/canvas/projects 按 name
    再匹配；仍找不到 → sys.exit（fail-loud，不让调用方拿假 id 去 import）。
    """
    payload = {
        "projectType": "",
        "name": name,
        "intro": intro,
        "type": "",
        "artStyle": "",
        "directorManual": "",
        "videoRatio": "",
        "imageModel": "",
        "videoModel": "",
        "imageQuality": "",
        "mode": "canvas-v2",
    }
    _post_json(base_url, "/api/project/addProject", payload, timeout=timeout)
    project_id = find_project(base_url, name, timeout=timeout)
    if project_id is None:
        sys.exit(f"[canvas-import] 项目已提交创建但回读未找到: {name!r}\n"
                 f"  （kap addProject 响应不含 id，本脚本依赖回读 "
                 f"/api/canvas/projects 按 name 匹配；请检查 name 是否含"
                 f"不可见字符或被画布端改名）")
    return project_id


def run_import(base_url: str, project_id: int, episodes_id: int,
               workdir: str, mode: str,
               timeout: float = IMPORT_TIMEOUT_SEC) -> dict:
    """POST /api/canvas/v2/import-from-dir —— 把 workdir 资产目录导入画布项目。

    projectId/episodesId 必须是 JSON number（zod z.number() 会拒 string）；
    workdir 必须 os.path.abspath（kap 服务端按该路径扫媒体文件，相对路径
    会相对 kap 进程 cwd 解析，毫无意义）。返回 envelope 的 data dict。
    """
    payload = {
        "projectId": int(project_id),
        "episodesId": int(episodes_id),
        "workdir": os.path.abspath(workdir),
        "mode": mode,
    }
    envelope = _post_json(base_url, "/api/canvas/v2/import-from-dir", payload,
                          timeout=timeout)
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


def main():
    """CLI 入口：找项目（→ 复用 / 新建 / 拒绝）→ import → 打印计数摘要。"""
    ap = argparse.ArgumentParser(
        description="画布导入器（output/<video-stem>/ → kap 画布项目；"
                    "按名找/建项目 → POST import-from-dir）")
    ap.add_argument("--asset-dir", required=True,
                    help="资产根目录（output/<video-stem>/，含 asset.json；"
                         "intro 取其 source.video_filename 的 stem）")
    ap.add_argument("--base-url", default="http://127.0.0.1:10588",
                    help="kap 服务基地址（默认 http://127.0.0.1:10588）")
    ap.add_argument("--project-name", required=True,
                    help="画布项目名（与 /api/canvas/projects 行 name 精确匹配"
                         "则复用，否则按 --no-create-project 决定是否新建）")
    ap.add_argument("--episodes-id", type=int, default=1,
                    help="画布 episodes id（默认 1）")
    ap.add_argument("--mode", choices=["merge", "replace"], default="replace",
                    help="导入模式（默认 replace：重复导入幂等覆盖，与画布"
                         "既有 ep01 导入口径一致）")
    ap.add_argument("--no-create-project", action="store_true",
                    help="项目不存在时不新建，直接报错退出"
                         "（缺省允许新建 mode=canvas-v2 项目）")
    args = ap.parse_args()

    asset_dir = os.path.abspath(args.asset_dir)
    if not os.path.isdir(asset_dir):
        sys.exit(f"[canvas-import] 资产目录不存在: {asset_dir}")

    print(f"[canvas-import] 查找画布项目: {args.project_name!r}")
    project_id = find_project(args.base_url, args.project_name)
    if project_id is not None:
        print(f"[canvas-import] 复用已有项目 id={project_id}")
    elif args.no_create_project:
        sys.exit(f"[canvas-import] 项目不存在且指定了 --no-create-project: "
                 f"{args.project_name!r}\n  如需新建请去掉该 flag 后重跑")
    else:
        intro = _episode_intro(asset_dir)
        print(f"[canvas-import] 项目不存在，新建: {args.project_name!r}"
              f"（intro={intro!r}）")
        project_id = create_project(args.base_url, args.project_name, intro)
        print(f"[canvas-import] 新建项目 id={project_id}")

    print(f"[canvas-import] 导入资产目录: {asset_dir}（mode={args.mode}）")
    data = run_import(args.base_url, project_id, args.episodes_id,
                      asset_dir, args.mode)
    print(f"[canvas-import] 导入完成: imported={data.get('imported')} "
          f"links={data.get('links')} artifacts={data.get('artifacts')} "
          f"phases={data.get('phases')} mode={data.get('mode')}")
    print(f"[canvas-import] done: {args.project_name!r} ← {asset_dir}")


if __name__ == "__main__":
    main()
