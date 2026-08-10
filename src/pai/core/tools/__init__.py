"""工具系统：@tool 装饰器从函数签名生成 schema 并注册（schema 与代码同源）。

从 mini-pi 移植，两点变化：
- REGISTRY 收进模块而非散在脚本顶层，get_tools() 支持子集选取（为子 agent 的受限工具集留口）
- Tool.run() 统一"异常转字符串结果"，loop 不再自己 try/except
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Annotated, Callable, get_args, get_origin, get_type_hints

PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}

REGISTRY: dict[str, "Tool"] = {}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs) -> str:
        # 工具错误必须变成给模型的反馈而不是异常（AGENTS.md 架构约束）
        try:
            result = self.func(**kwargs)
        except Exception as e:  # noqa: BLE001 - 工具边界是异常的最终防线
            return f"错误：{type(e).__name__}: {e}"
        # 返回值同样是边界的一部分：None/dict 会让 loop 在 result[:200] 处崩（R3#2）
        return result if isinstance(result, str) else str(result)


def tool(func: Callable) -> Callable:
    """从签名/Annotated 注解/docstring 首行生成 JSON Schema 并注册。"""
    hints = get_type_hints(func, include_extras=True)
    sig = inspect.signature(func)

    properties: dict[str, dict] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        hint = hints.get(pname, str)
        desc = ""
        typ = hint
        if get_origin(hint) is Annotated:
            typ, *meta = get_args(hint)
            desc = meta[0] if meta else ""
        if typ not in PY_TO_JSON:
            # 静默降级成 string 会生成错 schema，坑的是下一个加工具的人（R3#2）
            raise ValueError(
                f"工具 {func.__name__} 参数 {pname} 的类型 {typ!r} 不支持："
                f"只认 {sorted(t.__name__ for t in PY_TO_JSON)}，复杂结构请用 JSON 字符串参数"
            )
        properties[pname] = {"type": PY_TO_JSON[typ], "description": desc}
        if param.default is inspect.Parameter.empty:
            required.append(pname)

    # docstring 首行就是给模型看的工具描述，缺了模型无从选择用哪个工具。
    # 显式报错而不是让 splitlines()[0] 抛 IndexError——报错要指向真因。
    doc = (func.__doc__ or "").strip()
    if not doc:
        raise ValueError(f"工具 {func.__name__} 缺少 docstring：首行会作为工具描述发给模型")

    t = Tool(
        name=func.__name__,
        description=doc.splitlines()[0],
        parameters={"type": "object", "properties": properties, "required": required},
        func=func,
    )
    REGISTRY[t.name] = t
    return func


# 需要真人在场的工具：注册着但不进默认集合，得显式点名要（get_tools([...])）。
# once 模式没有真人可问，把它摆给模型看就是让模型撞空。
INTERACTIVE_ONLY = ("ask_user_question",)


def get_tools(names: list[str] | None = None) -> dict[str, Tool]:
    """默认全量（除需真人在场的）；传 names 取子集（受限工具集 / 交互模式加料用）。"""
    from pai.core.tools import ask, fs, memory_tool, shell  # noqa: F401 - import 即注册

    if names is None:
        return {n: t for n, t in REGISTRY.items() if n not in INTERACTIVE_ONLY}
    return {n: REGISTRY[n] for n in names}
