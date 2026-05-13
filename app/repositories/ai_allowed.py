from __future__ import annotations

from ..db import session as db_session
from ..db.schema import current_timestamp
from .common import execute_text


DEFAULT_KARMA = 100


def fetch_special_logins() -> list[dict]:
    rows = execute_text(
        """
        SELECT nickname, COALESCE(ai_enabled, 1) AS ai_enabled, COALESCE(karma, :default_karma) AS karma
        FROM ai_allowed_nicknames
        ORDER BY nickname COLLATE NOCASE
        """,
        {"default_karma": DEFAULT_KARMA},
    ).mappings().all()
    return [
        {
            "nickname": row["nickname"],
            "ai_enabled": bool(row["ai_enabled"]),
            "karma": int(row["karma"] if row["karma"] is not None else DEFAULT_KARMA),
        }
        for row in rows
    ]


def fetch_allowed_nicknames() -> list[str]:
    rows = execute_text(
        """
        SELECT nickname
        FROM ai_allowed_nicknames
        WHERE COALESCE(ai_enabled, 1) = 1
        ORDER BY nickname COLLATE NOCASE
        """
    ).mappings().all()
    return [row["nickname"] for row in rows]


def is_ai_allowed_for_nickname(nickname: str) -> bool:
    if not nickname:
        return False
    row = execute_text(
        """
        SELECT nickname
        FROM ai_allowed_nicknames
        WHERE nickname = :nickname COLLATE NOCASE
          AND COALESCE(ai_enabled, 1) = 1
        """,
        {"nickname": nickname},
    ).first()
    return row is not None


def is_special_login(nickname: str) -> bool:
    if not nickname:
        return False
    row = execute_text(
        """
        SELECT nickname
        FROM ai_allowed_nicknames
        WHERE nickname = :nickname COLLATE NOCASE
        """,
        {"nickname": nickname},
    ).first()
    return row is not None


def get_karma_for_nickname(nickname: str) -> int:
    if not nickname:
        return DEFAULT_KARMA
    row = execute_text(
        """
        SELECT COALESCE(karma, :default_karma) AS karma
        FROM ai_allowed_nicknames
        WHERE nickname = :nickname COLLATE NOCASE
        """,
        {"nickname": nickname, "default_karma": DEFAULT_KARMA},
    ).mappings().first()
    if not row:
        return DEFAULT_KARMA
    return int(row["karma"])


def add_ai_allowed_nickname(nickname: str, ai_enabled: bool = True, karma: int = DEFAULT_KARMA) -> None:
    upsert_special_login(nickname, ai_enabled=ai_enabled, karma=karma)


def upsert_special_login(nickname: str, ai_enabled: bool = True, karma: int = DEFAULT_KARMA) -> None:
    timestamp = current_timestamp()
    execute_text(
        """
        INSERT INTO ai_allowed_nicknames (nickname, ai_enabled, karma, created_at, updated_at)
        VALUES (:nickname, :ai_enabled, :karma, :created_at, :updated_at)
        ON CONFLICT(nickname) DO UPDATE SET
            ai_enabled = excluded.ai_enabled,
            karma = excluded.karma,
            updated_at = excluded.updated_at
        """,
        {
            "nickname": nickname,
            "ai_enabled": 1 if ai_enabled else 0,
            "karma": int(karma),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    from . import submissions

    submissions.recalculate_priorities_for_nickname(nickname)
    db_session.commit()


def update_special_login(nickname: str, ai_enabled: bool, karma: int) -> int:
    result = execute_text(
        """
        UPDATE ai_allowed_nicknames
        SET ai_enabled = :ai_enabled,
            karma = :karma,
            updated_at = :updated_at
        WHERE nickname = :nickname COLLATE NOCASE
        """,
        {
            "nickname": nickname,
            "ai_enabled": 1 if ai_enabled else 0,
            "karma": int(karma),
            "updated_at": current_timestamp(),
        },
    )
    from . import submissions

    submissions.recalculate_priorities_for_nickname(nickname)
    db_session.commit()
    return result.rowcount


def remove_ai_allowed_nickname(nickname: str) -> None:
    execute_text(
        "DELETE FROM ai_allowed_nicknames WHERE nickname = :nickname COLLATE NOCASE",
        {"nickname": nickname},
    )
    from . import submissions

    submissions.recalculate_priorities_for_nickname(nickname)
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
