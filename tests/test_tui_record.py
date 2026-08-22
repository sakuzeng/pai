"""T14：录制与回放。

存在的理由是 feature 12 的教训：四轮视觉修正全靠用户截图往返，
**pai 自己看不见屏幕上最后长什么样**。
"""

import json

import pytest

from pai.tui.record import ENV_VAR, Recorder, record_path
from pai.tui.replay import load, replay, to_png, to_text
from pai.tui.screen import VirtualScreen


def test_recording_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert record_path() is None
    monkeypatch.setenv(ENV_VAR, "/tmp/x.jsonl")
    assert record_path() == "/tmp/x.jsonl"


def test_wrap_passes_through_unchanged(tmp_path):
    """录制只是 tee：被包住的 write 收到的东西必须一个字节不差。"""
    seen = []
    rec = Recorder(str(tmp_path / "r.jsonl"), size=lambda: (80, 24), now=lambda: 0.0)
    write = rec.wrap(seen.append)
    write("\x1b[2Khello")
    rec.close()
    assert seen == ["\x1b[2Khello"]


def test_recording_carries_the_terminal_size(tmp_path):
    """resize 是已知的问题多发区——不记尺寸就还原不出当时的样子。"""
    path = tmp_path / "r.jsonl"
    size = [(80, 24)]
    rec = Recorder(str(path), size=lambda: size[0], now=lambda: 0.0)
    rec.note("a")
    size[0] = (40, 24)
    rec.note("b")
    rec.close()
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [r["cols"] for r in records] == [80, 40]


def test_a_broken_recording_file_never_breaks_the_session(tmp_path):
    """录制坏了不能把会话带崩。"""
    rec = Recorder(str(tmp_path / "nope" / "r.jsonl"), size=lambda: (80, 24))
    rec._file = None
    seen = []
    rec.wrap(seen.append)("x")
    assert seen == ["x"]


def test_replay_reconstructs_the_screen(tmp_path):
    path = tmp_path / "r.jsonl"
    rec = Recorder(str(path), size=lambda: (20, 6), now=lambda: 0.0)
    rec.wrap(lambda _: None)("第一行\r\n第二行")
    rec.close()
    screen = replay(load(str(path)))
    assert "第一行" in to_text(screen)
    assert "第二行" in to_text(screen)


def test_replay_keeps_colour_and_background(tmp_path):
    """出图要还原配色——用户输入那条色带正是靠背景色认出来的。"""
    path = tmp_path / "r.jsonl"
    rec = Recorder(str(path), size=lambda: (20, 4), now=lambda: 0.0)
    rec.wrap(lambda _: None)("\x1b[48;5;236m\x1b[36m› 问\x1b[0m 普通")
    rec.close()
    screen = replay(load(str(path)))
    cells = [c for c in screen.cells()[0] if c is not None]
    assert cells[0].bg == ("256", 236)
    assert cells[0].fg == 36
    assert cells[-1].bg is None            # 重置之后不该还带着底色


def test_replay_is_lenient_about_unknown_sequences():
    """真实终端流里什么都可能出现——回放到一半炸掉比少画一个色码更糟。"""
    screen = VirtualScreen(cols=10, rows=2, strict=False)
    screen.write("\x1b[99Zab")
    assert screen.unknown
    assert "ab" in to_text(screen)


def test_png_is_produced_and_non_trivial(tmp_path):
    # R4#26：不许 importorskip——回放出图是所有 e2e 的测量仪器，仪器缺席
    # 必须红而不是静默 skip（skip 在全绿的滚动条里没人看，缺了几个月都不知道）。
    # Pillow 已列进 pyproject 的 dev 依赖。
    try:
        import PIL  # noqa: F401
    except ImportError:
        pytest.fail("Pillow 缺失：pai-replay 出不了图，e2e 的测量仪器缺席。"
                    "装上：pip install pillow（已在 pyproject [dev] 里）")
    path = tmp_path / "r.jsonl"
    rec = Recorder(str(path), size=lambda: (30, 5), now=lambda: 0.0)
    rec.wrap(lambda _: None)("\x1b[36m› 中文 and ascii\x1b[0m\r\n● 答案")
    rec.close()
    out = tmp_path / "shot.png"
    to_png(replay(load(str(path))), str(out))
    assert out.exists() and out.stat().st_size > 1000


def test_width_changes_are_detected_and_only_the_last_segment_is_replayed():
    """dock 的重绘是**相对光标移动**，行数按当时的宽度算。

    拿 100 列的屏幕去放 50 列时写的帧，行数对不上、上移被夹到第 0 行，
    会把顶部内容覆盖掉——**图上像是 pai 画花了，其实是回放放错了**。
    """
    from pai.tui.replay import width_segments

    records = [{"cols": 100, "rows": 24, "data": "早期内容\r\n"},
               {"cols": 50, "rows": 24, "data": "窄的时候\r\n"},
               {"cols": 100, "rows": 24, "data": "最后一段"}]
    assert width_segments(records) == [(0, 100), (1, 50), (2, 100)]
    assert "最后一段" in to_text(replay(records))
    assert "早期内容" not in to_text(replay(records))
    assert "早期内容" in to_text(replay(records, whole=True))
