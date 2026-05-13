from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, Table, Text, text

from ..config import Config
from ..settings import DEFAULT_AI_PROMPT
from .session import engine


metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("nickname", Text, nullable=False, server_default=""),
    Column("current_task", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

submissions = Table(
    "submissions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, server_default="0"),
    Column("task_number", Text, nullable=False),
    Column("text_content", Text, nullable=False, server_default=""),
    Column("admin_answer", Text, nullable=False, server_default=""),
    Column("ai_answer", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("answered_at", Text),
    Column("ai_generated_at", Text),
)

submission_files = Table(
    "submission_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("submission_id", Integer, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
    Column("original_name", Text, nullable=False),
    Column("stored_name", Text, nullable=False),
)

ai_allowed_nicknames = Table(
    "ai_allowed_nicknames",
    metadata,
    Column("nickname", Text, primary_key=True),
    Column("created_at", Text, nullable=False),
)

app_settings = Table(
    "app_settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

Index("idx_submissions_user_task_id", submissions.c.user_id, submissions.c.task_number, submissions.c.id.desc())
Index("idx_submissions_user_answer", submissions.c.user_id, submissions.c.admin_answer, submissions.c.ai_answer)
Index("idx_submissions_user_id_desc", submissions.c.user_id, submissions.c.id.desc())
Index("idx_submission_files_submission", submission_files.c.submission_id, submission_files.c.id)
Index("idx_users_nickname_nocase", users.c.nickname.collate("NOCASE"))
Index("idx_ai_allowed_nickname_nocase", ai_allowed_nicknames.c.nickname.collate("NOCASE"))


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_column(table_name: str, column_name: str, definition: str) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        columns = {row[1] for row in rows}
        if column_name not in columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def ensure_indexes() -> None:
    statements = [
        """
        CREATE INDEX IF NOT EXISTS idx_submissions_user_task_id
        ON submissions (user_id, task_number, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_submissions_user_answer
        ON submissions (user_id, admin_answer, ai_answer)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_submissions_user_id_desc
        ON submissions (user_id, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_submission_files_submission
        ON submission_files (submission_id, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_users_nickname_nocase
        ON users (nickname COLLATE NOCASE)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_allowed_nickname_nocase
        ON ai_allowed_nicknames (nickname COLLATE NOCASE)
        """,
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db() -> None:
    metadata.create_all(engine)
    ensure_column("submissions", "user_id", "INTEGER NOT NULL DEFAULT 0")
    ensure_column("submissions", "ai_answer", "TEXT NOT NULL DEFAULT ''")
    ensure_column("submissions", "ai_generated_at", "TEXT")
    ensure_column("users", "current_task", "TEXT NOT NULL DEFAULT ''")
    ensure_indexes()

    timestamp = current_timestamp()
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode = WAL"))
        default_settings = {
            "ai_enabled": "1" if Config.AI_ENABLED else "0",
            "openai_model": Config.OPENAI_MODEL,
            "ai_prompt": DEFAULT_AI_PROMPT,
        }
        for key, value in default_settings.items():
            connection.execute(
                text(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES (:key, :value, :updated_at)
                    """
                ),
                {"key": key, "value": value, "updated_at": timestamp},
            )

        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO users (uid, nickname, current_task, created_at, updated_at)
                VALUES ('legacy-user', 'legacy', '', :created_at, :updated_at)
                """
            ),
            {"created_at": timestamp, "updated_at": timestamp},
        )
        legacy_user_id = connection.execute(text("SELECT id FROM users WHERE uid = 'legacy-user'")).scalar_one()
        connection.execute(
            text("UPDATE submissions SET user_id = :user_id WHERE COALESCE(user_id, 0) = 0"),
            {"user_id": legacy_user_id},
        )
