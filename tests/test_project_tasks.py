"""Historical repository snapshots and external task contracts."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tarfile
import io

import pytest

from pai.evals.project_tasks import ProjectCase, load_catalog, prepare_project, select_cases, extract_archive

REPO = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def catalog(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "-q")
    files = {
        "src/pai/__init__.py": "",
        "src/pai/subject.py": "def boundary(value):\n    return value > 0\n",
        "tests/conftest.py": "raise RuntimeError(\'historical conftest must not load\')\
",
        "tests/test_existing.py": "from pai.subject import boundary\ndef test_existing():\n    assert boundary(2)\n",
        "pyproject.toml": "[project]\nname='history-fixture'\nversion='0.0.0'\n",
        "docs/dev/answer.md": "hidden solution",
        "knowledge/answer.md": "hidden source notes",
        "AGENTS.md": "inherited instructions",
        ".pai/settings.json": "{}",
    }
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "fixture")
    commit = git(repo, "rev-parse", "HEAD")
    root = tmp_path / "catalog"
    for split in ("development", "holdout"):
        directory = root / (split + "-locate")
        directory.mkdir(parents=True)
        config = {"id": directory.name, "kind": "locate", "split": split,
                  "family": split + "-family", "commit": commit,
                  "prompt": "Find boundary; write answer.json. Do not change other files.",
                  "answer": {"path": "src/pai/subject.py", "symbol": "boundary"},
                  "allowed": ["answer.json"], "regressions": []}
        (directory / "case.json").write_text(json.dumps(config))
    return repo, root


def test_snapshot_keeps_complete_source_tests_and_build_config(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    repo, root = catalog
    case = load_catalog(root)[0]
    before = prepare_project(case, repo, tmp_path / "workspace")
    assert {"src/pai/subject.py", "tests/test_existing.py", "pyproject.toml"} <= set(before["files"])
    assert "docs/dev/answer.md" in before["excluded"]
    assert "knowledge/answer.md" in before["excluded"]
    assert not (tmp_path / "workspace/AGENTS.md").exists()
    assert not (tmp_path / "workspace/.pai").exists()
    assert before["commit"] == git(repo, "rev-parse", "HEAD")
    assert before["tree"] == git(repo, "rev-parse", "HEAD^{tree}")
    assert (tmp_path / "workspace/.git").is_dir()


def test_snapshot_uses_committed_content_not_dirty_worktree(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    repo, root = catalog
    (repo / "src/pai/subject.py").write_text("dirty")
    prepare_project(load_catalog(root)[0], repo, tmp_path / "workspace")
    assert "def boundary" in (tmp_path / "workspace/src/pai/subject.py").read_text()


def test_default_selection_keeps_holdout_explicit(catalog: tuple[Path, Path]) -> None:
    cases = load_catalog(catalog[1])
    assert [c.split for c in select_cases(cases)] == ["development"]
    assert [c.split for c in select_cases(cases, "holdout")] == ["holdout"]
    assert len(select_cases(cases, "all")) == 2
    with pytest.raises(ValueError):
        select_cases(cases, "unknown")


def test_catalog_rejects_cross_split_problem_family(catalog: tuple[Path, Path]) -> None:
    root = catalog[1]
    path = root / "holdout-locate/case.json"
    data = json.loads(path.read_text())
    data["family"] = "development-family"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="family"):
        load_catalog(root)


@pytest.mark.parametrize("name,symlink", [("../escape", False), ("/absolute", False), ("link", True)])
def test_archive_rejects_traversal_and_links(tmp_path: Path, name: str, symlink: bool) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = "../escape"
        archive.addfile(member)
    with pytest.raises(ValueError):
        extract_archive(stream.getvalue(), tmp_path / "workspace")


def test_catalog_rejects_revision_and_allowed_path_injection(catalog: tuple[Path, Path]) -> None:
    path = catalog[1] / "development-locate/case.json"
    data = json.loads(path.read_text())
    data["commit"] = "--output=/tmp/escape"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_catalog(catalog[1])
    data["commit"] = git(catalog[0], "rev-parse", "HEAD")
    data["allowed"] = ["../escape"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_catalog(catalog[1])

def scoring_case(catalog: tuple[Path, Path], kind: str) -> ProjectCase:
    repo, root = catalog
    directory = root / "development-locate"
    path = directory / "case.json"
    data = json.loads(path.read_text())
    data.update(kind=kind, source="src/pai/subject.py",
                allowed=["src/pai/subject.py"] if kind == "fix" else ["tests/test_task_added.py"],
                regressions=["tests/test_existing.py"])
    path.write_text(json.dumps(data))
    reference = directory / "reference"
    reference.mkdir()
    if kind == "fix":
        (reference / "source.py").write_text("def boundary(value):\n    return value >= 0\n")
        external = directory / "grader"
        external.mkdir()
        (external / "test_external.py").write_text(
            "from pai.subject import boundary\ndef test_zero():\n    assert boundary(0)\n"
            "def test_positive():\n    assert boundary(3)\n"
            "def test_negative():\n    assert not boundary(-1)\n")
    else:
        (reference / "test_task_added.py").write_text(
            "from pai.subject import boundary\ndef test_behavior():\n"
            "    assert boundary(1)\n    assert not boundary(0)\n    assert not boundary(-1)\n")
        mutants = directory / "mutants"
        mutants.mkdir()
        (mutants / "zero.py").write_text("def boundary(value):\n    return value >= 0\n")
        (mutants / "reversed.py").write_text("def boundary(value):\n    return value < 0\n")
    return next(c for c in load_catalog(root) if c.split == "development")


def test_external_grader_checks_artifacts_and_source(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    case = load_catalog(catalog[1])[0]
    ws = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], ws)
    assert grade_project(case, ws, before, tmp_path / "missing").status == "fail"
    install_reference(case, ws)
    assert grade_project(case, ws, before, tmp_path / "valid").status == "pass"
    (ws / "src/pai/subject.py").write_text("altered")
    assert grade_project(case, ws, before, tmp_path / "protected").status == "fail"


def test_fix_original_fails_reference_passes_in_historical_source(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    case = scoring_case(catalog, "fix")
    ws = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], ws)
    initial = grade_project(case, ws, before, tmp_path / "original")
    assert initial.status == "fail"
    assert initial.details[0]["assertionFailures"] > 0
    install_reference(case, ws)
    scored = grade_project(case, ws, before, tmp_path / "reference")
    assert scored.status == "pass", scored.details


@pytest.mark.parametrize("bad", ["", "def test_empty():\n    pass\n",
                                      "import pytest\n@pytest.mark.skip\ndef test_skip():\n    assert False\n",
                                      "import nonexistent_dependency\n"])
def test_new_tests_cannot_pass_empty_skipped_or_import_errors(catalog: tuple[Path, Path], tmp_path: Path, bad: str) -> None:
    from pai.evals.project_tasks import grade_project
    case = scoring_case(catalog, "tests")
    ws = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], ws)
    (ws / "tests/test_task_added.py").write_text(bad)
    assert grade_project(case, ws, before, tmp_path / "bad").status == "fail"


def test_reference_tests_must_kill_each_mutant_themselves(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    case = scoring_case(catalog, "tests")
    ws = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], ws)
    install_reference(case, ws)
    result = grade_project(case, ws, before, tmp_path / "score")
    assert result.status == "pass", result.details
    mutant_checks = [d for d in result.details if d["check"].startswith("mutant:")]
    assert len(mutant_checks) == 2
    assert all(d["assertionFailures"] > 0 for d in mutant_checks)


def test_deleted_test_and_symlink_are_rejected(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    case = scoring_case(catalog, "tests")
    ws = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], ws)
    install_reference(case, ws)
    (ws / "tests/test_existing.py").unlink()
    assert grade_project(case, ws, before, tmp_path / "deleted").status == "fail"
    (ws / "tests/test_existing.py").write_bytes((catalog[0] / "tests/test_existing.py").read_bytes())
    (ws / "tests/test_task_added.py").unlink()
    (ws / "tests/test_task_added.py").symlink_to("/etc/passwd")
    assert grade_project(case, ws, before, tmp_path / "symlink").status == "fail"

ACTUAL_CASE_IDS = ["dev-locate-compaction","dev-fix-path-key","dev-tests-queue","holdout-locate-stream","holdout-fix-resume","holdout-tests-boundary"]


@pytest.mark.parametrize("case_id", ACTUAL_CASE_IDS)
def test_real_historical_task_reference_contract(case_id: str, tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    cases = load_catalog(REPO / "evals/project_tasks")
    assert len(cases) == 6
    case = next(c for c in cases if c.id == case_id)
    ws = tmp_path / "candidate"
    before = prepare_project(case, REPO, ws)
    assert len([p for p in before["files"] if p.startswith("src/")]) > 30
    assert len([p for p in before["files"] if p.startswith("tests/")]) > 20
    initial = grade_project(case, ws, before, tmp_path / "original")
    assert initial.status == "fail", initial.details
    if case.kind == "fix":
        assert initial.details[0].get("assertionFailures", 0) > 0, initial.details
    install_reference(case, ws)
    final = grade_project(case, ws, before, tmp_path / "reference", timeout=45)
    assert final.status == "pass", final.details
    if case.kind == "fix":
        expected = git(REPO, "show", case.config["reference_commit"] + ":" + case.config["source"])
        assert (case.root / "reference/source.py").read_text().rstrip() == expected.rstrip()


def test_freeze_detects_catalog_runtime_and_snapshot_drift(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import build_freeze, check_freeze
    repo, root = catalog
    frozen = build_freeze(load_catalog(root), repo, tmp_path / "freeze-build")
    (root / "freeze.json").write_text(json.dumps(frozen))
    check_freeze(load_catalog(root), repo, root / "freeze.json", tmp_path / "valid")
    changed = json.loads(json.dumps(frozen))
    changed["harnessHashes"]["src/pai/evals/project_tasks.py"] = "0" * 64
    (root / "freeze.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="drift"):
        check_freeze(load_catalog(root), repo, root / "freeze.json", tmp_path / "bad-code")
    (root / "freeze.json").write_text(json.dumps(frozen))
    p = root / "development-locate/case.json"
    data = json.loads(p.read_text())
    data["prompt"] += " changed"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="drift"):
        check_freeze(load_catalog(root), repo, root / "freeze.json", tmp_path / "bad-case")


def test_offline_report_marks_reference_contract_not_model_success(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import preflight
    cases = select_cases(load_catalog(catalog[1]))
    report = preflight(cases, catalog[0], tmp_path / "report")
    assert report["kind"] == "reference_contract"
    assert report["newModelCalls"] == 0
    assert len(report["cases"]) == 1
    assert report["cases"][0]["referenceContractPassed"]
    assert report["cases"][0]["split"] == "development"
    assert "completeSuccess" not in report
    assert "modelSuccess" not in report


def test_project_cli_default_and_explicit_holdout_selection(catalog: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pai.evals import project_tasks as module
    invoked = []
    monkeypatch.setattr(module, "check_freeze", lambda *args: None)
    def fake_preflight(cases: list[ProjectCase], repo: Path, output: Path) -> dict:
        invoked.append([c.split for c in cases])
        return {"cases": [{"referenceContractPassed": True} for c in cases]}
    monkeypatch.setattr(module, "preflight", fake_preflight)
    args = ["--repo", str(catalog[0]), "--catalog", str(catalog[1]), "--output", str(tmp_path / "run")]
    assert module.main(args) == 0
    assert invoked == [["development"]]
    assert module.main(args + ["--split", "holdout"]) == 0
    assert invoked[-1] == ["holdout"]


def test_project_cli_rejects_paid_flag_and_missing_freeze(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import main
    args = ["--repo", str(catalog[0]), "--catalog", str(catalog[1]), "--output", str(tmp_path / "run")]
    with pytest.raises(SystemExit) as error:
        main(args + ["--llm"])
    assert error.value.code == 2
    assert main(args) == 2
    assert not (tmp_path / "run").exists()


def test_default_eval_does_not_collect_historical_grader_tests() -> None:
    result = subprocess.run([str(REPO / "eval.sh"), "--collect-only", "-q"],
                            cwd=REPO, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "project_tasks/" not in result.stdout


def test_project_shell_entry_runs_offline_module() -> None:
    result = subprocess.run([str(REPO / "eval.sh"), "--project-tasks", "--help"],
                            cwd=REPO, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--split" in result.stdout
    assert "--freeze" in result.stdout


def test_catalog_rejects_grading_paths_outside_snapshot(catalog: tuple[Path, Path]) -> None:
    path = catalog[1] / "development-locate/case.json"
    data = json.loads(path.read_text())
    data["answer"]["path"] = "/etc/passwd"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_catalog(catalog[1])


def test_grading_deadline_is_unavailable_not_artifact_failure(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import grade_project, install_reference
    case = scoring_case(catalog, "fix")
    workspace = tmp_path / "candidate"
    before = prepare_project(case, catalog[0], workspace)
    install_reference(case, workspace)
    result = grade_project(case, workspace, before, tmp_path / "grading", timeout=0)
    assert result.status == "unavailable"
    assert result.details[-1]["check"] == "deadline"


def test_freeze_detects_snapshot_fingerprint_change(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    from pai.evals.project_tasks import build_freeze, check_freeze
    repo, root = catalog
    cases = load_catalog(root)
    frozen = build_freeze(cases, repo, tmp_path / "build")
    frozen["cases"][cases[0].id]["files"]["src/pai/subject.py"] = "0" * 64
    path = root / "freeze.json"
    path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="drift"):
        check_freeze(cases, repo, path, tmp_path / "check")


def test_freeze_cli_accepts_relative_output_directory(catalog: tuple[Path, Path], tmp_path: Path) -> None:
    import sys
    scoring_case(catalog, "fix")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pai.evals.project_tasks", "--repo", str(catalog[0]),
         "--catalog", str(catalog[1]), "--split", "all", "--freeze", "--output", "relative-report"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "relative-report/report.json").read_text())
    assert all(row["referenceContractPassed"] for row in report["cases"])
    assert (catalog[1] / "freeze.json").is_file()
