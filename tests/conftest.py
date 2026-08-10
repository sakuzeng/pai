"""全局测试防护：**任何测试都不许碰真实的 $HOME**。

起因（2026-08-10，用户发现）：`tests/test_interactive.py` 里 20 处 `_run(...)` 没传
`history_path`，于是 REPL 的历史全部写进了用户真实的
`~/.pai/history/<cwd 哈希>`——`!sleep 300`、`问一句`、`!echo hi` 这些测试数据
混进了他自己的输入历史里。

为什么用 autouse 兜底而不是「逐个测试传参」：20 个调用点意味着第 21 个还会忘。
把「碰不到真实 home」变成**结构上做不到**，比依赖记性可靠。
"""
import os
import site
from pathlib import Path

import pytest

from pai.modes import interactive

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def isolate_home(tmp_path_factory, monkeypatch):
    # 用 tmp_path_factory 另开一个目录，**不能**放在 tmp_path 里——
    # 好几个测试在断言「tmp_path 下只有我写的那个文件」，塞个 fake-home 进去会误伤
    fake_home = tmp_path_factory.mktemp("fake-home")
    # Path.home() 在运行期读 $HOME（memory_dir / ask 等都走它）
    monkeypatch.setenv("HOME", str(fake_home))
    # 但 HISTORY_BASE 是**导入期**求值的模块常量，改 $HOME 追不回来，必须单独打
    monkeypatch.setattr(interactive, "HISTORY_BASE", fake_home / ".pai" / "history")
    # 连锁反应：**用户 site 目录由 $HOME 推导**，换了 HOME 之后子进程
    # （viz 的 `python -m pai.viz.collect`）既 import 不到 pai，也 import 不到
    # dotenv/openai 这些第三方包。把 src 与**真实的** user-site 一并交给 PYTHONPATH，
    # 让测试环境自给自足，而不是改生产代码迁就测试。
    # site.getusersitepackages() 在 pytest 启动时就算好了，此刻拿到的仍是真实路径。
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(SRC), site.getusersitepackages()]))
    return fake_home
