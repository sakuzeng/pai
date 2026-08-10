"""AskUserQuestion：让模型在拿不准时问真人，而不是猜着往下做。

两条约束决定了它长这样：
1. `@tool` 只认标量参数（str/int/float/bool），所以候选项只能以 **JSON 数组字符串**过来——
   这不是偷懒，是「schema 与代码同源」的直接后果，描述里必须对模型讲清楚格式。
2. 真人问答通道由装配层注入（REPL 注入真人、测试注入假 asker）。注入点是模块级的，
   理由与 pai.core.interrupt 相同：给函数加参数就会把它发给模型看。

`once` 模式**不注册**这个工具（`get_tools()` 默认排除）——没有真人可问却把它摆出来，
等于让模型撞空。
"""

from __future__ import annotations

import json
from typing import Annotated, Callable, List, Optional

from pai.core.tools import tool

# (问题, 候选项列表) -> 用户选择的答案
Asker = Callable[[str, List[str]], str]

_ASKER: Optional[Asker] = None


def set_asker(fn: Optional[Asker]) -> None:
    """装配期注入真人问答通道；传 None = 卸载（测试复位靠它）。"""
    global _ASKER
    _ASKER = fn


@tool
def ask_user_question(
    question: Annotated[str, "要问用户的问题，一句话说清楚在纠结什么"],
    options: Annotated[str, '候选项，JSON 数组字符串，至少两项，例如 ["方案A", "方案B"]'],
) -> str:
    """向用户提问并等待真人选择（只有交互模式有真人可问）。"""
    if _ASKER is None:
        return "错误：当前模式没有可问的真人，ask_user_question 只在交互模式可用"
    try:
        parsed = json.loads(options)
    except json.JSONDecodeError as e:
        return f"错误：options 必须是 JSON 数组字符串：{e}"
    if not isinstance(parsed, list) or not all(isinstance(o, str) for o in parsed):
        return f"错误：options 必须是字符串数组，收到 {type(parsed).__name__}"
    if len(parsed) < 2:
        # 只有一个选项的「提问」不是提问，是通知——那用不着打断真人
        return "错误：options 至少要有两个候选项，只有一个就不必问了"
    return _ASKER(question, parsed)
