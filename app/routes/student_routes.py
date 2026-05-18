from __future__ import annotations

from flask import Blueprint, jsonify, make_response, render_template, request

from ..config import Config
from ..repositories import ai_allowed, settings, submissions
from ..services.ai_service import ai_job_runner
from ..services.submission_service import submission_service
from ..services.text import normalize_text
from ..services.user_service import user_service
from ..settings import TASK_CONTENTS, TASK_NUMBERS, task_number_sort_key


student_bp = Blueprint("student", __name__)


def with_cookie_if_needed(response, is_new_user: bool, uid: str):
    if is_new_user:
        return user_service.with_user_cookie(response, uid)
    return response


@student_bp.route("/", methods=["GET"])
def index():
    current_user, is_new_user = user_service.get_or_create_current_user()
    requested_task = normalize_text(request.args.get("n", ""))
    if requested_task in TASK_NUMBERS:
        selected_task = requested_task
    elif current_user.get("current_task") in TASK_NUMBERS:
        selected_task = current_user["current_task"]
    else:
        selected_task = TASK_NUMBERS[0] if TASK_NUMBERS else ""

    if selected_task and current_user.get("current_task") != selected_task:
        current_user = user_service.save_current_task(current_user, selected_task)

    answered_tasks, teacher_answers, answer_sources = submissions.fetch_answer_overview(current_user["id"])
    response = make_response(
        render_template(
            "student_exam.html",
            task_numbers=TASK_NUMBERS,
            selected_task=selected_task,
            selected_task_html=TASK_CONTENTS.get(selected_task, ""),
            answered_tasks=answered_tasks,
            teacher_answers=teacher_answers,
            answer_sources=answer_sources,
            current_user=current_user,
        )
    )
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])


@student_bp.route("/profile", methods=["POST"])
def save_profile():
    current_user, is_new_user = user_service.get_or_create_current_user()
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    current_user = user_service.save_nickname(current_user, nickname)
    ai_queued = 0
    ai_settings = settings.get_ai_settings()
    if nickname and ai_settings.enabled and Config.OPENAI_API_KEY:
        submission_ids = submissions.fetch_unanswered_submission_ids_for_user(current_user["id"])
        ai_queued = ai_job_runner.maybe_schedule_for_user(current_user, submission_ids, ai_settings)
    response = jsonify({"ok": True, "user": current_user, "ai_queued": ai_queued})
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])


@student_bp.route("/profile/current-task", methods=["POST"])
def save_current_task():
    current_user, is_new_user = user_service.get_or_create_current_user()
    task_number = normalize_text((request.get_json(silent=True) or {}).get("task_number", ""))
    if task_number and task_number not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        return with_cookie_if_needed(response, is_new_user, current_user["uid"]), 400
    current_user = user_service.save_current_task(current_user, task_number)
    response = jsonify({"ok": True, "user": current_user})
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])


@student_bp.route("/submit", methods=["POST"])
def submit():
    current_user, is_new_user = user_service.get_or_create_current_user()
    nickname = normalize_text(current_user.get("nickname", ""))
    if settings.get_upload_settings().require_login and not ai_allowed.is_special_login(nickname):
        response = jsonify({"ok": False, "error": "Для загрузки задания укажите логин из списка специальных логинов."})
        return with_cookie_if_needed(response, is_new_user, current_user["uid"]), 403

    text_content = normalize_text(request.form.get("text_content", ""))
    selected_task = request.form.get("task_number") or None
    uploaded_files = [file for file in request.files.getlist("files") if file and file.filename]

    if not text_content and not uploaded_files:
        response = jsonify({"ok": False, "error": "Добавьте текст, файл или оба варианта сразу."})
        return with_cookie_if_needed(response, is_new_user, current_user["uid"]), 400

    if selected_task and selected_task not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        return with_cookie_if_needed(response, is_new_user, current_user["uid"]), 400

    item_count = max(len(uploaded_files), 1)
    try:
        assigned_tasks = submission_service.allocate_task_numbers(current_user["id"], selected_task, item_count)
    except ValueError as error:
        response = jsonify({"ok": False, "error": str(error)})
        return with_cookie_if_needed(response, is_new_user, current_user["uid"]), 400

    created_ids: list[int] = []
    if uploaded_files:
        for index, file_storage in enumerate(uploaded_files):
            created_ids.append(
                submission_service.upsert_submission(current_user, assigned_tasks[index], text_content, [file_storage])
            )
    else:
        created_ids.append(submission_service.upsert_submission(current_user, assigned_tasks[0], text_content, []))
    submission_service.commit()

    ai_queued = ai_job_runner.maybe_schedule_for_user(current_user, created_ids)

    response = jsonify(
        {
            "ok": True,
            "message": "Ответ отправлен",
            "assigned_tasks": assigned_tasks,
            "ai_queued": ai_queued,
        }
    )
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])


@student_bp.route("/answers", methods=["GET"])
def answers():
    current_user, is_new_user = user_service.get_or_create_current_user()
    answered_tasks, teacher_answers, answer_sources = submissions.fetch_answer_overview(current_user["id"])
    response = jsonify(
        {
            "ok": True,
            "answered_tasks": sorted(answered_tasks, key=task_number_sort_key),
            "teacher_answers": teacher_answers,
            "answer_sources": answer_sources,
            "user": current_user,
        }
    )
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])


@student_bp.route("/my-summary", methods=["GET"])
def my_summary():
    current_user, is_new_user = user_service.get_or_create_current_user()
    response = jsonify(
        {
            "ok": True,
            "uploads": submissions.fetch_user_summary_uploads(current_user["id"]),
            "answers": submissions.fetch_teacher_answers(current_user["id"]),
            "task_numbers": TASK_NUMBERS,
        }
    )
    return with_cookie_if_needed(response, is_new_user, current_user["uid"])
