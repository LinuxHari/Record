from record.exceptions.http_excpetions import BadRequestException

class FieldValidationException(BadRequestException):
    def __init__(self, *, field: str, detail: str):
        self.field = field
        super().__init__(detail)
