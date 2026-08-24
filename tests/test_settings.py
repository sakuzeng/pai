"""feature 30 · settings 统一读取层 + 通用信任门禁的原语单测。

消费方行为（权限/hoooks/mcp/skills 的各自语义）由它们既有测试盯着；
这里只钉原语本身：读盘容错一份实现、marker 读写、门禁三态。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pai.core.settings import (
    bash_timeout_seconds,
    mark_project_trusted,
    project_trust_gate,
    project_trusted,
    read_settings_layers,
)


def _write(root, data) -> None:
    p = root / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if isinstance(data, dict) else data,
                 encoding="utf-8")


# ---------------------------------------------------------------- 分层读取

def test_read_settings_layers_returns_both_layers_with_paths(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write(home, {"a": 1})
    _write(proj, {"b": 2})
    (user_path, user), (proj_path, project) = read_settings_layers(
        cwd=proj, home=home, warn=lambda _m: None)
    assert user == {"a": 1} and project == {"b": 2}
    assert user_path == home / ".pai" / "settings.json"
    assert proj_path == proj / ".pai" / "settings.json"


def test_read_settings_layers_missing_files_are_empty(tmp_path):
    (_, user), (_, project) = read_settings_layers(
        cwd=tmp_path / "nowhere", home=tmp_path / "nohome",
        warn=lambda _m: pytest.fail("没有文件是常态，不该告警"))
    assert user == {} and project == {}


def test_read_settings_layers_bad_json_warns_only_that_layer(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write(home, {"ok": True})
    _write(proj, "{烂掉的")
    warnings: list[str] = []
    (_, user), (_, project) = read_settings_layers(
        cwd=proj, home=home, warn=warnings.append)
    assert user == {"ok": True}
    assert project == {}
    assert len(warnings) == 1 and "不是合法 JSON" in warnings[0]


# ---------------------------------------------------------------- 通用信任门禁

def _items():
    return [SimpleNamespace(name="mine", source="user"),
            SimpleNamespace(name="theirs", source="project")]


_TEXTS = dict(
    question=lambda n, names: f"项目里有 {n} 个东西（{names}），信任吗？",
    trust_option="信任（记住）",
    refuse_option="本次不用",
    refused_note=lambda names: f"本次未启用：{names}",
    unattended_note=lambda names: f"未信任已跳过：{names}",
)


def test_trust_marker_roundtrip_and_isolation(tmp_path):
    proj = tmp_path / "proj"
    assert not project_trusted("x_trusted", cwd=proj, home=tmp_path / "home")
    mark_project_trusted("x_trusted", cwd=proj, home=tmp_path / "home")
    assert project_trusted("x_trusted", cwd=proj, home=tmp_path / "home")
    # 不同 marker 互不串（skills 信任不等于 mcp 信任）
    assert not project_trusted("y_trusted", cwd=proj, home=tmp_path / "home")


def test_gate_unattended_drops_project_items_with_note(tmp_path):
    warnings: list[str] = []
    kept = project_trust_gate(_items(), marker="x_trusted",
                              cwd=tmp_path / "proj", home=tmp_path / "home",
                              warn=warnings.append, **_TEXTS)
    assert [it.name for it in kept] == ["mine"]
    assert warnings == ["未信任已跳过：theirs"]


def test_gate_trust_persists_and_refuse_does_not(tmp_path):
    proj, home = tmp_path / "proj", tmp_path / "home"
    kept = project_trust_gate(_items(), marker="x_trusted", cwd=proj, home=home,
                              ask=lambda _q, options: options[1],
                              warn=lambda _m: None, **_TEXTS)
    assert [it.name for it in kept] == ["mine"]          # 拒绝：丢弃、不持久化
    asked: list[str] = []

    def trust(question, options):
        asked.append(question)
        return options[0]

    kept2 = project_trust_gate(_items(), marker="x_trusted", cwd=proj, home=home,
                               ask=trust, warn=lambda _m: None, **_TEXTS)
    assert [it.name for it in kept2] == ["mine", "theirs"]
    assert asked == ["项目里有 1 个东西（theirs），信任吗？"]
    kept3 = project_trust_gate(_items(), marker="x_trusted", cwd=proj, home=home,
                               ask=lambda *_: pytest.fail("信任后不该再问"),
                               warn=lambda _m: None, **_TEXTS)
    assert [it.name for it in kept3] == ["mine", "theirs"]


# ---------------------------------------------------------------- bash 超时配置

def test_bash_timeout_seconds_reads_valid_value():
    """超时可配置（TODO 工具调用超时 P1）：CC 走 env、dsh 走 settings section，
    pai 已有 settings 层，走 settings 与架构一致。"""
    assert bash_timeout_seconds({"bash": {"timeoutSeconds": 300}},
                                warn=lambda _m: None) == 300


def test_bash_timeout_seconds_missing_returns_none():
    assert bash_timeout_seconds({}, warn=lambda _m: None) is None
    assert bash_timeout_seconds({"bash": {}}, warn=lambda _m: None) is None


@pytest.mark.parametrize("bad", ["300", 0, -5, 601, True])
def test_bash_timeout_seconds_invalid_warns_and_falls_back(bad):
    """非法值 warn + 回默认（None）——静默按默认走的话，用户会以为自己配置生效了
    （与 mcp timeout、tui 开关同一条 fail-loud 约定）。上限即 MAX_TIMEOUT_SECONDS
    （600）：默认值配得比模型可传上限还大没有意义。bool 是 int 子类，单独挡。"""
    warns: list = []
    assert bash_timeout_seconds({"bash": {"timeoutSeconds": bad}},
                                warn=warns.append) is None
    assert warns and "timeoutSeconds" in warns[0]


# ---------------------------------------------------------------- additionalDirectories

def test_additional_directories_parses_and_expands_home():
    from pai.core.settings import additional_directories

    dirs = additional_directories(
        {"permissions": {"additionalDirectories": ["/tmp/extra", "~/notes"]}},
        warn=lambda _m: None)
    assert dirs[0] == "/tmp/extra"
    assert dirs[1].endswith("/notes") and not dirs[1].startswith("~")


def test_additional_directories_missing_is_empty():
    from pai.core.settings import additional_directories

    assert additional_directories({}, warn=lambda _m: None) == ()


def test_additional_directories_invalid_warns_and_ignores():
    """feature 33（H9）：这个键在 boundary 的 docstring 与 STATUS 里都声称
    存在，实际从没接进装配——用户配了静默不生效，比没有这个键更糟。
    接上之余，非法形状照 fail-loud 约定 warn。"""
    from pai.core.settings import additional_directories

    warns: list = []
    assert additional_directories(
        {"permissions": {"additionalDirectories": "not-a-list"}},
        warn=warns.append) == ()
    assert warns and "additionalDirectories" in warns[0]
