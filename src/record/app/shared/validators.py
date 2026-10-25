class StringValidator:
    label = "Value"

    def __init__(self, *, min_len: int, max_len: int) -> None:
        if min_len > max_len:
            raise ValueError("min_len cannot be greater than max_len")

        self.min_len = min_len
        self.max_len = max_len

    def validate(self, value: str, validate_len: bool = True) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{self.label} must be a string")
        if validate_len:
            if len(value) < self.min_len:
                raise ValueError(
                    f"{self.label} must be at least {self.min_len} characters"
                )
            if len(value) > self.max_len:
                raise ValueError(
                    f"{self.label} must not exceed {self.max_len} characters"
                )
        self._validate_rules(value)
        return value

    def _validate_rules(self, value: str) -> None:
        _ = value


class IntegerValidator:
    label = "Value"

    def __init__(self, *, min_value: int, max_value: int) -> None:
        if min_value > max_value:
            raise ValueError("min_value cannot be greater than max_value")

        self.min_value = min_value
        self.max_value = max_value

    def validate(self, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{self.label} must be an integer")
        if value < self.min_value:
            raise ValueError(f"{self.label} must be at least {self.min_value}")
        if value > self.max_value:
            raise ValueError(f"{self.label} must not exceed {self.max_value}")
        return value
