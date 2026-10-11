"""
Visual detection and the version fingerprint
"""

from pathlib import Path

from app.services.documents.ops.pdf import CAPTION_MAX_CHARS, PdfExtractor
from tests.services.documents.builders import FULL_PAGE_IMAGE, PAGE_HEIGHT, PAGE_WIDTH, write_pdf


class _FakeTranscriber:
    id = "fake"
    version = "1"

    def check_availability(self):
        return None

    def transcribe(self, image: bytes) -> str:
        return "transcribed"


def test_version_is_stable_for_the_same_inputs():
    assert PdfExtractor().version == PdfExtractor().version


def test_a_transcriber_changes_the_version():
    assert PdfExtractor().version != PdfExtractor(transcriber=_FakeTranscriber()).version


def test_version_matches_the_cache_safe_charset():
    import re

    assert re.fullmatch(r"[A-Za-z0-9_-]+", PdfExtractor(transcriber=_FakeTranscriber()).version)


def test_a_page_without_images_records_no_visuals(tmp_path: Path):
    result = PdfExtractor().extract(write_pdf(tmp_path / "guide.pdf"))
    assert result.page_visuals == []


def test_a_full_page_image_covers_the_page(tmp_path: Path):
    path = write_pdf(tmp_path / "scan.pdf", pages=[[]], outline=[], images=FULL_PAGE_IMAGE)
    visuals = PdfExtractor().extract(path).page_visuals
    assert len(visuals) == 1
    assert visuals[0].image_count == 1
    assert visuals[0].image_coverage == 1.0


def test_a_decorative_image_is_not_reported_as_coverage(tmp_path: Path):
    path = write_pdf(tmp_path / "border.pdf", pages=[["Chapter One"]], outline=[], images={0: [(20, 20, 30, 30)]})
    visuals = PdfExtractor().extract(path).page_visuals
    assert visuals[0].image_coverage < 0.01


def test_a_scan_appears_in_both_signals(tmp_path: Path):
    path = write_pdf(tmp_path / "scan.pdf", pages=[[]], outline=[], images=FULL_PAGE_IMAGE)
    result = PdfExtractor().extract(path)
    assert result.pages_without_text == [1]
    assert [visuals.page for visuals in result.page_visuals] == [1]


def test_overlapping_images_do_not_push_coverage_past_one(tmp_path: Path):
    rects = [(0, 0, PAGE_WIDTH, PAGE_HEIGHT), (0, 0, PAGE_WIDTH, PAGE_HEIGHT)]
    path = write_pdf(tmp_path / "stacked.pdf", pages=[[]], outline=[], images={0: rects})
    visuals = PdfExtractor().extract(path).page_visuals
    assert visuals[0].image_count == 2
    assert visuals[0].image_coverage == 1.0


def test_only_image_bearing_pages_are_recorded_and_pages_are_one_based(tmp_path: Path):
    path = write_pdf(
        tmp_path / "mixed.pdf",
        pages=[["Chapter One"], [], ["Chapter Two"]],
        outline=[],
        images={1: [(0, 0, PAGE_WIDTH, PAGE_HEIGHT)]},
    )
    assert [visuals.page for visuals in PdfExtractor().extract(path).page_visuals] == [2]


def test_a_caption_under_an_image_is_recorded(tmp_path: Path):
    path = write_pdf(
        tmp_path / "figure.pdf",
        pages=[["Figure 1: the sigil of the Blood Hunter"]],
        outline=[],
        images={0: [(72, 730, 200, 50)]},
    )
    visuals = PdfExtractor().extract(path).page_visuals
    assert visuals[0].nearby_text == "Figure 1: the sigil of the Blood Hunter"


def test_a_page_with_no_text_layer_has_no_caption(tmp_path: Path):
    path = write_pdf(tmp_path / "scan.pdf", pages=[[]], outline=[], images=FULL_PAGE_IMAGE)
    assert PdfExtractor().extract(path).page_visuals[0].nearby_text is None


def test_a_caption_is_capped_so_the_sidecar_stays_small(tmp_path: Path):
    lines = ["word " * 40 for _ in range(3)]
    path = write_pdf(tmp_path / "long.pdf", pages=[lines], outline=[], images={0: [(0, 730, 500, 50)]})
    caption = PdfExtractor().extract(path).page_visuals[0].nearby_text
    assert caption is not None
    assert len(caption) == CAPTION_MAX_CHARS
