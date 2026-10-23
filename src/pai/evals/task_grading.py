"""固定任务与外部世界评分；不根据 agent 自述判分。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Optional
import uuid
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TaskCase:
    id: str
    prompt: str
    root: Path


@dataclass(frozen=True)
class Grade:
    status: str
    details: list[dict]


def load_case(root: Path) -> TaskCase:
    data = json.loads((root / "case.json").read_text(encoding="utf-8"))
    if data["id"] not in ("locate", "fix", "tests") or not data["prompt"]:
        raise ValueError("未知或空任务")
    return TaskCase(data["id"], data["prompt"], root.resolve())


def snapshot(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in (".git", "__pycache__", ".pytest_cache") for p in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError("工作区含软链：" + str(rel))
        if path.is_file():
            files[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def prepare(case: TaskCase, workspace: Path) -> dict[str, str]:
    shutil.copytree(case.root / "workspace", workspace)
    subprocess.run(["git", "init", "-q", str(workspace)], check=True,
                   capture_output=True, timeout=10)
    return snapshot(workspace)


def _allowed(case: TaskCase, path: str, baseline: dict[str, str]) -> bool:
    if case.id == "locate":
        return path == "answer.json"
    if case.id == "fix":
        return path == "pagination.py"
    p = Path(path)
    return (p.parent == Path("tests") and p.name.startswith("test_")
            and p.suffix == ".py" and path not in baseline)


def _pytest(workspace: Path, target: Path, artifact: Path,
            deadline: float) -> dict:
    artifact.mkdir(parents=True)
    report = artifact / "junit.xml"
    home = artifact / "home"
    home.mkdir()
    env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home),
           "PYTHONPATH": str(workspace), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHON_DOTENV_DISABLED": "1"}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("评分期限耗尽")
    proc = subprocess.Popen([sys.executable, "-B", "-m", "pytest", "-q",
                             "-c", os.devnull, "--confcutdir=" + str(workspace),
                             "-p", "no:cacheprovider", "--junitxml=" + str(report),
                             str(target)], cwd=workspace, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = proc.communicate()
        (artifact / "output.txt").write_text(output, encoding="utf-8")
        raise TimeoutError("评分子进程超时")
    (artifact / "output.txt").write_text(output, encoding="utf-8")
    if not report.is_file():
        return {"returncode": proc.returncode, "collected": 0, "failures": 0,
                "errors": 1, "assertionFailures": 0}
    xml = ET.parse(report)
    tests = xml.findall(".//testcase")
    failures = [f for t in tests for f in t.findall("failure")]
    return {"returncode": proc.returncode, "collected": len(tests),
            "failures": len(failures),
            "errors": sum(len(t.findall("error")) for t in tests),
            "skipped": sum(len(t.findall("skipped")) for t in tests),
            "assertionFailures": sum(bool(re.search(r": AssertionError(?:$|:)", (f.text or "").strip().split("\n")[-1]))
                or ("DID NOT RAISE" in f.get("message", "")) for f in failures)}


def grade(case: TaskCase, workspace: Path, baseline: dict[str, str],
          artifact: Path, *, timeout: float = 20) -> Grade:
    deadline = time.monotonic() + timeout
    details: list[dict] = []
    try:
        after = snapshot(workspace)
    except ValueError as exc:
        return Grade("fail", [{"check": "paths", "error": str(exc)}])
    changed = sorted(k for k in set(after) | set(baseline)
                     if after.get(k) != baseline.get(k))
    forbidden = [p for p in changed if not _allowed(case, p, baseline)]
    if forbidden:
        return Grade("fail", [{"check": "protected_files", "changed": forbidden}])
    artifact.mkdir(parents=True, exist_ok=True)
    run = artifact / uuid.uuid4().hex
    run.mkdir()
    if case.id == "locate":
        try:
            answer = json.loads((workspace / "answer.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return Grade("fail", [{"check": "answer", "error": str(exc)}])
        passed = answer == {"path": "text_rules.py", "function": "slugify"}
        return Grade("pass" if passed else "fail", [{"check": "answer", "actual": answer}])
    clean = run / "workspace"
    shutil.copytree(case.root / "workspace", clean)
    try:
        if case.id == "fix":
            if not (workspace / "pagination.py").is_file():
                return Grade("fail", [{"check": "implementation", "error": "missing"}])
            shutil.copyfile(workspace / "pagination.py", clean / "pagination.py")
            external = clean / "test_external.py"
            shutil.copyfile(case.root / "grader" / "test_external.py", external)
            result = _pytest(clean, external, run / "correct", deadline)
            details.append({"check": "external_tests", **result})
            passed = result["returncode"] == 0 and result["collected"] >= 8 and result["skipped"] == 0
        else:
            added = [p for p in changed if p in after and _allowed(case, p, baseline)]
            if not added:
                return Grade("fail", [{"check": "new_tests", "error": "missing"}])
            for p in added:
                shutil.copyfile(workspace / p, clean / p)
            variants: list[Optional[Path]] = [None] + sorted((case.root / "grader" / "mutants").glob("*.py"))
            if len(variants) < 2:
                raise ValueError("评分器没有错误实现")
            passed = True
            for variant in variants:
                label = variant.stem if variant else "correct"
                source = variant or (case.root / "workspace" / "ranges.py")
                shutil.copyfile(source, clean / "ranges.py")
                result = _pytest(clean, clean / "tests", run / label, deadline)
                details.append({"check": label, **result})
                if variant is None:
                    passed &= (result["returncode"] == 0 and result["collected"] > 0
                               and result["skipped"] == 0)
                else:
                    passed &= (result["returncode"] == 1 and result["errors"] == 0
                               and result["assertionFailures"] > 0)
        return Grade("pass" if passed else "fail", details)
    except TimeoutError as exc:
        return Grade("unavailable", details + [{"check": "deadline", "error": str(exc)}])
