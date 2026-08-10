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


def _chunk(*, delta=None, finish_reason=None, usage=None, choices=None) -> SimpleNamespace:
    if choices is None:
        choices = [SimpleNamespace(delta=SimpleNamespace(**(delta or {})),
                                   finish_reason=finish_reason, index=0)]
    return SimpleNamespace(choices=choices, usage=usage)


def _tool_call_chunks(tool_calls, call_id_counter):
    """按**实测**的真实形状发：`id`/`name` 只在该 index 的首块，`arguments` 分片发。

    分片而不是整块，是因为「拿到 delta 就 json.loads」这个 bug 只有分片才测得出来
    （真实探针里 16 个字符分了 9 块）。这里按 3 字符切，足以证伪。
    """
    for index, (name, args) in enumerate(tool_calls):
        yield _chunk(delta={"tool_calls": [SimpleNamespace(
            index=index, id=f"call_{next(call_id_counter)}",
            function=SimpleNamespace(name=name, arguments=""))]})
        for i in range(0, len(args), 3):
            yield _chunk(delta={"tool_calls": [SimpleNamespace(
                index=index, id=None,
                function=SimpleNamespace(name=None, arguments=args[i:i + 3]))]})


def _chunks_for(turn: dict, call_id_counter):
    """把脚本化的一轮拆成 chunk 序列。

    默认 **DeepSeek 形状**：usage 挂在带 `finish_reason` 的末块上，该块 `choices` **非空**
    （实测如此，且与 DeepSeek 自己的文档不符）。
    `turn["usage_shape"] == "openai"` 时改用标准形状：usage 在一个 `choices` 为空数组的
    独立块上。两种都要能造，否则装配器「不许有分支偏好」那条无从对照。
    """
    content = turn.get("content")
    if content:
        for i in range(0, len(content), 2):
            yield _chunk(delta={"content": content[i:i + 2]})
    if turn.get("tool_calls"):
        for c in _tool_call_chunks(turn["tool_calls"], call_id_counter):
            yield c

    finish_reason = "tool_calls" if turn.get("tool_calls") else "stop"
    usage = turn.get("usage")
    if usage and turn.get("usage_shape") == "openai":
        yield _chunk(delta={}, finish_reason=finish_reason)
        yield _chunk(choices=[], usage=usage)
    else:
        yield _chunk(delta={}, finish_reason=finish_reason, usage=usage)


class FakeClient:
    def __init__(self, script: list[dict]):
        self._script = list(script)
        self._ids = itertools.count(1)
        self.requests: list[dict] = []  # 每次 create 收到的 kwargs，供断言
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        # 必须深拷贝：loop 是原地 append 到同一个 messages 列表的，直接存引用会让
        # 每次记录都指向最终状态——"第 N 次请求发了什么"就永远断言不出来。
        self.requests.append(copy.deepcopy(kwargs))
        if not self._script:
            raise AssertionError("FakeClient 脚本已耗尽，loop 比预期多调了一次模型")
        turn = self._script.pop(0)
        if kwargs.get("stream"):
            return _chunks_for(turn, self._ids)
        return _make_response(turn, self._ids)
