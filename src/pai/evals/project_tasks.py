"""Offline contracts for tasks in complete, pinned historical repositories."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import importlib.metadata
import platform
import sys
import tempfile
import ast
import shutil
import time
import uuid
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

from pai.evals.task_grading import Grade, _pytest, snapshot

EXCLUDED_ROOTS = frozenset({"knowledge", "refs", "evals", ".git", ".pai", ".claude",
                            ".codex", "pai_playground"})
INSTRUCTIONS = frozenset({"AGENTS.md", "PAI.md", "PAI.local.md", "CLAUDE.md", "CLAUDE.local.md"})
SPLITS = ("development", "holdout", "all")


@dataclass(frozen=True)
class ProjectCase:
    id: str
    kind: str
    split: str
    family: str
    commit: str
    prompt: str
    allowed: tuple[str, ...]
    root: Path
    config: dict


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "\\" not in value


def load_catalog(root: Path) -> list[ProjectCase]:
    cases: list[ProjectCase] = []
    families: dict[str, str] = {}
    for path in sorted(root.glob("*/case.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not re.fullmatch(r"[a-z][a-z0-9-]*", data["id"])
                or data["id"] != path.parent.name
                or data["kind"] not in ("locate", "fix", "tests")
                or data["split"] not in SPLITS[:2]
                or not re.fullmatch(r"[0-9a-f]{40}", data["commit"])
                or not data["prompt"].strip() or not data["family"]
                or not data["allowed"] or not all(safe_relative(p) for p in data["allowed"])):
            raise ValueError("Invalid historical case: " + str(path))
        grading_paths = list(data["regressions"])
        if data["kind"] == "locate":
            grading_paths.append(data["answer"]["path"])
            if data["allowed"] != ["answer.json"]:
                raise ValueError("Locate may only write answer.json")
        else:
            grading_paths.append(data["source"])
            if data["kind"] == "fix" and data["allowed"] != [data["source"]]:
                raise ValueError("Fix may only change its declared source")
            if data["kind"] == "tests" and any(
                    not p.startswith("tests/test_") or not p.endswith(".py") for p in data["allowed"]):
                raise ValueError("Test tasks may only add declared test files")
        if not all(safe_relative(p) for p in grading_paths):
            raise ValueError("Grading paths must stay inside the historical snapshot")
        if "reference_commit" in data and not re.fullmatch(r"[0-9a-f]{40}", data["reference_commit"]):
            raise ValueError("Reference commit must be a full immutable id")
        family = data["family"]
        if family in families and families[family] != data["split"]:
            raise ValueError("Problem family crosses splits: " + family)
        families[family] = data["split"]
        cases.append(ProjectCase(data["id"], data["kind"], data["split"], family,
                                 data["commit"], data["prompt"], tuple(data["allowed"]),
                                 path.parent.resolve(), data))
    if not cases:
        raise ValueError("Empty historical catalog")
    return cases


def select_cases(cases: list[ProjectCase], split: str = "development") -> list[ProjectCase]:
    if split not in SPLITS:
        raise ValueError("Unknown split: " + split)
    return [c for c in cases if split == "all" or c.split == split]


def excluded(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return (parts[0] in EXCLUDED_ROOTS or parts[:2] == ("docs", "dev")
            or parts[-1] in INSTRUCTIONS or parts[-1] == ".env"
            or any(p in ("__pycache__", ".pytest_cache") for p in parts))


def extract_archive(data: bytes, workspace: Path) -> list[str]:
    omitted: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            if (not safe_relative(member.name) or member.issym() or member.islnk()
                    or not (member.isdir() or member.isfile())):
                raise ValueError("Unsafe archive entry: " + member.name)
        workspace.mkdir(parents=True, exist_ok=False)
        for member in members:
            if excluded(member.name):
                if member.isfile():
                    omitted.append(member.name)
                continue
            target = workspace / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Archive file missing: " + member.name)
                target.write_bytes(source.read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return sorted(omitted)


def git_output(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], timeout=15)


def prepare_project(case: ProjectCase, repo: Path, workspace: Path) -> dict:
    tree = git_output(repo, "rev-parse", case.commit + "^{tree}").decode().strip()
    data = git_output(repo, "archive", "--format=tar", case.commit)
    omitted = extract_archive(data, workspace)
    subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", str(workspace)],
                   check=True, capture_output=True, timeout=10)
    return {"commit": case.commit, "tree": tree, "archiveHash": hashlib.sha256(data).hexdigest(),
            "files": snapshot(workspace), "excluded": omitted}


def install_reference(case: ProjectCase, workspace: Path) -> None:
    if case.kind == "locate":
        (workspace / "answer.json").write_text(json.dumps(case.config["answer"]), encoding="utf-8")
    elif case.kind == "fix":
        shutil.copyfile(case.root / "reference/source.py", workspace / case.config["source"])
    else:
        target = workspace / case.allowed[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(case.root / "reference/test_task_added.py", target)


def _passing(result: dict) -> bool:
    return (result["returncode"] == 0 and result["collected"] > 0
            and result["errors"] == 0 and result["failures"] == 0
            and result.get("skipped", 0) == 0)


def _score_process(case: ProjectCase, workspace: Path, run: Path, label: str,
                   tests: list[Path], deadline: float, variant: Path | None = None) -> dict:
    clean = run / (label.replace(":", "-") + "-" + uuid.uuid4().hex)
    shutil.copytree(workspace, clean, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    if variant is not None:
        shutil.copyfile(variant, clean / case.config["source"])
    suite = clean / "_external_grading"
    suite.mkdir()
    # The target tree's conftest must not configure the external oracle.
    (suite / "conftest.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "source = Path(__file__).resolve().parents[1] / 'src'\n"
        "sys.path.insert(0, str(source))\n"
        "sys.path.insert(1, str(source.parent / \'tests\'))\nimport pai\n"
        "assert Path(pai.__file__).resolve().is_relative_to(source.resolve()), 'wrong pai source'\n",
        encoding="utf-8")
    for index, test in enumerate(tests):
        target = suite / ("test_check_" + str(index) + ".py")
        rel = test.relative_to(workspace).as_posix() if test.is_relative_to(workspace) else None
        names = case.config.get("regression_select", {}).get(rel)
        if names:
            tree = ast.parse(test.read_text(encoding="utf-8"))
            found = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
            if not set(names) <= found:
                raise ValueError("Missing historical regression function")
            tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef)
                         or not n.name.startswith("test_") or n.name in names]
            target.write_text(ast.unparse(tree), encoding="utf-8")
        else:
            shutil.copyfile(test, target)
    result = _pytest(clean, suite, run / ("output-" + uuid.uuid4().hex), deadline)
    return {"check": label, **result}


def grade_project(case: ProjectCase, workspace: Path, baseline: dict,
                  artifact: Path, *, timeout: float = 30) -> Grade:
    workspace, artifact = workspace.resolve(), artifact.resolve()
    details: list[dict] = []
    deadline = time.monotonic() + timeout
    try:
        after = snapshot(workspace)
        before = baseline["files"]
        changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
        forbidden = sorted(p for p in changed if p not in case.allowed)
        if forbidden:
            return Grade("fail", [{"check": "protected_files", "changed": forbidden}])
        if case.kind == "locate":
            answer = json.loads((workspace / "answer.json").read_text(encoding="utf-8"))
            expected = case.config["answer"]
            source = workspace / expected["path"]
            symbols = {n.name for n in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            valid = answer == expected and expected["symbol"] in symbols
            return Grade("pass" if valid else "fail", [{"check": "answer", "actual": answer}])
        artifact.mkdir(parents=True, exist_ok=True)
        run = artifact / uuid.uuid4().hex
        run.mkdir()
        regressions = [workspace / p for p in case.config["regressions"]]
        if case.kind == "fix":
            external = sorted((case.root / "grader").glob("test_*.py"))
            if not external:
                raise ValueError("Missing external behavior tests")
            result = _score_process(case, workspace, run, "external_and_regressions",
                                    external + regressions, deadline)
            details.append(result)
            passed = _passing(result)
        else:
            added = [workspace / p for p in sorted(changed) if p in after]
            if not added or any(p in before for p in changed):
                return Grade("fail", [{"check": "new_tests", "error": "missing or existing file"}])
            mutants = sorted((case.root / "mutants").glob("*.py"))
            if not mutants:
                raise ValueError("Missing mutation probes")
            correct = _score_process(case, workspace, run, "candidate_correct", added, deadline)
            details.append(correct)
            passed = _passing(correct)
            if not passed:
                return Grade("fail", details)
            if regressions:
                result = _score_process(case, workspace, run, "regressions", regressions, deadline)
                details.append(result)
                passed &= _passing(result)
            for mutant in mutants:
                result = _score_process(case, workspace, run, "mutant:" + mutant.stem,
                                        added, deadline, mutant)
                details.append(result)
                passed &= (result["returncode"] == 1 and result["collected"] > 0
                           and result["errors"] == 0 and result.get("skipped", 0) == 0
                           and result["assertionFailures"] > 0)
        return Grade("pass" if passed else "fail", details)
    except TimeoutError as exc:
        return Grade("unavailable", details + [{"check": "deadline", "error": str(exc)}])
    except (OSError, ValueError, SyntaxError, KeyError) as exc:
        return Grade("fail", details + [{"check": "invalid_artifact", "error": str(exc)}])


HARNESS_ROOT = Path(__file__).resolve().parents[3]


def build_freeze(cases: list[ProjectCase], repo: Path, scratch: Path) -> dict:
    records: dict[str, dict] = {}
    for case in cases:
        before = prepare_project(case, repo, scratch / case.id)
        reference_commit = case.config.get("reference_commit")
        if reference_commit:
            expected = git_output(repo, "show", reference_commit + ":" + case.config["source"])
            if expected != (case.root / "reference/source.py").read_bytes():
                raise ValueError("Reference differs from historical fix: " + case.id)
        records[case.id] = {"split": case.split, "kind": case.kind, "family": case.family,
                            "prompt": case.prompt, "allowed": list(case.allowed),
                            "materials": snapshot(case.root), **before}
    harness = ["src/pai/evals/project_tasks.py", "src/pai/evals/task_grading.py", "eval.sh"]
    return {"schema": 1, "kind": "reference_contract", "newModelCalls": 0,
            "python": platform.python_version(),
            "dependencies": {name: importlib.metadata.version(name)
                             for name in ("pytest", "openai", "python-dotenv")},
            "harnessHashes": {name: hashlib.sha256((HARNESS_ROOT / name).read_bytes()).hexdigest()
                              for name in harness},
            "cases": records}


def check_freeze(cases: list[ProjectCase], repo: Path, frozen_path: Path, scratch: Path) -> None:
    if not frozen_path.is_file():
        raise ValueError("Missing freeze; explicitly validate all cases before freezing")
    expected = json.loads(frozen_path.read_text(encoding="utf-8"))
    current = build_freeze(cases, repo, scratch)
    expected["cases"] = {c.id: expected["cases"].get(c.id) for c in cases}
    if current != expected:
        raise ValueError("Historical task freeze drift; do not refresh implicitly")


def preflight(cases: list[ProjectCase], repo: Path, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict] = []
    for case in cases:
        directory = output / case.id
        directory.mkdir()
        workspace = directory / "workspace"
        before = prepare_project(case, repo, workspace)
        (directory / "snapshot.json").write_text(
            json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
        original = grade_project(case, workspace, before, directory / "original")
        install_reference(case, workspace)
        reference = grade_project(case, workspace, before, directory / "reference", timeout=45)
        initial_valid = original.status == "fail"
        if case.kind == "fix":
            initial_valid &= any(d.get("assertionFailures", 0) > 0 and d.get("errors", 0) == 0
                                 for d in original.details)
        rows.append({"id": case.id, "kind": case.kind, "split": case.split,
                     "original": asdict(original), "reference": asdict(reference),
                     "referenceContractPassed": initial_valid and reference.status == "pass"})
    report = {"kind": "reference_contract", "newModelCalls": 0, "cases": rows}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Historical task reference contracts", "",
             "Offline validation only; these are not model task successes.", "",
             "| Case | Split | Original | Reference | Contract |",
             "|---|---|---|---|---|"]
    lines += ["| {id} | {split} | {original} | {reference} | {passed} |".format(
        id=r["id"], split=r["split"], original=r["original"]["status"],
        reference=r["reference"]["status"], passed=r["referenceContractPassed"]) for r in rows]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline historical task reference contracts; no model calls")
    parser.add_argument("--split", choices=SPLITS, default="development")
    parser.add_argument("--repo", type=Path, default=HARNESS_ROOT)
    parser.add_argument("--catalog", type=Path, default=HARNESS_ROOT / "evals/project_tasks")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--freeze", action="store_true", help="validate --split all, then explicitly write freeze")
    args = parser.parse_args(argv)
    if args.freeze and args.split != "all":
        parser.error("--freeze requires explicit --split all")
    output = args.output or (HARNESS_ROOT / "pai_playground/project-task-evals" /
                             (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]))
    try:
        cases = select_cases(load_catalog(args.catalog), args.split)
        if not cases:
            raise ValueError("Empty selected split")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pai-history-freeze-", dir=output.parent) as directory:
            scratch = Path(directory)
            if not args.freeze:
                check_freeze(cases, args.repo, args.catalog / "freeze.json", scratch / "check")
            report = preflight(cases, args.repo, output)
            if not all(r["referenceContractPassed"] for r in report["cases"]):
                print("Reference contracts failed: " + str(output), file=sys.stderr)
                return 1
            if args.freeze:
                frozen = build_freeze(cases, args.repo, scratch / "freeze")
                (args.catalog / "freeze.json").write_text(
                    json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Offline reference contracts: " + str(output / "report.json"))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
