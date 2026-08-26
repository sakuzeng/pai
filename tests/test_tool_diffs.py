"""编辑结果里的 diff（feature 43 Task 3）。

需求原话是「改了什么你看不见」。落点是工具返回值——TUI 那边
`app._tool_entry` 本来就会把多行结果做成可展开条目（^O），
`app._display_result` 也已经分好了「模型拿原文 / 终端拿 sanitize 过的那份」，
所以给返回值加 diff 等于同时喂饱了模型和终端（拍板问 2·A）。

诚实边界：REPL / once 那条路是残的——`events.render_text` 的契约是
「返回一行」（`modes/echo.py` 的注释明写着它依赖这条），且会把换行压成空格
再截到 200 字符。本轮不动那条契约（拍板问 2 的候选 D 被否），如实登记 TODO。
"""
import pytest

from pai.core.tools.diffs import MAX_DIFF_LINES, render_change


# ---- 纯函数：怎么渲染 ----


def test_a_small_change_shows_a_unified_diff():
    out = render_change("a\nb\nc\n", "a\nB\nc\n", path="x.py")
    assert "-b" in out and "+B" in out
    assert "@@" in out, "没有 hunk 头，看不出改在第几行"


def test_the_empty_file_headers_are_stripped():
    """`difflib.unified_diff` 不给文件名时会吐两行 `--- ` / `+++ ` 纯噪音。

    这条是真跑冒烟抓到的：离线测试当时全绿，因为没有一条断言在看开头两行。
    只剥开头——正文里以 `---` 打头的代码行（yaml 分隔符、Markdown 分隔线）
    不该被误当成文件头删掉，下面那条钉这一半。
    """
    out = render_change("a\nb\n", "a\nB\n", path="x.py")
    assert not out.startswith("---"), f"文件头没剥干净：{out[:40]!r}"
    assert not out.startswith("+++")
    assert "@@" in out


def test_a_content_line_starting_with_dashes_survives():
    """反向守卫：剥文件头不许把正文里的 `---` 一起剥掉。

    方向要挑对（第一版挑错了，注入反证没红才发现）：**新增**的 `---` 在 diff 里是
    `+---`，全文过滤 `startswith("---")` 碰不到它；真正会被误删的是**被删掉**的
    那一行——`-` 加上 `---` 正好是 `----`，`startswith("---")` 当场命中。
    `++` 那半同理：新增时变成 `+++`。
    """
    removed = render_change("---\nyaml: 1\n", "yaml: 2\n", path="x.yml")
    assert "----" in removed, f"被删掉的 --- 行被当成文件头删了：{removed!r}"

    added = render_change("x\n", "++\n", path="x.txt")
    assert "+++" in added, f"新增的 ++ 行被当成文件头删了：{added!r}"


def test_an_unchanged_write_says_so_instead_of_showing_nothing():
    """内容没变与「diff 没渲染出来」在模型眼里必须分得开。"""
    out = render_change("same\n", "same\n", path="x.py")
    assert out
    assert "无变化" in out


def test_a_new_file_reports_lines_instead_of_pasting_the_body_twice():
    """新建文件不产 diff：对空文件做 diff 就是把模型刚写的正文再贴一遍。"""
    out = render_change(None, "one\ntwo\nthree\n", path="x.py")
    assert "新建" in out
    assert "3" in out
    assert "+one" not in out, "把正文又贴了一遍"


def test_a_huge_change_reports_stats_and_points_somewhere(tmp_path):
    """超过行数上限就不贴，但必须说清为什么不贴、去哪看（同 R#17 那条规矩）。"""
    before = "".join(f"line {i}\n" for i in range(400))
    after = "".join(f"changed {i}\n" for i in range(400))
    out = render_change(before, after, path="x.py")

    assert "@@" not in out, "超了还在贴 diff"
    assert "400" in out, "没报出改动量"
    assert str(MAX_DIFF_LINES) in out, "没说清上限是多少"
    assert "git_read" in out, "没告诉去哪看具体改动"


def test_the_stats_count_added_and_removed_separately():
    """`+X / -Y` 两个数要各自算准：只报「改了 N 行」分不出是加是删。"""
    before = "keep\ngone1\ngone2\n"
    after = "keep\nnew1\nnew2\nnew3\n"
    out = render_change(before, after, path="x.py", max_lines=1)
    assert "+3" in out and "-2" in out


def test_binary_or_undecodable_before_is_not_a_crash(tmp_path):
    """错误路径：读不到旧内容时不许炸，如实说 diff 出不来。"""
    out = render_change(None, "x\n", path="x.py", before_unreadable=True)
    assert "diff" in out or "对比" in out
    assert "+x" not in out


# ---- 接到两个写工具上 ----


def test_edit_file_returns_a_diff(tmp_path):
    from pai.core.tools.fs import edit_file

    p = tmp_path / "a.py"
    p.write_text("def f():\n    return None\n", encoding="utf-8")
    out = edit_file(path=str(p), old="return None", new="return 1")

    assert "完成 1 处替换" in out          # 原来那句话不许丢
    assert "-    return None" in out
    assert "+    return 1" in out


def test_write_file_returns_a_diff_when_overwriting(tmp_path):
    from pai.core.tools.fs import write_file

    p = tmp_path / "a.py"
    p.write_text("old\n", encoding="utf-8")
    out = write_file(path=str(p), content="new\n")

    assert "已写入" in out
    assert "-old" in out and "+new" in out


def test_write_file_on_a_new_file_does_not_paste_the_body_twice(tmp_path):
    from pai.core.tools.fs import write_file

    p = tmp_path / "new.py"
    out = write_file(path=str(p), content="one\ntwo\n")

    assert "已写入" in out
    assert "新建" in out
    assert "+one" not in out


def test_an_overwrite_with_identical_content_says_no_change(tmp_path):
    """写了但内容一样：不该假装改了什么。"""
    from pai.core.tools.fs import write_file

    p = tmp_path / "a.py"
    p.write_text("same\n", encoding="utf-8")
    out = write_file(path=str(p), content="same\n")
    assert "无变化" in out


def test_write_file_over_a_binary_file_still_writes(tmp_path):
    """错误路径：旧内容读不出来（二进制）时，写照样要成功，只是没有 diff。"""
    from pai.core.tools.fs import write_file

    p = tmp_path / "blob.bin"
    p.write_bytes(b"\xff\xfe\x00binary")
    out = write_file(path=str(p), content="现在是文本了\n")

    assert p.read_text(encoding="utf-8") == "现在是文本了\n", "没写进去"
    assert "已写入" in out
    assert "+现在是文本了" not in out


def test_the_diff_is_a_multiline_result_so_the_tui_can_fold_it(tmp_path):
    """接线断言：TUI 靠「结果不止一行」来决定要不要做成可展开条目。

    这条钉的是**两边的连接处**——diff 渲染得再好，如果结果被压成一行，
    TUI 那套现成机制就用不上（`app._hidden_rows` 数的正是第一行之后的非空行）。
    """
    from pai.core.events import ToolEnd
    from pai.core.tools.fs import edit_file
    from pai.tui.app import _hidden_rows

    p = tmp_path / "a.py"
    p.write_text("def f():\n    return None\n", encoding="utf-8")
    result = edit_file(path=str(p), old="return None", new="return 1")

    event = ToolEnd(tool_call_id="1", name="edit_file",
                    args={"path": str(p)}, result=result)
    assert _hidden_rows(event) > 0, "结果只有一行，TUI 的折叠/展开用不上"
