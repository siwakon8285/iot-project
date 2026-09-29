"""Environment-backed application configuration."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
# The older backend/.env remains supported; the documented root .env can
# provide new values without overriding an existing backend configuration.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Copy .env.example to .env and set it."
        )

    return database_url


def get_groq_api_key() -> Optional[str]:
    """Return the optional AI credential without affecting telemetry startup."""

    return os.getenv("GROQ_API_KEY", "").strip() or None


def get_groq_model() -> str:
    """Allow the Groq model to change without a source edit."""

    return os.getenv("GROQ_MODEL", "").strip() or "openai/gpt-oss-20b"
