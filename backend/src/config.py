import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    gemini_api_key: str | None
    gemini_contract_review_model: str
    gemini_generate_content_base_url: str
    gemini_timeout_seconds: float
    gemini_max_paragraphs_per_request: int
    gemini_max_characters_per_request: int
    gemini_max_issues_per_request: int
    gemini_max_output_tokens: int
    gemini_max_retries: int
    gemini_retry_base_seconds: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_contract_review_model=os.getenv(
            "GEMINI_CONTRACT_REVIEW_MODEL",
            "gemini-2.0-flash",
        ),
        gemini_generate_content_base_url=os.getenv(
            "GEMINI_GENERATE_CONTENT_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/models",
        ),
        gemini_timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "120")),
        gemini_max_paragraphs_per_request=int(
            os.getenv("GEMINI_MAX_PARAGRAPHS_PER_REQUEST", "60")
        ),
        gemini_max_characters_per_request=int(
            os.getenv("GEMINI_MAX_CHARACTERS_PER_REQUEST", "40000")
        ),
        gemini_max_issues_per_request=int(
            os.getenv("GEMINI_MAX_ISSUES_PER_REQUEST", "100")
        ),
        gemini_max_output_tokens=int(
            os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "6000")
        ),
        gemini_max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "2")),
        gemini_retry_base_seconds=float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "2")),
    )
