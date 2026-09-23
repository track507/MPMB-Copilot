"""
RFC 9457 problem+json rendering for every error response

One shape for all errors: type (machine discriminator), title, status, detail (human message), instance
Validation adds an `errors` extension
Handlers are wired in main.py via register_problem_handlers()
"""

from http import HTTPStatus
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import config
from app.logger import get_logger
from app.services.uploads.errors import UploadError

logger = get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

# * Upload error code -> human title
# * The `type` URL is derived from the code
_UPLOAD_TITLES: dict[str, str] = {
    "invalid_filename": "Invalid filename",
    "extension_not_allowed": "Extension not allowed",
    "empty_file": "Empty file",
    "invalid_scope": "Invalid scope",
    "quota_exceeded": "Quota exceeded",
    "file_too_large": "File too large",
    "file_missing": "File missing",
    "not_found": "Not found",
    "forbidden": "Forbidden",
}


def type_for(code: str) -> str:
    return f"/api/problems/{code.replace('_', '-')}"


def _reason_phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    *,
    status: int,
    title: str,
    detail: str,
    type: str = "about:blank",
    instance: Optional[str] = None,
    **extensions: Any,
) -> JSONResponse:
    body: dict[str, Any] = {"type": type, "title": title, "status": status, "detail": detail}
    if instance:
        body["instance"] = instance
    for key, value in extensions.items():
        if value is not None:
            body[key] = value
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)


class ProblemError(Exception):
    """
    Raise to emit a problem with an explicit machine `type`
    """

    def __init__(self, *, status: int, type: str, title: str, detail: str, **extensions: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.type = type
        self.title = title
        self.detail = detail
        self.extensions = extensions


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # ? Existing endpoints keep raising HTTPException; only the rendered body changes
        return problem_response(
            status=exc.status_code,
            title=_reason_phrase(exc.status_code),
            detail=str(exc.detail),
            instance=request.url.path,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return problem_response(
            status=422,
            type=type_for("validation_error"),
            title="Validation failed",
            detail="The request did not pass validation.",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            status=exc.status,
            type=exc.type,
            title=exc.title,
            detail=exc.detail,
            instance=request.url.path,
            **exc.extensions,
        )

    @app.exception_handler(UploadError)
    async def _upload(request: Request, exc: UploadError) -> JSONResponse:
        return problem_response(
            status=exc.status_code,
            type=type_for(exc.code),
            title=_UPLOAD_TITLES.get(exc.code, "Error"),
            detail=exc.message,
            instance=request.url.path,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # ! Never leak internal error text in production
        logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        detail = str(exc) if config.is_development else "An unexpected error occurred"
        return problem_response(
            status=500,
            title="Internal Server Error",
            detail=detail,
            instance=request.url.path,
        )
