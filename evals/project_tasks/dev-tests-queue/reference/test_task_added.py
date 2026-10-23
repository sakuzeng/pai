from pai.core.queue import PendingMessageQueue
import pytest

@pytest.mark.parametrize('mode', ['all', 'single'])
def test_matching_messages_are_removed_without_dropping_unmatched(mode: str) -> None:
    queue = PendingMessageQueue(mode)
    values = [{'content': text} for text in ('/help', 'one', '!pwd', 'two')]
    for value in values:
        queue.enqueue(value)
    match = lambda item: not item['content'].startswith(('/', '!'))
    if mode == 'all':
        assert queue.drain(match) == [values[1], values[3]]
    else:
        assert queue.drain(match) == [values[1]]
        assert queue.drain(match) == [values[3]]
    assert queue.drain(match) == []
    assert queue.take_first() == values[0]
    assert queue.take_first() == values[2]
    assert queue.take_first() is None

def test_all_keeps_fifo_and_returns_independent_result() -> None:
    queue = PendingMessageQueue('all')
    queue.enqueue({'content': 'one'})
    queue.enqueue({'content': 'two'})
    result = queue.drain()
    assert [v['content'] for v in result] == ['one', 'two']
    result.append({'content': 'unrelated'})
    assert queue.drain() == []

@pytest.mark.parametrize('mode', ['all', 'single'])
def test_empty_queue(mode: str) -> None:
    queue = PendingMessageQueue(mode)
    assert queue.drain() == []
    assert queue.drain(lambda item: True) == []
