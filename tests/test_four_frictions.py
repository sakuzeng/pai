"""feature 53：feature 45 真用清单最后四条（预算、计时、footer、权限文案）。

四条互不相干，放一个文件是因为它们同属一次交付；每条一节。
"""

import time
from typing import List

import pytest

from fake_llm import FakeClient
from helpers import OPEN_RULES, scripted_reader

from pai.core.events import AgentEnd, AgentStart, ToolEnd, ToolStart
from pai.modes.statusline import _ESCAPES, display_width
from pai.tui.dock import Dock


def plain(text: str) -> str:
    return _ESCAPES.sub("", text)


# ---- 1. 默认预算与撞顶提示（45-C3）-----------------------------------------

def test_default_budget_is_half_a_million():
    """20 万撑不过一个中等任务：实测 11 步的真实任务烧到 131820，
    用户 2026-09-10 那次 217839 撞顶。50 万在 v4-flash 上最坏约 1 元。"""
    import sys

    import pai.cli as cli

    seen = {}
    original = cli.run_once
    try:
        cli.run_once = lambda *a, **kw: seen.update(kw)
        sys.argv = ["pai", "做点什么"]
        cli.main()
    finally:
        cli.run_once = original
    assert seen["max_total_tokens"] == 500_000


def test_hitting_the_budget_says_how_to_continue(tmp_path, monkeypatch):
    """撞顶那句话要说清三件事：停在第几步、再说一句就接着做、怎么放宽。
    「再说一句就接着做」现在就成立（`spent_tokens` 是 run_agent 的局部变量，
    REPL 下一轮重新计数），只是从来没人说过。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    # 预算检查在**发下一次请求之前**（D#22），所以要跑到第二步才触发：
    # 第一轮调个工具，usage 回一个超过上限的数
    script = [{"content": "", "tool_calls": [{"name": "read_file",
                                              "arguments": {"path": "x.txt"}}],
               "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}},
              {"content": "不该跑到这里"}]
    joined = run_agent("干活", client=FakeClient(script), model="fake",
                       tools=get_tools(["read_file"]), max_total_tokens=1,
                       on_event=lambda e: None, session=None)
    assert "第 2 步" in joined
    assert "再说一句" in joined or "接着做" in joined, joined
    assert "--max-tokens" in joined, joined


def test_once_mode_does_not_promise_a_next_turn(tmp_path, monkeypatch):
    """单次模式没有下一轮，不能说「再说一句就接着做」——那是空头支票。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [{"content": "", "tool_calls": [{"name": "read_file",
                                              "arguments": {"path": "x.txt"}}],
               "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}},
              {"content": "不该跑到这里"}]
    text = run_agent("干活", client=FakeClient(script), model="fake",
                     tools=get_tools(["read_file"]), max_total_tokens=1,
                     on_event=lambda e: None, session=None, interactive=False)
    assert "再说一句" not in text and "--max-tokens" in text


# ---- 2. 等人回答的时间不算进用时（45-C2）-----------------------------------

class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_waiting_for_a_human_does_not_count_as_working_time():
    """真跑显示 `⠹ 3m59s`，其中 3m55s 是权限弹窗在等人。等人时该停表。"""
    clock = Clock()
    dock = Dock(now=clock)
    dock.handle(AgentStart(task="t"))
    clock.now += 5                      # 真干了 5 秒
    dock.pause_clock()
    clock.now += 235                    # 等人 3m55s
    dock.resume_clock()
    clock.now += 2                      # 又干了 2 秒
    assert "7s" in plain(dock.status_line(80)), plain(dock.status_line(80))
    summary = plain(dock.handle(AgentEnd(reason="final", text="")) or "")
    assert "7s" in summary and "3m" not in summary, summary


def test_the_clock_is_not_paused_twice_by_nested_asks():
    """一轮里可能连着弹两个框（权限 + 提问）。第二次 pause 不能把第一次的起点冲掉。"""
    clock = Clock()
    dock = Dock(now=clock)
    dock.handle(AgentStart(task="t"))
    dock.pause_clock()
    clock.now += 10
    dock.pause_clock()                  # 重复暂停：无操作
    clock.now += 10
    dock.resume_clock()
    clock.now += 3
    assert "3s" in plain(dock.status_line(80))


def test_resume_without_pause_is_a_no_op():
    clock = Clock()
    dock = Dock(now=clock)
    dock.handle(AgentStart(task="t"))
    clock.now += 4
    dock.resume_clock()
    assert "4s" in plain(dock.status_line(80))


def test_the_asker_pauses_the_clock_end_to_end(tmp_path, monkeypatch):
    """接线断言：装配层问真人的那条路上要真的调到 pause/resume，
    否则 dock 上的方法只是摆设（feature 16 真跑那次的教训：测试造了个替身）。"""
    import inspect

    from pai.modes import interactive

    source = inspect.getsource(interactive._run_tui)
    assert "pause_clock" in source and "resume_clock" in source


# ---- 3. 长路径不再挤掉模型与上下文（45-B3）---------------------------------

def test_a_long_cwd_keeps_the_model_and_context_visible():
    dock = Dock()
    dock.set_cwd("/Users/sakuzeng/improve/coding/agent/projects/pai")
    dock.set_mode("default")
    dock.set_model("deepseek-v4-flash")
    dock.set_context(120_000, 1_000_000)
    line = plain(dock.footer_lines(80)[0])
    assert "deepseek-v4-flash" in line, line
    assert "%" in line, line
    assert display_width(line) <= 80


def test_the_shortened_path_keeps_the_last_segment():
    """中间省略而不是尾部截断：用户最需要知道的是「我在哪个项目」。"""
    dock = Dock()
    import os

    dock.set_cwd(os.path.expanduser("~/improve/coding/agent/projects/pai"))
    dock.set_mode("default")
    dock.set_model("deepseek-v4-flash")
    dock.set_context(120_000, 1_000_000)
    line = plain(dock.footer_lines(60)[0])
    assert line.lstrip().startswith("~"), line
    assert "/pai" in line and "…" in line, line


def test_a_short_cwd_is_not_shortened():
    """反向守卫：装得下就别省略——每次都省略等于没省略。"""
    dock = Dock()
    dock.set_cwd("/tmp/proj")
    dock.set_model("m")
    line = plain(dock.footer_lines(80)[0])
    assert "…" not in line and "/tmp/proj" in line


# ---- 4. 权限弹窗说人话（45-C1）---------------------------------------------

def _reason(tool_name: str, args: dict, **kw) -> str:
    from pai.core.permissions import RuleSet, WorkingDirs, decide
    from pai.core.tools import get_tools

    tools = get_tools()
    decision = decide(tool_name, args, RuleSet.from_lists(), tools=tools,
                      working_dirs=kw.get("working_dirs", WorkingDirs(startup_cwd="/work")),
                      home=kw.get("home", "/home/u"))
    return decision.reason


def test_bash_asks_in_plain_words():
    """原文是「`bash` 不参与工作目录边界判定（未声明路径语义），按最保守处理」——
    对用户讲 D#52 的实现细节，既没说清风险也没给出路。"""
    reason = _reason("bash", {"command": "ls"})
    assert "未声明路径语义" not in reason and "边界判定" not in reason, reason
    assert "任意" in reason or "哪些文件" in reason, reason        # 为什么问 + 允许后会怎样
    assert "settings.json" in reason or "allow" in reason, reason  # 怎么配才不再问


def test_reading_outside_the_workdir_says_where_and_how_to_allow():
    reason = _reason("read_file", {"path": "/elsewhere/x.py"})
    assert "/work" in reason and "/elsewhere/x.py" in reason, reason
    assert "additionalDirectories" in reason, reason


def test_writing_says_what_changes_and_how_to_stop_being_asked():
    reason = _reason("write_file", {"path": "/work/x.py", "content": "x"})
    assert "acceptEdits" in reason, reason


def test_a_dangerous_write_says_it_cannot_be_turned_off():
    reason = _reason("write_file", {"path": "/home/u/.bashrc", "content": "x"},
                     home="/home/u")
    assert "退出后" in reason or "继续" in reason, reason
    assert "任何" in reason and ("关不掉" in reason or "都会问" in reason), reason


def test_permissions_command_shows_the_same_words():
    """`/permissions` 与弹窗是同一件事的两个出口，不能一个说人话一个说术语。"""
    from pai.modes.commands import _handle_command

    printed: List[str] = []
    _handle_command("/permissions", out=printed.append, messages=[], anchors=None,
                    state=None, tools=None, client=None, model="m", compaction=None,
                    context_window=1000, rules=OPEN_RULES)
    text = "\n".join(printed)
    assert "未声明路径语义" not in text, text
