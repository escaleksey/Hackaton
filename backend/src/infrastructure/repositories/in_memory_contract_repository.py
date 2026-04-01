from uuid import UUID

from src.domain.entities.contract import ContractDraft
from src.domain.repositories.contract_repository import ContractRepository


class InMemoryContractRepository(ContractRepository):
    def __init__(self) -> None:
        self._storage: dict[UUID, ContractDraft] = {}

    def save(self, contract: ContractDraft) -> ContractDraft:
        self._storage[contract.id] = contract
        return contract

    def get_by_id(self, contract_id: UUID) -> ContractDraft | None:
        return self._storage.get(contract_id)
