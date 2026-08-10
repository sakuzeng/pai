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
