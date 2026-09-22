"""
PDF text extraction via pypdfium2

Reading order, not table cells: rows land one per line with the key first, which keeps them greppable
A table-aware extractor can join behind the same port if that turns out to limit answers
"""

import re
from pathlib import Path
from typing import Any, Optional

from app.services.documents.errors import DocumentError
from app.services.documents.protocol import Extraction, OutlineEntry, normalize

EXTENSIONS = frozenset({".pdf"})
VERSION = "1"

MARKER = re.compile(r"\[page \d+\]")


def marker(page_number: int) -> str:
    return f"[page {page_number}]"


class PdfExtractor:
    extensions = EXTENSIONS
    version = VERSION

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
                finally:
                    textpage.close()
                    page.close()

                if not text.strip():
                    empty_pages.append(page_number)
                lines.extend(_escape_marker(line) for line in normalize(text).split("\n"))

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
        return Extraction(text="\n".join(lines), outline=outline, pages_without_text=empty_pages, summary=summary)


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
