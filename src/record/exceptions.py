import logging
import re
from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError, NoResultFound, SQLAlchemyError

logger = logging.getLogger(__name__)


class AppException(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None):
        self.detail = detail or type(self).detail


class BadRequestException(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "The request was invalid."


class UnauthorizedException(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication is required."


class ForbiddenException(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to access this resource."


class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "The requested resource could not be found."


class ConflictException(AppException):
    status_code = status.HTTP_409_CONFLICT
    detail = "The request could not be completed due to a conflict with the current state of the resource."


class TooManyRequestsException(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many requests, try again later."


class InternalServerException(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = "An unexpected error occurred on the server."


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
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
            "not null",
            "cannot be null",
            "must not be null",
            "null value",
            "cannot insert null",
        )
    )

def _not_found_detail(exc: NoResultFound) -> str:
    message = str(exc).strip()
    match = re.fullmatch(
        r"(?:No\s+([A-Za-z][A-Za-z0-9_.-]*)\s+found|"
        r"([A-Za-z][A-Za-z0-9_.-]*)\s+not found)\.?",
        message,
        flags=re.IGNORECASE,
    )
    if match:
        return message
    return NotFoundException.detail


def _internal_error(exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Unhandled database error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": InternalServerException.detail},
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    if isinstance(exc, NoResultFound):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "detail": _not_found_detail(exc)},
        )

    if isinstance(exc, DataError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "detail": "Input is too long."},
        )

    if isinstance(exc, IntegrityError):
        message = str(exc.orig)
        if _is_not_null_violation(message):
            return _internal_error(exc)

        constraint_name = _constraint_name(exc)
        constraint_errors: Mapping[str, str] = getattr(
            request.app.state, "constraint_errors", {}
        )
        if constraint_name in constraint_errors:
            error_detail = constraint_errors[constraint_name]
            error_status = (
                status.HTTP_409_CONFLICT
                if constraint_name.startswith("uq_")
                else status.HTTP_400_BAD_REQUEST
            )
            return JSONResponse(
                status_code=error_status,
                content={"success": False, "detail": error_detail},
            )

        if (constraint_name and constraint_name.startswith("uq_")):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"success": False, "detail": "A record with given value(s) already exists."},
            )
        if (constraint_name and constraint_name.startswith("ck_")):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "detail": "Invalid input."},
            )

    return _internal_error(exc)


def register_exception_handlers(
    app: FastAPI, *, constraint_errors: Mapping[str, str] | None = None
) -> None:
    app.state.constraint_errors = constraint_errors or {}
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
