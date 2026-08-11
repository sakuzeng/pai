"""T5：权限模式运行时可变 + 轮转。

**动工前撞见的结构问题**：模式今天是装配期常量——`make_before_tool_call(..., mode=mode)`
把值烤进闭包，`/mode` 与 shift+tab 运行时改不动。这里先把它变成可读的持有者。

轮转顺序照 CC 的 `getNextPermissionMode`，但去掉 `plan`（本轮不做，留位）
与 `dontAsk`（D#53：它与「无真人」合流，不该出现在给真人按的快捷键上；
CC 的注释同样写着它「尚未暴露在 UI 环里」）。
"""

import pytest

from pai.core.gate import make_before_tool_call
from pai.core.permissions import (
    ACCEPT_EDITS,
    BYPASS,
    DEFAULT_MODE,
    DONT_ASK,
    MODE_CYCLE,
    PermissionModeState,
    RuleSet,
    next_mode,
)


# --- 轮转表 ------------------------------------------------------------

def test_cycle_order():
    assert next_mode(DEFAULT_MODE, bypass_available=True) == ACCEPT_EDITS
    assert next_mode(ACCEPT_EDITS, bypass_available=True) == BYPASS
    assert next_mode(BYPASS, bypass_available=True) == DEFAULT_MODE


def test_bypass_is_skipped_when_unavailable():
    """危险档不是白给的：不可用就跳过，而不是报错。"""
    assert next_mode(ACCEPT_EDITS, bypass_available=False) == DEFAULT_MODE


def test_dont_ask_is_not_in_the_cycle():
    """它与「无真人」合流（D#53），不该出现在给真人按的键上。"""
    assert DONT_ASK not in MODE_CYCLE
    assert next_mode(DONT_ASK, bypass_available=True) == DEFAULT_MODE


def test_cycle_is_data_not_an_if_chain():
    """plan 单独立项时应当只需在表里加一行（本档案问 2 的改判要求）。"""
    assert isinstance(MODE_CYCLE, tuple)
    assert MODE_CYCLE[0] == DEFAULT_MODE


def test_unknown_mode_falls_back_to_default():
    assert next_mode("没听说过", bypass_available=True) == DEFAULT_MODE


# --- 可变持有者 --------------------------------------------------------

def test_state_reports_and_cycles():
    state = PermissionModeState(DEFAULT_MODE)
    assert state() == DEFAULT_MODE
    assert state.cycle(bypass_available=False) == ACCEPT_EDITS
    assert state() == ACCEPT_EDITS


def test_state_set_rejects_unknown_mode():
    state = PermissionModeState()
    with pytest.raises(ValueError):
        state.set("没听说过")


def test_gate_sees_the_new_mode_on_the_very_next_decision():
    """本 task 的要害。同一个 gate 闭包，改完模式**下一次判定**就得用新的。

    注入反证：把 gate 里的模式解析换回捕获的常量，这条必红。
    """
    rules = RuleSet.from_lists()             # 无显式规则：兜底走工作目录边界（写一律问）
    state = PermissionModeState(DEFAULT_MODE)
    gate = make_before_tool_call(rules, asker=None, mode=state)
    write = {"path": "a.txt", "content": "x"}

    # 两次判定的结果必须**不同**，否则这条测试换回捕获常量也照样绿（假绿）
    assert gate("write_file", write).kind == "deny"      # default → ask → 无真人 → deny
    state.set(ACCEPT_EDITS)
    assert gate("write_file", write).kind == "allow"     # acceptEdits → 界内写放行
    state.set(DEFAULT_MODE)
    assert gate("write_file", write).kind == "deny"      # 改回去也要立刻生效


def test_gate_still_accepts_a_plain_string_mode():
    """只加不改语义：once 那条传值的调用路径必须原样能用。"""
    rules = RuleSet.from_lists()
    gate = make_before_tool_call(rules, asker=None, mode=DONT_ASK)
    assert gate("read_file", {"path": "a.txt"}) is not None


def test_gate_accepts_none_as_before():
    rules = RuleSet.from_lists()
    assert make_before_tool_call(rules, asker=None, mode=None) is not None
