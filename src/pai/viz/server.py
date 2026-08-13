"""pai-viz 的本地 HTTP server。零依赖:stdlib http.server。

/api/structure 每次都起子进程跑 collect——不是偷懒,是设计:
server 常驻进程里模块有 import 缓存,新加的 @tool 刷不出来;
新解释器现场收集(约 100-200ms)才能保证「改完代码刷新即现」。
附赠隔离性:用户代码写挂了,子进程报错显示在页面上,server 不死。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from pai.core.paths import projects_root, sessions_dir
from pai.viz.flow import events_path_for, load_flow

# 仓库根：reveal 的边界。server.py 在 src/pai/viz/ 下，上溯三层。
REPO_ROOT = Path(__file__).resolve().parents[3]


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


def _session_files() -> list:
    """**所有项目**的会话文件，mtime 新→旧。`.events.jsonl` 不是会话，不占一行。

    为什么跨项目：会话目录按 cwd 分（`~/.pai/projects/<slug>/sessions/`），而
    `pai` 与 `pai-viz` 常常不在同一个目录起——AGENTS.md 要求手工冒烟在
    `pai_playground/` 里做，viz 却多半在仓库根开。只看 cwd 那个项目的话，
    页面会说「还没有会话文件」，而人明明刚跑过（用户 2026-08-13 实测撞到）。
    """
    root = projects_root()
    if not root.exists():
        return []
    files = [p for p in root.glob("*/sessions/*.jsonl")
             if not p.name.endswith(".events.jsonl")]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _project_of(path: Path) -> str:
    return path.parent.parent.name          # <projects>/<slug>/sessions/<file>


def list_sessions() -> dict:
    current = ""
    try:
        current = sessions_dir().parent.name
    except OSError:
        pass
    return {"sessions": [
        {"name": p.name, "project": _project_of(p),
         "id": f"{_project_of(p)}/{p.name}",   # 撞名时用它，见 _resolve_session
         "mtime": p.stat().st_mtime, "size": p.stat().st_size,
         "current": _project_of(p) == current,
         "has_events": events_path_for(p).exists()}
        for p in _session_files()
    ]}


def _resolve_session(name: str) -> "tuple[Path | None, str]":
    """会话标识 → 路径。返回 (路径, 错误说明)。

    接受两种写法：`<文件名>`（在所有项目里找，够用因为文件名带时间戳+短 id）
    与 `<项目>/<文件名>`（撞名时用）。

    **这是路径注入面**：不挡的话 `../../../etc/passwd` 会被原样拼进去。
    放宽成两段之后更要挡——两段都必须是**纯文件名**（`Path(x).name == x`），
    再 resolve 后校验确实落在 projects 根内。
    """
    root = projects_root()
    if not name or name == "latest":
        files = _session_files()
        if not files:
            return None, f"{root} 下还没有会话文件（先跑一次 pai）"
        return files[0], ""

    parts = name.split("/")
    if len(parts) > 2 or any(p != Path(p).name or not p for p in parts):
        return None, f"会话名不合法：{name}"
    if len(parts) == 2:
        target = (root / parts[0] / "sessions" / parts[1]).resolve()
        candidates = [target] if target.is_file() else []
    else:
        candidates = [p for p in _session_files() if p.name == parts[0]]
    if not candidates:
        return None, f"找不到会话：{name}"
    hit = candidates[0].resolve()
    if root.resolve() not in hit.parents:          # 兜底：绝不越出 projects 根
        return None, f"会话名不合法：{name}"
    return hit, ""


def flow_payload(name: str) -> dict:
    path, error = _resolve_session(name)
    if path is None:
        return {"turns": [], "error": error, "session": name}
    payload = load_flow(path)
    payload["error"] = ""
    return payload


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))


def _tail(path: Path, start: int) -> list:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i < start or not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass                     # 半行照旧跳过，不因它中断增量
    return out


def events_since(name: str, cursor: str) -> dict:
    """游标之后的新记录，两个流按 ts 归并。

    游标形如 `"<审计行数>:<观测行数>"`。**给不出合法游标就只回当前行数、不回历史**
    ——页面刚打开不该把整天的事件闪一遍（waku `events_since` 同款语义）。
    游标来自客户端，任何形状都不能让它 500。
    """
    path, error = _resolve_session(name)
    if path is None:
        return {"records": [], "cursor": "0:0", "error": error, "session": ""}
    ev_path = events_path_for(path)
    rows, evs = _line_count(path), _line_count(ev_path)

    parts = (cursor or "").split(":")
    if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
        return {"records": [], "cursor": f"{rows}:{evs}", "error": "", "session": path.name}
    a, b = int(parts[0]), int(parts[1])
    if not (0 <= a <= rows and 0 <= b <= evs):
        # 文件被换掉/清空（新会话开始）：重新对齐，不回历史。
        # **`session` 字段是这条分支的关键**——真跑时发现：新起一次 pai 就换了文件，
        # 页面盯着 latest 却拿到 0 条，看起来像「什么都没发生」，实际全新回合正在跑。
        # 带回会话名，前端一比对就知道该重载时间线（devlog T5）。
        return {"records": [], "cursor": f"{rows}:{evs}", "error": "", "session": path.name}

    records = _tail(path, a) + _tail(ev_path, b)
    records.sort(key=lambda r: r.get("ts") or 0.0)
    return {"records": records, "cursor": f"{rows}:{evs}", "error": "",
            "session": path.name}


def _editor_cmd() -> "list | None":
    """用户的编辑器 CLI：$PAI_EDITOR，然后 cursor，然后 code。"""
    import os

    custom = os.getenv("PAI_EDITOR")
    if custom and shutil.which(custom):
        return [custom]
    for cli in ("cursor", "code"):
        if shutil.which(cli):
            return [cli]
    return None


# macOS 上 `code`/`cursor` 的 CLI 默认**不在 PATH**（要手动装 shell command），
# 但 URL scheme 一定能用，而且它跳到**已经打开的那个窗口**——正是「我已经用
# VS Code 开着项目，点一下跳过去」要的效果。所以 CLI 找不到不算失败，降级到它。
_EDITOR_APPS = [("Visual Studio Code", "vscode"), ("Cursor", "cursor")]


def _installed_editor_scheme() -> "str | None":
    """装了哪个编辑器 → 它的 URL scheme。`$PAI_EDITOR_SCHEME` 可强制指定。"""
    import os
    import sys

    forced = os.getenv("PAI_EDITOR_SCHEME")
    if forced:
        return forced
    if sys.platform != "darwin":
        return None                      # 只有 macOS 的 `open` 认 URL scheme
    for app, scheme in _EDITOR_APPS:
        if Path(f"/Applications/{app}.app").exists():
            return scheme
    return None


def reveal(rel: str, line: str = "") -> dict:
    """在编辑器里打开仓库内的一个文件。页面上**唯一**会执行本机命令的端点，
    所以三道闸门都不能省：路径 resolve 后必须在仓库内、只认 PATH 上的
    cursor/code、argv 列表直接 exec **不过 shell**。
    """
    if not rel:
        return {"error": "没给路径"}
    target = (REPO_ROOT / rel).resolve()
    if target != REPO_ROOT and REPO_ROOT not in target.parents:
        return {"error": f"路径在仓库之外，不给开：{rel}"}
    if not target.is_file():
        return {"error": f"文件不存在：{target}"}
    editor = _editor_cmd()
    if editor is not None:
        where = f"{target}:{line}" if line.isdigit() else str(target)
        subprocess.run([*editor, "--goto", where] if line.isdigit() else [*editor, str(target)],
                       check=False)
        return {"ok": True, "opened_in": editor[0], "path": str(target)}

    scheme = _installed_editor_scheme()
    if scheme is not None:
        url = f"{scheme}://file{target}" + (f":{line}" if line.isdigit() else "")
        subprocess.run(["open", url], check=False)
        return {"ok": True, "opened_in": scheme, "path": str(target)}

    return {"error": f"没找到编辑器（可设 PAI_EDITOR 或 PAI_EDITOR_SCHEME）。路径是 {target}"}


class VizHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 的命名约定
        route = urlparse(self.path)
        query = parse_qs(route.query)

        def arg(key: str, default: str = "") -> str:
            return unquote(query.get(key, [default])[0])

        if route.path == "/":
            self._send(200, "text/html; charset=utf-8", _index_html())
        elif route.path == "/api/structure":
            # 结构图仍走子进程（为的是 @tool 的 import 缓存，见模块 docstring）；
            # 下面几个都是读 JSONL 文件，没有缓存问题，进程内直读即可
            code, body = _collect()
            self._send(code, "application/json; charset=utf-8", body)
        elif route.path == "/api/sessions":
            self._json(list_sessions())
        elif route.path == "/api/flow":
            self._json(flow_payload(arg("session", "latest")))
        elif route.path == "/api/events":
            self._json(events_since(arg("session", "latest"), arg("cursor")))
        elif route.path == "/api/reveal":
            self._json(reveal(arg("path"), arg("line")))
        else:
            self._send(404, "text/plain; charset=utf-8", "not found".encode())

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self._send(200, "application/json; charset=utf-8", body)

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
