from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.application.services.document_processor import ParsedContractDocument
from src.domain.entities.analysis_warning import ContractAnalysisWarning
from src.domain.entities.issue import ContractIssue
from src.domain.entities.legal_analysis import (
    CorrectionPatch,
    DocumentStructure,
    LegalEntityMention,
    ObligationFact,
    TemporalFact,
)


@dataclass(slots=True)
class SemanticAnalysisResult:
    issues: list[ContractIssue]
    warnings: list[ContractAnalysisWarning] = field(default_factory=list)
    corrected_text: str | None = None
    patches: list[CorrectionPatch] = field(default_factory=list)
    structure: DocumentStructure | None = None
    entities: list[LegalEntityMention] = field(default_factory=list)
    temporal_facts: list[TemporalFact] = field(default_factory=list)
    obligation_facts: list[ObligationFact] = field(default_factory=list)


class LegalAiPipeline(ABC):
    @abstractmethod
    def analyze(self, document: ParsedContractDocument) -> SemanticAnalysisResult:
        raise NotImplementedError
