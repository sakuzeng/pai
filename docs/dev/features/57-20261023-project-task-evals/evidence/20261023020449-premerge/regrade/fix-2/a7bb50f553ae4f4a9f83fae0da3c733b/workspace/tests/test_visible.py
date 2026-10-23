from pagination import page_count

def test_partial_page():
    assert page_count(5, 2) == 3
