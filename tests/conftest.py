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
