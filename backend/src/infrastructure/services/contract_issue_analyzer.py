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
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

ISSUE_TYPES = {
    "INVALID_DATE",
    "DATE_CONFLICT",
    "TERM_CONFLICT",
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

SYSTEM_PROMPT = """Проанализируй текст договора.
Найди только потенциальные ошибки в сроках, датах, ролях сторон
и логике обязательств.

Считай ошибками:
- несуществующие даты;
- дату окончания раньше даты начала;
- противоречие между сроком договора и сроками платежей;
- случаи, когда обязанность или право закреплены не за той стороной;
- случаи, когда в реквизитах или названии стороны есть несогласованность;
- расплывчатые формулировки сроков без конкретики;
- внутренние логические противоречия.

Не анализируй стиль, орфографию и общую юридическую полноту,
если это не связано с указанными категориями.

Используй только следующие типы проблем:
INVALID_DATE, DATE_CONFLICT, TERM_CONFLICT, DEADLINE_CONFLICT, AMBIGUOUS_TIME,
WRONG_ACTOR, ROLE_CONFLICT, ENTITY_MISMATCH, INCONSISTENCY, MISSING_CONDITION,
AMBIGUOUS_PHRASE, UNILATERAL_RIGHT.

Каждый объект должен содержать paragraph_index, fragment, type,
severity, confidence, explanation и suggestion.
Если проблем нет, верни {"issues": []}.
"""


class LlmIssuePayload(BaseModel):
    paragraph_index: int = Field(ge=1)
    fragment: str
    type: str
    severity: str
    confidence: str
    explanation: str
    suggestion: str


class LlmIssueResponse(BaseModel):
    issues: list[LlmIssuePayload] = Field(default_factory=list)


class OpenAIRateLimitError(Exception):
    """Raised when OpenAI rate limits contract analysis requests."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class RuleBasedContractIssueAnalyzer(ContractIssueAnalyzer):
    _numeric_date_pattern = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{4})\b")
    _textual_date_pattern = re.compile(
        r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\s+г(?:ода|\.?)?\b",
        re.IGNORECASE,
    )
    _period_pattern = re.compile(
        (
            r"(?:с|срок действия договора[:\s]*)\s*"
            r"(?P<start>\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{1,2}\s+[а-яё]+\s+\d{4}\s+г(?:ода|\.?)?)"
            r"\s*(?:по|до)\s*"
            r"(?P<end>\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{1,2}\s+[а-яё]+\s+\d{4}\s+г(?:ода|\.?)?)"
        ),
        re.IGNORECASE,
    )
    _ambiguous_time_phrases = (
        "в разумный срок",
        "в кратчайший срок",
        "в кратчайшие сроки",
        "по возможности",
        "при необходимости",
        "без промедления",
        "незамедлительно",
        "в ближайшее время",
    )
    _ambiguous_phrase_markers = (
        "иные обстоятельства",
        "по своему усмотрению",
        "в необходимых случаях",
    )

    _additional_ambiguous_phrase_markers = (
        "в установленном порядке",
        "в разумный срок",
        "по необходимости",
        "по согласованию сторон",
    )
    _company_pattern = re.compile(r'\bООО\s*[«"]([^»"]+)[»"]', re.IGNORECASE)
    _fio_pattern = re.compile(r"\b[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+\b")
    _wrong_actor_patterns = (
        (
            r"\b(?:заказчик|покупатель)\b[^.!?\n]{0,80}\b(?:оказывает|оказать|выполняет|выполнить|поставляет|поставить|передает|передать)\b",
            "Действие, похоже, закреплено за клиентской стороной вместо исполнителя.",
            "Проверить, какая сторона должна выполнять услугу, поставку или передачу.",
        ),
        (
            r"\b(?:исполнитель|поставщик|подрядчик|продавец)\b[^.!?\n]{0,80}\b(?:оплачивает|оплатить|оплата|принимает|принять|согласовывает|согласовать)\b",
            "Действие, похоже, закреплено за исполнителем вместо клиентской стороны.",
            "Проверить, какая сторона должна оплачивать, принимать или согласовывать.",
        ),
    )

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
            self._collect_entities(company_mentions, fio_mentions, paragraph.paragraph_index, text)

            if "срок действия договора" in text.lower():
                term_fragments.add(self._normalize_space(text.lower()))
                term_paragraph_index = term_paragraph_index or paragraph.paragraph_index

        if len(term_fragments) > 1 and term_paragraph_index is not None:
            issues.append(
                ContractIssue(
                    paragraph_index=term_paragraph_index,
                    fragment="срок действия договора",
                    type="TERM_CONFLICT",
                    severity="medium",
                    confidence="medium",
                    explanation="В документе есть разные формулировки срока действия договора.",
                    suggestion=(
                        "Проверить все упоминания срока и оставить одну согласованную версию."
                    ),
                )
            )

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
                        explanation="Указана несуществующая дата.",
                        suggestion="Исправить дату на существующую календарную дату.",
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
                        explanation="Указана несуществующая дата.",
                        suggestion="Проверить число, месяц и год и указать корректную дату.",
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
                        explanation="Дата окончания раньше даты начала.",
                        suggestion=(
                            "Уточнить даты начала и окончания и привести их в правильный порядок."
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
                        explanation="Срок сформулирован без конкретики.",
                        suggestion="Заменить формулировку на конкретную дату или измеримый период.",
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
                        explanation="Формулировка допускает неоднозначное толкование.",
                        suggestion="Уточнить условия применения и критерии этой формулировки.",
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
        if "в одностороннем порядке" not in lowered_text:
            return []
        if "вправе" not in lowered_text and "может" not in lowered_text:
            return []

        return [
            ContractIssue(
                paragraph_index=paragraph_index,
                fragment=self._extract_fragment(text, "в одностороннем порядке"),
                type="UNILATERAL_RIGHT",
                severity="medium",
                confidence="medium",
                explanation="Закреплено одностороннее право без явно описанных оснований.",
                suggestion=(
                    "Уточнить основания, порядок уведомления "
                    "и пределы одностороннего изменения."
                ),
            )
        ]

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
            original_value = f'ООО "{match.group(1).strip()}"'
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
                f"В документе встречаются разные наименования организаций: {entity_list}."
            )
            suggestion = "Унифицировать наименование организации во всех разделах договора."
        else:
            explanation = f"В документе встречаются разные ФИО: {entity_list}."
            suggestion = "Проверить, какое ФИО должно быть указано консистентно по всему документу."

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


class OpenAIContractIssueAnalyzer(ContractIssueAnalyzer):
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.openai_api_key
        self._model = settings.openai_contract_review_model
        self._base_url = settings.openai_responses_base_url
        self._timeout_seconds = settings.openai_timeout_seconds
        self._max_paragraphs_per_request = settings.openai_max_paragraphs_per_request
        self._max_characters_per_request = settings.openai_max_characters_per_request
        self._max_issues_per_request = settings.openai_max_issues_per_request
        self._max_output_tokens = settings.openai_max_output_tokens
        self._max_retries = settings.openai_max_retries
        self._retry_base_seconds = settings.openai_retry_base_seconds

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
        except OpenAIRateLimitError as error:
            warning = self._warning_from_openai_error(error)
            LOGGER.warning(
                "OpenAI contract analysis skipped; returning rule-based results only: %s",
                warning.message,
            )
            return ContractAnalysisResult(issues=issues, warnings=[warning])

        return ContractAnalysisResult(issues=issues, warnings=[])

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

    def _request_chunk(self, chunk: list[tuple[int, str]]) -> LlmIssueResponse | None:
        user_message = "\n".join(f"[{index}] {text}" for index, text in chunk if text.strip())
        if not user_message:
            return None

        request_payload = {
            "model": self._model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Ниже текст договора с индексами абзацев. "
                        "Верни только JSON строго по схеме.\n\n"
                        f"{user_message}"
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "contract_issues",
                    "strict": True,
                    "schema": self._schema(),
                }
            },
        }
        request_payload = self._build_request_payload(user_message)

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = self._post_with_retries(client, request_payload)
            if response is None:
                return None

        payload = response.json()
        output_text = payload.get("output_text") or self._extract_output_text(
            payload.get("output", [])
        )
        if not output_text:
            return None

        try:
            return LlmIssueResponse.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as error:
            LOGGER.warning("OpenAI contract analysis response validation failed: %s", error)
            return None

    def _build_request_payload(self, user_message: str) -> dict:
        return {
            "model": self._model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Review the contract and return only potential issues of these types: "
                        "INVALID_DATE, DATE_CONFLICT, TERM_CONFLICT, DEADLINE_CONFLICT, "
                        "AMBIGUOUS_TIME, WRONG_ACTOR, ROLE_CONFLICT, ENTITY_MISMATCH, "
                        "INCONSISTENCY, MISSING_CONDITION, AMBIGUOUS_PHRASE, "
                        "UNILATERAL_RIGHT. Ignore style, spelling, and general legal "
                        "completeness. Return every relevant issue you find, not only the "
                        "highest-confidence ones. "
                        f"If there are many, return up to {self._max_issues_per_request} issues "
                        "sorted by paragraph order. "
                        "Write concise Russian explanation and suggestion, one sentence "
                        "each, no more than 180 characters per field. Return strict JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Contract paragraphs with indexes. Report only the requested issue "
                        f"classes.\n\n{user_message}"
                    ),
                },
            ],
            "max_output_tokens": self._max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "contract_issues",
                    "strict": True,
                    "schema": self._schema(),
                }
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
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    error_code = self._extract_error_code(error.response)
                    if error_code == "insufficient_quota":
                        raise OpenAIRateLimitError(
                            self._extract_rate_limit_message(error.response),
                            error_code=error_code,
                        ) from error

                    if attempt >= self._max_retries:
                        raise OpenAIRateLimitError(
                            self._extract_rate_limit_message(error.response),
                            error_code=error_code,
                        ) from error

                    retry_after = self._retry_delay_seconds(error.response, attempt)
                    LOGGER.warning(
                        "OpenAI contract analysis hit rate limit, retrying in %.1f seconds "
                        "(attempt %s/%s).",
                        retry_after,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    time.sleep(retry_after)
                    continue

                LOGGER.warning("OpenAI contract analysis request failed: %s", error)
                return None
            except httpx.HTTPError as error:
                LOGGER.warning("OpenAI contract analysis request failed: %s", error)
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

    def _extract_error_code(self, response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None

        error = payload.get("error")
        if not isinstance(error, dict):
            return None

        code = error.get("code")
        return code.strip() if isinstance(code, str) and code.strip() else None

    def _warning_from_openai_error(
        self,
        error: OpenAIRateLimitError,
    ) -> ContractAnalysisWarning:
        if error.error_code == "insufficient_quota":
            return ContractAnalysisWarning(
                code="llm_insufficient_quota",
                message=(
                    "LLM-анализ OpenAI не выполнен: исчерпана квота или не подключён биллинг. "
                    "Показаны только локальные rule-based проверки."
                ),
            )

        return ContractAnalysisWarning(
            code="llm_temporarily_unavailable",
            message=(
                "LLM-анализ OpenAI временно недоступен из-за лимитов API. "
                "Показаны только локальные rule-based проверки."
            ),
        )

    def _schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paragraph_index": {"type": "integer"},
                            "fragment": {"type": "string"},
                            "type": {"type": "string", "enum": sorted(ISSUE_TYPES)},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "explanation": {"type": "string"},
                            "suggestion": {"type": "string"},
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

    def _extract_output_text(self, output_items: list[dict]) -> str | None:
        for item in output_items:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")
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
