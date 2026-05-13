from __future__ import annotations

from . import create_app
from .services.ai_service import ai_job_runner, ai_service
from .services.text import normalize_text


app = create_app()

build_file_part = ai_service.build_file_part
generate_ai_answer_for_submission = ai_service.generate_answer_for_submission
maybe_schedule_ai_for_user = ai_job_runner.maybe_schedule_for_user
run_auto_ai_generation = ai_job_runner.run_auto_generation
