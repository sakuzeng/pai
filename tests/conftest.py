import os

import pytest
from dotenv import load_dotenv

# 让 .env 里的 key 对测试可见（否则只认 shell 导出的环境变量）
load_dotenv()


def _has_real_key() -> bool:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    return bool(key) and not key.startswith("sk-在这里")


def _llm_tests_opted_in() -> bool:
    return os.environ.get("PAI_RUN_LLM_TESTS", "") not in ("", "0", "false", "False")


def pytest_collection_modifyitems(config, items):
    """llm 标记的测试要真花钱，必须**显式选择**才跑——光有 key 不够。

    原实现是「有 key 就自动跑」，结果是任何配好 .env 的人跑 pytest 都会静默产生 API 费用
    （外部评审时评审者本人就中招了）。改为双重条件：有 key **且** PAI_RUN_LLM_TESTS=1。
    """
    if _has_real_key() and _llm_tests_opted_in():
        return
    reason = (
        "跳过真实 LLM 测试（会产生 API 费用）。需要时：PAI_RUN_LLM_TESTS=1 pytest"
        if _has_real_key()
        else "无 DEEPSEEK_API_KEY，跳过依赖真实 LLM 的测试"
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)


# ---- 2026-08-10 追加：任何测试都不许碰真实的 $HOME ----
#
# 起因（用户发现）：tests/test_interactive.py 里 20 处 `_run(...)` 没传 history_path，
# 于是 REPL 的历史全部写进了用户真实的 ~/.pai/history/<cwd 哈希>——687 行里只有 3 行
# 是用户自己的。这类污染不会让任何测试变红。
#
# 为什么用 autouse 兜底而不是「逐个测试传参」：20 个调用点意味着第 21 个还会忘。
# 把「碰不到真实 home」变成**结构上做不到**，比依赖记性可靠。

# ---- 2026-08-18 追加：挂死必须变红（R4#T6）----
#
# 机制与理由都在 tests/pai_test_timeout.py（那里也是子进程验证时 `-p` 加载的同一份）。
# 这里只是把 autouse fixture 拉进 conftest 命名空间，让整套默认都装上。
# 不用 `pytest_plugins = [...]`：pytest 8 起非顶层 conftest 里写它是错误。
from pai_test_timeout import hang_becomes_red    # noqa: F401  autouse fixture


import site
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def isolate_home(tmp_path_factory, monkeypatch):
    from pai.modes import interactive

    # 用 tmp_path_factory 另开一个目录，**不能**放在 tmp_path 里——
    # 好几个测试在断言「tmp_path 下只有我写的那个文件」，塞个 fake-home 进去会误伤
    fake_home = tmp_path_factory.mktemp("fake-home")
    # Path.home() 在运行期读 $HOME（memory_dir / ask 等都走它）
    monkeypatch.setenv("HOME", str(fake_home))
    # 但 HISTORY_BASE 是**导入期**求值的模块常量，改 $HOME 追不回来，必须单独打
    monkeypatch.setattr(interactive, "HISTORY_BASE", fake_home / ".pai" / "history")
    # 连锁反应：**用户 site 目录由 $HOME 推导**，换了 HOME 之后子进程
    # （viz 的 `python -m pai.viz.collect`）既 import 不到 pai，也 import 不到
    # dotenv/openai 这些第三方包。把 src 与**真实的** user-site 一并交给 PYTHONPATH。
    # site.getusersitepackages() 在 pytest 启动时就算好了，此刻拿到的仍是真实路径。
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(SRC), site.getusersitepackages()]))
    return fake_home
