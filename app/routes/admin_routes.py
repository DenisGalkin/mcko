from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from ..config import Config
from ..db import session as db_session
from ..repositories import ai_allowed, settings, submissions
from ..services.ai_service import ai_service
from ..services.text import normalize_text
from .auth import admin_required


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin", methods=["GET"])
def admin():
    gate = admin_required()
    if gate is not None:
        return gate
    ai_settings = settings.get_ai_settings()
    return render_template(
        "admin_dashboard.html",
        submissions=submissions.fetch_submissions(),
        ai_allowed_nicknames=ai_allowed.fetch_allowed_nicknames(),
        ai_enabled=bool(ai_settings.enabled and Config.OPENAI_API_KEY),
    )


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    next_url = request.values.get("next") or url_for("admin.admin")
    if request.method == "POST":
        password = normalize_text(request.form.get("password", ""))
        if password == Config.ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(next_url)
        error = "Неверный пароль"
    return render_template("admin_login.html", error=error, next_url=next_url)


@admin_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin.admin_login"))


@admin_bp.route("/admin/settings", methods=["GET"])
def admin_settings():
    gate = admin_required()
    if gate is not None:
        return gate
    ai_settings = settings.get_ai_settings()
    return render_template(
        "admin_settings.html",
        ai_allowed_nicknames=ai_allowed.fetch_allowed_nicknames(),
        config_view={
            "AI_ENABLED": ai_settings.enabled,
            "OPENAI_MODEL": ai_settings.model,
            "AI_PROMPT": ai_settings.prompt,
            "OPENAI_API_URL": Config.OPENAI_API_URL,
            "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
            "ADMIN_PASSWORD_SET": bool(Config.ADMIN_PASSWORD),
        },
    )


@admin_bp.route("/admin/submission/<int:submission_id>/answer", methods=["POST"])
def save_admin_answer(submission_id: int):
    gate = admin_required()
    if gate is not None:
        return gate if not request.is_json else (jsonify({"ok": False, "error": "Нужен вход в админку"}), 401)
    payload = request.get_json(silent=True) or {}
    answer = normalize_text(payload.get("admin_answer", request.form.get("admin_answer", "")))
    updated_count = submissions.update_submission_admin_answer(submission_id, answer)

    if updated_count == 0:
        if request.is_json:
            return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
        flash("Загрузка не найдена.", "error")
        return redirect(url_for("admin.admin"))

    if request.is_json:
        return jsonify({"ok": True, "submission": submissions.fetch_submission(submission_id)})
    flash("Ответ администратора сохранен.", "success")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/submission/<int:submission_id>/generate-ai", methods=["POST"])
def generate_ai(submission_id: int):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    submission = submissions.fetch_submission(submission_id)
    if not submission:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    try:
        ai_answer = ai_service.generate_answer_for_submission(submission)
    except Exception as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    submissions.update_submission_ai_answer(submission_id, ai_answer)
    db_session.commit()
    return jsonify({"ok": True, "submission": submissions.fetch_submission(submission_id)})
