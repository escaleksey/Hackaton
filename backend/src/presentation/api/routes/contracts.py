from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from src.application.dto.contract_draft_result import ContractDraftResult
from src.application.use_cases.common import ContractNotFoundError
from src.application.use_cases.create_contract_draft import CreateContractDraftUseCase
from src.application.use_cases.download_contract import DownloadContractUseCase
from src.application.use_cases.get_contract_draft import GetContractDraftUseCase
from src.application.use_cases.update_contract_text import UpdateContractTextUseCase
from src.domain.entities.document import DocumentLayout, DocumentPage, ParagraphBlock, TextRun
from src.presentation.api.dependencies import (
    get_create_contract_draft_use_case,
    get_download_contract_use_case,
    get_get_contract_draft_use_case,
    get_update_contract_text_use_case,
)
from src.presentation.api.schemas import (
    ContractAnalysisWarningSchema,
    ContractDraftResponse,
    ContractIssueSchema,
    DocumentLayoutSchema,
    DocumentPageSchema,
    ParagraphBlockSchema,
    TextRunSchema,
    UpdateContractTextRequest,
)

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])


def _to_response(result: ContractDraftResult) -> ContractDraftResponse:
    return ContractDraftResponse(
        id=result.id,
        filename=result.filename,
        source_format=result.source_format,
        original_text=result.original_text,
        corrected_text=result.corrected_text,
        original_pages=[_page_to_schema(page) for page in result.original_pages],
        corrected_pages=[_page_to_schema(page) for page in result.corrected_pages],
        document_layout=_layout_to_schema(result.document_layout),
        issues=[
            ContractIssueSchema(
                paragraph_index=issue.paragraph_index,
                fragment=issue.fragment,
                type=issue.type,
                severity=issue.severity,
                confidence=issue.confidence,
                explanation=issue.explanation,
                suggestion=issue.suggestion,
                replacement=issue.replacement,
            )
            for issue in result.issues
        ],
        warnings=[
            ContractAnalysisWarningSchema(
                code=warning.code,
                message=warning.message,
            )
            for warning in result.warnings
        ],
        created_at=result.created_at,
    )


def _page_to_schema(page: DocumentPage) -> DocumentPageSchema:
    return DocumentPageSchema(
        number=page.number,
        blocks=[
            ParagraphBlockSchema(
                id=block.id,
                runs=[
                    TextRunSchema(
                        text=run.text,
                        bold=run.bold,
                        italic=run.italic,
                        underline=run.underline,
                        font_name=run.font_name,
                        font_size_pt=run.font_size_pt,
                        color=run.color,
                        highlight_color=run.highlight_color,
                    )
                    for run in block.runs
                ],
                alignment=block.alignment,
                style_name=block.style_name,
                space_before_pt=block.space_before_pt,
                space_after_pt=block.space_after_pt,
                line_spacing=block.line_spacing,
            )
            for block in page.blocks
        ],
    )


def _layout_to_schema(layout: DocumentLayout | None) -> DocumentLayoutSchema | None:
    if layout is None:
        return None

    return DocumentLayoutSchema(
        page_width_pt=layout.page_width_pt,
        page_height_pt=layout.page_height_pt,
        margin_top_pt=layout.margin_top_pt,
        margin_right_pt=layout.margin_right_pt,
        margin_bottom_pt=layout.margin_bottom_pt,
        margin_left_pt=layout.margin_left_pt,
    )


def _pages_from_schema(pages: list[DocumentPageSchema]) -> list[DocumentPage]:
    return [
        DocumentPage(
            number=page.number,
            blocks=[
                ParagraphBlock(
                    id=block.id,
                    runs=[
                        TextRun(
                            text=run.text,
                            bold=run.bold,
                            italic=run.italic,
                            underline=run.underline,
                            font_name=run.font_name,
                            font_size_pt=run.font_size_pt,
                            color=run.color,
                            highlight_color=run.highlight_color,
                        )
                        for run in block.runs
                    ],
                    alignment=block.alignment,
                    style_name=block.style_name,
                    space_before_pt=block.space_before_pt,
                    space_after_pt=block.space_after_pt,
                    line_spacing=block.line_spacing,
                )
                for block in page.blocks
            ],
        )
        for page in pages
    ]


def _handle_use_case(
    action: Callable[[], ContractDraftResult],
) -> ContractDraftResponse:
    try:
        return _to_response(action())
    except ContractNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


def _build_content_disposition(filename: str) -> str:
    ascii_fallback = "".join(char if ord(char) < 128 else "_" for char in filename)
    encoded_filename = quote(filename)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"


@router.post("/upload", response_model=ContractDraftResponse, status_code=status.HTTP_201_CREATED)
async def upload_contract(
    create_contract_draft_use_case: Annotated[
        CreateContractDraftUseCase, Depends(get_create_contract_draft_use_case)
    ],
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
) -> ContractDraftResponse:
    if file is None and not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Передайте файл договора или текст договора.",
        )

    filename = "contract.txt"
    contract_text = text
    file_bytes: bytes | None = None

    if file is not None:
        filename = file.filename or filename
        file_bytes = await file.read()

    return _handle_use_case(
        lambda: create_contract_draft_use_case.execute(
            filename=filename,
            text=contract_text,
            file_bytes=file_bytes,
        )
    )


@router.get("/{contract_id}", response_model=ContractDraftResponse)
def get_contract(
    contract_id: UUID,
    get_contract_draft_use_case: Annotated[
        GetContractDraftUseCase, Depends(get_get_contract_draft_use_case)
    ],
) -> ContractDraftResponse:
    return _handle_use_case(lambda: get_contract_draft_use_case.execute(contract_id))


@router.post("/{contract_id}/apply", response_model=ContractDraftResponse)
def apply_contract_corrections(
    contract_id: UUID,
    payload: UpdateContractTextRequest,
    update_contract_text_use_case: Annotated[
        UpdateContractTextUseCase, Depends(get_update_contract_text_use_case)
    ],
) -> ContractDraftResponse:
    return _handle_use_case(
        lambda: update_contract_text_use_case.execute(
            contract_id,
            corrected_text=payload.corrected_text,
            corrected_pages=_pages_from_schema(payload.corrected_pages)
            if payload.corrected_pages is not None
            else None,
        )
    )


@router.get("/{contract_id}/download")
def download_contract(
    contract_id: UUID,
    download_contract_use_case: Annotated[
        DownloadContractUseCase, Depends(get_download_contract_use_case)
    ],
) -> StreamingResponse:
    try:
        result = download_contract_use_case.execute(contract_id)
    except ContractNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    response = StreamingResponse(iter([result.content]), media_type=result.media_type)
    response.headers["Content-Disposition"] = _build_content_disposition(result.filename)
    return response
