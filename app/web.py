from __future__ import annotations

import base64
import json
import logging
import mimetypes
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import (
    Flask,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from . import database
from . import submission_service
from .config import Config
from .settings import DEFAULT_AI_PROMPT, TASK_NUMBERS, UPLOAD_DIR, USER_COOKIE_NAME

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
AI_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, Config.AI_MAX_WORKERS), thread_name_prefix="ai-answer")
AI_PENDING_IDS: set[int] = set()
AI_PENDING_LOCK = threading.Lock()
REQUEST_LOCAL = threading.local()


def normalize_text(value: str) -> str:
    return str(value or "").strip()


def admin_is_authenticated() -> bool:
    return session.get("admin_authenticated") is True


def admin_required():
    if admin_is_authenticated():
        return None
    return redirect(url_for("admin_login", next=request.path))


@app.teardown_appcontext
def close_db(exception: BaseException | None) -> None:
    database.close_session(exception)


def get_or_create_current_user() -> tuple[dict, bool]:
    uid = normalize_text(request.cookies.get(USER_COOKIE_NAME))
    return database.get_or_create_user(uid)


def with_user_cookie(response, uid: str):
    response.set_cookie(
        USER_COOKIE_NAME,
        uid,
        max_age=60 * 60 * 24 * 365 * 5,
        samesite="Lax",
        httponly=True,
    )
    return response


def _is_text_file(filename: str, mime_type: str) -> bool:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return mime_type.startswith("text/") or extension in {"txt", "md", "html", "xml"}


def build_file_part(stored_name: str, original_name: str) -> dict | None:
    file_path = UPLOAD_DIR / stored_name
    if not file_path.exists() or not file_path.is_file():
        return None
    if file_path.stat().st_size > Config.OPENAI_MAX_INLINE_BYTES:
        return None

    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    if _is_text_file(original_name, mime_type):
        text = file_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        return {"type": "input_text", "text": f"Содержимое файла {original_name}:\n{text}"}

    encoded = base64.b64encode(file_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    if mime_type.startswith("image/"):
        return {"type": "input_image", "image_url": data_url, "detail": "high"}
    return {"type": "input_file", "filename": original_name, "file_data": data_url}


def generate_ai_answer_for_submission(submission: dict, ai_settings: dict[str, object] | None = None) -> str:
    ai_settings = ai_settings or database.get_ai_settings()
    if not ai_settings["enabled"]:
        raise RuntimeError("AI отключен в настройках")
    if not Config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY не задан")

    prompt_lines = [str(ai_settings.get("prompt") or DEFAULT_AI_PROMPT).strip()]
    prompt_lines.append(f"Номер задания: {submission['task_number']}")
    nickname = normalize_text(submission.get("user_nickname"))
    if nickname:
        prompt_lines.append(f"Ник пользователя: {nickname}")
    text_content = normalize_text(submission.get("text_content", ""))
    if text_content:
        prompt_lines.append("Текст задания:")
        prompt_lines.append(text_content)

    content = [{"type": "input_text", "text": "\n".join(prompt_lines)}]
    for file_info in submission.get("files", []):
        file_part = build_file_part(file_info["stored_name"], file_info["original_name"])
        if file_part:
            content.append(file_part)

    response_payload = {
        "model": ai_settings["model"],
        "input": [{"role": "user", "content": content}],
        "store": False,
        "max_output_tokens": Config.OPENAI_MAX_OUTPUT_TOKENS,
    }
    if Config.OPENAI_REASONING_EFFORT:
        response_payload["reasoning"] = {"effort": Config.OPENAI_REASONING_EFFORT}

    http = getattr(REQUEST_LOCAL, "http", None)
    if http is None:
        http = requests.Session()
        REQUEST_LOCAL.http = http

    response = None
    retry_statuses = {429, 500, 502, 503, 504}
    for attempt in range(Config.OPENAI_MAX_RETRIES + 1):
        response = http.post(
            f"{Config.OPENAI_API_URL}/responses",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=response_payload,
            timeout=(5, 60),
        )
        if response.status_code not in retry_statuses or attempt >= Config.OPENAI_MAX_RETRIES:
            break
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except ValueError:
            delay = Config.OPENAI_RETRY_BASE_SECONDS * (2 ** attempt)
        time.sleep(min(max(delay, 0.2), 10))
    response.raise_for_status()
    data = response.json()
    answer_text = str(data.get("output_text") or "").strip()
    if not answer_text:
        texts = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text"):
                    texts.append(part["text"])
        answer_text = "\n".join(texts).strip()
    if not answer_text:
        raise RuntimeError("OpenAI не вернул текст ответа")
    return answer_text


def run_auto_ai_generation(submission_id: int) -> None:
    db_session = None
    try:
        max_attempts = max(1, Config.AI_JOB_MAX_ATTEMPTS)
        retry_delays = Config.AI_JOB_RETRY_DELAYS_SECONDS or [15, 60, 180]
        for attempt in range(max_attempts):
            try:
                db_session = database.create_session()
                submission = database.fetch_submission(submission_id, db_session)
                if not submission:
                    return
                answer_text = generate_ai_answer_for_submission(submission, database.get_ai_settings(db_session))
                database.update_submission_ai_answer(
                    submission_id,
                    answer_text,
                    set_answered_at_if_empty=True,
                    session=db_session,
                )
                db_session.commit()
                return
            except Exception as error:
                if attempt >= max_attempts - 1:
                    logger.exception(
                        "AI generation failed for submission %s after %s attempt(s)",
                        submission_id,
                        attempt + 1,
                    )
                    return
                logger.warning(
                    "AI generation attempt %s/%s failed for submission %s: %s",
                    attempt + 1,
                    max_attempts,
                    submission_id,
                    error,
                    exc_info=True,
                )
                try:
                    if db_session is not None:
                        db_session.close()
                except Exception:
                    pass
                db_session = None
                time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
    except Exception:
        logger.exception("Unexpected AI generation worker failure for submission %s", submission_id)
    finally:
        with AI_PENDING_LOCK:
            AI_PENDING_IDS.discard(submission_id)
        try:
            if db_session is not None:
                db_session.close()
        except Exception:
            pass


def maybe_schedule_ai_for_user(user: dict, submission_ids: list[int]) -> int:
    nickname = normalize_text(user.get("nickname"))
    ai_settings = database.get_ai_settings()
    if not nickname or not ai_settings["enabled"] or not Config.OPENAI_API_KEY or not database.is_ai_allowed_for_nickname(nickname):
        return 0
    queued = 0
    for submission_id in submission_ids:
        with AI_PENDING_LOCK:
            if submission_id in AI_PENDING_IDS:
                continue
            AI_PENDING_IDS.add(submission_id)
        AI_EXECUTOR.submit(run_auto_ai_generation, submission_id)
        queued += 1
    return queued


@app.route("/", methods=["GET"])
def index():
    current_user, is_new_user = get_or_create_current_user()
    answered_tasks, teacher_answers = database.fetch_answer_state(current_user["id"])
    answer_sources = database.fetch_answer_sources(current_user["id"])
    response = make_response(
        render_template(
            "student_exam.html",
            task_numbers=TASK_NUMBERS,
            answered_tasks=answered_tasks,
            teacher_answers=teacher_answers,
            answer_sources=answer_sources,
            current_user=current_user,
        )
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/profile", methods=["POST"])
def save_profile():
    current_user, is_new_user = get_or_create_current_user()
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    database.update_user_nickname(current_user["id"], nickname)
    current_user["nickname"] = nickname
    ai_queued = 0
    ai_settings = database.get_ai_settings()
    if nickname and ai_settings["enabled"] and Config.OPENAI_API_KEY and database.is_ai_allowed_for_nickname(nickname):
        submission_ids = database.fetch_unanswered_submission_ids_for_user(current_user["id"])
        ai_queued = maybe_schedule_ai_for_user(current_user, submission_ids)
    response = jsonify({"ok": True, "user": current_user, "ai_queued": ai_queued})
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/profile/current-task", methods=["POST"])
def save_current_task():
    current_user, is_new_user = get_or_create_current_user()
    task_number = normalize_text((request.get_json(silent=True) or {}).get("task_number", ""))
    if task_number and task_number not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400
    database.update_user_current_task(current_user["id"], task_number)
    current_user["current_task"] = task_number
    response = jsonify({"ok": True, "user": current_user})
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/submit", methods=["POST"])
def submit():
    current_user, is_new_user = get_or_create_current_user()
    text_content = normalize_text(request.form.get("text_content", ""))
    selected_task = request.form.get("task_number") or None
    uploaded_files = [file for file in request.files.getlist("files") if file and file.filename]

    if not text_content and not uploaded_files:
        response = jsonify({"ok": False, "error": "Добавьте текст, файл или оба варианта сразу."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    if selected_task and selected_task not in TASK_NUMBERS:
        response = jsonify({"ok": False, "error": "Выбран некорректный номер задания."})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    item_count = max(len(uploaded_files), 1)
    try:
        assigned_tasks = submission_service.allocate_task_numbers(current_user["id"], selected_task, item_count)
    except ValueError as error:
        response = jsonify({"ok": False, "error": str(error)})
        if is_new_user:
            response = with_user_cookie(response, current_user["uid"])
        return response, 400

    created_ids: list[int] = []
    if uploaded_files:
        for index, file_storage in enumerate(uploaded_files):
            created_ids.append(
                submission_service.upsert_submission(current_user, assigned_tasks[index], text_content, [file_storage])
            )
    else:
        created_ids.append(submission_service.upsert_submission(current_user, assigned_tasks[0], text_content, []))
    database.commit()

    ai_queued = maybe_schedule_ai_for_user(current_user, created_ids)

    response = jsonify(
        {
            "ok": True,
            "message": "Ответ отправлен",
            "assigned_tasks": assigned_tasks,
            "ai_queued": ai_queued,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/answers", methods=["GET"])
def answers():
    current_user, is_new_user = get_or_create_current_user()
    answered_tasks, teacher_answers = database.fetch_answer_state(current_user["id"])
    answer_sources = database.fetch_answer_sources(current_user["id"])
    response = jsonify(
        {
            "ok": True,
            "answered_tasks": sorted(answered_tasks, key=lambda item: TASK_NUMBERS.index(item)),
            "teacher_answers": teacher_answers,
            "answer_sources": answer_sources,
            "user": current_user,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    return jsonify({"ok": True, "tasks": database.fetch_submissions()})


@app.route("/my-summary", methods=["GET"])
def my_summary():
    current_user, is_new_user = get_or_create_current_user()
    response = jsonify(
        {
            "ok": True,
            "uploads": database.fetch_user_summary_uploads(current_user["id"]),
            "answers": database.fetch_teacher_answers(current_user["id"]),
            "task_numbers": TASK_NUMBERS,
        }
    )
    if is_new_user:
        response = with_user_cookie(response, current_user["uid"])
    return response


@app.route("/admin", methods=["GET"])
def admin():
    gate = admin_required()
    if gate is not None:
        return gate
    return render_template(
        "admin_dashboard.html",
        submissions=database.fetch_submissions(),
        ai_allowed_nicknames=database.fetch_allowed_nicknames(),
        ai_enabled=bool(database.get_ai_settings()["enabled"] and Config.OPENAI_API_KEY),
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    next_url = request.values.get("next") or url_for("admin")
    if request.method == "POST":
        password = normalize_text(request.form.get("password", ""))
        if password == Config.ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(next_url)
        error = "Неверный пароль"
    return render_template("admin_login.html", error=error, next_url=next_url)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/settings", methods=["GET"])
def admin_settings():
    gate = admin_required()
    if gate is not None:
        return gate
    ai_settings = database.get_ai_settings()
    return render_template(
        "admin_settings.html",
        ai_allowed_nicknames=database.fetch_allowed_nicknames(),
        config_view={
            "AI_ENABLED": ai_settings["enabled"],
            "OPENAI_MODEL": ai_settings["model"],
            "AI_PROMPT": ai_settings["prompt"],
            "OPENAI_API_URL": Config.OPENAI_API_URL,
            "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
            "ADMIN_PASSWORD_SET": bool(Config.ADMIN_PASSWORD),
        },
    )


@app.route("/api/admin/settings/ai", methods=["POST"])
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
    database.update_app_settings({
        "ai_enabled": "1" if enabled else "0",
        "openai_model": model,
        "ai_prompt": prompt,
    })
    return jsonify({
        "ok": True,
        "settings": {
            "AI_ENABLED": enabled,
            "OPENAI_MODEL": model,
            "AI_PROMPT": prompt,
            "OPENAI_API_KEY_SET": bool(Config.OPENAI_API_KEY),
        },
    })


@app.route("/api/ai-allowed", methods=["POST"])
@app.route("/admin/ai-allowed", methods=["POST"])
def add_ai_allowed_nickname():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    nickname = normalize_text((request.get_json(silent=True) or {}).get("nickname", ""))
    if not nickname:
        return jsonify({"ok": False, "error": "Укажите ник."}), 400
    database.add_ai_allowed_nickname(nickname)

    submission_ids = database.fetch_unanswered_submission_ids_for_nickname(nickname)
    maybe_schedule_ai_for_user({"nickname": nickname}, submission_ids)
    return jsonify({"ok": True, "nicknames": database.fetch_allowed_nicknames(), "queued": len(submission_ids)})


@app.route("/api/ai-allowed/<path:nickname>", methods=["DELETE"])
@app.route("/admin/ai-allowed/<path:nickname>", methods=["DELETE"])
def remove_ai_allowed_nickname(nickname: str):
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    database.remove_ai_allowed_nickname(nickname)
    return jsonify({"ok": True, "nicknames": database.fetch_allowed_nicknames()})


@app.route("/api/tasks/<path:task_key>", methods=["PATCH"])
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
    updated_count = database.update_submission_admin_answer(submission_id, answer_text)
    if updated_count == 0:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    return jsonify({"ok": True, "task": database.fetch_submission(submission_id)})


@app.route("/admin/submission/<int:submission_id>/answer", methods=["POST"])
def save_admin_answer(submission_id: int):
    gate = admin_required()
    if gate is not None:
        return gate if not request.is_json else (jsonify({"ok": False, "error": "Нужен вход в админку"}), 401)
    payload = request.get_json(silent=True) or {}
    answer = normalize_text(payload.get("admin_answer", request.form.get("admin_answer", "")))
    updated_count = database.update_submission_admin_answer(submission_id, answer)

    if updated_count == 0:
        if request.is_json:
            return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
        flash("Загрузка не найдена.", "error")
        return redirect(url_for("admin"))

    if request.is_json:
        return jsonify({"ok": True, "submission": database.fetch_submission(submission_id)})
    flash("Ответ администратора сохранен.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/submission/<int:submission_id>/generate-ai", methods=["POST"])
def generate_ai():
    gate = admin_required()
    if gate is not None:
        return jsonify({"ok": False, "error": "Нужен вход в админку"}), 401
    submission_id = int(request.view_args["submission_id"])
    submission = database.fetch_submission(submission_id)
    if not submission:
        return jsonify({"ok": False, "error": "Загрузка не найдена."}), 404
    try:
        ai_answer = generate_ai_answer_for_submission(submission)
    except Exception as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    database.update_submission_ai_answer(submission_id, ai_answer)
    database.commit()
    return jsonify({"ok": True, "submission": database.fetch_submission(submission_id)})


@app.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file_alias(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/healthz", methods=["GET"])
def healthz():
    database.health_check()
    return jsonify({"ok": True})


@app.context_processor
def inject_globals():
    return {"task_numbers_json": json.dumps(TASK_NUMBERS, ensure_ascii=False)}


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
database.init_db()


if __name__ == "__main__":
    app.run(debug=True)
