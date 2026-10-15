from record.exceptions.http_excpetions import BadRequestException, UnauthorizedException

class FieldValidationException(BadRequestException):
    def __init__(self, *, field: str, detail: str):
        self.field = field
        super().__init__(detail)

class TokenExpiredException(UnauthorizedException):
    def __init__(self):
        super().__init__("Token is expired")

class TokenInvalidException(UnauthorizedException):
    def __init__(self):
        super().__init__("Token is invalid")