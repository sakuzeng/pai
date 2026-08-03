"""假 LLM provider：不联网、不花钱地测 loop（学 pi 的 faux provider 模式）。

用法：FakeClient([turn1, turn2, ...])，每个 turn 是脚本化的一次模型回复：
- {"tool_calls": [("bash", '{"command": "ls"}')]} 表示模型发起工具调用
- {"content": "done"} 表示模型给出最终文本
- {"usage": {...}} 可选，模拟 provider 回传的用量；不写则该轮无 usage（真实 API 也可能不回）
FakeClient 会记录每次收到的 messages / tools，供断言。
"""

import copy
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
    # 真实 SDK 回的是 pydantic 对象，字段以属性暴露；这里用 SimpleNamespace 同构模拟
    usage = SimpleNamespace(**turn["usage"]) if turn.get("usage") else None
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


class FakeClient:
    def __init__(self, script: list[dict]):
        self._script = list(script)
        self._ids = itertools.count(1)
        self.requests: list[dict] = []  # 每次 create 收到的 kwargs，供断言
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs) -> SimpleNamespace:
        # 必须深拷贝：loop 是原地 append 到同一个 messages 列表的，直接存引用会让
        # 每次记录都指向最终状态——"第 N 次请求发了什么"就永远断言不出来。
        self.requests.append(copy.deepcopy(kwargs))
        if not self._script:
            raise AssertionError("FakeClient 脚本已耗尽，loop 比预期多调了一次模型")
        return _make_response(self._script.pop(0), self._ids)
