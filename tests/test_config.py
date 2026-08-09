"""config 的 env 装配测试。"""

from pai.config import model_name


def test_model_name_loads_dotenv_first(monkeypatch):
    """PAI_MODEL 配在 .env 时必须生效——不能依赖「client 恰好先被构造」的求值顺序（R3#7）。"""
    monkeypatch.delenv("PAI_MODEL", raising=False)

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("PAI_MODEL", "test-model-zzz")

    monkeypatch.setattr("pai.config.load_dotenv", fake_load_dotenv)
    assert model_name() == "test-model-zzz"
