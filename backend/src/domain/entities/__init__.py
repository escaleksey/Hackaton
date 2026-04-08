"""Domain entities."""

from src.domain.entities.analysis_warning import ContractAnalysisWarning
from src.domain.entities.contract import ContractDraft
from src.domain.entities.document import (
    DocumentLayout,
    DocumentPage,
    ParagraphBlock,
    TextRun,
)
from src.domain.entities.issue import ContractIssue
from src.domain.entities.legal_analysis import (
    CorrectionPatch,
    DocumentStructure,
    DocumentStructureNode,
    LegalEntityMention,
    ObligationFact,
    TemporalFact,
)

__all__ = [
    "ContractAnalysisWarning",
    "ContractDraft",
    "ContractIssue",
    "CorrectionPatch",
    "DocumentLayout",
    "DocumentPage",
    "DocumentStructure",
    "DocumentStructureNode",
    "LegalEntityMention",
    "ObligationFact",
    "ParagraphBlock",
    "TemporalFact",
    "TextRun",
]
