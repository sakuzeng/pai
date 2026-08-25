"""PendingMessageQueue（feature 05 task 2，feature 18 T1 加谓词）。

语义抄 pi 的 agent.ts:123（drain 分 all/single 两模式），代码独立写。
两种模式不是凑数：注入用 all 一次全灌（用户连打三句都是同一个转向意图，
且 CC 两个 drain 点实测都是批量）；取命令用 single 一条一条来
（照 CC `queueProcessor.ts` 对 slash/bash 逐条处理，为的是错误隔离与退码）。

**谓词（feature 18 问 7「跟 CC 一致」）**：pai 只有一条消息队列，
`/`、`!` 命令与普通消息混住在里面。注入时必须把命令**滤掉且留在队列里**——
它们要等本轮结束交给客户端执行，绝不能当文本发给模型。
对应 CC 的 `dequeueAllMatching(predicate)` 与 `getCommandsByMaxPriority` + `remove`。
"""
import pytest

from pai.core.queue import PendingMessageQueue


def _msg(text):
    return {"role": "user", "content": text}


def test_drain_all_takes_everything_and_empties():
    q = PendingMessageQueue("all")
    q.enqueue(_msg("a"))
    q.enqueue(_msg("b"))
    assert q.drain() == [_msg("a"), _msg("b")]
    assert q.has_items() is False
    assert q.drain() == []


def test_drain_single_takes_one_in_fifo_order():
    q = PendingMessageQueue("single")
    for text in ("a", "b", "c"):
        q.enqueue(_msg(text))
    assert q.drain() == [_msg("a")]
    assert q.drain() == [_msg("b")]
    assert q.has_items() is True
    assert q.drain() == [_msg("c")]
    assert q.has_items() is False


def test_drain_empty_returns_empty_list():
    # 空队列返回 [] 而不是抛/返回 None：调用点是 loop 的热路径，不该到处判空
    assert PendingMessageQueue("all").drain() == []
    assert PendingMessageQueue("single").drain() == []


def test_clear_discards_pending():
    q = PendingMessageQueue("all")
    q.enqueue(_msg("a"))
    q.clear()
    assert q.has_items() is False
    assert q.drain() == []


def test_has_items_reflects_state():
    q = PendingMessageQueue("single")
    assert q.has_items() is False
    q.enqueue(_msg("a"))
    assert q.has_items() is True


def test_drain_result_is_a_copy_not_the_internal_list():
    # 返回内部列表的引用 = 调用方改一下就把队列改了（FakeClient 存引用那个坑的同款）
    q = PendingMessageQueue("all")
    q.enqueue(_msg("a"))
    drained = q.drain()
    drained.append(_msg("b"))
    q.enqueue(_msg("c"))
    assert q.drain() == [_msg("c")]


def test_unknown_mode_is_rejected_at_construction():
    # 静默降级成某个模式 = 行为随手一改就变，报错要指向真因（对齐 @tool 的做法）
    with pytest.raises(ValueError):
        PendingMessageQueue("both")


# --- 谓词（feature 18 T1）------------------------------------------------

def _for_model(m):
    """注入侧的谓词：`/`、`!` 开头的是给客户端执行的命令，不进模型。"""
    return not str(m.get("content", "")).lstrip().startswith(("/", "!"))


def test_drain_all_with_predicate_leaves_unmatched_in_place():
    # 这条是「命令留到本轮结束」的落点：滤掉的**不是丢掉**，是留在队列里等 T4 取。
    q = PendingMessageQueue("all")
    for text in ("改用 rg", "/help", "再看看 tests/"):
        q.enqueue(_msg(text))
    assert q.drain(where=_for_model) == [_msg("改用 rg"), _msg("再看看 tests/")]
    assert q.has_items() is True
    assert q.drain() == [_msg("/help")]          # 顺序不变，命令还在


def test_drain_all_with_predicate_matching_nothing_keeps_queue_intact():
    q = PendingMessageQueue("all")
    q.enqueue(_msg("/help"))
    q.enqueue(_msg("!ls"))
    assert q.drain(where=_for_model) == []
    assert q.drain() == [_msg("/help"), _msg("!ls")]     # 一条不少、原序


def test_drain_single_with_predicate_takes_first_match_not_first_item():
    # 队首不匹配时不能返回 []（那样命令会永远堵住后面的消息），要往后找第一条匹配的
    q = PendingMessageQueue("single")
    q.enqueue(_msg("/help"))
    q.enqueue(_msg("改用 rg"))
    q.enqueue(_msg("再看看 tests/"))
    assert q.drain(where=_for_model) == [_msg("改用 rg")]
    assert q.drain(where=_for_model) == [_msg("再看看 tests/")]
    assert q.drain(where=_for_model) == []
    assert q.drain() == [_msg("/help")]          # 前面那条命令原地不动


def test_drain_empty_with_predicate_returns_empty_list():
    assert PendingMessageQueue("all").drain(where=_for_model) == []
    assert PendingMessageQueue("single").drain(where=_for_model) == []


def test_drain_without_predicate_is_unchanged():
    # 回归：不传谓词时行为与 feature 05 逐字一致（命令也照样被取走）
    q = PendingMessageQueue("all")
    q.enqueue(_msg("/help"))
    q.enqueue(_msg("改用 rg"))
    assert q.drain() == [_msg("/help"), _msg("改用 rg")]
    assert q.has_items() is False


def test_take_first_is_fifo_regardless_of_mode_or_kind():
    """本轮结束后的处理要**严格按用户敲的顺序**逐条走（feature 18 T4）：
    消息起新一轮、命令交客户端执行，混排时不许重排。"""
    for mode in ("all", "single"):
        q = PendingMessageQueue(mode)
        for text in ("改用 rg", "/help", "再看 tests/"):
            q.enqueue(_msg(text))
        assert q.take_first() == _msg("改用 rg")
        assert q.take_first() == _msg("/help")
        assert q.take_first() == _msg("再看 tests/")
        assert q.take_first() is None
        assert q.has_items() is False


def test_take_first_on_empty_returns_none_not_raises():
    assert PendingMessageQueue("all").take_first() is None


def test_drain_with_predicate_result_is_a_copy():
    q = PendingMessageQueue("all")
    q.enqueue(_msg("改用 rg"))
    q.enqueue(_msg("/help"))
    drained = q.drain(where=_for_model)
    drained.append(_msg("污染"))
    assert q.drain() == [_msg("/help")]


# ---- __len__：队列长度是公开面（12 复盘质疑一） ----


def test_queue_reports_its_own_length():
    """`len(queue)` 而不是 `len(queue._messages)`（12 复盘质疑一）。

    当时的理由「不给 05 交付的类加公开面」站不住：读私有表比加一个 `__len__`
    更耦合——它把「内部用 list 存」这件事泄漏进了 modes 层，
    换成 deque 或双表实现时 modes 会当场坏。
    """
    q = PendingMessageQueue("all")
    assert len(q) == 0
    q.enqueue({"role": "user", "content": "a"})
    q.enqueue({"role": "user", "content": "b"})
    assert len(q) == 2
    q.drain()
    assert len(q) == 0


def test_len_tracks_partial_drain_and_take_first():
    """留在队列里的命令要照样计数——dock 上「排队 N 条」说的就是它们。"""
    q = PendingMessageQueue("all")
    q.enqueue({"role": "user", "content": "说点什么"})
    q.enqueue({"role": "user", "content": "/help"})
    q.drain(where=lambda m: not m["content"].startswith("/"))
    assert len(q) == 1
    q.take_first()
    assert len(q) == 0
