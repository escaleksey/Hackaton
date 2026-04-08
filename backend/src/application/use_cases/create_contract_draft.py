from src.application.dto.contract_draft_result import ContractDraftResult
from src.application.services.document_processor import ContractDocumentProcessor
from src.application.services.legal_ai_pipeline import LegalAiPipeline
from src.application.use_cases.common import to_result
from src.domain.entities.contract import ContractDraft
from src.domain.repositories.contract_repository import ContractRepository


class CreateContractDraftUseCase:
    def __init__(
        self,
        repository: ContractRepository,
        document_processor: ContractDocumentProcessor,
        legal_ai_pipeline: LegalAiPipeline,
    ) -> None:
        self._repository = repository
        self._document_processor = document_processor
        self._legal_ai_pipeline = legal_ai_pipeline

    def execute(
        self,
        filename: str,
        *,
        text: str | None = None,
        file_bytes: bytes | None = None,
    ) -> ContractDraftResult:
        parsed_document = self._document_processor.parse(filename, text=text, file_bytes=file_bytes)
        analysis_result = self._legal_ai_pipeline.analyze(parsed_document)
        issues = analysis_result.issues
        annotated_pages = self._document_processor.annotate_pages(parsed_document.pages, issues)
        annotated_download = self._document_processor.build_annotated_source_download(
            filename=parsed_document.filename,
            source_format=parsed_document.source_format,
            file_bytes=parsed_document.source_file_bytes,
            issues=issues,
        )
        contract = ContractDraft(
            filename=parsed_document.filename,
            source_format=parsed_document.source_format,
            original_text=parsed_document.text,
            corrected_text=analysis_result.corrected_text or parsed_document.text,
            original_pages=parsed_document.pages,
            corrected_pages=annotated_pages,
            document_layout=parsed_document.document_layout,
            issues=issues,
            warnings=analysis_result.warnings,
            source_file_bytes=parsed_document.source_file_bytes,
            annotated_file_bytes=(
                annotated_download.content if annotated_download is not None else None
            ),
        )
        saved_contract = self._repository.save(contract)
        return to_result(saved_contract)
