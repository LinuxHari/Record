import re

from record.app.shared.regex import RE_ALPHA_LOWER, RE_EMAIL
from record.app.shared.validators import StringValidator


class PasswordValidator(StringValidator):
    label = "Password"

    def _validate_rules(self, value: str) -> None:
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_]", value):
            raise ValueError("Password must contain at least one special character")


class UsernameValidator(StringValidator):
    label = "Username"

    def _validate_rules(self, value: str) -> None:
        if " " in value:
            raise ValueError("Username cannot contain spaces")
        if not re.fullmatch(RE_ALPHA_LOWER, value):
            raise ValueError("Username can contain lowercase letters and numbers only")


class EmailValidator(StringValidator):
    label = "Email"

    def _validate_rules(self, value: str) -> None:
        if not re.fullmatch(RE_EMAIL, value):
            raise ValueError("Email address is not valid")


password_validator = PasswordValidator(min_len=8, max_len=255)
username_validator = UsernameValidator(min_len=3, max_len=32)
email_validator = EmailValidator(min_len=5, max_len=255)
