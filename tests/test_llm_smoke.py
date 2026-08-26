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


# ---- feature 38：只有真模型能验的两条 ----
#
# 它们各自对应一个「从未被真实验证过」的缺口，写下来是为了让「验一次」变成
# 一条命令（`./test.sh --llm`），而不是每次都要临时搭一遍场子。
# 写不花钱，跑才花钱——这条边界与本文件头部那条规矩是同一条。


@pytest.mark.llm
def test_remember_then_recall_round_trip(tmp_path, monkeypatch):
    """写入 → 召回的完整链路，真模型两端各一次。

    这条缺口是 2026-08-19 实测出来的：`~/.pai/projects/` 下 5 个项目目录
    全部只有 `sessions/`、没有 `memory/`——`remember` 在真实会话里一次都没被
    调用过，于是召回层每轮都走「候选为空」短路，请求根本不发。
    后果不是坏，是**看不出来**：「它没在工作」和「它工作得很好」外部表现一模一样。

    与 2026-08-11 那次真跑验的不是同一件事：那次验的是侧查询本身
    （json_object、max_tokens），这次验的是从写入到召回的整条链。
    """
    from pai.core.memory import memory_dir, scan_memories
    from pai.core.recall import RecallState, make_recall

    monkeypatch.chdir(tmp_path)                  # 记忆写进临时项目目录，不碰真实的
    client, model = make_client(), model_name()

    run_agent(
        "把这条记下来：这个项目的测试入口是 ./test.sh，不要用 pytest 直接跑。"
        "用 remember 工具记，记完简短确认一句。",
        client=client, model=model, tools=get_tools(), max_steps=6,
        on_event=lambda _: None,
    )
    written = scan_memories(memory_dir())
    assert written, "真模型没有调用 remember——召回层因此永远走空目录短路"

    recall = make_recall(client=client, model=model, directory=memory_dir(),
                         state=RecallState())
    block, usage = recall("我该怎么跑这个项目的测试？")
    assert "test.sh" in block, (
        f"写进去了却召不回来——链路断在召回这一头。选中的块：{block!r}")
    assert usage.get("total_tokens"), "侧查询的 usage 必须回传（它要计进预算熔断）"


@pytest.mark.llm
def test_a_path_scoped_rule_actually_reaches_the_model(tmp_path, monkeypatch):
    """路径作用域规则（feature 36）：模型读到匹配文件之后，规则真的进了上下文，
    而且模型真的照着做了。

    离线测试只断言得了「正文进了 messages」。「模型会不会听」是另一件事，
    而那才是这层机制存在的理由——36 交付时如实登记了这条没验过。
    """
    from pai.modes.assembly import assemble

    monkeypatch.chdir(tmp_path)
    rules = tmp_path / ".pai" / "rules"
    rules.mkdir(parents=True)
    (rules / "标记.md").write_text(
        "---\npaths: web/**\n---\n\n"
        "读到 web/ 下的文件之后，回答的开头必须原样写上 `[前端]` 这四个字符。",
        encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "a.css").write_text("body { color: red; }", encoding="utf-8")

    client, model = make_client(), model_name()
    asm = assemble(client=client, tools=get_tools(), warn=lambda _s: None,
                   on_event=lambda _e: None, session=None, recall_model=model,
                   mode="bypassPermissions", asker=None)
    answer = run_agent(
        "读一下 web/a.css，然后用一句话说说它是干什么的。",
        client=client, model=model, tools=asm.tools, max_steps=6,
        before_tool_call=asm.gate, on_paths_touched=asm.on_paths_touched,
        on_event=lambda _: None,
    )
    assert "[前端]" in answer, (
        f"规则没被模型照着做——它要么没进上下文，要么进了但压不住。实际回答：{answer!r}")
