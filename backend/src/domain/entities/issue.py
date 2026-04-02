from dataclasses import dataclass


@dataclass(slots=True)
class ContractIssue:
    paragraph_index: int
    fragment: str
    type: str
    severity: str
    explanation: str
    suggestion: str
    confidence: str = "medium"
