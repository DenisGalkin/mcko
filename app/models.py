from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class AiSettings:
    enabled: bool
    model: str
    prompt: str


@dataclass(frozen=True)
class UploadSettings:
    require_login: bool


class User(TypedDict, total=False):
    id: int
    uid: str
    nickname: str
    current_task: str
    created_at: str
    updated_at: str


class SubmissionFile(TypedDict):
    original_name: str
    stored_name: str


class Submission(TypedDict, total=False):
    id: int
    user_id: int
    user_uid: str
    user_nickname: str
    user_current_task: str
    task_number: str
    text_content: str
    admin_answer: str
    ai_answer: str
    task_priority: int
    visible_status: str
    tags: list[str]
    ai_processing_at: str | None
    admin_processing_by: str
    admin_processing_at: str | None
    created_at: str
    updated_at: str
    answered_at: str | None
    ai_generated_at: str | None
    files: list[SubmissionFile]
