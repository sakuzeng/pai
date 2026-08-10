import contextlib
import os
import re
import signal
import threading
import time

from pai.core import interrupt
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


# ---- feature 05 task 4：bash 可中断（进程组级） ----

@contextlib.contextmanager
def _injected_flag():
    """进程级注入点必须能干净复位，否则一个测试的中断标志会毒死后面所有测试。"""
    flag = interrupt.InterruptFlag()
    interrupt.set_current(flag)
    try:
        yield flag
    finally:
        interrupt.set_current(None)


def test_bash_normal_path_unchanged():
    """起独立会话（start_new_session）之后，普通命令的三条行为不变。"""
    from pai.core.tools import shell

    assert "hello" in shell.bash(command="echo hello")
    assert "到标准错误" in shell.bash(command="echo 到标准错误 1>&2")   # stdout+stderr 合并
    assert "没有输出" in shell.bash(command="exit 3")                   # 无输出带退出码
    assert "[... 截断" in shell.bash(command="head -c 5000 /dev/zero | tr '\\0' 'x'")


def test_bash_skips_execution_when_already_interrupted():
    from pai.core.tools import shell

    with _injected_flag() as flag:
        flag.set()
        result = shell.bash(command="echo 不该跑到")
    assert "已中断" in result
    assert "不该跑到" not in result


def test_bash_kills_running_command_and_returns_fast():
    from pai.core.tools import shell

    with _injected_flag() as flag:
        timer = threading.Timer(0.5, flag.set)
        timer.start()
        start = time.monotonic()
        try:
            result = shell.bash(command="sleep 30")
        finally:
            timer.cancel()
        elapsed = time.monotonic() - start
    assert "已中断" in result
    assert elapsed < 5, f"中断后没有立刻返回，耗时 {elapsed:.1f}s"


def test_bash_kills_whole_process_group_not_just_the_child():
    """本 task 的核心断言：杀 proc 只杀 shell 本身，后台孙进程会活下来继续烧机器。

    注入反证：把实现里的 killpg 换成 proc.kill()，本测试必红。
    """
    from pai.core.tools import shell

    with _injected_flag() as flag:
        timer = threading.Timer(0.5, flag.set)
        timer.start()
        try:
            result = shell.bash(command="sleep 30 & echo PID=$!; sleep 30")
        finally:
            timer.cancel()

    assert "已中断" in result
    m = re.search(r"PID=(\d+)", result)
    assert m, f"没拿到后台子进程 pid，输出：{result!r}"
    pid = int(m.group(1))
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)          # 别把跑飞的进程留给这台机器
    raise AssertionError(f"后台孙进程 {pid} 仍存活：杀的是子进程而不是进程组")


def test_bash_keeps_partial_output_on_interrupt():
    """与超时分支同一条教训（R3#3）：抹掉已产出的输出，模型必然误判重试。"""
    from pai.core.tools import shell

    with _injected_flag() as flag:
        timer = threading.Timer(0.5, flag.set)
        timer.start()
        try:
            result = shell.bash(command="echo 已经产出这行; sleep 30")
        finally:
            timer.cancel()
    assert "已经产出这行" in result
    assert "已中断" in result


# ---- feature 05 task 6：AskUserQuestion ----


@contextlib.contextmanager
def _injected_asker(fn):
    from pai.core.tools import ask

    ask.set_asker(fn)
    try:
        yield
    finally:
        ask.set_asker(None)


def test_ask_returns_asker_answer():
    from pai.core.tools import ask

    with _injected_asker(lambda question, options: f"选了 {options[1]}"):
        result = ask.ask_user_question(question="用哪个？", options='["A", "B"]')
    assert result == "选了 B"


def test_ask_without_asker_returns_error_string():
    """没有真人可问时返回错误字符串而不是抛——工具错误不 throw（架构约束）。"""
    from pai.core.tools import ask

    result = ask.ask_user_question(question="在吗", options='["A", "B"]')
    assert "错误" in result and "没有" in result


def test_ask_rejects_malformed_options():
    from pai.core.tools import ask

    with _injected_asker(lambda question, options: "不该走到这"):
        assert "错误" in ask.ask_user_question(question="q", options="不是 JSON")
        assert "错误" in ask.ask_user_question(question="q", options='{"a": 1}')
        assert "错误" in ask.ask_user_question(question="q", options='["只有一个"]')


def test_ask_schema_is_generated_from_signature():
    from pai.core.tools import REGISTRY, ask   # noqa: F401 - import 即注册

    fn = REGISTRY["ask_user_question"].schema()["function"]
    assert set(fn["parameters"]["properties"]) == {"question", "options"}
    # @tool 只认标量类型，选项列表只能以 JSON 字符串过来——描述里必须讲清楚
    assert "JSON" in fn["parameters"]["properties"]["options"]["description"]


def test_get_tools_excludes_ask_by_default():
    """once 模式没有真人可问，注册了就是让模型撞空——默认工具集必须不含它。"""
    assert "ask_user_question" not in get_tools()
    assert "ask_user_question" in get_tools(["bash", "ask_user_question"])


# ---- feature 06 task 6：remember（自动记忆写回） ----


@contextlib.contextmanager
def _memory_at(directory):
    """记忆目录走注入点而不是工具参数：@tool 只认标量，Path 参数会在装饰期就报错，
    而把目录做成 str 参数等于让模型自己挑写盘位置——那比路径穿越还糟。
    """
    from pai.core.tools import memory_tool

    memory_tool.set_memory_dir(directory)
    try:
        yield
    finally:
        memory_tool.set_memory_dir(None)


def test_remember_writes_topic_file_and_indexes_it(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        result = memory_tool.remember(topic="构建", fact="测试用 ./test.sh 跑")
    assert "构建" in result
    assert "测试用 ./test.sh 跑" in (tmp_path / "构建.md").read_text(encoding="utf-8")
    assert "构建.md" in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")


def test_remember_appends_without_clobbering(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(topic="构建", fact="第一条")
        memory_tool.remember(topic="构建", fact="第二条")
    body = (tmp_path / "构建.md").read_text(encoding="utf-8")
    assert "第一条" in body and "第二条" in body


def test_remember_indexes_each_topic_once(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(topic="构建", fact="a")
        memory_tool.remember(topic="构建", fact="b")
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert index.count("构建.md") == 1             # 索引有 200 行上限，别自己撑爆它


def test_remember_rejects_path_traversal(tmp_path):
    """topic 是**模型生成的**，且是唯一能指定写盘位置的参数——破了就是任意文件写。"""
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        for evil in ("../../etc/passwd", "/tmp/evil", "sub/dir", "..", ".", "", "   "):
            result = memory_tool.remember(topic=evil, fact="x")
            assert "错误" in result, f"{evil!r} 应被拒绝"
    assert list(tmp_path.iterdir()) == []          # 一个文件都不该被写出来


def test_remember_returns_error_string_instead_of_raising(tmp_path):
    from pai.core.tools import memory_tool

    blocked = tmp_path / "file"
    blocked.write_text("我是文件不是目录", encoding="utf-8")
    with _memory_at(blocked):
        result = memory_tool.remember(topic="构建", fact="x")
    assert "错误" in result                        # 工具错误不 throw（架构约束）


def test_remember_is_in_the_default_tool_set():
    """与 ask_user_question 不同：写回不是交互模式独有的，once 里也该能记。"""
    assert "remember" in get_tools()


def test_remember_notifies_the_assembly_layer(tmp_path):
    """写盘这件事必须能被看见。审计本身已由既有的工具消息落盘覆盖
    （assistant.tool_calls + tool 结果都进会话 JSONL），所以这里只补「可见性」一条：
    装配层注入一个通知回调，由它去发事件——工具不认识事件系统。
    """
    from pai.core.tools import memory_tool

    seen: list = []
    with _memory_at(tmp_path):
        memory_tool.set_notifier(lambda topic, path: seen.append((topic, path)))
        try:
            memory_tool.remember(topic="构建", fact="x")
            memory_tool.remember(topic="非法/名字", fact="x")     # 失败不该通知
        finally:
            memory_tool.set_notifier(None)

    assert [topic for topic, _ in seen] == ["构建"]
    assert seen[0][1] == tmp_path / "构建.md"
