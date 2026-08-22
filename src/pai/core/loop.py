"""THE AGENT LOOP。

从 mini-pi 移植，四个升级：
- client/model/tools 依赖注入 → 离线可测（tests/fake_llm.py）
- max_steps 兜底（mini-pi 只有唯一终止条件，模型不停就永不停）
- 工具异常处理下沉到 Tool.run()
- 每条消息同步落 SessionLog（审计地基）

压缩已接线（触发/切/摘/重建/熔断，见 pai.core.compaction）。
交互层已接线（feature 05）：结构化事件（pai.core.events）、steering/followUp
两个注入点（pai.core.queue 说明了两者的语义差别）、中断（pai.core.interrupt）。
权限已接线（feature 07）：`before_tool_call` 返回非 allow 就不执行、把理由回填。
所有新参数都是 keyword-only 且默认 None——不传时行为与接线前逐字相同。
流式已接线（feature 11）：主循环走 `stream=True` + `streaming.assemble`，
增量以 MessageDelta 发出；**侧查询（摘要/召回）刻意仍是非流式**。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable, List, Optional

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
    MessageDelta,
    PermissionDecided,
    RecallFailed,
    SteeringInjected,
    ToolEnd,
    ToolStart,
    render_text,
)
from pai.core.interrupt import InterruptFlag
from pai.core.scheduler import execute, partition
from pai.core.session import SessionLog
from pai.core.streaming import assemble
from pai.core.tools import Tool

if TYPE_CHECKING:                       # loop 只需要 .kind / .reason，不该运行期依赖权限层
    from pai.core.permissions import Decision

# provider 回传 usage 的字段名各家不同，这里只做透传不做归一化：
# 归一化会丢掉 DeepSeek 专有的 prompt_cache_hit/miss_tokens，而那正是我们要的。
USAGE_RECORD_TYPE = "usage"

CANCELLED_RESULT = "(已取消，用户中断)"

# 补上的占位结果：让人和模型都看得出这条是补的，别伪装成工具真跑过。
# CC 有同款（`SYNTHETIC_TOOL_RESULT_PLACEHOLDER`）。
MISSING_RESULT = "(工具结果缺失：本轮因内部错误中断，该调用未产出结果)"

# 被权限层拦下的调用回填给模型的前缀。带前缀是为了让模型一眼看出「这是规矩不让，
# 不是工具坏了」——后者会诱发重试，前者该诱发换做法。
DENIED_PREFIX = "权限被拒绝，该工具调用未执行。原因："

# 分层指令与自动记忆作为 **system 之后的第一条 user 消息**注入（照官方，D#42）。
# 靠内容前缀认出这条消息：messages 会原样发给 provider，加自定义字段是协议外的东西。
INSTRUCTION_HEADER = "# 项目指令与记忆（来自 PAI.md 与自动记忆）"

SYSTEM_PROMPT = (
    "你是一个最小化的编码 agent。你有这些工具：bash（跑命令）、read_file（读文件）、"
    "write_file（覆盖写文件）、edit_file（精确替换文件里的一段文本）。"
    "改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。"
    "一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。"
)


def build_system_prompt(tools: dict) -> str:
    """按实际工具集生成 system prompt（feature 22，R4#E2；形状照 CC 的
    `getSystemPrompt(tools, …)`——装配层算好、loop 收成品）。

    只列名字不抄描述：schema 本来就走请求的 tools 参数，prompt 里复述会漂。
    指导语按「有没有这个工具」条件化（CC 的 enabledTools 同款）；dict 迭代
    顺序即注册顺序，同一工具集生成结果逐字稳定——护住缓存前缀（CC 用
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY 防前缀哈希裂成 2^N 的同一课）。
    不经此函数直接调 run_agent 的老路径仍拿 SYSTEM_PROMPT 常量，逐字不变。
    """
    parts = ["你是一个最小化的编码 agent。"]
    if tools:
        parts.append("你有这些工具：" + "、".join(tools) + "。工具的用法与参数见各自的说明。")
    if "edit_file" in tools:
        parts.append("改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。")
    if "ask_user_question" in tools:
        parts.append("拿不准用户的意图、或不理解自己为什么被拒绝时，"
                     "用 ask_user_question 问真人，不要瞎猜。")
    parts.append("一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。")
    return "".join(parts)


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
    interrupt_flag: Optional[InterruptFlag] = None,
    instructions: Optional[Callable[[], str]] = None,
    anchors: Optional[AnchorBook] = None,
    compaction_state: Optional[CompactionState] = None,
    before_tool_call: Optional[Callable[[str, dict], "Decision"]] = None,
    recall: Optional[Callable[[str], "tuple"]] = None,
    system_prompt: Optional[str] = None,
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
        # system_prompt 由装配层生成（build_system_prompt），不传时用常量逐字不变
        system_entry = {"role": "system",
                        "content": system_prompt if system_prompt is not None
                        else SYSTEM_PROMPT}
        _record(messages, system_entry, session)
    if instructions is not None:
        _inject_instructions(messages, instructions, session)

    user_entry = {"role": "user", "content": task}
    _record(messages, user_entry, session)

    tool_schemas = [t.schema() for t in tools.values()]
    on_event(AgentStart(task=task))

    # 上下文大小以 provider 回传的真实值为锚，只估锚之后新增的消息（见 compaction.context_tokens）。
    # 两者都可注入：REPL 每轮调一次 run_agent，不跨轮持有的话每轮第一次请求都退回纯字符
    # 估算（-33% 误差），且熔断器每轮清零、连续失败永远数不到 3。
    anchors = anchors if anchors is not None else AnchorBook()
    state = compaction_state if compaction_state is not None else CompactionState()
    spent_tokens = 0

    # 按查询召回（feature 10）。loop 不认识记忆/模型/目录，只认识一个回调——
    # 与 instructions 同款做法，装配层把这些关进闭包里。
    # 契约：返回 (要注入的文本, usage)；空文本 = 什么都不插。
    if recall is not None:
        try:
            recalled, r_usage = recall(task)
        except Exception as exc:   # noqa: BLE001 - 召回失败降级成「没召回」，不该把整轮带走
            recalled, r_usage = "", {}
            # 降级不等于闭嘴（R4#22）：逃到这里的是包装层自己的 bug，正常失败
            # 在 make_recall 内已转 on_failure。loop 不持有熔断状态，disabled 说不了真话，恒 False
            on_event(RecallFailed(reason="crashed", detail=repr(exc), disabled=False))
        # 侧查询的 token 与压缩那次一样计进熔断账，否则预算就有个后门
        spent_tokens += (r_usage or {}).get("total_tokens") or 0
        if recalled.strip():
            _extend(messages, [{"role": "user", "content": recalled}], session)

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
                try:
                    messages[:], summary, s_usage = _compacted(
                        messages, cut=cut, client=client, model=model)
                except Exception:   # noqa: BLE001 - 网络边界，什么都可能抛
                    # 摘要请求是全链路最贵的一次（拍平重发近全窗口），也最容易撞
                    # 429/超时，而它此前是唯一不设防的网络调用：一次瞬时错误就逃出
                    # run_agent——REPL 下本轮作废，once 下整个进程带 traceback 崩掉。
                    # 计入熔断同样必须：不计的话 API 持续抖动时每轮都在超线状态下
                    # 重发最贵请求，熔断器永远不跳，等于一台自动烧钱机。
                    # messages 无需回滚——`compact()` 成功返回之后才做替换。
                    state.failures += 1
                    state.tripped = (state.tripped
                                     or state.failures >= MAX_COMPACT_FAILURES)
                    on_event(CompactionSkipped(reason="summarize_failed",
                                               estimated=estimated))
                    if state.tripped:
                        on_event(BreakerTripped(failures=state.failures))
                else:
                    anchors.reset()                  # 历史被改写，旧锚全部作废（D#18/32）
                    state.awaiting_verify = True     # 成败等首次真实 usage（D#34）
                    if instructions is not None:
                        # 压缩重建的是 [system]+[摘要]+[保留尾部]，指令消息在第一条
                        # user 位置必然被摘掉——不重注入就是长会话里 PAI.md 静默失效
                        # （D#42）。重新调用 loader = 从磁盘重读（官方原话），
                        # 顺带让中途改的文件生效。
                        _inject_instructions(messages, instructions, session)
                    # 摘要请求拍平重发近全窗口，是全系统最贵的单次请求，
                    # 必须计入预算熔断账
                    spent_tokens += s_usage.get("total_tokens") or 0
                    after = context_tokens(messages, tool_schemas)
                    on_event(Compacted(cut=cut, before=estimated, after=after))
                    if session:
                        session.append({"type": "compaction", "step": step, "cut": cut,
                                        "summary": summary, "estimated_before": estimated,
                                        "estimated_after": after, "usage": s_usage})
                    estimated = after

        # 主循环走流式（feature 11）。**侧查询不走**——摘要（compaction.summarize）与
        # 召回（recall）的输出没人看，流式只会把装配成本白花一遍。
        stream = client.chat.completions.create(
            model=model, messages=messages, tools=tool_schemas, stream=True
        )
        msg = assemble(stream, on_delta=lambda t: on_event(MessageDelta(text=t)), flag=flag)

        if msg.interrupted:
            # 掐在模型输出中途：**拿不到 usage**（它在末块，而我们没读到末块）。
            # 服务端照样计费，本地永远少算——偏差方向是恒定的，所以必须留痕，
            # 不能让「这一步没数」跟「这一步没花钱」长得一样。
            if session:
                session.append({"type": USAGE_RECORD_TYPE, "step": step,
                                "model": model, "unmetered": True})
            on_event(Interrupted(where="stream"))
            # 刻意**不把那半条 assistant 消息追加进 messages**：它从来不是一次完整的
            # 模型回合，且它的 token 数无从得知（没有 usage），追加进去会让锚点与估算
            # 凭空多出一段没有真实读数的历史。
            return finish("interrupted",
                          f"已中断：第 {step} 步的模型输出被打断，已完成的工作保留在会话里。")

        usage = usage_fields(msg)
        if compaction_on and state.awaiting_verify and usage.get("prompt_tokens") is not None:
            # 已知洞（R4#23，记档备参照）：provider 若从此停返 usage，这个条件
            # 永远不满足，awaiting_verify 永挂 → 压缩触发块（上面查 not awaiting_verify）
            # 永久跳过，且无任何提示。DeepSeek 恒回 usage 故不触发；换 provider 时再兜。
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
        _record(messages, assistant_entry, session)
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
            # **steering 的第二个出口**（feature 18）。少了它，模型这轮直接作答时
            # 队列里的话既不会注入、也不会退化，永久卡死——而收尾那轮通常就不调工具。
            # 形状取自 pi 内层 while 的 `|| pendingMessages.length > 0`
            # （agent-loop.ts:174「队列非空就不许退出」）；CC 在这种轮次上会退化成
            # 轮末新开一个 query（needsFollowUp 是它唯一的循环退出信号），pai 不退化。
            steering = get_steering_messages() if get_steering_messages else []
            if steering:
                # agent 本该停下，但用户排了队——继续跑，而不是让他重开一轮
                _extend(messages, steering, session, on_event)
                continue
            return finish("final", msg.content or "")

        interrupted = False
        # 保序贪心分批（feature 11）：连续的并发安全工具合成一批并行，其余各自成批串行。
        # 非并发批结构上恒为单个调用，`execute` 对单调用不起线程池——
        # 于是 bash 这类要装信号、要管进程组的工具**永远在主线程跑**。
        filled: set = set()
        try:
          for batch in partition(msg.tool_calls, tools):
            # ① 本批权限**串行判完再派发**（与 CC 的主要偏离，见 features/11 spec）。
            #    CC 在 runToolUse 内部判，那样同批的两个并行工具会同时要求问真人，
            #    正好撞上「asker 与 REPL 抢同一个输入流」那条已知缺陷。
            #    批与批之间仍是「先执行前一批、再判后一批」，所以
            #    「工具 A 建了目录、B 才写得进去」这类依赖不受影响。
            decisions: dict = {}
            for tc in batch.calls:
                if flag.is_set():
                    continue                     # 交给 ② 统一回「已取消」
                if tc.function.name not in tools:
                    # 存在性检查排在权限判定**之前**：模型幻觉出一个工具名时，
                    # 它该知道「没这个工具」而不是收到一段权限拒绝理由——
                    # 后者会让它去换姿势重试。交互模式下更糟：会弹一个对话框，
                    # 让真人给一个不存在的工具授权。回填留给 `_run_tool`。
                    continue
                if before_tool_call is not None:
                    decision = before_tool_call(
                        tc.function.name, _safe_args(tc.function.arguments))
                    decisions[tc.id] = decision
                    on_event(PermissionDecided(
                        tool_call_id=tc.id, name=tc.function.name,
                        kind=decision.kind, reason=decision.reason))

            # ② 派发。**所有事件都在主线程发**——不把「事件处理器必须线程安全」
            #    这条隐性要求强加给 modes 层（状态行会往同一个流写 `\r`）。
            #    工作线程里只跑工具本身。
            for tc in batch.calls:
                if not flag.is_set() and _allowed(decisions.get(tc.id)):
                    on_event(ToolStart(tool_call_id=tc.id, name=tc.function.name,
                                       args=_safe_args(tc.function.arguments)))

            def run_one(tc):
                if flag.is_set():
                    # 配对是硬约束：每个 tool_call 都得有结果，缺一条下一轮就是 400
                    # （R#11 有真实复现）。中断不是「跳过剩下的」，是「剩下的各回一条已取消」。
                    return {}, CANCELLED_RESULT, False
                decision = decisions.get(tc.id)
                if not _allowed(decision):
                    # 不执行，但**必须**回一条结果（D#41 同款不变量）。
                    # is_error=False：这不是出错，是按规矩拒绝，模型该据此换做法而非重试。
                    return (_safe_args(tc.function.arguments),
                            f"{DENIED_PREFIX}{decision.reason}", False)
                return _run_tool(tools, tc)

            results = execute(batch, run_one)
            if flag.is_set():
                interrupted = True               # 工具跑到一半被中断（bash 被杀）或批前已置位

            # ③ 按**原顺序**回填：并发的是执行，不是交付。
            #    **先进 messages 再发事件**：事件处理器由 modes 层注入且允许抛
            #    （`trace.compose` 明文不吞渲染器异常），发在前面就等于把不变量
            #    押在渲染器不出错上。
            for tc, (args, result, is_error) in zip(batch.calls, results):
                tool_entry = {"role": "tool", "tool_call_id": tc.id, "content": result}
                _record(messages, tool_entry, session)
                filled.add(tc.id)
                on_event(ToolEnd(tool_call_id=tc.id, name=tc.function.name, args=args,
                                 result=result, is_error=is_error))

        finally:
            # **配对是硬不变量，异常路径上也得成立。** assistant 已经声明了这些
            # tool_call，缺一条下一轮就是 400（R#11 有真实复现）。正常路径每个都
            # 回填过；逃逸时（渲染器抛、asker 抛、参数把 run 打穿）在这里补齐，
            # 补完让异常继续往上走——REPL 的兜底会把 messages 留着，而留下来的
            # 必须是**结构合法**的对话，否则「对话留着」反而把失败固化成永久 400。
            for tc in msg.tool_calls:
                if tc.id in filled:
                    continue
                entry = {"role": "tool", "tool_call_id": tc.id,
                         "content": MISSING_RESULT}
                _record(messages, entry, session)

        if interrupted:
            on_event(Interrupted(where="tool"))
            return finish("interrupted",
                          f"已中断：第 {step} 步的工具执行被终止，已完成的工作保留在会话里。")

        if get_steering_messages:
            # 注入点在**本轮所有工具结果都回填之后**：插在中间会劈开 tool_calls 与
            # 它的结果，配对当场断裂
            _extend(messages, get_steering_messages(), session, on_event)

    return finish("max_steps", f"达到最大步数（{max_steps}），任务可能未完成。")


def _instruction_message(text: str) -> dict:
    return {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n{text.strip()}"}


def _has_instructions(messages: List[dict]) -> bool:
    return any(m.get("role") == "user"
               and str(m.get("content") or "").startswith(INSTRUCTION_HEADER)
               for m in messages)


def _record(messages: List[dict], entry: dict, session: SessionLog | None) -> None:
    """「模型可见」的唯一入账口（feature 23，R4#E3）。

    进 messages 的模型可见消息必须同时进 session——此前成对 append 散在 5 处，
    漏一半不会红。对应 CC 的 `recordTranscript`（sessionStorage.ts 唯一收口）；
    它另有按消息 uuid 的幂等增量，pai 的消息没有身份字段，那半归 R4#A1。
    仅两类写入不走这里：`type` 旁账记录（本就不是模型可见的），以及
    `_inject_instructions`（它是 insert 不是 append——插在 system 之后；
    首次注入时刻早于一切后续追加，落盘顺序与最终列表顺序一致，
    压缩后的重注入则整个会话已被 replay_messages 拒收）。
    不变量测试：test_session_replay_equals_the_model_visible_messages。
    """
    messages.append(entry)
    if session:
        session.append(entry)


def _inject_instructions(messages: List[dict], loader: Callable[[], str],
                         session: SessionLog | None) -> None:
    """插在 system 之后。空指令不插——塞一条空 user 消息是白烧 token 且让模型困惑。

    续用同一份 messages（REPL 多轮）时不重复插：靠 INSTRUCTION_HEADER 前缀识别。
    """
    if _has_instructions(messages):
        return
    text = loader() or ""
    if not text.strip():
        return
    entry = _instruction_message(text)
    at = 1 if messages and messages[0].get("role") == "system" else 0
    messages.insert(at, entry)
    if session:
        session.append(entry)


def _adopt(state: CompactionState, updated: CompactionState) -> None:
    """把新算出的熔断状态写回同一个对象——状态的身份由调用方持有。"""
    state.failures = updated.failures
    state.awaiting_verify = updated.awaiting_verify
    state.tripped = updated.tripped


def _extend(messages: List[dict], extra: List[dict], session: SessionLog | None,
            on_event: Optional[Callable[[AgentEvent], None]] = None) -> None:
    """追加消息，**并在追加完成之后**发一条 SteeringInjected（feature 18 T2.5）。

    事件在循环之后发而不是每条一次：语义是「这一批已经进上下文了」。
    `on_event=None` 时静默追加——`_inject_instructions` 那类系统注入不是用户插话，
    不该顶着 steering 的名义上屏。
    """
    for m in extra:
        _record(messages, m, session)
    if on_event is not None and extra:
        on_event(SteeringInjected(
            texts=tuple(str(m.get("content") or "") for m in extra)))


def _allowed(decision) -> bool:
    """没有权限层（decision is None）= 放行。这是 `before_tool_call` 默认不传时的既有语义。"""
    return decision is None or decision.kind == "allow"


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
    if "self" in args:
        # 同一击的另一个形状：`{"self": …}` **是**合法对象，躲过了上面那道检查，
        # 却会让绑定方法 `t.run` 收到两个 self 而在门口抛 TypeError。
        return args, "错误：参数名 self 非法（它会与工具对象本身撞车）", True
    t = tools.get(name)
    if not t:
        return args, f"错误：未知工具 {name}", True
    return args, t.run(**args), False


def _compacted(messages: List[dict], *, cut: int, client, model: str) -> tuple:
    """compact 返回新列表，但调用方（可能是 REPL）持有的是原列表对象——
    必须原地替换内容，不能换绑变量，否则中断/续轮时拿到的还是压缩前的历史。"""
    return compact(messages, cut=cut, client=client, model=model)
