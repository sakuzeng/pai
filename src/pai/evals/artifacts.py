"""评测工件索引（feature 32 T1）：runs.jsonl 逐行追加 + run 目录命名。

形态抄 pi evals 的 `.eval/<时间戳>/runs.jsonl`（K evals/pi-evals.md 第 3 节：
工件优先于展示——事后能重放/审计的评测才有积累价值）。pai 缩水两处并如实
声明：目录名不带 uuid（个人机器同秒重跑不是真实场景）、不做 0o600 权限
收紧（spec 非目标，记录即可）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

# 记录的合法状态。pytest 的三态之外别的词一律拒收——
# 「分数低」与「基建坏」分不开的评测没有积累价值（K evals/pi-evals.md）
_STATUSES = ("passed", "failed", "skipped")


def new_run_dir(base: Path, *, now: float = None) -> Path:  # type: ignore[assignment]
    """`<base>/<UTC 时间戳>/`：一次评测运行一个目录，名字可排序。"""
    stamp = time.strftime("%Y%m%dT%H%M%SZ",
                          time.gmtime(now if now is not None else time.time()))
    directory = base / stamp
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_run_record(*, case: str, status: str, duration_ms: int,
                     artifacts: List[str]) -> dict:
    if status not in _STATUSES:
        raise ValueError(f"未知评测状态 {status!r}（合法：{'/'.join(_STATUSES)}）")
    return {
        "schemaVersion": 1,
        "case": case,
        "status": status,
        "durationMs": duration_ms,
        "artifacts": list(artifacts),
    }


def append_run_record(path: Path, record: dict) -> None:
    """逐行追加（评测进程内串行，无并发写；跨进程跑批是 spec 非目标）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
