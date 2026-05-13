from __future__ import annotations

import uuid

from flask import redirect, request, session, url_for


def get_admin_worker_id() -> str:
    admin_worker_id = session.get("admin_worker_id")
    if not admin_worker_id:
        admin_worker_id = uuid.uuid4().hex
        session["admin_worker_id"] = admin_worker_id
    return str(admin_worker_id)


def admin_is_authenticated() -> bool:
    return session.get("admin_authenticated") is True


def admin_required():
    if admin_is_authenticated():
        get_admin_worker_id()
        return None
    return redirect(url_for("admin.admin_login", next=request.path))
