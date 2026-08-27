"""evals 套件的公共件（feature 32 T1）：工件落盘的薄胶水。

能离线钉的形状都在 src/pai/evals/artifacts.py；这里只做 pytest 接线：
每条 eval（含失败与 skip）在 runs.jsonl 追加一行，需要存会话快照的 case
用 `eval_artifact_dir` fixture 拿目录——它会自动把相对路径登进本条记录。

HOME 隔离照抄 tests/conftest.py 的铁律：评测起的真 pai 子进程绝不许写
真实 `$HOME`（2026-08-10 的教训对评测同样成立）。
"""
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

# 项目 .env 也算数（feature 47）。原设计是「key 必须来自环境变量」，
# 理由是 HOME 被隔离、`~/.pai/.env` 读不到——但那条把**项目级** .env 也一起挡了，
# 于是 `./eval.sh --llm` 在一台配好 .env 的机器上什么都不跑、还一声不吭地全 skip。
# 花钱的门禁没有放宽：它一直是 `PAI_RUN_LLM_TESTS=1`（显式选择），不是「有没有 key」。
# 读项目 .env 与 HOME 隔离不冲突——隔离防的是**写进真实 HOME**。
load_dotenv()

from pai.evals.artifacts import append_run_record, build_run_record, new_run_dir

EVAL_ROOT = Path(__file__).resolve().parent

# fake_provider 住 tests/（与既有 e2e 共用同一个假服务，不复制第二份）
sys.path.insert(0, str(EVAL_ROOT.parent / "tests"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "eval_rep_" + rep.when, rep)


@pytest.fixture(scope="session")
def eval_run_dir():
    return new_run_dir(EVAL_ROOT / ".eval")


@pytest.fixture(autouse=True)
def _eval_home_isolation(tmp_path, monkeypatch):
    home = tmp_path / "eval-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture(autouse=True)
def _eval_record(request, eval_run_dir):
    request.node.eval_artifacts = []
    started = time.time()
    yield
    rep = (getattr(request.node, "eval_rep_call", None)
           or getattr(request.node, "eval_rep_setup", None))
    if rep is None:
        status = "failed"
    elif rep.skipped:
        status = "skipped"
    else:
        status = "passed" if rep.passed else "failed"
    append_run_record(eval_run_dir / "runs.jsonl", build_run_record(
        case=request.node.nodeid, status=status,
        duration_ms=int((time.time() - started) * 1000),
        artifacts=request.node.eval_artifacts))


@pytest.fixture
def eval_artifact_dir(request, eval_run_dir):
    """本条 eval 的工件目录（存被评测进程的会话 JSONL 等），自动登记进记录。"""
    name = request.node.name.replace("/", "_")
    directory = eval_run_dir / "sessions" / name
    directory.mkdir(parents=True, exist_ok=True)
    request.node.eval_artifacts.append(str(directory.relative_to(eval_run_dir)))
    return directory
