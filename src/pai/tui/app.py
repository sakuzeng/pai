"""把组件粘起来的那一层：编辑器 / 对话框 / 仲裁 / dock / 渲染器。

**它是 feature 12 的成品形态**：
- 屏幕上半归终端（scrollback），下半归 dock；两者之间只有 `commit()` 一条通道；
- 输入归属由 `InputArbiter` 算出来，**不是谁先 read 谁拿到**；
- agent 干活期间照样读键盘，回车进 followUp 队列（拍板问 4）。

仍然不碰终端：`renderer` 与 `read` 都是注入的。
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Sequence, Tuple

from pai.core.events import (
    AgentEnd,
    ToolEnd,
    AgentEvent,
    AssistantMessage,
    MessageDelta,
    render_text,
)
from pai.tui.width import _truncate
from pai.tui import logo, theme
from pai.tui.arbiter import EDITOR, InputArbiter
from pai.tui.component import Container, Component
from pai.tui.dialog import CANCELLED, Dialog
from pai.tui.sanitize import sanitize_terminal_text
from pai.tui.keys import Key
from pai.tui.dock import Dock
from pai.tui.clipboard import copy as _copy_to_clipboard
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import (Transcript, TranscriptEntry, dynamic_entry,
                                expandable_entry, text_entry)
from pai.tui.editor import LineEditor
from pai.tui.mouse import MouseEvent, merge as _merge_mouse

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
        self.editor_offset: Optional[int] = None

    def render(self, width: int) -> List[str]:
        app = self.app
        # 分隔线放最上面：它划出的是「这几行归 pai 管」，不是「输入框的边」。
        if app._intro > 0:               # 开场：logo 占住 dock，输入行还没上场
            return logo.banner(width, frame=logo.FRAMES - app._intro, color=app.color)
        lines: List[str] = []
        notice = app.dock.notice_line(width)
        if notice:
            # **在分隔线上面**：落在线下面就成了「输入框里」（用户对照 CC 指出）
            lines.append(notice)
        lines.append(app.dock.rule(width))
        lines += app.dock.activity_lines(width) + app.dock.queue_lines(width)
        # 滚动态**每次渲染现取**：存一份在 dock 里再定期同步的话，
        # 「什么时候同步」会与「什么时候组帧」错开一帧（装配期捕获的近亲）。
        app.dock.set_scroll(app.scroll.scrolled_up, app.scroll.has_unseen)
        status = app.dock.status_line(width)
        if status:
            lines.append(status)
        dialog = app.arbiter.current()
        # 输入行在 dock 里的位置——点击定位光标要用它换算屏幕行
        self.editor_offset = len(lines) if dialog is None else None
        lines.extend(dialog.render(width) if dialog is not None
                     else app.editor.render(width))
        lines.extend(app.dock.footer_lines(width))
        return lines


class TuiApp:
    def __init__(self, *, renderer, dock: Optional[Dock] = None,
                 editor: Optional[LineEditor] = None,
                 arbiter: Optional[InputArbiter] = None,
                 history: Optional[Sequence[str]] = None,
                 transcript: Optional[Transcript] = None,
                 scroll: Optional[ScrollState] = None,
                 selection: Optional[Selection] = None,
                 now: Optional[Callable[[], float]] = None,
                 color: bool = False) -> None:
        self.renderer = renderer
        self.color = color
        # alt 屏下 pai 自己持有整份会话文档；main-screen 下这两个是闲置的
        # （`keeps_transcript` 为假时 commit 不往里塞，不白涨内存）。
        self.transcript = transcript if transcript is not None else Transcript()
        self.scroll = scroll if scroll is not None else ScrollState()
        self.selection = selection if selection is not None else Selection()
        self.dock = dock if dock is not None else Dock(color=color)
        self.editor = editor if editor is not None else LineEditor(history=history)
        self.arbiter = arbiter if arbiter is not None else InputArbiter()
        self.root = _Root(self)
        self.busy = False                  # agent 是否正在干活
        self._streaming = ""               # 本条 assistant 消息已收到的增量
        self._intro = 0                    # >0 = 开场动画还剩几帧
        # 被折叠的工具结果。**有界**——长会话里全留着是白涨内存，
        # 而用户真正会回头看的只有最近几条。
        self._collapsed: List = []
        # 一次鼠标手势归谁：按下时定，松开时清。**不能靠「编辑器手里还有没有锚点」猜**——
        # 锚点在上一次点输入框之后一直留着，会把之后 transcript 的松开也吞掉
        # （用户 2026-08-11：「我从后往前移动复制不了」）。
        self._grab: Optional[str] = None
        self._now = now or time.monotonic
        self._last_frame_at = 0.0   # 拖动节流的窗口起点（见 DRAG_FRAME_INTERVAL）
        self._drag_at: Optional[float] = None   # 最后一条拖动事件的时刻
        self._copied: str = ""                  # 上次放进剪贴板的内容（避免重复复制）
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
        self.commit(dynamic_entry(lambda w: logo.settled(w, color=self.color)))
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
                or self.arbiter.is_suppressing() or self.dock.has_notice()
                or self._drag_at is not None)      # 没人来敲，拖动收尾永远不会发生

    def refresh(self) -> None:
        self.dock.set_pending(self.arbiter.pending_count()
                              if self.arbiter.is_suppressing() else 0)
        self.renderer.draw(self.root)

    def handle_resize(self) -> None:
        """SIGWINCH 之后的全套动作（从 interactive 的闭包挪进来，为的是可离线测）。

        终端在 resize 时会自己挪动备用屏的内容（实测），所以不能只重画——
        要先把「上一帧屏幕上有什么」的记忆作废，逼出一次全量重绘。
        选区必须清（R4#20）：它锚在逻辑行号上，而逻辑行是**按宽度折行**的产物，
        resize 后同一个 (row,col) 指向别的文字——「免疫 resize」的旧说法不成立。
        """
        if hasattr(self.renderer, "invalidate"):
            self.renderer.invalidate()
        self.selection.clear()
        self.refresh()

    def commit(self, payload) -> None:
        """把内容交出去。**两种模式的落点不同，这里是唯一的分叉点**（feature 13）。

        - main-screen：交给终端打进 scrollback，从此 pai 够不着（12 的形态）；
        - alt-screen：**没有「交出去」这回事**——进 transcript，永远归 pai 所有，
          这正是它能滚、能按新宽度重排的原因。

        收 `TranscriptEntry` 或纯文本。纯文本一律**按宽度折行**：
        main 下是因为「差一行整块就漂」（12 满屏阶梯的根因），
        alt 下是因为终端的自动折行被关掉了（`?7l`），不折就是截断。
        """
        entry = payload if isinstance(payload, TranscriptEntry) else text_entry(
            [payload] if isinstance(payload, str) else list(payload))
        if getattr(self.renderer, "keeps_transcript", False):
            self.transcript.append(entry)
        self.renderer.commit(entry, root=self.root)

    # --- 输入 ---------------------------------------------------------

    def feed(self, data: bytes, decoder) -> List[Tuple[str, object]]:
        """喂字节，吐动作。**输入归属在这里裁决**，不在调用方。

        鼠标事件先按批合并（实测一次滚动手势 142 条）。
        **末尾只 refresh 一次**——这条 feature 12 就有的结构才是挡住事件洪水的那道防线，
        合并是第二道（挡「将来有人在事件处理里直接 refresh」）。
        """
        actions: List[Tuple[str, object]] = []
        dragging_before = self._drag_at is not None
        for key in _merge_mouse_runs(decoder.feed(data)):
            actions.extend(self._key(key))
        if self._should_throttle_frame(dragging_before):
            # 压住这一帧，交给 `needs_tick()` 推出来的收尾帧
            # （拖动期间它本来就为真）。不压住的话，事件一条一批到达时
            # 一次手势要画上百帧——那正是「拖选卡顿」的根因。
            return actions
        self._last_frame_at = self._now()
        self.refresh()
        return actions

    def _should_throttle_frame(self, dragging_before: bool) -> bool:
        """只在拖动期节流，且只压「距上一帧不足一个窗口」的那些。

        判据用「这批之前就在拖」而不是「现在在拖」：按下那一帧要立刻画出来
        （用户得看见选区起点），松手那一帧同样——它们都不满足 dragging_before。
        """
        if not dragging_before or self._drag_at is None:
            return False
        return self._now() - self._last_frame_at < DRAG_FRAME_INTERVAL

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
        if name == "mouse":
            return self._mouse(key.mouse)
        if name == "paste_recovered":
            # 粘贴自愈的可见性（feature 33，19 遗留 2）：`201~` 丢失后按静默
            # 判据恢复，内容可能只有半截——不吭声等于把「可能截断」伪装成成功
            self.dock.set_notice("⚠ 粘贴结束符丢失，已按收到的内容恢复——请检查粘贴是否完整")
            return []
        if name in _SCROLL_KEYS:
            # **只在 alt 屏下管用**：main-screen 下滚动归终端，pai 假装自己能滚
            # 只会让「屏幕没反应」变成「屏幕乱跳」。
            if getattr(self.renderer, "keeps_transcript", False):
                _SCROLL_KEYS[name](self.scroll)
                return []
            return []

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

    def _mouse(self, event: Optional[MouseEvent]) -> List[Tuple[str, object]]:
        """鼠标事件的落点。**只在 alt 屏下有意义**——main-screen 下 pai 不拥有屏幕。

        即便如此也不许崩：终端可能残留着上一个程序开的鼠标模式，
        字节会照样送进来（这正是 feature 13 那条「我以为我在，其实不在」的镜像）。
        """
        if event is None or not getattr(self.renderer, "keeps_transcript", False):
            return []
        if event.kind == "wheel":
            self.scroll.scroll_by(event.delta * WHEEL_LINES)
            return []
        if self._input_click(event):
            return []
        row = self._logical_row(event.row)
        if event.kind == "press":
            self._finish_drag()                     # 上一次手势若没收到释放，先给它收掉
            self._grab = "transcript"
            self.selection.clear()
            self.editor.clear_selection()           # 换个地方按下，输入框那边的选区作废
            if row is not None:
                self.selection.start(row, event.col)
            return []
        if event.kind == "move":
            return []                        # 纯移动：本轮不做 hover，直接丢
        if event.kind == "drag":
            self._drag_at = self._now()
            if row is not None:
                self.selection.update(row, event.col)
            return []
        if event.kind == "release":
            had = self.selection.has_selection
            self._finish_drag()
            if not had and row is not None:
                # **没拖动才算点击**（照 CC）：否则「选一段」与「点一下」
                # 会用同一个动作触发两件事
                self._click(row)
        return []

    def _input_click(self, event: MouseEvent) -> bool:
        """点在输入行上：把光标挪过去，**并且不启动 transcript 选区**。

        拿走鼠标之后，终端原生的「点一下定位光标」也一并没了——
        这是接管鼠标的连带代价，得自己补回来（2026-08-11 真跑打回来的第三条）。
        """
        top = getattr(self.renderer, "input_row", None)
        if top is None or self.arbiter.current() is not None:
            return False
        height = len(self.editor.render(self._width()))
        line = event.row - top
        inside = 0 <= line < height
        # 列不在这里减前缀：折行后前缀宽按目标行所属逻辑行取（首行 prompt、
        # 续行 continuation），由 point_at_display 自己按行减（feature 33，
        # 21 遗留 1——旧的 point_at 把显示行当逻辑行换算，点第二段定位错）
        col = event.col
        if event.kind == "press":
            if not inside:
                return False
            self._finish_drag()
            self._grab = "input"                    # 这次手势归输入框
            index = self.editor.point_at_display(line, col, self._width())
            self.editor.cursor = index
            self.editor.start_selection(index)      # 只记锚点；裸点击不选中任何东西
            return True
        if self._grab != "input":
            return False
        # 拖动可以拖出输入框（手一抖就出去了），**整次手势仍归它**——
        # 判据是「从哪儿开始的」，不是「指针现在在哪」。
        if event.kind == "drag":
            self._drag_at = self._now()
            self.editor.extend_selection(
                self.editor.point_at_display(
                    max(0, min(height - 1, line)), col, self._width()))
            return True
        if event.kind == "release":
            self._finish_drag()
            return True
        return False

    def tick(self) -> None:
        """随时间发生的事。驱动在空闲那一拍调它。

        目前只有一件：**拖动中停手了，先把选中的放进剪贴板**。
        """
        if self._drag_at is None or self._now() - self._drag_at < DRAG_PAUSE_SECONDS:
            return
        self._autocopy()

    def _autocopy(self) -> None:
        """停手时的**不破坏性**复制：放进剪贴板 + 给提示，
        **但不结束拖动、也不清高亮**。

        为什么只能这样：释放事件真的会丢（向上/向左拖很容易把指针带出窗口，
        而终端只在窗口内上报），可**「停手」与「松开」在应用这边分不出来**——
        第一版把停手当成结束，用户当场打回：「如果我慢慢的移动，我还在按就结束了」。
        所以停手只做「把剪贴板刷成当前选中的」这件事，随后接着拖照样继续。

        内容没变就不再复制：不然停着不动的每一拍都要起一个 `pbcopy` 子进程。
        """
        text = (self.editor.selected_text() if self._grab == "input"
                else self.selection.text(self.transcript, self._width()))
        if not text or text == self._copied:
            return
        self._copied = text
        self._copy_text(text)

    def _finish_drag(self) -> None:
        """真正结束一次手势：复制 + 清掉高亮。只在**收到释放**或**下一次按下**时走。

        判据是 `_grab`（这次手势归谁）而不是 `_drag_at`——后者会被停手时的
        自动复制用掉，用它判会漏掉「停过手、随后释放丢了、用户直接点了别处」这条路。
        """
        if self._grab is None:
            return
        self._drag_at = None
        grab, self._grab = self._grab, None
        if grab == "input":
            self._copy_text(self.editor.selected_text())
            return
        self.selection.finish()
        if self.selection.has_selection:
            self._copy_selection()
            # **复制完把高亮清掉**（照 CC 的 `finishSelection` 注释：留着只是为了能复制）。
            # 不清的话用户会一直以为自己还选着东西——2026-08-11 真跑打回来的第一条。
            self.selection.clear()
        self._copied = ""

    def _logical_row(self, screen_row: int) -> Optional[int]:
        getter = getattr(self.renderer, "logical_row", None)
        return getter(screen_row) if getter is not None else None

    def _click(self, row: int) -> None:
        entry = self.transcript.owner_at(self._width(), row)
        if entry is not None:
            entry.toggle()

    def _copy_selection(self) -> None:
        self._copy_text(self.selection.text(self.transcript, self._width()))

    def _copy_text(self, text: str) -> None:
        """只管复制与提示。**清高亮不在这里**——它属于「这次手势结束了」，
        而停手时的自动复制并不结束手势（停手 ≠ 松开，两者分不出来）。
        混在一起的后果是：慢慢拖到一半，高亮被自动复制清掉了。"""
        if not text:
            return
        result = _copy_to_clipboard(text, write=self.renderer._write)
        self.dock.set_notice(result.message)

    def _dialog_key(self, dialog: Dialog, key) -> List[Tuple[str, object]]:
        result = dialog.handle(key)
        if key.name == "enter":
            # 对话框期间敲的 `!`/`/` **不是答案**——这正是 08 遗留那条铁证的修法。
            command = dialog.take_handoff()
            if command is not None:
                return [(COMMAND, command)]
        if result is None:
            return []
        # 结论跟着**这一框**走，不进共享 FIFO：FIFO 是 R4#3 那条错配的载体
        # （被中断的框事后被答掉，答案会被下一个问题取走）。
        dialog.settle(result)
        self.arbiter.resolve(dialog)
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
        # **按宽度动态渲染**：色带要铺满整行，存成行的话窗口一变宽就露出半截底色
        self.commit(dynamic_entry(lambda w: [""] + [
            theme.band(row, w, theme.USER_BG, color=self.color)
            for row in theme.wrap(f"{theme.PROMPT} {text}", w)]))
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
        body = _display_result(event).split("\n")
        self.commit([theme.paint(head, theme.CYAN, color=self.color)] + body)

    def cancel_dialog(self, dialog: Dialog) -> None:
        """撤掉一个还没答的框（中断 / EOF 退出等待时走这里）。

        **必须连队列一起摘**：只在调用方置个「不等了」的标志，框会留在队列里
        接管全部按键（`_key` 里 `arbiter.current()` 非 None 就一律走对话框分支），
        用户再把它答掉时结论就流向了下一个问题——R4#3。
        """
        dialog.settle(CANCELLED)
        self.arbiter.resolve(dialog)
        self.refresh()

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
            self.commit(_tool_entry(event, color=self.color))
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


def _display_result(event) -> str:
    """工具结果里**给终端看的那一份**。

    外来字节要消毒（见 tui/sanitize.py）。**只在这里做**：模型拿到的仍是
    `event.result` 原文——命令真打印了什么，模型就该看见什么。
    """
    return sanitize_terminal_text(event.result or "")


# 拖动期两帧之间至少隔这么久。数字取自 pi 的 `TuiBase.MIN_RENDER_INTERVAL_MS = 16`
# （约 60fps，人眼跟得上而机器省得下）。实测依据见
# `pai_playground/bench/drag_render.py`：一次手势 120 条移动事件，
# 事件一条一批到达时 206~263ms / 写终端 121 次；按 16ms 合并后 27~35ms / 16 次。
# **只对拖动生效**——按键必须帧帧跟手，一个字都不许并。
DRAG_FRAME_INTERVAL = 0.016

MAX_COLLAPSED = 32


def _hidden_rows(event) -> int:
    rows = _display_result(event).split("\n")
    return len([r for r in rows[1:] if r.strip()])


def _tool_entry(event, *, color: bool = False) -> TranscriptEntry:
    """工具结果的条目。**有被折叠的行才做成可展开的**——
    没东西可展开却能点，是给用户一个点了没反应的东西。"""
    if not _hidden_rows(event):
        return dynamic_entry(lambda w: _tool_lines(event, w, color=color))

    def render(width: int, expanded: bool) -> List[str]:
        if not expanded:
            return _tool_lines(event, width, color=color)
        # **命令要留在第一行**：展开是「把输出挂到命令下面」，不是「把命令换掉」。
        # 换掉之后用户看不出这段输出是哪条命令跑出来的（真跑打回来的）。
        head = _tool_lines(event, width, color=color, suffix=" (^O 收起)")[0]
        body: List[str] = []
        room = max(8, width - len(_OUTPUT_INDENT))
        for line in _display_result(event).split("\n"):
            body.extend(theme.wrap(line, room))
        # 引出符只在第一行，其余对齐——与正文混成一片是上一版最难读的地方
        out = [head]
        for i, line in enumerate(body):
            lead = _OUTPUT_LEAD if i == 0 else _OUTPUT_INDENT
            out.append(theme.paint(lead + line, theme.GREY, color=color))
        return out

    return expandable_entry(render)


_OUTPUT_LEAD = "  ⎿ "        # 输出块的引出符（照 CC 的形状；非 emoji，宽度 1）
_OUTPUT_INDENT = "    "


def _tool_lines(event, width: int, *, color: bool = False,
                suffix: str = "") -> List[str]:
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
    first = _display_result(event).split("\n")[0].strip()
    hidden = _hidden_rows(event)
    line = f"{head} → {first}" if first else head
    if suffix:
        line = f"{head}{suffix}"          # 展开态：只留命令 + 收起提示
    elif hidden:
        # 折叠而不说怎么看全，等于把内容藏了。
        # 形状照 CC（`FileWriteTool/UI.tsx` + `CtrlOToExpand.tsx`）：
        # `… +12 lines (ctrl+o to expand)`——**「+N 行」+ 括号里的快捷键**。
        # 不提「点击」：CC 的折叠块也能点，提示语里同样只写快捷键。
        # （我原先自己编的 `^O/点击展开`，那个斜杠让人以为是快捷键的一部分。）
        line += f" … +{hidden} 行 (^O 展开)"
    code = theme.RED if event.is_error else theme.GREY
    return [theme.paint(_truncate(line, width), code, color=color)]


# 滚动键 → 状态机操作。写成表而不是 if 链：加「滚到某条消息」之类的新键位时
# 只加一行（同 feature 12 的 MODE_CYCLE 那条经验）。
# 一格滚轮滚几行。**凭手感定，无实测依据**——3 行是终端里的常见默认值，
# 真觉得快了慢了再调（AGENTS 的照抄常数纪律：写明这个数从哪来）。
WHEEL_LINES = 3

# 拖动中停手多久，就把当前选中的先放进剪贴板。凭手感定，无实测依据。
# **它不结束拖动**——「停手」与「松开」分不出来，当成结束会误伤慢拖的人。
DRAG_PAUSE_SECONDS = 0.4


def _merge_mouse_runs(keys):
    """把**连续的**鼠标事件交给 `mouse.merge`，其余按键原样穿过、顺序不变。"""
    out, run = [], []

    def flush():
        for event in _merge_mouse(run):
            out.append(Key("mouse", mouse=event))
        run.clear()

    for key in keys:
        if key.name == "mouse" and key.mouse is not None:
            run.append(key.mouse)
            continue
        flush()
        out.append(key)
    flush()
    return out


_SCROLL_KEYS = {
    "page_up": lambda s: s.page_up(),
    "page_down": lambda s: s.page_down(),
    "ctrl_home": lambda s: s.to_start(),
    "ctrl_end": lambda s: s.to_end(),
}
