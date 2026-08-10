"""拍平 vs 原样发实测（spec 问 1/问 3，用户已授权 ≤1 元）。

跑法：./test.sh --llm（需 DEEPSEEK_API_KEY + PAI_RUN_LLM_TESTS=1）。
原始请求/响应/usage 归档进功能目录 evidence/，裁决进 decisions——数据可查证原件。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from pai.config import make_client, model_name
from pai.core.compaction import summarize
from test_compaction import REAL_TRAJECTORY

EVIDENCE = (Path(__file__).resolve().parent.parent / "docs" / "dev" / "features"
            / "02-20260803-compaction" / "evidence")

pytestmark = pytest.mark.llm


@pytest.mark.parametrize("style", ["flat", "raw"])
def test_summarize_experiment(style):
    client, model = make_client(), model_name()
    out_dir = EVIDENCE / f"{time.strftime('%Y%m%d')}-拍平vs原样发实测"
    out_dir.mkdir(parents=True, exist_ok=True)
    for run in range(3):
        text, usage = summarize(REAL_TRAJECTORY, client=client, model=model, style=style)
        (out_dir / f"{style}-run{run}.json").write_text(
            json.dumps({"style": style, "run": run, "summary": text, "usage": usage},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        assert text.strip(), f"{style} run{run} 摘要为空"
