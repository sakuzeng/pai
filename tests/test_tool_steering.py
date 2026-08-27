"""工具引导与项目结构注入（feature 46 Task 3）。

出处是 feature 45 的实测：整份 system prompt 里只有一句工具引导，是给
`edit_file` 的——而模型确实只听了那一句。`run_tests` 在任务明说「跑测试」时
零次被选中，加一句引导后 1 次调用、0 弹窗、9 秒完成。

本文件是**离线那一半**：断言那几句话确实生成出来了、结构注入是稳定的。
它证明不了「模型会听」——那一半在 `tests/test_llm_steering.py`（`--llm` 标记，
默认跳过），feature 45 的全部教训就是不能拿这一半冒充那一半。
"""
import os

import pytest

from pai.core.loop import build_system_prompt
from pai.core.tools import get_tools


def test_every_specialised_tool_gets_a_steering_line():
    """四个专用工具各有一句，缺一条就是 feature 45 那个缺口的一部分。"""
    prompt = build_system_prompt(get_tools())
    for tool, hint in (("read_file", "读文件"),
                       ("search_files", "找代码"),
                       ("run_tests", "跑测试"),
                       ("git_read", "git"),
                       ("list_dir", "目录")):
        assert tool in prompt, f"{tool} 没被提到"
        assert hint in prompt, f"{tool} 没有引导句（只出现在工具名单里不算）"


def test_steering_lines_are_conditional_on_the_tool_being_present():
    """受限工具集（子 agent / deny 摘掉工具）时不许摆一句调不动的引导。"""
    subset = get_tools(["read_file", "bash"])
    prompt = build_system_prompt(subset)
    assert "找代码" not in prompt and "跑测试" not in prompt
    assert "读文件" in prompt, "子集里有 read_file，它那句该在"


def test_bash_description_points_at_the_specialised_tools():
    """第二个决策时刻（在 schema 里挑工具那一刻）也要有引导——拍板问 1·A。"""
    desc = get_tools()["bash"].description
    assert "专用工具" in desc or "search_files" in desc, \
        f"bash 的描述没把模型推向专用工具：{desc!r}"


def test_the_project_overview_is_injected(tmp_path):
    """工作目录 + 结构摘要进 system prompt，开场那一步就不必发生了。

    顺带修掉 45-C4：模型此前不知道自己的 cwd，于是每条 bash 都写
    `cd /abs/path && …` 或 `git -C /abs/path …`，既浪费 token 又让权限弹窗里的
    命令长得没法读。
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    prompt = build_system_prompt(get_tools(), project_root=str(tmp_path))
    assert str(tmp_path) in prompt, "没告诉模型 cwd"
    assert "src/" in prompt and "README.md" in prompt


def test_without_a_project_root_the_prompt_is_byte_for_byte_unchanged():
    """不传就一个字都不加——老路径（不经装配层直调 run_agent）逐字不变。"""
    before = build_system_prompt(get_tools())
    assert build_system_prompt(get_tools(), project_root=None) == before


def test_the_prompt_is_stable_across_calls(tmp_path):
    """同一个项目生成两次必须逐字相同——不稳定的前缀会让每个会话的缓存前缀都不同
    （feature 22「护住缓存前缀」那条规矩）。"""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for i in range(20):
        (tmp_path / f"f{i}.txt").write_text("", encoding="utf-8")
    tools = get_tools()
    assert (build_system_prompt(tools, project_root=str(tmp_path))
            == build_system_prompt(tools, project_root=str(tmp_path)))


def test_a_broken_project_root_does_not_break_the_prompt(tmp_path):
    """错误路径：路径不存在/读不了时，提示词照样要生成出来。

    坏一个可选的上下文块就把整个会话起不来，是最不划算的失败方式
    （同「坏文件绝不弄挂 agent」那条铁律）。
    """
    prompt = build_system_prompt(get_tools(), project_root=str(tmp_path / "nope"))
    assert "你是一个最小化的编码 agent" in prompt


def test_once_passes_the_working_directory_into_the_prompt(tmp_path, monkeypatch):
    """接线测试：写了却没接进装配，等于没做（feature 33 H9 的教训）。

    第一版我写成「assemble 返回里有没有 system_prompt，没有就 skip」——
    那条测试**永远在 skip**，也就是一条永不执行的接线测试。
    改成钉住 `run_once` 真正传给 `build_system_prompt` 的那个 kwarg。
    """
    import json

    from pai.modes import once as once_mod
    from tests.fake_llm import FakeClient
    from tests.helpers import OPEN_RULES

    monkeypatch.chdir(tmp_path)
    seen = {}
    real = once_mod.build_system_prompt

    def spy(tools, **kw):
        seen.update(kw)
        return real(tools, **kw)

    monkeypatch.setattr(once_mod, "build_system_prompt", spy)
    once_mod.run_once("说句话", client=FakeClient([{"content": "好"}]),
                      model="fake", no_session=True, rules=OPEN_RULES)
    assert seen.get("project_root") == os.getcwd(), \
        f"once 没把工作目录传进 system prompt：{seen!r}"
