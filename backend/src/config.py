import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    openai_api_key: str | None
    openai_contract_review_model: str
    openai_responses_base_url: str
    openai_timeout_seconds: float
    openai_max_paragraphs_per_request: int
    openai_max_characters_per_request: int
    openai_max_issues_per_request: int
    openai_max_output_tokens: int
    openai_max_retries: int
    openai_retry_base_seconds: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_contract_review_model=os.getenv(
            "OPENAI_CONTRACT_REVIEW_MODEL",
            "gpt-4o-mini",
        ),
        openai_responses_base_url=os.getenv(
            "OPENAI_RESPONSES_BASE_URL",
            "https://api.openai.com/v1/responses",
        ),
        openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")),
        openai_max_paragraphs_per_request=int(
            os.getenv("OPENAI_MAX_PARAGRAPHS_PER_REQUEST", "60")
        ),
        openai_max_characters_per_request=int(
            os.getenv("OPENAI_MAX_CHARACTERS_PER_REQUEST", "40000")
        ),
        openai_max_issues_per_request=int(
            os.getenv("OPENAI_MAX_ISSUES_PER_REQUEST", "100")
        ),
        openai_max_output_tokens=int(
            os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "6000")
        ),
        openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
        openai_retry_base_seconds=float(os.getenv("OPENAI_RETRY_BASE_SECONDS", "2")),
    )
