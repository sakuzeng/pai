"""真模型冒烟评测（feature 32 T5）：真 DeepSeek + 真 pai 进程跑一个
可程序判定的任务。默认不跑（./eval.sh 的 -m "not llm" 摘除）；
./eval.sh --llm 且环境里有 DEEPSEEK_API_KEY 才执行——评测的 HOME 是
隔离的（conftest），~/.pai/.env 读不到，key 必须来自环境变量。

判分照 dsh 第一原则：重读文件（外部世界），不信 agent 自述。
这是 evals/README 旧计划（execution accuracy 任务集）的第一条；
扩成任务集与成功率统计等真实使用压力（spec 非目标节）。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PAI = str(Path(sys.executable).parent / "pai")

requires_llm = pytest.mark.skipif(
    not (os.environ.get("DEEPSEEK_API_KEY")
         and os.environ.get("PAI_RUN_LLM_TESTS") == "1"),
    reason="需要环境变量 DEEPSEEK_API_KEY 且 PAI_RUN_LLM_TESTS=1（./eval.sh --llm）")


@pytest.mark.llm
@requires_llm
def test_real_model_creates_requested_file(tmp_path, eval_artifact_dir):
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    result = subprocess.run(
        [PAI, "--dangerously-skip-permissions", "--max-steps", "8",
         "在当前目录创建文件 评测.txt，内容只有一行：eval-真模型-OK。完成后简短确认。"],
        capture_output=True, text=True, env=dict(os.environ), cwd=proj, timeout=180)

    assert result.returncode == 0, f"真模型评测进程非零退出：{result.stderr[-500:]}"
    product = proj / "评测.txt"
    assert product.is_file(), "真模型没有产出 评测.txt"
    assert "eval-真模型-OK" in product.read_text(encoding="utf-8")

    home = Path(os.environ["HOME"])
    for session in home.glob(".pai/projects/*/sessions/*.jsonl"):
        shutil.copy(session, eval_artifact_dir / session.name)
