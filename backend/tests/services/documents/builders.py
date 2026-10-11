"""
Test documents built at test time, so no binary fixture is committed

Real guides are wrong for the repo on licensing and size, and MPMB sheets are Patreon-only and must never ship
A hand-assembled PDF is small, readable in a diff, and exercises text, empty pages, images and the outline
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Optional

PAGE_WIDTH = 612
PAGE_HEIGHT = 792

FIRST_BASELINE = 720
LEADING = 14

_IMAGE_DATA = "00FFFF00>"

ImageRects = Mapping[int, Sequence[tuple[float, float, float, float]]]


def _escape(text: str) -> str:
    """PDF literal strings reserve backslash and both parentheses"""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(
    pages: Sequence[Sequence[str]],
    outline: Sequence[tuple[str, int]] = (),
    images: Optional[ImageRects] = None,
) -> bytes:
    """
    A minimal PDF with one Helvetica text line per string, and bookmarks to page indexes

    An empty list makes a page with no text layer, which is how the OCR seam is exercised
    images maps a page index to (x, y, width, height) rects in PDF units, each placing a tiny image XObject
    """
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    image_id: Optional[int] = None
    if images:
        image_id = add(
            "<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray "
            f"/BitsPerComponent 8 /Filter /ASCIIHexDecode /Length {len(_IMAGE_DATA)} >>\n"
            f"stream\n{_IMAGE_DATA}\nendstream"
        )

    content_ids: list[int] = []
    for index, lines in enumerate(pages):
        ops: list[str] = []
        for x, y, width, height in (images or {}).get(index, ()):
            ops.extend(["q", f"{width} 0 0 {height} {x} {y} cm", "/Im1 Do", "Q"])
        if lines:
            ops.extend(["BT", "/F1 12 Tf", f"{LEADING} TL", f"72 {FIRST_BASELINE} Td"])
            ops.extend(f"({_escape(line)}) Tj T*" for line in lines)
            ops.append("ET")
        stream = "\n".join(ops)
        content_ids.append(add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"))

    pages_obj = add("")
    resources = f"/Font << /F1 {font} 0 R >>"
    if image_id is not None:
        resources += f" /XObject << /Im1 {image_id} 0 R >>"
    page_ids = [
        add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << {resources} >> /Contents {content_id} 0 R >>"
        )
        for content_id in content_ids
    ]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_obj - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")

    catalog_extra = ""
    if outline:
        outline_root = add("")
        first_item = len(objects) + 1
        item_ids = [first_item + i for i in range(len(outline))]
        for i, (title, page_index) in enumerate(outline):
            links = f"/Parent {outline_root} 0 R"
            if i > 0:
                links += f" /Prev {item_ids[i - 1]} 0 R"
            if i < len(outline) - 1:
                links += f" /Next {item_ids[i + 1]} 0 R"
            add(f"<< /Title ({_escape(title)}) {links} /Dest [{page_ids[page_index]} 0 R /Fit] >>")
        objects[outline_root - 1] = (
            f"<< /Type /Outlines /First {item_ids[0]} 0 R /Last {item_ids[-1]} 0 R /Count {len(outline)} >>"
        ).encode("latin-1")
        catalog_extra = f" /Outlines {outline_root} 0 R"

    catalog = add(f"<< /Type /Catalog /Pages {pages_obj} 0 R{catalog_extra} >>")

    out = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


GUIDE_PAGES = [
    ["Chapter One: Blood Hunters", "The content stream holds the text.", "Make a saving throw (DC 15)."],
    [],
    ["Chapter Two: Grim Hollow", "A Wisdom saving throw, or be Frightened."],
]
GUIDE_OUTLINE = [("Chapter One", 0), ("Chapter Two", 2)]

FULL_PAGE_IMAGE: ImageRects = {0: [(0, 0, PAGE_WIDTH, PAGE_HEIGHT)]}


def write_pdf(
    path: Path,
    pages: Sequence[Sequence[str]] = GUIDE_PAGES,
    outline: Sequence[tuple[str, int]] = GUIDE_OUTLINE,
    images: Optional[ImageRects] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_pdf(pages, outline, images))
    return path
