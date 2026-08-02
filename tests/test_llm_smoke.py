"""真实 LLM 冒烟测试：整条链路（真模型 + 真工具）跑通一次最小任务。

默认**不跑**——需同时满足：配了有效 DEEPSEEK_API_KEY，且显式 PAI_RUN_LLM_TESTS=1（见 conftest.py）。
花钱的副作用不能是默认行为。跑它：./test.sh --llm
"""

import pytest

from pai.config import make_client, model_name
from pai.core.loop import run_agent
from pai.core.tools import get_tools


@pytest.mark.llm
def test_real_model_writes_and_reads_file(tmp_path):
    target = tmp_path / "smoke.txt"
    answer = run_agent(
        f"创建文件 {target}，内容写 pai-smoke，然后读出来确认，最后简短总结。",
        client=make_client(),
        model=model_name(),
        tools=get_tools(),
        max_steps=8,
        on_event=lambda _: None,
    )
    assert target.exists(), "真实模型没有完成写文件动作"
    assert "pai-smoke" in target.read_text(encoding="utf-8")
    assert answer, "loop 未返回最终答案"
