from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from .config import Config
from .settings import DATABASE_PATH, DATA_DIR, DEFAULT_AI_PROMPT


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
Index("idx_submission_files_submission", submission_files.c.submission_id, submission_files.c.id)
Index("idx_users_nickname_nocase", users.c.nickname.collate("NOCASE"))
Index("idx_ai_allowed_nickname_nocase", ai_allowed_nicknames.c.nickname.collate("NOCASE"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}",
    connect_args={
        "timeout": Config.SQLITE_TIMEOUT_SECONDS,
        "check_same_thread": False,
    },
    future=True,
)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
SessionLocal = scoped_session(SessionFactory)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute(f"PRAGMA busy_timeout = {int(Config.SQLITE_TIMEOUT_SECONDS * 1000)}")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA temp_store = MEMORY")
    cursor.execute(f"PRAGMA cache_size = -{max(1024, Config.SQLITE_CACHE_KB)}")
    cursor.close()


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_session() -> Session:
    return SessionLocal()


def create_session() -> Session:
    return SessionFactory()


def close_session(_exception: BaseException | None = None) -> None:
    SessionLocal.remove()


def commit() -> None:
    get_session().commit()


def rollback() -> None:
    get_session().rollback()


def row_to_dict(row: Any | None) -> dict | None:
    return dict(row) if row is not None else None


def execute_text(sql: str, params: dict[str, Any] | None = None, session: Session | None = None):
    return (session or get_session()).execute(text(sql), params or {})


def ensure_column(table_name: str, column_name: str, definition: str) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        columns = {row[1] for row in rows}
        if column_name not in columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def init_db() -> None:
    metadata.create_all(engine)
    ensure_column("submissions", "user_id", "INTEGER NOT NULL DEFAULT 0")
    ensure_column("submissions", "ai_answer", "TEXT NOT NULL DEFAULT ''")
    ensure_column("submissions", "ai_generated_at", "TEXT")
    ensure_column("users", "current_task", "TEXT NOT NULL DEFAULT ''")

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


def generate_short_user_id(session: Session) -> str:
    for _ in range(200):
        candidate = str(random.randint(1000, 9999))
        exists = session.execute(select(users.c.id).where(users.c.uid == candidate)).first()
        if not exists:
            return candidate
    raise RuntimeError("Не удалось подобрать свободный 4-значный ID")


def get_or_create_user(uid: str) -> tuple[dict, bool]:
    session = get_session()
    if uid:
        row = session.execute(
            select(users).where(users.c.uid == uid)
        ).mappings().first()
        if row:
            return dict(row), False

    timestamp = current_timestamp()
    for _ in range(5):
        uid = generate_short_user_id(session)
        try:
            result = session.execute(
                insert(users).values(
                    uid=uid,
                    nickname="",
                    current_task="",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.commit()
            break
        except IntegrityError:
            session.rollback()
            continue
    else:
        raise RuntimeError("Не удалось создать пользователя с уникальным ID")

    row = session.execute(
        select(users).where(users.c.id == result.inserted_primary_key[0])
    ).mappings().one()
    return dict(row), True


def get_user_answer_expression() -> str:
    return "CASE WHEN TRIM(COALESCE(admin_answer, '')) <> '' THEN admin_answer ELSE ai_answer END"


def fetch_app_settings(session: Session | None = None) -> dict[str, str]:
    rows = (session or get_session()).execute(select(app_settings.c.key, app_settings.c.value)).mappings().all()
    return {row["key"]: row["value"] for row in rows}


def get_ai_settings(session: Session | None = None) -> dict[str, object]:
    settings = fetch_app_settings(session)
    enabled = str(settings.get("ai_enabled", "1" if Config.AI_ENABLED else "0")).strip().lower() not in {"0", "false", "off", "no"}
    model = str(settings.get("openai_model", Config.OPENAI_MODEL) or "").strip() or Config.OPENAI_MODEL
    prompt = str(settings.get("ai_prompt", DEFAULT_AI_PROMPT) or "").strip() or DEFAULT_AI_PROMPT
    return {"enabled": enabled, "model": model, "prompt": prompt}


def update_app_settings(values: dict[str, str]) -> None:
    timestamp = current_timestamp()
    session = get_session()
    for key, value in values.items():
        session.execute(
            text(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (:key, :value, :updated_at)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """
            ),
            {"key": key, "value": value, "updated_at": timestamp},
        )
    session.commit()


def fetch_teacher_answers(user_id: int) -> dict[str, str]:
    answer_expression = get_user_answer_expression()
    rows = execute_text(
        f"""
        SELECT s.task_number, {answer_expression} AS answer_text
        FROM submissions s
        JOIN (
            SELECT task_number, MAX(id) AS max_id
            FROM submissions
            WHERE user_id = :user_id
              AND TRIM(COALESCE({answer_expression}, '')) <> ''
            GROUP BY task_number
        ) latest
        ON latest.max_id = s.id
        """,
        {"user_id": user_id},
    ).mappings().all()
    return {row["task_number"]: row["answer_text"] for row in rows}


def fetch_answer_sources(user_id: int) -> dict[str, str]:
    answer_expression = get_user_answer_expression()
    rows = execute_text(
        f"""
        SELECT s.task_number,
               CASE
                   WHEN TRIM(COALESCE(s.admin_answer, '')) <> '' THEN 'admin'
                   WHEN TRIM(COALESCE(s.ai_answer, '')) <> '' THEN 'ai'
                   ELSE ''
               END AS answer_source
        FROM submissions s
        JOIN (
            SELECT task_number, MAX(id) AS max_id
            FROM submissions
            WHERE user_id = :user_id
              AND TRIM(COALESCE({answer_expression}, '')) <> ''
            GROUP BY task_number
        ) latest
        ON latest.max_id = s.id
        """,
        {"user_id": user_id},
    ).mappings().all()
    return {row["task_number"]: row["answer_source"] for row in rows}


def fetch_answer_state(user_id: int) -> tuple[set[str], dict[str, str]]:
    teacher_answers = fetch_teacher_answers(user_id)
    return set(teacher_answers.keys()), teacher_answers


def fetch_used_tasks(user_id: int) -> list[str]:
    rows = execute_text(
        "SELECT DISTINCT task_number FROM submissions WHERE user_id = :user_id ORDER BY id",
        {"user_id": user_id},
    ).mappings().all()
    return [row["task_number"] for row in rows]


def add_submission_file(submission_id: int, original_name: str, stored_name: str) -> None:
    get_session().execute(
        insert(submission_files).values(
            submission_id=submission_id,
            original_name=original_name,
            stored_name=stored_name,
        )
    )


def fetch_submission_file_stored_names(submission_id: int, session: Session | None = None) -> list[str]:
    rows = (session or get_session()).execute(
        select(submission_files.c.stored_name).where(submission_files.c.submission_id == submission_id)
    ).mappings().all()
    return [row["stored_name"] for row in rows]


def delete_submission_file_rows(submission_id: int, session: Session | None = None) -> None:
    execute_text(
        "DELETE FROM submission_files WHERE submission_id = :submission_id",
        {"submission_id": submission_id},
        session,
    )


def create_submission(user_id: int, task_number: str, text_content: str) -> int:
    timestamp = current_timestamp()
    result = get_session().execute(
        insert(submissions).values(
            user_id=user_id,
            task_number=task_number,
            text_content=text_content,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    return int(result.inserted_primary_key[0])


def find_latest_submission_for_task(user_id: int, task_number: str) -> dict | None:
    row = execute_text(
        """
        SELECT id, text_content
        FROM submissions
        WHERE user_id = :user_id AND task_number = :task_number
        ORDER BY id DESC
        LIMIT 1
        """,
        {"user_id": user_id, "task_number": task_number},
    ).mappings().first()
    return row_to_dict(row)


def reset_submission_content(submission_id: int, text_content: str) -> None:
    execute_text(
        """
        UPDATE submissions
        SET text_content = :text_content,
            admin_answer = '',
            ai_answer = '',
            answered_at = NULL,
            ai_generated_at = NULL,
            updated_at = :updated_at
        WHERE id = :submission_id
        """,
        {
            "text_content": text_content,
            "updated_at": current_timestamp(),
            "submission_id": submission_id,
        },
    )


def fetch_allowed_nicknames() -> list[str]:
    rows = execute_text(
        "SELECT nickname FROM ai_allowed_nicknames ORDER BY nickname COLLATE NOCASE"
    ).mappings().all()
    return [row["nickname"] for row in rows]


def is_ai_allowed_for_nickname(nickname: str) -> bool:
    if not nickname:
        return False
    row = execute_text(
        "SELECT nickname FROM ai_allowed_nicknames WHERE nickname = :nickname COLLATE NOCASE",
        {"nickname": nickname},
    ).first()
    return row is not None


def get_submission_files(submission_id: int, session: Session | None = None) -> list[dict]:
    rows = execute_text(
        """
        SELECT original_name, stored_name
        FROM submission_files
        WHERE submission_id = :submission_id
        ORDER BY id
        """,
        {"submission_id": submission_id},
        session,
    ).mappings().all()
    return [{"original_name": row["original_name"], "stored_name": row["stored_name"]} for row in rows]


def build_submission_payload(base: dict) -> dict:
    admin_answer = str(base.get("admin_answer", "") or "").strip()
    ai_answer = str(base.get("ai_answer", "") or "").strip()
    answer_text = admin_answer or ai_answer
    answer_source = "admin" if admin_answer else ("ai" if ai_answer else "")
    files = list(base.get("files", []))
    filename = files[0]["original_name"] if files else ""
    file_url = f"/files/{files[0]['stored_name']}" if files else ""
    payload = dict(base)
    payload.update(
        {
            "task_key": f"submission:{base['id']}",
            "answer_text": answer_text,
            "answer_source": answer_source,
            "filename": filename,
            "file_url": file_url,
            "created": base.get("created_at", ""),
            "task_text": base.get("text_content", ""),
            "checked_by_teacher": False,
        }
    )
    return payload


def fetch_submission(submission_id: int, session: Session | None = None) -> dict | None:
    row = execute_text(
        """
        SELECT s.id, s.user_id, u.uid AS user_uid, u.nickname AS user_nickname,
               u.current_task AS user_current_task,
               s.task_number, s.text_content, s.admin_answer, s.ai_answer,
               s.created_at, s.updated_at, s.answered_at, s.ai_generated_at
        FROM submissions s
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.id = :submission_id
        """,
        {"submission_id": submission_id},
        session,
    ).mappings().first()
    if not row:
        return None
    return build_submission_payload(
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "user_uid": row["user_uid"] or "",
            "user_nickname": row["user_nickname"] or "",
            "user_current_task": row["user_current_task"] or "",
            "task_number": row["task_number"],
            "text_content": row["text_content"],
            "admin_answer": row["admin_answer"],
            "ai_answer": row["ai_answer"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "answered_at": row["answered_at"],
            "ai_generated_at": row["ai_generated_at"],
            "files": get_submission_files(row["id"], session),
        }
    )


def fetch_submissions() -> list[dict]:
    rows = execute_text(
        """
        SELECT s.id, s.user_id, u.uid AS user_uid, u.nickname AS user_nickname,
               u.current_task AS user_current_task,
               s.task_number, s.text_content, s.admin_answer, s.ai_answer,
               s.created_at, s.updated_at, s.answered_at, s.ai_generated_at
        FROM submissions s
        LEFT JOIN users u ON u.id = s.user_id
        ORDER BY
            LOWER(COALESCE(u.nickname, '')),
            u.id,
            CASE s.task_number
                WHEN '1' THEN 1
                WHEN '2' THEN 2
                WHEN '3' THEN 3
                WHEN '4' THEN 4
                WHEN '5' THEN 5
                WHEN '6' THEN 6
                WHEN '7' THEN 7
                WHEN '8' THEN 8
                WHEN '9' THEN 9
                WHEN '10' THEN 10
                WHEN '11' THEN 11
                WHEN '12' THEN 12
                WHEN '13' THEN 13
                WHEN '14' THEN 14
                WHEN '15' THEN 15
                WHEN '16' THEN 16
                WHEN '17' THEN 17
                ELSE 999
            END,
            s.id DESC
        """
    ).mappings().all()
    if not rows:
        return []

    submission_ids = [row["id"] for row in rows]
    file_rows = get_session().execute(
        select(
            submission_files.c.submission_id,
            submission_files.c.original_name,
            submission_files.c.stored_name,
        )
        .where(submission_files.c.submission_id.in_(submission_ids))
        .order_by(submission_files.c.id)
    ).mappings().all()
    files_by_submission: dict[int, list[dict]] = {}
    for row in file_rows:
        files_by_submission.setdefault(row["submission_id"], []).append(
            {"original_name": row["original_name"], "stored_name": row["stored_name"]}
        )

    return [
        build_submission_payload(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "user_uid": row["user_uid"] or "",
                "user_nickname": row["user_nickname"] or "",
                "user_current_task": row["user_current_task"] or "",
                "task_number": row["task_number"],
                "text_content": row["text_content"],
                "admin_answer": row["admin_answer"],
                "ai_answer": row["ai_answer"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "answered_at": row["answered_at"],
                "ai_generated_at": row["ai_generated_at"],
                "files": files_by_submission.get(row["id"], []),
            }
        )
        for row in rows
    ]


def update_user_nickname(user_id: int, nickname: str) -> None:
    execute_text(
        "UPDATE users SET nickname = :nickname, updated_at = :updated_at WHERE id = :user_id",
        {"nickname": nickname, "updated_at": current_timestamp(), "user_id": user_id},
    )
    commit()


def fetch_unanswered_submission_ids_for_user(user_id: int) -> list[int]:
    rows = execute_text(
        """
        SELECT id
        FROM submissions
        WHERE user_id = :user_id
          AND TRIM(COALESCE(admin_answer, '')) = ''
          AND TRIM(COALESCE(ai_answer, '')) = ''
        """,
        {"user_id": user_id},
    ).mappings().all()
    return [row["id"] for row in rows]


def update_user_current_task(user_id: int, task_number: str) -> None:
    execute_text(
        "UPDATE users SET current_task = :task_number, updated_at = :updated_at WHERE id = :user_id",
        {"task_number": task_number, "updated_at": current_timestamp(), "user_id": user_id},
    )
    commit()


def fetch_user_summary_uploads(user_id: int) -> list[dict]:
    rows = execute_text(
        """
        SELECT id, task_number, text_content, created_at
        FROM submissions
        WHERE user_id = :user_id
        ORDER BY id DESC
        """,
        {"user_id": user_id},
    ).mappings().all()
    return [
        {
            "id": row["id"],
            "task_number": row["task_number"],
            "text_content": row["text_content"],
            "created": row["created_at"],
            "files": get_submission_files(row["id"]),
        }
        for row in rows
    ]


def add_ai_allowed_nickname(nickname: str) -> None:
    execute_text(
        """
        INSERT OR IGNORE INTO ai_allowed_nicknames (nickname, created_at)
        VALUES (:nickname, :created_at)
        """,
        {"nickname": nickname, "created_at": current_timestamp()},
    )
    commit()


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


def remove_ai_allowed_nickname(nickname: str) -> None:
    execute_text(
        "DELETE FROM ai_allowed_nicknames WHERE nickname = :nickname COLLATE NOCASE",
        {"nickname": nickname},
    )
    commit()


def update_submission_admin_answer(submission_id: int, answer_text: str) -> int:
    timestamp = current_timestamp()
    result = execute_text(
        """
        UPDATE submissions
        SET admin_answer = :answer_text,
            updated_at = :updated_at,
            answered_at = :answered_at
        WHERE id = :submission_id
        """,
        {
            "answer_text": answer_text,
            "updated_at": timestamp,
            "answered_at": timestamp if answer_text else None,
            "submission_id": submission_id,
        },
    )
    commit()
    return result.rowcount


def update_submission_ai_answer(
    submission_id: int,
    answer_text: str,
    *,
    set_answered_at_if_empty: bool = False,
    session: Session | None = None,
) -> int:
    timestamp = current_timestamp()
    if set_answered_at_if_empty:
        sql = """
            UPDATE submissions
            SET ai_answer = :answer_text,
                ai_generated_at = :generated_at,
                updated_at = :updated_at,
                answered_at = CASE
                    WHEN TRIM(COALESCE(answered_at, '')) = '' THEN :answered_at
                    ELSE answered_at
                END
            WHERE id = :submission_id
        """
    else:
        sql = """
            UPDATE submissions
            SET ai_answer = :answer_text,
                ai_generated_at = :generated_at,
                updated_at = :updated_at
            WHERE id = :submission_id
        """
    result = execute_text(
        sql,
        {
            "answer_text": answer_text,
            "generated_at": timestamp,
            "updated_at": timestamp,
            "answered_at": timestamp,
            "submission_id": submission_id,
        },
        session,
    )
    return result.rowcount


def health_check() -> None:
    execute_text("SELECT 1").fetchone()
