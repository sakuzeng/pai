"""挂死必须变红（R4#T6）。

**这条测试基建守的是测试基建本身。** `./test.sh` 在 2026-08-13 与 2026-08-18
各挂死过一次（pty e2e 的父子退出竞态），两次都是人工 `kill` 才停。
危害不在慢：**它不红、也不超时**——CI 里表现成「一直在跑」，本地表现成
「我的改动把测试跑挂了」，两种都会把人引到错误的方向（2026-08-18 那次
我自己就误诊了一轮，去查一个与它无关的超时改动）。

用子进程真跑一次 pytest 来验证，而不是断言 fixture 的内部状态：
「超时真的会让这条测试变红」是个**进程级**事实，只有真跑一次才算数。
"""

import os
import subprocess
import sys
import textwrap


TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_pytest_on(tmp_path, body: str, extra=()):
    """在子进程里真跑一次 pytest。`-p` 显式加载被测插件，依赖写在明面上。"""
    test_file = tmp_path / "test_probe.py"
    test_file.write_text(textwrap.dedent(body), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=TESTS_DIR)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-p", "no:cacheprovider",
         "-p", "pai_test_timeout", "-q", *extra],
        capture_output=True, text=True, timeout=120, cwd=str(tmp_path), env=env,
    )


def test_a_hanging_test_fails_instead_of_hanging_forever(tmp_path):
    """一条永远不返回的测试，必须在预算内变成**失败**，而不是拖住整套。"""
    result = _run_pytest_on(tmp_path, '''
        import time
        import pytest

        @pytest.mark.timeout_seconds(1)
        def test_hangs_forever():
            time.sleep(300)
    ''')

    assert result.returncode != 0, "挂死的测试居然通过了"
    assert "1 failed" in result.stdout
    assert "超过 1s" in result.stdout + result.stderr


def test_a_normal_test_is_untouched(tmp_path):
    """兜底网不许误伤正常测试——它平时应当完全不存在感。"""
    result = _run_pytest_on(tmp_path, '''
        def test_quick():
            assert 1 + 1 == 2
    ''')

    assert result.returncode == 0
    assert "1 passed" in result.stdout


def test_the_repo_suite_arms_the_net_by_default(tmp_path):
    """光有机制不够——本仓库的 conftest 必须默认给每条测试都装上。"""
    conftest = os.path.join(TESTS_DIR, "conftest.py")
    with open(conftest, encoding="utf-8") as f:
        source = f.read()

    assert "hang_becomes_red" in source
