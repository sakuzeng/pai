"""MCP client：把外部 MCP server 的工具桥接进 pai 的工具注册表（feature 29）。

拍板四问全 A（features/29 README）：Tools only + 仅 stdio；手写 JSON-RPC
（newline-delimited，不引官方 SDK——dsh 被 SDK 隐式校验缓存咬过的 D4 教训 +
学习价值）；权限默认 ask（落既有兜底「未声明路径语义→ask」，CC 同构）；
配置在 settings.json 的 `mcpServers` 段。

三家对照见 knowledge/mcp/ 四篇。本模块只做协议与桥接（纯逻辑 + 子进程），
不 import loop 内部；装配在 modes 层。协议层错误是异常（MCPError），
到桥接层一律转成字符串回填——「工具错误不 throw」的架构约束在 loop 侧成立。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import unicodedata
from typing import Callable, Dict, List, Optional

from pai.core.tools import Tool

PROTOCOL_VERSION = "2025-06-18"

# 连接 + 发现的整体超时。CC 是 30s（MCP_TIMEOUT 默认）；pai v1 只有本地 stdio，
# 10s 足够起一个脚本。未实测校准。
CONNECT_TIMEOUT_MS = 10_000

# 每次工具调用的默认超时。取 dsh 的 toolCallTimeoutMs 默认值（60s）；
# CC 的默认是约 28 小时（有意近乎无限），对 pai 是挂死源，不抄。
DEFAULT_CALL_TIMEOUT_MS = 60_000

# 每条 description 的截断上限（CC 2.1.88 同值；它见过 OpenAPI 生成的 server
# 往 description 里倒 15-60KB 文档）。外部 description 是不可信输入。
MAX_MCP_DESC_CHARS = 2048

# 单次工具输出的字符预算。CC 的 25k token × 4 字符换算，未实测校准
# （与 skills 的 REATTACH_* 同一类「借来的经验值」）。超限截断不落盘（落盘记遗留）。
MAX_MCP_OUTPUT_CHARS = 100_000

# 公开名上限与 hash 兜底长度（dsh 同值：64 字符是 DeepSeek 工具名约定）。
_MAX_PUBLIC_NAME = 64
_HASH_LEN = 12

_NAME_BAD = re.compile(r"[^a-z0-9_-]")


class MCPError(Exception):
    """协议层的所有失败面：连不上、超时、进程死、JSON-RPC error、isError。

    只在 core/mcp.py 内部与桥接层之间流动——桥接出的 Tool 会把它转成
    `错误：...` 字符串返回，loop 永远看不到这个异常。
    """


def _text_of(content: object) -> str:
    """content 数组里 text 块拼接（错误细节与结果映射共用）。"""
    if not isinstance(content, list):
        return ""
    texts = [b.get("text", "") for b in content
             if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(t for t in texts if t)


class MCPSession:
    """一个 stdio MCP server 的会话：显式状态机，不做隐式重连。

    状态：connecting → connected → failed/closed。刻意不抄 CC 的
    「memoize 连接池 + 删缓存触发重连」（其作者自留 TODO 怀疑复杂度）；
    也不做重连（拍板问 1 范围）：进程死 = failed，后续调用立刻报错，
    错误经桥接回填给模型（pi 式「摘除胜过半吊子重连」）。
    close() 幂等（pi 的 shutdown 契约）。
    """

    def __init__(self, name: str, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None,
                 call_timeout_ms: int = DEFAULT_CALL_TIMEOUT_MS) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.call_timeout_ms = call_timeout_ms
        self.state = "connecting"
        self.tools: List[dict] = []           # tools/list 的原始条目（未桥接）
        self._proc: Optional[subprocess.Popen] = None
        self._next_id = 0
        self._lock = threading.Lock()         # id 分配 + pending 表
        # 写管道单独一把锁（29 复核低 2）：当前调度对 MCP 工具串行（未声明
        # concurrency_safe），这把锁是结构保险——将来声明并发时两线程写 stdin
        # 不会字节交错损坏协议。与 _lock 分开，避免写管道阻塞 reader 的配对查表。
        self._write_lock = threading.Lock()
        self._pending: Dict[int, dict] = {}   # id -> {"event": Event, "reply": msg}
        self._reader: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- 生命周期

    def start(self) -> None:
        """spawn + initialize 握手 + tools/list（drain 分页）。失败抛 MCPError。"""
        import os
        try:
            self._proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # stderr 单独排走不进 UI（CC 同款）；丢弃而非缓存——v1 不做
                # stderr 转录，server 的日志去它自己的文件
                stderr=subprocess.DEVNULL,
                env={**os.environ, **self.env},
            )
        except OSError as e:
            self.state = "failed"
            raise MCPError(f"MCP server `{self.name}` 起不来：{e}")
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        try:
            init = self._request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                # 空对象 = 不声明任何客户端能力（dsh 同款）：服务器在协议层
                # 就知道不能反向发起 sampling/roots/elicitation
                "capabilities": {},
                "clientInfo": {"name": "pai", "version": "0"},
            }, timeout_ms=CONNECT_TIMEOUT_MS)
            self._notify("notifications/initialized")
            cursor: Optional[str] = None
            while True:
                params = {"cursor": cursor} if cursor else {}
                page = self._request("tools/list", params,
                                     timeout_ms=CONNECT_TIMEOUT_MS)
                self.tools.extend(page.get("tools", []))
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            _ = init                          # 协议版本不校验：v1 收什么认什么
            self.state = "connected"
        except MCPError:
            self.state = "failed"
            self.close()
            self.state = "failed"             # close() 会置 closed，失败语义优先
            raise

    def close(self) -> None:
        """幂等关闭：SIGTERM 起步，0.5s 不退 SIGKILL。

        CC 的 SIGINT→SIGTERM 升级是给 Docker 容器 server 的；pai v1 只有
        本地脚本，SIGTERM 起步足够，真撞到再升级。
        """
        if self.state == "closed":
            return
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        self._fail_pending("server 已关闭")
        self.state = "closed"

    # ---------------------------------------------------------------- 调用

    def call_tool(self, raw_name: str, arguments: dict,
                  timeout_ms: Optional[int] = None) -> dict:
        """tools/call。线上永远走 raw name（三家一致，evidence P1 实证）。

        isError: true 在协议层也是异常——错误细节取 content 的 text 拼接，
        转字符串的职责在桥接层。timeout 不传时用本 session 的配置值
        （settings 的 `timeout` 字段一路传到这里）。
        """
        result = self._request("tools/call",
                               {"name": raw_name, "arguments": arguments},
                               timeout_ms=timeout_ms if timeout_ms is not None
                               else self.call_timeout_ms)
        if result.get("isError") is True:
            detail = _text_of(result.get("content")) or "（server 未给出错误细节）"
            raise MCPError(f"MCP 工具 `{raw_name}` 返回错误：{detail}")
        return result

    # ---------------------------------------------------------------- 传输

    def _read_loop(self) -> None:
        """后台线程：逐行读 stdout，按 id 配对；非 JSON 行丢弃（server 往
        stdout 打日志是常见事故，不能炸）；EOF = 进程死，唤醒所有挂起请求。"""
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        for raw in proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(msg, dict) or "id" not in msg:
                continue                      # server 端 notification：v1 忽略
            if not isinstance(msg["id"], (int, str)):
                # 29 复核低 1：`"id": [1]` 这类 unhashable id 会让 dict.get 抛
                # TypeError 弄死 reader——之后所有调用退化成超时挂等。丢弃该行。
                continue
            with self._lock:
                slot = self._pending.get(msg["id"])
            if slot is not None:
                slot["reply"] = msg
                slot["event"].set()
        if self.state == "connected":
            self.state = "failed"
        self._fail_pending("server 进程已退出")

    def _fail_pending(self, reason: str) -> None:
        with self._lock:
            slots = list(self._pending.values())
            self._pending.clear()
        for slot in slots:
            slot["reason"] = reason
            slot["event"].set()

    def _send(self, obj: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise MCPError(f"MCP server `{self.name}` 已退出，无法发送请求")
        try:
            with self._write_lock:
                proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
                proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.state = "failed"
            raise MCPError(f"MCP server `{self.name}` 管道已断（进程退出）")

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict, *, timeout_ms: int) -> dict:
        event = threading.Event()
        slot: dict = {"event": event, "reply": None, "reason": None}
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            self._pending[req_id] = slot
        try:
            self._send({"jsonrpc": "2.0", "id": req_id,
                        "method": method, "params": params})
            if not event.wait(timeout_ms / 1000):
                raise MCPError(
                    f"MCP server `{self.name}` 的 {method} 超时（{timeout_ms}ms）")
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
        if slot["reply"] is None:
            raise MCPError(f"MCP server `{self.name}` 未应答 {method}："
                           f"{slot['reason'] or '连接中断'}")
        reply = slot["reply"]
        if "error" in reply:
            err = reply["error"]
            raise MCPError(f"MCP server `{self.name}` 对 {method} 报错："
                           f"{err.get('message', err)}")
        return reply.get("result", {})


# ---------------------------------------------------------------- 桥接层

def public_tool_name(server: str, raw: str) -> str:
    """模型可见名：`mcp__<server>__<raw>` 小写化归一。

    超长退化为截断 + `sha256("<server>\\0<raw>")[:12]`（dsh 同款；`\\0` 分隔
    防 `(a, b__x)` 与 `(a__b, x)` 拼接歧义）。调用永远走 raw name——(server, raw)
    存在 Tool 闭包里，绝不从公开名反解字符串（CC 的 split('__') 缺陷引以为戒）。
    小写化是为与权限规则对齐：parse_rule 把规则里的工具名小写化，公开名不跟着
    小写的话 `mcp__srv__*` 这类规则会静默失配。
    """
    joined = f"mcp__{server}__{raw}".lower()
    normalized = _NAME_BAD.sub("_", joined)
    if len(normalized) <= _MAX_PUBLIC_NAME:
        return normalized
    # hash 只兜超长（dsh 对「归一化有改动」也 hash，pai 不抄：归一化撞名走
    # 桥接层的「跳过 + warn」fail loud 路径，比静默换成 hash 名对用户更可见）
    digest = hashlib.sha256(f"{server}\0{raw}".encode("utf-8")).hexdigest()[:_HASH_LEN]
    return f"{normalized[:_MAX_PUBLIC_NAME - _HASH_LEN - 1]}_{digest}"


def _sanitize(text: str) -> str:
    """NFKC 归一 + 剥 Cf/Co/Cn 类别字符（CC 防 HackerOne #3086545 的同款 20 行）：
    Unicode Tag 字符可以往 description 里藏模型可读、人不可见的指令。"""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(c for c in normalized
                   if unicodedata.category(c) not in ("Cf", "Co", "Cn"))


def _sanitize_schema(value: object) -> object:
    """schema 里的字符串值同样过清洗（描述性字段是同一个注入面）。"""
    if isinstance(value, str):
        return _sanitize(value)
    if isinstance(value, list):
        return [_sanitize_schema(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_schema(v) for k, v in value.items()}
    return value


def render_result(tool_name: str, result: dict) -> str:
    """tools/call 结果 → 回填给模型的字符串。

    text 块 `\\n` join（dsh 教训：join('') 静默丢块间边界是正确性缺陷）；
    非 text 块降级为占位符一行——不静默丢，模型该知道有内容被略去
    （落盘回文件路径的 CC 形态记遗留）。超预算截断并留提示。
    """
    parts: List[str] = []
    for block in result.get("content") or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            if block.get("text"):
                parts.append(str(block["text"]))
        else:
            mime = block.get("mimeType", "?")
            parts.append(f"[{kind}: {mime}，内容已略去（v1 不支持非文本内容）]")
    text = "\n".join(parts)
    if not text:
        return f"（{tool_name} 无文本输出）"
    if len(text) > MAX_MCP_OUTPUT_CHARS:
        text = (text[:MAX_MCP_OUTPUT_CHARS]
                + f"\n…（输出超出 {MAX_MCP_OUTPUT_CHARS} 字符预算，已截断）")
    return _sanitize(text)


def bridge_tools(session, *, warn: Callable[[str], None]) -> List[Tool]:
    """把一个 session 的远端工具桥接成 pai 的 Tool 列表。

    这是 @tool 装饰器「schema 与代码同源」约束的显式破例（升格 decisions）：
    parameters 来自外部 tools/list，经 Unicode 清洗后原样透传。归一化后撞名
    的后者跳过 + warn（fail loud）。产出的 Tool 不声明能力（未声明 = 串行 =
    对外部工具正确）、不声明路径也不豁免——兜底 ask（拍板问 3）。
    """
    out: List[Tool] = []
    seen: Dict[str, str] = {}
    for entry in session.tools:
        raw = str(entry.get("name", ""))
        if not raw:
            warn(f"MCP server `{session.name}` 有一个无名工具，已跳过")
            continue
        name = public_tool_name(session.name, raw)
        if name in seen:
            warn(f"MCP 工具 `{raw}`（server `{session.name}`）归一化后与 "
                 f"`{seen[name]}` 同名（{name}），已跳过")
            continue
        seen[name] = raw
        description = _sanitize(str(entry.get("description", "")))[:MAX_MCP_DESC_CHARS]
        parameters = _sanitize_schema(entry.get("inputSchema")
                                      or {"type": "object", "properties": {}})

        def make_runner(session=session, raw=raw, public=name):
            def run(**kwargs) -> str:
                try:
                    result = session.call_tool(raw, kwargs)
                except MCPError as e:
                    # 协议层异常收敛在这里：loop 永远拿到字符串
                    # （AGENTS「工具错误不 throw」）
                    return f"错误：{e}"
                return render_result(public, result)
            return run

        out.append(Tool(name=name, description=description,
                        parameters=parameters, func=make_runner()))
    return out


# ---------------------------------------------------------------- 配置与信任

# server 名合法性（dsh 模式收紧到小写：公开名要与权限规则的小写化约定对齐，
# parse_rule 会把规则里的工具名小写化，大写 server 名会让规则静默失配）
_SERVER_NAME_OK = re.compile(r"^[a-z0-9_-]{1,32}$")

# 项目级 MCP 配置的信任标记（feature 28 模式推广：标记在项目身份目录、
# 不进仓库——检入仓库的 settings.json 能配 server，但塞不进信任标记）
MCP_TRUST_MARKER = "mcp_trusted"


class MCPServerConfig:
    """一条 server 配置（扫描产物，不含运行态）。"""

    def __init__(self, name: str, command: str, args: List[str],
                 env: Dict[str, str], timeout_ms: int, source: str) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.timeout_ms = timeout_ms
        self.source = source                  # "user" | "project"


def _read_servers_layer(path, source: str,
                        warn: Callable[[str], None]) -> List[MCPServerConfig]:
    """读一层 settings.json 的 mcpServers 段。坏文件/坏条目 warn 后跳过，
    pai 照常起（启动路径不崩，与权限层 _read_settings、skills 扫描同一条铁律）。
    两层自读循 hooks.py 先例——项目层要单独过信任门禁，不能用 load_settings
    的预合并结果。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []                             # 没有文件是常态
    try:
        data = json.loads(text)
    except ValueError as e:
        warn(f"设置文件 {path} 不是合法 JSON（{e}），本层 mcpServers 按空处理")
        return []
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return []
    out: List[MCPServerConfig] = []
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            warn(f"MCP server `{name}` 的配置不是对象，已跳过")
            continue
        if not _SERVER_NAME_OK.match(str(name)):
            warn(f"MCP server 名 `{name}` 不合法（小写字母/数字/连字符/下划线，"
                 f"≤32 字符），已跳过")
            continue
        server_type = entry.get("type", "stdio")
        if server_type != "stdio":
            warn(f"MCP server `{name}` 的传输类型 `{server_type}` v1 不支持"
                 f"（只有 stdio），已跳过")
            continue
        command = entry.get("command")
        if not command or not isinstance(command, str):
            warn(f"MCP server `{name}` 缺 command，已跳过")
            continue
        timeout = entry.get("timeout", DEFAULT_CALL_TIMEOUT_MS)
        if not isinstance(timeout, int) or timeout < 1000:
            # <1000 忽略回默认（CC 同语义：防手滑把秒写成毫秒）
            timeout = DEFAULT_CALL_TIMEOUT_MS
        out.append(MCPServerConfig(
            name=str(name), command=command,
            args=[str(a) for a in entry.get("args", []) or []],
            env={str(k): str(v) for k, v in (entry.get("env", {}) or {}).items()},
            timeout_ms=timeout, source=source))
    return out


def load_mcp_servers(*, cwd=None, home=None,
                     warn: Callable[[str], None]) -> List[MCPServerConfig]:
    """读两层 settings.json 的 mcpServers。同名项目级赢（settings 合并语义与
    skills D#72 一致）。"""
    from pathlib import Path

    from pai.core.paths import USER_DIR
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    merged: Dict[str, MCPServerConfig] = {}
    for cfg in _read_servers_layer(home_path / USER_DIR / "settings.json",
                                   "user", warn):
        merged[cfg.name] = cfg
    for cfg in _read_servers_layer(cwd_path / USER_DIR / "settings.json",
                                   "project", warn):
        merged[cfg.name] = cfg                # 后写覆盖 = 项目赢
    return sorted(merged.values(), key=lambda c: c.name)


def project_mcp_trusted(cwd=None, home=None) -> bool:
    from pai.core.paths import project_dir
    return (project_dir(cwd, home) / MCP_TRUST_MARKER).is_file()


def mark_project_mcp_trusted(cwd=None, home=None) -> None:
    from pai.core.paths import project_dir
    directory = project_dir(cwd, home)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MCP_TRUST_MARKER).write_text("trusted\n", encoding="utf-8")


def apply_mcp_trust(servers: List[MCPServerConfig], *, cwd=None, home=None,
                    ask: Optional[Callable[[str, List[str]], str]] = None,
                    warn: Callable[[str], None] = lambda _m: None
                    ) -> List[MCPServerConfig]:
    """项目级 MCP server 的信任门禁（feature 28 问 2·B 的推广）：检入仓库的
    settings.json 能起任意子进程，静默生效不可接受。用户级永远受信。

    语义与 skills 的 apply_project_trust 逐条对齐：已信任放行；有真人问一次、
    精确选中「信任」才持久化；无真人（once）丢弃项目级 + warn 指路。
    """
    project = [s for s in servers if s.source == "project"]
    if not project or project_mcp_trusted(cwd, home):
        return servers
    names = "、".join(s.name for s in project)
    if ask is not None:
        trust_option = "信任并连接（记住，之后不再问）"
        answer = ask(f"项目 settings.json 配置了 {len(project)} 个 MCP server"
                     f"（{names}）。它们会作为子进程启动并向模型提供工具，"
                     f"只信任你 review 过的。", [trust_option, "本次不连接"])
        if answer == trust_option:
            mark_project_mcp_trusted(cwd, home)
            return servers
        warn(f"项目级 MCP server 本次未连接：{names}")
        return [s for s in servers if s.source != "project"]
    warn(f"项目级 MCP server 未信任，当前模式无人可确认，已跳过：{names}"
         "（在交互模式里确认一次即可信任）")
    return [s for s in servers if s.source != "project"]


# ---------------------------------------------------------------- 装配辅助

def connect_configured_servers(*, cwd=None, home=None,
                               ask: Optional[Callable[[str, List[str]], str]] = None,
                               warn: Callable[[str], None]
                               ) -> "tuple[List[MCPSession], List[Tool]]":
    """装配期一站式：读配置 → 信任门禁 → 逐个连接（单 server 失败 warn 隔离，
    不拖垮别家——CC 同款）→ 桥接成 Tool 列表。once 不传 ask（无人可问），
    interactive 传装配期 asker。"""
    sessions: List[MCPSession] = []
    tools: List[Tool] = []
    configs = apply_mcp_trust(load_mcp_servers(cwd=cwd, home=home, warn=warn),
                              cwd=cwd, home=home, ask=ask, warn=warn)
    try:
        for cfg in configs:
            session = MCPSession(cfg.name, cfg.command, cfg.args, cfg.env,
                                 call_timeout_ms=cfg.timeout_ms)
            try:
                session.start()
            except MCPError as e:
                warn(f"{e}，已跳过该 server")
                continue
            sessions.append(session)
            tools.extend(bridge_tools(session, warn=warn))
    except BaseException:
        # 29 复核低 4：非 MCPError 异常（内部 bug 才会走到这）不许把已启动的
        # 子进程留成孤儿——先收掉再照样往上抛，不吞
        close_all_mcp(sessions)
        raise
    return sessions, tools


def close_all_mcp(sessions: List[MCPSession]) -> None:
    """全部关闭（幂等；单个 close 抛错不拦下一个——退出路径不许炸）。"""
    for session in sessions:
        try:
            session.close()
        except Exception:  # noqa: BLE001 - 退出清理是异常的终点站
            pass
