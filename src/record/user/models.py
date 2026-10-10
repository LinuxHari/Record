import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, Index, TIMESTAMP, String, text
from sqlalchemy.orm import Mapped, mapped_column
from record.db.sql.postgres.session import PGBase

class User(PGBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) >= 3", name="username_min_length"),
        CheckConstraint("length(email) >= 5", name="email_min_length"),
        CheckConstraint("email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", name="email_regex_check"),        
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(String(length=32), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(length=255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(length=255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=True)