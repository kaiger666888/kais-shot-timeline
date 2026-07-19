#!/usr/bin/env python3
"""支持 HTTP Range 请求的最小静态文件 server（给 timeline.html 用）。

背景：python3 -m http.server 在某些发行版（Ubuntu/Debian）上不识别 Range 头，
返回 200 OK 而非 206 Partial Content。浏览器 <video> seek 到后期位置时会失败，
表现为"第一个分镜能播、后面 seek 回 0"。

用法：
    python3 scripts/serve.py [dir] [port]
    # 默认 dir=. port=8765
"""
import http.server
import os
import socketserver
import sys
import urllib.parse


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):

    def send_head(self):
        # 复刻 SimpleHTTPRequestHandler.send_head，但把 get搞得能处理 Range。
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            for index in ("index.html", "index.htm"):
                index_path = os.path.join(path, index)
                if os.path.exists(index_path):
                    path = index_path
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(http.HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            total = os.fstat(f.fileno()).st_size
        except OSError:
            total = 0

        # 处理 Range
        range_header = self.headers.get("Range")
        start, end = 0, total - 1
        partial = False
        if range_header and range_header.startswith("bytes="):
            spec = range_header[6:].split("-")
            try:
                if spec[0]:
                    start = int(spec[0])
                if len(spec) > 1 and spec[1]:
                    end = int(spec[1])
                if end >= total:
                    end = total - 1
                if start > end or start >= total:
                    self.send_error(416, "Requested range not satisfiable")
                    f.close()
                    return None
                partial = True
            except ValueError:
                partial = False

        if partial:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(total))
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", ctype)
        self.send_header("Last-Modified",
                         self.date_time_string(os.fstat(f.fileno()).st_mtime))
        self.end_headers()

        if start > 0:
            f.seek(start)
        remaining = end - start + 1
        chunk_size = 64 * 1024

        class _Partial:
            def read(self, _n=None):
                nonlocal remaining
                if remaining <= 0:
                    return b""
                n = min(chunk_size, remaining)
                data = f.read(n)
                remaining -= len(data)
                return data

        # 返回一个能 read 的对象，SimpleHTTPRequestHandler 用 wfile.copyfile
        return _Partial() if partial else f


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    if len(sys.argv) >= 2:
        os.chdir(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) >= 3 else 8765
    server = ThreadingHTTPServer(("0.0.0.0", port), RangeRequestHandler)
    print(f"[serve] http://localhost:{port}/  cwd={os.getcwd()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] bye")


if __name__ == "__main__":
    main()
