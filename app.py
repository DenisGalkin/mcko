from __future__ import annotations

import base64
import json
import mimetypes
import os
import random
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from config import Config


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
DATABASE_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
TASK_NUMBERS = [str(number) for number in range(1, 18)]
TASK_CONTENTS_PATH = BASE_DIR / "static" / "mcko_26733" / "tasks.json"
USER_COOKIE_NAME = "mcko_uid"
DEFAULT_AI_PROMPT = "\n".join(
    [
        "Реши школьное задание на русском языке.",
        "Верни только готовый ответ без markdown и без лишних пояснений.",
        "Если у задания несколько пунктов, ответь на каждый.",
        "Проверь орфографию перед выводом.",
    ]
)


def load_task_contents() -> dict[str, str]:
    try:
        data = json.loads(TASK_CONTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items()}


TASK_CONTENTS = load_task_contents()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
AI_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, Config.AI_MAX_WORKERS), thread_name_prefix="ai-answer")
AI_PENDING_IDS: set[int] = set()
AI_PENDING_LOCK = threading.Lock()
REQUEST_LOCAL = threading.local()


def task_number_sort_key(task_number: str) -> tuple[int, int | str]:
    task_number = str(task_number)
    if task_number in TASK_NUMBERS:
        return (0, TASK_NUMBERS.index(task_number))
    return (1, task_number)


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_text(value: str) -> str:
    return str(value or "").strip()


def admin_is_authenticated() -> bool:
    return session.get("admin_authenticated") is True


def admin_required():
    if admin_is_authenticated():
        return None
    return redirect(url_for("admin_login", next=request.path))


def configure_sqlite_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(Config.SQLITE_TIMEOUT_SECONDS * 1000)}")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute(f"PRAGMA cache_size = -{max(1024, Config.SQLITE_CACHE_KB)}")
    return connection


def open_sqlite_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=Config.SQLITE_TIMEOUT_SECONDS)
    return configure_sqlite_connection(connection)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = open_sqlite_connection()
    return g.db


def db_connect() -> sqlite3.Connection:
    return open_sqlite_connection()


@app.teardown_appcontext
def close_db(_exception: BaseException | None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with open_sqlite_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL UNIQUE,
                nickname TEXT NOT NULL DEFAULT '',
                current_task TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0,
                task_number TEXT NOT NULL,
                text_content TEXT NOT NULL DEFAULT '',
                admin_answer TEXT NOT NULL DEFAULT '',
                ai_answer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                answered_at TEXT,
                ai_generated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS submission_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_allowed_nicknames (
                nickname TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_submissions_user_task_id
                ON submissions(user_id, task_number, id DESC);

            CREATE INDEX IF NOT EXISTS idx_submissions_user_answer
                ON submissions(user_id, admin_answer, ai_answer);

            CREATE INDEX IF NOT EXISTS idx_submission_files_submission
                ON submission_files(submission_id, id);

            CREATE INDEX IF NOT EXISTS idx_users_nickname_nocase
                ON users(nickname COLLATE NOCASE);

            CREATE INDEX IF NOT EXISTS idx_ai_allowed_nickname_nocase
                ON ai_allowed_nicknames(nickname COLLATE NOCASE);
            """
        )

        ensure_column(connection, "submissions", "user_id", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "submissions", "ai_answer", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "submissions", "ai_generated_at", "TEXT")
        ensure_column(connection, "users", "current_task", "TEXT NOT NULL DEFAULT ''")

        timestamp = current_timestamp()
        default_settings = {
            "ai_enabled": "1" if Config.AI_ENABLED else "0",
            "openai_model": Config.OPENAI_MODEL,
            "ai_prompt": DEFAULT_AI_PROMPT,
        }
        for key, value in default_settings.items():
            connection.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, timestamp),
            )

        connection.execute(
            """
            INSERT OR IGNORE INTO users (uid, nickname, current_task, created_at, updated_at)
            VALUES ('legacy-user', 'legacy', '', ?, ?)
            """,
            (timestamp, timestamp),
        )
        legacy_user_id = connection.execute(
            "SELECT id FROM users WHERE uid = 'legacy-user'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE submissions SET user_id = ? WHERE COALESCE(user_id, 0) = 0",
            (legacy_user_id,),
        )


def get_or_create_current_user() -> tuple[dict, bool]:
    uid = normalize_text(request.cookies.get(USER_COOKIE_NAME))
    connection = get_db()
    if uid:
        row = connection.execute(
            "SELECT id, uid, nickname, current_task, created_at, updated_at FROM users WHERE uid = ?",
            (uid,),
        ).fetchone()
        if row:
            return dict(row), False

    timestamp = current_timestamp()
    for _ in range(5):
        uid = generate_short_user_id(connection)
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (uid, nickname, current_task, created_at, updated_at)
                VALUES (?, '', '', ?, ?)
                """,
                (uid, timestamp, timestamp),
            )
            break
        except sqlite3.IntegrityError:
            continue
    else:
        raise RuntimeError("Не удалось создать пользователя с уникальным ID")
    connection.commit()
    row = connection.execute(
        "SELECT id, uid, nickname, current_task, created_at, updated_at FROM users WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return dict(row), True


def generate_short_user_id(connection: sqlite3.Connection) -> str:
    for _ in range(200):
        candidate = str(random.randint(1000, 9999))
        exists = connection.execute("SELECT 1 FROM users WHERE uid = ?", (candidate,)).fetchone()
        if not exists:
            return candidate
    raise RuntimeError("Не удалось подобрать свободный 4-значный ID")


def with_user_cookie(response, uid: str):
    response.set_cookie(
        USER_COOKIE_NAME,
        uid,
        max_age=60 * 60 * 24 * 365 * 5,
        samesite="Lax",
        httponly=True,
    )
    return response


def get_user_answer_expression() -> str:
    return "CASE WHEN TRIM(COALESCE(admin_answer, '')) <> '' THEN admin_answer ELSE ai_answer END"


def fetch_app_settings(connection: sqlite3.Connection | None = None) -> dict[str, str]:
    database = connection or get_db()
    rows = database.execute("SELECT key, value FROM app_settings").fetchall()
    return {
        row["key"] if isinstance(row, sqlite3.Row) else row[0]: row["value"] if isinstance(row, sqlite3.Row) else row[1]
        for row in rows
    }


def get_ai_settings(connection: sqlite3.Connection | None = None) -> dict[str, object]:
    settings = fetch_app_settings(connection)
    enabled = str(settings.get("ai_enabled", "1" if Config.AI_ENABLED else "0")).strip().lower() not in {"0", "false", "off", "no"}
    model = normalize_text(settings.get("openai_model", Config.OPENAI_MODEL)) or Config.OPENAI_MODEL
    prompt = normalize_text(settings.get("ai_prompt", DEFAULT_AI_PROMPT)) or DEFAULT_AI_PROMPT
    return {"enabled": enabled, "model": model, "prompt": prompt}


def update_app_settings(values: dict[str, str]) -> None:
    timestamp = current_timestamp()
    for key, value in values.items():
        get_db().execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, timestamp),
        )
    get_db().commit()


def fetch_answered_tasks(user_id: int) -> set[str]:
    rows = get_db().execute(
        f"""
        SELECT DISTINCT task_number
        FROM submissions
        WHERE user_id = ?
          AND TRIM(COALESCE({get_user_answer_expression()}, '')) <> ''
        """,
        (user_id,),
    ).fetchall()
    return {row["task_number"] for row in rows}


def fetch_teacher_answers(user_id: int) -> dict[str, str]:
    answer_expression = get_user_answer_expression()
    rows = get_db().execute(
        f"""
        SELECT s.task_number, {answer_expression} AS answer_text
        FROM submissions s
        JOIN (
            SELECT task_number, MAX(id) AS max_id
            FROM submissions
            WHERE user_id = ?
              AND TRIM(COALESCE({answer_expression}, '')) <> ''
            GROUP BY task_number
        ) latest
        ON latest.max_id = s.id
        """,
        (user_id,),
    ).fetchall()
    return {row["task_number"]: row["answer_text"] for row in rows}


def fetch_answer_sources(user_id: int) -> dict[str, str]:
    answer_expression = get_user_answer_expression()
    rows = get_db().execute(
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
            WHERE user_id = ?
              AND TRIM(COALESCE({answer_expression}, '')) <> ''
            GROUP BY task_number
        ) latest
        ON latest.max_id = s.id
        """,
        (user_id,),
    ).fetchall()
    return {row["task_number"]: row["answer_source"] for row in rows}


def fetch_answer_state(user_id: int) -> tuple[set[str], dict[str, str]]:
    teacher_answers = fetch_teacher_answers(user_id)
    return set(teacher_answers.keys()), teacher_answers


def fetch_used_tasks(user_id: int) -> list[str]:
    rows = get_db().execute(
        "SELECT DISTINCT task_number FROM submissions WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    return [row["task_number"] for row in rows]


def allocate_task_numbers(user_id: int, start_task: str | None, count: int) -> list[str]:
    if count <= 0:
        return []

    if start_task:
        start_index = TASK_NUMBERS.index(start_task)
    else:
        used_tasks = set(fetch_used_tasks(user_id))
        start_index = next((index for index, value in enumerate(TASK_NUMBERS) if value not in used_tasks), 0)

    assigned = TASK_NUMBERS[start_index : start_index + count]
    if len(assigned) < count:
        raise ValueError("Недостаточно номеров заданий для выбранной загрузки.")
    return assigned


def save_file(file_storage, submission_id: int) -> None:
    original_name = secure_filename(file_storage.filename or "file")
    extension = Path(original_name).suffix
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_storage.save(UPLOAD_DIR / stored_name)
    get_db().execute(
        """
        INSERT INTO submission_files (submission_id, original_name, stored_name)
        VALUES (?, ?, ?)
        """,
        (submission_id, original_name or stored_name, stored_name),
    )


def delete_submission_files(submission_id: int, connection: sqlite3.Connection | None = None) -> None:
    db = connection or get_db()
    rows = db.execute(
        "SELECT stored_name FROM submission_files WHERE submission_id = ?",
        (submission_id,),
    ).fetchall()
    for row in rows:
        file_path = UPLOAD_DIR / row["stored_name"]
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
    db.execute("DELETE FROM submission_files WHERE submission_id = ?", (submission_id,))


def create_submission(user: dict, task_number: str, text_content: str, files: Iterable) -> int:
    timestamp = current_timestamp()
    cursor = get_db().execute(
        """
        INSERT INTO submissions (user_id, task_number, text_content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user["id"], task_number, text_content, timestamp, timestamp),
    )
    submission_id = cursor.lastrowid
    for file_storage in files:
        if file_storage and file_storage.filename:
            save_file(file_storage, submission_id)
    return submission_id


def upsert_submission(user: dict, task_number: str, text_content: str, files: Iterable) -> int:
    db = get_db()
    timestamp = current_timestamp()
    existing = db.execute(
        """
        SELECT id, text_content
        FROM submissions
        WHERE user_id = ? AND task_number = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user["id"], task_number),
    ).fetchone()

    file_list = [file for file in files if file and file.filename]
    if existing is None:
        return create_submission(user, task_number, text_content, file_list)

    submission_id = existing["id"]
    next_text = text_content if text_content else existing["text_content"]
    db.execute(
        """
        UPDATE submissions
        SET text_content = ?, admin_answer = '', ai_answer = '', answered_at = NULL, ai_generated_at = NULL, updated_at = ?
        WHERE id = ?
        """,
        (next_text, timestamp, submission_id),
    )

    if file_list:
        delete_submission_files(submission_id, db)
        for file_storage in file_list:
            save_file(file_storage, submission_id)
    return submission_id


def fetch_allowed_nicknames() -> list[str]:
    rows = get_db().execute("SELECT nickname FROM ai_allowed_nicknames ORDER BY nickname COLLATE NOCASE").fetchall()
    return [row["nickname"] for row in rows]


def is_ai_allowed_for_nickname(nickname: str) -> bool:
    nickname = normalize_text(nickname)
    if not nickname:
        return False
    row = get_db().execute(
        "SELECT nickname FROM ai_allowed_nicknames WHERE nickname = ? COLLATE NOCASE",
        (nickname,),
    ).fetchone()
    return row is not None


def get_submission_files(submission_id: int, connection: sqlite3.Connection | None = None) -> list[dict]:
    db = connection or get_db()
    rows = db.execute(
        """
        SELECT original_name, stored_name
        FROM submission_files
        WHERE submission_id = ?
        ORDER BY id
        """,
        (submission_id,),
    ).fetchall()
    return [
        {
            "original_name": row["original_name"],
            "stored_name": row["stored_name"],
        }
        for row in rows
    ]


def build_submission_payload(base: dict) -> dict:
    admin_answer = normalize_text(base.get("admin_answer", ""))
    ai_answer = normalize_text(base.get("ai_answer", ""))
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


def fetch_submission(submission_id: int, connection: sqlite3.Connection | None = None) -> dict | None:
    db = connection or get_db()
    row = db.execute(
        """
        SELECT s.id, s.user_id, u.uid AS user_uid, u.nickname AS user_nickname,
               u.current_task AS user_current_task,
               s.task_number, s.text_content, s.admin_answer, s.ai_answer,
               s.created_at, s.updated_at, s.answered_at, s.ai_generated_at
        FROM submissions s
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.id = ?
        """,
        (submission_id,),
    ).fetchone()
    if not row:
        return None
    return build_submission_payload({
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
        "files": get_submission_files(row["id"], db),
    })


def fetch_submissions() -> list[dict]:
    rows = get_db().execute(
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
    ).fetchall()
    if not rows:
        return []

    submission_ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in submission_ids)
    file_rows = get_db().execute(
        f"""
        SELECT submission_id, original_name, stored_name
        FROM submission_files
        WHERE submission_id IN ({placeholders})
        ORDER BY id
        """,
        submission_ids,
    ).fetchall()
    files_by_submission: dict[int, list[dict]] = {}
    for row in file_rows:
        files_by_submission.setdefault(row["submission_id"], []).append(
            {
                "original_name": row["original_name"],
                "stored_name": row["stored_name"],
            }
        )

    return [
        build_submission_payload({
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
        })
        for row in rows
    ]


def _is_text_file(filename: str, mime_type: str) -> bool:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return mime_type.startswith("text/") or extension in {"txt", "md", "html", "xml"}


def build_file_part(stored_name: str, original_name: str) -> dict | None:
    file_path = UPLOAD_DIR / stored_name
    if not file_path.exists() or not file_path.is_file():
        return None
    if file_path.stat().st_size > Config.OPENAI_MAX_INLINE_BYTES:
        return None

    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    if _is_text_file(original_name, mime_type):
        text = file_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        return {"type": "input_text", "text": f"Содержимое файла {original_name}:\n{text}"}

    encoded = base64.b64encode(file_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    if mime_type.startswith("image/"):
        return {"type": "input_image", "image_url": data_url, "detail": "high"}
    return {"type": "input_file", "filename": original_name, "file_data": data_url}


def generate_ai_answer_for_submission(submission: dict, ai_settings: dict[str, object] | None = None) -> str:
    ai_settings = ai_settings or get_ai_settings()
    if not ai_settings["enabled"]:
        raise RuntimeError("AI отключен в настройках")
    if not Config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY не задан")

    prompt_lines = [str(ai_settings.get("prompt") or DEFAULT_AI_PROMPT).strip()]
    prompt_lines.append(f"Номер задания: {submission['task_number']}")
    nickname = normalize_text(submission.get("user_nickname"))
    if nickname:
        prompt_lines.append(f"Ник пользователя: {nickname}")
    text_content = normalize_text(submission.get("text_content", ""))
    if text_content:
        prompt_lines.append("Текст задания:")
        prompt_lines.append(text_content)

    content = [{"type": "input_text", "text": "\n".join(prompt_lines)}]
    for file_info in submission.get("files", []):
        file_part = build_file_part(file_info["stored_name"], file_info["original_name"])
        if file_part:
            content.append(file_part)

    response_payload = {
        "model": ai_settings["model"],
        "input": [{"role": "user", "content": content}],
        "store": False,
        "max_output_tokens": Config.OPENAI_MAX_OUTPUT_TOKENS,
    }
    if Config.OPENAI_REASONING_EFFORT:
        response_payload["reasoning"] = {"effort": Config.OPENAI_REASONING_EFFORT}

    http = getattr(REQUEST_LOCAL, "http", None)
    if http is None:
        http = requests.Session()
        REQUEST_LOCAL.http = http

    response = None
    retry_statuses = {429, 500, 502, 503, 504}
    for attempt in range(Config.OPENAI_MAX_RETRIES + 1):
        response = http.post(
            f"{Config.OPENAI_API_URL}/responses",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=response_payload,
            timeout=(5, 60),
        )
        if response.status_code not in retry_statuses or attempt >= Config.OPENAI_MAX_RETRIES:
            break
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except ValueError:
            delay = Config.OPENAI_RETRY_BASE_SECONDS * (2 ** attempt)
        time.sleep(min(max(delay, 0.2), 10))
    response.raise_for_status()
    data = response.json()
    answer_text = str(data.get("output_text") or "").strip()
    if not answer_text:
        texts = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text"):
                    texts.append(part["text"])
        answer_text = "\n".join(texts).strip()
    if not answer_text:
        raise RuntimeError("OpenAI не вернул текст ответа")
    return answer_text


def run_auto_ai_generation(submission_id: int) -> None:
    connection: sqlite3.Connection | None = None
    try:
        max_attempts = max(1, Config.AI_JOB_MAX_ATTEMPTS)
        retry_delays = Config.AI_JOB_RETRY_DELAYS_SECONDS or [15, 60, 180]
        for attempt in range(max_attempts):
            try:
                connection = db_connect()
                submission = fetch_submission(submission_id, connection)
                if not submission:
                    return
                answer_text = generate_ai_answer_for_submission(submission, get_ai_settings(connection))
                timestamp = current_timestamp()
                connection.execute(
                    """
                    UPDATE submissions
                    SET ai_answer = ?, ai_generated_at = ?, updated_at = ?, answered_at = CASE WHEN TRIM(COALESCE(answered_at, '')) = '' THEN ? ELSE answered_at END
                    WHERE id = ?
                    """,
                    (answer_text, timestamp, timestamp, timestamp, submission_id),
                )
                connection.commit()
                return
            except Exception:
                if attempt >= max_attempts - 1:
                    return
                try:
                    if connection is not None:
                        connection.close()
                except Exception:
                    pass
                connection = None
                time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
    except Exception:
        pass
    finally:
        with AI_PENDING_LOCK:
            AI_PENDING_IDS.discard(submission_id)
        try:
            if connection is not None:
                connection.close()
        except Exception:
            pass


def maybe_schedule_ai_for_user(user: dict, submission_ids: list[int]) -> int:
    nickname = normalize_text(user.get("nickname"))
    ai_settings = get_ai_settings()
    if not nickname or not ai_settings["enabled"] or not Config.OPENAI_API_KEY or not is_ai_allowed_for_nickname(nickname):
        return 0
    queued = 0
    for submission_id in submission_ids:
        with AI_PENDING_LOCK:
            if submission_id in AI_PENDING_IDS:
                continue
            AI_PENDING_IDS.add(submission_id)
        AI_EXECUTOR.submit(run_auto_ai_generation, submission_id)
        queued += 1
    return queued


def parse_task_key(task_key: str) -> int:
    raw = normalize_text(task_key)
    if not raw.startswith("submission:"):
        raise ValueError("Некорректный task_key")
    return int(raw.split(":", 1)[1])


@app.route("/", methods=["GET"])
def index():
    current_user, is_new_user = get_or_create_current_user()
    answered_tasks, teacher_answers = fetch_answer_state(current_user["id"])
    answer_sources = fetch_answer_sources(current_user["id"])
    response = make_response(
        render_template(
            "index.html",
            task_numbers=TASK_NUMBERS,
            answered_tasks=answered_tasks,
            teacher_answers=teacher_answers,
            answer_sources=answer_sources,
            current_user=current_user,
        )
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/profile", methods=["POST"])
def save_profile():
    current_user, is_new_user = get_or_create_current_user()
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    get_db().execute(
        "UPDATE users SET nickname = ?, updated_at = ? WHERE id = ?",
        (nickname, current_timestamp(), current_user["id"]),
    )
    get_db().commit()
    current_user["nickname"] = nickname
    ai_queued = 0
    ai_settings = get_ai_settings()
    if nickname and ai_settings["enabled"] and Config.OPENAI_API_KEY and is_ai_allowed_for_nickname(nickname):
        rows = get_db().execute(
            """
            SELECT id
            FROM submissions
            WHERE user_id = ?
              AND TRIM(COALESCE(admin_answer, '')) = ''
              AND TRIM(COALESCE(ai_answer, '')) = ''
            """,
            (current_user["id"],),
        ).fetchall()
        ai_queued = maybe_schedule_ai_for_user(current_user, [row["id"] for row in rows])
    response = jsonify({"ok": True, "user": current_user, "ai_queued": ai_queued})
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/profile/current-task", methods=["POST"])
def save_current_task():
    current_user, is_new_user = get_or_create_current_user()
    task_number = normalize_text((request.get_json(silent=True) or {}).get("task_number", ""))
    if task_number and task_number not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400
    get_db().execute(
        "UPDATE users SET current_task = ?, updated_at = ? WHERE id = ?",
        (task_number, current_timestamp(), current_user["id"]),
    )
    get_db().commit()
    current_user["current_task"] = task_number
    response = jsonify({"ok": True, "user": current_user})
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/submit", methods=["POST"])
def submit():
    current_user, is_new_user = get_or_create_current_user()
    text_content = normalize_text(request.form.get("text_content", ""))
    selected_task = request.form.get("task_number") or None
    uploaded_files = [file for file in request.files.getlist("files") if file and file.filename]

    if not text_content and not uploaded_files:
        response = jsonify({"ok": False, "error": "Добавьте текст, файл или оба варианта сразу."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    if selected_task and selected_task not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    item_count = max(len(uploaded_files), 1)
    try:
        assigned_tasks = allocate_task_numbers(current_user["id"], selected_task, item_count)
    except ValueError as error:
        response = jsonify({"ok": False, "error": str(error)})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    created_ids: list[int] = []
    if uploaded_files:
        for index, file_storage in enumerate(uploaded_files):
            created_ids.append(upsert_submission(current_user, assigned_tasks[index], text_content, [file_storage]))
    else:
        created_ids.append(upsert_submission(current_user, assigned_tasks[0], text_content, []))
    get_db().commit()

    ai_queued = maybe_schedule_ai_for_user(current_user, created_ids)

    response = jsonify(
        {
            "ok": True,
            "message": "Ответ отправлен",
            "assigned_tasks": assigned_tasks,
            "ai_queued": ai_queued,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/answers", methods=["GET"])
def answers():
    current_user, is_new_user = get_or_create_current_user()
    answered_tasks, teacher_answers = fetch_answer_state(current_user["id"])
    answer_sources = fetch_answer_sources(current_user["id"])
    response = jsonify(
        {
            "ok": True,
            "answered_tasks": sorted(answered_tasks, key=task_number_sort_key),
            "teacher_answers": teacher_answers,
            "answer_sources": answer_sources,
            "user": current_user,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    return jsonify({"ok": True, "tasks": fetch_submissions()})


@app.route("/my-summary", methods=["GET"])
def my_summary():
    current_user, is_new_user = get_or_create_current_user()
    rows = get_db().execute(
        """
        SELECT id, task_number, text_content, created_at
        FROM submissions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (current_user["id"],),
    ).fetchall()
    uploads = []
    for row in rows:
        uploads.append(
            {
                "id": row["id"],
                "task_number": row["task_number"],
                "text_content": row["text_content"],
                "created": row["created_at"],
                "files": get_submission_files(row["id"]),
            }
        )
    response = jsonify(
        {
            "ok": True,
            "uploads": uploads,
            "answers": fetch_teacher_answers(current_user["id"]),
            "task_numbers": TASK_NUMBERS,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/admin", methods=["GET"])
def admin():
    gate = admin_required()
    if gate is not None:
        return gate
    return render_template(
        "admin.html",
        submissions=fetch_submissions(),
        ai_allowed_nicknames=fetch_allowed_nicknames(),
        ai_enabled=bool(get_ai_settings()["enabled"] and Config.OPENAI_API_KEY),
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    next_url = request.values.get("next") or url_for("admin")
    if request.method == "POST":
        password = normalize_text(request.form.get("password", ""))
        if password == Config.ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(next_url)
        error = "Неверный пароль"
    return render_template("admin_login.html", error=error, next_url=next_url)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/settings", methods=["GET"])
def admin_settings():
    gate = admin_required()
    if gate is not None:
        return gate
    ai_settings = get_ai_settings()
    return render_template(
        "admin_settings.html",
        ai_allowed_nicknames=fetch_allowed_nicknames(),
        config_view={
            "AI_ENABLED": ai_settings["enabled"],
            "OPENAI_MODEL": ai_settings["model"],
            "AI_PROMPT": ai_settings["prompt"],
            "OPENAI_API_URL": Config.OPENAI_API_URL,
            "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
            "ADMIN_PASSWORD_SET": bool(Config.ADMIN_PASSWORD),
        },
    )


@app.route("/api/admin/settings/ai", methods=["POST"])
def save_ai_settings():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    payload = request.get_json(silent=True) or {}
    model = normalize_text(payload.get("model", ""))
    if not model:
        return jsonify({"ok": False, "error": "Укажите модель."}), 400
    prompt = normalize_text(payload.get("prompt", ""))
    if not prompt:
        return jsonify({"ok": False, "error": "Укажите промпт для AI."}), 400
    enabled = bool(payload.get("enabled"))
    update_app_settings({
        "ai_enabled": "1" if enabled else "0",
        "openai_model": model,
        "ai_prompt": prompt,
    })
    return jsonify({
        "ok": True,
        "settings": {
            "AI_ENABLED": enabled,
            "OPENAI_MODEL": model,
            "AI_PROMPT": prompt,
            "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
        },
    })


@app.route("/api/ai-allowed", methods=["POST"])
@app.route("/admin/ai-allowed", methods=["POST"])
def add_ai_allowed_nickname():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    if not nickname:
        return jsonify({"ok": False, "error": "Укажите ник."}), 400
    get_db().execute(
        "INSERT OR IGNORE INTO ai_allowed_nicknames (nickname, created_at) VALUES (?, ?)",
        (nickname, current_timestamp()),
    )
    get_db().commit()

    rows = get_db().execute(
        """
        SELECT s.id
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        WHERE u.nickname = ? COLLATE NOCASE
          AND TRIM(COALESCE(s.admin_answer, '')) = ''
          AND TRIM(COALESCE(s.ai_answer, '')) = ''
        """,
        (nickname,),
    ).fetchall()
    maybe_schedule_ai_for_user({"nickname": nickname}, [row["id"] for row in rows])
    return jsonify({"ok": True, "nicknames": fetch_allowed_nicknames(), "queued": len(rows)})


@app.route("/api/ai-allowed/<path:nickname>", methods=["DELETE"])
@app.route("/admin/ai-allowed/<path:nickname>", methods=["DELETE"])
def remove_ai_allowed_nickname(nickname: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    get_db().execute("DELETE FROM ai_allowed_nicknames WHERE nickname = ? COLLATE NOCASE", (nickname,))
    get_db().commit()
    return jsonify({"ok": True, "nicknames": fetch_allowed_nicknames()})


@app.route("/api/tasks/<path:task_key>", methods=["PATCH"])
def patch_task(task_key: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    try:
        submission_id = parse_task_key(task_key)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    payload = request.get_json(silent=True) or {}
    answer_text = normalize_text(payload.get("answer_text", ""))
    timestamp = current_timestamp()
    updated = get_db().execute(
        """
        UPDATE submissions
        SET admin_answer = ?, updated_at = ?, answered_at = ?
        WHERE id = ?
        """,
        (answer_text, timestamp, timestamp if answer_text else None, submission_id),
    )
    get_db().commit()
    if updated.rowcount == 0:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    return jsonify({"ok": True, "task": fetch_submission(submission_id)})


@app.route("/admin/submission/<int:submission_id>/answer", methods=["POST"])
def save_admin_answer(submission_id: int):
    gate = admin_required()
    if gate is not None:
        return gate if not request.is_json else (jsonify({"ok": False, "error": "Нужен вход в админку"}), 401)
    payload = request.get_json(silent=True) or {}
    answer = normalize_text(payload.get("admin_answer", request.form.get("admin_answer", "")))
    timestamp = current_timestamp()
    answered_at = timestamp if answer else None
    updated = get_db().execute(
        """
        UPDATE submissions
        SET admin_answer = ?, updated_at = ?, answered_at = ?
        WHERE id = ?
        """,
        (answer, timestamp, answered_at, submission_id),
    )
    get_db().commit()

    if updated.rowcount == 0:
        if request.is_json:
            return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
        flash("Загрузка не найдена.", "error")
        return redirect(url_for("admin"))

    if request.is_json:
        return jsonify({"ok": True, "submission": fetch_submission(submission_id)})
    flash("Ответ администратора сохранен.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/submission/<int:submission_id>/generate-ai", methods=["POST"])
def generate_ai():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    submission_id = int(request.view_args["submission_id"])
    submission = fetch_submission(submission_id)
    if not submission:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    try:
        ai_answer = generate_ai_answer_for_submission(submission)
    except Exception as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    timestamp = current_timestamp()
    get_db().execute(
        """
        UPDATE submissions
        SET ai_answer = ?, ai_generated_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (ai_answer, timestamp, timestamp, submission_id),
    )
    get_db().commit()
    return jsonify({"ok": True, "submission": fetch_submission(submission_id)})


@app.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file_alias(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/healthz", methods=["GET"])
def healthz():
    get_db().execute("SELECT 1").fetchone()
    return jsonify({"ok": True})


@app.context_processor
def inject_globals():
    return {
        "task_numbers_json": json.dumps(TASK_NUMBERS, ensure_ascii=False),
        "task_contents_json": json.dumps(TASK_CONTENTS, ensure_ascii=False),
    }


init_db()


if __name__ == "__main__":
    app.run(debug=True)
