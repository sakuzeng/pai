"""工具调度：保序贪心分批（feature 11 task 4）。"""

import json
import threading
from types import SimpleNamespace

from pai.core.scheduler import Batch, execute, partition
from pai.core.tools import REGISTRY, Tool, capabilities_for, tool


def _tc(name, args="{}", id_="id"):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=args))


def _tools(**flags):
    """造一组工具：flags 形如 read=(True, True) 表示 (read_only, concurrency_safe)。"""
    out = {}
    for name, (ro, cs) in flags.items():
        t = Tool(name=name, description="d", parameters={}, func=lambda: "")
        t.is_read_only = lambda _a, _v=ro: _v
        t.is_concurrency_safe = lambda _a, _v=cs: _v
        out[name] = t
    return out


SAFE_AND_UNSAFE = {"read": (True, True), "write": (False, False)}


def test_consecutive_safe_tools_merge_into_one_batch():
    """照 CC 的 partitionToolCalls：连续的并发安全工具合批，其余各自成批。"""
    tools = _tools(**SAFE_AND_UNSAFE)
    calls = [_tc("read"), _tc("read"), _tc("write"), _tc("read")]
    batches = partition(calls, tools)

    assert [(b.parallel, len(b.calls)) for b in batches] == [(True, 2), (False, 1), (True, 1)]


def test_a_serial_tool_splits_the_batch_and_order_is_preserved():
    """保序是硬约束：模型发出的顺序有意义（先 read 再 edit），
    调度只在不改变可观察顺序的前提下偷并行——**不重排**。"""
    tools = _tools(**SAFE_AND_UNSAFE)
    calls = [_tc("read", id_="a"), _tc("write", id_="b"), _tc("read", id_="c")]
    flat = [tc.id for b in partition(calls, tools) for tc in b.calls]
    assert flat == ["a", "b", "c"]


def test_only_read_only_and_concurrency_safe_tools_go_parallel():
    """**两个标志都为真**才进并发批。

    这不是保守，是把 spec 里那条论证的前提钉死在代码里：
    「权限按批前置是安全的」依赖「并发批里全是只读工具」。只看 concurrency_safe 的话，
    将来出现一个「并发安全但会写」的工具，那条论证会**静默失效**。
    """
    tools = _tools(sneaky=(False, True))          # 声称并发安全，但不是只读
    batches = partition([_tc("sneaky"), _tc("sneaky")], tools)
    assert [b.parallel for b in batches] == [False, False]


def test_unknown_tool_is_never_parallel():
    """判不出来 ≠ 没问题。"""
    assert partition([_tc("no_such_tool")], {})[0].parallel is False


def test_bad_json_arguments_is_never_parallel():
    """能力标志收的是解析后的参数；参数都解析不了，判定无从谈起 → 串行。"""
    tools = _tools(read=(True, True))
    assert partition([_tc("read", args="{not json")], tools)[0].parallel is False


def test_results_are_returned_in_input_order_not_completion_order():
    """先完成的不许插队：并发的是**执行**，不是**交付**。"""
    started = threading.Event()

    def run_one(tc):
        if tc.id == "slow":
            started.wait(timeout=2)
            return "slow-done"
        started.set()
        return "fast-done"

    batch = Batch(parallel=True, calls=[_tc("read", id_="slow"), _tc("read", id_="fast")])
    assert execute(batch, run_one) == ["slow-done", "fast-done"]


def test_batch_really_runs_in_parallel():
    """真并发要**可观测地**证明：Barrier 要两个任务都到齐才放行，
    串行执行会在这里卡到超时。不用计时——慢机器上计时会 flaky。"""
    barrier = threading.Barrier(2, timeout=3)

    def run_one(tc):
        barrier.wait()                # 串行的话第一个就永远等不到第二个
        return tc.id

    batch = Batch(parallel=True, calls=[_tc("read", id_="a"), _tc("read", id_="b")])
    assert execute(batch, run_one) == ["a", "b"]


def test_serial_batch_runs_one_by_one():
    order = []

    def run_one(tc):
        order.append(tc.id)
        return tc.id

    batch = Batch(parallel=False, calls=[_tc("write", id_="a"), _tc("write", id_="b")])
    assert execute(batch, run_one) == ["a", "b"]
    assert order == ["a", "b"]


def test_single_call_batch_does_not_spawn_a_thread():
    """一个调用没必要起线程池——省的不是性能，是「主线程之外」带来的一整类问题
    （中断信号、进程组、异常栈）。"""
    seen = []

    def run_one(tc):
        seen.append(threading.current_thread() is threading.main_thread())
        return tc.id

    execute(Batch(parallel=True, calls=[_tc("read")]), run_one)
    assert seen == [True]


def test_real_builtin_tools_partition_as_expected():
    """拿**真实注册表**跑一遍，而不是只测造出来的假工具——
    Task 3 挂的标志与本模块的读取方式必须对得上，中间隔着一层就可能对不上。"""
    from pai.core.tools import all_tools

    tools = all_tools()
    calls = [
        _tc("read_file", json.dumps({"path": "a"})),
        _tc("read_file", json.dumps({"path": "b"})),
        _tc("bash", json.dumps({"command": "ls"})),
        _tc("read_file", json.dumps({"path": "c"})),
    ]
    assert [(b.parallel, len(b.calls)) for b in partition(calls, tools)] == [
        (True, 2), (False, 1), (True, 1)]


def test_exception_in_one_parallel_task_does_not_swallow_the_others():
    """一个工具炸了不该把整批带走。**本轮不做兄弟取消**（拍板选 B），
    所以正确行为是：让异常照常抛给调用方，由 loop 那一侧决定怎么回填结果。
    这条测试钉的是「不静默吞掉」，不是「继续跑」。"""
    import pytest

    def run_one(tc):
        if tc.id == "boom":
            raise RuntimeError("炸了")
        return tc.id

    batch = Batch(parallel=True, calls=[_tc("read", id_="ok"), _tc("read", id_="boom")])
    with pytest.raises(RuntimeError, match="炸了"):
        execute(batch, run_one)
