from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.contract import ContractDraft


class ContractRepository(ABC):
    @abstractmethod
    def save(self, contract: ContractDraft) -> ContractDraft:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, contract_id: UUID) -> ContractDraft | None:
        raise NotImplementedError
