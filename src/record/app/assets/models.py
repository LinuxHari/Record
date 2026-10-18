import uuid
import enum

from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer
from datetime import datetime

from record.db.sql.postgres.session import PGBase

class ChunkStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class Asset(MappedAsDataclass, PGBase):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default_factory=uuid.uuid4, init=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), nullable=False, init=False)
    user: Mapped["User"] = relationship(back_populates="assets")
    name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    url: Mapped[str]= mapped_column(String(length=1536), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    size: Mapped[int] = mapped_column(Integer(), nullable=False) # Size in bytes
    chunk_status: Mapped[ChunkStatus] = mapped_column(nullable=False, default_factory=ChunkStatus.PENDING, init=False)
    uploaded_at: Mapped[datetime] = mapped_column(nullable=False, default_factory=datetime.now, init=False)
    updated_at:  Mapped[datetime] = mapped_column(nullable=False, default_factory=datetime.now, init=False, onupdate=datetime.now)