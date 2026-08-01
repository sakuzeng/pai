from pai.tools import get_tools


def test_schema_generated_from_signature():
    tools = get_tools()
    schema = tools["edit_file"].schema()
    fn = schema["function"]
    assert fn["name"] == "edit_file"
    assert set(fn["parameters"]["properties"]) == {"path", "old", "new"}
    assert fn["parameters"]["required"] == ["path", "old", "new"]
    assert fn["parameters"]["properties"]["old"]["description"]  # Annotated 描述进了 schema


def test_get_tools_subset():
    subset = get_tools(["read_file", "bash"])
    assert set(subset) == {"read_file", "bash"}


def test_edit_file_unique_match(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world\n", encoding="utf-8")
    tools = get_tools()
    result = tools["edit_file"].run(path=str(p), old="world", new="pai")
    assert "1 处替换" in result
    assert p.read_text(encoding="utf-8") == "hello pai\n"


def test_edit_file_rejects_missing_and_ambiguous(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("aa bb aa\n", encoding="utf-8")
    tools = get_tools()
    assert "找不到" in tools["edit_file"].run(path=str(p), old="cc", new="x")
    assert "不唯一" in tools["edit_file"].run(path=str(p), old="aa", new="x")
    assert p.read_text(encoding="utf-8") == "aa bb aa\n"  # 两次拒绝都不该动文件


def test_tool_run_converts_exception_to_message():
    tools = get_tools()
    result = tools["read_file"].run(path="/definitely/not/exist/xyz.txt")
    assert result.startswith("错误：")  # 异常变反馈，不上抛
