"""把组件粘起来的那一层：编辑器 / 对话框 / 仲裁 / dock / 渲染器。

**它是 feature 12 的成品形态**：
- 屏幕上半归终端（scrollback），下半归 dock；两者之间只有 `commit()` 一条通道；
- 输入归属由 `InputArbiter` 算出来，**不是谁先 read 谁拿到**；
- agent 干活期间照样读键盘，回车进 followUp 队列（拍板问 4）。

仍然不碰终端：`renderer` 与 `read` 都是注入的。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from pai.core.events import (
    AgentEnd,
    ToolEnd,
    AgentEvent,
    AssistantMessage,
    MessageDelta,
    render_text,
)
from pai.modes.statusline import _truncate
from pai.tui import logo, theme
from pai.tui.arbiter import EDITOR, InputArbiter
from pai.tui.component import Container, Component
from pai.tui.dialog import CANCELLED, Dialog
from pai.tui.dock import Dock
from pai.tui.editor import LineEditor

# feed() 吐出来的动作。用 (kind, payload) 而不是各种回调——
# 主循环拿着它走 if/elif，读起来就是「用户干了什么」。
SUBMIT = "submit"          # 提交了一行（空闲态 → 跑一轮；干活态 → 进 followUp）
COMMAND = "command"        # `/` 命令或 `!` shell，含对话框期间交回来的
CYCLE_MODE = "cycle_mode"  # shift+tab
INTERRUPT = "interrupt"    # Ctrl+C
EOF = "eof"                # Ctrl+D
REDRAW = "redraw"          # Ctrl+L
EXPAND = "expand"          # Ctrl+O：展开被折叠的工具输出

# 不用 emoji：用户终端上 `🤖` 渲染成了方块（theme.py 第一条硬约束）
ANSWER_PREFIX = theme.ANSWER + " "


class _Root(Component):
    """dock 的根：活动区/队列区 + 对话框或输入行 + 状态行。

    对话框与输入行**互斥**——谁在这个位置由仲裁决定，这就是「模态」的全部实现。
    """

    def __init__(self, app: "TuiApp") -> None:
        self.app = app

    def render(self, width: int) -> List[str]:
        app = self.app
        # 分隔线放最上面：它划出的是「这几行归 pai 管」，不是「输入框的边」。
        if app._intro > 0:               # 开场：logo 占住 dock，输入行还没上场
            return logo.banner(width, frame=logo.FRAMES - app._intro, color=app.color)
        lines = [app.dock.rule(width)]
        lines += app.dock.activity_lines(width) + app.dock.queue_lines(width)
        status = app.dock.status_line(width)
        if status:
            lines.append(status)
        dialog = app.arbiter.current()
        lines.extend(dialog.render(width) if dialog is not None
                     else app.editor.render(width))
        lines.extend(app.dock.footer_lines(width))
        return lines


class TuiApp:
    def __init__(self, *, renderer, dock: Optional[Dock] = None,
                 editor: Optional[LineEditor] = None,
                 arbiter: Optional[InputArbiter] = None,
                 history: Optional[Sequence[str]] = None,
                 color: bool = False) -> None:
        self.renderer = renderer
        self.color = color
        self.dock = dock if dock is not None else Dock(color=color)
        self.editor = editor if editor is not None else LineEditor(history=history)
        self.arbiter = arbiter if arbiter is not None else InputArbiter()
        self.root = _Root(self)
        self.busy = False                  # agent 是否正在干活
        self._answers: List = []
        self._streaming = ""               # 本条 assistant 消息已收到的增量
        self._intro = 0                    # >0 = 开场动画还剩几帧
        # 被折叠的工具结果。**有界**——长会话里全留着是白涨内存，
        # 而用户真正会回头看的只有最近几条。
        self._collapsed: List = []
        self._expanded = 0                 # 已经展开到倒数第几条

    # --- 屏幕 ---------------------------------------------------------

    def start_intro(self, frames: int = logo.FRAMES) -> None:
        """播开场动画。每帧只改配色，几何不动（见 logo.py）。"""
        self._intro = frames
        self.refresh()

    def intro_tick(self) -> bool:
        """推进一帧。返回 False 表示放完了——此时把**定格的那份** commit 进 scrollback。

        commit 的必须是 `settled()` 而不是最后一帧：scrollback 里的东西不会再重画，
        留一个「高光正扫到一半」的姿态在那儿就成了永久的半成品。
        """
        if self._intro <= 0:
            return False
        self._intro -= 1
        if self._intro > 0:
            self.refresh()
            return True
        self.commit(logo.settled(self._width(), color=self.color))
        return False

    def _width(self) -> int:
        try:
            return self.renderer._width()
        except Exception:                   # noqa: BLE001 - 拿不到宽度就按 80 画
            return 80

    def needs_tick(self) -> bool:
        """没有输入时还需不需要重画。

        **真跑冒烟撞出来的**：空闲时驱动每 100ms 醒一次并无条件重画，
        于是屏幕上每秒白刷 10 帧（离线测试看不出来——它们从不走超时那条路）。
        只有两件事是随时间变化的：转圈动画、以及「停手 1500ms 放行对话框」。
        """
        return (self._intro > 0 or self.dock.is_running()
                or self.arbiter.is_suppressing())

    def refresh(self) -> None:
        self.dock.set_pending(self.arbiter.pending_count()
                              if self.arbiter.is_suppressing() else 0)
        self.renderer.draw(self.root)

    def commit(self, lines) -> None:
        """把内容上交给 scrollback。dock 与 scrollback 之间唯一的通道。

        **必须拆换行、必须折行**：交上去的东西一旦超过一行的量，
        终端会自己折，而 dock 的相对光标移动是按「我写了几行」算的——
        差一行整块就漂（用户 2026-08-11 满屏阶梯的根因）。
        """
        if isinstance(lines, str):
            lines = [lines]
        width = self._width()
        out: List[str] = []
        for line in lines:
            out.extend(theme.wrap(line, width))
        self.renderer.commit(out, root=self.root)

    # --- 输入 ---------------------------------------------------------

    def feed(self, data: bytes, decoder) -> List[Tuple[str, object]]:
        """喂字节，吐动作。**输入归属在这里裁决**，不在调用方。"""
        actions: List[Tuple[str, object]] = []
        for key in decoder.feed(data):
            actions.extend(self._key(key))
        self.refresh()
        return actions

    def _key(self, key) -> List[Tuple[str, object]]:
        name = key.name
        if name == "ctrl_c":
            return [(INTERRUPT, None)]
        if name == "ctrl_l":
            return [(REDRAW, None)]
        if name == "ctrl_o":
            return [(EXPAND, None)]
        if name == "shift_tab":
            return [(CYCLE_MODE, None)]

        dialog = self.arbiter.current()
        if dialog is not None:
            return self._dialog_key(dialog, key)

        if name == "ctrl_d" and not self.editor.text:
            return [(EOF, None)]
        submitted = self.editor.handle(key)
        self.arbiter.note_typing(self.editor.text)
        if submitted is None:
            return []
        return self._submitted(submitted)

    def _dialog_key(self, dialog: Dialog, key) -> List[Tuple[str, object]]:
        result = dialog.handle(key)
        if key.name == "enter":
            # 对话框期间敲的 `!`/`/` **不是答案**——这正是 08 遗留那条铁证的修法。
            command = dialog.take_handoff()
            if command is not None:
                return [(COMMAND, command)]
        if result is None:
            return []
        self._answers.append(None if result is CANCELLED else result)
        self.arbiter.resolve()
        return []

    def _submitted(self, line: str) -> List[Tuple[str, object]]:
        text = line.strip()
        self.arbiter.note_typing("")
        if not text:
            return []
        # 用户说的与 pai 说的必须一眼分得开（用户 2026-08-11 指出两者长得一样）：
        # 用户行的提示符高亮、正文常色；pai 的回答戴一个青色圆点。
        # **层级：用户 > agent > 工具**。
        # 第一版把用户行做成了灰色，而工具行、提示行也是灰的——于是它成了整屏
        # 最不显眼的东西（用户 2026-08-11 指出）。可它是长对话里最重要的导航锚点：
        # 一眼扫下来要先找到「我问了什么」。所以它加粗、走亮色，且**前面留一个空行**
        # 把轮次分开——没有留白，一屏文字会糊成一片。
        width = self._width()
        rows = theme.wrap(f"{theme.PROMPT} {text}", width)
        self.commit([""] + [theme.band(row, width, theme.USER_BG, color=self.color)
                            for row in rows])
        if text.startswith(("/", "!")) and not self.busy:
            return [(COMMAND, text)]
        return [(SUBMIT, text)]

    # --- 真人问答（asker 的落点）---------------------------------------

    def enqueue_dialog(self, dialog: Dialog, *, user_invoked: bool = False) -> None:
        self.arbiter.enqueue(dialog, user_invoked=user_invoked)
        self.refresh()

    def expand_last(self) -> None:
        """把最近一条被折叠的工具输出**整段**打进 scrollback。

        连按可以继续往回走——一轮里常有好几个工具，只能看最后一个的话没什么用。
        方案 A 下做不到「原地展开」（内容已经归终端所有，够不着），
        所以这里是「再打一遍完整的」。真正的原地展开要 alt-screen，见 features/13。
        """
        width = self._width()
        if self._expanded >= len(self._collapsed):
            self.commit(theme.paint("（没有更早的工具输出可展开了）", theme.GREY,
                                    color=self.color))
            return
        self._expanded += 1
        event = self._collapsed[-self._expanded]
        head = f"{theme.DETAIL} {event.name} 的完整输出："
        body = (event.result or "").split("\n")
        self.commit([theme.paint(head, theme.CYAN, color=self.color)] + body)

    def take_answer(self):
        return self._answers.pop(0) if self._answers else None

    # --- 事件 ---------------------------------------------------------

    def on_event(self, event: AgentEvent) -> None:
        """loop 的事件进来：dock 更新 + 该留痕的上交 scrollback。

        **答案的上屏走这里，不走 `render_text`**——`render_text(AssistantMessage)`
        返回 None（它的契约是「流式已逐字打过，别重打」，那是 echo 模式的前提）。
        TUI 不逐字打（dock 之上的行够不着，边流边写会与 dock 打架），
        所以这里**攒增量、整条上交**。2026-08-11 用户真跑时发现答案完全没显示，
        根因就是两边都以为对方会打。
        """
        if isinstance(event, MessageDelta):
            self._streaming += event.text
            return
        if isinstance(event, AssistantMessage):
            self._flush_answer(event.content)
            self.refresh()
            return

        summary = self.dock.handle(event)
        if isinstance(event, AgentEnd):
            # `final` 的文本就是刚才那条 assistant 消息（已上交）；
            # `budget`/`max_steps`/`interrupted` 是 loop **合成**的，从来没流过，必须打。
            self._flush_answer(None)
            if event.reason != "final" and event.text:
                self.commit(_answer_lines(event.text, color=self.color))
            if summary is not None:
                self.commit(summary)
            return
        if isinstance(event, ToolEnd):
            if _hidden_rows(event):
                self._collapsed.append(event)
                del self._collapsed[:-MAX_COLLAPSED]
                self._expanded = 0          # 有新东西了，展开游标回到最新
            self.commit(_tool_lines(event, self._width(), color=self.color))
            return
        text = render_text(event)
        if text is not None:
            self.commit(text)
        else:
            self.refresh()

    def _flush_answer(self, content: Optional[str]) -> None:
        """把攒着的增量（或非流式路径下的整条 content）上交 scrollback。"""
        answer = self._streaming or (content or "")
        self._streaming = ""
        if answer.strip():
            self.commit(_answer_lines(answer, color=self.color))


def _answer_lines(text: str, *, color: bool = False) -> List[str]:
    """答案的形态：第一行戴一个圆点，其余原样。"""
    prefix = theme.paint(theme.ANSWER, theme.CYAN, color=color) + " "
    lines = text.split("\n")
    return [prefix + lines[0]] + lines[1:]


MAX_COLLAPSED = 32


def _hidden_rows(event) -> int:
    rows = (event.result or "").split("\n")
    return len([r for r in rows[1:] if r.strip()])


def _tool_lines(event, width: int, *, color: bool = False) -> List[str]:
    """工具结果**默认折叠成一行**（照 CC）。

    全量倒进 scrollback 会把对话本身冲走——用户 2026-08-11 的截图里
    一条 `ls -la` 的输出占了半屏，而真正想看的答案被顶没了。
    折叠掉的行数要说出来，否则用户不知道自己少看了什么。
    **展开机制暂未做**（pai 还没有可点的东西），已登记 TODO。
    """
    head = f"{theme.DETAIL} {event.name}"
    args = ", ".join(f"{k}={v!r}" for k, v in (event.args or {}).items())
    if args:
        head += f"({_truncate(args, max(8, width // 3))})"
    first = (event.result or "").split("\n")[0].strip()
    hidden = _hidden_rows(event)
    line = f"{head} → {first}" if first else head
    if hidden:
        # 折叠而不说怎么看全，等于把内容藏了
        line += f" … 还有 {hidden} 行 · ^O 展开"
    code = theme.RED if event.is_error else theme.GREY
    return [theme.paint(_truncate(line, width), code, color=color)]
