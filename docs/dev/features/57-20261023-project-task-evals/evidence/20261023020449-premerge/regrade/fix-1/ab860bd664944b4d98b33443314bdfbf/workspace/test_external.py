import pytest
from pagination import page_count

@pytest.mark.parametrize("total,size,want", [(5,2,3),(4,2,2),(0,2,0),(1,1,1),(13,4,4)])
def test_page_count(total,size,want):
    assert page_count(total,size) == want

@pytest.mark.parametrize("total,size", [(-1,2),(2,0),(2,-1)])
def test_invalid(total,size):
    with pytest.raises(ValueError):
        page_count(total,size)
