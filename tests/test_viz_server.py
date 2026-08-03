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
