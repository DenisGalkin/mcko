from flask import Flask, request, send_from_directory, render_template, jsonify
from pathlib import Path
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_FILE = BASE_DIR / "data.json"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

TEST_DURATION_MINUTES = 44
START_TIME = datetime.now()
FINISH_TIME = START_TIME + timedelta(minutes=TEST_DURATION_MINUTES)


def load_data():
    if not DATA_FILE.exists():
        return {"tasks": {}}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": {}}
    if not isinstance(data, dict):
        return {"tasks": {}}
    if "tasks" not in data or not isinstance(data["tasks"], dict):
        data["tasks"] = {}
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
    app.run(host="0.0.0.0", port=1000, debug=True)