"""PendingMessageQueue（feature 05 task 2）。

语义抄 pi 的 agent.ts:123（drain 分 all/single 两模式），代码独立写。
两种模式不是凑数：steering 要一次全灌（用户连打三句都是同一个转向意图），
followUp 要一条一条来（每条各触发一轮，中间可能又被中断）。
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
