import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import (
    Mapped,
    MappedAsDataclass,
    mapped_column,
    relationship,
    validates,
)

from record.app.assets.validators import (
    asset_name_validator,
    asset_size_validator,
    asset_type_validator,
)
from record.db.sql.postgres.session import PGBase
from record.dependencies import utc_now

if TYPE_CHECKING:
    from record.app.user.models import User


class AssetStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class Asset(MappedAsDataclass, PGBase):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default_factory=uuid.uuid4, init=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="assets")
    name: Mapped[str] = mapped_column(
        String(length=asset_name_validator.max_len), nullable=False
    )
    key: Mapped[str] = mapped_column(String(length=320), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(
        String(length=asset_type_validator.max_len), nullable=False
    )
    size: Mapped[int] = mapped_column(Integer(), nullable=False)  # Size in bytes
    chunk_status: Mapped[AssetStatus] = mapped_column(nullable=False, default=AssetStatus.PENDING, init=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default_factory=utc_now, init=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default_factory=utc_now, init=False, onupdate=utc_now)

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        _ = key
        return asset_name_validator.validate(value)

    @validates("type")
    def validate_type(self, key: str, value: str) -> str:
        _ = key
        return asset_type_validator.validate(value)

    @validates("size")
    def validate_size(self, key: str, value: int) -> int:
        _ = key
        return asset_size_validator.validate(value)

class AssetUpload(MappedAsDataclass, PGBase):
    __tablename__ = "asset_uploads"

    upload_id: Mapped[str] = mapped_column(
        String(length=256), nullable=False, unique=True, primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(
        String(length=asset_name_validator.max_len), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(length=asset_type_validator.max_len), nullable=False
    )
    size: Mapped[int] = mapped_column(Integer(), nullable=False)
    key: Mapped[str] = mapped_column(String(length=320), nullable=False, unique=True)
    status: Mapped[AssetStatus] = mapped_column(
        nullable=False, default=AssetStatus.PENDING, init=False
    )
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

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        _ = key
        return asset_name_validator.validate(value)

    @validates("type")
    def validate_type(self, key: str, value: str) -> str:
        _ = key
        return asset_type_validator.validate(value)

    @validates("size")
    def validate_size(self, key: str, value: int) -> int:
        _ = key
        return asset_size_validator.validate(value)
