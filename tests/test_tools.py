import contextlib
import os
import re
import signal
import threading
import time

import pytest

from pai.core import interrupt
from pai.core.tools import get_tools, tool


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

    # 后台 sleep 只需比 1s 超时长即可复现「占住管道」；5s 改 2s 语义不变省 3s（30 优化）
    monkeypatch.setattr(shell, "TIMEOUT_SECONDS", 1, raising=False)
    result = shell.bash(command="sleep 2 & echo hi")
    assert "hi" in result
    assert "超时" in result


def test_the_default_timeout_matches_the_two_reference_implementations():
    """守的不是数字本身，是「改它之前先读一遍理由」。

    60s 是立项时拍脑袋定的，扛不住一次完整测试跑（本仓库自己就要 106s）
    或 `npm install`。CC 与 dsh **各自独立**收敛到同一对数字 120s/600s——
    三家参照里两家一致是难得的强信号，pai 取默认值那一档。
    （TODO「给照抄来的常数建一条检查习惯」：抄来的数字要带着它的前提一起被看见。）
    """
    from pai.core.tools import shell

    assert shell.TIMEOUT_SECONDS == 120


def test_timeout_message_tells_the_model_what_to_do_next(monkeypatch):
    """只说「杀了」的文案会让模型原样重试，再撞一次同样的墙。

    三家都在这个语境里给出路（dsh 把 `run_in_background` 写进工具描述、
    CC 的 ripgrep 超时说「换更具体的路径或 pattern」）。pai 没有后台任务机制，
    给的是穷人版出路：起到后台 + 分次读日志。
    """
    from pai.core.tools import shell

    monkeypatch.setattr(shell, "TIMEOUT_SECONDS", 1, raising=False)
    result = shell.bash(command="sleep 5")

    assert "超时" in result
    assert "nohup" in result          # 具体到可以照着敲的一条命令
    assert "read_file" in result      # 以及之后怎么把输出取回来


def test_timeout_message_reports_exit_code(monkeypatch):
    """dsh「正交事实独立上报」的后一半（TODO 工具调用超时节末条）：
    命令可能 trap 了 SIGTERM 后以 0 退出、同时确实超了时——超时与退出码是
    两个独立事实，文案里都得有，模型才分得清「被杀」与「自己退了但超时」。"""
    from pai.core.tools import shell

    monkeypatch.setattr(shell, "TIMEOUT_SECONDS", 1, raising=False)
    result = shell.bash(command="sleep 5")

    assert "超时" in result
    assert "退出码" in result


def test_interrupt_message_does_not_offer_the_timeout_way_out(monkeypatch):
    """中断是**用户主动喊停**，不是「跑太久」——给它出路等于劝模型绕过用户。

    两条路径共用同一个 `_kill_and_collect`，很容易顺手把话写到一块去。

    **必须中途中断，不能开跑前就置标志**——后者走的是 `bash()` 开头那条
    「已中断，命令未执行」的提前返回，根本进不了 `_kill_and_collect`，
    于是这条测试在两种实现下都绿（第一版就是这么写的，交付前的注入反证抓到了它）。
    """
    from pai.core.tools import shell

    with _injected_flag() as flag:
        timer = threading.Timer(0.5, flag.set)
        timer.start()
        try:
            result = shell.bash(command="sleep 30")
        finally:
            timer.cancel()

    assert "已中断" in result
    assert "nohup" not in result


# ---- 超时 P1：模型可传 timeout，且**真钳制**（2026-08-18）----


def test_omitted_timeout_falls_back_to_the_default():
    """0 是「没传」的哨兵——`@tool` 的 schema 生成器不吃 `Optional[int]`
    （`PY_TO_JSON` 只认 str/int/float/bool），所以用哨兵而不是 None。"""
    from pai.core.tools import shell

    assert shell.clamp_timeout(0) == shell.TIMEOUT_SECONDS


def test_a_model_supplied_timeout_is_clamped_to_the_cap():
    """**这条是抄 dsh 而不是抄 CC 的理由**。

    CC 的 BashTool 在 schema 描述里写着 `max 600000`，运行期却只有
    `timeout || default`——一个 `Math.min` 都没有，上限纯属君子协定
    （同仓库的 PowerShellTool 反而有，是疏漏不是设计）。
    dsh 的 `clampTimeout(requested, def, max) = min(requested ?? def, max)` 才是对的。
    """
    from pai.core.tools import shell

    assert shell.clamp_timeout(9_999_999) == shell.MAX_TIMEOUT_SECONDS
    assert shell.clamp_timeout(300) == 300


def test_the_cap_matches_the_two_reference_implementations():
    """与默认值同源：CC 与 dsh 各自独立把上限定在 600s。"""
    from pai.core.tools import shell

    assert shell.MAX_TIMEOUT_SECONDS == 600


def test_a_negative_timeout_is_reported_not_silently_ignored():
    """静默吞掉非法值 = 模型永远不知道自己传错了（本仓库「静默失败是 bug」）。"""
    from pai.core.tools import shell

    result = shell.bash(command="echo hi", timeout=-5)

    assert "timeout" in result
    assert "hi" not in result          # 没跑，而不是「跑了但用了默认值」


def test_a_model_supplied_timeout_actually_takes_effect():
    """光有钳制不够——传进来的值得真的用上，且超时文案要报**生效后**的秒数。"""
    from pai.core.tools import shell

    result = shell.bash(command="sleep 5", timeout=1)

    assert "超时 1s" in result


def test_bash_schema_exposes_timeout_as_an_optional_integer():
    """schema 与代码同源：参数一加，模型那边就该看得见，且不是必填。"""
    from pai.core.tools import get_tools

    params = get_tools()["bash"].schema()["function"]["parameters"]

    assert params["required"] == ["command"]
    assert params["properties"]["timeout"]["type"] == "integer"
    assert "600" in params["properties"]["timeout"]["description"]   # 上限要写给模型看


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


def test_remember_writes_a_memory_file_and_indexes_it(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        result = memory_tool.remember(name="构建", description="怎么跑测试",
                                      fact="测试用 ./test.sh 跑")
    assert "构建" in result
    assert "测试用 ./test.sh 跑" in (tmp_path / "构建.md").read_text(encoding="utf-8")
    assert "构建.md" in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")


def test_remember_appends_without_clobbering(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="构建", description="怎么跑测试", fact="第一条")
        memory_tool.remember(name="构建", description="怎么跑测试", fact="第二条")
    body = (tmp_path / "构建.md").read_text(encoding="utf-8")
    assert "第一条" in body and "第二条" in body


def test_remember_indexes_each_memory_once(tmp_path):
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="构建", description="怎么跑测试", fact="a")
        memory_tool.remember(name="构建", description="怎么跑测试", fact="b")
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert index.count("构建.md") == 1             # 索引有 200 行上限，别自己撑爆它


def test_remember_rejects_path_traversal(tmp_path):
    """name 是**模型生成的**，且是唯一能指定写盘位置的参数——破了就是任意文件写。"""
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        for evil in ("../../etc/passwd", "/tmp/evil", "sub/dir", "..", ".", "", "   "):
            result = memory_tool.remember(name=evil, description="d", fact="x")
            assert "错误" in result, f"{evil!r} 应被拒绝"
    assert list(tmp_path.iterdir()) == []          # 一个文件都不该被写出来


def test_remember_returns_error_string_instead_of_raising(tmp_path):
    from pai.core.tools import memory_tool

    blocked = tmp_path / "file"
    blocked.write_text("我是文件不是目录", encoding="utf-8")
    with _memory_at(blocked):
        result = memory_tool.remember(name="构建", description="d", fact="x")
    assert "错误" in result                        # 工具错误不 throw（架构约束）


# ---- feature 10 task 3：一事一文件 + frontmatter + 索引投影 ----


def test_remember_writes_frontmatter_that_scan_can_read_back(tmp_path):
    """写侧与扫描侧必须闭环——召回的 manifest 全靠这几个字段。"""
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="构建约定", description="怎么跑测试",
                             fact="用 ./test.sh", type="feedback")
    header = scan_memories(tmp_path)[0]
    assert header.name == "构建约定"
    assert header.description == "怎么跑测试"
    assert header.type == "feedback"
    assert header.modified                          # ISO 戳落在 frontmatter 里


def test_remember_type_defaults_to_project(tmp_path):
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="甲", description="d", fact="f")
    assert scan_memories(tmp_path)[0].type == "project"


def test_same_name_updates_instead_of_creating_a_second_file(tmp_path):
    """CC 的写入纪律：先找已有的、更新它，而不是新建重复的（本次靠工具保证，不靠提示词）。"""
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="构建", description="旧描述", fact="第一条")
        memory_tool.remember(name="构建", description="新描述", fact="第二条")

    memories = [p.name for p in tmp_path.glob("*.md") if p.name != "MEMORY.md"]
    assert memories == ["构建.md"]                  # 只有一篇，不是两篇
    header = scan_memories(tmp_path)[0]
    assert header.description == "新描述"           # 描述覆写
    body = (tmp_path / "构建.md").read_text(encoding="utf-8")
    assert "第一条" in body and "第二条" in body    # 正文追加，不丢信息


def test_origin_session_id_is_recorded_when_injected(tmp_path):
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.set_origin_session("deadbeef")
        try:
            memory_tool.remember(name="甲", description="d", fact="f")
        finally:
            memory_tool.set_origin_session(None)
        memory_tool.remember(name="乙", description="d", fact="f")

    by_name = {h.name: h for h in scan_memories(tmp_path)}
    assert by_name["甲"].origin_session_id == "deadbeef"
    assert by_name["乙"].origin_session_id == ""    # 没注入就没有这个字段，不写空值


def test_deleted_memory_disappears_from_the_index(tmp_path):
    """**投影方案的判据测试**：账本实现（往 MEMORY.md 打补丁）在这条上必红。"""
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="留下的", description="d", fact="f")
        memory_tool.remember(name="要删的", description="d", fact="f")
        (tmp_path / "要删的.md").unlink()           # 人手动删掉一篇
        memory_tool.remember(name="留下的", description="d", fact="再来一条")

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "留下的" in index
    assert "要删的" not in index


def test_index_is_rebuilt_so_hand_edits_are_overwritten(tmp_path):
    """拍板问 2 认下的代价：索引是生成物，手编会被覆盖。文件头把这件事写给人看。"""
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="甲", description="d", fact="f")
        (tmp_path / "MEMORY.md").write_text("我是人手写的一行\n", encoding="utf-8")
        memory_tool.remember(name="乙", description="d", fact="f")

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "我是人手写的一行" not in index
    assert "自动生成" in index and "手改会被覆盖" in index


def test_legacy_file_gets_frontmatter_on_next_write(tmp_path):
    """06 时代的裸 bullet 文件：下次写到它头上时就地补 frontmatter，旧内容不丢。"""
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    (tmp_path / "约定.md").write_text("- 2026-08-10 用户偏好中文回复\n", encoding="utf-8")
    with _memory_at(tmp_path):
        memory_tool.remember(name="约定", description="用户偏好", fact="也偏好简短")

    header = scan_memories(tmp_path)[0]
    assert header.type == "project"                 # 不再是 legacy
    body = (tmp_path / "约定.md").read_text(encoding="utf-8")
    assert "用户偏好中文回复" in body and "也偏好简短" in body


def test_writes_leave_no_temp_files_behind(tmp_path):
    """原子写用同目录临时文件；写完不该留垃圾（半截的临时文件比没有更让人困惑）。"""
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="甲", description="d", fact="f")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["MEMORY.md", "甲.md"]


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
            memory_tool.remember(name="构建", description="d", fact="x")
            memory_tool.remember(name="非法/名字", description="d", fact="x")   # 失败不该通知
        finally:
            memory_tool.set_notifier(None)

    assert [topic for topic, _ in seen] == ["构建"]
    assert seen[0][1] == tmp_path / "构建.md"


# ---- 退出时收割后台进程组（2026-08-10 用户指出） ----


def test_spawned_process_groups_are_reaped_on_exit():
    """`!sleep 300 &` 起的后台进程在 pai 退出后仍然活着——因为 start_new_session
    让它脱离了 pai 的进程组（那正是能整组 killpg 的前提）。所以退出时必须主动收割，
    对齐官方行为「当 Claude Code 退出时，后台任务会自动清理」。
    """
    from pai.core.tools import shell

    # 后台进程必须**不占 stdout 管道**，否则 bash() 会一直等到它结束才返回
    # （管道不 EOF，communicate 收不到流结束）——那样就复现不出「命令已返回、
    # 后台进程仍存活」这个真实场景。重定向掉之后父 shell 立刻退出，命令秒回。
    result = shell.bash(command="sleep 30 >/dev/null 2>&1 & echo PID=$!")
    m = re.search(r"PID=(\d+)", result)
    assert m, f"没拿到后台进程 pid：{result!r}"
    pid = int(m.group(1))
    os.kill(pid, 0)                       # 命令已返回，但它还活着——这就是问题本身

    shell.reap_spawned()

    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)
    raise AssertionError(f"后台进程 {pid} 在收割后仍然存活")


def test_reap_is_idempotent_and_safe_when_empty():
    from pai.core.tools import shell

    shell.reap_spawned()
    shell.reap_spawned()                  # 收割已经空了的登记表不该抛


def test_reap_does_not_raise_on_already_dead_groups():
    from pai.core.tools import shell

    shell.bash(command="true")            # 秒退的命令，进程组早没了
    shell.reap_spawned()                  # 不该因 ProcessLookupError 崩掉


# ---- 原子写：进程中途死掉不该留下半截文件（2026-08-10 用户追问引出） ----


def test_write_failure_leaves_the_original_file_intact(tmp_path, monkeypatch):
    """`open(path,"w")` 是先截断后写——中途死掉就是空文件或半截文件。
    原子写（临时文件 + os.replace）让任何时刻的中断都只有两种结果：旧的完好、或新的完整。
    """
    from pai.core.tools import fs

    target = tmp_path / "重要文件.txt"
    target.write_text("原始内容不能丢", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("模拟：改名前进程死了")

    monkeypatch.setattr(fs.os, "replace", boom)
    # 走 Tool.run 而不是裸函数：「工具错误不 throw」的契约在**边界上**（D#1），
    # 不在函数内部——裸调当然会抛，那测的不是系统真实行为
    result = get_tools()["write_file"].run(path=str(target), content="新内容")

    assert "错误" in result
    assert target.read_text(encoding="utf-8") == "原始内容不能丢"


def test_edit_failure_leaves_the_original_file_intact(tmp_path, monkeypatch):
    """edit 比 write 更险：原内容此刻只在内存里，截断之后进程一死就彻底没了。"""
    from pai.core.tools import fs

    target = tmp_path / "code.py"
    target.write_text("def a():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(fs.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("死了")))
    result = get_tools()["edit_file"].run(path=str(target), old="return 1", new="return 2")

    assert "错误" in result
    assert target.read_text(encoding="utf-8") == "def a():\n    return 1\n"


def test_no_temp_files_left_behind(tmp_path, monkeypatch):
    from pai.core.tools import fs

    target = tmp_path / "a.txt"
    fs.write_file(path=str(target), content="x")
    fs.edit_file(path=str(target), old="x", new="y")
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]

    monkeypatch.setattr(fs.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("死了")))
    get_tools()["write_file"].run(path=str(target), content="z")
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"], "失败路径也不该留垃圾"


def test_write_preserves_file_mode(tmp_path):
    """临时文件默认权限比原文件严，改名之后不该把可执行位/权限弄丢。"""
    import stat

    from pai.core.tools import fs

    target = tmp_path / "run.sh"
    target.write_text("echo hi\n", encoding="utf-8")
    target.chmod(0o755)

    fs.write_file(path=str(target), content="echo bye\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_update_keeps_the_existing_type_when_not_specified(tmp_path):
    """离线冒烟当场抓到的：更新时不传 type，不该把原来的 feedback 静默降回 project。

    `@tool` 的默认值让「没传」与「传了默认值」无法区分，所以默认值必须是空串，
    再由实现去回落：已有 type > DEFAULT_TYPE。
    """
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="甲", description="d", fact="第一条", type="feedback")
        memory_tool.remember(name="甲", description="d2", fact="第二条")
    assert scan_memories(tmp_path)[0].type == "feedback"


def test_new_memory_without_type_defaults_to_project(tmp_path):
    from pai.core.memory import scan_memories
    from pai.core.tools import memory_tool

    with _memory_at(tmp_path):
        memory_tool.remember(name="乙", description="d", fact="f")
    assert scan_memories(tmp_path)[0].type == "project"


# ---------------------------------------------------------------------------
# feature 11 task 3：工具能力标志
# ---------------------------------------------------------------------------


def test_capabilities_default_to_false_for_undeclared_tools():
    """fail-closed（照 CC 的 buildTool 默认）：新加的工具忘了声明 → 判为不可并发。

    **代价是慢，不是错**——最坏结果是它被串行执行。反过来默认 True 才是危险的。
    """
    from pai.core.tools import Tool

    t = Tool(name="x", description="d", parameters={}, func=lambda: "")
    assert t.read_only({}) is False
    assert t.concurrency_safe({}) is False


def test_capabilities_accept_plain_bools():
    """大多数工具的取值是常量（read_file 永远只读），写 True 就够。"""
    from pai.core.tools import REGISTRY, capabilities_for, tool

    @tool
    def _cap_bool_probe(a: str) -> str:
        """探针。"""
        return a

    capabilities_for(_cap_bool_probe, read_only=True, concurrency_safe=True)
    t = REGISTRY["_cap_bool_probe"]
    assert t.read_only({"a": "1"}) is True
    assert t.concurrency_safe({"a": "1"}) is True


def test_capabilities_accept_callables_that_look_at_args():
    """收 input 而不是静态布尔（照 CC 的 Tool.isReadOnly(input)）：
    bash 是不是只读取决于这次跑 `ls` 还是 `rm`，静态布尔表达不了。

    pai 今天没有这样的工具，但签名要现在就留对，否则将来得改第二次。
    """
    from pai.core.tools import REGISTRY, capabilities_for, tool

    @tool
    def _cap_callable_probe(cmd: str) -> str:
        """探针。"""
        return cmd

    capabilities_for(_cap_callable_probe,
                     read_only=lambda args: args.get("cmd", "").startswith("ls"))
    t = REGISTRY["_cap_callable_probe"]
    assert t.read_only({"cmd": "ls -l"}) is True
    assert t.read_only({"cmd": "rm -rf /"}) is False


def test_capability_raising_is_treated_as_unsafe():
    """照 CC：判定器自己抛异常就当不安全（它的注释点名了 shell 词法解析会失败）。"""
    from pai.core.tools import REGISTRY, capabilities_for, tool

    @tool
    def _cap_boom_probe(a: str) -> str:
        """探针。"""
        return a

    def boom(_args):
        raise RuntimeError("判定器炸了")

    capabilities_for(_cap_boom_probe, read_only=boom, concurrency_safe=boom)
    assert REGISTRY["_cap_boom_probe"].read_only({"a": "x"}) is False


def test_capability_with_non_dict_args_is_unsafe():
    """模型发来的 arguments 可能是 `null` / `[1,2]` / 字符串——
    判定期拿到脏输入是常态（同 get_path 那条注释的理由）。"""
    from pai.core.tools import REGISTRY

    t = REGISTRY["read_file"]
    assert t.read_only(None) is False
    assert t.concurrency_safe([1, 2]) is False


def test_capabilities_for_rejects_unregistered_tools():
    """静默不生效 = 调度静默退回串行，比报错难查得多（同 matcher_for 的理由）。"""
    from pai.core.tools import capabilities_for

    with pytest.raises(ValueError, match="没注册"):
        capabilities_for("no_such_tool_at_all", read_only=True)


def test_builtin_tool_capabilities():
    """六个内置工具的取值钉死。

    `bash` 两个都**不声明**：CC 是 `isConcurrencySafe = isReadOnly(input)`，
    而 pai 没有只读命令判定器（feature 07 明确不做只读免提示集合，TODO 有记），
    前件不存在就不装——不声明本身就是声明。
    """
    from pai.core.tools import all_tools

    tools = all_tools()
    assert tools["read_file"].read_only({"path": "x"}) is True
    assert tools["read_file"].concurrency_safe({"path": "x"}) is True
    for name in ("write_file", "edit_file", "bash", "remember", "ask_user_question"):
        assert tools[name].read_only({}) is False, name
        assert tools[name].concurrency_safe({}) is False, name
    # bash 是「不声明」而不是「声明为 False」——两者行为相同但意图不同，钉死意图
    assert tools["bash"].is_read_only is None
    assert tools["bash"].is_concurrency_safe is None


# ---- R4#T5：注册表必须测试级隔离（2026-08-19 评审）----


def test_the_registry_is_restored_between_tests():
    """`@tool` 是**进程级**注册表：测试里注册的探针工具会漏进后续所有测试。

    实测（本文件跑完之后）：`get_tools()` 里多出
    `_cap_bool_probe` / `_cap_callable_probe` / `_cap_boom_probe` 三个，
    连同它们的 schema 一起被发给假 client。此前靠**字母序**苟活
    （`test_tools` 排在多数文件之后，且后续断言恰好用 `<=` 或按名索引），
    换个随机序插件、或新增一条「精确断言工具集」的测试就当场爆。

    本测试自己注册一个探针**且不清理**——隔离由 conftest 的 autouse fixture
    负责。它下一条测试若还看得见这个探针，说明隔离没生效。
    """
    from typing import Annotated

    @tool
    def _leak_probe(a: Annotated[str, "x"]) -> str:
        """探针：故意不清理。"""
        return a

    assert "_leak_probe" in get_tools()


def test_the_previous_probe_did_not_leak_into_this_test():
    """上一条留下的探针不该出现在这里——这条与它是一对，拆开看都没意义。"""
    assert "_leak_probe" not in get_tools()
    assert set(get_tools()) == {"bash", "read_file", "write_file", "edit_file",
                                "remember", "skill"}, "内置工具集之外不该有别的"


def test_read_file_truncation_tells_the_model_how_to_get_the_rest(tmp_path):
    """截断提示要给出路，不能只报状态（R#17）。

    只说「截断，共 N 字符」的话，模型拿着残缺视图直接去 edit_file——
    它并不知道自己看到的不是全文，也不知道还能怎么读。零成本的修法就是
    在提示语里点名 bash 分段读（同 bash 超时文案那条规矩：报状态之外给做法）。
    """
    from pai.core.tools.fs import MAX_OUTPUT_CHARS, read_file

    p = tmp_path / "big.txt"
    p.write_text("x" * (MAX_OUTPUT_CHARS + 1234), encoding="utf-8")
    out = read_file(path=str(p))

    assert "截断" in out
    assert str(MAX_OUTPUT_CHARS + 1234) in out          # 总量照旧说清
    assert "sed" in out or "bash" in out, "提示语里没有「怎么读到剩下的」"
    assert "edit_file" in out, "没有提醒模型别拿残缺视图去改文件"


def test_a_crashing_capability_judge_leaves_a_trace(capsys):
    """三条退化路径此前完全同形（11 task 3）：未声明 / 参数不是 dict / 判定器抛异常，
    全部返回 False 且不留痕。前两条是常态，第三条是 bug——不留痕的话
    「这个工具确实不安全」与「判定器写错了」在外部一模一样，
    症状只是并发静默退回串行（一次看不出来的性能损失）。

    只喊一次：每次判定都刷一行会把真正要看的输出淹掉（同 EventTrace 落盘失败那条）。
    """
    from pai.core import tools as tools_mod
    from pai.core.tools import REGISTRY, capabilities_for, tool

    @tool
    def _cap_trace_probe(a: str) -> str:
        """探针。"""
        return a

    def boom(_args):
        raise RuntimeError("判定器炸了")

    capabilities_for(_cap_trace_probe, read_only=boom, concurrency_safe=boom)
    tools_mod._CAP_WARNED.clear()
    t = REGISTRY["_cap_trace_probe"]

    assert t.read_only({"a": "1"}) is False        # 行为不变：判不出来就当不安全
    assert t.read_only({"a": "2"}) is False
    err = capsys.readouterr().err
    assert err.count("_cap_trace_probe") == 1, f"要喊、且只喊一次，实际：{err!r}"
    assert "RuntimeError" in err and "判定器炸了" in err


def test_the_normal_degraded_paths_stay_silent(capsys):
    """反向守卫：未声明与参数脏是常态，不许拿它们刷屏——喊多了等于没喊。"""
    from pai.core import tools as tools_mod
    from pai.core.tools import REGISTRY

    tools_mod._CAP_WARNED.clear()
    assert REGISTRY["read_file"].read_only(None) is False       # 参数不是 dict
    assert REGISTRY["write_file"].read_only({"path": "x"}) is False   # 未声明只读
    assert capsys.readouterr().err == ""
