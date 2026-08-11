"""回放录制：还原成屏幕，并渲染成 PNG。

**它是 feature 14 的目的本身**——让 AI 自己看得见界面，而不是每次让用户截图。

回放用的是 `screen.VirtualScreen`，**与测试断言用的是同一份实现**：
分成两份的话，「测试全绿」与「图上是对的」会各说各话。

出图用 PIL 逐格绘制，而不是把整行交给字体去排——
终端本来就是格子，逐格画才能保证「一个中文两列」与终端一致
（K concepts/terminal-width.md）。ASCII 用 Menlo、CJK 用 Hiragino：
**等宽字体没有中文，交给一个字体去排会得到与真终端不同的列位**。

用法：

    python3 -m pai.tui.replay <录制.jsonl> [-o 输出.png] [--text]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Tuple

from pai.tui.screen import Cell, VirtualScreen

CELL_W, CELL_H = 9, 20
PAD = 12
FONT_SIZE = 15

ASCII_FONT = "/System/Library/Fonts/Menlo.ttc"
CJK_FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
SYMBOL_FONT = "/System/Library/Fonts/Apple Symbols.ttf"

# 只有**真正的 CJK** 才走中文字体。
# 第一版写的是 `ord > 0x2000 就当中文`，于是 `›`(U+203A)、`█`(U+2588)、`─`(U+2500)
# 全被丢给中文字体渲染成了方块——**出图工具自己的假象**，差点让我去追不存在的 bug。
# 教训：出图工具不可信时，它报的每一个「问题」都要先排除是它自己的。
_CJK_RANGES = ((0x3000, 0x303F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
               (0xF900, 0xFAFF), (0xFF00, 0xFFEF))


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)

# 终端默认配色（照用户截图那套深色主题取的近似值）
BG = (30, 39, 46)
FG = (220, 226, 232)

_BASE = {
    30: (40, 44, 52), 31: (224, 108, 117), 32: (152, 195, 121), 33: (229, 192, 123),
    34: (97, 175, 239), 35: (198, 120, 221), 36: (86, 182, 194), 37: (200, 204, 212),
    90: (120, 130, 145), 91: (240, 140, 148), 92: (170, 210, 140), 93: (240, 210, 150),
    94: (130, 190, 245), 95: (215, 150, 235), 96: (120, 205, 215), 97: (245, 248, 252),
}


def _xterm256(n: int) -> Tuple[int, int, int]:
    if n < 16:
        return _BASE.get(30 + n if n < 8 else 90 + (n - 8), FG)
    if n < 232:
        n -= 16
        levels = (0, 95, 135, 175, 215, 255)
        return (levels[n // 36], levels[(n // 6) % 6], levels[n % 6])
    grey = 8 + (n - 232) * 10
    return (grey, grey, grey)


def _color(spec, default) -> Tuple[int, int, int]:
    if spec is None:
        return default
    if isinstance(spec, (list, tuple)) and len(spec) == 2 and spec[0] == "256":
        return _xterm256(int(spec[1]))
    n = int(spec)
    if 40 <= n <= 47:
        n -= 10
    elif 100 <= n <= 107:
        n -= 10
    return _BASE.get(n, default)


def load(path: str) -> List[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def width_segments(records: List[dict]) -> List[Tuple[int, int]]:
    """录制按终端宽度切段，返回 [(起始下标, 宽度)]。"""
    out: List[Tuple[int, int]] = []
    for i, record in enumerate(records):
        cols = record.get("cols", 80)
        if not out or out[-1][1] != cols:
            out.append((i, cols))
    return out


def replay(records: List[dict], *, rows: Optional[int] = None,
           whole: bool = False) -> VirtualScreen:
    """把录制喂进模拟器。

    **宽度中途变过的录制，默认只回放最后一段**（`whole=True` 可强制全放）。
    理由是实撞出来的：dock 的重绘用的是**相对光标移动**，行数是按当时那个宽度
    算出来的。拿 100 列的屏幕去放 50 列时写的帧，行数对不上、上移被夹到第 0 行，
    结果把顶部的 logo 覆盖掉了——**图上像是 pai 画花了，其实是回放放错了**。
    这正是「验证工具自己也要被验证」那条（features/14 复盘）。

    高度默认放大到能装下全部内容，这样 scrollback 不会被截掉。
    """
    if not records:
        raise SystemExit("录制是空的")
    segments = width_segments(records)
    if len(segments) > 1 and not whole:
        records = records[segments[-1][0]:]
    cols = records[-1].get("cols", 80)
    total = sum(r["data"].count("\n") for r in records) + 4
    screen = VirtualScreen(cols=cols, rows=rows or max(24, min(total, 400)),
                           strict=False)
    for record in records:
        screen.write(record["data"])
    return screen


def to_text(screen: VirtualScreen) -> str:
    lines = [screen._line(r) for r in range(screen.rows)]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def to_png(screen: VirtualScreen, path: str) -> str:
    from PIL import Image, ImageDraw, ImageFont

    grid = [row for row in screen.cells()]
    while grid and all(c is None or c.char == " " for c in grid[-1]):
        grid.pop()
    if not grid:
        raise SystemExit("屏幕是空的，没什么可画")

    width = PAD * 2 + screen.cols * CELL_W
    height = PAD * 2 + len(grid) * CELL_H
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    ascii_font = ImageFont.truetype(ASCII_FONT, FONT_SIZE)
    ascii_bold = ImageFont.truetype(ASCII_FONT, FONT_SIZE, index=1)
    cjk_font = ImageFont.truetype(CJK_FONT, FONT_SIZE)
    try:
        symbol_font = ImageFont.truetype(SYMBOL_FONT, FONT_SIZE)
    except OSError:
        symbol_font = ascii_font
    missing = set()

    def pick(ch: str, bold: bool):
        """按覆盖率挑字体：Menlo → 中文 → 符号。挑不到的记下来**报出去**，
        免得图上一个方块被当成 pai 的 bug。"""
        if _is_cjk(ch):
            return cjk_font
        for font in (ascii_bold if bold else ascii_font, symbol_font, cjk_font):
            if font.getmask(ch).getbbox() is not None:
                return font
        missing.add(ch)
        return ascii_font

    for y, row in enumerate(grid):
        top = PAD + y * CELL_H
        for x, cell in enumerate(row):
            if cell is None:
                continue
            left = PAD + x * CELL_W
            bg = _color(cell.bg, None)
            if cell.bg is not None:
                # 背景要**按格子铺满**——只包住文字就不是色带，是歪块
                draw.rectangle([left, top, left + CELL_W - 1, top + CELL_H - 1], fill=bg)
            if cell.char == " ":
                continue
            fg = _color(cell.fg, FG)
            if cell.dim:
                fg = tuple(int(v * 0.55) for v in fg)
            draw.text((left, top + 2), cell.char,
                      font=pick(cell.char, cell.bold), fill=fg)
    image.save(path)
    if missing:
        print("（出图字体缺字，图上会是方块，与 pai 无关：",
              " ".join(sorted(missing)), "）", file=sys.stderr)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pai.tui.replay",
                                     description="回放 pai 的终端录制")
    parser.add_argument("recording")
    parser.add_argument("-o", "--output", default=None, help="PNG 输出路径")
    parser.add_argument("--text", action="store_true", help="只打文本，不出图")
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--all", action="store_true",
                        help="宽度变过时也强制回放全程（画面会错位，仅供排查）")
    args = parser.parse_args(argv)

    records = load(args.recording)
    segments = width_segments(records)
    if len(segments) > 1:
        widths = " → ".join(str(w) for _, w in segments)
        scope = "全程（会错位）" if args.all else f"仅最后一段（{segments[-1][1]} 列）"
        print(f"（录制中途改过宽度：{widths}；本次回放{scope}）", file=sys.stderr)
    screen = replay(records, rows=args.rows, whole=args.all)
    if screen.unknown:
        print(f"（回放时遇到 {len(screen.unknown)} 处未识别序列，已忽略：",
              ", ".join(sorted(set(screen.unknown))[:5]), "）", file=sys.stderr)
    if args.text or not args.output:
        print(to_text(screen))
    if args.output:
        print(f"→ {to_png(screen, args.output)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
