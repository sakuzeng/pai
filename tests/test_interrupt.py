"""中断标志（feature 05 task 3）。

选进程级单例而非构造注入，是因为 @tool 注册的是模块级函数：给 bash 加一个
flag 参数会污染发给模型的 schema（模型会看见一个它不该填的参数）。
代价是全局状态——所以 current() 必须永远返回一个可用对象，且测试要能干净复位。
"""
from pai.core import interrupt


def test_flag_set_is_set_clear_roundtrip():
    flag = interrupt.InterruptFlag()
    assert flag.is_set() is False
    flag.set()
    assert flag.is_set() is True
    flag.clear()
    assert flag.is_set() is False


def test_current_is_process_singleton():
    original = interrupt.current()
    try:
        flag = interrupt.InterruptFlag()
        interrupt.set_current(flag)
        assert interrupt.current() is flag
    finally:
        interrupt.set_current(original)


def test_current_defaults_to_unset_flag():
    # 不能返回 None：那样每个工具里都要写 `f = current(); if f and f.is_set()`
    assert interrupt.current().is_set() is False


def test_set_current_none_restores_a_usable_default():
    original = interrupt.current()
    try:
        interrupt.set_current(interrupt.InterruptFlag())
        interrupt.current().set()
        interrupt.set_current(None)          # 卸载注入
        assert interrupt.current().is_set() is False
    finally:
        interrupt.set_current(original)
