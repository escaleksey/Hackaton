from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class DocumentStructureNode:
    paragraph_index: int
    page_number: int
    block_id: str
    text: str
    node_type: str
    heading_level: int = 0
    heading_path: tuple[str, ...] = ()


@dataclass(slots=True)
class DocumentStructure:
    nodes: list[DocumentStructureNode] = field(default_factory=list)


@dataclass(slots=True)
class LegalEntityMention:
    paragraph_index: int
    page_number: int
    value: str
    entity_type: str
    canonical_value: str


@dataclass(slots=True)
class TemporalFact:
    paragraph_index: int
    page_number: int
    fragment: str
    semantic_label: str
    value: datetime
    heading_path: tuple[str, ...] = ()


@dataclass(slots=True)
class ObligationFact:
    paragraph_index: int
    page_number: int
    subject_term: str
    action_text: str
    recipient_term: str | None = None
    modality: str | None = None
    heading_path: tuple[str, ...] = ()


@dataclass(slots=True)
class CorrectionPatch:
    paragraph_index: int
    target_text: str
    replacement_text: str
    issue_type: str
    reason: str
