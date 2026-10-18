import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column, relationship, validates
from typing import List
from record.db.sql.postgres.session import PGBase
from record.app.shared.validators import username_validator, email_validator, password_validator
from record.exceptions.custom_exceptions import FieldValidationException 
from record.app.shared.regex import RE_EMAIL

class User(MappedAsDataclass, PGBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"length(username) >= {username_validator.min_len}", name="username_min_length"),
        CheckConstraint(f"length(email) >= {email_validator.min_len}", name="email_min_length"),
        CheckConstraint(fr"email ~* '{RE_EMAIL}'", name="email_regex_check"),        
       
        # Index("ix_users_email", "email", postgresql_where=text("deleted_at IS NULL")),
        # Index("ix_users_username", "username", postgresql_where=text("deleted_at IS NULL")),
        # Unique indexes are already created for above two indexes.
        Index("ix_users_active", "deleted_at", postgresql_where=text("deleted_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default_factory=uuid.uuid4, init=False
    )
    username: Mapped[str] = mapped_column(String(length=username_validator.max_len), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(length=email_validator.max_len), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(
        String(length=password_validator.max_len), nullable=False
    )
    assets: Mapped[List["Asset"]] = relationship(),
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default_factory=datetime.now, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default_factory=datetime.now,
        onupdate=datetime.now,
        init=False,
    )
    is_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(Boolean, nullable=True, default=None)

    @validates("username", "email")
    def validate_credentials(self, key: str, value: str) -> str:
        try:
            if key == "username":
                return username_validator.validate(value=value)

            return email_validator.validate(value=value)
        except ValueError as exc:
            raise FieldValidationException(field=key, detail=str(exc)) from exc


CONSTRAINT_EXCEPTIONS = {
    "uq_users_username": {
        "field": "username",
        "issue": "Username not available",
    },
    "uq_users_email": {
        "field": "email",
        "issue": "User with given email already exists",
    },
     "ck_users_username_min_length": {
        "field": "username",
        "issue": "Username is too small",
    },
    "ck_users_email_min_length": {
        "field": "email",
        "issue": "Email address is not valid",
    },
    "ck_users_email_regex_check": {
        "field": "email",
        "issue": "Email address is not valid",
    },
}
