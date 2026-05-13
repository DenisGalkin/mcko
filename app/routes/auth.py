from __future__ import annotations

from flask import redirect, request, session, url_for


def admin_is_authenticated() -> bool:
    return session.get("admin_authenticated") is True


def admin_required():
    if admin_is_authenticated():
        return None
    return redirect(url_for("admin.admin_login", next=request.path))
