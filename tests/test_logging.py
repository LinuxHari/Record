import asyncio
import json
import logging
import uuid

from record.logging import (
    JSONFormatter,
    RequestLoggingMiddleware,
    correlation_id_ctx,
)


def test_json_formatter_includes_context_and_extra_fields() -> None:
    token = correlation_id_ctx.set("request-123")
    try:
        record = logging.LogRecord(
            "record.test",
            logging.INFO,
            __file__,
            1,
            "Loaded %s",
            ("items",),
            None,
        )
        record.batch_size = 50

        log_entry = json.loads(JSONFormatter().format(record))
    finally:
        correlation_id_ctx.reset(token)

    assert log_entry["message"] == "Loaded items"
    assert log_entry["correlation_id"] == "request-123"
    assert log_entry["batch_size"] == 50
    assert log_entry["timestamp"].endswith("+00:00")


def test_request_logging_middleware_sets_and_resets_request_id(
    caplog,
) -> None:
    request_id = "request-456"
    context_during_request: list[str] = []
    response_messages: list[dict[str, object]] = []

    async def app(scope, receive, send) -> None:
        _ = scope, receive
        context_during_request.append(correlation_id_ctx.get())
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-request-id", b"app-generated-id")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message) -> None:
        response_messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items",
        "headers": [(b"x-request-id", request_id.encode("ascii"))],
    }
    caplog.set_level(logging.INFO, logger="record.request")

    asyncio.run(RequestLoggingMiddleware(app)(scope, None, send))

    response_headers = dict(response_messages[0]["headers"])
    assert context_during_request == [request_id]
    assert correlation_id_ctx.get() == ""
    assert response_headers[b"x-request-id"] == request_id.encode("ascii")

    finalized = next(
        record
        for record in caplog.records
        if record.name == "record.request" and record.msg == "Request finalized"
    )
    assert finalized.status_code == 200
    assert finalized.path == "/items"


def test_request_logging_middleware_replaces_unsafe_request_id() -> None:
    context_during_request: list[str] = []
    response_messages: list[dict[str, object]] = []

    async def app(scope, receive, send) -> None:
        _ = scope, receive
        context_during_request.append(correlation_id_ctx.get())
        await send({"type": "http.response.start", "status": 204, "headers": []})

    async def send(message) -> None:
        response_messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items",
        "headers": [(b"x-request-id", b"bad\r\nvalue")],
    }

    asyncio.run(RequestLoggingMiddleware(app)(scope, None, send))

    request_id = dict(response_messages[0]["headers"])[b"x-request-id"].decode("ascii")
    assert str(uuid.UUID(request_id)) == request_id
    assert context_during_request == [request_id]
