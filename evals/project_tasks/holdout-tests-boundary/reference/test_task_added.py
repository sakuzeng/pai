from pai.core.boundary import path_in_working_path
import pytest

@pytest.mark.parametrize('target,root,inside', [('/project', '/project', True), ('/project/src/a.py', '/project', True), ('/project-evil/a.py', '/project', False), ('/other', '/project', False), ('', '/project', False), ('/project', '', False), ('/project/src/../a.py', '/project', True), ('/project/../outside', '/project', False), ('/project/a', '/project/', True), ('/anywhere', '/', True), ('/', '/', True)])
def test_path_boundaries(target: str, root: str, inside: bool) -> None:
    assert path_in_working_path(target, root) is inside
