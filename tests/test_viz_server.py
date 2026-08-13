"""server 冒烟测试:随机端口起真 server,打两个端点。全离线(子进程只 import pai,不打 API)。

_collect() 的错误分支(子进程报错 / stdout 不是合法 JSON)用 monkeypatch 直接测,
不必真起子进程——起子进程测不到「子进程返回非 0」这种可控输入,mock 更直接。
"""

import json
import threading
import urllib.request
from types import SimpleNamespace

import pytest

from pai.viz import server as server_module
from pai.viz.server import make_server


@pytest.fixture()
def viz_server():
    httpd = make_server(port=0)  # 0 = 让系统挑个空闲端口,测试并行也不撞
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_index_served(viz_server):
    with urllib.request.urlopen(f"{viz_server}/") as r:
        assert r.status == 200
        assert "text/html" in r.headers["Content-Type"]
        assert "pai" in r.read().decode("utf-8")


def test_api_structure_returns_collected_json(viz_server):
    with urllib.request.urlopen(f"{viz_server}/api/structure") as r:
        assert r.status == 200
        data = json.loads(r.read().decode("utf-8"))
    assert "tools" in data and "pipeline" in data
    assert any(t["name"] == "bash" for t in data["tools"])


def test_index_is_real_page_not_placeholder(viz_server):
    with urllib.request.urlopen(f"{viz_server}/") as r:
        html = r.read().decode("utf-8")
    # 真页面的标志:会去打 API、有两个区域的容器
    assert "/api/structure" in html
    assert 'id="pipeline"' in html and 'id="stages"' in html


def test_unknown_path_404(viz_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(f"{viz_server}/nope")
    assert ei.value.code == 404


def test_collect_returns_500_on_subprocess_error(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"Traceback: boom")

    monkeypatch.setattr(server_module.subprocess, "run", fake_run)
    code, body = server_module._collect()
    assert code == 500
    data = json.loads(body)
    assert "Traceback: boom" in data["error"]


def test_collect_returns_500_when_stdout_is_not_valid_json(monkeypatch):
    # returncode==0 但 stdout 被杂散 print() 弄脏——不是「子进程崩了」,是「输出脏了」,
    # 两者要分开覆盖,否则脏输出会被当成 200 直接转发给前端,前端 JSON.parse 报个没头绪的错。
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=b"debug noise{}", stderr=b"")

    monkeypatch.setattr(server_module.subprocess, "run", fake_run)
    code, body = server_module._collect()
    assert code == 500
    data = json.loads(body)
    assert "error" in data


# ---- feature 17：观测端点（会话列表 / 时间线 / 增量游标 / 跳编辑器）

def get_json(base, path):
    with urllib.request.urlopen(f"{base}{path}") as r:
        return r.status, json.load(r)


def write_session(directory, name, rows):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return path


@pytest.fixture()
def sessions(tmp_path, monkeypatch):
    """把 server 看到的会话目录指到 tmp——**绝不读真实 $HOME**（08-10 教训）。

    要连 `projects_root` 一起指：列表是跨项目扫的（`<root>/*/sessions/*.jsonl`），
    只改 `sessions_dir` 的话扫不到这里，测试会看见一个空目录。
    """
    root = tmp_path / "projects"
    directory = root / "-test-proj" / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: directory)
    return directory


def test_sessions_lists_newest_first(sessions, viz_server):
    import os
    import time

    a = write_session(sessions, "20260101-000000-aaaa.jsonl",
                      [{"ts": 1.0, "role": "user", "content": "旧"}])
    b = write_session(sessions, "20260102-000000-bbbb.jsonl",
                      [{"ts": 2.0, "role": "user", "content": "新"}])
    os.utime(a, (1000, 1000))
    os.utime(b, (time.time(), time.time()))

    status, data = get_json(viz_server, "/api/sessions")

    assert status == 200
    assert [s["name"] for s in data["sessions"]] == [b.name, a.name]
    assert data["sessions"][0]["has_events"] is False


def test_sessions_reports_which_ones_have_an_event_stream(sessions, viz_server):
    """有没有观测流决定页面能显示多少东西,得让用户在下拉框里就看得出来。"""
    write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])
    write_session(sessions, "s.events.jsonl", [{"ts": 1.5, "event": "TurnStart", "step": 1}])

    _, data = get_json(viz_server, "/api/sessions")

    names = [s["name"] for s in data["sessions"]]
    assert names == ["s.jsonl"], "事件文件不是会话,不该自己占一行"
    assert data["sessions"][0]["has_events"] is True


def test_flow_returns_grouped_turns(sessions, viz_server):
    write_session(sessions, "s.jsonl", [
        {"ts": 1.0, "role": "user", "content": "问一句"},
        {"ts": 2.0, "role": "assistant", "content": "答一句"},
    ])

    status, data = get_json(viz_server, "/api/flow?session=s.jsonl")

    assert status == 200
    assert [t["user"] for t in data["turns"]] == ["问一句"]


def test_flow_defaults_to_the_newest_session(sessions, viz_server):
    """默认看「终端正跑着的那个」——每次都要先选一次会话是没必要的摩擦。"""
    import os
    import time

    old = write_session(sessions, "old.jsonl", [{"ts": 1.0, "role": "user", "content": "旧"}])
    write_session(sessions, "new.jsonl", [{"ts": 2.0, "role": "user", "content": "新"}])
    os.utime(old, (1000, 1000))

    _, data = get_json(viz_server, "/api/flow")

    assert data["turns"][0]["user"] == "新"


def test_events_first_poll_returns_only_the_cursor(sessions, viz_server):
    """没给 cursor = 页面刚打开:只回当前行数,**不重放历史**——
    否则一开页面就把整天的事件闪一遍(waku events_since 同款语义)。"""
    write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])
    write_session(sessions, "s.events.jsonl", [
        {"ts": 1.1, "event": "AgentStart", "task": "问"},
        {"ts": 1.2, "event": "AgentEnd", "reason": "final", "text": "答"},
    ])

    _, data = get_json(viz_server, "/api/events?session=s.jsonl")

    assert data["records"] == []
    assert data["cursor"] == "1:2"        # 审计流 1 行、观测流 2 行


def test_events_returns_only_what_arrived_after_the_cursor(sessions, viz_server):
    path = write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])
    ev = write_session(sessions, "s.events.jsonl", [{"ts": 1.1, "event": "AgentStart", "task": "问"}])

    _, first = get_json(viz_server, "/api/events?session=s.jsonl")
    with ev.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": 2.0, "event": "ToolStart", "tool_call_id": "c1",
                            "name": "bash", "args": {}}) + "\n")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": 2.1, "role": "assistant", "content": "答"}) + "\n")

    _, second = get_json(viz_server, f"/api/events?session=s.jsonl&cursor={first['cursor']}")

    kinds = [r.get("event") or r.get("role") for r in second["records"]]
    assert kinds == ["ToolStart", "assistant"], "两个流都要追,且按 ts 归并"
    assert second["cursor"] == "2:2"


def test_events_survives_a_truncated_cursor(sessions, viz_server):
    """游标是客户端传来的,不能信:乱七八糟的值应退化成「从现在开始」而不是 500。"""
    write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])

    for bad in ("", "abc", "1", "9:9", "-3:-3", "1:2:3"):
        status, data = get_json(viz_server, f"/api/events?session=s.jsonl&cursor={bad}")
        assert status == 200, bad
        assert data["records"] == [], bad


def test_unknown_session_is_a_clean_error_not_a_traceback(sessions, viz_server):
    status, data = get_json(viz_server, "/api/flow?session=nope.jsonl")
    assert status == 200 and data["turns"] == []
    assert data["error"]


def test_session_name_cannot_escape_the_sessions_directory(sessions, viz_server):
    """`session` 参数直接进路径,不挡的话是任意文件读取。"""
    write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])

    for evil in ("../../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "/etc/passwd"):
        _, data = get_json(viz_server, f"/api/flow?session={evil}")
        assert data["turns"] == [] and data["error"]


def test_reveal_refuses_paths_outside_the_repo(viz_server, monkeypatch):
    opened = []
    monkeypatch.setattr(server_module, "_editor_cmd", lambda: ["fake-editor"])
    monkeypatch.setattr(server_module.subprocess, "run", lambda *a, **k: opened.append(a))

    _, data = get_json(viz_server, "/api/reveal?path=../../../etc/passwd")

    assert data.get("error")
    assert opened == [], "越界路径绝不能真去开"


def test_reveal_opens_a_repo_file_in_the_editor(viz_server, monkeypatch):
    opened = []
    monkeypatch.setattr(server_module, "_editor_cmd", lambda: ["fake-editor"])
    monkeypatch.setattr(server_module.subprocess, "run",
                        lambda argv, **k: opened.append(argv))

    _, data = get_json(viz_server, "/api/reveal?path=src/pai/core/loop.py&line=42")

    assert data.get("ok") is True
    assert opened and "fake-editor" in opened[0][0]
    assert any("loop.py" in str(part) for part in opened[0])


def test_events_tells_the_client_which_session_it_resolved(sessions, viz_server):
    """真跑时发现的:新起一次 pai 会**换一个会话文件**,而页面盯的是 latest。
    旧游标对新文件不合法 → 走「重新对齐」分支 → 返回 0 条,
    于是页面显示「什么都没发生」,而实际上一个全新回合正在产出事件。

    修法:响应带回解析到的会话名,前端一比对就知道该重载时间线。
    """
    import os
    import time

    old = write_session(sessions, "old.jsonl", [{"ts": 1.0, "role": "user", "content": "旧"}] * 7)
    os.utime(old, (1000, 1000))

    _, first = get_json(viz_server, "/api/events")
    assert first["session"] == "old.jsonl"

    write_session(sessions, "new.jsonl", [{"ts": 2.0, "role": "user", "content": "新"}])
    os.utime(sessions / "new.jsonl", (time.time(), time.time()))

    _, second = get_json(viz_server, f"/api/events?cursor={first['cursor']}")

    assert second["session"] == "new.jsonl", "换了会话必须说出来,否则页面静默停更"
    assert second["cursor"] == "1:0"


def test_flow_also_reports_which_session_it_resolved(sessions, viz_server):
    """同理:`latest` 解析到哪个文件,前端要拿得到名字才能显示在下拉框里。"""
    write_session(sessions, "s.jsonl", [{"ts": 1.0, "role": "user", "content": "问"}])

    _, data = get_json(viz_server, "/api/flow")

    assert data["session"] == "s.jsonl"


# ---- feature 17 T7：前端结构断言（没有 JS 测试运行器，机器可判的钉在这里）

def index_source():
    from importlib import resources

    return resources.files("pai.viz").joinpath("index.html").read_text(encoding="utf-8")


def test_page_has_the_timeline_and_session_picker():
    html = index_source()
    for anchor in ('id="timeline"', 'id="sessions"', 'id="live"', 'id="arch-status"'):
        assert anchor in html, f"页面缺 {anchor}"


def test_every_api_the_page_calls_actually_has_a_route():
    """前端引用的每个 `/api/` 路径必须真有路由——端点改名而前端没跟，
    页面会静默瞎掉（fetch 拿 404，catch 吞掉，什么都不显示）。"""
    import re

    html = index_source()
    called = set(re.findall(r"['\"`(]/api/([a-z]+)", html))
    handler = inspect_source_of_do_get()
    for name in called:
        assert f'"/api/{name}"' in handler, f"页面调了 /api/{name}，但 server 没有这条路由"


def inspect_source_of_do_get() -> str:
    import inspect

    return inspect.getsource(server_module.VizHandler.do_GET)


def test_animation_map_only_references_real_pipeline_nodes():
    """STAGE 映射引用的节点 id 必须真存在于 _PIPELINE_NODES。

    waku 的 static/README 明说这类 id 漂移「测试抓不到，动画只是静默不亮」——
    pai 至少把存在性钉住。
    """
    import re

    from pai.viz.collect import _PIPELINE_NODES

    html = index_source()
    block = html.split("const STAGE = {", 1)[1].split("};", 1)[0]
    referenced = set(re.findall(r"'([a-z_]+)'", block))
    known = {n["id"] for n in _PIPELINE_NODES}
    assert referenced <= known, f"STAGE 引用了不存在的节点：{referenced - known}"


def test_event_types_in_the_animation_map_are_real_events():
    """反向：STAGE 的键里凡是事件名的，必须是真事件类型（拼错就永远不亮）。"""
    import dataclasses
    import re

    from pai.core import events as ev_mod

    html = index_source()
    block = html.split("const STAGE = {", 1)[1].split("};", 1)[0]
    keys = set(re.findall(r"^\s*([A-Za-z]+):", block, re.M))
    declared = {n for n, o in vars(ev_mod).items()
                if dataclasses.is_dataclass(o) and not n.startswith("_")}
    event_like = {k for k in keys if k[:1].isupper()}
    assert event_like <= declared, f"STAGE 里有不存在的事件：{event_like - declared}"
    # 审计流那几个小写键是 role/type，不是事件类型
    assert {k for k in keys if k[:1].islower()} <= {"usage", "assistant", "tool", "user"}


# ---- feature 17 T8：跨项目会话列表 + 编辑器 URL scheme

def test_sessions_lists_every_project_not_just_the_cwd_one(tmp_path, monkeypatch, viz_server):
    """会话目录按 **cwd** 分（`~/.pai/projects/<slug>/sessions/`），而
    `pai` 与 `pai-viz` 常常不在同一个目录起——AGENTS.md 要求手工冒烟在
    `pai_playground/` 里做，而 viz 你多半在仓库根开。只列 cwd 那个项目的话，
    页面会说「还没有会话文件」，而人明明刚跑过。

    所以列**所有项目**，每条带上它属于哪个项目。
    """
    root = tmp_path / "projects"
    here = root / "-Users-me-proj-a" / "sessions"
    there = root / "-Users-me-proj-b" / "sessions"
    write_session(here, "a.jsonl", [{"ts": 1.0, "role": "user", "content": "甲"}])
    write_session(there, "b.jsonl", [{"ts": 2.0, "role": "user", "content": "乙"}])
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: here)

    _, data = get_json(viz_server, "/api/sessions")

    names = {s["name"] for s in data["sessions"]}
    assert names == {"a.jsonl", "b.jsonl"}
    by_name = {s["name"]: s for s in data["sessions"]}
    assert by_name["a.jsonl"]["project"] == "-Users-me-proj-a"
    assert by_name["b.jsonl"]["project"] == "-Users-me-proj-b"
    # 当前 cwd 的项目要标出来：默认看的就是它，页面上得说清楚
    assert by_name["a.jsonl"]["current"] is True
    assert by_name["b.jsonl"]["current"] is False


def test_a_session_from_another_project_can_be_opened(tmp_path, monkeypatch, viz_server):
    """列得出来就得打得开——否则下拉框里那些条目是死的。"""
    root = tmp_path / "projects"
    here = root / "-proj-a" / "sessions"
    there = root / "-proj-b" / "sessions"
    write_session(here, "a.jsonl", [{"ts": 1.0, "role": "user", "content": "甲"}])
    write_session(there, "b.jsonl", [{"ts": 2.0, "role": "user", "content": "乙问"}])
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: here)

    _, data = get_json(viz_server, "/api/flow?session=b.jsonl")

    assert data["turns"][0]["user"] == "乙问"


def test_latest_across_projects_wins(tmp_path, monkeypatch, viz_server):
    """「跟着终端走」= 最新那个，不管它在哪个项目——
    在 playground 里跑、在仓库根看，是本轮要解决的正主。"""
    import os
    import time

    root = tmp_path / "projects"
    here = root / "-proj-a" / "sessions"
    there = root / "-proj-b" / "sessions"
    old = write_session(here, "a.jsonl", [{"ts": 1.0, "role": "user", "content": "旧"}])
    new = write_session(there, "b.jsonl", [{"ts": 2.0, "role": "user", "content": "新"}])
    os.utime(old, (1000, 1000))
    os.utime(new, (time.time(), time.time()))
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: here)

    _, data = get_json(viz_server, "/api/flow")

    assert data["turns"][0]["user"] == "新"


def test_same_name_in_two_projects_is_disambiguated(tmp_path, monkeypatch, viz_server):
    """会话文件名带时间戳+短 id，撞名概率低但不是零；
    撞了就必须能分开，否则点 B 打开的是 A。"""
    root = tmp_path / "projects"
    here = root / "-proj-a" / "sessions"
    there = root / "-proj-b" / "sessions"
    write_session(here, "same.jsonl", [{"ts": 1.0, "role": "user", "content": "甲"}])
    write_session(there, "same.jsonl", [{"ts": 2.0, "role": "user", "content": "乙"}])
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: here)

    _, data = get_json(viz_server, "/api/flow?session=-proj-b/same.jsonl")

    assert data["turns"][0]["user"] == "乙"


def test_a_session_id_still_cannot_escape_the_projects_root(tmp_path, monkeypatch, viz_server):
    """放宽成「项目/文件名」之后，越界检查更要在——两段都不许有 `..`。"""
    root = tmp_path / "projects"
    write_session(root / "-proj-a" / "sessions", "a.jsonl",
                  [{"ts": 1.0, "role": "user", "content": "甲"}])
    monkeypatch.setattr(server_module, "projects_root", lambda: root)
    monkeypatch.setattr(server_module, "sessions_dir", lambda: root / "-proj-a" / "sessions")

    for evil in ("../../../etc/passwd", "-proj-a/../../../etc/passwd",
                 "../-proj-a/sessions/a.jsonl", "/etc/passwd", "a/b/c.jsonl"):
        _, data = get_json(viz_server, f"/api/flow?session={evil}")
        assert data["turns"] == [] and data["error"], evil


def test_reveal_falls_back_to_the_editor_url_scheme(viz_server, monkeypatch):
    """没装 `code`/`cursor` CLI 时（macOS 上默认就没有），用 URL scheme：
    `vscode://file/<路径>:<行>` 会跳到**已经打开的那个窗口**，正是要的效果。
    比让用户先去装 CLI 好——少一步、且跳得更准。
    """
    opened = []
    monkeypatch.setattr(server_module, "_editor_cmd", lambda: None)
    monkeypatch.setattr(server_module, "_installed_editor_scheme", lambda: "vscode")
    monkeypatch.setattr(server_module.subprocess, "run", lambda argv, **k: opened.append(argv))

    _, data = get_json(viz_server, "/api/reveal?path=src/pai/core/loop.py&line=42")

    assert data.get("ok") is True
    assert opened, "应该真去开"
    argv = opened[0]
    assert argv[0] == "open"
    assert argv[1].startswith("vscode://file/")
    assert argv[1].endswith("/src/pai/core/loop.py:42")


def test_reveal_reports_when_there_is_no_editor_at_all(viz_server, monkeypatch):
    monkeypatch.setattr(server_module, "_editor_cmd", lambda: None)
    monkeypatch.setattr(server_module, "_installed_editor_scheme", lambda: None)

    _, data = get_json(viz_server, "/api/reveal?path=src/pai/core/loop.py")

    assert data.get("error") and "loop.py" in data["error"]
