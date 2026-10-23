import pytest
from ranges import clip

@pytest.mark.parametrize("value,want", [(-1,0),(0,0),(2,2),(5,5),(6,5)])
def test_clip(value,want):
    assert clip(value,0,5) == want

def test_invalid():
    with pytest.raises(ValueError):
        clip(1,5,0)

def test_equal_bounds():
    assert clip(9,3,3) == 3
