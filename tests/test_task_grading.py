from __future__ import annotations

from pathlib import Path
import json
import shutil

import pytest

from pai.evals.task_grading import Grade, TaskCase, load_case, prepare, grade

CASES = Path(__file__).resolve().parents[1] / "evals" / "tasks"


def setup_case(tmp_path: Path, name: str) -> tuple[TaskCase, Path, dict[str, str]]:
    case = load_case(CASES / name)
    workspace = tmp_path / "workspace"
    baseline = prepare(case, workspace)
    return case, workspace, baseline


def check(tmp_path: Path, case: TaskCase, workspace: Path, baseline: dict[str, str]) -> Grade:
    return grade(case, workspace, baseline, tmp_path / "grading", timeout=10)


def test_locate_requires_exact_target_and_no_protected_change(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "locate")
    assert check(tmp_path, case, ws, before).status == "fail"
    (ws / "answer.json").write_text(json.dumps({"path":"text_rules.py", "function":"slugify"}))
    assert check(tmp_path, case, ws, before).status == "pass"
    (ws / "answer.json").write_text(json.dumps({"path":"ui_labels.py", "function":"display_label"}))
    assert check(tmp_path, case, ws, before).status == "fail"


def test_fix_fixture_red_and_reference_green(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "fix")
    assert check(tmp_path, case, ws, before).status == "fail"
    shutil.copyfile(case.root / "reference" / "pagination.py", ws / "pagination.py")
    assert check(tmp_path, case, ws, before).status == "pass"
    (ws / "tests" / "test_visible.py").unlink()
    assert check(tmp_path, case, ws, before).status == "fail"


def test_added_tests_must_pass_correct_and_reject_every_mutant(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "tests")
    assert check(tmp_path, case, ws, before).status == "fail"
    (ws / "tests" / "test_clip.py").write_text("def test_empty():\n    assert True\n")
    assert check(tmp_path, case, ws, before).status == "fail"
    shutil.copyfile(case.root / "reference" / "test_clip.py", ws / "tests" / "test_clip.py")
    result = check(tmp_path, case, ws, before)
    assert result.status == "pass", result.details
    (ws / "ranges.py").write_text("raise RuntimeError('不能改生产实现')\n")
    assert check(tmp_path, case, ws, before).status == "fail"


@pytest.mark.parametrize("content", ["???", "import missing_package", "def test_bad():\n    assert False\n"])
def test_bad_added_tests_cannot_count_as_mutant_detection(tmp_path: Path, content: str) -> None:
    case, ws, before = setup_case(tmp_path, "tests")
    (ws / "tests" / "test_clip.py").write_text(content)
    assert check(tmp_path, case, ws, before).status == "fail"


def test_added_tests_must_detect_invalid_bounds_mutant(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "tests")
    (ws / "tests" / "test_clip.py").write_text(
        "from ranges import clip\ndef test_some():\n    assert clip(-2, 0, 5) == 0\n    assert clip(8, 0, 5) == 5\n")
    assert check(tmp_path, case, ws, before).status == "fail"


def test_symlink_and_extra_files_are_rejected(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "locate")
    (ws / "answer.json").symlink_to(case.root / "case.json")
    assert check(tmp_path, case, ws, before).status == "fail"
    (ws / "answer.json").unlink()
    (ws / "answer.json").write_text('{"path":"text_rules.py","function":"slugify"}')
    (ws / "unexpected.py").write_text("pass")
    assert check(tmp_path, case, ws, before).status == "fail"


def test_fix_cannot_pass_by_skipping_external_assertions(tmp_path: Path) -> None:
    case, ws, before = setup_case(tmp_path, "fix")
    (ws / "pagination.py").write_text(
        "from unittest import SkipTest\ndef page_count(total, size):\n    raise SkipTest('skip')\n")
    assert check(tmp_path, case, ws, before).status == "fail"


def test_external_grader_never_loads_source_checkout_conftest(tmp_path: Path) -> None:
    source=tmp_path/'source'
    root=source/'case'
    shutil.copytree(CASES/'fix',root)
    (source/'conftest.py').write_text("raise RuntimeError('source conftest must not execute')\n")
    case=load_case(root)
    ws=tmp_path/'workspace'
    before=prepare(case,ws)
    shutil.copyfile(root/'reference/pagination.py',ws/'pagination.py')
    result=check(tmp_path,case,ws,before)
    assert result.status=='pass',result.details
