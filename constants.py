from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
DATABASE_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
TASK_NUMBERS = ["1", "2", "3", "4", "5", "6.1", "6.2", "7", "8", "9", "10", "11", "12", "13"]
USER_COOKIE_NAME = "mcko_uid"
DEFAULT_AI_PROMPT = "\n".join(
    [
        "Реши школьное задание на русском языке.",
        "Верни только готовый ответ без markdown и без лишних пояснений.",
        "Если у задания несколько пунктов, ответь на каждый.",
        "Проверь орфографию перед выводом.",
    ]
)
