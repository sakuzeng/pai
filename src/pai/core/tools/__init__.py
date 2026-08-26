"""工具系统：@tool 装饰器从函数签名生成 schema 并注册（schema 与代码同源）。

从 mini-pi 移植，两点变化：
- REGISTRY 收进模块而非散在脚本顶层，get_tools() 支持子集选取（为子 agent 的受限工具集留口）
- Tool.run() 统一"异常转字符串结果"，loop 不再自己 try/except
"""

from __future__ import annotations

import fnmatch
import inspect
import sys
from dataclasses import dataclass
from typing import Annotated, Callable, Optional, get_args, get_origin, get_type_hints

PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}

REGISTRY: dict[str, "Tool"] = {}

# 已经喊过的 (工具名, 判定器名)。判定器抛异常是 bug 而不是常态，
# 但同一个坏判定器每轮都会被问到——喊一次就够，喊多了等于没喊。
_CAP_WARNED: set = set()

@dataclass(frozen=True)
class MatchContext:
    """匹配一条规则时的上下文：规则来源目录、当前工作目录、主目录。

    为什么 matcher 非要它不可：`/secrets/**` 的含义取决于**哪个设置文件写下了这条规则**
    （用户级指向 `~/.pai/secrets/**`，项目级指向 `<项目根>/secrets/**`）。
    这个信息既不在 specifier 里也不在工具参数里，只能由权限层带进来。
    """

    anchor: str = ""            # 定义这条规则的设置文件所在目录
    cwd: str = ""
    home: str = ""


# 权限匹配器签名：(specifier, args, require_all, ctx) -> bool
Matcher = Callable[[str, dict, bool, MatchContext], bool]

# 从工具入参取出它要碰的那个路径。取不到返回空串——权限判定期拿到脏输入是常态
# （模型可能发来任何东西），在这里抛异常会把判定链炸断。
PathGetter = Callable[[dict], str]

# 工具对文件系统的访问性质。目录边界对读写不对称（照 CC）：
# 读在工作目录内放行、界外问；写一律问。所以判定必须分得清这次是读还是写。
READ, WRITE = "read", "write"

# 工具能力标志（feature 11，调度用）。与 matcher / get_path / access 同一个模式：
# 框架问问题，工具用自己的领域知识回答，权限层与调度器都不认识具体工具。
# **收 input 而不是静态布尔**（照 CC 的 `Tool.isReadOnly(input)`）：
# 一个命令是不是只读取决于这次跑的是 `ls` 还是 `rm`，静态布尔表达不了。
# pai 今天还没有这样的工具，但签名现在就留对，将来不用改第二次。
Capability = Callable[[dict], bool]


def default_matcher(
    specifier: str, args: dict, require_all: bool, ctx: MatchContext
) -> bool:
    """没挂 matcher 的工具吃这个：对**第一个参数值**做通配符匹配。

    `require_all` 与 `ctx` 都用不上——前者表达「复合命令的每个子命令都要匹配」，
    后者表达路径锚点，默认实现眼里只有一个孤零零的值，两个概念都无处安放。
    """
    value = next(iter(args.values()), "")
    return fnmatch.fnmatchcase(str(value), specifier)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable
    # 权限规则的 specifier 怎么匹配这次调用，**由工具自己说了算**（feature 07 拍板问 2）：
    # bash 懂 shell 分隔符与包装器，fs 工具懂路径锚点，权限层一概不知道。
    matcher: Optional[Matcher] = None

    # 目录边界要用的两项声明（feature 09）。同样是「下放给工具」：
    # 这次调用碰哪个路径、是读是写，只有工具自己知道。
    # **bash 两个都不声明**，于是它结构上就进不了边界判定——
    # 这是拍板问 2「bash 不做目录边界」的落点，不是权限层里的一个 if。
    get_path: Optional[PathGetter] = None
    access: Optional[str] = None

    # 边界豁免位（feature 27，D#73）：路径由 pai 自算、入参无路径语义的工具
    # （skill：模型只能传名字，正文路径来自装配层扫描）在兜底步 allow，
    # 不落「未声明路径语义 → ask」。只影响求值链第 7 步兜底——deny 规则、
    # 危险写检查、用户显式 ask 规则照常在前。默认 False：豁免必须显式声明。
    boundary_exempt: bool = False

    # 调度用的两项能力声明（feature 11）。`None` = 没声明 = False，见 `_ask`。
    is_read_only: Optional[Capability] = None
    is_concurrency_safe: Optional[Capability] = None

    def _ask(self, cap: Optional[Capability], args) -> bool:
        """未声明 / 参数不是 dict / 判定器抛异常，一律 False。

        三条退化路径都指向同一个方向：**判不出来就当不安全**。
        代价是那次调用退回串行——慢，不是错。反过来（判不出来就当安全）
        才会让「加了个新工具忘了声明」变成一个并发数据竞争。
        参数脏是常态：模型发来的 arguments 可能是 `null` / `[1,2]` / 字符串。

        第三条留痕（11 task 3）：前两条是常态，判定器自己炸了是 bug——
        三条同形的话「这个工具确实不安全」与「判定器写错了」在外部一模一样，
        症状只是并发静默退回串行。每个 (工具, 判定器) 只喊一次：
        每次判定刷一行会把真正要看的输出淹掉（同 EventTrace 落盘失败那条）。
        """
        if cap is None or not isinstance(args, dict):
            return False
        try:
            return bool(cap(args))
        except Exception as e:  # noqa: BLE001 - 照 CC：判定器自己炸了就当不安全
            key = (self.name, getattr(cap, "__name__", repr(cap)))
            if key not in _CAP_WARNED:
                _CAP_WARNED.add(key)
                print(f"⚠️ 工具 `{self.name}` 的能力判定器抛了 "
                      f"{type(e).__name__}: {e}；本次按「不安全」处理"
                      "（该调用退回串行），本会话不再提示", file=sys.stderr)
            return False

    def read_only(self, args) -> bool:
        return self._ask(self.is_read_only, args)

    def concurrency_safe(self, args) -> bool:
        return self._ask(self.is_concurrency_safe, args)

    def participates_in_boundary(self) -> bool:
        """两项都声明了才参与目录边界判定。缺一不可：
        只有 access 不知道查哪个路径，只有 get_path 不知道该按读还是按写判。"""
        return self.get_path is not None and self.access in (READ, WRITE)

    def matches(
        self,
        specifier: str,
        args: dict,
        require_all: bool,
        ctx: Optional[MatchContext] = None,
    ) -> bool:
        ctx = ctx if ctx is not None else MatchContext()
        if self.matcher is None:
            return default_matcher(specifier, args, require_all, ctx)
        return bool(self.matcher(specifier, args, require_all, ctx))

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
    from pai.core.tools import ask, fs, memory_tool, shell, skill  # noqa: F401 - import 即注册

    if names is None:
        return {n: t for n, t in REGISTRY.items() if n not in INTERACTIVE_ONLY}
    return {n: REGISTRY[n] for n in names}


def all_tools() -> dict[str, Tool]:
    """全部已注册工具，**含**只在交互模式露面的那些。

    与 get_tools() 的区别是故意的：权限判定要认得每一个可能被调用的工具，
    而 INTERACTIVE_ONLY 只是「不摆给模型看」，不是「不会被调用」。
    显式 import 子模块而不是直接读 REGISTRY——否则判定结果取决于谁先 import 了谁。
    """
    from pai.core.tools import ask, fs, memory_tool, shell, skill  # noqa: F401 - import 即注册

    return dict(REGISTRY)


def path_access_for(tool_func, access: str) -> Callable[[PathGetter], PathGetter]:
    """给已注册的工具声明「碰哪个路径、是读是写」：`@path_access_for(read_file, READ)`。

    与 `matcher_for` 同款——不动 `@tool` 本身，挂到没注册的工具上当场抛。
    """
    name = tool_func if isinstance(tool_func, str) else getattr(tool_func, "__name__", "")
    if access not in (READ, WRITE):
        raise ValueError(f"access 只能是 {READ!r} 或 {WRITE!r}，得到 {access!r}")

    def attach(fn: PathGetter) -> PathGetter:
        if name not in REGISTRY:
            raise ValueError(f"path_access_for：工具 {name!r} 没注册，先用 @tool 注册")
        REGISTRY[name].get_path = fn
        REGISTRY[name].access = access
        return fn

    return attach


def capabilities_for(tool_func, *, read_only=False, concurrency_safe=False) -> None:
    """给已注册的工具挂能力标志。取值可以是 `bool`，也可以是 `(args) -> bool`。

    **刻意不做成装饰器**（与 `path_access_for` / `matcher_for` 不同）：那两个装饰的是
    真的 getter 函数，而能力标志绝大多数是常量——装饰一个 `lambda args: True` 只是噪音。
    保留 callable 形态是给 bash 这类「取值依赖参数」的工具留的签名口子。

    没注册就抛：静默不生效意味着调度**静默退回串行**，比报错难查得多（同 matcher_for）。
    """
    name = tool_func if isinstance(tool_func, str) else getattr(tool_func, "__name__", "")
    if name not in REGISTRY:
        raise ValueError(f"capabilities_for：工具 {name!r} 没注册，先用 @tool 注册再挂能力标志")

    def as_capability(value) -> Capability:
        if callable(value):
            return value
        return lambda _args, _v=value: bool(_v)

    REGISTRY[name].is_read_only = as_capability(read_only)
    REGISTRY[name].is_concurrency_safe = as_capability(concurrency_safe)


def boundary_exempt_for(tool_func) -> None:
    """给已注册的工具声明边界豁免（feature 27，D#73）：兜底步 allow，不落
    「未声明路径语义 → ask」。

    只许给满足两个条件的工具：入参表达不了路径（模型没法用它指定读哪个文件），
    且它真正碰的路径由 pai 自己算（装配期扫描等受信来源）。skill 是第一个也是
    目前唯一的：CC 的 SkillTool 无 getPath、dsh 的门是 isModelInvocable 策略位，
    「读 SKILL.md 这个路径」的建模是三家参照里没有的孤例。豁免只作用于求值链
    第 7 步兜底，deny 规则 / 危险写检查 / 用户显式 ask 规则照常在前
    （tests/test_skills.py 钉优先级）。没注册就抛，同 capabilities_for。
    """
    name = tool_func if isinstance(tool_func, str) else getattr(tool_func, "__name__", "")
    if name not in REGISTRY:
        raise ValueError(f"boundary_exempt_for：工具 {name!r} 没注册，先用 @tool 注册")
    REGISTRY[name].boundary_exempt = True


def matcher_for(tool_func) -> Callable[[Matcher], Matcher]:
    """把权限匹配函数挂到已注册的工具上：`@matcher_for(bash)`。

    不动 `@tool` 本身——它只负责「schema 与代码同源」这一件事。
    参数可以是工具函数，也可以是工具名字符串。
    """
    name = tool_func if isinstance(tool_func, str) else getattr(tool_func, "__name__", "")

    def attach(fn: Matcher) -> Matcher:
        if name not in REGISTRY:
            # 静默不生效 = 权限规则静默失效，比报错危险得多
            raise ValueError(f"matcher_for：工具 {name!r} 没注册，先用 @tool 注册再挂匹配器")
        REGISTRY[name].matcher = fn
        return fn

    return attach
