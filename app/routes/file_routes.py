from __future__ import annotations

from flask import Blueprint, jsonify, send_from_directory

from ..db import session as db_session
from ..settings import UPLOAD_DIR


file_bp = Blueprint("file", __name__)


@file_bp.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@file_bp.route("/files/<path:filename>", methods=["GET"])
def uploaded_file_alias(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@file_bp.route("/healthz", methods=["GET"])
def healthz():
    db_session.health_check()
    return jsonify({"ok": True})
