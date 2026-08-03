"""viz 数据收集的单测:工具自省形状 + pipeline 概念图 + STATUS.md 解析。全离线。"""

import json
from pathlib import Path

from pai.viz.collect import build_structure, parse_status_table


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


# Path(__file__) 而非相对路径 "docs/dev/STATUS.md":测试不该依赖 pytest 的运行目录,
# 谁在哪个 cwd 跑 `pytest` 都得找到同一份真实文件。
REAL_STATUS_PATH = Path(__file__).resolve().parents[1] / "docs" / "dev" / "STATUS.md"


def test_real_status_md_parses_to_nonempty_stages_with_expected_keys():
    # 防的是「STATUS.md 手改把表格格式改坏,却没人发现」——这条测试就是那道栏杆。
    stages = parse_status_table(REAL_STATUS_PATH.read_text(encoding="utf-8"))
    assert stages
    keys = {s["key"] for s in stages}
    assert "loop" in keys
    assert "tools" in keys


def test_real_status_md_covers_all_pipeline_stage_keys():
    # pipeline 节点的 stage 字段是手写的、STATUS.md 的模块行也是手写的——两边各自漂移
    # 互不知情。这条断言把两者钉在一起:pipeline 引用的每个 stage 都必须能在 STATUS.md
    # 里找到对应的模块行,否则前端会把该节点渲成永远没有状态色的哑节点。
    s = build_structure(status_path=REAL_STATUS_PATH)
    stage_keys = {st["key"] for st in s["stages"]}
    referenced = {n["stage"] for n in s["pipeline"]["nodes"] if n.get("stage")}
    assert referenced <= stage_keys
    assert "viz" in stage_keys  # viz 自己也在 STATUS.md 里挂了一行(自举)
