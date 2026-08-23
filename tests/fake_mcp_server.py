#!/usr/bin/env python3
"""测试用零依赖 stdio MCP server（feature 29；血统：动工前反向对照的探针 server）。

newline-delimited JSON-RPC。行为由环境变量参数化，让一个脚本覆盖协议层的全部
测试形态——子进程夹具不好传参，env 是最直的通道：

- FAKE_MCP_MODE=normal|die-after-init|slow-call|dirty-stdout|paginate
- FAKE_MCP_SLOW_SECONDS：slow-call 模式下 tools/call 的延迟（默认 5）
"""
import json
import os
import sys
import time

MODE = os.environ.get("FAKE_MCP_MODE", "normal")
SLOW = float(os.environ.get("FAKE_MCP_SLOW_SECONDS", "5"))

TOOLS_PAGE_1 = [
    {
        "name": "echo_token",
        "description": "返回固定暗号。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "always_fails",
        "description": "永远返回 isError 的工具。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]
TOOLS_PAGE_2 = [
    {
        "name": "page_two_tool",
        "description": "分页第二页的工具。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def send(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    msg = json.loads(raw)
    method = msg.get("method", "")
    if "id" not in msg:
        continue                              # notification
    if MODE == "dirty-stdout":
        # server 往 stdout 打日志是常见事故：协议行前后夹杂垃圾行
        sys.stdout.write("log: something noisy\n")
        sys.stdout.flush()
    if MODE == "bad-id-noise":
        # 恶意/坏 server：合法 JSON 但 id 是 unhashable 的 list（29 复核低 1）
        send({"jsonrpc": "2.0", "id": [1], "result": {}})
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp", "version": "0.1"},
        }})
        if MODE == "die-after-init":
            sys.exit(0)
    elif method == "tools/list":
        if MODE == "die-after-list":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS_PAGE_1}})
            sys.exit(0)
        if MODE == "paginate":
            cursor = msg.get("params", {}).get("cursor")
            if cursor == "p2":
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "result": {"tools": TOOLS_PAGE_2}})
            else:
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "result": {"tools": TOOLS_PAGE_1, "nextCursor": "p2"}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS_PAGE_1}})
    elif method == "tools/call":
        name = msg["params"].get("name", "")
        if MODE == "slow-call":
            time.sleep(SLOW)
        if name == "echo_token":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": "FAKE-MCP-TOKEN-4711"},
                            {"type": "text", "text": "第二个文本块"},
                            {"type": "image", "mimeType": "image/png", "data": "x"}]}})
        elif name == "always_fails":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "isError": True,
                "content": [{"type": "text", "text": "FAKE-FAILURE-8181"}]}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"],
                  "error": {"code": -32602, "message": f"unknown tool {name}"}})
    else:
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
