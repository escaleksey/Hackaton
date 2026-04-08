import json
import logging
import re
import time
from datetime import datetime

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.application.services.contract_issue_analyzer import (
    ContractAnalysisDocument,
    ContractAnalysisResult,
    ContractAnalysisWarning,
    ContractIssueAnalyzer,
)
from src.config import get_settings
from src.domain.entities.issue import ContractIssue

LOGGER = logging.getLogger(__name__)

RUSSIAN_MONTHS = {
    "\u044f\u043d\u0432\u0430\u0440\u044f": 1,
    "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2,
    "\u043c\u0430\u0440\u0442\u0430": 3,
    "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
    "\u043c\u0430\u044f": 5,
    "\u0438\u044e\u043d\u044f": 6,
    "\u0438\u044e\u043b\u044f": 7,
    "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
    "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9,
    "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10,
    "\u043d\u043e\u044f\u0431\u0440\u044f": 11,
    "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
}

ISSUE_TYPES = {
    "INVALID_DATE",
    "DATE_CONFLICT",
    "TERM_CONFLICT",
    "TERM_MISUSE",
    "DEADLINE_CONFLICT",
    "AMBIGUOUS_TIME",
    "WRONG_ACTOR",
    "ROLE_CONFLICT",
    "ENTITY_MISMATCH",
    "INCONSISTENCY",
    "MISSING_CONDITION",
    "AMBIGUOUS_PHRASE",
    "UNILATERAL_RIGHT",
}

SYSTEM_PROMPT = """
\u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0442\u0435\u043a\u0441\u0442 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430.
\u041d\u0430\u0439\u0434\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e\u0442\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0435 \u043e\u0448\u0438\u0431\u043a\u0438 \u0432 \u0441\u0440\u043e\u043a\u0430\u0445, \u0434\u0430\u0442\u0430\u0445, \u0440\u043e\u043b\u044f\u0445 \u0441\u0442\u043e\u0440\u043e\u043d
\u0438 \u043b\u043e\u0433\u0438\u043a\u0435 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432.

\u0421\u0447\u0438\u0442\u0430\u0439 \u043e\u0448\u0438\u0431\u043a\u0430\u043c\u0438:
- \u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0438\u0435 \u0434\u0430\u0442\u044b;
- \u0434\u0430\u0442\u0443 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u043d\u0430\u0447\u0430\u043b\u0430;
- \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0435 \u043c\u0435\u0436\u0434\u0443 \u0441\u0440\u043e\u043a\u043e\u043c \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u0438 \u0441\u0440\u043e\u043a\u0430\u043c\u0438 \u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439;
- \u0441\u043b\u0443\u0447\u0430\u0438, \u043a\u043e\u0433\u0434\u0430 \u043e\u0431\u044f\u0437\u0430\u043d\u043d\u043e\u0441\u0442\u044c \u0438\u043b\u0438 \u043f\u0440\u0430\u0432\u043e \u0437\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u044b \u043d\u0435 \u0437\u0430 \u0442\u043e\u0439 \u0441\u0442\u043e\u0440\u043e\u043d\u043e\u0439;
- \u0441\u043b\u0443\u0447\u0430\u0438, \u043a\u043e\u0433\u0434\u0430 \u0432 \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u0430\u0445 \u0438\u043b\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0438 \u0441\u0442\u043e\u0440\u043e\u043d\u044b \u0435\u0441\u0442\u044c \u043d\u0435\u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u043e\u0441\u0442\u044c;
- \u0440\u0430\u0441\u043f\u043b\u044b\u0432\u0447\u0430\u0442\u044b\u0435 \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0438 \u0441\u0440\u043e\u043a\u043e\u0432 \u0431\u0435\u0437 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u0438\u043a\u0438;
- \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0438\u0435 \u043b\u043e\u0433\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u044f.

\u041d\u0435 \u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0441\u0442\u0438\u043b\u044c, \u043e\u0440\u0444\u043e\u0433\u0440\u0430\u0444\u0438\u044e \u0438 \u043e\u0431\u0449\u0443\u044e \u044e\u0440\u0438\u0434\u0438\u0447\u0435\u0441\u043a\u0443\u044e \u043f\u043e\u043b\u043d\u043e\u0442\u0443,
\u0435\u0441\u043b\u0438 \u044d\u0442\u043e \u043d\u0435 \u0441\u0432\u044f\u0437\u0430\u043d\u043e \u0441 \u0443\u043a\u0430\u0437\u0430\u043d\u043d\u044b\u043c\u0438 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f\u043c\u0438.

\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0442\u043e\u043b\u044c\u043a\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0435 \u0442\u0438\u043f\u044b \u043f\u0440\u043e\u0431\u043b\u0435\u043c:
INVALID_DATE, DATE_CONFLICT, TERM_CONFLICT, DEADLINE_CONFLICT, AMBIGUOUS_TIME,
WRONG_ACTOR, ROLE_CONFLICT, ENTITY_MISMATCH, INCONSISTENCY, MISSING_CONDITION,
AMBIGUOUS_PHRASE, UNILATERAL_RIGHT, TERM_MISUSE.

\u041a\u0430\u0436\u0434\u044b\u0439 \u043e\u0431\u044a\u0435\u043a\u0442 \u0434\u043e\u043b\u0436\u0435\u043d \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442\u044c paragraph_index, fragment, type,
severity, confidence, explanation, suggestion \u0438 optional replacement.
\u0415\u0441\u043b\u0438 \u043f\u0440\u043e\u0431\u043b\u0435\u043c \u043d\u0435\u0442, \u0432\u0435\u0440\u043d\u0438 {"issues": []}.
"""


class LlmIssuePayload(BaseModel):
    paragraph_index: int = Field(ge=1)
    fragment: str
    type: str
    severity: str
    confidence: str
    explanation: str
    suggestion: str
    replacement: str | None = None


class LlmIssueResponse(BaseModel):
    issues: list[LlmIssuePayload] = Field(default_factory=list)


class GeminiRateLimitError(Exception):
    """Raised when Gemini rate limits contract analysis requests."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class RuleBasedContractIssueAnalyzer(ContractIssueAnalyzer):
    _numeric_date_pattern = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{4})\b")
    _textual_date_pattern = re.compile(
        r"\b(\d{1,2})\s+(\u044f\u043d\u0432\u0430\u0440\u044f|\u0444\u0435\u0432\u0440\u0430\u043b\u044f|\u043c\u0430\u0440\u0442\u0430|\u0430\u043f\u0440\u0435\u043b\u044f|\u043c\u0430\u044f|\u0438\u044e\u043d\u044f|\u0438\u044e\u043b\u044f|\u0430\u0432\u0433\u0443\u0441\u0442\u0430|\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f|\u043e\u043a\u0442\u044f\u0431\u0440\u044f|\u043d\u043e\u044f\u0431\u0440\u044f|\u0434\u0435\u043a\u0430\u0431\u0440\u044f)\s+(\d{4})\s+\u0433(?:\u043e\u0434\u0430|\.?)?\b",
        re.IGNORECASE,
    )
    _period_pattern = re.compile(
        (
            r"(?:\u0441|\u0441\u0440\u043e\u043a \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430[:\s]*)\s*"
            r"(?P<start>\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{1,2}\s+[\u0430-\u044f\u0451]+\s+\d{4}\s+\u0433(?:\u043e\u0434\u0430|\.?)?)"
            r"\s*(?:\u043f\u043e|\u0434\u043e)\s*"
            r"(?P<end>\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{1,2}\s+[\u0430-\u044f\u0451]+\s+\d{4}\s+\u0433(?:\u043e\u0434\u0430|\.?)?)"
        ),
        re.IGNORECASE,
    )
    _ambiguous_time_phrases = (
        "\u0432 \u0440\u0430\u0437\u0443\u043c\u043d\u044b\u0439 \u0441\u0440\u043e\u043a",
        "\u0432 \u043a\u0440\u0430\u0442\u0447\u0430\u0439\u0448\u0438\u0439 \u0441\u0440\u043e\u043a",
        "\u0432 \u043a\u0440\u0430\u0442\u0447\u0430\u0439\u0448\u0438\u0435 \u0441\u0440\u043e\u043a\u0438",
        "\u043f\u043e \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438",
        "\u043f\u0440\u0438 \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e\u0441\u0442\u0438",
        "\u0431\u0435\u0437 \u043f\u0440\u043e\u043c\u0435\u0434\u043b\u0435\u043d\u0438\u044f",
        "\u043d\u0435\u0437\u0430\u043c\u0435\u0434\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e",
        "\u0432 \u0431\u043b\u0438\u0436\u0430\u0439\u0448\u0435\u0435 \u0432\u0440\u0435\u043c\u044f",
    )
    _ambiguous_phrase_markers = (
        "\u0438\u043d\u044b\u0435 \u043e\u0431\u0441\u0442\u043e\u044f\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u0430",
        "\u043f\u043e \u0441\u0432\u043e\u0435\u043c\u0443 \u0443\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u044e",
        "\u0432 \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u044b\u0445 \u0441\u043b\u0443\u0447\u0430\u044f\u0445",
    )
    _additional_ambiguous_phrase_markers = (
        "\u0432 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043d\u043e\u043c \u043f\u043e\u0440\u044f\u0434\u043a\u0435",
        "\u0432 \u0440\u0430\u0437\u0443\u043c\u043d\u044b\u0439 \u0441\u0440\u043e\u043a",
        "\u043f\u043e \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e\u0441\u0442\u0438",
        "\u043f\u043e \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u0438\u044e \u0441\u0442\u043e\u0440\u043e\u043d",
    )
    _company_pattern = re.compile(r'\b\u041e\u041e\u041e\s*[«"]([^»"]+)[»"]', re.IGNORECASE)
    _fio_pattern = re.compile(r"\b[\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ [\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ [\u0410-\u042f\u0401][\u0430-\u044f\u0451]+\b")
    _wrong_actor_patterns = (
        (
            r"\b(?:\u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a|\u043f\u043e\u043a\u0443\u043f\u0430\u0442\u0435\u043b\u044c)\b[^.!?\n]{0,80}\b(?:\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442|\u043e\u043a\u0430\u0437\u0430\u0442\u044c|\u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442|\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c|\u043f\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u0442|\u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c|\u043f\u0435\u0440\u0435\u0434\u0430\u0435\u0442|\u043f\u0435\u0440\u0435\u0434\u0430\u0442\u044c)\b",
            "\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435, \u043f\u043e\u0445\u043e\u0436\u0435, \u0437\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u043e \u0437\u0430 \u043a\u043b\u0438\u0435\u043d\u0442\u0441\u043a\u043e\u0439 \u0441\u0442\u043e\u0440\u043e\u043d\u043e\u0439 \u0432\u043c\u0435\u0441\u0442\u043e \u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044f",
            "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c, \u043a\u0430\u043a\u0430\u044f \u0441\u0442\u043e\u0440\u043e\u043d\u0430 \u0434\u043e\u043b\u0436\u043d\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0442\u044c \u0443\u0441\u043b\u0443\u0433\u0443, \u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0443 \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0434\u0430\u0447\u0443",
        ),
        (
            r"\b(?:\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c|\u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a|\u043f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a|\u043f\u0440\u043e\u0434\u0430\u0432\u0435\u0446)\b[^.!?\n]{0,80}\b(?:\u043e\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0435\u0442|\u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c|\u043e\u043f\u043b\u0430\u0442\u0430|\u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0435\u0442|\u043f\u0440\u0438\u043d\u044f\u0442\u044c|\u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u044b\u0432\u0430\u0435\u0442|\u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u0442\u044c)\b",
            "\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435, \u043f\u043e\u0445\u043e\u0436\u0435, \u0437\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u043e \u0437\u0430 \u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u0435\u043c \u0432\u043c\u0435\u0441\u0442\u043e \u043a\u043b\u0438\u0435\u043d\u0442\u0441\u043a\u043e\u0439 \u0441\u0442\u043e\u0440\u043e\u043d\u044b",
            "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c, \u043a\u0430\u043a\u0430\u044f \u0441\u0442\u043e\u0440\u043e\u043d\u0430 \u0434\u043e\u043b\u0436\u043d\u0430 \u043e\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0442\u044c, \u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0442\u044c \u0438\u043b\u0438 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u044b\u0432\u0430\u0442\u044c",
        ),
    )
    _term_misuse_patterns = (
        (
            re.compile(r"\b\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a\b", re.IGNORECASE),
            "\u041a\u043b\u0438\u0435\u043d\u0442",
            "\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0441\u043c\u0435\u0448\u0438\u0432\u0430\u044e\u0442\u0441\u044f \u0440\u043e\u043b\u0438 \u043e\u0434\u043d\u043e\u0439 \u0438 \u0442\u043e\u0439 \u0436\u0435 \u0441\u0442\u043e\u0440\u043e\u043d\u044b",
            "\u0423\u043d\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0442\u0435\u0440\u043c\u0438\u043d \u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u043e\u0434\u043d\u043e \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0441\u0442\u043e\u0440\u043e\u043d\u044b \u043f\u043e \u0432\u0441\u0435\u043c\u0443 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0443",
        ),
        (
            re.compile(r"\b\u041f\u043e\u043a\u0443\u043f\u0430\u0442\u0435\u043b\u044c\b", re.IGNORECASE),
            "\u041a\u043b\u0438\u0435\u043d\u0442",
            "\u0422\u0435\u0440\u043c\u0438\u043d \u0441\u0442\u043e\u0440\u043e\u043d\u044b \u043e\u0442\u043b\u0438\u0447\u0430\u0435\u0442\u0441\u044f \u043e\u0442 \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0440\u043e\u043b\u0438 \u0432 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0435",
            "\u0417\u0430\u043c\u0435\u043d\u0438\u0442\u044c \u0442\u0435\u0440\u043c\u0438\u043d \u043d\u0430 \u0435\u0434\u0438\u043d\u043e\u0435 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0441\u0442\u043e\u0440\u043e\u043d\u044b, \u0447\u0442\u043e\u0431\u044b \u0443\u0431\u0440\u0430\u0442\u044c \u0440\u0430\u0437\u043d\u043e\u0447\u0442\u0435\u043d\u0438\u044f",
        ),
        (
            re.compile(r"\b\u0418\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\b", re.IGNORECASE),
            "\u041f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a",
            "\u0414\u043b\u044f \u043e\u0434\u043d\u043e\u0439 \u0441\u0442\u043e\u0440\u043e\u043d\u044b \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0440\u0430\u0437\u043d\u044b\u0435 \u044e\u0440\u0438\u0434\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0442\u0435\u0440\u043c\u0438\u043d\u044b",
            "\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u043e\u0434\u0438\u043d \u0442\u0435\u0440\u043c\u0438\u043d \u0434\u043b\u044f \u0441\u0442\u043e\u0440\u043e\u043d\u044b-\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044f \u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u0435\u0433\u043e \u0432\u043e \u0432\u0441\u0435\u0445 \u0440\u0430\u0437\u0434\u0435\u043b\u0430\u0445",
        ),
        (
            re.compile(r"\b\u041f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a\b", re.IGNORECASE),
            "\u041f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a",
            "\u0422\u0435\u0440\u043c\u0438\u043d\u043e\u043b\u043e\u0433\u0438\u044f \u0441\u0442\u043e\u0440\u043e\u043d\u044b-\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044f \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f \u043d\u0435\u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u043e",
            "\u0423\u043d\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0442\u0435\u0440\u043c\u0438\u043d \u0441\u0442\u043e\u0440\u043e\u043d\u044b-\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044f \u043f\u043e \u0432\u0441\u0435\u043c\u0443 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0443",
        ),
    )

    _quoted_textual_date_pattern = re.compile(
        r'(?<!\d)[\u00ab"]?(\d{1,2})[\u00bb"]?\s+'
        r'('
        r'\u044f\u043d\u0432\u0430\u0440\u044f|'
        r'\u0444\u0435\u0432\u0440\u0430\u043b\u044f|'
        r'\u043c\u0430\u0440\u0442\u0430|'
        r'\u0430\u043f\u0440\u0435\u043b\u044f|'
        r'\u043c\u0430\u044f|'
        r'\u0438\u044e\u043d\u044f|'
        r'\u0438\u044e\u043b\u044f|'
        r'\u0430\u0432\u0433\u0443\u0441\u0442\u0430|'
        r'\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f|'
        r'\u043e\u043a\u0442\u044f\u0431\u0440\u044f|'
        r'\u043d\u043e\u044f\u0431\u0440\u044f|'
        r'\u0434\u0435\u043a\u0430\u0431\u0440\u044f'
        r')\s+(\d{4})\s+\u0433(?:\u043e\u0434\u0430|\.?)?\b',
        re.IGNORECASE,
    )
    _month_name_to_number = {
        "\u044f\u043d\u0432\u0430\u0440\u044f": 1,
        "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2,
        "\u043c\u0430\u0440\u0442\u0430": 3,
        "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
        "\u043c\u0430\u044f": 5,
        "\u0438\u044e\u043d\u044f": 6,
        "\u0438\u044e\u043b\u044f": 7,
        "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
        "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9,
        "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10,
        "\u043d\u043e\u044f\u0431\u0440\u044f": 11,
        "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
    }

    def analyze_result(self, document: ContractAnalysisDocument) -> ContractAnalysisResult:
        issues: list[ContractIssue] = []
        term_fragments: set[str] = set()
        term_paragraph_index: int | None = None
        company_mentions: dict[str, tuple[int, str]] = {}
        fio_mentions: dict[str, tuple[int, str]] = {}

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue

            issues.extend(self._find_invalid_dates(paragraph.paragraph_index, text))
            issues.extend(self._find_date_conflicts(paragraph.paragraph_index, text))
            issues.extend(self._find_ambiguous_time(paragraph.paragraph_index, text))
            issues.extend(self._find_ambiguous_phrases(paragraph.paragraph_index, text))
            issues.extend(self._find_wrong_actor(paragraph.paragraph_index, text))
            issues.extend(self._find_unilateral_rights(paragraph.paragraph_index, text))
            issues.extend(self._find_term_misuse(paragraph.paragraph_index, text))
            self._collect_entities(company_mentions, fio_mentions, paragraph.paragraph_index, text)

            if "\u0441\u0440\u043e\u043a \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430" in text.lower():
                term_fragments.add(self._normalize_space(text.lower()))
                term_paragraph_index = term_paragraph_index or paragraph.paragraph_index

        if len(term_fragments) > 1 and term_paragraph_index is not None:
            issues.append(
                ContractIssue(
                    paragraph_index=term_paragraph_index,
                    fragment="\u0441\u0440\u043e\u043a \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                    type="TERM_CONFLICT",
                    severity="medium",
                    confidence="medium",
                    explanation="\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0435\u0441\u0442\u044c \u0440\u0430\u0437\u043d\u044b\u0435 \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0438 \u0441\u0440\u043e\u043a\u0430 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430.",
                    suggestion=(
                        "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0432\u0441\u0435 \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f \u0441\u0440\u043e\u043a\u0430 \u0438 \u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043e\u0434\u043d\u0443 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u0443\u044e \u0432\u0435\u0440\u0441\u0438\u044e."
                    ),
                )
            )

        issues.extend(self._find_cross_paragraph_date_conflicts(document.paragraphs))
        issues.extend(self._find_entity_mismatches(company_mentions, "company"))
        issues.extend(self._find_entity_mismatches(fio_mentions, "person"))

        return ContractAnalysisResult(issues=issues, warnings=[])

    def _find_invalid_dates(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        for match in self._numeric_date_pattern.finditer(text):
            if self._parse_date(match.group(0)) is None:
                issues.append(
                    ContractIssue(
                        paragraph_index=paragraph_index,
                        fragment=match.group(0),
                        type="INVALID_DATE",
                        severity="high",
                        confidence="high",
                        explanation="\u0423\u043a\u0430\u0437\u0430\u043d\u0430 \u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0430\u044f \u0434\u0430\u0442\u0430.",
                        suggestion="\u0418\u0441\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0434\u0430\u0442\u0443 \u043d\u0430 \u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0443\u044e \u043a\u0430\u043b\u0435\u043d\u0434\u0430\u0440\u043d\u0443\u044e \u0434\u0430\u0442\u0443.",
                    )
                )

        for match in self._textual_date_pattern.finditer(text):
            if self._parse_date(match.group(0)) is None:
                issues.append(
                    ContractIssue(
                        paragraph_index=paragraph_index,
                        fragment=match.group(0),
                        type="INVALID_DATE",
                        severity="high",
                        confidence="high",
                        explanation="\u0423\u043a\u0430\u0437\u0430\u043d\u0430 \u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0430\u044f \u0434\u0430\u0442\u0430.",
                        suggestion="\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0447\u0438\u0441\u043b\u043e, \u043c\u0435\u0441\u044f\u0446 \u0438 \u0433\u043e\u0434 \u0438 \u0443\u043a\u0430\u0437\u0430\u0442\u044c \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u0443\u044e \u0434\u0430\u0442\u0443.",
                    )
                )

        return issues

    def _find_date_conflicts(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        for match in self._period_pattern.finditer(text):
            start_date = self._parse_date(match.group("start"))
            end_date = self._parse_date(match.group("end"))
            if start_date and end_date and end_date < start_date:
                issues.append(
                    ContractIssue(
                        paragraph_index=paragraph_index,
                        fragment=match.group(0),
                        type="DATE_CONFLICT",
                        severity="high",
                        confidence="high",
                        explanation="\u0414\u0430\u0442\u0430 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u043d\u0430\u0447\u0430\u043b\u0430.",
                        suggestion=(
                            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0434\u0430\u0442\u044b \u043d\u0430\u0447\u0430\u043b\u0430 \u0438 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0438 \u043f\u0440\u0438\u0432\u0435\u0441\u0442\u0438 \u0438\u0445 \u0432 \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0439 \u043f\u043e\u0440\u044f\u0434\u043e\u043a."
                        ),
                    )
                )

        return issues

    def _find_ambiguous_time(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        lowered_text = text.lower()
        issues: list[ContractIssue] = []

        for phrase in self._ambiguous_time_phrases:
            if phrase in lowered_text:
                issues.append(
                    ContractIssue(
                        paragraph_index=paragraph_index,
                        fragment=self._extract_fragment(text, phrase),
                        type="AMBIGUOUS_TIME",
                        severity="medium",
                        confidence="high",
                        explanation="\u0421\u0440\u043e\u043a \u0441\u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d \u0431\u0435\u0437 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u0438\u043a\u0438.",
                        suggestion="\u0417\u0430\u043c\u0435\u043d\u0438\u0442\u044c \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0443 \u043d\u0430 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u0443\u044e \u0434\u0430\u0442\u0443 \u0438\u043b\u0438 \u0438\u0437\u043c\u0435\u0440\u0438\u043c\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434.",
                    )
                )

        return issues

    def _find_ambiguous_phrases(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        lowered_text = text.lower()
        issues: list[ContractIssue] = []

        for marker in self._ambiguous_phrase_markers + self._additional_ambiguous_phrase_markers:
            if marker in lowered_text:
                issues.append(
                    ContractIssue(
                        paragraph_index=paragraph_index,
                        fragment=self._extract_fragment(text, marker),
                        type="AMBIGUOUS_PHRASE",
                        severity="medium",
                        confidence="medium",
                        explanation="\u0424\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0430 \u0434\u043e\u043f\u0443\u0441\u043a\u0430\u0435\u0442 \u043d\u0435\u043e\u0434\u043d\u043e\u0437\u043d\u0430\u0447\u043d\u043e\u0435 \u0442\u043e\u043b\u043a\u043e\u0432\u0430\u043d\u0438\u0435.",
                        suggestion="\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0443\u0441\u043b\u043e\u0432\u0438\u044f \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0438 \u043a\u0440\u0438\u0442\u0435\u0440\u0438\u0438 \u044d\u0442\u043e\u0439 \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0438.",
                    )
                )

        return issues

    def _find_wrong_actor(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        for pattern, explanation, suggestion in self._wrong_actor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue

            issues.append(
                ContractIssue(
                    paragraph_index=paragraph_index,
                    fragment=match.group(0).strip(" ,.;:"),
                    type="WRONG_ACTOR",
                    severity="high",
                    confidence="medium",
                    explanation=explanation,
                    suggestion=suggestion,
                )
            )

        return issues

    def _find_unilateral_rights(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        lowered_text = text.lower()
        if "\u0432 \u043e\u0434\u043d\u043e\u0441\u0442\u043e\u0440\u043e\u043d\u043d\u0435\u043c \u043f\u043e\u0440\u044f\u0434\u043a\u0435" not in lowered_text:
            return []
        if "\u0432\u043f\u0440\u0430\u0432\u0435" not in lowered_text and "\u043c\u043e\u0436\u0435\u0442" not in lowered_text:
            return []

        return [
            ContractIssue(
                paragraph_index=paragraph_index,
                fragment=self._extract_fragment(text, "\u0432 \u043e\u0434\u043d\u043e\u0441\u0442\u043e\u0440\u043e\u043d\u043d\u0435\u043c \u043f\u043e\u0440\u044f\u0434\u043a\u0435"),
                type="UNILATERAL_RIGHT",
                severity="medium",
                confidence="medium",
                explanation="\u0417\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u043e \u043e\u0434\u043d\u043e\u0441\u0442\u043e\u0440\u043e\u043d\u043d\u0435\u0435 \u043f\u0440\u0430\u0432\u043e \u0431\u0435\u0437 \u044f\u0432\u043d\u043e \u043e\u043f\u0438\u0441\u0430\u043d\u043d\u044b\u0445 \u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0439.",
                suggestion=(
                    "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u044f, \u043f\u043e\u0440\u044f\u0434\u043e\u043a \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f "
                    "\u0438 \u043f\u0440\u0435\u0434\u0435\u043b\u044b \u043e\u0434\u043d\u043e\u0441\u0442\u043e\u0440\u043e\u043d\u043d\u0435\u0433\u043e \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f."
                ),
            )
        ]

    def _find_term_misuse(self, paragraph_index: int, text: str) -> list[ContractIssue]:
        lowered_text = text.lower()
        issues: list[ContractIssue] = []

        if "\u043a\u043b\u0438\u0435\u043d\u0442" in lowered_text and (
            "\u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a" in lowered_text or "\u043f\u043e\u043a\u0443\u043f\u0430\u0442\u0435\u043b\u044c" in lowered_text
        ):
            issues.extend(
                self._find_term_misuse_by_patterns(
                    paragraph_index,
                    text,
                    allowed_terms={"\u041a\u043b\u0438\u0435\u043d\u0442"},
                )
            )

        if "\u043f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a" in lowered_text and (
            "\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c" in lowered_text or "\u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a" in lowered_text
        ):
            issues.extend(
                self._find_term_misuse_by_patterns(
                    paragraph_index,
                    text,
                    allowed_terms={"\u041f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a"},
                )
            )

        return issues

    def _find_term_misuse_by_patterns(
        self,
        paragraph_index: int,
        text: str,
        *,
        allowed_terms: set[str],
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        for pattern, replacement, explanation, suggestion in self._term_misuse_patterns:
            if replacement not in allowed_terms:
                continue

            match = pattern.search(text)
            if match is None:
                continue

            fragment = match.group(0)
            issues.append(
                ContractIssue(
                    paragraph_index=paragraph_index,
                    fragment=fragment,
                    type="TERM_MISUSE",
                    severity="medium",
                    confidence="high",
                    explanation=explanation,
                    suggestion=suggestion,
                    replacement=self._preserve_casing(fragment, replacement),
                )
            )

        return issues

    def _find_cross_paragraph_date_conflicts(
        self,
        paragraphs,
    ) -> list[ContractIssue]:
        signing_reference = self._detect_signing_date(paragraphs)
        if signing_reference is None:
            return []

        signing_date, signing_paragraph_index, signing_fragment = signing_reference
        issues: list[ContractIssue] = []
        term_end_markers: list[tuple[int, str, datetime]] = []

        for paragraph in paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue

            extracted_dates = self._extract_all_dates(text)
            if not extracted_dates:
                continue

            lowered_text = text.lower()

            if (
                paragraph.paragraph_index != signing_paragraph_index
                and self._contains_any(
                    lowered_text,
                    (
                        "\u0441 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                        "\u0441 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0435\u0433\u043e \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                        "\u0441 \u043c\u043e\u043c\u0435\u043d\u0442\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                        "\u0441 \u043c\u043e\u043c\u0435\u043d\u0442\u0430 \u0435\u0433\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f",
                        "\u043f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                        "\u043f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0435\u0433\u043e \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
                    ),
                )
            ):
                for fragment, date_value in extracted_dates:
                    if date_value < signing_date:
                        issues.append(
                            ContractIssue(
                                paragraph_index=paragraph.paragraph_index,
                                fragment=fragment,
                                type="DEADLINE_CONFLICT",
                                severity="high",
                                confidence="high",
                                explanation=(
                                    "\u0423\u043a\u0430\u0437\u0430\u043d\u043d\u044b\u0439 \u0441\u0440\u043e\u043a \u043d\u0430\u0441\u0442\u0443\u043f\u0430\u0435\u0442 \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430."
                                ),
                                suggestion=(
                                    f"\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0434\u0435\u0434\u043b\u0430\u0439\u043d \u043e\u0442\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c\u043d\u043e \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f {signing_fragment}."
                                ),
                            )
                        )
                        break

            if self._contains_any(lowered_text, ("\u0432\u044b\u043f\u0438\u0441\u043a\u0438 \u0438\u0437 \u0435\u0433\u0440\u043d \u043e\u0442", "\u0432\u044b\u043f\u0438\u0441\u043a\u0430 \u0438\u0437 \u0435\u0433\u0440\u043d \u043e\u0442")):
                for fragment, date_value in extracted_dates:
                    if date_value > signing_date:
                        issues.append(
                            ContractIssue(
                                paragraph_index=paragraph.paragraph_index,
                                fragment=fragment,
                                type="DATE_CONFLICT",
                                severity="medium",
                                confidence="medium",
                                explanation=(
                                    "\u0414\u0430\u0442\u0430 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u044e\u0449\u0435\u0433\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u043f\u043e\u0437\u0436\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430."
                                ),
                                suggestion=(
                                    "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0434\u0430\u0442\u0443 \u043f\u0440\u0430\u0432\u043e\u0443\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u044e\u0449\u0435\u0433\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u0438 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u0442\u044c \u0435\u0435 "
                                    f"\u0441 \u0434\u0430\u0442\u043e\u0439 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f {signing_fragment}."
                                ),
                            )
                        )
                        break

            if "\u043d\u0435 \u0440\u0430\u043d\u0435\u0435" in lowered_text:
                for fragment, date_value in extracted_dates:
                    if date_value < signing_date:
                        issues.append(
                            ContractIssue(
                                paragraph_index=paragraph.paragraph_index,
                                fragment=fragment,
                                type="DATE_CONFLICT",
                                severity="medium",
                                confidence="medium",
                                explanation=(
                                    "\u0413\u0440\u0430\u043d\u0438\u0447\u043d\u0430\u044f \u0434\u0430\u0442\u0430 \u0443\u043a\u0430\u0437\u0430\u043d\u0430 \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430."
                                ),
                                suggestion=(
                                    f"\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u043d\u0438\u0436\u043d\u044e\u044e \u0433\u0440\u0430\u043d\u0438\u0446\u0443 \u0441\u0440\u043e\u043a\u0430 \u0441 \u0443\u0447\u0435\u0442\u043e\u043c \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f {signing_fragment}."
                                ),
                            )
                        )
                        break

            if self._contains_any(lowered_text, ("\u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0434\u043e", "\u0441\u0447\u0438\u0442\u0430\u0435\u0442\u0441\u044f \u043f\u0440\u0435\u043a\u0440\u0430\u0449", "\u043f\u0440\u0435\u043a\u0440\u0430\u0449\u0435\u043d")):
                fragment, date_value = extracted_dates[-1]
                term_end_markers.append((paragraph.paragraph_index, fragment, date_value))
                if date_value < signing_date:
                    issues.append(
                        ContractIssue(
                            paragraph_index=paragraph.paragraph_index,
                            fragment=fragment,
                            type="DATE_CONFLICT",
                            severity="high",
                            confidence="high",
                            explanation=(
                                "\u0414\u0430\u0442\u0430 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u0435\u0433\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f."
                            ),
                            suggestion=(
                                f"\u0423\u043a\u0430\u0437\u0430\u0442\u044c \u0434\u0430\u0442\u0443 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u043f\u043e\u0437\u0436\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f {signing_fragment}."
                            ),
                        )
                    )

        unique_term_dates = {
            date_value.date().isoformat(): (paragraph_index, fragment)
            for paragraph_index, fragment, date_value in term_end_markers
        }
        if len(unique_term_dates) > 1:
            paragraph_index, fragment = next(iter(unique_term_dates.values()))
            issues.append(
                ContractIssue(
                    paragraph_index=paragraph_index,
                    fragment=fragment,
                    type="TERM_CONFLICT",
                    severity="medium",
                    confidence="medium",
                    explanation="\u0412 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u044b \u0440\u0430\u0437\u043d\u044b\u0435 \u0434\u0430\u0442\u044b \u043f\u0440\u0435\u043a\u0440\u0430\u0449\u0435\u043d\u0438\u044f \u0438\u043b\u0438 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0435\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f.",
                    suggestion="\u041e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043e\u0434\u043d\u0443 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u0443\u044e \u0434\u0430\u0442\u0443 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u0432\u043e \u0432\u0441\u0435\u0445 \u043f\u0443\u043d\u043a\u0442\u0430\u0445.",
                )
            )

        return issues

    def _detect_signing_date(self, paragraphs) -> tuple[datetime, int, str] | None:
        for paragraph in paragraphs[:6]:
            extracted_dates = self._extract_all_dates(paragraph.text)
            if not extracted_dates:
                continue
            lowered_text = paragraph.text.lower()
            if self._contains_any(
                lowered_text,
                ("\u0434\u043e\u0433\u043e\u0432\u043e\u0440", "\u0433. ", "\u0433\u043e\u0440\u043e\u0434", "\u043c\u043e\u0441\u043a\u0432\u0430", "\u0441\u0430\u043d\u043a\u0442-\u043f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433"),
            ):
                fragment, date_value = extracted_dates[0]
                return date_value, paragraph.paragraph_index, fragment

        for paragraph in paragraphs:
            extracted_dates = self._extract_all_dates(paragraph.text)
            if extracted_dates:
                fragment, date_value = extracted_dates[0]
                return date_value, paragraph.paragraph_index, fragment
        return None

    def _extract_all_dates(self, text: str) -> list[tuple[str, datetime]]:
        matches: list[tuple[int, str, datetime]] = []

        for pattern in (
            self._numeric_date_pattern,
            self._textual_date_pattern,
            self._quoted_textual_date_pattern,
        ):
            for match in pattern.finditer(text):
                parsed_date = self._parse_date_value(match.group(0))
                if parsed_date is None:
                    continue
                matches.append((match.start(), match.group(0), parsed_date))

        deduplicated: list[tuple[str, datetime]] = []
        seen: set[tuple[str, str]] = set()
        for _, fragment, parsed_date in sorted(matches, key=lambda item: item[0]):
            key = (fragment, parsed_date.isoformat())
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append((fragment, parsed_date))

        return deduplicated

    def _parse_date_value(self, raw_value: str) -> datetime | None:
        parsed = self._parse_date(raw_value)
        if parsed is not None:
            return parsed

        value = self._normalize_space(raw_value.strip().lower())
        quoted_match = self._quoted_textual_date_pattern.fullmatch(value)
        if quoted_match is None:
            return None

        day = int(quoted_match.group(1))
        month = self._month_name_to_number.get(quoted_match.group(2).lower())
        year = int(quoted_match.group(3))
        if month is None:
            return None

        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    def _contains_any(self, text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

    def _parse_date(self, raw_value: str) -> datetime | None:
        value = self._normalize_space(raw_value.lower())
        numeric_match = self._numeric_date_pattern.fullmatch(value)
        if numeric_match:
            day, month, year = map(int, numeric_match.groups())
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        textual_match = self._textual_date_pattern.fullmatch(value)
        if textual_match:
            day = int(textual_match.group(1))
            month = RUSSIAN_MONTHS[textual_match.group(2).lower()]
            year = int(textual_match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        return None

    def _preserve_casing(self, source: str, replacement: str) -> str:
        if source.isupper():
            return replacement.upper()
        if source.islower():
            return replacement.lower()
        if source[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    def _normalize_space(self, value: str) -> str:
        return " ".join(value.split())

    def _collect_entities(
        self,
        companies: dict[str, tuple[int, str]],
        people: dict[str, tuple[int, str]],
        paragraph_index: int,
        text: str,
    ) -> None:
        for match in self._company_pattern.finditer(text):
            original_value = f'\u041e\u041e\u041e "{match.group(1).strip()}"'
            normalized_value = self._normalize_space(match.group(1).lower())
            companies.setdefault(normalized_value, (paragraph_index, original_value))

        for match in self._fio_pattern.finditer(text):
            original_value = match.group(0).strip()
            normalized_value = self._normalize_space(original_value.lower())
            people.setdefault(normalized_value, (paragraph_index, original_value))

    def _find_entity_mismatches(
        self,
        entities: dict[str, tuple[int, str]],
        entity_kind: str,
    ) -> list[ContractIssue]:
        if len(entities) <= 1:
            return []

        sorted_entities = sorted(entities.values(), key=lambda item: item[0])
        paragraph_index, fragment = sorted_entities[1]
        entity_list = ", ".join(value for _, value in sorted_entities[:3])

        if entity_kind == "company":
            explanation = (
                f"\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u044e\u0442\u0441\u044f \u0440\u0430\u0437\u043d\u044b\u0435 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u044f \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u0439: {entity_list}."
            )
            suggestion = "\u0423\u043d\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u0438 \u0432\u043e \u0432\u0441\u0435\u0445 \u0440\u0430\u0437\u0434\u0435\u043b\u0430\u0445 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430."
        else:
            explanation = f"\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u044e\u0442\u0441\u044f \u0440\u0430\u0437\u043d\u044b\u0435 \u0424\u0418\u041e: {entity_list}."
            suggestion = "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c, \u043a\u0430\u043a\u043e\u0435 \u0424\u0418\u041e \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u0443\u043a\u0430\u0437\u0430\u043d\u043e \u043a\u043e\u043d\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043d\u043e \u043f\u043e \u0432\u0441\u0435\u043c\u0443 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0443."

        return [
            ContractIssue(
                paragraph_index=paragraph_index,
                fragment=fragment,
                type="ENTITY_MISMATCH",
                severity="high",
                confidence="medium",
                explanation=explanation,
                suggestion=suggestion,
            )
        ]

    def _extract_fragment(self, text: str, marker: str) -> str:
        match = re.search(re.escape(marker), text, re.IGNORECASE)
        if not match:
            return marker
        start = max(0, match.start() - 20)
        end = min(len(text), match.end() + 20)
        return text[start:end].strip(" ,.;:")


class GeminiContractIssueAnalyzer(ContractIssueAnalyzer):
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_contract_review_model
        self._base_url = settings.gemini_generate_content_base_url
        self._timeout_seconds = settings.gemini_timeout_seconds
        self._max_paragraphs_per_request = settings.gemini_max_paragraphs_per_request
        self._max_characters_per_request = settings.gemini_max_characters_per_request
        self._max_issues_per_request = settings.gemini_max_issues_per_request
        self._max_output_tokens = settings.gemini_max_output_tokens
        self._max_retries = settings.gemini_max_retries
        self._retry_base_seconds = settings.gemini_retry_base_seconds

    def analyze_result(self, document: ContractAnalysisDocument) -> ContractAnalysisResult:
        if not self._api_key or not document.paragraphs:
            return ContractAnalysisResult(issues=[], warnings=[])

        issues: list[ContractIssue] = []
        prepared_paragraphs = self._prepare_paragraphs(document)
        if not prepared_paragraphs:
            return ContractAnalysisResult(issues=[], warnings=[])

        try:
            for chunk in self._chunk_paragraphs(prepared_paragraphs):
                payload = self._request_chunk(chunk)
                if payload is None:
                    continue
                issues.extend(self._to_issues(payload, len(document.paragraphs)))
        except GeminiRateLimitError as error:
            warning = self._warning_from_gemini_error(error)
            LOGGER.warning(
                "Gemini contract analysis skipped; returning rule-based results only: %s",
                warning.message,
            )
            return ContractAnalysisResult(issues=issues, warnings=[warning])

        return ContractAnalysisResult(issues=issues, warnings=[])
    
    def analyze_with_context(
        self,
        document: ContractAnalysisDocument,
        semantic_summary: str,
        candidate_signals: list[str],
    ) -> ContractAnalysisResult:
        if not self._api_key or not document.paragraphs:
            return ContractAnalysisResult(issues=[], warnings=[])

        issues: list[ContractIssue] = []
        warnings: list[ContractAnalysisWarning] = []

        context_prompt = (
            "Используй следующий семантический контекст документа для глубокого анализа:\n"
            f"<SEMANTIC_CONTEXT>\n{semantic_summary}\n</SEMANTIC_CONTEXT>\n\n"
        )
        
        if candidate_signals:
            context_prompt += (
                "Обрати особое внимание на следующие потенциальные проблемы, выявленные ранее:\n"
                f"<CANDIDATE_SIGNALS>\n" + "\n".join(candidate_signals) + "\n</CANDIDATE_SIGNALS>\n\n"
            )

        context_prompt += (
            "Твоя задача — выявить:\n"
            "1. Некорректное употребление терминов и предложить замену\n"
            "2. Логические противоречия в условиях\n"
            "3. Расхождения в наименованиях контрагентов\n"
            "4. Противоречия в датах и сроках\n\n"
            "Для каждой проблемы обязательно предложи замену в поле 'replacement', "
            "чтобы исправление можно было внести в текст автоматически"
        )

        prepared_paragraphs = self._prepare_paragraphs(document)
        if not prepared_paragraphs:
            return ContractAnalysisResult(issues=[], warnings=[])

        try:
            for chunk in self._chunk_paragraphs(prepared_paragraphs):
                payload = self._request_chunk(chunk, context_prompt=context_prompt)
                if payload is None:
                    continue
                
                chunk_issues = self._to_issues(payload, len(document.paragraphs))
                issues.extend(chunk_issues)
                
        except GeminiRateLimitError as error:
            warning = self._warning_from_gemini_error(error)
            LOGGER.warning(
                "Gemini context analysis skipped due to rate limits: %s",
                warning.message,
            )
            warnings.append(warning)
        except Exception as error:
            LOGGER.error("Unexpected error during Gemini context analysis: %s", error)
            warnings.append(ContractAnalysisWarning(
                code="llm_analysis_error",
                message=f"Ошибка при выполнении LLM-анализа: {str(error)}"
            ))

        return ContractAnalysisResult(issues=issues, warnings=warnings)

    def _prepare_paragraphs(
        self,
        document: ContractAnalysisDocument,
    ) -> list[tuple[int, str]]:
        repeated_boundary_fragments = self._repeated_page_boundary_fragments(document)
        prepared: list[tuple[int, str]] = []

        for paragraph in document.paragraphs:
            cleaned_text = self._clean_paragraph_text(paragraph.text)
            if not cleaned_text:
                continue

            if self._normalize_fragment_key(cleaned_text) in repeated_boundary_fragments:
                continue

            prepared.append((paragraph.paragraph_index, cleaned_text))

        return prepared

    def _repeated_page_boundary_fragments(
        self,
        document: ContractAnalysisDocument,
    ) -> set[str]:
        candidates: dict[str, int] = {}

        for page in document.pages:
            boundary_blocks = [block for block in page.blocks if block.text.strip()]
            if len(boundary_blocks) < 2:
                continue

            for block in (boundary_blocks[0], boundary_blocks[-1]):
                cleaned_text = self._clean_paragraph_text(block.text)
                if not cleaned_text or len(cleaned_text) > 120:
                    continue

                key = self._normalize_fragment_key(cleaned_text)
                candidates[key] = candidates.get(key, 0) + 1

        return {key for key, count in candidates.items() if count >= 2}

    def _clean_paragraph_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        previous_line = ""

        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            if self._looks_like_ocr_noise(line):
                continue
            if line == previous_line:
                continue

            cleaned_lines.append(line)
            previous_line = line

        return " ".join(cleaned_lines)

    def _looks_like_ocr_noise(self, line: str) -> bool:
        alnum_count = sum(char.isalnum() for char in line)
        if not alnum_count:
            return True

        if len(line) < 4:
            return False

        punctuation_count = sum(not char.isalnum() and not char.isspace() for char in line)
        return punctuation_count > alnum_count

    def _normalize_fragment_key(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _chunk_paragraphs(
        self,
        paragraphs: list[tuple[int, str]],
    ) -> list[list[tuple[int, str]]]:
        total_length = sum(len(text) for _, text in paragraphs)
        if total_length <= self._max_characters_per_request:
            return [paragraphs]

        chunks: list[list[tuple[int, str]]] = []
        current_chunk: list[tuple[int, str]] = []
        current_length = 0

        for entry in paragraphs:
            entry_length = len(entry[1])
            if current_chunk and current_length + entry_length > self._max_characters_per_request:
                chunks.append(current_chunk)
                current_chunk = []
                current_length = 0

            current_chunk.append(entry)
            current_length += entry_length

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _request_chunk(
        self, 
        chunk: list[tuple[int, str]], 
        context_prompt: str | None = None,
        custom_prompt: str | None = None
    ) -> LlmIssueResponse | None:
        effective_prompt = custom_prompt if custom_prompt is not None else context_prompt

        document_text = "\n".join(f"[{index}] {text}" for index, text in chunk if text.strip())
        if not document_text:
            return None

        user_message = document_text
        if context_prompt:
            user_message = f"{effective_prompt}\n\nТЕКСТ ДОГОВОРА ДЛЯ АНАЛИЗА:\n{document_text}"

        request_payload = self._build_request_payload(user_message)

        with httpx.Client(timeout=self._timeout_seconds ) as client:
            response = self._post_with_retries(client, request_payload)
            if response is None:
                return None

        try:
            payload = response.json()
            output_text = self._extract_output_text(payload)
            if not output_text:
                return None
            
            clean_json = re.sub(r"^```json\s*|\s*```$", "", output_text.strip(), flags=re.MULTILINE | re.IGNORECASE)
            return LlmIssueResponse.model_validate(json.loads(clean_json))
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            LOGGER.warning("Gemini contract analysis response validation failed: %s", error)
            return None

    def _build_request_payload(self, user_message: str) -> dict:
        return {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "Review the contract and return only potential issues of these types: "
                            "INVALID_DATE, DATE_CONFLICT, TERM_CONFLICT, TERM_MISUSE, DEADLINE_CONFLICT, "
                            "AMBIGUOUS_TIME, WRONG_ACTOR, ROLE_CONFLICT, ENTITY_MISMATCH, "
                            "INCONSISTENCY, MISSING_CONDITION, AMBIGUOUS_PHRASE, "
                            "UNILATERAL_RIGHT. Ignore style, spelling, and general legal "
                            "completeness. Return every relevant issue you find, not only the "
                            "highest-confidence ones. "
                            f"If there are many, return up to {self._max_issues_per_request} issues "
                            "sorted by paragraph order. "
                            "Write concise Russian explanation and suggestion, one sentence "
                            "each, no more than 180 characters per field. Include replacement only "
                            "when you can confidently propose an exact substitute. Return strict JSON only"
                        ),
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Contract paragraphs with indexes. Report only the requested issue "
                                f"classes.\n\n{user_message}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": self._schema(),
                "temperature": 0,
                "maxOutputTokens": self._max_output_tokens,
            },
        }

    def _post_with_retries(
        self,
        client: httpx.Client,
        request_payload: dict,
    ) -> httpx.Response | None:
        for attempt in range(self._max_retries + 1):
            try:
                response = client.post(
                    f"{self._base_url}/{self._model}:generateContent",
                    params={"key": self._api_key},
                    headers={
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    error_code = self._extract_error_status(error.response)
                    if error_code == "resource_exhausted":
                        raise GeminiRateLimitError(
                            self._extract_rate_limit_message(error.response),
                            error_code=error_code,
                        ) from error

                    if attempt >= self._max_retries:
                        raise GeminiRateLimitError(
                            self._extract_rate_limit_message(error.response),
                            error_code=error_code,
                        ) from error

                    retry_after = self._retry_delay_seconds(error.response, attempt)
                    LOGGER.warning(
                        "Gemini contract analysis hit rate limit, retrying in %.1f seconds "
                        "(attempt %s/%s).",
                        retry_after,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    time.sleep(retry_after)
                    continue

                LOGGER.warning("Gemini contract analysis request failed: %s", error)
                return None
            except httpx.HTTPError as error:
                LOGGER.warning("Gemini contract analysis request failed: %s", error)
                return None

        return None

    def _retry_delay_seconds(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
        return self._retry_base_seconds * (2**attempt)

    def _extract_rate_limit_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "HTTP 429"

        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return response.text or "HTTP 429"

    def _extract_error_status(self, response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None

        error = payload.get("error")
        if not isinstance(error, dict):
            return None

        status = error.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip().lower()
        return None

    def _warning_from_gemini_error(
        self,
        error: GeminiRateLimitError,
    ) -> ContractAnalysisWarning:
        if error.error_code == "resource_exhausted":
            return ContractAnalysisWarning(
                code="llm_insufficient_quota",
                message=(
                    "LLM-анализ Gemini не выполнен: исчерпана квота или не подключён биллинг"
                    "\u041f\u043e\u043a\u0430\u0437\u0430\u043d\u044b \u0442\u043e\u043b\u044c\u043a\u043e \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 rule-based \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438."
                ),
            )

        return ContractAnalysisWarning(
            code="llm_temporarily_unavailable",
            message=(
                "LLM-анализ Gemini временно недоступен из-за лимитов API. "
                "\u041f\u043e\u043a\u0430\u0437\u0430\u043d\u044b \u0442\u043e\u043b\u044c\u043a\u043e \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 rule-based \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438."
            ),
        )

    def _schema(self) -> dict:
        return {
            "type": "OBJECT",
            "properties": {
                "issues": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "paragraph_index": {"type": "INTEGER"},
                            "fragment": {"type": "STRING"},
                            "type": {"type": "STRING", "enum": sorted(ISSUE_TYPES)},
                            "severity": {"type": "STRING", "enum": ["high", "medium", "low"]},
                            "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
                            "explanation": {"type": "STRING"},
                            "suggestion": {"type": "STRING"},
                            "replacement": {"type": "STRING", "nullable": True},
                        },
                        "required": [
                            "paragraph_index",
                            "fragment",
                            "type",
                            "severity",
                            "confidence",
                            "explanation",
                            "suggestion",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["issues"],
            "additionalProperties": False,
        }

    def _extract_output_text(self, payload: dict) -> str | None:
        for candidate in payload.get("candidates", []):
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        return None

    def _to_issues(
        self,
        payload: LlmIssueResponse,
        total_paragraphs: int,
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        for item in payload.issues:
            if item.paragraph_index < 1 or item.paragraph_index > total_paragraphs:
                continue
            issues.append(
                ContractIssue(
                    paragraph_index=item.paragraph_index,
                    fragment=item.fragment.strip(),
                    type=item.type,
                    severity=item.severity,
                    confidence=item.confidence,
                    explanation=item.explanation.strip(),
                    suggestion=item.suggestion.strip(),
                    replacement=item.replacement.strip() if item.replacement else None,
                )
            )

        return issues


class CompositeContractIssueAnalyzer(ContractIssueAnalyzer):
    def __init__(self, analyzers: list[ContractIssueAnalyzer]) -> None:
        self._analyzers = analyzers

    def analyze_result(self, document: ContractAnalysisDocument) -> ContractAnalysisResult:
        merged: dict[tuple[int, str, str], ContractIssue] = {}
        warnings: list[ContractAnalysisWarning] = []

        for analyzer in self._analyzers:
            result = analyzer.analyze_result(document)
            warnings.extend(result.warnings)
            for issue in result.issues:
                key = (issue.paragraph_index, issue.type, self._normalize_fragment(issue.fragment))
                current = merged.get(key)
                if current is None or self._score(issue) > self._score(current):
                    merged[key] = issue

        return ContractAnalysisResult(
            issues=sorted(
                merged.values(),
                key=lambda issue: (
                    issue.paragraph_index,
                    self._severity_order(issue.severity),
                    issue.type,
                ),
            ),
            warnings=self._deduplicate_warnings(warnings),
        )

    def _normalize_fragment(self, fragment: str) -> str:
        return " ".join(fragment.lower().split())

    def _score(self, issue: ContractIssue) -> tuple[int, int, int]:
        return (
            self._confidence_order(issue.confidence),
            -self._severity_order(issue.severity),
            len(issue.explanation) + len(issue.suggestion),
        )

    def _confidence_order(self, value: str) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(value.lower(), 0)

    def _severity_order(self, value: str) -> int:
        return {"high": 0, "medium": 1, "low": 2}.get(value.lower(), 99)

    def _deduplicate_warnings(
        self,
        warnings: list[ContractAnalysisWarning],
    ) -> list[ContractAnalysisWarning]:
        seen: set[tuple[str, str]] = set()
        unique: list[ContractAnalysisWarning] = []

        for warning in warnings:
            key = (warning.code, warning.message)
            if key in seen:
                continue
            seen.add(key)
            unique.append(warning)

        return unique

