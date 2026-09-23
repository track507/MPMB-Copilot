from pathlib import Path
from typing import Optional

import pytest

from app.config import config
from app.services.documents import CacheScope, DocumentError, Extraction, registry
from app.services.documents import service as documents
from tests.services.documents.builders import write_pdf

USER = CacheScope.for_user("u1")


@pytest.fixture(autouse=True)
def extracted_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "extracted"
    monkeypatch.setattr(config, "extracted_dir", str(target), raising=False)
    monkeypatch.setattr(registry, "_availability", {})
    return target


class _FakePdf:
    """Stands in for the PDF adapter so a test controls what extraction returns and counts the calls"""

    extensions = frozenset({".pdf"})
    version = "1"

    def __init__(self, text: str = "[page 1]\nhello", reason: Optional[str] = None) -> None:
        self.text = text
        self.reason = reason
        self.calls = 0

    def check_availability(self) -> Optional[str]:
        return self.reason

    def extract(self, path: Path) -> Extraction:
        self.calls += 1
        return Extraction(text=self.text, outline=[], pages_without_text=[], summary={"pages": 1})


def _use(monkeypatch: pytest.MonkeyPatch, fake: _FakePdf) -> _FakePdf:
    monkeypatch.setitem(registry._extractors, ".pdf", fake)
    return fake


def test_extracts_once_then_serves_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = _use(monkeypatch, _FakePdf())
    pdf = write_pdf(tmp_path / "guide.pdf")

    first = documents.ensure_extracted(pdf, USER)
    second = documents.ensure_extracted(pdf, USER)

    assert fake.calls == 1
    assert first.text_path == second.text_path


def test_lookup_never_extracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = _use(monkeypatch, _FakePdf())
    pdf = write_pdf(tmp_path / "guide.pdf")

    assert documents.lookup(pdf, USER) is None
    assert fake.calls == 0
    documents.ensure_extracted(pdf, USER)
    assert documents.lookup(pdf, USER) is not None


def test_an_unsupported_format_names_the_readable_ones(tmp_path: Path):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"x")
    with pytest.raises(DocumentError) as exc:
        documents.ensure_extracted(path, USER)
    assert exc.value.category == "unsupported_format"
    assert ".pdf" in exc.value.message


def test_an_unavailable_extractor_surfaces_its_reason_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, _FakePdf(reason="LibreOffice is disabled in settings"))
    with pytest.raises(DocumentError) as exc:
        documents.ensure_extracted(write_pdf(tmp_path / "guide.pdf"), USER)
    assert exc.value.category == "extractor_unavailable"
    assert exc.value.message == "LibreOffice is disabled in settings"


def test_an_adapter_that_skips_normalize_is_rejected_before_caching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # ! Unnormalized text has line numbers the tools would disagree about, so it must never reach the cache
    _use(monkeypatch, _FakePdf(text="[page 1]\r\nhello"))
    pdf = write_pdf(tmp_path / "guide.pdf")
    with pytest.raises(DocumentError) as exc:
        documents.ensure_extracted(pdf, USER)
    assert exc.value.category == "extraction_failed"
    assert documents.lookup(pdf, USER) is None


def test_the_real_pdf_adapter_round_trips_through_the_cache(tmp_path: Path):
    pdf = write_pdf(tmp_path / "guide.pdf")
    document = documents.ensure_extracted(pdf, USER)
    assert "[page 1]" in document.text_path.read_text(encoding="utf-8")
    assert document.pages_without_text == [2]
    assert documents.lookup(pdf, USER) == document


def test_cached_summary_reads_by_hash_without_the_file(tmp_path: Path):
    pdf = write_pdf(tmp_path / "guide.pdf")
    digest = documents.file_hash(pdf)
    assert documents.cached_summary(digest, ".pdf", USER) is None

    documents.ensure_extracted(pdf, USER)
    pdf.unlink()

    summary = documents.cached_summary(digest, ".pdf", USER)
    assert summary is not None and summary["pages"] == 3


def test_release_removes_the_extraction(tmp_path: Path):
    pdf = write_pdf(tmp_path / "guide.pdf")
    digest = documents.file_hash(pdf)
    documents.ensure_extracted(pdf, USER)

    assert documents.release(digest, ".pdf", USER) == 2
    assert documents.lookup(pdf, USER) is None
    assert documents.release(digest, ".js", USER) == 0


def test_an_edited_file_is_hashed_again(tmp_path: Path):
    pdf = write_pdf(tmp_path / "guide.pdf")
    before = documents.file_hash(pdf)
    write_pdf(pdf, pages=[["a different document"]], outline=[])
    assert documents.file_hash(pdf) != before
