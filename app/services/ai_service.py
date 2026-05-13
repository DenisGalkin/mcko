from __future__ import annotations

import base64
import logging
import mimetypes
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from ..config import Config
from ..db import session as db_session
from ..models import AiSettings
from ..repositories import ai_allowed, settings, submissions
from ..settings import DEFAULT_AI_PROMPT, UPLOAD_DIR
from .text import normalize_text


logger = logging.getLogger(__name__)
REQUEST_LOCAL = threading.local()


class AiService:
    def is_text_file(self, filename: str, mime_type: str) -> bool:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return mime_type.startswith("text/") or extension in {"txt", "md", "html", "xml"}

    def build_file_part(self, stored_name: str, original_name: str) -> dict | None:
        file_path = UPLOAD_DIR / stored_name
        if not file_path.exists() or not file_path.is_file():
            return None
        if file_path.stat().st_size > Config.OPENAI_MAX_INLINE_BYTES:
            return None

        mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        file_bytes = file_path.read_bytes()

        if self.is_text_file(original_name, mime_type):
            text = file_bytes.decode("utf-8", errors="replace").strip()
            if not text:
                return None
            return {"type": "input_text", "text": f"Содержимое файла {original_name}:\n{text}"}

        encoded = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        if mime_type.startswith("image/"):
            return {"type": "input_image", "image_url": data_url, "detail": "high"}
        return {"type": "input_file", "filename": original_name, "file_data": data_url}

    def generate_answer_for_submission(
        self,
        submission: dict,
        ai_settings: AiSettings | None = None,
    ) -> str:
        ai_settings = ai_settings or settings.get_ai_settings()
        if not ai_settings.enabled:
            raise RuntimeError("AI отключен в настройках")
        if not Config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY не задан")

        prompt_lines = [str(ai_settings.prompt or DEFAULT_AI_PROMPT).strip()]
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
            file_part = self.build_file_part(file_info["stored_name"], file_info["original_name"])
            if file_part:
                content.append(file_part)

        response_payload = {
            "model": ai_settings.model,
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
                delay = Config.OPENAI_RETRY_BASE_SECONDS * (2**attempt)
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


class AiJobRunner:
    def __init__(self, ai_service: AiService):
        self.ai_service = ai_service
        self.executor = ThreadPoolExecutor(max_workers=max(1, Config.AI_MAX_WORKERS), thread_name_prefix="ai-answer")
        self.pending_ids: set[int] = set()
        self.pending_lock = threading.Lock()

    def maybe_schedule_for_user(self, user: dict, submission_ids: list[int]) -> int:
        nickname = normalize_text(user.get("nickname"))
        ai_settings = settings.get_ai_settings()
        if (
            not nickname
            or not ai_settings.enabled
            or not Config.OPENAI_API_KEY
            or not ai_allowed.is_ai_allowed_for_nickname(nickname)
        ):
            return 0
        queued = 0
        for submission_id in submission_ids:
            with self.pending_lock:
                if submission_id in self.pending_ids:
                    continue
                self.pending_ids.add(submission_id)
            self.executor.submit(self.run_auto_generation, submission_id)
            queued += 1
        return queued

    def run_auto_generation(self, submission_id: int) -> None:
        local_session = None
        try:
            max_attempts = max(1, Config.AI_JOB_MAX_ATTEMPTS)
            retry_delays = Config.AI_JOB_RETRY_DELAYS_SECONDS or [15, 60, 180]
            for attempt in range(max_attempts):
                try:
                    local_session = db_session.create_session()
                    submission = submissions.fetch_submission(submission_id, local_session)
                    if not submission:
                        return
                    answer_text = self.ai_service.generate_answer_for_submission(
                        submission,
                        settings.get_ai_settings(local_session),
                    )
                    submissions.update_submission_ai_answer(
                        submission_id,
                        answer_text,
                        set_answered_at_if_empty=True,
                        session=local_session,
                    )
                    local_session.commit()
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
                        if local_session is not None:
                            local_session.close()
                    except Exception:
                        pass
                    local_session = None
                    time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
        except Exception:
            logger.exception("Unexpected AI generation worker failure for submission %s", submission_id)
        finally:
            with self.pending_lock:
                self.pending_ids.discard(submission_id)
            try:
                if local_session is not None:
                    local_session.close()
            except Exception:
                pass


ai_service = AiService()
ai_job_runner = AiJobRunner(ai_service)
