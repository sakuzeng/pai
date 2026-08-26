"""编辑结果里那段 diff（feature 43 Task 3）。

需求原话是「改了什么你看不见」——`edit_file` / `write_file` 只回一句
「完成 1 处替换」。落点选在**工具返回值**而不是事件（拍板问 2·A）：
TUI 那边 `app._tool_entry` 本来就会把多行结果做成可展开条目（`^O`），
`app._display_result` 也已经分好了「模型拿原文 / 终端拿 sanitize 过的那份」，
所以给返回值加 diff 等于同时喂饱了模型和终端，零 UI 改动。

诚实边界：REPL / once 那条路是残的。`events.render_text` 的契约是「返回一行」
（`modes/echo.py` 的注释明写着它依赖这条），且会把换行压成空格再截到 200 字符。
本轮不动那条契约（拍板时的候选 D 被否），已登记 TODO。

三处刻意的取舍：

- **剥掉 `--- / +++` 文件头**。路径已经在上一句话里说了，多两行只是重复；
  而且这段 diff 是给人和模型读的，不是拿去 `patch` 用的。
  注意 `difflib.unified_diff` 不给 `fromfile`/`tofile` 时**照样会吐这两行**
  （文件名是空的，于是变成两行 `--- ` / `+++ ` 纯噪音）——第一版以为它不吐，
  是真跑冒烟才看见的（离线测试全绿，因为没有一条断言在看开头两行）。
- **新建文件不产 diff**。对空文件做 diff 就是把模型刚写的正文再贴一遍，
  那是花 token 买一份复读。只报行数。
- **超过行数上限就只报统计**（拍板问 3·A）。一段 200 行的 diff 对人和模型
  都已经不可读，而它确实花钱；此时报 `+X / -Y` 并把出路指向 `git_read("diff")`。
"""

import difflib
from typing import List, Optional

# diff 超过多少行就不贴。80 行 ≈ 一屏多一点，是「还读得完」与「已经在灌」的分界；
# **未实测**，凭手感定，改它之前先看看真实编辑的 diff 一般多长。
MAX_DIFF_LINES = 80

# 上下文行数。3 是 unified diff 的通行默认（`diff -u`、git 都是它），
# 不另发明——模型见过的 diff 绝大多数是这个形状。
CONTEXT_LINES = 3


def _counts(before: List[str], after: List[str]) -> tuple:
    """`(新增行数, 删除行数)`。

    `n=0` 只是**省一点**，不是正确性要求——上下文行以空格打头，`@@` 以 `@` 打头，
    两者本来就落不进 `+`/`-` 的计数，换成 `n=3` 结果一模一样。
    这条注释原本写的是「不这样会把改动量算成 diff 长度」，那是错的：
    注入反证（把 `n=0` 改成 `n=3`）没能让任何测试变红，查下来是注释在撒谎
    而不是实现有问题（档案 43 devlog 有记）。留 `n=0` 是因为它确实更便宜。"""
    added = removed = 0
    for line in difflib.unified_diff(before, after, n=0, lineterm=""):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _strip_file_headers(body: List[str]) -> List[str]:
    """剥掉开头那两行空文件头。只剥**开头**：正文里以 `---` 打头的代码行
    （yaml 分隔符、Markdown 分隔线）不许被当成文件头误删。"""
    out = list(body)
    while out and (out[0].startswith("--- ") or out[0].startswith("+++ ")
                   or out[0] in ("---", "+++")):
        out.pop(0)
    return out


def render_change(before: Optional[str], after: str, *, path: str,
                  max_lines: int = MAX_DIFF_LINES,
                  before_unreadable: bool = False) -> str:
    """把一次写入渲染成给模型/终端看的那段话。

    `before=None` = 文件此前不存在（新建）。`before_unreadable=True` =
    文件在但读不出文本（二进制等）——写照样成功，只是没法对比，如实说。
    """
    if before_unreadable:
        return "（旧内容不是文本，没法给出 diff）"
    if before is None:
        return f"（新建，{len(after.splitlines())} 行）"
    if before == after:
        return "（内容无变化）"

    b, a = before.splitlines(), after.splitlines()
    added, removed = _counts(b, a)
    body = _strip_file_headers(
        list(difflib.unified_diff(b, a, lineterm="", n=CONTEXT_LINES)))
    if len(body) > max_lines:
        # 报状态之外给做法（同 R#17 / bash 超时文案那条规矩）
        return (f"[改动 +{added} / -{removed} 行，diff 超过 {max_lines} 行上限，不贴；"
                f'要看具体改动用 git_read("diff") 或 read_file({path})]')
    return "\n".join(body)
