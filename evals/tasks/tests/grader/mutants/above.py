def clip(value: int, lower: int, upper: int) -> int:
    if lower > upper:
        raise ValueError("invalid bounds")
    return max(lower, value)
