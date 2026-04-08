from src.application.services.contract_issue_analyzer import build_contract_analysis_document
from src.domain.entities.document import DocumentPage, ParagraphBlock, TextRun
from src.infrastructure.services.contract_issue_analyzer import (
    GeminiContractIssueAnalyzer,
    GeminiRateLimitError,
    RuleBasedContractIssueAnalyzer,
)


def test_rule_based_analyzer_finds_invalid_dates_and_ambiguous_time() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(
                        id="1",
                        runs=[TextRun(text="Договор действует с 31.02.2025 по 15.03.2025.")],
                    ),
                    ParagraphBlock(
                        id="2",
                        runs=[TextRun(text="Оплата производится в разумный срок.")],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "INVALID_DATE" for issue in issues)
    assert any(issue.type == "AMBIGUOUS_TIME" for issue in issues)


def test_rule_based_analyzer_finds_wrong_actor() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(
                        id="1",
                        runs=[TextRun(text="Заказчик оказывает услуги по настоящему договору.")],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "WRONG_ACTOR" for issue in issues)


def test_rule_based_analyzer_finds_entity_mismatch() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(
                        id="1",
                        runs=[TextRun(text='Сторона 1: ООО "Ромашка". Директор Иванов Иван Иванович.')],
                    ),
                    ParagraphBlock(
                        id="2",
                        runs=[TextRun(text='Сторона 2: ООО "Лютик". Представитель Петров Петр Петрович.')],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "ENTITY_MISMATCH" for issue in issues)


def test_rule_based_analyzer_finds_requested_ambiguous_phrase() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(
                        id="1",
                        runs=[TextRun(text="Оплата производится по согласованию сторон.")],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "AMBIGUOUS_PHRASE" for issue in issues)


def test_rule_based_analyzer_finds_term_misuse_with_replacement() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(
                        id="1",
                        runs=[TextRun(text="Клиент направляет заявку, а Заказчик подписывает приложение.")],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    term_issue = next(issue for issue in issues if issue.type == "TERM_MISUSE")
    assert term_issue.fragment == "Заказчик"
    assert term_issue.replacement == "Клиент"


def test_rule_based_analyzer_finds_deadline_before_quoted_signing_date() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(id="1", runs=[TextRun(text="г. Москва\n«25» марта 2026 г.")]),
                    ParagraphBlock(
                        id="2",
                        runs=[
                            TextRun(
                                text=(
                                    "Покупатель обязуется открыть аккредитив в течение 5 рабочих дней "
                                    "с даты подписания договора, но не позднее 01 марта 2026 года."
                                )
                            )
                        ],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "DEADLINE_CONFLICT" for issue in issues)


def test_rule_based_analyzer_finds_contract_end_before_signing_date() -> None:
    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(id="1", runs=[TextRun(text="г. Москва\n«25» марта 2026 г.")]),
                    ParagraphBlock(
                        id="2",
                        runs=[
                            TextRun(
                                text=(
                                    "Настоящий договор вступает в силу с момента его подписания "
                                    "Сторонами 25 марта 2026 года и действует до 31 декабря 2025 года."
                                )
                            )
                        ],
                    ),
                ],
            )
        ],
    )

    issues = RuleBasedContractIssueAnalyzer().analyze(document)

    assert any(issue.type == "DATE_CONFLICT" for issue in issues)


def test_gemini_analyzer_returns_warning_after_quota_error(monkeypatch) -> None:
    analyzer = GeminiContractIssueAnalyzer()
    analyzer._api_key = "test-key"

    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[ParagraphBlock(id="1", runs=[TextRun(text="Первый абзац.")])],
            ),
            DocumentPage(
                number=2,
                blocks=[ParagraphBlock(id="2", runs=[TextRun(text="Второй абзац.")])],
            ),
        ],
    )

    calls = {"count": 0}

    def _raise_rate_limit(_chunk):
        calls["count"] += 1
        raise GeminiRateLimitError("quota exceeded", error_code="resource_exhausted")

    monkeypatch.setattr(analyzer, "_request_chunk", _raise_rate_limit)

    result = analyzer.analyze_result(document)

    assert result.issues == []
    assert result.warnings[0].code == "llm_insufficient_quota"
    assert calls["count"] == 1


def test_gemini_analyzer_sends_whole_cleaned_document_in_single_request(monkeypatch) -> None:
    analyzer = GeminiContractIssueAnalyzer()
    analyzer._api_key = "test-key"
    analyzer._max_characters_per_request = 5000

    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(id="header-1", runs=[TextRun(text="ООО Ромашка")]),
                    ParagraphBlock(
                        id="1",
                        runs=[
                            TextRun(
                                text="Поставщик обязан поставить товар.\n\n"
                                "Поставщик обязан поставить товар.\n"
                                "!!! --- !!!"
                            )
                        ],
                    ),
                ],
            ),
            DocumentPage(
                number=2,
                blocks=[
                    ParagraphBlock(id="header-2", runs=[TextRun(text="ООО Ромашка")]),
                    ParagraphBlock(id="2", runs=[TextRun(text="Оплата производится в разумный срок.")]),
                ],
            ),
        ],
    )

    captured_chunks: list[list[tuple[int, str]]] = []

    def _capture_chunk(chunk):
        captured_chunks.append(chunk)
        return None

    monkeypatch.setattr(analyzer, "_request_chunk", _capture_chunk)

    issues = analyzer.analyze(document)

    assert issues == []
    assert captured_chunks == [
        [
            (2, "Поставщик обязан поставить товар."),
            (4, "Оплата производится в разумный срок."),
        ]
    ]


def test_gemini_analyzer_splits_large_document_into_sequential_chunks(monkeypatch) -> None:
    analyzer = GeminiContractIssueAnalyzer()
    analyzer._api_key = "test-key"
    analyzer._max_characters_per_request = 40

    document = build_contract_analysis_document(
        filename="contract.docx",
        source_format="docx",
        text="",
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(id="1", runs=[TextRun(text="Первый абзац договора.")]),
                    ParagraphBlock(id="2", runs=[TextRun(text="Второй абзац договора с деталями.")]),
                    ParagraphBlock(id="3", runs=[TextRun(text="Третий абзац договора.")]),
                ],
            )
        ],
    )

    captured_chunks: list[list[tuple[int, str]]] = []

    def _capture_chunk(chunk):
        captured_chunks.append(chunk)
        return None

    monkeypatch.setattr(analyzer, "_request_chunk", _capture_chunk)

    issues = analyzer.analyze(document)

    assert issues == []
    assert captured_chunks == [
        [(1, "Первый абзац договора.")],
        [(2, "Второй абзац договора с деталями.")],
        [(3, "Третий абзац договора.")],
    ]
