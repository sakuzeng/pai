"""把模型回答里的 markdown 渲染成终端行（feature 44）。

只在 TUI 上用（拍板问 1·A）：那边答案是 `_flush_answer` 一次性 commit 的，
与流式没有冲突；REPL / once 逐字写 stdout，渲染与它相悖，且管道里本来就不该
有转义符。

自己写而不引 rich（拍板问 2·A）。买到的不是「少一个依赖」，是**只有一套宽度
体系**：这里的列宽全部走 `width.display_width`（CJK 感知、剥转义符），
上色全部走 `theme.paint`（`color=False` 时一个字节都不加）。
两套宽度计算并存正是 feature 13「满屏阶梯」那类 bug 的温床。

契约：`render(text, width, color) -> List[str]`，每行的 `display_width` 都
`<= width`。**不许把内容弄丢**——认不出的语法一律当普通段落透出，
渲染器吃掉一段文字比不渲染糟得多（`test_nothing_is_lost` 钉这条）。

一处诚实边界：这里用到的框线字符（`─ ━ │ • ◦ ┌ └`）在 Unicode 里是
East Asian Width = Ambiguous，`width.display_width` 按 1 列算，而部分 CJK 终端
按 2 列画。落在标题下划线、列表符号、代码块左栏上只是整体右移一格，无害；
**落在表格里会让整张表塌掉**，所以表格的分隔行刻意用 ASCII `-`，不用 `─`。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from pai.tui import theme
from pai.tui.width import _truncate, display_width

# 表格列之间的间隔与左边距。写成常量是因为列宽计算要减掉它们，
# 散在两处的话「算出来的宽度」与「排出来的宽度」会各说各话。
COL_GAP = 2
LEFT_PAD = 1
MIN_COL_WIDTH = 3               # 压缩时给每列留的最小宽（放得下一个字 + 省略号）

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HRULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_ULIST = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")

# 禁则：这些字符不许出现在行首（中文排版的「避头」）。折行正好落在它们前面时，
# 把上一行的最后一个字挤下来，让标点跟着它走。
# 只做避头不做避尾：行尾出现开引号/开括号同样不美，但那要往回看更多字符，
# 而实测里模型的回答几乎撞不到——不为一个没见过的形态加一条规则。
NO_LINE_START = frozenset("，。、；：？！）］｝》」』〉·…,.;:?!)]}%")

# 行内标记。**成对才算标记**——落单的 `*` 与反引号是内容不是语法
# （`2 ** 3` 这种表达式在回答里很常见，吃掉它就是改了模型的话）。
_INLINE = re.compile(r"(\*\*(?=\S)(.+?)(?<=\S)\*\*|`([^`]+)`|\*(?=\S)([^*]+?)(?<=\S)\*)")


def render(text: str, width: int, *, color: bool = False) -> List[str]:
    """渲染成不超过 `width` 列的行数组。块与块之间空一行。"""
    if width <= 0:
        return text.split("\n")
    blocks = _blocks(text.split("\n"))
    out: List[str] = []
    for kind, payload in blocks:
        rendered = _RENDERERS[kind](payload, width, color)
        if not rendered:
            continue
        if out:
            out.append("")              # 块间一个空行，源里有几个空行都归一
        out.extend(rendered)
    return out


# ---- 分块（按行扫描，不建 AST）----


def _blocks(lines: List[str]) -> List[Tuple[str, object]]:
    """把行切成块。顺序即优先级：围栏最先——它一开，里面的一切都是字面量。"""
    out: List[Tuple[str, object]] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        fence = _FENCE.match(line)
        if fence:
            marker, lang = fence.group(1)[0] * 3, fence.group(2)
            body, i = [], i + 1
            while i < n and not (_FENCE.match(lines[i])
                                 and lines[i].strip().startswith(marker)):
                body.append(lines[i])
                i += 1
            i += 1                      # 吃掉收尾围栏；没有收尾时这一步空转
            out.append(("code", (lang, body)))
            continue

        if _HEADING.match(line):
            m = _HEADING.match(line)
            out.append(("heading", (len(m.group(1)), m.group(2).strip())))
            i += 1
            continue

        if _HRULE.match(line):
            out.append(("hrule", None))
            i += 1
            continue

        # 表格：当前行有 `|` 且**下一行是分隔行**。少了后一半的话，
        # 正文里一句带竖线的话会被当成表格吃掉（`test_a_pipe_line_without…`）。
        if "|" in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]) \
                and "|" in lines[i + 1]:
            rows = [line]
            aligns = _aligns(lines[i + 1])
            i += 2
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(lines[i])
                i += 1
            out.append(("table", (rows, aligns)))
            continue

        if _QUOTE.match(line):
            body = []
            while i < n and _QUOTE.match(lines[i]):
                body.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            out.append(("quote", body))
            continue

        if _ULIST.match(line) or _OLIST.match(line):
            items = []
            while i < n and (_ULIST.match(lines[i]) or _OLIST.match(lines[i])):
                items.append(lines[i])
                i += 1
            out.append(("list", items))
            continue

        para = []
        while i < n and lines[i].strip() and not _block_start(lines, i):
            para.append(lines[i].strip())
            i += 1
        if para:
            # **单个换行按硬换行处理**，不按 CommonMark 的「软换行合成一段」。
            # 理由是这里的文本来自对话而不是文档：模型写下换行就是想换行
            # （无标记的枚举、短句分行都很常见），合并掉就是改了它的排版。
            # GFM 的 `breaks` 选项、以及各家聊天界面都是这么定的。
            # 这条是既有 e2e 撞出来的：`"回答。\n甲0\n甲1…"` 21 行被合成一段，
            # 内容一个字没丢，但结构没了（档案 44 devlog 有记）。
            out.append(("para", para))
        else:
            i += 1                      # 防死循环：这一行谁都不认，也不能卡住
    return out


def _block_start(lines: List[str], i: int) -> bool:
    """这一行是不是另一个块的开头（段落到此为止）。"""
    line = lines[i]
    if _FENCE.match(line) or _HEADING.match(line) or _HRULE.match(line) \
            or _QUOTE.match(line) or _ULIST.match(line) or _OLIST.match(line):
        return True
    return ("|" in line and i + 1 < len(lines)
            and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1])


# ---- 行内 ----


def _spans(text: str, color: bool) -> List[Tuple[str, str]]:
    """把一行拆成 `(文字, 颜色码)`。颜色码为空串 = 不上色。

    标记一律**剥掉**（「预览而不是原文」的字面意思），`color=False` 时只是
    不上色——于是有色终端上粗体是粗的，无色终端上它与正文同形。
    这是无色本身的代价，不是这里偷懒。
    """
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], ""))
        if m.group(2) is not None:
            out.append((m.group(2), theme.BOLD if color else ""))
        elif m.group(3) is not None:
            out.append((m.group(3), theme.CYAN if color else ""))
        else:
            # 斜体走 DIM 而不是 `\x1b[3m`：真正的 italic 各终端支持不一，
            # 有的画成反显、有的干脆不画，比不加样式更糟。
            out.append((m.group(4), theme.DIM if color else ""))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], ""))
    return out


def _wrap_spans(spans: List[Tuple[str, str]], width: int, color: bool,
                first_prefix: str = "", rest_prefix: str = "",
                prefix_code: str = "") -> List[str]:
    """按显示列宽折行，**折完再上色**。

    顺序是要紧的：先上色再折行的话，一段样式被折断时 `RESET` 落在第二行，
    第一行没有收尾——渲染是按行独立发出去的，那一行的颜色会漏给后面。
    先折后上色则每一行自带开与关。
    """
    room = max(1, width - display_width(first_prefix))
    rest_room = max(1, width - display_width(rest_prefix))
    # 逐字符攒（而不是逐段），是为了禁则那一步能把最后一个字挤到下一行去
    lines: List[List[Tuple[str, str]]] = [[]]
    used = 0
    for text, code in spans:
        for ch in text:
            w = display_width(ch)
            if used + w > room and lines[-1]:
                carry = []
                if ch in NO_LINE_START and len(lines[-1]) >= 2:
                    carry = [lines[-1].pop()]        # 避头：把上一个字挤下来陪它
                lines.append(carry)
                room = rest_room
                used = sum(display_width(c) for c, _ in carry)
            lines[-1].append((ch, code))
            used += w
    out = []
    for idx, line in enumerate(lines):
        prefix = first_prefix if idx == 0 else rest_prefix
        if prefix_code and prefix.strip():
            prefix = theme.paint(prefix, prefix_code, color=color)
        out.append(prefix + _merge(line, color))
    return out


def _merge(cells: List[Tuple[str, str]], color: bool) -> str:
    """把逐字符的 `(字, 颜色码)` 合成一行，同色的相邻字符并成一段再上色。

    不并的话每个字都套一对转义序列——功能上一样，但录制文件与
    `screen.py` 的解析开销都白涨一个数量级。
    """
    out, buf, code = [], "", None
    for ch, c in cells:
        if c != code:
            if buf:
                out.append(theme.paint(buf, code, color=color) if code else buf)
            buf, code = ch, c
        else:
            buf += ch
    if buf:
        out.append(theme.paint(buf, code, color=color) if code else buf)
    return "".join(out)


# ---- 各块的渲染 ----


def _render_para(lines: List[str], width: int, color: bool) -> List[str]:
    out = []
    for line in lines:
        out.extend(_wrap_spans(_spans(line, color), width, color))
    return out


def _render_heading(payload, width: int, color: bool) -> List[str]:
    level, text = payload
    lines = _wrap_spans(_spans(text, color), width, color)
    # 级别差异不能只靠颜色表达：h1/h2 粗线、h3+ 细线，无色终端上照样分得出
    glyph = "━" if level <= 2 else "─"
    rule = glyph * min(width, max(display_width(_strip(text)), 1))
    painted = [theme.paint(x, theme.CYAN, color=color) for x in lines]
    return painted + [theme.paint(rule, theme.CYAN, color=color)]


def _render_hrule(_payload, width: int, color: bool) -> List[str]:
    return [theme.paint("─" * width, theme.GREY, color=color)]


def _render_quote(body: List[str], width: int, color: bool) -> List[str]:
    out = []
    for line in body:
        if not line.strip():
            out.append(theme.paint("│", theme.GREY, color=color))
            continue
        for rendered in _wrap_spans(_spans(line, color), width - 2, color):
            out.append(theme.paint("│ ", theme.GREY, color=color) + rendered)
    return out


def _render_list(items: List[str], width: int, color: bool) -> List[str]:
    out = []
    for raw in items:
        m_o = _OLIST.match(raw)
        if m_o:
            indent, marker, text = m_o.group(1), m_o.group(2) + ". ", m_o.group(3)
        else:
            m_u = _ULIST.match(raw)
            indent, text = m_u.group(1), m_u.group(2)
            # 嵌套只认一层：再深的层级在终端上已经分不清，且模型很少用
            marker = "◦ " if len(indent) >= 2 else "• "
        pad = "  " if len(indent) >= 2 else ""
        # 续行对齐到正文下面（顶格会让人以为是新的一项）
        out.extend(_wrap_spans(
            _spans(text, color), width, color,
            first_prefix=pad + marker,
            rest_prefix=pad + " " * display_width(marker),
            prefix_code=theme.CYAN))
    return out


def _render_code(payload, width: int, color: bool) -> List[str]:
    lang, body = payload
    head = "┌─ " + lang if lang else "┌─"
    out = [theme.paint(_truncate(head, width), theme.GREY, color=color)]
    bar = theme.paint("│ ", theme.GREY, color=color)
    room = max(1, width - 2)
    for line in body:
        # 代码宁可折行也不许截断：截断的代码复制出去是坏的
        pieces = _hard_wrap(line, room) or [""]
        for piece in pieces:
            out.append(bar + theme.paint(piece, theme.GREEN, color=color))
    out.append(theme.paint("└─", theme.GREY, color=color))
    return out


def _hard_wrap(text: str, width: int) -> List[str]:
    """按列宽硬折（不找词边界）。代码里没有「词」，找边界只会折在更怪的地方。"""
    out, buf, used = [], "", 0
    for ch in text:
        w = display_width(ch)
        if used + w > width and buf:
            out.append(buf)
            buf, used = "", 0
        buf += ch
        used += w
    if buf or not out:
        out.append(buf)
    return out


# ---- 表格 ----


def _aligns(sep_line: str) -> List[str]:
    out = []
    for cell in _split_row(sep_line):
        cell = cell.strip()
        if cell.startswith(":") and cell.endswith(":"):
            out.append("center")
        elif cell.endswith(":"):
            out.append("right")
        else:
            out.append("left")
    return out


def _split_row(line: str) -> List[str]:
    """按 `|` 切单元格，剥掉首尾那一对（`| a | b |` 与 `a | b` 都要认）。"""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _strip(text: str) -> str:
    """行内标记剥掉之后的纯文本——列宽要按它算，不按带标记的原文算。"""
    return "".join(t for t, _ in _spans(text, False))


def _column_widths(rows: List[List[str]], width: int) -> List[int]:
    """先按内容定宽，超了再按比例压，每列不低于 `MIN_COL_WIDTH`。"""
    count = max(len(r) for r in rows)
    natural = [1] * count
    for row in rows:
        for idx, cell in enumerate(row):
            natural[idx] = max(natural[idx], display_width(_strip(cell)))

    room = width - LEFT_PAD - COL_GAP * (count - 1)
    if room <= 0:
        return [1] * count
    if sum(natural) <= room:
        return natural

    floor = min(MIN_COL_WIDTH, max(1, room // count))
    out = [max(floor, int(n * room / sum(natural))) for n in natural]
    # 比例分配会有余数，逐列削到装得下为止——**从最宽的那列削**，
    # 否则窄列先被削光，而窄列本来就没什么可截的
    while sum(out) > room:
        widest = out.index(max(out))
        if out[widest] <= floor:
            break
        out[widest] -= 1
    return out


def _cell(text: str, col_width: int, align: str, color: bool, bold: bool) -> str:
    plain = _strip(text)
    if display_width(plain) > col_width:
        painted = _truncate(plain, col_width)
        spans = [(painted, theme.BOLD if (color and bold) else "")]
    else:
        spans = _spans(text, color)
        if color and bold:
            spans = [(t, c or theme.BOLD) for t, c in spans]
        painted = plain
    body = "".join(theme.paint(t, c, color=color) if c else t for t, c in spans)
    pad = col_width - display_width(painted)
    if align == "right":
        return " " * pad + body
    if align == "center":
        left = pad // 2
        return " " * left + body + " " * (pad - left)
    return body + " " * pad


def _render_table(payload, width: int, color: bool) -> List[str]:
    rows_raw, aligns = payload
    rows = [_split_row(r) for r in rows_raw]
    count = max(len(r) for r in rows)
    rows = [r + [""] * (count - len(r)) for r in rows]
    aligns = (aligns + ["left"] * count)[:count]
    widths = _column_widths(rows, width)

    def line(cells: List[str], bold: bool) -> str:
        parts = [_cell(c, widths[i], aligns[i], color, bold) for i, c in enumerate(cells)]
        return " " * LEFT_PAD + (" " * COL_GAP).join(parts)

    out = [line(rows[0], True)]
    # 分隔行用 ASCII `-` 而不是 `─`：后者是 Ambiguous 宽度，部分 CJK 终端画 2 列，
    # 而表格的全部价值就在对齐（模块 docstring 里那条诚实边界的落点）
    out.append(" " * LEFT_PAD + (" " * COL_GAP).join(
        theme.paint("-" * w, theme.GREY, color=color) for w in widths))
    for row in rows[1:]:
        out.append(line(row, False))
    return out


_RENDERERS = {
    "para": _render_para,
    "heading": _render_heading,
    "hrule": _render_hrule,
    "quote": _render_quote,
    "list": _render_list,
    "code": _render_code,
    "table": _render_table,
}
