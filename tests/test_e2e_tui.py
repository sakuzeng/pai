"""T15：真 pai 进程 + 假 provider + 真 pty + 录制回放的端到端。

**它存在的全部理由**：feature 12 被用户打回的三条 bug（回答完全不上屏、
权限框在 raw mode 下把程序卡死、排版满屏阶梯）**全部需要一个真实的模型回合**才会暴露，
而那正是注入式 `FakeClient` 够不着、冒烟脚本又为了省钱绕开的地方。
这里把三条约束（花钱/慢/不可复现）全部解掉：假 provider 说的是同一套协议。

走的是**真实的整条路**：真进程 → 真 tty/raw mode → 真 HTTP → 真 SSE 解析
→ 真 `streaming.assemble` → 真 gate → 真 TUI 渲染 → 录制 → 回放成屏幕。
断言的是**屏幕上有什么**，也就是用户真正看到的东西。
"""

import json
import os
import pty
import select
import subprocess
import sys
import time

import pytest

from fake_provider import FakeProvider, turn
from pai.tui.replay import load, replay, to_text

pytestmark = pytest.mark.skipif(not hasattr(os, "openpty"), reason="需要 pty")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS, ROWS = 96, 30


def reap_pty_child(pid: int, fd: int, timeout: float = 5.0) -> None:
    """杀掉 pty 子进程并收割它——**边收边等**，不许裸 `waitpid` 死等。

    **这是防御性硬化，不是那条挂死的修复——根因至今未确诊。**
    曾推断「子进程卡在往 pty 写、父进程卡在 `waitpid`，两边互等」，
    但实测推翻了：`SIGKILL` 本来就能杀掉阻塞在 pty 写上的进程
    （`tests/test_pty_reaping.py` 头部记了完整经过）。

    留下有界等待的理由与那个推断无关：这个测试基建的失败模式就是「挂住」
    （2026-08-13、2026-08-18 各一次，都靠人工 kill），无界等待在这里没有存在价值。
    收割期间顺手把子进程写出来的东西读掉，也是同一个意思——少一个可能堵住的地方。
    """
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass                                     # 已经没了，照样要往下收
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if os.waitpid(pid, os.WNOHANG)[0]:
                return
        except ChildProcessError:
            return                               # 已经被收走了
        try:
            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                os.read(fd, 65536)               # 读掉就是为了让它写得下去
        except OSError:
            return                               # fd 已关/对端没了，没什么可读的了


class Session:
    """在真 pty 里跑一个 pai 进程，并把它写出来的东西录下来。"""

    def __init__(self, provider, tmp_path, cwd=None, argv=None, env=None):
        self.record = str(tmp_path / "rec.jsonl")
        env_extra = env
        env = dict(os.environ)
        env.update(
            PAI_BASE_URL=provider.base_url,
            PAI_TUI_RECORD=self.record,
            # 假 provider 不校验 key。这里的 dummy 是**刻意的**（我们本就不打真 API），
            # 与 feature 06 那次「dummy key 掩盖了 .env 解析 bug」不同：
            # 那次掩盖的是被测路径本身，这次被测路径是 TUI，key 不在路径上。
            DEEPSEEK_API_KEY="fake-key-for-e2e",
            PAI_NO_TUI="", TERM="xterm-256color", NO_COLOR="",
        )
        # 逐条覆盖（feature 38）：压缩那条 e2e 要把窗口与保留门槛调小，
        # 否则真实使用里根本攒不到触发压缩的量（`PAI_KEEP_RECENT_TOKENS` 就是
        # 为这件事开的口子，见 TODO「压缩链路的可验证性」）
        env.update(env_extra or {})
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                        # 子进程：变成 pai
            os.chdir(cwd or REPO)
            os.environ.update(env)
            code = ("import sys; sys.argv = %r; "
                    "from pai.cli import main; main()" % (argv or ["pai"],))
            os.execv(sys.executable, [sys.executable, "-c", code])
        import fcntl
        import struct
        import termios
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", ROWS, COLS, 0, 0))
        # 裸字节也留一份：**退出后打的东西不进录制**（录制器包的是 TUI 的写，
        # 而退出提示走的是普通 print）——feature 13 的退出路径要靠它断言。
        self.raw = b""

    def drain(self, seconds=1.0):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([self.fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(self.fd, 65536)
                    if not chunk:
                        return
                    self.raw += chunk
                except OSError:
                    return

    def send(self, text, wait=0.3, until=None, timeout=8.0):
        """发按键。给了 `until` 就**等到屏幕上出现它为止**，而不是死等一个固定秒数。

        死等既慢又脆：等短了偶发失败、等长了整套测试拖垮。
        """
        os.write(self.fd, text.encode() if isinstance(text, str) else text)
        if until is None:
            self.drain(wait)
            return
        end = time.time() + timeout
        while time.time() < end:
            self.drain(0.15)
            if until in self.screen_text():
                self.drain(0.15)          # 让这一帧画完，别抓到半截
                return
        raise AssertionError(
            f"等了 {timeout}s 也没在屏幕上等到 {until!r}。当前屏幕：\n{self.screen_text()}")

    def screen_text(self):
        # 启动那一瞬间录制文件还不存在——等的就是它出现，不能因此炸掉
        if not os.path.exists(self.record) or os.path.getsize(self.record) == 0:
            return ""
        return to_text(replay(load(self.record)))

    def close(self):
        reap_pty_child(self.pid, self.fd)
        os.close(self.fd)


@pytest.fixture
def session(tmp_path):
    made = []

    def start(script, wait_logo=True, provider_kwargs=None, **kwargs):
        provider = FakeProvider(script, **(provider_kwargs or {})).start()
        made.append(provider)
        s = Session(provider, tmp_path, **kwargs)
        made.append(s)
        # wait_logo=False 给「启动即阻塞在 TUI 之前」的场景（信任对话框等）：
        # logo 永远不会出现，8s 超时就是纯白等（实测省约 8s/条）
        if wait_logo:
            end = time.time() + 8.0
            while time.time() < end:             # 等启动动画放完（logo 定格进 scrollback）
                s.drain(0.15)
                if "从零实现的编码 agent" in s.screen_text():
                    break
        return s, provider

    yield start
    for item in reversed(made):
        item.stop() if isinstance(item, FakeProvider) else item.close()


# --- 三条被用户打回的 bug，各钉一条 --------------------------------------

def test_the_model_answer_reaches_the_screen(session, tmp_path):
    """用户 2026-08-11 打回第一条：`› hello` 之后直接就是 `✳ 用时 3s`，答案不见了。"""
    s, _ = session([turn("我是 pai，可以帮你写代码。")])
    s.send("你好\r", until="我是 pai")
    screen = s.screen_text()
    assert "你好" in screen                       # 用户说的
    assert "我是 pai，可以帮你写代码。" in screen    # pai 说的——**这条当初是空的**


def test_a_permission_dialog_appears_and_can_be_answered(session, tmp_path):
    """用户 2026-08-11 打回第二条：权限框走老 asker 调 `input()`，
    raw mode 下 Enter 发 `\\r` 永远等不到行尾，**整个程序死住、退都退不出去**。"""
    work = tmp_path / "work"
    work.mkdir()
    s, _ = session([turn(tool_calls=[{"name": "bash",
                                      "arguments": {"command": "echo hi"}}]),
                    turn("跑完了，输出是 hi。")], cwd=str(work))
    s.send("跑个命令\r", until="是否允许")       # 权限框弹出来
    s.send("1", until="跑完了")                   # 数字直选「允许这次」
    screen = s.screen_text()
    assert "跑完了" in screen, "答完权限之后没继续跑——大概率又卡住了"


def test_multiline_content_does_not_stair_step(session, tmp_path):
    """用户 2026-08-11 打回第三条：满屏阶梯，每行越缩越右。

    **真因是 raw mode 下 `ONLCR` 关着**——裸 `\n` 只下移、不回列首
    （K tui/terminal-raw-mode.md）。多行内容被当成「一行」交出去，
    里面的 `\n` 就成了阶梯。修法是在唯一出口处拆 `\n` 并逐行发 `\r\n`。

    钉的是**每一行都从第 0 列开始**——这才是阶梯的直接反面。
    第一版钉「行宽不越界」（虚拟屏会自动折行，永远不越界）与
    「dock 三行的结构」（工具结果已折叠成一行，没有多行内容可破坏）**都是假绿**。
    """
    work = tmp_path / "work2"
    work.mkdir()
    for i in range(8):
        (work / f"file{i}.txt").write_text("x", encoding="utf-8")
    answer = "目录里有 8 个文件：\n- file0.txt\n- file1.txt\n- file2.txt\n（后略）"
    s, _ = session([turn(tool_calls=[{"name": "bash",
                                      "arguments": {"command": "ls -la"}}]),
                    turn(answer)], cwd=str(work))
    s.send("看看目录\r", until="是否允许")
    s.send("1", until="（后略）")

    lines = [l for l in s.screen_text().split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()

    # **断言的是结构不是宽度**。第一版断言「没有行超过终端宽度」是假绿——
    # 虚拟屏与真终端一样会自动折行，永远不越界；而阶梯的真实症状是
    # **dock 被画到了错误的行**（`commit` 少算了行数，之后的相对移动全偏）。
    # 所以钉死 dock 的三行必须是屏幕最后三行、顺序正确。
    # 阶梯的直接反面：多行内容的每一行都必须**顶格**。
    # 答案这条走 `_answer_lines`（那里已经拆好了）；`/help` 这条是**整个多行字符串
    # 交给 `commit`** 的唯一现存路径——真正守住「commit 必须拆 \n」的是它。
    s.send("/help\r", until="/permissions")
    lines = [l for l in s.screen_text().split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    # 期望缩进锚到**那条路该有的样子**，两条路不同（feature 44 起）：
    #
    # - `/help` 是**整个多行字符串交给 commit** 的唯一现存路径，屏幕缩进必须
    #   与 `commands.HELP` 文案逐格相等——真正守住「commit 必须拆 \n」的是它。
    # - 答案那条走 markdown 渲染，缩进由渲染器给（圆点 gutter 2 格 + 列表符号），
    #   不再等于源文本。所以这一半改钉「渲染后的固定形状」：
    #   续行一律 2 格、列表符号是 •。阶梯的直接反面仍在——递增的缩进立刻会红。
    #
    # 第一版的 `row.startswith((marker, " "))` 只要行首有一个空格就恒真，
    # 1~11 格的阶梯全放过（R4#T2），所以这里一律用严格相等。
    from pai.modes.commands import HELP

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    for marker, want in (("• file0.txt", 2), ("• file1.txt", 2),
                         ("• file2.txt", 2), ("（后略）", 2)):
        row = next(l for l in lines if marker in l)
        assert indent_of(row) == want, \
            f"缩进漂了（阶梯）：屏幕 {indent_of(row)} 格，应为 {want} 格：{row!r}"

    for marker in ("/status", "/permissions"):
        want = indent_of(next(l for l in HELP.split("\n") if marker in l))
        row = next(l for l in lines if marker in l)
        assert indent_of(row) == want, \
            f"缩进漂了（阶梯）：屏幕 {indent_of(row)} 格，源头 {want} 格：{row!r}"

    separator, prompt, footer = lines[-3:]
    assert set(separator.strip()) == {"─"}, f"分隔线不在倒数第三行：{lines[-3:]}"
    assert prompt.lstrip().startswith("›"), f"输入行不在倒数第二行：{lines[-3:]}"
    assert footer.strip() and not footer.lstrip().startswith("›"), \
        f"footer 不在最后一行：{lines[-3:]}"


# --- 别的走不到的路径 ----------------------------------------------------

def test_the_request_carries_the_tool_schemas(session):
    """装配对不对，看 pai 真正发出去的请求。"""
    s, provider = session([turn("好的")])
    s.send("随便说点什么\r", until="好的")
    names = {t["function"]["name"] for t in provider.requests[0]["tools"]}
    assert {"bash", "read_file", "write_file", "edit_file"} <= names
    assert provider.requests[0]["stream"] is True     # 主循环走流式


def test_typing_while_busy_lands_in_the_queue(session):
    """干活时打的字进队列并被发出去。

    **语义在 feature 18 变了**：12 的拍板问 4 是「排队等本轮结束」，
    18 的问 1 改成「本轮就注入」。这条 e2e 只验「没丢」，两种语义下都成立——
    真正区分「本轮内注入」的断言（打在假 provider 收到的 messages 上）在 T5。
    """
    s, provider = session([turn("第一轮答完"), turn("第二轮答完")])
    s.send("第一个问题\r", wait=0.05)             # 不等它跑完
    s.send("追加的话\r", until="第二轮答完")        # 上一轮还没跑完时提交
    screen = s.screen_text()
    assert "第一轮答完" in screen
    assert "第二轮答完" in screen, "排队的那条没被发出去"
    assert len(provider.requests) >= 2


def test_idle_ctrl_c_actually_clears_the_input(session, tmp_path):
    """R4#24：空闲态 Ctrl+C 打出「(输入已清空，再按一次 Ctrl+C 退出)」，
    却从没调 `editor.clear()`——文本原样还在，文案说谎。
    钉的是**屏幕上输入真的没了**：`abc` 从未提交进 scrollback，
    清掉之后它就该从整个屏幕上消失。"""
    s, _ = session([turn("用不到")])
    s.send("", until="/help 看命令")            # 等开场动画放完、主循环开始读键盘
    s.send("abc", until="abc")                  # 前置：打的字先出现在输入行
    s.send("\x03", until="输入已清空")
    assert "abc" not in s.screen_text(), "说了「输入已清空」就得真的清"


def test_tui_shell_command_lands_in_history(session, tmp_path):
    """R4#17：`!命令` 历史——REPL 记（`_append_history` 在 `!` 分支之前）、
    TUI 不记（COMMAND 分支直接 dispatch），两处语义漂移。按 REPL 对齐：
    `!` 记、`/` 不记。同步点用 `$((40+2))` 的**展开值**——拿输入回显当
    「执行完成」会抢跑。"""
    from pai.modes.interactive import history_path_for

    s, _ = session([turn("用不到")])
    s.send("", until="/help 看命令")
    s.send("!echo pRoBe_$((40+2))\r", until="pRoBe_42")
    s.send("/help\r", until="/permissions")
    text = history_path_for(cwd=REPO).read_text(encoding="utf-8")
    assert "!echo pRoBe_$((40+2))" in text, "TUI 的 !命令 必须与 REPL 一样进历史"
    assert "/help" not in text, "`/` 命令不进历史——REPL 语义如此，别顺手扩大"


def test_main_screen_exit_leaves_no_dock_residue(session, tmp_path):
    """R4#18：main-screen 退出顺序——先 print 会话路径、再 `renderer.clear()`。
    DockRenderer 靠相对光标移动找自己的行，print 已把光标推走，清的就是别人的行：
    dock 残影留给 shell，退出提示反而可能被抹掉。

    退出 print 不进录制（走普通 print），所以这条喂的是 `s.raw`——pty 上的
    **全部字节**，正是真实终端拿到的那一份。"""
    from pai.tui.screen import VirtualScreen

    work = tmp_path / "ms"
    (work / ".pai").mkdir(parents=True)
    (work / ".pai" / "settings.json").write_text(
        json.dumps({"tui": {"altScreen": False}}), encoding="utf-8")
    s, _ = session([turn("用不到")], cwd=str(work))
    s.send("", until="/help 看命令")
    s.send("\x04")                                # Ctrl+D 退出
    s.drain(1.2)

    screen = VirtualScreen(cols=COLS, rows=ROWS)
    screen.write(s.raw.decode("utf-8", errors="replace"))
    text = to_text(screen)
    assert "会话已存" in text, "退出提示必须活着——被错位的清行抹掉就是 R4#18 的另一半"
    assert "再见" in text
    assert "›" not in text, "输入行是 dock 的，退出后必须被清干净"
    assert "─────" not in text, "分隔线是 dock 的，留在 shell 里就是残影"


def test_mode_cycle_works_during_dialogs_and_busy(session, tmp_path):
    """R4#25 拍板「放行安全三键」（2026-08-22）：CYCLE_MODE/EXPAND/REDRAW 在
    busy 期与对话框期不再被静默丢弃——连环权限申请时恰是最想 shift+tab 切
    acceptEdits 的时刻。EOF 仍刻意忽略（误触即退代价太大，退出走 Ctrl+C 两级）。"""
    work = tmp_path / "busy"
    work.mkdir()
    s, _ = session([turn(tool_calls=[{"name": "bash",
                                      "arguments": {"command": "sleep 0.8; echo slept"}}]),
                    turn("睡完了。")], cwd=str(work))
    s.send("跑\r", until="是否允许")
    s.send("\x1b[Z", until="模式 → acceptEdits", timeout=4.0)   # 对话框期切
    s.send("1", wait=0.2)                                       # 允许，进入 busy
    s.send("\x1b[Z", until="模式 → bypassPermissions")          # busy 期再切
    s.send("", until="睡完了")


# ---- feature 21：输入行超宽折行 ----


def test_overwide_input_tail_is_visible_in_alt_screen(session, tmp_path):
    """feature 21（R4#27）：alt 下旧行为是 `_fit` 硬截——96 列之后的内容
    （连同光标）直接消失，粘长命令的人看不到自己粘了什么。
    折行后行尾必须可见。"""
    s, _ = session([turn("用不到")])
    s.send("", until="/help 看命令")
    s.send("x" * 120 + "TAIL", until="TAIL")
    assert "TAIL" in s.screen_text()


def test_overwide_input_does_not_break_the_main_screen_dock(session, tmp_path):
    """feature 21（R4#27）：main-screen 下超宽行被终端自动折行，dock 的
    高度记账全错（阶梯同款根因）。折行后 dock 结构必须完好：
    分隔线在输入区上方、footer 是最后一行、输入折成的每行都带前缀。"""
    work = tmp_path / "ms21"
    (work / ".pai").mkdir(parents=True)
    (work / ".pai" / "settings.json").write_text(
        json.dumps({"tui": {"altScreen": False}}), encoding="utf-8")
    s, _ = session([turn("用不到")], cwd=str(work))
    s.send("", until="/help 看命令")
    s.send("y" * 120 + "TAIL", until="TAIL")

    lines = [l for l in s.screen_text().split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    footer = lines[-1]
    # footer 是状态行（含 cwd 路径，路径里可能有零星字母），判据用「不是输入行」：
    # 不带提示符、也不是折行正文（连续 y）
    assert footer.strip() and "›" not in footer and "yyyy" not in footer, \
        f"footer 必须是最后一行：{lines[-4:]!r}"
    rows = [i for i, l in enumerate(lines) if "y" * 10 in l or "TAIL" in l]
    assert rows, "输入内容要在屏幕上"
    sep = lines[rows[0] - 1]
    assert set(sep.strip()) == {"─"}, f"分隔线该在输入区上方：{sep!r}"
    assert lines[rows[0]].lstrip().startswith("›"), "输入首行带提示符"
    for i in rows[1:]:
        assert lines[i].startswith("  "), f"折行续排行该带两格缩进：{lines[i]!r}"


# ---- feature 24：--resume 真 pty e2e ----


def test_resume_carries_the_conversation_into_a_new_process(session, tmp_path):
    """两个真进程接力：第一个聊完退出，第二个 `--resume` 起来后，
    发给 provider 的请求里必须带着第一段对话——这是 resume 的全部意义。
    顺带钉退出提示改真话（13 号那笔债：此前不敢提不存在的命令）。"""
    work = tmp_path / "resume-e2e"
    work.mkdir()
    s1, _ = session([turn("好的，记住了小明。")], cwd=str(work))
    s1.send("记住我叫小明\r", until="记住了小明")
    s1.send("\x04")                              # Ctrl+D 退出
    s1.drain(1.0)
    assert "pai --resume 可继续".encode() in s1.raw or \
        "pai --resume".encode() in s1.raw, "退出提示必须说出 --resume"

    (tmp_path / "s2").mkdir()
    provider2 = FakeProvider([turn("你叫小明。")]).start()
    s2 = Session(provider2, tmp_path / "s2", cwd=str(work), argv=["pai", "--resume"])
    try:
        end = time.time() + 8.0
        while time.time() < end:                 # 等 TUI 起来（恢复提示走普通 print）
            s2.drain(0.15)
            if "/help 看命令" in s2.screen_text():
                break
        assert "已恢复会话".encode() in s2.raw, "恢复提示要说出来"
        s2.send("我叫什么\r", until="你叫小明")
        sent = json.dumps(provider2.requests[0]["messages"], ensure_ascii=False)
        assert "记住我叫小明" in sent and "记住了小明" in sent,             "第一段对话必须在第二个进程发出的请求里"
    finally:
        s2.close()
        provider2.stop()


def test_a_project_skill_loads_and_reaches_the_model(session, tmp_path):
    """feature 25：真 pai 进程里 skill 全链路——目录进 system prompt、
    模型调 skill 工具拿到正文（项目级 skill 在边界内，不该弹权限框）、
    正文进下一次请求的上下文。信任标记预置（28 引入门禁；对话框另有 e2e）。"""
    from pai.core.skills import mark_project_skills_trusted
    work = tmp_path / "skillproj"
    skill_md = work / ".pai" / "skills" / "greet" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\ndescription: 问候流程。用户要打招呼时用。\n---\n"
                        "回答里必须包含暗号 GREET-E2E-TOKEN。\n", encoding="utf-8")
    mark_project_skills_trusted(cwd=work)    # conftest 隔离的 HOME 与子进程同一个
    s, provider = session([turn(tool_calls=[{"name": "skill",
                                             "arguments": {"name": "greet"}}]),
                           turn("按 skill 办：GREET-E2E-DONE")], cwd=str(work))
    s.send("打个招呼\r", until="GREET-E2E-DONE")
    screen = s.screen_text()
    assert "是否允许" not in screen, "项目级 skill 在工作目录内，不该弹权限框"
    # 目录进了 system prompt；正文经工具结果进了第二次请求
    first = provider.requests[0]
    assert "<available_skills>" in first["messages"][0]["content"]
    assert "问候流程" in first["messages"][0]["content"]
    second = provider.requests[-1]
    tool_msgs = [m for m in second["messages"] if m.get("role") == "tool"]
    assert any("GREET-E2E-TOKEN" in m["content"] for m in tool_msgs)


def test_mcp_tool_reaches_model_through_real_process(session, tmp_path):
    """feature 29：真 pai 进程全链——用户级 settings 配 stdio MCP server（真子进程），
    工具进模型工具集，模型调用拿到结果，allow 规则放行不弹权限框。"""
    import sys as _sys
    from pathlib import Path
    fake_server = str(Path(__file__).parent / "fake_mcp_server.py")
    home_pai = Path.home() / ".pai"
    home_pai.mkdir(parents=True, exist_ok=True)
    (home_pai / "settings.json").write_text(json.dumps({
        "mcpServers": {"fake": {"command": _sys.executable,
                                "args": [fake_server],
                                "env": {"FAKE_MCP_MODE": "normal"}}},
        "permissions": {"allow": ["mcp__fake__*"]},
    }), encoding="utf-8")
    work = tmp_path / "mcpproj"
    work.mkdir()
    s, provider = session([turn(tool_calls=[{"name": "mcp__fake__echo_token",
                                             "arguments": {}}]),
                           turn("拿到了 MCP-E2E-DONE")], cwd=str(work))
    s.send("调一下 mcp 工具\r", until="MCP-E2E-DONE")
    screen = s.screen_text()
    assert "是否允许" not in screen, "allow 规则放行，不该弹权限框"
    tool_names = {t["function"]["name"] for t in provider.requests[0]["tools"]}
    assert "mcp__fake__echo_token" in tool_names
    tool_msgs = [m for m in provider.requests[-1]["messages"]
                 if m.get("role") == "tool"]
    assert any("FAKE-MCP-TOKEN-4711" in m["content"] for m in tool_msgs)


def test_project_skills_trust_dialog_gates_then_persists(session, tmp_path):
    """feature 28 问 2·B：首遇未信任项目 skills，启动即真人确认——答「信任」后
    本会话加载（目录进 system prompt）且标记持久化。对话在 TUI 起来之前（普通
    print + stdin），录制文件里没有，从裸字节里断言问题出现过。"""
    from pai.core import paths
    work = tmp_path / "skillproj"
    skill_md = work / ".pai" / "skills" / "greet" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\ndescription: 问候流程\n---\n正文\n", encoding="utf-8")
    s, provider = session([turn("好的 TRUST-E2E-DONE")], cwd=str(work),
                          wait_logo=False)      # 对话框挡在 TUI 前，logo 不会出现
    # 等信任问题出现在裸字节里（通常 <1s；上限只为慢机器兜底）
    end = time.time() + 8.0
    while time.time() < end and "项目 .pai/skills" not in s.raw.decode("utf-8", "replace"):
        s.drain(0.2)
    assert "项目 .pai/skills" in s.raw.decode("utf-8", "replace"), \
        f"启动时该有信任提问。裸输出：{s.raw.decode('utf-8', 'replace')[-400:]}"
    s.send("1\r", until="从零实现的编码 agent", timeout=10.0)
    s.send("你好\r", until="TRUST-E2E-DONE")
    assert "<available_skills>" in provider.requests[0]["messages"][0]["content"]
    marker = paths.project_dir(work) / "skills_trusted"
    assert marker.is_file(), "选「信任」必须持久化标记"


# --- feature 38：离线其实能验、只是一直没验的两条（feature 15 遗留）-------------


def test_automatic_compaction_really_happens_in_a_real_process(session, tmp_path):
    """自动压缩在真进程 + 真 pty 里真的发生过——这条到今天为止从没被验证过。

    2026-08-10 用户按测试清单真跑，输出里只有两次「锚点不足」，
    `🗜️ 压缩：切于 N` 一次都没出现过；离线测试之所以全绿，是因为它们直接传
    `CompactionSettings(keep_recent_tokens=1)` 把那道坎绕过去了。
    到 feature 35 才有了 `PAI_KEEP_RECENT_TOKENS` 这个口子，
    到 feature 38 才发现假 provider 的固定 usage 让这条路结构上走不到
    （相邻锚差值恒为 0 → 切点永远是「无可压」）。

    两头都断言，缺一不可：屏幕上用户看得见压缩发生了，
    以及假 provider 真的收到过一次**不带 tools 的请求**——那是摘要请求，
    也是「压缩不只是打了行字」的唯一硬证据。
    """
    work = tmp_path / "work"
    work.mkdir()
    (work / "甲.txt").write_text("内容", encoding="utf-8")
    read_call = [{"name": "read_file", "arguments": {"path": "甲.txt"}}]
    s, provider = session(
        [
            # 两轮工具调用攒出两个锚点，usage 按轮钉死：差值 4000 跨过保留门槛
            turn(tool_calls=read_call, prompt_tokens=4000),
            turn(tool_calls=read_call, prompt_tokens=8000),
            turn("这是摘要"),                      # ← 压缩触发的摘要请求（非流式）
            turn("压缩之后我接着答完了。"),
        ],
        cwd=str(work),
        env={"PAI_CONTEXT_WINDOW": "20000", "PAI_KEEP_RECENT_TOKENS": "1000"},
    )

    s.send("看看那个文件\r", until="压缩之后我接着答完了")
    screen = s.screen_text()
    # 不比 emoji：源码里是 `🗜️`（带变体选择符 U+FE0F），屏幕模型里是 `🗜`。
    # 断言钉的是「用户看得见压缩发生了」，不是字形的字节形状。
    assert "压缩：切于" in screen, f"屏幕上没有压缩发生过的痕迹：\n{screen}"
    assert "锚点不足" in screen, (
        "压缩前应先有一次「锚点不足」——那是锚定法的两步节奏（STATUS 已知缺陷 1），"
        "这条 e2e 顺带把它从设计推论变成跑出来的事实")

    summaries = [r for r in provider.requests if "tools" not in r]
    assert len(summaries) == 1, (
        f"摘要请求（不带 tools 的那一次）应恰好一次，实际 {len(summaries)}——"
        "只打了字没发请求的话，压缩就是假的")
    flattened = json.dumps(summaries[0]["messages"], ensure_ascii=False)
    assert "看看那个文件" in flattened, "摘要请求里应带着被压掉的那段历史"


def test_ctrl_c_mid_stream_stops_the_answer_and_keeps_the_repl_alive(session, tmp_path):
    """流中途 Ctrl+C：掐得断，且 REPL 不死（feature 15 遗留登记的另一条）。

    「掐得断」与「进程还活着」必须一起断言——只验前者的话，一个把整个 REPL
    带栈掀掉的实现照样通过（而那正是 pai 早期真实撞到过的形态，
    D#40 之所以选「只置标志不抛异常」就是为了它）。
    """
    s, _ = session([
        turn("这段答案很长" * 12, delay=0.05),      # 逐字符慢放（约 3.6s），给中断留窗口
        turn("我还活着。"),
    ])

    s.send("", until="/help 看命令")                # 等主循环真的开始读键盘
    # 这里只能死等一个固定秒数，不能用 `until`：流式期间的增量要等这一轮
    # 收尾才进 scrollback，屏幕上看不到「正在吐」——拿屏幕当同步点会一直等到
    # 整轮结束，Ctrl+C 就变成了空闲态的那一档（第一版正是这么假绿的）。
    s.send("说点长的\r", wait=1.0)
    s.send("\x03", until="已中断")
    screen = s.screen_text()
    assert "已中断" in screen
    # 真掐断了：整段答案不该完整出现在屏幕上。少了这一条，一个「中断消息照打、
    # 但流照样跑完」的实现同样能通过——那正是「已中断」这三个字最容易撒的谎。
    assert "这段答案很长" * 12 not in screen.replace("\n", ""), \
        f"答案跑完了才「中断」，等于没断：\n{screen}"

    s.send("还在吗\r", until="我还活着")            # 掐完还能接着聊 = REPL 没死
    assert "我还活着。" in s.screen_text()


# --- feature 39：干活期间的键盘不能像死了一样 ---------------------------------


def test_typing_during_a_long_command_shows_up_on_screen(session, tmp_path):
    """一条跑着的长命令期间打的字，屏幕上要看得见（12 复盘质疑二，挂了十五天）。

    此前 TUI 只在「有事件到来时」顺手 poll 一次键盘，而 bash 跑的那几十秒里
    一个事件都不发——字符没丢（在内核 tty 缓冲区等着），但屏幕一动不动，
    用户会以为键盘死了。在最需要反馈的时候没有反馈。

    用 `!命令` 而不是让模型调 bash：这条路不过权限框，测试短且只测一件事。
    两条路在这一点上是同一段代码（`shell._wait` 的轮询循环）。
    """
    s, _ = session([turn("用不到")])
    s.send("", until="/help 看命令")
    s.send("!sleep 3\r", wait=0.4)          # 命令跑起来，主线程进 bash 的等待循环
    s.send("干活时打的字", wait=0.8)         # 这时候打字——命令还在跑
    assert "干活时打的字" in s.screen_text(), (
        "长命令期间打的字没上屏——键盘看起来像死了")


def test_ctrl_c_can_stop_a_shell_command_in_the_tui(session, tmp_path):
    """TUI 里 `!命令` 期间按 Ctrl+C 要真的掐得断。

    这条是写上一条时顺带照出来的：raw mode 关掉了 ISIG，Ctrl+C 只是一个字节，
    而命令跑着的时候没有任何人读键盘——于是那个字节要等命令自己跑完才被看见，
    中断标志永远来不及置位。`_interruptible` 装的 SIGINT 处理器在这条路上
    也是摆设（raw mode 下压根不会有 SIGINT）。

    断言用时间：`sleep 8` 若真被掐断，几秒内就该回到提示符。
    """
    s, _ = session([turn("用不到")])
    s.send("", until="/help 看命令")
    started = time.time()
    s.send("!sleep 8\r", wait=0.5)
    s.send("\x03", wait=0.5)
    s.send("", until="已中断", timeout=4.0)
    assert time.time() - started < 8.0, "Ctrl+C 没掐断，是等 sleep 自己跑完的"
