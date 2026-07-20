#!/usr/bin/env python3
"""Range-206 自检：启动 scripts/serve.py → 发 Range 请求 → 断言 206/Content-Range/Accept-Ranges。

背景：scripts/serve.py 是 EXPORT-03 的 reference impl —— 必须对 Range 请求返回
206 Partial Content + Content-Range + Accept-Ranges 三件套，消费端 stem/视频 seek
才不会重传整文件。本脚本作为 SC-3「206 Partial Content responses observed」的
机器可检证据，并成为 Phase 4 回归 harness 的基础。

为什么不用 curl：stdlib-only 可移植，避免外部依赖。urllib.request.Request 支持
自定义 headers，足以发出 Range 请求并解析 status/headers/body。

用法：
    python3 scripts/check_range.py                  # 自动扫 output/ 下第一个含 video.mp4 的子目录
    python3 scripts/check_range.py <asset_root>     # 显式指定 asset 目录（必须含 video.mp4）

退出码：
    0 = 自检通过（206 + Content-Range + Accept-Ranges + 1024 字节 body 全 pass）
    1 = 自检失败（任一不变量 fail / server 未启动 / 目录无效）
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()  # scripts/ → repo root


def find_free_port() -> int:
    """让内核分配一个空闲的 ephemeral 端口（bind 127.0.0.1:0 后读 getsockname）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(port: int, timeout: float = 5.0) -> bool:
    """轮询 TCP 连接到 port；连上即 server ready，超时返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def check(asset_root: str) -> int:
    """对 asset_root 启动 serve.py + Range 请求 + 断言 4 条不变量。返回 0/1。

    不变量：
      - HTTP status == 206
      - Content-Range 以 "bytes 0-1023/" 起始
      - Accept-Ranges == "bytes"
      - body 长度 == 1024 字节

    任何异常路径（含 KeyboardInterrupt）都通过 try/finally 保证 serve.py 子进程被 terminate。
    """
    video_path = os.path.join(asset_root, "video.mp4")
    if not os.path.exists(video_path):
        print(f"[check-range] no video.mp4 in {asset_root} — nothing to probe")
        return 1

    port = find_free_port()
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / "serve.py"), asset_root, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_ready(port):
            print(f"[check-range] FAIL: server did not start on port {port} "
                  f"(check scripts/serve.py for import/startup errors)")
            return 1

        url = f"http://127.0.0.1:{port}/video.mp4"
        req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_range = resp.headers.get("Content-Range")
            accept_ranges = resp.headers.get("Accept-Ranges")
            body = resp.read()

        ok = True
        if status != 206:
            print(f"[check-range] FAIL: expected 206, got {status}")
            ok = False
        if not content_range or not content_range.startswith("bytes 0-1023/"):
            print(f"[check-range] FAIL: bad Content-Range: {content_range!r}")
            ok = False
        if accept_ranges != "bytes":
            print(f"[check-range] FAIL: bad Accept-Ranges: {accept_ranges!r}")
            ok = False
        if len(body) != 1024:
            print(f"[check-range] FAIL: expected 1024-byte body, got {len(body)}")
            ok = False
        if ok:
            print(f"[check-range] OK: 206 + Content-Range={content_range} "
                  f"+ Accept-Ranges=bytes + 1024-byte body")
        return 0 if ok else 1
    finally:
        # 沿用 audio/transcribe.py:150-155 的 finally cleanup 惯例：任何异常都要释放子进程
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            # 02-REVIEW WR-06：kill 后必须 wait 收尸 —— 否则 SIGKILL'd 子进程在 Linux
            # 上变 zombie，直到父进程退出才被 init 收养。Phase 4 回归 harness 在循环
            # 里多次调 check()，zombie 会累积。best-effort：仍超时只能放弃（kernel
            # 在父进程退出时 reap）。
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass


def main():
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="Range-206 自检：启动 serve.py → Range 请求 → assert 206/Content-Range/Accept-Ranges"
    )
    ap.add_argument(
        "asset_root",
        nargs="?",
        default=None,
        help="asset 目录（含 video.mp4）；缺省时自动扫 output/ 下第一个含 video.mp4 的子目录",
    )
    args = ap.parse_args()

    asset_root = args.asset_root
    if asset_root is None:
        # 自动扫 output/ 找第一个含 video.mp4 的子目录
        output_root = REPO / "output"
        if not output_root.is_dir():
            sys.exit(
                f"[check-range] no asset_root given and {output_root} does not exist — "
                f"run pipeline first or pass asset_root positional arg"
            )
        for child in sorted(output_root.iterdir()):
            if child.is_dir() and (child / "video.mp4").exists():
                asset_root = str(child)
                break
        if asset_root is None:
            sys.exit(
                f"[check-range] no asset_root given and no output/*/video.mp4 found — "
                f"run pipeline first or pass asset_root positional arg"
            )

    sys.exit(check(asset_root))


if __name__ == "__main__":
    main()
