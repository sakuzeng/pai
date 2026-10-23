def page_count(total: int, size: int) -> int:
    """非负总数、正页大小；非法参数抛 ValueError。"""
    if total < 0 or size <= 0:
        raise ValueError("invalid pagination")
    return total // size + 1
