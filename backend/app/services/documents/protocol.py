"""
Port and shared types for document extraction

Adapters in ops/ satisfy DocumentExtractor structurally, without importing or subclassing it
This module also owns what a line is, because outline, read and grep must all count lines the same way
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

# ! Typographic characters extract correctly and still break grep, since a user types a straight quote
_ASCII_FOLD = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2026": "...",
        "\xa0": " ",
    }
)

# ! str.splitlines() breaks on every one of these, and read and grep count lines with it
_LINE_SEPARATORS = re.compile("\r\n|[\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")

# ! Declared here rather than in registry.py so core can read it without reaching an adapter
EXTRACTABLE_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".csv", ".tsv"})


def normalize(text: str) -> str:
    """
    Fold typography to ASCII, make \\n the only line separator, and strip trailing whitespace per line

    Idempotent, so the service can check an adapter's output by normalizing it again
    """
    unified = _LINE_SEPARATORS.sub("\n", text).translate(_ASCII_FOLD)
    return "\n".join(line.rstrip() for line in unified.split("\n"))


@dataclass(frozen=True)
class OutlineEntry:
    """One navigable division of a document, addressed by its line in the normalized stream"""

    line: int
    kind: Literal["page", "sheet", "section"]
    label: str
    # ? Nesting depth from the source outline, so mpmb_outline can indent a long table of contents
    level: int = 0


@dataclass(frozen=True)
class PageVisuals:
    """
    What a page holds that text extraction cannot convey

    Recorded for every page with image objects, whether or not that page also has text
    """

    page: int
    image_count: int
    image_coverage: float
    # ? Text under the largest image, a hint and never a label
    nearby_text: Optional[str] = None
    transcribed_by: Optional[str] = None


class PageTranscriber(Protocol):
    """One rendered page image in, text out"""

    id: str
    version: str

    def check_availability(self) -> Optional[str]:
        """None when usable, otherwise the reason, surfaced verbatim to the model"""
        ...

    def transcribe(self, image: bytes) -> str: ...


@dataclass
class Extraction:
    """An extractor's output: the normalized stream plus what the tools need to navigate it"""

    text: str
    outline: list[OutlineEntry]
    pages_without_text: list[int]
    summary: dict[str, Any]
    page_visuals: list[PageVisuals] = field(default_factory=list)


class DocumentExtractor(Protocol):
    """
    The port every format adapter satisfies

    Adapters must return normalized text; the service rejects anything that normalize() would still change
    """

    extensions: frozenset[str]
    version: str

    def check_availability(self) -> Optional[str]:
        """None when usable, otherwise the reason, surfaced verbatim to the model"""
        ...

    def extract(self, path: Path) -> Extraction: ...


# ! A cache key becomes a directory name, so it must never carry a separator or a traversal
_SAFE_KEY = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class CacheScope:
    """
    Which cache bucket a document's sidecar belongs in

    It is the only request-derived fact extraction needs, which is why callers pass this and not their whole context
    """

    kind: Literal["user", "shared", "source_root"]
    key: str

    def __post_init__(self) -> None:
        if not _SAFE_KEY.fullmatch(self.key):
            raise ValueError(f"cache scope key is not a safe path component: {self.key!r}")

    @classmethod
    def for_user(cls, user_id: str) -> "CacheScope":
        return cls(kind="user", key=user_id)

    @classmethod
    def shared(cls, tenant_id: str) -> "CacheScope":
        """One tenant's library bucket; derived text never crosses a tenant boundary"""
        return cls(kind="shared", key=tenant_id)

    @classmethod
    def for_source_root(cls, name: str) -> "CacheScope":
        return cls(kind="source_root", key=name)


def is_extractable(extension: str) -> bool:
    return extension.lower() in EXTRACTABLE_EXTENSIONS


@dataclass(frozen=True)
class CachedDocument:
    """
    A completed extraction on disk: the text the tools read and the metadata the outline serves
    """

    text_path: Path
    outline: list[OutlineEntry]
    pages_without_text: list[int]
    summary: dict[str, Any]


# * The OCR state an adapter records under summary["ocr"] for a document with empty pages
OcrState = Literal["off", "pending", "stalled", "unavailable", "done"]

_OCR_NOTES: dict[str, str] = {
    "pending": "OCR is reading them now, so read again in a few minutes",
    "stalled": "OCR failed on them after repeated attempts",
    "unavailable": "OCR is unavailable on this server",
    "off": "OCR is turned off",
    "done": "OCR found no readable text on them",
}


def ocr_note(summary: dict[str, Any]) -> str:
    """What a tool says about pages with no text layer, from the summary's OCR state"""
    return _OCR_NOTES.get(str(summary.get("ocr", "")), "OCR runs only on uploaded documents")


class DocumentReader(Protocol):
    """
    How the tools turn a document into readable text, without naming what does the extracting

    ! Only the two calls that touch disk live here; is_extractable is pure and needs no adapter
    """

    def lookup(self, path: Path, scope: CacheScope) -> Optional[CachedDocument]: ...

    def ensure_extracted(self, path: Path, scope: CacheScope) -> CachedDocument: ...
