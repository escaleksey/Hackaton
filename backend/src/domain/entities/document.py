from dataclasses import dataclass, field


DEFAULT_PAGE_WIDTH_PT = 595.3
DEFAULT_PAGE_HEIGHT_PT = 841.9


@dataclass(slots=True)
class TextRun:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_name: str | None = None
    font_size_pt: float | None = None
    color: str | None = None


@dataclass(slots=True)
class ParagraphBlock:
    id: str
    runs: list[TextRun] = field(default_factory=list)
    alignment: str = "left"
    style_name: str | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    line_spacing: float | None = None

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass(slots=True)
class DocumentPage:
    number: int
    blocks: list[ParagraphBlock] = field(default_factory=list)


@dataclass(slots=True)
class DocumentLayout:
    page_width_pt: float = DEFAULT_PAGE_WIDTH_PT
    page_height_pt: float = DEFAULT_PAGE_HEIGHT_PT
    margin_top_pt: float | None = None
    margin_right_pt: float | None = None
    margin_bottom_pt: float | None = None
    margin_left_pt: float | None = None


def flatten_document_pages(pages: list[DocumentPage]) -> str:
    page_chunks: list[str] = []

    for page in pages:
        block_chunks = [block.text for block in page.blocks]
        page_chunks.append("\n".join(block_chunks))

    return "\n\n".join(page_chunks).strip()


def normalize_document_pages(pages: list[DocumentPage]) -> list[DocumentPage]:
    normalized_pages: list[DocumentPage] = []

    for page_index, page in enumerate(pages, start=1):
        normalized_blocks: list[ParagraphBlock] = []

        for block_index, block in enumerate(page.blocks, start=1):
            runs = block.runs or [TextRun(text="")]
            normalized_blocks.append(
                ParagraphBlock(
                    id=block.id or f"page-{page_index}-block-{block_index}",
                    runs=runs,
                    alignment=block.alignment or "left",
                    style_name=block.style_name,
                    space_before_pt=block.space_before_pt,
                    space_after_pt=block.space_after_pt,
                    line_spacing=block.line_spacing,
                )
            )

        normalized_pages.append(DocumentPage(number=page_index, blocks=normalized_blocks))

    return normalized_pages
