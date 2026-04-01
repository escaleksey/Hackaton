from src.application.dto.contract_draft_result import ContractDraftResult
from src.application.services.document_processor import ContractDocumentProcessor
from src.application.use_cases.common import to_result
from src.domain.entities.contract import ContractDraft
from src.domain.repositories.contract_repository import ContractRepository


class CreateContractDraftUseCase:
    def __init__(
        self,
        repository: ContractRepository,
        document_processor: ContractDocumentProcessor,
    ) -> None:
        self._repository = repository
        self._document_processor = document_processor

    def execute(
        self,
        filename: str,
        *,
        text: str | None = None,
        file_bytes: bytes | None = None,
    ) -> ContractDraftResult:
        parsed_document = self._document_processor.parse(filename, text=text, file_bytes=file_bytes)
        contract = ContractDraft(
            filename=parsed_document.filename,
            source_format=parsed_document.source_format,
            original_text=parsed_document.text,
            corrected_text=parsed_document.text,
            original_pages=parsed_document.pages,
            corrected_pages=parsed_document.pages,
            document_layout=parsed_document.document_layout,
        )
        saved_contract = self._repository.save(contract)
        return to_result(saved_contract)
