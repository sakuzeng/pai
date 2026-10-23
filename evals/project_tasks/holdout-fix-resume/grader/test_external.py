from pathlib import Path
from typing import Optional
import json
import inspect
import os
from pathlib import Path
import pytest
from pai.core.session import resolve_resume_target

def resolve(target: Optional[str], directory: Path, cwd: Path) -> Path:
    if 'cwd' in inspect.signature(resolve_resume_target).parameters:
        return resolve_resume_target(target, directory, cwd=cwd)
    return resolve_resume_target(target, directory)

def session(directory: Path, name: str, cwd: Path, mtime: float) -> Path:
    path = directory / (name + '.jsonl')
    path.write_text(json.dumps({'type': 'session', 'version': 1, 'id': name, 'cwd': str(cwd)}) + '\n')
    os.utime(path, (mtime, mtime))
    return path

def test_default_skips_newer_foreign_directory(tmp_path: Path) -> None:
    (here, other) = (tmp_path / 'here', tmp_path / 'other')
    wanted = session(tmp_path, 'ours', here, 100)
    session(tmp_path, 'foreign', other, 200)
    assert resolve(None, tmp_path, here) == wanted

def test_missing_current_directory_fails_instead_of_foreign(tmp_path: Path) -> None:
    session(tmp_path, 'foreign', tmp_path / 'other', 200)
    with pytest.raises(FileNotFoundError):
        resolve(None, tmp_path, tmp_path / 'here')

def test_explicit_id_still_allows_foreign_directory(tmp_path: Path) -> None:
    wanted = session(tmp_path, 'foreign', tmp_path / 'other', 200)
    assert resolve('foreign', tmp_path, tmp_path / 'here') == wanted

def test_explicit_path_still_allows_foreign_directory(tmp_path: Path) -> None:
    wanted = session(tmp_path, 'foreign', tmp_path / 'other', 200)
    assert resolve(str(wanted), tmp_path, tmp_path / 'here') == wanted

def test_process_cwd_is_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = tmp_path / 'here'
    here.mkdir()
    wanted = session(tmp_path, 'ours', here, 100)
    session(tmp_path, 'foreign', tmp_path / 'other', 200)
    monkeypatch.chdir(here)
    assert resolve_resume_target(None, tmp_path) == wanted

def test_broken_header_is_ignored(tmp_path: Path) -> None:
    (tmp_path / 'broken.jsonl').write_text('not json')
    wanted = session(tmp_path, 'ours', tmp_path / 'here', 100)
    assert resolve(None, tmp_path, tmp_path / 'here') == wanted
