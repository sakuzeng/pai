"""dock 的内容：活动区 / 队列区 / 状态行。纯组件，不碰终端。

形态照 CC 实物（features/12 的 evidence/20260811-cc实物截图）：

    Reading 1 file, running 1 shell command…   活动区：按**动作**聚合计数
      └ src/pai/modes/interactive.py           明细行（只列前几条）
    ✳ Hullaballooing… (16s · ↓ 536 tokens)     状态行：转圈 + 已用时 + 本轮 token

**为什么聚合而不是一工具一行**：工具一多就把 dock 撑高，把 scrollback 顶走。
聚合形态同样满足「并发看得见」（11 复盘质疑二的落点）——数字会从 1 变成 2。
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional

from pai.core.events import AgentEnd, AgentEvent, AgentStart, ToolEnd, ToolStart
from pai.modes.statusline import _preview
from pai.tui.width import _truncate, display_width
from pai.tui import theme
from pai.tui.component import Component

# 复制提示挂多久。凭手感定（够看清、又不碍事），无实测依据。
NOTICE_SECONDS = 2.5

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MAX_DETAIL_TOOLS = 2        # 同时展开明细的工具数：再多 dock 就把 scrollback 顶走了
MAX_PREVIEW_LINES = 6       # 每个工具最多展开几行命令
DETAIL_INDENT = "    "      # 续行缩进：与「  └ 」之后的正文对齐

# 工具名 → 动作说法。聚合按**动作**分组，所以这张表决定了「读 2 个文件」还是
# 「read_file ×2」。写成表而不是 if 链：加工具时只加一行。
_ACTIONS = {
    "read_file": "读文件",
    "search_files": "搜代码",
    "write_file": "写文件",
    "edit_file": "改文件",
    "bash": "跑命令",
    "ask_user_question": "等你回答",
    "remember": "记笔记",
}


class _Running:
    """一个正在跑的工具。用 class 不用 tuple：字段到四个了，位置参数开始靠猜。"""

    __slots__ = ("action", "preview", "shell", "started_at")

    def __init__(self, *, action: str, preview: str, shell: bool,
                 started_at: float) -> None:
        self.action, self.preview = action, preview
        self.shell, self.started_at = shell, started_at


def _action(name: str) -> str:
    return _ACTIONS.get(name, name)


def _human_duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    return f"{total // 60}m{total % 60:02d}s"


def _human_tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _short_path(path: str) -> str:
    """家目录缩成 `~`。终端底部那一行寸土寸金，全路径挤掉别的信息。"""
    if not path:
        return ""
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


def _justify(left: str, right: str, width: int) -> str:
    """左右对齐成恰好 width 列。装不下时**先牺牲右边再牺牲左边**——
    「我在哪个目录、什么模式」比「模型叫什么」更要紧。"""
    if display_width(left) + display_width(right) + 1 > width:
        right = ""
        left = _truncate(left, width)
    gap = width - display_width(left) - display_width(right)
    return left + " " * max(0, gap) + right


class Dock(Component):
    """屏幕底部那几行的内容。事件进来、行数组出去。"""

    def __init__(self, *, now: Callable[[], float] = time.monotonic,
                 color: bool = False) -> None:
        self._now = now
        self.color = color
        self._running: Dict[str, "_Running"] = {}
        self._started_at: Optional[float] = None
        self._tokens = 0
        self._mode = "default"
        self._pending = 0
        self._scrolled_up = False
        self._unseen = False
        self._notice = ""
        self._notice_at = 0.0
        self._queued = 0
        self._cwd = ""
        self._model = ""
        self._used = 0
        self._window = 0

    # --- 状态注入（由接线层调用）----------------------------------------

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def set_pending(self, count: int) -> None:
        """有多少个请求因为「用户正在打字」而被压着（T3 的 is_suppressing）。"""
        self._pending = count

    def set_queued(self, count: int) -> None:
        """排队队列里还剩多少条（feature 18：干活时打的字**本轮就注入**）。

        语义随 feature 18 变了：12 的拍板问 4 选的是「排队等本轮结束」，
        18 的问 1 改成默认中途注入，于是这个数字是**待注入量**而非「待发送量」，
        且会在本轮内随每次 drain 减少（补 2）——不是只在轮末归零。
        """
        self._queued = count

    def note_usage(self, total_tokens: int) -> None:
        self._tokens = total_tokens

    def set_cwd(self, path: str) -> None:
        self._cwd = path

    def set_model(self, name: str) -> None:
        self._model = name

    def set_context(self, used: int, window: int) -> None:
        """上下文占用。pai 早就在算（compaction 的 `context_tokens`），只是没给人看。"""
        self._used, self._window = used, window

    def is_running(self) -> bool:
        """本轮还在跑吗（转圈与计时都随时间变，需要按帧重画）。"""
        return self._started_at is not None

    # --- 事件 ---------------------------------------------------------

    def handle(self, event: AgentEvent) -> Optional[str]:
        """返回非 None 表示「这一行该 commit 进 scrollback」。"""
        if isinstance(event, AgentStart):
            self._started_at = self._now()
            self._tokens = 0
            self._running.clear()
        elif isinstance(event, ToolStart):
            self._running[event.tool_call_id] = _Running(
                action=_action(event.name), preview=_preview(event.args),
                shell=event.name == "bash", started_at=self._now())
        elif isinstance(event, ToolEnd):
            self._running.pop(event.tool_call_id, None)
        elif isinstance(event, AgentEnd):
            return self._finish()
        return None

    def _finish(self) -> str:
        """turn 结束：活动区清空，但**留一行痕迹**进 scrollback。

        清空了事的话，一轮跑完屏幕上什么都不剩——CC 留的是 `Cooked for 6m 48s`。
        """
        elapsed = 0.0 if self._started_at is None else self._now() - self._started_at
        self._running.clear()
        self._started_at = None
        parts = [f"{theme.SUMMARY} 用时 {_human_duration(elapsed)}"]
        if self._tokens:
            parts.append(f"{_human_tokens(self._tokens)} token")
        # 摘要属「元信息」，与工具行同级压暗——让位给用户的问题与 pai 的答案
        return theme.paint(" · ".join(parts), theme.GREY, color=self.color)

    # --- 渲染 ---------------------------------------------------------

    def activity_lines(self, width: int) -> List[str]:
        if not self._running:
            return []
        counts: Dict[str, int] = {}
        for item in self._running.values():
            counts[item.action] = counts.get(item.action, 0) + 1
        parts = "，".join(f"{action} {n}" for action, n in counts.items())
        turn = "" if self._started_at is None else f" · {_human_duration(self._now() - self._started_at)}"
        head = f"{theme.ANSWER} {parts}{turn}…"
        lines = [theme.paint(_truncate(head, width), theme.CYAN + theme.BOLD,
                             color=self.color)]
        for item in list(self._running.values())[:MAX_DETAIL_TOOLS]:
            lines.extend(self._detail_lines(item, width))
        return lines

    def _detail_lines(self, item: "_Running", width: int) -> List[str]:
        """一个工具的明细：首行带 `└`，续行缩进对齐；末尾报**这个工具自己**跑了多久。

        并发时「谁跑了多久」是最要紧的信息——聚合计数说不出这个
        （11 复盘质疑二要的就是这个粒度）。
        """
        if not item.preview:
            return []
        raw = item.preview.split("\n")
        shown, rest = raw[:MAX_PREVIEW_LINES], len(raw) - MAX_PREVIEW_LINES
        out = [f"  {theme.DETAIL} " + ("$ " if item.shell else "") + shown[0]]
        out += [DETAIL_INDENT + line for line in shown[1:]]
        # 耗时**接在最后一行末尾**，不单占一行——照 CC。dock 每多一行就少一行 scrollback。
        elapsed = f"({_human_duration(self._now() - item.started_at)})"
        out[-1] += f" … 还有 {rest} 行 {elapsed}" if rest > 0 else f" {elapsed}"
        return [theme.paint(_truncate(line, width), theme.DIM, color=self.color)
                for line in out]

    def queue_lines(self, width: int) -> List[str]:
        if not self._queued:
            return []
        return [theme.paint(_truncate(f"{theme.QUEUE} 已排队 {self._queued} 条", width),
                            theme.YELLOW, color=self.color)]

    def set_notice(self, text: str) -> None:
        """一句短反馈（复制结果之类）。**自己会过期**——不会过期的提示等于噪音，
        用户 2026-08-11 真跑时它一直挂在屏幕左下角不走。"""
        self._notice = text
        self._notice_at = self._now()

    def has_notice(self) -> bool:
        return bool(self._notice) and self._now() - self._notice_at < NOTICE_SECONDS

    def notice_line(self, width: int) -> str:
        """**右对齐、贴在输入行上方**（照用户要的位置：用户框的右上角）。"""
        if not self.has_notice():
            return ""
        text = _truncate(self._notice, width)
        pad = max(0, width - display_width(text))
        return " " * pad + theme.paint(text, theme.CYAN, color=self.color)

    def set_scroll(self, scrolled_up: bool, unseen: bool) -> None:
        self._scrolled_up = scrolled_up
        self._unseen = unseen

    def status_line(self, width: int) -> str:
        """只在**有话说的时候**出现。

        此前它空闲时也占一行、只写个 `default`——而 footer 里已经有模式了，
        屏幕上同一件事说了两遍（用户 2026-08-11 截图里那行孤零零的 `default`）。
        """
        bits: List[str] = []
        if self._started_at is not None:
            elapsed = self._now() - self._started_at
            frame = SPINNER[int(elapsed * 10) % len(SPINNER)]
            piece = f"{frame} {_human_duration(elapsed)}"
            if self._tokens:
                piece += f" · ↓ {self._tokens} tokens"
            bits.append(theme.paint(piece, theme.CYAN, color=self.color))
        if self._pending:
            bits.append(theme.paint(f"{self._pending} 个请求在等",
                                    theme.YELLOW, color=self.color))
        if self._scrolled_up:
            # 停在历史里时屏幕不动，得说出来；有新内容也得说，否则用户不知道
            # 「跳回底部」能看到什么（feature 13）。
            note = "已上滚" + (" · 有新内容" if self._unseen else "")
            bits.append(theme.paint(note, theme.YELLOW, color=self.color))
        if not bits:
            return ""
        return _truncate(" · ".join(bits), width)

    # --- 视觉外壳 ------------------------------------------------------

    def rule(self, width: int) -> str:
        return theme.paint(theme.RULE * max(0, width), theme.GREY, color=self.color)

    def footer_lines(self, width: int) -> List[str]:
        """底部信息条：左边「在哪、什么模式」，右边「用什么模型、上下文吃了多少」。

        形态取自 CC 与 pi 的共同点（features/12 的 evidence 两张实物）：
        用户随时想知道的四件事——**位置、模式、模型、还剩多少上下文**。
        """
        left = " · ".join(x for x in (_short_path(self._cwd), self._mode) if x)
        right = " · ".join(x for x in (self._model, self._context_text()) if x)
        if not left and not right:
            return []
        return [theme.paint(_justify(left, right, width), theme.GREY, color=self.color)]

    def _context_text(self) -> str:
        if not self._window:
            return ""
        percent = 100.0 * self._used / self._window
        return f"{percent:.1f}%/{_human_tokens(self._window)}"

    def render(self, width: int) -> List[str]:
        lines = [self.rule(width)]
        lines += self.activity_lines(width) + self.queue_lines(width)
        status = self.status_line(width)
        if status:
            lines.append(status)
        lines.extend(self.footer_lines(width))
        return [line for line in lines if display_width(line) <= width]
