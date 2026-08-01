"""THE AGENT LOOP。

从 mini-pi 移植，四个升级：
- client/model/tools 依赖注入 → 离线可测（tests/fake_llm.py）
- max_steps 兜底（mini-pi 只有唯一终止条件，模型不停就永不停）
- 工具异常处理下沉到 Tool.run()
- 每条消息同步落 SessionLog（审计地基）

刻意还没有的（路线图阶段任务）：压缩、权限钩子、流式、循环检测。
"""

from __future__ import annotations

import json
from typing import Callable

from pai.session import SessionLog
from pai.tools import Tool

SYSTEM_PROMPT = (
    "你是一个最小化的编码 agent。你有这些工具：bash（跑命令）、read_file（读文件）、"
    "write_file（覆盖写文件）、edit_file（精确替换文件里的一段文本）。"
    "改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。"
    "一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。"
)


def run_agent(
    task: str,
    *,
    client,
    model: str,
    tools: dict[str, Tool],
    max_steps: int = 20,
    session: SessionLog | None = None,
    on_event: Callable[[str], None] = print,
) -> str:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    if session:
        for m in messages:
            session.append(m)
    tool_schemas = [t.schema() for t in tools.values()]

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=tool_schemas
        )
        msg = response.choices[0].message

        assistant_entry: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)
        if session:
            session.append(assistant_entry)

        if not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                args, result = {}, f"错误：工具参数不是合法 JSON：{e}"
            else:
                t = tools.get(name)
                result = t.run(**args) if t else f"错误：未知工具 {name}"

            on_event(f"🔧 {name}({args}) → {result[:200]}{'…' if len(result) > 200 else ''}")
            tool_entry = {"role": "tool", "tool_call_id": tc.id, "content": result}
            messages.append(tool_entry)
            if session:
                session.append(tool_entry)

    return f"达到最大步数（{max_steps}），任务可能未完成。"
