"""THE AGENT LOOP。

从 mini-pi 移植，四个升级：
- client/model/tools 依赖注入 → 离线可测（tests/fake_llm.py）
- max_steps 兜底（mini-pi 只有唯一终止条件，模型不停就永不停）
- 工具异常处理下沉到 Tool.run()
- 每条消息同步落 SessionLog（审计地基）

压缩已接线（触发/切/摘/重建/熔断，见 pai.core.compaction）。
交互层已接线（feature 05）：结构化事件（pai.core.events）、steering/followUp
两个注入点（pai.core.queue 说明了两者的语义差别）、中断（pai.core.interrupt）。
所有新参数都是 keyword-only 且默认 None——不传时行为与接线前逐字相同。
刻意还没有的（路线图阶段任务）：权限钩子、流式。
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from pai.core import interrupt as interrupt_module
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
from pai.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    AssistantMessage,
    BreakerTripped,
    Compacted,
    CompactionSkipped,
    Interrupted,
    ToolEnd,
    ToolStart,
    render_text,
)
from pai.core.interrupt import InterruptFlag
from pai.core.session import SessionLog
from pai.core.tools import Tool

# provider 回传 usage 的字段名各家不同，这里只做透传不做归一化：
# 归一化会丢掉 DeepSeek 专有的 prompt_cache_hit/miss_tokens，而那正是我们要的。
USAGE_RECORD_TYPE = "usage"

CANCELLED_RESULT = "(已取消，用户中断)"

SYSTEM_PROMPT = (
    "你是一个最小化的编码 agent。你有这些工具：bash（跑命令）、read_file（读文件）、"
    "write_file（覆盖写文件）、edit_file（精确替换文件里的一段文本）。"
    "改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。"
    "一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。"
)


def print_event(event: AgentEvent) -> None:
    """默认事件处理器：渲染成中文一行打印。None 表示这个事件默认不出声。"""
    text = render_text(event)
    if text is not None:
        print(text)


def run_agent(
    task: str,
    *,
    client,
    model: str,
    tools: dict[str, Tool],
    max_steps: int = 20,
    max_total_tokens: int | None = None,
    session: SessionLog | None = None,
    on_event: Callable[[AgentEvent], None] = print_event,
    context_window: int | None = None,
    compaction: CompactionSettings | None = None,
    messages: Optional[List[dict]] = None,
    get_steering_messages: Optional[Callable[[], List[dict]]] = None,
    get_follow_up_messages: Optional[Callable[[], List[dict]]] = None,
    interrupt_flag: Optional[InterruptFlag] = None,
    anchors: Optional[AnchorBook] = None,
    compaction_state: Optional[CompactionState] = None,
) -> str:
    """跑一次 agent 任务，返回最终回答。

    max_total_tokens 是烧钱熔断：累计用量超过它就在**发下一次请求之前**停，
    因此超支上限被钳制在一次请求内。DeepSeek 平台侧只有并发限速、没有消费限额
    （refs/deepseek-api/quick_start/rate_limit.md），所以这道防线只能自己建。
    None = 不限，此时仅靠 max_steps 兜底。
    provider 不回 usage 时无从累计，预算自动失效——这是已知取舍，不是遗漏。

    messages 传入即续用（REPL 的多轮对话共享同一份列表，system 不重建），
    task 作为新的 user 消息追加。中断时这份列表原样留在调用方手里——
    「保留迄今完成的工作」就是靠调用方持有它兑现的。
    """
    flag = interrupt_flag if interrupt_flag is not None else interrupt_module.current()

    if messages is None:
        messages = []
    if not messages:
        system_entry = {"role": "system", "content": SYSTEM_PROMPT}
        messages.append(system_entry)
        if session:
            session.append(system_entry)
    user_entry = {"role": "user", "content": task}
    messages.append(user_entry)
    if session:
        session.append(user_entry)

    tool_schemas = [t.schema() for t in tools.values()]
    on_event(AgentStart(task=task))

    # 上下文大小以 provider 回传的真实值为锚，只估锚之后新增的消息（见 compaction.context_tokens）。
    # 两者都可注入：REPL 每轮调一次 run_agent，不跨轮持有的话每轮第一次请求都退回纯字符
    # 估算（-33% 误差），且熔断器每轮清零、连续失败永远数不到 3。
    anchors = anchors if anchors is not None else AnchorBook()
    state = compaction_state if compaction_state is not None else CompactionState()
    spent_tokens = 0

    def finish(reason: str, text: str) -> str:
        on_event(AgentEnd(reason=reason, text=text))
        return text

    for step in range(1, max_steps + 1):
        if flag.is_set():
            on_event(Interrupted(where="step"))
            return finish("interrupted",
                          f"已中断：在第 {step} 步发出请求前停止，已完成的工作保留在会话里。")

        if max_total_tokens is not None and spent_tokens > max_total_tokens:
            return finish("budget", (
                f"已达用量预算：累计 {spent_tokens} token 超过上限 {max_total_tokens}，"
                f"在第 {step} 步发出请求前停止。任务可能未完成。"
            ))

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
                    on_event(CompactionSkipped(reason="anchors_pending", estimated=estimated))
                else:
                    on_event(CompactionSkipped(reason="nothing_to_cut", estimated=estimated))
            else:
                messages[:], summary, s_usage = _compacted(
                    messages, cut=cut, client=client, model=model)
                anchors.reset()                      # 历史被改写，旧锚全部作废（D#18/32）
                state.awaiting_verify = True         # 成败等首次真实 usage（D#34）
                # 摘要请求拍平重发近全窗口，是全系统最贵的单次请求，必须计入预算熔断账
                spent_tokens += s_usage.get("total_tokens") or 0
                after = context_tokens(messages, tool_schemas)
                on_event(Compacted(cut=cut, before=estimated, after=after))
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
            # verify_compaction 返回新对象；这里必须**写回同一个 state**而不是换绑，
            # 否则注入方（REPL 跨轮持有）看不到失败计数，熔断器等于每轮清零
            _adopt(state, verify_compaction(
                usage["prompt_tokens"], context_window, compaction, state))
            if state.tripped:
                on_event(BreakerTripped(failures=MAX_COMPACT_FAILURES))
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
        on_event(AssistantMessage(
            content=msg.content,
            tool_call_names=tuple(tc.function.name for tc in (msg.tool_calls or [])),
        ))

        # 锚顺延到刚追加的 assistant 之后：它的真实 token 数就是 completion_tokens，不用估
        if usage and usage.get("prompt_tokens") is not None:
            anchors.record(
                len(messages), usage["prompt_tokens"] + (usage.get("completion_tokens") or 0)
            )

        if not msg.tool_calls:
            follow_ups = get_follow_up_messages() if get_follow_up_messages else []
            if follow_ups:
                # agent 本该停下，但用户排了队——继续跑，而不是让他重开一轮
                _extend(messages, follow_ups, session)
                continue
            return finish("final", msg.content or "")

        interrupted = False
        for tc in msg.tool_calls:
            if flag.is_set():
                # 配对是硬约束：每个 tool_call 都得有结果，缺一条下一轮就是 400（R#11
                # 有真实复现）。所以中断不是「跳过剩下的」，是「剩下的各回一条已取消」。
                interrupted = True
                args, result, is_error = {}, CANCELLED_RESULT, False
            else:
                on_event(ToolStart(tool_call_id=tc.id, name=tc.function.name,
                                   args=_safe_args(tc.function.arguments)))
                args, result, is_error = _run_tool(tools, tc)
                if flag.is_set():
                    interrupted = True          # 工具自己跑到一半被中断（bash 被杀）

            on_event(ToolEnd(tool_call_id=tc.id, name=tc.function.name, args=args,
                             result=result, is_error=is_error))
            tool_entry = {"role": "tool", "tool_call_id": tc.id, "content": result}
            messages.append(tool_entry)
            if session:
                session.append(tool_entry)

        if interrupted:
            on_event(Interrupted(where="tool"))
            return finish("interrupted",
                          f"已中断：第 {step} 步的工具执行被终止，已完成的工作保留在会话里。")

        if get_steering_messages:
            # 注入点在**本轮所有工具结果都回填之后**：插在中间会劈开 tool_calls 与
            # 它的结果，配对当场断裂
            _extend(messages, get_steering_messages(), session)

    return finish("max_steps", f"达到最大步数（{max_steps}），任务可能未完成。")


def _adopt(state: CompactionState, updated: CompactionState) -> None:
    """把新算出的熔断状态写回同一个对象——状态的身份由调用方持有。"""
    state.failures = updated.failures
    state.awaiting_verify = updated.awaiting_verify
    state.tripped = updated.tripped


def _extend(messages: List[dict], extra: List[dict], session: SessionLog | None) -> None:
    for m in extra:
        messages.append(m)
        if session:
            session.append(m)


def _safe_args(raw: str) -> dict:
    """只为事件展示用——真正的参数校验在 _run_tool 里，这里坏了就给空字典。"""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_tool(tools: dict[str, Tool], tc) -> tuple:
    """返回 (args, result, is_error)。is_error 只标 loop 自己造的错——工具内部异常被
    Tool.run 吸收成字符串，从这里分辨不出来（events.ToolEnd 的注释写明了这条边界）。"""
    name = tc.function.name
    try:
        args = json.loads(tc.function.arguments)
    except json.JSONDecodeError as e:
        return {}, f"错误：工具参数不是合法 JSON：{e}", True
    # `null` / `[1,2]` / `"hi"` 都是合法 JSON，但 t.run(**args) 会在进入
    # Tool.run 的 try 之前就抛 TypeError——错误吸收边界在函数内部，
    # 而这一击落在函数门口，必须在这里挡。
    if not isinstance(args, dict):
        return {}, f"错误：工具参数必须是 JSON 对象，收到 {type(args).__name__}", True
    t = tools.get(name)
    if not t:
        return args, f"错误：未知工具 {name}", True
    return args, t.run(**args), False


def _compacted(messages: List[dict], *, cut: int, client, model: str) -> tuple:
    """compact 返回新列表，但调用方（可能是 REPL）持有的是原列表对象——
    必须原地替换内容，不能换绑变量，否则中断/续轮时拿到的还是压缩前的历史。"""
    return compact(messages, cut=cut, client=client, model=model)
