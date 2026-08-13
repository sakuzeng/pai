"""结构数据收集:自省工具注册表 + 解析 STATUS.md + 概念图数据,打 JSON 到 stdout。

被 server 以子进程方式调用(python -m pai.viz.collect):每次都是新解释器,
所以新加的 @tool 不需要任何缓存失效手段,刷新页面就能看到——这是整个 viz
的核心体验,也是"为什么不在 server 进程里直接 import"的答案。
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

STATUS_DEFAULT = Path("docs/dev/STATUS.md")
# collect.py 在 src/pai/viz/ 下，上溯三层是仓库根（与 server.REPO_ROOT 同源）
REPO_ROOT = Path(__file__).resolve().parents[3]

# 状态词 → 状态码。用「包含」匹配:表格里可能写成 **部分**、可用(备注)等
_STATUS_WORDS = [("可用", "ok"), ("部分", "partial"), ("未开始", "todo")]


def _stage_key(cell: str) -> str:
    """`core/tools/` → tools;`cli.py` → cli;memory → memory。

    剥反引号/加粗/路径前缀/.py 后缀,得到与 pipeline 节点 stage 字段对齐的短名。

    **`strip("`")` 只剥两端,碰不到中间的**——STATUS.md 里有
    `` `core/tools/` 的 matcher `` 这种散文式单元格,反引号在中间,
    旧写法解析出 key = "` 的 matcher"(带反引号和空格)直接显示在页面上。
    2026-08-12 对真实 STATUS.md 实跑发现;既有一致性测试只查 pipeline→stages
    方向,这个反方向的畸形照不到(feature 17 顺手修)。
    """
    name = cell.replace("`", "").replace("*", "").strip()
    name = name.rstrip("/")
    name = name.rsplit("/", 1)[-1].strip()
    if name.endswith(".py"):
        name = name[:-3]
    if " " in name:
        # 散文式单元格(「… 的 matcher」):取最后一个标识符样的词当 key,
        # 整句留给 label——key 是用来和 pipeline 的 stage 字段对齐的,必须干净
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", name)
        name = tokens[-1] if tokens else name
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
                "label": part.replace("`", "").strip(),
                "status": status,
                "note": cells[2],
            })
    return stages

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


# 「这个环节住在哪个文件」——**手写映射**。程序推不出来:它是设计知识,
# 不是 import 关系(与 01 的 pipeline 手写数据同一取舍)。防漂移靠测试:
# EVENT_SRC 的键集合必须恰好等于 events.py 的事件类名集合。
#
# 未开工的环节没有代码文件,指向路线图——「还没写」也是一种诚实的位置,
# 点进去看得到设计。
NODE_SRC = {
    "loop": "src/pai/core/loop.py",
    "compaction": "src/pai/core/compaction.py",
    "permissions": "src/pai/core/gate.py",
    "streaming": "src/pai/core/streaming.py",
    "memory": "src/pai/core/memory.py",
    "tools": "src/pai/core/tools/__init__.py",
    "session": "src/pai/core/session.py",
    "skills": "docs/dev/roadmap.md",
    "mcp_client": "docs/dev/roadmap.md",
}

# 事件类型 → **机制住在哪**。刻意不指 events.py:那里只有 dataclass 定义,
# 14 个事件全指同一个文件等于什么都没说。
EVENT_SRC = {
    "AgentStart": "src/pai/core/loop.py",
    "TurnStart": "src/pai/core/loop.py",
    "AssistantMessage": "src/pai/core/loop.py",
    "AgentEnd": "src/pai/core/loop.py",
    "ToolStart": "src/pai/core/tools/__init__.py",
    "ToolEnd": "src/pai/core/tools/__init__.py",
    "PermissionDecided": "src/pai/core/gate.py",
    "Compacted": "src/pai/core/compaction.py",
    "CompactionSkipped": "src/pai/core/compaction.py",
    "BreakerTripped": "src/pai/core/compaction.py",
    "RecallFailed": "src/pai/core/recall.py",
    "RecallInjected": "src/pai/core/recall.py",
    "MemoryWritten": "src/pai/core/tools/memory_tool.py",
    "ConversationCleared": "src/pai/modes/interactive.py",
    # 排队消息的机制住在 queue.py（队列与两种 drain），loop 只是它的两个注入出口
    "SteeringInjected": "src/pai/core/queue.py",
    "Interrupted": "src/pai/core/interrupt.py",
}


def _source_of(func) -> str:
    """函数 → `src/pai/....py:<行号>`（仓库相对）。

    **必须自省,不许手写**——与「schema 由 @tool 从签名生成」同一条规矩:
    手写的位置会漂,而且漂了没人知道。`Tool.func` 存的是原函数
    （@tool 没有包一层 wrapper,实测无 `__wrapped__`),所以直接取即可。
    """
    try:
        path = Path(inspect.getsourcefile(func) or "")
        line = inspect.getsourcelines(func)[1]
    except (OSError, TypeError):
        return ""
    try:
        return f"{path.resolve().relative_to(REPO_ROOT)}:{line}"
    except ValueError:
        return f"{path}:{line}"          # 装在别处(site-packages):给绝对路径


def _tool_entries() -> list:
    from pai.core.tools import get_tools  # 函数内 import:让子进程按需注册

    out = []
    for t in get_tools().values():
        props = t.parameters.get("properties", {})
        required = set(t.parameters.get("required", []))
        out.append({
            "name": t.name,
            "description": t.description,
            "src": _source_of(t.func),
            "params": [
                {"name": p, "type": spec.get("type", "string"),
                 "desc": spec.get("description", ""), "required": p in required}
                for p, spec in props.items()
            ],
        })
    return sorted(out, key=lambda x: x["name"])


def build_structure(status_path: Path = STATUS_DEFAULT) -> dict:
    from pai.config import model_name

    model = model_name()  # config 自带 load_dotenv,不再需要这里手动补位(R3#7)

    warnings: list = []
    stages: list = []
    if not status_path.exists():
        warnings.append(f"未找到 {status_path},阶段路线图为空(请从项目根目录运行 pai-viz)")
    else:
        stages = parse_status_table(status_path.read_text(encoding="utf-8"))
        if not stages:
            warnings.append(f"{status_path} 里没解析出「模块现状」表(格式变了?),阶段路线图为空")

    nodes = [dict(n) for n in _PIPELINE_NODES]
    for n in nodes:
        if n["id"] == "llm":
            n["desc"] = f"{model} · OpenAI 兼容协议"
        if n.get("stage"):
            n["src"] = NODE_SRC.get(n["stage"], "")
    return {
        "model": model,
        "tools": _tool_entries(),
        "pipeline": {"nodes": nodes, "edges": _PIPELINE_EDGES},
        "stages": stages,
        "event_src": EVENT_SRC,
        "warnings": warnings,
    }


def main() -> None:
    print(json.dumps(build_structure(), ensure_ascii=False))


if __name__ == "__main__":
    main()
