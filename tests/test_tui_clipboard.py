"""复制到剪贴板（feature 16 T6）：双路径 + **不许假装成功**。

**实测前提**（features/16 evidence 第 1 条）：OSC 52 在本机 iTerm2 上
**一个字都写不进剪贴板**，BEL 与 ST 两种结尾都试过，而且**完全静默**——
终端不报错，应用无从知道自己没写成。
所以：本地必须走系统剪贴板命令（看退出码），OSC 52 只当 ssh/tmux 兜底，
且**它那条路径的提示语不许说「已复制」**。
"""

import pytest

from pai.tui.clipboard import OSC52_PREFIX, copy


class FakeRunner:
    """假的子进程执行器：记下被调用的命令，按脚本返回码/抛异常。"""

    def __init__(self, results=None):
        self.calls = []
        self.results = dict(results or {})

    def __call__(self, argv, text, timeout):
        self.calls.append((tuple(argv), text, timeout))
        outcome = self.results.get(argv[0], 0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _copy(text="hello", *, runner=None, writes=None, env=None, has=lambda c: True):
    written = writes if writes is not None else []
    return copy(text, run=runner or FakeRunner(), write=written.append,
                env=env or {}, which=has), written


def test_local_copy_uses_the_system_clipboard_command():
    runner = FakeRunner()
    result, written = _copy(runner=runner)
    assert runner.calls[0][0][0] in ("pbcopy", "wl-copy", "xclip", "xsel")
    assert runner.calls[0][1] == "hello"
    assert result.ok and result.path == "system"
    assert written == []                       # 成功就不必再发 OSC 52


def test_a_nonzero_exit_falls_back_to_osc52():
    runner = FakeRunner(results={"pbcopy": 1, "wl-copy": 1, "xclip": 1, "xsel": 1})
    result, written = _copy(runner=runner)
    assert result.path == "osc52"
    assert written and written[0].startswith(OSC52_PREFIX)


def test_a_timeout_falls_back_and_does_not_propagate():
    """子进程卡住不能把整个界面拖死——超时即当失败。"""
    import subprocess

    runner = FakeRunner(results={c: subprocess.TimeoutExpired("pbcopy", 0.5)
                                 for c in ("pbcopy", "wl-copy", "xclip", "xsel")})
    result, written = _copy(runner=runner)
    assert result.path == "osc52"
    assert written


def test_a_missing_command_is_skipped_not_crashed():
    runner = FakeRunner()
    result, _ = _copy(runner=runner, has=lambda c: c == "xsel")
    assert [c[0][0] for c in runner.calls] == ["xsel"]
    assert result.ok


def test_no_command_available_at_all_goes_straight_to_osc52():
    runner = FakeRunner()
    result, written = _copy(runner=runner, has=lambda c: False)
    assert runner.calls == []
    assert result.path == "osc52" and written


def test_ssh_sessions_skip_the_local_clipboard():
    """远程机器上的 pbcopy 写的是**远程**的剪贴板，对用户毫无意义。"""
    runner = FakeRunner()
    result, written = _copy(runner=runner, env={"SSH_CONNECTION": "1.2.3.4 22 …"})
    assert runner.calls == []
    assert result.path == "osc52" and written


def test_osc52_payload_is_base64():
    import base64

    _, written = _copy("你好", runner=FakeRunner(), has=lambda c: False)
    body = written[0][len(OSC52_PREFIX):].rstrip("\x07")
    assert base64.b64decode(body).decode() == "你好"


def test_the_osc52_path_never_claims_success():
    """**实测它会静默失败**——说「已复制」就是骗人。"""
    result, _ = _copy(runner=FakeRunner(), has=lambda c: False)
    assert "已复制" not in result.message
    assert "已尝试" in result.message


def test_the_system_path_does_claim_success():
    result, _ = _copy("a\nb", runner=FakeRunner())
    assert "已复制" in result.message


def test_empty_text_copies_nothing():
    runner = FakeRunner()
    result, written = _copy("", runner=runner)
    assert not result.ok and runner.calls == [] and written == []
