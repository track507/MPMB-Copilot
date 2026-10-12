"""
Request body ceiling, enforced before routing, parsing, or authentication

FastAPI reads a whole body before it resolves dependencies, so the auth wall cannot stop an anon client from making the server buffer an unbounded one
"""

from typing import Optional

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.problem import problem_response
from app.config import config
from app.settings import settings

MULTIPART_OVERHEAD_BYTES = 1_048_576


def body_limit_for(method: str, path: str) -> int:
    if method == "POST" and path == f"{config.api_prefix}/uploads":
        return settings.upload_max_file_bytes + MULTIPART_OVERHEAD_BYTES
    return config.max_request_body_bytes


def _declared_length(scope: Scope) -> Optional[int]:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _detail(limit: int) -> str:
    return f"The request body exceeds {limit} bytes."


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = body_limit_for(scope["method"], scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            response = problem_response(
                status=413, title="Content Too Large", detail=_detail(limit), instance=scope["path"]
            )
            await response(scope, receive, send)
            return

        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=_detail(limit))
            return message

        await self.app(scope, counted, send)
