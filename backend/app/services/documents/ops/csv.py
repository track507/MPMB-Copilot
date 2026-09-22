"""
CSV and TSV extraction, stdlib only

The degenerate case that proves the outline contract: a table has no navigable divisions, so the outline is empty
"""

import csv
import io
from pathlib import Path
from typing import Any, Optional

from app.services.documents.errors import DocumentError
from app.services.documents.protocol import Extraction, normalize

EXTENSIONS = frozenset({".csv", ".tsv"})
VERSION = "1"

_SNIFF_BYTES = 65_536
_CELL_SEPARATOR = " | "


class CsvExtractor:
    extensions = EXTENSIONS
    version = VERSION

    def check_availability(self) -> Optional[str]:
        """Stdlib only, so there is nothing to probe"""
        return None

    def extract(self, path: Path) -> Extraction:
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as e:
            raise DocumentError("extraction_failed", f"could not read the file ({e})") from e

        dialect = _dialect_for(path, raw)
        rows: list[str] = []
        first_row: list[str] = []
        try:
            for record in csv.reader(io.StringIO(raw, newline=""), dialect):
                # ! A quoted cell may contain newlines, and one row must stay one line or read and grep lose their place
                cells = [" ".join(cell.split()) for cell in record]
                if not first_row:
                    first_row = cells
                rows.append(_CELL_SEPARATOR.join(cells))
        except csv.Error as e:
            # ? The realistic cause is one unterminated quote swallowing the rest of the file into a single field
            raise DocumentError("extraction_failed", f"could not parse the {path.suffix.lower()} file ({e})") from e

        summary: dict[str, Any] = {
            "rows": len(rows),
            "columns": len(first_row),
            "first_row": first_row,
            "extractor": "csv",
            "version": VERSION,
        }
        return Extraction(text=normalize("\n".join(rows)), outline=[], pages_without_text=[], summary=summary)


def _dialect_for(path: Path, raw: str) -> Any:
    if path.suffix.lower() == ".tsv":
        return csv.excel_tab
    try:
        return csv.Sniffer().sniff(raw[:_SNIFF_BYTES], delimiters=",;\t|")
    except csv.Error:
        return csv.excel
