from __future__ import annotations

from .db.schema import current_timestamp, ensure_column, init_db
from .db.session import close_session, commit, create_session, get_session, health_check, rollback
from .repositories.ai_allowed import (
    add_ai_allowed_nickname,
    fetch_allowed_nicknames,
    fetch_unanswered_submission_ids_for_nickname,
    is_ai_allowed_for_nickname,
    remove_ai_allowed_nickname,
)
from .repositories.common import execute_text, row_to_dict
from .repositories import settings as settings_repository
from .repositories.settings import fetch_app_settings, update_app_settings
from .repositories.submissions import (
    add_submission_file,
    build_submission_payload,
    create_submission,
    delete_submission_file_rows,
    fetch_answer_sources,
    fetch_answer_overview,
    fetch_answer_state,
    fetch_submission,
    fetch_submission_file_stored_names,
    fetch_submissions,
    fetch_teacher_answers,
    fetch_unanswered_submission_ids_for_user,
    fetch_used_tasks,
    fetch_user_summary_uploads,
    find_latest_submission_for_task,
    get_submission_files,
    get_user_answer_expression,
    reset_submission_content,
    update_submission_admin_answer,
    update_submission_ai_answer,
)
from .repositories.users import (
    generate_short_user_id,
    get_or_create_user,
    update_user_current_task,
    update_user_nickname,
)


def get_ai_settings(session=None) -> dict[str, object]:
    ai_settings = settings_repository.get_ai_settings(session)
    return {
        "enabled": ai_settings.enabled,
        "model": ai_settings.model,
        "prompt": ai_settings.prompt,
    }


__all__ = [
    "add_ai_allowed_nickname",
    "add_submission_file",
    "build_submission_payload",
    "close_session",
    "commit",
    "create_session",
    "create_submission",
    "current_timestamp",
    "delete_submission_file_rows",
    "ensure_column",
    "execute_text",
    "fetch_allowed_nicknames",
    "fetch_answer_sources",
    "fetch_answer_overview",
    "fetch_answer_state",
    "fetch_app_settings",
    "fetch_submission",
    "fetch_submission_file_stored_names",
    "fetch_submissions",
    "fetch_teacher_answers",
    "fetch_unanswered_submission_ids_for_nickname",
    "fetch_unanswered_submission_ids_for_user",
    "fetch_used_tasks",
    "fetch_user_summary_uploads",
    "find_latest_submission_for_task",
    "generate_short_user_id",
    "get_ai_settings",
    "get_or_create_user",
    "get_session",
    "get_submission_files",
    "get_user_answer_expression",
    "health_check",
    "init_db",
    "is_ai_allowed_for_nickname",
    "remove_ai_allowed_nickname",
    "reset_submission_content",
    "rollback",
    "row_to_dict",
    "update_app_settings",
    "update_submission_admin_answer",
    "update_submission_ai_answer",
    "update_user_current_task",
    "update_user_nickname",
]
