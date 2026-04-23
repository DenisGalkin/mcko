from flask import Flask, request, send_from_directory, render_template, jsonify
from pathlib import Path
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import json
import os
import mimetypes
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_FILE = BASE_DIR / "data.json"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
ENV_FILE = BASE_DIR / ".env"

UPLOAD_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)


def load_env_file(path):
    if load_dotenv is not None:
        load_dotenv(path)
        return

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ENV_FILE)


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

TEST_DURATION_MINUTES = 44
START_TIME = datetime.now()
FINISH_TIME = START_TIME + timedelta(minutes=TEST_DURATION_MINUTES)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""
TELEGRAM_POLL_TIMEOUT = 30
TELEGRAM_SKIP_SSL_VERIFY = env_flag("TELEGRAM_SKIP_SSL_VERIFY", default=False)
TELEGRAM_SSL_CONTEXT = ssl._create_unverified_context() if TELEGRAM_SKIP_SSL_VERIFY else None
APP_DEBUG = env_flag("APP_DEBUG", default=True)
telegram_bot_started = False
telegram_bot_status = {
    "enabled": bool(TELEGRAM_BOT_TOKEN),
    "running": False,
    "last_error": "",
    "bot_username": "",
    "last_update_id": None,
    "skip_ssl_verify": TELEGRAM_SKIP_SSL_VERIFY
}


def load_data():
    if not DATA_FILE.exists():
        return {"tasks": {}, "telegram_subscribers": {}, "telegram_message_map": {}}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": {}, "telegram_subscribers": {}, "telegram_message_map": {}}
    if not isinstance(data, dict):
        return {"tasks": {}, "telegram_subscribers": {}, "telegram_message_map": {}}
    if "tasks" not in data or not isinstance(data["tasks"], dict):
        data["tasks"] = {}
    if "telegram_subscribers" not in data or not isinstance(data["telegram_subscribers"], dict):
        data["telegram_subscribers"] = {}
    if "telegram_message_map" not in data or not isinstance(data["telegram_message_map"], dict):
        data["telegram_message_map"] = {}
    return data


def save_data(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def normalize_task_number(raw_value):
    value = str(raw_value or "").strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


def get_next_task_number(data):
    nums = []
    for key in data["tasks"].keys():
        if str(key).isdigit():
            nums.append(int(key))
    return max(nums, default=0) + 1


def get_task_file_path(task_number):
    prefix = f"{task_number}."
    for path in UPLOAD_DIR.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            return path
    return None


def cleanup_data():
    data = load_data()
    changed = False
    tasks_to_delete = []

    for task_number, item in data["tasks"].items():
        filename = item.get("filename", "")
        if not filename:
            tasks_to_delete.append(task_number)
            changed = True
            continue

        path = UPLOAD_DIR / filename
        if not path.is_file():
            tasks_to_delete.append(task_number)
            changed = True

    for task_number in tasks_to_delete:
        data["tasks"].pop(task_number, None)

    if changed:
        save_data(data)

    return data


def get_sorted_task_numbers(data):
    nums = []
    for key in data["tasks"].keys():
        if str(key).isdigit():
            nums.append(int(key))
    nums.sort()
    return nums


def build_tasks_for_template(data):
    tasks = []
    for task_number in get_sorted_task_numbers(data):
        item = data["tasks"][str(task_number)]
        tasks.append({
            "task_number": task_number,
            "filename": item.get("filename", ""),
            "created": item.get("created", ""),
            "answer_text": item.get("answer_text", "")
        })
    return tasks


def telegram_api_call(method, payload=None, timeout=10):
    if not TELEGRAM_API_BASE:
        telegram_bot_status["last_error"] = "TELEGRAM_BOT_TOKEN is empty"
        return None

    payload = payload or {}
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"{TELEGRAM_API_BASE}/{method}"

    try:
        with urllib.request.urlopen(
            url,
            data=encoded,
            timeout=timeout,
            context=TELEGRAM_SSL_CONTEXT
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                telegram_bot_status["last_error"] = str(result.get("description", "Telegram API error"))
            else:
                telegram_bot_status["last_error"] = ""
            return result
    except Exception as exc:
        telegram_bot_status["last_error"] = str(exc)
        return None


def telegram_api_call_multipart(method, fields, file_field_name, file_path, timeout=30):
    if not TELEGRAM_API_BASE:
        telegram_bot_status["last_error"] = "TELEGRAM_BOT_TOKEN is empty"
        return None

    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    data_parts = []

    for key, value in fields.items():
        data_parts.extend([
            f"--{boundary}".encode("utf-8"),
            f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"),
            b"",
            str(value).encode("utf-8"),
        ])

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    data_parts.extend([
        f"--{boundary}".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{file_field_name}"; '
            f'filename="{file_path.name}"'
        ).encode("utf-8"),
        f"Content-Type: {mime_type}".encode("utf-8"),
        b"",
        file_bytes,
        f"--{boundary}--".encode("utf-8"),
        b"",
    ])

    body = b"\r\n".join(data_parts)
    request = urllib.request.Request(
        f"{TELEGRAM_API_BASE}/{method}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=TELEGRAM_SSL_CONTEXT
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                telegram_bot_status["last_error"] = str(result.get("description", "Telegram API error"))
            else:
                telegram_bot_status["last_error"] = ""
            return result
    except Exception as exc:
        telegram_bot_status["last_error"] = str(exc)
        return None


def send_telegram_message(chat_id, text):
    return telegram_api_call(
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text
        }
    )


def add_telegram_subscriber(chat_id, username="", full_name=""):
    data = load_data()
    data["telegram_subscribers"][str(chat_id)] = {
        "username": username,
        "full_name": full_name,
        "subscribed_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }
    save_data(data)


def remove_telegram_subscriber(chat_id):
    data = load_data()
    removed = data["telegram_subscribers"].pop(str(chat_id), None)
    if removed is not None:
        save_data(data)
    return removed is not None


def get_telegram_subscribers():
    data = load_data()
    return list(data.get("telegram_subscribers", {}).keys())


def save_task_answer(task_number, text):
    data = cleanup_data()
    task_key = str(task_number)
    if task_key not in data["tasks"]:
        return False

    data["tasks"][task_key]["answer_text"] = text
    save_data(data)
    return True


def remember_telegram_message(chat_id, message_id, task_number):
    data = load_data()
    key = f"{chat_id}:{message_id}"
    data["telegram_message_map"][key] = {
        "task_number": task_number,
        "saved_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }
    save_data(data)


def get_task_number_from_telegram_message(chat_id, message_id):
    data = load_data()
    item = data.get("telegram_message_map", {}).get(f"{chat_id}:{message_id}")
    if not isinstance(item, dict):
        return None
    return normalize_task_number(item.get("task_number"))


def send_telegram_document(chat_id, file_path, task_number):
    caption = (
        f"Новое задание #{task_number}\n"
        "Ответьте реплаем на это сообщение или отправьте:\n"
        f"/answer {task_number} ваш ответ"
    )
    result = telegram_api_call_multipart(
        "sendDocument",
        {
            "chat_id": str(chat_id),
            "caption": caption
        },
        "document",
        file_path
    )
    if result and result.get("ok"):
        message_id = ((result.get("result") or {}).get("message_id"))
        if message_id is not None:
            remember_telegram_message(chat_id, message_id, task_number)
    return result


def notify_new_file(task_number, filename):
    subscribers = get_telegram_subscribers()
    if not subscribers:
        return

    file_path = UPLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return

    for chat_id in subscribers:
        result = send_telegram_document(chat_id, file_path, task_number)
        if not result or not result.get("ok"):
            print(f"[telegram] failed to send document to {chat_id}: {telegram_bot_status['last_error']}")


def save_answer_from_reply(message):
    chat_id = (message.get("chat") or {}).get("id")
    reply_to_message = message.get("reply_to_message") or {}
    reply_message_id = reply_to_message.get("message_id")
    text = str(message.get("text", "") or "").strip()

    if not chat_id or not reply_message_id or not text or text.startswith("/"):
        return False

    task_number = get_task_number_from_telegram_message(chat_id, reply_message_id)
    if task_number is None:
        return False

    if not save_task_answer(task_number, text):
        send_telegram_message(chat_id, f"Не удалось сохранить ответ для задания #{task_number}.")
        return True

    send_telegram_message(chat_id, f"Ответ для задания #{task_number} сохранен.")
    return True


def save_answer_from_command(chat_id, text):
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        send_telegram_message(chat_id, "Формат: /answer 3 ваш ответ")
        return True

    task_number = normalize_task_number(parts[1])
    answer_text = parts[2].strip()
    if task_number is None or not answer_text:
        send_telegram_message(chat_id, "Формат: /answer 3 ваш ответ")
        return True

    if not save_task_answer(task_number, answer_text):
        send_telegram_message(chat_id, f"Задание #{parts[1]} не найдено.")
        return True

    send_telegram_message(chat_id, f"Ответ для задания #{task_number} сохранен.")
    return True


def handle_telegram_update(update):
    message = update.get("message") or {}
    text = str(message.get("text", "")).strip()
    chat = message.get("chat") or {}

    chat_id = chat.get("id")
    if not chat_id:
        return

    if save_answer_from_reply(message):
        return

    if not text.startswith("/"):
        return

    username = str((message.get("from") or {}).get("username", "") or "")
    first_name = str((message.get("from") or {}).get("first_name", "") or "").strip()
    last_name = str((message.get("from") or {}).get("last_name", "") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part)
    command = text.split()[0].lower()

    if command == "/start":
        add_telegram_subscriber(chat_id, username=username, full_name=full_name)
        send_telegram_message(
            chat_id,
            "Подписка включена. Я буду присылать уведомления о новых файлах."
        )
    elif command == "/stop":
        remove_telegram_subscriber(chat_id)
        send_telegram_message(
            chat_id,
            "Подписка отключена. Уведомления о новых файлах больше не будут приходить."
        )
    elif command == "/status":
        is_subscribed = str(chat_id) in get_telegram_subscribers()
        send_telegram_message(
            chat_id,
            "Подписка активна." if is_subscribed else "Подписка не активна. Отправьте /start."
        )
    elif command == "/answer":
        save_answer_from_command(chat_id, text)


def telegram_polling_loop():
    offset = 0
    telegram_bot_status["running"] = True

    while True:
        response = telegram_api_call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": TELEGRAM_POLL_TIMEOUT
            },
            timeout=TELEGRAM_POLL_TIMEOUT + 5
        )

        if not response or not response.get("ok"):
            if telegram_bot_status["last_error"]:
                print(f"[telegram] polling error: {telegram_bot_status['last_error']}")
            if "HTTP Error 409" in telegram_bot_status["last_error"]:
                telegram_api_call("deleteWebhook", {"drop_pending_updates": False})
                time.sleep(2)
            time.sleep(5)
            continue

        for update in response.get("result", []):
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
                telegram_bot_status["last_update_id"] = update_id
            handle_telegram_update(update)


def start_telegram_bot():
    global telegram_bot_started

    if telegram_bot_started or not TELEGRAM_BOT_TOKEN:
        if not TELEGRAM_BOT_TOKEN:
            print("[telegram] bot is disabled: TELEGRAM_BOT_TOKEN is empty")
        return

    me = telegram_api_call("getMe")
    if not me or not me.get("ok"):
        print(f"[telegram] bot failed to start: {telegram_bot_status['last_error']}")
        return

    telegram_bot_status["bot_username"] = ((me.get("result") or {}).get("username") or "")
    telegram_api_call("deleteWebhook", {"drop_pending_updates": False})
    if telegram_bot_status["last_error"]:
        print(f"[telegram] webhook cleanup warning: {telegram_bot_status['last_error']}")

    telegram_bot_started = True
    print(f"[telegram] bot started: @{telegram_bot_status['bot_username']}")
    thread = threading.Thread(target=telegram_polling_loop, daemon=True)
    thread.start()


@app.route("/telegram-status")
def telegram_status():
    return jsonify({
        "ok": True,
        "telegram": {
            **telegram_bot_status,
            "subscribers": len(get_telegram_subscribers())
        }
    })


@app.route("/")
def index():
    data = cleanup_data()
    tasks = build_tasks_for_template(data)
    answers_map = {
        str(task["task_number"]): task.get("answer_text", "")
        for task in tasks
    }
    return render_template(
        "index.html",
        tasks=sorted(tasks, key=lambda x: x["task_number"]),
        answers_map=answers_map,
        finish_ts=int(FINISH_TIME.timestamp())
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Файл не выбран"}), 400

    data = cleanup_data()

    requested_task = normalize_task_number(request.form.get("task_number"))
    task_number = requested_task if requested_task is not None else get_next_task_number(data)

    original_name = secure_filename(file.filename) or "file"
    ext = Path(original_name).suffix.lower()
    if not ext:
        ext = ".bin"

    final_filename = f"{task_number}{ext}"
    final_path = UPLOAD_DIR / final_filename

    old_path = get_task_file_path(task_number)
    if old_path and old_path.resolve() != final_path.resolve():
        old_path.unlink(missing_ok=True)

    if final_path.exists():
        final_path.unlink()

    file.save(final_path)

    created = datetime.fromtimestamp(final_path.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")

    task_key = str(task_number)
    old_answer = data["tasks"].get(task_key, {}).get("answer_text", "")

    data["tasks"][task_key] = {
        "task_number": task_number,
        "filename": final_filename,
        "created": created,
        "answer_text": old_answer
    }
    save_data(data)
    notify_new_file(task_number, final_filename)

    return jsonify({
        "ok": True,
        "task": {
            "task_number": task_number,
            "filename": final_filename,
            "created": created,
            "answer_text": old_answer
        }
    })


@app.route("/save-task-text", methods=["POST"])
def save_task_text():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Неверные данные"}), 400

    task_number = normalize_task_number(payload.get("task_number"))
    if task_number is None:
        return jsonify({"ok": False, "error": "Неверный номер задания"}), 400

    text = str(payload.get("text", ""))

    data = cleanup_data()
    task_key = str(task_number)
    if task_key not in data["tasks"]:
        return jsonify({"ok": False, "error": "Такого задания нет"}), 404

    data["tasks"][task_key]["answer_text"] = text
    save_data(data)

    return jsonify({
        "ok": True,
        "task_number": task_number,
        "text": text
    })


@app.route("/task-text/<int:task_number>")
def task_text(task_number):
    data = cleanup_data()
    item = data["tasks"].get(str(task_number))
    return jsonify({
        "ok": True,
        "text": item.get("answer_text", "") if item else ""
    })


@app.route("/delete/<int:task_number>", methods=["POST"])
def delete_task(task_number):
    data = cleanup_data()
    task_key = str(task_number)
    item = data["tasks"].get(task_key)

    if not item:
        return jsonify({"ok": False, "error": "Файл не найден"}), 404

    filename = item.get("filename", "")
    path = UPLOAD_DIR / filename
    if path.exists() and path.is_file():
        path.unlink()

    data["tasks"].pop(task_key, None)
    save_data(data)

    return jsonify({"ok": True, "task_number": task_number})


@app.route("/files/<path:filename>")
def download_file(filename):
    path = UPLOAD_DIR / filename
    if not path.exists() or not path.is_file():
        return jsonify({"ok": False, "error": "Файл не найден"}), 404

    return send_from_directory(
        UPLOAD_DIR,
        filename,
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":
    if not APP_DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_telegram_bot()
    app.run(host="0.0.0.0", port=1000, debug=APP_DEBUG)
