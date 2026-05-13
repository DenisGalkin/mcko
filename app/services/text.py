from __future__ import annotations


def normalize_text(value: str) -> str:
    return str(value or "").strip()
