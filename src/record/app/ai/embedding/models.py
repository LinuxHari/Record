import uuid

from sqlalchemy import ForeignKey, Integer, String, DateTime, ARRAY
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column
from pgvector.sqlalchemy import Vector
from datetime import datetime

from record.db.sql.postgres.session import PGBase
from record.dependencies import utc_now


class Embeddings(MappedAsDataclass, PGBase):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default_factory=uuid.uuid4, init=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    text_context: Mapped[str] = mapped_column(String(), nullable=False)
    embeddings: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    pages: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default_factory=utc_now, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=utc_now,
        init=False,
        onupdate=utc_now,
    )
