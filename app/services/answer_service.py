from __future__ import annotations

from ..repositories import submissions


class AnswerService:
    def fetch_answer_state(self, user_id: int):
        return submissions.fetch_answer_state(user_id)

    def fetch_answer_sources(self, user_id: int) -> dict[str, str]:
        return submissions.fetch_answer_sources(user_id)

    def fetch_teacher_answers(self, user_id: int) -> dict[str, str]:
        return submissions.fetch_teacher_answers(user_id)

    def update_admin_answer(self, submission_id: int, answer_text: str) -> int:
        return submissions.update_submission_admin_answer(submission_id, answer_text)

    def update_ai_answer(
        self,
        submission_id: int,
        answer_text: str,
        *,
        set_answered_at_if_empty: bool = False,
        session=None,
    ) -> int:
        return submissions.update_submission_ai_answer(
            submission_id,
            answer_text,
            set_answered_at_if_empty=set_answered_at_if_empty,
            session=session,
        )


answer_service = AnswerService()
