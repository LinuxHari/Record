from fastapi import status, Request
from fastapi.responses import JSONResponse
from .main import app

class AppException(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str = None):
        if detail:
            self.detail = detail

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

@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )