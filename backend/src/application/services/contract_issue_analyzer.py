from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.analysis_warning import ContractAnalysisWarning
from src.domain.entities.document import DocumentPage, enumerate_document_blocks
from src.domain.entities.issue import ContractIssue


@dataclass(slots=True)
class AnalyzableParagraph:
    paragraph_index: int
    page_number: int
    block_id: str
    text: str


@dataclass(slots=True)
class ContractAnalysisDocument:
    filename: str
    source_format: str
    text: str
    pages: list[DocumentPage]
    paragraphs: list[AnalyzableParagraph]


@dataclass(slots=True)
class ContractAnalysisResult:
    issues: list[ContractIssue]
    warnings: list[ContractAnalysisWarning]


class ContractIssueAnalyzer(ABC):
    def analyze(self, document: ContractAnalysisDocument) -> list[ContractIssue]:
        return self.analyze_result(document).issues

    @abstractmethod
    def analyze_result(self, document: ContractAnalysisDocument) -> ContractAnalysisResult:
        raise NotImplementedError


def build_contract_analysis_document(
    *,
    filename: str,
    source_format: str,
    text: str,
    pages: list[DocumentPage],
) -> ContractAnalysisDocument:
    return ContractAnalysisDocument(
        filename=filename,
        source_format=source_format,
        text=text,
        pages=pages,
        paragraphs=[
            AnalyzableParagraph(
                paragraph_index=paragraph_index,
                page_number=page_number,
                block_id=block.id,
                text=block.text,
            )
            for paragraph_index, page_number, block in enumerate_document_blocks(pages)
        ],
    )
