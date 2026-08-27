"""单步工具选择的可重复测量（feature 47）。

要修的是 feature 46 交付时我自己写下的那条遗留：端到端效果没有可信的测量方法
——同一个问题两次真跑，一次 7 调用/2 弹窗，一次 12 调用/5 弹窗。
方差压过了效应，于是「这次改动让 agent 变好了没有」只能靠感觉。

方法（拍板问 1·A + 问 2·A）：**不跑整条轨迹，只看第一步选哪个工具**。
固定上下文 → 一次很短的 completion → 看第一个 `tool_call` 的名字。

**一处被自己的检查推翻的前提**（feature 47 首轮）：原本的设计是
「`temperature=0` ⇒ 同一个 case 采样多次会退化成一个点 ⇒ 每个 case 采一次就够」。
预注册的可重复性检查当场证伪了它——逐字冻结的对照组提示词，三次跑出 14/14/16；
直接探针更清楚：同一 case 同一提示词采 6 次，`run_tests` 5 次、`list_dir` 1 次。
这家 provider 在 `temperature=0` 下**不是确定性的**（MoE 路由与批处理都会引入抖动）。

所以每个 case 必须**采样多次按命中率计分**，`temperature=0` 只是把抖动压小、
不是消掉。样本仍然便宜：单步 completion 比整条轨迹便宜两个数量级。

这个指标最容易被玩坏的方式是「一律不选 bash」，所以案例集里必须有
**bash 才是对的**那几条，且它们与其余案例同权计分（`negative` 标记只用于
分组报告，不用于加权）。

只测一步是明写的边界：模型可能第一步选对、后面仍然绕路。这一层测不到，
不假装能测到。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

# 评测请求的温度。0 = 要确定性；这是**评测夹具自己的请求参数**，
# 不经 `run_agent`，所以 pai 的产品行为一个字都不变（拍板问 2·A）。
EVAL_TEMPERATURE = 0


@dataclass(frozen=True)
class Case:
    """一条意图 → 期望工具。

    `why` 不是注释是数据：跑挂了要能一眼看出这条 case 想验什么，
    而不是回头去猜「当初为什么觉得这里该选 search_files」。
    """

    intent: str
    expect: str
    why: str
    negative: bool = False          # True = 这条里 bash 才是对的


@dataclass(frozen=True)
class Outcome:
    case: Case
    picks: tuple                    # 每次采样选了什么；None = 那次没调工具

    @property
    def hit_rate(self) -> float:
        """这条 case 的命中率。**不是布尔**——provider 在 temp=0 下也会抖，
        取多数会把 3/5 与 5/5 抹成同一个数，而那正是要区分的东西。"""
        if not self.picks:
            return 0.0
        return sum(1 for p in self.picks if p == self.case.expect) / len(self.picks)


def first_tool_name(response) -> Optional[str]:
    """从一次 completion 里取第一个 tool_call 的名字；没调工具回 None。

    容错到底：评测跑的是真 provider，字段缺失/结构不同不该让整轮评测炸掉，
    「模型没调工具」本身就是一个要记录的结果，不是异常。
    """
    try:
        calls = response.choices[0].message.tool_calls or []
    except (AttributeError, IndexError, TypeError):
        return None
    if not calls:
        return None
    try:
        return calls[0].function.name
    except (AttributeError, IndexError, TypeError):
        return None


def ask_once(client, model: str, system_prompt: str, intent: str,
             tool_schemas: Sequence[dict]) -> Optional[str]:
    """问一步：给定系统提示与一句意图，模型会调哪个工具。

    刻意**不流式**：这里要的是一个结构化结果，流式只会把装配成本白花一遍
    （同 loop 里「侧查询不走流式」那条）。
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": intent}],
        tools=list(tool_schemas),
        temperature=EVAL_TEMPERATURE,
    )
    return first_tool_name(response)


def run_cases(cases: Sequence[Case], ask: Callable[[Case], Optional[str]],
              samples: int = 1) -> List[Outcome]:
    """跑一组 case，每条采样 `samples` 次。

    `ask` 注入进来，于是这一层离线可测（不打真 API）。
    """
    return [Outcome(case=c, picks=tuple(ask(c) for _ in range(samples)))
            for c in cases]


@dataclass(frozen=True)
class Score:
    hits: float                     # 各 case 命中率之和（不是整数）
    total: int
    negative_hits: float
    negative_total: int
    samples: int
    misses: tuple                   # ((意图, 期望, 命中率, 实际选过什么), …)

    @property
    def rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def render(self, label: str) -> str:
        lines = [f"{label}：{self.hits:.2f}/{self.total}"
                 f"（命中率 {self.rate:.0%}，每条采样 {self.samples} 次；"
                 f"其中 bash 该赢的 {self.negative_hits:.2f}/{self.negative_total}）"]
        for intent, expect, rate, picked in self.misses:
            lines.append(f"  ✗ {intent} → 期望 {expect}（{rate:.0%}），实际 {picked}")
        return "\n".join(lines)


def score(outcomes: Sequence[Outcome]) -> Score:
    """计分。两条刻意的选择：

    一、**按命中率求和而不是数布尔**。provider 在 `temperature=0` 下也会抖
    （feature 47 实测：同 case 同提示词 6 次采样 5:1），取多数会把 3/5 与 5/5
    抹成同一个数——而那正是改提示词时要看的东西。

    二、**负例与其余同权**：`negative` 只用于分组报告，不参与加权。
    加权的话「一律不选 bash」这种退化策略就能靠调权重变得好看，
    而那正是这个指标最容易被玩坏的方式。
    """
    neg = [o for o in outcomes if o.case.negative]
    samples = len(outcomes[0].picks) if outcomes else 0
    misses = []
    for o in outcomes:
        if o.hit_rate < 1.0:
            others = sorted({p or "（没调工具）" for p in o.picks
                             if p != o.case.expect})
            misses.append((o.case.intent, o.case.expect, o.hit_rate, "/".join(others)))
    return Score(
        hits=sum(o.hit_rate for o in outcomes),
        total=len(outcomes),
        negative_hits=sum(o.hit_rate for o in neg),
        negative_total=len(neg),
        samples=samples,
        misses=tuple(misses),
    )
