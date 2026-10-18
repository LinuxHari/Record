import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.types import ASGIApp, Message, Receive, Scope, Send

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

_STANDARD_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack"] = self.formatStack(record.stack_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS:
                log_entry.setdefault(key, value)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("record.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        token = correlation_id_ctx.set(request_id)
        method = scope["method"]
        path = scope["path"]
        started_at = time.perf_counter()
        response_status: int | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            self.logger.info(
                "Request started",
                extra={"http_method": method, "path": path},
            )
            await self.app(scope, receive, send_with_request_id)
            if response_status is not None:
                log = self.logger.error if response_status >= 500 else self.logger.info
                log(
                    "Request finalized",
                    extra={
                        "http_method": method,
                        "path": path,
                        "status_code": response_status,
                        "duration_ms": round(
                            (time.perf_counter() - started_at) * 1000, 2
                        ),
                    },
                )
        finally:
            correlation_id_ctx.reset(token)

    @staticmethod
    def _request_id(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                if (
                    value
                    and len(value) <= 128
                    and all(33 <= byte <= 126 for byte in value)
                ):
                    return value.decode("ascii")
                break
        return str(uuid.uuid4())
