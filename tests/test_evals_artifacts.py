"""evals 公共件（feature 32 T1）：工件索引的纯逻辑。

evals/conftest.py 只是薄胶水；能离线钉的形状（run 目录命名、runs.jsonl
逐行追加、记录字段）都住 src/pai/evals/artifacts.py——评测基建自己
不许有静默失败（K evals/pi-evals.md 第二条）。
"""
import json

import pytest

from pai.evals.artifacts import append_run_record, build_run_record, new_run_dir


def test_new_run_dir_creates_timestamped_dir(tmp_path):
    d = new_run_dir(tmp_path, now=1755000000.0)
    assert d.is_dir() and d.parent == tmp_path
    # UTC 时间戳目录名：可排序、跨 run 不撞（同秒重跑是评测语境里不存在的场景）
    assert d.name == "20250812T120000Z"


def test_build_and_append_run_records_round_trip(tmp_path):
    path = tmp_path / "runs.jsonl"
    r1 = build_run_record(case="evals/test_replay.py::test_a", status="passed",
                          duration_ms=1234, artifacts=["sessions/test_a"])
    r2 = build_run_record(case="evals/test_replay.py::test_b", status="failed",
                          duration_ms=8, artifacts=[])
    append_run_record(path, r1)
    append_run_record(path, r2)
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [l["case"] for l in lines] == ["evals/test_replay.py::test_a",
                                          "evals/test_replay.py::test_b"]
    assert lines[0]["status"] == "passed" and lines[1]["status"] == "failed"
    assert lines[0]["durationMs"] == 1234
    assert lines[0]["artifacts"] == ["sessions/test_a"]
    assert all(l["schemaVersion"] == 1 for l in lines)


def test_build_run_record_rejects_unknown_status():
    with pytest.raises(ValueError):
        build_run_record(case="x", status="green", duration_ms=1, artifacts=[])
