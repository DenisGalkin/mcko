from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ..db import session as db_session
from ..db.schema import current_timestamp, submission_files, submissions
from .common import execute_text, row_to_dict


def get_user_answer_expression() -> str:
    return "CASE WHEN TRIM(COALESCE(admin_answer, '')) <> '' THEN admin_answer ELSE ai_answer END"


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


def fetch_answer_overview(user_id: int) -> tuple[set[str], dict[str, str], dict[str, str]]:
    answer_expression = get_user_answer_expression()
    rows = execute_text(
        f"""
        SELECT s.task_number,
               {answer_expression} AS answer_text,
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
    teacher_answers = {row["task_number"]: row["answer_text"] for row in rows}
    answer_sources = {row["task_number"]: row["answer_source"] for row in rows}
    return set(teacher_answers.keys()), teacher_answers, answer_sources


def fetch_answer_state(user_id: int) -> tuple[set[str], dict[str, str]]:
    answered_tasks, teacher_answers, _answer_sources = fetch_answer_overview(user_id)
    return answered_tasks, teacher_answers


def fetch_files_for_submissions(submission_ids: Sequence[int], session: Session | None = None) -> dict[int, list[dict]]:
    if not submission_ids:
        return {}

    rows = (session or db_session.get_session()).execute(
        select(
            submission_files.c.submission_id,
            submission_files.c.original_name,
            submission_files.c.stored_name,
        )
        .where(submission_files.c.submission_id.in_(submission_ids))
        .order_by(submission_files.c.id)
    ).mappings().all()
    files_by_submission: dict[int, list[dict]] = {}
    for row in rows:
        files_by_submission.setdefault(row["submission_id"], []).append(
            {"original_name": row["original_name"], "stored_name": row["stored_name"]}
        )
    return files_by_submission


def fetch_used_tasks(user_id: int) -> list[str]:
    rows = execute_text(
        "SELECT DISTINCT task_number FROM submissions WHERE user_id = :user_id ORDER BY id",
        {"user_id": user_id},
    ).mappings().all()
    return [row["task_number"] for row in rows]


def add_submission_file(submission_id: int, original_name: str, stored_name: str) -> None:
    db_session.get_session().execute(
        insert(submission_files).values(
            submission_id=submission_id,
            original_name=original_name,
            stored_name=stored_name,
        )
    )


def fetch_submission_file_stored_names(submission_id: int, session: Session | None = None) -> list[str]:
    rows = (session or db_session.get_session()).execute(
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
    result = db_session.get_session().execute(
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

    files_by_submission = fetch_files_for_submissions([row["id"] for row in rows])

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
    files_by_submission = fetch_files_for_submissions([row["id"] for row in rows])
    return [
        {
            "id": row["id"],
            "task_number": row["task_number"],
            "text_content": row["text_content"],
            "created": row["created_at"],
            "files": files_by_submission.get(row["id"], []),
        }
        for row in rows
    ]


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
    db_session.commit()
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
