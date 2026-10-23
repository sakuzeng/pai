"""独立任务进程的生命周期与持久工件。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping

from pai.evals.artifacts import append_run_record, build_run_record
from pai.evals.task_grading import TaskCase, grade, prepare, snapshot
from pai.evals.task_metrics import measure, summarize

SRC = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Limits:
    steps: int = 20
    tokens: int = 200000
    seconds: float = 180
    batch_seconds: float = 1200

    def __post_init__(self) -> None:
        if min(self.steps, self.tokens, self.seconds, self.batch_seconds) <= 0:
            raise ValueError("评测预算必须为正")


def build_env(home: Path, tmp: Path, credentials: dict[str, str], model: str) -> dict[str, str]:
    return {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "HOME": str(home), "TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp),
            "PYTHONPATH": str(SRC), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
            "PYTHON_DOTENV_DISABLED": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "DEEPSEEK_API_KEY": credentials["api_key"], "PAI_BASE_URL": credentials["base_url"],
            "PAI_MODEL": model, "PAI_CONTEXT_WINDOW": "1000000"}


def _stop(proc: subprocess.Popen) -> bool:
    if proc.poll() is not None:
        return True
    # 工具自己 setsid；强杀 worker 的组不足以回收这些子孙，必须在其父亲消失前取图。
    groups = {proc.pid}
    verified = True
    try:
        output = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid="], check=True,
                                capture_output=True, text=True, timeout=1).stdout
        rows = [tuple(map(int, line.split())) for line in output.splitlines() if line.strip()]
        descendants = {proc.pid}
        changed = True
        while changed:
            changed = False
            for pid, parent, group in rows:
                if parent in descendants and pid not in descendants:
                    descendants.add(pid)
                    groups.add(group)
                    changed = True
    except (OSError, ValueError, subprocess.SubprocessError):
        verified = False
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    finally:
        for group in groups:
            if group <= 1 or group == os.getpgrp():
                continue
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                verified = False
        proc.wait()
    return verified


def _check_ancestors(workspace: Path) -> None:
    for ancestor in workspace.parents:
        for name in ("AGENTS.md", "PAI.md", "PAI.local.md", ".env"):
            if (ancestor / name).is_file():
                raise ValueError("隔离执行目录有外部祖先配置：" + str(ancestor / name))


def run_one(case: TaskCase, artifact: Path, *, scratch_root: Path,
            credentials: dict[str, str], model: str = "deepseek-flash",
            limits: Limits = Limits()) -> dict:
    started = time.monotonic()
    deadline = started + limits.seconds
    artifact.mkdir(parents=True)
    scratch_root.mkdir(parents=True, exist_ok=True)
    artifact = artifact.resolve()
    result: dict = {"case": case.id, "execution": "harness_error", "agentEnd": "unknown",
                    "grade": {"status": "unavailable", "details": []}}
    with tempfile.TemporaryDirectory(prefix="pai-task-", dir=scratch_root) as temporary:
        root = Path(temporary)
        workspace, home, tmp = root / "workspace", root / "home", root / "tmp"
        _check_ancestors(workspace)
        before = prepare(case, workspace)
        home.mkdir(); tmp.mkdir()
        settings = home / ".pai" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"tests": {"command": shlex.quote(sys.executable)
            + " -B -m pytest -q -p no:cacheprovider", "timeoutSeconds": max(1, int(limits.seconds))}}), encoding="utf-8")
        env = build_env(home, tmp, credentials, model)
        config = {"prompt": case.prompt, "model": model, "max_steps": limits.steps,
                  "max_tokens": limits.tokens, "seconds": limits.seconds,
                  "trace": str(artifact / "trace.jsonl"), "result": str(artifact / "worker.json"),
                  "workspace": str(workspace), "home": str(home), "permissionMode": "acceptEdits",
                  "limits": asdict(limits), "baseline": before, "backendRevision": "unknown"}
        input_path = artifact / "input.json"
        input_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        agent_start = time.monotonic()
        with (artifact / "stdout.txt").open("w") as out, (artifact / "stderr.txt").open("w") as err:
            proc = subprocess.Popen([sys.executable, "-B", "-m", "pai.evals.task_worker", str(input_path)],
                                    cwd=workspace, env=env, stdout=out, stderr=err, start_new_session=True)
            try:
                proc.wait(timeout=max(0.001, deadline - time.monotonic() - 1))
            except subprocess.TimeoutExpired:
                result["execution"] = "timeout"
            except KeyboardInterrupt:
                result["execution"] = "interrupted"
            except BaseException:
                _stop(proc)
                raise
            finally:
                result["cleanupVerified"] = _stop(proc)
        result["durationMs"] = round((time.monotonic() - agent_start) * 1000)
        result["returncode"] = proc.returncode
        if result["execution"] not in ("timeout", "interrupted") and (artifact / "worker.json").exists():
            worker = json.loads((artifact / "worker.json").read_text(encoding="utf-8"))
            result.update(worker)
            if proc.returncode and result["execution"] == "completed":
                result["execution"] = "harness_error"
        sessions = artifact / "sessions"
        sessions.mkdir()
        for path in home.glob(".pai/projects/*/sessions/*.jsonl"):
            shutil.copyfile(path, sessions / path.name)
        # 动态运行目录不继承 pai 仓库的 AGENTS；产物完整保存到调用者的持久目录。
        shutil.copytree(workspace, artifact / "workspace", symlinks=True)
        paths = [p for p in sessions.glob("*.jsonl") if not p.name.endswith(".events.jsonl")]
        try:
            metrics = measure(paths[0] if len(paths) == 1 else None,
                              artifact / "trace.events.jsonl" if (artifact / "trace.events.jsonl").exists() else None)
            result["metrics"] = metrics
            result["agentEnd"] = metrics["agentEnd"]
        except (ValueError, KeyError, TypeError) as exc:
            result.update(execution="harness_error", metricsError=type(exc).__name__)
        grading_start = time.monotonic()
        remaining = deadline - grading_start
        if result["execution"] == "completed" and remaining > 0:
            scored = grade(case, workspace, before, artifact / "grading", timeout=min(20, remaining))
            result["grade"] = asdict(scored)
        if result["grade"]["status"] == "unavailable" and result["execution"] == "completed":
            result["execution"] = "harness_error"
        if not result["cleanupVerified"]:
            result["execution"] = "harness_error"
        result["gradingDurationMs"] = round((time.monotonic() - grading_start) * 1000)
    result["totalDurationMs"] = round((time.monotonic() - started) * 1000)
    (artifact / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def require_llm(env: Mapping[str, str]) -> dict[str, str]:
    key = env.get("DEEPSEEK_API_KEY", "")
    if env.get("PAI_RUN_LLM_TESTS") != "1" or not key or key.startswith("sk-在这里"):
        raise ValueError("真实任务评测需要 DEEPSEEK_API_KEY 和 PAI_RUN_LLM_TESTS=1；使用 ./eval.sh --tasks --llm")
    return {"api_key": key, "base_url": env.get("PAI_BASE_URL", "https://api.deepseek.com")}


def _hash_tree(root: Path) -> str:
    data = json.dumps(snapshot(root), sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def _report(records: list[dict], summary: dict) -> str:
    text = "# 任务基线报告\n\n"
    text += f"计划 {summary['planned']} 次，启动 {summary['started']} 次；完整成功 {summary['completeSuccesses']} 次，产物通过 {summary['productPasses']} 次。\n\n"
    text += f"完整成功率 {summary['completeSuccessRate']:.1%}，产物通过率 {summary['productPassRate']:.1%}。\n\n"
    text += "小型构造任务的首轮基线，不外推实际仓库能力。真人弹窗不适用；缺 usage 是未知，主请求用量不等于全部计费。\n\n"
    text += "| 任务 | 次数 | 执行 | agent 结束 | 产物 | 耗时 ms | 已报告 token | 工具尝试/执行/拒绝 |\n|---|---|---|---|---|---|---|---|\n"
    for r in records:
        m = r.get("metrics", {})
        counts = "/".join(str(m.get(k, "unknown")) for k in ("toolAttempts", "toolsStarted", "permissionDenials"))
        text += f"| {r['case']} | {r['repetition']} | {r['execution']} | {r.get('agentEnd', 'unknown')} | {r['grade']['status']} | {r.get('durationMs', 'unknown')} | {m.get('tokens', {}).get('total', 'unknown')} | {counts} |\n"
    text += "\n逐次结果见 task-results.jsonl，配置/哈希见 manifest.json；每个 trial 含原始会话、事件、输出、评分与最终工作区。\n"
    return text


def run_batch(cases: list[TaskCase], output: Path, *, scratch_root: Path,
              credentials: dict[str, str], model: str = "deepseek-flash",
              repetitions: int = 3, limits: Limits = Limits(),
              run_trial: Callable[..., dict] = run_one,
              now: Callable[[], float] = time.monotonic) -> dict:
    if repetitions < 1 or not cases:
        raise ValueError("需要案例和正采样数")
    output.mkdir(parents=True)
    repo = SRC.parent
    rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         text=True, capture_output=True, check=True, timeout=5).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--short"],
                           text=True, capture_output=True, check=True, timeout=5).stdout.splitlines()
    manifest = {"schemaVersion": 1, "model": model, "backendRevision": "unknown",
                "endpoint": credentials["base_url"], "permissionMode": "acceptEdits",
                "limits": asdict(limits), "repetitions": repetitions, "sourceRev": rev,
                "dirtyStatus": dirty, "codeHash": _hash_tree(SRC), "python": sys.version,
                "dependencies": {p: importlib.metadata.version(p) for p in ("openai", "python-dotenv", "pytest")},
                "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "cases": [{"id": c.id, "prompt": c.prompt, "hash": _hash_tree(c.root)} for c in cases]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    deadline = now() + limits.batch_seconds
    records: list[dict] = []
    halted = False
    for case in cases:
        for repetition in range(1, repetitions + 1):
            remaining = deadline - now()
            name = f"{case.id}-{repetition}"
            if remaining <= 0 or halted:
                result = {"case": case.id, "execution": "not_started", "agentEnd": "unknown",
                          "grade": {"status": "unavailable", "details": [{"check": "interrupted" if halted else "batch_deadline"}]}}
            else:
                try:
                    result = run_trial(case, output / name, scratch_root=scratch_root,
                        credentials=credentials, model=model,
                        limits=replace(limits, seconds=min(limits.seconds, remaining)))
                except KeyboardInterrupt:
                    result = {"case": case.id, "execution": "interrupted", "agentEnd": "unknown",
                              "grade": {"status": "unavailable", "details": []}}
                except Exception as exc:
                    result = {"case": case.id, "execution": "harness_error", "agentEnd": "unknown",
                              "errorType": type(exc).__name__, "grade": {"status": "unavailable", "details": []}}
            if result["execution"] == "interrupted":
                halted = True
            result["repetition"] = repetition
            result["artifact"] = name
            records.append(result)
            append_run_record(output / "task-results.jsonl", result)
            success = (result["execution"] == "completed" and result.get("agentEnd") == "final"
                       and result["grade"]["status"] == "pass")
            append_run_record(output / "runs.jsonl", build_run_record(case=name,
                status="passed" if success else "skipped" if result["execution"] == "not_started" else "failed",
                duration_ms=result.get("totalDurationMs", 0), artifacts=[name] if (output / name).exists() else []))
            summary = summarize(records)
            (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "report.md").write_text(_report(records, summary), encoding="utf-8")
    if halted:
        raise KeyboardInterrupt()
    return summarize(records)
