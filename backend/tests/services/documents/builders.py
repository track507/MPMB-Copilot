"""
Test documents built at test time, so no binary fixture is committed

Real guides are wrong for the repo on licensing and size, and MPMB sheets are Patreon-only and must never ship
A hand-assembled PDF is small, readable in a diff, and exercises text, empty pages and the outline
"""

from collections.abc import Sequence
from pathlib import Path


def _escape(text: str) -> str:
    """PDF literal strings reserve backslash and both parentheses"""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: Sequence[Sequence[str]], outline: Sequence[tuple[str, int]] = ()) -> bytes:
    """
    A minimal PDF with one Helvetica text line per string, and bookmarks to page indexes

    An empty list makes a page with no text layer, which is how the OCR seam is exercised
    """
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_ids: list[int] = []
    for lines in pages:
        ops = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
        ops.extend(f"({_escape(line)}) Tj T*" for line in lines)
        ops.append("ET")
        stream = "\n".join(ops) if lines else ""
        content_ids.append(add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"))

    pages_obj = add("")
    page_ids = [
        add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content_id} 0 R >>"
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


# * The standard fixture: two text pages around an image-only page, with a two-entry outline
GUIDE_PAGES = [
    ["Chapter One: Blood Hunters", "The content stream holds the text.", "Make a saving throw (DC 15)."],
    [],
    ["Chapter Two: Grim Hollow", "A Wisdom saving throw, or be Frightened."],
]
GUIDE_OUTLINE = [("Chapter One", 0), ("Chapter Two", 2)]


def write_pdf(
    path: Path,
    pages: Sequence[Sequence[str]] = GUIDE_PAGES,
    outline: Sequence[tuple[str, int]] = GUIDE_OUTLINE,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_pdf(pages, outline))
    return path
