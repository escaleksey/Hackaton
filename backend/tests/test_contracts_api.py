from io import BytesIO

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fastapi.testclient import TestClient

from src.main import app
from src.presentation.api.dependencies import get_contract_repository


@pytest.fixture(autouse=True)
def clear_contract_repository() -> None:
    get_contract_repository()._storage.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def build_docx_file() -> bytes:
    document = Document()
    document.add_heading("Заголовок договора", level=1)
    document.add_paragraph("Основной текст документа.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_upload_apply_and_download_text_contract(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/contracts/upload",
        data={"text": "Исходный договор"},
    )

    assert upload_response.status_code == 201
    draft = upload_response.json()
    assert draft["source_format"] == "txt"

    apply_response = client.post(
        f"/api/v1/contracts/{draft['id']}/apply",
        json={"corrected_text": "Исправленный договор"},
    )

    assert apply_response.status_code == 200
    assert apply_response.json()["corrected_text"] == "Исправленный договор"

    download_response = client.get(f"/api/v1/contracts/{draft['id']}/download")
    assert download_response.status_code == 200
    assert download_response.text == "Исправленный договор"
    assert "attachment" in download_response.headers["content-disposition"]


def test_upload_docx_preserves_heading_style_metadata(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/contracts/upload",
        files={
            "file": (
                "contract.docx",
                build_docx_file(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert upload_response.status_code == 201
    draft = upload_response.json()
    assert draft["source_format"] == "docx"
    assert draft["corrected_pages"]

    first_block = draft["corrected_pages"][0]["blocks"][0]
    assert first_block["style_name"] is not None
    assert first_block["runs"][0]["font_size_pt"] is not None


def test_apply_and_download_docx_preserves_heading_formatting(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/contracts/upload",
        files={
            "file": (
                "contract.docx",
                build_docx_file(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert upload_response.status_code == 201
    draft = upload_response.json()
    corrected_pages = draft["corrected_pages"]

    corrected_pages[0]["blocks"][0]["alignment"] = "center"
    corrected_pages[0]["blocks"][0]["style_name"] = "Heading 1"
    corrected_pages[0]["blocks"][0]["runs"] = [
        {
            "text": "Исправленный заголовок",
            "bold": True,
            "italic": False,
            "underline": False,
            "font_name": "Arial",
            "font_size_pt": 18,
            "color": None,
        }
    ]

    apply_response = client.post(
        f"/api/v1/contracts/{draft['id']}/apply",
        json={"corrected_pages": corrected_pages},
    )

    assert apply_response.status_code == 200

    download_response = client.get(f"/api/v1/contracts/{draft['id']}/download")
    assert download_response.status_code == 200
    assert (
        download_response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    downloaded_document = Document(BytesIO(download_response.content))
    heading = downloaded_document.paragraphs[0]

    assert heading.text == "Исправленный заголовок"
    assert heading.style.name == "Heading 1"
    assert heading.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert heading.runs[0].font.size is not None
    assert round(heading.runs[0].font.size.pt) == 18
