def clip(value: int, lower: int, upper: int) -> int:
    if lower > upper:
        raise ValueError("invalid bounds")
    return value if value < lower else min(value, upper)
