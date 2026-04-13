"""
Structured logging for MPMB-Copilot.

Provides JSON-formatted logs with correlation IDs for tracing requests
through the full RAG pipeline (chunk -> embed -> retrieve -> generate -> respond).

Usage:
    from app.logger import get_logger, bind_context, request_context

    logger = get_logger(__name__)
    logger.info("indexing started", chunk_count=350, edition="2014")

    # In a FastAPI route, wrap with request context:
    async with request_context(session_id="abc-123"):
        logger.info("query received", query="how do I add a spell?")

    # For RAG pipeline stages:
    with pipeline_stage("retrieve", query=query):
        results = await retriever.search(query)
"""

import contextvars
import logging
import logging.handlers
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog  # type: ignore[import-not-found]

# Context variables (thread/task-safe, works with asyncio)
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_session_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)
_edition_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("edition", default=None)


# Backend package root: .../backend (parent of .../backend/app)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _resolve_log_dir() -> Path:
    """Resolve the log directory, anchoring relative paths to the backend root.

    Relative paths (including the default `./logs`) are interpreted
    relative to `backend/` so logs land in the same place regardless of
    which CWD started the process (project root via uvicorn, or
    backend/ via pytest).
    """
    raw = os.getenv("LOG_DIR", "./logs")
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path
    return path


# Configuration
@lru_cache(maxsize=1)
def _get_config() -> dict[str, Any]:
    """Read logging config from environment once."""
    return {
        "level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "format": os.getenv("LOG_FORMAT", "json"),  # "json" or "console"
        "show_locals": os.getenv("LOG_SHOW_LOCALS", "false").lower() == "true",
        "slow_query_threshold_ms": int(os.getenv("LOG_SLOW_QUERY_MS", "3000")),
        "log_dir": _resolve_log_dir(),
        "log_retention_days": int(os.getenv("LOG_RETENTION_DAYS", "30")),
        "log_error_retention_days": int(os.getenv("LOG_ERROR_RETENTION_DAYS", "90")),
    }


# Structlog processors
def _inject_context_vars(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Pull correlation IDs from contextvars into every log entry."""
    request_id = _request_id_ctx.get()
    session_id = _session_id_ctx.get()
    edition = _edition_ctx.get()

    if request_id:
        event_dict["request_id"] = request_id
    if session_id:
        event_dict["session_id"] = session_id
    if edition:
        event_dict["edition"] = edition

    return event_dict


def _add_service_info(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Tag every log with the service name for multi-container stacks."""
    event_dict.setdefault("service", "mpmb-copilot-backend")
    return event_dict


def _censor_sensitive(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Redact API keys and other secrets from log output."""
    sensitive_keys = {"api_key", "token", "secret", "password", "authorization"}
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            val = event_dict[key]
            if isinstance(val, str) and len(val) > 8:
                event_dict[key] = val[:4] + "***" + val[-4:]
            else:
                event_dict[key] = "***"
    return event_dict


# Setup (call once at app startup)
_configured = False


def configure_logging() -> None:
    """
    Configure structlog + stdlib logging. Call once from main.py or a
    Starlette lifespan handler.
    """
    global _configured
    if _configured:
        return
    _configured = True

    config = _get_config()
    level = getattr(logging, config["level"], logging.INFO)

    # Shared processors applied to every log message
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context_vars,
        _add_service_info,
        _censor_sensitive,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if config["format"] == "console":
        # Human-readable colored output for local dev
        console_renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    else:
        # JSON for Docker / log aggregation
        console_renderer = structlog.processors.JSONRenderer()

    # File logs are always JSON (machine-parseable, grep-friendly)
    file_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatters
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            console_renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            file_renderer,
        ],
        foreign_pre_chain=[*shared_processors, structlog.processors.format_exc_info],
    )

    root = logging.getLogger()
    root.handlers.clear()

    # 1. Console handler (stderr) - same as before
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    root.addHandler(console_handler)

    # 2. File handlers - daily rotation
    log_dir = config["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)

    # app.log - all messages at INFO+, rotates daily, keeps N days
    app_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        interval=1,
        backupCount=config["log_retention_days"],
        encoding="utf-8",
        utc=True,
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(file_formatter)
    app_handler.suffix = "%Y-%m-%d"
    root.addHandler(app_handler)

    # error.log - ERROR+ only, rotates daily, keeps longer
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "error.log",
        when="midnight",
        interval=1,
        backupCount=config["log_error_retention_days"],
        encoding="utf-8",
        utc=True,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    error_handler.suffix = "%Y-%m-%d"
    root.addHandler(error_handler)

    root.setLevel(level)

    # Quiet noisy libraries
    for noisy in ("httpcore", "httpx", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Let Uvicorn access logs through at INFO, errors at WARNING
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)


# Logger factory
def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger bound to the given module name.

        from app.logger import get_logger
        logger = get_logger(__name__)
        logger.info("hello", foo="bar")
    """
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)


# Context managers
@asynccontextmanager
async def request_context(
    session_id: str | None = None,
    edition: str | None = None,
    request_id: str | None = None,
):
    """
    Async context manager that binds correlation IDs for the lifetime of a
    request. Use in FastAPI dependencies or middleware.

        async with request_context(session_id="abc"):
            logger.info("processing")  # automatically includes session_id
    """
    rid = request_id or secrets.token_urlsafe(9)
    tok_req = _request_id_ctx.set(rid)
    tok_ses = _session_id_ctx.set(session_id) if session_id else None
    tok_ed = _edition_ctx.set(edition) if edition else None
    try:
        yield rid
    finally:
        _request_id_ctx.reset(tok_req)
        if tok_ses is not None:
            _session_id_ctx.reset(tok_ses)
        if tok_ed is not None:
            _edition_ctx.reset(tok_ed)


@contextmanager
def pipeline_stage(stage_name: str, **extra: Any):
    """
    Synchronous context manager that logs entry/exit/duration for a named
    RAG pipeline stage. Works inside async code too.

        with pipeline_stage("retrieve", query=query, top_k=8):
            results = retriever.search(query)

    Emits:
        {"event": "stage_start", "stage": "retrieve", "query": "...", ...}
        {"event": "stage_end",   "stage": "retrieve", "duration_ms": 142, ...}
    """
    log = get_logger("pipeline")
    log.info("stage_start", stage=stage_name, **extra)
    t0 = time.perf_counter()
    error = None
    try:
        yield
    except Exception as exc:
        error = exc
        raise
    finally:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        config = _get_config()
        slow = duration_ms > config["slow_query_threshold_ms"]
        if error:
            log.error(
                "stage_error",
                stage=stage_name,
                duration_ms=duration_ms,
                error_type=type(error).__name__,
                error_msg=str(error)[:500],
                **extra,
            )
        else:
            log_fn = log.warning if slow else log.info
            log_fn(
                "stage_end",
                stage=stage_name,
                duration_ms=duration_ms,
                slow=slow,
                **extra,
            )


# FastAPI middleware (drop-in)
class RequestLoggingMiddleware:
    """
    ASGI middleware that wraps every request in a correlation context and
    logs request/response pairs.

    Add to FastAPI:
        from app.logger import RequestLoggingMiddleware
        app.add_middleware(RequestLoggingMiddleware)

    Or in a lifespan/startup:
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
    """

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("http")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = secrets.token_urlsafe(9)
        method = scope.get("method", "?")
        path = scope.get("path", "?")
        status_code = 500  # default until we capture the real one

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Inject request-id header so the frontend can correlate
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        t0 = time.perf_counter()
        async with request_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                log_fn = self.logger.warning if status_code >= 400 else self.logger.info
                log_fn(
                    "http_request",
                    method=method,
                    path=path,
                    status=status_code,
                    duration_ms=duration_ms,
                )


# Convenience: FastAPI dependency for binding session context
def bind_context(**kwargs: Any) -> None:
    """
    Bind arbitrary key-value pairs to the current structlog context.
    Useful in FastAPI dependencies:

        @app.post("/api/chat")
        async def chat(body: ChatRequest):
            bind_context(session_id=body.session_id, edition=body.edition)
            ...
    """
    if "session_id" in kwargs:
        _session_id_ctx.set(kwargs.pop("session_id"))
    if "edition" in kwargs:
        _edition_ctx.set(kwargs.pop("edition"))
    # Everything else goes into structlog's contextvars
    structlog.contextvars.bind_contextvars(**kwargs)
