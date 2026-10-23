import os
import sys

import pytest

# 让测试能找到仓库根目录下的 ranges.py（不依赖 pytest 的 sys.path 行为）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ranges import clip


def test_value_inside_range_is_returned_unchanged():
    assert clip(5, 0, 10) == 5


def test_value_below_lower_returns_lower():
    assert clip(-3, 0, 10) == 0


def test_value_above_upper_returns_upper():
    assert clip(42, 0, 10) == 10


def test_value_equal_to_lower_is_returned_unchanged():
    assert clip(0, 0, 10) == 0


def test_value_equal_to_upper_is_returned_unchanged():
    assert clip(10, 0, 10) == 10


def test_works_with_negative_bounds():
    assert clip(-10, -5, -1) == -5
    assert clip(0, -5, -1) == -1
    assert clip(-3, -5, -1) == -3


def test_degenerate_range_single_value():
    assert clip(7, 3, 3) == 3
    assert clip(1, 3, 3) == 3
    assert clip(9, 3, 3) == 3


def test_lower_greater_than_upper_raises_value_error():
    with pytest.raises(ValueError):
        clip(1, 10, 0)


@pytest.mark.parametrize("value", [-100, 0, 5, 100])
def test_invalid_range_raises_regardless_of_value(value):
    with pytest.raises(ValueError):
        clip(value, 10, 0)
