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


class Session:
    """在真 pty 里跑一个 pai 进程，并把它写出来的东西录下来。"""

    def __init__(self, provider, tmp_path, cwd=None):
        self.record = str(tmp_path / "rec.jsonl")
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
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                        # 子进程：变成 pai
            os.chdir(cwd or REPO)
            os.environ.update(env)
            os.execv(sys.executable, [sys.executable, "-c",
                                      "from pai.cli import main; main()"])
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
        try:
            os.kill(self.pid, 9)
            os.waitpid(self.pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(self.fd)


@pytest.fixture
def session(tmp_path):
    made = []

    def start(script, **kwargs):
        provider = FakeProvider(script).start()
        made.append(provider)
        s = Session(provider, tmp_path, **kwargs)
        made.append(s)
        end = time.time() + 8.0
        while time.time() < end:                 # 等启动动画放完（logo 定格进 scrollback）
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
    （K concepts/terminal-raw-mode.md）。多行内容被当成「一行」交出去，
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
    for marker in ("- file0.txt", "（后略）", "/status", "/permissions"):
        row = next(l for l in lines if marker in l)
        assert row.lstrip() == row.strip() or row.startswith((marker, " ")), \
            f"这一行没有回到列首（阶梯）：{row!r}"
        assert not row.startswith("    " * 3), f"缩进异常（阶梯）：{row!r}"

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
    """拍板问 4：干活时打的字排队，本轮结束后发出。"""
    s, provider = session([turn("第一轮答完"), turn("第二轮答完")])
    s.send("第一个问题\r", wait=0.05)             # 不等它跑完
    s.send("追加的话\r", until="第二轮答完")        # 上一轮还没跑完时提交
    screen = s.screen_text()
    assert "第一轮答完" in screen
    assert "第二轮答完" in screen, "排队的那条没被发出去"
    assert len(provider.requests) >= 2
