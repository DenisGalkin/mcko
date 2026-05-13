from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import Config
from ..db import session as db_session
from ..db.schema import app_settings, current_timestamp
from ..models import AiSettings
from ..settings import DEFAULT_AI_PROMPT
def fetch_app_settings(session: Session | None = None) -> dict[str, str]:
    rows = (session or db_session.get_session()).execute(select(app_settings.c.key, app_settings.c.value)).mappings().all()
    return {row["key"]: row["value"] for row in rows}


def get_ai_settings(session: Session | None = None) -> AiSettings:
    settings = fetch_app_settings(session)
    enabled = str(settings.get("ai_enabled", "1" if Config.AI_ENABLED else "0")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    model = str(settings.get("openai_model", Config.OPENAI_MODEL) or "").strip() or Config.OPENAI_MODEL
    prompt = str(settings.get("ai_prompt", DEFAULT_AI_PROMPT) or "").strip() or DEFAULT_AI_PROMPT
    return AiSettings(enabled=enabled, model=model, prompt=prompt)


def update_app_settings(values: dict[str, str]) -> None:
    timestamp = current_timestamp()
    session = db_session.get_session()
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
