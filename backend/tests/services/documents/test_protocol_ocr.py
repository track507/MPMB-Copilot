"""
The shapes OCR adds to the document port
"""

from app.services.documents import PageVisuals
from app.services.documents.protocol import Extraction


def test_extraction_defaults_to_no_visuals():
    e = Extraction(text="x", outline=[], pages_without_text=[], summary={})
    assert e.page_visuals == []


def test_visuals_and_empty_pages_are_independent():
    e = Extraction(
        text="prose",
        outline=[],
        pages_without_text=[],
        summary={},
        page_visuals=[PageVisuals(page=3, image_count=1, image_coverage=0.4)],
    )
    assert e.pages_without_text == []
    assert e.page_visuals[0].page == 3
