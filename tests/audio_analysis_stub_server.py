#!/usr/bin/env python3
"""Phase 12 SC#4 本地 stub server —— 把 frozen fixture 当作 POST 响应回给客户端。

仅用于 Plan 12-02 smoke harness（NOT for production；NOT exposed to internet）。
镜像 scripts/serve.py 的 http.server.BaseHTTPRequestHandler 极简风格 —— 不实现
Range（POST 不需要），只回应固定 fixture 字节。

设计要点：
  - 启动时一次性载入 fixture 字节（deterministic + 快；非 per-request IO）。
  - 路由 path 与 Phase 10 ROUTE-01 contract lock 一致：
    /api/production/audio-analysis (NO /v1/)。
  - POST → 200 + fixture body；GET → 405（Phase 10 路由只 define POST /，
    preflight 探测 GET 预期 4xx；任何 HTTP 响应都算 host:port 可达）。
  - 任何其他 path → 404。

用法（被 tests/run_audio_analysis_smoke.sh 后台启动）：
    python3 tests/audio_analysis_stub_server.py \\
        --fixture tests/fixtures/audio_analysis_stub_response_nonempty.json \\
        --port 10591
"""
import argparse
import http.server
import json
import socketserver
import sys
from pathlib import Path


# Phase 10 ROUTE-01 contract lock：mount path /api/production/audio-analysis
# (NO /v1/ per 10-02-SUMMARY:113-117 mount-path flag)
ROUTE_PATH = "/api/production/audio-analysis"


# 全局 fixture 字节 —— startup 时一次性载入（deterministic + 快；非 per-request IO）。
# ThreadingHTTPServer 多线程读这个常量是安全的（read-only after startup）。
_FIXTURE_BYTES: bytes = b""


class StubHandler(http.server.BaseHTTPRequestHandler):
    """POST → 返回 fixture；GET → 405（mirror Phase 10 路由仅 define POST /）。"""

    # HTTP/1.1 + 显式 Content-Length 让 httpx preflight GET 拿到完整响应。
    # Python 3.12 BaseHTTPRequestHandler.send_error + 默认 HTTP/1.0 在某些
    # keep-alive 路径上会让客户端收到 "empty reply"（curl 52）—— 显式构造响应避免之。
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path != ROUTE_PATH:
            body = b'{"code":404,"data":null,"message":"NOT_FOUND"}'
            self.send_response(http.HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = _FIXTURE_BYTES
        self.send_response(http.HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        # Phase 10 路由只 define POST / —— preflight (analysis/call_audio_analysis.py
        # :preflight) 用 GET 探测 host:port 可达性，预期 4xx（404/405）。任何 HTTP
        # 响应都算 "up"（Assumption A3）。显式构造 405 响应 + Content-Length。
        body = b'{"code":405,"data":null,"message":"METHOD_NOT_ALLOWED"}'
        self.send_response(http.HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A002 (BaseHTTPRequestHandler API)
        # 静默默认的 stderr access log（smoke script 自己 print 关键步骤）
        pass


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    """CLI 入口 —— 被 smoke script 后台调用。

    流程：parse args → 载入 + 校验 fixture → ThreadingHTTPServer.serve_forever()。
    """
    global _FIXTURE_BYTES
    ap = argparse.ArgumentParser(
        description="Phase 12 SC#4 stub server (test-only —— returns a frozen fixture)")
    ap.add_argument("--fixture", required=True,
                    help="fixture JSON 路径（POST 响应体；startup 一次性载入）")
    ap.add_argument("--port", type=int, default=10591,
                    help="监听端口（默认 10591，避免与 scripts/serve.py:8765 冲突）")
    ap.add_argument("--host", default="127.0.0.1",
                    help="监听地址（默认 127.0.0.1 —— 仅本机 smoke 用）")
    args = ap.parse_args()

    fixture_path = Path(args.fixture).resolve()
    if not fixture_path.is_file():
        sys.exit(f"fixture not found: {fixture_path}")
    # 载入 + 校验 JSON（早失败：坏 fixture 直接退出，不让 smoke 误判）
    try:
        with open(fixture_path, encoding="utf-8") as f:
            json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"fixture JSON parse failed: {e}")
    _FIXTURE_BYTES = fixture_path.read_bytes()

    server = ThreadingHTTPServer((args.host, args.port), StubHandler)
    # flush=True 让 smoke script 的 log 轮询立即看见 ready 标记（避免 block-buffer 延迟）
    print(f"[stub] listening on http://{args.host}:{args.port}{ROUTE_PATH} "
          f"(fixture: {fixture_path})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
