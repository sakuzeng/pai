# 11-streaming · 实施计划

spec 见 [spec.md](spec.md)（方案 B）。6 个 task，严格 TDD：先写测试跑红（贴红的输出），
再写实现跑绿（贴绿的数字）。

测试数字一律写成下限（`≥ N passed`）——这是 [feature 09 复盘](../09-20260810-working-dir-boundary/README.md)
留下的教训并已登记 TODO：上一轮 7 个 task 有 4 个实际数与 plan 不符，
把「计划的估算」当成「应该达到的事实」，制造了必然失败的对账。
基线：458 passed, 3 deselected。

## 动工前已核实的两件事（省掉的工作）

1. `render_tool_line` 已经结构性支持多个 `◐` 并列（`statusline.py:66` 的 `running` 是
   `dict[tool_call_id]`，渲染时 `for … in running.values()` 全部展开）。
   它的 docstring 说「pai 一次只跑一个工具，所以不做」——说法过时，代码是对的。
   Task 6 只需补测试钉死 + 订正 docstring，不用重写渲染。
2. 三个进程级全局不需要动（`set_memory_dir` / `set_notifier` / `set_origin_session`）：
   装配期写、执行期只读，线程并发下不构成竞争。TODO 里那条担忧核实后不成立，交付时去登记。

---

## Task 1：`core/streaming.py` 装配器 + 流式假 provider

目标：把 chunk 序列装配成一条与非流式同形状的响应。纯函数，不碰 loop。

测试先行（`tests/test_streaming.py` 新建；`tests/fake_llm.py` 加流式支持是它的前置）：

```python
"""流式装配器。夹具剪裁自真实探针，见
docs/dev/features/11-20260811-streaming/evidence/20260811-流式探针/。"""

import json
import pytest

from pai.core.interrupt import InterruptFlag
from pai.core.streaming import assemble


def _chunk(*, delta=None, finish_reason=None, usage=None, choices=None):
    """构造一个 chunk（SimpleNamespace 同构模拟 SDK 的 pydantic 对象）。
    choices 显式传 [] 用于模拟标准 OpenAI 的「usage 独立块」形状。"""
    from types import SimpleNamespace
    if choices is None:
        choices = [SimpleNamespace(delta=SimpleNamespace(**(delta or {})),
                                   finish_reason=finish_reason, index=0)]
    return SimpleNamespace(choices=choices, usage=usage)


# 真实分片时序，逐字抄自 evidence 的 B_parallel_tool_calls.jsonl（chunk#55-#75），
# 只保留 tool_calls 相关字段。编的字符串测不出「arguments 逐字符分片」这个坑。
REAL_TOOL_FRAGMENTS = [
    {"index": 0, "id": "call_00_U7xgjcyOxXvXbNTPOy2d8207",
     "function": {"name": "get_weather", "arguments": ""}},
    {"index": 0, "function": {"arguments": "{"}},
    {"index": 0, "function": {"arguments": '"'}},
    {"index": 0, "function": {"arguments": "city"}},
    {"index": 0, "function": {"arguments": '"'}},
    {"index": 0, "function": {"arguments": ": "}},
    {"index": 0, "function": {"arguments": '"'}},
    {"index": 0, "function": {"arguments": "北京"}},
    {"index": 0, "function": {"arguments": '"'}},
    {"index": 0, "function": {"arguments": "}"}},
    {"index": 1, "id": "call_01_i1QcRhY1WoHdH1peEnQ12146",
     "function": {"name": "get_population", "arguments": ""}},
    {"index": 1, "function": {"arguments": "{"}},
    {"index": 1, "function": {"arguments": '"'}},
    {"index": 1, "function": {"arguments": "city"}},
    {"index": 1, "function": {"arguments": '"'}},
    {"index": 1, "function": {"arguments": ": "}},
    {"index": 1, "function": {"arguments": '"'}},
    {"index": 1, "function": {"arguments": "上海"}},
    {"index": 1, "function": {"arguments": '"'}},
    {"index": 1, "function": {"arguments": "}"}},
]

# 实测的 usage 形状：在**末块**上，且该块 choices **非空**（带 finish_reason）
DEEPSEEK_USAGE = {"prompt_tokens": 437, "completion_tokens": 129, "total_tokens": 566,
                  "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 437}


def _real_stream():
    for frag in REAL_TOOL_FRAGMENTS:
        yield _chunk(delta={"tool_calls": [frag]})
    yield _chunk(delta={}, finish_reason="tool_calls", usage=DEEPSEEK_USAGE)


def test_assembles_parallel_tool_calls_from_real_fragments():
    r = assemble(_real_stream())
    assert [tc.function.name for tc in r.tool_calls] == ["get_weather", "get_population"]
    assert [tc.id for tc in r.tool_calls] == [
        "call_00_U7xgjcyOxXvXbNTPOy2d8207", "call_01_i1QcRhY1WoHdH1peEnQ12146"]
    # arguments 必须拼完才是合法 JSON——中途任何一块都不是
    assert json.loads(r.tool_calls[0].function.arguments) == {"city": "北京"}
    assert json.loads(r.tool_calls[1].function.arguments) == {"city": "上海"}
    assert r.finish_reason == "tool_calls"


def test_usage_is_found_on_deepseek_shape_last_chunk():
    """DeepSeek 形状：usage 在末块，choices 非空。
    惯用的 `if not chunk.choices: usage = …` 在这里永不触发（实测）。"""
    assert assemble(_real_stream()).usage["total_tokens"] == 566


def test_usage_is_found_on_openai_shape_separate_chunk():
    """标准 OpenAI 形状：usage 在 choices 为空数组的独立块上。
    两种形状**都要取得到**——这是本装配器唯一不许有分支偏好的地方。"""
    chunks = [_chunk(delta={"content": "hi"}),
              _chunk(delta={}, finish_reason="stop"),
              _chunk(choices=[], usage={"total_tokens": 42})]
    assert assemble(iter(chunks)).usage["total_tokens"] == 42


def test_content_deltas_are_streamed_out_in_order():
    seen = []
    r = assemble(iter([_chunk(delta={"content": "你"}), _chunk(delta={"content": "好"}),
                       _chunk(delta={}, finish_reason="stop", usage={"total_tokens": 1})]),
                 on_delta=seen.append)
    assert seen == ["你", "好"]
    assert r.content == "你好"


def test_reasoning_content_does_not_leak_into_content():
    """思考模式默认开（refs/deepseek-api/guides/thinking_mode.md）：
    reasoning_content 是独立字段，混进 content 就会把思考过程当答案发回给模型。"""
    r = assemble(iter([_chunk(delta={"reasoning_content": "想一下"}),
                       _chunk(delta={"content": "答案"}),
                       _chunk(delta={}, finish_reason="stop")]))
    assert r.content == "答案"


def test_interrupt_stops_consuming_and_reports_no_usage():
    """中断掐在流中途：拿不到末块 = 拿不到 usage（实测探针 F）。
    usage 必须是空 dict 而不是瞎猜一个——少算是事实，掩盖它才是 bug。"""
    flag = InterruptFlag()

    def stream():
        yield _chunk(delta={"content": "a"})
        flag.set()
        yield _chunk(delta={"content": "b"})
        yield _chunk(delta={}, finish_reason="stop", usage={"total_tokens": 99})

    r = assemble(stream(), flag=flag)
    assert r.interrupted is True
    assert r.usage == {}
    assert r.finish_reason is None
```

实现（`src/pai/core/streaming.py` 新建）：

```python
"""流式装配：把 chunk 序列装回一条与非流式同形状的响应。

**一次响应 = 一条 assistant 消息**，这条不许改。
CC 走 Anthropic 协议时把每个 content block 变成一条独立记录、共享 message.id，
于是必须再写一个 getAssistantMessageId 把它们认回去，否则上下文估算重复计数
（K streaming/cc-streaming-tools.md 第四节）。那个补丁存在的唯一原因是那个建模选择。
谁将来想为了「边流边显示」把这里拆成多条记录，先读这段。

装配规则全部来自真实探针（features/11 的 evidence），不是从文档推的——
DeepSeek 的实际行为与它自己的文档在 usage 这件事上不一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from pai.core.interrupt import InterruptFlag


@dataclass
class _Function:
    name: str = ""
    arguments: str = ""


@dataclass
class StreamedToolCall:
    """与 SDK 的 tool_call 同形状（.id / .function.name / .function.arguments），
    这样 loop 那一侧一个字都不用改。"""

    id: str = ""
    function: _Function = field(default_factory=_Function)


@dataclass
class StreamedResponse:
    content: Optional[str] = None
    tool_calls: Optional[List[StreamedToolCall]] = None
    finish_reason: Optional[str] = None
    usage: dict = field(default_factory=dict)   # 空 dict = 这次没拿到（中断）
    interrupted: bool = False


def assemble(
    chunks: Iterable,
    *,
    on_delta: Optional[Callable[[str], None]] = None,
    flag: Optional[InterruptFlag] = None,
) -> StreamedResponse:
    parts: List[str] = []
    calls: Dict[int, StreamedToolCall] = {}      # index -> 累积中的调用
    order: List[int] = []                        # 首次出现顺序，dict 顺序不拿来当契约
    finish_reason = None
    usage: dict = {}
    interrupted = False

    for chunk in chunks:
        if flag is not None and flag.is_set():
            interrupted = True
            break

        # usage：**每块都看**，最后一个非空的赢。
        # 不许写成 `if not chunk.choices`——DeepSeek 的末块 choices 非空，那个分支永不触发；
        # 也不许写成「只看末块」——标准 OpenAI 会给一个 choices 为空的独立块。
        # 「每块都看」是唯一同时吃得下两种形状的写法。
        chunk_usage = _as_dict(getattr(chunk, "usage", None))
        if chunk_usage:
            usage = chunk_usage

        for choice in getattr(chunk, "choices", None) or []:
            delta = getattr(choice, "delta", None)
            text = getattr(delta, "content", None) if delta is not None else None
            if text:
                parts.append(text)
                if on_delta is not None:
                    on_delta(text)
            # reasoning_content 是 DeepSeek 思考模式的独立字段，**不并进 content**：
            # 并进去就等于把思考过程当答案发回给模型
            for frag in (getattr(delta, "tool_calls", None) or []) if delta is not None else []:
                _merge_fragment(frag, calls, order)
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

    if interrupted:
        # 中断 = 没读到末块 = 没有 usage。不猜、不补，如实回空。
        return StreamedResponse(content="".join(parts) or None, tool_calls=None,
                                finish_reason=None, usage={}, interrupted=True)

    return StreamedResponse(
        content="".join(parts) or None,
        tool_calls=[calls[i] for i in order] or None,
        finish_reason=finish_reason,
        usage=usage,
    )


def _merge_fragment(frag, calls: Dict[int, StreamedToolCall], order: List[int]) -> None:
    """按 `index` 归并，**不按 id**：id 与 name 只在该 index 的首块出现（实测）。

    `arguments` 只做字符串累加，**中途绝不解析**——实测 `{"city": "北京"}` 这 16 个字符
    分了 9 块发，拿任何一块去 json.loads 都会炸，且炸点取决于分块位置。
    """
    index = getattr(frag, "index", None)
    if index is None:
        index = 0
    if index not in calls:
        calls[index] = StreamedToolCall()
        order.append(index)
    call = calls[index]
    if getattr(frag, "id", None):
        call.id = frag.id
    fn = getattr(frag, "function", None)
    if fn is not None:
        if getattr(fn, "name", None):
            call.function.name = fn.name
        if getattr(fn, "arguments", None):
            call.function.arguments += fn.arguments


def _as_dict(usage) -> dict:
    """与 compaction.usage_fields 同款的三条退化路径（pydantic / dict / namespace）。"""
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return dict(usage)
    return {k: v for k, v in vars(usage).items() if not k.startswith("_")}
```

`tests/fake_llm.py` 加流式（同 task，测试基建）：

```python
def _chunks_for(turn: dict, call_id_counter):
    """把脚本化的一轮拆成 chunk 序列。默认 DeepSeek 形状（usage 在末块、choices 非空）；
    turn["usage_shape"] == "openai" 时改用「choices 为空的独立块」——
    两种形状都要能造，否则 test_usage_is_found_on_openai_shape 无从写起。"""
    ...


def _create(self, **kwargs):
    self.requests.append(copy.deepcopy(kwargs))
    if not self._script:
        raise AssertionError("FakeClient 脚本已耗尽，loop 比预期多调了一次模型")
    turn = self._script.pop(0)
    if kwargs.get("stream"):
        return iter(_chunks_for(turn, self._ids))
    return _make_response(turn, self._ids)
```

验收：红阶段应看到 `ModuleNotFoundError: pai.core.streaming`；绿阶段
`./test.sh` ≥ 465 passed（新增 7 条左右）。

---

## Task 2：loop 改用流式（含中断到流中途 + unmetered 留痕）

目标：`create(stream=True)` → 装配器；除了多出增量事件，loop 的可观察行为逐字不变。

测试先行（追加 `tests/test_loop.py`）：

```python
def test_streaming_produces_identical_messages_and_session_records():
    """同一份脚本，流式与非流式跑出来的 messages / session 记录必须逐字相同。
    这是本 task 的主断言：流式是**传输方式**的改变，不是语义的改变。"""


def test_message_delta_events_are_emitted_in_order():
    """MessageDelta 是 events.py 开头承诺补的那个事件（『等阶段 5 真有一轮内多次增量再补』）。"""


def test_interrupt_mid_stream_stops_before_finishing_the_turn():
    """中断掐在第 N 块：不追加 assistant 消息、不记锚、AgentEnd.reason == 'interrupted'。"""


def test_interrupted_stream_does_not_count_toward_budget_and_leaves_a_trace():
    """中断没有 usage → spent_tokens 不增（现有 `if usage` 天然安全），
    但必须留痕：session 里有一条 {"type": "usage", "unmetered": True}。
    偏差方向是恒定的（总是少算），静默的恒定偏差比随机误差危险。"""
```

实现（`src/pai/core/loop.py` 改动点）：

```python
        stream = client.chat.completions.create(
            model=model, messages=messages, tools=tool_schemas, stream=True
        )
        msg = assemble(stream, on_delta=lambda t: on_event(MessageDelta(text=t)), flag=flag)

        usage = usage_fields(msg)          # msg.usage 是 dict，usage_fields 已覆盖 dict 分支
        if msg.interrupted:
            if session:
                # 被中断的请求服务端照样计费，本地却拿不到数字。不留痕就是静默少算。
                session.append({"type": USAGE_RECORD_TYPE, "step": step,
                                "model": model, "unmetered": True})
            on_event(Interrupted(where="stream"))
            return finish("interrupted",
                          f"已中断：第 {step} 步的模型输出被打断，已完成的工作保留在会话里。")
```

`events.py` 新增：

```python
@dataclass(frozen=True)
class MessageDelta:
    """一轮内的增量文本。events.py 开头写着「等阶段 5 真有『一轮内多次增量』再补」——就是它。

    `render_text` 对它返回 None：增量要**不换行**地写，而 render_text 的契约是「一行」。
    上屏由 modes 层负责（D#39 渲染下放）。
    """

    text: str
```

`Interrupted.where` 的取值从 `("tool", "step")` 扩成 `("tool", "step", "stream")`。

验收：红阶段 `MessageDelta` 未定义 / `stream` kwarg 未传；绿阶段 ≥ 470 passed。

---

## Task 3：能力标志进 `@tool`

目标：`is_read_only` / `is_concurrency_safe` 收 `input` 的函数、默认 `False`。

测试先行（追加 `tests/test_tools.py`）：

```python
def test_capabilities_default_to_false_for_undeclared_tools():
    """fail-closed：新加的工具忘了声明 → 判为不可并发。代价是慢，不是错。"""


def test_capabilities_accept_bool_or_callable():
    """大多数工具是常量（read_file 永远只读），bash 将来要按 command 判——
    两种都收，签名不用改第二次。"""


def test_capability_raising_is_treated_as_unsafe():
    """照 CC：isConcurrencySafe 抛异常就当不安全（它的注释点名了 shell 词法解析会失败）。"""


def test_capability_with_non_dict_args_is_unsafe():
    """模型发来的 arguments 可能是 `null` / `[1,2]`，判定期拿到脏输入是常态。"""


def test_builtin_tool_capabilities():
    """六个内置工具的取值钉死。bash 两个都不声明——CC 是
    isConcurrencySafe = isReadOnly(input)，而 pai 没有只读命令判定器（feature 07 明确不做），
    前件不存在就不装。"""
```

实现（`src/pai/core/tools/__init__.py`）：

```python
# 工具能力标志（feature 11）。与 get_path/access 同一个模式：框架问问题，工具用
# 自己的领域知识回答。**收 input 而不是静态布尔**——bash 是不是只读取决于这次跑
# `ls` 还是 `rm`，静态布尔表达不了（照 CC 的 Tool.isReadOnly(input)）。
Capability = Callable[[dict], bool]


@dataclass
class Tool:
    ...
    is_read_only: Optional[Capability] = None
    is_concurrency_safe: Optional[Capability] = None

    def _ask(self, cap: Optional[Capability], args: dict) -> bool:
        """未声明 / 抛异常 / 参数不是 dict 一律 False。fail-closed 的代价是串行，不是错。"""
        if cap is None or not isinstance(args, dict):
            return False
        try:
            return bool(cap(args))
        except Exception:      # noqa: BLE001 - 照 CC：判定器自己炸了就当不安全
            return False

    def read_only(self, args: dict) -> bool:
        return self._ask(self.is_read_only, args)

    def concurrency_safe(self, args: dict) -> bool:
        return self._ask(self.is_concurrency_safe, args)


def capabilities_for(tool_func, *, read_only=False, concurrency_safe=False) -> None:
    """给已注册的工具挂能力标志，取值可以是 bool 也可以是 `(args) -> bool`。

    与 `path_access_for` / `matcher_for` 不同，这里**不做成装饰器**：那两个装饰的是真的
    getter 函数，而能力标志绝大多数是常量，装饰一个 `lambda args: True` 只是噪音。
    保留 callable 形态是给 bash 将来留的签名口子。
    """
    name = tool_func if isinstance(tool_func, str) else getattr(tool_func, "__name__", "")
    if name not in REGISTRY:
        raise ValueError(f"capabilities_for：工具 {name!r} 没注册，先用 @tool 注册")
    as_cap = lambda v: (v if callable(v) else (lambda _args, _v=v: bool(_v)))
    REGISTRY[name].is_read_only = as_cap(read_only)
    REGISTRY[name].is_concurrency_safe = as_cap(concurrency_safe)
```

各工具模块尾部：`capabilities_for(read_file, read_only=True, concurrency_safe=True)`；
`write_file` / `edit_file` / `remember` / `ask_user_question` 显式 `False, False`（写清楚比默认更好读）；
`bash` 一行都不写（不声明本身就是声明）。

验收：红阶段 `AttributeError: 'Tool' object has no attribute 'read_only'`；
绿阶段 ≥ 475 passed。

---

## Task 4：`core/scheduler.py` 保序贪心分批

目标：纯函数 `partition` + 带线程池的 `execute`，并发的是执行，不是交付。

测试先行（`tests/test_scheduler.py` 新建）：

```python
def test_consecutive_safe_tools_merge_into_one_batch():
    """[read, read, write, read] → 3 批：[read,read] / [write] / [read]。
    照 CC 的 partitionToolCalls：连续的并发安全工具合批，其余各自成批。"""


def test_a_serial_tool_splits_the_batch_order_is_preserved():
    """保序是硬约束：模型发出的顺序有意义（先 read 再 edit），
    调度只在不改变可观察顺序的前提下偷并行。**不重排。**"""


def test_only_read_only_and_concurrency_safe_tools_go_parallel():
    """两个标志都为真才进并发批。

    这不是保守，是把 spec 里那条论证的前提钉死在代码里：
    『按批前置判权限是安全的』依赖『并发批里全是只读工具』。
    只看 concurrency_safe 的话，将来出现一个「并发安全但会写」的工具，
    那条论证会静默失效。"""


def test_results_are_returned_in_input_order_not_completion_order():
    """先完成的不许插队。"""


def test_batch_really_runs_in_parallel():
    """真并发要**可观测地**证明：用 threading.Barrier——两个任务都到齐才放行，
    串行执行会在这里超时死等。不用计时（慢机器上会 flaky）。"""


def test_unknown_tool_is_never_parallel():
    """未知工具名判不出能力 → 串行。判不出来 ≠ 没问题。"""
```

实现（`src/pai/core/scheduler.py` 新建）：

```python
"""工具调度：连续的并发安全工具合成一批并行跑，其余串行。

照 CC 的 `toolOrchestration.ts::partitionToolCalls`——**保序贪心分组，不是重排**。
模型发出的工具顺序是有意义的（先 read_file 再 edit_file），
调度只在不改变可观察顺序的前提下偷并行：**并发的是执行，不是交付**。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, List

# 并发上限。**这个数从哪来、依赖什么前提**（TODO「给照抄来的常数建一条检查习惯」）：
# CC 默认 10 且可用 CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY 调；pai 目前唯一的并发安全
# 工具是 read_file（纯 IO 不吃 CPU），8 是**未实测的经验值**，真实并发度还受限于
# 模型一轮发几个工具（实测见过 3 个）。改它之前先拿数字。
MAX_TOOL_WORKERS = 8


@dataclass
class Batch:
    parallel: bool
    calls: list          # 原始 tool_call 对象，顺序保持


def partition(tool_calls, tools: dict) -> List[Batch]:
    batches: List[Batch] = []
    for tc in tool_calls:
        if _parallelizable(tc, tools) and batches and batches[-1].parallel:
            batches[-1].calls.append(tc)
        else:
            batches.append(Batch(parallel=_parallelizable(tc, tools), calls=[tc]))
    return batches


def _parallelizable(tc, tools: dict) -> bool:
    """**两个标志都要为真**——见 test_only_read_only_and_concurrency_safe_tools_go_parallel
    的 docstring：这是 spec 里「权限按批前置是安全的」那条论证的前提，钉在这里。"""
    tool = tools.get(getattr(tc.function, "name", ""))
    if tool is None:
        return False
    try:
        args = json.loads(tc.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return False
    return tool.read_only(args) and tool.concurrency_safe(args)


def execute(batch: Batch, run_one: Callable, *, max_workers: int = MAX_TOOL_WORKERS) -> list:
    """跑一批，**结果按输入顺序回填**（先完成的不许插队）。"""
    if not batch.parallel or len(batch.calls) == 1:
        return [run_one(tc) for tc in batch.calls]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(batch.calls))) as pool:
        return list(pool.map(run_one, batch.calls))
```

验收：红阶段 `ModuleNotFoundError: pai.core.scheduler`；绿阶段 ≥ 482 passed。

---

## Task 5：loop 接调度器 + 权限按批前置 + `SessionLog` 加锁

目标：把 Task 4 接进 loop，不破任何既有不变量。

测试先行（追加 `tests/test_loop.py`）：

```python
def test_tool_call_id_pairing_survives_parallel_execution():
    """配对是硬约束：每个 tool_call 必须有且只有一条结果，顺序与 tool_calls 一致。
    缺一条下一轮就是 400（R#11 有真实复现）。"""


def test_tool_call_id_pairing_survives_parallel_plus_interrupt():
    """并发批跑到一半中断：已开始的照常收尾，没开始的回『已取消』——
    仍然是每个 tc 一条结果。中断不是『跳过剩下的』。"""


def test_tool_call_id_pairing_survives_parallel_plus_partial_denial():
    """同批里一个 allow 一个 deny：deny 的不执行但**必须**回一条结果（D#41 同款不变量）。"""


def test_permissions_are_decided_per_batch_before_dispatch():
    """按批前置：本批所有权限判完才派发；批与批之间仍是『先执行前一批、再判后一批』，
    所以『工具 A 建了目录、B 才写得进去』这类依赖不受影响。"""


def test_session_append_is_thread_safe():
    """多线程往同一个 JSONL 追加：N 条记录必须是 N 行完整 JSON，没有半行交织。"""


def test_serial_batch_behaviour_is_byte_identical_to_before():
    """全是串行工具时（bash / write_file），行为与接调度器之前逐字相同。"""
```

实现：

- `loop.py` 把「遍历 `msg.tool_calls` 逐个判权限 + 执行」换成：
  `for batch in partition(msg.tool_calls, tools):` → 先串行判完本批权限（发
  `PermissionDecided`），把 allow 的交给 `execute(batch, run_one)`，
  denied / 中断的直接生成结果；最后按原顺序追加 `tool_entry` 与发 `ToolEnd`。
- 事件时序的诚实边界：并发批里 `ToolStart` 由各线程发出，顺序不保证；
  `ToolEnd` 与消息追加按原顺序。状态行只关心「谁在跑」，不依赖顺序。
- `session.py`：`append` 用 `threading.Lock` 包住。

验收：绿阶段 ≥ 490 passed。

---

## Task 6：终端上屏（增量文本 / 不重复打印最终答案 / 多个 ◐）

目标：流式文本真的逐字上屏，且最终答案不打两遍。

现状：`cli.py:64` 与 `interactive._run_turn` 都在结尾打 `🤖 {answer}`。
流式之后那段文字已经逐字打过了，再打一遍就是重复。

规则（写进代码注释）：`AgentEnd.reason == "final"` 的文本是模型说的（已流式打过，不重打）；
`budget` / `max_steps` / `interrupted` 的文本是 loop 合成的（从没流过，必须打）。

测试先行（追加 `tests/test_modes.py`）：

```python
def test_final_answer_is_not_printed_twice_when_streamed():
def test_synthesized_endings_are_still_printed():   # budget / max_steps / interrupted
def test_delta_output_carries_the_robot_prefix_once():
def test_status_line_shows_multiple_running_tools():
    """并发下多个 ◐ 并列。render_tool_line 其实**早就支持**（running 是 dict），
    只是 docstring 写着「不做」——本 task 补测试钉死并订正那句话。"""
```

实现：新增 `src/pai/modes/echo.py` 的 `make_stream_echo()`，
`once` 用它当默认 `on_event`，`interactive.make_event_handler` 与状态行组合；
`cli.py` 与 `_run_turn` 去掉结尾的 `🤖 {answer}`。
`statusline.py` 的 docstring 订正（「一次只跑一个工具」已不成立）。

验收：绿阶段 ≥ 496 passed。

---

## 交付收尾（不是 task）

1. `./test.sh` 全绿，把真实数字写回 STATUS（机器对账会校验）。
2. 写 [复盘.md](复盘.md)（四问，「我现在质疑什么」必答）。
3. 遗留问题逐条登记 TODO；顺带核销两条：
   - 「三个进程级全局一旦有并发就要重新考虑」→ 核实不成立（装配期写、执行期只读）；
   - R#11「单轮多 tool_calls 无测试覆盖」→ Task 5 的配对测试覆盖了。
4. 够格升格的取舍进 `decisions.md`：① 一次响应 = 一条 assistant 消息（拒绝 CC 的 block 级记录）；
   ② 权限按批前置（偏离 CC，理由是绕开抢输入流 + 语义变化限制在批内）；
   ③ usage「每块都看」的取法（文档与实测不符）。
5. `features/README.md` 交付总览表加一行。
