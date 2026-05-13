from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..config import Config
from ..repositories import ai_allowed, settings, submissions
from ..services.ai_service import ai_job_runner
from ..services.submission_service import submission_service
from ..services.text import normalize_text
from .auth import admin_required, get_admin_worker_id


api_bp = Blueprint("api", __name__)


@api_bp.route("/api/tasks", methods=["GET"])
def api_tasks():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    return jsonify({"ok": True, "tasks": submissions.fetch_submissions()})


@api_bp.route("/api/admin/settings/ai", methods=["POST"])
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
    settings.update_app_settings(
        {
            "ai_enabled": "1" if enabled else "0",
            "openai_model": model,
            "ai_prompt": prompt,
        }
    )
    return jsonify(
        {
            "ok": True,
            "settings": {
                "AI_ENABLED": enabled,
                "OPENAI_MODEL": model,
                "AI_PROMPT": prompt,
                "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
            },
        }
    )


@api_bp.route("/api/admin/settings/uploads", methods=["POST"])
def save_upload_settings():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    payload = request.get_json(silent=True) or {}
    require_login = bool(payload.get("require_login"))
    settings.update_app_settings({"require_login_for_upload": "1" if require_login else "0"})
    return jsonify({"ok": True, "settings": {"REQUIRE_LOGIN_FOR_UPLOAD": require_login}})


def normalize_karma(value) -> int:
    try:
        karma = int(value)
    except (TypeError, ValueError):
        raise ValueError("Карма должна быть числом.") from None
    return max(-10000, min(10000, karma))


@api_bp.route("/api/special-logins", methods=["POST"])
def add_special_login():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    payload = request.get_json(silent=True) or {}
    nickname = normalize_text(payload.get("nickname", ""))
    if not nickname:
        return jsonify({"ok": False, "error": "Укажите логин."}), 400
    try:
        karma = normalize_karma(payload.get("karma", 100))
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    ai_enabled = bool(payload.get("ai_enabled", True))
    ai_allowed.upsert_special_login(nickname, ai_enabled=ai_enabled, karma=karma)

    queued = 0
    if ai_enabled:
        submission_ids = ai_allowed.fetch_unanswered_submission_ids_for_nickname(nickname)
        queued = ai_job_runner.maybe_schedule_for_user({"nickname": nickname}, submission_ids)
    return jsonify({"ok": True, "special_logins": ai_allowed.fetch_special_logins(), "queued": queued})


@api_bp.route("/api/special-logins/<path:nickname>", methods=["PATCH"])
def update_special_login(nickname: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        karma = normalize_karma(payload.get("karma", 100))
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    ai_enabled = bool(payload.get("ai_enabled"))
    updated_count = ai_allowed.update_special_login(nickname, ai_enabled=ai_enabled, karma=karma)
    if updated_count == 0:
        return jsonify({"ok": False, "error": "Логин не найден."}), 404

    queued = 0
    if ai_enabled:
        submission_ids = ai_allowed.fetch_unanswered_submission_ids_for_nickname(nickname)
        queued = ai_job_runner.maybe_schedule_for_user({"nickname": nickname}, submission_ids)
    return jsonify({"ok": True, "special_logins": ai_allowed.fetch_special_logins(), "queued": queued})


@api_bp.route("/api/special-logins/<path:nickname>", methods=["DELETE"])
def delete_special_login(nickname: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    ai_allowed.remove_ai_allowed_nickname(nickname)
    return jsonify({"ok": True, "special_logins": ai_allowed.fetch_special_logins()})


@api_bp.route("/api/ai-allowed", methods=["POST"])
@api_bp.route("/admin/ai-allowed", methods=["POST"])
def add_ai_allowed_nickname():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    if not nickname:
        return jsonify({"ok": False, "error": "Укажите ник."}), 400
    ai_allowed.add_ai_allowed_nickname(nickname)

    submission_ids = ai_allowed.fetch_unanswered_submission_ids_for_nickname(nickname)
    ai_job_runner.maybe_schedule_for_user({"nickname": nickname}, submission_ids)
    return jsonify({"ok": True, "nicknames": ai_allowed.fetch_allowed_nicknames(), "queued": len(submission_ids)})


@api_bp.route("/api/ai-allowed/<path:nickname>", methods=["DELETE"])
@api_bp.route("/admin/ai-allowed/<path:nickname>", methods=["DELETE"])
def remove_ai_allowed_nickname(nickname: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    ai_allowed.remove_ai_allowed_nickname(nickname)
    return jsonify({"ok": True, "nicknames": ai_allowed.fetch_allowed_nicknames()})


@api_bp.route("/api/tasks/<path:task_key>", methods=["PATCH"])
def patch_task(task_key: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    try:
        submission_id = submission_service.parse_task_key(task_key)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    payload = request.get_json(silent=True) or {}
    if "admin_in_progress" in payload:
        if bool(payload.get("admin_in_progress")):
            ok, error = submissions.claim_submission_for_admin(submission_id, get_admin_worker_id())
        else:
            ok, error = submissions.release_submission_for_admin(submission_id, get_admin_worker_id())
        if not ok:
            return jsonify({"ok": False, "error": error}), 400

    if "answer_text" in payload:
        answer_text = normalize_text(payload.get("answer_text", ""))
        updated_count = submissions.update_submission_admin_answer(submission_id, answer_text)
        if updated_count == 0:
            return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    return jsonify({"ok": True, "task": submissions.fetch_submission(submission_id)})
