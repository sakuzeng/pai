def slugify(label: str) -> str:
    return "-".join(label.strip().lower().split())
