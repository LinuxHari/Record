import logging
import re
from typing import Any, Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from record.exceptions.http_excpetions import (
    AppException,
    InternalServerException,
    ServiceUnavailableException,
)

from record.exceptions.custom_exceptions import FieldValidationException

logger = logging.getLogger(__name__)


def _validation_field(loc: tuple[str | int, ...]) -> str:
    path = list(loc)
    if path and path[0] in {"body", "query", "path", "header", "cookie"}:
        path.pop(0)

    if not path:
        return "request"

    field = ""
    for part in path:
        if isinstance(part, int):
            field += f"[{part}]"
        else:
            field += f".{part}" if field else part
    return field


def _validation_message(error: Mapping[str, Any]) -> str:
    field = _validation_field(error["loc"])
    label = field.rsplit(".", 1)[-1].split("[", 1)[0].replace("_", " ").title()
    error_type = error["type"]
    context = error.get("ctx") or {}

    if error_type == "string_too_short":
        return f"{label} should have at least {context['min_length']} characters"
    if error_type == "string_too_long":
        return f"{label} should not exceed {context['max_length']} characters"
    if error_type == "string_type":
        return f"{label} must be text"
    if error_type in {"int_parsing", "int_type"}:
        return f"{label} must be a valid integer"
    if error_type in {"float_parsing", "float_type"}:
        return f"{label} must be numeric"
    if error_type == "bool_type":
        return f"{label} must be true or false"
    if error_type == "list_type":
        return f"{label} must be a list"
    if error_type == "tuple_type":
        return f"{label} must be a tuple"
    if error_type == "set_type":
        return f"{label} must be a set"
    if error_type == "dict_type":
        return f"{label} must be an object"
    if error_type == "missing":
        return f"{label} is required"
    if error_type == "extra_forbidden":
        return f"{label} is not allowed"
    if error_type == "string_pattern_mismatch":
        return f"{label} has an invalid format"
    if error_type == "greater_than":
        return f"{label} must be greater than {context['gt']}"
    if error_type == "greater_than_equal":
        return f"{label} must be at least {context['ge']}"
    if error_type == "less_than":
        return f"{label} must be less than {context['lt']}"
    if error_type == "less_than_equal":
        return f"{label} must not exceed {context['le']}"

    message = error["msg"]
    if message.startswith("Input should be a valid "):
        return f"{label} must be a valid {message.removeprefix('Input should be a valid ')}"

    for prefix in ("Value error, ", "Assertion failed, "):
        if message.startswith(prefix):
            message = message.removeprefix(prefix)
            break

    for generic_prefix in ("String should ", "Number should ", "Input should "):
        if message.startswith(generic_prefix):
            return f"{label} should {message.removeprefix(generic_prefix)}"

    return message


def _error_response(
    status_code: int,
    *,
    message: str,
    issue: str,
    field: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    error = {"issue": issue}
    if field is not None:
        error = {"field": field, "issue": issue}

    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "status": "error",
            "message": message,
            "data": [error],
        },
    )


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return _error_response(
        exc.status_code,
        message="Request failed",
        issue=exc.detail,
        field=exc.field if isinstance(exc, FieldValidationException) else None,
    )


async def http_exception_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(
        exc.status_code,
        message="Request failed",
        issue=str(exc.detail),
        headers=exc.headers,
    )


async def request_validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": _validation_field(error["loc"]),
            "issue": _validation_message(error),
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "status": "error",
            "message": "Validation failed",
            "data": errors,
        },
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    candidate = getattr(exc.orig, "constraint_name", None)
    if isinstance(candidate, str) and candidate:
        return candidate

    message = str(exc.orig)
    match = re.search(
        r"\bconstraint\s+[\"'`]?([A-Za-z0-9_.-]+)",
        message,
        flags=re.IGNORECASE,
    )
    if match and match.group(1).lower() != "failed":
        return match.group(1)

    match = re.search(
        r"\bconstraint\s+failed\s*:\s*([A-Za-z0-9_.-]+)",
        message,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _is_not_null_violation(message: str) -> bool:
    message = re.sub(r"[-_]+", " ", message.lower())
    return any(
        phrase in message
        for phrase in (
            "not null", # To catch Pg & Sqlite not null error
            "cannot be null", # To catch MySQL not null error
        )
    )

def _internal_error() -> JSONResponse:
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Request failed",
        issue=InternalServerException.message,
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "Database operation failed",
        extra={"exception_type": type(exc).__name__},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    if isinstance(exc, DataError):
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            message="Request failed",
            issue="Input is too long.",
        )

    if isinstance(exc, IntegrityError):
        message = str(exc.orig)
        if _is_not_null_violation(message):
            return _internal_error()

        constraint_name = _constraint_name(exc)
        constraint_exceptions: Mapping[str, Mapping[str, str]] = getattr(
            request.app.state, "constraint_exceptions", {}
        )
        if constraint_name in constraint_exceptions:
            error = constraint_exceptions[constraint_name]
            error_status = (
                status.HTTP_409_CONFLICT
                if constraint_name.startswith("uq_")
                else status.HTTP_400_BAD_REQUEST
            )
            return _error_response(
                error_status,
                message="Request failed",
                issue=error["issue"],
                field=error.get("field"),
            )

        if constraint_name and constraint_name.startswith("uq_"):
            return _error_response(
                status.HTTP_409_CONFLICT,
                message="Request failed",
                issue="A record with given value(s) already exists.",
            )
        if constraint_name and constraint_name.startswith("ck_"):
            return _error_response(
                status.HTTP_400_BAD_REQUEST,
                message="Request failed",
                issue="Invalid input.",
            )

    return _internal_error()


async def unexpected_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled application exception",
        extra={"exception_type": type(exc).__name__},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _internal_error()


async def redis_exception_handler(_: Request, exc: RedisError) -> JSONResponse:
    return _error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        message="Request failed",
        issue=ServiceUnavailableException.message,
    )


def register_exception_handlers(
    app: FastAPI,
    *,
    constraint_exceptions: Mapping[str, Mapping[str, str]] | None = None,
) -> None:
    app.state.constraint_exceptions = constraint_exceptions or {}
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(RedisError, redis_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
