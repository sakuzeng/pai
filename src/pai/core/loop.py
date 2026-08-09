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

from pai.core.compaction import (
    AnchorBook,
    CompactionSettings,
    CompactionState,
    MAX_COMPACT_FAILURES,
    compact,
    context_tokens,
    find_cut_point,
    should_compact,
    usage_fields,
    verify_compaction,
)
from pai.core.session import SessionLog
from pai.core.tools import Tool

# provider 回传 usage 的字段名各家不同，这里只做透传不做归一化：
# 归一化会丢掉 DeepSeek 专有的 prompt_cache_hit/miss_tokens，而那正是我们要的。
USAGE_RECORD_TYPE = "usage"

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
    max_total_tokens: int | None = None,
    session: SessionLog | None = None,
    on_event: Callable[[str], None] = print,
    context_window: int | None = None,
    compaction: CompactionSettings | None = None,
) -> str:
    """跑一次 agent 任务，返回最终回答。

    max_total_tokens 是烧钱熔断：累计用量超过它就在**发下一次请求之前**停，
    因此超支上限被钳制在一次请求内。DeepSeek 平台侧只有并发限速、没有消费限额
    （refs/deepseek-api/quick_start/rate_limit.md），所以这道防线只能自己建。
    None = 不限，此时仅靠 max_steps 兜底。
    provider 不回 usage 时无从累计，预算自动失效——这是已知取舍，不是遗漏。
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    if session:
        for m in messages:
            session.append(m)
    tool_schemas = [t.schema() for t in tools.values()]

    # 上下文大小以 provider 回传的真实值为锚，只估锚之后新增的消息（见 compaction.context_tokens）
    anchors = AnchorBook()
    state = CompactionState()
    spent_tokens = 0

    for step in range(1, max_steps + 1):
        if max_total_tokens is not None and spent_tokens > max_total_tokens:
            return (
                f"已达用量预算：累计 {spent_tokens} token 超过上限 {max_total_tokens}，"
                f"在第 {step} 步发出请求前停止。任务可能未完成。"
            )

        anchor, anchor_index = anchors.latest()
        estimated = context_tokens(
            messages, tool_schemas, anchor=anchor, anchor_index=anchor_index
        )

        compaction_on = compaction is not None and context_window is not None
        if compaction_on and not state.tripped and not state.awaiting_verify \
                and should_compact(estimated, context_window, compaction):
            cut = find_cut_point(messages, anchors.entries,
                                 keep_recent_tokens=compaction.keep_recent_tokens)
            if cut <= 1:
                if len(anchors.entries) < 2:
                    # 正常两步节奏，不是真的没救：compact() 刚清空过锚点簿（D#18/32），
                    # find_cut_point 结构性地需要 ≥2 个锚才能算真实差值
                    # （test_compaction.py::test_returns_1_when_nothing_can_be_cut 钉死），
                    # 只差一轮真实 usage 落盘就能重建第二个锚——本步暂缓，不是警告。
                    on_event(f"🗜️ 压缩后锚点重建中（还差一轮真实 usage），本步暂缓（估算 {estimated}）")
                else:
                    on_event(f"⚠️ 上下文超线（估算 {estimated}）但无可压（超长单轮或预算吞下全部历史），"
                             "不压，靠预算熔断兜底")
            else:
                messages, summary, s_usage = compact(messages, cut=cut, client=client, model=model)
                anchors.reset()                      # 历史被改写，旧锚全部作废（D#18/32）
                state.awaiting_verify = True         # 成败等首次真实 usage（D#34）
                # 摘要请求拍平重发近全窗口，是全系统最贵的单次请求，必须计入预算熔断账
                spent_tokens += s_usage.get("total_tokens") or 0
                after = context_tokens(messages, tool_schemas)
                on_event(f"🗜️ 压缩：切于 {cut}，估算 {estimated} → {after}")
                if session:
                    session.append({"type": "compaction", "step": step, "cut": cut,
                                    "summary": summary, "estimated_before": estimated,
                                    "estimated_after": after, "usage": s_usage})
                estimated = after

        response = client.chat.completions.create(
            model=model, messages=messages, tools=tool_schemas
        )
        msg = response.choices[0].message

        usage = usage_fields(response)
        if compaction_on and state.awaiting_verify and usage.get("prompt_tokens") is not None:
            state = verify_compaction(usage["prompt_tokens"], context_window, compaction, state)
            if state.tripped:
                on_event(f"⚠️ 压缩连续失败 {MAX_COMPACT_FAILURES} 次，自动压缩已熔断")
        spent_tokens += usage.get("total_tokens") or 0
        if session and usage:
            session.append(
                {
                    "type": USAGE_RECORD_TYPE,
                    "step": step,
                    "model": model,
                    "estimated_prompt_tokens": estimated,
                    **usage,
                }
            )

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

        # 锚顺延到刚追加的 assistant 之后：它的真实 token 数就是 completion_tokens，不用估
        if usage and usage.get("prompt_tokens") is not None:
            anchors.record(
                len(messages), usage["prompt_tokens"] + (usage.get("completion_tokens") or 0)
            )

        if not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                args, result = {}, f"错误：工具参数不是合法 JSON：{e}"
            else:
                # `null` / `[1,2]` / `"hi"` 都是合法 JSON，但 t.run(**args) 会在进入
                # Tool.run 的 try 之前就抛 TypeError——错误吸收边界在函数内部，
                # 而这一击落在函数门口，必须在这里挡。
                if not isinstance(args, dict):
                    args, result = {}, f"错误：工具参数必须是 JSON 对象，收到 {type(args).__name__}"
                else:
                    t = tools.get(name)
                    result = t.run(**args) if t else f"错误：未知工具 {name}"

            on_event(f"🔧 {name}({args}) → {result[:200]}{'…' if len(result) > 200 else ''}")
            tool_entry = {"role": "tool", "tool_call_id": tc.id, "content": result}
            messages.append(tool_entry)
            if session:
                session.append(tool_entry)

    return f"达到最大步数（{max_steps}），任务可能未完成。"
