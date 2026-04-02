from uuid import UUID

from src.application.dto.contract_draft_result import ContractDraftResult
from src.application.use_cases.common import ContractNotFoundError, to_result
from src.domain.entities.document import (
    DocumentPage,
    flatten_document_pages,
    normalize_document_pages,
)
from src.domain.repositories.contract_repository import ContractRepository


class UpdateContractTextUseCase:
    def __init__(self, repository: ContractRepository) -> None:
        self._repository = repository

    def execute(
        self,
        contract_id: UUID,
        *,
        corrected_text: str | None = None,
        corrected_pages: list[DocumentPage] | None = None,
    ) -> ContractDraftResult:
        contract = self._repository.get_by_id(contract_id)
        if contract is None:
            raise ContractNotFoundError(f"Contract '{contract_id}' was not found.")

        if contract.source_format == "docx":
            if not corrected_pages:
                raise ValueError("Для DOCX-документа передайте исправленные страницы.")

            normalized_pages = normalize_document_pages(corrected_pages)
            corrected_document_text = flatten_document_pages(normalized_pages)
            if not corrected_document_text.strip():
                raise ValueError("Corrected contract text must not be empty.")

            contract.corrected_pages = normalized_pages
            contract.corrected_text = corrected_document_text
            contract.annotated_file_bytes = None
        else:
            if corrected_text is None or not corrected_text.strip():
                raise ValueError("Corrected contract text must not be empty.")

            contract.corrected_text = corrected_text
        saved_contract = self._repository.save(contract)
        return to_result(saved_contract)
