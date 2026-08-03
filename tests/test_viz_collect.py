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
