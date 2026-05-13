from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "mcko-local-secret")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    AI_ENABLED = os.getenv("AI_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1").rstrip("/")
    OPENAI_MAX_INLINE_BYTES = int(os.getenv("OPENAI_MAX_INLINE_BYTES", str(12 * 1024 * 1024)))
    OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "2048"))
    OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "").strip()
    OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    OPENAI_RETRY_BASE_SECONDS = float(os.getenv("OPENAI_RETRY_BASE_SECONDS", "1.5"))
    AI_MAX_WORKERS = int(os.getenv("AI_MAX_WORKERS", "8"))
    AI_JOB_MAX_ATTEMPTS = int(os.getenv("AI_JOB_MAX_ATTEMPTS", "4"))
    AI_JOB_RETRY_DELAYS_SECONDS = [
        float(value.strip())
        for value in os.getenv("AI_JOB_RETRY_DELAYS_SECONDS", "15,60,180").split(",")
        if value.strip()
    ]
    SQLITE_TIMEOUT_SECONDS = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "60"))
    SQLITE_CACHE_KB = int(os.getenv("SQLITE_CACHE_KB", "32768"))
