from src.application.dto.contract_draft_result import ContractDraftResult
from src.domain.entities.contract import ContractDraft


class ContractNotFoundError(Exception):
    """Raised when a contract draft does not exist."""


def to_result(contract: ContractDraft) -> ContractDraftResult:
    return ContractDraftResult(
        id=contract.id,
        filename=contract.filename,
        source_format=contract.source_format,
        original_text=contract.original_text,
        corrected_text=contract.current_text,
        original_pages=contract.original_pages,
        corrected_pages=contract.current_pages,
        document_layout=contract.document_layout,
        issues=contract.issues,
        warnings=contract.warnings,
        created_at=contract.created_at,
    )
