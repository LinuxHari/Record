import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, Index, TIMESTAMP, String, text
from sqlalchemy.orm import Mapped, mapped_column, MappedAsDataclass
from record.db.sql.postgres.session import PGBase

class User(MappedAsDataclass, PGBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) >= 3", name="username_min_length"),
        CheckConstraint("length(email) >= 5", name="email_min_length"),
        CheckConstraint("email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", name="email_regex_check"),        
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"), init=False)
    username: Mapped[str] = mapped_column(String(length=32), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(length=255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(length=255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=text("now()"), init=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=text("now()"), init=False)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True, default=None)


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
