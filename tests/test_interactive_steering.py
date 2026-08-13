"""干活期间打的字进 steering 队列（feature 18 T3）。

拍板结论（[features/18 spec](../docs/dev/features/18-20260813-steering-input/spec.md)）：
- 问 1：默认档改成 steering——人说话默认优先，本轮就注入，不再等本轮结束；
- 问 2：followUp 队列删掉，pai 只剩一条消息队列；
- 问 5/7：`/`、`!` 命令**留在同一条队列里**，注入时靠谓词滤掉，
  等本轮结束交给客户端逐条执行——绝不能当文本发给模型。
"""
from pai.core.queue import PendingMessageQueue
from pai.modes.interactive import (
    MAX_QUEUE_ROUNDS,
    _for_model,
    _process_queue_after_turn,
    _steering_source,
)


def _msg(text):
    return {"role": "user", "content": text}


class TestInjectionPredicate:
    """谓词是「命令不进模型」这条硬约束的唯一守门人，单独钉死。"""

    def test_plain_text_goes_to_the_model(self):
        assert _for_model(_msg("改用 rg 搜")) is True

    def test_slash_command_does_not(self):
        # CC 明文：slash 命令 must not be sent to the model as text
        assert _for_model(_msg("/help")) is False

    def test_bang_command_does_not(self):
        # `!` 同样是给客户端执行的（CC 那边 bash 模式也被排除在中途注入外）
        assert _for_model(_msg("!ls -la")) is False

    def test_leading_whitespace_does_not_smuggle_a_command_through(self):
        # 用户敲空格再敲 `/` 是常事；按裸 startswith 判就漏了
        assert _for_model(_msg("  /help")) is False

    def test_slash_inside_the_sentence_is_just_text(self):
        assert _for_model(_msg("看下 src/pai/core/loop.py")) is True

    def test_missing_or_empty_content_is_not_a_command(self):
        assert _for_model({"role": "user"}) is True
        assert _for_model(_msg("")) is True


class TestQueueWiring:
    """队列本身：命令与消息混住，注入只取消息、命令留着。"""

    def test_injection_takes_messages_and_leaves_commands(self):
        from pai.core.queue import PendingMessageQueue

        q = PendingMessageQueue("all")
        for text in ("改用 rg", "/help", "再看 tests/"):
            q.enqueue(_msg(text))

        assert q.drain(where=_for_model) == [_msg("改用 rg"), _msg("再看 tests/")]
        assert q.drain() == [_msg("/help")], "命令必须留到本轮结束，不能被注入吃掉"

    def test_the_queue_is_all_mode(self):
        """问 3 拍板：注入用 all（照 CC，两个 drain 点都是批量、每条各自一条消息）。

        这条钉的是**装配**而不是队列本身——`interactive` 建队列时选错模式，
        单测里的队列再对也没用。
        """
        import inspect

        from pai.modes import interactive

        src = inspect.getsource(interactive.run_interactive)
        assert 'PendingMessageQueue("all")' in src
        assert "PendingMessageQueue(\"single\")" not in src


class TestDockCountFollowsTheDrain:
    """补 2：dock 的待决数在**中途 drain 之后**就得减，不是等本轮结束才跳回真值。

    原缺陷：`set_queued` 只在「干活期间 enqueue 时」与「本轮结束的 finally」被调用，
    `run_agent` 内部 drain 掉队列后没有任何人更新——界面一直显示 drain 前的旧数字。
    """

    def test_reported_count_is_the_real_remainder_not_a_stale_snapshot(self):
        # 快照式断言：2 条消息 + 1 条命令，注入取走 2 条消息后应报 **1**（不是 3，也不是 0）
        q = PendingMessageQueue("all")
        for text in ("改用 rg", "/help", "再看 tests/"):
            q.enqueue(_msg(text))
        reported = []

        take = _steering_source(q, after_drain=reported.append)
        drained = take()

        assert drained == [_msg("改用 rg"), _msg("再看 tests/")]
        assert reported == [1], "命令还在队列里，报 0 就是骗人；报 3 是没更新"

    def test_reports_zero_when_the_queue_empties(self):
        q = PendingMessageQueue("all")
        q.enqueue(_msg("改用 rg"))
        reported = []
        _steering_source(q, after_drain=reported.append)()
        assert reported == [0]

    def test_reports_even_when_nothing_was_drained(self):
        """一条命令都取不走时也要报——否则 enqueue 之后那个数字永远停在旧值。"""
        q = PendingMessageQueue("all")
        q.enqueue(_msg("/help"))
        reported = []
        assert _steering_source(q, after_drain=reported.append)() == []
        assert reported == [1]

    def test_works_without_a_callback(self):
        """非 TUI 路径没有 dock，回调是可选的。"""
        q = PendingMessageQueue("all")
        q.enqueue(_msg("改用 rg"))
        assert _steering_source(q)() == [_msg("改用 rg")]


class TestAfterTurnProcessing:
    """T4：本轮结束后队列里剩的东西必须有人处理，否则就是换个地方丢消息。

    followUp 删掉之后没人兜「最后一次 drain 之后才敲进来的字」了——
    `AgentEnd` 事件也会触发一次 poll，窗口小但真实存在。
    """

    def _spy(self):
        return {"turns": [], "commands": []}

    def _run(self, q, spy, **kw):
        return _process_queue_after_turn(
            q,
            run_turn=lambda text: spy["turns"].append(text),
            dispatch=lambda text: spy["commands"].append(text),
            **kw,
        )

    def test_leftover_command_is_executed_not_sent_to_the_model(self):
        q, spy = PendingMessageQueue("all"), self._spy()
        q.enqueue(_msg("/help"))
        assert self._run(q, spy) == 1
        assert spy["commands"] == ["/help"]
        assert spy["turns"] == [], "命令绝不能起新一轮（那等于当文本发给模型）"
        assert q.has_items() is False

    def test_leftover_message_starts_a_new_turn(self):
        q, spy = PendingMessageQueue("all"), self._spy()
        q.enqueue(_msg("再补一句"))
        assert self._run(q, spy) == 1
        assert spy["turns"] == ["再补一句"]
        assert spy["commands"] == []

    def test_mixed_items_keep_the_order_the_user_typed_them(self):
        # 不许把命令攒到一起先跑完——用户敲的顺序就是他要的顺序
        q, spy = PendingMessageQueue("all"), self._spy()
        for text in ("/help", "再补一句", "!ls"):
            q.enqueue(_msg(text))
        assert self._run(q, spy) == 3
        assert spy["commands"] == ["/help", "!ls"]
        assert spy["turns"] == ["再补一句"]

    def test_empty_queue_does_nothing(self):
        q, spy = PendingMessageQueue("all"), self._spy()
        assert self._run(q, spy) == 0
        assert spy == {"turns": [], "commands": []}

    def test_the_round_bound_stops_a_runaway_and_leaves_the_rest_in_the_queue(self):
        """一轮又往队列里塞（真跑时是用户一直在打字）不能转成死循环。

        剩下的**留在队列里**而不是丢掉：下一轮结束时还会再处理一次。
        """
        q, spy = PendingMessageQueue("all"), self._spy()
        for i in range(5):
            q.enqueue(_msg(f"第{i}句"))
        assert self._run(q, spy, max_rounds=2) == 2
        assert spy["turns"] == ["第0句", "第1句"]
        assert q.has_items() is True

    def test_the_default_bound_is_a_real_number(self):
        assert isinstance(MAX_QUEUE_ROUNDS, int) and MAX_QUEUE_ROUNDS > 0

    def test_a_command_that_asks_to_exit_stops_the_processing(self):
        """`_dispatch_command` 返回 True = 该退出 REPL（`/exit`）。

        丢掉这个返回值的话，干活期间敲的 `/exit` 会被执行、然后**继续处理队列**——
        用户说了退出，pai 却又起了一轮新的对话。剩下的留在队列里由调用方收尾。
        """
        q, spy = PendingMessageQueue("all"), self._spy()
        for text in ("/exit", "再补一句"):
            q.enqueue(_msg(text))

        rounds = _process_queue_after_turn(
            q,
            run_turn=lambda text: spy["turns"].append(text),
            dispatch=lambda text: spy["commands"].append(text) or text == "/exit",
        )

        assert rounds == 1
        assert spy["commands"] == ["/exit"]
        assert spy["turns"] == [], "说了退出就不该再起新一轮"
        assert q.has_items() is True


class TestFollowUpIsGone:
    """问 2：followUp 删干净了——留半截比不删更糟（两条路各说各话）。"""

    def test_no_follow_up_symbol_left_in_the_module(self):
        import inspect

        from pai.modes import interactive

        src = inspect.getsource(interactive)
        assert "follow_up" not in src
        assert "get_follow_up_messages" not in src

    def test_run_agent_no_longer_accepts_it(self):
        import inspect

        from pai.core.loop import run_agent

        assert "get_follow_up_messages" not in inspect.signature(run_agent).parameters
