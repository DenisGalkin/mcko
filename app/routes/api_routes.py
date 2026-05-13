from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..config import Config
from ..repositories import ai_allowed, settings, submissions
from ..services.ai_service import ai_job_runner
from ..services.submission_service import submission_service
from ..services.text import normalize_text
from .auth import admin_required


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
    answer_text = normalize_text(payload.get("answer_text", ""))
    updated_count = submissions.update_submission_admin_answer(submission_id, answer_text)
    if updated_count == 0:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    return jsonify({"ok": True, "task": submissions.fetch_submission(submission_id)})
