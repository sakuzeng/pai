from pai.core.tools import get_tools


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


def test_tool_without_docstring_is_rejected_clearly():
    """空 docstring 会让 `splitlines()[0]` 抛 IndexError——报错必须指向真因，而不是索引越界。"""
    import pytest

    from pai.core.tools import tool

    with pytest.raises(ValueError, match="docstring"):

        @tool
        def no_doc(path: str) -> str:
            pass


def test_tool_rejects_unknown_param_type():
    """未知参数类型必须显式报错，而不是静默降级成 string 生成错 schema（R3#2）。"""
    import pytest

    from pai.core.tools import tool

    with pytest.raises(ValueError, match="类型"):

        @tool
        def bad_type(paths: list) -> str:
            """一个签名里带不支持类型的工具。"""
            return ""


def test_tool_run_coerces_non_str_return():
    """工具返回非 str 时不能让 loop 在 result[:200] 处崩掉（R3#2）。"""
    from pai.core.tools import REGISTRY, tool

    @tool
    def returns_none(path: str) -> str:
        """一个违规返回 None 的工具。"""
        return None  # type: ignore[return-value]

    try:
        result = REGISTRY["returns_none"].run(path="x")
        assert isinstance(result, str)
    finally:
        REGISTRY.pop("returns_none", None)


def test_bash_timeout_returns_partial_output(monkeypatch):
    """后台进程占住管道时，超时前已产出的输出必须回传，而不是被异常抹成零输出（R3#3，实测复现）。"""
    from pai.core.tools import shell

    monkeypatch.setattr(shell, "TIMEOUT_SECONDS", 1, raising=False)
    result = shell.bash(command="sleep 5 & echo hi")
    assert "hi" in result
    assert "超时" in result
