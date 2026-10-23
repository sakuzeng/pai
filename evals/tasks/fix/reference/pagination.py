def page_count(total: int, size: int) -> int:
    if total < 0 or size <= 0:
        raise ValueError("invalid pagination")
    return (total + size - 1) // size
