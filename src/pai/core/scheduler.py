"""工具调度：连续的并发安全工具合成一批并行跑，其余串行。

照 CC 的 `toolOrchestration.ts::partitionToolCalls`——**保序贪心分组，不是重排**。
模型发出的工具顺序是有意义的（先 read_file 再 edit_file），
调度只在不改变可观察顺序的前提下偷并行：**并发的是执行，不是交付**。

**不做**边流边派发与兄弟取消（feature 11 拍板选方案 B）：
实测「不等模型说完就开跑」最多抢到 16% 的流时间，而 CC 那套复杂度
（半成品丢弃 / 孤儿 tool_result / 兄弟取消）全是为它付的。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List

# 并发上限。**这个数从哪来、依赖什么前提**（TODO「给照抄来的常数建一条检查习惯」的落实）：
# CC 默认 10 且可用 CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY 调；pai 的并发安全工具
# 是 read_file 与 search_files（都是纯 IO 不吃 CPU；后者 feature 41 加入），
# 8 是**未实测的经验值**，真实并发度还受限于模型一轮
# 发几个工具（实测见过 3 个）。**改它之前先拿数字**——没有数字的调参不是 perf。
MAX_TOOL_WORKERS = 8


@dataclass
class Batch:
    parallel: bool
    calls: List = field(default_factory=list)      # 原始 tool_call 对象，顺序保持


def partition(tool_calls, tools: dict) -> List[Batch]:
    """把一轮里的多个 tool_call 折成批。**连续**的并发安全工具才合批——
    一个非并发安全的工具会把前后切开，顺序因此不变。"""
    batches: List[Batch] = []
    for tc in tool_calls:
        parallel = _parallelizable(tc, tools)
        if parallel and batches and batches[-1].parallel:
            batches[-1].calls.append(tc)
        else:
            batches.append(Batch(parallel=parallel, calls=[tc]))
    return batches


def _parallelizable(tc, tools: dict) -> bool:
    """**两个标志都要为真**——这是 spec 里「权限按批前置是安全的」那条论证的前提。

    那条论证是：并发批里全是只读工具，所以它们不会改变彼此的权限判定前提。
    只看 `concurrency_safe` 的话，将来出现一个「并发安全但会写」的工具，
    论证会**静默失效**——所以把前提钉在这里，而不是留在文档里。
    """
    tool = tools.get(getattr(getattr(tc, "function", None), "name", ""))
    if tool is None:                     # 未知工具：判不出来 ≠ 没问题
        return False
    try:
        args = json.loads(tc.function.arguments)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False                     # 参数都解析不了，能力判定无从谈起
    return tool.read_only(args) and tool.concurrency_safe(args)


def execute(batch: Batch, run_one: Callable, *, max_workers: int = MAX_TOOL_WORKERS) -> list:
    """跑一批，**结果按输入顺序回填**（先完成的不许插队）。

    单个调用不起线程池：省的不是性能，是「主线程之外」带来的一整类问题
    （中断信号只能装在主线程、bash 的进程组、异常栈）。

    工具内部异常**不在这里吞**——`Tool.run` 已经把工具自身的异常转成字符串结果了
    （AGENTS.md 的架构约束），能逃到这里的是 loop 那一侧的 bug，该让它响。
    本轮不做兄弟取消（拍板选 B），所以也没有「一个炸了要不要杀掉其他」这个问题。
    """
    if not batch.parallel or len(batch.calls) == 1:
        return [run_one(tc) for tc in batch.calls]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(batch.calls))) as pool:
        # pool.map 保序：返回顺序是**提交顺序**，不是完成顺序
        return list(pool.map(run_one, batch.calls))
