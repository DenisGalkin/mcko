from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.session import get_session


def row_to_dict(row: Any | None) -> dict | None:
    return dict(row) if row is not None else None


def execute_text(sql: str, params: dict[str, Any] | None = None, session: Session | None = None):
    return (session or get_session()).execute(text(sql), params or {})
