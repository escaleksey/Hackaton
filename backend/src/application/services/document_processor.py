from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.contract import ContractDraft
from src.domain.entities.document import DocumentLayout, DocumentPage
from src.domain.entities.issue import ContractIssue


@dataclass(slots=True)
class ParsedContractDocument:
    filename: str
    source_format: str
    text: str
    pages: list[DocumentPage]
    document_layout: DocumentLayout | None = None
    source_file_bytes: bytes | None = None


@dataclass(slots=True)
class DownloadableContractFile:
    filename: str
    content: bytes
    media_type: str


class ContractDocumentProcessor(ABC):
    @abstractmethod
    def parse(
        self,
        filename: str,
        *,
        file_bytes: bytes | None = None,
        text: str | None = None,
    ) -> ParsedContractDocument:
        raise NotImplementedError

    @abstractmethod
    def build_download(self, contract: ContractDraft) -> DownloadableContractFile:
        raise NotImplementedError

    @abstractmethod
    def annotate_pages(
        self,
        pages: list[DocumentPage],
        issues: list[ContractIssue],
    ) -> list[DocumentPage]:
        raise NotImplementedError

    @abstractmethod
    def build_annotated_source_download(
        self,
        *,
        filename: str,
        source_format: str,
        file_bytes: bytes | None,
        issues: list[ContractIssue],
    ) -> DownloadableContractFile | None:
        raise NotImplementedError
