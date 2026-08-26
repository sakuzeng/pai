import os

import pytest

"""config 的 env 装配测试。"""

from pai.config import model_name, recall_model


def test_model_name_loads_dotenv_first(monkeypatch):
    """PAI_MODEL 配在 .env 时必须生效——不能依赖「client 恰好先被构造」的求值顺序（R3#7）。"""
    monkeypatch.delenv("PAI_MODEL", raising=False)

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("PAI_MODEL", "test-model-zzz")

    monkeypatch.setattr("pai.config.load_dotenv", fake_load_dotenv)
    assert model_name() == "test-model-zzz"


# ---- ~/.pai/.env 兜底（2026-08-10：pai 在别的项目里起不来） ----


@pytest.fixture
def clean_env(monkeypatch):
    """load_dotenv 直接写 os.environ，且写进去的键 monkeypatch 追踪不到——手动快照还原。"""
    saved = dict(os.environ)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAI_MODEL", raising=False)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _write_env(path, **pairs):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{k}={v}" for k, v in pairs.items()), encoding="utf-8")


def test_user_level_env_is_used_when_project_has_none(tmp_path, monkeypatch, clean_env):
    """pai 的立意就是在别的项目里跑——那些目录没有 .env，key 得有个用户级的家。"""
    from pai import config

    home = tmp_path / "home"
    _write_env(home / ".pai" / ".env", DEEPSEEK_API_KEY="sk-user-level")
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: home))

    config._load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-user-level"


def test_project_env_wins_over_user_env(tmp_path, monkeypatch, clean_env):
    """与 PAI.md 的分层顺序一致：越靠近项目的越优先。"""
    from pai import config

    home = tmp_path / "home"
    project = tmp_path / "proj"
    _write_env(home / ".pai" / ".env", DEEPSEEK_API_KEY="sk-user-level")
    _write_env(project / ".env", DEEPSEEK_API_KEY="sk-project")
    monkeypatch.chdir(project)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: home))

    config._load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-project"


def test_real_environment_variable_wins_over_both(tmp_path, monkeypatch, clean_env):
    from pai import config

    home = tmp_path / "home"
    _write_env(home / ".pai" / ".env", DEEPSEEK_API_KEY="sk-user-level")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-shell")

    config._load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-shell"


def test_project_env_is_found_from_cwd_not_from_the_package_location(tmp_path, monkeypatch,
                                                                    clean_env):
    """find_dotenv 默认从**调用方文件**所在目录向上找（= src/pai/），于是「项目级 .env」
    会解析成 pai 仓库自己那份。pai 的立意是在别的项目里跑，这个默认是错的。
    """
    from pai import config

    home = tmp_path / "home"
    project = tmp_path / "别人的项目"
    _write_env(project / ".env", DEEPSEEK_API_KEY="sk-别人的项目")
    monkeypatch.chdir(project)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: home))

    config._load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-别人的项目"


def test_user_dir_constant_does_not_drift_from_memory_module():
    """~/.pai 这个位置被 config、memory、memory_tool 三处用到，写死两遍就会漂。"""
    from pai import config
    from pai.core import memory

    assert config.USER_DIR == memory.USER_DIR


def test_recall_model_falls_back_to_the_main_model(monkeypatch):
    """没配便宜档就用主模型——宁可默认可用，也不要因为没配就静默不召回。"""
    monkeypatch.delenv("PAI_RECALL_MODEL", raising=False)
    monkeypatch.setenv("PAI_MODEL", "主模型")
    assert recall_model() == "主模型"


def test_recall_model_env_overrides(monkeypatch):
    monkeypatch.setenv("PAI_MODEL", "主模型")
    monkeypatch.setenv("PAI_RECALL_MODEL", "便宜档")
    assert recall_model() == "便宜档"


# ---- PAI_CONTEXT_WINDOW 非法值：报清楚，不裸抛 ValueError（02 终审 Minor#7） ----


def test_context_window_rejects_non_numeric_with_a_clear_message(monkeypatch, clean_env):
    """裸 int() 抛的 `invalid literal for int()` 说不出「是哪个 env 配错了」。

    对齐 make_client 的先例：报错要说清是谁、当前值是什么、该怎么改。
    """
    from pai.config import context_window

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    monkeypatch.setenv("PAI_CONTEXT_WINDOW", "1_000_000 tokens")
    with pytest.raises(SystemExit) as exc:
        context_window()
    message = str(exc.value)
    assert "PAI_CONTEXT_WINDOW" in message
    assert "1_000_000 tokens" in message


def test_context_window_rejects_non_positive(monkeypatch, clean_env):
    """0 与负数在语法上是合法整数，但阈值公式 `window - reserve` 会算出负预算，
    should_compact 从此每轮都触发——比崩溃更难查。"""
    from pai.config import context_window

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    monkeypatch.setenv("PAI_CONTEXT_WINDOW", "0")
    with pytest.raises(SystemExit) as exc:
        context_window()
    assert "PAI_CONTEXT_WINDOW" in str(exc.value)


def test_context_window_accepts_valid_values(monkeypatch, clean_env):
    from pai.config import context_window

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    monkeypatch.setenv("PAI_CONTEXT_WINDOW", "65536")
    assert context_window() == 65536
    monkeypatch.delenv("PAI_CONTEXT_WINDOW", raising=False)
    assert context_window() == 1_000_000


# ---- PAI_KEEP_RECENT_TOKENS：让压缩在真实使用里跑得到（TODO「压缩链路的可验证性」）----


def test_keep_recent_tokens_defaults_to_the_settings_default(monkeypatch, clean_env):
    """不配就是 CompactionSettings 的默认值——这个 env 是**降低门槛**用的口子，
    不是第二个真相来源。"""
    from pai.config import keep_recent_tokens
    from pai.core.compaction import CompactionSettings

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    monkeypatch.delenv("PAI_KEEP_RECENT_TOKENS", raising=False)
    assert keep_recent_tokens() == CompactionSettings().keep_recent_tokens


def test_keep_recent_tokens_reads_the_env(monkeypatch, clean_env):
    from pai.config import keep_recent_tokens

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    monkeypatch.setenv("PAI_KEEP_RECENT_TOKENS", "500")
    assert keep_recent_tokens() == 500


def test_keep_recent_tokens_rejects_bad_values(monkeypatch, clean_env):
    """与 PAI_CONTEXT_WINDOW 同款报错（02 终审 Minor#7 定的先例）：
    说清是哪个 env、当前值是什么。非正数一并挡——0 会让切点算法把整段历史都压掉。"""
    from pai.config import keep_recent_tokens

    monkeypatch.setattr("pai.config._load_env", lambda: None)
    for bad in ("20k", "0", "-1"):
        monkeypatch.setenv("PAI_KEEP_RECENT_TOKENS", bad)
        with pytest.raises(SystemExit) as exc:
            keep_recent_tokens()
        assert "PAI_KEEP_RECENT_TOKENS" in str(exc.value)
        assert bad in str(exc.value)
