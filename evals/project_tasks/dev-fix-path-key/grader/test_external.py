from pai.core.tools import MatchContext
from pai.core.tools.fs import target_path
import os
import pytest

@pytest.mark.parametrize('args', [{'path': 'secret.txt', 'content': 'ordinary text'}, {'content': 'ordinary text', 'path': 'secret.txt'}, {'new': 'replacement', 'old': 'original', 'path': 'secret.txt'}])
def test_path_uses_named_argument(args: dict) -> None:
    assert target_path(args, MatchContext(cwd='/project')) == '/project/secret.txt'

@pytest.mark.parametrize('args', [{'content': 'secret.txt'}, {'content': 'secret.txt', 'path': ''}])
def test_empty_or_missing_path_does_not_use_content(args: dict) -> None:
    assert target_path(args, MatchContext(cwd='/project')) == ''

def test_absolute_path_is_not_rebased() -> None:
    assert target_path({'content': 'x', 'path': '/other/file'}, MatchContext(cwd='/project')) == '/other/file'
