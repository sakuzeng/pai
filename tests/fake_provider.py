"""本地假 provider：说 OpenAI 兼容协议，按脚本回放。

与 `fake_llm.py` 的分工是硬的：

- `fake_llm.FakeClient` —— **注入**的假客户端，测装配与逻辑（747 条测试用的是它）；
- 本模块 —— **起一个真 HTTP 服务**，让真 pai 进程通过 `PAI_BASE_URL` 打进来，
  于是走的是真实的整条路：真 HTTP → 真 SSE 解析 → 真 `streaming.assemble`
  → 真 gate → 真 TUI。

**为什么非要这一段**：feature 12 被用户打回的三条 bug（回答不上屏、权限框在
raw mode 下卡死、排版满屏阶梯）**全部需要一个真实的模型回合**才会暴露，
而那正是 `FakeClient` 够不着、冒烟脚本又为了省钱绕开的地方
（features/14 复盘：「为了省钱而绕开的路径，正是唯一没被验过的路径」）。

SSE 的字节形状照 **实测** 来（K streaming/streaming-tool-calls.md）：
`tool_calls` 按 `index` 归并、`id`/`name` 只在首块、`arguments` 逐字符分片、
**usage 在末块且 `choices` 非空**（D#58：`include_usage` 在 DeepSeek 上是空操作）。
照文档写的话，pai 的解析器会被一个它在真实环境里遇不到的形状喂出假绿。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable, List, Optional

MODEL = "fake-model"


def turn(content: str = "", tool_calls: Optional[List[dict]] = None,
         delay: float = 0.0) -> dict:
    """脚本里的一轮 assistant 响应。

    `tool_calls` 用人话写：`[{"name": "bash", "arguments": {"command": "ls"}}]`，
    序列化成协议形状（`arguments` 是 **JSON 字符串**）由本模块负责——
    那正是真实 provider 的形状，也是编的字符串测不出来的坑之一。

    `delay` = **每个字符之间**停多久（秒）。默认 0：绝大多数 e2e 只想要「秒答」。
    feature 18 加的：假 provider 秒答时「模型正在答」这个状态**根本不存在**，
    于是「干活期间打字」在不调工具的轮次上没有任何窗口可测——
    第一版 e2e 因此假绿（屏幕上两个「用时」= 那条消息其实是当新一轮发的）。
    逐字符停顿是对的做法而不是整轮停顿：TUI 靠**每个事件**顺手 poll 一次键盘，
    整轮停顿期间一个事件都不发，键还是读不到。
    """
    return {"content": content, "tool_calls": tool_calls or [], "delay": delay}


def _sse(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n"


def _chunks(item: dict) -> Iterable[bytes]:
    """把一轮响应拆成与真实 provider 同形的 SSE 块。"""
    base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": MODEL}

    def frame(delta: dict, finish=None, usage=None) -> bytes:
        payload = dict(base, choices=[{"index": 0, "delta": delta,
                                       "finish_reason": finish}])
        if usage is not None:
            payload["usage"] = usage
        return _sse(payload)

    delay = item.get("delay") or 0.0
    yield frame({"role": "assistant", "content": ""})
    for char in item.get("content") or "":
        if delay:
            time.sleep(delay)
        yield frame({"content": char})           # 逐字符：真实流式就是这么切的

    for index, call in enumerate(item.get("tool_calls") or []):
        arguments = json.dumps(call.get("arguments") or {}, ensure_ascii=False)
        # id / name 只在首块给，之后只有 arguments 分片——实测形状
        yield frame({"tool_calls": [{"index": index, "id": f"call_fake_{index}",
                                     "type": "function",
                                     "function": {"name": call["name"],
                                                  "arguments": ""}}]})
        for piece in arguments:
            yield frame({"tool_calls": [{"index": index,
                                         "function": {"arguments": piece}}]})

    finish = "tool_calls" if item.get("tool_calls") else "stop"
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    yield frame({}, finish=finish, usage=usage)   # usage 在末块且 choices 非空
    yield b"data: [DONE]\n\n"


def _blocking(item: dict) -> dict:
    """非流式响应（召回的侧查询走这条）。"""
    message = {"role": "assistant", "content": item.get("content") or ""}
    calls = item.get("tool_calls") or []
    if calls:
        message["tool_calls"] = [
            {"id": f"call_fake_{i}", "type": "function",
             "function": {"name": c["name"],
                          "arguments": json.dumps(c.get("arguments") or {},
                                                  ensure_ascii=False)}}
            for i, c in enumerate(calls)]
    return {"id": "chatcmpl-fake", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                      "total_tokens": 120}}


class FakeProvider:
    """`with FakeProvider(script) as p:` → `p.base_url`。

    脚本用完之后一律回一句兜底文本——**不抛 500**：
    脚本比真实轮数短是常态（比如 loop 因为别的原因多问了一轮），
    让它 500 会把「脚本没写够」伪装成「pai 崩了」。
    """

    def __init__(self, script: List[dict], *, exhausted: str = "（脚本已用完）") -> None:
        self.script = list(script)
        self.exhausted = exhausted
        self.requests: List[dict] = []
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    def _next(self) -> dict:
        with self._lock:
            return self.script.pop(0) if self.script else turn(self.exhausted)

    # --- 生命周期 -----------------------------------------------------

    def start(self) -> "FakeProvider":
        provider = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):          # 别把测试输出淹了
                pass

            def do_POST(self):                      # noqa: N802 - BaseHTTPRequestHandler 的约定
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                provider.requests.append(body)
                item = provider._next()
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for chunk in _chunks(item):
                        self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
                else:
                    payload = json.dumps(_blocking(item), ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "FakeProvider":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()
