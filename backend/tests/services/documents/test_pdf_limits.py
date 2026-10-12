from pathlib import Path

import pytest

from app.services.documents import DocumentError
from app.services.documents.ops.pdf import PdfExtractor
from app.settings import settings
from tests.services.documents.builders import write_pdf


def _five_pages(tmp_path: Path) -> Path:
    return write_pdf(tmp_path / "five.pdf", pages=[[f"page {n} text"] for n in range(1, 6)], outline=[])


def test_a_pdf_over_the_page_ceiling_is_refused(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(settings.documents, "max_pdf_pages", 3)
    with pytest.raises(DocumentError) as exc:
        PdfExtractor().extract(_five_pages(tmp_path))
    assert exc.value.category == "limit_exceeded"
    assert "5 pages" in exc.value.message


def test_extraction_stops_when_its_time_budget_is_spent(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(settings.documents, "extract_budget_sec", 0)
    with pytest.raises(DocumentError) as exc:
        PdfExtractor().extract(_five_pages(tmp_path))
    assert exc.value.category == "limit_exceeded"


def test_extraction_stops_once_the_text_passes_the_ceiling(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(settings.documents, "max_document_text_bytes", 20)
    with pytest.raises(DocumentError) as exc:
        PdfExtractor().extract(_five_pages(tmp_path))
    assert exc.value.category == "extracted_too_large"


def test_a_pdf_inside_every_limit_still_reads(tmp_path: Path):
    assert PdfExtractor().extract(_five_pages(tmp_path)).summary["pages"] == 5
