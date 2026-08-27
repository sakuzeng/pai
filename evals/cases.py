"""工具选择评测的案例集（feature 47）。

18 条固定的（意图 → 期望工具）。**14 条专用工具该赢、4 条 bash 才是对的**——
后者不是凑数：没有它们，这个指标就会奖励「一律不选 bash」这种退化策略，
而那与「让模型选对工具」根本不是一回事。

每条带 `why`。跑挂的时候要能一眼看出这条想验什么，而不是回头猜
「当初为什么觉得这里该选 search_files」。

改这张表就是改测量本身：加/删 case 会让前后两次的数字不可比。
真要改，在档案里说清改了什么、为什么，并重新跑一遍基线。

版本：v2（feature 47 首跑之后修了一条）。v1 里改函数那条写的是
「把 foo 改成 bar」——没给原文，而 `edit_file` 需要精确原文，
所以「先 read_file 再改」才是对的行为，那条 case 根本没有正确答案。
两次的数字因此不可直接比，档案里两次都记了。
"""

from pai.evals.tool_choice import Case

CASES = (
    # ---- run_tests（feature 45 的原始症状：任务明说跑测试，它零次被选中）----
    Case("跑一下这个项目的测试。", "run_tests",
         "45 实测的原始症状，最直接的一条"),
    Case("只跑 tests/test_boundary.py 里的测试，告诉我结果。", "run_tests",
         "带路径的形态——run_tests 有 path 参数，不该因此退回 bash"),

    # ---- search_files ----
    Case("MAGIC_LIMIT 这个常量定义在哪个文件？", "search_files",
         "最典型的找代码，对照组里模型走的是 bash 的 grep"),
    Case("哪些地方调用了 run_agent？", "search_files",
         "找引用，同上"),
    Case("src/config.py 里哪一行设置了 MAGIC_LIMIT？", "search_files",
         "**已知文件里找一行**——feature 46 才放开的单文件搜索根，45 实测里模型只能走 bash"),

    # ---- git_read ----
    Case("现在有哪些文件被改动了？", "git_read",
         "git status 的自然说法"),
    Case("看看最近三条提交说了什么。", "git_read",
         "git log 的自然说法"),

    # ---- list_dir（feature 46 新加，真跑里被 ls 顶掉过）----
    Case("src 目录下面有哪些子目录？", "list_dir",
         "46 加的工具，真跑里被 bash 的 ls 顶掉过一次"),
    Case("这个项目根目录里都有什么？", "list_dir",
         "开场探路——45 实测里这是**第一个**工具调用，且必然弹窗"),

    # ---- read_file ----
    Case("把 pyproject.toml 的内容给我看看。", "read_file",
         "46 才补上引导句（此前只有 edit_file 有），对照组里模型用的是 cat"),
    Case("读一下 README.md 的前 30 行。", "read_file",
         "带范围的读——read_file 有 offset/limit，不该因此退回 bash 的 head"),

    # ---- 写 ----
    Case("把 src/demo.py 里的 `TIMEOUT = 30` 原样改成 `TIMEOUT = 60`，原文我已经给你了。", "edit_file",
         "唯一一句从 feature 22 就存在的引导，当对照组的锚。"
         "**原文写进意图里**是必须的：edit_file 要精确原文，"
         "不给的话「先 read_file 再改」才是对的行为，那条 case 就没有正确答案"),
    Case("新建一个 hello.py，内容是 print(1)。", "write_file",
         "新建文件走 write_file 而不是 bash 的 echo >"),

    # ---- 记忆 ----
    Case("记住我这个项目习惯用 4 空格缩进。", "remember",
         "非文件类工具，看引导会不会把它一起带偏"),

    # ---- bash 才是对的（防止指标奖励「一律不选 bash」）----
    Case("把 build.sh 加上可执行权限。", "bash",
         "chmod 没有专用工具，选 bash 才对", negative=True),
    Case("看看当前用的 python 是哪个版本。", "bash",
         "跑一条外部命令，选 bash 才对", negative=True),
    Case("统计一下 src 目录下一共有多少行 Python 代码。", "bash",
         "要管道与 wc，search_files 做不到；这条最容易被引导带偏", negative=True),
    Case("在 8000 端口起一个静态文件服务器。", "bash",
         "起进程，没有专用工具", negative=True),
)


# feature 46 **之前**那份 system prompt 的原样抄写，冻结在这里当对照组。
# 与 feature 43 把「抽取前的三份实现」抄进测试当对照组是同一个手法：
# 对照组必须是冻结的文本，不能是「把开关关掉重新生成」——后者会跟着当前代码漂，
# 而漂了之后前后两次的数字就不可比了。
BASELINE_PROMPT_TAIL = (
    "改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。"
    "一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。"
)


def baseline_prompt(tools) -> str:
    """feature 46 之前的提示词：工具名单 + 仅 edit_file 那一句引导。"""
    return ("你是一个最小化的编码 agent。"
            "你有这些工具：" + "、".join(tools) + "。工具的用法与参数见各自的说明。"
            + BASELINE_PROMPT_TAIL)
