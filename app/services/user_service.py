from __future__ import annotations

from flask import request

from ..repositories import users
from ..settings import USER_COOKIE_NAME
from .text import normalize_text


class UserService:
    def get_or_create_current_user(self) -> tuple[dict, bool]:
        uid = normalize_text(request.cookies.get(USER_COOKIE_NAME))
        return users.get_or_create_user(uid)

    def with_user_cookie(self, response, uid: str):
        response.set_cookie(
            USER_COOKIE_NAME,
            uid,
            max_age=60 * 60 * 24 * 365 * 5,
            samesite="Lax",
            httponly=True,
        )
        return response

    def save_nickname(self, user: dict, nickname: str) -> dict:
        users.update_user_nickname(user["id"], nickname)
        next_user = dict(user)
        next_user["nickname"] = nickname
        return next_user

    def save_current_task(self, user: dict, task_number: str) -> dict:
        users.update_user_current_task(user["id"], task_number)
        next_user = dict(user)
        next_user["current_task"] = task_number
        return next_user


user_service = UserService()
