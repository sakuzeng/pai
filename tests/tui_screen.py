"""测试用的终端模拟器入口。

实现已升为一等公民 `src/pai/tui/screen.py`（feature 14）——
**回放出图与测试断言共用同一份**，否则「测试全绿」与「图上是对的」会各说各话。
本文件只做转发，保持 747 条既有测试的导入路径不变。
"""

from pai.tui.screen import Cell, VirtualScreen  # noqa: F401
