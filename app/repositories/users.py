from __future__ import annotations

import random

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import session as db_session
from ..db.schema import current_timestamp, users
from .common import execute_text


def generate_short_user_id(session: Session) -> str:
    for _ in range(200):
        candidate = str(random.randint(1000, 9999))
        exists = session.execute(select(users.c.id).where(users.c.uid == candidate)).first()
        if not exists:
            return candidate
    raise RuntimeError("Не удалось подобрать свободный 4-значный ID")


def get_or_create_user(uid: str) -> tuple[dict, bool]:
    session = db_session.get_session()
    if uid:
        row = session.execute(select(users).where(users.c.uid == uid)).mappings().first()
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

    row = session.execute(select(users).where(users.c.id == result.inserted_primary_key[0])).mappings().one()
    return dict(row), True


def update_user_nickname(user_id: int, nickname: str) -> None:
    execute_text(
        "UPDATE users SET nickname = :nickname, updated_at = :updated_at WHERE id = :user_id",
        {"nickname": nickname, "updated_at": current_timestamp(), "user_id": user_id},
    )
    from . import submissions

    submissions.recalculate_user_task_priorities(user_id)
    db_session.commit()


def update_user_current_task(user_id: int, task_number: str) -> None:
    execute_text(
        "UPDATE users SET current_task = :task_number, updated_at = :updated_at WHERE id = :user_id",
        {"task_number": task_number, "updated_at": current_timestamp(), "user_id": user_id},
    )
    db_session.commit()
