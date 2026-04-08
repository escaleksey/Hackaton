import re
from dataclasses import dataclass
from datetime import datetime

from src.application.services.contract_issue_analyzer import build_contract_analysis_document
from src.application.services.document_processor import ParsedContractDocument
from src.application.services.legal_ai_pipeline import LegalAiPipeline, SemanticAnalysisResult
from src.domain.entities.issue import ContractIssue
from src.domain.entities.legal_analysis import (
    CorrectionPatch,
    DocumentStructure,
    DocumentStructureNode,
    LegalEntityMention,
    ObligationFact,
    TemporalFact,
)
from src.infrastructure.services.contract_issue_analyzer import (
    GeminiContractIssueAnalyzer,
    RuleBasedContractIssueAnalyzer,
)


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _normalize_casefold(value: str) -> str:
    return _normalize_space(value).casefold()


@dataclass(slots=True)
class SemanticContext:
    analysis_document: object
    structure: DocumentStructure
    entities: list[LegalEntityMention]
    temporal_facts: list[TemporalFact]
    obligation_facts: list[ObligationFact]
    signing_fact: TemporalFact | None = None


class DocumentStructureLayer:
    _numbered_heading_pattern = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+(.+)$")

    def build(self, analysis_document) -> DocumentStructure:
        nodes: list[DocumentStructureNode] = []
        heading_stack: list[str] = []

        for paragraph in analysis_document.paragraphs:
            text = _normalize_space(paragraph.text.strip())
            if not text:
                continue

            node_type = "paragraph"
            heading_level = 0
            heading_match = self._numbered_heading_pattern.match(text)

            if heading_match and len(text) <= 180:
                node_type = "heading"
                heading_level = heading_match.group(1).count(".") + 1
                heading_stack = heading_stack[: heading_level - 1]
                heading_stack.append(text)
            elif text.isupper() and len(text) <= 120:
                node_type = "heading"
                heading_level = 1
                heading_stack = [text]

            nodes.append(
                DocumentStructureNode(
                    paragraph_index=paragraph.paragraph_index,
                    page_number=paragraph.page_number,
                    block_id=paragraph.block_id,
                    text=text,
                    node_type=node_type,
                    heading_level=heading_level,
                    heading_path=tuple(heading_stack),
                )
            )

        return DocumentStructure(nodes=nodes)


class LegalEntityExtractionLayer:
    _numeric_date_pattern = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{4})\b")
    _textual_date_pattern = re.compile(
        r'(?<!\d)[\u00ab"]?(\d{1,2})[\u00bb"]?\s+'
        r'('
        r'\u044f\u043d\u0432\u0430\u0440\u044f|'
        r'\u0444\u0435\u0432\u0440\u0430\u043b\u044f|'
        r'\u043c\u0430\u0440\u0442\u0430|'
        r'\u0430\u043f\u0440\u0435\u043b\u044f|'
        r'\u043c\u0430\u044f|'
        r'\u0438\u044e\u043d\u044f|'
        r'\u0438\u044e\u043b\u044f|'
        r'\u0430\u0432\u0433\u0443\u0441\u0442\u0430|'
        r'\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f|'
        r'\u043e\u043a\u0442\u044f\u0431\u0440\u044f|'
        r'\u043d\u043e\u044f\u0431\u0440\u044f|'
        r'\u0434\u0435\u043a\u0430\u0431\u0440\u044f'
        r')\s+(\d{4})\s+\u0433(?:\u043e\u0434\u0430|\.?)?\b',
        re.IGNORECASE,
    )
    _month_numbers = {
        "\u044f\u043d\u0432\u0430\u0440\u044f": 1,
        "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2,
        "\u043c\u0430\u0440\u0442\u0430": 3,
        "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
        "\u043c\u0430\u044f": 5,
        "\u0438\u044e\u043d\u044f": 6,
        "\u0438\u044e\u043b\u044f": 7,
        "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
        "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9,
        "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10,
        "\u043d\u043e\u044f\u0431\u0440\u044f": 11,
        "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
    }
    _role_aliases = {
        "client": (
            "\u043a\u043b\u0438\u0435\u043d\u0442",
            "\u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a",
            "\u043f\u043e\u043a\u0443\u043f\u0430\u0442\u0435\u043b\u044c",
        ),
        "provider": (
            "\u043f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a",
            "\u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c",
            "\u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a",
            "\u043f\u0440\u043e\u0434\u0430\u0432\u0435\u0446",
        ),
    }
    _company_pattern = re.compile(r'\b(?:\u041e\u041e\u041e|\u0410\u041e|\u041f\u0410\u041e|\u0418\u041f)\s*[«"]([^»"]+)[»"]', re.IGNORECASE)
    _fio_pattern = re.compile(
        r"\b[\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ [\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ [\u0410-\u042f\u0401][\u0430-\u044f\u0451]+\b"
    )
    _party_definition_patterns = (
        re.compile(
            r"(?P<entity>(?:\u041e\u041e\u041e|\u0410\u041e|\u041f\u0410\u041e|\u0418\u041f)[^()]{1,160})\(\s*(?:\u0434\u0430\u043b\u0435\u0435|\u0432 \u0434\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0435\u043c)\s*[-–—]?\s*[«\"](?P<alias>[^»\"\n]{2,80})[»\"]\s*\)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<entity>[^.:\n]{3,160}?)\s*,?\s*(?:\u0438\u043c\u0435\u043d\u0443\u0435\u043c(?:\u043e\u0435|\u044b\u0439|\u0430\u044f)?|(?:\u0438\u043c\u0435\u043d\u0443\u0435\u043c(?:\u044b\u0435)?)\s+\u0432 \u0434\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0435\u043c)\s*[«\"](?P<alias>[^»\"\n]{2,80})[»\"]",
            re.IGNORECASE,
        ),
    )
    _defined_term_patterns = (
        re.compile(
            r"[«\"](?P<term>[^»\"\n]{2,80})[»\"]\s*\(\u0434\u0430\u043b\u0435\u0435\s*[-–—]?\s*(?P<alias>[^)]+)\)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<term>[A-Z\u0410-\u042f\u0401][A-Za-z\u0410-\u042f\u0401\u0430-\u044f\u0451\s-]{1,80})\s*\(\u0434\u0430\u043b\u0435\u0435\s*[-–—]?\s*[«\"](?P<alias>[^»\"\n]{2,80})[»\"]\)",
            re.IGNORECASE,
        ),
        re.compile(
            r"[«\"](?P<term>[^»\"\n]{2,80})[»\"]",
            re.IGNORECASE,
        ),
    )
    _semantic_date_markers = {
        "signing_date": (
            "\u0434\u0430\u0442\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f",
            "\u0434\u043e\u0433\u043e\u0432\u043e\u0440",
            "\u0437\u0430\u043a\u043b\u044e\u0447\u0438\u043b\u0438",
        ),
        "deadline": (
            "\u043d\u0435 \u043f\u043e\u0437\u0434\u043d\u0435\u0435",
            "\u0432 \u0441\u0440\u043e\u043a \u0434\u043e",
            "\u0434\u043e ",
        ),
        "term_end": (
            "\u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0434\u043e",
            "\u0441\u0440\u043e\u043a \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f",
            "\u0438\u0441\u0442\u0435\u043a\u0430\u0435\u0442",
        ),
        "registry_document": (
            "\u0435\u0433\u0440\u043d",
            "\u0432\u044b\u043f\u0438\u0441\u043a\u0430 \u0438\u0437",
        ),
    }
    _city_markers = (
        "\u0433. ",
        "\u0433\u043e\u0440\u043e\u0434 ",
        "\u043c\u043e\u0441\u043a\u0432\u0430",
        "\u0435\u043a\u0430\u0442\u0435\u0440\u0438\u043d\u0431\u0443\u0440\u0433",
        "\u0441\u0430\u043d\u043a\u0442-\u043f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433",
    )

    def extract(
        self,
        analysis_document,
        structure: DocumentStructure,
    ) -> tuple[list[LegalEntityMention], list[TemporalFact]]:
        entities: list[LegalEntityMention] = []
        temporal_facts: list[TemporalFact] = []
        heading_by_paragraph = {
            node.paragraph_index: node.heading_path for node in structure.nodes
        }

        for paragraph in analysis_document.paragraphs:
            text = _normalize_space(paragraph.text.strip())
            if not text:
                continue

            lowered = text.casefold()
            for principal_value, alias_value in self._extract_party_definitions(text):
                canonical = _normalize_casefold(principal_value)
                entities.append(
                    LegalEntityMention(
                        paragraph_index=paragraph.paragraph_index,
                        page_number=paragraph.page_number,
                        value=principal_value,
                        entity_type="party_principal",
                        canonical_value=canonical,
                    )
                )
                entities.append(
                    LegalEntityMention(
                        paragraph_index=paragraph.paragraph_index,
                        page_number=paragraph.page_number,
                        value=alias_value,
                        entity_type="party_alias",
                        canonical_value=canonical,
                    )
                )

            for canonical_role, aliases in self._role_aliases.items():
                for alias in aliases:
                    if alias in lowered:
                        entities.append(
                            LegalEntityMention(
                                paragraph_index=paragraph.paragraph_index,
                                page_number=paragraph.page_number,
                                value=alias.capitalize(),
                                entity_type="party_role",
                                canonical_value=canonical_role,
                            )
                        )
                        for company_match in self._company_pattern.finditer(text):
                            company_value = company_match.group(0).strip()
                            entities.append(
                                LegalEntityMention(
                                    paragraph_index=paragraph.paragraph_index,
                                    page_number=paragraph.page_number,
                                    value=company_value,
                                    entity_type="counterparty_name",
                                    canonical_value=f"{canonical_role}:{_normalize_casefold(company_value)}",
                                )
                            )
                        for fio_match in self._fio_pattern.finditer(text):
                            fio_value = fio_match.group(0).strip()
                            entities.append(
                                LegalEntityMention(
                                    paragraph_index=paragraph.paragraph_index,
                                    page_number=paragraph.page_number,
                                    value=fio_value,
                                    entity_type="counterparty_person",
                                    canonical_value=f"{canonical_role}:{_normalize_casefold(fio_value)}",
                                )
                            )

            for term_value, normalized_value in self._extract_defined_terms(text):
                entities.append(
                    LegalEntityMention(
                        paragraph_index=paragraph.paragraph_index,
                        page_number=paragraph.page_number,
                        value=term_value,
                        entity_type="defined_term",
                        canonical_value=normalized_value,
                    )
                )

            for fragment, value, start, end in self._extract_dates(text):
                temporal_facts.append(
                    TemporalFact(
                        paragraph_index=paragraph.paragraph_index,
                        page_number=paragraph.page_number,
                        fragment=fragment,
                        value=value,
                        semantic_label=self._classify_date_semantics(
                            text,
                            lowered,
                            paragraph.paragraph_index,
                            start,
                            end,
                        ),
                        heading_path=heading_by_paragraph.get(paragraph.paragraph_index, ()),
                    )
                )

        return entities, temporal_facts

    def _extract_party_definitions(self, text: str) -> list[tuple[str, str]]:
        definitions: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for pattern in self._party_definition_patterns:
            for match in pattern.finditer(text):
                principal_value = _normalize_space(match.group("entity").strip(" ,.;:"))
                alias_value = _normalize_space(match.group("alias").strip(" ,.;:«»\""))
                if len(principal_value) < 3 or len(alias_value) < 2:
                    continue
                key = (_normalize_casefold(principal_value), _normalize_casefold(alias_value))
                if key in seen:
                    continue
                seen.add(key)
                definitions.append((principal_value, alias_value))

        return definitions

    def _extract_defined_terms(self, text: str) -> list[tuple[str, str]]:
        extracted: list[tuple[str, str]] = []
        seen: set[str] = set()

        for pattern in self._defined_term_patterns:
            for match in pattern.finditer(text):
                term = _normalize_space(match.group("term").strip(" ,.;:")) if "term" in match.groupdict() else ""
                alias = match.groupdict().get("alias")
                candidates = [term]
                if alias:
                    candidates.append(_normalize_space(alias.strip(" ,.;:«»\"")))

                for candidate in candidates:
                    if len(candidate) < 2:
                        continue
                    normalized = _normalize_casefold(candidate)
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    extracted.append((candidate, normalized))

        return extracted

    def _extract_dates(self, text: str) -> list[tuple[str, datetime, int, int]]:
        results: list[tuple[str, datetime, int, int]] = []

        for match in self._numeric_date_pattern.finditer(text):
            day, month, year = map(int, match.groups())
            try:
                results.append((match.group(0), datetime(year, month, day), match.start(), match.end()))
            except ValueError:
                continue

        for match in self._textual_date_pattern.finditer(text):
            day = int(match.group(1))
            month = self._month_numbers.get(match.group(2).casefold())
            year = int(match.group(3))
            if month is None:
                continue
            try:
                results.append((match.group(0), datetime(year, month, day), match.start(), match.end()))
            except ValueError:
                continue

        return sorted(results, key=lambda item: item[2])

    def _classify_date_semantics(
        self,
        text: str,
        lowered_text: str,
        paragraph_index: int,
        start: int,
        end: int,
    ) -> str:
        context_start = max(0, start - 48)
        context_end = min(len(text), end + 48)
        lowered_context = text[context_start:context_end].casefold()

        if any(marker in lowered_context for marker in self._semantic_date_markers["registry_document"]):
            return "registry_document"
        if any(marker in lowered_context for marker in self._semantic_date_markers["term_end"]):
            return "term_end"
        if any(marker in lowered_context for marker in self._semantic_date_markers["deadline"]):
            return "deadline"
        if paragraph_index <= 6 and any(
            marker in lowered_context for marker in self._semantic_date_markers["signing_date"]
        ):
            return "signing_date"
        if paragraph_index <= 3 and any(marker in lowered_text for marker in self._city_markers):
            return "signing_date"

        return "date_reference"


class ObligationExtractionLayer:
    _modality_markers = (
        "\u043e\u0431\u044f\u0437\u0443\u0435\u0442\u0441\u044f",
        "\u043e\u0431\u044f\u0437\u0430\u043d",
        "\u0434\u043e\u043b\u0436\u0435\u043d",
        "\u0432\u043f\u0440\u0430\u0432\u0435",
        "\u043c\u043e\u0436\u0435\u0442",
    )
    _action_verbs = (
        "\u043f\u0435\u0440\u0435\u0434\u0430\u0442\u044c",
        "\u043f\u0435\u0440\u0435\u0434\u0430\u0435\u0442",
        "\u043f\u0435\u0440\u0435\u0434\u0430\u0442\u044c",
        "\u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c",
        "\u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u0442",
        "\u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c",
        "\u043e\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0435\u0442",
        "\u043e\u043a\u0430\u0437\u0430\u0442\u044c",
        "\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442",
        "\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c",
        "\u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442",
        "\u0432\u043e\u0437\u0432\u0440\u0430\u0442\u0438\u0442\u044c",
        "\u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442",
        "\u043f\u0435\u0440\u0435\u0447\u0438\u0441\u043b\u0438\u0442\u044c",
        "\u0443\u043f\u043b\u0430\u0442\u0438\u0442\u044c",
        "\u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c",
        "\u043d\u0430\u043f\u0440\u0430\u0432\u0438\u0442\u044c",
    )

    def extract(
        self,
        analysis_document,
        structure: DocumentStructure,
        entities: list[LegalEntityMention],
    ) -> list[ObligationFact]:
        party_terms = self._collect_party_terms(entities)
        if not party_terms:
            return []

        heading_by_paragraph = {
            node.paragraph_index: node.heading_path for node in structure.nodes
        }
        obligation_facts: list[ObligationFact] = []

        for paragraph in analysis_document.paragraphs:
            text = _normalize_space(paragraph.text.strip())
            if not text:
                continue

            lowered = text.casefold()
            present_terms = [term for term in party_terms if _normalize_casefold(term) in lowered]
            if not present_terms:
                continue

            for subject_term in present_terms:
                subject_index = lowered.find(_normalize_casefold(subject_term))
                if subject_index < 0:
                    continue
                window = lowered[subject_index : min(len(lowered), subject_index + 220)]
                modality = next((marker for marker in self._modality_markers if marker in window), None)
                action = next((verb for verb in self._action_verbs if verb in window), None)
                if action is None:
                    continue
                recipient_term = next(
                    (
                        other_term
                        for other_term in present_terms
                        if other_term != subject_term
                        and _normalize_casefold(other_term) in window
                    ),
                    None,
                )
                fragment_end = min(len(text), subject_index + 220)
                obligation_facts.append(
                    ObligationFact(
                        paragraph_index=paragraph.paragraph_index,
                        page_number=paragraph.page_number,
                        subject_term=subject_term,
                        action_text=action,
                        recipient_term=recipient_term,
                        modality=modality,
                        heading_path=heading_by_paragraph.get(paragraph.paragraph_index, ()),
                    )
                )

        return self._deduplicate(obligation_facts)

    def _collect_party_terms(self, entities: list[LegalEntityMention]) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for entity in entities:
            if entity.entity_type not in {
                "party_alias",
                "party_role",
                "counterparty_name",
                "defined_term",
            }:
                continue
            normalized = _normalize_casefold(entity.value)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(entity.value)
        return terms

    def _deduplicate(self, obligations: list[ObligationFact]) -> list[ObligationFact]:
        unique: list[ObligationFact] = []
        seen: set[tuple[int, str, str, str | None]] = set()
        for obligation in obligations:
            key = (
                obligation.paragraph_index,
                _normalize_casefold(obligation.subject_term),
                _normalize_casefold(obligation.action_text),
                _normalize_casefold(obligation.recipient_term or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(obligation)
        return unique


class RuleEngineLayer:
    _preferred_role_labels = {
        "client": "\u041a\u043b\u0438\u0435\u043d\u0442",
        "provider": "\u041f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a",
    }

    def evaluate(self, context: SemanticContext) -> list[ContractIssue]:
        issues: list[ContractIssue] = []
        issues.extend(self._detect_term_misuse(context.entities))
        issues.extend(self._detect_counterparty_mismatches(context.entities))
        issues.extend(self._detect_temporal_conflicts(context.temporal_facts, context.signing_fact))
        issues.extend(self._detect_logical_conflicts(context.analysis_document, context.obligation_facts))
        return self._deduplicate(issues)

    def _detect_term_misuse(self, entities: list[LegalEntityMention]) -> list[ContractIssue]:
        issues: list[ContractIssue] = []
        grouped_aliases: dict[str, list[LegalEntityMention]] = {}

        for entity in entities:
            if entity.entity_type not in {"party_alias", "party_role"}:
                continue
            grouped_aliases.setdefault(entity.canonical_value, []).append(entity)

        for canonical_value, mentions in grouped_aliases.items():
            normalized_to_mentions: dict[str, list[LegalEntityMention]] = {}
            for mention in mentions:
                normalized_to_mentions.setdefault(_normalize_casefold(mention.value), []).append(mention)

            if len(normalized_to_mentions) <= 1:
                continue

            preferred_value = max(
                normalized_to_mentions.values(),
                key=lambda values: (len(values), -values[0].paragraph_index),
            )[0].value

            for normalized_value, values in normalized_to_mentions.items():
                sample = values[0]
                if normalized_value == _normalize_casefold(preferred_value):
                    continue
                issues.append(
                    ContractIssue(
                        paragraph_index=sample.paragraph_index,
                        fragment=sample.value,
                        type="TERM_MISUSE",
                        severity="medium",
                        confidence="high",
                        explanation="\u0414\u043b\u044f \u043e\u0434\u043d\u043e\u0439 \u0438 \u0442\u043e\u0439 \u0436\u0435 \u0441\u0443\u0449\u043d\u043e\u0441\u0442\u0438 \u0432 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0440\u0430\u0437\u043d\u044b\u0435 \u0442\u0435\u0440\u043c\u0438\u043d\u044b.",
                        suggestion="\u041e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043e\u0434\u043d\u043e \u043a\u043e\u043d\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043d\u043e\u0435 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u044d\u0442\u043e\u0439 \u0441\u0443\u0449\u043d\u043e\u0441\u0442\u0438 \u043f\u043e \u0432\u0441\u0435\u043c\u0443 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0443.",
                        replacement=preferred_value,
                    )
                )

        return issues

    def _detect_counterparty_mismatches(
        self,
        entities: list[LegalEntityMention],
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []
        grouped: dict[str, list[LegalEntityMention]] = {}

        for entity in entities:
            if entity.entity_type not in {"counterparty_name", "counterparty_person"}:
                continue
            role = entity.canonical_value.split(":", 1)[0]
            grouped.setdefault(f"{entity.entity_type}:{role}", []).append(entity)

        for group_key, mentions in grouped.items():
            normalized_to_mentions: dict[str, list[LegalEntityMention]] = {}
            for mention in mentions:
                normalized_to_mentions.setdefault(_normalize_casefold(mention.value), []).append(mention)

            if len(normalized_to_mentions) <= 1:
                continue

            preferred_value = max(
                normalized_to_mentions.values(),
                key=lambda values: (len(values), -values[0].paragraph_index),
            )[0].value

            for normalized_value, values in normalized_to_mentions.items():
                sample = values[0]
                if _normalize_casefold(sample.value) == _normalize_casefold(preferred_value):
                    continue
                issues.append(
                    ContractIssue(
                        paragraph_index=sample.paragraph_index,
                        fragment=sample.value,
                        type="ENTITY_MISMATCH",
                        severity="high",
                        confidence="medium",
                        explanation="\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442\u0430 \u0432 \u044d\u0442\u043e\u0439 \u0440\u043e\u043b\u0438 \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u0441 \u0434\u0440\u0443\u0433\u0438\u043c\u0438 \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\u043c\u0438 \u043f\u043e \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0443.",
                        suggestion="\u0423\u043d\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442\u0430 \u0432 \u044d\u0442\u043e\u0439 \u0440\u043e\u043b\u0438 \u043f\u043e \u0432\u0441\u0435\u043c\u0443 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0443.",
                        replacement=preferred_value,
                    )
                )

        return issues

    def _detect_temporal_conflicts(
        self,
        temporal_facts: list[TemporalFact],
        signing_fact: TemporalFact | None,
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        if signing_fact is not None:
            for fact in temporal_facts:
                if fact.semantic_label == "deadline" and fact.value < signing_fact.value:
                    issues.append(
                        ContractIssue(
                            paragraph_index=fact.paragraph_index,
                            fragment=fact.fragment,
                            type="DEADLINE_CONFLICT",
                            severity="high",
                            confidence="high",
                            explanation="\u0421\u0440\u043e\u043a \u0432 \u043f\u0443\u043d\u043a\u0442\u0435 \u043d\u0430\u0441\u0442\u0443\u043f\u0430\u0435\u0442 \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430.",
                            suggestion=f"\u0421\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u0434\u0435\u0434\u043b\u0430\u0439\u043d \u043d\u0430 \u0434\u0430\u0442\u0443 \u043f\u043e\u0437\u0436\u0435 {signing_fact.fragment}.",
                            replacement=self._format_like(signing_fact.value, fact.fragment),
                        )
                    )
                if fact.semantic_label == "term_end" and fact.value < signing_fact.value:
                    issues.append(
                        ContractIssue(
                            paragraph_index=fact.paragraph_index,
                            fragment=fact.fragment,
                            type="DATE_CONFLICT",
                            severity="high",
                            confidence="high",
                            explanation="\u0414\u0430\u0442\u0430 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u0440\u0430\u043d\u044c\u0448\u0435 \u0434\u0430\u0442\u044b \u0435\u0433\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f.",
                            suggestion=f"\u0423\u043a\u0430\u0437\u0430\u0442\u044c \u0434\u0430\u0442\u0443 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u043f\u043e\u0437\u0436\u0435 {signing_fact.fragment}.",
                            replacement=self._format_like(signing_fact.value, fact.fragment),
                        )
                    )
                if fact.semantic_label == "registry_document" and fact.value > signing_fact.value:
                    issues.append(
                        ContractIssue(
                            paragraph_index=fact.paragraph_index,
                            fragment=fact.fragment,
                            type="DATE_CONFLICT",
                            severity="medium",
                            confidence="medium",
                            explanation="\u0414\u0430\u0442\u0430 \u043f\u0440\u0430\u0432\u043e\u0443\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u044e\u0449\u0435\u0433\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u043f\u043e\u0437\u0436\u0435 \u0434\u0430\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f.",
                            suggestion="\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043b\u043e\u0433\u0438\u043a\u0443 \u0445\u0440\u043e\u043d\u043e\u043b\u043e\u0433\u0438\u0438 \u0434\u0430\u0442 \u0432 \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u0430\u0445.",
                        )
                    )

        term_end_facts = [fact for fact in temporal_facts if fact.semantic_label == "term_end"]
        unique_term_dates = {fact.value.date().isoformat() for fact in term_end_facts}
        if len(unique_term_dates) > 1:
            first_fact = max(term_end_facts, key=lambda item: item.value)
            issues.append(
                ContractIssue(
                    paragraph_index=first_fact.paragraph_index,
                    fragment=first_fact.fragment,
                    type="TERM_CONFLICT",
                    severity="medium",
                    confidence="medium",
                    explanation="\u0412 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0435 \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u044e\u0442\u0441\u044f \u0440\u0430\u0437\u043d\u044b\u0435 \u0434\u0430\u0442\u044b \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0435\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f.",
                    suggestion="\u041e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043e\u0434\u043d\u0443 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u0443\u044e \u0434\u0430\u0442\u0443 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0432\u043e \u0432\u0441\u0435\u0445 \u043f\u0443\u043d\u043a\u0442\u0430\u0445.",
                )
            )

        return issues

    def _detect_logical_conflicts(
        self,
        analysis_document,
        obligation_facts: list[ObligationFact],
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []
        if not obligation_facts:
            return issues

        paragraph_map = {
            paragraph.paragraph_index: paragraph.text for paragraph in analysis_document.paragraphs
        }
        direction_groups: dict[tuple[str, str], list[ObligationFact]] = {}
        recipient_preferences: dict[str, dict[str, int]] = {}

        for fact in obligation_facts:
            normalized_action = self._normalize_action(fact.action_text)
            if fact.recipient_term:
                pair_key = tuple(
                    sorted(
                        [
                            _normalize_casefold(fact.subject_term),
                            _normalize_casefold(fact.recipient_term),
                        ]
                    )
                )
                direction_groups.setdefault((normalized_action, "|".join(pair_key)), []).append(fact)
                recipient_preferences.setdefault(normalized_action, {})
                normalized_pair = (
                    f"{_normalize_casefold(fact.subject_term)}->{_normalize_casefold(fact.recipient_term)}"
                )
                recipient_preferences[normalized_action][normalized_pair] = (
                    recipient_preferences[normalized_action].get(normalized_pair, 0) + 1
                )

        for (_, _), facts in direction_groups.items():
            if len(facts) < 2:
                continue
            directions = {
                f"{_normalize_casefold(fact.subject_term)}->{_normalize_casefold(fact.recipient_term or '')}": fact
                for fact in facts
            }
            if len(directions) < 2:
                continue

            dominant_direction = max(
                recipient_preferences.get(self._normalize_action(facts[0].action_text), {}).items(),
                key=lambda item: item[1],
            )[0]

            for direction_key, fact in directions.items():
                if direction_key == dominant_direction:
                    continue
                reverse_recipient = fact.recipient_term
                reverse_subject = fact.subject_term
                paragraph_text = paragraph_map.get(fact.paragraph_index, "")
                replacement = self._swap_terms(paragraph_text, reverse_subject, reverse_recipient) if reverse_recipient else None
                issues.append(
                    ContractIssue(
                        paragraph_index=fact.paragraph_index,
                        fragment=paragraph_text.strip()[:160] or fact.subject_term,
                        type="INCONSISTENCY",
                        severity="high",
                        confidence="medium",
                        explanation="\u041d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u0430 \u0432 \u044d\u0442\u043e\u043c \u043f\u0443\u043d\u043a\u0442\u0435 \u0432\u044b\u0433\u043b\u044f\u0434\u0438\u0442 \u043e\u0431\u0440\u0430\u0442\u043d\u044b\u043c \u043f\u043e \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u044e \u0441 \u043e\u0441\u0442\u0430\u043b\u044c\u043d\u043e\u0439 \u043b\u043e\u0433\u0438\u043a\u043e\u0439 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430.",
                        suggestion="\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c, \u043a\u0442\u043e \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0441\u0443\u0431\u044a\u0435\u043a\u0442\u043e\u043c \u0438 \u0430\u0434\u0440\u0435\u0441\u0430\u0442\u043e\u043c \u044d\u0442\u043e\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f.",
                        replacement=replacement,
                    )
                )

        return issues

    def _format_like(self, value: datetime, template: str) -> str:
        lowered_template = template.casefold()
        if any(month in lowered_template for month in (
            "\u044f\u043d\u0432\u0430\u0440",
            "\u0444\u0435\u0432\u0440\u0430\u043b",
            "\u043c\u0430\u0440\u0442",
            "\u0430\u043f\u0440\u0435\u043b",
            "\u043c\u0430\u044f",
            "\u0438\u044e\u043d",
            "\u0438\u044e\u043b",
            "\u0430\u0432\u0433\u0443\u0441\u0442",
            "\u0441\u0435\u043d\u0442\u044f\u0431\u0440",
            "\u043e\u043a\u0442\u044f\u0431\u0440",
            "\u043d\u043e\u044f\u0431\u0440",
            "\u0434\u0435\u043a\u0430\u0431\u0440",
        )):
            months = {
                1: "\u044f\u043d\u0432\u0430\u0440\u044f",
                2: "\u0444\u0435\u0432\u0440\u0430\u043b\u044f",
                3: "\u043c\u0430\u0440\u0442\u0430",
                4: "\u0430\u043f\u0440\u0435\u043b\u044f",
                5: "\u043c\u0430\u044f",
                6: "\u0438\u044e\u043d\u044f",
                7: "\u0438\u044e\u043b\u044f",
                8: "\u0430\u0432\u0433\u0443\u0441\u0442\u0430",
                9: "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f",
                10: "\u043e\u043a\u0442\u044f\u0431\u0440\u044f",
                11: "\u043d\u043e\u044f\u0431\u0440\u044f",
                12: "\u0434\u0435\u043a\u0430\u0431\u0440\u044f",
            }
            suffix = "\u0433\u043e\u0434\u0430" if "\u0433\u043e\u0434\u0430" in lowered_template else "\u0433."
            quote_left = "\u00ab" if "\u00ab" in template else ""
            quote_right = "\u00bb" if "\u00bb" in template else ""
            return f"{quote_left}{value.day:02d}{quote_right} {months[value.month]} {value.year} {suffix}"
        return value.strftime("%d.%m.%Y")

    def _deduplicate(self, issues: list[ContractIssue]) -> list[ContractIssue]:
        unique: list[ContractIssue] = []
        seen: set[tuple[int, str, str]] = set()

        for issue in issues:
            key = (issue.paragraph_index, issue.type, _normalize_casefold(issue.fragment))
            if key in seen:
                continue
            seen.add(key)
            unique.append(issue)

        return unique

    def _replace_role_in_text(
        self,
        text: str,
        markers: tuple[str, ...],
        replacement: str,
    ) -> str | None:
        for marker in markers:
            pattern = re.compile(re.escape(marker), re.IGNORECASE)
            match = pattern.search(text)
            if match is None:
                continue
            source = match.group(0)
            if source.isupper():
                adjusted = replacement.upper()
            elif source.islower():
                adjusted = replacement.lower()
            elif source[:1].isupper():
                adjusted = replacement[:1].upper() + replacement[1:]
            else:
                adjusted = replacement
            return text[: match.start()] + adjusted + text[match.end() :]
        return None

    def _normalize_action(self, value: str) -> str:
        normalized = _normalize_casefold(value)
        for suffix in (
            "\u044b\u0432\u0430\u0435\u0442",
            "\u044f\u0435\u0442",
            "\u0430\u0435\u0442",
            "\u044f\u0437\u0443\u0435\u0442\u0441\u044f",
            "\u0438\u0442",
            "\u0435\u0442",
            "\u0442\u044c",
        ):
            if normalized.endswith(suffix) and len(normalized) > len(suffix) + 3:
                return normalized[: -len(suffix)]
        return normalized

    def _swap_terms(self, text: str, left: str, right: str) -> str | None:
        if not text or not left or not right:
            return None
        left_index = text.find(left)
        right_index = text.find(right)
        if left_index < 0 or right_index < 0:
            return None
        placeholder = "__LEGAL_AI_SWAP__"
        swapped = text.replace(left, placeholder, 1).replace(right, left, 1).replace(placeholder, right, 1)
        return swapped if swapped != text else None


class LegacyRuleEngineLayer:
    def __init__(self) -> None:
        self._analyzer = RuleBasedContractIssueAnalyzer()

    def evaluate(self, analysis_document) -> list[ContractIssue]:
        return self._analyzer.analyze(analysis_document)


class LlmReasoningLayer:
    def __init__(self, analyzer: GeminiContractIssueAnalyzer) -> None:
        self._analyzer = analyzer

    def analyze(
        self,
        context: SemanticContext,
        *,
        candidate_issues: list[ContractIssue] | None = None,
    ):
        semantic_summary = self._build_semantic_summary(context)
        candidate_signals = self._build_candidate_signals(candidate_issues or [])
        return self._analyzer.analyze_with_context(
            context.analysis_document,
            semantic_summary=semantic_summary,
            candidate_signals=candidate_signals,
        )

    def _build_semantic_summary(self, context: SemanticContext) -> str:
        lines: list[str] = []

        heading_nodes = [node for node in context.structure.nodes if node.node_type == "heading"]
        if heading_nodes:
            lines.append("Document structure:")
            lines.extend(
                f"- p{node.paragraph_index}: {' > '.join(node.heading_path) if node.heading_path else node.text}"
                for node in heading_nodes[:20]
            )

        if context.entities:
            lines.append("Extracted legal entities:")
            grouped: dict[str, set[str]] = {}
            for entity in context.entities:
                grouped.setdefault(entity.canonical_value, set()).add(entity.value)
            for canonical, values in grouped.items():
                rendered_values = ", ".join(sorted(values))
                lines.append(f"- {canonical}: {rendered_values}")

        defined_terms = [
            entity for entity in context.entities if entity.entity_type == "defined_term"
        ]
        if defined_terms:
            lines.append("Defined or quoted legal terms detected:")
            for entity in defined_terms[:40]:
                lines.append(f"- p{entity.paragraph_index}: {entity.value}")

        if context.signing_fact is not None:
            lines.append(
                f"Detected signing date: p{context.signing_fact.paragraph_index} -> {context.signing_fact.fragment}"
            )

        if context.temporal_facts:
            lines.append("Extracted temporal facts:")
            for fact in context.temporal_facts[:40]:
                heading_hint = f" | section={' > '.join(fact.heading_path)}" if fact.heading_path else ""
                lines.append(
                    f"- p{fact.paragraph_index} | {fact.semantic_label} | {fact.fragment}{heading_hint}"
                )

        if context.obligation_facts:
            lines.append("Extracted obligation statements:")
            for fact in context.obligation_facts[:50]:
                recipient = f" -> {fact.recipient_term}" if fact.recipient_term else ""
                modality = f" [{fact.modality}]" if fact.modality else ""
                lines.append(
                    f"- p{fact.paragraph_index}: {fact.subject_term}{modality} {fact.action_text}{recipient}"
                )

        return "\n".join(lines).strip()

    def _build_candidate_signals(self, issues: list[ContractIssue]) -> list[str]:
        signals: list[str] = []
        for issue in issues[:40]:
            signals.append(
                f"p{issue.paragraph_index} | {issue.type} | {issue.fragment} | {issue.explanation}"
            )
        return signals


class CorrectionPatchEngine:
    def build_patches(
        self,
        analysis_document,
        issues: list[ContractIssue],
    ) -> list[CorrectionPatch]:
        paragraph_by_index = {
            paragraph.paragraph_index: paragraph.text for paragraph in analysis_document.paragraphs
        }
        patches: list[CorrectionPatch] = []

        for issue in issues:
            if not issue.replacement or not issue.fragment:
                continue
            paragraph_text = paragraph_by_index.get(issue.paragraph_index, "")
            if issue.fragment not in paragraph_text:
                continue
            if issue.fragment == issue.replacement:
                continue
            patches.append(
                CorrectionPatch(
                    paragraph_index=issue.paragraph_index,
                    target_text=issue.fragment,
                    replacement_text=issue.replacement,
                    issue_type=issue.type,
                    reason=issue.suggestion,
                )
            )

        return self._deduplicate(patches)

    def apply_patches(self, analysis_document, patches: list[CorrectionPatch]) -> str | None:
        if not patches:
            return None

        paragraph_texts = {
            paragraph.paragraph_index: paragraph.text for paragraph in analysis_document.paragraphs
        }
        for patch in patches:
            text = paragraph_texts.get(patch.paragraph_index)
            if text is None or patch.target_text not in text:
                continue
            paragraph_texts[patch.paragraph_index] = text.replace(
                patch.target_text,
                patch.replacement_text,
                1,
            )

        ordered_indexes = sorted(paragraph_texts)
        return "\n".join(paragraph_texts[index] for index in ordered_indexes).strip()

    def _deduplicate(self, patches: list[CorrectionPatch]) -> list[CorrectionPatch]:
        unique: list[CorrectionPatch] = []
        seen: set[tuple[int, str, str]] = set()
        for patch in patches:
            key = (patch.paragraph_index, patch.target_text, patch.replacement_text)
            if key in seen:
                continue
            seen.add(key)
            unique.append(patch)
        return unique


class SemanticLegalAiPipeline(LegalAiPipeline):
    def __init__(
        self,
        *,
        structure_layer: DocumentStructureLayer | None = None,
        entity_extraction_layer: LegalEntityExtractionLayer | None = None,
        obligation_extraction_layer: ObligationExtractionLayer | None = None,
        rule_engine_layer: RuleEngineLayer | None = None,
        legacy_rule_engine_layer: LegacyRuleEngineLayer | None = None,
        llm_reasoning_layer: LlmReasoningLayer | None = None,
        correction_patch_engine: CorrectionPatchEngine | None = None,
    ) -> None:
        self._structure_layer = structure_layer or DocumentStructureLayer()
        self._entity_extraction_layer = entity_extraction_layer or LegalEntityExtractionLayer()
        self._obligation_extraction_layer = (
            obligation_extraction_layer or ObligationExtractionLayer()
        )
        self._rule_engine_layer = rule_engine_layer or RuleEngineLayer()
        self._legacy_rule_engine_layer = legacy_rule_engine_layer or LegacyRuleEngineLayer()
        self._llm_reasoning_layer = llm_reasoning_layer or LlmReasoningLayer(
            GeminiContractIssueAnalyzer()
        )
        self._correction_patch_engine = correction_patch_engine or CorrectionPatchEngine()

    def analyze(self, document: ParsedContractDocument) -> SemanticAnalysisResult:
        analysis_document = build_contract_analysis_document(
            filename=document.filename,
            source_format=document.source_format,
            text=document.text,
            pages=document.pages,
        )
        structure = self._structure_layer.build(analysis_document)
        entities, temporal_facts = self._entity_extraction_layer.extract(
            analysis_document,
            structure,
        )
        obligation_facts = self._obligation_extraction_layer.extract(
            analysis_document,
            structure,
            entities,
        )
        context = SemanticContext(
            analysis_document=analysis_document,
            structure=structure,
            entities=entities,
            temporal_facts=temporal_facts,
            obligation_facts=obligation_facts,
            signing_fact=self._resolve_signing_fact(temporal_facts),
        )

        semantic_issues = self._rule_engine_layer.evaluate(context)
        legacy_issues = self._legacy_rule_engine_layer.evaluate(analysis_document)
        llm_result = self._llm_reasoning_layer.analyze(
            context,
            candidate_issues=[*semantic_issues, *legacy_issues],
        )
        issues = self._merge_issues(semantic_issues, legacy_issues, llm_result.issues)
        patches = self._correction_patch_engine.build_patches(analysis_document, issues)
        corrected_text = self._correction_patch_engine.apply_patches(analysis_document, patches)

        return SemanticAnalysisResult(
            issues=issues,
            warnings=llm_result.warnings,
            corrected_text=corrected_text,
            patches=patches,
            structure=structure,
            entities=entities,
            temporal_facts=temporal_facts,
            obligation_facts=obligation_facts,
        )

    def _merge_issues(
        self,
        *issue_groups: list[ContractIssue],
    ) -> list[ContractIssue]:
        merged: list[ContractIssue] = []
        seen: set[tuple[int, str, str]] = set()

        for issue_group in issue_groups:
            for issue in issue_group:
                key = (issue.paragraph_index, issue.type, _normalize_casefold(issue.fragment))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(issue)

        return sorted(merged, key=lambda item: (item.paragraph_index, item.type, item.fragment))

    def _resolve_signing_fact(self, temporal_facts: list[TemporalFact]) -> TemporalFact | None:
        explicit = [fact for fact in temporal_facts if fact.semantic_label == "signing_date"]
        if explicit:
            return min(explicit, key=lambda item: (item.paragraph_index, item.value))

        early_facts = [fact for fact in temporal_facts if fact.paragraph_index <= 3]
        if early_facts:
            return min(early_facts, key=lambda item: (item.paragraph_index, item.value))

        return None
