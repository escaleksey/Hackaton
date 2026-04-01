from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.domain.entities.document import DocumentLayout, DocumentPage


@dataclass(slots=True)
class ContractDraft:
    filename: str
    original_text: str
    source_format: str = "txt"
    corrected_text: str | None = None
    original_pages: list[DocumentPage] = field(default_factory=list)
    corrected_pages: list[DocumentPage] = field(default_factory=list)
    document_layout: DocumentLayout | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_text(self) -> str:
        return self.corrected_text if self.corrected_text is not None else self.original_text

    @property
    def current_pages(self) -> list[DocumentPage]:
        return self.corrected_pages or self.original_pages
