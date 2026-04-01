from dataclasses import dataclass
from uuid import UUID

from src.application.services.document_processor import ContractDocumentProcessor
from src.application.use_cases.common import ContractNotFoundError
from src.domain.repositories.contract_repository import ContractRepository


@dataclass(slots=True)
class DownloadContractResult:
    filename: str
    content: bytes
    media_type: str


class DownloadContractUseCase:
    def __init__(
        self,
        repository: ContractRepository,
        document_processor: ContractDocumentProcessor,
    ) -> None:
        self._repository = repository
        self._document_processor = document_processor

    def execute(self, contract_id: UUID) -> DownloadContractResult:
        contract = self._repository.get_by_id(contract_id)
        if contract is None:
            raise ContractNotFoundError(f"Contract '{contract_id}' was not found.")

        downloadable_file = self._document_processor.build_download(contract)
        return DownloadContractResult(
            filename=downloadable_file.filename,
            content=downloadable_file.content,
            media_type=downloadable_file.media_type,
        )
