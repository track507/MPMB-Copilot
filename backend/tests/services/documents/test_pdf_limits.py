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


class _CountingTranscriber:
    id = "fake"
    version = "1"

    def __init__(self) -> None:
        self.calls = 0

    def check_availability(self):
        return None

    def transcribe(self, image: bytes) -> str:
        self.calls += 1
        return "words"


def _square_blank_page(path: Path, side: float) -> Path:
    import pypdfium2

    document = pypdfium2.PdfDocument.new()
    document.new_page(side, side)
    document.save(str(path))
    document.close()
    return path


def test_a_page_too_large_to_rasterize_is_never_rendered(tmp_path: Path, monkeypatch):
    import pypdfium2

    def refuse(*_args, **_kwargs):
        raise AssertionError("render was called")

    monkeypatch.setattr(pypdfium2.PdfPage, "render", refuse)
    transcriber = _CountingTranscriber()
    extraction = PdfExtractor(transcriber).extract(_square_blank_page(tmp_path / "huge.pdf", 30_000))
    assert extraction.pages_without_text == [1]
    assert extraction.summary["oversized_pages"] == [1]
    assert transcriber.calls == 0


def test_a_page_inside_the_pixel_budget_is_still_transcribed(tmp_path: Path):
    transcriber = _CountingTranscriber()
    extraction = PdfExtractor(transcriber).extract(_square_blank_page(tmp_path / "letter.pdf", 612))
    assert extraction.pages_without_text == []
    assert transcriber.calls == 1
    assert "oversized_pages" not in extraction.summary


class _SpyLock:
    def __init__(self) -> None:
        self.held = False
        self.entries = 0

    def __enter__(self):
        assert not self.held
        self.held = True
        self.entries += 1

    def __exit__(self, *_exc):
        self.held = False


def test_every_pdfium_call_holds_the_lock_and_ocr_runs_outside_it(tmp_path: Path, monkeypatch):
    import pypdfium2

    from app.services.documents.ops import pdf

    spy = _SpyLock()
    monkeypatch.setattr(pdf, "_PDFIUM", spy)

    def guarded(name):
        real = getattr(pypdfium2.PdfPage, name)

        def call(self, *args, **kwargs):
            assert spy.held
            return real(self, *args, **kwargs)

        return call

    monkeypatch.setattr(pypdfium2.PdfPage, "get_textpage", guarded("get_textpage"))
    monkeypatch.setattr(pypdfium2.PdfPage, "render", guarded("render"))

    class _OutsideTranscriber(_CountingTranscriber):
        def transcribe(self, image: bytes) -> str:
            assert not spy.held
            return super().transcribe(image)

    transcriber = _OutsideTranscriber()
    PdfExtractor(transcriber).extract(_square_blank_page(tmp_path / "scan.pdf", 612))
    assert transcriber.calls == 1
    assert spy.entries >= 4
    assert not spy.held
