from fastapi import status

class AppException(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    issue: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None):
        self.detail = detail or type(self).message
        super().__init__(self.detail)


class BadRequestException(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    issue = "bad_request"
    message = "The request was invalid."


class UnauthorizedException(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    issue = "unauthorized"
    message = "Authentication is required."


class ServiceUnavailableException(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    issue = "service_unavailable"
    message = "A required service is unavailable."


class ForbiddenException(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    issue = "forbidden"
    message = "You do not have permission to access this resource."


class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    issue = "not_found"
    message = "The requested resource could not be found."


class ConflictException(AppException):
    status_code = status.HTTP_409_CONFLICT
    issue = "conflict"
    message = "The request could not be completed due to a conflict with the current state of the resource."


class TooManyRequestsException(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    issue = "too_many_requests"
    message = "Too many requests, try again later."


class InternalServerException(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    issue = "internal_error"
    message = "An unexpected error occurred on the server."