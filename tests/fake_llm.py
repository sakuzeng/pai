"""假 LLM provider：不联网、不花钱地测 loop（学 pi 的 faux provider 模式）。

用法：FakeClient([turn1, turn2, ...])，每个 turn 是脚本化的一次模型回复：
- {"tool_calls": [("bash", '{"command": "ls"}')]} 表示模型发起工具调用
- {"content": "done"} 表示模型给出最终文本
FakeClient 会记录每次收到的 messages / tools，供断言。
"""

import itertools
from types import SimpleNamespace


def _make_response(turn: dict, call_id_counter) -> SimpleNamespace:
    tool_calls = None
    if turn.get("tool_calls"):
        tool_calls = [
            SimpleNamespace(
                id=f"call_{next(call_id_counter)}",
                function=SimpleNamespace(name=name, arguments=args),
            )
            for name, args in turn["tool_calls"]
        ]
    msg = SimpleNamespace(content=turn.get("content"), tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeClient:
    def __init__(self, script: list[dict]):
        self._script = list(script)
        self._ids = itertools.count(1)
        self.requests: list[dict] = []  # 每次 create 收到的 kwargs，供断言
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs) -> SimpleNamespace:
        self.requests.append(kwargs)
        if not self._script:
            raise AssertionError("FakeClient 脚本已耗尽，loop 比预期多调了一次模型")
        return _make_response(self._script.pop(0), self._ids)
