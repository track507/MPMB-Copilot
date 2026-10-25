"""
Transcription of empty pages, and the read path that never runs it
"""

from pathlib import Path

from app.services.documents import registry
from app.services.documents.ops.pdf import PdfExtractor
from app.settings import settings
from tests.services.documents.builders import FULL_PAGE_IMAGE, write_pdf


class _Fake:
    id = "fake"
    version = "1"

    def __init__(self, text: str) -> None:
        self._text = text

    def check_availability(self):
        return None

    def transcribe(self, image: bytes) -> str:
        return self._text


def _scan(tmp_path: Path) -> Path:
    return write_pdf(tmp_path / "scan.pdf", pages=[[]], outline=[], images=FULL_PAGE_IMAGE)


def test_a_transcribed_page_leaves_pages_without_text(tmp_path: Path):
    result = PdfExtractor(transcriber=_Fake("recovered words")).extract(_scan(tmp_path))
    assert "recovered words" in result.text
    assert result.pages_without_text == []


def test_a_transcribed_page_is_marked_with_its_engine(tmp_path: Path):
    result = PdfExtractor(transcriber=_Fake("recovered words")).extract(_scan(tmp_path))
    assert [visual.transcribed_by for visual in result.page_visuals] == ["fake"]


def test_a_page_the_engine_cannot_read_stays_reported(tmp_path: Path):
    result = PdfExtractor(transcriber=_Fake("")).extract(_scan(tmp_path))
    assert result.pages_without_text == [1]


def test_without_a_transcriber_nothing_changes(tmp_path: Path):
    assert PdfExtractor().extract(_scan(tmp_path)).pages_without_text == [1]


def test_later_pages_keep_their_outline_line_after_insertion(tmp_path: Path):
    path = write_pdf(
        tmp_path / "mixed.pdf",
        pages=[[], ["Chapter Two"]],
        outline=[("Two", 1)],
        images={0: [(0, 0, 612, 792)]},
    )
    result = PdfExtractor(transcriber=_Fake("line one\nline two")).extract(path)
    lines = result.text.split("\n")
    assert lines[result.outline[0].line - 1] == "[page 2]"


def test_the_read_path_extractor_has_no_transcriber():
    assert registry.extractor_for(".pdf").version == PdfExtractor().version


def test_candidate_versions_never_load_the_engine(monkeypatch):
    from app.services.documents.ops import ocr

    def refuse(self):
        raise AssertionError("engine loaded on the read path")

    monkeypatch.setitem(settings.documents, "ocr_enabled", True)
    monkeypatch.setattr(ocr.RapidOcrTranscriber, "_ensure_engine", refuse)
    assert len(registry.candidate_versions(".pdf")) == 2


def test_ocr_off_leaves_only_the_text_only_version(monkeypatch):
    monkeypatch.setitem(settings.documents, "ocr_enabled", False)
    assert registry.candidate_versions(".pdf") == [PdfExtractor().version]
