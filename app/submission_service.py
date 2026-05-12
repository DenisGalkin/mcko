from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable

from werkzeug.utils import secure_filename

from . import database
from .settings import TASK_NUMBERS, UPLOAD_DIR


def allocate_task_numbers(user_id: int, start_task: str | None, count: int) -> list[str]:
    if count <= 0:
        return []

    if start_task:
        start_index = TASK_NUMBERS.index(start_task)
    else:
        used_tasks = set(database.fetch_used_tasks(user_id))
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
    database.add_submission_file(submission_id, original_name or stored_name, stored_name)


def delete_submission_files(submission_id: int) -> None:
    for stored_name in database.fetch_submission_file_stored_names(submission_id):
        file_path = UPLOAD_DIR / stored_name
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
    database.delete_submission_file_rows(submission_id)


def create_submission(user: dict, task_number: str, text_content: str, files: Iterable) -> int:
    submission_id = database.create_submission(user["id"], task_number, text_content)
    for file_storage in files:
        if file_storage and file_storage.filename:
            save_file(file_storage, submission_id)
    return submission_id


def upsert_submission(user: dict, task_number: str, text_content: str, files: Iterable) -> int:
    existing = database.find_latest_submission_for_task(user["id"], task_number)
    file_list = [file for file in files if file and file.filename]
    if existing is None:
        return create_submission(user, task_number, text_content, file_list)

    submission_id = existing["id"]
    next_text = text_content if text_content else existing["text_content"]
    database.reset_submission_content(submission_id, next_text)

    if file_list:
        delete_submission_files(submission_id)
        for file_storage in file_list:
            save_file(file_storage, submission_id)
    return submission_id


def parse_task_key(task_key: str) -> int:
    raw = str(task_key or "").strip()
    if not raw.startswith("submission:"):
        raise ValueError("Некорректный task_key")
    return int(raw.split(":", 1)[1])
