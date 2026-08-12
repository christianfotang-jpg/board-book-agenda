"""Runtime configuration.

Reads settings from environment variables (optionally loaded from a .env
file via python-dotenv). Nothing here talks to the network - it just
centralizes the knobs the other modules need.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Anthropic model used for structured agenda extraction. The API key
    # itself is resolved by the SDK (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN
    # / an `ant auth login` profile) - we never read it directly here.
    anthropic_model: str = os.environ.get("BOARDBOOK_MODEL", "claude-opus-5")

    # Institution name shown when no logo/committee override is supplied.
    default_institution: str = os.environ.get(
        "BOARDBOOK_DEFAULT_INSTITUTION", "University of Alberta"
    )

    # Directory the API writes uploaded attachments/logos into before a
    # /build call references them by id.
    upload_dir: str = os.environ.get("BOARDBOOK_UPLOAD_DIR", "./uploads")

    # Directory finished board books are written to by default.
    output_dir: str = os.environ.get("BOARDBOOK_OUTPUT_DIR", "./output")


settings = Settings()
