"""共享测试夹具与小工具（feature 40）。

抽出来的判据不是「看着重复」，是**跨测试文件的 import 已经出现**——
`from tests.test_skills import _repl`、`from tests.test_recall import reply`、
`from tests.test_memory_scan import write_memory`……测试文件 A import 测试文件 B
意味着 B 的任何改动都可能让 A 假失败，而 A 的作者根本不知道自己依赖了 B。

同族但住别处的两位：真实会话轨迹在 `tests/trajectories.py`，
假客户端与假 provider 在 `tests/fake_llm.py` / `tests/fake_provider.py`
（它们是「被注入的替身」，不是夹具）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fake_llm import FakeClient
from pai.core.permissions import RuleSet

# 放行一切的规则集。多数测试测的是装配/交互，不是权限——而 feature 09 的边界兜底
# （写一律 ask、bash 一律 ask、界外读 ask）会把它们全拦住。
# 此前它在 5 个测试文件里各定义了一遍 `_OPEN`。
OPEN_RULES = RuleSet.from_lists(default_decision="allow")


def scripted_reader(lines):
    """脚本化输入源：元素是字符串就当用户输入，是异常类就抛（模拟 Ctrl+C / Ctrl+D）。

    队列空了抛 `EOFError`——那是 REPL 的正常退出信号，测试不必每次都在末尾补一个。
    「输入源可注入」是 modes 层能被离线测的唯一原因（features/05 拍板）。
    """
    queue = list(lines)

    def read(prompt: str = "") -> str:
        if not queue:
            raise EOFError
        item = queue.pop(0)
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item
        return item

    return read


def write_memory(directory: Path, name: str, *, description: str = "一句话描述",
                 type_: str = "project", body: str = "正文",
                 mtime: Optional[float] = None) -> Path:
    """写一篇带 frontmatter 的记忆（feature 10 的一事一文件格式）。

    `mtime` 可指定：新鲜度提示与「按 mtime 新→旧排序」都要拿它做输入，
    而真实文件的 mtime 是写入时刻，测不出「三个月前那篇」。
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "metadata:\n"
        f"  type: {type_}\n"
        "  originSessionId: abc123\n"
        "  modified: 2026-08-11T10:00:00Z\n"
        "---\n"
        f"\n{body}\n",
        encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(path, (mtime, mtime))
    return path


def recall_reply(names: list, usage: Optional[dict] = None) -> dict:
    """召回侧查询的一轮假回复：`{"selected": [...]}`。

    侧查询走非流式且要求 json_object，所以回的是 content 里的一段 JSON——
    形状照真实实测（2026-08-11 那次真跑抓到的两个坑就出在这条路上）。
    """
    turn = {"content": json.dumps({"selected": names}, ensure_ascii=False)}
    if usage:
        turn["usage"] = usage
    return turn


def run_repl(lines, script, tmp_path, monkeypatch):
    """在一个干净的临时项目目录里跑一轮 REPL，返回 (假客户端, 屏幕上打过的话)。

    `monkeypatch.chdir` 是必需的而不是讲究：项目级 skills / rules / `.pai/settings.json`
    / 指令文件全都按 cwd 找，不换目录就会捡到 pai 仓库自己的那些
    （feature 35 当场炸出过两条这样的测试）。
    """
    from pai.modes.interactive import run_interactive

    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    monkeypatch.chdir(proj)
    out: list = []
    client = FakeClient(script)
    run_interactive(client=client, model="fake", reader=scripted_reader(lines),
                    out=out.append, on_event=lambda _: None, no_session=True,
                    rules=OPEN_RULES)
    return client, "\n".join(out)
