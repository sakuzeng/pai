"""显式 --tasks 入口；文件名不被旧 eval 默认收集。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid

import pytest

from pai.evals.task_grading import grade, load_case, prepare
from pai.evals.task_runner import require_llm, run_batch

REPO = Path(__file__).resolve().parents[1]
CASES = [load_case(REPO / "evals/tasks" / n) for n in ("locate", "fix", "tests")]


def test_catalog_contract(tmp_path: Path) -> None:
    for case in CASES:
        directory = tmp_path / case.id
        directory.mkdir()
        ws = directory / "workspace"
        before = prepare(case, ws)
        assert grade(case, ws, before, directory / "initial").status == "fail"
        if case.id == "locate":
            (ws / "answer.json").write_text('{"path":"text_rules.py","function":"slugify"}')
        elif case.id == "fix":
            shutil.copyfile(case.root / "reference/pagination.py", ws / "pagination.py")
        else:
            shutil.copyfile(case.root / "reference/test_clip.py", ws / "tests/test_clip.py")
        scored = grade(case, ws, before, directory / "reference")
        assert scored.status == "pass", scored.details


@pytest.mark.llm
@pytest.mark.skipif(not (os.environ.get("PAI_RUN_LLM_TESTS") == "1"
                        and os.environ.get("DEEPSEEK_API_KEY")
                        and not os.environ["DEEPSEEK_API_KEY"].startswith("sk-在这里")),
                    reason="需要真实 key 和显式 ./eval.sh --tasks --llm")
def test_real_task_baseline(tmp_path: Path, eval_artifact_dir: Path) -> None:
    credentials = require_llm(os.environ)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    output = REPO / "pai_playground/task-evals" / stamp
    summary = run_batch(CASES, output, scratch_root=Path(tempfile.gettempdir()), credentials=credentials)
    (eval_artifact_dir / "task-run.json").write_text(
        json.dumps({"output": str(output), "summary": summary}, ensure_ascii=False, indent=2))
    print("任务报告：" + str(output / "report.md"))
    assert summary["planned"] == 9
    # 不要求模型九次全胜；pytest 验的是设施，任务质量见完整结果和两个通过口径。
    assert not any(summary["executionCounts"].get(k, 0)
                   for k in ("harness_error",)), summary
