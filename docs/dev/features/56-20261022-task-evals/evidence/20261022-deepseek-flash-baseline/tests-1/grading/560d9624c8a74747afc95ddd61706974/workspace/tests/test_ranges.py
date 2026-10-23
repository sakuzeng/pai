import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ranges import clip


class TestClipNormalValues:
    """lower <= upper 时的普通取值。"""

    @pytest.mark.parametrize(
        "value, lower, upper, expected",
        [
            (5, 0, 10, 5),      # 区间内
            (0, -10, 10, 0),    # 区间内，含 0
            (-3, -10, 10, -3),  # 区间内，负数
            (7, 1, 100, 7),     # 区间内，非对称区间
            (2.5, 0.0, 10.0, 2.5),  # 浮点
        ],
    )
    def test_inside_range_returns_value(self, value, lower, upper, expected):
        assert clip(value, lower, upper) == expected

    @pytest.mark.parametrize(
        "value, lower, upper, expected",
        [
            (-5, 0, 10, 0),      # 低于下界
            (-1, 0, 10, 0),      # 刚好低于下界
            (11, 0, 10, 10),     # 高于上界
            (100, -10, -5, -5),  # 区间为负数时高于上界
            (-11, -10, -5, -10),  # 区间为负数时低于下界
            (2.0, 3.0, 5.0, 3.0),  # 浮点低于下界
        ],
    )
    def test_outside_range_is_clamped(self, value, lower, upper, expected):
        assert clip(value, lower, upper) == expected


class TestClipBoundaries:
    """两端边界值原样返回。"""

    @pytest.mark.parametrize(
        "value, lower, upper",
        [
            (0, 0, 10),      # value == lower
            (10, 0, 10),     # value == upper
            (-10, -10, 5),   # value == lower，负数
            (5, -10, 5),     # value == upper，负数下界
            (3.5, 3.5, 8.0),  # value == lower，浮点
            (8.0, 3.5, 8.0),  # value == upper，浮点
        ],
    )
    def test_value_on_boundary_returned_unchanged(self, value, lower, upper):
        assert clip(value, lower, upper) == value

    def test_lower_equals_upper_returns_that_value(self):
        # 退化区间：lower == upper，任何输入都被夹到该值
        assert clip(3, 5, 5) == 5
        assert clip(5, 5, 5) == 5
        assert clip(7, 5, 5) == 5

    def test_extreme_int_values(self):
        big = 10**18
        assert clip(-big, -big, big) == -big
        assert clip(big, -big, big) == big
        assert clip(big + 1, -big, big) == big


class TestClipInvalidRange:
    """lower > upper 抛 ValueError。"""

    @pytest.mark.parametrize(
        "value, lower, upper",
        [
            (5, 10, 0),
            (0, 1, -1),
            (-5, -1, -10),
            (5.5, 10.0, 0.0),
        ],
    )
    def test_inverted_range_raises_value_error(self, value, lower, upper):
        with pytest.raises(ValueError):
            clip(value, lower, upper)

    def test_inverted_range_raises_even_if_value_in_between(self):
        with pytest.raises(ValueError):
            clip(5, 6, 4)

    def test_inverted_range_raises_regardless_of_order_of_check(self):
        # 即使 value 看起来"合法"也必须先校验区间
        for value in (-100, 0, 100):
            with pytest.raises(ValueError):
                clip(value, 10, 0)
