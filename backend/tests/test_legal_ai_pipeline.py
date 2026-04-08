from src.domain.entities.document import DocumentPage, ParagraphBlock, TextRun
from src.infrastructure.services.legal_ai_pipeline import SemanticLegalAiPipeline
from src.infrastructure.services.contract_issue_analyzer import GeminiContractIssueAnalyzer


def test_semantic_pipeline_detects_date_conflict_and_builds_patch(monkeypatch) -> None:
    pipeline = SemanticLegalAiPipeline()

    def _stub_llm_analyze_result(self, _document, **_kwargs):
        from src.application.services.contract_issue_analyzer import ContractAnalysisResult

        return ContractAnalysisResult(issues=[], warnings=[])

    monkeypatch.setattr(
        GeminiContractIssueAnalyzer,
        "analyze_with_context",
        _stub_llm_analyze_result,
    )

    parsed_document = pipeline_input(
        [
            '\u0433. \u041c\u043e\u0441\u043a\u0432\u0430\n\u00ab25\u00bb \u043c\u0430\u0440\u0442\u0430 2026 \u0433.',
            (
                '\u041a\u043b\u0438\u0435\u043d\u0442 \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442 \u0437\u0430\u044f\u0432\u043a\u0443, '
                '\u0430 \u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a \u043f\u043e\u0434\u043f\u0438\u0441\u044b\u0432\u0430\u0435\u0442 '
                '\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043d\u0435 \u043f\u043e\u0437\u0434\u043d\u0435\u0435 01.03.2026.'
            ),
        ]
    )

    result = pipeline.analyze(parsed_document)

    assert any(issue.type == "DEADLINE_CONFLICT" for issue in result.issues)
    term_issue = next(issue for issue in result.issues if issue.type == "TERM_MISUSE")
    assert term_issue.replacement == "\u041a\u043b\u0438\u0435\u043d\u0442"
    assert result.corrected_text is not None
    assert "\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a" not in result.corrected_text


def test_semantic_pipeline_detects_end_date_before_signing(monkeypatch) -> None:
    pipeline = SemanticLegalAiPipeline()

    def _stub_llm_analyze_result(self, _document, **_kwargs):
        from src.application.services.contract_issue_analyzer import ContractAnalysisResult

        return ContractAnalysisResult(issues=[], warnings=[])

    monkeypatch.setattr(
        GeminiContractIssueAnalyzer,
        "analyze_with_context",
        _stub_llm_analyze_result,
    )

    parsed_document = pipeline_input(
        [
            '\u0433. \u041c\u043e\u0441\u043a\u0432\u0430\n\u00ab25\u00bb \u043c\u0430\u0440\u0442\u0430 2026 \u0433.',
            (
                '\u041d\u0430\u0441\u0442\u043e\u044f\u0449\u0438\u0439 \u0434\u043e\u0433\u043e\u0432\u043e\u0440 '
                '\u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0434\u043e 31 \u0434\u0435\u043a\u0430\u0431\u0440\u044f 2025 \u0433\u043e\u0434\u0430.'
            ),
        ]
    )

    result = pipeline.analyze(parsed_document)

    conflict = next(issue for issue in result.issues if issue.type == "DATE_CONFLICT")
    assert conflict.replacement is not None


def test_semantic_pipeline_detects_logical_actor_conflict(monkeypatch) -> None:
    pipeline = SemanticLegalAiPipeline()

    def _stub_llm_analyze_result(self, _document, **_kwargs):
        from src.application.services.contract_issue_analyzer import ContractAnalysisResult

        return ContractAnalysisResult(issues=[], warnings=[])

    monkeypatch.setattr(
        GeminiContractIssueAnalyzer,
        "analyze_with_context",
        _stub_llm_analyze_result,
    )

    parsed_document = pipeline_input(
        [
            (
                '\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a '
                '\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0443\u0441\u043b\u0443\u0433\u0438, '
                '\u0430 \u041f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a \u043e\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0435\u0442 \u0438\u0445.'
            ),
        ]
    )

    result = pipeline.analyze(parsed_document)

    assert any(issue.type in {"WRONG_ACTOR", "INCONSISTENCY"} for issue in result.issues)


def test_semantic_pipeline_detects_generic_party_direction_conflict(monkeypatch) -> None:
    pipeline = SemanticLegalAiPipeline()

    def _stub_llm_with_context(self, _document, **_kwargs):
        from src.application.services.contract_issue_analyzer import ContractAnalysisResult

        return ContractAnalysisResult(issues=[], warnings=[])

    monkeypatch.setattr(
        GeminiContractIssueAnalyzer,
        "analyze_with_context",
        _stub_llm_with_context,
    )

    parsed_document = pipeline_input(
        [
            (
                'ООО "Ромашка" (далее - "Арендодатель") и '
                'ООО "Лютик" (далее - "Арендатор") заключили договор.'
            ),
            "Арендодатель обязуется передать помещение Арендатору по акту приема-передачи.",
            "Арендатор обязуется передать Арендодателю помещение в день подписания договора.",
        ]
    )

    result = pipeline.analyze(parsed_document)

    assert any(issue.type == "INCONSISTENCY" for issue in result.issues)


def pipeline_input(paragraphs: list[str]):
    from src.application.services.document_processor import ParsedContractDocument

    return ParsedContractDocument(
        filename="contract.docx",
        source_format="docx",
        text="\n".join(paragraphs),
        pages=[
            DocumentPage(
                number=1,
                blocks=[
                    ParagraphBlock(id=str(index), runs=[TextRun(text=text)])
                    for index, text in enumerate(paragraphs, start=1)
                ],
            )
        ],
        source_file_bytes=None,
    )
