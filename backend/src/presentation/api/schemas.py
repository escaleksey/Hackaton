from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TextRunSchema(BaseModel):
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_name: str | None = None
    font_size_pt: float | None = None
    color: str | None = None
    highlight_color: str | None = None


class ParagraphBlockSchema(BaseModel):
    id: str
    runs: list[TextRunSchema] = Field(default_factory=list)
    alignment: str = "left"
    style_name: str | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    line_spacing: float | None = None


class DocumentPageSchema(BaseModel):
    number: int
    blocks: list[ParagraphBlockSchema] = Field(default_factory=list)


class DocumentLayoutSchema(BaseModel):
    page_width_pt: float
    page_height_pt: float
    margin_top_pt: float | None = None
    margin_right_pt: float | None = None
    margin_bottom_pt: float | None = None
    margin_left_pt: float | None = None


class ContractIssueSchema(BaseModel):
    paragraph_index: int
    fragment: str
    type: str
    severity: Literal["high", "medium", "low"]
    confidence: Literal["high", "medium", "low"]
    explanation: str
    suggestion: str
    replacement: str | None = None


class ContractAnalysisWarningSchema(BaseModel):
    code: str
    message: str


class ContractDraftResponse(BaseModel):
    id: UUID
    filename: str
    source_format: Literal["txt", "docx"]
    original_text: str
    corrected_text: str
    original_pages: list[DocumentPageSchema] = Field(default_factory=list)
    corrected_pages: list[DocumentPageSchema] = Field(default_factory=list)
    document_layout: DocumentLayoutSchema | None = None
    issues: list[ContractIssueSchema] = Field(default_factory=list)
    warnings: list[ContractAnalysisWarningSchema] = Field(default_factory=list)
    created_at: datetime


class UpdateContractTextRequest(BaseModel):
    corrected_text: str | None = Field(default=None, min_length=1)
    corrected_pages: list[DocumentPageSchema] | None = None
