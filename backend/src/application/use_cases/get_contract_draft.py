from uuid import UUID

from src.application.dto.contract_draft_result import ContractDraftResult
from src.application.use_cases.common import ContractNotFoundError, to_result
from src.domain.repositories.contract_repository import ContractRepository


class GetContractDraftUseCase:
    def __init__(self, repository: ContractRepository) -> None:
        self._repository = repository

    def execute(self, contract_id: UUID) -> ContractDraftResult:
        contract = self._repository.get_by_id(contract_id)
        if contract is None:
            raise ContractNotFoundError(f"Contract '{contract_id}' was not found.")
        return to_result(contract)
