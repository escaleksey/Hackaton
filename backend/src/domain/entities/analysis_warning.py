from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ContractAnalysisWarning:
    code: str
    message: str
