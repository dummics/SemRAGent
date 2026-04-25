from __future__ import annotations


def format_score(value: float | int | None) -> float | None:
    """Public score formatter: float in 0.000..1.000 rounded to 3 decimals."""
    if value is None:
        return None
    return round(max(0.0, min(1.0, float(value))), 3)
