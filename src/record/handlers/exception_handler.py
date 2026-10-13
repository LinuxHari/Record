import re
from typing import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from record.exceptions.http_excpetions import AppException, InternalServerException

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
            **({"field": str(error["loc"][-1])} if error["loc"] else {}),
            "issue": error["msg"],
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
    original = exc.orig
    candidate = getattr(original, "constraint_name", None)
    if isinstance(candidate, str) and candidate:
        return candidate

    message = str(original)
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


# def _not_found_detail(exc: NoResultFound) -> str:
#     message = str(exc).strip()
#     match = re.fullmatch(
#         r"(?:No\s+([A-Za-z][A-Za-z0-9_.-]*)\s+found|"
#         r"([A-Za-z][A-Za-z0-9_.-]*)\s+not found)\.?",
#         message,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return message
#     return NotFoundException.message


def _internal_error() -> JSONResponse:
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Request failed",
        issue=InternalServerException.message,
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    # if isinstance(exc, NoResultFound):
    #     return _error_response(
    #         status.HTTP_404_NOT_FOUND,
    #         message="Request failed",
    #         issue=_not_found_detail(exc),
        # )
    print("Sql exception:", exc)
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

        constraint_name = _constraint_name(exc) # Extract constraint from error
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
    print("Unhandled exception:", exc)
    return _internal_error()


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
    app.add_exception_handler(Exception, unexpected_exception_handler)
