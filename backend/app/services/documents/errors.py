from typing import Literal

DocumentErrorCategory = Literal[
    "extraction_failed",
    "extractor_unavailable",
    "no_text_layer",
    "extracted_too_large",
    "unsupported_format",
]


class DocumentError(Exception):
    """
    A document the tools could not turn into readable text

    The tool layer renders it as an [error] string so the model can recover within the turn instead of losing it
    Categories label the message; nothing crosses an HTTP boundary, so they are not wire codes
    """

    def __init__(self, category: DocumentErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category: DocumentErrorCategory = category
        self.message = message

    def as_tool_error(self) -> str:
        return f"[error] {self.message}"
