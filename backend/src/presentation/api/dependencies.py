from functools import lru_cache

from src.application.services.contract_issue_analyzer import ContractIssueAnalyzer
from src.application.services.document_processor import ContractDocumentProcessor
from src.application.use_cases.create_contract_draft import CreateContractDraftUseCase
from src.application.use_cases.download_contract import DownloadContractUseCase
from src.application.use_cases.get_contract_draft import GetContractDraftUseCase
from src.application.use_cases.update_contract_text import UpdateContractTextUseCase
from src.infrastructure.repositories.in_memory_contract_repository import (
    InMemoryContractRepository,
)
from src.infrastructure.services.contract_issue_analyzer import (
    CompositeContractIssueAnalyzer,
    OpenAIContractIssueAnalyzer,
    RuleBasedContractIssueAnalyzer,
)
from src.infrastructure.services.python_docx_document_processor import (
    PythonDocxDocumentProcessor,
)


@lru_cache(maxsize=1)
def get_contract_repository() -> InMemoryContractRepository:
    return InMemoryContractRepository()


@lru_cache(maxsize=1)
def get_document_processor() -> ContractDocumentProcessor:
    return PythonDocxDocumentProcessor()


@lru_cache(maxsize=1)
def get_contract_issue_analyzer() -> ContractIssueAnalyzer:
    return CompositeContractIssueAnalyzer(
        [
            RuleBasedContractIssueAnalyzer(),
            OpenAIContractIssueAnalyzer(),
        ]
    )


def get_create_contract_draft_use_case() -> CreateContractDraftUseCase:
    return CreateContractDraftUseCase(
        get_contract_repository(),
        get_document_processor(),
        get_contract_issue_analyzer(),
    )


def get_get_contract_draft_use_case() -> GetContractDraftUseCase:
    return GetContractDraftUseCase(get_contract_repository())


def get_update_contract_text_use_case() -> UpdateContractTextUseCase:
    return UpdateContractTextUseCase(get_contract_repository())


def get_download_contract_use_case() -> DownloadContractUseCase:
    return DownloadContractUseCase(get_contract_repository(), get_document_processor())
