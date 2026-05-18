from __future__ import annotations

import json
import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
DATABASE_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
TASKS_DIR = PROJECT_ROOT / "tasks"
TASK_CONTENTS_PATH = PROJECT_ROOT / "app" / "static" / "mcko_26733" / "tasks.json"
USER_COOKIE_NAME = "mcko_uid"
DEFAULT_AI_PROMPT = "\n".join(
    [
        "Реши школьное задание на русском языке.",
        "Верни только готовый ответ без markdown и без лишних пояснений.",
        "Если у задания несколько пунктов, ответь на каждый.",
        "Проверь орфографию перед выводом.",
    ]
)


QUESTION_BLOCK_RE = re.compile(
    r'<div id="QuestionTest">\s*(.*?)\s*</div>\s*<!-- QuestionTest -->',
    re.IGNORECASE | re.DOTALL,
)


def parse_task_number(value: str) -> tuple[int, str]:
    task_number = str(value or "").strip()
    if task_number.isdigit():
        return (int(task_number), task_number)
    return (10**9, task_number)


def load_task_contents_from_pages() -> dict[str, str]:
    if not TASKS_DIR.exists():
        return {}

    task_contents: dict[str, str] = {}
    for page_path in sorted(TASKS_DIR.glob("*.htm"), key=lambda path: parse_task_number(path.stem)):
        match = QUESTION_BLOCK_RE.search(page_path.read_text(encoding="utf-8"))
        if not match:
            continue
        task_contents[str(page_path.stem)] = match.group(1).strip()
    return task_contents


def load_task_contents() -> dict[str, str]:
    task_contents = load_task_contents_from_pages()
    if task_contents:
        return task_contents
    try:
        data = json.loads(TASK_CONTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def task_number_sort_key(task_number: str) -> tuple[int, int | str]:
    parsed_number, raw_value = parse_task_number(task_number)
    return (0, parsed_number) if parsed_number != 10**9 else (1, raw_value)


TASK_CONTENTS = load_task_contents()
TASK_NUMBERS = sorted(TASK_CONTENTS.keys(), key=task_number_sort_key)
