"""feature 18 T5：干活期间打的字**本轮就进模型**——端到端的硬证据。

单测能证明「loop 在该注入的地方注入了」，证明不了「真跑时那句话确实进了请求体」。
这里断言的是**假 provider 真正收到的 messages**，走的是真进程 → 真 pty → 真 HTTP
→ 真 SSE → 真 gate → 真 TUI 那条整路（复用 feature 15 的 e2e 底座）。

三条各钉一件事：
1. 中途出口：注入的消息**紧跟在 tool 结果之后**——新起一轮的话中间会隔一条 assistant；
2. `/` 命令**永远不出现在请求体里**（CC 明文禁止的那件事，pai 此前每天在做）；
3. 结束出口（前置缺陷）：模型这轮不调工具时，排队的话照样发得出去。
"""

import time

import pytest

from fake_provider import turn
from test_e2e_tui import session  # noqa: F401 - pytest fixture 复用


def _user_texts(request):
    return [m.get("content") for m in request["messages"] if m.get("role") == "user"]


def test_typing_during_a_tool_call_is_injected_in_the_same_run(session, tmp_path):
    """中途出口：工具跑着的时候打的字，**这一轮就进模型**。

    钉的是**位置**而不只是「有没有」：注入的 user 消息必须紧跟在 tool 结果后面。
    若它是「新起一轮」发出去的，中间会隔着这一轮的 assistant 回答——
    位置断言是这两种语义在请求体上**唯一**的区别。
    """
    work = tmp_path / "work"
    work.mkdir()
    s, provider = session([
        turn(tool_calls=[{"name": "bash", "arguments": {"command": "sleep 1; echo hi"}}]),
        turn("按你说的改完了。"),
    ], cwd=str(work))

    s.send("跑个命令\r", until="是否允许")
    s.send("1", wait=0.1)              # 允许这次 → bash 开始跑，这 1 秒里没有对话框抢输入
    s.send("改用 rg 搜\r", until="按你说的改完了")

    assert len(provider.requests) >= 2, "注入之后应该又发了一次请求"
    sent = provider.requests[1]["messages"]
    assert sent[-1]["content"] == "改用 rg 搜"
    assert sent[-2]["role"] == "tool", (
        "注入的消息没有紧跟在工具结果后面——这说明它是新起一轮发的，不是本轮注入。"
        f"末尾三条：{[(m['role'], str(m.get('content'))[:20]) for m in sent[-3:]]}")


def test_a_slash_command_typed_while_busy_never_reaches_the_model(session, tmp_path):
    """`/` 命令是给**客户端**执行的，不是给模型读的（CC：not be sent to the model as text）。

    pai 在 feature 18 之前每天都在犯这条：`tui/app.py:407` 的 `and not self.busy`
    让干活期间的 `/help` 走 SUBMIT 进队列，最后原样发给模型。
    """
    work = tmp_path / "work2"
    work.mkdir()
    s, provider = session([
        turn(tool_calls=[{"name": "bash", "arguments": {"command": "sleep 1; echo hi"}}]),
        turn("命令跑完了。"),
    ], cwd=str(work))

    s.send("跑个命令\r", until="是否允许")
    s.send("1", wait=0.1)
    s.send("/help\r", until="/permissions")     # 本轮结束后作为命令执行，输出上屏

    for i, request in enumerate(provider.requests):
        for text in _user_texts(request):
            assert "/help" not in str(text), \
                f"第 {i} 次请求里混进了 `/help`——命令被当文本发给模型了"


# 逐字符停顿：给「模型正在答」造出一个真实存在的窗口。
# **这个旋钮是被一次假绿逼出来的**：没有它时假 provider 秒答，
# 下面两条测试里的第二句话根本没赶上「干活期间」，是当**新一轮**发的
# （屏幕上两个「✳ 用时」= 两次 AgentEnd），而断言照样绿。
SLOW = 0.25
SLOW_ANSWER = "第一轮答完了好的"        # 8 字 × 0.25s ≈ 2s 的窗口

def _wait_for_request(s, provider, count=1, timeout=8.0):
    """等到 pai **真的把请求发出去**为止，再往下走。

    第一行发出后必须确认这一轮已经在跑，才谈得上「干活期间打字」：
    `driver.poll()` 会把已排队的数据**一次读干净**（那是给鼠标事件合并用的），
    两行挨得太近就落进同一批 → 两个 SUBMIT 都走主循环、各起一轮，
    要测的那件事根本没发生。**第一版用固定 wait 就是这么假绿的。**

    等条件而不是等秒数，理由同 `Session.send` 的 `until`：死等既慢又脆。
    """
    end = time.time() + timeout
    while time.time() < end:
        s.drain(0.05)
        if len(provider.requests) >= count:
            return
    raise AssertionError(
        f"等了 {timeout}s，pai 也没发出第 {count} 次请求（当前 {len(provider.requests)} 次）——"
        "这一轮没跑起来，『干活期间打字』测不到")


def test_steering_survives_a_turn_with_no_tool_calls(session):
    """结束出口（前置缺陷的 e2e 版）：模型这轮**不调工具**直接作答时，排队的话不能卡死。

    改之前 `loop.py:283` 的 return 排在 steering poll 前面，这句话会永久留在队列里；
    而模型收尾那轮通常就不调工具，是最常撞上的场景。

    **「同一次 run」怎么在 e2e 层证明**：一次 run 只发一条 `AgentEnd`，
    而 `AgentEnd` 在屏幕上留一行「✳ 用时」。所以注入成功 = 屏幕上**只有一个**「用时」；
    若那句话是新起一轮发的，就会有两个。这是两种语义在界面上唯一的区别。
    """
    s, provider = session([turn(SLOW_ANSWER, delay=SLOW), turn("第二轮答完")])

    s.send("第一个问题\r", wait=0)              # 不等它跑完——模型正在逐字吐
    _wait_for_request(s, provider)
    s.send("追加的话\r", until="第二轮答完")

    assert len(provider.requests) >= 2
    assert "追加的话" in _user_texts(provider.requests[-1]), "排队的话没发出去"

    screen = s.screen_text()
    assert screen.count("用时") == 1, (
        "出现了两次「用时」= 两次 AgentEnd = 那句话是新起一轮发的，不是本轮注入。"
        f"当前屏幕：\n{screen}")


def test_the_injection_is_visible_on_screen(session):
    """补 1：注入必须看得见。

    `_extend` 原本只 append 进 messages 与 session、不发事件，于是用户插的话
    进了上下文而屏幕一无所知。CC 踩过同款（`utils/messages.ts` 的
    `case 'queued_command'`：*Previously this hardcoded isMeta:true, which hid
    user-typed messages*）——它修的是「藏起来了」，pai 补的是「压根没说」。
    """
    s, provider = session([turn(SLOW_ANSWER, delay=SLOW), turn("第二轮答完")])

    s.send("第一个问题\r", wait=0)
    _wait_for_request(s, provider)
    s.send("追加的话\r", until="第二轮答完")

    screen = s.screen_text()
    assert "已插入" in screen, (
        "注入没有在界面上留痕——用户看不出自己那句话什么时候真的生效了。"
        f"当前屏幕：\n{screen}")


@pytest.mark.parametrize("prefix", ["/", "!"])
def test_commands_typed_while_busy_run_after_the_turn(session, tmp_path, prefix):
    """命令留在队列里、本轮结束后执行（问 5 选的「排除，本轮结束后执行」）。

    这条钉的是 T4：谓词把命令滤出注入之外之后，**必须有人取走执行**，
    否则它们就永远躺在队列里（T3 交付时那个洞）。
    """
    work = tmp_path / "work3"
    work.mkdir()
    s, _ = session([turn("答完了。")], cwd=str(work))

    s.send("问一句\r", wait=0.05)
    command = "/help" if prefix == "/" else "!echo 命令跑过了"
    expect = "/permissions" if prefix == "/" else "命令跑过了"
    s.send(command + "\r", until=expect)

    assert expect in s.screen_text()
