"""Tests for ranges.clip."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ranges import clip  # noqa: E402


# --- 普通值：位于区间内部时原样返回 ---------------------------------------
@pytest.mark.parametrize(
    "value, lower, upper",
    [
        (5, 1, 10),      # 区间正中
        (2, 1, 10),      # 靠近下界
        (9, 1, 10),      # 靠近上界
        (0, -10, 10),    # 含负数
        (-3, -10, 10),
        (7, 7, 7),       # 退化区间 [7, 7]
    ],
)
def test_clip_inside_range_returns_value(value, lower, upper):
    assert clip(value, lower, upper) == value


# --- 越界：夹到最近的边界 -------------------------------------------------
@pytest.mark.parametrize(
    "value, lower, upper, expected",
    [
        (0, 1, 10, 1),        # 低于下界
        (-100, -10, 10, -10), # 负数低于下界
        (11, 1, 10, 10),      # 高于上界
        (1_000_000, 0, 100, 100),
        (-5, 0, 0, 0),        # 退化区间越界
    ],
)
def test_clip_outside_range_is_clamped(value, lower, upper, expected):
    assert clip(value, lower, upper) == expected


# --- 两端边界：恰好等于边界时原样返回 -------------------------------------
@pytest.mark.parametrize(
    "value, lower, upper",
    [
        (1, 1, 10),      # 恰好等于下界
        (10, 1, 10),     # 恰好等于上界
        (-10, -10, 10),
        (10, -10, 10),
        (7, 7, 7),       # 上下界重合
    ],
)
def test_clip_on_boundaries_returns_value(value, lower, upper):
    assert clip(value, lower, upper) == value


# --- 非法范围：lower > upper 抛 ValueError --------------------------------
@pytest.mark.parametrize(
    "value, lower, upper",
    [
        (5, 10, 1),      # 上下界颠倒
        (0, 1, 0),       # 相差 1
        (-5, 3, 2),
        (0, -1, -2),     # 全负数颠倒
    ],
)
def test_clip_invalid_range_raises_value_error(value, lower, upper):
    with pytest.raises(ValueError):
        clip(value, lower, upper)


def test_clip_invalid_range_error_message():
    with pytest.raises(ValueError, match="invalid bounds"):
        clip(5, 10, 1)


# --- 返回值是区间内的值，且不修改输入 ------------------------------------
def test_clip_result_within_bounds():
    lower, upper = -7, 13
    for value in range(-20, 21):
        result = clip(value, lower, upper)
        assert lower <= result <= upper


def test_clip_is_idempotent():
    for value in (-50, 0, 5, 50):
        once = clip(value, 1, 10)
        assert clip(once, 1, 10) == once
