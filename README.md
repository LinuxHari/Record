# Logging

The FastAPI application writes structured JSON logs to standard output. Each
HTTP request reuses a valid incoming `X-Request-ID` header or generates a UUID,
includes that ID in its logs, and returns it in the response header. Log
records include a UTC timestamp, level, logger name, message, and any fields
provided through `logging`'s `extra` argument. Uvicorn logs use the same
formatter.

Request boundaries and application lifecycle events are logged at `INFO`;
unexpected database and application errors are logged at `ERROR`, with
exception details. Request bodies, credentials, and query strings are not
included in request logs.