# pai-viz 架构可视化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个零依赖本地网页 `pai-viz`,展示 pai 的运行时结构图(工具从 `@tool` 注册表自动自省)与阶段路线图(解析 STATUS.md,状态着色),加新工具刷新即现。

**Architecture:** `src/pai/viz/` 三个文件:`collect.py`(子进程数据收集,打 JSON 到 stdout)、`server.py`(stdlib http.server,`/` 回页面、`/api/structure` 起子进程透传 JSON)、`index.html`(手写单页,卡片 + SVG 连线)。每次 API 请求起新解释器收集,保证模块缓存不会挡住新加的工具。

**Tech Stack:** Python 标准库(http.server / subprocess / importlib.resources)+ 手写 HTML/CSS/JS。零新增依赖。

**Spec:** `docs/superpowers/specs/2026-08-03-viz-design.md`

## Global Constraints

- Python **>=3.9** 兼容(pyproject 如此声明):运行时代码不用 `X | Y` 联合类型语法(注解里配合 `from __future__ import annotations` 可以用)
- **零新增依赖**:不改 `[project] dependencies`
- **不动现有代码**:`cli.py`、`core/`、`modes/` 一行不改;pyproject 只加 script 注册与 package-data
- 测试全离线,不打真实 API(项目铁律:花钱的副作用不能是默认行为)
- 注释风格与现有代码一致:中文、讲"为什么"
- 每个文件开头有模块 docstring,说明该模块存在的理由(项目惯例)

## File Structure

```
src/pai/viz/__init__.py    空文件,标记包
src/pai/viz/collect.py     数据收集(可独立跑:python -m pai.viz.collect)
src/pai/viz/server.py      HTTP server + main()(pai-viz 入口)
src/pai/viz/index.html     单页前端
tests/test_viz_collect.py  collect 的单测(自省 + STATUS 解析)
tests/test_viz_server.py   server 冒烟测试(随机端口 + 两个端点)
pyproject.toml             +2 处:pai-viz script、package-data
```

---

### Task 1: collect.py — 工具自省 + pipeline 概念图 + model 名

**Files:**
- Create: `src/pai/viz/__init__.py`
- Create: `src/pai/viz/collect.py`
- Test: `tests/test_viz_collect.py`

**Interfaces:**
- Consumes: `pai.core.tools.get_tools()`(已存在,返回 `dict[str, Tool]`,`Tool.parameters` 是 JSON Schema 的 object 定义)、`pai.config.model_name()`(已存在,读 env,不需要 API key)
- Produces: `build_structure(status_path: Path) -> dict`,键:`model`(str)、`tools`(list[dict])、`pipeline`(dict,含 `nodes`/`edges`)、`stages`(list,本 task 恒为 `[]`)、`warnings`(list[str])。Task 2 往 `stages`/`warnings` 里填内容,Task 3 的 server 调 `python -m pai.viz.collect` 拿整个 JSON。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_viz_collect.py`:

```python
"""viz 数据收集的单测:工具自省形状 + pipeline 概念图 + STATUS.md 解析。全离线。"""

import json
from pathlib import Path

from pai.viz.collect import build_structure


def test_tools_are_introspected_from_registry():
    s = build_structure(status_path=Path("不存在的路径.md"))
    names = {t["name"] for t in s["tools"]}
    # 四个内置工具必须在——它们来自 @tool 注册表,不是硬编码
    assert {"bash", "read_file", "write_file", "edit_file"} <= names
    bash = next(t for t in s["tools"] if t["name"] == "bash")
    assert bash["description"]  # docstring 首行,@tool 强制非空
    p = next(p for p in bash["params"] if p["name"] == "command")
    assert p["type"] == "string"
    assert p["required"] is True


def test_pipeline_nodes_and_edges_reference_each_other():
    s = build_structure(status_path=Path("不存在的路径.md"))
    ids = {n["id"] for n in s["pipeline"]["nodes"]}
    assert {"task", "loop", "llm", "tools", "session", "reply"} <= ids
    # 未来环节从第一版就预画(设计文档「预画未来节点」一节)
    assert {"compaction", "permissions", "streaming", "memory", "skills", "mcp_client"} <= ids
    for a, b in s["pipeline"]["edges"]:
        assert a in ids and b in ids, f"edge ({a},{b}) 引用了不存在的节点"
    # 每个节点都得有列号,前端靠它布局
    assert all(isinstance(n["col"], int) for n in s["pipeline"]["nodes"])


def test_structure_is_json_serializable_and_has_model():
    s = build_structure(status_path=Path("不存在的路径.md"))
    json.dumps(s, ensure_ascii=False)  # 不抛即过
    assert s["model"]  # model_name() 有默认值,不需要 .env
    # STATUS 文件不存在:stages 为空 + 有警告,但不崩(设计的「两块互不拖累」)
    assert s["stages"] == []
    assert s["warnings"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_viz_collect.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'pai.viz'`

- [ ] **Step 3: 最小实现**

创建空的 `src/pai/viz/__init__.py`,再创建 `src/pai/viz/collect.py`:

```python
"""结构数据收集:自省工具注册表 + 解析 STATUS.md + 概念图数据,打 JSON 到 stdout。

被 server 以子进程方式调用(python -m pai.viz.collect):每次都是新解释器,
所以新加的 @tool 不需要任何缓存失效手段,刷新页面就能看到——这是整个 viz
的核心体验,也是"为什么不在 server 进程里直接 import"的答案。
"""

from __future__ import annotations

import json
from pathlib import Path

STATUS_DEFAULT = Path("docs/dev/STATUS.md")

# pipeline 是手写的概念图(数据流),不是 import 依赖图——这是设计决定:
# 结构由人定义,程序只填充自动化的部分(工具清单、阶段状态)。
# col 是前端布局列号;stage 关联 STATUS.md「模块现状」表里的模块名(见 _stage_key)。
_PIPELINE_NODES = [
    {"id": "task", "label": "用户任务", "desc": "pai \"...\"", "col": 0},
    {"id": "loop", "label": "agent loop", "desc": "max_steps 兜底 · usage 落盘 · 预算熔断",
     "col": 1, "stage": "loop"},
    {"id": "compaction", "label": "上下文压缩", "desc": "秤/警戒线已就位,压缩未接",
     "col": 1, "stage": "compaction"},
    {"id": "permissions", "label": "权限钩子", "desc": "before_tool_call",
     "col": 1, "stage": "permissions"},
    {"id": "streaming", "label": "流式输出", "col": 1, "stage": "streaming"},
    {"id": "memory", "label": "长期记忆", "col": 1, "stage": "memory"},
    {"id": "skills", "label": "skills", "col": 1, "stage": "skills"},
    {"id": "mcp_client", "label": "MCP client", "col": 1, "stage": "mcp_client"},
    {"id": "llm", "label": "LLM", "desc": "", "col": 2},  # desc 运行时填 model 名
    {"id": "tools", "label": "工具(自动自省)", "col": 2, "stage": "tools"},
    {"id": "session", "label": "session JSONL 落盘", "desc": "append-only,审计地基",
     "col": 3, "stage": "session"},
    {"id": "reply", "label": "最终回答", "col": 3},
]

_PIPELINE_EDGES = [
    ["task", "loop"],
    ["loop", "llm"],
    ["loop", "tools"],
    ["loop", "session"],
    ["loop", "reply"],
    ["compaction", "loop"],
    ["permissions", "loop"],
    ["streaming", "loop"],
    ["memory", "loop"],
    ["skills", "loop"],
    ["mcp_client", "loop"],
]


def _tool_entries() -> list:
    from pai.core.tools import get_tools  # 函数内 import:让子进程按需注册

    out = []
    for t in get_tools().values():
        props = t.parameters.get("properties", {})
        required = set(t.parameters.get("required", []))
        out.append({
            "name": t.name,
            "description": t.description,
            "params": [
                {"name": p, "type": spec.get("type", "string"),
                 "desc": spec.get("description", ""), "required": p in required}
                for p, spec in props.items()
            ],
        })
    return sorted(out, key=lambda x: x["name"])


def build_structure(status_path: Path = STATUS_DEFAULT) -> dict:
    from dotenv import load_dotenv

    from pai.config import model_name

    load_dotenv()  # PAI_MODEL 可能配在 .env;没有 .env 也不报错
    model = model_name()

    warnings: list = []
    stages: list = []  # Task 2 接 STATUS.md 解析,这里先占位
    if not status_path.exists():
        warnings.append(f"未找到 {status_path},阶段路线图为空(请从项目根目录运行 pai-viz)")

    nodes = [dict(n) for n in _PIPELINE_NODES]
    for n in nodes:
        if n["id"] == "llm":
            n["desc"] = f"{model} · OpenAI 兼容协议"
    return {
        "model": model,
        "tools": _tool_entries(),
        "pipeline": {"nodes": nodes, "edges": _PIPELINE_EDGES},
        "stages": stages,
        "warnings": warnings,
    }


def main() -> None:
    print(json.dumps(build_structure(), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_viz_collect.py -v`
Expected: 3 项 PASS

- [ ] **Step 5: 手工验证子进程入口**

Run: `python -m pai.viz.collect | python -c "import json,sys; d=json.load(sys.stdin); print(d['model'], len(d['tools']))"`
Expected: 打印 model 名和工具数(4)

- [ ] **Step 6: Commit**

```bash
git add src/pai/viz/__init__.py src/pai/viz/collect.py tests/test_viz_collect.py
git commit -m "feat(viz): collect.py 工具自省 + pipeline 概念图数据"
```

---

### Task 2: STATUS.md「模块现状」表解析,接入 build_structure

**Files:**
- Modify: `src/pai/viz/collect.py`
- Test: `tests/test_viz_collect.py`(追加)

**Interfaces:**
- Produces: `parse_status_table(text: str) -> list`,每项 `{"key": str, "label": str, "status": "ok"|"partial"|"todo"|"unknown", "note": str}`;`build_structure()` 的 `stages` 从此有内容。前端(Task 4)靠 `key` 与 pipeline 节点的 `stage` 字段对上。

STATUS.md 的表长这样(解析目标,格式已存在于 `docs/dev/STATUS.md`):

```markdown
## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop:… |
| `core/compaction.py` | **部分** | 见下 |
| `cli.py` / `config.py` | 可用 | … |
| memory / permissions / streaming / skills / mcp_client / evals | 未开始 | 路线图后续阶段 |
```

要点:模块列可能一格多个模块(用「空格斜杠空格」分隔——路径里的 `/` 两侧无空格,不会误切);状态词可能带 `**` 加粗;模块名可能带反引号、路径前缀、`.py` 后缀、目录尾 `/`。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_viz_collect.py` 追加:

```python
from pai.viz.collect import parse_status_table

FIXTURE_OK = """\
# 当前状态快照

## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop:依赖注入 |
| `core/compaction.py` | **部分** | 见下 |
| `core/tools/` | 可用 | @tool 装饰器 |
| `cli.py` / `config.py` | 可用 | cli 只做分发 |
| memory / permissions / streaming | 未开始 | 路线图后续阶段 |

## 下一节

正文。
"""


def test_parse_status_table_normal():
    stages = parse_status_table(FIXTURE_OK)
    by_key = {s["key"]: s for s in stages}
    assert by_key["loop"]["status"] == "ok"
    assert by_key["compaction"]["status"] == "partial"  # ** 加粗要能穿透
    assert by_key["tools"]["status"] == "ok"            # 目录尾 / 要能剥掉
    # 一格多模块按「空格斜杠空格」切开,各成一条
    assert by_key["cli"]["status"] == "ok" and by_key["config"]["status"] == "ok"
    assert by_key["memory"]["status"] == "todo"
    assert by_key["memory"]["note"] == "路线图后续阶段"


def test_parse_status_table_malformed_returns_empty():
    # 没有「模块现状」小节 → 空列表,不抛(页面显示警告条,结构图照常)
    assert parse_status_table("# 别的文档\n\n随便什么") == []
    assert parse_status_table("## 模块现状\n\n这节没有表格") == []


def test_build_structure_reads_real_status(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text(FIXTURE_OK, encoding="utf-8")
    s = build_structure(status_path=f)
    assert s["warnings"] == []
    assert any(st["key"] == "loop" and st["status"] == "ok" for st in s["stages"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_viz_collect.py -v`
Expected: 新增 3 项 FAIL,`ImportError: cannot import name 'parse_status_table'`

- [ ] **Step 3: 实现解析器**

在 `collect.py` 中(`STATUS_DEFAULT` 之后)加:

```python
# 状态词 → 状态码。用「包含」匹配:表格里可能写成 **部分**、可用(备注)等
_STATUS_WORDS = [("可用", "ok"), ("部分", "partial"), ("未开始", "todo")]


def _stage_key(cell: str) -> str:
    """`core/tools/` → tools;`cli.py` → cli;memory → memory。

    剥反引号/加粗/路径前缀/.py 后缀,得到与 pipeline 节点 stage 字段对齐的短名。
    """
    name = cell.strip().strip("`").strip("*").strip()
    name = name.rstrip("/")
    name = name.rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[:-3]
    return name


def parse_status_table(text: str) -> list:
    """解析 STATUS.md「模块现状」表。格式不符时返回 [],绝不抛——

    STATUS.md 是手写文档,格式漂移是正常事件不是异常;页面用警告条提示即可,
    不能拖垮结构图(设计文档「两块互不拖累」)。
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## 模块现状"):
            start = i
            break
    if start is None:
        return []

    stages: list = []
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith("## "):  # 下一节,结束
            break
        if not s.startswith("|"):
            if stages:
                break  # 表格已经收集过且离开了表格区
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] == "模块" or set(cells[0]) <= set("-: "):
            continue  # 表头行 / 分隔行
        status = "unknown"
        for word, code in _STATUS_WORDS:
            if word in cells[1]:
                status = code
                break
        # 「空格斜杠空格」是多模块分隔符;路径 core/loop.py 的 / 两侧无空格,不受影响
        for part in cells[0].split(" / "):
            stages.append({
                "key": _stage_key(part),
                "label": part.strip().strip("`"),
                "status": status,
                "note": cells[2],
            })
    return stages
```

并把 `build_structure` 里的占位段替换为:

```python
    warnings: list = []
    stages: list = []
    if not status_path.exists():
        warnings.append(f"未找到 {status_path},阶段路线图为空(请从项目根目录运行 pai-viz)")
    else:
        stages = parse_status_table(status_path.read_text(encoding="utf-8"))
        if not stages:
            warnings.append(f"{status_path} 里没解析出「模块现状」表(格式变了?),阶段路线图为空")
```

- [ ] **Step 4: 跑全部 viz 测试确认通过**

Run: `pytest tests/test_viz_collect.py -v`
Expected: 6 项 PASS(注意 Task 1 的 `test_structure_...` 断言 STATUS 缺失时 `stages == []` 且有警告,应仍然通过)

- [ ] **Step 5: 用真实 STATUS.md 手工验证**

Run: `python -m pai.viz.collect | python -c "import json,sys; [print(s['key'], s['status']) for s in json.load(sys.stdin)['stages']]"`
Expected: 打印 loop/tools/session 等为 ok,compaction 为 partial,memory 等为 todo

- [ ] **Step 6: Commit**

```bash
git add src/pai/viz/collect.py tests/test_viz_collect.py
git commit -m "feat(viz): 解析 STATUS.md 模块现状表,阶段状态入 JSON"
```

---

### Task 3: server.py + pyproject 注册(pai-viz 命令)

**Files:**
- Create: `src/pai/viz/server.py`
- Modify: `pyproject.toml`(`[project.scripts]` 加一行;新增 `[tool.setuptools.package-data]`)
- Test: `tests/test_viz_server.py`

**Interfaces:**
- Consumes: `python -m pai.viz.collect`(Task 1/2 的子进程入口);`src/pai/viz/index.html`(Task 4 提供,本 task 先放占位页)
- Produces: `pai.viz.server:main`(console script 入口);`GET /` → HTML,`GET /api/structure` → collect 的 JSON(失败时 500 + `{"error": stderr}`)

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_viz_server.py`:

```python
"""server 冒烟测试:随机端口起真 server,打两个端点。全离线(子进程只 import pai,不打 API)。"""

import json
import threading
import urllib.request

import pytest

from pai.viz.server import make_server


@pytest.fixture()
def viz_server():
    httpd = make_server(port=0)  # 0 = 让系统挑个空闲端口,测试并行也不撞
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_index_served(viz_server):
    with urllib.request.urlopen(f"{viz_server}/") as r:
        assert r.status == 200
        assert "text/html" in r.headers["Content-Type"]
        assert "pai" in r.read().decode("utf-8")


def test_api_structure_returns_collected_json(viz_server):
    with urllib.request.urlopen(f"{viz_server}/api/structure") as r:
        assert r.status == 200
        data = json.loads(r.read().decode("utf-8"))
    assert "tools" in data and "pipeline" in data
    assert any(t["name"] == "bash" for t in data["tools"])


def test_unknown_path_404(viz_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(f"{viz_server}/nope")
    assert ei.value.code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_viz_server.py -v`
Expected: FAIL,`ModuleNotFoundError`/`ImportError`(server 还不存在)

- [ ] **Step 3: 放占位 index.html + 实现 server.py**

先放一个最小占位页(Task 4 会整体替换),`src/pai/viz/index.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>pai 架构总览</title>
<p>pai-viz 占位页(Task 4 替换)</p>
```

创建 `src/pai/viz/server.py`:

```python
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
    except subprocess.TimeoutExpired:
        return 500, json.dumps({"error": "collect 子进程超时(30s)"}, ensure_ascii=False).encode()
    if proc.returncode == 0:
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
```

`pyproject.toml` 两处修改:

```toml
[project.scripts]
pai = "pai.cli:main"
pai-viz = "pai.viz.server:main"
```

```toml
[tool.setuptools.package-data]
"pai.viz" = ["*.html"]
```

- [ ] **Step 4: 重装(让新 script 生效)并跑测试**

Run: `pip install -e ".[dev]" -q && pytest tests/test_viz_server.py -v`
Expected: 3 项 PASS

- [ ] **Step 5: 手工冒烟**

Run: `pai-viz --no-open --port 7799 &` 然后 `curl -s localhost:7799/api/structure | head -c 200`,最后 kill 后台进程
Expected: JSON 开头含 `"model"`

- [ ] **Step 6: Commit**

```bash
git add src/pai/viz/server.py src/pai/viz/index.html tests/test_viz_server.py pyproject.toml
git commit -m "feat(viz): stdlib http server + pai-viz 命令注册"
```

---

### Task 4: index.html — 单页前端(结构图 + 阶段路线图)

**Files:**
- Modify: `src/pai/viz/index.html`(整体替换占位页)
- Test: `tests/test_viz_server.py`(追加 1 项)

**Interfaces:**
- Consumes: `GET /api/structure` 的 JSON:`model` / `tools[{name,description,params[{name,type,desc,required}]}]` / `pipeline{nodes[{id,label,desc?,col,stage?}],edges[[a,b]]}` / `stages[{key,label,status,note}]` / `warnings[str]`;错误时 `{error}`。
- Produces: 完整页面。无构建步骤、无外部资源(离线可用)。

渲染规则(实现依据,来自设计文档):
- pipeline 节点按 `col` 分列;`stage` 字段在 `stages` 里查状态:`ok` 绿左边框、`partial` 黄左边框、`todo` 整卡虚线灰(「预画未来节点」);查不到或无 `stage` → 中性样式
- `tools` 节点特殊:内部渲染工具卡列表(来自 `tools` 数组),点击工具卡展开参数表
- 连线:一层绝对定位 SVG,按节点实际位置画贝塞尔;任一端是 `todo` 则虚线
- 顶部:标题 + meta(最后刷新时间 · model · 工具数)+ 刷新按钮(重新 fetch,不刷整页)
- `warnings` → 黄条;fetch 失败/`{error}` → 红条,结构图区照常尝试渲染已有数据

- [ ] **Step 1: 追加测试(先失败)**

在 `tests/test_viz_server.py` 追加:

```python
def test_index_is_real_page_not_placeholder(viz_server):
    with urllib.request.urlopen(f"{viz_server}/") as r:
        html = r.read().decode("utf-8")
    # 真页面的标志:会去打 API、有两个区域的容器
    assert "/api/structure" in html
    assert 'id="pipeline"' in html and 'id="stages"' in html
```

Run: `pytest tests/test_viz_server.py -v` → 新增 1 项 FAIL(占位页没有这些)

- [ ] **Step 2: 整体替换 index.html**

```html
<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pai 架构总览</title>
<style>
  :root {
    --bg:#111318; --panel:#1a1d24; --card:#22262f; --line:#3a4150;
    --text:#d8dce6; --dim:#8a93a6; --ok:#4ade80; --partial:#facc15;
    --todo:#5b6372; --err:#f87171; --accent:#818cf8;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
  header { display:flex; align-items:center; gap:12px; padding:14px 22px;
           border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--bg); }
  h1 { font-size:16px; margin:0; }
  #meta { color:var(--dim); font-size:12px; margin-left:auto; }
  button { background:var(--card); color:var(--text); border:1px solid var(--line);
           border-radius:6px; padding:6px 14px; cursor:pointer; }
  button:hover { border-color:var(--accent); }
  .banner { margin:12px 22px 0; padding:10px 14px; border-radius:8px;
            display:none; white-space:pre-wrap; font-size:13px; }
  #error { background:#3b1d1d; border:1px solid var(--err); color:#fecaca; }
  #warn  { background:#3b331d; border:1px solid var(--partial); color:#fde68a; }
  section { padding:16px 22px 34px; }
  h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.1em; }
  /* —— 结构图 —— */
  #pipeline { position:relative; display:flex; gap:72px; align-items:flex-start;
              overflow-x:auto; padding:8px 2px; }
  #wires { position:absolute; inset:0; pointer-events:none; }
  .col { display:flex; flex-direction:column; gap:14px; min-width:200px;
         position:relative; z-index:1; }
  .node { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:10px 12px; }
  .node .t { font-weight:600; font-size:13px; }
  .node .d { color:var(--dim); font-size:12px; margin-top:2px; }
  .node.ok      { border-left:3px solid var(--ok); }
  .node.partial { border-left:3px solid var(--partial); }
  .node.todo    { border:1px dashed var(--todo); color:var(--dim); background:transparent; }
  .node.todo .t::after { content:" · 未开始"; font-weight:400; font-size:11px; color:var(--todo); }
  .node.partial .t::after { content:" · 部分"; font-weight:400; font-size:11px; color:var(--partial); }
  /* tools 节点内的工具卡 */
  .tool { border:1px solid var(--line); border-radius:8px; padding:8px 10px;
          margin-top:8px; cursor:pointer; background:var(--panel); }
  .tool .name { font-family:ui-monospace,Menlo,monospace; font-size:13px; color:var(--accent); }
  .tool .desc { color:var(--dim); font-size:12px; }
  .tool table { display:none; width:100%; margin-top:6px; border-collapse:collapse; font-size:12px; }
  .tool.open table { display:table; }
  .tool td { padding:2px 6px 2px 0; color:var(--dim); vertical-align:top; }
  .tool td.pn { font-family:ui-monospace,Menlo,monospace; color:var(--text); }
  .req { color:var(--partial); }
  /* —— 阶段路线图 —— */
  #stages { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px; }
  .stage { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
  .stage .top { display:flex; align-items:center; gap:8px; }
  .stage .label { font-family:ui-monospace,Menlo,monospace; font-size:13px; }
  .stage .badge { font-size:11px; border-radius:99px; padding:1px 9px; margin-left:auto; }
  .stage.ok      .badge { background:#14321f; color:var(--ok); }
  .stage.partial .badge { background:#332c11; color:var(--partial); }
  .stage.todo    .badge { background:#242a35; color:var(--dim); }
  .stage.unknown .badge { background:#242a35; color:var(--dim); }
  .stage.todo { border-style:dashed; }
  .stage .note { color:var(--dim); font-size:12px; margin-top:6px; }
</style>

<header>
  <h1>pai 架构总览</h1>
  <span id="meta"></span>
  <button id="refresh">刷新</button>
</header>
<div id="error" class="banner"></div>
<div id="warn" class="banner"></div>
<section>
  <h2>运行时结构</h2>
  <div id="pipeline"><svg id="wires"></svg></div>
</section>
<section>
  <h2>阶段路线图(来自 docs/dev/STATUS.md)</h2>
  <div id="stages"></div>
</section>

<script>
const $ = id => document.getElementById(id);
let lastData = null;

async function load() {
  $('error').style.display = 'none';
  try {
    const r = await fetch('/api/structure');
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
    lastData = data;
    render(data);
    $('meta').textContent = '最后刷新 ' + new Date().toLocaleTimeString()
      + ' · ' + data.model + ' · 工具 ' + data.tools.length + ' 个';
  } catch (e) {
    $('error').textContent = '收集失败:\n' + e.message;
    $('error').style.display = 'block';
  }
}

function statusOf(data, key) {
  const s = (data.stages || []).find(x => x.key === key);
  return s ? s.status : null;
}

function render(data) {
  const warn = $('warn');
  warn.style.display = (data.warnings || []).length ? 'block' : 'none';
  warn.textContent = (data.warnings || []).join('\n');
  renderPipeline(data);
  renderStages(data.stages || []);
}

function renderPipeline(data) {
  const P = $('pipeline');
  P.querySelectorAll('.col').forEach(e => e.remove());
  const maxCol = Math.max(...data.pipeline.nodes.map(n => n.col));
  const cols = [];
  for (let i = 0; i <= maxCol; i++) {
    const c = document.createElement('div');
    c.className = 'col';
    P.appendChild(c); cols.push(c);
  }
  const els = {};
  for (const n of data.pipeline.nodes) {
    const el = document.createElement('div');
    el.className = 'node';
    const st = n.stage ? statusOf(data, n.stage) : null;
    if (st) el.classList.add(st);
    el.innerHTML = '<div class="t"></div>' + (n.desc ? '<div class="d"></div>' : '');
    el.querySelector('.t').textContent = n.label;
    if (n.desc) el.querySelector('.d').textContent = n.desc;
    if (n.id === 'tools') for (const t of data.tools) el.appendChild(toolCard(t));
    cols[n.col].appendChild(el);
    els[n.id] = el;
  }
  requestAnimationFrame(() => drawWires(data, els));
}

function toolCard(t) {
  const el = document.createElement('div');
  el.className = 'tool';
  el.innerHTML = '<div class="name"></div><div class="desc"></div><table></table>';
  el.querySelector('.name').textContent = t.name;
  el.querySelector('.desc').textContent = t.description;
  const tb = el.querySelector('table');
  for (const p of t.params) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="pn"></td><td></td><td></td>';
    tr.children[0].textContent = p.name + (p.required ? ' *' : '');
    if (p.required) tr.children[0].classList.add('req');
    tr.children[1].textContent = p.type;
    tr.children[2].textContent = p.desc;
    tb.appendChild(tr);
  }
  el.addEventListener('click', () => el.classList.toggle('open'));
  return el;
}

function drawWires(data, els) {
  const P = $('pipeline'), svg = $('wires');
  svg.setAttribute('width', P.scrollWidth);
  svg.setAttribute('height', P.scrollHeight);
  svg.innerHTML = '';
  const pr = P.getBoundingClientRect();
  const todoIds = new Set(data.pipeline.nodes
    .filter(n => n.stage && statusOf(data, n.stage) === 'todo').map(n => n.id));
  for (const [a, b] of data.pipeline.edges) {
    if (!els[a] || !els[b]) continue;
    const ra = els[a].getBoundingClientRect(), rb = els[b].getBoundingClientRect();
    let d;
    if (Math.abs(ra.left - rb.left) < 20) {   // 同列:上下相连
      const upper = ra.top < rb.top ? ra : rb, lower = ra.top < rb.top ? rb : ra;
      const x = upper.left - pr.left + P.scrollLeft + upper.width / 2;
      d = `M ${x} ${upper.bottom - pr.top} L ${x} ${lower.top - pr.top}`;
    } else {                                   // 跨列:右缘 → 左缘,贝塞尔
      const src = ra.left < rb.left ? ra : rb, dst = ra.left < rb.left ? rb : ra;
      const x1 = src.right - pr.left + P.scrollLeft, y1 = src.top - pr.top + src.height / 2;
      const x2 = dst.left - pr.left + P.scrollLeft,  y2 = dst.top - pr.top + dst.height / 2;
      const mx = (x1 + x2) / 2;
      d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
    }
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'var(--line)');
    path.setAttribute('stroke-width', '1.5');
    if (todoIds.has(a) || todoIds.has(b)) path.setAttribute('stroke-dasharray', '5 4');
    svg.appendChild(path);
  }
}

function renderStages(stages) {
  const S = $('stages');
  S.innerHTML = '';
  for (const st of stages) {
    const el = document.createElement('div');
    el.className = 'stage ' + st.status;
    el.innerHTML = '<div class="top"><span class="label"></span><span class="badge"></span></div>'
                 + '<div class="note"></div>';
    el.querySelector('.label').textContent = st.label;
    el.querySelector('.badge').textContent =
      ({ok: '可用', partial: '部分', todo: '未开始'})[st.status] || st.status;
    el.querySelector('.note').textContent = st.note;
    S.appendChild(el);
  }
}

$('refresh').addEventListener('click', load);
window.addEventListener('resize', () => { if (lastData) renderPipeline(lastData); });
load();
</script>
</html>
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_viz_server.py -v`
Expected: 4 项 PASS

- [ ] **Step 4: 手工验收(核心体验)**

1. `pai-viz` → 浏览器自动打开,确认:结构图四列、loop 绿边、compaction 黄边、memory 等虚线灰、连线正常;工具组里 4 张卡,点开 `bash` 能看到 `command` 参数标 `*`
2. **加新工具实验**:在 `src/pai/core/tools/fs.py` 临时加

   ```python
   @tool
   def web_fetch(url: Annotated[str, "要抓取的 URL"]) -> str:
       """抓取网页内容(实验占位)。"""
       return "TODO"
   ```

   浏览器点「刷新」→ 工具组出现 `web_fetch`。**这一步是整个项目的验收标准。**
   验完把临时工具删掉,`git checkout src/pai/core/tools/fs.py` 或手工还原。
3. 把 STATUS.md 里 compaction 的「部分」临时改成「可用」,刷新 → 结构图 compaction 节点变绿。改回来。

- [ ] **Step 5: Commit**

```bash
git add src/pai/viz/index.html tests/test_viz_server.py
git commit -m "feat(viz): 单页前端——结构图(SVG 连线)+ 阶段路线图"
```

---

### Task 5: 文档收尾 + 全量回归

**Files:**
- Modify: `README.md`(结构一节加 viz)
- Modify: `docs/dev/STATUS.md`(模块现状表加 viz 行——加完 viz 自己就会显示自己,顺手验证)
- Modify: `docs/dev/devlog.md`(按项目惯例追加一条记录)

- [ ] **Step 1: README 结构树加一段**

在 `README.md` 结构树 `modes/` 段之后加:

```
  viz/             架构可视化:pai-viz 起本地网页,结构图(工具自动自省)+ 阶段路线图(解析 STATUS.md)
```

- [ ] **Step 2: STATUS.md 模块现状表加一行**

在 `modes/once.py` 行后加:

```markdown
| `viz/` | 可用 | `pai-viz` 本地架构可视化:工具自省自动上图,阶段状态解析本表 |
```

- [ ] **Step 3: devlog.md 按现有条目格式追加记录**

内容要点:做了 pai-viz(动机:直观看到架构与进度)、三个文件的分工、
「每请求起子进程」的设计原因、STATUS.md 作为阶段状态单一事实来源。
格式参照 devlog.md 现有条目(日期 + 小节),与最近几条保持一致。

- [ ] **Step 4: 全量回归**

Run: `./test.sh`
Expected: 原 56 项 + 新增约 10 项全部 PASS(1 项 llm 标记 deselected 照旧);
再跑一次 `pai-viz --no-open --port 7788 &` + `curl -s localhost:7788/ | grep -c pipeline` 确认非占位页,kill 之。

- [ ] **Step 5: Commit**

```bash
git add README.md docs/dev/STATUS.md docs/dev/devlog.md
git commit -m "docs: README/STATUS/devlog 收录 pai-viz"
```
