"""pai-viz 的本地 HTTP server。零依赖:stdlib http.server。

/api/structure 每次都起子进程跑 collect——不是偷懒,是设计:
server 常驻进程里模块有 import 缓存,新加的 @tool 刷不出来;
新解释器现场收集(约 100-200ms)才能保证「改完代码刷新即现」。
附赠隔离性:用户代码写挂了,子进程报错显示在页面上,server 不死。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources


def _index_html() -> bytes:
    # 3.9 起可用 files();HTML 与代码同包分发(pyproject 的 package-data)
    return resources.files("pai.viz").joinpath("index.html").read_bytes()


def _collect() -> "tuple[int, bytes]":
    """跑子进程收集,返回 (http状态码, body)。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pai.viz.collect"],
            capture_output=True, timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        # 超时前子进程可能已经写出了部分 stderr(比如卡在某个耗时调用之前先报了别的错)
        # ——丢掉这条线索会让「为什么超时」完全无从排查;stderr 在还没写任何内容时是 None。
        stderr = (e.stderr or b"").decode("utf-8", errors="replace")
        msg = "collect 子进程超时(30s)"
        if stderr:
            msg += ":\n" + stderr
        return 500, json.dumps({"error": msg}, ensure_ascii=False).encode()
    if proc.returncode == 0:
        # returncode==0 不代表 stdout 是干净的 JSON:import 路径上一句杂散 print()
        # (比如某依赖库的调试输出)会把 JSON 弄脏,不校验的话前端只会看到一个不知所云的
        # JSON.parse 报错,查不到真因。这里提前校验,把原始 stdout 带回去方便定位。
        try:
            json.loads(proc.stdout)
        except json.JSONDecodeError:
            return 500, json.dumps(
                {
                    "error": "collect 输出不是合法 JSON(可能有 print 之类混入 stdout):\n"
                    + proc.stdout.decode("utf-8", errors="replace")
                },
                ensure_ascii=False,
            ).encode()
        return 200, proc.stdout
    # stderr 原样透传给页面:让语法错误之类的问题直接可见,顺手当编译检查
    return 500, json.dumps(
        {"error": proc.stderr.decode("utf-8", errors="replace")}, ensure_ascii=False
    ).encode()


class VizHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 的命名约定
        if self.path == "/":
            self._send(200, "text/html; charset=utf-8", _index_html())
        elif self.path == "/api/structure":
            code, body = _collect()
            self._send(code, "application/json; charset=utf-8", body)
        else:
            self._send(404, "text/plain; charset=utf-8", "not found".encode())

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 静音默认访问日志,终端只留有用信息
        pass


def make_server(port: int = 7777) -> ThreadingHTTPServer:
    """只建不跑:测试用 port=0 拿随机端口,main() 用默认端口。"""
    return ThreadingHTTPServer(("127.0.0.1", port), VizHandler)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pai-viz", description="pai 架构可视化(本地网页)")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    try:
        httpd = make_server(port=args.port)
    except OSError as e:
        sys.exit(f"端口 {args.port} 起不来({e}),用 --port 换一个")

    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"pai-viz 就绪:{url}(Ctrl+C 停止)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
