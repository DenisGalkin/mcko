from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
DATABASE_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
TASK_NUMBERS = [str(number) for number in range(1, 18)]
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


def load_task_contents() -> dict[str, str]:
    try:
        data = json.loads(TASK_CONTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def task_number_sort_key(task_number: str) -> tuple[int, int | str]:
    task_number = str(task_number)
    if task_number in TASK_NUMBERS:
        return (0, TASK_NUMBERS.index(task_number))
    return (1, task_number)


TASK_CONTENTS = load_task_contents()
