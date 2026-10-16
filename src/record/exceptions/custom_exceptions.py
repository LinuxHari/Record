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


class TokenReuseDetectedException(TokenInvalidException):
    def __init__(self, session_id: str, user_id: str):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id