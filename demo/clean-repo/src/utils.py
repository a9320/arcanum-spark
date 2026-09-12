"""Small string and math helpers used by the clean demo app."""


def slugify(text: str) -> str:
    return "-".join(part.strip().lower() for part in text.split() if part)


def clamp(value: int, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(high, value))


def summary(lines: list[str]) -> dict:
    non_empty = [line for line in lines if line.strip()]
    return {"total": len(lines), "non_empty": len(non_empty)}
