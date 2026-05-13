from __future__ import annotations

from ..db import session as db_session
from ..db.schema import current_timestamp
from .common import execute_text


def fetch_allowed_nicknames() -> list[str]:
    rows = execute_text("SELECT nickname FROM ai_allowed_nicknames ORDER BY nickname COLLATE NOCASE").mappings().all()
    return [row["nickname"] for row in rows]


def is_ai_allowed_for_nickname(nickname: str) -> bool:
    if not nickname:
        return False
    row = execute_text(
        "SELECT nickname FROM ai_allowed_nicknames WHERE nickname = :nickname COLLATE NOCASE",
        {"nickname": nickname},
    ).first()
    return row is not None


def add_ai_allowed_nickname(nickname: str) -> None:
    execute_text(
        """
        INSERT OR IGNORE INTO ai_allowed_nicknames (nickname, created_at)
        VALUES (:nickname, :created_at)
        """,
        {"nickname": nickname, "created_at": current_timestamp()},
    )
    db_session.commit()


def remove_ai_allowed_nickname(nickname: str) -> None:
    execute_text(
        "DELETE FROM ai_allowed_nicknames WHERE nickname = :nickname COLLATE NOCASE",
        {"nickname": nickname},
    )
    db_session.commit()


def fetch_unanswered_submission_ids_for_nickname(nickname: str) -> list[int]:
    rows = execute_text(
        """
        SELECT s.id
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        WHERE u.nickname = :nickname COLLATE NOCASE
          AND TRIM(COALESCE(s.admin_answer, '')) = ''
          AND TRIM(COALESCE(s.ai_answer, '')) = ''
        """,
        {"nickname": nickname},
    ).mappings().all()
    return [row["id"] for row in rows]
