from pathlib import Path

import pytest

from app.services.documents import DocumentError, normalize
from app.services.documents.ops.pdf import MARKER, PdfExtractor
from tests.services.documents.builders import GUIDE_PAGES, write_pdf

# ? Gitignored with the rest of data/adobe_docs, so the one test that needs a real document skips where it is absent
SPEC_PDF = Path(__file__).resolve().parents[4] / "data" / "adobe_docs" / "PDF32000_2008.pdf"


def _marker_lines(text: str) -> list[int]:
    return [i for i, line in enumerate(text.splitlines(), start=1) if MARKER.fullmatch(line)]


def test_every_page_starts_with_exactly_one_marker_line(tmp_path: Path):
    result = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf"))
    # ? Counted as whole lines: the substring "[page " can also occur inside ordinary text
    assert len(_marker_lines(result.text)) == result.summary["pages"] == len(GUIDE_PAGES)


def test_outline_lines_land_on_their_page_markers(tmp_path: Path):
    result = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf"))
    lines = result.text.splitlines()
    assert [entry.label for entry in result.outline] == ["Chapter One", "Chapter Two"]
    # ! Checked with splitlines(), which is how mpmb_read counts, so an outline line is a line read will reach
    assert [lines[entry.line - 1] for entry in result.outline] == ["[page 1]", "[page 3]"]


def test_split_and_splitlines_agree(tmp_path: Path):
    text = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf")).text
    assert text.split("\n") == text.splitlines()


def test_a_page_with_no_text_layer_is_reported(tmp_path: Path):
    result = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf"))
    assert result.pages_without_text == [2]


def test_output_is_already_normalized(tmp_path: Path):
    text = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf")).text
    assert normalize(text) == text


def test_text_that_looks_like_a_marker_cannot_impersonate_one(tmp_path: Path):
    path = write_pdf(tmp_path / "tricky.pdf", pages=[["see below", "[page 9]", "end"]], outline=[])
    result = PdfExtractor().extract(path)
    assert len(_marker_lines(result.text)) == 1
    assert " [page 9]" in result.text.splitlines()


def test_an_unreadable_file_raises_extraction_failed(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf at all")
    with pytest.raises(DocumentError) as exc:
        PdfExtractor().extract(path)
    assert exc.value.category == "extraction_failed"
    assert exc.value.as_tool_error().startswith("[error]")


@pytest.mark.skipif(not SPEC_PDF.exists(), reason="PDF 32000 spec is gitignored under data/adobe_docs")
def test_real_document_keeps_phrases_whole_and_lines_consistent():
    # ! pypdf split "content stream" mid-word here, which is invisible to a reader and fatal to grep
    result = PdfExtractor().extract(SPEC_PDF)
    lowered = result.text.lower()
    assert "content stream" in lowered
    assert "conten t stream" not in lowered
    lines = result.text.splitlines()
    assert all(MARKER.fullmatch(lines[entry.line - 1]) for entry in result.outline)
