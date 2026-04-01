from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.document import DocumentLayout, DocumentPage


@dataclass(slots=True)
class ContractDraftResult:
    id: UUID
    filename: str
    source_format: str
    original_text: str
    corrected_text: str
    original_pages: list[DocumentPage]
    corrected_pages: list[DocumentPage]
    document_layout: DocumentLayout | None
    created_at: datetime
