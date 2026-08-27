"""真模型会不会选专用工具（feature 46 拍板问 4·A）。

**这是本轮唯一能证明它有用的测试**。feature 45 的全部教训是：离线断言
「提示语里有那几个字」证明不了「模型看了之后会听」——四轮工具建设默默失效，
而所有单测都是绿的。

默认不跑（同 test_llm_smoke.py：要 DEEPSEEK_API_KEY + PAI_RUN_LLM_TESTS=1）。
跑它：`./test.sh --llm`。写不花钱，跑才花钱。

断言写成**能容忍随机性**的形状：不要求「只用了那一个工具」，
只要求「用了它」且「没有拿 bash 去干它的活」——后者才是 feature 45 观察到的病。
"""
import os

import pytest

from pai.config import make_client, model_name
from pai.core.events import ToolStart
from pai.core.loop import build_system_prompt, run_agent
from pai.core.tools import get_tools


def _run(task, cwd, max_steps=6):
    """跑一轮真模型，回 `[(工具名, 参数), …]`。"""
    calls = []

    def on_event(e):
        if isinstance(e, ToolStart):
            calls.append((e.name, e.args))

    tools = get_tools()
    run_agent(task, client=make_client(), model=model_name(), tools=tools,
              max_steps=max_steps, on_event=on_event,
              system_prompt=build_system_prompt(tools, project_root=cwd))
    return calls


def _bash_commands(calls):
    return [a.get("command", "") for name, a in calls if name == "bash"]


@pytest.mark.llm
def test_the_model_picks_run_tests_instead_of_bash(tmp_path, monkeypatch):
    """feature 45 的原始症状：任务明说「跑测试」，`run_tests` 零次被选中。

    那次它走 bash、7 次权限弹窗、烧完预算没做完。这条测试是那个症状的反面。
    """
    (tmp_path / "test.sh").write_text("#!/bin/sh\necho '1 passed'\n", encoding="utf-8")
    os.chmod(tmp_path / "test.sh", 0o755)
    monkeypatch.chdir(tmp_path)

    calls = _run("跑一下这个项目的测试，告诉我结果。", str(tmp_path))
    names = [n for n, _ in calls]
    assert "run_tests" in names, f"模型没选 run_tests，它调了：{names}"
    assert not any("pytest" in c or "test.sh" in c for c in _bash_commands(calls)), \
        f"模型拿 bash 去跑测试了：{_bash_commands(calls)}"


@pytest.mark.llm
def test_the_model_picks_search_files_instead_of_grep(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("MAGIC_LIMIT = 4000\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("import a\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    calls = _run("MAGIC_LIMIT 定义在哪个文件？", str(tmp_path))
    names = [n for n, _ in calls]
    assert "search_files" in names, f"模型没选 search_files，它调了：{names}"
    assert not any("grep" in c or "find " in c for c in _bash_commands(calls)), \
        f"模型拿 bash 去搜代码了：{_bash_commands(calls)}"


@pytest.mark.llm
def test_the_injected_overview_removes_the_orientation_step(tmp_path, monkeypatch):
    """feature 45 里 `pwd && ls` 是**两次真跑的第一个调用**，且必然弹窗。

    结构摘要进了 system prompt 之后，那一步该根本不发生——
    钉的是「第一个工具调用不是拿 bash 探路」。
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "loop.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    calls = _run("这个项目的 src 目录里有什么？", str(tmp_path), max_steps=4)
    assert calls, "一个工具都没调"
    first, first_args = calls[0]
    assert first != "bash" or not any(
        w in first_args.get("command", "") for w in ("ls", "pwd", "find")), \
        f"第一步仍然是拿 bash 探路：{first} {first_args}"
