import os

import pytest


def pytest_collection_modifyitems(config, items):
    """无真实 API key 时跳过 llm 标记的测试（学 pi 的 test.sh 约定）。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key and not key.startswith("sk-在这里"):
        return
    skip = pytest.mark.skip(reason="无 DEEPSEEK_API_KEY，跳过依赖真实 LLM 的测试")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
