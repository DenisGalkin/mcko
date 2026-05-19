from __future__ import annotations

from flask import Blueprint, abort, jsonify, send_file, send_from_directory

from ..db import session as db_session
from ..settings import PROJECT_ROOT, UPLOAD_DIR


file_bp = Blueprint("file", __name__)


@file_bp.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@file_bp.route("/files/<path:filename>", methods=["GET"])
def uploaded_file_alias(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@file_bp.route("/download/mcko.zip", methods=["GET"])
def download_mcko_zip():
    archive_path = PROJECT_ROOT / "mcko.zip"
    if not archive_path.is_file():
        abort(404)
    return send_file(archive_path, as_attachment=True, download_name="mcko.zip")


@file_bp.route("/healthz", methods=["GET"])
def healthz():
    db_session.health_check()
    return jsonify({"ok": True})
