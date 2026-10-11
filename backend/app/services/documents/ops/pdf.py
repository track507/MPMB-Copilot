"""
PDF text extraction via pypdfium2

Reading order, not table cells: rows land one per line with the key first, which keeps them greppable
A table-aware extractor can join behind the same port if that turns out to limit answers
"""

import hashlib
import io
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from app.services.documents.errors import DocumentError
from app.services.documents.protocol import Extraction, OutlineEntry, PageTranscriber, PageVisuals, normalize

EXTENSIONS = frozenset({".pdf"})
# ! Bump on any change to the extraction output
VERSION = "2"
RENDER_DPI = 200

CAPTION_BAND_FRACTION = 0.06
CAPTION_BAND_MAX = 40.0
CAPTION_MAX_CHARS = 200

MARKER = re.compile(r"\[page \d+\]")


def marker(page_number: int) -> str:
    return f"[page {page_number}]"


class PdfExtractor:
    extensions = EXTENSIONS

    def __init__(self, transcriber: Optional[PageTranscriber] = None) -> None:
        self._transcriber = transcriber
        self.version = self._fingerprint()

    def _fingerprint(self) -> str:
        """A hash of every input that can change the output; a new input must be added here"""
        declared = {
            "extractor": VERSION,
            "transcriber": None if self._transcriber is None else f"{self._transcriber.id}.{self._transcriber.version}",
            "render_dpi": RENDER_DPI,
        }
        digest = hashlib.sha256(json.dumps(declared, sort_keys=True).encode()).hexdigest()[:16]
        return f"{VERSION}-{digest}"

    def check_availability(self) -> Optional[str]:
        """
        Pure-Python wheel with a bundled binary, so nothing to probe
        """
        return None

    def extract(self, path: Path) -> Extraction:
        # ? Imported here, not at module scope, so an absent optional dependency is genuinely tolerated
        import pypdfium2

        try:
            document = pypdfium2.PdfDocument(str(path))
        except Exception as e:
            raise DocumentError("extraction_failed", f"could not open the PDF ({e}); try re-uploading it") from e

        lines: list[str] = []
        empty_pages: list[int] = []
        page_visuals: list[PageVisuals] = []
        page_start_line: dict[int, int] = {}

        try:
            for index in range(len(document)):
                page_number = index + 1
                # ! Marker lines are part of the stream, so every line number below counts them
                lines.append(marker(page_number))
                page_start_line[index] = len(lines)

                page = document[index]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_bounded()
                    visuals = _page_visuals(page, textpage, page_number)
                finally:
                    textpage.close()
                    page.close()

                if not text.strip():
                    empty_pages.append(page_number)
                if visuals is not None:
                    page_visuals.append(visuals)
                lines.extend(_escape_marker(line) for line in normalize(text).split("\n"))

            if self._transcriber is not None and empty_pages:
                self._transcribe_empty(document, empty_pages, page_start_line, lines, page_visuals)

            outline = _read_outline(document, page_start_line)
        except DocumentError:
            raise
        except Exception as e:
            raise DocumentError("extraction_failed", f"could not read the PDF ({e}); try re-uploading it") from e
        finally:
            document.close()

        # ? Trailing blank lines carry nothing, and dropping them keeps split and splitlines counts equal at the end too
        while lines and not lines[-1]:
            lines.pop()

        summary: dict[str, Any] = {"pages": len(page_start_line), "extractor": "pdf", "version": VERSION}
        return Extraction(
            text="\n".join(lines),
            outline=outline,
            pages_without_text=empty_pages,
            summary=summary,
            page_visuals=page_visuals,
        )

    def _transcribe_empty(
        self,
        document: Any,
        empty_pages: list[int],
        page_start_line: dict[int, int],
        lines: list[str],
        page_visuals: list[PageVisuals],
    ) -> None:
        """
        Fill pages that produced no text layer, in place

        A page the engine cannot read stays in empty_pages
        """
        assert self._transcriber is not None
        still_empty: list[int] = []
        transcribed: set[int] = set()

        for page_number in empty_pages:
            index = page_number - 1
            page = document[index]
            try:
                image = page.render(scale=RENDER_DPI / 72).to_pil()
            finally:
                page.close()

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            text = self._transcriber.transcribe(buffer.getvalue()).strip()
            if not text:
                still_empty.append(page_number)
                continue

            inserted = [_escape_marker(line) for line in normalize(text).split("\n")]
            at = page_start_line[index]
            lines[at:at] = inserted
            _shift_starts_after(page_start_line, index, len(inserted))
            transcribed.add(page_number)

        empty_pages[:] = still_empty
        for i, visual in enumerate(page_visuals):
            if visual.page in transcribed:
                page_visuals[i] = replace(visual, transcribed_by=self._transcriber.id)


def _shift_starts_after(page_start_line: dict[int, int], index: int, inserted: int) -> None:
    """Every later page's start moves down by the number of lines inserted above it"""
    for other in page_start_line:
        if other > index:
            page_start_line[other] += inserted


def _escape_marker(line: str) -> str:
    """
    Keep document text from impersonating a page marker

    A line that reads exactly like a marker would otherwise make a real page ambiguous to the outline
    """
    return f" {line}" if MARKER.fullmatch(line) else line


def _read_outline(document: Any, page_start_line: dict[int, int]) -> list[OutlineEntry]:
    """
    Bookmarks mapped onto stream line numbers

    A bookmark whose destination cannot be resolved is dropped rather than guessed at
    """
    entries: list[OutlineEntry] = []
    for bookmark in document.get_toc():
        destination = bookmark.get_dest()
        if destination is None:
            continue
        line = page_start_line.get(destination.get_index())
        if line is None:
            continue
        label = normalize(bookmark.get_title() or "").strip()
        if label:
            entries.append(OutlineEntry(line=line, kind="section", label=label, level=int(bookmark.level)))
    return entries


def _page_visuals(page: Any, textpage: Any, page_number: int) -> Optional[PageVisuals]:
    """
    Image objects on a page, the fraction of the page they cover, and the text under the largest

    None for a page with no images
    """
    import pypdfium2.raw as raw

    width, height = page.get_size()
    area = float(width) * float(height)
    covered = 0.0
    count = 0
    largest_area = -1.0
    largest: Optional[tuple[float, float, float]] = None
    for obj in page.get_objects():
        if obj.type != raw.FPDF_PAGEOBJ_IMAGE:
            continue
        count += 1
        # ? get_bounds is (left, bottom, right, top) in PDF page coordinates
        left, bottom, right, top = obj.get_bounds()
        size = abs(float(right) - float(left)) * abs(float(top) - float(bottom))
        covered += size
        if size > largest_area:
            largest_area = size
            largest = (float(left), float(bottom), float(right))

    if count == 0:
        return None
    # ! Clamped to 1: overlapping images sum past the page area
    coverage = min(covered / area, 1.0) if area > 0 else 0.0
    caption = None if largest is None else _caption_below(textpage, largest, float(height))
    return PageVisuals(page=page_number, image_count=count, image_coverage=coverage, nearby_text=caption)


def _caption_below(textpage: Any, bounds: tuple[float, float, float], page_height: float) -> Optional[str]:
    """
    Text in the strip directly under an image

    A hint, never a label: body text in that strip reads the same as a caption
    """
    left, bottom, right = bounds
    band = min(page_height * CAPTION_BAND_FRACTION, CAPTION_BAND_MAX)
    floor = max(bottom - band, 0.0)
    if floor >= bottom:
        return None
    found = textpage.get_text_bounded(left=left, bottom=floor, right=right, top=bottom)
    caption = " ".join(normalize(found).split())
    return caption[:CAPTION_MAX_CHARS] or None
